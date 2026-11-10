"""Task 3.7 batch A — the focus family as actions on `rmx_focus` (RED).

Spec #fam-focus / #decisions-r2: `rmx_focus` gains `action` (13 values, default
`context`); every STM action resolves its session through
`verbs.resolve_session_source` (`purpose="read"` for reads, `"write"` for writes).
Three defects die with the old CLI bodies:
  #fam-focus-clear     `focus clear` skipped the resolver and cleared `$RMX_SESSION`
                       or the literal `default` ring, printing "focus cleared";
  #fam-focus-subjects  `focus subjects` listed the CODE partition while
                       `change_subject` writes `memory_partition(root)`, and an
                       `ok:false` printed "no subjects yet";
  #fam-focus-composite `focus composite` had no `--session` and `composite.py`
                       called `latest_session` itself.

Result shapes pinned here (the CLI renders them; test_verb_parity.py's canaries use
the same keys): tail/export/show → `events` (export/show rows carry `line`), topics →
`topics` [{lead, members, first_line, last_line}], subject → `subject`, subjects →
`rows`, detours → `detours` [{index, label, line, ts}] (index 1 = most recent, the
`focus return` selector), detour → the mark {label, line, ts}, return → {returned,
remaining, …}, clear / clear_subject → {cleared, session}, composite → {composite,
session}. Every STM action also returns `session` and `session_source`.
"""
from __future__ import annotations

import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod
from refmatrix import discovery, stm as stm_mod, verbs
from tests.task3_7_helpers import FakeDaemon, init_store, rm, short_root

_NO_SESSION_ENV = ("RMX_SESSION", "CLAUDE_PID", "CLAUDECODE", "CLAUDE_CODE_SESSION_ID")


@pytest.fixture
def root(monkeypatch):
    for k in _NO_SESSION_ENV:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.delenv("RMX_PARTITION", raising=False)
    base, r = short_root("r37f-")
    monkeypatch.setattr(cli_mod, "_root", lambda: r)
    yield r
    rm(base)


def _ring(root, session, lines):
    s = stm_mod.Stm(root, session)
    for ln in lines:
        s.record("input", ln)
    return s


def _ring_files(root, session):
    return sorted(p.name for p in (root / "stm").glob(f"{session}*"))


# ---- the dispatcher ----------------------------------------------------------


def test_context_is_unchanged_for_a_caller_that_sends_no_action(root):
    """Existing MCP callers send no `action` (a guard that must keep holding)."""
    _ring(root, "sA", ["AlphaParser alpha_lexer"])
    out = verbs.VERBS["rmx_focus"].run(root, {"session": "sA"})
    assert {"graph", "tasks", "dialogue", "milestones", "last_line", "events_total"} <= set(out)


def test_tail_returns_the_last_n_events_with_its_session_provenance(root):
    _ring(root, "sA", ["one AlphaX", "two BetaX", "three GammaX"])
    out = verbs.focus(root, action="tail", n=2, session="sA")
    assert out["session"] == "sA" and out["session_source"] == "explicit", out
    assert [e["terse"] for e in out["events"]] == ["two BetaX", "three GammaX"], out


def test_tail_default_n_is_the_cli_default_20(root):
    _ring(root, "sA", [f"event number {i} Sym{i}" for i in range(25)])
    out = verbs.focus(root, action="tail", session="sA")
    assert len(out["events"]) == 20, len(out["events"])


def test_show_returns_the_line_and_its_context_window(root):
    _ring(root, "sA", ["l1 A1", "l2 A2", "l3 A3", "l4 A4"])
    out = verbs.focus(root, action="show", line=2, context=1, session="sA")
    assert [e["line"] for e in out["events"]] == [1, 2, 3], out
    assert out["events"][1]["terse"] == "l2 A2"
    assert out["total"] == 4


def test_export_returns_every_event_line_numbered_and_never_writes_a_file(root, tmp_path,
                                                                        monkeypatch):
    """r3 M1: `-o/--out` is a CLI-only render option; an MCP call never writes."""
    _ring(root, "sA", [f"ev {i} Sym{i}" for i in range(30)])
    monkeypatch.chdir(tmp_path)
    out = verbs.focus(root, action="export", session="sA")
    assert [e["line"] for e in out["events"]] == list(range(1, 31))
    assert out["events"][0]["terse"] == "ev 0 Sym0"
    assert "out" not in verbs.VERBS["rmx_focus"].schema["properties"], (
        "an MCP-reachable file write")
    assert list(tmp_path.iterdir()) == []


