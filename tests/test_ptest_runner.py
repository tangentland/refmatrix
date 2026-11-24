"""plan-29 task 29.4a (stage 4): the sharded runner, `scripts/ptest.sh` -> `scripts/ptest.py`.

WHY. The suite has one way to run today: every test, one process, file order (58:37 for the
0.83.0 release). Shards are several processes, and each one can reach a live socket (bug-088,
bug-101). The user decided (`plan-review-fable D3` = (a), ruling L106) that nothing is sharded
until a live touch fails the RUN, in every shard, and the serial group: that is AC-12, stage 4's
first AC, and it is the first block of this file. The rest pins the runner of task-29.4 `#r2`
(AC-2, AC-3) and the merge gate of `#r7` (AC-9).

Everything runs through the entry point a user calls: `bash scripts/ptest.sh …` as a child
process, on a throwaway checkout built by `tests/suite_health_tree.py` from the `case_*.py`
fixtures of `tests/fixtures/suite_health/` (never collected by the real suite,
`#r1-fixtures`). Each shard is a real pytest process with this checkout's conftest, so the
sandbox refusal, SkipGate and the reaper under test are the real ones. Nothing is mocked.

THE CONTRACT these tests pin for GREEN (names the spec leaves open are chosen here, once):
- `scripts/ptest.sh --tier unit|daemon|devtree|timing|all [--shards N] [--name RUN]`;
  `--compare DIR_A DIR_B`; `--compare --outcomes DIR_A DIR_B [--expect 'node:phase:a->b' …]`;
  `--merge-gate`. A run directory is passed to `--compare` as a PATH.
- The shards' interpreter is `$RMX_PYTEST_PY` when set (today's `ptest.sh` already reads it).
- A run writes `<checkout>/workflow/review-output/<RUN>/`: `<tier>-<k>.log` per shard,
  `summary.txt`, `failures.jsonl`, `outcomes.jsonl`. The checkout is the one the script lives in.
- `summary.txt` has one line per shard holding: the shard id (`<tier>-<k>`; the serial group's
  is `serial` or `serial-<k>`), `exit=<int>`, `root=<sandbox root>`, and the shard's command
  (so it names each of the shard's files by repo-relative path). A file with no weight is named
  on a line that says `no weight`. When tier (c) did not run, the LAST line names `devtree` and
  says the run is `incomplete`; nothing ever says "all green" then.
- In a clone, stdout carries, verbatim: `tier devtree: NOT RUN here (clone); run it in the
  owning checkout before the merge commit`.
- `failures.jsonl` records are `{"nodeid", "phase", "e"}` (the keys `rmx_sandbox.failure_record`
  already writes); `outcomes.jsonl` records are `{"nodeid", "phase", "outcome"}`.
- `scripts/ptest.py` exposes `normalise_e_line(str) -> str`, the ONE normalisation rule.
- `tests/tiering.py` exposes `DEVTREE_FILES`, `ALWAYS_FILES`, `SERIAL_GROUP` as dicts
  (repo-relative path -> reason); a fixture checkout appends its own entries to them.

Mutations this file kills (task-29.4 `#test-strategy`): AC-12's (the run's exit code taken from
the last shard only: the position-0 run passes), 3 (0 when a shard exits non-zero), 4 ("all
green" with tier (c) not run), 5 (`--compare` ignores the phase), 6 (the normaliser replaces
words), 15 (the merge gate ignores teardown errors), 24 (no `xfailed` / `xpassed`), 25
(`--compare --outcomes` ignores a node missing from one run), 26 (a strict XPASS recorded
`xpassed`), 27 (`--expect` ignores its phase).
"""
from __future__ import annotations

import importlib.util
import json
import os
import pwd
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests import suite_health_tree as sht

_REPO = sht.REPO
_PTEST_SH = _REPO / "scripts" / "ptest.sh"
_PTEST_PY = _REPO / "scripts" / "ptest.py"

# Hang guard for one runner invocation (not a bound under test): a fixture run is a few pytest
# processes of one to seven trivial tests each, seconds on an idle machine.
_RUN_HANG_GUARD_S = 420.0

_NOT_RUN = ("tier devtree: NOT RUN here (clone); run it in the owning checkout before the "
            "merge commit")
