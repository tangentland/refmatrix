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
import threading
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any, Callable

from refmatrix.store import Store
from refmatrix.subproc import subproc_embed_enabled


SOCKET_NAME = "rmxd.sock"
PID_NAME = "rmxd.pid"
LOG_NAME = "rmxd.log"
# Written by a READ surface that hit DuckDB index drift (plan-4 task 4.1):
# `{table, op, at}`. Boot repairs the named table before serving and clears
# it; `rmx daemon status` shows `repair pending: <table>` while it exists.
REPAIR_MARKER_NAME = "repair.needed"


def repair_marker_path(root: Path) -> Path:
    return Path(root) / REPAIR_MARKER_NAME


# Liveness the SUPERVISOR can read without a socket round-trip (plan-4 task
# 4.3): a file the daemon touches from a thread that holds no locks. A ping
# that must pass the accept loop is exactly what stalls when the daemon is
# busy; the heartbeat keeps ticking through an ingest, an index rebuild or a
# model-worker reconnect, so "busy" and "dead" are distinguishable.
# How long a supervised start waits for an unsupervised predecessor to stop
# gracefully before serve_forever's reap escalates (plan-4 task 4.4).
ADOPT_GRACE_S = float(os.environ.get("RMX_ADOPT_GRACE_S", "20") or "20")
HEARTBEAT_NAME = "heartbeat"
HEARTBEAT_INTERVAL_S = float(os.environ.get("RMX_HEARTBEAT_S", "5") or "5")


def heartbeat_path(root: Path) -> Path:
    return Path(root) / HEARTBEAT_NAME


def heartbeat_age(root: Path) -> float:
    """Seconds since the daemon last touched its heartbeat; `inf` when there
    is none (pre-0.69 daemon, or never started)."""
    try:
        return max(0.0, time.time() - heartbeat_path(root).stat().st_mtime)
    except OSError:
        return float("inf")


def read_repair_marker(root: Path) -> "dict | None":
    p = repair_marker_path(root)
    if not p.exists():
        return None
    try:
        body = json.loads(p.read_text() or "{}")
        return body if isinstance(body, dict) else {"table": str(body)}
    except (OSError, ValueError):
        return {"table": "unknown"}


class _FairLock:
    """Strict-FIFO mutex with the same surface as `threading.Lock`.

    Python's `threading.Lock` is not FIFO: when `release()` happens, any
    blocked waiter MAY win, but a thread that re-calls `acquire()`
    immediately after releasing often wins the next lock cycle because
    it's still hot on the same CPU and the OS hasn't yet woken the
    blocked waiter. The `_op_ingest_gmd` yield (`release() + sleep(1ms)
    + acquire()`) hits this directly — the ingest thread re-grabs the
    lock most cycles and CLI ops queue for the whole ingest.

    This lock hands ownership EXPLICITLY to the next queued waiter on
    release, so a yield always lets a waiter in if one is present.

    Surface compatible with `threading.Lock`:
      - `acquire(blocking=True, timeout=None) -> bool`
      - `release()`
      - context-manager (`with lock: ...`)
      - `locked() -> bool`
    """

    def __init__(self) -> None:
        self._mu = threading.Lock()
        self._held = False
        self._waiters: deque[threading.Event] = deque()

    def acquire(self, blocking: bool = True, timeout: float | None = None) -> bool:
        with self._mu:
            if not self._held and not self._waiters:
                self._held = True
                return True
            if not blocking:
                return False
            ev = threading.Event()
            self._waiters.append(ev)
        # Wait OUTSIDE the meta-mutex so release() can hand us the lock.
        # Use a finite poll if timeout is None to avoid lost-wake hangs;
        # threading.Event.wait(None) is well-defined but we want the
        # withdraw path on timeout below.
        woken = ev.wait(timeout)
        if woken:
            # release() popped us off and handed us ownership (`_held`
            # is already True). Done.
            return True
        # Timeout. Try to withdraw our ticket.
        with self._mu:
            try:
                self._waiters.remove(ev)
                return False
            except ValueError:
                # Race: release() handed ownership to us between the
                # timeout firing and re-acquiring `_mu`. We hold the
                # lock now. Pass it on to the next waiter (or release
                # outright) and report timeout to the caller.
                self._pass_or_release_locked()
                return False

    def release(self) -> None:
        with self._mu:
            if not self._held:
                raise RuntimeError("_FairLock released when unlocked")
            self._pass_or_release_locked()

    def _pass_or_release_locked(self) -> None:
        """Called with `_mu` held. Hands lock to next waiter or marks
        free."""
        if self._waiters:
            ev = self._waiters.popleft()
            # `_held` stays True — ownership transferred.
            ev.set()
        else:
            self._held = False

    def locked(self) -> bool:
        with self._mu:
            return self._held

    def __enter__(self) -> "_FairLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


class _MemMirror:
    """In-memory DuckDB mirror of the on-disk snapshot.

    Goal: serve daemon read ops from an uncompressed in-memory copy of
    the catalog so reads cost ~1ms (memory cursor) instead of ~10ms
    (open snapshot file + connect). Refreshes after every snapshot tick
    so the mirror lags the writer by at most one debounce window
    (`RMX_SNAPSHOT_DEBOUNCE_MS`, default 250ms).

    State machine:
      * `ready=False, store=None` — daemon just booted, no refresh yet.
      * `ready=True, store=<Store>` — mirror loaded; `borrow()` returns
        a Store usable for reads.
      * `ready=False, store=<old Store>` — refresh in flight; callers
        fall back to the on-disk snapshot Store via `_open_read_store`.

    Concurrency model: a single in-memory DuckDB connection serves all
    reads. DuckDB connections aren't thread-safe for concurrent
    cursors, so `borrow()` returns a context manager that holds
    `_use_lock` for the duration of one query. Reads are fast (no I/O)
    so the lock window is small; if it becomes a bottleneck, switch to
    one in-memory connection per thread (DuckDB `:memory:dbname`
    pattern with one master + per-thread duplicates).

    Memory cost: ~equal to snapshot file size. 64MB for a small project
    catalog, ~150MB for viascope-scale. Disable via `RMX_MEM_MIRROR=0`
    when running on memory-constrained hosts.
    """

    def __init__(self, daemon: "Daemon") -> None:
        self._daemon = daemon
        self._store: "Store | None" = None
        self._ready = False
        self._use_lock = threading.Lock()  # one reader at a time
        self._refresh_lock = threading.Lock()  # serialize refreshes
        self._last_refresh_ts: float = 0.0
        self._refresh_count = 0
        self._last_error: str | None = None

    @property
    def ready(self) -> bool:
        return self._ready

    def borrow(self) -> "Store | None":
        """Return the in-memory Store if ready, else None. Caller must
        NOT hold the returned Store across blocking ops — reads must
        complete quickly so `_use_lock` doesn't gate everyone.
        """
        if not self._ready:
            return None
        return self._store

    def acquire_use(self) -> threading.Lock:
        """Returns the cursor-use lock. `with mem_mirror.acquire_use():`
        gates concurrent cursors against the shared in-memory
        connection."""
        return self._use_lock

    def refresh(self) -> bool:
        """Rebuild the in-memory mirror from the current snapshot file.

        Closes any old in-memory Store, opens a fresh one against
        `:memory:`, ATTACHes the snapshot file, copies every catalog
        table over, then DETACHes. The new Store is swapped in
        atomically under `_refresh_lock`. Returns False if the
        snapshot file is missing (cold start) or the load fails;
        callers fall back to the on-disk path.

        Cheap to call: ~100-300ms for a viascope-scale catalog. The
        snapshot tick triggers this debounced by
        RMX_SNAPSHOT_DEBOUNCE_MS so a burst of writes pays one refresh.
        """
        snap = self._daemon._snapshot_file()
        if not snap.exists():
            return False
        with self._refresh_lock:
            try:
                new_store = self._load_from_snapshot(snap)
            except Exception as exc:
                self._last_error = repr(exc)
                self._daemon._log(f"mem mirror refresh failed: {exc!r}")
                return False
            # Swap in atomically. Anyone holding `_use_lock` finishes
            # their read against the old store; subsequent borrowers
            # get the new one.
            with self._use_lock:
                old = self._store
                self._store = new_store
                self._ready = True
                self._last_refresh_ts = time.time()
                self._refresh_count += 1
                self._last_error = None
            if old is not None:
                try:
                    old.close()
                except Exception:
                    pass
        return True

    def _load_from_snapshot(self, snap: Path) -> "Store":
        """Open an in-memory Store and populate every catalog table
        from the snapshot file. Tables are copied one at a time via
        `CREATE TABLE x AS SELECT * FROM src.x`, which preserves
        schema + data without re-running migrations.

        Uses the real `Store.__init__` so every lazily-checked attribute
        (`_read_via_duckdb`, `_duck_view`, `_link_buffer`, `_fragments`,
        etc.) is populated. Then overrides `db_path` to `:memory:` and
        connects the in-memory backend manually, bypassing the snapshot/
        symlink resolution from __init__ and the migration logic in
        `_connect`.
        """
        from refmatrix.store import Store
        writer = self._daemon.store
        assert writer is not None  # snapshot reader exists only while serving
        # Build a fully-initialized read-only Store, then redirect it
        # to the in-memory backend. read_only=True keeps __init__ off
        # any write-paths and gives us the correct sentinel state.
        s = Store(
            writer.root,
            partition=writer._partition_name,
            read_only=True,
        )
        # Override db_path AFTER __init__ — the snapshot/symlink block
        # in Store.__init__ pointed it at `catalog.read.duckdb`; we
        # want the in-memory backend instead.
        s.db_path = Path(":memory:")
        # Open the in-memory backend connection directly so we don't
        # trigger Store._connect's migration / schema-DDL paths.
        s._conn = s._backend.connect(s.db_path)
        mc = s._conn._duck
        # ATTACH the snapshot in read-only mode and clone every table
        # in `main` schema. Skip information_schema/system tables.
        mc.execute(f"ATTACH '{snap}' AS src (READ_ONLY)")
        try:
            # `duckdb_tables()` enumerates tables across all attached DBs
            # — information_schema views aren't reachable through an
            # ATTACH alias in DuckDB ≥ 0.10, but duckdb_tables() always
            # works.
            rows = mc.execute(
                "SELECT table_name FROM duckdb_tables() "
                "WHERE database_name='src' AND schema_name='main'"
            ).fetchall()
            for (table,) in rows:
                qt = table.replace('"', '""')
                mc.execute(f'CREATE TABLE "{qt}" AS SELECT * FROM src."{qt}"')
        finally:
            mc.execute("DETACH src")
        # Resolve partition_id off the freshly-loaded data.
        try:
            row = mc.execute(
                "SELECT id FROM partitions WHERE name=?",
                (s._partition_name,),
            ).fetchone()
            s._partition_id = row[0] if row else 1
        except Exception:
            s._partition_id = 1
        # Callers `close()` the borrowed Store at end of op — but the
        # mirror Store is shared, not per-op. Swap `close` for a no-op
        # so the convention works without leaking the in-memory state.
        # Real close happens only through `_MemMirror.close()` /
        # `refresh()` swap.
        s.close = lambda: None  # type: ignore[assignment]
        return s

    def close(self) -> None:
        with self._refresh_lock:
            old = self._store
            self._store = None
            self._ready = False
        if old is not None:
            try:
                old.close()
            except Exception:
                pass

    def stats(self) -> dict:
        return {
            "ready": self._ready,
            "last_refresh_ts": self._last_refresh_ts,
            "refresh_count": self._refresh_count,
            "last_error": self._last_error,
        }

# Replica refresh strategy switch. `apply_log_delta` replays log events
# one-by-one through the Store API (~tens of KB/s on a large catalog), so a
# multi-MB backlog can peg CPU for a very long time and never converge
# across restarts. Once the inactive slot is this far behind, rebuild it by
# copying the (already-current) writer file instead — O(file size), bounded,
# seconds. Small deltas still take the cheap incremental replay path.
REPLICA_REBUILD_DELTA_BYTES = int(
    os.environ.get("RMX_REPLICA_REBUILD_DELTA_BYTES", str(16 * 1024 * 1024))
)


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


def ping(root: Path, timeout: float = 0.5, retries: int = 2,
         retry_backoff: float = 0.15) -> bool:
    """Quick health check: send {"op":"ping"} and expect ok=true.

    Retries before answering False. A single 0.5s probe cannot tell a DEAD
    daemon from a BUSY one, and a healthy daemon is routinely busy at exactly
    the moment something checks: rebuilding an index at startup (observed
    `repaired idx_entity_links_lk_concept rows=23138`), flushing fragments, or
    holding the store lock for a write. cliquet was reported `stale pid …
    (socket unreachable)` while a direct RPC answered in 0.1s.

    Cost is unchanged when the daemon is healthy — one round trip, capped at
    `timeout`. The extra attempts are only paid on the path that is about to
    declare a daemon dead, which is the expensive thing to get wrong."""
    sock = socket_path(root)
    if not sock.exists():
        return False
    for attempt in range(max(1, retries + 1)):
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)
                s.connect(str(sock))
                s.sendall(b'{"op":"ping"}\n')
                data = _recv_line(s, timeout)
            if json.loads(data).get("ok") is True:
                return True
        except Exception:
            pass
        if attempt < retries:
            time.sleep(retry_backoff * (attempt + 1))
    return False


def served_identity(root: Path, timeout: float = 2.0) -> "tuple[int, str] | None":
    """`(pid, version)` the live daemon reports via ping, or None if no daemon
    answers. The authority on whether a restart actually swapped the process:
    compare against the installed `__version__` and the pre-restart pid."""
    try:
        resp = call(root, "ping", {}, timeout=timeout, retries=1)
    except Exception:
        return None
    if not isinstance(resp, dict) or not resp.get("ok"):
        return None
    result = resp.get("result") or {}
    pid = result.get("pid")
    ver = result.get("version")
    if pid is None or ver is None:
        return None
    return int(pid), str(ver)


