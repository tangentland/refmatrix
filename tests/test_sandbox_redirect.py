"""Task 23.0 R1/R2/R5, AC-1 and AC-5: the suite's home is a sandbox, decided before import.

bug-088 (72 in-process connects to live sockets in one full run) and bug-101 (143,108
`facts.log` events and 235 `query.log` fixture rows written into the LIVE global store) both
come from the same fact: the suite ran with the developer's real `$HOME`, so
`taxonomy.user_home()`, the hub home, the registry and `launchctl.LAUNCH_AGENTS_DIR` (computed
at IMPORT time) all named the live machine. These tests assert the redirect, not the refusal
(that is tests/test_sandbox_refusal.py).

Every test here calls `_require_sandbox()` FIRST, so at a HEAD without the sandbox it fails on
the missing R1 environment and never reaches a line that would touch the live home.
"""
from __future__ import annotations

import json
import os
import pwd
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

_REPO = Path(__file__).resolve().parents[1]


def _real_home() -> Path:
    """The account's real home from the password database — `$HOME` is redirected by R1."""
    return Path(pwd.getpwuid(os.getuid()).pw_dir)


def _require_sandbox() -> Path:
    root = os.environ.get("RMX_SANDBOX_ROOT")
    assert root, (
        "R1: RMX_SANDBOX_ROOT is unset -- tests/conftest.py installed no sandbox; refusing "
        "to run a probe that would resolve the live home")
    p = Path(root)
    assert p.is_dir(), f"R1: RMX_SANDBOX_ROOT={root} is not a directory"
    return p.resolve()


def _under(path: Path | str, root: Path) -> bool:
    try:
        Path(path).resolve().relative_to(root)
        return True
    except ValueError:
        return False


# ---- AC-1: the redirect canary ---------------------------------------------------------


def test_redirect_canary_every_home_derived_path_is_in_the_sandbox():
    """AC-1. Mutation (pre-registered): move the R1 env assignments below the first
    `refmatrix` import in conftest -> this fails on `launchctl.LAUNCH_AGENTS_DIR`, the one
    path computed at import time."""
    root = _require_sandbox()
    from refmatrix import cli, discovery, hub, launchctl, taxonomy

    paths = {
        "HOME": os.environ.get("HOME", ""),
        "RMX_HOME": os.environ.get("RMX_HOME", ""),
        "launchctl.LAUNCH_AGENTS_DIR": launchctl.LAUNCH_AGENTS_DIR,
        "taxonomy.user_home()": taxonomy.user_home(),
        "discovery.registry_path()": discovery.registry_path(),
        "hub.hub_home()": hub.hub_home(),
        "hub.global_store_root()": hub.global_store_root(),
        "cli._root()": cli._root(),
    }
    escaped = {k: str(v) for k, v in paths.items() if not v or not _under(v, root)}
    assert not escaped, f"paths outside the sandbox {root}: {escaped}"

    # Only now, with every path proven sandboxed, make the global home exist so
    # discover_roots() has at least one root to report (an empty list would pass
    # "every root is in the sandbox" vacuously).
    taxonomy.user_home().mkdir(parents=True, exist_ok=True)
    roots = discovery.discover_roots()
    assert roots, "discover_roots() returned nothing even with the sandbox global home present"
    outside = [str(r) for r in roots if not _under(r, root)]
    assert not outside, f"discover_roots() returned live roots: {outside}"


# ---- AC-5: the short root ---------------------------------------------------------------


def test_sandbox_root_is_short_enough_for_a_unix_socket():
    """AC-5. macOS `sun_path` is ~104 bytes; `<root>/<store>/.refmatrix/rmxd.sock` must fit."""
    root = Path(os.environ.get("RMX_SANDBOX_ROOT") or "")
    assert os.environ.get("RMX_SANDBOX_ROOT"), "R1: RMX_SANDBOX_ROOT is unset"
    sock = root / "s" / ".refmatrix" / "rmxd.sock"
    assert len(str(sock)) <= 100, f"{len(str(sock))} bytes: {sock}"
    # R1: mkdtemp(prefix="rmx-", dir="/tmp")
    assert str(root).startswith(("/tmp/rmx-", "/private/tmp/rmx-")), root


# ---- R1: the run tag, and the PATH pin --------------------------------------------------


