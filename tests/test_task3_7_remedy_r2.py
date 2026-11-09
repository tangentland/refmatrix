"""Task 3.7 remedy round 2 — RED (spec #remedy-r2; ch-bsd
`workflow/bullshit/2026-11-08-2256-task-3.7-remedy-r1-2a4096c.md` #s-1).

R2-S1  R-H1's process-wide embed client (`recall._EMBED_CLIENT`) is never dropped. A
       daemonless `rmx mcp` that cached the HUB-shared client keeps it after the hub dies:
       every later call retries the dead socket. Before R-H1 each call ran
       `new_model_client`, which saw `shared_available()` false and spawned a private
       worker. After a failure the process must build a FRESH client (a private worker
       when the hub stays down), the in-process model must not load on every call, and
       calls that succeed must still share ONE client (R13,
       `test_no_daemon_graph_calls_share_one_embed_client`).

What is real: the hub is a real `ModelServer` in a real subprocess, killed with SIGKILL
(a hub crash: connections drop, the socket file stays). `SharedWorkerClient`,
`new_model_client`, `_process_embed_client`, `shared_embedder` and `RemoteEmbedder` run
unpatched. Doubles (registered in workflow/test_mock_registry.md, row "task 3.7 remedy
r2"): the model process behind each worker is a stub script on the real frame protocol
(a real model is a 6-33 s torch load); `subproc.WorkerClient` is a subclass whose ONLY
change is that stub `argv`; `embedder.Embedder` (the in-process model) is a counter,
because the in-process load IS what is counted.

Note for the GREEN step: `SharedWorkerClient.info()` returns its cached header without
touching the socket, so on the real path the dead client is NOT detected inside
`shared_embedder` (`RemoteEmbedder.dim` succeeds); the failure surfaces in
`embed_texts`. The first test pins that real path; the second pins the `except` branch
the audit's probe exercised (a cached client with no header).
"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path

import numpy as np
import pytest

from refmatrix import embedder as embedder_mod
from refmatrix import modelsrv
from refmatrix import recall as recall_mod
from refmatrix import subproc

_SRC = Path(recall_mod.__file__).resolve().parent.parent

_STUB_WORKER = textwrap.dedent("""
    import os, sys
    _OUT = os.fdopen(os.dup(1), "wb"); os.dup2(2, 1); sys.stdout = sys.stderr
    _IN = os.fdopen(os.dup(0), "rb")
    from refmatrix.subproc import recv_frame, send_frame
    tag = sys.argv[1]
    while True:
        try:
            req, blob = recv_frame(_IN)
        except EOFError:
            sys.exit(0)
        op = req.get("op")
        if op == "info":
            send_frame(_OUT, {"ok": True, "model": "stub/" + tag, "dim": 4,
                              "pid": os.getpid()})
        elif op == "embed":
            n = len(req.get("texts") or [])
            send_frame(_OUT, {"ok": True, "n": n, "dim": 4,
                              "model": "stub/" + tag}, b"\\x00\\x00\\x80\\x3f" * 4 * n)
        else:
            send_frame(_OUT, {"ok": False, "error": "stub: unknown op " + str(op)})
""")

_HUB = textwrap.dedent("""
    import signal, sys
    from refmatrix.modelsrv import ModelServer
    from refmatrix.subproc import WorkerClient
    stub = sys.argv[1]
    srv = ModelServer()
    def worker(role):
        with srv._lock:
            w = srv._clients.get(role)
            if w is None:
                w = WorkerClient(role, argv=[sys.executable, stub, "hub"], timeout=15.0)
                srv._clients[role] = w
            return w
    srv._worker = worker
    assert srv.start()
    print("ready", flush=True)
    signal.pause()
