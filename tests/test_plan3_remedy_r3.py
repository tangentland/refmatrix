"""ch-bsd plan-3 r3 remediation: #b-1 the promote-digest write path never
opens the store under a busy daemon; #b-2 `rmx locate` and the remaining
fan-outs report skipped stores; #s-3 the last bare pings classify; #s-4 a
socket timeout on an op IS busy (tested), promote goes through the wrappers;
#m-5 read twins fall through to the lock-free reader on busy, loudly; the
hub's queue rows say busy instead of down."""
from __future__ import annotations

import os
import shutil
import tempfile
import time
from pathlib import Path

import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod
from refmatrix import daemon as daemon_mod
from refmatrix import hub as hub_mod
from refmatrix import verbs
from refmatrix.cli import main as cli_main
from refmatrix.store import Store
from tests.test_plan2_remedy import _SilentDaemon, _PingOnlyDaemon


@pytest.fixture
def silent():
    d = _SilentDaemon(); yield d; d.close()


@pytest.fixture
def pingonly():
    d = _PingOnlyDaemon(); yield d; d.close()


# ---- #b-1 promote never opens the slot under a busy daemon ---------------------

def test_promote_digest_queues_on_a_busy_daemon_and_never_opens_the_store(silent):
    """#b-1: under a busy daemon the promote never opens the writer slot, and the handoff is
    written.

    Was `test_promote_digest_reports_busy_and_never_opens_the_store`. task-hook-writes-queue
    (L212, 2026-11-24; R11.4-R11.5, AC-8) reversed its busy half: the save-state promote is
    best-effort, its handoff file is already on disk and the subject filing rides in the
    entry, so a busy daemon QUEUES the digest (the busy probe enqueues without a dial).
    `_promote_digest` returns `{"queued": <name>, "name": <name>, "note": QUEUED_WRITE_MSG}`
    with no `error`, and `verbs.save_state` RETURNS (no `SaveStateIncompleteError`: bug-212 r5 /
    L95's raise is for a promote that FAILED, and a queued one did not). The two protections
    this test exists for stand: the writer slot is never opened (no `catalog*.duckdb`
    appears) and the handoff file is written. Each call leaves its own spool entry."""
    from refmatrix import handoff, stm as stm_mod
    from tests.held_writer import spool_files
    name = "focus_summary_s1"
    note = verbs.QUEUED_WRITE_MSG.format(name=name) if hasattr(verbs, "QUEUED_WRITE_MSG") \
        else None
    s = stm_mod.Stm(silent.root, "s1"); s.record("input", "hi")
    out = handoff._promote_digest(silent.root, s)
    assert not out.get("error"), f"a busy daemon must queue the promote, not fail it: {out}"
    assert (out.get("queued"), out.get("name"), out.get("note")) == (name, name, note), out
    assert not list(silent.root.glob("catalog*.duckdb")), "opened the writer slot under a busy daemon"
    res = verbs.save_state(silent.root, session="s1", memory_dir=str(silent.base / "mem"),
                           lint=False, sync=False)
    promoted = res.get("promoted") or {}
    assert not promoted.get("error") and promoted.get("queued") == name, res
    assert Path(res["target"]).is_file(), f"the handoff was not written: {res.get('target')}"
    assert not list(silent.root.glob("catalog*.duckdb"))
    assert len(spool_files(silent.root)) == 2, spool_files(silent.root)


# ---- #b-2 skipped stores reach the operator ------------------------------------

def test_locate_cli_prints_skipped_stores(silent, monkeypatch):
    monkeypatch.setattr(cli_mod, "_root", lambda: silent.root)
    monkeypatch.setattr("refmatrix.discovery.discover_roots", lambda: [silent.root])
    r = CliRunner().invoke(cli_main, ["locate", "x.md"])
    assert r.exit_code == 0, r.output
    assert "no matches" in r.output and "1 store" in r.output and "skipped" in r.output
    assert "busy" in (r.stderr or "") and "skipped" in (r.stderr or "")


def test_federated_query_and_concept_carry_skipped(silent, monkeypatch):
    from refmatrix import search
    monkeypatch.setattr("refmatrix.discovery.discover_roots", lambda: [silent.root])
    out = search.federated_query("mentions:x")
    assert out["projects"] == [] and out["skipped"] and "busy" in out["skipped"][0]["reason"]
    out2 = search.federated_concept("x")
    assert out2["projects"] == [] and out2["skipped"] and "busy" in out2["skipped"][0]["reason"]
    out3 = verbs.search(silent.root, "mentions:x")
    assert out3["skipped"]


