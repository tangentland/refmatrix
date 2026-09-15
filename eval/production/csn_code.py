#!/usr/bin/env python3
"""Honest CSN NL→code benchmark: drive the PRODUCTION ingest + read path.

The historical `eval/run.py --model rmx` number (0.972 MRR@10) came from
`eval/retrievers/rmx_retriever.py`, which builds its own index with a bespoke
`_tokenize` + `ast_extract` and per-token `store.add_concept(...)` calls. It
calls `refmatrix.ingest` ZERO times. That is why a true 0.98 sat on top of a
main ingest path that content-indexed almost nothing (43-83% of entities
termless) for months -- the benchmark exercised code users never run
(feedback_measure_the_path_users_run).

This harness measures the path users actually run:

  1. materialize the BEIR corpus as real `<id>.py` files on disk,
  2. `refmatrix.ingest.ingest_path(..., semantic=True)` -- the production
     tree + Python-semantic passes, the exact code `rmx ingest` invokes,
  3. rank each query with `Store.content_rank` -- the exact function
     `rmx context` calls -- mapping the returned code entities back to their
     corpus ids by file stem,
  4. score with the same `eval/metrics.all_metrics` as the old harness so the
     numbers are directly comparable.

No adapter class, no bespoke tokenizer, no direct concept writes. If a defect
lives in the production ingest, this harness sees it; the old one could not.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_HERE.parent))  # eval/ for datasets, metrics

from datasets import load_beir          # noqa: E402
from metrics import all_metrics         # noqa: E402

# Query tokenizer: the READ side of production. `content_rank` takes a bag of
# terms; `rmx context`/`scan-prompt` split the prompt on the same class of
# word boundary. Kept minimal and identical for every query -- the point of
# the harness is that the INDEX is production, not that the query split is
# clever.
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_]{1,}")


def _q_terms(text: str) -> list[str]:
    return [w.lower() for w in _WORD.findall(text)]


def _materialize(corpus: dict, dst: Path, limit: int | None) -> dict[str, str]:
    """Write each corpus doc as `<id>.py`. Returns {stem: corpus_id}."""
    dst.mkdir(parents=True, exist_ok=True)
    stem_to_id: dict[str, str] = {}
    for i, (cid, doc) in enumerate(corpus.items()):
        if limit and i >= limit:
            break
        stem = cid.replace("/", "_")
        (dst / f"{stem}.py").write_text(doc.get("text", ""), encoding="utf-8")
        stem_to_id[stem] = cid
    return stem_to_id


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=str(_ROOT / "eval/datasets/csn_python"))
    ap.add_argument("--workdir", default="/Volumes/littlebig/csn-honest",
                    help="where the .py corpus + store are written (off any "
                         "watched tree)")
    ap.add_argument("--limit-corpus", type=int, default=None,
                    help="cap corpus docs (INVALID for scoring unless every "
                         "sampled query's gold doc is included -- use "
                         "--sample-queries for a valid quick run instead)")
    ap.add_argument("--limit-queries", type=int, default=None)
    ap.add_argument("--sample-queries", type=int, default=None,
                    help="valid quick run: take the first N queries, "
                         "materialize their GOLD docs plus fillers so every "
                         "sampled query is answerable.")
    ap.add_argument("--top-k", type=int, default=1000)
    ap.add_argument("--reuse", action="store_true",
                    help="skip materialize+ingest if the store already exists")
    ap.add_argument("--out", default=None,
                    help="write the metrics + run provenance as JSON here "
                         "(the committed artifact README cites: "
                         "eval/production/results/csn_python/metrics.json)")
    a = ap.parse_args()

    from refmatrix.store import Store
    from refmatrix.ingest import ingest_path

    ds = load_beir(Path(a.dataset))
    print(f"dataset: {ds}")
    work = Path(a.workdir)
    corpus_dir = work / "corpus"
    store_root = work / ".refmatrix"

    t0 = time.time()
    timing: dict[str, float] = {}
    if a.reuse and store_root.exists():
        stem_to_id = {cid.replace("/", "_"): cid for cid in ds.corpus}
        s = Store(store_root)
        print("reusing existing store")
    else:
        import shutil
        if work.exists():
            shutil.rmtree(work)
        if a.sample_queries:
            q_ids = list(ds.queries)[:a.sample_queries]
            gold_cids = {c for q in q_ids for c in ds.qrels.get(q, {})}
            # fillers: corpus docs not already gold, capped so the store stays
            # small but distractors still compete.
            fillers = [c for c in ds.corpus if c not in gold_cids][:5000]
            keep = gold_cids | set(fillers)
            sub = {c: ds.corpus[c] for c in ds.corpus if c in keep}
            stem_to_id = _materialize(sub, corpus_dir, None)
        else:
            stem_to_id = _materialize(ds.corpus, corpus_dir, a.limit_corpus)
        print(f"materialized {len(stem_to_id)} .py files in "
              f"{time.time()-t0:.0f}s")
        s = Store(store_root)
        s.init()
        t1 = time.time()
        timing["materialize_s"] = round(t1 - t0, 1)
        n = ingest_path(s, corpus_dir, source="auto", semantic=True)
        timing["ingest_s"] = round(time.time() - t1, 1)
        print(f"PRODUCTION ingest_path: {n} entities in {time.time()-t1:.0f}s")

    # entity id -> corpus id, by file stem (code entities carry the path)
    con = s._connect()
    eid_to_cid: dict[int, str] = {}
    for eid, path in con.execute(
        "SELECT id, path FROM entities WHERE partition_id=? AND kind='code' "
        "AND path IS NOT NULL", (s._partition_id,)).fetchall():
        stem = Path(str(path)).stem
        cid = stem_to_id.get(stem)
        if cid is not None:
            eid_to_cid[int(eid)] = cid
    print(f"mapped {len(eid_to_cid)} code entities back to corpus ids")

    # rank every query through production content_rank
    q_items = list(ds.queries.items())
    if a.sample_queries:
        q_items = q_items[:a.sample_queries]
    elif a.limit_queries:
        q_items = q_items[:a.limit_queries]
    run: dict[str, dict[str, float]] = {}
    t2 = time.time()
    for qi, (qid, qtext) in enumerate(q_items):
        terms = _q_terms(qtext)
        if not terms:
            run[qid] = {}
            continue
        hits = s.content_rank(terms, kinds=["code"], limit=a.top_k)
        scores: dict[str, float] = {}
        for eid, sc in hits:
            cid = eid_to_cid.get(int(eid))
            if cid is not None:
                scores[cid] = float(sc)
        run[qid] = scores
        if (qi + 1) % 2000 == 0:
            print(f"  {qi+1}/{len(q_items)} queries "
                  f"({(qi+1)/(time.time()-t2):.0f}/s)")
    timing["retrieval_s"] = round(time.time() - t2, 1)
    print(f"retrieval: {len(q_items)} queries in {time.time()-t2:.0f}s")

    qrels = {q: r for q, r in ds.qrels.items() if q in run}
    m = all_metrics(run, qrels)
    print("\n=== PRODUCTION-PATH metrics (csn_python) ===")
    for k, v in m.items():
        print(f"  {k:14s} {v:.4f}")
    if a.out:
        write_artifact(Path(a.out), a, ds, len(stem_to_id), len(q_items), m, timing)
    s.close()
    return 0


def write_artifact(out: Path, a: argparse.Namespace, ds, corpus_docs: int,
                   queries: int, metrics: dict, timing: dict) -> None:
    """The committed provenance record (plan-6 task 6.3, 2026-09-14). Until
    then the headline 0.961 lived in a memory file only; README now cites this
    path and `tests/test_eval_artifact_cited.py` compares the figure. A run is
    `full_run` only when nothing capped the corpus or the query set — a sampled
    run is a valid number about an easier haystack and the docs must say so."""
    from refmatrix import __version__
    full_run = not (a.limit_corpus or a.limit_queries or a.sample_queries)
    sha = subprocess.run(["git", "-C", str(_ROOT), "rev-parse", "--short", "HEAD"],
                         capture_output=True, text=True)
    rec = {
        "harness": "eval/production/csn_code.py",
        "dataset": Path(a.dataset).name,
        "corpus_docs": corpus_docs,
        "corpus_docs_total": len(ds.corpus),
        "queries": queries,
        "queries_total": len(ds.queries),
        "full_run": full_run,
        "sample_queries": a.sample_queries,
        "limit_queries": a.limit_queries,
        "limit_corpus": a.limit_corpus,
        "top_k": a.top_k,
        "metrics": {k: round(float(v), 4) for k, v in metrics.items()},
        "timing_s": timing,
        "refmatrix_version": __version__,
        "git_sha": sha.stdout.strip() if sha.returncode == 0 else f"unknown ({sha.stderr.strip()})",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "command": " ".join(sys.argv),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    raise SystemExit(main())
