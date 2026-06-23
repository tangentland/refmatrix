"""`rmx task push/list` must resolve to the SAME session ring.

Regression for the cross-invocation bug: `task push` used a bare `_stm()`
(session "default" with no RMX_SESSION) while `task list` used
`prefer_latest=True` (the active Claude session whose ring the hook writes most
recently). So a plain-shell push landed in `default.tasks.json` and list read
`<claude-session>.tasks.json` — the stack always looked empty.
"""
from __future__ import annotations

import json

from click.testing import CliRunner

from refmatrix import stm as stm_mod
from refmatrix.cli import main


def _seed_active_session(root_dir, sess: str) -> None:
    """Make `latest_session()` resolve to `sess` by writing a recent ring —
    same effect the Claude UserPromptSubmit hook has during a live session."""
    s = stm_mod.Stm(root_dir / ".refmatrix", sess)
    s.record("input", "hello")  # writes <sess>.jsonl


def test_push_and_list_share_the_active_session(tmp_path, monkeypatch):
    root = tmp_path
    (root / ".refmatrix").mkdir(parents=True)
    monkeypatch.setenv("REFMATRIX_ROOT", str(root / ".refmatrix"))
    monkeypatch.delenv("RMX_SESSION", raising=False)
    _seed_active_session(root, "claude-abc-123")

    r = CliRunner().invoke(main, ["task", "push", "refactor X"])
    assert r.exit_code == 0, r.output
    assert "depth=1" in r.output

    # The push must have landed in the active session ring, not "default".
    stm_d = root / ".refmatrix" / "stm"
    assert (stm_d / "claude-abc-123.tasks.json").exists()
    assert not (stm_d / "default.tasks.json").exists()

    # And list (same resolution) sees it.
    r2 = CliRunner().invoke(main, ["task", "list"])
    assert r2.exit_code == 0, r2.output
    assert "refactor X" in r2.output


def test_push_then_pop_round_trip_same_session(tmp_path, monkeypatch):
    root = tmp_path
    (root / ".refmatrix").mkdir(parents=True)
    monkeypatch.setenv("REFMATRIX_ROOT", str(root / ".refmatrix"))
    monkeypatch.delenv("RMX_SESSION", raising=False)
    _seed_active_session(root, "claude-xyz")

    CliRunner().invoke(main, ["task", "push", "task-A"])
    CliRunner().invoke(main, ["task", "push", "task-B"])
    tasks_file = root / ".refmatrix" / "stm" / "claude-xyz.tasks.json"
    assert len(json.loads(tasks_file.read_text())) == 2

    r = CliRunner().invoke(main, ["task", "pop"])
    assert r.exit_code == 0, r.output
    assert "task-B" in r.output  # popped the top
    assert len(json.loads(tasks_file.read_text())) == 1
