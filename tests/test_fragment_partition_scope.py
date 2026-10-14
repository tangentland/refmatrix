"""bug-105: the bitmap fragment cache must follow the partition binding.

`Store._fragments` / `_dirty_fragments` were one dict keyed by linkage only, while at least
seven code paths rebind `_partition_id` (`with_partition`, three daemon sites, rename, ...).
A fragment loaded under partition A stayed cached when the Store was rebound to B, so B's
links were OR-ed into A's bitmap and flushed under whichever partition was bound at flush
time. A 2026-10-14 census of a copy of this repo's live read snapshot found
`sessions-refmatrix mentions` holding 195,003 of 422,811 bits whose entity lives in another
partition (ch-bsd plan-23/17 re-review, `bsd-plan23-17-spec-rereview-32dde06#nb23-1`).

Each test checks the PERSISTED `bitmap_fragments` rows, not the in-memory cache: the defect
only becomes visible once a flush writes the mixed bitmap under a partition id.
"""
from __future__ import annotations

import pytest

from refmatrix.store import Store


@pytest.fixture
def duck_store(tmp_path, monkeypatch):
    monkeypatch.delenv("RMX_BACKEND", raising=False)
    s = Store(tmp_path / ".refmatrix", backend="duckdb")
    s.init()
    yield s
    s.close()


def _persisted_entities(s: Store, partition: str, linkage: str) -> set[int]:
    """Entity ids encoded in the persisted fragment row of (partition, linkage)."""
    from pyroaring import BitMap64

    con = s._connect()
    pid = con._duck.execute(
        "SELECT id FROM partitions WHERE name = ?", [partition]
    ).fetchone()[0]
    row = con._duck.execute(
        "SELECT blob FROM bitmap_fragments WHERE partition_id = ? AND linkage = ?",
        [pid, linkage],
    ).fetchone()
    if row is None:
        return set()
    mask = (1 << 32) - 1
    return {int(b) & mask for b in BitMap64.deserialize(bytes(row[0]))}


def _entity_partition(s: Store, entity_id: int) -> int:
    return s._connect()._duck.execute(
        "SELECT partition_id FROM entities WHERE id = ?", [entity_id]
    ).fetchone()[0]


def test_with_partition_does_not_leak_bits_into_the_other_partition(duck_store):
    s = duck_store
    home = s.partition_name
    concept = s.add_concept("parser")
    a = s.upsert_entity(kind="code", name="src/a.py")
    s.link("defines", concept, a)          # loads + dirties `defines` under `home`

    with s.with_partition("other"):
        c2 = s.add_concept("parser")
        b = s.upsert_entity(kind="code", name="src/b.py")
        s.link("defines", c2, b)
        s.flush_fragments()

    s.flush_fragments()

    assert _persisted_entities(s, "other", "defines") == {b}
    assert _persisted_entities(s, home, "defines") == {a}


def test_every_persisted_bit_belongs_to_its_rows_partition(duck_store):
    """The census invariant itself: no fragment row holds a foreign-partition entity."""
    s = duck_store
    ids = {}
    for part in (s.partition_name, "p2", "p3"):
        with s.with_partition(part):
            c = s.add_concept("shared")
            for i in range(3):
                e = s.upsert_entity(kind="doc", name=f"{part}/d{i}.md")
                s.link("mentions", c, e)
                ids.setdefault(part, set()).add(e)
    s.flush_fragments()

    con = s._connect()
    rows = con._duck.execute(
        "SELECT p.name, f.partition_id FROM bitmap_fragments f "
        "JOIN partitions p ON p.id = f.partition_id WHERE f.linkage = 'mentions'"
    ).fetchall()
    assert {r[0] for r in rows} == set(ids)
    for part, pid in rows:
        persisted = _persisted_entities(s, part, "mentions")
        assert persisted == ids[part]
        assert {_entity_partition(s, e) for e in persisted} == {pid}


def test_a_direct_rebind_also_switches_the_cache(duck_store):
    """The daemon rebinds `_partition_name/_partition_id` directly (daemon.py:3334, :4916,
    :4955). The cache must follow that too, not only `with_partition`."""
    s = duck_store
    home, home_id = s.partition_name, s.partition_id
    c = s.add_concept("parser")
    a = s.upsert_entity(kind="code", name="src/a.py")
    s.link("defines", c, a)

    with s.with_partition("other"):
        other_id = s.partition_id
    s._partition_name, s._partition_id = "other", other_id
    try:
        c2 = s.add_concept("parser")
        b = s.upsert_entity(kind="code", name="src/b.py")
        s.link("defines", c2, b)
    finally:
        s._partition_name, s._partition_id = home, home_id
    s.flush_fragments()

    assert _persisted_entities(s, "other", "defines") == {b}
    assert _persisted_entities(s, home, "defines") == {a}
