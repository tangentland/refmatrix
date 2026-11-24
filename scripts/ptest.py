#!/usr/bin/env python3
"""The sharded test runner (plan-29 task 29.4 `#r2`, `#r7`; sub-task 29.4a, 2026-11-23).

WHY. The suite had one way to run: every test, one process, in file order (58:37 for the
0.83.0 release), and the 24-line `ptest.sh` before this split files round-robin, read its
verdict from grepped text and printed "ALL GREEN". Shards are several processes, each able to
reach a live socket (bug-088, bug-101), so the user ruled (`plan-review-fable D3` = (a), L106)
that nothing is sharded until a live touch fails the RUN from any shard (AC-12). This runner:

- picks each file's run tier from `tests/tiering.py::tier_of` (the checkout's own copy);
- runs tiers `unit` and `daemon` sharded and at the same time, then the serial group as one
  extra shard, then `timing` alone in one process, then `devtree` in the owning checkout only;
- places files greedily by weight (`tests/shard_weights.json`), deterministically; a file with
  no weight is named and placed at its tier's median weight per test;
- runs every shard as a plain pytest process whose command is printed (copy and paste re-runs
  it), with its own sandbox root, read back from its log header and checked distinct;
- takes `failures.jsonl` and `outcomes.jsonl` from the conftest (never parsed from text);
- exits non-zero when ANY shard did (never the last shard's code), and names every failed
  phase, live touches included, in `summary.txt`;
- never says "all green": a run that skipped a tier says so on its last line.

Modes:
  ptest.sh [--tier unit|daemon|devtree|timing|all] [--shards N] [--name RUN] [--max-minutes M]
  ptest.sh --files F [F …] [--shards N] [--name RUN]
  ptest.sh --compare RUN_A RUN_B
  ptest.sh --compare --outcomes RUN_A RUN_B [--expect 'node:phase:from->to' …]
  ptest.sh --merge-gate

Exit codes: 0 clean; 1 a test, shard, comparison or gate check failed; 2 refused or usage
(not the owning checkout, no merge in progress, pytest-timeout missing, a file tier_of cannot
place). The interpreter is `$RMX_PYTEST_PY`, else `<checkout>/.venv-eval/bin/python`.

Stdlib only, and it imports nothing from `refmatrix`: it runs under whatever interpreter the
wrapper picks, and the code under test is only ever imported by the shards.
"""
from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import os
import re
import shlex
import signal
import statistics
import subprocess
import sys
import time
from pathlib import Path

CHECKOUT = Path(__file__).resolve().parent.parent
SHARDED_TIERS = ("unit", "daemon")
TIER_ORDER = ("unit", "daemon", "timing", "devtree")
NOT_RUN_CLONE = ("tier devtree: NOT RUN here (clone); run it in the owning checkout before the "
                 "merge commit")
OUT_VARS = ("RMX_FAILURES_OUT", "RMX_OUTCOMES_OUT")
OUT_OWNER = "RMX_PTEST_OUT_OWNER"
_POLL_S = 0.5


class Refusal(Exception):
    """The runner will not run (exit 2): the message says why."""


def say(msg: str = "") -> None:
    print(msg, flush=True)


# ---- the ONE normalisation rule (#r2: `--compare` is equal by E line) ----------------------

_NORMALISE = [
    # sandbox roots, and the per-test store index under them (rmx_sandbox.make_root /
    # new_store_root: /tmp/rmx-[<tag>-]XXXXXXXX[/r/N])
    (re.compile(r"(?:/private)?/tmp/rmx-[A-Za-z0-9_-]+(?:/r/\d+)?"), "<SANDBOX>"),
    # the macOS per-user temp dir, then a random segment directly under a temp root
    (re.compile(r"(?:/private)?/var/folders/[^/\s]+/[^/\s]+/T(?=/|\b)"), "<TMPDIR>"),
    (re.compile(r"pytest-of-[^/\s]+/pytest-\d+"), "pytest-of-<USER>/pytest-<N>"),
    # a random segment is mkdtemp's default shape, the WHOLE path component: `tmp` + 8 of
    # [a-z0-9_]. A named path (/tmp/fixture_alpha) stays as it is (bsd-294a r1 m-4, L197:
    # the earlier rule ate the tail of any 8+ character name, so two different fixtures'
    # failures compared equal and the merge gate would read one as `seen`).
    (re.compile(r"((?:/private)?/tmp|<TMPDIR>)/tmp[a-z0-9_]{8}(?=[/\s)'\",:]|$)"),
     r"\1/tmp<RAND>"),
    # pids
    (re.compile(r"\b(pid)(\s*[=:]\s*|\s+)\d+", re.IGNORECASE), r"\1\2<PID>"),
    # hex addresses
    (re.compile(r"\b0x[0-9a-fA-F]+\b"), "0x<HEX>"),
    # decimal seconds
    (re.compile(r"\b\d+(?:\.\d+)?(\s?)(s|sec|secs|seconds)\b"), r"<S>\1\2"),
]


def normalise_e_line(e: str) -> str:
    """An E line with run noise replaced: sandbox roots, temp-dir random segments, pids, hex
    addresses and decimal seconds become placeholders, and NOTHING else (words, quoted keys,
    plain integers and path tails are what tell two errors apart). task-29.4 `#r2`."""
    out = e.strip()
    for rx, rep in _NORMALISE:
        out = rx.sub(rep, out)
    return out


# ---- the checkout ----------------------------------------------------------------------------

