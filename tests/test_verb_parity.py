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

EFFECTIVE_DEFAULTS = {
    "rmx_context": {"max_entities": 20, "max_tokens": 4000},
}
# verb -> (click path, {verb_param: click_param}, verb params with no CLI twin)
PAIRING = {
    "rmx_context": (("context",), {"ref": "symbol"}, {"linkage"}),
    "rmx_query": (("query",), {"dsl": "expr"}, set()),
    "rmx_memory_add": (("memory", "add"), {"to_global": "is_global"}, {"tags", "metadata"}),
    # `partition`: the CLI carries it on the `rmx` group (`-p`), not the subcommand
    "rmx_memory_recall": (("memory", "recall"), {}, {"since_seconds", "kinds", "exclude_mtype", "partition"}),
    "rmx_ingest": (("ingest",), {}, {"path", "mode", "kinds", "limit", "rebuild", "partition"}),
    "rmx_save_state": (("save-state",), {}, {"lint", "sync"}),
    "rmx_focus": (("focus", "context"), {}, set()),
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


# ---- wiring (#bs-1): the twin CALLS the verb -------------------------------

# verb -> (click argv, canned verb result, kwargs the argv must reach the verb
# with, a CANARY string from the canned result the CLI output must show).
# The kwargs + canary are what turn the recorder from "was called" into "the
# options arrive and the result is what gets rendered" (ch-bsd plan-3 r2 #s-3:
# a twin that called the verb and then rendered from the ring passed).
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
LEGACY_BASELINE_SIZE = 140
LEGACY_BASELINE = frozenset({
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


def test_cli_actions_are_the_fifteen_dispatcher_twins():
    """AC-5: r8 #s-4 item 1 — these 15 would otherwise land in LEGACY."""
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
    assert len(LEGACY_BASELINE) == LEGACY_BASELINE_SIZE
    legacy = set(verbs.LEGACY_UNPAIRED)
    grown = sorted(legacy - LEGACY_BASELINE)
    assert not grown, f"LEGACY_UNPAIRED grew (verb it or INTERNAL_CLI instead): {grown}"
    assert len(legacy) <= LEGACY_BASELINE_SIZE
    cats = set(verbs.LEGACY_CATEGORIES)
    assert cats == {"verb-it", "operator", "maintenance", "hook", "harness"}, cats
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
    ("memory", "brief"): (["memory", "brief", "--json"],
                          {"briefs": [{"class": "singleton", "label": "CANARY-brief",
                                       "finding": "f", "evidence": [1]}], "stats": {}},
                          {"action": "brief"}, "CANARY-brief"),
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
