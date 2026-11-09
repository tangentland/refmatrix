"""Task 3.7 remedy round 4 — RED (spec #remedy-r4-red; ch-bsd
`workflow/bullshit/2026-11-09-0115-task-3.7-remedy-r3-b0cc89b.md`).

B-1  bug-173. A daemonless process whose PRIVATE embed worker cannot start loads a fresh
     in-process `Embedder()` on EVERY call (3 calls, 3 loads, under `RMX_SHARED_MODELS` 0
     and 1). The in-process model is ~610 MB and a 6-33 s load; r2's own contract says it
     must not load per call. Required: at most ONE in-process load per process across N
     calls while the private worker cannot spawn, and the hub is still re-adopted when it
     answers again.
S-1  The daemonless re-probe runs on the request path, under `_EMBED_CLIENT_LOCK`, with
     `info(timeout=PROBE_TIMEOUT_S)` (45 s default). Behind a mute hub (accepts, never
     answers) two concurrent calls took 45 s and 90 s, and the next call paid 45 s again.
     And a build that just probed, failed and went private CLEARS the throttle, so the
     next call probes again at once. Required: (a) each of two concurrent calls behind a
     mute hub finishes within `REQUEST_PATH_CEILING_S`, independent of `PROBE_TIMEOUT_S`;
     the next call inside the backoff window does not probe; (b) after a build that fell
     back to private the throttle is SET: the second call inside `RMX_SHARED_REPROBE_S`
     makes no connection to the hub socket.
M-1  Mutation killers for three r3 lines that survived (`bsd-r3-mutations.log`):
     M3  `retire` -> `close` on the daemonless swap: an embedder captured BEFORE the swap
         must be refused afterwards ("retired ... not respawning"), not respawn a worker.
     M10 a successful re-probe no longer pops `backoff` / `next_at`: after adopt, hub
         loss, the next private stint must start at `base`, not the doubled wait — pinned
         on `reprobe_shared_client` AND on the daemon's `_maybe_adopt_shared`.
     M12 the named close-failure line in the re-probe ("closing the unusable shared client
         failed") is asserted when the probe's `close` raises behind a mute socket.

The request-path bound. `PROBE_TIMEOUT_S` is the COLD-worker probe of `new_model_client`
(a cold hub worker loads its model first: 14.9 s embed, 33 s rerank, bug-014); it stays
there. The request-path re-probe asks a worker the hub ALREADY serves, so it needs a
short bound of its own: 1.0 s or less (two times `shared_available`'s 0.5 s connect
bound). The test raises `PROBE_TIMEOUT_S` to 6 s, so any request-path use of it fails,
and allows each concurrent call `REQUEST_PATH_CEILING_S` = 2.5 s: two request-path probes
of 1.0 s back to back (a caller serialised behind another's probe) plus 0.5 s for the
stub worker round trip and thread scheduling. At HEAD the calls take ~6 s and ~12 s.

Doubles: the r2 rig (`tests/test_task3_7_remedy_r2.py`, registry rows "task 3.7 remedy
r2/r3"), extended here (registry row "task 3.7 remedy r4"): the two re-probe throttle
dicts are reset per test; a `WorkerClient` subclass whose argv exits at once (a private
worker that cannot spawn, the bsd-r3 bug-173 probe shape); the mute hub is the REAL unix
socket `_StubHub(answer=False)` from `tests/test_shared_worker_readoption.py` (accepts,
reads the frame, never replies) — no function under test is patched. M12 replaces
`SharedWorkerClient.close` with one that raises, because the line under test is what the
re-probe says when that close raises; M10's daemon test uses the readoption suite's
`_FakePrivate` (adoption only needs a non-shared client to close).
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

from refmatrix import daemon as dm
from refmatrix import modelsrv
from refmatrix import recall as recall_mod
from refmatrix import subproc
from refmatrix.subproc import WorkerError
from tests.test_shared_worker_readoption import _FakePrivate, _StubHub
from tests.test_task3_7_remedy_r2 import _one_call, rig  # noqa: F401 — the fixture

REQUEST_PATH_CEILING_S = 2.5
COLD_PROBE_S = 6.0          # PROBE_TIMEOUT_S under test: must never be paid on a request


@pytest.fixture
def rig4(rig, monkeypatch):
    """The r2 rig plus a clean re-probe throttle: `_EMBED_REPROBE_NEXT` / `_BACKOFF` are
    process-wide dicts the r2/r3 rig never reset, so throttle state leaked between
    tests."""
    monkeypatch.setattr(recall_mod, "_EMBED_REPROBE_NEXT", {}, raising=False)
    monkeypatch.setattr(recall_mod, "_EMBED_REPROBE_BACKOFF", {}, raising=False)
    rig["sock"] = rig["root"] / "models.sock"
    yield rig


def _unspawnable_private(monkeypatch):
    """A real `WorkerClient` whose model process exits at once (rc=3): a sandbox that
    forbids the spawn, an interpreter the child cannot reach (bsd-r3-probe_173.py)."""
    made: list = []
    real = subproc.WorkerClient.__mro__[0]
    while real.__module__ != subproc.__name__:   # unwrap the rig's stub subclass
        real = real.__mro__[1]

    class _DeadOnArrival(real):
        def __init__(self, role, **kw):
            kw.setdefault("argv", [sys.executable, "-c", "raise SystemExit(3)"])
            kw.setdefault("timeout", 5.0)
            super().__init__(role, **kw)
            made.append(self)

    monkeypatch.setattr(subproc, "WorkerClient", _DeadOnArrival)
    return made


def _brief(calls):
    return [{k: (v if k != "client" else type(v).__name__) for k, v in o.items()}
            for o in calls]


# ---- B-1 (bug-173): one in-process load per process, not one per call ----------------------


@pytest.mark.timeout(90)
@pytest.mark.parametrize("shared_models", ["0", "1"])
def test_an_unspawnable_private_worker_loads_the_in_process_model_at_most_once(
        rig4, monkeypatch, shared_models):
    monkeypatch.setenv("RMX_SHARED_MODELS", shared_models)
    # Probe on every call: a re-probe never hides behind the backoff window here.
    monkeypatch.setenv("RMX_SHARED_REPROBE_S", "0")
    monkeypatch.setenv("RMX_SHARED_REPROBE_MAX_S", "0")
    _unspawnable_private(monkeypatch)
    root, logs = rig4["root"], []
    assert not rig4["sock"].exists()            # no hub at all

    calls = [_one_call(root, logs) for _ in range(4)]
    shown = _brief(calls)
    # Precondition (green at HEAD): every call is served, by the in-process model.
    assert all(o["ok"] and o["model"] == "in-process" for o in calls), shown
    assert len(rig4["loads"]) <= 1, (
        f"bug-173: the in-process model loaded {len(rig4['loads'])}x across "
        f"{len(calls)} daemonless calls with RMX_SHARED_MODELS={shared_models} and a "
        f"private worker that cannot spawn (each load ~610 MB, 6-33 s): {shown}")

    if shared_models == "1":
        # And the cached fallback must not pin the process: the hub is re-adopted.
        rig4["start_hub"]()
        back: list = []
        for _ in range(3):
            back.append(_one_call(root, logs))
            if back[-1]["ok"] and back[-1]["model"] == "stub/hub":
                break
        shown = _brief(back)
        assert back[-1]["ok"] and back[-1]["model"] == "stub/hub", (
            f"the process never returned to the hub within 3 calls of it answering "
            f"after an in-process fallback: {shown}")
        assert isinstance(recall_mod._EMBED_CLIENT, modelsrv.SharedWorkerClient), shown
        assert len(rig4["loads"]) <= 1, (len(rig4["loads"]), shown)


# ---- S-1: the request-path re-probe is bounded and throttled -------------------------------


@pytest.mark.timeout(90)
def test_two_concurrent_calls_behind_a_mute_hub_finish_within_the_request_path_bound(
        rig4, monkeypatch):
    monkeypatch.setattr(modelsrv, "PROBE_TIMEOUT_S", COLD_PROBE_S)
    monkeypatch.setenv("RMX_SHARED_REPROBE_S", "2")
    monkeypatch.setenv("RMX_SHARED_REPROBE_MAX_S", "60")
    root, logs = rig4["root"], []

    # No hub: the build goes private without probing (no socket file).
    first = _one_call(root, logs)
    assert first["ok"] and first["model"] == "stub/private", _brief([first])
    time.sleep(2.2)                              # past the base window: a re-probe is due

    hub = _StubHub(rig4["sock"], answer=False)   # a hub mid-restart: accepts, never answers
    try:
        out: dict = {}

        def call(tag):
            t0 = time.monotonic()
            o = _one_call(root, logs)
            o["s"] = round(time.monotonic() - t0, 2)
            out[tag] = o

        ts = [threading.Thread(target=call, args=(t,)) for t in ("A", "B")]
        for t in ts:
            t.start()
        for t in ts:
            t.join(timeout=60)
        shown = {k: _brief([v])[0] for k, v in out.items()}
        assert set(out) == {"A", "B"}, f"a concurrent call never returned: {shown}"
        assert all(o["ok"] and o["model"] == "stub/private" for o in out.values()), shown
        slow = {k: o["s"] for k, o in out.items() if o["s"] > REQUEST_PATH_CEILING_S}
        assert not slow, (
            f"ch-bsd r3 #s-1: concurrent calls behind a mute hub stalled on the request-"
            f"path re-probe {slow} (bound {REQUEST_PATH_CEILING_S}s; PROBE_TIMEOUT_S="
            f"{COLD_PROBE_S}s is the cold-worker probe and must not be paid here): {shown}")

        time.sleep(0.3)
        before = hub.connections
        t0 = time.monotonic()
        nxt = _one_call(root, logs)
        took = time.monotonic() - t0
        time.sleep(0.3)
        assert nxt["ok"] and nxt["model"] == "stub/private", _brief([nxt])
        assert hub.connections == before and took < 1.0, (
            f"the call after a failed re-probe probed again inside the backoff window: "
            f"{hub.connections - before} new hub connection(s), {took:.2f}s")
    finally:
        hub.close()


@pytest.mark.timeout(60)
def test_a_build_that_fell_back_to_private_sets_the_reprobe_throttle(rig4, monkeypatch):
    monkeypatch.setattr(modelsrv, "PROBE_TIMEOUT_S", 0.5)
    monkeypatch.setenv("RMX_SHARED_REPROBE_S", "300")
    monkeypatch.setenv("RMX_SHARED_REPROBE_MAX_S", "1800")
    root, logs = rig4["root"], []
    hub = _StubHub(rig4["sock"], answer=False)
    try:
        # The build probes the mute hub (new_model_client's cold probe), fails, goes private.
        first = _one_call(root, logs)
        assert first["ok"] and first["model"] == "stub/private", _brief([first])
        time.sleep(0.3)
        assert hub.connections >= 1, "precondition: the build never probed the hub"
        before = hub.connections

        second = _one_call(root, logs)
        time.sleep(0.3)
        assert second["ok"] and second["model"] == "stub/private", _brief([second])
        assert hub.connections == before, (
            f"ch-bsd r3 #s-1: the build that just probed the hub and went private left "
            f"the throttle clear, so the very next call (inside RMX_SHARED_REPROBE_S=300) "
            f"probed again: {hub.connections - before} new hub connection(s); "
            f"next_at={dict(recall_mod._EMBED_REPROBE_NEXT)}")
    finally:
        hub.close()


# ---- M-1 / M3: a captured private embedder is retired by the swap --------------------------


@pytest.mark.timeout(60)
def test_an_embedder_captured_before_the_hub_swap_is_refused_not_respawned(rig4, monkeypatch):
    monkeypatch.setenv("RMX_SHARED_REPROBE_S", "0")
    monkeypatch.setenv("RMX_SHARED_REPROBE_MAX_S", "0")
    root, logs = rig4["root"], []
    captured = recall_mod.shared_embedder(root, log=logs.append)
    captured.embed_texts(["a"])
    private = recall_mod._EMBED_CLIENT
    assert isinstance(private, subproc.WorkerClient), type(private)
    assert captured.model_name == "stub/private"

    rig4["start_hub"]()
    fresh = _one_call(root, logs)
    assert fresh["ok"] and fresh["model"] == "stub/hub", _brief([fresh])

    with pytest.raises(WorkerError, match=r"retired.*not respawning"):
        captured.embed_texts(["c"])
    assert private._proc is None, (
        f"the swapped-away private client respawned a worker pid={private._proc.pid}")


# ---- M-1 / M10: a successful re-probe clears the backoff ------------------------------------


@pytest.mark.timeout(60)
def test_a_successful_reprobe_clears_the_backoff_so_the_next_stint_starts_at_base(
        rig4, monkeypatch):
    monkeypatch.setattr(modelsrv, "PROBE_TIMEOUT_S", 2.0)
    monkeypatch.setenv("RMX_SHARED_REPROBE_S", "100")
    monkeypatch.setenv("RMX_SHARED_REPROBE_MAX_S", "1000")
    nxt: dict = {}
    back: dict = {}
    logs: list = []
    t = 1_000_000.0
    assert recall_mod.reprobe_shared_client("embed", next_at=nxt, backoff=back,
                                            log=logs.append, now=t) is None
    t = nxt["embed"]
    assert recall_mod.reprobe_shared_client("embed", next_at=nxt, backoff=back,
                                            log=logs.append, now=t) is None
    assert back["embed"] == 200, back            # precondition: the wait doubled
    t = nxt["embed"]
    hub = rig4["start_hub"]()
    client = recall_mod.reprobe_shared_client("embed", next_at=nxt, backoff=back,
                                              log=logs.append, now=t)
    try:
        assert isinstance(client, modelsrv.SharedWorkerClient), client
        assert "embed" not in back and "embed" not in nxt, (
            f"a successful re-probe left the throttle behind: backoff={back} "
            f"next_at={nxt}")
    finally:
        if client is not None:
            client.close()
    rig4["kill_hub"](hub)
    t += 500
    assert recall_mod.reprobe_shared_client("embed", next_at=nxt, backoff=back,
                                            log=logs.append, now=t) is None
    assert round(nxt["embed"] - t) == 100, (
        f"after adopt + hub loss the next private stint waits {nxt['embed'] - t:.0f}s, "
        f"not the base 100s: backoff={back}")


@pytest.fixture
def daemon4(monkeypatch):
    base = Path(tempfile.mkdtemp(prefix="r37r4d-", dir="/tmp"))
    root = base / "p" / ".refmatrix"
    root.parent.mkdir(parents=True)
    sock = base / "models.sock"
    monkeypatch.setenv("RMX_MODEL_SOCK", str(sock))
    monkeypatch.setenv("RMX_SHARED_MODELS", "1")
    d = dm.Daemon(root)
    logs: list = []
    d._log = logs.append
    yield d, sock, logs
    for w in (getattr(d, "_embed_worker", None), getattr(d, "_rerank_worker", None)):
        if isinstance(w, modelsrv.SharedWorkerClient):
            w.close()
    shutil.rmtree(base, ignore_errors=True)


@pytest.mark.timeout(60)
def test_the_daemon_after_adopt_and_hub_loss_reprobes_at_base(daemon4, monkeypatch):
    d, sock, logs = daemon4
    monkeypatch.setattr(modelsrv, "PROBE_TIMEOUT_S", 2.0)
    monkeypatch.setenv("RMX_SHARED_REPROBE_S", "100")
    monkeypatch.setenv("RMX_SHARED_REPROBE_MAX_S", "1000")
    d._embed_worker = _FakePrivate()

    t = 1_000_000.0
    assert d._maybe_adopt_shared(now=t) == []            # no hub: wait 100
    t = d._reprobe_next["embed"]
    assert d._maybe_adopt_shared(now=t) == []            # still none: wait 200
    assert d._reprobe_backoff["embed"] == 200, d._reprobe_backoff
    t = d._reprobe_next["embed"]
    hub = _StubHub(sock)
    try:
        assert d._maybe_adopt_shared(now=t) == ["embed"], logs
    finally:
        hub.close()
    assert "embed" not in d._reprobe_backoff and "embed" not in d._reprobe_next, (
        f"the daemon adopted the hub but kept its throttle: "
        f"backoff={d._reprobe_backoff} next_at={d._reprobe_next}")

    # The hub goes away; the daemon is private again (whatever brought it there).
    d._embed_worker.close()
    d._embed_worker = _FakePrivate()
    t += 500
    assert d._maybe_adopt_shared(now=t) == []
    assert round(d._reprobe_next["embed"] - t) == 100, (
        f"the daemon's next private stint waits {d._reprobe_next['embed'] - t:.0f}s, not "
        f"the base 100s (a success did not clear the doubled backoff): "
        f"{d._reprobe_backoff}")


# ---- M-1 / M12: the named close-failure line of the re-probe --------------------------------


@pytest.mark.timeout(60)
def test_a_failing_close_of_the_mute_probe_client_is_named_in_the_log(daemon4, monkeypatch):
    d, sock, logs = daemon4
    monkeypatch.setattr(modelsrv, "PROBE_TIMEOUT_S", 0.5)

    def _raising_close(self, *, timeout: float = 0.0):
        raise RuntimeError("close boom r4")

    monkeypatch.setattr(modelsrv.SharedWorkerClient, "close", _raising_close)
    priv = _FakePrivate()
    d._embed_worker = priv
    hub = _StubHub(sock, answer=False)
    try:
        assert d._maybe_adopt_shared(now=time.time() + 10_000) == []
    finally:
        hub.close()
    assert d._embed_worker is priv and priv.closed is False
    named = [m for m in logs if "closing the unusable shared client failed" in m]
    assert named and "close boom r4" in named[0], (
        f"the re-probe's close of the unusable shared client raised and the log did not "
        f"name it: {logs}")
