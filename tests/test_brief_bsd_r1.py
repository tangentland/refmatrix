"""Regressions for ch-bsd plans-7-10 round 1 (bsd-plan7-10-r1-399d0a3).

Every test here reproduces a finding the audit made against a REAL daemon or the
live read replica. They are written to fail on the code as shipped.
"""
from __future__ import annotations

import json

import numpy as np
import pytest
from click.testing import CliRunner

from refmatrix import brief, terms
from refmatrix.cli import main as cli_main
from refmatrix.store import Store

pytest.importorskip("lance")
PART = "memory-proj"


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("RMX_BACKEND", "sqlite")
    root = tmp_path / "proj" / ".refmatrix"
    root.mkdir(parents=True)
    s = Store(root)
    s.init()
    yield s
    s.close()


# ── #b-1: --gmd crashes on dicts off the wire ──────────────────────────────

def test_render_gmd_accepts_the_dicts_the_daemon_actually_returns():
    """The daemon serialises via `as_dict()`; the verb returns dicts over the
    wire; the CLI handed them straight to render_gmd, which indexed `b.cls`."""
    wire = [{"class": "singleton", "label": "lonely", "finding": "touched once",
             "evidence": [4], "detail": {}, "mtype": "brief/singleton"}]
    out = brief.render_gmd(wire, names={4: "lonely"})
    assert "singleton" in out
    assert "[[lonely]]" in out


def test_cli_gmd_flag_runs_end_to_end(monkeypatch):
    """No test invoked --gmd through the CLI; it died on every real call."""
    def fake_memory(root, action, **kw):
        return {"briefs": [{"class": "singleton", "label": "x",
                            "finding": "f", "evidence": [1], "detail": {},
                            "mtype": "brief/singleton"}],
                "stats": {"skipped": 0, "briefs": 1, "partition": "p"}}

    from refmatrix import verbs
    monkeypatch.setattr(verbs, "memory", fake_memory)
    res = CliRunner().invoke(cli_main, ["memory", "brief", "--gmd"])
    assert res.exit_code == 0, res.output + str(res.exception)
    assert "gmd:" in res.output


# ── #b-3: the shared stoplist, sixth site ──────────────────────────────────

def test_orphan_concept_drops_stopwords(store):
    """The top brief on the live replica was the word `the`."""
    with store.with_partition(PART):
        junk = store.add_concept("the")
        real = store.add_concept("fast-exit")
        for i in range(6):
            m = store.add_memory(f"m{i}", "body", mtype="project")
            store.link("mentions", junk, m)
            store.link("mentions", real, m)
        labels = [b.label for b in brief.orphan_concept(store, min_mentions=3)]
    assert "the" not in [l.lower() for l in labels], labels
    assert any("fast" in l for l in labels), labels


def test_brief_uses_the_shared_stoplist_by_identity():
    """One definition, imported — the whole point of the module docstring."""
    assert brief.STOPWORDS is terms.STOPWORDS


def test_orphan_concept_drops_memory_id_shaped_names(store):
    """`project_daemon_sigabrt_diagnosed` surfaced as a 'concept'."""
    with store.with_partition(PART):
        c = store.add_concept("project_daemon_sigabrt_diagnosed")
        for i in range(5):
            m = store.add_memory(f"n{i}", "body", mtype="project")
            store.link("mentions", c, m)
        labels = [b.label for b in brief.orphan_concept(store, min_mentions=3)]
    assert labels == [], labels


# ── #b-4: saved briefs re-enter the corpus ─────────────────────────────────

def test_saved_briefs_are_excluded_from_the_next_run(store):
    with store.with_partition(PART):
        c = store.add_concept("orphan_term")
        for i in range(5):
            m = store.add_memory(f"k{i}", "about orphan_term", mtype="project")
            store.link("mentions", c, m)
        before = brief.compile_briefs(store, min_mentions=3)["stats"]["memories"]
        # simulate --save writing its own output back
        store.add_memory("brief-orphan-concept-orphan_term", "finding",
                         mtype="brief/orphan-concept")
        after = brief.compile_briefs(store, min_mentions=3)["stats"]["memories"]
    assert after == before, "a saved brief re-entered its own corpus"


def test_brief_mtypes_are_in_the_exclusion_set():
    assert any("brief" in p for p in brief.EXCLUDE_MTYPES), brief.EXCLUDE_MTYPES


# ── #b-5: the GMD round trip must recover evidence ─────────────────────────

def test_parse_gmd_recovers_evidence_ids():
    """`evidence` is 'the whole contract' per the module docstring, and was
    written into the doc and never read back. The round-trip test smuggled a
    literal `[1, 2]` back in."""
    b = brief.Brief(cls="contradicted", label="a vs b", finding="unresolved",
                    evidence=[11, 22])
    doc = brief.render_gmd([b], names={11: "mem-a", 22: "mem-b"})
    back = brief.parse_gmd(doc)
    assert back[0]["evidence"] == [11, 22], back


def test_parse_gmd_recovers_an_unresolved_evidence_id():
    b = brief.Brief(cls="singleton", label="x", finding="f", evidence=[7, 99])
    doc = brief.render_gmd([b], names={7: "known"})
    assert brief.parse_gmd(doc)[0]["evidence"] == [7, 99]


def test_round_trip_needs_no_smuggled_literal():
    briefs = [brief.Brief(cls="singleton", label="s", finding="f", evidence=[3])]
    names = {3: "mem-c"}
    once = brief.render_gmd(briefs, names=names)
    rebuilt = [brief.Brief(cls=d["class"], label=d["label"],
                           finding=d["finding"], evidence=d["evidence"])
               for d in brief.parse_gmd(once)]
    assert brief.render_gmd(rebuilt, names=names) == once


# ── #m-17: an unrecognised class must not be silent ────────────────────────

def test_an_unknown_brief_class_is_reported_not_silently_empty(store):
    with pytest.raises(ValueError) as e:
        brief.compile_briefs(store, classes=["bogus-class"])
    assert "bogus-class" in str(e.value)


# ── #b-2: contradicted must fire on the endpoints real data has ────────────

def test_contradicted_fires_on_concept_anchor_endpoints(store):
    """On the live replica 54 of 59 `contradicts` endpoints are CONCEPT nodes
    (GMD `#anchor` ids), not memory rows — so the class scored 0 on 41 pairs
    and the CLI blamed 'unresolvable ids' (ch-bsd r1 #b-2)."""
    with store.with_partition(PART):
        a = store.add_concept("adr-0042#old-spec")
        b = store.add_concept("adr-0087#zone-class")
        store.link("contradicts", a, b)
        out = brief.contradicted(store)
    assert len(out) == 1, out
    assert sorted(out[0].evidence) == sorted([a, b])


def test_contradicted_still_honours_supersedes_on_concept_endpoints(store):
    with store.with_partition(PART):
        a = store.add_concept("adr-0042#old-spec")
        b = store.add_concept("adr-0087#zone-class")
        store.link("contradicts", a, b)
        store.add_linkage_type("supersedes")
        store.link("supersedes", b, a)
        assert brief.contradicted(store) == []


def test_contradicted_reports_a_real_skip_reason_not_a_wrong_one(store):
    """An endpoint in neither the memory set nor the entity table is the only
    thing that should count as a skip."""
    with store.with_partition(PART):
        a = store.add_concept("x#one")
        b = store.add_concept("y#two")
        store.link("contradicts", a, b)
        out, skipped = brief.contradicted(store, count_skips=True)
    assert skipped == 0, "a resolvable concept pair must not be counted a skip"
    assert len(out) == 1
