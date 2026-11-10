"""Task 3.7 remedy round 6 -- RED (ch-bsd r6
`workflow/bullshit/2026-11-09-1058-task-3.7-remedy-r5-e285c1c.md`, id
`bsd-task3.7-remedy-r5-e285c1c`; probe logs `workflow/review-output/task-3.7/bsd-r6-*.log`).

S-1  A MUTE hub: `models.sock` accepts (a wedged or SIGSTOPped hub, a ModelServer whose worker
     hangs) and never answers, so every probe connects and times out at the header stage.
     r5 classified every such miss as `cold` and re-armed at BASE every time, so the backoff
     never grows: measured at e285c1c, the request path made 22 probes / 22.0 s of stall in
     25 s (base 1, cap 8), and the daemon tick's re-arm waits were [100]*6 (base 100, cap 400)
     where e4faf32 gave [100, 200, 400, 400, 400, 400]. Intended: the FIRST cold miss of a run
     of misses may re-arm at base (r5 #m-3: a hub that came up cold is adopted one base window
     later; `test_a_cold_hub_rearms_at_base_while_an_absent_or_refused_socket_doubles[cold]`
     and `test_a_request_path_probe_of_a_cold_hub_rearms_at_base` keep that), and every
     CONSECUTIVE header-timeout miss doubles up to the cap, because a worker still cold after
     a full base window is not loading. Pinned on BOTH paths the audit measured: the daemon's
     background tick (`Daemon._maybe_adopt_shared`, bound `modelsrv.PROBE_TIMEOUT_S`) and the
     daemonless request path (`recall._process_embed_client` via `shared_embedder`, bound
     `modelsrv.REQUEST_PROBE_TIMEOUT_S`).
M-1  Killers for four `env_float` survivors (`bsd-r6-mutations.log`): G1 non-finite accepted,
     G2 negative accepted, G8 `RMX_SHARED_OP_TIMEOUT_S` hand-rolled again, G9
     `RMX_SHARED_PROBE_TIMEOUT_S` hand-rolled again. Plus RED tests for the sibling knobs on
     the same import paths that still hand-roll the parse: a typo makes the import RAISE
     (`RMX_WORKER_TIMEOUT_S`, `RMX_ADOPT_GRACE_S`, `RMX_HEARTBEAT_S`,
     `RMX_LEARN_DRAIN_BUDGET_S`, `RMX_HUB_HEARTBEAT_STALE_S`) or is swallowed with NO warning
     (`RMX_WORKER_IDLE_S`, `ModelServer.idle_seconds`). Intended (r5's own `env_float`
     contract): the default plus ONE warning naming the variable.

Doubles (registry row "task 3.7 remedy r6"): `_StubHub(answer=False)` from
`tests/test_shared_worker_readoption.py` -- a REAL unix socket in a short `/tmp` mkdtemp root
that accepts, reads the frame and never answers (the mute hub; classified there as a
fake-impl of the hub's ModelServer socket); its `_FakePrivate` as the daemon's private worker
(adoption only needs "not shared"); the r5 rig (`rig5`) and its stub private worker for the
request path; `modelsrv.PROBE_TIMEOUT_S` / `REQUEST_PROBE_TIMEOUT_S` set short (config
constants, not the function under test). `reprobe_shared_client`, `_maybe_adopt_shared`,
`_process_embed_client`, `SharedWorkerClient` and `env_float` run unpatched. The import tests
run a fresh interpreter (`python -c "import refmatrix.<mod>"`) with the clone's `src` first on
`PYTHONPATH` and a throwaway `HOME`; nothing touches a live store.
"""
from __future__ import annotations

import json
import logging
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from refmatrix import daemon as dm
from refmatrix import modelsrv
from refmatrix import recall as recall_mod
from tests.test_shared_worker_readoption import _FakePrivate, _StubHub
from tests.test_task3_7_remedy_r2 import _one_call, rig  # noqa: F401 -- the fixture
from tests.test_task3_7_remedy_r4 import _brief, rig4  # noqa: F401 -- the fixture
from tests.test_task3_7_remedy_r5 import _env_warnings, _settle, env_warned, rig5  # noqa: F401

SRC = Path(__file__).resolve().parents[1] / "src"


# ---- S-1: a mute hub's consecutive header-timeout misses double to the cap ------------------


