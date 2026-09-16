"""One set of model workers for the whole fleet, owned by the hub.

`subproc` gave every daemon its own embedder and reranker. That fixed the
jetsam problem — the daemon stopped being the fattest process — but it
multiplies: 7 stores x 2 models = 14 worker processes at ~450 MB, ~6.5 GB
resident, to serve one user who is typing in one project at a time. The
models are identical; only the stores differ.

So the hub hosts them once and the per-project daemons become clients.
Same models, same vectors, ~0.9 GB instead of ~6.5 GB.

Wire format is deliberately the SAME framed protocol `subproc` speaks, just
over a unix socket instead of a pipe pair, with a `role` field selecting
which worker serves the request. That means `embedder.RemoteEmbedder` and
`reranker.RemoteReranker` work against a `SharedWorkerClient` with no
changes — they only ever needed `.call()` and `.info()`.

Failure containment matters here, because this turns one process into a
dependency of every store's dense retrieval. Two guards:

  * A daemon that cannot reach the socket falls back to its own private
    worker (`subproc.WorkerClient`) and keeps serving. The hub going down
    costs memory, not availability.
  * The server owns its workers through the same `WorkerClient` that
    already handles death, respawn, and wedged-process timeouts, so a
    model crash is one client's retry rather than a fleet outage.

Requests serialize per role (a `WorkerClient` holds a lock). A warm embed
is ~40 ms, so interactive traffic from several daemons interleaves fine; a
bulk `rmx embed` pass is the case that queues, and that is the price of
not paying for seven copies of the model.
"""
from __future__ import annotations

import os
import socket
import threading
from pathlib import Path

from refmatrix.subproc import WorkerClient, recv_frame, send_frame

ROLES = ("embed", "rerank")


def model_sock_path() -> Path:
    """Where the shared model server listens. Lives beside the hub's own
    socket in the global store, because the hub owns its lifecycle."""
    return Path(
        os.environ.get("RMX_MODEL_SOCK")
        or (Path.home() / ".refmatrix" / "models.sock")
    )


def shared_enabled() -> bool:
    """Should daemons prefer the shared workers? Default: yes.

    `RMX_SHARED_MODELS=0` sends every daemon back to a private worker pair
    — the escape hatch if the shared path ever becomes the problem."""
    return os.environ.get("RMX_SHARED_MODELS", "1") not in ("0", "false", "False")


# Adoption probe bound: how long a daemon waits for the shared worker's
# `info` before going private. A COLD worker loads its model first — measured
# 14.9 s (embed) and 33 s (rerank) on 2026-09-15 — so the old 5 s sent every
# daemon that booted or relaunched while the hub was cold to a private
# worker for good (bug-014: sixteen ~450 MB workers on one machine). A mute
# socket (hub mid-restart) still costs at most this long, once per role.
PROBE_TIMEOUT_S = float(os.environ.get("RMX_SHARED_PROBE_TIMEOUT_S", "45") or "45")


def shared_available(timeout: float = 0.5) -> bool:
    """Cheap probe: is something listening on the model socket?

    Deliberately does not load a model or send a request — this runs on the
    daemon's path to deciding shared-vs-private and must stay fast."""
    sp = model_sock_path()
    if not sp.exists():
        return False
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect(str(sp))
        s.close()
        return True
    except OSError:
        return False


