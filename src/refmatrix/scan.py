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
import re
import sys

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
_PROMPT_STOPWORDS = frozenset({
    # articles / determiners
    "a", "an", "the", "this", "that", "these", "those",
    # conjunctions
    "and", "or", "but", "nor", "if", "so", "yet",
    # prepositions
    "of", "to", "in", "on", "at", "by", "for", "with", "from", "into",
    "onto", "off", "per", "via", "as", "about",
    # pronouns
    "i", "we", "me", "my", "us", "our", "you", "your", "he", "she", "it",
    "they", "them", "their",
    # interrogatives / relatives
    "how", "why", "who", "whom", "whose", "what", "which", "when", "where",
    "while",
    # auxiliaries / copula
    "is", "am", "are", "was", "were", "be", "been", "being",
    "do", "does", "did", "doing", "done",
    "have", "has", "had", "can", "could", "will", "would", "should",
    "shall", "may", "might", "must",
    # misc grammatical
    "not", "no", "yes", "than", "then", "such",
})


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
        ranked = ppr_mod.rank_related(
            s, seed_ids, k=max_concepts, kinds=("concept",),
            include_seeds=True)
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
) -> str:
    cands = extract_candidates(prompt)
    matches = match_concepts(
        s, cands,
        exclude_namespaces=exclude_namespaces,
        include_noise=include_noise,
    )
    if matches and rank == "ppr":
        matches = _ppr_rerank(s, matches, max_concepts=max_concepts)
    if not matches:
        # No registered concept matched the prompt. Don't go dark — fall back
        # to a content-ranked grep over the prompt's candidate terms so the
        # always-on hook still surfaces code/doc for arbitrary phrasing (the
        # strength of `rmx context "<phrase>"`, which the concept-gated path
        # otherwise withholds). Whole-line snippets only (expand=0) to bound
        # the per-prompt injected token cost.
        if not cands:
            return ""
        # grep_backstop OFF here: scan-prompt is the always-on UserPromptSubmit
        # hook — spawning `rg` (and learning) on every prompt that names no
        # concept would tax every turn. The index path stays; explicit
        # `rmx context` carries the grep floor.
        b = content_only_bundle(
            s, " ".join(cands),
            max_tokens=per_concept_tokens, max_entities=10,
            grep_backstop=False,
        )
        if not b.groups:
            return ""
        if fmt == "json":
            return json.dumps([json.loads(render_json(b))], indent=2)
        header = (f"# refmatrix content matches for prompt: "
                  f"{', '.join(cands[:8])}")
        return header + "\n\n" + render_text(b)
    matches = matches[:max_concepts]

    if fmt == "json":
        bundles = [
            build_context(s, name, max_tokens=per_concept_tokens, max_entities=10)
            for name in matches
        ]
        from refmatrix.context import render_json
        return json.dumps(
            [json.loads(render_json(b)) for b in bundles],
            indent=2,
        )

    parts: list[str] = []
    used = 0
    parts.append(f"# refmatrix context for prompt-mentioned symbols: {', '.join(matches)}")
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
    return "\n".join(parts)


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
