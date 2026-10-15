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


# ---- ch-bsd r1 (bsd-bug111-repair-dead-links-0f268f5) -------------------------------------------

def _cross_partition_part_of(s: Store) -> tuple[int, int]:
    """Doc D in partition `mem`; entity E in the default partition; E part-of D (probe1)."""
    s.add_linkage_type("part-of")
    with s.with_partition("mem"):
        d = s.upsert_entity(kind="doc", name="d.md")
    e = s.upsert_entity(kind="concept", name="e")
    s.link("part-of", d, e); s.flush_fragments()
    return d, e


def test_purge_clears_a_concept_bit_that_lives_in_another_partition(s, tmp_path):
    d, e = _cross_partition_part_of(s)
    with s.with_partition("mem"):
        s.purge_entity(d)
    s.flush_fragments()
    rep = s.repair_fragments(dry_run=True, manifest_dir=tmp_path / "m")
    assert rep["dropped_dead_concept"] == 0 and rep["dropped_dead"] == 0, rep


def test_purge_under_a_foreign_binding_clears_the_entitys_own_bit(s, tmp_path):
    d, e = _cross_partition_part_of(s)
    with s.with_partition("mem"):
        s.purge_entity(e)                      # E lives in the default partition
    s.flush_fragments()
    rep = s.repair_fragments(dry_run=True, manifest_dir=tmp_path / "m")
    assert rep["dropped_dead"] == 0 and rep["dropped_dead_concept"] == 0, rep


def test_bulk_purge_clears_bits_in_every_partition(s, tmp_path):
    d, e = _cross_partition_part_of(s)
    with s.with_partition("mem"):
        s._bulk_purge_ids([(d, "doc", "d.md")])
    s.flush_fragments()
    rep = s.repair_fragments(dry_run=True, manifest_dir=tmp_path / "m")
    assert rep["dropped_dead_concept"] == 0 and rep["dropped_dead"] == 0, rep


def test_links_dead_entity_counts_the_orphan_share_of_links_skipped(s, tmp_path):
    c = s.add_concept("k"); e = s.upsert_entity(kind="doc", name="a.md")
    s.add_linkage_type("mentions"); s.link("mentions", c, e); s.flush_fragments()
    con = s._connect()._duck
    lid = con.execute("SELECT id FROM linkage_types WHERE name='mentions'").fetchone()[0]
    con.execute("INSERT INTO entity_links (entity_id, linkage_id, concept_id) VALUES (?, ?, ?)",
                [987_654, lid, c])
    rep = s.repair_fragments(dry_run=True, manifest_dir=tmp_path / "m")
    assert rep["links_dead_entity"] == 1 and rep["links_skipped"] == 1, rep


def _memo(tmp_path, name="note", sub="mem"):
    md = tmp_path / sub / f"{name}.md"
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text(f'---\ngmd: "0.1"\nid: {name}\ntitle: "N"\ntags: [t]\n---\n'
                  f"# N {{#root}}\n\n## Part {{#part}}\n\nBody.\n")
    return md


def test_a_failed_doc_drop_is_counted_reported_printed_and_bridged(s, tmp_path, monkeypatch,
                                                                     capsys):
    from refmatrix.cli import _bridge_stats

    md = _memo(tmp_path)
    ingest_gmd_paths(s, [md])

    def _boom(*a, **k):
        raise RuntimeError("purge refused")
    monkeypatch.setattr(s, "purge_entity", _boom)
    stats = ingest_gmd_paths(s, [md], as_memory=True)       # verbose stays False
    assert len(stats.doc_drop_failed) == 1, stats.doc_drop_failed
    assert "purge refused" in stats.doc_drop_failed[0][1]
    assert stats.as_dict()["doc_drop_failed"][0][0] == str(md)
    assert "doc_drop_failed: 1" in stats.report()
    assert "doc->memory cleanup failed" in capsys.readouterr().out
    out: dict = {}
    _bridge_stats(out, stats.as_dict())
    assert out["doc_drop_failed"] and out["doc_drop_failed"][0]["path"] == str(md), out


