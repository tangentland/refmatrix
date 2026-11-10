"""Task 3.7 batch A — the shared verb-layer infrastructure (RED).

Spec: workflow/plans/plan-3-verbs-parity-tasks/task-3.7-verb-it-backlog.md
  #c3   `verbs.snapshot_read(root, fn, *, partition)` — a per-call read-only open of
        `catalog.read.duckdb`, never cached, never the writer slot; daemon up with no
        snapshot is BUSY worded as a read; a truly ABSENT daemon opens the store
        read-only in-process EVEN when an old snapshot exists; busy is never absent;
        the result carries `source`.
  #c4a  `verbs.local_write(root, fn, *, partition)` — the ONE in-process write
        helper for the absent-daemon case; a read-then-write call does its reads on
        the writer handle (bug-135 `StaleDuckDBInstance`).
  #c6   `verbs.ACTION_DEFAULTS[(verb, action)]` resolves a param whose default
        differs by action; `rmx_focus.top` is `int | None = None`.
  #c1   every new verb is an MCP tool generated from its signature.

Interpretation (named in the RED report): `snapshot_read` returns `fn`'s dict with a
`source` key added ("the result dict carries source").
"""
from __future__ import annotations

import inspect
import typing
from pathlib import Path

import pytest

import refmatrix.mcp as mcp
from refmatrix import discovery, verbs
from refmatrix.store import Store
from tests.task3_7_helpers import (add_entities, init_store, make_snapshot, rm,
                                   short_root)
from tests.test_plan2_remedy import _PingOnlyDaemon, _SilentDaemon


@pytest.fixture
def absent_store(monkeypatch):
    """A real store with NO daemon (no pid, no socket): the bootstrap case."""
    monkeypatch.delenv("RMX_PARTITION", raising=False)
    base, root = short_root("r37a-")
    init_store(root, [("concept", "alpha")])
    yield root
    rm(base)


def _has(name):
    return lambda s: {"found": s.get_entity("concept", name) is not None}


# ---- C3: snapshot_read ------------------------------------------------------


def test_snapshot_read_exists_with_the_specified_signature():
    sig = inspect.signature(verbs.snapshot_read)
    params = list(sig.parameters)
    assert params[:2] == ["root", "fn"], params
    assert sig.parameters["partition"].kind is inspect.Parameter.KEYWORD_ONLY


def test_absent_daemon_without_snapshot_reads_in_process_read_only(absent_store):
    p = discovery.store_name(absent_store)
    wrote: list = []

    def fn(s):
        try:
            s.upsert_entity("concept", "sneaky")
            wrote.append("write accepted")
        except Exception as e:  # noqa: BLE001 — the read-only refusal is the point
            wrote.append(type(e).__name__)
        return {"found": s.get_entity("concept", "alpha") is not None}
    out = verbs.snapshot_read(absent_store, fn, partition=p)
    assert out["found"] is True, out
    assert out["source"] == "in-process", out
    assert wrote and wrote[0] != "write accepted", "snapshot_read handed fn a WRITABLE store"


def test_absent_daemon_with_a_stale_snapshot_still_reads_in_process(absent_store):
    """r2 S2: with no daemon the snapshot is stale; a row written in-process after
    it must be visible to the next read."""
    p = discovery.store_name(absent_store)
    make_snapshot(absent_store)
    add_entities(absent_store, [("concept", "late")])
    out = verbs.snapshot_read(absent_store, _has("late"), partition=p)
    assert out == {"found": True, "source": "in-process"}, out


def test_daemon_up_without_snapshot_is_busy_worded_as_a_read(monkeypatch):
    monkeypatch.delenv("RMX_PARTITION", raising=False)
    d = _PingOnlyDaemon(seeded=True)
    try:
        assert not (d.root / "catalog.read.duckdb").exists()
        called: list = []
        with pytest.raises(verbs.VerbBusyError) as ei:
            verbs.snapshot_read(d.root, lambda s: called.append(1) or {},
                                partition=discovery.store_name(d.root))
        assert "no read snapshot yet" in str(ei.value), str(ei.value)
        assert "write" not in str(ei.value).lower(), ("a read must not be worded as a write",
                                                      str(ei.value))
        assert called == []
    finally:
        d.close()


