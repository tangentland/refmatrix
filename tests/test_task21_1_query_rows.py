"""Task 21.1 RED: query.log rows on every context route, invocation precedence, grep-stdin
cardinality, one recall log format, and the ONE outcome vocabulary.

ACs covered here (workflow/plans/plan-21-agent-context-usage-tasks/
task-21.1-context-usage-telemetry.md, through revision round 12):
  AC-2   CLI routes: one `query.log` row per `rmx context` on the replica, daemon and direct
         routes, `source` naming the route (R3), each carrying R4's `query_id`, `cwd`, `root`.
  AC-3   `invocation_source()` precedence (R2): explicit > CLAUDECODE (`agent`) > tty > unknown.
  AC-5   `grep-stdin` rows carry `cardinality` = lines emitted (R6).
  AC-9   one recall log format: the only recall-carrying `*.jsonl` written under
         `src/refmatrix/` is `recall-events.jsonl` (R8).
  AC-2b  validation leg: `CALL_OUTCOMES`, `OUTCOMES_BY_KIND`, `classify_outcome(...,
         budgeted=)` by exception type, and `log_query` rewriting an outcome outside the
         vocabulary to `error` / `outcome-invalid: <v>` (R4, round-9 #m9-5, round-12 #m12-2).
         (`--agent-usage`'s `outcome-invalid=1` print is in test_task21_1_recall_skip.py.)

Every test runs inside task 23.0's sandbox and ends by asserting the live logs did not move
(AC preamble; `(inode, size)` by `os.stat`, see tests/task21_1_support.py).
"""
from __future__ import annotations

import ast
import io
import json
import os
import re
import socket
import sys
import textwrap
from pathlib import Path

import pytest

from refmatrix import telemetry
from tests import task21_1_support as h

SRC_PKG = h.SRC / "refmatrix"
_HEX32 = re.compile(r"^[0-9a-f]{32}$")


@pytest.fixture(autouse=True)
def _live_logs_guard(monkeypatch):
    for k in h.CLAUDE_ENV:
        monkeypatch.delenv(k, raising=False)
    snap = h.live_snapshot()
    yield
    h.assert_live_logs_unchanged(snap)


@pytest.fixture
def root() -> Path:
    return Path(os.environ["REFMATRIX_ROOT"])


def _context_rows(root: Path) -> list[dict]:
    return [r for r in h.query_rows(root) if r.get("kind") == "context"]


def _strip_replica(root: Path) -> None:
    """Remove every file `cli._replica_reader_path()` could resolve to, so
    `_should_via_replica(False)` is False: the snapshot, the legacy symlink, the legacy
    `catalog.duckdb`, and the INACTIVE slot the `active` marker names. The active (writer)
    slot is left, so a running daemon keeps serving and an absent daemon leaves the direct
    route `_store()` its catalog. Probed at HEAD: with these gone the CLI takes the daemon
    route (daemon up) or the direct route (daemon down)."""
    for n in ("catalog.read.duckdb", "read_only.duckdb", "catalog.duckdb"):
        p = root / n
        if p.exists() or p.is_symlink():
            p.unlink()
    marker = root / "active"
    if marker.exists():
        active = marker.read_text().strip()
        inactive = "B" if active == "A" else "A"
        for suf in (".duckdb", ".offset", ".duckdb.wal"):
            p = root / f"catalog.{inactive}{suf}"
            if p.exists():
                p.unlink()


def _assert_r4_fields(row: dict, *, cwd: Path, root: Path) -> None:
    for k in ("session", "query_id", "cwd", "root"):
        assert k in row, f"R4: query.log row lacks `{k}`: {row}"
    assert isinstance(row["query_id"], str) and _HEX32.match(row["query_id"]), (
        f"R4: query_id is not a uuid4 hex: {row}")
    assert Path(row["cwd"]).resolve() == cwd.resolve(), f"R4: cwd is the CALLER's: {row}"
    assert Path(row["root"]).resolve() == root.resolve(), f"R4: root is the store: {row}"


# ---- AC-2: one row per CLI route -----------------------------------------------------------

