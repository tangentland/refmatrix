"""
`rmx scan-prompt` — dynamic context for `UserPromptSubmit` hooks.

Reads a prompt (stdin or argv), tokenizes it, matches tokens against the
concept set, and emits a token-budgeted concatenation of `rmx context`
bundles for the top-K matches. Exit code 0 always so the hook never blocks
the user prompt.
"""
from __future__ import annotations

import json
import math
import os
import re
import sys

from refmatrix.terms import STOPWORDS as _STOPWORDS
from pathlib import Path

from refmatrix.context import (
    build_context, content_only_bundle, render_json, render_text,
)
from refmatrix.store import Store


# Tokenization: identifier-shaped runs only. Skip pure-English noise.
_IDENT_RE = re.compile(r"[A-Za-z_][\w\-./]*(?:::[\w\-./]+)*")

# Minimum `_salience` a PLAIN lowercase word (shape-score 0, not namespaced)
# must reach to earn a context bundle in the always-on scan-prompt hook, once
# PageRank has been computed. Calibrated on the live refmatrix graph: central
# domain concepts (`entity`≈1.62, `store`≈2.74, `memory`≈2.71) clear it;
# code-mentioned common-English words (`keep`≈1.53, `selection`≈1.19,
# `lower`≈1.21, `send`≈1.11) fall below. Shaped / namespaced tokens bypass this
# floor entirely — they are cited symbols, not prose.
SHAPE0_SALIENCE_FLOOR = 1.55

# Function words that are never useful concept anchors. The graph sometimes
# carries junk concepts for them (`THE`, `Does`, `How` from capitalized-word /
# acronym extraction, noise=0); without this guard a prompt like "how does the
# camera work" emits bundles for `the`/`does`/`how` and crowds out the real
# concepts. Deliberately function-words-ONLY (articles, prepositions,
# conjunctions, pronouns, interrogatives, auxiliaries/copula). Content words —
# `user`, `get`, `make`, `use`, `work`, `show`, `go`, ... — are NOT here: they
# can be legit domain concepts / method names and must stay matchable.
# Canonical home is `terms.STOPWORDS`. Re-exported under the historical
# name because consolidate.py, stm.py and context.py import it from here.
_PROMPT_STOPWORDS = _STOPWORDS


def extract_candidates(text: str) -> list[str]:
    """Return distinct identifier-shaped tokens from a prompt, in first-seen order."""
    seen: set[str] = set()
    out: list[str] = []
    for m in _IDENT_RE.finditer(text):
        tok = m.group(0)
        if tok in seen:
            continue
        seen.add(tok)
        out.append(tok)
    return out


def _token_shape_score(token: str) -> float:
    """Reward identifier-shaped tokens, penalize plain dictionary words.

    `MCP` (acronym), `KeyError` (CamelCase), `scan_prompt` (snake),
    `a.b::c` (qualified) look like code the author cited deliberately;
    `first` / `call` / `results` / `query` are bare lowercase English
    words that merely happen to exist as degree-0 concepts. Shape alone
    separates the two without a hand-maintained blocklist."""
    leaf = token.rsplit("/", 1)[-1].rsplit("::", 1)[-1]
    score = 0.0
    has_upper = any(c.isupper() for c in leaf)
    has_lower = any(c.islower() for c in leaf)
    if has_upper and has_lower:
        score += 1.0                       # CamelCase / mixedCase
    if leaf.isupper() and len(leaf) >= 2:
        score += 1.0                       # acronym (MCP, API, RPC)
    if "_" in leaf or "." in leaf or "::" in token or "-" in leaf:
        score += 1.0                       # compound identifier
    if any(c.isdigit() for c in leaf):
        score += 0.5
    if len(leaf) >= 12:
        score += 0.5                       # long token ≠ plain word
    return score