""")


@pytest.fixture
def rig(monkeypatch):
    """A short socket dir, the stub scripts, the counting in-process model, the stub
    private worker, and a clean process-wide embed client (restored afterwards)."""
    base = Path(tempfile.mkdtemp(prefix="r37r2-", dir="/tmp"))
    sock = base / "models.sock"
    stub = base / "stub_worker.py"
    stub.write_text(_STUB_WORKER)
    hub_py = base / "hub.py"
    hub_py.write_text(_HUB)
    monkeypatch.setenv("RMX_MODEL_SOCK", str(sock))
    monkeypatch.setenv("RMX_SHARED_MODELS", "1")
    monkeypatch.setenv("RMX_EMBED_SUBPROC", "1")
    monkeypatch.setattr(recall_mod, "_EMBED_CLIENT", None)

    loads: list = []

    class _CountingInProcessModel:
        """Stands in for the in-process model load (the ~610 MB RSS the audit counts)."""

        def __init__(self):
            loads.append(1)
            self.dim = 4
            self.model_name = "in-process"

        def embed_texts(self, texts):
            return np.ones((len(texts), 4), dtype="float32")

    monkeypatch.setattr(embedder_mod, "Embedder", _CountingInProcessModel)

    privates: list = []
    real_worker = subproc.WorkerClient

    class _StubPrivateWorker(real_worker):
        """A real `WorkerClient`; only the spawned model process is the stub."""

        def __init__(self, role, **kw):
            kw.setdefault("argv", [sys.executable, str(stub), "private"])
            kw.setdefault("timeout", 15.0)
            super().__init__(role, **kw)
            privates.append(self)

    monkeypatch.setattr(subproc, "WorkerClient", _StubPrivateWorker)

    hubs: list = []

    def start_hub():
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join([str(_SRC), env.get("PYTHONPATH", "")])
        p = subprocess.Popen([sys.executable, str(hub_py), str(stub)], env=env,
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        hubs.append(p)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if modelsrv.shared_available():
                return p
            if p.poll() is not None:
                raise AssertionError(f"stub hub exited rc={p.returncode} before listening")
            time.sleep(0.05)
        raise AssertionError("stub hub never listened")

    def kill_hub(p):
        p.send_signal(signal.SIGKILL)
        p.wait(timeout=10)
        assert not modelsrv.shared_available(), "hub still answers after SIGKILL"

    yield {"loads": loads, "privates": privates, "start_hub": start_hub,
           "kill_hub": kill_hub, "root": base}

    cached = recall_mod._EMBED_CLIENT
    for c in [cached, *privates]:
        try:
            if c is not None:
                c.close()
        except Exception as exc:  # noqa: BLE001 — teardown; named, never masks the test
            print(f"teardown close failed: {exc!r}")
    for p in hubs:
        if p.poll() is None:
            p.kill()
            p.wait(timeout=10)
    shutil.rmtree(base, ignore_errors=True)


def _one_call(root, logs):
    """One daemonless dense/recall call as the verb makes it: get the embedder, embed the
    query (`verbs._graph_dense` / `prepare_graph_recall_embedder`)."""
    try:
        e = recall_mod.shared_embedder(root, log=logs.append)
        e.embed_texts(["document number 3"])
        return {"ok": True, "model": e.model_name, "client": recall_mod._EMBED_CLIENT}
    except Exception as exc:  # noqa: BLE001 — the outcome IS the observation
        return {"ok": False, "error": repr(exc)[:120], "client": recall_mod._EMBED_CLIENT}


def test_a_hub_crash_does_not_pin_the_process_to_its_dead_shared_client(rig):
    root, logs = rig["root"], []
    hub = rig["start_hub"]()
    first = _one_call(root, logs)
    assert first["ok"] and first["model"] == "stub/hub", first
    dead = recall_mod._EMBED_CLIENT
    assert isinstance(dead, modelsrv.SharedWorkerClient), type(dead)

    rig["kill_hub"](hub)
    after = [_one_call(root, logs) for _ in range(3)]
    shown = [{k: (v if k != "client" else type(v).__name__ + ("(dead)" if v is dead else ""))
              for k, v in o.items()} for o in after]

    # The call that meets the dead socket may fail or degrade; the ones after it must not
    # go back to that client object.
    assert all(o["client"] is not dead for o in after[1:]), (
        f"the process kept the dead hub-shared client after it failed: {shown}")
    assert all(o["ok"] and o["model"] == "stub/private" for o in after[1:]), (
        f"no fresh worker was adopted after the hub died: {shown}")
    assert after[1]["client"] is after[2]["client"], (
        f"recovered calls built more than one client (R13): {shown}")
    assert len(rig["loads"]) <= 1, (
        f"in-process model loaded {len(rig['loads'])}x across 3 calls: {shown}")


def test_a_cached_client_that_fails_in_shared_embedder_is_dropped_not_retried(rig):
    """The audit's probe shape: the cached hub client has no header and the hub is gone,
    so `remote_embedder` raises INSIDE `shared_embedder` and the in-process model serves.
    The next call must build a fresh client (a private worker), not retry the dead one
    and load the in-process model again."""
    root, logs = rig["root"], []
    seeded = modelsrv.SharedWorkerClient("embed", timeout=2)
    recall_mod._EMBED_CLIENT = seeded   # monkeypatch restores the module global

    calls = [_one_call(root, logs) for _ in range(3)]
    shown = [{k: (v if k != "client" else type(v).__name__ + ("(dead)" if v is seeded
                                                             else ""))
              for k, v in o.items()} for o in calls]

    assert calls[0]["ok"] and calls[0]["model"] == "in-process", shown
    assert all(o["client"] is not seeded for o in calls[1:]), (
        f"the dead cached client was kept after the fallback: {shown}")
    assert len(rig["loads"]) == 1, (
        f"in-process model loaded {len(rig['loads'])}x across 3 calls: {shown}")
    assert all(o["ok"] and o["model"] == "stub/private" for o in calls[1:]), shown
    assert calls[1]["client"] is calls[2]["client"], shown
