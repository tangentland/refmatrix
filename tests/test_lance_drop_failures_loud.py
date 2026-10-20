"""ch-bsd r7 #s-2: a failed vector delete is LOUD and COUNTED, never `pass`.

Since bug-085 (3b1b544) `_drop_lance_for_purge_batch` is the only vector delete
on file re-sync, concept fold, noise prune and bulk memory forget. It swallowed
every failure (`except Exception: pass`) and read ANY ImportError as "lance not
installed" — under `python -I`, `import lance` fails on a missing transitive
dependency (`typing_inspection`), and every delete would have been skipped
without a word, leaving orphan vectors for purged ids (559 of 5,495 in this
repo's `code.lance`, cause unproven).

Real Lance, real broken dataset: a `code.lance` directory that is not a Lance
dataset makes `lance.dataset()` raise.
"""
from __future__ import annotations

import builtins

import pytest

import importlib.util

# Skip ONLY when lance is not installed; an installed-but-broken lance fails
# here instead of skipping (ch-bsd r8 #s-4).
if importlib.util.find_spec("lance") is None:
    pytest.skip("lance not installed", allow_module_level=True)
import lance  # noqa: E402,F401

from refmatrix import sync as sync_mod
from refmatrix.store import Store


def _store(tmp_path):
    s = Store(tmp_path / ".refmatrix")
    s.init()
    return s


def _break(s: Store, kind: str):
    d = s.root / "vectors" / s._partition_name / f"{kind}.lance"
    d.mkdir(parents=True)
    (d / "not-a-manifest").write_text("x")


def test_a_failed_batch_delete_is_printed_and_counted(tmp_path, capsys):
    s = _store(tmp_path)
    _break(s, "code")

    s._drop_lance_for_purge_batch({"code": [1, 2, 3]})

    err = capsys.readouterr().err
    assert "code" in err and "3" in err and "embed --gc" in err, err
    assert s.vector_delete_failures == 3


def test_a_broken_lance_import_is_not_read_as_not_installed(tmp_path, capsys, monkeypatch):
    s = _store(tmp_path)
    (s.root / "vectors" / s._partition_name / "code.lance").mkdir(parents=True)
    real_import = builtins.__import__

    def broken(name, *a, **k):
        if name == "lance":
            raise ModuleNotFoundError("No module named 'typing_inspection'",
                                      name="typing_inspection")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", broken)
    s._drop_lance_for_purge_batch({"code": [7]})
    s._drop_lance_for_purge(8, "code")
    monkeypatch.setattr(builtins, "__import__", real_import)

    err = capsys.readouterr().err
    assert "typing_inspection" in err, err
    assert s.vector_delete_failures == 2


def test_the_single_id_delete_is_loud_too(tmp_path, capsys):
    s = _store(tmp_path)
    _break(s, "memory")

    assert s._drop_lance_for_purge(5, "memory") is False

    assert "memory" in capsys.readouterr().err
    assert s.vector_delete_failures == 1


def test_sync_prune_and_fold_report_the_failures(tmp_path, capsys):
    s = _store(tmp_path)
    _break(s, "code")
    _break(s, "concept")
    src = tmp_path / "a.py"
    src.write_text("def f():\n    return 1\n")
    sync_mod.sync_files(s, [str(src)], project_root=tmp_path)
    src.write_text("def f():\n    return 2\n")

    rep = sync_mod.sync_files(s, [str(src)], project_root=tmp_path)
    assert rep["vector_delete_failed"] >= 1, rep

    ents = [s.upsert_entity(kind="code", name=f"f{i}.py") for i in range(20)]
    c = s.add_namespaced_concept("keyword", "rare")
    s.link("mentions", c, ents[0])
    out = s.prune_noise(min_df=2, max_df_ratio=0.25, drop=True)
    assert out["vector_delete_failed"] == 1, out

    s.add_memory(name="dup", content="x")
    s.upsert_entity(kind="concept", name="dup")
    res = s.fold_concept_dups()
    assert res["vector_delete_failed"] == 1, res


