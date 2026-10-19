"""Task 21.1 AC-2b: a recall the hook SKIPS is still a `query.log` row (round-8 #nm-5, as
amended by rounds 9-12).

The per-prompt recall hook (`rmx memory recall --stdin-json ... --timeout 5`) degrades past its
budget to "recall skipped", `[]` and exit 0 (`cli.memory_recall`'s `_degrade_or_raise`). At HEAD
that outcome leaves no trace in telemetry: no `kind=recall` row is written on ANY route, so a
skipped prompt and a prompt that was never asked are indistinguishable, and "recall ran and
delivered 0" cannot be told apart from "recall never ran".

Every leg runs the GENERATED UserPromptSubmit command (not a hand-written one) in a child
`bash -c`, against the per-test sandbox store, and talks to a test-owned socket peer at
`daemon.socket_path(root)` -- the client code under test runs unchanged; only the process on
the other end of the socket is the test's. RED at HEAD: the failing assertion of each hook leg
is the `kind=recall` row count (spec AC-2b, "RED at HEAD: no kind=recall row is written at
all"); the report legs fail because `--agent-usage` does not parse.
"""
from __future__ import annotations

import json
import os
import re
import socket
import threading
import time
from pathlib import Path

import pytest

from tests import task21_1_support as h

SESSION = "sess-ac2b-0001"
PROMPT = "which parser handles the widget tokens"


@pytest.fixture
def root():
    return Path(os.environ["REFMATRIX_ROOT"])


@pytest.fixture(autouse=True)
def _live_logs_untouched():
    """AC preamble: the live query.log / recall-events.jsonl line counts are unchanged."""
    snap = h.live_snapshot()
    yield
    h.assert_live_logs_unchanged(snap)


def _envelope() -> dict:
    return {"session_id": SESSION, "prompt": PROMPT, "hook_event_name": "UserPromptSubmit",
            "cwd": "", "transcript_path": ""}


def _recall_cmd(root: Path) -> str:
    return h.generated_cmd(root, "UserPromptSubmit", "memory recall --stdin-json")


def _recall_rows(root: Path) -> list[dict]:
    return [r for r in h.query_rows(root) if r.get("kind") == "recall"]


def _stdout_is_empty_json(out: str) -> bool:
    lines = [l for l in out.splitlines() if l.strip()]
    return lines == ["[]"]


def _bootstrap_window(root: Path) -> None:
    """Put the sandbox store in the state whose hook traffic the spec records for HEAD
    ([ping, partition_list, ping, memory_recall], AC-2b / round-11 #s11-1): a rotated store
    (`active` = A, `catalog.A.duckdb`) whose lock-free reader slot does not exist yet. A fresh
    `Store.init()` store reads its own `catalog.duckdb` as the "replica", so the legacy-partition
    probe never asks the daemon and the traffic is only [ping, memory_recall] (measured at
    HEAD d4bf001); without a reader slot the probe asks the daemon (`ping`, `partition_list`,
    `_legacy_memory_partition_exists` path 2) and the replica recall leg falls through to
    `require_daemon` (`ping`) and the `memory_recall` op."""
    (root / "catalog.duckdb").rename(root / "catalog.A.duckdb")
    wal = root / "catalog.duckdb.wal"
    if wal.exists():
        wal.rename(root / "catalog.A.duckdb.wal")
    (root / "active").write_text("A")
    for name in ("catalog.read.duckdb", "read_only.duckdb", "catalog.B.duckdb"):
        assert not (root / name).exists(), name


class _SilentListener:
    """A plain AF_UNIX listener at the daemon socket path that accepts and NEVER replies (the
    spec's busy-leg peer; same shape as the registry's `_SilentDaemon`)."""

    def __init__(self, root: Path):
        from refmatrix import daemon as daemon_mod
        self.path = daemon_mod.socket_path(root)
        if self.path.exists():
            self.path.unlink()
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.bind(str(self.path))
        self.sock.listen(16)
        self.conns: list = []
        self._stop = False
        self.t = threading.Thread(target=self._serve, daemon=True)
        self.t.start()

    def _serve(self):
        while not self._stop:
            try:
                c, _ = self.sock.accept()
            except OSError:
                return
            self.conns.append(c)         # held open, never answered

    def stop(self):
        self._stop = True
        for c in self.conns:
            try:
                c.close()
            except OSError:
                pass
        try:
            self.sock.close()
        except OSError:
            pass
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


@pytest.fixture
def busy_daemon(root):
    """Busy precondition (round-10 #s10-2): the pid file names a LIVE helper whose argv carries
    "rmx", and the socket path is held by a peer that never answers."""
    from refmatrix import daemon as daemon_mod
    helper = h.spawn_rmx_named_helper()
    daemon_mod.pid_path(root).write_text(str(helper.pid))
    peer = _SilentListener(root)
    try:
        yield helper
    finally:
        peer.stop()
        helper.kill()
        helper.wait(timeout=30)
        try:
            daemon_mod.pid_path(root).unlink()
        except FileNotFoundError:
            pass


