"""Task 3.7 batch C — `rmx_refine(action=list|show)` over `verbs._hub_rpc` (RED).

Spec #fam-refine, #fam-refine-gate, C9:
  - read-only views of the hub's refinement queue through THE typed hub boundary
    `verbs._hub_rpc`: a hub `ok:false` is a `VerbError` with the hub's words — today
    `_refine_rows` turns it into `[]` ("no pending candidates");
  - `--project` is the verb param `project_filter` (r1 S2); `-n` is `limit` (20);
    `--full` / `--json` are renderings (CLI-only);
  - show: an id or a unique prefix; no match ⇒ `VerbError`, an ambiguous prefix ⇒
    `VerbArgsError` (accept writes a memory, so a prefix never silently picks one);
  - re-decided: `refine accept` / `refine reject` → `operator` (the human approval gate
    of the "no silent writes" queue; the hub UI is the other surface; the gmd-curator
    agent never calls `rmx refine`).
Result shapes: list {candidates, total, shown}; show {candidate}.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod
from refmatrix import hub as hub_mod
from refmatrix import verbs

_REPO = Path(__file__).resolve().parent.parent
_ROWS = [
    {"id": "a1b2c3d4e5f6", "ts": "2026-10-01T10:00", "scope": "project", "project": "proj",
     "status": "pending", "suggested": {"name": "n1", "mtype": "note", "content": "body one"}},
    {"id": "a1ffffffffff", "ts": "2026-10-02T10:00", "scope": "global", "project": None,
     "status": "pending", "suggested": {"name": "n2", "mtype": "note", "content": "body two"}},
    {"id": "b9b9b9b9b9b9", "ts": "2026-10-03T10:00", "scope": "project", "project": "other",
     "status": "pending", "suggested": {"name": "n3", "mtype": "note", "content": "body 3"}},
]


@pytest.fixture
def hub(monkeypatch, tmp_path):
    root = tmp_path / ".refmatrix"
    root.mkdir()
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    sent: list = []
    state = {"resp": {"ok": True, "result": {"candidates": list(_ROWS)}}}

    def rpc(op, args=None, **kw):
        sent.append((op, args))
        r = state["resp"]
        if isinstance(r, BaseException):
            raise r
        return r
    monkeypatch.setattr(hub_mod, "is_running", lambda: True)
    monkeypatch.setattr(hub_mod, "rpc", rpc)
    return root, sent, state


def test_list_goes_through_the_hub_and_filters(hub):
    root, sent, _state = hub
    out = verbs.refine(root, action="list", scope="project", project_filter="other")
    assert sent[-1] == ("refine_list", {"status": "pending"}), sent
    assert [c["id"] for c in out["candidates"]] == ["b9b9b9b9b9b9"]
    assert out["total"] == 1 and out["shown"] == 1


def test_list_limit_caps_shown_not_total(hub):
    root, _sent, _state = hub
    out = verbs.refine(root, action="list", limit=2)
    assert out["shown"] == 2 and out["total"] == 3, out


def test_a_hub_refusal_is_a_verb_error_not_an_empty_list(hub):
    root, _sent, state = hub
    state["resp"] = {"ok": False, "error": "CANARY-hub-no"}
    with pytest.raises(verbs.VerbError) as ei:
        verbs.refine(root, action="list")
    assert "CANARY-hub-no" in str(ei.value)


def test_a_hub_timeout_is_a_verb_error(hub):
    root, _sent, state = hub
    state["resp"] = TimeoutError("timed out")
    with pytest.raises(verbs.VerbError):
        verbs.refine(root, action="list")


def test_cli_refine_list_refusal_fails_loudly(hub):
    _root, _sent, state = hub
    state["resp"] = {"ok": False, "error": "CANARY-hub-no"}
    r = CliRunner().invoke(cli_mod.main, ["refine", "list"])
    assert r.exit_code != 0, r.output
    assert "no pending candidates" not in r.output
    assert "CANARY-hub-no" in r.output + (r.stderr or "")


def test_show_resolves_a_unique_prefix_over_all_statuses(hub):
    root, sent, _state = hub
    out = verbs.refine(root, action="show", cand_id="b9b9")
    assert sent[-1] == ("refine_list", {"status": "all"})
    assert out["candidate"]["id"] == "b9b9b9b9b9b9"


def test_show_ambiguous_prefix_is_an_args_error_and_no_match_a_verb_error(hub):
    root, _sent, _state = hub
    with pytest.raises(verbs.VerbArgsError):
        verbs.refine(root, action="show", cand_id="a1")
    with pytest.raises(verbs.VerbError):
        verbs.refine(root, action="show", cand_id="zz")


def test_the_project_filter_is_not_named_project():
    import inspect
    sig = inspect.signature(verbs.refine)
    assert "project_filter" in sig.parameters and "project" not in sig.parameters
    assert set(verbs.VERBS["rmx_refine"].schema["properties"]["action"]["enum"]) == {
        "list", "show"}


@pytest.mark.parametrize("path", [("refine", "accept"), ("refine", "reject")])
def test_accept_and_reject_are_the_operator_gate_with_a_code_checked_reason(path):
    cat, reason = verbs.LEGACY_UNPAIRED[path]
    assert cat == "operator", cat
    assert "verb-it" not in reason and "gmd-curator agent drives" not in reason, reason
    assert "approval" in reason, "the reason names the human approval gate"
    for rel in ("src/refmatrix/templates/agents/gmd-curator.md", ".claude/agents/gmd-curator.md"):
        assert "rmx refine" not in (_REPO / rel).read_text(), rel
