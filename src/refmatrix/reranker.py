"""Cross-encoder reranking over a retrieved shortlist.

The retrieval stack scores a query and a document *independently* — BM25
over the mentions index, or a 384-dim bi-encoder vector per side. That is
what makes it cheap enough to run over a whole partition, and also what
caps its precision: neither side ever sees the other. A cross-encoder
scores the pair jointly in one forward pass, so it can tell "the query
term appears, but about a different subject" from a real match. The cost
is linear in candidates, which is why it can only run over a shortlist
someone else already narrowed.

Where it pays: `project_memaware_benchmark` measured proactive retrieval
at 0.200 hit@20 on the scan-prompt surface against 0.433 for `context`
after the 0.36.0 fixes. Recall is not the binding constraint there —
ordering within the retrieved pool is. That is precisely the shape a
reranker fixes.

Default model is `cross-encoder/ms-marco-MiniLM-L-12-v2`: 33M params,
~130 MB, English, built for exactly this reranking job.
`BAAI/bge-reranker-base` is the quality upgrade (278M params, multilingual,
~1.1 GB resident) and is a reasonable choice *because* the model runs
out-of-process and is evictable — set `RMX_RERANK_MODEL` to switch.

Landmine, measured here 2026-08-27: the L-6 sibling of the default
(`cross-encoder/ms-marco-MiniLM-L-6-v2`) returns **NaN** for every pair
under transformers 5.8.1 / torch 2.12. Its parameters are finite and its
embedding layer is fine; NaN first appears at encoder layer 1, under both
eager and sdpa attention. L-12, bge-reranker-base and TinyBERT-L-2 all
score correctly on the same stack, so this is one bad checkpoint, not a
broken environment. `score()` guards against it regardless — a
non-finite result raises rather than silently ordering by NaN, which
compares False against everything and would scramble the ranking.
"""
from __future__ import annotations

import os
from typing import Sequence

DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-12-v2"

# Cross-encoders truncate at 512 tokens. Bounding upfront keeps the
# per-pair cost predictable when an extractor hands back a whole file.
MAX_DOC_CHARS = 2048

# How many candidates to rerank per k requested. 4x is the usual
# retrieve-then-rerank ratio: wide enough that a mis-ranked true hit is
# inside the pool, narrow enough that the forward passes stay cheap.
DEFAULT_POOL_MULT = int(os.environ.get("RMX_RERANK_POOL_MULT", "4") or "4")
MAX_POOL = int(os.environ.get("RMX_RERANK_MAX_POOL", "100") or "100")

# Gap between consecutive demoted (unscored) rows. Only their ORDER matters —
# the value exists so a sort by score cannot reshuffle them.
_EPS = 1e-6


def rerank_enabled() -> bool:
    """Is the cross-encoder stage on? Default: yes.

    Set `RMX_RERANK=0` to disable it globally, or pass `--no-rerank` /
    `{"rerank": false}` per call. It is on by default because it runs in
    its own worker process, so the cost is a second evictable child rather
    than a fatter daemon -- the tradeoff that made it unaffordable before
    `subproc` existed. Steady-state cost is one warm forward pass over the
    shortlist (~0.1-0.3s); the model load is paid once by the daemon's
    background warmup, not by the first recall.
    """
    return os.environ.get("RMX_RERANK", "1") not in ("0", "false", "False")


def rerank_available() -> bool:
    """Cheap probe for the [dense] extra without importing torch."""
    try:
        import importlib.util as _u
        return _u.find_spec("sentence_transformers") is not None
    except Exception:
        return False


def _checked(scores, model_name: str) -> list[float]:
    """Reject a non-finite score set.

    NaN compares False against everything, so a NaN score does not sort to
    the bottom — it lands wherever the sort algorithm happens to leave it
    and quietly scrambles the ranking. Some published checkpoints produce
    NaN on current transformers builds (see the module docstring), so this
    is a real case, not a theoretical one. Raising lets the daemon's
    `_apply_rerank_safe` fall back to retrieval order and log why.
    """
    out = [float(x) for x in scores]
    bad = [x for x in out if x != x or x in (float("inf"), float("-inf"))]
    if bad:
        raise RuntimeError(
            f"reranker {model_name} returned non-finite scores "
            f"({len(bad)}/{len(out)}); refusing to rank by them"
        )
    return out


