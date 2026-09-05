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


# ---- ingest wiring -----------------------------------------------------

def test_as_memory_ingest_emits_coref_linkage(store, tmp_path, monkeypatch):
    """RMX_INGEST_COREF=1 on the as-memory path must store resolutions AND
    emit the `coref` linkage — the wiring the shadowed-import bug broke while
    every resolver unit test stayed green."""
    monkeypatch.setenv("RMX_INGEST_COREF", "1")
    from refmatrix.ingest_gmd import ingest_gmd_paths
    md = tmp_path / "note.md"
    md.write_text(
        "# Note\n\nMarcus fixed the gate. He also rewrote the gate check. "
        "He documented everything.\n")
    ingest_gmd_paths(store, [md], lenient=True, as_memory=True,
                     project_root=tmp_path)
    row = store.get_entity("memory", "note.md")
    assert row is not None
    res = store.load_coref(row.id)
    assert res, "resolutions were not persisted"
    assert {r.antecedent for r in res} == {"Marcus"}
    lid = store.get_linkage_id("coref")
    n = store._connect().execute(
        "SELECT count(*) FROM entity_links WHERE linkage_id=?", (lid,)
    ).fetchone()[0]
    assert n >= 1, "coref linkage carries no bits"


# ---- cross-doc resolution ----------------------------------------------

def test_initial_unresolved_flags_doc_opening_pronouns():
    # "He" opens the doc with no prior antecedent -> cross-doc candidate.
    text = "He went back about the crown. The dentist was firm."
    pend = coref.initial_unresolved(text)
    assert [p for _o, p in pend] == ["He"]
    # A doc that introduces its referent first has nothing pending.
    assert coref.initial_unresolved("Marcus went in. He sat.") == []


def test_doc_antecedent_prefers_recurring_person():
    text = "Marcus called. Marcus waited. The office was closed."
    res = coref.resolve_text(text)
    assert coref.doc_antecedent(res, text) == "Marcus"


def test_cross_doc_link_binds_via_pair_neighbor(store):
    # Doc A establishes Marcus + a distinctive shared vocabulary.
    shared = ("Marcus scheduled the crown fitting. Marcus asked the "
              "endodontist about the crown fitting appointment.")
    a = store.add_memory(name="sessionA", content=shared, mtype="note")
    # Doc B opens with an unresolved pronoun and repeats the shared pairs,
    # so pair_index makes A its neighbor.
    b = store.add_memory(
        name="sessionB",
        content=("He returned about the crown fitting. The crown fitting "
                 "appointment ran long."),
        mtype="note")
    store.compile_pairs(min_df=2)
    r = store.link_cross_doc_coref(min_shared=2)
    assert r["linked"] >= 1
    res_b = store.load_coref(b)
    assert any(x.antecedent == "Marcus" for x in res_b), \
        "cross-doc pronoun did not bind to the neighbor's referent"
    # coref postings now let content_rank reach B by a term it never contains.
    import os
    os.environ["RMX_BOOST_COREF"] = "1.0"
    try:
        hits = dict(store.content_rank(["marcus"], limit=10))
    finally:
        os.environ.pop("RMX_BOOST_COREF", None)
    assert b in hits, "coref postings did not grow the candidate set"
    assert b not in dict(store.content_rank(["marcus"], limit=10)), \
        "boost=off should NOT surface B (proves the postings are gated)"
