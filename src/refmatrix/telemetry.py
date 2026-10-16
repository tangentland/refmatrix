"""
Query telemetry. JSONL append-only log at `.refmatrix/query.log`.

One record per query, fields:
    ts            ISO-8601 timestamp
    kind          'dsl' | 'pql' | 'neighbors' | 'co-occur' | 'top' | 'context' | 'scan'
    body          query string or anchor symbol
    source        the SURFACE that answered ('scan-prompt', 'grep-replica', ...)
    invocation    WHO asked: 'hook' | 'interactive' | 'mcp' | 'internal' | 'unknown'
                  (absent on rows written before 2026-09-15; readers default it)
    cardinality   integer for bitmap results, null otherwise
    latency_ms    elapsed milliseconds
    outcome       'ok' | 'empty' | 'consumer-closed' | 'error' — WHICH of the
                  four things happened (absent before 2026-09-20; readers
                  classify those rows from `error`/`exit_code`)
    answered_by   grep rows only: WHAT produced the answer — see ANSWERED_BY.
                  Absent before 2026-10-05 and NOT recoverable for those rows
                  (the paths that decide eligibility were never logged), so
                  readers report them as 'unknown' and never as 'floor'
    learn         grep rows only: the EFFECTIVE learning state of the call, so
                  a replayed log says which arm wrote the row
    error         "ExcType: msg" if the query FAILED, else null. A no-match
                  exit and a closed consumer are conventions, not failures,
                  and live in `outcome` (bug-052)

Disable by setting `REFMATRIX_NO_TELEMETRY=1` in the env.

Use the `log_query` context manager:

    with log_query(store, kind="dsl", body=expr, source="query") as t:
        result = qe.run(expr)
        t.cardinality = len(result)
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
import time
import uuid
from collections import Counter
from pathlib import Path
import typing
from typing import Any

from refmatrix.store import Store


LOG_NAME = "query.log"
CLI_LOG_NAME = "cli.log"

# Recognized invocation "forms" — how an `rmx` call entered the system.
# `hook`        — fired by a Claude Code / git hook (set RMX_INVOCATION_SOURCE=hook)
# `interactive` — a human typed it at a tty
# `mcp`         — issued through the hub MCP server
# `internal`    — daemon/subprocess fan-out, eval harnesses
# `agent`       — run under Claude Code (`CLAUDECODE` set) with no explicit
#                 source: an agent's Bash call. Task 21.1 R2 (2026-10-14): the
#                 exploration found `invocation` = `unknown` on all 1,119 agent
#                 greps of its window, because an agent's Bash call has no tty
#                 and no hint, so agent adoption could not be counted at all.
# `unknown`     — pre-source-field logs, or no tty + no hint
INVOCATION_SOURCES = ("hook", "interactive", "mcp", "internal", "agent", "unknown")


# What actually happened on a logged call. `error` is reserved for the LAST
# one; the first three are conventions, not failures (bug-052).
#
# `grep-replica` showed 278 "errors" in query.log. 256 were `SystemExit: 1` —
# grep's no-match exit, which `rmx grep` honours on purpose — and 22 were
# `BrokenPipeError`, a downstream `| head` closing the pipe. Real failures were
# about six. cli.log carried the same distortion from the other side:
# `error_rate` counted every nonzero exit. The reader who found bug-049 had to
# dismiss 272 rows by hand before the signal was visible.
OUTCOMES = ("ok", "empty", "consumer-closed", "error")

# THE outcome vocabulary of a `query.log` row (task 21.1 R4, round-9 #m9-5):
# the four bug-052 values plus `skipped_budget` — a call whose budget expired
# before an answer (the per-prompt recall hook degrades to `[]` and exit 0
# under load; since bug-116 the daemon drops the queued read too). Without it a
# skipped prompt read as "recall ran and delivered 0".
CALL_OUTCOMES = ("ok", "empty", "consumer-closed", "error", "skipped_budget")

# Per-kind outcome vocabularies (round-10 #m10-4). Empty here on purpose: every
# kind validates against CALL_OUTCOMES until a kind needs its own (21.3 R3 adds
# `nudge`). `log_query` validates the final outcome against
# `OUTCOMES_BY_KIND.get(kind, CALL_OUTCOMES)` at WRITE time.
OUTCOMES_BY_KIND: "dict[str, tuple[str, ...]]" = {}


# WHAT answered a grep. Five-valued, and the reason it is not a boolean is the
# whole shape of the instrument: `cli._index_may_answer(paths)` is `not paths`,
# so a drop-in read that NAMES files can never be served from the learned index
# (bug-058 — a learned index answered with 1000 rows covering ~100 of a file's
# 500 matching lines). `index|floor` alone would therefore score every CORRECT
# drop-in read as a learning miss, and the loop would look dead exactly where
# the tool floor is the right answer.
#
#   index   the learned index answered
#   floor   the index was ELIGIBLE, had nothing, and rg/grep answered. The only
#           bucket whose rate the learning loop can move, and the denominator
#           any claim about learning has to use
#   dropin  paths were named; the index was never eligible. Not a miss
#   stdin   a grep reading a pipe: a filter, byte-exact, consults nothing
#   none    eligible, empty, --no-fallback — nothing answered
ANSWERED_BY = ("index", "floor", "dropin", "stdin", "none")

# A grep row whose producer never set the field. Written LOUDLY rather than
# omitted: an omitted field is indistinguishable from a pre-2026-10-05 row, so
# a future render path that forgets to label itself would read as history
# instead of as the hole it is.
ANSWERED_BY_UNSET = "unset"


def _budget_exception_types() -> tuple:
    """The exception types a BUDGETED call classifies as `skipped_budget`:
    `VerbBusyError` (every source of it reaches the recall hook's degrade path:
    `_left`'s deadline, the replica leg, `require_daemon`'s busy daemon) and the
    two timeouts. Imported lazily: verbs imports telemetry."""
    import socket
    from refmatrix.verbs import VerbBusyError
    return (VerbBusyError, TimeoutError, socket.timeout)


def _error_text(exc_type, exc_val) -> str:
    return f"{getattr(exc_type, '__name__', exc_type)}: {exc_val}"


def classify_outcome(exc_type, exc_val, *, budgeted: bool = False
                     ) -> "tuple[str, str | None]":
    """Map how a logged call ended onto (outcome, error).

    `error` is non-None only for the `error` outcome, so a reader counting
    `error` rows counts failures and nothing else. The other two exits keep
    their evidence in `outcome` — they are not dropped, they are named.

    `budgeted=True` is the recall hook's degrade path (task 21.1 R4, rounds
    9-12): the path catches `(VerbBusyError, TimeoutError, socket.timeout,
    OSError, json.JSONDecodeError)`, so "it degraded" is not "its budget ran
    out" — a refused or reset connection degrades too. Classified by TYPE: a
    busy daemon or a timeout is `skipped_budget`; any other `OSError` (tested
    BEFORE the BrokenPipeError mapping, so a daemon-socket broken pipe is an
    `error`, never `consumer-closed`) and anything else is `error`. The verb
    (MCP) route classifies unbudgeted by design: `verbs._call` wraps every
    transport exception as `VerbBusyError`, and an MCP call carries no hook
    budget (round-11 #m11-6)."""
    if exc_type is None:
        return ("ok", None)
    if budgeted and isinstance(exc_type, type):
        # Timeouts first: TimeoutError and socket.timeout ARE OSErrors, so the
        # generic OSError test below would swallow them (round-12 #m12-2).
        if issubclass(exc_type, _budget_exception_types()):
            return ("skipped_budget", None)
        if issubclass(exc_type, OSError):
            return ("error", _error_text(exc_type, exc_val))
    if isinstance(exc_type, type) and issubclass(exc_type, SystemExit):
        code = getattr(exc_val, "code", None)
        if code is None or code == 0:
            return ("ok", None)
        if code == 1:
            # The command's own "nothing to report" exit: grep's no-match
            # contract, which `_grep_rg_fallback` raises deliberately after
            # printing the stderr note. `cardinality: 0` carries the detail.
            return ("empty", None)
        return ("error", f"SystemExit: {code}")
    if isinstance(exc_type, type) and issubclass(exc_type, BrokenPipeError):
        # `rmx grep ... | head -5`: head exits, the pipe closes, we raise. We
        # did the work; the reader stopped reading.
        return ("consumer-closed", None)
    return ("error", _error_text(exc_type, exc_val))


def _outcome_of(row: dict) -> str:
    """The outcome of a row, classified on READ for the rows written before
    the field existed. Rewriting the logs is not on the table — re-reading
    them by the same rules is what makes the historical rate honest."""
    known = row.get("outcome")
    if known in CALL_OUTCOMES:
        return known
    err = row.get("error")
    if err:
        head = str(err).split(":", 1)[0].strip()
        if head == "SystemExit":
            tail = str(err).split(":", 1)[1].strip() if ":" in str(err) else ""
            if tail in ("0", "None", ""):
                return "ok"
            return "empty" if tail == "1" else "error"
        if head == "BrokenPipeError":
            return "consumer-closed"
        return "error"
    code = row.get("exit_code")
    if isinstance(code, int) and code != 0:
        # A cli.log row with no exception recorded: exit 1 is the empty
        # convention, anything higher is a real failure.
        return "empty" if code == 1 else "error"
    return "ok"


def _disabled() -> bool:
    return os.environ.get("REFMATRIX_NO_TELEMETRY") in ("1", "true", "yes")


def invocation_source() -> str:
    """Classify *how* this `rmx` call was invoked — the telemetry "form" axis.

    Precedence (task 21.1 R2, decision-log #m-2), first match wins:
      1. explicit `RMX_INVOCATION_SOURCE` (hooks: `hook`; MCP: `mcp`;
         harnesses: `internal`);
      2. `CLAUDECODE` set → `agent` (an agent's Bash call has no tty and no
         hint; before 2026-10-14 every one of them logged `unknown`);
      3. stdin is a tty → `interactive`;
      4. otherwise `unknown`.
    Stated consequences: a `!`-typed human command inside Claude Code logs
    `agent`, and a bare grep the grep-rewrite-guard rewrote to `rmx grep` logs
    `agent` although the agent never chose rmx — adoption reads separate
    chosen calls by `source`, never by `invocation` alone. Always returns a
    member of INVOCATION_SOURCES."""
    src = os.environ.get("RMX_INVOCATION_SOURCE")
    if src:
        src = src.strip().lower()
        return src if src in INVOCATION_SOURCES else "unknown"
    if os.environ.get("CLAUDECODE"):
        return "agent"
    try:
        if sys.stdin is not None and sys.stdin.isatty():
            return "interactive"
    except (ValueError, OSError):
        pass
    return "unknown"


class CountingStream(io.TextIOBase):
    """A transparent `sys.stdout` proxy that counts the BYTES written through it.

    This exists to answer a question the project could not previously ask: what
    does rmx charge the model's context window? Three hooks fire on every prompt
    and each writes its output straight into that window, and until 2026-09-15
    the telemetry recorded only how LONG they took.

    Counting happens here, once, wrapped around stdout in `cli_entry` — never at
    the individual renderers. It covers every command uniformly, and there is one
    copy of the logic instead of one per render site, which is the shape of bug
    `feedback_reuse_shared_stoplist` records (one junk-token defect, four call
    sites, because each grew its own copy).

    WHAT THIS IS AND IS NOT. `out_bytes` is **the bytes this process wrote to
    stdout** — measured, byte-exact, verified across eight renderers. It is NOT
    "what the hook injected", which an earlier version of this docstring claimed
    and which is false in both directions (ch-bsd r1 #s-11):

      * OVER-counts. Four installed hooks redirect stdout to `/dev/null`
        (`sync --flush-queue` x3, `primer --out`). A hook-env `rmx stats
        >/dev/null` logs its full 1,536 B and nothing was injected.
      * UNDER-counts. `grep-tool-teach.sh`, `enforce-test-to-file.sh`,
        `enforce-rmx-grep.sh`, `grep-rewrite-guard.sh` and
        `compile_guardrails.py` inject their own stdout and never reach
        `cli.log` at all — they are not `rmx` invocations.

    Treat the hook budget as a bound on what rmx COMMANDS emitted, not as the
    context window's actual intake.

    TRANSPARENCY IS LOAD-BEARING. `rich.Console` branches on `isatty()` to pick
    colour and width, so a proxy that misreported ttyness would change the very
    bytes it exists to measure. `encoding`, `flush()` and `fileno()` pass
    through for the same reason. (Verified 2026-09-15 that rich resolves
    `sys.stdout` lazily at write time, so a Console created at import — as
    `cli.console` is — picks up a wrapper installed afterwards.)
    """

    def __init__(self, inner):
        self._inner = inner
        self._out_bytes = 0

    @property
    def out_bytes(self) -> int:
        return self._out_bytes

    def write(self, s):
        # BYTES, not characters: a UTF-8 prompt would otherwise under-count.
        try:
            self._out_bytes += len(s.encode("utf-8", "replace"))
        except Exception:
            pass                      # never let accounting break the write
        return self._inner.write(s)

    def flush(self):
        return self._inner.flush()

    def isatty(self):
        try:
            return self._inner.isatty()
        except Exception:
            return False

    def fileno(self):
        return self._inner.fileno()

    def writable(self):
        return True

    @property
    def encoding(self):
        return getattr(self._inner, "encoding", "utf-8")

    @property
    def errors(self):
        return getattr(self._inner, "errors", None)

    def __getattr__(self, item):
        # Anything not modelled above (buffer, line_buffering, ...) belongs to
        # the wrapped stream. A missing attribute here would be a behaviour
        # change dressed as telemetry.
        return getattr(self._inner, item)


def log_cli_invocation(
    root: Path,
    *,
    argv: list[str],
    cwd: str,
    exit_code: int,
    latency_ms: int,
    error: str | None,
    pid: int,
    out_bytes: "int | None" = None,
    outcome: "str | None" = None,
) -> None:
    """Append one JSONL record for an `rmx` CLI invocation to .refmatrix/cli.log.

    `out_bytes` is what this invocation wrote to stdout. NOT necessarily what a
    hook injected — a redirected hook over-counts and a non-rmx hook is absent
    entirely; see `CountingStream` (ch-bsd r1 #s-11). Optional, because callers
    that did not wrap stdout have nothing to report, and a row without it is
    UNKNOWN rather than free (readers must not average it in as a zero).

    Best-effort: silently skips if .refmatrix/ doesn't exist (e.g. `rmx init`
    invoked outside any project) or if write fails.
    """
    if _disabled():
        return
    if not root.is_dir():
        return
    record: dict[str, Any] = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "argv": argv,
        "cwd": cwd,
        "exit_code": exit_code,
        "latency_ms": latency_ms,
        # WHICH of the four things happened (bug-052). Omitted by a caller
        # that does not know, and then classified on read from `exit_code`.
        "outcome": outcome,
        "error": error,
        "pid": pid,
        "source": invocation_source(),
        "out_bytes": out_bytes,
        # Deliberately an ESTIMATE and named as one. The decision this drives is
        # "is a hook spending 400 bytes or 40 KB", where a 20% error changes
        # nothing; pulling in a tokenizer to make a ratio look precise is the
        # expensive kind of false rigor. A field named `_est` cannot be quoted
        # as exact by accident.
        "out_tokens_est": (out_bytes // 4) if out_bytes is not None else None,
    }
    try:
        with (root / CLI_LOG_NAME).open("a") as f:
            f.write(json.dumps(record) + "\n")
    except OSError:
        pass


def log_cli_intent(
    root: Path,
    *,
    op: str,
    argv: list[str],
    pid: int,
) -> None:
    """Persist the intent of an `rmx memory` invocation to cli.log BEFORE
    the command body runs. Pairs with the end-of-run record written by
    cli_entry's finally block. If the daemon crashes or the process is
    killed mid-op (the failure mode that motivated this — DuckDB SIGABRT
    under memory upsert), the start record survives and lets a recovery
    pass reconstruct what was intended.

    Schema: {"ts", "phase": "start", "op", "argv", "pid"}. The end-phase
    record from log_cli_invocation has no `phase` key, so a reader can
    pair (start, end) by pid + closest ts."""
    if _disabled():
        return
    if not root.is_dir():
        return
    record: dict[str, Any] = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "phase": "start",
        "op": op,
        "argv": argv,
        "pid": pid,
        "source": invocation_source(),
    }
    try:
        with (root / CLI_LOG_NAME).open("a") as f:
            f.write(json.dumps(record) + "\n")
            f.flush()
    except OSError:
        pass


