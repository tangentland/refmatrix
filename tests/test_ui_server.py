"""Phase 6: web UI server — endpoints, graph conversion, federated where."""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from starlette.testclient import TestClient  # noqa: E402

from refmatrix import discovery  # noqa: E402
from refmatrix.hub import Hub  # noqa: E402
from refmatrix.ui import server as srv  # noqa: E402


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(discovery, "discover_roots", lambda: [])
    monkeypatch.setattr(discovery, "all_projects",
                        lambda with_footprint=True: [])
    return TestClient(srv.create_app(Hub(port=0)))


def test_spa_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/style.css").status_code == 200


def test_read_spine_endpoints(client):
    assert client.get("/api/projects").json()["projects"] == []
    assert client.get("/api/usage").json()["ok"]
    assert client.get("/api/hub").json()["ok"]
    assert client.get("/api/health").json()["ok"]
    assert client.get("/api/taxonomy").json()["ok"]


def test_project_register_endpoint(client, tmp_path, monkeypatch):
    # isolate the registry to a temp home so the test never pollutes the real
    # ~/.refmatrix/registry.json with a tmp path the watchdog would later chase
    monkeypatch.setenv("RMX_HOME", str(tmp_path / "home"))
    root = tmp_path / "proj" / ".refmatrix"
    root.mkdir(parents=True)
    r = client.post("/api/projects/register", json={"root": str(tmp_path / "proj")})
    assert r.json()["ok"]
    bad = client.post("/api/projects/register", json={"root": "/no/such/place"})
    assert bad.json()["ok"] is False


def test_canon_and_schedule_endpoints(client, monkeypatch, tmp_path):
    monkeypatch.setenv("RMX_HOME", str(tmp_path / "home"))
    assert client.get("/api/canon?concept=foo").json()["ok"]
    root = str(tmp_path / "p" / ".refmatrix")
    r = client.post("/api/schedule", json={"root": root, "op": "sync",
                                           "interval_s": 600})
    assert r.json()["ok"]
    got = client.get("/api/schedule").json()
    assert got["ok"] and got["result"]["schedule"]


def test_bus_focus_refine_endpoints(client, tmp_path):
    assert client.get("/api/bus/channels").json()["ok"]
    assert client.get("/api/refine").json()["result"]["candidates"] == []
    assert client.get("/api/queues").json()["ok"]
    # publish via API then it's in history
    r = client.post("/api/bus/pub", json={"channel": "global:t", "body": "hi", "type": "note"})
    assert r.json()["ok"]
    hist = client.get("/api/bus/history?channel=global:t").json()
    assert any(m["body"] == "hi" for m in hist["result"]["messages"])
    # focus on an empty root
    root = tmp_path / "p" / ".refmatrix"; root.mkdir(parents=True)
    f = client.get(f"/api/focus?root={root}&session=default").json()
    assert f["ok"] and f["result"]["graph"]["nodes"] == []


def test_context_to_graph_conversion():
    bundle = {
        "ref": "foo",
        "anchor": {"name": "foo", "kind": "concept", "tldr": "t"},
        "groups": {
            "defines": [{"name": "foo.py", "kind": "code", "path": "/a/foo.py",
                         "weight": 5, "line": 10}],
            "mentions": [{"name": "bar", "kind": "concept"}],
        },
        "truncated": False,
    }
    g = srv._context_to_graph(bundle)
    names = {n["name"] for n in g["nodes"]}
    assert names == {"foo", "foo.py", "bar"}
    anchor = [n for n in g["nodes"] if n.get("anchor")][0]
    assert anchor["name"] == "foo"
    assert len(g["edges"]) == 2
    assert {e["linkage"] for e in g["edges"]} == {"defines", "mentions"}


def test_where_federates(monkeypatch, tmp_path):
    # /api/where delegates to refmatrix.search.federated_where — patch THERE.
    from refmatrix import search
    root = Path("/tmp/projX/.refmatrix")
    monkeypatch.setattr(search.discovery, "discover_roots", lambda: [root])
    monkeypatch.setattr(search.discovery, "store_name", lambda r: "projX")
    monkeypatch.setattr(search.daemon_mod, "ping", lambda r, timeout=0.5: True)
    monkeypatch.setenv("RMX_HOME", str(tmp_path / "home"))  # no global store

    # context now goes through the in-process replica bundle, not a daemon call
    monkeypatch.setattr(search, "_replica_bundle", lambda root, ref, degree=0: {
        "anchor": {"name": "keys", "kind": "concept"},
        "groups": {"mentions": [
            {"name": "keychain.py", "kind": "code", "path": "/p/keychain.py",
             "line": 3}]},
    })

    def fake_call(r, op, args, timeout=60.0):
        if op == "memory_search":
            return {"ok": True, "result": {"rows": [
                {"name": "where-keys-note", "content": "in the drawer"}]}}
        return {"ok": False, "error": "?"}

    monkeypatch.setattr(search.daemon_mod, "call", fake_call)
    c = TestClient(srv.create_app(Hub(port=0)))
    res = c.get("/api/where?q=keys").json()
    assert res["ok"]
    kinds = {h["kind"] for h in res["result"]["results"]}
    assert "code" in kinds and "memory" in kinds
    assert all(h["project"] == "projX" for h in res["result"]["results"])
