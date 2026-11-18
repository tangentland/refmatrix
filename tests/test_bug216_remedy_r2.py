"""bug-216 remedy r2 RED — bsd-216 r2 at 25ceacd (DIRTY 2B/0S/2M, NO-GO), ruling L94.

Report: workflow/bullshit/2026-11-14-0041-bug216-r2-25ceacd.md (a32874a in the bug-216 clone).
Ruling: workflow/plan-review-2026-11-13.md, row L94 (dev tree).

  B1-r2  `ingest_ignore_root` judges a target OUTSIDE the store's project on its absolute path,
         as 758bca1 did — never by the target itself, never by a FOREIGN store's spec:
         (i)  r1's own repro, rebuilt where r1 had it (bsd r2: "A REMEDY RED THAT REBUILDS THE
              REPRO IN A MORE CONVENIENT PLACE TESTS A DIFFERENT BUG" — aac951c put the memdir
              under `<proj>/.claude/`): a memdir outside the project, with NO `.refmatrix/`
              above it, stores 0 kind=doc rows;
         (ii) an out-of-project tree (the `claude_tools/gmd` shape) under a dir that a PARENT
              store's spec lists ingests the file count 758bca1's code ingests on the same tree
              (measured here, by running 758bca1's `ingest_path` on a twin fixture).
  B2     (bug-227, completed on this branch) the merge_slots fresh-id move — two DIFFERENT
         entities under one id, B's moved to a fresh id — must carry every column that holds B's
         id: (a) step 7b's newer-wins memory_content UPDATE keys on the raw id and gives A's
         memory B's body; (b) B-only fragment rows keep B's ids, so a moved entity's bit points
         at A's entity (`repair_fragments(id_map=...)` exists for this); (c) the moved ids are
         reported apart from `b_loser_count`, so they can be re-embedded; (d) `MergeRefused`
         past REMAP_HEADROOM (pin: green at 25ceacd, mutation-proven); (e) B's NAME-loser id held
         by a DIFFERENT A entity: the entity UPDATE overwrites A's row and dies on the unique
         (partition, kind, name) key — same remap code (`_merge_into` step 5), RED.
  M1-r2  a built-in-included profile whose frontmatter is removed (file kept) is purged on the
         next watcher event — `watch.is_relevant` is True for every BUILTIN_INCLUDES path, so
         `_sync_one` decides. No path-specific sync.
  M2-r2  (tests/test_bug216_remedy_r1.py) `audit_via_writer` is called with keywords, so its
         keyword-only `*,` can be restored.

Contracts this file assumes where L94 names no field: the moved ids are reported as
`fresh_moved` = [[old_id, new_id], ...], at the top level of merge_slots' result or under its
`remap` dict, and `remap.b_loser_count` counts name-losers only.

Throwaway stores under short `/tmp` mkdtemp roots only; no live `.refmatrix/` is touched.
"""
from __future__ import annotations

import rmx_sandbox  # task-29.4 #r5: test roots live under the sandbox root (short_root)
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import duckdb
import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod
from refmatrix.store import Store
from tests.test_bug216_remedy_r1 import _gmd, _new_store, _old_src, _open, _write

FEEDBACK_FM = "metadata:\n  type: feedback\n"


@pytest.fixture
def base():
    b = Path(rmx_sandbox.short_root("b216q")).resolve()
    # The test's own premise: no `.refmatrix/` anywhere above the mkdtemp root.
    assert not any((p / ".refmatrix").exists() for p in b.parents), b
    yield b
    shutil.rmtree(b)


def _point_cli_at(monkeypatch, root: Path) -> None:
    monkeypatch.setenv("REFMATRIX_ROOT", str(root))
    monkeypatch.delenv("RMX_PARTITION", raising=False)
    monkeypatch.setattr(cli_mod, "_partition_override", None, raising=False)


def _rows_from(root: Path, under: Path) -> "list[tuple[str, str]]":
    s = _open(root)
    try:
        return sorted((str(k), str(n)) for k, n, p in s._connect().execute(
            "SELECT kind, name, path FROM entities WHERE path IS NOT NULL").fetchall()
            if str(Path(p).resolve()).startswith(str(under) + "/"))
    finally:
        s.close()


