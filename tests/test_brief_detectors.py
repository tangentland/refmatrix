"""`rmx memory brief` detectors — what the corpus knows, and what it lacks.

RED first for task 8.1 (plan-8). `memory compile` says what the store HAS;
nothing said what it LACKS, and every coverage failure this project hit was
invisible from inside the store until a benchmark or an audit went looking:
43-83% of entities carrying no terms, 179 docs stranded by an mtime gate, a
helix log too self-suppressed to decide anything.

A brief is a DERIVED row over signal that already exists. The contract these
tests enforce:

  * Every brief carries `evidence` — entity ids a reader can resolve. A brief
    with no evidence is a bug, and the constructor refuses it. That is the one
    rule that keeps this a diagnostic rather than a generator of plausible
    sentences.
  * Detectors are deterministic, and their thresholds are parameters. A fixture
    driven to two different outcomes by two different thresholds proves the
    knob is real rather than decorative.
  * Operational rows (session/*, digest/*) never enter. They are per-session
    artifacts, not knowledge, and they are numerous enough to dominate every
    class. `consolidate` already excludes them with a constant and a regex, and
    `brief` must REUSE those rather than redeclare them — the same junk-token
    bug appeared at four call sites because each one grew its own copy.
  * Skips are counted. `feedback_no_silent_failures` applies here: an
    unembedded or unreadable row is reported, never quietly dropped.
"""
from __future__ import annotations

import numpy as np
import pytest

from refmatrix import brief, consolidate
from refmatrix.store import Store

pytest.importorskip("lance")

PART = "memory-proj"
DIM = 8


def _unit(*components: float) -> np.ndarray:
    v = np.zeros(DIM, dtype="float32")
    for i, c in enumerate(components):
        v[i] = c
    return v / (np.linalg.norm(v) or 1.0)


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("RMX_BACKEND", "sqlite")
    root = tmp_path / "proj" / ".refmatrix"
    root.mkdir(parents=True)
    s = Store(root)
    s.init()
    yield s
    s.close()


# ── the evidence contract ──────────────────────────────────────────────────

def test_a_brief_without_evidence_cannot_be_constructed():
    """The rule that keeps this a diagnostic and not a sentence generator."""
    with pytest.raises(ValueError):
        brief.Brief(cls="singleton", label="x", finding="y", evidence=[])


def test_a_brief_keeps_its_evidence_ids_and_its_class():
    b = brief.Brief(cls="singleton", label="x", finding="y", evidence=[7, 9])
    assert b.evidence == [7, 9]
    assert b.cls == "singleton"


# ── corroborated ───────────────────────────────────────────────────────────

def _cluster(label, members, ids):
    return {"label": label, "size": len(members),
            "members": [{"id": ids[m], "name": m, "mtype": "project"}
                        for m in members],
            "evidence": []}


def test_corroborated_fires_on_a_subject_spanning_several_dates(store):
    ids = {n: i for i, n in enumerate(["a", "b", "c", "d"], start=100)}
    plan = {"clusters": [_cluster("daemon-writes", ["a", "b", "c", "d"], ids)],
            "unclustered": [], "stats": {}}
    dates = {100: 1.0, 101: 200000.0, 102: 400000.0, 103: 600000.0}
    out = brief.corroborated(plan, dates=dates, min_members=3, min_dates=3)
    assert [b.label for b in out] == ["daemon-writes"]
    assert sorted(out[0].evidence) == [100, 101, 102, 103]


def test_corroborated_does_not_fire_when_every_member_lands_on_one_day(store):
    """Four memories written in one sitting are one observation, not four."""
    ids = {n: i for i, n in enumerate(["a", "b", "c", "d"], start=100)}
    plan = {"clusters": [_cluster("daemon-writes", ["a", "b", "c", "d"], ids)],
            "unclustered": [], "stats": {}}
    same_day = {i: 1000.0 + i for i in ids.values()}
    assert brief.corroborated(plan, dates=same_day, min_members=3,
                              min_dates=3) == []


def test_corroborated_thresholds_are_real_knobs(store):
    ids = {n: i for i, n in enumerate(["a", "b"], start=100)}
    plan = {"clusters": [_cluster("small", ["a", "b"], ids)],
            "unclustered": [], "stats": {}}
    dates = {100: 1.0, 101: 400000.0}
    assert brief.corroborated(plan, dates=dates, min_members=3, min_dates=2) == []
    assert len(brief.corroborated(plan, dates=dates, min_members=2,
                                  min_dates=2)) == 1


# ── singleton ──────────────────────────────────────────────────────────────

def test_singleton_fires_on_a_memory_that_joined_no_cluster(store):
    plan = {"clusters": [], "unclustered": ["lonely-note"], "stats": {}}
    out = brief.singleton(plan, name_to_id={"lonely-note": 42})
    assert [b.label for b in out] == ["lonely-note"]
    assert out[0].evidence == [42]


def test_singleton_does_not_fire_on_a_clustered_memory(store):
    ids = {"a": 1, "b": 2}
    plan = {"clusters": [_cluster("pair", ["a", "b"], ids)],
            "unclustered": [], "stats": {}}
    assert brief.singleton(plan, name_to_id=ids) == []


