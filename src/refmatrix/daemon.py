"""rmx daemon — per-store Unix-socket server that holds one Store open
across many client invocations.

DuckDB is embedded + single-writer per file: every fresh `rmx` invocation
takes the exclusive write lock. When hooks fire in parallel (Edit/Write,
Stop, SubagentStop, SessionStart) the second client errors out with
`IOException: Could not set lock on file`. The daemon serializes all
access through one long-lived Store, so concurrent CLI clients become
sub-millisecond socket round-trips with no contention.

Protocol: newline-delimited JSON over `<root>/rmxd.sock`. Each request:
    {"op": "<name>", "args": {...}}
Response:
    {"ok": true,  "result": ...}
    {"ok": false, "error": "<message>"}

The daemon process is single-threaded: every request runs to completion
before the next is read. That matches the underlying Store's single-
writer semantics and keeps the protocol trivial.
"""
from __future__ import annotations

import errno
import json
import os
import signal
import socket
import sys
import time
from pathlib import Path
from typing import Any, Callable

from refmatrix.store import Store


SOCKET_NAME = "rmxd.sock"
PID_NAME = "rmxd.pid"
LOG_NAME = "rmxd.log"


def socket_path(root: Path) -> Path:
    return root / SOCKET_NAME


def pid_path(root: Path) -> Path:
    return root / PID_NAME


def is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def read_pid(root: Path) -> int | None:
    p = pid_path(root)
    if not p.exists():
        return None
    try:
        pid = int(p.read_text().strip())
    except (OSError, ValueError):
        return None
    return pid if is_alive(pid) else None


def ping(root: Path, timeout: float = 0.5) -> bool:
    """Quick health check: send {"op":"ping"} and expect ok=true."""
    sock = socket_path(root)
    if not sock.exists():
        return False
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect(str(sock))
            s.sendall(b'{"op":"ping"}\n')
            data = _recv_line(s, timeout)
        return json.loads(data).get("ok") is True
    except Exception:
        return False


def call(root: Path, op: str, args: dict | None = None,
         timeout: float = 60.0) -> dict:
    """Send a request to the daemon and return the parsed response."""
    sock = socket_path(root)
    payload = json.dumps({"op": op, "args": args or {}}).encode() + b"\n"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        s.connect(str(sock))
        s.sendall(payload)
        data = _recv_line(s, timeout)
    return json.loads(data)


def _recv_line(s: socket.socket, timeout: float) -> bytes:
    """Read until first newline. Daemon always terminates responses with \\n."""
    s.settimeout(timeout)
    chunks: list[bytes] = []
    while True:
        chunk = s.recv(65536)
        if not chunk:
            break
        chunks.append(chunk)
        if b"\n" in chunk:
            break
    buf = b"".join(chunks)
    nl = buf.find(b"\n")
    return buf[:nl] if nl >= 0 else buf


# ---------- server ----------------------------------------------------------


