"""Task 26.2, ch-bsd r1 remedy (8a867bc..90abc72, 2026-11-10): b-1, s-1, m-3, m-4.

WHY. r1's blocker (b-1): a memdir that lives INSIDE a git project under `.claude/` (viascope's
layout, plan-27) reaches `sync._sync_paths` through the project's git post-commit
`rmx sync --since HEAD~1`, and through `-f` / `-i`. `should_ignore` is True for any dot-segment,
so the sync purges every entity whose `path` is the changed file -- the memory's `x#anchor`
concepts included. In an organised dir the anchors follow a moved file (26.2 AC-1), so the
commit that records the move lists the NEW path and the sync purges the NEW anchors; the
path-aware gate then sees hash + source_path unchanged and skips the file forever. 26.2 turned
"stale but alive" into "purged for good". The EDIT twin (either gate) loses its anchors the same
way -- pre-existing, pinned here because the same fix covers it.

These tests pin the BEHAVIOUR only: after the sync the anchors exist at the file's current path,
and the next bridge still skips the file as unchanged. They do not pin how the fix decides the
bridge owns a row (a stamp, or a `source_path` match).

The rest:
- s-1: an UNREADABLE marker turns the path-aware gate on (ADR-0005 #marker-encoding: never read
  as "not organised") and the report names the marker -- the behaviour exists at HEAD, unpinned;
  this test is proven by killing r1's mutations A and B, not by a RED.
- m-3: a `.memory-layout` in an ANCESTOR of the memdir is not the memdir's marker (ADR-0005
  #marker) and must not turn the gate on.
- m-4: `--store-snapshot -p <partition absent from the copy>` is refused cleanly, naming it.

Real CLI through CliRunner; a real spawned daemon for the post-commit leg; a throwaway store
under a short `mkdtemp(dir="/tmp")` root, RESOLVED (an unresolved `/var` root would store
anchor paths the resolved purge never matches, hiding the marker-off edit loss); a real git repo
in that root. Nothing in the bridge or the sync is mocked.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod
from refmatrix import daemon as dm
from refmatrix.store import Store
from tests.test_bridge_move_safety import (  # noqa: F401 -- fixtures are used by name
    X_MD, _anchor_paths, _bridge, _invoke, _mem, _memdir, _move, _set_source_path, _term,
    _with_store, inproc, snapshot_env,
)

ANCHORS = {"x#root", "x#one", "x#two"}


# ---- every child imports THIS checkout (ch-bsd 26.2 r2 #m2-1) -------------------------------

CHECKOUT_SRC = str(Path(__file__).resolve().parents[1] / "src")


def absolute_pythonpath(pp: "str | None") -> str:
    """`PYTHONPATH` for a child: this checkout's `src`, ABSOLUTE, first; other absolute entries
    kept (the sandbox's `tests/sandbox_site` rides here); relative entries DROPPED. The conftest
    guards only this process's import. A child run in a throwaway cwd resolves a caller's
    relative `PYTHONPATH=src` against that cwd, finds nothing, and imports the venv's editable
    tree instead -- a false RED or a false GREEN on code the run never meant to test."""
    keep = [e for e in (pp or "").split(os.pathsep)
            if e and os.path.isabs(e) and os.path.normpath(e) != CHECKOUT_SRC]
    return os.pathsep.join([CHECKOUT_SRC, *keep])


def _pin_child_pythonpath(monkeypatch) -> None:
    """Set before any daemon spawn: `spawn_daemon_subprocess` and every CLI / hook subprocess
    copy `os.environ`."""
    monkeypatch.setenv("PYTHONPATH", absolute_pythonpath(os.environ.get("PYTHONPATH")))


# ---- a git project with its memdir under `.claude/`, store under a short resolved root ------

def _git_project(spawn: bool):
    base = Path(tempfile.mkdtemp(prefix="r1-", dir="/tmp")).resolve()
    proj = base / "proj"
    root = proj / ".refmatrix"
    proj.mkdir()
    s = Store(root)
    s.init()
    s.close()
    assert len(str(dm.socket_path(root))) < 100, f"socket path too long: {dm.socket_path(root)}"
    if spawn:
        pid = dm.spawn_daemon_subprocess(root, watch_root=[])
        assert pid and dm.ping(root)
    return base, proj, root


@pytest.fixture
def gitproj(monkeypatch):
    _pin_child_pythonpath(monkeypatch)
    base, proj, root = _git_project(spawn=True)
    monkeypatch.setenv("REFMATRIX_ROOT", str(root))
    monkeypatch.delenv("RMX_PARTITION", raising=False)
    yield base, proj, root
    dm.stop_daemon(root)
    shutil.rmtree(base, ignore_errors=True)


@pytest.fixture
def gitproj_inproc(monkeypatch):
    _pin_child_pythonpath(monkeypatch)
    base, proj, root = _git_project(spawn=False)
    monkeypatch.setenv("REFMATRIX_ROOT", str(root))
    monkeypatch.delenv("RMX_PARTITION", raising=False)
    yield base, proj, root
    shutil.rmtree(base, ignore_errors=True)


def _git(proj: Path, *args: str) -> None:
    # No templates, no hooks: the throwaway repo must never run a post-commit `rmx` of its own.
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    r = subprocess.run(["git", "-C", str(proj), "-c", f"core.hooksPath={proj}/.nohooks",
                        *args], env=env, capture_output=True, text=True)
    assert r.returncode == 0, f"git {' '.join(args)}: {r.stdout}{r.stderr}"


def _init_repo(proj: Path) -> None:
    _git(proj, "init", "-q", "--template=", "-b", "main")
    (proj / ".gitignore").write_text(".refmatrix/\n", encoding="utf-8")
    (proj / "README.md").write_text("r\n", encoding="utf-8")


def _commit(proj: Path, msg: str) -> None:
    _git(proj, "add", "-A")
    _git(proj, "commit", "-q", "-m", msg)


def _proj_memdir(proj: Path, *, marker: bool) -> Path:
    """`<proj>/.claude/projects/slug/memory` -- the shape of viascope's in-repo memdir."""
    return _memdir(proj, marker=marker, name=".claude/projects/slug/memory")


def _post_commit_sync(proj: Path, root: Path) -> str:
    """`rmx sync --since HEAD~1`, as a post-commit hook runs it. The CLI hands `--since` to the
    daemon whenever it answers a ping, so the ping IS the route check (the `[daemon]` suffix of
    the CLI's own report is eaten by rich markup and cannot be read back)."""
    assert dm.ping(root), "the daemon is not up: the sync would run in-process"
    return _invoke(["sync", "--project-root", str(proj), "--since", "HEAD~1"])


def _set_metadata_raw(root: Path, name: str, raw: str) -> None:
    """Overwrite one memory row's `memory_content.metadata` TEXT verbatim (the column is TEXT,
    so `'{not json'` is storable) -- on the THROWAWAY store only, daemon stopped."""
    def _w(s):
        con = s._connect()
        eid = con.execute("SELECT id FROM entities WHERE kind = 'memory' AND name = ?",
                          (name,)).fetchone()[0]
        con.execute("UPDATE memory_content SET metadata = ? WHERE entity_id = ?", (raw, eid))
        con.commit()
    _with_store(root, _w)


MEMORY_X = re.compile(r"memory\W{0,3}x\W")    # the error names the memory x


def _restart(root: Path) -> None:
    assert dm.spawn_daemon_subprocess(root, watch_root=[]) and dm.ping(root)


def _assert_anchors_at(root: Path, path: str, when: str) -> None:
    got = _anchor_paths(root, "x")
    assert set(got) == ANCHORS, f"x's anchors {when}: {sorted(got)} (expected {sorted(ANCHORS)})"
    assert set(got.values()) == {path}, f"x's anchor paths {when}: {got}, expected {path}"


def _assert_next_bridge_skips(memdir: Path, root: Path, path: str) -> None:
    """The bridge after the sync: still `skipped_unchanged` for both files (x and y), and x's
    anchors still where they were -- the gate is not what puts them back.

    The post-commit legs run this bridge on a restarted daemon, which holds the catalog's
    writer lock: it is stopped before the rows are read with `Store` (green-262r1 hit the
    `Could not set lock on file` IOException here; RED never reached this leg)."""
    out = _bridge(memdir)
    assert _term(out, "skipped_unchanged") == 2, f"next bridge did not skip x and y:\n{out}"
    if dm.ping(root):
        dm.stop_daemon(root)
        assert not dm.ping(root), "the daemon still answers after stop_daemon"
    _assert_anchors_at(root, path, "after the next bridge")
    assert _mem(root, "x")["source_path"] == path


# =============================================================================================
# b-1 (i): the post-commit `sync --since` of a commit that recorded a move
# =============================================================================================

def test_b1_post_commit_sync_since_after_a_move_keeps_the_new_anchors(gitproj):
    base, proj, root = gitproj
    _init_repo(proj)
    memdir = _proj_memdir(proj, marker=True)
    _commit(proj, "c0: the memory, before the move")
    _bridge(memdir)
    old, new = _move(memdir)
    out = _bridge(memdir)
    assert _term(out, "moved") == 1, f"fixture: the move was not refreshed:\n{out}"
    _commit(proj, "c1: move a/x.md -> b/x.md")
    # git post-commit, as viascope's hook runs it -- through the REAL CLI, on the daemon
    _post_commit_sync(proj, root)
    dm.stop_daemon(root)
    _assert_anchors_at(root, new, "after the post-commit sync of the move")
    assert _mem(root, "x")["source_path"] == new
    _restart(root)
    _assert_next_bridge_skips(memdir, root, new)


# =============================================================================================
# b-1 (ii): the same with an EDIT, marker on and off (marker-off loss is pre-existing)
# =============================================================================================

@pytest.mark.parametrize("marker", [True, False], ids=["marker-on", "marker-off"])
def test_b1_post_commit_sync_since_after_an_edit_keeps_the_anchors(gitproj, marker):
    base, proj, root = gitproj
    _init_repo(proj)
    memdir = _proj_memdir(proj, marker=marker)
    _commit(proj, "c0: the memory, before the edit")
    _bridge(memdir)
    x = memdir / "a" / "x.md"
    x.write_text(X_MD.format(id="x", body="edited body of x"), encoding="utf-8")
    _bridge(memdir)
    _commit(proj, "c1: edit a/x.md")
    _post_commit_sync(proj, root)
    dm.stop_daemon(root)
    path = str(x.resolve())
    _assert_anchors_at(root, path, "after the post-commit sync of the edit")
    assert "edited body of x" in _mem(root, "x")["content"]
    _restart(root)
    _assert_next_bridge_skips(memdir, root, path)


# =============================================================================================
# b-1 (iii): `rmx sync -i/-f <current path>` keeps the anchors
# =============================================================================================

@pytest.mark.parametrize("flag", ["-i", "-f"])
def test_b1_sync_of_the_current_path_keeps_the_anchors(gitproj_inproc, flag):
    """AC-5's test syncs only the OLD path with the memdir outside the project; this one names
    the moved file's CURRENT path, inside the project under `.claude/`."""
    base, proj, root = gitproj_inproc
    memdir = _proj_memdir(proj, marker=True)
    _bridge(memdir)
    old, new = _move(memdir)
    _bridge(memdir)
    _invoke(["sync", "--project-root", str(proj), flag, new])
    _assert_anchors_at(root, new, f"after `rmx sync {flag} <current path>`")
    assert _mem(root, "x")["source_path"] == new
    _assert_next_bridge_skips(memdir, root, new)


# =============================================================================================
# s-1: an unreadable marker still applies the path-aware gate, and the report names it
# =============================================================================================

def test_s1_unreadable_marker_refreshes_the_move_and_names_the_marker(inproc):
    base, root = inproc
    memdir = _memdir(base, marker=False)
    marker = memdir / ".memory-layout"
    marker.write_text('{"layout": 1,\n', encoding="utf-8")      # invalid JSON
    _bridge(memdir)
    old, new = _move(memdir)
    r = CliRunner().invoke(cli_mod.main, ["ingest-gmd", "--as-memory", str(memdir)])
    out = r.output
    assert r.exit_code == 0, f"an unreadable marker failed the bridge: {r.exit_code}\n{out}" \
                             f"\n{r.exception!r}"
    assert _term(out, "moved") == 1, f"the move under an unreadable marker was not refreshed " \
                                     f"(read as not-organised?):\n{out}"
    errs = [ln for ln in out.splitlines() if ln.strip().startswith("marker_error:")]
    assert errs, f"no `marker_error:` line in the bridge report:\n{out}"
    assert any(str(marker.resolve()) in " ".join(e.split()) or str(marker) in e for e in errs), \
        f"the marker_error line does not name {marker}: {errs}"
    assert _mem(root, "x")["source_path"] == new
    assert set(_anchor_paths(root, "x").values()) == {new}


# =============================================================================================
# m-3: a marker in an ANCESTOR of the memdir is not the memdir's marker
# =============================================================================================

def test_m3_ancestor_marker_does_not_turn_on_the_path_aware_gate(inproc):
    """ADR-0005 #marker: the marker is `<memdir>/.memory-layout`. One in `projects/` (an
    ancestor shared by every memdir below it) leaves this un-marked memdir on HEAD's hash-only
    rule: a moved unchanged file is skipped and its row keeps the old path."""
    base, root = inproc
    memdir = _memdir(base, marker=False, name="projects/slug/memory")
    (base / "projects" / ".memory-layout").write_text('{"layout": 1}\n', encoding="utf-8")
    _bridge(memdir)
    old, new = _move(memdir)
    out = _bridge(memdir)
    assert not _term(out, "moved"), f"an ancestor's marker turned the path-aware gate on:\n{out}"
    assert _term(out, "skipped_unchanged") == 2, f"hash-only rule did not skip x and y:\n{out}"
    assert _mem(root, "x")["source_path"] == old


# =============================================================================================
# m-4: a snapshot run naming a partition the copy does not hold is refused
# =============================================================================================

def test_m4_store_snapshot_with_an_absent_partition_is_refused(snapshot_env):
    base, memdir, snap, part, ghost, home = snapshot_env
    absent = "no-such-partition-r1"
    r = CliRunner().invoke(cli_mod.main, ["-p", absent, "ingest-gmd", "--as-memory",
                                          "--dry-run", "--store-snapshot", str(snap),
                                          str(memdir)])
    out = r.output
    assert r.exit_code != 0, f"--store-snapshot -p {absent} ran:\n{out}"
    # a refusal (click exits), not a crash on the read-only copy
    assert isinstance(r.exception, SystemExit), f"not a clean refusal: {r.exception!r}\n{out}"
    assert absent in out, f"the refusal does not name the partition:\n{out}"
    assert not ghost.exists()


# =============================================================================================
# r1 GREEN survivors (b) and (b2): the guard in `Store.purge_path` decides ownership by the
# memory row's `source_path`, RESOLVED as well as literal, and ONLY by it
# (`#r1-green-survivors`: mutations b and b2 passed 8/8 and 33/33)
# =============================================================================================

def test_b1_guard_keeps_anchors_whose_source_path_is_a_symlink_form_of_the_purged_path(
        gitproj_inproc):
    """(b). The bridge writes the anchor path and `source_path` from one string, so a bridge-only
    history never makes them differ. A store row written before 26.2 can: viascope's memdir is a
    symlink, and its rows hold `source_path` in that symlink form (AC-1b's stale_before case),
    while every sync purges the RESOLVED path. Seeded here on the throwaway store, as
    `_set_source_path` seeds the older shapes in the 26.2 file. The anchors must survive."""
    base, proj, root = gitproj_inproc
    memdir = _proj_memdir(proj, marker=False)
    link = base / "memlink"
    link.symlink_to(memdir, target_is_directory=True)
    _bridge(memdir)
    real = str((memdir / "a" / "x.md").resolve())
    via_link = str(link / "a" / "x.md")
    assert via_link != real and os.path.realpath(via_link) == real, "fixture: not a symlink form"
    _assert_anchors_at(root, real, "after the bridge (fixture)")
    _set_source_path(root, "x", via_link)
    _invoke(["sync", "--project-root", str(proj), "-f", real])
    _assert_anchors_at(root, real, "after `sync -f <resolved path>` with source_path in "
                                   "symlink form")


def test_b1_guard_purges_a_dropped_anchor_left_on_the_old_path(gitproj_inproc):
    """(b2), the natural form. Un-organised dir: x moves AND loses its `## Second {#two}`
    heading. The bridge re-ingests (the hash changed), re-points x#root / x#one to the new
    path, and leaves x#two on the OLD path -- an anchor no memory's `source_path` names. Syncing
    the old (deleted) path must purge it; x's live anchors stay."""
    base, proj, root = gitproj_inproc
    memdir = _proj_memdir(proj, marker=False)
    _bridge(memdir)
    old = str((memdir / "a" / "x.md").resolve())
    new = str((memdir / "b" / "x.md").resolve())
    (memdir / "b" / "x.md").write_text(
        X_MD.format(id="x", body="body of x").split("## Second")[0], encoding="utf-8")
    os.remove(old)
    _bridge(memdir)
    assert _mem(root, "x")["source_path"] == new, "fixture: the edited move was not re-ingested"
    got = _anchor_paths(root, "x")
    assert got.get("x#two") == old and {got.get("x#root"), got.get("x#one")} == {new}, \
        f"fixture: expected x#two stranded on the old path, x#root/x#one on the new: {got}"
    _invoke(["sync", "--project-root", str(proj), "-f", old])
    got = _anchor_paths(root, "x")
    assert "x#two" not in got, f"the stranded x#two on {old} survived the purge: {got}"
    assert got == {"x#root": new, "x#one": new}, f"x's live anchors after the purge: {got}"


def test_b1_guard_purges_a_project_docs_anchors_that_share_a_memory_id(gitproj_inproc):
    """(b2), the id-collision form. A project doc (not a memory) with GMD id `x` re-points the
    `x#...` concepts to its own path. A memory named x exists, but its `source_path` names the
    memdir file, so it does not own them: deleting the doc and syncing its path purges them, as
    before 26.2."""
    base, proj, root = gitproj_inproc
    memdir = _proj_memdir(proj, marker=False)
    _bridge(memdir)
    docs = proj / ".claude" / "docs"
    docs.mkdir(parents=True)
    doc = docs / "x.md"
    doc.write_text(X_MD.format(id="x", body="a project doc that reuses the id x"),
                   encoding="utf-8")
    dpath = str(doc.resolve())
    _invoke(["ingest-gmd", dpath])
    assert set(_anchor_paths(root, "x").values()) == {dpath}, \
        f"fixture: the doc ingest did not re-point x's concepts: {_anchor_paths(root, 'x')}"
    assert _mem(root, "x")["source_path"] != dpath
    doc.unlink()
    _invoke(["sync", "--project-root", str(proj), "-f", dpath])
    got = _anchor_paths(root, "x")
    assert dpath not in got.values(), f"the deleted doc's anchors survived the purge: {got}"


def test_b1_guard_purges_anchors_when_the_memorys_source_path_names_another_file(
        gitproj_inproc):
    """(b2), form 1 (#r1-green-survivors): memory x's `source_path` names an existing OTHER file
    (y.md), so x does not own the anchors at a/x.md. `sync -f a/x.md` purges them."""
    base, proj, root = gitproj_inproc
    memdir = _proj_memdir(proj, marker=False)
    _bridge(memdir)
    p = str((memdir / "a" / "x.md").resolve())
    q = str((memdir / "y.md").resolve())
    _assert_anchors_at(root, p, "after the bridge (fixture)")
    _set_source_path(root, "x", q)
    _invoke(["sync", "--project-root", str(proj), "-f", p])
    got = _anchor_paths(root, "x")
    assert p not in got.values(), \
        f"anchors at {p} survived although memory x's source_path names {q}: {got}"


def test_b1_forgetting_the_memory_releases_its_anchors_to_the_purge(gitproj_inproc):
    """(b2), form 2: the property the `source_path` design is justified by -- ownership ends
    with the memory. After `rmx memory forget x`, `sync -f <its path>` leaves no x#anchor
    there.

    Forget hard-deletes the memory row and its sidecar (`purge_entity`) but leaves the anchor
    concepts, so the precondition below proves the SYNC releases them, through the guard. A
    stamp read off the anchors themselves would survive the forget and protect these orphans
    forever (the guard's docstring); this pin is what kills that design."""
    base, proj, root = gitproj_inproc
    memdir = _proj_memdir(proj, marker=False)
    _bridge(memdir)
    p = str((memdir / "a" / "x.md").resolve())
    _assert_anchors_at(root, p, "after the bridge (fixture)")
    out = _invoke(["memory", "forget", "x", "--yes"])
    assert "forgot" in out, f"fixture: memory x was not forgotten:\n{out}"
    gone = _with_store(root, lambda s: s._connect().execute(
        "SELECT count(*) FROM entities WHERE kind = 'memory' AND name = 'x'").fetchone()[0])
    assert gone == 0, f"fixture: {gone} memory row(s) named x after the forget"
    _assert_anchors_at(root, p, "after the forget, before the sync (fixture: the forget itself "
                                "must not be what removes them)")
    _invoke(["sync", "--project-root", str(proj), "-f", p])
    got = _anchor_paths(root, "x")
    assert p not in got.values(), f"orphaned anchors at {p} survived the purge: {got}"


def test_b1_guard_fails_closed_on_unreadable_memory_metadata(gitproj_inproc):
    """The guard cannot tell whether x owns the anchors when x's metadata does not parse:
    neither deleting nor keeping silently is acceptable on a memory path (CLAUDE.md
    #no-silent-failures). `sync -f P` fails naming x, and the anchors are still there."""
    base, proj, root = gitproj_inproc
    memdir = _proj_memdir(proj, marker=False)
    _bridge(memdir)
    p = str((memdir / "a" / "x.md").resolve())
    _set_metadata_raw(root, "x", "{not json")
    r = CliRunner().invoke(cli_mod.main, ["sync", "--project-root", str(proj), "-f", p])
    text = f"{r.output}\n{r.exception!r}"
    assert r.exit_code != 0, f"the sync succeeded over unreadable metadata:\n{text}"
    assert MEMORY_X.search(text), f"the failure does not name memory x:\n{text}"
    _assert_anchors_at(root, p, "after the refused sync")
