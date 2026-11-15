#!/usr/bin/env python3
"""T0.3's load harness: one target test under N concurrent pytest load processes, one trial
per run, and the pre-registered bands (`task-t0-suite-trust-sweep#t0-3-bands`).

Written before trial 1, as the bands require; the numbers below are the spec's, not tuned:
- the load is the 25 heaviest files of stage 0's durations run
  (`task-29.4-r0-durations#top25`, frozen: it does not change after trial 1), split over N
  processes heaviest first into the lightest (29.4 R2's rule), N = 3, then 5, then 8;
- the per-trial wall cap is `max(3 * T, 300 s)`, T the R0 seconds of the files the trial's
  processes run, the target's file included (`tests/shard_weights.json`);
- a trial's outcome is the TARGET's (`t03_capture.py` records it); a cap hit is a `hang` only
  if the target had not finished; a load-only hang makes the trial `void` (recorded, re-run);
  a 4th void at a level makes the level `noisy`;
- reproducer: >= 3 failures (hangs included) in 10 base trials at a level; fix proven: 45
  consecutive passes at the reproducer's level.

Lane discipline (the lead's brief, 2026-11-15): every trial is a test run, so `run` takes the
lane lock around EACH trial (`/usr/bin/lockf <lock> ... trial ...`): other agents' runs can
interleave between trials, never inside one. The machine runs one test process group at a time.

Two choices the spec leaves to the lead are flags, defaulting to the spec's text:
- `--load-mode complete` (default): every load process runs its files to the end; the trial ends
  when all processes have exited or the cap fires. `until-target` stops the load once the
  target has exited (a trial then lasts warm-up + the target; the void rule cannot fire);
- several `--target` nodes in one trial run in ONE target process, in order, each with its own
  outcome. One `--target` is the spec's "one harness run gives one trial" per row.

Usage:
  t03_load_harness.py plan  --level 3 --target NODE
  t03_load_harness.py trial --level 3 --target NODE --out DIR      (caller holds the lane)
  t03_load_harness.py run   --level 3 --target NODE --trials 10 --out DIR [--mode base|fix]
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WEIGHTS = REPO / "tests" / "shard_weights.json"
TOUCHES = REPO / "workflow" / "review-output" / "live-socket-touches.log"
LOCK = "/private/tmp/claude-501/rmx-test-lane.lock"

# task-29.4-r0-durations#top25, stage 0 at 4c6a0c6. Frozen before trial 1.
TOP25 = (
    "tests/test_memory_bridge.py", "tests/test_task25_1_recall_budget.py",
    "tests/test_bridge_move_safety.py", "tests/test_plan3_remedy_r5.py",
    "tests/test_task21_1_used_events.py", "tests/test_bug212_r4_red.py",
    "tests/test_memory_compile_scope.py", "tests/test_savestate_mtype.py",
    "tests/test_plan3_remedy_r4.py", "tests/test_bridge_move_safety_r1.py",
    "tests/test_modelsrv.py", "tests/test_bug216_hidden_no_pollution.py",
    "tests/test_sync_fails_loudly_r2.py", "tests/test_bug212_r6_red.py",
    "tests/test_task3_6_r9_remedy.py", "tests/test_task21_1_emitters.py",
    "tests/test_rerank_budget_real_clients.py", "tests/test_plan3_remedy_r6.py",
    "tests/test_plan4_remedy_r3.py", "tests/test_plan3_remedy_r3.py",
    "tests/test_plan4_remedy.py", "tests/test_bug225_handoff_trunk.py",
    "tests/test_catalog_measure.py", "tests/test_bug212_r1_remedy.py",
    "tests/test_memory_compile_remedy_r1.py",
)

# The five rows (task-t0-suite-trust-sweep#t0-3, #amend-4).
ROWS = {
    "bug-130": "tests/test_catalog_measure.py::test_rewrite_bytes_is_the_median_of_the_runs",
    "bug-190": ("tests/test_rerank_budget_real_clients.py::"
                "test_a_cold_private_worker_is_skipped_without_spawning"),
    "bug-091": "tests/test_watch.py::test_run_watcher_picks_up_new_file",
    "bug-228": ("tests/test_task21_1_recall_skip.py::"
                "test_ac2b_live_daemon_recall_writes_one_ok_recall_row"),
    "bug-231": "tests/test_plan4_remedy.py::test_graceful_stop_on_a_live_daemon_returns_quickly",
}
LEVELS = (3, 5, 8)
BASE_TRIALS = 10
REPRO_FAILS = 3
FIX_PASSES = 45
MAX_VOIDS = 3
CAP_FLOOR_S = 300.0
CAP_FACTOR = 3.0


# ---- pure logic (tests/test_t03_load_harness.py) ------------------------------------------

def load_weights(path: Path = WEIGHTS) -> dict:
    return json.loads(path.read_text())["files"]


def file_of(node: str) -> str:
    return node.split("::", 1)[0]


def split_load(files, weights: dict, n: int) -> list:
    """Heaviest first into the lightest process (29.4 R2's placement rule); ties go to the
    lowest index. A file with no weight is an error: every file a cap needs has one."""
    missing = [f for f in files if f not in weights]
    if missing:
        raise KeyError(f"no R0 weight for {missing}")
    procs: list = [[] for _ in range(n)]
    sums = [0.0] * n
    for f in sorted(files, key=lambda f: (-weights[f], f)):
        i = min(range(n), key=lambda j: (sums[j], j))
        procs[i].append(f)
        sums[i] += weights[f]
    return procs


def trial_cap(load: list, targets, weights: dict) -> tuple:
    """(cap seconds, T): T sums the R0 seconds of every file each process runs, the target
    process's files included (a file run by two processes counts twice)."""
    tfiles = sorted({file_of(t) for t in targets})
    missing = [f for f in tfiles if f not in weights]
    if missing:
        raise KeyError(f"no R0 weight for {missing}")
    total = sum(weights[f] for proc in load for f in proc) + sum(weights[f] for f in tfiles)
    return max(CAP_FACTOR * total, CAP_FLOOR_S), total


def node_outcomes(records: list, targets, *, target_exited: bool) -> dict:
    """Each target node's outcome from the capture plugin's records:
    `pass`, `fail` (with its first E line), `hang` (started, not finished, process killed),
    or `not-run` (never started)."""
    out = {}
    for node in targets:
        recs = [r for r in records if r.get("node") == node]
        started = any(r.get("event") == "start" for r in recs)
        reps = {r["phase"]: r for r in recs if r.get("event") == "report"}
        failed = [reps[p] for p in ("setup", "call", "teardown")
                  if p in reps and reps[p]["outcome"] == "failed"]
        done = "teardown" in reps
        if failed:
            r = failed[0]
            e = (r.get("e_lines") or [r.get("crash") or "<no E line>"])[0]
            out[node] = {"outcome": "fail", "phase": r["phase"], "e_line": e,
                         "call_s": reps.get("call", {}).get("duration")}
        elif done and reps.get("call", {}).get("outcome") == "passed":
            out[node] = {"outcome": "pass", "call_s": reps["call"]["duration"]}
        elif done:
            out[node] = {"outcome": "fail", "phase": "call",
                         "e_line": f"<outcome {reps.get('call', {}).get('outcome')}>"}
        elif started and not target_exited:
            out[node] = {"outcome": "hang"}
        elif started:
            out[node] = {"outcome": "fail", "phase": "?", "e_line": "<target exited mid-node>"}
        else:
            out[node] = {"outcome": "not-run"}
    return out


def trial_status(outcomes: dict, *, cap_hit: bool, target_exited: bool) -> str:
    """`void` when the cap fired after the target finished (only a load process hung), else
    `counted`."""
    if cap_hit and target_exited:
        return "void"
    return "counted"


def base_band(outcomes: list) -> dict:
    """Base trials of one row at one level: failures (hangs included) out of the counted
    trials, and whether that level is the reproducer."""
    fails = sum(1 for o in outcomes if o in ("fail", "hang"))
    return {"trials": len(outcomes), "failures": fails,
            "reproducer": len(outcomes) >= BASE_TRIALS and fails >= REPRO_FAILS}


def fix_band(outcomes: list) -> dict:
    """A fix attempt: held only on FIX_PASSES consecutive passes; any failure ends it."""
    run = 0
    for o in outcomes:
        if o != "pass":
            return {"held": False, "passes_before_failure": run, "failure": o}
        run += 1
        if run >= FIX_PASSES:
            return {"held": True, "passes": run}
    return {"held": None, "passes": run}


# ---- the trial ------------------------------------------------------------------------------

def _env(trial_dir: Path) -> dict:
    env = dict(os.environ)
    if env.get("REFMATRIX_ROOT"):
        raise SystemExit("REFMATRIX_ROOT is set: refusing (it would point tests at a store)")
    pp = [str(REPO / "src"), str(REPO / "scripts")]
    env["PYTHONPATH"] = os.pathsep.join(pp + [p for p in env.get("PYTHONPATH", "").split(
        os.pathsep) if p and p not in pp])
    env["T03_TRIAL_DIR"] = str(trial_dir)
    env.pop("PYTEST_ADDOPTS", None)
    return env


def _pytest(args: list, log: Path, env: dict) -> subprocess.Popen:
    fh = open(log, "wb")
    return subprocess.Popen([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                             *args], cwd=str(REPO), env=env, stdout=fh,
                            stderr=subprocess.STDOUT, start_new_session=True)


def _descendants(pids: list) -> list:
    rows = subprocess.run(["ps", "-A", "-o", "pid=,ppid="], capture_output=True,
                          text=True).stdout.split("\n")
    kids: dict = {}
    for ln in rows:
        parts = ln.split()
        if len(parts) == 2:
            kids.setdefault(int(parts[1]), []).append(int(parts[0]))
    out, todo = [], list(pids)
    while todo:
        p = todo.pop()
        out.append(p)
        todo.extend(kids.get(p, []))
    return out


def _snapshot(pids: list, path: Path) -> None:
    """`ps -o pid,etime,time,command` and `lsof -p` of every still-running process, taken
    BEFORE anything is killed (#t0-3-cap)."""
    allp = _descendants(pids)
    with open(path, "w") as fh:
        ps = subprocess.run(["ps", "-o", "pid,ppid,etime,time,command", "-p",
                             ",".join(map(str, allp))], capture_output=True, text=True)
        fh.write(ps.stdout + ps.stderr)
        for p in allp:
            ls = subprocess.run(["lsof", "-p", str(p)], capture_output=True, text=True)
            fh.write(f"\n==== lsof -p {p} (exit {ls.returncode})\n{ls.stdout}{ls.stderr}")


def _kill_group(p: subprocess.Popen) -> None:
    """SIGINT first so pytest runs its teardowns (a test's daemon is stopped by its fixture),
    then SIGTERM, then SIGKILL. The validation trial (2026-11-15) saw SIGINT end one of three
    load processes; the other two ran on until SIGTERM."""
    for sig, wait in ((signal.SIGINT, 20.0), (signal.SIGTERM, 15.0), (signal.SIGKILL, 5.0)):
        if p.poll() is not None:
            return
        try:
            os.killpg(p.pid, sig)
        except ProcessLookupError:
            return
        try:
            p.wait(timeout=wait)
        except subprocess.TimeoutExpired:
            continue


def _lines(path: Path) -> int:
    try:
        return len(path.read_text(errors="replace").splitlines())
    except FileNotFoundError:
        return 0


def run_trial(level: int, targets: list, out: Path, *, warmup: float, load_mode: str) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    weights = load_weights()
    load = split_load(list(TOP25), weights, level)
    cap, total = trial_cap(load, targets, weights)
    env = _env(out)
    touches0 = _lines(TOUCHES)
    load0 = os.getloadavg()
    t0 = time.monotonic()
    w0 = time.time()
    loads = [_pytest(files, out / f"load-{i}.log", env) for i, files in enumerate(load)]
    time.sleep(warmup)
    target = _pytest(["-p", "t03_capture", *targets], out / "target.log", env)
    target_exit_s = None
    cap_hit = False
    while True:
        now = time.monotonic() - t0
        if target_exit_s is None and target.poll() is not None:
            target_exit_s = now
            if load_mode == "until-target":
                for p in loads:
                    _kill_group(p)
        if all(p.poll() is not None for p in [target, *loads]):
            break
        if now >= cap:
            cap_hit = True
            live = [p.pid for p in [target, *loads] if p.poll() is None]
            _snapshot(live, out / "cap-hit-ps-lsof.txt")
            for p in [target, *loads]:
                _kill_group(p)
            break
        time.sleep(0.5)
    wall = time.monotonic() - t0
    # monotonic (mach_absolute_time) does not advance while the host sleeps; the validation
    # trial measured 605 s awake inside 58 min of wall clock (pmset: Sleep / DarkWake cycles).
    wall_clock = time.time() - w0
    target_exited = target_exit_s is not None
    recs = []
    try:
        recs = [json.loads(ln) for ln in (out / "target-outcomes.jsonl").read_text().splitlines()]
    except FileNotFoundError:
        pass
    outcomes = node_outcomes(recs, targets, target_exited=target_exited)
    status = trial_status(outcomes, cap_hit=cap_hit, target_exited=target_exited)
    rec = {
        "level": level, "targets": targets, "load": load, "load_mode": load_mode,
        "warmup_s": warmup, "cap_s": cap, "T_s": total, "wall_s": wall,
        "wall_clock_s": wall_clock, "cap_hit": cap_hit,
        "target_exit_s": target_exit_s, "target_rc": target.returncode,
        "load_rcs": [p.returncode for p in loads], "status": status, "outcomes": outcomes,
        "loadavg_start": load0, "loadavg_end": os.getloadavg(),
        "live_socket_touches_added": _lines(TOUCHES) - touches0,
        "sha": subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                              capture_output=True, text=True).stdout.strip(),
    }
    (out / "trial.json").write_text(json.dumps(rec, indent=1))
    return rec


