"""The conditions a measurement was taken under, recorded with the measurement.

On 2026-09-20 three numbers moved for reasons no harness recorded:

  * a stale `[UNVERIFIED]` daemon served a MemAware run and moved `scan-prompt`
    hit@20 0.433 -> 0.444 — same code on disk, same corpus, same 90 questions
    (bug-055). `rmx version -v` and `rmx hub status` describe the FLEET; a
    benchmark store outside it keeps whatever daemon was last started by hand.
  * `rmx context` measured 0.478/0.186 against a recorded 0.511/0.248, and the
    cause is STILL unattributed.
  * that 0.511 turned out to be a HELD-OUT question set, tabled beside numbers
    from a different one for weeks.

Plus the fleet survey (ADR-0003): four partition layouts, one store with no
vectors at all, one with session vectors nobody else has.

The pattern is not three bugs. It is that a number's PROVENANCE is not captured,
so longitudinal comparison — "scan went 0.200 -> 0.378 -> 0.444" — compares three
measurements under three unrecorded configurations. Paired comparisons within one
run survive, because every confound is shared by both arms; that is why the
in-harness bm25 baseline is the most trustworthy figure this project has.

So: `compose()` is pure and takes facts. `trustworthy` says whether a number may
be believed ABOUT THE VERSION IT NAMES. `key` says which other numbers it may sit
in a table with. `require()` is the gate a harness calls before scoring — and its
override records what it accepted rather than laundering it.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

# The axes that must match for two numbers to be comparable. Row COUNTS are
# deliberately absent: a corpus that grew is the same condition, and a key that
# changed on every ingest would make nothing ever comparable, which is the same
# as having no key.
KEY_AXES = (
    "daemon_version",
    "partition_shape",
    "vector_partitions",
    "derive_versions",
    "worker_topology",
    "corpus_encoding",
)

DEV_TREE_MARKER = "claude_tools"


class UntrustworthyMeasurement(RuntimeError):
    """Raised by `require()` when a harness would otherwise score a run whose
    conditions are not the ones it is about to claim."""


def compose(
    *,
    cli_version: str,
    daemon_version: "str | None",
    daemon_code: "str | None",
    store_root: str,
    partition_shape: str,
    partitions: "dict[str, int]",
    vector_partitions: "list[str]",
    derive_stale: bool,
    derive_versions: "dict[str, str]",
    worker_topology: str,
    corpus_encoding: str,
) -> "dict[str, Any]":
    """Build a fingerprint from measured facts. Pure: no I/O, no store."""
    reasons: list[str] = []

    if not daemon_version or not daemon_code:
        reasons.append(
            "the serving daemon is UNVERIFIED — it carries no code path, so the "
            "run describes an unknown version (bug-055)"
        )
    else:
        if daemon_version != cli_version:
            reasons.append(
                f"the serving daemon runs {daemon_version} while the CLI is "
                f"{cli_version}; the number describes the daemon, not the CLI"
            )
        if DEV_TREE_MARKER in daemon_code:
            reasons.append(
                "the serving daemon imports the DEV tree, so the number describes "
                "uncommitted code (feedback_deploy_tree_is_the_runtime)"
            )

    if derive_stale:
        stamped = ", ".join(f"{k}={v}" for k, v in sorted(derive_versions.items()))
        reasons.append(
            f"the derived graph is STALE ({stamped or 'unstamped'}) — a store decays "
            "while health reads green (bug-039)"
        )

    if partitions and not vector_partitions:
        reasons.append(
            "the store has rows and NO vectors, so every dense retrieval returns "
            "nothing while symbolic surfaces keep working"
        )

    axes = {
        "daemon_version": daemon_version,
        "partition_shape": partition_shape,
        "vector_partitions": sorted(vector_partitions),
        "derive_versions": dict(sorted(derive_versions.items())),
        "worker_topology": worker_topology,
        "corpus_encoding": corpus_encoding,
    }
    key = hashlib.sha256(
        json.dumps(axes, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:16]

    return {
        "key": key,
        "axes": axes,
        "trustworthy": not reasons,
        "reasons": reasons,
        "cli_version": cli_version,
        "daemon_version": daemon_version,
        "daemon_code": daemon_code,
        "store_root": store_root,
        "partitions": dict(partitions),
        "partition_shape": partition_shape,
        "vector_partitions": sorted(vector_partitions),
        "derive_stale": derive_stale,
        "worker_topology": worker_topology,
        "corpus_encoding": corpus_encoding,
    }


def same_conditions(a: dict, b: dict) -> bool:
    """May these two numbers sit in one table? Equal keys, nothing else."""
    return a.get("key") == b.get("key")


def require(fingerprint: dict, *, accept_reasons: "list[str] | None" = None) -> dict:
    """Gate a harness on its own conditions. Returns the fingerprint or raises.

    `accept_reasons` is for a DELIBERATE measurement of a known-bad condition —
    plan-13's arms measure a drifted corpus encoding on purpose. Each entry is a
    substring matched against the reasons; an override that matches nothing still
    raises, so a stale accept-list cannot silently wave through a NEW problem.
    The fingerprint stays `trustworthy: False`: the override records what was
    accepted, it does not launder it.
    """
    reasons = list(fingerprint.get("reasons") or [])
    if not reasons:
        return fingerprint

    accepted: list[str] = []
    remaining: list[str] = []
    for reason in reasons:
        if any(token.lower() in reason.lower() for token in (accept_reasons or [])):
            accepted.append(reason)
        else:
            remaining.append(reason)

    if remaining:
        raise UntrustworthyMeasurement(
            "refusing to score: "
            + "; ".join(remaining)
            + ". Fix the condition, or pass accept_reasons to record that this "
              "run measures it deliberately."
        )

    fingerprint["accepted_despite"] = accepted
    return fingerprint


def gather(root, *, corpus_encoding: str = "project") -> "dict[str, Any]":
    """Collect the facts for `compose()` from a live store. The I/O half.

    Every field is read from the surface that already reports it — `ping`
    carries `version`/`code_path`/`dev_tree` (the authority on what the SERVING
    process imported, which is the fact bug-055 turned on), `derive_status` is
    the detector shipped for bug-039, and the partition shape comes from the
    ADR-0003 audit. Nothing new is measured; what is new is that the number and
    its conditions are written down together.
    """
    from pathlib import Path

    from refmatrix import __version__ as _cli_version
    from refmatrix import daemon as daemon_mod
    from refmatrix import modelsrv
    from refmatrix.partitions import audit as _audit

    root = Path(root)
    daemon_version = daemon_code = None
    partition_shape = "unknown"
    partitions: dict[str, int] = {}
    vector_partitions: list[str] = []
    derive_stale = False
    derive_versions: dict[str, str] = {}

    if daemon_mod.ping(root):
        try:
            resp = daemon_mod.call(root, "ping", {}, timeout=5.0, retries=0)
            result = (resp or {}).get("result") or {}
            daemon_version = result.get("version")
            daemon_code = result.get("code_path")
        except Exception:                                  # noqa: BLE001
            pass
        try:
            resp = daemon_mod.call(root, "partition_audit", {}, timeout=15.0, retries=0)
            if resp.get("ok"):
                out = resp["result"]
                partition_shape = out["shape"]
                partitions = out.get("counts") or {}
                vector_partitions = [
                    p for p in out.get("found", [])
                    if not any(f["kind"] == "orphan-vectors" and f["name"] == p
                               for f in out.get("findings", []))
                    and p in _vector_dirs(root)
                ]
        except Exception:                                  # noqa: BLE001
            pass
        try:
            resp = daemon_mod.call(root, "derive_status", {}, timeout=10.0, retries=0)
            if resp.get("ok"):
                st = resp["result"]
                derive_stale = bool(st.get("stale"))
                derive_versions = {
                    p.get("pass_name", "?"): p.get("version", "?")
                    for p in (st.get("passes") or [])
                }
        except Exception:                                  # noqa: BLE001
            pass
    else:
        vector_partitions = _vector_dirs(root)

    try:
        topology = "shared" if modelsrv.shared_available() else "private"
    except Exception:                                      # noqa: BLE001
        topology = "unknown"

    return compose(
        cli_version=_cli_version,
        daemon_version=daemon_version,
        daemon_code=daemon_code,
        store_root=str(root),
        partition_shape=partition_shape,
        partitions=partitions,
        vector_partitions=vector_partitions,
        derive_stale=derive_stale,
        derive_versions=derive_versions,
        worker_topology=topology,
        corpus_encoding=corpus_encoding,
    )


def _vector_dirs(root) -> "list[str]":
    from pathlib import Path

    vec = Path(root) / "vectors"
    try:
        return sorted(p.name for p in vec.iterdir() if p.is_dir())
    except OSError:
        return []
