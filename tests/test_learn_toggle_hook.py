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
    # The whole check is an env read and STATs — not `os.path.exists`, which
    # read an unreadable marker as absent and said nothing (bug-080).
    assert "_marker_present(" in body
    assert "os.path.exists" not in body
    helper = script.split("def _marker_present(")[1].split("\ndef ")[0]
    assert "_os.stat(" in helper and "subprocess" not in helper


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


# ---- an UNREADABLE marker: same answer as the resolver, and SAID (bug-080) --
#
# The resolver (`learn_switch.decision`) answers an unreadable store marker by
# falling through (a marker that cannot be read has not said "off") and
# reporting it in `marker_error`. The shell and the rewriter copies used
# `[ -f ]` / `os.path.exists`, which answer "absent" for an unsearchable dir
# and say nothing. They cannot print to stderr — the wrapper's output must stay
# grep's bytes — so they append to `~/.refmatrix/learn-switch.log`, and
# `rmx learn status` shows it.

_ROOT_UID = hasattr(os, "geteuid") and os.geteuid() == 0


def _switch_log(project: Path) -> Path:
    return project.parent / "home" / ".refmatrix" / "learn-switch.log"


@pytest.mark.skipif(_ROOT_UID, reason="root ignores chmod")
def test_the_rewriter_reports_an_unreadable_store_marker(rendered, project):
    store = project / ".refmatrix"
    store.chmod(0)
    try:
        out = _rewrite(rendered, "grep -rn alpha src/", project)
    finally:
        store.chmod(0o755)

    assert "rmxgrep" in out, "an unreadable marker must not flip the answer"
    log = _switch_log(project)
    assert log.exists(), "the unreadable marker was not reported"
    assert "unreadable" in log.read_text() and str(store) in log.read_text()


@pytest.mark.skipif(_ROOT_UID or not shutil.which("grep"),
                    reason="root ignores chmod / no grep")
def test_the_wrapper_reports_an_unreadable_store_marker(project):
    f = project / "t.txt"
    f.write_text("alpha one\n")
    store = project / ".refmatrix"
    store.chmod(0)
    try:
        r = _run_wrapper(["-n", "alpha", "t.txt"], project,
                         {"RMXGREP_MODE": "plain", "RMXGREP_TEACH": "0",
                          "RMXGREP_RMX": "/usr/bin/true",
                          "HOME": str(project.parent / "home")})
    finally:
        store.chmod(0o755)

    assert r.stdout == "1:alpha one\n" and r.stderr == "", (r.stdout, r.stderr)
    log = _switch_log(project)
    assert log.exists() and "unreadable" in log.read_text(), \
        "the wrapper read an unreadable marker as absent and said nothing"


@pytest.mark.skipif(not shutil.which("rg"), reason="no rg on PATH")
def test_rmxrg_follows_the_toggle_too(project, tmp_path):
    """`bin/rmxrg` had NO learn check at all (found fixing bug-080's shell
    sibling): with `RMX_LEARN=0` it still called `rmx grep` in rich mode."""
    called = tmp_path / "rmx-was-called"
    stand_in = tmp_path / "rmx"
    stand_in.write_text(f"#!/bin/sh\ntouch {called}\nexit 0\n")
    stand_in.chmod(0o755)
    (project / "t.txt").write_text("alpha one\n")
    wrapper = Path(__file__).resolve().parents[1] / "bin" / "rmxrg"
    e = dict(os.environ, RMXGREP_MODE="rich", RMX_LEARN="0",
             RMXGREP_RMX=str(stand_in), HOME=str(project.parent / "home"))
    real = subprocess.run(["rg", "-n", "alpha", "t.txt"], capture_output=True,
                          text=True, cwd=str(project))

    r = subprocess.run(["sh", str(wrapper), "-n", "alpha", "t.txt"],
                       capture_output=True, text=True, cwd=str(project), env=e)

    assert not called.exists(), "rmxrg called rmx with learning OFF"
    assert (r.stdout, r.returncode) == (real.stdout, real.returncode)
