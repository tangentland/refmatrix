"""ch-bsd r10 #b-1 / #s-2: a budgeted rerank is a bound on the CALLER, proven on
the REAL client classes.

r9's remedy bounded the socket read and nothing else. r10 measured, on a real
`ModelServer` + `SharedWorkerClient` + `WorkerClient` over a stub model process:

- S2: the daemon's own unbudgeted rerank (memory_recall shape) holds the ONE
  shared client's lock; a context op with a 1.0 s budget waited 3.80 s.
- Q2/Q3: on a private worker the socket timeout `close()`d the model process,
  the respawn clause retried with an expired deadline (WorkerError, spawns
  1 -> 2), and the next op paid the cold load through an unbounded `info()`:
  6.01 s on a 3.0 s budget.
- S3b (#s-2): the "fresh" queue depth was read THROUGH the worker's lock, so
  it waited behind the very rerank it was predicting.

Every earlier budget test drove a fake `_Client` that implemented the timeout
itself and held no lock — which is why B3/B5/B7 survived. Only the model
process is a stub here (no model loads); its frame protocol, dequeue-deadline
drop, cold load and per-request scoring time are the real worker's shape.
"""
from __future__ import annotations

import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

_STUB = r'''
import os, sys, time
sys.path.insert(0, sys.argv[1])
_OUT = os.fdopen(os.dup(1), "wb"); os.dup2(2, 1)
_IN = os.fdopen(os.dup(0), "rb")
from refmatrix.subproc import recv_frame, send_frame
D = sys.argv[2]; LOAD_S = float(sys.argv[3])
with open(os.path.join(D, "spawns"), "a") as fh:
    fh.write(f"{os.getpid()}\n")
loaded = False; ema = None; scored = 0
while True:
    try:
        req, blob = recv_frame(_IN)
    except EOFError:
        sys.exit(0)
    op = req.pop("op", ""); req.pop("role", None)
    dl = req.pop("deadline", None)
    if dl is not None and time.time() > float(dl):
        send_frame(_OUT, {"ok": False,
                          "error": f"deadline expired {time.time()-float(dl):.2f}s ago; not scored"})
        continue
    if op == "ping":
        send_frame(_OUT, {"ok": True}); continue
    if os.path.exists(os.path.join(D, "fail")):
        send_frame(_OUT, {"ok": False,
                          "error": "ModelNotCached: model 'stub/ce' is not in the local cache"})
        continue
    if not loaded:
        with open(os.path.join(D, "loads"), "a") as fh:
            fh.write("1\n")
        time.sleep(LOAD_S); loaded = True
    if op == "info":
        send_frame(_OUT, {"ok": True, "model": "stub/ce", "cost_s_per_doc": ema,
                          "scored_docs": scored}); continue
    rr = float(open(os.path.join(D, "rr_s")).read().strip() or "0")
    docs = req.get("docs") or []
    t0 = time.time(); time.sleep(rr)
    if docs:
        pd = (time.time() - t0) / len(docs)
        ema = pd if ema is None else 0.3 * pd + 0.7 * ema
        scored += len(docs)
    send_frame(_OUT, {"ok": True, "scores": [0.0] * len(docs),
                      "cost_s_per_doc": ema, "scored_docs": scored})
'''

_SRC = str(Path(__file__).resolve().parents[1] / "src")


@pytest.fixture
def stub(monkeypatch):
    """Short root (macOS sun_path), a stub worker script, and a hub socket
    path INSIDE it — nothing here can reach the live ~/.refmatrix/models.sock."""
    root = Path(tempfile.mkdtemp(prefix="rmxb", dir="/tmp"))
    (root / "w.py").write_text(_STUB)
    (root / "rr_s").write_text("0.05")
    (root / "spawns").write_text("")
    (root / "loads").write_text("")
    monkeypatch.setenv("RMX_MODEL_SOCK", str(root / "m.sock"))

    class S:
        dir = root

        @staticmethod
        def rr(seconds: float) -> None:
            (root / "rr_s").write_text(str(seconds))

        @staticmethod
        def spawns() -> int:
            return len((root / "spawns").read_text().split())

        @staticmethod
        def loads() -> int:
            return len((root / "loads").read_text().split())

        @staticmethod
        def argv(load_s: float = 0.2) -> list[str]:
            return [sys.executable, str(root / "w.py"), _SRC, str(root), str(load_s)]

    yield S
    import shutil
    shutil.rmtree(root, ignore_errors=True)