def test_a_singleton_whose_id_cannot_be_resolved_is_counted_not_emitted(store):
    """An unresolvable name would produce a brief with no evidence."""
    plan = {"clusters": [], "unclustered": ["ghost"], "stats": {}}
    out, skipped = brief.singleton(plan, name_to_id={}, count_skips=True)
    assert out == []
    assert skipped == 1


# ── contradicted ───────────────────────────────────────────────────────────

def test_contradicted_fires_on_an_unresolved_pair(store):
    with store.with_partition(PART):
        a = store.add_memory("claim-a", "the fix is X", mtype="project")
        b = store.add_memory("claim-b", "the fix is not X", mtype="project")
        store.link("contradicts", a, b)
        out = brief.contradicted(store)
    assert len(out) == 1
    assert sorted(out[0].evidence) == sorted([a, b])


def test_contradicted_does_not_fire_when_one_side_is_superseded(store):
    """A contradiction someone already resolved is history, not a finding."""
    with store.with_partition(PART):
        a = store.add_memory("claim-a", "the fix is X", mtype="project")
        b = store.add_memory("claim-b", "the fix is not X", mtype="project")
        store.link("contradicts", a, b)
        store.add_linkage_type("supersedes")
        store.link("supersedes", b, a)
        out = brief.contradicted(store)
    assert out == []


def test_contradicted_ignores_operational_rows(store):
    with store.with_partition(PART):
        a = store.add_memory("session-1", "a handoff", mtype="session/digest")
        b = store.add_memory("session-2", "another handoff", mtype="session/digest")
        store.link("contradicts", a, b)
        out = brief.contradicted(store)
    assert out == []


# ── orphan-concept ─────────────────────────────────────────────────────────

def test_orphan_concept_fires_on_a_term_talked_about_but_never_pinned_down(store):
    with store.with_partition(PART):
        c = store.add_concept("fast-exit")
        for i in range(4):
            m = store.add_memory(f"m{i}", f"mentions fast-exit {i}", mtype="project")
            store.link("mentions", c, m)
        out = brief.orphan_concept(store, min_mentions=3)
        # add_concept canonicalises the name; the brief must carry whatever
        # the store stored, not the string the caller typed.
        canonical = store.get_entity_by_id(c).name
    assert [b.label for b in out] == [canonical]
    assert len(out[0].evidence) >= 1


def test_orphan_concept_does_not_fire_when_something_defines_the_term(store):
    with store.with_partition(PART):
        c = store.add_concept("fast-exit")
        for i in range(4):
            m = store.add_memory(f"m{i}", f"mentions fast-exit {i}", mtype="project")
            store.link("mentions", c, m)
        anchor = store.add_memory("spec", "fast-exit is defined thus", mtype="project")
        store.link("defines", c, anchor)
        out = brief.orphan_concept(store, min_mentions=3)
    assert out == []


def test_orphan_concept_threshold_is_a_real_knob(store):
    with store.with_partition(PART):
        c = store.add_concept("rare-term")
        for i in range(2):
            m = store.add_memory(f"m{i}", "mentions rare-term", mtype="project")
            store.link("mentions", c, m)
        assert brief.orphan_concept(store, min_mentions=3) == []
        assert len(brief.orphan_concept(store, min_mentions=2)) == 1


# ── the shared exclusions ──────────────────────────────────────────────────

def test_brief_reuses_consolidates_exclusion_constants_rather_than_copying_them():
    """The same junk-token bug appeared at four call sites because each grew
    its own copy of the list. One definition, imported."""
    assert brief.EXCLUDE_MTYPES is consolidate.DEFAULT_EXCLUDE_MTYPES
    assert brief.OPERATIONAL_RE is consolidate._OPERATIONAL_RE


# ── the whole run ──────────────────────────────────────────────────────────

def test_compile_brief_returns_every_class_and_a_reconciled_skip_count(store):
    with store.with_partition(PART):
        c = store.add_concept("orphan-term")
        for i in range(4):
            m = store.add_memory(f"om{i}", "about orphan-term", mtype="project")
            store.link("mentions", c, m)
        a = store.add_memory("claim-a", "X", mtype="project")
        b = store.add_memory("claim-b", "not X", mtype="project")
        store.link("contradicts", a, b)
        result = brief.compile_briefs(store, min_mentions=3)
    classes = {b.cls for b in result["briefs"]}
    assert "orphan-concept" in classes
    assert "contradicted" in classes
    assert "skipped" in result["stats"]
    assert isinstance(result["stats"]["skipped"], int)


def test_every_emitted_brief_has_evidence_that_resolves_to_a_real_row(store):
    with store.with_partition(PART):
        c = store.add_concept("orphan-term")
        for i in range(4):
            m = store.add_memory(f"om{i}", "about orphan-term", mtype="project")
            store.link("mentions", c, m)
        result = brief.compile_briefs(store, min_mentions=3)
        for b in result["briefs"]:
            assert b.evidence, b
            for eid in b.evidence:
                assert store.get_entity_by_id(eid) is not None, (b, eid)


def test_operational_memories_never_appear_in_any_class(store):
    with store.with_partition(PART):
        c = store.add_concept("session-term")
        for i in range(5):
            m = store.add_memory(f"session-{i}", "a handoff", mtype="session/digest")
            store.link("mentions", c, m)
        result = brief.compile_briefs(store, min_mentions=2)
    for b in result["briefs"]:
        for eid in b.evidence:
            ent = store.get_entity_by_id(eid)
            assert not str(ent.name).startswith("session-"), b
