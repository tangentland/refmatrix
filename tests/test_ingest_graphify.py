"""Graphify graph.json ingest — entity/concept registration, verb mapping,
confidence-weighted edges, evidence rows, additive layering on tldr."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from refmatrix.ingest import _ingest_graphify, ingest_path
from refmatrix.query import QueryEngine
from refmatrix.store import Store


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / ".refmatrix")
    s.init()
    yield s
    s.close()


def _write_graph(project: Path, payload: dict) -> Path:
    out = project / "graphify-out"
    out.mkdir(parents=True, exist_ok=True)
    p = out / "graph.json"
    p.write_text(json.dumps(payload))
    return p


def _names_of(store, hits):
    return {store.get_entity_by_id(h).name for h in hits}


def _basic_graph() -> dict:
    return {
        "directed": True,
        "multigraph": False,
        "graph": {},
        "nodes": [
            {
                "id": "module_alpha",
                "label": "alpha.py",
                "file_type": "code",
                "source_file": "src/alpha.py",
                "source_location": "L1",
                "community": 0,
                "norm_label": "alpha.py",
            },
            {
                "id": "module_beta",
                "label": "beta.py",
                "file_type": "code",
                "source_file": "src/beta.py",
                "source_location": "L1",
                "community": 0,
                "norm_label": "beta.py",
            },
            {
                "id": "doc_design",
                "label": "DESIGN.md",
                "file_type": "doc",
                "source_file": "docs/DESIGN.md",
                "source_location": "L1",
                "community": 1,
                "norm_label": "DESIGN.md",
            },
        ],
        "links": [
            {
                "relation": "calls",
                "confidence": "EXTRACTED",
                "source_file": "src/alpha.py",
                "source_location": "L42",
                "weight": 1.0,
                "source": "module_alpha",
                "target": "module_beta",
                "confidence_score": 1.0,
                "context": "alpha.foo() calls beta.bar()",
            },
            {
                "relation": "rationale_for",
                "confidence": "INFERRED",
                "source_file": "docs/DESIGN.md",
                "source_location": "L17",
                "weight": 1.0,
                "source": "doc_design",
                "target": "module_alpha",
                "confidence_score": 0.7,
            },
            {
                "relation": "semantically_similar_to",
                "confidence": "AMBIGUOUS",
                "source_file": "src/alpha.py",
                "source_location": "L5",
                "weight": 0.8,
                "source": "module_alpha",
                "target": "module_beta",
                "confidence_score": 0.6,
            },
        ],
        "hyperedges": [],
        "built_at_commit": "deadbeef",
    }


def test_ingest_graphify_registers_entities(store, tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    _write_graph(project, _basic_graph())
    n = _ingest_graphify(store, project)
    assert n == 3  # three edges processed
    # All three nodes became entities under graphify:: prefix
    qe = QueryEngine(store)
    names = {e.name for e in store.iter_entities()}
    assert "graphify::module_alpha" in names
    assert "graphify::module_beta" in names
    assert "graphify::doc_design" in names


def test_ingest_graphify_doc_kind_inferred(store, tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    _write_graph(project, _basic_graph())
    _ingest_graphify(store, project)
    doc_e = store.get_entity(kind="doc", name="graphify::doc_design")
    code_e = store.get_entity(kind="code", name="graphify::module_alpha")
    assert doc_e is not None
    assert code_e is not None


def test_ingest_graphify_calls_edge_emits_calls_linkage(store, tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    _write_graph(project, _basic_graph())
    _ingest_graphify(store, project)
    qe = QueryEngine(store)
    # source concept is gf/module_alpha → calls edge bitmaps include beta entity
    hits = list(qe.run("calls:gf/module_alpha"))
    names = _names_of(store, hits)
    assert "graphify::module_beta" in names


def test_ingest_graphify_rationale_for_maps_to_specifies(store, tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    _write_graph(project, _basic_graph())
    _ingest_graphify(store, project)
    qe = QueryEngine(store)
    hits = list(qe.run("specifies:gf/doc_design"))
    names = _names_of(store, hits)
    assert "graphify::module_alpha" in names


def test_ingest_graphify_auto_creates_unknown_verb(store, tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    _write_graph(project, _basic_graph())
    _ingest_graphify(store, project)
    # similar_to is not in DEFAULT_LINKAGES; should be auto-registered
    lid = store.get_linkage_id("similar_to")
    assert lid is not None


def test_ingest_graphify_writes_evidence(store, tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    _write_graph(project, _basic_graph())
    _ingest_graphify(store, project)
    beta_e = store.get_entity(kind="code", name="graphify::module_beta")
    rows = store.get_evidence(beta_e.id, linkage="calls")
    assert any(
        r["file"] == "src/alpha.py" and r["line"] == 42 for r in rows
    ), rows


def test_ingest_graphify_via_source_flag(store, tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    _write_graph(project, _basic_graph())
    n = ingest_path(store, project, source="graphify")
    assert n == 3


def test_ingest_graphify_additive_with_auto(store, tmp_path):
    """Source=auto with no tldr cache but graphify present should fall through
    to tree ingest AND layer graphify edges on top."""
    project = tmp_path / "proj"
    project.mkdir()
    (project / "src").mkdir()
    (project / "src" / "alpha.py").write_text("def foo(): pass\n")
    _write_graph(project, _basic_graph())
    ingest_path(store, project, source="auto")
    # tree-walked entity AND graphify entity coexist
    names = {e.name for e in store.iter_entities()}
    assert "src/alpha.py" in names  # from tree walk
    assert "graphify::module_alpha" in names  # from graphify


def test_ingest_graphify_skips_when_cache_missing(store, tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    n = _ingest_graphify(store, project)
    assert n == 0


def test_ingest_graphify_mtime_gate_skips_unchanged(store, tmp_path, monkeypatch):
    """Front-door no-op gate: a re-ingest over an unchanged graph.json mtime
    must skip the per-row upsert/link/evidence work entirely and return the
    recorded edge count (so `_ingest_path_inner`'s `n == 0` source-chaining and
    the 'ingested N' tally stay truthful). Touching the file re-arms the pass."""
    import os
    project = tmp_path / "proj"
    project.mkdir()
    gp = _write_graph(project, _basic_graph())

    n1 = ingest_path(store, project, source="graphify")
    assert n1 == 3

    # add_evidence is written only by the graphify edge pass (derive_called_by
    # never touches it), so it's a clean sentinel for "the pass actually ran".
    calls = {"evidence": 0}
    real = store.add_evidence

    def spy(*a, **k):
        calls["evidence"] += 1
        return real(*a, **k)

    monkeypatch.setattr(store, "add_evidence", spy)

    n2 = ingest_path(store, project, source="graphify")
    assert n2 == 3            # count preserved for chaining + tally
    assert calls["evidence"] == 0  # gate fired: zero re-writes

    # New mtime → gate misses → the pass re-runs.
    st = gp.stat()
    os.utime(gp, (st.st_atime + 5, st.st_mtime + 5))
    n3 = ingest_path(store, project, source="graphify")
    assert n3 == 3
    assert calls["evidence"] > 0


def test_ingest_graphify_weight_modulated_by_confidence(store, tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    _write_graph(project, _basic_graph())
    _ingest_graphify(store, project)
    # INFERRED edge (rationale_for) had confidence 0.7 × edge weight 1.0
    # × confidence_label_w 0.5 = 0.35. AMBIGUOUS (similar_to) had
    # 0.6 × 0.8 × 0.3 = 0.144. EXTRACTED (calls) = 1.0.
    # The shadow entity_links table records weight — verify ordering.
    import sqlite3
    con = store._connect()
    rows = con.execute(
        "SELECT lt.name, el.weight FROM entity_links el "
        "JOIN linkage_types lt ON lt.id = el.linkage_id "
        "WHERE el.weight IS NOT NULL"
    ).fetchall()
    weights = {row[0]: row[1] for row in rows}
    assert weights.get("calls") == pytest.approx(1.0)
    assert weights.get("specifies") == pytest.approx(0.35, rel=1e-3)
    assert weights.get("similar_to") == pytest.approx(0.144, rel=1e-3)
