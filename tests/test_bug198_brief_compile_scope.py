"""bug-198: `memory brief`'s compile scope gets its own key, distinct from
recall's `scope`.

RED first (ch-bsd 26.6 r2 #m-2-r2, 2026-11-10). The brief action rode
`rmx_memory`'s `scope` parameter for its COMPILE scope (`memory | pattern`)
while recall uses the same parameter for `project | global | both`; the schema
documented neither meaning, and the CLI `memory brief` had no `--scope`, so MCP
could brief the pattern corpus and the CLI could not. One parameter name was
carrying two vocabularies.

Contract (bug-198 Fix column):
  * the brief action takes `compile_scope` (memory | pattern), and recall's
    `scope` no longer reaches the brief op as a compile scope;
  * `rmx memory brief --scope memory|pattern` passes it (and `--compile` plans
    that same scope: one corpus for all four detectors, #rm-one-corpus);
  * the generated MCP schema describes both keys;
  * an invalid value fails loudly, before any daemon call.
"""
from __future__ import annotations

import inspect
import json

import pytest
from click.testing import CliRunner

from refmatrix import consolidate, verbs
from refmatrix import cli as cli_mod
import refmatrix.mcp as mcp


@pytest.fixture(autouse=True)
def _no_live_cli_log(monkeypatch):
    """The CLI's `_memory_intent` writes into the LIVE cli.log otherwise (the
    sibling fixture in test_brief_surfaces.py)."""
    from refmatrix import telemetry
    monkeypatch.setattr(telemetry, "log_cli_intent", lambda root, **kw: None, raising=False)
    monkeypatch.setattr(telemetry, "log_cli_invocation", lambda root, **kw: None,
                        raising=False)


# ---------------------------------------------------------------- the verb ---

def test_the_memory_verb_has_a_compile_scope_parameter():
    params = inspect.signature(verbs.VERBS["rmx_memory"].fn).parameters
    assert "compile_scope" in params, sorted(params)


@pytest.fixture
def op_calls(tmp_path, monkeypatch):
    """Record what the verb sends to the daemon, with no daemon: the brief
    action's routing is the unit here, not the op."""
    root = tmp_path / "proj" / ".refmatrix"
    root.mkdir(parents=True)
    seen: list = []
    monkeypatch.setattr(verbs, "memory_partition", lambda r, **kw: "proj")
    monkeypatch.setattr(verbs, "require_daemon", lambda r, **kw: {"up": True})

    def _call(r, op, args, **kw):
        seen.append((op, dict(args)))
        return {"briefs": [], "stats": {}, "names": {}}
    monkeypatch.setattr(verbs, "_call", _call)
    return root, seen


def _brief_args(seen) -> dict:
    ops = [a for op, a in seen if op == "memory_brief"]
    assert ops, f"the verb never issued memory_brief: {seen}"
    return ops[-1]


@pytest.mark.parametrize("sc", ["memory", "pattern"])
def test_compile_scope_reaches_the_brief_op(op_calls, sc):
    root, seen = op_calls
    verbs.memory(root, "brief", compile_scope=sc)
    assert _brief_args(seen).get("scope") == sc, seen


def test_recalls_scope_never_becomes_the_brief_compile_scope(op_calls):
    """`scope` is recall's `project|global|both`. Sent with the brief action it
    must not select the compile corpus — the defect was exactly that it did."""
    root, seen = op_calls
    verbs.memory(root, "brief", scope="pattern")
    assert _brief_args(seen).get("scope") in (None, consolidate.DEFAULT_SCOPE), seen


@pytest.mark.parametrize("bad", ["both", "project", "bogus"])
def test_an_invalid_compile_scope_fails_loudly_before_the_daemon(op_calls, bad):
    root, seen = op_calls
    with pytest.raises(verbs.VerbArgsError) as ei:
        verbs.memory(root, "brief", compile_scope=bad)
    assert "compile_scope" in str(ei.value), str(ei.value)
    assert not [op for op, _ in seen if op == "memory_brief"], seen


