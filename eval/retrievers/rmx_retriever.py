"""rmx retriever adapter for the eval harness.

Two scoring variants:

  scorer="tf_rrf"  (baseline)
      Per-token TF posting list from the store, fused via RRF. Sets the
      floor for what the symbolic graph alone can do with naive TF.

  scorer="bm25"
      BM25 over the same posting lists (k1, b configurable). Standard IR
      scoring with IDF + document-length normalization. Sums per-token
      contributions to a single doc score, no RRF needed.

Both variants share the same tokenizer and ingest path. The only difference
is the per-query scoring function.
"""
from __future__ import annotations

import ast
import math
import multiprocessing as mp
import re
import tempfile
from dataclasses import dataclass
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


@dataclass
class BM25Params:
    k1: float = 1.5
    b: float = 0.75


# Curated NL↔Python-code synonym groups. Union of these tokens shares a
# canon at retrieval time (the bitmap-union of sibling postings IS the
# token's effective posting). Asymmetric in nature — NL uses "count",
# code uses "len" — but a symmetric union covers both directions.
SYNONYM_GROUPS: list[set[str]] = [
    {"sort", "sorted", "order", "ordered", "ordering", "arrange", "arranged"},
    {"delete", "remove", "drop", "erase", "discard", "pop"},
    {"parse", "read", "load", "loads", "decode", "deserialize"},
    {"write", "dump", "dumps", "save", "store", "serialize", "encode"},
    {"find", "search", "lookup", "locate", "match", "matches", "get"},
    {"create", "make", "build", "construct", "new", "init", "initialize"},
    {"check", "validate", "verify", "assert", "ensure", "test"},
    {"count", "length", "size", "len", "num", "number"},
    {"list", "array", "arr", "seq", "sequence", "iterable", "items", "vec"},
    {"dict", "dictionary", "map", "mapping", "hashmap", "hash"},
    {"file", "path", "filename", "filepath", "pathname"},
    {"string", "str", "text", "txt"},
    {"int", "integer", "float", "number", "numeric", "num"},
    {"update", "modify", "change", "edit", "alter"},
    {"add", "append", "insert", "push", "extend"},
    {"print", "display", "show", "output", "log"},
    {"error", "exception", "fail", "failure", "fault"},
    {"convert", "transform", "cast", "coerce"},
    {"compare", "equal", "equals", "match", "eq"},
    {"concat", "join", "merge", "combine", "concatenate"},
    {"split", "separate", "divide", "partition"},
    {"filter", "select", "where", "subset"},
    {"open", "close", "connect", "disconnect"},
    {"start", "begin", "init", "stop", "end", "finish"},
    {"min", "minimum", "max", "maximum"},
    {"key", "value", "val", "entry"},
    {"row", "column", "col", "field"},
    {"json", "yaml", "xml", "toml"},  # serialization formats often interchanged
    {"args", "arguments", "params", "parameters", "kwargs"},
    {"return", "yield", "result", "output"},
]
_TOKEN_TO_GROUP: dict[str, frozenset[str]] = {}
for _g in SYNONYM_GROUPS:
    _fs = frozenset(_g)
    for _t in _g:
        # First wins on collisions (groups should ideally not overlap).
        _TOKEN_TO_GROUP.setdefault(_t, _fs)


# Worker-side globals for fork-pool parallel retrieve.
_WORKER_RETRIEVER: "RmxRetriever | None" = None


def _worker_init() -> None:
    """Detach parent's TempDir finalizer in fork-children so worker exit
    doesn't race the parent on cleanup."""
    r = _WORKER_RETRIEVER
    if r is not None and r._tmp is not None:
        try:
            r._tmp._finalizer.detach()
        except AttributeError:
            pass


def _worker_retrieve(args: tuple) -> tuple:
    qid, qtext, top_k = args
    return qid, _WORKER_RETRIEVER.retrieve(qtext, top_k=top_k)


def _tokenize(text: str) -> list[str]:
    out: list[str] = []
    for m in _TOKEN_RE.finditer(text):
        t = m.group(0).lower()
        if len(t) >= 2 and t not in _STOP:
            out.append(t)
    return out