class Daemon:
    def __init__(self, root: Path, *, partition: str | None = None,
                 watch_root: "Path | list[Path] | None" = None,
                 watch_debounce_ms: int = 500,
                 watch_semantic: bool = False):
        self.root = Path(root).resolve()
        self.partition = partition
        # Filesystem watcher config. If `watch_roots` is non-empty,
        # serve_forever spawns a watchdog thread that schedules one
        # observer per root, debounces fs events across all of them,
        # and syncs the changed files through the daemon's Store.
        # Accepts a single Path (back-compat) or a list of Paths.
        if watch_root is None:
            self.watch_roots: list[Path] = []
        elif isinstance(watch_root, (list, tuple)):
            self.watch_roots = [Path(r).resolve() for r in watch_root]
        else:
            self.watch_roots = [Path(watch_root).resolve()]
        # Convenience scalar — first root, for callers that only need one
        # path (logs, sync_files default project_root). None if no watcher.
        self.watch_root: Path | None = (
            self.watch_roots[0] if self.watch_roots else None
        )
        self.watch_debounce_ms = watch_debounce_ms
        self.watch_semantic = watch_semantic
        self.store: Store | None = None
        self._stop = False
        self.log_fh = None
        # Async flush worker — single thread, serialized via a lock so it
        # never races the synchronous request handler on the shared Store.
        # Coalesces multiple fire-and-forget flush requests: if a flush is
        # already pending, additional `flush_async` calls are no-ops.
        import threading
        self._store_lock = threading.Lock()
        self._async_flush_pending = False
        self._async_lock = threading.Lock()
        # Cooperative shutdown event. SIGTERM/SIGINT set this so long-running
        # work (sync_files batch, ingest loop) can poll and early-exit
        # cleanly instead of pinning pool.shutdown(wait=True) until the
        # batch finishes minutes later.
        self._shutdown_event = threading.Event()
        self._watch_stop: "threading.Event | None" = None
        self._watch_thread: "threading.Thread | None" = None
        self._replica_stop: "threading.Event | None" = None
        self._replica_thread: "threading.Thread | None" = None
        self._replica_last: dict | None = None
        # Index-repair tick (option B). See `_start_index_repair_tick`.
        self._repair_stop: "threading.Event | None" = None
        self._repair_thread: "threading.Thread | None" = None
        # Guard against re-entering fast-exit from multiple threads racing
        # the same FatalException.
        self._fast_exit_armed = False
        self._fast_exit_lock = threading.Lock()
        # Dense embedder cache. Populated lazily by `_embedder()` on
        # first `embed` / `ann_search` op so the daemon doesn't load
        # ~134 MB of sentence-transformers state unless someone asks
        # for it. None when [dense] extra isn't installed yet.
        self._embedder_inst = None

    def _log(self, msg: str) -> None:
        if self.log_fh is None:
            return
        self.log_fh.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {msg}\n")
        self.log_fh.flush()

    def _embedder(self):
        """Lazy-cached Embedder. Loads sentence-transformers model on
        first call (~134 MB for the default bge-small-en-v1.5).
        Raises ImportError if the [dense] extra isn't installed —
        the op handler catches that and surfaces a clean error to
        the client instead of crashing the daemon."""
        existing = getattr(self, "_embedder_inst", None)
        if existing is not None:
            return existing
        from refmatrix.embedder import Embedder

        e = Embedder()
        # Trigger the model load so the first real call doesn't
        # eat the latency. Subsequent calls are model.encode-only.
        _ = e.dim
        self._embedder_inst = e
        self._log(f"embedder loaded model={e.model_name} dim={e.dim}")
        return e

    # ---- option D: SIGABRT/index-drift defense ----------------------------
    #
    # DuckDB secondary index drift on `idx_entity_links_lk_concept` after
    # bulk DELETEs can throw a fatal "Failed to delete all rows from index"
    # error. Once that fires DuckDB invalidates the database; any
    # subsequent op against that connection -- including from DuckDB's
    # own internal worker threads -- can throw a C++ exception that
    # bypasses Python's try/except and lands at std::terminate -> SIGABRT.
    #
    # Defense in depth:
    #   A. Pre-repair burst flushes (large path counts).
    #   B. Periodic index-repair tick.
    #   C. Fast-exit when invalidation is detected so we don't keep
    #      running against a poisoned connection long enough for an
    #      internal worker to crash the process.
    _FAST_EXIT_NEEDLES = (
        "Failed to delete all rows from index",
        "database has been invalidated",
    )

    @classmethod
    def _is_fatal_invalidation(cls, exc: BaseException) -> bool:
        msg = str(exc)
        return any(n in msg for n in cls._FAST_EXIT_NEEDLES)

    def _fast_exit_if_invalidated(self, exc: BaseException, where: str) -> None:
        """If `exc` looks like DuckDB index-drift / DB-invalidation,
        log + exit hard so the supervisor can spawn a fresh daemon
        before a DuckDB internal worker crashes us via std::terminate."""
        if not self._is_fatal_invalidation(exc):
            return
        with self._fast_exit_lock:
            if self._fast_exit_armed:
                return
            self._fast_exit_armed = True
        self._shutdown_event.set()
        self._stop = True
        try:
            self._log(
                f"fast-exit: {where}: detected DuckDB invalidation; "
                f"daemon exiting so supervisor can restart. exc={exc!r}"
            )
        except Exception:
            pass
        # Flush log fh before _exit so the message lands on disk.
        try:
            if self.log_fh is not None:
                self.log_fh.flush()
        except Exception:
            pass
        os._exit(2)

    def _drain_pool(self, name: str, pool, timeout_s: float) -> None:
        """Bounded ThreadPoolExecutor shutdown. ThreadPoolExecutor.shutdown
        has no native timeout — `wait=True` is unbounded and `wait=False`
        returns immediately without draining. Workaround: cancel queued
        futures + initiate non-blocking shutdown, then join the worker
        threads with a per-thread budget bounded by `timeout_s` total.

        Leaks worker threads on timeout. Acceptable for shutdown — process
        exit reaps them. Cooperative cancellation (_shutdown_event) in the
        long-running ops should make the timeout rare."""
        import time as _time
        pool.shutdown(wait=False, cancel_futures=True)
        deadline = _time.monotonic() + timeout_s
        # Internal: ThreadPoolExecutor.shutdown(wait=False) leaves the
        # worker threads referenced on `_threads`. Public API exposes no
        # timed join. Reach through to the worker set; if the contract
        # changes upstream we fall back to a single sleep-until-deadline.
        workers = getattr(pool, "_threads", None)
        if not workers:
            return
        for t in list(workers):
            remaining = deadline - _time.monotonic()
            if remaining <= 0:
                self._log(
                    f"pool drain {name}: timed out, {len(workers)} workers "
                    f"may outlive shutdown"
                )
                return
            t.join(timeout=remaining)

    def serve_forever(self) -> int:
        sock_path = socket_path(self.root)
        # Defensive: if another daemon is somehow alive on this socket
        # (concurrent spawn that slipped past the parent's flock), bail
        # instead of unlinking and stomping it.
        if sock_path.exists() and ping(self.root, timeout=0.2):
            return 0
        # Clean up any stale socket left from a crashed daemon.
        if sock_path.exists():
            sock_path.unlink()

        self.log_fh = (self.root / LOG_NAME).open("a", encoding="utf-8")
        self._log(f"daemon starting pid={os.getpid()} root={self.root}")
        pid_path(self.root).write_text(str(os.getpid()))
        # Banner the stderr stream too so an abort message landing there
        # can be correlated back to a specific daemon launch in rmxd.log.
        # Best-effort: stderr may be /dev/null when serve_forever is run
        # outside _run_detached (tests, in-process), in which case the
        # writes are silently dropped.
        try:
            sys.stderr.write(
                f"=== {time.strftime('%Y-%m-%dT%H:%M:%S')} "
                f"daemon starting pid={os.getpid()} ===\n"
            )
            sys.stderr.flush()
        except Exception:
            pass

        # Open Store once. All subsequent client ops reuse this connection,
        # so DuckDB's single-writer lock is held exactly once for the life
        # of the daemon.
        self.store = Store(self.root, partition=self.partition)
        self.store.init()
        self._log(f"store opened backend={self.store._backend.kind}")

        # Defensive recreate of idx_entity_links_lk_concept. DuckDB
        # secondary indexes drift after bulk DELETEs (prune_noise --drop,
        # purge_entity on high-degree concepts) and especially after a
        # SIGKILL'd daemon's WAL replays at next open. The fatal "Failed
        # to delete all rows from index" surfaces on the next op that
        # tries to touch entity_links — invalidating the database until
        # restart. ~1s startup cost on a 100k-row table; cheap insurance.
        if self.store._backend.kind == "duckdb":
            try:
                r = self.store.repair_entity_links_index()
                self._log(
                    f"repaired idx_entity_links_lk_concept "
                    f"rows={r.get('row_count', '?')}"
                )
            except Exception as e:
                self._log(f"repair_entity_links_index failed: {e}")

        if self.watch_root is not None:
            self._start_watcher()

        # Periodic bitmap-fragment flush. Fragments live in-memory in the
        # Store and only persist on close() -- so a daemon crash, SIGKILL,
        # or power loss between explicit checkpoints leaves the relational
        # tables ahead of the on-disk bitmaps. Walk every 30s and flush
        # any dirty fragments under _store_lock so we never grow more than
        # 30 seconds of unrecoverable bitmap drift.
        self._start_periodic_flush()
        # Option B: periodic index repair (DuckDB-only) -- see method docs.
        self._start_index_repair_tick()

        # Read replica via two-file rotation. Files: catalog.A.duckdb,
        # catalog.B.duckdb. A marker `.refmatrix/active` stores which
        # slot is the current writer. Refresh = catch up the inactive
        # slot then atomically swap the marker; the just-promoted slot
        # becomes writer, the demoted slot becomes the frozen reader.
        # `rmx replica path` reports the reader file for CLI tools that
        # want a lock-free read connection.
        self._active_slot = self._read_active_slot()
        self._bootstrap_rotation_if_needed()
        # Point read_only.duckdb at the inactive slot so in-process
        # readers always have a lock-free path even before the first
        # rotation cycle.
        self._refresh_read_only_link()
        # Refresh thread: catches up the inactive slot every N seconds
        # (RMX_REPLICA_REFRESH_S, default 5).
        self._start_replica_refresh()

        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(str(sock_path))
        os.chmod(sock_path, 0o600)
        srv.listen(16)
        srv.settimeout(1.0)

        def _shutdown(*_):
            self._stop = True
            self._shutdown_event.set()
        signal.signal(signal.SIGTERM, _shutdown)
        signal.signal(signal.SIGINT, _shutdown)

        # Bounded thread pool for per-connection handlers so a long-running
        # op (e.g. a multi-minute ingest holding _store_lock) does not
        # block the accept loop. Without this, `rmx daemon stop` and every
        # other client call queue behind the slow op and the only escape
        # is SIGKILL -- which risks DuckDB WAL corruption.
        #
        # Two-pool design — separates interactive CLI ops from bulk
        # background work so a long-running ingest can't starve `rmx
        # query`, `rmx stats`, etc. queued behind it.
        #
        #   cli_pool  — small. Latency-sensitive reads (query, context,
        #               neighbors, stats, ping, etc.).
        #   bg_pool   — bigger. Bulk + mutating ops (ingest_path,
        #               ingest_gmd, sync_*, prune_noise, vacuum,
        #               checkpoint, flush_queue, learn_from_grep, etc.).
        #   disp_pool — accept-loop handoff. Reads the request, classifies
        #               by op name, hands off to the right backend pool.
        #               Sized to cli + bg + slack so it never becomes the
        #               bottleneck.
        #
        # `_store_lock` still serializes mutations — pools shape
        # *scheduling*, not lock semantics. The win is that a cli request
        # arriving while bg_pool is saturated lands directly in cli_pool's
        # own queue at position 0, instead of behind N bg tasks in a
        # single shared pool.
        #
        # Sizing: `RMX_DAEMON_CLI_WORKERS` (default 4),
        # `RMX_DAEMON_BG_WORKERS` (default 12). Legacy
        # `RMX_DAEMON_WORKERS` is honored as a total budget when set —
        # split 1:3 cli:bg.
        from concurrent.futures import ThreadPoolExecutor

        legacy = os.environ.get("RMX_DAEMON_WORKERS")
        if legacy:
            total = max(2, int(legacy))
            cli_workers = max(1, total // 4)
            bg_workers = max(1, total - cli_workers)
        else:
            cli_workers = int(os.environ.get("RMX_DAEMON_CLI_WORKERS", "4") or "4")
            bg_workers = int(os.environ.get("RMX_DAEMON_BG_WORKERS", "12") or "12")
        cli_pool = ThreadPoolExecutor(
            max_workers=cli_workers, thread_name_prefix="rmxd-cli",
        )
        bg_pool = ThreadPoolExecutor(
            max_workers=bg_workers, thread_name_prefix="rmxd-bg",
        )
        disp_pool = ThreadPoolExecutor(
            max_workers=cli_workers + bg_workers + 4,
            thread_name_prefix="rmxd-disp",
        )
        # Expose for handlers / introspection / shutdown.
        self._cli_pool = cli_pool
        self._bg_pool = bg_pool
        self._disp_pool = disp_pool
        self._log(
            f"pools cli={cli_workers} bg={bg_workers} "
            f"disp={cli_workers + bg_workers + 4}"
        )

        def _run_handler(c) -> None:
            try:
                with c:
                    self._handle(c, cli_pool, bg_pool)
            except Exception as exc:
                self._log(f"handler thread crashed: {exc!r}")

        try:
            while not self._stop:
                try:
                    conn, _ = srv.accept()
                except socket.timeout:
                    continue
                disp_pool.submit(_run_handler, conn)
        finally:
            # Make absolutely sure the cooperative shutdown event is set:
            # serve loop may have exited via something other than the signal
            # handler (exception, explicit stop op). Workers polling this
            # event need to see it regardless of how we got here.
            self._shutdown_event.set()
            # Set ALL stop events first, before any draining/joining. The
            # periodic ticks (flush, repair, replica) each grab _store_lock
            # for a multi-second DuckDB op; if a tick fires DURING the pool
            # drain it can still be mid-call when we get to its join, leak
            # its worker thread, and pin the daemon's DuckDB connection past
            # store.close() — which is what stranded PID 79273 holding
            # catalog.B's lock for 8 minutes after "daemon stopped".
            if self._watch_stop is not None:
                self._watch_stop.set()
            if getattr(self, "_flush_stop", None) is not None:
                self._flush_stop.set()
            if getattr(self, "_repair_stop", None) is not None:
                self._repair_stop.set()
            if getattr(self, "_replica_stop", None) is not None:
                self._replica_stop.set()
            # Step 1: stop the watcher BEFORE pool shutdowns. The watcher
            # debouncer fires _flush() outside the pools but grabs
            # _store_lock — if it kicks off a new flush while we're trying
            # to drain bg_pool, that flush can hold the lock for minutes
            # against a queued bg task and pin shutdown.
            if self._watch_thread is not None:
                self._watch_thread.join(timeout=3.0)
            # Step 2: bounded pool drain. `wait=True` is unbounded — an
            # in-flight ingest/sync (cancel_check now lets it early-exit)
            # should finish within a couple seconds. Hard timeout caps
            # the worst case; we accept leaking a worker thread (daemon=True
            # via thread_name_prefix on the executor's threads are not
            # daemon, so we live with the wait_for_workers ceiling).
            shutdown_timeout = float(
                os.environ.get("RMX_DAEMON_SHUTDOWN_TIMEOUT_S", "10") or "10"
            )
            self._drain_pool("disp", disp_pool, shutdown_timeout)
            self._drain_pool("cli", cli_pool, shutdown_timeout)
            self._drain_pool("bg", bg_pool, shutdown_timeout)
            if getattr(self, "_flush_thread", None) is not None:
                self._flush_thread.join(timeout=3.0)
            if getattr(self, "_repair_thread", None) is not None:
                self._repair_thread.join(timeout=3.0)
            if getattr(self, "_replica_thread", None) is not None:
                self._replica_thread.join(timeout=3.0)
            # Final flush before close() so anything queued in the last
            # interval lands. close() also flushes, but doing it explicitly
            # under _store_lock keeps the on-disk state consistent if
            # close() races with a late handler.
            #
            # Bounded acquire: if a leaked drain-pool worker still holds
            # _store_lock, blocking forever here turns the daemon into a
            # zombie process that keeps the writer-slot file lock and
            # stops the next spawn from refreshing the replica. 5s budget
            # is generous; if we still can't get it, the worker is in a
            # C-extension call we can't preempt -- skip the flush and let
            # the process exit so a fresh daemon can take over.
            try:
                if self.store is not None:
                    if self._store_lock.acquire(timeout=5.0):
                        try:
                            self.store.flush_fragments()
                        finally:
                            self._store_lock.release()
                    else:
                        self._log(
                            "final flush skipped: _store_lock contended "
                            "(5s timeout) -- leaked worker likely holds it; "
                            "exiting anyway so the next spawn isn't blocked"
                        )
            except Exception as exc:
                self._log(f"final flush failed: {exc!r}")
            srv.close()
            if sock_path.exists():
                sock_path.unlink()
            pid_p = pid_path(self.root)
            if pid_p.exists():
                pid_p.unlink()
            if self.store is not None:
                # Bounded close. A leaked pool/repair worker holding the
                # DuckDB connection mid-statement makes self._conn.close()
                # block forever -- which pins this process alive holding
                # the catalog file lock, so the next daemon spawn can never
                # open it (the exact stranding we saw with PID 79273).
                # Run close() on a background thread and bail after a budget;
                # the outer _run_detached finally calls os._exit(0) so the
                # kernel releases all fcntl/duckdb locks regardless.
                import threading as _t
                close_done = _t.Event()
                close_err: list[BaseException] = []
                def _do_close():
                    try:
                        self.store.close()
                    except BaseException as exc:
                        close_err.append(exc)
                    finally:
                        close_done.set()
                close_budget = float(
                    os.environ.get("RMX_STORE_CLOSE_TIMEOUT_S", "5") or "5"
                )
                _t.Thread(
                    target=_do_close, name="rmxd-close", daemon=True,
                ).start()
                if not close_done.wait(timeout=close_budget):
                    self._log(
                        f"store close timed out after {close_budget:.1f}s "
                        "-- leaked worker holds the connection; relying on "
                        "process exit to release file locks"
                    )
                elif close_err:
                    self._log(f"store close failed: {close_err[0]!r}")
            self._log("daemon stopped")
            if self.log_fh is not None:
                try:
                    self.log_fh.close()
                except Exception:
                    pass
            # Belt-and-suspenders force-exit. _run_detached's finally already
            # calls os._exit(0), but: (a) serve_forever may be called outside
            # _run_detached (rmxd entrypoint, tests) and (b) atexit handlers
            # registered by concurrent.futures.thread join all worker threads
            # before interpreter shutdown -- including the workers we just
            # leaked in _drain_pool. Skip atexit; the kernel reaps the
            # threads and releases all DuckDB file locks immediately.
            os._exit(0)
        return 0  # unreachable; satisfies `-> int` signature

    def _start_periodic_flush(self, interval_s: float | None = None) -> None:
        """Spawn a daemon thread that periodically calls
        store.flush_fragments() so in-memory bitmap state lands on disk
        even when no explicit close() / transaction() runs.

        Without this, fragments only persist at scope exit of an outer
        s.transaction() (added in the same series) or at Store.close().
        A SIGKILL between flushes leaves the relational tables ahead of
        the bitmaps -- exactly the corruption surface that wedged
        viascope earlier today.

        Interval defaults to 30s; override via RMX_DAEMON_FLUSH_S env."""
        import threading as _t
        if interval_s is None:
            interval_s = float(os.environ.get("RMX_DAEMON_FLUSH_S", "30") or "30")
        self._flush_stop = _t.Event()

        def _runner():
            while not self._flush_stop.is_set():
                # wait first so we don't immediately race the initial
                # transaction.flush at startup
                if self._flush_stop.wait(interval_s):
                    return
                if self.store is None:
                    continue
                try:
                    with self._store_lock:
                        if self.store._dirty_fragments:
                            n = len(self.store._dirty_fragments)
                            self.store.flush_fragments()
                            self._log(f"periodic flush: {n} fragment(s)")
                except Exception as exc:
                    self._log(f"periodic flush failed: {exc!r}")
                    self._fast_exit_if_invalidated(exc, "periodic flush")

        self._flush_thread = _t.Thread(
            target=_runner, name="rmxd-flush", daemon=True,
        )
        self._flush_thread.start()

    def _start_index_repair_tick(self, interval_s: float | None = None) -> None:
        """Option B: periodically DROP+CREATE idx_entity_links_lk_concept
        so secondary-index drift (which compounds across DELETE bursts)
        never accumulates past the tick window.

        Disabled by default since DuckDB 1.5.3 fixed the ART operator
        bug that drove the original recurrence (PR #22591). Enable by
        setting RMX_INDEX_REPAIR_S=60 (or any positive integer) if a
        new drift surface appears. Cost: ~1-5s under _store_lock per
        tick on a 100k-500k entity_links table -- non-trivial under
        CLI-priority workloads.

        DuckDB backend only -- SQLite has no equivalent drift.
        """
        if self.store is None or self.store._backend.kind != "duckdb":
            return
        if interval_s is None:
            interval_s = float(
                os.environ.get("RMX_INDEX_REPAIR_S", "0") or "0"
            )
        if interval_s <= 0:
            return
        import threading as _t
        self._repair_stop = _t.Event()

        def _runner():
            while not self._repair_stop.is_set():
                if self._repair_stop.wait(interval_s):
                    return
                if self.store is None:
                    continue
                try:
                    with self._store_lock:
                        r = self.store.repair_entity_links_index()
                    self._log(
                        f"periodic index repair: rows={r.get('row_count','?')}"
                    )
                except Exception as exc:
                    self._log(f"periodic index repair failed: {exc!r}")
                    self._fast_exit_if_invalidated(exc, "index repair")

        self._repair_thread = _t.Thread(
            target=_runner, name="rmxd-repair", daemon=True,
        )
        self._repair_thread.start()

    # ---- read replica (rotation) ----------------------------------------

    def _replica_file(self, slot: str) -> Path:
        """Path to a rotation slot file (`A` or `B`)."""
        return self.root / f"catalog.{slot}.duckdb"

    @staticmethod
    def _is_invalidated_error(exc: Exception) -> bool:
        """True if `exc` indicates a DuckDB FATAL/invalidated catalog —
        the slot file is poisoned and only a rebuild recovers it."""
        msg = str(exc).lower()
        return (
            "has been invalidated" in msg
            or "fatal error" in msg
            or "internal error" in msg
        )

    def _rebuild_slot_from(self, source_slot: str, target_slot: str,
                           log_offset: int) -> None:
        """Overwrite `target_slot`'s catalog file with a fresh copy of
        `source_slot`'s. Used to recover an invalidated reader slot.

        Assumes no live DuckDB connection on either side at call time.
        Resets both offset markers so the next refresh tick treats both
        slots as caught up to `log_offset`.
        """
        import shutil as _shutil
        source_path = self._replica_file(source_slot)
        target_path = self._replica_file(target_slot)
        # Drop stale target + its WAL so DuckDB sees a clean snapshot
        # after the copy. Unlink is safe — the slot was already locked
        # out of the rotation by the invalidation.
        for p in (target_path,
                  target_path.with_name(target_path.name + ".wal")):
            try:
                if p.exists() or p.is_symlink():
                    p.unlink()
            except OSError as exc:
                self._log(f"rebuild unlink {p.name} failed: {exc!r}")
        _shutil.copy2(source_path, target_path)
        try:
            self._write_slot_offset(source_slot, log_offset)
            self._write_slot_offset(target_slot, log_offset)
        except Exception as exc:
            self._log(f"rebuild offset reset failed: {exc!r}")
        self._log(
            f"rebuilt slot {target_slot} from {source_slot} "
            f"(log_offset={log_offset})"
        )

    def _read_only_link(self) -> Path:
        """Symlink the daemon maintains pointing at the current READER
        (inactive) slot. In-process Stores that need to read while the
        daemon holds the writer slot open with a lock prefer this link
        over `catalog.duckdb` so they always land on a lock-free file.
        Updated atomically on every rotation swap (and on startup).
        """
        return self.root / "read_only.duckdb"

    def _refresh_read_only_link(self) -> None:
        """Point `read_only.duckdb` at the current inactive slot.
        Atomic via os.symlink-to-temp + os.replace. No-op if symlinks
        aren't available (Windows w/o developer mode); the Store side
        falls back to `catalog.duckdb` in that case."""
        import os as _os
        target = self._replica_file(self._inactive_slot()).name
        link = self._read_only_link()
        tmp = link.with_name(link.name + ".tmp")
        try:
            if tmp.exists() or tmp.is_symlink():
                tmp.unlink()
            _os.symlink(target, tmp)
            _os.replace(tmp, link)
        except OSError as exc:
            self._log(f"read_only.duckdb symlink update failed: {exc!r}")

    def _active_marker(self) -> Path:
        """File storing the current writer-slot letter (A or B)."""
        return self.root / "active"

    def _read_active_slot(self) -> str:
        """Read the currently-active (writer) slot from disk. Defaults to A."""
        m = self._active_marker()
        if m.exists():
            try:
                val = m.read_text().strip()
                if val in ("A", "B"):
                    return val
            except OSError:
                pass
        return "A"

    def _inactive_slot(self, active: str | None = None) -> str:
        active = active or getattr(self, "_active_slot", None) or self._read_active_slot()
        return "B" if active == "A" else "A"

    def _slot_offset_path(self, slot: str) -> Path:
        """Path to the byte-offset marker for a slot. The marker stores the
        end-of-facts.log byte position up through which the slot is
        current. Refresh applies log events [offset..end-of-log] to the
        inactive slot, then writes the new offset alongside."""
        return self.root / f"catalog.{slot}.offset"

    def _read_slot_offset(self, slot: str) -> int:
        p = self._slot_offset_path(slot)
        if not p.exists():
            return 0
        try:
            return int(p.read_text().strip() or "0")
        except (OSError, ValueError):
            return 0

    def _write_slot_offset(self, slot: str, offset: int) -> None:
        p = self._slot_offset_path(slot)
        try:
            p.write_text(str(int(offset)))
        except OSError as exc:
            self._log(f"slot offset write failed for {slot}: {exc!r}")

    def _refresh_replica_now(self) -> dict:
        """Rotate the read replica via facts.log delta-replay.

        Steps:
          1. Read end-of-log byte offset.
          2. If inactive slot is already at that offset, no-op.
          3. Open inactive slot in normal write mode.
          4. Replay log events [inactive_offset..end] into it.
          5. Persist the new offset alongside the inactive slot.
          6. Atomically swap the `active` marker — the just-caught-up
             slot becomes the writer, the previous writer becomes the
             frozen reader.

        Cost: O(delta entries) instead of O(file size). For idle
        catalogs the typical cycle is near-zero work.

        DuckDB only."""
        if self.store is None or self.store._backend.kind != "duckdb":
            return {"enabled": False, "reason": "non-duckdb backend"}
        active = self._active_slot
        inactive = self._inactive_slot(active)
        t0 = time.monotonic()
        with self._store_lock:
            # 1. snapshot current log position
            try:
                end_offset = self.store.log_path.stat().st_size \
                    if self.store.log_path.exists() else 0
            except OSError:
                end_offset = 0
            inactive_offset = self._read_slot_offset(inactive)
            if end_offset == inactive_offset:
                # Inactive is already current at this log offset; just
                # swap (active slot has the same logical state under our
                # CHECKPOINT-on-quiesce invariant — but we still need to
                # commit pending state to disk before promoting).
                try:
                    self.store._connect().execute("CHECKPOINT")
                    self.store.flush_fragments()
                except Exception:
                    pass
                self._write_slot_offset(active, end_offset)
                new_active = inactive
                # Atomic-ish swap: do the reopen FIRST so we know it
                # works before flipping the marker on disk. If we wrote
                # the marker first and the reopen failed, the marker
                # would lie about which slot is the writer for the rest
                # of the daemon's life.
                rebuilt = False
                try:
                    self.store.close()
                except Exception:
                    pass
                try:
                    self.store = Store(self.root, partition=self.partition)
                    self.store.db_path = self._replica_file(new_active)
                    self.store.init()
                except Exception as exc:
                    if self._is_invalidated_error(exc):
                        try:
                            self._rebuild_slot_from(active, new_active,
                                                    end_offset)
                            rebuilt = True
                            self.store = Store(self.root,
                                               partition=self.partition)
                            self.store.db_path = self._replica_file(new_active)
                            self.store.init()
                        except Exception as rexc:
                            self._log(
                                f"noop-swap rebuild failed: {rexc!r}"
                            )
                            try:
                                self.store = Store(self.root,
                                                   partition=self.partition)
                                self.store.db_path = self._replica_file(active)
                                self.store.init()
                            except Exception:
                                pass
                            return {"enabled": True, "ok": False,
                                    "error": f"noop-swap rebuild: {rexc!r}"}
                    else:
                        try:
                            self.store = Store(self.root,
                                               partition=self.partition)
                            self.store.db_path = self._replica_file(active)
                            self.store.init()
                        except Exception:
                            pass
                        return {"enabled": True, "ok": False,
                                "error": f"pointer swap: {exc!r}"}
                # Reopen succeeded — commit the swap.
                try:
                    self._active_marker().write_text(new_active)
                    self._active_slot = new_active
                    self._refresh_read_only_link()
                except Exception as exc:
                    return {"enabled": True, "ok": False,
                            "error": f"swap marker update: {exc!r}"}
                elapsed_ms = int((time.monotonic() - t0) * 1000)
                result = {
                    "enabled": True, "ok": True,
                    "applied": 0, "skipped_unresolved": 0,
                    "writer_slot": new_active,
                    "reader_slot": "B" if new_active == "A" else "A",
                    "writer_path": str(self._replica_file(new_active)),
                    "reader_path": str(self._replica_file(
                        "B" if new_active == "A" else "A")),
                    "log_end_offset": end_offset,
                    "elapsed_ms": elapsed_ms,
                    "refreshed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "mode": "noop-delta-rebuilt" if rebuilt else "noop-delta",
                    "rebuilt_slot": new_active if rebuilt else None,
                }
                self._replica_last = result
                return result

            # 2. CHECKPOINT + flush primary so its on-disk state equals
            # its logical state (the log already captured the writes).
            try:
                self.store._connect().execute("CHECKPOINT")
                self.store.flush_fragments()
            except Exception as exc:
                return {"enabled": True, "ok": False,
                        "error": f"pre-replay checkpoint: {exc!r}"}

            # 3. open inactive slot, apply delta, close.
            try:
                self.store.close()
            except Exception:
                pass
            inactive_store = None
            try:
                inactive_store = Store(self.root, partition=self.partition)
                inactive_store.db_path = self._replica_file(inactive)
                inactive_store.init()
                report = inactive_store.apply_log_delta(
                    inactive_offset, end_offset,
                )
                inactive_store.flush_fragments()
            except Exception as exc:
                # Reopen active so the daemon stays functional, then
                # surface the error. CRITICAL: drop the inactive slot's
                # DuckDB connection explicitly. Store.close() calls
                # flush_fragments() first, which can itself re-raise on
                # a FatalException-invalidated catalog and skip the real
                # connection close — leaving the file lock held for the
                # rest of the daemon's lifetime. Hit _conn directly to
                # guarantee release.
                if inactive_store is not None:
                    conn = getattr(inactive_store, "_conn", None)
                    if conn is not None:
                        try:
                            conn.close()
                        except Exception:
                            pass
                        inactive_store._conn = None
                    try:
                        inactive_store.close()
                    except Exception:
                        pass
                rebuilt = False
                if self._is_invalidated_error(exc):
                    try:
                        self._rebuild_slot_from(active, inactive, end_offset)
                        rebuilt = True
                    except Exception as rexc:
                        self._log(
                            f"delta-replay rebuild failed: {rexc!r}"
                        )
                self.store = Store(self.root, partition=self.partition)
                self.store.db_path = self._replica_file(active)
                self.store.init()
                err_kind = "delta-replay-rebuilt" if rebuilt else "delta-replay"
                return {"enabled": True, "ok": False,
                        "error": f"{err_kind}: {exc!r}",
                        "rebuilt_slot": inactive if rebuilt else None}
            else:
                try:
                    inactive_store.close()
                except Exception:
                    pass

            self._write_slot_offset(inactive, end_offset)

            # 4. swap pointer. The newly-current slot becomes writer.
            # Reopen FIRST so a failed open doesn't leave the on-disk
            # marker pointing at a slot the daemon can't actually use.
            new_active = inactive
            try:
                self.store = Store(self.root, partition=self.partition)
                self.store.db_path = self._replica_file(new_active)
                self.store.init()
            except Exception as exc:
                # Fall back to active so daemon stays functional. Do
                # not write the marker — current marker still names
                # the working slot.
                try:
                    self.store = Store(self.root, partition=self.partition)
                    self.store.db_path = self._replica_file(active)
                    self.store.init()
                except Exception:
                    pass
                return {"enabled": True, "ok": False,
                        "error": f"pointer swap: {exc!r}"}
            try:
                self._active_marker().write_text(new_active)
                self._active_slot = new_active
                self._refresh_read_only_link()
            except Exception as exc:
                return {"enabled": True, "ok": False,
                        "error": f"swap marker update: {exc!r}"}

        size = self._replica_file(new_active).stat().st_size \
            if self._replica_file(new_active).exists() else 0
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        result = {
            "enabled": True, "ok": True,
            "applied": report.get("applied", 0),
            "skipped_unresolved": report.get("skipped_unresolved", 0),
            "writer_slot": new_active,
            "reader_slot": "B" if new_active == "A" else "A",
            "writer_path": str(self._replica_file(new_active)),
            "reader_path": str(self._replica_file(
                "B" if new_active == "A" else "A")),
            "size_bytes": size,
            "log_start_offset": inactive_offset,
            "log_end_offset": end_offset,
            "elapsed_ms": elapsed_ms,
            "refreshed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "mode": "delta",
        }
        self._replica_last = result
        return result

    def _bootstrap_rotation_if_needed(self) -> None:
        """One-shot migration of legacy single-file `catalog.duckdb` into the
        A/B rotation pair. Runs at most once per .refmatrix root."""
        import shutil
        if self.store is None or self.store._backend.kind != "duckdb":
            return
        a = self._replica_file("A")
        b = self._replica_file("B")
        if a.exists() and b.exists():
            # Already migrated. But pre-0.3.10 daemons didn't seed offset
            # files — if they're missing, set both to current log end so
            # the first delta-replay doesn't try to re-apply the whole log.
            try:
                if not self._slot_offset_path("A").exists() or \
                   not self._slot_offset_path("B").exists():
                    log_size = self.store.log_path.stat().st_size \
                        if self.store.log_path.exists() else 0
                    self._write_slot_offset("A", log_size)
                    self._write_slot_offset("B", log_size)
                    self._log(
                        f"rotation offsets seeded at log_offset={log_size} "
                        f"(0.3.10 upgrade)"
                    )
            except Exception as exc:
                self._log(f"offset seed failed: {exc!r}")
            return

        # Asymmetric repair: exactly one slot exists. Common cause: the
        # other slot's WAL got corrupted (a DuckDB SIGABRT-era artifact),
        # operator deleted it, and now we re-enter bootstrap. Without
        # this branch the legacy-copy path below would clobber the
        # surviving slot with a STALER pre-rotation snapshot. Instead:
        # copy the surviving slot into the missing one, preserve the
        # active marker that picked the survivor (or default to the
        # survivor itself), and skip the legacy seed entirely.
        if a.exists() ^ b.exists():
            survivor = "A" if a.exists() else "B"
            missing = "B" if survivor == "A" else "A"
            survivor_path = self._replica_file(survivor)
            missing_path = self._replica_file(missing)
            try:
                with self._store_lock:
                    if self.store is not None:
                        try:
                            self.store._connect().execute("CHECKPOINT")
                            self.store.flush_fragments()
                            self.store.close()
                        except Exception:
                            pass
                    shutil.copy2(survivor_path, missing_path)
                    marker = self._active_marker()
                    current = (marker.read_text().strip()
                               if marker.exists() else "")
                    if current not in ("A", "B"):
                        marker.write_text(survivor)
                    self.store = Store(self.root, partition=self.partition)
                    self.store.db_path = self._replica_file(
                        marker.read_text().strip()
                    )
                    self.store.init()
                    self._active_slot = marker.read_text().strip()
                    log_size = self.store.log_path.stat().st_size \
                        if self.store.log_path.exists() else 0
                    self._write_slot_offset("A", log_size)
                    self._write_slot_offset("B", log_size)
                    self._log(
                        f"rotation slot repair: cloned {survivor} -> "
                        f"{missing}, active={self._active_slot}, "
                        f"log_offset={log_size}"
                    )
            except Exception as exc:
                self._log(f"rotation slot repair failed: {exc!r}")
            return

        legacy = self.root / "catalog.duckdb"
        # The current Store opened catalog.duckdb. To bootstrap we close
        # it, copy the legacy file into both A and B, and reopen on A.
        try:
            with self._store_lock:
                self.store._connect().execute("CHECKPOINT")
                self.store.flush_fragments()
                self.store.close()
                if legacy.exists():
                    shutil.copy2(legacy, a)
                    shutil.copy2(legacy, b)
                else:
                    # Brand-new store with no legacy file. Just create an
                    # empty A; B will be seeded on first refresh.
                    a.touch()
                    b.touch()
                self._active_marker().write_text("A")
                self.store = Store(self.root, partition=self.partition)
                self.store.db_path = a
                self.store.init()
                self._active_slot = "A"
                # Seed both slots' offsets to current log position so the
                # first refresh sees no delta to replay (both slots are
                # already at the bootstrap snapshot point).
                try:
                    log_size = self.store.log_path.stat().st_size \
                        if self.store.log_path.exists() else 0
                except OSError:
                    log_size = 0
                self._write_slot_offset("A", log_size)
                self._write_slot_offset("B", log_size)
                self._log(
                    f"rotation bootstrapped: A={a.name} B={b.name} "
                    f"active=A log_offset={log_size}"
                )
        except Exception as exc:
            self._log(f"rotation bootstrap failed: {exc!r}")

    def _start_replica_refresh(self, interval_s: float | None = None) -> None:
        """Spawn a daemon thread that periodically rotates the replica.

        Default interval 5s, override via RMX_REPLICA_REFRESH_S. Set
        RMX_REPLICA_REFRESH_S=0 to disable the thread entirely. DuckDB
        backend only."""
        import threading as _t
        if self.store is None or self.store._backend.kind != "duckdb":
            return
        if interval_s is None:
            interval_s = float(os.environ.get("RMX_REPLICA_REFRESH_S", "5") or "5")
        if interval_s <= 0:
            return
        self._replica_stop = _t.Event()

        def _runner():
            while not self._replica_stop.is_set():
                if self._replica_stop.wait(interval_s):
                    return
                try:
                    self._refresh_replica_now()
                except Exception as exc:
                    self._log(f"replica refresh failed: {exc!r}")
                    self._fast_exit_if_invalidated(exc, "replica refresh")

        self._replica_thread = _t.Thread(
            target=_runner, name="rmxd-replica", daemon=True,
        )
        self._replica_thread.start()

    def _start_watcher(self) -> None:
        """Spawn a watchdog thread that debounces fs events and syncs the
        changed files through the daemon's Store. The flush callback grabs
        `_store_lock` so it never races synchronous request handlers."""
        import threading
        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer
        except ImportError as exc:
            self._log(f"watchdog not installed; watcher disabled: {exc}")
            return
        from refmatrix.watch import Debouncer, is_relevant, is_curator_relevant
        from refmatrix.sync import sync_files

        self._watch_stop = threading.Event()
        curator_queue_path = self.root / "curator.queue"

        def _enqueue_curator(paths: list[str]) -> int:
            """Append curator-relevant paths to .refmatrix/curator.queue.

            Format: one JSON object per line — {ts, path, reason}. A
            SessionStart hook reads + drains this so Claude knows to
            dispatch the gmd-curator subagent."""
            import json as _json
            keep = [p for p in paths if is_curator_relevant(Path(p))]
            if not keep:
                return 0
            now = time.time()
            try:
                with curator_queue_path.open("a", encoding="utf-8") as fh:
                    for p in keep:
                        fh.write(_json.dumps({
                            "ts": now, "path": p, "reason": "fs-change",
                        }, ensure_ascii=False) + "\n")
            except OSError as exc:
                self._log(f"curator queue write failed: {exc!r}")
            return len(keep)

        # Option A: pre-repair the entity_links secondary index when the
        # flush batch is big enough that an in-flight DELETE burst is
        # likely to trip index drift. Disabled by default now that DuckDB
        # 1.5.3 fixes the ART bug at root (PR #22591); re-enable by
        # setting RMX_PRE_REPAIR_THRESHOLD to a positive integer.
        # Threshold gates the cost (~1-3s under _store_lock per flush).
        pre_repair_threshold = int(
            os.environ.get("RMX_PRE_REPAIR_THRESHOLD", "0") or "0"
        )

        def _owning_root(p: Path) -> Path | None:
            """Return the watch_root that contains `p`, or None. Falls
            back to the first root for events from unexpected sources
            (shouldn't happen — observer only fires on scheduled paths)."""
            for r in self.watch_roots:
                try:
                    if p == r or p.is_relative_to(r):
                        return r
                except (ValueError, OSError):
                    continue
            return self.watch_roots[0] if self.watch_roots else None

        def _flush(paths: list[str]) -> None:
            # Skip entirely if shutdown was requested while debounce window
            # was open. Avoids grabbing _store_lock just to be cancelled.
            if self._shutdown_event.is_set():
                return
            # Group paths by the watch root that owns them so each batch
            # gets the right `project_root` for sync_files' relative-path
            # resolution + curator-queue logic.
            groups: dict[Path, list[str]] = {}
            for raw in paths:
                owner = _owning_root(Path(raw).resolve())
                if owner is None:
                    continue
                groups.setdefault(owner, []).append(raw)
            if not groups:
                return
            # Take the store_lock so the watcher and the socket request
            # handler never touch the shared Store concurrently.
            try:
                with self._store_lock:
                    repaired = False
                    if (pre_repair_threshold > 0
                            and len(paths) >= pre_repair_threshold
                            and self.store._backend.kind == "duckdb"):
                        try:
                            self.store.repair_entity_links_index()
                            repaired = True
                        except Exception as rexc:
                            self._log(f"pre-flush repair failed: {rexc!r}")
                            self._fast_exit_if_invalidated(rexc, "pre-flush repair")
                    total_added = total_updated = total_purged = 0
                    cancelled = False
                    for owner, owner_paths in groups.items():
                        report = sync_files(
                            self.store, owner_paths,
                            project_root=owner,
                            semantic=self.watch_semantic,
                            cancel_check=self._shutdown_event.is_set,
                        )
                        total_added += report["added"]
                        total_updated += report["updated"]
                        total_purged += report["purged"]
                        if report.get("cancelled"):
                            cancelled = True
                queued = _enqueue_curator(paths)
                tail = f" curator+{queued}" if queued else ""
                cancel_tail = " cancelled" if cancelled else ""
                repair_tail = " pre-repaired" if repaired else ""
                roots_tail = (
                    f" roots={len(groups)}" if len(self.watch_roots) > 1 else ""
                )
                self._log(
                    f"watch flush: paths={len(paths)} +{total_added} "
                    f"~{total_updated} -{total_purged}"
                    f"{tail}{cancel_tail}{repair_tail}{roots_tail}"
                )
            except Exception as exc:
                self._log(f"watch flush failed: {exc!r}")
                self._fast_exit_if_invalidated(exc, "watch flush")

        debouncer = Debouncer(self.watch_debounce_ms, _flush)

        class _Handler(FileSystemEventHandler):
            def _maybe(self_inner, raw_path: str) -> None:
                p = Path(raw_path)
                if is_relevant(p):
                    debouncer.add(str(p))

            def on_created(self_inner, event) -> None:
                if not event.is_directory:
                    self_inner._maybe(event.src_path)

            def on_modified(self_inner, event) -> None:
                if not event.is_directory:
                    self_inner._maybe(event.src_path)

            def on_deleted(self_inner, event) -> None:
                if not event.is_directory:
                    self_inner._maybe(event.src_path)

            def on_moved(self_inner, event) -> None:
                if event.is_directory:
                    return
                self_inner._maybe(event.src_path)
                self_inner._maybe(event.dest_path)

        observer = Observer()
        for r in self.watch_roots:
            observer.schedule(_Handler(), str(r), recursive=True)
        observer.start()
        debouncer.start()

        def _runner():
            try:
                while not self._watch_stop.is_set():
                    self._watch_stop.wait(1.0)
            finally:
                debouncer.stop()
                observer.stop()
                observer.join(timeout=2.0)

        self._watch_thread = threading.Thread(
            target=_runner, name="rmxd-watcher", daemon=True,
        )
        self._watch_thread.start()
        roots_repr = (
            str(self.watch_roots[0])
            if len(self.watch_roots) == 1
            else "[" + ", ".join(str(r) for r in self.watch_roots) + "]"
        )
        self._log(
            f"watcher started roots={roots_repr} "
            f"debounce={self.watch_debounce_ms}ms"
        )

    def _handle(self, conn: socket.socket, cli_pool, bg_pool) -> None:
        """Read one request, route it to the right pool, return the response.

        Runs on a dispatcher thread (disp_pool). Classifies the op via
        `CLI_OPS`; sends interactive ops to `cli_pool` and bulk/mutating
        ops to `bg_pool`. The dispatcher thread blocks on the future and
        writes the response, which is why `disp_pool` is sized larger
        than the sum of the two work pools."""
        try:
            conn.settimeout(30.0)
            req_bytes = _recv_line(conn, timeout=30.0)
            if not req_bytes:
                return
            req = json.loads(req_bytes.decode("utf-8"))
            op = req.get("op")
            args = req.get("args") or {}
            handler = OPS.get(op)
            if handler is None:
                resp = {"ok": False, "error": f"unknown op: {op!r}"}
            else:
                target_pool = cli_pool if op in CLI_OPS else bg_pool
                try:
                    fut = target_pool.submit(handler, self, args)
                    result = fut.result()
                    resp = {"ok": True, "result": result}
                except Exception as exc:
                    self._log(f"op {op} raised: {exc!r}")
                    resp = {"ok": False, "error": str(exc)}
                    self._fast_exit_if_invalidated(exc, f"op {op}")
        except Exception as exc:
            resp = {"ok": False, "error": f"protocol error: {exc!r}"}
        try:
            conn.sendall((json.dumps(resp) + "\n").encode("utf-8"))
        except OSError:
            pass


# ---------- op handlers -----------------------------------------------------


def _op_ping(d: Daemon, args: dict) -> dict:
    return {
        "pid": os.getpid(),
        "root": str(d.root),
        "backend": d.store._backend.kind if d.store else None,
    }


def _op_enqueue(d: Daemon, args: dict) -> dict:
    from refmatrix import sync as syncmod
    paths = args.get("paths") or []
    if not paths:
        return {"enqueued": 0}
    syncmod.enqueue(d.root, [str(p) for p in paths])
    return {"enqueued": len(paths)}


def _op_flush_queue(d: Daemon, args: dict) -> dict:
    from refmatrix import sync as syncmod
    proot = Path(args.get("project_root") or Path.cwd()).resolve()
    semantic = bool(args.get("semantic"))
    with d._store_lock:
        report = syncmod.flush_queue(
            d.store, project_root=proot, semantic=semantic,
            cancel_check=d._shutdown_event.is_set,
        )
    return report


def _op_flush_queue_async(d: Daemon, args: dict) -> dict:
    """Fire-and-forget flush: ACK immediately, run the flush on a
    background thread. Coalesces — if a flush is already pending, this
    becomes a no-op so a burst of Edit hooks doesn't spawn N threads."""
    import threading
    from refmatrix import sync as syncmod
    proot = Path(args.get("project_root") or Path.cwd()).resolve()
    semantic = bool(args.get("semantic"))

    with d._async_lock:
        if d._async_flush_pending:
            return {"queued": False, "reason": "flush already pending"}
        d._async_flush_pending = True

    def _runner():
        try:
            with d._store_lock:
                syncmod.flush_queue(
                    d.store, project_root=proot, semantic=semantic,
                    cancel_check=d._shutdown_event.is_set,
                )
        except Exception as exc:
            d._log(f"async flush failed: {exc!r}")
        finally:
            with d._async_lock:
                d._async_flush_pending = False

    t = threading.Thread(target=_runner, name="rmxd-async-flush", daemon=True)
    t.start()
    return {"queued": True}


def _op_sync_files(d: Daemon, args: dict) -> dict:
    from refmatrix import sync as syncmod
    proot = Path(args.get("project_root") or Path.cwd()).resolve()
    files = args.get("files") or []
    semantic = bool(args.get("semantic"))
    with d._store_lock:
        report = syncmod.sync_files(
            d.store, [str(p) for p in files],
            project_root=proot, semantic=semantic,
            cancel_check=d._shutdown_event.is_set,
        )
    return report


def _op_ingest_path(d: Daemon, args: dict) -> dict:
    """Run a full ingest against the daemon-owned store. CLI routes here
    when the daemon is up so the catalog write lock stays single-owner."""
    from refmatrix.ingest import ingest_path
    path = Path(args["path"]).resolve()
    source = args.get("source") or "auto"
    semantic = bool(args.get("semantic"))
    with d._store_lock:
        n = ingest_path(d.store, path, source=source, semantic=semantic)
    return {"entities": n, "path": str(path)}


def _op_ingest_gmd(d: Daemon, args: dict) -> dict:
    """Run GMD ingest against the daemon-owned store. Same rationale as
    `_op_ingest_path`: avoid catalog-lock contention with the watcher.

    Passes a `yield_lock` callback to `ingest_gmd_paths` that releases +
    reacquires `_store_lock` periodically so CLI ops queued behind a
    long ingest get a turn at the lock. Without this, a multi-thousand-
    file ingest blocks every `rmx query`/`rmx stats`/etc. until done.
    """
    from refmatrix.ingest_gmd import collect_gmd_files, ingest_gmd_paths
    targets = [Path(p).resolve() for p in (args.get("targets") or [])]
    verbose = bool(args.get("verbose"))
    files = collect_gmd_files(targets)
    if not files:
        return {"files": 0, "report": "no candidate files found"}
    yield_every = int(os.environ.get("RMX_INGEST_YIELD_EVERY", "1") or "1")
    # 1ms sleep is enough for the OS scheduler to wake a cli waiter blocked
    # on _store_lock — Python's threading.Lock is not strict FIFO and a
    # bare sleep(0) lets the bg thread immediately re-grab. 1ms loses ~1%
    # of bg throughput per yield, negligible against the responsiveness win.
    yield_sleep_s = float(os.environ.get("RMX_INGEST_YIELD_SLEEP_S", "0.001") or "0.001")
    d._store_lock.acquire()
    try:
        def _yield() -> None:
            d._store_lock.release()
            time.sleep(yield_sleep_s)
            d._store_lock.acquire()
        stats = ingest_gmd_paths(
            d.store, files, verbose=verbose,
            yield_lock=_yield, yield_every=yield_every,
        )
    finally:
        d._store_lock.release()
    return {
        "files": len(files), "report": stats.report(),
        "docs": stats.docs, "nodes": stats.nodes,
        "rels": stats.rels, "mentions": stats.mentions,
        "unresolved": len(stats.unresolved),
    }


def _op_sync_since(d: Daemon, args: dict) -> dict:
    """Run `sync_since` through the daemon's long-lived Store. Targets the
    git post-commit hook (`rmx sync --since HEAD~1`), which used to grab
    the catalog write lock outside the daemon and block every other
    flush for the duration of a 100+ file diff."""
    from refmatrix import sync as syncmod
    proot = Path(args.get("project_root") or Path.cwd()).resolve()
    git_ref = args["git_ref"]
    semantic = bool(args.get("semantic"))
    with d._store_lock:
        report = syncmod.sync_since(
            d.store, git_ref, project_root=proot, semantic=semantic,
            cancel_check=d._shutdown_event.is_set,
        )
    return report


def _op_stats(d: Daemon, args: dict) -> dict:
    with d._store_lock:
        return d.store.stats()


def _op_checkpoint(d: Daemon, args: dict) -> dict:
    """DuckDB CHECKPOINT: flush WAL into the main file. Also rebuilds the
    `entity_links` secondary index, which can get out of sync with the
    table after `prune-noise --drop` (DuckDB FATAL during the next
    DELETE — "Failed to delete all rows from index"). Drop+recreate
    self-heals without losing data."""
    if d.store._backend.kind != "duckdb":
        return {"checkpointed": False, "reason": "not a duckdb backend"}
    with d._store_lock:
        con = d.store._connect()._duck
        con.execute("DROP INDEX IF EXISTS idx_entity_links_lk_concept")
        con.execute(
            "CREATE INDEX idx_entity_links_lk_concept "
            "ON entity_links(linkage_id, concept_id)"
        )
        con.execute("CHECKPOINT")
    return {"checkpointed": True, "index_rebuilt": True}


def _op_prune_noise(d: Daemon, args: dict) -> dict:
    namespaces = tuple(args.get("namespaces") or ("keyword",))
    min_df = int(args.get("min_df", 2))
    max_df_ratio = float(args.get("max_df_ratio", 0.25))
    drop = bool(args.get("drop", False))
    with d._store_lock:
        return d.store.prune_noise(
            namespaces=namespaces, min_df=min_df,
            max_df_ratio=max_df_ratio, drop=drop,
        )


def _op_vacuum(d: Daemon, args: dict) -> dict:
    with d._store_lock:
        return d.store.vacuum()


def _op_upsert_entity(d: Daemon, args: dict) -> dict:
    import json as _json
    meta = args.get("meta")
    if isinstance(meta, str):
        meta = _json.loads(meta)
    with d._store_lock:
        eid = d.store.upsert_entity(
            kind=args["kind"], name=args["name"],
            path=args.get("path"), tldr=args.get("tldr"),
            meta=meta, protected=bool(args.get("protected", True)),
        )
    return {"id": eid}


def _op_add_concept(d: Daemon, args: dict) -> dict:
    with d._store_lock:
        cid = d.store.add_concept(
            args["name"],
            description=args.get("description"),
            protected=bool(args.get("protected", True)),
        )
    return {"id": cid}


def _op_add_linkage_type(d: Daemon, args: dict) -> dict:
    with d._store_lock:
        lid = d.store.add_linkage_type(
            name=args["name"],
            directed=bool(args.get("directed", True)),
            description=args.get("description"),
        )
    return {"id": lid}


def _op_iter_entities(d: Daemon, args: dict) -> dict:
    kind = args.get("kind")
    with d._store_lock:
        rows = [
            {"id": e.id, "kind": e.kind, "name": e.name,
             "path": e.path, "tldr": e.tldr}
            for e in d.store.iter_entities(kind)
        ]
    return {"rows": rows}


def _op_list_linkages(d: Daemon, args: dict) -> dict:
    with d._store_lock:
        return {"rows": d.store.list_linkages()}


def _op_list_saved_queries(d: Daemon, args: dict) -> dict:
    with d._store_lock:
        return {"rows": list(d.store.list_saved_queries())}


def _op_grep_indexed(d: Daemon, args: dict) -> dict:
    """Index-backed grep: find concepts whose name matches PATTERN (LIKE
    or REGEXP) and return their `linkage_evidence` rows. The CLI may
    follow up with a real `rg` fallback when this returns zero.
    """
    pattern = args["pattern"]
    is_regex = bool(args.get("regex", False))
    linkage_filter = args.get("linkage")
    kind_filter = args.get("kind")  # 'doc' | 'code' | None
    limit = int(args.get("limit", 100))

    if is_regex:
        concept_pred = "regexp_matches(c.name, ?)"
        concept_args = [pattern]
    else:
        # Treat bare pattern as case-insensitive substring; users who want
        # exact match can pass an exact name (LIKE % wrapping still matches).
        concept_pred = "c.name ILIKE ?"
        concept_args = [f"%{pattern}%"]

    where_extra = []
    extra_args: list = []
    if linkage_filter:
        where_extra.append("lt.name = ?")
        extra_args.append(linkage_filter)
    if kind_filter:
        where_extra.append("e.kind = ?")
        extra_args.append(kind_filter)

    extra_sql = (" AND " + " AND ".join(where_extra)) if where_extra else ""

    sql = (
        "SELECT e.path AS path, e.name AS entity_name, ev.line AS line, "
        "       lt.name AS linkage, c.name AS concept_name "
        "FROM linkage_evidence ev "
        "JOIN entities e ON e.id = ev.entity_id "
        "JOIN entities c ON c.id = ev.concept_id "
        "JOIN linkage_types lt ON lt.id = ev.linkage_id "
        f"WHERE {concept_pred}{extra_sql} "
        "ORDER BY e.path, ev.line "
        "LIMIT ?"
    )
    with d._store_lock:
        rows = d.store._connect()._duck.execute(
            sql, concept_args + extra_args + [limit],
        ).fetchall()
    return {
        "rows": [
            {
                "path": r[0], "entity": r[1], "line": r[2],
                "linkage": r[3], "concept": r[4],
            }
            for r in rows
        ],
    }


def _op_learn_from_grep(d: Daemon, args: dict) -> dict:
    """Promote rg fallback hits into the index. A search miss + a grep hit
    is a strong signal that PATTERN is something the user cares about;
    fold the hits into a `query/PATTERN` namespaced concept with one
    `mentions` linkage per matched file and `linkage_evidence` carrying
    the line. Future `rmx grep`/`context` calls hit the index.
    """
    pattern = args["pattern"]
    hits = args.get("hits") or []  # [{file, line}]
    project_root = Path(args.get("project_root") or Path.cwd()).resolve()
    if not pattern or not hits:
        return {"added": 0}

    name = f"query/{pattern}"
    with d._store_lock, d.store.transaction(), d.store.deferred_links():
        cid = d.store.add_concept(
            name, description=f"learned from grep query {pattern!r}",
            protected=False,
        )
        # Group hits by file so we add one entity + one link per file,
        # then evidence rows per line.
        per_file: dict[str, list[int]] = {}
        for h in hits:
            f = h.get("file")
            ln = h.get("line")
            if not f:
                continue
            per_file.setdefault(f, []).append(ln if ln is not None else 0)

        added = 0
        for abs_path, lines in per_file.items():
            ap = Path(abs_path)
            try:
                rel = ap.relative_to(project_root).as_posix()
            except ValueError:
                rel = str(ap)
            kind = "code" if ap.suffix.lower() in {
                ".py", ".js", ".ts", ".go", ".rs", ".java", ".rb", ".php",
                ".cpp", ".c", ".h", ".hpp", ".pseudo",
            } else "doc"
            eid = d.store.upsert_entity(
                kind=kind, name=rel, path=str(ap),
            )
            d.store.link("mentions", cid, eid)
            for line in lines:
                d.store.add_evidence(
                    "mentions", cid, eid, file=rel, line=line,
                    detail=f"learned from grep {pattern!r}",
                )
            added += 1
    return {"added": added, "concept": name, "concept_id": cid}


def _op_query(d: Daemon, args: dict) -> dict:
    """Run a DSL or PQL expression and return result ids + names rendered
    as text or json. Routes through the daemon so reads work while the
    daemon holds the catalog write lock."""
    from refmatrix.query import QueryEngine
    expr = args["expr"]
    is_pql = bool(args.get("pql", False))
    include_noise = bool(args.get("include_noise", False))
    strict = bool(args.get("strict", False))
    limit = int(args.get("limit", 50))
    name_filter = args.get("name_filter")
    explain = bool(args.get("explain", False))
    with d._store_lock:
        qe = QueryEngine(d.store, include_noise=include_noise, strict=strict)
        result = qe.run_pql(expr) if is_pql else qe.run(expr)
        if name_filter:
            from pyroaring import BitMap
            matching = BitMap(
                r[0] for r in d.store._connect().execute(
                    "SELECT id FROM entities WHERE name LIKE ?", (name_filter,)
                )
            )
            if isinstance(result, list):
                result = [(eid, w) for eid, w in result if eid in matching]
            elif hasattr(result, "__iter__") and not isinstance(result, int):
                result = result & matching

        if isinstance(result, int):
            return {"shape": "int", "value": result}
        if isinstance(result, list):
            rows = []
            for eid, w in result[:limit]:
                e = d.store.get_entity_by_id(eid)
                rows.append({
                    "id": eid,
                    "weight": w,
                    "name": e.name if e else None,
                    "kind": e.kind if e else None,
                    "path": e.path if e else None,
                })
            return {"shape": "weighted", "rows": rows, "cardinality": len(result)}

        ids = list(result)
        rows = []
        for eid in ids[:limit]:
            e = d.store.get_entity_by_id(eid)
            rows.append({
                "id": eid,
                "name": e.name if e else None,
                "kind": e.kind if e else None,
                "path": e.path if e else None,
            })
        out = {"shape": "bitmap", "rows": rows, "cardinality": len(ids)}
        if explain:
            evidence = {}
            for eid in ids[:limit]:
                ev_rows = d.store._connect().execute(
                    """
                    SELECT lt.name AS linkage, c.name AS concept_name,
                           ev.file, ev.line
                    FROM linkage_evidence ev
                    JOIN linkage_types lt ON lt.id = ev.linkage_id
                    JOIN entities c ON c.id = ev.concept_id
                    WHERE ev.entity_id = ?
                    """,
                    (eid,),
                ).fetchall()
                evidence[str(eid)] = [
                    {"linkage": r["linkage"], "concept": r["concept_name"],
                     "file": r["file"], "line": r["line"]}
                    for r in ev_rows
                ]
            out["evidence"] = evidence
        return out


def _op_context(d: Daemon, args: dict) -> dict:
    """Build a context bundle and return its rendered form. Read-side
    operations have to route through the daemon too because DuckDB blocks
    cross-process reads while another process holds the write lock."""
    from refmatrix.context import build_context, render_json, render_text
    ref = args["ref"]
    fmt = args.get("format", "text")
    linkages = args.get("linkages") or None
    max_entities = int(args.get("max_entities", 20))
    max_tokens = int(args.get("max_tokens", 4000))
    fuse = bool(args.get("fuse", False))
    strict = bool(args.get("strict", False))
    with d._store_lock:
        bundle = build_context(
            d.store, ref,
            linkages=linkages,
            max_entities=max_entities,
            max_tokens=max_tokens,
            fuse=fuse,
            strict=strict,
        )
    body = render_json(bundle) if fmt == "json" else render_text(bundle)
    return {"body": body}


def _memory_partition(d: "Daemon", args: dict) -> str:
    """Resolve which partition this memory op targets. Caller passes
    `partition` explicitly; absent, we fall back to the daemon's bound
    partition. The daemon binds for code-sync writes; memory ops
    normally land in `intuition` via explicit pass-through from the
    CLI, but we honor whatever the caller asked for."""
    return args.get("partition") or d.store._partition_name


def _op_memory_add(d: Daemon, args: dict) -> dict:
    """Upsert a memory entity + its sidecar content. ADR-0001 Phase B."""
    name = args["name"]
    content = args["content"]
    mtype = args.get("mtype") or "observation"
    tags = args.get("tags")
    metadata = args.get("metadata")
    protected = bool(args.get("protected", False))
    with d._store_lock, d.store.with_partition(_memory_partition(d, args)):
        eid = d.store.add_memory(
            name=name, content=content, mtype=mtype,
            tags=tags, metadata=metadata, protected=protected,
        )
    return {"id": eid}


def _op_memory_get(d: Daemon, args: dict) -> dict:
    """Fetch a memory by name (active partition) or id (any partition)."""
    target = args.get("name") if args.get("name") is not None else args.get("id")
    if target is None:
        raise ValueError("memory_get requires 'name' or 'id'")
    with d.store.with_partition(_memory_partition(d, args)):
        m = d.store.get_memory(target)
    return {"memory": m}


def _op_memory_iter(d: Daemon, args: dict) -> dict:
    """Stream memories in the active partition. Optional mtype filter."""
    mtype = args.get("mtype")
    limit = args.get("limit")
    with d.store.with_partition(_memory_partition(d, args)):
        rows = list(d.store.iter_memories(mtype=mtype, limit=limit))
    return {"rows": rows}


def _op_memory_search(d: Daemon, args: dict) -> dict:
    """Substring search over memory name + content. Returns at most
    `limit` rows newest-first."""
    query = args["query"]
    limit = int(args.get("limit", 20))
    with d.store.with_partition(_memory_partition(d, args)):
        rows = d.store.search_memories(query, limit=limit)
    return {"rows": rows}


def _op_memory_recent(d: Daemon, args: dict) -> dict:
    """Phase C2: most recent memories within an optional `since_seconds`
    window, newest first. Routed through the daemon so the in-process
    Store can't deadlock against the daemon's DuckDB write lock."""
    since = args.get("since_seconds")
    limit = int(args.get("limit", 20))
    with d.store.with_partition(_memory_partition(d, args)):
        rows = d.store.recent_memories(since_seconds=since, limit=limit)
    return {"rows": rows}


def _op_memory_forget(d: Daemon, args: dict) -> dict:
    """Delete a memory entity, its sidecar, and every entity_link it owns."""
    target = args.get("name") if args.get("name") is not None else args.get("id")
    if target is None:
        raise ValueError("memory_forget requires 'name' or 'id'")
    with d._store_lock, d.store.with_partition(_memory_partition(d, args)):
        ok = d.store.forget_memory(target)
    return {"forgotten": ok}


def _op_memory_score(d: Daemon, args: dict) -> dict:
    """Phase B5: per-concept reinforcement signal. Returns the signed
    score (clamped to ±cap) plus the contributing concept_ids so the
    caller can render --explain."""
    name = args["concept"]
    halflife = args.get("halflife_days")
    cap = args.get("cap")
    explain = bool(args.get("explain", False))
    with d.store.with_partition(_memory_partition(d, args)):
        cids = d.store.resolve_concept_ids(name, strict=False)
        if not cids:
            return {"concept": name, "concept_ids": [], "signal": 0.0,
                    "components": []}
        scores = d.store.reinforcement_scores(
            cids, halflife_days=halflife, cap=cap,
        )
        components: list[dict] = []
        if explain:
            for cid in cids:
                components.extend({
                    "concept_id": cid,
                    **row,
                } for row in d.store.reinforcement_components(
                    cid, halflife_days=halflife,
                ))
    return {
        "concept": name,
        "concept_ids": cids,
        "scores": scores,
        "signal": sum(scores.values()),
        "components": components,
    }


def _op_memory_link(d: Daemon, args: dict) -> dict:
    """Create a reinforces/contradicts/recalls/informs (or arbitrary
    DEFAULT_LINKAGES) edge from a memory entity to a concept entity.
    Auto-creates the concept by name if not already present so the
    typical add-memory + link flow stays single-step."""
    src = args.get("src_name") if args.get("src_name") is not None else args.get("src_id")
    if src is None:
        raise ValueError("memory_link requires 'src_name' or 'src_id'")
    linkage = args["linkage"]
    concept_name = args["concept"]
    weight = args.get("weight")
    with d._store_lock, d.store.with_partition(_memory_partition(d, args)):
        m = d.store.get_memory(src)
        if m is None:
            raise ValueError(f"no memory matching {src!r}")
        cid = d.store.add_concept(concept_name)
        d.store.link(linkage, cid, m["id"], weight=weight)
    return {"src_id": m["id"], "concept_id": cid}


def _op_stop(d: Daemon, args: dict) -> dict:
    d._stop = True
    return {"stopping": True}


def _op_replica_refresh(d: Daemon, args: dict) -> dict:
    """Force an immediate snapshot of primary → replica .duckdb file."""
    return d._refresh_replica_now()


def _op_replica_status(d: Daemon, args: dict) -> dict:
    """Report rotation state: writer + reader slots, file paths + sizes,
    last-refresh timestamp + latency, refresh-thread liveness."""
    enabled = d.store is not None and d.store._backend.kind == "duckdb"
    active = getattr(d, "_active_slot", None) or d._read_active_slot()
    inactive = "B" if active == "A" else "A"
    a_path = d._replica_file("A")
    b_path = d._replica_file("B")
    return {
        "enabled": enabled,
        "writer_slot": active,
        "reader_slot": inactive,
        "writer_path": str(d._replica_file(active)),
        "reader_path": str(d._replica_file(inactive)),
        "a_size": a_path.stat().st_size if a_path.exists() else 0,
        "b_size": b_path.stat().st_size if b_path.exists() else 0,
        "a_exists": a_path.exists(),
        "b_exists": b_path.exists(),
        "refresh_thread": (
            getattr(d, "_replica_thread", None) is not None
            and d._replica_thread.is_alive()
        ),
        "last": d._replica_last,
    }


def _op_embed(d: Daemon, args: dict) -> dict:
    """Run a batch embedding pass. Walks `Store.pending_embeddings` for
    the given kinds (or all if None), extracts text per kind, embeds in
    a single sentence-transformers call, upserts vectors via Lance, and
    stamps `entities.vectors_updated_at` for the touched rows.

    Args:
        kinds: optional list of entity kinds to embed.
            Default: ["code", "doc", "concept", "memory"].
        limit: cap rows per call so the daemon stays responsive
            (default 256). Caller iterates if more pending.
        rebuild: if True, ignore the `vectors_updated_at` filter and
            re-embed every row of the selected kinds.

    Routes through bg_pool (CPU-heavy under the model). Honors
    cooperative shutdown via `d._shutdown_event`."""
    try:
        emb = d._embedder()
    except ImportError as exc:
        return {"ok": False, "error": f"dense extra not installed: {exc}"}
    from refmatrix import embedder as embmod

    kinds = args.get("kinds") or ["code", "doc", "concept", "memory"]
    limit = int(args.get("limit") or 256)
    rebuild = bool(args.get("rebuild"))

    with d._store_lock:
        if rebuild:
            # `pending_embeddings` already skips current rows; for a
            # rebuild we ask the catalog directly so the WHERE clause
            # matches every row of the selected kinds.
            con = d.store._connect()
            in_list = ",".join("?" * len(kinds))
            rows = con.execute(
                f"SELECT id, kind, name FROM entities "
                f"WHERE partition_id = ? AND kind IN ({in_list}) "
                f"ORDER BY id LIMIT ?",
                [d.store._partition_id, *kinds, limit],
            ).fetchall()
            rows = [(r[0], r[1], r[2]) for r in rows]
        else:
            rows = d.store.pending_embeddings(kinds=kinds, limit=limit)

        if not rows:
            return {"embedded": 0, "remaining": 0, "kinds": kinds}

        # Per-kind grouping so we upsert into the right Lance dataset.
        triples = embmod.extract_batch(d.store, rows)
        if not triples:
            return {"embedded": 0, "remaining": 0, "skipped_empty": len(rows)}

        # Single batch encode keeps the model warm + amortizes the
        # tokenizer cost. ST handles batching internally.
        if d._shutdown_event.is_set():
            return {"embedded": 0, "remaining": len(rows), "cancelled": True}
        vectors = emb.embed_texts([t for (_eid, _k, t) in triples])

        embedded = 0
        by_kind: dict[str, list[int]] = {}
        for (eid, kind, _t), idx in zip(triples, range(len(triples))):
            by_kind.setdefault(kind, []).append(idx)
        for kind, idxs in by_kind.items():
            eids = [triples[i][0] for i in idxs]
            sub = vectors[idxs]
            d.store.upsert_vector(eids, sub, kind=kind, dim=emb.dim)
            embedded += len(eids)

    # Remaining pending after this batch — caller can loop until 0.
    remaining = len(d.store.pending_embeddings(kinds=kinds, limit=1))
    return {
        "embedded": embedded,
        "remaining": remaining,
        "kinds": kinds,
        "dim": emb.dim,
        "model": emb.model_name,
    }


def _op_ann_search(d: Daemon, args: dict) -> dict:
    """Dense ANN search via Lance. Accepts either a precomputed
    `vector` (list of floats) or a `query` string that gets embedded
    server-side. Returns `[{id, distance}, ...]` ascending by L2.

    Args:
        query: text to embed and search by.
        vector: alternative — caller supplies the vector directly.
        k: top-k (default 20).
        kinds: optional filter (default: all kinds in the partition).
        partition: override the daemon Store's bound partition for
            this read. Memory recall sets partition='intuition' so a
            daemon bound to 'local' can still serve hybrid memory
            queries. Lance datasets live at
            `<root>/vectors/<partition>/<kind>.lance` so the read
            crosses partition without touching the bound store.
    """
    try:
        emb = d._embedder()
    except ImportError as exc:
        return {"ok": False, "error": f"dense extra not installed: {exc}"}

    k = int(args.get("k") or 20)
    kinds = args.get("kinds")
    query = args.get("query")
    vector = args.get("vector")
    partition = args.get("partition")

    if vector is None and not query:
        return {"ok": False, "error": "need 'query' text or 'vector' list"}

    if vector is None:
        v = emb.embed_texts([query])[0]
    else:
        import numpy as np
        v = np.asarray(vector, dtype="float32")
        if v.shape[0] != emb.dim:
            return {
                "ok": False,
                "error": f"vector dim {v.shape[0]} != model dim {emb.dim}",
            }

    with d._store_lock:
        hits = d.store.ann_search(
            v, k=k, dim=emb.dim, kinds=kinds, partition=partition,
        )
    return {"hits": [{"id": eid, "distance": dist} for eid, dist in hits]}


OPS: dict[str, Callable[[Daemon, dict], Any]] = {
    "ping": _op_ping,
    "enqueue": _op_enqueue,
    "flush_queue": _op_flush_queue,
    "flush_queue_async": _op_flush_queue_async,
    "sync_files": _op_sync_files,
    "sync_since": _op_sync_since,
    "ingest_path": _op_ingest_path,
    "ingest_gmd": _op_ingest_gmd,
    "context": _op_context,
    "query": _op_query,
    "grep_indexed": _op_grep_indexed,
    "learn_from_grep": _op_learn_from_grep,
    "upsert_entity": _op_upsert_entity,
    "add_concept": _op_add_concept,
    "add_linkage_type": _op_add_linkage_type,
    "iter_entities": _op_iter_entities,
    "list_linkages": _op_list_linkages,
    "list_saved_queries": _op_list_saved_queries,
    "prune_noise": _op_prune_noise,
    "vacuum": _op_vacuum,
    "stats": _op_stats,
    "checkpoint": _op_checkpoint,
    "replica_refresh": _op_replica_refresh,
    "replica_status": _op_replica_status,
    "embed": _op_embed,
    "ann_search": _op_ann_search,
    "memory_add": _op_memory_add,
    "memory_get": _op_memory_get,
    "memory_iter": _op_memory_iter,
    "memory_search": _op_memory_search,
    "memory_recent": _op_memory_recent,
    "memory_forget": _op_memory_forget,
    "memory_link": _op_memory_link,
    "memory_score": _op_memory_score,
    "stop": _op_stop,
}

# Ops dispatched to the small `cli_pool` — latency-sensitive, mostly
# reads, expected to complete in milliseconds-to-low-seconds. Everything
# else (ingest, sync, prune, vacuum, checkpoint, large list ops, learn-
# on-miss writebacks) goes to `bg_pool`. `stop` is cli because we want
# it to take effect immediately even while bg work is in flight.
CLI_OPS: set[str] = {
    "ping",
    "stats",
    "context",
    "query",
    "grep_indexed",
    "list_linkages",
    "list_saved_queries",
    "replica_refresh",
    "replica_status",
    "ann_search",
    "memory_get",
    "memory_iter",
    "memory_search",
    "memory_recent",
    "memory_score",
    "stop",
}


# ---------- daemonize -------------------------------------------------------


def spawn_daemon(root: Path, *, partition: str | None = None,
                 wait_for_ready: float = 5.0,
                 watch_root: "Path | list[Path] | None" = None,
                 watch_debounce_ms: int = 500,
                 watch_semantic: bool = False) -> int:
    """Fork a background daemon for `root` and return when it's accepting
    connections. Idempotent: if a daemon is already running for `root`,
    returns its PID immediately. Safe under concurrent calls — uses an
    exclusive `daemon.lock` flock so only one fork wins; the loser polls
    until the winner is healthy.

    `watch_root` accepts either a single Path or a list of Paths. With
    multiple paths, the daemon schedules one observer per root and
    groups path events back to their owning root for sync_files.
    """
    import fcntl
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)

    # Fast path before locking. Trust ping(): a healthy socket means a
    # daemon is up even if `rmxd.pid` is missing or stale (an orphaned
    # daemon whose pid file was overwritten by a losing concurrent
    # spawn — see the bind-race below).
    if ping(root):
        existing = read_pid(root)
        if existing is not None:
            return existing

    lock_path = root / "daemon.lock"
    lockf = lock_path.open("w")
    try:
        # Block on the lock — multiple Claude SessionStart hooks may fire
        # at once. The first one starts the daemon (and holds the lock
        # through fork + readiness wait); the rest wait here briefly,
        # then re-check and return the now-running pid.
        fcntl.flock(lockf.fileno(), fcntl.LOCK_EX)

        # Re-check under the lock. Use ping() as the authoritative signal:
        # the previous daemon's serve_forever() unlinks any prior socket
        # file before binding (so a losing concurrent spawn would have
        # stomped the original socket path with a now-dead bind). If ping
        # answers, *someone* is alive on the socket; treat it as the
        # daemon and don't start another that would just re-race.
        if ping(root):
            existing = read_pid(root)
            if existing is not None:
                return existing
            # ping ok but pid file gone — orphaned-but-functional daemon.
            # Return its pid via the ping reply.
            try:
                resp = call(root, "ping", timeout=0.5)
                pid = (resp.get("result") or {}).get("pid")
                if isinstance(pid, int):
                    return pid
            except Exception:
                pass
            # Couldn't get a pid, but it's serving — caller doesn't strictly
            # need one. Return -1 as a sentinel.
            return -1

        # Two-stage fork so the daemon becomes session leader, untied from
        # the parent shell. Standard double-fork incantation. The child
        # closes the lockfile fd before serving so the parent's flock is
        # the only thing keeping siblings out.
        pid = os.fork()
        if pid > 0:
            # Parent: wait for socket to come up, then release lock.
            deadline = time.time() + wait_for_ready
            while time.time() < deadline:
                if ping(root):
                    return read_pid(root) or pid
                time.sleep(0.05)
            raise RuntimeError(
                f"daemon did not start within {wait_for_ready:.1f}s "
                f"(see {root / LOG_NAME})"
            )

        # Child 1
        os.setsid()
        pid = os.fork()
        if pid > 0:
            os._exit(0)

        # Child 2 — the actual daemon. Detach FDs. stdin -> /dev/null;
        # stdout/stderr -> rmxd.stderr so DuckDB's abort message
        # (printed to std::cerr right before std::terminate -> SIGABRT)
        # is captured. Append, not truncate, so a tight crash loop
        # leaves a full record. Falls back to /dev/null if the open
        # fails (e.g. permission, full disk) so we never block startup.
        lockf.close()
        devnull = os.open(os.devnull, os.O_RDWR)
        os.dup2(devnull, 0)
        try:
            err_fd = os.open(
                str(root / "rmxd.stderr"),
                os.O_WRONLY | os.O_CREAT | os.O_APPEND,
                0o600,
            )
            os.dup2(err_fd, 1)
            os.dup2(err_fd, 2)
            os.close(err_fd)
        except OSError:
            os.dup2(devnull, 1)
            os.dup2(devnull, 2)
        os.close(devnull)
        try:
            Daemon(
                root, partition=partition,
                watch_root=watch_root,
                watch_debounce_ms=watch_debounce_ms,
                watch_semantic=watch_semantic,
            ).serve_forever()
        finally:
            os._exit(0)
    finally:
        # Parent path only — child2 already _exit'd.
        try:
            lockf.close()
        except Exception:
            pass


