"""plan-2 hooks-reproducible (ch-bsd #bs-4, #sk-5).

The Claude Code hook config a project runs is PRODUCED by `rmx install-hooks`
and PROVEN by `rmx install-hooks --check`. Four hand-authored hooks lived only
in this repo's settings.local.json on 2026-09-14; a forced reinstall would have
deleted them, and the PreCompact save-state swallowed the bridge failure the
code was built to shout.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from refmatrix import hooks as hooks_mod
from refmatrix.hooks import _claude_hook_block, install


def _cmds(block, event=None):
    out = []
    for ev, entries in block["hooks"].items():
        if event and ev != event:
            continue
        for e in entries:
            for h in e.get("hooks", []):
                out.append((ev, e.get("matcher"), h["command"]))
    return out


MEMORY_PATH_MARKERS = ("memory recall", "ingest-gmd", "save-state", "focus summarize")


def _project(tmp_path, *, enforce_scripts=False):
    proj = tmp_path / "proj"
    (proj / ".refmatrix").mkdir(parents=True)
    if enforce_scripts:
        hd = proj / ".claude" / "hooks"
        hd.mkdir(parents=True)
        for n in ("enforce-test-to-file.sh", "enforce-rmx-grep.sh", "adr-gate.sh"):
            (hd / n).write_text("#!/bin/sh\nexit 0\n")
        (proj / ".claude" / "p20-0").mkdir()
        (proj / ".claude" / "p20-0" / "compile_guardrails.py").write_text("")
    return proj


# ---- 2.1 the production hooks are first-class generator options ----

def test_precompact_checkpoint_is_loud_and_no_sync(tmp_path):
    block = _claude_hook_block(tmp_path / ".refmatrix")
    pre = [c for _, _, c in _cmds(block, "PreCompact")]
    ss = [c for c in pre if "rmx save-state" in c]
    assert ss, "PreCompact must checkpoint via save-state"
    assert "--no-sync" in ss[0] and "--no-promote" in ss[0]
    assert ">/dev/null" not in ss[0] and "|| true" not in ss[0]
    off = _claude_hook_block(tmp_path / ".refmatrix", precompact_checkpoint=False)
    assert not [c for _, _, c in _cmds(off, "PreCompact") if "save-state" in c]


def test_stop_promotes_stm_loud(tmp_path):
    block = _claude_hook_block(tmp_path / ".refmatrix")
    stop = [c for _, _, c in _cmds(block, "Stop")]
    prom = [c for c in stop if "focus summarize --promote" in c]
    assert prom and "2>/dev/null" not in prom[0] and "|| true" not in prom[0]
    off = _claude_hook_block(tmp_path / ".refmatrix", stop_promote=False)
    assert not [c for _, _, c in _cmds(off, "Stop") if "focus summarize" in c]


def test_resume_focus_context_entry(tmp_path):
    block = _claude_hook_block(tmp_path / ".refmatrix")
    hits = [(m, c) for _, m, c in _cmds(block, "SessionStart") if "focus context --top 15" in c]
    assert hits and hits[0][0] == "resume"
    assert "2>/dev/null" not in hits[0][1]


def test_scan_prompt_composite_every(tmp_path):
    block = _claude_hook_block(tmp_path / ".refmatrix")
    scan = [c for _, _, c in _cmds(block, "UserPromptSubmit") if "scan-prompt" in c]
    assert scan and "--composite-every 3" in scan[0]
    none = _claude_hook_block(tmp_path / ".refmatrix", composite_every=None)
    assert "--composite-every" not in [c for _, _, c in _cmds(none, "UserPromptSubmit") if "scan-prompt" in c][0]


def test_bridge_catch_up_is_detached_and_loud(tmp_path):
    block = _claude_hook_block(tmp_path / ".refmatrix")
    bridge = [c for _, _, c in _cmds(block, "SessionStart") if "ingest-gmd --as-memory" in c]
    assert bridge, "SessionStart bridge catch-up missing"
    assert "--detach" in bridge[0]
    assert ">/dev/null" not in bridge[0] and "|| true" not in bridge[0]
    # and it is NOT buried in the sync/primer background group
    assert "rmx primer" not in bridge[0]


def test_enforce_entries_follow_scripts_on_disk(tmp_path):
    with_scripts = _project(tmp_path, enforce_scripts=True)
    block = _claude_hook_block(with_scripts / ".refmatrix", project_root=with_scripts)
    pre = [c for _, _, c in _cmds(block, "PreToolUse")]
    assert any("enforce-test-to-file.sh" in c for c in pre)
    assert any("enforce-rmx-grep.sh" in c for c in pre)
    assert any("adr-gate.sh" in c for _, _, c in _cmds(block, "PostToolUse"))
    assert any("compile_guardrails.py" in c for _, _, c in _cmds(block, "SessionStart"))
    bare = _project(tmp_path / "b")
    block2 = _claude_hook_block(bare / ".refmatrix", project_root=bare)
    # match the script paths, not bare substrings: pytest's tmp dir carries
    # this test's own name ("…test-enforce-entries…") inside the memdir path.
    leaked = [c for _, _, c in _cmds(block2)
              if ".claude/hooks/enforce-" in c or ".claude/hooks/adr-gate" in c
              or "compile_guardrails" in c]
    assert not leaked, leaked
    forced_off = _claude_hook_block(with_scripts / ".refmatrix", project_root=with_scripts, enforce=False)
    assert not any(".claude/hooks/enforce-" in c for _, _, c in _cmds(forced_off))


def test_no_memory_path_hook_is_silenced(tmp_path):
    """Everything between a memory file and the store shouts. Non-memory
    plumbing (sync flush, primer, focus events) may stay quiet."""
    block = _claude_hook_block(tmp_path / ".refmatrix")
    for ev, _, c in _cmds(block):
        if any(m in c for m in MEMORY_PATH_MARKERS):
            assert "2>/dev/null" not in c, f"{ev}: silenced memory path: {c}"
            assert "|| true" not in c, f"{ev}: swallowed exit on memory path: {c}"


# ---- 2.2 settings.json target, recorded flags, --check ----

def _apply(proj, **flags):
    return install(project_root=proj, refmatrix_root=proj / ".refmatrix",
                   git=False, claude=True, briefing=False, agent_env=False,
                   search=False, scope="project", apply=True, force=True, **flags)


def test_apply_writes_settings_json_and_records_flags(tmp_path):
    proj = _project(tmp_path)
    _apply(proj)
    settings = proj / ".claude" / "settings.json"
    assert settings.exists()
    assert not (proj / ".claude" / "settings.local.json").exists()
    rec = json.loads((proj / ".claude" / "rmx-hooks.json").read_text())
    assert rec["flags"]["memory_hooks"] is True and "version" in rec
    ok, diff = hooks_mod.check(proj)
    assert ok, diff


def test_check_detects_hand_edit(tmp_path):
    proj = _project(tmp_path)
    _apply(proj)
    settings = proj / ".claude" / "settings.json"
    d = json.loads(settings.read_text())
    ent = d["hooks"]["UserPromptSubmit"][0]["hooks"][0]
    ent["command"] = ent["command"] + " --composite-every 9"
    settings.write_text(json.dumps(d))
    ok, diff = hooks_mod.check(proj)
    assert not ok and "--composite-every 9" in diff


def test_check_reports_missing_generated_entry(tmp_path):
    proj = _project(tmp_path)
    _apply(proj)
    settings = proj / ".claude" / "settings.json"
    d = json.loads(settings.read_text())
    del d["hooks"]["PreCompact"]
    settings.write_text(json.dumps(d))
    ok, diff = hooks_mod.check(proj)
    assert not ok and "PreCompact" in diff


def test_force_keeps_foreign_hooks_and_other_keys(tmp_path):
    proj = _project(tmp_path)
    (proj / ".claude").mkdir(parents=True, exist_ok=True)
    settings = proj / ".claude" / "settings.json"
    settings.write_text(json.dumps({
        "statusLine": {"type": "command", "command": "x.sh"},
        "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo mine"}]}]},
    }))
    _apply(proj); _apply(proj)
    d = json.loads(settings.read_text())
    assert d["statusLine"]["command"] == "x.sh"
    cmds = [h["command"] for blks in d["hooks"].values() for b in blks for h in b["hooks"]]
    assert cmds.count("echo mine") == 1
    assert sum("focus hook --event say" in c for c in cmds) == 1


def test_apply_strips_rmx_hooks_from_legacy_local_file(tmp_path):
    """Pre-0.67 installs wrote settings.local.json; leaving that copy in place
    would fire every rmx hook twice."""
    proj = _project(tmp_path)
    (proj / ".claude").mkdir(parents=True, exist_ok=True)
    local = proj / ".claude" / "settings.local.json"
    local.write_text(json.dumps({
        "permissions": {"allow": ["Bash(ls:*)"]},
        "hooks": {"Stop": [{"hooks": [
            {"type": "command", "command": "export RMX_INVOCATION_SOURCE=hook; rmx focus hook --event say"},
            {"type": "command", "command": "echo keep-me"}]}]},
    }))
    _apply(proj)
    d = json.loads(local.read_text())
    assert d["permissions"]["allow"] == ["Bash(ls:*)"]
    cmds = [h["command"] for blks in d.get("hooks", {}).values() for b in blks for h in b["hooks"]]
    assert cmds == ["echo keep-me"]


def test_enforce_entries_are_rmx_managed(tmp_path):
    """The template's enforcement hooks count as rmx-managed so --force
    replaces them and --check covers them."""
    for c in ('[ -x "$CLAUDE_PROJECT_DIR/.claude/hooks/enforce-rmx-grep.sh" ] && ...',
              '"$CLAUDE_PROJECT_DIR/.claude/hooks/adr-gate.sh" 2>/dev/null || true',
              'python3 "$CLAUDE_PROJECT_DIR/.claude/p20-0/compile_guardrails.py"'):
        assert hooks_mod._is_rmx_hook(c)


# ---- CLI surface ----

def test_install_hooks_cli_check_exit_code(tmp_path, monkeypatch):
    from refmatrix import cli as cli_mod
    proj = _project(tmp_path)
    monkeypatch.setattr(cli_mod, "_root", lambda: proj / ".refmatrix")
    r = CliRunner().invoke(cli_mod.main, ["install-hooks", "--check"])
    assert r.exit_code == 1 and "rmx-hooks.json" in r.output
    r = CliRunner().invoke(cli_mod.main, ["install-hooks", "--no-git", "--no-briefing",
                                          "--no-agent-env", "--no-search", "--apply", "--force"])
    assert r.exit_code == 0, r.output
    r = CliRunner().invoke(cli_mod.main, ["install-hooks", "--check"])
    assert r.exit_code == 0, r.output


def test_install_hooks_cli_flags_reach_the_block(tmp_path, monkeypatch):
    from refmatrix import cli as cli_mod
    proj = _project(tmp_path)
    monkeypatch.setattr(cli_mod, "_root", lambda: proj / ".refmatrix")
    r = CliRunner().invoke(cli_mod.main, ["install-hooks", "--no-git", "--no-briefing",
                                          "--no-agent-env", "--no-search", "--no-memory-hooks",
                                          "--no-precompact-checkpoint", "--composite-every", "5",
                                          "--apply", "--force"])
    assert r.exit_code == 0, r.output
    d = json.loads((proj / ".claude" / "settings.json").read_text())
    rendered = json.dumps(d)
    assert "memory recall" not in rendered and "save-state" not in rendered
    assert "--composite-every 5" in rendered
    rec = json.loads((proj / ".claude" / "rmx-hooks.json").read_text())
    assert rec["flags"]["memory_hooks"] is False and rec["flags"]["composite_every"] == 5


def test_ingest_gmd_detach_without_daemon_fails_loud(tmp_path, monkeypatch):
    """The SessionStart bridge uses --detach so it returns immediately; with
    no daemon that must be an error line, not a 25 s foreground ingest."""
    from refmatrix import cli as cli_mod
    from refmatrix import daemon as daemon_mod
    memdir = tmp_path / "mem"; memdir.mkdir()
    (memdir / "m.md").write_text('---\ngmd: "0.1"\nid: m\ntitle: "m"\ntags: [x]\n---\n# m {#root}\n')
    monkeypatch.setattr(cli_mod, "_root", lambda: tmp_path / ".refmatrix")
    monkeypatch.setattr(daemon_mod, "ping", lambda root, **kw: False)
    r = CliRunner().invoke(cli_mod.main, ["ingest-gmd", "--as-memory", "--detach", str(memdir)])
    assert r.exit_code != 0
    assert "no daemon" in r.output.lower()