def _camel_split(token: str) -> Iterable[str]:
    """Further split camelCase / PascalCase into pieces."""
    parts = re.findall(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+", token)
    return [p.lower() for p in parts if len(p) >= 2]


_DOCSTRING_RE = re.compile(r'("""(.*?)"""|\'\'\'(.*?)\'\'\')', re.DOTALL)


def ast_extract(text: str) -> dict[str, str]:
    """Return raw per-linkage *text* slices via Python ast. The caller still
    tokenizes via expand_token. Keys: defines, params, calls, docstring, code.

    Falls back to ('', text) docstring split on SyntaxError, leaving the
    structural buckets empty.
    """
    out = {"defines": "", "params": "", "calls": "", "docstring": "", "code": ""}
    if not text:
        return out
    try:
        tree = ast.parse(text)
    except SyntaxError:
        ds, body = split_docstring(text)
        out["docstring"] = ds
        out["code"] = body
        return out

    defines: list[str] = []
    params: list[str] = []
    calls: list[str] = []
    docstring = ""
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if not docstring:
                d = ast.get_docstring(node)
                if d:
                    docstring = d
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                defines.append(node.name)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = node.args
                arg_nodes = (
                    list(args.args)
                    + list(args.kwonlyargs)
                    + list(getattr(args, "posonlyargs", []))
                )
                if args.vararg:
                    arg_nodes.append(args.vararg)
                if args.kwarg:
                    arg_nodes.append(args.kwarg)
                for a in arg_nodes:
                    if a and a.arg:
                        params.append(a.arg)
        elif isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name):
                calls.append(f.id)
            elif isinstance(f, ast.Attribute):
                calls.append(f.attr)

    _, body = split_docstring(text)
    out["defines"] = " ".join(defines)
    out["params"] = " ".join(params)
    out["calls"] = " ".join(calls)
    out["docstring"] = docstring
    out["code"] = body
    return out


def split_docstring(text: str) -> tuple[str, str]:
    """Return (docstring, code_body). Uses ast where possible, regex fallback.

    On CSN python the doc is typically a single function. We extract the first
    function/class/module docstring via ast, then strip its source span from
    the body. If ast.parse fails, fall back to regex on the first triple-quoted
    block.
    """
    if not text:
        return "", ""
    try:
        tree = ast.parse(text)
        ds = ""
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                d = ast.get_docstring(node)
                if d:
                    ds = d
                    break
        if not ds:
            return "", text
    except SyntaxError:
        m = _DOCSTRING_RE.search(text)
        if not m:
            return "", text
        ds = (m.group(2) or m.group(3) or "").strip()
        body = text[:m.start()] + text[m.end():]
        return ds, body

    # ast succeeded — strip the first triple-quoted block from the body text.
    m = _DOCSTRING_RE.search(text)
    if m:
        body = text[:m.start()] + text[m.end():]
    else:
        body = text
    return ds, body


def expand_token(text: str, stem=None) -> list[str]:
    """Top-level tokenize + camel split. Returns deduped order-preserved tokens.

    If stem is provided (callable str -> str), each token is stemmed after
    camel split and stoplist filtering. Stemmed forms are deduped.
    """
    seen: set[str] = set()
    out: list[str] = []
    for raw in _tokenize(text):
        candidates = [raw] + list(_camel_split(raw))
        for c in candidates:
            if c in _STOP or c in seen or len(c) < 2:
                continue
            if stem is not None:
                c = stem(c)
                if not c or len(c) < 2 or c in _STOP or c in seen:
                    continue
            seen.add(c)
            out.append(c)
    return out


