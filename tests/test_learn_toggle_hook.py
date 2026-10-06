"""The rewrite hook and the `rmxgrep` wrapper follow the toggle (task 14.3).

With learning OFF, a bare `grep` must stay a real `grep` — no rewrite, no index
read, no teach. That is the user's decision (2026-10-05): the OFF arm of the
measurement in task 14.4 measures no routing AND no learning, not routing
without learning.

Two artifacts carry the rule, and neither can import `refmatrix.learn_switch`:
the rewriter runs under `/usr/bin/env python3` (the system interpreter, no
refmatrix on sys.path) and the wrapper is POSIX shell. So the rule is copied,
and the tests below assert the copies carry the SAME constants as the resolver —
a second copy of a rule is a second place for it to drift.

NOT fixed here: bug-066, the installed rewriter resolving a STALE wrapper copy.
Until that row is closed, the authoritative check is the one in the generated
hook, and these tests exercise the GENERATED artifact rather than whatever is
installed on this machine.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from refmatrix import learn_switch as ls
from refmatrix import search_hooks as sh


@pytest.fixture
def rendered(tmp_path, monkeypatch):
    """The rewriter as `install-hooks` would write it, on disk and executable."""
    monkeypatch.delenv("RMX_LEARN", raising=False)
    monkeypatch.setenv("RMX_CLAUDE_HOOKS_DIR", str(tmp_path / "hooks"))
    scripts = sh.render_scripts()
    out = tmp_path / "hooks"
    out.mkdir(parents=True, exist_ok=True)
    p = out / sh.REWRITER_NAME
    p.write_text(scripts[sh.REWRITER_NAME])
    p.chmod(0o755)
    return p


@pytest.fixture
def project(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    proj = tmp_path / "proj"
    (proj / ".refmatrix").mkdir(parents=True)
    return proj


def _rewrite(script: Path, cmd: str, cwd: Path, env: dict | None = None) -> str:
    payload = json.dumps({"tool_input": {"command": cmd}, "cwd": str(cwd)})
    e = dict(os.environ)
    e.update(env or {})
    r = subprocess.run([sys.executable, str(script)], input=payload,
                       capture_output=True, text=True, cwd=str(cwd), env=e)
    assert r.returncode == 0, r.stderr
    return r.stdout


# ---- the rewriter --------------------------------------------------------

def test_the_rewriter_rewrites_when_learning_is_on(rendered, project):
    """The control. Without it every OFF assertion below passes against a
    rewriter that rewrites nothing at all."""
    out = _rewrite(rendered, "grep -rn alpha src/", project)

    assert out, "no rewrite emitted with learning ON"
    assert "rmxgrep" in out
    assert "-rn alpha src/" in out


@pytest.mark.parametrize("how", ["env", "store-marker", "global-marker"])
def test_the_rewriter_passes_bare_grep_through_when_off(rendered, project, how):
    env = {}
    if how == "env":
        env["RMX_LEARN"] = "0"
    elif how == "store-marker":
        ls.set_enabled(project / ".refmatrix", False, scope="store")
    else:
        ls.set_enabled(None, False, scope="global")

    out = _rewrite(rendered, "grep -rn alpha src/", project, env)

    assert out == "", f"{how}: the hook still rewrote the command ({out!r})"


def test_a_store_marker_above_the_cwd_still_decides(rendered, project):
    """The hook's cwd is wherever the tool ran, which is often a subdirectory.
    The marker lives at the store, so the walk upward has to find it."""
    deep = project / "a" / "b" / "c"
    deep.mkdir(parents=True)
    ls.set_enabled(project / ".refmatrix", False, scope="store")

    assert _rewrite(rendered, "grep -rn alpha .", deep) == ""


def test_a_malformed_env_value_does_not_disable_the_rewrite(rendered, project):
    """`RMX_LEARN=banana` decides nothing here either — the same rule the
    resolver follows, so an operator's typo cannot silently switch the hook off
    (which would look exactly like the hook being broken)."""
    out = _rewrite(rendered, "grep -rn alpha src/", project,
                   {"RMX_LEARN": "banana"})

    assert "rmxgrep" in out


def test_an_env_on_overrides_a_marker_for_the_hook_too(rendered, project):
    ls.set_enabled(project / ".refmatrix", False, scope="store")

    out = _rewrite(rendered, "grep -rn alpha src/", project, {"RMX_LEARN": "1"})

    assert "rmxgrep" in out


# ---- the copies must not drift ------------------------------------------

def test_the_rendered_hook_carries_the_resolver_s_constants():
    """Interpolated at render time, not retyped. If `learn_switch` renames the
    marker or the env var, the rendered hook changes with it — and this test
    fails if someone goes back to hardcoding."""
    script = sh.render_scripts()[sh.REWRITER_NAME]

    assert f'_LEARN_ENV = "{ls.ENV_VAR}"' in script
    assert f'_LEARN_MARKER = "{ls.MARKER_NAME}"' in script
    for v in ls._OFF_VALUES:
        assert repr(v) in script.split("_LEARN_OFF = ")[1].split("\n")[0]
    for v in ls._ON_VALUES:
        assert repr(v) in script.split("_LEARN_ON = ")[1].split("\n")[0]
    assert "@LEARN_" not in script, "a placeholder survived rendering"


def test_the_wrapper_carries_the_same_marker_and_env_var():
    wrapper = Path(__file__).resolve().parents[1] / "bin" / "rmxgrep"
    text = wrapper.read_text()

    assert ls.ENV_VAR in text
    assert ls.MARKER_NAME in text


def test_the_rewriter_checks_the_toggle_without_a_subprocess_or_an_import():
    """This runs on EVERY bare grep in every session. A `rmx` call or a package
    import here would be a per-tool-call tax — asserted by reading the
    generated script, not by timing it (a timing assertion on a dev machine
    measures the machine)."""
    script = sh.render_scripts()[sh.REWRITER_NAME]
    body = script.split("def _learning_off(")[1].split("\ndef ")[0]

    assert "subprocess" not in body
    assert "import refmatrix" not in body
    assert "shutil.which" not in body
    # The whole check is an env read and file tests.
    assert "os.path.exists" in body


# ---- the wrapper ---------------------------------------------------------

def _run_wrapper(args: list[str], cwd: Path, env: dict) -> subprocess.CompletedProcess:
    wrapper = Path(__file__).resolve().parents[1] / "bin" / "rmxgrep"
    e = dict(os.environ)
    e.update(env)
    return subprocess.run(["sh", str(wrapper), *args], capture_output=True,
                          text=True, cwd=str(cwd), env=e)


@pytest.mark.skipif(not shutil.which("grep"), reason="no grep on PATH")
def test_the_wrapper_is_plain_grep_when_learning_is_off(project, monkeypatch):
    """`RMXGREP_MODE=rich` normally forces the annotated index path even with a
    piped stdout. With learning off the real tool answers instead, byte-for-byte
    against a direct-exec control."""
    f = project / "t.txt"
    f.write_text("alpha one\nbeta two\n")
    real = subprocess.run([shutil.which("grep") or "/usr/bin/grep",
                           "-n", "alpha", "t.txt"],
                          capture_output=True, text=True, cwd=str(project))

    off = _run_wrapper(["-n", "alpha", "t.txt"], project,
                       {"RMXGREP_MODE": "rich", "RMX_LEARN": "0",
                        "HOME": str(project.parent / "home")})

    assert off.returncode == real.returncode
    assert off.stdout == real.stdout
    assert off.stderr == "", f"the index annotated a read it should not have: {off.stderr!r}"
