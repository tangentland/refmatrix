#!/usr/bin/env python3
"""Sum a pytest `--durations=0` report into per-file weights: tests/shard_weights.json.

Why: task-29.4 R0.2 (plan-29, 2026-11-14). No committed full-suite log carried durations, so the
sharded runner (29.4 R2) and T0.3's load harness had no per-file weights. This reads the
`slowest durations` block of one serial run and sums setup + call + teardown by test file.

Limit, stated rather than hidden: without `-vv`, pytest hides every phase under 0.005 s and
prints only their count. Those phases are not in the sums. The count is recorded in the output
(`hidden_phases`), with its upper bound in seconds (count x 0.005). A file whose every phase was
hidden (or that only skipped) has no entry, so the runner's no-weight rule estimates it. A file
with a FAILED or ERROR node in the run's short summary is listed under `understated`: an error
at setup records setup time only, so its weight is below a working run's (R0 at 4c6a0c6: the
bug-240/241 fixtures errored in a clone with no `.venv-eval/` of its own).

usage: shard_weights_from_durations.py <pytest log> <out.json> [--sha SHA]
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

_LINE = re.compile(r"^(\d+(?:\.\d+)?)s (setup|call|teardown)\s+(\S+?\.py)(?:::.*)?$")
_HIDDEN = re.compile(r"^\((\d+) durations < ([\d.]+)s hidden")


def parse(log_text: str) -> tuple[dict[str, dict[str, float]], int, float]:
    in_block = False
    per_file: dict[str, dict[str, float]] = defaultdict(
        lambda: {"setup": 0.0, "call": 0.0, "teardown": 0.0})
    hidden, hidden_below = 0, 0.0
    lines = 0
    for raw in log_text.splitlines():
        if "slowest durations" in raw:
            in_block = True
            continue
        if not in_block:
            continue
        m = _LINE.match(raw.strip())
        if m:
            per_file[m.group(3)][m.group(2)] += float(m.group(1))
            lines += 1
            continue
        h = _HIDDEN.match(raw.strip())
        if h:
            hidden, hidden_below = int(h.group(1)), float(h.group(2))
    if not in_block or lines == 0:
        raise SystemExit("no `slowest durations` block with phase lines found in the log")
    return dict(per_file), hidden, hidden_below


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    log, out = Path(argv[1]), Path(argv[2])
    sha = argv[argv.index("--sha") + 1] if "--sha" in argv else None
    per_file, hidden, below = parse(log.read_text(errors="replace"))
    files = {f: round(sum(p.values()), 2) for f, p in per_file.items()}
    files = dict(sorted(files.items(), key=lambda kv: (-kv[1], kv[0])))
    understated: dict[str, dict[str, int]] = defaultdict(lambda: {"failed": 0, "error": 0})
    for raw in log.read_text(errors="replace").splitlines():
        m = re.match(r"^(FAILED|ERROR) (tests/\S+?\.py)::", raw)
        if m:
            understated[m.group(2)]["failed" if m.group(1) == "FAILED" else "error"] += 1
    doc = {
        "source": str(log.name),
        "sha": sha,
        "unit": "seconds, setup + call + teardown summed per test file",
        "hidden_phases": hidden,
        "hidden_below_s": below,
        "hidden_upper_bound_s": round(hidden * below, 2),
        "total_s": round(sum(files.values()), 2),
        "understated": {f: understated[f] for f in sorted(understated)},
        "files": files,
        "phases": {f: {k: round(v, 2) for k, v in per_file[f].items()} for f in files},
    }
    out.write_text(json.dumps(doc, indent=1) + "\n")
    print(f"{len(files)} files, total {doc['total_s']} s, hidden phases {hidden} "
          f"(< {below} s each, <= {doc['hidden_upper_bound_s']} s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
