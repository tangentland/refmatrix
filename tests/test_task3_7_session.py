"""Task 3.7 batch C — `rmx_session(action=list|recall|show)` (RED).

Spec #fam-session, #budgets, C9 (r1 S2), C4a:
  - every read goes through daemon ops (`memory_iter`, `memory_search`, `memory_get`) on
    the `sessions-<project>` partition, ONE attempt, 60 s; busy ⇒ `VerbBusyError` with no
    Store opened; absent ⇒ in-process read-only (C4a) — built on batch B's
    `verbs.session_memories` / `verbs.session_memory_get`;
  - the CLI `--project` FILTER is the verb param `project_filter` — `project` is the MCP
    transport's store selector and the MCP layer overwrites a param of that name;
  - #fam-session-stats: `session stats` → `harness`, re-routed onto the verb's `list`
    read (no writer-slot open).
The defect still at ee12ebd: `session recall QUERY` with ping down opens
`Store(root, partition=…)` read-WRITE (cli.py session_recall_cmd).

Result shapes pinned: list {sessions:[{session_id, project, branch, ended, turn_count,
title}], total}; recall {sessions:[{id, name, session_id, project, branch, started, ended,
turn_count, title, snippet}]}; show {session: <card row>} (mode=card).
"""
from __future__ import annotations

import inspect

import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod
from refmatrix import verbs
from refmatrix.store import Store
from tests.task3_7_helpers import FakeDaemon, init_store, rm, short_root
from tests.test_plan2_remedy import _SilentDaemon


@pytest.fixture
def root(monkeypatch):
    monkeypatch.delenv("RMX_PARTITION", raising=False)
    base, r = short_root("r37s-")
    monkeypatch.setattr(cli_mod, "_root", lambda: r)
    yield r
    rm(base)


def _card(i, *, project="/w/proj", branch="main", ended=None, body="worked on parser"):
    sid = f"{i:08d}-aaaa-bbbb-cccc-dddddddddddd"
    return {"name": f"session-{sid[:8]}", "mtype": "session",
            "content": f"# Session {i} title {{#root}}\n{body}",
            "metadata": {"session_id": sid, "project": project, "branch": branch,
                         "started": f"2026-10-0{i}T09:00:00",
                         "ended": ended or f"2026-10-0{i}T10:00:00", "turn_count": i}}


def _seed(root, cards):
    init_store(root)
    s = Store(root)
    try:
        with s.with_partition("sessions-proj"):
            for c in cards:
                s.add_memory(name=c["name"], content=c["content"], mtype="session",
                             metadata=c["metadata"])
    finally:
        s.close()


def _store_opens(monkeypatch) -> list:
    opened: list = []
    real = Store.__init__

    def rec(self, r, *a, **k):
        opened.append((str(r), k.get("read_only")))
        return real(self, r, *a, **k)
    monkeypatch.setattr(Store, "__init__", rec)
    return opened


# ---- C9: project_filter ---------------------------------------------------------------


def test_the_project_filter_is_not_named_project():
    sig = inspect.signature(verbs.session)
    assert "project_filter" in sig.parameters and "project" not in sig.parameters
    props = verbs.VERBS["rmx_session"].schema["properties"]
    assert "project_filter" in props
    assert set(props["action"]["enum"]) == {"list", "recall", "show"}


def test_an_mcp_project_selector_does_not_filter_sessions(root):
    _seed(root, [_card(1, project="/w/proj"), _card(2, project="/w/other")])
    out = verbs.VERBS["rmx_session"].run(root, {"action": "list", "project": "elsewhere",
                                                "project_filter": "other"})
    assert [s["project"] for s in out["sessions"]] == ["/w/other"], out


# ---- budgets + routing (daemon up) -------------------------------------------------------


def test_list_reads_memory_iter_on_the_sessions_partition_with_one_attempt(root, monkeypatch):
    fd = FakeDaemon({"memory_iter": {"ok": True, "result": {
        "rows": [_card(1), _card(3), _card(2)]}}}).install(monkeypatch)
    out = verbs.session(root, action="list")
    _op, args, timeout, retries = fd.last("memory_iter")
    assert args["partition"] == "sessions-proj" and timeout == 60.0 and retries == 0, (args,
                                                                                      timeout)
    assert [s["turn_count"] for s in out["sessions"]] == [3, 2, 1], "ended DESC"
    assert out["total"] == 3
    assert {"session_id", "project", "branch", "ended", "turn_count", "title"} <= set(
        out["sessions"][0])


def test_list_limit_offset_and_filters(root, monkeypatch):
    FakeDaemon({"memory_iter": {"ok": True, "result": {"rows": [
        _card(i, branch="main" if i % 2 else "dev") for i in range(1, 7)]}}}).install(monkeypatch)
    out = verbs.session(root, action="list", branch="main", limit=2, offset=1)
    assert [s["turn_count"] for s in out["sessions"]] == [3, 1], out
    assert out["total"] == 3


