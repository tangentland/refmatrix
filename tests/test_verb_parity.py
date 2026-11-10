"""Structural CLI/MCP anti-drift gate (plan-3; ch-bsd plan-3 r1 #bs-1/#bs-2).

1. Every MCP tool IS a verb and every verb IS an MCP tool — `set(TOOLS) ==
   set(VERBS)`; a tool handler that bypasses the verb registry cannot exist.
2. Every tool schema is EXACTLY the verb-generated one (aliases included).
3. Every verb names its CLI twin in `verbs.CLI_MAP` (or `None` + an MCP_ONLY
   reason); every named click path resolves.
4. WIRING, not existence (#bs-1): every CLI twin either CALLS the verb
   (`verbs.CLI_WIRING[name] == "calls"`: the click command invokes
   `verbs.<fn>`) or builds its daemon payload through the verb's `payload_*`
   helper (`"payload"`: the replica-first / blocking surfaces the verbs
   docstring sanctions). Proven by recording the call while the click
   command runs — a twin that re-implements the capability fails here.
5. For every parameter a verb shares with its paired click command, the click
   default equals the verb default; the exclusion set is itself checked
   (#bs-2): a param may only be excluded when the click command has NO
   same-named option, or the difference is a declared shape difference.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

import refmatrix.mcp as mcp
from refmatrix import cli as cli_mod
from refmatrix import daemon as daemon_mod
from refmatrix import verbs
from refmatrix.cli import main as cli_main

# ---- defaults parity -------------------------------------------------------

# Verbs whose None default resolves to a fixed value the CLI shows.
_MANUAL_EFFECTIVE_DEFAULTS = {
    "rmx_context": {"max_entities": 20, "max_tokens": 4000},
}
# The action a required-`action` dispatcher's CLI_MAP twin runs (a dispatcher with a
# default action uses that default).
_TWIN_ACTION = {"rmx_memory": "get", "rmx_curate": "protect", "rmx_graph": "neighbors",
                "rmx_canon": "find", "rmx_matrix": "add_concept", "rmx_session": "list",
                "rmx_refine": "list"}


def _effective_defaults() -> dict:
    """Task 3.7 C6 (r2 M2): a dispatcher param whose default differs by action is
    `X | None = None`, resolved through `verbs.ACTION_DEFAULTS[(verb, action)]`. The
    CLI_MAP twin compares against the resolution for ITS action — so
    `rmx_focus.top: int | None = None` still equals `focus context`'s 20."""
    import inspect
    eff = {k: dict(v) for k, v in _MANUAL_EFFECTIVE_DEFAULTS.items()}
    for vname, path in verbs.CLI_MAP.items():
        if path is None or vname not in verbs.VERBS:
            continue
        p = inspect.signature(verbs.VERBS[vname].fn).parameters.get("action")
        if p is None:
            continue
        act = p.default if p.default is not inspect.Parameter.empty else _TWIN_ACTION.get(vname)
        if act is not None:
            eff.setdefault(vname, {}).update(verbs.ACTION_DEFAULTS.get((vname, act), {}))
    return eff
# verb -> (click path, {verb_param: click_param}, verb params with no CLI twin)
PAIRING = {
    "rmx_context": (("context",), {"ref": "symbol"}, {"linkage"}),
    "rmx_query": (("query",), {"dsl": "expr"}, set()),
    "rmx_memory_add": (("memory", "add"), {"to_global": "is_global"}, {"tags", "metadata"}),
    # `partition`: the CLI carries it on the `rmx` group (`-p`), not the subcommand
    "rmx_memory_recall": (("memory", "recall"), {}, {"since_seconds", "kinds", "exclude_mtype", "partition"}),
    "rmx_ingest": (("ingest",), {}, {"path", "mode", "kinds", "limit", "rebuild", "partition"}),
    "rmx_save_state": (("save-state",), {}, {"lint", "sync"}),
    # task 3.7: the other actions' params are not options of `focus context`; each
    # action's own command is compared by test_cli_action_click_defaults_*.
    # `partition` (remedy r1 R-B2): the CLI carries it on the `rmx` group (`-p`).
    "rmx_focus": (("focus", "context"), {}, {"action", "n", "line", "context", "label",
                                            "selector", "k", "max_tokens", "no_expand",
                                            "no_autoscale", "timeout", "partition"}),
    "rmx_focus_note": (("focus", "note"), {}, {"session"}),
    "rmx_change_subject": (("focus", "change-subject"), {}, set()),
    "rmx_projects": (("projects",), {}, set()),
    "rmx_locate": (("locate",), {"file": "filename", "n": "limit"}, {"keywords"}),
    "rmx_task": (("task", "list"), {}, {"action", "desc", "selector"}),
    "rmx_queues": (("hub", "queues"), {}, set()),
    "rmx_ingest_status": (("ingest-status",), {}, {"since_seq", "limit"}),
    "rmx_recall_state": (("recall-state",), {}, set()),
    # dispatcher over the `rmx memory` group: its per-action parity is the
    # dedicated verbs' job (recall/add); `memory get` shares no defaults.
    "rmx_memory": (("memory", "get"), {}, "ALL"),
    "rmx_bus_pub": (("bus", "pub"), {"type": "mtype"}, {"project"}),
    "rmx_bus_history": (("bus", "history"), {}, set()),
    "rmx_bus_channels": (("bus", "channels"), {}, set()),
    "rmx_bus_read": (("bus", "read"), {}, {"channels", "channel"}),
    "rmx_bus_mark_read": (("bus", "mark-read"), {}, set()),
    "rmx_bus_delete": (("bus", "delete"), {"id": "msg_id"}, set()),
    "rmx_bus_archive": (("bus", "archive"), {"id": "msg_id", "before_ts": "before"}, set()),
    "rmx_bus_unarchive": (("bus", "unarchive"), {"id": "msg_id"}, set()),
    "rmx_bus_purge": (("bus", "purge"), {"before_ts": "before"}, set()),
    "rmx_bus_stats": (("bus", "stats"), {}, set()),
    # task 3.7 batch A. `partition`: the CLI carries it on the `rmx` group (`-p`).
    "rmx_curate": (("protect",), {}, {"action", "dry_run", "broad", "partition", "timeout"}),
    "rmx_taxonomy": (("taxonomy", "list"), {}, {"action", "category", "tag", "desc", "color"}),
    # `max_entries` pairs with the new `--max-entries`; the click `--limit` (sample
    # paths in the hook line) is a CLI-only render option (r6 S1).
    "rmx_curator": (("curator", "status"), {}, {"action", "token"}),
    # task 3.7 batch B. The twin is `neighbors`; the other actions' params are
    # compared on their own commands by test_cli_action_click_defaults_*.
    "rmx_graph": (("neighbors",), {}, {"action", "linkage", "ref", "first", "edge_limit",
                                       "evidence_limit", "sibling_limit", "no_vectors",
                                       "query", "k", "kinds", "symbolic", "no_dense",
                                       "stale", "hops", "since", "until", "git",
                                       "partition", "timeout"}),
    "rmx_canon": (("canon", "find"), {}, {"action", "canon_name", "canon_partition",
                                          "partition", "timeout"}),
    # task 3.7 batch C. `project_filter` is the CLI `--project` FILTER (C9, r1 S2).
    "rmx_matrix": (("add", "concept"), {}, {"action", "kind", "path", "tldr", "meta",
                                            "directed", "concept", "entity", "linkage",
                                            "want_protected", "want_noise", "limit", "is_pql",
                                            "ids_only", "body", "partition", "timeout"}),
    "rmx_session": (("session", "list"), {"project_filter": "project"},
                    {"action", "query", "commit", "touched", "until", "k", "session_id",
                     "mode", "partition", "timeout"}),
    "rmx_refine": (("refine", "list"), {"project_filter": "project"},
                   {"action", "cand_id", "timeout"}),
    # task 26.6 R-D: `memory compile` leaves LEGACY_UNPAIRED for the 19.4 R1 verb. `apply` is
    # the click `--apply` flag (dest `do_apply`); `prune` is the inverted `--no-prune`;
    # `invoked_by` / `status` are op duties (17.2 R2) with no CLI option; `partition` rides
    # on the `rmx` group (`-p`).
    "rmx_memory_compile": (("memory", "compile"), {"apply": "do_apply"},
                           {"exclude_mtypes", "prune", "invoked_by", "status", "partition",
                            "timeout"}),
}
# A no_twin param that DOES have a same-named click option must be one of
# these declared shape differences (a click `multiple=True` option defaults
# to `()` where the verb takes `None`; an inverted `--no-x` flag).
SHAPE_DIFFERENCES = {
    ("rmx_context", "linkage"): "click multiple=True () vs verb single str/None",
    ("rmx_memory_add", "tags"): "click multiple=True () vs verb None",
    ("rmx_memory_recall", "kinds"): "click multiple=True () vs verb None",
    ("rmx_memory_recall", "exclude_mtype"): "click multiple=True () vs verb None",
    ("rmx_bus_read", "channels"): "click nargs=-1 () vs verb None",
    ("rmx_ingest", "path"): "click required argument vs verb default (store parent)",
    ("rmx_graph", "linkage"): "click multiple=True () on `neighbors` vs verb None, resolved "
                              "per action (co_occur / top: \"mentions\")",
    ("rmx_memory_compile", "exclude_mtypes"): "click multiple=True () vs verb None (None = "
                                              "consolidate.DEFAULT_EXCLUDE_MTYPES)",
}


def _click_cmd(path):
    cmd = cli_main
    for name in path:
        cmd = cmd.commands[name]  # type: ignore[attr-defined]
    return cmd


