"""bug-178 AC-3 timing harness: `pagerank.store_scores` on 50,000 entities, DuckDB backend.

Not a pass/fail test. Run once at HEAD (before GREEN) and once after, on the same machine, and
record both in workflow/plans/task-bug178-bulk-write-helper.md (#measured-head / AC-3). The
pre-registered bar is the new path >= 5x faster; less than that is reported, not lowered.

    PYTHONPATH=<checkout>/src <dev venv python> workflow/measurements/bug178-store-scores.py \
        2>&1 | tee workflow/review-output/bug178-store-scores-<label>.log

A throwaway store under a short /tmp root; never a live store. The timed call is the production
function on a real Store (the benchmark path IS the production path). Each rep replaces the
partition's rows (DELETE + insert), exactly as a daemon PageRank pass does.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ENTITIES = 50_000
REPS = 3


def main() -> None:
    os.environ["RMX_LOG"] = "0"                       # facts.log is not what is measured
    os.environ.setdefault("RMX_HOME", tempfile.mkdtemp(prefix="b178h", dir="/tmp"))
    from refmatrix import __file__ as pkg_file, pagerank
    from refmatrix.store import Store

    base = Path(tempfile.mkdtemp(prefix="b178m", dir="/tmp"))
    s = Store(base / ".refmatrix", backend="duckdb")
    s.init()
    try:
        ids: list[int] = []
        for i in range(0, ENTITIES, 5_000):
            ids += s.bulk_upsert_entity(
                [("doc", f"m{j:06d}", None, None, None) for j in range(i, i + 5_000)])
        scores = {eid: (k % 997) / 13.0 for k, eid in enumerate(ids)}
        walls = []
        for rep in range(REPS):
            t0 = time.perf_counter()
            n = pagerank.store_scores(s, scores, now=float(rep))
            walls.append(time.perf_counter() - t0)
            assert n == ENTITIES
        got = s._connect().execute("SELECT COUNT(*) FROM pagerank").fetchone()[0]
        assert got == ENTITIES, got
    finally:
        s.close()
        shutil.rmtree(base, ignore_errors=True)

    repo = Path(pkg_file).resolve().parents[2]
    sha = subprocess.run(["git", "-C", str(repo), "rev-parse", "--short", "HEAD"],
                         capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", str(repo), "diff", "--quiet", "--", "src"]).returncode
    print(json.dumps({
        "sha": sha, "src_dirty": bool(dirty), "src": str(Path(pkg_file).parent),
        "entities": ENTITIES, "reps": REPS,
        "wall_s": [round(w, 3) for w in walls], "best_s": round(min(walls), 3),
        "python": sys.version.split()[0],
    }, indent=1))


if __name__ == "__main__":
    main()