def test_recall_with_a_query_searches_with_the_cli_limit(root, monkeypatch):
    fd = FakeDaemon({"memory_search": {"ok": True, "result": {
        "rows": [_card(2, body="the parser bug"), {"name": "x", "mtype": "note"}]}}}
    ).install(monkeypatch)
    out = verbs.session(root, action="recall", query="parser", k=5)
    _op, args, timeout, retries = fd.last("memory_search")
    assert args["query"] == "parser" and args["limit"] == 100, "max(k * 4, 100)"
    assert args["partition"] == "sessions-proj" and timeout == 60.0 and retries == 0
    assert [s["turn_count"] for s in out["sessions"]] == [2], "non-session rows dropped"
    assert out["sessions"][0]["snippet"], out


def test_show_gets_the_card_by_name(root, monkeypatch):
    fd = FakeDaemon({"memory_get": {"ok": True, "result": {"memory": _card(4)}}}
                    ).install(monkeypatch)
    out = verbs.session(root, action="show", session_id="00000004")
    assert fd.last("memory_get")[1]["partition"] == "sessions-proj"
    assert out["session"]["name"] == "session-00000004", out


def test_a_refusal_is_a_verb_error_not_an_empty_list(root, monkeypatch):
    FakeDaemon({"memory_iter": {"ok": False, "error": "CANARY-sess-no"}}).install(monkeypatch)
    with pytest.raises(verbs.VerbError) as ei:
        verbs.session(root, action="list")
    assert "CANARY-sess-no" in str(ei.value)


# ---- busy ⇒ VerbBusyError, no Store opened -------------------------------------------------


@pytest.mark.parametrize("action,kw", [("list", {}), ("recall", {"query": "parser"}),
                                       ("show", {"session_id": "00000001"})])
def test_a_busy_daemon_is_busy_and_opens_no_store(monkeypatch, action, kw):
    monkeypatch.delenv("RMX_PARTITION", raising=False)
    d = _SilentDaemon()
    try:
        opened = _store_opens(monkeypatch)
        with pytest.raises(verbs.VerbBusyError):
            verbs.session(d.root, action=action, **kw)
        assert opened == [], f"a Store was opened under a busy daemon: {opened}"
    finally:
        d.close()


def test_cli_session_recall_query_on_a_busy_daemon_never_opens_the_writer(monkeypatch):
    """The defect at ee12ebd: ping failed → `Store(root, partition=…)` read-WRITE."""
    monkeypatch.delenv("RMX_PARTITION", raising=False)
    d = _SilentDaemon()
    try:
        monkeypatch.setattr(cli_mod, "_root", lambda: d.root)
        opened = _store_opens(monkeypatch)
        r = CliRunner().invoke(cli_mod.main, ["session", "recall", "parser"])
        assert [o for o in opened if not o[1]] == [], f"read-write Store opened: {opened}"
        assert r.exit_code != 0 and "busy" in (r.output + (r.stderr or "")), r.output
    finally:
        d.close()


# ---- absent ⇒ C4a in-process ---------------------------------------------------------------


def test_no_daemon_list_recall_show_read_in_process(root):
    _seed(root, [_card(1), _card(2, body="the parser bug")])
    lst = verbs.session(root, action="list")
    assert [s["turn_count"] for s in lst["sessions"]] == [2, 1], lst
    rec = verbs.session(root, action="recall", query="parser")
    assert [s["turn_count"] for s in rec["sessions"]] == [2], rec
    show = verbs.session(root, action="show", session_id="00000002")
    assert show["session"]["name"] == "session-00000002", show


def test_show_of_an_unknown_session_is_a_verb_error(root):
    _seed(root, [_card(1)])
    with pytest.raises(verbs.VerbError):
        verbs.session(root, action="show", session_id="ffffffff")


# ---- #fam-session-stats: harness, re-routed onto the verb's list read ------------------------


def test_session_stats_is_harness_with_a_true_reason():
    cat, reason = verbs.LEGACY_UNPAIRED[("session", "stats")]
    assert cat == "harness" and "verb-it" not in reason, (cat, reason)


def test_session_stats_reads_through_the_verbs_list(root, monkeypatch):
    _seed(root, [_card(1), _card(2)])
    real = verbs.session
    calls: list = []

    def spy(r, *a, **kw):
        calls.append(kw.get("action", a[0] if a else None))
        return real(r, *a, **kw)
    monkeypatch.setattr(verbs, "session", spy)
    opened = _store_opens(monkeypatch)
    res = CliRunner().invoke(cli_mod.main, ["session", "stats"])
    assert res.exit_code == 0, res.output
    assert calls and set(calls) == {"list"}, calls
    assert [o for o in opened if not o[1]] == [], f"session stats opened the writer: {opened}"