# A shard id not glued to a preceding word or dash (a run named `x-unit-0` is not shard unit-0).
_SHARD_ID = re.compile(r"(?<![-\w])((?:unit|daemon|devtree|timing)-\d+|serial(?:-\d+)?)\b")
_EXIT = re.compile(r"\bexit=(-?\d+)\b")
_ROOT = re.compile(r"\broot=(\S+)")

# AC-12's deny-set target, computed as the fixtures compute it (case_live_touch*.py).
_TARGET = os.path.join(pwd.getpwuid(os.getuid()).pw_dir, ".refmatrix", "rmx-294a-ac12-probe")


# ---- running the runner --------------------------------------------------------------------

def _ptest(tree: Path, *args: str) -> "subprocess.CompletedProcess":
    script = tree / "scripts" / "ptest.sh"
    assert script.is_file(), f"no runner at {script} (task-29.4 #r2: scripts/ptest.sh)"
    env = dict(os.environ, RMX_PYTEST_PY=sys.executable)
    try:
        return subprocess.run(["bash", str(script), *args], cwd=str(tree), env=env,
                              capture_output=True, text=True, timeout=_RUN_HANG_GUARD_S)
    except subprocess.TimeoutExpired as e:
        out = e.stdout.decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        pytest.fail(f"ptest.sh {' '.join(args)} hung past {_RUN_HANG_GUARD_S} s (hang guard):\n"
                    + out[-3000:])


def _out(r: "subprocess.CompletedProcess") -> str:
    return (r.stdout or "") + (r.stderr or "")


def _summary(tree: Path, name: str, r) -> str:
    p = sht.run_dir(tree, name) / "summary.txt"
    assert p.is_file(), (f"run {name!r} wrote no summary.txt at {p} (exit {r.returncode}); "
                         f"runner output:\n{_out(r)[-3000:]}")
    return p.read_text()


def _shard_lines(summary: str) -> dict:
    """`shard id -> its summary line`: lines that carry a shard id and an `exit=`."""
    out: dict = {}
    for ln in summary.splitlines():
        m = _SHARD_ID.search(ln)
        if m and _EXIT.search(ln):
            out.setdefault(m.group(1), ln)
    return out


def _exit_of(line: str) -> int:
    m = _EXIT.search(line)
    assert m, f"no exit=<n> on shard line: {line}"
    return int(m.group(1))


def _holding(lines: dict, relpath: str) -> list:
    return [sid for sid, ln in lines.items() if relpath in ln]


def _records(path: Path) -> list:
    assert path.is_file(), f"{path} was not written"
    return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]


def _target_named(text: str) -> bool:
    return any(v in text for v in {_TARGET, os.path.realpath(_TARGET)})


# ---- AC-12 (stage 4's gate): a live touch fails the run, in every shard --------------------

@pytest.mark.sandbox_probe
@pytest.mark.parametrize("case,filler,tier,test_name", [
    ("case_live_touch", "case_trivial", "unit", "test_touches_a_live_path"),
    ("case_live_touch_child", "case_pass_child", "daemon", "test_child_touches_a_live_path"),
], ids=["in-process", "spawned-child"])
def test_ac12_a_live_touch_fails_its_shard_and_the_run_in_every_shard_position(
        tmp_path, case, filler, tier, test_name):
    """task-29.4 #ac-12: a test that touches a deny-set target without the probe marker fails
    its test, its shard and the run, and `summary.txt` names the test and the target. Run once
    with the probe as the heavier file and once as the lighter, so the deterministic greedy
    placement puts it in each of the two shard positions; the filler's shard passes. The
    outer test is a `sandbox_probe` (its children's touches-log lines are flagged deliberate);
    the inner probe test is not.

    Kills AC-12's mutation (the run's exit code from the last shard only): in the run where the
    probe sits in shard 0, the run exits 0."""
    node = f"tests/test_probe.py::{test_name}"
    positions = set()
    for k, (w_probe, w_fill) in enumerate(((30.0, 10.0), (10.0, 30.0))):
        tree = sht.build(tmp_path / f"p{k}", {"test_probe.py": case, "test_fill.py": filler},
                         weights={"tests/test_probe.py": w_probe, "tests/test_fill.py": w_fill})
        name = f"ac12p{k}{tier}"
        r = _ptest(tree, "--tier", tier, "--shards", "2", "--name", name)
        summary = _summary(tree, name, r)
        lines = {s: ln for s, ln in _shard_lines(summary).items() if s.startswith(tier + "-")}
        assert len(lines) == 2, f"expected 2 {tier} shard lines in summary.txt:\n{summary}"
        hold = _holding(lines, "tests/test_probe.py")
        assert len(hold) == 1, f"the probe file is in {hold}, not exactly one shard:\n{summary}"
        assert _exit_of(lines[hold[0]]) != 0, f"the probe's shard {hold[0]} exited 0:\n{summary}"
        for sid, ln in lines.items():
            if sid != hold[0]:
                assert _exit_of(ln) == 0, f"the filler's shard {sid} failed:\n{summary}"
        assert r.returncode != 0, (
            f"a live touch in shard {hold[0]} did not fail the run (exit 0):\n{_out(r)[-2000:]}")
        assert node in summary, f"summary.txt does not name the test {node}:\n{summary}"
        assert _target_named(summary), f"summary.txt does not name the target {_TARGET}:\n{summary}"
        positions.add(int(hold[0].rsplit("-", 1)[1]))
    assert positions == {0, 1}, f"the probe never ran in every shard position: {positions}"


