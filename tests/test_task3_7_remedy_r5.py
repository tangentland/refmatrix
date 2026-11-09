"""Task 3.7 remedy round 5 — RED (spec #remedy-r5; ch-bsd
`workflow/bullshit/2026-11-09-0224-task-3.7-remedy-r4-e4faf32.md`, id
`bsd-task3.7-remedy-r4-e4faf32`, probe logs `workflow/review-output/task-3.7/bsd-r5-*.log`).

M-1  Mutation killers for three r4 lines that survived `bsd-r5-mutations.log` (green at
     HEAD; each is proven against its mutation in `r5-mutations.log`):
     F2   the `_EMBED_REPROBE_INFLIGHT = False` clear moved out of `finally`: a request-path
          probe that RAISES must still leave the flag clear, and the next eligible call
          must probe (and here adopt) the hub.
     F8   the swap no longer drops `_EMBED_INPROC`: after re-adoption the stand-in is
          gone (`_EMBED_INPROC is None`) and the model object is freed (weakref dead).
     F13  the stand-in loader no longer closes the failed private worker: after the
          stand-in loads, the failed client's `_proc` is None and every child it spawned
          is reaped (no zombie).
M-2  A malformed `RMX_SHARED_REPROBE_S` (operator typo `300s`) with a HEALTHY private
     worker and no hub. Observed at HEAD (`bsd-r5-probe-badenv.log`): under
     `RMX_SHARED_MODELS=1` 4 calls gave 4 UNCACHED in-process loads, with the
     `ValueError` repeated as a WARNING on every call; under `=0` call 1 loaded in-process
     (`hold_reprobe` parsed the env even though no hub is possible). Intended (spec
     #remedy-r5 decision): a malformed env falls back to the defaults with ONE WARNING that
     names the variable, and `hold_reprobe` is skipped when shared models are disabled. So:
     every call is served by the private worker, ZERO in-process loads, exactly one named
     warning (under `=1`; at most one under `=0`), and the throttle holds the default base.
M-3  A cold hub worker: the socket CONNECTS and only the info header times out. Observed at
     HEAD (`bsd-r5-probe-coldhub.log`): the miss doubled the backoff, so adoption took
     base + 2*base. Intended: connect-ok / header-timeout re-arms at BASE; an absent or
     refused socket (no hub, or a stale socket file nobody listens on) still doubles, so
     the fix cannot simply stop doubling.

Doubles (registry row "task 3.7 remedy r5"): the r4 rig (`rig4`, which is the r2 rig
plus a clean throttle), extended here to also reset `recall._EMBED_INPROC` and
`recall._EMBED_REPROBE_INFLIGHT`; r4's `_DeadOnArrival` private worker (argv exits at
once), here subclassed once more to record each spawned pid; a pass-through spy on
`modelsrv.shared_enabled` that raises ONCE when called from `reprobe_shared_client` (F2:
the probe that raises; it is a dependency of the function under test, the `finally` in
`_process_embed_client`, not the function itself); and `_SlowHub`, a `_StubHub` whose
handler answers only after `delay` seconds (a REAL unix socket: connect succeeds, the
header times out). `reprobe_shared_client`, `hold_reprobe`, `_reprobe_window`,
`_process_embed_client`, `_load_process_inproc_standin`, `shared_embedder`,
`SharedWorkerClient` and `WorkerClient.close` run unpatched.
"""
from __future__ import annotations

import gc
import logging
import os
import socket
import sys
import time
import weakref

import pytest

from refmatrix import modelsrv
from refmatrix import recall as recall_mod
from refmatrix import subproc
from refmatrix.subproc import recv_frame, send_frame
from tests.test_shared_worker_readoption import _StubHub, _version
from tests.test_task3_7_remedy_r2 import _one_call, rig  # noqa: F401 — the fixture
from tests.test_task3_7_remedy_r4 import _brief, _unspawnable_private, rig4  # noqa: F401


@pytest.fixture
def rig5(rig4, monkeypatch):
    """The r4 rig plus the two r4 globals it does not reset: the in-process stand-in and
    the in-flight flag (both process-wide; a test that leaves either set decides the
    next test's outcome)."""
    monkeypatch.setattr(recall_mod, "_EMBED_INPROC", None, raising=False)
    monkeypatch.setattr(recall_mod, "_EMBED_REPROBE_INFLIGHT", False, raising=False)
    yield rig4


