"""ch-bsd plan-12 remedy — the findings that survived the first round.

Two blockers were the same shape: a number sampled at the wrong instant
(`queue_depth` after the queue drained, the phase label one interval off).
Those are covered in `test_rerank_cost_budget.py` and `test_cli_time_phases.py`
beside the code they fix. This file carries the rest: the gates, the renderers
that survived deletion (#m-2), and the states nobody could see (#s-4, #m-3).
"""
from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod
from refmatrix import daemon as dm
from refmatrix import hub as hub_mod


# ---- #m-2: the renderers are REACHED, not merely correct -----------------

def test_hub_queues_renders_the_split_fleet(monkeypatch):
    """M4 deleted the `render_worker_split` call and 24 tests still passed."""
    row = {"project": "p", "daemon_up": True, "stale_files": 0,
           "private_workers": {"embed": "private", "rerank": "shared"}}
    from refmatrix import verbs as _verbs
    monkeypatch.setattr(_verbs, "queues",
                        lambda *a, **kw: {"queues": [row], "refinement_pending": 0})
    res = CliRunner().invoke(cli_mod.main, ["hub", "queues"])
    assert res.exit_code == 0, res.output
    assert "embed=private" in res.output


def test_hub_queues_renders_the_in_process_split(monkeypatch):
    row = {"project": "p", "daemon_up": True, "stale_files": 0,
           "private_workers": {"embed": "in-process", "rerank": "none"}}
    from refmatrix import verbs as _verbs
    monkeypatch.setattr(_verbs, "queues",
                        lambda *a, **kw: {"queues": [row], "refinement_pending": 0})
    res = CliRunner().invoke(cli_mod.main, ["hub", "queues"])
    assert "embed=in-process" in res.output


def test_daemon_status_renders_the_stale_derive_line(tmp_path, monkeypatch):
    """M5 deleted the `render_derive_warning` call and 13 tests still passed."""
    root = tmp_path / ".refmatrix"
    root.mkdir()
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    monkeypatch.setattr(dm, "read_repair_marker", lambda r: None)
    monkeypatch.setattr(dm, "read_pid", lambda r: 4242)
    monkeypatch.setattr(dm, "ping", lambda r, **kw: True)

    def _call(r, op, args=None, timeout=0.0, retries=1, **kw):
        if op == "ping":
            return {"ok": True, "result": {"code_path": "/x/src/refmatrix/__init__.py",
                                           "dev_tree": False}}
        if op == "derive_status":
            assert (args or {}).get("all"), "status must ask every partition"
            return {"ok": True, "result": {"partitions": {
                "memory-p": {"stale": True, "oldest_version": "0.49.1",
                             "running_version": "0.71.0", "never_stamped": False,
                             "reason": "derived by gmd@0.49.1, running 0.71.0"},
                "p": {"stale": False, "oldest_version": "0.71.0",
                      "running_version": "0.71.0", "reason": None},
            }}}
        return {"ok": False}

    monkeypatch.setattr(dm, "call", _call)
    res = CliRunner().invoke(cli_mod.main, ["daemon", "status"])
    # rich wraps at the test console width; compare without whitespace.
    flat = "".join(res.output.split())
    assert "derive[memory-p]" in flat and "0.49.1" in flat
    assert "derive[p]:" not in flat, "a current partition stays quiet"


def test_daemon_status_marks_an_unknown_derive_unverified(tmp_path, monkeypatch):
    """The store most likely to be stale is the one too busy to answer, so
    `unknown` here is not clean (bsd-plan1 #s-3 applied to the new line)."""
    root = tmp_path / ".refmatrix"
    root.mkdir()
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    monkeypatch.setattr(dm, "read_repair_marker", lambda r: None)
    monkeypatch.setattr(dm, "read_pid", lambda r: 4242)
    monkeypatch.setattr(dm, "ping", lambda r, **kw: True)

    def _call(r, op, args=None, timeout=0.0, retries=1, **kw):
        if op == "ping":
            return {"ok": True, "result": {"code_path": "/x/src/refmatrix/__init__.py"}}
        raise TimeoutError("daemon busy")

    monkeypatch.setattr(dm, "call", _call)
    res = CliRunner().invoke(cli_mod.main, ["daemon", "status"])
    flat = "".join(res.output.split())
    assert "derive:" in flat and "UNVERIFIED" in flat


# ---- #b-3: the gate fires on the incident, and not on ship day -----------

def test_a_stamped_and_different_store_is_hot():
    assert hub_mod._queue_row_is_hot(
        {"daemon_up": True, "stale_files": 0, "derive_stale": "0.49.1"}) is True