def _click_defaults(cmd) -> dict:
    # click 8.2 marks an optional positional's default with a sentinel; the
    # value the callback receives is None.
    out = {}
    for p in cmd.params:
        d = p.default
        out[p.name] = None if type(d).__name__ == "Sentinel" else d
    return out


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


def test_pairing_covers_every_cli_twin():
    twins = {n for n, p in verbs.CLI_MAP.items() if p is not None}
    assert twins == set(PAIRING), sorted(twins ^ set(PAIRING))
    for name, (path, _r, _n) in PAIRING.items():
        assert verbs.CLI_MAP[name] == path, name


def test_no_twin_exclusions_are_honest():
    """A verb param may only be excluded from the defaults comparison when
    the click command has no option by that (renamed) name, or the pair is a
    declared shape difference. Excluding a same-named option hid the k=8 vs
    k=10 drift the gate exists to catch (#bs-2)."""
    bad = []
    for vname, (path, renames, no_twin) in PAIRING.items():
        if no_twin == "ALL":
            continue
        cdefs = _click_defaults(_click_cmd(path))
        for param in no_twin:
            cname = renames.get(param, param)
            if cname in cdefs and (vname, param) not in SHAPE_DIFFERENCES:
                bad.append(f"{vname}.{param}: click has '{cname}' — compare it or declare the shape difference")
    assert not bad, "\n" + "\n".join(bad)


def test_click_defaults_match_verb_defaults():
    mismatches = []
    for vname, (path, renames, no_twin) in PAIRING.items():
        if no_twin == "ALL":
            continue
        v = verbs.VERBS[vname]
        cdefs = _click_defaults(_click_cmd(path))
        eff = _effective_defaults().get(vname, {})
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


# ---- wiring (#bs-1): the twin CALLS the verb -------------------------------

# verb -> (click argv, canned verb result, kwargs the argv must reach the verb
# with, a CANARY string from the canned result the CLI output must show).
# The kwargs + canary are what turn the recorder from "was called" into "the
# options arrive and the result is what gets rendered" (ch-bsd plan-3 r2 #s-3:
# a twin that called the verb and then rendered from the ring passed).
# The canned `rmx_memory_compile` index text: a distinct marker, so the CLI can only have
# written it by copying the verb's `subjects_gmd`, never by rendering its own.
MEMORY_COMPILE_GMD = ('---\ngmd: "0.1"\nid: memory-subjects\ntitle: "CANARY-GMD"\n'
                      'tags: [memory]\n---\n\n# CANARY-GMD-written-by-the-verb {#root}\n')

CLI_INVOKE = {
    "rmx_memory_add": (["memory", "add", "n", "-c", "body", "--type", "note", "--protect"],
                       {"id": 4242},
                       {"name": "n", "content": "body", "mtype": "note", "protect": True}, "4242"),
    "rmx_memory_recall": (["memory", "recall", "--recent", "-k", "3", "--scope", "both", "--json"],
                          {"memories": [{"id": 1, "name": "CANARY-mem", "mtype": "m", "content": "c"}],
                           "mode": "recent", "widened": False, "since_seconds": None, "warnings": []},
                          {"recent": True, "k": 3, "scope": "both", "include_session": True}, "CANARY-mem"),
    "rmx_save_state": (["save-state", "--dry-run", "-m", "hello"],
                       {"target": "/t/x.md", "doc": "# CANARY-doc", "events": 0, "dry_run": True},
                       {"dry_run": True, "message": "hello"}, "CANARY-doc"),
    "rmx_focus": (["focus", "context", "--top", "20"],
                  {"graph": {"nodes": [{"name": "CANARY-node", "kind": "file", "count": 1, "weight": 1.0}],
                             "edges": [], "events": 3, "session": "s"},
                   "tasks": [], "dialogue": [{"line": 1, "kind": "input", "terse": "CANARY-say"}],
                   "milestones": [], "last_line": {}, "events_total": 3},
                  {"top": 60}, "CANARY-say"),   # CLI over-fetches 3x for noise filtering
    "rmx_focus_note": (["focus", "note", "why"], {"noted": True, "session": "s", "refs": ["CANARY-ref"]},
                       {"text": "why"}, "CANARY-ref"),
    "rmx_change_subject": (["focus", "change-subject", "topic"],
                           {"subject": "canary-slug", "label": "topic", "id": 1, "session": "s"},
                           {"label": "topic"}, "canary-slug"),
    "rmx_projects": (["projects", "--footprint"],
                     {"projects": [{"name": "CANARY-proj", "root": "/r", "daemon": {"up": True}}]},
                     {"footprint": True}, "CANARY-proj"),
    "rmx_locate": (["locate", "cli.py", "alpha", "-n", "4"],
                   {"results": [{"path": "/x/CANARY-path.py", "project": "p", "score": 1.0, "why": []}],
                    "skipped": [{"project": "q", "root": "/q", "reason": "CANARY-skip"}]},
                   {"file": "cli.py", "keywords": ["alpha"], "n": 4}, "CANARY-path"),
    "rmx_task": (["task", "list"], {"tasks": [{"desc": "CANARY-task", "ts": "t"}]},
                 {"action": "list"}, "CANARY-task"),
    "rmx_queues": (["hub", "queues"],
                   {"queues": [{"project": "CANARY-q", "root": "/r", "daemon_up": True, "stale_files": 0}]},
                   {}, "CANARY-q"),
    "rmx_ingest_status": (["ingest-status", "job-7"],
                          {"job": {"id": "job-7", "status": "done", "files_done": 1, "files_total": 1,
                                   "current_file": "CANARY-file"}, "events": []},
                          {"job_id": "job-7"}, "CANARY-file"),
    "rmx_recall_state": (["recall-state", "--json", "-s", "sess-9"], {"handoff": "CANARY-handoff"},
                         {"session": "sess-9"}, "CANARY-handoff"),
    "rmx_memory": (["memory", "get", "x"],
                   {"memory": {"name": "x", "id": 1, "mtype": "m", "tags": [],
                               "metadata": {}, "content": "CANARY-body"}},
                   {"action": "get", "name": "x"}, "CANARY-body"),
    "rmx_bus_pub": (["bus", "pub", "global:t", "hi", "--type", "note", "--from", "me"],
                    {"message": {"id": "CANARY-msg"}},
                    {"channel": "global:t", "body": "hi", "type": "note", "sender": "me"}, "CANARY-msg"),
    "rmx_bus_history": (["bus", "history", "global:t", "-n", "3", "--status", "archived"],
                        {"messages": [{"ts": "t", "from": "a", "type": "note", "id": "1", "body": "CANARY-hist"}]},
                        {"channel": "global:t", "n": 3, "status": "archived"}, "CANARY-hist"),
    "rmx_bus_channels": (["bus", "channels", "--glob", "proj:*"],
                         {"channels": [{"channel": "CANARY-chan", "messages": 1}]},
                         {"glob": "proj:*"}, "CANARY-chan"),
    "rmx_bus_read": (["bus", "read", "proj:*", "--peek", "--from", "me"],
                     {"messages": [{"ts": "t", "channel": "c", "from": "a", "type": "note", "id": "1",
                                    "body": "CANARY-unread"}]},
                     {"channels": ["proj:*"], "peek": True, "agent": "me"}, "CANARY-unread"),
    "rmx_bus_mark_read": (["bus", "mark-read", "global:t", "--upto-seq", "9"], {"last_seq": 4242},
                          {"channel": "global:t", "upto_seq": 9}, "4242"),
    "rmx_bus_delete": (["bus", "delete", "m1"], {"deleted": True}, {"id": "m1"}, "m1"),
    "rmx_bus_archive": (["bus", "archive", "--id", "m1"], {"ok": True, "archived": 4242},
                        {"id": "m1"}, "4242"),
    "rmx_bus_unarchive": (["bus", "unarchive", "m1"], {"restored": True}, {"id": "m1"}, "m1"),
    "rmx_bus_purge": (["bus", "purge", "-y", "--status", "archived"], {"purged": 4242},
                      {"status": "archived"}, "4242"),
    "rmx_bus_stats": (["bus", "stats"],
                      {"totals": {"active": 1}, "unread": {}, "channels": [{"channel": "CANARY-stat", "messages": 1}]},
                      {}, "CANARY-stat"),
    # task 3.7 batch A
    "rmx_curate": (["protect", "a", "b", "--like", "x%"],
                   {"count": 4242, "names": ["CANARY-ent"]},
                   {"action": "protect", "names": ["a", "b"], "like": "x%"}, "4242"),
    "rmx_taxonomy": (["taxonomy", "list"],
                     {"categories": {"cat": {"description": "d", "tags": {
                         "CANARY-tag": {"description": "x", "color": "#000000"}}}},
                      "path": "/t/taxonomy.json", "warnings": []},
                     {"action": "list"}, "CANARY-tag"),
    "rmx_curator": (["curator", "status", "--json", "--max-entries", "7"],
                    {"entries": [{"ts": 1.0, "path": "/x/CANARY-cur.md", "reason": "fs-change"}],
                     "token": ["00000000000000000001-a.jsonl"],
                     "spool": {"files": 1, "bytes": 10, "remaining_files": 0},
                     "warnings": [], "missing": []},
                    {"action": "status", "max_entries": 7}, "CANARY-cur"),
    # task 3.7 batch B
    "rmx_graph": (["neighbors", "alpha", "--depth", "2", "--linkage", "mentions", "--limit", "5",
                   "--strict"],
                  {"concept": "alpha", "entities": [{"id": 3, "kind": "doc", "name": "CANARY-nb",
                                                     "path": "/p/d.md"}],
                   "cardinality": 1, "source": "snapshot"},
                  {"action": "neighbors", "concept": "alpha", "depth": 2, "linkage": ["mentions"],
                   "limit": 5, "strict": True}, "CANARY-nb"),
    "rmx_canon": (["canon", "find", "alpha"],
                  {"concept": "alpha", "projects": [{"project": "CANARY-proj", "root": "/r",
                                                     "kind": "concept", "neighbors": 3}],
                   "skipped": []},
                  {"action": "find", "concept": "alpha"}, "CANARY-proj"),
    # task 3.7 batch C
    "rmx_matrix": (["add", "concept", "foo", "-d", "desc", "--no-protect"], {"id": 4242},
                   {"action": "add_concept", "name": "foo", "description": "desc",
                    "no_protect": True}, "4242"),
    "rmx_session": (["session", "list", "--project", "other", "--branch", "main", "--limit", "3",
                     "--offset", "1", "--json"],
                    {"sessions": [{"session_id": "CANARY-sess", "project": "/w/other",
                                   "branch": "main", "ended": "2026-10-01", "turn_count": 2,
                                   "title": "t"}], "total": 1},
                    {"action": "list", "project_filter": "other", "branch": "main", "limit": 3,
                     "offset": 1}, "CANARY-sess"),
    "rmx_refine": (["refine", "list", "--status", "all", "--scope", "project", "--project", "p",
                    "-n", "4", "--json"],
                   {"candidates": [{"id": "CANARY-cand", "ts": "t", "scope": "project",
                                    "project": "p", "suggested": {"name": "n", "mtype": "m",
                                                                  "content": "c"}}],
                    "total": 1, "shown": 1},
                   {"action": "list", "status": "all", "scope": "project", "project_filter": "p",
                    "limit": 4}, "CANARY-cand"),
    # task 26.6 R-D: the CLI twin CALLS the verb with the scope, the apply flag and
    # `invoked_by="cli"`, and renders the verb's plan (canary = a cluster label).
    "rmx_memory_compile": (["memory", "compile", "--apply", "--scope", "pattern",
                            "--min-size", "3", "--k", "5"],
                           {"scope": "pattern", "dry_run": False, "applied": True,
                            "invoked_by": "cli",
                            "plan": {"clusters": [{"label": "CANARY-subj", "size": 2,
                                                   "members": [{"id": 1, "name": "a",
                                                                "mtype": "impression"},
                                                               {"id": 2, "name": "b",
                                                                "mtype": "impression"}],
                                                   "evidence": []}],
                                     "crosscutting": [], "unclustered": [],
                                     "stats": {"candidates": 2, "embedded": 2,
                                               "unembedded": 0, "partition": "proj"},
                                     "params": {}},
                            "subjects": [{"id": 9, "name": "subject_pattern_canary_subj",
                                          "label": "CANARY-subj", "size": 2}],
                            "linked": 2, "unlinked": 0, "stale_total": 0, "stale_new": 0,
                            "stale_unmarked": 0,
                            # 26.6 r1 remedy #rm-subjects-gmd: the VERB renders the index and
                            # the CLI only writes it; an applied result without it fails closed.
                            "subjects_gmd": MEMORY_COMPILE_GMD},
                           {"scope": "pattern", "apply": True, "min_size": 3, "k": 5,
                            "invoked_by": "cli"}, "CANARY-subj"),
}
# payload-class twins: argv + the daemon op the click command must issue with
# a payload built by the verb's helper (recorded by wrapping the helper).
CLI_PAYLOAD_INVOKE = {
    "rmx_context": (["context", "foo"], "payload_context",
                    {"context": {"ok": True, "result": {"body": '{"ref": "foo", "groups": {}}'}}}),
    "rmx_query": (["query", "mentions:x"], "payload_query",
                  {"query": {"ok": True, "result": {"shape": "bitmap", "rows": [], "cardinality": 0}}}),
}