def stop_daemon(root: Path, *, timeout: float = 5.0) -> bool:
    """Send a stop op, then wait for the pid to exit. Returns True if the
    daemon stopped within the timeout (or if no daemon was running)."""
    # Use ping as the readiness signal — pidfile can be stale (orphaned
    # daemon survived a losing concurrent spawn that overwrote it).
    pid = read_pid(root)
    socket_alive = ping(root, timeout=0.5)
    if pid is None and not socket_alive:
        return True

    # If ping works, ask the daemon to stop via its protocol so it can
    # cleanly join its watcher thread and unlink its socket.
    try:
        if socket_alive:
            call(root, "stop", timeout=2.0)
    except Exception:
        pass

    # Discover the real pid if pidfile was stale: ping result carries it.
    if pid is None and socket_alive:
        try:
            resp = call(root, "ping", timeout=0.5)
            pid_candidate = (resp.get("result") or {}).get("pid")
            if isinstance(pid_candidate, int):
                pid = pid_candidate
        except Exception:
            pass

    deadline = time.time() + timeout
    while time.time() < deadline:
        if pid is None or not is_alive(pid):
            return True
        if not ping(root, timeout=0.2) and not socket_path(root).exists():
            return True
        time.sleep(0.05)

    # Timed out — SIGTERM the pid we have (if any) for one last try.
    if pid is not None:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            return True
        deadline2 = time.time() + 2.0
        while time.time() < deadline2:
            if not is_alive(pid):
                return True
            time.sleep(0.05)
        # Final escalation: SIGKILL. A daemon that's ignored protocol-stop
        # + SIGTERM is wedged (worker leaked in a C-extension call, etc.);
        # leaving it alive holds the writer-slot DuckDB file lock and
        # stops the next spawn from refreshing the replica. SIGKILL is
        # safe under 0.3.1+ durability (WAL + fragment flush) and was
        # already the documented escape hatch for this case.
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            return True
        deadline3 = time.time() + 1.0
        while time.time() < deadline3:
            if not is_alive(pid):
                return True
            time.sleep(0.05)
    return False


