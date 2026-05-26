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

# Append-only fact log. Source-of-truth-in-progress: when RMX_LOG=1, every
# mutation also writes a JSON line to .refmatrix/facts.log. The log is keyed
# by names (not auto-IDs), so two branches that ingest disjoint material can
# be merged with a plain text-line merge and rebuilt via
# rebuild_index_from_log(). The catalog and fragments stay authoritative for
# reads; phase-2 will flip that.
LOG_FILENAME = "facts.log"


def _log_enabled() -> bool:
    return os.environ.get("RMX_LOG") in ("1", "true", "True")

# A single .refmatrix/ root can host multiple named partitions so several agents
# can write to a shared store without colliding on (kind, name). Each entity
# carries a partition_id; fragment files live under fragments/<partition>/.
# Existing single-partition catalogs are migrated on open to a default 'local'
# partition (id=1) — pre-partition data lands there with no behavior change.
DEFAULT_PARTITION = "local"

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
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    partition_id INTEGER NOT NULL DEFAULT 1 REFERENCES partitions(id),
    kind         TEXT NOT NULL CHECK (kind IN ('doc', 'code', 'concept')),
    path         TEXT,
    name         TEXT NOT NULL,
    tldr         TEXT,
    meta         TEXT,
    created_at   REAL NOT NULL,
    updated_at   REAL NOT NULL,
    protected    INTEGER NOT NULL DEFAULT 0,
    noise        INTEGER NOT NULL DEFAULT 0,
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
"""

DEFAULT_LINKAGES = [
    ("mentions",     1, None, "entity mentions concept"),
    ("defines",      1, None, "entity defines / declares concept"),
    ("calls",        1, None, "entity (function) calls concept (function)"),
    ("called_by",    1, "calls", "inverse of calls"),
    ("imports",      1, None, "entity imports module/concept"),
    ("is_a",         1, None, "concept is a subtype of concept"),
    ("related_to",   0, None, "undirected association"),
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
]


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
    ):
        from refmatrix.backend import select_backend
        self.root = Path(root).resolve()
        self._backend = select_backend(backend, root=self.root)
        # `db_path` historically pointed at catalog.db. Backend chooses the
        # filename now; legacy SQLite stores stay at catalog.db, DuckDB-native
        # stores use catalog.duckdb so the two can coexist during migration.
        self.db_path = self.root / self._backend.db_filename
        # bitmaps_dir is the legacy per-(linkage, concept) layout. Kept as an
        # attribute so the migration path can find and convert it.
        self.bitmaps_dir = self.root / "bitmaps"
        self.fragments_dir = self.root / "fragments"
        self.queries_dir = self.root / "queries"
        # Active partition. Falls back to RMX_PARTITION env, then 'local'. The
        # partition row is auto-created on first connect — passing a brand-new
        # name from CLI flag or env "just works" without an explicit register.
        self._partition_name: str = (
            partition
            or os.environ.get("RMX_PARTITION")
            or DEFAULT_PARTITION
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
        self.bitmaps_dir.mkdir(exist_ok=True)
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
                # Indexes are unconditional (and IF NOT EXISTS): both the
                # alter-table path above and the fresh-schema path leave us
                # with the columns present, so this is now safe.
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
                # partition index is safe to create unconditionally.
                con.execute(
                    "CREATE INDEX IF NOT EXISTS idx_entities_partition "
                    "ON entities(partition_id)"
                )
                con.commit()
            else:
                # DuckDB native catalog: schema is created up-front via the
                # native DDL (refmatrix.duckdb_catalog). All tables/indexes/
                # columns are present from the start, so the SQLite legacy
                # migration paths (partitions backfill, ALTER ADD COLUMN,
                # post-DDL CREATE INDEX) are not needed.
                self._backend.init_catalog(con)
                self._conn = con
            # Ensure the default + active partition rows exist and resolve the
            # active partition_id. Auto-creates the active partition the first
            # time a Store is opened with a new name (matches how a fresh
            # `rmx init` lands you in 'local' without a register step).
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
        (the default 'local' partition)."""
        assert self._conn is not None
        con = self._conn
        ent_cols = {r[1] for r in con.execute("PRAGMA table_info(entities)")}
        tf_cols = {r[1] for r in con.execute("PRAGMA table_info(tracked_files)")}
        if "partition_id" in ent_cols and "partition_id" in tf_cols:
            return
        # Insert default partition before any FK-bearing rebuild references it.
        con.execute(
            "INSERT OR IGNORE INTO partitions(id, name, kind, created_at) "
            "VALUES (1, ?, 'repo', ?)",
            (DEFAULT_PARTITION, time.time()),
        )
        # Must commit before PRAGMA foreign_keys = OFF — the pragma is
        # silently ignored while a transaction is open.
        con.commit()
        con.execute("PRAGMA foreign_keys = OFF")
        try:
            if "partition_id" not in ent_cols:
                con.executescript("""
                    DROP TABLE IF EXISTS entities_new;
                    CREATE TABLE entities_new (
                        id           INTEGER PRIMARY KEY AUTOINCREMENT,
                        partition_id INTEGER NOT NULL DEFAULT 1
                                       REFERENCES partitions(id),
                        kind         TEXT NOT NULL CHECK (kind IN ('doc','code','concept')),
                        path         TEXT,
                        name         TEXT NOT NULL,
                        tldr         TEXT,
                        meta         TEXT,
                        created_at   REAL NOT NULL,
                        updated_at   REAL NOT NULL,
                        protected    INTEGER NOT NULL DEFAULT 0,
                        noise        INTEGER NOT NULL DEFAULT 0,
                        UNIQUE(partition_id, kind, name)
                    );
                    INSERT INTO entities_new
                        (id, partition_id, kind, path, name, tldr, meta,
                         created_at, updated_at, protected, noise)
                    SELECT id, 1, kind, path, name, tldr, meta,
                           created_at, updated_at, protected, noise
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

    def _ensure_partition(self) -> None:
        """Resolve self._partition_id, auto-creating the partition row if the
        configured name is new. Always runs after _migrate_to_partitions_if_needed
        so the partitions table is guaranteed to exist."""
        assert self._conn is not None
        con = self._conn
        # Default partition is also handled by the migration path; insert here
        # too to cover fresh-schema callers (where the migration was a no-op).
        con.execute(
            "INSERT OR IGNORE INTO partitions(name, kind, created_at) "
            "VALUES (?, 'repo', ?)",
            (DEFAULT_PARTITION, time.time()),
        )
        if self._partition_name != DEFAULT_PARTITION:
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
        fragments/<DEFAULT_PARTITION>/ so they're visible to a Store opened on
        the default partition. Idempotent — once moved, subsequent calls find
        nothing to do."""
        if not self.fragments_dir.exists():
            return
        loose = [p for p in self.fragments_dir.glob("*.rb64") if p.is_file()]
        if not loose:
            return
        target_dir = self.fragments_dir / DEFAULT_PARTITION
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
        self.flush_fragments()
        if self._duck_view is not None:
            self._duck_view.close()
            self._duck_view = None
            self._read_conn = None
        if self._conn is not None:
            self._conn.close()
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
        if kind not in ("doc", "code", "concept"):
            raise ValueError(f"unknown kind: {kind}")
        now = time.time()
        meta_json = json.dumps(meta) if meta else None
        prot = 1 if protected else 0
        con = self._connect()
        pid = self._partition_id
        # On conflict: only ratchet protected upward — re-ingestion by an
        # auto-source must never clear a flag the user set manually.
        cur = con.execute(
            """
            INSERT INTO entities(partition_id, kind, name, path, tldr, meta,
                                 created_at, updated_at, protected)
            VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(partition_id, kind, name) DO UPDATE SET
                path = COALESCE(excluded.path, entities.path),
                tldr = COALESCE(excluded.tldr, entities.tldr),
                meta = COALESCE(excluded.meta, entities.meta),
                updated_at = excluded.updated_at,
                protected = GREATEST(entities.protected, excluded.protected)
            RETURNING id
            """,
            (pid, kind, name, path, tldr, meta_json, now, now, prot),
        )
        eid = cur.fetchone()[0]
        if kind == "concept":
            con.execute(
                "INSERT OR IGNORE INTO concepts(id, description) VALUES (?, ?)",
                (eid, (meta or {}).get("description")),
            )
        con.commit()
        self._log_event(
            "entity",
            kind=kind, name=name, path=path, tldr=tldr, meta=meta,
        )
        if protected:
            self._log_event("protect", kind=kind, name=name, value=1)
        return eid

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
        """Resolve a string ref to an entity. Tries 'kind:name', then 'name' across kinds."""
        if ":" in ref:
            kind, name = ref.split(":", 1)
            return self.get_entity(kind, name)
        for kind in ("concept", "code", "doc"):
            e = self.get_entity(kind, ref)
            if e:
                return e
        return None

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
        con = self._connect()
        cur = con.execute(
            "INSERT OR IGNORE INTO linkage_types(name, directed, description) VALUES (?,?,?)",
            (name, 1 if directed else 0, description),
        )
        con.commit()
        if cur.lastrowid:
            return cur.lastrowid
        row = con.execute("SELECT id FROM linkage_types WHERE name=?", (name,)).fetchone()
        return row[0]

    def get_linkage_id(self, name: str) -> int:
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

    # ---- bitmaps (Pilosa-style fragments) ---------------------------------

    def _fragment_path(self, linkage: str) -> Path:
        return self._partition_fragments_dir() / f"{linkage}.rb64"

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
        for linkage in list(self._dirty_fragments):
            frag = self._fragments.get(linkage)
            if frag is None:
                self._dirty_fragments.discard(linkage)
                continue
            p = self._fragment_path(linkage)
            if len(frag) == 0:
                if p.exists():
                    p.unlink()
            else:
                tmp = p.with_suffix(".rb64.tmp")
                tmp.write_bytes(frag.serialize())
                tmp.replace(p)
            self._dirty_fragments.discard(linkage)

    def _flush_fragments_duckdb(self) -> None:
        """DuckDB persistence path for flush_fragments: UPSERT (or DELETE on
        empty) the BLOB row for each dirty linkage in the active partition."""
        con = self._connect()
        pid = self._partition_id
        for linkage in list(self._dirty_fragments):
            frag = self._fragments.get(linkage)
            if frag is None:
                self._dirty_fragments.discard(linkage)
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
            self._dirty_fragments.discard(linkage)

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
                    con.commit()
        return _scope()

    def link(
        self,
        linkage: str,
        concept_id: int,
        entity_id: int,
        weight: float | None = None,
        protect: bool = False,
    ) -> bool:
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
        con.commit()
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
        con.commit()
        if present and cn and en:
            self._log_event(
                "unlink",
                linkage=linkage, c=cn[1], e_kind=en[0], e=en[1],
            )
        return present

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
        con.commit()

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
        con.commit()
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
        lid = self.get_linkage_id(linkage)
        con = self._connect()
        con.execute(
            "INSERT INTO linkage_evidence(entity_id, linkage_id, concept_id, "
            "file, line, span_end, detail) VALUES (?,?,?,?,?,?,?)",
            (entity_id, lid, concept_id, file, line, span_end, detail),
        )
        con.commit()
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

    def purge_entity(self, entity_id: int) -> int:
        """Remove an entity from every bitmap it's a member of, then drop the row."""
        con = self._connect()
        # Resolve names BEFORE deletion so log events can reference them.
        log_on = _log_enabled() and not self._replay_mode
        self_name = self._name_of(entity_id) if log_on else None
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
        """Snapshot the current catalog into facts.log as a fresh sequence
        of events. Overwrites any existing log. Run once to bootstrap an
        existing repo onto the log, then commit the result."""
        con = self._connect()
        counts = {
            "entity": 0, "protect": 0, "noise": 0,
            "link": 0, "evidence": 0, "track": 0,
        }
        # Stream into a temp file then atomic-rename so a crash mid-dump
        # doesn't leave a half-written log.
        tmp = self.log_path.with_suffix(".log.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            def emit(rec: dict) -> None:
                f.write(json.dumps(rec, sort_keys=True, ensure_ascii=False) + "\n")

            for row in con.execute(
                "SELECT id, kind, name, path, tldr, meta, "
                "       created_at, updated_at, protected, noise "
                "FROM entities ORDER BY created_at, id"
            ):
                meta = json.loads(row["meta"]) if row["meta"] else None
                emit({
                    "ts": row["created_at"],
                    "op": "entity",
                    "kind": row["kind"], "name": row["name"],
                    "path": row["path"], "tldr": row["tldr"], "meta": meta,
                })
                counts["entity"] += 1
                if row["protected"]:
                    emit({
                        "ts": row["updated_at"],
                        "op": "protect",
                        "kind": row["kind"], "name": row["name"], "value": 1,
                    })
                    counts["protect"] += 1
                if row["noise"]:
                    emit({
                        "ts": row["updated_at"],
                        "op": "noise",
                        "kind": row["kind"], "name": row["name"], "value": 1,
                    })
                    counts["noise"] += 1

            # Use the entity's updated_at as the link timestamp baseline so
            # links sort *after* their entities on replay even when
            # facts.log is regenerated on a different machine clock.
            for row in con.execute(
                """
                SELECT lt.name AS linkage,
                       c.name AS c_name,
                       e.kind AS e_kind, e.name AS e_name,
                       el.weight AS weight,
                       GREATEST(c.updated_at, e.updated_at) AS ts
                FROM entity_links el
                JOIN linkage_types lt ON lt.id = el.linkage_id
                JOIN entities c ON c.id = el.concept_id
                JOIN entities e ON e.id = el.entity_id
                ORDER BY ts, lt.name, c.name, e.name
                """
            ):
                emit({
                    "ts": row["ts"],
                    "op": "link",
                    "linkage": row["linkage"],
                    "c": row["c_name"],
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
                ORDER BY ts, lt.name, c.name, e.name, ev.file, ev.line
                """
            ):
                emit({
                    "ts": row["ts"],
                    "op": "evidence",
                    "linkage": row["linkage"],
                    "c": row["c_name"],
                    "e_kind": row["e_kind"], "e": row["e_name"],
                    "file": row["file"], "line": row["line"],
                    "span_end": row["span_end"], "detail": row["detail"],
                })
                counts["evidence"] += 1

            for row in con.execute(
                "SELECT path, mtime, last_synced FROM tracked_files "
                "ORDER BY last_synced, path"
            ):
                emit({
                    "ts": row["last_synced"],
                    "op": "track",
                    "path": row["path"], "mtime": row["mtime"],
                })
                counts["track"] += 1

        tmp.replace(self.log_path)
        return counts

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

        # Pass 2: collapse to final state per key.
        entity_state: dict[tuple[str, str], dict] = {}
        tombstone_ts: dict[tuple[str, str], float] = {}
        protect_lww: dict[tuple[str, str], tuple[float, int]] = {}
        noise_lww: dict[tuple[str, str], tuple[float, int]] = {}
        link_state: dict[tuple, tuple[float, str, float | None]] = {}
        track_state: dict[str, tuple[float, str, float | None]] = {}
        evidence_events: list[dict] = []

        for ev in events:
            op = ev.get("op")
            ts = ev.get("ts", 0)
            if op == "entity":
                key = (ev["kind"], ev["name"])
                cur = entity_state.setdefault(key, {})
                for field in ("path", "tldr", "meta"):
                    val = ev.get(field)
                    if val is not None:
                        cur[field] = val
                cur["latest_ts"] = max(cur.get("latest_ts", 0), ts)
            elif op == "tombstone":
                key = (ev["kind"], ev["name"])
                if ts > tombstone_ts.get(key, -1):
                    tombstone_ts[key] = ts
            elif op == "protect":
                key = (ev["kind"], ev["name"])
                prev = protect_lww.get(key)
                if prev is None or ts > prev[0]:
                    protect_lww[key] = (ts, int(ev.get("value", 1)))
            elif op == "noise":
                key = (ev["kind"], ev["name"])
                prev = noise_lww.get(key)
                if prev is None or ts > prev[0]:
                    noise_lww[key] = (ts, int(ev.get("value", 1)))
            elif op in ("link", "unlink"):
                key = (
                    ev["linkage"], ev["c"],
                    ev["e_kind"], ev["e"],
                )
                prev = link_state.get(key)
                if prev is None or ts > prev[0]:
                    link_state[key] = (ts, op, ev.get("weight"))
            elif op == "evidence":
                evidence_events.append(ev)
            elif op == "track":
                key = ev["path"]
                prev = track_state.get(key)
                if prev is None or ts > prev[0]:
                    track_state[key] = (ts, "track", ev.get("mtime"))
            elif op == "untrack":
                key = ev["path"]
                prev = track_state.get(key)
                if prev is None or ts > prev[0]:
                    track_state[key] = (ts, "untrack", None)

        # Pass 3: materialize, with logging suppressed to avoid the rebuild
        # appending duplicate events to the same log we're replaying.
        self._replay_mode = True
        try:
            name_to_id: dict[tuple[str, str], int] = {}
            for key, state in entity_state.items():
                kind, name = key
                ts_dead = tombstone_ts.get(key)
                if ts_dead is not None and ts_dead >= state.get("latest_ts", 0):
                    continue
                eid = self.upsert_entity(
                    kind=kind, name=name,
                    path=state.get("path"),
                    tldr=state.get("tldr"),
                    meta=state.get("meta"),
                )
                name_to_id[key] = eid

            con = self._connect()
            for key, (_, val) in protect_lww.items():
                eid = name_to_id.get(key)
                if eid is not None:
                    con.execute(
                        "UPDATE entities SET protected=? WHERE id=?", (val, eid)
                    )
            for key, (_, val) in noise_lww.items():
                eid = name_to_id.get(key)
                if eid is not None:
                    con.execute(
                        "UPDATE entities SET noise=? WHERE id=?", (val, eid)
                    )
            con.commit()

            links_added = 0
            for (linkage, c_name, e_kind, e_name), (_, op, weight) in link_state.items():
                if op != "link":
                    continue
                cid = name_to_id.get(("concept", c_name))
                eid = name_to_id.get((e_kind, e_name))
                if cid is None or eid is None:
                    continue
                self.link(linkage, cid, eid, weight=weight)
                links_added += 1

            evidence_added = 0
            for ev in evidence_events:
                cid = name_to_id.get(("concept", ev["c"]))
                eid = name_to_id.get((ev["e_kind"], ev["e"]))
                if cid is None or eid is None:
                    continue
                self.add_evidence(
                    ev["linkage"], cid, eid,
                    file=ev.get("file"), line=ev.get("line"),
                    span_end=ev.get("span_end"), detail=ev.get("detail"),
                )
                evidence_added += 1

            tracks_added = 0
            for path, (_, op, mtime) in track_state.items():
                if op == "track" and mtime is not None:
                    self.mark_tracked(path, mtime)
                    tracks_added += 1
        finally:
            self._replay_mode = False

        self.flush_fragments()
        return {
            "entities": len(name_to_id),
            "links": links_added,
            "evidence": evidence_added,
            "tracked": tracks_added,
            "events_replayed": len(events),
        }
