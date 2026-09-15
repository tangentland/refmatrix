"""`rmx daemon restart` must pick the right path per supervision state.

Two behaviors under test, no real daemon/store needed:

- launchd-supervised (LaunchAgent loaded) → force-restart in place via
  `launchctl kickstart -k` (`lc.kickstart(root, restart=True)`); no
  stop+respawn, so the supervisor keeps owning the lifecycle.
- standalone (not loaded, or --standalone) → `stop_daemon` then
  `spawn_daemon` fork a fresh process.
"""
from __future__ import annotations

from click.testing import CliRunner

from refmatrix.cli import main
from refmatrix import hub as hub_mod
import refmatrix.cli as cli
import refmatrix.daemon as daemon_mod
import refmatrix.launchctl as lc


def _init(tmp_path, monkeypatch):
    proj = tmp_path / "proj"
    proj.mkdir()
    monkeypatch.chdir(proj)
    r = CliRunner().invoke(main, ["init"], catch_exceptions=False)
    assert r.exit_code == 0, r.output


def test_restart_standalone_stops_then_spawns(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    monkeypatch.setattr(cli, "_resolve_partition", lambda: "testproj")
    # Not launchd-supervised → standalone path.
    monkeypatch.setattr(lc, "is_loaded", lambda root: False)

    calls: list[str] = []
    monkeypatch.setattr(daemon_mod, "stop_daemon",
                        lambda root, **kw: calls.append("stop") or True)
    monkeypatch.setattr(
        daemon_mod, "spawn_daemon",
        lambda root, **kw: calls.append("spawn") or 4242,
    )

    r = CliRunner().invoke(main, ["daemon", "restart"], catch_exceptions=False)
    assert r.exit_code == 0, r.output
    # Stop precedes spawn — a fresh process replaces the old one.
    assert calls == ["stop", "spawn"]
    assert "pid=4242" in r.output


def test_restart_supervised_kickstarts_in_place(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    monkeypatch.setattr(cli, "_resolve_partition", lambda: "testproj")
    # Force the darwin/supervised branch regardless of host OS.
    monkeypatch.setattr(cli.sys, "platform", "darwin", raising=False)
    monkeypatch.setattr(lc, "is_loaded", lambda root: True)

    kicked: list[bool] = []

    def fake_kickstart(root, *, restart=False):
        kicked.append(restart)
        return "com.example.rmx.testproj"

    monkeypatch.setattr(lc, "kickstart", fake_kickstart)
    monkeypatch.setattr(daemon_mod, "read_pid", lambda root: 777)
    # Must NOT spawn or stop_daemon when launchd owns it — but it DOES ask the
    # daemon to stop first (plan-4 r3 #b-1: a bare -k was a SIGKILL at
    # launchd's 5 s ExitTimeOut) and then kicks WITHOUT -k when it stopped.
    stops = []
    monkeypatch.setattr(daemon_mod, "graceful_stop",
                        lambda root, *, grace, report=None: stops.append(grace) or True)
    monkeypatch.setattr(hub_mod, "rpc", lambda op, args=None, **kw: {"ok": True})   # the watchdog pause
    monkeypatch.setattr(daemon_mod, "stop_daemon",
                        lambda root, **kw: (_ for _ in ()).throw(
                            AssertionError("stop_daemon called under launchd")))
    monkeypatch.setattr(daemon_mod, "spawn_daemon",
                        lambda root, **kw: (_ for _ in ()).throw(
                            AssertionError("spawn_daemon called under launchd")))

    r = CliRunner().invoke(main, ["daemon", "restart"], catch_exceptions=False)
    assert r.exit_code == 0, r.output
    assert stops == [daemon_mod.stop_grace_s()]
    assert kicked == [False]  # plain kickstart: the daemon already stopped
    assert "kickstart" in r.output and "kickstart -k" not in r.output


def test_restart_standalone_flag_overrides_launchd(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    monkeypatch.setattr(cli, "_resolve_partition", lambda: "testproj")
    monkeypatch.setattr(cli.sys, "platform", "darwin", raising=False)
    # Supervised, but --standalone forces the stop+respawn path.
    monkeypatch.setattr(lc, "is_loaded", lambda root: True)
    monkeypatch.setattr(lc, "kickstart",
                        lambda root, **kw: (_ for _ in ()).throw(
                            AssertionError("kickstart called with --standalone")))

    calls: list[str] = []
    monkeypatch.setattr(daemon_mod, "stop_daemon",
                        lambda root, **kw: calls.append("stop") or True)
    monkeypatch.setattr(
        daemon_mod, "spawn_daemon",
        lambda root, **kw: calls.append("spawn") or 9,
    )

    r = CliRunner().invoke(main, ["daemon", "restart", "--standalone"],
                           catch_exceptions=False)
    assert r.exit_code == 0, r.output
    assert calls == ["stop", "spawn"]