def call(root: Path, op: str, args: dict | None = None,
         timeout: float = 60.0, retries: int = 2,
         retry_backoff: float = 0.05) -> dict:
    """Send a request to the daemon and return the parsed response.

    Retries on transient errors that surface when the daemon is mid-
    swap, mid-restart, or briefly socket-busy. Specifically:
      * empty-line response (`JSONDecodeError`) — socket closed before
        write, typical of a daemon restart racing the call.
      * `ConnectionResetError` / `BrokenPipeError` — peer reset.
      * `TimeoutError` from the socket — daemon held `_store_lock`
        longer than the caller's patience.
    Each retry doubles the backoff. Backoff is bounded: total wait
    is `retry_backoff * (2^retries - 1)` (default ~150 ms across
    2 retries). Long enough to absorb a swap window; short enough
    not to compound CLI latency.
    """
    sock = socket_path(root)
    payload = json.dumps({"op": op, "args": args or {}}).encode() + b"\n"
    last_exc: Exception | None = None
    backoff = retry_backoff
    for attempt in range(retries + 1):
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)
                s.connect(str(sock))
                s.sendall(payload)
                data = _recv_line(s, timeout)
            return json.loads(data)
        except (json.JSONDecodeError, ConnectionResetError, BrokenPipeError,
                socket.timeout, TimeoutError, ConnectionRefusedError) as exc:
            last_exc = exc
            if attempt >= retries:
                break
            time.sleep(backoff)
            backoff *= 2
    raise last_exc  # type: ignore[misc]


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
        # Memory-only guard: the user-level global store (`~/.refmatrix`)
        # holds memories and must never track filesystem code/doc paths — a
        # historical $HOME ingest filled it with ~/Library cache churn and a
        # perpetual stale count. Derived from the root (same test
        # launchctl.plist_for_root uses) so every launch path agrees without
        # flag plumbing; also force-drops any watch roots for the same reason.
        self.memory_only = (
            self.root == (Path.home() / ".refmatrix").resolve()
        )
        if self.memory_only:
            self.watch_roots = []
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
        # FIFO lock — see `_FairLock`. The ingest yield (release+sleep+
        # acquire) is only useful if waiters are guaranteed a turn; the
        # built-in `threading.Lock` doesn't promise that and the ingest
        # thread re-grabs the lock most cycles, starving CLI ops.
        self._store_lock = _FairLock()
        self._async_flush_pending = False
        self._async_lock = threading.Lock()
        # Background jobs (big ops run off the RPC thread so the caller gets
        # an id instead of a 300s socket timeout). id -> {state, phase, done,
        # total, result, error}; states: running | done | error.
        self._jobs: dict[str, dict] = {}
        self._jobs_lock = threading.Lock()
        # Read-op refcount + gate. Each `_open_read_store` increments the
        # count; the dedicated read store's wrapper decrements on close
        # and notifies. `_refresh_replica_now` waits on this gate before
        # closing connections so the swap never runs while a reader
        # holds a cursor against the slot file. Prevents the
        # "NoneType not subscriptable" / empty-row race observed in
        # 0.3.23.
        self._swap_gate = threading.Condition()
        self._read_inflight = 0
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
        # facts.log compaction tick. See `_start_factslog_compact_tick`.
        self._factslog_stop: "threading.Event | None" = None
        self._factslog_thread: "threading.Thread | None" = None
        # Guard against re-entering fast-exit from multiple threads racing
        # the same FatalException.
        self._fast_exit_armed = False
        self._fast_exit_lock = threading.Lock()
        # Dense embedder cache. Populated lazily by `_embedder()` on
        # first `embed` / `ann_search` op so the daemon doesn't load
        # ~134 MB of sentence-transformers state unless someone asks
        # for it. None when [dense] extra isn't installed yet.
        self._embedder_inst = None
        # Out-of-process model workers (RMX_EMBED_SUBPROC=1). When enabled,
        # `_embedder()` returns a `RemoteEmbedder` over `_embed_worker` and
        # the ~610 MB model lives in a child that can actually be killed to
        # reclaim it. `_rerank_worker` backs the optional cross-encoder
        # stage, which is subprocess-only by policy — a 90 MB-to-1.1 GB
        # second model has no business resident in this process.
        self._embed_worker = None
        self._rerank_worker = None
        self._reranker_inst = None
        self._worker_lock = threading.Lock()
        # Snapshot-tier state. `_request_snapshot()` sets `_snapshot_dirty`
        # + signals `_snapshot_event`; the snapshot tick thread debounces
        # and produces `catalog.read.duckdb`. `_last_snapshot_ts` gates
        # ad-hoc `_snapshot_catalog()` calls so a burst pays one copy.
        self._snapshot_stop: "threading.Event | None" = None
        self._snapshot_event: "threading.Event | None" = None
        self._snapshot_thread: "threading.Thread | None" = None
        self._snapshot_dirty = False
        self._last_snapshot_ts: float = 0.0
        self._snapshot_lock = threading.Lock()
        # Ingest job registry. Single-active guard: an in-flight ingest
        # blocks subsequent ingest starts (synchronous or detached) so
        # two ingests never trample each other on the same store. State
        # entries hold {id, status, files_total, files_done, started_at,
        # ended_at, result, error}. Cleared on daemon restart — no
        # cross-process persistence by design.
        self._ingest_jobs: dict[str, dict] = {}
        self._ingest_jobs_lock = threading.Lock()
        # In-memory mirror. Refreshed from `catalog.read.duckdb` after
        # every snapshot tick — reads served from here run against
        # uncompressed in-memory data with no file-system contention.
        # Disabled when `RMX_MEM_MIRROR=0`. See `_MemMirror`.
        self._mem_mirror: "_MemMirror | None" = None

    def _st(self) -> "Store":
        """The open Store, narrowed for op handlers. serve_forever()
        opens the store before any request is dispatched."""
        st = self.store
        assert st is not None  # opened in serve_forever() before dispatch
        return st

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
        if subproc_embed_enabled():
            try:
                e = self._remote_embedder()
                self._embedder_inst = e
                self._log(
                    f"embedder loaded (subprocess) "
                    f"model={e.model_name} dim={e.dim}"
                )
                return e
            except ImportError:
                # No [dense] extra. In-process would fail identically, so
                # let the op handlers surface it the way they always have.
                raise
            except Exception as exc:
                # Anything else -- an interpreter the child can't reach, a
                # sandbox that forbids spawn, a pipe the OS won't give us --
                # is a transport problem, not a dense problem. Since this is
                # the DEFAULT path now, failing here would take dense
                # retrieval down on hosts where it used to work fine. Fall
                # back to the in-process model and say so loudly.
                self._log(
                    f"subprocess embedder unavailable ({exc!r}); "
                    "falling back to in-process model -- the daemon now "
                    "carries the model's RSS. Set RMX_EMBED_SUBPROC=0 to "
                    "silence this, or investigate the spawn failure."
                )
                # Only the embed worker: a live rerank worker is unrelated
                # and killing it would cost a needless model reload.
                w, self._embed_worker = self._embed_worker, None
                if w is not None:
                    try:
                        w.close(timeout=2.0)
                    except Exception:
                        pass
        from refmatrix.embedder import Embedder

        e = Embedder()
        # Trigger the model load so the first real call doesn't
        # eat the latency. Subsequent calls are model.encode-only.
        _ = e.dim
        self._embedder_inst = e
        self._log(f"embedder loaded model={e.model_name} dim={e.dim}")
        return e

    def _remote_embedder(self):
        """Build the subprocess-backed embedder, spawning its worker.

        Raises ImportError when the [dense] extra is missing, matching the
        in-process path's contract: every `_op_*` already catches ImportError
        and returns a clean client error instead of crashing the daemon.
        The worker reports the failure as an error frame; we translate.
        """
        from refmatrix.embedder import RemoteEmbedder
        from refmatrix.subproc import WorkerError

        e = RemoteEmbedder(self._model_client("embed"))
        try:
            _ = e.dim          # forces the spawn + model load now
        except WorkerError as exc:
            if "ModuleNotFoundError" in str(exc) or "ImportError" in str(exc):
                raise ImportError(str(exc)) from exc
            raise
        return e

    def _model_client(self, role: str):
        """Return a client for `role` — the hub's shared worker when one is
        listening, otherwise a private worker of our own.

        The hub hosts one embedder and one reranker for the whole fleet
        because the models are identical and only the stores differ; seven
        daemons each holding both was ~6.5 GB to serve one person typing in
        one project. Falling back to a private worker rather than failing is
        the rule that keeps the hub from becoming a single point of failure
        for every store's dense retrieval.
        """
        attr = "_embed_worker" if role == "embed" else "_rerank_worker"
        with self._worker_lock:
            existing = getattr(self, attr, None)
            if existing is not None:
                return existing
            client = None
            from refmatrix import modelsrv
            if modelsrv.shared_enabled() and modelsrv.shared_available():
                try:
                    client = modelsrv.SharedWorkerClient(role, log=self._log)
                    # prove it answers before adopting — bounded, so a mute
                    # socket costs seconds, not the 300 s op timeout
                    client.info(timeout=modelsrv.PROBE_TIMEOUT_S)
                    self._log(f"{role}: using hub-shared worker")
                except Exception as exc:
                    self._log(
                        f"{role}: hub-shared worker unusable ({exc!r}); "
                        "falling back to a private worker"
                    )
                    try:
                        if client is not None:
                            client.close()
                    except Exception:
                        pass
                    client = None
            if client is None:
                from refmatrix.subproc import WorkerClient
                client = WorkerClient(role, log=self._log)
                client.set_stderr(self.log_fh)
            setattr(self, attr, client)
            return client

    def _reranker(self):
        """Lazy cross-encoder reranker, always out-of-process.

        Unlike the embedder there is no in-process branch. A reranker is a
        SECOND model in a daemon that already jetsams under one; keeping it
        subprocess-only means the co-residence question never reopens.
        Raises ImportError when the [dense] extra is missing.
        """
        existing = getattr(self, "_reranker_inst", None)
        if existing is not None:
            return existing
        from refmatrix.reranker import RemoteReranker, rerank_available
        from refmatrix.subproc import WorkerError

        if not rerank_available():
            raise ImportError("sentence-transformers not installed")
        r = RemoteReranker(self._model_client("rerank"))
        try:
            name = r.model_name
        except WorkerError as exc:
            if "ModuleNotFoundError" in str(exc) or "ImportError" in str(exc):
                raise ImportError(str(exc)) from exc
            raise
        self._reranker_inst = r
        self._log(f"reranker loaded (subprocess) model={name}")
        return r

    def _maybe_rerank(self, args: dict) -> bool:
        """Should this op run the rerank stage? Per-request `rerank` arg
        wins; otherwise the RMX_RERANK env default."""
        from refmatrix.reranker import rerank_enabled
        want = args.get("rerank")
        return rerank_enabled() if want is None else bool(want)

    def _close_workers(self) -> None:
        """Terminate model workers. Called on shutdown so a daemon exit
        never strands a child holding ~610 MB (or its pipes)."""
        for attr in ("_embed_worker", "_rerank_worker"):
            w = getattr(self, attr, None)
            if w is None:
                continue
            try:
                w.close(timeout=2.0)
            except Exception as exc:
                self._log(f"worker close failed ({attr}): {exc!r}")
            setattr(self, attr, None)
        self._embedder_inst = None
        self._reranker_inst = None

    def _evict_idle_workers(self) -> None:
        """Reap workers idle past RMX_WORKER_IDLE_S (default 0 = never).

        This is the eviction that in-process caching could never provide:
        the memory comes back because the process is gone. Opt-in, because
        the next query then pays a cold model load — worth it on a
        memory-constrained host, not on a busy one.
        """
        idle_s = float(os.environ.get("RMX_WORKER_IDLE_S", "0") or "0")
        if idle_s <= 0:
            return
        for attr, cache in (("_embed_worker", "_embedder_inst"),
                            ("_rerank_worker", "_reranker_inst")):
            w = getattr(self, attr, None)
            if w is None:
                continue
            try:
                if w.evict_if_idle(idle_s):
                    # Drop the proxy too: it caches dim/model_name, which
                    # stay valid, but a fresh proxy keeps the invariant
                    # "proxy exists => worker was reachable" simple.
                    setattr(self, cache, None)
            except Exception as exc:
                self._log(f"worker idle-evict failed ({attr}): {exc!r}")

    def _start_embedder_warmup(self) -> None:
        """Load the dense embedder in the background once the daemon is up.

        It used to load lazily on the first `embed` / `ann_search`, which put
        ~134MB of sentence-transformers startup on whoever asked first — and
        that is almost always the always-on UserPromptSubmit hook, which runs
        `memory recall --scope both` and therefore pays it on TWO stores.
        Measured in cli.log: 5.2s, 5.3s, 6.0s, 8.8s, 21.8s, every one of them
        the first recall after a daemon restart, against ~0.18s warm. The
        hook's 30s budget covers three stages, so a couple of cold stores
        could blow the whole thing and Claude Code discards ALL hook output on
        timeout — the context injection silently vanishes.

        Deliberately best-effort and off the critical path: a daemon with no
        [dense] extra installed, or a model that fails to load, is still a
        perfectly good daemon for every symbolic op. Set RMX_NO_EMBED_WARMUP=1
        to keep the old lazy behaviour (a memory-constrained host may prefer
        never to hold the model unless something asks).
        """
        if os.environ.get("RMX_NO_EMBED_WARMUP") in ("1", "true", "True"):
            self._log("embedder warmup disabled (RMX_NO_EMBED_WARMUP)")
            return

        def _warm() -> None:
            t0 = time.time()
            try:
                self._embedder()
                self._log(f"embedder warm in {time.time() - t0:.1f}s")
            except ImportError:
                self._log("embedder warmup skipped ([dense] extra not installed)")
            except Exception as exc:
                # Never fatal: symbolic ops do not need the embedder, and the
                # lazy path will retry on first real use.
                self._log(f"embedder warmup failed: {exc!r}")
            # Same argument for the reranker, and the same stakes: a cold
            # cross-encoder on the first recall would blow the hook budget
            # exactly the way the cold embedder used to.
            from refmatrix.reranker import rerank_enabled
            if not rerank_enabled():
                return
            t1 = time.time()
            try:
                self._reranker()
                self._log(f"reranker warm in {time.time() - t1:.1f}s")
            except ImportError:
                self._log("reranker warmup skipped ([dense] extra not installed)")
            except Exception as exc:
                self._log(f"reranker warmup failed: {exc!r}")

        threading.Thread(target=_warm, name="rmx-embed-warm",
                         daemon=True).start()

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

    def _mark_repair_needed(self, table: str, *, op: str) -> Path:
        """A read surface hit index drift: record it for the boot-time
        repair instead of taking the daemon down (plan-4 task 4.1 — every
        `rmx grep` miss fast-exited the daemon 39 times on 2026-09-14).
        Idempotent; the marker names the first op that saw it."""
        self._repair_needed = table
        p = repair_marker_path(self.root)
        if not p.exists():
            try:
                p.write_text(json.dumps({"table": table, "op": op, "at": time.time()}))
            except OSError as e:
                self._log(f"could not write {p.name}: {e}")
        return p

    def _adopt_unsupervised(self, sock_path: Path) -> bool:
        """A SUPERVISED start (launchd's `--no-detach`) that finds a live
        daemon answering on this root — a manual `rmx daemon start` the
        supervisor does not own — asks it to stop gracefully and takes the
        root over. Before this, `serve_foreground` raised "already running"
        → exit 1 → KeepAlive respawn every 10 s: orderly's launchd job ran
        11,251 times in 1.3 days behind one unsupervised daemon (plan-4
        task 4.4). Returns True when a daemon was adopted (stopped or asked
        to stop; a survivor is escalated by `_reap_predecessor`)."""
        if not (sock_path.exists() and ping(self.root, timeout=0.5, retries=0)):
            return False
        pid = None
        try:
            resp = call(self.root, "ping", {}, timeout=1.0, retries=0)
            pid = ((resp or {}).get("result") or {}).get("pid")
        except Exception:
            pass
        if self.log_fh is None:
            try:
                self.log_fh = (self.root / LOG_NAME).open("a", encoding="utf-8")
            except OSError:
                pass
        self._log(f"adopted unsupervised daemon pid={pid or '?'} on {self.root}: "
                  f"asking it to stop so the supervised daemon owns the root")
        stopped = stop_daemon(self.root, timeout=ADOPT_GRACE_S)
        if not stopped:
            self._log(f"adopted daemon pid={pid or '?'} did not stop within "
                      f"{ADOPT_GRACE_S:g}s; startup reap will escalate")
        return True

    def _start_heartbeat(self) -> None:
        """Touch `.refmatrix/heartbeat` every RMX_HEARTBEAT_S (5) from a
        thread that takes NO lock, so the supervisor's liveness signal is
        independent of every op. Interval is re-read so tests can shorten it."""
        import threading as _t
        if getattr(self, "_heartbeat_thread", None) and self._heartbeat_thread.is_alive():
            return
        self._heartbeat_stop = _t.Event()
        interval = float(os.environ.get("RMX_HEARTBEAT_S", str(HEARTBEAT_INTERVAL_S)) or "5")
        hb = heartbeat_path(self.root)

        def _runner():
            stop = self._heartbeat_stop
            while not stop.is_set():
                try:
                    hb.touch()
                except OSError:
                    pass
                stop.wait(interval)

        try:
            hb.touch()  # first touch synchronously: alive from line one
        except OSError:
            pass
        self._heartbeat_thread = _t.Thread(target=_runner, name="rmxd-heartbeat", daemon=True)
        self._heartbeat_thread.start()

    def _stop_heartbeat(self) -> None:
        ev = getattr(self, "_heartbeat_stop", None)
        if ev is not None:
            ev.set()
        th = getattr(self, "_heartbeat_thread", None)
        if th is not None and th.is_alive():
            th.join(timeout=2.0)

    def _run_pending_repair(self) -> "dict | None":
        """Boot-time repair (plan-4 task 4.2): when a read surface left
        `repair.needed`, rebuild the named table BEFORE serving and clear
        the marker. None when there is nothing to do. A `RepairAbort` (real
        duplicates) is logged loudly and the marker KEPT, so `daemon status`
        keeps saying `repair pending` until an operator resolves it."""
        from refmatrix.store import RepairAbort
        marker = read_repair_marker(self.root)
        if not marker:
            return None
        table = str(marker.get("table") or "unknown")
        if table != "entities":
            self._log(f"repair.needed names unknown table {table!r}; clearing the marker")
            repair_marker_path(self.root).unlink(missing_ok=True)
            return {"table": table, "skipped": "unknown-table"}
        try:
            with self._store_lock:
                rep = self.store.rebuild_entities_indexes()
        except RepairAbort as e:
            self._log(f"repair ABORTED for entities: {e}; marker kept — operator action needed")
            return {"table": table, "aborted": str(e)}
        repair_marker_path(self.root).unlink(missing_ok=True)
        self._repair_needed = None
        self._log(f"repaired entities rows={rep['rows']} indexes={rep['indexes']} "
                  f"(queued by {marker.get('op')})")
        return {"table": table, **rep}

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

    def _reap_predecessor(self, sock_path: Path) -> bool:
        """Kill any predecessor daemon for this root so a fresh launch wins.

        Targets the pid named in the pid file (the single owner slot) — a
        wedged process that holds the file but no longer serves, or a healthy
        orphan that should defer to this newer launch. SIGTERM, then escalate
        to SIGKILL. Returns True when it is safe to bind (predecessor gone, or
        none existed); False only if a predecessor survives SIGKILL AND still
        answers the socket — in which case the caller yields to avoid a
        double-bind that could corrupt the DuckDB WAL.

        A stale socket file (no listener) is unlinked either way."""
        my_pid = os.getpid()
        old = read_pid(self.root)  # live pid from the pid file, or None
        if old is not None and old != my_pid:
            try:
                os.kill(old, signal.SIGTERM)
            except ProcessLookupError:
                old = None
            except PermissionError:
                old = None  # not ours to kill; fall through to the ping gate
            if old is not None:
                deadline = time.monotonic() + 3.0
                while time.monotonic() < deadline and is_alive(old):
                    time.sleep(0.1)
                if is_alive(old):
                    try:
                        os.kill(old, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    # Brief grace for the kernel to tear it down + release the
                    # socket.
                    kdeadline = time.monotonic() + 2.0
                    while time.monotonic() < kdeadline and is_alive(old):
                        time.sleep(0.05)
        # If something still answers the socket after the reap, a process we
        # could not kill owns it — yield rather than stomp it.
        if sock_path.exists() and ping(self.root, timeout=0.3):
            return False
        # Clean up a stale socket left by a crashed/killed predecessor.
        if sock_path.exists():
            try:
                sock_path.unlink()
            except OSError:
                pass
        return True

    def serve_forever(self) -> int:
        sock_path = socket_path(self.root)
        # Smart startup: reap any predecessor daemon for this root before we
        # bind. launchd serializes spawns of a job, so a fresh launch is the
        # legit owner — an older process still holding the pid file (a wedged
        # alive-but-not-serving daemon) or still answering on the socket (an
        # orphan / standalone fork that escaped the supervisor) must yield to
        # it, NOT the other way round. Without this, a wedged predecessor or an
        # orphan kept the socket and every relaunch crash-looped on a refused
        # connection while `launchctl list` showed the job "running".
        if not self._reap_predecessor(sock_path):
            # Could not guarantee the predecessor is gone (it ignored SIGKILL
            # or we lack permission) AND it still answers — yield rather than
            # double-bind and corrupt the DuckDB WAL.
            self.log_fh = self.log_fh or (self.root / LOG_NAME).open("a", encoding="utf-8")
            self._log("startup: predecessor still serving after reap; yielding")
            return 0

        self.log_fh = self.log_fh or (self.root / LOG_NAME).open("a", encoding="utf-8")
        self._log(f"daemon starting pid={os.getpid()} root={self.root}")
        pid_path(self.root).write_text(str(os.getpid()))
        # Heartbeat first: the store open + repairs below can take a while
        # and the supervisor must already see "alive", not "dead".
        self._start_heartbeat()
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
            # A read surface queued an entities rebuild (task 4.1): run it
            # now, single-writer, before anything is served.
            try:
                self._run_pending_repair()
            except Exception as e:  # noqa: BLE001 — logged, boot continues
                self._log(f"pending repair failed: {e!r}; marker kept")

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
        # Defensive rebind: `Store(self.root, ...)` opened the legacy
        # `catalog.duckdb` by default. `_bootstrap_rotation_if_needed`
        # rebinds to the active slot ONLY when it has to copy the
        # legacy file into A/B. When both slots already exist, the
        # bootstrap returns early and the store is still pointed at
        # `catalog.duckdb` — writes leak into the legacy file until
        # the first replica swap rebinds. Force the rebind here so
        # every write from line one targets the rotation-tracked slot.
        active_path = self._replica_file(self._active_slot)
        if (self.store is not None
                and self.store._backend.kind == "duckdb"
                and active_path.exists()
                and self.store.db_path != active_path):
            try:
                self.store._connect().execute("CHECKPOINT")
                self.store.flush_fragments()
                self.store.close()
            except Exception as exc:
                self._log(f"init slot rebind: close failed: {exc!r}")
            try:
                self.store = Store(self.root, partition=self.partition)
                self.store.db_path = active_path
                self.store.init()
                self._log(
                    f"init slot rebind: db_path -> {active_path.name}"
                )
            except Exception as exc:
                # Fall back to the legacy file; daemon stays alive but
                # writes will continue to land in catalog.duckdb. Log
                # so the operator notices the drift.
                #
                # "Log so the operator notices" was not enough. cliquet served
                # 1 entity out of 3545 from the legacy file after this fired,
                # and nothing surfaced it: `rmx daemon status` said running,
                # the hub said daemon_up + stale_files 0. The line below is
                # why `_store_health` reports `slot_bound`, and why the hub
                # alerts on it.
                self._log(
                    f"init slot rebind FAILED: {exc!r} — SERVING LEGACY "
                    f"catalog.duckdb; the rotation slot "
                    f"{active_path.name} is NOT bound and its contents are "
                    f"invisible until this is fixed"
                )
                self.store = Store(self.root, partition=self.partition)
                self.store.init()
        # Reconcile the on-disk marker to the slot we actually opened.
        # The rebind can land on a different slot than the marker named
        # (e.g. the intended slot was lock-held by a lingering daemon
        # during a supervised restart, or a prior swap drifted). Persist
        # the truth so the next swap / `rmx replica status` don't trust a
        # lying marker. No-op on the legacy fallback (real is None).
        real = self._writer_slot_from_store()
        if real is not None:
            self._active_slot = real
            if self._read_active_slot() != real:
                try:
                    self._active_marker().write_text(real)
                    self._log(f"init marker reconcile: active -> {real}")
                except OSError as exc:
                    self._log(f"init marker reconcile failed: {exc!r}")
        # Point read_only.duckdb at the reader (non-writer) slot so
        # out-of-process readers always have a lock-free path even before
        # the first rotation cycle. Derived from the real writer above.
        self._refresh_read_only_link()
        # Writer rotation is dropped: the writer stays pinned to the active
        # slot for the daemon's life. No refresh/swap thread is started — the
        # swap could promote a log-replayed slot missing under-logged state.
        # Snapshot-tier: unidirectional copy of writer catalog into
        # `catalog.read.duckdb`, regenerated within ~250ms after each write op.
        # This is the sole read path now (A/B kept only as the writer's slot).
        self._start_snapshot_tick()
        # facts.log rotation: keep the append-only mutation log from growing
        # unbounded across re-ingests (a churned store reached 2.4GB).
        self._start_factslog_compact_tick()
        # Materialize an initial snapshot at startup so readers spawning
        # right after `daemon start` already have a lock-free file to
        # open. Best-effort: a checkpoint failure here doesn't block
        # serve_forever — the snapshot tick retries on the first write.
        try:
            self._snapshot_catalog(force=True)
        except Exception as exc:
            self._log(f"startup snapshot failed: {exc!r}")
        # In-memory mirror. Constructed + warmed from the startup
        # snapshot above. Disabled with RMX_MEM_MIRROR=0 on memory-
        # constrained hosts. See `_MemMirror`.
        if os.environ.get("RMX_MEM_MIRROR", "1") != "0":
            self._mem_mirror = _MemMirror(self)
            if self._mem_mirror.refresh():
                self._log("mem mirror ready")
            else:
                self._log("mem mirror not ready (no snapshot yet)")

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
        self._start_embedder_warmup()

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
            # Model workers first: they hold no locks and no store state,
            # so reaping them early gives back ~610 MB (and any reranker)
            # while the slower DuckDB teardown runs.
            try:
                self._close_workers()
            except Exception as exc:
                self._log(f"worker shutdown failed: {exc!r}")
            if self._watch_stop is not None:
                self._watch_stop.set()
            if getattr(self, "_flush_stop", None) is not None:
                self._flush_stop.set()
            self._stop_heartbeat()
            repair_stop = getattr(self, "_repair_stop", None)
            if repair_stop is not None:
                repair_stop.set()
            factslog_stop = getattr(self, "_factslog_stop", None)
            if factslog_stop is not None:
                factslog_stop.set()
            replica_stop = getattr(self, "_replica_stop", None)
            if replica_stop is not None:
                replica_stop.set()
            snapshot_stop = getattr(self, "_snapshot_stop", None)
            if snapshot_stop is not None:
                snapshot_stop.set()
                # Wake the snapshot tick out of its event.wait().
                ev = getattr(self, "_snapshot_event", None)
                if ev is not None:
                    ev.set()
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
            repair_thread = getattr(self, "_repair_thread", None)
            if repair_thread is not None:
                repair_thread.join(timeout=3.0)
            replica_thread = getattr(self, "_replica_thread", None)
            if replica_thread is not None:
                replica_thread.join(timeout=3.0)
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
                        self._st().close()
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
                # Outside _store_lock on purpose: reaping a worker must
                # never queue behind a multi-minute ingest holding the lock.
                try:
                    self._evict_idle_workers()
                except Exception as exc:
                    self._log(f"worker evict tick failed: {exc!r}")
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
            stop = self._repair_stop
            assert stop is not None  # set just above, before the thread starts
            while not stop.is_set():
                if stop.wait(interval_s):
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

    # ---- facts.log rotation ---------------------------------------------

    def _factslog_threshold(self) -> int:
        """Max facts.log size before compaction, in bytes. Default 256 MiB.
        <=0 disables auto-compaction."""
        return int(
            os.environ.get("RMX_FACTSLOG_MAX_BYTES", str(256 * 1024 * 1024))
            or 0
        )

    def _factslog_floor_path(self) -> Path:
        """Path to the compaction floor marker — the size facts.log must reach
        before auto-compaction is worth attempting again."""
        return self.root / "factslog.floor"

    def _read_factslog_floor(self) -> int:
        p = self._factslog_floor_path()
        if not p.exists():
            return 0
        try:
            return int(p.read_text().strip() or "0")
        except (OSError, ValueError):
            return 0

    def _write_factslog_floor(self, floor: int) -> None:
        p = self._factslog_floor_path()
        try:
            if floor <= 0:
                p.unlink(missing_ok=True)
            else:
                p.write_text(str(int(floor)))
        except OSError as exc:
            self._log(f"facts.log floor write failed: {exc!r}")

    # A compaction that reclaims less than this fraction of the log did not
    # earn its cost: the log is already at (or near) its minimal form and the
    # size gate alone would re-fire it on the very next tick, forever.
    _FACTSLOG_MIN_RECLAIM = 0.10
    # How much a floored log must grow past its compacted size before another
    # attempt can pay off.
    _FACTSLOG_REGROW = 1.25

    def _compact_factslog_if_needed(self, *, force: bool = False) -> dict:
        """Compact `.refmatrix/facts.log` when it grows past the threshold.

        facts.log is the append-only mutation log: every write appends, and
        re-ingests append duplicate events the catalog already folds by name.
        Left alone it grows unbounded (a re-ingested store hit 2.4 GB).
        `dump_catalog_to_log()` rewrites it from the authoritative catalog as a
        minimal, replay-faithful current-state snapshot (atomic tmp+rename).

        Held under `_store_lock` so no concurrent `_log_event` append races the
        swap (every write op already serializes on that lock). After the swap
        every byte-offset into the old, larger log is stale, so reset the A/B
        slot offsets to the new EOF — the snapshot is full current state,
        already materialized in the catalog, so there is nothing left for a
        delta-replay to apply.

        Size-gated: returns `{skipped: ...}` until the log exceeds the
        threshold. `force=True` compacts regardless of size."""
        if self.store is None:
            return {"skipped": "no-store"}
        log_path = self.store.log_path
        try:
            size = log_path.stat().st_size
        except OSError:
            return {"skipped": "no-log"}
        threshold = self._factslog_threshold()
        # A store whose MINIMAL snapshot already exceeds the threshold (a big
        # catalog: hundreds of thousands of entities/links) can never get back
        # under it. The size gate alone therefore re-fires every tick forever,
        # rewriting hundreds of MB under `_store_lock` and reclaiming nothing —
        # observed on a 202k-entity store as `270568387 -> 270568387 bytes`
        # every 30 minutes, which also blocked `stats` RPCs long enough for the
        # hub to report a null. The floor records "compacting at this size does
        # not help"; auto-compaction resumes only after real growth past it.
        floor = self._read_factslog_floor()
        effective = max(threshold, floor)
        if not force and (threshold <= 0 or size < effective):
            return {"skipped": "under-threshold", "size": size,
                    "threshold": threshold, "floor": floor or None}
        with self._store_lock:
            counts = self.store.dump_catalog_to_log()
            try:
                new_size = log_path.stat().st_size
            except OSError:
                new_size = 0
            # Old offsets point past the new EOF; reset both slots to the end.
            for slot in ("A", "B"):
                if self._slot_offset_path(slot).exists():
                    self._write_slot_offset(slot, new_size)
        reclaimed = size - new_size
        ratio = (reclaimed / size) if size else 0.0
        if ratio < self._FACTSLOG_MIN_RECLAIM:
            new_floor = int(new_size * self._FACTSLOG_REGROW)
            self._write_factslog_floor(new_floor)
            self._log(
                f"facts.log compaction reclaimed {reclaimed} bytes "
                f"({ratio:.1%}) — at its minimal size; floor set to "
                f"{new_floor} bytes (no auto-compaction until it grows past)"
            )
        else:
            # Productive again — drop any floor so the plain size gate governs.
            new_floor = 0
            if self._read_factslog_floor():
                self._write_factslog_floor(0)
        self._log(
            f"facts.log compacted {size} -> {new_size} bytes "
            f"(entity={counts.get('entity')} link={counts.get('link')} "
            f"memory_content={counts.get('memory_content')})"
        )
        return {"compacted": True, "old_size": size, "new_size": new_size,
                "counts": counts, "reclaimed": reclaimed,
                "floor": new_floor or None}

    def _start_factslog_compact_tick(self) -> None:
        """Spawn the facts.log compaction tick. Wakes every
        RMX_FACTSLOG_COMPACT_INTERVAL_S (default 1800s) and compacts when the
        log exceeds RMX_FACTSLOG_MAX_BYTES (default 256 MiB). Low frequency
        because `dump_catalog_to_log` scans the whole catalog under
        `_store_lock` (seconds on a 100k-entity store) — only paid when the log
        is genuinely bloated. Disable by setting either env <= 0."""
        if self.store is None:
            return
        interval_s = float(
            os.environ.get("RMX_FACTSLOG_COMPACT_INTERVAL_S", "1800") or "1800"
        )
        if interval_s <= 0 or self._factslog_threshold() <= 0:
            return
        import threading as _t
        self._factslog_stop = _t.Event()

        def _runner():
            stop = self._factslog_stop
            assert stop is not None  # set just above, before the thread starts
            while not stop.is_set():
                if stop.wait(interval_s):
                    return
                if self.store is None:
                    continue
                try:
                    r = self._compact_factslog_if_needed()
                    if r.get("compacted"):
                        self._log(
                            f"periodic facts.log compaction: "
                            f"{r['old_size']} -> {r['new_size']} bytes"
                        )
                except Exception as exc:
                    self._log(f"periodic facts.log compaction failed: {exc!r}")
                    self._fast_exit_if_invalidated(exc, "facts.log compaction")

        self._factslog_thread = _t.Thread(
            target=_runner, name="rmxd-factslog", daemon=True,
        )
        self._factslog_thread.start()

    # ---- read replica (rotation) ----------------------------------------

    def _replica_file(self, slot: str) -> Path:
        """Path to a rotation slot file (`A` or `B`)."""
        return self.root / f"catalog.{slot}.duckdb"

    def _writer_slot_from_store(self) -> str | None:
        """The slot letter the store is ACTUALLY open on, read off
        `store.db_path`. Authoritative over the `active` marker: a swap
        reopens the store on the new slot before persisting the marker,
        so if that persist fails (or an abrupt restart lands mid-swap)
        the marker drifts while the store keeps writing the real slot.
        Deriving the reader from this — not the marker — guarantees the
        `read_only.duckdb` symlink never lands on the locked writer.

        Returns None for the legacy `catalog.duckdb` (not a rotation
        slot), in which case callers fall back to the marker."""
        store = getattr(self, "store", None)
        if store is None:
            return None
        try:
            name = Path(store.db_path).name
        except Exception:
            return None
        if name == self._replica_file("A").name:
            return "A"
        if name == self._replica_file("B").name:
            return "B"
        return None

    def _open_read_store(self, partition: str | None = None) -> "Store | None":
        """Return a Store usable for a single read op.

        Resolution order (fastest → safest):
          1. In-memory mirror (`_mem_mirror`). Zero file I/O, ~1ms reads.
             Lagged by `RMX_SNAPSHOT_DEBOUNCE_MS` (default 250ms) behind
             the writer.
          2. Snapshot file `catalog.read.duckdb`. ~10ms per open. Lock-
             free because the writer never holds the snapshot open
             exclusively. Same lag as the mirror.
          3. Writer rotation slot fallback. Used only when no snapshot
             file exists yet (very early bootstrap).

        For the mirror path, the returned Store is the SHARED in-memory
        Store — callers must NOT `close()` it. The refcount + close-
        patch dance only applies to file-backed paths (which need to
        coordinate with replica swap). The mirror's own `_use_lock`
        already serializes concurrent cursors against the shared
        connection.
        """
        # Mirror path: zero-latency, no file I/O.
        mirror = getattr(self, "_mem_mirror", None)
        if mirror is not None:
            mirror_store = mirror.borrow()
            if mirror_store is not None:
                # Repoint the partition if the caller wants a different
                # one — partition_id resolution lives on the Store.
                if partition is not None and \
                        partition != mirror_store._partition_name:
                    try:
                        with mirror.acquire_use():
                            row = mirror_store._conn._duck.execute(
                                "SELECT id FROM partitions WHERE name=?",
                                (partition,),
                            ).fetchone()
                        if row:
                            mirror_store._partition_name = partition
                            mirror_store._partition_id = row[0]
                    except Exception:
                        pass
                return mirror_store
        # File-snapshot or slot fallback path.
        from refmatrix.store import Store
        snap = self._snapshot_file()
        if snap.exists():
            target = snap
        else:
            active = self._active_slot or self._read_active_slot()
            target = self._replica_file(active)
            if not target.exists():
                return None
        # Reserve the refcount BEFORE the connect attempt so a swap that
        # races a failing connect can't sneak through between increment
        # and the failure path. Released in `close()` (success) or
        # immediately on failure below.
        with self._swap_gate:
            self._read_inflight += 1
        try:
            s = Store(
                self.root,
                partition=partition or self._st()._partition_name,
                read_only=True,
            )
            s.db_path = target
            s._connect()  # surface lock errors here, not at first query
        except Exception as exc:
            with self._swap_gate:
                self._read_inflight -= 1
                if self._read_inflight == 0:
                    self._swap_gate.notify_all()
            self._log(f"open_read_store({target.name}) failed: {exc!r}")
            return None
        # Patch close() so the refcount drops + notifies exactly once.
        orig_close = s.close
        already_closed = [False]
        daemon_ref = self

        def _wrapped_close() -> None:
            if already_closed[0]:
                return
            already_closed[0] = True
            try:
                orig_close()
            finally:
                with daemon_ref._swap_gate:
                    daemon_ref._read_inflight -= 1
                    if daemon_ref._read_inflight == 0:
                        daemon_ref._swap_gate.notify_all()
        s.close = _wrapped_close  # type: ignore[assignment]
        return s

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

    def _reader_slot(self) -> str:
        """The slot the read replica should point at: the one the writer
        is NOT on. Derived from the store's real db_path when it sits on a
        rotation slot (drift-proof), else from the `active` marker."""
        writer = self._writer_slot_from_store()
        if writer is None:
            writer = self._read_active_slot()
        return "B" if writer == "A" else "A"

    def _set_read_only_link(self, slot: str) -> None:
        """Atomically point `read_only.duckdb` at a SPECIFIC slot file.
        os.symlink-to-temp + os.replace. No-op if symlinks aren't available
        (Windows w/o developer mode); the Store side falls back to
        `catalog.duckdb` in that case.

        Used both for the steady-state reader (`_refresh_read_only_link`)
        and, mid-refresh, to move readers onto the just-freed old-writer
        slot before the slot being caught up gets write-locked."""
        import os as _os
        target = self._replica_file(slot).name
        link = self._read_only_link()
        tmp = link.with_name(link.name + ".tmp")
        try:
            if tmp.exists() or tmp.is_symlink():
                tmp.unlink()
            _os.symlink(target, tmp)
            _os.replace(tmp, link)
        except OSError as exc:
            self._log(f"read_only.duckdb symlink update failed: {exc!r}")

    def _refresh_read_only_link(self) -> None:
        """Point `read_only.duckdb` at the lock-free reader.

        Snapshot-tier wins when `catalog.read.duckdb` exists — readers land
        on a file the writer is never attached to, so there's zero lock
        contention even mid-rotation. Falls back to the rotation reader
        slot (`_reader_slot`) when no snapshot has been taken yet, which
        keeps the bootstrap window and SQLite-only deploys working."""
        snap = self._snapshot_file()
        if snap.exists():
            self._set_read_only_link_to(snap.name)
            return
        self._set_read_only_link(self._reader_slot())

    def _snapshot_file(self) -> Path:
        """Snapshot-tier reader file. Materialized by `_snapshot_catalog()`
        as an atomic file-copy of the writer's current DuckDB catalog,
        regenerated after every write op (debounced)."""
        return self.root / "catalog.read.duckdb"

    def _set_read_only_link_to(self, target_name: str) -> None:
        """Atomically point `read_only.duckdb` at `target_name`. Same
        primitive as `_set_read_only_link` but takes a filename instead
        of a slot letter — used by snapshot-tier which targets
        `catalog.read.duckdb` rather than a slot file."""
        import os as _os
        link = self._read_only_link()
        tmp = link.with_name(link.name + ".tmp")
        try:
            if tmp.exists() or tmp.is_symlink():
                tmp.unlink()
            _os.symlink(target_name, tmp)
            _os.replace(tmp, link)
        except OSError as exc:
            self._log(f"read_only.duckdb symlink update failed: {exc!r}")

    def _snapshot_catalog(self, *, force: bool = False) -> dict:
        """Materialize a frozen read-only copy of the writer's catalog at
        `catalog.read.duckdb` and swing `read_only.duckdb` to it.

        CHECKPOINT flushes WAL into the main file, then a file-level copy
        produces a self-contained snapshot — no second DuckDB process,
        no shared-lock attach. Atomic via tmp + os.replace.

        Debounced by RMX_SNAPSHOT_DEBOUNCE_MS (default 250ms). The
        background snapshot tick is the normal driver; ad-hoc calls
        through `_op_snapshot(force=True)` bypass the debounce.

        DuckDB-only. SQLite stores skip silently — SQLite WAL already
        gives many-readers-one-writer concurrency without snapshotting."""
        if self.store is None or self.store._backend.kind != "duckdb":
            return {"skipped": "non-duckdb"}
        now = time.monotonic()
        debounce_s = float(
            os.environ.get("RMX_SNAPSHOT_DEBOUNCE_MS", "250") or "250"
        ) / 1000.0
        with self._snapshot_lock:
            if not force and (now - self._last_snapshot_ts) < debounce_s:
                return {
                    "skipped": "debounced",
                    "since_last_s": now - self._last_snapshot_ts,
                }
            snap_path = self._snapshot_file()
            tmp_path = snap_path.with_name(snap_path.name + ".tmp")
            import shutil as _shutil
            with self._store_lock:
                try:
                    self.store._connect().execute("CHECKPOINT")
                except Exception as exc:
                    self._log(f"snapshot CHECKPOINT failed: {exc!r}")
                    return {"error": "checkpoint", "detail": str(exc)}
                src = self.store.db_path
                try:
                    for p in (
                        tmp_path,
                        tmp_path.with_name(tmp_path.name + ".wal"),
                    ):
                        if p.exists() or p.is_symlink():
                            p.unlink()
                    _shutil.copy2(src, tmp_path)
                    os.replace(tmp_path, snap_path)
                except OSError as exc:
                    self._log(f"snapshot copy failed: {exc!r}")
                    return {"error": "copy", "detail": str(exc)}
            self._set_read_only_link_to(snap_path.name)
            self._last_snapshot_ts = now
            try:
                size = snap_path.stat().st_size
            except OSError:
                size = 0
            # Refresh the in-memory mirror off the new snapshot so the
            # next read sees fresh state. Best-effort: a refresh failure
            # leaves the previous mirror in place and `_open_read_store`
            # falls back to the snapshot file.
            mirror = getattr(self, "_mem_mirror", None)
            if mirror is not None:
                try:
                    mirror.refresh()
                except Exception as exc:
                    self._log(f"mem mirror refresh raised: {exc!r}")
            return {
                "snapshot_path": str(snap_path),
                "size": size,
                "source": str(src),
            }

    def _request_snapshot(self) -> None:
        """Mark catalog as having an outstanding write that needs to land
        in the snapshot. The snapshot tick picks this up within the
        debounce window and runs `_snapshot_catalog()`.

        Safe to call under `_store_lock` (sets a flag + signals an Event;
        does no DuckDB work itself). Write-op handlers call this at the
        tail of their handler so readers see fresh state within ~250ms."""
        self._snapshot_dirty = True
        ev = self._snapshot_event
        if ev is not None:
            ev.set()

    def _start_snapshot_tick(self) -> None:
        """Spawn the snapshot ticker. Sleeps on `_snapshot_event` until a
        write op fires; on wake, sleeps `RMX_SNAPSHOT_DEBOUNCE_MS` to
        coalesce burst writes, then runs `_snapshot_catalog(force=True)`.

        Disabled on SQLite backend (no need). Disabled by setting
        RMX_SNAPSHOT_DEBOUNCE_MS=0."""
        if self.store is None or self.store._backend.kind != "duckdb":
            return
        debounce_ms = float(
            os.environ.get("RMX_SNAPSHOT_DEBOUNCE_MS", "250") or "250"
        )
        if debounce_ms <= 0:
            return
        debounce_s = debounce_ms / 1000.0
        import threading as _t
        self._snapshot_stop = _t.Event()
        self._snapshot_event = _t.Event()

        def _runner():
            stop = self._snapshot_stop
            ev = self._snapshot_event
            assert stop is not None and ev is not None  # set before thread start
            while not stop.is_set():
                ev.wait()
                if stop.is_set():
                    return
                ev.clear()
                if stop.wait(debounce_s):
                    return
                if not self._snapshot_dirty:
                    continue
                self._snapshot_dirty = False
                try:
                    self._snapshot_catalog(force=True)
                except Exception as exc:
                    self._log(f"snapshot tick failed: {exc!r}")
                    self._fast_exit_if_invalidated(exc, "snapshot tick")

        self._snapshot_thread = _t.Thread(
            target=_runner, name="rmxd-snapshot", daemon=True,
        )
        self._snapshot_thread.start()

    @staticmethod
    def _force_close_store(st) -> None:
        """Guarantee a Store's DuckDB connection (and its file lock) is
        released, even if flush_fragments() would re-raise on a poisoned
        catalog. Drops `_conn` directly, then best-effort close(). Safe on
        None. This is the no-leak backstop for every transient slot Store
        the rotation opens."""
        if st is None:
            return
        conn = getattr(st, "_conn", None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
            st._conn = None
        try:
            st.close()
        except Exception:
            pass

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
        """No-op: writer rotation is dropped (see body). Kept so the
        `replica refresh` RPC and any lingering caller degrade gracefully."""
        # Writer rotation is DROPPED. The swap promoted the inactive slot —
        # caught up only by facts.log delta-replay — to writer; any state not
        # fully captured by the log (memory_content historically, plus any
        # under-logged table or off-log direct write made while the daemon was
        # down) was absent from the promoted slot, and the snapshot rebuilt
        # from the new writer lost it. Snapshot-tier (`catalog.read.duckdb`, a
        # full copy of the writer) is the read path, so the swap bought nothing
        # and only risked data loss. The writer now stays pinned to the active
        # slot for the daemon's life; the refresh thread is no longer started.
        # Retained as a no-op so the `replica refresh` RPC degrades gracefully.
        return {"enabled": False, "ok": True,
                "reason": "rotation dropped (snapshot-tier read path)"}

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

    def _start_watcher(self) -> None:
        """Spawn a watchdog thread that debounces fs events and syncs the
        changed files through the daemon's Store. The flush callback grabs
        `_store_lock` so it never races synchronous request handlers."""
        import threading
        try:
            from watchdog.events import FileSystemEventHandler  # pyright: ignore[reportMissingImports]
            from watchdog.observers import Observer  # pyright: ignore[reportMissingImports]
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
                            and self._st()._backend.kind == "duckdb"):
                        try:
                            self._st().repair_entity_links_index()
                            repaired = True
                        except Exception as rexc:
                            self._log(f"pre-flush repair failed: {rexc!r}")
                            self._fast_exit_if_invalidated(rexc, "pre-flush repair")
                    total_added = total_updated = total_purged = 0
                    cancelled = False
                    for owner, owner_paths in groups.items():
                        report = sync_files(
                            self._st(), owner_paths,
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
            stop = self._watch_stop
            assert stop is not None  # set before the watcher thread starts
            try:
                while not stop.is_set():
                    stop.wait(1.0)
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
    # `version` is the code the daemon PROCESS actually imported, which is the
    # only authority on whether a restart took: the CLI binary and the daemon
    # are separate processes, and a stale daemon serves old ops while `rmx
    # --version` reports the new install. `rmx daemon restart --relaunch`
    # polls this until it changes.
    from refmatrix import __version__ as _v
    # `code_path` / `dev_tree`: which tree THIS process imported. A daemon
    # whose venv points at a dev checkout ran uncommitted code all day on
    # 2026-09-14 while every status surface said "deployed". Computed once
    # at import (identity cannot change within a process) so the health
    # probe never globs site-packages and never fails because of it.
    ident = _process_identity()
    out = {
        "pid": os.getpid(),
        "root": str(d.root),
        "backend": d.store._backend.kind if d.store else None,
        "version": _v,
        "code_path": ident["code_path"],
        "dev_tree": ident["dev_tree"],
    }
    # The fallback identity is a GUESS; say so on the wire so every consumer
    # (hub rows, relaunch guard, daemon status) renders it as unverified
    # (bsd-plan1-r4 #b-1: the readers existed, the producer dropped it).
    if ident.get("identity_error"):
        out["identity_error"] = ident["identity_error"]
    return out


_PROCESS_IDENTITY: "dict | None" = None


def _process_identity() -> dict:
    global _PROCESS_IDENTITY
    if _PROCESS_IDENTITY is None:
        try:
            from refmatrix import upgrade as _up
            ident = _up.runtime_identity()
            _PROCESS_IDENTITY = {"code_path": str(ident["import_path"]),
                                 "dev_tree": bool(ident["dev_tree"])}
        except Exception as e:  # noqa: BLE001 — never take the ping down
            import refmatrix
            _PROCESS_IDENTITY = {"code_path": str(getattr(refmatrix, "__file__", "?")),
                                 "dev_tree": False, "identity_error": str(e)}
    return _PROCESS_IDENTITY


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
            d._st(), project_root=proot, semantic=semantic,
            cancel_check=d._shutdown_event.is_set,
        )
    d._request_snapshot()
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
                    d._st(), project_root=proot, semantic=semantic,
                    cancel_check=d._shutdown_event.is_set,
                )
            d._request_snapshot()
        except Exception as exc:
            d._log(f"async flush failed: {exc!r}")
        finally:
            with d._async_lock:
                d._async_flush_pending = False

    t = threading.Thread(target=_runner, name="rmxd-async-flush", daemon=True)
    t.start()
    return {"queued": True}