def checkout_kind(co: Path) -> "tuple[bool, str]":
    """(owning, why) by task-29.4 `#r7` item 1: the owning checkout has its own `.refmatrix/`
    and a `.venv-eval` that resolves inside it; a littlebig clone's or a lane worktree's
    `.venv-eval` is a symlink out of it (ruling L192 (3): a lane worktree is a clone)."""
    if not (co / ".refmatrix").is_dir():
        return False, f"no .refmatrix/ in {co}"
    venv = co / ".venv-eval"
    if not os.path.lexists(venv):
        return False, f"no .venv-eval in {co}"
    real = venv.resolve()
    base = co.resolve()
    if real != base and base not in real.parents:
        return False, f".venv-eval resolves outside the checkout ({venv} -> {real})"
    return True, "owning"


def interpreter(co: Path) -> str:
    return os.environ.get("RMX_PYTEST_PY") or str(co / ".venv-eval" / "bin" / "python")


def require_hang_guard(py: str) -> None:
    """Ruling L192 (6): refuse to run unguarded. pytest-timeout is the hang guard
    (`[tool.pytest.ini_options] timeout`); without the plugin pytest only warns about an unknown
    option and a hung test hangs the run."""
    if not os.access(py, os.X_OK):
        raise Refusal(f"refusing to run: no interpreter at {py} (set RMX_PYTEST_PY)")
    r = subprocess.run([py, "-c", "import pytest, pytest_timeout"], capture_output=True,
                       text=True)
    if r.returncode != 0:
        last = (r.stderr.strip().splitlines() or ["?"])[-1]
        raise Refusal(f"refusing to run: pytest-timeout (the hang guard) is not importable in "
                      f"{py} ({last}); install requirements-dev.lock")
    # Importable is not loaded (bsd-294a r1 m-2, L197): with PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
    # and no `-p pytest_timeout`, pytest never registers the plugin and `timeout = 600` is only
    # an unknown-option warning. Ask a pytest started with the shards' environment.
    import tempfile
    with tempfile.TemporaryDirectory(prefix="ptest-probe-") as d:
        r = subprocess.run([py, "-c", _LOADED_PROBE, d], cwd=d, capture_output=True, text=True,
                           env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    marks = [ln for ln in r.stdout.splitlines() if ln.startswith("PTEST-TIMEOUT-")]
    if marks != ["PTEST-TIMEOUT-LOADED"]:
        why = marks[-1] if marks else (r.stdout + r.stderr).strip()[-300:] or f"exit {r.returncode}"
        flags = (f"PYTEST_DISABLE_PLUGIN_AUTOLOAD={os.environ.get('PYTEST_DISABLE_PLUGIN_AUTOLOAD')!r}"
                 f", PYTEST_ADDOPTS={os.environ.get('PYTEST_ADDOPTS', '')!r}")
        raise Refusal(f"refusing to run: pytest-timeout (the hang guard) is importable but pytest "
                      f"does not load it under this environment ({flags}; probe: {why}); unset "
                      f"PYTEST_DISABLE_PLUGIN_AUTOLOAD or add `-p pytest_timeout` to PYTEST_ADDOPTS")


# Run by `require_hang_guard` under the interpreter and environment the shards get, in an empty
# temp dir (no ini, no conftest): does pytest register the pytest_timeout module as a plugin?
_LOADED_PROBE = """
import sys, pytest
class _Probe:
    loaded = None
    def pytest_configure(self, config):
        _Probe.loaded = any(getattr(p, "__name__", "") == "pytest_timeout"
                            for p in config.pluginmanager.get_plugins())
pytest.main(["-q", "-p", "no:cacheprovider", "--collect-only", sys.argv[1]], plugins=[_Probe()])
print("PTEST-TIMEOUT-LOADED" if _Probe.loaded else "PTEST-TIMEOUT-NOT-LOADED", flush=True)
"""


def git(co: Path, *args: str) -> "tuple[int, str]":
    r = subprocess.run(["git", "-C", str(co), *args], capture_output=True, text=True)
    return r.returncode, (r.stdout.strip() if r.returncode == 0 else r.stderr.strip())


def load_tiering(co: Path):
    path = co / "tests" / "tiering.py"
    if not path.is_file():
        raise Refusal(f"no {path}: the run tiers are decided there (task-29.4 #r1)")
    spec = importlib.util.spec_from_file_location("ptest_tiering", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_weights(co: Path) -> dict:
    p = co / "tests" / "shard_weights.json"
    if not p.is_file():
        return {}
    try:
        files = json.loads(p.read_text())["files"]
        return {str(k): float(v) for k, v in files.items()}
    except (ValueError, KeyError, TypeError) as exc:
        raise Refusal(f"{p}: unreadable weights ({exc})") from exc


def static_test_count(path: Path) -> int:
    """`def test*` at module level and in `Test*` classes: the placer's per-file count for an
    unweighted file. Parametrisation is not expanded (a collection pass would cost a pytest
    process per run); the summary says the count is static."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    n = 0
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and \
                node.name.startswith("test"):
            n += 1
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            n += sum(1 for m in node.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
                     and m.name.startswith("test"))
    return max(n, 1)


# ---- the plan --------------------------------------------------------------------------------

class Shard:
    def __init__(self, sid: str, tier: str, files: list):
        self.sid, self.tier, self.files = sid, tier, list(files)
        self.cmd: list = []
        self.proc = None
        self.rc: "int | None" = None
        self.root: "str | None" = None
        self.counts: dict = {}
        self.wall = 0.0
        self.notes: list = []
        self.log = self.failures = self.outcomes = None


def default_shards(concurrent_tiers: int = 1) -> int:
    """Ruling L192 (3): load stays at or under the core count. A daemon-tier shard keeps a
    child (a daemon, a CLI, an inner pytest) busy beside its pytest process, so the budget is
    half the cores, split between the tiers that run at the same time."""
    cpu = os.cpu_count() or 2
    return max(1, max(1, cpu // 2) // max(1, concurrent_tiers))


def place(weighted: list, n: int, models: set) -> list:
    """Greedy, deterministic: heaviest first (ties by path), each into the lightest shard (ties
    by index); a model-loading file only into shards 0 and 1 (#r2-shared). Empty shards are
    dropped and the rest renumbered."""
    n = max(1, n)
    shards: list = [[] for _ in range(n)]
    loads = [0.0] * n
    for rel, w in sorted(weighted, key=lambda x: (-x[1], x[0])):
        cand = range(min(2, n)) if rel in models else range(n)
        k = min(cand, key=lambda i: (loads[i], i))
        shards[k].append(rel)
        loads[k] += w
    return [s for s in shards if s]


class Plan:
    def __init__(self):
        self.phases: list = []          # list of lists of Shard, run phase by phase
        self.not_run: list = []         # (tier, reason)
        self.no_weight: list = []       # summary lines
        self.tiers_asked: list = []


def build_plan(co: Path, tiering, files_by_tier: dict, tiers_asked: list, shards_opt,
               owning: bool) -> Plan:
    plan = Plan()
    plan.tiers_asked = list(tiers_asked)
    weights = load_weights(co)
    serial_names = set(getattr(tiering, "SERIAL_GROUP", {}))

    def weigh(tier: str, rels: list) -> list:
        per_test = []
        tier_all = [f"tests/{p.name}" for p in tiering.list_test_files(co / "tests")
                    if tiering.tier_of(p) == tier]
        for rel in tier_all:
            if rel in weights:
                per_test.append(weights[rel] / static_test_count(co / rel))
        if not per_test:
            per_test = [w / static_test_count(co / r) for r, w in weights.items()
                        if (co / r).is_file()] or [1.0]
            basis = "the median of every weighted file"
        else:
            basis = f"the {tier} median"
        med = statistics.median(per_test)
        out = []
        for rel in rels:
            if rel in weights:
                out.append((rel, weights[rel]))
            else:
                n = static_test_count(co / rel)
                w = med * n
                out.append((rel, w))
                plan.no_weight.append(
                    f"no weight: {rel} ({tier}) placed at {w:.2f} s = {basis} {med:.3f} s/test "
                    f"x {n} test(s) (static count); add it to tests/shard_weights.json")
        return out

    sharded = [t for t in SHARDED_TIERS if t in tiers_asked and files_by_tier.get(t)]
    n = shards_opt if shards_opt else default_shards(len(sharded) or 1)
    first, serial = [], []
    for tier in SHARDED_TIERS:
        if tier not in tiers_asked:
            continue
        rels = files_by_tier.get(tier, [])
        serial += [r for r in rels if r in serial_names]
        rels = [r for r in rels if r not in serial_names]
        if not rels:
            continue
        models = {r for r in rels if tiering.loads_models(co / r)}
        for k, files in enumerate(place(weigh(tier, rels), n, models)):
            first.append(Shard(f"{tier}-{k}", tier, files))
    if first:
        plan.phases.append(first)
    if serial:
        for r in serial:                                            # names unweighted ones
            if r not in weights:
                weigh(tiering.tier_of(co / r), [r])
        plan.phases.append([Shard("serial", "serial", sorted(serial))])
    for tier in ("timing", "devtree"):
        if tier not in tiers_asked:
            continue
        rels = files_by_tier.get(tier, [])
        if tier == "devtree" and not owning:
            plan.not_run.append(("devtree", "NOT RUN here (clone)"))
            continue
        if rels:
            weigh(tier, [r for r in rels if r not in weights])
            plan.phases.append([Shard(f"{tier}-0", tier, sorted(rels))])
    for t in TIER_ORDER:
        if t not in tiers_asked:
            plan.not_run.append((t, "NOT RUN here (clone)" if t == "devtree" and not owning
                                 else "not asked"))
    return plan


# ---- running ---------------------------------------------------------------------------------

_ROOT_RX = re.compile(r"^rmx sandbox root: (\S+)\s*$", re.MULTILINE)
_COLLECTED_RX = re.compile(r"^collected (\d+) items?", re.MULTILINE)
_FINAL_RX = re.compile(r"^=+ (.+?) in [\d.]+s(?: \([\d:]+\))? =+\s*$", re.MULTILINE)
_COUNT_RX = re.compile(r"(\d+) (passed|failed|errors?|skipped|xfailed|xpassed|deselected)")
_TIMEOUT_RX = re.compile(r"^\++ Timeout \++\s*$", re.MULTILINE)
_TIMEOUT_FAIL_RX = re.compile(r"Timeout \(>[\d.]+s\) from pytest-timeout")


def shard_env(rd: Path, s: Shard, co: Path) -> dict:
    env = dict(os.environ)
    env.pop(OUT_OWNER, None)
    env.pop("PYTEST_CURRENT_TEST", None)
    env["RMX_FAILURES_OUT"] = str(rd / "shards" / f"{s.sid}.failures.jsonl")
    env["RMX_OUTCOMES_OUT"] = str(rd / "shards" / f"{s.sid}.outcomes.jsonl")
    pp = [p for p in env.get("PYTHONPATH", "").split(os.pathsep) if p]
    src = str(co / "src")
    env["PYTHONPATH"] = os.pathsep.join([src] + [p for p in pp if p != src])
    return env


def start(rd: Path, s: Shard, co: Path, py: str) -> None:
    s.cmd = [py, "-m", "pytest", "-p", "no:cacheprovider", "-rfE", *s.files]
    s.log = rd / f"{s.sid}.log"
    s.failures = rd / "shards" / f"{s.sid}.failures.jsonl"
    s.outcomes = rd / "shards" / f"{s.sid}.outcomes.jsonl"
    for p in (s.failures, s.outcomes):
        p.write_text("")
    fh = open(s.log, "w")
    s.t0 = time.monotonic()
    s.proc = subprocess.Popen(s.cmd, cwd=str(co), env=shard_env(rd, s, co), stdout=fh,
                              stderr=subprocess.STDOUT, start_new_session=True)
    s._fh = fh
    s._timeouts_seen = 0
    say(f"started {s.sid} (pid {s.proc.pid}): {rerun_command(s, co)}")


def rerun_command(s: Shard, co: Path) -> str:
    return (f"cd {shlex.quote(str(co))} && PYTHONPATH={shlex.quote(str(co / 'src'))} "
            + shlex.join(s.cmd))


def ps_snapshot(pgid: int) -> str:
    """`ps -o pid,etime,time,command` for one shard's process group (#r2 hang guard)."""
    r = subprocess.run(["ps", "-A", "-o", "pid=,pgid=,etime=,time=,command="],
                       capture_output=True, text=True)
    rows = ["  PID  ETIME     TIME COMMAND"]
    for ln in r.stdout.splitlines():
        parts = ln.split(None, 4)
        if len(parts) == 5 and parts[1] == str(pgid):
            rows.append(f"{parts[0]} {parts[2]} {parts[3]} {parts[4]}")
    return "\n".join(rows)


def watch_timeouts(rd: Path, s: Shard) -> None:
    """pytest-timeout's `signal` method prints a `+++ Timeout +++` banner while the stuck test
    is still alive: record the shard's process group at that moment."""
    try:
        n = len(_TIMEOUT_RX.findall(s.log.read_text(errors="replace")))
    except OSError:
        return
    if n > s._timeouts_seen:
        s._timeouts_seen = n
        snap = ps_snapshot(s.proc.pid)
        with open(rd / f"{s.sid}.ps.txt", "a") as fh:
            fh.write(f"# {time.strftime('%Y-%m-%dT%H:%M:%S')} timeout banner #{n}\n{snap}\n")
        s.notes.append(f"pytest-timeout fired; process group recorded in {s.sid}.ps.txt")


def stop_group(s: Shard) -> None:
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(s.proc.pid, sig)
        except ProcessLookupError:
            return
        try:
            s.proc.wait(timeout=10)
            return
        except subprocess.TimeoutExpired:
            continue


def run_phase(rd: Path, shards: list, co: Path, py: str, deadline_s: "float | None") -> None:
    for s in shards:
        start(rd, s, co, py)
    running = list(shards)
    while running:
        time.sleep(_POLL_S)
        for s in list(running):
            watch_timeouts(rd, s)
            if s.proc.poll() is None:
                if deadline_s and time.monotonic() - s.t0 > deadline_s:
                    with open(rd / f"{s.sid}.ps.txt", "a") as fh:
                        fh.write(f"# deadline {deadline_s:.0f} s passed\n"
                                 f"{ps_snapshot(s.proc.pid)}\n")
                    stop_group(s)
                    s.notes.append(f"KILLED at the run deadline ({deadline_s:.0f} s); process "
                                   f"group in {s.sid}.ps.txt")
                continue
            running.remove(s)
            finish(s)
            say(f"finished {s.sid}: exit={s.rc} {fmt_counts(s.counts)} wall={s.wall:.1f}s")


def finish(s: Shard) -> None:
    s.rc = s.proc.returncode
    s.wall = time.monotonic() - s.t0
    s._fh.close()
    text = s.log.read_text(errors="replace")
    m = _ROOT_RX.search(text)
    s.root = m.group(1) if m else None
    m = _COLLECTED_RX.search(text)
    s.counts = {"collected": int(m.group(1)) if m else None}
    if _TIMEOUT_FAIL_RX.search(text) and not getattr(s, "_timeouts_seen", 0):
        # bsd-294a r1 m-1 (L197): pytest-timeout's signal method prints its banner only when
        # more than one thread is alive, so a main-thread hang leaves no moment to snapshot.
        s.notes.append("pytest-timeout fired; no process snapshot taken (no `+++ Timeout +++` "
                       "banner: a single-threaded hang)")
    finals = _FINAL_RX.findall(text)
    if finals:
        # a parsed final line: a count it does not name is 0, not unknown
        s.counts.update({k: 0 for k in _COUNT_KEYS[1:]})
        for num, what in _COUNT_RX.findall(finals[-1]):
            key = "errors" if what.startswith("error") else what
            s.counts[key] = int(num)


_COUNT_KEYS = ("collected", "passed", "failed", "errors", "skipped", "xfailed", "xpassed")


def fmt_counts(c: dict) -> str:
    """`?` = not read from the shard's log (no `collected` line, or no final summary line)."""
    return " ".join(f"{k}={c[k] if c.get(k) is not None else '?'}" for k in _COUNT_KEYS)


def read_jsonl(p: Path) -> list:
    out = []
    if not p.is_file():
        return out
    for i, ln in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        if not ln.strip():
            continue
        try:
            out.append(json.loads(ln))
        except ValueError as exc:
            raise Refusal(f"{p}:{i}: not JSON ({exc})") from exc
    return out


def precompile(rd: Path, co: Path, py: str) -> "str | None":
    """#r2-shared: compile `src/` once (checked-hash, bug-037's safe form) and run the pyc
    guard BEFORE the shards start, so shards and their children read bytecode instead of all
    compiling `cli.py` at once. Returns a failure line, or None."""
    pkg = co / "src" / "refmatrix"
    if not pkg.is_dir():
        return f"precompile: no {pkg}"
    log = rd / "precompile.log"
    with open(log, "w") as fh:
        for cmd in ([py, "-m", "compileall", "-q", "--invalidation-mode", "checked-hash",
                     str(pkg)],
                    [py, str(co / "tools" / "pyc_guard.py"), str(pkg)]):
            fh.write(f"$ {shlex.join(cmd)}\n")
            fh.flush()
            r = subprocess.run(cmd, cwd=str(co), stdout=fh, stderr=subprocess.STDOUT)
            fh.write(f"exit {r.returncode}\n")
            if r.returncode != 0:
                return f"precompile: `{shlex.join(cmd)}` exited {r.returncode} (see {log})"
    return None


class Run:
    """One run directory's results."""

    def __init__(self, name: str, rd: Path, co: Path, py: str, owning: bool):
        self.name, self.rd, self.co, self.py, self.owning = name, rd, co, py, owning
        self.shards: list = []
        self.problems: list = []
        self.failures: list = []
        self.started = time.strftime("%Y-%m-%dT%H:%M:%S")
        self.load0 = os.getloadavg()[0]
        self.load1 = None
        self.t0 = time.monotonic()
        rc, top = git(co, "rev-parse", "--show-toplevel")
        rc2, sha = git(co, "rev-parse", "HEAD")
        mine = rc == 0 and rc2 == 0 and Path(top).resolve() == co.resolve()
        self.sha = sha if mine else "unknown (not a git checkout)"


def make_run_dir(co: Path, name: str) -> Path:
    rd = co / "workflow" / "review-output" / name
    if rd.exists():
        aside = rd.with_name(f"{rd.name}.{time.strftime('%Y%m%d-%H%M%S')}")
        rd.rename(aside)
        say(f"run dir {rd} existed; moved aside to {aside}")
    (rd / "shards").mkdir(parents=True)
    return rd


def execute(run: Run, plan: Plan, deadline_s) -> None:
    bad = precompile(run.rd, run.co, run.py)
    if bad:
        run.problems.append(bad)
        return
    for phase in plan.phases:
        run_phase(run.rd, phase, run.co, run.py, deadline_s)
        run.shards += phase
    run.load1 = os.getloadavg()[0]
    # the records, concatenated in shard order
    for kind in ("failures", "outcomes"):
        with open(run.rd / f"{kind}.jsonl", "w", encoding="utf-8") as out:
            for s in run.shards:
                p = s.failures if kind == "failures" else s.outcomes
                if p is not None and p.is_file():
                    out.write(p.read_text(encoding="utf-8"))
    for s in run.shards:
        recs = read_jsonl(s.failures)
        for r in recs:
            r["_shard"] = s.sid
        run.failures += recs
    roots: dict = {}
    for s in run.shards:
        if s.root is None:
            run.problems.append(f"{s.sid}: no `rmx sandbox root:` line in its log header, so "
                                f"its sandbox cannot be shown to be its own")
            continue
        roots.setdefault(s.root, []).append(s.sid)
    for root, sids in roots.items():
        if len(sids) > 1:
            run.problems.append(f"shards {', '.join(sids)} share the sandbox root {root}")
    for s in run.shards:
        if s.rc != 0 and not any(r["_shard"] == s.sid for r in run.failures):
            run.problems.append(f"{s.sid} exited {s.rc} with no failures.jsonl record "
                                f"(collection error, crash or interrupt: read {s.sid}.log)")


def shard_line(s: Shard, co: Path) -> str:
    note = f" note: {'; '.join(s.notes)}" if s.notes else ""
    return (f"{s.sid} exit={s.rc} root={s.root or 'MISSING'} {fmt_counts(s.counts)} "
            f"wall={s.wall:.1f}s files={len(s.files)}{note} cmd: {rerun_command(s, co)}")


def failure_lines(run: Run, seen: "set | None" = None) -> list:
    out = []
    if not run.failures:
        return ["failures: none recorded"]
    out.append(f"failures ({len(run.failures)}, from failures.jsonl):")
    for r in run.failures:
        tag = ""
        if seen is not None:
            key = (r["nodeid"], r["phase"], normalise_e_line(r["e"]))
            tag = "seen (open in the previous gate) " if key in seen else "NEW "
        out.append(f"  {tag}FAILED {r['nodeid']} [{r['phase']}] in {r['_shard']}: {r['e']}")
    touches = [r for r in run.failures if "SandboxViolation" in r.get("e", "")]
    if touches:
        out.append(f"live touches ({len(touches)}): the sandbox refused a live target; the test "
                   f"and the target are named:")
        for r in touches:
            out.append(f"  LIVE TOUCH {r['nodeid']} [{r['phase']}]: {r['e']}")
    return out


def header_lines(run: Run, kind: str) -> list:
    return [f"# ptest {kind} {run.name}: sha {run.sha}; checkout {run.co} "
            f"({'owning' if run.owning else 'clone'}); started {run.started}; "
            f"load at start {run.load0:.2f}",
            f"# interpreter {run.py}; logs in {run.rd}"]


def totals_line(run: Run) -> str:
    tot: dict = {}
    for k in _COUNT_KEYS:
        vals = [s.counts.get(k) for s in run.shards]
        tot[k] = None if any(v is None for v in vals) else sum(vals)
    nonzero = sum(1 for s in run.shards if s.rc != 0)
    load1 = f"{run.load1:.2f}" if run.load1 is not None else "?"
    return (f"totals: shards={len(run.shards)} non-zero={nonzero} {fmt_counts(tot)} "
            f"wall={time.monotonic() - run.t0:.1f}s load at end {load1}")


def write_summary(run: Run, lines: list) -> None:
    text = "\n".join(lines) + "\n"
    (run.rd / "summary.txt").write_text(text)
    say("")
    say(text.rstrip("\n"))


# ---- modes -----------------------------------------------------------------------------------

def tier_files(co: Path, tiering, rels: "list | None") -> dict:
    """`tier -> [repo-relative paths]` for every top-level `tests/test_*.py`, or for `rels`."""
    tests = co / "tests"
    nested = sorted(p for p in tests.rglob("test_*.py") if p.parent != tests
                    and not ({"fixtures", "sandbox_site", "__pycache__"} & set(p.relative_to(tests).parts)))
    if nested:
        raise Refusal("test files in a subdirectory of tests/ have no tier (task-29.4 "
                      "#r1-also): " + ", ".join(str(p.relative_to(co)) for p in nested))
    paths = [co / r for r in rels] if rels is not None else tiering.list_test_files(tests)
    by: dict = {t: [] for t in TIER_ORDER}
    for p in paths:
        try:
            t = tiering.tier_of(p)
        except tiering.TierError as exc:
            raise Refusal(f"run tier: {exc}") from exc
        by[t].append(f"tests/{p.name}")
    return by


def mode_run(args, co: Path) -> int:
    owning, why = checkout_kind(co)
    py = interpreter(co)
    tiering = load_tiering(co)
    if args.files:
        rels = []
        for f in args.files:
            p = (Path(f) if os.path.isabs(f) else co / f).resolve()
            if p.parent != (co / "tests").resolve() or not p.is_file():
                raise Refusal(f"--files {f}: not a test file directly in {co / 'tests'}")
            rels.append(f"tests/{p.name}")
        by = tier_files(co, tiering, rels)
        asked = [t for t in TIER_ORDER if by[t]]
        kind = "files"
    else:
        by = tier_files(co, tiering, None)
        asked = list(TIER_ORDER) if args.tier == "all" else [args.tier]
        kind = f"tier {args.tier}"
    if asked == ["devtree"] and not owning:
        raise Refusal(f"{NOT_RUN_CLONE} ({why})")
    require_hang_guard(py)
    name = args.name or f"ptest-{'files' if args.files else args.tier}-" \
                        f"{time.strftime('%Y%m%d-%H%M%S')}"
    rd = make_run_dir(co, name)
    run = Run(name, rd, co, py, owning)
    plan = build_plan(co, tiering, by, asked, args.shards, owning)
    for ln in plan.no_weight:
        say(ln)
    deadline = args.max_minutes * 60 if args.max_minutes else None
    execute(run, plan, deadline)
    lines = header_lines(run, kind)
    lines += [shard_line(s, co) for s in run.shards]
    lines += plan.no_weight
    lines += failure_lines(run)
    lines += [f"PROBLEM: {p}" for p in run.problems]
    lines.append(totals_line(run))
    failed = bool(run.problems) or any(s.rc != 0 for s in run.shards)
    nonzero = sum(1 for s in run.shards if s.rc != 0)
    verdict = (f"FAILED: {nonzero} of {len(run.shards)} shard(s) exited non-zero"
               + (f", {len(run.problems)} problem(s)" if run.problems else "")
               if failed else f"passed: {len(run.shards)} shard(s), each exited 0")
    if any(t == "devtree" and r.startswith("NOT RUN") for t, r in plan.not_run):
        say(NOT_RUN_CLONE)
        lines.append(NOT_RUN_CLONE)
    missing = [t for t, _ in plan.not_run]
    if missing:
        lines.append(f"INCOMPLETE for a merge: tier(s) not run: "
                     + ", ".join(f"{t} ({r})" for t, r in plan.not_run)
                     + f"; this run {verdict}")
    else:
        lines.append(f"run {verdict}; every tier ran (unit, daemon, timing, devtree)")
    write_summary(run, lines)
    return 1 if failed else 0


def mode_merge_gate(args, co: Path) -> int:
    owning, why = checkout_kind(co)
    if not owning:
        raise Refusal(f"--merge-gate refuses to run here: {why}. The merge gate runs in the "
                      f"owning checkout, after `git merge --no-commit` and before the merge "
                      f"commit (task-29.4 #r7)")
    rc, merge_head = git(co, "rev-parse", "-q", "--verify", "MERGE_HEAD")
    if rc != 0 or not merge_head:
        raise Refusal("--merge-gate: no merge in progress (no MERGE_HEAD); run it after "
                      "`git merge --no-commit --no-ff <branch>`")
    rc, head = git(co, "rev-parse", "HEAD")
    if rc != 0:
        raise Refusal(f"--merge-gate: git rev-parse HEAD failed: {head}")
    rc, diff = git(co, "diff", "--cached", "--name-only", "HEAD")
    if rc != 0:
        raise Refusal(f"--merge-gate: git diff failed: {diff}")
    py = interpreter(co)
    tiering = load_tiering(co)
    touched = sorted(r for r in diff.splitlines()
                     if re.fullmatch(r"tests/test_[^/]*\.py", r) and (co / r).is_file())
    by_all = tier_files(co, tiering, None)
    problems = []
    always = []
    for r in sorted(getattr(tiering, "ALWAYS_FILES", {})):
        if (co / r).is_file():
            always.append(r)
        else:
            problems.append(f"ALWAYS_FILES names {r}, which is not on disk")
    rels = sorted(set(by_all["devtree"]) | set(touched) | set(always))
    require_hang_guard(py)
    name = f"merge-gate-{merge_head}"
    rd = make_run_dir(co, name)
    run = Run(name, rd, co, py, owning)
    run.problems += problems
    by = tier_files(co, tiering, rels) if rels else {t: [] for t in TIER_ORDER}
    asked = list(TIER_ORDER)
    plan = build_plan(co, tiering, by, asked, args.shards, owning)
    execute(run, plan, args.max_minutes * 60 if args.max_minutes else None)
    # the lint gate
    lint = co / "scripts" / "lint-gmd.sh"
    lint_log = rd / "lint-gmd.log"
    if lint.is_file():
        with open(lint_log, "w") as fh:
            lint_rc = subprocess.run(["bash", str(lint)], cwd=str(co), stdout=fh,
                                     stderr=subprocess.STDOUT).returncode
    else:
        lint_rc = None
        run.problems.append(f"no lint gate at {lint}")
    # compare by E line against the previous gate (#r7)
    prev = previous_gate(co, rd)
    seen: set = set()
    if prev is not None:
        seen = {(r["nodeid"], r["phase"], normalise_e_line(r["e"]))
                for r in read_jsonl(prev / "failures.jsonl")}
    new = [r for r in run.failures
           if (r["nodeid"], r["phase"], normalise_e_line(r["e"])) not in seen]
    lines = header_lines(run, "merge gate")
    lines.append(f"# merge head {merge_head}; touched test files: {', '.join(touched) or 'none'}; "
                 f"devtree files: {len(by_all['devtree'])}; ALWAYS_FILES: {len(always)}")
    lines.append(f"# previous gate: {prev if prev is not None else 'none (no passed gate whose merge head is an ancestor of HEAD; every failure is new)'}")
    lines += [shard_line(s, co) for s in run.shards]
    lines += plan.no_weight
    lines += failure_lines(run, seen)
    lines.append(f"lint gate ./scripts/lint-gmd.sh: "
                 + ("not run" if lint_rc is None else f"exit code {lint_rc}"
                    + (" FAILED" if lint_rc else " ok")) + f" (log {lint_log.name})")
    lines += [f"PROBLEM: {p}" for p in run.problems]
    lines.append(totals_line(run))
    reasons = []
    if new:
        reasons.append(f"{len(new)} new failure(s): " + ", ".join(
            f"{r['nodeid']} [{r['phase']}]" for r in new[:10]))
    if lint_rc != 0:
        reasons.append("the lint gate failed" if lint_rc is not None else "no lint gate")
    if run.problems:
        reasons.append(f"{len(run.problems)} problem(s)")
    lines.append(("merge gate FAILED: " + "; ".join(reasons)) if reasons else
                 f"merge gate passed: {len(run.shards)} shard(s), "
                 f"{len(run.failures)} failure record(s) all open in the previous gate, lint ok")
    write_summary(run, lines)
    (rd / GATE_RECORD).write_text(json.dumps(
        {"merge_head": merge_head, "head": head, "passed": not reasons,
         "exit": 1 if reasons else 0, "finished": time.strftime("%Y-%m-%dT%H:%M:%S")}) + "\n")
    return 1 if reasons else 0


_GATE_DIR_RX = re.compile(r"merge-gate-([0-9a-f]{40,64})")
GATE_RECORD = "gate.json"


def previous_gate(co: Path, current: Path) -> "Path | None":
    """The baseline of #r7's E-line comparison: the newest gate that PASSED (its `gate.json`
    says so) and whose merge head is an ancestor of HEAD (it was merged). Never a failed gate,
    never a gate of a merge that was not committed, and never a moved-aside
    `merge-gate-<sha>.<ts>` copy (only an exact `merge-gate-<sha>` directory qualifies).

    bug-304 (bsd-294a r1 b-1, ruling L197, 2026-11-24): the baseline was "the newest earlier
    merge-gate-* run with a summary", so a failed gate re-run on the same merge took its own
    moved-aside copy as the baseline, read every failure as `seen` and passed; a different
    merge carrying the failure did the same."""
    cands = []
    for d in (co / "workflow" / "review-output").glob("merge-gate-*"):
        m = _GATE_DIR_RX.fullmatch(d.name)
        if m is None or d == current or not (d / GATE_RECORD).is_file():
            continue
        try:
            rec = json.loads((d / GATE_RECORD).read_text())
        except ValueError:
            continue
        if rec.get("passed") is not True or rec.get("merge_head") != m.group(1):
            continue
        rc, _ = git(co, "merge-base", "--is-ancestor", m.group(1), "HEAD")
        if rc == 0:
            cands.append(d)
    if not cands:
        return None
    return max(cands, key=lambda d: (d / GATE_RECORD).stat().st_mtime)


# ---- --compare -------------------------------------------------------------------------------

def run_records(d: Path, fname: str) -> list:
    p = Path(d) / fname
    if not p.is_file():
        raise Refusal(f"--compare: no {fname} in {d}")
    return read_jsonl(p)


def mode_compare_failures(a: Path, b: Path) -> int:
    def keyset(d):
        return {(r["nodeid"], r["phase"], normalise_e_line(r["e"]))
                for r in run_records(d, "failures.jsonl")}
    ka, kb = keyset(a), keyset(b)
    if ka == kb:
        say(f"equal: {len(ka)} failure record(s) by (node id, phase, normalised E line)")
        return 0
    for tag, only in (("only in A", ka - kb), ("only in B", kb - ka)):
        for node, phase, e in sorted(only):
            say(f"{tag}: {node} [{phase}] {e}")
    say(f"DIFFERENT: {len(ka - kb)} record(s) only in A ({a}), {len(kb - ka)} only in B ({b})")
    return 1


PHASES = ("setup", "call", "teardown")
OUTCOMES = ("passed", "failed", "error", "skipped", "xfailed", "xpassed")


def parse_expect(s: str) -> tuple:
    """`<node id>:<phase>:<from>-><to>`, parsed from the RIGHT (a node id may hold a colon)."""
    parts = s.rsplit(":", 2)
    if len(parts) != 3 or "->" not in parts[2]:
        raise Refusal(f"--expect {s!r}: want '<node id>:<phase>:<from>-><to>'")
    node, phase, change = parts
    frm, to = change.split("->", 1)
    if phase not in PHASES or frm not in OUTCOMES or to not in OUTCOMES or not node:
        raise Refusal(f"--expect {s!r}: phase must be one of {PHASES}, outcomes of {OUTCOMES}")
    return node, phase, frm, to


def mode_compare_outcomes(a: Path, b: Path, expects: list) -> int:
    def table(d):
        out: dict = {}
        dup = []
        for r in run_records(d, "outcomes.jsonl"):
            k = (r["nodeid"], r["phase"])
            if k in out:
                dup.append(k)
            out[k] = r["outcome"]
        return out, dup
    ta, da = table(a)
    tb, db = table(b)
    bad = [f"recorded twice in A: {n} [{p}]" for n, p in da]
    bad += [f"recorded twice in B: {n} [{p}]" for n, p in db]
    exp = {}
    for e in expects:
        node, phase, frm, to = parse_expect(e)
        exp[(node, phase)] = (frm, to)
    for k in sorted(set(ta) | set(tb) | set(exp)):
        node, phase = k
        oa, ob = ta.get(k, "<absent>"), tb.get(k, "<absent>")
        if k in exp:
            frm, to = exp[k]
            if (oa, ob) != (frm, to):
                bad.append(f"--expect {node}:{phase}:{frm}->{to} did not hold: "
                           f"A={oa}, B={ob}")
        elif oa != ob:
            bad.append(f"changed: {node} [{phase}] A={oa} B={ob}")
    if not bad:
        say(f"equal: {len(ta)} node/phase outcome(s), {len(exp)} expected change(s) held")
        return 0
    for ln in bad:
        say(ln)
    say(f"DIFFERENT: {len(bad)} difference(s) between {a} and {b}")
    return 1


# ---- main ------------------------------------------------------------------------------------

def parse_args(argv: list):
    ap = argparse.ArgumentParser(prog="ptest.sh", description=__doc__.split("\n\n")[0])
    ap.add_argument("--tier", choices=("unit", "daemon", "devtree", "timing", "all"),
                    default="all")
    ap.add_argument("--files", nargs="+", metavar="F")
    ap.add_argument("--shards", type=int, default=None,
                    help="shard processes per tier: unit and daemon EACH get N, so --tier all "
                         "runs up to 2N at once (timing and devtree run in one process each); "
                         "default: default_shards(), half of os.cpu_count() split between the "
                         "tiers that run at the same time")
    ap.add_argument("--name")
    ap.add_argument("--max-minutes", type=float, default=None,
                    help="kill a shard's process group past this many minutes (off by default)")
    ap.add_argument("--compare", action="store_true")
    ap.add_argument("--outcomes", action="store_true")
    ap.add_argument("--expect", action="append", default=[])
    ap.add_argument("--merge-gate", action="store_true")
    ap.add_argument("dirs", nargs="*")
    args = ap.parse_args(argv)
    if args.shards is not None and args.shards < 1:
        ap.error("--shards must be >= 1")
    if args.compare and len(args.dirs) != 2:
        ap.error("--compare takes two run directories")
    if not args.compare and (args.dirs or args.outcomes or args.expect):
        ap.error("run directories, --outcomes and --expect go with --compare")
    if args.expect and not args.outcomes:
        ap.error("--expect goes with --compare --outcomes")
    if args.name and ("/" in args.name or args.name in (".", "..")):
        ap.error("--name is one path component")
    return args


def main(argv: "list | None" = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.compare:
            a, b = (Path(d) for d in args.dirs)
            if args.outcomes:
                return mode_compare_outcomes(a, b, args.expect)
            return mode_compare_failures(a, b)
        if args.merge_gate:
            return mode_merge_gate(args, CHECKOUT)
        return mode_run(args, CHECKOUT)
    except Refusal as exc:
        print(f"ptest: {exc}", file=sys.stderr, flush=True)
        if str(exc).startswith(NOT_RUN_CLONE):
            say(NOT_RUN_CLONE)
        return 2


if __name__ == "__main__":
    sys.exit(main())