def test_ac2_replica_route_writes_one_context_replica_row_with_r4_fields(root):
    """AC-2 replica route (exists at HEAD) + R4: the row gains query_id / cwd / root."""
    caller = root.parent / "caller-cwd"
    caller.mkdir()
    r = h.run_rmx(["context", "alpha_symbol"], root=root, cwd=caller)
    rows = _context_rows(root)
    assert [x["source"] for x in rows] == ["context-replica"], (rows, r.stderr[-500:])
    _assert_r4_fields(rows[0], cwd=caller, root=root)
    assert r.returncode == 0, r.stderr


def test_ac2_daemon_route_writes_one_context_daemon_row_on_the_caller_side(root):
    """AC-2 daemon route (`cli.py` `daemon_mod.call(root, "context", ...)`): exactly one row,
    `source=context-daemon`. RED at HEAD: no row at all. Written by the CALLER (R3): the row's
    `cwd` is the CLI's cwd, not the daemon's (the daemon runs with cwd = the project dir)."""
    caller = root.parent / "caller-cwd"
    caller.mkdir()
    with h.SandboxDaemon(root):
        _strip_replica(root)
        r = h.run_rmx(["context", "alpha_symbol"], root=root, cwd=caller)
        rows = _context_rows(root)
    assert [x["source"] for x in rows] == ["context-daemon"], (
        f"AC-2: the daemon route wrote {len(rows)} context rows: {rows}; stderr={r.stderr[-400:]}")
    _assert_r4_fields(rows[0], cwd=caller, root=root)
    assert r.returncode == 0, r.stderr


def test_ac2_direct_route_writes_one_context_row_with_r4_fields(root):
    """AC-2 direct route (`source=context`, exists at HEAD) + R4 fields (RED: none today)."""
    with h.SandboxDaemon(root):     # boots the A/B slots, then stops: a daemon-shaped store
        pass
    _strip_replica(root)
    caller = root.parent / "caller-cwd"
    caller.mkdir()
    r = h.run_rmx(["context", "alpha_symbol"], root=root, cwd=caller)
    rows = _context_rows(root)
    assert [x["source"] for x in rows] == ["context"], (rows, r.stderr[-500:])
    _assert_r4_fields(rows[0], cwd=caller, root=root)
    assert r.returncode == 0, r.stderr


# ---- AC-3: precedence ----------------------------------------------------------------------

class _Tty(io.StringIO):
    def isatty(self) -> bool:
        return True


class _NoTty(io.StringIO):
    def isatty(self) -> bool:
        return False


@pytest.mark.parametrize("env, tty, want", [
    ({"RMX_INVOCATION_SOURCE": "hook", "CLAUDECODE": "1"}, False, "hook"),
    ({"CLAUDECODE": "1"}, False, "agent"),
    ({}, True, "interactive"),
    ({}, False, "unknown"),
], ids=["explicit-hook+CLAUDECODE", "CLAUDECODE-alone", "tty-alone", "none"])
def test_ac3_invocation_source_precedence(monkeypatch, env, tty, want):
    """AC-3 (R2): explicit RMX_INVOCATION_SOURCE > CLAUDECODE -> `agent` > tty ->
    `interactive` > `unknown`. RED at HEAD on CLAUDECODE alone (returns `unknown`).
    `sys.stdin` is replaced by a StringIO answering `isatty()` (a dependency, registered)."""
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(sys, "stdin", _Tty() if tty else _NoTty())
    assert telemetry.invocation_source() == want


def test_ac3_tty_does_not_beat_claudecode(monkeypatch):
    """AC-3 / R2 order: CLAUDECODE is step 2, the tty step 3 (a `!`-typed human command inside
    Claude Code logs `agent`, stated in R2)."""
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setattr(sys, "stdin", _Tty())
    assert telemetry.invocation_source() == "agent"


def test_ac3_agent_is_a_member_of_invocation_sources():
    """AC-3 / R2: `agent` joins INVOCATION_SOURCES (an explicit RMX_INVOCATION_SOURCE=agent is
    then kept rather than mapped to unknown)."""
    assert "agent" in telemetry.INVOCATION_SOURCES


# ---- AC-5: grep-stdin cardinality ----------------------------------------------------------

