"""Tests for session_launchctl.py — Phase D plist rendering.

Install/uninstall round-trip is skipped: it would touch the real
~/Library/LaunchAgents and call launchctl. Coverage focuses on plist
contents, label shape, and partition handling — the parts where a bug
would produce a broken LaunchAgent."""
from __future__ import annotations

import plistlib
from pathlib import Path

import pytest

from refmatrix import session_launchctl as sl


@pytest.fixture
def fake_root(tmp_path, monkeypatch):
    """A pretend refmatrix root + fake `rmx` on PATH so render_plist works
    without requiring a real install."""
    root = tmp_path / "myproj" / ".refmatrix"
    root.mkdir(parents=True)
    fake_rmx = tmp_path / "bin" / "rmx"
    fake_rmx.parent.mkdir()
    fake_rmx.write_text("#!/bin/sh\nexit 0\n")
    fake_rmx.chmod(0o755)
    monkeypatch.setenv("RMX_BIN", str(fake_rmx))
    return root


def test_label_for_root_shape(fake_root):
    label = sl.label_for_root(fake_root)
    assert label.startswith("com.refmatrix.session-indexer.")
    assert "myproj" in label


def test_label_for_root_distinct_from_daemon_label(fake_root):
    """Session indexer + daemon labels must not collide (one is the
    process supervisor, the other is the periodic ticker)."""
    from refmatrix import launchctl as daemon_lc
    assert sl.label_for_root(fake_root) != daemon_lc.label_for_root(fake_root)


def test_plist_path_in_launch_agents_dir(fake_root):
    p = sl.plist_path(fake_root)
    assert p.parent == sl.LAUNCH_AGENTS_DIR
    assert p.name.endswith(".plist")


def test_render_plist_basics(fake_root):
    blob = sl.render_plist(fake_root)
    data = plistlib.loads(blob)
    assert data["Label"] == sl.label_for_root(fake_root)
    assert data["RunAtLoad"] is True
    assert data["StartInterval"] == sl.DEFAULT_INTERVAL_SECONDS
    assert "KeepAlive" not in data  # one-shot, not a daemon
    args = data["ProgramArguments"]
    assert args[-2:] == ["session", "ingest"]
    assert "--all-projects" not in args


def test_render_plist_all_projects(fake_root):
    blob = sl.render_plist(fake_root, all_projects=True)
    data = plistlib.loads(blob)
    assert "--all-projects" in data["ProgramArguments"]


def test_render_plist_custom_interval(fake_root):
    blob = sl.render_plist(fake_root, interval_seconds=120)
    data = plistlib.loads(blob)
    assert data["StartInterval"] == 120


def test_render_plist_includes_refmatrix_root_env(fake_root):
    blob = sl.render_plist(fake_root)
    data = plistlib.loads(blob)
    assert data["EnvironmentVariables"]["REFMATRIX_ROOT"] == str(
        fake_root.resolve()
    )


def test_render_plist_omits_partition_when_default(fake_root):
    """If partition matches the project default, don't bake it into env —
    the daemon resolves the same value on its own."""
    from refmatrix.store import default_partition_name
    default = default_partition_name(fake_root)
    blob = sl.render_plist(fake_root, partition=default)
    data = plistlib.loads(blob)
    assert "RMX_PARTITION" not in data["EnvironmentVariables"]


def test_render_plist_bakes_partition_when_override(fake_root):
    blob = sl.render_plist(fake_root, partition="sessions-myproj")
    data = plistlib.loads(blob)
    assert data["EnvironmentVariables"]["RMX_PARTITION"] == "sessions-myproj"


def test_render_plist_log_paths(fake_root):
    blob = sl.render_plist(fake_root)
    data = plistlib.loads(blob)
    assert data["StandardOutPath"].endswith("session-indexer.stdout.log")
    assert data["StandardErrorPath"].endswith("session-indexer.stderr.log")
