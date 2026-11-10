"""Hybrid retrieval entry point.

Combines refmatrix's symbolic retrieval (BM25 + linkage coverage +
identifier expansion) with Lance dense ANN. Three modes:

- dense-only      : `dense_recall(...)` — pure ANN, no symbolic.
- symbolic-only   : existing query/context paths; nothing here.
- hybrid          : `hybrid_recall(...)` — RRF fusion of a caller-
                    supplied symbolic ranking with the dense ANN
                    output. Optional bitmap pre-filter narrows the
                    ANN candidate pool BEFORE the distance search,
                    which is the cheap precision lever (microsecond
                    AND on roaring bitmaps + sub-100ms ANN).

The dense path is best-effort: if the [dense] extra isn't installed
or no vectors have been indexed yet, callers should fall back to the
symbolic ranking. `dense_available()` is the cheap probe.

Phase A7 surface; Phase B's `rmx memory recall` is the CLI consumer.
"""
from __future__ import annotations

import re
import threading
from typing import Callable, Sequence

from refmatrix.query import fuse_rrf
from refmatrix.store import Store


def dense_available() -> bool:
    """Cheap probe — does this environment have the [dense] extra
    available? Lets callers degrade quietly to symbolic-only when
    pylance / sentence-transformers isn't installed."""
    try:
        import importlib.util as _u
        return all(
            _u.find_spec(name) is not None
            for name in ("lance", "numpy", "sentence_transformers")
        )
    except Exception:
        return False


def dense_recall(
    store: Store,
    embedder,
    query: str,
    *,
    k: int = 20,
    kinds: Sequence[str] | None = None,
    candidate_ids: Sequence[int] | None = None,
) -> list[tuple[int, float]]:
    """Pure dense ANN. `embedder` must already be loaded. Returns
    `[(entity_id, distance)]` ascending by L2."""
    if not query:
        return []
    v = embedder.embed_texts([query])[0]
    return store.ann_search(
        v, k=k, dim=embedder.dim, kinds=kinds,
        candidate_ids=candidate_ids,
    )


def hybrid_recall(
    store: Store,
    embedder,
    query: str,
    *,
    k: int = 20,
    kinds: Sequence[str] | None = None,
    symbolic_hits: Sequence[int] | None = None,
    candidate_ids: Sequence[int] | None = None,
    rrf_k: int = 60,
) -> list[tuple[int, float]]:
    """RRF-fused hybrid retrieval.

    Inputs:
        symbolic_hits: caller-ranked entity ids (best-first) from
            the existing scoring stack. None = symbolic side
            contributes nothing.
        candidate_ids: bitmap-derived id set used as a PRE-FILTER
            on the ANN scan. None = no pre-filter. Empty list =
            ANN returns nothing (the symbolic side may still
            contribute).

    Output: `[(entity_id, fused_score)]` descending by fused RRF
    score. RRF inputs are rank-based, so distance magnitudes from
    Lance don't need calibrating against symbolic scores.
    """
    lists: list[list[int]] = []
    if symbolic_hits:
        lists.append(list(symbolic_hits))

    dense_hits = dense_recall(
        store, embedder, query,
        k=max(k, rrf_k),  # widen the ANN pool a bit so fusion has
                          # room to upvote cross-list winners.
        kinds=kinds,
        candidate_ids=candidate_ids,
    )
    if dense_hits:
        lists.append([eid for eid, _d in dense_hits])

    if not lists:
        return []
    fused = fuse_rrf(lists, k=rrf_k)
    return fused[:k]


def _content_terms(query: str) -> list[str]:
    """Tokenize an NL query into content-search terms for `content_rank`.

    Was a local copy that claimed to mirror `context._ref_terms` but dropped
    no stopwords, so `memory recall --fuse` sent `why`/`did`/`the`/`by` into
    BM25 as query terms. Now the same tokenizer every read surface uses."""
    from refmatrix.terms import content_terms
    return content_terms(query)


def hybrid_memory_recall(
    store: Store,
    embedder,
    query: str,
    *,
    k: int = 20,
    kinds: Sequence[str] | None = None,
    rrf_k: int = 60,
    candidate_ids: Sequence[int] | None = None,
) -> list[tuple[int, float]]:
    """Dense ⊕ symbolic RRF fusion for `rmx memory recall`.

    Runs `store.content_rank` (BM25 over the mentions forward index — rewards
    rare, exact query terms) AND the dense ANN, then RRF-fuses via
    `hybrid_recall`. Closes the gap where pure dense missed a lexically-exact
    memory because a 384-dim vector dilutes rare terms into topical space
    (e.g. "grep backstop protected query concept" — symbolic nailed it, dense
    didn't). `content_rank` is partition-scoped, so the CALLER must already
    have `store` bound to the target memory partition.

    Returns `[(entity_id, fused_score)]` descending by RRF score."""
    terms = _content_terms(query)
    # Cull the dense search space with the symbolic side's own answer. See
    # `concept_prefilter` for why this returns None rather than [] when it
    # cannot help.
    symbolic_hits: list[int] = []
    if terms:
        symbolic_hits = [
            eid for eid, _score in store.content_rank(
                terms,
                kinds=list(kinds) if kinds else ["memory"],
                limit=max(k, rrf_k),
            )
        ]
    return hybrid_recall(
        store, embedder, query,
        k=k, kinds=kinds, symbolic_hits=symbolic_hits, rrf_k=rrf_k,
        candidate_ids=candidate_ids,
    )


