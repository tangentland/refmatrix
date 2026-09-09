"""Two rank modifiers, 2026-09-09:

1. ADR source authority — structural edges (defines/is_a/related-to, GMD
   rel:) from ADRs weigh above baseline. mentions/tf channels untouched.
2. Phrase proximity — content hits where query terms travel together
   outrank the same terms scattered. Ordering-only.
"""
from __future__ import annotations

import pytest

from refmatrix.context import _phrase_hit, content_only_bundle
from refmatrix.store import Store


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / ".refmatrix")
    s.init()
    yield s
    s.close()


# --- ADR authority ----------------------------------------------------------


ADR_TEXT = """# ADR-0042: Zone classification

Status: Accepted
Governs: Zone

## Decision

```
class Zone:
    kind: str
```
"""


def _ingest_adr(s, tmp_path, text=ADR_TEXT):
    adr_dir = tmp_path / "docs" / "adr"
    adr_dir.mkdir(parents=True)
    f = adr_dir / "0042-zone-classification.md"
    f.write_text(text, encoding="utf8")
    from refmatrix.ingest import _ingest_adr_semantics
    eid = s.upsert_entity(kind="doc", name="docs/adr/0042-zone-classification.md",
                          path=str(f))
    return _ingest_adr_semantics(s, f, tmp_path, {"0042": eid})


def test_adr_structural_edges_carry_authority(store, tmp_path, monkeypatch):
    monkeypatch.setenv("RMX_ADR_AUTHORITY", "3.0")
    n = _ingest_adr(store, tmp_path)
    assert n > 0
    con = store._connect()
    row = con.execute(
        "SELECT el.weight FROM entity_links el "
        "JOIN linkage_types lt ON lt.id = el.linkage_id "
        "JOIN entities c ON c.id = el.concept_id "
        "WHERE lt.name = 'defines' AND c.name = 'Zone'"
    ).fetchone()
    assert row is not None
    assert row[0] == pytest.approx(3.0)  # Accepted (1.0) x authority (3.0)


def test_adr_mentions_stay_tf_pure(store, tmp_path, monkeypatch):
    monkeypatch.setenv("RMX_ADR_AUTHORITY", "3.0")
    _ingest_adr(store, tmp_path)
    con = store._connect()
    row = con.execute(
        "SELECT el.weight FROM entity_links el "
        "JOIN linkage_types lt ON lt.id = el.linkage_id "
        "JOIN entities c ON c.id = el.concept_id "
        "WHERE lt.name = 'mentions' AND c.name = 'Zone'"
    ).fetchone()
    assert row is not None
    assert row[0] == pytest.approx(1.0)  # status weight only — NO authority


def test_adr_authority_env_override(store, tmp_path, monkeypatch):
    monkeypatch.setenv("RMX_ADR_AUTHORITY", "5.0")
    _ingest_adr(store, tmp_path)
    con = store._connect()
    row = con.execute(
        "SELECT el.weight FROM entity_links el "
        "JOIN linkage_types lt ON lt.id = el.linkage_id "
        "JOIN entities c ON c.id = el.concept_id "
        "WHERE lt.name = 'defines' AND c.name = 'Zone'"
    ).fetchone()
    assert row[0] == pytest.approx(5.0)


def test_gmd_adr_rel_edges_carry_authority(store, tmp_path, monkeypatch):
    monkeypatch.setenv("RMX_ADR_AUTHORITY", "3.0")
    d = tmp_path / "docs" / "adr"
    d.mkdir(parents=True)
    (d / "0001-target.md").write_text(
        '---\ngmd: "0.1"\nid: 0001-target\ntitle: "T"\ntags: [adr]\n---\n'
        "# Target {#root}\n", encoding="utf8")
    (d / "0002-src.md").write_text(
        '---\ngmd: "0.1"\nid: 0002-src\ntitle: "S"\ntags: [adr]\n---\n'
        "# Src {#root}\n\nrel: supersedes -> [[0001-target]]\n",
        encoding="utf8")
    from refmatrix.ingest_gmd import ingest_gmd_paths
    ingest_gmd_paths(store, [d / "0001-target.md", d / "0002-src.md"])
    con = store._connect()
    rows = con.execute(
        "SELECT el.weight FROM entity_links el "
        "JOIN linkage_types lt ON lt.id = el.linkage_id "
        "WHERE lt.name = 'supersedes'"
    ).fetchall()
    assert rows and all(r[0] == pytest.approx(3.0) for r in rows)


