#!/usr/bin/env python3
"""Cost baseline of a shell-prefiltered PreToolUse hook (I1.b R0). Renders hooks._handoff_cmd(root,
"gate", per_session=True) for a mkdtemp() root with NO gate file, runs it 200x by /bin/bash -c with a
tool envelope on stdin, timed around the process; floor = `bash -c 'exit 0'` the same way.
Bands: median <= 10 ms stands; > 10 ms with a floor under it -> fix form in b3; floor > 10 ms -> report.
Imports refmatrix from this clone's src (not the lane install)."""
import json, os, statistics, subprocess, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "src"))
from refmatrix import hooks
N = 200
root = Path(tempfile.mkdtemp()); (root / "handoffs").mkdir()
cmd = hooks._handoff_cmd(root, "gate", per_session=True)
env = json.dumps({"session_id": "0f8e7d6c-1111-4222-8333-444455556666", "hook_event_name": "PreToolUse",
                  "tool_name": "Bash", "tool_input": {"command": "echo hi"}, "cwd": "/tmp"})
def run(argv, stdin):
    t = time.perf_counter_ns()
    r = subprocess.run(argv, input=stdin, capture_output=True, text=True)
    return (time.perf_counter_ns() - t) / 1e6, r.returncode
def series(argv, stdin):
    for _ in range(10): run(argv, stdin)            # warm-up, discarded
    xs = [run(argv, stdin) for _ in range(N)]
    assert all(rc == 0 for _, rc in xs), "non-zero exit: the prefilter did not short-circuit"
    ms = sorted(x for x, _ in xs)
    return {"median_ms": round(statistics.median(ms), 2), "p95_ms": round(ms[int(0.95 * N) - 1], 2),
            "min_ms": round(ms[0], 2), "max_ms": round(ms[-1], 2)}
hook = series(["/bin/bash", "-c", cmd], env)
floor = series(["/bin/bash", "-c", "exit 0"], env)
added = round(hook["median_ms"] - floor["median_ms"], 2)
band = ("median<=10ms: the form stands" if hook["median_ms"] <= 10 else
        "floor>10ms: no shell prefilter meets the band here" if floor["median_ms"] > 10 else
        "median>10ms, floor under: fix the form in b3 (candidate: $(cat) subshell)")
print(json.dumps({"n": N, "hook": hook, "floor": floor, "added_median_ms": added, "band": band,
                  "load_avg": [round(x, 2) for x in os.getloadavg()], "machine": os.uname().machine,
                  "command_len": len(cmd), "command_head": cmd[:160]}, indent=1))
