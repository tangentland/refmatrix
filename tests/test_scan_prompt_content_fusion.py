"""scan-prompt fuses a content-ranked view over ALL the prompt's terms.

The per-concept bundles answer "what neighbours this term", once per term,
independently. That question has no idf and no coverage: a bundle ranks by raw
`mentions` weight (= term frequency), so a COMMON prompt word with a high tf
outranks a RARE one with a low tf, and nothing prefers a document carrying
several of the prompt's terms over one carrying a single term many times.

Measured on 1307 GMD chat sessions (eval/memaware, 90 questions): scan-prompt
hit@20 0.200 against 0.433 for `rmx context` over the SAME store.
"""
from __future__ import annotations

import json

import pytest

from refmatrix.ingest_gmd import ingest_gmd_paths
from refmatrix.scan import scan_prompt
from refmatrix.store import Store

# `rare` appears ONCE in the target and nowhere else; `common` appears many
# times in the decoy. Ranking by tf within one term crowns the decoy; ranking
# with idf + coverage crowns the target, which carries BOTH prompt terms.
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

DECOY = """---
gmd: "0.1"
id: doc-decoy
title: "Decoy"
tags: [t]
metadata: {node_type: memory, type: test/doc}
---

# Decoy {#root}

common common common common common common common common common common closet.
"""


@pytest.fixture
def store(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "doc-target.md").write_text(TARGET, encoding="utf8")
    (docs / "doc-decoy.md").write_text(DECOY, encoding="utf8")
    s = Store(tmp_path / ".refmatrix", backend="duckdb")
    s.init()
    ingest_gmd_paths(s, sorted(docs.glob("*.md")), as_memory=True,
                     memory_mtype_default="test/doc")
    yield s
    s.close()


def _names(payload: str) -> list[str]:
    out = []
    for bundle in json.loads(payload):
        for entries in bundle.get("groups", {}).values():
            out.extend(e["name"] for e in entries)
    return out


def test_content_bundle_is_emitted_even_when_concepts_match(store):
    """The regression. This path existed but ran ONLY as a fallback for when no
    concept matched — so on a corpus where every content word is a concept, the
    case that needed it most could never reach it."""
    got = _names(scan_prompt(store, "rare common", fmt="json", composite=False))
    assert any(n.startswith("doc-target") for n in got)


def test_coverage_beats_raw_term_frequency(store):
    """The document carrying BOTH prompt terms must outrank the one repeating
    the commoner term ten times."""
    got = _names(scan_prompt(store, "rare common", fmt="json", composite=False))
    ranks = {n.split("#")[0]: i for i, n in enumerate(reversed(got))}
    assert "doc-target" in ranks
    if "doc-decoy" in ranks:
        assert ranks["doc-target"] > ranks["doc-decoy"]


def test_no_content_flag_restores_the_concept_only_view(store):
    payload = scan_prompt(store, "rare common", fmt="json", composite=False,
                          content=False)
    for bundle in json.loads(payload):
        assert bundle.get("anchor") is not None, "concept-only view is anchored"


def test_text_mode_carries_both_sections(store):
    out = scan_prompt(store, "rare common", composite=False)
    assert "content matches for prompt" in out
    assert "context for prompt-mentioned symbols" in out


def test_json_is_always_valid_even_with_no_hits(store):
    """Previously the no-match path returned "" — unparseable for a JSON
    consumer."""
    payload = scan_prompt(store, "zzzznothingmatches", fmt="json",
                          composite=False)
    assert json.loads(payload) == []
