"""Structural CLI/MCP anti-drift gate (plan-3, ch-bsd #sk-3).

1. Every MCP tool IS a verb and every verb IS an MCP tool — `set(TOOLS) ==
   set(VERBS)`; a tool handler that bypasses the verb registry cannot exist.
2. Every tool schema is EXACTLY the verb-generated one (aliases included, since
   the generator owns them now).
3. Every verb names its CLI twin in `verbs.CLI_MAP` (or an explicit
   `None` + reason); every named click path resolves.
4. For every parameter a verb shares with its paired click command, the click
   default equals the verb default.
"""
from __future__ import annotations

import refmatrix.mcp as mcp
from refmatrix import verbs
from refmatrix.cli import main as cli_main

EFFECTIVE_DEFAULTS = {
    "rmx_context": {"max_entities": 20, "max_tokens": 4000},
}
# verb -> (click path, {verb_param: click_param}, verb params with no CLI twin)
PAIRING = {
    "rmx_context": (("context",), {"ref": "symbol"}, {"linkage"}),
    "rmx_query": (("query",), {"dsl": "expr"}, {"dsl"}),
    "rmx_memory_add": (("memory", "add"), {}, {"tags", "protect"}),
    "rmx_memory_recall": (("memory", "recall"), {},
                          {"kinds", "exclude_mtype", "rerank", "since_seconds",
                           "query", "scope", "fuse", "k", "since", "subject",
                           "degree", "include_session", "recent", "session_start"}),
    "rmx_ingest": (("ingest",), {}, {"path", "mode", "kinds", "limit", "rebuild", "partition"}),
    "rmx_save_state": (("save-state",), {}, {"session"}),
    "rmx_projects": (("projects",), {}, set()),
    "rmx_locate": (("locate",), {}, {"file", "keywords", "n"}),
    "rmx_recall_state": (("recall-state",), {}, {"session"}),
    "rmx_ingest_status": (("ingest-status",), {}, {"job_id", "since_seq", "limit"}),
    "rmx_bus_pub": (("bus", "pub"), {}, {"channel", "body", "type", "sender", "project", "reply_to"}),
    "rmx_bus_history": (("bus", "history"), {}, {"channel", "n"}),
}


def _click_cmd(path):
    cmd = cli_main
    for name in path:
        cmd = cmd.commands[name]  # type: ignore[attr-defined]
    return cmd


def _click_defaults(cmd) -> dict:
    return {p.name: p.default for p in cmd.params}


def test_tools_and_verbs_are_the_same_set():
    assert set(mcp.TOOLS) == set(verbs.VERBS), (
        sorted(set(mcp.TOOLS) ^ set(verbs.VERBS)))


def test_every_tool_dispatches_to_its_verb():
    for name, t in mcp.TOOLS.items():
        assert getattr(t["fn"], "verb_name", None) == name, name


def test_tool_schemas_are_exactly_the_generated_ones():
    for name, v in verbs.VERBS.items():
        assert mcp.TOOLS[name]["schema"] == v.schema, name
        assert mcp.TOOLS[name]["description"] == v.description, name


def test_schema_exposes_every_verb_kwarg_and_alias():
    for name, v in verbs.VERBS.items():
        for param in v.defaults:
            assert param in v.schema["properties"], (name, param)
        for alias in v.aliases:
            assert alias in v.schema["properties"], (name, alias)


def test_every_verb_names_its_cli_twin():
    missing = [n for n in verbs.VERBS if n not in verbs.CLI_MAP]
    assert not missing, missing
    for name, path in verbs.CLI_MAP.items():
        if path is None:
            assert name in verbs.MCP_ONLY, f"{name}: None in CLI_MAP needs an MCP_ONLY reason"
            continue
        _click_cmd(path)  # raises KeyError if the command does not exist


def test_click_defaults_match_verb_defaults():
    mismatches = []
    for vname, (path, renames, no_twin) in PAIRING.items():
        v = verbs.VERBS[vname]
        cdefs = _click_defaults(_click_cmd(path))
        eff = EFFECTIVE_DEFAULTS.get(vname, {})
        for param, vdefault in v.defaults.items():
            if param in no_twin:
                continue
            if vdefault is None and param in eff:
                vdefault = eff[param]
            cname = renames.get(param, param)
            if cname not in cdefs:
                mismatches.append(f"{vname}.{param}: no click option '{cname}' on {'/'.join(path)}")
                continue
            cdefault = cdefs[cname]
            if isinstance(vdefault, tuple):
                vdefault = list(vdefault)
            if isinstance(cdefault, tuple):
                cdefault = list(cdefault)
            if cdefault != vdefault:
                mismatches.append(f"{vname}.{param}: verb default {vdefault!r} != CLI default {cdefault!r}")
    assert not mismatches, "\n" + "\n".join(mismatches)


def test_payload_query_uses_expr():
    assert verbs.payload_query("a AND b") == {"expr": "a AND b"}


def test_payload_context_explicitness_tracks_none_sentinels():
    p = verbs.payload_context("x")
    assert p["entities_explicit"] is False and p["tokens_explicit"] is False
    assert "max_entities" not in p
    p2 = verbs.payload_context("x", max_entities=5, max_tokens=100)
    assert p2["entities_explicit"] is True and p2["max_entities"] == 5
    assert p2["tokens_explicit"] is True and p2["max_tokens"] == 100


def test_alias_args_reach_the_verb_param():
    """`from` (a Python keyword) is a documented tool arg for rmx_bus_pub; the
    generator maps it to the verb's `sender` and exposes it in the schema."""
    v = verbs.VERBS["rmx_bus_pub"]
    assert v.aliases.get("from") == "sender"
    assert "from" in v.schema["properties"]
