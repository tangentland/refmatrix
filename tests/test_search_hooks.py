"""Vendored Claude search hooks: rendering, installation, and the rewriter's
dodge coverage (bare / absolute-path / command / env launches; ugrep and
quoted strings untouched)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
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
    """Run the RENDERED rewriter on a command; '' = no rewrite.

    bug-168 (T0.2 R2.2, ruling L142 (5), 2026-11-15): the rewriter stands down when learning is
    off, and decides that from `RMX_LEARN`, else a `.refmatrix/learn.off` in any ancestor of the
    cwd, else `~/.refmatrix/learn.off` -- files outside this test's tmp root (the user's has
    existed since 2026-10-15, so in the main tree every rewrite came back ''). `RMX_LEARN=on`
    wins over both markers, so the result depends on the rewriting alone. The stand-down itself
    is tested by `test_bug168_the_rewriter_stands_down_under_a_planted_learn_off`."""
    script = env_hooks / sh.REWRITER_NAME
    if not script.exists():
        sh.install_search_hooks(env_hooks.parent, scope="user",
                                apply=True, force=False)
    payload = json.dumps({"tool_input": {"command": cmd}})
    r = subprocess.run([sys.executable, str(script)], input=payload,
                       capture_output=True, text=True, env=dict(os.environ, RMX_LEARN="on"))
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


# ── bug-168: the rewriter tests measure rewriting, not the ambient learn switch ─────
#
# task-t0-suite-trust-sweep `#t0-2` R2.2 / AC-2.2. The rendered rewriter's `_learning_off(cwd)`
# walks UP from the cwd for `.refmatrix/learn.off`, then reads `~/.refmatrix/learn.off`. The dev
# tree lives under the real `$HOME`, whose `~/.refmatrix/learn.off` has existed since 2026-10-15,
# so in the main tree every `_rewrite()` came back '' and 9 tests failed
# (`AssertionError: ('grep -rn pat src/', '')`); littlebig clones have no `$HOME` ancestor and
# passed 24/24, which is why no release saw it. `_rewrite()` must depend on no file outside the
# test's tmp root; the stand-down itself stays tested, on a marker the test plants.


def _planted_learn_off() -> Path:
    """A tmp tree OUTSIDE the test's tmp root whose `.refmatrix/learn.off` is an ancestor
    marker of `<it>/a/b`, the way the user's `~/.refmatrix/learn.off` is for the dev tree."""
    base = Path(tempfile.mkdtemp(prefix="b168-", dir=os.environ["RMX_SANDBOX_ROOT"])).resolve()
    (base / ".refmatrix").mkdir()
    (base / ".refmatrix" / "learn.off").write_text("")
    (base / "a" / "b").mkdir(parents=True)
    return base


def test_bug168_rewriting_does_not_depend_on_the_cwds_ancestry(env_hooks, monkeypatch):
    """AC-2.2 in any checkout: run from a cwd whose ancestor holds `.refmatrix/learn.off` (the
    main tree's condition), `_rewrite()` still rewrites. At c4b44d0 it returns ''."""
    base = _planted_learn_off()
    try:
        monkeypatch.chdir(base / "a" / "b")
        out = _rewrite(env_hooks, "grep -rn pat src/")
        assert "rmxgrep" in out, ("grep -rn pat src/", out)
    finally:
        shutil.rmtree(base)


def test_bug168_rewriting_does_not_depend_on_the_homes_learn_switch(env_hooks, monkeypatch,
                                                                     tmp_path):
    """R2.2: `~/.refmatrix/learn.off` is a file outside the test's tmp root too (the sandbox
    home is shared by every test in the session; one `rmx learn off` there would stand down
    every rewriter test after it). `_rewrite()` still rewrites."""
    _rewrite(env_hooks, "true")                     # render the script under the sandbox home
    home = tmp_path / "home"
    (home / ".refmatrix").mkdir(parents=True)
    (home / ".refmatrix" / "learn.off").write_text("")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(tmp_path)
    out = _rewrite(env_hooks, "grep -rn pat src/")
    assert "rmxgrep" in out, ("grep -rn pat src/", out)


