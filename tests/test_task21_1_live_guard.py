"""The task-21.1 live-log guard, converged with 23.0 (ch-bsd r2 #s2, bug-134).

Two halves, one rule each:
- the PER-TEST guard (`tests/task21_1_support.assert_live_logs_unchanged`) only STATS a live
  log -- a test process may never open one (23.0's audit hook refuses it). It fails on a
  rotation or truncation, and records growth to the sandbox growth ledger;
- the END-OF-RUN content check (`rmx_sandbox.check_logs` -> `growth_leaks`, run by
  scripts/sandbox-proof.sh outside any sandboxed process) reads each recorded byte range ONCE
  and fails on a complete row carrying a recorded marker (a sandbox path, a minted token);
  concurrent live rows (bug-134's +379 B `scan-prompt` hook row) and a partial trailing line
  are not leaks.

Every leg runs the real code over stand-in logs and a stand-in ledger under `tmp_path`.
"""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

import rmx_sandbox
from tests import task21_1_support as h

LIVE_ROW = {"ts": "2026-10-19T16:03:28", "kind": "scan", "body": "<agent-message …>",
            "source": "scan-prompt", "invocation": "hook", "cwd": "/Users/someone/elsewhere"}


@pytest.fixture
def watched(monkeypatch, tmp_path):
    """The guard's watched-path list pointed at ONE stand-in log, and the growth ledger at a
    stand-in file (registered: no test writes a live log); guard and checker run unpatched."""
    p = tmp_path / "live" / "query.log"
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps(LIVE_ROW) + "\n")
    monkeypatch.setattr(h, "live_log_paths", lambda: [p])
    monkeypatch.setenv("RMX_LIVE_GROWTH_LEDGER", str(tmp_path / "growth.jsonl"))
    return p


def _append(p: Path, text: str) -> None:
    with open(p, "a") as f:
        f.write(text)


def _ledger(tmp_path: Path) -> list[dict]:
    g = tmp_path / "growth.jsonl"
    return [json.loads(x) for x in g.read_text().splitlines()] if g.exists() else []


def _check(tmp_path: Path, capsys) -> tuple[int, str]:
    n = rmx_sandbox.check_logs({}, "", str(tmp_path / "no-touches.log"), 0,
                               str(tmp_path / "growth.jsonl"), 0)
    return n, capsys.readouterr().out


# ---- the per-test guard: stat only ------------------------------------------------------

def test_guard_records_growth_without_opening_the_live_log(watched, tmp_path):
    """Growth passes the per-test guard and is RECORDED (path, inode, start, end, nodeid,
    markers) -- and the guard never opens the log: the stand-in is mode 000 while it runs, so
    an open raises. RED at the r2 guard (it opened the log: the 23.0 audit hook's
    SandboxViolation on the real one)."""
    snap = h.live_snapshot()
    size0 = watched.stat().st_size
    _append(watched, json.dumps(LIVE_ROW) + "\n")
    watched.chmod(0)
    try:
        h.assert_live_logs_unchanged(snap)
    finally:
        watched.chmod(stat.S_IRUSR | stat.S_IWUSR)
    (e,) = _ledger(tmp_path)
    assert (e["path"], e["start"], e["end"]) == (str(watched), size0, watched.stat().st_size), e
    assert e["ino"] == watched.stat().st_ino and "test_guard_records_growth" in e["nodeid"], e
    assert os.environ["RMX_SANDBOX_ROOT"] in e["markers"], e["markers"]


def test_guard_fails_a_rotation(watched, tmp_path):
    """An inode change (rotate/replace) is never the user's: it fails in the test."""
    snap = h.live_snapshot()
    q = watched.with_name("query.log.new")
    q.write_text(json.dumps(LIVE_ROW) * 2 + "\n")
    os.replace(q, watched)
    with pytest.raises(AssertionError, match="inode changed"):
        h.assert_live_logs_unchanged(snap)
    assert _ledger(tmp_path) == []


def test_guard_fails_a_truncation(watched):
    _append(watched, json.dumps(LIVE_ROW) + "\n")
    snap = h.live_snapshot()
    with open(watched, "r+") as f:
        f.truncate(10)
    with pytest.raises(AssertionError, match="shrank"):
        h.assert_live_logs_unchanged(snap)


# ---- the end-of-run check: attribution once ----------------------------------------------

def test_check_ignores_an_unrelated_live_row(watched, tmp_path, capsys):
    """bug-134's false positive, now at the checker: a concurrent live row (no sandbox path,
    no minted token) in the recorded growth is not a leak."""
    snap = h.live_snapshot()
    _append(watched, json.dumps(LIVE_ROW) + "\n")
    h.assert_live_logs_unchanged(snap)
    n, out = _check(tmp_path, capsys)
    assert n == 0 and "attributed_growth_rows=0" in out, out


def test_check_does_not_judge_a_partial_trailing_line(watched, tmp_path, capsys):
    snap = h.live_snapshot()
    _append(watched, '{"cwd": "' + os.environ["RMX_SANDBOX_ROOT"])
    h.assert_live_logs_unchanged(snap)
    n, out = _check(tmp_path, capsys)
    assert n == 0, out


@pytest.mark.parametrize("field", ["cwd", "root"])
def test_check_catches_a_planted_row_under_the_sandbox_root(watched, tmp_path, capsys, field):
    """A real leak: a row whose cwd/root is a sandbox store, in the OTHER macOS /tmp spelling,
    appended during a test is attributed to that test's nodeid by the end-of-run check."""
    snap = h.live_snapshot()
    sb = os.environ["RMX_SANDBOX_ROOT"]
    other = ("/tmp/" + sb[len("/private/tmp/"):]) if sb.startswith("/private/tmp/") else sb
    _append(watched, json.dumps(LIVE_ROW) + "\n"
            + json.dumps({**LIVE_ROW, field: other + "/r/1/.refmatrix"}) + "\n")
    h.assert_live_logs_unchanged(snap)
    n, out = _check(tmp_path, capsys)
    assert n == 1 and "GROWTH-LEAK" in out and "test_check_catches_a_planted_row" in out, out


def test_check_catches_a_planted_row_carrying_a_minted_token(watched, tmp_path, capsys):
    """A leak with no sandbox path is still the test's when it carries a session id the test
    minted (`h.mark_token`), recorded with the growth."""
    h.mark_token("sess-guard-planted-7f3a")
    snap = h.live_snapshot()
    _append(watched, json.dumps({**LIVE_ROW, "session": "sess-guard-planted-7f3a"}) + "\n")
    h.assert_live_logs_unchanged(snap)
    n, out = _check(tmp_path, capsys)
    assert n == 1 and "sess-guard-planted-7f3a" in out, out


def test_check_cli_consumes_the_ledger_from_its_recorded_size(watched, tmp_path, capsys):
    """The `check` entry scripts/sandbox-proof.sh calls takes GROWTH GROWTH_SIZE: records
    before GROWTH_SIZE (an earlier run's) are not re-judged; this run's leak fails it."""
    h.mark_token("sess-guard-cli-91b2")
    snap = h.live_snapshot()
    _append(watched, json.dumps({**LIVE_ROW, "session": "sess-guard-cli-91b2"}) + "\n")
    h.assert_live_logs_unchanged(snap)
    g = tmp_path / "growth.jsonl"
    snapf = tmp_path / "snap.json"
    snapf.write_text("{}")
    args = ["check", str(snapf), "", str(tmp_path / "t.log"), "0", str(g)]
    assert rmx_sandbox._main(args + ["0"]) == 1
    assert rmx_sandbox._main(args + [str(g.stat().st_size)]) == 0
    capsys.readouterr()
