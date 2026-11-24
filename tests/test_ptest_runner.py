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
`xpassed`), 27 (`--expect` ignores its phase), and bsd-294a r1's MX1 (the merge gate never
reads the previous gate: a failure open in the last passed, merged gate is then NEW).

bsd-294a r1's fold (ruling L197, 2026-11-24) adds: b-1 / bug-304 (the merge gate's baseline is
only a gate that PASSED and whose merge head is an ancestor of HEAD, never a moved-aside
`merge-gate-<sha>.<ts>` copy), m-1 (a single-threaded hang says no process snapshot was taken),
m-2 (the refusal checks pytest-timeout is LOADED, not only importable), m-3 (`--help` says
`--shards` is per tier) and m-4 (the /tmp rule replaces only random segments).
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

def _ptest(tree: Path, *args: str, env_extra: "dict | None" = None
           ) -> "subprocess.CompletedProcess":
    script = tree / "scripts" / "ptest.sh"
    assert script.is_file(), f"no runner at {script} (task-29.4 #r2: scripts/ptest.sh)"
    env = dict(os.environ, RMX_PYTEST_PY=sys.executable, **(env_extra or {}))
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
    ("FileNotFoundError: /private/tmp/tmpab_12xyz/x.json",
     "FileNotFoundError: /private/tmp/tmp9q8w_7e6/x.json"),
    ("OSError: /tmp/tmpk3j2h1g0", "OSError: /tmp/tmp0a9s8d7f"),
    ("FileNotFoundError: /var/folders/xy/ab12cd34/T/tmpk3j2h1g0/x.json",
     "FileNotFoundError: /var/folders/qr/zz99yy88/T/tmp0a9s8d7f/x.json"),
], ids=["sandbox-root", "tmp-segment", "pid", "hex-address", "seconds",
        "private-tmp-segment", "tmp-segment-at-line-end", "tmpdir-segment"])
def test_normalise_e_line_replaces_only_run_noise(a, b):
    """task-29.4 #r2: sandbox roots, /tmp random segments, pids, hex addresses and decimal
    seconds become placeholders. A random segment is mkdtemp's shape (`tmp` and 8 characters
    of `[a-z0-9_]`, the whole path component), under /tmp, /private/tmp or the per-user temp
    dir (bsd-294a r1 m-4 keeps these merging while named fixtures stay apart)."""
    norm = _ptest_module().normalise_e_line
    assert norm(a) == norm(b), (norm(a), norm(b))


@pytest.mark.parametrize("a,b", [
    ("AssertionError: expected foo", "AssertionError: expected bar"),
    ("KeyError: 'alpha'", "KeyError: 'beta'"),
    ("assert 3 == 4", "assert 3 == 5"),
    ("FileNotFoundError: /private/tmp/rmx-a1b2c3d4/r/3/.refmatrix/rmxd.sock",
     "FileNotFoundError: /private/tmp/rmx-a1b2c3d4/r/3/.refmatrix/rmxd.pid"),
    ("FileNotFoundError: /tmp/fixture_alpha", "FileNotFoundError: /tmp/fixture_bravo"),
    ("FileNotFoundError: /private/tmp/fixture_alpha/x.json",
     "FileNotFoundError: /private/tmp/fixture_bravo/x.json"),
], ids=["word", "quoted-key", "plain-int", "path-tail", "named-tmp-fixture",
        "named-private-tmp-fixture"])
def test_normalise_e_line_keeps_what_tells_errors_apart(a, b):
    """...and nothing else (kills mutation 6: words replaced, different errors equal).

    bsd-294a r1 m-4 (ruling L197): a NAMED first-level /tmp path is not a random segment.
    At 1bb14a5b the rule ate the tail of any name 8+ characters long, so `/tmp/fixture_alpha`
    and `/tmp/fixture_bravo` both became `/tmp/fixtu<RAND>`, and the merge gate would read a
    different failure as `seen`."""
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


# ---- bug-304 (bsd-294a r1 b-1, ruling L197): the merge gate's baseline -------------------------
#
# #r7: "a row that is still open is recorded as seen, and a new node id or a new E line fails
# the gate". At 1bb14a5b the baseline was "the newest earlier merge-gate-* run with a summary":
# a FAILED gate, and the `merge-gate-<sha>.<ts>` copy `make_run_dir` moves aside on a re-run,
# both qualified. So a failed gate passed when run again, and a different merge carrying the
# same failure inherited it. The baseline is only a gate that PASSED and whose merge head is an
# ancestor of HEAD (it was merged), never a moved-aside copy.