# ---- busy leg: skipped_budget -----------------------------------------------------------------

def test_ac2b_busy_daemon_skip_writes_one_skipped_budget_recall_row(root, busy_daemon):
    """AC-2b busy leg: `require_daemon`'s VerbBusyError under `budgeted=True` is
    `skipped_budget`. The generated per-prompt recall command exits 0 with `[]`, and the store's
    query.log gains exactly ONE kind=recall row with outcome=skipped_budget, budget_s=5 and the
    envelope's session; recall-events.jsonl gains no event."""
    from refmatrix import discovery
    assert discovery.daemon_status(root, retries=0)["busy"] is True, (
        "busy precondition: the leg must reach require_daemon's busy classification")
    before_rows = len(_recall_rows(root))
    before_events = h.line_count(root / "recall-events.jsonl")

    r = h.run_hook(_recall_cmd(root), root=root, envelope=_envelope(), timeout=120)

    rows = _recall_rows(root)[before_rows:]
    assert len(rows) == 1, (
        f"R3/R4: a skipped recall must still write exactly one kind=recall query.log row; "
        f"got {len(rows)}: {rows}\nstderr={r.stderr[-800:]}")
    row = rows[0]
    assert row["outcome"] == "skipped_budget", row
    assert row["budget_s"] == 5, row
    assert row["session"] == SESSION, row
    assert row.get("query_id"), row
    assert h.line_count(root / "recall-events.jsonl") == before_events, (
        "a skipped call writes NO recall events")
    assert r.returncode == 0, r.stderr
    assert _stdout_is_empty_json(r.stdout), r.stdout


# ---- ok leg: a live sandbox daemon ------------------------------------------------------------

def _seed_memories(root: Path) -> None:
    from refmatrix.store import Store
    s = Store(root)
    try:
        for i in range(3):
            s.add_memory(name=f"feedback_widget_{i}",
                         content=f"the widget parser handles token family {i}",
                         mtype="feedback")
    finally:
        s.close()


def test_ac2b_live_daemon_recall_writes_one_ok_recall_row(root):
    """AC-2b, "the same run against a live sandbox daemon logs outcome=ok": the same generated
    command, served by a real `rmx daemon` on the sandbox root, writes exactly one kind=recall
    row with outcome=ok (`ok`: an answer was rendered, however many items), budget_s=5 and the
    envelope's session."""
    _seed_memories(root)
    before = len(_recall_rows(root))
    with h.SandboxDaemon(root):
        r = h.run_hook(_recall_cmd(root), root=root, envelope=_envelope(), timeout=240)
    rows = _recall_rows(root)[before:]
    assert len(rows) == 1, (
        f"R3: one kind=recall row per recall call; got {len(rows)}: {rows}\n"
        f"stderr={r.stderr[-800:]}")
    assert rows[0]["outcome"] == "ok", rows[0]
    assert rows[0]["budget_s"] == 5, rows[0]
    assert rows[0]["session"] == SESSION, rows[0]
    assert r.returncode == 0, r.stderr


# ---- non-budget leg: a refused connect is `error`, not `skipped_budget` ----------------------

def test_ac2b_non_budget_refused_connect_is_error(root):
    """AC-2b non-budget leg (round-9 #m9-5, round-10 #s10-2, round-11 #s11-1, round-12
    #m12-1). The dispatcher answers `ping` and `partition_list`; on the SECOND `ping` it reads
    the request, closes its LISTENING socket (the socket file stays), and only then replies
    `{"ok": true}` on the accepted connection, so the `memory_recall` connect raises
    ConnectionRefusedError (an OSError: `error` under R4, never `skipped_budget`).
    Asserts: ops == [ping, partition_list, ping]; exactly one kind=recall row, outcome=error,
    `error` starting "ConnectionRefusedError"; no recall event; exit 0 and `[]`."""

    def on_op(op, n, conn, server):
        if op == "ping" and n == 2:
            server.close_listener()                     # close BEFORE replying
            conn.sendall(b'{"ok": true}\n')
            conn.close()
            return True
        return False

    _bootstrap_window(root)
    before_rows = len(_recall_rows(root))
    before_events = h.line_count(root / "recall-events.jsonl")
    with h.OpDispatcher(root, on_op=on_op) as peer:
        r = h.run_hook(_recall_cmd(root), root=root, envelope=_envelope(), timeout=120)
        ops = list(peer.ops)

    assert ops == ["ping", "partition_list", "ping"], (
        f"op sequence drifted (round-11 #s11-1): the leg must reach the recall op's connect; "
        f"got {ops}\nstderr={r.stderr[-800:]}")
    rows = _recall_rows(root)[before_rows:]
    assert len(rows) == 1, (
        f"R3/R4: a degraded recall still writes exactly one kind=recall row; got {len(rows)}: "
        f"{rows}\nstderr={r.stderr[-800:]}")
    assert rows[0]["outcome"] == "error", rows[0]
    assert str(rows[0].get("error") or "").startswith("ConnectionRefusedError"), rows[0]
    assert h.line_count(root / "recall-events.jsonl") == before_events
    assert r.returncode == 0, r.stderr
    assert _stdout_is_empty_json(r.stdout), r.stdout


