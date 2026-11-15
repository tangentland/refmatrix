"""Daemon cooperative-shutdown unit tests.

These cover the in-process mechanics only:
  - `_drain_pool` honors its timeout (bounded wait when a worker
    refuses to finish).
  - `_drain_pool` returns promptly when workers do finish.

A full fork+SIGTERM end-to-end test would exercise more, but is heavy
and flaky in CI; the unit shape is what fixes the hang the memory
captured.
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from refmatrix.daemon import Daemon


def _make_daemon(tmp_path: Path) -> Daemon:
    root = tmp_path / ".refmatrix"
    root.mkdir(parents=True, exist_ok=True)
    d = Daemon(root)
    return d


def test_drain_pool_returns_within_timeout_when_worker_hangs(tmp_path):
    d = _make_daemon(tmp_path)
    pool = ThreadPoolExecutor(max_workers=2)
    block = threading.Event()

    def _hang() -> None:
        block.wait()  # never set until after drain returns

    pool.submit(_hang)
    pool.submit(_hang)

    start = time.monotonic()
    d._drain_pool("test", pool, timeout_s=0.4)
    elapsed = time.monotonic() - start

    # Bounded — must return well under 2x the cap even with two workers.
    assert elapsed < 1.0, f"drain pinned for {elapsed:.2f}s"
    # Workers still running; we leaked them on purpose.
    block.set()


def test_drain_pool_returns_quickly_when_workers_finish(tmp_path):
    """29.4 R3 class C (T0.3 + 29.4c, 2026-11-15): the old `elapsed < 1.0` against a 5 s
    timeout is an ordering check now. The workers are held on an event the test owns, so the
    drain is seen waiting on them; once they are released it returns, under a drain timeout ten
    times the hang guard, so returning at all proves it ended on the workers, not the deadline."""
    from tests.timing import HANG_GUARD_S, wait_for

    d = _make_daemon(tmp_path)
    pool = ThreadPoolExecutor(max_workers=2)
    release = threading.Event()
    started = threading.Semaphore(0)

    def _held() -> None:
        started.release()
        release.wait()

    futs = [pool.submit(_held), pool.submit(_held)]
    assert started.acquire(timeout=HANG_GUARD_S) and started.acquire(timeout=HANG_GUARD_S)
    drained = threading.Event()
    th = threading.Thread(
        target=lambda: (d._drain_pool("test", pool, timeout_s=10 * HANG_GUARD_S), drained.set()),
        daemon=True)
    th.start()
    try:
        # The drain cannot return while the workers are held: it joins them.
        assert not drained.wait(0.2), "the drain returned while its workers were still running"
    finally:
        release.set()
    wait_for(drained.is_set, what="the drain to return once its workers finished")
    assert all(f.done() for f in futs)


def test_drain_pool_cancels_queued_futures(tmp_path):
    d = _make_daemon(tmp_path)
    pool = ThreadPoolExecutor(max_workers=1)
    started = threading.Event()
    block = threading.Event()

    def _hang() -> None:
        started.set()
        block.wait(2.0)

    pool.submit(_hang)
    started.wait(1.0)
    queued = pool.submit(_hang)  # cannot start; worker count exhausted

    # Drain with a short timeout; the queued future should be cancelled.
    d._drain_pool("test", pool, timeout_s=0.3)
    assert queued.cancelled()
    block.set()


def test_shutdown_event_flips_on_signal_path(tmp_path):
    """Constructor wires `_shutdown_event`; signal handler in serve_forever
    sets it. Here we exercise the field directly — the signal-handler hook
    just calls `self._shutdown_event.set()`."""
    d = _make_daemon(tmp_path)
    assert d._shutdown_event.is_set() is False
    d._shutdown_event.set()
    assert d._shutdown_event.is_set() is True


# --- option D: index-drift / DB-invalidation defense -----------------------


def test_is_fatal_invalidation_matches_index_drift_strings():
    """The predicate must catch both the ART/index drift string and the
    follow-up `database has been invalidated` message that DuckDB emits
    once it poisons the connection."""
    drift = RuntimeError(
        "FATAL Error: Invalid Input Error: Failed to delete all rows "
        "from index. Only deleted 1 out of 54 rows."
    )
    invalidated = RuntimeError(
        "FATAL Error: Failed: database has been invalidated because of "
        "a previous fatal error. The database must be restarted prior "
        "to being used again."
    )
    benign = RuntimeError("table does not exist")

    assert Daemon._is_fatal_invalidation(drift) is True
    assert Daemon._is_fatal_invalidation(invalidated) is True
    assert Daemon._is_fatal_invalidation(benign) is False


def test_fast_exit_skips_when_exception_is_benign(tmp_path):
    """`_fast_exit_if_invalidated` must NOT exit the test process on a
    benign error. If it bailed, this test would never finish."""
    d = _make_daemon(tmp_path)
    # No log_fh set; the helper tolerates that.
    d._fast_exit_if_invalidated(RuntimeError("unrelated bug"), "test")
    # If we got here, no os._exit happened. Also: armed flag stays clear.
    assert d._fast_exit_armed is False


def test_fast_exit_armed_flag_is_thread_idempotent(tmp_path, monkeypatch):
    """When the helper does decide to exit, it must arm exactly once even
    if many threads race the same FatalException. We patch os._exit to
    raise SystemExit so we can observe the call without killing pytest."""
    d = _make_daemon(tmp_path)

    calls = []

    def _fake_exit(code: int) -> None:  # type: ignore[no-redef]
        calls.append(code)
        raise SystemExit(code)

    monkeypatch.setattr("os._exit", _fake_exit)
    exc = RuntimeError(
        "FATAL Error: Failed: database has been invalidated"
    )
    try:
        d._fast_exit_if_invalidated(exc, "test")
    except SystemExit:
        pass
    assert d._fast_exit_armed is True
    assert calls == [2]
    # Second call from a sibling thread is a no-op (armed gate).
    d._fast_exit_if_invalidated(exc, "test-second")
    assert calls == [2]


# ---- the model-worker stage of a stop (bug-269, bug-278, bug-272; ruling L177) -------------
#
# A stop must not wait on a model client's lock: not on a private worker's warm-up load
# (bug-269), not on a hub-shared call in flight (bug-278, ch-bsd t03 r1 B1), and a client built
# after the stage ran must not serve (bug-272, M1). Every check below is an ordering or a state,
# never a clock: a gate the test owns says when the lock is held, and a hang guard only raises.

import os  # noqa: E402
import socket  # noqa: E402
import tempfile  # noqa: E402
import textwrap  # noqa: E402

import pytest  # noqa: E402

from refmatrix import daemon as dm  # noqa: E402

# A wait the test is not measuring; it only turns a hang into a failure.
_GUARD_S = 140.0


class _MuteHub:
    """A unix socket at `RMX_MODEL_SOCK` that accepts, reads the request, and never answers:
    a hub mid-restart or a cold shared worker. Fake process boundary (the hub), registered in
    workflow/test_mock_registry.md. `got_request` is set once a frame's bytes arrive, i.e. once
    a client call is in recv holding its `_lock`."""

    def __init__(self, path: str):
        self.path = path
        self.srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.srv.bind(path)
        self.srv.listen(8)
        self.conns: list = []
        self.got_request = threading.Event()
        self._t = threading.Thread(target=self._serve, daemon=True)
        self._t.start()

    def _serve(self):
        while True:
            try:
                c, _ = self.srv.accept()
            except OSError:
                return
            self.conns.append(c)
            threading.Thread(target=self._read, args=(c,), daemon=True).start()

    def _read(self, c):
        try:
            while c.recv(65536):
                self.got_request.set()
        except OSError:
            pass

    def close(self):
        for c in self.conns:
            try:
                c.close()
            except OSError:
                pass
        self.srv.close()


def test_close_workers_does_not_wait_on_a_shared_call_held_by_a_mute_hub(tmp_path, monkeypatch):
    """bug-278 (ch-bsd t03 r1 B1). With the hub up, `_embed_worker` is a `SharedWorkerClient`;
    its `close()` takes `_lock`, which `call()` holds through send/recv, so a stop waited for the
    in-flight call's own timeout (SHARED_OP_TIMEOUT_S = 45 s per role in production). Here the
    call's timeout is `CALL_TIMEOUT_S`; the stop must not be what ends it: the call may fail
    (the client was abandoned) but not by its own TimeoutError, and an abandoned client must not
    reconnect to the hub."""
    from refmatrix import modelsrv
    CALL_TIMEOUT_S = 20.0
    short = tempfile.mkdtemp(prefix="sh", dir=os.environ.get("RMX_SANDBOX_ROOT") or None)
    sock = os.path.join(short, "m.sock")
    monkeypatch.setenv("RMX_MODEL_SOCK", sock)
    hub = _MuteHub(sock)
    d = _make_daemon(tmp_path)
    c = modelsrv.SharedWorkerClient("embed", timeout=CALL_TIMEOUT_S)
    d._embed_worker, d._rerank_worker = c, None
    events: list = []

    def inflight():
        try:
            c.call("embed", {"texts": ["x"]}, timeout=CALL_TIMEOUT_S)
            events.append(("call", "returned"))
        except Exception as exc:  # noqa: BLE001 — the outcome IS the assertion
            events.append(("call", type(exc).__name__))

    th = threading.Thread(target=inflight, daemon=True)
    th.start()
    try:
        assert hub.got_request.wait(_GUARD_S), "the in-flight call never reached the hub"
        closer = threading.Thread(target=lambda: (d._close_workers(),
                                                  events.append(("close", "returned"))),
                                  daemon=True)
        closer.start()
        closer.join(_GUARD_S)
        th.join(_GUARD_S)
        assert not closer.is_alive() and not th.is_alive(), f"hang guard: {events}"
        call_end = dict(events)["call"]
        assert call_end != "TimeoutError", (
            f"bug-278: the stop waited out the in-flight shared call: it ended by its own "
            f"TimeoutError ({CALL_TIMEOUT_S:.0f} s) and only then did _close_workers return; "
            f"order {events}")
        assert len(hub.conns) == 1, (
            f"the abandoned shared client reconnected to the hub ({len(hub.conns)} connections)")
        assert d._embed_worker is None
    finally:
        hub.close()
        c.close()


_PRELOAD = r'''
"""bug-269 preload (registered in workflow/test_mock_registry.md): hold the embed worker's cold
load open. Acts only in `python -m refmatrix.embed_worker --role embed`. No parent-death exit
during the hold: the daemon's stop must kill this process itself (ch-bsd t03 r1 S1)."""
import os, sys, time
from pathlib import Path

