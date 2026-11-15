"""Task T0.3 R3.1, R3.3, R3.4 and AC-3.2's M3.1, M3.3, M3.4 (`task-t0-suite-trust-sweep#t0-3`):
every load flake explains itself.

Each forced-failure node runs ONE flaky test in a child pytest with a tiny plugin
(`t03_force`, written to tmp and loaded with `-p`) that forces the failure the flake shows under
load, and then reads the child's failure output. The plugin injects the fault; the flaky test
itself runs unchanged, so what is read is the message the test really prints.

- bug-130 (R3.1, M3.1, M3.4): a store whose measurement fails (`before_gate` raises a marked
  error). The test must fail with an `AssertionError` that carries the store's captured error,
  never a bare `KeyError: 'rewrite_bytes_all'`. RED at base: the child's E line is that KeyError.
- bug-190 (R3.2's evidence, M3.4): the cold-worker skip path is made to spawn, through a function
  named `_t03_forced_spawn`. The failure must name the stack of every spawn, so the forcing
  frame appears in the output. RED at base: the message is `(wall, spawns)` only.
- bug-091 (R3.3, M3.3, M3.4): the watcher is never started and the deadline is patched to 1.5 s
  through the module constant `WATCHER_DELIVERY_DEADLINE_S` (so the test must read it at call
  time, not bind it as a default). The failure must give the elapsed time (at least the
  deadline) and the watcher's state. RED at base: `watcher did not fire` / `wait(timeout=3.0)`.

M3.2 (the bug-190 skip path spawns) is a `src/` mutation of the reranker's skip path; the node
that kills it is the flaky test itself, `test_a_cold_private_worker_is_skipped_without_spawning`.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
# A child pytest that hangs is killed here; this is a process timeout, not an assertion on time.
_CHILD_TIMEOUT_S = 300

BUG130 = "tests/test_catalog_measure.py::test_rewrite_bytes_is_the_median_of_the_runs"
BUG190 = ("tests/test_rerank_budget_real_clients.py::"
          "test_a_cold_private_worker_is_skipped_without_spawning")
BUG091 = "tests/test_watch.py::test_run_watcher_picks_up_new_file"
FORCED_DEADLINE_S = 1.5

_PLUGIN = r'''
"""t03_force: inject the fault a load flake shows (task T0.3 RED). Selected by T03_FORCE."""
import os
import time
from pathlib import Path

CASE = os.environ.get("T03_FORCE", "")
_undo = []


def _set(obj, name, value):
    _undo.append((obj, name, getattr(obj, name, None), hasattr(obj, name)))
    setattr(obj, name, value)


def _t03_never_started(*args, stop_event=None, **kw):
    """A watcher whose observer never subscribed: it only waits to be stopped."""
    if stop_event is not None:
        stop_event.wait(120)


# Nothing is imported or patched at plugin import: the conftest's sandbox redirect must run
# before any refmatrix import (rmx_sandbox.assert_under_sandbox).


def pytest_runtest_setup(item):
    mod = item.module
    if CASE == "bug130":
        real = mod.mc.run

        def forced_run(roots, scratch, out, **kw):
            def _t03_forced_store_failure(target):
                raise RuntimeError("t03-forced-store-error: the catalog rewrite failed")
            kw["before_gate"] = _t03_forced_store_failure
            return real(roots, scratch, out, **kw)
        _set(mod.mc, "run", forced_run)
    elif CASE == "bug190":
        from refmatrix.reranker import RemoteReranker
        real = RemoteReranker.with_budget

        def _t03_forced_spawn(self, budget_s):
            client = self._client
            client._ensure()                        # the spawn the skip path must not make
            spawns = Path(client._argv[3]) / "spawns"
            deadline = time.monotonic() + 60
            while not spawns.read_text().split() and time.monotonic() < deadline:
                time.sleep(0.02)                    # the stub records its own pid at start
            return real(self, budget_s)
        _set(RemoteReranker, "with_budget", _t03_forced_spawn)
    elif CASE == "bug091":
        _set(mod, "run_watcher", _t03_never_started)
        _set(mod, "WATCHER_DELIVERY_DEADLINE_S", float(os.environ["T03_DEADLINE_S"]))


def pytest_runtest_teardown(item):
    while _undo:
        obj, name, old, had = _undo.pop()
        if had:
            setattr(obj, name, old)
        else:
            delattr(obj, name)
'''


def _force(tmp_path: Path, case: str, node: str, **env_extra) -> tuple:
    plug = tmp_path / "plug"
    plug.mkdir()
    (plug / "t03_force.py").write_text(textwrap.dedent(_PLUGIN))
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(plug), str(REPO / "src")] + [p for p in env.get("PYTHONPATH", "").split(os.pathsep)
                                          if p])
    env["T03_FORCE"] = case
    env.update(env_extra)
    env.pop("PYTEST_ADDOPTS", None)
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--tb=long", "-p", "no:cacheprovider",
         "-p", "t03_force", node],
        cwd=str(REPO), env=env, capture_output=True, text=True, timeout=_CHILD_TIMEOUT_S)
    out = r.stdout + r.stderr
    return r.returncode, out


def _e_lines(out: str) -> list:
    """The failure message as pytest prints it: every `E ` line of the child's report (a
    diagnostic printed to captured stdout or stderr is not the failure message, R3.4)."""
    return [ln for ln in out.splitlines() if ln.startswith("E ")]


def test_r3_1_bug130_a_failed_store_fails_on_its_error_not_on_a_keyerror(tmp_path):
    code, out = _force(tmp_path, "bug130", BUG130)
    assert code == 1, f"the forced failure did not fail the test (exit {code}):\n{out[-3000:]}"
    e = "\n".join(_e_lines(out))
    assert "KeyError: 'rewrite_bytes_all'" not in out, (
        f"R3.1/M3.1: the test indexed rewrite_bytes_all before checking `failed`:\n{e}")
    assert "AssertionError" in out, f"R3.1: no AssertionError:\n{e}"
    assert "t03-forced-store-error" in e, (
        f"R3.4: the failure message does not carry the failed store's error:\n{e}")


def test_r3_4_bug190_a_spawn_on_the_skip_path_names_its_stack(tmp_path):
    code, out = _force(tmp_path, "bug190", BUG190)
    assert code == 1, f"the forced spawn did not fail the test (exit {code}):\n{out[-3000:]}"
    e = "\n".join(_e_lines(out))
    assert "_t03_forced_spawn" in e, (
        f"R3.2/R3.4: the failure does not name the stack of the spawn:\n{e}")


def test_r3_3_bug091_the_delivery_deadline_is_a_named_constant_of_at_least_30s():
    import ast

    from tests import test_watch as tw

    deadline = getattr(tw, "WATCHER_DELIVERY_DEADLINE_S", None)
    assert isinstance(deadline, (int, float)) and deadline >= 30, (
        f"R3.3: tests/test_watch.py has no WATCHER_DELIVERY_DEADLINE_S >= 30 (got {deadline!r})")
    tree = ast.parse((REPO / "tests" / "test_watch.py").read_text())
    (fn,) = [n for n in tree.body if isinstance(n, ast.FunctionDef)
             and n.name == "test_run_watcher_picks_up_new_file"]
    names = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)}
    assert "WATCHER_DELIVERY_DEADLINE_S" in names, "R3.3: the test does not read the constant"
    src = ast.get_source_segment((REPO / "tests" / "test_watch.py").read_text(), fn)
    assert "timeout=3.0" not in src, "R3.3: the one 3 s wait is still there"


def test_r3_4_bug091_a_watcher_that_never_fires_reports_elapsed_and_state(tmp_path):
    code, out = _force(tmp_path, "bug091", BUG091, T03_DEADLINE_S=str(FORCED_DEADLINE_S))
    assert code == 1, f"the never-started watcher did not fail the test (exit {code}):\n{out[-3000:]}"
    e = "\n".join(_e_lines(out))
    m = re.search(r"elapsed\D{0,12}(\d+(?:\.\d+)?)", e)
    assert m, f"R3.4: the failure does not give the elapsed time:\n{e}"
    assert float(m.group(1)) >= FORCED_DEADLINE_S, (
        f"M3.3: the poll gave up before its deadline ({m.group(1)} s):\n{e}")
    assert re.search(r"watcher[^\n]*(alive|running|started|stopped|state)", e, re.I), (
        f"R3.4: the failure does not give the watcher's state:\n{e}")
