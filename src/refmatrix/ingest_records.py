"""Record protocol for parallel-parse ingest.

The single-threaded ingesters in ingest.py interleave file parsing
(regex / AST / line-walk) with Store mutations. That made the ingest
process CPU-bound on one core: parsing must hold the store lock
because the parser writes as it walks.

This module provides a recording surface that quacks like Store but
buffers every mutation into a plain-data IngestRecord. Workers build
records in parallel (no shared mutable state, no store lock); a
single applier thread later replays the record against the real
Store under the active transaction. Cross-record references that
need the real catalog (path resolution, ADR lookups) are encoded as
symbolic @-refs that the applier resolves at apply time.

Symbolic ref grammar:

  @doc                       this record's primary entity
  @sub:<kind>/<qname>        sub-entity created earlier in this record
  @concept:<name>            bare concept created earlier in this record
  @nsconcept:<ns>/<name>     namespaced concept created earlier
  @adr:<NNNN>                ADR by 4-digit number (resolved via map)
  @ref:<key>                 path-resolved ref (resolves at apply time)

The record is intentionally JSON-friendly so it can pickle through a
ProcessPoolExecutor in the future. ThreadPoolExecutor is enough today
since regex + ast both release the GIL.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class IngestRecord:
    """All store mutations captured from parsing one file, plus the
    metadata an applier needs to materialize them."""
    rel: str
    file_path: str
    mtime: float | None = None
    doc_kind: str = "doc"
    doc_meta: dict | None = None
    # Order matters within each list — apply phase preserves it.
    sub_entities: list[dict] = field(default_factory=list)
    concepts: list[dict] = field(default_factory=list)
    ns_concepts: list[dict] = field(default_factory=list)
    ref_resolves: list[dict] = field(default_factory=list)
    ops: list[dict] = field(default_factory=list)


class RecordingStore:
    """Store-shaped recorder that buffers mutations into an IngestRecord
    instead of touching DuckDB. Worker threads use this; the real Store
    is reserved for the applier thread.

    Methods mirror the Store mutation surface used by the ingest
    helpers. All `_id` return values are symbolic strings (@doc, @sub,
    @concept, ...) rather than integers; helpers don't care because they
    treat the value as an opaque handle to thread through `link()` and
    `add_evidence()` calls."""

    def __init__(
        self,
        rel: str,
        file_path: str,
        mtime: float | None = None,
        doc_kind: str = "doc",
        doc_meta: dict | None = None,
    ):
        self.record = IngestRecord(
            rel=rel, file_path=file_path, mtime=mtime,
            doc_kind=doc_kind, doc_meta=doc_meta,
        )
        self._concept_set: set[str] = set()
        self._ns_set: set[tuple[str, str]] = set()
        self._sub_set: set[tuple[str, str]] = set()
        self._ref_counter = 0

    # ---- entity / concept registration ----------------------------------

    def upsert_entity(
        self,
        kind: str,
        name: str,
        path: str | None = None,
        tldr: str | None = None,
        meta: dict | None = None,
        protected: bool = False,
    ) -> str:
        if name == self.record.rel and kind == self.record.doc_kind:
            # doc-level entity already in the record header
            if meta is not None and self.record.doc_meta is None:
                self.record.doc_meta = meta
            return "@doc"
        key = (kind, name)
        if key not in self._sub_set:
            self.record.sub_entities.append({
                "kind": kind, "qname": name, "meta": meta,
            })
            self._sub_set.add(key)
        return f"@sub:{kind}/{name}"

    def mark_tracked(self, path: str, mtime: float) -> None:
        # mtime is captured at record creation; the applier mark_tracks
        # using record.mtime. Re-calls are no-ops.
        if self.record.mtime is None:
            self.record.mtime = mtime

    def add_concept(
        self, name: str, description: str | None = None, protected: bool = False,
    ) -> str:
        if name not in self._concept_set:
            self.record.concepts.append({"name": name, "description": description})
            self._concept_set.add(name)
        return f"@concept:{name}"

    def add_namespaced_concept(
        self, ns: str, name: str, description: str | None = None,
        protected: bool = False,
    ) -> str:
        key = (ns, name)
        if key not in self._ns_set:
            self.record.ns_concepts.append({
                "ns": ns, "name": name, "description": description,
            })
            self._ns_set.add(key)
        return f"@nsconcept:{ns}/{name}"

    # ---- linkage ops ----------------------------------------------------

    def link(
        self, linkage: str, c: str, e: str,
        weight: float | None = None, protect: bool = False,
    ) -> bool:
        self.record.ops.append({
            "op": "link", "linkage": linkage,
            "src": c, "dst": e, "weight": weight,
        })
        return True

    def weighted_link(
        self, linkage: str, c: str, e: str, weight: float,
    ) -> bool:
        self.record.ops.append({
            "op": "weighted_link", "linkage": linkage,
            "src": c, "dst": e, "weight": weight,
        })
        return True

    def add_evidence(
        self, linkage: str, c: str, e: str, *,
        file: str | None = None, line: int | None = None,
        span_end: int | None = None, detail: str | None = None,
    ) -> None:
        self.record.ops.append({
            "op": "evidence", "linkage": linkage,
            "src": c, "dst": e,
            "file": file, "line": line, "detail": detail,
        })

    # ---- deferred path resolution ---------------------------------------

    def register_ref_resolve(
        self, candidates: list[tuple[str, str]],
    ) -> str:
        """Record a list of (kind, name) lookup candidates. The applier
        tries each in order and binds the first hit to the returned
        @ref:<key> symbol. Use when a worker can't resolve a path until
        the real Store is available."""
        self._ref_counter += 1
        key = f"r{self._ref_counter}"
        self.record.ref_resolves.append({"key": key, "candidates": candidates})
        return f"@ref:{key}"

    # ---- Store-compat stubs used by helpers but harmless here -----------

    def get_entity(self, kind: str, name: str):
        # Helpers that try this should call register_ref_resolve instead.
        # Returning None preserves any "skip when missing" code paths.
        return None


def apply_record(
    s,
    record: IngestRecord,
    *,
    adr_num_to_eid: dict[str, int] | None = None,
) -> int:
    """Materialize a record against the real Store. Single-threaded,
    runs under the caller's transaction. Returns the number of ops
    applied (entities created + links + evidence rows)."""
    adr_num_to_eid = adr_num_to_eid or {}
    n = 0

    # 1. doc-level entity
    doc_eid = s.upsert_entity(
        kind=record.doc_kind, name=record.rel,
        path=record.file_path, meta=record.doc_meta,
    )
    n += 1
    if record.mtime is not None:
        try:
            s.mark_tracked(record.file_path, record.mtime)
        except OSError:
            pass

    # 2. sub entities (need real ids before link replay)
    sub_ids: dict[tuple[str, str], int] = {}
    for sub in record.sub_entities:
        sub_ids[(sub["kind"], sub["qname"])] = s.upsert_entity(
            kind=sub["kind"], name=sub["qname"],
            path=record.file_path, meta=sub.get("meta"),
        )
        n += 1

    # 3. concepts
    concept_ids: dict[str, int] = {}
    for c in record.concepts:
        concept_ids[c["name"]] = s.add_concept(
            c["name"], description=c.get("description"),
        )

    # 4. namespaced concepts
    ns_concept_ids: dict[tuple[str, str], int] = {}
    for c in record.ns_concepts:
        ns_concept_ids[(c["ns"], c["name"])] = s.add_namespaced_concept(
            c["ns"], c["name"], description=c.get("description"),
        )

    # 5. path-based ref resolutions — real store available here
    ref_ids: dict[str, int | None] = {}
    for r in record.ref_resolves:
        found: int | None = None
        for cand in r["candidates"]:
            ent = s.get_entity(cand[0], cand[1])
            if ent is not None:
                found = ent.id
                break
        ref_ids[r["key"]] = found

    def _resolve(ref: str) -> int | None:
        if ref == "@doc":
            return doc_eid
        if ref.startswith("@sub:"):
            kind, _, qname = ref[len("@sub:"):].partition("/")
            return sub_ids.get((kind, qname))
        if ref.startswith("@concept:"):
            return concept_ids.get(ref[len("@concept:"):])
        if ref.startswith("@nsconcept:"):
            ns, _, name = ref[len("@nsconcept:"):].partition("/")
            return ns_concept_ids.get((ns, name))
        if ref.startswith("@adr:"):
            return adr_num_to_eid.get(ref[len("@adr:"):])
        if ref.startswith("@ref:"):
            return ref_ids.get(ref[len("@ref:"):])
        return None

    # 6. linkage ops, batched
    with s.deferred_links():
        for op in record.ops:
            src = _resolve(op["src"])
            dst = _resolve(op["dst"])
            if src is None or dst is None:
                continue
            kind = op["op"]
            if kind == "link":
                s.link(op["linkage"], src, dst, weight=op.get("weight"))
            elif kind == "weighted_link":
                s.weighted_link(
                    op["linkage"], src, dst, weight=op["weight"],
                )
            elif kind == "evidence":
                s.add_evidence(
                    op["linkage"], src, dst,
                    file=op.get("file"), line=op.get("line"),
                    detail=op.get("detail"),
                )
            n += 1
    return n
