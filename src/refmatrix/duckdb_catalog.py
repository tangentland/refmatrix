"""THE catalog schema: the one DuckDB DDL every catalog builder applies.

The Store (`backend.DuckDBBackend.init_catalog`), the replica-merge target
(replica_merge.py) and every test store bootstrap through `init_catalog`
below. Until task S1 (2026-11-19) a second backend kept its own copy of this
schema in store.py; that copy carried the incident notes several tables
here pointed at. S1 deleted it and moved those notes into this file, beside
the tables they explain.

Shape rules:

- Ids come from an explicit `SEQUENCE` plus `DEFAULT nextval('<seq>')` on
  the column (DuckDB has no AUTOINCREMENT); `init_catalog`'s
  `sequence_starts` positions them for a merge target.
- No FOREIGN KEY clauses (see the note at the top of `CATALOG_DDL`): the
  Store issues every cascade DELETE itself (store.py — every entity-delete
  path also deletes from entity_links, concepts, tracked_files, etc.).
"""
from __future__ import annotations

# Default linkage rows — kept in sync with refmatrix.store.DEFAULT_LINKAGES.
# Re-imported there rather than duplicated to avoid drift; this module just
# owns the schema.

SEQUENCES = (
    ("partitions", "id", "seq_partitions_id"),
    ("entities", "id", "seq_entities_id"),
    ("linkage_types", "id", "seq_linkage_types_id"),
)