# ---- mid-answer leg: a peer that closes mid-answer is `error`, never a traceback -------------

def test_ac2b_mid_answer_close_is_error_not_traceback(root):
    """AC-2b mid-answer leg (round-10 #s10-2, round-11 #s11-1). On `memory_recall` the
    dispatcher reads the full request line, then closes without replying, so the client's recv
    sees EOF and `json.loads(b"")` raises JSONDecodeError -- outside HEAD's degrade tuple, so
    the hook dies with a traceback today. Asserts: ops == [ping, partition_list, ping,
    memory_recall]; one kind=recall row, outcome=error, `error` starting "JSONDecodeError";
    exit 0, `[]`, and no traceback on stderr."""

    def on_op(op, n, conn, server):
        if op == "memory_recall":
            conn.close()                                 # request already read; no reply
            return True
        return False

    _bootstrap_window(root)
    before_rows = len(_recall_rows(root))
    before_events = h.line_count(root / "recall-events.jsonl")
    with h.OpDispatcher(root, on_op=on_op) as peer:
        r = h.run_hook(_recall_cmd(root), root=root, envelope=_envelope(), timeout=120)
        ops = list(peer.ops)

    assert ops == ["ping", "partition_list", "ping", "memory_recall"], (
        f"op sequence drifted (round-11 #s11-1); got {ops}\nstderr={r.stderr[-800:]}")
    rows = _recall_rows(root)[before_rows:]
    assert len(rows) == 1, (
        f"R3/R4: a mid-answer close still writes exactly one kind=recall row; got "
        f"{len(rows)}: {rows}\nstderr={r.stderr[-800:]}")
    assert rows[0]["outcome"] == "error", rows[0]
    assert str(rows[0].get("error") or "").startswith("JSONDecodeError"), rows[0]
    assert h.line_count(root / "recall-events.jsonl") == before_events
    assert "Traceback" not in r.stderr, r.stderr[-1500:]
    assert r.returncode == 0, r.stderr
    assert _stdout_is_empty_json(r.stdout), r.stdout


# ---- report legs ------------------------------------------------------------------------------

def _row(**kw) -> dict:
    """A `kind=recall` row as the GREEN writer writes it for the per-prompt hook recall. It
    carries R11's channel flags (`session_start` / `stdin_json` / `recent`): round 13 #b1 --
    every recall row carries them, and a row without them is a writer defect the report
    counts, never classifies. A key set to None is removed (the flagless defect row)."""
    base = {"ts": "2026-10-16T10:00:00", "kind": "recall", "body": PROMPT,
            "source": "memory-recall", "invocation": "hook", "cardinality": None,
            "latency_ms": 10, "outcome": "ok", "error": None, "session": SESSION,
            "query_id": "0" * 32, "cwd": None, "root": None, "budget_s": 5,
            "session_start": False, "stdin_json": True, "recent": False}
    base.update(kw)
    return {k: v for k, v in base.items() if v is not None or k not in _FLAGS}


_FLAGS = ("session_start", "stdin_json", "recent")


def _write_query_log(root: Path, rows: list[dict]) -> None:
    proj = str(root.parent)
    with (root / "query.log").open("a") as f:
        for r in rows:
            r = dict(r)
            r["cwd"] = r["cwd"] or proj
            r["root"] = r["root"] or str(root)
            f.write(json.dumps(r) + "\n")


def _agent_usage(root: Path, *args) -> "h.subprocess.CompletedProcess":
    return h.run_rmx(["telemetry", "--agent-usage", *args], root=root, timeout=120)


