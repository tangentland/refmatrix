"""plan-5 — the memory bridge (`ingest-gmd --as-memory` over the curated
memory dir) on a REAL tmp store behind a REAL spawned daemon, no monkeypatch
of the bridge (ch-bsd e2e #bs-1/#sk-1/#sk-2: the 0.66.1 bridge skipped
non-GMD files with no counter, `sync-disk` was a second bridge, overlapping
runs printed FAILED, and the tests patched the bridge itself)."""
from __future__ import annotations

import os
import shutil
import tempfile
import time
from pathlib import Path

import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod
from refmatrix import daemon as dm
from refmatrix import verbs
from refmatrix.store import Store


GMD = '---\ngmd: "0.1"\nid: {id}\ntitle: "{id}"\ntags: [project]\nmetadata:\n  type: feedback\n---\n# {id} {{#root}}\n\n{body}\n'


def _spawn():
    base = Path(tempfile.mkdtemp(prefix="rmxb-"))
    root = base / "proj" / ".refmatrix"; root.parent.mkdir()
    Store(root).init()
    pid = dm.spawn_daemon_subprocess(root, watch_root=[])
    assert pid and dm.ping(root)
    return base, root


@pytest.fixture
def live(monkeypatch):
    base, root = _spawn()
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    monkeypatch.delenv("RMX_PARTITION", raising=False)
    yield base, root
    dm.stop_daemon(root)
    shutil.rmtree(base, ignore_errors=True)


def _get(root, name):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        r = dm.call(root, "memory_get", {"name": name, "partition": verbs.memory_partition(root)},
                    timeout=10)
        m = (r.get("result") or {}).get("memory") if r.get("ok") else None
        if m:
            return m
        time.sleep(0.2)
    return None


# ---- 5.1 lenient bridge + counters -------------------------------------------

def test_bridge_ingests_gmd_and_plain_files(live):
    base, root = live
    memdir = base / "memory"; memdir.mkdir()
    (memdir / "authored_note.md").write_text(GMD.format(id="authored_note", body="an authored memory"))
    (memdir / "plain_note.md").write_text("# Plain note\n\nno frontmatter at all, still a memory\n")
    (memdir / "MEMORY.md").write_text("- [x](authored_note.md) — index\n")
    out = cli_mod._sync_memory_dir(memdir)
    assert out["error"] is None, out
    assert _get(root, "authored_note")["mtype"] == "feedback"
    plain = _get(root, "plain_note")
    assert plain and "still a memory" in plain["content"]
    assert plain["mtype"] == "curated"
    assert "skipped_non_gmd: 0" in out["report"]
    assert out["skipped_non_gmd"] == 0 and out["skipped_unparseable"] == []


def test_bridge_counts_and_names_an_unparseable_file(live):
    base, root = live
    memdir = base / "memory"; memdir.mkdir()
    (memdir / "good.md").write_text(GMD.format(id="good", body="ok"))
    (memdir / "binary.md").write_bytes(b"\xff\xfe\x00garbage\x00\xff")
    out = cli_mod._sync_memory_dir(memdir)
    assert out["error"] is None, out
    assert _get(root, "good")
    assert "skipped_unparseable: 1" in out["report"] and "binary.md" in out["report"]
    assert len(out["skipped_unparseable"]) == 1 and out["skipped_unparseable"][0]["path"].endswith("binary.md")


def test_sync_disk_is_the_bridge(live):
    base, root = live
    memdir = base / "memory"; memdir.mkdir()
    (memdir / "via_alias.md").write_text("# via alias\n\nbody\n")
    r = CliRunner().invoke(cli_mod.main, ["memory", "sync-disk", str(memdir)])
    assert r.exit_code == 0, r.output
    assert "deprecated" in (r.output + (r.stderr or "")).lower()
    assert "ingest-gmd --as-memory" in (r.output + (r.stderr or ""))
    assert _get(root, "via_alias")


# ---- 5.2 overlap: wait for the active job --------------------------------------

def _big_dir(base, name, n):
    d = base / name; d.mkdir()
    for i in range(n):
        (d / f"doc{i:04d}.md").write_text(GMD.format(id=f"{name}_doc{i:04d}", body="x " * 400))
    return d


def test_bridge_waits_for_an_active_job_on_the_same_target(live, monkeypatch):
    base, root = live
    memdir = _big_dir(base, "memory", 350)
    part = verbs.memory_partition(root)
    resp = dm.call(root, "ingest_gmd_start", {"targets": [str(memdir)], "as_memory": True,
                                              "memory_mtype": "curated", "partition": part}, timeout=30)
    assert resp.get("ok"), resp
    jid = resp["result"]["job_id"]
    monkeypatch.setenv("RMX_BRIDGE_WAIT_S", "120")
    out = cli_mod._sync_memory_dir(memdir)
    assert out["error"] is None, out
    assert out["waited"] is True and out["waited_job"] == jid
    assert "ingested" in (out["report"] or "")
    st = dm.call(root, "ingest_gmd_status", {"job_id": jid}, timeout=10)["result"]["job"]
    assert st["status"] == "done"


def test_bridge_runs_its_own_ingest_after_a_job_on_another_target(live, monkeypatch):
    base, root = live
    other = _big_dir(base, "other", 350)
    memdir = base / "memory"; memdir.mkdir()
    (memdir / "mine.md").write_text(GMD.format(id="mine", body="mine"))
    part = verbs.memory_partition(root)
    resp = dm.call(root, "ingest_gmd_start", {"targets": [str(other)], "as_memory": True,
                                              "memory_mtype": "curated", "partition": part}, timeout=30)
    assert resp.get("ok"), resp
    monkeypatch.setenv("RMX_BRIDGE_WAIT_S", "120")
    out = cli_mod._sync_memory_dir(memdir)
    assert out["error"] is None, out
    assert out["waited"] is True and out["waited_job"] == resp["result"]["job_id"]
    assert _get(root, "mine")


def test_bridge_reports_a_wait_that_ran_out(live, monkeypatch):
    base, root = live
    memdir = _big_dir(base, "memory", 350)
    part = verbs.memory_partition(root)
    resp = dm.call(root, "ingest_gmd_start", {"targets": [str(memdir)], "as_memory": True,
                                              "memory_mtype": "curated", "partition": part}, timeout=30)
    assert resp.get("ok"), resp
    monkeypatch.setenv("RMX_BRIDGE_WAIT_S", "0.2")
    out = cli_mod._sync_memory_dir(memdir)
    assert out["waited"] is True
    assert out["error"] and "still running" in out["error"] and resp["result"]["job_id"] in out["error"]


# ---- 5.3 finalize on a real store --------------------------------------------

def test_finalize_save_state_bridges_the_handoff_dir_for_real(live):
    from refmatrix import handoff
    base, root = live
    memdir = base / "memory"; memdir.mkdir()
    (memdir / "MEMORY.md").write_text("")
    (memdir / "savestate_abc.md").write_text(GMD.format(id="savestate_abc", body="handoff body"))
    res = {"target": str(memdir / "savestate_abc.md"), "memdir": str(memdir),
           "dry_run": False, "promoted": None}
    fin = handoff.finalize_save_state(None, root, res, repo=base / "proj", lint=False)
    assert fin["sync"]["error"] is None, fin["sync"]
    assert "ingested" in fin["sync"]["report"]
    assert _get(root, "savestate_abc")["content"].strip().endswith("handoff body")