def _concept_signal(s: Store, con, name: str) -> tuple[int | None, int, int]:
    """`(concept_id, linkage_degree, mention_doc_freq)` for a concept name.

    Single source of truth for the graph signals that feed both the
    unlinked-plain-word gate and the salience score, so `match_concepts`
    queries each matched concept once. All-zero / `None` on any lookup
    failure so callers degrade gracefully."""
    cid = None
    try:
        row = con.execute(
            "SELECT id FROM entities WHERE kind='concept' AND name=? LIMIT 1",
            (name,),
        ).fetchone()
        if row:
            cid = row[0]
    except Exception:
        cid = None
    deg = 0
    df = 0
    if cid is not None:
        try:
            r = con.execute(
                "SELECT COUNT(*) FROM entity_links WHERE concept_id=?", (cid,),
            ).fetchone()
            deg = int(r[0]) if r else 0
        except Exception:
            deg = 0
        try:
            df = len(s.load_bitmap("mentions", cid))
        except Exception:
            df = 0
    return cid, deg, df


def _is_unlinked_plain(token: str, deg: int) -> bool:
    """True when a matched concept is a degree-0 node whose citing token is a
    plain lowercase word — indistinguishable from an accidental prose-word
    extraction (`meaningful`, `selection`, `keep`, `send`, `note`, `lower`,
    `start`), and whose context bundle is empty anyway. The always-on
    scan-prompt hook drops these so the token budget lands on real symbols.

    NOT dropped: linked concepts (`deg > 0` → a real domain concept, even a
    plain-word one like `user`/`camera` that is mentioned in code), and
    identifier-shaped tokens the author cited deliberately (`max_tokens`,
    `scan-prompt`, `adr-0036`, `p20`) which keep `_token_shape_score > 0`
    even at degree 0."""
    return deg == 0 and _token_shape_score(token) == 0.0


def _salience(
    s: Store, name: str, token: str, cid: int | None, deg: int, df: int,
    *, pr_computed: bool = False,
) -> float:
    """Rank score for a matched concept. Higher = more worth surfacing in
    the always-on scan-prompt hook. Combines graph signal (linkage degree),
    specificity (inverse mention frequency = idf), token shape, and a small
    namespaced-concept bonus. Demote-only: weak matches sort last and fall
    off the per-prompt budget rather than being hard-dropped. Graph signals
    (`cid`/`deg`/`df`) are precomputed by `_concept_signal`; `pr_computed` is
    `pagerank.has_scores(s)`, hoisted out of the per-concept loop."""
    idf = 1.0 / math.log2(df + 2) if df > 0 else 0.3
    # Centrality prior: the global PageRank ratio (avg node ≈ 1.0) when it has
    # been computed (`rmx pagerank`), log-compressed and capped so a mega-hub
    # can't swamp the other signals.
    from refmatrix import pagerank as pr_mod
    pr = pr_mod.get_score(s, cid) if cid is not None else None
    if pr is not None and pr > 0:
        central = min(2.5, 0.8 * math.log2(pr + 1.0))
    elif pr_computed:
        # PageRank ran but this concept is absent/zero — genuinely peripheral
        # (or created after the last `rmx pagerank`). Give only a tiny
        # degree-derived nudge, NOT the fresh-store flat prior below: a plain
        # word like `meaningful` (deg 5, unscored) must not inflate to
        # hub-level and outrank real domain concepts.
        central = 0.1 * min(deg, 10)
    else:
        # No PageRank table at all — a fresh store. Fall back to raw linkage
        # degree so it still ranks sensibly before the first `rmx pagerank`.
        central = (2.0 + 0.1 * min(deg, 10)) if deg > 0 else 0.0
    ns_bonus = 0.5 if "/" in name else 0.0
    return central + 1.5 * idf + _token_shape_score(token) + ns_bonus


# Salience bump for an STM seed that carries a body. Small — it reorders
# among survivors of the gate, it does not rescue a node the gate rejected.
_STM_BODY_BONUS = 0.5


def _variant_expansion() -> bool:
    """Canonical-variant expansion in `match_concepts`. On by default; set
    RMX_SCAN_VARIANTS=0 to restore exact-name-only resolution (the pre-fix
    behavior) for an A/B. Read per call, not at import, so the eval harness
    can flip it without a fresh interpreter."""
    return os.environ.get("RMX_SCAN_VARIANTS", "1") not in ("0", "false", "False")


