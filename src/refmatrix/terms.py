"""One tokenizer and one stoplist for every read surface.

`rmx context`, `rmx memory recall` and `rmx scan-prompt` all turn a string
into terms for `Store.content_rank`. They did it three different ways.

`context._ref_terms` applied the stoplist and documented exactly why:

    a prose question carrying `are`/`the`/`to` sends those to `rg` and they
    hit INSIDE unrelated words ... Observed live: context "...my old sneakers
    are still in that spot?" returned a file whose top hit was
    `tags: [memaw<are>, session]` at weight 191.

`recall._content_terms` claimed in its own docstring to mirror that function
and did not apply the stoplist at all — a copy made to avoid importing a
"context-private helper", which then drifted. So `memory recall --fuse` fed
`why`, `did`, `the`, `by` straight into BM25 as query terms.

That is the same class of bug the project already recorded once, at four call
sites. The fix is not to patch the fourth copy; it is to have one.

Note the deliberate asymmetry with `scan.extract_candidates`: that answers a
different question — which tokens look like *identifiers* worth resolving to
concept nodes — and keeps `parse_url` while discarding prose. This module
answers "which words should BM25 search for". Both apply `STOPWORDS`.
"""
from __future__ import annotations

import re

# Function words. Not a general English stoplist: these are the tokens that
# carry no retrieval signal in a prompt but are frequent enough to dominate a
# literal grep or a tf-weighted match.
STOPWORDS = frozenset({
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


def content_terms(
    text: str,
    *,
    strip_kind_prefix: bool = False,
    drop_stopwords: bool = True,
) -> list[str]:
    """Tokenize `text` into content-search terms for `Store.content_rank`.

    Whitespace split, drop sub-2-char tokens, dedupe case-insensitively,
    preserve first-seen order and original case (per-term canonical/variant
    expansion happens inside `content_rank`).

    Stopwords are dropped only when something survives. A single-token query
    IS the query — `context "the"` should still look for `the` — and a query
    whose every token is a function word has nothing else to search on. That
    rule came from `context._ref_terms` and is the reason it is safe to apply
    the stoplist unconditionally at every call site.

    `strip_kind_prefix` handles `context`'s `kind:name` refs, where the head
    is a kind selector rather than a search term. Only stripped when the head
    has no space or slash, so a prose query containing a colon is untouched.
    """
    text = (text or "").strip()
    if strip_kind_prefix and ":" in text:
        head = text.split(":", 1)[0]
        if " " not in head and "/" not in head:
            text = text.split(":", 1)[1]

    out: list[str] = []
    seen: set[str] = set()
    for tok in re.split(r"\s+", text):
        tok = tok.strip()
        if len(tok) < 2 or tok.lower() in seen:
            continue
        seen.add(tok.lower())
        out.append(tok)

    if drop_stopwords and len(out) > 1:
        content = [t for t in out if t.lower() not in STOPWORDS]
        if content:
            return content
    return out
