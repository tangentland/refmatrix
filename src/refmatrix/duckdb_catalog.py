"""Native DuckDB catalog schema (phase-2 of the DuckDB migration).

Mirrors the SQLite `CATALOG_DDL` from refmatrix.store, with a few mechanical
adjustments DuckDB requires:

- `INTEGER PRIMARY KEY AUTOINCREMENT` → an explicit `SEQUENCE` plus
  `DEFAULT nextval('<seq>')` on the column. DuckDB has no AUTOINCREMENT.
- `ON DELETE CASCADE` is dropped from FOREIGN KEY constraints. DuckDB does
  not support cascade actions; the Store already issues the matching
  DELETEs manually (see store.py — every entity-delete path also deletes
  from entity_links, concepts, tracked_files, etc.).

Everything else (CHECK, UNIQUE, FOREIGN KEY, indexes, ON CONFLICT, RETURNING,
INSERT OR IGNORE, PRAGMA table_info) works the same in DuckDB as in SQLite,
so the surrounding query code can stay unchanged.
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
-- DuckDB-specific note: FOREIGN KEY clauses are intentionally omitted on
-- this schema. DuckDB enforces FKs conservatively — UPDATEs on a parent
-- row trigger the check even when the FK column isn't being modified, and
-- bulk INSERTs into self-referential tables fail per-row before the parent
-- is visible. SQLite-side store.py already issues every cascade DELETE
-- explicitly (delete_entity, prune_noise, vacuum, etc.), so app-level
-- enforcement is unchanged. The constraints are documented in store.py
-- alongside the SQLite CATALOG_DDL.

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

-- Intuition memory layer (ADR-0001). Sidecar for entities with
-- kind='memory'. See sqlite CATALOG_DDL for full rationale.
CREATE TABLE IF NOT EXISTS memory_content (
    entity_id   INTEGER PRIMARY KEY,
    content     TEXT NOT NULL,
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

-- WHICH CODE derived this partition's graph, per ingest pass (bug-039). See
-- the SQLite CATALOG_DDL for the incident: `tracked_files` answers "did the
-- FILES change" and cannot see a graph derived by older passes.
CREATE TABLE IF NOT EXISTS derive_stamps (
    partition_id INTEGER NOT NULL DEFAULT 1,
    pass_name    TEXT NOT NULL,
    version      TEXT NOT NULL,
    derived_at   DOUBLE NOT NULL,
    PRIMARY KEY (partition_id, pass_name)
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
-- files on disk. Serialized BitMap64 (pyroaring) bytes go in `blob`. The
-- SQLite backend still uses fragments/<partition>/<linkage>.rb64 files;
-- this table is DuckDB-only. Empty bitmaps are not stored — the row is
-- DELETEd on flush when the fragment becomes empty (matches the file
-- backend's behavior of unlinking the file).
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
"""

# Tables in the order they need to be (re-)populated so foreign keys resolve.
TABLE_LOAD_ORDER = (
    "partitions",
    "linkage_types",
    "entities",
    "concepts",
    "memory_content",
    "entity_links",
    "tracked_files",
    "linkage_evidence",
    "saved_queries",
)


def init_catalog(con, *, sequence_starts: dict[str, int] | None = None) -> None:
    """Create sequences + tables on a fresh DuckDB connection.

    `sequence_starts` lets a migration pre-position each sequence at the
    next free id (max(id_in_source) + 1) so that bulk-loaded rows with
    explicit ids and post-migration `nextval` calls never collide. DuckDB
    can't `ALTER SEQUENCE ... RESTART` once a table column DEFAULTs to it,
    and `DROP SEQUENCE` is blocked by the dependency, so we have to set the
    start at create time.

    Re-running on the same connection is safe — sequences and tables use
    `IF NOT EXISTS`. Migration callers should ensure the file is fresh.
    """
    starts = sequence_starts or {}
    for _table, _col, seq in SEQUENCES:
        start = starts.get(seq, 1)
        con.execute(f"CREATE SEQUENCE IF NOT EXISTS {seq} START {start}")
    con.execute(CATALOG_DDL)
