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
    # the flat index is NOT a memory (ch-bsd plan-5 #b-2): skipped and counted
    time.sleep(1.0)
    r = dm.call(root, "memory_get", {"name": "MEMORY", "partition": verbs.memory_partition(root)}, timeout=10)
    assert (r.get("result") or {}).get("memory") is None
    assert out["skipped_index"] == ["MEMORY.md"] and "skipped_index: 1" in out["report"]
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


def test_finalize_skips_the_bridge_on_sync_false_and_dry_run(live):
    """sync=False and a dry run never touch the store — proven on the real
    store (no row appears), not on a recorded call list."""
    from refmatrix import handoff
    base, root = live
    memdir = base / "memory"; memdir.mkdir()
    (memdir / "savestate_skip.md").write_text(GMD.format(id="savestate_skip", body="never"))
    res = {"target": str(memdir / "savestate_skip.md"), "memdir": str(memdir),
           "dry_run": False, "promoted": None}
    fin = handoff.finalize_save_state(None, root, res, repo=base / "proj", lint=False, sync=False)
    assert fin["sync"] is None
    fin = handoff.finalize_save_state(None, root, dict(res, dry_run=True), repo=base / "proj", lint=False)
    assert fin["sync"] is None
    time.sleep(1.0)
    r = dm.call(root, "memory_get", {"name": "savestate_skip",
                                     "partition": verbs.memory_partition(root)}, timeout=10)
    assert (r.get("result") or {}).get("memory") is None


# ---- r1 remedy: busy is not absent on the bridge; coverage needs as_memory --------

from tests.test_plan2_remedy import _SilentDaemon  # noqa: E402


def test_bridge_never_opens_the_slot_under_a_busy_daemon(monkeypatch):
    """ch-bsd plan-5 #b-1: four live bridge runs wrote catalog.B directly
    while pid 30867 was alive-but-silent; the daemon then fast-exited on a
    corrupted ART index. Busy → a named error, no catalog file, ever."""
    d = _SilentDaemon(seeded=True)
    try:
        slots = lambda: {p.name: (p.stat().st_mtime_ns, p.stat().st_size)  # noqa: E731
                         for p in d.root.glob("catalog*.duckdb")}
        before = slots()
        assert before, "seeded fixture has a real catalog (bsd-plan5-r2 #s-4-r2)"
        monkeypatch.setattr(cli_mod, "_root", lambda: d.root)
        memdir = d.base / "mem"; memdir.mkdir()
        (memdir / "m.md").write_text(GMD.format(id="m", body="x"))
        out = cli_mod._sync_memory_dir(memdir)
        assert out["error"] and "busy" in out["error"] and f"pid={d.pid}" in out["error"], out
        assert slots() == before, "the bridge wrote the writer slot"
        # the write control point itself refuses
        import click
        with pytest.raises(click.ClickException, match="busy"):
            cli_mod._store(write=True)
        assert slots() == before
    finally:
        d.close()


def test_bridge_does_not_take_a_non_memory_job_as_its_report(live, monkeypatch):
    """ch-bsd plan-5 #s-3: a plain doc ingest over the memory dir is not the
    bridge; the bridge runs its own once the slot is free."""
    base, root = live
    memdir = _big_dir(base, "memory", 350)
    resp = dm.call(root, "ingest_gmd_start", {"targets": [str(memdir)], "as_memory": False,
                                              "partition": "proj"}, timeout=30)
    assert resp.get("ok"), resp
    monkeypatch.setenv("RMX_BRIDGE_WAIT_S", "120")
    out = cli_mod._sync_memory_dir(memdir)
    assert out["error"] is None, out
    assert out["waited"] is True and out["waited_job"] == resp["result"]["job_id"]
    assert _get(root, "memory_doc0001"), "no memory row landed — the bridge took a doc ingest's report"


