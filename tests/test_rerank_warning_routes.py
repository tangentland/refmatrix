"""ch-bsd r8 #s-3: every rerank-warning ROUTE is pinned, not only its helper.

r7's tests stubbed the op under the verb, the daemon under the helper and the
client under `shared_reranker`; nine mutations that delete a route's warning
survived (R2 R3 R3b R5 R8 R9 R10 R13 R16). Each test here drives the real op
or surface over a REAL store (ingested bodies, real Lance vectors); only the
model boundary is stubbed: an embedder that returns a fixed vector, and a
reranker / worker that fails the way a missing model fails.
"""
from __future__ import annotations

import json
import threading

import numpy as np
import pytest

from refmatrix.ingest import ingest_path
from refmatrix.models_local import ModelNotCached
from refmatrix.reranker import RerankSkipped
from refmatrix.store import Store

BODY = ("The daemon was SIGKILLed by macOS jetsam under memory pressure while the "
        "embed worker held the model. ") * 4


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / ".refmatrix")
    s.init()
    docs = tmp_path / "docs"
    docs.mkdir()
    for i in range(3):
        (docs / f"deaths{i}.md").write_text(f"# Death {i}\n\n{BODY}\n")
    ingest_path(s, docs)
    yield s
    s.close()


class _Emb:
    dim = 4

    def embed_texts(self, texts):
        return np.array([[1.0, 0.5, 0.25, 0.125]] * len(texts), dtype="float32")


class _D:
    """A daemon over a real store; the model boundary fails like a missing model."""

    def __init__(self, st, *, reranker_raises=True, rr=None):
        self.store = st
        self._store_lock = threading.RLock()
        self._raise = reranker_raises
        self._rr = rr
        self.logged: list[str] = []

    def _st(self):
        return self.store

    def _open_read_store(self, partition, **kw):
        return None

    def _request_snapshot(self):
        pass

    def _log(self, msg):
        self.logged.append(msg)

    def _embedder(self):
        return _Emb()

    def _maybe_rerank(self, args):
        return True

    def _reranker(self):
        if self._raise:
            raise ModelNotCached("model 'x/y' is not in the local Hugging Face cache")
        return self._rr


@pytest.fixture
def mem_store(tmp_path):
    from refmatrix.vectors import LanceVectorStore

    s = Store(tmp_path / ".refmatrix")
    s.init()
    ids = [s.add_memory(name=f"m{i}", content=BODY) for i in range(3)]
    vs = LanceVectorStore(s.root / "vectors", partition=s._partition_name, dim=4)
    vs.upsert_vectors(ids, np.array([[1.0, 0.5, 0.25, 0.125]] * 3, dtype="float32"),
                      kind="memory")
    yield s
    s.close()


# R2
def test_ann_search_returns_the_rerank_degrade(mem_store):
    from refmatrix.daemon import _op_ann_search

    out = _op_ann_search(_D(mem_store), {"query": "daemon jetsam", "k": 2,
                                         "kinds": ["memory"]})
    assert out["hits"], out
    assert any("ModelNotCached" in w for w in out.get("warnings", [])), out


# R3, R3b
@pytest.mark.parametrize("fuse", [False, True])
def test_memory_recall_returns_the_rerank_degrade(mem_store, fuse):
    from refmatrix.daemon import _op_memory_recall

    out = _op_memory_recall(_D(mem_store), {"query": "daemon jetsam", "k": 2,
                                            "fuse": fuse})
    assert out["hits"], out
    assert any("ModelNotCached" in w for w in out.get("warnings", [])), out


class _ScoreRaises:
    def __init__(self, exc):
        self.exc = exc

    def score(self, query, docs):
        raise self.exc


# R10 (score-time failure merged by the op) and R13 (RerankSkipped)
@pytest.mark.parametrize("exc,needle", [
    (ModelNotCached("cached INCOMPLETE"), "rerank failed"),
    (RerankSkipped("10 docs x 1.0 s/doc = 10.0s > 3.0s left"), "rerank skipped"),
])
def test_the_context_op_carries_a_score_time_degrade(store, exc, needle):
    from refmatrix.daemon import _op_context

    d = _D(store, reranker_raises=False, rr=_ScoreRaises(exc))
    out = _op_context(d, {"ref": "memory pressure", "format": "json",
                          "grep_backstop": False})
    body_ws = json.loads(out["body"]).get("warnings") or []
    assert any(needle in w for w in body_ws), out["body"]
    # ...and stated ONCE: the op's own warnings do not repeat it (r8 #m-2)
    assert not any(needle in w for w in out.get("warnings", [])), out

    text = _op_context(d, {"ref": "memory pressure", "format": "text",
                           "grep_backstop": False})
    assert text["body"].count(needle) == 1, text["body"]