@pytest.fixture
def mute_daemon(monkeypatch):
    """A real `Daemon` (never served) with a PRIVATE embed worker, its log captured, and a
    models.sock path in a SHORT root (macOS `sun_path` is ~104 bytes)."""
    base = Path(tempfile.mkdtemp(prefix="r37r6-", dir="/tmp"))
    root = base / "p" / ".refmatrix"
    root.parent.mkdir(parents=True)
    sock = base / "models.sock"
    monkeypatch.setenv("RMX_MODEL_SOCK", str(sock))
    monkeypatch.setenv("RMX_SHARED_MODELS", "1")
    d = dm.Daemon(root)
    logs: list = []
    d._log = logs.append
    d._embed_worker = _FakePrivate()
    yield d, sock, logs
    shutil.rmtree(base, ignore_errors=True)


@pytest.mark.timeout(90)
def test_a_mute_hub_daemon_tick_backoff_doubles_to_the_cap(mute_daemon, monkeypatch):
    """`bsd-r6-probe-daemon-mutehub.log`'s shape: the real `_maybe_adopt_shared`, a hub that
    accepts and never answers, base 100, cap 400. Six due ticks; each probe times out on the
    header (bound 0.5 s here, 45 s live). Waits must be [100, 200, 400, 400, 400, 400]."""
    d, sock, logs = mute_daemon
    monkeypatch.setenv("RMX_SHARED_REPROBE_S", "100")
    monkeypatch.setenv("RMX_SHARED_REPROBE_MAX_S", "400")
    monkeypatch.setattr(modelsrv, "PROBE_TIMEOUT_S", 0.5)
    hub = _StubHub(sock, answer=False)
    t = 1_000_000.0
    waits: list = []
    try:
        for _ in range(6):
            assert d._maybe_adopt_shared(now=t) == [], logs
            nxt = d._reprobe_next["embed"]
            waits.append(round(nxt - t))
            t = nxt
        probes = _settle(hub)
    finally:
        hub.close()
    assert probes >= 6, (
        f"precondition: the mute hub saw {probes} connects for 6 due ticks (each probe must "
        f"connect and time out on the header): {logs}")
    unusable = [m for m in logs if "shared worker still unusable" in m]
    assert len(unusable) == 6 and all("TimeoutError" in m for m in unusable), (
        f"precondition: every miss must be a header TIMEOUT (the mute hub): {unusable}")
    assert waits == [100, 200, 400, 400, 400, 400], (
        f"ch-bsd r6 #s-1: a hub that ACCEPTS and never answers re-armed the daemon tick's "
        f"re-probe at {waits} (base 100, cap 400). Only the FIRST cold miss of a run may "
        f"re-arm at base; a worker still silent after a full base window is not loading, so "
        f"each consecutive header-timeout miss must double to the cap. Live, the tick paid "
        f"the full 45 s PROBE_TIMEOUT_S per role every 300 s for as long as the hub stayed "
        f"wedged. {logs}")
    assert not any("re-probing at the base window" in m for m in unusable[1:]), (
        f"the log must not claim a base-window re-probe for a miss that doubled: "
        f"{unusable[1:]}")


@pytest.mark.timeout(90)
def test_a_mute_hub_request_path_backoff_doubles_to_the_cap(rig5, monkeypatch):
    """`bsd-r6-probe-mutehub-backoff.log`'s shape, scaled down: a daemonless process with a
    cached private client (no hub -> `hold_reprobe`, backoff = base), then a MUTE hub. Each
    eligible embed call probes on the request path (bound `REQUEST_PROBE_TIMEOUT_S`, 0.3 s
    here, 1.0 s live), misses on the header, and keeps serving from the private worker. The
    backoff recorded after each probe must be [base, 2*base, 4*base, cap, cap]."""
    monkeypatch.setenv("RMX_SHARED_MODELS", "1")
    monkeypatch.setenv("RMX_SHARED_REPROBE_S", "0.5")
    monkeypatch.setenv("RMX_SHARED_REPROBE_MAX_S", "2")
    monkeypatch.setattr(modelsrv, "REQUEST_PROBE_TIMEOUT_S", 0.3)
    root, logs = rig5["root"], []

    first = _one_call(root, logs)                 # no hub: private, backoff = base
    assert first["ok"] and first["model"] == "stub/private", _brief([first])
    assert recall_mod._EMBED_REPROBE_BACKOFF.get("embed") == 0.5, (
        dict(recall_mod._EMBED_REPROBE_BACKOFF))

    hub = _StubHub(rig5["sock"], answer=False)
    backoffs: list = []
    served: list = []
    try:
        hard_stop = time.monotonic() + 45.0
        while len(backoffs) < 5 and time.monotonic() < hard_stop:
            due = recall_mod._EMBED_REPROBE_NEXT["embed"]
            while time.time() <= due + 0.05:
                time.sleep(0.02)
            out = _one_call(root, logs)
            served.append(out["ok"] and out["model"] == "stub/private")
            if recall_mod._EMBED_REPROBE_NEXT.get("embed") != due:
                backoffs.append(recall_mod._EMBED_REPROBE_BACKOFF.get("embed"))
        probes = _settle(hub)
    finally:
        hub.close()
    assert all(served), f"the private worker must serve every call: {served} {logs}"
    assert probes >= 5, f"precondition: the request path never reached the mute hub: {logs}"
    assert backoffs == [0.5, 1.0, 2.0, 2.0, 2.0], (
        f"ch-bsd r6 #s-1: behind a hub that accepts and never answers, the request path's "
        f"backoff after each probe was {backoffs} (base 0.5, cap 2). r5 re-arms at base on "
        f"every header-timeout miss, so it probes (and stalls the caller for the probe "
        f"bound) once per base window forever: 22 probes / 22.0 s of stall in 25 s at base "
        f"1. Consecutive misses must double to the cap. {logs[-6:]}")


