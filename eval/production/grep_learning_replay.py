#!/usr/bin/env python3
"""Two-arm replay: what does the grep→graph learning loop actually buy?

The loop has run for weeks with its COST measured and bounded (the 30 s wall,
`LEARN_DRAIN_BUDGET_S`, a capped queue) and its BENEFIT uninstrumented. Task
14.1 added `answered_by` to the grep telemetry row so the question is even
askable; this harness asks it.

WHAT IT DOES. Builds two stores from ONE corpus snapshot through the production
ingest path, replays this project's real grep history against both in timestamp
order, and reports the `answered_by` distribution per arm. The arms differ in
exactly one bit — the learning toggle (`RMX_LEARN`) — and the harness does not
have to be trusted on that: every row carries the effective `learn` state
(task 14.1 Q5), so the report asserts the arms were what they claim from the
rows themselves.

WHY THE PRIMARY NUMBER IS A RATIO OVER *ELIGIBLE* CALLS. `_index_may_answer`
is `return not paths`, so the learned index only ever answers exploration
(`rmx grep PATTERN`). A drop-in read that names files is answered by the tool by
contract, and counting that as a learning miss would make the loop look dead
where it is behaving correctly. So the replay issues exploration calls, and
`dropin`/`stdin` are expected to be ~0 — if they are not, the harness is
building calls it did not intend to, which is a harness bug and not a finding.

WHAT THIS HARNESS DOES NOT MEASURE, stated here so the report cannot overclaim:

  * The eligible SHARE of live traffic. `query.log`'s historical rows hold the
    pattern and not the paths, so whether each original call named files is
    unrecoverable. Only forward data from the shipped `answered_by` field can
    say what fraction of real greps the index was ever allowed to answer.
  * The daemon's flush TICK. Learning is asynchronous — the CLI enqueues and the
    daemon drains — and this harness calls `Daemon._drain_learn_queue` (the real
    drain, the same function the tick calls) directly rather than running a
    daemon per arm. Starting throwaway daemons would register throwaway stores
    with the machine's hub, and polluting the live fleet to measure a read path
    is not a trade worth making. The scheduler is therefore out of scope; the
    drain it invokes is in scope.
  * Process startup. Greps are real subprocesses, so startup IS included in the
    latencies reported, but latency is not the question here and the numbers are
    not a performance claim.

Usage:
  eval/production/grep_learning_replay.py                 # full run
  eval/production/grep_learning_replay.py --limit 50       # smoke
  eval/production/grep_learning_replay.py --keep           # leave the arms on disk
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# `rmx` from the DEV venv, deliberately: this harness verifies dev code, and it
# only ever touches throwaway stores under a short mkdtemp root. Never the
# live store — a dev-venv rmx against it trips the hub version handshake and
# restarts the fleet (CLAUDE.md#development-commands).
RMX = REPO / ".venv-eval" / "bin" / "rmx"

# How often the queue is drained during a replay. The real daemon drains on a
# 30 s tick; draining every N patterns reproduces "the teach lands some time
# after the read", which is what makes a later repeat of a pattern able to hit
# the index at all.
DRAIN_EVERY = 25


def read_patterns(log: Path, limit: int = 0) -> list[str]:
    """The grep workload, in timestamp order — order is load-bearing, because
    learning is sequential and a shuffled replay measures a different system."""
    rows = []
    for line in log.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("kind") != "grep":
            continue
        body = r.get("body")
        if isinstance(body, str) and body.strip():
            rows.append((r.get("ts", ""), body))
    rows.sort(key=lambda t: t[0])
    pats = [b for _, b in rows]
    return pats[:limit] if limit else pats


def _env(arm_root: Path, hooks: Path, learn: bool) -> dict:
    e = dict(os.environ)
    e["REFMATRIX_ROOT"] = str(arm_root / ".refmatrix")
    # `rmx init` writes the user-global hooks dir unless redirected, and
    # bug-008's guard refuses that from a dev tree. Redirect it per run so the
    # harness can never touch ~/.claude/hooks.
    e["RMX_CLAUDE_HOOKS_DIR"] = str(hooks)
    e["RMX_LEARN"] = "1" if learn else "0"
    # Telemetry is the instrument here; make sure a developer's env cannot
    # switch off the thing being measured.
    e.pop("REFMATRIX_NO_TELEMETRY", None)
    e["RMX_INVOCATION_SOURCE"] = "internal"
    return e


def build_arm(arm_root: Path, corpus: list[Path], hooks: Path,
              learn: bool) -> dict:
    """Copy the corpus, init a store, ingest through the production path."""
    arm_root.mkdir(parents=True, exist_ok=True)
    for src in corpus:
        dst = arm_root / src.name
        if not dst.exists():
            shutil.copytree(src, dst, symlinks=False, ignore_dangling_symlinks=True)
    env = _env(arm_root, hooks, learn)
    t0 = time.monotonic()
    subprocess.run([str(RMX), "init"], cwd=str(arm_root), env=env,
                   capture_output=True, text=True)
    ing = subprocess.run([str(RMX), "ingest", str(arm_root)], cwd=str(arm_root),
                         env=env, capture_output=True, text=True)
    if ing.returncode != 0:
        raise SystemExit(f"ingest failed for {arm_root}:\n{ing.stderr}")
    return {"ingest_s": round(time.monotonic() - t0, 1),
            "ingest_out": ing.stdout.strip().splitlines()[-1:] or [""]}


def drain(arm_root: Path, learn: bool) -> dict:
    """Run the REAL drain (`Daemon._drain_learn_queue`) once.

    Not a reimplementation: this is the function the daemon's tick calls. With
    learning off it refuses and keeps the queue, which is itself part of what
    the arms are supposed to differ in.
    """
    from refmatrix.daemon import Daemon
    from refmatrix.store import Store

    root = arm_root / ".refmatrix"
    prev = os.environ.get("RMX_LEARN")
    os.environ["RMX_LEARN"] = "1" if learn else "0"
    d = Daemon(root)
    s = Store(root)
    d.store = s
    d._log = lambda m: None
    try:
        t0 = time.monotonic()
        report = d._drain_learn_queue()
        report["drain_s"] = round(time.monotonic() - t0, 2)
        return report
    finally:
        s.close()
        if prev is None:
            os.environ.pop("RMX_LEARN", None)
        else:
            os.environ["RMX_LEARN"] = prev


def learned_concepts(arm_root: Path) -> int:
    """How many `query/*` concepts the arm's store holds."""
    from refmatrix.store import Store

    s = Store(arm_root / ".refmatrix")
    try:
        row = s._connect().execute(
            "SELECT count(*) FROM entities WHERE name LIKE 'query/%'").fetchone()
        return int(row[0]) if row else 0
    finally:
        s.close()


