"""Promote recurring STM co-occurrence into durable LTM edges.

`Stm._apply_turn` already cliques every prompt's admitted refs and bumps the
pair weight by 1.0 per co-occurrence, so the session graph accumulates exactly
the evidence "these two things keep coming up together". Nothing ever moved
that into the long-term graph: `handoff._promote_digest` promotes a digest
MEMORY, not edges, so the association died with the session.

`project_stm_ltm_helix_design` already settled the shape this should take. Its
load-bearing correction is that the two strands have different physics —
structural edges (`calls`, `defines`, `imports`) are time-invariant and must
never be discounted, while the ASSOCIATIVE layer (`mentions`, co-occurrence,
`related-to`) decays. Prompt co-occurrence is associative, so it gets its own
verb and never touches the structural edges the symbolic retrieval floor is
built on.

The threshold is the whole safety argument. Promoting every co-occurrence
would durably link whatever vocabulary a session happened to use — measured
live mid-session, the top STM nodes were `multiple`, `cross`, `terms`,
`prompt`, `link`, the words of a conversation ABOUT retrieval. Requiring a pair
to recur across several turns is what separates "the session is about this
relationship" from "these two words appeared in one sentence".
"""
from __future__ import annotations

import os
from pathlib import Path

# Associative verb, kebab-case per the project's verb canon. Deliberately NOT
# `related-to`: that one is authored in GMD documents and carries editorial
# intent, and mixing machine-derived co-occurrence into it would make a curated
# edge indistinguishable from an accident of phrasing.
CO_OCCURS = "co-occurs"

# How many turns a pair must have co-occurred in before it is worth keeping.
DEFAULT_MIN_WEIGHT = 3.0

# Cap per promotion run. A focus graph of N nodes can carry O(N^2) edges, and
# a single unbounded run could add thousands of weak associative edges to a
# graph whose value is that its edges mean something.
DEFAULT_MAX_EDGES = 200


def min_weight() -> float:
    try:
        return float(os.environ.get("RMX_PROMOTE_MIN_WEIGHT",
                                    str(DEFAULT_MIN_WEIGHT)) or DEFAULT_MIN_WEIGHT)
    except ValueError:
        return DEFAULT_MIN_WEIGHT


def _resolve_entity_ref(store, name: str) -> "int | None":
    """Resolve an STM ref that is NOT a concept to the entity it names.

    STM and LTM do not share a vocabulary. `_extract_refs` records what a
    prompt and its tool output mention — file paths, log locations, dotted
    symbols — while the concept graph holds a different namespace entirely.
    Measured on one live session: of 98 endpoints that recurred often enough
    to be worth promoting, 95 had no concept of that name, and the sample was
    `src/refmatrix/daemon.py`, `Path.home`, `/tmp/envs.txt`. Most of those ARE
    entities, just `kind=code`/`doc` rather than `concept`.

    Tried in order: exact entity name, then a path suffix match. The suffix
    match uses a leading-wildcard LIKE — a full scan — which is affordable
    only because promotion runs on save-state or an explicit command, never
    per query. The same pattern on the recall hot path stopped a daemon
    answering earlier today.

    Refs that name nothing in the graph (a log file, a /tmp scratch path) stay
    unresolved and are simply not promoted.
    """
    ref = (name or "").strip()
    if not ref:
        return None
    try:
        e = store.resolve_entity(ref)
    except Exception:
        e = None
    if e is not None:
        return e.id
    # Path-ish refs: STM often holds a fragment ("src/refmatrix/daemon.py")
    # while the graph holds the absolute path.
    if "/" in ref and not ref.endswith("/"):
        try:
            row = store._connect().execute(
                "SELECT id FROM entities WHERE partition_id = ? "
                "AND path LIKE ? ORDER BY length(path) LIMIT 1",
                (store._partition_id, f"%{ref}"),
            ).fetchone()
        except Exception:
            row = None
        if row is not None:
            return int(row[0])
    return None


