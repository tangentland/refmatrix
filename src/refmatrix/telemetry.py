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
import time
from collections import Counter
from pathlib import Path
from typing import Any

from refmatrix.store import Store


LOG_NAME = "query.log"


def _disabled() -> bool:
    return os.environ.get("REFMATRIX_NO_TELEMETRY") in ("1", "true", "yes")


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
    """Queries that returned cardinality 0 — gaps to fill."""
    rows = read_log(store)
    counter: Counter[str] = Counter()
    for r in rows:
        if r.get("cardinality") == 0:
            counter[r.get("body") or "?"] += 1
    return counter.most_common(limit)