class RmxRetriever:
    """Build a temp Store from a BEIR corpus, then run NL queries against it."""

    def __init__(
        self,
        *,
        store_dir: Path | None = None,
        k_per_token: int = 1000,
        rrf_k: int = 60,
        scorer: str = "tf_rrf",
        bm25: BM25Params | None = None,
        stem: bool = False,
        freq_stop_threshold: float | None = None,
        idf_power: float = 1.0,
        linkage_weights: dict[str, float] | None = None,
        coverage_alpha: float = 0.0,
        canon_expand: bool = False,
        comention_alpha: float = 0.0,
        bigram_source: str | None = None,
        bigram_weight: float = 0.0,
    ):
        if scorer not in {"tf_rrf", "bm25", "bm25_multi"}:
            raise ValueError(f"unknown scorer: {scorer!r}")
        self._tmp: tempfile.TemporaryDirectory | None = None
        if store_dir is None:
            self._tmp = tempfile.TemporaryDirectory(prefix="rmx-eval-")
            store_dir = Path(self._tmp.name) / ".refmatrix"
        self.store_dir = Path(store_dir)
        self.store = Store(self.store_dir)
        self.store.init()
        self.k_per_token = k_per_token
        self.rrf_k = rrf_k
        self.scorer = scorer
        self.bm25 = bm25 or BM25Params()
        if stem:
            import Stemmer
            self._stem_fn = Stemmer.Stemmer("porter").stemWord
        else:
            self._stem_fn = None

        self.freq_stop_threshold = freq_stop_threshold
        self._freq_stop_cids: set[int] = set()
        self.idf_power = idf_power
        self.linkage_weights = linkage_weights  # bm25_multi only
        self.coverage_alpha = coverage_alpha
        self.canon_expand = canon_expand
        self.comention_alpha = comention_alpha
        self.bigram_source = bigram_source  # None | 'docstring' | 'code'
        self.bigram_weight = bigram_weight

        # Bigram-specific stores (positional, source-linkage-relative).
        self._bigram_postings: dict[int, dict[int, int]] = {}
        self._bigram_doc_len: dict[int, int] = {}
        self._bigram_avgdl: float = 0.0
        self._bigram_N: int = 0

        # Per-linkage storage (bm25_multi). Keyed by linkage name.
        self._postings_l: dict[str, dict[int, dict[int, int]]] = {}
        self._doc_len_l: dict[str, dict[int, int]] = {}
        self._avgdl_l: dict[str, float] = {}
        self._N_l: dict[str, int] = {}

        # docid -> rmx entity id  /  token -> concept id
        self._doc_eid: dict[str, int] = {}
        self._concept: dict[str, int] = {}

        # In-process indices used by BM25 (built during ingest).
        self._postings: dict[int, dict[int, int]] = {}  # cid -> {eid: tf}
        self._doc_len: dict[int, int] = {}              # eid -> total tokens
        self._avgdl: float = 0.0
        self._N: int = 0

    def close(self) -> None:
        self.store.close()
        if self._tmp is not None:
            self._tmp.cleanup()
            self._tmp = None

    # --- ingest ----------------------------------------------------------

    def ingest_corpus(self, corpus: dict[str, dict]) -> None:
        """corpus: {doc_id: {'text': str, 'title': str}} (BEIR shape)."""
        if self.scorer == "bm25_multi":
            self._ingest_multi(corpus)
            return

        for did, doc in corpus.items():
            blob = (doc.get("title", "") + "\n" + doc.get("text", "")).strip()
            tokens = expand_token(blob, stem=self._stem_fn)
            if not tokens:
                continue
            eid = self.store.upsert_entity(kind="doc", name=did, path=did, tldr=None)
            self._doc_eid[did] = eid

            tf: dict[str, int] = {}
            for t in tokens:
                tf[t] = tf.get(t, 0) + 1
            self._doc_len[eid] = sum(tf.values())
            for tok, count in tf.items():
                cid = self._concept.get(tok)
                if cid is None:
                    cid = self.store.add_concept(tok)
                    self._concept[tok] = cid
                self.store.weighted_link("mentions", cid, eid, weight=float(count))
                self._postings.setdefault(cid, {})[eid] = count

        self._N = len(self._doc_len)
        if self._N:
            self._avgdl = sum(self._doc_len.values()) / self._N

        if self.freq_stop_threshold is not None and self._N:
            cutoff = self.freq_stop_threshold * self._N
            self._freq_stop_cids = {
                cid for cid, posting in self._postings.items()
                if len(posting) > cutoff
            }
            stop_tokens = {
                tok for tok, cid in self._concept.items()
                if cid in self._freq_stop_cids
            }
            print(
                f"  freq stoplist: {len(self._freq_stop_cids)} concepts pruned "
                f"(df > {cutoff:.0f}) — {sorted(stop_tokens)[:30]}"
            )

    def _ingest_multi(self, corpus: dict[str, dict]) -> None:
        """Ingest with per-linkage tokenization (docstring, code, defines, params, calls)."""
        # Register any custom linkage types up front.
        wanted = set((self.linkage_weights or {}).keys())
        for linkage in wanted:
            self.store.add_linkage_type(linkage, directed=True)

        use_ast = bool(wanted & {"defines", "params", "calls"})

        for did, doc in corpus.items():
            text = (doc.get("title", "") + "\n" + doc.get("text", "")).strip()
            if not text:
                continue
            if use_ast:
                slices = ast_extract(text)
                tokens_per_linkage = {
                    L: expand_token(slices.get(L, ""), stem=self._stem_fn)
                    for L in wanted
                }
            else:
                ds, body = split_docstring(text)
                tokens_per_linkage = {
                    "docstring": expand_token(ds, stem=self._stem_fn) if ds else [],
                    "code":      expand_token(body, stem=self._stem_fn) if body else [],
                }
            if not any(tokens_per_linkage.values()):
                continue

            eid = self.store.upsert_entity(kind="doc", name=did, path=did, tldr=None)
            self._doc_eid[did] = eid

            for linkage, tokens in tokens_per_linkage.items():
                if not tokens:
                    continue
                tf: dict[str, int] = {}
                for t in tokens:
                    tf[t] = tf.get(t, 0) + 1
                self._doc_len_l.setdefault(linkage, {})[eid] = sum(tf.values())
                for tok, count in tf.items():
                    cid = self._concept.get(tok)
                    if cid is None:
                        cid = self.store.add_concept(tok)
                        self._concept[tok] = cid
                    self.store.weighted_link(linkage, cid, eid, weight=float(count))
                    self._postings_l.setdefault(linkage, {}).setdefault(cid, {})[eid] = count

            # Optional bigram pass: positional adjacency on the source linkage.
            if self.bigram_source:
                src_tokens = tokens_per_linkage.get(self.bigram_source, [])
                if len(src_tokens) >= 2:
                    bg_tf: dict[str, int] = {}
                    for a, b in zip(src_tokens, src_tokens[1:]):
                        bg = f"{a}::{b}"
                        bg_tf[bg] = bg_tf.get(bg, 0) + 1
                    self._bigram_doc_len[eid] = sum(bg_tf.values())
                    for bg, count in bg_tf.items():
                        cid = self._concept.get(bg)
                        if cid is None:
                            cid = self.store.add_concept(bg)
                            self._concept[bg] = cid
                        self._bigram_postings.setdefault(cid, {})[eid] = count

        self._N = len(self._doc_eid)
        for linkage, dlens in self._doc_len_l.items():
            self._N_l[linkage] = len(dlens)
            self._avgdl_l[linkage] = sum(dlens.values()) / max(1, len(dlens))
        if self.bigram_source and self._bigram_doc_len:
            self._bigram_N = len(self._bigram_doc_len)
            self._bigram_avgdl = sum(self._bigram_doc_len.values()) / self._bigram_N
        print(
            f"  multi-linkage stats: " +
            ", ".join(f"{L}: N={self._N_l[L]}, avgdl={self._avgdl_l[L]:.1f}" for L in self._N_l)
        )

    # --- query -----------------------------------------------------------

    def retrieve(self, query: str, top_k: int = 1000) -> dict[str, float]:
        if self.scorer == "bm25":
            return self._retrieve_bm25(query, top_k)
        if self.scorer == "bm25_multi":
            return self._retrieve_bm25_multi(query, top_k)
        return self._retrieve_tf_rrf(query, top_k)

    def _retrieve_tf_rrf(self, query: str, top_k: int) -> dict[str, float]:
        tokens = expand_token(query, stem=self._stem_fn)
        if not tokens:
            return {}

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
        eid_to_did = {v: k for k, v in self._doc_eid.items()}
        return {eid_to_did[eid]: score for eid, score in fused if eid in eid_to_did}

    def _query_units(self, tokens: list[str]) -> list[list[int]]:
        """Decompose query tokens into BM25 'units'. Each unit is a list of
        concept-ids treated as a single canonical concept (bitmap-UNION of
        their postings) at scoring time. When canon_expand is off, every
        unit is a singleton. Dedups across units."""
        out: list[list[int]] = []
        seen_groups: set[frozenset[str]] = set()
        seen_cids: set[int] = set()
        for tok in tokens:
            if self.canon_expand and tok in _TOKEN_TO_GROUP:
                grp = _TOKEN_TO_GROUP[tok]
                if grp in seen_groups:
                    continue
                seen_groups.add(grp)
                cids = []
                for t in grp:
                    cid = self._concept.get(t)
                    if cid is None or cid in self._freq_stop_cids or cid in seen_cids:
                        continue
                    cids.append(cid)
                    seen_cids.add(cid)
                if cids:
                    out.append(cids)
            else:
                cid = self._concept.get(tok)
                if cid is None or cid in self._freq_stop_cids or cid in seen_cids:
                    continue
                seen_cids.add(cid)
                out.append([cid])
        return out

    def _retrieve_bm25(self, query: str, top_k: int) -> dict[str, float]:
        tokens = expand_token(query, stem=self._stem_fn)
        if not tokens or self._N == 0:
            return {}

        units = self._query_units(tokens)
        if not units:
            return {}

        k1, b = self.bm25.k1, self.bm25.b
        avgdl = self._avgdl
        scores: dict[int, float] = {}
        coverage: dict[int, int] | None = {} if self.coverage_alpha > 0 else None

        for unit_cids in units:
            # Union postings across siblings — sum TF per doc.
            virtual: dict[int, int] = {}
            for cid in unit_cids:
                p = self._postings.get(cid)
                if not p:
                    continue
                for eid, tf in p.items():
                    virtual[eid] = virtual.get(eid, 0) + tf
            if not virtual:
                continue
            n_t = len(virtual)
            idf = math.log((self._N - n_t + 0.5) / (n_t + 0.5) + 1.0)
            if self.idf_power != 1.0:
                idf = idf ** self.idf_power
            for eid, tf in virtual.items():
                dl = self._doc_len.get(eid, avgdl)
                norm = 1.0 - b + b * dl / avgdl
                contrib = idf * (tf * (k1 + 1.0)) / (tf + k1 * norm)
                scores[eid] = scores.get(eid, 0.0) + contrib
                if coverage is not None:
                    coverage[eid] = coverage.get(eid, 0) + 1

        if not scores:
            return {}

        if coverage is not None:
            n_units = len(units)
            alpha = self.coverage_alpha
            for eid in scores:
                cov = coverage.get(eid, 0) / n_units
                scores[eid] *= cov ** alpha

        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:top_k]
        eid_to_did = {v: k for k, v in self._doc_eid.items()}
        return {eid_to_did[eid]: s for eid, s in ranked if eid in eid_to_did}

    def _retrieve_bm25_multi(self, query: str, top_k: int) -> dict[str, float]:
        tokens = expand_token(query, stem=self._stem_fn)
        if not tokens or not self.linkage_weights:
            return {}

        units = self._query_units(tokens)
        if not units:
            return {}

        k1, b = self.bm25.k1, self.bm25.b
        scores: dict[int, float] = {}
        # Coverage tracked at the unit level (per-doc set of unit indices hit).
        doc_hits: dict[int, set[int]] | None = {} if self.coverage_alpha > 0 else None
        # Co-mention: per-doc per-linkage set of unit indices hit. Captures
        # "did this doc's docstring (or code) alone cover the whole query".
        doc_hits_per_linkage: dict[str, dict[int, set[int]]] | None = (
            {L: {} for L in self.linkage_weights} if self.comention_alpha > 0 else None
        )

        for u_idx, unit_cids in enumerate(units):
            for linkage, w_L in self.linkage_weights.items():
                postings_L = self._postings_l.get(linkage, {})
                doc_len_L = self._doc_len_l.get(linkage, {})
                N_L = self._N_l.get(linkage, 0)
                avgdl_L = self._avgdl_l.get(linkage, 0.0)
                if not postings_L or avgdl_L == 0 or N_L == 0:
                    continue
                # Union postings of unit's cids inside this linkage.
                virtual: dict[int, int] = {}
                for cid in unit_cids:
                    p = postings_L.get(cid)
                    if not p:
                        continue
                    for eid, tf in p.items():
                        virtual[eid] = virtual.get(eid, 0) + tf
                if not virtual:
                    continue
                n_t = len(virtual)
                idf = math.log((N_L - n_t + 0.5) / (n_t + 0.5) + 1.0)
                if self.idf_power != 1.0:
                    idf = idf ** self.idf_power
                for eid, tf in virtual.items():
                    dl = doc_len_L.get(eid, avgdl_L) or 1
                    norm = 1.0 - b + b * dl / avgdl_L
                    contrib = w_L * idf * (tf * (k1 + 1.0)) / (tf + k1 * norm)
                    scores[eid] = scores.get(eid, 0.0) + contrib
                    if doc_hits is not None:
                        doc_hits.setdefault(eid, set()).add(u_idx)
                    if doc_hits_per_linkage is not None:
                        doc_hits_per_linkage[linkage].setdefault(eid, set()).add(u_idx)

        if not scores:
            return {}

        n_units = len(units)

        if doc_hits is not None:
            alpha = self.coverage_alpha
            for eid in scores:
                cov = len(doc_hits.get(eid, ())) / n_units
                scores[eid] *= cov ** alpha

        if doc_hits_per_linkage is not None:
            beta = self.comention_alpha
            for eid in scores:
                # Best linkage-local coverage = max over L of |hits_L(d)| / n_units.
                # 1.0 means one field covered the entire query — strong co-mention.
                best = 0.0
                for L, lhits in doc_hits_per_linkage.items():
                    n = len(lhits.get(eid, ()))
                    if n > 0:
                        best = max(best, n / n_units)
                if best > 0:
                    scores[eid] *= best ** beta

        # Bigram bonus — added AFTER cov/cm scaling so it doesn't get blunted
        # by partial-coverage docs that happen to have a phrase match.
        if self.bigram_source and self.bigram_weight > 0 and len(tokens) >= 2 and self._bigram_N > 0:
            query_bgs = [f"{a}::{b}" for a, b in zip(tokens, tokens[1:])]
            avgdl_bg = self._bigram_avgdl
            N_bg = self._bigram_N
            for bg in query_bgs:
                cid = self._concept.get(bg)
                if cid is None:
                    continue
                posting = self._bigram_postings.get(cid)
                if not posting:
                    continue
                n_t = len(posting)
                idf = math.log((N_bg - n_t + 0.5) / (n_t + 0.5) + 1.0)
                for eid, tf in posting.items():
                    dl = self._bigram_doc_len.get(eid, avgdl_bg) or 1
                    norm = 1.0 - b + b * dl / avgdl_bg
                    contrib = self.bigram_weight * idf * (tf * (k1 + 1.0)) / (tf + k1 * norm)
                    scores[eid] = scores.get(eid, 0.0) + contrib

        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:top_k]
        eid_to_did = {v: k for k, v in self._doc_eid.items()}
        return {eid_to_did[eid]: s for eid, s in ranked if eid in eid_to_did}

    def run(
        self,
        queries: dict[str, str],
        top_k: int = 1000,
        *,
        workers: int = 1,
    ) -> dict[str, dict[str, float]]:
        if workers <= 1 or self.scorer == "tf_rrf":
            # Sequential. tf_rrf path hits SQLite per query — not fork-safe.
            out: dict[str, dict[str, float]] = {}
            for qid, qtext in queries.items():
                out[qid] = self.retrieve(qtext, top_k=top_k)
            return out

        global _WORKER_RETRIEVER
        _WORKER_RETRIEVER = self
        ctx = mp.get_context("fork")
        items = [(qid, qtext, top_k) for qid, qtext in queries.items()]
        chunksize = max(1, len(items) // (workers * 8))
        with ctx.Pool(processes=workers, initializer=_worker_init) as pool:
            results = pool.imap_unordered(_worker_retrieve, items, chunksize=chunksize)
            return dict(results)