@pytest.mark.sandbox_probe
def test_ac12_a_live_touch_in_the_serial_group_fails_the_run(tmp_path):
    """task-29.4 #ac-12, the serial group: a file named in `tiering.SERIAL_GROUP` runs as one
    extra shard after the others, and a live touch there fails the run like any other shard."""
    tree = sht.build(
        tmp_path, {"test_probe.py": "case_live_touch", "test_fill_a.py": "case_trivial",
                   "test_fill_b.py": "case_trivial"},
        weights={"tests/test_probe.py": 5.0, "tests/test_fill_a.py": 20.0,
                 "tests/test_fill_b.py": 10.0},
        tiering_extra='SERIAL_GROUP["tests/test_probe.py"] = '
                      '"fixture: AC-12, a live touch in the serial group"')
    r = _ptest(tree, "--tier", "unit", "--shards", "2", "--name", "ac12-serial")
    summary = _summary(tree, "ac12-serial", r)
    lines = _shard_lines(summary)
    serial = [s for s in lines if s.startswith("serial")]
    assert len(serial) == 1, f"no single serial-group line in summary.txt:\n{summary}"
    assert "tests/test_probe.py" in lines[serial[0]], f"the probe is not in the serial group:\n{summary}"
    assert [s for s in _holding(lines, "tests/test_probe.py") if not s.startswith("serial")] == [], \
        f"a serial-group file also ran in a sharded process:\n{summary}"
    assert _exit_of(lines[serial[0]]) != 0, f"the serial group exited 0:\n{summary}"
    assert r.returncode != 0, f"a live touch in the serial group did not fail the run:\n{_out(r)[-2000:]}"
    assert "tests/test_probe.py::test_touches_a_live_path" in summary
    assert _target_named(summary), f"summary.txt does not name the target {_TARGET}:\n{summary}"


# ---- AC-2: the runner's logs are the evidence ----------------------------------------------

_AC2_CASES = {
    "test_pass.py": "case_trivial",
    "test_fail.py": "case_fail",
    "test_teardown.py": "case_teardown_error",
    "test_skip.py": "case_skip_unpinned",
    "test_child.py": "case_pass_child",
    "test_devtree.py": "case_trivial",
}
_AC2_WEIGHTS = {"tests/test_pass.py": 4.0, "tests/test_fail.py": 3.0,
                "tests/test_teardown.py": 2.0, "tests/test_child.py": 5.0,
                "tests/test_devtree.py": 1.0}           # test_skip.py has no weight, on purpose
_DEVTREE_EXTRA = 'DEVTREE_FILES["tests/test_devtree.py"] = "fixture: a devtree-tier file"'


