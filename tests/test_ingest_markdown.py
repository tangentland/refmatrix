"""Generic markdown (concept doc, design doc) semantic extraction."""
from __future__ import annotations

from pathlib import Path

import pytest

from refmatrix.ingest import ingest_path
from refmatrix.query import QueryEngine
from refmatrix.store import Store


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / ".refmatrix")
    s.init()
    yield s
    s.close()


def _make(project: Path, rel: str, body: str) -> Path:
    p = project / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)
    return p


def _names_of(store, hits):
    return {store.get_entity_by_id(h).name for h in hits}


def test_concept_doc_filename_defines(store, tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    _make(project, "docs/concepts/spatial.md", """\
# Spatial — Entities, Hierarchy, Containment

Brief intro.
""")
    ingest_path(store, project)
    qe = QueryEngine(store)
    names = _names_of(store, qe.run("defines:Spatial"))
    assert any("spatial.md" in n for n in names), f"spatial.md not defined: {names}"


def test_concept_doc_h3_creates_subconcept_entities(store, tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    _make(project, "docs/concepts/spatial.md", """\
# Spatial

Body.

## Entities

### World

The root namespace.

### Zone

A zone subclasses Area, adding reactive behavior.

### Place

A place subclasses Zone.
""")
    ingest_path(store, project)
    qe = QueryEngine(store)

    # Each H3 produces a defines linkage
    for concept in ("World", "Zone", "Place"):
        hits = list(qe.run(f"defines:{concept}"))
        names = _names_of(store, hits)
        assert any(f"::{concept}" in n for n in names), (
            f"missing sub-entity for {concept}: {names}"
        )


def test_concept_doc_subclass_prose_emits_is_a(store, tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    _make(project, "docs/concepts/spatial.md", """\
# Spatial

## Entities

### Zone

A zone subclasses Area, adding reactive behavior.

### Place

A place subclasses Zone, adding activity context.
""")
    ingest_path(store, project)
    qe = QueryEngine(store)

    # Zone is_a Area  → entity for ::Zone is in is_a:Area
    area_children = _names_of(store, qe.run("is_a:Area"))
    assert any("::Zone" in n for n in area_children), (
        f"Zone not a child of Area: {area_children}"
    )
    zone_children = _names_of(store, qe.run("is_a:Zone"))
    assert any("::Place" in n for n in zone_children), (
        f"Place not a child of Zone: {zone_children}"
    )


def test_concept_doc_multi_word_h3_ignored(store, tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    _make(project, "docs/concepts/spatial.md", """\
# Spatial

### Areas Are Exclusive Partitions

Multi-word H3, should not become a single concept.
""")
    ingest_path(store, project)
    qe = QueryEngine(store)
    # No sub-entity for "Areas"
    hits = list(qe.run("defines:Areas"))
    names = _names_of(store, hits)
    assert not any("::Areas" in n for n in names), f"unexpected sub-entity: {names}"


def test_design_doc_bold_metadata_related_to(store, tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    _make(project, "docs/architecture/principles.md", "# Principles\n\nBody.\n")
    _make(project, "CLAUDE.md", "# Claude config\n")
    _make(project, "docs/design/tenets.md", """\
# Architecture Tenets

**Source:** docs/architecture/principles.md
**Referenced by:** CLAUDE.md

## Body

Stuff.
""")
    ingest_path(store, project)
    qe = QueryEngine(store)

    # ref/<path> concept hub links tenets.md to principles.md
    p_hits = _names_of(store, qe.run("related_to:ref/docs/architecture/principles.md"))
    assert any("tenets.md" in n for n in p_hits)
    assert any("principles.md" in n for n in p_hits)

    c_hits = _names_of(store, qe.run("related_to:ref/CLAUDE.md"))
    assert any("tenets.md" in n for n in c_hits)
    assert any(n == "CLAUDE.md" for n in c_hits)


def test_design_doc_adr_implements_ref(store, tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    _make(project, "docs/architecture/adr/0087-zone.md", """\
# ADR-0087

Status: Accepted
""")
    _make(project, "docs/design/zone-impl.md", """\
# Zone Implementation Notes

**Implements:** ADR-0087

## Body
""")
    ingest_path(store, project)
    qe = QueryEngine(store)
    hits = _names_of(store, qe.run("related_to:adr/0087"))
    assert any("zone-impl.md" in n for n in hits), f"missing zone-impl: {hits}"


def test_markdown_adr_cross_reference_in_prose(store, tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    _make(project, "docs/architecture/adr/0087-zone.md", """\
# ADR-0087

Status: Accepted
""")
    _make(project, "docs/design/random.md", """\
# Random Notes

See ADR-0087 for the spatial zone design.
""")
    ingest_path(store, project)
    qe = QueryEngine(store)
    hits = _names_of(store, qe.run("related_to:adr/0087"))
    assert any("random.md" in n for n in hits)


def test_plain_markdown_no_extraction(store, tmp_path):
    """A plain markdown file with no concept-doc location, no bold metadata,
    no ADR refs, no fenced class specs — should be registered as a doc
    entity but emit no extra semantic linkages."""
    project = tmp_path / "proj"
    project.mkdir()
    _make(project, "docs/random-notes.md", """\
# Some Random Notes

Just some prose about JavaScript and WebSockets. Words like
HttpClient and Database appear but shouldn't become concepts.

## Body

More prose.
""")
    ingest_path(store, project)
    qe = QueryEngine(store)
    # CamelCase tokens from prose are NOT extracted
    assert list(qe.run("defines:JavaScript")) == []
    assert list(qe.run("defines:HttpClient")) == []
    assert list(qe.run("mentions:JavaScript")) == []


def test_concept_doc_kebab_filename(store, tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    _make(project, "docs/concepts/binding-result-contract.md", """\
# Binding Result Contract

The contract.
""")
    ingest_path(store, project)
    qe = QueryEngine(store)
    names = _names_of(store, qe.run("defines:BindingResultContract"))
    assert any("binding-result-contract.md" in n for n in names), names


def test_fenced_class_spec_in_design_doc(store, tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    _make(project, "docs/design/region-design.md", """\
# Region Design Notes

## Proposed shape

```
Region:
  bounds: BBOX
  refine(point) -> Point
```
""")
    ingest_path(store, project)
    qe = QueryEngine(store)
    names = _names_of(store, qe.run("defines:Region"))
    assert any("::Region" in n for n in names), names