def match_concepts(
    s: Store,
    candidates: list[str],
    *,
    exclude_namespaces: tuple[str, ...] = ("keyword",),
    case_insensitive: bool = True,
    include_noise: bool = False,
    drop_unlinked_plain: bool = True,
) -> list[str]:
    """Resolve candidate tokens to concept names that exist in the index,
    salience-ranked (most-informative first).

    Resolution per candidate, in order:
    1. exact bare-name match
    2. case-insensitive bare-name match
    3. namespaced suffix match — `tree_sitter` matches `import/tree_sitter`
       (excluding namespaces in `exclude_namespaces`)

    Survivors of the unlinked-plain-word gate (`drop_unlinked_plain`, see
    `_is_unlinked_plain`) are then ranked by `_salience` so the always-on
    scan-prompt hook spends its small budget on the concepts the prompt
    actually cared about, not on the first lowercase dictionary word that
    happened to be registered. Order is salience desc, first-seen as the
    stable tie-break. Set `drop_unlinked_plain=False` to keep every resolved
    match (demote-only, pre-gate behavior)."""
    excluded = set(exclude_namespaces)
    found: list[tuple[str, str]] = []   # (concept name, source token)
    seen: set[str] = set()
    con = s._connect()
    noise_clause = "" if include_noise else " AND noise=0"

    def consider(name: str, token: str) -> None:
        if name in seen:
            return
        ns = name.split("/", 1)[0] if "/" in name else None
        if ns and ns in excluded:
            return
        seen.add(name)
        found.append((name, token))

    for cand in candidates:
        # Drop function words before they can match junk concepts in the
        # graph (THE / Does / How). Content words pass through untouched.
        if cand.lower() in _PROMPT_STOPWORDS:
            continue
        # exact (case-preserving)
        e = s.resolve_entity(cand)
        if e is not None and e.kind == "concept" and (include_noise or not e.noise):
            consider(e.name, cand)
            continue
        if case_insensitive:
            row = con.execute(
                f"SELECT name FROM entities WHERE kind='concept'{noise_clause} "
                "AND lower(name) = lower(?) LIMIT 1",
                (cand,),
            ).fetchone()
            if row:
                consider(row[0], cand)
                continue
        # Canonical-form expansion. `resolve_concept_ids` matches on
        # `canonical_name`, folding camelCase / PascalCase-with-acronym /
        # dash / space / digit-boundary variants into one indexed lookup.
        # store.py documents it as "used by the query/context/neighbors path
        # so an LLM passing any surface form lands on the same set" — but
        # scan-prompt, the always-on hook, resolved by exact name only and so
        # was the ONE read surface that missed every variant. `parse_url` in a
        # prompt did not find `parseURL` in the graph.
        if _variant_expansion():
            try:
                ids = s.resolve_concept_ids(cand)
            except Exception:
                ids = []
            if ids:
                in_list = ",".join("?" * len(ids))
                rows = con.execute(
                    f"SELECT name FROM entities WHERE id IN ({in_list})"
                    f"{noise_clause}",
                    list(ids),
                ).fetchall()
                if rows:
                    for r in rows:
                        consider(r[0], cand)
                    continue
        # namespaced suffix: match anything */<cand>
        rows = con.execute(
            f"SELECT name FROM entities WHERE kind='concept'{noise_clause} "
            "AND name LIKE ?",
            (f"%/{cand}",),
        ).fetchall()
        for r in rows:
            consider(r[0], cand)

    # Gate then rank. Query each matched concept's graph signal once
    # (`_concept_signal`) and reuse it for both the unlinked-plain-word gate
    # and the salience score. Stable sort: equal scores keep first-seen order;
    # negate the score for descending without disturbing the index tie-break.
    from refmatrix import pagerank as pr_mod
    pr_computed = pr_mod.has_scores(s)
    scored: list[tuple[int, str, float]] = []
    for idx, (name, token) in enumerate(found):
        cid, deg, df = _concept_signal(s, con, name)
        if drop_unlinked_plain and _is_unlinked_plain(token, deg):
            continue
        sal = _salience(s, name, token, cid, deg, df, pr_computed=pr_computed)
        # Shape-0 salience floor: a plain lowercase word (no identifier shape,
        # not namespaced) must clear SHAPE0_SALIENCE_FLOOR to earn a bundle in
        # the always-on hook. Kills common-English hapaxes that happen to be
        # code-mentioned (`selection`, `lower`, `thing`, `going`) — degree>0
        # so the unlinked-plain gate above misses them — while central domain
        # concepts (`store`, `memory`, `concept`, `entity`) clear it and every
        # identifier-shaped / namespaced token is exempt. Only applied once
        # PageRank exists, so a fresh store (flat central prior) keeps all.
        if (drop_unlinked_plain and pr_computed
                and "/" not in name and _token_shape_score(token) == 0.0
                and sal < SHAPE0_SALIENCE_FLOOR):
            continue
        scored.append((idx, name, sal))
    ranked = sorted(scored, key=lambda it: (-it[2], it[0]))
    return [name for _idx, name, _sc in ranked]