def concept_prefilter(
    store: Store,
    query: str,
    *,
    linkage: str = "mentions",
    kinds: "Sequence[str] | None" = None,
    min_candidates: int = 5,
    max_fraction: float = 0.5,
) -> "list[int] | None":
    """Derive a dense-ANN candidate set from the query's own concepts.

    The pieces have been here since Phase A7 — `bitmap_prefilter` unions the
    concept bitmaps, `ann_search(candidate_ids=...)` restricts the scan, and
    the module docstring calls it "the cheap precision lever". Nothing ever
    derived the concept list automatically: `rmx recall --concept` made the
    caller name them by hand, and `memory recall` never passed one at all. So
    the dense side has always searched the whole partition while the symbolic
    side knew exactly which documents mention the query's terms.

    Returns None (meaning "do not filter") rather than an empty list in every
    case where filtering would be wrong or worthless:

    * no concept resolved — an empty `candidate_ids` makes `ann_search` return
      NOTHING, so a query whose terms are absent from the graph would silently
      lose its dense half. That is the failure mode this guard exists for.
    * fewer than `min_candidates` — too tight to trust; a couple of documents
      is not a candidate pool, it is a guess.
    * more than `max_fraction` of the partition — filtering to most of the
      corpus costs a set union and buys no precision.

    Uses `scan.match_concepts`, so the query is tokenized, stoplisted and
    canonical-expanded by the same code every other surface uses.
    """
    if not query:
        return None
    # Resolve cheaply and by INDEX only. `scan.match_concepts` was the obvious
    # reuse, but it ends its ladder with `name LIKE '%/<cand>'` — a leading
    # wildcard, so a full scan of the concept table per candidate token. That
    # is fine for a once-per-prompt hook and not fine on the recall hot path:
    # wired that way it made the eval daemon stop answering. `resolve_concept_ids`
    # hits `idx_entities_canonical` and covers the case that matters here.
    try:
        from refmatrix.scan import extract_candidates
        from refmatrix.terms import STOPWORDS
        cands = [c for c in extract_candidates(query)
                 if c.lower() not in STOPWORDS]
    except Exception:
        return None
    if not cands:
        return None
    cids: list[int] = []
    seen: set[int] = set()
    for cand in cands:
        try:
            for cid in store.resolve_concept_ids(cand):
                if cid not in seen:
                    seen.add(cid)
                    cids.append(cid)
        except Exception:
            continue
    if not cids:
        return None
    ids = bitmap_prefilter(store, cids, linkage=linkage)
    if len(ids) < min_candidates:
        return None
    # Compare against the population actually being SEARCHED, not against
    # every row in the partition. Counting all entities includes tens of
    # thousands of bare concept nodes that the ANN never ranks, which inflates
    # the denominator so far that the guard can never fire: measured on a
    # 1307-document corpus, a union covering 947 documents (72%) still looked
    # like a tiny fraction of "all entities" and was passed through as a
    # useful cull. A filter that keeps three-quarters of the corpus costs a
    # set union and buys nothing.
    kinds = list(kinds) if kinds else ["code", "doc", "memory"]
    try:
        in_list = ",".join("?" * len(kinds))
        total = store._connect().execute(
            f"SELECT count(*) FROM entities WHERE partition_id = ? "
            f"AND kind IN ({in_list})",
            [store._partition_id, *kinds],
        ).fetchone()[0] or 0
    except Exception:
        total = 0
    if total and len(ids) > total * max_fraction:
        return None
    return ids


def bitmap_prefilter(
    store: Store,
    concepts: Sequence[int],
    linkage: str = "mentions",
) -> list[int]:
    """Build a candidate-id set by OR-ing the bitmaps for each concept
    under `linkage`. Cheap (microseconds of roaring set ops) — the
    typical pre-filter for hybrid_recall when the caller has parsed
    query concepts already.

    Empty `concepts` returns an empty list. Concepts with no
    bitmap contribute nothing.
    """
    if not concepts:
        return []
    from pyroaring import BitMap

    union: BitMap = BitMap()
    for cid in concepts:
        try:
            bm = store.load_bitmap(linkage, cid)
        except Exception:
            continue
        union |= bm
    return list(union)


# ---- task 3.7 #fam-graph-read: ONE embedder seam + the graph recall algorithm ----------
#
# Why here (task 3.7 #fam-graph-read-recall, spec decision 2026-10-20): `rmx recall` built
# `Embedder()` in the CLI process and ran its own ranking, so the daemon and the CLI could
# not share an answer. The ranking moved into `graph_recall` (run by the daemon op
# `graph_recall` AND, with no daemon at all, in-process by the verb — C4a), and the
# embedder into `shared_embedder`, which `Daemon._embedder` delegates to: one seam, two
# callers, provably the same model route.


