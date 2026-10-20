"""M4 (hypertree spike 2026-10-20): render token cost, tree render vs today's flat bundle.

Measurement only, never imported by `src/`. Opens the COPY of a store's snapshot
(`<SPIKE_ROOT>/<store>/catalog.duckdb`) with `Store(read_only=True)`; never a live store,
never a daemon, the hub or models.sock (reranker=None; HF_HUB_OFFLINE=1; helix_pending is
cleared before rendering so no helix flush happens).

Bundles are the PRODUCTION bundles (`build_context` / `content_only_bundle`); only the
renderer differs between arms. Every arm renders the SAME entries:

  flat       production `render_text(b)` (today)
  flat_rel   production `render_text(b)` with paths made root-relative (the cheap Option-A fix)
  tree_grp   per-linkage-group path trees: shared dir prefixes printed once, entries under
             their file node, the file part dropped from names the file node already shows;
             snippet/tldr/body lines identical
  tree_one   one path tree per bundle, linkage carried as a tag on each entry

Metric: tokens per distinct covered entity, per query (production `estimate_tokens`,
chars/4; plus tiktoken cl100k when importable).

Query sources:
  prompts    (refmatrix only) seeded sample of logged scan-prompt bodies (query.log, kind=scan,
             ts >= 2026-09-20, deduped). scan_prompt's bundle set is reproduced: content bundle
             over the candidate bag + build_context per matched concept (ppr-ranked, top 5,
             cross-section dedup), per-concept budget 600, max_entities 10.
  concepts   (every store; the LABELLED VARIANT) seeded 200 concept names with mentions df>=2,
             not in the `keyword/` namespace, each as one build_context anchor.
Raw prompt text is never written; only sha256 hashes.
"""
from __future__ import annotations

import argparse
import copy
import dataclasses
import hashlib
import json
import os
import random
import statistics
import sys
import time
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import RESULTS, SEED, SPIKE_ROOT, STORES, copy_db  # noqa: E402

from refmatrix.store import Store  # noqa: E402
from refmatrix import context as ctx  # noqa: E402
from refmatrix import scan  # noqa: E402

try:
    import tiktoken
    _ENC = tiktoken.get_encoding("cl100k_base")
except Exception:  # tokenizer optional; chars/4 is the production estimator
    _ENC = None

ARMS = ("flat", "flat_rel", "tree_grp", "tree_one")
PER_CONCEPT_TOKENS = 600
MAX_ENT = 10


def tok(text: str) -> dict:
    out = {"est": ctx.estimate_tokens(text)}
    if _ENC is not None:
        out["cl100k"] = len(_ENC.encode(text, disallowed_special=()))
    return out


# ---------------------------------------------------------------- path helpers
def _rel(p: str | None, root: str) -> str | None:
    if not p:
        return p
    r = root.rstrip("/") + "/"
    return p[len(r):] if p.startswith(r) else p


def _relativize(b: ctx.ContextBundle, root: str) -> ctx.ContextBundle:
    nb = copy.copy(b)
    nb.groups = {}
    for ln, es in b.groups.items():
        out = []
        for e in es:
            e2 = copy.copy(e)
            e2.entity = dataclasses.replace(e.entity, path=_rel(e.entity.path, root))
            e2.file = _rel(e.file, root)
            out.append(e2)
        nb.groups[ln] = out
    if b.anchor is not None:
        nb.anchor = dataclasses.replace(b.anchor, path=_rel(b.anchor.path, root))
    return nb


def _loc_parts(e: ctx.ContextEntry, root: str) -> tuple[str | None, str]:
    """(root-relative file path or None, location tail such as ':123' or ':1,5,9')."""
    blk, _ = ctx._location_block(e)
    if not blk:
        return None, ""
    loc = blk[0].strip()
    path = e.file or e.entity.path
    if e.linkage == "content" and e.entity.kind == "code":
        path = e.entity.path
    if path and loc.startswith(path):
        tail = loc[len(path):]
    else:
        # loc is "path:line" — split on the last ':' whose suffix is numeric-ish
        head, sep, t = loc.rpartition(":")
        if sep and t.replace(",", "").replace("(", "").replace(")", "").replace("+", "").isdigit():
            path, tail = head, ":" + t
        else:
            path, tail = loc, ""
    return _rel(path, root), tail


def _short_name(e: ctx.ContextEntry, relpath: str, abspath: str | None) -> str:
    n = e.entity.name
    for p in (relpath, abspath or ""):
        if p and n.startswith(p + "::"):
            return n[len(p) + 2:]
        if p and n == p:
            return ""
    return n


