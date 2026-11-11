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
    X_MD, _anchor_paths, _bridge, _invoke, _mem, _memdir, _move, _term, inproc, snapshot_env,
)

ANCHORS = {"x#root", "x#one", "x#two"}


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
    base, proj, root = _git_project(spawn=True)
    monkeypatch.setenv("REFMATRIX_ROOT", str(root))
    monkeypatch.delenv("RMX_PARTITION", raising=False)
    yield base, proj, root
    dm.stop_daemon(root)
    shutil.rmtree(base, ignore_errors=True)


@pytest.fixture
def gitproj_inproc(monkeypatch):
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
