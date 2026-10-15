"""Task 23.0, ch-bsd r1 remedy (2026-10-15): the refusal holes and silent passes the first audit
found (workflow/bullshit/2026-10-15-0543-task23-0-sandbox-r1-ccdefef.md).

- b1: the bug-127 fd-walk exemption skipped every relative path raised from `shutil.py`, so a
  relative `shutil.copyfile` / `copy2` / `move` / `rmtree` of a denied store went through with
  no refusal and no touches line. Pinned in BOTH directions.
- b2: a skip is a test that stopped running; the session now fails on an unpinned skip.
- s1: a child's refusal (exit 86) is invisible when its spawner ignores the exit code.
- s2: a violation recorded under a key no report hook pops was dropped at session end.
- s3: R4's spawn-hook propagation had no test (mutation MA survived).
- s5: AC-4's `/pytest-of-` marker fired on live doc ingestion that QUOTES such a path.
- s6: `launchctl` and `os.kill` reached live processes unaudited.
- m1: "`RMX_SANDBOX_DENY_EXTRA` can only ADD" was unpinned (mutation MF survived).
- m4: a spawn's `cwd` inside a denied root was not checked.
- m5: no in-process way to expect a violation.

SAFETY. No test here can touch a live path even with its fix mutated away: every "live" target
is a name that does NOT exist inside the protected `.refmatrix/` (a refused read; unrefused, a
FileNotFoundError), a DECOY store the test builds and adds to a child's deny set, a launchd
label that does not exist, or a sleeper process the test itself started. `kill -1` and
`os.kill(-1, ...)` are pinned on the pure rule only, never executed. Each test calls
`_require_sandbox()` first.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

import rmx_sandbox  # on sys.path via tests/conftest.py (tests/sandbox_site)

pytest_plugins = ["pytester"]

_REPO = Path(__file__).resolve().parents[1]


def _require_sandbox() -> Path:
    root = os.environ.get("RMX_SANDBOX_ROOT")
    assert root and Path(root).is_dir(), "no sandbox; refusing to run a refusal probe"
    return Path(root)


def _absent_live_name() -> str:
    """A path INSIDE the protected `~/.refmatrix/` that does not exist: refused, it is a
    SandboxViolation; unrefused (a mutated sandbox), a FileNotFoundError -- never a change."""
    return os.path.join(os.environ["RMX_SANDBOX_REAL_HOME"], ".refmatrix",
                        f"sbx-absent-{uuid.uuid4().hex}")


def _py(code: str, cwd=None, env=None, timeout=60) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                          cwd=cwd, env=env if env is not None else dict(os.environ),
                          timeout=timeout)


def _decoy_store(base: Path) -> Path:
    """A decoy `<base>/.refmatrix/` holding a 'catalog' and a `queries/` dir. The child is
    told to deny it through `RMX_SANDBOX_DENY_EXTRA` (additive only)."""
    store = base / ".refmatrix"
    (store / "queries").mkdir(parents=True)
    (store / "catalog.read.duckdb").write_text("secret")
    (store / "queries" / "q.json").write_text("{}")
    return store


# ---- b1: the fd-walk exemption, both directions -------------------------------------------


@pytest.mark.sandbox_probe
@pytest.mark.parametrize("op", [
    'shutil.copyfile(".refmatrix/catalog.read.duckdb", "stolen")',
    'shutil.copy2(".refmatrix/catalog.read.duckdb", "stolen")',
    'shutil.move(".refmatrix/catalog.read.duckdb", "stolen")',
    'shutil.rmtree(".refmatrix/queries")',
    'shutil.copytree(".refmatrix", "stolen")',
], ids=["copyfile", "copy2", "move", "rmtree", "copytree"])
def test_relative_shutil_on_a_denied_store_is_refused(tmp_path, op):
    """b1: from the store's parent as cwd (the repo cwd is the main tree's default), a
    relative `shutil` op on the denied store exits CHILD_EXIT and changes nothing."""
    _require_sandbox()
    work = tmp_path / "w"
    store = _decoy_store(work)
    env = dict(os.environ, RMX_SANDBOX_DENY_EXTRA=str(store))
    r = _py(f"import shutil\n{op}\nprint('DONE')\n", cwd=str(work), env=env)
    assert r.returncode == rmx_sandbox.CHILD_EXIT, (r.returncode, r.stdout, r.stderr[-2000:])
    assert "SandboxViolation" in r.stderr and "DONE" not in r.stdout
    assert not (work / "stolen").exists(), "the denied store's content was copied out"
    assert (store / "catalog.read.duckdb").read_text() == "secret"
    assert (store / "queries" / "q.json").is_file()


def test_the_sandboxs_own_rmtree_from_a_stores_parent_is_not_refused(tmp_path):
    """b1, the other direction: `remove_tree` of an UNdenied tree whose walk opens a
    `.refmatrix` entry by bare name (fd-relative) with the cwd beside a DENIED `.refmatrix`
    succeeds. This is the 2026-10-15 GREEN-run false positive the exemption exists for."""
    _require_sandbox()
    work = tmp_path / "w"
    store = _decoy_store(work)
    other = tmp_path / "other"
    (other / ".refmatrix" / "sub").mkdir(parents=True)
    (other / ".refmatrix" / "sub" / "f").write_text("x")
    env = dict(os.environ, RMX_SANDBOX_DENY_EXTRA=str(store))
    code = ("import sys\nfrom pathlib import Path\nimport rmx_sandbox\n"
            f"rmx_sandbox.remove_tree(Path({str(other)!r}))\nprint('REMOVED')\n")
    r = _py(code, cwd=str(work), env=env)
    assert r.returncode == 0 and "REMOVED" in r.stdout, (r.returncode, r.stderr[-2000:])
    assert not other.exists(), "the cleanup left the tree behind"
    assert (store / "catalog.read.duckdb").read_text() == "secret"


def test_the_exemption_is_named_by_function_not_by_file():
    """b1: the pure rule. A bare name from the fd walk is exempt; a name with a separator, or
    any `shutil.*` event, is never exempt."""
    deny = {"paths": [os.path.abspath(".refmatrix")], "ports": [], "pids": []}
    assert rmx_sandbox.violation("open", (".refmatrix", None, 0), deny, fd_walk=True) is None
    assert rmx_sandbox.violation("os.remove", (".refmatrix", 3), deny, fd_walk=True) is None
    assert rmx_sandbox.violation("open", (".refmatrix/x", None, 0), deny, fd_walk=True)
    assert rmx_sandbox.violation("shutil.rmtree", (".refmatrix", None), deny, fd_walk=True)
    assert rmx_sandbox.violation("shutil.copyfile", (".refmatrix", "y"), deny, fd_walk=True)
    assert rmx_sandbox.violation("open", (".refmatrix", None, 0), deny, fd_walk=False)


# ---- b2: the skip gate --------------------------------------------------------------------


def test_an_unpinned_skip_fails_the_session_and_a_pinned_one_does_not(pytester):
    """b2: `SkipGate` (the conftest registers it with `ALLOWED_SKIPS`) fails the session on a
    skip it does not name, and accepts the one it does."""
    _require_sandbox()
    pytester.makepyfile(test_inner_skips='''
import pytest

def test_pinned():
    pytest.skip("named in the pinned list")

def test_silent():
    pytest.skip("a HOME-derived condition turned true")

def test_runs():
    assert True
''')
    gate = rmx_sandbox.SkipGate({"test_inner_skips.py::test_pinned": "why"})
    result = pytester.runpytest("-p", "no:cacheprovider", plugins=[gate])
    out = result.stdout.str()
    assert result.ret == pytest.ExitCode.TESTS_FAILED, out[-3000:]
    assert "SKIPPED-UNPINNED test_inner_skips.py::test_silent" in out, out[-3000:]
    assert "test_pinned:" not in out.split("SkipGate:")[-1], out[-3000:]

    ok = rmx_sandbox.SkipGate({"test_inner_skips.py::test_pinned": "why",
                               "test_inner_skips.py::test_silent": "why"})
    assert pytester.runpytest("-p", "no:cacheprovider", plugins=[ok]).ret == 0


def test_the_conftest_registers_the_skip_gate(pytestconfig):
    """b2: the gate is ON for this session, with the conftest's pinned list."""
    gate = pytestconfig.pluginmanager.get_plugin("rmx_skip_gate")
    assert isinstance(gate, rmx_sandbox.SkipGate), gate