def _entry_tail_lines(e: ctx.ContextEntry) -> list[str]:
    """The entry's payload lines (snippet / tldr / body) exactly as production renders them,
    minus the naming line and the location line."""
    e2 = copy.copy(e)
    e2.file = None
    e2.entity = dataclasses.replace(e.entity, path=None)
    if e2.linkage == "content":
        pass  # _single_location returns None without a path
    return ctx._render_entry(e2).split("\n")[1:]


def _entry_head(e: ctx.ContextEntry, short: str, tail: str, tag: str | None) -> str:
    s = f"{short}{tail}" if short else (tail.lstrip(":") and f"@{tail.lstrip(':')}" or "")
    s = s or "·"
    s += f"  [{e.entity.kind}{'|' + tag if tag else ''}]"
    if e.weight is not None:
        s += f"  (w={e.weight:g})"
    return s


def _tree_lines(entries: list[ctx.ContextEntry], root: str, tagged: bool) -> list[str]:
    """Compact path tree: single-child directory chains collapse into one node; two spaces
    per level; entries without a path render flat, as today, after the tree."""
    tree: dict = {}
    loose: list[ctx.ContextEntry] = []
    for e in entries:
        relp, tail = _loc_parts(e, root)
        if not relp:
            loose.append(e)
            continue
        parts = [x for x in relp.split("/") if x]
        node = tree
        for d in parts[:-1]:
            node = node.setdefault(d + "/", {})
        leaf = node.setdefault(parts[-1], {"__entries__": []})
        if "__entries__" not in leaf:
            leaf["__entries__"] = []
        leaf["__entries__"].append((e, relp, tail))

    out: list[str] = []

    def walk(node: dict, depth: int) -> None:
        for key in sorted(k for k in node if k != "__entries__"):
            child = node[key]
            label = key
            # collapse single-child directory chains
            while (label.endswith("/") and len([k for k in child if k != "__entries__"]) == 1
                   and "__entries__" not in child
                   and next(iter(child)).endswith("/")):
                k2 = next(iter(child))
                label += k2
                child = child[k2]
            ind = "  " * (depth + 1)
            if not label.endswith("/"):  # file node
                out.append(f"{ind}{label}")
                for e, relp, tail in child.get("__entries__", []):
                    short = _short_name(e, relp, e.file or e.entity.path)
                    out.append(f"{ind}  {_entry_head(e, short, tail, e.linkage if tagged else None)}")
                    out.extend(f"{ind}{ln}" for ln in _entry_tail_lines(e))
                walk({k: v for k, v in child.items() if k != "__entries__"}, depth + 1)
            else:
                out.append(f"{ind}{label}")
                walk(child, depth + 1)

    walk(tree, 0)
    for e in loose:
        line = f"  {e.entity.name}  [{e.entity.kind}{'|' + e.linkage if tagged else ''}]"
        if e.weight is not None:
            line += f"  (w={e.weight:g})"
        out.append(line)
        out.extend(_entry_tail_lines(e))
    return out


def _render_common_head(b: ctx.ContextBundle) -> list[str]:
    """Header + anchor block, identical to production (taken from its own output)."""
    flat = ctx.render_text(b).split("\n")
    head = []
    for ln in flat:
        if b.groups and any(ln == f"{ctx.LINKAGE_LABELS.get(g, g.upper())} ({g}):" for g in b.groups):
            break
        head.append(ln)
    # drop the trailing blank line that precedes the first group
    while head and head[-1] == "":
        head.pop()
    return head


def _footer(b: ctx.ContextBundle) -> list[str]:
    out = []
    if b.truncated:
        out += ["", "[truncated by budget]"]
    out += ["", f"[~{b.estimated_tokens} tokens, {b.total_entities()} neighbors, degree={b.degree}]"]
    return out


def render_tree(b: ctx.ContextBundle, root: str, one: bool) -> str:
    if not b.groups:
        return ctx.render_text(b)
    lines = _render_common_head(b)
    if one:
        lines += ["", "NEIGHBORS:"]
        allents = [e for es in b.groups.values() for e in es]
        lines += _tree_lines(allents, root, tagged=True)
        for ln in b.groups:
            note = ctx._completeness_note(b, ln)
            if note:
                lines.append(f"  {note}")
    else:
        for ln, es in b.groups.items():
            lines += ["", f"{ctx.LINKAGE_LABELS.get(ln, ln.upper())} ({ln}):"]
            lines += _tree_lines(es, root, tagged=False)
            note = ctx._completeness_note(b, ln)
            if note:
                lines.append(f"  {note}")
    lines += _footer(b)
    return "\n".join(lines)


