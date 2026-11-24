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

# Surfaces whose pool this harness cannot size. Their `_meta.depth` is null and
# their ceilings are NOT comparable to a depth-N ceiling (ch-bsd r2 #b-6-r2).
DEPTH_UNCONTROLLED = frozenset({"scan", "scan-nocontent"})


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
          *, ks: list[int], mode: str, depth: int = 0,
          failed: "list[str] | None" = None) -> dict:
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

    # A DEAD surface and a surface that found nothing both score 0.000. The
    # error branch printed to stderr and left no trace in the artifact, so a
    # method that failed on every question was indistinguishable in the
    # committed JSON and in REPORT.md (ch-bsd r1 #s-13). Carry it.
    failed = list(failed or [])
    summary: dict = {"_meta": {"mode": mode, "depth": depth,
                               "n_failed": len(failed),
                               "failed_ids": failed[:50]}}
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
    # The surface asks for the cross-encoder. Its `_meta` then carries `n_reranked`: a rerank
    # that could not run falls back to the dense order and is NOT a rerank answer (bug-303).
    rerank: bool = False


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
    """scan-prompt is DEPTH-UNCONTROLLED. `k` is deliberately unused.

    Two wrong answers preceded this one, both mine:

    1. It silently accepted `k` and dropped it, while `_meta["depth"]` recorded
       50, the table printed it, and REPORT.md's #1 next step was "re-run at
       --depth 200" — which would have moved `context` and left `scan`
       byte-identical (ch-bsd r1 #b-6).
    2. It then translated depth into `--max-tokens`. Measured by ch-bsd r2:
       `--max-tokens 1` and `--max-tokens 100000` return the SAME 11,931 bytes
       in JSON mode. The budget binds in text mode only — `scan.py` cuts at
       `matches[:max_concepts]` before any budgeting and the `fmt == "json"`
       branch emits every match unconditionally. `--max-concepts` did not move
       it either. So the second fix was a second guess (ch-bsd r2 #b-6-r2).

    Rather than guess a third constant, this surface is now labelled honestly:
    it has no depth knob this harness knows how to turn, `DEPTH_UNCONTROLLED`
    marks it, and `score()` records `depth: null` for it so no reader can
    compare its ceiling against a depth-50 ceiling. Finding the real knob needs
    a budget-bound prompt and a measurement, and is a deferral, not a constant.
    """
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
                        "same retrieval, cross-encoder reordering", rerank=True),
    "recall-fuse-rr": Method(lambda q, *, k: _recall_argv(q, k=k, fuse=True, rerank=True),
                             rerank=True),
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

WARNING_PREFIX = "# rmx: warning: "


def _rmx_json(argv: list[str], rmx: str, root: Path,
              warnings: "list[str] | None" = None) -> object:
    """Run one `rmx` read and parse its JSON payload.

    `warnings`, when given, receives what the call SAID besides its answer: every
    `# rmx: warning: …` stderr line, and a dict payload's own `warnings`. `memory recall
    --json` prints a bare list of rows and says a skipped rerank only on stderr ("rerank
    skipped: …; hits unreranked"); discarding stderr on exit 0 is how T0.6 published 86
    dense answers as `recall-rr` rows (bug-303, 2026-11-24).
    """
    env = rmx_env()
    env["REFMATRIX_ROOT"] = str(root)
    p = subprocess.run([rmx, *argv], env=env, capture_output=True, text=True,
                       timeout=300)
    if p.returncode != 0:
        raise RuntimeError(f"rmx {' '.join(argv[:3])} -> exit {p.returncode}\n"
                           f"{p.stderr[-600:]}")
    if warnings is not None:
        warnings.extend(ln[len(WARNING_PREFIX):].strip()
                        for ln in p.stderr.splitlines() if ln.startswith(WARNING_PREFIX))
    out = p.stdout.strip()
    if not out:
        return None
    try:
        payload = json.loads(out)
    except ValueError:
        # Some surfaces prepend a human line before the JSON payload.
        payload = json.loads(out.splitlines()[-1])
    if warnings is not None and isinstance(payload, dict):
        warnings.extend(w for w in payload.get("warnings") or [] if isinstance(w, str))
    return payload