def test_ac2_tier_all_in_a_clone_logs_every_shard_and_fails_when_any_shard_fails(tmp_path):
    """task-29.4 #ac-2 and #r2: `--tier all` in a clone. One log per shard; `summary.txt` has
    an exit code and a distinct sandbox root for every shard, each root also in its own log;
    every file runs in exactly one shard; a failing, a teardown-erroring and an unpinned-skip
    file each fail their shard and so the run; `failures.jsonl` records each by phase; the
    devtree tier is NOT RUN, said verbatim, and the last line says the run is incomplete.

    Kills mutation 3 (exit 0 although shards failed) and 4 ("all green" with tier (c) not run)."""
    tree = sht.build(tmp_path, _AC2_CASES, weights=_AC2_WEIGHTS, tiering_extra=_DEVTREE_EXTRA)
    r = _ptest(tree, "--tier", "all", "--shards", "2", "--name", "ac2")
    out = _out(r)
    summary = _summary(tree, "ac2", r)
    lines = _shard_lines(summary)
    rd = sht.run_dir(tree, "ac2")

    assert r.returncode != 0, f"shards failed but the run exited 0:\n{out[-2000:]}"
    assert len([s for s in lines if s.startswith("unit-")]) == 2, f"not 2 unit shards:\n{summary}"
    assert not [s for s in lines if s.startswith("devtree")], f"tier (c) ran in a clone:\n{summary}"
    for sid in lines:
        if not sid.startswith("serial"):
            assert (rd / f"{sid}.log").is_file(), f"no log for shard {sid} in {rd}"
    roots = {}
    for sid, ln in lines.items():
        m = _ROOT.search(ln)
        assert m, f"shard {sid} has no root= on its summary line: {ln}"
        roots[sid] = m.group(1)
        assert m.group(1) in (rd / f"{sid}.log").read_text(), \
            f"shard {sid}'s root {m.group(1)} is not in its own log"
    assert len(set(roots.values())) == len(roots), f"two shards share a sandbox root: {roots}"
    for name in ("test_pass.py", "test_fail.py", "test_teardown.py", "test_skip.py",
                 "test_child.py"):
        assert len(_holding(lines, f"tests/{name}")) == 1, f"{name} not in exactly one shard"
    assert _holding(lines, "tests/test_devtree.py") == []
    for bad in ("test_fail.py", "test_teardown.py", "test_skip.py"):
        sid = _holding(lines, f"tests/{bad}")[0]
        assert _exit_of(lines[sid]) != 0, f"{bad}'s shard {sid} exited 0:\n{summary}"
    child = _holding(lines, "tests/test_child.py")[0]
    assert child.startswith("daemon-"), f"test_child.py ran in {child}, not a daemon shard"
    assert _exit_of(lines[child]) == 0, f"the passing daemon shard failed:\n{summary}"
    for name in ("test_pass.py", "test_fail.py", "test_teardown.py", "test_skip.py"):
        assert _holding(lines, f"tests/{name}")[0].startswith("unit-"), f"{name} not in a unit shard"
    assert any("tests/test_skip.py" in ln and "no weight" in ln
               for ln in (out + "\n" + summary).splitlines()), \
        "the runner did not say that tests/test_skip.py had no weight"

    assert _NOT_RUN in out, f"the clone's NOT RUN line is missing:\n{out[-2000:]}"
    last = summary.rstrip().splitlines()[-1]
    assert "devtree" in last and "incomplete" in last.lower(), f"last line: {last!r}"
    assert "all green" not in (out + summary).lower(), "a run that skipped tier (c) said all green"

    fails = {(x["nodeid"], x["phase"]): x["e"] for x in _records(rd / "failures.jsonl")}
    assert ("tests/test_fail.py::test_fails_plainly", "call") in fails, fails
    assert ("tests/test_teardown.py::test_passes_then_errors_at_teardown", "teardown") in fails, \
        f"a teardown error is not a failures.jsonl record: {fails}"
    assert "teardown broke" in fails[("tests/test_teardown.py::test_passes_then_errors_at_teardown",
                                       "teardown")]
    assert [k for k in fails if k[0] == "tests/test_skip.py::test_skips_unpinned"], \
        f"the SkipGate finding is not a failures.jsonl record: {fails}"
    outcomes = {(x["nodeid"], x["phase"]): x["outcome"] for x in _records(rd / "outcomes.jsonl")}
    assert outcomes.get(("tests/test_pass.py::test_nothing", "call")) == "passed", outcomes
    assert outcomes.get(("tests/test_child.py::test_passes_with_a_child", "call")) == "passed"


