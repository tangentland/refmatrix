"""bug-212 remedy r1: the RED tests for the ch-bsd r1 findings b-1, s-1, m-1, m-2, m-3
(report `workflow/bullshit/2026-11-11-1342-bug212-r1-b024a95.md`, DIRTY 8, merge NO-GO until b-1).

WHY each group exists (2026-11-11 audit of b024a95; brief `workflow/agents/red-212r1.md`):

b-1 (BLOCKER). The GREEN store gate is FILE PRESENCE: exit 0 unless a `store.WRITER_CATALOG_FILES`
    name exists under `$ROOT/.refmatrix/`. Fleet repos COMMIT those files (cliquet: catalog.A /
    B / duckdb + `active` on main; atldb: all three on its branch; prep_prolific: catalog.duckdb
    on master), so every worktree and clone of them passes the gate, and the hook's in-process
    `rmx sync` writes the tracked catalog: `git status` shows ` M .refmatrix/catalog.duckdb`,
    `git worktree remove` refuses, a `commit -a` puts the mutated binary into history. The old
    RED fixture asserted a CLAUDE.md-only layout, so it could not see this. The remedy (lead,
    2026-11-13): the gate passes ONLY on a live daemon socket (git cannot track a socket) OR a
    catalog git does NOT track. bug-214 untracked the fleet's files on 2026-11-13 on the
    checked-out branches only; their trunks still track them until merged, so the gate must
    hold on its own.
s-1. A vanished cwd is still a raw traceback once `REFMATRIX_ROOT` is set -- the remedy the
    GREEN error text itself recommends ("cd to a project, or set REFMATRIX_ROOT") -- because
    `discovery.partition_marker` reads `Path.cwd()` unguarded. The guard covered cli.py only;
    `discovery` (`_cwd_root`, `partition_marker`), `sync` (`sync_since`, `_sync_paths`),
    `mcp._resolve_root` and `cctree.resolve_path` still read the cwd raw. The fix is ONE shared
    cwd helper, so every entry point that reads the cwd is driven here.
m-1. The cwd-less telemetry row is a deliverable with no test (mutations A and B survived).
m-2. The daemon-down + launchd-installed branch of `rmx sync --since` catches only
    `RuntimeError`; `GitRefError`'s base class was unpinned (mutation D survived).
a2 (lead decision, 2026-11-13). The socket half of that gate cannot tell a live daemon from a
    socket file a crashed daemon left; the CLI then syncs in-process into the tracked catalog.
    So an in-process sync whose target catalog git tracks refuses, loudly, catalog untouched.
m-3. A ROOT commit (no parent) makes post-commit run `rmx sync --since HEAD~1`, which git
    rejects: a loud "failure" that indexes nothing. It should diff against the empty tree.

Everything is real: git, the GENERATED hook bodies (installed by `hooks._install_git_hooks` into
tmp repos under a short `/tmp` root), the store, the sync, a throwaway daemon. Stand-ins: the
recording `rmx` PATH shim from `tests/test_bug212_hooks_in_worktrees.py` (registered,
`external`), and for m-2 a placeholder plist FILE in the sandbox's LaunchAgents dir (registered,
`external`): `launchctl.is_installed` is a file-existence check, so the real function answers
True; nothing is loaded into launchd.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from refmatrix import daemon as dm
from refmatrix import hooks as hooks_mod
from refmatrix import launchctl
from refmatrix.store import WRITER_CATALOG_FILES, Store
from tests.test_bridge_move_safety_r1 import (  # noqa: F401 -- fixtures are used by name
    _commit, _init_repo, absolute_pythonpath, gitproj_inproc,
)
from tests.test_bug212_hooks_in_worktrees import (
    CLAUDE_MD, FAILED_LINE, TRACEBACK, Repo, _assert_clean_since_error, _base_env, _calls,
    _entry, _git_says, _hooked, _hooks_ran, _quiet, _store_has_path, _store_paths_under,
    _write_shim,
)


# =============================================================================================
# b-1: a repo that TRACKS its catalog files
# =============================================================================================

# Two committed layouts, both seen in the fleet survey of 2026-11-11 (read-only):
#   slots  -- catalog.A.duckdb + catalog.B.duckdb + `active` + the legacy catalog.duckdb
#             (cliquet on main, atldb on its branch);
#   legacy -- catalog.duckdb only (prep_prolific on master).
LAYOUTS = ["slots", "legacy"]


def _status_refmatrix(co: Path) -> str:
    """`git status` of the checkout's `.refmatrix/`, untracked files included -- empty when the
    hook wrote nothing there."""
    r = subprocess.run(["git", "-C", str(co), "status", "--porcelain", "--untracked-files=all",
                        "--", ".refmatrix"], env=_base_env(), capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0, f"git status: {r.stdout}{r.stderr}"
    return r.stdout


def _tracked_catalogs(co: Path) -> list[str]:
    r = subprocess.run(["git", "-C", str(co), "ls-files", "--",
                        *[f".refmatrix/{n}" for n in WRITER_CATALOG_FILES]],
                       env=_base_env(), capture_output=True, text=True, timeout=60)
    return sorted(r.stdout.split())


@pytest.fixture(params=LAYOUTS)
def tracked_repo(request):
    """A git repo `proj` on `main` whose `.refmatrix/` is a real store AND committed: the
    catalog file(s) of the layout are tracked (nothing under `.refmatrix/` is ignored, the way
    a repo that once ran `git add -A` looks). Branch `other` is one commit ahead (adds
    `other.py`); the GENERATED hooks are installed; the recording shim is on PATH for hooked
    ops. No daemon: a test that wants one starts it. Short resolved `/tmp` root."""
    layout = request.param
    base = Path(tempfile.mkdtemp(prefix="b212t-", dir="/tmp")).resolve()
    r = Repo(base)
    try:
        r.proj.mkdir()
        _quiet(r.proj, r, "init", "-q", "--template=", "-b", "main")
        (r.proj / "README.md").write_text("r\n", encoding="utf-8")
        r.store.mkdir()
        (r.store / "CLAUDE.md").write_text(CLAUDE_MD, encoding="utf-8")
        s = Store(r.store)
        s.init()
        s.close()
        legacy = r.store / "catalog.duckdb"
        assert legacy.is_file(), f"fixture: Store.init made no catalog.duckdb: {list(r.store.iterdir())}"
        if layout == "slots":
            shutil.copyfile(legacy, r.store / "catalog.A.duckdb")
            shutil.copyfile(legacy, r.store / "catalog.B.duckdb")
            (r.store / "active").write_text("A\n", encoding="utf-8")
        _quiet(r.proj, r, "add", "-A")
        _quiet(r.proj, r, "commit", "-q", "-m", "c0 (the store committed)")
        want = (["catalog.A.duckdb", "catalog.B.duckdb", "catalog.duckdb"]
                if layout == "slots" else ["catalog.duckdb"])
        assert _tracked_catalogs(r.proj) == [f".refmatrix/{n}" for n in want], \
            f"fixture: tracked catalogs {_tracked_catalogs(r.proj)}"
        _quiet(r.proj, r, "checkout", "-q", "-b", "other")
        (r.proj / "other.py").write_text("def other():\n    return 1\n", encoding="utf-8")
        _quiet(r.proj, r, "add", "-A")
        _quiet(r.proj, r, "commit", "-q", "-m", "c1 on other")
        _quiet(r.proj, r, "checkout", "-q", "main")
        hooks_mod._install_git_hooks(r.proj, apply=True, force=True)
        for name in hooks_mod.GIT_HOOK_SCRIPTS:
            assert (r.proj / ".git" / "hooks" / name).exists(), f"hook not installed: {name}"
        _write_shim(r)
        assert _status_refmatrix(r.proj) == "", \
            f"fixture: the main checkout's .refmatrix/ is dirty before any hook ran:\n" \
            f"{_status_refmatrix(r.proj)}"
        yield r, layout
    finally:
        dm.stop_daemon(r.store)
        shutil.rmtree(base, ignore_errors=True)


def _tracked_checkout(repo: Repo, where: str) -> Path:
    """A second checkout of `main` (hooks OFF while it is made): its `.refmatrix/` holds the
    COMMITTED catalog files, so a file-presence gate passes there."""
    if where == "worktree":
        co = repo.base / "wt"
        _quiet(repo.proj, repo, "worktree", "add", "-q", "-b", "feature", str(co), "main")
    else:
        co = repo.base / "clone"
        r = subprocess.run(["git", "clone", "-q", "--template=", str(repo.proj), str(co)],
                           env=_base_env(), capture_output=True, text=True, timeout=120)
        assert r.returncode == 0, f"clone: {r.stdout}{r.stderr}"
        hooks_mod._install_git_hooks(co, apply=True, force=True)
    present = [n for n in WRITER_CATALOG_FILES if (co / ".refmatrix" / n).exists()]
    assert present, f"fixture: the {where} has no committed catalog file -- not the b-1 layout"
    assert not (co / ".refmatrix" / dm.SOCKET_NAME).exists(), \
        f"fixture: the {where} has a daemon socket"
    assert _status_refmatrix(co) == "", f"fixture: the {where} is dirty before the op"
    return co


def _op(hook: str, repo: Repo, co: Path, where: str) -> subprocess.CompletedProcess:
    other = "other" if where == "worktree" else "origin/other"
    if hook == "post-commit":
        (co / f"new_in_{where}.py").write_text("def new():\n    return 2\n", encoding="utf-8")
        _quiet(co, repo, "add", f"new_in_{where}.py")
        return _hooked(co, repo, "commit", "-q", "-m", f"commit in the {where}")
    if hook == "post-checkout":
        return _hooked(co, repo, "checkout", "-q", "other")        # a REAL branch switch
    if hook == "post-merge":
        return _hooked(co, repo, "merge", "-q", "--no-edit", other)
    assert hook == "post-rewrite"
    return _hooked(co, repo, "commit", "-q", "--amend", "-m", f"c0 amended in the {where}")


@pytest.mark.timeout(300)
@pytest.mark.parametrize("where", ["worktree", "clone"])
@pytest.mark.parametrize("hook", sorted(hooks_mod.GIT_HOOK_SCRIPTS))
def test_a_checkout_of_a_repo_that_tracks_its_catalog_runs_no_sync(tracked_repo, hook, where):
    """b-1: a worktree or clone carries the committed catalog and no daemon. The hook must not
    run `rmx` there, must leave `git status` clean of `.refmatrix/`, and (worktree) a plain
    `git worktree remove` must succeed."""
    repo, layout = tracked_repo
    co = _tracked_checkout(repo, where)
    r = _op(hook, repo, co, where)
    text = f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    assert r.returncode == 0, f"the git op itself failed\n{text}"
    assert f"hooks/{hook}" in _hooks_ran(repo), \
        f"fixture: git never ran {hook} (GIT_TRACE), so 'no rmx call' would prove nothing"
    status = _status_refmatrix(co)
    calls = _calls(repo)
    assert not calls, (f"[{layout}] {hook} in a {where} of a repo that TRACKS its catalog ran "
                       f"rmx: {calls}\ngit status .refmatrix/:\n{status}\n{text}")
    assert TRACEBACK not in r.stderr, f"{hook} in a {where} printed a raw traceback\n{text}"
    assert FAILED_LINE not in r.stderr, f"{hook} in a {where} printed a FAILED line\n{text}"
    assert status == "", (f"[{layout}] {hook} in a {where} left .refmatrix/ dirty (a tracked "
                          f"catalog written?):\n{status}")
    if where == "worktree":
        rm = _hooked(repo.proj, repo, "worktree", "remove", str(co))
        assert rm.returncode == 0, \
            f"[{layout}] plain `git worktree remove` refused after {hook}: {rm.stdout}{rm.stderr}"
        assert not co.exists(), "the worktree is still on disk after `git worktree remove`"


@pytest.mark.timeout(300)
@pytest.mark.parametrize("hook", ["post-commit", "post-checkout"])
def test_the_main_checkout_of_a_repo_that_tracks_its_catalog_runs_no_in_process_sync(
        tracked_repo, hook):
    """b-1, the main checkout: the catalog is tracked and NO daemon answers. An in-process sync
    would write the tracked binary (the remedy's gate: a live socket OR an untracked catalog;
    here there is neither), so the hook runs no `rmx` and `.refmatrix/` stays clean."""
    repo, layout = tracked_repo
    assert not dm.ping(repo.store), "fixture: a daemon answers"
    if hook == "post-commit":
        (repo.proj / "main_new.py").write_text("def main_new():\n    return 3\n",
                                                encoding="utf-8")
        _quiet(repo.proj, repo, "add", "main_new.py")
        r = _hooked(repo.proj, repo, "commit", "-q", "-m", "commit in the main checkout")
    else:
        r = _hooked(repo.proj, repo, "checkout", "-q", "other")
    text = f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    assert r.returncode == 0, f"the git op itself failed\n{text}"
    assert f"hooks/{hook}" in _hooks_ran(repo), f"fixture: git never ran {hook} (GIT_TRACE)"
    status = _status_refmatrix(repo.proj)
    assert not _calls(repo), (f"[{layout}] {hook} in the main checkout (catalog tracked, no "
                              f"daemon) ran rmx: {_calls(repo)}\ngit status .refmatrix/:\n"
                              f"{status}\n{text}")
    assert status == "", f"[{layout}] {hook} left the main checkout's .refmatrix/ dirty:\n{status}"


@pytest.mark.timeout(300)
def test_a_repo_that_tracks_its_catalog_still_syncs_through_a_live_daemon(tracked_repo,
                                                                          monkeypatch):
    """GUARD (passes at HEAD): the socket half of the remedy's gate. With a live daemon the
    sync goes through it (no in-process write by the hook's process), so a repo that tracks its
    catalog is still kept fresh. A gate reduced to "untracked catalog only" fails this."""
    repo, layout = tracked_repo
    monkeypatch.setenv("PYTHONPATH", absolute_pythonpath(os.environ.get("PYTHONPATH")))
    assert len(str(dm.socket_path(repo.store))) < 100, dm.socket_path(repo.store)
    pid = dm.spawn_daemon_subprocess(repo.store, watch_root=[])
    assert pid and dm.ping(repo.store), "fixture: the daemon did not come up"
    path = repo.proj / "main_new.py"
    path.write_text("def main_new():\n    return 3\n", encoding="utf-8")
    _quiet(repo.proj, repo, "add", "main_new.py")
    r = _hooked(repo.proj, repo, "commit", "-q", "-m", "commit with the daemon up")
    text = f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    assert r.returncode == 0, f"the git op itself failed\n{text}"
    assert TRACEBACK not in r.stderr and FAILED_LINE not in r.stderr, text
    syncs = [c for c in _calls(repo) if c[1].startswith("sync")]
    assert syncs and all(Path(pwd).resolve() == repo.proj for pwd, _ in syncs), \
        f"[{layout}] post-commit with a live daemon (catalog tracked) ran no sync: " \
        f"{_calls(repo)}\n{text}"
    assert dm.stop_daemon(repo.store), "the daemon did not stop"
    assert _store_has_path(repo, path), \
        f"[{layout}] the daemon-routed sync did not index {path.name}\n{text}"


# =============================================================================================
# m-3: a root commit is synced against the empty tree, not reported as a failure
# =============================================================================================

@pytest.fixture
def fresh_repo():
    """A git repo with NO commit yet, a real (ignored) store, the generated hooks and the
    shim."""
    base = Path(tempfile.mkdtemp(prefix="b212f-", dir="/tmp")).resolve()
    r = Repo(base)
    try:
        r.proj.mkdir()
        _quiet(r.proj, r, "init", "-q", "--template=", "-b", "main")
        (r.proj / ".gitignore").write_text(".refmatrix/\n", encoding="utf-8")
        s = Store(r.store)
        s.init()
        s.close()
        hooks_mod._install_git_hooks(r.proj, apply=True, force=True)
        _write_shim(r)
        yield r
    finally:
        shutil.rmtree(base, ignore_errors=True)


@pytest.mark.timeout(300)
def test_a_root_commit_is_synced_not_reported_as_a_failure(fresh_repo):
    repo = fresh_repo
    path = repo.proj / "root_file.py"
    path.write_text("def root_file():\n    return 0\n", encoding="utf-8")
    _quiet(repo.proj, repo, "add", "-A")
    r = _hooked(repo.proj, repo, "commit", "-q", "-m", "the root commit")
    text = f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    assert r.returncode == 0, f"the root commit itself failed\n{text}"
    assert "hooks/post-commit" in _hooks_ran(repo), "fixture: git never ran post-commit"
    assert TRACEBACK not in r.stderr, f"post-commit on a root commit crashed\n{text}"
    assert FAILED_LINE not in r.stderr and "Error:" not in r.stderr, \
        f"post-commit on a root commit (no HEAD~1) reported a failure\n{text}\n" \
        f"rmx calls: {_calls(repo)}"
    assert [c for c in _calls(repo) if c[1].startswith("sync")], \
        f"post-commit on a root commit ran no sync (it must index the commit): {_calls(repo)}"
    assert _store_has_path(repo, path), \
        f"the root commit's {path.name} was not indexed\n{text}"


# =============================================================================================
# s-1: a vanished cwd is a clean error at EVERY entry point that reads the cwd
# =============================================================================================

def _vanished(argv: list[str], env: dict, stdin: "str | None" = None,
              timeout: int = 110) -> subprocess.CompletedProcess:
    """Run `argv` with its working directory already deleted: a shell `cd`s in, removes the
    dir, execs. The shape of a backgrounded hook outliving `git worktree remove`."""
    base = Path(tempfile.mkdtemp(prefix="b212c-", dir="/tmp")).resolve()
    try:
        gone = base / "gone"
        gone.mkdir()
        return subprocess.run(["/bin/sh", "-c", 'cd "$1" && rmdir "$1" && shift && exec "$@"',
                               "sh", str(gone), *argv], cwd=str(base), env=env, input=stdin,
                              capture_output=True, text=True, timeout=timeout)
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _says_cwd_gone(line: str) -> bool:
    low = line.lower()
    return "director" in low or "cwd" in low


@pytest.fixture
def named_store():
    """A throwaway store for `REFMATRIX_ROOT` -- the remedy the cwd error text recommends."""
    base = Path(tempfile.mkdtemp(prefix="b212s-", dir="/tmp")).resolve()
    root = base / "st" / ".refmatrix"
    s = Store(root)
    s.init()
    s.close()
    try:
        yield base, root
    finally:
        shutil.rmtree(base, ignore_errors=True)


CWD_ARGVS = [["sync", "--since", "HEAD~1"], ["stats"], ["grep", "foo"], ["context", "foo"],
             ["query", "kind:function"]]


@pytest.mark.timeout(120)
@pytest.mark.parametrize("argv", CWD_ARGVS, ids=lambda a: "-".join(a[:2]).replace("~", ""))
def test_a_vanished_cwd_with_refmatrix_root_set_is_a_clean_error(named_store, argv):
    """s-1: the cwd error says "cd to a project, or set REFMATRIX_ROOT". Set it, and the
    command must still not traceback: the partition is resolved from the cwd
    (`discovery.partition_marker`), and that cwd is gone -- a clean `Error:` naming it."""
    base, root = named_store
    entry = _entry(base)
    env = {**_base_env(), "REFMATRIX_ROOT": str(root)}
    r = _vanished([sys.executable, str(entry), *argv], env)
    text = f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    assert TRACEBACK not in r.stderr, \
        f"`rmx {' '.join(argv)}` (REFMATRIX_ROOT set) in a vanished cwd crashed with a raw " \
        f"traceback\n{text}"
    assert r.returncode != 0, f"`rmx {' '.join(argv)}` in a vanished cwd exited 0\n{text}"
    err = [ln for ln in r.stderr.splitlines() if ln.startswith("Error:")]
    assert any(_says_cwd_gone(ln) for ln in err), \
        f"`rmx {' '.join(argv)}`: no `Error:` line saying the working directory is gone\n{text}"


@pytest.mark.timeout(120)
@pytest.mark.parametrize("argv", [["cctree"], ["hub", "pause", "nosuch-bug212"]],
                         ids=["cctree", "hub-pause"])
def test_a_vanished_cwd_is_a_clean_error_outside_root_resolution(named_store, argv):
    """s-1: commands that read the cwd WITHOUT `cli._root()` -- `cctree.resolve_path` (no
    `--project`) and `discovery._cwd_root` (via `discover_roots`, reached by
    `hub pause <name>`). No `REFMATRIX_ROOT`. Never a traceback; one `Error:` line."""
    base, _root = named_store
    r = _vanished([sys.executable, str(_entry(base)), *argv], _base_env())
    text = f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    assert TRACEBACK not in r.stderr, \
        f"`rmx {' '.join(argv)}` in a vanished cwd crashed with a raw traceback\n{text}"
    assert r.returncode != 0, f"`rmx {' '.join(argv)}` in a vanished cwd exited 0\n{text}"
    assert [ln for ln in r.stderr.splitlines() if ln.startswith("Error:")], \
        f"`rmx {' '.join(argv)}` in a vanished cwd failed with no `Error:` line\n{text}"


@pytest.mark.timeout(120)
def test_an_mcp_tool_call_in_a_vanished_cwd_names_the_working_directory(named_store):
    """s-1: `mcp._resolve_root` reads the cwd when the call names no root/project and no
    `REFMATRIX_ROOT` is set. The dispatcher turns any exception into `isError`, so this is not
    a traceback -- but the text was `FileNotFoundError: [Errno 2] No such file or directory`,
    which names nothing. It must say the working directory is gone, and the server keeps
    serving."""
    base, _root = named_store
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": "rmx_query", "arguments": {"dsl": "kind:function"}}},
            {"jsonrpc": "2.0", "id": 3, "method": "ping"}]
    stdin = "".join(json.dumps(m) + "\n" for m in msgs)
    r = _vanished([sys.executable, str(_entry(base)), "mcp"], _base_env(), stdin=stdin)
    text = f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    assert TRACEBACK not in r.stderr, f"`rmx mcp` in a vanished cwd crashed\n{text}"
    replies = {}
    for ln in r.stdout.splitlines():
        try:
            msg = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if isinstance(msg, dict) and "id" in msg:
            replies[msg["id"]] = msg
    assert 2 in replies and 3 in replies, f"the MCP server stopped answering\n{text}"
    res = replies[2].get("result") or {}
    body = " ".join(c.get("text", "") for c in res.get("content", []))
    assert res.get("isError") is True, f"rmx_query in a vanished cwd did not fail\n{text}"
    assert _says_cwd_gone(body) and not body.startswith("FileNotFoundError"), \
        f"rmx_query in a vanished cwd failed without saying the working directory is gone: " \
        f"{body!r}"


_LIB_PROBE = r"""
import json, sys
from pathlib import Path
from refmatrix import sync
from refmatrix.store import Store
s = Store(Path(sys.argv[1]))
try:
    if sys.argv[2] == "sync_since":
        sync.sync_since(s, "HEAD")
    else:
        sync.sync_files(s, [sys.argv[3]])
except BaseException as e:
    print(json.dumps({"raised": type(e).__name__, "oserror": isinstance(e, OSError),
                      "msg": str(e)}))
else:
    print(json.dumps({"raised": None}))
finally:
    s.close()
"""


@pytest.mark.timeout(120)
@pytest.mark.parametrize("fn", ["sync_since", "sync_files"])
def test_sync_library_entries_in_a_vanished_cwd_raise_the_named_cwd_error(named_store, fn):
    """s-1: `sync.sync_since` (sync.py `project_root or Path.cwd()`) and `sync.sync_files` ->
    `_sync_paths` (the same default) are library entries the daemon ops also reach. With no
    `project_root` and the cwd gone they must raise the shared helper's error -- one that says
    the working directory is gone -- not a bare `FileNotFoundError` (an OSError naming no
    path)."""
    base, root = named_store
    probe = base / "probe.py"
    probe.write_text(_LIB_PROBE, encoding="utf-8")
    afile = base / "a.py"
    afile.write_text("def a():\n    return 1\n", encoding="utf-8")
    r = _vanished([sys.executable, str(probe), str(root), fn, str(afile)], _base_env())
    text = f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    assert r.returncode == 0, f"the probe itself failed\n{text}"
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["raised"] is not None, f"sync.{fn} in a vanished cwd raised nothing\n{text}"
    assert not out["oserror"] and _says_cwd_gone(out["msg"]), \
        f"sync.{fn} in a vanished cwd raised {out['raised']}: {out['msg']!r} -- not the named " \
        f"cwd error"


# =============================================================================================
# m-1: the cwd-less telemetry row is written, once, and says why
# =============================================================================================

@pytest.mark.timeout(120)
def test_a_cwd_less_run_writes_one_telemetry_row_naming_the_lost_cwd():
    """GUARD (passes at HEAD; proven by mutations A and B): `rmx version` in a vanished cwd,
    no `REFMATRIX_ROOT`, a fresh `RMX_HOME`: exactly one `cli.log` row there, `cwd` null,
    `cwd_error` naming the directory. Mutation A (the row filed through `_root()`, whose cwd
    error the pre-existing `except Exception: pass` swallows) drops the row silently."""
    from refmatrix.telemetry import CLI_LOG_NAME
    base = Path(tempfile.mkdtemp(prefix="b212m-", dir="/tmp")).resolve()
    try:
        home = base / "rmxhome"
        home.mkdir()
        env = {k: v for k, v in _base_env().items() if k != "REFMATRIX_NO_TELEMETRY"}
        env["RMX_HOME"] = str(home)
        gone_parent = Path(tempfile.mkdtemp(prefix="b212g-", dir="/tmp")).resolve()
        try:
            gone = gone_parent / "gone"
            gone.mkdir()
            r = subprocess.run(["/bin/sh", "-c", 'cd "$1" && rmdir "$1" && shift && exec "$@"',
                                "sh", str(gone), sys.executable, str(_entry(base)), "version"],
                               cwd=str(gone_parent), env=env, capture_output=True, text=True,
                               timeout=110)
        finally:
            shutil.rmtree(gone_parent, ignore_errors=True)
        text = f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
        assert r.returncode == 0, f"`rmx version` in a vanished cwd failed\n{text}"
        log = home / CLI_LOG_NAME
        rows = ([json.loads(ln) for ln in log.read_text(encoding="utf-8").splitlines()
                 if ln.strip()] if log.exists() else [])
        assert len(rows) == 1, f"expected exactly one cli.log row in RMX_HOME, got {rows}\n{text}"
        row = rows[0]
        assert row.get("argv") == ["version"], row
        assert row.get("cwd") is None, f"the cwd-less row carries a cwd: {row}"
        assert str(gone) in (row.get("cwd_error") or ""), \
            f"the cwd-less row's cwd_error does not name {gone}: {row}"
    finally:
        shutil.rmtree(base, ignore_errors=True)


# =============================================================================================
# m-2: the daemon-down + launchd-installed branch of `rmx sync --since`
# =============================================================================================

_PLIST = ('<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict>'
          '<key>Label</key><string>bug212-placeholder</string></dict></plist>\n')


@pytest.mark.timeout(300)
def test_sync_since_a_bad_ref_on_a_supervised_store_with_the_daemon_down_is_a_clean_error(
        gitproj_inproc):
    """GUARD (passes at HEAD; proven by mutation D, `GitRefError(Exception)`): no daemon, but
    the store is launchd-installed (`launchctl.is_installed` = the plist FILE exists; a
    placeholder in the sandbox's LaunchAgents dir, never loaded). That branch computes the
    changed paths itself and catches only `RuntimeError`. A control call with a GOOD ref proves
    the branch is the one that ran ("daemon down -- enqueued")."""
    base, proj, root = gitproj_inproc
    _init_repo(proj)
    _commit(proj, "c0")
    assert not dm.ping(root), "fixture: a daemon is up; this is the daemon-down leg"
    plist = launchctl.plist_path(root)
    sandbox = os.environ.get("RMX_SANDBOX_ROOT")
    assert sandbox and str(plist.resolve()).startswith(str(Path(sandbox).resolve())), \
        f"refusing: the plist path {plist} is outside the test sandbox {sandbox}"
    assert not plist.exists(), f"fixture: {plist} already exists"
    plist.parent.mkdir(parents=True, exist_ok=True)
    plist.write_text(_PLIST, encoding="utf-8")
    try:
        env = {**_base_env(), "REFMATRIX_ROOT": str(root)}
        entry = _entry(base)
        ctl = subprocess.run([sys.executable, str(entry), "sync", "--project-root", str(proj),
                              "--since", "HEAD"], cwd=str(proj), capture_output=True, text=True,
                             env=env, timeout=240)
        ctext = f"stdout:\n{ctl.stdout}\nstderr:\n{ctl.stderr}"
        assert ctl.returncode == 0 and "daemon down" in ctl.stdout, \
            f"fixture: the daemon-down + installed branch did not run for a good ref\n{ctext}"
        ref = "no-such-ref-bug212"
        says = _git_says(proj, ref)
        r = subprocess.run([sys.executable, str(entry), "sync", "--project-root", str(proj),
                            "--since", ref], cwd=str(proj), capture_output=True, text=True,
                           env=env, timeout=240)
        _assert_clean_since_error(r, ref, says, "daemon-down+launchd")
    finally:
        plist.unlink()


# =============================================================================================
# a2 (lead decision 2026-11-13): an in-process sync never writes a git-TRACKED catalog
# =============================================================================================
#
# The hook gate's socket half (`[ -S "$ROOT/.refmatrix/rmxd.sock" ]`) cannot tell a live daemon
# from a socket file a crashed daemon left behind. With no listener the CLI falls to an
# in-process sync and writes the tracked catalog -- b-1 again, behind the new gate. So the CLI
# itself refuses: an in-process `rmx sync` (plain and `--since`) whose target catalog git
# tracks fails with ONE `Error:` line naming the tracked file and the remedy (untrack it, or
# start the daemon), exit non-zero, catalog bytes unchanged.


def _catalog_digests(store: Path) -> dict[str, str]:
    return {n: hashlib.sha256((store / n).read_bytes()).hexdigest()
            for n in WRITER_CATALOG_FILES if (store / n).exists()}


def _target_catalog(layout: str) -> str:
    """The file an in-process write lands in: the `active` slot, else the legacy file (the
    files HEAD wrote in the b-1 runs: catalog.A.duckdb / catalog.duckdb)."""
    return "catalog.A.duckdb" if layout == "slots" else "catalog.duckdb"


def _refusal_head(target: Path) -> str:
    """The lead's wording contract for the in-process refusal (bug-212 r2, 2026-11-13), the
    tracked line and the `ls-files`-failure line alike: `refusing to open <target> read-write
    in-process: ...`. `target` is the FULL path of the catalog the open would land on, not its
    basename: the tracked-names list `(catalog.A.duckdb, ...)` already carries the basename, so
    a line that dropped the target still matched the basename (GREEN r2 mutations K6/K8
    survived). "open ... read-write", not "write": `_read_store()` with no replica and no
    daemon reaches the same `_store_rw()` for a READ (GREEN r2 flag 5, lead ruling)."""
    return f"refusing to open {target} read-write in-process:"


def _refusal_lines(stderr: str, target: Path) -> list[str]:
    """`Error:` lines carrying `_refusal_head(target)` -- the full target path -- AND both
    remedies (untrack the catalog; start the daemon)."""
    head = _refusal_head(target)
    out = []
    for ln in stderr.splitlines():
        if not ln.startswith("Error:"):
            continue
        low = ln.lower()
        if head in ln and ("untrack" in low or "rm --cached" in low) and "daemon" in low:
            out.append(ln)
    return out


def _stale_socket(path: Path) -> None:
    """A unix socket FILE with no listener: bound, then closed without unlinking -- what a
    daemon killed with SIGKILL leaves."""
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        s.bind(str(path))
    finally:
        s.close()
    assert path.is_socket(), f"fixture: {path} is not a socket file"


@pytest.mark.timeout(300)
@pytest.mark.parametrize("mode", ["files", "since"])
def test_an_in_process_sync_refuses_to_write_a_git_tracked_catalog(tracked_repo, mode):
    """a2: `rmx sync --files <f>` and `rmx sync --since HEAD~1`, no daemon, cwd = the main
    checkout (no `REFMATRIX_ROOT`, as a hook runs it): one loud refusal, non-zero exit, the
    tracked catalog untouched."""
    repo, layout = tracked_repo
    assert not dm.ping(repo.store), "fixture: a daemon answers"
    path = repo.proj / "main_new.py"
    path.write_text("def main_new():\n    return 3\n", encoding="utf-8")
    _quiet(repo.proj, repo, "add", "main_new.py")
    _quiet(repo.proj, repo, "commit", "-q", "-m", "a commit to sync")
    before = _catalog_digests(repo.store)
    argv = (["sync", "--files", str(path)] if mode == "files"
            else ["sync", "--since", "HEAD~1"])
    r = subprocess.run([sys.executable, str(_entry(repo.base)), *argv], cwd=str(repo.proj),
                       env=_base_env(), capture_output=True, text=True, timeout=240)
    text = f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    after = _catalog_digests(repo.store)
    changed = sorted(n for n in before if after.get(n) != before[n])
    assert TRACEBACK not in r.stderr, f"[{layout}] `rmx {' '.join(argv)}` crashed\n{text}"
    assert not changed, (f"[{layout}] in-process `rmx {' '.join(argv)}` wrote the git-tracked "
                         f"catalog {changed} (exit {r.returncode})\n{text}")
    assert r.returncode != 0, \
        f"[{layout}] `rmx {' '.join(argv)}` on a tracked catalog exited 0\n{text}"
    target = repo.store / _target_catalog(layout)
    assert len(_refusal_lines(r.stderr, target)) == 1, \
        f"[{layout}] no single `Error:` line `{_refusal_head(target)} ...` with the remedy " \
        f"(untrack it, or start the daemon)\n{text}"
    assert _status_refmatrix_catalogs(repo.proj) == "", \
        f"[{layout}] git sees the tracked catalog modified:\n{_status_refmatrix_catalogs(repo.proj)}"


def _status_refmatrix_catalogs(co: Path) -> str:
    r = subprocess.run(["git", "-C", str(co), "status", "--porcelain", "--",
                        *[f".refmatrix/{n}" for n in WRITER_CATALOG_FILES]],
                       env=_base_env(), capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, f"git status: {r.stdout}{r.stderr}"
    return r.stdout


@pytest.mark.timeout(300)
def test_post_commit_with_a_stale_socket_on_a_tracked_catalog_refuses_loudly(tracked_repo):
    """a2 through the GENERATED post-commit: the main checkout tracks its catalog and holds a
    socket file with no listener (a crashed daemon's leftover), so a socket-presence gate
    passes. The tracked catalog must be left byte-identical; if the hook ran `rmx`, the
    refusal must be loud on the committing terminal (its `Error:` line naming the tracked file
    and the remedy, then the hook's `rmx sync FAILED` line). The git op itself still exits 0."""
    repo, layout = tracked_repo
    sock = repo.store / dm.SOCKET_NAME
    _stale_socket(sock)
    assert not dm.ping(repo.store), "fixture: something answers on the stale socket"
    assert _status_refmatrix_catalogs(repo.proj) == "", "fixture: the catalog is already dirty"
    before = _catalog_digests(repo.store)
    (repo.proj / "main_new.py").write_text("def main_new():\n    return 3\n", encoding="utf-8")
    _quiet(repo.proj, repo, "add", "main_new.py")
    r = _hooked(repo.proj, repo, "commit", "-q", "-m", "commit beside a stale socket")
    text = f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}\nrmx calls: {_calls(repo)}"
    assert r.returncode == 0, f"the git op itself failed\n{text}"
    assert "hooks/post-commit" in _hooks_ran(repo), "fixture: git never ran post-commit"
    after = _catalog_digests(repo.store)
    changed = sorted(n for n in before if after.get(n) != before[n])
    assert TRACEBACK not in r.stderr, f"[{layout}] post-commit crashed\n{text}"
    assert not changed, (f"[{layout}] post-commit beside a stale socket wrote the git-tracked "
                         f"catalog {changed}\ngit status:\n"
                         f"{_status_refmatrix_catalogs(repo.proj)}\n{text}")
    if _calls(repo):
        target = repo.store / _target_catalog(layout)
        assert len(_refusal_lines(r.stderr, target)) == 1 and FAILED_LINE in r.stderr, \
            f"[{layout}] post-commit ran rmx beside a stale socket and the refusal was not " \
            f"loud (one `Error:` `{_refusal_head(target)} ...` + the remedy, then " \
            f"`{FAILED_LINE}`)\n{text}"


@pytest.mark.timeout(300)
def test_an_in_process_sync_of_a_store_outside_any_git_repo_still_writes():
    """GUARD (passes at HEAD) against an over-broad a2 fix: a store that is not inside any git
    repository (`git ls-files` fails there) is not "tracked" -- the in-process sync indexes."""
    base = Path(tempfile.mkdtemp(prefix="b212n-", dir="/tmp")).resolve()
    try:
        proj = base / "proj"
        root = proj / ".refmatrix"
        s = Store(root)
        s.init()
        s.close()
        probe = subprocess.run(["git", "-C", str(proj), "rev-parse", "--git-dir"],
                               env=_base_env(), capture_output=True, text=True)
        assert probe.returncode != 0, f"fixture: {proj} is inside a git repo: {probe.stdout}"
        f = proj / "loose.py"
        f.write_text("def loose():\n    return 5\n", encoding="utf-8")
        r = subprocess.run([sys.executable, str(_entry(base)), "sync", "--files", str(f)],
                           cwd=str(proj), env=_base_env(), capture_output=True, text=True,
                           timeout=240)
        text = f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
        assert r.returncode == 0 and TRACEBACK not in r.stderr, \
            f"in-process `rmx sync --files` on a store outside git failed\n{text}"
        st = Store(root)
        try:
            n = st._connect().execute("SELECT count(*) FROM entities WHERE path = ?",
                                      (str(f),)).fetchone()[0]
        finally:
            st.close()
        assert int(n) > 0, f"the sync did not index {f.name}\n{text}"
    finally:
        shutil.rmtree(base, ignore_errors=True)