class _Unresolved:
    def __repr__(self) -> str:
        return "SESSION_UNRESOLVED"


# Sentinel: "resolve the row's session at __exit__". Distinct from None, which
# is a RESOLVED answer ("nothing resolves") the row must carry as null.
SESSION_UNRESOLVED = _Unresolved()


def resolve_event_session(root: "Path | None", envelope: "dict | None" = None
                          ) -> "str | None":
    """The session a telemetry row or recall event carries: R9's ONE resolver
    with `purpose="event"` (null when nothing resolves — never the newest
    ring). Telemetry never fails the command it describes, so a resolver that
    raises is said on stderr and the row carries null.

    A miss is recorded in the pointer-error log only for a call Claude Code's
    machinery made (`invocation` hook / mcp / agent). A call that classifies
    `unknown` or `interactive` — a human's pipe, a harness — is a plain-terminal
    call for R9's purposes: its row still carries the resolved session (or
    null), and recording a "miss" for it would put a row in the log for every
    piped `rmx` a human runs (task 21.1 AC-4b (xiii): prose piped to
    scan-prompt adds no row)."""
    if root is None:
        return None
    try:
        from refmatrix import verbs
        return verbs.resolve_session_source(
            Path(root), None, envelope=envelope, purpose="event",
            record_miss=invocation_source() in ("hook", "mcp", "agent")).session
    except Exception as e:  # noqa: BLE001 — telemetry must not fail the command
        print(f"rmx: telemetry session not resolved: {type(e).__name__}: {e}",
              file=sys.stderr)
        return None