def test_tier_all_in_the_owning_checkout_runs_the_devtree_tier(tmp_path):
    """task-29.4 #r2: in the owning checkout (its own `.refmatrix/`, a `.venv-eval` inside it)
    `--tier all` runs tier (c) after the others, prints no NOT RUN line, and does not call
    the run incomplete."""
    tree = sht.build(tmp_path, {"test_pass.py": "case_trivial", "test_devtree.py": "case_trivial"},
                     owning=True, weights={"tests/test_pass.py": 2.0, "tests/test_devtree.py": 1.0},
                     tiering_extra=_DEVTREE_EXTRA)
    r = _ptest(tree, "--tier", "all", "--shards", "2", "--name", "own")
    summary = _summary(tree, "own", r)
    lines = _shard_lines(summary)
    dev = [s for s in _holding(lines, "tests/test_devtree.py") if s.startswith("devtree-")]
    assert dev, f"tier (c) did not run in the owning checkout:\n{summary}"
    assert _exit_of(lines[dev[0]]) == 0
    assert (sht.run_dir(tree, "own") / f"{dev[0]}.log").is_file()
    assert r.returncode == 0, _out(r)[-2000:]
    assert "NOT RUN" not in _out(r)
    assert "incomplete" not in summary.rstrip().splitlines()[-1].lower()


# ---- AC-3: outcomes.jsonl, and --compare in both modes --------------------------------------

_O = "tests/test_outcomes.py::"


def test_ac3_outcomes_jsonl_follows_the_normalisation_table(tmp_path):
    """task-29.4 #r2-outcomes: one record per node and phase, derived from pytest's report by
    the table; a strict XPASS is `failed` in its call phase and is in `failures.jsonl`.

    Kills mutation 24 (no xfailed / xpassed) and 26 (strict XPASS recorded `xpassed`)."""
    tree = sht.build(tmp_path, {"test_outcomes.py": "case_outcomes"},
                     weights={"tests/test_outcomes.py": 1.0})
    r = _ptest(tree, "--tier", "unit", "--shards", "1", "--name", "outc")
    rd = sht.run_dir(tree, "outc")
    recs = _records(rd / "outcomes.jsonl")
    keys = [(x["nodeid"], x["phase"]) for x in recs]
    assert len(keys) == len(set(keys)), f"a node/phase was recorded twice: {keys}"
    got = {(x["nodeid"], x["phase"]): x["outcome"] for x in recs}
    want = {
        (_O + "test_passes", "setup"): "passed",
        (_O + "test_passes", "call"): "passed",
        (_O + "test_passes", "teardown"): "passed",
        (_O + "test_skips", "call"): "skipped",
        (_O + "test_strict_xfail_that_fails", "call"): "xfailed",
        (_O + "test_nonstrict_xfail_that_passes", "call"): "xpassed",
        (_O + "test_strict_xfail_that_passes", "call"): "failed",
        (_O + "test_fails", "call"): "failed",
        (_O + "test_errors_at_teardown", "call"): "passed",
        (_O + "test_errors_at_teardown", "teardown"): "error",
    }
    wrong = {k: (got.get(k), v) for k, v in want.items() if got.get(k) != v}
    assert not wrong, f"(got, want) per node/phase: {wrong}\nall records: {got}"
    for node in {k[0] for k in want}:
        assert (node, "setup") in got and (node, "teardown") in got, f"{node}: phases {got}"
    fails = {(x["nodeid"], x["phase"]) for x in _records(rd / "failures.jsonl")}
    assert (_O + "test_strict_xfail_that_passes", "call") in fails, fails
    assert (_O + "test_fails", "call") in fails
    assert (_O + "test_errors_at_teardown", "teardown") in fails
    assert (_O + "test_strict_xfail_that_fails", "call") not in fails
    assert (_O + "test_nonstrict_xfail_that_passes", "call") not in fails
    assert r.returncode != 0


