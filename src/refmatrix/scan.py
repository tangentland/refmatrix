"""
`rmx scan-prompt` — dynamic context for `UserPromptSubmit` hooks.

Reads a prompt (stdin or argv), tokenizes it, matches tokens against the
concept set, and emits a token-budgeted concatenation of `rmx context`
bundles for the top-K matches. Exit code 0 always so the hook never blocks
the user prompt.
"""
from __future__ import annotations

import json
import re
import sys

from refmatrix.context import (
    build_context, content_only_bundle, render_json, render_text,
)
from refmatrix.store import Store


# Tokenization: identifier-shaped runs only. Skip pure-English noise.
_IDENT_RE = re.compile(r"[A-Za-z_][\w\-./]*(?:::[\w\-./]+)*")

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


def match_concepts(
    s: Store,
    candidates: list[str],
    *,
    exclude_namespaces: tuple[str, ...] = ("keyword",),
    case_insensitive: bool = True,
    include_noise: bool = False,
) -> list[str]:
    """Resolve candidate tokens to concept names that exist in the index.

    Tries, in order:
    1. exact bare-name match
    2. case-insensitive bare-name match
    3. namespaced suffix match — `tree_sitter` matches `import/tree_sitter`
       (excluding namespaces in `exclude_namespaces`)
    """
    excluded = set(exclude_namespaces)
    out: list[str] = []
    seen: set[str] = set()
    con = s._connect()
    noise_clause = "" if include_noise else " AND noise=0"

    def consider(name: str) -> None:
        if name in seen:
            return
        ns = name.split("/", 1)[0] if "/" in name else None
        if ns and ns in excluded:
            return
        seen.add(name)
        out.append(name)

    for cand in candidates:
        # Drop function words before they can match junk concepts in the
        # graph (THE / Does / How). Content words pass through untouched.
        if cand.lower() in _PROMPT_STOPWORDS:
            continue
        # exact (case-preserving)
        e = s.resolve_entity(cand)
        if e is not None and e.kind == "concept" and (include_noise or not e.noise):
            consider(e.name)
            continue
        if case_insensitive:
            row = con.execute(
                f"SELECT name FROM entities WHERE kind='concept'{noise_clause} "
                "AND lower(name) = lower(?) LIMIT 1",
                (cand,),
            ).fetchone()
            if row:
                consider(row[0])
                continue
        # namespaced suffix: match anything */<cand>
        rows = con.execute(
            f"SELECT name FROM entities WHERE kind='concept'{noise_clause} "
            "AND name LIKE ?",
            (f"%/{cand}",),
        ).fetchall()
        for r in rows:
            consider(r[0])
    return out


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
) -> str:
    cands = extract_candidates(prompt)
    matches = match_concepts(
        s, cands,
        exclude_namespaces=exclude_namespaces,
        include_noise=include_noise,
    )
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