# ---- ch-bsd r8 #s-1: the count reaches every caller, memory paths included --

def test_the_forget_paths_and_vacuum_return_the_count(tmp_path, capsys):
    s = _store(tmp_path)
    _break(s, "memory")
    _break(s, "concept")
    m1 = s.add_memory(name="m1", content="x")
    s.add_memory(name="m2", content="y")

    r = s.bulk_forget_memories(ids=[m1])
    assert r["vector_delete_failed"] == 1, r

    r = s.forget_by_selector(names=["m2"])
    assert r["vector_delete_failed"] == 1, r

    s.add_concept("lonely")          # a concept with no links: vacuum drops it
    r = s.vacuum()
    assert r["concepts_dropped"] >= 1 and r["vector_delete_failed"] >= 1, r


def test_rmx_forget_prints_the_failure_on_the_callers_terminal(tmp_path, monkeypatch):
    """End to end through the real CLI on a store with a broken dataset."""
    from click.testing import CliRunner

    from refmatrix import cli as cli_mod

    s = _store(tmp_path)
    _break(s, "concept")
    s.add_concept("doomed")
    s.close()
    monkeypatch.setattr(cli_mod, "_root", lambda: tmp_path / ".refmatrix")
    monkeypatch.setattr("refmatrix.daemon.ping", lambda *a, **k: False)

    r = CliRunner().invoke(cli_mod.main, ["forget", "doomed", "-y"])

    assert r.exit_code == 0, r.output
    assert "rmx forget: 1 vector delete(s) FAILED" in r.stderr, r.stderr


# ---- ch-bsd r9 #s-2: every render site and the flush line, pinned ----------

class _ReportingStore:
    """The store boundary for the CLI render sites: each method returns what
    the real store/daemon op returns, with 2 failed vector deletes."""
    R = {"vector_delete_failed": 2}

    def prune_noise(self, **k):
        return {"dropped": 1, "kept": 0, "total_seen": 1, "min_df": 2, "max_df": 9,
                "marked": 0, "unmarked": 0, **self.R}

    def vacuum(self):
        return {"concepts_dropped": 1, "files_purged": 0, **self.R}

    def fold_concept_dups(self, dry_run=False):
        return {"folded": 1, "edges_migrated": 0, "dry_run": False, **self.R}

    def bulk_forget_memories(self, **k):
        if k.get("dry_run"):
            return {"ids": [1], "by_mtype": {"note": 1}, "dry_run": True}
        return {"forgotten": 1, "ids": [1], "by_mtype": {}, "dry_run": False, **self.R}

    def untrack_by_path(self, **k):
        if k.get("dry_run"):
            return {"paths": ["x"], "files_untracked": 1, "entities_purged": 1}
        return {"paths": ["x"], "files_untracked": 1, "entities_purged": 1, **self.R}


@pytest.mark.parametrize("argv,what", [
    (["prune-noise", "--drop"], "prune-noise"),
    (["vacuum"], "vacuum"),
    (["memory", "dedup"], "memory dedup"),
    (["memory", "bulk-forget", "--id", "1", "-y"], "memory bulk-forget"),
    (["untrack", "--like", "x%", "-y"], "untrack"),
])
def test_each_cli_render_site_prints_the_count(tmp_path, monkeypatch, argv, what):
    from click.testing import CliRunner

    from refmatrix import cli as cli_mod

    # NEVER a live daemon: with `_root` unpatched, `memory bulk-forget`
    # reached this project's live daemon socket (2026-10-07, a dry-run
    # preview; nothing was deleted). Every path here is the local store.
    monkeypatch.setattr(cli_mod, "_root", lambda: tmp_path / ".refmatrix")
    monkeypatch.setattr("refmatrix.daemon.ping", lambda *a, **k: False)
    monkeypatch.setattr(cli_mod, "_store", lambda *a, **k: _ReportingStore())
    monkeypatch.setattr(cli_mod, "_memory_intent", lambda *a, **k: None, raising=False)
    r = CliRunner().invoke(cli_mod.main, argv)
    assert "2 vector delete(s) FAILED" in r.stderr, (argv, r.exit_code, r.output, r.stderr)