def test_the_mcp_tool_rejects_an_invalid_compile_scope(op_calls):
    """The transport path (`Verb.run`, which MCP calls) fails the same way."""
    root, seen = op_calls
    with pytest.raises(verbs.VerbArgsError):
        verbs.VERBS["rmx_memory"].run(root, {"action": "brief", "compile_scope": "both"})
    assert not seen, seen


# -------------------------------------------------------------- the schema ---

def _props() -> dict:
    return mcp.TOOLS["rmx_memory"]["schema"]["properties"]


def test_the_mcp_schema_describes_compile_scope():
    props = _props()
    assert "compile_scope" in props, sorted(props)
    frag = props["compile_scope"]
    text = json.dumps(frag)
    assert "memory" in text and "pattern" in text, frag
    assert frag.get("description"), frag
    assert "brief" in frag["description"], frag


def test_the_mcp_schema_describes_recalls_scope():
    frag = _props()["scope"]
    desc = frag.get("description") or ""
    assert desc, frag
    for word in ("recall", "project", "global", "both"):
        assert word in desc, (word, desc)
    # and it no longer claims (or is silent about) the brief compile scope
    assert "pattern" not in desc, desc


# ----------------------------------------------------------------- the CLI ---

@pytest.fixture
def cli_seen(tmp_path, monkeypatch):
    root = tmp_path / "proj" / ".refmatrix"
    root.mkdir(parents=True)
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    seen: list = []

    def fake_memory(r, action, **kw):
        seen.append({"action": action, **kw})
        return {"briefs": [], "stats": {"skipped": 0, "briefs": 0}}
    monkeypatch.setattr(verbs, "memory", fake_memory)
    return seen


def test_cli_brief_defaults_to_the_memory_compile_scope(cli_seen):
    r = CliRunner().invoke(cli_mod.main, ["memory", "brief", "--json"])
    assert r.exit_code == 0, r.output
    assert cli_seen[-1].get("compile_scope") == consolidate.DEFAULT_SCOPE, cli_seen
    assert "scope" not in cli_seen[-1], cli_seen


def test_cli_brief_scope_pattern_reaches_the_verb_as_compile_scope(cli_seen):
    r = CliRunner().invoke(cli_mod.main, ["memory", "brief", "--scope", "pattern", "--json"])
    assert r.exit_code == 0, r.output
    assert cli_seen[-1].get("compile_scope") == "pattern", cli_seen
    assert "scope" not in cli_seen[-1], cli_seen


def test_cli_brief_compile_plans_the_same_scope(cli_seen, monkeypatch):
    """One corpus for all four detectors: `--compile --scope pattern` plans the
    pattern corpus and briefs it, never a memory plan under a pattern brief."""
    planned = []

    def fake_plan(store, *, scope, **kw):
        planned.append(scope)
        return {"clusters": [], "crosscutting": [], "unclustered": [], "stats": {},
                "params": {"scope": scope}}
    monkeypatch.setattr(consolidate, "compile_memories", fake_plan)
    monkeypatch.setattr(cli_mod, "_read_store", lambda *a, **k: object())
    r = CliRunner().invoke(cli_mod.main,
                           ["memory", "brief", "--compile", "--scope", "pattern", "--json"])
    assert r.exit_code == 0, r.output
    assert planned == ["pattern"], planned
    assert cli_seen[-1].get("compile_scope") == "pattern", cli_seen


def test_cli_brief_rejects_an_invalid_scope(cli_seen):
    """A click Choice: `both` (recall's vocabulary) is refused BY VALUE. HEAD
    also exits 2, but for `No such option: --scope` — that is not this check."""
    r = CliRunner().invoke(cli_mod.main, ["memory", "brief", "--scope", "both", "--json"])
    assert "No such option" not in r.output, r.output
    assert r.exit_code == 2, r.output
    assert "Invalid value" in r.output and "both" in r.output, r.output
    assert not cli_seen, cli_seen