# ---- s1: a child's refusal fails its test even when the spawner ignores the exit ---------


class _ConftestHooks:
    """Carries THIS checkout's conftest hooks (the function objects pytest registered, so a
    mutation of the conftest is what runs) into an in-process inner session. Registered in
    workflow/test_mock_registry.md as a non-mock carrier."""


def _conftest_hooks(config, *names) -> _ConftestHooks:
    want = (_REPO / "tests" / "conftest.py").resolve()
    for plugin in config.pluginmanager.get_plugins():
        f = getattr(plugin, "__file__", None)
        if f and Path(f).resolve() == want:
            carrier = _ConftestHooks()
            for n in names:
                setattr(carrier, n, getattr(plugin, n))
            return carrier
    raise AssertionError(f"{want} is not a registered plugin of this session")


@pytest.mark.sandbox_probe
def test_a_child_refusal_with_an_ignored_exit_code_fails_its_test(pytester, pytestconfig):
    """s1: the inner test spawns a child that is refused (exit 86) and IGNORES the code
    (`check=False`), as a best-effort hook would. With the conftest's protocol + report
    hooks, the inner test FAILS and names the child's touches line; the clean control passes.
    The child's line is OWNED by this outer probe (AC-4 accepts it), and the inner test, which
    is not its owner, is still failed by it."""
    _require_sandbox()
    absent = _absent_live_name()
    pytester.makepyfile(test_inner_child=f'''
import os, subprocess, sys

def test_ignores_the_child_exit():
    subprocess.run([sys.executable, "-c", "open({absent!r})"], capture_output=True,
                   check=False)

def test_clean_control():
    subprocess.run([sys.executable, "-c", "pass"], check=True)
''')
    hooks = _conftest_hooks(pytestconfig, "pytest_runtest_protocol",
                            "pytest_runtest_makereport")
    result = pytester.runpytest("-p", "no:cacheprovider", "-rf", "-vv", plugins=[hooks])
    reports = {r.nodeid.rsplit("::", 1)[-1]: r
               for r in result.reprec.getreports("pytest_runtest_logreport")
               if r.when == "teardown"}
    out = result.stdout.str()
    assert reports["test_clean_control"].passed, out[-3000:]
    bad = reports["test_ignores_the_child_exit"]
    assert bad.failed, f"a child's refusal passed unseen\n{out[-3000:]}"
    assert "SandboxViolation in a child process" in str(bad.longrepr), bad.longrepr
    assert absent in str(bad.longrepr), bad.longrepr


