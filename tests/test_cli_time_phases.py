"""bug-033: ~8.5 s between `build_context` (0.45 s warm) and the daemonless CLI
(9.0 s), of which only 2.8 s is CPU — so most of it is waiting, not computing.

Nothing here proposes a mechanism. It makes the split MEASURABLE and
reproducible by anyone, which is the step the 62.9 s retraction skipped.
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

from refmatrix import cli as cli_mod


def test_phase_report_is_off_by_default(monkeypatch):
    monkeypatch.delenv("RMX_TIME_PHASES", raising=False)
    cli_mod._PHASE_MARKS.clear()
    cli_mod.phase_mark("store-bind")
    assert cli_mod._PHASE_MARKS == []
    assert cli_mod.render_phase_report(1.0) == ""


def test_every_phase_appears_exactly_once(monkeypatch):
    monkeypatch.setenv("RMX_TIME_PHASES", "1")
    cli_mod._PHASE_MARKS.clear()
    for name in ("entry", "dispatch", "store-bind", "build_context"):
        cli_mod.phase_mark(name)
    out = cli_mod.render_phase_report(cli_mod.time.monotonic())
    for name in ("import", "dispatch", "store-bind", "build_context", "exit",
                 "total"):
        assert f"{name}=" in out, (name, out)
    body = [p for p in out.split() if "=" in p]
    assert len(body) == len(set(p.split("=")[0] for p in body))


def test_each_interval_carries_the_phase_that_produced_it(monkeypatch):
    """ch-bsd plan-12 #b-2: the labels were shifted by one, so the tool built
    to attribute 8.5 s billed the neighbouring phase. Costs fixed in advance."""
    monkeypatch.setenv("RMX_TIME_PHASES", "1")
    cli_mod._PHASE_MARKS.clear()
    t = cli_mod._PROC_T0
    # import 0.1 | dispatch 0.2 | store-bind 0.3 | build_context 2.0 | exit 0.5
    marks = [("entry", 0.1), ("dispatch", 0.3), ("store-bind", 0.6),
             ("build_context", 2.6)]
    for name, off in marks:
        cli_mod._PHASE_MARKS.append((name, t + off))
    out = cli_mod.render_phase_report(t + 3.1)
    parts = dict((p.split("=")[0], float(p.split("=")[1].rstrip("s")))
                 for p in out.split() if "=" in p)
    assert parts["import"] == pytest.approx(0.1, abs=0.01)
    assert parts["dispatch"] == pytest.approx(0.2, abs=0.01)
    assert parts["store-bind"] == pytest.approx(0.3, abs=0.01)
    assert parts["build_context"] == pytest.approx(2.0, abs=0.01), (
        "the phase that cost 2 s must be the one billed for it")
    assert parts["exit"] == pytest.approx(0.5, abs=0.01)


def test_the_splits_sum_to_the_total(monkeypatch):
    monkeypatch.setenv("RMX_TIME_PHASES", "1")
    cli_mod._PHASE_MARKS.clear()
    t = cli_mod._PROC_T0
    for i, name in enumerate(("entry", "dispatch", "store-bind",
                              "build_context"), 1):
        cli_mod._PHASE_MARKS.append((name, t + i * 0.5))
    out = cli_mod.render_phase_report(t + 3.0)
    parts = dict(
        (p.split("=")[0], float(p.split("=")[1].rstrip("s")))
        for p in out.split() if "=" in p
    )
    total = parts.pop("total")
    assert abs(sum(parts.values()) - total) <= 0.05 * total, (parts, total)


def test_phases_go_to_stderr_never_stdout(tmp_path):
    """stdout is the hook payload — plan 9 counts those bytes and a stray line
    corrupts an injection."""
    env = dict(os.environ, RMX_TIME_PHASES="1", RMX_INVOCATION_SOURCE="test")
    r = subprocess.run(
        [sys.executable, "-m", "refmatrix.cli", "version"],
        cwd=str(tmp_path), env=env, capture_output=True, text=True)
    assert "phase" not in r.stdout
    assert r.stdout.strip(), "the command still has to print its own output"

    env2 = dict(os.environ, RMX_INVOCATION_SOURCE="test")
    env2.pop("RMX_TIME_PHASES", None)
    r2 = subprocess.run(
        [sys.executable, "-m", "refmatrix.cli", "version"],
        cwd=str(tmp_path), env=env2, capture_output=True, text=True)
    assert r2.stdout == r.stdout, "the timing flag must not change stdout bytes"
    assert "phase" not in r2.stderr


# ---- what the measurement found (bug-033) --------------------------------

def test_the_grep_backstop_never_walks_a_memory_only_store(tmp_path, monkeypatch):
    """`~/.refmatrix` is the global memory-only store, so `s.root.parent` is
    the user's HOME. The backstop was `rg`-ing all of it: 15.09 s measured, the
    hard subprocess timeout, zero hits, swallowed. It tracks no filesystem
    paths, so there is nothing there for a grep floor to find."""
    from refmatrix import context as ctx

    called = []
    monkeypatch.setattr(ctx, "_grep_backstop",
                        lambda *a, **kw: called.append(a[1]) or [])
    monkeypatch.setattr("refmatrix.store.is_memory_only_root",
                        lambda root: True)

    from refmatrix.store import Store
    s = Store(tmp_path / ".refmatrix")
    s.init()
    try:
        ctx.build_context(s, "a phrase that indexes nothing", max_tokens=200)
    finally:
        s.close()
    assert called == [], f"greped {called} for a store that tracks no files"


def test_a_backstop_timeout_is_said_not_swallowed(tmp_path, monkeypatch, capsys):
    """15 s of wall time that buys nothing must not look like 'no hits'."""
    import subprocess

    from refmatrix import context as ctx

    def _boom(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, kw.get("timeout", 15))

    monkeypatch.setattr(subprocess, "run", _boom)
    out = ctx._grep_backstop(["alpha"], tmp_path, limit=5)
    assert out == []
    err = capsys.readouterr().err
    assert "grep backstop timed out" in err and str(tmp_path) in err