def test_ac2b_report_counts_prompt_recall_outcomes(root):
    """AC-2b report leg: `rmx telemetry --agent-usage` over one ok and one skipped_budget
    per-prompt recall row prints `prompt_recall: ok=1 skipped_budget=1 error=0` (R7: per recall
    channel, recomputed from the row by `recall_channel`, the count of each outcome). The rows
    are the shape AC-2b's two hook legs write at GREEN (a `--stdin-json` recall under
    `invocation=hook`, `budget_s=5`); they are written directly so this leg isolates the
    report from the writer. The row's `body`/`source` do not decide the channel -- the spec
    recomputes it from the row's flags, which the fixture carries (round 13 #b1)."""
    _write_query_log(root, [
        _row(outcome="ok", query_id="a" * 32),
        _row(outcome="skipped_budget", query_id="b" * 32),
    ])
    r = _agent_usage(root)
    assert "prompt_recall: ok=1 skipped_budget=1 error=0" in r.stdout, (
        f"R7: per-channel outcome counts missing.\nrc={r.returncode}\nstdout={r.stdout[-1500:]}"
        f"\nstderr={r.stderr[-1500:]}")
    assert r.returncode == 0, r.stderr


def test_ac2b_report_daemon_down_prints_expired_reads_unavailable(root):
    """AC-2b report leg: with no daemon and no listener, `--agent-usage` prints
    `expired_reads: unavailable (daemon down)` -- never `expired_reads: 0` (R7, the
    `_op_stats` `expired_reads` key; mutation: a down daemon printed as 0)."""
    from refmatrix import daemon as daemon_mod
    assert not daemon_mod.socket_path(root).exists()
    _write_query_log(root, [_row(outcome="ok")])
    r = _agent_usage(root)
    assert "expired_reads: unavailable (daemon down)" in r.stdout, (
        f"rc={r.returncode}\nstdout={r.stdout[-1500:]}\nstderr={r.stderr[-1500:]}")
    assert not re.search(r"expired_reads:\s*0\b", r.stdout), r.stdout
    assert r.returncode == 0, r.stderr


def test_ac2b_report_counts_outcome_invalid_rows(root):
    """AC-2b validation leg, report half: a row written by a `log_query` handle given
    `t.outcome = "timeout"` (rewritten by the GREEN writer to outcome=error,
    error="outcome-invalid: timeout") makes `--agent-usage` print `outcome-invalid=1`.

    The row is produced through the real writer when it supports a set `t.outcome`; at HEAD
    the writer ignores it, so the row the GREEN writer would write is appended instead (the
    in-process writer half is the validation unit leg, owned by another file)."""
    from refmatrix import telemetry
    with telemetry.log_query(None, kind="recall", body=PROMPT, source="memory-recall",
                             root=root) as t:
        t.outcome = "timeout"
    rows = [r for r in h.query_rows(root) if r.get("kind") == "recall"]
    if not rows or rows[-1].get("error") != "outcome-invalid: timeout":
        _write_query_log(root, [_row(outcome="error", error="outcome-invalid: timeout",
                                     query_id="c" * 32)])
    r = _agent_usage(root)
    assert "outcome-invalid=1" in r.stdout, (
        f"R4: an outcome outside CALL_OUTCOMES is counted by the report.\nrc={r.returncode}\n"
        f"stdout={r.stdout[-1500:]}\nstderr={r.stderr[-1500:]}")
    assert r.returncode == 0, r.stderr


def test_ac2b_report_counts_a_flagless_recall_row_as_a_writer_defect(root):
    """Round 13 #b1 (R7/R11): a `kind=recall` row WITHOUT `session_start` / `stdin_json` /
    `recent` is a writer defect -- COUNTED on the report (an `unflagged=<n>` count) and put
    in NO recall channel, never guessed from `invocation` / `body`. One flagged per-prompt
    row (ok) and one flagless query-less hook row (skipped_budget, the shape the r1 heuristic
    misread as `precompact`): the channel lines show exactly the flagged row, and the defect
    count is 1. RED at HEAD: `_recall_flags_of` guesses (the flagless row prints a
    `precompact:` outcome line) and nothing counts it."""
    flagless = _row(outcome="skipped_budget", query_id="d" * 32, body="",
                    session_start=None, stdin_json=None, recent=None)
    assert not any(k in flagless for k in _FLAGS), flagless
    _write_query_log(root, [_row(outcome="ok", query_id="e" * 32), flagless])
    r = _agent_usage(root)
    out = r.stdout
    assert r.returncode == 0, r.stderr
    counts = re.findall(r"unflagged=(\d+)", out)
    assert counts == ["1"], (
        f"#b1: the flagless recall row is not counted as a writer defect (unflagged=<n>): "
        f"{counts}\nstdout={out[-1500:]}")
    assert "prompt_recall: ok=1 skipped_budget=0 error=0" in out, out[-1500:]
    chan_lines = [ln.strip() for ln in out.splitlines()
                  if re.match(r"^\s*(session_start|precompact|recall|prompt_recall)\s*:", ln)]
    assert chan_lines == ["prompt_recall: ok=1 skipped_budget=0 error=0"], (
        f"#b1: a flagless row was classified into a channel: {chan_lines}")