def test_strict_ingest_counts_non_gmd_files():
    """ch-bsd plan-5 #s-5: the counter must be able to move — in strict
    (non-memory) mode a plain .md is skipped_non_gmd, and the daemon-side
    result carries the counters structurally."""
    from refmatrix.ingest_gmd import ingest_gmd_paths
    base = Path(tempfile.mkdtemp(prefix="rmxsg-"))
    try:
        root = base / "proj" / ".refmatrix"; root.parent.mkdir()
        s = Store(root); s.init()
        (base / "proj" / "plain.md").write_text("# plain\n\nno frontmatter\n")
        (base / "proj" / "doc.md").write_text(GMD.format(id="doc", body="x"))
        stats = ingest_gmd_paths(s, [base / "proj" / "plain.md", base / "proj" / "doc.md"])
        assert stats.skipped_non_gmd == 1 and stats.docs == 1
        assert stats.as_dict()["skipped_non_gmd"] == 1
        s.close()
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_save_state_reports_a_waited_bridge(live, monkeypatch):
    """ch-bsd plan-5 #s-8: `waited` / `waited_job` reach the CLI."""
    base, root = live
    memdir = _big_dir(base, "memory", 350)
    (memdir / "MEMORY.md").write_text("")
    part = verbs.memory_partition(root)
    resp = dm.call(root, "ingest_gmd_start", {"targets": [str(memdir)], "as_memory": True,
                                              "memory_mtype": "curated", "partition": part}, timeout=30)
    assert resp.get("ok"), resp
    monkeypatch.setenv("RMX_BRIDGE_WAIT_S", "120")
    monkeypatch.setenv("RMX_SESSION", "s-ss")
    from refmatrix import stm as stm_mod
    stm_mod.Stm(root, "s-ss").record("input", "hi")
    r = CliRunner().invoke(cli_mod.main, ["save-state", "--memory-dir", str(memdir), "--no-lint", "--no-promote"])
    assert r.exit_code == 0, r.output + (r.stderr or "")
    assert "waited for ingest job " + resp["result"]["job_id"] in r.output



# ---- task 26.1 AC-2: the bridge's memory walk IS `memory_layout.iter_memory_files` ---------
#
# ch-bsd plan-26 r1 #s3: `collect_gmd_files` excluded only MEMORY.md, so a
# `.organise-rollback-1/x.md` inside a memdir was ingested as a memory. ADR-0005 #one-walk: a
# dot-dir inside a memdir is never a memory store. The spec runs the test three ways (in-process,
# the daemon sync op, the detached op behind the SessionStart hook) and the prestage twins
# (daemon op `prestage_hashes`, the no-daemon branch in `cli.ingest_gmd`) must walk the same set,
# or prestage stamps hashes on files the bridge then skips (r2 m1, r3 m7).
#
# Real CLI (`rmx ingest-gmd --as-memory`) through CliRunner, a throwaway store under a short
# `mkdtemp()` root, a real spawned daemon for the daemon legs. No patch: the store root reaches
# `cli._root()` through `REFMATRIX_ROOT`, the env input the 23.0 sandbox already uses.

import re  # noqa: E402


def _ac2_memdir(base: Path) -> Path:
    memdir = base / "memory"
    memdir.mkdir()
    (memdir / "keep_top.md").write_text(GMD.format(id="keep_top", body="a top-level memory"))
    (memdir / "feedback").mkdir()
    (memdir / "feedback" / "keep_nested.md").write_text(
        GMD.format(id="keep_nested", body="a memory in a type folder"))
    (memdir / ".organise-rollback-1").mkdir()
    (memdir / ".organise-rollback-1" / "x.md").write_text(
        GMD.format(id="x", body="an organise aside, NOT a memory"))
    (memdir / ".hidden").mkdir()
    (memdir / ".hidden" / "y.md").write_text(GMD.format(id="y", body="a dot-dir, NOT a memory"))
    return memdir


def _ac2_store(spawn: bool):
    base = Path(tempfile.mkdtemp(prefix="rmx261-"))
    root = base / "proj" / ".refmatrix"
    root.parent.mkdir()
    Store(root).init()
    if spawn:
        pid = dm.spawn_daemon_subprocess(root, watch_root=[])
        assert pid and dm.ping(root)
    return base, root


@pytest.fixture
def ac2_inproc(monkeypatch):
    base, root = _ac2_store(spawn=False)
    monkeypatch.setenv("REFMATRIX_ROOT", str(root))
    monkeypatch.delenv("RMX_PARTITION", raising=False)
    yield base, root
    shutil.rmtree(base, ignore_errors=True)


