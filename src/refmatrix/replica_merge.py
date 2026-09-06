"""Slot-rotation drift recovery: merge two replica slots into one canonical
catalog file.

Drift class: rows written outside the daemon's facts.log replay protocol
end up only in the writer slot and never reach the inactive slot. Once
both slots have accumulated unlogged writes (because of mid-cycle slot
swaps, direct-write callsites, sqlite import paths, etc.), neither slot
is a superset and naive reseed in either direction loses data.

Recovery semantics:
  - Build the union of all rows across both slots.
  - For shared ids in tables with `updated_at`, prefer the newer row.
  - For (partition_id, kind, name) entity collisions on different ids,
    pick the winner by `entities.updated_at` (A wins ties) and remap
    every dependent reference (entity_id, concept_id) in the loser-slot
    rows to the winner's id.
  - For tables without `updated_at` (concepts, entity_links, etc.) use
    natural-PK union; on conflict, keep the A-side row.
  - Skip `bitmap_fragments` deep-merge — copy the union; daemon recomputes
    fragments on the next flush anyway.

Output: a fresh catalog file at `target_path` initialized via
`duckdb_catalog.init_catalog` with sequences positioned safely beyond
max(id) so future writes can't collide.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import duckdb

from refmatrix.duckdb_catalog import init_catalog


# Reserve this many id slots beyond max(id) for fresh-id allocation when a
# remap loser_id is occupied in the winner slot by a different entity.
# 1000 is generous for any realistic drift volume; the unused tail just
# means the sequence starts a few thousand ids ahead of the real high
# water mark — harmless.
REMAP_HEADROOM = 1000


def _scalar(cur: Any) -> Any:
    """First column of an aggregate SELECT — always returns exactly one row."""
    row = cur.fetchone()
    assert row is not None
    return row[0]


def _table_count(con: duckdb.DuckDBPyConnection, table: str) -> int:
    return _scalar(con.execute(f'SELECT COUNT(*) FROM "{table}"'))


def merge_slots(
    a_path: Path,
    b_path: Path,
    target_path: Path,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Merge slot A and slot B into a fresh DuckDB catalog at `target_path`.

    `dry_run`: build the remap and report per-table source counts + expected
    merged counts WITHOUT writing the target file.

    Returns: dict with keys
      - a_counts, b_counts, merged_counts: {table: rowcount}
      - remap: {a_loser_count, b_loser_count, fresh_alloc_count}
      - elapsed_ms
      - target_size_bytes (None when dry_run)
    """
    a_path = Path(a_path)
    b_path = Path(b_path)
    target_path = Path(target_path)

    t0 = time.monotonic()

    # ---- 1. Probe source state -----------------------------------------
    a_ro = duckdb.connect(str(a_path), read_only=True)
    b_ro = duckdb.connect(str(b_path), read_only=True)

    tables = (
        "partitions", "linkage_types", "entities", "concepts",
        "memory_content", "entity_links", "tracked_files",
        "linkage_evidence", "saved_queries", "bitmap_fragments",
    )
    a_counts = {t: _table_count(a_ro, t) for t in tables}
    b_counts = {t: _table_count(b_ro, t) for t in tables}

    max_entity = max(
        _scalar(a_ro.execute("SELECT COALESCE(MAX(id),0) FROM entities")),
        _scalar(b_ro.execute("SELECT COALESCE(MAX(id),0) FROM entities")),
    )
    max_partition = max(
        _scalar(a_ro.execute("SELECT COALESCE(MAX(id),0) FROM partitions")),
        _scalar(b_ro.execute("SELECT COALESCE(MAX(id),0) FROM partitions")),
    )
    max_lt = max(
        _scalar(a_ro.execute("SELECT COALESCE(MAX(id),0) FROM linkage_types")),
        _scalar(b_ro.execute("SELECT COALESCE(MAX(id),0) FROM linkage_types")),
    )
    a_ro.close()
    b_ro.close()

    # ---- 2. Open target + attach sources -------------------------------
    if dry_run:
        # Dry-run still needs a temp DB to compute the merge plan, but
        # we can use :memory: and skip the file writes.
        con = duckdb.connect(":memory:")
    else:
        if target_path.exists():
            target_path.unlink()
        # Also drop a stale .wal if one happens to be lying next to it.
        wal = target_path.with_name(target_path.name + ".wal")
        if wal.exists():
            wal.unlink()
        con = duckdb.connect(str(target_path))

    init_catalog(con, sequence_starts={
        "seq_partitions_id":    max_partition + 1,
        "seq_entities_id":      max_entity + REMAP_HEADROOM + 1,
        "seq_linkage_types_id": max_lt + 1,
    })

    con.execute(f"ATTACH '{a_path}' AS a (READ_ONLY)")
    con.execute(f"ATTACH '{b_path}' AS b (READ_ONLY)")

    # ---- 3. Lookup tables: partitions + linkage_types ------------------
    con.execute("INSERT INTO partitions SELECT * FROM a.partitions")
    con.execute("""
        INSERT INTO partitions
        SELECT * FROM b.partitions
        WHERE id NOT IN (SELECT id FROM partitions)
    """)
    con.execute("INSERT INTO linkage_types SELECT * FROM a.linkage_types")
    con.execute("""
        INSERT INTO linkage_types
        SELECT * FROM b.linkage_types
        WHERE id NOT IN (SELECT id FROM linkage_types)
    """)

    # ---- 4. Build entity-id remap --------------------------------------
    coll_rows = con.execute("""
        SELECT
            ae.id AS a_id, be.id AS b_id,
            ae.updated_at AS a_u, be.updated_at AS b_u
        FROM a.entities ae JOIN b.entities be
        ON ae.partition_id = be.partition_id
           AND ae.kind = be.kind
           AND ae.name = be.name
        WHERE ae.id <> be.id
    """).fetchall()

    # Set of ids shared between slots (so we can detect "loser id taken
    # in winner slot by a different entity"). Used purely for the fresh-
    # id allocation accounting reported back.
    shared_ids = set(r[0] for r in con.execute(
        "SELECT id FROM a.entities WHERE id IN (SELECT id FROM b.entities)"
    ).fetchall())

    remap_a: dict[int, int] = {}  # A-side loser_id -> canonical (in B)
    remap_b: dict[int, int] = {}  # B-side loser_id -> canonical (in A)
    fresh_alloc_count = 0
    for a_id, b_id, a_u, b_u in coll_rows:
        if a_u >= b_u:
            # A wins; B's loser_id remaps to A's winner id.
            remap_b[b_id] = a_id
            if b_id in shared_ids:
                fresh_alloc_count += 1
        else:
            remap_a[a_id] = b_id
            if a_id in shared_ids:
                fresh_alloc_count += 1

    # Materialize remap as temp tables for SQL joins.
    con.execute("CREATE TEMP TABLE remap_a (loser_id BIGINT, canonical_id BIGINT)")
    con.execute("CREATE TEMP TABLE remap_b (loser_id BIGINT, canonical_id BIGINT)")
    if remap_a:
        con.executemany("INSERT INTO remap_a VALUES (?, ?)", list(remap_a.items()))
    if remap_b:
        con.executemany("INSERT INTO remap_b VALUES (?, ?)", list(remap_b.items()))

    # ---- 5. entities: drop losers, union, newer-wins on shared ids -----
    con.execute("""
        INSERT INTO entities
        SELECT ae.* FROM a.entities ae
        LEFT JOIN remap_a r ON r.loser_id = ae.id
        WHERE r.loser_id IS NULL
    """)
    con.execute("""
        INSERT INTO entities
        SELECT be.* FROM b.entities be
        LEFT JOIN remap_b r ON r.loser_id = be.id
        LEFT JOIN entities m ON m.id = be.id
        WHERE r.loser_id IS NULL AND m.id IS NULL
    """)
    con.execute("""
        UPDATE entities AS m
        SET partition_id = be.partition_id,
            kind = be.kind,
            path = be.path,
            name = be.name,
            tldr = be.tldr,
            meta = be.meta,
            created_at = be.created_at,
            updated_at = be.updated_at,
            protected = be.protected,
            noise = be.noise,
            canonical_name = be.canonical_name,
            vectors_updated_at = be.vectors_updated_at
        FROM b.entities be
        WHERE m.id = be.id AND be.updated_at > m.updated_at
    """)

    # ---- 6. concepts: drop loser ids, union --------------------------
    con.execute("""
        INSERT INTO concepts
        SELECT ac.* FROM a.concepts ac
        LEFT JOIN remap_a r ON r.loser_id = ac.id
        WHERE r.loser_id IS NULL
    """)
    con.execute("""
        INSERT INTO concepts
        SELECT bc.* FROM b.concepts bc
        LEFT JOIN remap_b r ON r.loser_id = bc.id
        LEFT JOIN concepts m ON m.id = bc.id
        WHERE r.loser_id IS NULL AND m.id IS NULL
    """)

    # ---- 7. memory_content: newer-wins on entity_id; remap losers ------
    # 7a. Insert non-loser-side memory_content rows from each slot.
    con.execute("""
        INSERT INTO memory_content
        SELECT mc.* FROM a.memory_content mc
        LEFT JOIN remap_a r ON r.loser_id = mc.entity_id
        WHERE r.loser_id IS NULL
    """)
    con.execute("""
        INSERT INTO memory_content
        SELECT mc.* FROM b.memory_content mc
        LEFT JOIN remap_b r ON r.loser_id = mc.entity_id
        LEFT JOIN memory_content m ON m.entity_id = mc.entity_id
        WHERE r.loser_id IS NULL AND m.entity_id IS NULL
    """)
    # 7b. For shared entity_id rows, pull in B's content when newer.
    con.execute("""
        UPDATE memory_content AS m
        SET content = bc.content,
            mtype = bc.mtype,
            tags = bc.tags,
            metadata = bc.metadata,
            created_at = bc.created_at,
            updated_at = bc.updated_at
        FROM b.memory_content bc
        WHERE m.entity_id = bc.entity_id AND bc.updated_at > m.updated_at
    """)
    # 7c. Loser-side mc rows: redirect entity_id via remap; insert when
    # canonical has no mc yet, then overwrite when loser's mc is newer.
    con.execute("""
        INSERT INTO memory_content
            (entity_id, content, mtype, tags, metadata, created_at, updated_at)
        SELECT r.canonical_id, mc.content, mc.mtype, mc.tags, mc.metadata,
               mc.created_at, mc.updated_at
        FROM a.memory_content mc JOIN remap_a r ON r.loser_id = mc.entity_id
        LEFT JOIN memory_content m ON m.entity_id = r.canonical_id
        WHERE m.entity_id IS NULL
    """)
    con.execute("""
        UPDATE memory_content AS m
        SET content = sub.content,
            mtype = sub.mtype,
            tags = sub.tags,
            metadata = sub.metadata,
            created_at = sub.created_at,
            updated_at = sub.updated_at
        FROM (
            SELECT r.canonical_id, mc.content, mc.mtype, mc.tags,
                   mc.metadata, mc.created_at, mc.updated_at
            FROM a.memory_content mc JOIN remap_a r ON r.loser_id = mc.entity_id
        ) sub
        WHERE m.entity_id = sub.canonical_id AND sub.updated_at > m.updated_at
    """)
    con.execute("""
        INSERT INTO memory_content
            (entity_id, content, mtype, tags, metadata, created_at, updated_at)
        SELECT r.canonical_id, mc.content, mc.mtype, mc.tags, mc.metadata,
               mc.created_at, mc.updated_at
        FROM b.memory_content mc JOIN remap_b r ON r.loser_id = mc.entity_id
        LEFT JOIN memory_content m ON m.entity_id = r.canonical_id
        WHERE m.entity_id IS NULL
    """)
    con.execute("""
        UPDATE memory_content AS m
        SET content = sub.content,
            mtype = sub.mtype,
            tags = sub.tags,
            metadata = sub.metadata,
            created_at = sub.created_at,
            updated_at = sub.updated_at
        FROM (
            SELECT r.canonical_id, mc.content, mc.mtype, mc.tags,
                   mc.metadata, mc.created_at, mc.updated_at
            FROM b.memory_content mc JOIN remap_b r ON r.loser_id = mc.entity_id
        ) sub
        WHERE m.entity_id = sub.canonical_id AND sub.updated_at > m.updated_at
    """)

    # ---- 8. entity_links: remap both id columns, dedup by PK ----------
    con.execute("""
        INSERT INTO entity_links
        SELECT COALESCE(ra_e.canonical_id, al.entity_id) AS entity_id,
               al.linkage_id,
               COALESCE(ra_c.canonical_id, al.concept_id) AS concept_id,
               al.weight
        FROM a.entity_links al
        LEFT JOIN remap_a ra_e ON ra_e.loser_id = al.entity_id
        LEFT JOIN remap_a ra_c ON ra_c.loser_id = al.concept_id
        ON CONFLICT (entity_id, linkage_id, concept_id) DO NOTHING
    """)
    con.execute("""
        INSERT INTO entity_links
        SELECT COALESCE(rb_e.canonical_id, bl.entity_id) AS entity_id,
               bl.linkage_id,
               COALESCE(rb_c.canonical_id, bl.concept_id) AS concept_id,
               bl.weight
        FROM b.entity_links bl
        LEFT JOIN remap_b rb_e ON rb_e.loser_id = bl.entity_id
        LEFT JOIN remap_b rb_c ON rb_c.loser_id = bl.concept_id
        ON CONFLICT (entity_id, linkage_id, concept_id) DO NOTHING
    """)

    # ---- 9. linkage_evidence: no PK, UNION DISTINCT with remap --------
    con.execute("""
        INSERT INTO linkage_evidence
        SELECT DISTINCT * FROM (
            SELECT COALESCE(ra_e.canonical_id, le.entity_id) AS entity_id,
                   le.linkage_id,
                   COALESCE(ra_c.canonical_id, le.concept_id) AS concept_id,
                   le.file, le.line, le.span_end, le.detail
            FROM a.linkage_evidence le
            LEFT JOIN remap_a ra_e ON ra_e.loser_id = le.entity_id
            LEFT JOIN remap_a ra_c ON ra_c.loser_id = le.concept_id
            UNION ALL
            SELECT COALESCE(rb_e.canonical_id, le.entity_id) AS entity_id,
                   le.linkage_id,
                   COALESCE(rb_c.canonical_id, le.concept_id) AS concept_id,
                   le.file, le.line, le.span_end, le.detail
            FROM b.linkage_evidence le
            LEFT JOIN remap_b rb_e ON rb_e.loser_id = le.entity_id
            LEFT JOIN remap_b rb_c ON rb_c.loser_id = le.concept_id
        )
    """)

    # ---- 10. tracked_files: composite PK, newer last_synced wins ------
    con.execute("INSERT INTO tracked_files SELECT * FROM a.tracked_files ON CONFLICT DO NOTHING")
    con.execute("INSERT INTO tracked_files SELECT * FROM b.tracked_files ON CONFLICT DO NOTHING")
    con.execute("""
        UPDATE tracked_files AS m
        SET mtime = bt.mtime, last_synced = bt.last_synced
        FROM b.tracked_files bt
        WHERE m.partition_id = bt.partition_id
              AND m.path = bt.path
              AND bt.last_synced > m.last_synced
    """)

    # ---- 11. saved_queries: composite PK, A wins on conflict ---------
    con.execute("INSERT INTO saved_queries SELECT * FROM a.saved_queries ON CONFLICT DO NOTHING")
    con.execute("INSERT INTO saved_queries SELECT * FROM b.saved_queries ON CONFLICT DO NOTHING")

    # ---- 12. bitmap_fragments: copy union; daemon recomputes ---------
    con.execute("INSERT INTO bitmap_fragments SELECT * FROM a.bitmap_fragments")
    con.execute("""
        INSERT INTO bitmap_fragments
        SELECT * FROM b.bitmap_fragments b
        WHERE NOT EXISTS (
            SELECT 1 FROM bitmap_fragments m
            WHERE m.partition_id = b.partition_id
                  AND m.linkage = b.linkage
        )
    """)

    # ---- 13. Final counts + checkpoint --------------------------------
    merged_counts = {t: _table_count(con, t) for t in tables}

    con.execute("DETACH a")
    con.execute("DETACH b")
    if not dry_run:
        con.execute("CHECKPOINT")
    con.close()

    elapsed_ms = int((time.monotonic() - t0) * 1000)
    target_size = None
    if not dry_run and target_path.exists():
        target_size = target_path.stat().st_size

    return {
        "a_counts": a_counts,
        "b_counts": b_counts,
        "merged_counts": merged_counts,
        "remap": {
            "a_loser_count": len(remap_a),
            "b_loser_count": len(remap_b),
            "fresh_alloc_edge_cases": fresh_alloc_count,
        },
        "elapsed_ms": elapsed_ms,
        "target_size_bytes": target_size,
        "dry_run": dry_run,
    }