def _clique_weight() -> float:
    """Weight of the artificial edges linking the prompt's own concepts to
    each other before the PPR walk. 0 = off (plain joint seeding).

    Default 2.0, matching `build_adjacency`'s `link_weight`. It ships ON only
    in company: measured alone it makes things WORSE (concept-path hit@20
    0.200 -> 0.178), because a junk seed that survives the salience gate gets
    a path into every other seed's neighborhood. Coverage is the corrective —
    with both on the same walk goes to 0.222, and with variant expansion too,
    0.267. Turning coverage off while leaving this on reproduces the
    regression, so the two move together."""
    try:
        return float(os.environ.get("RMX_SCAN_CLIQUE_W", "2.0") or "2.0")
    except ValueError:
        return 0.0


def _coverage_alpha() -> float:
    """Exponent on per-seed prompt-coverage when ordering concepts. 0 = off.

    The same lever `content_rank` uses at alpha=3 for entities, where it was
    the biggest single win in the CSN scoring stack. Applied to concept
    SELECTION here, which never had it. Default 3 to match content_rank;
    measured identical at alpha=1, so the exponent is not sensitive on this
    corpus and the shared constant is the better default."""
    try:
        return float(os.environ.get("RMX_SCAN_COVERAGE_ALPHA", "3") or "3")
    except ValueError:
        return 0.0


def _stm_seed_ids(s: Store, root, *, max_seeds: int = 8) -> list[int]:
    """Concept ids for the session's current focus, as extra walk seeds.

    The STM focus graph is already maintained per session and already
    rendered into the prompt as a topic composite. Using it as a RETRIEVAL
    seed is different: it conditions what the graph walk explores on what the
    session is actually about, which is the one input in the enrichment chain
    that adds information rather than rearranging what the prompt already
    said. A three-word prompt in a long session is exactly the case the rest
    of the pipeline cannot help with.

    Best-effort: no STM, no session, unresolvable names -> no extra seeds.
    """
    if root is None:
        return []
    try:
        from pathlib import Path as _P

        from refmatrix.stm import Stm, latest_session
        root = _P(root)
        session = latest_session(root)
        if not session:
            return []
        graph = Stm(root, session=session).focus_graph(top=30)
    except Exception:
        return []
    # Gate them the same way prompt tokens are gated. `_stm_seed_ids` used to
    # resolve every focus-graph name straight through, which put discourse
    # vocabulary into the core: measured live mid-session, the top five STM
    # seeds were `multiple`, `cross`, `terms`, `prompt`, `link` — the words of
    # a conversation ABOUT retrieval, not the domain. Seeding a graph walk with
    # those spends the walk on nothing.
    #
    # The gate is applied directly on the resolved concept rather than through
    # `match_concepts`, whose resolution ladder ends in a leading-wildcard LIKE
    # (a full concept-table scan per name). Thirty of those per prompt is not
    # something an always-on hook can pay for.
    from refmatrix import pagerank as pr_mod
    con = s._connect()
    pr_computed = pr_mod.has_scores(s)
    scored: list[tuple[float, int, int]] = []
    seen: set[int] = set()
    for idx, nd in enumerate(graph.get("nodes") or []):
        name = (nd.get("name") or "").split("#", 1)[0]
        if not name or name.lower() in _PROMPT_STOPWORDS:
            continue
        try:
            cids = s.resolve_concept_ids(name)
        except Exception:
            continue
        for cid in cids:
            if cid in seen:
                continue
            seen.add(cid)
            row = con.execute(
                "SELECT name FROM entities WHERE id = ?", (cid,)).fetchone()
            if row is None:
                continue
            cname = row[0]
            _cid, deg, df = _concept_signal(s, con, cname)
            if _is_unlinked_plain(name, deg):
                continue
            sal = _salience(s, cname, name, cid, deg, df,
                            pr_computed=pr_computed)
            if (pr_computed and "/" not in cname
                    and _token_shape_score(name) == 0.0
                    and sal < SHAPE0_SALIENCE_FLOOR):
                continue
            # Prefer a node that can actually carry the tldr expansion. A bare
            # concept has no body, so it contributes edges but nothing for
            # `net._body_expansion` to work with.
            body = con.execute(
                "SELECT length(coalesce(tldr,'')) FROM entities WHERE id = ?",
                (cid,)).fetchone()
            if body and body[0]:
                sal += _STM_BODY_BONUS
            scored.append((sal, idx, cid))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [cid for _sal, _idx, cid in scored[:max_seeds]]