@pytest.fixture
def ac2_daemon(monkeypatch):
    base, root = _ac2_store(spawn=True)
    monkeypatch.setenv("REFMATRIX_ROOT", str(root))
    monkeypatch.delenv("RMX_PARTITION", raising=False)
    yield base, root
    dm.stop_daemon(root)
    shutil.rmtree(base, ignore_errors=True)


def _rows(root: Path, names) -> dict:
    """Which memory rows exist, read off the (stopped-daemon) throwaway store."""
    s = Store(root)
    try:
        return {n: s.find_memory_any_partition(n) is not None for n in names}
    finally:
        s.close()


def _ac2_assert_rows(root: Path) -> None:
    got = _rows(root, ["keep_top", "keep_nested", "x", "y"])
    assert got["keep_top"] and got["keep_nested"], f"the ingest did not run: {got}"
    assert not got["x"], "a `.organise-rollback-1/x.md` aside was ingested as a memory"
    assert not got["y"], "a `.hidden/y.md` dot-dir file was ingested as a memory"


def _invoke(args):
    r = CliRunner().invoke(cli_mod.main, args)
    assert r.exit_code == 0, f"{r.output}\n{r.exception!r}"
    return r.output


def test_ac2_in_process_bridge_skips_dot_dirs(ac2_inproc):
    base, root = ac2_inproc
    memdir = _ac2_memdir(base)
    assert not dm.ping(root, retries=0), "the in-process leg must run with NO daemon"
    _invoke(["ingest-gmd", "--as-memory", str(memdir)])
    assert not dm.ping(root, retries=0)
    _ac2_assert_rows(root)


def _jobs(root: Path) -> list:
    resp = dm.call(root, "ingest_gmd_status", {}, timeout=10)
    assert resp.get("ok"), resp
    return resp["result"]["jobs"]


def test_ac2_daemon_sync_op_skips_dot_dirs(ac2_daemon):
    base, root = ac2_daemon
    memdir = _ac2_memdir(base)
    _invoke(["ingest-gmd", "--as-memory", str(memdir)])
    jobs = _jobs(root)
    assert len(jobs) == 1 and jobs[0]["status"] == "done", jobs   # it ran THROUGH the daemon
    dm.stop_daemon(root)
    _ac2_assert_rows(root)
    assert jobs[0]["files_total"] == 2, f"the sync op walked {jobs[0]['files_total']} files, not 2"


def test_ac2_detached_op_skips_dot_dirs(ac2_daemon):
    """The SessionStart bridge hook's path: `ingest-gmd --as-memory --detach`."""
    base, root = ac2_daemon
    memdir = _ac2_memdir(base)
    out = _invoke(["ingest-gmd", "--as-memory", "--detach", str(memdir)])
    m = re.search(r"ingest job (\S+) started \((\d+) files\)", out)
    assert m, out
    job_id, files_total = m.group(1), int(m.group(2))
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        st = dm.call(root, "ingest_gmd_status", {"job_id": job_id}, timeout=10)["result"]["job"]
        if st["status"] != "running":
            break
        time.sleep(0.25)
    assert st["status"] == "done", st
    dm.stop_daemon(root)
    _ac2_assert_rows(root)
    assert files_total == 2, f"the detached op walked {files_total} files, not 2"


def _considered(out: str) -> int:
    m = re.search(r"prestaged: considered=(\d+)", out)
    assert m, out
    return int(m.group(1))


def test_ac2_prestage_without_a_daemon_walks_the_same_set(ac2_inproc):
    """`cli.py`'s no-daemon prestage twin of the daemon op (r3 m7)."""
    base, root = ac2_inproc
    memdir = _ac2_memdir(base)
    assert not dm.ping(root, retries=0)
    out = _invoke(["ingest-gmd", "--as-memory", "--prestage", str(memdir)])
    assert _considered(out) == 2, out