class _SlowHub(_StubHub):
    """A hub whose worker is COLD: it accepts, reads the frame, and answers only after
    `delay` seconds (the model load of a freshly (re)started hub, 6-33 s live). The
    connect succeeds; a bounded `info` times out."""

    def __init__(self, path, *, delay: float):
        self.delay = float(delay)                # set before the accept thread starts
        super().__init__(path, answer=True)

    def _handle(self, conn):
        rw = conn.makefile("rwb")
        try:
            req, _ = recv_frame(rw)
        except (EOFError, OSError):
            return
        if self._stop.wait(self.delay):
            return
        try:
            send_frame(rw, {"ok": True, "model": "stub", "dim": 384,
                            "version": _version(), "op": req.get("op")})
        except OSError:
            return                               # the prober already gave up


def _unspawnable_private_with_pids(monkeypatch):
    """r4's `_DeadOnArrival` (argv exits at once), recording every child pid it spawns."""
    made = _unspawnable_private(monkeypatch)
    dead_on_arrival = subproc.WorkerClient
    pids: list = []

    class _DeadOnArrivalPids(dead_on_arrival):
        def _spawn(self) -> None:
            super()._spawn()
            pids.append(self._proc.pid)

    monkeypatch.setattr(subproc, "WorkerClient", _DeadOnArrivalPids)
    return made, pids


def _settle(hub, *, quiet_s: float = 0.5, limit_s: float = 3.0) -> int:
    """Let the stub's accept loop catch up: wait until `connections` stops moving."""
    deadline = time.monotonic() + limit_s
    seen = hub.connections
    quiet_until = time.monotonic() + quiet_s
    while time.monotonic() < min(deadline, quiet_until):
        time.sleep(0.05)
        if hub.connections != seen:
            seen = hub.connections
            quiet_until = time.monotonic() + quiet_s
    return seen


# ---- M-1 / F2: a probe that raises still clears the in-flight flag ---------------------------


@pytest.mark.timeout(60)
def test_a_request_path_probe_that_raises_clears_the_inflight_flag_and_the_next_call_probes(
        rig5, monkeypatch):
    monkeypatch.setenv("RMX_SHARED_REPROBE_S", "0")     # a re-probe is due on every call
    monkeypatch.setenv("RMX_SHARED_REPROBE_MAX_S", "0")
    root, logs = rig5["root"], []

    first = _one_call(root, logs)                       # no hub: the build goes private
    assert first["ok"] and first["model"] == "stub/private", _brief([first])
    private = recall_mod._EMBED_CLIENT
    assert isinstance(private, subproc.WorkerClient), type(private)

    real_enabled = modelsrv.shared_enabled
    raised: list = []

    def _spy_enabled() -> bool:
        # Raise ONCE, and only inside the request-path re-probe: the probe that raises
        # past its own `except` (as `_reprobe_window`'s `float()` did on a typo'd env).
        if not raised and sys._getframe(1).f_code.co_name == "reprobe_shared_client":
            raised.append(1)
            raise RuntimeError("probe boom r5")
        return real_enabled()

    monkeypatch.setattr(modelsrv, "shared_enabled", _spy_enabled)
    second = _one_call(root, logs)
    assert raised == [1], (
        f"precondition: the request-path re-probe never ran (so it never raised): "
        f"{_brief([second])} {logs}")
    assert recall_mod._EMBED_REPROBE_INFLIGHT is False, (
        "a request-path re-probe that RAISED left `_EMBED_REPROBE_INFLIGHT` set: no later "
        "call of this process will ever re-probe, and the hub is never re-adopted (the "
        "clear must sit in `finally`)")

    rig5["start_hub"]()
    third = _one_call(root, logs)
    assert third["ok"] and third["model"] == "stub/hub", (
        f"after a re-probe that raised, the next eligible call did not probe the "
        f"answering hub: {_brief([third])} inflight={recall_mod._EMBED_REPROBE_INFLIGHT}")
    assert isinstance(recall_mod._EMBED_CLIENT, modelsrv.SharedWorkerClient)


# ---- M-1 / F8: re-adoption drops (and frees) the in-process stand-in -------------------------


