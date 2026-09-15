"""ch-bsd plan-3 r1 remediation: #sk-4 one 'which rows' (dense payload +
row annotation + recent/widen helper shared with the CLI fallback), #sk-5 a
named include_session divergence, #sk-7 warnings instead of silent swallows,
#meh-9 descriptions + no dead transport prop, #meh-10 no redundant ping."""
from __future__ import annotations

import json
import shutil
import tempfile
import time
from pathlib import Path

import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod
from refmatrix import daemon as daemon_mod
from refmatrix import verbs
from refmatrix.cli import main as cli_main
from refmatrix.store import Store
from tests.test_verbs_memory_recall import _spawn, DAY


# ---- #sk-4 shared row selection ---------------------------------------------

def test_recent_rows_helper_overfetches_filters_and_widens():
    calls = []

    def fetch(since_seconds, limit):
        calls.append((since_seconds, limit))
        if since_seconds is not None:
            return []
        return [{"name": "d", "mtype": "session/digest"}, {"name": "a", "mtype": "note"}]
    rows, widened = verbs.recent_rows(fetch, k=1, patterns=["session/*"],
                                      since_seconds=7 * DAY, widen_if_empty=True)
    assert widened is True and [r["name"] for r in rows] == ["a"]
    assert calls == [(7 * DAY, 10), (None, 10)]          # ×10 over-fetch when filtering
    rows, widened = verbs.recent_rows(fetch, k=1, patterns=[], since_seconds=7 * DAY,
                                      widen_if_empty=False)
    assert rows == [] and widened is False


def test_annotate_hit_puts_score_distance_fused_on_the_row():
    m = verbs.annotate_hit({"name": "x"}, {"distance": 0.0})
    assert m["score"] == pytest.approx(1.0) and m["distance"] == 0.0 and m["fused"] is False
    f = verbs.annotate_hit({"name": "y"}, {"score": 0.3, "fused": True})
    assert f["score"] == 0.3 and f["fused"] is True


def test_verb_dense_rows_carry_the_annotation(monkeypatch, tmp_path):
    monkeypatch.setattr(daemon_mod, "ping", lambda root, **kw: True)

    def call(root, op, args=None, **kw):
        if op == "partition_list":
            return {"ok": True, "result": {"rows": []}}
        if op == "memory_recall":
            return {"ok": True, "result": {"hits": [{"id": 1, "distance": 0.0}]}}
        if op == "memory_get":
            return {"ok": True, "result": {"memory": {"id": 1, "name": "m", "mtype": "note"}}}
        return {"ok": False, "error": op}
    monkeypatch.setattr(daemon_mod, "call", call)
    monkeypatch.setattr("refmatrix.discovery.store_name", lambda root: "p")
    out = verbs.memory_recall(tmp_path, query="q")
    assert out["memories"][0]["score"] == pytest.approx(1.0)
    assert out["memories"][0]["fused"] is False and out["warnings"] == []


def test_cli_dense_path_builds_its_payload_through_the_verb_helper(monkeypatch, tmp_path):
    root = tmp_path / ".refmatrix"; root.mkdir()
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    monkeypatch.setenv("RMX_RECALL_REPLICA_FIRST", "0")
    monkeypatch.setattr(daemon_mod, "ping", lambda root, **kw: True)
    monkeypatch.setattr("refmatrix.discovery.store_name", lambda root: "p")
    real = verbs.payload_memory_recall
    built = []
    monkeypatch.setattr(verbs, "payload_memory_recall",
                        lambda *a, **kw: built.append(real(*a, **kw)) or built[-1])
    sent = []

    def call(root, op, args=None, **kw):
        sent.append((op, args))
        if op == "partition_list":
            return {"ok": True, "result": {"rows": []}}
        if op == "memory_recall":
            return {"ok": True, "result": {"hits": [{"id": 1, "distance": 0.0}]}}
        if op == "memory_get":
            return {"ok": True, "result": {"memory": {"id": 1, "name": "m", "mtype": "note",
                                                      "tags": [], "metadata": {}, "content": "c"}}}
        return {"ok": False, "error": op}
    monkeypatch.setattr(daemon_mod, "call", call)
    r = CliRunner().invoke(cli_main, ["memory", "recall", "hello", "--json", "-k", "3"],
                                           catch_exceptions=False)
    assert r.exit_code == 0, r.output + (r.stderr or "")
    assert built and built[0]["query"] == "hello"
    op_args = dict(sent)["memory_recall"]
    for k, v in built[0].items():
        assert op_args[k] == v
    rows = json.loads(r.stdout)
    assert rows[0]["score"] == pytest.approx(1.0) and rows[0]["fused"] is False


@pytest.fixture
def old_store():
    """A store whose newest memory is 8d old, NO daemon: the CLI must degrade
    to the reader and still widen (#sk-4: the fallback was a second untested
    implementation of the rule)."""
    base = Path(tempfile.mkdtemp(prefix="rmxo-"))
    root = base / "proj" / ".refmatrix"; root.parent.mkdir()
    s = Store(root); s.init()
    now = time.time()
    for name, age in (("fresh", 8 * DAY), ("old", 10 * DAY)):
        s.add_memory(name=name, content=name, mtype="project")
        s._connect().execute("UPDATE entities SET created_at=? WHERE name=? AND kind='memory'",
                             [now - age, name])
    s.close()
    yield root
    shutil.rmtree(base, ignore_errors=True)


