"""The global store (~/.refmatrix) is memory-only, and every ingest route
refuses filesystem tracking structurally — daemon ops, the direct in-process
ingest, and the sync funnel — instead of relying on callers remembering.

The historical failure: an explicit ingest rooted at $HOME dumped 5357
code/doc entities (~/Library caches included) into the global partition and
produced a perpetual stale count. The drain removed the rows; this guard
makes the refill impossible.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from refmatrix import daemon as dm
from refmatrix import sync as syncmod
from refmatrix.ingest import ingest_path
from refmatrix.store import Store, is_memory_only_root


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    """Point Path.home() at a tmp dir so ~/.refmatrix is test-owned."""
    home = tmp_path / "home"
    (home / ".refmatrix").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    return home


def test_predicate_matches_only_the_global_root(fake_home, tmp_path):
    assert is_memory_only_root(fake_home / ".refmatrix")
    assert not is_memory_only_root(tmp_path / "proj" / ".refmatrix")


def test_ingest_path_refuses_the_global_store(fake_home):
    s = SimpleNamespace(root=fake_home / ".refmatrix")
    with pytest.raises(RuntimeError, match="memory-only global store"):
        ingest_path(s, fake_home)


def test_sync_refuses_nonempty_paths_on_the_global_store(fake_home):
    s = SimpleNamespace(root=fake_home / ".refmatrix")
    with pytest.raises(RuntimeError, match="memory-only global store"):
        syncmod.sync_files(s, [str(fake_home / "x.py")])


def test_sync_empty_flush_stays_quiet_on_the_global_store(fake_home):
    # Hook-driven `rmx sync --flush-queue` fires from $HOME contexts; an
    # empty queue must no-op, not crash the hook.
    root = fake_home / ".refmatrix"
    s = Store(root)
    s.init()
    try:
        report = syncmod.flush_queue(s, project_root=fake_home)
    finally:
        s.close()
    assert report["added"] == 0 and report["touched"] == 0


def test_daemon_derives_memory_only_and_drops_watch_roots(fake_home):
    d = dm.Daemon(fake_home / ".refmatrix", watch_root=[fake_home])
    assert d.memory_only
    assert d.watch_roots == [] and d.watch_root is None


def test_project_daemon_is_not_memory_only(fake_home, tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    d = dm.Daemon(proj / ".refmatrix", watch_root=[proj])
    assert not d.memory_only
    assert d.watch_roots == [proj.resolve()]


def test_daemon_ingest_ops_refuse_before_registering_a_job(fake_home):
    d = SimpleNamespace(memory_only=True, root=fake_home / ".refmatrix")
    for op, fn, args in [
        ("ingest", dm._op_ingest_path, {"path": str(fake_home)}),
        ("ingest", dm._op_ingest_path_start, {"path": str(fake_home)}),
        ("sync", dm._op_sync_files, {"files": [str(fake_home / "x.py")]}),
        ("sync", dm._op_sync_since, {"git_ref": "HEAD~1"}),
        ("ingest-gmd", dm._op_ingest_gmd, {"targets": [str(fake_home)]}),
        ("ingest-gmd", dm._op_ingest_gmd_start, {"targets": [str(fake_home)]}),
    ]:
        with pytest.raises(RuntimeError, match="memory-only global store"):
            fn(d, args)


def test_daemon_ingest_gmd_as_memory_passes_the_guard(fake_home):
    # `--as-memory` is the sanctioned write shape for the global store; the
    # guard must not fire. Empty target dir → clean early return.
    d = SimpleNamespace(memory_only=True, root=fake_home / ".refmatrix")
    empty = fake_home / "gmd-empty"
    empty.mkdir()
    out = dm._op_ingest_gmd(d, {"targets": [str(empty)], "as_memory": True})
    assert out["files"] == 0
