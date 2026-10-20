"""`rmx task push/list` must resolve to the SAME session ring.

Regression for the cross-invocation bug: `task push` used a bare `_stm()`
(session "default" with no RMX_SESSION) while `task list` used
`prefer_latest=True` (the active Claude session whose ring the hook writes most
recently). So a plain-shell push landed in `default.tasks.json` and list read
`<claude-session>.tasks.json` — the stack always looked empty.

Task 21.1 D2 (task-21.1-context-usage-telemetry.md, the resolver's `write` tail) removed the
`latest` / `default` tail for writes: an UNRESOLVED push is refused with `SessionUnresolved`
and writes no ring at all — neither the newest ring nor `default`. These tests used to pin the
newest-ring routing D2 forbids; they now pin the refusal, and keep the original intent (push
and list/pop share ONE ring) with an explicitly resolved session (`RMX_SESSION`, source `env`).
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


def _plain_shell(monkeypatch, root) -> None:
    (root / ".refmatrix").mkdir(parents=True)
    monkeypatch.setenv("REFMATRIX_ROOT", str(root / ".refmatrix"))
    # No session signal of any kind: the runner's own Claude env is not this test's.
    for k in ("RMX_SESSION", "CLAUDE_PID", "CLAUDECODE", "CLAUDE_CODE_SESSION_ID"):
        monkeypatch.delenv(k, raising=False)


def test_an_unresolved_push_is_refused_and_writes_no_ring(tmp_path, monkeypatch):
    """21.1 D2: with no explicit / envelope / pointer / env session, a push is a refused
    write -- it names SessionUnresolved and lands in NEITHER the newest ring nor `default`."""
    root = tmp_path
    _plain_shell(monkeypatch, root)
    _seed_active_session(root, "claude-abc-123")

    r = CliRunner().invoke(main, ["task", "push", "refactor X"])
    assert r.exit_code != 0, r.output
    assert "SessionUnresolved" in r.output, r.output

    stm_d = root / ".refmatrix" / "stm"
    assert sorted(p.name for p in stm_d.glob("*.tasks.json")) == [], list(stm_d.iterdir())


def test_push_and_list_share_the_resolved_session(tmp_path, monkeypatch):
    """The original intent, on a RESOLVED session (21.1 D2): push and list read and write the
    same ring, and nothing reaches `default`."""
    root = tmp_path
    _plain_shell(monkeypatch, root)
    _seed_active_session(root, "claude-abc-123")
    monkeypatch.setenv("RMX_SESSION", "claude-abc-123")

    r = CliRunner().invoke(main, ["task", "push", "refactor X"])
    assert r.exit_code == 0, r.output
    assert "depth=1" in r.output

    stm_d = root / ".refmatrix" / "stm"
    assert (stm_d / "claude-abc-123.tasks.json").exists()
    assert not (stm_d / "default.tasks.json").exists()

    r2 = CliRunner().invoke(main, ["task", "list"])
    assert r2.exit_code == 0, r2.output
    assert "refactor X" in r2.output


def test_push_then_pop_round_trip_same_session(tmp_path, monkeypatch):
    root = tmp_path
    _plain_shell(monkeypatch, root)
    _seed_active_session(root, "claude-xyz")
    # 21.1 D2: a write needs a resolved session; RMX_SESSION is the plain-shell way to give one.
    monkeypatch.setenv("RMX_SESSION", "claude-xyz")

    for desc in ("task-A", "task-B"):
        r = CliRunner().invoke(main, ["task", "push", desc])
        assert r.exit_code == 0, r.output
    tasks_file = root / ".refmatrix" / "stm" / "claude-xyz.tasks.json"
    assert len(json.loads(tasks_file.read_text())) == 2

    r = CliRunner().invoke(main, ["task", "pop"])
    assert r.exit_code == 0, r.output
    assert "task-B" in r.output  # popped the top
    assert len(json.loads(tasks_file.read_text())) == 1