_FAILING_NODE = "tests/test_topic.py::test_fails_plainly"
_PREV_RX = re.compile(r"^# previous gate: (.*)$", re.MULTILINE)


def _gate(tree: Path) -> "tuple[subprocess.CompletedProcess, str]":
    """One `--merge-gate` run on the merge in progress: (result, that run's summary.txt)."""
    merge_head = _git(tree, "rev-parse", "MERGE_HEAD")
    r = _ptest(tree, "--merge-gate")
    gate = _gate_dir(tree, merge_head)
    assert gate is not None and (gate / "summary.txt").is_file(), \
        f"no merge-gate-{merge_head[:12]}…/summary.txt (exit {r.returncode}):\n{_out(r)[-2000:]}"
    return r, (gate / "summary.txt").read_text()


def _start_merge(tree: Path, branch: str, files: dict) -> str:
    """From `master`, a branch `branch` adding `files` (`tests/test_*.py` name -> case stem),
    then `git merge --no-commit --no-ff branch` on `master`. Returns MERGE_HEAD."""
    _git(tree, "checkout", "-q", "-b", branch, "master")
    for name, case in files.items():
        shutil.copy2(sht.CASES / f"{case}.py", tree / "tests" / name)
        _git(tree, "add", f"tests/{name}")
    _git(tree, "commit", "-q", "-m", branch)
    _git(tree, "checkout", "-q", "master")
    _git(tree, "merge", "--no-commit", "--no-ff", branch)
    return _git(tree, "rev-parse", "MERGE_HEAD")


def _passed_merged_gate(tmp_path) -> "tuple[Path, str]":
    """A tree whose `master` holds one merge (`topic`, a clean file) gated and PASSED before its
    merge commit: the one gate a later gate may take as its baseline. Returns (tree, its sha)."""
    tree, m1 = _merging_checkout(tmp_path, "case_trivial")
    r, summary = _gate(tree)
    assert r.returncode == 0, f"the clean merge's gate failed:\n{summary}"
    _git(tree, "commit", "-q", "-m", "merge topic")
    return tree, m1


def _previous_gate_line(summary: str) -> str:
    m = _PREV_RX.search(summary)
    assert m, f"summary.txt has no '# previous gate:' line:\n{summary}"
    return m.group(1)


def test_merge_gate_a_failed_gate_run_again_on_the_same_merge_still_fails(tmp_path):
    """bug-304 (b-1, P1): a merge adds a failing test; the gate fails with it NEW. Run again on
    the same merge, the gate must fail again. At 1bb14a5b the second run took the first run's
    moved-aside copy as its baseline, read the failure as `seen` and exited 0."""
    tree, _ = _merging_checkout(tmp_path, "case_fail")
    r1, s1 = _gate(tree)
    assert r1.returncode == 1, f"run 1: exit {r1.returncode}, not 1:\n{s1}"
    assert f"NEW FAILED {_FAILING_NODE}" in s1, s1
    r2, s2 = _gate(tree)
    assert r2.returncode == 1, (f"run 2 of a failed gate on the same merge exited "
                                f"{r2.returncode}, not 1 (bug-304):\n{s2}")
    assert f"NEW FAILED {_FAILING_NODE}" in s2, f"run 2 does not call the failure NEW:\n{s2}"


def test_merge_gate_a_different_merge_carrying_a_failure_from_a_failed_gate_fails(tmp_path):
    """bug-304 (b-1, P1's second half): the gate fails on merge `topic`; the merge is aborted;
    a DIFFERENT merge (`topic2`, another commit) carries the same failing test. Its gate must
    fail: the failed gate was never a baseline. At 1bb14a5b it exited 0."""
    tree, m1 = _merging_checkout(tmp_path, "case_fail")
    r1, s1 = _gate(tree)
    assert r1.returncode == 1, s1
    _git(tree, "merge", "--abort")
    m2 = _start_merge(tree, "topic2", {"test_topic.py": "case_fail",
                                       "test_other.py": "case_trivial"})
    assert m2 != m1
    r2, s2 = _gate(tree)
    assert r2.returncode == 1, (f"a second merge carrying a failure first seen in a FAILED gate "
                                f"exited {r2.returncode}, not 1 (bug-304):\n{s2}")
    assert f"NEW FAILED {_FAILING_NODE}" in s2, s2


