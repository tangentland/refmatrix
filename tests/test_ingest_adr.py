"""ADR markdown semantic extraction."""
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


def _make_adr(project: Path, num: str, title: str, body: str) -> Path:
    adr_dir = project / "docs" / "architecture" / "adr"
    adr_dir.mkdir(parents=True, exist_ok=True)
    p = adr_dir / f"{num}-{title}.md"
    p.write_text(body)
    return p


def test_accepted_adr_emits_defines_for_class_spec(store, tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    _make_adr(project, "0087", "spatial-zone", """\
# ADR-0087: Spatial Zone

Status: Accepted
Governs: Zone coordinate representation, geometry operations

## Decision

```
Zone:
  type: BBOX | POLYGON
  area -> float
  centroid -> Point
  contains_point(point) -> bool
```
""")
    ingest_path(store, project)
    qe = QueryEngine(store)
    hits = list(qe.run("defines:Zone"))
    names = {store.get_entity_by_id(h).name for h in hits}
    assert any("0087" in n for n in names), f"no ADR entity in defines:Zone: {names}"


def test_cross_reference_emits_related_to(store, tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    _make_adr(project, "0087", "zone", """\
# ADR-0087: Zone

Status: Accepted

## Decision

See ADR-0043 for prior context.
""")
    _make_adr(project, "0043", "prior", """\
# ADR-0043: Prior

Status: Accepted

## Decision

Stuff.
""")
    ingest_path(store, project)
    # adr/0043 concept should related_to both ADR entities
    qe = QueryEngine(store)
    hits = list(qe.run("related_to:adr/0043"))
    assert len(hits) >= 2, f"expected both ADRs related_to adr/0043, got {hits}"


def test_superseded_adr_emits_no_linkages(store, tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    _make_adr(project, "0099", "dead", """\
# ADR-0099

Status: Superseded
Governs: DeadZone

## Decision

```
DeadZone:
  field: int
```
""")
    ingest_path(store, project)
    qe = QueryEngine(store)
    assert list(qe.run("defines:DeadZone")) == []
    assert list(qe.run("mentions:DeadZone")) == []


def test_subclass_tree_emits_is_a(store, tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    _make_adr(project, "0087", "zone", """\
# ADR-0087

Status: Accepted

## Hierarchy

```
Zone (base)
  +-- AnnotatedZone(Zone)
  +-- ScoredZone(Zone)
  +-- DetectionZone(ScoredZone, AnnotatedZone)
```
""")
    ingest_path(store, project)
    qe = QueryEngine(store)
    # Zone concept is_a target should include child entities
    is_a_hits = list(qe.run("is_a:Zone"))
    names = {store.get_entity_by_id(h).name for h in is_a_hits}
    assert any("AnnotatedZone" in n for n in names), f"AnnotatedZone missing: {names}"
    assert any("ScoredZone" in n for n in names), f"ScoredZone missing: {names}"


def test_governs_emits_mentions(store, tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    _make_adr(project, "0087", "zone", """\
# ADR-0087

Status: Accepted
Governs: Zone coordinate representation, BBOX operations

## Decision

Stuff.
""")
    ingest_path(store, project)
    qe = QueryEngine(store)
    hits = list(qe.run("mentions:Zone"))
    names = {store.get_entity_by_id(h).name for h in hits}
    assert any("0087" in n for n in names), f"ADR not in mentions:Zone: {names}"


def test_non_adr_markdown_ignored(store, tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    # NOT in adr/ dir
    (project / "docs").mkdir()
    p = project / "docs" / "0001-not-an-adr.md"
    p.write_text("""\
# Title

Status: Accepted

```
NotAClass:
  field: int
```
""")
    ingest_path(store, project)
    qe = QueryEngine(store)
    assert list(qe.run("defines:NotAClass")) == []
