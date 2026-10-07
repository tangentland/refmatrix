"""Launchd plists render a PATH that does not depend on who ran the install.

All three renderers (daemon, hub, session indexer) baked `os.environ["PATH"]`
of the INSTALLING shell. Rendered from a Claude Code session, the plist carried
that session's versioned plugin-cache bin dirs (`~/.claude/plugins/cache/.../
<hash>/bin`, which rot on every plugin update) plus `./` and an empty `::`
entry (both mean "the cwd"). And every later drift check run from a different
shell reported `loaded job env PATH ... != rendered ...`, so the fleet could
never read as in sync (2026-10-07, seen on `rmx hub relaunch-fleet`).
"""
from __future__ import annotations

import plistlib
from pathlib import Path

import pytest

from refmatrix import launchctl, session_launchctl

SESSION_PATH = ("/Users/x/.claude/plugins/cache/foo/abc123/bin::./:"
                "/usr/bin:/bin")


def _path(xml: bytes) -> str:
    return plistlib.loads(xml)["EnvironmentVariables"]["PATH"]


def _renders(tmp_path, rmx):
    root = tmp_path / "proj" / ".refmatrix"
    root.mkdir(parents=True)
    return {
        "daemon": lambda: launchctl.render_plist(root, rmx=rmx),
        "hub": lambda: launchctl.render_hub_plist(rmx=rmx, allow_dev=True),
        "session": lambda: session_launchctl.render_plist(root),
    }


@pytest.mark.parametrize("which", ["daemon", "hub", "session"])
def test_the_rendered_path_ignores_the_callers_path(tmp_path, monkeypatch, which):
    rmx = str(tmp_path / "venv" / "bin" / "rmx")
    (tmp_path / "venv" / "bin").mkdir(parents=True)
    monkeypatch.setenv("RMX_BIN", rmx)
    render = _renders(tmp_path, rmx)[which]

    monkeypatch.setenv("PATH", SESSION_PATH)
    a = _path(render())
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    b = _path(render())

    assert a == b, f"{which}: the PATH followed the caller's shell"
    parts = a.split(":")
    assert "" not in parts and "." not in parts and "./" not in parts, a
    assert not any(".claude/plugins" in p for p in parts), a
    assert "/usr/bin" in parts and "/bin" in parts, a


def test_the_installed_rmx_venv_bin_leads_and_only_existing_dirs_are_kept(tmp_path):
    venv_bin = tmp_path / "venv" / "bin"
    venv_bin.mkdir(parents=True)

    parts = launchctl.launchd_path(str(venv_bin / "rmx")).split(":")

    assert parts[0] == str(venv_bin)
    assert all(Path(p).is_dir() for p in parts), parts
    assert len(parts) == len(set(parts)), parts
