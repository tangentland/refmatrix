"""Task 3.7 remedy round 1 — RED (spec #remedy-r1; ch-bsd [[bsd-plan3-task37-impl-41c3568]]
+ the ch-code-reviewer pass). One section per decision row that changes behaviour.

R-B1   the generated hooks run `curator status` WITHOUT `--drain`; the CLI `--drain`
       drains only what that call printed (`max_entries = limit`).
R-B2   ONE partition resolver (flag → RMX_PARTITION → `.refmatrix/partition` marker →
       store name) shared by `cli._resolve_partition` and `verbs.project_partition`;
       `rmx_focus` gains `partition`; `rmx -p X focus composite` reads X.
R-S1   `link` / `unlink` / `canon link` send NAMES and the daemon ops resolve them under
       the writer (op level here; read-your-writes on a real daemon in test_task3_7_live).
R-S2   "an unknown partition reads EMPTY" — one test per guard (snapshot_read, read-only
       Store.with_partition); mutations M11 / M18 must die.
R-M2   a raw-path legacy `curator.queue` line is an entry with reason "legacy".
R-H1   N no-daemon `rmx_graph` recall/dense calls in one process → ONE embed client.
R-RM1  `_op_ann_search` resolves the store INSIDE `_store_lock`.
R-RM2  `_op_graph_recall` falls back to `d.partition`, never an unlocked store read.
R-RM5  forget's preview carries the 600 s budget too.
R-RM6  a taxonomy write that cannot write raises `VerbError` naming the file.
R-L    `session show` refuses an ambiguous prefix; an ignored `--via-replica` warns.
R-OBJC every generated hook command exports OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES and
       TOKENIZERS_PARALLELISM=false, so a hook-run `rmx` does not re-exec.

R-RM1 / R-RM2 are BEHAVIOURAL: the daemon's store is a sentinel that fails on any read
until `_store_lock` is entered, at which point the lock swaps the real store in — the
old code reads the store resolved outside the lock and hits the sentinel.
"""
from __future__ import annotations

import ast
import inspect
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod
from refmatrix import daemon as dm
from refmatrix import discovery, gmd_curator, verbs
from refmatrix import hooks as hooks_mod
from refmatrix.store import Store
from tests.task3_7_helpers import (FakeDaemon, HashEmbedder, graph_store, init_store,
                                   make_snapshot, rm, short_root)

_REPO = Path(__file__).resolve().parent.parent
_SRC = _REPO / "src" / "refmatrix"


@pytest.fixture
def root(monkeypatch):
    monkeypatch.delenv("RMX_PARTITION", raising=False)
    base, r = short_root("r37r-")
    monkeypatch.setattr(cli_mod, "_root", lambda: r)
    yield r
    rm(base)


def _hook_commands(tmp_path) -> list:
    block = hooks_mod._claude_hook_block(tmp_path / ".refmatrix")
    return [h["command"] for evs in block["hooks"].values() for e in evs
            for h in e.get("hooks", []) if "command" in h]


# ---- R-B1 ---------------------------------------------------------------------------------


def test_no_generated_hook_drains_the_curator_spool(tmp_path):
    segs = [seg.strip() for c in _hook_commands(tmp_path) for seg in c.split(";")
            if "curator status" in seg]
    assert segs, "no generated hook runs `rmx curator status`"
    bad = [s for s in segs if "--drain" in s]
    assert not bad, f"a prompt hook drains entries the curator never saw: {bad}"


def test_cli_drain_that_printed_more_leaves_the_rest_in_the_spool(root):
    """The ledger's probe: 15 paths, the line shows 10 and "+5 more" — the 5 were never
    shown, so they must survive."""
    gmd_curator.write_spool(root, [str(root.parent / f"PLAN-{i}.md") for i in range(15)])
    r = CliRunner().invoke(cli_mod.main, ["curator", "status", "--drain"])
    assert r.exit_code == 0, r.output
    assert "+5 more" in r.output, r.output
    assert gmd_curator.read_spool(root)["entries"], "the hook emptied what it only counted"