def test_topics_returns_clusters_with_their_log_ranges(root):
    _ring(root, "sA", ["AlphaParser alpha_lexer AlphaToken"] * 3
          + ["BetaWidget beta_gadget BetaSprocket"] * 3)
    out = verbs.focus(root, action="topics", session="sA")
    assert out["topics"], out
    t = out["topics"][0]
    assert {"lead", "members", "first_line", "last_line"} <= set(t), t


def test_subject_and_clear_subject_round_trip(root):
    s = _ring(root, "sA", ["x Alpha"])
    s.set_subject("Topic Q")
    got = verbs.focus(root, action="subject", session="sA")
    assert got["subject"]["label"] == "Topic Q", got
    cl = verbs.focus(root, action="clear_subject", session="sA")
    assert cl["cleared"] is True, cl
    assert verbs.focus(root, action="subject", session="sA")["subject"] is None


def test_detour_detours_return_round_trip(root):
    _ring(root, "sA", ["AlphaParser alpha_lexer"])
    m = verbs.focus(root, action="detour", label="tangent", session="sA")
    assert m["label"] == "tangent" and isinstance(m["line"], int), m
    ds = verbs.focus(root, action="detours", session="sA")["detours"]
    assert [(d["index"], d["label"]) for d in ds] == [(1, "tangent")], ds
    r = verbs.focus(root, action="return", selector="1", session="sA")
    assert r["returned"] == "tangent" and r["remaining"] == 0, r
    assert verbs.focus(root, action="detours", session="sA")["detours"] == []


@pytest.mark.parametrize("action,kw", [("detour", {"label": "x"}), ("return", {}),
                                       ("clear_subject", {}), ("clear", {})])
def test_every_stm_write_refuses_an_unresolved_session(root, action, kw):
    """21.1 D2: a write that does not resolve is refused, never the newest ring."""
    _ring(root, "newest", ["AlphaParser"])
    with pytest.raises(verbs.SessionUnresolved):
        verbs.focus(root, action=action, **kw)


def test_an_mcp_call_reaches_an_action_through_the_tool_args(root):
    _ring(root, "sA", ["one AlphaX", "two BetaX"])
    out = verbs.VERBS["rmx_focus"].run(root, {"action": "tail", "n": 1, "session": "sA"})
    assert [e["terse"] for e in out["events"]] == ["two BetaX"], out


# ---- #fam-focus-clear ----------------------------------------------------------


def test_focus_clear_clears_the_resolved_ring_only(root):
    _ring(root, "sA", ["a Alpha"])
    _ring(root, "default", ["d Delta"])
    out = verbs.focus(root, action="clear", session="sA")
    assert out["cleared"] is True and out["session"] == "sA", out
    assert not any(n.endswith(".jsonl") for n in _ring_files(root, "sA")), _ring_files(root, "sA")
    assert "default.jsonl" in _ring_files(root, "default"), "clear touched another ring"


def test_cli_focus_clear_with_no_session_is_refused_and_clears_nothing(root):
    """The defect: hooks do not export RMX_SESSION, so `rmx focus clear` cleared
    the literal `default` ring and said "focus cleared"."""
    _ring(root, "default", ["d Delta"])
    _ring(root, "claude-sess", ["c Gamma"])
    r = CliRunner().invoke(cli_mod.main, ["focus", "clear"])
    assert r.exit_code == 2, (r.exit_code, r.output)
    assert "SessionUnresolved" in (r.output + (r.stderr or "")), r.output
    assert "focus cleared" not in r.output
    assert "default.jsonl" in _ring_files(root, "default")
    assert "claude-sess.jsonl" in _ring_files(root, "claude-sess")


def test_cli_focus_clear_with_rmx_session_clears_that_ring_and_names_it(root, monkeypatch):
    _ring(root, "sA", ["a Alpha"])
    _ring(root, "default", ["d Delta"])
    monkeypatch.setenv("RMX_SESSION", "sA")
    r = CliRunner().invoke(cli_mod.main, ["focus", "clear"])
    assert r.exit_code == 0, r.output
    assert "sA" in r.output, "the CLI must say WHICH ring it cleared"
    assert "default.jsonl" in _ring_files(root, "default")


# ---- #fam-focus-subjects -------------------------------------------------------


def _legacy_partition_answers(root, subject_rows):
    legacy = f"memory-{discovery.store_name(root)}"
    return legacy, {
        "partition_list": {"ok": True, "result": {"rows": [{"name": discovery.store_name(root)},
                                                           {"name": legacy}]}},
        "subject_list": {"ok": True, "result": {"rows": subject_rows}},
    }