def _attempt(view, docs=("a", "b", "c")):
    from refmatrix.reranker import RerankSkipped
    t0 = time.time()
    try:
        view.score("why does the daemon die", list(docs))
        out = "scored"
    except RerankSkipped as exc:
        out = f"skipped: {exc}"
    except Exception as exc:  # noqa: BLE001 — the outcome IS the assertion
        out = f"{type(exc).__name__}: {exc}"
    return time.time() - t0, out


@pytest.fixture
def hub(stub, monkeypatch):
    """A REAL ModelServer whose role workers are REAL WorkerClients over the
    stub argv, and the daemon's REAL long-lived SharedWorkerClient."""
    from refmatrix import modelsrv, subproc

    argv = stub.argv()

    class _StubWC(subproc.WorkerClient):
        def __init__(self, role, **kw):
            kw.setdefault("argv", argv)
            super().__init__(role, **kw)

    monkeypatch.setattr(modelsrv, "WorkerClient", _StubWC)
    srv = modelsrv.ModelServer()
    assert srv.start()
    daemon_client = modelsrv.SharedWorkerClient("rerank", timeout=45.0)
    daemon_client.info(timeout=5.0)              # Daemon._model_client's probe
    yield srv, daemon_client
    daemon_client.close()
    srv.stop()


# ---- #b-1, shared worker ---------------------------------------------------

def test_the_daemons_own_unbudgeted_rerank_does_not_hold_a_budgeted_view(stub, hub):
    """S2: memory_recall's rerank on the daemon's ONE client must not make a
    budgeted context view wait for the client's lock."""
    from refmatrix.reranker import RemoteReranker

    _srv, client = hub
    base = RemoteReranker(client)
    stub.rr(2.5)
    th = threading.Thread(target=lambda: _attempt(base))
    th.start()
    time.sleep(0.3)
    wall, out = _attempt(base.with_budget(0.8))
    th.join()
    assert out.startswith("skipped"), out
    assert wall < 1.2, f"budget 0.8 s, waited {wall:.2f} s behind the client lock"


def test_the_queue_estimate_is_answered_while_the_worker_is_busy(stub, hub):
    """#s-2 / S3b: the hub must answer the cost header WITHOUT the worker lock,
    so a pool that cannot fit behind a busy worker is skipped at once instead
    of after the whole budget."""
    from refmatrix import modelsrv
    from refmatrix.reranker import RemoteReranker

    _srv, client = hub
    base = RemoteReranker(client)
    stub.rr(0.6)
    assert _attempt(base)[1] == "scored"          # seeds ~0.2 s/doc
    stub.rr(3.0)
    other = modelsrv.SharedWorkerClient("rerank", timeout=45.0)
    th = threading.Thread(target=lambda: _attempt(RemoteReranker(other)))
    th.start()
    time.sleep(0.3)
    wall, out = _attempt(base.with_budget(2.5), docs=["d"] * 20)
    th.join()
    other.close()
    assert out.startswith("skipped") and "queued" in out, out
    assert wall < 0.6, f"the estimate waited {wall:.2f} s behind the rerank it predicts"


def test_a_cold_hub_worker_is_skipped_not_loaded_inside_the_budget(stub, monkeypatch):
    """A budget is no place to pay a cold model load (6-33 s on the real hub)."""
    from refmatrix import modelsrv, subproc
    from refmatrix.reranker import RemoteReranker

    argv = stub.argv(load_s=3.0)

    class _StubWC(subproc.WorkerClient):
        def __init__(self, role, **kw):
            kw.setdefault("argv", argv)
            super().__init__(role, **kw)

    monkeypatch.setattr(modelsrv, "WorkerClient", _StubWC)
    srv = modelsrv.ModelServer()
    assert srv.start()
    try:
        c = modelsrv.SharedWorkerClient("rerank", timeout=45.0)
        wall, out = _attempt(RemoteReranker(c).with_budget(1.0))
        c.close()
    finally:
        srv.stop()
    assert out.startswith("skipped") and "cold" in out, out
    assert wall < 0.5, wall


# ---- #b-1, private worker --------------------------------------------------