def _trial_args(a, out: Path) -> list:
    args = ["trial", "--level", str(a.level), "--out", str(out), "--warmup", str(a.warmup),
            "--load-mode", a.load_mode]
    for t in a.target:
        args += ["--target", t]
    return args


def run_trials(a) -> dict:
    """Up to `--trials` counted trials at one level, each under the lane lock; voids are
    re-run, a 4th void stops the level as noisy; `--mode fix` stops at the first failure."""
    base = Path(a.out)
    base.mkdir(parents=True, exist_ok=True)
    counted, voids, n = [], 0, 0
    noisy = False
    while len(counted) < a.trials:
        n += 1
        tdir = base / f"trial-{n:03d}"
        cmd = [sys.executable, str(Path(__file__).resolve()), *_trial_args(a, tdir)]
        if a.lock:
            cmd = ["/usr/bin/lockf", a.lock, *cmd]
        rc = subprocess.run(cmd, cwd=str(REPO)).returncode
        if rc != 0 or not (tdir / "trial.json").exists():
            raise SystemExit(f"trial {n} failed to run (exit {rc}); see {tdir}")
        rec = json.loads((tdir / "trial.json").read_text())
        line = {k: rec[k] for k in ("status", "wall_s", "cap_hit", "loadavg_start")}
        line["outcomes"] = {k: v["outcome"] for k, v in rec["outcomes"].items()}
        print(f"trial {n}: {json.dumps(line)}", flush=True)
        if rec["status"] == "void":
            voids += 1
            if voids > MAX_VOIDS:
                noisy = True
                break
            continue
        counted.append(rec)
        if a.mode == "fix" and any(v["outcome"] != "pass" for v in rec["outcomes"].values()):
            break
    summary = {"level": a.level, "mode": a.mode, "targets": a.target, "voids": voids,
               "noisy": noisy, "trials_run": n, "rows": {}}
    for t in a.target:
        seq = [r["outcomes"][t]["outcome"] for r in counted]
        summary["rows"][t] = {
            "sequence": seq,
            "band": base_band(seq) if a.mode == "base" else fix_band(seq),
            "e_lines": [r["outcomes"][t].get("e_line") for r in counted
                        if r["outcomes"][t]["outcome"] in ("fail",)],
            "walls_s": [round(r["wall_s"], 1) for r in counted]}
    (base / "summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))
    return summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "trial", "run"):
        p = sub.add_parser(name)
        p.add_argument("--level", type=int, choices=LEVELS, required=True)
        p.add_argument("--target", action="append", required=True)
        p.add_argument("--warmup", type=float, default=20.0)
        p.add_argument("--load-mode", choices=("complete", "until-target"), default="complete")
        if name != "plan":
            p.add_argument("--out", required=True)
        if name == "run":
            p.add_argument("--trials", type=int, default=BASE_TRIALS)
            p.add_argument("--mode", choices=("base", "fix"), default="base")
            p.add_argument("--lock", default=LOCK)
    a = ap.parse_args(argv)
    if a.cmd == "plan":
        w = load_weights()
        load = split_load(list(TOP25), w, a.level)
        cap, total = trial_cap(load, a.target, w)
        for i, files in enumerate(load):
            print(f"load-{i}: {sum(w[f] for f in files):7.1f} s  {len(files)} files")
        print(f"T = {total:.1f} s; cap = {cap:.1f} s")
        return 0
    if a.cmd == "trial":
        rec = run_trial(a.level, a.target, Path(a.out), warmup=a.warmup, load_mode=a.load_mode)
        print(json.dumps({k: rec[k] for k in ("status", "wall_s", "outcomes")}, indent=1))
        return 0
    run_trials(a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
