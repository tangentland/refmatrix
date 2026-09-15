"""plan-2 remediation (ch-bsd bsd-plan2-hooks-reproducible-03f46b8: #b-1, #b-2,
#s-4, #s-6, #m-7)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from refmatrix import hooks as hooks_mod
from refmatrix.hooks import _claude_hook_block, install
from tests.test_hooks_reproducible import _cmds, _project, _apply


def test_enforce_forced_on_emits_entries_without_scripts(tmp_path):
    proj = _project(tmp_path)                      # no .claude/hooks on disk
    block = _claude_hook_block(proj / ".refmatrix", project_root=proj, enforce=True)
    cmds = [c for _, _, c in _cmds(block)]
    assert any(".claude/hooks/enforce-test-to-file.sh" in c for c in cmds)
    assert any(".claude/hooks/enforce-rmx-grep.sh" in c for c in cmds)
    assert any(".claude/hooks/adr-gate.sh" in c for c in cmds)
    assert any("compile_guardrails.py" in c for c in cmds)


def test_force_keeps_a_same_prefix_foreign_hook(tmp_path):
    """#bs-4 one layer down: a user's `enforce-my-own-policy.sh` is NOT rmx's."""
    proj = _project(tmp_path)
    (proj / ".claude").mkdir(parents=True, exist_ok=True)
    settings = proj / ".claude" / "settings.json"
    mine = '[ -x "$CLAUDE_PROJECT_DIR/.claude/hooks/enforce-my-own-policy.sh" ] && "$CLAUDE_PROJECT_DIR/.claude/hooks/enforce-my-own-policy.sh" || true'
    settings.write_text(json.dumps({"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
        {"type": "command", "command": mine}]}]}}))
    _apply(proj); _apply(proj)
    assert "enforce-my-own-policy" in settings.read_text()
    assert not hooks_mod._is_rmx_hook(mine)


def test_check_detects_a_duplicated_managed_block(tmp_path):
    proj = _project(tmp_path); _apply(proj)
    settings = proj / ".claude" / "settings.json"
    d = json.loads(settings.read_text())
    d["hooks"]["Stop"].append(json.loads(json.dumps(d["hooks"]["Stop"][0])))
    settings.write_text(json.dumps(d))
    ok, diff = hooks_mod.check(proj)
    assert not ok and "duplicate" in diff.lower()


def test_check_detects_extra_key_drift(tmp_path):
    proj = _project(tmp_path); _apply(proj)
    settings = proj / ".claude" / "settings.json"
    d = json.loads(settings.read_text())
    d["hooks"]["Stop"][0]["hooks"][0]["timeout"] = 5
    settings.write_text(json.dumps(d))
    ok, diff = hooks_mod.check(proj)
    assert not ok and "timeout" in diff


def test_check_reports_unmanaged_entries_without_failing(tmp_path):
    proj = _project(tmp_path); _apply(proj)
    settings = proj / ".claude" / "settings.json"
    d = json.loads(settings.read_text())
    d["hooks"]["Stop"].append({"hooks": [{"type": "command", "command": "rmx context foo"}]})
    settings.write_text(json.dumps(d))
    ok, diff = hooks_mod.check(proj)
    assert ok is True
    assert "? Stop" in diff and "rmx context foo" in diff


def test_flags_recorded_without_claude(tmp_path):
    proj = _project(tmp_path)
    install(project_root=proj, refmatrix_root=proj / ".refmatrix", git=False, claude=False,
            briefing=False, agent_env=False, search=False, scope="project", apply=True, force=True)
    assert (proj / ".claude" / "rmx-hooks.json").exists()


def test_check_covers_the_search_scripts(tmp_path, monkeypatch):
    """The three ~/.claude/hooks scripts are the second author of runtime
    behaviour; a modified one is drift."""
    from refmatrix import search_hooks
    hd = tmp_path / "userhooks"
    monkeypatch.setattr(search_hooks, "hooks_dir", lambda: hd)
    proj = _project(tmp_path)
    install(project_root=proj, refmatrix_root=proj / ".refmatrix", git=False, claude=True,
            briefing=False, agent_env=False, search=True, scope="project", apply=True, force=True)
    ok, diff = hooks_mod.check(proj)
    assert ok, diff
    (hd / search_hooks.GUARD_NAME).write_text("#!/bin/sh\nexit 0\n")
    ok, diff = hooks_mod.check(proj)
    assert not ok and search_hooks.GUARD_NAME in diff