@pytest.mark.timeout(90)
def test_readoption_drops_and_frees_the_in_process_standin(rig5, monkeypatch):
    monkeypatch.setenv("RMX_SHARED_MODELS", "1")
    monkeypatch.setenv("RMX_SHARED_REPROBE_S", "0")
    monkeypatch.setenv("RMX_SHARED_REPROBE_MAX_S", "0")
    _unspawnable_private(monkeypatch)
    root, logs = rig5["root"], []

    first = _one_call(root, logs)
    assert first["ok"] and first["model"] == "in-process", _brief([first])
    held = recall_mod._EMBED_INPROC
    assert held is not None and held[0] is recall_mod._EMBED_CLIENT, (
        f"precondition: no stand-in was cached for the failed private client: {held!r}")
    standin = weakref.ref(held[1])
    del held

    rig5["start_hub"]()
    back: list = []
    for _ in range(3):
        back.append(_one_call(root, logs))
        if back[-1]["ok"] and back[-1]["model"] == "stub/hub":
            break
    assert back[-1]["ok"] and back[-1]["model"] == "stub/hub", _brief(back)
    assert recall_mod._EMBED_INPROC is None, (
        f"the process re-adopted the hub but kept its in-process stand-in "
        f"({recall_mod._EMBED_INPROC!r}): ~610 MB retained for nothing; the swap must drop "
        f"`_EMBED_INPROC` (the docstring's 'dropped when the hub is re-adopted')")
    gc.collect()
    assert standin() is None, (
        "the in-process stand-in is still referenced after re-adoption: its model RSS "
        "is never returned")


# ---- M-1 / F13: the failed private worker is closed and reaped -------------------------------


@pytest.mark.timeout(60)
@pytest.mark.parametrize("shared_models", ["0", "1"])
def test_the_failed_private_worker_is_closed_and_reaped_when_the_standin_loads(
        rig5, monkeypatch, shared_models):
    monkeypatch.setenv("RMX_SHARED_MODELS", shared_models)
    _made, pids = _unspawnable_private_with_pids(monkeypatch)
    root, logs = rig5["root"], []

    first = _one_call(root, logs)
    assert first["ok"] and first["model"] == "in-process", _brief([first])
    client = recall_mod._EMBED_CLIENT
    assert client is not None and not isinstance(client, modelsrv.SharedWorkerClient), client
    assert pids, "precondition: the private worker never spawned a child"
    assert client._proc is None, (
        f"the stand-in loaded but the failed private worker still holds its process "
        f"pid={client._proc.pid} (never closed: not reaped)")
    unreaped = []
    for pid in pids:
        try:
            got, _status = os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            continue                              # already reaped: what we want
        unreaped.append((pid, "zombie" if got == pid else "running"))
    assert not unreaped, (
        f"the failed private worker's child(ren) were not reaped when the stand-in "
        f"loaded: {unreaped}")


# ---- M-2: a malformed reprobe env falls back to the defaults ---------------------------------


@pytest.mark.timeout(60)
@pytest.mark.parametrize("var,value,shared_models", [
    ("RMX_SHARED_REPROBE_S", "300s", "1"),
    ("RMX_SHARED_REPROBE_S", "300s", "0"),
    ("RMX_SHARED_REPROBE_MAX_S", "30m", "1"),
], ids=["base-typo-shared", "base-typo-unshared", "cap-typo-shared"])
def test_a_malformed_reprobe_env_never_costs_an_in_process_load_with_a_healthy_private_worker(
        rig5, monkeypatch, caplog, var, value, shared_models):
    monkeypatch.setenv("RMX_SHARED_MODELS", shared_models)
    monkeypatch.delenv("RMX_SHARED_REPROBE_S", raising=False)
    monkeypatch.delenv("RMX_SHARED_REPROBE_MAX_S", raising=False)
    monkeypatch.setenv(var, value)
    caplog.set_level(logging.WARNING)
    root, logs = rig5["root"], []
    assert not rig5["sock"].exists()             # no hub; the private worker is healthy

    calls = [_one_call(root, logs) for _ in range(4)]
    shown = _brief(calls)
    assert all(o["ok"] for o in calls), shown
    assert len(rig5["loads"]) == 0 and all(o["model"] == "stub/private" for o in calls), (
        f"ch-bsd r5 #m-2: {var}={value!r} (an operator typo) with a HEALTHY private worker "
        f"and RMX_SHARED_MODELS={shared_models} cost {len(rig5['loads'])} in-process "
        f"load(s) across 4 calls (each ~610 MB, 6-33 s: bug-173's cost); a malformed env "
        f"must fall back to the defaults: {shown}")
    assert len(rig5["privates"]) == 1, f"one private worker per process: {shown}"

    named = [r.getMessage() for r in caplog.records
             if r.levelno >= logging.WARNING and var in r.getMessage()]
    named += [m for m in logs if var in m]
    if shared_models == "1":
        assert len(named) == 1, (
            f"a malformed {var} must be named in exactly ONE warning (not none, not one "
            f"per call): {named}")
        assert recall_mod._EMBED_REPROBE_BACKOFF.get("embed") == 300.0, (
            f"the throttle does not hold the default base 300 s after the fallback: "
            f"backoff={dict(recall_mod._EMBED_REPROBE_BACKOFF)}")
    else:
        assert len(named) <= 1, named