def test_child_touches_reads_only_unflagged_lines_from_other_pids(tmp_path):
    """s1: the pure reader. Own-pid lines are the record's job; flagged lines are probes."""
    log = tmp_path / "touches.log"
    me = os.getpid()
    log.write_text("".join([
        f"{me}\tt::a\tt::a\topen\t/x\t-\n",            # own pid: the record's job
        f"{me + 1}\tt::a\tt::a\topen\t/x\tt::a\n",     # t::a's own deliberate probe
        f"{me + 1}\tt::a\tt::a\topen\t/own\tt::o\n",   # owned by ANOTHER (outer) probe
        f"{me + 1}\tt::b\tt::b\topen\t/x\t-\n",        # another test
        f"{me + 1}\tt::a\tt::a\topen\t/hit\t-\n",      # THE one
        f"{me + 1}\tinner::x\tt::a\topen\t/hit2\n",    # an old 5-field line, outer = t::a
    ]))
    got = rmx_sandbox.child_touches(str(log), 0, "t::a", me)
    assert [ln.split("\t")[4] for ln in got] == ["/own", "/hit", "/hit2"], got


# ---- s2: every leftover record fails the session -----------------------------------------


@pytest.mark.sandbox_probe
@pytest.mark.parametrize("leg", ["inner-key", "no-test"])
def test_a_leftover_record_fails_the_session(pytester, pytestconfig, leg):
    """s2: a swallowed violation recorded under a key no report hook pops -- an inner test's
    own id (no report hook in that session), or `<no-test>` (`PYTEST_CURRENT_TEST` unset, as
    for a thread between tests) -- fails the session through the conftest's
    `pytest_sessionfinish`. Mutation MC (the exit-status line -> `pass`) and the pre-remedy
    `NO_TEST`-only pop each fail one leg."""
    _require_sandbox()
    absent = _absent_live_name()
    unset = 'monkeypatch.delenv("PYTEST_CURRENT_TEST")' if leg == "no-test" else "pass"
    pytester.makepyfile(test_inner_left=f'''
def test_swallows(monkeypatch):
    {unset}
    try:
        open({absent!r})
    except Exception:
        pass
''')
    hooks = _conftest_hooks(pytestconfig, "pytest_sessionfinish")
    try:
        result = pytester.runpytest("-p", "no:cacheprovider", plugins=[hooks])
    finally:
        left = rmx_sandbox.drain_record()
    out = result.stdout.str()
    assert result.ret == pytest.ExitCode.TESTS_FAILED, out[-3000:]
    assert "SandboxViolation outside any reported test" in out, out[-3000:]
    assert absent in out, out[-3000:]
    assert not left, f"the session hook left records behind: {left}"


