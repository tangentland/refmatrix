"""Self-eval: does layering graphify-derived edges on top of rmx's standard
ingest improve retrieval of refmatrix's own internals via NL queries?

Compares two index variants on the refmatrix project itself:

  A. baseline    — tree walk + Python AST semantics + markdown semantics
  B. +graphify   — same + graphify-out/graph.json edges

Runs a hand-curated NL query set with known-correct target entities; reports
MRR@10 and Recall@1/3/10 per variant plus the per-query rank delta.

Usage:
    python eval/run_graphify_eval.py
    python eval/run_graphify_eval.py --top-k 20
"""
from __future__ import annotations

import argparse
import re
import sys
import tempfile
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PROJECT = _HERE.parent
if str(_PROJECT / "src") not in sys.path:
    sys.path.insert(0, str(_PROJECT / "src"))

from refmatrix.ingest import ingest_path
from refmatrix.store import Store


# (NL query, set of substring patterns that mark a correct answer)
# Patterns match against entity name; first match wins for rank scoring.
QUERIES: list[tuple[str, list[str]]] = [
    ("daemon unix socket dispatcher",
        ["daemon.py", "rmxd.sock", "gf/daemon"]),
    ("roaring bitmap fragment flush",
        ["store.py", "flush_fragments", "gf/store"]),
    ("ingest plan or spec doc and emit specifies edge",
        ["ingest.py", "_is_plan_file", "ISSUE-adr-semantic-extraction.md",
         "gf/ingest"]),
    ("graphify graph json ingest",
        ["ingest.py", "_ingest_graphify", "gf/ingest"]),
    ("learn from grep miss promote ripgrep hits to index",
        ["daemon.py", "learn_from_grep", "gf/daemon"]),
    ("RRF reciprocal rank fusion",
        ["query.py", "fuse_rrf", "gf/query"]),
    ("GMD typed rel edges parser",
        ["ingest_gmd.py", "_REL_RE", "gf/ingest_gmd"]),
    ("filesystem watcher debounce",
        ["watch.py", "Debouncer", "gf/watch"]),
    ("incremental sync skip unchanged mtime",
        ["sync.py", "_sync_paths", "gf/sync"]),
    ("install claude code hooks",
        ["hooks.py", "_install_claude_hooks", "gf/hooks"]),
    ("DSL set algebra parser",
        ["query.py", "QueryEngine", "Token", "gf/query"]),
    ("ADR markdown class spec extraction",
        ["ingest.py", "_ingest_adr_semantics", "gf/ingest"]),
    ("context bundle token budget",
        ["context.py", "build_context", "estimate_tokens", "gf/context"]),
    ("scan prompt for user prompt submit hook",
        ["scan.py", "scan_prompt", "gf/scan"]),
    ("DuckDB native catalog schema",
        ["duckdb_catalog.py", "CATALOG_DDL", "gf/duckdb_catalog"]),
    ("partition canonical cross codebase concept",
        ["store.py", "canon", "partition", "gf/store"]),
    ("vacuum drop empty concepts",
        ["store.py", "vacuum", "gf/store"]),
    ("primer density ranked symbol map",
        ["primer.py", "build_primer", "concept_density", "gf/primer"]),
    ("Python AST imports docstring keywords",
        ["ingest.py", "_ingest_python_semantics", "gf/ingest"]),
    ("test plan file emits specifies",
        ["test_ingest_markdown.py", "test_plan_file", "gf/test_ingest_markdown"]),
]


_TOKEN_RE = re.compile(r"[A-Za-z]{3,}")
_STOP = {
    "the", "and", "for", "with", "that", "this", "from", "into", "are",
    "use", "uses", "using", "via", "any", "all",
}


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text) if t.lower() not in _STOP]


