"""bug-212 r5 RED: ch-bsd r4 (`workflow/bullshit/2026-11-14-0040-bug212-r4-03d7b27.md`, DIRTY
1B/1S/5M, NO-GO) and the lead's ruling L95 (`workflow/plan-review-2026-11-13.md`, 2026-11-14).

WHY each group exists:

b-1 (BULLSHIT). r4 routed every read-write `Store(` through the two checked openers, and the
    census (keyed on `Store(`) went green -- while `rmx compact` and `rmx migrate-to-duckdb
    --overwrite` open the same catalog FILE with the raw `open_duckdb` and rename / unlink over
    it. On a tracked catalog `compact` exited 0 with ` M catalog.A.duckdb` and ` D
    catalog.duckdb`; and `compact` STOPS a running daemon first, defeating the very remedy the
    refusal names. L95: the check runs at the top of `compact` (before it pings or stops the
    daemon) and in `migrate-to-duckdb` before it writes. (The census half -- keyed on the
    resource -- lives in `tests/test_bug212_r4_red.py`.)
s-1 (SKETCHY). In the same `rmx save-state`, a refused memory bridge printed `memory bridge
    FAILED` on stdout and exited 0 -- the sibling of the promote that L82 made loud.
MEH (all taken in r5, L95):
    m-3 MCP `rmx_save_state` replied SUCCESS with `promoted: {"error"}` while the CLI exits 1.
    m-4 a refused `change-subject` had already switched the session's STM subject, and its
        line did not say so; the next promote files under a subject the store does not hold.
    m-5 `init` / `partition drop` took the in-process route on `daemon.ping` false -- a busy
        daemon (alive, not answering) is not an absent one (`local_write`'s own precondition).
    Y2 / Y5b / Y5c (and Y7, in the r4 file): behaviours r4 shipped and a probe verified, that
        no test held -- each is a GUARD here, proven by its mutation, not a RED.

Everything is real: git, the CLI (a console-script-shaped entry file), the MCP stdio server, a
throwaway daemon, the store. Stand-in: the registered rmx-lookalike process
(`tests/test_plan2_remedy.rmx_lookalike_process`) as the busy daemon's pid.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import shutil
from pathlib import Path

import pytest

from refmatrix import daemon as dm
from refmatrix import store as store_mod
from refmatrix.store import WRITER_CATALOG_FILES, Store
from tests.test_bridge_move_safety_r1 import absolute_pythonpath
from tests.test_bug212_hooks_in_worktrees import TRACEBACK, Repo, _base_env, _entry, _quiet
from tests.test_bug212_r1_remedy import (  # noqa: F401 -- `tracked_repo` is used by name
    _refusal_head, _refusal_lines, _status_refmatrix_catalogs, _target_catalog, tracked_repo,
)
from tests.test_bug212_r4_red import (  # noqa: F401 -- `ignored_store_repo` is used by name
    EMPTY_PARTITION, _PROMOTE_PROBE, _changed, _cli, _digests, _errors, ignored_store_repo,
)
from tests.test_plan2_remedy import rmx_lookalike_process


def _text(r: subprocess.CompletedProcess) -> str:
    return f"exit {r.returncode}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"


def _one_refusal_line(stderr: str, store: Path) -> list[str]:
    """`Error:` lines carrying a refusal head for SOME catalog file of `store` (for the cases
    where which slot is the target depends on the daemon's rotation): `refusing to open
    <store>/<file> read-write in-process:`, with both remedies."""
    out = []
    for ln in stderr.splitlines():
        low = ln.lower()
        if (ln.startswith("Error:") and f"refusing to open {store}/" in ln
                and " read-write in-process:" in ln
                and ("untrack" in low or "rm --cached" in low) and "daemon" in low):
            out.append(ln)
    return out


# =============================================================================================
# b-1: `rmx compact` and `rmx migrate-to-duckdb` refuse a git-tracked catalog
# =============================================================================================

def _compact_leftovers(store: Path) -> list[str]:
    return sorted(p.name for p in store.iterdir()
                  if p.name == "catalog-export" or p.name.endswith((".new.duckdb", ".bloat",
                                                                     ".legacy-bloat")))


@pytest.mark.timeout(300)
def test_compact_refuses_a_git_tracked_catalog(tracked_repo):
    """b-1 (i): `rmx compact --no-keep-backup`, no daemon, a repo that commits its catalog. One
    `Error:` line `refusing to open <full writer slot> read-write in-process: ...`, exit
    non-zero, catalog bytes unchanged, `git status` clean (at 03d7b27: exit 0, ` M
    catalog.A.duckdb` and ` D catalog.duckdb`), and no compaction leftovers."""
    repo, layout = tracked_repo
    assert not dm.ping(repo.store), "fixture: a daemon answers"
    before = _digests(repo.store)
    r = _cli(repo, ["compact", "--no-keep-backup"])
    text = _text(r)
    changed = _changed(before, _digests(repo.store))
    status = _status_refmatrix_catalogs(repo.proj)
    assert TRACEBACK not in r.stderr, f"[{layout}] compact crashed\n{text}"
    assert not changed and status == "", (
        f"[{layout}] `rmx compact` rewrote the git-tracked catalog {changed} (exit "
        f"{r.returncode})\ngit status:\n{status}\n{text}")
    assert r.returncode != 0, f"[{layout}] `rmx compact` on a tracked catalog exited 0\n{text}"
    target = repo.store / _target_catalog(layout)
    errs = _errors(r.stderr)
    assert len(errs) == 1 and _refusal_lines(r.stderr, target) == errs, \
        f"[{layout}] expected ONE `Error:` line `{_refusal_head(target)} ...`; got {errs}\n{text}"
    assert not _compact_leftovers(repo.store), \
        f"[{layout}] compact left {_compact_leftovers(repo.store)}"


@pytest.mark.timeout(300)
def test_compact_refuses_before_it_stops_a_running_daemon(tracked_repo, monkeypatch):
    """b-1 (ii): with a daemon running, `rmx compact` on a tracked catalog refuses BEFORE it
    pings or stops the daemon -- the daemon the refusal names as the remedy is still the same
    process afterwards (at 03d7b27 compact stops it, compacts in-process, and spawns a new
    one)."""
    repo, layout = tracked_repo
    monkeypatch.setenv("PYTHONPATH", absolute_pythonpath(os.environ.get("PYTHONPATH")))
    assert len(str(dm.socket_path(repo.store))) < 100, dm.socket_path(repo.store)
    pid = dm.spawn_daemon_subprocess(repo.store, watch_root=[])
    assert pid and dm.ping(repo.store), "fixture: the daemon did not come up"
    pid_before = dm.read_pid(repo.store)
    assert pid_before, "fixture: no daemon pid file"
    r = _cli(repo, ["compact", "--no-keep-backup"])
    text = _text(r)
    pid_after = dm.read_pid(repo.store)
    assert dm.ping(repo.store) and pid_after == pid_before, (
        f"[{layout}] `rmx compact` on a tracked catalog stopped the running daemon (pid "
        f"{pid_before} -> {pid_after}, answering={dm.ping(repo.store)})\n{text}")
    assert TRACEBACK not in r.stderr, f"[{layout}] compact crashed\n{text}"
    assert r.returncode != 0, f"[{layout}] `rmx compact` exited 0\n{text}"
    errs = _errors(r.stderr)
    assert len(errs) == 1 and _one_refusal_line(r.stderr, repo.store) == errs, \
        f"[{layout}] expected ONE refusal `Error:` line for a catalog under {repo.store}; " \
        f"got {errs}\n{text}"
    assert not _compact_leftovers(repo.store), \
        f"[{layout}] compact left {_compact_leftovers(repo.store)}"


@pytest.fixture
def sqlite_tracked_repo():
    """A repo whose store holds a SQLite `catalog.db` (the source `migrate-to-duckdb` reads)
    AND a DuckDB `catalog.duckdb` (the destination `--overwrite` replaces), both COMMITTED.
    No daemon. Short resolved `/tmp` root."""
    base = Path(tempfile.mkdtemp(prefix="b212q-", dir="/tmp")).resolve()
    r = Repo(base)
    try:
        r.proj.mkdir()
        _quiet(r.proj, r, "init", "-q", "--template=", "-b", "main")
        r.store.mkdir()
        s = Store(r.store, backend="sqlite")
        s.init()
        s.add_concept("bug212_r5_sqlite")
        s.close()
        d = Store(r.store, backend="duckdb")
        d.init()
        d.close()
        for name in ("catalog.db", "catalog.duckdb"):
            assert (r.store / name).is_file(), f"fixture: no {name}: {list(r.store.iterdir())}"
        _quiet(r.proj, r, "add", "-A")
        _quiet(r.proj, r, "commit", "-q", "-m", "c0 (sqlite + duckdb catalogs committed)")
        assert set(store_mod.git_tracked_catalogs(r.store)) >= {"catalog.db", "catalog.duckdb"}
        assert _status_refmatrix_catalogs(r.proj) == "", "fixture: catalogs dirty"
        yield r
    finally:
        dm.stop_daemon(r.store)
        shutil.rmtree(base, ignore_errors=True)


@pytest.mark.timeout(300)
def test_migrate_to_duckdb_overwrite_refuses_a_git_tracked_catalog(sqlite_tracked_repo):
    """b-1 (iii): `rmx migrate-to-duckdb --overwrite` on a repo that commits its catalogs
    refuses BEFORE it unlinks and rebuilds `catalog.duckdb`: one `Error:` line naming that
    destination, exit non-zero, bytes unchanged, `git status` clean."""
    repo = sqlite_tracked_repo
    before = _digests(repo.store)
    r = _cli(repo, ["migrate-to-duckdb", "--overwrite"])
    text = _text(r)
    changed = _changed(before, _digests(repo.store))
    status = _status_refmatrix_catalogs(repo.proj)
    assert TRACEBACK not in r.stderr, f"migrate-to-duckdb crashed\n{text}"
    assert not changed and status == "", (
        f"`rmx migrate-to-duckdb --overwrite` rewrote the git-tracked catalog {changed} (exit "
        f"{r.returncode})\ngit status:\n{status}\n{text}")
    assert r.returncode != 0, f"`rmx migrate-to-duckdb --overwrite` exited 0\n{text}"
    target = repo.store / "catalog.duckdb"
    errs = _errors(r.stderr)
    assert len(errs) == 1 and _refusal_lines(r.stderr, target) == errs, \
        f"expected ONE `Error:` line `{_refusal_head(target)} ...`; got {errs}\n{text}"


# =============================================================================================
# s-1: a refused memory bridge in save-state is loud (the L82 sibling)
# =============================================================================================

@pytest.mark.timeout(300)
def test_save_state_whose_memory_bridge_is_refused_says_so_on_stderr_and_exits_non_zero(
        tracked_repo):
    """s-1 (L95): a real `rmx save-state --no-promote` (lint off; the bridge ON, as
    `/save-state` runs it) on a tracked catalog, no daemon. The handoff is written; the memory
    bridge (`ingest-gmd --as-memory` of the memory dir) is refused -- and that refusal is on
    STDERR with a non-zero exit. At 03d7b27: `memory bridge FAILED ...` on stdout, exit 0."""
    from refmatrix import stm
    repo, layout = tracked_repo
    assert not dm.ping(repo.store), "fixture: a daemon answers"
    session = "bug212-r5-bridge"
    stm.Stm(repo.store, session).record("note", "a focus event for the bug-212 r5 bridge probe")
    memdir = repo.base / "memdir"
    memdir.mkdir()
    before = _digests(repo.store)
    r = _cli(repo, ["save-state", "-s", session, "--memory-dir", str(memdir), "--no-promote",
                    "--no-lint", "-m", "bug-212 r5 bridge probe"])
    text = _text(r)
    changed = _changed(before, _digests(repo.store))
    assert TRACEBACK not in r.stderr, f"[{layout}] save-state crashed\n{text}"
    assert not changed and _status_refmatrix_catalogs(repo.proj) == "", \
        f"[{layout}] save-state's bridge wrote the git-tracked catalog {changed}\n{text}"
    assert sorted(memdir.rglob("savestate_*.md")), \
        f"[{layout}] save-state wrote no handoff file under {memdir}\n{text}"
    head = _refusal_head(repo.store / _target_catalog(layout))
    assert any(head in ln for ln in r.stderr.splitlines()), \
        f"[{layout}] the bridge refusal (`{head} ...`) is not on stderr\n{text}"
    assert r.returncode != 0, \
        f"[{layout}] save-state exited 0 although its memory bridge was refused\n{text}"


# =============================================================================================
# m-3: MCP `rmx_save_state` reports a failed promote as an error, like the CLI's exit 1
# =============================================================================================

def _mcp(repo: Repo, cwd: Path, calls: list[tuple[str, dict]]) -> tuple[dict, str]:
    """Run `rmx mcp` with `initialize`, the tool calls (ids 2..), and a trailing `ping`;
    return {id: reply} and the run's text."""
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}]
    for i, (name, args) in enumerate(calls, start=2):
        msgs.append({"jsonrpc": "2.0", "id": i, "method": "tools/call",
                     "params": {"name": name, "arguments": args}})
    msgs.append({"jsonrpc": "2.0", "id": 99, "method": "ping"})
    r = subprocess.run([sys.executable, str(_entry(repo.base)), "mcp"], cwd=str(cwd),
                       env=_base_env(), input="".join(json.dumps(m) + "\n" for m in msgs),
                       capture_output=True, text=True, timeout=240)
    replies = {}
    for ln in r.stdout.splitlines():
        try:
            m = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if isinstance(m, dict) and "id" in m:
            replies[m["id"]] = m
    return replies, _text(r)


@pytest.mark.timeout(300)
def test_mcp_save_state_with_a_refused_promote_is_an_error_reply(tracked_repo):
    """m-3 (L95): MCP `rmx_save_state` (no daemon, tracked catalog, sync and lint off) whose
    promote is refused replies `isError` carrying the refusal -- the CLI's exit 1 for the same
    result -- and the handoff is still written. At 03d7b27 the reply is a SUCCESS whose
    `promoted` field holds the error as data."""
    from refmatrix import stm
    repo, layout = tracked_repo
    assert not dm.ping(repo.store), "fixture: a daemon answers"
    session = "bug212-r5-mcp-save"
    stm.Stm(repo.store, session).record("note", "a focus event for the bug-212 r5 MCP probe")
    memdir = repo.base / "memdir"
    memdir.mkdir()
    before = _digests(repo.store)
    replies, text = _mcp(repo, repo.proj, [("rmx_save_state", {
        "session": session, "memory_dir": str(memdir), "sync": False, "lint": False,
        "message": "bug-212 r5 MCP probe"})])
    assert 2 in replies and 99 in replies, f"the MCP server stopped answering\n{text}"
    res = replies[2].get("result") or {}
    body = " ".join(c.get("text", "") for c in res.get("content", []))
    assert _changed(before, _digests(repo.store)) == [], \
        f"[{layout}] MCP save-state's promote wrote the tracked catalog: {body!r}"
    assert sorted(memdir.rglob("savestate_*.md")), \
        f"[{layout}] MCP save-state wrote no handoff under {memdir}: {body!r}"
    head = _refusal_head(repo.store / _target_catalog(layout))
    assert res.get("isError") is True and head in body, (
        f"[{layout}] MCP rmx_save_state with a refused promote did not reply as an error "
        f"carrying the refusal: isError={res.get('isError')} body={body[:600]!r}")


# =============================================================================================
# m-4: a refused change-subject leaves the STM subject as it was, and says so
# =============================================================================================

@pytest.mark.timeout(300)
def test_a_refused_change_subject_leaves_the_stm_subject_unchanged_and_says_so(tracked_repo):
    """m-4 (L95): the session already has an STM subject. `rmx focus change-subject <new>` is
    refused (no daemon, tracked catalog): the STM subject is STILL the old one, and the one
    `Error:` line carries the refusal and says the subject was not changed. At 03d7b27 the STM
    subject switches to <new> before the store write is refused."""
    from refmatrix import stm
    repo, layout = tracked_repo
    assert not dm.ping(repo.store), "fixture: a daemon answers"
    session = "bug212-r5-subject"
    stm.Stm(repo.store, session).set_subject("bug212 r5 prior subject")
    before = _digests(repo.store)
    r = _cli(repo, ["focus", "change-subject", "bug212 r5 new subject", "-s", session])
    text = _text(r)
    now = (stm.Stm(repo.store, session).get_subject() or {}).get("label")
    assert TRACEBACK not in r.stderr, f"[{layout}] change-subject crashed\n{text}"
    assert _changed(before, _digests(repo.store)) == [], f"[{layout}] the catalog changed\n{text}"
    assert now == "bug212 r5 prior subject", (
        f"[{layout}] a refused change-subject switched the STM subject to {now!r}: the next "
        f"promote would file under a subject the store does not hold\n{text}")
    assert r.returncode != 0, f"[{layout}] the refused change-subject exited 0\n{text}"
    errs = _errors(r.stderr)
    target = repo.store / _target_catalog(layout)
    assert len(errs) == 1 and _refusal_head(target) in errs[0], \
        f"[{layout}] expected ONE `Error:` line `{_refusal_head(target)} ...`; got {errs}\n{text}"
    low = errs[0].lower()
    assert "subject" in low and any(w in low for w in ("unchanged", "not changed", "not set",
                                                         "kept")), \
        f"[{layout}] the refusal does not say the subject was left unchanged: {errs[0]!r}"


# =============================================================================================
# m-5: a busy daemon is not an absent one -- init / partition drop do not open in-process
# =============================================================================================

@pytest.fixture
def busy_store(ignored_store_repo):
    """`ignored_store_repo` (catalog IGNORED, so the tracked-catalog check passes and only the
    busy gate can stop the write) with an empty partition `EMPTY_PARTITION`, and a BUSY daemon:
    the pid file names a live rmx-lookalike process (`discovery.daemon_status` classifies a
    live rmx pid with no answering socket as busy) that never answers."""
    repo = ignored_store_repo
    s = Store(repo.store)
    try:
        with s.with_partition(EMPTY_PARTITION):
            pass
    finally:
        s.close()
    proc = rmx_lookalike_process()
    try:
        dm.pid_path(repo.store).write_text(str(proc.pid))
        from refmatrix import discovery
        st = discovery.daemon_status(repo.store, retries=0)
        assert st.get("busy") and not st.get("up"), f"fixture: not a busy daemon: {st}"
        yield repo
    finally:
        proc.kill()
        proc.wait()
        dm.pid_path(repo.store).unlink(missing_ok=True)


def _partitions(store: Path) -> set[str]:
    s = Store(store, read_only=True)
    try:
        return {r[0] for r in s._connect().execute("SELECT name FROM partitions").fetchall()}
    finally:
        s.close()


@pytest.mark.timeout(300)
@pytest.mark.parametrize("cmd", ["init", "partition-drop"])
def test_init_and_partition_drop_refuse_the_in_process_route_under_a_busy_daemon(busy_store,
                                                                                 cmd):
    """m-5 (L95): the daemon is alive but not answering. `rmx init` and `rmx partition drop`
    must not take the in-process route (ping false is not "absent"; `local_write`'s own
    precondition is `VerbAbsentError` only): one `Error:` line naming the busy daemon, exit
    non-zero, catalog bytes unchanged, the partition still registered. At 03d7b27 both open
    the writer catalog in-process and exit 0."""
    repo = busy_store
    before = _digests(repo.store)
    argv = (["init", "--no-hooks", "--no-agents"] if cmd == "init"
            else ["partition", "drop", EMPTY_PARTITION, "-y"])
    r = _cli(repo, argv)
    text = _text(r)
    assert TRACEBACK not in r.stderr, f"`rmx {' '.join(argv)}` crashed\n{text}"
    assert r.returncode != 0, \
        f"`rmx {' '.join(argv)}` took the in-process route under a busy daemon (exit 0)\n{text}"
    assert _changed(before, _digests(repo.store)) == [], \
        f"`rmx {' '.join(argv)}` wrote the catalog under a busy daemon\n{text}"
    if cmd == "partition-drop":
        assert EMPTY_PARTITION in _partitions(repo.store), \
            f"the partition was dropped under a busy daemon\n{text}"
    errs = _errors(r.stderr)
    assert len(errs) == 1 and "busy" in errs[0].lower(), \
        f"expected ONE `Error:` line naming the busy daemon; got {errs}\n{text}"


# =============================================================================================
# GUARDS (pass at 03d7b27; each is proven by the ch-bsd r4 mutation it kills)
# =============================================================================================

@pytest.mark.timeout(300)
def test_a_deleted_tracked_catalog_is_refused_and_not_recreated(tracked_repo):
    """GUARD for Y2 (`local_write` checks only when the catalog file exists): every writer
    catalog git tracks is deleted from the worktree (` D`). `rmx init` -- a `create=True`
    caller -- is still refused (git lists a tracked file even when it is deleted), and no
    catalog file is re-created; `git status` is exactly what it was."""
    repo, layout = tracked_repo
    assert not dm.ping(repo.store), "fixture: a daemon answers"
    for name in WRITER_CATALOG_FILES:
        (repo.store / name).unlink(missing_ok=True)
    status_before = _status_refmatrix_catalogs(repo.proj)
    assert status_before and all(ln.startswith(" D") for ln in status_before.splitlines()), \
        f"fixture: not every catalog shows as deleted:\n{status_before}"
    r = _cli(repo, ["init", "--no-hooks", "--no-agents"])
    text = _text(r)
    recreated = sorted(n for n in WRITER_CATALOG_FILES if (repo.store / n).exists())
    assert not recreated, f"[{layout}] `rmx init` re-created the tracked {recreated}\n{text}"
    assert _status_refmatrix_catalogs(repo.proj) == status_before, \
        f"[{layout}] git status changed\n{text}"
    assert TRACEBACK not in r.stderr and r.returncode != 0, text
    errs = _errors(r.stderr)
    assert len(errs) == 1 and _one_refusal_line(r.stderr, repo.store) == errs, \
        f"[{layout}] expected ONE refusal `Error:` line; got {errs}\n{text}"


@pytest.fixture
def no_catalog_store():
    """A project dir `proj` with an EMPTY `.refmatrix/` (no catalog yet), in no git repository,
    no daemon -- the bootstrap state the `create=True` fallbacks exist for."""
    base = Path(tempfile.mkdtemp(prefix="b212b-", dir="/tmp")).resolve()
    r = Repo(base)
    try:
        r.proj.mkdir()
        r.store.mkdir()
        probe = subprocess.run(["git", "-C", str(r.proj), "rev-parse", "--git-dir"],
                               env=_base_env(), capture_output=True, text=True)
        assert probe.returncode != 0, f"fixture: {r.proj} is inside a git repo"
        assert not any((r.store / n).exists() for n in WRITER_CATALOG_FILES)
        yield r
    finally:
        dm.stop_daemon(r.store)
        shutil.rmtree(base, ignore_errors=True)


def _memory_rows(store: Path, like: str) -> int:
    s = Store(store, read_only=True)
    try:
        return int(s._connect().execute(
            "SELECT count(*) FROM entities WHERE kind = 'memory' AND name LIKE ?",
            (like,)).fetchone()[0])
    finally:
        s.close()


@pytest.mark.timeout(300)
def test_the_mcp_memory_add_fallback_creates_a_missing_catalog(no_catalog_store):
    """GUARD for Y5b (the MCP `rmx_memory_add` fallback with `create=False`): on a store with
    no catalog yet and no daemon, the first memory still lands -- the catalog is created and
    holds it (the documented bootstrap exception)."""
    repo = no_catalog_store
    replies, text = _mcp(repo, repo.proj, [("rmx_memory_add", {
        "name": "bug212_r5_boot", "content": "first memory on a fresh store (bug-212 r5)"})])
    assert 2 in replies, f"the MCP server stopped answering\n{text}"
    res = replies[2].get("result") or {}
    body = " ".join(c.get("text", "") for c in res.get("content", []))
    assert res.get("isError") is not True and '"id"' in body, \
        f"MCP rmx_memory_add on a store with no catalog failed: {body!r}"
    assert any((repo.store / n).exists() for n in WRITER_CATALOG_FILES), \
        f"no catalog was created under {repo.store}"
    assert _memory_rows(repo.store, "bug212_r5_boot") == 1, "the memory row is not there"


@pytest.mark.timeout(300)
def test_the_save_state_promote_creates_a_missing_catalog(no_catalog_store):
    """GUARD for Y5c (the save-state promote with `create=False`): on a store with no catalog
    yet and no daemon, `handoff._promote_digest` returns an `id`, and the digest row exists."""
    repo = no_catalog_store
    probe = repo.base / "promote_probe.py"
    probe.write_text(_PROMOTE_PROBE, encoding="utf-8")
    r = subprocess.run([sys.executable, str(probe), str(repo.store)], cwd=str(repo.proj),
                       env=_base_env(), capture_output=True, text=True, timeout=240)
    text = _text(r)
    assert r.returncode == 0, f"the promote probe itself failed\n{text}"
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert "error" not in out and out.get("id"), \
        f"the promote on a store with no catalog failed: {out}"
    assert _memory_rows(repo.store, "focus_summary_%") == 1, "the digest row is not there"