def test_ac5_grep_stdin_row_carries_cardinality(root):
    """AC-5 (R6): `printf 'a\\nb\\nc\\nd\\n' | rmx grep -E 'a|b|c'` logs a `grep-stdin` row with
    `cardinality=3`. RED at HEAD (`null`)."""
    r = h.run_rmx(["grep", "-E", "a|b|c"], root=root, input="a\nb\nc\nd\n")
    rows = [x for x in h.query_rows(root) if x.get("source") == "grep-stdin"]
    assert len(rows) == 1, (rows, r.stderr[-400:])
    assert rows[0]["cardinality"] == 3, rows[0]
    assert r.stdout.splitlines() == ["a", "b", "c"], r.stdout


# ---- AC-9: one recall log format -----------------------------------------------------------

_RECALLISH = re.compile(r"recall|event|deliver|retriev|used", re.I)
SINK = "recall-events.jsonl"


def _jsonl_names(tree: ast.AST) -> list[tuple[int, str]]:
    """Every `*.jsonl` FILE NAME the module spells: plain constants (`"queue.jsonl"`) and
    f-string templates rendered with `{}` for each field (`f"{key}.jsonl"` -> `{}.jsonl`).
    Globs (`*.jsonl`) and a bare suffix (`.jsonl`) are readers / suffix tests, not names."""
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            v = n.value
            if v.endswith(".jsonl") and not v.startswith(("*", ".")) and re.fullmatch(
                    r"[\w.\-/]+", v):
                out.append((n.lineno, v.rsplit("/", 1)[-1]))
        elif isinstance(n, ast.JoinedStr):
            parts = []
            for v in n.values:
                parts.append(v.value if isinstance(v, ast.Constant) else "{}")
            s = "".join(parts)
            if s.endswith(".jsonl") and re.fullmatch(r"[\w.\-/{}]+", s):
                out.append((n.lineno, s.rsplit("/", 1)[-1]))
    return out


def _recall_jsonl_violations(files) -> list[str]:
    bad = []
    for p in files:
        for line, name in _jsonl_names(ast.parse(Path(p).read_text())):
            if _RECALLISH.search(name) and name != SINK:
                bad.append(f"{p}:{line}: {name}")
    return bad


def _src_files() -> list[Path]:
    return sorted(SRC_PKG.rglob("*.py"))


def test_ac9_no_recall_log_format_other_than_recall_events_jsonl():
    """AC-9 (R8): every `*.jsonl` name written under src/refmatrix/ that carries recall items
    (named for recall / events / delivery / retrieval / use) is `recall-events.jsonl`; and the
    sink EXISTS (named in telemetry.py, the ONE writer `emit_recall_events`, R11). RED at HEAD:
    no module names the sink."""
    assert _recall_jsonl_violations(_src_files()) == []
    holders = [p for p in _src_files()
               if any(n == SINK for _l, n in _jsonl_names(ast.parse(p.read_text())))]
    assert holders == [SRC_PKG / "telemetry.py"], (
        f"R8/R11: `{SINK}` must be named exactly once, in telemetry.py (the one writer); "
        f"named in: {holders}")


def test_ac9_the_scan_reports_a_planted_second_recall_log(tmp_path):
    """AC-9 control: the scan is not vacuous -- a module writing `recall-hits.jsonl` (or an
    f-string `{session}.events.jsonl`) is reported."""
    planted = tmp_path / "planted.py"
    planted.write_text(textwrap.dedent("""
        def bad(root, s):
            open(root / "recall-hits.jsonl", "a").write("x")
            open(root / f"{s}.events.jsonl", "a").write("x")
            open(root / "recall-events.jsonl", "a").write("ok")
    """))
    bad = _recall_jsonl_violations([planted])
    assert len(bad) == 2 and "recall-hits.jsonl" in bad[0] and "{}.events.jsonl" in bad[1], bad


# ---- AC-2b validation leg: the one outcome vocabulary ----------------------------------------

def test_ac2b_call_outcomes_is_the_one_vocabulary():
    """AC-2b / R4 (round-9 #m9-5): the existing four outcomes plus `skipped_budget`."""
    assert hasattr(telemetry, "CALL_OUTCOMES"), "R4: telemetry.CALL_OUTCOMES not built"
    assert telemetry.CALL_OUTCOMES == (
        "ok", "empty", "consumer-closed", "error", "skipped_budget")


def test_ac2b_outcomes_by_kind_is_defined_empty():
    """AC-2b / R4 (round-10 #m10-4): `OUTCOMES_BY_KIND` exists with no entries (21.3 adds
    `nudge`), so every kind validates against CALL_OUTCOMES."""
    assert hasattr(telemetry, "OUTCOMES_BY_KIND"), "R4: telemetry.OUTCOMES_BY_KIND not built"
    assert telemetry.OUTCOMES_BY_KIND == {}


