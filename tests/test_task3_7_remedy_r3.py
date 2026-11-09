"""Task 3.7 remedy round 3 — RED (spec #remedy-r3-red; ch-bsd
`workflow/bullshit/2026-11-08-2352-task-3.7-remedy-r2-3281c53.md`).

S-1  A daemonless process that fell back to a PRIVATE embed worker after a hub crash never
     goes back to the hub: `_embed_client_is_dead` judges only a `SharedWorkerClient`, so a
     private client is kept for the process's life (bug-024's shape, which
     `Daemon._maybe_adopt_shared` fixed for daemons in task 12.1). Once the hub answers
     again, the process must re-adopt the hub-shared worker within a bounded number of
     calls (the daemon's backoff knob `RMX_SHARED_REPROBE_S`, set to 0 here) and close the
     private worker it held.
S-2  Two calls against a HEALTHY hub reuse one client and rebuild nothing (pins the
     `not client.alive()` gate; mutation M3 survived r2).
M-1  On the production path (no injected `log`, no logging configured: `rmx mcp`, the CLI)
     the rebuild notice and the in-process fallback notice must reach stderr, at WARNING
     like `verbs.memory_partition`'s notice and `embedder`'s degraded-extraction line. The
     rebuild count is read from that line.
M-3  The atexit closer is registered ONCE per process across a crash + rebuild (mutation
     M6, register on every rebuild, survived r2 because R13's spy counted only `close`).
M-4  `gmd_curator._is_legacy_path_line`: one test per clause of the R2-M3 rule (mutations
     M9/M10/M11 survived r2).

Doubles: the r2 rig (`tests/test_task3_7_remedy_r2.py`, registry row "task 3.7 remedy r2",
extended in r3) — a stub model-worker script behind a REAL `ModelServer` in a REAL
subprocess, a `WorkerClient` subclass whose only change is the stub `argv`, a counting
in-process `Embedder`, and an `atexit.register` recorder for callables from
`refmatrix.recall`. The M-1 tests run the SAME doubles inside a fresh child interpreter so
that no pytest logging handler is installed: that child is what the operator's process
looks like.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import textwrap
import time

import pytest

from refmatrix import modelsrv
from refmatrix import recall as recall_mod
from refmatrix import verbs
from tests.task3_7_helpers import rm, short_root
from tests.test_task3_7_remedy_r2 import _SRC, _one_call, rig  # noqa: F401 — the fixture


def _shown(calls, mark=None):
    return [{k: (v if k != "client" else type(v).__name__ + ("(mark)" if v is mark else ""))
             for k, v in o.items()} for o in calls]


# ---- S-1: re-adopt the hub after a private fallback ----------------------------------------


def test_a_private_fallback_returns_to_the_hub_once_it_answers_again(rig, monkeypatch):
    # The daemon's re-probe backoff knob (task 12.1), at 0: probe on every call, so the
    # bound below is a count of calls, not of wall-clock seconds.
    monkeypatch.setenv("RMX_SHARED_REPROBE_S", "0")
    monkeypatch.setenv("RMX_SHARED_REPROBE_MAX_S", "0")
    root, logs = rig["root"], []
    hub = rig["start_hub"]()
    first = _one_call(root, logs)
    assert first["ok"] and first["model"] == "stub/hub", first

    rig["kill_hub"](hub)
    down = [_one_call(root, logs) for _ in range(3)]
    # Precondition (r2's contract, green at HEAD): the process fell back to ONE private
    # worker while the hub was down.
    assert down[-1]["ok"] and down[-1]["model"] == "stub/private", _shown(down)
    private = down[-1]["client"]
    assert isinstance(private, rig["privates"][0].__class__), type(private)
    proc = private._proc
    assert proc is not None and proc.poll() is None, "the private worker is not running"

    rig["start_hub"]()
    back: list = []
    for _ in range(3):                      # the bound: three calls after the hub returns
        back.append(_one_call(root, logs))
        if back[-1]["ok"] and back[-1]["model"] == "stub/hub":
            break
    back.append(_one_call(root, logs))      # and it STAYS on the hub
    shown = _shown(back, private)

    assert back[-2]["ok"] and back[-2]["model"] == "stub/hub", (
        f"the process never returned to the hub-shared worker within 3 calls of the hub "
        f"answering again (bug-024 in a daemonless process): {shown}")
    assert isinstance(back[-1]["client"], modelsrv.SharedWorkerClient), shown
    assert back[-1]["ok"] and back[-1]["model"] == "stub/hub", shown
    assert back[-1]["client"] is back[-2]["client"], (
        f"the re-adopted hub client was not reused: {shown}")
    assert proc.poll() is not None, (
        f"the private worker pid={proc.pid} is still running after the hub was "
        f"re-adopted: {shown}")
    assert private._proc is None, "the dropped private client respawned its worker"
    assert len(rig["privates"]) + len(rig["loads"]) <= 1, (
        f"{len(rig['privates'])} private worker(s) + {len(rig['loads'])} in-process "
        f"load(s) across one outage: {shown}")
    assert len(rig["registered"]) == 1, (
        f"atexit registrations from recall across hub -> private -> hub: "
        f"{rig['registered']}")


# ---- S-2: a healthy hub client is reused, not rebuilt ---------------------------------------


def test_a_healthy_hub_client_is_reused_across_calls_without_a_rebuild(rig):
    root, logs = rig["root"], []
    rig["start_hub"]()
    before = recall_mod._EMBED_CLIENT_REBUILDS
    calls = [_one_call(root, logs) for _ in range(2)]
    shown = _shown(calls)
    assert all(o["ok"] and o["model"] == "stub/hub" for o in calls), shown
    assert isinstance(calls[0]["client"], modelsrv.SharedWorkerClient), shown
    assert calls[0]["client"] is calls[1]["client"], (
        f"a healthy hub-shared client was replaced between two calls: {shown}")
    assert recall_mod._EMBED_CLIENT_REBUILDS == before, (
        f"rebuild counter moved {before} -> {recall_mod._EMBED_CLIENT_REBUILDS} with the "
        f"hub up: {shown}")
    assert not [m for m in logs if "lost its connection" in m], logs


# ---- M-3: one atexit closer across a rebuild ------------------------------------------------


def test_the_atexit_closer_is_registered_once_across_a_crash_and_rebuild(rig):
    root, logs = rig["root"], []
    hub = rig["start_hub"]()
    assert _one_call(root, logs)["ok"]
    rig["kill_hub"](hub)
    after = [_one_call(root, logs) for _ in range(3)]
    assert recall_mod._EMBED_CLIENT_REBUILDS == 1, _shown(after)   # precondition
    assert len(rig["registered"]) == 1, (
        f"recall registered {len(rig['registered'])} atexit callable(s) for one "
        f"process: {rig['registered']}")
    assert rig["registered"][0] is recall_mod._close_process_embed_client


# ---- M-1: the production path tells the operator ---------------------------------------------

_CHILD = textwrap.dedent("""
    import json, os, signal, sys, time
    import numpy as np
    from refmatrix import embedder as embedder_mod, modelsrv, recall, subproc
    mode, stub, hub_pid, root = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
    real = subproc.WorkerClient
    argv = ([sys.executable, stub, "private"] if mode == "rebuild"
            else [sys.executable, "-c", "raise SystemExit(3)"])

    class Priv(real):
        def __init__(self, role, **kw):
            kw.setdefault("argv", argv)
            kw.setdefault("timeout", 15.0)
            super().__init__(role, **kw)
    subproc.WorkerClient = Priv
    loads = []

    class InProc:
        def __init__(self):
            loads.append(1)
            self.dim = 4
            self.model_name = "in-process"

        def embed_texts(self, texts):
            return np.ones((len(texts), 4), dtype="float32")
    embedder_mod.Embedder = InProc

    def one():
        # The verb's call shape (`verbs._graph_dense`): NO log argument.
        try:
            e = recall.shared_embedder(root)
            e.embed_texts(["document number 3"])
            return {"ok": True, "model": e.model_name}
        except Exception as exc:
            return {"ok": False, "error": repr(exc)[:120]}

    out = [one()]
    if mode == "rebuild":
        os.kill(hub_pid, signal.SIGKILL)
        deadline = time.monotonic() + 10
        while modelsrv.shared_available() and time.monotonic() < deadline:
            time.sleep(0.05)
        out += [one() for _ in range(3)]
    print(json.dumps({"calls": out, "rebuilds": recall._EMBED_CLIENT_REBUILDS,
                      "loads": len(loads)}))
