"""Task 31.5 R0.5 `#r0-5-method`: the capture's cost on the hook path, on a COPY of the live
catalog, in fresh processes, with the generated hook's scan arguments, on the dev binary BY PATH.

Usage: python measure.py setup <workdir>
       python measure.py run <workdir> <label> <arms> <passes>
         arms: comma list of off,full,names (alternated per prompt)
Prints a JSON summary per arm. Never touches the live store: the live catalog is only READ
(copied), HOME points at a scratch dir, REFMATRIX_ROOT and RMX_HOME are removed from the env.
"""
from __future__ import annotations

import json
import os
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

CLONE = Path("/Volumes/littlebig/refmatrix-315-green")
LIVE_CATALOG = Path("/Users/tholley/claude_tools/refmatrix/.refmatrix/catalog.read.duckdb")
RMX = CLONE / ".venv-eval" / "bin" / "rmx"
PROMPTS = CLONE / "tests" / "fixtures" / "injection_capture" / "prompts.txt"
# The generated scan_cmd's arguments (hooks.py `scan_cmd`, composite_every 3 in this store).
SCAN_ARGS = ["scan-prompt", "--composite-every", "3", "--max-tokens", "2000", "--timeout", "5"]
DROP = {"REFMATRIX_ROOT", "RMX_HOME", "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT",
        "CLAUDE_PROJECT_DIR", "RMX_INJECTION_CAPTURE", "REFMATRIX_NO_TELEMETRY",
        "RMX_SESSION"}


def env_for(work: Path, **extra) -> dict:
    e = {k: v for k, v in os.environ.items() if k not in DROP and not k.startswith("CLAUDE")}
    e["HOME"] = str(work / "h")
    e["PYTHONPATH"] = str(CLONE / "src")
    e["RMX_INVOCATION_SOURCE"] = "hook"
    e["HF_HUB_OFFLINE"] = "1"
    e.update({k: str(v) for k, v in extra.items()})
    return e


def setup(work: Path) -> None:
    (work / "h").mkdir(parents=True, exist_ok=True)
    root = work / "refmatrix" / ".refmatrix"
    root.mkdir(parents=True, exist_ok=True)
    dst = root / "catalog.read.duckdb"
    if not dst.exists():
        shutil.copyfile(LIVE_CATALOG, dst)
    import duckdb
    con = duckdb.connect(str(dst), read_only=True)
    n = con.execute("SELECT count(*) FROM entities").fetchone()[0]
    con.close()
    print(json.dumps({"copy": str(dst), "bytes": dst.stat().st_size, "entities": n}))
    v = subprocess.run([str(RMX), "version", "-v"], env=env_for(work), cwd=str(work / "refmatrix"),
                       capture_output=True, text=True, timeout=120)
    print(v.stdout + v.stderr)


def pct(vals, q):
    s = sorted(vals)
    return s[min(len(s) - 1, int(q * len(s)))] if s else None


def run(work: Path, label: str, arms: "list[str]", passes: int) -> None:
    proj = work / "refmatrix"
    root = proj / ".refmatrix"
    prompts = [ln for ln in PROMPTS.read_text().splitlines() if ln.strip()]
    cap_dir = root / "injection-capture"
    out_rows = []
    for ps in range(passes):
        for pi, prompt in enumerate(prompts):
            for arm in arms:
                env = env_for(work, RMX_INJECTION_CAPTURE={"off": "0"}.get(arm, arm))
                envelope = json.dumps({"session_id": f"m315-{label}", "prompt": prompt,
                                       "hook_event_name": "UserPromptSubmit",
                                       "cwd": str(proj), "transcript_path": ""})
                before = _count_records(cap_dir)
                t = time.perf_counter()
                r = subprocess.run([str(RMX), *SCAN_ARGS], input=envelope, env=env,
                                   cwd=str(proj), capture_output=True, text=True, timeout=300)
                wall = (time.perf_counter() - t) * 1000.0
                rec = _last_record(cap_dir) if arm != "off" and \
                    _count_records(cap_dir) == before + 1 else None
                out_rows.append({"label": label, "pass": ps, "prompt": pi, "arm": arm,
                                 "rc": r.returncode, "wall_ms": round(wall, 1),
                                 "trip": "# [truncated by --max-tokens]" in r.stdout,
                                 "out_bytes": len(r.stdout.encode()),
                                 "capture_ms": rec and rec["capture_ms"],
                                 "capture_built": rec and rec["capture_built"],
                                 "load1": os.getloadavg()[0]})
    raw = work / f"runs-{label}.jsonl"
    with raw.open("a") as f:
        for row in out_rows:
            f.write(json.dumps(row) + "\n")
    summary = {}
    for arm in arms:
        rows = [r for r in out_rows if r["arm"] == arm]
        w = [r["wall_ms"] for r in rows]
        s = {"n": len(rows), "rc_nonzero": sum(1 for r in rows if r["rc"]),
             "wall_p50": pct(w, .5), "wall_p95": pct(w, .95),
             "load1_mean": round(statistics.mean(r["load1"] for r in rows), 2),
             "trips": sum(1 for r in rows if r["trip"]),
             "prompts_tripping": len({r["prompt"] for r in rows if r["trip"]})}
        if arm != "off":
            cm = [r["capture_ms"] for r in rows if r["capture_ms"] is not None]
            cb = [r["capture_built"] for r in rows if r["capture_built"] is not None]
            built_rows = [r for r in rows if r["capture_built"]]
            s.update({"records": len(cm), "capture_ms_p50": pct(cm, .5),
                      "capture_ms_p95": pct(cm, .95), "capture_ms_max": max(cm) if cm else None,
                      "capture_built_mean": round(statistics.mean(cb), 2) if cb else None,
                      "capture_built_max": max(cb) if cb else None,
                      "calls_with_builds": len(built_rows),
                      "ms_per_built_bundle_agg": round(
                          sum(r["capture_ms"] for r in built_rows)
                          / max(1, sum(r["capture_built"] for r in built_rows)), 1),
                      "ms_per_built_bundle_p50": pct([r["capture_ms"] / r["capture_built"]
                                                      for r in built_rows], .5)})
        summary[arm] = s
    print(json.dumps({"label": label, **summary}, indent=1))


def _count_records(d: Path) -> int:
    return sum(1 for f in d.glob("capture-*.jsonl") for ln in f.open() if ln.strip()) \
        if d.is_dir() else 0


def _last_record(d: Path) -> "dict | None":
    files = sorted(d.glob("capture-*.jsonl"))
    if not files:
        return None
    lines = [ln for ln in files[-1].read_text().splitlines() if ln.strip()]
    return json.loads(lines[-1]) if lines else None


if __name__ == "__main__":
    cmd, work = sys.argv[1], Path(sys.argv[2])
    if cmd == "setup":
        setup(work)
    else:
        run(work, sys.argv[3], sys.argv[4].split(","), int(sys.argv[5]))