CATALOG_DDL = """
-- FOREIGN KEY clauses are intentionally omitted on this schema. DuckDB
-- enforces FKs conservatively — UPDATEs on a parent row trigger the check
-- even when the FK column isn't being modified, and bulk INSERTs into
-- self-referential tables fail per-row before the parent is visible.
-- store.py issues every cascade DELETE explicitly (delete_entity,
-- prune_noise, vacuum, etc.), so the references are enforced in the app.
-- The references the app keeps (the second backend's schema declared them
-- until task S1 deleted it, 2026-11-19):
--   * the `partition_id` of entities, saved_queries, tracked_files,
--     derive_stamps, derive_history and pagerank -> partitions(id);
--   * concepts(id), memory_content(entity_id), pagerank(entity_id) ->
--     entities(id), deleted with the entity;
--   * entity_links and linkage_evidence: entity_id and concept_id ->
--     entities(id), deleted with either entity; linkage_id ->
--     linkage_types(id);
--   * linkage_types(inverse_of) -> linkage_types(id).

CREATE TABLE IF NOT EXISTS partitions (
    id          INTEGER PRIMARY KEY DEFAULT nextval('seq_partitions_id'),
    name        TEXT NOT NULL UNIQUE,
    root_path   TEXT,
    kind        TEXT NOT NULL DEFAULT 'repo'
                CHECK (kind IN ('repo','canon','agent-scratch')),
    created_at  DOUBLE NOT NULL,
    meta        TEXT
);

CREATE TABLE IF NOT EXISTS entities (
    id             INTEGER PRIMARY KEY DEFAULT nextval('seq_entities_id'),
    partition_id   INTEGER NOT NULL DEFAULT 1,
    kind           TEXT NOT NULL CHECK (kind IN ('doc', 'code', 'concept', 'memory')),
    path           TEXT,
    name           TEXT NOT NULL,
    tldr           TEXT,
    meta           TEXT,
    created_at     DOUBLE NOT NULL,
    updated_at     DOUBLE NOT NULL,
    protected      INTEGER NOT NULL DEFAULT 0,
    noise          INTEGER NOT NULL DEFAULT 0,
    -- Lowercase underscore-joined identifier form. Populated for kind='concept'
    -- rows so variant-expanded lookups (snake / camelCase / PascalCase-with-
    -- acronym / dash / digit boundary) resolve via a single indexed SELECT
    -- rather than N point lookups. NULL for kind='doc'/'code'.
    canonical_name TEXT,
    -- POSIX-epoch seconds (DOUBLE). When the Lance vector for this row
    -- was last refreshed. NULL = never embedded. Read by `rmx embed`
    -- to decide which entities need (re-)embedding.
    vectors_updated_at DOUBLE,
    UNIQUE(partition_id, kind, name)
);
CREATE INDEX IF NOT EXISTS idx_entities_kind ON entities(kind);
CREATE INDEX IF NOT EXISTS idx_entities_path ON entities(path);
CREATE INDEX IF NOT EXISTS idx_entities_partition ON entities(partition_id);
CREATE INDEX IF NOT EXISTS idx_entities_protected ON entities(protected);
CREATE INDEX IF NOT EXISTS idx_entities_noise ON entities(noise);
-- idx_entities_canonical is created post-init by Store._connect() so the
-- ALTER TABLE ADD COLUMN canonical_name path for legacy catalogs has a
-- chance to run before the index references it. CATALOG_DDL runs on every
-- open, including catalogs created pre-0.3.3.

CREATE TABLE IF NOT EXISTS concepts (
    id          INTEGER PRIMARY KEY,
    description TEXT
);

-- Intuition memory layer (ADR-0001). Sidecar 1:1 with entities where
-- kind='memory'. Keeps the raw observation/note body off of the
-- entities row (which stays a thin metadata header consistent with
-- doc/code/concept) so a recall doesn't have to read content unless
-- explicitly asked, and so embedding extractors can pull content
-- directly without parsing entities.meta.
CREATE TABLE IF NOT EXISTS memory_content (
    entity_id   INTEGER PRIMARY KEY,
    content     TEXT NOT NULL,
    -- Free-form type tag: 'observation' / 'note' / 'decision' / 'feedback'
    -- / ... — not constrained at the DB layer to keep the surface flexible
    -- as new memory subtypes appear. Default 'observation' matches the
    -- intuition import path.
    mtype       TEXT NOT NULL DEFAULT 'observation',
    tags        TEXT,
    metadata    TEXT,
    created_at  DOUBLE NOT NULL,
    updated_at  DOUBLE NOT NULL
);

CREATE TABLE IF NOT EXISTS linkage_types (
    id          INTEGER PRIMARY KEY DEFAULT nextval('seq_linkage_types_id'),
    name        TEXT NOT NULL UNIQUE,
    directed    INTEGER NOT NULL DEFAULT 1,
    inverse_of  INTEGER,
    description TEXT
);

CREATE TABLE IF NOT EXISTS saved_queries (
    partition_id INTEGER NOT NULL DEFAULT 1,
    name TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at DOUBLE NOT NULL,
    PRIMARY KEY (partition_id, name)
);

CREATE TABLE IF NOT EXISTS entity_links (
    entity_id   INTEGER NOT NULL,
    linkage_id  INTEGER NOT NULL,
    concept_id  INTEGER NOT NULL,
    weight      DOUBLE,
    PRIMARY KEY (entity_id, linkage_id, concept_id)
);
CREATE INDEX IF NOT EXISTS idx_entity_links_lk_concept
    ON entity_links(linkage_id, concept_id);

CREATE TABLE IF NOT EXISTS tracked_files (
    partition_id INTEGER NOT NULL DEFAULT 1,
    path         TEXT NOT NULL,
    mtime        DOUBLE NOT NULL,
    last_synced  DOUBLE NOT NULL,
    PRIMARY KEY (partition_id, path)
);

-- WHICH CODE derived the graph in this partition, per ingest pass (bug-039).
-- `tracked_files` answers "did the FILES change"; it answered `35` while this
-- project's own store sat at a 1-bundle floor because the graph had not been
-- re-derived since 0.49.1 — ten days and several ingest changes earlier. A
-- derive carries no freshness signal of its own unless the deriving version is
-- written down, so every pass that writes derived state stamps itself here.
CREATE TABLE IF NOT EXISTS derive_stamps (
    partition_id INTEGER NOT NULL DEFAULT 1,
    pass_name    TEXT NOT NULL,
    version      TEXT NOT NULL,
    derived_at   DOUBLE NOT NULL,
    code_hash    TEXT,
    PRIMARY KEY (partition_id, pass_name)
);

-- WHAT each derive PRODUCED, append-only (task 15.2). `derive_stamps` answers
-- "which code built what is in the store NOW" and upserts, so there is nothing
-- to compare a derive against — and bug-039's own impact figures (31 -> 63
-- bundles, 206 -> 466 nodes) came from a hand-rolled harness that no longer
-- runs. `counts` is the partition's structural shape AFTER the pass, so two
-- derives diff directly and a derive that changed nothing is visibly a no-op.
--
-- Capped per (partition, pass): `global:queues` reached 3,196 rows unbounded
-- (bug-061), and an append-only table with no retention is that defect under a
-- new name. `pruned` records how many rows the insert evicted, so the drop is
-- visible in `rmx derive log` rather than silent.
CREATE TABLE IF NOT EXISTS derive_history (
    id           BIGINT PRIMARY KEY,
    partition_id INTEGER NOT NULL DEFAULT 1,
    pass_name    TEXT NOT NULL,
    version      TEXT NOT NULL,
    code_hash    TEXT,
    derived_at   DOUBLE NOT NULL,
    duration_s   DOUBLE,
    pruned       INTEGER NOT NULL DEFAULT 0,
    counts       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS linkage_evidence (
    entity_id   INTEGER NOT NULL,
    linkage_id  INTEGER NOT NULL,
    concept_id  INTEGER NOT NULL,
    file        TEXT,
    line        INTEGER,
    span_end    INTEGER,
    detail      TEXT
);
CREATE INDEX IF NOT EXISTS idx_evidence_entity
    ON linkage_evidence(entity_id);
CREATE INDEX IF NOT EXISTS idx_evidence_lookup
    ON linkage_evidence(linkage_id, concept_id, entity_id);

-- Phase-3: bitmap fragments live as BLOB rows instead of per-partition
-- files on disk. Serialized BitMap64 (pyroaring) bytes go in `blob`. Empty
-- bitmaps are not stored — the row is DELETEd on flush when the fragment
-- becomes empty.
CREATE TABLE IF NOT EXISTS bitmap_fragments (
    partition_id INTEGER NOT NULL,
    linkage      TEXT NOT NULL,
    blob         BLOB NOT NULL,
    PRIMARY KEY (partition_id, linkage)
);

-- Global PageRank prior (stage 2 of scan-prompt ranking). One centrality
-- score per node per partition; score is the centrality RATIO (pr * N, avg
-- node ≈ 1.0). Recomputed offline by `rmx pagerank`, read as a query-agnostic
-- salience prior. Whole-file snapshot copy carries it to the read replica.
CREATE TABLE IF NOT EXISTS pagerank (
    partition_id INTEGER NOT NULL DEFAULT 1,
    entity_id    INTEGER NOT NULL,
    score        DOUBLE NOT NULL,
    computed_at  DOUBLE NOT NULL,
    PRIMARY KEY (partition_id, entity_id)
);
CREATE INDEX IF NOT EXISTS idx_pagerank_score
    ON pagerank(partition_id, score);

-- Pronoun-deref sidecar (see coref.py). One row per resolved pronoun
-- occurrence; offsets index the exact content string that was resolved
-- (memory_content.content for memories). The resolved TEXT is never stored:
-- symbolic reads the counts, dense re-materializes the substitution at embed
-- time, and this table is the only persistent artifact.
CREATE TABLE IF NOT EXISTS coref_resolutions (
    partition_id INTEGER NOT NULL DEFAULT 1,
    entity_id    INTEGER NOT NULL,
    pos          INTEGER NOT NULL,
    pronoun      TEXT NOT NULL,
    antecedent   TEXT NOT NULL,
    confidence   REAL NOT NULL,
    PRIMARY KEY (partition_id, entity_id, pos)
);

-- Central df-filtered pair inventory with document postings -- the cross-doc
-- substrate for coref (which documents share this pair) and the persisted
-- form of the phrase-tabulation threshold work. Compiled offline by
-- `rmx pairs compile --min-df N`; docs is a roaring-bitmap blob of entity
-- ids. Never on the write hot path.
CREATE TABLE IF NOT EXISTS pair_index (
    partition_id INTEGER NOT NULL DEFAULT 1,
    pair_key     TEXT NOT NULL,
    df           INTEGER NOT NULL,
    docs         BLOB NOT NULL,
    compiled_at  REAL NOT NULL,
    PRIMARY KEY (partition_id, pair_key)
);
CREATE INDEX IF NOT EXISTS idx_pair_index_df
    ON pair_index(partition_id, df);

-- `rel:` lines whose target did not resolve when their doc was ingested
-- (bug-216 R10, 2026-11-13). GMD ingest skips unchanged files, so a target
-- that appears LATER (a rule doc un-ignored, a doc written after its citer)
-- left the citing line dangling until someone edited the citer: 247 lines
-- cite the two rule docs alone. Ingesting a doc / memory / anchor whose name
-- equals `target_name` resolves the row (edge + evidence) and deletes it; a
-- purge of `source_id` deletes it; re-ingesting the citing file replaces its
-- rows. Rebuilt from facts.log (bug-216 R13, `rebuild_index_from_log`): `pending_ref` /
-- `pending_ref_delete` / `pending_refs_clear` events, source named by kind and
-- name, partition-qualified; a source's `tombstone` drops its rows; the
-- compaction dump re-emits the live rows. No PK or index: the table holds the
-- unresolved residue (hundreds of rows), and the writer keeps it duplicate-free
-- (`Store.add_pending_ref`).
CREATE TABLE IF NOT EXISTS pending_refs (
    partition_id INTEGER NOT NULL DEFAULT 1,
    source_id    INTEGER NOT NULL,
    linkage      TEXT NOT NULL,
    target_name  TEXT NOT NULL,
    ref          TEXT NOT NULL,
    file         TEXT NOT NULL,
    line         INTEGER NOT NULL,
    weight       DOUBLE,
    detail       TEXT,
    created_at   DOUBLE NOT NULL
);
"""

