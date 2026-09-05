#!/usr/bin/env python3
"""Paired per-query comparison of two structural-signal settings.

The arms share a query set, so the mean MRR difference is the wrong statistic:
most queries are untouched by a prior, and their identical ranks dilute the
mean toward zero regardless of how decisively the affected ones moved. What
matters is how many queries CHANGED and in which direction.
"""
from __future__ import annotations

import argparse, os, random, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from known_item import _passages, LEAD_SKIP  # noqa: E402
from baseline_rederive import _body_lines, _q_merge  # noqa: E402


def ranks_for(s, samples, env, limit):
    for k, v in env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    out = []
    for q, gold in samples:
        hits = s.content_rank(q.split(), limit=limit)
        out.append(next((i + 1 for i, (e, _) in enumerate(hits) if e in gold), 0))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/Volumes/littlebig/cq/.refmatrix")
    ap.add_argument("--partition", default="cliquedb")
    ap.add_argument("--n", type=int, default=400)
    ap.add_argument("--seed", type=int, default=20260903)
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--var", required=True, help="env var to toggle")
    ap.add_argument("--val", required=True)
    ap.add_argument("--off", default=None,
                    help="explicit OFF-arm value, for knobs whose default is "
                         "already on (RMX_BOOST_LEAD): unset != off.")
    ap.add_argument("--construction", choices=("lines", "merge"),
                    default="lines",
                    help="query construction: `lines` = the 09-03 verbatim "
                         "rule (comparability); `merge` = cross-line dedup, "
                         "the arm with rank-histogram headroom.")
    a = ap.parse_args()

    os.environ["REFMATRIX_ROOT"] = a.root
    os.environ["RMX_PARTITION"] = a.partition
    from refmatrix.store import Store
    s = Store(a.root, read_only=True); con = s._connect()

    by_path: dict[str, set] = {}
    for r in con.execute("SELECT id, path FROM entities WHERE partition_id=? "
                         "AND path IS NOT NULL AND kind IN ('doc','memory')",
                         (s._partition_id,)).fetchall():
        by_path.setdefault(str(r[1]), set()).add(int(r[0]))
    for r in con.execute("SELECT id, path FROM entities WHERE partition_id=? "
                         "AND path IS NOT NULL", (s._partition_id,)).fetchall():
        p = str(r[1])
        if p in by_path:
            by_path[p].add(int(r[0]))

    rnd = random.Random(a.seed)
    paths = [p for p in by_path if Path(p).exists()]
    rnd.shuffle(paths)
    samples = []
    for p in paths:
        if len(samples) >= a.n:
            break
        if a.construction == "merge":
            q = _q_merge(_body_lines(Path(p)))
        else:
            q = _passages(Path(p), rnd)
        if q:
            samples.append((q, by_path[p]))

    off = ranks_for(s, samples, {a.var: a.off}, a.limit)
    on = ranks_for(s, samples, {a.var: a.val}, a.limit)

    def rr(r): return 1.0 / r if r > 0 else 0.0
    better = sum(1 for x, y in zip(off, on) if rr(y) > rr(x))
    worse = sum(1 for x, y in zip(off, on) if rr(y) < rr(x))
    same = len(off) - better - worse
    d = (sum(rr(y) for y in on) - sum(rr(x) for x in off)) / len(off)
    print(f"  {a.var}={a.val}  n={len(off)}")
    print(f"    changed: {better+worse}/{len(off)}  better={better}  worse={worse}  "
          f"unchanged={same}")
    print(f"    mean dMRR={d:+.4f}   net={better-worse:+d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