# ---- s3: R4 propagation reaches a child whose env names only PATH -------------------------


@pytest.mark.sandbox_probe
def test_a_child_given_only_path_is_sandboxed_by_the_spawn_hook():
    """s3: `env={"PATH": ...}` -- no PYTHONPATH, no HOME, no RMX_SANDBOX_ROOT. The spawn hook
    adds the sandbox: the child's read inside the protected `.refmatrix/` exits CHILD_EXIT,
    and a second child's `Path.home()` is under the sandbox root. Mutation MA
    (`_SPAWN_EVENTS = {}`) leaves the child unguarded: FileNotFoundError, and the live home."""
    root = _require_sandbox()
    deny = json.loads((root / rmx_sandbox.DENY_FILE).read_text())
    before = rmx_sandbox.touches_size(deny)
    bare = {"PATH": os.environ["PATH"]}
    target = _absent_live_name()
    r = _py(f"open({target!r})", env=dict(bare))
    assert r.returncode == rmx_sandbox.CHILD_EXIT, (r.returncode, r.stderr[-2000:])
    assert "SandboxViolation" in r.stderr
    # ... and the refusal is attributed to THIS test (the child-touch check reads by test id).
    me = os.environ["PYTEST_CURRENT_TEST"].rsplit(" (", 1)[0]
    mine = [ln for ln in rmx_sandbox.touches_since(deny["touches"], before) if target in ln]
    assert mine and mine[0].split("\t")[1] == me, mine
    h = _py("from pathlib import Path; print(Path.home())", env=dict(bare))
    assert h.returncode == 0, h.stderr[-2000:]
    assert Path(h.stdout.strip()).resolve().is_relative_to(root.resolve()), h.stdout


# ---- m1: the extra deny set only adds -----------------------------------------------------


@pytest.mark.sandbox_probe
def test_a_deny_extra_does_not_drop_the_live_deny_set(tmp_path):
    """m1: a child given `RMX_SANDBOX_DENY_EXTRA` still refuses the protected home. Mutation
    MF (`paths=sorted(add)`) replaced the deny set with the extra."""
    _require_sandbox()
    extra = tmp_path / "decoy" / ".refmatrix"
    extra.mkdir(parents=True)
    env = dict(os.environ, RMX_SANDBOX_DENY_EXTRA=str(extra))
    r = _py(f"open({_absent_live_name()!r})", env=env)
    assert r.returncode == rmx_sandbox.CHILD_EXIT, (r.returncode, r.stderr[-2000:])
    r2 = _py(f"open({str(extra / 'x')!r}, 'w')", env=env)
    assert r2.returncode == rmx_sandbox.CHILD_EXIT, (r2.returncode, r2.stderr[-2000:])
    assert not (extra / "x").exists()


# ---- m4 + m5: a spawn's cwd, and the in-process expectation ------------------------------


def test_a_spawn_whose_cwd_is_inside_a_denied_root_is_refused():
    """m4: refused BEFORE the fork (the audit event carries the cwd). Unrefused, the cwd does
    not exist and Popen raises FileNotFoundError, which `expect_sandbox_violation` lets
    propagate -- the test fails, nothing is touched."""
    _require_sandbox()
    with rmx_sandbox.expect_sandbox_violation() as got:
        subprocess.run([sys.executable, "-c", "pass"], cwd=_absent_live_name())
    assert any(g.startswith("subprocess.Popen cwd ") for g in got), got


def test_expect_sandbox_violation_consumes_its_record_and_flags_the_line():
    """m5: inside the block a refusal (even a swallowed one) is expected: the test is not
    flipped, the record is empty after, and the touches line carries the probe flag."""
    _require_sandbox()
    deny = rmx_sandbox._STATE["deny"]
    before = rmx_sandbox.touches_size(deny)
    target = _absent_live_name()
    with rmx_sandbox.expect_sandbox_violation() as got:
        try:
            open(target)
        except Exception:
            pass
    assert got and target in got[0], got
    assert rmx_sandbox.current_test() not in rmx_sandbox.RECORD
    lines = [rmx_sandbox.parse_touch(ln)
             for ln in rmx_sandbox.touches_since(deny["touches"], before)]
    mine = [t for t in lines if t and t["target"] == target]
    assert mine and all(t["probe"] for t in mine), mine
    assert os.environ.get(rmx_sandbox.PROBE_ENV) is None, "the probe flag leaked out"