# ---- #s-3 / #s-4 the last bare pings classify; a socket timeout is busy --------

def test_memory_partition_raises_busy_and_defaults_on_absent(silent, tmp_path):
    with pytest.raises(verbs.VerbBusyError):
        verbs.memory_partition(silent.root)
    absent = tmp_path / "proj" / ".refmatrix"; absent.mkdir(parents=True)
    assert verbs.memory_partition(absent) == "proj"


def test_attach_context_names_busy(silent):
    w: list = []
    rows = verbs.attach_context(silent.root, [{"name": "x"}], 1, None, w)
    assert rows[0].get("context") is None
    assert w and "busy" in w[0]


def test_socket_timeout_on_an_op_is_busy(pingonly):
    with pytest.raises(verbs.VerbBusyError, match="ingest_gmd_status"):
        verbs.ingest_status(pingonly.root)


def test_promote_action_goes_through_the_typed_wrappers(tmp_path, monkeypatch):
    monkeypatch.setattr("refmatrix.discovery.daemon_status", lambda r, **kw: {"up": True, "busy": False, "pid": 1})
    monkeypatch.setattr("refmatrix.discovery.store_name", lambda r: "p")
    monkeypatch.setattr(daemon_mod, "ping", lambda r, **kw: True)
    monkeypatch.setattr(daemon_mod, "call", lambda r, op, args=None, **kw:
                        {"ok": True, "result": {"rows": []}} if op == "partition_list"
                        else {"ok": False, "error": "no such memory"})
    with pytest.raises(verbs.VerbError, match="no such memory"):
        verbs.memory(tmp_path, action="promote", name="m")
    monkeypatch.setattr(daemon_mod, "call", lambda r, op, args=None, **kw:
                        {"ok": True, "result": {"rows": []}} if op == "partition_list"
                        else {"ok": True, "result": {"memory": {"name": "m", "content": "c", "tags": []}}})
    def boom(*a, **kw):
        raise OSError("hub down")
    monkeypatch.setattr(hub_mod, "global_call", boom)
    with pytest.raises(verbs.VerbError, match="hub down"):
        verbs.memory(tmp_path, action="promote", name="m")


# ---- #m-5 reads fall through to the lock-free reader on busy, loudly ----------

def test_memory_get_reads_the_replica_when_the_daemon_is_busy(silent, monkeypatch):
    s = Store(silent.root); s.init()
    s.add_memory(name="r1", content="from the reader", mtype="note"); s.close()
    monkeypatch.setattr(cli_mod, "_root", lambda: silent.root)
    r = CliRunner().invoke(cli_main, ["memory", "get", "r1"])
    assert r.exit_code == 0, r.output + (r.stderr or "")
    assert "from the reader" in r.output
    assert "busy" in (r.stderr or "") and "replica" in (r.stderr or "")


def test_memory_recall_recent_reads_the_replica_when_the_daemon_is_busy(silent, monkeypatch):
    import json
    s = Store(silent.root); s.init()
    s.add_memory(name="r2", content="recent", mtype="note"); s.close()
    monkeypatch.setattr(cli_mod, "_root", lambda: silent.root)
    r = CliRunner().invoke(cli_main, ["memory", "recall", "--recent", "--json", "--timeout", "1"])
    assert r.exit_code == 0, r.output + (r.stderr or "")
    assert [m["name"] for m in json.loads(r.stdout)] == ["r2"]
    assert "busy" in (r.stderr or "") and "replica" in (r.stderr or "")


# ---- the hub's queue row says busy, not down -------------------------------------

def test_gather_queues_marks_a_busy_daemon_busy(silent, monkeypatch):
    monkeypatch.setattr("refmatrix.discovery.discover_roots", lambda: [silent.root])
    hub = hub_mod.Hub.__new__(hub_mod.Hub)
    rows = hub_mod.Hub._gather_queues(hub)
    assert rows[0]["daemon_up"] is False and rows[0]["daemon_busy"] is True
    assert rows[0].get("identity") == "unknown"
    monkeypatch.setattr(cli_mod, "_root", lambda: silent.root)
    monkeypatch.setattr(verbs, "queues", lambda root: {"queues": rows})
    r = CliRunner().invoke(cli_main, ["hub", "queues"])
    assert "busy" in r.output
