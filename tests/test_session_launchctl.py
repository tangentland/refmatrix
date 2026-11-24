"""Tests for session_launchctl.py — Phase D plist rendering.

Install/uninstall round-trip is skipped: it would touch the real
~/Library/LaunchAgents and call launchctl. Coverage focuses on plist
contents, label shape, and partition handling — the parts where a bug
would produce a broken LaunchAgent."""
from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from refmatrix import session_launchctl as sl
from refmatrix.cli import main


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


@pytest.fixture
def agents_dir(tmp_path, monkeypatch):
    """A per-test LaunchAgents dir: the stagger reads the OTHER installed session plists, so the
    sandbox's shared dir would carry one test's plists into the next."""
    d = tmp_path / "LaunchAgents"
    d.mkdir()
    monkeypatch.setattr(sl, "LAUNCH_AGENTS_DIR", d)
    return d


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


def test_render_plist_basics(fake_root, agents_dir):
    blob = sl.render_plist(fake_root)
    data = plistlib.loads(blob)
    assert data["Label"] == sl.label_for_root(fake_root)
    assert data["RunAtLoad"] is True
    assert "StartInterval" not in data   # L206: a per-store calendar offset instead
    assert len(data["StartCalendarInterval"]) == 60 * 60 // sl.DEFAULT_INTERVAL_SECONDS
    assert "KeepAlive" not in data  # one-shot, not a daemon
    args = data["ProgramArguments"]
    assert args[-2:] == ["session", "ingest"]
    assert "--all-projects" not in args


def test_render_plist_all_projects(fake_root):
    blob = sl.render_plist(fake_root, all_projects=True)
    data = plistlib.loads(blob)
    assert "--all-projects" in data["ProgramArguments"]


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


# ---- L206 (2026-11-24): staggered schedule + one indexer at a time --------------------------
#
# Six launchd session indexers, `StartInterval` 600 each on its own clock, overlapped 7-wide
# under load on 2026-11-24 (~06:25Z) and helped push the machine to load average ~200 (bug-309
# note, bug-310). Each store now fires on its own minutes inside the interval, and a run that
# finds another indexer running exits 0 with one counted line.

_FLEET = ["viascope", "refmatrix", "atldb", "cliquet", "cliquedb", "orderly"]


def _minutes(root: Path) -> list:
    data = plistlib.loads(sl.plist_path(root).read_bytes())
    assert "StartInterval" not in data, data
    return sorted(e["Minute"] for e in data["StartCalendarInterval"])


@pytest.mark.parametrize("names", [_FLEET, [f"s{i}" for i in range(10)]], ids=["fleet6", "full10"])
def test_installed_stores_fire_on_distinct_stable_minutes(fake_root, tmp_path, agents_dir, names):
    """Each store installed in turn (the bytes `install()` writes) fires every 10 minutes on
    minutes no other store uses. Ten stores fill all ten slots, so a hash collision is certain
    there and must be resolved. Stable: the re-render `check()` makes from the installed flags is
    byte-identical, and so is a fresh render after the plist is removed."""
    roots = []
    for n in names:
        r = tmp_path / n / ".refmatrix"
        r.mkdir(parents=True)
        roots.append(r)
        sl.plist_path(r).write_bytes(sl.render_plist(r))
    layout = {r.parent.name: _minutes(r) for r in roots}
    for mins in layout.values():
        assert len(mins) == 6 and all(b - a == 10 for a, b in zip(mins, mins[1:])), layout
    flat = [m for mins in layout.values() for m in mins]
    assert len(flat) == len(set(flat)), f"two stores share a minute: {layout}"
    for r in roots:
        installed = sl.plist_path(r).read_bytes()
        assert sl.render_plist(r, **sl.installed_flags(r)) == installed
        sl.plist_path(r).unlink()
        assert sl.render_plist(r) == installed, f"{r} moved on reinstall"
        sl.plist_path(r).write_bytes(installed)