def test_expect_sandbox_violation_fails_when_nothing_is_refused():
    """m5: a block that triggers no refusal is an AssertionError, not a silent pass."""
    _require_sandbox()
    with pytest.raises(AssertionError, match="expected a SandboxViolation"):
        with rmx_sandbox.expect_sandbox_violation():
            pass


# ---- s5: the content check reads PATH fields for the pytest temp marker -------------------


def test_pytest_temp_marker_matches_path_fields_not_quoted_text():
    """s5: the live watcher ingesting a ledger that QUOTES `/pytest-of-` is not a leak; a row
    whose `path` / `cwd` / `root` (any depth) is under pytest's temp dir is."""
    quoted = {"kind": "concept", "op": "entity", "path": "/repo/workflow/bullshit/x.md",
              "tldr": "bug-101 wrote /private/var/folders/q/pytest-of-u/pytest-1/a",
              "meta": {"description": "see /pytest-of-u/"}}
    assert rmx_sandbox.leak_reasons(json.dumps(quoted), "abc123", "facts.log") == []
    for row in ({"op": "link", "path": "/private/var/folders/q/pytest-of-u/p/f.md"},
                {"kind": "grep", "cwd": "/tmp/pytest-of-u/x"},
                {"op": "entity", "meta": {"root": "/tmp/pytest-of-u/r/.refmatrix"}}):
        assert "pytest temp path" in rmx_sandbox.leak_reasons(json.dumps(row), "", "facts.log")
    assert rmx_sandbox.leak_reasons('{"tldr": "x rmx-abc123-y"}', "abc123", "facts.log") == [
        "run tag"]


def test_check_logs_counts_only_unflagged_touches(tmp_path, capsys):
    """m2/s1: the AC-4 touches count excludes lines a probe owns, and nothing else -- no
    module allowlist."""
    t = tmp_path / "touches.log"
    t.write_text("1\ttests/test_sandbox_refusal.py::x\ttests/test_sandbox_refusal.py::x\topen"
                 "\t/a\t-\n"
                 "1\ttests/test_y.py::z\ttests/test_y.py::z\topen\t/b\tprobe\n")
    assert rmx_sandbox.check_logs({}, "", str(t), 0) == 1
    assert "/a" in capsys.readouterr().out
    assert not hasattr(rmx_sandbox, "DELIBERATE_PROBE_MODULES")


# ---- s6: launchctl and kill ---------------------------------------------------------------


def _nonexistent_label() -> str:
    return f"gui/{os.getuid()}/com.refmatrix.sbx-absent-{uuid.uuid4().hex[:12]}"


def test_the_launchctl_shim_is_first_on_the_sandbox_path():
    _require_sandbox()
    import shutil
    assert shutil.which("launchctl") == str(rmx_sandbox.BIN_DIR / "launchctl")


@pytest.mark.sandbox_probe
def test_the_shim_refuses_a_mutating_launchctl_from_a_shell(tmp_path):
    """s6: a SHELL script's `launchctl bootout` (no Python spawn for the audit hook to see)
    meets the shim: exit CHILD_EXIT, SandboxViolation, a touches line. The label does not
    exist, so even an unrefused bootout changes nothing."""
    _require_sandbox()
    deny = rmx_sandbox._STATE["deny"]
    before = rmx_sandbox.touches_size(deny)
    script = tmp_path / "boot.sh"
    script.write_text(f"launchctl bootout {_nonexistent_label()}\n")
    r = subprocess.run(["/bin/sh", str(script)], capture_output=True, text=True, timeout=60)
    assert r.returncode == rmx_sandbox.CHILD_EXIT, (r.returncode, r.stderr[-2000:])
    assert "SandboxViolation" in r.stderr
    lines = rmx_sandbox.touches_since(deny["touches"], before)
    assert any("launchctl bootout" in ln for ln in lines), lines