def test_ac2_prestage_through_the_daemon_walks_the_same_set(ac2_daemon):
    """The daemon's `prestage_hashes` op (r2 m1)."""
    base, root = ac2_daemon
    memdir = _ac2_memdir(base)
    out = _invoke(["ingest-gmd", "--as-memory", "--prestage", str(memdir)])
    assert _considered(out) == 2, out


def test_ac2_doc_ingest_keeps_its_own_walk():
    """Without `as_memory` the walk is unchanged: a doc tree's dot-dirs are not the memory
    rule's business (spec AC-2: "Doc ingest keeps its own walk")."""
    from refmatrix.ingest_gmd import collect_gmd_files
    base = Path(tempfile.mkdtemp(prefix="rmx261-"))
    try:
        memdir = _ac2_memdir(base)
        got = {p.name for p in collect_gmd_files([memdir])}
        assert got == {"keep_top.md", "keep_nested.md", "x.md", "y.md"}
    finally:
        shutil.rmtree(base, ignore_errors=True)


# ---- task 26.1 remedy, ch-bsd 26.1 #s-3: every skip is counted, named, and reaches the caller -
#
# The walk dropped a symlinked sub-folder, a dangling `.md` symlink and a `.gmd` file WITHOUT
# counting them (HEAD's bridge ingested `.gmd`), and on the daemon ops the "skipped N" line went
# to the daemon's stderr log -- never into the result the hook or CLI receives. CLAUDE.md
# #no-silent-failures: a skipped file is counted and printed, by the CALLER.

S3_SKIPPED = (".organise-rollback-1/x.md", ".hidden/y.md", "linked", "dangling.md", "notes.gmd")


def _s3_memdir(base: Path) -> Path:
    memdir = _ac2_memdir(base)              # keep_top + feedback/keep_nested; x, y in dot-dirs
    outside = base / "elsewhere"
    outside.mkdir()
    (outside / "far.md").write_text(GMD.format(id="far", body="outside the memdir"))
    (memdir / "linked").symlink_to(outside, target_is_directory=True)
    (memdir / "dangling.md").symlink_to(base / "no-such-file.md")
    (memdir / "notes.gmd").write_text(GMD.format(id="notes", body="a .gmd file in a memdir"))
    return memdir


def _flat(text: str) -> str:
    return " ".join(str(text).split())


def _assert_names_every_skip(text: str, where: str) -> None:
    flat = _flat(text)
    assert re.search(r"skipped 5\b", flat), f"{where}: no 'skipped 5' count: {flat}"
    missing = [n for n in S3_SKIPPED if n not in flat]
    assert not missing, f"{where}: skipped paths not named: {missing}: {flat}"


def test_s3_in_process_bridge_counts_and_names_every_skip(ac2_inproc):
    base, root = ac2_inproc
    memdir = _s3_memdir(base)
    assert not dm.ping(root, retries=0)
    out = _invoke(["ingest-gmd", "--as-memory", str(memdir)])
    _assert_names_every_skip(out, "in-process CLI output")
    got = _rows(root, ["keep_top", "keep_nested", "far", "notes"])
    assert got["keep_top"] and got["keep_nested"], got
    assert not got["far"], "the walk followed a symlinked sub-folder out of the memdir"


def test_s3_daemon_sync_op_returns_the_skip_count_to_the_caller(ac2_daemon):
    """The `ingest_gmd` op's RESULT carries `skipped` (int) and `skipped_paths` (names), and the
    CLI that called it prints them -- not only the daemon's stderr log."""
    base, root = ac2_daemon
    memdir = _s3_memdir(base)
    resp = dm.call(root, "ingest_gmd", {"targets": [str(memdir)], "as_memory": True},
                   timeout=300)
    assert resp.get("ok"), resp
    res = resp["result"]
    assert res.get("skipped") == 5, f"the op result carries no skipped count of 5: {res}"
    named = " ".join(str(p) for p in (res.get("skipped_paths") or []))
    missing = [n for n in S3_SKIPPED if n not in named]
    assert not missing, f"skipped_paths does not name {missing}: {res.get('skipped_paths')}"
    out = _invoke(["ingest-gmd", "--as-memory", str(memdir)])
    _assert_names_every_skip(out, "daemon-backed CLI output")
