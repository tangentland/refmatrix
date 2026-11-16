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

import logging
import os
import socket
import threading
from pathlib import Path

from refmatrix import envknob as _envknob
from refmatrix.subproc import WorkerClient, recv_frame, send_frame

ROLES = ("embed", "rerank")


def model_sock_path() -> Path:
    """Where the shared model server listens. Lives beside the hub's own
    socket in the global store, because the hub owns its lifecycle."""
    return Path(
        os.environ.get("RMX_MODEL_SOCK")
        or (Path.home() / ".refmatrix" / "models.sock")
    )


# The process-wide dedupe set of `envknob.env_float`, bound here so this module's knobs
# (and tests that hand it a fresh set) keep their r5 name.
_ENV_WARNED: "set[tuple[str, str]]" = _envknob._ENV_WARNED


def env_float(name: str, default: float) -> float:
    """THE parse of a numeric shared-model knob (`RMX_SHARED_*_S`), bound to this module's
    logger: `envknob.env_float` (the env value as a float; unset/empty is the default; a
    value that is not a finite, non-negative number -- `300s`, `nan`, `-5` -- is the default
    plus ONE warning per process naming the variable and the value).

    Why (task 3.7 remedy r5, ch-bsd r4 #m-2, 2026-11-09): every knob on the shared-worker
    path was a bare `float(os.environ.get(...))`. A typo'd `RMX_SHARED_REPROBE_S=300s`
    raised `ValueError` out of `recall._reprobe_window`, inside the embed call of a
    daemonless process with a HEALTHY private worker, and the same typo in
    `RMX_SHARED_PROBE_TIMEOUT_S` made `import refmatrix.modelsrv` itself raise. The parse
    itself moved to the leaf `envknob` in r6 (ch-bsd 3.7 r6 #m-1, 2026-11-09) so `subproc`,
    which this module imports, can share it without a cycle. `_ENV_WARNED` is read at call
    time, so it is the one dedupe set unless a caller rebinds it."""
    return _envknob.env_float(name, default, logger=__name__, warned=_ENV_WARNED)


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
# Parsed by `env_float` (remedy r5 #m-2): a typo'd value is the default plus one warning,
# never an `import` that raises.
PROBE_TIMEOUT_S = env_float("RMX_SHARED_PROBE_TIMEOUT_S", 45.0)

