"""Derive subjects from the memory corpus — `rmx memory compile`.

The subject CONTAINER already existed (`upsert_subject` / `link_part_of` /
`list_subjects`, ADR-0002); what was missing is the DERIVATION layer. Nothing
grouped the corpus automatically, so subjects had to be declared by hand.

Signal is a SYNTHESIS of two views of "these two memories belong together":

  dense    cosine over the Lance memory vectors — catches paraphrase, two
           memories saying the same thing in unrelated vocabulary.
  concept  idf-weighted overlap of the concepts each memory mentions (the
           `mentions` fragment) — catches shared rare terms, and is the only
           half that can EXPLAIN a grouping.

Neither alone is right. Dense-only clusters have no symbolic "why" — you
cannot say which term made two memories group. Concept-only misses paraphrase
entirely, and drowns in hub terms (`rmx`, `memory`, `store`) that co-occur
everywhere and mean nothing. So:

    edge in the dense kNN:      w = w_dense * (1 + beta * s)
    pair NOT in the kNN,
      with s >= bridge_min:     w = gamma * s

Dense sets the topology; concepts MODULATE it (a dense-adjacent pair sharing
rare terms binds harder) and separately ADD sparse bridges dense missed. The
asymmetry is deliberate: concepts can strengthen a dense edge but never create
one inside the kNN, and a bridge has to clear a much higher bar (`bridge_min`)
than a confirmation.

Hub damping falls out of idf rather than a stoplist: the concept space is
restricted to `2 <= df <= hub_df_frac * N`, so a term in every memory carries
no weight and a term in one memory can't pair anything. This is the same
lift-over-raw-weight rule the STM composite work landed — the aha-bridges are
sparse outliers, not hubs.

Clustering itself is `stm.cluster_focus` (label propagation), which only ever
ran on the ephemeral per-session focus graph. It takes a weighted adjacency and
is signal-agnostic, so the entire fusion above happens in edge construction —
no new clustering algorithm.

Output is BOTH: `mtype='subject'` nodes + `part-of` edges in the store, and a
readable GMD index on disk. The index is regenerable from the store, and the
store is rebuildable from the index.
"""
from __future__ import annotations

import fnmatch
import json
import math
import re
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable

from refmatrix.scan import _PROMPT_STOPWORDS, _token_shape_score
from refmatrix.store import _CONCEPT_SHIFT, _ENTITY_MASK

if TYPE_CHECKING:
    from refmatrix.store import Store

# Operational content (raw session/digest cards) never enters the graph, and
# it must not enter clustering either: those rows are per-session artifacts,
# not knowledge, and they are numerous enough to form their own giant cluster
# that swallows real subjects. Same rule + same regex as pagerank's graph.
DEFAULT_EXCLUDE_MTYPES = ("session", "session/*", "digest", "digest/*", "subject")
_OPERATIONAL_RE = re.compile(r"(?i)^(session|digest)[-_]")

COMPILED_BY = "memory-compile"


# ---------------------------------------------------------------- corpus ---

def _memory_rows(
    store: "Store", *, exclude_mtypes: Iterable[str],
) -> list[dict]:
    """Memory rows of the active partition, minus excluded mtypes (globs)."""
    store._connect()
    rows = store._read().execute(
        "SELECT e.id, e.name, mc.mtype FROM entities e "
        "JOIN memory_content mc ON mc.entity_id = e.id "
        "WHERE e.partition_id=? AND e.kind='memory' "
        "ORDER BY e.id",
        (store._partition_id,),
    ).fetchall()
    pats = list(exclude_mtypes)
    out = []
    for r in rows:
        mtype = r[2] or ""
        if any(fnmatch.fnmatch(mtype, p) for p in pats):
            continue
        if _OPERATIONAL_RE.match(str(r[1])):
            continue
        out.append({"id": int(r[0]), "name": str(r[1]), "mtype": mtype})
    return out