def catalog_bytes(arm_root: Path) -> int:
    root = arm_root / ".refmatrix"
    return sum(p.stat().st_size for p in root.glob("catalog*.duckdb"))


def replay(arm_root: Path, patterns: list[str], hooks: Path, learn: bool,
           verbose: bool = True, drain_every: int = DRAIN_EVERY) -> dict:
    """Issue every pattern as an EXPLORATION call, draining periodically."""
    env = _env(arm_root, hooks, learn)
    mark = _log_lines(arm_root)
    drains: list[dict] = []
    t0 = time.monotonic()
    for i, pat in enumerate(patterns, 1):
        _grep(arm_root, pat, env)
        if drain_every and i % drain_every == 0:
            drains.append(drain(arm_root, learn))
            if verbose:
                print(f"    {i}/{len(patterns)}", end="\r", flush=True)
    drains.append(drain(arm_root, learn))
    wall = round(time.monotonic() - t0, 1)
    rows = _rows_after(arm_root, mark)
    return {
        "calls": len(patterns),
        "rows_written": len(rows),
        "answered_by": dict(Counter(r.get("answered_by") or "missing" for r in rows)),
        "learn_field": dict(Counter(str(r.get("learn")) for r in rows)),
        "cardinality_zero": sum(1 for r in rows if r.get("cardinality") == 0),
        "latency_p50_ms": _pct([r["latency_ms"] for r in rows
                                if isinstance(r.get("latency_ms"), int)], 0.5),
        "wall_s": wall,
        "drain_applied": sum(int(d.get("applied") or 0) for d in drains),
        "drain_s": round(sum(float(d.get("drain_s") or 0) for d in drains), 2),
        "drain_skipped": sorted({d.get("skipped") for d in drains if d.get("skipped")}),
        "queue_pending_end": max((int(d.get("pending") or 0) for d in drains), default=0),
        "learned_concepts": learned_concepts(arm_root),
        "catalog_bytes": catalog_bytes(arm_root),
    }


def _rows_after(arm_root: Path, mark: int) -> list[dict]:
    p = arm_root / ".refmatrix" / "query.log"
    out = []
    for line in p.read_text().splitlines()[mark:]:
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("kind") == "grep":
            out.append(r)
    return out


def _pct(vals: list[int], p: float) -> int:
    if not vals:
        return 0
    vals = sorted(vals)
    return vals[min(len(vals) - 1, int(p * len(vals)))]