class log_query:
    """Context manager that times its body and appends a JSONL telemetry record."""

    def __init__(
        self,
        store: "Store | None",
        *,
        kind: str,
        body: str,
        source: str = "cli",
        root: "Path | None" = None,
        session: "str | None | object" = SESSION_UNRESOLVED,
        query_id: "str | None" = None,
        budget_s: "float | None" = None,
    ):
        self.store = store
        self.kind = kind
        self.body = body
        self.source = source
        # Task 21.1 R4 (2026-10-14): a row carried no session, no query id and
        # no cwd, so no per-session count could be computed and no recall event
        # could be joined to its query. `session=SESSION_UNRESOLVED` (the
        # default) resolves it at __exit__ through R9's ONE resolver with
        # `purpose="event"`; a caller that already resolved it for the same
        # call (the recall and scan emitters, whose events share the row's
        # session) passes it, so one call records at most one resolver miss.
        self.session = session
        # Minted ONCE per call; the recall events of the call carry the same id.
        self.query_id = query_id or uuid.uuid4().hex
        self.budget_s = budget_s
        # A path that ends the call without an exception (the recall hook's
        # degrade path returns `[]` and exit 0) sets these; __exit__ then uses
        # them in place of its own classification (R4).
        self.outcome: "str | None" = None
        self.error: "str | None" = None
        # Kind-specific fields the caller wants on the row (recall flags, the
        # used-lookup counters), merged last.
        self.extra: dict = {}
        # Telemetry needs a DIRECTORY, not a database. `root` lets the paths
        # that legitimately hold no Store still be recorded: the stdin filter
        # (which returns before any store resolution, by design — a filter must
        # not pay for an attach) and the daemon-RPC-served grep, whose rows were
        # dropped entirely by the `store is None` guard below. That silent drop
        # is why the 1,536 grep rows in this project's log are a partial census
        # of greps rather than all of them.
        # A CALLABLE is allowed and is what the stdin filter passes: resolving
        # the store root costs a cwd walk (and, under ~/.claude/projects, a
        # `discovery.discover_roots()`), and a grep reading a pipe must not pay
        # that before answering. Resolved at __exit__, after the bytes are out.
        self.root = root if (root is None or callable(root)) else Path(root)
        self.cardinality: int | None = None
        # grep only; see ANSWERED_BY. Set by whichever branch produces the
        # answer, and left None by every other kind of query.
        self.answered_by: str | None = None
        self.learn: bool | None = None
        self.t0: float = 0.0

    def _log_dir(self) -> "Path | None":
        if self.store is not None:
            return self.store.root
        if callable(self.root):
            try:
                r = self.root()
            except Exception:
                return None      # telemetry never fails the command it describes
            return Path(r) if r is not None else None
        return self.root

    def __enter__(self) -> "log_query":
        self.t0 = time.monotonic()
        return self

    def __exit__(self, exc_type, exc_val, _exc_tb) -> None:
        if _disabled():
            return
        log_dir = self._log_dir()
        if log_dir is None:
            # No store AND no root: nowhere to append the record. Callers on
            # the RPC-served and stdin paths pass `root=` so they land in the
            # log rather than vanishing. Previously a store-less call raised
            # AttributeError out of __exit__.
            return
        latency_ms = int((time.monotonic() - self.t0) * 1000)
        # `invocation` is WHO asked (hook / interactive / mcp / internal);
        # `source` is WHICH SURFACE answered (scan-prompt / grep-replica / ...).
        # Two different axes, deliberately two different keys — `cli.log` uses
        # `source` for the form, and overloading the name across the two logs
        # would make every later join silently wrong.
        #
        # Added 2026-09-15 (plan-9). The field's absence is what stopped the
        # `brief/unanswered` confound gate: 174 of 465 zero-result rows came
        # from the always-on scan-prompt hook firing on "yes" and "go", and
        # nothing on the row could say so.
        try:
            form = invocation_source()
        except Exception:
            # Telemetry never fails the command it describes.
            form = "unknown"
        # `outcome` says WHICH of the four things happened; `error` is reserved
        # for the failure. Before bug-052 every exception landed in `error`, so
        # grep's no-match exit and a closed pipe read as failures.
        if self.outcome is not None:
            outcome, error = self.outcome, self.error
        else:
            outcome, error = classify_outcome(exc_type, exc_val)
        # Validated where it is written (task 21.1 R4, round-9 #m9-5): a value
        # outside the vocabulary is never silently kept or dropped.
        if outcome not in OUTCOMES_BY_KIND.get(self.kind, CALL_OUTCOMES):
            outcome, error = "error", f"outcome-invalid: {outcome}"
        session = self.session
        if session is SESSION_UNRESOLVED:
            session = resolve_event_session(log_dir)
        try:
            cwd = os.getcwd()
        except OSError:
            cwd = None
        record: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "kind": self.kind,
            "body": self.body,
            "source": self.source,
            "invocation": form,
            "cardinality": self.cardinality,
            "latency_ms": latency_ms,
            "outcome": outcome,
            "error": error,
            # R4: joinable per session and per call, and attributable (R5).
            "session": session,
            "query_id": self.query_id,
            "cwd": cwd,
            "root": str(log_dir),
        }
        if self.kind in ("recall", "context"):
            # The call's budget (`--timeout`), or null when it has none, so a
            # `skipped_budget` row says what it was skipped against.
            record["budget_s"] = self.budget_s
        if self.kind == "grep":
            # Always present on a grep row, even when no branch set it: see
            # ANSWERED_BY_UNSET. The field is what makes "did the index answer
            # this?" answerable at all, so a missing label is a defect to
            # surface, not a value to omit.
            record["answered_by"] = (
                self.answered_by if self.answered_by in ANSWERED_BY
                else ANSWERED_BY_UNSET
            )
            record["learn"] = self.learn
        elif self.answered_by is not None:
            record["answered_by"] = self.answered_by
        record.update(self.extra)
        try:
            with (log_dir / LOG_NAME).open("a") as f:
                f.write(json.dumps(record) + "\n")
        except OSError:
            pass


# ---- analysis -------------------------------------------------------------


def read_log(store: Store, since: str | None = None) -> list[dict]:
    """Read the JSONL log, oldest first. `since` filters by ISO timestamp prefix."""
    p = store.root / LOG_NAME
    if not p.exists():
        return []
    out: list[dict] = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if since and r.get("ts", "") < since:
            continue
        out.append(r)
    return out


def summarize(store: Store, since: str | None = None) -> dict:
    """Compute the headline stats from the telemetry log."""
    rows = read_log(store, since=since)
    if not rows:
        return {"total": 0}

    total = len(rows)
    by_kind = Counter(r.get("kind", "?") for r in rows)
    by_source = Counter(r.get("source", "?") for r in rows)
    # Months of rows predate `invocation` (added 2026-09-15). They are UNKNOWN,
    # not absent: defaulting here is what keeps the pre-field baseline readable.
    by_invocation = Counter(r.get("invocation") or "unknown" for r in rows)
    body_counter = Counter(r.get("body", "") for r in rows)
    zero = [r for r in rows if r.get("cardinality") == 0]
    # Classified on read, so the months of rows written before `outcome`
    # existed are counted by the same rules (bug-052).
    by_outcome = Counter(_outcome_of(r) for r in rows)
    errors = [r for r in rows if _outcome_of(r) == "error"]
    # GREP rows only — the field is meaningless on a scan or a dsl query, and
    # mixing them would inflate whatever denominator a reader picks. Rows
    # written before 2026-10-05 report as `unknown` and are NOT folded into
    # `floor`: the paths that decide eligibility were never logged, so their
    # bucket is unrecoverable, and guessing it would manufacture the exact
    # number the field was added to measure.
    by_answered_by = Counter(
        r.get("answered_by") or "unknown"
        for r in rows if r.get("kind") == "grep"
    )

    latencies = [r["latency_ms"] for r in rows if isinstance(r.get("latency_ms"), int)]
    latencies.sort()

    def pct(p: float) -> int:
        if not latencies:
            return 0
        idx = min(len(latencies) - 1, int(p * len(latencies)))
        return latencies[idx]

    return {
        "total": total,
        "by_kind": dict(by_kind),
        "by_source": dict(by_source),
        "top_queries": body_counter.most_common(20),
        "by_invocation": dict(by_invocation),
        "zero_by_invocation": dict(
            Counter(r.get("invocation") or "unknown" for r in zero)),
        "zero_result_count": len(zero),
        "zero_result_examples": [r["body"] for r in zero[-10:]],
        "by_outcome": dict(by_outcome),
        "by_answered_by": dict(by_answered_by),
        "error_count": len(errors),
        "error_examples": [
            {"body": r["body"], "error": r["error"]} for r in errors[-5:]
        ],
        "latency_p50_ms": pct(0.50),
        "latency_p95_ms": pct(0.95),
        "latency_p99_ms": pct(0.99),
    }


def read_cli_log(root: Path, since: str | None = None) -> list[dict]:
    """Read .refmatrix/cli.log JSONL, oldest first. `since` filters by ISO ts prefix."""
    p = root / CLI_LOG_NAME
    if not p.exists():
        return []
    out: list[dict] = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if since and r.get("ts", "") < since:
            continue
        out.append(r)
    return out


def _subcommand_of(argv: list[str]) -> str:
    """Bucket an argv list to its `rmx` subcommand, skipping global flags."""
    sub = argv[0] if argv else "<no-args>"
    if sub in ("--version", "-V", "-h", "--help") and len(argv) > 1:
        sub = argv[1]
    return sub


