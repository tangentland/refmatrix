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
import re
from dataclasses import dataclass, field

from refmatrix.kwic import kwic_one
from refmatrix.store import Entity, Store

# Co-mention linkages whose neighbors are sections/docs that merely *talk
# about* the anchor (vs. defining it). For these we replace the whole-section
# tldr with a KWIC window around the anchor term — the tldr is a section
# summary that often does not even contain the term.
_KWIC_LINKAGES = {"mentions", "related_to", "content"}


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
    "content": "CONTENT MATCH",
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
    # KWIC window around the anchor term inside this entry's section/body.
    # Populated for co-mention neighbors so the renderer shows the line where
    # the term actually appears instead of a whole-section summary that often
    # does not contain it. None → renderer falls back to tldr / body.
    snippet: str | None = None


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
    include_sessions: bool = False,
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
    else:
        # The anchor resolved to a concept/doc/code node, but the same slug
        # very often ALSO exists as a memory entity — a curated `.md` is
        # ingested as a memory AND its title spawns a concept, so a bare
        # `rmx context <slug>` lands on the thin concept node. Surface the
        # memory body here so context (and the scan-prompt hook, which renders
        # through this same path) returns actual content, not just a graph
        # stub. Cross-partition: the memory may live in memory-<project> while
        # the concept lives in the code partition.
        try:
            mem = s.find_memory_any_partition(e.name)
        except Exception:
            mem = None
        if mem is not None and mem.get("content"):
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

    # Budget-bound the anchor body so a long memory can't swallow the whole
    # bundle and crowd out the graph view. Matters for the scan-prompt hook's
    # small per-concept budget; `rmx context` runs at 4000 tokens so typical
    # bodies pass through untouched. Reserve ~25% of the budget for neighbors.
    if bundle.anchor_body:
        header_cost = estimate_tokens(_render_header(bundle))
        tldr_cost = estimate_tokens(e.tldr) if e.tldr else 0
        body_budget = int(max_tokens * 0.75) - header_cost - tldr_cost
        if body_budget > 0 and estimate_tokens(bundle.anchor_body) > body_budget:
            bundle.anchor_body = (
                bundle.anchor_body[: body_budget * 4].rstrip()
                + "\n…[body truncated to fit budget]"
            )

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

    # Pass 1: materialize entries (+ KWIC snippets) so ranking can see which
    # are real hits. Parent-doc bodies are cached so a card with several
    # mentioned sections is fetched once.
    parent_cache: dict[str, str | None] = {}
    built: list[ContextEntry] = []
    for linkage, eid, weight in list(rows_iter):
        ent = s.get_entity_by_id(eid)
        if ent is None or ent.id == e.id:
            continue
        # Session summaries are transient activity logs that co-mention
        # nearly everything; by default keep them out of the durable concept
        # graph so specs / code / ADRs aren't drowned out. `rmx session
        # recall <term>` is their home (with KWIC snippets of its own).
        if not include_sessions and _is_session_card(ent.name):
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
        # For co-mention neighbors, surface a KWIC window around the anchor
        # term instead of the whole-section tldr. Beats a plain
        # `grep <term>`: ranked, deduped, centered on the match.
        if linkage in _KWIC_LINKAGES:
            entry.snippet = _mention_snippet(s, entry, e.name,
                                             parent_cache=parent_cache)
        built.append(entry)

    # Content-ranked fusion (always-on unless the caller filtered linkages):
    # BM25 over the `mentions` forward index for the ref's terms, folding in
    # body matches the graph walk can't reach — a natural-language phrase whose
    # terms were never co-mentioned on a single node has no graph anchor, so
    # without this `context "fov wedge"` returns an empty stub. Turns context
    # (and scan-prompt / memory recall, which share this path) into a ranked
    # grep. content_rank is partition-scoped, so operational SESSION cards
    # (separate partition) never surface here.
    if not linkages:
        ref_terms = _ref_terms(ref)
        if ref_terms:
            seen_ids = {x.entity.id for x in built} | {e.id}
            for ceid, cscore in s.content_rank(
                ref_terms, kinds=["code", "doc", "memory"],
                limit=max_entities,
            ):
                if ceid in seen_ids:
                    continue
                cent = s.get_entity_by_id(ceid)
                if cent is None:
                    continue
                if not include_sessions and _is_session_card(cent.name):
                    continue
                centry = ContextEntry(entity=cent, linkage="content",
                                      weight=cscore)
                centry.snippet = _content_snippet(
                    s, cent, ref_terms, parent_cache=parent_cache,
                )
                built.append(centry)
                seen_ids.add(ceid)

    # Pass 2: rank (hits-first, docs-before-sessions) then apply the budget so
    # real hits and durable docs survive truncation.
    for entry in _rank_entries(built):
        cost = estimate_tokens(_render_entry(entry))
        if used + cost > max_tokens:
            bundle.truncated = True
            break
        if bundle.total_entities() >= max_entities:
            bundle.truncated = True
            break
        bundle.groups.setdefault(entry.linkage, []).append(entry)
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


def _section_text(body: str, anchor_id: str) -> str | None:
    """Return the GMD section whose heading carries `{#anchor_id}` — from that
    heading line to the next heading. None when the anchor is absent. Lets a
    co-mention KWIC center on the right section of a multi-section card rather
    than the first match anywhere in the parent doc."""
    if not body or not anchor_id:
        return None
    idx = body.find("{#%s}" % anchor_id)
    if idx == -1:
        return None
    line_start = body.rfind("\n", 0, idx) + 1
    nl = body.find("\n", idx)
    if nl == -1:
        return body[line_start:]
    nxt = re.search(r"^#", body[nl + 1:], re.M)
    end = nl + 1 + nxt.start() if nxt else len(body)
    return body[line_start:end]


