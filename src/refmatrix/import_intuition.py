"""Phase C1: import an intuition `.memory.db` into rmx.

Reads the SQLite catalog directly (no intuition runtime needed); maps:

    observations            -> entities(kind='memory') + memory_content sidecar
    observations.type       -> memory_content.mtype
    observations.tags/meta  -> memory_content.tags/metadata (JSON-preserved)
    observations.created_at -> entities.created_at  (ISO TEXT → REAL epoch)
    concepts                -> entities(kind='concept') via add_concept (auto-
                                canonicalizes + emits variant same_as edges)
    concept_aliases         -> additional concept entities linked same_as
                                to the canonical concept
    observation_concepts    -> link('mentions', cid, eid, weight=score)
    concept_relations       -> link(relation_type, target_cid, source_cid,
                                weight=weight)  (auto-registers relation_type
                                as a directed linkage)

Idempotent on `obs-{intuition_id}` memory names: re-running skips memories
that already exist (the upsert path leaves their content unchanged unless
forced).

Vector blobs: intuition stores FAISS sidecars (`*.faiss`) outside the
sqlite file, so there's nothing to copy here. The Lance dense path
re-embeds via `rmx embed --kinds memory` after import.
"""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from refmatrix.store import Store


# Memory-name prefix so re-imports collide on the same entity. Includes the
# source-db basename so two different intuition stores can import into the
# same partition without overlap. Format: `imp-{stem}-{orig_id}`.
def _memory_name(src_db: Path, obs_id: int) -> str:
    stem = src_db.stem.lstrip(".")
    return f"imp-{stem}-{obs_id}"


# intuition relation_type strings observed in the wild (vs- corpus): keep
# their original spelling, register as directed linkages on the fly.
# observation_concepts has no type column — every membership becomes a
# `mentions` edge, weight = score.
_MENTIONS = "mentions"


@dataclass
class ImportStats:
    memories_added: int = 0
    memories_skipped: int = 0
    concepts_added: int = 0
    aliases_linked: int = 0
    obs_concept_links: int = 0
    concept_relations: int = 0
    linkage_types_registered: int = 0
    errors: list[str] = None  # populated only when --strict=False

    def __post_init__(self):
        if self.errors is None:
            self.errors = []

    def as_dict(self) -> dict:
        return {
            "memories_added": self.memories_added,
            "memories_skipped": self.memories_skipped,
            "concepts_added": self.concepts_added,
            "aliases_linked": self.aliases_linked,
            "obs_concept_links": self.obs_concept_links,
            "concept_relations": self.concept_relations,
            "linkage_types_registered": self.linkage_types_registered,
            "errors": list(self.errors),
        }


def _parse_iso(ts: str) -> float:
    """intuition stores ISO 8601 with `+00:00`; sqlite3 returns it as TEXT.
    fromisoformat handles the format on 3.11+."""
    try:
        return datetime.fromisoformat(ts).timestamp()
    except Exception:
        return time.time()


def _patch_entity_created_at(s: "Store", eid: int, ts: float) -> None:
    """Override the entities.created_at set by upsert_entity so the
    reinforcement decay (Phase B5) anchors on the ORIGINAL observation
    date, not the import timestamp."""
    con = s._connect()
    con.execute(
        "UPDATE entities SET created_at=? WHERE id=?", (ts, eid),
    )