def _canon_key(name: str, path: str | None) -> str:
    """Collapse graphify-mirrored entities onto their underlying file so
    `src/refmatrix/daemon.py` and `graphify::daemon_py` don't both occupy
    rank slots. Path wins when present (graphify entities carry path back to
    their source_file). Falls back to the trailing path segment of the name."""
    if path:
        # normalize against project root for stable comparison
        try:
            p = Path(path).resolve()
            if p.is_relative_to(_PROJECT):
                return p.relative_to(_PROJECT).as_posix()
        except (ValueError, OSError):
            pass
        return Path(path).name
    if name.startswith("graphify::"):
        # use the label-ish suffix
        return name.split("::", 1)[1]
    return name


def query_score(store, qe, nl: str, top_k: int) -> list[tuple[int, str]]:
    """Hybrid score per entity, deduped onto canonical file keys so a
    tree-walked file and its graphify mirror don't both consume rank slots.

    (a) Bare-token concept lookup via QueryEngine (entities linked to a
        concept literally named like the token, in a few casings).
    (b) Entity-name substring match — rmx-grep-style fallback.

    The scoring is summed per (entity, token); then we collapse to canonical
    keys keeping the highest-scoring entity for each key."""
    from collections import Counter
    tokens = tokenize(nl)
    counts: Counter = Counter()

    for tok in tokens:
        for cand in (tok, tok.capitalize(), tok.upper()):
            try:
                hits = list(qe.run(cand))
            except Exception:
                hits = []
            for eid in hits:
                counts[eid] += 2

    name_idx: list[tuple[int, str, str | None]] = [
        (e.id, e.name, e.path) for e in store.iter_entities()
    ]
    for eid, name, _ in name_idx:
        low = name.lower()
        for tok in tokens:
            if tok in low:
                counts[eid] += 1

    # Build canon-key → best (score, eid, name) map.
    eid_to_entity = {eid: (name, path) for eid, name, path in name_idx}
    best_by_key: dict[str, tuple[float, int, str]] = {}
    for eid, score in counts.items():
        entry = eid_to_entity.get(eid)
        if entry is None:
            continue
        name, path = entry
        key = _canon_key(name, path)
        if key not in best_by_key or score > best_by_key[key][0]:
            best_by_key[key] = (score, eid, name)

    ranked = sorted(best_by_key.values(), key=lambda t: -t[0])[:top_k]
    return [(eid, name) for _, eid, name in ranked]


def rank_of_first_correct(ranked: list[tuple[int, str]],
                          patterns: list[str]) -> int | None:
    for i, (_, name) in enumerate(ranked, start=1):
        if any(pat in name for pat in patterns):
            return i
    return None


def _scoped_project_root(workdir: Path) -> Path:
    """Copy real subdirs (src/, tests/, docs/) into a clean root so rglob
    doesn't walk .venv-eval/. Symlinks would have been faster but rglob
    won't descend through them. graphify-out/ is symlinked since we only
    read graph.json once via direct path."""
    import shutil
    root = workdir / "proj"
    root.mkdir(parents=True, exist_ok=True)
    for sub in ("src", "tests", "docs"):
        src = _PROJECT / sub
        if src.exists():
            shutil.copytree(src, root / sub, symlinks=False,
                            ignore=shutil.ignore_patterns(
                                "*.pyc", "__pycache__", ".pytest_cache",
                                ".mypy_cache", "*.egg-info"))
    for f in ("README.md", "ISSUE-adr-semantic-extraction.md"):
        sp = _PROJECT / f
        if sp.exists():
            shutil.copy2(sp, root / f)
    gf = _PROJECT / "graphify-out"
    if gf.exists():
        (root / "graphify-out").symlink_to(gf)
    return root


def build_index(variant: str, store_dir: Path, project_root: Path) -> Store:
    s = Store(store_dir)
    s.init()
    if variant == "baseline":
        ingest_path(s, project_root, source="tree", semantic=True)
    elif variant == "graphify_only":
        ingest_path(s, project_root, source="graphify")
    elif variant == "baseline_plus_graphify":
        ingest_path(s, project_root, source="tree", semantic=True)
        ingest_path(s, project_root, source="graphify")
    else:
        raise ValueError(variant)
    return s