def _aggregate_cli_rows(rows: list[dict]) -> dict:
    """Shared cli.log aggregation. `phase=='start'` intent markers are skipped
    (they pair with an end record — counting both double-counts memory ops)."""
    sub_counter: Counter[str] = Counter()
    argv_counter: Counter[str] = Counter()
    cwd_counter: Counter[str] = Counter()
    source_counter: Counter[str] = Counter()
    exit_counter: Counter[int] = Counter()
    outcome_counter: Counter[str] = Counter()
    errors: list[dict] = []
    latencies: list[int] = []
    total = 0

    for r in rows:
        if r.get("phase") == "start":
            continue
        total += 1
        argv = r.get("argv") or []
        sub_counter[_subcommand_of(argv)] += 1
        argv_counter[" ".join(argv) if argv else "<no-args>"] += 1
        cwd_counter[r.get("cwd") or "?"] += 1
        source_counter[r.get("source") or "unknown"] += 1
        code = r.get("exit_code", 0)
        if isinstance(code, int):
            exit_counter[code] += 1
        outcome = _outcome_of(r)
        outcome_counter[outcome] += 1
        if outcome == "error":
            errors.append({"argv": argv,
                           "error": r.get("error") or f"exit {code}",
                           "ts": r.get("ts")})
        lat = r.get("latency_ms")
        if isinstance(lat, int):
            latencies.append(lat)

    latencies.sort()

    def pct(p: float) -> int:
        if not latencies:
            return 0
        idx = min(len(latencies) - 1, int(p * len(latencies)))
        return latencies[idx]

    nonzero_exits = sum(c for code, c in exit_counter.items() if code != 0)

    return {
        "total": total,
        "by_subcommand": dict(sub_counter.most_common()),
        "by_source": dict(source_counter.most_common()),
        "top_invocations": argv_counter.most_common(20),
        "by_cwd": cwd_counter.most_common(10),
        "exit_codes": dict(exit_counter),
        "by_outcome": dict(outcome_counter),
        "error_count": len(errors),
        # FAILURES over calls. It was nonzero-exits over calls, which counted
        # every no-match `rmx grep` as a failed command (bug-052). The raw
        # fact keeps its own key rather than being dropped.
        "error_rate": (len(errors) / total) if total else 0.0,
        "nonzero_exit_rate": (nonzero_exits / total) if total else 0.0,
        "error_examples": errors[-5:],
        "latency_p50_ms": pct(0.50),
        "latency_p95_ms": pct(0.95),
        "latency_p99_ms": pct(0.99),
        "latency_max_ms": latencies[-1] if latencies else 0,
    }


def summarize_cli_log(root: Path, since: str | None = None) -> dict:
    """Headline stats for cli.log: invocation counts by subcommand, by source
    (form), error rate, latency percentiles, top exact-argv invocations."""
    rows = read_cli_log(root, since=since)
    if not rows:
        return {"total": 0}
    return _aggregate_cli_rows(rows)


def summarize_all(roots, since: str | None = None) -> dict:
    """Cross-project roll-up of cli.log across every known store. Answers
    "how much / in which form / which projects is rmx used". `roots` is an
    iterable of `.refmatrix` dir paths."""
    combined: list[dict] = []
    by_project: dict[str, int] = {}
    for root in roots:
        root = Path(root)
        rows = read_cli_log(root, since=since)
        real = [r for r in rows if r.get("phase") != "start"]
        if not real:
            continue
        name = root.resolve().parent.name or str(root)
        by_project[name] = by_project.get(name, 0) + len(real)
        combined.extend(rows)

    if not combined:
        return {"total": 0, "by_project": {}}

    agg = _aggregate_cli_rows(combined)
    agg["by_project"] = dict(
        sorted(by_project.items(), key=lambda kv: kv[1], reverse=True)
    )
    return agg


def read_query_log(root: Path, since: str | None = None) -> list[dict]:
    """Read .refmatrix/query.log by root (no Store needed). Oldest first."""
    p = root / LOG_NAME
    if not p.exists():
        return []
    out: list[dict] = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if since and r.get("ts", "") < since:
            continue
        out.append(r)
    return out


# Commands worth nudging toward — high-value reads that prove the graph is
# being used for more than ingest plumbing.
_HIGH_VALUE_CMDS = ("context", "memory", "concept", "where", "query")


def adoption_report(
    root: Path,
    *,
    stats: dict | None = None,
    daemon_up: bool | None = None,
    launchd_installed: bool | None = None,
    since: str | None = None,
) -> list[dict]:
    """Integration-refinement signals for one store. Log-derived signals are
    computed here; operational facts (entity counts, daemon/launchd state) are
    passed in by the caller so this stays import-light and unit-testable.

    Returns a list of `{kind, severity, message, fix_action?}`, highest
    severity first."""
    signals: list[dict] = []
    cli = summarize_cli_log(root, since=since)
    by_sub = cli.get("by_subcommand", {})
    by_source = cli.get("by_source", {})

    if daemon_up is False:
        signals.append({
            "kind": "daemon_down",
            "severity": "high",
            "message": "Daemon is not running for this store.",
            "fix_action": "daemon start",
        })
    if launchd_installed is False:
        signals.append({
            "kind": "unsupervised",
            "severity": "medium",
            "message": "Daemon is not supervised (no launchd plist); it won't restart on crash/login.",
            "fix_action": "daemon launchctl install",
        })

    if stats is not None:
        ents = stats.get("entities") or {}
        total_ents = sum(v for v in ents.values() if isinstance(v, int))
        if total_ents == 0:
            signals.append({
                "kind": "never_ingested",
                "severity": "high",
                "message": "Store is registered but holds no entities — nothing has been ingested.",
                "fix_action": "ingest .",
            })
        stale = stats.get("stale_files") or []
        if isinstance(stale, list) and len(stale) >= 10:
            signals.append({
                "kind": "stale",
                "severity": "medium",
                "message": f"{len(stale)} tracked files are stale or missing.",
                "fix_action": "sync",
            })

    if cli.get("total", 0) > 0 and by_source.get("hook", 0) == 0:
        signals.append({
            "kind": "no_hooks",
            "severity": "medium",
            "message": "No hook-driven invocations recorded — rmx isn't wired into your Claude/git hooks.",
            "fix_action": "install-hooks",
        })

    q = read_query_log(root, since=since)
    real_q = [r for r in q if r.get("kind") != "scan"]
    if real_q:
        zero = sum(1 for r in real_q if r.get("cardinality") == 0)
        rate = zero / len(real_q)
        if rate >= 0.30 and zero >= 5:
            signals.append({
                "kind": "high_zero_result",
                "severity": "medium",
                "message": f"{rate:.0%} of lookups return nothing — the index likely misses what you search for.",
                "fix_action": "ingest . --semantic",
            })

    if cli.get("total", 0) >= 20:
        unused = [c for c in _HIGH_VALUE_CMDS if by_sub.get(c, 0) == 0]
        if unused:
            signals.append({
                "kind": "underused_reads",
                "severity": "low",
                "message": "High-value commands never used: " + ", ".join(unused)
                + ". These turn the index into answers, not just storage.",
                "fix_action": None,
            })

    order = {"high": 0, "medium": 1, "low": 2}
    signals.sort(key=lambda s: order.get(s.get("severity", "low"), 3))
    return signals


def top_queried_concepts(store: Store, limit: int = 20) -> list[tuple[str, int]]:
    """Most-queried *concepts* — extracts symbols out of `context` / `neighbors` /
    `co-occur` / `top` calls (where body == concept name) and counts them.

    DSL/PQL bodies are skipped — we'd need to parse them to extract concepts,
    and the value of this signal comes from the higher-level lookups anyway.
    """
    rows = read_log(store)
    sym_counter: Counter[str] = Counter()
    for r in rows:
        if r.get("kind") in ("context", "neighbors", "co-occur", "top"):
            body = r.get("body") or ""
            if body and "AND" not in body and "OR" not in body:
                sym_counter[body] += 1
    return sym_counter.most_common(limit)


def zero_result_queries(store: Store, limit: int = 20) -> list[tuple[str, int]]:
    """Queries that returned cardinality 0 — gaps to fill.

    Excludes kind="scan" rows: those are raw UserPromptSubmit bodies logged
    for provenance, not real lookups; their zero-result rate is meaningless.
    """
    rows = read_log(store)
    counter: Counter[str] = Counter()
    for r in rows:
        if r.get("kind") == "scan":
            continue
        if r.get("cardinality") == 0:
            counter[r.get("body") or "?"] += 1
    return counter.most_common(limit)



# The commands only a UserPromptSubmit firing produces. `source == "hook"`
# alone is every hook event in the system (ch-bsd r1 #b-7).
PROMPT_ANCHORS = frozenset({"scan-prompt"})


def _command_groups() -> "frozenset[str]":
    """Names of click GROUPS (`memory`, `daemon`, ...) — commands whose second
    argv token is a subcommand rather than a value. Read from the CLI tree so
    this cannot drift as commands are added. An import failure degrades to a
    small static set rather than mis-grouping everything."""
    try:
        from refmatrix.cli import main as _main
        return frozenset(
            name for name, cmd in _main.commands.items()
            if hasattr(cmd, "commands"))
    except Exception:
        return frozenset({"memory", "daemon", "hub", "focus", "bus", "session",
                          "task", "queue", "subject", "flag"})

