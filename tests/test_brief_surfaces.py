"""`rmx memory brief` reaches the store through the verb layer, once.

RED first for task 8.2 (plan-8). The anti-drift rule: a capability is a VERB
first, and CLI + MCP are thin adapters that render. The failure this guards is
a third implementation growing quietly beside the other two — the same class of
bug as `feedback_reuse_shared_stoplist` (one junk-token bug, four call sites).

Parity here is compared over the FULL parameter set, not by checking the action
name appears on both surfaces. An existence check dressed as a parity gate is a
recorded failure of this project's own review process: plan-3's parity test
excluded every `memory_recall` parameter and hid a `k` default mismatch (8 vs
10) behind a green run. So the count of compared keys is asserted against the
count of parameters — a test that silently compares a subset fails here.
"""
from __future__ import annotations

import threading

import pytest

@pytest.fixture(autouse=True)
def _no_live_cli_log(monkeypatch):
    """These tests invoke the CLI, whose `_memory_intent` writes a
    phase:"start" row into the LIVE .refmatrix/cli.log before the body
    runs. Patched in test_context_cost.py two rounds ago and missed
    here — third round, third sibling call site (ch-bsd r3).
    """
    from refmatrix import telemetry
    monkeypatch.setattr(telemetry, "log_cli_intent",
                        lambda root, **kw: None, raising=False)
    monkeypatch.setattr(telemetry, "log_cli_invocation",
                        lambda root, **kw: None, raising=False)


from refmatrix import brief, consolidate, daemon as daemon_mod, verbs
import refmatrix.mcp as mcp


# Every parameter the `brief` action reads. `compile` (T0.5 R5.3, ch-bsd plan-8 r5 #s-4) is the
# verb-first plan switch: before it, only the CLI could reach `corroborated` / `singleton`,
# because only the CLI built the plan.
BRIEF_PARAMS = ("min_members", "min_dates", "min_mentions", "classes", "save", "compile",
                "compile_scope")
# verb param -> click param, where they are spelled differently
_CLICK_NAME = {"compile": "do_compile"}
# A verb default of None DEFERS; what it resolves to is what the CLI default must equal. Each
# key is a declared shape difference in test_verb_parity.SHAPE_DIFFERENCES (T0.5 R5.5).
_NONE_RESOLVES_TO = {"classes": (), "compile_scope": consolidate.DEFAULT_SCOPE}


# ── the verb exists and carries the whole surface ──────────────────────────

def test_brief_is_an_action_on_the_memory_verb():
    import typing
    hints = typing.get_type_hints(verbs.VERBS["rmx_memory"].fn)
    assert "brief" in typing.get_args(hints["action"])


def test_the_memory_verb_accepts_every_brief_parameter():
    params = verbs.VERBS["rmx_memory"].fn.__annotations__
    missing = [p for p in BRIEF_PARAMS if p not in params]
    assert not missing, f"verb cannot carry {missing}"


def test_the_generated_mcp_schema_exposes_every_brief_parameter():
    """MCP gets the surface from the verb; a hand-written schema would drift."""
    schema = mcp.TOOLS["rmx_memory"]["schema"]["properties"]
    missing = [p for p in BRIEF_PARAMS if p not in schema]
    assert not missing, f"MCP schema is missing {missing}"


def test_brief_routes_to_a_daemon_op_that_exists():
    assert verbs._MEMORY_OPS["brief"] == "memory_brief"
    assert "memory_brief" in daemon_mod.OPS


# ── parity over the FULL parameter set ─────────────────────────────────────

