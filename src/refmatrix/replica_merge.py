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
from contextlib import closing
from pathlib import Path
from typing import Any

import duckdb

from refmatrix.backend import attach_file, open_duckdb
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
    tables = (
        "partitions", "linkage_types", "entities", "concepts",
        "memory_content", "entity_links", "tracked_files",
        "linkage_evidence", "saved_queries", "bitmap_fragments",
    )
    # Every connection this function opens is closed on every exit path
    # (bug-113): a connection left open after an error kept slot A ATTACHed,
    # and the daemon's writer reopen then failed "Unique file handle
    # conflict" — leaving the live writer closed and unlocked.
    a_ro = open_duckdb(a_path, read_only=True)
    try:
        b_ro = open_duckdb(b_path, read_only=True)
        try:
            clashes = _partition_collisions(a_ro, b_ro)
            if clashes:
                raise MergeRefused(
                    "slots disagree on partition identity — " + "; ".join(clashes)
                    + ". Partition ids reach every table; the merge refuses rather "
                      "than guess (bug-128)")
            a_counts, b_counts, max_entity, max_partition, max_lt = _probe(
                a_ro, b_ro, tables)
        finally:
            b_ro.close()
    finally:
        a_ro.close()

    # ---- 2. Open target + attach sources -------------------------------
    if dry_run:
        # Dry-run still needs a temp DB to compute the merge plan, but
        # we can use :memory: and skip the file writes.
        con = open_duckdb(":memory:")
    else:
        _unlink_target(target_path)
        con = open_duckdb(target_path)
    try:
        merged_counts, remap_a, remap_b, fresh_alloc_count = _merge_into(
            con, a_path, b_path, tables, dry_run=dry_run,
            max_entity=max_entity, max_partition=max_partition, max_lt=max_lt)
    except BaseException:
        con.close()
        if not dry_run:
            _unlink_target(target_path)          # never leave a half-built merge
        raise
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


def _unlink_target(target_path: Path) -> None:
    """Remove a merge target and its WAL (a stale or half-built file)."""
    for p in (target_path, target_path.with_name(target_path.name + ".wal")):
        if p.exists():
            p.unlink()


class MergeRefused(RuntimeError):
    """The two slots cannot be merged safely; raised before anything is
    written, naming why (bug-128)."""


def _columns(con, table: str, db: "str | None" = None) -> "list[str]":
    """A table's columns, in order, in database `db` (default: the target) —
    read off the catalog, never hand-listed (a hand-listed SET dropped
    `vectors_partition`, bug-113)."""
    return [r[0] for r in con.execute(
        "SELECT column_name FROM duckdb_columns() "
        "WHERE database_name = COALESCE(?, current_database()) AND schema_name = 'main' "
        "AND table_name = ? ORDER BY column_index", [db, table]).fetchall()]


def _set_all(con, table: str, src_db: str, src: str, key: str) -> str:
    """The SET list of a newer-wins UPDATE from source slot `src_db`: every
    target column; `col = src.col` where the source has it, `col = NULL` where
    it predates the column — the winning row exactly as that slot would read
    after the upgrade ALTER, and the same value a BY NAME insert of it gets. A
    slot older than the schema (the global store's 2026-06-20 B has no
    `vectors_partition`) failed the whole merge when a missing column was
    named (ch-bsd r1 b-3)."""
    have = set(_columns(con, table, src_db))
    return ",\n            ".join(
        f"{c} = {src}.{c}" if c in have else f"{c} = NULL"
        for c in _columns(con, table) if c != key)


def _partition_collisions(a_ro, b_ro) -> "list[str]":
    """partitions.name is UNIQUE and partition ids reach every table, so a
    name held under different ids (or an id under different names) cannot be
    merged by `id NOT IN` — the B rows were dropped or the insert failed
    (bug-128). Returns one description per clash; `merge_slots` refuses on a
    non-empty list, `audit_slots` reports it as drift (ch-bsd r2 m-r2-1)."""
    return _partition_clashes(
        dict(a_ro.execute("SELECT name, id FROM partitions").fetchall()),
        dict(b_ro.execute("SELECT name, id FROM partitions").fetchall()))