def render_all(b: ctx.ContextBundle, root: str) -> dict[str, str]:
    b.helix_pending = []
    return {
        "flat": ctx.render_text(b),
        "flat_rel": ctx.render_text(_relativize(b, root)),
        "tree_grp": render_tree(b, root, one=False),
        "tree_one": render_tree(b, root, one=True),
    }


def _ekey(e: ctx.ContextEntry):
    return ("id", e.entity.id) if e.entity.id else ("name", e.entity.name)


# ---------------------------------------------------------------- bundle sources
def prompt_bundles(s: Store, prompt: str) -> list[ctx.ContextBundle]:
    """scan_prompt's bundle set (text mode), reranker=None, grep backstop off."""
    cands = scan.extract_candidates(prompt)
    matches = scan.match_concepts(s, cands, exclude_namespaces=("keyword",), include_noise=False)
    if matches:
        matches = scan._ppr_rerank(s, matches, max_concepts=5)
    matches = scan._dedup_twin_concepts(matches)[:5]
    out: list[ctx.ContextBundle] = []
    shown: set[str] = set()
    if cands:
        cb = ctx.content_only_bundle(s, " ".join(cands), max_tokens=PER_CONCEPT_TOKENS,
                                     max_entities=MAX_ENT, grep_backstop=False, degree=0,
                                     reranker=None)
        if cb.groups:
            out.append(cb)
            for es in cb.groups.values():
                for e in es:
                    shown.add(scan._render_key(e.entity.name))
    for name in matches:
        b = ctx.build_context(s, name, max_tokens=PER_CONCEPT_TOKENS, max_entities=MAX_ENT,
                              degree=0, grep_backstop=False)
        if b.anchor is None or not b.groups:
            continue
        if shown:
            for ln in list(b.groups):
                kept = [e for e in b.groups[ln] if scan._render_key(e.entity.name) not in shown]
                if kept:
                    b.groups[ln] = kept
                else:
                    del b.groups[ln]
            if not b.groups:
                continue
        out.append(b)
        for es in b.groups.values():
            for e in es:
                shown.add(scan._render_key(e.entity.name))
    return out


def sample_prompts(store: str, n: int, rnd: random.Random) -> list[str]:
    seen, bodies = set(), []
    for line in open(SPIKE_ROOT / store / "query.log", errors="replace"):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("kind") != "scan" or r.get("ts", "") < "2026-09-20":
            continue
        body = (r.get("body") or "").strip()
        if body and body not in seen:
            seen.add(body)
            bodies.append(body)
    return rnd.sample(bodies, min(n, len(bodies))), len(bodies)


def sample_concepts(store: str, pid: int, n: int, rnd: random.Random) -> list[str]:
    import duckdb
    c = duckdb.connect(copy_db(store), read_only=True)
    rows = c.execute(
        """SELECT e.name FROM entity_links el
           JOIN linkage_types lt ON lt.id = el.linkage_id
           JOIN entities e ON e.id = el.concept_id
           JOIN entities m ON m.id = el.entity_id
           WHERE lt.name = 'mentions' AND e.kind = 'concept' AND m.partition_id = ?
             AND m.kind != 'concept' AND e.name NOT LIKE 'keyword/%'
           GROUP BY e.name HAVING count(DISTINCT el.entity_id) >= 2
           ORDER BY e.name""", [pid]).fetchall()
    c.close()
    names = [r[0] for r in rows]
    return rnd.sample(names, min(n, len(names))), len(names)


# ---------------------------------------------------------------- measure
def measure_query(bundles: list[ctx.ContextBundle], root: str) -> dict | None:
    ents = set()
    toks = {a: {"est": 0, "cl100k": 0} for a in ARMS}
    for b in bundles:
        for es in b.groups.values():
            for e in es:
                ents.add(_ekey(e))
        r = render_all(b, root)
        for a in ARMS:
            t = tok(r[a])
            toks[a]["est"] += t["est"]
            toks[a]["cl100k"] += t.get("cl100k", 0)
    if not ents:
        return None
    return {"entities": len(ents), "tokens": toks}


