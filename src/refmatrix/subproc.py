"""Out-of-process model workers.

Why this exists: `project_daemon_ingest_jetsam_diagnosed` established that
the daemon's resident sentence-transformers model (~610 MB RSS for
bge-small-en-v1.5) is one of two terms that sum to a macOS jetsam target.
It also established that in-process eviction CANNOT fix it — dropping the
model ref + `gc.collect()` returned only ~84 MB of 610 to the OS, because
torch's caching allocator never calls `malloc_trim` on macOS. The memory
named the real fix as option B': run the model in a worker process, where
"evict" means `kill()` and actually reclaims the memory.

This module is the transport half. It is model-agnostic: `WorkerClient`
spawns `python -m refmatrix.embed_worker --role <role>` and speaks a tiny
framed request/response protocol over its stdin/stdout pipes. The embed
and rerank proxies (`embedder.RemoteEmbedder`, `reranker.RemoteReranker`)
are thin wrappers over it.

Design notes:

- **exec, not fork.** The worker is a fresh interpreter. That is not
  incidental: `daemon._harden_fork_safety` exists because ObjC aborts
  forked children that touch a framework in the parent, which is exactly
  what `fork()`ing a loaded torch would do. An exec'd worker sidesteps the
  hazard rather than papering over it.
- **Vectors travel as raw bytes.** A JSON float array is ~10x the size and
  costs a parse. Frames carry an optional binary blob the caller
  reinterprets with `np.frombuffer`.
- **The worker's stdout is sacred.** Model libraries print. The worker
  duplicates fd 1 to a private channel and repoints fd 1 at stderr before
  importing anything heavy, so a stray `print()` corrupts a log line
  instead of the protocol.
- **Death is survivable.** A dead worker is respawned on the next call and
  the request is retried once. Only if the retry also fails does the error
  reach the daemon op, which already degrades to a clean client error.
"""
from __future__ import annotations

import json
import os
import select
import struct
import subprocess
import sys
import threading
import time

_HDR = struct.Struct(">I")

# Cold start is a model load: 5-20s warm cache, up to ~90s on a busy CPU
# with a cold HF cache. The daemon warms in the background so nobody
# normally pays it, but the budget has to cover the case where someone does.
DEFAULT_TIMEOUT_S = float(os.environ.get("RMX_WORKER_TIMEOUT_S", "300") or "300")


def in_venv() -> bool:
    """Is this interpreter running inside a virtualenv / venv?"""
    return sys.prefix != getattr(sys, "base_prefix", sys.prefix)


def python_executable() -> str:
    """The interpreter a worker must run under.

    `sys.executable` is authoritative: a venv's python sets it to the venv
    binary, and `sys.prefix` (hence site-packages) is derived from that
    path, so spawning it reproduces the parent's environment exactly. The
    fallbacks exist only for the cases where it is not usable at all —
    an embedded or frozen interpreter can leave it empty.

    A worker that lands on the wrong interpreter does not fail cleanly: it
    fails as `ModuleNotFoundError: sentence_transformers` from a system
    python that never had the [dense] extra installed, which reads like a
    missing dependency rather than a wrong venv.
    """
    exe = sys.executable
    if exe and os.path.isfile(exe) and os.access(exe, os.X_OK):
        return exe
    # Activated-venv fallback: VIRTUAL_ENV is set by `activate`.
    venv = os.environ.get("VIRTUAL_ENV")
    if venv:
        for name in ("python3", "python"):
            cand = os.path.join(venv, "bin", name)
            if os.path.isfile(cand) and os.access(cand, os.X_OK):
                return cand
    # Last resort: derive from the running prefix.
    for name in ("python3", "python"):
        cand = os.path.join(sys.prefix, "bin", name)
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    raise RuntimeError(
        "cannot resolve a python interpreter to spawn the model worker "
        f"(sys.executable={sys.executable!r}, sys.prefix={sys.prefix!r})"
    )


def subproc_embed_enabled() -> bool:
    """Is the out-of-process embedder switched on? Default: yes.

    Set `RMX_EMBED_SUBPROC=0` to opt back into the in-process model. The
    flag is kept (rather than deleted along with the old path) so the two
    can still be A/B'd on a live daemon without a code change, and so a
    host that hits an unforeseen spawn problem has a one-env-var escape.

    The worker itself sets this to "0" in its child env, so a worker can
    never spawn a worker.
    """
    return os.environ.get("RMX_EMBED_SUBPROC", "1") not in ("0", "false", "False")


def send_frame(fh, obj: dict, blob: bytes | None = None) -> None:
    """Write one frame: 4-byte BE length + JSON header, then `blob` bytes
    when present (header carries `_blob` = byte count)."""
    if blob is not None:
        obj = dict(obj)
        obj["_blob"] = len(blob)
    payload = json.dumps(obj).encode("utf-8")
    fh.write(_HDR.pack(len(payload)))
    fh.write(payload)
    if blob:
        fh.write(blob)
    fh.flush()


