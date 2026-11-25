#!/usr/bin/env python3
"""The T0.9 (a) probe harness: the same measurement on the host and in the container.

WHY. task-t0.9-test-isolation `#a-probe` compares the container with the host by wall time per
file, outcomes by node and E line, and peak memory. Two different stopwatches (a shell `date` in
the container, `/usr/bin/time` on the host) would measure two different things, so both sides
run THIS file under the interpreter that runs the tests:

    probe.py OUT_DIR FILE [FILE ...]

Each file is one plain `python -m pytest -q -p no:cacheprovider FILE` child with
`PYTHONPATH=<checkout>/src` first, `RMX_OUTCOMES_OUT` / `RMX_FAILURES_OUT` set to
`OUT_DIR/<stem>.outcomes.jsonl` / `.failures.jsonl` (the conftest writes them, never parsed from
text, task 29.4 `#r2`), and its output in `OUT_DIR/<stem>.log`. Per file, one line of
`OUT_DIR/probe.jsonl`: wall seconds (monotonic, around the child), the 1-minute load average
before and after, pytest's exit code, and the peak RSS of the largest process in the child's
tree (`RUSAGE_CHILDREN` read in a fresh intermediary per file, so one file's peak never carries
into the next; bytes on darwin, KiB on linux, normalised to MiB). In a container the cgroup's
`memory.peak` (all processes, page cache included) is recorded once at the end.

Stdlib only; it imports nothing from `refmatrix`.
"""
from __future__ import annotations

import json
import os
import resource
import subprocess
import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]


def _maxrss_mib(ru_maxrss: int) -> float:
    return round(ru_maxrss / (1024 * 1024 if sys.platform == "darwin" else 1024), 1)


def _one(out_dir: Path, test_file: str) -> int:
    """Run one file as a child of THIS process and print its record as JSON on stdout."""
    stem = Path(test_file).stem
    env = dict(os.environ)
    src = str(_REPO / "src")
    rest = [p for p in env.get("PYTHONPATH", "").split(os.pathsep) if p and p != src]
    env["PYTHONPATH"] = os.pathsep.join([src] + rest)
    env["RMX_OUTCOMES_OUT"] = str(out_dir / f"{stem}.outcomes.jsonl")
    env["RMX_FAILURES_OUT"] = str(out_dir / f"{stem}.failures.jsonl")
    for k in ("RMX_OUTCOMES_OUT", "RMX_FAILURES_OUT"):
        Path(env[k]).unlink(missing_ok=True)
    env.pop("RMX_PTEST_OUT_OWNER", None)
    cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", test_file]
    load0 = os.getloadavg()[0]
    t0 = time.monotonic()
    with open(out_dir / f"{stem}.log", "w", encoding="utf-8") as log:
        log.write("# " + " ".join(cmd) + "\n")
        log.flush()
        rc = subprocess.call(cmd, cwd=_REPO, env=env, stdout=log, stderr=subprocess.STDOUT)
    wall = time.monotonic() - t0
    load1 = os.getloadavg()[0]
    peak = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    print(json.dumps({"file": test_file, "wall_s": round(wall, 2), "load1_before": round(load0, 2),
                      "load1_after": round(load1, 2), "exit": rc,
                      "peak_rss_mib": _maxrss_mib(peak)}))
    return 0


def _cgroup_peak_mib() -> "float | None":
    p = Path("/sys/fs/cgroup/memory.peak")
    try:
        return round(int(p.read_text().strip()) / (1024 * 1024), 1)
    except FileNotFoundError:
        return None


def main(argv: list[str]) -> int:
    if len(argv) >= 3 and argv[0] == "--one":
        return _one(Path(argv[1]), argv[2])
    if len(argv) < 2:
        sys.stderr.write("usage: probe.py OUT_DIR FILE [FILE ...]\n")
        return 2
    out_dir = Path(argv[0]).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    records = out_dir / "probe.jsonl"
    records.unlink(missing_ok=True)
    worst = 0
    for f in argv[1:]:
        # A fresh intermediary per file: RUSAGE_CHILDREN only ever grows within one process.
        res = subprocess.run([sys.executable, __file__, "--one", str(out_dir), f], cwd=_REPO,
                             capture_output=True, text=True)
        if res.returncode != 0 or not res.stdout.strip():
            sys.stderr.write(f"probe.py: the intermediary for {f} failed ({res.returncode}): "
                             f"{res.stderr.strip()}\n")
            return 1
        rec = json.loads(res.stdout.strip().splitlines()[-1])
        with open(records, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
        print(json.dumps(rec), flush=True)
        worst = max(worst, rec["exit"])
    cg = _cgroup_peak_mib()
    if cg is not None:
        with open(records, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"cgroup_memory_peak_mib": cg}) + "\n")
        print(json.dumps({"cgroup_memory_peak_mib": cg}), flush=True)
    return worst


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