def test_cli_drain_removes_exactly_the_files_it_printed(root):
    names = [gmd_curator.write_spool(root, [str(root.parent / f"PLAN-{i}{j}.md")
                                            for j in "ab"]) for i in range(3)]
    r = CliRunner().invoke(cli_mod.main, ["curator", "status", "--drain", "--limit", "4"])
    assert r.exit_code == 0, r.output
    left = gmd_curator.read_spool(root)
    assert left["token"] == names[2:], left["token"]
    for i in range(2):
        assert f"PLAN-{i}a.md" in r.output and f"PLAN-{i}b.md" in r.output


# ---- R-B2 ---------------------------------------------------------------------------------


def _marker(root, name):
    (root / "partition").write_text(name + "\n")


def test_project_partition_reads_the_partition_marker(root, monkeypatch):
    _marker(root, "px")
    monkeypatch.chdir(root.parent)
    assert verbs.project_partition(root) == "px"
    assert cli_mod._resolve_partition() == "px"


def test_env_beats_the_marker_in_both(root, monkeypatch):
    _marker(root, "px")
    monkeypatch.chdir(root.parent)
    monkeypatch.setenv("RMX_PARTITION", "pe")
    assert verbs.project_partition(root) == "pe"
    assert cli_mod._resolve_partition() == "pe"


def test_no_override_is_the_store_name_in_both(root, monkeypatch):
    monkeypatch.chdir(root.parent)
    assert verbs.project_partition(root) == cli_mod._resolve_partition() == "proj"


def _callees(mod_path: Path, fn_name: str) -> set:
    tree = ast.parse(mod_path.read_text())
    fn = next(f for f in ast.walk(tree) if isinstance(f, ast.FunctionDef) and f.name == fn_name)
    out = set()
    for c in ast.walk(fn):
        if isinstance(c, ast.Call):
            f = c.func
            out.add(f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None))
    return out


def test_one_resolver_is_shared_by_the_cli_and_the_verbs():
    """R-B2: ONE function decides flag → env → marker → store name; both entry points
    call it (the defect was two orders that disagreed on the marker)."""
    defined = set()
    for p in _SRC.rglob("*.py"):
        defined |= {f.name for f in ast.parse(p.read_text()).body
                    if isinstance(f, ast.FunctionDef)}
    common = (_callees(_SRC / "cli.py", "_resolve_partition")
              & _callees(_SRC / "verbs.py", "project_partition")) & defined
    common -= {"store_name", "default_partition_name", "_root"}
    assert common, "cli._resolve_partition and verbs.project_partition share no resolver"


def test_rmx_focus_takes_a_partition():
    assert "partition" in inspect.signature(verbs.focus).parameters
    assert "partition" in verbs.VERBS["rmx_focus"].schema["properties"]


def test_cli_focus_composite_forwards_the_cli_partition(root, monkeypatch):
    seen: list = []
    monkeypatch.setattr(verbs, "focus", lambda r, **kw: seen.append(kw) or {
        "composite": "CANARY", "session": "S1", "session_source": "explicit"})
    r = CliRunner().invoke(cli_mod.main, ["-p", "px", "focus", "composite", "--session", "S1"])
    assert r.exit_code == 0, r.output
    assert seen and seen[-1].get("partition") == "px", seen


def test_focus_composite_reads_the_partition_it_is_given(root, monkeypatch):
    from refmatrix import stm as stm_mod
    graph_store(root, partition="px")
    s = stm_mod.Stm(root, "sA")
    for _ in range(4):
        s.record("input", "AlphaParser alpha_lexer AlphaToken working")
    real = verbs.snapshot_read
    parts: list = []

    def spy(r, fn, *, partition):
        parts.append(partition)
        return real(r, fn, partition=partition)
    monkeypatch.setattr(verbs, "snapshot_read", spy)
    verbs.focus(root, action="composite", session="sA", partition="px")
    assert parts and set(parts) == {"px"}, parts


# ---- R-S1 (op level): the write ops resolve NAMES under the writer --------------------------


def _daemon_with(root):
    s = Store(root)
    s.init()
    d = dm.Daemon(root)
    d.store = s
    d._log = lambda msg: None
    d._request_snapshot = lambda: None
    return d, s


