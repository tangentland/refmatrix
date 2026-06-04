"""
Token-budgeted context bundle for a symbol.

Resolves a concept (or an entity), walks its linkages, and returns the
neighbor entities grouped by linkage with their tldr blobs. Caps both by
entity count and by an estimated token budget so the output stays paste-
able into an LLM prompt.

The estimator is a rough chars/4 heuristic. We don't try to be precise —
the goal is "stop bloating the context" not "exact accounting."
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from refmatrix.store import Entity, Store


# Order linkages so output reads like a natural definition: what *is* this
# thing, who points at it, what does it point at, where is it talked about.
DEFAULT_LINKAGE_ORDER = [
    "defines", "implements",
    "called_by", "imports",
    "calls", "is_a", "related_to",
    "mentions",
]

LINKAGE_LABELS = {
    "defines": "DEFINED BY",
    "implements": "IMPLEMENTED BY",
    "called_by": "CALLED BY",
    "imports": "IMPORTED BY",
    "calls": "CALLS",
    "mentions": "MENTIONED IN",
    "is_a": "IS A",
    "related_to": "RELATED TO",
}


def estimate_tokens(text: str) -> int:
    """~chars/4. Good enough to bound output, not for billing."""
    return max(1, len(text) // 4)


@dataclass
class ContextEntry:
    entity: Entity
    linkage: str
    weight: float | None = None
    # Where in the source the linkage was first emitted. Populated from
    # `linkage_evidence` when available — text/JSON renderers print it as
    # `file:line` so callers can jump straight to the line.
    file: str | None = None
    line: int | None = None
    # Full memory content for kind='memory' entries. Lets `rmx context`
    # at degree>=1 surface the BODY of linked memories alongside the
    # graph view, closing the "get vs context two-surfaces" cliff.
    # None on non-memory entries; the renderers skip it then.
    body: str | None = None


@dataclass
class ContextBundle:
    ref: str
    anchor: Entity | None = None
    groups: dict[str, list[ContextEntry]] = field(default_factory=dict)
    truncated: bool = False
    estimated_tokens: int = 0
    # Full memory body for the anchor when its kind is 'memory'. At
    # degree=0 (anchor-only) this is the entire response payload; at
    # degree>=1 it sits above the graph view.
    anchor_body: str | None = None
    # Hop-depth requested; preserved so renderers and callers can show
    # which expansion shape produced the bundle.
    degree: int = 0

    def total_entities(self) -> int:
        return sum(len(v) for v in self.groups.values())


def build_context(
    s: Store,
    ref: str,
    *,
    linkages: list[str] | None = None,
    max_entities: int = 20,
    max_tokens: int = 4000,
    fuse: bool = False,
    strict: bool = False,
    degree: int = 0,
    _entities_explicit: bool = False,
    _tokens_explicit: bool = False,
) -> ContextBundle:
    """Build a context bundle anchored on `ref` (concept name or entity name).

    `degree` controls extra graph expansion ON TOP of the current
    one-hop walk:

    - `degree=0` (default): current behavior — one-hop linkage walk
      from the anchor. Memory entities (anchor and neighbors) carry
      their full body, so the bundle covers both "what does this say"
      AND "what is it linked to" in one call. Closes the
      `memory get` vs `memory context` two-surfaces cliff.
    - `degree>=1`: reserved for multi-hop expansion (BFS to depth
      degree+1). Not yet implemented as a true multi-hop walk; the
      walk still caps at one hop but `max_entities` / `max_tokens`
      auto-scale with degree so the budget is ready for the deeper
      shape when the BFS lands.

    Budget auto-adjustment: when `max_entities` / `max_tokens` were NOT
    explicitly passed by the caller (i.e. the CLI defaults flowed
    through), they scale with `degree>0` so a deeper request actually
    fits more material. Explicit overrides win.

    When `strict=False` (default), a bare ref (no `kind:name` prefix) is
    first variant-expanded via `Store.resolve_concept_ids(ref, strict=False)`
    so an LLM passing `JSONParser` lands on the canonical `json_parser`
    concept (or vice versa). The first matching concept id becomes the
    anchor. Falls through to literal `resolve_entity` if no canonical
    concept matches — preserves the existing kind:name and code/doc lookup
    paths."""
    bundle = ContextBundle(ref=ref, degree=degree)
    e: object | None = None
    if not strict and ":" not in ref:
        cids = s.resolve_concept_ids(ref, strict=False)
        if cids:
            e = s.get_entity_by_id(cids[0])
    if e is None:
        e = s.resolve_entity(ref)
    if e is None:
        return bundle
    bundle.anchor = e

    # Attach the memory body to the bundle regardless of degree — at
    # degree=0 it's the only payload; at degree>=1 it sits above the
    # graph view.
    if e.kind == "memory":
        try:
            mem = s.get_memory(e.id)
        except Exception:
            mem = None
        if mem is not None:
            bundle.anchor_body = mem.get("content")

    # Auto-scale the budget when the caller did NOT explicitly set the
    # flag and degree > 0 — a deeper request without an override should
    # get a deeper budget too. Explicit values always win.
    if degree > 0:
        if not _entities_explicit:
            max_entities = max_entities * (1 + degree)
        if not _tokens_explicit:
            max_tokens = max_tokens * (1 + degree)

    # Build the linkage iteration order: prioritized defaults first, then any
    # user-defined linkages, both filtered by the user's --linkage choice.
    all_linkages = [lk["name"] for lk in s.list_linkages()]
    ordered = [ln for ln in DEFAULT_LINKAGE_ORDER if ln in all_linkages]
    ordered += [ln for ln in all_linkages if ln not in ordered]
    if linkages:
        wanted = set(linkages)
        ordered = [ln for ln in ordered if ln in wanted]

    used = estimate_tokens(_render_header(bundle))
    if e.tldr:
        used += estimate_tokens(e.tldr)
    if bundle.anchor_body:
        used += estimate_tokens(bundle.anchor_body)

    if fuse:
        rows_iter = _fused_rows(s, e, ordered, max_entities)
    elif e.kind == "concept":
        rows_iter = _concept_rows(s, e.id, ordered, max_entities)
    else:
        rows_iter = _entity_anchored_rows(s, e.id, ordered, max_entities)

    # Pull evidence rows for the anchor concept up front so we don't issue
    # one SELECT per entry. Keyed by (entity_id, linkage_name); when an
    # extractor wrote multiple evidence rows for the same (entity, linkage,
    # concept) triple we keep the lowest line — that's the most useful
    # "jump to here" target.
    evidence = _evidence_index(s, e) if e.kind == "concept" else {}

    for linkage, eid, weight in rows_iter:
        ent = s.get_entity_by_id(eid)
        if ent is None or ent.id == e.id:
            continue
        entry = ContextEntry(entity=ent, linkage=linkage, weight=weight)
        file_line = evidence.get((eid, linkage))
        if file_line is not None:
            entry.file, entry.line = file_line
        # Attach memory bodies to memory neighbors so a degree>=1 walk
        # carries the actual content rather than just a graph edge.
        if ent.kind == "memory":
            try:
                m = s.get_memory(ent.id)
            except Exception:
                m = None
            if m is not None:
                entry.body = m.get("content")
        cost = estimate_tokens(_render_entry(entry))
        if used + cost > max_tokens:
            bundle.truncated = True
            break
        if bundle.total_entities() >= max_entities:
            bundle.truncated = True
            break
        bundle.groups.setdefault(linkage, []).append(entry)
        used += cost

    bundle.estimated_tokens = used
    return bundle


def _evidence_index(
    s: Store, anchor: Entity
) -> dict[tuple[int, str], tuple[str | None, int | None]]:
    """Return {(entity_id, linkage_name): (file, line)} for every evidence
    row pointing at `anchor` (a concept). Picks the lowest line per group
    so the printed target is the first occurrence in the source."""
    con = s._connect()
    rows = con.execute(
        """
        SELECT ev.entity_id, lt.name AS linkage,
               ev.file, MIN(ev.line) AS line
        FROM linkage_evidence ev
        JOIN linkage_types lt ON lt.id = ev.linkage_id
        WHERE ev.concept_id = ?
        GROUP BY ev.entity_id, lt.name, ev.file
        """,
        (anchor.id,),
    ).fetchall()
    out: dict[tuple[int, str], tuple[str | None, int | None]] = {}
    for r in rows:
        key = (r["entity_id"], r["linkage"])
        # If multiple files recorded evidence for the same (entity, linkage),
        # the first one we see wins. They're typically the same file anyway
        # (the entity's own source).
        if key not in out:
            out[key] = (r["file"], r["line"])
    return out


def _fused_rows(s: Store, anchor: Entity, linkages: list[str], cap: int):
    """RRF across per-linkage rankings.

    Each linkage produces a ranked candidate list (top_weighted first, then
    bitmap-order fallback for unweighted linkages). fuse_rrf merges them into
    one global ranking; entity attribution goes to the first linkage that
    ranked it. Caller still groups by linkage for output, but truncation now
    sees globally-best entities first instead of being biased by linkage order.

    Entity-anchored bundles defer to the regular walk — that path mixes
    concepts and sibling entities, which is not a homogeneous candidate set
    suitable for RRF.
    """
    from refmatrix.query import fuse_rrf

    if anchor.kind != "concept":
        yield from _entity_anchored_rows(s, anchor.id, linkages, cap)
        return

    per_linkage: dict[str, list[int]] = {}
    weights: dict[tuple[str, int], float | None] = {}
    for ln in linkages:
        ranked: list[int] = []
        weighted = s.top_weighted(ln, anchor.id, k=cap)
        if weighted:
            for eid, w in weighted:
                ranked.append(eid)
                weights[(ln, eid)] = w
        else:
            for eid in list(s.load_bitmap(ln, anchor.id))[:cap]:
                ranked.append(eid)
                weights[(ln, eid)] = None
        if ranked:
            per_linkage[ln] = ranked

    fused = fuse_rrf(list(per_linkage.values()))
    first_linkage: dict[int, str] = {}
    for ln, ids in per_linkage.items():
        for eid in ids:
            first_linkage.setdefault(eid, ln)

    for eid, _score in fused:
        ln = first_linkage.get(eid)
        if ln is None:
            continue
        yield ln, eid, weights.get((ln, eid))


def _concept_rows(s: Store, concept_id: int, linkages: list[str], cap: int):
    """Yield (linkage, entity_id, weight) for entities reachable from a concept row."""
    for ln in linkages:
        weighted = s.top_weighted(ln, concept_id, k=cap)
        if weighted:
            for eid, w in weighted:
                yield ln, eid, w
            continue
        bm = s.load_bitmap(ln, concept_id)
        for eid in list(bm)[:cap]:
            yield ln, eid, None


def _entity_anchored_rows(s: Store, entity_id: int, linkages: list[str], cap: int):
    """When the anchor is an entity (not a concept), surface the concepts that
    link to it and, through them, sibling entities under the same (linkage, concept).
    Uses the entity_links forward index — O(links) per query."""
    con = s._connect()
    rows = con.execute(
        """
        SELECT linkage_types.name AS linkage,
               entity_links.concept_id AS concept_id,
               entity_links.weight AS weight
        FROM entity_links
        JOIN linkage_types ON linkage_types.id = entity_links.linkage_id
        WHERE entity_links.entity_id = ?
        """,
        (entity_id,),
    ).fetchall()
    by_link: dict[str, list[tuple[int, float | None]]] = {}
    for r in rows:
        by_link.setdefault(r["linkage"], []).append((r["concept_id"], r["weight"]))

    for ln in linkages:
        for concept_id, weight in by_link.get(ln, []):
            # The concept itself is the most useful thing to surface first.
            yield ln, concept_id, weight
            # Then sibling entities under the same (linkage, concept), capped.
            bm = s.load_bitmap(ln, concept_id)
            n = 0
            for eid in bm:
                if eid == entity_id:
                    continue
                yield ln, eid, None
                n += 1
                if n >= cap:
                    break


# ----------------------------- rendering ---------------------------------


def _render_header(b: ContextBundle) -> str:
    return f"=== context for `{b.ref}` ==="


def _render_entry(e: ContextEntry) -> str:
    line = f"  {e.entity.name}  [{e.entity.kind}]"
    if e.weight is not None:
        line += f"  (w={e.weight:g})"
    if e.entity.tldr:
        line += f"\n    {e.entity.tldr}"
    elif e.entity.path:
        # Append :line when we have one from linkage_evidence so editors
        # / readers can jump straight to the relevant source location.
        location = e.entity.path
        if e.line is not None:
            location = f"{location}:{e.line}"
        line += f"\n    {location}"
    if e.body:
        # Indent body lines so they read as a block under the entry header.
        body_block = "\n".join(f"    {ln}" for ln in e.body.splitlines())
        line += f"\n{body_block}"
    return line


def render_text(b: ContextBundle) -> str:
    lines = [_render_header(b)]
    if b.anchor is None:
        lines.append("(unknown symbol)")
        return "\n".join(lines)
    a = b.anchor
    lines.append(f"anchor: {a.name}  [{a.kind}]")
    if a.tldr:
        lines.append(f"  {a.tldr}")
    if b.anchor_body:
        lines.append("")
        lines.append("--- body ---")
        lines.append(b.anchor_body)
    if not b.groups:
        lines.append("")
        lines.append("(no linkages found — try `rmx link` or `rmx ingest --semantic`)")
        return "\n".join(lines)
    for ln, entries in b.groups.items():
        lines.append("")
        lines.append(f"{LINKAGE_LABELS.get(ln, ln.upper())} ({ln}):")
        for e in entries:
            lines.append(_render_entry(e))
    if b.truncated:
        lines.append("")
        lines.append("[truncated by budget]")
    lines.append("")
    lines.append(
        f"[~{b.estimated_tokens} tokens, "
        f"{b.total_entities()} neighbors, degree={b.degree}]"
    )
    return "\n".join(lines)


def render_json(b: ContextBundle) -> str:
    return json.dumps(
        {
            "ref": b.ref,
            "degree": b.degree,
            "anchor": (
                {
                    "name": b.anchor.name,
                    "kind": b.anchor.kind,
                    "path": b.anchor.path,
                    "tldr": b.anchor.tldr,
                    "body": b.anchor_body,
                }
                if b.anchor else None
            ),
            "groups": {
                ln: [
                    {
                        "name": e.entity.name,
                        "kind": e.entity.kind,
                        "path": e.entity.path,
                        "tldr": e.entity.tldr,
                        "body": e.body,
                        "weight": e.weight,
                        "linkage": e.linkage,
                        "file": e.file,
                        "line": e.line,
                    }
                    for e in entries
                ]
                for ln, entries in b.groups.items()
            },
            "truncated": b.truncated,
            "estimated_tokens": b.estimated_tokens,
            "total_neighbors": b.total_entities(),
        },
        indent=2,
    )