def _partition_clashes(pa: "dict[str, int]", pb: "dict[str, int]") -> "list[str]":
    """THE partition identity comparison: {name: id} of slot A vs slot B."""
    by_name = sorted(f"{n!r}: A id {pa[n]}, B id {pb[n]}"
                     for n in pa.keys() & pb.keys() if pa[n] != pb[n])
    ia = {v: k for k, v in pa.items()}
    ib = {v: k for k, v in pb.items()}
    by_id = sorted(f"id {i}: A {ia[i]!r}, B {ib[i]!r}"
                   for i in ia.keys() & ib.keys() if ia[i] != ib[i])
    return by_name + by_id


def _merge_linkage_types(con) -> None:
    """linkage_types by NAME (bug-128): refmatrix's own snapshot vs its stale
    slot A failed `Duplicate key "name: part-of"` — one name, different ids.
    A's rows go in as they are; each B row maps to A's id for the same name,
    else keeps its id when free, else gets a fresh one. `remap_lk_b(old_id,
    new_id)` carries every changed B id to the referencing tables
    (entity_links, linkage_evidence, linkage_types.inverse_of)."""
    con.execute("INSERT INTO linkage_types BY NAME SELECT * FROM a.linkage_types")
    con.execute("CREATE TEMP TABLE remap_lk_b (old_id BIGINT, new_id BIGINT)")
    a_by_name = dict(con.execute("SELECT name, id FROM linkage_types").fetchall())
    b_rows = con.execute("SELECT id, name FROM b.linkage_types ORDER BY id").fetchall()
    next_id = max(set(a_by_name.values()) | {bid for bid, _ in b_rows} | {0}) + 1
    remap = {}
    taken: set = set(a_by_name.values())
    for bid, name in b_rows:
        if name in a_by_name:
            tgt = a_by_name[name]
        elif bid not in taken:
            tgt = bid
        else:
            tgt, next_id = next_id, next_id + 1
        taken.add(tgt)
        if tgt != bid:
            remap[bid] = tgt
    if remap:
        con.executemany("INSERT INTO remap_lk_b VALUES (?, ?)", list(remap.items()))
    con.execute("""
        INSERT INTO linkage_types BY NAME
        SELECT bl.* EXCLUDE (id, inverse_of),
               COALESCE(r.new_id, bl.id) AS id,
               COALESCE(ri.new_id, bl.inverse_of) AS inverse_of
        FROM b.linkage_types bl
        LEFT JOIN remap_lk_b r ON r.old_id = bl.id
        LEFT JOIN remap_lk_b ri ON ri.old_id = bl.inverse_of
        WHERE bl.name NOT IN (SELECT name FROM a.linkage_types)
    """)


def _probe(a_ro, b_ro, tables) -> tuple:
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
    return a_counts, b_counts, max_entity, max_partition, max_lt