def test_cli_and_verb_agree_on_every_brief_default_not_a_subset():
    """plan-3's parity test compared zero of memory_recall's params and called
    itself a gate. Count what is compared -- and count it only where an assertion
    RUNS (T0.5 R5.5, ch-bsd plan-8 r5 #m-10): this loop used to bump `compared`
    and then `continue` past a None verb default, so `classes` counted as
    compared while nothing compared it, and mutation M7 (CLI `--class` defaulting
    to `("contradicted",)`) stayed green. A None default is now a declared shape
    difference with the value it resolves to, and that value is asserted."""
    from refmatrix.cli import main as cli_main
    from tests.test_verb_parity import SHAPE_DIFFERENCES

    cmd = cli_main
    for part in ("memory", "brief"):
        cmd = cmd.commands[part]
    # The values the command's callback RECEIVES with no options given. `p.default` is
    # click's `Sentinel.UNSET` for a `multiple=True` option without a default; the callback
    # gets `()` -- and with M7 it gets `("contradicted",)`.
    click_defaults = dict(cmd.make_context("brief", [], resilient_parsing=True).params)

    import inspect
    sig = inspect.signature(verbs.VERBS["rmx_memory"].fn)

    compared = 0
    bad = []
    for name in BRIEF_PARAMS:
        cname = _CLICK_NAME.get(name, name)
        if name not in sig.parameters:
            bad.append(f"{name}: the rmx_memory verb has no such parameter")
            continue
        if cname not in click_defaults:
            bad.append(f"{name}: `rmx memory brief` has no option {cname!r}")
            continue
        verb_default = sig.parameters[name].default
        click_default = click_defaults[cname]
        if verb_default is None:
            if ("rmx_memory", name) not in SHAPE_DIFFERENCES:
                bad.append(f"{name}: verb None vs click {click_default!r} is not a declared "
                           f"shape difference")
                continue
            verb_default = _NONE_RESOLVES_TO[name]
            if isinstance(click_default, list):
                click_default = tuple(click_default)
        if click_default != verb_default:
            bad.append(f"{name}: click={click_default!r} verb={verb_default!r}")
        compared += 1
    assert not bad, "\n" + "\n".join(bad)
    assert compared == len(BRIEF_PARAMS), (
        f"only {compared} of {len(BRIEF_PARAMS)} brief params were compared — "
        f"a parity test that checks a subset is not a parity test")


def test_the_cli_defaults_match_the_modules_stated_defaults():
    """One definition of 'what counts as corroborated'."""
    from refmatrix.cli import main as cli_main

    cmd = cli_main
    for part in ("memory", "brief"):
        cmd = cmd.commands[part]
    d = {p.name: p.default for p in cmd.params}
    assert d["min_members"] == brief.MIN_MEMBERS
    assert d["min_dates"] == brief.MIN_DATES
    assert d["min_mentions"] == brief.MIN_MENTIONS


# ── wiring, not existence ──────────────────────────────────────────────────

def test_the_cli_command_calls_the_verb_rather_than_reimplementing_it(monkeypatch):
    """Recorded call, not a grep. A twin that re-derives briefs itself fails."""
    from click.testing import CliRunner
    from refmatrix.cli import main as cli_main

    seen: list[dict] = []

    def fake_memory(root, action, **kw):
        seen.append({"action": action, **kw})
        return {"briefs": [], "stats": {"skipped": 0, "briefs": 0}}

    # The command imports `refmatrix.verbs` inside its body, so patching the
    # module attribute is what the running code will see.
    monkeypatch.setattr(verbs, "memory", fake_memory)

    res = CliRunner().invoke(cli_main, ["memory", "brief", "--json"])
    assert res.exit_code == 0, res.output
    assert seen and seen[0]["action"] == "brief", seen


def test_the_cli_never_opens_a_write_store_directly():
    """`feedback_store_calls_via_daemon`: writes go through the daemon op."""
    from refmatrix import cli as cli_mod
    from tests.conftest import source_of

    # Sliced by name from disk, not `inspect.getsource` — see #m-4-r4.
    src = source_of(cli_mod, "memory_brief")
    assert "Store(" not in src, "the CLI must not construct a Store"
    assert "_store(write" not in src


# ── the daemon op ──────────────────────────────────────────────────────────
#
# T0.5 (bsd-t05 r1 #m-1, 2026-11-19): these ran on fakes of `daemon._read_with_fallback`,
# `brief.compile_briefs` and the Store (registry rows 75-79). The read-path fake patched the very
# function whose use is the claim, and its 3-positional signature bent `src/` (GREEN `32c406e1`
# split one `private=` call to fit it). They now run the REAL op on r9 #b-2's real daemon shell
# (`_daemon`: real DuckDB, a real snapshot, a real `_MemMirror`), with a lock that records its
# acquisitions standing in for nothing: it IS the daemon's `_store_lock`, observed.