def new_model_client(role: str, *, log: "Callable[[str], None] | None" = None,
                     stderr=None):
    """A model-worker client for `role` ("embed" | "rerank"): the hub's shared worker when
    one answers, else a private worker of our own. The hub hosts one model per role for
    the whole fleet; falling back to a private worker rather than failing keeps the hub
    from becoming a single point of failure for dense retrieval. `Daemon._model_client`
    caches what this returns; a daemonless caller owns (and closes) it."""
    import logging

    from refmatrix import modelsrv
    say = log or logging.getLogger(__name__).info
    if modelsrv.shared_enabled() and modelsrv.shared_available():
        client = None
        try:
            # Bounded: the worker's 300 s default let a broken shared worker
            # (bug-014/015) stall an op for five minutes.
            from refmatrix.daemon import SHARED_OP_TIMEOUT_S
            client = modelsrv.SharedWorkerClient(role, log=say, timeout=SHARED_OP_TIMEOUT_S)
            client.info(timeout=modelsrv.PROBE_TIMEOUT_S)
            say(f"{role}: using hub-shared worker")
            return client
        except Exception as exc:  # noqa: BLE001 — logged; the private worker serves
            say(f"{role}: hub-shared worker unusable ({exc!r}); falling back to a private "
                f"worker")
            if client is not None:
                try:
                    client.close()
                except Exception as cexc:  # noqa: BLE001 — named; the fallback proceeds
                    say(f"{role}: closing the unusable shared client failed: {cexc!r}")
    from refmatrix.subproc import WorkerClient
    client = WorkerClient(role, log=say)
    if stderr is not None:
        client.set_stderr(stderr)
    return client


def _reprobe_window() -> "tuple[float, float]":
    """The re-probe backoff window `(base, cap)`: `RMX_SHARED_REPROBE_S` (default 300 s)
    and `RMX_SHARED_REPROBE_MAX_S` (1800 s), read per call so an operator's env applies.

    Never raises (task 3.7 remedy r5, ch-bsd r4 #m-2, 2026-11-09): both go through
    `modelsrv.env_float`, so a malformed value is its default plus ONE warning naming the
    variable. Before r5 a typo'd `300s` raised out of here into the embed call of a
    process with a healthy private worker, which then loaded the in-process model on
    every call."""
    from refmatrix import modelsrv
    base = modelsrv.env_float("RMX_SHARED_REPROBE_S", 300.0)
    cap = modelsrv.env_float("RMX_SHARED_REPROBE_MAX_S", 1800.0)
    return base, cap


def cold_streak_key(role: str) -> str:
    """The key, in the caller's `backoff` dict, of `role`'s cold-miss streak: how many
    CONSECUTIVE re-probes of `role` connected to the hub socket and then timed out on the
    `info` header.

    Why a marker at all (ch-bsd 3.7 r6 #s-1, 2026-11-09): r5 re-armed at base on EVERY
    header-timeout miss, so a hub that accepts and never answers (wedged, SIGSTOPped, a
    hung ModelServer worker) was probed once per base window forever -- measured 22
    probes / 22.0 s of request-path stall in 25 s at base 1, and a daemon tick paying the
    full 45 s `PROBE_TIMEOUT_S` per role every 300 s. Only the FIRST header-timeout miss of
    a run may re-arm at base; the backoff VALUE cannot mark the run, because after
    `hold_reprobe` it already equals base. Why inside `backoff` rather than a third dict:
    the streak qualifies the backoff, so it must be reset by every path that resets the
    throttle -- a success's pop, `_process_embed_client`'s clear on a shared build, a
    caller (or test rig) that rebinds the dict -- and living in the same dict makes that
    true by construction rather than by remembering a sibling. The key never collides with
    a role name (roles are `embed` / `rerank`)."""
    return f"{role}#cold-streak"


def hold_reprobe(role: str, *, next_at: "dict[str, float]", backoff: "dict[str, float]",
                 now: "float | None" = None) -> None:
    """A hub decision was JUST made for `role` and it went private: the next re-probe
    waits one base window (`next_at = now + base`, `backoff = base`).

    Task 3.7 remedy r4 (ch-bsd r3 #s-1, 2026-11-09): r3 CLEARED the throttle after every
    build, so a build that had just probed the hub, failed and gone private told the very
    next call to probe again at once; behind a mute hub that was a second full probe on
    the request path. The build's own probe IS the first attempt of the window.

    Skipped when shared models are disabled (task 3.7 remedy r5, ch-bsd r4 #m-2,
    2026-11-09): under `RMX_SHARED_MODELS=0` no hub can ever be adopted, so there is no
    window to hold, and r4 still parsed the reprobe env here (a typo then cost the call
    its private worker)."""
    import time

    from refmatrix import modelsrv
    if not modelsrv.shared_enabled():
        return
    base, _cap = _reprobe_window()
    now = time.time() if now is None else float(now)
    backoff[role] = base
    next_at[role] = now + base
    # A fresh decision starts a fresh run of misses (ch-bsd 3.7 r6 #s-1, 2026-11-09): the
    # next header-timeout miss is the FIRST of its run, so it may re-arm at base.
    backoff.pop(cold_streak_key(role), None)


