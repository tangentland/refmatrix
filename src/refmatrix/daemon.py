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
                 watch_root: Path | None = None,
                 watch_debounce_ms: int = 500,
                 watch_semantic: bool = False):
        self.root = Path(root).resolve()
        self.partition = partition
        # Filesystem watcher config. If `watch_root` is set, serve_forever
        # spawns a watchdog thread that debounces fs events and syncs the
        # changed files through the daemon's Store. None = no watcher.
        self.watch_root = Path(watch_root).resolve() if watch_root else None
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
        self._watch_stop: "threading.Event | None" = None
        self._watch_thread: "threading.Thread | None" = None

    def _log(self, msg: str) -> None:
        if self.log_fh is None:
            return
        self.log_fh.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {msg}\n")
        self.log_fh.flush()

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

        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(str(sock_path))
        os.chmod(sock_path, 0o600)
        srv.listen(16)
        srv.settimeout(1.0)

        def _shutdown(*_):
            self._stop = True
        signal.signal(signal.SIGTERM, _shutdown)
        signal.signal(signal.SIGINT, _shutdown)

        # Bounded thread pool for per-connection handlers so a long-running
        # op (e.g. a multi-minute ingest holding _store_lock) does not
        # block the accept loop. Without this, `rmx daemon stop` and every
        # other client call queue behind the slow op and the only escape
        # is SIGKILL -- which risks DuckDB WAL corruption.
        #
        # _store_lock continues to serialize mutations; the pool exists
        # purely to keep the accept loop hot and to let independent reads
        # run while writes are in flight. Pool size is small (16) because
        # the work is either lock-bound (waiting on _store_lock) or
        # IO-bound (waiting on DuckDB); a larger pool just produces more
        # contention without throughput.
        from concurrent.futures import ThreadPoolExecutor

        pool_workers = int(os.environ.get("RMX_DAEMON_WORKERS", "16") or "16")
        pool = ThreadPoolExecutor(
            max_workers=pool_workers,
            thread_name_prefix="rmxd-handler",
        )

        def _run_handler(c) -> None:
            try:
                with c:
                    self._handle(c)
            except Exception as exc:
                self._log(f"handler thread crashed: {exc!r}")

        try:
            while not self._stop:
                try:
                    conn, _ = srv.accept()
                except socket.timeout:
                    continue
                pool.submit(_run_handler, conn)
        finally:
            # Wait briefly for in-flight handlers to drain so we don't
            # tear down the socket out from under a request that was
            # almost done. Hard cap so a stuck handler can't pin shutdown.
            pool.shutdown(wait=True, cancel_futures=True)
            if getattr(self, "_flush_stop", None) is not None:
                self._flush_stop.set()
            if getattr(self, "_flush_thread", None) is not None:
                self._flush_thread.join(timeout=3.0)
            # Final flush before close() so anything queued in the last
            # interval lands. close() also flushes, but doing it explicitly
            # under _store_lock keeps the on-disk state consistent if
            # close() races with a late handler.
            try:
                with self._store_lock:
                    if self.store is not None:
                        self.store.flush_fragments()
            except Exception as exc:
                self._log(f"final flush failed: {exc!r}")
            if self._watch_stop is not None:
                self._watch_stop.set()
            if self._watch_thread is not None:
                self._watch_thread.join(timeout=3.0)
            srv.close()
            if sock_path.exists():
                sock_path.unlink()
            pid_p = pid_path(self.root)
            if pid_p.exists():
                pid_p.unlink()
            if self.store is not None:
                self.store.close()
            self._log("daemon stopped")
            if self.log_fh is not None:
                self.log_fh.close()
        return 0

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

        self._flush_thread = _t.Thread(
            target=_runner, name="rmxd-flush", daemon=True,
        )
        self._flush_thread.start()

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

        def _flush(paths: list[str]) -> None:
            # Take the store_lock so the watcher and the socket request
            # handler never touch the shared Store concurrently.
            try:
                with self._store_lock:
                    report = sync_files(
                        self.store, paths,
                        project_root=self.watch_root,
                        semantic=self.watch_semantic,
                    )
                queued = _enqueue_curator(paths)
                tail = f" curator+{queued}" if queued else ""
                self._log(
                    f"watch flush: paths={len(paths)} +{report['added']} "
                    f"~{report['updated']} -{report['purged']}{tail}"
                )
            except Exception as exc:
                self._log(f"watch flush failed: {exc!r}")

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
        observer.schedule(_Handler(), str(self.watch_root), recursive=True)
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
        self._log(
            f"watcher started root={self.watch_root} "
            f"debounce={self.watch_debounce_ms}ms"
        )

    def _handle(self, conn: socket.socket) -> None:
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
                try:
                    result = handler(self, args)
                    resp = {"ok": True, "result": result}
                except Exception as exc:
                    self._log(f"op {op} raised: {exc!r}")
                    resp = {"ok": False, "error": str(exc)}
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
    `_op_ingest_path`: avoid catalog-lock contention with the watcher."""
    from refmatrix.ingest_gmd import collect_gmd_files, ingest_gmd_paths
    targets = [Path(p).resolve() for p in (args.get("targets") or [])]
    verbose = bool(args.get("verbose"))
    files = collect_gmd_files(targets)
    if not files:
        return {"files": 0, "report": "no candidate files found"}
    with d._store_lock:
        stats = ingest_gmd_paths(d.store, files, verbose=verbose)
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


def _op_stop(d: Daemon, args: dict) -> dict:
    d._stop = True
    return {"stopping": True}


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
    "stop": _op_stop,
}


# ---------- daemonize -------------------------------------------------------


def spawn_daemon(root: Path, *, partition: str | None = None,
                 wait_for_ready: float = 5.0,
                 watch_root: Path | None = None,
                 watch_debounce_ms: int = 500,
                 watch_semantic: bool = False) -> int:
    """Fork a background daemon for `root` and return when it's accepting
    connections. Idempotent: if a daemon is already running for `root`,
    returns its PID immediately. Safe under concurrent calls — uses an
    exclusive `daemon.lock` flock so only one fork wins; the loser polls
    until the winner is healthy.
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

        # Child 2 — the actual daemon. Detach FDs.
        lockf.close()
        devnull = os.open(os.devnull, os.O_RDWR)
        os.dup2(devnull, 0)
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
    return False
