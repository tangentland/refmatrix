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


# ── task 6.5 / bug-008: the user-global rewriter must not name a tree ──────

def test_rewriter_bakes_no_tree_path(env_hooks):
    """`~/.claude/hooks/rmxgrep-rewrite.py` is USER-GLOBAL and was rendered
    with `RMXGREP = "<generator tree>/bin/rmxgrep"`. Any `install-hooks
    --apply` from the dev venv — a test without the `RMX_CLAUDE_HOOKS_DIR`
    redirect, an audit probe in a throwaway project — overwrote the live hook
    with dev-tree paths. Seen twice (bug-008, recurring).

    The script must resolve its wrappers at RUNTIME instead, so the bytes are
    identical whichever tree renders them."""
    body = sh.render_scripts()[sh.REWRITER_NAME]
    assert "/refmatrix/bin/" not in body, (
        "the user-global rewriter names a refmatrix tree")
    # No absolute path into ANY checkout of this package, dev or deploy.
    for tree in (Path(sh.__file__).resolve().parents[2], Path.home() / "refmatrix"):
        assert str(tree) not in body, f"rewriter bakes {tree}"


def test_rewriter_renders_identically_from_any_tree(env_hooks, monkeypatch):
    """The property that makes bug-008 impossible rather than merely caught:
    two different generating trees produce the same bytes."""
    monkeypatch.setattr(sh, "wrapper_paths",
                        lambda: ("/dev/tree/bin/rmxgrep", "/dev/tree/bin/rmxrg"))
    a = sh.render_scripts()[sh.REWRITER_NAME]
    monkeypatch.setattr(sh, "wrapper_paths",
                        lambda: ("/deploy/bin/rmxgrep", "/deploy/bin/rmxrg"))
    b = sh.render_scripts()[sh.REWRITER_NAME]
    assert a == b, "the rendered rewriter still depends on the generating tree"


def test_rewriter_resolves_its_wrappers_at_runtime(env_hooks, tmp_path):
    """Resolution moved into the script, so prove the script still finds the
    wrappers — a rewriter that resolves to nothing is worse than one that
    bakes a path."""
    body = sh.render_scripts()[sh.REWRITER_NAME]
    script = tmp_path / "rw.py"
    script.write_text(body)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    for n in ("rmx", "rmxgrep", "rmxrg"):
        (fake_bin / n).write_text("#!/bin/sh\nexit 0\n")
        (fake_bin / n).chmod(0o755)
    r = subprocess.run(
        [sys.executable, "-c",
         f"import runpy,sys;sys.argv=['rw'];m=runpy.run_path({str(script)!r});"
         "print(m['RMXGREP'](), m['RMXRG']())"],
        capture_output=True, text=True,
        env={"PATH": f"{fake_bin}:/usr/bin:/bin", "HOME": str(tmp_path)})
    assert r.returncode == 0, r.stderr
    assert str(fake_bin / "rmxgrep") in r.stdout, r.stdout
    assert str(fake_bin / "rmxrg") in r.stdout, r.stdout


def test_install_refuses_user_global_dir_from_a_foreign_tree(
        tmp_path, monkeypatch):
    """The second half of the guard: even with runtime resolution, a foreign
    tree must not overwrite the user-global scripts. `RMX_CLAUDE_HOOKS_DIR`
    is the stated escape, so tests and probes keep working."""
    from refmatrix import upgrade
    monkeypatch.delenv("RMX_CLAUDE_HOOKS_DIR", raising=False)
    monkeypatch.setattr(sh, "hooks_dir", lambda: tmp_path / "userhooks")
    monkeypatch.setattr(upgrade, "runtime_identity",
                        lambda: {"venv_tree": "/dev/tree"})
    monkeypatch.setattr(sh, "path_rmx_tree", lambda: "/deploy")

    with pytest.raises(RuntimeError) as e:
        sh.install_search_hooks(tmp_path, "project", apply=True, force=True)
    msg = str(e.value)
    assert "/dev/tree" in msg and "/deploy" in msg, msg
    assert "RMX_CLAUDE_HOOKS_DIR" in msg, msg
    assert not (tmp_path / "userhooks").exists(), "a refused install wrote scripts"


def test_install_allows_the_owning_tree(tmp_path, monkeypatch):
    from refmatrix import upgrade
    monkeypatch.delenv("RMX_CLAUDE_HOOKS_DIR", raising=False)
    monkeypatch.setattr(sh, "hooks_dir", lambda: tmp_path / "userhooks")
    monkeypatch.setattr(upgrade, "runtime_identity",
                        lambda: {"venv_tree": "/deploy"})
    monkeypatch.setattr(sh, "path_rmx_tree", lambda: "/deploy")
    sh.install_search_hooks(tmp_path, "project", apply=True, force=True)
    assert (tmp_path / "userhooks" / sh.REWRITER_NAME).exists()


def test_install_allows_a_redirected_hooks_dir_from_any_tree(
        tmp_path, monkeypatch):
    """The escape must actually work, or every test in this file breaks."""
    from refmatrix import upgrade
    monkeypatch.setenv("RMX_CLAUDE_HOOKS_DIR", str(tmp_path / "redirected"))
    monkeypatch.setattr(upgrade, "runtime_identity",
                        lambda: {"venv_tree": "/dev/tree"})
    monkeypatch.setattr(sh, "path_rmx_tree", lambda: "/deploy")
    sh.install_search_hooks(tmp_path, "project", apply=True, force=True)
    assert (tmp_path / "redirected" / sh.REWRITER_NAME).exists()