def init_catalog(con, *, sequence_starts: dict[str, int] | None = None) -> None:
    """Create sequences + tables on a fresh DuckDB connection.

    `sequence_starts` lets a merge target (replica_merge.py) pre-position
    each sequence at the next free id (max(id_in_source) + 1) so that
    bulk-loaded rows with explicit ids and later `nextval` calls never
    collide. DuckDB can't `ALTER SEQUENCE ... RESTART` once a table column
    DEFAULTs to it, and `DROP SEQUENCE` is blocked by the dependency, so we
    have to set the start at create time.

    Re-running on the same connection is safe — sequences and tables use
    `IF NOT EXISTS`. A caller passing `sequence_starts` should ensure the
    file is fresh.
    """
    starts = sequence_starts or {}
    for _table, _col, seq in SEQUENCES:
        start = starts.get(seq, 1)
        con.execute(f"CREATE SEQUENCE IF NOT EXISTS {seq} START {start}")
    con.execute(CATALOG_DDL)
    upgrade_catalog(con)


# Columns `entities` gained after catalogs already existed, in the order they
# were added. THE list: a fresh catalog and an upgraded one both end with these
# columns appended by ALTER, so every DuckDB catalog (Store, merge target)
# has one column set in one order. bug-113: the
# Store ALTERed `vectors_partition` in on open while `init_catalog` — the
# replica-merge target's builder — never did, and `INSERT INTO entities SELECT
# ae.*` from a Store-built slot failed "13 columns but 14 values".
ENTITY_COLUMN_UPGRADES = (
    ("canonical_name", "TEXT"),
    ("vectors_updated_at", "DOUBLE"),
    ("vectors_partition", "TEXT"),
)


def upgrade_catalog(con) -> "list[str]":
    """Add any `ENTITY_COLUMN_UPGRADES` column `entities` lacks. Idempotent;
    returns the columns it added. `idx_entities_canonical` is created only
    when `canonical_name` is added here, exactly as Store._connect did."""
    have = {r[0] for r in con.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'entities' AND table_catalog = current_database() "
        "AND table_schema = 'main'").fetchall()}
    added = []
    for col, typ in ENTITY_COLUMN_UPGRADES:
        if col in have:
            continue
        con.execute(f"ALTER TABLE entities ADD COLUMN {col} {typ}")
        added.append(col)
        if col == "canonical_name":
            con.execute("CREATE INDEX IF NOT EXISTS idx_entities_canonical "
                        "ON entities(partition_id, kind, canonical_name)")
    return added