def test_the_daemon_sync_render_prints_the_count(tmp_path, monkeypatch):
    from click.testing import CliRunner

    from refmatrix import cli as cli_mod
    from refmatrix import daemon as daemon_mod

    f = tmp_path / "a.py"
    f.write_text("x = 1\n")
    monkeypatch.setattr(cli_mod, "_root", lambda: tmp_path / ".refmatrix")
    monkeypatch.setattr(daemon_mod, "ping", lambda *a, **k: True)
    monkeypatch.setattr(daemon_mod, "call", lambda root, op, args, **k: {
        "ok": True, "result": {"added": 0, "updated": 1, "purged": 0, "touched": 1,
                               "cancelled": False, "vector_delete_failed": 2}})
    r = CliRunner().invoke(cli_mod.main, ["sync", "--files", str(f)])
    assert "rmx sync: 2 vector delete(s) FAILED" in r.stderr, (r.output, r.stderr)


def test_memory_forget_carries_the_count_from_the_daemon(tmp_path, monkeypatch):
    """The count rides back in the VERB's result and reaches the caller's
    terminal. Task 3.4 routed `memory forget` through `verbs.memory` (the
    anti-drift rule), so the seam is the verb now, not the retired
    `cli._memory_daemon_call` + `daemon.ping` pair this test used to patch —
    patching those left the command dialling a real socket under pytest's
    tmp_path ("AF_UNIX path too long"). The recorder also pins that the
    command asks for `action="forget"` with the name it was given."""
    from click.testing import CliRunner

    from refmatrix import cli as cli_mod
    from refmatrix import verbs

    monkeypatch.setattr(cli_mod, "_root", lambda: tmp_path / ".refmatrix")
    # An explicit partition: the memory group's default-partition probe is not
    # what this test is about, and it would dial the same tmp socket.
    monkeypatch.setenv("RMX_PARTITION", "p")
    seen: list = []

    def recorder(root, action=None, **kw):
        seen.append((action, kw))
        return {"forgotten": True, "vector_delete_failed": 1}
    monkeypatch.setattr(verbs, "memory", recorder)
    r = CliRunner().invoke(cli_mod.main, ["memory", "forget", "m1", "--yes"])
    assert seen and seen[-1][0] == "forget" and seen[-1][1].get("name") == "m1", seen
    assert "rmx memory forget: 1 vector delete(s) FAILED" in r.stderr, (r.output, r.stderr)


def test_the_memory_forget_op_returns_the_count(tmp_path):
    import threading

    from refmatrix.daemon import _op_memory_forget

    s = _store(tmp_path)
    _break(s, "memory")
    s.add_memory(name="m1", content="x")

    class D:
        def __init__(self):
            self.store = s
            self._store_lock = threading.RLock()

        def _st(self):
            return self.store

        def _request_snapshot(self):
            pass

        def _log(self, m):
            pass

    out = _op_memory_forget(D(), {"name": "m1", "partition": s._partition_name})
    assert out == {"forgotten": True, "vector_delete_failed": 1}, out


def test_untrack_returns_the_count(tmp_path):
    s = _store(tmp_path)
    _break(s, "code")
    p = tmp_path / "a.py"
    p.write_text("x = 1\n")
    s.upsert_entity(kind="code", name="a.py", path=str(p))
    s.mark_tracked(str(p), p.stat().st_mtime)
    r = s.untrack_by_path(paths=[str(p)])
    assert r["vector_delete_failed"] == 1, r


def test_the_watch_flush_line_carries_the_count():
    from refmatrix.daemon import _watch_flush_line

    assert _watch_flush_line(3, 1, 1, 1, "", 0) == "watch flush: paths=3 +1 ~1 -1"
    assert _watch_flush_line(3, 1, 1, 1, " curator+1", 4).endswith(
        " curator+1 vector_delete_FAILED=4")