# REQUEST-PATH re-probe bound (task 3.7 remedy r4, ch-bsd r3 #s-1, 2026-11-09). A
# daemonless process (`rmx mcp`, the CLI) holding a PRIVATE embed worker re-probes the
# hub inside an embed call (`recall._process_embed_client`), because it has no
# background tick. r3 used `PROBE_TIMEOUT_S` there: behind a hub that accepts and never
# answers, two concurrent calls took 45 s and 90 s and the next call 45 s again. That
# bound exists for a COLD worker's model load (bug-014) and belongs to the first build
# (`new_model_client`) and the daemon's tick, never to a request. Here the hub either
# answers its header at once or it does not: 1.0 s is twice `shared_available`'s 0.5 s
# connect bound. A cold hub worker misses it, but the probe has already asked the hub to
# start that worker. The FIRST such miss of a run re-arms the re-probe at the BASE window,
# not a doubled one (`recall.reprobe_shared_client`, task 3.7 remedy r5 #m-3, 2026-11-09:
# before r5 the miss doubled, so a cold hub cost base + 2*base), and the next re-probe
# finds the worker warm. A CONSECUTIVE header timeout doubles to the cap (ch-bsd 3.7 r6
# #s-1, 2026-11-09): that hub is mute, not cold. Env `RMX_SHARED_REQUEST_PROBE_TIMEOUT_S` (parsed by `env_float`).
REQUEST_PROBE_TIMEOUT_S = env_float("RMX_SHARED_REQUEST_PROBE_TIMEOUT_S", 1.0)


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
    `alive`, `close`, `retire` — so the model proxies cannot tell the difference.

    ONE CONNECTION PER CALL (bug-278, ch-bsd t03 r1 B1; the user's option (b), ruling L180,
    2026-11-15). The client used to hold one long-lived socket and take its `_lock` through a
    whole send/recv. A daemon stopping with a call in flight on a slow, cold or mute hub then
    waited in `close()` for that call's own timeout (`SHARED_OP_TIMEOUT_S`, 45 s per role, 90 s
    for both: past the stop grace and launchd's ExitTimeOut). The same persistent socket carried
    a per-call timeout into the next call unless it was restored (bsd-plan2 r7 #b-1) and needed
    a reconnect-and-retry after a hub restart. Now each `call` opens its own unix socket, with
    that call's timeout on it alone, and closes it when the call ends; no lock is held across
    I/O. The open sockets are kept in `_inflight` (its lock guards only the add and the remove),
    so `retire()` can shut every in-flight connection down and the blocked `recv` sees EOF at
    once. A dropped connection fails that call; nothing retries silently (a hub restart between
    calls needs no retry: the next call connects fresh).
    """

    def __init__(self, role: str, *, log=None, timeout: float | None = None):
        if role not in ROLES:
            raise ValueError(f"unknown role {role!r}")
        self.role = role
        self._log_fn = log
        from refmatrix.subproc import DEFAULT_TIMEOUT_S
        self.timeout = timeout or DEFAULT_TIMEOUT_S
        self._inflight: set = set()
        self._inflight_lock = threading.Lock()   # add / remove only, never around I/O
        self._info: dict = {}
        # True after a round trip completed (a header came back, ok or not); False before the
        # first, after a transport failure or a timeout, and once retired. `recall`'s
        # re-probe reads False as "this shared client is dead" (`_shared_client_is_dead`).
        self._alive = False
        self._retired = False

    def _log(self, msg: str) -> None:
        if self._log_fn is not None:
            try:
                self._log_fn(f"shared[{self.role}] {msg}")
            except Exception:
                pass

    def alive(self) -> bool:
        return self._alive and not self._retired

    def _refused(self):
        from refmatrix.subproc import WorkerError
        return WorkerError(f"shared {self.role} client retired (shut down); not connecting")

    def retire(self, *, timeout: float = 5.0, abandon_in_flight: bool = False) -> None:
        """Close for good: every later call raises without connecting, and the calls in flight
        end now or after `timeout`.

        The client is marked retired FIRST, so a call that has not connected yet refuses.
        `abandon_in_flight=True` (the daemon's stop, `_close_workers`) then shuts down every
        in-flight socket at once: the blocked `recv` sees EOF and its call raises `WorkerError`
        ("in-flight call abandoned"), so the stop waits on nothing the hub does (bug-278). The
        default first lets the in-flight calls finish for up to `timeout`, then shuts down
        whatever is still open. Never blocks longer than `timeout` plus the shutdowns."""
        self._retired = True
        self._alive = False
        if not abandon_in_flight and timeout > 0:
            import time as _time
            end = _time.monotonic() + float(timeout)
            while _time.monotonic() < end:
                with self._inflight_lock:
                    if not self._inflight:
                        break
                _time.sleep(0.02)
        with self._inflight_lock:
            socks = list(self._inflight)
        for s in socks:
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError as exc:
                # Already closed by its own call's `finally` between the snapshot and here.
                self._log(f"retire: shutdown of an in-flight connection: {exc!r}")
        if socks:
            self._log(f"retired; shut down {len(socks)} in-flight connection(s)")

    def close(self, *, timeout: float = 0.0) -> None:
        """`retire` without waiting: there is no persistent connection to close, only the
        in-flight ones, which are shut down. Never blocks."""
        self.retire(timeout=0.0, abandon_in_flight=True)

    def _connect(self, timeout: float) -> socket.socket:
        sp = model_sock_path()
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            s.settimeout(timeout)
            s.connect(str(sp))
        except BaseException:
            s.close()
            raise
        return s

    def call(self, op: str, payload: dict | None = None, *,
             blob: bytes | None = None, timeout: float | None = None):
        if self._retired:
            raise self._refused()
        req = {"role": self.role, "op": op, **(payload or {})}
        # A bounded client cannot forget: if it gave itself N seconds, the
        # frame says when it stops caring, and a worker that dequeues it after
        # that drops it instead of starving the next caller (bug-025).
        if timeout is not None and op != "info" and "deadline" not in req:
            import time as _time
            req["deadline"] = _time.time() + float(timeout)
        budget = self.timeout if timeout is None else float(timeout)
        try:
            s = self._connect(budget)
        except OSError:
            self._alive = False
            raise
        with self._inflight_lock:
            self._inflight.add(s)
        try:
            if self._retired:            # retired between the check above and the add
                raise self._refused()
            rw = s.makefile("rwb")
            try:
                send_frame(rw, req, blob)
                hdr, out = recv_frame(rw)
            finally:
                try:
                    rw.close()
                except OSError as exc:
                    self._log(f"closing the op={op} stream: {exc!r}")
        except TimeoutError:
            # A timeout is the answer for THIS call; the connection goes with it.
            self._alive = False
            raise
        except (EOFError, OSError) as exc:
            self._alive = False
            if self._retired:
                from refmatrix.subproc import WorkerError
                raise WorkerError(f"shared {self.role} client retired; in-flight op={op} "
                                  f"abandoned") from exc
            self._log(f"connection lost on op={op} ({exc!r})")
            raise
        finally:
            with self._inflight_lock:
                self._inflight.discard(s)
            s.close()
        self._alive = True
        if not hdr.get("ok"):
            from refmatrix.subproc import WorkerError
            raise WorkerError(hdr.get("error") or "shared worker error")
        return hdr, out

    def evict_if_idle(self, idle_s: float) -> bool:
        """No-op. The daemon's idle tick calls this on whatever client it
        holds, but a shared worker belongs to the hub — one project going
        quiet is not a reason to drop a model six other projects are using.
        Returning False keeps the tick's bookkeeping honest."""
        return False

    def info(self, *, timeout: float | None = None, nowait: bool = False) -> dict:
        """The worker's info header. `timeout` bounds the probe: a socket
        that accepts but never answers (a hub mid-restart, an evicted
        worker) must not hold the caller for the 300 s op timeout — that is
        the wedge the hub watchdog SIGKILLed on 2026-09-14.

        `nowait=True` asks the HUB, not the worker: the hub answers from the
        worker's cached header plus the queue depth it sampled when this frame
        joined the line, without taking the worker's lock. r9's `fresh` re-ask
        went through that lock, so on a busy worker it waited behind the very
        rerank it was predicting (ch-bsd r10 #s-2). `{}` + `queue_depth` means
        the worker is cold. Not cached: it describes one instant."""
        if nowait:
            hdr, _ = self.call("info", {"nowait": True}, timeout=timeout)
            return {k: v for k, v in hdr.items() if k != "ok"}
        # No lock across the call (bug-278): two first callers may both ask; the header is
        # the same, and the last assignment wins.
        if self._info:
            return self._info
        hdr, _ = self.call("info", timeout=timeout)
        self._info = {k: v for k, v in hdr.items() if k != "ok"}
        return self._info

    def fork(self, timeout: float | None = None) -> "SharedWorkerClient":
        """A new client on its OWN connection, for one bounded request.

        The daemon holds one long-lived client per role, and `call` used to hold
        its lock for a whole round trip. A budgeted read that shared it queued
        behind the daemon's own unbudgeted `memory_recall` rerank: 3.80 s on a
        1.0 s budget (ch-bsd r10 #b-1). Every call now has its own connection
        (bug-278), so the fork's job is its own `timeout` and its own retirement:
        `close()` it after use."""
        return SharedWorkerClient(self.role, log=self._log_fn, timeout=timeout)


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
        self._warming: set[str] = set()
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
            created = w is None
            if created:
                w = WorkerClient(role, log=self._log_fn)
                self._clients[role] = w
                self._log(f"worker[{role}] created")
        # The version handshake LOADS the model (6-33 s cold). It used to run
        # under `_lock`, which `_handle` also takes to count the queue, so
        # every frame of every role — a lock-free `nowait` header included —
        # stalled behind a cold start (ch-bsd r10 #s-2). Callers that get `w`
        # meanwhile queue on the worker's own lock, behind this load.
        if created:
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

        A typo (`300s`) is the default 0 plus ONE warning naming the variable
        (ch-bsd 3.7 r6 #m-1, 2026-11-09): before r6 a `ValueError` here was
        swallowed with no word, so an operator's typo silently disabled idle
        reaping.
        """
        return env_float("RMX_WORKER_IDLE_S", 0.0)

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
        with self._lock:
            # One warmup per role at a time: a cold role is asked about by
            # every budgeted read until it is warm (`nowait` info), and each
            # ask must not start another load.
            roles = [r for r in roles if r not in self._warming]
            self._warming.update(roles)
        if not roles:
            return

        def _warm() -> None:
            for role in roles:
                try:
                    import time
                    t0 = time.time()
                    self._worker(role).info()
                    self._log(f"worker[{role}] warm in {time.time() - t0:.1f}s")
                except Exception as exc:
                    self._log(f"worker[{role}] warmup failed: {exc!r}")
                finally:
                    with self._lock:
                        self._warming.discard(role)
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
                    w = None
                    try:
                        if op == "info" and req.pop("nowait", False):
                            # Lock-free (ch-bsd r10 #s-2): the worker's cached
                            # header, never a frame to the worker, and never
                            # `_worker()`, which holds `_lock` through a cold
                            # spawn. A cold role answers `{}` and starts warming
                            # so a LATER budget can use it.
                            cur = self._clients.get(role)
                            hdr = cur.info(nowait=True) if cur is not None else {}
                            out = None
                            if not hdr:
                                self.warm((role,))
                        else:
                            w = self._worker(role)
                            hdr, out = w.call(op, req, blob=blob)
                    except (EOFError, BrokenPipeError, ConnectionError) as exc:
                        # The WORKER side, and only after WorkerClient's own
                        # respawn-and-retry also failed: drop it so the next
                        # call gets a fresh one instead of failing forever.
                        #
                        # Only when we HAVE a worker. `_drop_worker(worker=None)`
                        # does not mean "nothing to drop" — its guard reads
                        # `if worker is not None and cur is not worker: return`,
                        # so None bypasses the identity check and closes the
                        # role's live client, which is the incident commented 15
                        # lines below. Unreachable today (`_worker` does no I/O
                        # that raises these), armed for the day it grows an
                        # eager spawn (ch-bsd plan-12 r3).
                        if w is not None:
                            self._drop_worker(role, exc, worker=w)
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