# ---- M-3: a cold hub worker re-arms the re-probe at base; a refused socket doubles -----------


def _stale_socket_file(path) -> None:
    """A socket file nobody listens on (a hub that crashed without unlinking): connect is
    REFUSED."""
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.bind(str(path))
    s.close()


@pytest.mark.timeout(60)
@pytest.mark.parametrize("hub_state", ["cold", "absent", "refused"])
def test_a_cold_hub_rearms_at_base_while_an_absent_or_refused_socket_doubles(
        rig5, monkeypatch, hub_state):
    monkeypatch.setenv("RMX_SHARED_MODELS", "1")
    monkeypatch.setenv("RMX_SHARED_REPROBE_S", "100")
    monkeypatch.setenv("RMX_SHARED_REPROBE_MAX_S", "1000")
    sock, logs = rig5["sock"], []
    nxt: dict = {}
    back: dict = {}
    t = 1_000_000.0
    # The state a build that went private leaves behind (`hold_reprobe`): backoff = base.
    recall_mod.hold_reprobe("embed", next_at=nxt, backoff=back, now=t)
    assert back["embed"] == 100.0, back           # precondition
    t = nxt["embed"]                              # the re-probe is due

    hub = None
    if hub_state == "cold":
        hub = _SlowHub(sock, delay=5.0)
    elif hub_state == "refused":
        _stale_socket_file(sock)
        assert sock.exists() and not modelsrv.shared_available()
    else:
        assert not sock.exists()
    try:
        client = recall_mod.reprobe_shared_client(
            "embed", next_at=nxt, backoff=back, log=logs.append, now=t, probe_timeout=0.3)
        assert client is None, client
        if hub is not None:
            assert _settle(hub) >= 1, "precondition: the probe never connected to the hub"
    finally:
        if hub is not None:
            hub.close()
        elif sock.exists():
            sock.unlink()

    waited = round(nxt["embed"] - t)
    if hub_state == "cold":
        assert waited == 100 and back["embed"] == 100.0, (
            f"ch-bsd r5 #m-3: the hub socket CONNECTED and only the info header timed out "
            f"(its worker is warming), yet the next re-probe waits {waited}s "
            f"(backoff={back}), not the base 100s: a cold worker costs a doubled window "
            f"with a duplicate private worker beside the hub's. {logs}")
    else:
        assert waited == 200 and back["embed"] == 200.0, (
            f"no hub ({hub_state}) must still double the wait (base 100 -> 200), or a "
            f"machine with no hub probes at full rate forever: waited {waited}s "
            f"backoff={back} {logs}")


@pytest.mark.timeout(60)
def test_a_request_path_probe_of_a_cold_hub_rearms_at_base(rig5, monkeypatch):
    """The audit's process-level shape (`bsd-r5-probe_coldhub.py`): a private client is
    cached, the hub comes up with a cold worker, the request-path probe (1.0 s bound)
    connects and times out on the header. The throttle must re-arm at base."""
    monkeypatch.setenv("RMX_SHARED_MODELS", "1")
    monkeypatch.setenv("RMX_SHARED_REPROBE_S", "2")
    monkeypatch.setenv("RMX_SHARED_REPROBE_MAX_S", "60")
    root, logs = rig5["root"], []

    first = _one_call(root, logs)                 # no hub: private, backoff = base
    assert first["ok"] and first["model"] == "stub/private", _brief([first])
    assert recall_mod._EMBED_REPROBE_BACKOFF.get("embed") == 2.0, (
        dict(recall_mod._EMBED_REPROBE_BACKOFF))

    hub = _SlowHub(rig5["sock"], delay=6.0)
    try:
        due = recall_mod._EMBED_REPROBE_NEXT["embed"]
        while time.time() <= due + 0.1:           # bounded: base is 2 s
            time.sleep(0.05)
        t0 = time.time()
        second = _one_call(root, logs)
        assert second["ok"] and second["model"] == "stub/private", _brief([second])
        assert _settle(hub) >= 1, f"precondition: the request path never probed: {logs}"
    finally:
        hub.close()
    nxt = recall_mod._EMBED_REPROBE_NEXT["embed"]
    back = recall_mod._EMBED_REPROBE_BACKOFF["embed"]
    assert back == 2.0 and nxt - t0 < 3.5, (
        f"ch-bsd r5 #m-3: a request-path probe of a hub whose worker is cold (connected, "
        f"header timed out) doubled the re-probe window: backoff={back}s, next in "
        f"{nxt - t0:.1f}s (base 2 s). {logs}")