def _refuse_filesystem_ingest(d: Daemon, op: str) -> None:
    """Refuse ops that would track filesystem paths into a memory-only
    store. Raising here surfaces as `{"ok": False, "error": ...}` at the
    dispatch layer, so the caller fails loudly instead of silently filling
    the global store with code/doc rows."""
    if d.memory_only:
        raise RuntimeError(
            f"{op} refused: {d.root} is the memory-only global store and "
            "does not track filesystem paths. Ingest into a project store, "
            "or use `rmx ingest-gmd --as-memory` for memory rows."
        )


def _op_sync_files(d: Daemon, args: dict) -> dict:
    from refmatrix import sync as syncmod
    _refuse_filesystem_ingest(d, "sync")
    proot = Path(args.get("project_root") or Path.cwd()).resolve()
    files = args.get("files") or []
    semantic = bool(args.get("semantic"))
    with d._store_lock:
        report = syncmod.sync_files(
            d._st(), [str(p) for p in files],
            project_root=proot, semantic=semantic,
            cancel_check=d._shutdown_event.is_set,
        )
    d._request_snapshot()
    return report


def _op_ingest_path(d: Daemon, args: dict) -> dict:
    """Run a full ingest against the daemon-owned store. CLI routes here
    when the daemon is up so the catalog write lock stays single-owner.

    Cooperative: instead of holding `_store_lock` for the whole ingest, the
    dominant inner loops flush fragments and yield the lock every N units, so
    a big `tldr-warm` doesn't stall latency-sensitive writes (memory hooks)
    for minutes. Same machinery as `_run_ingest_gmd_body`."""
    from refmatrix.ingest import ingest_path
    _refuse_filesystem_ingest(d, "ingest")
    path = Path(args["path"]).resolve()
    source = args.get("source") or "auto"
    semantic = bool(args.get("semantic"))
    yield_every = int(
        os.environ.get("RMX_INGEST_YIELD_EVERY_UNITS", "200") or "200"
    )
    yield_sleep_s = float(
        os.environ.get("RMX_INGEST_YIELD_SLEEP_S", "0.005") or "0.005"
    )

    def _yield() -> None:
        d._store_lock.release()
        time.sleep(yield_sleep_s)
        d._request_snapshot()
        d._store_lock.acquire()

    # Emit `ingest-progress` per pass so the blocking CLI ingest isn't a black
    # box — the CLI tails these lines live (see `_stream_ingest_progress`).
    job_id = f"ingest-{int(time.monotonic() * 1000) % 1_000_000}"
    t0 = time.monotonic()

    def _progress(phase: str, done: int = 0, total: int = 0) -> None:
        elapsed = time.monotonic() - t0
        detail = f"{done}/{total} " if total else ""
        d._log(f"ingest-progress {phase} {detail}job={job_id} "
               f"elapsed={elapsed:.0f}s {path}")

    part = args.get("partition")
    d._store_lock.acquire()
    try:
        if part:
            with d._st().with_partition(part):
                n = ingest_path(
                    d._st(), path, source=source, semantic=semantic,
                    yield_lock=_yield, yield_every=yield_every,
                    progress_cb=_progress,
                )
        else:
            n = ingest_path(
                d._st(), path, source=source, semantic=semantic,
                yield_lock=_yield, yield_every=yield_every,
                progress_cb=_progress,
            )
    finally:
        d._store_lock.release()
    d._request_snapshot()
    return {"entities": n, "path": str(path)}


