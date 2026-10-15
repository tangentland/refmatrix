"""bug-118: the generated cat-herder BLOCKING hooks never blocked.

The generator rendered every optional project hook as
`[ -x P ] && P || true`. When P exits 2 (the PreToolUse "block" code) the
`|| true` turns the hook's exit into 0, so `enforce-test-to-file.sh` and
`enforce-rmx-grep.sh` could never block (ch-bsd plan-16/22 r8, 2026-10-15,
read from `.claude/settings.json:149`).

The contract: an optional project hook exits with P's status when P is
present and executable, and 0 when it is absent. ONE helper renders it
(`hooks._optional_project_hook`); an AST check refuses a second rendering.
"""
from __future__ import annotations

import ast
import os
import subprocess
from pathlib import Path

import pytest

from refmatrix import hooks as hooks_mod
from refmatrix.hooks import _claude_hook_block
from tests.test_hooks_reproducible import _cmds, _project

SCRIPTS = ("enforce-test-to-file.sh", "enforce-rmx-grep.sh", "adr-gate.sh")


def _script_cmds(block):
    out = {}
    for _, _, c in _cmds(block):
        for n in SCRIPTS:
            if f".claude/hooks/{n}" in c:
                out[n] = c
    return out


def _run(cmd: str, proj: Path) -> int:
    env = {"PATH": "/usr/bin:/bin", "CLAUDE_PROJECT_DIR": str(proj)}
    return subprocess.run(["/bin/bash", "-c", cmd], env=env, cwd=str(proj),
                          capture_output=True, timeout=30).returncode


def _stub(proj: Path, name: str, code: int) -> None:
    hd = proj / ".claude" / "hooks"
    hd.mkdir(parents=True, exist_ok=True)
    p = hd / name
    p.write_text(f"#!/bin/sh\necho blocked-by-{name} >&2\nexit {code}\n")
    p.chmod(0o755)


@pytest.mark.parametrize("name", SCRIPTS)
def test_generated_hook_propagates_the_scripts_exit_2(tmp_path, name):
    proj = _project(tmp_path)
    _stub(proj, name, 2)
    block = _claude_hook_block(proj / ".refmatrix", project_root=proj, enforce=True)
    cmds = _script_cmds(block)
    assert name in cmds, cmds
    assert _run(cmds[name], proj) == 2, cmds[name]


@pytest.mark.parametrize("name", SCRIPTS)
def test_generated_hook_exits_0_when_the_script_is_absent(tmp_path, name):
    proj = _project(tmp_path)                          # no .claude/hooks at all
    block = _claude_hook_block(proj / ".refmatrix", project_root=proj, enforce=True)
    assert _run(_script_cmds(block)[name], proj) == 0


@pytest.mark.parametrize("name", SCRIPTS)
def test_generated_hook_exits_0_when_the_script_passes(tmp_path, name):
    proj = _project(tmp_path)
    _stub(proj, name, 0)
    block = _claude_hook_block(proj / ".refmatrix", project_root=proj, enforce=True)
    assert _run(_script_cmds(block)[name], proj) == 0


def test_no_generated_command_swallows_a_project_hooks_exit(tmp_path):
    proj = _project(tmp_path)
    block = _claude_hook_block(proj / ".refmatrix", project_root=proj, enforce=True)
    for ev, _, c in _cmds(block):
        if "$CLAUDE_PROJECT_DIR" in c:
            assert "|| true" not in c, f"{ev}: swallowed project-hook exit: {c}"


def test_one_helper_renders_every_optional_project_hook():
    """AST check against bypass: the only string literal in hooks.py that
    names a `$CLAUDE_PROJECT_DIR/.claude/hooks/` path lives inside
    `_optional_project_hook`. A second hand-rendered site fails here."""
    src = Path(hooks_mod.__file__).read_text()
    tree = ast.parse(src)
    helper = [n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "_optional_project_hook"]
    assert len(helper) == 1, "hooks._optional_project_hook must exist exactly once"
    inside = {id(n) for n in ast.walk(helper[0])}
    stray = [(n.lineno, n.value) for n in ast.walk(tree)
             if isinstance(n, ast.Constant) and isinstance(n.value, str)
             and "$CLAUDE_PROJECT_DIR/.claude/hooks" in n.value and id(n) not in inside]
    assert not stray, f"optional project hook rendered outside the helper: {stray}"


def test_helper_rendering_is_if_then_fi():
    c = hooks_mod._optional_project_hook("x.sh")
    assert c == ('if [ -x "$CLAUDE_PROJECT_DIR/.claude/hooks/x.sh" ]; '
                 'then "$CLAUDE_PROJECT_DIR/.claude/hooks/x.sh"; fi')