def summarize_context(root: Path, *, since: "str | None" = None,
                      window_s: int = 5) -> dict:
    """What rmx charged the model's context window, from `cli.log`.

    Answers the question the project could not previously ask. Three hooks fire
    on every prompt and each writes its output straight into the window; until
    plan-9 the telemetry recorded only how long they took. `out_bytes` is the
    real payload — the bytes this process wrote to stdout, which is exactly what
    the hook captured and injected.

    TWO RULES THIS FUNCTION EXISTS TO ENFORCE:

    **A row without `out_bytes` is UNKNOWN, not free.** Months of history
    predate the field. Averaging those in as zeros would halve every figure and
    make the surface look cheap, so they are excluded from the counted set and
    reported separately as `uncounted`. A reader who sees a small mean and a
    large `uncounted` knows not to trust the mean.

    **Token counts are estimates and say so.** `out_tokens_est` is bytes // 4.
    The decision this drives is "is a hook spending 400 bytes or 40 KB", where a
    20% error changes nothing; a key named `total_tokens` would get quoted as
    exact.

    The hook budget groups hook-sourced rows into `window_s`-second windows —
    one window approximates one prompt's fan-out of hooks. That rule is a
    modelling choice, so it is returned in the payload rather than left for a
    reader to infer.
    """
    rows = read_cli_log(root, since=since)
    counted: list[dict] = []
    uncounted = 0
    for r in rows:
        if r.get("phase") == "start":
            continue                 # intent records carry no output
        if isinstance(r.get("out_bytes"), int):
            counted.append(r)
        else:
            uncounted += 1

    groups = _command_groups()

    def _cmd(r: dict, _g=None) -> str:
        """The SUBCOMMAND PATH, never its arguments.

        `argv[:2]` looked right and was wrong: `scan-prompt <the user's whole
        prompt>` then became a distinct "command" per prompt, so the surface
        with the highest call volume in the product scattered into a row each
        and its percentiles were computed over samples of one. The group set
        comes from the click tree itself, so a new subcommand cannot silently
        reintroduce the bug.
        """
        argv = [a for a in (r.get("argv") or []) if not str(a).startswith("-")]
        if not argv:
            return "(none)"
        head = str(argv[0])
        if head in groups and len(argv) > 1:
            return f"{head} {argv[1]}"
        return head

    def _pct(vals: list[int], q: float) -> int:
        if not vals:
            return 0
        s = sorted(vals)
        return s[min(len(s) - 1, int(q * len(s)))]

    by_command: dict[str, dict] = {}
    for r in counted:
        by_command.setdefault(_cmd(r), []).append(int(r["out_bytes"]))
    commands = {}
    for name, vals in sorted(by_command.items()):
        commands[name] = {
            "n": len(vals),
            "total_bytes": sum(vals),
            "mean_bytes": sum(vals) // len(vals),
            "p50_bytes": _pct(vals, 0.50),
            "p95_bytes": _pct(vals, 0.95),
            "max_bytes": max(vals),
        }

    # ---- the per-prompt hook budget ------------------------------------
    # ANCHORED ON AN ACTUAL PROMPT. `source == "hook"` is exported by EVERY
    # rmx hook template — PostToolUse, PreToolUse, Stop, SubagentStop,
    # SessionStart, PreCompact — not just the UserPromptSubmit set this budget
    # is about. On this project's real cli.log only 11.8% of 5s hook windows
    # contained a scan-prompt, and 75% of hook rows are `focus hook --event
    # tool/tool-pre` pairs fired per TOOL CALL; the p50 of the old "per-prompt"
    # figure was a tool call (ch-bsd r1 #b-7). Nothing on the row says which
    # hook EVENT fired, so tuning window_s cannot fix it — the window has to be
    # anchored on the command that only a prompt produces.
    hook_rows = [r for r in counted if r.get("source") == "hook"]
    hook_rows.sort(key=lambda r: r.get("ts") or "")
    windows: list[int] = []
    cur_total = 0
    cur_start: "float | None" = None
    cur_has_prompt = False

    def _close() -> None:
        nonlocal cur_total, cur_has_prompt
        # A window with no prompt in it is not a prompt.
        if cur_has_prompt:
            windows.append(cur_total)
        cur_total, cur_has_prompt = 0, False

    for r in hook_rows:
        ts = _ts_epoch(r.get("ts"))
        if ts is None:
            continue
        if cur_start is None or (ts - cur_start) > window_s:
            if cur_start is not None:
                _close()
            cur_start = ts
        cur_total += int(r["out_bytes"])
        if _cmd(r) in PROMPT_ANCHORS:
            cur_has_prompt = True
    if cur_start is not None:
        _close()

    total_bytes = sum(int(r["out_bytes"]) for r in counted)
    return {
        "counted": len(counted),
        "uncounted": uncounted,
        "total_bytes": total_bytes,
        "total_tokens_est": total_bytes // 4,
        "by_command": commands,
        "hook_budget": {
            "windows": len(windows),
            "window_s": window_s,
            "anchored_on": sorted(PROMPT_ANCHORS),
            "caveat": ("bytes rmx COMMANDS wrote to stdout; a hook that "
                       "redirects to /dev/null still counts, and non-rmx "
                       "hooks are absent entirely"),
            "grouping": (
                f"hook-sourced rows within a {window_s}s window ANCHORED on a "
                f"scan-prompt row are one prompt's hook fan-out; windows with "
                f"no prompt command are excluded"),
            "total_bytes": sum(windows),
            "p50_bytes": _pct(windows, 0.50),
            "p95_bytes": _pct(windows, 0.95),
            "max_bytes": max(windows) if windows else 0,
            "p50_tokens_est": _pct(windows, 0.50) // 4,
        },
    }


def _ts_epoch(ts: "str | None") -> "float | None":
    """`%Y-%m-%dT%H:%M:%S` -> epoch seconds. Unparseable stays None rather than
    silently becoming 0, which would collapse every row into one window."""
    if not ts:
        return None
    try:
        return time.mktime(time.strptime(str(ts)[:19], "%Y-%m-%dT%H:%M:%S"))
    except (ValueError, TypeError):
        return None


# ---- task 21.1: the ONE recall-event schema (C7) ----------------------------
#
# Why (2026-10-07 exploration, plan-21): 3 CLI `context` calls were counted
# against 1,119 agent greps and no MCP call could be counted at all, and no
# instrument said which recalled item reached the payload or was later used.
# Plan-19's 19.2 / 19.5 / 19.6 have no measurement without it. Everything below
# is the single writer, the single row classifier and the single report.

EVENTS_NAME = "recall-events.jsonl"

# R10's closed SURFACE enum, the ONE channel enum of C7. `cli` / `mcp` are
# invocations (R2), never channels.
RECALL_CHANNELS = ("session_start", "prompt_recall", "scan_prompt", "precompact",
                   "context", "recall", "nudge")

EVENT_STAGES = ("retrieved", "delivered", "used")

# R10: every emitter writes every field (null where the table allows null);
# 19.2's fold imports this tuple.
RECALL_EVENT_FIELDS_V1 = (
    "v", "ts", "session", "turn", "query_id",
    "channel", "invocation",
    "name", "entity_id", "kind", "scope", "partition",
    "cwd", "root",
    "rank", "stage",
    "offset_bytes", "bytes", "payload_bytes",
    "body_offset_bytes", "body_bytes",
    "arm", "policy",
    "stm_session", "stm_source", "stm_events_n", "focus_topics_n", "overlap",
    "phase", "restored_cluster_id",
    "block_id", "block_sha", "rev", "unchanged",
    "evidence", "ref_query_id", "lag_turns",
)

# R5 class 0: an event lacking any of these is `malformed`.
_EVENT_REQUIRED = ("v", "stage", "name", "channel", "cwd", "root", "ts")
_EVENT_TS_RE = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$")

# Until 19.6 chooses an arm per prompt (d5b), every emitter writes these.
FIXED_ARM = "fixed"
FIXED_POLICY = "fixed-v0"

# R12's backward read of the delivered set.
_DELIVERED_BLOCK = 64 * 1024
DELIVERED_CAP_BYTES = 4 * 1024 * 1024


def event_ts(t: "float | None" = None) -> str:
    """R10's UTC stamp, fixed width (`YYYY-MM-DDTHH:MM:SS.mmmZ`), so lexical
    order is time order and no reader depends on its own TZ or a DST change
    (round-4 #s-2). Every other writer stamps local naive time; query.log rows
    keep that form and are joined to events by `query_id`, never by `ts`."""
    t = time.time() if t is None else float(t)
    ms = int(round((t - int(t)) * 1000))
    sec = int(t)
    if ms >= 1000:
        sec, ms = sec + 1, ms - 1000
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(sec)) + f".{ms:03d}Z"


def event_kind(entity_kind: "str | None", mtype: "str | None") -> "str | None":
    """R10a, the ONLY place the catalog-kind → event-kind map lives. `function`
    / `class` are `is_a` concepts, not entity kinds, and session cards and
    subjects are memory rows told apart by `mtype`. Anything else is None: the
    emitter writes no event for it and counts it (`unmapped_kind=<n>`), so a
    new catalog kind surfaces instead of being copied raw."""
    if entity_kind in ("code", "doc", "concept"):
        return entity_kind
    if entity_kind == "memory":
        if mtype == "subject":
            return "subject"
        if mtype == "session":
            return "session"
        return "memory"
    return None


def recall_channel(*, session_start: bool, stdin_json: bool, recent: bool,
                   invocation: str) -> str:
    """R11: which channel a `memory recall` call is, first match wins. The only
    generated hook that runs `--recent` is PreCompact's, so `--recent` is
    `precompact` only under `invocation == "hook"`; an agent's or a human's
    `--recent` is `recall`."""
    if session_start:
        return "session_start"
    if stdin_json:
        return "prompt_recall"
    if recent and invocation == "hook":
        return "precompact"
    return "recall"


def _recall_flags_of(row: dict) -> "tuple[bool, bool, bool]":
    """The `recall_channel` inputs of a `kind=recall` query.log row. Rows
    written by this task carry them (`session_start`, `stdin_json`, `recent`).
    A row without them predates the fields: only one generated hook recall
    carries a query body — the per-prompt `--stdin-json` one (session-start
    and PreCompact recalls are recent-mode and query-less) — so a `hook` row
    with a body reads as `stdin_json`, a `hook` row without one as `recent`."""
    if any(k in row for k in ("session_start", "stdin_json", "recent")):
        return (bool(row.get("session_start")), bool(row.get("stdin_json")),
                bool(row.get("recent")))
    hook = (row.get("invocation") or "unknown") == "hook"
    body = bool((row.get("body") or "").strip())
    return (False, hook and body, hook and not body)