def test_every_cli_twin_declares_its_wiring_class():
    twins = {n for n, p in verbs.CLI_MAP.items() if p is not None}
    assert set(verbs.CLI_WIRING) == twins, sorted(set(verbs.CLI_WIRING) ^ twins)
    assert set(verbs.CLI_WIRING.values()) <= {"calls", "payload"}
    calls = {n for n, w in verbs.CLI_WIRING.items() if w == "calls"}
    payload = {n for n, w in verbs.CLI_WIRING.items() if w == "payload"}
    assert calls == set(CLI_INVOKE), sorted(calls ^ set(CLI_INVOKE))
    assert payload == set(CLI_PAYLOAD_INVOKE) | {"rmx_ingest"}


@pytest.fixture
def _cli_env(tmp_path, monkeypatch):
    root = tmp_path / "proj" / ".refmatrix"
    root.mkdir(parents=True)
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    monkeypatch.chdir(tmp_path / "proj")
    monkeypatch.setattr(daemon_mod, "ping", lambda *a, **k: True)
    monkeypatch.setattr("refmatrix.hub.is_running", lambda: True)

    # Fail CLOSED: a twin that bypasses its verb must never reach the live
    # hub or daemon from this test (a scratch mutation during the plan-3 r1
    # remedy published to the real bus through exactly that gap).
    def _live(*a, **k):
        raise AssertionError("test reached a live service — the twin bypassed its verb")
    monkeypatch.setattr("refmatrix.hub.rpc", _live)
    monkeypatch.setattr("refmatrix.hub.global_call", _live)
    monkeypatch.setattr(daemon_mod, "call", _live)
    return root


@pytest.mark.parametrize("vname", sorted(CLI_INVOKE))
def test_cli_twin_calls_its_verb(vname, _cli_env, monkeypatch):
    """Three properties per twin: the verb is CALLED (with a root), the argv's
    options ARRIVE as the verb's own parameters (bound against the real
    signature), and the CLI RENDERS the verb's result (canary)."""
    import inspect
    argv, canned, expect, canary = CLI_INVOKE[vname]
    v = verbs.VERBS[vname]
    sig = inspect.signature(v.fn)
    seen = []

    def recorder(root, *a, **kw):
        bound = sig.bind(root, *a, **kw)      # a wrong kwarg name fails here
        bound.apply_defaults()
        seen.append(bound.arguments)
        return json.loads(json.dumps(canned))
    monkeypatch.setattr(verbs, v.fn.__name__, recorder)
    r = CliRunner().invoke(cli_main, argv, catch_exceptions=False)
    assert r.exit_code == 0, r.output + (r.stderr or "")
    assert seen, f"{vname}: `rmx {' '.join(argv)}` never called verbs.{v.fn.__name__}"
    assert Path(seen[0]["root"]) == _cli_env
    for k, val in expect.items():
        got = seen[0].get(k)
        if isinstance(got, tuple):
            got = list(got)
        assert got == val, f"{vname}.{k}: argv gave {got!r}, expected {val!r}"
    assert canary in r.output, f"{vname}: CLI did not render the verb's result ({canary!r})"


def test_cli_memory_compile_writes_the_verbs_subjects_gmd(_cli_env, monkeypatch):
    """26.6 r1 remedy #rm-subjects-gmd: `memory compile --apply` writes the verb's
    `subjects_gmd` byte-for-byte to the default `--out` path, and renders nothing itself."""
    from refmatrix import consolidate
    argv, canned, _expect, _canary = CLI_INVOKE["rmx_memory_compile"]
    v = verbs.VERBS["rmx_memory_compile"]
    monkeypatch.setattr(verbs, v.fn.__name__,
                        lambda root, *a, **kw: json.loads(json.dumps(canned)))
    dest = consolidate.default_out_path(_cli_env)
    assert not dest.exists(), dest
    r = CliRunner().invoke(cli_main, argv, catch_exceptions=False)
    assert r.exit_code == 0, r.output + (r.stderr or "")
    assert dest.read_text() == MEMORY_COMPILE_GMD, dest.read_text()

    # Fail-closed: an applied result with no `subjects_gmd` writes nothing and exits non-zero.
    dest.unlink()
    bare = {k: val for k, val in canned.items() if k != "subjects_gmd"}
    monkeypatch.setattr(verbs, v.fn.__name__,
                        lambda root, *a, **kw: json.loads(json.dumps(bare)))
    r = CliRunner().invoke(cli_main, argv)
    assert r.exit_code != 0, r.output
    assert "subjects_gmd" in r.output, r.output
    assert not dest.exists(), "the adapter wrote an index the verb never rendered"


@pytest.mark.parametrize("vname", sorted(CLI_PAYLOAD_INVOKE))
def test_cli_routed_twin_builds_its_payload_through_the_verb_helper(vname, _cli_env, monkeypatch):
    argv, helper, ops = CLI_PAYLOAD_INVOKE[vname]
    real = getattr(verbs, helper)
    built = []

    def rec(*a, **kw):
        p = real(*a, **kw)
        built.append(p)
        return p
    monkeypatch.setattr(verbs, helper, rec)
    sent = []

    def fake_call(root, op, args=None, **kw):
        sent.append((op, args))
        return ops.get(op, {"ok": True, "result": {}})
    monkeypatch.setattr(daemon_mod, "call", fake_call)
    r = CliRunner().invoke(cli_main, argv, catch_exceptions=False)
    assert r.exit_code == 0, r.output + (r.stderr or "")
    assert built, f"{vname}: `rmx {' '.join(argv)}` never called verbs.{helper}"
    op_args = dict(sent)[next(iter(ops))]
    for k, val in built[0].items():
        assert op_args.get(k) == val, (k, val, op_args.get(k))