def reprobe_shared_client(role: str, *, next_at: "dict[str, float]",
                          backoff: "dict[str, float]", log: "Callable[[str], None]",
                          now: "float | None" = None,
                          probe_timeout: "float | None" = None):
    """THE re-probe of the hub's shared model socket for a holder of a PRIVATE `role`
    worker: a connected `SharedWorkerClient` when the hub answers now, else None.

    One implementation, two holders (task 3.7 remedy r3, ch-bsd r2 #s-1): a daemon on its
    background tick (`Daemon._maybe_adopt_shared`, bug-024 / task 12.1) and a daemonless
    process on its next embed call (`_process_embed_client`). Before r3 only the daemon
    re-probed, so an `rmx mcp` that fell back to a private worker during a hub crash kept
    that ~610 MB worker for its whole life: bug-024's shape in a process with no tick.

    The caller owns the throttle state (`next_at` / `backoff`, keyed by role) and the
    swap; this owns the probe and the backoff rule. A failed probe doubles the wait from
    `RMX_SHARED_REPROBE_S` (default 300 s) up to `RMX_SHARED_REPROBE_MAX_S` (1800 s), so a
    machine that will never have a hub does not probe at full rate forever. A success
    clears the role's state.

    A COLD hub is not an absent one (task 3.7 remedy r5, ch-bsd r4 #m-3, 2026-11-09):
    when the socket CONNECTED (`shared_available`) and only the `info` header timed out,
    the hub is alive and our probe has just asked it to load its worker, so the next
    re-probe is re-armed at the BASE window (`backoff = base`) -- but only for the FIRST
    such miss of a run (ch-bsd 3.7 r6 #s-1, 2026-11-09). A second CONSECUTIVE header
    timeout doubles like any miss, up to the cap: a worker still silent a full base window
    after it was asked to load is not loading, it is a mute hub (wedged, SIGSTOPped, a
    hung worker), and r5's every-miss-at-base probed it at base forever. The run is
    counted under `cold_streak_key(role)` in `backoff`; any other miss ends the run (a
    refused or absent socket means that hub is gone, and the next one to come up cold is
    a new run), and a success or `hold_reprobe` clears it. Before r5 that miss
    doubled like a dead hub's, so a hub that came up cold was adopted only after
    base + 2*base, with a duplicate private worker running beside the hub's. The case is
    told apart by STAGE and exception TYPE, never by message text: the miss must happen
    after the connect probe succeeded (stage `header`) and be a `TimeoutError`, which is
    what `SharedWorkerClient.call` re-raises for a bounded read that expired. An absent
    socket file or a refused connect (no hub; a stale socket nobody listens on) makes
    `shared_available` False, and a connect refused inside `info` raises
    `ConnectionRefusedError`: those still double.

    `probe_timeout` bounds the header probe. Default `modelsrv.PROBE_TIMEOUT_S`, the
    cold-worker bound, for the daemon's background tick. A caller on a REQUEST path passes
    `modelsrv.REQUEST_PROBE_TIMEOUT_S` (1.0 s; task 3.7 remedy r4, ch-bsd r3 #s-1,
    2026-11-09): behind a mute hub the r3 request path paid the 45 s cold bound per call."""
    import time

    from refmatrix import modelsrv
    if not modelsrv.shared_enabled():
        return None
    now = time.time() if now is None else float(now)
    if now < next_at.get(role, 0.0):
        return None
    base, cap = _reprobe_window()
    bound = modelsrv.PROBE_TIMEOUT_S if probe_timeout is None else float(probe_timeout)
    client = None
    cold = False                      # connected, header timed out (r5 #m-3, r6 #s-1)
    miss: "BaseException | None" = None
    stage = "connect"
    try:
        if modelsrv.shared_available(timeout=0.5):
            stage = "header"
            from refmatrix.daemon import SHARED_OP_TIMEOUT_S
            client = modelsrv.SharedWorkerClient(role, log=log, timeout=SHARED_OP_TIMEOUT_S)
            client.info(timeout=bound)
    except Exception as exc:  # noqa: BLE001 — logged; the private worker keeps serving
        cold = stage == "header" and isinstance(exc, TimeoutError)
        if client is not None:
            try:
                client.close()
            except Exception as cexc:  # noqa: BLE001 — named; the private worker serves
                log(f"{role}: closing the unusable shared client failed: {cexc!r}")
        client = None
        miss = exc
    if client is None:
        key = cold_streak_key(role)
        streak = int(backoff.get(key, 0)) if cold else 0
        if cold and streak == 0:
            wait = min(base, cap)         # first cold miss of the run (r5 #m-3)
        else:
            wait = min(max(base, backoff.get(role, 0.0) * 2.0), cap)
        if cold:
            backoff[key] = float(streak + 1)
        else:
            backoff.pop(key, None)
        backoff[role] = wait
        next_at[role] = now + wait
        # `miss is None`: `shared_available` was False (no hub listening) -- unlogged, as
        # before r6, so a machine with no hub does not log every tick.
        if miss is not None and cold and streak == 0:
            log(f"{role}: shared worker still unusable ({miss!r}): the hub socket "
                f"connected but its worker did not answer within {bound}s (cold, loading "
                f"its model); keeping the private worker, re-probing at the base window "
                f"{base}s")
        elif miss is not None and cold:
            log(f"{role}: shared worker still unusable ({miss!r}): the hub socket "
                f"connected but its worker did not answer within {bound}s again "
                f"({streak + 1} consecutive header timeouts: not loading, the hub is "
                f"mute); keeping the private worker, re-probing in {wait}s")
        elif miss is not None:
            log(f"{role}: shared worker still unusable ({miss!r}); keeping the private "
                f"worker, re-probing in {wait}s")
        return None
    backoff.pop(cold_streak_key(role), None)
    backoff.pop(role, None)
    next_at.pop(role, None)
    return client


def remote_embedder(model_client):
    """A loaded `RemoteEmbedder` over `model_client` (forces the worker spawn + model load
    now). A worker that reports a missing [dense] extra raises ImportError, matching the
    in-process model's contract."""
    from refmatrix.embedder import RemoteEmbedder
    from refmatrix.subproc import WorkerError
    e = RemoteEmbedder(model_client)
    try:
        _ = e.dim
    except WorkerError as exc:
        if "ModuleNotFoundError" in str(exc) or "ImportError" in str(exc):
            raise ImportError(str(exc)) from exc
        raise
    return e