def channel_of_row(row: dict) -> str:
    """The R11 channel of a query.log `recall` / `context` row, recomputed from
    the row by `recall_channel` (R7)."""
    if row.get("kind") == "context":
        return "context"
    ss, sj, rc = _recall_flags_of(row)
    return recall_channel(session_start=ss, stdin_json=sj, recent=rc,
                          invocation=row.get("invocation") or "unknown")


def _global_root_default() -> Path:
    from refmatrix import hub
    return Path(hub.global_store_root())


def emit_recall_events(events: "list[dict]", *, root: Path,
                       global_root: "Path | None" = None) -> int:
    """The ONLY writer of recall events (R8, R11). Each surface calls it
    EXACTLY ONCE per call, after its payload is written. Fills every field of
    `RECALL_EVENT_FIELDS_V1` (null where allowed), stamps one UTC `ts` and the
    caller's `cwd` / `root`, drops (and counts on stderr) an item whose kind is
    unmapped or whose partition is unknown, and splits the list by `scope`: a
    `global` event goes to the GLOBAL root's file (d8e), every other to
    `root`'s. Lock-free like query.log: one `write()` of one complete line per
    event, `O_APPEND`, never under the daemon's writer lock. A failed append is
    said on stderr and the command continues (telemetry never fails the command
    it describes). Returns the number of events written."""
    if _disabled() or not events:
        return 0
    ts = event_ts()
    try:
        cwd = os.getcwd()
    except OSError as e:
        print(f"rmx: recall-event append failed: cwd unreadable ({e})", file=sys.stderr)
        return 0
    groot = Path(global_root) if global_root is not None else None
    by_file: dict[Path, list[bytes]] = {}
    unmapped = no_partition = 0
    for ev in events:
        rec = {f: ev.get(f) for f in RECALL_EVENT_FIELDS_V1}
        rec["v"] = 1
        rec["ts"] = ts
        rec["cwd"] = cwd
        rec["root"] = str(root)
        if rec["kind"] is None:
            unmapped += 1
            continue
        if not rec["name"]:
            no_partition += 1               # an item with no name cannot be keyed (19.2 R1)
            continue
        if not rec["partition"]:
            no_partition += 1
            continue
        if rec["scope"] == "global":
            if groot is None:
                groot = _global_root_default()
            dest = groot / EVENTS_NAME
        else:
            rec["scope"] = rec["scope"] or "project"
            dest = Path(root) / EVENTS_NAME
        by_file.setdefault(dest, []).append(
            (json.dumps(rec, default=str) + "\n").encode("utf-8"))
    if unmapped:
        print(f"rmx: recall events: unmapped_kind={unmapped} item(s) not logged",
              file=sys.stderr)
    if no_partition:
        print(f"rmx: recall events: partition_unresolved={no_partition} item(s) "
              f"(no partition or no name) not logged", file=sys.stderr)
    written = 0
    for dest, lines in by_file.items():
        if not dest.parent.is_dir():
            print(f"rmx: recall-event append failed: no store at {dest.parent}",
                  file=sys.stderr)
            continue
        try:
            fd = os.open(str(dest), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        except OSError as e:
            print(f"rmx: recall-event append failed: {e}", file=sys.stderr)
            continue
        try:
            for line in lines:
                os.write(fd, line)
                written += 1
        except OSError as e:
            print(f"rmx: recall-event append failed: {e}", file=sys.stderr)
        finally:
            os.close(fd)
    return written


# R10 `block_id` per surface (the emitted block's stable id).
RECALL_BLOCK_IDS = {"session_start": "session-start", "prompt_recall": "prompt-recall",
                    "scan_prompt": "scan-prompt", "precompact": "precompact",
                    "context": "context", "recall": "recall", "nudge": "nudge"}


def recall_item(row: dict, *, rank: int) -> dict:
    """An emitter item from a recall hit or row: its name, id, catalog kind and mtype (R10a
    maps them), scope and the partition NAME the row was read from — never the bound one."""
    return {"name": row.get("name"), "entity_id": row.get("id") or row.get("entity_id"),
            "catalog_kind": row.get("kind") or "memory", "mtype": row.get("mtype"),
            "partition": row.get("partition"), "scope": row.get("scope") or "project",
            "rank": rank}


def spans_by_name(payload: bytes, items: "list[dict]", *, json_mode: bool) -> "list[dict]":
    """Byte spans of the items a payload names, found in payload order from a moving
    cursor: in JSON the `"name": "<name>"` member of each row object (the object carries
    the body, so `body_*` stay null); in text the name itself. An item not found keeps null
    spans (R10: offsets are UTF-8 bytes of what the command wrote)."""
    cur = 0
    out = []
    for it in items:
        it = dict(it)
        it.setdefault("body_offset_bytes", None)
        it.setdefault("body_bytes", None)
        name = it.get("name")
        needles = ([('"name": ' + json.dumps(name)).encode(), ('"name":' + json.dumps(name)).encode()]
                   if json_mode else [str(name).encode("utf-8")]) if name else []
        found = None
        for nd in needles:
            i = payload.find(nd, cur)
            if i >= 0:
                found = (i, len(nd))
                break
        if found:
            it["offset_bytes"], it["bytes"] = found
            cur = found[0] + found[1]
        else:
            it["offset_bytes"] = it["bytes"] = None
        out.append(it)
    return out


def _item_fields(it: dict) -> dict:
    return {"name": it.get("name"), "entity_id": it.get("entity_id"),
            "kind": event_kind(it.get("catalog_kind"), it.get("mtype")),
            "scope": it.get("scope") or "project", "partition": it.get("partition"),
            "rank": it.get("rank")}


def emit_call(root: Path, *, channel: str, invocation: str, session: "str | None",
              query_id: str, retrieved: "list[dict]", delivered: "list[dict]",
              payload: "bytes | None", block_id: "str | None",
              phase: "dict | None" = None, turn: "int | None" = None,
              global_root: "Path | None" = None) -> int:
    """Build one call's `retrieved` and `delivered` events and hand them to the ONE writer
    in ONE `emit_recall_events` call (R11). `phase` is `stm.phase_fields(...)` on the
    prompt-time channels (it carries `turn`); other channels pass `turn`. `block_sha` is the
    sha256 of the exact payload bytes the command wrote."""
    import hashlib
    common = {"session": session, "turn": turn, "query_id": query_id, "channel": channel,
              "invocation": invocation, "arm": FIXED_ARM, "policy": FIXED_POLICY,
              "block_id": block_id,
              "block_sha": hashlib.sha256(payload).hexdigest() if payload is not None else None}
    if phase:
        common.update(phase)
    events: list[dict] = []
    for it in retrieved:
        events.append({**common, **_item_fields(it), "stage": "retrieved"})
    for it in delivered:
        ev = {**common, **_item_fields(it), "stage": "delivered",
              "offset_bytes": it.get("offset_bytes"), "bytes": it.get("bytes"),
              "payload_bytes": len(payload) if payload is not None else None,
              "body_offset_bytes": it.get("body_offset_bytes"),
              "body_bytes": it.get("body_bytes")}
        events.append(ev)
    return emit_recall_events(events, root=root, global_root=global_root)


def emit_context_call(root: Path, *, ref: str, items: "list[dict]",
                      payload: "bytes | None", query_id: str, session: "str | None",
                      invocation: str, turn: "int | None" = None) -> int:
    """The `context` channel's ONE emission (R11) for any of R3's four routes: `retrieved`
    for every item the bundle names and `delivered` for those with a span in the payload.
    Then R12's `context_by_name` `used` events, looked up after them: a key this call
    delivered is used when ANOTHER surface delivered it earlier in the session (see
    `context_used_keys`), and the event points to that key's newest delivery."""
    delivered = [it for it in items if it.get("offset_bytes") is not None]
    n = emit_call(root, channel="context", invocation=invocation, session=session,
                  query_id=query_id, retrieved=items, delivered=delivered,
                  payload=payload, block_id=RECALL_BLOCK_IDS["context"], turn=turn)
    used = used_events(root, session=session, invocation=invocation,
                       evidence="context_by_name",
                       match=lambda d: context_used_keys(ref, delivered, d),
                       body=ref, turn=turn, query_id=query_id, channel="context")
    return n + (emit_recall_events(used, root=root) if used else 0)


# ---- R12: `used` events -------------------------------------------------------------------

# A name in a note is matched on whole tokens: a token boundary is any character outside
# [A-Za-z0-9_.-] (so a sentence-final `name.` is the token `name.` and does NOT match — an
# under-count, the safe direction for a never-decaying counter).
_NOTE_TOKEN_RE = re.compile(r"[A-Za-z0-9_.\-]+")
_WIKILINK_RE = re.compile(r"\[\[([^\]#|]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")


def _matchable(name: str) -> bool:
    """Only names of length >= 6 or containing one of `_ . -` can fire, so a short
    delivered name (`run`, `rank`) cannot match prose."""
    return bool(name) and (len(name) >= 6 or any(c in name for c in "_.-"))


def note_used_keys(text: str, delivered: "dict") -> "list[tuple]":
    """R12 `focus_note` matcher: every delivered key whose `name` is a whole token of the
    note, or the `<doc>` of a `[[<doc>]]` / `[[<doc>#<anchor>]]` wikilink — one key per
    `(name, kind, scope)`, however often the name occurs."""
    names = set(_NOTE_TOKEN_RE.findall(text or ""))
    names |= {m.strip() for m in _WIKILINK_RE.findall(text or "")}
    return [key for key in delivered if key[0] in names and _matchable(key[0])]


def _log_used_lookup(root: Path, *, evidence: str, body: str, session: "str | None",
                     cap_hits: int = 0, used_no_session: bool = False) -> None:
    """A `used-lookup` query.log row, written ONLY when the lookup was cut at its cap or
    could not run for want of a session — the two under-counts R12 says are counted."""
    with log_query(None, kind="used-lookup", body=body[:200], source=f"used-{evidence}",
                   root=root, session=session) as t:
        t.outcome = "empty" if used_no_session else "ok"
        t.extra.update(cap_hits=cap_hits, used_no_session=used_no_session)


def used_events(root: Path, *, session: "str | None", invocation: str, evidence: str,
                match, body: str = "", turn: "int | None" = None,
                query_id: "str | None" = None, channel: "str | None" = None,
                global_root: "Path | None" = None) -> "list[dict]":
    """R12's `used` events for one EXPLICIT call (the caller hands them to the ONE writer
    with its own events, in its one `emit_recall_events` call). A `hook` call never emits (the helix
    confound cannot recur); with no resolved session nothing is emitted and the miss is
    counted (`used_no_session`) for agent/MCP calls — the newest ring is never used. `match`
    maps the session's delivered set (`delivered_in_session`) to the keys this call used;
    each key emits ONE event pointing back (`ref_query_id`) to its delivered event, to the
    file of that event's scope (a global memory's use goes to the global file, d8e). A call
    that has its own query.log row and events (a context call) passes its `query_id` and
    `channel`, so every event of the call shares them (R4); a call with neither (`memory
    get`, `focus note`) mints an id, and the event carries the delivered event's channel."""
    if invocation == "hook":
        return []
    if not session:
        if invocation in ("agent", "mcp"):
            _log_used_lookup(root, evidence=evidence, body=body, session=None,
                             used_no_session=True)
        return []
    delivered = delivered_in_session(session, root=root, global_root=global_root)
    if delivered.cap_hits:
        _log_used_lookup(root, evidence=evidence, body=body, session=session,
                         cap_hits=delivered.cap_hits)
    keys = match(delivered)
    if not keys:
        return []
    qid = query_id or uuid.uuid4().hex
    events = []
    for key in dict.fromkeys(keys):
        d = delivered[key]
        lag = (turn - d["turn"]) if isinstance(turn, int) and isinstance(d.get("turn"), int) \
            else None
        events.append({"session": session, "turn": turn, "query_id": qid,
                       "channel": channel or d.get("channel"), "invocation": invocation,
                       "name": d.get("name"), "entity_id": d.get("entity_id"),
                       "kind": d.get("kind"), "scope": d.get("scope") or "project",
                       "partition": d.get("partition"), "stage": "used",
                       "arm": FIXED_ARM, "policy": FIXED_POLICY,
                       "evidence": evidence, "ref_query_id": d.get("query_id"),
                       "lag_turns": lag})
    return events


def context_used_keys(ref: str, delivered_here: "list[dict]", delivered: "dict"
                      ) -> "list[tuple]":
    """R12 `context_by_name`: the call's `ref`, stripped, equals a delivered name exactly
    (case-sensitive) AND this context call delivered an item of that name and kind — its
    anchor, or (for `kind=memory`) the memory body it attached to a concept/doc/code anchor.
    The key must ALSO have been delivered by a surface other than `context` in this
    session: a context call's own delivery (or an earlier context call's) is the lookup
    itself, not evidence that something delivered to the agent was used — so `rmx context X`
    twice on a bare concept is no use, while the memory a prompt recall injected is."""
    ref = (ref or "").strip()
    here = {(it.get("name"), event_kind(it.get("catalog_kind"), it.get("mtype")))
            for it in delivered_here}
    channels = getattr(delivered, "channels", {})
    return [key for key in delivered
            if key[0] == ref and (key[0], key[1]) in here and key[2] == "project"
            and (channels.get(key, set()) - {"context"})]


class DeliveredSet(dict):
    """`delivered_in_session`'s answer: `(name, kind, scope) -> event`, plus
    what the bounded read cost (`bytes_read`) and whether a file was cut at the
    cap (`cap_hits`), so the caller can count the under-count."""
    bytes_read: int = 0
    cap_hits: int = 0

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        # every channel that delivered each key within the read range
        self.channels: "dict[tuple, set]" = {}


def _lines_backwards(path: Path, cap: int) -> "tuple[list[bytes], int, bool]":
    """Complete lines of `path`, NEWEST first, read backwards in 64 KB blocks
    and stopping at `cap` bytes. Returns (lines, bytes_read, capped)."""
    out: list[bytes] = []
    read = 0
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        pos = f.tell()
        carry = b""
        while pos > 0 and read < cap:
            n = min(_DELIVERED_BLOCK, pos, cap - read)
            pos -= n
            f.seek(pos)
            chunk = f.read(n)
            read += n
            buf = chunk + carry
            parts = buf.split(b"\n")
            carry = parts[0]                 # possibly partial: completed next round
            for ln in reversed(parts[1:]):
                if ln.strip():
                    out.append(ln)
        capped = pos > 0
        if not capped and carry.strip():
            out.append(carry)                # the file's first line, complete
    return out, read, capped


def delivered_in_session(session: "str | None", *, root: Path,
                         global_root: "Path | None" = None) -> DeliveredSet:
    """R12's lookup: the `delivered` events of `session`, newest per
    `(name, kind, scope)`, from `root`'s and the global root's
    `recall-events.jsonl`, read BACKWARDS from the end and capped at 4 MB per
    file. A delivery older than the cap is not found — an under-count, the safe
    direction for a never-decaying counter — and the cut is counted
    (`cap_hits`). Events with a null session are in no set; `precompact`
    deliveries are excluded until 19.5 R1 decides whether PreCompact stdout
    reaches the agent (d5d). Runs only on the explicit `used` calls."""
    found = DeliveredSet()
    if not session:
        return found
    groot = Path(global_root) if global_root is not None else _global_root_default()
    seen_paths = set()
    for base in (Path(root), groot):
        p = base / EVENTS_NAME
        try:
            key_path = p.resolve()
        except OSError:
            key_path = p
        if key_path in seen_paths or not p.is_file():
            continue
        seen_paths.add(key_path)
        try:
            lines, nread, capped = _lines_backwards(p, DELIVERED_CAP_BYTES)
        except OSError as e:
            print(f"rmx: delivered-set read failed for {p}: {e}", file=sys.stderr)
            continue
        found.bytes_read += nread
        found.cap_hits += int(capped)
        for ln in lines:
            try:
                ev = json.loads(ln)
            except ValueError:
                continue                     # counted by the report, not here
            if not isinstance(ev, dict) or ev.get("stage") != "delivered":
                continue
            if ev.get("session") != session or ev.get("channel") == "precompact":
                continue
            key = (ev.get("name"), ev.get("kind"), ev.get("scope") or "project")
            found.channels.setdefault(key, set()).add(ev.get("channel"))
            if key not in found:             # newest first: keep the first seen
                found[key] = ev
    return found


# ---- R5: the ONE row classifier ----------------------------------------------

def _norm_tmp(p: str) -> str:
    """`/private/tmp` and `/tmp` (and `/private/var` / `/var`) are one place on
    macOS; a row written by a child that saw the symlinked spelling must land
    in the same test base as its reader."""
    for pre in ("/private/tmp", "/private/var"):
        if p == pre or p.startswith(pre + "/"):
            return p[len("/private"):]
    return p


def _test_base(p: "str | Path | None") -> "str | None":
    """R5's test base of a path: up to and including the `pytest-<N>` component
    that follows a `pytest-of-<user>` component; else, under `/tmp` (or
    `/private/tmp`), the first component below it when it starts with `rmx-`
    (23.0's sandbox root); else None (a live tree)."""
    if not p:
        return None
    s = _norm_tmp(str(p))
    parts = Path(s).parts
    for i, comp in enumerate(parts[:-1]):
        if comp.startswith("pytest-of-") and parts[i + 1].startswith("pytest-"):
            return str(Path(*parts[: i + 2]))
    if len(parts) >= 3 and parts[0] == "/" and parts[1] == "tmp" \
            and parts[2].startswith("rmx-"):
        return str(Path(*parts[:3]))
    return None


ROW_CLASSES = ("attributed", "test_artifact", "legacy_fixture", "legacy_unattributed",
               "malformed")


def row_provenance(row: dict, *, reader_root: "Path | None" = None,
                   source: "typing.Literal['query_log', 'events']" = "query_log") -> str:
    """Classify one `query.log` row or `recall-events.jsonl` event (task 21.1
    R5, d8d, d9g). EVERY reader of those two logs calls this; no reader keeps
    its own copy, and no reader decides `malformed` itself. First match wins:

    0. `malformed` (`source="events"` only): a required field missing, `v`
       not 1, a channel outside the enum, or a `ts` not in R10's UTC form;
    1. `test_artifact`: the row's KEY PATH (`root`, else `cwd`) has a test
       base that differs from the reader's. Keyed on `root` (round-3 #s-3): one
       test run has two test bases — the sandbox store roots under
       `/tmp/rmx-*` and pytest's `tmp_path` — and the root is the store the row
       was written for. A row with NO test base is never a test artifact;
    2. `legacy_fixture`: no `cwd`/`root`, `kind == "grep"` and `body` exactly
       `alpha|beta` (the 235 fixture rows in the global store, 2026-10-14);
    3. `legacy_unattributed`: any other row with neither `cwd` nor `root`;
    4. `attributed`.
    `reader_root=None` is a LIVE reader (no test base)."""
    if source == "events":
        if not isinstance(row, dict) or any(row.get(k) is None for k in _EVENT_REQUIRED):
            return "malformed"
        if row.get("v") != 1 or row.get("channel") not in RECALL_CHANNELS:
            return "malformed"
        if not isinstance(row.get("ts"), str) or not _EVENT_TS_RE.match(row["ts"]):
            return "malformed"
    key = row.get("root") or row.get("cwd")
    if key:
        base = _test_base(key)
        if base is not None and base != _test_base(reader_root):
            return "test_artifact"
    if not row.get("cwd") and not row.get("root"):
        if row.get("kind") == "grep" and row.get("body") == "alpha|beta":
            return "legacy_fixture"
        return "legacy_unattributed"
    return "attributed"


def is_test_artifact_row(row: dict, *, reader_root: "Path | None" = None,
                         source: "typing.Literal['query_log', 'events']" = "query_log"
                         ) -> bool:
    """`row_provenance(...) == "test_artifact"` and nothing else (23.0 AC-4
    calls it as `is_test_artifact_row(row)` on live rows)."""
    return row_provenance(row, reader_root=reader_root, source=source) == "test_artifact"


# ---- R7: `rmx telemetry --agent-usage` ------------------------------------------

def _read_jsonl_counted(path: Path) -> "tuple[list[dict], int]":
    """Every parseable object row of a JSONL file, plus the count of lines that
    did not parse — counted and printed by the report, never skipped silently."""
    rows: list[dict] = []
    bad = 0
    if not path.exists():
        return rows, 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except ValueError:
            bad += 1
            continue
        if isinstance(r, dict):
            rows.append(r)
        else:
            bad += 1
    return rows, bad


def _in_window(ts: "str | None", since: "str | None", until: "str | None") -> bool:
    """ISO-prefix window: `since` inclusive, `until` exclusive."""
    t = str(ts or "")
    if since and t < since:
        return False
    if until and t >= until:
        return False
    return True


def _pcts(vals: "list[int]") -> "tuple[int, int]":
    if not vals:
        return 0, 0
    s = sorted(vals)
    return (s[min(len(s) - 1, int(0.50 * len(s)))],
            s[min(len(s) - 1, int(0.95 * len(s)))])


def _lat(rows: "list[dict]") -> str:
    p50, p95 = _pcts([r["latency_ms"] for r in rows
                      if isinstance(r.get("latency_ms"), int)])
    return f"p50={p50}ms p95={p95}ms"


def agent_usage_report(root: Path, *, since: "str | None" = None,
                       until: "str | None" = None, include_internal: bool = False,
                       by_session: bool = False,
                       expired_reads: "int | str | None" = None) -> "list[str]":
    """How the agent used rmx context / grep / recall, from ONE store's
    `query.log`, `cli.log` and `recall-events.jsonl` (task 21.1 R7).

    Every row is classified by `row_provenance` with `reader_root` = this root:
    `attributed` and `legacy_unattributed` rows are counted, `test_artifact`
    and `legacy_fixture` rows are not, and all three non-attributed counts are
    printed (R5's totals rule), so nothing is silently included or dropped.
    `invocation=internal` rows (eval harnesses) are excluded unless
    `include_internal`. A `cli.log` command is counted once (its `phase=start`
    intent row is not a call). `expired_reads` is the daemon's dropped-read
    count from `_op_stats`, or the reason it is unavailable — never a 0 for a
    daemon that did not answer."""
    root = Path(root)
    out: list[str] = [f"agent usage · window {since or '-'} .. {until or '-'} "
                      f"(since inclusive, until exclusive)"]
    qrows, q_bad = _read_jsonl_counted(root / LOG_NAME)
    counts = Counter()
    kept: list[dict] = []
    internal = 0
    for r in qrows:
        if not _in_window(r.get("ts"), since, until):
            continue
        cls = row_provenance(r, reader_root=root)
        counts[cls] += 1
        if cls not in ("attributed", "legacy_unattributed"):
            continue
        if not include_internal and (r.get("invocation") or "unknown") == "internal":
            internal += 1
            continue
        kept.append(r)
    out.append(f"excluded_test_rows={counts['test_artifact']} "
               f"legacy_fixture_rows={counts['legacy_fixture']} "
               f"legacy_unattributed={counts['legacy_unattributed']}")
    out.append(f"query.log: counted={len(kept)} unparseable={q_bad} "
               f"internal_excluded={internal}")

    def _route(r: dict) -> str:
        return r.get("source") or "?"

    ctx = [r for r in kept if r.get("kind") == "context"]
    grp = [r for r in kept if r.get("kind") == "grep"]
    rec = [r for r in kept if r.get("kind") == "recall"]

    out.append("totals:")
    for name, rows in sorted(Counter(_route(r) for r in ctx).items()):
        out.append(f"  context {name}: {rows}")
    for name, rows in sorted(Counter(_route(r) for r in grp).items()):
        out.append(f"  grep {name}: {rows}")
    out.append(f"  memory_recall rows: {len(rec)}")

    out.append("by invocation:")
    invs = sorted({r.get("invocation") or "unknown" for r in ctx + grp + rec})
    for inv in invs:
        out.append(f"  invocation={inv}")
        mine = [r for r in ctx + grp + rec if (r.get("invocation") or "unknown") == inv]
        groups: dict[str, list[dict]] = {}
        for r in mine:
            if r.get("kind") == "context":
                groups.setdefault(f"context {_route(r)}", []).append(r)
            elif r.get("kind") == "grep":
                groups.setdefault(f"grep {_route(r)}", []).append(r)
                ab = r.get("answered_by") or "unknown"
                groups.setdefault(f"grep {_route(r)} answered_by={ab}", []).append(r)
            else:
                groups.setdefault(f"memory_recall {channel_of_row(r)}", []).append(r)
        for label in sorted(groups):
            out.append(f"    {label}: {len(groups[label])} {_lat(groups[label])}")

    # R7 / round-8 #nm-5: per recall channel and for context, the count of each
    # outcome, so a skipped prompt never reads as "recall ran and delivered 0".
    out.append("outcomes:")
    by_channel: dict[str, Counter] = {}
    for r in rec + ctx:
        by_channel.setdefault(channel_of_row(r), Counter())[_outcome_of(r)] += 1
    for ch in sorted(by_channel):
        c = by_channel[ch]
        extra = "".join(f" {k}={c[k]}" for k in ("empty", "consumer-closed") if c.get(k))
        out.append(f"  {ch}: ok={c['ok']} skipped_budget={c['skipped_budget']} "
                   f"error={c['error']}{extra}")
    invalid = sum(1 for r in kept if str(r.get("error") or "").startswith("outcome-invalid:"))
    if invalid:
        out.append(f"outcome-invalid={invalid}")
    if expired_reads is None:
        out.append("expired_reads: unavailable (not queried)")
    else:
        out.append(f"expired_reads: {expired_reads}")

    # R12's lookup counters, from the `used-lookup` rows the used emitters write.
    lookups = [r for r in kept if r.get("kind") == "used-lookup"]
    out.append(f"used_lookup_cap_hits={sum(int(r.get('cap_hits') or 0) for r in lookups)} "
               f"used_no_session={sum(1 for r in lookups if r.get('used_no_session'))}")

    # cli.log: one count per command (phase=start intent rows excluded).
    crows, c_bad = _read_jsonl_counted(root / CLI_LOG_NAME)
    c_test = 0
    recalls = 0
    for r in crows:
        if r.get("phase") == "start" or not _in_window(r.get("ts"), since, until):
            continue
        if row_provenance(r, reader_root=root) == "test_artifact":
            c_test += 1
            continue
        if not include_internal and (r.get("source") or "unknown") == "internal":
            continue
        argv = [str(a) for a in (r.get("argv") or [])]
        if argv[:2] == ["memory", "recall"]:
            recalls += 1
    out.append(f"cli.log: memory recall commands={recalls} "
               f"excluded_test_rows={c_test} unparseable={c_bad}")

    # recall-events.jsonl, classified by the same function (source="events").
    erows, e_bad = _read_jsonl_counted(root / EVENTS_NAME)
    ecount = Counter()
    folded = Counter()
    for ev in erows:
        cls = row_provenance(ev, reader_root=root, source="events")
        ecount[cls] += 1
        if cls == "attributed" and _in_window(ev.get("ts"), since, until):
            folded[(ev.get("channel"), ev.get("stage"))] += 1
    out.append(f"recall-events.jsonl: folded={sum(folded.values())} "
               f"malformed={ecount['malformed']} unparseable={e_bad} "
               f"excluded_test_rows={ecount['test_artifact']}")
    for (ch, st), n in sorted(folded.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))):
        out.append(f"  events {ch} {st}: {n}")

    if by_session:
        out.append("by session:")
        sc = Counter(r.get("session") or "(null)" for r in kept)
        for sess, n in sorted(sc.items(), key=lambda kv: (-kv[1], kv[0])):
            out.append(f"  {sess}: {n} calls")
    out.append("note: stm_events_n counts every ring line until 19.0 R2 stamps "
               "an origin on subagent events.")
    return out
