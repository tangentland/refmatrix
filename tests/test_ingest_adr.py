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


def test_class_keyword_prefix_and_extends_form(store, tmp_path):
    """Class regex accepts keyword prefixes (class/enum/struct/interface)
    and both inheritance forms: Foo(Bar) and Foo extends Bar."""
    project = tmp_path / "proj"
    project.mkdir()
    _make_adr(project, "0090", "shapes", """\
# ADR-0090

Status: Accepted

## Decision

```
class Shape:
  area -> float

struct Rectangle extends Shape:
  width: float
  height: float

enum ColorEnum:
  RED
  BLUE

interface Drawable:
  draw() -> None
```
""")
    ingest_path(store, project)
    qe = QueryEngine(store)
    for c in ("Shape", "Rectangle", "ColorEnum", "Drawable"):
        names = _names_of_helper(store, list(qe.run(f"defines:{c}")))
        assert any(f"::{c}" in n for n in names), f"missing {c}: {names}"
    # Rectangle is_a Shape via "extends" form
    is_a_shape = _names_of_helper(store, list(qe.run("is_a:Shape")))
    assert any("::Rectangle" in n for n in is_a_shape), is_a_shape


def test_bold_wrapped_header_fields(store, tmp_path):
    """ADR headers in the wild often use bold-wrapped labels like
    **Status:** Accepted (from copy-paste of rendered markdown).
    Both forms must parse the same."""
    project = tmp_path / "proj"
    project.mkdir()
    _make_adr(project, "0087", "zone", """\
# ADR-0087

**Status:** Accepted
**Governs:** Zone, BBOX
**Cross-references:** ADR-0043

## Decision

```
Zone:
  field: int
```
""")
    _make_adr(project, "0043", "prior", """\
# ADR-0043

**Status:** Accepted
""")
    ingest_path(store, project)
    qe = QueryEngine(store)

    # Status was parsed → linkages emitted at Accepted weight (not skipped)
    defines_hits = _names_of_helper(store, list(qe.run("defines:Zone")))
    assert any("0087" in n for n in defines_hits), defines_hits

    # Governs parsed
    mentions_hits = _names_of_helper(store, list(qe.run("mentions:Zone")))
    assert any("0087" in n for n in mentions_hits), mentions_hits

    # Cross-references parsed
    rel_hits = _names_of_helper(store, list(qe.run("related_to:adr/0043")))
    assert any("0087" in n for n in rel_hits), rel_hits


def _names_of_helper(store, hits):
    return {store.get_entity_by_id(h).name for h in hits}


def test_non_adr_markdown_no_adr_namespace(store, tmp_path):
    """A markdown file outside adr/ is NOT treated as an ADR even with an
    ADR-like header. Status weighting and adr/NNNN namespacing don't apply;
    it goes through the general markdown extractor instead."""
    project = tmp_path / "proj"
    project.mkdir()
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
    # File is registered, fenced class spec extracts (universal behavior)
    hits = list(qe.run("defines:NotAClass"))
    assert hits, "fenced class spec should still extract from general markdown"
    # But the file does NOT register as an ADR — no adr_number metadata
    ent = store.get_entity("doc", "docs/0001-not-an-adr.md")
    assert ent is not None
    meta = ent.meta or {}
    assert "adr_number" not in meta, f"non-ADR file got adr_number: {meta}"