def test_the_link_and_unlink_ops_take_names(root):
    graph_store(root)
    d, s = _daemon_with(root)
    p = discovery.store_name(root)
    try:
        out = dm.OPS["link"](d, {"linkage": "defines", "concept": "beta", "entity": "d0.md",
                                  "partition": p})
        assert out["created"] is True, out
        out2 = dm.OPS["unlink"](d, {"linkage": "defines", "concept": "beta",
                                     "entity": "d0.md", "partition": p})
        assert out2["unlinked"] is True, out2
    finally:
        s.close()


def test_the_link_canon_op_takes_a_name(root):
    graph_store(root)
    d, s = _daemon_with(root)
    try:
        out = dm.OPS["link_canon"](d, {"concept": "alpha", "canon_partition": "canon",
                                        "canon_concept_name": "Alpha",
                                        "partition": discovery.store_name(root)})
        assert isinstance(out["canon_id"], int), out
    finally:
        s.close()


def test_the_verbs_send_names_not_snapshot_ids(root, monkeypatch):
    """No snapshot exists: a verb that resolves ids on the snapshot cannot even start."""
    fd = FakeDaemon({"link": {"ok": True, "result": {"created": True}},
                     "unlink": {"ok": True, "result": {"unlinked": True}},
                     "link_canon": {"ok": True, "result": {"canon_id": 9}}}).install(monkeypatch)
    verbs.matrix(root, action="link", concept="beta", entity="d0.md")
    verbs.matrix(root, action="unlink", concept="beta", entity="d0.md")
    verbs.canon(root, action="link", concept="alpha")
    for op in ("link", "unlink"):
        a = fd.last(op)[1]
        assert a["concept"] == "beta" and a["entity"] == "d0.md", (op, a)
    assert fd.last("link_canon")[1]["concept"] == "alpha"


# ---- R-S2: unknown partition reads EMPTY (kills M11 / M18) ----------------------------------


def _partition_one_is_proj(root):
    s = Store(root, read_only=True)
    try:
        row = s._connect().execute("SELECT id FROM partitions WHERE name=?",
                                   ("proj",)).fetchone()
    finally:
        s.close()
    assert row is not None and row[0] == 1, ("precondition: proj is partition 1", row)


def test_snapshot_read_of_an_unknown_partition_is_empty(root):
    graph_store(root)
    _partition_one_is_proj(root)

    def fn(s):
        n = s._connect().execute("SELECT count(*) FROM entities WHERE partition_id=?",
                                 (s._partition_id,)).fetchone()[0]
        return {"n": n, "alpha": s.get_entity("concept", "alpha") is not None}
    out = verbs.snapshot_read(root, fn, partition="no-such-partition")
    assert out["n"] == 0 and out["alpha"] is False, (
        "an unknown partition answered from partition 1", out)


def test_read_only_with_partition_of_an_unknown_partition_is_empty(root):
    graph_store(root)
    _partition_one_is_proj(root)
    s = Store(root, read_only=True)
    try:
        with s.with_partition("no-such-partition"):
            assert s.get_entity("concept", "alpha") is None, (
                "read-only with_partition answered from partition 1")
            assert s._partition_id != 1
    finally:
        s.close()


# ---- R-M2: raw-path legacy lines are legacy entries ------------------------------------------


def test_a_raw_path_legacy_queue_line_is_a_legacy_entry(root):
    (root / "curator.queue").write_text("docs/plan/a.md\n/abs/ADR-1.md\n")
    out = verbs.curator(root, action="status")
    got = [(e["path"], e["reason"]) for e in out["entries"]]
    assert got == [("docs/plan/a.md", "legacy"), ("/abs/ADR-1.md", "legacy")], out
    assert not out["warnings"], out["warnings"]


# ---- R-H1: one embed client per process -------------------------------------------------------


