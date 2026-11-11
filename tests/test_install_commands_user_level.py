"""The session-handoff commands install at USER level (2026-11-10, user).

`/save-state` and `/recall-state` used to be copied into every project's `.claude/commands/`,
so a fix to them had to reach each project copy by hand, and the copies drifted: the user wrote
new user-level versions that had lost the memory-dir rules the project copies carried (memory
before the bridge, `savestates/`, the one "newest" order). Now ONE packaged copy installs into
`~/.claude/commands/`; every other packaged command stays project-local.

A user-level file is shared by every project, so `rmx init` in one project must never clobber
it silently: a differing copy is kept unless `--force`, and `--force` backs it up first.
"""
from __future__ import annotations

from importlib import resources
from pathlib import Path

import pytest

from refmatrix import init_agents
from refmatrix.init_agents import install_commands

USER_LEVEL = ("save-state.md", "recall-state.md")
PROJECT_LEVEL = ("stash.md", "stash-list.md", "stash-pop.md", "detour.md", "return.md",
                 "commit-state.md")
# 26.3 AC-7's wording (tests/test_savestate_subfolder.py RECALL_SOURCE in that branch).
RECALL_SOURCE = "newest save-state (`savestates/`, legacy top-level)"


def _template(name: str) -> str:
    return (resources.files("refmatrix.templates.commands") / name).read_text(encoding="utf-8")


@pytest.fixture
def dirs(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    return proj, tmp_path / "home" / ".claude" / "commands", tmp_path / "backups"


def _install(dirs, force=False):
    proj, user, backup = dirs
    return install_commands(proj, force=force, user_dir=user, backup_dir=backup)


def test_handoff_commands_go_to_the_user_dir_and_nowhere_else(dirs):
    proj, user, _ = dirs
    _install(dirs)
    for name in USER_LEVEL:
        assert (user / name).read_text(encoding="utf-8") == _template(name), name
        assert not (proj / ".claude" / "commands" / name).exists(), name
    for name in PROJECT_LEVEL:
        assert (proj / ".claude" / "commands" / name).is_file(), name
        assert not (user / name).exists(), name


def test_the_default_user_dir_is_the_home_claude_commands_dir():
    assert init_agents.user_commands_dir() == Path.home() / ".claude" / "commands"


def test_the_default_backup_dir_is_under_the_refmatrix_user_home(monkeypatch, tmp_path):
    monkeypatch.setenv("RMX_HOME", str(tmp_path / "rmxhome"))
    assert init_agents.command_backup_dir() == tmp_path / "rmxhome" / "backups" / "commands"


def test_a_current_user_copy_is_reported_and_not_rewritten(dirs):
    _, user, backup = dirs
    user.mkdir(parents=True)
    target = user / "save-state.md"
    target.write_text(_template("save-state.md"), encoding="utf-8")
    before = target.stat().st_mtime_ns
    out = _install(dirs, force=True)
    assert target.stat().st_mtime_ns == before
    assert any(str(target) in line and "current" in line for line in out), out
    assert not backup.exists()


def test_a_differing_user_copy_is_kept_without_force(dirs):
    _, user, backup = dirs
    user.mkdir(parents=True)
    target = user / "recall-state.md"
    target.write_text("my own recall-state\n", encoding="utf-8")
    out = _install(dirs)
    assert target.read_text(encoding="utf-8") == "my own recall-state\n"
    line = next((ln for ln in out if str(target) in ln), "")
    assert "skip" in line and "--force" in line, out
    assert not backup.exists()


def test_force_backs_up_a_differing_user_copy_before_overwriting(dirs):
    _, user, backup = dirs
    user.mkdir(parents=True)
    target = user / "recall-state.md"
    target.write_text("my own recall-state\n", encoding="utf-8")
    out = _install(dirs, force=True)
    assert target.read_text(encoding="utf-8") == _template("recall-state.md")
    saved = [p for p in backup.iterdir() if p.name.startswith("recall-state.md")]
    assert len(saved) == 1, list(backup.iterdir())
    assert saved[0].read_text(encoding="utf-8") == "my own recall-state\n"
    assert any(str(saved[0]) in line for line in out), out


def test_a_failed_backup_leaves_the_user_copy_untouched(dirs):
    _, user, backup = dirs
    user.mkdir(parents=True)
    target = user / "save-state.md"
    target.write_text("mine\n", encoding="utf-8")
    backup.write_text("a file where the backup dir should be\n", encoding="utf-8")
    with pytest.raises(OSError):
        _install(dirs, force=True)
    assert target.read_text(encoding="utf-8") == "mine\n"


def test_a_project_local_copy_is_named_and_never_deleted(dirs):
    proj, _, _ = dirs
    local = proj / ".claude" / "commands" / "save-state.md"
    local.parent.mkdir(parents=True)
    local.write_text("old project copy\n", encoding="utf-8")
    out = _install(dirs, force=True)
    assert local.read_text(encoding="utf-8") == "old project copy\n"
    assert any(str(local) in line and "user-level" in line for line in out), out


def test_rmx_init_installs_the_pair_at_user_level(tmp_path, monkeypatch):
    """The production path (ch-bsd r1 #s-1): `rmx init` passes no user_dir, so the pair must
    land under the HOME it runs with and never in the project it initialises."""
    from click.testing import CliRunner

    from refmatrix.cli import main

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    proj = tmp_path / "proj"
    proj.mkdir()
    r = CliRunner().invoke(main, ["init", "--path", str(proj), "--no-hooks"])
    assert r.exit_code == 0, r.output
    for name in USER_LEVEL:
        assert (home / ".claude" / "commands" / name).read_text(encoding="utf-8") \
            == _template(name), name
        assert not (proj / ".claude" / "commands" / name).exists(), name
    assert (proj / ".claude" / "commands" / "stash.md").is_file()


# ---- the packaged text carries the memory-dir layout (ADR-0005) -------------------------------

def test_recall_state_names_the_savestates_source_and_the_one_shot():
    text = _template("recall-state.md")
    assert RECALL_SOURCE in text
    assert "rmx recall-state" in text
    assert "rmx ingest-gmd --as-memory" in text     # the bridge-lag fallback


def test_save_state_writes_memory_before_the_bridge_runs():
    text = _template("save-state.md")
    memory_step = text.index("Enduring memory")
    bridge_call = text.index("rmx save-state")
    assert memory_step < bridge_call, "memory must be written before save-state's bridge"


def test_save_state_states_the_layout_rules_and_the_commit_all_caveat():
    text = _template("save-state.md")
    for needle in ("savestates/", ".memory-layout", "rmx memory organise", "git add -A"):
        assert needle in text, needle


@pytest.mark.parametrize("name", USER_LEVEL)
def test_the_status_file_falls_back_to_an_existing_handoff_md(name):
    """ch-bsd r1 #s-3 (user decision 2026-11-10): refmatrix and 9 of 10 fleet projects keep
    `handoff.md` and no `workflow/STATUS.md`; a bare STATUS.md default made /save-state start a
    second session file in each. The chain is: CLAUDE.md's file, else handoff.md, else STATUS.md."""
    text = _template(name)
    start = text.index("**Status file**")
    line = text[start:text.index("**Agent brief dir**", start)]
    assert "CLAUDE.md" in line and "`handoff.md` if it exists" in line, line
    assert line.index("handoff.md") < line.index("workflow/STATUS.md"), line
