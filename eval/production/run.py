#!/usr/bin/env python3
"""Score the PRODUCTION pipeline: rmx ingest -> rmx embed -> rmx context.

Everything here goes through the `rmx` CLI against a real store. No adapter
class, no direct `Store` writes, no bespoke tokenizer. What this measures is
what a user gets.

Conditions differ only in how the corpus was INGESTED:

    nobody     `rmx ingest --semantic` with RMX_INGEST_BODIES=0
    semantic   `rmx ingest --semantic`

Both run the SAME pass and build the same graph — same concepts, same mentions
edges, same links. The only difference is whether the docstring is written as
the entity's body. That is the isolation.

`plain` (a bare `rmx ingest`) is also available and is NOT a valid control: a
plain ingest of Python extracts no concepts at all, so `content_rank` has no
index and scores 0.0000 on every metric. Comparing plain to semantic measures
whether the store was indexed, not whether nodes could describe themselves.

Metrics come from `eval/metrics.py` — the same MRR/Recall/nDCG the CSN table
uses. The absolute numbers are NOT comparable to `eval/results/REPORT.md`: this
is a subsample, which makes the haystack smaller and retrieval easier. Compare
conditions to each other, never to that table.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))          # eval/ for metrics
try:
    from metrics import all_metrics
finally:
    sys.path.pop(0)


def _run(cmd: list[str], env: dict, *, timeout: int = 3600) -> str:
    p = subprocess.run(cmd, env=env, capture_output=True, text=True,
                       timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(
            f"{' '.join(cmd[:4])}... -> {p.returncode}\n{p.stderr[-1200:]}")
    return p.stdout


def _env(root: Path) -> dict:
    e = dict(os.environ)
    e["REFMATRIX_ROOT"] = str(root)
    e["RMX_INVOCATION_SOURCE"] = "eval"
    e.pop("RMX_PARTITION", None)
    return e


def build_store(rmx: str, corpus: Path, root: Path, *, semantic: bool,
                bodies: bool = True, phrases: bool = False) -> dict:
    """Fresh store, real ingest, real embed. Returns timings."""
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    env = _env(root)
    if not bodies:
        env["RMX_INGEST_BODIES"] = "0"
    env["RMX_INGEST_PHRASES"] = "1" if phrases else "0"
    out: dict = {}

    _run([rmx, "init"], env)
    # No watcher: the corpus never changes under us, and a watcher on an eval
    # store is just a source of nondeterminism.
    _run([rmx, "daemon", "start", "--no-watch"], env, timeout=180)
    time.sleep(3)
    try:
        t0 = time.time()
        cmd = [rmx, "ingest", str(corpus)]
        if semantic:
            cmd.append("--semantic")
        _run(cmd, env, timeout=7200)
        out["ingest_s"] = round(time.time() - t0, 1)

        t0 = time.time()
        _run([rmx, "embed", "--kinds", "code"], env, timeout=7200)
        out["embed_s"] = round(time.time() - t0, 1)
    finally:
        pass
    return out


def body_stats(rmx: str, root: Path) -> dict:
    """What ingest actually wrote — the thing the other harnesses cannot see."""
    import duckdb
    active = (root / "active")
    slot = active.read_text().strip() if active.exists() else None
    path = root / (f"catalog.{slot}.duckdb" if slot else "catalog.duckdb")
    con = duckdb.connect(str(path), read_only=True)
    tot, withb, avg = con.execute(
        "SELECT count(*), sum(CASE WHEN coalesce(tldr,'')<>'' THEN 1 ELSE 0 END), "
        "avg(length(coalesce(tldr,''))) FROM entities WHERE kind='code'"
    ).fetchone()
    con.close()
    return {"code_entities": tot, "with_body": withb or 0,
            "avg_body_chars": round(avg or 0, 1)}


def _entity_to_doc(name: str, file_to_doc: dict[str, str]) -> "str | None":
    """Map a returned entity name back to its corpus doc id.

    Entities arrive as `unit_123.py`, `unit_123.py::fn`, or an absolute path;
    the file stem is the join key.
    """
    if not name:
        return None
    stem = name.split("::", 1)[0].replace("\\", "/").rsplit("/", 1)[-1]
    return file_to_doc.get(stem)


def _rank_scores(ordered_docs: list[str]) -> dict[str, float]:
    """Reciprocal-rank scores, first occurrence wins.

    The metrics only read the ORDER, so any strictly-decreasing score works;
    1/rank keeps a run file readable. Deduped because one corpus file yields
    both a module entity and its function entities, and both map to the same
    doc id."""
    out: dict[str, float] = {}
    rank = 0
    for doc in ordered_docs:
        if doc and doc not in out:
            rank += 1
            out[doc] = 1.0 / rank
    return out


def retrieve_symbolic(rmx: str, root: Path, query: str, *, k: int,
                      file_to_doc: dict[str, str],
                      degree: int = 0) -> dict[str, float]:
    """`rmx context` — BM25 over the mentions index, plus the graph walk.
    `degree>0` adds the seeded-PPR expansion (0.63.0) — the candidate-set
    A/B this harness exists for."""
    env = _env(root)
    cmd = [rmx, "context", query, "--format", "json",
           "--max-entities", str(k)]
    if degree:
        cmd += ["--degree", str(degree)]
    try:
        raw = _run(cmd, env, timeout=300)
        payload = json.loads(raw)
    except Exception:
        return {}

    found: list[str] = []

    def walk(node) -> None:
        if isinstance(node, dict):
            for key in ("name", "entity", "path"):
                v = node.get(key)
                if isinstance(v, str) and v:
                    doc = _entity_to_doc(v, file_to_doc)
                    if doc:
                        found.append(doc)
                    break
            for v in node.values():
                if isinstance(v, (dict, list)):
                    walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(payload)
    return _rank_scores(found)


def retrieve_dense(rmx: str, root: Path, query: str, *, k: int,
                   file_to_doc: dict[str, str]) -> dict[str, float]:
    """`rmx recall` — pure dense ANN over the code vectors.

    This is the surface the body work should move if it moves anything: the
    vector for a code entity is produced by `embedder._extract_code`, which
    concatenates name + `tldr`. With no body that is a filename; with one it
    is the docstring.
    """
    env = _env(root)
    try:
        raw = _run([rmx, "recall", query, "-k", str(k), "-K", "code",
                    "--json"], env, timeout=300)
        payload = json.loads(raw.strip().splitlines()[-1])
    except Exception:
        return {}
    return _rank_scores(
        [_entity_to_doc(h.get("name") or "", file_to_doc) for h in payload]
    )


SURFACES = {"symbolic": retrieve_symbolic, "dense": retrieve_dense}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, required=True,
                    help="Directory written by prepare.py")
    ap.add_argument("--rmx", default="rmx")
    ap.add_argument("--condition", action="append",
                    choices=["plain", "nobody", "semantic", "phrases"],
                    default=None)
    ap.add_argument("--k", type=int, default=20)
    ap.add_argument("--surface", action="append",
                    choices=sorted(SURFACES), default=None,
                    help="Read surface(s) to score. Default: both.")
    ap.add_argument("--limit", type=int, default=0,
                    help="Cap queries (0 = all in the manifest).")
    ap.add_argument("--context-degree", type=int, default=0,
                    help="Pass --degree N to rmx context on the symbolic "
                         "surface (seeded-PPR expansion A/B).")
    ap.add_argument("--reuse-store", action="store_true",
                    help="Skip ingest/embed when the condition's store "
                         "already exists — retrieval-knob A/Bs share one "
                         "build.")
    a = ap.parse_args()

    manifest = json.loads((a.data / "manifest.json").read_text())
    corpus = a.data / "corpus"
    file_to_doc = {f: d for d, f in manifest["doc_to_file"].items()}
    qids = sorted(manifest["queries"])
    if a.limit:
        qids = qids[:a.limit]
    qrels = {q: {manifest["gold"][q]: 1} for q in qids}

    conditions = a.condition or ["nobody", "semantic"]
    a.surface = a.surface or sorted(SURFACES)
    report: dict[str, dict] = {}
    for cond in conditions:
        root = a.data / f"store-{cond}" / ".refmatrix"
        if a.reuse_store and root.exists():
            print(f"\n=== {cond}: reusing store ===", flush=True)
            env = _env(root)
            subprocess.run([a.rmx, "daemon", "start", "--no-watch"],
                           env=env, capture_output=True)
            time.sleep(3)
            timings = {}
        else:
            print(f"\n=== {cond}: building store ===", flush=True)
            timings = build_store(a.rmx, corpus, root,
                                  semantic=(cond != "plain"),
                                  bodies=(cond != "nobody"),
                                  phrases=(cond == "phrases"))
        stats = body_stats(a.rmx, root)
        print(f"  {timings} {stats}", flush=True)

        for surface in a.surface:
            fn = SURFACES[surface]
            run: dict[str, dict[str, float]] = {}
            t0 = time.time()
            kw = ({"degree": a.context_degree}
                  if surface == "symbolic" and a.context_degree else {})
            for i, q in enumerate(qids, 1):
                run[q] = fn(a.rmx, root, manifest["queries"][q],
                            k=a.k, file_to_doc=file_to_doc, **kw)
                if i % 100 == 0:
                    print(f"  {surface} {i}/{len(qids)}", flush=True)
            m = {k: round(v, 4) for k, v in all_metrics(run, qrels).items()}
            m.update(timings); m.update(stats)
            m["retrieve_s"] = round(time.time() - t0, 1)
            tag = (f"{cond}/{surface}@d{a.context_degree}"
                   if surface == "symbolic" and a.context_degree
                   else f"{cond}/{surface}")
            report[tag] = m
            print(f"  {tag}: MRR@10={m['MRR@10']} "
                  f"R@1={m['Recall@1']} R@10={m['Recall@10']}", flush=True)
        subprocess.run([a.rmx, "daemon", "stop"], env=_env(root),
                       capture_output=True)

    res_path = a.data / "results.json"
    merged: dict = {}
    if res_path.exists():
        try:
            merged = json.loads(res_path.read_text())
        except ValueError:
            merged = {}
    merged.update(report)
    res_path.write_text(json.dumps(merged, indent=1))
    print("\n" + "=" * 72)
    keys = ["MRR@10", "Recall@1", "Recall@10", "nDCG@10"]
    print(f"{'condition/surface':22s} " + " ".join(f"{k:>10s}" for k in keys)
          + f" {'bodies':>8s} {'avg_chars':>10s}")
    for cond, m in report.items():
        print(f"{cond:22s} " + " ".join(f"{m.get(k, 0):10.4f}" for k in keys)
              + f" {m.get('with_body', 0):8d} {m.get('avg_body_chars', 0):10.1f}")
    print(f"\nSUBSAMPLE: {manifest['n_docs']} docs, {len(qids)} queries. "
          f"NOT comparable to eval/results/REPORT.md (43827 docs).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
