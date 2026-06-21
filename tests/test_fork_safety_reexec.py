"""cli._reexec_for_fork_safety: the macOS guard that re-execs once so a fresh
libobjc loads with the initialize-after-fork check disabled.

libobjc caches OBJC_DISABLE_INITIALIZE_FORK_SAFETY at image load, so setting it
from Python is too late for the daemon's no-exec os.fork(). The only fix is to
re-exec with the var already present. These tests lock that contract without
actually exec'ing (os.execv is monkeypatched).
"""
from __future__ import annotations

import os

from refmatrix import cli


def test_reexecs_on_darwin_when_var_unset(monkeypatch):
    monkeypatch.setattr(cli.sys, "platform", "darwin")
    monkeypatch.delenv("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", raising=False)
    monkeypatch.setattr(cli.sys, "argv", ["/path/to/rmx", "focus", "tail"])
    calls: list = []
    monkeypatch.setattr(os, "execv", lambda exe, argv: calls.append((exe, argv)))

    cli._reexec_for_fork_safety()

    # Var is set before exec so the re-exec'd process short-circuits (no loop).
    assert os.environ["OBJC_DISABLE_INITIALIZE_FORK_SAFETY"] == "YES"
    assert os.environ["TOKENIZERS_PARALLELISM"] == "false"
    assert len(calls) == 1
    exe, argv = calls[0]
    assert exe == cli.sys.executable
    assert argv == [cli.sys.executable, "/path/to/rmx", "focus", "tail"]


def test_no_reexec_when_var_already_set(monkeypatch):
    """A launchd plist (or shell export) that already provides the var must
    short-circuit — no exec cost, no loop."""
    monkeypatch.setattr(cli.sys, "platform", "darwin")
    monkeypatch.setenv("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")
    calls: list = []
    monkeypatch.setattr(os, "execv", lambda exe, argv: calls.append(1))

    cli._reexec_for_fork_safety()

    assert calls == []


def test_no_reexec_off_darwin(monkeypatch):
    monkeypatch.setattr(cli.sys, "platform", "linux")
    monkeypatch.delenv("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", raising=False)
    calls: list = []
    monkeypatch.setattr(os, "execv", lambda exe, argv: calls.append(1))

    cli._reexec_for_fork_safety()

    assert calls == []
    # Off darwin we don't touch the env either.
    assert "OBJC_DISABLE_INITIALIZE_FORK_SAFETY" not in os.environ


def test_exec_failure_does_not_raise(monkeypatch):
    """If execv fails (e.g. ENOMEM) we must fall through, not crash startup."""
    monkeypatch.setattr(cli.sys, "platform", "darwin")
    monkeypatch.delenv("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", raising=False)
    monkeypatch.setattr(cli.sys, "argv", ["/path/to/rmx"])

    def boom(exe, argv):
        raise OSError("cannot exec")

    monkeypatch.setattr(os, "execv", boom)
    cli._reexec_for_fork_safety()  # must not raise