def summarize(rows: list[dict]) -> dict:
    out: dict = {"n_queries": len(rows),
                 "entities_mean": statistics.mean(r["entities"] for r in rows) if rows else 0}
    for unit in ("est", "cl100k"):
        if unit == "cl100k" and _ENC is None:
            continue
        u: dict = {}
        tot_ent = sum(r["entities"] for r in rows)
        for a in ARMS:
            per = [r["tokens"][a][unit] / r["entities"] for r in rows]
            u[a] = {"tokens_per_entity_mean": statistics.mean(per),
                    "tokens_per_entity_median": statistics.median(per),
                    "aggregate_tokens_per_entity": sum(r["tokens"][a][unit] for r in rows) / tot_ent}
        base = u["flat"]["aggregate_tokens_per_entity"]
        for a in ARMS:
            agg = u[a]["aggregate_tokens_per_entity"]
            u[a]["aggregate_saving_vs_flat"] = 1 - agg / base
            u[a]["median_per_query_saving_vs_flat"] = statistics.median(
                1 - r["tokens"][a][unit] / r["tokens"]["flat"][unit] for r in rows)
            # same fixed budget: how many more entities fit (ratio estimate)
            u[a]["more_entities_at_fixed_budget"] = base / agg - 1
        rel = u["flat_rel"]["aggregate_tokens_per_entity"]
        for a in ("tree_grp", "tree_one"):
            u[a]["saving_vs_flat_rel"] = 1 - u[a]["aggregate_tokens_per_entity"] / rel
        out[unit] = u
    best = max(out["est"]["tree_grp"]["aggregate_saving_vs_flat"],
               out["est"]["tree_one"]["aggregate_saving_vs_flat"])
    out["band"] = (">=25%: tree render default" if best >= 0.25 else
                   "10-25%: opt-in flag" if best >= 0.10 else "<10%: keep flat")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("store", choices=sorted(STORES))
    ap.add_argument("--n", type=int, default=200)
    a = ap.parse_args()
    root_live, pid = STORES[a.store]
    copy_dir = SPIKE_ROOT / a.store
    assert ".refmatrix" not in str(copy_dir)
    s = Store(copy_dir, partition=a.store, read_only=True)
    assert str(s.db_path).startswith(str(SPIKE_ROOT)), s.db_path
    print(f"store={a.store} db={s.db_path}", flush=True)
    res: dict = {"store": a.store, "partition_id": pid, "seed": SEED,
                 "db": str(s.db_path), "tokenizers": ["chars/4"] + (["cl100k"] if _ENC else []),
                 "per_concept_tokens": PER_CONCEPT_TOKENS, "max_entities": MAX_ENT,
                 "deviations": ["reranker=None (production uses the hub worker when up)",
                                "grep_backstop=False on every bundle (on a copy its root is "
                                "the spike dir; scan-prompt's content bundle has it off anyway)",
                                "scan-prompt's 2000-token cross-bundle cut not applied: every "
                                "bundle is rendered in all arms"]}
    t0 = time.time()
    sources = []
    if a.store == "refmatrix":
        prompts, pool = sample_prompts(a.store, a.n, random.Random(SEED))
        sources.append(("prompts", prompts, pool))
    concepts, cpool = sample_concepts(a.store, pid, a.n, random.Random(SEED))
    sources.append(("concepts", concepts, cpool))
    for label, qs, pool in sources:
        rows, hashes, empty = [], [], 0
        for i, q in enumerate(qs):
            bundles = (prompt_bundles(s, q) if label == "prompts" else
                       [ctx.build_context(s, q, max_tokens=PER_CONCEPT_TOKENS,
                                          max_entities=MAX_ENT, degree=0,
                                          grep_backstop=False)])
            m = measure_query(bundles, root_live)
            hashes.append(hashlib.sha256(q.encode()).hexdigest()[:16])
            if m is None:
                empty += 1
            else:
                rows.append(m)
            if (i + 1) % 25 == 0:
                print(f"  {label} {i + 1}/{len(qs)} ({time.time() - t0:.0f}s)", flush=True)
        summ = summarize(rows)
        summ.update({"pool_size": pool, "sampled": len(qs), "empty_bundles": empty,
                     "query_sha256_16": hashes})
        res[label] = summ
        print(json.dumps({k: v for k, v in summ.items() if k != "query_sha256_16"}, indent=2),
              flush=True)
    res["elapsed_s"] = round(time.time() - t0, 1)
    RESULTS.mkdir(parents=True, exist_ok=True)
    with open(RESULTS / f"m4_{a.store}.json", "w") as f:
        json.dump(res, f, indent=2)


if __name__ == "__main__":
    main()