# ---- M-1: env_float's own edges (G1, G2) ----------------------------------------------------


@pytest.mark.timeout(30)
@pytest.mark.parametrize("raw", ["nan", "inf", "-inf", "-5", "-0.5"])
def test_env_float_rejects_non_finite_and_negative_with_one_warning(
        env_warned, monkeypatch, caplog, raw):
    """G1 (`nan`/`inf` accepted) and G2 (negative accepted). `-5` as RMX_SHARED_REPROBE_S
    makes the re-probe wait negative, so it would probe on EVERY call."""
    caplog.set_level(logging.WARNING, logger="refmatrix.modelsrv")
    monkeypatch.setenv("RMX_SHARED_REPROBE_S", raw)
    got = [modelsrv.env_float("RMX_SHARED_REPROBE_S", 300.0) for _ in range(3)]
    assert got == [300.0] * 3 and all(math.isfinite(g) for g in got), (
        f"ch-bsd r6 #m-1 (G1/G2): RMX_SHARED_REPROBE_S={raw!r} must read as the default 300.0 "
        f"(not a finite non-negative number of seconds), got {got}")
    assert recall_mod._reprobe_window()[0] == 300.0
    assert _env_warnings(caplog, "RMX_SHARED_REPROBE_S") == [raw], (
        f"one warning naming {raw!r}: {_env_warnings(caplog, 'RMX_SHARED_REPROBE_S')}")


@pytest.mark.timeout(30)
@pytest.mark.parametrize("raw,want", [("0", 0.0), ("2.5", 2.5), ("1e2", 100.0)])
def test_env_float_accepts_zero_and_positive_silently(env_warned, monkeypatch, caplog,
                                                      raw, want):
    """The other side of G1/G2: a bound too tight (rejecting 0, which the r5 tests use to
    re-probe on every call) must fail too."""
    caplog.set_level(logging.WARNING, logger="refmatrix.modelsrv")
    monkeypatch.setenv("RMX_SHARED_REPROBE_S", raw)
    assert modelsrv.env_float("RMX_SHARED_REPROBE_S", 300.0) == want
    assert _env_warnings(caplog, "RMX_SHARED_REPROBE_S") == []


# ---- M-1: import-time knobs (G8, G9) and the hand-rolled siblings ---------------------------


def _import_with_env(module: str, expr: str, **env) -> "tuple[int, object, str]":
    """`import refmatrix.<module>` in a FRESH interpreter with `env` set; print `expr` (a
    Python expression over the imported module `m`) as JSON. Returns (rc, value, stderr).
    The interpreter's logging is unconfigured, so a `logging.warning` reaches stderr through
    the last-resort handler -- the operator's view of an import-time knob."""
    home = tempfile.mkdtemp(prefix="r37r6h-", dir="/tmp")
    try:
        e = {k: v for k, v in os.environ.items()
             if not k.startswith(("RMX_", "CLAUDE", "REFMATRIX_"))}
        pp = [p for p in e.get("PYTHONPATH", "").split(os.pathsep) if p and p != str(SRC)]
        e.update(PYTHONPATH=os.pathsep.join([str(SRC)] + pp), HOME=home, HF_HUB_OFFLINE="1",
                 REFMATRIX_ROOT=str(Path(home) / "p" / ".refmatrix"))
        e.update({k: str(v) for k, v in env.items()})
        code = (f"import json, importlib; m = importlib.import_module('refmatrix.{module}'); "
                f"print(json.dumps({expr}))")
        r = subprocess.run([sys.executable, "-c", code], env=e, cwd=home,
                           capture_output=True, text=True, timeout=120)
    finally:
        shutil.rmtree(home, ignore_errors=True)
    value = None
    if r.returncode == 0 and r.stdout.strip():
        value = json.loads(r.stdout.strip().splitlines()[-1])
    return r.returncode, value, r.stderr


