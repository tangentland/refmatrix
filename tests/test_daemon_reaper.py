"""plan-29 task 29.4b (stage 2, with T0.2): bug-229 -- the reaper that fails the session.

WHY. A test daemon outlived its test by 20 hours: pid 89734, `rmx daemon start --no-watch` from
the bug-212 clone, serving `/private/tmp/r1-hcn81cf7/proj/.refmatrix` with its own embed and
rerank workers, found 2026-11-14 while a full suite crawled at load 12-15. Its root was a
`mkdtemp(prefix="r1-", dir="/tmp")`, OUTSIDE the sandbox root, as were 95 other sites, so a
reaper keyed on "sockets under the sandbox root" (the bug row's proposal) would not have seen
it. The run that leaked it was most likely killed before teardown, so a reaper that runs only
at teardown would not have seen it either (task-29.4 `#r4`).

What is pinned here (task-29.4 `#r4`, `#ac-5`; the fixtures are real, nothing is mocked: the
reaper is the thing under test, and a faked process list would test the fake):
- AC-5's six inner sessions, each a CHILD pytest process over one `case_*.py` of
  `tests/fixtures/suite_health/`, copied into a throwaway checkout whose `tests/conftest.py` is
  this checkout's (so the inner session builds its own sandbox, ledger and reaper):
  a leaked daemon on an out-of-sandbox root; a clean one; a reused pid; a run killed with
  SIGKILL mid-test and the next session's orphan sweep; an in-process `Daemon` left serving;
  a SIGSTOPped daemon. Plus `register_spawn`'s own-test failure and its control.
- R4's first sentence on a plain (non-daemon) child: every process the suite starts is known.
- R4 item 1 directly: an exec'd child and a forked grandchild each write one ledger line; a
  fork of the pytest process writes one; `enter()` writes `owner.json`.
- R4 item 9: `sweep_orphans(ledger_path)` is a function others call.

The ledger's line format is the GREEN author's, except that each line is one JSON object with
the process id under the key `pid` (the cases and these tests read nothing else by key; the
other fields are checked by value: parent pid, argv, cwd, `REFMATRIX_ROOT`, test id).

Mutations this file kills (task-29.4 `#test-strategy`): 9 (no ledger after a fork: the
double-forked daemon's pid is not in the LEAKED line), 10 (prints, does not stop: the pid
survives), 11 (stops, does not fail: exit 0), 12 (no start-time check: the unrelated process
is signalled), 13 (no session-start sweep: the orphan survives), 16 (the `Daemon.__init__`
wrapper records nothing: the in-process daemon passes unseen), 17 (a stopped process is
skipped: it survives), 22 (`root=` only from a sandbox pid file: the out-of-sandbox root is
printed `unknown`).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

import rmx_sandbox  # on sys.path via tests/conftest.py (tests/sandbox_site)
from refmatrix import daemon as dm

_REPO = Path(__file__).resolve().parents[1]
_CASES = _REPO / "tests" / "fixtures" / "suite_health"

# Hang guards (not bounds under test): an inner session that starts a real daemon takes
# 10-40 s on an idle machine; one that hangs is killed here and fails on its own message.
_INNER_HANG_GUARD_S = 420.0
_GONE_GRACE_S = 15.0
_INFO_WAIT_S = 180.0

_NODE = "tests/test_case.py::"


# ---- the inner checkout --------------------------------------------------------------------

def _inner_tree(tmp_path: Path, case: str) -> Path:
    """A throwaway checkout: this checkout's test support (conftest, every non-test file at the
    top of tests/, `sandbox_site/`), `tools/pyc_guard.py`, `pyproject.toml`, `src` as a symlink
    to the real `src/`, and ONE case as `tests/test_case.py`. The inner session's `_REPO` is
    this tree, so its sandbox, ledger and leaked-process log are its own."""
    tree = (tmp_path / "inner").resolve()
    tests = tree / "tests"
    tests.mkdir(parents=True)
    for p in (_REPO / "tests").iterdir():
        if p.name in ("__pycache__", "fixtures") or p.name.startswith("test_"):
            continue
        if p.is_dir():
            shutil.copytree(p, tests / p.name, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy2(p, tests / p.name)
    shutil.copy2(_CASES / "support.py", tests / "suite_health_support.py")
    shutil.copy2(_CASES / f"{case}.py", tests / "test_case.py")
    (tree / "tools").mkdir()
    shutil.copy2(_REPO / "tools" / "pyc_guard.py", tree / "tools" / "pyc_guard.py")
    if (_REPO / "pyproject.toml").is_file():
        shutil.copy2(_REPO / "pyproject.toml", tree / "pyproject.toml")
    (tree / "src").symlink_to(_REPO / "src")
    (tree / "workflow" / "review-output").mkdir(parents=True)
    return tree


def _inner_cmd() -> list:
    return [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-rA",
            "tests/test_case.py"]


def _inner_env(info: Path, **extra) -> dict:
    env = dict(os.environ, RMX_CASE_INFO=str(info))
    env.update({k: str(v) for k, v in extra.items()})
    return env


def _run_inner(tree: Path, info: Path, **extra) -> "subprocess.CompletedProcess":
    try:
        return subprocess.run(_inner_cmd(), cwd=str(tree), env=_inner_env(info, **extra),
                              capture_output=True, text=True, timeout=_INNER_HANG_GUARD_S)
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"").decode(errors="replace") if isinstance(e.stdout, bytes) \
            else (e.stdout or "")
        pytest.fail(f"the inner session hung past {_INNER_HANG_GUARD_S} s (hang guard):\n"
                    + out[-3000:])


def _out(r: "subprocess.CompletedProcess") -> str:
    return (r.stdout or "") + (r.stderr or "")


def _info(info: Path) -> dict:
    assert info.is_file(), f"the case never reported what it started ({info} missing)"
    return json.loads(info.read_text())


# ---- processes -----------------------------------------------------------------------------

def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _gone_within(pid: int, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not _alive(pid):
            return True
        time.sleep(0.1)
    return not _alive(pid)


def _cleanup(info: Path) -> None:
    """Stop and remove whatever a case started that the inner session left (at base, all of
    it). Signals only the pid the case reported, and only if it is still that daemon's root
    that answers or the pid is alive."""
    if not info.is_file():
        return
    d = json.loads(info.read_text())
    pid = d.get("pid")
    root = d.get("root")
    if isinstance(pid, int) and pid > 0 and _alive(pid):
        try:
            os.kill(pid, signal.SIGCONT)
        except ProcessLookupError:
            pass
        if root:
            dm.stop_daemon(Path(root), timeout=10)
        if _alive(pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            _gone_within(pid, 5)
    for k in ("base",):
        if d.get(k):
            shutil.rmtree(d[k], ignore_errors=True)


@pytest.fixture
def case_info(tmp_path):
    info = tmp_path / "case-info.json"
    yield info
    _cleanup(info)


def _line_with(out: str, *needles: str) -> "str | None":
    for ln in out.splitlines():
        if all(n in ln for n in needles):
            return ln
    return None


def _root_forms(root: str) -> set:
    p = Path(root)
    return {str(p), str(p.resolve()), os.path.realpath(str(p))}


# ---- AC-5: a leaked daemon fails the session, by name --------------------------------------

def test_ac5_a_leaked_out_of_sandbox_daemon_fails_the_session_by_name(tmp_path, case_info):
    """bug-229's shape: a real daemon on a `mkdtemp(dir="/tmp")` root, never stopped. The one
    inner test PASSES, and the session must still exit with pytest's "tests failed" status,
    print `LEAKED PROCESS` with the daemon's pid, the test id and the store root, and leave no
    process: the pid is gone and the socket does not answer.

    Kills mutation 9 (no fork ledger: the daemon's final pid exists only after its double
    fork, so the LEAKED line would not carry it), 10 (the pid survives), 11 (exit 0) and 22
    (the root is outside the sandbox, so a reaper that reads `root=` from sandbox pid files
    prints `unknown`)."""
    tree = _inner_tree(tmp_path, "case_leak_daemon")
    r = _run_inner(tree, case_info)
    out = _out(r)
    d = _info(case_info)
    pid, root = d["pid"], d["root"]
    assert "1 passed" in out, f"the fixture test itself must pass:\n{out[-3000:]}"
    assert r.returncode == pytest.ExitCode.TESTS_FAILED, (
        f"a daemon (pid {pid}, root {root}) outlived its test and the inner session exited "
        f"{r.returncode}, not {int(pytest.ExitCode.TESTS_FAILED)}: no reaper failed the "
        f"session (bug-229)\n{out[-3000:]}")
    line = _line_with(out, "LEAKED PROCESS", f"pid={pid}")
    assert line is not None, f"no `LEAKED PROCESS pid={pid}` line:\n{out[-3000:]}"
    assert f"{_NODE}test_leaks_a_daemon" in line, (
        f"the LEAKED line does not name the test that spawned it: {line!r}")
    assert any(f"root={form}" in line for form in _root_forms(root)), (
        f"the LEAKED line does not name the store root {root} (out of the sandbox, known only "
        f"from the ledger's REFMATRIX_ROOT): {line!r}")
    assert _gone_within(pid, _GONE_GRACE_S), f"the leaked daemon pid {pid} is still alive"
    assert not dm.ping(Path(root), timeout=0.5, retries=0), (
        f"the leaked daemon's socket under {root} still answers")


def test_ac5_a_daemon_stopped_by_its_test_is_no_leak(tmp_path, case_info):
    """AC-5 fixture 2: a test that stops its daemon properly. The inner session exits 0 and
    prints no `LEAKED` line (no false positive from the launcher, the double fork, or the
    daemon's workers, all of which have exited)."""
    tree = _inner_tree(tmp_path, "case_clean_daemon")
    r = _run_inner(tree, case_info)
    out = _out(r)
    assert r.returncode == 0, f"a clean spawn failed the session (exit {r.returncode}):\n" \
        + out[-3000:]
    assert "LEAKED" not in out, f"a clean spawn was reported as leaked:\n{out[-3000:]}"


def test_ac5_a_reused_pid_is_not_signalled_and_the_line_says_so(tmp_path, case_info):
    """AC-5 fixture 3: a ledger line naming a live, UNRELATED process whose start time is not
    the ledger's. The reaper must not signal it (a reused pid is someone else's process), and
    its line says so. Kills mutation 12 (no start-time check: the process is signalled)."""
    unrelated = subprocess.Popen(["/bin/sleep", "600"])
    try:
        # The start times must differ whatever resolution the ledger uses (`ps -o lstart` is
        # whole seconds): the case's own child starts after the inner session's startup.
        time.sleep(1.5)
        tree = _inner_tree(tmp_path, "case_reused_pid")
        r = _run_inner(tree, case_info, RMX_CASE_TARGET_PID=unrelated.pid)
        out = _out(r)
        assert "no ledger line with pid=" not in out, (
            "the case could not point a ledger line at the unrelated pid: its own child wrote "
            "no line to <sandbox root>/children.jsonl (#r4 item 1)\n" + out[-3000:])
        assert "1 passed" in out, f"the fixture test itself must pass:\n{out[-3000:]}"
        assert unrelated.poll() is None and _alive(unrelated.pid), (
            f"the reaper signalled pid {unrelated.pid}, an unrelated process whose start time "
            f"does not match the ledger's (a reused pid); exit {unrelated.returncode}\n"
            + out[-3000:])
        line = next((ln for ln in out.splitlines()
                     if str(unrelated.pid) in ln and "reused" in ln.lower()), None)
        assert line is not None, (
            f"no line naming pid {unrelated.pid} as a reused pid (task-29.4 #r4 item 2: "
            f"'it is not signalled, and the line says so'):\n{out[-3000:]}")
        assert r.returncode == 0, (
            f"a reused pid is not a leak, but the session exited {r.returncode}:\n"
            + out[-3000:])
    finally:
        unrelated.kill()
        unrelated.wait()


def test_ac5_a_killed_runs_orphan_is_stopped_at_the_next_session_start(tmp_path, case_info):
    """AC-5 fixture 4: a run killed with SIGKILL mid-test never reaches teardown, so no
    session-finish reaper can run (bug-229's most likely cause). The NEXT inner session's start
    finds the killed run's `/tmp/rmx-*/owner.json` (owner no longer running), stops its
    ledger's survivors, prints `ORPHAN from a killed run` with the pid, removes the killed
    run's root, logs the count in `workflow/review-output/leaked-processes.log`, and exits 0
    (plan-29 D13: a killed run's orphan does not fail the new session). Kills mutation 13."""
    tree = _inner_tree(tmp_path, "case_killed_mid_test")
    a = subprocess.Popen(_inner_cmd(), cwd=str(tree), env=_inner_env(case_info),
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    killed_sandbox = None
    try:
        deadline = time.monotonic() + _INFO_WAIT_S
        while not case_info.is_file() and time.monotonic() < deadline and a.poll() is None:
            time.sleep(0.2)
        assert case_info.is_file(), (
            f"the killed-run case never reported its daemon (exit {a.poll()}):\n"
            + (a.stdout.read().decode(errors="replace")[-3000:] if a.poll() is not None
               else "(still running)"))
        d = _info(case_info)
        pid, killed_sandbox = d["pid"], d["sandbox"]
        assert _alive(pid), f"the case's daemon {pid} is not running before the kill"
        a.kill()
        a.wait(timeout=30)
    finally:
        if a.poll() is None:
            a.kill()
            a.wait()
        a.stdout.close()
    assert killed_sandbox and Path(killed_sandbox).is_dir(), (
        f"the killed run's sandbox root {killed_sandbox} should still exist after SIGKILL")

    (tree / "tests" / "test_case.py").write_text(
        (_CASES / "case_trivial.py").read_text())
    try:
        r = _run_inner(tree, tmp_path / "unused-info.json")
        out = _out(r)
        line = _line_with(out, "ORPHAN from a killed run", str(pid))
        assert line is not None, (
            f"the next session's start printed no `ORPHAN from a killed run` line for pid "
            f"{pid} (left by a run killed with SIGKILL):\n{out[-3000:]}")
        assert _gone_within(pid, _GONE_GRACE_S), (
            f"the killed run's orphan daemon {pid} is still alive after the next session")
        assert r.returncode == 0, (
            f"a killed run's orphan must not fail the new session (plan-29 D13), exit "
            f"{r.returncode}:\n{out[-3000:]}")
        assert not Path(killed_sandbox).exists(), (
            f"the killed run's sandbox root {killed_sandbox} was not removed")
        log = tree / "workflow" / "review-output" / "leaked-processes.log"
        assert log.is_file() and str(pid) in log.read_text(), (
            f"{log} does not record the orphan {pid}: "
            f"{log.read_text()[-1000:] if log.is_file() else '(missing)'}")
    finally:
        if killed_sandbox and Path(killed_sandbox).exists():
            shutil.rmtree(killed_sandbox, ignore_errors=True)


def test_ac5_an_in_process_daemon_left_serving_fails_the_session(tmp_path, case_info):
    """AC-5 fixture 5: a `Daemon` built and served INSIDE the pytest process is not in the
    spawn ledger. conftest's weak registry of `Daemon` instances finds it still serving; it is
    printed `LEAKED IN-PROCESS DAEMON root=<…> built in <test id>`, stopped, and the session
    fails. Kills mutation 16 (the `Daemon.__init__` wrapper records nothing)."""
    tree = _inner_tree(tmp_path, "case_inprocess_daemon")
    r = _run_inner(tree, case_info)
    out = _out(r)
    d = _info(case_info)
    root = d["root"]
    assert "1 passed" in out, f"the fixture test itself must pass:\n{out[-3000:]}"
    assert r.returncode == pytest.ExitCode.TESTS_FAILED, (
        f"an in-process daemon on {root} was left serving and the session exited "
        f"{r.returncode}:\n{out[-3000:]}")
    line = _line_with(out, "LEAKED IN-PROCESS DAEMON")
    assert line is not None, f"no `LEAKED IN-PROCESS DAEMON` line:\n{out[-3000:]}"
    assert any(f"root={form}" in line for form in _root_forms(root)), (
        f"the line does not name the daemon's root {root}: {line!r}")
    assert f"{_NODE}test_leaves_an_in_process_daemon_serving" in line, (
        f"the line does not name the test that built it: {line!r}")


def test_ac5_a_sigstopped_daemon_is_continued_stopped_and_fails_the_session(tmp_path,
                                                                           case_info):
    """AC-5 fixture 6 (`#r4` item 8): a daemon left SIGSTOPped is still a leak. It is sent
    SIGCONT, stopped, reported like any other, and the session fails. Kills mutation 17."""
    tree = _inner_tree(tmp_path, "case_sigstopped_daemon")
    r = _run_inner(tree, case_info)
    out = _out(r)
    d = _info(case_info)
    pid = d["pid"]
    assert "1 passed" in out, f"the fixture test itself must pass:\n{out[-3000:]}"
    assert r.returncode == pytest.ExitCode.TESTS_FAILED, (
        f"a SIGSTOPped daemon (pid {pid}) was left and the session exited {r.returncode}:\n"
        + out[-3000:])
    assert _line_with(out, "LEAKED PROCESS", f"pid={pid}") is not None, (
        f"no `LEAKED PROCESS pid={pid}` line for the stopped daemon:\n{out[-3000:]}")
    assert _gone_within(pid, _GONE_GRACE_S), (
        f"the SIGSTOPped daemon {pid} is still alive after the session")


def test_r4_a_leaked_plain_child_is_stopped_even_though_its_ledger_names_a_root(tmp_path,
                                                                                case_info):
    """`#r4`'s first sentence: EVERY process the suite starts is known. A plain Python child
    (not a daemon) left running: its ledger line carries the per-test `REFMATRIX_ROOT` the
    sandbox gives every child, and no daemon serves that root, so `stop_daemon(root)` alone
    stops nothing. The pid must still be stopped, reported, and fail the session."""
    tree = _inner_tree(tmp_path, "case_leak_plain_child")
    r = _run_inner(tree, case_info)
    out = _out(r)
    pid = _info(case_info)["pid"]
    try:
        assert r.returncode == pytest.ExitCode.TESTS_FAILED, (
            f"an abandoned child (pid {pid}) outlived its test and the session exited "
            f"{r.returncode}:\n{out[-3000:]}")
        assert _line_with(out, "LEAKED PROCESS", f"pid={pid}") is not None, (
            f"no `LEAKED PROCESS pid={pid}` line:\n{out[-3000:]}")
        assert _gone_within(pid, _GONE_GRACE_S), (
            f"the abandoned child {pid} is still alive: a ledger root was taken to mean the "
            "pid is that root's daemon")
    finally:
        if _alive(pid):
            os.kill(pid, signal.SIGKILL)


# ---- AC-5 last sentence: register_spawn ------------------------------------------------------

def test_ac5_a_registered_spawn_its_fixture_does_not_stop_fails_its_own_test(tmp_path,
                                                                             case_info):
    """A fixture registered through `rmx_sandbox.register_spawn` whose teardown does not stop
    its daemon fails ITS OWN test, by name, before the session ends (`#r4` item 7: a
    registered entry's teardown asserts the stop answered and the pid exited). The test that
    runs after it is untouched."""
    tree = _inner_tree(tmp_path, "case_register_spawn_unstopped")
    r = _run_inner(tree, case_info)
    out = _out(r)
    pid = _info(case_info)["pid"]
    own = f"{_NODE}test_uses_the_owned_daemon"
    assert "ERROR at setup of test_uses_the_owned_daemon" not in out, (
        "the fixture could not register its daemon through rmx_sandbox.register_spawn(pid, "
        "root, why) (#r4 item 7), so the test errored at setup, not at the teardown that "
        "must catch the unstopped spawn:\n" + out[-3000:])
    hit = re.search(rf"^(ERROR|FAILED) {re.escape(own)}\b.*$", out, re.M)
    assert hit is not None, (
        f"{own} registered pid {pid} through register_spawn and its fixture never stopped it, "
        f"but the test did not fail by name:\n{out[-3000:]}")
    assert re.search(rf"^PASSED {re.escape(_NODE)}test_runs_after\b", out, re.M), (
        f"the next test must be untouched:\n{out[-3000:]}")
    assert str(pid) in out.split("short test summary")[0], (
        f"the failure does not name the registered pid {pid}:\n{out[-3000:]}")
    assert r.returncode == pytest.ExitCode.TESTS_FAILED, out[-3000:]
    assert _gone_within(pid, _GONE_GRACE_S), f"the registered daemon {pid} survived the run"


def test_ac5_a_registered_spawn_its_fixture_stops_passes(tmp_path, case_info):
    """The control: `register_spawn` plus a teardown that stops the daemon passes, exit 0, no
    `LEAKED` line."""
    tree = _inner_tree(tmp_path, "case_register_spawn_stopped")
    r = _run_inner(tree, case_info)
    out = _out(r)
    assert "ERROR at setup of test_uses_the_owned_daemon" not in out, (
        "the fixture could not register its daemon through rmx_sandbox.register_spawn(pid, "
        "root, why) (#r4 item 7):\n" + out[-3000:])
    assert r.returncode == 0, (
        f"a registered spawn that its fixture stopped failed the session (exit "
        f"{r.returncode}):\n{out[-3000:]}")
    assert "LEAKED" not in out, out[-3000:]


# ---- R4 item 1: the ledger, directly ---------------------------------------------------------

def _ledger() -> Path:
    return Path(os.environ["RMX_SANDBOX_ROOT"]) / "children.jsonl"


def _records(pid: int) -> list:
    led = _ledger()
    if not led.is_file():
        return []
    out = []
    for ln in led.read_text().splitlines():
        try:
            rec = json.loads(ln)
        except ValueError:
            continue
        if isinstance(rec, dict) and rec.get("pid") == pid:
            out.append(rec)
    return out


def _values(rec: dict) -> list:
    return list(rec.values())


_FORK_CHILD = r"""
import os, sys
pid = os.fork()
if pid == 0:
    os._exit(0)
os.waitpid(pid, 0)
print(os.getpid(), pid)
"""


def test_r4_an_exec_child_and_its_forked_grandchild_each_write_one_ledger_line(request):
    """`#r4` item 1: every Python process that starts under the sandbox appends ONE line to
    `<sandbox root>/children.jsonl`; `install_from_env()` writes the exec'd child's, and the
    `os.register_at_fork(after_in_child=…)` callback it registers writes the fork's (a daemon
    double-forks with no exec, so its final pid is only visible there). The line carries the
    pid, the parent pid, the argv, the cwd, the child's `REFMATRIX_ROOT` and the test id."""
    cwd = Path(tempfile.mkdtemp(prefix="led-", dir=os.environ["RMX_SANDBOX_ROOT"])).resolve()
    root = str(cwd / "store" / ".refmatrix")
    env = dict(os.environ, REFMATRIX_ROOT=root)
    r = subprocess.run([sys.executable, "-c", _FORK_CHILD], cwd=str(cwd), env=env,
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    child, grandchild = (int(x) for x in r.stdout.split())
    recs = _records(child)
    assert len(recs) == 1, (
        f"expected exactly one ledger line for the exec'd child {child} in {_ledger()}, got "
        f"{len(recs)}: {recs!r}")
    rec = recs[0]
    vals = _values(rec)
    assert os.getpid() in vals, f"the child's parent pid {os.getpid()} is not in {rec!r}"
    assert any(isinstance(v, list) and "-c" in v for v in vals), f"no argv in {rec!r}"
    assert str(cwd) in vals, f"the working directory {cwd} is not in {rec!r}"
    assert root in vals, f"the child's REFMATRIX_ROOT {root} is not in {rec!r}"
    assert any(isinstance(v, str) and request.node.nodeid in v for v in vals), (
        f"the test id {request.node.nodeid} is not in {rec!r}")
    grec = _records(grandchild)
    assert len(grec) == 1, (
        f"expected exactly one ledger line for the forked grandchild {grandchild} (the "
        f"at-fork hook), got {len(grec)}: {grec!r}")
    assert child in _values(grec[0]), f"the grandchild's parent pid {child} is not in {grec!r}"


def test_r4_a_fork_of_the_pytest_process_writes_a_ledger_line():
    """`#r4` item 1: `enter()` registers the at-fork callback in the pytest process too (an
    in-process `spawn_daemon` forks from here)."""
    pid = os.fork()
    if pid == 0:
        os._exit(0)
    os.waitpid(pid, 0)
    assert len(_records(pid)) == 1, (
        f"no single ledger line for pid {pid}, forked from the pytest process ({_ledger()})")


def test_r4_enter_writes_owner_json_naming_this_process():
    """`#r4` item 3: `enter()` writes `owner.json` (pid and start time), which the next
    session's start reads to tell a killed run's sandbox from a live one."""
    owner = Path(os.environ["RMX_SANDBOX_ROOT"]) / "owner.json"
    assert owner.is_file(), f"no {owner}: a killed run's sandbox cannot be told from a live one"
    rec = json.loads(owner.read_text())
    assert rec.get("pid") == os.getpid(), rec
    assert len(rec) >= 2, f"owner.json must carry the owner's start time too: {rec!r}"


# ---- R4 item 9: sweep_orphans is a function others call -------------------------------------

def test_r4_sweep_orphans_stops_the_live_survivors_of_a_ledger(tmp_path):
    """`#r4` item 9: `rmx_sandbox.sweep_orphans(ledger_path)` is item 3's logic as a function
    (28.2's paired-run clone daemons sweep their own ledger with it). Given a ledger holding
    one live process's own line, it stops that process and reports it."""
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
    try:
        deadline = time.monotonic() + 30
        while not _records(child.pid) and time.monotonic() < deadline:
            time.sleep(0.1)
        recs = _records(child.pid)
        assert recs, f"the child {child.pid} wrote no ledger line in {_ledger()}"
        ledger = tmp_path / "children.jsonl"
        ledger.write_text(json.dumps(recs[0]) + "\n")
        sweep = getattr(rmx_sandbox, "sweep_orphans", None)
        assert callable(sweep), "rmx_sandbox has no sweep_orphans(ledger_path) (#r4 item 9)"
        sweep(ledger)
        try:
            child.wait(timeout=_GONE_GRACE_S)      # our own child: reaped here, not a zombie
        except subprocess.TimeoutExpired:
            pass
        assert child.poll() is not None, (
            f"sweep_orphans({ledger}) left the live survivor {child.pid} running")
    finally:
        if child.poll() is None:
            child.kill()
        child.wait()
