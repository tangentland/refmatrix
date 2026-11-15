"""t03_capture: the pytest plugin the T0.3 load harness loads into the TARGET process only.

Task T0.3 (`task-t0-suite-trust-sweep#t0-3-bands`). A trial's outcome is the target test's own
(r3 m-1), so this plugin writes, to `$T03_TRIAL_DIR/target-outcomes.jsonl`, one record when each
node starts and one per phase report (outcome, the E lines, the duration). A node that started
and has no `call`/`teardown` record when the cap kills the process is the hang.

It also writes `$T03_TRIAL_DIR/diag.jsonl`: the evidence the base trials need before any fix,
because at base the five tests do not explain their own failures (R3.4 is what fixes that):
- bug-130: the rows `measure_catalogs.run` returned (a failed store's captured error);
- bug-190: the stack of every `WorkerClient._spawn` (R3.2: "the reproducer records the stack of
  every spawn");
- bug-091: the live threads when the test fails (the watcher's state);
- bug-228: the boot time of `SandboxDaemon`, the wall of `run_hook`, and on a failure the
  store's `query.log`, `rmxd.log` and daemon stderr tails, which the leg breakdown is read from
  (`#t0-3-bug228-legs`);
- bug-231: each `daemon.graceful_stop` call's grace, wall, report and result.

Every wrapper calls the real function through; none changes a result. They are spies,
registered in `workflow/test_mock_registry.md`. All are removed at the node's teardown.
"""
from __future__ import annotations

import json
import os
import threading
import time
import traceback
from pathlib import Path

_DIR = Path(os.environ.get("T03_TRIAL_DIR") or ".")
_undo: list = []
_t_start: dict = {}


def _write(name: str, rec: dict) -> None:
    rec = dict(rec, t=time.time())
    with open(_DIR / name, "a") as fh:
        fh.write(json.dumps(rec, default=str) + "\n")


def _diag(node: str, kind: str, **kw) -> None:
    _write("diag.jsonl", dict(node=node, kind=kind, **kw))


def _wrap(obj, name: str, make) -> None:
    real = getattr(obj, name)
    _undo.append((obj, name, real))
    setattr(obj, name, make(real))


def _tail(path: Path, n: int = 200) -> str:
    try:
        return "\n".join(path.read_text(errors="replace").splitlines()[-n:])
    except OSError as e:
        return f"<unreadable: {type(e).__name__}: {e}>"


def pytest_runtest_logstart(nodeid, location):
    _t_start[nodeid] = time.monotonic()
    _write("target-outcomes.jsonl", {"node": nodeid, "event": "start"})


def pytest_runtest_logreport(report):
    e_lines = []
    if report.failed:
        text = getattr(report, "longreprtext", "") or str(report.longrepr)
        e_lines = [ln for ln in text.splitlines() if ln.startswith("E ")]
    _write("target-outcomes.jsonl", {
        "node": report.nodeid, "event": "report", "phase": report.when,
        "outcome": report.outcome, "duration": report.duration, "e_lines": e_lines[:40],
        "crash": (str(report.longrepr.reprcrash.message)
                  if report.failed and hasattr(report.longrepr, "reprcrash") else None)})


def pytest_runtest_setup(item):
    node = item.nodeid
    if "test_catalog_measure.py" in node:
        mod = item.module

        def make(real):
            def run(*a, **kw):
                rows, v, code = real(*a, **kw)
                _diag(node, "bug130.rows", rows=rows, verdict=v, code=code)
                return rows, v, code
            return run
        _wrap(mod.mc, "run", make)
    elif "test_rerank_budget_real_clients.py" in node:
        from refmatrix import subproc

        def make(real):
            def _spawn(self):
                _diag(node, "bug190.spawn", stack="".join(traceback.format_stack()))
                return real(self)
            return _spawn
        _wrap(subproc.WorkerClient, "_spawn", make)
    elif "test_task21_1_recall_skip.py" in node:
        from tests import task21_1_support as h

        def make_init(real):
            def __init__(self, root, *a, **kw):
                t0 = time.monotonic()
                try:
                    return real(self, root, *a, **kw)
                finally:
                    _diag(node, "bug228.sandbox_daemon_boot", seconds=time.monotonic() - t0,
                          root=str(root))
            return __init__

        def make_hook(real):
            def run_hook(*a, **kw):
                t0 = time.monotonic()
                try:
                    return real(*a, **kw)
                finally:
                    _diag(node, "bug228.run_hook", seconds=time.monotonic() - t0)
            return run_hook
        _wrap(h.SandboxDaemon, "__init__", make_init)
        _wrap(h, "run_hook", make_hook)
    elif "test_plan4_remedy.py" in node:
        from refmatrix import daemon as dm

        def make(real):
            def graceful_stop(root, *, grace, report=None):
                rep = report if report is not None else {}
                t0 = time.monotonic()
                ok = real(root, grace=grace, report=rep)
                _diag(node, "bug231.graceful_stop", grace=grace,
                      seconds=time.monotonic() - t0, report=rep, result=ok)
                return ok
            return graceful_stop
        _wrap(dm, "graceful_stop", make)


def pytest_runtest_makereport(item, call):
    if call.when != "call" or call.excinfo is None:
        return
    node = item.nodeid
    if "test_watch.py" in node:
        _diag(node, "bug091.threads", threads=[
            {"name": t.name, "alive": t.is_alive(), "daemon": t.daemon}
            for t in threading.enumerate()])
    elif "test_task21_1_recall_skip.py" in node:
        root = Path(os.environ.get("REFMATRIX_ROOT", "."))
        _diag(node, "bug228.logs", root=str(root),
              query_log=_tail(root / "query.log", 40), rmxd_log=_tail(root / "rmxd.log"),
              daemon_stderr=_tail(root.parent / "daemon-test.stderr.log"))


def pytest_runtest_teardown(item):
    while _undo:
        obj, name, real = _undo.pop()
        setattr(obj, name, real)