# (env name, typo, module, expression over `m`, the default it must fall back to)
_IMPORT_KNOBS = [
    # G9: `modelsrv.PROBE_TIMEOUT_S = env_float(...)` hand-rolled again -> import raises.
    ("RMX_SHARED_PROBE_TIMEOUT_S", "45s", "modelsrv", "m.PROBE_TIMEOUT_S", 45.0),
    # G8: `daemon._shared_op_timeout_default` hand-rolled again -> import raises.
    ("RMX_SHARED_OP_TIMEOUT_S", "45s", "daemon", "m.SHARED_OP_TIMEOUT_S", 45.0),
    # Siblings, RED at HEAD: each is a bare `float(os.environ.get(...))` at import.
    ("RMX_WORKER_TIMEOUT_S", "300s", "subproc", "m.DEFAULT_TIMEOUT_S", 300.0),   # subproc:52
    ("RMX_WORKER_TIMEOUT_S", "300s", "modelsrv",                                # via subproc
     "__import__('refmatrix.subproc').subproc.DEFAULT_TIMEOUT_S", 300.0),
    ("RMX_ADOPT_GRACE_S", "20s", "daemon", "m.ADOPT_GRACE_S", 20.0),             # daemon:61
    ("RMX_HEARTBEAT_S", "5s", "daemon", "m.HEARTBEAT_INTERVAL_S", 5.0),          # daemon:63
    ("RMX_HUB_HEARTBEAT_STALE_S", "60s", "daemon", "m.HEARTBEAT_STALE_S", 60.0),  # daemon:66
    ("RMX_LEARN_DRAIN_BUDGET_S", "5s", "daemon", "m.LEARN_DRAIN_BUDGET_S", 5.0),  # daemon:708
    # Swallowed, not raised: `ModelServer.idle_seconds` (modelsrv:447) catches ValueError
    # and returns 0.0 with NO warning -- an operator's typo silently disables idle reaping.
    ("RMX_WORKER_IDLE_S", "300s", "modelsrv", "m.ModelServer().idle_seconds()", 0.0),
]


@pytest.mark.timeout(150)
@pytest.mark.parametrize("name,raw,module,expr,default", _IMPORT_KNOBS,
                         ids=[f"{k[0]}-{k[2]}" for k in _IMPORT_KNOBS])
def test_a_typod_knob_on_an_import_path_is_its_default_plus_one_warning(
        name, raw, module, expr, default):
    rc, value, err = _import_with_env(module, expr, **{name: raw})
    assert rc == 0, (
        f"ch-bsd r6 #m-1: {name}={raw!r} (an operator typo) made `import refmatrix.{module}` "
        f"(or reading {expr}) RAISE, so every caller of that module fails before it starts. "
        f"It must read as the default {default} with one warning. stderr: {err[-600:]}")
    assert value == default, f"{name}={raw!r}: {expr} = {value!r}, want the default {default}"
    named = [ln for ln in err.splitlines() if name in ln and raw in ln]
    assert len(named) == 1, (
        f"{name}={raw!r} must produce exactly ONE warning naming the variable and the value "
        f"(the `env_float` contract); got {len(named)}: {named} stderr: {err[-600:]}")


@pytest.mark.timeout(150)
@pytest.mark.parametrize("name,module,expr,want", [
    ("RMX_SHARED_PROBE_TIMEOUT_S", "modelsrv", "m.PROBE_TIMEOUT_S", 7.5),
    ("RMX_SHARED_OP_TIMEOUT_S", "daemon", "m.SHARED_OP_TIMEOUT_S", 90.0),
    ("RMX_WORKER_TIMEOUT_S", "subproc", "m.DEFAULT_TIMEOUT_S", 120.0),
    ("RMX_ADOPT_GRACE_S", "daemon", "m.ADOPT_GRACE_S", 3.0),
    ("RMX_LEARN_DRAIN_BUDGET_S", "daemon", "m.LEARN_DRAIN_BUDGET_S", 2.0),
    ("RMX_WORKER_IDLE_S", "modelsrv", "m.ModelServer().idle_seconds()", 600.0),
])
def test_a_wellformed_knob_on_an_import_path_is_honoured_silently(name, module, expr, want):
    """The other side: moving a knob onto the shared parser must not drop the operator's
    valid value (a parser that always returned the default would pass the typo test)."""
    rc, value, err = _import_with_env(module, expr, **{name: repr(want)})
    assert rc == 0, err[-600:]
    assert value == want, f"{name}={want!r}: {expr} = {value!r}"
    assert not [ln for ln in err.splitlines() if name in ln], err[-600:]
