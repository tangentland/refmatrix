#!/usr/bin/env python3
"""A/B the reranker's truncation strategy on LongMemEval's oracle split.

The constants in `reranker.py` (`WINDOW_HEAD_FRAC`, `WINDOW_MIN_CHARS`) were
chosen by this measurement, so the measurement has to be re-runnable when the
reranker, `prepare.py`, or the corpus changes (ch-bsd plan-12 #s-7). The
DATASET stays out of the repo by design (`eval/production/longmemeval/paths.py`
says why); the harness does not.

What it measures is COVERAGE, not ranking: for every answer-bearing turn, does
that turn survive the cut the reranker applies? Both arms see the same
documents, the same questions and the same char budget, so the per-pair model
cost is identical and only the strategy differs.

    python3 eval/production/rerank_window_ab.py \
        --oracle /Volumes/littlebig/longmemeval/upstream/longmemeval_oracle

Reports, per limit: covered when the answer is inside the head, covered when it
is past the head, and the totals. The shipped `window_doc` is arm `window`;
`head` is `doc[:limit]`, i.e. the behaviour before bug-032.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "longmemeval"))

# `prepare._as_gmd` renders a session EXACTLY as ingest sees it. Re-implementing
# the rendering here would measure a document the store never held.
from prepare import _as_gmd  # noqa: E402

from refmatrix import reranker as rr  # noqa: E402

# The answer turn counts as "seen" when its first PROBE_CHARS survive the cut.
# Fixed BEFORE the arms were compared and deliberately not re-tuned after: a
# shorter probe raises every number, including the one it would flatter.
PROBE_CHARS = 200


def _session_ids(q: dict) -> list:
    sids = q["haystack_session_ids"]
    if isinstance(sids, str):                 # some rows carry a repr'd list
        sids = json.loads(sids.replace("'", '"'))
    return sids


def run(oracle: Path, limits: "list[int]") -> dict:
    rows = json.loads(oracle.read_text())
    out: dict = {}
    for limit in limits:
        acc = {"head": {"in": 0, "past": 0}, "window": {"in": 0, "past": 0},
               "n_in": 0, "n_past": 0}
        for q in rows:
            question = q["question"]
            for sid, session in zip(_session_ids(q), q["haystack_sessions"]):
                if not any(t.get("has_answer") for t in session):
                    continue
                doc = _as_gmd(sid, "", session)
                head = doc[:limit]
                win = rr.window_doc(doc, question, limit=limit)
                assert len(win) <= limit, (sid, len(win))
                for turn in session:
                    if not turn.get("has_answer"):
                        continue
                    ans = (turn.get("content") or "").strip()
                    if not ans or ans not in doc:
                        continue
                    where = "in" if doc.index(ans) < limit else "past"
                    acc["n_in" if where == "in" else "n_past"] += 1
                    probe = ans[:PROBE_CHARS]
                    acc["head"][where] += probe in head
                    acc["window"][where] += probe in win
        acc["head_total"] = acc["head"]["in"] + acc["head"]["past"]
        acc["window_total"] = acc["window"]["in"] + acc["window"]["past"]
        out[str(limit)] = acc
    return out


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(prog="rerank_window_ab")
    ap.add_argument("--oracle", required=True, type=Path,
                    help="path to the longmemeval_oracle blob")
    ap.add_argument("--limits", default="700,2048",
                    help="comma-separated char budgets to measure")
    ns = ap.parse_args(argv)
    limits = [int(x) for x in ns.limits.split(",") if x.strip()]
    print(json.dumps(run(ns.oracle, limits), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
