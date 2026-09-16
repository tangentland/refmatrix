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
    error         "ExcType: msg" if the query raised, else null

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
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

from refmatrix.store import Store


LOG_NAME = "query.log"
CLI_LOG_NAME = "cli.log"

# Recognized invocation "forms" — how an `rmx` call entered the system.
# `hook`        — fired by a Claude Code / git hook (set RMX_INVOCATION_SOURCE=hook)
# `interactive` — a human typed it at a tty
# `mcp`         — issued through the hub MCP server
# `internal`    — daemon/subprocess fan-out
# `unknown`     — pre-source-field logs, or no tty + no hint
INVOCATION_SOURCES = ("hook", "interactive", "mcp", "internal", "unknown")


def _disabled() -> bool:
    return os.environ.get("REFMATRIX_NO_TELEMETRY") in ("1", "true", "yes")


def invocation_source() -> str:
    """Classify *how* this `rmx` call was invoked — the telemetry "form" axis.

    Explicit `RMX_INVOCATION_SOURCE` wins (hook templates / the MCP server set
    it). Absent that, a tty means a human typed it (`interactive`); no tty means
    we can't tell (`unknown`). Always returns a member of INVOCATION_SOURCES."""
    src = os.environ.get("RMX_INVOCATION_SOURCE")
    if src:
        src = src.strip().lower()
        return src if src in INVOCATION_SOURCES else "unknown"
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


class log_query:
    """Context manager that times its body and appends a JSONL telemetry record."""

    def __init__(
        self,
        store: "Store | None",
        *,
        kind: str,
        body: str,
        source: str = "cli",
    ):
        self.store = store
        self.kind = kind
        self.body = body
        self.source = source
        self.cardinality: int | None = None
        self.t0: float = 0.0

    def __enter__(self) -> "log_query":
        self.t0 = time.monotonic()
        return self

    def __exit__(self, exc_type, exc_val, _exc_tb) -> None:
        if _disabled():
            return
        if self.store is None:
            # RPC-served paths (e.g. grep via daemon) have no local store;
            # there is nowhere to append the record. Previously this raised
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
        record: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "kind": self.kind,
            "body": self.body,
            "source": self.source,
            "invocation": form,
            "cardinality": self.cardinality,
            "latency_ms": latency_ms,
            "error": None if exc_type is None else f"{exc_type.__name__}: {exc_val}",
        }
        try:
            with (self.store.root / LOG_NAME).open("a") as f:
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
    errors = [r for r in rows if r.get("error")]

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
        if r.get("error"):
            errors.append({"argv": argv, "error": r["error"], "ts": r.get("ts")})
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
        "error_count": len(errors),
        "error_rate": (nonzero_exits / total) if total else 0.0,
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
