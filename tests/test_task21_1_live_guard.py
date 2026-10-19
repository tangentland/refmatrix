"""The task-21.1 live-log guard attributes what moved (ch-bsd r2 #s2, bug-134).

`tests/task21_1_support.assert_live_logs_unchanged` is the AC preamble's teardown in every
task-21.1 test file. It compared only `(inode, size)`, so the main dev tree's `query.log` --
appended by every hook of whichever Claude session works there -- failed it for the user's
typing (task21.1-r1-tests-final-full.log: +379 B, a live `scan-prompt` hook row, reported as an
ERROR at teardown of `test_ac4b_xiii_text_key_envelope_on_the_recall_path`).

These legs run the REAL guard over stand-in log files under `tmp_path` (never the live logs):
it must still catch a planted leak (a row carrying the sandbox root, or a token the test
minted), a rotation and a truncation, and must ignore an unrelated appended row and a partial
trailing line.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tests import task21_1_support as h


@pytest.fixture
def watched(monkeypatch, tmp_path):
    """The guard's watched-path list pointed at ONE stand-in log under tmp_path (registered:
    the live logs are never written by a test); the guard itself runs unpatched."""
    p = tmp_path / "live" / "query.log"
    monkeypatch.setattr(h, "live_log_paths", lambda: [p])
    return p


def _log(p: Path, rows: list[dict]) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return p


def _append(p: Path, text: str) -> None:
    with open(p, "a") as f:
        f.write(text)


LIVE_ROW = {"ts": "2026-10-19T16:03:28", "kind": "scan", "body": "<agent-message …>",
            "source": "scan-prompt", "invocation": "hook", "cwd": "/Users/someone/elsewhere"}


def test_an_unrelated_live_row_appended_during_the_test_is_ignored(watched):
    """The bug-134 false positive: a concurrent live hook row (no sandbox path, no minted
    token) appended to a watched log does not fail the guard. RED at HEAD (size moved)."""
    p = _log(watched, [LIVE_ROW])
    snap = h.live_snapshot()
    _append(p, json.dumps(LIVE_ROW) + "\n")
    h.assert_live_logs_unchanged(snap)


def test_a_partial_trailing_line_is_not_judged(watched):
    """A concurrent writer mid-append leaves an incomplete last line: not judged (it cannot
    be attributed until complete), even if it would carry a marker."""
    p = _log(watched, [LIVE_ROW])
    snap = h.live_snapshot()
    _append(p, '{"cwd": "' + os.environ["RMX_SANDBOX_ROOT"])
    h.assert_live_logs_unchanged(snap)


@pytest.mark.parametrize("field", ["cwd", "root"])
def test_a_planted_row_under_the_sandbox_root_is_caught(watched, field):
    """A real leak: a row whose cwd/root is a sandbox store (the shape a test's `rmx` child
    writes when it reaches a live log) fails the guard, in either macOS /tmp spelling."""
    p = _log(watched, [LIVE_ROW])
    snap = h.live_snapshot()
    sb = os.environ["RMX_SANDBOX_ROOT"]
    other = ("/tmp/" + sb[len("/private/tmp/"):]) if sb.startswith("/private/tmp/") else sb
    _append(p, json.dumps(LIVE_ROW) + "\n"
            + json.dumps({**LIVE_ROW, field: other + "/r/1/.refmatrix"}) + "\n")
    with pytest.raises(AssertionError, match="attributable to this test"):
        h.assert_live_logs_unchanged(snap)


def test_a_planted_row_carrying_a_minted_token_is_caught(watched):
    """A leak with no sandbox path (e.g. cwd = the dev tree) is still the test's when it
    carries a session id the test minted (`h.mark_token`)."""
    p = _log(watched, [LIVE_ROW])
    snap = h.live_snapshot()
    h.mark_token("sess-guard-planted-7f3a")
    _append(p, json.dumps({**LIVE_ROW, "session": "sess-guard-planted-7f3a"}) + "\n")
    with pytest.raises(AssertionError, match="attributable to this test"):
        h.assert_live_logs_unchanged(snap)


def test_a_rotation_fails_whatever_it_holds(watched):
    """An inode change (rotate/replace) is never the user's typing: it fails even with only
    unrelated rows."""
    p = _log(watched, [LIVE_ROW])
    snap = h.live_snapshot()
    q = p.with_name("query.log.new")
    q.write_text(json.dumps(LIVE_ROW) + "\n" + json.dumps(LIVE_ROW) + "\n")
    os.replace(q, p)
    with pytest.raises(AssertionError, match="inode changed"):
        h.assert_live_logs_unchanged(snap)


def test_a_truncation_fails(watched):
    p = _log(watched, [LIVE_ROW, LIVE_ROW])
    snap = h.live_snapshot()
    with open(p, "r+") as f:
        f.truncate(10)
    with pytest.raises(AssertionError, match="shrank"):
        h.assert_live_logs_unchanged(snap)