def _files_from(root: Path, under: Path) -> "set[str]":
    """The files under `under` that own at least one entity (the 'file count' L94 compares)."""
    s = _open(root)
    try:
        return {Path(p).resolve().relative_to(under).as_posix() for (p,) in s._connect().execute(
            "SELECT DISTINCT path FROM entities WHERE path IS NOT NULL").fetchall()
            if str(Path(p).resolve()).startswith(str(under) + "/")}
    finally:
        s.close()


# ================================================================ B1-r2 (i)


@pytest.fixture
def outside_memdir(base, monkeypatch):
    """r1's repro shape: the store's project at `<base>/github/proj`, the memdir at
    `<base>/home/.claude/projects/x/memory` — OUTSIDE the project, as Claude Code puts it, and
    with no `.refmatrix/` above it (the global store at `~` is what hid this on the workstation)."""
    proj = base / "github" / "proj"
    _write(proj, "docs/d.md", _gmd("d"))
    mem = base / "home" / ".claude" / "projects" / "x" / "memory"
    _write(mem, "feedback_a.md", _gmd("feedback_a", extra_fm=FEEDBACK_FM))
    _write(mem, "feedback/feedback_b.md", _gmd("feedback_b", extra_fm=FEEDBACK_FM))
    root = proj / ".refmatrix"
    _new_store(root)
    _point_cli_at(monkeypatch, root)
    assert not any((p / ".refmatrix").exists() for p in mem.parents if p != proj)
    return {"proj": proj, "root": root, "mem": mem}


def test_b1r2_ingest_path_of_an_outside_memdir_stores_no_doc_rows(outside_memdir):
    """`ingest_path(store, <memdir>)` — the op `rmx ingest <memdir>` and MCP `rmx_ingest` run.
    Judged on its absolute path, every file carries `.claude`."""
    from refmatrix.ingest import ingest_path
    o = outside_memdir
    s = _open(o["root"])
    try:
        ingest_path(s, o["mem"])
    finally:
        s.close()
    docs = [r for r in _rows_from(o["root"], o["mem"]) if r[0] == "doc"]
    assert docs == [], f"an outside memdir landed kind=doc rows: {docs}"


def test_b1r2_cli_ingest_of_an_outside_memdir_stores_no_doc_rows(outside_memdir):
    o = outside_memdir
    r = CliRunner().invoke(cli_mod.main, ["ingest", str(o["mem"])], catch_exceptions=False)
    assert r.exit_code == 0, r.output
    docs = [x for x in _rows_from(o["root"], o["mem"]) if x[0] == "doc"]
    assert docs == [], f"`rmx ingest <outside memdir>` landed kind=doc rows: {docs}"


# ================================================================ B1-r2 (ii)

_OLD_INGEST = """
import sys
sys.path.insert(0, sys.argv[1])
import refmatrix
assert refmatrix.__file__.startswith(sys.argv[1]), refmatrix.__file__
from pathlib import Path
from refmatrix.store import Store
from refmatrix.ingest import ingest_path
s = Store(Path(sys.argv[2]))
s.init()
try:
    ingest_path(s, Path(sys.argv[3]))
finally:
    s.close()
"""


def _foreign_layout(home: Path) -> dict:
    """`<home>/.refmatrix/.refmatrix_ignore` lists `claude_tools` (the global store's spec on
    the workstation lists `Library`, `refmatrix`, `claude_tools`); this store's project is
    `<home>/github/proj`; the target is `<home>/claude_tools/gmd`, outside the project."""
    (home / ".refmatrix").mkdir(parents=True)
    (home / ".refmatrix" / ".refmatrix_ignore").write_text("Library\nrefmatrix\nclaude_tools\n")
    proj = home / "github" / "proj"
    _write(proj, "docs/d.md", _gmd("d"))
    tree = home / "claude_tools" / "gmd"
    _write(tree, "SPEC.md", _gmd("gmd-spec", "The GMD spec.\n"))
    root = proj / ".refmatrix"
    _new_store(root)
    return {"proj": proj, "root": root, "tree": tree}


