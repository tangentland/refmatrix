"""`Store.same_as_audit` — observability tripwire for identifier variant
unification.

`same_as` edges link a concept's surface variants (space / dash forms) to the
underscore canonical. The query path unifies via the `canonical_name` column,
not these edges, so their only risk is a silent over-merge — an edge whose two
endpoints have DIFFERENT canonical_names, meaning `canonicalize_name` fused
distinct identifiers. The audit reports growth (edge count + per-canonical
distribution) and flags any such divergent edge.
"""
from __future__ import annotations

import pytest

from refmatrix.store import Store


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / ".refmatrix")
    s.init()
    yield s
    s.close()


def test_same_as_audit_clean(store):
    # Each multi-word concept spawns space + dash variants linked via same_as.
    store.add_concept("foo bar")
    store.add_concept("baz qux quux")
    store.flush_fragments()

    out = store.same_as_audit()
    assert out["edges"] >= 2
    # Every edge unifies one identifier -> no over-merge.
    assert out["divergent_count"] == 0
    assert out["divergent"] == []
    # Variants-per-canonical is the bounded, ~2/concept shape.
    assert 2 in out["distribution"]


def test_same_as_audit_flags_over_merge(store):
    # Two genuinely distinct single-token concepts (different canonical_name).
    a = store.add_concept("alpha")
    b = store.add_concept("beta")
    # Forge an over-merge: a same_as edge across the two canonicals.
    store.link("same_as", a, b)
    store.flush_fragments()

    out = store.same_as_audit()
    assert out["divergent_count"] >= 1
    pairs = {(d["variant_canon"], d["canonical_canon"]) for d in out["divergent"]}
    assert ("alpha", "beta") in pairs


def test_same_as_audit_empty_store(store):
    out = store.same_as_audit()
    assert out["edges"] == 0
    assert out["divergent_count"] == 0
    assert out["distribution"] == {}