def test_sandbox_tag_prefixes_the_root(tmp_path):
    """R1: with RMX_SANDBOX_TAG set, the root prefix is `rmx-<tag>-`, so every sandbox path
    carries the run's tag (AC-4's content check keys on it). A fresh top-level conftest
    import (what `scripts/sandbox-proof.sh` causes) is simulated in a child: the parent's
    RMX_SANDBOX_ROOT is removed so the child must create its own root."""
    _require_sandbox()
    tag = secrets.token_hex(3)
    env = dict(os.environ)
    env.pop("RMX_SANDBOX_ROOT", None)
    env["RMX_SANDBOX_TAG"] = tag
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in env.get("PYTHONPATH", "").split(os.pathsep) if "sandbox_site" not in p)
    code = (
        "import json, os, sys\n"
        f"sys.path.insert(0, {str(_REPO / 'tests')!r})\n"
        "import conftest\n"
        "from refmatrix import launchctl\n"
        "print(json.dumps({'root': os.environ.get('RMX_SANDBOX_ROOT'),"
        " 'home': os.environ.get('HOME'), 'rmx_home': os.environ.get('RMX_HOME'),"
        " 'agents': str(launchctl.LAUNCH_AGENTS_DIR)}))\n"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       cwd=str(tmp_path), env=env, timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]
    got = json.loads(r.stdout.strip().splitlines()[-1])
    assert got["root"], f"conftest import set no RMX_SANDBOX_ROOT: {got}"
    child_root = Path(got["root"]).resolve()
    assert child_root.name.startswith(f"rmx-{tag}-"), (tag, got["root"])
    for k in ("home", "rmx_home", "agents"):
        assert got[k] and _under(got[k], child_root), (k, got[k], child_root)


def test_path_pins_rmx_to_the_test_interpreters_venv():
    """R1: `rmx` resolves to the venv running the suite (`.venv-eval/bin/rmx` on the
    workstation, the lane venv on tier 1), never the deploy `~/bin/rmx`."""
    _require_sandbox()
    found = shutil.which("rmx")
    assert found, "no rmx on PATH"
    assert Path(found) == Path(sys.executable).parent / "rmx", found
    assert Path(found).resolve() != (_real_home() / "bin" / "rmx").resolve(), found


# ---- R2: a per-test store root ----------------------------------------------------------

_SEEN_ROOTS: dict[str, str] = {}


@pytest.mark.parametrize("case", ["first", "second"])
def test_refmatrix_root_is_injected_per_test(case):
    """R2: an autouse fixture points REFMATRIX_ROOT at a per-test path under the sandbox, so
    `_root()` from the repo cwd can never resolve the repo's live `.refmatrix/`."""
    root = _require_sandbox()
    env = os.environ.get("REFMATRIX_ROOT")
    assert env, "R2: REFMATRIX_ROOT is not injected"
    assert _under(env, root), env
    from refmatrix import cli
    assert _under(cli._root(), root)
    assert Path(cli._root()).resolve() != (_REPO / ".refmatrix").resolve()
    _SEEN_ROOTS[case] = str(Path(env).resolve())
    if case == "second":
        assert "first" in _SEEN_ROOTS, "ordering: the first case did not run"
        assert _SEEN_ROOTS["first"] != _SEEN_ROOTS["second"], (
            f"R2: two tests shared one REFMATRIX_ROOT {_SEEN_ROOTS['second']}")


# ---- R5: the grep fixture rows land in the sandbox --------------------------------------


def test_grep_query_log_row_lands_in_the_sandbox(tmp_path, monkeypatch):
    """R5 (bug-101): `rmx grep` from a tmp cwd wrote its `query.log` row into the LIVE
    `~/.refmatrix` (the cwd walk found nothing and `_root()` fell back to `user_home()`).
    Under the sandbox the same invocation's row is found under RMX_SANDBOX_ROOT."""
    root = _require_sandbox()
    from refmatrix import cli as cli_mod
    monkeypatch.setattr("refmatrix.daemon.ping", lambda *a, **k: False)
    monkeypatch.delenv("REFMATRIX_NO_TELEMETRY", raising=False)
    token = f"sbxprobe{secrets.token_hex(4)}"
    (tmp_path / "t.txt").write_text(f"{token} one\nother\n")
    monkeypatch.chdir(tmp_path)
    CliRunner().invoke(cli_mod.main, ["grep", token, "t.txt"])
    hits = [p for p in root.rglob("query.log") if token in p.read_text(errors="replace")]
    assert hits, f"no query.log under {root} carries the grep row for {token!r}"
