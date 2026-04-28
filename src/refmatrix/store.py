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
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

from pyroaring import BitMap, BitMap64

# Packing: concept_id occupies the high 32 bits, entity_id the low 32. Both
# come from the same `entities.id` autoincrement so they share a counter; 32
# bits each gives ~4B headroom on each side, well past anything realistic.
_CONCEPT_SHIFT = 32
_ENTITY_MASK = (1 << 32) - 1

CATALOG_DDL = """
CREATE TABLE IF NOT EXISTS entities (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT NOT NULL CHECK (kind IN ('doc', 'code', 'concept')),
    path        TEXT,
    name        TEXT NOT NULL,
    tldr        TEXT,
    meta        TEXT,
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL,
    protected   INTEGER NOT NULL DEFAULT 0,
    noise       INTEGER NOT NULL DEFAULT 0,
    UNIQUE(kind, name)
);
CREATE INDEX IF NOT EXISTS idx_entities_kind ON entities(kind);
CREATE INDEX IF NOT EXISTS idx_entities_path ON entities(path);
-- protected/noise indexes are created in _connect() after the conditional
-- ALTER TABLE; CREATE INDEX here would fail on legacy schemas where the
-- columns don't yet exist (executescript runs all statements top-to-bottom).

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
    name TEXT PRIMARY KEY,
    body TEXT NOT NULL,
    created_at REAL NOT NULL
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
    path        TEXT PRIMARY KEY,
    mtime       REAL NOT NULL,
    last_synced REAL NOT NULL
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
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.db_path = self.root / "catalog.db"
        # bitmaps_dir is the legacy per-(linkage, concept) layout. Kept as an
        # attribute so the migration path can find and convert it.
        self.bitmaps_dir = self.root / "bitmaps"
        self.fragments_dir = self.root / "fragments"
        self.queries_dir = self.root / "queries"
        self._conn: sqlite3.Connection | None = None
        # Lazy-loaded fragment cache: linkage_name -> BitMap64. Populated on
        # first read/write of any concept under that linkage; flushed back to
        # disk via flush_fragments() (called from close()).
        self._fragments: dict[str, BitMap64] = {}
        self._dirty_fragments: set[str] = set()

    # ---- lifecycle ---------------------------------------------------------

    def init(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.bitmaps_dir.mkdir(exist_ok=True)
        self.fragments_dir.mkdir(exist_ok=True)
        self.queries_dir.mkdir(exist_ok=True)
        with self._connect() as con:
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

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            # check_same_thread=False so the watcher daemon (debounce thread)
            # can flush via sync_files. WAL + our single-writer pattern keeps
            # this safe.
            con = sqlite3.connect(self.db_path, check_same_thread=False)
            con.execute("PRAGMA foreign_keys = ON")
            con.execute("PRAGMA journal_mode = WAL")
            con.row_factory = sqlite3.Row
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
        # One-shot migration: collapse legacy per-(linkage, concept) .rb files
        # into per-linkage BitMap64 fragments. Runs at most once per catalog.
        self._migrate_legacy_bitmaps_if_needed()
        return self._conn

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
        self.fragments_dir.mkdir(parents=True, exist_ok=True)
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

    def close(self) -> None:
        # Persist any in-memory fragment edits before tearing down the
        # connection. Safe to call on a never-modified Store (no-op).
        self.flush_fragments()
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
        # On conflict: only ratchet protected upward — re-ingestion by an
        # auto-source must never clear a flag the user set manually.
        cur = con.execute(
            """
            INSERT INTO entities(kind, name, path, tldr, meta, created_at, updated_at, protected)
            VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(kind, name) DO UPDATE SET
                path = COALESCE(excluded.path, entities.path),
                tldr = COALESCE(excluded.tldr, entities.tldr),
                meta = COALESCE(excluded.meta, entities.meta),
                updated_at = excluded.updated_at,
                protected = MAX(entities.protected, excluded.protected)
            RETURNING id
            """,
            (kind, name, path, tldr, meta_json, now, now, prot),
        )
        eid = cur.fetchone()[0]
        if kind == "concept":
            con.execute(
                "INSERT OR IGNORE INTO concepts(id, description) VALUES (?, ?)",
                (eid, (meta or {}).get("description")),
            )
        con.commit()
        return eid

    def add_concept(
        self,
        name: str,
        description: str | None = None,
        protected: bool = False,
    ) -> int:
        return self.upsert_entity(
            kind="concept",
            name=name,
            meta={"description": description} if description else None,
            protected=protected,
        )

    def get_entity(self, kind: str, name: str) -> Entity | None:
        row = self._connect().execute(
            "SELECT * FROM entities WHERE kind=? AND name=?", (kind, name)
        ).fetchone()
        return self._row_to_entity(row) if row else None

    def get_entity_by_id(self, eid: int) -> Entity | None:
        row = self._connect().execute(
            "SELECT * FROM entities WHERE id=?", (eid,)
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
        sql = "SELECT * FROM entities"
        params: tuple = ()
        if kind:
            sql += " WHERE kind=?"
            params = (kind,)
        for row in self._connect().execute(sql, params):
            yield self._row_to_entity(row)

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
        row = self._connect().execute(
            "SELECT id FROM linkage_types WHERE name=?", (name,)
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown linkage type: {name}. Use add-linkage-type first.")
        return row[0]

    def list_linkages(self) -> list[dict]:
        rows = self._connect().execute(
            "SELECT id, name, directed, description FROM linkage_types ORDER BY name"
        ).fetchall()
        return [dict(r) for r in rows]

    # ---- bitmaps (Pilosa-style fragments) ---------------------------------

    def _fragment_path(self, linkage: str) -> Path:
        return self.fragments_dir / f"{linkage}.rb64"

    def _load_fragment(self, linkage: str) -> BitMap64:
        """Return the in-memory BitMap64 for a linkage, lazy-loading from disk
        on first access. Mutating the returned object is fine — call
        flush_fragments() (or close()) to persist."""
        if linkage in self._fragments:
            return self._fragments[linkage]
        self.fragments_dir.mkdir(parents=True, exist_ok=True)
        p = self._fragment_path(linkage)
        if p.exists():
            frag = BitMap64.deserialize(p.read_bytes())
        else:
            frag = BitMap64()
        self._fragments[linkage] = frag
        return frag

    def flush_fragments(self) -> None:
        """Write any dirty linkage fragments back to disk. Idempotent."""
        if not self._dirty_fragments:
            return
        self.fragments_dir.mkdir(parents=True, exist_ok=True)
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

    def link(
        self,
        linkage: str,
        concept_id: int,
        entity_id: int,
        weight: float | None = None,
        protect: bool = False,
    ) -> bool:
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
        return not already

    def unlink(self, linkage: str, concept_id: int, entity_id: int) -> bool:
        lid = self.get_linkage_id(linkage)
        frag = self._load_fragment(linkage)
        bit = self._pack(concept_id, entity_id)
        present = bit in frag
        if present:
            frag.discard(bit)
            self._dirty_fragments.add(linkage)
        con = self._connect()
        con.execute(
            "DELETE FROM entity_links WHERE entity_id=? AND linkage_id=? AND concept_id=?",
            (entity_id, lid, concept_id),
        )
        con.commit()
        return present

    def link_many(self, linkage: str, concept_id: int, entity_ids: Iterable[int]) -> int:
        lid = self.get_linkage_id(linkage)
        frag = self._load_fragment(linkage)
        ids = list(entity_ids)
        before = len(frag)
        for eid in ids:
            frag.add(self._pack(concept_id, eid))
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
        return [
            (r[0], r[1])
            for r in self._connect().execute(
                "SELECT entity_id, weight FROM entity_links "
                "WHERE linkage_id=? AND concept_id=? AND weight IS NOT NULL "
                "ORDER BY weight DESC, entity_id ASC LIMIT ?",
                (lid, concept_id, k),
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
                "SELECT * FROM entities WHERE kind='concept' AND name LIKE ? || '%'",
                (prefix,),
            )
        ]

    # ---- purge / track files -----------------------------------------------

    def purge_entity(self, entity_id: int) -> int:
        """Remove an entity from every bitmap it's a member of, then drop the row."""
        con = self._connect()
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
        con.execute("DELETE FROM tracked_files WHERE path = "
                    "(SELECT path FROM entities WHERE id=?)", (entity_id,))
        con.commit()
        return n

    def purge_path(self, abs_path: str) -> int:
        """Remove every entity (file + per-function) anchored at abs_path.
        Returns the number of *entities* removed."""
        con = self._connect()
        ids = [
            r[0] for r in con.execute(
                "SELECT id FROM entities WHERE path=?", (abs_path,)
            )
        ]
        for eid in ids:
            self.purge_entity(eid)
        con.execute("DELETE FROM tracked_files WHERE path=?", (abs_path,))
        con.commit()
        return len(ids)

    def mark_tracked(self, abs_path: str, mtime: float) -> None:
        now = time.time()
        con = self._connect()
        con.execute(
            "INSERT INTO tracked_files(path, mtime, last_synced) VALUES (?,?,?) "
            "ON CONFLICT(path) DO UPDATE SET mtime=excluded.mtime, last_synced=excluded.last_synced",
            (abs_path, mtime, now),
        )
        con.commit()

    def list_tracked(self) -> list[tuple[str, float]]:
        return [
            (r[0], r[1])
            for r in self._connect().execute(
                "SELECT path, mtime FROM tracked_files"
            )
        ]

    def stale_files(self) -> list[dict]:
        """Return tracked files where on-disk mtime is newer than last_synced.
        These are files the index doesn't yet reflect."""
        out: list[dict] = []
        from os import stat as _stat
        for path, mtime, last_synced in self._connect().execute(
            "SELECT path, mtime, last_synced FROM tracked_files"
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
        empty_concepts = [
            r[0] for r in con.execute(
                """
                SELECT e.id FROM entities e
                LEFT JOIN entity_links el ON el.concept_id = e.id
                WHERE e.kind = 'concept'
                  AND el.entity_id IS NULL
                  AND e.protected = 0
                """
            )
        ]
        for cid in empty_concepts:
            self.purge_entity(cid)

        # 2. tracked_files for paths that no longer exist
        gone = [
            r[0] for r in con.execute("SELECT path FROM tracked_files")
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
            "SELECT COUNT(*) FROM entities WHERE kind != 'concept'"
        ).fetchone()[0]
        if total == 0:
            return {"marked": 0, "unmarked": 0, "kept": 0, "total_seen": 0,
                    "dropped": 0}

        max_df = max(min_df, int(total * max_df_ratio))
        seen = marked = unmarked = dropped = 0
        for ns in namespaces:
            prefix = f"{ns}/"
            for cid, _name, prev_noise in con.execute(
                "SELECT id, name, noise FROM entities "
                "WHERE kind='concept' AND protected=0 AND name LIKE ? || '%'",
                (prefix,),
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
                    marked += 1
                else:
                    if prev_noise:
                        con.execute(
                            "UPDATE entities SET noise=0 WHERE id=?", (cid,)
                        )
                        unmarked += 1
        con.commit()
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
        """All concept ids currently marked as noise."""
        return {
            r[0] for r in self._connect().execute(
                "SELECT id FROM entities WHERE kind='concept' AND noise=1"
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
        for r in self._connect().execute(
            "SELECT DISTINCT concept_id FROM entity_links WHERE linkage_id=?",
            (lid,),
        ):
            yield r[0]

    # ---- saved queries -----------------------------------------------------

    def save_query(self, name: str, body: str) -> None:
        con = self._connect()
        con.execute(
            "INSERT INTO saved_queries(name, body, created_at) VALUES (?,?,?) "
            "ON CONFLICT(name) DO UPDATE SET body=excluded.body",
            (name, body, time.time()),
        )
        con.commit()

    def get_saved_query(self, name: str) -> str | None:
        row = self._connect().execute(
            "SELECT body FROM saved_queries WHERE name=?", (name,)
        ).fetchone()
        return row[0] if row else None

    def list_saved_queries(self) -> list[tuple[str, str]]:
        return [
            (r["name"], r["body"])
            for r in self._connect().execute(
                "SELECT name, body FROM saved_queries ORDER BY name"
            )
        ]

    # ---- stats -------------------------------------------------------------

    def stats(self) -> dict:
        con = self._connect()
        out: dict = {}
        out["entities"] = {
            r["kind"]: r["c"]
            for r in con.execute("SELECT kind, COUNT(*) AS c FROM entities GROUP BY kind")
        }
        out["linkages"] = {}
        for lk in self.list_linkages():
            name = lk["name"]
            row = con.execute(
                "SELECT COUNT(DISTINCT concept_id) AS c, COUNT(*) AS b "
                "FROM entity_links WHERE linkage_id=?",
                (lk["id"],),
            ).fetchone()
            out["linkages"][name] = {
                "concepts": row["c"] or 0,
                "bits": row["b"] or 0,
            }
        return out