def test_gmd_plain_doc_rel_edges_stay_baseline(store, tmp_path):
    d = tmp_path / "docs"
    d.mkdir()
    (d / "a-doc.md").write_text(
        '---\ngmd: "0.1"\nid: a-doc\ntitle: "A"\ntags: [notes]\n---\n'
        "# A {#root}\n", encoding="utf8")
    (d / "b-doc.md").write_text(
        '---\ngmd: "0.1"\nid: b-doc\ntitle: "B"\ntags: [notes]\n---\n'
        "# B {#root}\n\nrel: related-to -> [[a-doc]]\n", encoding="utf8")
    from refmatrix.ingest_gmd import ingest_gmd_paths
    ingest_gmd_paths(store, [d / "a-doc.md", d / "b-doc.md"])
    con = store._connect()
    rows = con.execute(
        "SELECT el.weight FROM entity_links el "
        "JOIN linkage_types lt ON lt.id = el.linkage_id "
        "JOIN entities src ON src.id = el.concept_id "
        "WHERE lt.name = 'related-to' AND src.name LIKE 'b-doc%'"
    ).fetchall()
    # baseline: weight NULL (link default) or 1.0 — never the ADR multiplier
    assert rows and all(r[0] is None or r[0] == pytest.approx(1.0)
                        for r in rows)


# --- phrase proximity -------------------------------------------------------


def test_phrase_hit_adjacent_and_windowed():
    assert _phrase_hit("the replica rotation drifted", ["replica", "rotation"])
    assert _phrase_hit("replica slot rotation", ["replica", "rotation"])
    assert not _phrase_hit(
        "rotation happens hourly; the replica lags", ["replica", "rotation"])
    assert not _phrase_hit(
        "replica " + "x" * 40 + " rotation", ["replica", "rotation"])
    assert not _phrase_hit("replica rotation", ["replica"])   # 1 term: no-op


def test_phrase_proximity_reorders_content_hits(store, monkeypatch):
    monkeypatch.setenv("RMX_PHRASE_BOOST", "10.0")  # exaggerate for the test
    for i in range(6):
        store.upsert_entity(kind="doc", name=f"filler{i}.md",
                            tldr=f"unrelated background text {i} about daemons")
        fid = store.add_concept(f"bg{i}")
    # Scattered doc gets MORE raw term mass; phrase doc has the bigram.
    scattered = store.upsert_entity(
        kind="doc", name="scattered.md",
        tldr="rotation policy notes are quite long and detailed here; "
             "eventually after much unrelated prose the replica catches up")
    phrased = store.upsert_entity(
        kind="doc", name="phrased.md",
        tldr="how replica rotation works end to end")
    for cname, tf_scattered, tf_phrased in (
            ("replica", 4.0, 1.0), ("rotation", 4.0, 1.0)):
        cid = store.add_concept(cname)
        store.link("mentions", cid, scattered, weight=tf_scattered)
        store.link("mentions", cid, phrased, weight=tf_phrased)
    b = content_only_bundle(store, "replica rotation")
    names = [e.entity.name for e in b.groups.get("content", [])]
    assert names and names[0] == "phrased.md", names


def test_phrase_boost_disabled_keeps_bm25_order(store, monkeypatch):
    monkeypatch.setenv("RMX_PHRASE_BOOST", "1.0")
    for i in range(6):
        store.upsert_entity(kind="doc", name=f"filler{i}.md",
                            tldr=f"unrelated background text {i} about daemons")
        fid = store.add_concept(f"bg{i}")
    scattered = store.upsert_entity(
        kind="doc", name="scattered.md",
        tldr="rotation policy notes are quite long and detailed here; "
             "eventually after much unrelated prose the replica catches up")
    phrased = store.upsert_entity(
        kind="doc", name="phrased.md",
        tldr="how replica rotation works end to end")
    for cname, tf_scattered, tf_phrased in (
            ("replica", 4.0, 1.0), ("rotation", 4.0, 1.0)):
        cid = store.add_concept(cname)
        store.link("mentions", cid, scattered, weight=tf_scattered)
        store.link("mentions", cid, phrased, weight=tf_phrased)
    b = content_only_bundle(store, "replica rotation")
    names = [e.entity.name for e in b.groups.get("content", [])]
    assert names and names[0] == "scattered.md", names
