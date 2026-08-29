"""Authored docstrings outrank generated bodies, whatever the ingest order.

`entities` upserts with `tldr = COALESCE(excluded.tldr, entities.tldr)`, so a
non-null write always wins and pass ORDER decided which body the embeddings
were built from: a tldr-warm after ingest replaced docstrings with generated
summaries, an ingest after tldr-warm reversed it, and nothing recorded which
kind of body a row held.

`_ingest_tldr_metadata` now passes None where a body already exists, which
makes COALESCE preserve it — gap-fill by construction rather than by luck.
"""
from __future__ import annotations

import json

import pytest


@pytest.fixture
def tree(tmp_path):
    """A module with one documented function and one bare one, plus a tldr
    cache offering a generated body for BOTH."""
    (tmp_path / ".tldr" / "cache" / "semantic").mkdir(parents=True)
    f = tmp_path / "mod.py"
    f.write_text(
        '"""Module body."""\n\n'
        'def go(x):\n    """AUTHORED docstring."""\n    return x\n\n'
        'def nodoc(y):\n    return y\n'
    )
    (tmp_path / ".tldr" / "cache" / "semantic" / "metadata.json").write_text(
        json.dumps({"units": [
            {"qualified_name": "mod.py::go", "file": "mod.py", "name": "go",
             "unit_type": "function", "signature": "GENERATED go"},
            {"qualified_name": "mod.py::nodoc", "file": "mod.py",
             "name": "nodoc", "unit_type": "function",
             "signature": "GENERATED nodoc"},
        ]})
    )
    return tmp_path, f


@pytest.fixture
def store(tmp_path):
    from refmatrix.store import Store

    s = Store(tmp_path / ".rmx")
    s.init()
    yield s
    s.close()


def _bodies(s):
    return dict(s._connect().execute(
        "SELECT name, coalesce(tldr,'') FROM entities WHERE kind='code'"
    ).fetchall())


@pytest.mark.parametrize("semantic_first", [True, False])
def test_docstring_wins_in_either_order(store, tree, semantic_first):
    from refmatrix.ingest import _ingest_python_semantics, _ingest_tldr_metadata

    root, f = tree
    if semantic_first:
        _ingest_python_semantics(store, f, root)
        _ingest_tldr_metadata(store, root)
    else:
        _ingest_tldr_metadata(store, root)
        _ingest_python_semantics(store, f, root)

    b = _bodies(store)
    assert b["mod.py::go"] == "AUTHORED docstring.", \
        "a generated body must never replace an authored one"
    assert b["mod.py::nodoc"] == "GENERATED nodoc", \
        "tldr must still gap-fill a unit that has no docstring"
    assert b["mod.py"] == "Module body.", "file keeps its module docstring"


def test_entities_with_bodies_reports_only_non_empty(store):
    from refmatrix.ingest import _entities_with_bodies

    store.upsert_entity(kind="code", name="has.py", tldr="a body")
    store.upsert_entity(kind="code", name="bare.py")
    store.upsert_entity(kind="code", name="empty.py", tldr="")
    got = _entities_with_bodies(store, ["has.py", "bare.py", "empty.py"])
    assert got == {"has.py"}


def test_entities_with_bodies_chunks_large_inputs(store):
    """One entry per code unit runs to the thousands on a real tree, past what
    a single bound IN-list wants to carry."""
    from refmatrix.ingest import _entities_with_bodies

    names = [f"f{i}.py" for i in range(2000)]
    for n in names[:5]:
        store.upsert_entity(kind="code", name=n, tldr="body")
    assert _entities_with_bodies(store, names) == set(names[:5])


def test_empty_input_is_a_noop(store):
    from refmatrix.ingest import _entities_with_bodies

    assert _entities_with_bodies(store, []) == set()
