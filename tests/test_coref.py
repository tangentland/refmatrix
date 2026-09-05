"""Pronoun deref: resolver behavior, sidecar roundtrip, pair inventory, and
the embed-time substitution that must never persist resolved text."""
from __future__ import annotations

import pytest

from refmatrix import coref
from refmatrix.store import Store


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / ".refmatrix")
    s.init()
    yield s
    s.close()


# ---- resolver ----------------------------------------------------------

def test_person_pronoun_binds_to_nearest_proper_noun():
    text = "Marcus visited the office. He signed the lease."
    res = coref.resolve_text(text)
    assert [(r.pronoun, r.antecedent) for r in res] == [("He", "Marcus")]
    # offset indexes the original text exactly
    r = res[0]
    assert text[r.offset:r.offset + len(r.pronoun)] == "He"


def test_neuter_pronoun_needs_a_recurring_noun():
    # `gate` recurs -> `it` binds; `lease` is incidental (df=1) -> no bind.
    text = ("The gate fired early. The gate skipped the file. "
            "It never logged anything.")
    res = coref.resolve_text(text)
    assert ("It", "gate") in [(r.pronoun, r.antecedent) for r in res]


def test_window_expiry_leaves_pronoun_unresolved():
    filler = "Nothing here. " * 5
    text = "Marcus arrived. " + filler + "He left."
    assert coref.resolve_text(text, window=3) == []


def test_competing_candidates_halve_confidence():
    solo = coref.resolve_text("Marcus spoke. He nodded.")
    pair = coref.resolve_text("Marcus met Elena. He nodded.")
    assert solo[0].confidence > pair[0].confidence


def test_sentence_opener_needs_recurrence_to_be_a_candidate():
    # `Yesterday` opens the sentence and never recurs -> not a candidate.
    res = coref.resolve_text("Yesterday everything broke. He was blamed.")
    assert res == []


# ---- apply -------------------------------------------------------------

def test_apply_substitutes_back_to_front_and_skips_drift():
    text = "Marcus arrived. He sat. He spoke."
    res = coref.resolve_text(text)
    out = coref.apply(text, res)
    assert out == "Marcus arrived. Marcus sat. Marcus spoke."
    # Drifted text: offsets no longer match -> substitution declines, no crash.
    assert coref.apply("completely different text", res) == \
        "completely different text"


# ---- sidecar roundtrip -------------------------------------------------

def test_save_load_coref_roundtrip(store):
    eid = store.upsert_entity(kind="memory", name="m1")
    res = coref.resolve_text("Marcus arrived. He sat.")
    assert store.save_coref(eid, res) == 1
    assert store.load_coref(eid) == res
    # replace-not-accrete
    store.save_coref(eid, [])
    assert store.load_coref(eid) == []


# ---- pair inventory ----------------------------------------------------

def test_compile_pairs_filters_hapax_and_keeps_postings(store):
    common = "the sentence transformer model loads the sentence transformer"
    ids = [store.add_memory(name=f"m{i}", content=common, mtype="note")
           for i in range(3)]
    store.add_memory(name="solo", content="a unique quantum banana pancake",
                     mtype="note")
    r = store.compile_pairs(min_df=3)
    assert r["kept"] >= 1
    assert r["hapax"] >= 1
    docs = store.pair_docs("sentence_transformer")
    assert set(ids) <= set(docs)
    # hapax pair from the solo doc must not survive
    assert store.pair_docs("banana_pancake") == []
