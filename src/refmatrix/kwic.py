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