class SharedWorkerClient:
    """Client half. Same surface as `subproc.WorkerClient` — `call`, `info`,
    `alive`, `close` — so the model proxies cannot tell the difference.

    One socket per client object, opened lazily and reconnected once on a
    dropped connection (the hub restarting under us is the expected case).
    """

    def __init__(self, role: str, *, log=None, timeout: float | None = None):
        if role not in ROLES:
            raise ValueError(f"unknown role {role!r}")
        self.role = role
        self._log_fn = log
        from refmatrix.subproc import DEFAULT_TIMEOUT_S
        self.timeout = timeout or DEFAULT_TIMEOUT_S
        self._sock: socket.socket | None = None
        self._rw = None
        self._lock = threading.RLock()
        self._info: dict = {}

    def _log(self, msg: str) -> None:
        if self._log_fn is not None:
            try:
                self._log_fn(f"shared[{self.role}] {msg}")
            except Exception:
                pass

    def alive(self) -> bool:
        return self._sock is not None

    def _connect(self) -> None:
        sp = model_sock_path()
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(self.timeout)
        s.connect(str(sp))
        self._sock = s
        self._rw = s.makefile("rwb")
        self._log(f"connected to {sp}")

    def close(self, *, timeout: float = 0.0) -> None:
        with self._lock:
            for obj in (self._rw, self._sock):
                try:
                    if obj is not None:
                        obj.close()
                except Exception:
                    pass
            self._rw = None
            self._sock = None

    def _call_once(self, req: dict, blob: bytes | None):
        if self._sock is None:
            self._connect()
        assert self._rw is not None
        send_frame(self._rw, req, blob)
        hdr, out = recv_frame(self._rw)
        if not hdr.get("ok"):
            from refmatrix.subproc import WorkerError
            raise WorkerError(hdr.get("error") or "shared worker error")
        return hdr, out

    def call(self, op: str, payload: dict | None = None, *,
             blob: bytes | None = None, timeout: float | None = None):
        req = {"role": self.role, "op": op, **(payload or {})}
        # A bounded client cannot forget: if it gave itself N seconds, the
        # frame says when it stops caring, and a worker that dequeues it after
        # that drops it instead of starving the next caller (bug-025).
        if timeout is not None and op != "info" and "deadline" not in req:
            import time as _time
            req["deadline"] = _time.time() + float(timeout)
        with self._lock:
            if timeout is not None:
                if self._sock is None:
                    self._connect()
                self._sock.settimeout(timeout)
            try:
                return self._call_once(req, blob)
            except TimeoutError:
                # A timeout is the answer, not a dropped connection: the
                # reconnect-and-retry below used to catch it (it is an
                # OSError) and reconnect with the DEFAULT 300 s timeout, so a
                # bounded probe blocked for five minutes anyway.
                self.close()
                raise
            except (EOFError, BrokenPipeError, ConnectionError, OSError) as exc:
                self._log(f"connection lost on op={op} ({exc!r}); reconnecting")
                self.close()
                if timeout is not None:
                    self._connect()
                    self._sock.settimeout(timeout)
                return self._call_once(req, blob)
            finally:
                # A per-call timeout is for THIS call only. It used to stay
                # on the socket, so the 1 s `info` probe of the recall hook
                # shortened the `rerank` that followed to 1 s — a warm worker
                # scores 20 docs in ~1 s, and 0 of 12 live hook runs reranked
                # (bsd-plan2-r7 #b-1); the daemon's 45 s probe likewise left
                # its 30 s client at 45 s.
                if timeout is not None and self._sock is not None:
                    try:
                        self._sock.settimeout(self.timeout)
                    except OSError:
                        pass

    def evict_if_idle(self, idle_s: float) -> bool:
        """No-op. The daemon's idle tick calls this on whatever client it
        holds, but a shared worker belongs to the hub — one project going
        quiet is not a reason to drop a model six other projects are using.
        Returning False keeps the tick's bookkeeping honest."""
        return False

    def info(self, *, timeout: float | None = None) -> dict:
        """The worker's info header. `timeout` bounds the probe: a socket
        that accepts but never answers (a hub mid-restart, an evicted
        worker) must not hold the caller for the 300 s op timeout — that is
        the wedge the hub watchdog SIGKILLed on 2026-09-14."""
        with self._lock:
            if self._info:
                return self._info
            hdr, _ = self.call("info", timeout=timeout)
            self._info = {k: v for k, v in hdr.items() if k != "ok"}
            return self._info


