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
    def __init__(self, root: Path, *, partition: str | None = None):
        self.root = Path(root).resolve()
        self.partition = partition
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

    def _log(self, msg: str) -> None:
        if self.log_fh is None:
            return
        self.log_fh.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {msg}\n")
        self.log_fh.flush()

    def serve_forever(self) -> int:
        sock_path = socket_path(self.root)
        # Clean up any stale socket left from a crashed daemon. We've
        # already verified upstream that no live daemon is using it.
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

        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(str(sock_path))
        os.chmod(sock_path, 0o600)
        srv.listen(16)
        srv.settimeout(1.0)

        def _shutdown(*_):
            self._stop = True
        signal.signal(signal.SIGTERM, _shutdown)
        signal.signal(signal.SIGINT, _shutdown)

        try:
            while not self._stop:
                try:
                    conn, _ = srv.accept()
                except socket.timeout:
                    continue
                with conn:
                    self._handle(conn)
        finally:
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


def _op_stop(d: Daemon, args: dict) -> dict:
    d._stop = True
    return {"stopping": True}


OPS: dict[str, Callable[[Daemon, dict], Any]] = {
    "ping": _op_ping,
    "enqueue": _op_enqueue,
    "flush_queue": _op_flush_queue,
    "flush_queue_async": _op_flush_queue_async,
    "sync_files": _op_sync_files,
    "stop": _op_stop,
}


# ---------- daemonize -------------------------------------------------------


def spawn_daemon(root: Path, *, partition: str | None = None,
                 wait_for_ready: float = 5.0) -> int:
    """Fork a background daemon for `root` and return when it's accepting
    connections. Idempotent: if a daemon is already running for `root`,
    returns its PID immediately. Safe under concurrent calls — uses an
    exclusive `daemon.lock` flock so only one fork wins; the loser polls
    until the winner is healthy.
    """
    import fcntl
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)

    # Fast path before locking.
    existing = read_pid(root)
    if existing is not None and ping(root):
        return existing

    lock_path = root / "daemon.lock"
    lockf = lock_path.open("w")
    try:
        # Block on the lock — multiple Claude SessionStart hooks may fire
        # at once. The first one starts the daemon (and holds the lock
        # through fork + readiness wait); the rest wait here briefly,
        # then re-check and return the now-running pid.
        fcntl.flock(lockf.fileno(), fcntl.LOCK_EX)

        existing = read_pid(root)
        if existing is not None and ping(root):
            return existing

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
            Daemon(root, partition=partition).serve_forever()
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
    daemon stopped within the timeout."""
    pid = read_pid(root)
    if pid is None:
        return True
    try:
        call(root, "stop")
    except Exception:
        # Socket gone or unresponsive — fall back to SIGTERM.
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            return True
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not is_alive(pid):
            return True
        time.sleep(0.05)
    return False
