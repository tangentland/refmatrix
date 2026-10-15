"""bug-111: the fragment repair re-added a dead-concept bit from `entity_links`, and an ingest path
left the dead `entity_links` rows behind in the first place.

Six seconds after the bug-105 repair on cliquedb (2026-10-14 19:09), a dry run found one
`part-of` bit whose concept id is in neither `entities` nor `concepts`. No writer ran in between:
`repair_fragments` rebuilds from `entity_links` checking only that the ENTITY is alive, while its
fragment half also checks the CONCEPT — so an orphan `entity_links` row came back as a bit on every
apply, and every later dry run reported it as `dropped_dead_concept`. The orphan rows come from
deletes that bypass `purge_entity`, such as `ingest_gmd_paths(as_memory=True)` dropping a prior
kind='doc' entity with raw SQL.
"""

import pytest
from pyroaring import BitMap64

from refmatrix.ingest_gmd import ingest_gmd_paths
from refmatrix.store import Store, _CONCEPT_SHIFT


@pytest.fixture
def s(tmp_path, monkeypatch):
    monkeypatch.delenv("RMX_BACKEND", raising=False)
    st = Store(tmp_path / ".refmatrix", backend="duckdb"); st.init()
    yield st
    st.close()


def _all_bits(s: Store) -> set[int]:
    out: set[int] = set()
    for bm in s._read_all_fragment_rows().values():
        out |= set(bm)
    return out


def _orphan_link(s: Store, linkage: str = "part-of") -> tuple[int, int]:
    """A live entity E with an `entity_links` row to a concept id that exists nowhere."""
    e = s.upsert_entity(kind="concept", name="architecture-readme")
    parent = s.upsert_entity(kind="concept", name="heading")
    s.add_linkage_type(linkage)
    s.link(linkage, parent, e); s.flush_fragments()
    con = s._connect()._duck
    lid = con.execute("SELECT id FROM linkage_types WHERE name=?", [linkage]).fetchone()[0]
    dead = 2_791_209
    assert con.execute("SELECT count(*) FROM entities WHERE id=?", [dead]).fetchone()[0] == 0
    con.execute("INSERT INTO entity_links (entity_id, linkage_id, concept_id) VALUES (?, ?, ?)",
                [e, lid, dead])
    return e, dead


def test_apply_does_not_restore_a_dead_concept_bit_from_entity_links(s, tmp_path):
    e, dead = _orphan_link(s)
    bit = (dead << _CONCEPT_SHIFT) | e
    applied = s.repair_fragments(dry_run=False, manifest_dir=tmp_path / "m")
    assert bit not in _all_bits(s), "the repair wrote a bit whose concept does not exist"
    assert applied["links_dead_concept"] == 1, applied
    again = s.repair_fragments(dry_run=True, manifest_dir=tmp_path / "m")
    assert again["dropped_dead_concept"] == 0, again       # the cliquedb symptom
    assert again["rows_changed"] == 0, again                # idempotent: a fixed point
    assert again["links_dead_concept"] == 1, again          # the orphan row stays visible


def test_a_dead_concept_bit_already_in_a_fragment_is_dropped_once_and_stays_dropped(s, tmp_path):
    e, dead = _orphan_link(s)
    bit = (dead << _CONCEPT_SHIFT) | e
    pid = s._partition_id
    rows = s._read_all_fragment_rows()
    rows[(pid, "part-of")] = rows[(pid, "part-of")] | BitMap64([bit])
    with s.transaction():
        s._write_all_fragment_rows(rows)
    s._clear_fragment_caches()
    first = s.repair_fragments(dry_run=False, manifest_dir=tmp_path / "m")
    assert first["dropped_dead_concept"] == 1 and first["manifest"], first
    assert bit not in _all_bits(s)
    second = s.repair_fragments(dry_run=True, manifest_dir=tmp_path / "m")
    assert second["dropped_dead_concept"] == 0 and second["rows_changed"] == 0, second


def test_as_memory_ingest_replacing_a_doc_entity_leaves_no_orphan_links(s, tmp_path):
    md = tmp_path / "note.md"
    md.write_text('---\ngmd: "0.1"\nid: note\ntitle: "Note"\ntags: [t]\n---\n'
                  "# Note {#root}\n\n## Part {#part}\n\nBody about [[other]].\n")
    ingest_gmd_paths(s, [md])                       # kind='doc' entity + heading part-of links
    con = s._connect()._duck
    doc_id = con.execute("SELECT id FROM entities WHERE kind='doc' AND name='note'").fetchone()
    assert doc_id is not None
    ingest_gmd_paths(s, [md], as_memory=True)       # drops the doc entity for the memory row
    orphans = con.execute(
        "SELECT count(*) FROM entity_links l WHERE NOT EXISTS "
        "(SELECT 1 FROM entities e WHERE e.id = l.entity_id) OR (NOT EXISTS "
        "(SELECT 1 FROM entities e WHERE e.id = l.concept_id) AND NOT EXISTS "
        "(SELECT 1 FROM concepts c WHERE c.id = l.concept_id))").fetchone()[0]
    assert orphans == 0, "the as-memory doc drop left entity_links rows naming a deleted id"
    rep = s.repair_fragments(dry_run=True, manifest_dir=tmp_path / "m")
    assert rep["dropped_dead"] == 0 and rep["dropped_dead_concept"] == 0, rep