def _budgeted(exc_type, exc):
    try:
        return telemetry.classify_outcome(exc_type, exc, budgeted=True)
    except TypeError as e:
        pytest.fail(f"R4: classify_outcome has no `budgeted` keyword ({e})")


def test_ac2b_broken_pipe_is_error_under_a_budget_and_consumer_closed_without():
    """AC-2b validation leg (round-12 #m12-2; kills the round-11 mutation mapping a
    daemon-socket broken pipe to `consumer-closed` under budgeted=True): the OSError test runs
    before the BrokenPipeError mapping only when budgeted."""
    e = BrokenPipeError(32, "Broken pipe")
    assert _budgeted(BrokenPipeError, e) == ("error", "BrokenPipeError: [Errno 32] Broken pipe")
    assert telemetry.classify_outcome(BrokenPipeError, e, budgeted=False) == (
        "consumer-closed", None)


@pytest.mark.parametrize("exc", [TimeoutError(), socket.timeout()],
                         ids=["TimeoutError", "socket.timeout"])
def test_ac2b_timeouts_are_skipped_budget_when_budgeted(exc):
    """AC-2b (round-12 #m12-2): TimeoutError / socket.timeout -> `skipped_budget` (kills the
    mutation placing the generic OSError test before the timeout test: both are OSErrors)."""
    assert _budgeted(type(exc), exc)[0] == "skipped_budget"


def test_ac2b_verb_busy_is_skipped_budget_when_budgeted():
    """AC-2b / R4: every VerbBusyError reaching the degrade path is `skipped_budget`."""
    from refmatrix.verbs import VerbBusyError
    e = VerbBusyError("daemon busy pid=1")
    assert _budgeted(VerbBusyError, e)[0] == "skipped_budget"


@pytest.mark.parametrize("exc, head", [
    (ConnectionRefusedError(61, "Connection refused"), "ConnectionRefusedError"),
    (json.JSONDecodeError("Expecting value", "", 0), "JSONDecodeError"),
], ids=["ConnectionRefusedError", "JSONDecodeError"])
def test_ac2b_other_transport_failures_are_error_when_budgeted(exc, head):
    """AC-2b / R4 (round-9 #m9-5, round-10 #s10-2): a refused connect and a mid-answer close
    are `error`, never `skipped_budget`, and the error text names the type."""
    outcome, err = _budgeted(type(exc), exc)
    assert outcome == "error" and err.startswith(head), (outcome, err)


def test_ac2b_unbudgeted_classification_is_unchanged():
    """AC-2b: `budgeted` defaults to False and the bug-052 mapping stands (the verb/MCP route
    is classified unbudgeted by design, round-11 #m11-6)."""
    from refmatrix.verbs import VerbBusyError
    e = VerbBusyError("busy")
    try:
        out = telemetry.classify_outcome(VerbBusyError, e, budgeted=False)
    except TypeError as te:
        pytest.fail(f"R4: classify_outcome has no `budgeted` keyword ({te})")
    assert out == ("error", "VerbBusyError: busy")


def _write_with_outcome(root: Path, kind: str, outcome: str) -> dict:
    with telemetry.log_query(None, kind=kind, body="q", source="test", root=root) as t:
        t.outcome = outcome
    return h.query_rows(root)[-1]


def test_ac2b_log_query_rewrites_an_outcome_outside_the_vocabulary(root):
    """AC-2b validation leg: a handle given `t.outcome = "timeout"` writes `outcome=error`,
    `error="outcome-invalid: timeout"` (never silently kept or dropped). RED at HEAD: the set
    outcome is ignored and the row reads `ok`."""
    row = _write_with_outcome(root, "recall", "timeout")
    assert (row["outcome"], row["error"]) == ("error", "outcome-invalid: timeout"), row


def test_ac2b_log_query_honours_a_set_valid_outcome(root):
    """AC-2b / R4: `__exit__` uses a set `t.outcome` in place of its own classification (the
    degrade path sets `skipped_budget` on a call that returned normally)."""
    row = _write_with_outcome(root, "recall", "skipped_budget")
    assert row["outcome"] == "skipped_budget", row