def audit_via_writer(
    writer_conn: "duckdb.DuckDBPyConnection",
    *,
    writer_slot: str,
    reader_path: Path,
    reader_slot: str,
) -> dict[str, Any]:
    """Audit variant that runs against the daemon's live writer connection.

    DuckDB only allows one process to hold a file lock on a catalog at a
    time, so a CLI-side audit can't open the writer slot read-only when the
    daemon owns the writer. This function ATTACHes the reader slot
    read-only on the writer's existing connection, runs the same compare
    queries `audit_slots` does, then DETACHes. Result shape matches
    `audit_slots`: keys are still `a_counts` / `b_counts` regardless of
    which slot is the writer."""
    tables = (
        "partitions", "linkage_types", "entities", "concepts",
        "memory_content", "entity_links", "tracked_files",
        "linkage_evidence", "saved_queries", "bitmap_fragments",
    )
    # Use a unique attach alias so we never collide with whatever schema
    # name the writer happens to be using. Also DETACH at the end so a
    # follow-up audit doesn't see a stale ATTACH.
    alias = "_audit_reader"
    writer_conn.execute(f"ATTACH '{reader_path}' AS {alias} (READ_ONLY)")
    try:
        writer_counts = {
            t: _scalar(writer_conn.execute(f'SELECT COUNT(*) FROM "{t}"'))
            for t in tables
        }
        reader_counts = {
            t: _scalar(writer_conn.execute(
                f'SELECT COUNT(*) FROM {alias}."{t}"'
            ))
            for t in tables
        }
        # Entity overlap shape — express both sides symmetrically.
        writer_only = _scalar(writer_conn.execute(
            f"SELECT COUNT(*) FROM entities WHERE id NOT IN "
            f"(SELECT id FROM {alias}.entities)"
        ))
        reader_only = _scalar(writer_conn.execute(
            f"SELECT COUNT(*) FROM {alias}.entities WHERE id NOT IN "
            f"(SELECT id FROM entities)"
        ))
        same_id_diff_payload = _scalar(writer_conn.execute(f"""
            SELECT COUNT(*) FROM entities w
            JOIN {alias}.entities r USING (id)
            WHERE w.name <> r.name OR w.kind <> r.kind
                  OR w.partition_id <> r.partition_id
        """))
        pkn_collisions = _scalar(writer_conn.execute(f"""
            SELECT COUNT(*) FROM entities w
            JOIN {alias}.entities r
            ON w.partition_id = r.partition_id
               AND w.kind = r.kind
               AND w.name = r.name
            WHERE w.id <> r.id
        """))
        mc_writer_only = _scalar(writer_conn.execute(
            f"SELECT COUNT(*) FROM memory_content WHERE entity_id NOT IN "
            f"(SELECT entity_id FROM {alias}.memory_content)"
        ))
        mc_reader_only = _scalar(writer_conn.execute(
            f"SELECT COUNT(*) FROM {alias}.memory_content WHERE entity_id NOT IN "
            f"(SELECT entity_id FROM memory_content)"
        ))
    finally:
        try:
            writer_conn.execute(f"DETACH {alias}")
        except Exception:
            pass

    # Normalize to A/B regardless of which slot is the writer right now.
    if writer_slot == "A":
        a_counts, b_counts = writer_counts, reader_counts
        a_only, b_only = writer_only, reader_only
        mc_a_only, mc_b_only = mc_writer_only, mc_reader_only
    else:
        a_counts, b_counts = reader_counts, writer_counts
        a_only, b_only = reader_only, writer_only
        mc_a_only, mc_b_only = mc_reader_only, mc_writer_only

    diffs = [t for t in tables if a_counts[t] != b_counts[t]]
    return {
        "a_counts": a_counts,
        "b_counts": b_counts,
        "tables_with_diff": diffs,
        "entities": {
            "a_only_ids": a_only,
            "b_only_ids": b_only,
            "same_id_diff_payload": same_id_diff_payload,
            "pkn_collisions_different_ids": pkn_collisions,
        },
        "memory_content": {
            "a_only_entity_ids": mc_a_only,
            "b_only_entity_ids": mc_b_only,
        },
        "writer_slot": writer_slot,
        "reader_slot": reader_slot,
        "drift_detected": bool(
            diffs or a_only or b_only or same_id_diff_payload or pkn_collisions
        ),
    }


