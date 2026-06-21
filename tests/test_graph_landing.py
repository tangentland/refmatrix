"""Graph-tab landing views: top-N concepts daemon op + tree endpoint."""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from starlette.testclient import TestClient  # noqa: E402

from refmatrix import discovery  # noqa: E402
from refmatrix.daemon import _op_top_concepts  # noqa: E402
from refmatrix.hub import Hub  # noqa: E402
from refmatrix.store import Store  # noqa: E402
from refmatrix.ui import server as srv  # noqa: E402


class _D:
    """Minimal daemon stand-in exposing a store + lock for the op."""
    def __init__(self, store):
        import threading
        self.store = store
        self._store_lock = threading.RLock()


def test_top_concepts_ranks_by_density(tmp_path):
    s = Store(tmp_path / ".refmatrix"); s.init()
    with s.with_partition("p"):
        hot = s.add_concept("BuildContext")
        cold = s.add_concept("RareThing")
        for i in range(5):
            e = s.upsert_entity(kind="code", name=f"f{i}.py")
            s.link("mentions", hot, e)
        e = s.upsert_entity(kind="code", name="z.py")
        s.link("mentions", cold, e)
        d = _D(s)
        # the op uses d.store bound to the active partition
        out = _op_top_concepts(d, {"n": 10})["concepts"]
        names = [c["name"] for c in out]
        assert "BuildContext" in names
        # denser concept ranks above sparser
        if "RareThing" in names:
            assert names.index("BuildContext") < names.index("RareThing")
        assert out[0]["total"] >= out[-1]["total"]  # sorted desc
    s.close()


def test_top_concepts_partition_scoped_no_cross_partition_dupes(tmp_path):
    """Regression: a concept name living in two partitions must not appear
    twice in one partition's ranked list (the viascope `new_id ×3` bug)."""
    s = Store(tmp_path / ".refmatrix"); s.init()
    with s.with_partition("A"):
        cA = s.add_concept("shared_sym")
        for i in range(4):
            s.link("mentions", cA, s.upsert_entity(kind="code", name=f"a{i}.py"))
    with s.with_partition("B"):
        cB = s.add_concept("shared_sym")
        for i in range(9):
            s.link("mentions", cB, s.upsert_entity(kind="code", name=f"b{i}.py"))
    with s.with_partition("A"):
        out = _op_top_concepts(_D(s), {"n": 10})["concepts"]
        names = [c["name"] for c in out]
        assert names.count("shared_sym") == 1          # not duplicated
        assert dict(zip(names, [c["total"] for c in out]))["shared_sym"] == 4  # A's count, not B's
    s.close()


def test_context_op_honors_partition_under_ambient_drift(tmp_path):
    """Regression: `_op_context` must bind the requested partition. On a
    multi-partition daemon the ambient partition drifts (memory ops enter/exit
    with_partition); without an explicit bind, build_context resolved the
    concept in the wrong partition → anchor=None ('graph not coming up')."""
    import threading
    from refmatrix.daemon import _op_context
    import json as _json

    s = Store(tmp_path / ".refmatrix"); s.init()
    with s.with_partition("code-proj"):
        cid = s.add_concept("Widget")
        for i in range(3):
            s.link("defines", cid, s.upsert_entity(kind="code", name=f"w{i}.py"))
    # create another partition + leave the store's AMBIENT partition pointing there
    with s.with_partition("memory-proj"):
        s.add_memory(name="note", content="x")
    s.with_partition("memory-proj").__enter__()  # drift ambient away from code-proj

    class D:
        def __init__(self, st):
            self.store = st; self._store_lock = threading.RLock()
        def _request_snapshot(self): pass

    resp = _op_context(D(s), {"ref": "Widget", "format": "json", "degree": 1,
                              "partition": "code-proj"})
    bundle = _json.loads(resp["body"])
    assert bundle["anchor"] and bundle["anchor"]["name"] == "Widget"
    assert sum(len(v) for v in bundle["groups"].values()) == 3
    s.close()


def test_context_to_graph_filters_tests():
    bundle = {
        "ref": "make_config",
        "anchor": {"name": "make_config", "kind": "concept"},
        "groups": {"defines": [
            {"name": "tests.test_x._make_config", "kind": "code",
             "path": "/p/tests/test_x.py"},
            {"name": "config.builder", "kind": "code", "path": "/p/config/builder.py"},
            {"name": "conftest._cfg", "kind": "code", "path": "/p/conftest.py"},
        ]},
    }
    excl = srv._context_to_graph(bundle, include_tests=False)
    names = {n["name"] for n in excl["nodes"]}
    assert names == {"make_config", "config.builder"}  # tests + conftest dropped
    assert excl["dropped_tests"] == 2
    incl = srv._context_to_graph(bundle, include_tests=True)
    assert len({n["name"] for n in incl["nodes"]}) == 4


def test_is_test_path():
    for p in ["/a/tests/test_x.py", "/a/test_foo.py", "/a/foo_test.py",
              "/a/conftest.py", "/a/__tests__/x.js", "/a/x.spec.ts"]:
        assert srv._is_test_path(p), p
    for p in ["/a/config/builder.py", "/a/src/store.py", None, "/a/contest.py"]:
        assert not srv._is_test_path(p), p


def test_tree_endpoint_lists_code_and_docs(tmp_path, monkeypatch):
    monkeypatch.setattr(discovery, "discover_roots", lambda: [])
    proj = tmp_path / "proj"
    (proj / "src").mkdir(parents=True)
    (proj / ".refmatrix").mkdir()
    (proj / "src" / "a.py").write_text("x=1")
    (proj / "README.md").write_text("# hi")
    (proj / "node_modules").mkdir()
    (proj / "node_modules" / "junk.js").write_text("//skip")
    c = TestClient(srv.create_app(Hub(port=0)))
    r = c.get(f"/api/tree?root={proj / '.refmatrix'}").json()
    assert r["ok"]
    rels = {e["rel"] for e in r["result"]["entries"]}
    assert "README.md" in rels
    assert any(rel.endswith("a.py") for rel in rels)
    assert not any("node_modules" in rel for rel in rels)  # skipped


def test_top_endpoint_routes_to_daemon(monkeypatch, tmp_path):
    monkeypatch.setattr(discovery, "discover_roots", lambda: [])
    monkeypatch.setattr(srv.daemon_mod, "ping", lambda r, timeout=0.5: True)
    monkeypatch.setattr(srv.daemon_mod, "call",
                        lambda r, op, a, timeout=60.0: {
                            "ok": True, "result": {"concepts": [
                                {"name": "X", "total": 9, "by_link": {}}]}})
    c = TestClient(srv.create_app(Hub(port=0)))
    r = c.get(f"/api/top?root={tmp_path}/.refmatrix&n=5").json()
    assert r["ok"] and r["result"]["concepts"][0]["name"] == "X"