def _register_ingest_job(d: Daemon, *, files_total: int, args: dict) -> str:
    """Reserve the ingest slot or raise if another job is already running.

    Single-active-ingest guard: two ingests against the same daemon would
    fight over `_store_lock` AND interleave their two-pass parse/resolve
    state. Forbid it. Caller proceeds with the returned `job_id` and
    must eventually flip `status` to `done` or `error`.
    """
    job_id = uuid.uuid4().hex[:12]
    with d._ingest_jobs_lock:
        for jid, js in d._ingest_jobs.items():
            if js["status"] == "running":
                raise RuntimeError(
                    f"ingest already active: job {jid} "
                    f"({js['files_done']}/{js['files_total']} files)"
                )
        d._ingest_jobs[job_id] = {
            "id": job_id,
            "status": "running",
            "started_at": time.time(),
            "ended_at": None,
            "files_total": files_total,
            "files_done": 0,
            "current_file": None,
            "events": deque(maxlen=2000),
            "next_seq": 1,
            "result": None,
            "error": None,
            "args": {
                k: args.get(k) for k in
                ("targets", "verbose", "as_memory", "memory_mtype", "partition")
            },
        }
    return job_id


def _run_ingest_gmd_body(d: Daemon, job_id: str, files: list, args: dict) -> dict:
    """Execute one ingest against the daemon's Store. Mutates the job
    record in `d._ingest_jobs` as it goes — `files_done`, `current_file`,
    and an `events` deque every status query can stream from.

    Yields `_store_lock` between files (best-effort with stdlib Lock, FIFO
    with `_FairLock`) so cli-pool reads interleave. Triggers a snapshot
    every `RMX_INGEST_SNAPSHOT_EVERY` yields so readers see partial
    progress instead of an end-of-ingest cliff.
    """
    from refmatrix.ingest_gmd import ingest_gmd_paths
    job = d._ingest_jobs[job_id]
    yield_every = int(os.environ.get("RMX_INGEST_YIELD_EVERY", "1") or "1")
    # Default sleep raised from 1ms to 5ms — paired with `_FairLock`,
    # 5ms gives the OS scheduler plenty of margin to wake a waiter
    # without measurably hurting ingest throughput on the bg side.
    yield_sleep_s = float(
        os.environ.get("RMX_INGEST_YIELD_SLEEP_S", "0.005") or "0.005"
    )
    # Mid-ingest snapshot cadence in yield-count units. 0 disables.
    # Default 1: request a snapshot on every yield. `_request_snapshot()`
    # is cheap (sets a flag + signals an Event); the actual file copy
    # runs on the snapshot-tick thread and is debounced by
    # `RMX_SNAPSHOT_DEBOUNCE_MS`. So one-per-yield doesn't fan out into
    # one-per-yield file copies — it just keeps the snapshot ticker
    # warm so the snapshot file is always reasonably fresh.
    snapshot_every = int(
        os.environ.get("RMX_INGEST_SNAPSHOT_EVERY", "1") or "1"
    )
    partition = args.get("partition") or d._st()._partition_name
    log_every = max(1, yield_every)
    t0 = time.monotonic()
    yield_counter = [0]

    def _progress(phase: str, i: int, n: int, p: Path) -> None:
        with d._ingest_jobs_lock:
            job["files_done"] = i
            job["files_total"] = n
            job["current_file"] = str(p)
            job["events"].append({
                "seq": job["next_seq"],
                "phase": phase, "i": i, "n": n,
                "path": str(p), "ts": time.time(),
            })
            job["next_seq"] += 1
        if i == 1 or i == n or i % log_every == 0:
            elapsed = time.monotonic() - t0
            eta = (elapsed / max(i, 1)) * max(n - i, 0)
            d._log(
                f"ingest-progress {phase} {i}/{n} job={job_id} "
                f"elapsed={elapsed:.0f}s eta={eta:.0f}s {p}"
            )

    def _yield() -> None:
        d._store_lock.release()
        time.sleep(yield_sleep_s)
        yield_counter[0] += 1
        if snapshot_every > 0 and yield_counter[0] % snapshot_every == 0:
            d._request_snapshot()
        d._store_lock.acquire()

    try:
        d._store_lock.acquire()
        try:
            with d._st().with_partition(partition):
                stats = ingest_gmd_paths(
                    d._st(), files, verbose=bool(args.get("verbose")),
                    yield_lock=_yield, yield_every=yield_every,
                    as_memory=bool(args.get("as_memory")),
                    memory_mtype_default=args.get("memory_mtype") or "curated",
                    progress_cb=_progress,
                )
        finally:
            d._store_lock.release()
    except Exception as exc:
        with d._ingest_jobs_lock:
            job["status"] = "error"
            job["error"] = repr(exc)
            job["ended_at"] = time.time()
        d._request_snapshot()
        raise
    d._request_snapshot()
    result = {
        "files": len(files), "report": stats.report(),
        "docs": stats.docs, "nodes": stats.nodes,
        "rels": stats.rels, "mentions": stats.mentions,
        "unresolved": len(stats.unresolved),
        "job_id": job_id,
    }
    with d._ingest_jobs_lock:
        job["status"] = "done"
        job["result"] = result
        job["ended_at"] = time.time()
    return result


def _op_ingest_gmd(d: Daemon, args: dict) -> dict:
    """Synchronous GMD ingest against the daemon-owned store. Errors if
    another ingest is already in flight against the same daemon.

    Honors `args['partition']` so `--as-memory` rows land in the caller's
    partition (e.g. `memory-<project>`) rather than the daemon's bound
    partition.
    """
    from refmatrix.ingest_gmd import collect_gmd_files
    if not args.get("as_memory"):
        _refuse_filesystem_ingest(d, "ingest-gmd")
    targets = [Path(p).resolve() for p in (args.get("targets") or [])]
    files = collect_gmd_files(targets)
    if not files:
        return {"files": 0, "report": "no candidate files found"}
    job_id = _register_ingest_job(d, files_total=len(files), args=args)
    return _run_ingest_gmd_body(d, job_id, files, args)