def test_cli_session_start_widens_with_the_daemon_down(old_store, monkeypatch):
    monkeypatch.setattr(cli_mod, "_root", lambda: old_store)
    assert not daemon_mod.ping(old_store)
    r = CliRunner().invoke(cli_main, ["memory", "recall", "--session-start", "-k", "5", "--json"],
                                           catch_exceptions=False)
    assert r.exit_code == 0, r.output + (r.stderr or "")
    assert [m["name"] for m in json.loads(r.stdout)] == ["fresh", "old"]
    assert "widened" in (r.stderr or "")
    assert "reading the store directly" in (r.stderr or "")


# ---- #sk-5 the divergence is a named parameter -----------------------------

@pytest.fixture
def live():
    base, root = _spawn(1 * DAY)
    yield root
    daemon_mod.stop_daemon(root)
    shutil.rmtree(base, ignore_errors=True)


def test_cli_recent_passes_include_session_explicitly(live, monkeypatch):
    """`rmx memory recall --recent` shows session cards (operator affordance);
    it says so by passing include_session=True, not by an empty exclude list."""
    monkeypatch.setattr(cli_mod, "_root", lambda: live)
    seen = []
    real = verbs.memory_recall
    monkeypatch.setattr(verbs, "memory_recall",
                        lambda root, **kw: seen.append(kw) or real(root, **kw))
    r = CliRunner().invoke(cli_main, ["memory", "recall", "--recent", "--json"],
                                           catch_exceptions=False)
    assert r.exit_code == 0, r.output + (r.stderr or "")
    assert seen[0]["include_session"] is True and seen[0].get("exclude_mtype") is None
    assert "digest" in [m["name"] for m in json.loads(r.stdout)]
    seen.clear()
    r = CliRunner().invoke(cli_main, ["memory", "recall", "--session-start", "--json"],
                                           catch_exceptions=False)
    assert seen[0]["include_session"] is False
    assert "digest" not in [m["name"] for m in json.loads(r.stdout)]


# ---- #sk-7 warnings, not silence --------------------------------------------

def test_global_failure_surfaces_as_a_warning(live, monkeypatch):
    monkeypatch.setattr("refmatrix.hub.global_store_root", lambda: live)  # exists → tries the hub
    def boom(*a, **kw):
        raise OSError("hub socket refused")
    monkeypatch.setattr("refmatrix.hub.global_call", boom)
    out = verbs.memory_recall(live, recent=True, scope="both", k=5)
    assert [m["name"] for m in out["memories"]] == ["fresh", "old", "older"]
    assert out["warnings"] and "global" in out["warnings"][0] and "hub socket refused" in out["warnings"][0]


def test_cli_prints_verb_warnings_on_stderr(live, monkeypatch):
    monkeypatch.setattr(cli_mod, "_root", lambda: live)
    monkeypatch.setattr("refmatrix.hub.global_store_root", lambda: live)
    def boom(*a, **kw):
        raise OSError("hub socket refused")
    monkeypatch.setattr("refmatrix.hub.global_call", boom)
    r = CliRunner().invoke(cli_main, ["memory", "recall", "--recent", "--scope", "both", "--json"],
                                           catch_exceptions=False)
    assert r.exit_code == 0
    assert json.loads(r.stdout)
    assert "warning" in (r.stderr or "") and "hub socket refused" in (r.stderr or "")


def test_context_failure_is_named_on_the_row(live, monkeypatch):
    real_call = daemon_mod.call
    def call(root, op, args=None, **kw):
        if op == "context":
            raise OSError("context op blew up")
        return real_call(root, op, args, **kw)
    monkeypatch.setattr(daemon_mod, "call", call)
    out = verbs.memory_recall(live, recent=True, k=1, degree=1)
    row = out["memories"][0]
    assert row.get("context") is None and "context op blew up" in row["context_error"]
    assert any("context op blew up" in w for w in out["warnings"])


# ---- #meh-9 / #meh-10 schema hygiene -----------------------------------------

def test_recall_schema_documents_its_knobs_and_carries_no_dead_session_prop():
    props = verbs.VERBS["rmx_memory_recall"].schema["properties"]
    assert "session/*" in props["exclude_mtype"]["description"]
    assert props["k"].get("description")
    assert "session" not in props
    assert "session" in verbs.VERBS["rmx_focus"].schema["properties"]
    assert props["root"].get("description") and props["project"].get("description")


def test_verb_defaults_match_the_cli_k():
    assert verbs.VERBS["rmx_memory_recall"].defaults["k"] == 10
    assert verbs.VERBS["rmx_memory_recall"].defaults["query"] is None


def test_dense_path_pings_once(monkeypatch, tmp_path):
    pings = []
    monkeypatch.setattr(daemon_mod, "ping", lambda root, **kw: pings.append(1) or True)
    monkeypatch.setattr("refmatrix.discovery.store_name", lambda root: "p")

    def call(root, op, args=None, **kw):
        if op == "memory_recall":
            return {"ok": True, "result": {"hits": []}}
        return {"ok": True, "result": {"rows": []}}
    monkeypatch.setattr(daemon_mod, "call", call)
    verbs.memory_recall(tmp_path, query="q")
    # memory_partition pings once (legacy partition probe) + _call pings once
    assert len(pings) == 2