def test_an_unstamped_store_is_carried_but_not_hot():
    """On the release that introduces stamping, every store is unstamped. A
    gate that fired there would alert eight rows once and be ignored after."""
    assert hub_mod._queue_row_is_hot(
        {"daemon_up": True, "stale_files": 0, "derive_unstamped": True}) is False


def test_a_split_fleet_is_hot():
    assert hub_mod._queue_row_is_hot(
        {"daemon_up": True, "stale_files": 0,
         "private_workers": {"embed": "private"}}) is True


def test_gather_queues_separates_unstamped_from_stale(tmp_path, monkeypatch):
    from refmatrix import daemon as daemon_mod

    root = tmp_path / "p" / ".refmatrix"
    root.mkdir(parents=True)
    monkeypatch.setattr("refmatrix.discovery.discover_roots", lambda: [root])
    monkeypatch.setattr("refmatrix.discovery.daemon_status",
                        lambda r: {"up": True, "pid": 1})
    monkeypatch.setattr("refmatrix.discovery.store_name", lambda r: "p")

    def _mk(derive):
        def _call(r, op, args=None, timeout=0.0, retries=2, **kw):
            if op == "stats":
                return {"ok": True, "result": {"stale_files": [],
                                               "health": {"derive": derive}}}
            if op == "ping":
                return {"ok": True, "result": {"pid": 1, "version": "x",
                                               "code_path": "/x/src/refmatrix/__init__.py",
                                               "dev_tree": False}}
            return {"ok": False}
        return _call

    monkeypatch.setattr(daemon_mod, "call",
                        _mk({"stale": True, "never_stamped": True}))
    row = hub_mod.Hub._gather_queues(None)[0]
    assert row.get("derive_unstamped") is True and "derive_stale" not in row
    assert hub_mod._queue_row_is_hot(row) is False

    monkeypatch.setattr(daemon_mod, "call",
                        _mk({"stale": True, "never_stamped": False,
                             "oldest_version": "0.49.1"}))
    row = hub_mod.Hub._gather_queues(None)[0]
    assert row["derive_stale"] == "0.49.1" and "derive_unstamped" not in row
    assert hub_mod._queue_row_is_hot(row) is True


# ---- #s-4: the in-process embedder is a split, and it can be healed ------

def test_worker_kinds_names_the_in_process_model(tmp_path):
    from refmatrix.embedder import Embedder

    d = dm.Daemon(tmp_path / ".refmatrix")
    assert d.worker_kinds()["embed"] == "none"
    d._embedder_inst = Embedder.__new__(Embedder)
    assert d.worker_kinds()["embed"] == "in-process", (
        "a daemon carrying the model itself is the heaviest split there is")
    assert cli_mod.render_worker_split(d.worker_kinds()) != ""


def test_the_reprobe_heals_an_in_process_embedder(tmp_path, monkeypatch):
    from refmatrix import modelsrv
    from refmatrix.embedder import Embedder

    probes = []

    class _C:
        def __init__(self, role, **kw):
            self.role = role

        def info(self, *, timeout=None):
            probes.append(self.role)
            return {"model": "stub"}

        def close(self, *, timeout=0.0):
            pass

    monkeypatch.setenv("RMX_SHARED_MODELS", "1")
    monkeypatch.setattr(modelsrv, "shared_available", lambda timeout=0.5: True)
    monkeypatch.setattr(modelsrv, "SharedWorkerClient", _C)

    d = dm.Daemon(tmp_path / ".refmatrix")
    d._log = lambda m: None
    d._embedder_inst = Embedder.__new__(Embedder)
    assert d._maybe_adopt_shared() == ["embed"]
    assert d._embedder_inst is None, "the resident model must be dropped"
    assert probes == ["embed"]


# ---- #s-1: the oldest version is the oldest VERSION ----------------------

def test_oldest_version_is_numeric_not_lexicographic(tmp_path):
    from refmatrix.store import Store

    s = Store(tmp_path / ".refmatrix")
    s.init()
    try:
        f = tmp_path / "a.md"
        f.write_text("# a\n")
        s.mark_tracked(str(f.resolve()), f.stat().st_mtime)
        s.stamp_derive("gmd", version="0.71.0")
        s.stamp_derive("ingest", version="0.9.0")
        st = s.derive_status()
        assert st["oldest_version"] == "0.9.0", (
            "min() over strings puts 0.71.0 before 0.9.0 and the line then "
            "read `derived by the version you are running — stale`")
    finally:
        s.close()


# ---- #s-2: the status probe rides the CLI pool ---------------------------

def test_derive_status_is_a_cli_op():
    """It takes `_store_lock` and a status surface asks it every invocation;
    behind a fat ingest in the bulk pool it would time out exactly when a
    store is most likely to be stale."""
    assert "derive_status" in dm.CLI_OPS