def _merge_into(con, a_path: Path, b_path: Path, tables, *, dry_run: bool,
                max_entity: int, max_partition: int, max_lt: int) -> tuple:
    """Build the merge on `con` (the target). Rows are copied BY NAME: the
    target's schema is `init_catalog`'s, the Store's own (bug-113), and a
    positional `SELECT *` silently misplaces same-typed columns whenever a
    slot's column order differs."""
    init_catalog(con, sequence_starts={
        "seq_partitions_id":    max_partition + 1,
        "seq_entities_id":      max_entity + REMAP_HEADROOM + 1,
        # headroom: B linkage names that lose their id to A get fresh ids
        "seq_linkage_types_id": max_lt + REMAP_HEADROOM + 1,
    })

    attach_file(con, a_path, "a")
    attach_file(con, b_path, "b")

    # ---- 3. Lookup tables: partitions + linkage_types ------------------
    con.execute("INSERT INTO partitions BY NAME SELECT * FROM a.partitions")
    con.execute("""
        INSERT INTO partitions BY NAME
        SELECT * FROM b.partitions
        WHERE id NOT IN (SELECT id FROM partitions)
    """)
    _merge_linkage_types(con)

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
        INSERT INTO entities BY NAME
        SELECT ae.* FROM a.entities ae
        LEFT JOIN remap_a r ON r.loser_id = ae.id
        WHERE r.loser_id IS NULL
    """)
    con.execute("""
        INSERT INTO entities BY NAME
        SELECT be.* FROM b.entities be
        LEFT JOIN remap_b r ON r.loser_id = be.id
        LEFT JOIN entities m ON m.id = be.id
        WHERE r.loser_id IS NULL AND m.id IS NULL
    """)
    con.execute(f"""
        UPDATE entities AS m
        SET {_set_all(con, "entities", "b", "be", "id")}
        FROM b.entities be
        WHERE m.id = be.id AND be.updated_at > m.updated_at
    """)

    # ---- 6. concepts: drop loser ids, union --------------------------
    con.execute("""
        INSERT INTO concepts BY NAME
        SELECT ac.* FROM a.concepts ac
        LEFT JOIN remap_a r ON r.loser_id = ac.id
        WHERE r.loser_id IS NULL
    """)
    con.execute("""
        INSERT INTO concepts BY NAME
        SELECT bc.* FROM b.concepts bc
        LEFT JOIN remap_b r ON r.loser_id = bc.id
        LEFT JOIN concepts m ON m.id = bc.id
        WHERE r.loser_id IS NULL AND m.id IS NULL
    """)

    # ---- 7. memory_content: newer-wins on entity_id; remap losers ------
    # 7a. Insert non-loser-side memory_content rows from each slot.
    con.execute("""
        INSERT INTO memory_content BY NAME
        SELECT mc.* FROM a.memory_content mc
        LEFT JOIN remap_a r ON r.loser_id = mc.entity_id
        WHERE r.loser_id IS NULL
    """)
    con.execute("""
        INSERT INTO memory_content BY NAME
        SELECT mc.* FROM b.memory_content mc
        LEFT JOIN remap_b r ON r.loser_id = mc.entity_id
        LEFT JOIN memory_content m ON m.entity_id = mc.entity_id
        WHERE r.loser_id IS NULL AND m.entity_id IS NULL
    """)
    # 7b. For shared entity_id rows, pull in B's content when newer.
    con.execute(f"""
        UPDATE memory_content AS m
        SET {_set_all(con, "memory_content", "b", "bc", "entity_id")}
        FROM b.memory_content bc
        WHERE m.entity_id = bc.entity_id AND bc.updated_at > m.updated_at
    """)
    # 7c. Loser-side mc rows: redirect entity_id via remap; insert when
    # canonical has no mc yet, then overwrite when loser's mc is newer.
    # Column lists come from the catalogs (a slot may predate a column).
    for side, remap_t in (("a", "remap_a"), ("b", "remap_b")):
        con.execute(f"""
            INSERT INTO memory_content BY NAME
            SELECT mc.* EXCLUDE (entity_id), r.canonical_id AS entity_id
            FROM {side}.memory_content mc JOIN {remap_t} r ON r.loser_id = mc.entity_id
            LEFT JOIN memory_content m ON m.entity_id = r.canonical_id
            WHERE m.entity_id IS NULL
        """)
        con.execute(f"""
            UPDATE memory_content AS m
            SET {_set_all(con, "memory_content", side, "sub", "entity_id")}
            FROM (
                SELECT mc.* EXCLUDE (entity_id), r.canonical_id
                FROM {side}.memory_content mc JOIN {remap_t} r ON r.loser_id = mc.entity_id
            ) sub
            WHERE m.entity_id = sub.canonical_id AND sub.updated_at > m.updated_at
        """)

    # ---- 8. entity_links: remap both id columns, dedup by PK ----------
    con.execute("""
        INSERT INTO entity_links BY NAME
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
        INSERT INTO entity_links BY NAME
        SELECT COALESCE(rb_e.canonical_id, bl.entity_id) AS entity_id,
               COALESCE(rl.new_id, bl.linkage_id) AS linkage_id,
               COALESCE(rb_c.canonical_id, bl.concept_id) AS concept_id,
               bl.weight
        FROM b.entity_links bl
        LEFT JOIN remap_b rb_e ON rb_e.loser_id = bl.entity_id
        LEFT JOIN remap_b rb_c ON rb_c.loser_id = bl.concept_id
        LEFT JOIN remap_lk_b rl ON rl.old_id = bl.linkage_id
        ON CONFLICT (entity_id, linkage_id, concept_id) DO NOTHING
    """)

    # ---- 9. linkage_evidence: no PK, UNION DISTINCT with remap --------
    con.execute("""
        INSERT INTO linkage_evidence BY NAME
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
                   COALESCE(rl.new_id, le.linkage_id) AS linkage_id,
                   COALESCE(rb_c.canonical_id, le.concept_id) AS concept_id,
                   le.file, le.line, le.span_end, le.detail
            FROM b.linkage_evidence le
            LEFT JOIN remap_b rb_e ON rb_e.loser_id = le.entity_id
            LEFT JOIN remap_b rb_c ON rb_c.loser_id = le.concept_id
            LEFT JOIN remap_lk_b rl ON rl.old_id = le.linkage_id
        )
    """)

    # ---- 10. tracked_files: composite PK, newer last_synced wins ------
    con.execute("INSERT INTO tracked_files BY NAME SELECT * FROM a.tracked_files ON CONFLICT DO NOTHING")
    con.execute("INSERT INTO tracked_files BY NAME SELECT * FROM b.tracked_files ON CONFLICT DO NOTHING")
    con.execute("""
        UPDATE tracked_files AS m
        SET mtime = bt.mtime, last_synced = bt.last_synced
        FROM b.tracked_files bt
        WHERE m.partition_id = bt.partition_id
              AND m.path = bt.path
              AND bt.last_synced > m.last_synced
    """)

    # ---- 11. saved_queries: composite PK, A wins on conflict ---------
    con.execute("INSERT INTO saved_queries BY NAME SELECT * FROM a.saved_queries ON CONFLICT DO NOTHING")
    con.execute("INSERT INTO saved_queries BY NAME SELECT * FROM b.saved_queries ON CONFLICT DO NOTHING")

    # ---- 12. bitmap_fragments: copy union; daemon recomputes ---------
    con.execute("INSERT INTO bitmap_fragments BY NAME SELECT * FROM a.bitmap_fragments")
    con.execute("""
        INSERT INTO bitmap_fragments BY NAME
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
    return merged_counts, remap_a, remap_b, fresh_alloc_count


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
    attach_file(writer_conn, reader_path, alias)
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
        parts_writer = dict(writer_conn.execute("SELECT name, id FROM partitions").fetchall())
        parts_reader = dict(writer_conn.execute(
            f"SELECT name, id FROM {alias}.partitions").fetchall())
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
        partition_collisions = _partition_clashes(parts_writer, parts_reader)
    else:
        a_counts, b_counts = reader_counts, writer_counts
        a_only, b_only = reader_only, writer_only
        mc_a_only, mc_b_only = mc_reader_only, mc_writer_only
        partition_collisions = _partition_clashes(parts_reader, parts_writer)

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
        "partition_collisions": partition_collisions,
        "drift_detected": bool(
            diffs or a_only or b_only or same_id_diff_payload or pkn_collisions
            or partition_collisions
        ),
    }


