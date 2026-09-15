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
    "rmx_memory_recall": (("memory", "recall"), {}, {"since_seconds", "kinds", "exclude_mtype"}),
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
                   {"results": [{"path": "/x/CANARY-path.py", "project": "p", "score": 1.0, "why": []}], "skipped": []},
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