def test_merge_gate_baseline_is_the_last_passed_merged_gate_never_a_moved_aside_copy(tmp_path):
    """bug-304 (b-1), the baseline itself, read from the summary's `# previous gate:` line.
    `master` holds merge `topic`, gated and passed (M1). Then merge `topic2` adds a failing
    test and is gated twice; the second run moves the first aside to
    `merge-gate-<sha>.<ts>`. Both runs fail, and both name M1's gate dir as the baseline:
    never the failed run, never the moved-aside copy, never a gate of an unmerged head. At
    1bb14a5b run 2 named the moved-aside copy and passed."""
    tree, m1 = _passed_merged_gate(tmp_path)
    m1_dir = re.compile(rf"merge-gate-{m1}(?![.\w])")
    m2 = _start_merge(tree, "topic2", {"test_t2.py": "case_fail"})
    for k in (1, 2):
        r, summary = _gate(tree)
        prev = _previous_gate_line(summary)
        assert m1_dir.search(prev) and prev.count("merge-gate-") == 1, (
            f"run {k}: the baseline is {prev!r}, not the passed, merged gate merge-gate-{m1}")
        assert f"merge-gate-{m2}" not in prev, f"run {k} took its own merge's gate: {prev!r}"
        assert r.returncode == 1, f"run {k}: exit {r.returncode}, not 1 (bug-304):\n{summary}"
        assert "NEW FAILED tests/test_t2.py::test_fails_plainly" in summary, summary
    asides = [d.name for d in (tree / "workflow" / "review-output").glob(f"merge-gate-{m2}.*")]
    assert len(asides) == 1, f"run 2 did not move run 1 aside: {asides}"


