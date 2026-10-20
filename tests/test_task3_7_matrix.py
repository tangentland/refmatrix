"""Task 3.7 batch C — the matrix-edit family as `rmx_matrix` actions (RED).

Spec #fam-matrix-edit, #budgets: actions add_concept, add_entity, add_linkage_type,
link, unlink, list_entities, list_linkages, list_queries, run, save_query.
  - writes via `_call` (60 s, single attempt, `write=True` classification); absent ⇒
    `local_write` (C4a); reads (`list_*`, `run`) via `snapshot_read`;
  - #fam-matrix-edit-partition: `_op_add_concept` / `_op_upsert_entity` honour
    `partition` (they wrote to the daemon's bound partition, so `rmx -p X add concept
    foo` then `rmx -p X link foo …` could not find it);
  - `list_entities` gains `limit` (default 200) and the CLI gains `--json` (a logged
    agent call `list entities --json` failed with exit 2);
  - #fam-matrix-edit-dead: the uncalled, writer-locking ops `iter_entities`,
    `list_linkages`, `list_saved_queries` leave `OPS` AND the interactive-pool list
    (`CLI_OPS`) unless a verb calls one;
  - the hidden aliases (`add-concept`, …) follow their targets.

Verb params are the click dest names (C9): name, description, no_protect, kind, path,
tldr, meta, directed, concept, entity, linkage, want_protected, want_noise, limit,
is_pql, ids_only, body, partition, timeout. `limit` is `int | None`, resolved per action
(list_entities 200, run 50). Result shapes pinned: add_* {id}; link {created}; unlink
{unlinked}; save_query {saved, name}; list_entities / list_linkages {rows}; list_queries
{rows:[{name, body}]}; run {rows:[{id, …}]}.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod
from refmatrix import daemon as dm
from refmatrix import discovery, verbs
from refmatrix.store import Store
from tests.task3_7_helpers import (FakeDaemon, entity_names, graph_store, init_store,
                                   make_snapshot, rm, short_root)

_REPO = Path(__file__).resolve().parent.parent


@pytest.fixture
def root(monkeypatch):
    monkeypatch.delenv("RMX_PARTITION", raising=False)
    base, r = short_root("r37m-")
    monkeypatch.setattr(cli_mod, "_root", lambda: r)
    yield r
    rm(base)


# ---- #fam-matrix-edit-partition: the two ops honour `partition` ----------------------


def _daemon_on(root):
    s = Store(root)
    s.init()
    d = dm.Daemon(root)
    d.store = s
    d._log = lambda msg: None
    return d, s


@pytest.mark.parametrize("op,args,kind", [
    ("add_concept", {"name": "foo"}, "concept"),
    ("upsert_entity", {"kind": "doc", "name": "foo.md"}, "doc"),
])
def test_the_write_op_lands_in_the_requested_partition(root, op, args, kind):
    init_store(root)
    d, s = _daemon_on(root)
    try:
        dm.OPS[op](d, {**args, "partition": "px"})
    finally:
        s.close()
    assert entity_names(root, kind, partition="px") == {args["name"]}, (
        f"{op} ignored partition — it wrote to the daemon's bound partition")
    assert entity_names(root, kind) == set()


# ---- writes: one classified attempt, partition forwarded ------------------------------


def test_add_concept_is_one_write_with_partition(root, monkeypatch):
    fd = FakeDaemon({"add_concept": {"ok": True, "result": {"id": 4242}}}).install(monkeypatch)
    out = verbs.matrix(root, action="add_concept", name="foo", description="d",
                       no_protect=True, partition="px")
    _op, args, timeout, retries = fd.last("add_concept")
    assert args["name"] == "foo" and args["description"] == "d"
    assert args["protected"] is False and args["partition"] == "px", args
    assert timeout == 60.0 and retries == 0
    assert out["id"] == 4242


def test_add_entity_forwards_its_fields(root, monkeypatch):
    fd = FakeDaemon({"upsert_entity": {"ok": True, "result": {"id": 7}}}).install(monkeypatch)
    verbs.matrix(root, action="add_entity", kind="doc", name="x.md", path="/p/x.md",
                 tldr="t", meta='{"a": 1}')
    _op, args, _t, _r = fd.last("upsert_entity")
    assert (args["kind"], args["name"], args["path"], args["tldr"]) == ("doc", "x.md",
                                                                        "/p/x.md", "t")
    assert args["meta"] in ('{"a": 1}', {"a": 1}) and args["protected"] is True
    assert args["partition"] == discovery.store_name(root)


def test_link_resolves_its_ends_and_sends_one_write(root, monkeypatch):
    ids = graph_store(root)
    make_snapshot(root)
    fd = FakeDaemon({"link": {"ok": True, "result": {"created": True}}}).install(monkeypatch)
    out = verbs.matrix(root, action="link", concept="beta", entity="d0.md", linkage="defines")
    _op, args, timeout, retries = fd.last("link")
    assert args["concept_id"] == ids["beta"] and args["entity_id"] == ids["docs"][0], args
    assert args["linkage"] == "defines" and timeout == 60.0 and retries == 0
    assert out["created"] is True


def test_a_write_timeout_is_busy_and_not_confirmed(root, monkeypatch):
    FakeDaemon({"add_concept": TimeoutError("timed out")}).install(monkeypatch)
    with pytest.raises(verbs.VerbBusyError) as ei:
        verbs.matrix(root, action="add_concept", name="foo")
    assert "not confirmed" in str(ei.value)


def test_a_write_refusal_carries_the_daemons_words(root, monkeypatch):
    FakeDaemon({"add_linkage_type": {"ok": False, "error": "CANARY-lt-no"}}).install(monkeypatch)
    with pytest.raises(verbs.VerbError) as ei:
        verbs.matrix(root, action="add_linkage_type", name="frob")
    assert "CANARY-lt-no" in str(ei.value)


# ---- C4a: no daemon ⇒ in-process ---------------------------------------------------------


def test_no_daemon_add_then_link_then_list_in_process(root):
    init_store(root, [("doc", "a.md")])
    assert not dm.ping(root)
    c = verbs.matrix(root, action="add_concept", name="topic")
    assert c["source"] == "in-process" and isinstance(c["id"], int), c
    lk = verbs.matrix(root, action="link", concept="topic", entity="a.md")
    assert lk["created"] is True, lk
    rows = verbs.matrix(root, action="list_entities", kind="concept")["rows"]
    assert "topic" in [r["name"] for r in rows]


def test_no_daemon_save_query_then_run(root):
    ids = graph_store(root)
    verbs.matrix(root, action="save_query", name="q1", body="mentions:alpha")
    qs = verbs.matrix(root, action="list_queries")["rows"]
    assert {"name": "q1", "body": "mentions:alpha"} in qs, qs
    out = verbs.matrix(root, action="run", name="q1")
    assert sorted(r["id"] for r in out["rows"]) == ids["docs"][:4], out


def test_list_linkages_reads_the_registered_types(root):
    graph_store(root)
    rows = verbs.matrix(root, action="list_linkages")["rows"]
    assert "mentions" in [r["name"] for r in rows]


# ---- list_entities: limit + CLI --json -----------------------------------------------------


def test_list_entities_defaults_to_200_rows(root):
    init_store(root, [("doc", f"f{i:03d}.md") for i in range(205)])
    out = verbs.matrix(root, action="list_entities")
    assert len(out["rows"]) == 200, len(out["rows"])
    assert len(verbs.matrix(root, action="list_entities", limit=5)["rows"]) == 5


def test_cli_list_entities_json(root):
    init_store(root, [("code", "x.py")])
    r = CliRunner().invoke(cli_mod.main, ["list", "entities", "--kind", "code", "--json"])
    assert r.exit_code == 0, r.output
    doc = json.loads(r.output)
    rows = doc["rows"] if isinstance(doc, dict) else doc
    assert [x["name"] for x in rows] == ["x.py"], doc


# ---- #fam-matrix-edit-dead -------------------------------------------------------------------


_DIALS = {"_call", "call", "global_call", "_write_or_local", "_memory_daemon_call",
          "_session_call"}


def _src_dials_of(op: str) -> list:
    """Every src call that DIALS the daemon op `op`: a call of `_call` / `daemon.call` /
    `global_call` (or a wrapper that takes the op name the same way) whose op argument is
    the literal `op`. A string that merely equals an op name — `list_linkages` is also an
    rmx_matrix ACTION — is not a dial."""
    import ast
    hits = []
    for p in sorted((_REPO / "src" / "refmatrix").rglob("*.py")):
        for c in ast.walk(ast.parse(p.read_text())):
            if not isinstance(c, ast.Call):
                continue
            f = c.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
            if name not in _DIALS:
                continue
            args = list(c.args) + [k.value for k in c.keywords if k.arg == "op"]
            if any(isinstance(a, ast.Constant) and a.value == op for a in args):
                hits.append(f"{p.name}:{c.lineno}")
    return hits


@pytest.mark.parametrize("op", ["iter_entities", "list_linkages", "list_saved_queries"])
def test_a_dead_writer_locking_read_op_is_gone_unless_a_verb_calls_it(op):
    if _src_dials_of(op):          # something in src dials it: then it must exist
        assert op in dm.OPS, f"{op} is dialled ({_src_dials_of(op)}) but not served"
        return
    assert op not in dm.OPS, f"{op} is still registered"
    assert op not in dm.CLI_OPS, f"{op} is still on the interactive pool list"


# ---- the hidden aliases follow their targets -----------------------------------------------


def test_every_hidden_alias_target_is_a_rmx_matrix_twin():
    for alias, target in verbs.HIDDEN_ALIASES.items():
        twin = "rmx_matrix" if verbs.CLI_MAP.get("rmx_matrix") == target else (
            verbs.CLI_ACTIONS.get(target, (None, None))[0])
        assert twin == "rmx_matrix", (alias, target, twin)


def test_a_hidden_alias_calls_the_verb_like_its_target(root, monkeypatch):
    import inspect
    sig = inspect.signature(verbs.matrix)
    seen: list = []

    def rec(r, *a, **kw):
        b = sig.bind(r, *a, **kw)
        b.apply_defaults()
        seen.append(b.arguments)
        return {"id": 4242}
    monkeypatch.setattr(verbs, "matrix", rec)
    res = CliRunner().invoke(cli_mod.main, ["add-concept", "foo"])
    assert res.exit_code == 0, res.output
    assert seen and seen[-1]["action"] == "add_concept" and seen[-1]["name"] == "foo"
    assert "4242" in res.output