def test_focus_summarize_promote_refuses_without_daemon(tmp_path, monkeypatch):
    """Stop runs `focus summarize --promote` every turn; with the daemon down
    it must refuse loudly, not open the active slot from a CLI process."""
    from refmatrix import cli as cli_mod
    from refmatrix import daemon as daemon_mod
    from refmatrix import stm as stm_mod
    root = tmp_path / ".refmatrix"; root.mkdir()
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    monkeypatch.setenv("RMX_SESSION", "s1")
    stm_mod.Stm(root, "s1").record("input", "hi")
    monkeypatch.setattr(daemon_mod, "ping", lambda r, **kw: False)
    r = CliRunner().invoke(cli_mod.main, ["focus", "summarize", "--promote"])
    assert r.exit_code != 0
    assert "daemon" in r.output.lower()


# ---- round 2 (bsd-plan2-r2) ----

def test_stop_promote_is_bounded_and_fails_loud_when_busy(tmp_path, monkeypatch):
    """Live: the Stop hook's `focus summarize --promote` took 55 s / 15 s / 6 s
    while the daemon was busy with a bridge + sync (Q4 assumed 0.13 s). The
    hook path is bounded; a timeout is a loud skip, not a wait."""
    from refmatrix import cli as cli_mod
    from refmatrix import daemon as daemon_mod
    from refmatrix import stm as stm_mod
    root = tmp_path / ".refmatrix"; root.mkdir()
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    monkeypatch.setenv("RMX_SESSION", "s1")
    stm_mod.Stm(root, "s1").record("input", "hi")
    monkeypatch.setattr(daemon_mod, "ping", lambda r, **kw: True)
    def slow_call(root, op, args=None, timeout=60.0, **kw):
        raise TimeoutError(f"no answer in {timeout}s")
    monkeypatch.setattr(daemon_mod, "call", slow_call)
    r = CliRunner().invoke(cli_mod.main, ["focus", "summarize", "--promote", "--timeout", "0.5"])
    assert r.exit_code != 0
    assert "busy" in r.output.lower() and "skipped" in r.output.lower()
    # the generator passes the bound on the Stop hook
    block = _claude_hook_block(tmp_path / ".refmatrix")
    stop = [c for _, _, c in _cmds(block, "Stop") if "focus summarize --promote" in c][0]
    assert "--timeout" in stop


def test_promote_refusal_names_a_real_flag(tmp_path, monkeypatch):
    from refmatrix import cli as cli_mod
    from refmatrix import daemon as daemon_mod
    from refmatrix import stm as stm_mod
    root = tmp_path / ".refmatrix"; root.mkdir()
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    monkeypatch.setenv("RMX_SESSION", "s1")
    stm_mod.Stm(root, "s1").record("input", "hi")
    monkeypatch.setattr(daemon_mod, "ping", lambda r, **kw: False)
    r = CliRunner().invoke(cli_mod.main, ["focus", "summarize", "--promote"])
    assert r.exit_code != 0 and "--no-promote" not in r.output


def test_no_claude_apply_then_check_is_clean(tmp_path):
    proj = _project(tmp_path)
    install(project_root=proj, refmatrix_root=proj / ".refmatrix", git=False, claude=False,
            briefing=False, agent_env=False, search=False, scope="project", apply=True, force=True)
    rec = json.loads((proj / ".claude" / "rmx-hooks.json").read_text())
    assert rec["flags"]["claude"] is False
    ok, diff = hooks_mod.check(proj)
    assert ok, diff


def test_detach_busy_branch_waits_wall_clock_and_names_the_pid(tmp_path, monkeypatch):
    import time
    from refmatrix import cli as cli_mod
    from refmatrix import daemon as daemon_mod
    memdir = tmp_path / "mem"; memdir.mkdir()
    (memdir / "m.md").write_text('---\ngmd: "0.1"\nid: m\ntitle: "m"\ntags: [x]\n---\n# m {#root}\n')
    monkeypatch.setattr(cli_mod, "_root", lambda: tmp_path / ".refmatrix")
    monkeypatch.setattr(daemon_mod, "ping", lambda root, **kw: False)
    monkeypatch.setattr("refmatrix.discovery.daemon_status", lambda root: {"up": False, "busy": True, "pid": 77})
    monkeypatch.setenv("RMX_DETACH_WAIT_S", "1")
    t0 = time.monotonic()
    r = CliRunner().invoke(cli_mod.main, ["ingest-gmd", "--as-memory", "--detach", str(memdir)])
    elapsed = time.monotonic() - t0
    assert r.exit_code != 0
    assert "busy pid=77" in r.output
    assert elapsed < 2.5, f"waited {elapsed:.1f}s for a 1s budget"


def test_intuition_doc_describes_the_shipped_stop_hook():
    text = (Path(__file__).resolve().parents[1] / "docs" / "hooks" / "intuition-style-hooks.md").read_text()
    assert "Phase C4" not in text and "out of scope" not in text
    assert "focus summarize --promote" in text
