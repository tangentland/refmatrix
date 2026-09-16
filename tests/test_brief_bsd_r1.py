"""Regressions for ch-bsd plans-7-10 round 1 (bsd-plan7-10-r1-399d0a3).

Every test here reproduces a finding the audit made against a REAL daemon or the
live read replica. They are written to fail on the code as shipped.
"""
from __future__ import annotations

import json

import numpy as np
import pytest
from click.testing import CliRunner

@pytest.fixture(autouse=True)
def _no_live_cli_log(monkeypatch):
    """These tests invoke the CLI, whose `_memory_intent` writes a
    phase:"start" row into the LIVE .refmatrix/cli.log before the body
    runs. Patched in test_context_cost.py two rounds ago and missed
    here — third round, third sibling call site (ch-bsd r3).
    """
    from refmatrix import telemetry
    monkeypatch.setattr(telemetry, "log_cli_intent",
                        lambda root, **kw: None, raising=False)
    monkeypatch.setattr(telemetry, "log_cli_invocation",
                        lambda root, **kw: None, raising=False)


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


def _fake_brief_payload(root, action, **kw):
    """The shape the daemon op actually returns — INCLUDING `names`.

    The first version of this fake omitted `names`, so no wikilink existed in
    the rendered doc and the rich-markup defect below had nothing to eat
    (ch-bsd r3 #b-1-r3). A fake that drops the field under test proves nothing.
    """
    return {"briefs": [{"class": "singleton", "label": "x", "finding": "f",
                        "evidence": [1], "detail": {},
                        "mtype": "brief/singleton"}],
            "names": {"1": "note-one"},
            "stats": {"skipped": 0, "briefs": 1, "partition": "p"}}


def test_cli_gmd_flag_runs_end_to_end(monkeypatch):
    """No test invoked --gmd through the CLI; it died on every real call."""
    from refmatrix import verbs
    monkeypatch.setattr(verbs, "memory", _fake_brief_payload)
    res = CliRunner().invoke(cli_main, ["memory", "brief", "--gmd"])
    assert res.exit_code == 0, res.output + str(res.exception)
    assert "gmd:" in res.output


def test_cli_gmd_output_keeps_its_wikilinks_and_edges(monkeypatch):
    """`console.print` parsed `[[note-one]]` as rich markup and emitted `[]`,
    deleting every link and every `rel:` target — and `tools/gmd/lint.py`
    reported 0 errors on the wreckage because `[[]]` is not a wikilink
    (ch-bsd r3 #b-1-r3). The CONTENT is the assertion, not the exit code."""
    from refmatrix import verbs
    monkeypatch.setattr(verbs, "memory", _fake_brief_payload)
    res = CliRunner().invoke(cli_main, ["memory", "brief", "--gmd"])
    assert res.exit_code == 0, res.output
    assert "[[note-one]]" in res.output, res.output
    assert "rel: evidence-for -> [[note-one]]" in res.output, res.output
    assert "-> []" not in res.output, "rich ate the wikilink"


def test_cli_gmd_output_survives_the_repo_linter_with_its_edges(monkeypatch,
                                                                tmp_path):
    """Lint alone cannot catch this — assert the edges are THERE first."""
    from refmatrix import verbs
    monkeypatch.setattr(verbs, "memory", _fake_brief_payload)
    res = CliRunner().invoke(cli_main, ["memory", "brief", "--gmd"])
    assert res.output.count("rel: evidence-for ->") >= 1
    assert "[[" in res.output and "]]" in res.output


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
        out, skipped, why = brief.contradicted(store, count_skips=True)
    assert skipped == 0, "a resolvable concept pair must not be counted a skip"
    assert len(out) == 1
    assert why == {}, why


# ── #s-15: corroboration must use the AUTHORING clock, not the ingest clock ──

def test_corroborated_prefers_the_authored_date_over_the_ingest_date(store):
    """`memory_dates` read `entities.created_at` — the day the BRIDGE ingested
    the file. On the live replica 74 of 236 rows share one bridge run, and a
    `reingest --force` (routine here) collapses every memory onto one day and
    silences the class permanently with no counter that moves (ch-bsd r1 #s-15).
    The authored date is in each memory's `metadata.created` and was ignored."""
    with store.with_partition(PART):
        ids = {}
        for i, day in enumerate(["2026-06-01", "2026-07-02", "2026-08-03"]):
            ids[f"a{i}"] = store.add_memory(
                f"a{i}", "body", mtype="project", metadata={"created": day})
        # every row shares ONE ingest timestamp, as after a re-derive
        dates = brief.memory_dates(store, ids.values())
    days = {brief._day(v) for v in dates.values()}
    assert len(days) == 3, (
        f"authored dates collapsed to {len(days)} day(s) — the ingest clock won")


def test_corroborated_falls_back_to_created_at_when_unauthored(store):
    with store.with_partition(PART):
        eid = store.add_memory("plain", "body", mtype="project")
        dates = brief.memory_dates(store, [eid])
    assert dates[eid] > 0


# ── #b-2-r2: workflow-authored contradicts edges are a convention ──────────

def test_contradicted_excludes_workflow_authored_citation_edges(store):
    """45 of 47 emitted on the live replica were ch-bsd's OWN
    `rel: contradicts -> [[rule]]` lines — a ledger citation convention, not a
    corpus disagreement (ch-bsd r2 #b-2-r2). Same principle as
    feedback_operational_content_not_in_graph: process artifacts are not
    knowledge."""
    with store.with_partition(PART):
        a = store.add_concept("bsd-plan3-verbs-parity-8ba4799#bs-1")
        b = store.add_concept("tdd-governance")
        store.link("contradicts", a, b)
        assert brief.contradicted(store) == []


def test_contradicted_keeps_a_genuine_corpus_disagreement(store):
    with store.with_partition(PART):
        a = store.add_concept("adr-0042#old-spec")
        b = store.add_concept("adr-0087#zone-class")
        store.link("contradicts", a, b)
        assert len(brief.contradicted(store)) == 1


def test_endpoint_fallthrough_still_honours_mtype_exclusion(store):
    """`_endpoint`'s docstring said mtype exclusions 'still apply'; the
    get_entity_by_id fallthrough bypassed them for rows excluded by mtype but
    not by the name regex (ch-bsd r2 #b-2-r2c)."""
    with store.with_partition(PART):
        keep = store.add_memory("real-note", "x", mtype="project")
        skip = store.add_memory("savestate_abc123", "x", mtype="session/digest")
        store.link("contradicts", keep, skip)
        out, skipped, why = brief.contradicted(store, count_skips=True)
    assert out == [], "an mtype-excluded row reached the class"
    assert skipped == 1
    assert why.get("unresolvable_or_mtype") == 1, why


def test_contradicted_finding_does_not_claim_both_sides_are_memories(store):
    """The line read 'two memories contradict' over two concept anchors."""
    with store.with_partition(PART):
        a = store.add_concept("adr-0042#old-spec")
        b = store.add_concept("adr-0087#zone-class")
        store.link("contradicts", a, b)
        out = brief.contradicted(store)
    assert "memories" not in out[0].finding, out[0].finding