def _is_session_card(name: str) -> bool:
    """True for session-summary nodes (`session-<hex>` cards and their
    `session-<hex>#anchor` sections). These are transient activity logs; a
    spec / plan / ADR that discusses the term is more durable knowledge and
    should outrank them in a co-mention list."""
    return name.startswith("session-")


def _rank_entries(entries: list[ContextEntry]) -> list[ContextEntry]:
    """Stable re-rank within each co-mention linkage: real hits (carry a KWIC
    snippet) before non-hits, and durable docs before any session cards that
    were opted back in. Linkage order and intra-class weight order are
    preserved (stable sort). Definitional linkages are left untouched.

    Done before the budget loop so hits and durable docs survive truncation
    rather than being crowded out by weak or verbose co-mentions."""
    by_link: dict[str, list[ContextEntry]] = {}
    order: list[str] = []
    for e in entries:
        if e.linkage not in by_link:
            by_link[e.linkage] = []
            order.append(e.linkage)
        by_link[e.linkage].append(e)
    out: list[ContextEntry] = []
    for ln in order:
        rows = by_link[ln]
        if ln in _KWIC_LINKAGES:
            rows = sorted(rows, key=lambda e: (
                0 if e.snippet else 1,                          # hits first
                1 if _is_session_card(e.entity.name) else 0,    # docs first
            ))
        out.extend(rows)
    return out


def _ref_terms(ref: str) -> list[str]:
    """Tokenize a context ref into content-search terms: split a multi-word
    phrase on whitespace, strip a leading `kind:` prefix, drop 1-char tokens.
    Per-term variant/canonical expansion happens inside `Store.content_rank`."""
    ref = ref.strip()
    head = ref.split(":", 1)[0]
    if ":" in ref and " " not in head and "/" not in head:
        ref = ref.split(":", 1)[1]  # kind:name → name
    out: list[str] = []
    seen: set[str] = set()
    for tok in re.split(r"\s+", ref):
        tok = tok.strip()
        if len(tok) < 2 or tok.lower() in seen:
            continue
        seen.add(tok.lower())
        out.append(tok)
    return out


def _content_snippet(
    s: Store, ent: Entity, terms: list[str],
    *, parent_cache: dict[str, str | None] | None = None,
) -> str | None:
    """KWIC window for a content-ranked hit: reuse the `_mention_snippet` body
    ladder (memory body → parent doc/section → tldr) for the first term that
    lands a window. None when no term occurs in any available text."""
    probe = ContextEntry(entity=ent, linkage="content")
    if ent.kind == "memory":
        try:
            m = s.get_memory(ent.id)
        except Exception:
            m = None
        if m is not None:
            probe.body = m.get("content")
    for t in terms:
        snip = _mention_snippet(s, probe, t, parent_cache=parent_cache)
        if snip:
            return snip
    return None


def _mention_snippet(
    s: Store, entry: ContextEntry, term: str,
    *, parent_cache: dict[str, str | None] | None = None,
) -> str | None:
    """Best KWIC window of `term` for a co-mention neighbor, via a body ladder:
    1. an already-attached memory body, 2. the parent doc/section fetched
    cross-partition (sliced to the neighbor's anchor), 3. the entry tldr.
    Returns None when the term occurs in none of them (renderer keeps tldr).

    `parent_cache` memoizes parent-doc bodies by name across calls so a doc
    with several mentioned sections is fetched once."""
    ent = entry.entity
    if entry.body:
        snip = kwic_one(entry.body, term)
        if snip:
            return snip
    if "#" in ent.name:
        parent_name, anchor_id = ent.name.split("#", 1)
        if parent_cache is not None and parent_name in parent_cache:
            body = parent_cache[parent_name]
        else:
            try:
                mem = s.find_memory_any_partition(parent_name)
            except Exception:
                mem = None
            body = mem.get("content") if mem else None
            if parent_cache is not None:
                parent_cache[parent_name] = body
        if body:
            # Prefer the neighbor's own section; fall back to the whole card
            # when the term lives in a different section of the same doc.
            for src in (_section_text(body, anchor_id), body):
                snip = kwic_one(src, term) if src else ""
                if snip:
                    return snip
    if ent.tldr:
        snip = kwic_one(ent.tldr, term)
        if snip:
            return snip
    return None


# ----------------------------- rendering ---------------------------------


def _render_header(b: ContextBundle) -> str:
    return f"=== context for `{b.ref}` ==="


def _render_entry(e: ContextEntry) -> str:
    line = f"  {e.entity.name}  [{e.entity.kind}]"
    if e.weight is not None:
        line += f"  (w={e.weight:g})"
    # A KWIC snippet is the whole payload — it already shows the matched line,
    # so we skip the whole-section tldr / full body dump that follows.
    if e.snippet:
        line += f"\n    {e.snippet}"
        return line
    if e.entity.tldr:
        tldr = e.entity.tldr
        # A co-mention node with no KWIC hit: the term isn't in its body, so
        # the multi-line section summary is noise — show only its first line
        # as a label. (Definitional linkages keep the full tldr.)
        if e.linkage in _KWIC_LINKAGES:
            tldr = tldr.splitlines()[0] if tldr.strip() else tldr
        line += f"\n    {tldr}"
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
                        "snippet": e.snippet,
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
