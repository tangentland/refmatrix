"""bug-197: an unknown `compiled_scope` must be ONE scope's record, never the
whole partition verdict.

RED first (ch-bsd 26.6 r2 #m-1-r2, 2026-11-10). `Store._memory_compile_status`
raised `ValueError` on a compiled subject whose `compiled_scope` this rmx does not
know. It runs inside `derive_status`, so the raise took the WHOLE partition
verdict with it: ping health set `derive_error`, `rmx daemon status` printed
`derive: unknown`, and the `derive_status` op and `rmx derive status` failed. The
row is reachable after a rollback from a release that writes a new scope, or by a
hand-edited row. Fail-closed belongs on the one scope record:
`scopes[<name>] = {unknown: true, needs_compile: true}`, printed as
`scope <name>: unknown to this rmx`.

The probe shape is the auditor's (`test_bsd266r2_probe.py`, scratch clone): a
hand-written subject row with `compiled_scope: "future_scope"`.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
from pathlib import Path

import pytest

from refmatrix import discovery
from refmatrix import daemon as dm
from refmatrix.store import Store

import tests.test_memory_compile_scope as T
from tests.test_memory_compile_scope import spawn  # noqa: F401 — the real-daemon fixture

if importlib.util.find_spec("lance") is None:
    pytest.skip("lance not installed", allow_module_level=True)

UNKNOWN = "future_scope"
UNKNOWN_LINE = f"scope {UNKNOWN}: unknown to this rmx"


def _known_subject(s: Store, part: str) -> None:
    """A memory-scope compiled subject with NO stamp: the memory scope's own
    `needs_compile` is True, so the test can see whether the unknown row moved it."""
    with s.with_partition(part):
        s.upsert_subject("daemon_ops", metadata={
            "compiled_by": "memory-compile", "compiled_scope": "memory",
            "compiled_at": 1.0})
        s.flush_fragments()


def _unknown_subjects(s: Store, part: str, n: int = 2) -> None:
    with s.with_partition(part):
        for i in range(n):
            s.upsert_subject(f"future_{i}", metadata={
                "compiled_by": "memory-compile", "compiled_scope": UNKNOWN,
                "compiled_at": 2.0})
        s.flush_fragments()


@pytest.fixture
def store():
    base = Path(tempfile.mkdtemp(prefix="b197-"))
    root = base / "proj" / ".refmatrix"
    root.mkdir(parents=True)
    s = Store(root)
    s.init()
    part = discovery.store_name(root)
    T._seed_scopes(s, part)
    try:
        yield s, part
    finally:
        s.close()
        shutil.rmtree(base, ignore_errors=True)


# ------------------------------------------------------------- the store ---

def test_derive_status_never_raises_on_an_unknown_compile_scope(store):
    s, part = store
    _unknown_subjects(s, part)
    with s.with_partition(part):
        st = s.derive_status()      # HEAD: ValueError("... unknown compiled_scope ...")
    scopes = st["memory_compile"]["scopes"]
    assert UNKNOWN in scopes, sorted(scopes)
    rec = scopes[UNKNOWN]
    assert rec.get("unknown") is True, rec
    assert rec.get("needs_compile") is True, rec


def test_the_known_scopes_are_still_reported_beside_the_unknown_one(store):
    s, part = store
    _unknown_subjects(s, part)
    with s.with_partition(part):
        scopes = s.derive_status()["memory_compile"]["scopes"]
    for sc in ("memory", "pattern"):
        assert sc in scopes, sorted(scopes)
        assert not scopes[sc].get("unknown"), (sc, scopes[sc])


def test_an_unknown_scope_moves_no_other_verdict_field(store):
    """Every field outside the unknown record is what it was before the row
    landed: the partition verdict, the top-level (memory-scope) compile fields,
    and each known scope's record."""
    s, part = store
    _known_subject(s, part)
    with s.with_partition(part):
        before = s.derive_status()
    _unknown_subjects(s, part)
    with s.with_partition(part):
        after = s.derive_status()

    def _verdict(st):
        return {k: v for k, v in st.items() if k != "memory_compile"}

    assert json.dumps(_verdict(after), sort_keys=True, default=str) == \
        json.dumps(_verdict(before), sort_keys=True, default=str)
    mc_b, mc_a = before["memory_compile"], after["memory_compile"]
    top_b = {k: v for k, v in mc_b.items() if k != "scopes"}
    top_a = {k: v for k, v in mc_a.items() if k != "scopes"}
    assert top_a == top_b, (top_b, top_a)
    assert top_a["needs_compile"] is True and top_a["compiled_subjects"] == 1, top_a
    for sc, rec in mc_b["scopes"].items():
        assert mc_a["scopes"][sc] == rec, (sc, rec, mc_a["scopes"][sc])


# ----------------------------------------------------------- the renderer ---

def test_the_warning_names_the_unknown_scope(store):
    from refmatrix.cli import render_memory_compile_warning

    s, part = store
    _known_subject(s, part)
    _unknown_subjects(s, part)
    with s.with_partition(part):
        st = s.derive_status()
    out = render_memory_compile_warning(st, partition=part)
    assert UNKNOWN_LINE in out, out
    # the known scope's own line still prints beside it
    assert "scope memory:" in out, out


def test_the_warning_renders_a_hand_built_unknown_record():
    """The renderer contract on its own, as the wire carries it: a daemon that
    reports the record prints the line even if no store is involved."""
    from refmatrix.cli import render_memory_compile_warning

    status = {"memory_compile": {
        "needs_compile": False, "scopes": {
            "memory": {"needs_compile": False},
            UNKNOWN: {"unknown": True, "needs_compile": True}}}}
    out = render_memory_compile_warning(status)
    assert UNKNOWN_LINE in out, out
    assert "scope memory" not in out, out


# ------------------------------------------- the daemon surfaces (real) ---

def _pre(s: Store, part: str) -> None:
    _known_subject(s, part)
    _unknown_subjects(s, part)


def test_the_derive_status_op_answers(spawn):  # noqa: F811
    ctx = spawn(T._seed_scopes, pre=_pre)
    r = dm.call(ctx.root, "derive_status", {"all": True}, timeout=30, retries=0)
    assert r.get("ok"), r
    parts = r["result"]["partitions"]
    rec = parts[ctx.part]["memory_compile"]["scopes"][UNKNOWN]
    assert rec.get("unknown") is True and rec.get("needs_compile") is True, rec


def test_ping_health_keeps_the_derive_verdict(spawn):  # noqa: F811
    ctx = spawn(T._seed_scopes, pre=_pre)
    r = dm.call(ctx.root, "stats", {"include_health": True}, timeout=60, retries=0)
    assert r.get("ok"), r
    h = r["result"]["health"]
    assert "derive_error" not in h, h.get("derive_error")
    assert "derive" in h, sorted(h)


def test_daemon_status_prints_the_unknown_line_and_a_known_verdict(spawn):  # noqa: F811
    ctx = spawn(T._seed_scopes, pre=_pre)
    out = T._ok("daemon", "status")
    assert "derive: unknown" not in out, out
    assert UNKNOWN_LINE in out, out


def test_rmx_derive_status_answers(spawn):  # noqa: F811
    ctx = spawn(T._seed_scopes, pre=_pre)
    out = T._ok("derive", "status", "--json")
    assert "unknown compiled_scope" not in out, out
    assert UNKNOWN in out, out