def _concept_sets(
    store: "Store", ids: set[int], *, hub_df_frac: float, min_df: int = 2,
) -> tuple[dict[int, set[int]], dict[int, float], dict[int, str]]:
    """Per-memory concept sets restricted to the INFORMATIVE concept space.

    One decode pass over the packed `mentions` fragment (`concept<<32|entity`),
    same as `pagerank.build_adjacency`. Returns
    `(memory_id -> concept ids, concept id -> idf, concept id -> name)`.

    A concept is informative when `min_df <= df <= hub_df_frac * N` over THIS
    corpus: below the floor it can never pair two memories, above the ceiling
    it is a hub that would pair all of them. Dropping hubs from the space (not
    merely down-weighting them) also keeps the similarity denominator honest —
    `s` stays a true cosine over the terms that carry signal.
    """
    try:
        frag = store._load_fragment("mentions")
    except Exception:
        frag = None
    raw: dict[int, set[int]] = defaultdict(set)
    df: Counter = Counter()
    if frag is not None:
        for packed in frag:
            eid = packed & _ENTITY_MASK
            if eid not in ids:
                continue
            cid = packed >> _CONCEPT_SHIFT
            if cid in raw[eid]:
                continue
            raw[eid].add(int(cid))
            df[int(cid)] += 1

    n = max(1, len(ids))
    ceiling = max(min_df, int(hub_df_frac * n))
    keep = {c for c, d in df.items() if min_df <= d <= ceiling}

    # Concept names, and a second filter pass: operational card concepts leak
    # in as concept nodes from other partitions' mention edges.
    names: dict[int, str] = {}
    if keep:
        con = store._connect()
        ordered = sorted(keep)
        for chunk_start in range(0, len(ordered), 500):
            chunk = ordered[chunk_start:chunk_start + 500]
            ph = ",".join("?" * len(chunk))
            for r in con.execute(
                f"SELECT id, name FROM entities WHERE id IN ({ph})", chunk,
            ).fetchall():
                names[int(r[0])] = str(r[1])
    keep = {c for c in keep
            if c in names and not _OPERATIONAL_RE.match(names[c])}

    idf = {c: math.log(n / df[c]) for c in keep}
    sets = {eid: (cs & keep) for eid, cs in raw.items()}
    return sets, idf, names


# ------------------------------------------------------------ similarity ---

def _unit_rows(mat):
    import numpy as np

    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return mat / norms


