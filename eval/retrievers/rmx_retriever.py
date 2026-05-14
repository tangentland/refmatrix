"""rmx retriever adapter for the eval harness.

rmx is symbolic — no embeddings, no NL semantics — so we give it the
fairest shot at NL-to-code retrieval by treating tokens as concepts:

  ingest:  each corpus doc is an entity. Tokenize its text; for each
           unique token, get-or-create a concept and `mentions`-link the
           doc to it with weight = term frequency.
  query:   tokenize the NL query. For each token that exists as a concept,
           pull `top_weighted("mentions", concept_id, k=K)` — that's a
           ranked doc list per token. Fuse with `fuse_rrf` to produce a
           final ranking.

This is a weak baseline by design. It sets a floor for what the symbolic
graph alone can do on NL-to-code retrieval, which lets us measure the gap
to CodeRankEmbed and motivate hybrid (graph + dense) work.
"""
from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Iterable

from refmatrix.query import fuse_rrf
from refmatrix.store import Store

# Identifier-ish tokenizer: alphanumeric runs, lowercased, length>=2.
# Splits camelCase and snake_case via the [A-Za-z]+|\d+ pattern.
_TOKEN_RE = re.compile(r"[A-Za-z]{2,}|\d{2,}")

# Stoplist — extremely common English words plus generic code noise.
_STOP = {
    "the", "and", "for", "with", "that", "this", "from", "into", "are",
    "was", "were", "you", "your", "but", "not", "can", "all", "any", "use",
    "used", "using", "will", "may", "see", "also", "one", "two", "three",
    "function", "method", "class", "return", "returns", "param", "params",
    "arg", "args", "true", "false", "none", "null", "self", "type", "var",
    "let", "const", "def", "fn", "func", "new", "old", "get", "set", "has",
    "out", "off", "via", "per", "non", "via",
}


def _tokenize(text: str) -> list[str]:
    out: list[str] = []
    for m in _TOKEN_RE.finditer(text):
        t = m.group(0).lower()
        if len(t) >= 2 and t not in _STOP:
            out.append(t)
    return out


def _camel_split(token: str) -> Iterable[str]:
    """Further split camelCase / PascalCase into pieces."""
    # foo_bar handled by tokenizer already (underscores aren't matched).
    # Split on case transitions: "parseJSONFile" -> ["parse", "JSON", "File"].
    parts = re.findall(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+", token)
    return [p.lower() for p in parts if len(p) >= 2]


def expand_token(text: str) -> list[str]:
    """Top-level tokenize + camel split. Returns deduped order-preserved tokens."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in _tokenize(text):
        candidates = [raw] + list(_camel_split(raw))
        for c in candidates:
            if c in _STOP or c in seen or len(c) < 2:
                continue
            seen.add(c)
            out.append(c)
    return out


class RmxRetriever:
    """Build a temp Store from a BEIR corpus, then run NL queries against it."""

    def __init__(self, *, store_dir: Path | None = None, k_per_token: int = 1000, rrf_k: int = 60):
        self._tmp: tempfile.TemporaryDirectory | None = None
        if store_dir is None:
            self._tmp = tempfile.TemporaryDirectory(prefix="rmx-eval-")
            store_dir = Path(self._tmp.name) / ".refmatrix"
        self.store_dir = Path(store_dir)
        self.store = Store(self.store_dir)
        self.store.init()
        self.k_per_token = k_per_token
        self.rrf_k = rrf_k

        # docid -> rmx entity id  /  token -> concept id
        self._doc_eid: dict[str, int] = {}
        self._concept: dict[str, int] = {}

    def close(self) -> None:
        self.store.close()
        if self._tmp is not None:
            self._tmp.cleanup()
            self._tmp = None

    # --- ingest ----------------------------------------------------------

    def ingest_corpus(self, corpus: dict[str, dict]) -> None:
        """corpus: {doc_id: {'text': str, 'title': str}} (BEIR shape)."""
        for did, doc in corpus.items():
            blob = (doc.get("title", "") + "\n" + doc.get("text", "")).strip()
            tokens = expand_token(blob)
            if not tokens:
                continue
            # entity name must be unique inside the partition; doc_id is.
            eid = self.store.upsert_entity(kind="doc", name=did, path=did, tldr=None)
            self._doc_eid[did] = eid

            tf: dict[str, int] = {}
            for t in tokens:
                tf[t] = tf.get(t, 0) + 1
            for tok, count in tf.items():
                cid = self._concept.get(tok)
                if cid is None:
                    cid = self.store.add_concept(tok)
                    self._concept[tok] = cid
                self.store.weighted_link("mentions", cid, eid, weight=float(count))

    # --- query -----------------------------------------------------------

    def retrieve(self, query: str, top_k: int = 1000) -> dict[str, float]:
        tokens = expand_token(query)
        if not tokens:
            return {}

        # Per-token ranked entity-id lists from top_weighted.
        ranked_lists: list[list[int]] = []
        for tok in tokens:
            cid = self._concept.get(tok)
            if cid is None:
                continue
            ranked = self.store.top_weighted("mentions", cid, k=self.k_per_token)
            if not ranked:
                continue
            ranked_lists.append([eid for eid, _w in ranked])

        if not ranked_lists:
            return {}

        fused = fuse_rrf(ranked_lists, k=self.rrf_k)[:top_k]

        # Map entity ids back to doc ids.
        eid_to_did = {v: k for k, v in self._doc_eid.items()}
        return {eid_to_did[eid]: score for eid, score in fused if eid in eid_to_did}

    def run(self, queries: dict[str, str], top_k: int = 1000) -> dict[str, dict[str, float]]:
        out: dict[str, dict[str, float]] = {}
        for qid, qtext in queries.items():
            out[qid] = self.retrieve(qtext, top_k=top_k)
        return out