def test_subjects_reads_the_memory_partition_with_one_budgeted_attempt(root, monkeypatch):
    """The defect shows only when the memory partition differs from the project
    partition (legacy `memory-<p>`), so the RED test sets that up (r1)."""
    legacy, answers = _legacy_partition_answers(
        root, [{"id": 7, "name": "topic-q", "label": "Topic Q", "leaves": 2}])
    fd = FakeDaemon(answers).install(monkeypatch)
    out = verbs.focus(root, action="subjects")
    assert [r["label"] for r in out["rows"]] == ["Topic Q"], out
    _op, args, timeout, retries = fd.last("subject_list")
    assert args.get("partition") == legacy, ("subjects read the code partition", args)
    assert timeout <= 10.0 and retries == 0, (timeout, retries)


def test_subjects_refusal_is_a_verb_error_not_an_empty_list(root, monkeypatch):
    _legacy, answers = _legacy_partition_answers(root, [])
    answers["subject_list"] = {"ok": False, "error": "CANARY-refusal: catalog unreadable"}
    FakeDaemon(answers).install(monkeypatch)
    with pytest.raises(verbs.VerbError) as ei:
        verbs.focus(root, action="subjects")
    assert "CANARY-refusal" in str(ei.value)


def test_subjects_transport_timeout_is_busy(root, monkeypatch):
    _legacy, answers = _legacy_partition_answers(root, [])
    answers["subject_list"] = TimeoutError("timed out")
    FakeDaemon(answers).install(monkeypatch)
    with pytest.raises(verbs.VerbBusyError):
        verbs.focus(root, action="subjects")


def test_cli_subjects_refusal_fails_loudly_not_no_subjects_yet(root, monkeypatch):
    _legacy, answers = _legacy_partition_answers(root, [])
    answers["subject_list"] = {"ok": False, "error": "CANARY-refusal"}
    FakeDaemon(answers).install(monkeypatch)
    r = CliRunner().invoke(cli_mod.main, ["focus", "subjects"])
    assert r.exit_code != 0, r.output
    assert "no subjects yet" not in r.output
    assert "CANARY-refusal" in r.output + (r.stderr or "")


def test_subjects_with_no_daemon_reads_the_legacy_memory_partition_in_process(root):
    """C4a: absent ⇒ snapshot_read's in-process branch, on the SAME partition
    `change_subject` writes (`memory_partition(root)`)."""
    from refmatrix.store import Store
    legacy = f"memory-{discovery.store_name(root)}"
    init_store(root)
    s = Store(root)
    try:
        with s.with_partition(legacy):
            s.upsert_subject("Legacy Topic")
    finally:
        s.close()
    out = verbs.focus(root, action="subjects")
    assert "Legacy Topic" in [r.get("label") for r in out["rows"]], out
    assert out.get("source") == "in-process", out


# ---- #fam-focus-composite ------------------------------------------------------


def _two_rings(root):
    _ring(root, "sA", ["AlphaParser alpha_lexer AlphaToken working"] * 4)
    _ring(root, "sB", ["BetaWidget beta_gadget BetaSprocket working"] * 4)  # newest
    assert stm_mod.latest_session(root) == "sB"


def test_composite_uses_the_explicit_session_not_the_newest_ring(root):
    init_store(root)
    _two_rings(root)
    out = verbs.focus(root, action="composite", session="sA", no_expand=True)
    assert "AlphaParser" in out["composite"], out
    assert "BetaWidget" not in out["composite"], out
    assert out["session"] == "sA"


def test_composite_resolves_through_the_one_resolver(root, monkeypatch):
    """$RMX_SESSION beats the newest ring in the resolver; `latest_session`
    alone (composite.py's own default) would pick sB."""
    init_store(root)
    _two_rings(root)
    monkeypatch.setenv("RMX_SESSION", "sA")
    out = verbs.focus(root, action="composite", no_expand=True)
    assert out["session"] == "sA" and "AlphaParser" in out["composite"], out


def test_cli_composite_gains_session(root):
    init_store(root)
    _two_rings(root)
    r = CliRunner().invoke(cli_mod.main, ["focus", "composite", "--session", "sA",
                                          "--no-expand"])
    assert r.exit_code == 0, r.output
    assert "AlphaParser" in r.output and "BetaWidget" not in r.output, r.output
