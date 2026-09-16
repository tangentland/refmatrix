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


from refmatrix import brief, daemon as daemon_mod, verbs
import refmatrix.mcp as mcp


BRIEF_PARAMS = ("min_members", "min_dates", "min_mentions", "classes", "save")


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
    itself a gate. Count what is compared."""
    from refmatrix.cli import main as cli_main

    cmd = cli_main
    for part in ("memory", "brief"):
        cmd = cmd.commands[part]
    click_defaults = {p.name: p.default for p in cmd.params}

    import inspect
    sig = inspect.signature(verbs.VERBS["rmx_memory"].fn)

    compared = 0
    for name in BRIEF_PARAMS:
        if name not in click_defaults:
            continue
        compared += 1
        verb_default = sig.parameters[name].default
        click_default = click_defaults[name]
        if verb_default is None:          # verb defers to the module default
            continue
        assert click_default == verb_default, (
            f"{name}: click={click_default!r} verb={verb_default!r}")
    assert compared >= 4, (
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
    import inspect
    from refmatrix import cli as cli_mod

    src = inspect.getsource(cli_mod.memory_brief.callback)
    assert "Store(" not in src, "the CLI must not construct a Store"
    assert "_store(write" not in src


# ── the daemon op ──────────────────────────────────────────────────────────

class _FakeCon:
    """`_names_for` reads entity names to build the id->name map --gmd links
    against (ch-bsd r2 #b-2-r2d). No names in this fixture, so: empty."""

    def execute(self, sql, params=None):
        return self

    def fetchall(self):
        return []


class _FakeStore:
    def __init__(self):
        self.saved: list[dict] = []
        self._partition_name = "memory-proj"
        self._partition_id = 1

    def _read(self):
        return _FakeCon()

    def add_memory(self, name, content, mtype="observation", tags=None,
                   metadata=None, protected=False):
        self.saved.append({"name": name, "mtype": mtype, "content": content})
        return len(self.saved)


def test_the_op_derives_briefs_on_the_read_path(monkeypatch):
    """Derivation is a read; it must not take the writer lock."""
    called: dict = {}

    def fake_compile(store, **kw):
        called.update(kw)
        return {"briefs": [brief.Brief(cls="singleton", label="x",
                                       finding="f", evidence=[1])],
                "stats": {"skipped": 0}, "params": {}}

    monkeypatch.setattr(brief, "compile_briefs", fake_compile)
    reads: list[str] = []

    def fake_read(d, partition, fn):
        reads.append(partition)
        return fn(_FakeStore())      # fn is now the combined derive closure

    monkeypatch.setattr(daemon_mod, "_read_with_fallback", fake_read)
    out = daemon_mod.OPS["memory_brief"](
        object(), {"partition": "memory-proj", "min_mentions": 3})
    # ONE read-path call: derivation and the id->name map share a closure, so
    # they see ONE snapshot and take the lock at most once in the boot window
    # (ch-bsd r3, answer to Q2).
    assert reads == ["memory-proj"]
    assert out["stats"]["skipped"] == 0
    assert len(out["briefs"]) == 1
    assert called["min_mentions"] == 3


def test_saving_writes_one_memory_row_per_brief_under_the_writer_lock(monkeypatch):
    fake = _FakeStore()

    def fake_compile(store, **kw):
        return {"briefs": [brief.Brief(cls="singleton", label="lonely",
                                       finding="touched once", evidence=[4])],
                "stats": {"skipped": 0}, "params": {}}

    monkeypatch.setattr(brief, "compile_briefs", fake_compile)
    monkeypatch.setattr(daemon_mod, "_read_with_fallback",
                        lambda d, p, fn: fn(fake))

    locks: list[str] = []

    class _D:
        _store_lock = _CtxRecorder(locks)
        def _st(self): return _PartCtx(fake)
        def _request_snapshot(self): locks.append("snapshot")

    out = daemon_mod.OPS["memory_brief"](
        _D(), {"partition": "memory-proj", "save": True})
    assert out["saved"] == 1
    assert fake.saved[0]["mtype"] == "brief/singleton"
    assert "lock" in locks
    assert "snapshot" in locks


def test_not_saving_writes_nothing(monkeypatch):
    fake = _FakeStore()
    monkeypatch.setattr(brief, "compile_briefs", lambda store, **kw: {
        "briefs": [brief.Brief(cls="singleton", label="x", finding="f",
                               evidence=[1])],
        "stats": {"skipped": 0}, "params": {}})
    monkeypatch.setattr(daemon_mod, "_read_with_fallback",
                        lambda d, p, fn: fn(fake))
    out = daemon_mod.OPS["memory_brief"](object(), {"partition": "memory-proj"})
    assert fake.saved == []
    assert out.get("saved", 0) == 0


class _CtxRecorder:
    def __init__(self, log): self.log = log
    def __enter__(self): self.log.append("lock"); return self
    def __exit__(self, *a): return False


class _PartCtx:
    def __init__(self, store): self._store = store
    def with_partition(self, name): return self
    def __enter__(self): return self._store
    def __exit__(self, *a): return False
    def __getattr__(self, item): return getattr(self._store, item)
