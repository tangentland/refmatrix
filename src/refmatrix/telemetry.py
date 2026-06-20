"""
Query telemetry. JSONL append-only log at `.refmatrix/query.log`.

One record per query, fields:
    ts            ISO-8601 timestamp
    kind          'dsl' | 'pql' | 'neighbors' | 'co-occur' | 'top' | 'context' | 'scan'
    body          query string or anchor symbol
    source        cli command name ('query', 'context', etc.)
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


def log_cli_invocation(
    root: Path,
    *,
    argv: list[str],
    cwd: str,
    exit_code: int,
    latency_ms: int,
    error: str | None,
    pid: int,
) -> None:
    """Append one JSONL record for an `rmx` CLI invocation to .refmatrix/cli.log.

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
        store: Store,
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
        latency_ms = int((time.monotonic() - self.t0) * 1000)
        record: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "kind": self.kind,
            "body": self.body,
            "source": self.source,
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
