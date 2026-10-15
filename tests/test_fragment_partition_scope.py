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


# ---- repair: rebuild contaminated fragments without losing a real bit -----------------


def _put_fragment(s: Store, partition: str, linkage: str, bits) -> None:
    """Write a raw fragment row, bypassing the cache — reproduces the on-disk damage the
    bug-105 cache left behind (foreign bits, dead-entity bits)."""
    from pyroaring import BitMap64

    con = s._connect()
    pid = con._duck.execute(
        "SELECT id FROM partitions WHERE name = ?", [partition]).fetchone()[0]
    con._duck.execute(
        "INSERT INTO bitmap_fragments(partition_id, linkage, blob) VALUES (?, ?, ?) "
        "ON CONFLICT(partition_id, linkage) DO UPDATE SET blob = excluded.blob",
        [pid, linkage, BitMap64(bits).serialize()],
    )


def _contaminated(s: Store):
    """home: entity a (linked), entity x (bit only in a fragment, no entity_links row);
    other: entity b (linked). Damage: home's fragment lost a's bit (it is only in
    entity_links), holds b's bit (foreign) and a bit for a purged entity; other's fragment
    holds only x's fragment-only bit (foreign AND not in entity_links)."""
    home = s.partition_name
    c = s.add_concept("parser")
    a = s.upsert_entity(kind="code", name="src/a.py")
    x = s.upsert_entity(kind="code", name="src/x.py")
    s.link("defines", c, a)
    s.flush_fragments()
    with s.with_partition("other"):
        c2 = s.add_concept("parser")
        b = s.upsert_entity(kind="code", name="src/b.py")
        s.link("defines", c2, b)
        s.flush_fragments()
    dead = 999_999
    pk = s._pack
    _put_fragment(s, home, "defines", [pk(c2, b), pk(c, dead)])
    _put_fragment(s, "other", "defines", [pk(c, x)])
    s._clear_fragment_caches()
    return home, a, b, x, dead, c, c2


def test_repair_moves_every_bit_to_its_entity_partition(duck_store, tmp_path):
    s = duck_store
    home, a, b, x, dead, c, c2 = _contaminated(s)
    rep = s.repair_fragments(dry_run=False, manifest_dir=tmp_path / "m")
    assert _persisted_entities(s, home, "defines") == {a, x}     # x moved home, not dropped
    assert _persisted_entities(s, "other", "defines") == {b}     # b restored from links
    assert rep["dropped_dead"] == 1
    assert rep["moved"] == 2              # b -> other, x -> home
    assert rep["added_from_links"] == 1   # a, present only in entity_links


def test_repair_dry_run_writes_nothing(duck_store, tmp_path):
    s = duck_store
    home, a, b, x, dead, c, c2 = _contaminated(s)
    before = s._connect()._duck.execute(
        "SELECT partition_id, linkage, blob FROM bitmap_fragments ORDER BY 1, 2").fetchall()
    rep = s.repair_fragments(dry_run=True, manifest_dir=tmp_path / "m")
    after = s._connect()._duck.execute(
        "SELECT partition_id, linkage, blob FROM bitmap_fragments ORDER BY 1, 2").fetchall()
    assert before == after
    assert rep["dry_run"] is True and rep["dropped_dead"] == 1


def test_repair_manifest_holds_every_dropped_bit(duck_store, tmp_path):
    """Dead-entity bits are the only bits removed; the manifest keeps them restorable."""
    import json
    from pyroaring import BitMap64

    s = duck_store
    home, a, b, x, dead, c, c2 = _contaminated(s)
    rep = s.repair_fragments(dry_run=False, manifest_dir=tmp_path / "m")
    lines = [json.loads(l) for l in open(rep["manifest"])]
    dropped = set()
    for rec in lines:
        dropped |= set(BitMap64.deserialize(bytes.fromhex(rec["dropped_hex"])))
    assert dropped == {s._pack(c, dead)}


def test_repair_is_idempotent(duck_store, tmp_path):
    s = duck_store
    _contaminated(s)
    s.repair_fragments(dry_run=False, manifest_dir=tmp_path / "m1")
    rep2 = s.repair_fragments(dry_run=False, manifest_dir=tmp_path / "m2")
    assert rep2["moved"] == 0 and rep2["dropped_dead"] == 0 and rep2["added_from_links"] == 0


# ---- the repair surfaces: daemon op (through the real dispatcher) and the CLI ----------


def _dispatch(d, req: dict) -> dict:
    import json
    import socket
    from concurrent.futures import Future

    class _NowPool:
        def submit(self, fn, *a, **kw):
            f = Future()
            try:
                f.set_result(fn(*a, **kw))
            except BaseException as e:  # noqa: BLE001 — the dispatcher reads it back
                f.set_exception(e)
            return f

    a, b = socket.socketpair()
    a.sendall((json.dumps(req) + "\n").encode())
    d._handle(b, _NowPool(), _NowPool())
    b.close()
    out = a.recv(1 << 20).decode().strip()
    a.close()
    return json.loads(out)


def test_repair_fragments_op_through_the_dispatcher(monkeypatch):
    """Dry run reports and changes nothing; apply fixes the rows and writes the manifest
    under the store's backups/. A short /tmp root keeps the socket path legal."""
    import shutil
    import tempfile
    from pathlib import Path

    from refmatrix import daemon as dm

    monkeypatch.delenv("RMX_BACKEND", raising=False)
    base = Path(tempfile.mkdtemp(prefix="rmxf-", dir="/tmp"))
    root = base / ".refmatrix"
    d = dm.Daemon(root)
    d.store = Store(root, backend="duckdb"); d.store.init()
    d._log = lambda m: None
    monkeypatch.setattr(d, "_request_snapshot", lambda: None)
    try:
        home, a, b, x, dead, c, c2 = _contaminated(d.store)
        dry = _dispatch(d, {"op": "repair_fragments", "args": {"dry_run": True}})
        assert dry["ok"] is True, dry
        assert dry["result"]["dry_run"] is True and dry["result"]["moved"] == 2
        assert _persisted_entities(d.store, "other", "defines") == {x}   # unchanged
        res = _dispatch(d, {"op": "repair_fragments", "args": {"dry_run": False}})
        assert res["ok"] is True, res
        assert _persisted_entities(d.store, "other", "defines") == {b}
        assert Path(res["result"]["manifest"]).parent.resolve() == (root / "backups").resolve()
    finally:
        d.store.close()
        shutil.rmtree(base, ignore_errors=True)


def test_repair_index_fragments_cli_offline_dry_run(tmp_path, monkeypatch):
    """With no daemon, `rmx repair-index --fragments --dry-run` runs offline, prints the
    counts, and leaves the fragments unchanged."""
    from click.testing import CliRunner

    from refmatrix import cli as cli_mod
    from refmatrix import verbs as verbs_mod

    monkeypatch.delenv("RMX_BACKEND", raising=False)
    root = tmp_path / ".refmatrix"
    s = Store(root, backend="duckdb"); s.init()
    home, a, b, x, dead, c, c2 = _contaminated(s)
    s.close()

    def _absent(r):
        raise verbs_mod.VerbAbsentError("no daemon")

    monkeypatch.setattr(verbs_mod, "require_daemon", _absent)
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    out = CliRunner().invoke(cli_mod.main, ["repair-index", "--fragments", "--dry-run"])
    assert out.exit_code == 0, out.output
    assert "moved=2" in out.output and "dropped_dead=1" in out.output and "dry run" in out.output
    s = Store(root, backend="duckdb")
    try:
        assert _persisted_entities(s, "other", "defines") == {x}
    finally:
        s.close()