def payload_reranked(payload) -> bool:
    """Did the cross-encoder order this answer? True when a returned row carries `reranked`.

    The recall verb marks every row it reranked (`"reranked": True`) and returns the dense
    rows unmarked when the rerank was skipped or failed; the same test the CLI's own table
    uses to pick its score column (bug-089). An empty answer was not reranked.
    """
    rows = payload
    if isinstance(payload, dict):
        rows = payload.get("memories") or payload.get("hits") or []
    return isinstance(rows, list) and any(
        isinstance(r, dict) and r.get("reranked") for r in rows)


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
             depth: int, workers: int
             ) -> tuple[dict[str, list[str]], list[str], "dict | None"]:
    """Run one surface over every question. Deep — `restricted` filters after.

    Returns `(rankings, failed_ids, rerank)`. The failure list is the half that
    used to go only to stderr: without it the artifact cannot tell a dead surface
    from an empty one (ch-bsd r1 #s-13).

    `rerank` is None unless the surface asks for the cross-encoder. Then it counts
    the answered questions whose rows came back reranked (`n_reranked`), the ones
    that came back in the dense order (`n_rerank_skipped`, `unreranked_ids`), and
    every distinct warning text the calls printed, with its count. The same
    blindness as #s-13, one leg further in: `--rerank` falls back to the dense
    order and says so on stderr, which this function used to drop, so T0.6's
    `-rr` rows were 72-86 of 120 dense answers under a rerank label (bug-303,
    bsd-t06 r1 #b-1, 2026-11-24).
    """
    m = METHODS[method]
    wants_rerank = bool(getattr(m, "rerank", False))

    def one(q: dict) -> tuple[str, list[str], bool, bool, list[str]]:
        ws: list[str] = []
        try:
            payload = _rmx_json(m.argv(q["question"], k=depth), rmx, root, warnings=ws)
            return (q["question_id"], session_ids(payload), False,
                    payload_reranked(payload), ws)
        except Exception as exc:
            # Say so on stderr AND report it upward.
            print(f"  ! {method} {q['question_id']}: {exc}", file=sys.stderr)
            return q["question_id"], [], True, False, ws

    with ThreadPoolExecutor(max_workers=workers) as ex:
        rows = list(ex.map(one, questions))
    rerank = None
    if wants_rerank:
        answered = [r for r in rows if not r[2]]
        texts: dict[str, int] = {}
        for r in rows:
            for w in r[4]:
                texts[w] = texts.get(w, 0) + 1
        unreranked = [r[0] for r in answered if not r[3]]
        rerank = {"n_reranked": sum(1 for r in answered if r[3]),
                  "n_rerank_skipped": len(unreranked),
                  "unreranked_ids": unreranked[:50],
                  "rerank_warnings": dict(sorted(texts.items()))}
        for w, n in rerank["rerank_warnings"].items():
            print(f"  ! {method}: {n}x warning: {w}", file=sys.stderr)
    return ({r[0]: r[1] for r in rows},
            [r[0] for r in rows if r[2]], rerank)


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
    dep = meta.get("depth")
    head = (f"\n  === {method}  [mode={meta['mode']} "
            + (f"depth={dep}" if dep is not None else "depth=UNCONTROLLED"))
    if "recall_ceiling" in meta:
        head += f" ceiling={meta['recall_ceiling']:.3f}"
    if meta.get("n_failed"):
        # Loud in the table, not just in the JSON: a 0.000 with failures behind
        # it is not a retrieval result.
        head += f" FAILED={meta['n_failed']}"
    if "n_reranked" in meta:
        # As loud: an `-rr` row with dense answers behind it is not a rerank result (bug-303).
        head += f" reranked={meta['n_reranked']}/{meta.get('n_questions', '?')}"
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
        rankings, failed, rerank = rank_all(method, questions, rmx=a.rmx, root=a.root,
                                            depth=a.depth, workers=a.workers)
        elapsed = round(time.time() - t0, 1)
        (RESULTS / f"rank-{method}.json").write_text(
            json.dumps(rankings, indent=1), encoding="utf8")
        for mode in modes:
            s = score(rankings, questions, qrels, haystacks, ks=ks, mode=mode,
                      depth=(None if method in DEPTH_UNCONTROLLED else a.depth),
                      failed=failed)
            s["_meta"]["retrieve_s"] = elapsed
            s["_meta"]["n_questions"] = len(questions)
            if rerank is not None:
                s["_meta"].update(rerank)
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