def test_no_daemon_graph_calls_share_one_embed_client(root, monkeypatch):
    import atexit

    from refmatrix import recall as recall_mod
    from refmatrix import subproc
    graph_store(root)
    monkeypatch.setenv("RMX_RERANK", "0")
    monkeypatch.setattr(subproc, "subproc_embed_enabled", lambda: True)
    # Off the machine's live hub socket: a cached non-shared client may be re-probed
    # against the hub (remedy r3 S-1), and this test's fake is not a worker.
    monkeypatch.setenv("RMX_SHARED_MODELS", "0")
    # All four process-wide globals (ch-bsd r2 #m-2/#m-3): a leaked ATEXIT flag made the
    # registration count below 0 whatever the code did.
    monkeypatch.setattr(recall_mod, "_EMBED_CLIENT", None)
    monkeypatch.setattr(recall_mod, "_EMBED_CLIENT_ISSUED", None)
    monkeypatch.setattr(recall_mod, "_EMBED_CLIENT_REBUILDS", 0)
    monkeypatch.setattr(recall_mod, "_EMBED_CLIENT_ATEXIT", False)
    clients: list = []

    class _Client:
        def close(self, *a, **k):
            pass
    monkeypatch.setattr(recall_mod, "new_model_client",
                        lambda *a, **k: clients.append(_Client()) or clients[-1])
    monkeypatch.setattr(recall_mod, "remote_embedder", lambda client, *a, **k: HashEmbedder())
    # Counts EVERY callable `refmatrix.recall` registers (ch-bsd r2 #m-3: the spy counted
    # only functions named `close`, and the closer is `_close_process_embed_client`, so
    # the count was always 0). Recorded, not really registered.
    closes: list = []
    real_register = atexit.register
    monkeypatch.setattr(atexit, "register",
                        lambda fn, *a, **k: (closes.append(fn) or fn)
                        if getattr(fn, "__module__", "") == recall_mod.__name__
                        else real_register(fn, *a, **k))
    for _ in range(3):
        verbs.graph(root, action="dense", query="document number 3", k=3)
    for _ in range(2):
        verbs.graph(root, action="recall", query="document number 3", k=3)
    assert len(clients) <= 1, f"{len(clients)} embed clients for 5 calls in one process"
    assert closes == [recall_mod._close_process_embed_client], (
        f"{len(closes)} atexit closer(s) registered for one process: {closes}")


# ---- R-RM1 / R-RM2: no store read outside _store_lock -----------------------------------------


class _Unlocked:
    def __getattr__(self, n):
        raise AssertionError(f"store.{n} read OUTSIDE _store_lock")


class _SwapInLock:
    """Delegates to the daemon's real lock; on enter, swaps the real store in."""

    def __init__(self, d, real_lock, store):
        self.d, self.lock, self.store = d, real_lock, store

    def __enter__(self):
        self.lock.__enter__()
        self.d.store = self.store
        return self

    def __exit__(self, *exc):
        return self.lock.__exit__(*exc)

    def acquire(self, *a, **k):
        got = self.lock.acquire(*a, **k)
        if got:
            self.d.store = self.store
        return got

    def release(self):
        return self.lock.release()

    def __getattr__(self, n):
        return getattr(self.lock, n)


def _sentinel_daemon(root, monkeypatch):
    graph_store(root)
    make_snapshot(root)
    monkeypatch.setattr("refmatrix.recall.shared_embedder", lambda r, *a, **k: HashEmbedder())
    s = Store(root)
    s.init()
    d = dm.Daemon(root)
    d._log = lambda msg: None
    d._embedder_inst = HashEmbedder()
    d._store_lock = _SwapInLock(d, d._store_lock, s)
    d.store = _Unlocked()
    return d, s


def test_ann_search_resolves_the_store_inside_the_lock(root, monkeypatch):
    d, s = _sentinel_daemon(root, monkeypatch)
    try:
        out = dm.OPS["ann_search"](d, {"query": "document number 3", "k": 3, "rerank": False,
                                        "partition": discovery.store_name(root)})
    finally:
        s.close()
    assert out["hits"] and out["hits"][0]["id"] == 6, out


def test_graph_recall_takes_the_partition_from_d_partition(root, monkeypatch):
    d, s = _sentinel_daemon(root, monkeypatch)
    d.partition = discovery.store_name(root)
    try:
        out = dm.OPS["graph_recall"](d, {"query": "document number 3", "k": 3})
    finally:
        s.close()
    assert [h["id"] for h in out["hits"]][:1] == [6], out