def _enrich_rerank(
    s: Store, matches: list[str], *, max_concepts: int, root=None,
) -> list[str]:
    """Full-enrichment ranking: canonical-expanded seeds (+ STM focus) walked
    to degree 2, coalesced by how many seeds reach each node, then ranked.

    Falls back to the salience order on any failure — same contract as
    `_ppr_rerank`, because the always-on hook must never go dark."""
    from refmatrix import enrich as enrich_mod

    seed_ids: list[int] = []
    for name in matches:
        e = s.resolve_entity(name)
        if e is not None and e.kind == "concept":
            seed_ids.append(e.id)
    if not seed_ids:
        return matches
    try:
        ranked = enrich_mod.enrich_concepts(
            s, seed_ids, k=max_concepts, kinds=("concept",),
            include_seeds=True,
            hops=_enrich_hops(),
            stm_seed_ids=_stm_seed_ids(s, root) if _enrich_stm() else None,
            clique_weight=_clique_weight(),
        )
    except Exception:
        return matches
    names = [r["name"] for r in ranked]
    for name in matches:
        if name not in names:
            names.append(name)
    return names


def _net_rerank(
    s: Store, matches: list[str], *, max_concepts: int, root=None,
) -> list[str]:
    """Core clique -> tldr expansion -> corroboration cull -> ranked concepts.

    STM focus joins the core unconditionally here (not only under a flag):
    it is what gives a one-term prompt a core large enough for the
    `>1 edge` cull to mean anything. Falls back to the PPR order when the net
    comes back empty — a short prompt in a fresh session with no STM is
    exactly that case, and the always-on hook must not go dark."""
    from refmatrix import net as net_mod

    seed_ids: list[int] = []
    for name in matches:
        e = s.resolve_entity(name)
        if e is not None and e.kind == "concept":
            seed_ids.append(e.id)
    if not seed_ids:
        return matches
    try:
        ranked = net_mod.net_concepts(
            s, seed_ids, k=max_concepts, kinds=("concept",),
            include_seeds=True,
            stm_seed_ids=_stm_seed_ids(s, root),
            min_support=_net_min_support(),
            use_bodies=_net_use_bodies(),
        )
    except Exception:
        return _ppr_rerank(s, matches, max_concepts=max_concepts)
    corroborated = [r for r in ranked if r.get("support", 0) > 0]
    if not corroborated:
        # Empty net: nothing was reached by more than one core member.
        return _ppr_rerank(s, matches, max_concepts=max_concepts)
    names = [r["name"] for r in ranked]
    for name in matches:
        if name not in names:
            names.append(name)
    return names