def test_a_busy_private_worker_is_skipped_not_waited_on(stub):
    from refmatrix import subproc
    from refmatrix.reranker import RemoteReranker

    wc = subproc.WorkerClient("rerank", argv=stub.argv())
    try:
        base = RemoteReranker(wc)
        base.model_name                              # Daemon._reranker(): loads
        stub.rr(2.5)
        th = threading.Thread(target=lambda: _attempt(base))
        th.start()
        time.sleep(0.3)
        wall, out = _attempt(base.with_budget(0.8))
        th.join()
    finally:
        wc.close()
    assert out.startswith("skipped") and "busy" in out, out
    assert wall < 1.2, wall
    assert stub.spawns() == 1


def test_a_slow_private_rerank_finishes_and_keeps_the_worker(stub):
    """Q2/Q3: a timeout on a private pipe KILLS the model. The budget must
    never do that: a started forward pass finishes, the overrun is recorded,
    and the next op does not pay a cold load."""
    from refmatrix import subproc
    from refmatrix.reranker import RemoteReranker

    wc = subproc.WorkerClient("rerank", argv=stub.argv(load_s=1.5))
    try:
        base = RemoteReranker(wc)
        base.model_name
        stub.rr(1.2)
        view = base.with_budget(0.8)
        wall, out = _attempt(view, docs=["a"])
        assert out == "scored", out
        assert view.overrun_s and view.overrun_s > 0.2, view.overrun_s
        stub.rr(0.05)
        # one doc: the EMA now says 1.2 s/doc, and 1.2 s fits in 3.0 s
        wall2, out2 = _attempt(base.with_budget(3.0), docs=["a"])
    finally:
        wc.close()
    assert stub.spawns() == 1, "the budget killed the private model process"
    assert stub.loads() == 1
    assert out2 == "scored" and wall2 < 0.6, (wall2, out2)


def test_a_cold_private_worker_is_skipped_without_spawning(stub):
    from refmatrix import subproc
    from refmatrix.reranker import RemoteReranker

    wc = subproc.WorkerClient("rerank", argv=stub.argv(load_s=3.0))
    try:
        wall, out = _attempt(RemoteReranker(wc).with_budget(2.0))
    finally:
        wc.close()
    assert out.startswith("skipped") and "cold" in out, out
    assert wall < 0.3 and stub.spawns() == 0, (wall, stub.spawns())


def test_an_evicted_private_worker_reads_as_cold(stub):
    """`evict_if_idle` closes the process; a header cached before that must not
    make the next budgeted call look warm and pay the respawn's load."""
    from refmatrix import subproc
    from refmatrix.reranker import RemoteReranker

    wc = subproc.WorkerClient("rerank", argv=stub.argv(load_s=2.0))
    try:
        base = RemoteReranker(wc)
        base.model_name
        assert wc.evict_if_idle(0.0)
        wall, out = _attempt(base.with_budget(1.0))
    finally:
        wc.close()
    assert out.startswith("skipped") and "cold" in out, out
    assert wall < 0.3 and stub.loads() == 1, (wall, stub.loads())


def test_the_private_header_tracks_the_cost_of_real_calls(stub):
    """The private estimate is read from the client's header, never from a
    blocking probe, so every rerank reply must refresh its cost."""
    from refmatrix import subproc
    from refmatrix.reranker import RemoteReranker

    wc = subproc.WorkerClient("rerank", argv=stub.argv())
    try:
        base = RemoteReranker(wc)
        base.model_name
        assert wc.info(nowait=True).get("cost_s_per_doc") is None
        stub.rr(0.4)
        _attempt(base, docs=["a", "b"])
        cost = wc.info(nowait=True).get("cost_s_per_doc")
    finally:
        wc.close()
    assert cost is not None and cost == pytest.approx(0.2, abs=0.08), cost


# ---- the budget's own arithmetic, on a real SharedWorkerClient -------------