def audit_slots(a_path: Path, b_path: Path) -> dict[str, Any]:
    """Lightweight read-only drift detector — counts per-table row diffs +
    entity (p,k,n) collisions. No mutation. Cheap; runs in well under a
    second on a multi-100-MB catalog."""
    tables = (
        "partitions", "linkage_types", "entities", "concepts",
        "memory_content", "entity_links", "tracked_files",
        "linkage_evidence", "saved_queries", "bitmap_fragments",
    )
    # Closed on every path, as in merge_slots (bug-113).
    with closing(open_duckdb(a_path, read_only=True)) as a_ro, \
            closing(open_duckdb(b_path, read_only=True)) as b_ro:
        a_counts, b_counts, *_ = _probe(a_ro, b_ro, tables)
        partition_collisions = _partition_collisions(a_ro, b_ro)

    with closing(duckdb.connect(":memory:")) as mem:
        a_only, b_only, same_id_diff_payload, pkn_collisions, mc_a_only, mc_b_only = \
            _audit_overlap(mem, a_path, b_path)

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
        "partition_collisions": partition_collisions,
        "drift_detected": bool(
            diffs or a_only or b_only or same_id_diff_payload or pkn_collisions
            or partition_collisions
        ),
    }


def _audit_overlap(mem, a_path: Path, b_path: Path) -> tuple:
    attach_file(mem, a_path, "a")
    attach_file(mem, b_path, "b")

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
    return a_only, b_only, same_id_diff_payload, pkn_collisions, mc_a_only, mc_b_only
