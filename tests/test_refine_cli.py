"""`rmx refine list/show/accept/reject` — the CLI drain for the hub's
promotion queue.

The queue had producers (bus promotions, the GMD curator) and hub-side
accept/reject ops, but nothing that called them from a terminal — so it only
ever grew, and the `global:queues` alert counted a number nobody could act on.
"""
from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod


def _cand(cid, *, status="pending", scope="global", project=None,
          name=None, content="a body", mtype="observation"):
    return {
        "id": cid, "ts": "2026-06-22T01:30:18", "origin": "bus",
        "scope": scope, "channel": "global:refmatrix", "project": project,
        "status": status,
        "suggested": {"name": name or f"announce-{cid}", "content": content,
                      "mtype": mtype, "tags": ["behavior"]},
    }


ROWS = [
    _cand("8311511383d5"),
    _cand("4c79e9521abb", scope="project", project="refmatrix"),
    _cand("83aaaaaaaaaa"),                       # shares a prefix with the 1st
    _cand("cc00000000ff", status="accepted"),
]


class _Hub:
    """Stand-in for the hub module: records rpc calls, returns canned results."""

    def __init__(self, accept=None):
        self.calls = []
        self._accept = accept or (lambda cid: {"ok": True, "memory_id": 42})

    def is_running(self):
        return True

    def rpc(self, op, args=None):
        args = args or {}
        self.calls.append((op, args))
        if op == "refine_list":
            st = args.get("status", "pending")
            rows = ROWS if st == "all" else [c for c in ROWS if c["status"] == st]
            return {"result": {"candidates": rows}}
        if op == "refine_accept":
            return {"result": self._accept(args["id"])}
        if op == "refine_reject":
            return {"result": {"ok": True}}
        raise AssertionError(f"unexpected op {op}")


@pytest.fixture
def hub(monkeypatch):
    h = _Hub()
    monkeypatch.setattr(cli_mod, "_require_hub", lambda: h)
    return h


@pytest.fixture
def runner():
    return CliRunner()


def _run(runner, args):
    return runner.invoke(cli_mod.main, ["refine", *args])


# -------------------------------------------------------------------- list ---

def test_list_shows_pending_by_default(runner, hub):
    r = _run(runner, ["list"])
    assert r.exit_code == 0
    assert "8311511383d5" in r.output
    assert hub.calls[0] == ("refine_list", {"status": "pending"})


def test_list_ids_are_not_truncated(runner, hub):
    """The id is the argument you paste into `accept`; an ellipsized id makes
    the whole surface unusable."""
    r = _run(runner, ["list"])
    assert "8311511383d5" in r.output
    assert "…" not in r.output.split("suggested")[0]


def test_list_filters_by_scope_and_project(runner, hub):
    r = _run(runner, ["list", "--scope", "project"])
    assert "4c79e9521abb" in r.output and "8311511383d5" not in r.output

    r = _run(runner, ["list", "--project", "refmatrix"])
    assert "4c79e9521abb" in r.output and "8311511383d5" not in r.output


def test_list_json_reports_total_alongside_shown(runner, hub):
    r = _run(runner, ["list", "--json", "-n", "1"])
    body = json.loads(r.output)
    assert body["shown"] == 1
    assert body["total"] == 3          # 3 pending of 4 rows


def test_list_says_when_it_capped(runner, hub):
    """A -n cap must not read as 'that is all there is'."""
    r = _run(runner, ["list", "-n", "1"])
    assert "showing 1 of 3" in r.output


def test_list_empty_is_stated_not_blank(runner, hub):
    r = _run(runner, ["list", "--status", "rejected"])
    assert "no rejected candidates" in r.output


# -------------------------------------------------------------------- show ---

def test_show_prints_the_full_body(runner, hub):
    r = _run(runner, ["show", "4c79e9521abb"])
    assert r.exit_code == 0
    assert "a body" in r.output
    assert "scope=project" in r.output


def test_show_accepts_an_unambiguous_prefix(runner, hub):
    r = _run(runner, ["show", "4c79"])
    assert r.exit_code == 0 and "4c79e9521abb" in r.output


# ------------------------------------------------------------- id safety ----

def test_ambiguous_prefix_refuses_rather_than_guessing(runner, hub):
    """`83` matches two candidates. Accept WRITES a memory, so picking one
    silently is not an acceptable convenience."""
    r = _run(runner, ["accept", "83"])
    assert r.exit_code != 0
    assert "matches 2 candidates" in r.output
    assert not any(op == "refine_accept" for op, _ in hub.calls)


def test_unknown_id_errors(runner, hub):
    r = _run(runner, ["accept", "deadbeef"])
    assert r.exit_code != 0
    assert "no candidate matching" in r.output


# ------------------------------------------------------------ accept/reject --

def test_accept_sends_the_full_id_not_the_prefix(runner, hub):
    r = _run(runner, ["accept", "4c79"])
    assert r.exit_code == 0
    assert ("refine_accept", {"id": "4c79e9521abb"}) in hub.calls
    assert "entity 42" in r.output


def test_accept_handles_several_ids(runner, hub):
    r = _run(runner, ["accept", "8311511383d5", "4c79e9521abb"])
    assert r.exit_code == 0
    assert sum(1 for op, _ in hub.calls if op == "refine_accept") == 2
    assert "2/2 accepted" in r.output


def test_a_failing_candidate_does_not_strand_the_rest(runner, monkeypatch):
    """Batch drain: one already-accepted id must not abort the others."""
    def accept(cid):
        if cid == "8311511383d5":
            return {"ok": False, "error": "already accepted"}
        return {"ok": True, "memory_id": 7}

    h = _Hub(accept=accept)
    monkeypatch.setattr(cli_mod, "_require_hub", lambda: h)
    r = CliRunner().invoke(
        cli_mod.main, ["refine", "accept", "8311511383d5", "4c79e9521abb"])
    assert r.exit_code == 0
    assert "already accepted" in r.output
    assert "1/2 accepted" in r.output
    assert sum(1 for op, _ in h.calls if op == "refine_accept") == 2


def test_reject_marks_without_writing_a_memory(runner, hub):
    r = _run(runner, ["reject", "8311511383d5"])
    assert r.exit_code == 0
    assert ("refine_reject", {"id": "8311511383d5"}) in hub.calls
    assert not any(op == "refine_accept" for op, _ in hub.calls)


# --------------------------------------------------------------- hub down ----

def test_hub_down_is_a_clear_error(runner, monkeypatch):
    import click

    def boom():
        raise click.ClickException(
            "hub not running — start it with `rmx hub start`")

    monkeypatch.setattr(cli_mod, "_require_hub", boom)
    r = _run(runner, ["list"])
    assert r.exit_code != 0
    assert "hub not running" in r.output