class _RawHub:
    """A raw unix-socket peer speaking the frame protocol, for the two shapes
    a real hub cannot be made to produce on demand: a slow header and a
    worker-side deadline refusal. The CLIENT under test is real."""

    def __init__(self, path: Path, *, info_delay=0.0, rerank_reply=None):
        self.frames: list[dict] = []
        self.connections = 0
        self._info_delay = info_delay
        self._rerank_reply = rerank_reply
        self._srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._srv.bind(str(path))
        self._srv.listen(8)
        self._srv.settimeout(0.2)
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._serve, daemon=True)
        self._t.start()

    def _serve(self):
        from refmatrix.subproc import recv_frame, send_frame
        while not self._stop.is_set():
            try:
                conn, _ = self._srv.accept()
            except (socket.timeout, OSError):
                continue
            self.connections += 1

            def one(c=conn):
                rw = c.makefile("rwb")
                while True:
                    try:
                        req, _ = recv_frame(rw)
                    except Exception:
                        return
                    self.frames.append(req)
                    if req.get("op") == "info":
                        time.sleep(self._info_delay)
                        send_frame(rw, {"ok": True, "model": "stub/ce",
                                        "cost_s_per_doc": None, "queue_depth": 0})
                    elif self._rerank_reply is not None:
                        send_frame(rw, self._rerank_reply)
                    # else: never answer a rerank
            threading.Thread(target=one, daemon=True).start()

    def close(self):
        self._stop.set()
        self._srv.close()


def test_a_spent_budget_sends_nothing(stub):
    """B5: a caller already past its deadline must not put a frame on the wire."""
    from refmatrix import modelsrv
    from refmatrix.reranker import RemoteReranker, RerankSkipped

    raw = _RawHub(stub.dir / "m.sock")
    try:
        c = modelsrv.SharedWorkerClient("rerank", timeout=45.0)
        view = RemoteReranker(c, deadline=time.time() - 0.5)
        with pytest.raises(RerankSkipped):
            view.score("q", ["a", "b"])
        c.close()
    finally:
        raw.close()
    assert raw.frames == [] and raw.connections == 0, raw.frames


def test_the_socket_gets_what_is_left_after_the_header_not_the_whole_budget(stub):
    """B7: a 0.5 s header on a 1.0 s budget leaves 0.5 s for the rerank."""
    from refmatrix import modelsrv
    from refmatrix.reranker import RemoteReranker

    raw = _RawHub(stub.dir / "m.sock", info_delay=0.5)
    try:
        c = modelsrv.SharedWorkerClient("rerank", timeout=45.0)
        wall, out = _attempt(RemoteReranker(c).with_budget(1.0))
        c.close()
    finally:
        raw.close()
    assert out.startswith("skipped"), out
    assert wall < 1.2, f"budget 1.0 s, took {wall:.2f} s"


def test_a_worker_side_deadline_refusal_is_a_skip_not_an_error(stub):
    from refmatrix import modelsrv
    from refmatrix.reranker import RemoteReranker

    raw = _RawHub(stub.dir / "m.sock", rerank_reply={
        "ok": False, "error": "WorkerError: deadline expired 0.10s ago; not scored"})
    try:
        c = modelsrv.SharedWorkerClient("rerank", timeout=45.0)
        _wall, out = _attempt(RemoteReranker(c).with_budget(2.0))
        c.close()
    finally:
        raw.close()
    assert out.startswith("skipped") and "deadline" in out, out


# ---- the worker's half of the contract ------------------------------------

def test_the_rerank_reply_carries_the_workers_cost():
    from refmatrix.embed_worker import _RerankRole

    class _RR:
        model_name = "stub/ce"

        def score(self, q, docs):
            time.sleep(0.05)
            return [0.0] * len(docs)

    role = object.__new__(_RerankRole)
    role._rr = _RR()
    role._ema = None
    role._scored_docs = 0
    hdr, _ = role.handle("rerank", {"query": "q", "docs": ["a", "b"]}, b"")
    assert hdr["cost_s_per_doc"] == pytest.approx(0.025, abs=0.02)
    assert hdr["scored_docs"] == 2


# ---- the surface: an overrun is said, not swallowed ------------------------

def test_a_recorded_overrun_reaches_the_answers_warnings(monkeypatch):
    """The private path lets a started forward pass finish; the answer must
    say it ran over, or the overrun is the silent kind of bound."""
    from refmatrix import context as ctx
    import refmatrix.embedder as embmod
    import refmatrix.reranker as rmod

    class _Ent:
        kind = "doc"

    class _S:
        def get_entity_by_id(self, eid):
            return _Ent()

    class _RR:
        overrun_s = 0.7

    # the boundary: entity text and the scorer's I/O; `_rerank_bodied` is real
    monkeypatch.setattr(embmod, "extract_text_for_entity", lambda s, eid, kind: "x" * 400)
    monkeypatch.setattr(rmod, "rerank_entity_hits", lambda s, rr, q, subset, k: list(subset))
    warnings: list[str] = []
    ctx._rerank_bodied(_S(), _RR(), "q", [(1, 1.0), (2, 0.5)], warnings)
    assert any("overran" in w and "0.7" in w for w in warnings), warnings


