#!/usr/bin/env python3
"""Layer A: does the retriever find the session that holds the answer?

No LLM, no API cost, deterministic. Every question names its
`answer_session_ids` and `prepare.py` wrote one file per session, so the
retrieval half of LongMemEval is recoverable as a document-level metric that
costs nothing. Run this before ever considering a paid Layer B: if Recall@20 is
at the floor there is no QA accuracy for an answer model to find, and the paid
run is wasted.

Everything goes through the `rmx` CLI. That is the point — `eval/production/`
exists because the older harnesses imported `fuse_rrf` and `Store` and built
their own index with their own tokenizer, which is how four "declared but never
populated" ingest defects survived behind a 0.982 MRR
([[feedback_measure_the_path_users_run]]).

TWO SCORING MODES, and they are never the same number:

  union        the ranked list scored against the whole 19,829-doc store. The
               gold session has to beat every other question's haystack too.
               Harder than anything published, comparable to nobody, and the
               honest picture of what rmx does in production — where no oracle
               hands it a 50-session shortlist.

  restricted   retrieve DEEP through the same CLI call, then filter the ranked
               list to the question's own haystack and cut to k. This is the
               mode comparable to published figures (mcp-memory-service reports
               80.4% Recall@5 / 89.1% MRR on this benchmark).

`restricted` is an APPROXIMATION of per-question retrieval, not the real thing.
`ann_search(candidate_ids=...)` exists in the Python API and no CLI flag exposes
it; reaching past the CLI to use it would make this harness the bespoke path it
was built to replace. The cost of the approximation is that a gold session can
fall outside the deep pool entirely, capping `restricted` for reasons that have
nothing to do with retrieval quality. That cap is the RECALL CEILING, it is
computed every run, and it is printed beside every restricted table. A
`restricted` figure quoted without its ceiling is not a result.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from paths import (HAYSTACKS, QRELS, QUESTIONS, RESULTS, STORE_ROOT, SUBSETS,
                   rmx_env)

MODES = ("union", "restricted")


# ── metrics ────────────────────────────────────────────────────────────────

def recall_at_k(ranked: Sequence[str], rel: set[str], k: int) -> float:
    return len(set(ranked[:k]) & rel) / len(rel) if rel else 0.0


def rr_at_k(ranked: Sequence[str], rel: set[str], k: int) -> float:
    for i, doc in enumerate(ranked[:k], 1):
        if doc in rel:
            return 1.0 / i
    return 0.0


def hit_at_k(ranked: Sequence[str], rel: set[str], k: int) -> float:
    return 1.0 if set(ranked[:k]) & rel else 0.0


# ── the modes ──────────────────────────────────────────────────────────────

def restrict(ranked: Sequence[str], haystack: set[str], k: int) -> list[str]:
    """Filter to the question's own haystack, THEN cut to k.

    Order matters: cutting first would discard haystack members the filter
    would have promoted, which is the entire reason the retrieval goes deep.
    """
    return [d for d in ranked if d in haystack][:k]


def recall_ceiling(rankings: dict[str, list[str]], questions: list[dict],
                   qrels: dict[str, list[str]]) -> float:
    """Fraction of questions whose gold appeared ANYWHERE in the deep pool.

    `restricted` cannot score above this, and a low value indicts the retrieval
    depth rather than rmx. Reported beside every restricted table so the
    approximation is visible instead of silently eating recall.
    """
    n = hits = 0
    for q in questions:
        rel = set(qrels.get(q["question_id"]) or [])
        if not rel:
            continue
        n += 1
        hits += bool(set(rankings.get(q["question_id"]) or []) & rel)
    return hits / n if n else 0.0


def score(rankings: dict[str, list[str]], questions: list[dict],
          qrels: dict[str, list[str]], haystacks: dict[str, list[str]],
          *, ks: list[int], mode: str, depth: int = 0) -> dict:
    """Per-type, abstention, and overall slices for one method under one mode.

    A question with no resolvable gold is NOT scored as a zero — it is excluded
    from the denominator and `prepare.py` already counted and named it. Scoring
    it zero would quietly punish the retriever for a label problem.
    """
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}; expected one of {MODES}")

    by_slice: dict[str, list[dict]] = defaultdict(list)
    for q in questions:
        qid = q["question_id"]
        rel = set(qrels.get(qid) or [])
        if not rel:
            continue
        ranked = list(rankings.get(qid) or [])
        if mode == "restricted":
            ranked = restrict(ranked, set(haystacks.get(qid) or []), max(ks))
        row = {"mrr": rr_at_k(ranked, rel, max(ks))}
        for k in ks:
            row[f"recall@{k}"] = recall_at_k(ranked, rel, k)
            row[f"hit@{k}"] = hit_at_k(ranked, rel, k)
        by_slice[q.get("question_type", "unknown")].append(row)
        if q.get("abstention"):
            by_slice["abstention"].append(row)
        by_slice["overall"].append(row)

    summary: dict = {"_meta": {"mode": mode, "depth": depth}}
    for name, rows in by_slice.items():
        entry = {"n": len(rows)}
        if rows:
            for metric in rows[0]:
                entry[metric] = sum(r[metric] for r in rows) / len(rows)
        summary[name] = entry
    if mode == "restricted":
        summary["_meta"]["recall_ceiling"] = recall_ceiling(
            rankings, questions, qrels)
    return summary


# ── the read surfaces ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class Method:
    """One rmx read surface, as the argv that invokes it.

    `argv` is a plain function of the query so a test can read the command
    without a store — which is the only way the explicit-rerank rule is
    enforceable. 0.42.0 flipped the daemon's rerank default ON; a method that
    passes no flag measures whatever the environment happened to be, and every
    figure taken before that release silently stops being comparable.
    """
    argv: Callable[..., list[str]]
    note: str = ""


def _recall_argv(query: str, *, k: int, fuse: bool, rerank: bool) -> list[str]:
    a = ["memory", "recall", query, "--json", "-k", str(k)]
    if fuse:
        a.append("--fuse")
    a.append("--rerank" if rerank else "--no-rerank")
    return a


def _context_argv(query: str, *, k: int, degree: int = 0) -> list[str]:
    a = ["context", query, "--format", "json", "--max-entities", str(k)]
    if degree:
        a += ["--degree", str(degree)]
    return a


def _scan_argv(query: str, *, k: int, content: bool = True) -> list[str]:
    a = ["scan-prompt", query, "--format", "json", "--no-composite"]
    if not content:
        a.append("--no-content")
    return a


METHODS: dict[str, Method] = {
    "recall": Method(lambda q, *, k: _recall_argv(q, k=k, fuse=False, rerank=False),
                     "dense ANN over bge-small, no rerank"),
    "recall-fuse": Method(lambda q, *, k: _recall_argv(q, k=k, fuse=True, rerank=False),
                          "dense RRF-fused with content_rank BM25"),
    "recall-rr": Method(lambda q, *, k: _recall_argv(q, k=k, fuse=False, rerank=True),
                        "same retrieval, cross-encoder reordering"),
    "recall-fuse-rr": Method(lambda q, *, k: _recall_argv(q, k=k, fuse=True, rerank=True)),
    "context": Method(lambda q, *, k: _context_argv(q, k=k),
                      "symbolic content_rank + graph walk"),
    "context-d2": Method(lambda q, *, k: _context_argv(q, k=k, degree=2),
                         "seeded-PPR expansion, degree 2"),
    "scan": Method(lambda q, *, k: _scan_argv(q, k=k),
                   "the proactive surface the product ships"),
    "scan-nocontent": Method(lambda q, *, k: _scan_argv(q, k=k, content=False),
                             "concept path only — the content bundle masks it"),
}


# ── talking to rmx ─────────────────────────────────────────────────────────

def _rmx_json(argv: list[str], rmx: str, root: Path) -> object:
    env = rmx_env()
    env["REFMATRIX_ROOT"] = str(root)
    p = subprocess.run([rmx, *argv], env=env, capture_output=True, text=True,
                       timeout=300)
    if p.returncode != 0:
        raise RuntimeError(f"rmx {' '.join(argv[:3])} -> exit {p.returncode}\n"
                           f"{p.stderr[-600:]}")
    out = p.stdout.strip()
    if not out:
        return None
    try:
        return json.loads(out)
    except ValueError:
        # Some surfaces prepend a human line before the JSON payload.
        return json.loads(out.splitlines()[-1])


def session_ids(payload) -> list[str]:
    """Pull session ids out of whatever shape a read surface returned.

    The surfaces disagree on envelope (`hits`, `rows`, `neighbors`,
    `memories`) and on whether an id arrives as `name`, `entity`, or a `path`.
    Pinning one shape per command rots the moment an output grows a field, so
    walk the structure in order and keep the first id-looking string per
    record. Order is preserved — these are ranked lists and the rank is the
    measurement.
    """
    out: list[str] = []
    seen: set[str] = set()

    def take(v: str) -> None:
        # Graph nodes arrive anchored (`answer_8ee04a2e_1#root`); grep hits
        # arrive as paths. Qrels are bare session ids — the file stem, minus
        # any anchor.
        sid = Path(v).stem if ("/" in v or v.endswith(".md")) else v
        sid = sid.split("#", 1)[0]
        if sid and sid not in seen:
            seen.add(sid)
            out.append(sid)

    def walk(o) -> None:
        if isinstance(o, dict):
            for key in ("name", "entity", "id", "path", "file"):
                v = o.get(key)
                if isinstance(v, str) and v:
                    take(v)
                    break
            for v in o.values():
                if isinstance(v, (dict, list)):
                    walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(payload)
    return out


def rank_all(method: str, questions: list[dict], *, rmx: str, root: Path,
             depth: int, workers: int) -> dict[str, list[str]]:
    """Run one surface over every question. Deep — `restricted` filters after."""
    m = METHODS[method]

    def one(q: dict) -> tuple[str, list[str]]:
        try:
            return q["question_id"], session_ids(
                _rmx_json(m.argv(q["question"], k=depth), rmx, root))
        except Exception as exc:
            # A dead surface must not be indistinguishable from a surface that
            # found nothing: score it 0 AND say so, with the question id.
            print(f"  ! {method} {q['question_id']}: {exc}", file=sys.stderr)
            return q["question_id"], []

    with ThreadPoolExecutor(max_workers=workers) as ex:
        return dict(ex.map(one, questions))


# ── output ─────────────────────────────────────────────────────────────────

def print_table(method: str, summary: dict, ks: list[int]) -> None:
    meta = summary["_meta"]
    order = ["single-session-user", "single-session-assistant",
             "single-session-preference", "multi-session",
             "temporal-reasoning", "knowledge-update", "abstention", "overall"]
    slices = [s for s in order if s in summary]
    cols = ["mrr"] + [f"recall@{k}" for k in ks] + [f"hit@{k}" for k in ks]
    # `mrr` is reciprocal rank at the deepest reported cutoff; name it so a
    # reader never has to guess which k a bare "MRR" was taken at.
    labels = [f"mrr@{max(ks)}"] + cols[1:]
    head = f"\n  === {method}  [mode={meta['mode']} depth={meta['depth']}"
    if "recall_ceiling" in meta:
        head += f" ceiling={meta['recall_ceiling']:.3f}"
    print(head + "]\n")
    print("  " + "slice".ljust(26) + "n".rjust(5)
          + "".join(c.rjust(11) for c in labels))
    print("  " + "-" * (31 + 11 * len(labels)))
    for s in slices:
        row = summary[s]
        print("  " + s.ljust(26) + str(row["n"]).rjust(5)
              + "".join(f"{row.get(c, 0):.3f}".rjust(11) for c in cols))


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--method", action="append", default=None,
                    help=f"repeatable; default all of {sorted(METHODS)}")
    ap.add_argument("--mode", action="append", default=None, choices=list(MODES),
                    help="repeatable; default both")
    ap.add_argument("--questions", type=Path, default=None,
                    help="question file (default: the full questions.json)")
    ap.add_argument("--subset", type=int, default=None,
                    help="use subsets/stratified-<n>.json instead")
    ap.add_argument("--k", type=int, default=20, help="report cutoff")
    ap.add_argument("--at", default="1,5,10,20")
    ap.add_argument("--depth", type=int, default=200,
                    help="retrieval depth before the restricted filter; the "
                         "recall ceiling is a direct function of this")
    ap.add_argument("--rmx", default="rmx")
    ap.add_argument("--root", type=Path, default=STORE_ROOT)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    qpath = a.questions or (SUBSETS / f"stratified-{a.subset}.json"
                            if a.subset else QUESTIONS)
    questions = json.loads(Path(qpath).read_text(encoding="utf8"))
    if a.limit:
        questions = questions[:a.limit]
    qrels = json.loads(QRELS.read_text(encoding="utf8"))
    haystacks = json.loads(HAYSTACKS.read_text(encoding="utf8"))
    ks = [int(x) for x in a.at.split(",")]
    RESULTS.mkdir(parents=True, exist_ok=True)

    methods = a.method or list(METHODS)
    modes = a.mode or list(MODES)
    report: dict = {}

    for method in methods:
        t0 = time.time()
        rankings = rank_all(method, questions, rmx=a.rmx, root=a.root,
                            depth=a.depth, workers=a.workers)
        elapsed = round(time.time() - t0, 1)
        (RESULTS / f"rank-{method}.json").write_text(
            json.dumps(rankings, indent=1), encoding="utf8")
        for mode in modes:
            s = score(rankings, questions, qrels, haystacks, ks=ks, mode=mode,
                      depth=a.depth)
            s["_meta"]["retrieve_s"] = elapsed
            s["_meta"]["n_questions"] = len(questions)
            print_table(method, s, ks)
            report[f"{method}/{mode}"] = s
            (RESULTS / f"retrieval-{method}-{mode}.json").write_text(
                json.dumps(s, indent=1), encoding="utf8")

    (RESULTS / "summary.json").write_text(json.dumps(report, indent=1),
                                          encoding="utf8")
    print(f"\n  {len(questions)} questions, depth={a.depth}. "
          f"`restricted` is a deep retrieve + post-hoc haystack filter, NOT a "
          f"per-question index — quote it with its ceiling or not at all.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