# ---- R-RM5 / R-RM6 ----------------------------------------------------------------------------


def test_forget_preview_carries_the_600s_budget(root, monkeypatch):
    fd = FakeDaemon({"forget": {"ok": True, "result": {"forgotten": 0, "names": ["a"],
                                                       "dry_run": True}}}).install(monkeypatch)
    verbs.curate(root, action="forget", names=["a"])
    _op, args, timeout, _r = fd.last("forget")
    assert args["dry_run"] is True and timeout == 600.0, (args, timeout)


def test_a_taxonomy_write_that_cannot_write_names_the_file(tmp_path, root, monkeypatch):
    home = tmp_path / "rmxhome"
    home.mkdir()
    monkeypatch.setenv("RMX_HOME", str(home))
    verbs.taxonomy(root, action="add", category="c", tag="t1")
    home.chmod(0o500)
    try:
        with pytest.raises(verbs.VerbError) as ei:
            verbs.taxonomy(root, action="add", category="c", tag="t2")
        assert "taxonomy.json" in str(ei.value), str(ei.value)
    finally:
        home.chmod(0o700)


# ---- R-L ------------------------------------------------------------------------------------


def _session_cards(root):
    init_store(root)
    s = Store(root)
    try:
        with s.with_partition("sessions-proj"):
            for i in (1, 2):
                sid = f"0000000{i}-aaaa-bbbb-cccc-dddddddddddd"
                s.add_memory(name=f"session-{sid[:8]}", content=f"# S{i} {{#root}}\nx",
                             mtype="session", metadata={"session_id": sid,
                                                        "ended": f"2026-10-0{i}"})
    finally:
        s.close()


def test_session_show_refuses_an_ambiguous_prefix(root):
    _session_cards(root)
    with pytest.raises(verbs.VerbArgsError):
        verbs.session(root, action="show", session_id="0000000")
    r = CliRunner().invoke(cli_mod.main, ["session", "show", "0000000"])
    assert r.exit_code != 0 and "matches 2" in r.output, r.output


@pytest.mark.parametrize("argv", [["neighbors", "alpha", "--via-replica"],
                                  ["describe", "d0.md", "--via-replica", "--no-vectors"]])
def test_an_ignored_via_replica_warns_that_it_is_deprecated(root, argv):
    graph_store(root)
    r = CliRunner().invoke(cli_mod.main, argv)
    assert r.exit_code == 0, r.output
    assert "deprecated" in (r.output + (r.stderr or "")).lower(), r.output


# ---- R-OBJC -------------------------------------------------------------------------------------

_FORK_ENV = {"OBJC_DISABLE_INITIALIZE_FORK_SAFETY": "YES", "TOKENIZERS_PARALLELISM": "false"}


def test_every_generated_rmx_hook_exports_the_fork_safety_env(tmp_path):
    cmds = [c for c in _hook_commands(tmp_path) if "rmx " in c]
    assert cmds
    for c in cmds:
        for k, v in _FORK_ENV.items():
            assert f"{k}={v}" in c, (k, c[:160])


@pytest.mark.skipif(sys.platform != "darwin", reason="the re-exec is macOS-only")
def test_a_hook_run_rmx_does_not_re_exec():
    exports = dict(re.findall(r"export ([A-Z_]+)=([^;\s]+)", hooks_mod.HOOK_ENV))
    env = {k: v for k, v in os.environ.items() if k not in _FORK_ENV}
    env.update(exports)
    probe = ("import os, sys\n"
             "os.execv = lambda *a: (print('RE-EXEC'), sys.exit(3))\n"
             "from refmatrix import cli\n"
             "cli._reexec_for_fork_safety()\n"
             "print('NO-REEXEC')\n")
    r = subprocess.run([sys.executable, "-c", probe], env=env, capture_output=True, text=True,
                       timeout=120)
    assert "NO-REEXEC" in r.stdout and "RE-EXEC" not in r.stdout.replace("NO-REEXEC", ""), (
        r.stdout, r.stderr[-800:])
