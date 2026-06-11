"""Keyword-in-context (KWIC) snippet extraction.

Shared by `rmx session recall` (a match snippet per session row) and
`rmx context` (a window around the anchor term inside each MENTIONED-IN
body). Both read surfaces previously showed a title or a whole-section
summary that frequently did not even contain the query term; KWIC shows the
actual line the term appears on — grep-quality, but windowed and centered.

Pure + presentation-neutral: the match is wrapped in `marker` sentinels the
caller can restyle or strip. No I/O, no store access.
"""
from __future__ import annotations

import re

_WORD_RE = re.compile(r"[A-Za-z0-9_]+")
_WS_RE = re.compile(r"\s+")

# Tokens shorter than this carry no signal as a KWIC anchor (BM25 still scores
# them; we just don't want to center a window on "a"/"of"). 2 keeps "id"/"ts".
_MIN_TERM = 2


def query_terms(query: str) -> list[str]:
    """Distinct lowercased word tokens (len >= _MIN_TERM), longest first so the
    most specific term wins when several occur at the same position."""
    seen: set[str] = set()
    out: list[str] = []
    for tok in _WORD_RE.findall(query.lower()):
        if len(tok) >= _MIN_TERM and tok not in seen:
            seen.add(tok)
            out.append(tok)
    out.sort(key=len, reverse=True)
    return out


def _first_hit(low: str, terms: list[str]) -> tuple[int, int] | None:
    """Earliest occurrence of any term in `low`. Ties resolve toward the
    longer term because `terms` is ordered longest-first."""
    best: tuple[int, int] | None = None
    for t in terms:
        i = low.find(t)
        if i == -1:
            continue
        if best is None or i < best[0]:
            best = (i, i + len(t))
    return best


def kwic_one(
    text: str | None,
    query: str | None,
    *,
    width: int = 100,
    marker: tuple[str, str] = ("«", "»"),
    ellipsis: str = "…",
) -> str:
    """Return a single ~`width`-char window of `text` centered on the first
    occurrence of any `query` term, with the match wrapped in `marker` and a
    leading/trailing `ellipsis` when the window is truncated. Whitespace is
    collapsed to single spaces.

    Returns "" when there is no text, no query, or no term occurs — callers
    fall back to their existing summary in that case."""
    if not text or not query:
        return ""
    norm = _WS_RE.sub(" ", text).strip()
    if not norm:
        return ""
    low = norm.lower()
    hit = _first_hit(low, query_terms(query))
    if hit is None:
        return ""
    s, e = hit
    pad = max(0, (width - (e - s)) // 2)
    start = max(0, s - pad)
    end = min(len(norm), e + pad)
    # Snap to word edges so we don't slice mid-token on either side.
    if start > 0:
        nb = norm.find(" ", start, e)
        if nb != -1:
            start = nb + 1
    if end < len(norm):
        nb = norm.rfind(" ", e, end)
        if nb != -1 and nb > e:
            end = nb
    seg = norm[start:end]
    ms, me = s - start, e - start
    seg = seg[:ms] + marker[0] + seg[ms:me] + marker[1] + seg[me:]
    pre = ellipsis if start > 0 else ""
    post = ellipsis if end < len(norm) else ""
    return pre + seg + post


def kwic_line(
    text: str | None,
    query: str | None,
    *,
    expand: int = 0,
    max_chars: int = 240,
    marker: tuple[str, str] = ("«", "»"),
    ellipsis: str = "…",
) -> str:
    """Return the whole LINE containing the first occurrence of any `query`
    term (grep-style, not a centered window), with the match wrapped in
    `marker`. `expand > 0` adds that many context lines before AND after the
    match (like `grep -C`), preserving indentation. A match line longer than
    `max_chars` is capped around the match with ellipsis. "" when no term hits."""
    if not text or not query:
        return ""
    terms = query_terms(query)
    if not terms:
        return ""
    lines = [ln.rstrip() for ln in text.splitlines()]
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        hit = _first_hit(line.lower(), terms)
        if hit is None:
            continue
        s, e = hit
        if len(line) <= max_chars:
            marked = line[:s] + marker[0] + line[s:e] + marker[1] + line[e:]
        else:  # cap a very long match line around the hit
            half = max_chars // 2
            start = max(0, s - half)
            end = min(len(line), e + half)
            ms, me = s - start, e - start
            seg = line[start:end]
            seg = seg[:ms] + marker[0] + seg[ms:me] + marker[1] + seg[me:]
            marked = ((ellipsis if start > 0 else "") + seg
                      + (ellipsis if end < len(line) else ""))
        if expand <= 0:
            return marked.strip()
        lo, hi = max(0, i - expand), min(len(lines), i + expand + 1)
        out = [(marked if j == i else lines[j]) for j in range(lo, hi)]
        while out and not out[0].strip():   # trim blank context edges
            out.pop(0)
        while out and not out[-1].strip():
            out.pop()
        return "\n".join(out)
    return ""