def _net_min_support() -> int:
    """Core members that must independently reach a node for it to join the
    net. 2 is corroboration; 1 would be no cull at all."""
    try:
        return max(1, int(os.environ.get("RMX_SCAN_NET_SUPPORT", "2") or "2"))
    except ValueError:
        return 2


def _net_use_bodies() -> bool:
    """Expand the core through `tldr` bodies as well as graph edges."""
    return os.environ.get("RMX_SCAN_NET_BODIES", "1") not in (
        "0", "false", "False")


def _enrich_hops() -> int:
    try:
        return max(1, int(os.environ.get("RMX_SCAN_ENRICH_HOPS", "2") or "2"))
    except ValueError:
        return 2


def _enrich_stm() -> bool:
    """Merge STM focus into the walk seeds. On by default under `--rank
    enrich`; note that an independent-question benchmark cannot measure it,
    since there is no session to condition on."""
    return os.environ.get("RMX_SCAN_ENRICH_STM", "1") not in ("0", "false", "False")


def _ppr_rerank(
    s: Store, matches: list[str], *, max_concepts: int,
) -> list[str]:
    """Seed local-push PPR on the matched concepts and return a concept list
    re-ranked by PPR mass — seeds plus the most strongly related concepts the
    prompt never named. Falls back to the salience order on any failure so the
    always-on hook can never go dark."""
    from refmatrix import ppr as ppr_mod
    seed_ids: list[int] = []
    for name in matches:
        e = s.resolve_entity(name)
        if e is not None and e.kind == "concept":
            seed_ids.append(e.id)
    if not seed_ids:
        return matches
    try:
        ranked = ppr_mod.rank_related_for_prompt(
            s, seed_ids, k=max_concepts, kinds=("concept",),
            include_seeds=True,
            clique_weight=_clique_weight(),
            coverage_alpha=_coverage_alpha(),
        )
    except Exception:
        return matches
    names = [r["name"] for r in ranked]
    # Guarantee seeds survive even if the walk surfaced unrelated hubs: append
    # any matched concept the PPR top-k dropped, preserving salience order.
    for name in matches:
        if name not in names:
            names.append(name)
    return names