def _run_rendered_rewriter(env_hooks, cmd: str, cwd: Path) -> str:
    """The rendered rewriter as Claude Code runs it: the hook payload carries the cwd, the
    process runs there, and no `RMX_LEARN` decides for it."""
    _rewrite(env_hooks, "true")                     # render the script
    env = {k: v for k, v in os.environ.items() if k != "RMX_LEARN"}
    payload = json.dumps({"tool_input": {"command": cmd}, "cwd": str(cwd)})
    r = subprocess.run([sys.executable, str(env_hooks / sh.REWRITER_NAME)], input=payload,
                       capture_output=True, text=True, cwd=str(cwd), env=env, timeout=60)
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_bug168_the_rewriter_stands_down_under_a_planted_learn_off(env_hooks):
    """R2.2: the stand-down stays tested. With `learn.off` planted in an ancestor of a tmp cwd,
    the rendered rewriter emits nothing; with the marker removed, the same call rewrites (so
    the '' is the stand-down, not a broken script). Mutation M2.1 (the rewriter ignores
    `learn.off`) turns this red."""
    base = _planted_learn_off()
    try:
        cwd = base / "a" / "b"
        assert _run_rendered_rewriter(env_hooks, "grep -rn pat src/", cwd) == "", (
            "the rewriter rewrote under a planted .refmatrix/learn.off in an ancestor")
        (base / ".refmatrix" / "learn.off").unlink()
        assert "rmxgrep" in _run_rendered_rewriter(env_hooks, "grep -rn pat src/", cwd), (
            "control: with the marker gone the rewriter must rewrite")
    finally:
        shutil.rmtree(base)


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


def test_rewriter_renders_identically_from_any_tree(env_hooks, monkeypatch, tmp_path):
    """The property that makes bug-008 impossible rather than merely caught:
    two different generating environments produce the same bytes. The
    environment is varied for real (a different `rmxgrep`/`rmxrg` first on
    PATH), not by patching a resolver, so the test outlives the removal of
    the wrapper plumbing (T0.4 R4.3)."""
    renders = []
    for tree in ("dev-tree", "deploy-tree"):
        b = tmp_path / tree / "bin"
        b.mkdir(parents=True)
        for n in ("rmxgrep", "rmxrg"):
            (b / n).write_text("#!/bin/sh\nexit 0\n")
            (b / n).chmod(0o755)
        monkeypatch.setenv("PATH", f"{b}:/usr/bin:/bin")
        renders.append(sh.render_scripts()[sh.REWRITER_NAME])
    assert renders[0] == renders[1], "the rendered rewriter still depends on the generating tree"


def _install_project(proj: Path) -> None:
    from refmatrix import hooks as hooks_mod
    (proj / ".refmatrix").mkdir(parents=True)
    hooks_mod.install(project_root=proj, refmatrix_root=proj / ".refmatrix", git=False,
                      claude=True, briefing=False, agent_env=False, search=True,
                      scope="project", apply=True, force=True)


def test_apply_records_no_wrapper_paths(env_hooks, tmp_path):
    """T0.4 R4.3 (ch-bsd plan-6 r1 #s-1): the rewriter resolves its wrappers at
    runtime (bug-008), so the `wrappers` paths `install --apply` recorded in
    `.claude/rmx-hooks.json` are read by nothing. The apply records no such
    flag."""
    proj = tmp_path / "proj"
    _install_project(proj)
    flags = json.loads((proj / ".claude" / "rmx-hooks.json").read_text())["flags"]
    assert flags.get("search") is True, flags
    assert "wrappers" not in flags, flags


def test_an_install_recorded_with_wrappers_reads_in_sync(env_hooks, tmp_path):
    """AC-4.3 / R0.7: every install applied before R4.3 carries a `wrappers`
    key in `.claude/rmx-hooks.json`. The dev code's `hooks.check` on such a
    fixture install (a tmp root, never the live install) reads in sync: the
    leftover key is not drift, and the scripts it would name are not
    re-rendered differently. M4.3 (check treats the key as drift) is red."""
    from refmatrix import hooks as hooks_mod
    proj = tmp_path / "proj"
    _install_project(proj)
    rec_file = proj / ".claude" / "rmx-hooks.json"
    rec = json.loads(rec_file.read_text())
    rec["flags"]["wrappers"] = ["/old/tree/bin/rmxgrep", "/old/tree/bin/rmxrg"]
    rec_file.write_text(json.dumps(rec, indent=2) + "\n")
    ok, diff = hooks_mod.check(proj)
    assert ok, diff
    assert (env_hooks / sh.REWRITER_NAME).read_text() == sh.render_scripts()[sh.REWRITER_NAME]


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
