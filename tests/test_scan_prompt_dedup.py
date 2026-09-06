"""scan-prompt slot hygiene: twin collapse, operational-anchor gate,
root-anchor dedup, cross-section dedup.

Observed live (2026-09-06, three consecutive prompts): `scan-prompt` and
`scan_prompt` each took a symbol slot (same_as twins); PPR expansion spent two
of five slots on `savestate_*#focus` / `#session` anchors the prompt never
named; the content bundle listed a memory row AND its `#root` concept with the
same headline; and the symbol bundle for the prompt's main term re-printed the
memories the content section had just shown. Four fixes, one budget.
"""
from __future__ import annotations

import json

import pytest

from refmatrix.ingest_gmd import ingest_gmd_paths
from refmatrix.scan import (
    _dedup_twin_concepts,
    _is_operational_anchor,
    _ppr_rerank,
    _render_key,
    match_concepts,
    scan_prompt,
)
from refmatrix.store import Store


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / ".refmatrix")
    s.init()
    yield s
    s.close()


# --- 1. alias twins collapse to one slot -----------------------------------


def test_dedup_keeps_first_of_a_twin_pair():
    got = _dedup_twin_concepts(["scan-prompt", "scan_prompt", "ScanPrompt"])
    assert got == ["scan-prompt"]


def test_dedup_keeps_distinct_anchors_of_one_doc():
    got = _dedup_twin_concepts(["doc#alpha", "doc#beta"])
    assert got == ["doc#alpha", "doc#beta"]


def test_match_concepts_collapses_variant_twins(store):
    store.add_concept("scan-prompt")
    store.add_concept("scan_prompt")
    got = match_concepts(store, ["scan-prompt", "scan_prompt"],
                         drop_unlinked_plain=False)
    assert len(got) == 1


def test_match_concepts_case_twins_collapse(store):
    store.add_concept("context")
    store.add_concept("Context")
    got = match_concepts(store, ["context", "Context"],
                         drop_unlinked_plain=False)
    assert len(got) == 1


# --- 2. PPR expansion never spends slots on operational anchors -------------


def test_operational_anchor_predicate():
    assert _is_operational_anchor("savestate_82464028d71d#focus")
    assert _is_operational_anchor("savestate_82464028d71d")
    assert _is_operational_anchor("session-abc123#events")
    assert _is_operational_anchor("focus_summary_deadbeef")
    assert not _is_operational_anchor("project_scan_prompt_junk_gate#root")
    assert not _is_operational_anchor("scan-prompt")


def test_ppr_rerank_drops_walk_discovered_savestate(store, monkeypatch):
    """Save-state cards mention everything a session touched, so they win
    walk mass on ANY prompt — but the prompt never named them."""
    from refmatrix import ppr as ppr_mod

    store.add_concept("seed")
    monkeypatch.setattr(
        ppr_mod, "rank_related_for_prompt",
        lambda *a, **k: [
            {"name": "savestate_abc#focus"},
            {"name": "related-thing"},
            {"name": "seed"},
        ])
    got = _ppr_rerank(store, ["seed"], max_concepts=5)
    assert "savestate_abc#focus" not in got
    assert "related-thing" in got
    assert "seed" in got


def test_ppr_rerank_keeps_a_savestate_the_prompt_named(store, monkeypatch):
    """Query-driven relevance stays: a seed IS the prompt's own term."""
    from refmatrix import ppr as ppr_mod

    store.add_concept("savestate_abc#focus")
    monkeypatch.setattr(
        ppr_mod, "rank_related_for_prompt",
        lambda *a, **k: [{"name": "savestate_abc#focus"}])
    got = _ppr_rerank(store, ["savestate_abc#focus"], max_concepts=5)
    assert "savestate_abc#focus" in got


# --- 3 + 4. content root-twin dedup and cross-section dedup -----------------

TARGET = """---
gmd: "0.1"
id: doc-target
title: "Target"
tags: [t]
metadata: {node_type: memory, type: test/doc}
---

# Target {#root}

The rare sneakers sat in the common closet.
"""


@pytest.fixture
def gmd_store(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "doc-target.md").write_text(TARGET, encoding="utf8")
    s = Store(tmp_path / ".refmatrix", backend="duckdb")
    s.init()
    ingest_gmd_paths(s, sorted(docs.glob("*.md")), as_memory=True,
                     memory_mtype_default="test/doc")
    yield s
    s.close()