def test_busy_daemon_without_snapshot_is_busy_never_in_process(monkeypatch):
    monkeypatch.delenv("RMX_PARTITION", raising=False)
    d = _SilentDaemon(seeded=True)
    try:
        called: list = []
        with pytest.raises(verbs.VerbBusyError):
            verbs.snapshot_read(d.root, lambda s: called.append(1) or {},
                                partition=discovery.store_name(d.root))
        assert called == [], "a busy daemon was treated as absent (in-process open)"
    finally:
        d.close()


def test_busy_daemon_with_snapshot_reads_the_snapshot_not_the_primary(monkeypatch):
    monkeypatch.delenv("RMX_PARTITION", raising=False)
    d = _SilentDaemon()
    try:
        init_store(d.root, [("concept", "alpha")])
        make_snapshot(d.root)
        add_entities(d.root, [("concept", "after_snap")])   # primary only
        p = discovery.store_name(d.root)
        out = verbs.snapshot_read(d.root, _has("alpha"), partition=p)
        assert out == {"found": True, "source": "snapshot"}, out
        out2 = verbs.snapshot_read(d.root, _has("after_snap"), partition=p)
        assert out2 == {"found": False, "source": "snapshot"}, (
            "a busy daemon's read reached the primary catalog", out2)
    finally:
        d.close()


def test_snapshot_read_opens_per_call_and_never_caches(monkeypatch):
    """bug-136: `search.cached_replica` caches a Store for the life of `rmx mcp`.
    A re-written snapshot must be seen by the very next call."""
    monkeypatch.delenv("RMX_PARTITION", raising=False)
    d = _SilentDaemon()
    try:
        init_store(d.root, [("concept", "alpha")])
        make_snapshot(d.root)
        p = discovery.store_name(d.root)
        assert verbs.snapshot_read(d.root, _has("fresh"), partition=p)["found"] is False
        add_entities(d.root, [("concept", "fresh")])
        make_snapshot(d.root)
        assert verbs.snapshot_read(d.root, _has("fresh"), partition=p)["found"] is True, (
            "snapshot_read served a cached handle over a rotated snapshot")
    finally:
        d.close()


def test_snapshot_read_refuses_a_replica_path_that_is_the_writer_slot(monkeypatch):
    """C3: "refuses any file that is not the replica (never the active writer
    slot)". A `catalog.read.duckdb` symlinked at the primary is the writer's file."""
    monkeypatch.delenv("RMX_PARTITION", raising=False)
    d = _SilentDaemon()
    try:
        init_store(d.root, [("concept", "alpha")])
        primary = Path(Store(d.root).db_path)
        (d.root / "catalog.read.duckdb").symlink_to(primary)
        called: list = []
        with pytest.raises(verbs.VerbError):
            verbs.snapshot_read(d.root, lambda s: called.append(1) or {},
                                partition=discovery.store_name(d.root))
        assert called == [], "fn ran against the writer slot"
    finally:
        d.close()


def test_snapshot_read_honours_the_partition(absent_store):
    add_entities(absent_store, [("concept", "only_in_px")], partition="px")
    out = verbs.snapshot_read(absent_store, _has("only_in_px"), partition="px")
    assert out["found"] is True, out
    out2 = verbs.snapshot_read(absent_store, _has("only_in_px"),
                               partition=discovery.store_name(absent_store))
    assert out2["found"] is False, out2


# ---- C4a: local_write -------------------------------------------------------


def test_local_write_exists_with_the_specified_signature():
    sig = inspect.signature(verbs.local_write)
    assert list(sig.parameters)[:2] == ["root", "fn"]
    assert sig.parameters["partition"].kind is inspect.Parameter.KEYWORD_ONLY


