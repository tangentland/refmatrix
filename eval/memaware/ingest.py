#!/usr/bin/env python3
"""Build a dedicated rmx store over the split MemAware corpus.

Isolated on purpose: `REFMATRIX_ROOT=eval/memaware/store/.refmatrix`, its own
partition, no watcher and no launchd job. The benchmark corpus is 1307 chat
transcripts about one synthetic person's life — it has no business landing in
the refmatrix project store or the global one.

Passes run in order and each is skippable, because they cost very different
amounts:
  ingest   markdown/prose pass -> entities + `mentions` concept graph (minutes)
  embed    bge-small vectors over the docs, for the dense/hybrid conditions
  compile  `rmx memory compile` -> subject clusters, the ROOT.md analog
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

from paths import CORPUS, DATA, PARTITION, STORE_ROOT, rmx_env

HERE = Path(__file__).resolve().parent
ROOT = STORE_ROOT


_LOG = True


def env() -> dict:
    # This is a batch build, not an editor session: no daemon, no watcher.
    return rmx_env(log=_LOG)


def run(args: list[str], *, label: str) -> None:
    print(f"\n  === {label}\n  $ {' '.join(args)}")
    t0 = time.time()
    p = subprocess.run(args, env=env())
    dt = time.time() - t0
    if p.returncode != 0:
        sys.exit(f"  ! {label} failed (exit {p.returncode}) after {dt:.1f}s")
    print(f"  + {label} ok in {dt:.1f}s")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rmx", default="rmx", help="rmx binary (default: deploy `rmx`)")
    ap.add_argument("--skip-ingest", action="store_true")
    ap.add_argument("--skip-embed", action="store_true")
    ap.add_argument("--skip-compile", action="store_true")
    ap.add_argument("--facts-log", action="store_true",
                    help="keep the append-only facts.log on (default OFF for "
                         "this store: it is rebuildable from corpus/, and the "
                         "per-link log write dominates the ingest)")
    args = ap.parse_args()

    global _LOG
    _LOG = bool(args.facts_log)

    if not CORPUS.exists():
        sys.exit("  ! corpus/ missing — run `python3 prepare.py --clone` first")

    n = sum(1 for _ in CORPUS.rglob("*.md"))
    print(f"  ~ corpus: {n} session docs under {CORPUS}")
    print(f"  ~ store:  {ROOT} (partition={PARTITION})")

    if not ROOT.exists():
        DATA.mkdir(parents=True, exist_ok=True)
        run([args.rmx, "init", "--path", str(DATA), "--no-hooks", "--no-agents",
             "--no-memory-hooks"], label="init")

    if not args.skip_ingest:
        # ingest-gmd, NOT plain `ingest`: the general markdown pass extracts
        # only structured signals and leaves a prose transcript with zero
        # concepts (measured: 1309 docs, 0 `mentions` rows). ingest-gmd runs
        # the body term-frequency sweep that every symbolic read surface
        # depends on. See prepare._as_gmd.
        run([args.rmx, "ingest-gmd", "--as-memory",
             "--memory-mtype", "memaware/session", str(CORPUS)], label="ingest-gmd")
    if not args.skip_embed:
        run([args.rmx, "embed", "--kinds", "memory"], label="embed")
    if not args.skip_compile:
        run([args.rmx, "memory", "compile"], label="compile")

    run([args.rmx, "stats"], label="stats")


if __name__ == "__main__":
    main()
