"""
SQLite catalog + Pilosa-style fragment files for bitmap storage.

Mental model (mirrors Pilosa):
- Index    -> the whole .refmatrix/ directory
- Field    -> a linkage type (`mentions`, `calls`, ...)
- Row      -> a concept id
- Column   -> an entity id

One fragment file per linkage at .refmatrix/fragments/<linkage>.rb64,
storing a single BitMap64 with bit positions packed as
`(concept_id << 32) | entity_id`. Slicing a bitmap row out is a
range-mask intersection (Pilosa-style). The catalog lives at
.refmatrix/catalog.db and holds the id<->name maps, linkage metadata, and
the entity_links shadow (kept in sync; used by SQL-side queries like
density/top-N where bitmap iteration would be the slow path).
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

from pyroaring import BitMap, BitMap64

_CONCEPT_WORD_SPLIT_RE = re.compile(r"[\s_\-]+")


def _canonical_for_kind(kind: str, name: str) -> str | None:
    """Compute the canonical_name column value for an entities row.

    Concept entities get the full identifier-aware canonical form (lowercase
    underscore split on whitespace/_/-/camelCase/PascalCase-w-acronym/digit-
    boundary). Doc/code entities get NULL — their literal name is the only
    addressable form and canonicalization would collide unrelated paths."""
    if kind != "concept":
        return None
    from refmatrix.identifier import canonicalize_name
    return canonicalize_name(name)


def _concept_variants(name: str) -> tuple[str, list[str]]:
    """For a multi-word concept name, return (canonical, alias_variants).

    Canonical is the underscore form. Aliases are the space and dash forms
    that differ from canonical. Single-token names return (name, []).
    """
    stripped = name.strip()
    parts = [p for p in _CONCEPT_WORD_SPLIT_RE.split(stripped) if p]
    if len(parts) < 2:
        return stripped, []
    canonical = "_".join(parts)
    variants: list[str] = []
    for v in (" ".join(parts), "-".join(parts)):
        if v != canonical and v not in variants:
            variants.append(v)
    return canonical, variants

# Packing: concept_id occupies the high 32 bits, entity_id the low 32. Both
# come from the same `entities.id` autoincrement so they share a counter; 32
# bits each gives ~4B headroom on each side, well past anything realistic.
_CONCEPT_SHIFT = 32
_ENTITY_MASK = (1 << 32) - 1

# Append-only fact log. Source-of-truth-in-progress: every mutation also
# writes a JSON line to .refmatrix/facts.log unless RMX_LOG=0. The log is
# keyed by names (not auto-IDs), so two branches that ingest disjoint
# material can be merged with a plain text-line merge and rebuilt via
# rebuild_index_from_log(). The catalog and fragments stay authoritative for
# reads; phase-2 will flip that.
LOG_FILENAME = "facts.log"


def _log_enabled() -> bool:
    return os.environ.get("RMX_LOG", "1") not in ("0", "false", "False")

# A single .refmatrix/ root can host multiple named partitions so several agents
# can write to a shared store without colliding on (kind, name). Each entity
# carries a partition_id; fragment files live under fragments/<partition>/.


def default_partition_name(root: "Path") -> str:
    """The default partition for an unconfigured store or CLI invocation:
    the project name (basename of the directory that holds `.refmatrix/`).

    This is THE default — there is no separate baked-in partition. An
    explicit `partition=` argument or the `RMX_PARTITION` env var override
    it; env vars are overrides only, never required to reach the default.
    Store() and the CLI both resolve through here, so the same root always
    maps to the same partition regardless of which layer opens it.

    The user-level global store (`~/.refmatrix`, the hub home) is the one
    exception — it maps to the partition "global" rather than its parent dir
    name, so a bare `rmx` command falling back to it reads/writes the global
    behavior memories."""
    p = Path(root).resolve()
    try:
        from refmatrix.taxonomy import user_home
        if p == user_home().resolve():
            return "global"
    except Exception:
        pass
    return p.parent.name or "default"

CATALOG_DDL = """
CREATE TABLE IF NOT EXISTS partitions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    root_path   TEXT,
    kind        TEXT NOT NULL DEFAULT 'repo'
                CHECK (kind IN ('repo','canon','agent-scratch')),
    created_at  REAL NOT NULL,
    meta        TEXT
);

CREATE TABLE IF NOT EXISTS entities (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    partition_id       INTEGER NOT NULL DEFAULT 1 REFERENCES partitions(id),
    kind               TEXT NOT NULL CHECK (kind IN ('doc', 'code', 'concept', 'memory')),
    path               TEXT,
    name               TEXT NOT NULL,
    tldr               TEXT,
    meta               TEXT,
    created_at         REAL NOT NULL,
    updated_at         REAL NOT NULL,
    protected          INTEGER NOT NULL DEFAULT 0,
    noise              INTEGER NOT NULL DEFAULT 0,
    canonical_name     TEXT,
    vectors_updated_at REAL,
    UNIQUE(partition_id, kind, name)
);
CREATE INDEX IF NOT EXISTS idx_entities_kind ON entities(kind);
CREATE INDEX IF NOT EXISTS idx_entities_path ON entities(path);
-- protected/noise/partition indexes are created in _connect() after the
-- conditional ALTER TABLE; CREATE INDEX here would fail on legacy schemas
-- where the columns don't yet exist (executescript runs all statements
-- top-to-bottom).