def test_local_write_writes_in_process_and_closes_the_writer(absent_store):
    """The `_memory_write` local-fallback shape: open read-write, run fn, CLOSE.
    A leaked writer handle makes the next read-only open in this process raise
    bug-135's `StaleDuckDBInstance … already attached`."""
    out = verbs.local_write(absent_store, lambda s: {"id": s.upsert_entity("concept", "w1")},
                            partition="pw")
    assert out["source"] == "in-process", out
    assert isinstance(out["id"], int)
    ro = Store(absent_store, read_only=True)
    try:
        with ro.with_partition("pw"):
            assert ro.get_entity("concept", "w1") is not None
    finally:
        ro.close()


def test_read_then_write_in_one_local_write_call_with_a_stale_snapshot(absent_store):
    """r3 M3: the reads happen inside `local_write`'s fn on the writer handle —
    never a `snapshot_read` in-process handle held while the writer opens."""
    p = discovery.store_name(absent_store)
    make_snapshot(absent_store)

    def fn(s):
        before = s.get_entity("concept", "alpha") is not None
        s.upsert_entity("concept", "beta")
        return {"before": before, "after": s.get_entity("concept", "beta") is not None}
    out = verbs.local_write(absent_store, fn, partition=p)
    assert out == {"before": True, "after": True, "source": "in-process"}, out


# ---- C6: action defaults -----------------------------------------------------


def test_action_defaults_resolve_the_focus_top_conflict():
    """r1 S1: focus `top` is 20 for `context` and 60 for `topics`."""
    ad = verbs.ACTION_DEFAULTS
    assert ad[("rmx_focus", "context")]["top"] == 20
    assert ad[("rmx_focus", "topics")]["top"] == 60
    assert ad[("rmx_focus", "tail")]["n"] == 20
    sig = inspect.signature(verbs.focus)
    assert sig.parameters["top"].default is None, "a per-action default is typed X | None = None"
    hint = typing.get_type_hints(verbs.focus)["top"]
    assert type(None) in typing.get_args(hint), hint


def test_action_defaults_keys_name_real_verbs_and_actions():
    for (vname, action), params in verbs.ACTION_DEFAULTS.items():
        assert vname in verbs.VERBS, vname
        hint = typing.get_type_hints(verbs.VERBS[vname].fn).get("action")
        assert hint is not None and action in typing.get_args(hint), (vname, action)
        sig = inspect.signature(verbs.VERBS[vname].fn)
        for p in params:
            assert p in sig.parameters, f"{vname}.{action}: {p} is not a verb param"


# ---- C1: the batch-A verbs are MCP tools generated from their signatures -----

_BATCH_A_ACTIONS = {
    "rmx_focus": {"context", "tail", "show", "topics", "subject", "subjects", "clear_subject",
                  "composite", "export", "detour", "detours", "return", "clear"},
    "rmx_curate": {"protect", "unprotect", "noise", "unnoise", "forget"},
    "rmx_taxonomy": {"list", "add", "remove"},
    "rmx_curator": {"status", "drain"},
}


@pytest.mark.parametrize("vname", sorted(_BATCH_A_ACTIONS))
def test_batch_a_verb_is_a_generated_mcp_tool_with_its_actions(vname):
    assert vname in verbs.VERBS, f"{vname} is not a verb"
    assert vname in mcp.TOOLS, f"{vname} is not an MCP tool"
    schema = mcp.TOOLS[vname]["schema"]
    assert schema == verbs.VERBS[vname].schema
    assert set(schema["properties"]["action"]["enum"]) == _BATCH_A_ACTIONS[vname]


def test_rmx_focus_defaults_to_context_for_existing_mcp_callers():
    assert verbs.VERBS["rmx_focus"].defaults.get("action") == "context"


def test_curate_forget_defaults_to_a_dry_run_and_no_broad():
    d = verbs.VERBS["rmx_curate"].defaults
    assert d.get("dry_run") is True and d.get("broad") is False, d