def _read_exact(fh, n: int) -> bytes:
    """Read exactly `n` bytes or raise EOFError. A short read means the
    peer died mid-frame — the caller treats that the same as a clean EOF."""
    if n == 0:
        return b""
    buf = fh.read(n)
    if buf is None or len(buf) < n:
        raise EOFError("worker closed mid-frame")
    return buf


def recv_frame(fh) -> tuple[dict, bytes]:
    """Read one frame. Returns `(header, blob)`; blob is b"" when absent."""
    raw = fh.read(_HDR.size)
    if not raw or len(raw) < _HDR.size:
        raise EOFError("worker closed")
    (n,) = _HDR.unpack(raw)
    obj = json.loads(_read_exact(fh, n).decode("utf-8"))
    nblob = int(obj.pop("_blob", 0) or 0)
    return obj, _read_exact(fh, nblob) if nblob else b""


class WorkerError(RuntimeError):
    """The worker answered, and the answer was an error."""


class WorkerClient:
    """Supervises one model subprocess and speaks the frame protocol to it.

    Thread-safe: every call serializes on `_lock`, because the protocol is
    strict request/response over a single pipe pair and the daemon calls
    this from several pool threads.
    """

    def __init__(
        self,
        role: str,
        *,
        model: str | None = None,
        log=None,
        timeout: float | None = None,
        argv: list[str] | None = None,
    ):
        self.role = role
        self.model = model
        # Overridable so the lifecycle (respawn, timeout, EOF-exit) can be
        # tested against a stub worker that starts in milliseconds instead
        # of paying a real model load.
        self._argv = argv
        self._log_fn = log
        self.timeout = timeout or DEFAULT_TIMEOUT_S
        self._proc: subprocess.Popen | None = None
        self._lock = threading.RLock()
        self._last_used = 0.0
        self._info: dict = {}
        self._stderr_fh = None

    # ---- logging ------------------------------------------------------

    def _log(self, msg: str) -> None:
        if self._log_fn is not None:
            try:
                self._log_fn(f"worker[{self.role}] {msg}")
            except Exception:
                pass

    # ---- lifecycle ----------------------------------------------------

    def alive(self) -> bool:
        p = self._proc
        return p is not None and p.poll() is None

    def _worker_env(self) -> dict:
        env = dict(os.environ)
        # Same hardening the daemon applies to itself. Harmless in an
        # exec'd child, and it keeps HF tokenizers from spawning a worker
        # pool we neither need nor want inside an already-isolated process.
        env.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")
        env.setdefault("TOKENIZERS_PARALLELISM", "false")
        env.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
        env.setdefault("TRANSFORMERS_VERBOSITY", "error")
        # The worker must never recurse into another worker.
        env["RMX_EMBED_SUBPROC"] = "0"

        # --- keep the child inside this venv ---------------------------
        #
        # `__PYVENV_LAUNCHER__` is set by the macOS framework python build.
        # A child that inherits it can resolve back to the framework
        # interpreter instead of the venv one we asked for -- which shows up
        # as `ModuleNotFoundError: sentence_transformers` from a python that
        # never had the extra installed, not as an obvious wrong-interpreter
        # error. Drop it; we pass the interpreter explicitly in argv.
        env.pop("__PYVENV_LAUNCHER__", None)
        # PYTHONHOME overrides the prefix derived from the interpreter path
        # and would send the child to a different stdlib entirely. Nothing
        # in refmatrix sets it, so inheriting one is an accident.
        env.pop("PYTHONHOME", None)
        if in_venv():
            # Make the venv explicit for the child and for anything it
            # shells out to (HF tooling occasionally does).
            env["VIRTUAL_ENV"] = sys.prefix
            bindir = os.path.join(sys.prefix, "bin")
            path_parts = [p for p in env.get("PATH", "").split(os.pathsep) if p]
            if bindir not in path_parts:
                env["PATH"] = os.pathsep.join([bindir, *path_parts])
        if self.model:
            env["RMX_WORKER_MODEL"] = self.model
        # An editable/venv install already has refmatrix importable via
        # sys.path; a launchd-spawned daemon may not have it on PYTHONPATH.
        # Prepend the package parent so `-m refmatrix.embed_worker` resolves
        # from exactly the tree this process is running.
        try:
            import refmatrix
            pkg_parent = os.path.dirname(os.path.dirname(
                os.path.abspath(refmatrix.__file__)))
            existing = env.get("PYTHONPATH", "")
            parts = [p for p in existing.split(os.pathsep) if p]
            if pkg_parent not in parts:
                env["PYTHONPATH"] = os.pathsep.join([pkg_parent, *parts])
        except Exception:
            pass
        return env

    def _spawn(self) -> None:
        argv = self._argv or [
            python_executable(), "-m", "refmatrix.embed_worker",
            "--role", self.role,
        ]
        # Worker stderr is a log channel, not a pipe: nobody drains a pipe
        # here, so a chatty model load would fill the buffer and deadlock
        # the worker mid-import. Route it to the daemon's own log fd when
        # we have one, else discard.
        stderr_target = self._stderr_fh
        if stderr_target is None:
            stderr_target = subprocess.DEVNULL
        self._proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=stderr_target,
            env=self._worker_env(),
            close_fds=True,
            # Buffered (not bufsize=0): a raw FileIO write() may be partial,
            # which would silently truncate a frame. BufferedWriter + an
            # explicit flush per frame guarantees the whole frame lands.
        )
        self._info = {}
        self._log(
            f"spawned pid={self._proc.pid} model={self.model or 'default'} "
            f"python={argv[0]} venv={sys.prefix if in_venv() else '-'}"
        )

    def set_stderr(self, fh) -> None:
        """Point worker stderr at an already-open file object (the daemon
        log). Takes effect on the next spawn."""
        self._stderr_fh = fh

    def _ensure(self) -> subprocess.Popen:
        if not self.alive():
            self._spawn()
        assert self._proc is not None
        return self._proc

    def close(self, *, timeout: float = 5.0) -> None:
        """Shut the worker down and reclaim its RSS.

        Closing stdin is the polite path: the worker's read loop sees EOF
        and exits its own main(). Escalate only if it doesn't.
        """
        with self._lock:
            p = self._proc
            self._proc = None
            if p is None:
                return
            try:
                if p.stdin is not None:
                    try:
                        p.stdin.close()
                    except Exception:
                        pass
                try:
                    p.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    p.terminate()
                    try:
                        p.wait(timeout=2.0)
                    except subprocess.TimeoutExpired:
                        p.kill()
                        try:
                            p.wait(timeout=2.0)
                        except subprocess.TimeoutExpired:
                            pass
            finally:
                for stream in (p.stdin, p.stdout):
                    try:
                        if stream is not None:
                            stream.close()
                    except Exception:
                        pass
                self._log("closed")

    def evict_if_idle(self, idle_s: float) -> bool:
        """Kill the worker if it hasn't been used in `idle_s` seconds.

        This is the thing in-process eviction could never deliver: the
        ~530 MB torch never gives back is returned by process exit.
        Returns True if a worker was actually reaped.
        """
        with self._lock:
            if not self.alive():
                return False
            if self._last_used and (time.time() - self._last_used) < idle_s:
                return False
            self._log(f"idle-evict after {idle_s:.0f}s")
            self.close()
            return True

    # ---- protocol -----------------------------------------------------

    def _call_once(self, req: dict, blob: bytes | None,
                   timeout: float) -> tuple[dict, bytes]:
        p = self._ensure()
        assert p.stdin is not None and p.stdout is not None
        send_frame(p.stdin, req, blob)
        # Bound the wait: a wedged worker (stuck in a C-extension call)
        # must not pin a daemon pool thread forever.
        ready, _, _ = select.select([p.stdout], [], [], timeout)
        if not ready:
            self._log(f"timeout after {timeout:.0f}s on op={req.get('op')}; killing")
            self.close(timeout=0.5)
            raise TimeoutError(
                f"{self.role} worker timed out after {timeout:.0f}s"
            )
        hdr, out_blob = recv_frame(p.stdout)
        if not hdr.get("ok"):
            raise WorkerError(hdr.get("error") or "worker error")
        return hdr, out_blob

    def call(self, op: str, payload: dict | None = None, *,
             blob: bytes | None = None,
             timeout: float | None = None) -> tuple[dict, bytes]:
        """Send one request, return `(header, blob)`.

        Retries exactly once across a respawn. A worker that dies while
        serving is the expected case under jetsam — the whole point of
        this module is that it costs a retry instead of the daemon.
        """
        req = {"op": op, **(payload or {})}
        budget = timeout or self.timeout
        with self._lock:
            try:
                hdr, out = self._call_once(req, blob, budget)
            except (EOFError, BrokenPipeError, ConnectionError, OSError) as exc:
                self._log(f"died on op={op} ({exc!r}); respawning")
                self.close(timeout=1.0)
                hdr, out = self._call_once(req, blob, budget)
            self._last_used = time.time()
            return hdr, out

    def info(self) -> dict:
        """Cached `{model, dim, python, prefix}` from the worker.

        Also verifies the child landed in the same environment as the
        parent. It should be impossible to miss -- we pass the interpreter
        explicitly and strip the env vars that could redirect it -- but a
        silent mismatch is expensive to diagnose later, because the symptom
        is a missing-package error rather than a wrong-interpreter one.
        """
        with self._lock:
            if self._info:
                return self._info
            hdr, _ = self.call("info")
            self._info = {k: v for k, v in hdr.items() if k != "ok"}
            child_prefix = self._info.get("prefix")
            if child_prefix and child_prefix != sys.prefix:
                self._log(
                    f"WARNING worker prefix {child_prefix!r} != parent "
                    f"{sys.prefix!r} -- the worker is running in a different "
                    "environment than the daemon"
                )
            return self._info
