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

pytest.importorskip("lance")

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