def eval_variant(variant: str, top_k: int) -> dict:
    from refmatrix.query import QueryEngine
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        proj = _scoped_project_root(tdp / "wd")
        t0 = time.time()
        s = build_index(variant, tdp / ".refmatrix", proj)
        ingest_sec = time.time() - t0
        qe = QueryEngine(s)

        t1 = time.time()
        ranks: list[int | None] = []
        rows: list[tuple[str, int | None]] = []
        for nl, pats in QUERIES:
            ranked = query_score(s, qe, nl, top_k)
            r = rank_of_first_correct(ranked, pats)
            ranks.append(r)
            rows.append((nl, r))
        query_sec = time.time() - t1
        n_entities = sum(1 for _ in s.iter_entities())
        s.close()

    mrr10 = sum((1.0 / r if r and r <= 10 else 0.0) for r in ranks) / len(ranks)
    rec1 = sum(1 for r in ranks if r is not None and r <= 1) / len(ranks)
    rec3 = sum(1 for r in ranks if r is not None and r <= 3) / len(ranks)
    rec10 = sum(1 for r in ranks if r is not None and r <= 10) / len(ranks)
    miss = sum(1 for r in ranks if r is None)
    return {
        "variant": variant,
        "n_entities": n_entities,
        "ingest_sec": round(ingest_sec, 2),
        "query_sec": round(query_sec, 2),
        "mrr@10": round(mrr10, 4),
        "recall@1": round(rec1, 4),
        "recall@3": round(rec3, 4),
        "recall@10": round(rec10, 4),
        "misses": miss,
        "per_query": rows,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--top-k", type=int, default=50)
    p.add_argument("--show-per-query", action="store_true")
    args = p.parse_args()

    print(f"refmatrix project: {_PROJECT}")
    print(f"queries: {len(QUERIES)}    top_k: {args.top_k}\n")

    results: list[dict] = []
    for v in ("baseline", "graphify_only", "baseline_plus_graphify"):
        print(f"--- {v} ---")
        r = eval_variant(v, args.top_k)
        results.append(r)
        print(f"  entities={r['n_entities']}  "
              f"ingest={r['ingest_sec']}s  query={r['query_sec']}s")
        print(f"  MRR@10={r['mrr@10']}  R@1={r['recall@1']}  "
              f"R@3={r['recall@3']}  R@10={r['recall@10']}  "
              f"misses={r['misses']}/{len(QUERIES)}")

    print("\n=== summary ===")
    print(f"{'variant':<30} {'MRR@10':>8} {'R@1':>6} {'R@3':>6} "
          f"{'R@10':>6} {'miss':>5} {'ents':>6}")
    for r in results:
        print(f"{r['variant']:<30} {r['mrr@10']:>8.4f} {r['recall@1']:>6.3f} "
              f"{r['recall@3']:>6.3f} {r['recall@10']:>6.3f} "
              f"{r['misses']:>5d} {r['n_entities']:>6d}")

    if args.show_per_query:
        print("\n=== per-query rank (lower better; - = miss) ===")
        for i, (nl, _) in enumerate(QUERIES):
            ranks = [r["per_query"][i][1] for r in results]
            rs = "  ".join(f"{('-' if r is None else r):>4}" for r in ranks)
            print(f"  {rs}   {nl[:60]}")

    # Delta highlight
    base = results[0]
    aug = results[-1]
    delta_mrr = aug["mrr@10"] - base["mrr@10"]
    delta_rec10 = aug["recall@10"] - base["recall@10"]
    print(f"\nΔ MRR@10 (baseline → baseline+graphify): {delta_mrr:+.4f}")
    print(f"Δ R@10   (baseline → baseline+graphify): {delta_rec10:+.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