class Reranker:
    """Lazy-loaded sentence-transformers CrossEncoder wrapper.

    Mirrors `embedder.Embedder`: model loads on first `score`, cached on
    the instance, module import stays cheap.
    """

    def __init__(self, model_name: str | None = None):
        self.model_name = (
            model_name or os.environ.get("RMX_RERANK_MODEL") or DEFAULT_MODEL
        )
        self._model = None

    def _load(self) -> None:
        if self._model is not None:
            return
        from sentence_transformers import CrossEncoder

        device = os.environ.get("RMX_RERANK_DEVICE") or \
            os.environ.get("RMX_EMBED_DEVICE", "cpu")
        self._model = CrossEncoder(self.model_name, device=device)

    def score(self, query: str, docs: Sequence[str]) -> list[float]:
        """Score each doc against the query. Higher = more relevant.

        Scores are raw model outputs, comparable only within one call —
        never mix them with BM25 or RRF magnitudes; use them for ordering.
        """
        self._load()
        model = self._model
        assert model is not None  # _load() just set it
        if not docs:
            return []
        pairs = [[query, (d or "")[:MAX_DOC_CHARS]] for d in docs]
        out = model.predict(pairs, show_progress_bar=False)
        return _checked(out, self.model_name)


class RemoteReranker:
    """Same surface as `Reranker`, backed by a worker process.

    See `subproc` for why the model lives out-of-process. Cross-encoders
    make the case sharper than the bi-encoder does: `bge-reranker-base`
    is ~1.1 GB resident, which is a non-starter inside a daemon that
    already jetsams — but fine in a process that can be killed between
    queries.
    """

    def __init__(self, client):
        self._client = client
        self._model_name: str | None = None

    @property
    def model_name(self) -> str:
        if self._model_name is None:
            self._model_name = self._client.info().get("model") or DEFAULT_MODEL
        return self._model_name

    def score(self, query: str, docs: Sequence[str]) -> list[float]:
        if not docs:
            return []
        truncated = [(d or "")[:MAX_DOC_CHARS] for d in docs]
        hdr, _ = self._client.call(
            "rerank", {"query": query, "docs": truncated},
        )
        # The worker already ran `_checked`; re-run it here so a future
        # transport that bypasses `Reranker.score` cannot skip the guard.
        return _checked(hdr.get("scores") or [], self.model_name)


def _entity_kinds(store, eids: Sequence[int]) -> dict[int, str]:
    """Map entity_id -> kind for the shortlist. One query, not N."""
    if not eids:
        return {}
    con = store._connect()
    in_list = ",".join("?" * len(eids))
    rows = con.execute(
        f"SELECT id, kind FROM entities WHERE id IN ({in_list})",
        list(eids),
    ).fetchall()
    return {int(r[0]): (r[1] or "") for r in rows}


def collect_rerank_docs(
    store,
    hits: Sequence[tuple[int, float]],
    *,
    k: int = 20,
    pool: int | None = None,
) -> tuple[list[tuple[int, str]], list[tuple[int, float]], list[tuple[int, float]]]:
    """Split `hits` into `(scored, untexted, tail)` and fetch doc text.

    This is the DuckDB half of reranking, kept separate from the model half
    so the daemon can do it under `_store_lock` and then release the lock
    before spending a few hundred milliseconds in a forward pass. Holding
    the store lock across a model call would put every `rmx query` behind
    the reranker, which is exactly the CLI-priority regression the two-pool
    design exists to prevent.

    - `scored`   — `(entity_id, text)` for the top `pool` rows that have text.
    - `untexted` — top-pool rows whose extractor returned nothing. An empty
      string scores meaninglessly against any query, so these are never sent
      to the model; they keep their retrieval order behind the scored rows.
      Same convention `embedder.extract_batch` uses when it skips empty rows.
    - `tail`     — everything below the pool, order preserved.
    """
    pool_n = pool if pool is not None else max(k, k * DEFAULT_POOL_MULT)
    pool_n = min(max(pool_n, k), MAX_POOL, len(hits))
    head = list(hits)[:pool_n]
    tail = [(int(e), float(sc)) for e, sc in list(hits)[pool_n:]]

    from refmatrix import embedder as embmod

    kinds = _entity_kinds(store, [eid for eid, _ in head])
    scored: list[tuple[int, str]] = []
    untexted: list[tuple[int, float]] = []
    for eid, sc in head:
        kind = kinds.get(int(eid), "")
        text = ""
        if kind:
            try:
                text = embmod.extract_text_for_entity(store, int(eid), kind)
            except Exception:
                text = ""
        if text:
            scored.append((int(eid), text))
        else:
            untexted.append((int(eid), float(sc)))
    return scored, untexted, tail


