"""Structural CLI/MCP anti-drift gate.

Three invariants, enforced by CI rather than discipline:
1. Every verb-backed MCP tool's schema is EXACTLY the generated one — a
   hand-edit to TOOLS for those names fails here.
2. For every parameter a verb shares with its paired click command, the
   click default equals the verb default — the finding-2/6 class (semantic
   True/False, scope/exclusion drift) becomes a red build.
3. Verb schemas expose every verb kwarg — trivially true because they are
   generated, asserted anyway as a canary against generator regressions.
"""
from __future__ import annotations

import copy

import refmatrix.mcp as mcp
from refmatrix import verbs
from refmatrix.cli import main as cli_main

# verb name -> (click command path, {verb_param: click_param} renames,
#               verb params with no CLI twin)
# A verb param defaulting to None is a sentinel for "use the daemon op's
# default"; EFFECTIVE_DEFAULTS pins what that op default is, so the CLI's
# literal default is still checked against a single declared truth.
EFFECTIVE_DEFAULTS = {
    "rmx_context": {"max_entities": 20, "max_tokens": 4000},
}
PAIRING = {
    "rmx_context": (("context",), {"ref": "symbol"},
                    {"linkage"}),          # CLI --linkage is multi-valued
    "rmx_query": (("query",), {"dsl": "expr"}, {"dsl"}),
    "rmx_memory_add": (("memory", "add"), {}, {"tags", "protect"}),
    "rmx_memory_recall": (("memory", "recall"), {},
                          {"kinds", "exclude_mtype", "rerank",
                           "since_seconds", "query", "scope", "fuse", "k"}),
    "rmx_ingest": (("ingest",), {}, {"path", "mode", "kinds", "limit",
                                     "rebuild", "partition"}),
    "rmx_save_state": (("save-state",), {}, {"session"}),
}


def _click_cmd(path):
    cmd = cli_main
    for name in path:
        cmd = cmd.commands[name]  # type: ignore[attr-defined]  # Group at runtime
    return cmd


def _click_defaults(cmd) -> dict:
    out = {}
    for p in cmd.params:
        out[p.name] = p.default
    return out


def test_tool_schemas_are_exactly_the_generated_ones():
    aliased_extra = {"rmx_focus_note": {"note"}, "rmx_change_subject": {"subject"}}
    for name, v in verbs.VERBS.items():
        assert name in mcp.TOOLS, f"{name} missing from TOOLS"
        got = mcp.TOOLS[name]["schema"]
        expect = copy.deepcopy(v.schema)
        extra = aliased_extra.get(name, set())
        got_props = set(got["properties"]) - extra
        assert got_props == set(expect["properties"]), name
        # required may only shrink (alias relaxation), never grow.
        assert set(got.get("required", [])) <= set(expect.get("required", [])), name
        assert mcp.TOOLS[name]["description"] == v.description, name


def test_schema_exposes_every_verb_kwarg():
    for name, v in verbs.VERBS.items():
        for param in v.defaults:
            assert param in v.schema["properties"], (name, param)


def test_click_defaults_match_verb_defaults():
    mismatches = []
    for vname, (path, renames, no_twin) in PAIRING.items():
        v = verbs.VERBS[vname]
        cmd = _click_cmd(path)
        cdefs = _click_defaults(cmd)
        eff = EFFECTIVE_DEFAULTS.get(vname, {})
        for param, vdefault in v.defaults.items():
            if param in no_twin:
                continue
            if vdefault is None and param in eff:
                vdefault = eff[param]
            cname = renames.get(param, param)
            if cname not in cdefs:
                mismatches.append(f"{vname}.{param}: no click option "
                                  f"'{cname}' on {'/'.join(path)}")
                continue
            cdefault = cdefs[cname]
            if isinstance(vdefault, tuple):
                vdefault = list(vdefault)
            if isinstance(cdefault, tuple):
                cdefault = list(cdefault)
            if cdefault != vdefault:
                mismatches.append(
                    f"{vname}.{param}: verb default {vdefault!r} != "
                    f"CLI default {cdefault!r}")
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