""")


def _run_child(rig, mode, hub_pid, env_extra):
    child = rig["root"] / "child.py"
    child.write_text(_CHILD)
    env = dict(os.environ)
    env.update(env_extra)
    env["PYTHONPATH"] = os.pathsep.join([str(_SRC), env.get("PYTHONPATH", "")])
    for k in ("RMX_SHARED_REPROBE_S", "RMX_SHARED_REPROBE_MAX_S"):
        env.pop(k, None)
    p = subprocess.run([sys.executable, str(child), mode, str(rig["stub"]), str(hub_pid),
                        str(rig["root"])], env=env, capture_output=True, text=True,
                       timeout=120)
    assert p.returncode == 0, f"child rc={p.returncode}\nstderr:\n{p.stderr}"
    return json.loads(p.stdout.strip().splitlines()[-1]), p.stderr


def test_a_rebuild_on_the_production_path_reaches_stderr_with_its_count(rig):
    hub = rig["start_hub"]()
    out, err = _run_child(rig, "rebuild", hub.pid, {})
    hub.wait(timeout=10)
    calls = out["calls"]
    # Preconditions (green at HEAD): the hub served, the crash rebuilt once, a private
    # worker served after it.
    assert calls[0]["ok"] and calls[0]["model"] == "stub/hub", out
    assert out["rebuilds"] == 1 and calls[-1]["model"] == "stub/private", out
    line = re.search(r"(?im)^.*rebuil.*$", err)
    assert line, (
        f"a hub-shared client was rebuilt in a process with no log configured and the "
        f"operator saw nothing on stderr (ch-bsd r2 #m-1): stderr={err!r}")
    assert re.search(r"\b1\b", line.group(0)), (
        f"the rebuild notice does not carry the rebuild count: {line.group(0)!r}")


def test_an_in_process_fallback_on_the_production_path_reaches_stderr(rig, monkeypatch):
    # No hub at all, and a private worker that cannot start: the "loudly" in-process
    # fallback line of `shared_embedder`.
    monkeypatch.setenv("RMX_SHARED_MODELS", "0")
    out, err = _run_child(rig, "fallback", 0, {"RMX_SHARED_MODELS": "0"})
    assert out["calls"][0] == {"ok": True, "model": "in-process"}, out   # precondition
    assert out["loads"] == 1, out
    assert re.search(r"(?i)in-process", err), (
        f"the process fell back to the in-process model (the model's RSS) with no log "
        f"configured and stderr said nothing (ch-bsd r2 #m-1): stderr={err!r}")


# ---- M-4: each clause of the legacy path-shape rule ------------------------------------------


@pytest.fixture
def root(monkeypatch):
    monkeypatch.delenv("RMX_PARTITION", raising=False)
    base, r = short_root("r37r3-")
    yield r
    rm(base)


def _legacy(root, text):
    (root / "curator.queue").write_text(text)
    out = verbs.curator(root, action="status")
    return [(e["path"], e["reason"]) for e in out["entries"]], out["warnings"]


def test_a_line_with_internal_whitespace_is_bad_even_with_a_slash_and_a_suffix(root):
    got, warnings = _legacy(root, "docs/plan/a.md\nsee src/a.py for details\n")
    assert got == [("docs/plan/a.md", "legacy")], got
    assert any(w.startswith("1 unparseable line(s)") for w in warnings), warnings


def test_a_suffix_only_name_is_a_legacy_path(root):
    got, warnings = _legacy(root, "README.md\n")
    assert got == [("README.md", "legacy")], got
    assert not warnings, warnings


def test_a_slash_only_name_is_a_legacy_path(root):
    got, warnings = _legacy(root, "docs/Makefile\n")
    assert got == [("docs/Makefile", "legacy")], got
    assert not warnings, warnings


def test_a_name_with_neither_slash_nor_suffix_is_bad(root):
    got, warnings = _legacy(root, "README\n")
    assert got == [], got
    assert any(w.startswith("1 unparseable line(s)") for w in warnings), warnings