class ModelServer:
    """Server half. Owns one `WorkerClient` per role and fans N socket
    clients onto them.

    Workers are created lazily: a fleet that never runs a dense query never
    pays for a model, and the hub stays light until something asks.
    """

    def __init__(self, *, log=None):
        self._log_fn = log
        self._clients: dict[str, WorkerClient] = {}
        # In-flight + waiting requests per role. One serialized worker serves
        # every hook of every session, so "how many callers are ahead of me"
        # is the term a budgeted caller was missing (bug-025 / G13).
        self._pending: dict[str, int] = {}
        self._lock = threading.Lock()
        self._srv: socket.socket | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._evict_thread: threading.Thread | None = None

    def _log(self, msg: str) -> None:
        if self._log_fn is not None:
            try:
                self._log_fn(f"models {msg}")
            except Exception:
                pass

    def _worker(self, role: str) -> WorkerClient:
        with self._lock:
            w = self._clients.get(role)
            if w is None:
                w = WorkerClient(role, log=self._log_fn)
                self._clients[role] = w
                self._log(f"worker[{role}] created")
                self._check_worker_version(w)
            return w

    def _augment_info(self, role: str, hdr: dict, queue_depth: int) -> dict:
        """Add the server-side half of the cost to an `info` answer.

        The worker knows its seconds-per-doc; only the hub knows how many
        callers were AHEAD of this one. `queue_depth` is sampled at ENQUEUE and
        passed in — never re-read here.

        The first version read `_pending` at this point and subtracted one "for
        the caller being served". Both were wrong at once: `_handle` decrements
        in its `finally`, so by the time this ran the queue had drained and the
        count described the callers who arrived BEHIND the asker, minus one
        more. Against the real `_handle` over socketpairs it answered
        `queue_depth: 0` with two reranks ahead — exactly the single-contender
        case `(1 + queue_depth)` exists to catch (ch-bsd plan-12 #b-1). The
        value has to be taken when the caller joins the line, which is the only
        instant that describes its own wait.
        """
        out = dict(hdr)
        out["queue_depth"] = max(0, int(queue_depth))
        return out

    def _drop_worker(self, role: str, exc: BaseException, *, worker=None) -> None:
        """Forget `worker` (or the current one) for `role`. Only the worker
        that failed is dropped: a thread holding a stale reference must not
        close the replacement another thread is already using."""
        with self._lock:
            cur = self._clients.get(role)
            if worker is not None and cur is not worker:
                return
            w = self._clients.pop(role, None)
        if w is None:
            return
        try:
            w.close(timeout=2.0)
        except Exception as cexc:  # noqa: BLE001 — logged, never masks the drop
            self._log(f"worker[{role}] close after broken pipe failed: {cexc!r}")
        self._log(f"worker[{role}] dropped after {type(exc).__name__}; "
                  f"recreated on the next call")

    def _check_worker_version(self, w: WorkerClient) -> None:
        """A hub that outlived a deploy spawns TODAY's workers from
        YESTERDAY's process: the frame protocol drifts and every op dies
        with BrokenPipeError while the hub keeps serving (observed
        2026-09-09 — 8 minutes of ~3s hook stalls fleet-wide). The worker
        now reports its refmatrix version at the info handshake; on a
        mismatch the only correct move is to restart THIS process onto the
        deployed code. Under launchd (KeepAlive on non-zero exit) that is
        exactly `os._exit(1)`; an unsupervised hub dies loudly instead of
        limping, and the log says why."""
        try:
            info = w.info()
        except Exception:
            # Worker didn't come up — the existing respawn/timeout
            # machinery owns that failure mode.
            return
        child = info.get("version")
        if not child:
            return
        from refmatrix import __version__ as mine
        if child != mine:
            self._log(
                f"FATAL worker version {child} != hub {mine} — hub "
                f"outlived a deploy; exiting for supervisor respawn")
            import os as _os
            _os._exit(1)

    # -- lifecycle ----------------------------------------------------

    def start(self) -> bool:
        sp = model_sock_path()
        sp.parent.mkdir(parents=True, exist_ok=True)
        # Unlink-before-bind, the way the per-project daemons do. A stale
        # socket file from a killed hub would otherwise make bind fail and
        # send the whole fleet to private workers silently.
        if sp.exists():
            try:
                sp.unlink()
            except OSError:
                pass
        try:
            srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            srv.bind(str(sp))
            os.chmod(sp, 0o600)
            srv.listen(32)
            srv.settimeout(1.0)
        except OSError as exc:
            self._log(f"listen failed at {sp}: {exc!r} -- daemons will use "
                      "private workers")
            return False
        self._srv = srv
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._serve, name="rmx-models", daemon=True)
        self._thread.start()
        self._start_evict_tick()
        self._log(f"listening at {sp}")
        return True

    def idle_seconds(self) -> float:
        """Reap a worker idle this long. 0 = never (the default).

        The knob moved here when the workers did. A per-daemon
        `RMX_WORKER_IDLE_S` is a NO-OP under sharing: each daemon holds a
        `SharedWorkerClient` whose `evict_if_idle` deliberately returns False,
        because one project going quiet is not a reason to drop a model six
        others are using. Only the hub, which owns the processes, can decide
        the fleet is idle.
        """
        try:
            return float(os.environ.get("RMX_WORKER_IDLE_S", "0") or "0")
        except ValueError:
            return 0.0

    def _evict_loop(self, idle_s: float, interval: float) -> None:
        while not self._stop.wait(interval):
            with self._lock:
                workers = list(self._clients.items())
            for role, w in workers:
                try:
                    if w.evict_if_idle(idle_s):
                        # Drop the entry so the next request builds a fresh
                        # client rather than reusing a closed one.
                        with self._lock:
                            if self._clients.get(role) is w:
                                del self._clients[role]
                        self._log(f"worker[{role}] idle-evicted after "
                                  f"{idle_s:.0f}s")
                except Exception as exc:
                    self._log(f"worker[{role}] idle-evict failed: {exc!r}")

    def _start_evict_tick(self) -> None:
        """Reclaim model RSS when the fleet goes quiet.

        This is the only eviction that actually returns memory: torch's
        caching allocator never gives it back on macOS (dropping an in-process
        reference recovered ~84 MB of ~610), so `kill()` is the mechanism.
        Measured live: two shared workers sat at 891 MB cold and 3155 MB after
        a 13,517-vector embed, because the allocator keeps its high-water mark.
        """
        idle_s = self.idle_seconds()
        if idle_s <= 0:
            return
        interval = max(5.0, min(idle_s / 4.0, 60.0))
        self._evict_thread = threading.Thread(
            target=self._evict_loop, args=(idle_s, interval),
            name="rmx-models-evict", daemon=True)
        self._evict_thread.start()
        self._log(f"idle-evict tick every {interval:.0f}s (idle>{idle_s:.0f}s)")

    def stop(self) -> None:
        self._stop.set()
        if self._evict_thread is not None:
            self._evict_thread.join(timeout=3.0)
        if self._thread is not None:
            self._thread.join(timeout=3.0)
        try:
            if self._srv is not None:
                self._srv.close()
        except OSError:
            pass
        sp = model_sock_path()
        try:
            if sp.exists():
                sp.unlink()
        except OSError:
            pass
        with self._lock:
            workers, self._clients = self._clients, {}
        for role, w in workers.items():
            try:
                w.close(timeout=2.0)
            except Exception as exc:
                self._log(f"worker[{role}] close failed: {exc!r}")
        self._log("stopped")

    def warm(self, roles=ROLES) -> None:
        """Load the models now, in the background, so the first client does
        not pay for it. Same argument as the daemon's own warmup: the first
        caller is almost always an always-on hook with a budget."""
        def _warm() -> None:
            for role in roles:
                try:
                    import time
                    t0 = time.time()
                    self._worker(role).info()
                    self._log(f"worker[{role}] warm in {time.time() - t0:.1f}s")
                except Exception as exc:
                    self._log(f"worker[{role}] warmup failed: {exc!r}")
        threading.Thread(target=_warm, name="rmx-models-warm",
                         daemon=True).start()

    def status(self) -> dict:
        with self._lock:
            live = {r: w.alive() for r, w in self._clients.items()}
        return {
            "socket": str(model_sock_path()),
            "listening": self._srv is not None and not self._stop.is_set(),
            "workers": live,
        }

    # -- serving ------------------------------------------------------

    def _serve(self) -> None:
        assert self._srv is not None
        while not self._stop.is_set():
            try:
                conn, _ = self._srv.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._handle, args=(conn,),
                             daemon=True).start()

    def _handle(self, conn: socket.socket) -> None:
        """One client connection. Stays open for many requests — a daemon
        holds its connection for its lifetime rather than reconnecting per
        query."""
        try:
            rw = conn.makefile("rwb")
            while not self._stop.is_set():
                try:
                    req, blob = recv_frame(rw)
                except (EOFError, OSError):
                    return                    # client went away; normal
                role = req.pop("role", "")
                op = req.pop("op", "")
                try:
                    if role not in ROLES:
                        raise ValueError(f"unknown role {role!r}")
                    # Join the line BEFORE `_worker()`, not after. `_worker`
                    # holds `_lock` while it creates the client and runs the
                    # version handshake, and a COLD model load blocks there for
                    # 6-33 s — the exact window where callers pile up. Counting
                    # after it meant a caller with two reranks ahead still read
                    # `queue_depth: 0` during a cold start (ch-bsd plan-12 r2),
                    # which is the same off-by-an-instant as #b-1, one scope out.
                    with self._lock:
                        self._pending[role] = self._pending.get(role, 0) + 1
                        # Callers already in line when we joined — not us.
                        ahead = self._pending[role] - 1
                    try:
                        w = self._worker(role)
                        hdr, out = w.call(op, req, blob=blob)
                    except (EOFError, BrokenPipeError, ConnectionError) as exc:
                        # The WORKER side, and only after WorkerClient's own
                        # respawn-and-retry also failed: drop it so the next
                        # call gets a fresh one instead of failing forever.
                        # `w` may be unbound if `_worker()` itself raised.
                        self._drop_worker(role, exc, worker=locals().get("w"))
                        raise
                    finally:
                        with self._lock:
                            self._pending[role] = max(
                                0, self._pending.get(role, 1) - 1)
                    if op == "info":
                        hdr = self._augment_info(role, hdr, ahead)
                    # `ok` comes from the worker; re-send it as our own.
                    hdr = {k: v for k, v in hdr.items() if k != "ok"}
                    try:
                        send_frame(rw, {"ok": True, **hdr}, out or None)
                    except (BrokenPipeError, ConnectionError, OSError):
                        # The CLIENT went away — a daemon's bounded probe timed
                        # out while the worker was still warming (the
                        # `op=info failed: BrokenPipeError` lines of bug-014).
                        # The worker is fine; a drop here killed healthy
                        # workers under the whole fleet (2026-09-15 02:35).
                        return
                except Exception as exc:
                    self._log(f"role={role} op={op} failed: {exc!r}")
                    try:
                        send_frame(rw, {
                            "ok": False,
                            "error": f"{type(exc).__name__}: {exc}",
                        })
                    except Exception:
                        return
        finally:
            try:
                conn.close()
            except OSError:
                pass