def index_vs_control(arm_root: Path, patterns: list[str], hooks: Path,
                     learn: bool, cap: int = 40) -> list[dict]:
    """SECONDARY outcome: when the index answers, is its answer right?

    For each pattern the index served, compare its `file:line` set against a
    REAL-TOOL control over the same corpus. A loop that answers from the index
    with worse rows has made retrieval worse, not better, and the primary
    index/floor ratio cannot see that.
    """
    env = _env(arm_root, hooks, learn)
    grep = shutil.which("grep") or "/usr/bin/grep"
    out: list[dict] = []
    seen: set[str] = set()
    for pat in patterns:
        if pat in seen or len(out) >= cap:
            continue
        seen.add(pat)
        r = _grep(arm_root, pat, env)
        rows = _rows_after(arm_root, 0)
        if not rows or rows[-1].get("answered_by") != "index":
            continue
        idx_pairs = set()
        for line in r.stdout.splitlines():
            head = line.split("  ")[0]
            if ":" in head:
                f, _, ln = head.rpartition(":")
                if ln.isdigit():
                    idx_pairs.add((Path(f).name, int(ln)))
        ctl = subprocess.run([grep, "-rnF", "--", pat, str(arm_root)],
                             capture_output=True, text=True)
        ctl_pairs = set()
        for line in ctl.stdout.splitlines():
            parts = line.split(":", 2)
            if len(parts) >= 2 and parts[1].isdigit():
                ctl_pairs.add((Path(parts[0]).name, int(parts[1])))
        if not ctl_pairs:
            continue
        hit = idx_pairs & ctl_pairs
        out.append({
            "pattern": pat,
            "index_rows": len(idx_pairs),
            "control_rows": len(ctl_pairs),
            "overlap": len(hit),
            "recall": round(len(hit) / len(ctl_pairs), 3),
            "precision": round(len(hit) / len(idx_pairs), 3) if idx_pairs else 0.0,
        })
    return out


def _grep(arm_root: Path, pat: str, env: dict) -> subprocess.CompletedProcess:
    """One exploration call, with the ERE retry the log forces on us.

    `query.log` records the PATTERN and not the flags, so the original
    invocation's `-E` is unrecoverable. A BRE-invalid pattern (`\\(`, `\\|`)
    is rejected by `rmx grep`'s fail-loud guard with exit 2 BEFORE any
    telemetry row is written, and in production the `rmxgrep` wrapper then
    falls back to the real grep — so those calls are invisible to rmx
    entirely. Replaying them bare would score a flag-parsing refusal as a
    learning miss, so a rejected pattern is retried once as ERE, which is what
    the caller almost certainly passed. Approximation, and named as one.
    """
    r = subprocess.run([str(RMX), "grep", "--", pat], cwd=str(arm_root),
                       env=env, capture_output=True, text=True, timeout=120)
    if r.returncode == 2 and "is not supported" in (r.stderr or ""):
        r = subprocess.run([str(RMX), "grep", "-E", "--", pat],
                           cwd=str(arm_root), env=env, capture_output=True,
                           text=True, timeout=120)
        r.args = list(r.args) + ["(ERE retry)"]
    return r


def _log_lines(arm_root: Path) -> int:
    p = arm_root / ".refmatrix" / "query.log"
    return len(p.read_text().splitlines()) if p.exists() else 0


def reachability(arm_root: Path, patterns: list[str], hooks: Path,
                 verbose: bool = True) -> list[dict]:
    """Does a teach ever make the SAME query indexed? One pattern at a time.

    grep (floor, teaches) -> drain -> grep again. This is the loop's own promise
    reduced to its smallest testable form: `rmx grep` says "future searches hit
    the index", and this says for which patterns that is true.

    Needed because the sequential replay cannot separate "learning does not
    help" from "this pattern never repeated in the window". Here every pattern
    repeats, immediately, with its teach already applied — the most generous
    condition the loop can ever be given.
    """
    env = _env(arm_root, hooks, True)
    out: list[dict] = []
    for i, pat in enumerate(patterns, 1):
        before = _log_lines(arm_root)
        _grep(arm_root, pat, env)
        first = _rows_after(arm_root, before)
        d = drain(arm_root, True)
        before2 = _log_lines(arm_root)
        _grep(arm_root, pat, env)
        second = _rows_after(arm_root, before2)
        out.append({
            "pattern": pat,
            "first": (first[-1].get("answered_by") if first else None),
            "first_cardinality": (first[-1].get("cardinality") if first else None),
            "applied": int(d.get("applied") or 0),
            "second": (second[-1].get("answered_by") if second else None),
        })
        if verbose and i % 10 == 0:
            print(f"    {i}/{len(patterns)}", end="\r", flush=True)
    return out