def test_b1r2_an_outside_tree_is_not_judged_by_a_foreign_stores_spec(base):
    new = _foreign_layout(base / "new" / "home")
    old = _foreign_layout(base / "old" / "home")
    p = subprocess.run([sys.executable, "-c", _OLD_INGEST, str(_old_src(base)),
                        str(old["root"]), str(old["tree"])],
                       capture_output=True, text=True, env=dict(os.environ), timeout=600)
    assert p.returncode == 0, p.stdout + p.stderr
    want = _files_from(old["root"], old["tree"])
    assert want, "precondition: 758bca1 ingests the outside tree's doc (bsd r2 measured 1 file)"
    from refmatrix.ingest import ingest_path
    s = _open(new["root"])
    try:
        ingest_path(s, new["tree"])
    finally:
        s.close()
    got = _files_from(new["root"], new["tree"])
    assert got == want, (
        f"the outside tree was judged by the PARENT store's spec (`claude_tools`): 758bca1 "
        f"ingested files {sorted(want)}, this code {sorted(got)}")


# ================================================================ B2 — merge_slots fresh-id move


def _slot_pair(base: Path) -> dict:
    """Two slots diverged from ONE copy (the bug-216 S2 shape): each later wrote a new MEMORY,
    so both allocated the same next id for different (kind, name). B wrote after A (newer)."""
    a_root = base / "A" / "proj" / ".refmatrix"
    b_root = base / "B" / "proj" / ".refmatrix"
    _new_store(a_root)
    s = _open(a_root)
    try:
        topic = s.add_concept("topic")
    finally:
        s.close()
    b_root.mkdir(parents=True)
    shutil.copy2(a_root / "catalog.duckdb", b_root / "catalog.duckdb")
    s = _open(a_root)
    try:
        a_id = s.add_memory("mem-a", "BODY OF A", mtype="feedback")
    finally:
        s.close()
    s = _open(b_root)
    try:
        b_id = s.add_memory("mem-b", "BODY OF B", mtype="feedback")
        # a linkage only B has: its fragment row is copied from B as-is by step 12
        try:
            s.get_linkage_id("zz-b-only")
        except KeyError:
            s.add_linkage_type("zz-b-only", directed=True, description="bug-216 r2 fixture")
        s.link("zz-b-only", topic, b_id)
        s.flush_fragments()
    finally:
        s.close()
    assert a_id == b_id, f"precondition: the two new memories share an id ({a_id} vs {b_id})"
    return {"a": a_root / "catalog.duckdb", "b": b_root / "catalog.duckdb", "id": a_id,
            "topic": topic, "target": base / "T" / "catalog.duckdb"}


def _merge(pair: dict) -> dict:
    from refmatrix.replica_merge import merge_slots
    pair["target"].parent.mkdir(parents=True, exist_ok=True)
    return merge_slots(pair["a"], pair["b"], pair["target"])


def _bodies(target: Path) -> dict:
    con = duckdb.connect(str(target), read_only=True)
    try:
        return {str(n): (int(i), str(c)) for i, n, c in con.execute(
            "SELECT e.id, e.name, mc.content FROM entities e "
            "JOIN memory_content mc ON mc.entity_id = e.id WHERE e.kind = 'memory'").fetchall()}
    finally:
        con.close()


def test_b2a_a_fresh_id_move_keeps_each_memory_its_own_body(base):
    pair = _slot_pair(base)
    _merge(pair)
    got = _bodies(pair["target"])
    assert {n: c for n, (_i, c) in got.items()} == {"mem-a": "BODY OF A", "mem-b": "BODY OF B"}, (
        f"merged memory bodies: {got}")
    assert got["mem-a"][0] == pair["id"] and got["mem-b"][0] != pair["id"], got


def test_b2b_b_only_fragment_rows_follow_the_moved_id(base):
    """`zz-b-only` exists only in B, so step 12 copies B's fragment row verbatim. Its bit for
    mem-b must sit on mem-b's FRESH id; at the old id it names mem-a."""
    pair = _slot_pair(base)
    _merge(pair)
    new_id = _bodies(pair["target"])["mem-b"][0]
    probe = base / "P" / "proj" / ".refmatrix"
    probe.mkdir(parents=True)
    shutil.copy2(pair["target"], probe / "catalog.duckdb")
    s = Store(probe)
    s.init()
    try:
        with s.with_partition("proj"):
            bm = set(s.load_bitmap("zz-b-only", pair["topic"]))
    finally:
        s.close()
    assert new_id in bm and pair["id"] not in bm, (
        f"zz-b-only[topic] = {sorted(bm)}: mem-b moved {pair['id']} -> {new_id}; the bit must "
        f"follow it (a bit at {pair['id']} now names mem-a)")


