"""plan-4 task 4.2 — in-band entities index rebuild (the 2026-09-14 offline
recipe as a store method + daemon op + boot-time repair when a marker says
a write hit a phantom)."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from refmatrix import daemon as dm
from refmatrix import store as store_mod
from refmatrix.store import Store

# RED until task 4.2 lands the class; getattr keeps collection alive.
RepairAbort = getattr(store_mod, "RepairAbort", type("_Missing", (Exception,), {}))


_BASES: list = []


def _store():
    base = Path(tempfile.mkdtemp(prefix="rmxr-"))
    _BASES.append(base)
    root = base / "proj" / ".refmatrix"; root.parent.mkdir()
    s = Store(root); s.init()
    return root, s


@pytest.fixture(autouse=True)
def _cleanup_bases():
    yield
    import shutil
    while _BASES:
        shutil.rmtree(_BASES.pop(), ignore_errors=True)


def test_rebuild_entities_indexes_preserves_rows_and_ids():
    root, s = _store()
    ids = [s.add_memory(name=f"m{i}", content="b", mtype="project") for i in range(5)]
    c = s.add_concept("alpha")
    rep = s.rebuild_entities_indexes()
    assert rep["rows"] == 6 and rep["indexes"] >= 5 and rep["constraints"] == ["PRIMARY KEY", "UNIQUE"]
    assert [s.get_memory(f"m{i}")["id"] for i in range(5)] == ids
    # the exact path that crashed: delete + reinsert of an existing row
    s.purge_entity(ids[0])
    assert s.add_memory(name="m0", content="b", mtype="project")
    s.close()


def test_rebuild_aborts_on_real_duplicate_groups(monkeypatch):
    root, s = _store()
    s.add_memory(name="m", content="b", mtype="project")
    real = s._connect().execute
    def fake_execute(sql, *a, **k):
        if "GROUP BY" in sql and "HAVING" in sql:
            class R:
                def fetchall(self_inner): return [(1, "memory", "m", 2)]
            return R()
        return real(sql, *a, **k)
    monkeypatch.setattr(s._connect(), "execute", fake_execute)
    with pytest.raises(RepairAbort):
        s.rebuild_entities_indexes()
    s.close()


def test_boot_runs_pending_repair_and_clears_marker():
    root, s = _store(); s.close()
    (root / "repair.needed").write_text(json.dumps({"table": "entities", "op": "learn_from_grep", "at": 0}))
    d = dm.Daemon(root)
    d.store = Store(root); d.store.init()
    logs = []
    d._log = lambda m: logs.append(m)
    rep = d._run_pending_repair()
    assert rep and rep["table"] == "entities"
    assert not (root / "repair.needed").exists()
    assert any("repaired entities" in m for m in logs)
    d.store.close()


def test_boot_without_marker_is_a_noop():
    root, s = _store(); s.close()
    d = dm.Daemon(root)
    d.store = Store(root); d.store.init()
    assert d._run_pending_repair() is None
    d.store.close()


def test_daemon_status_reports_pending_repair(tmp_path, monkeypatch):
    from click.testing import CliRunner
    from refmatrix import cli as cli_mod
    root = tmp_path / ".refmatrix"; root.mkdir()
    (root / "repair.needed").write_text(json.dumps({"table": "entities", "op": "x", "at": 0}))
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    monkeypatch.setattr(dm, "read_pid", lambda r: None)
    out = CliRunner().invoke(cli_mod.main, ["daemon", "status"]).output
    assert "repair pending: entities" in out