def audit_slots(a_path: Path, b_path: Path) -> dict[str, Any]:
    """Lightweight read-only drift detector — counts per-table row diffs +
    entity (p,k,n) collisions. No mutation. Cheap; runs in well under a
    second on a multi-100-MB catalog."""
    a_ro = duckdb.connect(str(a_path), read_only=True)
    b_ro = duckdb.connect(str(b_path), read_only=True)
    tables = (
        "partitions", "linkage_types", "entities", "concepts",
        "memory_content", "entity_links", "tracked_files",
        "linkage_evidence", "saved_queries", "bitmap_fragments",
    )
    a_counts = {t: _table_count(a_ro, t) for t in tables}
    b_counts = {t: _table_count(b_ro, t) for t in tables}
    a_ro.close()
    b_ro.close()

    mem = duckdb.connect(":memory:")
    mem.execute(f"ATTACH '{a_path}' AS a (READ_ONLY)")
    mem.execute(f"ATTACH '{b_path}' AS b (READ_ONLY)")

    # Entity id-overlap shape
    a_only = _scalar(mem.execute(
        "SELECT COUNT(*) FROM a.entities WHERE id NOT IN (SELECT id FROM b.entities)"
    ))
    b_only = _scalar(mem.execute(
        "SELECT COUNT(*) FROM b.entities WHERE id NOT IN (SELECT id FROM a.entities)"
    ))
    same_id_diff_payload = _scalar(mem.execute("""
        SELECT COUNT(*) FROM a.entities ae JOIN b.entities be USING (id)
        WHERE ae.name <> be.name OR ae.kind <> be.kind
              OR ae.partition_id <> be.partition_id
    """))
    pkn_collisions = _scalar(mem.execute("""
        SELECT COUNT(*) FROM a.entities ae JOIN b.entities be
        ON ae.partition_id = be.partition_id
           AND ae.kind = be.kind
           AND ae.name = be.name
        WHERE ae.id <> be.id
    """))

    # Memory_content overlap (the user-visible drift class)
    mc_a_only = _scalar(mem.execute(
        "SELECT COUNT(*) FROM a.memory_content WHERE entity_id NOT IN (SELECT entity_id FROM b.memory_content)"
    ))
    mc_b_only = _scalar(mem.execute(
        "SELECT COUNT(*) FROM b.memory_content WHERE entity_id NOT IN (SELECT entity_id FROM a.memory_content)"
    ))
    mem.close()

    diffs = [t for t in tables if a_counts[t] != b_counts[t]]

    return {
        "a_counts": a_counts,
        "b_counts": b_counts,
        "tables_with_diff": diffs,
        "entities": {
            "a_only_ids": a_only,
            "b_only_ids": b_only,
            "same_id_diff_payload": same_id_diff_payload,
            "pkn_collisions_different_ids": pkn_collisions,
        },
        "memory_content": {
            "a_only_entity_ids": mc_a_only,
            "b_only_entity_ids": mc_b_only,
        },
        "drift_detected": bool(
            diffs or a_only or b_only or same_id_diff_payload or pkn_collisions
        ),
    }