_EMBED_CLIENT: "object | None" = None
_EMBED_CLIENT_REBUILDS = 0
_EMBED_CLIENT_ATEXIT = False
_EMBED_CLIENT_LOCK = threading.Lock()
# The re-probe throttle of THIS process's private embed client, in the shape
# `reprobe_shared_client` shares with the daemon (`Daemon._reprobe_next` / `_backoff`).
# A build that went private SETS it (`hold_reprobe`); a build that got the hub clears it
# (task 3.7 remedy r4, ch-bsd r3 #s-1: r3 cleared it after every build).
_EMBED_REPROBE_NEXT: "dict[str, float]" = {}
_EMBED_REPROBE_BACKOFF: "dict[str, float]" = {}
# True while one caller runs the request-path re-probe OUTSIDE `_EMBED_CLIENT_LOCK`;
# every other caller keeps the cached client instead of queueing a second probe
# (remedy r4, ch-bsd r3 #s-1). Read and written only under the lock.
_EMBED_REPROBE_INFLIGHT = False
# The in-process model standing in for a cached client whose worker could not serve
# (bug-173, remedy r4): `(client, embedder)`. Valid only while `_EMBED_CLIENT is client`.
_EMBED_INPROC: "tuple[object, object] | None" = None
_EMBED_INPROC_LOCK = threading.Lock()


def _close_process_embed_client() -> None:
    """atexit: close whichever client is cached when the process exits (a rebuilt-away
    or re-adopted-away client was already closed when it was dropped)."""
    client = _EMBED_CLIENT
    if client is not None:
        client.close()


def _embed_client_is_dead(client) -> bool:
    """Whether the cached client can no longer serve (task 3.7 remedy r2, ch-bsd
    2026-11-08-2256 #s-1). Only the HUB-shared client can pin the process dead: its
    backend is the hub's, and after the hub dies its `call` closes the socket, tries one
    reconnect, and leaves `_sock` None when that fails too -- `alive()` False. A shared
    client holding no socket is dead whatever its history: every client this cache holds
    was connected by `new_model_client`'s `info()` probe before it was cached (remedy r3
    dropped the "was it handed out" conjunct, ch-bsd r2 #m-2). A private `WorkerClient`
    respawns its own process on the next call (`_ensure`), so a dead private process is
    not a reason to rebuild; a private client is REPLACED by the hub's once the hub
    answers (`_process_embed_client`), not rebuilt. A private client whose worker could
    not start at all is served by the cached in-process stand-in (`_EMBED_INPROC`,
    bug-173) until then."""
    from refmatrix.modelsrv import SharedWorkerClient
    return isinstance(client, SharedWorkerClient) and not client.alive()


