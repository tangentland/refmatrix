#!/usr/bin/env python3
"""bug-070: how WIDE is the index match, and does narrowing it cost reach?

`Store.grep_evidence` is THE index-backed grep read — bug-067 collapsed three
divergent copies into it, and the daemon op plus both CLI branches call it. So
this measures the production read path, not a bespoke one
(`feedback_measure_the_path_users_run`).

THE QUESTION. bug-067 made the match also consult `canonical_name`, which is
what lets a LEARNED `query/roaring bitmap` be found by the query that created
it. It did that with a SUBSTRING predicate, and on a short punctuated pattern
that joins a whole family: `rmx grep 'error:'` went from 0 index rows to 62,
because `canonicalize_name('error:')` is `error` and `%error%` matches every
`error`-ish concept name. bug-070 is that breadth: "a caller who asked for a
narrower thing now gets the family."

WHAT THIS MEASURES, AND WHAT IT DELIBERATELY DOES NOT.

  * BREADTH, the complaint itself: index rows and DISTINCT CONCEPTS one lookup
    draws from. A lookup for `error:` that draws on 26 concepts is the defect
    stated in its own terms.
  * REACH, the number not to lose: whether the pattern gets an index answer at
    all. The same predicate bought the spelling bridge (`roaring bitmap` ->
    `roaring_bitmap`), and an exact match that kills the family must not kill
    that too.
  * NOT precision against a literal `rg` control. The first version of this
    script did that and reported 0.000 for every multi-word pattern — BY
    CONSTRUCTION, because the bridge's whole job is to answer a space-spelled
    query from underscore-spelled evidence, so the evidence lines do not
    contain the literal. That number would have indicted the mechanism it was
    built to protect. Precision stays measured where it is meaningful: the
    replay harness scores LEARNED `query/*` rows, whose evidence came from a
    floor result and does contain the literal
    (`grep_learning_replay.score_against_control`, median 1.000).

HOW TO RUN IT — two arms, one bit different, same store:

    # build once and keep it
    eval/production/grep_evidence_precision.py --build --root /tmp/b070
    # arm A, at HEAD
    eval/production/grep_evidence_precision.py --root /tmp/b070 --out A.json
    # apply the predicate change, then arm B over the SAME rows
    eval/production/grep_evidence_precision.py --root /tmp/b070 --out B.json

Reusing the store is the point: a rebuilt corpus would make the two arms differ
in more than the predicate.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

# The patterns bug-070 names (the punctuated ones the canonical predicate
# newly reaches, and the two the row records as OLDER breadth), plus the
# multi-word ones the row credits the same predicate with reaching. A measure
# of the fix has to carry both halves or it is a measure of one of them.
PATTERNS = [
    # bug-070's outliers
    "error:", " error: ", "ERROR", "timeout",
    # the reach the canonical predicate bought (spelling bridge)
    "roaring bitmap", "build context", "scan prompt", "derive status",
    "memory recall", "grep evidence", "learn queue", "replica bundle",
    # ordinary single tokens, as a control group
    "pagerank", "canonicalize", "bitmap", "partition",
]


def build(root: Path, corpus: list[Path]) -> dict:
    """Copy the corpus, init, and ingest through the production path."""
    root.mkdir(parents=True, exist_ok=True)
    for src in corpus:
        dst = root / src.name
        if not dst.exists():
            shutil.copytree(src, dst, symlinks=False,
                            ignore_dangling_symlinks=True)
    rmx = REPO / ".venv-eval" / "bin" / "rmx"
    hooks = root / "hooks"
    hooks.mkdir(exist_ok=True)
    import os
    env = dict(os.environ)
    env["REFMATRIX_ROOT"] = str(root / ".refmatrix")
    env["RMX_CLAUDE_HOOKS_DIR"] = str(hooks)
    env["RMX_LEARN"] = "1"
    subprocess.run([str(rmx), "init"], cwd=str(root), env=env,
                   capture_output=True, text=True)
    ing = subprocess.run([str(rmx), "ingest", str(root)], cwd=str(root),
                         env=env, capture_output=True, text=True)
    if ing.returncode != 0:
        raise SystemExit(f"ingest failed:\n{ing.stderr}")
    return {"built": str(root)}


def measure(root: Path) -> dict:
    """Breadth and reach per pattern, straight off the production read."""
    from refmatrix.store import Store

    s = Store(root / ".refmatrix")
    rows = []
    try:
        for pat in PATTERNS:
            ev = s.grep_evidence(pat, limit=None)
            concepts = sorted({r["concept"] for r in ev})
            rows.append({
                "pattern": pat,
                "index_rows": len(ev),
                "distinct_concepts": len(concepts),
                "answered": bool(ev),
                "concepts_sample": concepts[:8],
            })
    finally:
        s.close()
    return {
        "rows": rows,
        "patterns": len(rows),
        "answered": sum(1 for r in rows if r["answered"]),
        "total_index_rows": sum(r["index_rows"] for r in rows),
        "total_distinct_concepts": sum(r["distinct_concepts"] for r in rows),
        "max_concepts": max((r["distinct_concepts"] for r in rows), default=0),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", required=True)
    ap.add_argument("--corpus", nargs="*", default=["src", "docs"])
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    root = Path(a.root)
    if a.build:
        print(build(root, [REPO / c for c in a.corpus]))
        return
    res = measure(root)
    print(f"answered {res['answered']}/{res['patterns']} patterns; "
          f"{res['total_index_rows']} index rows, "
          f"{res['total_distinct_concepts']} concept draws, "
          f"max {res['max_concepts']} concepts on one lookup")
    for r in res["rows"]:
        print(f"  {r['pattern']!r:18} rows={r['index_rows']:<5} "
              f"concepts={r['distinct_concepts']:<4} "
              f"{'' if r['answered'] else 'NO INDEX ANSWER'}")
    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=2))
        print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
