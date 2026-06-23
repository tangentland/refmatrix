"""facts.log rotation: faithful compaction + size-gated daemon tick.

`dump_catalog_to_log()` is both the bootstrap-onto-log and the compaction
primitive. These tests lock in that a dump→rebuild round-trip is faithful
across partitions and memory bodies (the pre-rotation dump flattened
partitions and dropped memory bodies), and that the daemon's
`_compact_factslog_if_needed` is size-gated, offset-resetting, and lossless.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from refmatrix.store import Store

duckdb_only = pytest.mark.skipif(
    importlib.util.find_spec("duckdb") is None, reason="duckdb not installed",
)


def _snapshot(s: Store) -> dict:
    """{partition: sorted[(kind, name, path)]} across the whole catalog."""
    con = s._connect()
    out: dict = {}
    for pid, pname in con.execute(
        "SELECT id, name FROM partitions ORDER BY name"
    ).fetchall():
        out[pname] = sorted(
            tuple(r) for r in con.execute(
                "SELECT kind, name, path FROM entities WHERE partition_id=?",
                [pid],
            ).fetchall()
        )
    return out


def test_dump_rebuild_partition_and_memory_faithful(tmp_path):
    s = Store(tmp_path / ".refmatrix")
    s.init()
    with s.with_partition("p1"):
        f1 = s.upsert_entity(kind="code", name="a.sql", path="/x/a.sql")
        c1 = s.add_concept("users")
        s.link("defines", c1, f1)
        s.add_evidence("defines", c1, f1, file="a.sql", line=10, detail="t")
    with s.with_partition("p2"):
        # SAME (kind, name) as p1 but a different path — must stay distinct.
        s.upsert_entity(kind="code", name="a.sql", path="/y/a.sql")
        s.add_memory("mem1", content="body!", mtype="project",
                     tags=["t"], metadata={"k": "v"})

    before = _snapshot(s)
    counts = s.dump_catalog_to_log()
    assert counts["memory_content"] == 1
    assert counts["entity"] == 4
    s.rebuild_index_from_log()
    after = _snapshot(s)

    assert before == after, "partition fidelity lost on round-trip"
    # same-name entity kept its per-partition path
    assert ("code", "a.sql", "/x/a.sql") in after["p1"]
    assert ("code", "a.sql", "/y/a.sql") in after["p2"]
    # memory body + mtype survived
    with s.with_partition("p2"):
        m = s.get_memory("mem1")
        assert m is not None and m["content"] == "body!" and m["mtype"] == "project"
        assert m["tags"] == ["t"]
    s.close()


def test_legacy_log_without_partition_rebuilds_into_default(tmp_path):
    # A pre-rotation facts.log: events with no `partition` field. They must
    # still replay (into the active/default partition) for back-compat.
    root = tmp_path / ".refmatrix"
    s = Store(root)
    s.init()
    default = s.partition_name
    import json
    with s.log_path.open("w", encoding="utf-8") as f:
        f.write(json.dumps({"ts": 1, "op": "entity", "kind": "code",
                            "name": "legacy.py", "path": "/p/legacy.py"}) + "\n")
        f.write(json.dumps({"ts": 2, "op": "entity", "kind": "concept",
                            "name": "thing"}) + "\n")
        f.write(json.dumps({"ts": 3, "op": "link", "linkage": "mentions",
                            "c": "thing", "e_kind": "code", "e": "legacy.py"}) + "\n")
    res = s.rebuild_index_from_log()
    assert res["entities"] == 2
    assert res["links"] == 1
    snap = _snapshot(s)
    assert ("code", "legacy.py", "/p/legacy.py") in snap[default]
    s.close()


def _make_daemon(tmp_path: Path):
    from refmatrix.daemon import Daemon
    root = tmp_path / ".refmatrix"
    root.mkdir(parents=True, exist_ok=True)
    s = Store(root)
    s.init()
    d = Daemon(root)
    d.store = s
    return d, s


@duckdb_only
def test_compact_size_gated_skips_under_threshold(tmp_path, monkeypatch):
    d, s = _make_daemon(tmp_path)
    with s.with_partition("p"):
        s.upsert_entity(kind="code", name="x.py", path="/x.py")
    s.dump_catalog_to_log()  # establish a small log
    monkeypatch.setenv("RMX_FACTSLOG_MAX_BYTES", str(10 * 1024 * 1024))
    r = d._compact_factslog_if_needed(force=False)
    assert r["skipped"] == "under-threshold"
    s.close()


@duckdb_only
def test_compact_force_shrinks_and_resets_offsets(tmp_path):
    d, s = _make_daemon(tmp_path)
    # Churn the log: re-ingest the same entity many times so the append log
    # holds duplicate events the catalog folds to one row.
    with s.with_partition("p"):
        for i in range(200):
            s.upsert_entity(kind="code", name="x.py", path=f"/x.py#{i}")
    big = s.log_path.stat().st_size
    # Pretend slots were caught up to some stale (larger) offset.
    d._write_slot_offset("A", big + 12345)
    d._write_slot_offset("B", big + 12345)

    r = d._compact_factslog_if_needed(force=True)
    assert r["compacted"] is True
    assert r["new_size"] < big, "compaction did not shrink the log"
    # offsets reset to the new EOF (not the stale larger value)
    new_size = s.log_path.stat().st_size
    assert d._read_slot_offset("A") == new_size
    assert d._read_slot_offset("B") == new_size
    # lossless: rebuilding from the compacted log reproduces the catalog
    before = _snapshot(s)
    s.rebuild_index_from_log()
    assert _snapshot(s) == before
    s.close()