def test_b2c_the_moved_ids_are_reported_apart_from_the_loser_count(base):
    pair = _slot_pair(base)
    res = _merge(pair)
    new_id = _bodies(pair["target"])["mem-b"][0]
    moved = res.get("fresh_moved", (res.get("remap") or {}).get("fresh_moved"))
    assert moved is not None and [list(m) for m in moved] == [[pair["id"], new_id]], (
        f"the merge must name the moved ids (to re-embed them): {res.get('remap')}")
    assert res["remap"]["b_loser_count"] == 0, (
        f"b_loser_count folds the moves into the name-losers: {res['remap']}")


def test_b2d_pin_merge_refused_past_the_headroom_leaves_no_target(base, monkeypatch):
    """PIN (green at 25ceacd — bsd r2: loud, but no test drove it). Two fresh-id collisions
    against a headroom of 1: `MergeRefused`, and no target file."""
    import refmatrix.replica_merge as rm
    a_root = base / "A" / "proj" / ".refmatrix"
    b_root = base / "B" / "proj" / ".refmatrix"
    _new_store(a_root)
    b_root.mkdir(parents=True)
    shutil.copy2(a_root / "catalog.duckdb", b_root / "catalog.duckdb")
    for root, side in ((a_root, "a"), (b_root, "b")):
        s = _open(root)
        try:
            for k in range(2):
                s.add_memory(f"mem-{side}{k}", f"body {side}{k}")
        finally:
            s.close()
    monkeypatch.setattr(rm, "REMAP_HEADROOM", 1)
    target = base / "T" / "catalog.duckdb"
    target.parent.mkdir()
    with pytest.raises(rm.MergeRefused):
        rm.merge_slots(a_root / "catalog.duckdb", b_root / "catalog.duckdb", target)
    assert not target.exists(), "a refused merge left a target file"


def test_b2d_pin_the_replica_merge_op_refuses_loudly_and_unlinks_the_target(base, monkeypatch):
    """PIN, the op half: `_op_replica_merge` (the `rmx replica merge` path) answers the refusal
    with ok:False naming it, leaves no merge target, and reopens the writer on slot A."""
    import refmatrix.replica_merge as rm
    from refmatrix import daemon as dm
    a_root = base / "A" / "proj" / ".refmatrix"
    b_root = base / "B" / "proj" / ".refmatrix"
    _new_store(a_root)
    b_root.mkdir(parents=True)
    shutil.copy2(a_root / "catalog.duckdb", b_root / "catalog.duckdb")
    for root, side in ((a_root, "a"), (b_root, "b")):
        s = _open(root)
        try:
            for k in range(2):
                s.add_memory(f"mem-{side}{k}", f"body {side}{k}")
        finally:
            s.close()
    droot = base / "D" / "proj" / ".refmatrix"
    droot.mkdir(parents=True)
    shutil.copy2(a_root / "catalog.duckdb", droot / "catalog.A.duckdb")
    shutil.copy2(b_root / "catalog.duckdb", droot / "catalog.B.duckdb")
    (droot / "active").write_text("A")
    monkeypatch.setattr(rm, "REMAP_HEADROOM", 1)
    d = dm.Daemon(droot, partition="proj")
    d._log = lambda msg: None
    d.store = Store(droot, partition="proj")
    d.store.init()
    d.store._connect()
    try:
        r = dm._op_replica_merge(d, {"dry_run": False})
        assert r.get("ok") is False and "MergeRefused" in str(r.get("error")), r
        assert not (droot / "catalog.merge.tmp.duckdb").exists(), "the refused target was left"
        assert d.store is not None and d.store.db_path.name == "catalog.A.duckdb", (
            "the writer was not reopened on slot A after the refusal")
    finally:
        if d.store is not None:
            d.store.close()


def _seed(path: Path, rows) -> None:
    con = duckdb.connect(str(path))
    try:
        for eid, name, upd in rows:
            con.execute(
                "INSERT INTO entities(id, partition_id, kind, name, created_at, updated_at) "
                "VALUES (?, (SELECT min(id) FROM partitions), 'doc', ?, 1.0, ?)",
                [eid, name, upd])
    finally:
        con.close()