@pytest.mark.parametrize("seconds,step", [(600, 10), (120, 2), (420, 6), (2700, 30), (3600, 60)])
def test_calendar_cadence_keeps_the_interval(fake_root, agents_dir, seconds, step):
    """600 s is every 10 minutes. A step that does not divide the hour rounds DOWN to one that
    does (7 min -> 6, 45 -> 30), so the gap across the hour is the same as every other gap and
    a store never fires less often than asked. The installed flags read the schedule back."""
    data = plistlib.loads(sl.render_plist(fake_root, interval_seconds=seconds))
    mins = sorted(e["Minute"] for e in data["StartCalendarInterval"])
    assert len(mins) == 60 // step and mins[0] < step, mins
    assert all(b - a == step for a, b in zip(mins, mins[1:])), mins
    sl.plist_path(fake_root).write_bytes(plistlib.dumps(data))
    flags = sl.installed_flags(fake_root)
    assert flags["interval_seconds"] == step * 60 and flags["offset_minutes"] == mins[0], flags


@pytest.mark.parametrize("seconds", [30, 7200])
def test_an_interval_a_calendar_minute_cannot_express_is_refused(fake_root, agents_dir, seconds):
    with pytest.raises(ValueError, match="interval"):
        sl.render_plist(fake_root, interval_seconds=seconds)


def test_an_installed_start_interval_plist_reports_drift(agents_dir, deployed_rmx):
    """The pre-L206 plist (`StartInterval` 600, no calendar) is read back as a 600 s interval
    with no offset, and `rmx session launchctl install --check` calls it drift, naming both
    keys, so `rmx hub relaunch-fleet` re-renders it on the next deploy."""
    root = Path(os.environ["REFMATRIX_ROOT"])           # the per-test store `_root()` resolves
    old = plistlib.loads(sl.render_plist(root))
    old.pop("StartCalendarInterval", None)
    old["StartInterval"] = 600
    sl.plist_path(root).write_bytes(plistlib.dumps(old))
    flags = sl.installed_flags(root)
    assert flags["interval_seconds"] == 600 and flags["offset_minutes"] is None, flags
    r = CliRunner().invoke(main, ["session", "launchctl", "install", "--check"])
    out = " ".join(r.output.split())
    assert r.exit_code == 1, r.output
    assert "DRIFT" in out and "StartInterval" in out and "StartCalendarInterval" in out, out


_HOLDER = r"""
import os, sys
from pathlib import Path
from refmatrix import session_ingest as si
with si.indexer_lock(Path(os.environ["REFMATRIX_ROOT"])) as holder:
    assert holder is None, holder
    print("HELD", flush=True)
    sys.stdin.read()        # the gate: held until the test closes stdin or kills this process
"""


@pytest.mark.timeout(60)
def test_a_second_session_ingest_exits_zero_naming_the_running_indexer(tmp_path):
    """A real holder process takes the indexer lock; `rmx session ingest` run meanwhile exits 0
    with one counted line naming the holder's pid and does no work. The holder is then
    SIGKILLed: the OS releases the lock, so the next run proceeds (no pid file to go stale)."""
    empty = tmp_path / "no-jsonl"
    empty.mkdir()
    argv = ["session", "ingest", "--no-index", str(empty)]
    holder = subprocess.Popen([sys.executable, "-c", _HOLDER], stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        line = holder.stdout.readline()
        if line.strip() != "HELD":
            holder.kill()
            pytest.fail(f"holder did not take the lock: {line!r} {holder.stderr.read()}")
        r = CliRunner().invoke(main, argv)
        out = " ".join(r.output.split())
        assert r.exit_code == 0, r.output
        assert "skipped=1" in out and f"pid {holder.pid}" in out, out
        assert "no session JSONLs found" not in out, out
        holder.kill()
        holder.wait()
        r = CliRunner().invoke(main, argv)
        out = " ".join(r.output.split())
        assert r.exit_code == 0, r.output
        assert "no session JSONLs found" in out and "skipped=1" not in out, out
    finally:
        if holder.poll() is None:
            holder.kill()
            holder.wait()
