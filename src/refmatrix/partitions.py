"""Canonical partition layout and the read-only audit over it (ADR-0003).

A survey of the fleet on 2026-09-20 found FOUR layouts across nine stores: six
zero-row orphan registrations (one of them `test_session_list_shows_ingest0`, a
test fixture name in this project's live catalog), ~143MB of Lance vectors for
partitions that no longer exist, session partitions on four of eight stores, and
one store never embedded at all. Every anomaly was invisible because nothing in
the product reports a store's SHAPE — `rmx partition list` prints rows without
comment, so drift only surfaces when somebody surveys by hand.

`audit()` is deliberately a PURE FUNCTION over facts. It receives partitions,
row counts and vector directory names; it cannot open a catalog, cannot take the
writer lock, and cannot write. Read-only is a property of the signature rather
than a promise in a docstring — `test_audit_is_pure_and_takes_no_store` asserts
exactly that, because "the repair tool damaged the thing it was auditing" is a
failure this project can afford once.

The canonical shape and the reasoning for it live in
`docs/adr/0003-canonical-partition-layout.md`.
"""
from __future__ import annotations

from typing import Any

# Kinds a `global` store may hold. It is memory-only since 0.65.0; `concept` is
# derived from memory rows, so it is expected company.
GLOBAL_KINDS = {"memory", "concept"}

# The reversed split. `memory-<project>` was the layout until post-0.5.0, when
# it was undone BECAUSE it made cross-partition wikilinks unresolvable and
# memory->memory `rel:` edges silently dropped (`cli.py:9736`). A live one is
# drift with a specific remedy, not a generic orphan.
REVERSED_SPLIT_PREFIX = "memory-"

SESSIONS_PREFIX = "sessions-"


def expected_partitions(store_name: str, *, is_global: bool) -> "list[str]":
    """The canonical partition names for a store (ADR-0003 #shape): exactly two
    for a project store, exactly one for global."""
    if is_global:
        return [store_name]
    return [store_name, f"{SESSIONS_PREFIX}{store_name}"]


def _finding(kind: str, name: str, severity: str, detail: str, remedy: str) -> dict:
    return {"kind": kind, "name": name, "severity": severity,
            "detail": detail, "remedy": remedy}


def audit(
    *,
    store_name: str,
    partitions: "list[dict]",
    active: str,
    row_counts: "dict[str, dict[str, int]]",
    vector_dirs: "list[str]",
    is_global: bool,
) -> "dict[str, Any]":
    """Compare one store's layout against ADR-0003 and return its findings.

    `partitions` is `[{id, name, kind}]` as `partition_list` returns them;
    `row_counts` maps a partition name to `{entity_kind: count}`; `vector_dirs`
    is the basenames under `.refmatrix/vectors/`.

    Severity is three-valued on purpose. `drift` means the store is not the
    canonical shape. `warn` means something is wrong inside a canonical shape
    (an unembedded project partition answers every dense query with nothing,
    silently). `info` is reported and does NOT make a store non-canonical —
    session embedding is deliberately undecided until plan-13's gate returns
    (ADR-0003 #deferred-embed), and an audit that called an undecided question
    drift would train its own signal away.
    """
    names = [p["name"] for p in partitions]
    expected = expected_partitions(store_name, is_global=is_global)
    sessions_name = f"{SESSIONS_PREFIX}{store_name}"
    findings: list[dict] = []

    def rows(name: str) -> int:
        return sum((row_counts.get(name) or {}).values())

    for name in names:
        if name in expected:
            continue
        # A reversed-split partition is named as such: the remedy is a merge
        # into the project partition, not a drop.
        if name.startswith(REVERSED_SPLIT_PREFIX) and name == f"{REVERSED_SPLIT_PREFIX}{store_name}":
            findings.append(_finding(
                "reversed-split", name, "drift",
                "the memory-<project> split was reversed post-0.5.0 because it made "
                "cross-partition wikilinks unresolvable and memory->memory rel: edges "
                "silently dropped",
                f"merge {name} into {store_name}; do not simply drop it — it holds memory rows",
            ))
            continue
        # Another project's partition registered in this store.
        if name.startswith(REVERSED_SPLIT_PREFIX) or name.startswith(SESSIONS_PREFIX):
            findings.append(_finding(
                "foreign-partition", name, "drift",
                f"belongs to another project, registered inside {store_name}'s catalog",
                f"drop the registration if it holds no rows ({rows(name)} rows found)",
            ))
            continue
        # Everything else with no rows is a leak: a partition is registered
        # WITH its first rows (ADR-0003 invariant 1), so a zero-row one was
        # created by something that wrote nothing — a test, or an aborted
        # ingest. The ACTIVE partition is exempt: a freshly `init`ed store has
        # an empty active partition and is new, not drifted.
        if rows(name) == 0 and name != active:
            findings.append(_finding(
                "orphan-partition", name, "drift",
                "registered with zero rows — a partition is registered with its first "
                "rows, so this was created by something that wrote nothing",
                "drop the registration",
            ))
        else:
            findings.append(_finding(
                "unexpected-partition", name, "drift",
                f"not part of the canonical shape and holds {rows(name)} rows",
                "decide whether it belongs; ADR-0003 allows exactly "
                + " + ".join(expected),
            ))

    if not is_global and sessions_name not in names:
        findings.append(_finding(
            "missing-sessions", sessions_name, "drift",
            "no session partition — this store has no turn-level session history",
            "rmx session ingest",
        ))

    # Vectors are a second catalog. A directory with no partition describes a
    # partition that does not exist, which is worse than dead weight: a reader
    # of vectors/ would conclude it does.
    for vec in vector_dirs:
        if vec not in names:
            findings.append(_finding(
                "orphan-vectors", vec, "drift",
                "Lance vectors for a partition that is not in the catalog",
                f"remove vectors/{vec} after backing it up",
            ))

    # A populated partition with no vectors answers every dense query with
    # nothing while symbolic surfaces keep working, so nothing reads broken.
    if rows(active) and active not in vector_dirs:
        findings.append(_finding(
            "unembedded", active, "warn",
            f"{rows(active)} rows and no vectors — every dense retrieval returns nothing",
            "rmx embed",
        ))
    if sessions_name in names and rows(sessions_name) and sessions_name not in vector_dirs:
        findings.append(_finding(
            "sessions-unembedded", sessions_name, "info",
            "session partition is symbolic-only; whether sessions should be embedded is "
            "undecided until plan-13's gate 13.0 returns (ADR-0003 #deferred-embed)",
            "no action yet — decide after 13.0",
        ))

    if is_global:
        held = {k for k, n in (row_counts.get(active) or {}).items() if n}
        extra = sorted(held - GLOBAL_KINDS)
        if extra:
            findings.append(_finding(
                "global-not-memory-only", active, "drift",
                f"global store holds {', '.join(extra)} rows; it is memory-only since 0.65.0",
                "establish where those rows came from before removing anything",
            ))

    drifted = [f for f in findings if f["severity"] == "drift"]
    return {
        "store": store_name,
        "active": active,
        "expected": expected,
        "found": names,
        "shape": "drift" if drifted else "canonical",
        "findings": findings,
        "counts": {name: rows(name) for name in names},
    }
