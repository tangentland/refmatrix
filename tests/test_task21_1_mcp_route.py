"""Task 21.1 AC-1: the MCP `rmx_context` route writes exactly one caller-side `query.log` row.

R1 (the server sets `RMX_INVOCATION_SOURCE=mcp`), R3 (one row per context call on every route,
`source=context-mcp` for the MCP route, written by the verb, never inside the daemon op) and R4
(`query_id`, `session` resolved through R9's pointer). Everything runs for real: a sandbox daemon
(`rmx daemon start --no-detach`), the stdio server `rmx mcp` as a child of this test process (so
its owner pointer is the one written for THIS pid), and the GENERATED SessionStart command.

RED at post-bug-109 `master`: the failing assertion is the row count (no `context-mcp` row).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tests import task21_1_support as h


@pytest.fixture
def live_guard():
    snap = h.live_snapshot()
    yield
    h.assert_live_logs_unchanged(snap)


@pytest.fixture
def root(monkeypatch, live_guard) -> Path:
    for k in h.CLAUDE_ENV:
        monkeypatch.delenv(k, raising=False)
    ptr = h.global_root() / "by-pid" / f"{os.getpid()}.json"   # D3: user-level, per pid
    ptr.unlink(missing_ok=True)
    yield Path(os.environ["REFMATRIX_ROOT"])
    ptr.unlink(missing_ok=True)


def _session_start_cmd(root: Path) -> str:
    """The generated SessionStart pointer writer (D4). When the generator lacks it (HEAD) the
    literal command the spec names is used, so this leg's recorded failure is the row, not
    the generator lookup (the generator leg is AC-1b's own test)."""
    hits = [c for ev, _m, c in h.hook_entries(root, "SessionStart")
            if "focus hook --event session-start" in c]
    if hits:
        return hits[0]
    from refmatrix.hooks import HOOK_ENV
    return HOOK_ENV + "rmx focus hook --event session-start"


def test_ac1_mcp_context_writes_one_context_mcp_row_with_the_pointer_session(root):
    """AC-1: one MCP `rmx_context` call through the real stdio server produces exactly one
    `query.log` row: invocation=mcp, kind=context, source=context-mcp, a non-null query_id,
    and session == the session of the pid pointer written for the server's parent (this test
    process) by the GENERATED SessionStart command."""
    sess = "sess-ac1-pointer"
    hook = h.run_hook(_session_start_cmd(root), root=root,
                      envelope={"session_id": sess, "source": "startup",
                                "hook_event_name": "SessionStart"},
                      CLAUDE_PID=os.getpid())
    with h.SandboxDaemon(root):
        before = len(h.query_rows(root))
        with h.McpServer(root) as srv:
            r = srv.tool("rmx_context", {"ref": "anything_at_all"})
        rows = h.query_rows(root)[before:]
    mcp_rows = [x for x in rows if x.get("source") == "context-mcp"]
    assert len(mcp_rows) == 1, (
        f"AC-1/R3: expected exactly one source=context-mcp row; new rows: {rows}; "
        f"tool answer: {r['text'][:300]}")
    row = mcp_rows[0]
    assert row["kind"] == "context", row
    assert row["invocation"] == "mcp", f"R1: the server must set RMX_INVOCATION_SOURCE=mcp: {row}"
    assert row.get("query_id"), f"R4: query_id missing: {row}"
    assert len(rows) == 1, f"R3: exactly one row per call (none from the daemon op): {rows}"
    # The pointer observable (D3/D4): written by the generated hook under the global by-pid/.
    ptr = h.global_root() / "by-pid" / f"{os.getpid()}.json"
    assert ptr.is_file(), (f"D3/D4: the SessionStart writer left no pointer at {ptr}; "
                           f"hook rc={hook.returncode} stderr={hook.stderr[-400:]}")
    assert json.loads(ptr.read_text())["session"] == sess
    assert row.get("session") == sess, f"R4/R9: row session must be the pointer's: {row}"