def _process_embed_client(log: "Callable[[str], None]",
                          warn: "Callable[[str], None] | None" = None):
    """The ONE embed-worker client of a daemonless process (task 3.7 remedy r1 R-H1): the
    long-lived `rmx mcp` used to spawn a new, never-reaped worker on every no-daemon
    recall / dense call. Created once under a lock, closed once at exit.

    This is also the ONE place that decides the cached client is unusable or replaceable:

    - remedy r2 (2026-11-08): a hub-shared client whose last call failed (the hub died:
      its socket is gone) is closed, counted in `_EMBED_CLIENT_REBUILDS`, said, and
      replaced by a fresh `new_model_client` (a private worker while the hub stays down).
      The call that met the dead socket already raised (or, inside `shared_embedder`,
      logged and degraded); the rebuild does not hide it.
    - remedy r3 (2026-11-09, ch-bsd r2 #s-1): a PRIVATE client is replaced by the hub's
      shared worker once the hub answers again, through `reprobe_shared_client`, the same
      probe and backoff knobs (`RMX_SHARED_REPROBE_S` / `_MAX_S`) a daemon's tick uses.
      The private worker is retired (not just closed) so a caller that captured it before
      the swap cannot respawn it.
    - remedy r4 (2026-11-09, ch-bsd r3 #s-1): that re-probe runs on a REQUEST path, so it
      is bounded by `modelsrv.REQUEST_PROBE_TIMEOUT_S` (1.0 s), not the 45 s cold-worker
      `PROBE_TIMEOUT_S`, and it runs OUTSIDE `_EMBED_CLIENT_LOCK` behind the
      `_EMBED_REPROBE_INFLIGHT` flag: a concurrent caller keeps the cached private client
      instead of waiting for the lock and then probing again (r3: 45 s then 90 s behind a
      mute hub). The lock is taken again only for the swap, which still happens once. A
      build that went private SETS the throttle (`hold_reprobe`): its own probe was the
      window's first attempt.

    `warn` carries what the operator must see (the rebuild and its count): a WARNING on
    this module's logger when no `log` was injected (remedy r3, ch-bsd r2 #m-1)."""
    import atexit

    from refmatrix import modelsrv
    from refmatrix.modelsrv import SharedWorkerClient
    global _EMBED_CLIENT, _EMBED_CLIENT_REBUILDS, _EMBED_CLIENT_ATEXIT
    global _EMBED_REPROBE_INFLIGHT, _EMBED_INPROC
    warn = warn or log
    with _EMBED_CLIENT_LOCK:
        cached = _EMBED_CLIENT
        if cached is not None and _embed_client_is_dead(cached):
            _EMBED_CLIENT_REBUILDS += 1
            warn(f"embed: hub-shared client lost its connection (its last call failed); "
                 f"dropping it and building a fresh client "
                 f"(rebuild #{_EMBED_CLIENT_REBUILDS} in this process)")
            _EMBED_CLIENT = None
            _EMBED_INPROC = None          # a stand-in keyed to the dropped client goes
            try:
                cached.close()
            except Exception as exc:  # noqa: BLE001 — named; the rebuild proceeds
                warn(f"embed: closing the dead hub-shared client failed: {exc!r}")
        if _EMBED_CLIENT is None:
            _EMBED_CLIENT = new_model_client("embed", log=log)
            if isinstance(_EMBED_CLIENT, SharedWorkerClient):
                _EMBED_REPROBE_NEXT.clear()
                _EMBED_REPROBE_BACKOFF.clear()
            else:
                hold_reprobe("embed", next_at=_EMBED_REPROBE_NEXT,
                             backoff=_EMBED_REPROBE_BACKOFF)
            if not _EMBED_CLIENT_ATEXIT:
                atexit.register(_close_process_embed_client)
                _EMBED_CLIENT_ATEXIT = True
            return _EMBED_CLIENT
        if isinstance(cached, SharedWorkerClient) or _EMBED_REPROBE_INFLIGHT:
            return cached
        _EMBED_REPROBE_INFLIGHT = True
    # The request-path re-probe, outside the lock: only this caller runs it.
    shared = None
    try:
        shared = reprobe_shared_client("embed", next_at=_EMBED_REPROBE_NEXT,
                                       backoff=_EMBED_REPROBE_BACKOFF, log=log,
                                       probe_timeout=modelsrv.REQUEST_PROBE_TIMEOUT_S)
    finally:
        with _EMBED_CLIENT_LOCK:
            _EMBED_REPROBE_INFLIGHT = False
            swapped = shared is not None and _EMBED_CLIENT is cached
            if swapped:
                _EMBED_CLIENT = shared
                _EMBED_INPROC = None      # the in-process stand-in (if any) goes too
            current = _EMBED_CLIENT
    if shared is not None and not swapped:
        # Unreachable while the flag holds (only a dead SHARED client is ever replaced
        # under it), armed so a future path cannot leak a hub connection.
        log("embed: the cached client changed during the re-probe; closing the probe's "
            "hub-shared client unused")
        try:
            shared.close()
        except Exception as exc:  # noqa: BLE001 — named; the cached client serves
            warn(f"embed: closing the unused hub-shared client failed: {exc!r}")
    if swapped:
        pid = getattr(getattr(cached, "_proc", None), "pid", "?")
        try:
            getattr(cached, "retire", cached.close)(timeout=2.0)
        except Exception as exc:  # noqa: BLE001 — the swap already happened
            warn(f"embed: private worker close failed after adoption: {exc!r}")
        log(f"embed: adopted hub-shared worker; closed private worker pid={pid}")
    return current


def _process_inproc_standin(client):
    """The cached in-process model standing in for `client`, or None (bug-173)."""
    held = _EMBED_INPROC
    if held is not None and client is not None and held[0] is client:
        return held[1]
    return None


def _load_process_inproc_standin(client, say: "Callable[[str], None]"):
    """Load the in-process model ONCE as the stand-in for `client`, the cached private
    client whose worker could not serve (bug-173, task 3.7 remedy r4, ch-bsd r3 #b-1,
    2026-11-09).

    Before r4 a daemonless process whose private worker could not spawn (a sandbox that
    forbids it, an interpreter the child cannot reach) built a fresh `Embedder()` on EVERY
    call: 3 calls, 3 loads of ~610 MB and 6-33 s each, under `RMX_SHARED_MODELS` 0 and 1.
    Now the process does what a daemon does in the same state (`Daemon._embedder`'s
    `on_fallback` drops its private worker and keeps `_embedder_inst`): it keeps ONE
    in-process model and stops respawning the failed worker. The stand-in is keyed to the
    cached client, so it lives exactly as long as that client is the process's choice:
    when the hub answers again, `_process_embed_client`'s re-probe swaps the client and
    drops the stand-in (as `Daemon._maybe_adopt_shared` drops `_embedder_inst`), so the
    cached fallback never pins the process off the hub. Under `RMX_SHARED_MODELS=0` there
    is no hub to return to, and the process stays in-process for its life, as a daemon
    does.

    The failed worker is closed (its exited process reaped); it stays cached as the key
    and is retired by the swap. The load runs under its own lock: two callers that fail
    together load once, and neither holds `_EMBED_CLIENT_LOCK` through a model load. A
    `client` of None (the client build itself raised) is not cached: that call loads and
    says so."""
    global _EMBED_INPROC
    from refmatrix.embedder import Embedder
    if client is None:
        say("embed: no process embed client was built; loading an UNCACHED in-process "
            "model for this call")
        e = Embedder()
        _ = e.dim
        return e
    with _EMBED_INPROC_LOCK:
        held = _process_inproc_standin(client)
        if held is not None:
            return held
        try:
            client.close()
        except Exception as exc:  # noqa: BLE001 — named; the stand-in still loads
            say(f"embed: closing the private worker that could not serve failed: {exc!r}")
        e = Embedder()
        _ = e.dim
        with _EMBED_CLIENT_LOCK:
            if _EMBED_CLIENT is client:
                _EMBED_INPROC = (client, e)
            else:
                say("embed: the process embed client changed during the in-process load; "
                    "this model serves the call and is not cached")
        say(f"embed: in-process model cached as this process's stand-in for its private "
            f"worker (loaded once; dropped when the hub is re-adopted)")
        return e