argv = list(getattr(sys, "orig_argv", sys.argv))
if "refmatrix.embed_worker" in argv and "embed" in argv[argv.index("--role") + 1:][:1]:
    import refmatrix.embedder as _emb
    _d = Path(os.environ["T269_HOLD_DIR"])
    _hold_s = float(os.environ["T269_HOLD_S"])
    _real = _emb.Embedder.__init__

    def _held_init(self, *a, **kw):
        (_d / "held").write_text(str(os.getpid()))
        end = time.monotonic() + _hold_s
        while time.monotonic() < end and not (_d / "release").exists():
            time.sleep(0.05)
        (_d / "released").write_text(str(os.getpid()))
        return _real(self, *a, **kw)

    _emb.Embedder.__init__ = _held_init
'''
# The held warm-up: far longer than a stop that does not wait on it.
_HOLD_S = 20.0


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_a_stop_during_warmup_abandons_the_held_load():
    """bug-269 (ruling L161), with ch-bsd t03 r1 S1/S2 folded in. A real sandbox daemon whose
    embed worker's cold load is held open; the stop op is sent during the hold. Outcomes:
    the daemon exits while the load is still held; the held worker is already dead then (the
    stop killed it: M3); this launch spawned exactly one embed worker and the warm-up hit
    `not respawning` (the retired flag: M4); the reranker warm-up was skipped and never spawned
    (M5); the in-process embedder fallback refused and loaded nothing (M6)."""
    from tests import task21_1_support as h
    root = Path(os.environ["REFMATRIX_ROOT"])
    hold = root.parent / "t269-hold"
    hold.mkdir()
    pre = root.parent / "t269_preload.py"
    pre.write_text(textwrap.dedent(_PRELOAD))
    d = h.SandboxDaemon(root, RMX_SANDBOX_PRELOAD=str(pre), T269_HOLD_DIR=str(hold),
                        T269_HOLD_S=str(_HOLD_S))

    def log() -> str:
        return (root / "rmxd.log").read_bytes()[d.log_offset:].decode(errors="replace")

    def wait(pred, what):
        end = time.monotonic() + _GUARD_S
        while time.monotonic() < end:
            if pred():
                return
            time.sleep(0.05)
        raise AssertionError(f"hang guard: {what}; daemon rc={d.proc.poll()}; log:\n{log()}")

    try:
        wait(lambda: (hold / "held").exists(), "the embed worker never entered its held load")
        held_pid = int((hold / "held").read_text())
        assert d.proc.poll() is None, "the daemon exited before the stop was sent"
        dm.call(root, "stop", {}, timeout=2.0, retries=0)
        wait(lambda: d.proc.poll() is not None or (hold / "released").exists(),
             "neither the daemon exit nor the end of the hold")
        exited_first = d.proc.poll() is not None and not (hold / "released").exists()
        held_dead = not _pid_alive(held_pid)
        if not exited_first:
            wait(lambda: d.proc.poll() is not None, "the daemon never exited after the hold")
        text = log()
        assert exited_first, (
            f"bug-269: the stop waited out the warm-up: the held load was released (after the "
            f"{_HOLD_S:.0f} s hold) before the daemon exited; log:\n{text}")
        assert held_dead, (
            f"the stop left the held embed worker pid={held_pid} alive (it was not killed); "
            f"log:\n{text}")
        assert text.count("worker[embed] spawned") == 1 and "not respawning" in text, (
            f"the abandoned embed client respawned, or its holder never saw it retired; "
            f"log:\n{text}")
        # The embed path first: the reranker step runs only after it (M6 before M5).
        assert "daemon stopping: no in-process embedder fallback" in text, (
            f"the in-process embedder fallback did not refuse once the stop began; log:\n{text}")
        assert "embedder loaded model=" not in text, (
            f"the embedder was loaded in-process in the stopping daemon; log:\n{text}")
        assert "reranker warmup skipped: the daemon is stopping" in text, (
            f"the reranker warm-up was not skipped once the stop began; log:\n{text}")
        assert "worker[rerank] spawned" not in text, (
            f"a reranker worker was spawned into the stopping daemon; log:\n{text}")
    finally:
        (hold / "release").write_text("1")
        d.stop()


@pytest.mark.parametrize("role", ["embed", "rerank"])
def test_a_model_client_built_after_the_worker_stage_cannot_serve(tmp_path, monkeypatch, role):
    """bug-272 (ch-bsd t03 r1 M1). `_shutdown_event` is set, then `_close_workers` reads the
    slots without `_worker_lock`; a warm thread inside `new_model_client` (its shared probe can
    take PROBE_TIMEOUT_S) assigns its client after that. This is that order, made exact: the
    stop has begun and the worker stage has run, THEN `_model_client` builds a private client.
    It must not be able to start a model process (or `_model_client` refuses outright).
    `RMX_SHARED_MODELS=0` sends `new_model_client` straight to the private worker; `ping` spawns
    the worker without loading a model."""
    from refmatrix.subproc import WorkerError
    monkeypatch.setenv("RMX_SHARED_MODELS", "0")
    d = _make_daemon(tmp_path)
    attr = "_embed_worker" if role == "embed" else "_rerank_worker"
    d._shutdown_event.set()
    d._close_workers()
    client = None
    try:
        try:
            client = d._model_client(role)
        except RuntimeError as exc:
            assert "stopping" in str(exc), exc
        slot = getattr(d, attr, None) or client
        if slot is None:
            return
        try:
            slot.call("ping", timeout=30.0)
            served = True
        except WorkerError as exc:
            served = False
            assert "not respawning" in str(exc), exc
        pid = getattr(getattr(slot, "_proc", None), "pid", None)
        assert not served and pid is None, (
            f"bug-272: a private {role} client built after the stop's worker stage spawned a "
            f"model process (pid={pid}) and served; nothing will retire it")
    finally:
        for c in {id(x): x for x in (client, getattr(d, attr, None)) if x is not None}.values():
            c.close()