def import_intuition_db(
    store: "Store", src_db: Path, *, strict: bool = False,
) -> ImportStats:
    """Drive the import. `store` must already be `.init()`ed against the
    target partition. `strict=True` re-raises per-row failures; default
    collects them in `stats.errors` and keeps going so a single bad row
    doesn't abort an 866-row migration."""
    src_db = Path(src_db).resolve()
    if not src_db.exists():
        raise FileNotFoundError(f"intuition db not found: {src_db}")
    src = sqlite3.connect(src_db)
    src.row_factory = sqlite3.Row
    stats = ImportStats()

    # --- pass 1: concepts + aliases ----------------------------------------
    cid_map: dict[int, int] = {}  # intuition.concept.id -> rmx entity_id
    for r in src.execute(
        "SELECT id, name, aliases, description FROM concepts"
    ).fetchall():
        try:
            cid = store.add_concept(
                r["name"], description=r["description"] or None,
            )
            cid_map[r["id"]] = cid
            stats.concepts_added += 1
            # Aliases column is JSON list of alternate names. add_concept
            # already emits canonical/variant pairs; this pass adds the
            # user-supplied aliases that the canonicalizer wouldn't infer.
            aliases = json.loads(r["aliases"] or "[]")
            for alias in aliases:
                if not isinstance(alias, str) or not alias.strip():
                    continue
                alias_cid = store.add_concept(alias)
                if alias_cid != cid:
                    store.link("same_as", cid, alias_cid)
                    stats.aliases_linked += 1
        except Exception as e:
            stats.errors.append(f"concept id={r['id']}: {e}")
            if strict:
                raise

    # --- pass 2: observations -> memories ----------------------------------
    eid_map: dict[int, int] = {}  # intuition.observation.id -> rmx entity_id
    for r in src.execute(
        "SELECT id, content, type, tags, metadata, created_at "
        "FROM observations"
    ).fetchall():
        try:
            name = _memory_name(src_db, r["id"])
            existing = store.get_memory(name)
            if existing is not None:
                eid_map[r["id"]] = existing["id"]
                stats.memories_skipped += 1
                continue
            tags = json.loads(r["tags"] or "[]")
            metadata = json.loads(r["metadata"] or "{}")
            metadata["intuition_id"] = r["id"]
            metadata["intuition_source"] = str(src_db)
            eid = store.add_memory(
                name=name,
                content=r["content"],
                mtype=r["type"] or "observation",
                tags=tags if isinstance(tags, list) else [],
                metadata=metadata if isinstance(metadata, dict) else None,
            )
            ts = _parse_iso(r["created_at"])
            _patch_entity_created_at(store, eid, ts)
            eid_map[r["id"]] = eid
            stats.memories_added += 1
        except Exception as e:
            stats.errors.append(f"observation id={r['id']}: {e}")
            if strict:
                raise

    # --- pass 3: observation_concepts -> mentions edges -------------------
    for r in src.execute(
        "SELECT observation_id, concept_id, score FROM observation_concepts"
    ).fetchall():
        try:
            eid = eid_map.get(r["observation_id"])
            cid = cid_map.get(r["concept_id"])
            if eid is None or cid is None:
                continue
            store.link(_MENTIONS, cid, eid, weight=float(r["score"]))
            stats.obs_concept_links += 1
        except Exception as e:
            stats.errors.append(
                f"obs_concept obs={r['observation_id']} "
                f"cid={r['concept_id']}: {e}"
            )
            if strict:
                raise

    # --- pass 4: concept_relations ----------------------------------------
    seen_linkages: set[str] = set()
    for r in src.execute(
        "SELECT source_concept_id, target_concept_id, relation_type, weight "
        "FROM concept_relations"
    ).fetchall():
        try:
            src_cid = cid_map.get(r["source_concept_id"])
            tgt_cid = cid_map.get(r["target_concept_id"])
            if src_cid is None or tgt_cid is None:
                continue
            lk = r["relation_type"] or "related_to"
            if lk not in seen_linkages:
                store.add_linkage_type(lk, directed=True)
                seen_linkages.add(lk)
                stats.linkage_types_registered += 1
            store.link(lk, tgt_cid, src_cid, weight=float(r["weight"]))
            stats.concept_relations += 1
        except Exception as e:
            stats.errors.append(
                f"concept_relation src={r['source_concept_id']} "
                f"tgt={r['target_concept_id']}: {e}"
            )
            if strict:
                raise

    src.close()
    return stats


# --- archival --------------------------------------------------------------

# Intuition writes alongside the sqlite file. We sweep up the same family
# on archive so the running intuition process can't reopen any of them.
_ARCHIVE_SUFFIXES = (
    "",            # the .memory.db file itself
    "-wal",        # SQLite WAL
    "-shm",        # SQLite SHM
    ".concepts.faiss",
    ".obs.faiss",
    ".txlog.jsonl",
)


def archive_source(src_db: Path) -> list[Path]:
    """Move the intuition data family next to `src_db` into a sibling
    `.intuition-migrated/` directory. Returns the list of moved files
    (in their NEW locations). Missing siblings are silently skipped —
    intuition installs vary in which sidecars they keep.
    """
    src_db = Path(src_db).resolve()
    dest_dir = src_db.parent / ".intuition-migrated"
    dest_dir.mkdir(exist_ok=True)
    moved: list[Path] = []
    for suffix in _ARCHIVE_SUFFIXES:
        candidate = (
            src_db if suffix == "" else src_db.with_name(src_db.name + suffix)
        )
        if not candidate.exists():
            continue
        target = dest_dir / candidate.name
        # If a previous archive left a file there, append a numeric
        # suffix so we never silently overwrite a prior migration.
        if target.exists():
            n = 1
            while target.with_name(f"{candidate.name}.{n}").exists():
                n += 1
            target = target.with_name(f"{candidate.name}.{n}")
        candidate.rename(target)
        moved.append(target)
    return moved
