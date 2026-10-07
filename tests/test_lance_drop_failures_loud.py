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