def scan_prompt(
    s: Store,
    prompt: str,
    *,
    max_tokens: int = 2000,
    per_concept_tokens: int = 600,
    max_concepts: int = 5,
    exclude_namespaces: tuple[str, ...] = ("keyword",),
    fmt: str = "text",
    include_noise: bool = False,
    rank: str = "ppr",
    composite: bool = False,
    composite_root: "str | Path | None" = None,
    composite_k: int = 3,
    composite_expand: bool = True,
    composite_max_tokens: int = 1200,
    composite_every: int = 1,
    composite_intra_edges: int = 3,
    content: bool = True,
    content_tokens: int = 600,
) -> str:
    """Emit context bundles for a prompt's symbols. When `composite` is set (and
    `composite_root` names the project `.refmatrix` dir), ALSO append a GMD
    topic-composite subgraph of the session's current focus — a running
    aggregate of every prompt+result — budgeted SEPARATELY by
    `composite_max_tokens`, independent of `max_tokens`. Text mode only; JSON
    output is unchanged."""

    def _compose(sym_text: str) -> str:
        if not composite or composite_root is None or fmt == "json":
            return sym_text
        try:
            from .composite import build_topic_composite
            comp = build_topic_composite(
                s, composite_root, k=composite_k,
                expand=composite_expand, max_tokens=composite_max_tokens,
                every=composite_every, intra_edges=composite_intra_edges)
        except Exception:
            comp = ""
        if not comp:
            return sym_text
        return (sym_text + "\n\n" + comp) if sym_text else comp

    cands = extract_candidates(prompt)
    matches = match_concepts(
        s, cands,
        exclude_namespaces=exclude_namespaces,
        include_noise=include_noise,
    )
    if matches and rank == "ppr":
        matches = _ppr_rerank(s, matches, max_concepts=max_concepts)
    elif matches and rank == "enrich":
        matches = _enrich_rerank(
            s, matches, max_concepts=max_concepts, root=composite_root)
    elif matches and rank == "net":
        matches = _net_rerank(
            s, matches, max_concepts=max_concepts, root=composite_root)
    matches = matches[:max_concepts]

    # ---- content-ranked view over the WHOLE candidate bag ------------------
    # The per-concept bundles below answer "what neighbours this term", once
    # per term, independently. That question has no notion of idf and none of
    # coverage: a bundle ranks by raw `mentions` weight (= term frequency), so
    # a COMMON prompt word with a high tf outranks a RARE one with a low tf,
    # and nothing ever prefers a document that contains several of the prompt's
    # terms over one that contains a single term many times.
    #
    # Measured on a prose corpus (eval/memaware, 90 questions): scan-prompt hit
    # @20 0.200 against 0.433 for `rmx context` over the SAME store, because
    # `vacuum` alone at tf=12 crowded out the session that actually carried
    # `sneakers` + `closet`. content_rank supplies exactly the two missing
    # terms — BM25 idf and coverage^alpha.
    #
    # This path already existed here, but only as a fallback for when NO
    # concept matched. On a corpus where every content word is a concept it
    # therefore never ran — the case that needs it most was the case that
    # could not reach it.
    #
    # grep_backstop stays OFF: scan-prompt is the always-on UserPromptSubmit
    # hook, and spawning `rg` (plus learning its hits) on every prompt would
    # tax every turn. Explicit `rmx context` carries the grep floor.
    cbundle = None
    if content and cands:
        # Shared-or-nothing reranker: `scan-prompt` is the always-on
        # UserPromptSubmit hook running in a short-lived CLI process, so it
        # uses the hub's worker if one is listening and otherwise keeps the
        # BM25 order. It must never spawn a model of its own — see
        # `reranker.shared_reranker`.
        from refmatrix.reranker import shared_reranker
        cb = content_only_bundle(
            s, " ".join(cands),
            max_tokens=content_tokens, max_entities=10,
            grep_backstop=False,
            reranker=shared_reranker(),
            # The bundle's `ref` is the candidate BAG; the reranker needs the
            # sentence the user actually typed.
            rerank_query=prompt,
        )
        if cb.groups:
            cbundle = cb

    if fmt == "json":
        out = []
        if cbundle is not None:
            out.append(json.loads(render_json(cbundle)))
        out.extend(
            json.loads(render_json(
                build_context(s, name, max_tokens=per_concept_tokens,
                              max_entities=10)))
            for name in matches
        )
        return json.dumps(out, indent=2)

    parts: list[str] = []
    used = 0
    if cbundle is not None:
        header = (f"# refmatrix content matches for prompt: "
                  f"{', '.join(cands[:8])}")
        rendered = render_text(cbundle)
        parts.append(header)
        parts.append("")
        parts.append(rendered)
        used += (len(header) + len(rendered)) // 4
    if not matches:
        return _compose("\n".join(parts))
    parts.append("")
    parts.append(
        f"# refmatrix context for prompt-mentioned symbols: {', '.join(matches)}")
    used += len(parts[-1]) // 4
    for name in matches:
        b = build_context(s, name, max_tokens=per_concept_tokens, max_entities=10)
        if b.anchor is None or not b.groups:
            continue
        rendered = render_text(b)
        cost = len(rendered) // 4
        if used + cost > max_tokens:
            parts.append("# [truncated by --max-tokens]")
            break
        parts.append("")
        parts.append(rendered)
        used += cost
    return _compose("\n".join(parts))


def read_stdin_prompt() -> str:
    """Read the user prompt from stdin.

    Claude Code's UserPromptSubmit hook receives a JSON envelope on stdin
    with a `prompt` field. We accept either the envelope or raw text and
    do the right thing.
    """
    raw = sys.stdin.read()
    if not raw.strip():
        return ""
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            for key in ("prompt", "user_prompt", "text", "message"):
                if key in data and isinstance(data[key], str):
                    return data[key]
    except json.JSONDecodeError:
        pass
    return raw
