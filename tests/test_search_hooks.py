"""Vendored Claude search hooks: rendering, installation, and the rewriter's
dodge coverage (bare / absolute-path / command / env launches; ugrep and
quoted strings untouched)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from refmatrix import search_hooks as sh


@pytest.fixture
def env_hooks(tmp_path, monkeypatch):
    d = tmp_path / "hooks"
    monkeypatch.setenv("RMX_CLAUDE_HOOKS_DIR", str(d))
    return d


def test_render_bakes_absolute_paths(env_hooks):
    scripts = sh.render_scripts()
    assert "@RMXGREP@" not in scripts[sh.REWRITER_NAME]
    assert "@REWRITER@" not in scripts[sh.GUARD_NAME]
    assert str(env_hooks / sh.REWRITER_NAME) in scripts[sh.GUARD_NAME]
    for tok in ("rmxgrep", "rmxrg"):
        assert tok in scripts[sh.REWRITER_NAME]


def test_install_writes_scripts_and_settings(env_hooks, tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    out = sh.install_search_hooks(proj, scope="project", apply=True, force=False)
    assert any("write" in ln for ln in out)
    for name in (sh.GUARD_NAME, sh.REWRITER_NAME, sh.TEACH_NAME):
        f = env_hooks / name
        assert f.exists() and f.stat().st_mode & 0o111
    cfg = json.loads((proj / ".claude" / "settings.json").read_text())
    cmds = [h["command"] for evs in cfg["hooks"].values()
            for e in evs for h in e["hooks"]]
    assert str(env_hooks / sh.GUARD_NAME) in cmds
    assert str(env_hooks / sh.TEACH_NAME) in cmds


def test_reinstall_is_idempotent(env_hooks, tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    sh.install_search_hooks(proj, scope="project", apply=True, force=False)
    sh.install_search_hooks(proj, scope="project", apply=True, force=False)
    cfg = json.loads((proj / ".claude" / "settings.json").read_text())
    cmds = [h["command"] for evs in cfg["hooks"].values()
            for e in evs for h in e["hooks"]]
    assert len(cmds) == len(set(cmds)) == 2


def test_user_scope_prints_snippet_only(env_hooks, tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    out = sh.install_search_hooks(proj, scope="user", apply=True, force=False)
    assert not (proj / ".claude" / "settings.json").exists()
    assert any("settings.json" in ln for ln in out)


def _rewrite(env_hooks, cmd: str) -> str:
    """Run the RENDERED rewriter on a command; '' = no rewrite."""
    script = env_hooks / sh.REWRITER_NAME
    if not script.exists():
        sh.install_search_hooks(env_hooks.parent, scope="user",
                                apply=True, force=False)
    payload = json.dumps({"tool_input": {"command": cmd}})
    r = subprocess.run([sys.executable, str(script)], input=payload,
                       capture_output=True, text=True)
    return r.stdout


@pytest.mark.parametrize("cmd,expect_tool", [
    ("grep -rn pat src/", "rmxgrep"),
    ("/usr/bin/grep -n foo bar.py", "rmxgrep"),
    ("lint | /opt/local/bin/rg -c error", "rmxrg"),
    ("command grep -c error f.txt", "rmxgrep"),
    ("command -p grep foo", "rmxgrep"),
    ("env HF_HUB_OFFLINE=1 grep -n pat f.py", "rmxgrep"),
    ("env A=1 B=2 rg TODO", "rmxrg"),
    ("command /usr/bin/grep -n foo", "rmxgrep"),
])
def test_rewriter_catches_dodges(env_hooks, cmd, expect_tool):
    out = _rewrite(env_hooks, cmd)
    assert expect_tool in out, (cmd, out)
    assert "/usr/bin/grep" not in out and "/opt/local/bin/rg" not in out


@pytest.mark.parametrize("cmd", [
    "command -v grep",
    "ugrep -n foo bar",
    "/usr/local/bin/ugrep -n foo bar",
    'echo "/usr/bin/grep in a string"',
    "cat <<EOF\ngrep inside heredoc\nEOF",
])
def test_rewriter_leaves_non_searches_alone(env_hooks, cmd):
    assert _rewrite(env_hooks, cmd) == ""


def test_env_assignments_survive_in_place(env_hooks):
    out = _rewrite(env_hooks, "env HF_HUB_OFFLINE=1 grep -n pat f.py")
    assert out.startswith("env HF_HUB_OFFLINE=1 ")
