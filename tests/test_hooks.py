"""Hook installer tests. Focused on the ADR-0001 Phase C3 addition —
SessionStart/UserPromptSubmit/PreCompact memory hooks land in
.claude/settings.local.json when `rmx init` runs with default flags,
and stay out when `--no-memory-hooks` is passed."""
from __future__ import annotations

import json
from pathlib import Path

from refmatrix.hooks import _claude_hook_block, install


def test_memory_hooks_default_on(tmp_path):
    block = _claude_hook_block(tmp_path / ".refmatrix")
    cmds = {
        ev: " ".join(
            h.get("command", "")
            for entry in entries for h in entry.get("hooks", [])
        )
        for ev, entries in block["hooks"].items()
    }
    # Memory commands explicitly route to the intuition partition;
    # the bound daemon partition shouldn't determine where recall
    # looks.
    assert "rmx memory recall --session-start" in cmds["SessionStart"]
    # UserPromptSubmit reads the prompt from stdin (Claude Code's hook
    # envelope), not from an env var -- the old `--prompt $ENV` pattern
    # was broken because the env var doesn't exist in the hook context.
    assert "rmx memory recall --stdin-json" in cmds["UserPromptSubmit"]
    assert "PreCompact" in block["hooks"]
    assert "--recent --since 1h" in cmds["PreCompact"]
    # Memory hooks must NOT silently swallow errors -- per-project
    # convention is to surface failures so a broken store can't quietly
    # rot. Check only the memory-recall commands (the file-sync SessionStart
    # hook above intentionally uses 2>/dev/null on rmx sync because the
    # sync queue is best-effort by design).
    memory_cmds = []
    for ev in ("SessionStart", "UserPromptSubmit", "PreCompact"):
        for entry in block["hooks"].get(ev, []):
            for h in entry.get("hooks", []):
                cmd = h.get("command", "")
                if "memory recall" in cmd:
                    memory_cmds.append(cmd)
    assert memory_cmds, "no memory hooks emitted"
    for cmd in memory_cmds:
        assert "2>/dev/null" not in cmd, f"memory hook masks stderr: {cmd}"
        assert "|| true" not in cmd, f"memory hook suppresses exit: {cmd}"


def test_memory_hooks_opt_out(tmp_path):
    block = _claude_hook_block(tmp_path / ".refmatrix", memory_hooks=False)
    assert "PreCompact" not in block["hooks"]
    # SessionStart + UserPromptSubmit still exist for the file-sync side,
    # but must not reference the memory CLI.
    for ev in ("SessionStart", "UserPromptSubmit"):
        cmds = " ".join(
            h.get("command", "")
            for entry in block["hooks"].get(ev, [])
            for h in entry.get("hooks", [])
        )
        assert "rmx memory recall" not in cmds


def test_install_writes_memory_hooks_into_settings(tmp_path):
    """Default-flag install drops the memory hook commands into
    .claude/settings.local.json."""
    project = tmp_path / "proj"
    rmx_root = project / ".refmatrix"
    project.mkdir()
    rmx_root.mkdir()
    install(project_root=project, refmatrix_root=rmx_root,
            git=False, claude=True, briefing=False, scope="project",
            apply=True, force=True, memory_hooks=True)
    settings = json.loads((project / ".claude" / "settings.local.json").read_text())
    rendered = json.dumps(settings)
    assert "rmx memory recall --session-start" in rendered
    assert "rmx memory recall --stdin-json" in rendered
    assert "PreCompact" in settings["hooks"]


def test_install_respects_no_memory_hooks(tmp_path):
    project = tmp_path / "proj"
    rmx_root = project / ".refmatrix"
    project.mkdir()
    rmx_root.mkdir()
    install(project_root=project, refmatrix_root=rmx_root,
            git=False, claude=True, briefing=False, scope="project",
            apply=True, force=True, memory_hooks=False)
    settings = json.loads((project / ".claude" / "settings.local.json").read_text())
    rendered = json.dumps(settings)
    assert "rmx memory recall" not in rendered
    assert "PreCompact" not in settings.get("hooks", {})


def test_force_reinstall_overwrites_not_duplicates(tmp_path):
    """`--force` re-install must replace rmx hooks, not append duplicates,
    while preserving user-authored hooks."""
    from refmatrix.hooks import _install_claude_hooks
    proj = tmp_path / "proj"
    (proj / ".claude").mkdir(parents=True)
    settings = proj / ".claude" / "settings.local.json"
    # Seed a user hook that rmx must never touch.
    user_hook = {"type": "command", "command": "echo my-own-hook"}
    settings.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [user_hook]}]}}))

    rroot = proj / ".refmatrix"
    for _ in range(2):  # install twice with force
        _install_claude_hooks(proj, rroot, "project", apply=True, force=True)

    data = json.loads(settings.read_text())
    all_cmds = [h["command"] for blks in data["hooks"].values()
                for blk in blks for h in blk.get("hooks", [])]
    # rmx say-hook present exactly once despite two force installs
    assert sum("focus hook --event say" in c for c in all_cmds) == 1
    assert sum("rmx focus hook --event tool" in c for c in all_cmds) == 1
    # user hook survived
    assert "echo my-own-hook" in all_cmds