def _op_ingest_gmd_start(d: Daemon, args: dict) -> dict:
    """Detached GMD ingest: register the job, dispatch onto `bg_pool`,
    and return the job_id immediately. The client polls via
    `ingest_gmd_status` (or tails events via the cursor) and disconnects
    without holding a 24h socket open.
    """
    from refmatrix.ingest_gmd import collect_gmd_files
    if not args.get("as_memory"):
        _refuse_filesystem_ingest(d, "ingest-gmd")
    targets = [Path(p).resolve() for p in (args.get("targets") or [])]
    files = collect_gmd_files(targets)
    if not files:
        return {"files": 0, "report": "no candidate files found"}
    job_id = _register_ingest_job(d, files_total=len(files), args=args)

    def _runner() -> None:
        try:
            _run_ingest_gmd_body(d, job_id, files, args)
        except Exception as exc:
            d._log(f"detached ingest job {job_id} failed: {exc!r}")

    # Dispatched to bg_pool so it counts against bg worker budget like
    # the synchronous path. Daemon shutdown drains bg_pool, so a clean
    # `rmx daemon stop` still waits for in-flight ingest to finish.
    d._bg_pool.submit(_runner)
    return {
        "job_id": job_id,
        "files_total": len(files),
        "status": "running",
    }


def _run_detached_job(d: Daemon, job_id: str, fn) -> None:
    """Run `fn()` on the bg pool under the ingest-job lifecycle: flip the job
    record to `done` (capturing the return as `result`) or `error`. The job
    record is otherwise progress-agnostic — `ingest_path`/`embed` emit their
    own `ingest-progress`/running-total log lines that the status op surfaces
    via the daemon log; per-file event granularity is GMD-only."""
    job = d._ingest_jobs[job_id]
    try:
        result = fn()
        with d._ingest_jobs_lock:
            job["status"] = "done"
            job["ended_at"] = time.time()
            job["result"] = result
    except Exception as exc:
        with d._ingest_jobs_lock:
            job["status"] = "error"
            job["ended_at"] = time.time()
            job["error"] = repr(exc)
        d._log(f"detached job {job_id} failed: {exc!r}")


def _op_ingest_path_start(d: Daemon, args: dict) -> dict:
    """Fire-and-poll `ingest_path`: reserve the ingest slot, dispatch the same
    body `_op_ingest_path` runs onto bg_pool, return the job_id immediately.
    Poll completion via `ingest_gmd_status` (generic over all ingest jobs).
    The single-active guard in `_register_ingest_job` rejects a second start
    while one is running."""
    _refuse_filesystem_ingest(d, "ingest")
    job_id = _register_ingest_job(d, files_total=0, args=args)
    d._bg_pool.submit(lambda: _run_detached_job(d, job_id, lambda: _op_ingest_path(d, args)))
    return {"job_id": job_id, "status": "running",
            "path": str(Path(args["path"]).resolve())}


def _op_embed_start(d: Daemon, args: dict) -> dict:
    """Fire-and-poll `embed`: dispatch the embedding pass onto bg_pool and
    return the job_id immediately. Poll via `ingest_gmd_status`. Shares the
    single-active-ingest slot so an embed and an ingest don't fight the store
    lock."""
    job_id = _register_ingest_job(d, files_total=0, args=args)
    d._bg_pool.submit(lambda: _run_detached_job(d, job_id, lambda: _op_embed(d, args)))
    return {"job_id": job_id, "status": "running"}


def _op_mem_mirror_status(d: Daemon, args: dict) -> dict:
    """Inspect the in-memory mirror: ready / last refresh / refresh
    count / last error. Lets operators verify the mirror is keeping
    up with the writer."""
    mirror = getattr(d, "_mem_mirror", None)
    if mirror is None:
        return {"enabled": False, "reason": "disabled or pre-init"}
    return {"enabled": True, **mirror.stats()}


def _op_ingest_gmd_status(d: Daemon, args: dict) -> dict:
    """Inspect ingest jobs. `args['job_id']` selects one job; omitted
    returns all jobs (sans events for compactness). `args['since_seq']`
    streams new per-file events with seq > since_seq, capped at
    `args['limit']` (default 500).
    """
    job_id = args.get("job_id")
    since_seq = int(args.get("since_seq", 0) or 0)
    limit = int(args.get("limit", 500) or 500)
    with d._ingest_jobs_lock:
        if not job_id:
            return {
                "jobs": [
                    {k: v for k, v in js.items() if k != "events"}
                    for js in d._ingest_jobs.values()
                ],
            }
        js = d._ingest_jobs.get(job_id)
        if js is None:
            raise KeyError(f"no such ingest job: {job_id}")
        events = [
            e for e in js["events"] if e["seq"] > since_seq
        ][:limit]
        job_summary = {k: v for k, v in js.items() if k != "events"}
        return {"job": job_summary, "events": events}


def _op_prestage_hashes(d: Daemon, args: dict) -> dict:
    """Backfill `gmd_content_hash` on entities for files whose content
    matches the current DB state. Bootstraps the auto-resume fast path
    on older stores without re-running the full ingest pipeline."""
    from refmatrix.ingest_gmd import collect_gmd_files, prestage_hashes
    targets = [Path(p).resolve() for p in (args.get("targets") or [])]
    files = collect_gmd_files(targets)
    partition = args.get("partition") or d._st()._partition_name
    with d._store_lock, d._st().with_partition(partition):
        report = prestage_hashes(d._st(), files)
    d._request_snapshot()
    return report


def _op_sync_since(d: Daemon, args: dict) -> dict:
    """Run `sync_since` through the daemon's long-lived Store. Targets the
    git post-commit hook (`rmx sync --since HEAD~1`), which used to grab
    the catalog write lock outside the daemon and block every other
    flush for the duration of a 100+ file diff."""
    from refmatrix import sync as syncmod
    _refuse_filesystem_ingest(d, "sync")
    proot = Path(args.get("project_root") or Path.cwd()).resolve()
    git_ref = args["git_ref"]
    semantic = bool(args.get("semantic"))
    with d._store_lock:
        report = syncmod.sync_since(
            d._st(), git_ref, project_root=proot, semantic=semantic,
            cancel_check=d._shutdown_event.is_set,
        )
    d._request_snapshot()
    return report


def _op_stats(d: Daemon, args: dict) -> dict:
    with d._store_lock:
        out = d._st().stats()
        # `--stale` needs the writer's tracked_files (mtime > last_synced),
        # which the replica/snapshot never refreshes — so serve it from the
        # daemon (the writer) instead of forcing the user to stop the daemon.
        if args.get("include_stale"):
            out["stale_files"] = d._st().stale_files()
        if args.get("include_health"):
            out["health"] = _store_health(d)
        return out


def _store_health(d: Daemon) -> dict:
    """Facts a monitor needs that `daemon_up` + `stale_files` cannot express.

    Written after a store ran for six days reporting `daemon_up: true,
    stale_files: 0` while EVERY memory read raised (1013 logged failures) and
    its catalog had grown to 41GB for 45 documents. Both signals were true and
    both were useless: neither exercises a read path, and neither looks at the
    file. So this reports three things that would have caught it on day one.

    Cheap by construction — one bounded query, one stat() per catalog file —
    because it runs on the hub's alert tick for every project.
    """
    h: dict = {}
    # 1. Does a memory read actually work? A corrupt row, a bad index or a
    #    damaged zonemap surfaces here and nowhere else.
    try:
        d._st().recent_memories(limit=1)
        h["memory_read_ok"] = True
    except Exception as exc:
        h["memory_read_ok"] = False
        h["memory_read_error"] = f"{type(exc).__name__}: {exc}"[:200]
    # 2. Footprint. DuckDB reuses freed blocks but never shrinks the file, so
    #    unbounded growth is invisible until the disk is gone.
    try:
        total = 0
        for pat in ("catalog*.duckdb", "*.wal"):
            for f in d.root.glob(pat):
                try:
                    total += f.stat().st_size
                except OSError:
                    pass
        h["store_bytes"] = total
    except Exception:
        h["store_bytes"] = None
    # 3. WHICH catalog is being served. When the init slot rebind fails the
    #    daemon falls back to the legacy `catalog.duckdb` and serves whatever
    #    stale contents it holds — cliquet served 1 entity out of 3545 that
    #    way. The marker and the bound file disagreeing is the tell.
    try:
        h["db_file"] = d._st().db_path.name
        h["active_slot"] = d._read_active_slot()
        h["slot_bound"] = d._st().db_path.name != "catalog.duckdb"
    except Exception:
        pass
    return h


def _op_checkpoint(d: Daemon, args: dict) -> dict:
    """DuckDB CHECKPOINT: flush WAL into the main file. Also rebuilds the
    `entity_links` secondary index, which can get out of sync with the
    table after `prune-noise --drop` (DuckDB FATAL during the next
    DELETE — "Failed to delete all rows from index"). Drop+recreate
    self-heals without losing data."""
    if d._st()._backend.kind != "duckdb":
        return {"checkpointed": False, "reason": "not a duckdb backend"}
    with d._store_lock:
        con = d._st()._connect()._duck
        con.execute("DROP INDEX IF EXISTS idx_entity_links_lk_concept")
        con.execute(
            "CREATE INDEX idx_entity_links_lk_concept "
            "ON entity_links(linkage_id, concept_id)"
        )
        con.execute("CHECKPOINT")
    d._request_snapshot()
    return {"checkpointed": True, "index_rebuilt": True}


def _op_job_status(d: Daemon, args: dict) -> dict:
    """Status of a background job started by an async big-op (partition_merge
    with async=true). No `job` arg lists every known job this daemon run."""
    job_id = args.get("job")
    with d._jobs_lock:
        if job_id is None:
            return {"jobs": {k: dict(v) for k, v in d._jobs.items()}}
        j = d._jobs.get(job_id)
        if j is None:
            return {"error": f"unknown job {job_id!r}"}
        return {"job": job_id, **dict(j)}


def _op_prune_noise(d: Daemon, args: dict) -> dict:
    namespaces = tuple(args.get("namespaces") or ("keyword",))
    min_df = int(args.get("min_df", 2))
    max_df_ratio = float(args.get("max_df_ratio", 0.25))
    drop = bool(args.get("drop", False))
    with d._store_lock:
        result = d._st().prune_noise(
            namespaces=namespaces, min_df=min_df,
            max_df_ratio=max_df_ratio, drop=drop,
        )
    d._request_snapshot()
    return result


def _op_vacuum(d: Daemon, args: dict) -> dict:
    with d._store_lock:
        result = d._st().vacuum()
    d._request_snapshot()
    return result


def _op_upsert_entity(d: Daemon, args: dict) -> dict:
    import json as _json
    meta = args.get("meta")
    if isinstance(meta, str):
        meta = _json.loads(meta)
    with d._store_lock:
        eid = d._st().upsert_entity(
            kind=args["kind"], name=args["name"],
            path=args.get("path"), tldr=args.get("tldr"),
            meta=meta, protected=bool(args.get("protected", True)),
        )
    d._request_snapshot()
    return {"id": eid}


def _op_add_concept(d: Daemon, args: dict) -> dict:
    with d._store_lock:
        cid = d._st().add_concept(
            args["name"],
            description=args.get("description"),
            protected=bool(args.get("protected", True)),
        )
    d._request_snapshot()
    return {"id": cid}


def _op_add_linkage_type(d: Daemon, args: dict) -> dict:
    with d._store_lock:
        lid = d._st().add_linkage_type(
            name=args["name"],
            directed=bool(args.get("directed", True)),
            description=args.get("description"),
        )
    d._request_snapshot()
    return {"id": lid}


def _op_iter_entities(d: Daemon, args: dict) -> dict:
    kind = args.get("kind")
    with d._store_lock:
        rows = [
            {"id": e.id, "kind": e.kind, "name": e.name,
             "path": e.path, "tldr": e.tldr}
            for e in d._st().iter_entities(kind)
        ]
    return {"rows": rows}


def _op_list_linkages(d: Daemon, args: dict) -> dict:
    with d._store_lock:
        return {"rows": d._st().list_linkages()}


def _op_top_concepts(d: Daemon, args: dict) -> dict:
    """Density-ranked concept entry points (reuses primer.concept_density) —
    the Graph-tab landing view. Symbol-shaped, noise-excluded by default."""
    from refmatrix.primer import concept_density, is_symbol_like
    n = int(args.get("n", 30))
    symbol_only = bool(args.get("symbol_only", True))
    min_refs = int(args.get("min_refs", 2))
    exclude_ns = set(args.get("exclude_ns") or ("keyword",))
    partition = args.get("partition")

    def _run(s):
        rows = concept_density(s, include_noise=False)  # partition-scoped
        out, seen = [], set()
        for r in rows:
            name = r["name"]
            if r["total"] < min_refs:
                break  # sorted desc — nothing below this clears the bar
            if "/" in name and name.split("/", 1)[0] in exclude_ns:
                continue
            if symbol_only and not is_symbol_like(name):
                continue
            if name in seen:  # dedup by name (belt + suspenders)
                continue
            seen.add(name)
            out.append({"name": name, "total": r["total"],
                        "by_link": r["by_link"]})
            if len(out) >= n:
                break
        return out

    if partition:
        rows = _read_with_fallback(d, partition, _run)
    else:
        with d._store_lock:
            rows = _run(d.store)
    return {"concepts": rows}


def _op_snapshot(d: Daemon, args: dict) -> dict:
    """Materialize a fresh `catalog.read.duckdb` and swing the
    `read_only.duckdb` symlink onto it. Bypasses the debounce when
    `force=True` (default) so CLI callers get a guaranteed-fresh
    snapshot. Returns `{snapshot_path, size, source}` or `{skipped: ...}`
    on SQLite backends / non-DuckDB stores."""
    return d._snapshot_catalog(force=bool(args.get("force", True)))


def _op_compact_factslog(d: Daemon, args: dict) -> dict:
    """Compact `.refmatrix/facts.log` from the authoritative catalog (size-
    gated unless `force=True`). Returns `{compacted, old_size, new_size,
    counts}` or `{skipped: ...}`. Runs on the bg pool: the catalog scan can
    take seconds on a large store."""
    return d._compact_factslog_if_needed(force=bool(args.get("force", False)))


def _op_partition_add(d: Daemon, args: dict) -> dict:
    """Register a partition row in the catalog. Routed through the daemon
    so `rmx partition add` doesn't try to grab the writer lock from a
    second process."""
    import time as _time
    name = args["name"]
    kind = args.get("kind", "repo")
    root_path = args.get("root_path")
    with d._store_lock:
        con = d._st()._connect()
        con.execute(
            "INSERT OR IGNORE INTO partitions(name, kind, root_path, created_at) "
            "VALUES (?, ?, ?, ?)",
            (name, kind, root_path, _time.time()),
        )
        con.commit()
    d._request_snapshot()
    return {"name": name, "kind": kind}


def _op_partition_rename(d: Daemon, args: dict) -> dict:
    """Rename a partition. Routed through the daemon so the writer-side
    Store does the rename + directory moves under the held catalog lock."""
    old = args["old"]
    new = args["new"]
    with d._store_lock:
        d._st().rename_partition(old, new)
    d._request_snapshot()
    return {"old": old, "new": new}


def _op_partition_merge(d: Daemon, args: dict) -> dict:
    """Merge SRC partition into DST. Drops SRC on success. See
    `Store.merge_partition` for the full semantics — collisions remap
    child rows to DST and prefer the longer memory_content body.

    Driven by the memory partition consolidation (memory-<project>
    → <project>) that closes the cross-partition wikilink resolution
    gap. `dry_run=True` returns the same shape minus the mutation."""
    src = args["src"]
    dst = args["dst"]
    dry_run = bool(args.get("dry_run"))

    def _progress(job_id=None):
        def cb(phase: str, done: int, total: int) -> None:
            d._log(f"merge-progress {phase} {done}/{total} {src}->{dst}")
            if job_id is not None:
                with d._jobs_lock:
                    j = d._jobs.get(job_id)
                    if j is not None:
                        j.update(phase=phase, done=done, total=total)
        return cb

    if args.get("async") and not dry_run:
        # Background job: return an id now; the merge takes the store lock
        # per chunk (lock-yield), so queued ops interleave while it runs.
        import uuid
        job_id = uuid.uuid4().hex[:12]
        with d._jobs_lock:
            d._jobs[job_id] = {"state": "running", "op": "partition_merge",
                               "src": src, "dst": dst,
                               "phase": "classify", "done": 0, "total": 0,
                               "result": None, "error": None}

        def _run() -> None:
            try:
                res = d._st().merge_partition(
                    src, dst, dry_run=False,
                    lock=d._store_lock, progress=_progress(job_id))
                # The merge rewrites rows with direct SQL and emits NO log
                # events (facts.log audit 2026-09-06): without this snapshot
                # the log keeps describing the pre-merge partition layout and
                # every log-replay consumer silently diverges. The log is the
                # replication boundary — restructurings must be followed by a
                # forced snapshot-compaction.
                d._compact_factslog_if_needed(force=True)
                with d._jobs_lock:
                    d._jobs[job_id].update(state="done", result=res)
                d._request_snapshot()
                d._log(f"merge-done {src}->{dst} job={job_id}")
            except Exception as e:
                with d._jobs_lock:
                    d._jobs[job_id].update(state="error", error=str(e))
                d._log(f"merge-error {src}->{dst} job={job_id}: {e}")

        threading.Thread(target=_run, name=f"rmx-merge-{job_id}",
                         daemon=True).start()
        return {"job": job_id, "async": True}

    # Synchronous path: same lock-yield chunking, caller blocks for the
    # result. The lock is taken per chunk INSIDE merge_partition — not here —
    # so hooks and reads interleave with a long merge instead of timing out.
    result = d._st().merge_partition(
        src, dst, dry_run=dry_run,
        lock=d._store_lock, progress=_progress())
    if not dry_run:
        # See the async branch: merge_partition is log-invisible, so the log
        # must be re-snapshotted from the post-merge catalog.
        d._compact_factslog_if_needed(force=True)
        d._request_snapshot()
    return result


def _op_partition_list(d: Daemon, args: dict) -> dict:
    """List all partitions in the catalog. Routed through the daemon so
    `rmx partition list` doesn't try to grab the catalog lock the daemon
    already holds."""
    with d._store_lock:
        rows = d._st()._connect().execute(
            "SELECT id, name, kind, root_path, created_at "
            "FROM partitions ORDER BY id"
        ).fetchall()
    return {
        "rows": [
            {
                "id": r["id"],
                "name": r["name"],
                "kind": r["kind"],
                "root_path": r["root_path"],
                "created_at": r["created_at"],
            }
            for r in rows
        ],
        "daemon_partition": d._st().partition_name,
    }