# R16: the ANCHORED path (the ref resolves to a graph entity) passes warnings too
def test_the_anchored_path_records_the_degrade(store):
    from refmatrix.context import build_context

    anchor = "jetsam"            # a concept: anchors AND its terms hit bodied rows
    b = build_context(store, anchor, grep_backstop=False,
                      reranker=_ScoreRaises(ModelNotCached("cached INCOMPLETE")))
    if b.anchor is None:
        pytest.fail(f"fixture: {anchor!r} did not resolve to an anchor")
    assert any("rerank failed" in w for w in b.warnings), b.warnings


# R9: scan-prompt puts a reached-but-failing worker's cause on its output
def test_scan_prompt_shows_the_cause(store, monkeypatch):
    from refmatrix import reranker, scan

    def failing_shared(log=None, timeout=None, probe_timeout=None, why=None):
        if why is not None:
            why.append("ModelNotCached: model 'x/y' is not in the local Hugging Face cache")
        return None

    monkeypatch.setattr(reranker, "shared_reranker", failing_shared)
    out = scan.scan_prompt(store, "why does memory pressure kill the daemon",
                           fmt="text")
    assert "rerank skipped: ModelNotCached" in out, out[:2000]


# R8: the replica recall leg names the CAUSE of a reached-but-failing worker
def test_replica_recall_names_the_cause(mem_store, monkeypatch):
    from refmatrix import cli as cli_mod
    from refmatrix import embedder, modelsrv, reranker

    monkeypatch.setattr(modelsrv, "shared_enabled", lambda: True)
    monkeypatch.setattr(modelsrv, "shared_available", lambda timeout=None: True)
    monkeypatch.setattr(modelsrv, "SharedWorkerClient", lambda *a, **k: object())
    monkeypatch.setattr(embedder, "RemoteEmbedder", lambda client: _Emb())
    monkeypatch.setattr(cli_mod, "_reader_store", lambda: mem_store)
    monkeypatch.setattr(cli_mod, "_resolve_partition", lambda: mem_store._partition_name)

    def failing_shared(log=None, timeout=None, probe_timeout=None, why=None):
        if why is not None:
            why.append("ModelNotCached: model 'x/y' is not in the local Hugging Face cache")
        return None

    monkeypatch.setattr(reranker, "shared_reranker", failing_shared)
    ws: list[str] = []
    hits = cli_mod._replica_memory_recall("daemon jetsam", k=2, kinds=["memory"],
                                          fuse=False, rerank=True, warnings=ws)
    assert hits, hits
    assert any("ModelNotCached" in w for w in ws), ws
    assert not any("shared worker unavailable" in w for w in ws), ws


# R5: the CLI's daemon branch prints the op's warnings on stderr
def test_cli_recall_daemon_branch_prints_the_warnings(mem_store, monkeypatch):
    from click.testing import CliRunner

    from refmatrix import cli as cli_mod
    from refmatrix import verbs

    monkeypatch.setenv("RMX_RECALL_REPLICA_FIRST", "0")
    monkeypatch.setattr(cli_mod, "_root", lambda: mem_store.root)
    monkeypatch.setattr(cli_mod, "_resolve_partition", lambda: mem_store._partition_name)
    monkeypatch.setattr(verbs, "require_daemon", lambda *a, **k: {"running": True})
    monkeypatch.setattr(cli_mod, "_memory_daemon_call", lambda op, args, **k: {
        "ok": True, "result": {"hits": [], "warnings": ["rerank skipped (X); hits unreranked"]}})

    r = CliRunner().invoke(cli_mod.main, ["memory", "recall", "daemon jetsam"])
    assert "rerank skipped (X); hits unreranked" in r.stderr, (r.exit_code, r.output, r.stderr)