def test_the_shim_passes_a_read_only_launchctl_through(tmp_path):
    _require_sandbox()
    script = tmp_path / "list.sh"
    script.write_text("launchctl list >/dev/null\n")
    r = subprocess.run(["/bin/sh", str(script)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, (r.returncode, r.stderr[-2000:])
    assert "SandboxViolation" not in r.stderr


def test_a_python_spawn_of_a_mutating_launchctl_is_refused_in_process():
    """s6: refused by the audit hook before the fork, whatever PATH says."""
    _require_sandbox()
    with rmx_sandbox.expect_sandbox_violation() as got:
        subprocess.run(["/bin/launchctl", "bootstrap", f"gui/{os.getuid()}",
                        "/nonexistent/sbx-absent.plist"], capture_output=True)
    assert any("launchctl bootstrap" in g for g in got), got


class _DenyPids:
    """Add pids to THIS process's deny set for one block (the live pids are captured at
    `enter()`; a test may never signal those, so it denies a sleeper it owns instead)."""

    def __init__(self, *pids):
        self.pids = list(pids)

    def __enter__(self):
        self.saved = rmx_sandbox._STATE["deny"]
        rmx_sandbox._STATE["deny"] = dict(self.saved,
                                          pids=list(self.saved.get("pids") or []) + self.pids)

    def __exit__(self, *exc):
        rmx_sandbox._STATE["deny"] = self.saved
        return False


@pytest.fixture
def sleeper():
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    try:
        yield p
    finally:
        p.kill()
        p.wait(timeout=30)


def test_signalling_a_live_pid_is_refused(sleeper):
    """s6: `os.kill` and a spawned `kill` on a deny-set pid are refused; signal 0 (an
    existence probe) is not. The pid is a sleeper this test owns."""
    _require_sandbox()
    with _DenyPids(sleeper.pid):
        os.kill(sleeper.pid, 0)
        with rmx_sandbox.expect_sandbox_violation():
            os.kill(sleeper.pid, signal.SIGTERM)
        with rmx_sandbox.expect_sandbox_violation():
            subprocess.run(["kill", "-TERM", str(sleeper.pid)])
    assert sleeper.poll() is None, "the deny-set pid was signalled"


def test_the_signal_rule_on_every_process_and_groups():
    """s6, pure only (never executed): `-1` is every process; `-pid` is a live pid's group."""
    deny = {"paths": [], "ports": [], "pids": [4242]}
    v = rmx_sandbox.violation
    assert v("os.kill", (-1, 15), deny)
    assert v("os.kill", (-1, 0), deny) is None
    assert v("os.kill", (-4242, 9), deny)
    assert v("os.killpg", (4242, 15), deny)
    assert v("os.kill", (4243, 15), deny) is None
    assert v("subprocess.Popen", ("/bin/sh", ["/bin/sh", "-c", "true; kill -9 -1"], None, None),
             deny)
    assert v("subprocess.Popen", ("kill", ["kill", "-0", "4242"], None, None), deny) is None
    assert v("subprocess.Popen", ("x", ["launchctl", "print", "gui/1"], None, None),
             deny) is None
    assert v("subprocess.Popen", ("x", ["sh", "-c", "X=1 launchctl kickstart -k a"], None,
                                        None), deny)


def test_build_deny_captures_the_live_pids_from_the_real_pid_files(tmp_path, monkeypatch):
    """s6: `enter()`'s deny set names the daemon of every store root and the hub of every
    protected home, read from their pid files. A decoy real home stands in for the account's
    (`_account_home`, the password-database lookup, is the external boundary)."""
    _require_sandbox()
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    other = tmp_path / "other" / ".refmatrix"
    for d in (home / ".refmatrix", repo / ".refmatrix", other, home / "Library" /
              "LaunchAgents"):
        d.mkdir(parents=True)
    (home / ".refmatrix" / "hub.pid").write_text("111\n")
    (home / ".refmatrix" / "rmxd.pid").write_text("222 extra\n")
    (repo / ".refmatrix" / "rmxd.pid").write_text("333\n")
    (other / "rmxd.pid").write_text("not-a-pid\n")
    import plistlib
    (home / "Library" / "LaunchAgents" / "com.refmatrix.daemon.x.plist").write_bytes(
        plistlib.dumps({"EnvironmentVariables": {"REFMATRIX_ROOT": str(other)}}))
    monkeypatch.setattr(rmx_sandbox, "_account_home", lambda: home)
    deny = rmx_sandbox.build_deny(repo, env={"HOME": str(home)})
    assert deny["pids"] == [111, 222, 333], deny["pids"]
    assert any(p.endswith("/other/.refmatrix") for p in deny["paths"]), deny["paths"]


def test_this_sessions_deny_set_carries_a_pid_list():
    """s6: the deny set `enter()` wrote (and every child reads) has the `pids` key."""
    root = _require_sandbox()
    deny = json.loads((root / rmx_sandbox.DENY_FILE).read_text())
    assert isinstance(deny.get("pids"), list), deny.keys()
    assert all(isinstance(p, int) for p in deny["pids"])