CREATE TABLE IF NOT EXISTS concepts (
    id          INTEGER PRIMARY KEY,            -- equals entities.id where kind='concept'
    description TEXT,
    FOREIGN KEY (id) REFERENCES entities(id) ON DELETE CASCADE
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
    tags        TEXT,           -- JSON array
    metadata    TEXT,           -- JSON object
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL,
    FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS linkage_types (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    directed    INTEGER NOT NULL DEFAULT 1,
    inverse_of  INTEGER,
    description TEXT,
    FOREIGN KEY (inverse_of) REFERENCES linkage_types(id)
);

CREATE TABLE IF NOT EXISTS saved_queries (
    partition_id INTEGER NOT NULL DEFAULT 1 REFERENCES partitions(id),
    name TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (partition_id, name)
);

-- Forward index: O(links) entity -> bitmap membership lookup.
-- Lets us purge an entity from every bitmap it appears in without scanning
-- every (linkage, concept) bitmap on disk. Bitmaps remain the source of truth
-- for set algebra; this table is a maintained shadow.
CREATE TABLE IF NOT EXISTS entity_links (
    entity_id   INTEGER NOT NULL,
    linkage_id  INTEGER NOT NULL,
    concept_id  INTEGER NOT NULL,
    weight      REAL,
    PRIMARY KEY (entity_id, linkage_id, concept_id),
    FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE,
    FOREIGN KEY (linkage_id) REFERENCES linkage_types(id),
    FOREIGN KEY (concept_id) REFERENCES entities(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_entity_links_lk_concept
    ON entity_links(linkage_id, concept_id);

-- Files we've successfully ingested, keyed by absolute path. Used by the
-- incremental sync to detect deletes.
CREATE TABLE IF NOT EXISTS tracked_files (
    partition_id INTEGER NOT NULL DEFAULT 1 REFERENCES partitions(id),
    path         TEXT NOT NULL,
    mtime        REAL NOT NULL,
    last_synced  REAL NOT NULL,
    PRIMARY KEY (partition_id, path)
);

-- Evidence: where a linkage was sourced from. Optional; ingesters that know
-- the source location (e.g. semantic ingester walking ast nodes) populate it.
-- The `entity_links` row is authoritative for membership; this table is for
-- explainability and `rmx query --explain`.
CREATE TABLE IF NOT EXISTS linkage_evidence (
    entity_id   INTEGER NOT NULL,
    linkage_id  INTEGER NOT NULL,
    concept_id  INTEGER NOT NULL,
    file        TEXT,
    line        INTEGER,
    span_end    INTEGER,
    detail      TEXT,
    FOREIGN KEY (entity_id)  REFERENCES entities(id)      ON DELETE CASCADE,
    FOREIGN KEY (linkage_id) REFERENCES linkage_types(id),
    FOREIGN KEY (concept_id) REFERENCES entities(id)      ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_evidence_entity
    ON linkage_evidence(entity_id);
CREATE INDEX IF NOT EXISTS idx_evidence_lookup
    ON linkage_evidence(linkage_id, concept_id, entity_id);

-- Global PageRank prior (stage 2 of scan-prompt ranking). One centrality
-- score per node per partition, recomputed offline by `rmx pagerank`. Score
-- is the centrality RATIO (pr * N): an average node ≈ 1.0, hubs > 1. Read as
-- a query-agnostic salience prior; never on the write hot path.
CREATE TABLE IF NOT EXISTS pagerank (
    partition_id INTEGER NOT NULL DEFAULT 1 REFERENCES partitions(id),
    entity_id    INTEGER NOT NULL,
    score        REAL NOT NULL,
    computed_at  REAL NOT NULL,
    PRIMARY KEY (partition_id, entity_id),
    FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_pagerank_score
    ON pagerank(partition_id, score);
"""

DEFAULT_LINKAGES = [
    ("mentions",     1, None, "entity mentions concept"),
    ("defines",      1, None, "entity defines / declares concept"),
    ("calls",        1, None, "entity (function) calls concept (function)"),
    ("called_by",    1, "calls", "inverse of calls"),
    ("imports",      1, None, "entity imports module/concept"),
    ("is_a",         1, None, "concept is a subtype of concept"),
    ("related-to",   0, None, "undirected association"),
    # Provenance: a plan / spec / issue entity specifies a concept that some
    # downstream code is meant to realize. Lets queries trace "what produced
    # this class?" back through the spec that drove it.
    ("specifies",    1, None, "plan/spec entity specifies concept"),
    ("specified_by", 1, "specifies", "inverse of specifies"),
    # Cross-partition canonicalization: a per-partition concept points at a
    # canonical concept (typically in a 'canon' partition) so queries in one
    # repo's partition can find sibling concepts in another repo's partition
    # via the canon hub. Stored in entity_links (partition-blind) so traversal
    # works without enumerating partitions.
    ("same_as",      0, None, "concept is the same as a canonical concept"),
    # Reinforcement semantics for the intuition memory layer (ADR-0001).
    # Weighted: + reinforces / − contradicts feeds the signed-reinforcement
    # scoring signal. recalls / informs carry zero default weight but mark
    # provenance edges between memories and concepts.
    ("reinforces",   1, None, "memory amplifies confidence in a concept"),
    ("contradicts",  1, None, "memory undermines confidence in a concept"),
    ("recalls",      1, None, "memory references / recalls a concept"),
    ("informs",      1, None, "memory provides context informing a concept"),
]


# Verb canonicalization. The graph mixes two naming conventions: GMD/memory
# `rel:` edges are kebab-case (the regex only admits `[a-z0-9-]`), while the
# seeded defaults + code emitters (ADR ingest, graphify map) historically used
# snake_case for the same relations. Where both forms denote the SAME relation
# they would otherwise live under two `linkage_types` ids — a split-brain that
# makes `related-to:x` miss the `related_to` edges and vice versa. This map
# folds each known snake twin to its kebab canonical at every verb choke point
# (link/query/bitmap-key), so no emitter can re-split. Snake verbs WITHOUT a
# kebab twin (`same_as`, `is_a`, `called_by`, `similar_to`, `shares_data_with`,
# `specified_by`) are intentional distinct relations and are NOT remapped.
_VERB_ALIASES = {
    "related_to": "related-to",
}


def _canonical_verb(name: str) -> str:
    """Fold a linkage verb to its canonical form (see `_VERB_ALIASES`).
    Idempotent: a verb with no alias (incl. already-canonical) returns
    unchanged, so applying this at multiple layers is harmless."""
    return _VERB_ALIASES.get(name, name)


@dataclass
class Entity:
    id: int
    kind: str
    name: str
    path: str | None
    tldr: str | None
    meta: dict
    protected: bool = False
    noise: bool = False


class Store:
    def __init__(
        self,
        root: Path,
        partition: str | None = None,
        backend: str | None = None,
        read_only: bool = False,
    ):
        from refmatrix.backend import select_backend
        self.root = Path(root).resolve()
        self._backend = select_backend(backend, root=self.root)
        # Read-only mode: open the backend connection in read-only mode and
        # skip every migration / ALTER / repair / backfill path. Used by
        # `--via-replica` CLI ops that open a frozen reader-slot file
        # without disturbing it. Writes raise via the backend driver.
        self._read_only: bool = bool(read_only)
        # `db_path` historically pointed at catalog.db. Backend chooses the
        # filename now; legacy SQLite stores stay at catalog.db, DuckDB-native
        # stores use catalog.duckdb so the two can coexist during migration.
        self.db_path = self.root / self._backend.db_filename
        # Snapshot-tier policy: read_only Stores prefer the daemon-maintained
        # snapshot file `catalog.read.duckdb` over the writer's primary file
        # because the writer never holds the snapshot open exclusively,
        # making it multi-process-safe to open READ_ONLY without the
        # "Could not set lock on catalog.A.duckdb" collision.
        #
        # Resolution order: snapshot file → legacy `read_only.duckdb`
        # symlink → primary catalog file. The legacy symlink path stays
        # because pre-snapshot-tier stores still rely on it; once a
        # snapshot has been materialized the symlink path never gets hit.
        # Falls back to the primary file when neither exists (fresh
        # install, daemon never started).
        if self._read_only and self._backend.kind == "duckdb":
            snap = self.root / "catalog.read.duckdb"
            try:
                if snap.exists():
                    self.db_path = snap
                else:
                    symlink = self.root / "read_only.duckdb"
                    if symlink.exists() or symlink.is_symlink():
                        self.db_path = symlink
            except OSError:
                pass
        # bitmaps_dir is the legacy per-(linkage, concept) layout. Kept as an
        # attribute so the migration path can find and convert it.
        self.bitmaps_dir = self.root / "bitmaps"
        self.fragments_dir = self.root / "fragments"
        self.queries_dir = self.root / "queries"
        # Active partition. Explicit arg wins, then the RMX_PARTITION env
        # override, then the project-scoped default (basename of the
        # project dir). The partition row is auto-created on first connect
        # — passing a brand-new name "just works" without an explicit
        # register.
        self._partition_name: str = (
            partition
            or os.environ.get("RMX_PARTITION")
            or default_partition_name(self.root)
        )
        self._partition_id: int | None = None
        self._conn: sqlite3.Connection | None = None
        # Phase-1 of the DuckDB migration: when RMX_READ_VIA_DUCKDB is set,
        # SELECTs on this Store are routed through a DuckDB sqlite_scanner
        # view of catalog.db. Writes still go through SQLite. The DuckDB view
        # and read shim are constructed lazily on first read.
        self._read_via_duckdb: bool = os.environ.get("RMX_READ_VIA_DUCKDB") in (
            "1", "true", "True",
        )
        self._duck_view = None
        self._read_conn = None
        # See `deferred_links()`. None = direct mode (default); list =
        # buffering link/weighted_link calls for one bulk_link flush.
        self._link_buffer: list[tuple[str, int, int, float | None]] | None = None
        self._link_protect_buffer: list[tuple[int, int]] | None = None
        # See `transaction()`. True = we've issued BEGIN; subsequent
        # nested scopes are no-ops.
        self._in_transaction: bool = False
        # Lazy-loaded fragment cache: linkage_name -> BitMap64. Populated on
        # first read/write of any concept under that linkage; flushed back to
        # disk via flush_fragments() (called from close()). The Store is bound
        # to one partition for its lifetime, so the cache is implicitly
        # partition-scoped.
        self._fragments: dict[str, BitMap64] = {}
        self._dirty_fragments: set[str] = set()
        # When True, _log_event is a no-op. Used by rebuild_index_from_log so
        # replaying events through link()/upsert_entity() doesn't duplicate
        # them back into the log.
        self._replay_mode = False

    @property
    def partition_name(self) -> str:
        return self._partition_name

    @property
    def partition_id(self) -> int:
        if self._partition_id is None:
            self._connect()
        assert self._partition_id is not None
        return self._partition_id

    def _partition_fragments_dir(self) -> Path:
        return self.fragments_dir / self._partition_name

    @property
    def log_path(self) -> Path:
        return self.root / LOG_FILENAME

    def _log_event(self, op: str, **fields) -> None:
        """Append one JSON event to facts.log if RMX_LOG=1 and not replaying.

        Called after the SQLite commit on every mutation. Phase 1: log runs
        alongside the catalog as a verification target. Phase 2 will gate the
        catalog writes off and treat the log as authoritative."""
        if self._replay_mode or not _log_enabled():
            return
        rec = {"ts": time.time(), "op": op, **fields}
        line = json.dumps(rec, sort_keys=True, ensure_ascii=False)
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    # ---- lifecycle ---------------------------------------------------------

    def init(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        # Legacy `bitmaps/` dir is only read for migration off the
        # historical per-(linkage, concept) layout. Stop creating it
        # on fresh inits -- nothing writes there, and an empty dir
        # next to fragments/ confuses operators looking for state.
        # `bitmaps_dir` attribute stays so migration code can still
        # find an existing one if a legacy store is upgraded.
        # `fragments/` is also DuckDB-irrelevant (BLOBs in catalog),
        # but the SQLite backend writes there.
        if self._backend.kind == "sqlite":
            self.fragments_dir.mkdir(exist_ok=True)
            self._partition_fragments_dir().mkdir(parents=True, exist_ok=True)
        self.queries_dir.mkdir(exist_ok=True)
        with self._connect() as con:
            if self._backend.kind == "sqlite":
                # SQLite-only: ensure schema. DuckDB backend already ran the
                # native DDL inside _connect()'s init_catalog path.
                con.executescript(CATALOG_DDL)
            existing = {r[0] for r in con.execute("SELECT name FROM linkage_types")}
            for name, directed, inverse_name, desc in DEFAULT_LINKAGES:
                if name in existing:
                    continue
                con.execute(
                    "INSERT INTO linkage_types(name, directed, description) VALUES (?,?,?)",
                    (name, directed, desc),
                )
            for name, directed, inverse_name, desc in DEFAULT_LINKAGES:
                if inverse_name is None:
                    continue
                con.execute(
                    "UPDATE linkage_types SET inverse_of=(SELECT id FROM linkage_types WHERE name=?) WHERE name=?",
                    (inverse_name, name),
                )

    def _connect(self):
        if self._conn is None:
            if self._read_only:
                # Fast path: replica reader. Open the backend in read-only
                # mode, skip every migration / repair / backfill path, set
                # the partition id from disk if present. The schema is
                # assumed current (the replica file was just file-copied
                # from a 0.3.3+ primary that already migrated). Writes via
                # this connection will raise from the driver, which is
                # exactly what we want.
                con = self._backend.connect(self.db_path, read_only=True)
                self._conn = con
                # Resolve partition_id without writing.
                try:
                    row = con.execute(
                        "SELECT id FROM partitions WHERE name=?",
                        (self._partition_name,),
                    ).fetchone()
                    self._partition_id = (
                        row[0] if row else 1  # 1 = the default partition (id 1)
                    )
                except Exception:
                    self._partition_id = 1
                return self._conn
            con = self._backend.connect(self.db_path)
            if self._backend.kind == "sqlite":
                # Self-heal schema on first connect. CATALOG_DDL is fully
                # idempotent (all CREATE TABLE/INDEX IF NOT EXISTS), so existing
                # catalogs created before later schema additions transparently
                # gain the new tables (e.g. linkage_evidence, tracked_files,
                # entity_links).
                con.executescript(CATALOG_DDL)
                # ALTER TABLE isn't idempotent — add post-DDL columns conditionally.
                # CATALOG_DDL deliberately omits the indexes for these columns
                # because executescript runs top-to-bottom and would fail on a
                # legacy schema before the ALTER below has a chance to add them.
                cols = {r[1] for r in con.execute("PRAGMA table_info(entities)")}
                if "protected" not in cols:
                    con.execute(
                        "ALTER TABLE entities ADD COLUMN protected INTEGER NOT NULL DEFAULT 0"
                    )
                if "noise" not in cols:
                    con.execute(
                        "ALTER TABLE entities ADD COLUMN noise INTEGER NOT NULL DEFAULT 0"
                    )
                if "canonical_name" not in cols:
                    con.execute(
                        "ALTER TABLE entities ADD COLUMN canonical_name TEXT"
                    )
                if "vectors_updated_at" not in cols:
                    con.execute(
                        "ALTER TABLE entities ADD COLUMN vectors_updated_at REAL"
                    )
                # Indexes that don't depend on partition_id are safe before
                # the legacy migration; the partition-aware index waits until
                # after _migrate_to_partitions_if_needed() has added the
                # column.
                con.execute(
                    "CREATE INDEX IF NOT EXISTS idx_entities_protected ON entities(protected)"
                )
                con.execute(
                    "CREATE INDEX IF NOT EXISTS idx_entities_noise ON entities(noise)"
                )
                con.commit()
                self._conn = con
                # Schema migration: pre-partition catalogs need partition_id added
                # plus a table rebuild to swap UNIQUE/PK constraints. Runs at most
                # once per catalog. Must come before the fragments migration so
                # the resolved partition_id is stable.
                self._migrate_to_partitions_if_needed()
                # Now that partition_id is guaranteed to exist on entities (via the
                # CATALOG_DDL fresh-schema path or the migration above), the
                # partition-aware indexes are safe to create unconditionally.
                con.execute(
                    "CREATE INDEX IF NOT EXISTS idx_entities_partition "
                    "ON entities(partition_id)"
                )
                con.execute(
                    "CREATE INDEX IF NOT EXISTS idx_entities_canonical "
                    "ON entities(partition_id, kind, canonical_name)"
                )
                con.commit()
            else:
                # DuckDB native catalog: schema is created up-front via the
                # native DDL (refmatrix.duckdb_catalog). All tables/indexes/
                # columns are present from the start, so the SQLite legacy
                # migration paths (partitions backfill, post-DDL CREATE INDEX)
                # are not needed.
                self._backend.init_catalog(con)
                self._conn = con
                # ALTER ADD COLUMN for catalogs created before canonical_name
                # was part of the schema (pre-0.3.3). DuckDB supports both
                # ALTER TABLE ADD COLUMN IF NOT EXISTS and the conditional
                # information_schema check below for portability across
                # DuckDB versions.
                cols = {
                    r[0] for r in con.execute(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name='entities'"
                    ).fetchall()
                }
                if "canonical_name" not in cols:
                    con.execute("ALTER TABLE entities ADD COLUMN canonical_name TEXT")
                    con.execute(
                        "CREATE INDEX IF NOT EXISTS idx_entities_canonical "
                        "ON entities(partition_id, kind, canonical_name)"
                    )
                if "vectors_updated_at" not in cols:
                    con.execute(
                        "ALTER TABLE entities ADD COLUMN vectors_updated_at DOUBLE"
                    )
                # ADR-0001 / Phase B: relax the kind CHECK constraint on
                # pre-Phase-B catalogs so 'memory' rows can land. DuckDB
                # auto-names CHECK constraints; query duckdb_constraints
                # to find the one that mentions 'doc'/'code'/'concept'
                # but not 'memory', drop it, leave Python-side validation
                # in upsert_entity as the kind whitelist. Idempotent: a
                # post-migration catalog returns no matching row.
                self._migrate_entities_kind_check_if_needed()
            # Ensure the active partition row exists and resolve the active
            # partition_id. Auto-creates the partition the first time a Store
            # is opened with a new name (a fresh `rmx init` lands you in the
            # project-scoped default without a register step).
            self._ensure_partition()
            # Backfill any DEFAULT_LINKAGES that were introduced after this
            # catalog was first init'd (e.g. 'same_as' for canon hops). Pure
            # INSERT OR IGNORE — fresh catalogs see this as a no-op since
            # init() already seeded the same set.
            for name, directed, _inverse, desc in DEFAULT_LINKAGES:
                con.execute(
                    "INSERT OR IGNORE INTO linkage_types(name, directed, description) "
                    "VALUES (?,?,?)",
                    (name, directed, desc),
                )
            con.commit()
            # One-shot backfill of canonical_name for legacy concept rows. Runs
            # exactly once per catalog (after the ALTER ADD COLUMN above
            # populated the column as NULL). Safe to re-run: WHERE clause
            # skips rows already populated.
            self._backfill_canonical_name_if_needed()
        # One-shot migration: collapse legacy per-(linkage, concept) .rb files
        # into per-linkage BitMap64 fragments. Runs at most once per catalog.
        self._migrate_legacy_bitmaps_if_needed()
        # Move pre-partition fragments/<linkage>.rb64 into fragments/local/.
        # Idempotent and a no-op once done.
        self._migrate_fragments_to_partitions_if_needed()
        return self._conn

    def _migrate_to_partitions_if_needed(self) -> None:
        """Add partition_id columns and rebuild entities/tracked_files/saved_queries
        for the new UNIQUE/PK constraints. SQLite can't ALTER a UNIQUE/PK
        constraint in place, so each affected table goes through the standard
        12-step rebuild dance. All pre-existing rows backfill to partition_id=1
        (the project-scoped default partition)."""
        assert self._conn is not None
        con = self._conn
        ent_cols = {r[1] for r in con.execute("PRAGMA table_info(entities)")}
        tf_cols = {r[1] for r in con.execute("PRAGMA table_info(tracked_files)")}
        if "partition_id" in ent_cols and "partition_id" in tf_cols:
            return
        # Insert default partition before any FK-bearing rebuild references it.
        # Pre-partition rows backfill to id=1 = the project-scoped default.
        con.execute(
            "INSERT OR IGNORE INTO partitions(id, name, kind, created_at) "
            "VALUES (1, ?, 'repo', ?)",
            (default_partition_name(self.root), time.time()),
        )
        # Must commit before PRAGMA foreign_keys = OFF — the pragma is
        # silently ignored while a transaction is open.
        con.commit()
        con.execute("PRAGMA foreign_keys = OFF")
        try:
            if "partition_id" not in ent_cols:
                # Carry forward post-0.3.3 columns the legacy ALTER added
                # to the old table (canonical_name, vectors_updated_at) so
                # the rebuild doesn't drop them on the way through.
                con.executescript("""
                    DROP TABLE IF EXISTS entities_new;
                    CREATE TABLE entities_new (
                        id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                        partition_id       INTEGER NOT NULL DEFAULT 1
                                             REFERENCES partitions(id),
                        kind               TEXT NOT NULL CHECK (kind IN ('doc','code','concept','memory')),
                        path               TEXT,
                        name               TEXT NOT NULL,
                        tldr               TEXT,
                        meta               TEXT,
                        created_at         REAL NOT NULL,
                        updated_at         REAL NOT NULL,
                        protected          INTEGER NOT NULL DEFAULT 0,
                        noise              INTEGER NOT NULL DEFAULT 0,
                        canonical_name     TEXT,
                        vectors_updated_at REAL,
                        UNIQUE(partition_id, kind, name)
                    );
                    INSERT INTO entities_new
                        (id, partition_id, kind, path, name, tldr, meta,
                         created_at, updated_at, protected, noise,
                         canonical_name, vectors_updated_at)
                    SELECT id, 1, kind, path, name, tldr, meta,
                           created_at, updated_at, protected, noise,
                           canonical_name, vectors_updated_at
                    FROM entities;
                    DROP TABLE entities;
                    ALTER TABLE entities_new RENAME TO entities;
                    CREATE INDEX idx_entities_kind ON entities(kind);
                    CREATE INDEX idx_entities_path ON entities(path);
                    CREATE INDEX idx_entities_partition ON entities(partition_id);
                    CREATE INDEX idx_entities_protected ON entities(protected);
                    CREATE INDEX idx_entities_noise ON entities(noise);
                """)
            if "partition_id" not in tf_cols:
                con.executescript("""
                    DROP TABLE IF EXISTS tracked_files_new;
                    CREATE TABLE tracked_files_new (
                        partition_id INTEGER NOT NULL DEFAULT 1
                                       REFERENCES partitions(id),
                        path         TEXT NOT NULL,
                        mtime        REAL NOT NULL,
                        last_synced  REAL NOT NULL,
                        PRIMARY KEY (partition_id, path)
                    );
                    INSERT INTO tracked_files_new (partition_id, path, mtime, last_synced)
                    SELECT 1, path, mtime, last_synced FROM tracked_files;
                    DROP TABLE tracked_files;
                    ALTER TABLE tracked_files_new RENAME TO tracked_files;
                """)
            sq_cols = {r[1] for r in con.execute("PRAGMA table_info(saved_queries)")}
            if "partition_id" not in sq_cols:
                con.executescript("""
                    DROP TABLE IF EXISTS saved_queries_new;
                    CREATE TABLE saved_queries_new (
                        partition_id INTEGER NOT NULL DEFAULT 1
                                       REFERENCES partitions(id),
                        name TEXT NOT NULL,
                        body TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        PRIMARY KEY (partition_id, name)
                    );
                    INSERT INTO saved_queries_new (partition_id, name, body, created_at)
                    SELECT 1, name, body, created_at FROM saved_queries;
                    DROP TABLE saved_queries;
                    ALTER TABLE saved_queries_new RENAME TO saved_queries;
                """)
            con.commit()
        finally:
            con.execute("PRAGMA foreign_keys = ON")

    def _migrate_entities_kind_check_if_needed(self) -> None:
        """DuckDB-only: relax the kind CHECK constraint on `entities` so
        pre-Phase-B catalogs accept 'memory' rows. The DDL was tightened
        to allow 4 kinds in Phase B; existing stores baked the old 3-kind
        constraint into their catalog at init time and DuckDB 1.5 does
        not support `ALTER TABLE DROP CONSTRAINT` for CHECK constraints.

        Strategy: detect the old CHECK via duckdb_constraints, then
        rebuild the entities table — CREATE entities_new with the new
        constraint, INSERT SELECT all rows, DROP old, RENAME. Sequence
        binding survives because the column DEFAULT references the
        named sequence rather than copying its current value.

        Idempotent: a post-migration catalog returns no matching row
        and the call is a no-op."""
        assert self._conn is not None
        if self._backend.kind != "duckdb":
            return
        con = self._conn
        try:
            rows = con.execute(
                "SELECT constraint_name, constraint_text "
                "FROM duckdb_constraints "
                "WHERE table_name='entities' AND constraint_type='CHECK'"
            ).fetchall()
        except Exception:
            # Older DuckDB releases may not expose duckdb_constraints.
            # Without visibility we can't safely rebuild — leave the
            # old CHECK in place and let upsert raise a Python-side
            # ConstraintException for 'memory' rows.
            return
        needs_rebuild = False
        for _cname, ctext in rows:
            text = (ctext or "").lower()
            if "memory" in text:
                continue
            if all(k in text for k in ("'doc'", "'code'", "'concept'")):
                needs_rebuild = True
                break
        if not needs_rebuild:
            return
        # Resync the seq_entities_id default-sequence past the current max
        # id so the rebuild's INSERT SELECT (which preserves ids) doesn't
        # collide with future nextval() calls. The DEFAULT clause on the
        # new column references the same named sequence so its state
        # carries over implicitly; this select_setval is belt-and-
        # suspenders against an empty table where the sequence was never
        # advanced past 1.
        max_id = con.execute(
            "SELECT COALESCE(MAX(id), 0) FROM entities"
        ).fetchone()[0]
        try:
            con.execute(
                "SELECT setval('seq_entities_id', ?)",
                (max(int(max_id), 1),),
            )
        except Exception:
            # setval is supported on DuckDB sequences; if it fails we
            # accept the risk — the rebuild itself still preserves ids.
            pass
        try:
            con.execute("BEGIN")
            con.execute("""
                CREATE TABLE entities_kind_migrate (
                    id                 INTEGER PRIMARY KEY
                                         DEFAULT nextval('seq_entities_id'),
                    partition_id       INTEGER NOT NULL DEFAULT 1,
                    kind               TEXT NOT NULL
                                         CHECK (kind IN ('doc','code','concept','memory')),
                    path               TEXT,
                    name               TEXT NOT NULL,
                    tldr               TEXT,
                    meta               TEXT,
                    created_at         DOUBLE NOT NULL,
                    updated_at         DOUBLE NOT NULL,
                    protected          INTEGER NOT NULL DEFAULT 0,
                    noise              INTEGER NOT NULL DEFAULT 0,
                    canonical_name     TEXT,
                    vectors_updated_at DOUBLE,
                    UNIQUE(partition_id, kind, name)
                )
            """)
            con.execute("""
                INSERT INTO entities_kind_migrate
                    (id, partition_id, kind, path, name, tldr, meta,
                     created_at, updated_at, protected, noise,
                     canonical_name, vectors_updated_at)
                SELECT id, partition_id, kind, path, name, tldr, meta,
                       created_at, updated_at, protected, noise,
                       canonical_name, vectors_updated_at
                FROM entities
            """)
            con.execute("DROP TABLE entities")
            con.execute("ALTER TABLE entities_kind_migrate RENAME TO entities")
            # Recreate the secondary indexes that lived on the old table.
            for idx_sql in (
                "CREATE INDEX IF NOT EXISTS idx_entities_kind ON entities(kind)",
                "CREATE INDEX IF NOT EXISTS idx_entities_path ON entities(path)",
                "CREATE INDEX IF NOT EXISTS idx_entities_partition ON entities(partition_id)",
                "CREATE INDEX IF NOT EXISTS idx_entities_protected ON entities(protected)",
                "CREATE INDEX IF NOT EXISTS idx_entities_noise ON entities(noise)",
                "CREATE INDEX IF NOT EXISTS idx_entities_canonical "
                "ON entities(partition_id, kind, canonical_name)",
            ):
                con.execute(idx_sql)
            con.execute("COMMIT")
        except Exception:
            try:
                con.execute("ROLLBACK")
            except Exception:
                pass
            raise

    def rename_partition(self, old: str, new: str) -> None:
        """Rename partition `old` to `new`: update the catalog row and move
        its on-disk fragment + vector directories so partition-scoped paths
        keep resolving. Idempotent-safe guards:

          - raises ValueError if `old` doesn't exist or `new` already exists
            (the `partitions.name` column is UNIQUE);
          - refuses to overwrite an existing `new` fragment/vector dir.

        Entity rows reference the partition by id, not name, so they need no
        update. A daemon bound to `old` should be restarted afterwards."""
        if old == new:
            return
        con = self._connect()
        if con.execute(
            "SELECT 1 FROM partitions WHERE name=?", (old,)
        ).fetchone() is None:
            raise ValueError(f"no partition named {old!r}")
        if con.execute(
            "SELECT 1 FROM partitions WHERE name=?", (new,)
        ).fetchone() is not None:
            raise ValueError(f"partition {new!r} already exists")
        # Move dirs first: if a target dir already exists, bail before
        # mutating the catalog so name and on-disk layout never diverge.
        moves: list[tuple[Path, Path]] = []
        for base in (self.fragments_dir, self.root / "vectors"):
            src = base / old
            if src.is_dir():
                dst = base / new
                if dst.exists():
                    raise ValueError(
                        f"{dst} already exists; refusing to overwrite"
                    )
                moves.append((src, dst))
        for src, dst in moves:
            src.rename(dst)
        con.execute(
            "UPDATE partitions SET name=? WHERE name=?", (new, old)
        )
        con.commit()
        # Keep the in-memory binding correct if we renamed the active one.
        if self._partition_name == old:
            self._partition_name = new

    def merge_partition(
        self, src_name: str, dst_name: str, *, dry_run: bool = False,
    ) -> dict:
        """Merge SRC partition into DST partition. Drops SRC on success.

        Built for the `memory-<project>` → `<project>` consolidation: the
        memory partition split made cross-partition wikilinks unresolvable
        and produced orphan rows during ingest. Single-partition layout
        kills both bug classes; recall's existing kind=memory filter
        already separates memory hits at query time.

        Behavior:
          * For every entity in SRC with no (kind, name) collision in
            DST: reparent (UPDATE partition_id = DST.id).
          * For colliding entities: remap SRC entity_id → DST entity_id
            across entity_links, linkage_evidence, memory_content,
            concepts. Prefer the longer/non-empty memory_content side.
            Delete the SRC entity row.
          * saved_queries: reparent; skip dup name.
          * tracked_files: reparent; on path dup keep the row with the
            newer last_synced.
          * Lance vector datasets under `vectors/<src>/`: any `*.lance`
            sub-tree gets moved/merged into `vectors/<dst>/`. Per-kind
            files are concatenated via lance.dataset.merge when both
            exist; otherwise the file is renamed.
          * Bitmap fragment dirs under `fragments/<src>/`: same shape.
          * Drop SRC `partitions` row when empty.

        `dry_run=True` returns the resolved counts without mutating.
        Returns `{src, dst, entities_reparented, entities_merged,
        saved_queries, tracked_files, dry_run}`.
        """
        con = self._connect()
        src_row = con.execute(
            "SELECT id FROM partitions WHERE name=?", (src_name,),
        ).fetchone()
        dst_row = con.execute(
            "SELECT id FROM partitions WHERE name=?", (dst_name,),
        ).fetchone()
        if src_row is None:
            raise ValueError(f"no partition named {src_name!r}")
        if dst_row is None:
            raise ValueError(f"no partition named {dst_name!r}")
        if src_row["id"] == dst_row["id"]:
            return {
                "src": src_name, "dst": dst_name,
                "entities_reparented": 0, "entities_merged": 0,
                "saved_queries": 0, "tracked_files": 0,
                "dry_run": dry_run, "note": "src == dst",
            }
        src_id = int(src_row["id"])
        dst_id = int(dst_row["id"])

        # Classify SRC entities: collide vs reparent.
        collisions: list[tuple[int, int, str, str]] = []
        reparents: list[int] = []
        for r in con.execute(
            "SELECT id, kind, name FROM entities WHERE partition_id=?",
            (src_id,),
        ).fetchall():
            dst_match = con.execute(
                "SELECT id FROM entities "
                "WHERE partition_id=? AND kind=? AND name=?",
                (dst_id, r["kind"], r["name"]),
            ).fetchone()
            if dst_match is None:
                reparents.append(int(r["id"]))
            else:
                collisions.append(
                    (int(r["id"]), int(dst_match["id"]),
                     r["kind"], r["name"])
                )

        sq_count = con.execute(
            "SELECT COUNT(*) AS n FROM saved_queries WHERE partition_id=?",
            (src_id,),
        ).fetchone()["n"]
        tf_count = con.execute(
            "SELECT COUNT(*) AS n FROM tracked_files WHERE partition_id=?",
            (src_id,),
        ).fetchone()["n"]

        if dry_run:
            return {
                "src": src_name, "dst": dst_name,
                "entities_reparented": len(reparents),
                "entities_merged": len(collisions),
                "saved_queries": int(sq_count),
                "tracked_files": int(tf_count),
                "dry_run": True,
            }

        # ---- collisions: remap child refs, prefer longer content ------
        for src_eid, dst_eid, _kind, _name in collisions:
            # memory_content: prefer the side whose content is longer
            # (longer == more authoritative; null/empty loses).
            src_mc = con.execute(
                "SELECT content, mtype, tags, metadata, created_at, "
                "       updated_at FROM memory_content WHERE entity_id=?",
                (src_eid,),
            ).fetchone()
            dst_mc = con.execute(
                "SELECT content FROM memory_content WHERE entity_id=?",
                (dst_eid,),
            ).fetchone()
            if src_mc is not None:
                src_len = len(src_mc["content"] or "")
                dst_len = len(dst_mc["content"] or "") if dst_mc else 0
                if src_len > dst_len:
                    if dst_mc is None:
                        con.execute(
                            "INSERT INTO memory_content "
                            "(entity_id, content, mtype, tags, metadata, "
                            " created_at, updated_at) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (dst_eid, src_mc["content"], src_mc["mtype"],
                             src_mc["tags"], src_mc["metadata"],
                             src_mc["created_at"], src_mc["updated_at"]),
                        )
                    else:
                        con.execute(
                            "UPDATE memory_content "
                            "SET content=?, mtype=?, tags=?, metadata=?, "
                            "    updated_at=? "
                            "WHERE entity_id=?",
                            (src_mc["content"], src_mc["mtype"],
                             src_mc["tags"], src_mc["metadata"],
                             src_mc["updated_at"], dst_eid),
                        )
                con.execute(
                    "DELETE FROM memory_content WHERE entity_id=?",
                    (src_eid,),
                )
            # entity_links: replace SRC id with DST id (both source +
            # concept sides). Conflicts (same (entity_id, linkage_id,
            # concept_id) row already exists for DST) are dropped — the
            # PK constraint already covered them.
            con.execute(
                "DELETE FROM entity_links "
                "WHERE entity_id=? AND concept_id IN ("
                "  SELECT concept_id FROM entity_links WHERE entity_id=?"
                ")",
                (dst_eid, src_eid),
            )
            con.execute(
                "UPDATE entity_links SET entity_id=? WHERE entity_id=?",
                (dst_eid, src_eid),
            )
            con.execute(
                "DELETE FROM entity_links "
                "WHERE concept_id=? AND entity_id IN ("
                "  SELECT entity_id FROM entity_links WHERE concept_id=?"
                ")",
                (dst_eid, src_eid),
            )
            con.execute(
                "UPDATE entity_links SET concept_id=? WHERE concept_id=?",
                (dst_eid, src_eid),
            )
            # linkage_evidence: re-point both sides.
            con.execute(
                "UPDATE linkage_evidence SET entity_id=? WHERE entity_id=?",
                (dst_eid, src_eid),
            )
            con.execute(
                "UPDATE linkage_evidence SET concept_id=? WHERE concept_id=?",
                (dst_eid, src_eid),
            )
            # concepts: PK is entity_id; if a concept row sits on the
            # SRC id, the DST id may or may not already have one.
            con.execute(
                "INSERT OR IGNORE INTO concepts (id, description) "
                "SELECT ?, description FROM concepts WHERE id=?",
                (dst_eid, src_eid),
            )
            con.execute("DELETE FROM concepts WHERE id=?", (src_eid,))
            # Finally drop the SRC entity row.
            con.execute("DELETE FROM entities WHERE id=?", (src_eid,))

        # ---- reparent the non-colliding survivors --------------------
        if reparents:
            placeholders = ",".join("?" * len(reparents))
            con.execute(
                f"UPDATE entities SET partition_id=? "
                f"WHERE id IN ({placeholders})",
                [dst_id, *reparents],
            )

        # ---- saved_queries / tracked_files ---------------------------
        # saved_queries: composite PK (partition_id, name); skip dup names.
        for r in con.execute(
            "SELECT name, body, created_at FROM saved_queries "
            "WHERE partition_id=?",
            (src_id,),
        ).fetchall():
            con.execute(
                "INSERT OR IGNORE INTO saved_queries "
                "(partition_id, name, body, created_at) "
                "VALUES (?, ?, ?, ?)",
                (dst_id, r["name"], r["body"], r["created_at"]),
            )
        con.execute(
            "DELETE FROM saved_queries WHERE partition_id=?", (src_id,),
        )
        # tracked_files: prefer the newer last_synced on collision.
        for r in con.execute(
            "SELECT path, mtime, last_synced FROM tracked_files "
            "WHERE partition_id=?",
            (src_id,),
        ).fetchall():
            existing = con.execute(
                "SELECT last_synced FROM tracked_files "
                "WHERE partition_id=? AND path=?",
                (dst_id, r["path"]),
            ).fetchone()
            if existing is None:
                con.execute(
                    "INSERT INTO tracked_files "
                    "(partition_id, path, mtime, last_synced) "
                    "VALUES (?, ?, ?, ?)",
                    (dst_id, r["path"], r["mtime"], r["last_synced"]),
                )
            elif r["last_synced"] > existing["last_synced"]:
                con.execute(
                    "UPDATE tracked_files SET mtime=?, last_synced=? "
                    "WHERE partition_id=? AND path=?",
                    (r["mtime"], r["last_synced"], dst_id, r["path"]),
                )
        con.execute(
            "DELETE FROM tracked_files WHERE partition_id=?", (src_id,),
        )

        # ---- on-disk side: vectors + fragments -----------------------
        import shutil as _shutil
        for base in (self.root / "vectors", self.fragments_dir):
            src_dir = base / src_name
            if not src_dir.is_dir():
                continue
            dst_dir = base / dst_name
            dst_dir.mkdir(parents=True, exist_ok=True)
            for child in src_dir.iterdir():
                target = dst_dir / child.name
                if not target.exists():
                    child.rename(target)
                # Existing target: best-effort skip. Per-kind Lance
                # dataset merge is tricky (id collisions, schema
                # checks); leaving the SRC copy in place to be
                # rebuilt by `rmx embed --gc` + re-embed is safer.
            try:
                src_dir.rmdir()
            except OSError:
                pass

        # ---- drop SRC partition row ----------------------------------
        con.execute("DELETE FROM partitions WHERE id=?", (src_id,))
        con.commit()

        if self._partition_name == src_name:
            self._partition_name = dst_name
            self._partition_id = dst_id

        return {
            "src": src_name, "dst": dst_name,
            "entities_reparented": len(reparents),
            "entities_merged": len(collisions),
            "saved_queries": int(sq_count),
            "tracked_files": int(tf_count),
            "dry_run": False,
        }

    def with_partition(self, name: str):
        """Context manager: temporarily switch self._partition_id to the
        partition row matching `name` for the duration of the block, then
        restore. Auto-creates the partition row if new. The daemon binds
        to one partition for writes, but memory ops need to land in
        whichever partition the CLI requested; this lets the daemon
        re-target per call without re-binding the Store.

        Not safe under concurrent ops on the same Store — wrap with
        d._store_lock at the daemon op layer."""
        from contextlib import contextmanager

        @contextmanager
        def _scope():
            self._connect()
            prev_id = self._partition_id
            prev_name = self._partition_name
            if name == prev_name:
                yield self
                return
            con = self._conn
            con.execute(
                "INSERT OR IGNORE INTO partitions(name, kind, created_at) "
                "VALUES (?, 'repo', ?)",
                (name, time.time()),
            )
            con.commit()
            row = con.execute(
                "SELECT id FROM partitions WHERE name=?", (name,)
            ).fetchone()
            self._partition_id = row[0]
            self._partition_name = name
            # Drop the cached vector store too — its bound partition
            # would mismatch if we don't.
            old_vs = getattr(self, "_vs", None)
            self._vs = None
            try:
                yield self
            finally:
                self._partition_id = prev_id
                self._partition_name = prev_name
                self._vs = old_vs

        return _scope()

    def _ensure_partition(self) -> None:
        """Resolve self._partition_id, auto-creating the partition row if the
        configured name is new. Always runs after _migrate_to_partitions_if_needed
        so the partitions table is guaranteed to exist."""
        assert self._conn is not None
        con = self._conn
        # Ensure the active partition row exists. The active partition IS the
        # default (project-scoped) unless an explicit arg/RMX_PARTITION
        # overrode it — either way a brand-new name auto-registers on first
        # connect, no separate baked-in default row needed.
        con.execute(
            "INSERT OR IGNORE INTO partitions(name, kind, created_at) "
            "VALUES (?, 'repo', ?)",
            (self._partition_name, time.time()),
        )
        con.commit()
        row = con.execute(
            "SELECT id FROM partitions WHERE name=?", (self._partition_name,)
        ).fetchone()
        self._partition_id = row[0]

    def _migrate_fragments_to_partitions_if_needed(self) -> None:
        """Move pre-partition fragment files (fragments/<linkage>.rb64) into
        fragments/<default-partition>/ so they're visible to a Store opened on
        the default partition. Idempotent — once moved, subsequent calls find
        nothing to do."""
        if not self.fragments_dir.exists():
            return
        loose = [p for p in self.fragments_dir.glob("*.rb64") if p.is_file()]
        if not loose:
            return
        target_dir = self.fragments_dir / default_partition_name(self.root)
        target_dir.mkdir(parents=True, exist_ok=True)
        for src in loose:
            dst = target_dir / src.name
            if dst.exists():
                # A per-partition file already won — discard the loose copy.
                src.unlink()
            else:
                src.replace(dst)

    def _migrate_legacy_bitmaps_if_needed(self) -> None:
        """If .refmatrix/bitmaps/ holds per-concept .rb files but
        .refmatrix/fragments/ is empty (or missing fragment files for those
        linkages), pack each linkage's per-concept bitmaps into a single
        BitMap64 fragment, then delete the originals."""
        if not self.bitmaps_dir.exists():
            return
        legacy_linkages = [
            d for d in self.bitmaps_dir.iterdir()
            if d.is_dir() and any(d.glob("*.rb"))
        ]
        if not legacy_linkages:
            return
        self._partition_fragments_dir().mkdir(parents=True, exist_ok=True)
        for ld in legacy_linkages:
            linkage = ld.name
            frag_path = self._fragment_path(linkage)
            if frag_path.exists():
                # Already migrated for this linkage; skip but still clean up
                # the legacy directory so the migration is idempotent.
                for rb in ld.glob("*.rb"):
                    rb.unlink()
                try:
                    ld.rmdir()
                except OSError:
                    pass
                continue
            frag = BitMap64()
            for rb in ld.glob("*.rb"):
                try:
                    cid = int(rb.stem)
                except ValueError:
                    continue
                bm = BitMap.deserialize(rb.read_bytes())
                base = cid << _CONCEPT_SHIFT
                for eid in bm:
                    frag.add(base | eid)
            if len(frag) > 0:
                tmp = frag_path.with_suffix(".rb64.tmp")
                tmp.write_bytes(frag.serialize())
                tmp.replace(frag_path)
            for rb in ld.glob("*.rb"):
                rb.unlink()
            try:
                ld.rmdir()
            except OSError:
                pass

    def _read(self):
        """Return the connection used for SELECTs. Defaults to the SQLite
        write connection. When RMX_READ_VIA_DUCKDB is set, returns a DuckDB
        sqlite_scanner view that exposes the same `con.execute(sql, params)`
        cursor surface (see refmatrix.duckdb_view.ReadConnection)."""
        if not self._read_via_duckdb:
            return self._connect()
        if self._read_conn is None:
            # Force the SQLite catalog into existence (schema, migrations,
            # default linkages, partition row) before DuckDB attaches it —
            # DuckDB opens read-only and won't trigger our self-heal.
            self._connect()
            from refmatrix.duckdb_view import DuckCatalogView

            self._duck_view = DuckCatalogView(self.db_path)
            self._read_conn = self._duck_view.read_connection()
        return self._read_conn

    def close(self) -> None:
        # Persist any in-memory fragment edits before tearing down the
        # connection. Safe to call on a never-modified Store (no-op).
        # Each step is best-effort and isolated so a failure in one
        # (e.g. flush_fragments raising on a DuckDB FatalException-
        # invalidated catalog) does not skip the connection close that
        # actually releases the file lock. Without this, a failed
        # rotation/refresh leaves the slot file locked for the rest of
        # the process's lifetime.
        try:
            self.flush_fragments()
        except Exception:
            pass
        if self._duck_view is not None:
            try:
                self._duck_view.close()
            except Exception:
                pass
            self._duck_view = None
            self._read_conn = None
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    # ---- entities / concepts ----------------------------------------------

    def upsert_entity(
        self,
        kind: str,
        name: str,
        path: str | None = None,
        tldr: str | None = None,
        meta: dict | None = None,
        protected: bool = False,
    ) -> int:
        if kind not in ("doc", "code", "concept", "memory"):
            raise ValueError(f"unknown kind: {kind}")
        now = time.time()
        meta_json = json.dumps(meta) if meta else None
        prot = 1 if protected else 0
        con = self._connect()
        pid = self._partition_id
        # canonical_name is populated for concept rows only; doc/code retain
        # their literal name as the only addressable form.
        canon = _canonical_for_kind(kind, name)
        # On conflict: only ratchet protected upward — re-ingestion by an
        # auto-source must never clear a flag the user set manually.
        # updated_at advances ONLY when an embedding-/content-relevant field
        # (path/tldr/meta, or a first-time canonical_name) actually changes. A
        # no-op re-ingest of an unchanged entity must NOT bump it: otherwise
        # `pending_embeddings` (vectors_updated_at < updated_at) re-stales every
        # row each cycle (the ~2709-vector re-embed tax), and replica-merge /
        # concept-timeline both read updated_at as "last real write".
        cur = con.execute(
            """
            INSERT INTO entities(partition_id, kind, name, path, tldr, meta,
                                 created_at, updated_at, protected,
                                 canonical_name)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(partition_id, kind, name) DO UPDATE SET
                path = COALESCE(excluded.path, entities.path),
                tldr = COALESCE(excluded.tldr, entities.tldr),
                meta = COALESCE(excluded.meta, entities.meta),
                updated_at = CASE WHEN
                    (excluded.path IS NOT NULL AND (entities.path IS NULL OR entities.path <> excluded.path))
                 OR (excluded.tldr IS NOT NULL AND (entities.tldr IS NULL OR entities.tldr <> excluded.tldr))
                 OR (excluded.meta IS NOT NULL AND (entities.meta IS NULL OR entities.meta <> excluded.meta))
                 OR (entities.canonical_name IS NULL AND excluded.canonical_name IS NOT NULL)
                THEN excluded.updated_at ELSE entities.updated_at END,
                protected = GREATEST(entities.protected, excluded.protected),
                canonical_name = COALESCE(entities.canonical_name,
                                          excluded.canonical_name)
            RETURNING id
            """,
            (pid, kind, name, path, tldr, meta_json, now, now, prot, canon),
        )
        eid = cur.fetchone()[0]
        if kind == "concept":
            con.execute(
                "INSERT OR IGNORE INTO concepts(id, description) VALUES (?, ?)",
                (eid, (meta or {}).get("description")),
            )
        self._maybe_commit(con)
        self._log_event(
            "entity",
            kind=kind, name=name, path=path, tldr=tldr, meta=meta,
        )
        if protected:
            self._log_event("protect", kind=kind, name=name, value=1)
        return eid

    def bulk_upsert_entity(
        self,
        rows: list[tuple[str, str, str | None, str | None, dict | None]],
    ) -> list[int]:
        """Upsert many entities in one prepared statement, returning the
        resulting ids in input order.

        Each input row is `(kind, name, path, tldr, meta)`. Same on-conflict
        semantics as `upsert_entity` (path/tldr/meta COALESCE, protected
        ratchets up only). Logging emits one entity event per row so the
        fact log remains replayable.

        Intended for the file-walk + metadata passes where N is in the
        thousands -- a single transaction-wrapped executemany cuts per-row
        cursor + COMMIT overhead.
        """
        if not rows:
            return []
        now = time.time()
        pid = self._partition_id
        con = self._connect()
        payload = [
            (pid, kind, name, path, tldr,
             json.dumps(meta) if meta else None, now, now, 0,
             _canonical_for_kind(kind, name))
            for (kind, name, path, tldr, meta) in rows
        ]
        # DuckDB does not support RETURNING from executemany, so the upsert
        # is followed by a single SELECT against the (partition_id, kind,
        # name) unique index. Cheaper than N round-trips.
        #
        # DuckDB's `executemany` runs INSERT...ON CONFLICT row-by-row (no
        # engine-level batching) — the dominant cost on big ingests (~1.3s
        # per 1k-row chunk in profiling). So under DuckDB we push the rows as
        # one Arrow batch and INSERT...SELECT, which IS vectorized (same trick
        # as `bulk_link`). Falls back to executemany when the batch has
        # intra-batch duplicate (kind, name) keys: DuckDB rejects two
        # conflicting rows in a single ON CONFLICT DO UPDATE, whereas
        # executemany merges them sequentially.
        has_dups = len({(p[1], p[2]) for p in payload}) != len(payload)
        if self._backend.kind == "duckdb" and not has_dups:
            import pyarrow as pa
            schema = pa.schema([
                ("partition_id", pa.int64()), ("kind", pa.string()),
                ("name", pa.string()), ("path", pa.string()),
                ("tldr", pa.string()), ("meta", pa.string()),
                ("created_at", pa.float64()), ("updated_at", pa.float64()),
                ("protected", pa.int64()), ("canonical_name", pa.string()),
            ])
            tbl = pa.table({
                "partition_id":   [p[0] for p in payload],
                "kind":           [p[1] for p in payload],
                "name":           [p[2] for p in payload],
                "path":           [p[3] for p in payload],
                "tldr":           [p[4] for p in payload],
                "meta":           [p[5] for p in payload],
                "created_at":     [p[6] for p in payload],
                "updated_at":     [p[7] for p in payload],
                "protected":      [p[8] for p in payload],
                "canonical_name": [p[9] for p in payload],
            }, schema=schema)
            con._duck.register("_rmx_bulk_entities", tbl)
            try:
                con._duck.execute(
                    "INSERT INTO entities(partition_id, kind, name, path, "
                    "tldr, meta, created_at, updated_at, protected, "
                    "canonical_name) SELECT partition_id, kind, name, path, "
                    "tldr, meta, created_at, updated_at, protected, "
                    "canonical_name FROM _rmx_bulk_entities "
                    "ON CONFLICT(partition_id, kind, name) DO UPDATE SET "
                    "path = COALESCE(excluded.path, entities.path), "
                    "tldr = COALESCE(excluded.tldr, entities.tldr), "
                    "meta = COALESCE(excluded.meta, entities.meta), "
                    "updated_at = CASE WHEN "
                    "  (excluded.path IS NOT NULL AND (entities.path IS NULL OR entities.path <> excluded.path)) "
                    "OR (excluded.tldr IS NOT NULL AND (entities.tldr IS NULL OR entities.tldr <> excluded.tldr)) "
                    "OR (excluded.meta IS NOT NULL AND (entities.meta IS NULL OR entities.meta <> excluded.meta)) "
                    "OR (entities.canonical_name IS NULL AND excluded.canonical_name IS NOT NULL) "
                    "THEN excluded.updated_at ELSE entities.updated_at END, "
                    "protected = GREATEST(entities.protected, "
                    "excluded.protected), "
                    "canonical_name = COALESCE(entities.canonical_name, "
                    "excluded.canonical_name)"
                )
            finally:
                con._duck.unregister("_rmx_bulk_entities")
        else:
            con.executemany(
                """
                INSERT INTO entities(partition_id, kind, name, path, tldr, meta,
                                     created_at, updated_at, protected,
                                     canonical_name)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(partition_id, kind, name) DO UPDATE SET
                    path = COALESCE(excluded.path, entities.path),
                    tldr = COALESCE(excluded.tldr, entities.tldr),
                    meta = COALESCE(excluded.meta, entities.meta),
                    updated_at = CASE WHEN
                        (excluded.path IS NOT NULL AND (entities.path IS NULL OR entities.path <> excluded.path))
                     OR (excluded.tldr IS NOT NULL AND (entities.tldr IS NULL OR entities.tldr <> excluded.tldr))
                     OR (excluded.meta IS NOT NULL AND (entities.meta IS NULL OR entities.meta <> excluded.meta))
                     OR (entities.canonical_name IS NULL AND excluded.canonical_name IS NOT NULL)
                    THEN excluded.updated_at ELSE entities.updated_at END,
                    protected = GREATEST(entities.protected, excluded.protected),
                    canonical_name = COALESCE(entities.canonical_name,
                                              excluded.canonical_name)
                """,
                payload,
            )
        # Look up the ids keyed by (kind, name). Under DuckDB, register the
        # keys as an Arrow table and JOIN: one scan of `entities` regardless
        # of batch size. The old `(kind, name) IN (...)` list forced callers
        # to chunk, and each chunk's IN-list scanned the table -- O(chunks)
        # scans, pathological when re-ingesting into a large existing store.
        # SQLite keeps the IN-list (no Arrow registration there).
        keys = [(kind, name) for (kind, name, *_rest) in rows]
        if self._backend.kind == "duckdb":
            import pyarrow as pa
            ktbl = pa.table({
                "kind": pa.array([k for (k, _n) in keys], type=pa.string()),
                "name": pa.array([n for (_k, n) in keys], type=pa.string()),
            })
            con._duck.register("_rmx_id_keys", ktbl)
            try:
                id_rows = con._duck.execute(
                    "SELECT e.kind, e.name, e.id FROM entities e "
                    "JOIN _rmx_id_keys k "
                    "ON e.kind = k.kind AND e.name = k.name "
                    "WHERE e.partition_id = ?",
                    [pid],
                ).fetchall()
            finally:
                con._duck.unregister("_rmx_id_keys")
        else:
            placeholders = ",".join("(?,?)" for _ in keys)
            flat: list = [pid]
            for kind, name in keys:
                flat.extend([kind, name])
            id_rows = con.execute(
                f"SELECT kind, name, id FROM entities "
                f"WHERE partition_id=? AND (kind, name) IN ({placeholders})",
                flat,
            ).fetchall()
        id_by_key = {(r[0], r[1]): r[2] for r in id_rows}
        ids: list[int] = [id_by_key[(k, n)] for (k, n) in keys]
        # Concepts need a row in the concepts table; insert any missing.
        concept_payload = [
            (ids[i], (rows[i][4] or {}).get("description"))
            for i in range(len(rows))
            if rows[i][0] == "concept"
        ]
        if concept_payload:
            if self._backend.kind == "duckdb":
                import pyarrow as pa
                ctbl = pa.table({
                    "id": pa.array([c[0] for c in concept_payload],
                                   type=pa.int64()),
                    "description": pa.array([c[1] for c in concept_payload],
                                            type=pa.string()),
                })
                con._duck.register("_rmx_bulk_concepts", ctbl)
                try:
                    con._duck.execute(
                        "INSERT INTO concepts(id, description) "
                        "SELECT id, description FROM _rmx_bulk_concepts "
                        "ON CONFLICT(id) DO NOTHING"
                    )
                finally:
                    con._duck.unregister("_rmx_bulk_concepts")
            else:
                con.executemany(
                    "INSERT OR IGNORE INTO concepts(id, description) "
                    "VALUES (?, ?)",
                    concept_payload,
                )
        self._maybe_commit(con)
        for (kind, name, path, tldr, meta) in rows:
            self._log_event(
                "entity",
                kind=kind, name=name, path=path, tldr=tldr, meta=meta,
            )
        return ids

    def add_concept(
        self,
        name: str,
        description: str | None = None,
        protected: bool = False,
    ) -> int:
        canonical, variants = _concept_variants(name)
        cid = self.upsert_entity(
            kind="concept",
            name=canonical,
            meta={"description": description} if description else None,
            protected=protected,
        )
        for variant in variants:
            vid = self.upsert_entity(
                kind="concept",
                name=variant,
                meta={"description": f"alias of '{canonical}'"},
            )
            if vid != cid:
                self.link("same_as", vid, cid)
        return cid

    # ---- intuition memory layer (ADR-0001, Phase B) -----------------------

    def add_memory(
        self,
        name: str,
        content: str,
        mtype: str = "observation",
        tags: list[str] | None = None,
        metadata: dict | None = None,
        protected: bool = False,
    ) -> int:
        """Upsert a memory entity + its memory_content sidecar in one shot.

        Returns the entity id. Re-running with the same name updates the
        content (preserving created_at, ratcheting updated_at). Tags and
        metadata are stored as JSON text — readers parse them on the way
        out via get_memory().
        """
        eid = self.upsert_entity(kind="memory", name=name, protected=protected)
        now = time.time()
        tags_json = json.dumps(tags) if tags else None
        meta_json = json.dumps(metadata) if metadata else None
        con = self._connect()
        con.execute(
            """
            INSERT INTO memory_content
                (entity_id, content, mtype, tags, metadata,
                 created_at, updated_at)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(entity_id) DO UPDATE SET
                content    = excluded.content,
                mtype      = excluded.mtype,
                tags       = excluded.tags,
                metadata   = excluded.metadata,
                updated_at = excluded.updated_at
            """,
            (eid, content, mtype, tags_json, meta_json, now, now),
        )
        con.commit()
        # Log the body too. upsert_entity above logged the entity row, but the
        # sidecar content was previously unlogged — so log-replay / catch-up /
        # `rebuild --from-log` reconstructed memory entities WITHOUT bodies.
        # Replayed by `_apply_one_event` + `rebuild_index_from_log`.
        self._log_event(
            "memory_content", kind="memory", name=name,
            content=content, mtype=mtype, tags=tags, metadata=metadata,
        )
        return eid

    def get_memory(self, name_or_id: str | int) -> dict | None:
        """Resolve a memory by name (current partition) or id (any partition)
        and return entity + sidecar fields as a dict. Returns None if not
        found or if the row exists but isn't kind='memory'."""
        self._connect()
        if isinstance(name_or_id, int) or (
            isinstance(name_or_id, str) and name_or_id.isdigit()
        ):
            eid = int(name_or_id)
            ent_row = self._read().execute(
                "SELECT id, kind, name, partition_id FROM entities WHERE id=?",
                (eid,),
            ).fetchone()
        else:
            ent_row = self._read().execute(
                "SELECT id, kind, name, partition_id FROM entities "
                "WHERE partition_id=? AND kind='memory' AND name=?",
                (self._partition_id, name_or_id),
            ).fetchone()
        if ent_row is None or ent_row["kind"] != "memory":
            return None
        mc_row = self._read().execute(
            "SELECT content, mtype, tags, metadata, created_at, updated_at "
            "FROM memory_content WHERE entity_id=?",
            (ent_row["id"],),
        ).fetchone()
        return {
            "id": ent_row["id"],
            "name": ent_row["name"],
            "partition_id": ent_row["partition_id"],
            "content": mc_row["content"] if mc_row else None,
            "mtype": mc_row["mtype"] if mc_row else None,
            "tags": json.loads(mc_row["tags"]) if mc_row and mc_row["tags"] else [],
            "metadata":
                json.loads(mc_row["metadata"])
                if mc_row and mc_row["metadata"] else {},
            "created_at": mc_row["created_at"] if mc_row else None,
            "updated_at": mc_row["updated_at"] if mc_row else None,
        }

    def find_memory_any_partition(self, name: str) -> dict | None:
        """Resolve a memory by NAME across ALL partitions (not just the active
        one) and return it via `get_memory(id)`. Used by `rmx context` to pull
        a mention neighbor's parent-doc body when that body lives in a
        different partition than the anchor (e.g. session cards live in
        `sessions-<project>` while the co-mention concept resolves in the
        project's memory/code partition). Read-only.

        A name can exist as a content-less stub in one partition and the full
        card in another (cross-partition mirrors of session/memory ids), so we
        pick the row with the LONGEST content — the real body — rather than
        the lowest partition_id, which can land on an empty mirror."""
        row = self._read().execute(
            "SELECT e.id FROM entities e "
            "LEFT JOIN memory_content mc ON mc.entity_id = e.id "
            "WHERE e.name=? AND e.kind='memory' "
            "ORDER BY length(COALESCE(mc.content, '')) DESC, e.partition_id "
            "LIMIT 1",
            (name,),
        ).fetchone()
        return self.get_memory(int(row["id"])) if row else None

    @staticmethod
    def _tag_filter_sql(
        tags: "list[str] | None", mode: str = "all",
    ) -> "tuple[str, list[Any]]":
        """Build a WHERE fragment that matches `mc.tags` (a json.dumps'd list)
        against `tags`. Uses a quoted LIKE (`%"tag"%`) so it matches whole
        tokens — `"git"` never matches inside `"github"`. `mode='all'` = AND
        (every tag present), `'any'` = OR. Returns ('', []) when no tags."""
        if not tags:
            return "", []
        clauses = ["mc.tags LIKE ?" for _ in tags]
        params: list[Any] = [f'%"{tg}"%' for tg in tags]
        joiner = " AND " if mode == "all" else " OR "
        return " AND (" + joiner.join(clauses) + ")", params

    def iter_memories(
        self, *, mtype: str | None = None, limit: int | None = None,
        tags: "list[str] | None" = None, tags_match: str = "all",
    ) -> Iterator[dict]:
        """Stream memories in the active partition (id ascending). `mtype`
        filters by sidecar mtype; `tags` filters by sidecar tags (AND when
        tags_match='all', OR when 'any'). None returns all kinds."""
        self._connect()
        sql = (
            "SELECT e.id, e.name, mc.content, mc.mtype, mc.tags, mc.metadata, "
            "       mc.created_at, mc.updated_at "
            "FROM entities e "
            "LEFT JOIN memory_content mc ON mc.entity_id = e.id "
            "WHERE e.partition_id=? AND e.kind='memory'"
        )
        params: list[Any] = [self._partition_id]
        if mtype is not None:
            sql += " AND mc.mtype = ?"
            params.append(mtype)
        tag_sql, tag_params = self._tag_filter_sql(tags, tags_match)
        sql += tag_sql
        params.extend(tag_params)
        sql += " ORDER BY e.id"
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        for row in self._read().execute(sql, params).fetchall():
            yield {
                "id": row["id"],
                "name": row["name"],
                "content": row["content"],
                "mtype": row["mtype"],
                "tags": json.loads(row["tags"]) if row["tags"] else [],
                "metadata":
                    json.loads(row["metadata"]) if row["metadata"] else {},
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }

    def search_memories(
        self, query: str, *, limit: int = 20,
        tags: "list[str] | None" = None, tags_match: str = "all",
    ) -> list[dict]:
        """Substring search over memory name + content (case-insensitive),
        optionally narrowed to `tags`. Returns rows newest-first. Intentionally
        lo-fi — the hybrid / BM25-fused recall path lives in `rmx memory recall`
        (ann_search op). This is the cheap symbolic fallback that works without
        the [dense] extra installed."""
        self._connect()
        like = f"%{query}%"
        tag_sql, tag_params = self._tag_filter_sql(tags, tags_match)
        sql = (
            "SELECT e.id, e.name, mc.content, mc.mtype, mc.tags, mc.metadata, "
            "       mc.created_at, mc.updated_at "
            "FROM entities e "
            "LEFT JOIN memory_content mc ON mc.entity_id = e.id "
            "WHERE e.partition_id=? AND e.kind='memory' "
            "  AND (lower(e.name) LIKE lower(?) OR lower(mc.content) LIKE lower(?)) "
            + tag_sql +
            " ORDER BY mc.updated_at DESC NULLS LAST "
            "LIMIT ?"
        )
        rows = []
        for r in self._read().execute(
            sql, (self._partition_id, like, like, *tag_params, int(limit)),
        ).fetchall():
            rows.append({
                "id": r["id"], "name": r["name"],
                "content": r["content"], "mtype": r["mtype"],
                "tags": json.loads(r["tags"]) if r["tags"] else [],
                "metadata":
                    json.loads(r["metadata"]) if r["metadata"] else {},
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
            })
        return rows

    # ---- subjects (durable face of an STM partition; ADR-0002) ----
    def upsert_subject(self, label: str) -> dict:
        """Upsert a durable subject node (`mtype='subject'`) in the active
        partition. The STM-partition slug is the entity name (`subject_<slug>`);
        the human label lives in content + metadata. Protected so prune/vacuum
        never reaps a pursuit. Idempotent on the slug."""
        from refmatrix.stm import subject_slug
        slug = subject_slug(label)
        name = f"subject_{slug}"
        eid = self.add_memory(
            name=name, content=label, mtype="subject",
            metadata={"label": label, "slug": slug}, protected=True,
        )
        return {"id": eid, "name": name, "slug": slug, "label": label}

    def link_part_of(self, leaf_id: int, subject_id: int) -> bool:
        """File a leaf memory under a subject via a `part-of` edge
        (entity=leaf → concept=subject). Ensures the linkage type exists."""
        self.add_linkage_type(
            "part-of", directed=True, description="entity is part of a container")
        return self.link("part-of", concept_id=subject_id, entity_id=leaf_id)

    def list_subjects(self) -> list[dict]:
        """Subject nodes in the active partition with leaf counts, most-recently
        -updated first."""
        self._connect()
        try:
            lid = self.get_linkage_id("part-of")
        except KeyError:
            lid = None
        rows = self._read().execute(
            "SELECT e.id, e.name, mc.metadata, mc.updated_at "
            "FROM entities e JOIN memory_content mc ON mc.entity_id=e.id "
            "WHERE e.partition_id=? AND e.kind='memory' AND mc.mtype='subject' "
            "ORDER BY mc.updated_at DESC",
            (self._partition_id,),
        ).fetchall()
        out = []
        for r in rows:
            leaves = 0
            if lid is not None:
                leaves = self._read().execute(
                    "SELECT count(*) FROM entity_links "
                    "WHERE linkage_id=? AND concept_id=?",
                    (lid, r["id"]),
                ).fetchone()[0]
            meta = json.loads(r["metadata"]) if r["metadata"] else {}
            out.append({
                "id": r["id"], "name": r["name"],
                "label": meta.get("label") or r["name"],
                "leaves": leaves, "updated_at": r["updated_at"],
            })
        return out

    def subject_leaves(self, name_or_id: "str | int") -> list[dict]:
        """Memories filed under a subject (walk part-of: concept=subject →
        entity=leaf), newest first. Empty if the subject or linkage is
        unknown. Accepts a memory id, `subject_<slug>` name, or a bare label."""
        subj = self.get_memory(name_or_id)
        if subj is None and not str(name_or_id).isdigit():
            from refmatrix.stm import subject_slug
            subj = self.get_memory(f"subject_{subject_slug(str(name_or_id))}")
        if subj is None:
            return []
        try:
            lid = self.get_linkage_id("part-of")
        except KeyError:
            return []
        rows = self._read().execute(
            "SELECT el.entity_id FROM entity_links el "
            "JOIN memory_content mc ON mc.entity_id=el.entity_id "
            "WHERE el.linkage_id=? AND el.concept_id=? "
            "ORDER BY mc.updated_at DESC",
            (lid, subj["id"]),
        ).fetchall()
        out = []
        for r in rows:
            m = self.get_memory(int(r["entity_id"]))
            if m:
                out.append(m)
        return out

    def recent_memories(
        self, since_seconds: float | None = None, limit: int = 20,
        *, tags: "list[str] | None" = None, tags_match: str = "all",
    ) -> list[dict]:
        """Phase C2: return memories in the active partition ordered by
        `entities.created_at` DESC. When `since_seconds` is set, only
        include rows newer than `now - since_seconds`. Optionally narrowed to
        `tags`. Powers `rmx memory recall --recent --since <duration>` and the
        SessionStart / PreCompact hook templates."""
        import time as _time
        self._connect()
        sql = (
            "SELECT e.id, e.name, e.created_at AS entity_created_at, "
            "       mc.content, mc.mtype, mc.tags, mc.metadata, "
            "       mc.created_at, mc.updated_at "
            "FROM entities e "
            "LEFT JOIN memory_content mc ON mc.entity_id = e.id "
            "WHERE e.partition_id=? AND e.kind='memory'"
        )
        params: list[Any] = [self._partition_id]
        if since_seconds is not None and since_seconds > 0:
            sql += " AND e.created_at >= ?"
            params.append(_time.time() - since_seconds)
        tag_sql, tag_params = self._tag_filter_sql(tags, tags_match)
        sql += tag_sql
        params.extend(tag_params)
        sql += " ORDER BY e.created_at DESC LIMIT ?"
        params.append(int(limit))
        rows = []
        for r in self._read().execute(sql, params).fetchall():
            rows.append({
                "id": r["id"], "name": r["name"],
                "content": r["content"], "mtype": r["mtype"],
                "tags": json.loads(r["tags"]) if r["tags"] else [],
                "metadata":
                    json.loads(r["metadata"]) if r["metadata"] else {},
                "created_at": r["created_at"] or r["entity_created_at"],
                "updated_at": r["updated_at"],
            })
        return rows

    def forget_memory(self, name_or_id: str | int) -> bool:
        """Drop a memory entity + its sidecar + all entity_links it owns.
        Returns True if a row was removed, False if nothing matched.
        Defers all the bitmap/forward-index housekeeping to purge_entity;
        purge_entity also drops the memory_content row via the explicit
        DELETE we added in that path."""
        m = self.get_memory(name_or_id)
        if m is None:
            return False
        self.purge_entity(m["id"])
        return True

    def memory_facets(self) -> dict:
        """Distinct mtypes + tags (with counts) for memories in the active
        partition — populates the UI filter dropdowns. Tags are stored as a
        JSON list per row, so they're unpacked + counted in Python."""
        self._connect()
        rows = self._read().execute(
            "SELECT mc.mtype, mc.tags FROM entities e "
            "JOIN memory_content mc ON mc.entity_id = e.id "
            "WHERE e.partition_id=? AND e.kind='memory'",
            (self._partition_id,),
        ).fetchall()
        from collections import Counter
        mtypes: Counter = Counter()
        tags: Counter = Counter()
        for r in rows:
            mtypes[r["mtype"] or "?"] += 1
            if r["tags"]:
                try:
                    for t in json.loads(r["tags"]):
                        tags[t] += 1
                except (json.JSONDecodeError, TypeError):
                    pass
        return {
            "mtypes": dict(mtypes.most_common()),
            "tags": dict(tags.most_common()),
            "total": len(rows),
        }

    def reclassify_memories(
        self, *, to_mtype: str, like: "str | None" = None,
        names: "list[str] | None" = None, from_mtype: "str | None" = None,
        dry_run: bool = False,
    ) -> dict:
        """Bulk-change the `mtype` of memories in the active partition.

        Selection (intersected): `like` (SQL glob on name, `*`→`%`), explicit
        `names`, and/or `from_mtype`. Re-logs each change so log-replay keeps
        the new mtype. Returns {matched, changed, names:[...], dry_run}."""
        con = self._connect()
        where = ["e.partition_id = ?", "e.kind = 'memory'"]
        params: list[Any] = [self._partition_id]
        if like:
            where.append("e.name LIKE ?")
            params.append(like.replace("*", "%"))
        if names:
            where.append("e.name IN (" + ",".join("?" * len(names)) + ")")
            params.extend(names)
        if from_mtype:
            where.append("mc.mtype = ?")
            params.append(from_mtype)
        rows = self._read().execute(
            "SELECT e.id, e.name FROM entities e "
            "JOIN memory_content mc ON mc.entity_id = e.id "
            "WHERE " + " AND ".join(where),
            params,
        ).fetchall()
        matched = [(r["id"], r["name"]) for r in rows]
        if dry_run or not matched:
            return {"matched": len(matched), "changed": 0,
                    "names": [n for _, n in matched], "dry_run": dry_run}
        now = time.time()
        for eid, _name in matched:
            con.execute(
                "UPDATE memory_content SET mtype=?, updated_at=? WHERE entity_id=?",
                (to_mtype, now, eid),
            )
        con.commit()
        # re-log each so rebuild-from-log preserves the reclassification
        for eid, name in matched:
            m = self.get_memory(int(eid))
            if m:
                self._log_event(
                    "memory_content", kind="memory", name=name,
                    content=m["content"] or "", mtype=to_mtype,
                    tags=m["tags"] or None, metadata=m["metadata"] or None,
                )
        return {"matched": len(matched), "changed": len(matched),
                "names": [n for _, n in matched], "dry_run": False}

    def retag_memory(
        self, name_or_id: "str | int", *,
        add: "list[str] | None" = None,
        remove: "list[str] | None" = None,
        replace: "list[str] | None" = None,
    ) -> "list[str] | None":
        """Mutate a memory's tags. `replace` sets the whole list; otherwise
        `remove` then `add` are applied to the current tags (order-preserving,
        deduped). Leaves content/mtype/protected/created_at untouched. Returns
        the new tag list, or None if the memory doesn't exist."""
        m = self.get_memory(name_or_id)
        if m is None:
            return None
        if replace is not None:
            new = list(dict.fromkeys(replace))
        else:
            rm = set(remove or [])
            new = [t for t in (m["tags"] or []) if t not in rm]
            for t in (add or []):
                if t not in new:
                    new.append(t)
        now = time.time()
        con = self._connect()
        con.execute(
            "UPDATE memory_content SET tags=?, updated_at=? WHERE entity_id=?",
            (json.dumps(new) if new else None, now, m["id"]),
        )
        con.commit()
        # Re-log the full sidecar so log-replay / rebuild keeps the new tags.
        self._log_event(
            "memory_content", kind="memory", name=m["name"],
            content=m["content"] or "", mtype=m["mtype"] or "observation",
            tags=new, metadata=m["metadata"] or None,
        )
        return new

    def bulk_forget_memories(
        self,
        *,
        ids: "list[int] | None" = None,
        names: "list[str] | None" = None,
        mtypes: "list[str] | None" = None,
        dry_run: bool = False,
    ) -> dict:
        """Bulk-delete memory rows + sidecars + linkages.

        Selection is the UNION of any of:
          - `ids`: explicit entity-id list
          - `names`: explicit name list (resolved within the active partition)
          - `mtypes`: every memory whose sidecar mtype is in this list

        Resolution scope: name + mtype resolution is partition-scoped to
        prevent a stray purge from crossing into another project's
        memory rows. `ids` are global by entity-id (callers that want
        partition safety should pre-filter with `iter_memories`).

        `dry_run=True` returns the resolved id set + per-mtype counts
        without touching the catalog — exactly the same shape as the
        real run minus the row deletion.

        Returns `{forgotten: N, ids: [...], by_mtype: {mtype: count, ...},
        dry_run: bool}`.
        """
        con = self._connect()
        resolved_ids: set[int] = set()
        per_mtype: dict[str, int] = {}

        if ids:
            for eid in ids:
                resolved_ids.add(int(eid))
        if names:
            placeholders = ",".join("?" * len(names))
            for row in con.execute(
                f"SELECT id FROM entities "
                f"WHERE partition_id=? AND kind='memory' "
                f"  AND name IN ({placeholders})",
                [self._partition_id, *names],
            ).fetchall():
                resolved_ids.add(int(row["id"]))
        if mtypes:
            placeholders = ",".join("?" * len(mtypes))
            for row in con.execute(
                f"SELECT e.id FROM entities e "
                f"JOIN memory_content mc ON mc.entity_id = e.id "
                f"WHERE e.partition_id=? AND e.kind='memory' "
                f"  AND mc.mtype IN ({placeholders})",
                [self._partition_id, *mtypes],
            ).fetchall():
                resolved_ids.add(int(row["id"]))

        if not resolved_ids:
            return {
                "forgotten": 0, "ids": [], "by_mtype": {},
                "dry_run": dry_run,
            }

        id_list = sorted(resolved_ids)
        id_placeholders = ",".join("?" * len(id_list))
        for row in con.execute(
            f"SELECT mc.mtype, COUNT(*) AS n "
            f"FROM entities e "
            f"LEFT JOIN memory_content mc ON mc.entity_id = e.id "
            f"WHERE e.id IN ({id_placeholders}) "
            f"GROUP BY mc.mtype",
            id_list,
        ).fetchall():
            per_mtype[row["mtype"] or "(none)"] = int(row["n"])

        if dry_run:
            return {
                "forgotten": 0, "ids": id_list, "by_mtype": per_mtype,
                "dry_run": True,
            }

        # Batch the Lance side BEFORE the per-id catalog purges so a
        # 261-id forget pays one Lance open per kind (typically 1 — every
        # memory row is kind='memory') instead of 261. `purge_entity` is
        # then told to skip its per-id Lance drop via `_skip_lance=True`.
        ids_by_kind: dict[str, list[int]] = {}
        for row in con.execute(
            f"SELECT id, kind FROM entities "
            f"WHERE id IN ({id_placeholders})",
            id_list,
        ).fetchall():
            ids_by_kind.setdefault(row["kind"], []).append(int(row["id"]))
        self._drop_lance_for_purge_batch(ids_by_kind)

        for eid in id_list:
            self.purge_entity(eid, _skip_lance=True)
        return {
            "forgotten": len(id_list), "ids": id_list,
            "by_mtype": per_mtype, "dry_run": False,
        }

    def reinforcement_score(
        self, concept_id: int, *, now: float | None = None,
        halflife_days: float | None = None, cap: float | None = None,
    ) -> float:
        """Phase B5: signed per-concept reinforcement signal (decayed
        Σ reinforces.weight − Σ contradicts.weight). See
        `refmatrix.reinforcement` for the math and env-vars."""
        from refmatrix.reinforcement import reinforcement_score
        self._connect()
        return reinforcement_score(
            self, concept_id, now=now,
            halflife_days=halflife_days, cap=cap,
        )

    def reinforcement_scores(
        self, concept_ids: list[int], *, now: float | None = None,
        halflife_days: float | None = None, cap: float | None = None,
    ) -> dict[int, float]:
        """Batched form of reinforcement_score."""
        from refmatrix.reinforcement import reinforcement_scores
        self._connect()
        return reinforcement_scores(
            self, concept_ids, now=now,
            halflife_days=halflife_days, cap=cap,
        )

    def reinforcement_components(
        self, concept_id: int, *, now: float | None = None,
        halflife_days: float | None = None,
    ) -> list[dict]:
        """Per-row contribution breakdown for inspection / --explain."""
        from refmatrix.reinforcement import reinforcement_components
        self._connect()
        return reinforcement_components(
            self, concept_id, now=now, halflife_days=halflife_days,
        )

    def get_entity(self, kind: str, name: str) -> Entity | None:
        # Ensure schema/partition migration before going through the read path.
        self._connect()
        row = self._read().execute(
            "SELECT id, kind, name, path, tldr, meta, protected, noise "
            "FROM entities WHERE partition_id=? AND kind=? AND name=?",
            (self._partition_id, kind, name),
        ).fetchone()
        return self._row_to_entity(row) if row else None

    def get_entity_by_id(self, eid: int) -> Entity | None:
        # By-id lookup is intentionally cross-partition: entity ids are
        # globally unique, and call sites (logs, evidence, _name_of) need to
        # resolve any id they observe regardless of the active partition.
        self._connect()
        row = self._read().execute(
            "SELECT id, kind, name, path, tldr, meta, protected, noise "
            "FROM entities WHERE id=?", (eid,)
        ).fetchone()
        return self._row_to_entity(row) if row else None

    def resolve_entity(self, ref: str) -> Entity | None:
        """Resolve a string ref to an entity. Tries 'kind:name', then 'name'
        across kinds. The kind sweep includes 'memory' so `rmx context
        <memory-name>` lands the memory entity (and its body) instead of
        falling through to no-match."""
        if ":" in ref:
            kind, name = ref.split(":", 1)
            return self.get_entity(kind, name)
        for kind in ("concept", "code", "doc", "memory"):
            e = self.get_entity(kind, ref)
            if e:
                return e
        return None

    def resolve_concept_ids(self, name: str, strict: bool = False) -> list[int]:
        """Resolve a name to all matching concept entity ids.

        Default (`strict=False`): lookup by canonical_name — every concept
        whose canonicalized form equals canonicalize_name(`name`). Covers
        camelCase / PascalCase-with-leading-acronym / dash / space /
        digit-boundary variants in a single indexed SELECT against
        idx_entities_canonical. Used by the query/context/neighbors path so
        an LLM passing any surface form lands on the same set of mentions.

        Strict (`strict=True`): exact-name lookup only. Returned list has at
        most one id.

        Ids returned in a stable order (exact-name match first if present,
        then remaining canonical matches by entity id). Empty list if
        nothing matches."""
        from refmatrix.identifier import canonicalize_name

        if strict:
            e = self.get_entity("concept", name)
            return [e.id] if e else []

        self._connect()
        canon = canonicalize_name(name)
        rows = self._read().execute(
            "SELECT id, name FROM entities "
            "WHERE partition_id=? AND kind='concept' AND canonical_name=?",
            (self._partition_id, canon),
        ).fetchall()
        if not rows:
            return []
        # Surface exact-name match first so callers that downstream-truncate
        # still see the user's literal intent. Remaining ids in id order for
        # determinism.
        exact = [r[0] for r in rows if r[1] == name]
        others = sorted(r[0] for r in rows if r[1] != name)
        return exact + others

    def same_as_audit(self, limit: int = 20) -> dict:
        """Read-only health report on `same_as` — the identifier variant-
        unification edges (`_concept_variants`: space/dash forms linked to the
        underscore canonical).

        The variant-expansion query path (`resolve_concept_ids`) unifies via
        the `canonical_name` column, NOT these edges, so they carry no query
        weight; their only risk is the audit's #6 concern — a silent over-merge
        fusing DISTINCT symbols. A legitimate `same_as` edge connects surface
        variants of ONE identifier, so both endpoints share a `canonical_name`.
        An edge whose endpoints have DIFFERENT canonical_names is the tripwire:
        it means `canonicalize_name` collapsed two distinct identifiers. Empty
        `divergent` = healthy. Reports edge count + variants-per-canonical
        distribution so growth stays observable (it should be ~2/concept)."""
        self._connect()
        r = self._read()
        edges = r.execute(
            "SELECT count(*) FROM entity_links el JOIN linkage_types lt "
            "ON lt.id=el.linkage_id WHERE lt.name='same_as'"
        ).fetchone()[0]
        dist = r.execute(
            "SELECT cnt, count(*) FROM ("
            "  SELECT el.entity_id, count(*) cnt FROM entity_links el "
            "  JOIN linkage_types lt ON lt.id=el.linkage_id AND lt.name='same_as' "
            "  GROUP BY el.entity_id) GROUP BY cnt ORDER BY cnt"
        ).fetchall()
        _div_where = (
            "JOIN linkage_types lt ON lt.id=el.linkage_id AND lt.name='same_as' "
            "JOIN entities v ON v.id=el.concept_id "
            "JOIN entities c ON c.id=el.entity_id "
            "WHERE v.canonical_name IS NOT NULL AND c.canonical_name IS NOT NULL "
            "  AND v.canonical_name <> c.canonical_name"
        )
        divergent_count = r.execute(
            f"SELECT count(*) FROM entity_links el {_div_where}"
        ).fetchone()[0]
        sample = r.execute(
            "SELECT v.name, v.canonical_name, c.name, c.canonical_name "
            f"FROM entity_links el {_div_where} LIMIT ?",
            (limit,),
        ).fetchall()
        return {
            "edges": edges,
            "distribution": {int(k): int(v) for k, v in dist},
            "divergent_count": divergent_count,
            "divergent": [
                {"variant": s[0], "variant_canon": s[1],
                 "canonical": s[2], "canonical_canon": s[3]}
                for s in sample
            ],
        }

    # ---- dense vector wrappers (Lance-backed) -----------------------------
    #
    # The [dense] optional extra (pylance + numpy) is required for any of
    # these to do real work. They lazy-import refmatrix.vectors so SQLite-
    # only installs never pay the import cost. Calling without the extra
    # raises ImportError with a clear message; the daemon catches that and
    # surfaces it as a graceful "dense not installed" response.

    def _vector_store(self, dim: int, partition: str | None = None):
        """Return a LanceVectorStore for <root>/vectors/<partition>/. `dim`
        must match the embedder's output dimension; mismatch raises.

        With `partition=None` (default) the Store's bound partition is
        used and the handle is cached. With `partition` set and != bound,
        a one-shot non-cached handle is returned — the daemon binds to
        ONE partition for its writes, but Lance datasets are filesystem-
        addressable so reads can reach any partition without re-binding.
        The cache invariant only covers the bound-partition handle.
        """
        from refmatrix.vectors import LanceVectorStore

        if partition is not None and partition != self._partition_name:
            return LanceVectorStore(
                self.root / "vectors", partition=partition, dim=dim,
            )
        existing = getattr(self, "_vs", None)
        if existing is not None:
            if existing.dim != dim or existing.partition != self._partition_name:
                raise ValueError(
                    "LanceVectorStore re-init with different dim/partition "
                    f"({existing.dim}/{existing.partition} -> {dim}/"
                    f"{self._partition_name}); reopen Store first"
                )
            return existing
        vroot = self.root / "vectors"
        vs = LanceVectorStore(vroot, partition=self._partition_name, dim=dim)
        self._vs = vs
        return vs

    def upsert_vector(
        self,
        entity_ids,
        vectors,
        *,
        kind: str,
        dim: int,
        mark_embedded: bool = True,
    ) -> None:
        """Persist `vectors` (N x dim) for `entity_ids` into the Lance
        dataset for this Store's partition + the given `kind`. When
        `mark_embedded=True` (default) also stamps `entities.vectors_updated_at`
        for those ids so `rmx embed --incremental` knows they're current.
        """
        vs = self._vector_store(dim)
        vs.upsert_vectors(list(entity_ids), vectors, kind=kind)
        if mark_embedded and len(entity_ids) > 0:
            import time as _t
            now = _t.time()
            con = self._connect()
            placeholders = ",".join("?" * len(entity_ids))
            con.execute(
                f"UPDATE entities SET vectors_updated_at = ? "
                f"WHERE id IN ({placeholders})",
                [now, *list(entity_ids)],
            )
            con.commit()

    def ann_search(
        self,
        query_vec,
        k: int,
        *,
        dim: int,
        kinds=None,
        candidate_ids=None,
        partition: str | None = None,
    ) -> list[tuple[int, float]]:
        """Dense ANN search via Lance. Returns `[(entity_id, distance), ...]`
        sorted by L2 distance ascending. `kinds=None` searches every
        kind that has a Lance dataset under the target partition.
        `candidate_ids` (optional) narrows the ANN scan to those ids —
        the hybrid retrieval pre-filter.

        `partition` overrides the Store's bound partition for this call so
        a daemon bound to `local` can still serve memory recall against
        `intuition` (paired-subsystem isolation lives at the partition
        level, not at the daemon level)."""
        vs = self._vector_store(dim, partition=partition)
        return vs.ann_search(
            query_vec, k=k, kinds=kinds, candidate_ids=candidate_ids,
        )

    def gc_vectors(
        self, *, kinds: list[str] | None = None, dim: int,
        dry_run: bool = False,
    ) -> dict[str, dict]:
        """Remove vectors whose entity_id no longer exists in the catalog
        for this Store's partition+kind.

        Forget / purge ops drop catalog rows but leave vectors behind in
        the per-kind lance dataset. Those orphans then surface in
        `ann_search` top-k with score but no resolvable name — and the
        JSON output of `memory recall` silently drops them, masquerading
        as a "no recall hits" result.

        Returns a `{kind: {"orphans": N, "kept": N, "dry_run": bool}}` map.
        """
        vs = self._vector_store(dim)
        if kinds is None:
            kinds = vs.kinds_on_disk()
        out: dict[str, dict] = {}
        con = self._connect()
        for kind in kinds:
            lance_ids = vs.list_ids(kind=kind)
            if not lance_ids:
                out[kind] = {"orphans": 0, "kept": 0, "dry_run": dry_run}
                continue
            # Catalog ids for this partition+kind.
            rows = con.execute(
                "SELECT id FROM entities "
                "WHERE partition_id=? AND kind=?",
                (self._partition_id, kind),
            ).fetchall()
            catalog_ids = {int(r[0]) for r in rows}
            orphans = [i for i in lance_ids if i not in catalog_ids]
            if orphans and not dry_run:
                vs.drop_for(orphans, kind=kind)
            out[kind] = {
                "orphans": len(orphans),
                "kept": len(lance_ids) - len(orphans),
                "dry_run": dry_run,
            }
        return out

    def drop_vectors(self, entity_ids, *, kind: str, dim: int) -> int:
        """Remove vectors for `entity_ids` from the kind's Lance dataset.
        Used when purge_path / purge_entity drop the relational row."""
        vs = self._vector_store(dim)
        n = vs.drop_for(entity_ids, kind=kind)
        # Clear the embedded timestamp so future `rmx embed` re-emits if
        # the entity row still exists.
        if n > 0:
            con = self._connect()
            placeholders = ",".join("?" * len(list(entity_ids)))
            con.execute(
                f"UPDATE entities SET vectors_updated_at = NULL "
                f"WHERE id IN ({placeholders})",
                list(entity_ids),
            )
            con.commit()
        return n

    def _drop_lance_for_purge(self, entity_id: int, kind: str) -> bool:
        """Best-effort: drop entity_id's vector from its (partition, kind)
        Lance dataset. Paired with `purge_entity` so a DuckDB row deletion
        also clears the corresponding dense vector instead of leaving an
        orphan for the next `embed --gc`.

        Skips silently on:
          - `lance` not importable (no [dense] extra installed)
          - dataset directory absent (kind never embedded in this partition)
          - any Lance-side exception (the catalog purge must still proceed
            even if the vector side fails — worst case stays "orphan, GC
            reaps later," never "user thinks the row is gone but it isn't")

        Returns True when a delete was issued, False otherwise.
        """
        try:
            import lance
        except ImportError:
            return False
        path = self.root / "vectors" / self._partition_name / f"{kind}.lance"
        if not path.exists():
            return False
        try:
            ds = lance.dataset(str(path))
            ds.delete(f"id = {int(entity_id)}")
            return True
        except Exception:
            return False

    def _drop_lance_for_purge_batch(
        self, ids_by_kind: "dict[str, list[int]]",
    ) -> int:
        """Batched form of `_drop_lance_for_purge`: one Lance dataset open
        per kind, one delete per kind. Used by `bulk_forget_memories` so
        a 261-id purge pays N dataset opens (one per distinct kind) rather
        than 261. Same failure semantics as the single-id variant.
        Returns the number of ids whose Lance row was attempted (count is
        per-kind input length when the dataset exists and lance is
        importable; sum across kinds)."""
        try:
            import lance
        except ImportError:
            return 0
        total = 0
        for kind, ids in ids_by_kind.items():
            if not ids:
                continue
            path = (
                self.root / "vectors" / self._partition_name
                / f"{kind}.lance"
            )
            if not path.exists():
                continue
            try:
                ds = lance.dataset(str(path))
                in_list = ",".join(str(int(i)) for i in ids)
                ds.delete(f"id IN ({in_list})")
                total += len(ids)
            except Exception:
                pass
        return total

    def pending_embeddings(
        self, *, kinds: list[str] | None = None, limit: int | None = None
    ) -> list[tuple[int, str, str]]:
        """Return `(id, kind, name)` for entities whose vector is missing or
        stale: `vectors_updated_at` is NULL or older than `updated_at`.
        Filtered to `kinds` when provided. `limit` caps the result.
        """
        con = self._connect()
        sql = (
            "SELECT id, kind, name FROM entities "
            "WHERE partition_id = ? "
            "AND (vectors_updated_at IS NULL "
            "     OR vectors_updated_at < updated_at)"
        )
        params: list = [self._partition_id]
        if kinds:
            in_list = ",".join("?" * len(kinds))
            sql += f" AND kind IN ({in_list})"
            params.extend(kinds)
        sql += " ORDER BY id"
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        rows = con.execute(sql, params).fetchall()
        return [(r[0], r[1], r[2]) for r in rows]

    def repair_entity_links_index(self) -> dict:
        """Drop + recreate `idx_entity_links_lk_concept` to defend against
        DuckDB secondary-index drift after bulk DELETEs (prune_noise --drop,
        purge_entity on high-degree concepts, SIGKILL+WAL replay).

        Returns `{"recreated": True, "row_count": N}` on success. Cheap (~1s
        on a 100k-entity_links table). Idempotent — safe to run repeatedly.

        Background: DuckDB's b-tree secondary indexes can disagree with the
        underlying table after a multi-row DELETE. Symptom is a fatal error
        on the next op that touches the index: 'Failed to delete all rows
        from index. Only deleted X out of N rows'. Once that fires, the
        database is invalidated until restart. This method is the
        documented self-heal and is wired into `Daemon` startup so every
        daemon spawn has a clean index."""
        con = self._connect()
        n = con.execute("SELECT COUNT(*) FROM entity_links").fetchone()[0]
        con.execute("DROP INDEX IF EXISTS idx_entity_links_lk_concept")
        con.execute(
            "CREATE INDEX idx_entity_links_lk_concept "
            "ON entity_links(linkage_id, concept_id)"
        )
        con.commit()
        return {"recreated": True, "row_count": n}

    def _backfill_canonical_name_if_needed(self) -> None:
        """Populate canonical_name for any concept rows where it's NULL.

        Runs once after schema upgrade (the ALTER TABLE adds the column as
        NULL). Idempotent: subsequent calls see no NULL rows and skip.
        Pulls all matching rows into Python to compute canonicalize_name —
        cheap because there's at most ~100k concept entities in a typical
        repo and the computation is regex-only."""
        from refmatrix.identifier import canonicalize_name

        con = self._connect()
        rows = con.execute(
            "SELECT id, name FROM entities "
            "WHERE kind='concept' AND canonical_name IS NULL"
        ).fetchall()
        if not rows:
            return
        payload = [(canonicalize_name(name), eid) for (eid, name) in rows]
        con.executemany(
            "UPDATE entities SET canonical_name=? WHERE id=?",
            payload,
        )
        con.commit()

    def iter_entities(self, kind: str | None = None) -> Iterator[Entity]:
        self._connect()
        sql = (
            "SELECT id, kind, name, path, tldr, meta, protected, noise "
            "FROM entities WHERE partition_id=?"
        )
        params: tuple = (self._partition_id,)
        if kind:
            sql += " AND kind=?"
            params = (self._partition_id, kind)
        for row in self._read().execute(sql, params):
            yield self._row_to_entity(row)

    def _name_of(self, eid: int) -> tuple[str, str] | None:
        """Look up (kind, name) for an entity id. Used by the logger to write
        name-keyed events instead of branch-local IDs."""
        self._connect()
        row = self._read().execute(
            "SELECT kind, name FROM entities WHERE id=?", (eid,)
        ).fetchone()
        return (row["kind"], row["name"]) if row else None

    @staticmethod
    def _row_to_entity(row: sqlite3.Row) -> Entity:
        keys = row.keys()
        return Entity(
            id=row["id"],
            kind=row["kind"],
            name=row["name"],
            path=row["path"],
            tldr=row["tldr"],
            meta=json.loads(row["meta"]) if row["meta"] else {},
            protected=bool(row["protected"]) if "protected" in keys else False,
            noise=bool(row["noise"]) if "noise" in keys else False,
        )

    # ---- linkage types -----------------------------------------------------

    def add_linkage_type(
        self, name: str, directed: bool = True, description: str | None = None
    ) -> int:
        name = _canonical_verb(name)
        con = self._connect()
        cur = con.execute(
            "INSERT OR IGNORE INTO linkage_types(name, directed, description) VALUES (?,?,?)",
            (name, 1 if directed else 0, description),
        )
        self._maybe_commit(con)
        # Log the registration so `rmx rebuild --from-log` can replay
        # custom linkage types before any link events that reference
        # them. Without this, a fresh-DB replay fails the moment it
        # hits a link for a non-default verb (e.g. GMD's part-of).
        self._log_event("linkage_type", name=name, directed=1 if directed else 0,
                        description=description or "")
        if cur.lastrowid:
            return cur.lastrowid
        row = con.execute("SELECT id FROM linkage_types WHERE name=?", (name,)).fetchone()
        return row[0]

    def get_linkage_id(self, name: str) -> int:
        name = _canonical_verb(name)
        self._connect()
        row = self._read().execute(
            "SELECT id FROM linkage_types WHERE name=?", (name,)
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown linkage type: {name}. Use add-linkage-type first.")
        return row[0]

    def list_linkages(self) -> list[dict]:
        self._connect()
        rows = self._read().execute(
            "SELECT id, name, directed, description FROM linkage_types ORDER BY name"
        ).fetchall()
        return [dict(r) for r in rows]

    def merge_verb_alias(self, legacy: str, canon: str) -> dict:
        """Fold a legacy linkage verb into its canonical twin across BOTH the
        relational forward index (entity_links, linkage_evidence) and the
        per-partition bitmap fragments, then drop the orphan linkage_type.

        Idempotent: returns `{merged: False}` once `legacy` is gone. The
        relational re-point carries a NOT EXISTS guard so the
        UNIQUE(entity_id, linkage_id, concept_id) never collides — a legacy
        edge duplicating an existing canonical edge is simply dropped. Bitmap
        bits are partition-blind (`_pack` of global ids), so the legacy
        fragment ORs into canon verbatim. Must run on a directly-opened writer
        Store (daemon down), not a DaemonWriter proxy."""
        con = self._connect()
        legacy_row = con.execute(
            "SELECT id, directed FROM linkage_types WHERE name=?", (legacy,)
        ).fetchone()
        if not legacy_row:
            return {"legacy": legacy, "canon": canon, "merged": False,
                    "edges": 0, "evidence": 0, "fragments": 0}
        legacy_id, legacy_dir = legacy_row[0], legacy_row[1]
        # Ensure the canonical linkage_type exists (inherit directedness).
        canon_row = con.execute(
            "SELECT id FROM linkage_types WHERE name=?", (canon,)
        ).fetchone()
        if canon_row:
            canon_id = canon_row[0]
        else:
            canon_id = self.add_linkage_type(canon, directed=bool(legacy_dir))
            con = self._connect()
        # --- relational: entity_links (re-point, dedup on the UNIQUE) ---
        edges = con.execute(
            "SELECT count(*) FROM entity_links WHERE linkage_id=?", (legacy_id,)
        ).fetchone()[0]
        con.execute(
            "INSERT INTO entity_links(entity_id, linkage_id, concept_id, weight) "
            "SELECT e.entity_id, ?, e.concept_id, e.weight FROM entity_links e "
            "WHERE e.linkage_id=? AND NOT EXISTS ("
            "  SELECT 1 FROM entity_links c WHERE c.entity_id=e.entity_id "
            "    AND c.linkage_id=? AND c.concept_id=e.concept_id)",
            (canon_id, legacy_id, canon_id),
        )
        con.execute(
            "DELETE FROM entity_links WHERE linkage_id=?", (legacy_id,)
        )
        # --- relational: linkage_evidence (no UNIQUE; plain re-point) ---
        evid = con.execute(
            "SELECT count(*) FROM linkage_evidence WHERE linkage_id=?",
            (legacy_id,),
        ).fetchone()[0]
        con.execute(
            "UPDATE linkage_evidence SET linkage_id=? WHERE linkage_id=?",
            (canon_id, legacy_id),
        )
        # --- bitmaps: OR each partition's legacy fragment into canon ---
        frags = self._merge_fragment_all_partitions(legacy, canon)
        # --- drop the orphan linkage_type ---
        con.execute("DELETE FROM linkage_types WHERE id=?", (legacy_id,))
        self._maybe_commit(con)
        con.commit()
        return {"legacy": legacy, "canon": canon, "merged": True,
                "edges": edges, "evidence": evid, "fragments": frags}

    def _read_legacy_fragment_raw(self, linkage_raw: str) -> "BitMap64 | None":
        """Load a bitmap fragment by its RAW (non-canonicalized) key in the
        active partition. Needed only by the alias merge: `_load_fragment`
        canonicalizes its key, so it can no longer reach a legacy fragment."""
        if self._backend.kind == "duckdb":
            con = self._connect()
            row = con._duck.execute(
                "SELECT blob FROM bitmap_fragments "
                "WHERE partition_id=? AND linkage=?",
                [self._partition_id, linkage_raw],
            ).fetchone()
            if not row or row[0] is None:
                return None
            return BitMap64.deserialize(bytes(row[0]))
        p = self._partition_fragments_dir() / f"{linkage_raw}.rb64"
        if not p.exists():
            return None
        return BitMap64.deserialize(p.read_bytes())

    def _drop_legacy_fragment_raw(self, linkage_raw: str) -> None:
        """Delete a legacy fragment by RAW key in the active partition + evict
        any cache entry under that key."""
        if self._backend.kind == "duckdb":
            self._connect()._duck.execute(
                "DELETE FROM bitmap_fragments WHERE partition_id=? AND linkage=?",
                [self._partition_id, linkage_raw],
            )
        else:
            p = self._partition_fragments_dir() / f"{linkage_raw}.rb64"
            if p.exists():
                p.unlink()
        self._fragments.pop(linkage_raw, None)

    def _merge_fragment_all_partitions(self, legacy: str, canon: str) -> int:
        """OR every partition's `legacy` bitmap fragment into its `canon`
        fragment, then delete the legacy fragment. Returns the count of
        partitions whose legacy fragment held bits."""
        con = self._connect()
        parts = [r[0] for r in con.execute(
            "SELECT name FROM partitions"
        ).fetchall()]
        n = 0
        for pname in parts:
            with self.with_partition(pname):
                legacy_bits = self._read_legacy_fragment_raw(legacy)
                if legacy_bits is None or len(legacy_bits) == 0:
                    self._drop_legacy_fragment_raw(legacy)
                    continue
                canon_frag = self._load_fragment(canon)
                canon_frag |= legacy_bits
                self._dirty_fragments.add(_canonical_verb(canon))
                self.flush_fragments()
                self._drop_legacy_fragment_raw(legacy)
                n += 1
        return n

    # ---- bitmaps (Pilosa-style fragments) ---------------------------------

    def _fragment_path(self, linkage: str) -> Path:
        return self._partition_fragments_dir() / f"{_canonical_verb(linkage)}.rb64"

    def _load_fragment(self, linkage: str) -> BitMap64:
        """Return the in-memory BitMap64 for a linkage, lazy-loading on first
        access. Mutating the returned object is fine — call flush_fragments()
        (or close()) to persist.

        Backend differences:
        - SQLite: fragment persists as `fragments/<partition>/<linkage>.rb64`
          on disk; lazy-loaded by file read.
        - DuckDB: fragment persists as a BLOB row in `bitmap_fragments`
          keyed by (partition_id, linkage); lazy-loaded by SELECT.
        """
        linkage = _canonical_verb(linkage)
        if linkage in self._fragments:
            return self._fragments[linkage]
        if self._backend.kind == "duckdb":
            self._connect()  # ensures partition_id is resolved
            row = self._read_raw_blob(linkage)
            frag = BitMap64.deserialize(row) if row else BitMap64()
        else:
            self._partition_fragments_dir().mkdir(parents=True, exist_ok=True)
            p = self._fragment_path(linkage)
            if p.exists():
                frag = BitMap64.deserialize(p.read_bytes())
            else:
                frag = BitMap64()
        self._fragments[linkage] = frag
        return frag

    def _read_raw_blob(self, linkage: str) -> bytes | None:
        """DuckDB-only: fetch the raw bitmap blob for (active partition,
        linkage), or None if no row exists. Split out so the deserialization
        and BitMap64() fallback live in _load_fragment."""
        con = self._connect()
        row = con._duck.execute(
            "SELECT blob FROM bitmap_fragments "
            "WHERE partition_id = ? AND linkage = ?",
            [self._partition_id, linkage],
        ).fetchone()
        return bytes(row[0]) if row and row[0] is not None else None

    def flush_fragments(self) -> None:
        """Write any dirty linkage fragments to their backing store. Idempotent.

        SQLite path writes to `fragments/<partition>/<linkage>.rb64` on disk
        (atomic via tmp + rename); DuckDB path UPSERTs the BLOB into the
        `bitmap_fragments` table. Empty fragments are removed in both modes.
        """
        if not self._dirty_fragments:
            return
        if self._backend.kind == "duckdb":
            self._flush_fragments_duckdb()
            return
        self._partition_fragments_dir().mkdir(parents=True, exist_ok=True)
        for raw in list(self._dirty_fragments):
            # Fold a raw-alias dirty entry to its canonical cache + path key.
            linkage = _canonical_verb(raw)
            frag = self._fragments.get(linkage)
            if frag is None:
                self._dirty_fragments.discard(raw)
                continue
            p = self._fragment_path(linkage)
            if len(frag) == 0:
                if p.exists():
                    p.unlink()
            else:
                tmp = p.with_suffix(".rb64.tmp")
                tmp.write_bytes(frag.serialize())
                tmp.replace(p)
            self._dirty_fragments.discard(raw)

    def _flush_fragments_duckdb(self) -> None:
        """DuckDB persistence path for flush_fragments: UPSERT (or DELETE on
        empty) the BLOB row for each dirty linkage in the active partition."""
        con = self._connect()
        pid = self._partition_id
        for raw in list(self._dirty_fragments):
            # A dirtied entry may be a raw alias (e.g. `related_to`); the cache
            # + blob key are canonical, so fold before lookup/persist.
            linkage = _canonical_verb(raw)
            frag = self._fragments.get(linkage)
            if frag is None:
                self._dirty_fragments.discard(raw)
                continue
            if len(frag) == 0:
                con._duck.execute(
                    "DELETE FROM bitmap_fragments "
                    "WHERE partition_id = ? AND linkage = ?",
                    [pid, linkage],
                )
            else:
                con._duck.execute(
                    "INSERT INTO bitmap_fragments(partition_id, linkage, blob) "
                    "VALUES (?, ?, ?) "
                    "ON CONFLICT(partition_id, linkage) DO UPDATE "
                    "SET blob = excluded.blob",
                    [pid, linkage, frag.serialize()],
                )
            self._dirty_fragments.discard(raw)

    @staticmethod
    def _pack(concept_id: int, entity_id: int) -> int:
        return (concept_id << _CONCEPT_SHIFT) | entity_id

    def load_bitmap(self, linkage: str, concept_id: int) -> BitMap:
        """Extract the BitMap32 of entity_ids set under (linkage, concept).

        Implementation: range-mask intersection on the linkage fragment,
        then strip the high 32 bits. Pilosa does the same trick: rows are
        slices of one fragment by row-id range, not separate files."""
        frag = self._load_fragment(linkage)
        if len(frag) == 0:
            return BitMap()
        start = concept_id << _CONCEPT_SHIFT
        end = (concept_id + 1) << _CONCEPT_SHIFT
        mask = BitMap64()
        mask.add_range(start, end)
        sub = frag & mask
        out = BitMap()
        for v in sub:
            out.add(v & _ENTITY_MASK)
        return out

    def save_bitmap(self, linkage: str, concept_id: int, bm: BitMap) -> None:
        """Replace the row for (linkage, concept) with bm. Used by callers
        that build a bitmap from scratch; link/unlink/link_many use the
        targeted in-place ops below to avoid the extra clear-then-add."""
        frag = self._load_fragment(linkage)
        start = concept_id << _CONCEPT_SHIFT
        end = (concept_id + 1) << _CONCEPT_SHIFT
        # Clear any existing bits in this row, then set the new ones.
        frag.remove_range(start, end)
        for eid in bm:
            frag.add(start | eid)
        self._dirty_fragments.add(linkage)

    def _maybe_commit(self, con) -> None:
        """Commit only if not inside an outer `transaction()` scope.

        Per-mutation commits inside a `BEGIN TRANSACTION` block silently
        end the transaction (DuckDB's commit() is a real COMMIT, not a
        no-op) and switch the connection back to autocommit -- so callers
        that wrap many writes in s.transaction() get one commit-per-call
        anyway unless individual writes opt out. This helper makes the
        opt-out automatic."""
        if not self._in_transaction:
            con.commit()

    def transaction(self):
        """Context manager that wraps the body in BEGIN/COMMIT. DuckDB
        otherwise autocommits each statement; bundling many writes into
        one transaction skips the per-statement WAL fsync and is the
        single biggest win on bulk sync paths.

        Re-entry safe: nested `with s.transaction():` blocks share the
        outermost transaction. Rolls back on exception."""
        from contextlib import contextmanager

        @contextmanager
        def _scope():
            if self._in_transaction:
                yield
                return
            con = self._connect()
            con.execute("BEGIN TRANSACTION")
            self._in_transaction = True
            try:
                yield
            except Exception:
                con.execute("ROLLBACK")
                self._in_transaction = False
                raise
            con.execute("COMMIT")
            self._in_transaction = False
            # Persist any dirty bitmap fragments alongside the relational
            # commit. Without this, fragments only flushed in Store.close()
            # and a daemon SIGKILL between ingests left the relational
            # tables ahead of the on-disk bitmaps -- the exact corruption
            # surface that hit viascope earlier.
            if self._dirty_fragments:
                try:
                    self.flush_fragments()
                except Exception as exc:
                    # Don't roll the transaction back -- the relational
                    # write already landed. Surface the error so the next
                    # explicit flush retries.
                    import sys
                    print(f"[rmx] fragment flush failed: {exc!r}",
                          file=sys.stderr)
        return _scope()

    def deferred_links(self):
        """Context manager that buffers `link()` / `weighted_link()` calls
        and flushes them via one `bulk_link` at scope exit. Targets the
        markdown semantic extractors, which emit hundreds of small links
        per file — each one is a DuckDB write transaction in the default
        path; the buffered flush is one Arrow batch.

        Within the scope, the bitmap fragment is NOT updated until flush —
        callers that query their own writes mid-scope would miss them.
        Extractors don't, but the constraint is real.

        Re-entry safe: nested `with s.deferred_links():` blocks all
        contribute to the same buffer and only the outermost scope
        flushes.
        """
        from contextlib import contextmanager

        @contextmanager
        def _scope():
            if self._link_buffer is not None:
                # Nested — outer scope owns the flush.
                yield
                return
            self._link_buffer = []
            self._link_protect_buffer = []
            try:
                yield
            finally:
                items = self._link_buffer
                protects = self._link_protect_buffer
                self._link_buffer = None
                self._link_protect_buffer = None
                if items:
                    self.bulk_link(items)
                if protects:
                    con = self._connect()
                    ids = sorted({i for pair in protects for i in pair})
                    placeholders = ",".join("?" * len(ids))
                    con.execute(
                        f"UPDATE entities SET protected = 1 "
                        f"WHERE id IN ({placeholders})",
                        ids,
                    )
                    self._maybe_commit(con)
        return _scope()

    def link(
        self,
        linkage: str,
        concept_id: int,
        entity_id: int,
        weight: float | None = None,
        protect: bool = False,
    ) -> bool:
        linkage = _canonical_verb(linkage)
        if self._link_buffer is not None:
            self._link_buffer.append((linkage, concept_id, entity_id, weight))
            if protect:
                self._link_protect_buffer.append((concept_id, entity_id))
            # Optimistic return: extractors don't check this.
            return True
        lid = self.get_linkage_id(linkage)
        frag = self._load_fragment(linkage)
        bit = self._pack(concept_id, entity_id)
        already = bit in frag
        if not already:
            frag.add(bit)
            self._dirty_fragments.add(linkage)
        # maintain forward index + (re)set weight
        con = self._connect()
        con.execute(
            "INSERT INTO entity_links(entity_id, linkage_id, concept_id, weight) "
            "VALUES (?,?,?,?) "
            "ON CONFLICT(entity_id, linkage_id, concept_id) DO UPDATE SET weight = "
            "  CASE WHEN excluded.weight IS NULL THEN entity_links.weight ELSE excluded.weight END",
            (entity_id, lid, concept_id, weight),
        )
        if protect:
            con.execute(
                "UPDATE entities SET protected = 1 WHERE id IN (?, ?)",
                (concept_id, entity_id),
            )
        self._maybe_commit(con)
        if _log_enabled() and not self._replay_mode:
            cn = self._name_of(concept_id)
            en = self._name_of(entity_id)
            if cn and en:
                self._log_event(
                    "link",
                    linkage=linkage, c=cn[1],
                    e_kind=en[0], e=en[1], weight=weight,
                )
                if protect:
                    self._log_event("protect", kind=cn[0], name=cn[1], value=1)
                    self._log_event("protect", kind=en[0], name=en[1], value=1)
        return not already

    def unlink(self, linkage: str, concept_id: int, entity_id: int) -> bool:
        linkage = _canonical_verb(linkage)
        lid = self.get_linkage_id(linkage)
        frag = self._load_fragment(linkage)
        bit = self._pack(concept_id, entity_id)
        present = bit in frag
        # Resolve names BEFORE the delete so the log entry survives even when
        # the entity is later purged. Skipped when logging is off.
        cn = en = None
        if present and _log_enabled() and not self._replay_mode:
            cn = self._name_of(concept_id)
            en = self._name_of(entity_id)
        if present:
            frag.discard(bit)
            self._dirty_fragments.add(linkage)
        con = self._connect()
        con.execute(
            "DELETE FROM entity_links WHERE entity_id=? AND linkage_id=? AND concept_id=?",
            (entity_id, lid, concept_id),
        )
        self._maybe_commit(con)
        if present and cn and en:
            self._log_event(
                "unlink",
                linkage=linkage, c=cn[1], e_kind=en[0], e=en[1],
            )
        return present

    def derive_called_by(self) -> int:
        """Materialize `called_by` edges as the inverse of `calls`.

        `called_by` is registered with `inverse_of=calls` but nothing
        traverses that metadata at query time, and the tldr/graphify extractors
        never populate a unit's `called_by` field — so the linkage rendered a
        "CALLED BY" header with zero rows tool-wide ("who calls this function?"
        silently returned nothing). The data to derive it IS present as `calls`.

        Model: links are `entity --[linkage]--> concept`. A call is
        `caller_entity --calls--> callee_bare_concept`; a definition is
        `defn_entity --defines--> bare_concept`. So the callee ENTITY is whoever
        DEFINES the called bare name, and the caller's displayable name is the
        bare concept the caller entity defines. Join through `defines` on both
        sides and emit `callee_entity --called_by--> caller_bare_concept`.

        Idempotent (bulk_link skips bits already present) and source-agnostic
        (operates on the final `entity_links`, so it covers the metadata, tldr
        call-graph, graphify, and python-semantic passes at once). Returns the
        number of newly added called_by edges.
        """
        con = self._connect()
        try:
            calls_lid = self.get_linkage_id("calls")
            defines_lid = self.get_linkage_id("defines")
        except Exception:
            return 0
        rows = con.execute(
            """
            SELECT DISTINCT def_callee.entity_id  AS callee_entity,
                            def_caller.concept_id AS caller_concept
            FROM entity_links calls
            JOIN entity_links def_callee
              ON def_callee.linkage_id = ?
             AND def_callee.concept_id = calls.concept_id
            JOIN entity_links def_caller
              ON def_caller.linkage_id = ?
             AND def_caller.entity_id = calls.entity_id
            WHERE calls.linkage_id = ?
              AND def_callee.entity_id <> calls.entity_id
            """,
            (defines_lid, defines_lid, calls_lid),
        ).fetchall()
        if not rows:
            return 0
        items = [
            ("called_by", int(caller_concept), int(callee_entity), 1.0)
            for (callee_entity, caller_concept) in rows
        ]
        return self.bulk_link(items)

    def bulk_link(
        self,
        items: list[tuple[str, int, int, float | None]],
    ) -> int:
        """Insert many links at once, amortizing per-row INSERT overhead.

        `items` is a list of `(linkage_name, concept_id, entity_id, weight)`
        tuples. Bitmap fragments are updated in-process (one pass); the
        relational `entity_links` shadow is written in a single SQL
        statement — Arrow batch under DuckDB, `executemany` under SQLite.
        Returns the number of bitmap bits newly added.

        Weight policy matches `link()`: on conflict the existing row's
        weight is preserved unless the new weight is non-NULL. SQLite's
        `INSERT OR IGNORE` skips the weight update entirely on conflict,
        so callers updating weights for already-linked pairs should stick
        with `link()`; bulk_link is for the ingest-time path where the
        common case is fresh links.
        """
        if not items:
            return 0
        # Resolve linkage names once. The cache hit on _connect() at the
        # bottom also serves the bitmap fragment loads.
        linkage_ids: dict[str, int] = {}
        for linkage, _c, _e, _w in items:
            if linkage not in linkage_ids:
                linkage_ids[linkage] = self.get_linkage_id(linkage)

        # In-process bitmap updates. Track newly added per linkage for the
        # log + the return value.
        added_total = 0
        newly_added_for_log: list[tuple[str, int, int, float | None]] = []
        for linkage, concept_id, entity_id, weight in items:
            frag = self._load_fragment(linkage)
            bit = self._pack(concept_id, entity_id)
            if bit not in frag:
                added_total += 1
                frag.add(bit)
                self._dirty_fragments.add(linkage)
                newly_added_for_log.append(
                    (linkage, concept_id, entity_id, weight)
                )

        con = self._connect()
        if self._backend.kind == "duckdb":
            # Arrow batch path. DuckDB ingests an Arrow table in one shot,
            # avoiding the per-row binder overhead of executemany.
            import pyarrow as pa

            tbl = pa.table({
                "entity_id":  [it[2] for it in items],
                "linkage_id": [linkage_ids[it[0]] for it in items],
                "concept_id": [it[1] for it in items],
                "weight":     [it[3] for it in items],
            })
            con._duck.register("_rmx_bulk_links", tbl)
            try:
                con._duck.execute(
                    "INSERT INTO entity_links"
                    "(entity_id, linkage_id, concept_id, weight) "
                    "SELECT entity_id, linkage_id, concept_id, weight "
                    "FROM _rmx_bulk_links "
                    "ON CONFLICT(entity_id, linkage_id, concept_id) DO NOTHING"
                )
            finally:
                con._duck.unregister("_rmx_bulk_links")
        else:
            con.executemany(
                "INSERT OR IGNORE INTO entity_links"
                "(entity_id, linkage_id, concept_id, weight) "
                "VALUES (?,?,?,?)",
                [
                    (it[2], linkage_ids[it[0]], it[1], it[3])
                    for it in items
                ],
            )
        self._maybe_commit(con)

        if newly_added_for_log and _log_enabled() and not self._replay_mode:
            # Resolve names once per concept/entity rather than per link.
            name_cache: dict[int, tuple[str, str] | None] = {}
            def _name(eid: int):
                if eid not in name_cache:
                    name_cache[eid] = self._name_of(eid)
                return name_cache[eid]
            for linkage, concept_id, entity_id, weight in newly_added_for_log:
                cn = _name(concept_id)
                en = _name(entity_id)
                if cn and en:
                    self._log_event(
                        "link",
                        linkage=linkage, c=cn[1],
                        e_kind=en[0], e=en[1], weight=weight,
                    )
        return added_total

    def link_many(self, linkage: str, concept_id: int, entity_ids: Iterable[int]) -> int:
        lid = self.get_linkage_id(linkage)
        frag = self._load_fragment(linkage)
        ids = list(entity_ids)
        before = len(frag)
        # Track which bits are actually new so the log doesn't repeat already-set
        # links (link_many is hot in ingest).
        newly_added: list[int] = []
        for eid in ids:
            bit = self._pack(concept_id, eid)
            if bit not in frag:
                newly_added.append(eid)
            frag.add(bit)
        added = len(frag) - before
        if added:
            self._dirty_fragments.add(linkage)
        con = self._connect()
        con.executemany(
            "INSERT OR IGNORE INTO entity_links(entity_id, linkage_id, concept_id) "
            "VALUES (?,?,?)",
            [(eid, lid, concept_id) for eid in ids],
        )
        self._maybe_commit(con)
        if newly_added and _log_enabled() and not self._replay_mode:
            cn = self._name_of(concept_id)
            if cn:
                for eid in newly_added:
                    en = self._name_of(eid)
                    if en:
                        self._log_event(
                            "link",
                            linkage=linkage, c=cn[1],
                            e_kind=en[0], e=en[1], weight=None,
                        )
        return added

    def weighted_link(
        self,
        linkage: str,
        concept_id: int,
        entity_id: int,
        weight: float,
    ) -> bool:
        """Set the (linkage, concept, entity) bit and store a ranking weight."""
        return self.link(linkage, concept_id, entity_id, weight=weight)

    def get_weight(
        self, linkage: str, concept_id: int, entity_id: int
    ) -> float | None:
        lid = self.get_linkage_id(linkage)
        row = self._connect().execute(
            "SELECT weight FROM entity_links "
            "WHERE entity_id=? AND linkage_id=? AND concept_id=?",
            (entity_id, lid, concept_id),
        ).fetchone()
        return row[0] if row and row[0] is not None else None

    def top_weighted(
        self, linkage: str, concept_id: int, k: int = 10
    ) -> list[tuple[int, float]]:
        lid = self.get_linkage_id(linkage)
        # JOIN entities so cross-partition entries don't surface here. In
        # normal usage all entity_links rows for a given concept_id sit in the
        # concept's home partition (because link() resolves both sides through
        # get_entity, which is partition-scoped); the JOIN is defensive against
        # programmatic cross-partition writes.
        return [
            (r[0], r[1])
            for r in self._connect().execute(
                "SELECT el.entity_id, el.weight FROM entity_links el "
                "JOIN entities e ON e.id = el.entity_id "
                "WHERE el.linkage_id=? AND el.concept_id=? "
                "  AND el.weight IS NOT NULL AND e.partition_id=? "
                "ORDER BY el.weight DESC, el.entity_id ASC LIMIT ?",
                (lid, concept_id, self._partition_id, k),
            )
        ]

    def _mentions_bm25_stats(self, mentions_lid: int) -> tuple[int, float]:
        """(N, avgdl) for BM25 over the `mentions` forward index in the active
        partition: N = #entities carrying any mention edge, avgdl = mean
        summed-tf per such entity. Cached per (instance, partition) — N/avgdl
        are slow-moving denominators, so a small staleness between ingests is
        harmless; a long-lived daemon Store computes this once."""
        cache = getattr(self, "_bm25_stats_cache", None)
        if cache is not None and cache[0] == self._partition_id:
            return cache[1], cache[2]
        row = self._connect().execute(
            "SELECT COUNT(DISTINCT el.entity_id), COALESCE(SUM(el.weight), 0) "
            "FROM entity_links el JOIN entities e ON e.id = el.entity_id "
            "WHERE el.linkage_id=? AND e.partition_id=?",
            (mentions_lid, self._partition_id),
        ).fetchone()
        n = int(row[0] or 0)
        avgdl = (float(row[1] or 0.0) / n) if n else 0.0
        self._bm25_stats_cache = (self._partition_id, n, avgdl)
        return n, avgdl

    def content_rank(
        self,
        terms: "list[str]",
        *,
        kinds: "list[str] | None" = None,
        limit: int = 50,
        k1: float = 1.5,
        b: float = 0.75,
        coverage_alpha: float = 3.0,
    ) -> "list[tuple[int, float]]":
        """BM25 (+ coverage^alpha) over the `mentions` forward index for a bag
        of query terms — the live counterpart of the eval retriever's winning
        variant, computed straight off `entity_links` (concept = term, weight =
        tf). Returns `[(entity_id, score)]` best-first (score > 0), scoped to
        the active partition.

        Lets `rmx context "<natural language>"` rank the entities whose bodies
        actually contain the query terms (via their docstring/body `mentions`
        edges), instead of only resolving an exact concept-name anchor."""
        import math
        terms = [t for t in (terms or []) if t and t.strip()]
        if not terms:
            return []
        con = self._connect()
        try:
            mlid = self.get_linkage_id("mentions")
        except Exception:
            return []
        # Each query term → its matching mention-concept ids: variant/canonical
        # expansion (so `FovWedge` and `fov_wedge` collapse) PLUS namespaced
        # auto-concepts (`keyword/<t>`, `import/<t>`, …) so a code file's
        # docstring keywords + import edges are reachable by the bare term.
        term_cids: list[list[int]] = []
        for t in terms:
            cids = list(self.resolve_concept_ids(t, strict=False) or [])
            seen_t = set(cids)
            for r in con.execute(
                "SELECT id FROM entities WHERE kind='concept' AND partition_id=? "
                "AND lower(name) LIKE ?",
                (self._partition_id, f"%/{t.lower()}"),
            ):
                if r[0] not in seen_t:
                    seen_t.add(r[0])
                    cids.append(r[0])
            term_cids.append(cids)
        cid_to_term: dict[int, int] = {}
        for ti, cids in enumerate(term_cids):
            for c in cids:
                cid_to_term.setdefault(c, ti)
        flat = list(cid_to_term)
        if not flat:
            return []
        kind_clause = f" AND e.kind IN ({','.join('?' * len(kinds))})" if kinds else ""
        scores: dict[int, float] = {}
        cover: dict[int, set] = {}
        # BM25 (+ coverage) over the `mentions` index. Skipped wholesale when the
        # index is empty or these terms have no mention postings — an exact
        # symbol with no body mentions still falls through to def-surfacing below.
        N, avgdl = self._mentions_bm25_stats(mlid)
        if N > 0 and avgdl > 0:
            # Document frequency per query term (global within the partition).
            n_term: dict[int, int] = {}
            for ti, cids in enumerate(term_cids):
                if not cids:
                    n_term[ti] = 0
                    continue
                ph = ",".join("?" * len(cids))
                n_term[ti] = int(con.execute(
                    f"SELECT COUNT(DISTINCT el.entity_id) FROM entity_links el "
                    f"JOIN entities e ON e.id = el.entity_id "
                    f"WHERE el.linkage_id=? AND e.partition_id=? "
                    f"AND el.concept_id IN ({ph})",
                    (mlid, self._partition_id, *cids),
                ).fetchone()[0] or 0)
            # Postings for the query-term concepts (partition + optional kind scope).
            ph = ",".join("?" * len(flat))
            rows = con.execute(
                f"SELECT el.entity_id, el.concept_id, el.weight FROM entity_links el "
                f"JOIN entities e ON e.id = el.entity_id "
                f"WHERE el.linkage_id=? AND e.partition_id=? "
                f"AND el.concept_id IN ({ph}){kind_clause}",
                (mlid, self._partition_id, *flat, *(kinds or [])),
            ).fetchall()
            if rows:
                cand_ids = sorted({r[0] for r in rows})
                ph2 = ",".join("?" * len(cand_ids))
                doc_len = {
                    r[0]: float(r[1] or 0.0) for r in con.execute(
                        f"SELECT entity_id, SUM(weight) FROM entity_links "
                        f"WHERE linkage_id=? AND entity_id IN ({ph2}) GROUP BY entity_id",
                        (mlid, *cand_ids),
                    )
                }
                for eid, cid, w in rows:
                    ti = cid_to_term.get(cid)
                    if ti is None:
                        continue
                    nt = n_term.get(ti, 0)
                    if nt <= 0:
                        continue
                    idf = math.log((N - nt + 0.5) / (nt + 0.5) + 1.0)
                    tf = float(w or 0.0)
                    dl = doc_len.get(eid, avgdl)
                    denom = tf + k1 * (1.0 - b + b * dl / avgdl)
                    if denom <= 0:
                        continue
                    scores[eid] = scores.get(eid, 0.0) + idf * (tf * (k1 + 1.0)) / denom
                    cover.setdefault(eid, set()).add(ti)
                n_units = sum(1 for cids in term_cids if cids) or 1
                if coverage_alpha > 0 and n_units > 1:
                    for eid in list(scores):
                        scores[eid] *= (len(cover[eid]) / n_units) ** coverage_alpha
        # M1 — surface DEFINITION files. A symbol's own name is a `defines`
        # concept on its file, not a `mentions` term, so the file that DEFINES
        # the query symbol is otherwise ABSENT from this index entirely (the
        # deeper root of the exact-symbol `w=0` miss). Add the def entities for
        # the query-term concepts with a small floor score so they're RETURNED:
        # `_floor_exact_defs` (context) lifts an exact-symbol def above fuzzy
        # body mentions, while for NL phrases they sit below real hits and get
        # trimmed by `limit`. Skipped silently if `defines` doesn't exist yet.
        try:
            dlid = self.get_linkage_id("defines")
        except Exception:
            dlid = None
        if dlid is not None and flat:
            ph_def = ",".join("?" * len(flat))
            def_rows = con.execute(
                f"SELECT DISTINCT el.entity_id FROM entity_links el "
                f"JOIN entities e ON e.id = el.entity_id "
                f"WHERE el.linkage_id=? AND e.partition_id=? "
                f"AND el.concept_id IN ({ph_def}){kind_clause}",
                (dlid, self._partition_id, *flat, *(kinds or [])),
            ).fetchall()
            for (eid,) in def_rows:
                if eid not in scores:
                    scores[eid] = 1e-3
        if not scores:
            return []
        return sorted(scores.items(), key=lambda kv: -kv[1])[:limit]

    def add_evidence(
        self,
        linkage: str,
        concept_id: int,
        entity_id: int,
        *,
        file: str | None = None,
        line: int | None = None,
        span_end: int | None = None,
        detail: str | None = None,
    ) -> None:
        """Record where a linkage came from. Pure annotation — does not affect bitmaps."""
        linkage = _canonical_verb(linkage)
        lid = self.get_linkage_id(linkage)
        con = self._connect()
        con.execute(
            "INSERT INTO linkage_evidence(entity_id, linkage_id, concept_id, "
            "file, line, span_end, detail) VALUES (?,?,?,?,?,?,?)",
            (entity_id, lid, concept_id, file, line, span_end, detail),
        )
        self._maybe_commit(con)
        if _log_enabled() and not self._replay_mode:
            cn = self._name_of(concept_id)
            en = self._name_of(entity_id)
            if cn and en:
                self._log_event(
                    "evidence",
                    linkage=linkage, c=cn[1], e_kind=en[0], e=en[1],
                    file=file, line=line, span_end=span_end, detail=detail,
                )

    def get_evidence(
        self, entity_id: int, linkage: str | None = None, concept_id: int | None = None
    ) -> list[dict]:
        sql = (
            "SELECT linkage_types.name AS linkage, e.concept_id, "
            "       c.name AS concept_name, e.file, e.line, e.span_end, e.detail "
            "FROM linkage_evidence e "
            "JOIN linkage_types ON linkage_types.id = e.linkage_id "
            "LEFT JOIN entities c ON c.id = e.concept_id "
            "WHERE e.entity_id = ?"
        )
        params: list = [entity_id]
        if linkage is not None:
            sql += " AND linkage_types.name = ?"
            params.append(linkage)
        if concept_id is not None:
            sql += " AND e.concept_id = ?"
            params.append(concept_id)
        return [dict(r) for r in self._connect().execute(sql, params)]

    def explain_entity(self, entity_id: int) -> list[dict]:
        """Return every (linkage, concept) the entity is a member of, plus evidence."""
        rows = [
            dict(r)
            for r in self._connect().execute(
                """
                SELECT linkage_types.name AS linkage,
                       el.concept_id        AS concept_id,
                       c.name               AS concept_name,
                       el.weight            AS weight
                FROM entity_links el
                JOIN linkage_types ON linkage_types.id = el.linkage_id
                LEFT JOIN entities c ON c.id = el.concept_id
                WHERE el.entity_id = ?
                ORDER BY linkage_types.name, c.name
                """,
                (entity_id,),
            )
        ]
        for r in rows:
            r["evidence"] = self.get_evidence(
                entity_id, linkage=r["linkage"], concept_id=r["concept_id"]
            )
        return rows

    def add_namespaced_concept(
        self, namespace: str, name: str, description: str | None = None
    ) -> int:
        """Convention: namespaced concepts are stored as 'ns/name'.

        The DSL parser already accepts '/' inside concept refs, so a query
        like `mentions:keyword/parser` parses as expected. Bare user concepts
        (`parser`) don't collide with namespaced ones (`keyword/parser`).
        """
        return self.add_concept(f"{namespace}/{name}", description=description)

    def list_concepts_in_namespace(self, namespace: str) -> list[Entity]:
        prefix = f"{namespace}/"
        return [
            self._row_to_entity(r)
            for r in self._connect().execute(
                "SELECT * FROM entities "
                "WHERE partition_id=? AND kind='concept' AND name LIKE ? || '%'",
                (self._partition_id, prefix),
            )
        ]

    # ---- canon (cross-partition concept matching) -------------------------

    def link_canon(
        self,
        local_concept_id: int,
        canon_partition: str,
        canon_concept_name: str,
    ) -> int:
        """Wire the active partition's concept to a canonical concept living
        in `canon_partition`. Auto-creates the canon concept if missing.
        Returns the canon concept_id.

        The same_as edge lands in entity_links (partition-blind), so siblings
        are reachable from any partition's Store via siblings_via_canon().
        The bitmap-fragment side accumulates the bit in the active partition's
        same_as fragment — fine, since traversal uses entity_links and the
        per-partition fragment isn't read for canon hops."""
        local = self.get_entity_by_id(local_concept_id)
        if local is None or local.kind != "concept":
            raise ValueError(
                f"local_concept_id={local_concept_id} is not a concept"
            )
        # Open the canon partition just long enough to ensure the canon
        # concept row exists. This auto-registers the partition too if it's
        # the first reference to that name; we then bump its kind to 'canon'
        # since link_canon is the explicit signal that this is a canon hub.
        canon_store = Store(self.root, partition=canon_partition)
        try:
            canon_id = canon_store.add_concept(canon_concept_name)
            canon_store._connect().execute(
                "UPDATE partitions SET kind='canon' WHERE name=? AND kind='repo'",
                (canon_partition,),
            )
            canon_store._connect().commit()
        finally:
            canon_store.close()
        # Record the same_as edge from the active Store. The link API treats
        # concept_id as the row anchor and entity_id as the member — for a
        # concept-to-concept edge we use the canon as the anchor and the
        # local as the member, so loading bitmap(same_as, canon_id) yields
        # all per-partition concepts that point at this canon.
        self.link("same_as", canon_id, local_concept_id)
        return canon_id

    def siblings_via_canon(self, concept_id: int) -> list[dict]:
        """Concepts in any partition that share at least one canon hub with
        the given concept_id. Returns [{id, name, partition_id, partition_name,
        canon_id, canon_name, canon_partition}, ...]. Excludes the input
        concept itself."""
        con = self._connect()
        canon_rows = con.execute(
            "SELECT el.concept_id, c.name, c.partition_id, p.name AS partition_name "
            "FROM entity_links el "
            "JOIN linkage_types lt ON lt.id = el.linkage_id "
            "JOIN entities c ON c.id = el.concept_id "
            "JOIN partitions p ON p.id = c.partition_id "
            "WHERE el.entity_id = ? AND lt.name = 'same_as'",
            (concept_id,),
        ).fetchall()
        if not canon_rows:
            return []
        out: list[dict] = []
        seen: set[int] = set()
        for canon in canon_rows:
            siblings = con.execute(
                "SELECT e.id, e.name, e.partition_id, p.name AS partition_name "
                "FROM entity_links el "
                "JOIN linkage_types lt ON lt.id = el.linkage_id "
                "JOIN entities e ON e.id = el.entity_id "
                "JOIN partitions p ON p.id = e.partition_id "
                "WHERE el.concept_id = ? AND lt.name = 'same_as' "
                "  AND e.id != ?",
                (canon["concept_id"], concept_id),
            ).fetchall()
            for s in siblings:
                if s["id"] in seen:
                    continue
                seen.add(s["id"])
                out.append({
                    "id": s["id"],
                    "name": s["name"],
                    "partition_id": s["partition_id"],
                    "partition_name": s["partition_name"],
                    "canon_id": canon["concept_id"],
                    "canon_name": canon["name"],
                    "canon_partition": canon["partition_name"],
                })
        return out

    # ---- purge / track files -----------------------------------------------

    def purge_entity(self, entity_id: int, *, _skip_lance: bool = False) -> int:
        """Remove an entity from every bitmap it's a member of, drop the row,
        and drop its dense vector from the matching Lance dataset.

        `_skip_lance=True` lets a caller that has already issued a batched
        Lance delete (e.g. `bulk_forget_memories`) suppress the redundant
        per-id Lance open. Internal flag — not part of the public contract.
        """
        con = self._connect()
        # Resolve names BEFORE deletion so log events can reference them.
        log_on = _log_enabled() and not self._replay_mode
        self_name = self._name_of(entity_id) if log_on else None
        # Look up kind upfront so the Lance side can be dropped before the
        # row goes away. `_name_of` returns (kind, name) — reuse it when
        # the logger already needs the result; otherwise do a minimal
        # single-column read. The kind is None for ids that don't exist;
        # the Lance drop short-circuits in that case.
        if self_name is not None:
            kind = self_name[0]
        else:
            row = self._read().execute(
                "SELECT kind FROM entities WHERE id=?", (entity_id,),
            ).fetchone()
            kind = row["kind"] if row else None
        if kind is not None and not _skip_lance:
            self._drop_lance_for_purge(entity_id, kind)
        es_pairs: list[tuple[str, str, str]] = []  # (linkage, c_kind, c_name)
        cs_pairs: list[tuple[str, str, str]] = []  # (linkage, e_kind, e_name)
        if log_on and self_name:
            es_pairs = [
                (r["linkage"], r["c_kind"], r["c_name"])
                for r in con.execute(
                    """
                    SELECT lt.name AS linkage, c.kind AS c_kind, c.name AS c_name
                    FROM entity_links el
                    JOIN linkage_types lt ON lt.id = el.linkage_id
                    JOIN entities c ON c.id = el.concept_id
                    WHERE el.entity_id = ?
                    """,
                    (entity_id,),
                )
            ]
            cs_pairs = [
                (r["linkage"], r["e_kind"], r["e_name"])
                for r in con.execute(
                    """
                    SELECT lt.name AS linkage, e.kind AS e_kind, e.name AS e_name
                    FROM entity_links el
                    JOIN linkage_types lt ON lt.id = el.linkage_id
                    JOIN entities e ON e.id = el.entity_id
                    WHERE el.concept_id = ?
                    """,
                    (entity_id,),
                )
            ]
        rows = con.execute(
            """
            SELECT entity_links.linkage_id, entity_links.concept_id, linkage_types.name
            FROM entity_links
            JOIN linkage_types ON linkage_types.id = entity_links.linkage_id
            WHERE entity_links.entity_id = ?
            """,
            (entity_id,),
        ).fetchall()
        n = 0
        # Drop the entity from every (linkage, concept) row it appears in.
        for r in rows:
            ln = r["name"]
            cid = r["concept_id"]
            frag = self._load_fragment(ln)
            bit = self._pack(cid, entity_id)
            if bit in frag:
                frag.discard(bit)
                self._dirty_fragments.add(ln)
                n += 1
        con.execute("DELETE FROM entity_links WHERE entity_id=?", (entity_id,))
        # If the entity is also a concept (its id appears as the high-32-bit
        # prefix of bits in any fragment), clear that whole row too.
        prefix_start = entity_id << _CONCEPT_SHIFT
        prefix_end = (entity_id + 1) << _CONCEPT_SHIFT
        for ln in (lk["name"] for lk in self.list_linkages()):
            frag = self._load_fragment(ln)
            if frag.range_cardinality(prefix_start, prefix_end) > 0:
                frag.remove_range(prefix_start, prefix_end)
                self._dirty_fragments.add(ln)
                n += 1
        # Forward index rows where this id is the concept side also go.
        con.execute("DELETE FROM entity_links WHERE concept_id=?", (entity_id,))
        con.execute("DELETE FROM entities WHERE id=?", (entity_id,))
        con.execute("DELETE FROM concepts WHERE id=?", (entity_id,))
        # Memory sidecar (no-op for non-memory rows; sqlite has FK CASCADE
        # set but the daemon does not turn PRAGMA foreign_keys on, and
        # DuckDB's memory_content has no FK clause at all — so the explicit
        # DELETE is what guarantees the sidecar row goes away).
        con.execute("DELETE FROM memory_content WHERE entity_id=?", (entity_id,))
        con.execute(
            "DELETE FROM tracked_files WHERE partition_id=? AND path = "
            "(SELECT path FROM entities WHERE id=?)",
            (self._partition_id, entity_id),
        )
        con.commit()
        if log_on and self_name:
            kind, name = self_name
            for linkage, c_kind, c_name in es_pairs:
                self._log_event(
                    "unlink",
                    linkage=linkage, c=c_name, e_kind=kind, e=name,
                )
            for linkage, e_kind, e_name in cs_pairs:
                self._log_event(
                    "unlink",
                    linkage=linkage, c=name, e_kind=e_kind, e=e_name,
                )
            self._log_event("tombstone", kind=kind, name=name)
        return n

    def fold_concept_dups(self, *, dry_run: bool = False) -> dict:
        """Fold every kind=concept entity whose (partition, name) collides
        with a kind=memory entity in the SAME partition into that memory:
        migrate the concept's graph edges onto the memory, then purge the
        concept.

        Repairs pre-0.7.6 duplicate-node debt — the GMD `__root__` node minted
        a concept twinning the doc-level memory, splitting a subject's edges
        across two nodes. New ingests no longer create the dup (ingest_gmd
        fix); this cleans the ones already on disk. Active partition only.

        Edges already present on the memory are left untouched (the memory's
        post-reingest weights are authoritative); only edges the memory lacks
        are migrated. Self-loops (concept↔its own memory) are dropped.

        Returns {folded, edges_migrated, dry_run}."""
        con = self._connect()
        pairs = con.execute(
            """
            SELECT c.id AS cid, m.id AS mid
            FROM entities c
            JOIN entities m
              ON c.name = m.name AND c.partition_id = m.partition_id
            WHERE c.kind = 'concept' AND m.kind = 'memory'
              AND c.partition_id = ?
            """,
            (self._partition_id,),
        ).fetchall()

        folded = 0
        edges_migrated = 0
        for row in pairs:
            cid, mid = int(row["cid"]), int(row["mid"])
            if cid == mid:
                continue
            # The concept as the SOURCE side (concept_id=cid).
            out_edges = con.execute(
                "SELECT lt.name AS ln, el.entity_id AS eid, el.weight AS w "
                "FROM entity_links el JOIN linkage_types lt "
                "ON lt.id = el.linkage_id WHERE el.concept_id = ?",
                (cid,),
            ).fetchall()
            # The concept as the OBJECT side (entity_id=cid).
            in_edges = con.execute(
                "SELECT lt.name AS ln, el.concept_id AS cpid, el.weight AS w "
                "FROM entity_links el JOIN linkage_types lt "
                "ON lt.id = el.linkage_id WHERE el.entity_id = ?",
                (cid,),
            ).fetchall()
            if dry_run:
                folded += 1
                edges_migrated += len(out_edges) + len(in_edges)
                continue
            # Edges the memory already carries — don't clobber its weights.
            m_out = {
                (r["ln"], int(r["eid"])) for r in con.execute(
                    "SELECT lt.name AS ln, el.entity_id AS eid "
                    "FROM entity_links el JOIN linkage_types lt "
                    "ON lt.id = el.linkage_id WHERE el.concept_id = ?",
                    (mid,),
                )
            }
            m_in = {
                (r["ln"], int(r["cpid"])) for r in con.execute(
                    "SELECT lt.name AS ln, el.concept_id AS cpid "
                    "FROM entity_links el JOIN linkage_types lt "
                    "ON lt.id = el.linkage_id WHERE el.entity_id = ?",
                    (mid,),
                )
            }
            for e in out_edges:
                tgt = int(e["eid"])
                if tgt == mid or (e["ln"], tgt) in m_out:
                    continue
                self.link(e["ln"], mid, tgt, weight=e["w"])
                edges_migrated += 1
            for e in in_edges:
                src = int(e["cpid"])
                if src == mid or (e["ln"], src) in m_in:
                    continue
                self.link(e["ln"], src, mid, weight=e["w"])
                edges_migrated += 1
            self.purge_entity(cid)
            folded += 1

        if not dry_run and folded:
            self.flush_fragments()
        return {"folded": folded, "edges_migrated": edges_migrated,
                "dry_run": dry_run}

    def purge_path(self, abs_path: str) -> int:
        """Remove every entity (file + per-function) anchored at abs_path.
        Returns the number of *entities* removed. Scoped to the active
        partition so two partitions tracking the same path stay isolated."""
        con = self._connect()
        ids = [
            r[0] for r in con.execute(
                "SELECT id FROM entities WHERE partition_id=? AND path=?",
                (self._partition_id, abs_path),
            )
        ]
        for eid in ids:
            self.purge_entity(eid)
        con.execute(
            "DELETE FROM tracked_files WHERE partition_id=? AND path=?",
            (self._partition_id, abs_path),
        )
        con.commit()
        self._log_event("untrack", path=abs_path)
        return len(ids)

    # -- protected / noise flag CRUD + forget -------------------------------
    #
    # The replay log already carries `protect` / `noise` / `tombstone` events
    # (see `_apply_event`); these are the on-demand emitters + a selector layer
    # so the CLI can read, set, clear, and delete by name / glob / namespace.

    def find_entity_ids(
        self, *, names=None, like=None, namespace=None, kind=None,
        protected=None, noise=None,
    ) -> "list[tuple[int, str, str, int, int]]":
        """Resolve entities in the ACTIVE partition by any combination of
        selectors. Returns `(id, name, kind, protected, noise)` rows sorted by
        name. `names` is exact-match; `like` is a SQL LIKE glob; `namespace`
        is shorthand for the `NS/%` prefix; `kind` / `protected` / `noise`
        refine. No selector → every entity in the partition."""
        where = ["partition_id = ?"]
        params: list = [self.partition_id]
        if names:
            where.append("name IN (" + ",".join("?" * len(names)) + ")")
            params += list(names)
        if like:
            where.append("name LIKE ?")
            params.append(like)
        if namespace:
            where.append("name LIKE ?")
            params.append(f"{namespace}/%")
        if kind:
            where.append("kind = ?")
            params.append(kind)
        if protected is not None:
            where.append("protected = ?")
            params.append(1 if protected else 0)
        if noise is not None:
            where.append("noise = ?")
            params.append(1 if noise else 0)
        rows = self._connect().execute(
            f"SELECT id, name, kind, protected, noise FROM entities "
            f"WHERE {' AND '.join(where)} ORDER BY name", params,
        ).fetchall()
        return [(r[0], r[1], r[2], r[3], r[4]) for r in rows]

    def set_entity_flag(self, ids, flag: str, value: bool) -> int:
        """Set `protected` or `noise` to `value` on each id, emitting one
        replayable event per row so the flag survives a rebuild-from-log.
        Returns the number of rows changed."""
        if flag not in ("protected", "noise"):
            raise ValueError(f"unknown flag: {flag}")
        ids = list(ids)
        if not ids:
            return 0
        con = self._connect()
        now = time.time()
        v = 1 if value else 0
        ev = "protect" if flag == "protected" else "noise"
        n = 0
        for eid in ids:
            row = con.execute(
                "SELECT kind, name FROM entities WHERE id=?", (eid,)).fetchone()
            if not row:
                continue
            con.execute(
                f"UPDATE entities SET {flag}=?, updated_at=? WHERE id=?",
                (v, now, eid))
            self._log_event(ev, kind=row["kind"], name=row["name"], value=v)
            n += 1
        self._maybe_commit(con)
        return n

    def set_flag_by_selector(self, flag: str, value: bool, **selectors) -> dict:
        """Resolve `selectors` (see `find_entity_ids`) then set `flag`. Returns
        `{count, names}` so the caller can report exactly what changed."""
        rows = self.find_entity_ids(**selectors)
        names = [r[1] for r in rows]
        count = self.set_entity_flag([r[0] for r in rows], flag, value)
        return {"count": count, "names": names}

    def forget_by_selector(self, *, dry_run: bool = False, **selectors) -> dict:
        """Resolve `selectors` then bulk-purge them (drops the row, every bitmap
        membership, linkage evidence, memory sidecar, and the Lance vector;
        emits a `tombstone` per id so the delete replays). `dry_run` previews
        the matched names without deleting. Returns `{forgotten, names,
        dry_run}`.

        Uses the batched `_bulk_purge_ids` path so a large selection (e.g.
        `forget --kind code` over a partition's thousands of rows) completes in
        one pass instead of a per-entity loop that times out the daemon RPC.
        The graph result is identical to looping `purge_entity`."""
        rows = self.find_entity_ids(**selectors)
        names = [r[1] for r in rows]
        if dry_run:
            return {"forgotten": 0, "names": names, "dry_run": True}
        self._bulk_purge_ids([(int(r[0]), r[2], r[1]) for r in rows])
        return {"forgotten": len(rows), "names": names, "dry_run": False}

    def _bulk_purge_ids(self, info: "list[tuple[int, str, str]]") -> int:
        """Batched purge of `(id, kind, name)` triples — the scalable sibling of
        `purge_entity`. One-pass bitmap-fragment cleanup + chunked SQL deletes +
        per-id tombstones. Produces the same graph state as looping
        `purge_entity`, but issues O(#linkages) fragment scans and O(rows/chunk)
        DELETEs instead of O(#entities) of each. Caller owns lock/partition."""
        if not info:
            return 0
        con = self._connect()
        ids = [int(i) for i, _k, _n in info]
        chunk = 900

        def _chunks(seq):
            for i in range(0, len(seq), chunk):
                yield seq[i:i + chunk]

        # 1. Lance: one drop per kind (not per id).
        ids_by_kind: dict[str, list[int]] = {}
        for eid, kind, _name in info:
            ids_by_kind.setdefault(kind, []).append(int(eid))
        try:
            self._drop_lance_for_purge_batch(ids_by_kind)
        except Exception:
            pass

        # 2. Bitmap cleanup. Entity-side: gather the (linkage, packed-bit) set
        #    for edges where a killed id is the ENTITY, then discard. Concept-
        #    side: for ids that are a concept prefix, remove the whole row range.
        bits_by_ln: dict[str, list[int]] = {}
        for ck in _chunks(ids):
            ph = ",".join("?" * len(ck))
            for r in con.execute(
                f"SELECT lt.name AS ln, el.concept_id AS cid, el.entity_id AS eid "
                f"FROM entity_links el JOIN linkage_types lt "
                f"ON lt.id = el.linkage_id WHERE el.entity_id IN ({ph})", ck,
            ).fetchall():
                bits_by_ln.setdefault(r["ln"], []).append(
                    self._pack(int(r["cid"]), int(r["eid"])))
        for ln in (lk["name"] for lk in self.list_linkages()):
            frag = self._load_fragment(ln)
            changed = False
            for bit in bits_by_ln.get(ln, ()):
                if bit in frag:
                    frag.discard(bit)
                    changed = True
            for kid in ids:
                start = kid << _CONCEPT_SHIFT
                end = (kid + 1) << _CONCEPT_SHIFT
                if frag.range_cardinality(start, end) > 0:
                    frag.remove_range(start, end)
                    changed = True
            if changed:
                self._dirty_fragments.add(ln)

        # 3. Chunked SQL deletes. tracked_files first (needs entities.path).
        for ck in _chunks(ids):
            ph = ",".join("?" * len(ck))
            con.execute(
                f"DELETE FROM tracked_files WHERE partition_id=? AND path IN "
                f"(SELECT path FROM entities WHERE id IN ({ph}) "
                f" AND path IS NOT NULL)", [self._partition_id, *ck])
            con.execute(f"DELETE FROM entity_links WHERE entity_id IN ({ph})", ck)
            con.execute(f"DELETE FROM entity_links WHERE concept_id IN ({ph})", ck)
            con.execute(f"DELETE FROM memory_content WHERE entity_id IN ({ph})", ck)
            con.execute(f"DELETE FROM concepts WHERE id IN ({ph})", ck)
            con.execute(f"DELETE FROM entities WHERE id IN ({ph})", ck)
        con.commit()

        # 4. Per-id tombstones so rebuild_index_from_log doesn't resurrect them.
        if _log_enabled() and not self._replay_mode:
            for _eid, kind, name in info:
                self._log_event("tombstone", kind=kind, name=name)
        return len(ids)

    def mark_tracked(self, abs_path: str, mtime: float) -> None:
        now = time.time()
        con = self._connect()
        con.execute(
            "INSERT INTO tracked_files(partition_id, path, mtime, last_synced) "
            "VALUES (?,?,?,?) "
            "ON CONFLICT(partition_id, path) DO UPDATE SET "
            "  mtime=excluded.mtime, last_synced=excluded.last_synced",
            (self._partition_id, abs_path, mtime, now),
        )
        con.commit()
        self._log_event("track", path=abs_path, mtime=mtime)

    def bulk_mark_tracked(self, rows: "list[tuple[str, float]]") -> None:
        """Mark many `(abs_path, mtime)` pairs tracked in one batched write.

        Bulk equivalent of `mark_tracked`: a single Arrow `INSERT...SELECT`
        (DuckDB) or one `executemany` (SQLite) plus one `_maybe_commit`,
        instead of a per-row INSERT + `con.commit()` each. Used by gated
        ingest passes that mark thousands of files at once (e.g. the
        `pysem:` markers for the `--semantic` Python pass) — per-row
        `mark_tracked` would force thousands of commits. Skips `_log_event`:
        these are internal gate markers, not user-facing mutations."""
        if not rows:
            return
        now = time.time()
        con = self._connect()
        if self._backend.kind == "duckdb":
            import pyarrow as pa

            tbl = pa.table({
                "partition_id": [self._partition_id] * len(rows),
                "path":         [r[0] for r in rows],
                "mtime":        [float(r[1]) for r in rows],
                "last_synced":  [now] * len(rows),
            })
            con._duck.register("_rmx_bulk_tracked", tbl)
            try:
                con._duck.execute(
                    "INSERT INTO tracked_files"
                    "(partition_id, path, mtime, last_synced) "
                    "SELECT partition_id, path, mtime, last_synced "
                    "FROM _rmx_bulk_tracked "
                    "ON CONFLICT(partition_id, path) DO UPDATE SET "
                    "  mtime=excluded.mtime, last_synced=excluded.last_synced"
                )
            finally:
                con._duck.unregister("_rmx_bulk_tracked")
        else:
            con.executemany(
                "INSERT INTO tracked_files"
                "(partition_id, path, mtime, last_synced) "
                "VALUES (?,?,?,?) "
                "ON CONFLICT(partition_id, path) DO UPDATE SET "
                "  mtime=excluded.mtime, last_synced=excluded.last_synced",
                [(self._partition_id, r[0], float(r[1]), now) for r in rows],
            )
        self._maybe_commit(con)

    def get_tracked_mtime(self, abs_path: str) -> float | None:
        """Return the tracked mtime for `abs_path` in the active partition,
        or None if the file isn't tracked. Used by sync to skip files whose
        on-disk mtime matches the indexed copy."""
        row = self._connect().execute(
            "SELECT mtime FROM tracked_files "
            "WHERE partition_id=? AND path=?",
            (self._partition_id, abs_path),
        ).fetchone()
        return float(row[0]) if row else None

    def list_tracked(self) -> list[tuple[str, float]]:
        return [
            (r[0], r[1])
            for r in self._connect().execute(
                "SELECT path, mtime FROM tracked_files WHERE partition_id=?",
                (self._partition_id,),
            )
        ]

    def stale_files(self) -> list[dict]:
        """Return tracked files where on-disk mtime is newer than last_synced.
        These are files the index doesn't yet reflect."""
        out: list[dict] = []
        from os import stat as _stat
        for path, mtime, last_synced in self._connect().execute(
            "SELECT path, mtime, last_synced FROM tracked_files WHERE partition_id=?",
            (self._partition_id,),
        ):
            # tracked_files also stores synthetic mtime-gate keys for the bulk
            # passes (`pysem:/abs`, `pssem:/abs`, …) — not real files, so they'd
            # always read as "missing". Real entries are absolute paths.
            if not path.startswith("/"):
                continue
            try:
                cur = _stat(path).st_mtime
            except OSError:
                out.append({"path": path, "status": "missing",
                            "mtime": mtime, "last_synced": last_synced})
                continue
            if cur > last_synced + 0.001:
                out.append({"path": path, "status": "stale",
                            "mtime": cur, "last_synced": last_synced})
        return out

    # ---- vacuum -----------------------------------------------------------

    def vacuum(self) -> dict:
        """Drop concepts that have zero linkages (empty bitmaps everywhere) and
        any tracked_files that point at paths no longer on disk. Returns a
        summary dict."""
        from os.path import exists as _exists
        con = self._connect()

        # 1. concepts whose every bitmap is empty == no rows in entity_links.
        # Skip protected concepts — those are user-asserted and survive vacuum
        # even when they have no links (e.g. a freshly-added bare concept).
        # Scoped to the active partition so vacuum can't drop concepts that
        # belong to a different agent's partition.
        empty_concepts = [
            r[0] for r in con.execute(
                """
                SELECT e.id FROM entities e
                LEFT JOIN entity_links el ON el.concept_id = e.id
                WHERE e.partition_id = ?
                  AND e.kind = 'concept'
                  AND el.entity_id IS NULL
                  AND e.protected = 0
                """,
                (self._partition_id,),
            )
        ]
        for cid in empty_concepts:
            self.purge_entity(cid)

        # 2. tracked_files for paths that no longer exist
        gone = [
            r[0] for r in con.execute(
                "SELECT path FROM tracked_files WHERE partition_id=?",
                (self._partition_id,),
            )
            if not _exists(r[0])
        ]
        for p in gone:
            self.purge_path(p)

        # 3. orphaned linkage_evidence rows (after purges, FKs handle this with
        # ON DELETE CASCADE — but make sure)
        con.execute(
            "DELETE FROM linkage_evidence WHERE entity_id NOT IN (SELECT id FROM entities)"
        )
        con.commit()

        return {
            "concepts_dropped": len(empty_concepts),
            "files_purged": len(gone),
        }

    # ---- noise pruning ----------------------------------------------------

    def prune_noise(
        self,
        *,
        namespaces: tuple[str, ...] = ("keyword",),
        min_df: int = 2,
        max_df_ratio: float = 0.25,
        drop: bool = False,
    ) -> dict:
        """Mark (or, with drop=True, delete) noise concepts in the given namespaces.

        DF = number of distinct entities the concept is linked to (across all
        linkages). Concepts with DF < min_df are too rare to matter; concepts
        with DF / total_entities > max_df_ratio are too generic.

        Default behavior is non-destructive: sets `noise=1` on offending
        concepts and clears it on concepts that no longer offend. Queries hide
        noise=1 concepts by default, but `--full` can resurrect them so the
        full graph remains available to find/grep-style use. Pass drop=True
        to actually purge marked concepts.

        Protected concepts are skipped entirely (they're never marked, never
        dropped).
        """
        con = self._connect()
        total = con.execute(
            "SELECT COUNT(*) FROM entities "
            "WHERE partition_id=? AND kind != 'concept'",
            (self._partition_id,),
        ).fetchone()[0]
        if total == 0:
            return {"marked": 0, "unmarked": 0, "kept": 0, "total_seen": 0,
                    "dropped": 0}

        max_df = max(min_df, int(total * max_df_ratio))
        seen = marked = unmarked = dropped = 0
        # Buffer noise transitions so log writes happen after commit.
        noise_changes: list[tuple[str, int]] = []  # (concept_name, new_value)
        for ns in namespaces:
            prefix = f"{ns}/"
            for cid, c_name, prev_noise in con.execute(
                "SELECT id, name, noise FROM entities "
                "WHERE partition_id=? AND kind='concept' AND protected=0 "
                "AND name LIKE ? || '%'",
                (self._partition_id, prefix),
            ).fetchall():
                seen += 1
                df = con.execute(
                    "SELECT COUNT(DISTINCT entity_id) FROM entity_links WHERE concept_id = ?",
                    (cid,),
                ).fetchone()[0]
                is_noise = df < min_df or df > max_df
                if is_noise:
                    if drop:
                        self.purge_entity(cid)
                        dropped += 1
                        continue
                    if not prev_noise:
                        con.execute(
                            "UPDATE entities SET noise=1 WHERE id=?", (cid,)
                        )
                        noise_changes.append((c_name, 1))
                    marked += 1
                else:
                    if prev_noise:
                        con.execute(
                            "UPDATE entities SET noise=0 WHERE id=?", (cid,)
                        )
                        noise_changes.append((c_name, 0))
                        unmarked += 1
        con.commit()
        for c_name, value in noise_changes:
            self._log_event("noise", kind="concept", name=c_name, value=value)
        return {
            "marked": marked,
            "unmarked": unmarked,
            "dropped": dropped,
            "kept": seen - marked - dropped,
            "total_seen": seen,
            "min_df": min_df,
            "max_df": max_df,
            "total_entities": total,
        }

    def is_noise(self, concept_id: int) -> bool:
        """Cheap lookup so the query engine can short-circuit noise rows."""
        row = self._connect().execute(
            "SELECT noise FROM entities WHERE id=?", (concept_id,)
        ).fetchone()
        return bool(row[0]) if row else False

    def noise_concept_ids(self) -> set[int]:
        """All concept ids currently marked as noise in the active partition.
        Used by the query engine to skip noise rows; scoping to the partition
        means partition A's noise list never shadows partition B's concepts."""
        return {
            r[0] for r in self._connect().execute(
                "SELECT id FROM entities "
                "WHERE partition_id=? AND kind='concept' AND noise=1",
                (self._partition_id,),
            )
        }

    # ---- sync log ----------------------------------------------------------

    def append_sync_log(self, line: str) -> None:
        log = self.root / "sync.log"
        try:
            with log.open("a") as f:
                f.write(line.rstrip("\n") + "\n")
        except OSError:
            pass

    def iter_concept_ids_for_linkage(self, linkage: str) -> Iterator[int]:
        """Yield distinct concept_ids that have at least one bit set in the
        given linkage. Reads from the entity_links shadow (indexed) — much
        faster than scanning the BitMap64 fragment for unique high-32 prefixes.
        """
        try:
            lid = self.get_linkage_id(linkage)
        except KeyError:
            return
        # JOIN entities so we only yield concept_ids whose concept entity lives
        # in the active partition. entity_links itself is partition-agnostic
        # (entity ids are global); the partition gate lives on entities.
        for r in self._connect().execute(
            "SELECT DISTINCT el.concept_id FROM entity_links el "
            "JOIN entities e ON e.id = el.concept_id "
            "WHERE el.linkage_id=? AND e.partition_id=?",
            (lid, self._partition_id),
        ):
            yield r[0]

    # ---- saved queries -----------------------------------------------------

    def save_query(self, name: str, body: str) -> None:
        con = self._connect()
        con.execute(
            "INSERT INTO saved_queries(partition_id, name, body, created_at) "
            "VALUES (?,?,?,?) "
            "ON CONFLICT(partition_id, name) DO UPDATE SET body=excluded.body",
            (self._partition_id, name, body, time.time()),
        )
        con.commit()

    def get_saved_query(self, name: str) -> str | None:
        row = self._connect().execute(
            "SELECT body FROM saved_queries WHERE partition_id=? AND name=?",
            (self._partition_id, name),
        ).fetchone()
        return row[0] if row else None

    def list_saved_queries(self) -> list[tuple[str, str]]:
        return [
            (r["name"], r["body"])
            for r in self._connect().execute(
                "SELECT name, body FROM saved_queries WHERE partition_id=? "
                "ORDER BY name",
                (self._partition_id,),
            )
        ]

    # ---- stats -------------------------------------------------------------

    def stats(self) -> dict:
        con = self._connect()
        out: dict = {}
        out["partition"] = self._partition_name
        out["entities"] = {
            r["kind"]: r["c"]
            for r in con.execute(
                "SELECT kind, COUNT(*) AS c FROM entities "
                "WHERE partition_id=? GROUP BY kind",
                (self._partition_id,),
            )
        }
        out["linkages"] = {}
        for lk in self.list_linkages():
            name = lk["name"]
            # Bits and concepts are counted via the active partition's entities
            # only; the bitmap fragment is already per-partition, so this also
            # matches what set-algebra queries would return.
            row = con.execute(
                "SELECT COUNT(DISTINCT el.concept_id) AS c, COUNT(*) AS b "
                "FROM entity_links el "
                "JOIN entities e ON e.id = el.entity_id "
                "WHERE el.linkage_id=? AND e.partition_id=?",
                (lk["id"], self._partition_id),
            ).fetchone()
            out["linkages"][name] = {
                "concepts": row["c"] or 0,
                "bits": row["b"] or 0,
            }
        return out

    # ---- log dump / rebuild -----------------------------------------------

    def dump_catalog_to_log(self) -> dict:
        """Snapshot the WHOLE catalog into facts.log as a fresh, replay-faithful
        event sequence. Overwrites any existing log (atomic tmp+rename).

        Faithful = a `rebuild_index_from_log()` of the result reproduces the
        catalog exactly, including:
        - every partition (each event carries `partition`; replay re-scopes),
        - memory bodies (`memory_content` events for kind=memory rows),
        - non-default linkage types (`linkage_type` events).

        This is both the bootstrap-onto-the-log primitive and the compaction
        primitive the daemon's facts.log rotation tick calls: a 2GB append log
        of churned duplicate events collapses to one minimal current-state
        snapshot."""
        con = self._connect()
        counts = {
            "entity": 0, "protect": 0, "noise": 0, "memory_content": 0,
            "link": 0, "evidence": 0, "track": 0, "linkage_type": 0,
        }
        default_linkages = {row[0] for row in DEFAULT_LINKAGES}
        # Stream into a temp file then atomic-rename so a crash mid-dump
        # doesn't leave a half-written log.
        tmp = self.log_path.with_suffix(".log.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            def emit(rec: dict) -> None:
                f.write(json.dumps(rec, sort_keys=True, ensure_ascii=False) + "\n")

            # Linkage types first (partition-independent) so link/evidence
            # replay can resolve them. Only the non-default ones — defaults are
            # recreated by init() during rebuild.
            for row in con.execute(
                "SELECT name, directed, description FROM linkage_types "
                "ORDER BY name"
            ):
                if row["name"] in default_linkages:
                    continue
                emit({
                    "ts": 0, "op": "linkage_type",
                    "name": row["name"],
                    "directed": int(row["directed"]) if row["directed"] is not None else 1,
                    "description": row["description"],
                })
                counts["linkage_type"] += 1

            # One pass per partition so every event is tagged with its
            # partition and replay lands rows in the right slot (pre-this-
            # change dumps flattened all partitions into the default one).
            partitions = [
                (r["id"], r["name"])
                for r in con.execute(
                    "SELECT id, name FROM partitions ORDER BY id"
                )
            ]
            for pid, pname in partitions:
                for row in con.execute(
                    "SELECT id, kind, name, path, tldr, meta, "
                    "       created_at, updated_at, protected, noise "
                    "FROM entities WHERE partition_id=? "
                    "ORDER BY created_at, id",
                    (pid,),
                ):
                    meta = json.loads(row["meta"]) if row["meta"] else None
                    emit({
                        "ts": row["created_at"],
                        "op": "entity", "partition": pname,
                        "kind": row["kind"], "name": row["name"],
                        "path": row["path"], "tldr": row["tldr"], "meta": meta,
                    })
                    counts["entity"] += 1
                    if row["protected"]:
                        emit({
                            "ts": row["updated_at"], "op": "protect",
                            "partition": pname,
                            "kind": row["kind"], "name": row["name"], "value": 1,
                        })
                        counts["protect"] += 1
                    if row["noise"]:
                        emit({
                            "ts": row["updated_at"], "op": "noise",
                            "partition": pname,
                            "kind": row["kind"], "name": row["name"], "value": 1,
                        })
                        counts["noise"] += 1

                # Memory bodies (sidecar) — emit AFTER the entity events so the
                # entity exists at replay time. LWW-keyed by name on replay.
                for row in con.execute(
                    "SELECT e.name AS name, mc.content, mc.mtype, mc.tags, "
                    "       mc.metadata, mc.updated_at AS ts "
                    "FROM memory_content mc "
                    "JOIN entities e ON e.id = mc.entity_id "
                    "WHERE e.partition_id=? ORDER BY mc.updated_at, e.name",
                    (pid,),
                ):
                    emit({
                        "ts": row["ts"], "op": "memory_content",
                        "partition": pname,
                        "kind": "memory", "name": row["name"],
                        "content": row["content"] or "",
                        "mtype": row["mtype"] or "observation",
                        "tags": json.loads(row["tags"]) if row["tags"] else None,
                        "metadata": json.loads(row["metadata"]) if row["metadata"] else None,
                    })
                    counts["memory_content"] += 1

                # Links + evidence are scoped to the partition by requiring BOTH
                # endpoints to live in it (entity_links has no partition column).
                # entity.updated_at is the ts baseline so links sort after their
                # entities on replay even if regenerated on a different clock.
                for row in con.execute(
                    """
                    SELECT lt.name AS linkage, c.name AS c_name,
                           e.kind AS e_kind, e.name AS e_name,
                           el.weight AS weight,
                           GREATEST(c.updated_at, e.updated_at) AS ts
                    FROM entity_links el
                    JOIN linkage_types lt ON lt.id = el.linkage_id
                    JOIN entities c ON c.id = el.concept_id
                    JOIN entities e ON e.id = el.entity_id
                    WHERE c.partition_id=? AND e.partition_id=?
                    ORDER BY ts, lt.name, c.name, e.name
                    """,
                    (pid, pid),
                ):
                    emit({
                        "ts": row["ts"], "op": "link", "partition": pname,
                        "linkage": row["linkage"], "c": row["c_name"],
                        "e_kind": row["e_kind"], "e": row["e_name"],
                        "weight": row["weight"],
                    })
                    counts["link"] += 1

                for row in con.execute(
                    """
                    SELECT lt.name AS linkage, c.name AS c_name,
                           e.kind AS e_kind, e.name AS e_name,
                           ev.file, ev.line, ev.span_end, ev.detail,
                           GREATEST(c.updated_at, e.updated_at) AS ts
                    FROM linkage_evidence ev
                    JOIN linkage_types lt ON lt.id = ev.linkage_id
                    JOIN entities c ON c.id = ev.concept_id
                    JOIN entities e ON e.id = ev.entity_id
                    WHERE c.partition_id=? AND e.partition_id=?
                    ORDER BY ts, lt.name, c.name, e.name, ev.file, ev.line
                    """,
                    (pid, pid),
                ):
                    emit({
                        "ts": row["ts"], "op": "evidence", "partition": pname,
                        "linkage": row["linkage"], "c": row["c_name"],
                        "e_kind": row["e_kind"], "e": row["e_name"],
                        "file": row["file"], "line": row["line"],
                        "span_end": row["span_end"], "detail": row["detail"],
                    })
                    counts["evidence"] += 1

                for row in con.execute(
                    "SELECT path, mtime, last_synced FROM tracked_files "
                    "WHERE partition_id=? ORDER BY last_synced, path",
                    (pid,),
                ):
                    emit({
                        "ts": row["last_synced"], "op": "track",
                        "partition": pname,
                        "path": row["path"], "mtime": row["mtime"],
                    })
                    counts["track"] += 1

        tmp.replace(self.log_path)
        return counts

    def apply_log_delta(
        self,
        start_offset: int,
        end_offset: int | None = None,
    ) -> dict:
        """Apply facts.log events from byte offset [start_offset..end_offset)
        to this Store in order, suppressing re-logging.

        Idempotent operations everywhere (upsert, link, INSERT OR IGNORE),
        so re-running with the same range produces the same state.

        Returns {"applied": N, "skipped_unresolved": M, "end_offset": pos}.
        `end_offset` defaults to the current end-of-log byte position so
        callers can capture a consistent snapshot range.

        Used by the daemon's two-file rotation refresh path: instead of
        copying the active slot to the inactive slot every cycle
        (O(file_size)), we apply just the new log events to the inactive
        slot (O(delta)). For typical 5-second refresh windows the delta
        is small (often zero); the file copy was wasting most of that
        budget on unchanged bytes."""
        log_path = self.log_path
        if not log_path.exists():
            return {"applied": 0, "skipped_unresolved": 0, "end_offset": 0}
        size = log_path.stat().st_size
        if end_offset is None:
            end_offset = size
        if start_offset >= end_offset:
            return {"applied": 0, "skipped_unresolved": 0,
                    "end_offset": end_offset}

        # The daemon always captures offsets at end-of-log-write boundaries
        # (log_path.stat().st_size after the writer's commit), so
        # start_offset is on a line boundary in the normal case. A naive
        # readline() at a clean boundary reads a full valid event and
        # consuming it would silently DROP the first event of the window.
        # No partial-line discard here; if external rotation lands a non-
        # boundary offset, the JSON parser will skip the malformed first
        # line and continue with the rest.
        applied = 0
        unresolved = 0
        self._replay_mode = True
        try:
            with log_path.open("r", encoding="utf-8") as fh:
                fh.seek(start_offset)
                while True:
                    pos = fh.tell()
                    if pos >= end_offset:
                        break
                    line = fh.readline()
                    if not line:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ev = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if self._apply_one_event(ev):
                        applied += 1
                    else:
                        unresolved += 1
        finally:
            self._replay_mode = False

        return {"applied": applied, "skipped_unresolved": unresolved,
                "end_offset": end_offset}

    def _apply_one_event(self, ev: dict) -> bool:
        """Apply a single facts.log event, re-scoping to the event's
        `partition` when it carries one (partition-faithful logs). Events
        without a partition apply to the active partition (legacy logs)."""
        part = ev.get("partition")
        if part and part != self._partition_name:
            with self.with_partition(part):
                return self._apply_event_body(ev)
        return self._apply_event_body(ev)

    def _apply_event_body(self, ev: dict) -> bool:
        """Apply a single facts.log event to self's active partition. Returns
        True if applied, False if the event couldn't be resolved (e.g. link
        referencing an entity that doesn't exist yet — rare; can happen if
        events arrive out of order from a concurrent writer)."""
        op = ev.get("op")
        try:
            if op == "entity":
                self.upsert_entity(
                    kind=ev["kind"], name=ev["name"],
                    path=ev.get("path"), tldr=ev.get("tldr"),
                    meta=ev.get("meta"),
                )
                return True
            if op == "protect":
                e = self.get_entity(ev["kind"], ev["name"])
                if e is None:
                    return False
                con = self._connect()
                con.execute(
                    "UPDATE entities SET protected=? WHERE id=?",
                    (int(ev.get("value", 1)), e.id),
                )
                self._maybe_commit(con)
                return True
            if op == "noise":
                e = self.get_entity(ev["kind"], ev["name"])
                if e is None:
                    return False
                con = self._connect()
                con.execute(
                    "UPDATE entities SET noise=? WHERE id=?",
                    (int(ev.get("value", 1)), e.id),
                )
                self._maybe_commit(con)
                return True
            if op == "tombstone":
                e = self.get_entity(ev["kind"], ev["name"])
                if e is None:
                    return False
                self.purge_entity(e.id)
                return True
            if op == "linkage_type":
                self.add_linkage_type(
                    ev["name"],
                    directed=bool(ev.get("directed", 1)),
                    description=ev.get("description") or None,
                )
                return True
            if op == "link":
                c = self.get_entity("concept", ev["c"])
                e = self.get_entity(ev["e_kind"], ev["e"])
                if c is None or e is None:
                    return False
                self.link(ev["linkage"], c.id, e.id, weight=ev.get("weight"))
                return True
            if op == "unlink":
                c = self.get_entity("concept", ev["c"])
                e = self.get_entity(ev["e_kind"], ev["e"])
                if c is None or e is None:
                    return False
                self.unlink(ev["linkage"], c.id, e.id)
                return True
            if op == "evidence":
                c = self.get_entity("concept", ev["c"])
                e = self.get_entity(ev["e_kind"], ev["e"])
                if c is None or e is None:
                    return False
                self.add_evidence(
                    ev["linkage"], c.id, e.id,
                    file=ev.get("file"), line=ev.get("line"),
                    span_end=ev.get("span_end"), detail=ev.get("detail"),
                )
                return True
            if op == "memory_content":
                # add_memory upserts the entity (idempotent — the prior
                # `entity` event already created it) and (re)writes the body.
                self.add_memory(
                    name=ev["name"],
                    content=ev.get("content", ""),
                    mtype=ev.get("mtype", "observation"),
                    tags=ev.get("tags"),
                    metadata=ev.get("metadata"),
                )
                return True
            if op == "track":
                mtime = ev.get("mtime")
                if mtime is not None:
                    self.mark_tracked(ev["path"], float(mtime))
                return True
            if op == "untrack":
                # purge_path is the live API but also tombstones the
                # entities; on replay those tombstones come as their own
                # events. Untrack-the-tracking-row alone is the right
                # operation here.
                con = self._connect()
                con.execute(
                    "DELETE FROM tracked_files WHERE partition_id=? AND path=?",
                    (self._partition_id, ev["path"]),
                )
                self._maybe_commit(con)
                return True
        except Exception:
            return False
        return False

    def rebuild_index_from_log(self) -> dict:
        """Wipe catalog.db + fragments and replay facts.log into a fresh
        catalog. Convergent: re-running yields the same final state.

        Replay rules:
        - ENTITY upsert: per-(kind, name), 'last non-null wins' on path/tldr/meta
        - TOMBSTONE: per-(kind, name), drops the entity if its ts > the
          latest entity event for that key
        - PROTECT/NOISE: LWW per-(kind, name)
        - LINK/UNLINK: OR-Set with tombstones — for each
          (linkage, c, e_kind, e), keep the event with the largest ts
        - TRACK/UNTRACK: LWW per-path
        - EVIDENCE: replayed unconditionally (idempotent in practice — the
          source-side ingester writes the same evidence each scan)
        """
        if not self.log_path.exists():
            raise FileNotFoundError(self.log_path)

        # Wipe derived state. Close current connection so the file unlink is
        # safe on platforms where SQLite holds open handles.
        self.close()
        if self.db_path.exists():
            self.db_path.unlink()
        for f in self.fragments_dir.rglob("*.rb64"):
            f.unlink()
        self._fragments.clear()
        self._dirty_fragments.clear()

        self.init()

        # Pass 1: load and sort all events by timestamp. For a small log this
        # is fine; for a huge log we'd stream and rely on file-order plus a
        # later compaction pass.
        events: list[dict] = []
        with self.log_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    # Tolerate stray lines (e.g. from a botched manual edit).
                    continue
        events.sort(key=lambda e: e.get("ts", 0))

        # Events lacking a `partition` field (legacy pre-partition-faithful
        # logs) default to the store's active partition — same as before this
        # change, so old logs still rebuild into one partition.
        dpart = self._partition_name

        # Pass 2: collapse to final state per key. Keys are partition-qualified
        # so the same (kind, name) in two partitions stays distinct.
        entity_state: dict[tuple[str, str, str], dict] = {}
        tombstone_ts: dict[tuple[str, str, str], float] = {}
        protect_lww: dict[tuple[str, str, str], tuple[float, int]] = {}
        noise_lww: dict[tuple[str, str, str], tuple[float, int]] = {}
        link_state: dict[tuple, tuple[float, str, float | None]] = {}
        track_state: dict[tuple[str, str], tuple[float, str, float | None]] = {}
        evidence_events: list[dict] = []
        # Memory bodies, LWW by (partition, entity name).
        memory_content_lww: dict[tuple[str, str], tuple[float, dict]] = {}
        # Linkage types referenced anywhere in the log (partition-independent).
        # Pre-2.0 logs don't carry `linkage_type` events, so we also derive the
        # set from link/unlink/evidence events and register the missing ones
        # before replay or `get_linkage_id` blows up mid-replay.
        linkage_types_seen: dict[str, dict] = {}

        for ev in events:
            op = ev.get("op")
            ts = ev.get("ts", 0)
            part = ev.get("partition") or dpart
            if op == "linkage_type":
                name = ev["name"]
                cur = linkage_types_seen.setdefault(name, {
                    "directed": 1, "description": "",
                })
                cur["directed"] = int(ev.get("directed", cur["directed"]))
                desc = ev.get("description")
                if desc:
                    cur["description"] = desc
                continue
            if op in ("link", "unlink", "evidence"):
                lname = ev.get("linkage")
                if lname:
                    linkage_types_seen.setdefault(
                        lname, {"directed": 1, "description": ""},
                    )
            if op == "entity":
                key = (part, ev["kind"], ev["name"])
                cur = entity_state.setdefault(key, {})
                for field in ("path", "tldr", "meta"):
                    val = ev.get(field)
                    if val is not None:
                        cur[field] = val
                cur["latest_ts"] = max(cur.get("latest_ts", 0), ts)
            elif op == "tombstone":
                key = (part, ev["kind"], ev["name"])
                if ts > tombstone_ts.get(key, -1):
                    tombstone_ts[key] = ts
            elif op == "protect":
                key = (part, ev["kind"], ev["name"])
                prev = protect_lww.get(key)
                if prev is None or ts > prev[0]:
                    protect_lww[key] = (ts, int(ev.get("value", 1)))
            elif op == "noise":
                key = (part, ev["kind"], ev["name"])
                prev = noise_lww.get(key)
                if prev is None or ts > prev[0]:
                    noise_lww[key] = (ts, int(ev.get("value", 1)))
            elif op in ("link", "unlink"):
                key = (part, ev["linkage"], ev["c"], ev["e_kind"], ev["e"])
                prev = link_state.get(key)
                if prev is None or ts > prev[0]:
                    link_state[key] = (ts, op, ev.get("weight"))
            elif op == "evidence":
                evidence_events.append(ev)
            elif op == "track":
                key = (part, ev["path"])
                prev = track_state.get(key)
                if prev is None or ts > prev[0]:
                    track_state[key] = (ts, "track", ev.get("mtime"))
            elif op == "untrack":
                key = (part, ev["path"])
                prev = track_state.get(key)
                if prev is None or ts > prev[0]:
                    track_state[key] = (ts, "untrack", None)
            elif op == "memory_content":
                key = (part, ev["name"])
                prev = memory_content_lww.get(key)
                if prev is None or ts > prev[0]:
                    memory_content_lww[key] = (ts, ev)

        # Pass 3: materialize, with logging suppressed to avoid the rebuild
        # appending duplicate events to the same log we're replaying. Work
        # one partition at a time under `with_partition` (auto-creates the
        # partition row) so rows land in the right slot.
        counts = {
            "entities": 0, "links": 0, "evidence": 0,
            "tracked": 0, "memory_content": 0,
        }
        self._replay_mode = True
        try:
            # Register every linkage type seen in the log before any
            # link/evidence replay touches them. Idempotent (INSERT OR IGNORE).
            for lname, props in linkage_types_seen.items():
                self.add_linkage_type(
                    lname, directed=bool(props.get("directed", 1)),
                    description=props.get("description") or None,
                )

            parts = sorted({k[0] for k in entity_state}
                           | {k[0] for k in track_state})
            for pname in parts:
                with self.with_partition(pname):
                    # (kind, name) -> id within THIS partition.
                    name_to_id: dict[tuple[str, str], int] = {}
                    for key, state in entity_state.items():
                        if key[0] != pname:
                            continue
                        _, kind, name = key
                        ts_dead = tombstone_ts.get(key)
                        if ts_dead is not None and ts_dead >= state.get("latest_ts", 0):
                            continue
                        eid = self.upsert_entity(
                            kind=kind, name=name,
                            path=state.get("path"),
                            tldr=state.get("tldr"),
                            meta=state.get("meta"),
                        )
                        name_to_id[(kind, name)] = eid
                    counts["entities"] += len(name_to_id)

                    con = self._connect()
                    for key, (_, val) in protect_lww.items():
                        if key[0] != pname:
                            continue
                        eid = name_to_id.get((key[1], key[2]))
                        if eid is not None:
                            con.execute(
                                "UPDATE entities SET protected=? WHERE id=?",
                                (val, eid),
                            )
                    for key, (_, val) in noise_lww.items():
                        if key[0] != pname:
                            continue
                        eid = name_to_id.get((key[1], key[2]))
                        if eid is not None:
                            con.execute(
                                "UPDATE entities SET noise=? WHERE id=?",
                                (val, eid),
                            )
                    con.commit()

                    for key, (_, op, weight) in link_state.items():
                        if key[0] != pname or op != "link":
                            continue
                        _, linkage, c_name, e_kind, e_name = key
                        cid = name_to_id.get(("concept", c_name))
                        eid = name_to_id.get((e_kind, e_name))
                        if cid is None or eid is None:
                            continue
                        self.link(linkage, cid, eid, weight=weight)
                        counts["links"] += 1

                    for ev in evidence_events:
                        if (ev.get("partition") or dpart) != pname:
                            continue
                        cid = name_to_id.get(("concept", ev["c"]))
                        eid = name_to_id.get((ev["e_kind"], ev["e"]))
                        if cid is None or eid is None:
                            continue
                        self.add_evidence(
                            ev["linkage"], cid, eid,
                            file=ev.get("file"), line=ev.get("line"),
                            span_end=ev.get("span_end"), detail=ev.get("detail"),
                        )
                        counts["evidence"] += 1

                    for key, (_, op, mtime) in track_state.items():
                        if key[0] != pname:
                            continue
                        if op == "track" and mtime is not None:
                            self.mark_tracked(key[1], mtime)
                            counts["tracked"] += 1

                    # Memory bodies: attach to surviving memory entities.
                    for key, (_, ev) in memory_content_lww.items():
                        if key[0] != pname:
                            continue
                        if ("memory", key[1]) not in name_to_id:
                            continue
                        self.add_memory(
                            name=key[1],
                            content=ev.get("content", ""),
                            mtype=ev.get("mtype", "observation"),
                            tags=ev.get("tags"),
                            metadata=ev.get("metadata"),
                        )
                        counts["memory_content"] += 1
        finally:
            self._replay_mode = False

        self.flush_fragments()
        return {
            "entities": counts["entities"],
            "links": counts["links"],
            "evidence": counts["evidence"],
            "tracked": counts["tracked"],
            "memory_content": counts["memory_content"],
            "events_replayed": len(events),
        }