def _gated_concept_id(store, name: str) -> "int | None":
    """Resolve an STM node name to a graph endpoint, applying the same junk
    gate the prompt path uses. Returns None for anything that should not
    become a durable edge endpoint."""
    from refmatrix.scan import (
        SHAPE0_SALIENCE_FLOOR, _concept_signal, _is_unlinked_plain,
        _PROMPT_STOPWORDS, _salience, _token_shape_score,
    )
    from refmatrix import pagerank as pr_mod

    bare = (name or "").split("#", 1)[0]
    if not bare or bare.lower() in _PROMPT_STOPWORDS:
        return None
    try:
        cids = store.resolve_concept_ids(bare)
    except Exception:
        return None
    if not cids:
        # Not a concept — try the entity namespace before giving up.
        return _resolve_entity_ref(store, name)
    con = store._connect()
    pr_computed = pr_mod.has_scores(store)
    for cid in cids:
        row = con.execute(
            "SELECT name FROM entities WHERE id = ?", (cid,)).fetchone()
        if row is None:
            continue
        cname = row[0]
        _c, deg, df, max_tf = _concept_signal(store, con, cname)
        if _is_unlinked_plain(bare, deg):
            continue
        sal = _salience(store, cname, bare, cid, deg, df,
                        pr_computed=pr_computed, max_tf=max_tf)
        if (pr_computed and "/" not in cname
                and _token_shape_score(bare) == 0.0
                and sal < SHAPE0_SALIENCE_FLOOR):
            continue
        return cid
    # Resolved as a concept but gated out; the entity namespace may still hold
    # a legitimate target for the same ref.
    return _resolve_entity_ref(store, name)


def promote_focus_edges(
    store,
    root: "Path | str",
    *,
    session: "str | None" = None,
    threshold: "float | None" = None,
    max_edges: int = DEFAULT_MAX_EDGES,
    verb: str = CO_OCCURS,
    dry_run: bool = True,
) -> dict:
    """Write STM co-occurrence pairs at or above `threshold` as LTM edges.

    Defaults to `dry_run=True`: this mutates the durable graph, and the caller
    should have to ask for that explicitly.

    Returns `{promoted, skipped_below_threshold, skipped_ungated, pairs}` where
    `pairs` lists `(a, b, weight)` for what was (or would be) written.
    """
    from refmatrix.stm import Stm, latest_session

    root = Path(root)
    session = session or latest_session(root)
    if not session:
        return {"promoted": 0, "skipped_below_threshold": 0,
                "skipped_ungated": 0, "pairs": [], "session": None}

    thresh = min_weight() if threshold is None else threshold
    graph = Stm(root, session=session).focus_graph(top=200)

    # Node frequencies, for lift. `project_composite_edge_selection_outliers`
    # established this for the STM composite and the reason applies verbatim
    # here: raw weight favours the node that co-occurs with EVERYTHING. On the
    # session that motivated this, `src/refmatrix/__init__.py` was in 4 of the
    # top 10 pairs purely because the version gets bumped alongside every
    # change — an artefact of the workflow, not an association worth keeping.
    # Lift (w / (freq_a * freq_b)) surfaces pairs that bind tighter than their
    # popularity predicts.
    freq = {n["name"]: max(int(n.get("count") or 1), 1)
            for n in (graph.get("nodes") or [])}

    below = 0
    ungated = 0
    resolved: dict[str, "int | None"] = {}
    cands: list[tuple[float, str, str, float]] = []
    for e in graph.get("edges") or []:
        w = float(e.get("weight") or 0.0)
        if w < thresh:
            below += 1
            continue
        a, b = e.get("source"), e.get("target")
        for name in (a, b):
            if name not in resolved:
                resolved[name] = _gated_concept_id(store, name)
        if resolved[a] is None or resolved[b] is None or resolved[a] == resolved[b]:
            ungated += 1
            continue
        lift = w / (freq.get(a, 1) * freq.get(b, 1))
        cands.append((lift, a, b, w))
    # Highest lift first, then weight as the tie-break.
    cands.sort(key=lambda t: (-t[0], -t[3]))
    pairs: list[tuple[str, str, float]] = [
        (a, b, w) for _lift, a, b, w in cands[:max_edges]]

    if not dry_run and pairs:
        store.add_linkage_type(
            verb, directed=False,
            description="co-occurred in the same prompts across a session")
        for a, b, w in pairs:
            ca, cb = resolved[a], resolved[b]
            # Undirected association, stored both ways so a walk from either
            # endpoint sees it. `weighted_link` sets the ranking weight, which
            # the adjacency builder already reads.
            store.weighted_link(verb, concept_id=ca, entity_id=cb, weight=w)
            store.weighted_link(verb, concept_id=cb, entity_id=ca, weight=w)

    return {
        "session": session,
        "promoted": 0 if dry_run else len(pairs),
        "would_promote": len(pairs) if dry_run else 0,
        "skipped_below_threshold": below,
        "skipped_ungated": ungated,
        "threshold": thresh,
        "pairs": pairs,
    }
