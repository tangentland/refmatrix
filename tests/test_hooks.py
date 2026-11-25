"""Hook installer tests. Focused on the ADR-0001 Phase C3 addition —
SessionStart/UserPromptSubmit/PreCompact memory hooks land in
.claude/settings.json when `rmx init` runs with default flags,
and stay out when `--no-memory-hooks` is passed."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

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
    # The memory bridge catch-up is a loud, detached SessionStart entry:
    # memory files written outside `rmx save-state` still reach the store.
    # It targets the project's curated-memory dir, as memory.
    assert "rmx ingest-gmd --as-memory --detach '" in cmds["SessionStart"]
    assert "/.claude/projects/" in cmds["SessionStart"]
    assert "/memory'" in cmds["SessionStart"]
    # UserPromptSubmit reads the prompt from stdin (Claude Code's hook
    # envelope), not from an env var -- the old `--prompt $ENV` pattern
    # was broken because the env var doesn't exist in the hook context.
    assert "rmx memory recall --stdin-json" in cmds["UserPromptSubmit"]
    assert "PreCompact" in block["hooks"]
    # task-compaction-as-handoff R1/R2 (L195, 2026-11-24): PreCompact saves state and prints
    # only the one-line summary instruction; the `--recent` recall left it (its pack would
    # become summary instructions too).
    assert "rmx save-state" in cmds["PreCompact"]
    assert "memory recall" not in cmds["PreCompact"]
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
        assert "ingest-gmd --as-memory" not in cmds


def test_install_writes_memory_hooks_into_settings(tmp_path):
    """Default-flag install drops the memory hook commands into
    .claude/settings.json."""
    project = tmp_path / "proj"
    rmx_root = project / ".refmatrix"
    project.mkdir()
    rmx_root.mkdir()
    install(project_root=project, refmatrix_root=rmx_root,
            git=False, claude=True, briefing=False, scope="project",
            apply=True, force=True, memory_hooks=True)
    settings = json.loads((project / ".claude" / "settings.json").read_text())
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
    settings = json.loads((project / ".claude" / "settings.json").read_text())
    rendered = json.dumps(settings)
    assert "rmx memory recall" not in rendered
    assert "PreCompact" not in settings.get("hooks", {})


def test_force_reinstall_overwrites_not_duplicates(tmp_path):
    """`--force` re-install must replace rmx hooks, not append duplicates,
    while preserving user-authored hooks."""
    from refmatrix.hooks import _install_claude_hooks
    proj = tmp_path / "proj"
    (proj / ".claude").mkdir(parents=True)
    settings = proj / ".claude" / "settings.json"
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
    # Exact-match the event name: `--event tool` is a PREFIX of `--event
    # tool-pre`, so a bare substring count conflates the two hooks.
    def _n(event):
        return sum(f"rmx focus hook --event {event} " in c for c in all_cmds)

    assert _n("tool") == 1
    assert _n("tool-pre") == 1, "PreToolUse focus capture missing"
    # user hook survived
    assert "echo my-own-hook" in all_cmds


def test_install_commands_writes_stash_slash_commands(tmp_path):
    from refmatrix.init_agents import install_commands
    out = install_commands(tmp_path, force=True, user_dir=tmp_path / "user-commands",
                           backup_dir=tmp_path / "backups")
    cmds_dir = tmp_path / ".claude" / "commands"
    names = {p.name for p in cmds_dir.glob("*.md")}
    assert {"stash.md", "stash-list.md", "stash-pop.md",
            "detour.md", "return.md", "commit-state.md"} <= names
    # 2026-11-10: the handoff pair is user-level, never a project copy
    assert not {"save-state.md", "recall-state.md"} & names
    # the stash command pairs git + focus
    body = (cmds_dir / "stash.md").read_text()
    assert "git stash push" in body and "rmx task push" in body


# ---- H1.a AC-1: the packaged agents and commands are project-neutral (bug-319) ------------
#
# `rmx init` ships these files into every project and, for /save-state and /recall-state, into
# ~/.claude/commands/ for every project at once. A path or a name from this one workstation in
# them is an instruction that is wrong everywhere else: at 8c4c9eb3 commit-state.md and
# save-state.md told any project to fast-forward `~/refmatrix`, and gmd-curator.md linted with
# `~/claude_tools/gmd/lint.py` (task-H1.a-reconcile-shipped-files, AC-1).

# One workstation's paths and names. `/Users/` and `/Volumes/` catch any absolute home or volume
# path; the rest are the forms this repo's own text uses.
_PROJECT_SPECIFIC = ("~/claude_tools", "~/refmatrix", ".venv-eval", "/Users/", "/Volumes/",
                     "tholley", "Todd Holley")


def _packaged_markdown() -> "list[tuple[str, str]]":
    """(package-relative name, text) for every agent and command `rmx init` installs."""
    from importlib import resources
    from refmatrix.init_agents import COMMANDS_PKG, TEMPLATE_PKG
    out = []
    for pkg in (TEMPLATE_PKG, COMMANDS_PKG):
        for p in sorted(resources.files(pkg).iterdir(), key=lambda q: q.name):
            if p.is_file() and p.name.endswith(".md"):
                out.append((f"{pkg.rsplit('.', 1)[1]}/{p.name}", p.read_text(encoding="utf-8")))
    return out


def project_specifics(name: str, text: str) -> "list[str]":
    """`name:line: pattern` for every line of `text` that carries a project-specific form."""
    return [f"{name}:{i}: {pat}" for i, line in enumerate(text.splitlines(), 1)
            for pat in _PROJECT_SPECIFIC if pat in line]


def test_packaged_templates_hold_no_project_specifics():
    files = _packaged_markdown()
    names = {n for n, _ in files}
    # the nine files both installers ship (H1.a); an empty package would pass vacuously
    assert {"agents/gmd-curator.md", "commands/save-state.md", "commands/recall-state.md",
            "commands/commit-state.md", "commands/detour.md", "commands/return.md",
            "commands/stash.md", "commands/stash-list.md", "commands/stash-pop.md"} <= names
    hits = [h for n, t in files for h in project_specifics(n, t)]
    assert not hits, ("packaged agent/command text names one workstation; write it neutrally "
                      "or move it to the project's overlay:\n" + "\n".join(hits))


@pytest.mark.parametrize("pattern", _PROJECT_SPECIFIC)
def test_project_specifics_guard_fails_on_a_planted_line(pattern):
    """AC-1's must-fail case: one planted line in a packaged file's real text is reported, for
    every form the guard claims to check."""
    name, text = _packaged_markdown()[0]
    planted = text + f"\nDeploy: see {pattern}/somewhere.\n"
    n = len(planted.splitlines())
    on_planted_line = [h for h in project_specifics(name, planted)
                       if h.startswith(f"{name}:{n}: ")]
    assert on_planted_line == [f"{name}:{n}: {pattern}"]