def test_a_failed_vector_delete_counts_as_a_failed_doc_drop(s, tmp_path, monkeypatch):
    md = _memo(tmp_path)
    ingest_gmd_paths(s, [md])
    real = s.purge_entity

    def _lance_fails(eid, **k):
        s.vector_delete_failures = getattr(s, "vector_delete_failures", 0) + 1
        return real(eid, **k)
    monkeypatch.setattr(s, "purge_entity", _lance_fails)
    stats = ingest_gmd_paths(s, [md], as_memory=True)
    assert len(stats.doc_drop_failed) == 1 and "vector delete" in stats.doc_drop_failed[0][1]


def test_as_memory_ingest_does_not_purge_a_same_id_doc_at_another_path(s, tmp_path):
    project_doc = _memo(tmp_path, sub="docs")             # project doc, GMD id "note"
    memory_file = _memo(tmp_path, sub="mem")               # memory file, same id
    ingest_gmd_paths(s, [project_doc])
    con = s._connect()._duck
    before = con.execute("SELECT id FROM entities WHERE kind='doc' AND name='note'").fetchall()
    assert len(before) == 1
    ingest_gmd_paths(s, [memory_file], as_memory=True)
    after = con.execute("SELECT id FROM entities WHERE kind='doc' AND name='note'").fetchall()
    assert after == before, "a different file's doc entity was purged by name alone"


# ---- ch-bsd r2 (bsd-bug111-r2-remedy-129366b) ----------------------------------------------------

def test_links_dead_entity_is_not_links_skipped_when_a_linkage_is_unknown(s, tmp_path):
    """D1: an unknown-linkage row is skipped but its entity is alive — not an orphan."""
    c = s.add_concept("k"); e = s.upsert_entity(kind="doc", name="a.md")
    s.add_linkage_type("mentions"); s.link("mentions", c, e); s.flush_fragments()
    con = s._connect()._duck
    lid = con.execute("SELECT id FROM linkage_types WHERE name='mentions'").fetchone()[0]
    con.execute("INSERT INTO entity_links (entity_id, linkage_id, concept_id) VALUES (?, ?, ?)",
                [987_654, lid, c])                                   # dead entity
    con.execute("INSERT INTO entity_links (entity_id, linkage_id, concept_id) VALUES (?, ?, ?)",
                [e, 99_999, c])                                      # unknown linkage, live entity
    rep = s.repair_fragments(dry_run=True, manifest_dir=tmp_path / "m")
    assert rep["links_skipped"] == 2 and rep["links_dead_entity"] == 1, rep


def test_purge_never_upserts_a_partition(s, monkeypatch):
    """r2 #1: the per-partition clear swaps the binding directly; `with_partition` (an INSERT OR
    IGNORE + commit + lookup per partition per purge, and no damaged-zonemap fallback) is not on
    the purge path."""
    d, e = _cross_partition_part_of(s)

    def _no(*a, **k):
        raise AssertionError("purge went through with_partition")
    monkeypatch.setattr(s, "with_partition", _no)
    s.purge_entity(e)
    s._bulk_purge_ids([(d, "doc", "d.md")])
    assert s.partition_name == s._partition_name  # binding restored


def _linked_dir(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    return real, link


def test_doc_drop_matches_a_doc_stored_under_the_symlinked_path(s, tmp_path):
    """I2: both ingests pass the symlinked path; the stored path is the unresolved string."""
    real, link = _linked_dir(tmp_path)
    md = _memo(real, sub=".")
    via = link / md.name
    ingest_gmd_paths(s, [via])
    con = s._connect()._duck
    assert con.execute("SELECT path FROM entities WHERE kind='doc' AND name='note'"
                       ).fetchone()[0] == str(via)
    ingest_gmd_paths(s, [via], as_memory=True)
    assert con.execute("SELECT count(*) FROM entities WHERE kind='doc' AND name='note'"
                       ).fetchone()[0] == 0


def test_doc_drop_matches_a_doc_stored_under_the_resolved_path(s, tmp_path):
    """I3: the doc was ingested by its real path, the memory bridge passes the symlinked one."""
    real, link = _linked_dir(tmp_path)
    md = _memo(real, sub=".")
    ingest_gmd_paths(s, [md.resolve()])
    ingest_gmd_paths(s, [link / md.name], as_memory=True)
    con = s._connect()._duck
    assert con.execute("SELECT count(*) FROM entities WHERE kind='doc' AND name='note'"
                       ).fetchone()[0] == 0
