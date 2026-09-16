#!/usr/bin/env python3
"""Task 10.1: how much of each scan-prompt injection did the turn already have?

`scan-prompt` fires on every UserPromptSubmit and the agent cannot decline to
pay it, so if consecutive calls re-select the same entries the window is charged
twice for the same bytes. Plan 9 built the instrument that can SEE per-call cost
and cannot answer this: `query.log` stores the query, never the result.

So this replays real prompts and measures the overlap directly.

PRE-REGISTERED (plan-10 Q1, fixed before any number was read):

    median |prev ∩ cur| / |cur| over >= 200 consecutive pairs must be >= 0.40

At or above, build the ledger. Below, the plan stops here and THIS is the
deliverable — `project_helix_log_confounded` is the record of what happens when a
hook surface is reasoned about instead of measured, and task 8.4 is the record of
a negative result being worth shipping.

THREE LIMITATIONS, STATED RATHER THAN BURIED:

  1. `query.log` truncates `body` to 200 chars at write time. A truncated prompt
     can select different concepts than the original did, so this is a proxy for
     the real selection, not a replay of it. Reported with every figure.
  2. `query.log` carries no session id. Consecutive-ness is approximated by a
     timestamp gap cutoff, which is a PARAMETER and appears in the output. A
     wrong grouping rule silently invents or destroys overlap.
  3. Overlap is on ENTRY IDENTITY (name + path:line), never on rendered bytes.
     Two calls picking the same entry but windowing a different snippet line are
     a repeat for dedup purposes; byte-diffing would score them as new.

Read-only: goes through the production CLI against the replica. Opens no writer,
starts no daemon.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_CUTOFF_S = 900          # 15 min gap ends a "session" for grouping
THRESHOLD = 0.40                # plan-10 Q1, pre-registered
MIN_PAIRS = 200                 # plan-10 Q1, pre-registered


def entry_ids(payload) -> set[str]:
    """Identity of every entry a scan-prompt bundle offered.

    `name` plus `path:line` when present — the same entry windowed at a
    different snippet line is the SAME entry for dedup purposes.
    """
    out: set[str] = set()

    def walk(o) -> None:
        if isinstance(o, dict):
            name = o.get("name") or o.get("entity")
            if isinstance(name, str) and name:
                path = o.get("path") or ""
                line = o.get("line")
                out.add(f"{name}@{path}:{line}" if path else name)
            for v in o.values():
                if isinstance(v, (dict, list)):
                    walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(payload)
    return out


def overlap(prev: set[str], cur: set[str]) -> "tuple[float, float] | None":
    """(carried, jaccard). None when either side is empty.

    `carried` = |prev ∩ cur| / |cur| — the fraction of THIS call the turn
    already had, which is what the mechanism would actually save. Jaccard is
    reported beside it so a reader can see set-size effects. An empty side
    contributes NO pair rather than a 0.0 that would drag the median down and
    make the case look worse than it is.
    """
    if not prev or not cur:
        return None
    inter = len(prev & cur)
    return inter / len(cur), inter / len(prev | cur)


def _ts(s: str) -> float:
    return time.mktime(time.strptime(str(s)[:19], "%Y-%m-%dT%H:%M:%S"))


def load_prompts(log: Path, *, limit: int, cutoff_s: int) -> list[list[dict]]:
    """Real `scan` rows from query.log, grouped into runs by a timestamp gap."""
    rows = []
    for line in log.read_text(errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("kind") != "scan" or not (r.get("body") or "").strip():
            continue
        try:
            r["_ts"] = _ts(r["ts"])
        except Exception:
            continue
        rows.append(r)
    rows.sort(key=lambda r: r["_ts"])
    if limit:
        rows = rows[-limit:]

    runs: list[list[dict]] = []
    cur: list[dict] = []
    for r in rows:
        if cur and (r["_ts"] - cur[-1]["_ts"]) > cutoff_s:
            runs.append(cur)
            cur = []
        cur.append(r)
    if cur:
        runs.append(cur)
    return runs


def scan(rmx: str, root: Path, prompt: str, *, max_tokens: int) -> set[str]:
    env = dict(os.environ)
    env["REFMATRIX_ROOT"] = str(root)
    env["RMX_INVOCATION_SOURCE"] = "eval"
    try:
        p = subprocess.run(
            [rmx, "scan-prompt", prompt, "--format", "json",
             "--no-composite", "--max-tokens", str(max_tokens)],
            env=env, capture_output=True, text=True, timeout=120)
        if p.returncode != 0 or not p.stdout.strip():
            return set()
        return entry_ids(json.loads(p.stdout))
    except Exception as exc:
        print(f"  ! scan failed: {exc}", file=sys.stderr)
        return set()


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=Path(".refmatrix"))
    ap.add_argument("--rmx", default="rmx")
    ap.add_argument("--limit", type=int, default=400,
                    help="most recent N scan rows to replay (0 = all)")
    ap.add_argument("--cutoff", type=int, default=DEFAULT_CUTOFF_S,
                    help="seconds of gap that ends a run (grouping rule)")
    ap.add_argument("--max-tokens", type=int, default=2000)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()

    log = a.root / "query.log"
    if not log.exists():
        sys.exit(f"  ! {log} missing")

    runs = load_prompts(log, limit=a.limit, cutoff_s=a.cutoff)
    total = sum(len(r) for r in runs)
    print(f"  ~ {total} scan rows in {len(runs)} run(s) "
          f"(gap cutoff {a.cutoff}s)", flush=True)

    carried: list[float] = []
    jaccard: list[float] = []
    sizes: list[int] = []
    empty = 0
    done = 0
    for run in runs:
        prev: "set[str] | None" = None
        for r in run:
            ids = scan(a.rmx, a.root, r["body"], max_tokens=a.max_tokens)
            done += 1
            if done % 25 == 0:
                print(f"  {done}/{total}", flush=True)
            if ids:
                sizes.append(len(ids))
            else:
                empty += 1
            if prev is not None:
                got = overlap(prev, ids)
                if got:
                    carried.append(got[0])
                    jaccard.append(got[1])
            prev = ids

    if not carried:
        print("  ! no comparable pairs — nothing to decide on")
        return 1

    med = statistics.median(carried)
    result = {
        "pairs": len(carried),
        "replayed": done,
        "runs": len(runs),
        "empty_results": empty,
        "median_carried": round(med, 4),
        "mean_carried": round(statistics.mean(carried), 4),
        "p25_carried": round(statistics.quantiles(carried, n=4)[0], 4)
        if len(carried) > 3 else None,
        "p75_carried": round(statistics.quantiles(carried, n=4)[2], 4)
        if len(carried) > 3 else None,
        "median_jaccard": round(statistics.median(jaccard), 4),
        "median_entries_per_call": statistics.median(sizes) if sizes else 0,
        "grouping": f"consecutive within a run; a gap > {a.cutoff}s ends a run",
        "prompt_source": "query.log body, TRUNCATED TO 200 CHARS at write time "
                         "— a proxy for the real selection, not a replay of it",
        "threshold": THRESHOLD,
        "min_pairs": MIN_PAIRS,
        "verdict": ("BUILD" if (med >= THRESHOLD and len(carried) >= MIN_PAIRS)
                    else "STOP"),
    }
    if len(carried) < MIN_PAIRS:
        result["verdict_note"] = (
            f"only {len(carried)} pairs against a pre-registered minimum of "
            f"{MIN_PAIRS} — UNDERPOWERED, not a negative result")

    print("\n" + json.dumps(result, indent=1))
    print(f"\n  median carried = {med:.3f} vs pre-registered {THRESHOLD} "
          f"-> {result['verdict']}")
    if a.out:
        a.out.write_text(json.dumps(result, indent=1))
        print(f"  + {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