def test_a_header_that_eats_the_budget_sends_no_rerank(stub):
    """When the cost header alone outlasts the budget, nothing is left to
    score with; a rerank frame then is a request the caller has already
    abandoned, which the worker would still queue. The probe is bounded by
    the remaining budget, so such a header times out and reads as cold —
    which is why the explicit "spent on the cost header" guard is an
    equivalent mutant (F16 in r10-remedy-mutations.log); it stays for timing
    jitter between the probe's end and the deadline."""
    from refmatrix import modelsrv
    from refmatrix.reranker import RemoteReranker

    raw = _RawHub(stub.dir / "m.sock", info_delay=0.9)
    try:
        c = modelsrv.SharedWorkerClient("rerank", timeout=45.0)
        _wall, out = _attempt(RemoteReranker(c).with_budget(0.8))
        c.close()
        time.sleep(0.3)        # let a stray frame land before counting
    finally:
        raw.close()
    assert out.startswith("skipped"), out
    assert [f.get("op") for f in raw.frames] == ["info"], raw.frames



# ---- ch-bsd r11 #b-1: a private worker does not stay cold ------------------

def _until(pred, timeout=6.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pred():
            return True
        time.sleep(0.05)
    return False


def test_a_respawned_private_worker_is_warm_again_after_any_real_call(stub):
    """r11 #b-1: `close()`/`_spawn()` clear the header and nothing refilled it,
    so after ONE jetsam respawn every budgeted rerank skipped as "cold" while
    the unbudgeted recall reranks kept the model loaded and serving."""
    from refmatrix import subproc
    from refmatrix.reranker import RemoteReranker

    wc = subproc.WorkerClient("rerank", argv=stub.argv())
    try:
        base = RemoteReranker(wc)
        base.model_name
        wc._proc.kill()
        wc._proc.wait()
        stub.rr(0.05)
        assert _attempt(base)[1] == "scored"            # respawns: the jetsam case
        assert stub.spawns() == 2
        outs = [_attempt(base.with_budget(2.0))[1] for _ in range(3)]
    finally:
        wc.close()
    assert outs == ["scored"] * 3, outs


def test_a_cold_private_worker_warms_in_the_background_then_scores(stub):
    """Nothing but budgeted callers: the first skips as cold AND starts one
    warmup; once it lands, budgeted reranks score."""
    from refmatrix import subproc
    from refmatrix.reranker import RemoteReranker

    wc = subproc.WorkerClient("rerank", argv=stub.argv(load_s=0.5))
    try:
        rr = RemoteReranker(wc)
        first = _attempt(rr.with_budget(1.0))
        _attempt(rr.with_budget(1.0))                     # a second skip starts no second load
        assert _until(lambda: wc.info(nowait=True).get("model")), "never warmed"
        later = _attempt(rr.with_budget(2.0))
    finally:
        wc.close()
    assert first[1].startswith("skipped") and "cold" in first[1], first
    assert later[1] == "scored", later
    assert stub.spawns() == 1 and stub.loads() == 1


def test_a_failing_warmup_is_named_by_the_skip(stub):
    """r6 #s-2's rule on the new path: a ModelNotCached is an operator action;
    the cold skip must carry it, not only `rmxd.log`."""
    from refmatrix import subproc
    from refmatrix.reranker import RemoteReranker

    (stub.dir / "fail").write_text("1")
    wc = subproc.WorkerClient("rerank", argv=stub.argv())
    try:
        rr = RemoteReranker(wc)
        _attempt(rr.with_budget(1.0))
        assert _until(lambda: wc.warm_error is not None), "warm never reported"
        out = _attempt(rr.with_budget(1.0))[1]
    finally:
        wc.close()
    assert "cold" in out and "ModelNotCached" in out, out


def test_the_daemons_reranker_never_loads_a_cold_private_model(stub, monkeypatch):
    """r11 #b-1, second route: after an idle eviction `_op_context` rebuilds
    the reranker BEFORE its budget starts, and `model_name` paid the full cold
    load there. A cold private worker warms in the background instead."""
    import threading as _th

    from refmatrix import reranker as rmod
    from refmatrix import subproc
    from refmatrix.daemon import Daemon

    monkeypatch.setattr(rmod, "rerank_available", lambda: True)
    d = object.__new__(Daemon)
    d._log = lambda *a, **k: None
    d._worker_lock = _th.Lock()
    d._reranker_inst = None
    wc = subproc.WorkerClient("rerank", argv=stub.argv(load_s=2.0))
    d._rerank_worker = wc
    try:
        t0 = time.time()
        r = d._reranker()
        wall = time.time() - t0
        assert r is not None
        assert wall < 0.5, f"_reranker() took {wall:.2f} s on a cold private worker"
        assert _until(lambda: wc.info(nowait=True).get("model")), "never warmed"
        assert _attempt(r.with_budget(2.0))[1] == "scored"
    finally:
        wc.close()


# ---- ch-bsd r11 #m-1: K2 / K3 / K7 ----------------------------------------

def test_a_cold_hub_role_warms_once_and_then_scores(stub, monkeypatch):
    """K2: the cold `nowait` answer must start the hub's warmup — and only one
    (K3), however many budgeted reads ask while it loads."""
    from refmatrix import modelsrv, subproc
    from refmatrix.reranker import RemoteReranker

    argv = stub.argv(load_s=0.6)

    class _StubWC(subproc.WorkerClient):
        def __init__(self, role, **kw):
            kw.setdefault("argv", argv)
            super().__init__(role, **kw)

    monkeypatch.setattr(modelsrv, "WorkerClient", _StubWC)
    srv = modelsrv.ModelServer()
    assert srv.start()
    try:
        c = modelsrv.SharedWorkerClient("rerank", timeout=45.0)
        rr = RemoteReranker(c)
        firsts = [_attempt(rr.with_budget(1.0))[1] for _ in range(4)]
        assert _until(lambda: (srv._clients.get("rerank") is not None
                               and srv._clients["rerank"].info(nowait=True).get("model")))
        later = _attempt(rr.with_budget(2.0))[1]
        c.close()
    finally:
        srv.stop()
    assert all(f.startswith("skipped") for f in firsts), firsts
    assert later == "scored", later
    assert stub.spawns() == 1 and stub.loads() == 1, (stub.spawns(), stub.loads())


def test_a_budgeted_view_closes_its_forked_connection(stub, hub):
    """K7: a fork per request that is never closed is a socket (and a hub
    handler thread) leaked per context op."""
    from refmatrix.reranker import RemoteReranker

    _srv, client = hub
    view = RemoteReranker(client).with_budget(2.0)
    assert view._client is not client
    assert _attempt(view)[1] == "scored"
    assert view._client._sock is None, "the forked connection was left open"


def test_concurrent_cold_skips_start_one_warm_thread(stub):
    """G5: every budgeted read on a cold worker asks for a warmup; one thread
    loads, the rest must not pile up behind the worker lock."""
    import threading as _th

    from refmatrix import subproc

    wc = subproc.WorkerClient("rerank", argv=stub.argv(load_s=1.0))
    try:
        for _ in range(5):
            wc.warm_async()
        warmers = [t for t in _th.enumerate() if t.name == "rmx-warm-rerank"]
        assert len(warmers) == 1, len(warmers)
        assert _until(lambda: wc.info(nowait=True).get("model"))
    finally:
        wc.close()


def test_an_unprobed_view_asks_the_worker_nothing_after_scoring(stub):
    """G7: the model name comes from the header the budget already read. Asked
    after scoring, `model_name` was a worker-bound `info` outside every bound."""
    from refmatrix import modelsrv
    from refmatrix.reranker import RemoteReranker

    raw = _RawHub(stub.dir / "m.sock", rerank_reply={"ok": True, "scores": [0.0, 0.0]})
    try:
        c = modelsrv.SharedWorkerClient("rerank", timeout=45.0)
        out = _attempt(RemoteReranker(c).with_budget(2.0), docs=["a", "b"])[1]
        c.close()
        time.sleep(0.2)
    finally:
        raw.close()
    assert out == "scored", out
    assert [(f.get("op"), bool(f.get("nowait"))) for f in raw.frames] == \
        [("info", True), ("rerank", False)], raw.frames
