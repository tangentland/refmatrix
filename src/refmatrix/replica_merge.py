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
  - `bitmap_fragments`: A's rows as they are; every B row has its bits moved
    through `remap_b` (`store.remap_fragment`) and is OR-ed into A's row of
    the same (partition, linkage), or inserted when A has none. Nothing
    rebuilds fragments after the merge -- a flush writes only the rows the
    running daemon dirties -- so a B bit left out here is lost (bug-216 remedy
    r3 S1, bug-227).

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

from refmatrix.backend import attach_file, bulk_write, open_duckdb
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


# Tables a slot written before they existed does not have (bug-216 S2,
# 2026-11-13): `pending_refs` arrived with bug-216 R10, and every writer open
# adds it, but a slot nobody has opened since predates it. Such a slot counts
# 0 rows and contributes none; a missing CORE table still raises.
OPTIONAL_TABLES = frozenset({"pending_refs"})


def _has_table(con, table: str, db: "str | None" = None) -> bool:
    return bool(con.execute(
        "SELECT count(*) FROM duckdb_tables() "
        "WHERE database_name = COALESCE(?, current_database()) AND schema_name = 'main' "
        "AND table_name = ?", [db, table]).fetchone()[0])


def _table_count(con: duckdb.DuckDBPyConnection, table: str, db: "str | None" = None) -> int:
    if table in OPTIONAL_TABLES and not _has_table(con, table, db):
        return 0
    ref = f'{db}."{table}"' if db else f'"{table}"'
    return _scalar(con.execute(f"SELECT COUNT(*) FROM {ref}"))


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
        "pending_refs",
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
        merged_counts, remap_a, remap_b, fresh_alloc_count, fresh_b, frag_remapped = _merge_into(
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
        # B entities moved to a fresh id (two different entities shared an id;
        # bug-216 remedy B2c, bug-227), `[[old, new], ...]`. Reported apart:
        # their VECTORS are not moved -- the Lance row at the old id is
        # whichever slot wrote last, the fresh id has none -- and the merge
        # marks both ids unembedded so the next `rmx embed` re-embeds them.
        "fresh_moved": [[int(o), int(n)] for o, n in sorted(fresh_b.items())],
        "fragment_bits_remapped": frag_remapped,
        "remap": {
            "a_loser_count": len(remap_a),
            # name-losers only (remap_b also carries the fresh moves)
            "b_loser_count": len(remap_b) - len(fresh_b),
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


def _fill_remap(con, table: str, old_col: str, new_col: str,
                remap: "dict[int, int]") -> None:
    """Fill a two-column BIGINT remap temp table from `remap` in ONE set-based
    INSERT (bug-178, 2026-11-09). These went through DuckDB executemany — one
    statement per collision (10,000 in a 2 x 5,000-collision merge) on the
    merge target's raw connection. Empty `remap` writes nothing."""
    bulk_write(
        con,
        f"INSERT INTO {table} ({old_col}, {new_col}) "
        f"SELECT {old_col}, {new_col} FROM {{view}}",
        [old_col, new_col],
        list(remap.items()),
        types={old_col: "int64", new_col: "int64"},
        view=f"_rmx_{table}",
    )


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
    # One set-based INSERT (bug-178): `con` is a raw DuckDBPyConnection, where
    # executemany is one statement per row.
    _fill_remap(con, "remap_lk_b", "old_id", "new_id", remap)
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

    # Two DIFFERENT entities under one id (bug-216 S2 fixture, 2026-11-13): slots
    # that diverged from one copy both allocate the next ids from the same
    # sequence state, so A's new row and B's new row share an id with
    # different (partition, kind, name). The entity steps below read a shared
    # id as ONE entity -- B's newer row overwrote A's, and A's entity, with
    # every row naming it, was lost. B's row moves to a fresh id inside the
    # sequence headroom, and `remap_b` carries every B-side reference to it. A
    # B id that is already a name-loser needs no move (it maps to A's twin);
    # every step that reads B by raw id excludes ALL remap_b losers, moved or
    # name-lost (bug-216 remedy B2, bug-227): an A row at that id is A's.
    fresh_b: dict[int, int] = {}
    next_fresh = max_entity + 1
    for (bid,) in con.execute("""
        SELECT be.id FROM a.entities ae JOIN b.entities be ON ae.id = be.id
        WHERE NOT (ae.partition_id = be.partition_id AND ae.kind = be.kind
                   AND ae.name = be.name)
        ORDER BY be.id
    """).fetchall():
        bid = int(bid)
        if bid in remap_b or bid in remap_a:
            continue
        fresh_b[bid] = next_fresh
        next_fresh += 1
    if len(fresh_b) > REMAP_HEADROOM:
        raise MergeRefused(
            f"{len(fresh_b)} distinct entities share an id across the slots — more than "
            f"the {REMAP_HEADROOM}-id headroom the merge target reserves")
    remap_b.update(fresh_b)

    # Materialize remap as temp tables for SQL joins.
    con.execute("CREATE TEMP TABLE remap_fresh_b (old_id BIGINT, new_id BIGINT)")
    _fill_remap(con, "remap_fresh_b", "old_id", "new_id", fresh_b)
    con.execute("CREATE TEMP TABLE remap_a (loser_id BIGINT, canonical_id BIGINT)")
    con.execute("CREATE TEMP TABLE remap_b (loser_id BIGINT, canonical_id BIGINT)")
    _fill_remap(con, "remap_a", "loser_id", "canonical_id", remap_a)
    _fill_remap(con, "remap_b", "loser_id", "canonical_id", remap_b)

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
    con.execute("""
        INSERT INTO entities BY NAME
        SELECT be.* EXCLUDE (id), f.new_id AS id
        FROM b.entities be JOIN remap_fresh_b f ON f.old_id = be.id
    """)
    con.execute(f"""
        UPDATE entities AS m
        SET {_set_all(con, "entities", "b", "be", "id")}
        FROM b.entities be
        WHERE m.id = be.id AND be.updated_at > m.updated_at
              AND be.id NOT IN (SELECT loser_id FROM remap_b)
    """)

    # A moved entity has no vector at its fresh id, and the Lance row at the old
    # id is whichever slot embedded last (both slots share `vectors/`): mark both
    # entities unembedded so `pending_embeddings` hands them to the next
    # `rmx embed` (bug-216 remedy B2c). Until it runs a dense read can return the
    # old id's vector for either entity -- the merge reply names the ids.
    con.execute("""
        UPDATE entities SET vectors_updated_at = NULL
        WHERE id IN (SELECT new_id FROM remap_fresh_b)
           OR id IN (SELECT old_id FROM remap_fresh_b)
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
    con.execute("""
        INSERT INTO concepts BY NAME
        SELECT bc.* EXCLUDE (id), f.new_id AS id
        FROM b.concepts bc JOIN remap_fresh_b f ON f.old_id = bc.id
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
    # Every remap_b loser is excluded (bug-216 remedy B2a, bug-227): at a
    # name-loser's or a MOVED entity's id the target row is A's, so a raw-id
    # match gave A's memory B's body (step 7c carries B's body to its id).
    con.execute(f"""
        UPDATE memory_content AS m
        SET {_set_all(con, "memory_content", "b", "bc", "entity_id")}
        FROM b.memory_content bc
        WHERE m.entity_id = bc.entity_id AND bc.updated_at > m.updated_at
              AND bc.entity_id NOT IN (SELECT loser_id FROM remap_b)
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

    # ---- 9b. pending_refs (bug-216 S2): remap the source id, dedupe ----
    # A dangling `rel:` ref that binds when its target is ingested; losing it
    # on a merge is the silent loss rev 5 rejected for the rebuild. Same
    # source-id remap as `linkage_evidence`; a row recorded in both slots
    # becomes one (earliest `created_at`). A slot predating the table gives
    # none.
    _pending_sides = [
        f"""SELECT pr.* EXCLUDE (source_id),
                   COALESCE(r.canonical_id, pr.source_id) AS source_id
            FROM {side}.pending_refs pr
            LEFT JOIN {remap_t} r ON r.loser_id = pr.source_id"""
        for side, remap_t in (("a", "remap_a"), ("b", "remap_b"))
        if _has_table(con, "pending_refs", side)]
    if _pending_sides:
        con.execute(f"""
            INSERT INTO pending_refs BY NAME
            SELECT partition_id, source_id, linkage, target_name, file, line,
                   any_value(ref) AS ref, any_value(weight) AS weight,
                   any_value(detail) AS detail, min(created_at) AS created_at
            FROM ({" UNION ALL ".join(_pending_sides)})
            GROUP BY partition_id, source_id, linkage, target_name, file, line
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

    # ---- 12. bitmap_fragments: A's rows + every B bit, remapped ---------
    # Nothing recomputes fragments after the merge (a flush rewrites only the
    # rows the running daemon dirties), so every B bit must land here. B's bits
    # carry B's ids: each goes through `store.remap_fragment(row, remap_b)` --
    # the kernel `repair_fragments(id_map=...)` applies, scoped to B's rows
    # because A's rows hold A's ids -- so a remapped B entity's bit (name-loser
    # or moved) sits on the id it now has. A row only B holds is inserted; a
    # row BOTH hold gets B's remapped bits OR-ed in and A's bits unchanged
    # (bug-216 remedy B2b + r3 S1, bug-227: at bff34c1 a shared row kept A's
    # bits only, so B's moved entity was in `entity_links` and in no bitmap).
    con.execute("INSERT INTO bitmap_fragments BY NAME SELECT * FROM a.bitmap_fragments")
    from pyroaring import BitMap64

    from refmatrix.store import remap_fragment
    a_rows = {(int(pid), str(lk)): bytes(blob) for pid, lk, blob in con.execute(
        "SELECT partition_id, linkage, blob FROM bitmap_fragments").fetchall()}
    fragment_bits_remapped = 0
    for pid, linkage, blob in con.execute(
            "SELECT partition_id, linkage, blob FROM b.bitmap_fragments").fetchall():
        bm, n = remap_fragment(BitMap64.deserialize(bytes(blob)), remap_b)
        fragment_bits_remapped += n
        key = (int(pid), str(linkage))
        if key in a_rows:
            merged = BitMap64.deserialize(a_rows[key]) | bm
            con.execute("UPDATE bitmap_fragments SET blob = ? "
                        "WHERE partition_id = ? AND linkage = ?",
                        [merged.serialize(), pid, linkage])
        else:
            con.execute("INSERT INTO bitmap_fragments (partition_id, linkage, blob) "
                        "VALUES (?, ?, ?)", [pid, linkage, bm.serialize()])

    # ---- 13. Final counts + checkpoint --------------------------------
    merged_counts = {t: _table_count(con, t) for t in tables}

    con.execute("DETACH a")
    con.execute("DETACH b")
    if not dry_run:
        con.execute("CHECKPOINT")
    return merged_counts, remap_a, remap_b, fresh_alloc_count, fresh_b, fragment_bits_remapped


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
        "pending_refs",
    )
    # Use a unique attach alias so we never collide with whatever schema
    # name the writer happens to be using. Also DETACH at the end so a
    # follow-up audit doesn't see a stale ATTACH.
    alias = "_audit_reader"
    attach_file(writer_conn, reader_path, alias)
    try:
        writer_counts = {t: _table_count(writer_conn, t) for t in tables}
        reader_counts = {
            t: _table_count(writer_conn, t, alias)
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
        "pending_refs",
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