def _ptest_module():
    assert _PTEST_PY.is_file(), "scripts/ptest.py does not exist (task-29.4 #r2: the logic is Python)"
    spec = importlib.util.spec_from_file_location("rmx_ptest_under_test", _PTEST_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("a,b", [
    ("FileNotFoundError: /private/tmp/rmx-a1b2c3d4/r/3/.refmatrix/rmxd.sock",
     "FileNotFoundError: /private/tmp/rmx-z9y8x7w6/r/3/.refmatrix/rmxd.sock"),
    ("JSONDecodeError in /tmp/tmpk3j2h1g0/x.json", "JSONDecodeError in /tmp/tmp0a9s8d7f/x.json"),
    ("daemon pid=12345 did not answer", "daemon pid=678 did not answer"),
    ("<Daemon object at 0x10a3b4c50>", "<Daemon object at 0x7f00deadbeef>"),
    ("AssertionError: stop took 10.05s", "AssertionError: stop took 9.02s"),
], ids=["sandbox-root", "tmp-segment", "pid", "hex-address", "seconds"])
def test_normalise_e_line_replaces_only_run_noise(a, b):
    """task-29.4 #r2: sandbox roots, /tmp random segments, pids, hex addresses and decimal
    seconds become placeholders."""
    norm = _ptest_module().normalise_e_line
    assert norm(a) == norm(b), (norm(a), norm(b))


@pytest.mark.parametrize("a,b", [
    ("AssertionError: expected foo", "AssertionError: expected bar"),
    ("KeyError: 'alpha'", "KeyError: 'beta'"),
    ("assert 3 == 4", "assert 3 == 5"),
    ("FileNotFoundError: /private/tmp/rmx-a1b2c3d4/r/3/.refmatrix/rmxd.sock",
     "FileNotFoundError: /private/tmp/rmx-a1b2c3d4/r/3/.refmatrix/rmxd.pid"),
], ids=["word", "quoted-key", "plain-int", "path-tail"])
def test_normalise_e_line_keeps_what_tells_errors_apart(a, b):
    """...and nothing else (kills mutation 6: words replaced, different errors equal)."""
    norm = _ptest_module().normalise_e_line
    assert norm(a) != norm(b), (norm(a), norm(b))


def _run_with(root: Path, name: str, failures=None, outcomes=None) -> Path:
    d = root / name
    d.mkdir(parents=True)
    if failures is not None:
        (d / "failures.jsonl").write_text("".join(json.dumps(x) + "\n" for x in failures))
    if outcomes is not None:
        (d / "outcomes.jsonl").write_text("".join(json.dumps(x) + "\n" for x in outcomes))
    return d


def _compare_tree(tmp_path) -> Path:
    return sht.build(tmp_path, {})


_FAIL_A = {"nodeid": "tests/test_a.py::test_x", "phase": "call",
           "e": "E   FileNotFoundError: /private/tmp/rmx-a1b2c3d4/r/1/.refmatrix/rmxd.sock "
                "(pid=4242) after 1.25s"}


def test_ac3_compare_failures_equal_apart_from_run_noise(tmp_path):
    """task-29.4 #ac-3, failures: runs differing only in a sandbox path, a pid and a duration
    compare equal."""
    tree = _compare_tree(tmp_path)
    b = dict(_FAIL_A, e="E   FileNotFoundError: /private/tmp/rmx-qq77ww88/r/1/.refmatrix/rmxd.sock "
                        "(pid=31) after 12.5s")
    da = _run_with(tmp_path / "runs", "A", failures=[_FAIL_A])
    db = _run_with(tmp_path / "runs", "B", failures=[b])
    r = _ptest(tree, "--compare", str(da), str(db))
    assert r.returncode == 0, _out(r)[-2000:]


@pytest.mark.parametrize("change,named", [
    ({"e": "E   FileNotFoundError: /private/tmp/rmx-a1b2c3d4/r/1/.refmatrix/rmxd.pid "
           "(pid=4242) after 1.25s"}, "tests/test_a.py::test_x"),
    ({"nodeid": "tests/test_a.py::test_y"}, "tests/test_a.py::test_y"),
    ({"phase": "teardown"}, "teardown"),
], ids=["e-line", "node-id", "phase"])
def test_ac3_compare_failures_unequal_names_the_difference(tmp_path, change, named):
    """task-29.4 #ac-3, failures: one E line, one node id or one phase apart compares unequal
    and the output names it (kills mutation 5: the phase ignored)."""
    tree = _compare_tree(tmp_path)
    da = _run_with(tmp_path / "runs", "A", failures=[_FAIL_A])
    db = _run_with(tmp_path / "runs", "B", failures=[dict(_FAIL_A, **change)])
    r = _ptest(tree, "--compare", str(da), str(db))
    assert r.returncode != 0, f"runs that differ compared equal:\n{_out(r)[-2000:]}"
    assert named in _out(r), f"the output does not name {named!r}:\n{_out(r)[-2000:]}"


_P = "tests/test_o.py::"
_COLON = _P + "test_param[a:b]"


def _outcomes(**over) -> list:
    """Three nodes x three phases; `over` maps 'n<k>_<phase>' to an outcome, or to None to drop
    the record."""
    nodes = {"n1": _P + "test_one", "n2": _P + "test_xf", "n3": _COLON}
    base = {"n1": {"setup": "passed", "call": "passed", "teardown": "passed"},
            "n2": {"setup": "passed", "call": "xfailed", "teardown": "passed"},
            "n3": {"setup": "passed", "call": "passed", "teardown": "passed"}}
    out = []
    for n, phases in base.items():
        for ph, oc in phases.items():
            oc = over.get(f"{n}_{ph}", oc)
            if oc is not None:
                out.append({"nodeid": nodes[n], "phase": ph, "outcome": oc})
    return out


_XF_EXPECT = _P + "test_xf:call:xfailed->passed"


@pytest.mark.parametrize("a_over,b_over,expects,ok,named", [
    ({}, {}, [], True, None),
    ({}, {"n2_call": "passed"}, [], False, "test_xf"),
    ({}, {"n2_call": "passed"}, [_XF_EXPECT], True, None),
    ({}, {"n2_call": "passed", "n1_call": "failed"}, [_XF_EXPECT], False, "test_one"),
    ({}, {}, [_XF_EXPECT], False, "test_xf"),
    ({"n2_call": "failed"}, {"n2_call": "passed"}, [_XF_EXPECT], False, "test_xf"),
    ({}, {"n2_call": "passed", "n2_teardown": "error"}, [_XF_EXPECT], False, "teardown"),
    ({}, {"n2_call": "passed"}, [_P + "test_xf:setup:xfailed->passed"], False, "test_xf"),
    ({}, {"n3_setup": None, "n3_call": None, "n3_teardown": None}, [], False, "test_param"),
    ({}, {"n1_teardown": None}, [], False, "test_one"),
    ({}, {"n3_call": "xfailed"}, [_COLON + ":call:passed->xfailed"], True, None),
], ids=["equal", "xfail-to-pass-unexpected", "xfail-to-pass-expected", "second-change",
        "expected-change-absent", "from-was-not-xfailed", "same-node-other-phase-changed",
        "expect-wrong-phase", "node-missing-from-b", "phase-missing-from-b",
        "node-id-with-a-colon"])
def test_ac3_compare_outcomes_is_exact(tmp_path, a_over, b_over, expects, ok, named):
    """task-29.4 #ac-3, outcomes: equal runs are equal; every change of outcome, phase by
    phase, fails unless an `--expect` names exactly that node, phase, from and to; a node or a
    phase present in one run only fails; an `--expect` is parsed from the right (a node id may
    hold a colon).

    Kills mutation 25 (a missing node ignored) and 27 (`--expect` ignores its phase)."""
    tree = _compare_tree(tmp_path)
    da = _run_with(tmp_path / "runs", "A", outcomes=_outcomes(**a_over))
    db = _run_with(tmp_path / "runs", "B", outcomes=_outcomes(**b_over))
    args = ["--compare", "--outcomes", str(da), str(db)]
    for e in expects:
        args += ["--expect", e]
    r = _ptest(tree, *args)
    if ok:
        assert r.returncode == 0, _out(r)[-2000:]
    else:
        assert r.returncode != 0, f"compared equal but should not:\n{_out(r)[-2000:]}"
        assert named in _out(r), f"the output does not name {named!r}:\n{_out(r)[-2000:]}"


# ---- AC-9: the merge gate runs on the owning checkout -----------------------------------------

_CLEAR_LISTS = "ALWAYS_FILES.clear()\nDEVTREE_FILES.clear()\nSERIAL_GROUP.clear()"


def _git_env() -> dict:
    return dict(os.environ, GIT_AUTHOR_NAME="rmx test", GIT_AUTHOR_EMAIL="rmx-test@invalid",
                GIT_COMMITTER_NAME="rmx test", GIT_COMMITTER_EMAIL="rmx-test@invalid",
                GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")


def _git(tree: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(tree), *args], capture_output=True, text=True,
                       env=_git_env(), timeout=60)
    assert r.returncode == 0, f"git {' '.join(args)}: {r.stderr}"
    return r.stdout.strip()


def _merging_checkout(tmp_path, case: str, *, owning=True, lint_exit=0) -> "tuple[Path, str]":
    """A git checkout with `tests/test_ok.py` on `master`, a branch `topic` that adds
    `tests/test_topic.py` (`case`), and `git merge --no-commit --no-ff topic` in progress:
    the state `--merge-gate` runs in (task-29.4 #r7). Returns (tree, MERGE_HEAD)."""
    tree = sht.build(tmp_path, {"test_ok.py": "case_trivial"}, owning=owning,
                     weights={"tests/test_ok.py": 1.0, "tests/test_topic.py": 1.0},
                     tiering_extra=_CLEAR_LISTS, lint_exit=lint_exit)
    (tree / ".gitignore").write_text(".refmatrix/\n.venv-eval\nworkflow/review-output/\n"
                                     "__pycache__/\n")
    _git(tree, "init", "-q", "-b", "master")
    _git(tree, "add", "-A")
    _git(tree, "commit", "-q", "-m", "base")
    _git(tree, "checkout", "-q", "-b", "topic")
    shutil.copy2(sht.CASES / f"{case}.py", tree / "tests" / "test_topic.py")
    _git(tree, "add", "tests/test_topic.py")
    _git(tree, "commit", "-q", "-m", "topic")
    _git(tree, "checkout", "-q", "master")
    _git(tree, "merge", "--no-commit", "--no-ff", "topic")
    return tree, _git(tree, "rev-parse", "MERGE_HEAD")


def _gate_dir(tree: Path, merge_head: str) -> "Path | None":
    for d in (tree / "workflow" / "review-output").glob("merge-gate-*"):
        sha = d.name[len("merge-gate-"):]
        if len(sha) >= 7 and merge_head.startswith(sha):
            return d
    return None


@pytest.mark.parametrize("shape,why", [
    ("no-refmatrix", ".refmatrix"),
    ("venv-outside", ".venv-eval"),
], ids=["no-refmatrix", "venv-resolves-outside"])
def test_ac9_merge_gate_refuses_a_checkout_that_is_not_the_owning_one(tmp_path, shape, why):
    """task-29.4 #r7 item 1 / #ac-9: exit 2, saying why, in a checkout with no `.refmatrix/`
    or whose `.venv-eval` resolves outside it (a littlebig clone's is a symlink to the dev
    tree's)."""
    tree, _ = _merging_checkout(tmp_path, "case_trivial", owning=True)
    if shape == "no-refmatrix":
        (tree / ".refmatrix").rmdir()
    else:
        (tree / ".venv-eval").rmdir()
        (tree / ".venv-eval").symlink_to(Path(sys.prefix).resolve())
    r = _ptest(tree, "--merge-gate")
    assert r.returncode == 2, f"exit {r.returncode}, not 2:\n{_out(r)[-2000:]}"
    assert why in _out(r), f"the refusal does not say why ({why!r}):\n{_out(r)[-2000:]}"


@pytest.mark.parametrize("case,lint_exit,ok,named", [
    ("case_teardown_error", 0, False,
     "tests/test_topic.py::test_passes_then_errors_at_teardown"),
    ("case_trivial", 0, True, None),
    ("case_trivial", 1, False, "lint"),
], ids=["teardown-error", "clean", "lint-gate-fails"])
def test_ac9_merge_gate_runs_the_touched_tests_and_the_lint_gate(tmp_path, case, lint_exit, ok,
                                                                  named):
    """task-29.4 #r7 items 2-4 / #ac-9: in the owning checkout, mid-merge, the gate runs the
    test files the merge touches and the lint gate; a test that passes and errors at teardown
    (bug-230's shape) fails it, named; a non-zero lint gate fails it; the run's logs are in
    `workflow/review-output/merge-gate-<merge head sha>/`.

    Kills mutation 15 (teardown errors ignored)."""
    tree, merge_head = _merging_checkout(tmp_path, case, lint_exit=lint_exit)
    r = _ptest(tree, "--merge-gate")
    gate = _gate_dir(tree, merge_head)
    assert gate is not None and (gate / "summary.txt").is_file(), \
        f"no merge-gate-{merge_head[:12]}…/summary.txt:\n{_out(r)[-2000:]}"
    text = _out(r) + (gate / "summary.txt").read_text()
    assert "tests/test_topic.py" in text, "the gate did not run the file the merge touches"
    if ok:
        assert r.returncode == 0, _out(r)[-2000:]
    else:
        assert r.returncode != 0, f"the merge gate passed:\n{_out(r)[-2000:]}"
        assert named in text, f"the gate's output does not name {named!r}:\n{text[-2000:]}"