def repeated_patterns(log: Path) -> list[str]:
    """Distinct patterns that occur MORE THAN ONCE in the log — the only ones
    where a within-session teach could ever pay off."""
    pats = read_patterns(log)
    c = Counter(pats)
    seen: list[str] = []
    for p in pats:
        if c[p] > 1 and p not in seen:
            seen.append(p)
    return seen


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--query-log", default=str(REPO / ".refmatrix" / "query.log"))
    ap.add_argument("--corpus", nargs="*", default=["src", "docs"],
                    help="subdirectories of the repo to use as the corpus")
    ap.add_argument("--limit", type=int, default=0, help="0 = every grep row")
    ap.add_argument("--drain-every", type=int, default=DRAIN_EVERY,
                    help="drain the learn queue every N patterns. The real "
                         "daemon drains on a 30 s tick, so a small value is "
                         "GENEROUS to learning: 1 means every teach has landed "
                         "before the next call, which bounds the benefit from "
                         "above rather than reproducing production timing.")
    ap.add_argument("--root", default="", help="short tmp root (default: mkdtemp)")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--secondary", action="store_true",
                    help="also score index answers against a real-grep control")
    ap.add_argument("--reachability", action="store_true",
                    help="measure whether a teach makes the SAME query indexed "
                         "(grep -> drain -> grep, per pattern) instead of "
                         "running the two-arm sequential replay")
    ap.add_argument("--repeated-only", action="store_true",
                    help="restrict the workload to patterns that occur more "
                         "than once in the log")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    if args.repeated_only:
        patterns = repeated_patterns(Path(args.query_log))
        if args.limit:
            patterns = patterns[:args.limit]
    else:
        patterns = read_patterns(Path(args.query_log), args.limit)
    if not patterns:
        raise SystemExit(f"no grep rows in {args.query_log}")
    corpus = [REPO / c for c in args.corpus]
    for c in corpus:
        if not c.is_dir():
            raise SystemExit(f"corpus dir missing: {c}")

    # SHORT root: macOS caps a unix socket path at ~104 bytes, and a long
    # mkdtemp prefix is how daemon tests hang instead of failing.
    root = Path(args.root) if args.root else Path(tempfile.mkdtemp(prefix="rmxR"))
    hooks = root / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    print(f"replay root {root}")
    print(f"workload {len(patterns)} grep calls from {args.query_log}")

    result = {"root": str(root), "calls": len(patterns),
              "drain_every": args.drain_every,
              "corpus": [str(c) for c in corpus], "arms": {}}
    try:
        if args.reachability:
            arm = root / "R_reachability"
            print(f"  building reachability arm ...")
            build = build_arm(arm, corpus, hooks, True)
            print(f"    ingest {build['ingest_s']}s")
            rows = reachability(arm, patterns, hooks)
            became = [r for r in rows if r["second"] == "index"]
            taught = [r for r in rows if r["applied"] > 0]
            result["reachability"] = {
                "patterns": len(rows),
                "taught_something": len(taught),
                "indexed_on_the_second_call": len(became),
                "share_of_taught": (round(len(became) / len(taught), 3)
                                    if taught else 0.0),
                "rows": rows,
            }
            print(f"    taught {len(taught)}/{len(rows)}; indexed on the "
                  f"second call {len(became)}/{len(taught)}")
            text = json.dumps(result, indent=2)
            if args.out:
                Path(args.out).write_text(text)
                print(f"wrote {args.out}")
            else:
                print(text)
            return
        for name, learn in (("A_learning_on", True), ("B_learning_off", False)):
            arm = root / name
            print(f"  building {name} (learn={learn}) ...")
            build = build_arm(arm, corpus, hooks, learn)
            print(f"    ingest {build['ingest_s']}s {build['ingest_out']}")
            baseline = learned_concepts(arm)
            print(f"    replaying {len(patterns)} patterns ...")
            stats = replay(arm, patterns, hooks, learn,
                           drain_every=args.drain_every)
            stats["ingest_s"] = build["ingest_s"]
            stats["learned_concepts_before_replay"] = baseline
            if args.secondary:
                stats["index_vs_control"] = index_vs_control(arm, patterns, hooks, learn)
            result["arms"][name] = stats
            print(f"    {json.dumps(stats['answered_by'])}  "
                  f"learned={stats['learned_concepts']}  wall={stats['wall_s']}s")
    finally:
        if not args.keep:
            print(f"removing {root}")
            shutil.rmtree(root, ignore_errors=True)

    out = Path(args.out) if args.out else None
    text = json.dumps(result, indent=2)
    if out:
        out.write_text(text)
        print(f"wrote {out}")
    else:
        print(text)


if __name__ == "__main__":
    sys.exit(main())