def _op_list_saved_queries(d: Daemon, args: dict) -> dict:
    with d._store_lock:
        return {"rows": list(d._st().list_saved_queries())}


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
        rows = d._st()._connect()._duck.execute(
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


def _learn_grep_hits(store, pattern: str, hits: list, project_root: Path) -> dict:
    """Fold grep fall-through hits into a `query/PATTERN` concept (one
    `mentions` link + `linkage_evidence` per file/line). A search miss + a grep
    hit is a strong signal the user cares about PATTERN, so the concept AND its
    entities are marked **protected** — `prune_noise` skips `protected` rows, so
    the index self-heals permanently instead of re-missing after the next prune.
    Caller holds `d._store_lock`. Returns {added, concept, concept_id}."""
    name = f"query/{pattern}"
    with store.transaction(), store.deferred_links():
        cid = store.add_concept(
            name, description=f"learned from grep query {pattern!r}",
            protected=True,
        )
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
            # protected: a learned hit must survive prune_noise so the index
            # doesn't churn (miss -> grep -> learn -> prune -> miss ...).
            eid = store.upsert_entity(kind=kind, name=rel, path=str(ap),
                                      protected=True)
            store.link("mentions", cid, eid)
            for line in lines:
                store.add_evidence(
                    "mentions", cid, eid, file=rel, line=line,
                    detail=f"learned from grep {pattern!r}",
                )
            added += 1
    return {"added": added, "concept": name, "concept_id": cid}


def _op_learn_from_grep(d: Daemon, args: dict) -> dict:
    """Promote rg fallback hits into the index (protected — see
    `_learn_grep_hits`). Future `rmx grep`/`context` calls hit the index."""
    pattern = args["pattern"]
    hits = args.get("hits") or []  # [{file, line}]
    project_root = Path(args.get("project_root") or Path.cwd()).resolve()
    if not pattern or not hits:
        return {"added": 0}
    try:
        with d._store_lock:
            result = _learn_grep_hits(d.store, pattern, hits, project_root)
    except Exception as exc:  # noqa: BLE001 — classified below
        if not Daemon._is_fatal_invalidation(exc):
            raise
        # A READ surface (every `rmx grep` miss, incl. the PreToolUse rewrite)
        # must never take the daemon down: degrade, name it, queue the repair
        # for boot (plan-4 task 4.1). Write ops keep the fast-exit.
        d._log(f"learn skipped: store invalid ({exc!r}); repair queued")
        d._mark_repair_needed("entities", op="learn_from_grep")
        return {"added": 0, "skipped": "store-invalid"}
    d._request_snapshot()
    return result


def _op_set_flag(d: Daemon, args: dict) -> dict:
    """Set the `protected` or `noise` flag on entities matched by selector
    (names / like / namespace / kind), in the caller's partition. Writes a
    replayable event per row."""
    flag = args["flag"]
    value = bool(args.get("value"))
    part = args.get("partition") or d._st()._partition_name
    sel = {k: args.get(k) for k in ("names", "like", "namespace", "kind")}
    with d._store_lock, d._st().with_partition(part):
        result = d._st().set_flag_by_selector(flag, value, **sel)
    d._request_snapshot()
    return result


def _op_forget(d: Daemon, args: dict) -> dict:
    """Purge entities matched by selector (names / like / namespace / kind) in
    the caller's partition — drops the row + bitmaps + linkages + Lance vector,
    tombstone-logged. `dry_run` previews the matched names."""
    part = args.get("partition") or d._st()._partition_name
    dry_run = bool(args.get("dry_run"))
    sel = {k: args.get(k) for k in ("names", "like", "namespace", "kind")}
    with d._store_lock, d._st().with_partition(part):
        result = d._st().forget_by_selector(dry_run=dry_run, **sel)
    if not dry_run:
        d._request_snapshot()
    return result


def _op_untrack(d: Daemon, args: dict) -> dict:
    """Untrack tracked_files matching a path glob (or an explicit path list) in
    the caller's partition, purging the entities anchored there. Unlike
    `vacuum`, this works on paths that still exist on disk. `dry_run`
    previews."""
    part = args.get("partition") or d._st()._partition_name
    dry_run = bool(args.get("dry_run"))
    with d._store_lock, d._st().with_partition(part):
        result = d._st().untrack_by_path(
            like=args.get("like"), paths=args.get("paths"), dry_run=dry_run,
        )
    if not dry_run:
        d._request_snapshot()
    return result


def _op_clear_tracked_stamps(d: Daemon, args: dict) -> dict:
    """Drop the ingest mtime stamps for the caller's partition without
    touching entities, so the next ingest re-derives every file. `like` scopes
    it to one subtree."""
    part = args.get("partition") or d._st()._partition_name
    with d._store_lock, d._st().with_partition(part):
        result = d._st().clear_tracked_stamps(like=args.get("like"))
    d._request_snapshot()
    return result


def _op_compile_pairs(d: Daemon, args: dict) -> dict:
    """Compile the df-filtered pair inventory for the caller's partition
    (see Store.compile_pairs). Heavy corpus scan; runs under the writer lock
    because it replaces the partition's pair_index wholesale."""
    part = args.get("partition") or d._st()._partition_name
    with d._store_lock, d._st().with_partition(part):
        result = d._st().compile_pairs(min_df=int(args.get("min_df", 3)))
    d._request_snapshot()
    return result


def _op_coref_link(d: Daemon, args: dict) -> dict:
    """Cross-doc coref pass for the caller's partition (see
    Store.link_cross_doc_coref). Needs a compiled pair_index."""
    part = args.get("partition") or d._st()._partition_name
    with d._store_lock, d._st().with_partition(part):
        result = d._st().link_cross_doc_coref(
            min_shared=int(args.get("min_shared", 2)))
    d._request_snapshot()
    return result


def _op_merge_verb_aliases(d: Daemon, args: dict) -> dict:
    """Fold legacy snake-case linkage verbs into their kebab canonical across
    the whole store (relational forward index + per-partition bitmaps +
    linkage_type), in-process under the writer lock — so a supervised daemon
    never has to be stopped. Idempotent; snapshot refreshed on any merge."""
    from refmatrix.store import _VERB_ALIASES
    results = []
    with d._store_lock:
        for legacy, canon in _VERB_ALIASES.items():
            results.append(d._st().merge_verb_alias(legacy, canon))
    if any(r["merged"] for r in results):
        # merge_verb_alias rewrites the forward index + bitmaps with direct
        # SQL and no log events; snapshot the log so replay stays faithful.
        d._compact_factslog_if_needed(force=True)
        d._request_snapshot()
    return {"results": results}


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
    _q_part = args.get("partition") or d._st()._partition_name
    with d._store_lock, d._st().with_partition(_q_part):
        qe = QueryEngine(d._st(), include_noise=include_noise, strict=strict)
        result = qe.run_pql(expr) if is_pql else qe.run(expr)
        if name_filter:
            from pyroaring import BitMap
            matching = BitMap(
                r[0] for r in d._st()._connect().execute(
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
                e = d._st().get_entity_by_id(eid)
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
            e = d._st().get_entity_by_id(eid)
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
                ev_rows = d._st()._connect().execute(
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
    degree = int(args.get("degree", 0))
    include_sessions = bool(args.get("include_sessions", False))
    expand = int(args.get("expand", 0))
    hit_lines = args.get("hit_lines", "first")
    grep_backstop = bool(args.get("grep_backstop", True))
    entities_explicit = bool(args.get("entities_explicit", False))
    tokens_explicit = bool(args.get("tokens_explicit", False))
    # Bind the requested partition explicitly. build_context →
    # resolve_concept_ids filters by `self._partition_id`; without this the
    # op runs on the daemon's *ambient* partition, which drifts on a
    # long-lived multi-partition daemon (every memory op enters/exits a
    # `with_partition`). The result was anchor=None for valid concepts —
    # the "graph not coming up" bug. `partition` defaults to the daemon's
    # bound name so single-partition callers are unaffected.
    _ctx_part = args.get("partition") or d._st()._partition_name
    # Same rerank stage `memory_recall` and `ann_search` carry. `context` was
    # symbolic-only, so a surface that already scored well on recall was
    # ordering purely by BM25. Resolved OUTSIDE the store lock: building the
    # reranker can spawn or connect to a worker, and that must not queue
    # behind an ingest holding the lock.
    # getattr, not attribute access: `_op_context` is called with lightweight
    # stub daemons in tests and by callers that never built the model
    # machinery. A read op must not hard-require the rerank stage to exist.
    _ctx_rr = None
    if getattr(d, "_maybe_rerank", None) and d._maybe_rerank(args):
        try:
            _ctx_rr = d._reranker()
        except Exception as exc:
            d._log(f"context rerank unavailable: {exc!r}")
    with d._store_lock, d._st().with_partition(_ctx_part):
        bundle = build_context(
            d._st(), ref,
            linkages=linkages,
            max_entities=max_entities,
            max_tokens=max_tokens,
            fuse=fuse,
            strict=strict,
            degree=degree,
            include_sessions=include_sessions,
            expand=expand,
            hit_lines=hit_lines,
            grep_backstop=grep_backstop,
            reranker=_ctx_rr,
            _entities_explicit=entities_explicit,
            _tokens_explicit=tokens_explicit,
        )
    body = render_json(bundle) if fmt == "json" else render_text(bundle)
    # Self-heal: if the grep backstop fired (index missed, grep hit), fold the
    # hits into a protected `query/<ref>` concept so the next query hits the
    # index — and survives prune_noise. We hold the writer here (daemon); the
    # read-only replica/CLI path just displays the floor, never learns.
    grep_entries = bundle.groups.get("grep") or []
    if grep_backstop and grep_entries:
        hits = []
        for ge in grep_entries:
            path = ge.entity.path
            if not path:
                continue
            for ln in (ge.lines or ([ge.line] if ge.line is not None else [])):
                hits.append({"file": path, "line": ln})
        if hits:
            try:
                with d._store_lock:
                    _learn_grep_hits(d._st(), ref, hits, d._st().root.parent)
                d._request_snapshot()
            except Exception as exc:  # learning is best-effort; never fail a read
                d._log(f"context grep-learn skipped: {exc}")
    return {"body": body}


def _op_describe(d: Daemon, args: dict) -> dict:
    """Full metadata dump for ONE entity: resolve the ref, then join every
    catalog fact about it. Read-only, so it runs on the read store like the
    other CLI reads (see `_op_memory_get` for the isolation rationale)."""
    ref = args.get("ref")
    if ref is None:
        raise ValueError("describe requires 'ref'")
    partition = args.get("partition") or d._st()._partition_name
    kwargs = {
        "evidence_limit": int(args.get("evidence_limit", 20)),
        "edge_limit": int(args.get("edge_limit", 200)),
        "sibling_limit": int(args.get("sibling_limit", 200)),
        "include_vectors": bool(args.get("include_vectors", True)),
    }

    def _run(s):
        targets = s.find_describe_targets(str(ref))
        if not targets:
            return {"found": None, "candidates": []}
        if len(targets) > 1 and not args.get("first"):
            return {"found": None, "candidates": targets}
        return {"found": s.describe_entity(targets[0]["id"], **kwargs),
                "candidates": targets}

    return _read_with_fallback(d, partition, _run)


def _memory_partition(d: "Daemon", args: dict) -> str:
    """Resolve which partition this memory op targets. Caller passes
    `partition` explicitly; absent, we fall back to the daemon's bound
    partition. The daemon binds for code-sync writes; memory ops
    normally land in `intuition` via explicit pass-through from the
    CLI, but we honor whatever the caller asked for."""
    return args.get("partition") or d._st()._partition_name


def _op_memory_add(d: Daemon, args: dict) -> dict:
    """Upsert a memory entity + its sidecar content. ADR-0001 Phase B."""
    name = args["name"]
    content = args["content"]
    mtype = args.get("mtype") or "observation"
    tags = args.get("tags")
    metadata = args.get("metadata")
    protected = bool(args.get("protected", False))
    with d._store_lock, d._st().with_partition(_memory_partition(d, args)):
        eid = d._st().add_memory(
            name=name, content=content, mtype=mtype,
            tags=tags, metadata=metadata, protected=protected,
        )
    d._request_snapshot()
    return {"id": eid}


def _read_with_fallback(d: Daemon, partition: str, fn):
    """Run `fn(store)` against the fastest available read path.

    Resolution (per `_open_read_store`): in-memory mirror → snapshot
    file Store → shared writer connection under `_store_lock`.

    When `_open_read_store` returns the in-memory mirror Store, the
    DuckDB connection is shared across all callers, so `fn` must run
    under the mirror's `_use_lock` to keep cursors serialized.
    """
    rs = d._open_read_store(partition)
    if rs is not None:
        mirror = getattr(d, "_mem_mirror", None)
        use_lock = (
            mirror.acquire_use()
            if mirror is not None and mirror.borrow() is rs
            else None
        )
        try:
            if use_lock is not None:
                with use_lock:
                    return fn(rs)
            return fn(rs)
        finally:
            try:
                rs.close()
            except Exception:
                pass
    # Fallback: serialize under the write lock so the swap can't close
    # the connection mid-cursor.
    with d._store_lock, d._st().with_partition(partition):
        return fn(d.store)


def _op_memory_get(d: Daemon, args: dict) -> dict:
    """Fetch a memory by name (active partition) or id (any partition).

    Routes through a dedicated read-only DuckDB connection
    (`_open_read_store`) so reads run concurrently with ingest writes
    AND with the periodic replica swap. The swap closes the WRITER
    connection; the reader has its own connection at the same slot
    and stays valid for the duration of the op."""
    target = args.get("name") if args.get("name") is not None else args.get("id")
    if target is None:
        raise ValueError("memory_get requires 'name' or 'id'")
    m = _read_with_fallback(
        d, _memory_partition(d, args),
        lambda s: s.get_memory(target),
    )
    return {"memory": m}


def _op_memory_iter(d: Daemon, args: dict) -> dict:
    """Stream memories in the active partition. Optional mtype + tags filter.
    See `_op_memory_get` for the read-isolation rationale."""
    mtype = args.get("mtype")
    limit = args.get("limit")
    tags = args.get("tags")
    tags_match = args.get("tags_match", "all")
    rows = _read_with_fallback(
        d, _memory_partition(d, args),
        lambda s: list(s.iter_memories(
            mtype=mtype, limit=limit, tags=tags, tags_match=tags_match)),
    )
    return {"rows": rows}


def _op_memory_search(d: Daemon, args: dict) -> dict:
    """Substring search over memory name + content, optional tags filter.
    Returns at most `limit` rows newest-first. See `_op_memory_get` for the
    read-isolation rationale."""
    query = args["query"]
    limit = int(args.get("limit", 20))
    tags = args.get("tags")
    tags_match = args.get("tags_match", "all")
    rows = _read_with_fallback(
        d, _memory_partition(d, args),
        lambda s: s.search_memories(
            query, limit=limit, tags=tags, tags_match=tags_match),
    )
    return {"rows": rows}


def _op_memory_recent(d: Daemon, args: dict) -> dict:
    """Phase C2: most recent memories within an optional `since_seconds`
    window, newest first, optional tags filter. Routed through the daemon so
    the in-process Store can't deadlock against the daemon's DuckDB write lock.
    See `_op_memory_get` for the read-isolation rationale."""
    since = args.get("since_seconds")
    limit = int(args.get("limit", 20))
    tags = args.get("tags")
    tags_match = args.get("tags_match", "all")
    rows = _read_with_fallback(
        d, _memory_partition(d, args),
        lambda s: s.recent_memories(
            since_seconds=since, limit=limit, tags=tags, tags_match=tags_match),
    )
    return {"rows": rows}


def _op_memory_forget(d: Daemon, args: dict) -> dict:
    """Delete a memory entity, its sidecar, and every entity_link it owns."""
    target = args.get("name") if args.get("name") is not None else args.get("id")
    if target is None:
        raise ValueError("memory_forget requires 'name' or 'id'")
    with d._store_lock, d._st().with_partition(_memory_partition(d, args)):
        ok = d._st().forget_memory(target)
    d._request_snapshot()
    return {"forgotten": ok}


def _op_memory_retag(d: Daemon, args: dict) -> dict:
    """Mutate a memory's tags (add/remove/replace). Returns the new tags."""
    target = args.get("name") if args.get("name") is not None else args.get("id")
    if target is None:
        raise ValueError("memory_retag requires 'name' or 'id'")
    with d._store_lock, d._st().with_partition(_memory_partition(d, args)):
        new = d._st().retag_memory(
            target, add=args.get("add"), remove=args.get("remove"),
            replace=args.get("replace"),
        )
    d._request_snapshot()
    return {"tags": new}


def _op_memory_facets(d: Daemon, args: dict) -> dict:
    """Distinct mtypes + tags (with counts) for the UI filter dropdowns."""
    return _read_with_fallback(
        d, _memory_partition(d, args), lambda s: s.memory_facets())


def _op_memory_reclassify(d: Daemon, args: dict) -> dict:
    """Bulk-change memory mtype in a partition (selector: like/names/from_mtype)."""
    with d._store_lock, d._st().with_partition(_memory_partition(d, args)):
        res = d._st().reclassify_memories(
            to_mtype=args["to_mtype"], like=args.get("like"),
            names=args.get("names"), from_mtype=args.get("from_mtype"),
            dry_run=bool(args.get("dry_run")),
        )
    if not args.get("dry_run"):
        d._request_snapshot()
    return res


def _op_memory_dedup(d: Daemon, args: dict) -> dict:
    """Fold concept↔memory duplicate nodes in a partition (pre-0.7.6 debt)."""
    with d._store_lock, d._st().with_partition(_memory_partition(d, args)):
        result = d._st().fold_concept_dups(dry_run=bool(args.get("dry_run")))
    if not args.get("dry_run"):
        d._request_snapshot()
    return result


def _op_memory_bulk_forget(d: Daemon, args: dict) -> dict:
    """Bulk-delete memory rows by ids / names / mtypes (union semantics).

    Args:
        ids: list of entity-ids to forget (global; partition-agnostic).
        names: list of memory names to resolve within the active partition.
        mtypes: list of sidecar mtypes; every memory matching any of them
            in the active partition is purged. Drives the 271-card
            session-card cleanup on viascope (mtypes=[session-request,
            session-milestone]).
        dry_run: resolve the id set + per-mtype counts WITHOUT deleting.
        partition: override the daemon's bound partition (memory ops are
            usually scoped to `memory-<project>` even when the daemon
            owns the code-sync partition).

    Returns Store.bulk_forget_memories' shape: {forgotten, ids, by_mtype,
    dry_run}.
    """
    if (
        not args.get("ids")
        and not args.get("names")
        and not args.get("mtypes")
    ):
        raise ValueError(
            "memory_bulk_forget requires at least one of "
            "'ids', 'names', 'mtypes'"
        )
    dry_run = bool(args.get("dry_run"))
    with d._store_lock, d._st().with_partition(_memory_partition(d, args)):
        result = d._st().bulk_forget_memories(
            ids=args.get("ids"),
            names=args.get("names"),
            mtypes=args.get("mtypes"),
            dry_run=dry_run,
        )
    if not dry_run and result.get("forgotten", 0) > 0:
        d._request_snapshot()
    return result


def _op_memory_score(d: Daemon, args: dict) -> dict:
    """Phase B5: per-concept reinforcement signal. Returns the signed
    score (clamped to ±cap) plus the contributing concept_ids so the
    caller can render --explain."""
    name = args["concept"]
    halflife = args.get("halflife_days")
    cap = args.get("cap")
    explain = bool(args.get("explain", False))
    with d._st().with_partition(_memory_partition(d, args)):
        cids = d._st().resolve_concept_ids(name, strict=False)
        if not cids:
            return {"concept": name, "concept_ids": [], "signal": 0.0,
                    "components": []}
        scores = d._st().reinforcement_scores(
            cids, halflife_days=halflife, cap=cap,
        )
        components: list[dict] = []
        if explain:
            for cid in cids:
                components.extend({
                    "concept_id": cid,
                    **row,
                } for row in d._st().reinforcement_components(
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
    with d._store_lock, d._st().with_partition(_memory_partition(d, args)):
        m = d._st().get_memory(src)
        if m is None:
            raise ValueError(f"no memory matching {src!r}")
        cid = d._st().add_concept(concept_name)
        d._st().link(linkage, cid, m["id"], weight=weight)
    d._request_snapshot()
    return {"src_id": m["id"], "concept_id": cid}


def _op_subject_upsert(d: Daemon, args: dict) -> dict:
    """Upsert a durable subject node (ADR-0002) in the memory partition."""
    label = args["label"]
    with d._store_lock, d._st().with_partition(_memory_partition(d, args)):
        rec = d._st().upsert_subject(label)
    d._request_snapshot()
    return rec


def _op_subject_link(d: Daemon, args: dict) -> dict:
    """File a leaf memory under a subject via a `part-of` edge."""
    leaf_id = int(args["leaf_id"])
    subject_id = int(args["subject_id"])
    with d._store_lock, d._st().with_partition(_memory_partition(d, args)):
        created = d._st().link_part_of(leaf_id, subject_id)
    d._request_snapshot()
    return {"linked": created}


def _op_memory_compile_apply(d: Daemon, args: dict) -> dict:
    """Write a `memory compile` plan: subject nodes + `part-of` edges.

    Only the APPLY half runs here. The clustering itself stays in the caller
    because it reads the whole vector matrix, and the daemon is the process
    that gets jetsammed when it grows fat — the plan arrives as data.
    """
    from refmatrix import consolidate

    plan = args["plan"]
    prune = bool(args.get("prune", True))
    with d._store_lock, d._st().with_partition(_memory_partition(d, args)):
        result = consolidate.apply_plan(d._st(), plan, prune=prune)
    d._request_snapshot()
    return result


def _op_subject_list(d: Daemon, args: dict) -> dict:
    """Subject nodes with leaf counts (read-routed)."""
    rows = _read_with_fallback(
        d, _memory_partition(d, args), lambda s: s.list_subjects())
    return {"rows": rows}


def _op_subject_leaves(d: Daemon, args: dict) -> dict:
    """The memories filed under a subject (read-routed)."""
    target = args["subject"]
    rows = _read_with_fallback(
        d, _memory_partition(d, args), lambda s: s.subject_leaves(target))
    return {"rows": rows}


def _op_stop(d: Daemon, args: dict) -> dict:
    d._stop = True
    return {"stopping": True}


def _op_repair_entities(d: Daemon, args: dict) -> dict:
    """In-band entities rebuild (`rmx repair-index --entities`). Under the
    writer lock; clears `repair.needed` on success. If the store is already
    invalidated (a fatal fired), DuckDB refuses every statement until the
    process restarts — restart the daemon and boot runs the repair."""
    from refmatrix.store import RepairAbort
    try:
        with d._store_lock:
            rep = d.store.rebuild_entities_indexes()
    except RepairAbort as e:
        return {"ok": False, "error": f"repair aborted: {e}"}
    repair_marker_path(d.root).unlink(missing_ok=True)
    d._repair_needed = None
    d._log(f"repaired entities (op) rows={rep['rows']} indexes={rep['indexes']}")
    d._request_snapshot()
    return rep


def _op_replica_refresh(d: Daemon, args: dict) -> dict:
    """Force an immediate snapshot of primary → replica .duckdb file."""
    result = d._refresh_replica_now()
    d._request_snapshot()
    return result


def _op_replica_relink(d: Daemon, args: dict) -> dict:
    """Re-point `read_only.duckdb` at the true reader (non-writer) slot.

    Deliberately does NOT take `_store_lock`: `_refresh_read_only_link`
    only touches the symlink (derived from `store.db_path`), so this is
    safe to run even while the daemon is mid-operation. It's the recovery
    op a replica reader calls after hitting a lock conflict because the
    symlink had transiently drifted onto the writer slot."""
    d._refresh_read_only_link()
    reader = d._reader_slot()
    return {"ok": True, "reader_slot": reader,
            "reader_path": str(d._replica_file(reader))}


def _op_replica_audit(d: Daemon, args: dict) -> dict:
    """Drift detector: per-table row diff + entity collision counts across
    both rotation slots. Runs INSIDE the daemon because DuckDB refuses any
    other in-process connection to the writer-locked slot file. We borrow
    the store's existing writer connection (its main DB is the writer
    slot) and ATTACH the other slot read-only on it for the comparison."""
    from refmatrix import replica_merge as rm
    if d.store is None or d.store._backend.kind != "duckdb":
        return {"enabled": False, "reason": "non-duckdb backend"}
    a_path = d._replica_file("A")
    b_path = d._replica_file("B")
    if not (a_path.exists() and b_path.exists()):
        return {"enabled": True, "ok": False,
                "error": f"missing slot file: a_exists={a_path.exists()} "
                         f"b_exists={b_path.exists()}"}
    # Hold the store lock so the refresh thread can't swap slots or
    # close the reader file out from under our ATTACH mid-audit.
    with d._store_lock:
        writer_slot = d._writer_slot_from_store() or d._active_slot or "A"
        reader_slot = "B" if writer_slot == "A" else "A"
        reader_path = d._replica_file(reader_slot)
        try:
            report = rm.audit_via_writer(
                d.store._connect()._duck,
                writer_slot=writer_slot,
                reader_path=reader_path,
                reader_slot=reader_slot,
            )
        except Exception as exc:
            return {"enabled": True, "ok": False, "error": f"audit: {exc!r}"}
    report["enabled"] = True
    report["ok"] = True
    return report


def _op_replica_merge(d: Daemon, args: dict) -> dict:
    """Merge slots A and B into one canonical catalog and atomically install
    it on both slots. Drift recovery for unlogged-write data loss.

    Args:
        dry_run: build the merge plan + counts without writing the catalog.

    Holds `_store_lock` (writer + readers blocked) for the whole merge.
    Drains in-flight read-replica connections via `_swap_gate` before
    closing the writer. On success: writer reopens on slot A, reader
    symlink repoints at slot B, both offset files point at the
    end-of-log byte position the merge captured."""
    from refmatrix import replica_merge as rm
    import shutil as _shutil

    if d.store is None or d.store._backend.kind != "duckdb":
        return {"enabled": False, "reason": "non-duckdb backend"}
    dry_run = bool(args.get("dry_run"))

    a_path = d._replica_file("A")
    b_path = d._replica_file("B")
    if not (a_path.exists() and b_path.exists()):
        return {"enabled": True, "ok": False,
                "error": f"missing slot file: a_exists={a_path.exists()} "
                         f"b_exists={b_path.exists()}"}

    t0 = time.monotonic()

    # Both dry-run and real merge have to close the writer first, because
    # the merge SQL opens fresh connections to BOTH slot files and DuckDB
    # refuses an in-process second connection (read-only or otherwise) to
    # the file the writer's lock is held on.

    # Drain readers via the swap gate, take the store lock for the
    # duration, close the writer, do the merge on a temp file. For real
    # merge: swap into both slots. For dry-run: discard temp.
    with d._swap_gate:
        wait_start = time.monotonic()
        while d._read_inflight > 0 and (time.monotonic() - wait_start) < 30.0:
            d._swap_gate.wait(timeout=5.0)
        if d._read_inflight > 0:
            return {"enabled": True, "ok": False,
                    "error": f"readers still in flight ({d._read_inflight}) "
                             f"after 30s; aborting merge"}

    with d._store_lock:
        # 1. Quiesce writer.
        try:
            d.store._connect().execute("CHECKPOINT")
            d.store.flush_fragments()
        except Exception as exc:
            return {"enabled": True, "ok": False,
                    "error": f"pre-merge checkpoint: {exc!r}"}

        # Snapshot log end-offset BEFORE we close the writer so the post-
        # merge offset reset reflects the on-disk state baked into the
        # merged catalog.
        try:
            log_end_offset = (
                d.store.log_path.stat().st_size
                if d.store.log_path.exists() else 0
            )
        except OSError:
            log_end_offset = 0

        prev_writer = d._writer_slot_from_store() or d._active_slot or "A"

        try:
            Daemon._force_close_store(d.store)
        except Exception:
            pass

        # Move any reader symlinks off the slots BEFORE we overwrite them.
        # The merged file will sit on both slots; we re-link to B once the
        # store has reopened on A.
        tmp_link = d.root / "read_only.duckdb"
        try:
            if tmp_link.exists() or tmp_link.is_symlink():
                tmp_link.unlink()
        except OSError as exc:
            d._log(f"merge: unlink read_only.duckdb: {exc!r}")

        # 2. Build merged catalog at a temp path. dry_run still writes the
        # file (it's the only way to get accurate counts) — we just delete
        # it before reopening the writer.
        tmp_target = d.root / "catalog.merge.tmp.duckdb"
        try:
            report = rm.merge_slots(a_path, b_path, tmp_target)
        except Exception as exc:
            try:
                d.store = Store(d.root, partition=d.partition)
                d.store.db_path = d._replica_file(prev_writer)
                d.store.init()
                d._active_slot = prev_writer
                d._refresh_read_only_link()
            except Exception as rexc:
                d._log(f"merge: failed AND reopen failed: {rexc!r}")
            return {"enabled": True, "ok": False,
                    "error": f"merge build: {exc!r}"}

        if dry_run:
            # Throw away the merged file; reopen the prior writer slot.
            try:
                if tmp_target.exists():
                    tmp_target.unlink()
            except OSError as exc:
                d._log(f"dry_run: unlink tmp_target: {exc!r}")
            try:
                d.store = Store(d.root, partition=d.partition)
                d.store.db_path = d._replica_file(prev_writer)
                d.store.init()
                d._active_slot = prev_writer
                d._refresh_read_only_link()
            except Exception as exc:
                return {"enabled": True, "ok": False,
                        "error": f"dry_run reopen: {exc!r}"}
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            report["enabled"] = True
            report["ok"] = True
            report["dry_run"] = True
            report["writer_slot"] = prev_writer
            report["reader_slot"] = "B" if prev_writer == "A" else "A"
            report["log_end_offset"] = log_end_offset
            report["elapsed_ms_total"] = elapsed_ms
            return report

        # 3. Atomic swap: replace BOTH slots with the merged file. Use
        # os.replace for atomicity within a filesystem. Drop stale .wal
        # files on both slots so DuckDB sees a clean snapshot.
        try:
            for slot in ("A", "B"):
                slot_path = d._replica_file(slot)
                wal_path = slot_path.with_name(slot_path.name + ".wal")
                if wal_path.exists():
                    try:
                        wal_path.unlink()
                    except OSError as exc:
                        d._log(f"merge: unlink {wal_path.name}: {exc!r}")
                if slot == "A":
                    # First slot uses os.replace from the temp file.
                    os.replace(tmp_target, slot_path)
                else:
                    # Second slot gets a fresh copy of the now-installed A.
                    _shutil.copy2(d._replica_file("A"), slot_path)
            # Reset both offset markers to the post-merge log end-offset.
            d._write_slot_offset("A", log_end_offset)
            d._write_slot_offset("B", log_end_offset)
            # Promote A as writer.
            d._active_marker().write_text("A")
            d._active_slot = "A"
        except Exception as exc:
            d._log(f"merge: swap failed: {exc!r}")
            return {"enabled": True, "ok": False,
                    "error": f"swap: {exc!r}"}

        # 4. Reopen writer on slot A.
        try:
            d.store = Store(d.root, partition=d.partition)
            d.store.db_path = d._replica_file("A")
            d.store.init()
        except Exception as exc:
            return {"enabled": True, "ok": False,
                    "error": f"post-merge reopen: {exc!r}"}

        # 5. Point read replica at B.
        d._refresh_read_only_link()

    # merge_slots wrote the union with direct SQL — zero log events — so
    # facts.log still describes a pre-merge slot. Snapshot it from the merged
    # catalog (also resets both slot offsets to the fresh EOF).
    d._compact_factslog_if_needed(force=True)

    elapsed_ms = int((time.monotonic() - t0) * 1000)
    report["enabled"] = True
    report["ok"] = True
    report["dry_run"] = False
    report["writer_slot"] = "A"
    report["reader_slot"] = "B"
    report["log_end_offset"] = log_end_offset
    report["elapsed_ms_total"] = elapsed_ms
    return report


def _op_replica_status(d: Daemon, args: dict) -> dict:
    """Report rotation state: writer + reader slots, file paths + sizes,
    last-refresh timestamp + latency, refresh-thread liveness."""
    enabled = d.store is not None and d.store._backend.kind == "duckdb"
    # Authoritative writer = the slot the store is actually open on;
    # the `active` marker can drift behind a swap that failed to persist.
    active = (d._writer_slot_from_store()
              or getattr(d, "_active_slot", None)
              or d._read_active_slot())
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
            (_rt := getattr(d, "_replica_thread", None)) is not None
            and _rt.is_alive()
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
    # Honor a caller-specified partition so embed lands in the same slot
    # ann_search will later read from. Without this, vectors land in the
    # daemon's bound startup partition regardless of `-p` and memory
    # recall returns zero hits even after a "successful" rebuild.
    partition = args.get("partition") or d._st()._partition_name

    with d._store_lock, d._st().with_partition(partition):
        if rebuild:
            # `pending_embeddings` already skips current rows; for a
            # rebuild we ask the catalog directly so the WHERE clause
            # matches every row of the selected kinds.
            con = d._st()._connect()
            in_list = ",".join("?" * len(kinds))
            rows = con.execute(
                f"SELECT id, kind, name FROM entities "
                f"WHERE partition_id = ? AND kind IN ({in_list}) "
                f"ORDER BY id LIMIT ?",
                [d._st()._partition_id, *kinds, limit],
            ).fetchall()
            rows = [(r[0], r[1], r[2]) for r in rows]
        else:
            rows = d._st().pending_embeddings(kinds=kinds, limit=limit)

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
            d._st().upsert_vector(eids, sub, kind=kind, dim=emb.dim)
            embedded += len(eids)
        remaining = len(d._st().pending_embeddings(kinds=kinds, limit=1))

    d._request_snapshot()
    return {
        "embedded": embedded,
        "remaining": remaining,
        "kinds": kinds,
        "dim": emb.dim,
        "model": emb.model_name,
    }


def _op_embed_gc(d: Daemon, args: dict) -> dict:
    """Drop lance vectors whose entity_id is absent from the catalog for
    the (partition, kind) pair. Pairs with `forget` / `purge` ops that
    delete catalog rows without touching the dense layer."""
    try:
        emb = d._embedder()
    except ImportError as exc:
        return {"ok": False, "error": f"dense extra not installed: {exc}"}

    kinds = args.get("kinds")
    if kinds is not None and not isinstance(kinds, list):
        kinds = list(kinds)
    dry_run = bool(args.get("dry_run"))
    partition = args.get("partition") or d._st()._partition_name

    with d._store_lock, d._st().with_partition(partition):
        result = d._st().gc_vectors(
            kinds=kinds, dim=emb.dim, dry_run=dry_run,
        )
    if not dry_run:
        d._request_snapshot()
    return {"by_kind": result, "partition": partition, "dim": emb.dim}


def _prefilter_enabled(args: dict) -> bool:
    """Cull the dense candidate pool with the query's own concepts. Per-call
    `prefilter` arg wins; otherwise RMX_RECALL_PREFILTER (default off until
    measured)."""
    want = args.get("prefilter")
    if want is not None:
        return bool(want)
    return os.environ.get("RMX_RECALL_PREFILTER", "0") not in (
        "0", "false", "False")


def _op_promote_edges(d: "Daemon", args: dict) -> dict:
    """Promote recurring STM co-occurrence into durable LTM `co-occurs` edges.

    A write op, so it runs under `_store_lock` on the single writer — the same
    control point every other mutation goes through. Defaults to dry_run: the
    caller has to ask to mutate the graph.
    """
    from refmatrix.promote import promote_focus_edges

    dry_run = args.get("dry_run")
    dry_run = True if dry_run is None else bool(dry_run)
    partition = args.get("partition") or d._st()._partition_name
    with d._store_lock, d._st().with_partition(partition):
        res = promote_focus_edges(
            d.store, d.root,
            session=args.get("session"),
            threshold=args.get("threshold"),
            max_edges=int(args.get("max_edges") or 200),
            dry_run=dry_run,
        )
    if not dry_run and res.get("promoted"):
        d._request_snapshot()
    # The pair list can be long; the caller asked for a count plus a sample.
    sample = int(args.get("sample") or 20)
    res["pairs"] = res.get("pairs", [])[:sample]
    return res


def _apply_rerank_safe(d: "Daemon", query: str, docs, k: int):
    """Run the cross-encoder stage, or return None to keep retrieval order.

    Every failure mode degrades rather than raises: no [dense] extra, a
    worker that died twice, a model that will not load. Reranking is a
    precision refinement on an answer we already have — it must never be
    the reason a recall returns nothing.
    """
    from refmatrix.reranker import apply_rerank

    scored, untexted, tail = docs
    if not scored:
        # Worth a line. Without it, "rerank is enabled" is unfalsifiable from
        # the logs: a partition whose rows have no extractable body silently
        # returns retrieval order forever and looks identical to rerank being
        # off. Cheap -- it fires only when the whole shortlist was untexted.
        d._log(
            f"rerank skipped: no extractable text in the shortlist "
            f"({len(untexted)} untexted, {len(tail)} beyond pool)"
        )
        return None
    try:
        rr = d._reranker()
    except ImportError as exc:
        d._log(f"rerank skipped (dense extra missing): {exc}")
        return None
    except Exception as exc:
        d._log(f"rerank skipped (reranker unavailable): {exc!r}")
        return None
    try:
        return apply_rerank(rr, query, scored, untexted, tail, k=k)
    except Exception as exc:
        d._log(f"rerank failed, keeping retrieval order: {exc!r}")
        return None


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
            daemon bound to its project partition can still serve hybrid
            memory queries. Lance datasets live at
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
        assert query is not None  # the vector-or-query check above returned
        v = emb.embed_texts([query])[0]
    else:
        import numpy as np
        v = np.asarray(vector, dtype="float32")
        if v.shape[0] != emb.dim:
            return {
                "ok": False,
                "error": f"vector dim {v.shape[0]} != model dim {emb.dim}",
            }

    want_rerank = d._maybe_rerank(args) and bool(query)
    # Over-fetch before reranking: the stage can only reorder what retrieval
    # already returned, so a true hit sitting at rank 30 of a k=10 request is
    # unreachable unless the pool is widened here.
    from refmatrix.reranker import DEFAULT_POOL_MULT, MAX_POOL
    ann_k = min(max(k, k * DEFAULT_POOL_MULT), MAX_POOL) if want_rerank else k
    docs = None

    with d._store_lock:
        hits = d._st().ann_search(
            v, k=ann_k, dim=emb.dim, kinds=kinds, partition=partition,
        )
        if want_rerank:
            from refmatrix.reranker import collect_rerank_docs
            try:
                docs = collect_rerank_docs(d.store, hits, k=k)
            except Exception as exc:
                d._log(f"rerank doc collect failed: {exc!r}")
                docs = None

    if want_rerank and docs is not None:
        assert query is not None  # want_rerank requires bool(query)
        # Model call OUTSIDE _store_lock -- see collect_rerank_docs.
        reranked = _apply_rerank_safe(d, query, docs, k)
        if reranked is not None:
            return {"hits": [{"id": eid, "score": sc, "reranked": True}
                             for eid, sc in reranked]}

    return {"hits": [{"id": eid, "distance": dist} for eid, dist in hits[:k]]}


def _op_memory_recall(d: Daemon, args: dict) -> dict:
    """Hybrid memory recall: dense ANN ⊕ symbolic content_rank, RRF-fused —
    the lexical side the pure-dense `ann_search` op lacks. `fuse=False` falls
    back to pure dense. Runs under `with_partition` so content_rank (DuckDB,
    partition-scoped) and the Lance ANN both target the requested memory
    partition. Fused hits carry an RRF `score` (higher = better); dense hits
    carry the raw L2 `distance`."""
    try:
        emb = d._embedder()
    except ImportError as exc:
        return {"ok": False, "error": f"dense extra not installed: {exc}"}
    query = args.get("query")
    if not query:
        return {"ok": False, "error": "need 'query' text"}
    k = int(args.get("k") or 20)
    kinds = args.get("kinds")
    fuse = args.get("fuse", True)
    partition = _memory_partition(d, args)

    from refmatrix.recall import dense_recall, hybrid_memory_recall

    want_rerank = d._maybe_rerank(args)
    from refmatrix.reranker import DEFAULT_POOL_MULT, MAX_POOL
    retrieve_k = min(max(k, k * DEFAULT_POOL_MULT), MAX_POOL) if want_rerank else k

    # Resolve the dense candidate cull BEFORE taking the lock. It reads the
    # concept index, which does not need the writer, and holding _store_lock
    # across it puts every other op behind a query-shaped lookup.
    _cand = None
    if _prefilter_enabled(args):
        from refmatrix.recall import concept_prefilter
        try:
            with d._st().with_partition(partition):
                _cand = concept_prefilter(d._st(), query)
        except Exception as exc:
            d._log(f"concept prefilter skipped: {exc!r}")

    with d._store_lock, d._st().with_partition(partition):
        if fuse:
            hits = hybrid_memory_recall(
                d._st(), emb, query, k=retrieve_k, kinds=kinds,
                candidate_ids=_cand)
        else:
            hits = dense_recall(d._st(), emb, query, k=retrieve_k, kinds=kinds,
                                candidate_ids=_cand)
        docs = None
        if want_rerank:
            from refmatrix.reranker import collect_rerank_docs
            try:
                docs = collect_rerank_docs(d.store, hits, k=k)
            except Exception as exc:
                d._log(f"rerank doc collect failed: {exc!r}")
                docs = None

    if want_rerank and docs is not None:
        reranked = _apply_rerank_safe(d, query, docs, k)
        if reranked is not None:
            return {"hits": [{"id": eid, "score": sc, "fused": bool(fuse),
                              "reranked": True}
                             for eid, sc in reranked]}

    hits = hits[:k]
    if fuse:
        return {"hits": [{"id": eid, "score": sc, "fused": True}
                         for eid, sc in hits]}
    return {"hits": [{"id": eid, "distance": dist} for eid, dist in hits]}


def _op_part_ctx(d: "Daemon", args: dict):
    """Optional per-op partition override, mirroring the memory ops.

    Returns a context manager: the requested partition when `args` carries
    one, else a no-op so the daemon's bound partition stands. Lets a CLI
    process that resolved a different `-p` than the daemon's startup
    partition route a write to the correct partition."""
    import contextlib
    p = args.get("partition")
    return d._st().with_partition(p) if p else contextlib.nullcontext()


def _op_link(d: Daemon, args: dict) -> dict:
    """Create a typed concept->entity edge. Routes `rmx link` through the
    daemon so the catalog write-lock stays single-owner."""
    with d._store_lock, _op_part_ctx(d, args):
        created = d._st().link(
            args["linkage"], int(args["concept_id"]), int(args["entity_id"]),
            weight=args.get("weight"), protect=bool(args.get("protect", False)),
        )
    d._request_snapshot()
    return {"created": bool(created)}


def _op_unlink(d: Daemon, args: dict) -> dict:
    """Remove a typed concept->entity edge (`rmx unlink`)."""
    with d._store_lock, _op_part_ctx(d, args):
        removed = d._st().unlink(
            args["linkage"], int(args["concept_id"]), int(args["entity_id"]),
        )
    d._request_snapshot()
    return {"unlinked": bool(removed)}


def _op_link_canon(d: Daemon, args: dict) -> dict:
    """Wire a local concept to a canonical hub in another partition
    (`rmx canon link`). The canon-partition Store opened inside link_canon
    is same-process as the daemon, so DuckDB permits the second connection
    (the lock conflict is only cross-process)."""
    with d._store_lock, _op_part_ctx(d, args):
        canon_id = d._st().link_canon(
            int(args["local_concept_id"]),
            args["canon_partition"], args["canon_concept_name"],
        )
    d._request_snapshot()
    return {"canon_id": canon_id}


def _op_save_query(d: Daemon, args: dict) -> dict:
    """Persist a named saved query (`rmx save-query`)."""
    with d._store_lock, _op_part_ctx(d, args):
        d._st().save_query(args["name"], args["body"])
    d._request_snapshot()
    return {"saved": True, "name": args["name"]}


def _op_rebuild_index(d: Daemon, args: dict) -> dict:
    """Replay facts.log into the daemon's own catalog (wipe + rebuild) —
    the same machinery the daemon runs on startup repair, held under the
    write lock so nothing races the rebuild."""
    with d._store_lock:
        result = d._st().rebuild_index_from_log()
    d._request_snapshot()
    return {"result": result}


def _op_pagerank(d: Daemon, args: dict) -> dict:
    """Recompute the global PageRank prior for a partition and persist it to
    the `pagerank` sidecar (stage 2 of scan-prompt ranking). Heavy-ish offline
    compute → bg_pool. Binds the requested partition explicitly so it doesn't
    run on the daemon's ambient (drifting) partition."""
    from refmatrix import pagerank as pr_mod
    part = args.get("partition") or d._st()._partition_name
    damping = float(args.get("damping", 0.85))
    link_weight = float(args.get("link_weight", 2.0))
    max_iter = int(args.get("max_iter", 100))
    topn = int(args.get("top", 10))
    # Read the graph under the lock...
    with d._store_lock, d._st().with_partition(part):
        adj = pr_mod.build_adjacency(d._st(), link_weight=link_weight)
    # ...but run the CPU-bound power iteration OUTSIDE the store lock. The
    # vectorized path releases the GIL during the matvec, so the daemon stays
    # responsive to pings while computing — otherwise a multi-second hold makes
    # the hub watchdog think the daemon is dead and SIGKILL-restart it mid-op.
    raw = pr_mod.pagerank(adj, damping=damping, max_iter=max_iter)
    n = len(raw)
    scores = {nid: score * n for nid, score in raw.items()}
    # ...then write + resolve top names under the lock again.
    with d._store_lock, d._st().with_partition(part):
        written = pr_mod.store_scores(d._st(), scores)
        con = d._st()._connect()
        top_named = []
        for eid, score in sorted(scores.items(), key=lambda kv: -kv[1])[:topn]:
            r = con.execute(
                "SELECT name, kind FROM entities WHERE id = ?", (int(eid),),
            ).fetchone()
            top_named.append({
                "id": int(eid), "name": r[0] if r else str(eid),
                "kind": r[1] if r else "?", "ratio": round(score, 3)})
    d._request_snapshot()
    return {"partition": part, "nodes": written, "top": top_named}


OPS: dict[str, Callable[[Daemon, dict], Any]] = {
    "ping": _op_ping,
    "pagerank_compute": _op_pagerank,
    "enqueue": _op_enqueue,
    "flush_queue": _op_flush_queue,
    "flush_queue_async": _op_flush_queue_async,
    "sync_files": _op_sync_files,
    "sync_since": _op_sync_since,
    "ingest_path": _op_ingest_path,
    "ingest_path_start": _op_ingest_path_start,
    "ingest_gmd": _op_ingest_gmd,
    "ingest_gmd_start": _op_ingest_gmd_start,
    "ingest_gmd_status": _op_ingest_gmd_status,
    "embed_start": _op_embed_start,
    "mem_mirror_status": _op_mem_mirror_status,
    "prestage_hashes": _op_prestage_hashes,
    "context": _op_context,
    "describe": _op_describe,
    "query": _op_query,
    "grep_indexed": _op_grep_indexed,
    "learn_from_grep": _op_learn_from_grep,
    "upsert_entity": _op_upsert_entity,
    "add_concept": _op_add_concept,
    "add_linkage_type": _op_add_linkage_type,
    "link": _op_link,
    "unlink": _op_unlink,
    "link_canon": _op_link_canon,
    "save_query": _op_save_query,
    "rebuild_index": _op_rebuild_index,
    "iter_entities": _op_iter_entities,
    "top_concepts": _op_top_concepts,
    "list_linkages": _op_list_linkages,
    "list_saved_queries": _op_list_saved_queries,
    "partition_add": _op_partition_add,
    "partition_list": _op_partition_list,
    "partition_rename": _op_partition_rename,
    "partition_merge": _op_partition_merge,
    "job_status": _op_job_status,
    "prune_noise": _op_prune_noise,
    "set_flag": _op_set_flag,
    "forget": _op_forget,
    "untrack": _op_untrack,
    "clear_tracked_stamps": _op_clear_tracked_stamps,
    "compile_pairs": _op_compile_pairs,
    "coref_link": _op_coref_link,
    "merge_verb_aliases": _op_merge_verb_aliases,
    "vacuum": _op_vacuum,
    "stats": _op_stats,
    "checkpoint": _op_checkpoint,
    "snapshot": _op_snapshot,
    "compact_factslog": _op_compact_factslog,
    "replica_refresh": _op_replica_refresh,
    "replica_status": _op_replica_status,
    "replica_relink": _op_replica_relink,
    "replica_audit": _op_replica_audit,
    "replica_merge": _op_replica_merge,
    "embed": _op_embed,
    "embed_gc": _op_embed_gc,
    "ann_search": _op_ann_search,
    "memory_recall": _op_memory_recall,
    "promote_edges": _op_promote_edges,
    "memory_add": _op_memory_add,
    "memory_get": _op_memory_get,
    "memory_iter": _op_memory_iter,
    "memory_search": _op_memory_search,
    "memory_recent": _op_memory_recent,
    "memory_forget": _op_memory_forget,
    "memory_retag": _op_memory_retag,
    "memory_facets": _op_memory_facets,
    "memory_reclassify": _op_memory_reclassify,
    "memory_dedup": _op_memory_dedup,
    "memory_bulk_forget": _op_memory_bulk_forget,
    "memory_link": _op_memory_link,
    "memory_score": _op_memory_score,
    "subject_upsert": _op_subject_upsert,
    "subject_link": _op_subject_link,
    "memory_compile_apply": _op_memory_compile_apply,
    "subject_list": _op_subject_list,
    "subject_leaves": _op_subject_leaves,
    "stop": _op_stop,
    "repair_entities": _op_repair_entities,
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
    "describe",
    "query",
    "grep_indexed",
    "list_linkages",
    "list_saved_queries",
    "partition_add",
    "partition_list",
    "partition_rename",
    "replica_refresh",
    "replica_status",
    "replica_relink",
    "replica_audit",
    "snapshot",
    "ann_search",
    "memory_recall",
    "memory_get",
    "memory_iter",
    "memory_search",
    "memory_recent",
    "memory_score",
    "subject_list",
    "subject_leaves",
    "ingest_gmd_status",
    "mem_mirror_status",
    "stop",
}


# ---------- daemonize -------------------------------------------------------


def spawn_daemon(root: Path, *, partition: str | None = None,
                 wait_for_ready: float | None = None,
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
    _harden_fork_safety()
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

        if wait_for_ready is None:
            # A fresh store's first boot (index repair + rotation bootstrap +
            # model-worker connects) can take >5s; the old hardcoded 5.0
            # aborted eval/cold-start spawns that were about to succeed.
            try:
                wait_for_ready = float(
                    os.environ.get("RMX_DAEMON_SPAWN_WAIT", "15") or "15")
            except ValueError:
                wait_for_ready = 15.0

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


def spawn_daemon_subprocess(
    root: Path, *, partition: str | None = None,
    watch_root: "Path | list[Path] | None" = None,
    watch_semantic: bool = False, wait_for_ready: float = 30.0,
) -> int:
    """Start the daemon for `root` as a fresh `rmx daemon start` SUBPROCESS
    instead of an in-process `os.fork`.

    For multi-threaded callers — notably the hub (watchdog + bus + queue-alert
    threads) — `os.fork` hands the child a snapshot in which every mutex held
    by another thread (malloc arena, the import lock, logging, a C-extension
    lock) stays locked forever, so the child can deadlock. That is the CPython
    "fork in a multi-threaded process may deadlock the child" hazard and the
    same class as the objc fork-safety abort. Re-launching via the CLI means
    the process that ultimately daemonizes (`spawn_daemon`) is single-threaded
    when IT forks, so the fork is safe.

    Idempotent (returns the running pid if one is already up). Blocks until the
    daemon answers ping or `wait_for_ready` elapses; returns its pid (or -1 if
    serving without a readable pidfile), else raises RuntimeError."""
    import subprocess
    import sys as _sys

    root = Path(root).resolve()
    if ping(root):
        return read_pid(root) or -1

    argv = [_sys.executable, "-m", "refmatrix.cli"]
    if partition:
        argv += ["-p", partition]
    argv += ["daemon", "start"]
    # None / [] → no file watcher (matches the hub callers' spawn_daemon use).
    if not watch_root:
        argv += ["--no-watch"]
    else:
        roots = [watch_root] if isinstance(watch_root, Path) else list(watch_root)
        for r in roots:
            argv += ["--watch-root", str(r)]
    if watch_semantic:
        argv += ["--semantic"]

    env = dict(os.environ, REFMATRIX_ROOT=str(root))
    # `rmx daemon start` blocks until the daemon is accepting connections, then
    # returns — so run it and let it daemonize. Its own fork is single-threaded
    # and safe. Output is discarded; failure surfaces via the ping check below.
    try:
        subprocess.run(
            argv, env=env, timeout=wait_for_ready + 5.0,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    except subprocess.TimeoutExpired:
        pass

    # Poll for the full readiness window after the launcher returns: under load
    # the inner `daemon start` can exit before its child has bound the socket,
    # so a short poll would spuriously fail.
    deadline = time.time() + wait_for_ready
    while time.time() < deadline:
        if ping(root):
            return read_pid(root) or -1
        time.sleep(0.1)
    raise RuntimeError(
        f"subprocess daemon did not start for {root} "
        f"within {wait_for_ready:.0f}s")


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


def _harden_fork_safety() -> None:
    """Pre-set env vars that prevent macOS libsystem_c from SIGABRT-ing
    forked children in the embedder's loky worker pool.

    Symptom this fixes: daemon dies with `EXC_CRASH / SIGABRT` and the
    crash report carries
    `asi: libsystem_c.dylib: crashed on child side of fork pre-exec`.
    sentence-transformers spawns loky workers via fork; on macOS the
    Objective-C runtime aborts forked children if any framework was
    touched in the parent. Setting these env vars before the embedder
    is loaded is the standard bypass.

    `OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES` — silences the ObjC
    initialize-after-fork abort.
    `TOKENIZERS_PARALLELISM=false` — Hugging Face tokenizers disables
    its own fork warning + worker pool that triggers the same path.

    Idempotent: only `setdefault`s, so a launchd plist override still
    wins."""
    import os as _os
    _os.environ.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")
    _os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


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
    _harden_fork_safety()
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)

    daemon = Daemon(
        root, partition=partition,
        watch_root=watch_root,
        watch_debounce_ms=watch_debounce_ms,
        watch_semantic=watch_semantic,
    )
    # A live unsupervised daemon on this root is adopted (asked to stop),
    # not a reason to exit 1 into a KeepAlive spawn loop (plan-4 task 4.4).
    daemon._adopt_unsupervised(socket_path(root))

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
        daemon.serve_forever()
    finally:
        try:
            lockf.close()
        except Exception:
            pass
    return 0
