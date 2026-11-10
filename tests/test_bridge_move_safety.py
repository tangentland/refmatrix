"""Task 26.2: bridge move-safety (`workflow/plans/plan-26-memory-organisation-tasks/
task-26.2-bridge-move-safety.md`, ADR-0005).

WHY. The bridge's resume gate (`ingest_gmd.ingest_gmd_paths`, pass 1) skips a memory file when
the stored `gmd_content_hash` for its NAME matches. A file moved with its bytes unchanged is
therefore skipped: its memory row keeps `memory_content.metadata.source_path = <old path>` and
its `x#anchor` concepts keep `entities.path = <old path>` (ch-bsd plan-26 r1, reproduced on the
production CLI). Organising a memdir (26.5) moves every file, so before it ships the gate must
read the path it already records, refresh every row on a moved file's old path (the legacy
`memory_sync_disk` duplicates, r5 s1) in one logged write (r6-lite n1), count each refresh
term (r4 s3, r5 m3, r6-lite n2), measure the one-time refresh read-only (r3 s2, r4 s2), and
refuse two files claiming one id instead of letting the last one walked win.

Real CLI (`rmx ingest-gmd --as-memory`) through CliRunner, a throwaway store under a short
`mkdtemp()` root, a real spawned daemon for the daemon legs; nothing in the bridge is mocked.
Rows are read back with `Store` on the THROWAWAY store only, after its daemon is stopped.

Contracts this file pins (the spec names the terms; the shapes are chosen here, RED author):
- `IngestStats.as_dict()` and the bridge result (`cli._sync_memory_dir`, both legs and the
  waited-job path) carry `moved`, `stale_before`, `forced`, `moved_legacy` (ints),
  `skipped_unchanged` (int) and `duplicate_ids` (a list of `[id, [path, ...]]`).
- The bridge report prints `<term>: N` lines for those terms when non-zero, and
  `duplicate_ids: N` followed by the id and every claiming path.
- `rmx ingest-gmd --as-memory --dry-run` prints `refresh_pending: N` and each of the four terms
  (`moved`, `stale_before`, `forced`, `moved_legacy`) on its own `<term>: N` line.
- The path-aware skip needs the stored `source_path` to EQUAL the file's resolved path; a stored
  path that only resolves to it (symlink form) is `stale_before`, one that resolves elsewhere is
  `moved` -- r5 m3's precedence by stored-path shape.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod
from refmatrix import daemon as dm
from refmatrix import verbs
from refmatrix.store import Store


X_MD = ('---\ngmd: "0.1"\nid: {id}\ntitle: "{id}"\ntags: [project]\nmetadata:\n'
        '  type: feedback\n---\n# {id} {{#root}}\n\n{body}\n\n'
        '## First {{#one}}\n\nalpha\n\n## Second {{#two}}\n\nbeta\n')
Y_MD = ('---\ngmd: "0.1"\nid: y\ntitle: "y"\ntags: [project]\nmetadata:\n  type: feedback\n'
        '---\n# y {#root}\n\ny cites x.\n\nrel: depends-on -> [[x]]\n')
PLAIN = ('---\ngmd: "0.1"\nid: {id}\ntitle: "{id}"\ntags: [project]\nmetadata:\n'
         '  type: feedback\n---\n# {id} {{#root}}\n\n{body}\n')


# ---- fixtures: a throwaway store, in-process or behind a real daemon ------------------------

def _new_store(spawn: bool):
    base = Path(tempfile.mkdtemp(prefix="rmx262-"))
    root = base / "proj" / ".refmatrix"
    root.parent.mkdir()
    s = Store(root)
    s.init()
    s.close()
    if spawn:
        pid = dm.spawn_daemon_subprocess(root, watch_root=[])
        assert pid and dm.ping(root)
    return base, root


@pytest.fixture
def inproc(monkeypatch):
    base, root = _new_store(spawn=False)
    monkeypatch.setenv("REFMATRIX_ROOT", str(root))
    monkeypatch.delenv("RMX_PARTITION", raising=False)
    yield base, root
    shutil.rmtree(base, ignore_errors=True)


@pytest.fixture
def daemon(monkeypatch):
    base, root = _new_store(spawn=True)
    monkeypatch.setenv("REFMATRIX_ROOT", str(root))
    monkeypatch.delenv("RMX_PARTITION", raising=False)
    yield base, root
    dm.stop_daemon(root)
    shutil.rmtree(base, ignore_errors=True)


def _memdir(base: Path, *, marker: bool, name: str = "memory") -> Path:
    d = base / name
    (d / "a").mkdir(parents=True)
    (d / "b").mkdir()
    if marker:
        (d / ".memory-layout").write_text('{"layout": 1}\n', encoding="utf-8")
    (d / "a" / "x.md").write_text(X_MD.format(id="x", body="body of x"), encoding="utf-8")
    (d / "y.md").write_text(Y_MD, encoding="utf-8")
    return d


def _invoke(args, *, ok: bool = True) -> str:
    r = CliRunner().invoke(cli_mod.main, args)
    if ok:
        assert r.exit_code == 0, f"rmx {' '.join(map(str, args))}: exit {r.exit_code}\n" \
                                 f"{r.output}\n{r.exception!r}"
    return r.output


def _bridge(memdir: Path, *extra) -> str:
    return _invoke(["ingest-gmd", "--as-memory", *extra, str(memdir)])


def _move(memdir: Path, src: str = "a/x.md", dst: str = "b/x.md") -> tuple[str, str]:
    """Move a file with its bytes unchanged; return (old, new) RESOLVED paths."""
    old = (memdir / src).resolve()
    new = (memdir / dst).resolve()
    os.replace(old, new)
    return str(old), str(new)


# ---- readers on the throwaway store (daemon stopped first) --------------------------------

def _bridged_partition(s: Store) -> "str | None":
    """The partition the bridge wrote its memory rows into, read off the rows themselves.
    (`verbs.memory_partition` opens a read-only attach, which collides with the catalog the
    in-process CLI leg still holds open in this process.)"""
    row = s._connect().execute(
        "SELECT p.name FROM entities e JOIN partitions p ON p.id = e.partition_id "
        "WHERE e.kind = 'memory' ORDER BY e.id LIMIT 1").fetchone()
    return row[0] if row else None


def _with_store(root: Path, fn):
    s = Store(root)
    try:
        part = _bridged_partition(s)
        if part is None:
            return fn(s)
        with s.with_partition(part):
            return fn(s)
    finally:
        s.close()


def _mem(root: Path, name: str) -> dict:
    """Everything AC-1 says must not change, plus the path it says must."""
    def _read(s):
        con = s._connect()
        rows = con.execute(
            "SELECT e.id, e.protected, e.noise, e.vectors_updated_at, mc.metadata, "
            "mc.created_at, mc.content FROM entities e "
            "JOIN memory_content mc ON mc.entity_id = e.id "
            "WHERE e.kind = 'memory' AND e.name = ?", (name,)).fetchall()
        assert len(rows) == 1, f"{len(rows)} memory rows named {name!r}, expected exactly 1"
        r = rows[0]
        meta = json.loads(r[4]) if r[4] else {}
        eid = int(r[0])
        inbound = sorted(
            (lt, c) for lt, c in con.execute(
                "SELECT lt.name, c.name FROM entity_links el "
                "JOIN linkage_types lt ON lt.id = el.linkage_id "
                "JOIN entities c ON c.id = el.concept_id "
                "WHERE el.entity_id = ? AND lt.name = 'depends-on'", (eid,)).fetchall())
        vec = None
        try:
            ids, mat = s.read_vectors(kind="memory", ids=[eid])
            if len(ids):
                vec = [round(float(v), 6) for v in mat[0]]
        except Exception as exc:  # noqa: BLE001 -- named in the dict, compared as such
            vec = f"read_vectors failed: {type(exc).__name__}"
        return {"id": eid, "protected": int(r[1]), "noise": int(r[2]),
                "vectors_updated_at": r[3], "source_path": meta.get("source_path"),
                "source": meta.get("source"), "created_at": r[5], "content": r[6],
                "inbound": inbound, "vector": vec}
    return _with_store(root, _read)


def _anchor_paths(root: Path, doc_id: str) -> dict:
    def _read(s):
        return {n: p for n, p in s._connect().execute(
            "SELECT name, path FROM entities WHERE kind = 'concept' AND name LIKE ?",
            (f"{doc_id}#%",)).fetchall()}
    return _with_store(root, _read)


def _seed_legacy(root: Path, *, name: str, source_path: str, content: str) -> int:
    """A pre-`sync-disk`-alias legacy row (r5 s1): differently named, same `source_path`.
    Written with `Store` on the THROWAWAY store only."""
    def _w(s):
        return s.add_memory(name=name, content=content, mtype="feedback",
                            metadata={"source": "memory_sync_disk", "source_path": source_path})
    return _with_store(root, _w)


def _set_source_path(root: Path, name: str, value: "str | None") -> None:
    """Rewrite (or drop, `None`) one row's stored `source_path` -- the shape an older store
    holds (a missing key, or the symlink form of the memdir, as viascope's)."""
    def _w(s):
        con = s._connect()
        eid, meta = con.execute(
            "SELECT e.id, mc.metadata FROM entities e JOIN memory_content mc "
            "ON mc.entity_id = e.id WHERE e.kind = 'memory' AND e.name = ?", (name,)).fetchone()
        meta = json.loads(meta)
        if value is None:
            meta.pop("source_path", None)
        else:
            meta["source_path"] = value
        con.execute("UPDATE memory_content SET metadata = ? WHERE entity_id = ?",
                    (json.dumps(meta), eid))
        con.commit()
    _with_store(root, _w)


def _set_flags(root: Path, name: str) -> None:
    def _w(s):
        con = s._connect()
        con.execute("UPDATE entities SET protected = 1, noise = 1 "
                    "WHERE kind = 'memory' AND name = ?", (name,))
        con.commit()
    _with_store(root, _w)


def _term(text: str, term: str) -> "int | None":
    m = re.search(rf"^\s*{re.escape(term)}: (\d+)\b", text, re.M)
    return int(m.group(1)) if m else None


def _facts_size(root: Path) -> int:
    p = root / "facts.log"
    return p.stat().st_size if p.exists() else 0


# =============================================================================================
# AC-1: a move refreshes the row; it never creates a new one
# =============================================================================================

def _ac1_assert(root: Path, before: dict, new: str) -> None:
    after = _mem(root, "x")                      # asserts exactly one `x` memory row
    assert after["source_path"] == new, \
        f"memory_content.metadata.source_path is {after['source_path']!r}, not the moved {new!r}"
    anchors = _anchor_paths(root, "x")
    assert anchors and set(anchors.values()) == {new}, f"x#anchor paths after the move: {anchors}"
    for k in ("id", "created_at", "protected", "noise", "vector", "vectors_updated_at",
              "inbound", "content"):
        assert after[k] == before[k], f"{k} changed across the move: {before[k]!r} -> {after[k]!r}"


def test_ac1_in_process_move_refreshes_the_row_and_its_anchors(inproc):
    base, root = inproc
    memdir = _memdir(base, marker=True)
    _bridge(memdir)
    before = _mem(root, "x")
    assert before["inbound"], "fixture: y's `rel: depends-on -> [[x]]` edge did not land"
    assert before["vector"] is not None, "fixture: x has no vector to compare"
    old, new = _move(memdir)
    assert before["source_path"] == old
    _bridge(memdir)
    _ac1_assert(root, before, new)


def test_ac1_moved_row_keeps_its_protected_and_noise_flags(inproc):
    base, root = inproc
    memdir = _memdir(base, marker=True)
    _bridge(memdir)
    _set_flags(root, "x")
    before = _mem(root, "x")
    assert before["protected"] == 1 and before["noise"] == 1
    _, new = _move(memdir)
    _bridge(memdir)
    _ac1_assert(root, before, new)


def test_ac1_daemon_move_refreshes_the_row_and_its_anchors(daemon):
    """The daemon path is the one save-state uses (spec #test-strategy)."""
    base, root = daemon
    memdir = _memdir(base, marker=True)
    _bridge(memdir)
    dm.stop_daemon(root)
    before = _mem(root, "x")
    _, new = _move(memdir)
    assert dm.spawn_daemon_subprocess(root, watch_root=[]) and dm.ping(root)
    _bridge(memdir)
    dm.stop_daemon(root)
    _ac1_assert(root, before, new)


def test_ac1_symlinked_memdir_move_stores_the_resolved_path(inproc):
    """viascope's memdir is a symlink (plan-27): the refresh stores the RESOLVED path."""
    base, root = inproc
    real = _memdir(base, marker=True, name="real-memory")
    link = base / "memory"
    link.symlink_to(real, target_is_directory=True)
    _bridge(link)
    before = _mem(root, "x")
    os.replace(real / "a" / "x.md", real / "b" / "x.md")
    _bridge(link)
    _ac1_assert(root, before, str((real / "b" / "x.md").resolve()))


# =============================================================================================
# AC-1b: a move refreshes EVERY row on the old path, in one logged write (r5 s1, r6-lite n1/n2)
# =============================================================================================

def _ac1b_fixture(base: Path, root: Path, *, marker: bool):
    memdir = _memdir(base, marker=marker)
    _bridge(memdir)
    old = str((memdir / "a" / "x.md").resolve())
    _seed_legacy(root, name="legacy-x", source_path=old, content="the legacy body of x")
    legacy0 = _mem(root, "legacy-x")
    _, new = _move(memdir)
    return memdir, old, new, legacy0


def test_ac1b_every_row_on_the_old_path_is_refreshed_and_counted(inproc):
    base, root = inproc
    memdir, old, new, legacy0 = _ac1b_fixture(base, root, marker=True)
    out = cli_mod._sync_memory_dir(memdir)
    assert out["error"] is None, out
    assert _mem(root, "x")["source_path"] == new
    legacy = _mem(root, "legacy-x")
    assert legacy["source_path"] == new, \
        f"legacy-x still names {legacy['source_path']!r} after its file moved to {new!r}"
    for k in ("id", "content", "protected", "noise", "created_at", "source"):
        assert legacy[k] == legacy0[k], f"legacy-x {k} changed: {legacy0[k]!r} -> {legacy[k]!r}"
    assert out.get("moved") == 1 and out.get("moved_legacy") == 1, \
        f"bridge result terms: moved={out.get('moved')!r} moved_legacy={out.get('moved_legacy')!r}"
    rep = out["report"] or ""
    assert _term(rep, "moved") == 1 and _term(rep, "moved_legacy") == 1, rep


def test_ac1b_daemon_leg_refreshes_the_legacy_row(daemon):
    base, root = daemon
    memdir = _memdir(base, marker=True)
    _bridge(memdir)
    dm.stop_daemon(root)
    old = str((memdir / "a" / "x.md").resolve())
    _seed_legacy(root, name="legacy-x", source_path=old, content="the legacy body of x")
    _, new = _move(memdir)
    assert dm.spawn_daemon_subprocess(root, watch_root=[]) and dm.ping(root)
    out = cli_mod._sync_memory_dir(memdir)
    dm.stop_daemon(root)
    assert out["error"] is None, out
    assert _mem(root, "legacy-x")["source_path"] == new
    assert out.get("moved") == 1 and out.get("moved_legacy") == 1, out


def test_ac1b_marker_off_twin_refreshes_nothing(inproc):
    """AC-3b: an un-organised dir keeps HEAD's hash-only gate -- no row is refreshed, and the
    bridge SAYS so (all refresh terms present and zero)."""
    base, root = inproc
    memdir, old, new, _ = _ac1b_fixture(base, root, marker=False)
    out = cli_mod._sync_memory_dir(memdir)
    assert out["error"] is None, out
    assert _mem(root, "x")["source_path"] == old
    assert _mem(root, "legacy-x")["source_path"] == old
    for k in ("moved", "moved_legacy", "stale_before", "forced"):
        assert out.get(k) == 0, f"marker-off bridge result {k}={out.get(k)!r}, expected 0"


def test_ac1b_legacy_refresh_survives_rebuild_from_log(inproc):
    """r6-lite n1: the legacy row's refresh is a logged `memory_content` event carrying
    `updated_at`, so replaying facts.log into a FRESH store reproduces the new path."""
    base, root = inproc
    memdir, old, new, _ = _ac1b_fixture(base, root, marker=True)
    _bridge(memdir)
    assert _mem(root, "legacy-x")["source_path"] == new
    events = [json.loads(ln) for ln in (root / "facts.log").read_text().splitlines() if ln]
    legacy_ev = [e for e in events if e.get("op") == "memory_content"
                 and e.get("name") == "legacy-x"]
    assert legacy_ev and (legacy_ev[-1].get("metadata") or {}).get("source_path") == new, \
        f"no memory_content event logs legacy-x at {new!r}: {legacy_ev[-1:]}"
    assert "updated_at" in legacy_ev[-1], \
        f"the legacy refresh event carries no updated_at (r6 cross-plan note): {legacy_ev[-1]}"
    fresh = base / "fresh" / ".refmatrix"
    fresh.mkdir(parents=True)
    shutil.copy2(root / "facts.log", fresh / "facts.log")
    s = Store(fresh)
    try:
        s.rebuild_index_from_log()
        got = s.find_memory_any_partition("legacy-x")
    finally:
        s.close()
    assert got is not None, "replay lost legacy-x entirely"
    assert got["metadata"].get("source_path") == new, \
        f"replay restored legacy-x at {got['metadata'].get('source_path')!r}, not {new!r}"


def test_ac1b_symlink_form_id_row_is_stale_before_and_still_counts_its_legacy_row(inproc):
    """r6-lite n2: the id row stored the symlink form of its path (viascope), so it lands in
    `stale_before`, not `moved`; its legacy row on the old path is still refreshed and counted
    as `moved_legacy`."""
    base, root = inproc
    real = _memdir(base, marker=True, name="real-memory")
    link = base / "memory"
    link.symlink_to(real, target_is_directory=True)
    _bridge(link)
    _set_source_path(root, "x", str(link / "a" / "x.md"))          # symlink form
    _seed_legacy(root, name="legacy-x", source_path=str((real / "a" / "x.md").resolve()),
                 content="the legacy body of x")
    os.replace(real / "a" / "x.md", real / "b" / "x.md")
    new = str((real / "b" / "x.md").resolve())
    out = cli_mod._sync_memory_dir(link)
    assert out["error"] is None, out
    assert _mem(root, "x")["source_path"] == new
    assert _mem(root, "legacy-x")["source_path"] == new
    assert (out.get("stale_before"), out.get("moved"), out.get("moved_legacy")) == (1, 0, 1), \
        f"terms: stale_before={out.get('stale_before')!r} moved={out.get('moved')!r} " \
        f"moved_legacy={out.get('moved_legacy')!r}"


# =============================================================================================
# AC-2: the gate reuses the recorded path; an unchanged file at an unchanged path is skipped
# =============================================================================================

def test_ac2_unchanged_file_is_skipped_counted_and_writes_nothing(inproc):
    base, root = inproc
    memdir = _memdir(base, marker=True)
    _bridge(memdir)
    size0 = _facts_size(root)
    before = _mem(root, "x")
    out = cli_mod._sync_memory_dir(memdir)
    assert out["error"] is None, out
    assert _facts_size(root) == size0, "an unchanged re-bridge wrote to the store (facts.log grew)"
    assert _mem(root, "x") == before
    assert out.get("skipped_unchanged") == 2, \
        f"skipped_unchanged={out.get('skipped_unchanged')!r}, expected 2 (x and y)"
    assert (out.get("moved"), out.get("stale_before")) == (0, 0), out


def test_ac2_symlinked_memdir_unchanged_compares_equal(inproc):
    """The daemon/CLI resolve their targets, so a memdir reached through a symlink stores and
    compares the resolved path: a re-run refreshes nothing."""
    base, root = inproc
    real = _memdir(base, marker=True, name="real-memory")
    link = base / "memory"
    link.symlink_to(real, target_is_directory=True)
    _bridge(link)
    size0 = _facts_size(root)
    out = cli_mod._sync_memory_dir(link)
    assert out["error"] is None, out
    assert _facts_size(root) == size0
    assert out.get("skipped_unchanged") == 2 and out.get("stale_before") == 0, out


def test_ac2_no_gmd_source_path_key_is_added(inproc):
    """r1 #s5: the gate reuses `source_path` / `entities.path`; no second copy of the path."""
    base, root = inproc
    memdir = _memdir(base, marker=True)
    _bridge(memdir)
    _move(memdir)
    _bridge(memdir)

    def _metas(s):
        return [m for (m,) in s._connect().execute(
            "SELECT meta FROM entities WHERE meta IS NOT NULL").fetchall()] + \
               [m for (m,) in s._connect().execute(
                   "SELECT metadata FROM memory_content WHERE metadata IS NOT NULL").fetchall()]
    leaked = [m for m in _with_store(root, _metas) if "gmd_source_path" in m]
    assert not leaked, f"a gmd_source_path key was added: {leaked[:3]}"


def test_ac2_doc_row_keeps_the_hash_only_gate(inproc):
    """#rd-doc-rows (2026-11-10): doc rows are never path-aware. A doc tree carries no
    `.memory-layout`, and a doc move is the watcher's `sync` job, so a moved doc with unchanged
    bytes is skipped by HEAD's hash-only gate and keeps its recorded path. A pin: it passes at
    HEAD and is proven by a mutation that makes the doc-row gate path-aware."""
    base, root = inproc
    tree = base / "docs"
    (tree / "a").mkdir(parents=True)
    (tree / "b").mkdir()
    (tree / "a" / "d.md").write_text(PLAIN.format(id="d", body="a doc"), encoding="utf-8")
    _invoke(["ingest-gmd", str(tree)])
    old = str((tree / "a" / "d.md").resolve())
    size0 = _facts_size(root)
    os.replace(tree / "a" / "d.md", tree / "b" / "d.md")
    _invoke(["ingest-gmd", str(tree)])

    def _path(s):
        return [p for (p,) in s._connect().execute(
            "SELECT path FROM entities WHERE kind = 'doc' AND name = 'd'").fetchall()]
    assert _with_store(root, _path) == [old], "a doc row's gate became path-aware"
    assert _facts_size(root) == size0, "the hash-only doc gate wrote on an unchanged doc"


def test_ac3_missing_source_path_is_reingested_once(inproc):
    """AC-3: a row with no `source_path` is re-ingested ONCE (`stale_before`), then skipped."""
    base, root = inproc
    memdir = _memdir(base, marker=True)
    _bridge(memdir)
    _set_source_path(root, "x", None)
    out1 = cli_mod._sync_memory_dir(memdir)
    assert out1["error"] is None, out1
    assert _mem(root, "x")["source_path"] == str((memdir / "a" / "x.md").resolve())
    assert out1.get("stale_before") == 1, out1
    out2 = cli_mod._sync_memory_dir(memdir)
    assert out2.get("stale_before") == 0 and out2.get("skipped_unchanged") == 2, out2


# =============================================================================================
# AC-3: `--dry-run` / `--store-snapshot` / `--path-map`: the one-time refresh, measured
# =============================================================================================

def test_ac3_dry_run_reports_refresh_pending_and_writes_nothing(inproc):
    """The dry-run evaluates the MARKER-ON rule whatever the dir's marker says (r4 s2): this
    dir has no marker, and the moved file still counts."""
    base, root = inproc
    memdir = _memdir(base, marker=False)
    _bridge(memdir)
    old, _ = _move(memdir)
    size0 = _facts_size(root)
    out = _bridge(memdir, "--dry-run")
    assert _term(out, "refresh_pending") == 1, out
    assert _term(out, "moved") == 1 and _term(out, "stale_before") == 0, out
    assert _term(out, "forced") == 0 and _term(out, "moved_legacy") == 0, out
    assert _facts_size(root) == size0, "--dry-run wrote to the store"
    assert _mem(root, "x")["source_path"] == old, "--dry-run refreshed a row"
    assert not (memdir / "MEMORY.md").exists(), "--dry-run wrote the memory index"


def test_ac3_dry_run_prints_the_four_pre_registered_terms(inproc):
    """r6-lite n2's pre-registered expectation, term by term: one missing `source_path`, one
    symlink-form stored path, one moved file, one legacy row on that file's old path."""
    base, root = inproc
    real = _memdir(base, marker=False, name="real-memory")
    (real / "m.md").write_text(PLAIN.format(id="m", body="missing path"), encoding="utf-8")
    (real / "s.md").write_text(PLAIN.format(id="s", body="symlink form"), encoding="utf-8")
    link = base / "memory"
    link.symlink_to(real, target_is_directory=True)
    _bridge(link)
    _set_source_path(root, "m", None)
    _set_source_path(root, "s", str(link / "s.md"))
    _seed_legacy(root, name="legacy-x", source_path=str((real / "a" / "x.md").resolve()),
                 content="the legacy body of x")
    os.replace(real / "a" / "x.md", real / "b" / "x.md")
    out = _bridge(link, "--dry-run")
    got = {t: _term(out, t) for t in ("refresh_pending", "stale_before", "moved",
                                      "moved_legacy", "forced")}
    assert got == {"refresh_pending": 4, "stale_before": 2, "moved": 1, "moved_legacy": 1,
                   "forced": 0}, f"{got}\n{out}"


# The daemonless assertion (r5 m4): 23.0's sandbox REFUSES live sockets but does not record a
# connect to a sandbox socket, so a test-local audit hook records every `socket.connect` while
# the flag is on. Audit hooks cannot be removed; this one is installed once per process.
_CONNECTS: list = []
_RECORDING = [False]
_HOOKED = [False]


def _install_connect_recorder() -> None:
    if _HOOKED[0]:
        return

    def _hook(event, args):
        if _RECORDING[0] and event == "socket.connect":
            _CONNECTS.append(repr(args[1]) if len(args) > 1 else repr(args))
    sys.addaudithook(_hook)
    _HOOKED[0] = True


def _snapshot_of(root: Path, dest: Path) -> Path:
    """A copy of the throwaway store's catalog, as the measurement copies a read snapshot."""
    s = Store(root)
    try:
        s._connect()
        src = Path(s.db_path)
        s.close()
    finally:
        s.close()
    dest.mkdir(parents=True)
    out = dest / "catalog.read.duckdb"
    shutil.copy2(src, out)
    return out


@pytest.fixture
def snapshot_env(inproc, monkeypatch):
    """A filled throwaway store; then `RMX_HOME` -> an EMPTY sandbox dir and `REFMATRIX_ROOT`
    -> a root that does not exist, so a run that resolves either one is caught."""
    base, root = inproc
    memdir = _memdir(base, marker=False)
    (memdir / "u.md").write_text(PLAIN.format(id="u", body="unchanged"), encoding="utf-8")
    _bridge(memdir)
    part = _with_store(root, _bridged_partition)
    snap = _snapshot_of(root, base / "snap")
    home = base / "empty-home"
    home.mkdir()
    ghost = base / "ghost" / ".refmatrix"
    monkeypatch.setenv("RMX_HOME", str(home))
    monkeypatch.setenv("REFMATRIX_ROOT", str(ghost))
    _install_connect_recorder()
    return base, memdir, snap, part, ghost, home


def _snapshot_run(args) -> str:
    _CONNECTS.clear()
    _RECORDING[0] = True
    try:
        return _invoke(args)
    finally:
        _RECORDING[0] = False


def test_ac3_store_snapshot_dry_run_is_daemonless(snapshot_env):
    base, memdir, snap, part, ghost, home = snapshot_env
    _move(memdir)
    out = _snapshot_run(["-p", part, "ingest-gmd", "--as-memory", "--dry-run",
                         "--store-snapshot", str(snap), str(memdir)])
    assert _term(out, "refresh_pending") == 1 and _term(out, "moved") == 1, out
    assert _CONNECTS == [], f"--store-snapshot connected to sockets: {_CONNECTS}"
    assert not ghost.exists(), "--store-snapshot resolved (and created) the live root"
    assert list(home.iterdir()) == [], f"--store-snapshot wrote under RMX_HOME: {list(home.iterdir())}"


def test_ac3_store_snapshot_without_a_partition_is_refused(snapshot_env):
    """#rd-snapshot-partition: a snapshot run has no live root to derive the memory partition
    from, so `--store-snapshot` without `-p` exits non-zero and names the flag -- and still
    touches no socket."""
    base, memdir, snap, part, ghost, home = snapshot_env
    _CONNECTS.clear()
    _RECORDING[0] = True
    try:
        r = CliRunner().invoke(cli_mod.main, ["ingest-gmd", "--as-memory", "--dry-run",
                                              "--store-snapshot", str(snap), str(memdir)])
    finally:
        _RECORDING[0] = False
    out = r.output + (str(r.exception) if r.exception else "")
    assert "No such option" not in out, f"the flags do not exist yet: {out}"
    assert r.exit_code != 0, f"--store-snapshot without -p ran: {out}"
    assert re.search(r"(?<![\w-])(-p|--partition)\b", out), \
        f"the refusal does not name -p/--partition: {out}"
    assert _CONNECTS == [], f"the refused run connected to sockets: {_CONNECTS}"
    assert not ghost.exists()


def test_ac3_relocated_twin_reports_zero_through_path_map(snapshot_env):
    """r3 s2: a COPY of the memdir with nothing changed. Without `--path-map` every row looks
    moved (~100%: the defect this case pins); with it, nothing is pending."""
    base, memdir, snap, part, ghost, home = snapshot_env
    twin = base / "twin-memory"
    shutil.copytree(memdir, twin, symlinks=True)
    raw = _snapshot_run(["-p", part, "ingest-gmd", "--as-memory", "--dry-run",
                         "--store-snapshot", str(snap), str(twin)])
    assert _term(raw, "refresh_pending") == 3, f"unmapped twin should count all 3 rows:\n{raw}"
    mapped = _snapshot_run(["-p", part, "ingest-gmd", "--as-memory", "--dry-run",
                            "--store-snapshot", str(snap),
                            "--path-map", f"{memdir.resolve()}={twin.resolve()}", str(twin)])
    assert _term(mapped, "refresh_pending") == 0, mapped
    assert _CONNECTS == [], f"--store-snapshot connected to sockets: {_CONNECTS}"


# =============================================================================================
# AC-4: an id claimed twice is refused, counted and named
# =============================================================================================

def _dup_memdir(base: Path) -> tuple[Path, list[str]]:
    d = base / "memory"
    (d / "a").mkdir(parents=True)
    (d / "b").mkdir()
    (d / "a" / "x.md").write_text(PLAIN.format(id="x", body="x version one"), encoding="utf-8")
    return d, [str((d / "a" / "x.md").resolve()), str((d / "b" / "dup.md").resolve())]


def _add_dup(d: Path) -> None:
    (d / "a" / "x.md").write_text(PLAIN.format(id="x", body="x version two"), encoding="utf-8")
    (d / "b" / "dup.md").write_text(PLAIN.format(id="x", body="a second file claiming x"),
                                    encoding="utf-8")


def _assert_dup_reported(out: dict, paths: list[str], where: str) -> None:
    assert out["error"] is None, f"{where}: {out}"
    dups = out.get("duplicate_ids")
    assert dups is not None, f"{where}: bridge result carries no duplicate_ids: {out}"
    norm = {(i, tuple(sorted(str(Path(p).resolve()) for p in ps))) for i, ps in dups}
    assert norm == {("x", tuple(sorted(paths)))}, f"{where}: duplicate_ids={dups!r}"
    rep = " ".join(str(out.get("report") or "").split())
    assert re.search(r"duplicate_ids: 1\b", rep), f"{where}: no duplicate_ids line: {rep}"
    missing = [p for p in paths if p not in rep]
    assert not missing, f"{where}: report does not name {missing}: {rep}"


def _assert_prior_content_kept(root: Path, first_path: str) -> None:
    m = _mem(root, "x")
    assert "x version one" in m["content"], \
        f"a duplicate id overwrote the stored row: content={m['content']!r}"
    assert m["source_path"] == first_path, m


def test_ac4_in_process_duplicate_id_is_refused_counted_and_named(inproc):
    base, root = inproc
    d, paths = _dup_memdir(base)
    _bridge(d)
    _add_dup(d)
    out = cli_mod._sync_memory_dir(d)
    _assert_dup_reported(out, paths, "in-process bridge")
    _assert_prior_content_kept(root, paths[0])


def test_ac4_ingest_stats_carry_duplicate_ids(inproc):
    from refmatrix.ingest_gmd import collect_gmd_files, ingest_gmd_paths
    base, root = inproc
    d, paths = _dup_memdir(base)
    _add_dup(d)
    s = Store(root)
    try:
        st = ingest_gmd_paths(s, collect_gmd_files([d.resolve()], as_memory=True),
                              as_memory=True)
    finally:
        s.close()
    assert [(i, sorted(map(str, ps))) for i, ps in st.duplicate_ids] == [("x", sorted(paths))]
    assert [(i, sorted(ps)) for i, ps in st.as_dict()["duplicate_ids"]] == \
        [("x", sorted(paths))]
    # a fresh store has no prior row: neither claimant is written (neither overwrites the other)
    assert _with_store(root, lambda s2: s2.find_memory_any_partition("x")) is None, \
        "a contested id was written: one claimant silently won"


def test_ac4_daemon_duplicate_id_is_refused_counted_and_named(daemon):
    base, root = daemon
    d, paths = _dup_memdir(base)
    _bridge(d)
    _add_dup(d)
    out = cli_mod._sync_memory_dir(d)
    assert out["waited"] is False, out
    dm.stop_daemon(root)
    _assert_dup_reported(out, paths, "daemon bridge")
    _assert_prior_content_kept(root, paths[0])


def test_ac4_waited_job_result_carries_duplicate_ids(daemon, monkeypatch):
    """r1 #m5: the overlap path takes the covering job's result; it must carry the field."""
    base, root = daemon
    d, paths = _dup_memdir(base)
    _add_dup(d)
    for i in range(350):                      # long enough that the bridge meets it running
        (d / f"doc{i:04d}.md").write_text(PLAIN.format(id=f"w_doc{i:04d}", body="x " * 400),
                                          encoding="utf-8")
    part = verbs.memory_partition(root)
    resp = dm.call(root, "ingest_gmd_start", {"targets": [str(d.resolve())], "as_memory": True,
                                              "memory_mtype": "curated", "partition": part},
                   timeout=30)
    assert resp.get("ok"), resp
    monkeypatch.setenv("RMX_BRIDGE_WAIT_S", "300")
    out = cli_mod._sync_memory_dir(d)
    assert out["waited"] is True and out["waited_job"] == resp["result"]["job_id"], out
    _assert_dup_reported(out, paths, "waited bridge")


def test_ac4_save_state_output_names_the_duplicate(daemon, monkeypatch):
    base, root = daemon
    d, paths = _dup_memdir(base)
    _add_dup(d)
    (d / "MEMORY.md").write_text("")
    monkeypatch.setenv("RMX_SESSION", "s-262")
    from refmatrix import stm as stm_mod
    stm_mod.Stm(root, "s-262").record("input", "hi")
    r = CliRunner().invoke(cli_mod.main, ["save-state", "--memory-dir", str(d), "--no-lint",
                                          "--no-promote"])
    assert r.exit_code == 0, r.output + repr(r.exception)
    flat = " ".join(r.output.split())
    assert "duplicate_ids" in flat and all(p in flat for p in paths), flat


# =============================================================================================
# AC-5: no forget path touches memory rows on a move (regression pin)
# =============================================================================================

def test_ac5_vacuum_and_sync_after_a_move_keep_the_row_and_its_anchors(inproc):
    base, root = inproc
    memdir = _memdir(base, marker=True)
    _bridge(memdir)
    eid0 = _mem(root, "x")["id"]
    old, new = _move(memdir)
    _bridge(memdir)
    _invoke(["vacuum"])
    # the watcher's view of a move: the OLD path was deleted. Sync it, then force-purge it
    # (`--invalidate`): neither may reach the moved memory row or its anchors.
    _invoke(["sync", "--project-root", str(base / "proj"), "-f", old])
    _invoke(["sync", "--project-root", str(base / "proj"), "-i", old])
    m = _mem(root, "x")
    anchors = _anchor_paths(root, "x")
    # survival first (the regression pin), then provenance (AC-1)
    assert m["id"] == eid0, f"the memory row was replaced: {eid0} -> {m['id']}"
    assert set(anchors) == {"x#root", "x#one", "x#two"}, f"anchors after vacuum + sync: {anchors}"
    assert m["source_path"] == new, f"source_path after vacuum + sync: {m['source_path']!r}"
    assert set(anchors.values()) == {new}, anchors
