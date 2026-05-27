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
    assert "rmx memory recall --session-start" in cmds["SessionStart"]
    assert "rmx memory recall --prompt" in cmds["UserPromptSubmit"]
    assert "PreCompact" in block["hooks"]
    assert "--recent --since 1h" in cmds["PreCompact"]


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
    assert "rmx memory recall --prompt" in rendered
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