def auto_threshold(mat, percentile: float, *, sample: int = 4000) -> float:
    """Cosine floor as a PERCENTILE of this corpus's own pair distribution.

    An absolute cosine is close to meaningless: it depends on the embedding
    model and, far more, on how narrow the corpus is. A single project's
    memories all discuss the same system in the same vocabulary, so their
    pairwise cosines pile up near 0.73 — an absolute 0.55 floor then admits
    essentially every pair and label propagation collapses the whole corpus
    into one blob. Anchoring on a percentile keeps the graph equally sparse
    whatever the corpus's absolute scale.
    """
    import numpy as np

    n = mat.shape[0]
    if n < 3:
        return 0.0
    unit = _unit_rows(mat)
    if n > sample:
        # Deterministic stride sample — no RNG, so repeated runs agree.
        idx = np.arange(0, n, max(1, n // int(math.sqrt(sample))))
        unit = unit[idx]
    sims = unit @ unit.T
    iu = np.triu_indices(sims.shape[0], 1)
    vals = sims[iu]
    if vals.size == 0:
        return 0.0
    return float(np.percentile(vals, percentile))


def _dense_knn(
    mat, k: int, threshold: float, *, mutual: bool = True,
) -> dict[tuple[int, int], float]:
    """kNN over row-normalized vectors → `{(i,j): w_dense}` with `i < j`.

    `w_dense` rescales cosine so `threshold` maps to 0 and 1.0 maps to 1.

    `mutual` keeps an edge only when BOTH endpoints rank the other in their
    top-k. Plain kNN is asymmetric and hub-prone: one generic memory lands in
    everyone's neighbour list and single-handedly welds unrelated groups into
    one component. Requiring reciprocity is what actually separates clusters
    here — the threshold alone only shifts where the single blob forms.
    """
    import numpy as np

    n = mat.shape[0]
    if n < 2:
        return {}
    unit = _unit_rows(mat)
    kk = min(k, n - 1)
    neighbors: list[set[int]] = [set() for _ in range(n)]
    cos_of: dict[tuple[int, int], float] = {}
    block = max(1, min(n, 512))
    for start in range(0, n, block):
        stop = min(n, start + block)
        sims = unit[start:stop] @ unit.T
        for local, row in enumerate(sims):
            i = start + local
            row[i] = -1.0  # no self-edge
            top = np.argpartition(row, -kk)[-kk:]
            for j in top:
                j = int(j)
                cos = float(row[j])
                if cos <= threshold:
                    continue
                neighbors[i].add(j)
                key = (i, j) if i < j else (j, i)
                cos_of[key] = cos

    out: dict[tuple[int, int], float] = {}
    for (i, j), cos in cos_of.items():
        if mutual and not (j in neighbors[i] and i in neighbors[j]):
            continue
        out[(i, j)] = (cos - threshold) / (1.0 - threshold)
    return out


def _concept_sim(
    sets: dict[int, set[int]], idf: dict[int, float], ids: list[int],
) -> dict[tuple[int, int], float]:
    """Sparse idf-weighted cosine over the concept space → `{(i,j): s}`.

    Accumulated through the inverted index rather than pairwise, so cost is
    driven by the concept space's df (already capped at `hub_df_frac * N`)
    instead of N^2.
    """
    pos = {eid: i for i, eid in enumerate(ids)}
    inverted: dict[int, list[int]] = defaultdict(list)
    for eid, cs in sets.items():
        if eid not in pos:
            continue
        for c in cs:
            inverted[c].append(pos[eid])

    num: dict[tuple[int, int], float] = defaultdict(float)
    for c, members in inverted.items():
        w = idf.get(c, 0.0) ** 2
        if w <= 0 or len(members) < 2:
            continue
        members = sorted(members)
        for a_idx in range(len(members)):
            for b_idx in range(a_idx + 1, len(members)):
                num[(members[a_idx], members[b_idx])] += w

    mass = [0.0] * len(ids)
    for eid, cs in sets.items():
        if eid not in pos:
            continue
        mass[pos[eid]] = math.sqrt(sum(idf.get(c, 0.0) ** 2 for c in cs))

    out: dict[tuple[int, int], float] = {}
    for (a, b), v in num.items():
        denom = mass[a] * mass[b]
        if denom > 0:
            out[(a, b)] = v / denom
    return out


# --------------------------------------------------------------- labeling --

# Prose-generic terms that name nothing as a SUBJECT. Deliberately separate
# from `scan._PROMPT_STOPWORDS` (function words), which is applied first: these
# are content words that are perfectly good prompt tokens but useless as the
# name of a group of memories — every corpus has `fixes` and `session` in it,
# so a subject called "fixes" tells a reader nothing about what is inside.
_LABEL_GENERIC = {
    "existing", "fixes", "fix", "session", "sessions", "memory", "memories",
    "feedback", "commit", "commits", "thing", "things", "stuff", "work",
    "change", "changes", "code", "file", "files", "data", "test", "tests",
    "issue", "issues", "problem", "problems", "case", "cases", "note", "notes",
    "one", "same", "other", "others", "new", "old", "next", "last", "first",
    "way", "ways", "part", "parts", "step", "steps", "item", "items",
}
_LABEL_MIN_LEN = 3


def _label_candidate_ok(name: str) -> bool:
    """A label must be a word that could plausibly name a body of work."""
    n = (name or "").strip()
    if len(n) < _LABEL_MIN_LEN or n.isdigit():
        return False
    low = n.lower()
    return low not in _PROMPT_STOPWORDS and low not in _LABEL_GENERIC


def _member_derived_label(
    members: list[int], sets: dict[int, set[int]], by_id: dict,
) -> str:
    """Name a cluster after its richest member when no shared concept survives.

    Beats `unlabeled-N`, which is what shipped before: 6 of 30 clusters here
    carried a positional name that tells a reader nothing and makes the subject
    list unusable as a navigational index. The member with the most concepts is
    the most representative one; its name is at least a real handle back into
    the corpus. Deterministic (name breaks size ties)."""
    if not members:
        return ""
    best = max(members,
               key=lambda e: (len(sets.get(e, ())), by_id.get(e, {}).get("name", "")))
    raw = (by_id.get(best, {}).get("name") or "").strip()
    # Normalize separators FIRST: memory names use either `-` or `_`, and
    # checking the prefix against the raw form let `project-phase-c-shipped`
    # keep the `project` segment while `project_phase_c_shipped` shed it.
    norm = raw.replace("-", "_")
    for prefix in ("project_", "feedback_", "reference_", "savestate_",
                   "guardrail_", "impression_", "subject_"):
        if norm.startswith(prefix):
            norm = norm[len(prefix):]
            break
    parts = [p for p in norm.split("_") if p][:3]
    return "_".join(parts) or norm or raw


def _cluster_label(
    members: list[int], sets: dict[int, set[int]], idf: dict[int, float],
    names: dict[int, str], df_all: Counter, n_total: int, *, top: int = 5,
    by_id: dict | None = None,
) -> tuple[str, list[dict]]:
    """Highest-LIFT shared concept names the cluster; the runners-up become
    its evidence. Deterministic — no model call.

    lift = P(concept | cluster) / P(concept | corpus). A term that is
    ubiquitous inside the cluster and rare outside it wins; a term that is
    merely frequent everywhere scores ~1 and loses. `df_in >= 2` is required
    so a label is always something the cluster SHARES, never one member's
    private vocabulary.
    """
    size = len(members)
    local: Counter = Counter()
    for eid in members:
        for c in sets.get(eid, ()):  # noqa: SIM118 - sets may lack the key
            local[c] += 1
    scored = []
    for c, df_in in local.items():
        if df_in < 2:
            continue
        if not _label_candidate_ok(names.get(c, "")):
            continue
        p_local = df_in / size
        p_global = df_all[c] / max(1, n_total)
        if p_global <= 0:
            continue
        lift = p_local / p_global
        scored.append({
            "concept": names.get(c, str(c)),
            "concept_id": c,
            "lift": round(lift, 3),
            "df_in": df_in,
            "df_all": df_all[c],
            "idf": round(idf.get(c, 0.0), 3),
        })
    # Coverage breaks lift ties: two terms with equal lift, prefer the one
    # more of the cluster actually mentions. Then SHAPE — `existing`,
    # `linkage` and `one` tied at lift 43.667 and the winner was decided
    # alphabetically, which is how a cluster came to be called "existing".
    # An identifier-shaped token (`dual_write`, `csn_typescript`, `KeyError`)
    # is something the project named deliberately; a bare English word is not.
    # Name last, purely for determinism.
    for d in scored:
        d["shape"] = _token_shape_score(d["concept"])
    scored.sort(key=lambda d: (-d["lift"], -d["df_in"], -d["shape"],
                               -d["idf"], d["concept"]))
    if not scored:
        return "", []
    return scored[0]["concept"], scored[:top]


def _crosscutting(
    clusters: list[list[int]], sets: dict[int, set[int]],
    idf: dict[int, float], names: dict[int, str], *, cap: int = 12,
) -> list[dict]:
    """Concepts spanning >= 2 clusters, ranked as BRIDGES and capped.

    Score is `df * idf / (spread - 1)` — evidence, concentrated.

    Both correction terms are load-bearing, and each fixes the other's
    failure. Rewarding spread re-derives the hub list (`fix`, `code`, `use`
    touch every subject and explain nothing) — that is the filler the
    outliers-not-bulk rule exists to exclude, hence the INVERSE spread. But
    ranking on idf alone then hands the top to df=2 noise, since the rarest
    term is by construction the least attested one; `df` restores the
    evidence requirement. What wins is a term attested across many memories
    that nonetheless stays inside two subjects — an unexpected link between
    them, not a word the whole corpus uses.
    """
    where: dict[int, set[int]] = defaultdict(set)
    df: Counter = Counter()
    for ci, members in enumerate(clusters):
        for eid in members:
            for c in sets.get(eid, ()):  # noqa: SIM118
                where[c].add(ci)
                df[c] += 1
    out = []
    for c, cs in where.items():
        if len(cs) < 2:
            continue
        out.append({
            "concept": names.get(c, str(c)),
            "concept_id": c,
            "clusters": sorted(cs),
            "spread": len(cs),
            "df": df[c],
            "score": round(df[c] * idf.get(c, 0.0) / (len(cs) - 1), 3),
        })
    out.sort(key=lambda d: (-d["score"], d["concept"]))
    return out[:cap]


# ------------------------------------------------------------------ plan ---

def compile_memories(
    store: "Store", *,
    k: int = 8,
    threshold: float | None = None,
    threshold_pct: float = 95.0,
    mutual: bool = True,
    beta: float = 1.0,
    gamma: float = 0.5,
    bridge_min: float = 0.35,
    hub_df_frac: float = 0.10,
    min_size: int = 2,
    signal: str = "fused",
    exclude_mtypes: Iterable[str] | None = None,
    max_subjects: int | None = None,
) -> dict:
    """Cluster the partition's memories and return a PLAN (no writes).

    `signal` selects the edge weighting — `fused` (default), `dense`, or
    `concept`. The ablation is a first-class flag rather than a branch to
    delete later: the store already carries hand-declared `part-of` / `amends`
    / `supersedes` edges, which are weak ground truth for scoring the three
    against each other instead of arguing about them.
    """
    from refmatrix.stm import cluster_focus

    if signal not in ("fused", "dense", "concept"):
        raise ValueError(f"signal must be fused|dense|concept, got {signal!r}")

    excl = tuple(exclude_mtypes) if exclude_mtypes is not None \
        else DEFAULT_EXCLUDE_MTYPES
    rows = _memory_rows(store, exclude_mtypes=excl)
    by_id = {r["id"]: r for r in rows}
    stats: dict[str, Any] = {
        "candidates": len(rows), "partition": store._partition_name,
    }

    vec_ids: list[int] = []
    mat = None
    if signal in ("fused", "dense"):
        vec_ids, mat = store.read_vectors(kind="memory", ids=list(by_id))
        vec_ids = [i for i in vec_ids if i in by_id]
    # Concept-only still needs a node set; use every candidate.
    ids = vec_ids if signal in ("fused", "dense") else sorted(by_id)
    stats["embedded"] = len(vec_ids)
    stats["unembedded"] = len(rows) - len(vec_ids)

    if len(ids) < 2:
        return {
            "clusters": [], "crosscutting": [],
            "unclustered": [r["name"] for r in rows],
            "stats": stats,
            "params": _params(k, threshold, threshold_pct, mutual, beta,
                              gamma, bridge_min, hub_df_frac, min_size,
                              signal),
        }

    # Row-align the matrix to `ids` when dense participates.
    if mat is not None and len(vec_ids) == len(ids):
        import numpy as np
        order = {eid: i for i, eid in enumerate(vec_ids)}
        mat = np.asarray([mat[order[e]] for e in ids], dtype="float32")

    sets, idf, cnames = _concept_sets(
        store, set(ids), hub_df_frac=hub_df_frac)
    df_all: Counter = Counter()
    for eid in ids:
        for c in sets.get(eid, ()):  # noqa: SIM118
            df_all[c] += 1
    stats["concept_space"] = len(idf)

    if signal in ("fused", "dense"):
        thr = auto_threshold(mat, threshold_pct) if threshold is None \
            else threshold
        stats["threshold"] = round(thr, 4)
        stats["threshold_auto"] = threshold is None
        dense = _dense_knn(mat, k, thr, mutual=mutual)
    else:
        thr, dense = 0.0, {}
    csim = _concept_sim(sets, idf, ids) if signal in ("fused", "concept") \
        else {}

    # --- fusion -----------------------------------------------------------
    edges: dict[tuple[int, int], dict] = {}
    if signal == "dense":
        for key, w in dense.items():
            edges[key] = {"weight": w, "cos": w, "s": 0.0, "kind": "dense"}
    elif signal == "concept":
        for key, s in csim.items():
            if s >= bridge_min:
                edges[key] = {"weight": s, "cos": 0.0, "s": s,
                              "kind": "concept"}
    else:
        for key, w in dense.items():
            s = csim.get(key, 0.0)
            edges[key] = {"weight": w * (1.0 + beta * s), "cos": w, "s": s,
                          "kind": "confirmed" if s > 0 else "dense"}
        for key, s in csim.items():
            if key in edges or s < bridge_min:
                continue
            edges[key] = {"weight": gamma * s, "cos": 0.0, "s": s,
                          "kind": "bridge"}
    stats["edges"] = len(edges)
    stats["bridges"] = sum(1 for e in edges.values() if e["kind"] == "bridge")
    stats["confirmed"] = sum(
        1 for e in edges.values() if e["kind"] == "confirmed")

    # --- cluster ----------------------------------------------------------
    degree: dict[int, float] = defaultdict(float)
    for (a, b), e in edges.items():
        degree[a] += e["weight"]
        degree[b] += e["weight"]
    names_by_idx = [by_id[e]["name"] for e in ids]
    graph = {
        "nodes": [
            {"name": names_by_idx[i], "weight": round(degree.get(i, 0.0), 4)}
            for i in sorted(range(len(ids)),
                            key=lambda i: (-degree.get(i, 0.0),
                                           names_by_idx[i]))
        ],
        "edges": [
            {"source": names_by_idx[a], "target": names_by_idx[b],
             "weight": e["weight"]}
            for (a, b), e in edges.items()
        ],
    }
    name_to_id = {by_id[e]["name"]: e for e in ids}
    raw_clusters = [
        [name_to_id[n] for n in members if n in name_to_id]
        for members in cluster_focus(graph, min_size=min_size)
    ]
    raw_clusters = [c for c in raw_clusters if len(c) >= min_size]
    if max_subjects is not None:
        dropped = raw_clusters[max_subjects:]
        raw_clusters = raw_clusters[:max_subjects]
        stats["dropped_clusters"] = len(dropped)
        stats["dropped_members"] = sum(len(c) for c in dropped)

    # --- label ------------------------------------------------------------
    clustered: set[int] = set()
    out_clusters = []
    used_labels: Counter = Counter()
    for ci, members in enumerate(raw_clusters):
        label, evidence = _cluster_label(
            members, sets, idf, cnames, df_all, len(ids), by_id=by_id)
        if not label:
            # No shared concept survived: dense grouped these but nothing names
            # them. Fall back to the richest member rather than a positional
            # `unlabeled-N` — the grouping is real, so it deserves a handle a
            # reader can follow back into the corpus.
            label = _member_derived_label(members, sets, by_id)
        if not label:
            label = f"unlabeled-{ci + 1}"
        used_labels[label] += 1
        if used_labels[label] > 1:
            label = f"{label}-{used_labels[label]}"
        clustered.update(members)
        out_clusters.append({
            "label": label,
            "size": len(members),
            "members": [{"id": e, "name": by_id[e]["name"],
                         "mtype": by_id[e]["mtype"]} for e in members],
            "evidence": evidence,
        })

    unclustered = [by_id[e]["name"] for e in ids if e not in clustered]
    return {
        "clusters": out_clusters,
        "crosscutting": _crosscutting(raw_clusters, sets, idf, cnames),
        "unclustered": unclustered,
        "stats": stats,
        "params": _params(k, threshold, threshold_pct, mutual, beta, gamma,
                          bridge_min, hub_df_frac, min_size, signal),
    }


def _params(k, threshold, threshold_pct, mutual, beta, gamma, bridge_min,
            hub_df_frac, min_size, signal) -> dict:
    return {"k": k, "threshold": threshold, "threshold_pct": threshold_pct,
            "mutual": mutual, "beta": beta, "gamma": gamma,
            "bridge_min": bridge_min, "hub_df_frac": hub_df_frac,
            "min_size": min_size, "signal": signal}


# ----------------------------------------------------------------- apply ---

def apply_plan(store: "Store", plan: dict, *, prune: bool = True) -> dict:
    """Write the plan's subjects + `part-of` edges into the active partition.

    Idempotent by construction: subject identity is the slug of its label, and
    with `prune` the compiler's OWN prior leaves are unlinked before re-filing.
    Without that a re-run after the corpus shifts ACCRETES — a memory stays
    filed under last week's subject as well as this week's. Hand-declared
    subjects (no `compiled_by` stamp) are never touched.
    """
    stamp = time.time()
    labels = {c["label"] for c in plan.get("clusters", [])}
    unlinked = 0
    if prune:
        for subj in store.list_subjects():
            meta = subj.get("metadata") or {}
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except (json.JSONDecodeError, TypeError):
                    meta = {}
            if meta.get("compiled_by") != COMPILED_BY:
                continue
            sid = int(subj["id"])
            for leaf in store.subject_leaves(sid):
                if store.unlink("part-of", sid, int(leaf["id"])):
                    unlinked += 1

    subjects, linked = [], 0
    for c in plan.get("clusters", []):
        rec = store.upsert_subject(c["label"], metadata={
            "compiled_by": COMPILED_BY,
            "compiled_at": stamp,
            "size": c["size"],
            "evidence": [e["concept"] for e in c.get("evidence", [])],
            "params": plan.get("params", {}),
        })
        for m in c["members"]:
            if store.link_part_of(int(m["id"]), int(rec["id"])):
                linked += 1
        subjects.append({**rec, "size": c["size"]})
    return {"subjects": subjects, "linked": linked, "unlinked": unlinked,
            "labels": sorted(labels)}


# ------------------------------------------------------------------- gmd ---

def render_gmd(plan: dict, *, doc_id: str = "memory-subjects",
               partition: str | None = None) -> str:
    """Render the plan as a GMD index doc.

    Edges are emitted as `catalogs` from the subject to each leaf, which is
    the correct DIRECTION for a container node (the store's own edge is the
    inverse `part-of`, leaf -> subject). Anyone rebuilding the store from this
    doc inverts one verb; emitting `part-of` here would have claimed the
    subject is part of its own members.
    """
    p = plan.get("params", {})
    st = plan.get("stats", {})
    lines = [
        '---',
        'gmd: "0.1"',
        f'id: {doc_id}',
        'title: "Compiled memory subjects"',
        'tags: [memory, subject, compiled]',
        'metadata:',
        '  node_type: index',
        f'  generator: {COMPILED_BY}',
        f'  partition: {partition or st.get("partition", "?")}',
        f'  signal: {p.get("signal", "fused")}',
        '---',
        '',
        '# Compiled memory subjects {#root}',
        '',
        f'{len(plan.get("clusters", []))} subject(s) derived from '
        f'{st.get("embedded", 0)} embedded memories '
        f'({st.get("candidates", 0)} candidates, '
        f'{st.get("unembedded", 0)} unembedded). '
        f'Edges: {st.get("edges", 0)} '
        f'({st.get("confirmed", 0)} concept-confirmed, '
        f'{st.get("bridges", 0)} concept-only bridges). '
        f'Concept space: {st.get("concept_space", 0)} informative concepts.',
        '',
        'Derived, not authored — regenerate with `rmx memory compile`. Labels '
        'are the highest-lift shared concept; evidence lists the concepts that '
        'actually bound each group.',
        '',
    ]
    for i, c in enumerate(plan.get("clusters", []), 1):
        anchor = f"subject-{i}"
        lines.append(f'## {c["label"]} {{#{anchor}}}')
        lines.append('')
        ev = ", ".join(
            f'`{e["concept"]}` (lift {e["lift"]}, {e["df_in"]}/{c["size"]})'
            for e in c.get("evidence", []))
        lines.append(f'{c["size"]} member(s). Evidence: {ev or "none"}.')
        lines.append('')
        for m in c["members"]:
            lines.append(f'- [[{m["name"]}]] — {m["mtype"]}')
        lines.append('')
        for m in c["members"]:
            lines.append(f'rel: catalogs -> [[{m["name"]}]]')
        lines.append('')
    cross = plan.get("crosscutting", [])
    if cross:
        lines += ['## Crosscutting concepts {#crosscutting}', '',
                  'Concepts spanning two or more subjects, ranked by '
                  'df x idf / (spread - 1) — attested but concentrated, so '
                  'sparse bridges outrank corpus-wide hubs.', '']
        for x in cross:
            span = ", ".join(f'[[#subject-{ci + 1}]]' for ci in x["clusters"])
            lines.append(
                f'- `{x["concept"]}` — {x["spread"]} subjects, '
                f'{x.get("df", 0)} memories (score {x["score"]}): {span}')
        lines.append('')
    unc = plan.get("unclustered", [])
    if unc:
        lines += ['## Unclustered {#unclustered}', '',
                  f'{len(unc)} memory(ies) had no edge clearing the '
                  f'thresholds. Not an error — an honest floor.', '']
        lines += [f'- [[{n}]]' for n in unc]
        lines.append('')
    return "\n".join(lines).rstrip() + "\n"


def default_out_path(root: Path) -> Path:
    """Where the index lands when `--out` is not given.

    NOT the memory dir: a doc written there is re-ingested as a memory on the
    next `sync-disk`, so the compiler's own output would join the corpus it
    clusters and grow a feedback loop. Pass `--out` explicitly to put it in the
    memory dir on purpose.
    """
    return Path(root) / "compiled" / "subjects.md"