def apply_rerank(
    reranker,
    query: str,
    scored: Sequence[tuple[int, str]],
    untexted: Sequence[tuple[int, float]],
    tail: Sequence[tuple[int, float]],
    *,
    k: int = 20,
) -> list[tuple[int, float]]:
    """The model half. Returns `[(entity_id, rerank_score)]` capped at `k`.

    Scores are the cross-encoder's own. Retrieval scores are NOT preserved
    for reranked rows: the two scales share no units and blending them
    would produce a number that means nothing.
    """
    if not scored:
        return (list(untexted) + list(tail))[:k]
    scores = reranker.score(query, [t for _e, t in scored])
    ranked = sorted(
        ((eid, float(sc)) for (eid, _t), sc in zip(scored, scores)),
        key=lambda p: p[1],
        reverse=True,
    )
    # Restamp the unscored remainder onto the reranked scale.
    #
    # `untexted` and `tail` still carry RETRIEVAL scores — cosine-ish values
    # around 0.4 — while reranked rows carry cross-encoder logits that are
    # routinely negative. Returning them side by side makes position the only
    # thing that encodes the ranking, and position does not survive a consumer
    # that re-sorts by score. `rmx memory recall` does exactly that, which put
    # a body-less row (retrieval 0.44) above a genuine reranked hit (logit
    # -0.52). Placing them strictly below the reranked floor makes the
    # documented contract — descending by score — actually true, so ordering
    # survives any downstream sort.
    floor = ranked[-1][1]
    rest = list(untexted) + list(tail)
    demoted = [(eid, floor - _EPS * (i + 1)) for i, (eid, _sc) in enumerate(rest)]
    return (ranked + demoted)[:k]


def rerank_entity_hits(
    store,
    reranker,
    query: str,
    hits: Sequence[tuple[int, float]],
    *,
    k: int = 20,
    pool: int | None = None,
) -> list[tuple[int, float]]:
    """Reorder `[(entity_id, score)]` with a cross-encoder.

    Convenience wrapper over `collect_rerank_docs` + `apply_rerank` for
    callers with no lock to worry about (tests, in-process/CLI paths). The
    daemon calls the two halves separately — see `collect_rerank_docs`.
    """
    if not hits or not query:
        return list(hits)[:k]
    scored, untexted, tail = collect_rerank_docs(store, hits, k=k, pool=pool)
    if not scored:
        return list(hits)[:k]
    return apply_rerank(reranker, query, scored, untexted, tail, k=k)


def shared_reranker(log=None, *, timeout: "float | None" = None):
    """A reranker backed by the hub's shared worker, or None. `timeout`
    bounds the probe AND every score call (the client's socket timeout;
    the worker default is 300 s — bsd-plan2-r6 #b-1).

    Deliberately shared-or-nothing, with no private-worker fallback. The
    callers are read surfaces that run in short-lived CLI processes — the
    always-on `scan-prompt` hook among them — and spawning a ~450 MB model
    process per invocation to rerank twenty rows would cost far more than the
    ranking is worth. In the daemon the tradeoff is different (a private
    worker is amortized over the daemon's life), which is why
    `Daemon._model_client` does fall back and this does not.

    Returns None when the hub is down or sharing is disabled, and every caller
    treats None as "keep retrieval order".
    """
    if not rerank_enabled() or not rerank_available():
        return None
    try:
        from refmatrix import modelsrv
        if not modelsrv.shared_enabled() or not modelsrv.shared_available():
            return None
        client = modelsrv.SharedWorkerClient("rerank", log=log, timeout=timeout)
        client.info(timeout=timeout)   # prove it answers before handing it out
        return RemoteReranker(client)
    except Exception:
        return None