def test_daemon_writer_ingest_uses_the_verb_payload(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(cli_mod._DaemonWriter, "_call",
                        lambda self, op, args, **kw: seen.append((op, args)) or {"entities": 3})
    w = cli_mod._DaemonWriter.__new__(cli_mod._DaemonWriter)
    w._root = tmp_path
    assert w.ingest_path(tmp_path, source="auto", semantic=True) == 3
    assert seen[0][0] == "ingest_path"
    assert seen[0][1] == verbs.payload_ingest(str(tmp_path), source="auto", semantic=True)


# ---- payload helpers -------------------------------------------------------

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


# ---- task 3.4: the REVERSE walk — every invocable CLI path is classified ----
#
# ch-bsd plan-3 r8 #s-4 / #t34-build. The forward gate above proves every verb
# has a twin; nothing proved every click command is a twin or a DECIDED
# exception, so a new agent-facing command with no verb was invisible. Five
# classes, exactly one each:
#   CLI_MAP twin      — the verb's own command
#   CLI_ACTIONS       — a dispatcher verb's action (rmx_memory / rmx_task)
#   INTERNAL_CLI      — CLI-only by the user's 2026-10-06 decision
#   HIDDEN_ALIASES    — an `_alias` copy; the target's class applies
#   LEGACY_UNPAIRED   — today's unpaired surface, pinned and shrink-only

import copy

import click

_INTERNAL_SEED = {
    ("derive", "log"), ("derive", "diff"), ("derive", "status"), ("derive", "unstamp"),
    ("learn",), ("learn", "on"), ("learn", "off"), ("learn", "status"),
}
_ACTIONS_SEED = {
    ("memory", "list"): ("rmx_memory", "list"),
    ("memory", "search"): ("rmx_memory", "search"),
    ("memory", "promote"): ("rmx_memory", "promote"),
    ("memory", "brief"): ("rmx_memory", "brief"),
    ("memory", "forget"): ("rmx_memory", "forget"),
    ("memory", "reclassify"): ("rmx_memory", "reclassify"),
    ("memory", "retag"): ("rmx_memory", "retag"),
    ("memory", "link"): ("rmx_memory", "link"),
    ("memory", "score"): ("rmx_memory", "score"),
    ("memory", "bulk-forget"): ("rmx_memory", "bulk_forget"),
    ("memory", "dedup"): ("rmx_memory", "dedup"),
    ("task", "push"): ("rmx_task", "push"),
    ("task", "pop"): ("rmx_task", "pop"),
    ("task", "current"): ("rmx_task", "current"),
    ("task", "swap"): ("rmx_task", "swap"),
    # task 3.7 batch A (#fam-focus incl. `export`, #fam-curation, #fam-taxonomy,
    # #fam-refine-drain)
    ("focus", "tail"): ("rmx_focus", "tail"),
    ("focus", "topics"): ("rmx_focus", "topics"),
    ("focus", "show"): ("rmx_focus", "show"),
    ("focus", "subject"): ("rmx_focus", "subject"),
    ("focus", "subjects"): ("rmx_focus", "subjects"),
    ("focus", "clear-subject"): ("rmx_focus", "clear_subject"),
    ("focus", "composite"): ("rmx_focus", "composite"),
    ("focus", "export"): ("rmx_focus", "export"),
    ("focus", "detour"): ("rmx_focus", "detour"),
    ("focus", "detours"): ("rmx_focus", "detours"),
    ("focus", "return"): ("rmx_focus", "return"),
    ("focus", "clear"): ("rmx_focus", "clear"),
    ("unprotect",): ("rmx_curate", "unprotect"),
    ("noise",): ("rmx_curate", "noise"),
    ("unnoise",): ("rmx_curate", "unnoise"),
    ("forget",): ("rmx_curate", "forget"),
    ("taxonomy", "add"): ("rmx_taxonomy", "add"),
    ("taxonomy", "remove"): ("rmx_taxonomy", "remove"),
    ("curator", "drain"): ("rmx_curator", "drain"),
    # task 3.7 batch B (#fam-graph-read incl. `stats`, #fam-canon)
    ("co-occur",): ("rmx_graph", "co_occur"),
    ("top",): ("rmx_graph", "top"),
    ("describe",): ("rmx_graph", "describe"),
    ("recall",): ("rmx_graph", "recall"),
    ("search-dense",): ("rmx_graph", "dense"),
    ("stats",): ("rmx_graph", "stats"),
    ("concept", "timeline"): ("rmx_graph", "timeline"),
    ("canon", "siblings"): ("rmx_canon", "siblings"),
    ("canon", "link"): ("rmx_canon", "link"),
    # task 3.7 batch C (#fam-matrix-edit, #fam-session, #fam-refine)
    ("add", "entity"): ("rmx_matrix", "add_entity"),
    ("add", "linkage-type"): ("rmx_matrix", "add_linkage_type"),
    ("link",): ("rmx_matrix", "link"),
    ("unlink",): ("rmx_matrix", "unlink"),
    ("list", "entities"): ("rmx_matrix", "list_entities"),
    ("list", "linkages"): ("rmx_matrix", "list_linkages"),
    ("list", "queries"): ("rmx_matrix", "list_queries"),
    ("run",): ("rmx_matrix", "run"),
    ("save-query",): ("rmx_matrix", "save_query"),
    ("session", "recall"): ("rmx_session", "recall"),
    ("session", "show"): ("rmx_session", "show"),
    ("refine", "show"): ("rmx_refine", "show"),
}
_HIDDEN_SEED = {
    ("add-concept",): ("add", "concept"),
    ("add-entity",): ("add", "entity"),
    ("add-linkage-type",): ("add", "linkage-type"),
    ("list-entities",): ("list", "entities"),
    ("list-linkages",): ("list", "linkages"),
    ("list-queries",): ("list", "queries"),
}
# FROZEN at d4bf001 + task 3.4 (ch-bsd r8 clitree walk: 195 paths - 26 twins -
# 15 actions - 8 internal - 6 hidden). verbs.LEGACY_UNPAIRED may only SHRINK
# against this: a path leaves by gaining a verb or an INTERNAL_CLI reason. Do
# NOT add to this set to make a new command pass — that is the growth the gate
# exists to stop.
_BASELINE_3_4_SIZE = 140
_BASELINE_3_4 = frozenset({
    ('audit-same-as',), ('cctree',), ('checkpoint',), ('cli-log',), ('co-occur',), ('compact',),
    ('compact-log',), ('describe',), ('dump-log',), ('embed',), ('export',), ('fingerprint',),
    ('forget',), ('graphify-warm',), ('grep',), ('import',), ('info',), ('ingest-gmd',),
    ('init',), ('install-hooks',), ('link',), ('log',), ('mcp',), ('merge-verb-aliases',),
    ('migrate-to-duckdb',), ('neighbors',), ('noise',), ('pagerank',), ('primer',), ('protect',),
    ('prune-noise',), ('queue',), ('rebuild',), ('recall',), ('reingest',), ('repair-index',),
    ('run',), ('save-query',), ('scan-prompt',), ('search-dense',), ('stats',), ('sync',),
    ('telemetry',), ('tldr-warm',), ('tools-primer',), ('top',), ('ui',), ('unlink',),
    ('unnoise',), ('unprotect',), ('untrack',), ('upgrade',), ('vacuum',), ('version',),
    ('watch',),
    ('add', 'concept'), ('add', 'entity'), ('add', 'linkage-type'),
    ('bus', 'sub'),
    ('canon', 'find'), ('canon', 'link'), ('canon', 'siblings'),
    ('concept', 'timeline'),
    ('coref', 'link'),
    ('curator', 'drain'), ('curator', 'scan'), ('curator', 'status'),
    ('daemon', 'launchctl', 'install'), ('daemon', 'launchctl', 'kickstart'),
    ('daemon', 'launchctl', 'print'), ('daemon', 'launchctl', 'status'),
    ('daemon', 'launchctl', 'uninstall'), ('daemon', 'restart'), ('daemon', 'start'),
    ('daemon', 'status'), ('daemon', 'stop'),
    ('focus', 'clear'), ('focus', 'clear-subject'), ('focus', 'composite'), ('focus', 'detour'),
    ('focus', 'detours'), ('focus', 'export'), ('focus', 'hook'), ('focus', 'promote-edges'),
    ('focus', 'rebuild'), ('focus', 'record'), ('focus', 'return'), ('focus', 'show'),
    ('focus', 'size'), ('focus', 'subject'), ('focus', 'subjects'), ('focus', 'summarize'),
    ('focus', 'tail'), ('focus', 'topics'),
    ('hub', 'launchctl', 'install'), ('hub', 'launchctl', 'status'),
    ('hub', 'launchctl', 'uninstall'), ('hub', 'pause'), ('hub', 'relaunch-fleet'),
    ('hub', 'resume'), ('hub', 'start'), ('hub', 'status'), ('hub', 'stop'),
    ('list', 'entities'), ('list', 'linkages'), ('list', 'queries'),
    ('memory', 'compile'), ('memory', 'sync-disk'),
    ('pairs', 'compile'), ('pairs', 'show'),
    ('partition', 'add'), ('partition', 'audit'), ('partition', 'drop'), ('partition', 'list'),
    ('partition', 'merge'), ('partition', 'rename'),
    ('queue', 'clear'),
    ('refine', 'accept'), ('refine', 'list'), ('refine', 'reject'), ('refine', 'show'),
    ('replica', 'audit'), ('replica', 'merge'), ('replica', 'path'), ('replica', 'refresh'),
    ('replica', 'status'),
    ('schedule', 'add'), ('schedule', 'list'), ('schedule', 'remove'),
    ('session', 'ingest'), ('session', 'launchctl', 'install'),
    ('session', 'launchctl', 'status'), ('session', 'launchctl', 'uninstall'),
    ('session', 'list'), ('session', 'recall'), ('session', 'show'), ('session', 'stats'),
    ('taxonomy', 'add'), ('taxonomy', 'list'), ('taxonomy', 'remove'),
})
# Task 3.7 batch A (#schedule): the paths that gained twins — focus (11 + `export`),
# curation (5), taxonomy (3), curator `status` + `drain`. LEGACY_BASELINE shrinks by
# EXACTLY these (C6); later batches subtract their own.
_TASK_3_7_BATCH_A = frozenset({
    ('focus', 'tail'), ('focus', 'topics'), ('focus', 'show'), ('focus', 'subject'),
    ('focus', 'subjects'), ('focus', 'clear-subject'), ('focus', 'composite'),
    ('focus', 'detour'), ('focus', 'detours'), ('focus', 'return'), ('focus', 'clear'),
    ('focus', 'export'),
    ('protect',), ('unprotect',), ('noise',), ('unnoise',), ('forget',),
    ('taxonomy', 'list'), ('taxonomy', 'add'), ('taxonomy', 'remove'),
    ('curator', 'status'), ('curator', 'drain'),
})
# Task 3.7 batch B: graph-read (7) + `stats` + canon (3) = 11. `pairs show` STAYS in
# LEGACY_UNPAIRED, re-decided as `harness` (#fam-graph-read-pairs).
_TASK_3_7_BATCH_B = frozenset({
    ('neighbors',), ('co-occur',), ('top',), ('describe',), ('recall',), ('search-dense',),
    ('concept', 'timeline'), ('stats',),
    ('canon', 'find'), ('canon', 'siblings'), ('canon', 'link'),
})
# Task 3.7 batch C: matrix-edit (10) + session list/recall/show (3) + refine list/show (2)
# = 15. `session stats` (harness) and `refine accept` / `reject` (operator) STAY,
# re-decided. AC-G5: 140 → 92.
_TASK_3_7_BATCH_C = frozenset({
    ('add', 'concept'), ('add', 'entity'), ('add', 'linkage-type'), ('link',), ('unlink',),
    ('list', 'entities'), ('list', 'linkages'), ('list', 'queries'), ('run',), ('save-query',),
    ('session', 'list'), ('session', 'recall'), ('session', 'show'),
    ('refine', 'list'), ('refine', 'show'),
})
# Task 26.6 R-D: `memory compile` gained the `rmx_memory_compile` verb (19.4 R1's op half).
_TASK_26_6 = frozenset({('memory', 'compile')})
LEGACY_BASELINE = (_BASELINE_3_4 - _TASK_3_7_BATCH_A - _TASK_3_7_BATCH_B - _TASK_3_7_BATCH_C
                   - _TASK_26_6)
LEGACY_BASELINE_SIZE = 91
_USER_QUOTE = "internal harness/testing cli only commands"


def _invocable_paths(group, prefix=()):
    """Every path a user can invoke under `group`: each leaf, and each group
    that runs on its own (`invoke_without_command` — bare `rmx learn`, bare
    `rmx queue`). Hidden commands INCLUDED: plan-16's `grep-learn` will be
    hidden, so "skip hidden" is not a safe rule (r8 #s-4 item 4)."""
    for name, cmd in sorted(group.commands.items()):
        path = prefix + (name,)
        if isinstance(cmd, click.Group):
            if cmd.invoke_without_command:
                yield path
            yield from _invocable_paths(cmd, path)
        else:
            yield path


def _classes() -> dict:
    return {
        "CLI_MAP": {p for p in verbs.CLI_MAP.values() if p is not None},
        "CLI_ACTIONS": set(verbs.CLI_ACTIONS),
        "INTERNAL_CLI": set(verbs.INTERNAL_CLI),
        "HIDDEN_ALIASES": set(verbs.HIDDEN_ALIASES),
        "LEGACY_UNPAIRED": set(verbs.LEGACY_UNPAIRED),
    }


def _classification_failures(group) -> list[str]:
    """One message per path that is in no class or in more than one. The
    message names the command and BOTH remedies, so the author of a new
    command is told where it can go."""
    classes = _classes()
    out = []
    for path in _invocable_paths(group):
        hits = [c for c, members in classes.items() if path in members]
        cmd = "rmx " + " ".join(path)
        if not hits:
            out.append(f"{cmd}: unclassified — give it a verb and name it as the verb's "
                       f"twin in verbs.CLI_MAP, or add it to verbs.INTERNAL_CLI with a reason")
        elif len(hits) > 1:
            out.append(f"{cmd}: listed in {len(hits)} classes ({', '.join(hits)}) — exactly one")
    return out


def _stale_keys(group) -> list[str]:
    paths = set(_invocable_paths(group))
    out = []
    for cls, members in _classes().items():
        out += [f"{cls}: {' '.join(p)!r} is not an invocable command" for p in members
                if p not in paths]
    out += [f"HIDDEN_ALIASES target {' '.join(t)!r} is not an invocable command"
            for t in verbs.HIDDEN_ALIASES.values() if t not in paths]
    return out


def test_every_invocable_cli_path_is_classified_exactly_once():
    bad = _classification_failures(cli_main)
    assert not bad, "\n" + "\n".join(bad)


def test_a_new_command_in_no_class_fails_naming_it_and_both_remedies():
    """AC-1 on a REAL copy: `copy.copy(cli.main)` shares its `.commands` dict,
    so `add_command` on a bare copy would register the probe on the real tree
    (r8 #s-4 item 5) and every later test would see it."""
    g = copy.copy(cli_main)
    g.commands = dict(cli_main.commands)
    g.add_command(click.Command("zz-probe"))
    try:
        bad = _classification_failures(g)
    finally:
        assert "zz-probe" not in cli_main.commands, "the probe mutated the real click tree"
    hit = [m for m in bad if m.startswith("rmx zz-probe:")]
    assert hit, bad
    assert "verbs.CLI_MAP" in hit[0] and "verbs.INTERNAL_CLI" in hit[0], hit[0]
    assert not [m for m in bad if not m.startswith("rmx zz-probe:")], bad


def test_removing_an_internal_entry_fails_the_walk(monkeypatch):
    """AC-2."""
    monkeypatch.delitem(verbs.INTERNAL_CLI, ("derive", "log"))
    bad = _classification_failures(cli_main)
    assert any(m.startswith("rmx derive log:") for m in bad), bad


def test_internal_cli_is_exactly_the_seeded_set_and_quotes_the_decision():
    assert set(verbs.INTERNAL_CLI) == _INTERNAL_SEED, sorted(set(verbs.INTERNAL_CLI) ^ _INTERNAL_SEED)
    for path, reason in verbs.INTERNAL_CLI.items():
        assert _USER_QUOTE in reason, f"{path}: the reason must quote the user's decision"
    assert ("grep-learn",) not in verbs.INTERNAL_CLI, "task 16.1 adds it when the command exists"


def test_a_path_listed_twice_fails_naming_both_classes(monkeypatch):
    """AC-4: exactly one, not at least one."""
    monkeypatch.setitem(verbs.LEGACY_UNPAIRED, ("derive", "log"), ("harness", "dup probe"))
    bad = _classification_failures(cli_main)
    hit = [m for m in bad if m.startswith("rmx derive log:")]
    assert hit and "INTERNAL_CLI" in hit[0] and "LEGACY_UNPAIRED" in hit[0], bad


def test_the_five_maps_have_no_stale_keys():
    bad = _stale_keys(cli_main)
    assert not bad, "\n" + "\n".join(bad)


@pytest.mark.parametrize("which", ["CLI_MAP", "CLI_ACTIONS", "INTERNAL_CLI", "HIDDEN_ALIASES",
                                   "LEGACY_UNPAIRED", "HIDDEN_ALIASES-target"])
def test_a_stale_key_in_any_map_fails_hygiene(which, monkeypatch):
    """AC-3: a key whose command no longer exists is an allowlist nobody reads."""
    stale = ("zz-stale",)
    if which == "CLI_MAP":
        monkeypatch.setitem(verbs.CLI_MAP, "rmx_zz_stale", stale)
    elif which == "CLI_ACTIONS":
        monkeypatch.setitem(verbs.CLI_ACTIONS, stale, ("rmx_memory", "list"))
    elif which == "INTERNAL_CLI":
        monkeypatch.setitem(verbs.INTERNAL_CLI, stale, _USER_QUOTE)
    elif which == "HIDDEN_ALIASES":
        monkeypatch.setitem(verbs.HIDDEN_ALIASES, stale, ("add", "concept"))
    elif which == "LEGACY_UNPAIRED":
        monkeypatch.setitem(verbs.LEGACY_UNPAIRED, stale, ("harness", "stale probe"))
    else:
        monkeypatch.setitem(verbs.HIDDEN_ALIASES, ("add-concept",), stale)
    bad = _stale_keys(cli_main)
    assert any("'zz-stale'" in m for m in bad), bad


def test_cli_actions_are_the_seeded_dispatcher_twins():
    """AC-5: r8 #s-4 item 1 — these 15 would otherwise land in LEGACY. Task 3.7
    batch A adds 19 (focus 12, curation 4, taxonomy 2, curator drain); batch B adds 9
    (graph 7 beside the `neighbors` twin, canon 2 beside the `canon find` twin); batch C
    adds 12 (matrix 9 beside `add concept`, session 2 beside `session list`, refine show)."""
    assert len(_ACTIONS_SEED) == 55
    import typing
    assert dict(verbs.CLI_ACTIONS) == _ACTIONS_SEED, sorted(
        set(verbs.CLI_ACTIONS.items()) ^ set(_ACTIONS_SEED.items()))
    for path, (vname, action) in verbs.CLI_ACTIONS.items():
        hint = typing.get_type_hints(verbs.VERBS[vname].fn)["action"]
        assert action in typing.get_args(hint), f"{path}: {action!r} is not a {vname} action"
        assert verbs.CLI_MAP[vname] != path, f"{path}: already the verb's CLI_MAP twin"


def test_hidden_aliases_are_the_six_alias_copies():
    """AC-7: the key is hidden, the target is visible and runs the SAME
    callback, so the target's classification is the alias's."""
    assert dict(verbs.HIDDEN_ALIASES) == _HIDDEN_SEED
    for alias, target in verbs.HIDDEN_ALIASES.items():
        a, t = _click_cmd(alias), _click_cmd(target)
        assert a.hidden, f"{alias} is not hidden"
        assert not t.hidden, f"{target} is hidden"
        assert a.callback is t.callback, f"{alias} does not run {target}"
        assert target not in verbs.HIDDEN_ALIASES


def test_legacy_unpaired_carries_a_category_and_can_only_shrink():
    """AC-8: r8 #s-4 item 6 — 140 paths with no rule against growth. Pinned:
    the set is a subset of the frozen baseline and never larger than it."""
    assert len(_BASELINE_3_4) == _BASELINE_3_4_SIZE
    assert _TASK_3_7_BATCH_A <= _BASELINE_3_4 and len(_TASK_3_7_BATCH_A) == 22
    assert _TASK_3_7_BATCH_B <= _BASELINE_3_4 and len(_TASK_3_7_BATCH_B) == 11
    assert not (_TASK_3_7_BATCH_A & _TASK_3_7_BATCH_B)
    assert _TASK_3_7_BATCH_C <= _BASELINE_3_4 and len(_TASK_3_7_BATCH_C) == 15
    assert not (_TASK_3_7_BATCH_C & (_TASK_3_7_BATCH_A | _TASK_3_7_BATCH_B))
    assert len(LEGACY_BASELINE) == LEGACY_BASELINE_SIZE
    legacy = set(verbs.LEGACY_UNPAIRED)
    grown = sorted(legacy - LEGACY_BASELINE)
    assert not grown, f"LEGACY_UNPAIRED grew (verb it or INTERNAL_CLI instead): {grown}"
    assert len(legacy) <= LEGACY_BASELINE_SIZE
    cats = set(verbs.LEGACY_CATEGORIES)
    # AC-G1: `verb-it` is empty after batch C and the category itself is removed, so the
    # shrink-only pin forbids its return.
    assert cats == {"operator", "maintenance", "hook", "harness"}, cats
    for path, val in verbs.LEGACY_UNPAIRED.items():
        assert isinstance(val, tuple) and len(val) == 2, f"{path}: (category, reason)"
        cat, reason = val
        assert cat in cats, f"{path}: unknown category {cat!r}"
        assert reason and reason.strip(), f"{path}: empty reason"


# ---- task 3.4 AC-6: the action twins CALL their dispatcher verb ------------
#
# path -> (argv, canned verb result, kwargs the LAST verb call must carry,
# canary from the result the CLI must render). The last call is the one that
# acts: `reclassify` and `bulk-forget` preview first (dry_run=True) and then
# write. The seven memory WRITES are RED at d4bf001: they build their own
# daemon payloads (`_memory_daemon_call`, `_store(write=True)`), so they reach
# `daemon.call` — which `_cli_env` fails closed — and never the verb.
CLI_ACTION_INVOKE = {
    ("memory", "list"): (["memory", "list", "--type", "note", "-n", "3"],
                         {"rows": [{"id": 1, "name": "CANARY-row", "mtype": "m", "content": "c",
                                    "tags": []}]},
                         {"action": "list", "mtype": "note", "limit": 3}, "CANARY-row"),
    ("memory", "search"): (["memory", "search", "foo", "-n", "3"],
                           {"rows": [{"id": 1, "name": "CANARY-hit", "mtype": "m", "content": "c"}]},
                           {"action": "search", "query": "foo", "limit": 3}, "CANARY-hit"),
    ("memory", "promote"): (["memory", "promote", "x"], {"id": 4242},
                            {"action": "promote", "name": "x"}, "4242"),
    # bug-198: the CLI's `--scope` reaches the verb as the brief's own
    # `compile_scope`, never as recall's `scope`.
    ("memory", "brief"): (["memory", "brief", "--scope", "pattern", "--json"],
                          {"briefs": [{"class": "singleton", "label": "CANARY-brief",
                                       "finding": "f", "evidence": [1]}], "stats": {}},
                          {"action": "brief", "compile_scope": "pattern", "scope": None},
                          "CANARY-brief"),
    ("memory", "forget"): (["memory", "forget", "x", "--yes"], {"forgotten": True},
                           {"action": "forget", "name": "x"}, "forgot"),
    ("memory", "reclassify"): (["memory", "reclassify", "--to", "new", "--like", "a*",
                                "--from", "old", "--name", "n1", "-y"],
                               {"matched": 1, "names": ["n1"], "changed": 4242},
                               {"action": "reclassify", "to_mtype": "new", "like": "a*",
                                "from_mtype": "old", "names": ["n1"], "dry_run": False}, "4242"),
    ("memory", "retag"): (["memory", "retag", "x", "--add", "t1"], {"tags": ["CANARY-tag"]},
                          {"action": "retag", "name": "x", "add": ["t1"]}, "CANARY-tag"),
    ("memory", "link"): (["memory", "link", "x", "reinforces", "conc", "-w", "0.5"],
                         {"src_id": 4242, "concept_id": 7},
                         {"action": "link", "name": "x", "linkage": "reinforces",
                          "concept": "conc", "weight": 0.5}, "4242"),
    ("memory", "score"): (["memory", "score", "conc"],
                          {"concept_ids": [1], "signal": 0.4242, "components": []},
                          {"action": "score", "concept": "conc"}, "+0.4242"),
    ("memory", "bulk-forget"): (["memory", "bulk-forget", "--mtype", "session-x", "-y"],
                                {"ids": [1], "by_mtype": {"session-x": 1}, "forgotten": 4242},
                                {"action": "bulk_forget", "mtypes": ["session-x"],
                                 "dry_run": False, "timeout": 600.0}, "4242"),
    ("memory", "dedup"): (["memory", "dedup", "--dry-run"],
                          {"dry_run": True, "folded": 4242, "edges_migrated": 0},
                          {"action": "dedup", "dry_run": True}, "4242"),
    ("task", "push"): (["task", "push", "hello"], {"current": "CANARY-cur", "depth": 1},
                       {"action": "push", "desc": "hello"}, "CANARY-cur"),
    ("task", "pop"): (["task", "pop", "2"], {"popped": "CANARY-pop", "depth": 0},
                      {"action": "pop", "selector": "2"}, "CANARY-pop"),
    ("task", "current"): (["task", "current"], {"current": {"desc": "CANARY-curr"}},
                          {"action": "current"}, "CANARY-curr"),
    ("task", "swap"): (["task", "swap"], {"swapped": True, "current": "CANARY-swap"},
                       {"action": "swap"}, "CANARY-swap"),
    # ---- task 3.7 batch A: the focus actions ----
    ("focus", "tail"): (["focus", "tail", "-n", "5", "-s", "S1"],
                        {"session": "S1", "session_source": "explicit",
                         "events": [{"ts": "t", "kind": "input", "terse": "CANARY-tail"}]},
                        {"action": "tail", "n": 5, "session": "S1"}, "CANARY-tail"),
    ("focus", "topics"): (["focus", "topics", "--top", "7", "-s", "S1"],
                          {"session": "S1", "session_source": "explicit", "events_total": 3,
                           "topics": [{"lead": "CANARY-topic", "members": ["a", "b"],
                                       "first_line": 1, "last_line": 2}], "anomalies": []},
                          {"action": "topics", "top": 7, "session": "S1"}, "CANARY-topic"),
    ("focus", "show"): (["focus", "show", "3", "-C", "1", "-s", "S1"],
                        {"session": "S1", "session_source": "explicit", "line": 3, "total": 5,
                         "events": [{"line": 3, "ts": "t", "kind": "say",
                                     "terse": "CANARY-show", "refs": []}]},
                        {"action": "show", "line": 3, "context": 1, "session": "S1"},
                        "CANARY-show"),
    ("focus", "subject"): (["focus", "subject", "-s", "S1"],
                           {"session": "S1", "session_source": "explicit",
                            "subject": {"subject": "slug", "label": "CANARY-subj", "ts": "t"}},
                           {"action": "subject", "session": "S1"}, "CANARY-subj"),
    ("focus", "subjects"): (["focus", "subjects"],
                            {"rows": [{"id": 1, "name": "n", "label": "CANARY-subjects",
                                       "leaves": 2, "updated_at": "t"}]},
                            {"action": "subjects"}, "CANARY-subjects"),
    ("focus", "clear-subject"): (["focus", "clear-subject", "-s", "S1"],
                                 {"cleared": True, "session": "S1", "session_source": "explicit"},
                                 {"action": "clear_subject", "session": "S1"}, "cleared"),
    ("focus", "composite"): (["focus", "composite", "--k", "2", "--max-tokens", "900",
                              "--no-expand", "--session", "S1"],
                             {"composite": "CANARY-gmd", "session": "S1",
                              "session_source": "explicit", "source": "in-process"},
                             {"action": "composite", "k": 2, "max_tokens": 900,
                              "no_expand": True, "session": "S1"}, "CANARY-gmd"),
    ("focus", "export"): (["focus", "export", "-s", "S1"],
                          {"session": "S1", "session_source": "explicit", "total": 1,
                           "events": [{"line": 1, "ts": "t", "kind": "input",
                                       "terse": "CANARY-export"}]},
                          {"action": "export", "session": "S1"}, "CANARY-export"),
    ("focus", "detour"): (["focus", "detour", "lbl"],
                          {"label": "CANARY-detour", "line": 4, "ts": "t", "session": "S1",
                           "session_source": "pointer"},
                          {"action": "detour", "label": "lbl"}, "CANARY-detour"),
    ("focus", "detours"): (["focus", "detours", "-s", "S1"],
                           {"session": "S1", "session_source": "explicit",
                            "detours": [{"index": 1, "label": "CANARY-detours", "line": 2,
                                         "ts": "t"}]},
                           {"action": "detours", "session": "S1"}, "CANARY-detours"),
    ("focus", "return"): (["focus", "return", "2"],
                          {"returned": "CANARY-ret", "line": 3, "remaining": 0, "focus": [],
                           "session": "S1", "session_source": "pointer"},
                          {"action": "return", "selector": "2"}, "CANARY-ret"),
    ("focus", "clear"): (["focus", "clear"],
                         {"cleared": True, "session": "CANARY-clr", "session_source": "env"},
                         {"action": "clear"}, "CANARY-clr"),
    # ---- curation (the CLI_MAP twin is `protect`) ----
    ("unprotect",): (["unprotect", "a"], {"count": 4242, "names": ["a"]},
                     {"action": "unprotect", "names": ["a"]}, "4242"),
    ("noise",): (["noise", "--namespace", "query"], {"count": 4242, "names": ["q/x"]},
                 {"action": "noise", "namespace": "query"}, "4242"),
    ("unnoise",): (["unnoise", "--kind", "concept", "--like", "q%"],
                   {"count": 4242, "names": ["q1"]},
                   {"action": "unnoise", "kind": "concept", "like": "q%"}, "4242"),
    # preview (dry_run=True) then, after -y, the destructive call: the LAST call
    # carries dry_run=False + broad=True (#fam-curation-forget)
    ("forget",): (["forget", "--kind", "code", "-y"],
                  {"count": 1, "names": ["CANARY-f"], "forgotten": 4242, "dry_run": False},
                  {"action": "forget", "kind": "code", "dry_run": False, "broad": True}, "4242"),
    # ---- taxonomy ----
    ("taxonomy", "add"): (["taxonomy", "add", "cat", "tg", "--desc", "dd", "--color", "#111111"],
                          {"added": True, "tag": "CANARY-add", "category": "cat"},
                          {"action": "add", "category": "cat", "tag": "tg", "desc": "dd",
                           "color": "#111111"}, "CANARY-add"),
    ("taxonomy", "remove"): (["taxonomy", "remove", "tg"], {"removed": True, "tag": "CANARY-rm"},
                             {"action": "remove", "tag": "tg"}, "CANARY-rm"),
    # ---- curator ----
    ("curator", "drain"): (["curator", "drain", "--token", "n1.jsonl", "--token", "n2.jsonl"],
                           {"drained": ["n1.jsonl"], "missing": ["CANARY-miss.jsonl"]},
                           {"action": "drain", "token": ["n1.jsonl", "n2.jsonl"]},
                           "CANARY-miss"),
    # ---- task 3.7 batch B: graph-read (the CLI_MAP twin is `neighbors`) ----
    ("co-occur",): (["co-occur", "alpha", "--type", "defines", "--limit", "3"],
                    {"rows": [{"concept": "CANARY-co", "overlap": 2}], "source": "snapshot"},
                    {"action": "co_occur", "concept": "alpha", "linkage": "defines", "limit": 3},
                    "CANARY-co"),
    ("top",): (["top", "alpha", "--type", "mentions", "-k", "4"],
               {"rows": [{"id": 6, "name": "CANARY-top", "kind": "doc", "weight": 4.0}],
                "source": "snapshot"},
               {"action": "top", "concept": "alpha", "linkage": "mentions", "k": 4}, "CANARY-top"),
    ("describe",): (["describe", "d3.md", "--first", "--edge-limit", "7", "--no-vectors",
                     "--format", "json"],
                    {"found": {"id": 6, "name": "CANARY-desc"}, "candidates": [{"id": 6}]},
                    {"action": "describe", "ref": "d3.md", "first": True, "edge_limit": 7,
                     "no_vectors": True}, "CANARY-desc"),
    ("recall",): (["recall", "q", "-k", "3", "-K", "doc", "-c", "beta", "--json"],
                  {"hits": [{"rank": 1, "id": 8, "score": 0.03, "kind": "doc",
                             "name": "CANARY-rec", "path": "/p"}]},
                  {"action": "recall", "query": "q", "k": 3, "kinds": ["doc"],
                   "concept": ["beta"]}, "CANARY-rec"),
    ("search-dense",): (["search-dense", "q", "-k", "4", "-K", "doc"],
                        {"hits": [{"rank": 1, "id": 6, "distance": 0.1, "kind": "doc",
                                   "name": "CANARY-dense"}], "warnings": []},
                        {"action": "dense", "query": "q", "k": 4, "kinds": ["doc"]},
                        "CANARY-dense"),
    ("stats",): (["stats", "--stale"],
                 {"partition": "proj", "entities": {"doc": 6},
                  "linkages": {"mentions": {"concepts": 2, "bits": 8}},
                  "stale_files": [{"path": "CANARY-stale.py", "status": "modified",
                                   "mtime": 2.0, "last_synced": 1.0}]},
                 {"action": "stats", "stale": True}, "CANARY-stale"),
    ("concept", "timeline"): (["concept", "timeline", "alpha", "--hops", "1", "--k", "5",
                               "--no-git", "--json"],
                              {"concept": "alpha", "resolved_files": 1, "resolved_concepts": 1,
                               "hops": 1, "events": [{"date": "2026-10-01", "type": "session",
                                                      "ref": "CANARY-tl", "detail": "d"}],
                               "session_count": 1, "truncated": False, "warnings": []},
                              {"action": "timeline", "concept": "alpha", "hops": 1, "k": 5,
                               "git": False}, "CANARY-tl"),
    # ---- canon (the CLI_MAP twin is `canon find`) ----
    ("canon", "siblings"): (["canon", "siblings", "alpha"],
                            {"rows": [{"partition_name": "other", "name": "CANARY-sib",
                                       "canon_partition": "canon", "canon_name": "Alpha"}],
                             "source": "snapshot"},
                            {"action": "siblings", "concept": "alpha"}, "CANARY-sib"),
    ("canon", "link"): (["canon", "link", "alpha", "--canon-name", "Alpha"],
                        {"canon_id": 4242, "source": "daemon"},
                        {"action": "link", "concept": "alpha", "canon_name": "Alpha",
                         "canon_partition": "canon"}, "4242"),
    # ---- task 3.7 batch C: matrix-edit (the CLI_MAP twin is `add concept`) ----
    ("add", "entity"): (["add", "entity", "--kind", "doc", "x.md", "--path", "/p/x.md",
                         "--tldr", "t", "--meta", '{"a": 1}'], {"id": 4242},
                        {"action": "add_entity", "kind": "doc", "name": "x.md",
                         "path": "/p/x.md", "tldr": "t", "meta": '{"a": 1}'}, "4242"),
    ("add", "linkage-type"): (["add", "linkage-type", "frob", "--undirected", "-d", "dd"],
                              {"id": 4242},
                              {"action": "add_linkage_type", "name": "frob", "directed": False,
                               "description": "dd"}, "4242"),
    ("link",): (["link", "alpha", "d0.md", "--type", "defines", "--no-protect"],
                {"created": True, "concept": "CANARY-lc", "entity": "d0.md"},
                {"action": "link", "concept": "alpha", "entity": "d0.md", "linkage": "defines",
                 "no_protect": True}, "CANARY-lc"),
    ("unlink",): (["unlink", "alpha", "d0.md"],
                  {"unlinked": True, "concept": "CANARY-ul", "entity": "d0.md"},
                  {"action": "unlink", "concept": "alpha", "entity": "d0.md",
                   "linkage": "mentions"}, "CANARY-ul"),
    ("list", "entities"): (["list", "entities", "--kind", "code", "--protected", "--json"],
                           {"rows": [{"id": 1, "kind": "code", "name": "CANARY-ent",
                                      "path": None, "tldr": None, "protected": True,
                                      "noise": False}]},
                           {"action": "list_entities", "kind": "code", "want_protected": True},
                           "CANARY-ent"),
    ("list", "linkages"): (["list", "linkages"],
                           {"rows": [{"id": 1, "name": "CANARY-lk", "directed": True,
                                      "description": None}]},
                           {"action": "list_linkages"}, "CANARY-lk"),
    ("list", "queries"): (["list", "queries"], {"rows": [{"name": "CANARY-q", "body": "b"}]},
                          {"action": "list_queries"}, "CANARY-q"),
    ("run",): (["run", "q1", "--pql", "--limit", "7"],
               {"rows": [{"id": 6, "kind": "doc", "name": "CANARY-run", "path": None}],
                "shape": "bitmap"},
               {"action": "run", "name": "q1", "is_pql": True, "limit": 7}, "CANARY-run"),
    ("save-query",): (["save-query", "q1", "mentions:alpha"], {"saved": True, "name": "CANARY-sq"},
                      {"action": "save_query", "name": "q1", "body": "mentions:alpha"},
                      "CANARY-sq"),
    # ---- session (the CLI_MAP twin is `session list`) ----
    ("session", "recall"): (["session", "recall", "parser", "--project", "p", "--k", "5",
                             "--json"],
                            {"sessions": [{"id": 1, "name": "n", "session_id": "CANARY-sr",
                                           "project": "p", "branch": "b", "started": "s",
                                           "ended": "e", "turn_count": 1, "title": "t",
                                           "snippet": "x"}]},
                            {"action": "recall", "query": "parser", "project_filter": "p",
                             "k": 5}, "CANARY-sr"),
    ("session", "show"): (["session", "show", "00000004"],
                          {"session": {"name": "session-00000004", "mtype": "session",
                                       "content": "# CANARY-card", "metadata": {}},
                           "mode": "card"},
                          {"action": "show", "session_id": "00000004", "mode": "card"},
                          "CANARY-card"),
    # ---- refine (the CLI_MAP twin is `refine list`) ----
    ("refine", "show"): (["refine", "show", "b9b9"],
                         {"candidate": {"id": "b9b9b9b9b9b9", "ts": "t", "status": "pending",
                                        "scope": "project", "project": "p",
                                        "suggested": {"name": "n", "mtype": "m",
                                                      "content": "CANARY-cbody"}}},
                         {"action": "show", "cand_id": "b9b9"}, "CANARY-cbody"),
}


def test_every_cli_action_has_a_wiring_row():
    assert set(CLI_ACTION_INVOKE) == set(verbs.CLI_ACTIONS), sorted(
        set(CLI_ACTION_INVOKE) ^ set(verbs.CLI_ACTIONS))


@pytest.mark.parametrize("path", sorted(CLI_ACTION_INVOKE), ids=lambda p: "-".join(p))
def test_cli_action_twin_calls_its_dispatcher_verb(path, _cli_env, monkeypatch):
    """AC-6, the recorder shape of `test_cli_twin_calls_its_verb`: the verb is
    CALLED with the root, `action=<x>` and the argv's options ARRIVE as the
    verb's own parameters (bound against the real signature), and the CLI
    RENDERS the verb's result (canary). The verb is resolved from the local
    seed, not `verbs.CLI_ACTIONS`, so each twin's wiring is judged on its own."""
    import inspect
    argv, canned, expect, canary = CLI_ACTION_INVOKE[path]
    vname, _action = _ACTIONS_SEED[path]
    v = verbs.VERBS[vname]
    sig = inspect.signature(v.fn)
    seen = []

    def recorder(root, *a, **kw):
        bound = sig.bind(root, *a, **kw)      # a wrong kwarg name fails here
        bound.apply_defaults()
        seen.append(bound.arguments)
        return json.loads(json.dumps(canned))
    monkeypatch.setattr(verbs, v.fn.__name__, recorder)
    r = CliRunner().invoke(cli_main, argv, catch_exceptions=False)
    assert r.exit_code == 0, r.output + (r.stderr or "")
    assert seen, f"`rmx {' '.join(argv)}` never called verbs.{v.fn.__name__}"
    assert all(Path(s["root"]) == _cli_env for s in seen)
    last = seen[-1]
    for k, val in expect.items():
        got = last.get(k)
        if isinstance(got, tuple):
            got = list(got)
        assert got == val, f"{' '.join(path)}.{k}: argv gave {got!r}, expected {val!r}"
    assert canary in r.output, f"{' '.join(path)}: CLI did not render the verb's result ({canary!r})"


# ---- task 3.7 C6 (r1 S1): EVERY CLI_ACTIONS twin's click defaults ---------------
#
# The CLI_MAP-twin test above sees one command per verb, and a dispatcher's shared
# params conflict across actions (focus `top` 20 vs 60). Each action twin is compared
# against `verbs.ACTION_DEFAULTS[(verb, action)]` over the verb's own defaults, and
# every click option must BE a verb param (C9) unless it is a declared CLI-only
# render option (r3 M1 `--out`, r6 S1 `--limit`). No "ALL" escape for a new verb.
#
# path -> ({verb_param: click_param}, {CLI-only click params})
ACTION_PAIRING = {
    ("task", "push"): ({}, set()),
    ("task", "pop"): ({}, set()),
    ("task", "current"): ({}, set()),
    ("task", "swap"): ({}, set()),
    ("focus", "tail"): ({}, set()),
    ("focus", "topics"): ({}, set()),
    ("focus", "show"): ({"context": "ctx"}, set()),
    ("focus", "subject"): ({}, set()),
    ("focus", "subjects"): ({}, set()),
    ("focus", "clear-subject"): ({}, set()),
    ("focus", "composite"): ({}, set()),
    ("focus", "export"): ({}, {"out", "as_json"}),
    ("focus", "detour"): ({}, set()),
    ("focus", "detours"): ({}, set()),
    ("focus", "return"): ({}, set()),
    ("focus", "clear"): ({}, set()),
    ("unprotect",): ({}, set()),
    ("noise",): ({}, set()),
    ("unnoise",): ({}, set()),
    ("forget",): ({}, {"yes"}),
    ("taxonomy", "add"): ({}, set()),
    ("taxonomy", "remove"): ({}, set()),
    ("curator", "drain"): ({}, set()),
    # task 3.7 batch B. `--via-replica` is dead on every snapshotted store and the verb
    # always routes by #budgets; `--format` / `--json` are renderings.
    ("co-occur",): ({}, set()),
    ("top",): ({}, set()),
    ("describe",): ({}, {"fmt", "via_replica"}),
    ("recall",): ({}, {"as_json"}),
    ("search-dense",): ({}, set()),
    ("stats",): ({}, {"via_replica"}),
    ("concept", "timeline"): ({"git": "no_git"}, {"as_json"}),
    ("canon", "siblings"): ({}, set()),
    ("canon", "link"): ({}, set()),
    # task 3.7 batch C
    ("add", "entity"): ({}, set()),
    ("add", "linkage-type"): ({}, set()),
    ("link",): ({}, set()),
    ("unlink",): ({}, set()),
    ("list", "entities"): ({}, {"as_json"}),
    ("list", "linkages"): ({}, set()),
    ("list", "queries"): ({}, set()),
    ("run",): ({}, set()),
    ("save-query",): ({}, set()),
    ("session", "recall"): ({"project_filter": "project"}, {"as_json"}),
    ("session", "show"): ({}, set()),
    ("refine", "show"): ({}, set()),
}
# (path, verb param) -> why the click default may differ from the resolved one.
ACTION_SHAPE_DIFFERENCES = {
    (("forget",), "dry_run"): "the verb previews by default over MCP (#fam-curation-forget); "
                              "the CLI keeps its confirm / -y gate and passes dry_run=False",
    (("curator", "drain"), "token"): "click multiple=True () vs verb None",
    (("recall",), "kinds"): "click multiple=True () vs verb None",
    (("recall",), "concept"): "click multiple=True () vs verb None (a str for other actions)",
    (("recall",), "symbolic"): "click multiple=True () vs verb None",
    (("search-dense",), "kinds"): "click multiple=True () vs verb None",
    (("concept", "timeline"), "git"): "inverted flag: click --no-git False == verb git True",
    (("session", "show"), "mode"): "three flag_value options share dest `mode`; the click "
                                   "default is the `--card` flag (default=True) vs verb 'card'",
}
# Pre-3.7 dispatcher whose per-action parity is its dedicated verbs' job (PAIRING
# "ALL"). Closed: no other verb may be escaped.
_ACTION_ESCAPE = {"rmx_memory": "per-action parity is rmx_memory_add / rmx_memory_recall's"}


def test_every_cli_action_twin_has_an_action_pairing_row():
    walked = {p for p, (v, _a) in verbs.CLI_ACTIONS.items() if v not in _ACTION_ESCAPE}
    assert set(ACTION_PAIRING) == walked, sorted(set(ACTION_PAIRING) ^ walked)
    assert set(_ACTION_ESCAPE) == {"rmx_memory"}


@pytest.mark.parametrize("path", sorted(ACTION_PAIRING), ids=lambda p: "-".join(p))
def test_cli_action_click_defaults_equal_the_resolved_verb_default(path):
    import inspect
    vname, action = verbs.CLI_ACTIONS[path]
    renames, cli_only = ACTION_PAIRING[path]
    v = verbs.VERBS[vname]
    params = set(inspect.signature(v.fn).parameters) - {"root"}
    resolved = {**v.defaults, **verbs.ACTION_DEFAULTS.get((vname, action), {})}
    cdefs = _click_defaults(_click_cmd(path))
    rev = {c: vp for vp, c in renames.items()}
    bad = []
    for name in cli_only:
        if name not in cdefs:
            bad.append(f"CLI-only {name!r} is not an option of {' '.join(path)}")
        elif rev.get(name, name) in params:
            bad.append(f"CLI-only {name!r} IS a verb param — compare it instead")
    for cname, cdefault in cdefs.items():
        if cname in cli_only:
            continue
        vp = rev.get(cname, cname)
        if vp not in params:
            bad.append(f"{' '.join(path)} --{cname}: no {vname} param {vp!r} (C9)")
            continue
        if (path, vp) in ACTION_SHAPE_DIFFERENCES:
            continue
        vdefault = resolved.get(vp)
        vdefault = list(vdefault) if isinstance(vdefault, tuple) else vdefault
        cdefault = list(cdefault) if isinstance(cdefault, tuple) else cdefault
        if cdefault != vdefault:
            bad.append(f"{vname}.{action}.{vp}: resolved verb default {vdefault!r} != "
                       f"CLI default {cdefault!r}")
    assert not bad, "\n" + "\n".join(bad)


def test_action_shape_differences_name_real_click_options():
    for (path, vp), why in ACTION_SHAPE_DIFFERENCES.items():
        renames, _cli_only = ACTION_PAIRING[path]
        assert renames.get(vp, vp) in _click_defaults(_click_cmd(path)), (path, vp)
        assert why.strip()


def test_legacy_shrinks_by_exactly_the_batched_paths():
    """C6 / AC-G5: 140 - 22 - 11 - 15 = 92; task 26.6 R-D: - 1 (`memory compile`) = 91,
    nothing else moved."""
    assert set(verbs.LEGACY_UNPAIRED) == set(LEGACY_BASELINE), sorted(
        set(verbs.LEGACY_UNPAIRED) ^ set(LEGACY_BASELINE))
