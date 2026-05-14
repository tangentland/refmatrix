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


@dataclass
class ContextBundle:
    ref: str
    anchor: Entity | None = None
    groups: dict[str, list[ContextEntry]] = field(default_factory=dict)
    truncated: bool = False
    estimated_tokens: int = 0

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
) -> ContextBundle:
    """Build a context bundle anchored on `ref` (concept name or entity name)."""
    bundle = ContextBundle(ref=ref)
    e = s.resolve_entity(ref)
    if e is None:
        return bundle
    bundle.anchor = e

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

    if fuse:
        rows_iter = _fused_rows(s, e, ordered, max_entities)
    elif e.kind == "concept":
        rows_iter = _concept_rows(s, e.id, ordered, max_entities)
    else:
        rows_iter = _entity_anchored_rows(s, e.id, ordered, max_entities)

    for linkage, eid, weight in rows_iter:
        ent = s.get_entity_by_id(eid)
        if ent is None or ent.id == e.id:
            continue
        entry = ContextEntry(entity=ent, linkage=linkage, weight=weight)
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
        line += f"\n    {e.entity.path}"
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
    lines.append(f"[~{b.estimated_tokens} tokens, {b.total_entities()} neighbors]")
    return "\n".join(lines)


def render_json(b: ContextBundle) -> str:
    return json.dumps(
        {
            "ref": b.ref,
            "anchor": (
                {
                    "name": b.anchor.name,
                    "kind": b.anchor.kind,
                    "path": b.anchor.path,
                    "tldr": b.anchor.tldr,
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
                        "weight": e.weight,
                        "linkage": e.linkage,
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