def test_merge_gate_carries_a_failure_open_in_the_last_passed_merged_gate_and_names_it(tmp_path):
    """#r7 / L194, the carry-over that must survive the bug-304 fix: a failure recorded in the
    last PASSED, merged gate's `failures.jsonl` is still open, so a later gate records it as
    `seen`, names it, and passes. Kills MX1 (the gate never reads the previous gate: the open
    failure is then NEW and the gate fails).

    Set-up: M1 (clean) is gated, passes and is merged. Merge `topic2` adds a failing test and
    its first gate fails (NEW), which gives the real record. A passed gate holds a failure
    only when it was carried into it, and a fresh tree has no such gate, so the record is
    written into M1's `failures.jsonl`: the state a passed gate that carried it leaves. The
    re-run on `topic2` then has M1 as its baseline and passes. RED at 1bb14a5b only on its last
    assertion (the baseline named is run 1's moved-aside copy)."""
    tree, m1 = _passed_merged_gate(tmp_path)
    _start_merge(tree, "topic2", {"test_t2.py": "case_fail"})
    r1, s1 = _gate(tree)
    assert r1.returncode == 1, s1
    node = "tests/test_t2.py::test_fails_plainly"
    merge_head = _git(tree, "rev-parse", "MERGE_HEAD")
    recs = [x for x in _records(_gate_dir(tree, merge_head) / "failures.jsonl")
            if x["nodeid"] == node]
    assert len(recs) == 1, recs
    m1_gate = _gate_dir(tree, m1)
    with open(m1_gate / "failures.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps({k: recs[0][k] for k in ("nodeid", "phase", "e")}) + "\n")
    r2, s2 = _gate(tree)
    # MX1's assertion first: it holds at 1bb14a5b (whose baseline is the moved-aside copy,
    # which also holds the record), so the mutation is seen dying here, not on the line below
    assert re.search(rf"\bseen\b[^\n]*FAILED {re.escape(node)}", s2), \
        f"the carried failure is not named as seen (MX1's shape):\n{s2}"
    assert r2.returncode == 0, (f"a failure open in the last passed, merged gate failed the "
                                f"gate (exit {r2.returncode}):\n{s2}")
    prev = _previous_gate_line(s2)
    assert re.search(rf"merge-gate-{m1}(?![.\w])", prev) and prev.count("merge-gate-") == 1, \
        f"the baseline is {prev!r}, not the passed, merged gate merge-gate-{m1} (bug-304)"


# ---- ruling L192 (6) and (3): the hang guard's plugin, and the default shard count ----------

_NO_TIMEOUT_STUB = (
    '"""A stand-in that makes `import pytest_timeout` fail (test_ptest_runner.py, L192 (6))."""\n'
    'raise ImportError("fixture: pytest-timeout is not installed for this interpreter")\n')


def test_the_runner_refuses_an_interpreter_without_pytest_timeout(tmp_path):
    """Ruling L192 (6): the hang guard (`#r2`, `timeout = 600`) is a config key that pytest only
    WARNS about when the plugin is missing, so a run without pytest-timeout would have no hang
    guard and say nothing. `ptest.py` refuses instead: exit 2, a line naming pytest-timeout, and
    no shard started.

    The interpreter at `$RMX_PYTEST_PY` is a shim over this one that puts a stub
    `pytest_timeout` module first on `PYTHONPATH`, so `import pytest_timeout` raises while
    pytest itself still imports. No real venv is touched."""
    stub = tmp_path / "no_timeout"
    stub.mkdir()
    (stub / "pytest_timeout.py").write_text(_NO_TIMEOUT_STUB)
    shim = tmp_path / "python-no-timeout"
    shim.write_text(f'#!/bin/bash\nexport PYTHONPATH="{stub}${{PYTHONPATH:+:$PYTHONPATH}}"\n'
                    f'exec "{sys.executable}" "$@"\n')
    shim.chmod(0o755)
    probe = subprocess.run([str(shim), "-c", "import pytest; import pytest_timeout"],
                           capture_output=True, text=True, timeout=60)
    assert probe.returncode != 0 and "fixture: pytest-timeout" in probe.stderr, \
        f"the shim does not hide pytest-timeout: {probe.stderr[-500:]}"
    tree = sht.build(tmp_path, {"test_pass.py": "case_trivial"},
                     weights={"tests/test_pass.py": 1.0})
    env = dict(os.environ, RMX_PYTEST_PY=str(shim))
    r = subprocess.run(["bash", str(tree / "scripts" / "ptest.sh"), "--tier", "unit",
                        "--shards", "1", "--name", "notimeout"], cwd=str(tree), env=env,
                       capture_output=True, text=True, timeout=_RUN_HANG_GUARD_S)
    out = _out(r)
    assert r.returncode == 2, f"exit {r.returncode}, not 2:\n{out[-2000:]}"
    assert [ln for ln in out.splitlines() if "pytest-timeout" in ln], \
        f"no line names pytest-timeout:\n{out[-2000:]}"
    assert not list(sht.run_dir(tree, "notimeout").glob("unit-*.log")), \
        "a shard ran although the hang guard's plugin is missing"


def test_with_no_shards_flag_the_shard_count_is_the_cpu_derived_default(tmp_path):
    """Ruling L192 (3): with no `--shards`, a tier is split into `ptest.default_shards()`
    processes, derived from `os.cpu_count()`. The count is read from the runner's own function,
    never hard-coded, and the tier gets one equal-weight file per shard so every shard has
    work and appears in `summary.txt`."""
    n = _ptest_module().default_shards()
    assert isinstance(n, int) and 1 <= n <= (os.cpu_count() or 1), n
    cases = {f"test_s{i:02d}.py": "case_trivial" for i in range(n)}
    tree = sht.build(tmp_path, cases, weights={f"tests/{k}": 1.0 for k in cases})
    r = _ptest(tree, "--tier", "unit", "--name", "dflt")
    summary = _summary(tree, "dflt", r)
    units = [s for s in _shard_lines(summary) if s.startswith("unit-")]
    assert len(units) == n, f"{len(units)} unit shards, default_shards() = {n}:\n{summary}"
    assert r.returncode == 0, _out(r)[-2000:]


# ---- bsd-294a r1 m-1, m-2, m-3 (ruling L197) ---------------------------------------------------

def test_a_single_threaded_hang_says_no_process_snapshot_was_taken(tmp_path):
    """bsd-294a r1 m-1 (ruling L197): a test that hangs in its main thread fails on
    pytest-timeout (2 s, the fixture's own test-sized budget), but the `signal` method prints
    no `+++ Timeout +++` banner, so the runner's watcher takes no process snapshot. That is
    accepted (L194); a SILENT absence is not: the shard's summary line either names the
    `<shard>.ps.txt` it wrote or says `no process snapshot`. At 1bb14a5b it said neither."""
    tree = sht.build(tmp_path, {"test_hang.py": "case_hang_main_thread"},
                     weights={"tests/test_hang.py": 1.0})
    r = _ptest(tree, "--tier", "unit", "--shards", "1", "--name", "hang")
    summary = _summary(tree, "hang", r)
    rd = sht.run_dir(tree, "hang")
    assert r.returncode == 1, f"exit {r.returncode}, not 1:\n{_out(r)[-2000:]}"
    fails = [x for x in _records(rd / "failures.jsonl")
             if x["nodeid"] == "tests/test_hang.py::test_hangs_in_its_main_thread"]
    assert fails and "Timeout" in fails[0]["e"], f"no timeout record: {fails}"
    line = _shard_lines(summary).get("unit-0")
    assert line, f"no unit-0 line:\n{summary}"
    snaps = sorted(p.name for p in rd.glob("*.ps.txt"))
    if snaps:
        assert any(n in line for n in snaps), f"{snaps} written but not named:\n{line}"
    else:
        assert "no process snapshot" in line.lower(), (
            f"a timeout with no process snapshot is not said on the shard line:\n{line}")


@pytest.mark.parametrize("addopts,refused", [
    ("", True),
    ("-p pytest_timeout", False),
], ids=["autoload-off-refused", "autoload-off-plugin-named-runs"])
def test_the_runner_refuses_when_pytest_timeout_is_importable_but_not_loaded(tmp_path, addopts,
                                                                             refused):
    """bsd-294a r1 m-2 (ruling L197): with `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` inherited,
    `import pytest_timeout` still succeeds but pytest does not LOAD the plugin, the
    `timeout = 600` key is only an unknown-option warning, and a hung test hangs the run. The
    runner refuses (exit 2, a line naming pytest-timeout, no shard started). The control: the
    same environment with the plugin named on `PYTEST_ADDOPTS` (`-p pytest_timeout`) is guarded,
    so the runner runs it. At 1bb14a5b the first case ran unguarded and exited 0."""
    tree = sht.build(tmp_path, {"test_pass.py": "case_trivial"},
                     weights={"tests/test_pass.py": 1.0})
    r = _ptest(tree, "--tier", "unit", "--shards", "1", "--name", "noload",
               env_extra={"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "PYTEST_ADDOPTS": addopts})
    out = _out(r)
    shard_logs = list(sht.run_dir(tree, "noload").glob("unit-*.log"))
    if refused:
        assert r.returncode == 2, f"exit {r.returncode}, not 2:\n{out[-2000:]}"
        assert [ln for ln in out.splitlines() if "pytest-timeout" in ln], \
            f"no line names pytest-timeout:\n{out[-2000:]}"
        assert not shard_logs, "a shard ran although pytest-timeout is not loaded"
    else:
        assert r.returncode == 0, f"a guarded run was refused or failed:\n{out[-2000:]}"
        assert shard_logs, "no shard ran"


def test_help_says_shards_is_per_tier(tmp_path):
    """bsd-294a r1 m-3 (ruling L197; L194 accepted `--shards N` per tier "said in `--help`"):
    the `--shards` entry of `ptest.sh --help` says the count is per tier. At 1bb14a5b the
    option had no help text."""
    tree = sht.build(tmp_path, {})
    r = _ptest(tree, "--help")
    assert r.returncode == 0, _out(r)[-2000:]
    lines = r.stdout.splitlines()
    starts = [i for i, ln in enumerate(lines) if ln.lstrip().startswith("--shards")]
    assert starts, f"--help lists no --shards:\n{r.stdout}"
    block = [lines[starts[0]]]
    for ln in lines[starts[0] + 1:]:
        if ln.lstrip().startswith("-") or not ln.strip():
            break
        block.append(ln)
    text = " ".join(" ".join(block).split())
    assert re.search(r"\bper (?:sharded )?tier\b", text, re.IGNORECASE), \
        f"the --shards help does not say it is per tier: {text!r}"