def shared_embedder(root, *, remote: "Callable[[], object] | None" = None,
                    log: "Callable[[str], None] | None" = None,
                    on_fallback: "Callable[[], None] | None" = None):
    """THE embedder accessor (task 3.7 #fam-graph-read-recall). Returns a loaded embedder
    for the store at `root`: by default the out-of-process worker (the hub's shared worker
    when it is up, else a private one), else the in-process model.

    `Daemon._embedder` passes its own `remote` builder (over its cached worker client),
    `log` and `on_fallback` (which drops its private worker); a daemonless caller — the
    verb's C4a branch — passes none and gets a worker client of its own, closed at exit.
    A daemonless caller whose worker could not serve gets ONE cached in-process model for
    as long as that client stays the process's choice (bug-173, remedy r4,
    `_load_process_inproc_standin`), never a fresh load per call.
    Raises ImportError when the [dense] extra is missing; callers surface that cleanly."""
    import logging

    from refmatrix.subproc import subproc_embed_enabled
    say = log or logging.getLogger(__name__).info
    # What the operator must see goes out at WARNING when nothing was injected (remedy r3,
    # ch-bsd r2 #m-1): `rmx mcp` and the CLI configure no logging, and Python's lastResort
    # handler prints WARNING and above to stderr, as for `verbs.memory_partition`'s notice
    # and `embedder`'s degraded-extraction line. At INFO the rebuild and the in-process
    # fallback reached no one. An injected `log` (the daemon's file) gets both lines.
    warn = log or logging.getLogger(__name__).warning
    if subproc_embed_enabled():
        client = None
        try:
            if remote is not None:
                e = remote()
            else:
                client = _process_embed_client(say, warn)
                held = _process_inproc_standin(client)
                if held is not None:
                    say(f"embedder: serving the cached in-process model (the private "
                        f"worker could not serve; re-probing the hub) "
                        f"model={getattr(held, 'model_name', '?')}")
                    return held
                e = remote_embedder(client)
            say(f"embedder loaded (subprocess) model={e.model_name} dim={e.dim}")
            return e
        except ImportError:
            # No [dense] extra: the in-process model would fail identically.
            raise
        except Exception as exc:  # noqa: BLE001 — a transport problem, said, then degraded
            # An interpreter the child cannot reach, a sandbox that forbids spawn, a pipe
            # the OS will not give: not a dense problem. Degrade to the in-process model
            # and say so loudly (it carries the model's RSS).
            warn(f"subprocess embedder unavailable ({exc!r}); falling back to in-process "
                 "model -- this process now carries the model's RSS. Set "
                 "RMX_EMBED_SUBPROC=0 to silence this, or investigate the spawn failure.")
            if on_fallback is not None:
                on_fallback()
            if remote is None:
                e = _load_process_inproc_standin(client, say)
                say(f"embedder loaded model={e.model_name} dim={e.dim}")
                return e
    from refmatrix.embedder import Embedder
    e = Embedder()
    _ = e.dim
    say(f"embedder loaded model={e.model_name} dim={e.dim}")
    return e


class PrecomputedQuery:
    """An embedder stand-in holding ONE precomputed query vector.

    The query is embedded BEFORE any store lock is taken (ch-bsd r9 #s-1: the model call ran
    inside the daemon's `_store_lock`, so a busy worker held every writer). The recall code
    asks this object for the query's vector; any other text is refused loudly, so a later
    change cannot quietly move a model call back under the lock."""

    def __init__(self, emb, query: str, vec) -> None:
        self.dim = emb.dim
        self.model_name = getattr(emb, "model_name", None)
        self._query = query
        self._vec = vec

    def embed_texts(self, texts):
        if list(texts) == [self._query]:
            return self._vec
        raise RuntimeError("model call under _store_lock: only the precomputed "
                           "query vector is available here")


def graph_recall_wants_dense(query: "str | None", *, no_dense: bool) -> bool:
    """Whether `graph_recall` needs the embedder (so the caller embeds BEFORE the read)."""
    return bool(query) and not no_dense and dense_available()


def prepare_graph_recall_embedder(get_embedder: "Callable[[], object]", query: "str | None",
                                  *, no_dense: bool):
    """The embedder `graph_recall` runs with: a `PrecomputedQuery` (the model called HERE,
    before any store is opened or locked), or None when the dense side does not run."""
    if not graph_recall_wants_dense(query, no_dense=no_dense):
        return None
    emb = get_embedder()
    return PrecomputedQuery(emb, query or "", emb.embed_texts([query]))


