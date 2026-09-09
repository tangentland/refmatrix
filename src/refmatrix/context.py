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

import itertools
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from refmatrix.kwic import kwic_def_line, kwic_line, kwic_one
from refmatrix.store import Entity, Store

# Co-mention linkages whose neighbors are sections/docs that merely *talk
# about* the anchor (vs. defining it). For these we replace the whole-section
# tldr with a KWIC window around the anchor term — the tldr is a section
# summary that often does not even contain the term.
_KWIC_LINKAGES = {"mentions", "related-to", "content"}


# Order linkages so output reads like a natural definition: what *is* this
# thing, who points at it, what does it point at, where is it talked about.
DEFAULT_LINKAGE_ORDER = [
    "defines", "implements",
    "called_by", "imports",
    "calls", "is_a", "related-to",
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
    "related-to": "RELATED TO",
    "content": "CONTENT MATCH",
    "grep": "GREP (unindexed — floor)",
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
    # Every source line where the anchor concept hit this entity (sorted, from
    # linkage_evidence). Populated under `--hit-lines nums`/`text`; the renderer
    # prints `file:l1,l2,l3` instead of the single first-occurrence line.
    lines: list[int] | None = None
    # (line_no, source_text) for each hit line — populated under `--hit-lines
    # text` so the renderer shows grep -n style content, not just numbers.
    hit_lines: list[tuple[int, str]] | None = None


# Helix neighbor sweep bounds: how many neighbor names to test against the
# touch index per bundle, and how many annotations may render.
_HELIX_NEIGHBOR_SCAN = 20
_HELIX_NEIGHBOR_NOTES = 5


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
    # Helix phase-1 annotation: when the anchor's last STM touch predates
    # the working window, this carries the point-in-time neighborhood from
    # that touch (see helix.annotate). None = current work or no history.
    helix_note: "str | None" = None
    # Stale graph NEIGHBORS annotated the same way (capped): the richest
    # source of genuinely-cold concepts — an anchor the prompt just named is
    # almost never stale, its neighborhood often is.
    helix_neighbor_notes: "list[str]" = field(default_factory=list)
    # Deferred helix readership rows + the store root to flush them against.
    # Renderers call helix.flush() so ONLY rendered bundles log (scan-prompt
    # drops some bundles after building them; those must not count).
    helix_pending: list = field(default_factory=list)
    store_root: "str | None" = None

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
    expand: int = 0,
    hit_lines: str = "first",
    reranker=None,
    grep_backstop: bool = True,
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
        # No graph anchor — serve a content-ranked grep over ref's terms so an
        # arbitrary NL phrase (and the scan-prompt hook) gets the ranked-grep
        # fallback instead of an empty stub. --linkage filtering opts out.
        if linkages:
            return bundle
        return content_only_bundle(
            s, ref, max_entities=max_entities, max_tokens=max_tokens,
            expand=expand, include_sessions=include_sessions,
            hit_lines=hit_lines, grep_backstop=grep_backstop,
        )
    bundle.anchor = e

    # Helix phase 1: when this anchor's last STM touch predates the working
    # window, carry the point-in-time neighborhood from that touch. Strictly
    # additive and best-effort — a read surface must never fail (or slow
    # down meaningfully) because the STM rings were unreadable.
    bundle.store_root = str(s.root)
    try:
        from refmatrix import helix
        bundle.helix_note = helix.annotate(s.root, e.name,
                                           sink=bundle.helix_pending)
    except Exception:
        bundle.helix_note = None

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

    # `<doc-id>` and `<doc-id>#root` are BOTH real entities for an ingested
    # GMD doc, and the typed `rel:` edges land on the `#root` concept — the
    # doc-level entity carries only `mentions`. An author seeding retrieval
    # with the id they declared in frontmatter (the id MEMORY.md indexes)
    # therefore got mention noise and none of the graph. Seed both and put
    # the root node's rows FIRST so real edges win the token budget.
    companion = None
    if "#" not in e.name:
        try:
            companion = s.resolve_entity(f"{e.name}#root")
        except Exception:
            companion = None
        if companion is not None and companion.id == e.id:
            companion = None

    def _rows_for(anchor):
        if fuse:
            return _fused_rows(s, anchor, ordered, max_entities)
        if anchor.kind == "concept":
            return _concept_rows(s, anchor.id, ordered, max_entities)
        # A non-concept anchor can still be the SOURCE side of a typed edge:
        # `store.link(verb, src, dst)` packs src into the concept_id column
        # whatever the src entity's kind, so a memory's own `rel:` edges are
        # keyed by its id. `_entity_anchored_rows` only reads the entity_id
        # side, so those outbound edges were invisible — a GMD memory's
        # declared graph did not show up in its own context bundle. Read the
        # source side first (few, typed, high-signal), then the inbound walk.
        return itertools.chain(
            _concept_rows(s, anchor.id, ordered, max_entities),
            _entity_anchored_rows(s, anchor.id, ordered, max_entities),
        )

    rows_iter = _rows_for(e)
    if companion is not None:
        rows_iter = itertools.chain(_rows_for(companion), rows_iter)

    # Pull evidence rows for the anchor concept up front so we don't issue
    # one SELECT per entry. Keyed by (entity_id, linkage_name); when an
    # extractor wrote multiple evidence rows for the same (entity, linkage,
    # concept) triple we keep the lowest line — that's the most useful
    # "jump to here" target.
    all_lines = hit_lines in ("nums", "text")
    evidence = (_evidence_index(s, e, all_lines=all_lines)
                if e.kind == "concept" else {})
    if companion is not None and companion.kind == "concept":
        # Companion rows keep their file:line jump targets too.
        for k, v in _evidence_index(s, companion, all_lines=all_lines).items():
            evidence.setdefault(k, v)
    proj_root = s.root.parent

    # Pass 1: materialize entries (+ KWIC snippets) so ranking can see which
    # are real hits. Parent-doc bodies are cached so a card with several
    # mentioned sections is fetched once.
    parent_cache: dict[str, str | None] = {}
    built: list[ContextEntry] = []
    seen_pairs: set[tuple[str, int]] = set()
    for linkage, eid, weight in list(rows_iter):
        ent = s.get_entity_by_id(eid)
        if ent is None or ent.id == e.id:
            continue
        # The bundle now merges several row sources (outbound edges, the
        # inbound walk, the `#root` companion); the same (linkage, entity)
        # can surface from more than one of them.
        if (linkage, eid) in seen_pairs:
            continue
        seen_pairs.add((linkage, eid))
        # Session summaries are transient activity logs that co-mention
        # nearly everything; by default keep them out of the durable concept
        # graph so specs / code / ADRs aren't drowned out. `rmx session
        # recall <term>` is their home (with KWIC snippets of its own).
        if not include_sessions and _is_session_card(ent.name):
            continue
        entry = ContextEntry(entity=ent, linkage=linkage, weight=weight)
        ev = evidence.get((eid, linkage))
        if ev is not None:
            entry.file, entry.line, entry.lines = ev
            if hit_lines == "text" and entry.lines:
                entry.hit_lines = _read_hit_lines(proj_root, entry.file,
                                                  entry.lines)
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
        seen_ids = {x.entity.id for x in built} | {e.id}
        _append_content_hits(
            s, ref, built, seen_ids=seen_ids, max_entities=max_entities,
            expand=expand, include_sessions=include_sessions,
            parent_cache=parent_cache, grep_backstop=grep_backstop,
            hit_lines=hit_lines, reranker=reranker,
        )

    _apply_budget(bundle, built, max_entities, max_tokens, used)

    # Helix: annotate stale NEIGHBORS too (the anchor-only gate measured the
    # wrong thing — a concept the prompt just named is inside the working
    # window by construction; its neighborhood is where cold history lives).
    _helix_neighbor_sweep(s, bundle, skip={e.name})
    return bundle


def _def_pattern(sym: str) -> "re.Pattern[str]":
    """Regex matching a source line that DEFINES `sym` (a single identifier),
    across Python / JS / TS / Rust-ish syntaxes. Used to recognize an exact-
    symbol definition among content hits so it can be floored above fuzzy body
    mentions."""
    s = re.escape(sym)
    return re.compile(
        r"\b(?:async\s+)?(?:def|class|function|interface|type|enum|struct"
        r"|trait|fn)\s+" + s + r"\b"
        r"|\b(?:const|let|var)\s+" + s + r"\b\s*[=:]"
    )


def _floor_exact_defs(entries: list[ContextEntry], ref: str) -> None:
    """In-place: lift any content entry whose snippet DEFINES the single-
    identifier `ref` above the top fuzzy score, then sort exact-first.

    A definition's BM25 content score can be 0 — e.g. the ref resolves to a
    learned `query/<ref>` concept whose `mentions` edges carry `tf=0`, zeroing
    the BM25 numerator — which sinks the actual `def <ref>` below fuzzy body
    mentions and renders it as `w=0`: the least-useful slot for the most-
    relevant hit. No-op for an NL phrase (no single symbol to define) or when
    no hit defines the ref, so phrase queries rank exactly as before."""
    sym = ref.strip()
    if not entries or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", sym):
        return
    pat = _def_pattern(sym)
    top = max((e.weight or 0.0) for e in entries)
    boosted = False
    for e in entries:
        if e.snippet and pat.search(e.snippet):
            e.weight = top + 1.0 + (e.weight or 0.0)
            boosted = True
    if boosted:
        entries.sort(key=lambda e: -(e.weight or 0.0))


# A hit earns a rerank only if its extractor returns more than a label. Asking
# a cross-encoder to score a sentence against two words is noise, and this path
# surfaces a lot of short nodes: on a GMD corpus the anchored `doc#section`
# concepts carry the body-term index, so they dominate `content_rank`.
#
# Deliberately measured on TEXT rather than on kind. Kind was the first cut and
# it was wrong in both directions — it excluded anchored concepts that do have
# bodies (`_extract_concept` now returns them) and would have included any
# future bodiless doc row.
_MIN_RERANK_CHARS = 120


def _prf_terms() -> int:
    """How many expansion terms to mine from the top hits' bodies. 0 = off."""
    import os
    try:
        return max(0, int(os.environ.get("RMX_PRF_TERMS", "0") or "0"))
    except ValueError:
        return 0


def _prf_docs() -> int:
    """How many top hits to mine them FROM. Kept small: the whole risk of
    pseudo-relevance feedback is that a bad first-pass hit poisons the second
    pass, and the damage scales with how many documents you trust."""
    import os
    try:
        return max(1, int(os.environ.get("RMX_PRF_DOCS", "3") or "3"))
    except ValueError:
        return 3


def _prf_expansion(s: Store, hits: list, ref_terms: list[str],
                   n_terms: int) -> list[str]:
    """Mine expansion terms from the bodies of the top hits.

    Ranks candidate terms by document frequency WITHIN the feedback set — a
    term several top hits agree on is a better bet than one that appears many
    times in a single document, which is how PRF usually goes wrong.
    Stopwords and terms already in the query are dropped.
    """
    from collections import Counter

    from refmatrix.terms import STOPWORDS, content_terms

    have = {t.lower() for t in ref_terms}
    df: Counter[str] = Counter()
    surface: dict[str, str] = {}
    order: dict[str, int] = {}
    for eid, _sc in hits[:_prf_docs()]:
        ent = s.get_entity_by_id(eid)
        if ent is None:
            continue
        body = (getattr(ent, "tldr", None) or "").strip()
        if not body:
            continue
        seen_here: set[str] = set()
        for tok in content_terms(body, drop_stopwords=False):
            low = tok.lower()
            if low in have or low in STOPWORDS or len(low) < 3:
                continue
            if low not in seen_here:          # df, not tf
                seen_here.add(low)
                df[low] += 1
            surface.setdefault(low, tok)
            order.setdefault(low, len(order))
    # Deterministic: df descending, then first appearance. Iterating a set
    # made tie-breaking arbitrary, so which expansion terms won varied run to
    # run — and with a small feedback set almost every term ties at df=1.
    ranked = sorted(df, key=lambda t: (-df[t], order[t]))
    return [surface[t] for t in ranked[:n_terms]]


def _rerank_pool() -> int:
    """How many bodied hits the cross-encoder may score on the content path.

    Bodied concepts are what made reranking this surface work at all
    (MemAware MRR 0.150 -> 0.217), and also what made it expensive: an
    823-char body costs ~20x a 45-char label. 10 keeps the always-on hook
    near a second."""
    import os
    try:
        return max(2, int(os.environ.get("RMX_SCAN_RERANK_POOL", "10") or "10"))
    except ValueError:
        return 10


def _rerank_bodied(s: Store, reranker, query: str,
                   hits: list) -> list:
    """Reorder only the hits that carry real text; leave label-like rows where
    BM25 put them.

    Reranking everything measured WORSE than not reranking at all on MemAware
    (hit@20 0.389 -> 0.344 even after fixing the query shape). Bodied rows keep
    their positions in the output list, so a label row is never displaced by a
    reorder it did not participate in.
    """
    from refmatrix import embedder as embmod
    from refmatrix.reranker import rerank_entity_hits

    slots: list[int] = []
    for i, (eid, _sc) in enumerate(hits):
        ent = s.get_entity_by_id(eid)
        if ent is None:
            continue
        try:
            text = embmod.extract_text_for_entity(s, eid, ent.kind)
        except Exception:
            continue
        if len(text) >= _MIN_RERANK_CHARS:
            slots.append(i)
    if len(slots) < 2:
        return hits
    # Cap the pool. Cost is linear-ish in DOC COUNT and indifferent to doc
    # length (the model truncates at 512 tokens either way): measured 5 docs
    # 0.64s, 10 docs 1.33s, 15 docs 5.25s, 30 docs 10.67s. Reranking all 30
    # content hits took the always-on scan-prompt hook from 0.24s to 9.3s,
    # which no per-prompt budget can absorb. Rows beyond the pool keep their
    # BM25 positions.
    pool = _rerank_pool()
    slots = slots[:pool]
    subset = [hits[i] for i in slots]
    reordered = rerank_entity_hits(s, reranker, query, subset, k=len(subset))
    if len(reordered) != len(subset):
        return hits
    out = list(hits)
    for slot, hit in zip(slots, reordered):
        out[slot] = hit
    return out


def _phrase_boost_factor() -> float:
    """Rank-time multiplier for content hits where the query's terms appear
    ADJACENT (as a phrase) rather than merely co-present. Ordering-only
    signal: it cannot change the candidate set (the closed phrase-layer
    experiment showed composition adds no reachability), it promotes the
    exact-phrase hit above the scattered-terms hit inside the shortlist.
    RMX_PHRASE_BOOST=1.0 disables."""
    import os as _os
    try:
        return float(_os.environ.get("RMX_PHRASE_BOOST", "1.5") or "1.5")
    except ValueError:
        return 1.5


# Max chars allowed between two query terms to still count as "adjacent".
_PHRASE_WINDOW_CHARS = 24


def _phrase_hit(text: str | None, terms: list[str]) -> bool:
    """True when any consecutive term BIGRAM of the query occurs in order
    within a small window in `text`. Case-insensitive, cheap (top-N snippet
    strings only), order-sensitive — `replica rotation` matches
    "replica slot rotation", not "rotation ... replica"."""
    if not text or len(terms) < 2:
        return False
    low = text.lower()
    for a, b in zip(terms, terms[1:]):
        start = 0
        la = a.lower()
        lb = b.lower()
        while True:
            i = low.find(la, start)
            if i < 0:
                break
            j = low.find(lb, i + len(la))
            if j >= 0 and (j - (i + len(la))) <= _PHRASE_WINDOW_CHARS:
                return True
            start = i + 1
    return False


def _append_content_hits(
    s: Store, ref: str, built: list[ContextEntry], *,
    seen_ids: set[int], max_entities: int, expand: int,
    include_sessions: bool, parent_cache: dict[str, str | None],
    grep_backstop: bool = False, hit_lines: str = "first", reranker=None,
    rerank_query: "str | None" = None,
) -> None:
    """Content-ranked fusion: BM25 over the `mentions` forward index for the
    ref's terms, folding in body matches the graph walk can't reach. Turns
    context (and scan-prompt / memory recall, which share this path) into a
    ranked grep. Partition-scoped, so operational SESSION cards never surface.

    Twin dedup: two paths holding byte-identical code (vendored copies, a
    `docker/uat-workspace` mirror) yield the same visible def-line snippet at
    the same rank — keep the first (highest-scoring) and drop the rest, so a
    duplicated tree can't eat half the result slots.

    Grep backstop: when the index returns ZERO content hits but `grep_backstop`
    is set, literally grep the source tree (`_grep_backstop`) so `context` is
    never worse than a plain grep — grep with the index's upside on top."""
    ref_terms = _ref_terms(ref)
    if not ref_terms:
        return
    seen_snip: set[tuple[str, str]] = set()
    seen_root_twins: set[str] = set()
    n_before = len(built)
    content_entries: list[ContextEntry] = []
    # `concept` belongs in this list because of how GMD ingest shapes the
    # graph: a GMD doc becomes TWO entities — a doc/memory named `<doc-id>`
    # and one `kind=concept` node per heading named `<doc-id>#<anchor>` — and
    # the body term-frequency sweep hangs every `mentions` edge on the NODE.
    # Measured on a GMD-ingested corpus: the `#root` node carried hundreds of
    # body-term edges while its memory sibling carried 5. Ranking only
    # code/doc/memory therefore searched the half of the graph that has no body
    # index, and every multi-word natural-language ref fell through to the grep
    # floor while the same terms resolved fine as single-token anchors.
    # Over-fetch: several anchors of one doc can rank, and they collapse below.
    ranked_hits = s.content_rank(
        ref_terms, kinds=["code", "doc", "memory", "concept"],
        limit=max_entities * 3,
    )
    # Pseudo-relevance feedback over `tldr`. The top hits' bodies name the
    # vocabulary the prompt was reaching for but did not use — the classic
    # case being a request whose words share nothing with the answer's words.
    # Only possible now that anchored concepts carry their section text;
    # before, expanding from `tldr` would have expanded from headings.
    prf_n = _prf_terms()
    if prf_n and ranked_hits and ref_terms:
        extra = _prf_expansion(s, ranked_hits, ref_terms, prf_n)
        if extra:
            ranked_hits = s.content_rank(
                list(ref_terms) + extra,
                kinds=["code", "doc", "memory", "concept"],
                limit=max_entities * 3,
            ) or ranked_hits
    # Cross-encoder pass over the shortlist, when the caller supplied one.
    # This is THE shared choke point: `build_context` (rmx context) and
    # `content_only_bundle` (scan-prompt's content view) both land here, so
    # wiring rerank once gives both surfaces the capability that previously
    # existed only on `memory recall` / `ann_search`. Degrades to the BM25
    # order on any failure — reranking refines an answer we already have and
    # must never be the reason a surface returns nothing.
    if reranker is not None and ranked_hits:
        # Rerank against the ORIGINAL phrasing, not the tokenized bag. A
        # cross-encoder scores a (query, passage) pair jointly and was trained
        # on natural language; handing it stoplisted identifier tokens is a
        # different distribution. Measured: scan-prompt reranking against its
        # candidate bag took MemAware hit@20 0.389 -> 0.333 and MRR 0.150 ->
        # 0.065, while `memory recall` reranking against the raw question
        # GAINED 21% MRR. Same model, same corpus — the query shape was the
        # whole difference. `rerank_query` lets a caller whose `ref` is already
        # a bag supply the sentence the user actually wrote.
        rq = rerank_query or ref
        try:
            ranked_hits = _rerank_bodied(s, reranker, rq, ranked_hits)
        except Exception:
            pass
    for ceid, cscore in ranked_hits:
        if len(content_entries) >= max_entities:
            break
        if ceid in seen_ids:
            continue
        cent = s.get_entity_by_id(ceid)
        if cent is None:
            continue
        # A bare concept is a query term, not a body — only ANCHORED concepts
        # (`doc#section`) are content the reader can be sent to.
        if cent.kind == "concept" and "#" not in cent.name:
            continue
        if not include_sessions and _is_session_card(cent.name):
            continue
        # Root-anchor twin: GMD ingest makes a doc/memory row `X` AND a
        # concept row `X#root` carrying the same headline. Both rank on the
        # same terms and print as near-identical lines — one hit, not two.
        # Non-root anchors are real sections and stay eligible.
        base = cent.name[:-5] if cent.name.endswith("#root") else cent.name
        if base in seen_root_twins:
            continue
        seen_root_twins.add(base)
        seen_ids.add(ceid)
        res = _content_snippet(s, cent, ref_terms, expand=expand,
                               parent_cache=parent_cache)
        snippet, line = res if res else (None, None)
        if snippet:
            # Key on (symbol leaf, first/anchor snippet line) — identical
            # visible code from a different path is a twin, not a new hit.
            tkey = (cent.name.split("::")[-1], snippet.splitlines()[0])
            if tkey in seen_snip:
                continue
            seen_snip.add(tkey)
        centry = ContextEntry(entity=cent, linkage="content", weight=cscore)
        centry.snippet = snippet
        centry.line = line
        content_entries.append(centry)
    # Phrase proximity: terms travelling TOGETHER outrank the same terms
    # scattered. Checked against the text already in hand (snippet, else
    # name/tldr) so it costs nothing beyond the shortlist. Ordering-only.
    boost = _phrase_boost_factor()
    if boost != 1.0 and len(ref_terms) >= 2:
        changed = False
        for centry in content_entries:
            probe = centry.snippet or centry.entity.tldr or centry.entity.name
            if _phrase_hit(probe, ref_terms):
                centry.weight = (centry.weight or 0.0) * boost
                changed = True
        if changed:
            content_entries.sort(key=lambda x: -(x.weight or 0.0))
    # Floor an exact-symbol definition above fuzzy body mentions before the
    # entries land: a `def <ref>` whose BM25 score is 0 must not rank last or
    # render w=0. No-op for NL phrases.
    _floor_exact_defs(content_entries, ref)
    built.extend(content_entries)
    # Floor: index found nothing on disk that grep would have. Grep the files.
    if grep_backstop and len(built) == n_before:
        built.extend(_grep_backstop(
            ref_terms, s.root.parent, limit=max_entities,
            expand=expand, hit_lines=hit_lines,
            # A multi-word ref is prose, not a symbol: match whole words.
            whole_word=len(ref.split()) > 1,
        ))


def _grep_backstop(
    terms: list[str], root: Path, *, limit: int, expand: int = 0,
    hit_lines: str = "first", whole_word: bool = False,
) -> list[ContextEntry]:
    """Literal `rg` (then `grep -rn`) over the source tree for `terms` — the
    floor that makes `context` never worse than a plain grep. Honors
    `.refmatrix_ignore` + code/doc extensions, groups matches per file, and
    returns `grep`-linkage entries that render like content hits (path:line,
    snippet, and `--hit-lines` nums/text). Empty on no tool / no match.

    `whole_word` adds `-w`. Callers set it for natural-language refs, where a
    substring match on a short word is almost always spurious. It stays OFF for
    identifier refs: there, matching `fov_wedge` inside `fov_wedge_polygon` is
    the point of the floor, and a word boundary would throw the hit away."""
    import shutil
    import subprocess
    from refmatrix.ingest import CODE_EXTS, DOC_EXTS, should_ignore

    if not terms:
        return []
    rg = shutil.which("rg")
    if rg:
        cmd = [rg, "-nH", "-i", "-F", "--no-heading", "--no-messages"]
        if whole_word:
            cmd.append("-w")
        for t in terms:
            cmd += ["-e", t]
        cmd.append(str(root))
    else:
        g = shutil.which("grep")
        if not g:
            return []
        cmd = [g, "-rnHiFw"] if whole_word else [g, "-rnHiF"]
        for t in terms:
            cmd += ["-e", t]
        cmd.append(str(root))
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    except (OSError, ValueError, subprocess.SubprocessError):
        return []
    if not res.stdout.strip():
        return []
    exts = CODE_EXTS | DOC_EXTS
    per_file: dict[str, list[tuple[int, str]]] = {}
    for raw in res.stdout.splitlines():
        parts = raw.split(":", 2)
        if len(parts) < 3:
            continue
        path, lno, text = parts
        try:
            n = int(lno)
        except ValueError:
            continue
        p = Path(path)
        if p.suffix.lower() not in exts or should_ignore(p, root):
            continue
        per_file.setdefault(str(p), []).append((n, text.rstrip()))
        if len(per_file) > limit * 8:   # bound parse work on a flood
            break
    # Rank files by match count (a density signal), then path for stability.
    ranked = sorted(per_file.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:limit]
    q = " ".join(terms)
    out: list[ContextEntry] = []
    for path, hits in ranked:
        hits.sort()
        try:
            rel = str(Path(path).relative_to(root))
        except ValueError:
            rel = path
        kind = "code" if Path(path).suffix.lower() in CODE_EXTS else "doc"
        ent = Entity(id=0, kind=kind, name=rel, path=path, tldr=None, meta={})
        e = ContextEntry(entity=ent, linkage="grep", weight=float(len(hits)))
        e.file = rel
        e.line = hits[0][0]
        e.snippet = kwic_line(hits[0][1], q) or hits[0][1]
        if hit_lines in ("nums", "text"):
            e.lines = [n for n, _ in hits]
            if hit_lines == "text":
                e.hit_lines = hits[:_HIT_LINES_CAP]
        out.append(e)
    return out


def _apply_budget(
    bundle: ContextBundle, built: list[ContextEntry],
    max_entities: int, max_tokens: int, used: int,
) -> None:
    """Rank (hits-first, docs-before-sessions) then fill groups under the token
    / entity budget so real hits and durable docs survive truncation."""
    for entry in _rank_entries(built):
        cost = estimate_tokens(_render_entry(entry))
        if used + cost > max_tokens or bundle.total_entities() >= max_entities:
            bundle.truncated = True
            break
        bundle.groups.setdefault(entry.linkage, []).append(entry)
        used += cost
    bundle.estimated_tokens = used


def _helix_neighbor_sweep(s: Store, bundle: ContextBundle,
                          *, skip: set | None = None) -> None:
    """Annotate stale graph neighbors on a built bundle. Bounded: one shared
    index, first _HELIX_NEIGHBOR_SCAN names checked, at most
    _HELIX_NEIGHBOR_NOTES emitted. Rows go to bundle.helix_pending so only a
    RENDERED bundle logs them. Best-effort, never fatal."""
    try:
        from refmatrix import helix
        idx = helix.build_index(s.root)
        bundle.store_root = bundle.store_root or str(s.root)
        seen: set = set(skip or ())
        for entries in bundle.groups.values():
            for entry in entries:
                nm = entry.entity.name
                if nm in seen:
                    continue
                seen.add(nm)
                if len(seen) > _HELIX_NEIGHBOR_SCAN:
                    break
                note = helix.annotate(s.root, nm, index=idx, label=nm,
                                      sink=bundle.helix_pending)
                if note:
                    bundle.helix_neighbor_notes.append(note)
                    if len(bundle.helix_neighbor_notes) >= _HELIX_NEIGHBOR_NOTES:
                        break
            if (len(bundle.helix_neighbor_notes) >= _HELIX_NEIGHBOR_NOTES
                    or len(seen) > _HELIX_NEIGHBOR_SCAN):
                break
    except Exception:
        pass


def content_only_bundle(
    s: Store, ref: str, *, max_entities: int = 20, max_tokens: int = 4000,
    expand: int = 0, include_sessions: bool = False,
    hit_lines: str = "first", grep_backstop: bool = True,
    reranker=None, rerank_query: "str | None" = None,
) -> ContextBundle:
    """A ranked-grep bundle for a ref that resolves to NO graph anchor — the
    content-fusion path with `anchor=None`. Lets `rmx context "<phrase>"` and
    the scan-prompt hook serve code/doc hits for an arbitrary natural-language
    phrase instead of an empty `(unknown symbol)` stub."""
    bundle = ContextBundle(ref=ref)
    built: list[ContextEntry] = []
    _append_content_hits(
        s, ref, built, seen_ids=set(), max_entities=max_entities,
        expand=expand, include_sessions=include_sessions, parent_cache={},
        grep_backstop=grep_backstop, hit_lines=hit_lines, reranker=reranker,
        rerank_query=rerank_query,
    )
    _apply_budget(bundle, built, max_entities, max_tokens,
                  estimate_tokens(_render_header(bundle)))
    # Coverage: the NL/no-anchor path was invisible to helix entirely, which
    # biased the phase-2 readership signal downward. The hits ARE the
    # neighborhood here — sweep them like graph neighbors.
    _helix_neighbor_sweep(s, bundle)
    return bundle


# Cap the lines printed per entry under --hit-lines nums/text so a concept
# mentioned hundreds of times in one file can't blow the budget. The renderer
# appends a `(+N more)` marker rather than truncating silently.
_HIT_LINES_CAP = 8


def _evidence_index(
    s: Store, anchor: Entity, *, all_lines: bool = False
) -> dict[tuple[int, str], tuple[str | None, int | None, list[int] | None]]:
    """Return {(entity_id, linkage_name): (file, first_line, all_lines)} for
    every evidence row pointing at `anchor` (a concept). `first_line` is the
    lowest line (the default jump target). `all_lines` is the sorted distinct
    line list when the caller asked for it (`--hit-lines nums`/`text`), else
    None."""
    con = s._connect()
    rows = con.execute(
        """
        SELECT ev.entity_id, lt.name AS linkage, ev.file, ev.line
        FROM linkage_evidence ev
        JOIN linkage_types lt ON lt.id = ev.linkage_id
        WHERE ev.concept_id = ? AND ev.line IS NOT NULL
        """,
        (anchor.id,),
    ).fetchall()
    # Gather every line per (entity, linkage); the first file seen wins (rows
    # for one entity+linkage are typically all its own source file anyway).
    acc: dict[tuple[int, str], tuple[str | None, set[int]]] = {}
    for r in rows:
        key = (r["entity_id"], r["linkage"])
        file, lines = acc.get(key, (r["file"], set()))
        lines.add(r["line"])
        acc[key] = (file, lines)
    out: dict[tuple[int, str], tuple[str | None, int | None, list[int] | None]] = {}
    for key, (file, lines) in acc.items():
        ordered = sorted(lines)
        out[key] = (file, ordered[0], ordered if all_lines else None)
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
    """Tokenize a context ref into content-search terms.

    Thin wrapper over the shared tokenizer; `strip_kind_prefix` handles this
    surface's `kind:name` refs. See `terms.content_terms` for why the stoplist
    is applied and why it is skipped when nothing would survive."""
    from refmatrix.terms import content_terms
    return content_terms(ref, strip_kind_prefix=True)


def _content_snippet(
    s: Store, ent: Entity, terms: list[str],
    *, expand: int = 0, parent_cache: dict[str, str | None] | None = None,
) -> tuple[str, int | None] | None:
    """Whole-line (grep-style) snippet for a content-ranked hit, via the body
    ladder (memory body → parent doc/section → tldr). `expand` adds that many
    context lines around the match. Returns `(snippet, line)` where `line` is
    the 1-based source line for a CODE file hit (a `path:line` jump target) and
    None for body/tldr hits that aren't a file line. None when no term occurs in
    any text."""
    q = " ".join(terms)
    texts: list[str] = []
    if ent.kind == "memory":
        try:
            m = s.get_memory(ent.id)
        except Exception:
            m = None
        if m and m.get("content"):
            texts.append(m["content"])
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
            sec = _section_text(body, anchor_id)
            if sec:
                texts.append(sec)
            texts.append(body)
    # Code hit: read the real source file so the whole matched line AND the
    # `--expand N` context lines come from disk (grep -C), not the one-line
    # `tldr` label — which has nothing to expand into. A code entity IS its
    # definition, so anchor the window on the symbol's def line (most relevant
    # for a function-level hit); fall back to the first query-term occurrence
    # (plain grep) when no def line is found. Size-guarded; a missing/oversized
    # file falls through to the tldr below.
    if ent.kind == "code" and ent.path:
        file_text = _read_source(ent.path)
        if file_text:
            for symbol in _symbol_candidates(ent):
                snip, ln = kwic_def_line(file_text, q, symbol, expand=expand,
                                         with_line=True)
                if snip:
                    return snip, (ln + 1 if ln is not None else None)
            snip, ln = kwic_line(file_text, q, expand=expand, with_line=True)
            if snip:
                return snip, (ln + 1 if ln is not None else None)
    if ent.tldr:
        texts.append(ent.tldr)
    for t in texts:
        snip = kwic_line(t, q, expand=expand)
        if snip:
            return snip, None
    return None


_MAX_SOURCE_BYTES = 1_000_000  # skip reading pathologically large source files


def _read_source(path: str) -> str | None:
    """Read a source file for snippet windowing; None on miss / oversize."""
    try:
        p = Path(path)
        if p.is_file() and p.stat().st_size <= _MAX_SOURCE_BYTES:
            return p.read_text(errors="replace")
    except OSError:
        pass
    return None


def _read_hit_lines(
    proj_root: Path, file: str | None, lines: list[int],
) -> list[tuple[int, str]]:
    """For `--hit-lines text`: `(line_no, source_text)` per hit line (1-based),
    capped at `_HIT_LINES_CAP`. A relative evidence path resolves against the
    project root. Empty list when the file is unreadable."""
    if not file or not lines:
        return []
    p = Path(file)
    if not p.is_absolute():
        p = proj_root / p
    txt = _read_source(str(p))
    if txt is None:
        return []
    src = txt.splitlines()
    return [(n, src[n - 1].rstrip())
            for n in lines[:_HIT_LINES_CAP] if 1 <= n <= len(src)]


def _symbol_candidates(ent: Entity) -> list[str]:
    """Symbol names to locate a code entity's definition by, best-first:
    the `norm_label` (e.g. ``store()`` → ``store``) then the name leaf after
    ``::`` (e.g. ``region_detection.py::fov_wedge_polygon`` → that function)."""
    out: list[str] = []
    nl = (ent.meta or {}).get("norm_label")
    if isinstance(nl, str) and nl.strip():
        out.append(nl.split("(", 1)[0].strip())
    leaf = ent.name.split("::")[-1].strip()
    if leaf:
        out.append(leaf)
    seen: set[str] = set()
    return [s for s in out if s and not (s in seen or seen.add(s))]


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


# Caller/callee edge groups are built from STATIC extraction (AST for code, a
# parse of static call sites for SQL). They cannot see calls made through
# dynamic dispatch — dynamic SQL (`EXECUTE format('… fn(…)')`), reflection,
# function pointers — so the reported set is a lower bound, never a census.
# A short `calls` list otherwise reads as authoritative; the note below is the
# honesty signal cliquedb bug #5fcfecd3862a asked for (asks #2 + #3): flag
# unresolved dynamic-SQL sites AND mark the group as non-exhaustive generally.
_STATIC_EXTRACTION_GROUPS = {"calls", "called_by"}


def _completeness_note(b: ContextBundle, ln: str) -> str | None:
    """Non-census caveat for a static-extraction edge group, or None. Wording
    is SQL-specific when the anchor/neighbors live in `.sql` (ask #2), else the
    general dynamic-dispatch caveat (ask #3)."""
    if ln not in _STATIC_EXTRACTION_GROUPS or not b.groups.get(ln):
        return None
    paths = [b.anchor.path if b.anchor else None]
    paths += [e.file or e.entity.path for e in b.groups.get(ln, [])]
    is_sql = any((p or "").endswith(".sql") for p in paths)
    dyn = (
        "dynamic SQL (`EXECUTE format(...)`) call sites"
        if is_sql
        else "dynamic-dispatch call sites (reflection, function pointers)"
    )
    return (
        f"[completeness: static-extraction only — {dyn} are not resolved; "
        f"treat as a lower bound, not a census]"
    )


def _single_location(e: ContextEntry) -> str | None:
    """The `path:line` jump target for an entry (default `first` mode). A code
    CONTENT hit points at its own def line; a graph/mention entry points at the
    evidence `file:line` (first occurrence)."""
    if e.linkage == "content":
        if e.entity.kind == "code" and e.entity.path:
            return f"{e.entity.path}:{e.line}" if e.line is not None \
                else e.entity.path
        return None
    if e.file and e.line is not None:
        return f"{e.file}:{e.line}"
    if e.entity.path:
        return f"{e.entity.path}:{e.line}" if e.line is not None \
            else e.entity.path
    return None


def _location_block(e: ContextEntry) -> tuple[list[str], bool]:
    """Indented location/hit-line lines to print, plus whether the KWIC snippet
    should still follow. `--hit-lines text` → grep -n block (snippet redundant);
    `nums` → compact `file:l1,l2,l3`; otherwise a single `file:line`."""
    # text: the hit lines ARE the content.
    if e.hit_lines:
        loc = e.file or (e.entity.path or "")
        block = [f"    {loc}"] if loc else []
        block += [f"      {n}: {txt}" for n, txt in e.hit_lines]
        extra = len(e.lines or []) - len(e.hit_lines)
        if extra > 0:
            block.append(f"      (+{extra} more)")
        return block, False
    # nums: every hit line number, compact.
    if e.lines and len(e.lines) > 1:
        loc = e.file or e.entity.path
        if loc:
            shown = e.lines[:_HIT_LINES_CAP]
            nums = ",".join(str(n) for n in shown)
            more = len(e.lines) - len(shown)
            if more > 0:
                nums += f"(+{more})"
            return [f"    {loc}:{nums}"], True
    # first / fallback: a single jump target.
    loc = _single_location(e)
    return ([f"    {loc}"] if loc else []), True


def _render_entry(e: ContextEntry) -> str:
    line = f"  {e.entity.name}  [{e.entity.kind}]"
    if e.weight is not None:
        line += f"  (w={e.weight:g})"
    parts, show_snippet = _location_block(e)
    # text mode: location + hit lines are the whole payload.
    if e.hit_lines:
        line += "\n" + "\n".join(parts)
        return line
    # A KWIC snippet is the payload — show it (led by the location) and skip the
    # whole-section tldr that would otherwise follow.
    if e.snippet and show_snippet:
        parts += [f"    {ln}" for ln in e.snippet.splitlines()]
        line += "\n" + "\n".join(parts)
        return line
    # No snippet: location (if any) + tldr/body fallbacks.
    if e.entity.tldr:
        tldr = e.entity.tldr
        # A co-mention node with no KWIC hit: the term isn't in its body, so
        # the multi-line section summary is noise — show only its first line
        # as a label. (Definitional linkages keep the full tldr.)
        if e.linkage in _KWIC_LINKAGES:
            tldr = tldr.splitlines()[0] if tldr.strip() else tldr
        parts.append(f"    {tldr}")
    if e.body:
        parts += [f"    {ln}" for ln in e.body.splitlines()]
    if parts:
        line += "\n" + "\n".join(parts)
    return line


def _helix_flush(b: ContextBundle) -> None:
    if b.helix_pending and b.store_root:
        try:
            from refmatrix import helix
            helix.flush(Path(b.store_root), b.helix_pending)
        except Exception:
            pass


def render_text(b: ContextBundle) -> str:
    _helix_flush(b)
    lines = [_render_header(b)]
    a = b.anchor
    if a is not None:
        lines.append(f"anchor: {a.name}  [{a.kind}]")
        if a.tldr:
            lines.append(f"  {a.tldr}")
        if b.helix_note:
            lines.append(b.helix_note)
        for _n in b.helix_neighbor_notes:
            lines.append(_n)
        if b.anchor_body:
            lines.append("")
            lines.append("--- body ---")
            lines.append(b.anchor_body)
    elif not b.groups:
        # No graph anchor AND no content hits — truly nothing to show.
        lines.append("(unknown symbol)")
        return "\n".join(lines)
    else:
        # Anchor-less content bundle: stale-neighbor notes still render
        # (the NL path is part of the readership instrument too).
        for _n in b.helix_neighbor_notes:
            lines.append(_n)
    if not b.groups:
        lines.append("")
        lines.append("(no linkages found — try `rmx link` or `rmx ingest --semantic`)")
        return "\n".join(lines)
    for ln, entries in b.groups.items():
        lines.append("")
        lines.append(f"{LINKAGE_LABELS.get(ln, ln.upper())} ({ln}):")
        for e in entries:
            lines.append(_render_entry(e))
        note = _completeness_note(b, ln)
        if note:
            lines.append(f"  {note}")
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
    _helix_flush(b)
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
                        "lines": e.lines,
                        "hit_lines": e.hit_lines,
                    }
                    for e in entries
                ]
                for ln, entries in b.groups.items()
            },
            "group_notes": {
                ln: note
                for ln in b.groups
                if (note := _completeness_note(b, ln))
            },
            "truncated": b.truncated,
            "estimated_tokens": b.estimated_tokens,
            "total_neighbors": b.total_entities(),
            # Helix staleness signal must survive the JSON surface too — MCP
            # callers request format=json, and dropping these made the whole
            # phase-1 instrument text-render-only (parity audit 2026-09-06).
            "helix_note": b.helix_note,
            "helix_neighbor_notes": b.helix_neighbor_notes,
        },
        indent=2,
    )
