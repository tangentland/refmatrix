"""ch-bsd r7 #s-1: every rerank leg says when an answer came back UNRERANKED.

r6 made the `context` op's construction failure loud and stopped there. The
siblings stayed quiet or named the wrong cause:
- `shared_reranker` turned a reached-but-failing worker (ModelNotCached on its
  `info` probe) into "shared worker unavailable" — the fetch command was lost;
- `_apply_rerank_safe` (daemon `memory_recall` / `ann_search`) only logged;
- a score-time failure inside `build_context` went to the PROCESS's stderr —
  the daemon's log on the daemon path — while the answer looked ranked.

The model worker is the external boundary stubbed here (a reranker whose
`score` raises, a daemon whose `_reranker` raises); store, context building,
the op helper, the verb and the CLI render are real.
"""
from __future__ import annotations

import json

import pytest

from refmatrix.models_local import ModelNotCached


@pytest.fixture
def store(tmp_path):
    from refmatrix.ingest import ingest_path
    from refmatrix.store import Store

    s = Store(tmp_path / ".refmatrix")
    s.init()
    # INGESTED real bodies: `_rerank_bodied` reaches the model only with >= 2
    # rows carrying >= 120 chars of text, and content_rank needs the index
    # ingest writes (r7's probe used tldr-only rows and never reached `score`).
    body = ("The daemon was SIGKILLed by macOS jetsam under memory pressure "
            "while the embed worker held the model. ") * 4
    docs = tmp_path / "docs"
    docs.mkdir()
    for i in range(3):
        (docs / f"deaths{i}.md").write_text(f"# Death {i}\n\n{body}\n")
    ingest_path(s, docs)
    yield s
    s.close()


class _Broken:
    def score(self, query, docs):
        raise ModelNotCached("model 'x/y' is cached INCOMPLETE")


@pytest.mark.parametrize("surface", ["build_context", "content_only_bundle"])
def test_a_score_time_failure_rides_on_the_bundle(store, surface):
    from refmatrix import context as ctx

    b = getattr(ctx, surface)(store, "memory pressure", grep_backstop=False,
                              reranker=_Broken())

    assert any("ModelNotCached" in w for w in b.warnings), b.warnings
    assert json.loads(ctx.render_json(b))["warnings"] == b.warnings
    assert "# warning: rerank failed" in ctx.render_text(b)


def test_a_phrase_with_no_graph_anchor_is_still_reranked(store):
    """build_context's no-anchor hand-off dropped the reranker."""
    from refmatrix import context as ctx

    seen = []

    class _Spy:
        def score(self, query, docs):
            seen.append(query)
            return [0.0] * len(docs)

    ctx.build_context(store, "memory pressure", grep_backstop=False, reranker=_Spy())
    assert seen == ["memory pressure"], seen


def test_a_clean_bundle_carries_no_warnings_key(store):
    from refmatrix import context as ctx

    b = ctx.content_only_bundle(store, "memory pressure", grep_backstop=False)
    assert b.warnings == []
    assert "warnings" not in json.loads(ctx.render_json(b))


class _D:
    def __init__(self):
        self.logged: list[str] = []

    def _log(self, msg):
        self.logged.append(msg)

    def _reranker(self):
        raise ModelNotCached("model 'x/y' is not in the local Hugging Face cache")


def test_the_daemon_rerank_helper_returns_the_degrade_as_a_warning():
    from refmatrix.daemon import _apply_rerank_safe

    d, ws = _D(), []
    out = _apply_rerank_safe(d, "q", ([(1, "body")], [], []), k=5, warnings=ws)

    assert out is None
    assert len(ws) == 1 and "ModelNotCached" in ws[0] and "unreranked" in ws[0], ws
    assert d.logged == ws


def test_shared_reranker_hands_back_the_cause_of_a_reached_worker(monkeypatch):
    from refmatrix import modelsrv, reranker

    class _Client:
        def __init__(self, *a, **k):
            pass

        def info(self, timeout=None):
            raise ModelNotCached("model 'x/y' is not in the local Hugging Face cache")

    monkeypatch.setattr(reranker, "rerank_enabled", lambda: True)
    monkeypatch.setattr(reranker, "rerank_available", lambda: True)
    monkeypatch.setattr(modelsrv, "shared_enabled", lambda: True)
    monkeypatch.setattr(modelsrv, "shared_available", lambda: True)
    monkeypatch.setattr(modelsrv, "SharedWorkerClient", _Client)

    why: list[str] = []
    assert reranker.shared_reranker(timeout=1.0, why=why) is None
    assert why and "ModelNotCached" in why[0], why


def test_the_recall_verb_carries_the_ops_warnings(tmp_path, monkeypatch):
    from refmatrix import verbs

    def fake_call(root, op, payload, **k):
        if op == "memory_recall":
            return {"hits": [], "warnings": ["rerank skipped (X); hits unreranked"]}
        return {}

    monkeypatch.setattr(verbs, "_call", fake_call)
    out = verbs.memory_recall(tmp_path, query="q", scope="project")
    assert "rerank skipped (X); hits unreranked" in out["warnings"], out


def test_search_dense_renders_reranked_hits_and_prints_warnings(tmp_path, monkeypatch):
    """bug-089: `KeyError: 'distance'` on a reranking daemon."""
    from click.testing import CliRunner

    from refmatrix import cli as cli_mod
    from refmatrix import daemon as daemon_mod
    from refmatrix.store import Store

    root = tmp_path / ".refmatrix"
    Store(root).init()
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    monkeypatch.setattr(daemon_mod, "ping", lambda r, *a, **k: True)
    monkeypatch.setattr(daemon_mod, "call", lambda r, op, args, **k: {
        "ok": True, "result": {"hits": [{"id": 1, "score": 0.9, "reranked": True}],
                               "warnings": ["W"]}})

    r = CliRunner().invoke(cli_mod.main, ["search-dense", "q"])

    assert r.exit_code == 0, r.output
    assert "rerank score" in r.stdout and "0.900" in r.stdout, r.stdout
    assert "rmx search-dense: W" in r.stderr


def test_the_context_verb_merges_body_and_op_warnings(tmp_path, monkeypatch):
    """r8 #m-2: the op's warnings were assigned OVER the body's, so a
    construction failure hid a score-time one."""
    from refmatrix import verbs

    monkeypatch.setattr(verbs, "_call", lambda root, op, payload, **k: {
        "body": json.dumps({"anchor": None, "groups": {}, "warnings": ["B"]}),
        "warnings": ["A"]})
    assert verbs.context(tmp_path, "x")["warnings"] == ["B", "A"]


def test_the_verb_merge_does_not_repeat_a_warning_already_in_the_body(tmp_path, monkeypatch):
    """r9 #m-1 (M2): the merge's de-duplication was untested."""
    from refmatrix import verbs

    monkeypatch.setattr(verbs, "_call", lambda root, op, payload, **k: {
        "body": json.dumps({"anchor": None, "groups": {}, "warnings": ["B", "A"]}),
        "warnings": ["A", "C"]})
    assert verbs.context(tmp_path, "x")["warnings"] == ["B", "A", "C"]