class _RecordingLock:
    """A real `threading.Lock` that counts acquisitions -- the writer lock, observed."""

    def __init__(self):
        self._lk = threading.Lock()
        self.acquired = 0

    def acquire(self, blocking=True, timeout=-1):
        ok = self._lk.acquire(blocking, timeout)
        self.acquired += int(ok)
        return ok

    def release(self):
        self._lk.release()

    def locked(self):
        return self._lk.locked()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *a):
        self.release()
        return False


def _brief_daemon(tmp_path):
    """The real shell, a corpus with one orphan concept, a fresh snapshot and mirror, and the
    writer lock swapped for its recording twin AFTER setup (setup's own locking is not the
    op's)."""
    from tests.test_read_path_partition_and_budget import _daemon

    d, s = _daemon(tmp_path)
    with s.with_partition("pa"):
        c = s.add_concept("orphan_term")
        for i in range(4):
            m = s.add_memory(f"om{i}", f"talks about orphan_term {i}", mtype="project")
            s.link("mentions", c, m)
        s.flush_fragments()
    s._conn.commit()
    d._snapshot_catalog(force=True)
    assert d._mem_mirror.refresh() is True
    d._store_lock = _RecordingLock()
    return d, s


def _memory_count(s, part):
    with s.with_partition(part):
        return len(s._read().execute(
            "SELECT e.id FROM entities e WHERE e.partition_id=? AND e.kind='memory'",
            (s._partition_id,)).fetchall())


def test_the_op_derives_briefs_on_the_read_path(tmp_path):
    """Derivation is a read: the op answers without taking the writer lock, the knobs reach
    the detectors (`params`), and the id->name map covers every evidence id (one closure,
    one snapshot: ch-bsd r3, answer to Q2)."""
    d, s = _brief_daemon(tmp_path)
    try:
        out = daemon_mod.OPS["memory_brief"](d, {"partition": "pa", "min_mentions": 3})
    finally:
        s.close()
    assert d._store_lock.acquired == 0, "a non-saving brief took the writer lock"
    assert [b["class"] for b in out["briefs"]] == ["orphan-concept"], out
    assert out["params"]["min_mentions"] == 3, out["params"]
    ev = {str(e) for b in out["briefs"] for e in b["evidence"]}
    assert ev and ev <= set(out["names"]), (ev, out["names"])
    assert out["saved"] == 0


def test_saving_writes_one_memory_row_per_brief_under_the_writer_lock(tmp_path):
    d, s = _brief_daemon(tmp_path)
    try:
        before = _memory_count(s, "pa")
        out = daemon_mod.OPS["memory_brief"](
            d, {"partition": "pa", "min_mentions": 3, "save": True})
        after = _memory_count(s, "pa")
        with s.with_partition("pa"):
            rows = s._read().execute(
                "SELECT mc.mtype FROM entities e JOIN memory_content mc "
                "ON mc.entity_id = e.id WHERE e.partition_id=? AND e.name LIKE 'brief-%'",
                (s._partition_id,)).fetchall()
    finally:
        s.close()
    assert out["saved"] == len(out["briefs"]) == 1, out
    assert after - before == 1
    assert [r[0] for r in rows] == ["brief/orphan-concept"], rows
    assert d._store_lock.acquired >= 1, "the save did not take the writer lock"
    assert d._snapshot_dirty is True, "the save did not request a snapshot"


def test_not_saving_writes_nothing(tmp_path):
    d, s = _brief_daemon(tmp_path)
    try:
        before = _memory_count(s, "pa")
        out = daemon_mod.OPS["memory_brief"](d, {"partition": "pa", "min_mentions": 3})
        after = _memory_count(s, "pa")
    finally:
        s.close()
    assert out["briefs"], "nothing derived; the test is vacuous"
    assert after == before
    assert out.get("saved", 0) == 0
    assert d._snapshot_dirty is False
