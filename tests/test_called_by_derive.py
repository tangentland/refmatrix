"""`called_by` is the materialized inverse of `calls`.

The linkage was registered with inverse_of=calls and rendered with a "CALLED BY"
header, but the extractors never populated a unit's called_by field, so it had
0 rows tool-wide. Store.derive_called_by() reconstructs it from `calls` through
the `defines` bridge. These tests pin the derivation + idempotency directly on a
synthetic store (no ingest plumbing).
"""
from __future__ import annotations

from refmatrix.store import Store


def _setup(tmp_path):
    """Two functions: caller() calls callee(). Modeled exactly as the ingest
    passes write it — entity --defines--> bare concept, entity --calls-->
    callee bare concept."""
    s = Store(tmp_path / ".refmatrix")
    s.init()
    caller = s.upsert_entity("code", "mod.py::caller", path="/mod.py",
                             tldr="def caller(): ...")
    callee = s.upsert_entity("code", "mod.py::callee", path="/mod.py",
                             tldr="def callee(): ...")
    caller_bare = s.upsert_entity("concept", "caller")
    callee_bare = s.upsert_entity("concept", "callee")
    # defines: entity --defines--> its bare name
    s.bulk_link([
        ("defines", caller_bare, caller, 1.0),
        ("defines", callee_bare, callee, 1.0),
        # calls: caller entity --calls--> callee bare concept
        ("calls", callee_bare, caller, 1.0),
    ])
    return s, caller, callee, caller_bare, callee_bare


def _called_by_pairs(s: Store) -> set[tuple[int, int]]:
    lid = s.get_linkage_id("called_by")
    rows = s._connect().execute(
        "SELECT entity_id, concept_id FROM entity_links WHERE linkage_id=?",
        (lid,),
    ).fetchall()
    return {(r[0], r[1]) for r in rows}


def test_derive_called_by_inverts_calls(tmp_path):
    s, caller, callee, caller_bare, callee_bare = _setup(tmp_path)
    assert _called_by_pairs(s) == set()  # nothing before

    added = s.derive_called_by()
    assert added == 1
    # callee ENTITY is called_by the caller's bare concept.
    assert _called_by_pairs(s) == {(callee, caller_bare)}
    s.close()


def test_derive_called_by_is_idempotent(tmp_path):
    s, *_ = _setup(tmp_path)
    assert s.derive_called_by() == 1
    # Second run adds nothing (bit already present in the fragment).
    assert s.derive_called_by() == 0
    s.close()


def test_derive_called_by_noop_without_calls(tmp_path):
    s = Store(tmp_path / ".refmatrix")
    s.init()
    e = s.upsert_entity("code", "solo.py::f", path="/solo.py", tldr="def f(): 1")
    s.bulk_link([("defines", s.upsert_entity("concept", "f"), e, 1.0)])
    assert s.derive_called_by() == 0
    assert _called_by_pairs(s) == set()
    s.close()
