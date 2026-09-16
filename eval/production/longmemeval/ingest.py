#!/usr/bin/env python3
"""Build a dedicated rmx store over the exploded LongMemEval corpus.

Isolated on purpose: its own `REFMATRIX_ROOT` on a separate volume, its own
partition, no watcher and no launchd job. The corpus is 19,829 chat transcripts
about synthetic people; it has no business landing in the refmatrix project
store or the global one, and MemAware proved the watcher will take it if given
the chance.

Three passes, each separately skippable because they cost very different
amounts:

    ingest-gmd   prose pass -> memory entities + the `mentions` concept index
    embed        bge-small vectors over the memory rows (dense conditions)
    compile      `rmx memory compile` -> subject clusters

`ingest-gmd`, never plain `rmx ingest`. This is the single most load-bearing
argument in the harness. rmx's general markdown pass extracts only STRUCTURED
signals — bold metadata, ADR refs, concept-doc linkages, fenced specs — and a
chat transcript has none of them. Measured on the MemAware corpus: plain ingest
gave 1309 doc entities, **0 `mentions` rows and 3 concepts**. Every symbolic
read surface then falls through to the grep backstop, and the benchmark reports
a number for an index that was never built. `ingest_gmd` is the pass that runs
the body term-frequency sweep `content_rank`, `context`, and `scan-prompt` all
read. `--as-memory` is the honest analogy besides: in rmx a past session IS a
memory, which puts the corpus on the same surfaces the shipped product uses.

Everything goes through the `rmx` CLI. No adapter class, no direct `Store()`
open ([[feedback_store_calls_via_daemon]]) — the benchmark path IS the
production path, and `feedback_measure_the_path_users_run` is on record about
what happens when it is not: four ingest defects hid behind a true-looking
0.982 MRR for months.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Iterable

from paths import CORPUS, DATA, PARTITION, STORE_ROOT, rmx_env

Runner = Callable[[list[str], dict], int]


class PassFailed(RuntimeError):
    """A build pass exited non-zero, or the corpus was not there to build from."""


def _default_runner(argv: list[str], env: dict) -> int:
    return subprocess.run(argv, env=env).returncode


def passes(rmx: str, corpus: Path, root: Path) -> list[tuple[str, list[str]]]:
    """The build, as (label, argv) pairs. Pure — the test reads this directly."""
    return [
        ("init", [rmx, "init", "--path", str(root.parent), "--no-hooks",
                  "--no-agents", "--no-memory-hooks"]),
        ("ingest-gmd", [rmx, "ingest-gmd", "--as-memory",
                        "--memory-mtype", "longmemeval/session", str(corpus)]),
        ("embed", [rmx, "embed", "--kinds", "memory"]),
        ("compile", [rmx, "memory", "compile"]),
        ("stats", [rmx, "stats"]),
    ]


def build(*, rmx: str, corpus: Path, root: Path,
          runner: "Runner | None" = None,
          skip: Iterable[str] = (), log: bool = False) -> dict:
    """Run the passes in order, aborting loudly on the first failure.

    Returns per-pass wall clock. A pass that fails names itself and its exit
    code and stops the build — continuing would leave, say, an empty vector
    table that scores as "rmx is bad at dense recall" rather than as a broken
    build.
    """
    runner = runner or _default_runner
    skip = set(skip)

    n = sum(1 for _ in corpus.rglob("*.md")) if corpus.exists() else 0
    if not n:
        raise PassFailed(
            f"corpus is empty or missing: {corpus} — run `python3 prepare.py "
            f"--fetch` first")
    print(f"  ~ corpus: {n} session docs under {corpus}")
    print(f"  ~ store:  {root} (partition={PARTITION})")

    env = rmx_env(log=log)
    # `rmx_env` pins REFMATRIX_ROOT to paths.STORE_ROOT; an explicit root
    # (tests, a throwaway build) has to win over it.
    env["REFMATRIX_ROOT"] = str(root)

    timings: dict[str, float] = {}
    for label, argv in passes(rmx, corpus, root):
        if label in skip:
            print(f"  ~ skipping {label}")
            continue
        if label == "init" and root.exists():
            print(f"  ~ store already initialised, skipping init")
            continue
        print(f"\n  === {label}\n  $ {' '.join(argv)}", flush=True)
        t0 = time.time()
        code = runner(argv, env)
        dt = time.time() - t0
        timings[label] = round(dt, 1)
        if code != 0:
            raise PassFailed(f"pass {label!r} failed with exit {code} after "
                             f"{dt:.1f}s — build aborted, later passes not run")
        print(f"  + {label} ok in {dt:.1f}s", flush=True)
    return timings


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rmx", default="rmx", help="rmx binary (default: deploy `rmx`)")
    ap.add_argument("--skip", action="append", default=[],
                    choices=["init", "ingest-gmd", "embed", "compile", "stats"],
                    help="skip a pass; repeatable")
    ap.add_argument("--facts-log", action="store_true",
                    help="keep the append-only facts.log on (default OFF: this "
                         "store is rebuildable from corpus/ in one command, and "
                         "the per-link log write dominates the ingest)")
    a = ap.parse_args()

    DATA.mkdir(parents=True, exist_ok=True)
    try:
        timings = build(rmx=a.rmx, corpus=CORPUS, root=STORE_ROOT,
                        skip=a.skip, log=a.facts_log)
    except PassFailed as exc:
        sys.exit(f"  ! {exc}")
    total = sum(timings.values())
    print(f"\n  + build complete in {total:.1f}s: {timings}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