def serve_foreground(root: Path, *, partition: str | None = None,
                     watch_root: "Path | list[Path] | None" = None,
                     watch_debounce_ms: int = 500,
                     watch_semantic: bool = False) -> int:
    """Run the daemon in the foreground (no fork). Used by supervisors
    like launchd / systemd that own the process lifecycle and need the
    daemon process to stay attached to them. Returns 0 on clean exit.

    Stdout/stderr are NOT redirected — the supervisor handles that
    (`StandardOutPath` / `StandardErrorPath` in the plist).

    `watch_root` accepts either a single Path or a list of Paths.
    """
    import fcntl
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)

    if ping(root):
        raise RuntimeError(
            f"daemon already running for {root}; stop it before "
            f"launching under a supervisor (`rmx daemon stop`)"
        )

    lock_path = root / "daemon.lock"
    lockf = lock_path.open("w")
    try:
        fcntl.flock(lockf.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as e:
        lockf.close()
        raise RuntimeError(
            f"another daemon spawn holds {lock_path}; refusing to start"
        ) from e

    try:
        Daemon(
            root, partition=partition,
            watch_root=watch_root,
            watch_debounce_ms=watch_debounce_ms,
            watch_semantic=watch_semantic,
        ).serve_forever()
    finally:
        try:
            lockf.close()
        except Exception:
            pass
    return 0