def graph_recall(store: Store, embedder, *, query: "str | None", k: int = 10,
                 kinds: "Sequence[str] | None" = None,
                 concept: "Sequence[str] | None" = None,
                 symbolic: "Sequence[int] | None" = None,
                 no_dense: bool = False) -> dict:
    """`rmx recall`'s algorithm (591a2fb `recall_cmd`), shared by the daemon op
    `graph_recall` and the verb's no-daemon branch (task 3.7 #fam-graph-read-recall, r1 B2):

    - `concept` names → `bitmap_prefilter` over `mentions` → `candidate_ids` (an unknown
      name is a warning and contributes nothing; an empty candidate set answers no hits);
    - dense by default (`dense_recall`); `hybrid_recall(symbolic_hits=…)` when `symbolic`;
    - the symbolic-only short-circuit when `no_dense` or the dense extra is missing;
    - NO rerank and NO BM25 fusion — that is `memory_recall`, a different contract.

    `embedder` is what `prepare_graph_recall_embedder` returned (None when the dense side
    does not run). Returns `{hits: [{rank, id, score, kind, name, path}], warnings}`,
    names resolved from `store` — the same partition the ranking read."""
    warnings: list[str] = []
    candidate_ids = None
    if concept:
        cids: list[int] = []
        for name in concept:
            e = store.get_entity("concept", name)
            if e is None:
                warnings.append(f"unknown concept: {name}")
                continue
            cids.append(e.id)
        if cids:
            candidate_ids = bitmap_prefilter(store, cids, linkage="mentions")
            if not candidate_ids:
                warnings.append("concept pre-filter produced an empty candidate set — "
                                "nothing matches the given concepts under 'mentions'")
                return {"hits": [], "warnings": warnings}
    symbolic_hits = [int(x) for x in symbolic] if symbolic else None
    kinds_l = list(kinds) if kinds else None
    if no_dense or not dense_available():
        if symbolic_hits is None:
            warnings.append("dense not available and no symbolic ranking given — "
                            "nothing to rank")
            return {"hits": [], "warnings": warnings}
        ids = list(symbolic_hits)
        if candidate_ids is not None:
            allowed = set(candidate_ids)
            ids = [i for i in ids if i in allowed]
        ranked = [(eid, 1.0 - i / max(1, len(ids))) for i, eid in enumerate(ids[:k])]
    else:
        if symbolic_hits is None and not query:
            warnings.append("no query and no symbolic ranking given")
            return {"hits": [], "warnings": warnings}
        if symbolic_hits is None:
            ranked = dense_recall(store, embedder, query or "", k=k, kinds=kinds_l,
                                  candidate_ids=candidate_ids)
        else:
            ranked = hybrid_recall(store, embedder, query or "", k=k, kinds=kinds_l,
                                   symbolic_hits=symbolic_hits, candidate_ids=candidate_ids)
    con = store._connect()
    hits = []
    for rank, (eid, score) in enumerate(ranked, 1):
        row = con.execute("SELECT kind, name, path FROM entities WHERE id = ?",
                          [eid]).fetchone()
        hits.append({"rank": rank, "id": int(eid), "score": float(score),
                     "kind": row[0] if row else None, "name": row[1] if row else None,
                     "path": row[2] if row else None})
    return {"hits": hits, "warnings": warnings}


def ann_search(store: "Store | Callable[[], Store]", emb, *, query: "str | None" = None,
               vector=None, k: int = 20,
               kinds: "Sequence[str] | None" = None, partition: "str | None" = None,
               rerank: "Callable[[str, object, int, list], object] | None" = None,
               lock=None, log: "Callable[[str], None] | None" = None) -> dict:
    """The `ann_search` op's algorithm (task 3.7 #fam-graph-read-recall: the daemon op AND
    the verb's no-daemon branch run this ONE function). Dense ANN via Lance by `query`
    (embedded HERE, before `lock`) or a precomputed `vector`. `rerank(query, docs, k,
    warnings)` — the daemon's cross-encoder stage — runs OUTSIDE `lock` when given; it
    returns `[(id, score)]` or None to keep retrieval order. Returns `{hits: [{id,
    distance}] | [{id, score, reranked}], warnings?}` or `{ok: False, error}`."""
    import contextlib
    if vector is None and not query:
        return {"ok": False, "error": "need 'query' text or 'vector' list"}
    if vector is None:
        v = emb.embed_texts([query])[0]
    else:
        import numpy as np
        v = np.asarray(vector, dtype="float32")
        if v.shape[0] != emb.dim:
            return {"ok": False, "error": f"vector dim {v.shape[0]} != model dim {emb.dim}"}
    want_rerank = rerank is not None and bool(query)
    # Over-fetch before reranking: the stage can only reorder what retrieval returned.
    from refmatrix.reranker import DEFAULT_POOL_MULT, MAX_POOL
    ann_k = min(max(k, k * DEFAULT_POOL_MULT), MAX_POOL) if want_rerank else k
    docs = None
    with (lock if lock is not None else contextlib.nullcontext()):
        # `store` may be a getter, resolved HERE, inside `lock` (task 3.7 remedy r1
        # R-RM1): the daemon's store resolved before the lock could be mid-swap.
        st = store() if callable(store) else store
        hits = st.ann_search(v, k=ann_k, dim=emb.dim, kinds=kinds, partition=partition)
        if want_rerank:
            from refmatrix.reranker import collect_rerank_docs
            try:
                docs = collect_rerank_docs(st, hits, k=k)
            except Exception as exc:  # noqa: BLE001 — logged; retrieval order stands
                if log is not None:
                    log(f"rerank doc collect failed: {exc!r}")
                docs = None
    rr_warnings: list[str] = []
    if want_rerank and docs is not None:
        assert rerank is not None and query is not None
        reranked = rerank(query, docs, k, rr_warnings)
        if reranked is not None:
            return {"hits": [{"id": eid, "score": sc, "reranked": True}
                             for eid, sc in reranked]}
    out: dict = {"hits": [{"id": eid, "distance": dist} for eid, dist in hits[:k]]}
    if rr_warnings:
        out["warnings"] = rr_warnings
    return out
