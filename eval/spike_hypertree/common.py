"""Shared constants for the 2026-10-20 hypertree spike (M1-M7).

Measurement only, never imported by `src/`. Every script reads a COPY of a store's
lock-free snapshot (`catalog.read.duckdb` copied to `<SPIKE_ROOT>/<store>/catalog.duckdb`),
never a live `.refmatrix/`. Same six stores and code partitions as
spike-2026-10-07-adjacency-shape (session partitions excluded).
"""
from __future__ import annotations

import os
from pathlib import Path

SPIKE_ROOT = Path(os.environ.get("HYPERTREE_SPIKE_ROOT", "/Volumes/littlebig/refmatrix-spike-hypertree"))
SEED = 20261020
RESULTS = Path(__file__).resolve().parent / "results"

# store -> (live project root [read for source files only], code partition id)
STORES: dict[str, tuple[str, int]] = {
    "refmatrix": ("/Users/tholley/claude_tools/refmatrix", 4),
    "cliquedb": ("/Users/tholley/github/atollogy/bdep/cliquedb", 2),
    "viascope": ("/Users/tholley/github/atollogy/bdep/viascope", 104),
    "cliquet": ("/Users/tholley/github/atollogy/bdep/cliquet", 1),
    "orderly": ("/Users/tholley/github/atollogy/bdep/orderly", 1),
    "atldb": ("/Users/tholley/github/atollogy/bdep/atldb", 2),
}


def copy_db(store: str) -> str:
    """The COPY of the store's snapshot. Never the live file."""
    p = SPIKE_ROOT / store / "catalog.duckdb"
    assert "/.refmatrix/" not in str(p), "refusing a live .refmatrix path"
    return str(p)


def rel_parts(path: str | None, root: str) -> tuple[str, ...] | None:
    """Path components relative to the store root. Relative paths are taken as already
    root-relative. Absolute paths outside the root (e.g. ~/.claude memory files, /private/tmp
    scratch) return ('@ext', <components...>) so callers can count or exclude them."""
    if not path:
        return None
    if not path.startswith("/"):
        return tuple(x for x in path.split("/") if x and x != ".")
    r = root.rstrip("/") + "/"
    if path.startswith(r):
        return tuple(x for x in path[len(r):].split("/") if x)
    return ("@ext",) + tuple(x for x in path.split("/") if x)