def test_content_bundle_dedups_doc_and_its_root_anchor(gmd_store):
    """GMD ingest makes a memory row `X` AND a concept `X#root` with the same
    headline; both rank on the same terms. One hit, not two."""
    payload = scan_prompt(gmd_store, "rare closet", fmt="json",
                          composite=False)
    content_names = []
    for bundle in json.loads(payload):
        if bundle.get("anchor") is None:
            for entries in bundle.get("groups", {}).values():
                content_names.extend(e["name"] for e in entries)
    hits = {n for n in content_names
            if n in ("doc-target", "doc-target#root")}
    assert len(hits) <= 1, f"root twin not collapsed: {sorted(hits)}"


def test_render_key_folds_root_anchor_onto_base():
    assert _render_key("doc-target#root") == _render_key("doc-target")
    assert _render_key("doc-target#other") != _render_key("doc-target")


def test_symbol_bundles_skip_rows_the_content_section_showed(gmd_store):
    """Cross-section dedup: a row rendered in the content-match section must
    not re-render inside a per-symbol bundle."""
    out = scan_prompt(gmd_store, "rare closet", fmt="text", composite=False)
    for name in ("doc-target  [", "doc-target#root  ["):
        assert out.count(name) <= 1, (
            f"{name!r} rendered {out.count(name)}x:\n{out}")


# --- 5. concentration demotion of shape-0 centrality ------------------------
# `working` (df=56, max mention tf=2, PageRank-central) cleared the shape-0
# floor and earned the fattest bundle in the hook, because PageRank rewards
# being mentioned everywhere — the exact profile of a discourse word. Peak
# per-doc tf is the discriminator: every domain hub has a document that is
# ABOUT it (`memory` 24, `hub` 15); no discourse word does (all measured <= 2).


def test_diffuse_central_word_loses_its_centrality():
    from refmatrix.scan import _salience_from_parts

    kw = dict(df=56, token="working", name="working", code_frac=1.0,
              n_docs=1666)
    undemoted = _salience_from_parts(central=1.86, max_tf=None, **kw)
    demoted = _salience_from_parts(central=1.86, max_tf=2.0, **kw)
    assert demoted < undemoted
    assert demoted < 1.55, "diffuse word must fall below the shape-0 floor"


def test_concentrated_hub_keeps_full_centrality():
    from refmatrix.scan import _salience_from_parts

    kw = dict(df=209, token="memory", name="memory", code_frac=1.0,
              n_docs=1666)
    assert (_salience_from_parts(central=2.5, max_tf=24.0, **kw)
            == _salience_from_parts(central=2.5, max_tf=None, **kw))


def test_shaped_token_is_exempt_from_demotion():
    from refmatrix.scan import _salience_from_parts

    kw = dict(central=2.0, df=50, name="scan_prompt", token="scan_prompt",
              code_frac=1.0, n_docs=1666)
    assert (_salience_from_parts(max_tf=1.0, **kw)
            == _salience_from_parts(max_tf=None, **kw))


def test_identity_preserved_when_max_tf_is_none():
    """The code_frac=1.0 identity property extends: max_tf=None means the
    original expression exactly."""
    from refmatrix.scan import _salience_from_parts, _token_shape_score
    import math

    central, df, token, name = 1.7, 45, "just", "just"
    got = _salience_from_parts(central=central, df=df, token=token, name=name,
                               code_frac=1.0, n_docs=0, max_tf=None)
    want = central + 1.5 * (1.0 / math.log2(df + 2)) + _token_shape_score(token)
    assert abs(got - want) < 1e-9


def test_demotion_env_kill_switch(monkeypatch):
    from refmatrix.scan import _salience_from_parts

    monkeypatch.setenv("RMX_SCAN_CONC_DEMOTE", "0")
    kw = dict(central=1.86, df=56, token="working", name="working",
              code_frac=1.0, n_docs=1666)
    assert (_salience_from_parts(max_tf=2.0, **kw)
            == _salience_from_parts(max_tf=None, **kw))


def test_concentration_curve_shape():
    from refmatrix.scan import _mention_concentration

    assert _mention_concentration(0) == 0.0
    assert abs(_mention_concentration(2) - 0.5) < 0.01
    assert _mention_concentration(8) == 1.0
    assert _mention_concentration(24) == 1.0
