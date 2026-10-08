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
def client(monkeypatch, tmp_path):
    # Isolate the global store (RMX_HOME) so endpoints like /api/refine read a
    # clean per-test queue instead of the developer's live ~/.refmatrix bus.
    monkeypatch.setenv("RMX_HOME", str(tmp_path / "home"))
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
    monkeypatch.setattr(search.daemon_mod, "ping", lambda r, timeout=0.5, **kw: True)
    monkeypatch.setenv("RMX_HOME", str(tmp_path / "home"))  # no global store

    # context now goes through the in-process replica bundle, not a daemon call
    # `**kw`: plan-3 r8 added `on_error=` to the real call and this double
    # rejected it, so the code leg raised, only the memory leg survived, and
    # `/api/where` answered with memory hits alone (bug-069).
    monkeypatch.setattr(search, "_replica_bundle",
                        lambda root, ref, degree=0, **kw: {
                            "anchor": {"name": "keys", "kind": "concept"},
                            "groups": {"mentions": [
                                {"name": "keychain.py", "kind": "code",
                                 "path": "/p/keychain.py", "line": 3}]},
                        })

    def fake_call(r, op, args, timeout=60.0, **kw):
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


def test_the_omnibox_keeps_the_skip_note_when_some_stores_answered():
    """ch-bsd r1 #b-4: `doWhere` computed `skipNote` and spent it ONLY in the
    zero-hits branch, so the PARTIAL case — some stores answered, one could not
    be read — overwrote `innerHTML` and dropped it. Partial is the common
    fan-out shape, which made the comment four lines above it ("a store that
    could not be searched is SAID, never rendered as 'no hits'") false exactly
    where it mattered.

    A source-level assertion, and named as the weak gate it is: this repo runs
    no JS. It pins the one thing that regressed — the note reaching the
    grouped-render assignment — rather than the behaviour, which would need a
    DOM. The server half (`/api/where` carrying `skipped`) is covered by
    `test_where_federates` and by `search`'s own tests.
    """
    from pathlib import Path

    from refmatrix import ui

    js = (Path(ui.__file__).resolve().parent / "static" / "app.js").read_text()
    body = js[js.index("async function doWhere("):]
    body = body[:body.index("\n}\n")]

    assert "skipNote" in body
    grouped = body[body.index("const groups = {}"):]
    assert "skipNote +" in grouped, (
        "the grouped render drops the skipped-store note — the partial "
        "fan-out case renders as if every store answered")
    # And the reason is escaped: it carries exception text and paths now.
    assert "esc(s.reason)" in body, "skip reasons go into innerHTML unescaped"


def test_app_js_has_one_escape_and_server_text_goes_through_it():
    """ch-bsd r2 #s-2 / r3 #s-4: `doWhere` carried a second, shadowing
    `const esc` with its own null rule, and three renderers wrote server- or
    bus-produced text into `innerHTML` raw (`d.error`, `r.error`, the bus
    line's `d.from`/`d.channel`/`d.body`). Source-level, and weak for the same
    reason as the test above: this repo runs no JS. It pins the two things
    that regressed — one definition, and no raw interpolation at those sites.
    """
    import re
    from pathlib import Path

    from refmatrix import ui

    js = (Path(ui.__file__).resolve().parent / "static" / "app.js").read_text()

    assert len(re.findall(r"\bconst esc\s*=", js)) == 1, "a second esc shadows the shared one"
    for raw in ("${d.error}", "${r.error ||", "${d.from}", "${d.channel}",
                "${d.body}", "innerHTML += d.line +"):
        assert raw not in js, f"unescaped server text reaches innerHTML: {raw}"