def test_b2e_a_name_loser_id_held_by_a_different_a_entity_merges(base):
    """Shape 4 of bsd r2 #b2: `shared` is id 101 in A (newer, wins) and id 100 in B, so B's 100
    is a name-loser remapped to 101 — while A holds a DIFFERENT entity, `a-x`, at 100. The
    entity UPDATE (it excludes only the fresh moves) writes B's `shared` row over `a-x` and dies
    on the unique (partition, kind, name) key. Expected: both of A's entities, untouched."""
    from refmatrix.replica_merge import merge_slots
    a_root = base / "A" / "proj" / ".refmatrix"
    _new_store(a_root)
    a = a_root / "catalog.duckdb"
    b = base / "B" / "catalog.duckdb"
    b.parent.mkdir()
    shutil.copy2(a, b)
    _seed(a, [(100, "a-x", 1.0), (101, "shared", 9.0)])
    _seed(b, [(100, "shared", 5.0)])
    target = base / "T" / "catalog.duckdb"
    target.parent.mkdir()
    try:
        merge_slots(a, b, target)
    except Exception as e:  # noqa: BLE001 — the crash is the defect; said plainly
        pytest.fail(f"merge_slots died on a name-loser id held by another A entity: "
                    f"{type(e).__name__}: {str(e)[:300]}")
    con = duckdb.connect(str(target), read_only=True)
    try:
        got = sorted((int(i), str(n)) for i, n in con.execute(
            "SELECT id, name FROM entities WHERE name IN ('a-x', 'shared')").fetchall())
    finally:
        con.close()
    assert got == [(100, "a-x"), (101, "shared")], f"merged entities: {got}"


# ================================================================ M1-r2


def test_m1r2_removing_the_profiles_frontmatter_purges_it_on_the_next_watcher_event(base,
                                                                                   monkeypatch):
    """No ignore file: the GMD profile is in by R11. Its author removes the frontmatter and
    keeps the file. The watcher's modify event must reach `_sync_one` (is_relevant True for a
    BUILTIN_INCLUDES path, whatever its content), which purges the now-ignored path. At
    25ceacd the include needs `is_gmd_file`, the hidden-dir rule wins, and the event is dropped."""
    import watchdog.observers as wo
    from watchdog.events import FileModifiedEvent

    from refmatrix import daemon as daemon_mod
    from refmatrix.sync import sync_files
    from tests.test_bug216_remedy_r1 import PROFILE_MD
    from tests.test_bug216_rule_docs_e2e import _FakeObserver
    proj = base / "proj"
    root = proj / ".refmatrix"
    _new_store(root)
    prof = _write(proj, ".claude/PROJECT_PROFILE.md", PROFILE_MD)
    s = _open(root)
    try:
        sync_files(s, [str(prof)], project_root=proj)
        assert s.get_entity("doc", "project-profile") is not None, "precondition: profile in"
    finally:
        s.close()
    prof.write_text("# Project profile\n\nPlain markdown now, no frontmatter.\n")
    t = prof.stat().st_mtime + 10
    os.utime(prof, (t, t))
    _FakeObserver.instances = []
    monkeypatch.setattr(wo, "Observer", _FakeObserver)
    d = daemon_mod.Daemon(root, watch_root=proj, watch_debounce_ms=50)
    d.store = _open(root)
    try:
        d._start_watcher()
        (handler, _p), = _FakeObserver.instances[0].handlers
        handler.on_modified(FileModifiedEvent(str(prof)))
        d._watch_stop.set()
        d._watch_thread.join(timeout=30)
        assert not d._watch_thread.is_alive()
        assert d.sync_errors() == [], d.sync_errors()
    finally:
        d.store.close()
    s = _open(root)
    try:
        left = s.get_entity("doc", "project-profile")
    finally:
        s.close()
    assert left is None, "the profile lost its frontmatter but its doc survived the watcher"


def test_m1r2_watch_is_relevant_for_a_builtin_include_path_whatever_its_content(base):
    from refmatrix.watch import is_relevant
    proj = base / "proj"
    prof = _write(proj, ".claude/PROJECT_PROFILE.md", "# Plain\n\nNo frontmatter.\n")
    assert is_relevant(prof, proj) is True, (
        "a BUILTIN_INCLUDES path must reach `_sync_one`, which decides include vs purge")
