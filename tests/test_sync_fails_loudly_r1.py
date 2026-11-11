"""Task 26.2 r1 remedy: a sync that stops in an error fails LOUDLY (user requirement,
2026-11-10, verbatim: "if the sync stops in an error, it needs to fail loudly on the commandline
or console, not just logs").

WHY. 26.2 r1 GREEN (497f7f0) made `Store.purge_path` fail closed: when the memory that may own
the anchors at a path has unreadable metadata, it RAISES rather than deleting or keeping them
silently. A raise is only fail-closed if someone sees it. Four of the surfaces that carry a
sync are pinned here with that real raise as the error (x's `memory_content.metadata` =
`'{not json'` on a throwaway store). The fifth, the hooks' `rmx sync --flush-queue --async`
(ch-bsd 26.2 r2 #b2-1: "Four surfaces" was false), and the per-path refusal (#s2-1) are in
`tests/test_sync_fails_loudly_r2.py`:

1. the in-process CLI (`rmx sync -f|-i P`, no daemon): non-zero exit, error naming x on STDERR;
2. the daemon-routed CLI (`rmx sync --since HEAD~1`): the daemon replies ok:false, and the CLI
   exits non-zero and names x;
3. the generated git hooks (`hooks.GIT_HOOK_SCRIPTS`): they ran `rmx sync ... >/dev/null 2>&1 ||
   true`, which discards every error. A real post-commit hook, installed by `_install_git_hooks`
   into a throwaway repo, must leave the error on the committing terminal's stderr;
4. the daemon watcher (no terminal): a failed watch flush was only written to `rmxd.log`.
   `rmx daemon status` must print it, naming the error, until a later successful flush clears
   it.

Nothing is mocked. The hook test puts a launcher named `rmx` on PATH that execs THIS checkout's
CLI (`python -m refmatrix.cli`), the way `~/bin/rmx` execs the deploy tree. It is a PATH shim,
not a stand-in: the sync it runs is the real one.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod
from refmatrix import daemon as dm
from refmatrix import hooks as hooks_mod
from tests.test_bridge_move_safety import X_MD, _bridge, _invoke
from tests.test_bridge_move_safety_r1 import (  # noqa: F401 -- fixtures are used by name
    MEMORY_X, _commit, _git, _init_repo, _proj_memdir, _restart, _set_metadata_raw,
    absolute_pythonpath, gitproj, gitproj_inproc,
)


def _broken_x(proj: Path, root: Path, *, daemon_up: bool,
              memdir: "Path | None" = None) -> tuple[Path, str]:
    """Bridge the in-repo memdir (created unless given), then make x's metadata unreadable
    (daemon stopped for the write, restarted after when it was up). Returns (memdir, resolved
    a/x.md)."""
    memdir = memdir or _proj_memdir(proj, marker=False)
    _bridge(memdir)
    if daemon_up:
        dm.stop_daemon(root)
    _set_metadata_raw(root, "x", "{not json")
    if daemon_up:
        _restart(root)
    return memdir, str((memdir / "a" / "x.md").resolve())


def _edit_x(memdir: Path, n: int = 1) -> None:
    (memdir / "a" / "x.md").write_text(X_MD.format(id="x", body=f"edited body of x, rev {n}"),
                                       encoding="utf-8")


def _cli_env(root: Path) -> dict:
    """The env every subprocess / PATH-shim leg runs with: the throwaway root, and THIS
    checkout's `src` as an absolute PYTHONPATH (ch-bsd 26.2 r2 #m2-1)."""
    return {**os.environ, "REFMATRIX_ROOT": str(root),
            "PYTHONPATH": absolute_pythonpath(os.environ.get("PYTHONPATH"))}


# =============================================================================================
# 1. the in-process CLI
# =============================================================================================

@pytest.mark.parametrize("flag", ["-f", "-i"])
def test_in_process_sync_error_exits_nonzero_and_names_it_on_stderr(gitproj_inproc, flag):
    base, proj, root = gitproj_inproc
    memdir, p = _broken_x(proj, root, daemon_up=False)
    assert not dm.ping(root), "fixture: a daemon is up; this is the in-process leg"
    r = subprocess.run([sys.executable, "-m", "refmatrix.cli", "sync", "--project-root",
                        str(proj), flag, p], capture_output=True, text=True, cwd=str(proj),
                       env=_cli_env(root), timeout=180)
    assert r.returncode != 0, \
        f"`rmx sync {flag} P` exited 0 over a failed purge\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    assert MEMORY_X.search(r.stderr), \
        f"`rmx sync {flag} P`: stderr does not name memory x\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    # A CLEAN failure, as the daemon route gives (`Error: daemon sync_since failed: ...`): a raw
    # traceback reads like a crash, not a refusal (team-lead, 2026-11-10).
    assert "Traceback (most recent call last)" not in r.stderr, \
        f"`rmx sync {flag} P` failed as a raw traceback, not a clean error\nstderr:\n{r.stderr}"
    err = [ln for ln in r.stderr.splitlines() if ln.startswith("Error:")]
    assert any(MEMORY_X.search(ln + " ") and "metadata" in ln for ln in err), \
        f"`rmx sync {flag} P`: no `Error:` line naming memory x and its metadata\n" \
        f"stderr:\n{r.stderr}"


# =============================================================================================
# 2. the daemon-routed CLI
# =============================================================================================

def test_daemon_routed_sync_error_is_an_error_reply_and_a_loud_cli_exit(gitproj):
    base, proj, root = gitproj
    _init_repo(proj)
    memdir = _proj_memdir(proj, marker=False)
    _commit(proj, "c0")
    memdir, p = _broken_x(proj, root, daemon_up=True, memdir=memdir)
    _edit_x(memdir)
    _commit(proj, "c1: edit a/x.md")
    assert dm.ping(root), "fixture: the daemon is down; this is the daemon-routed leg"
    r = CliRunner().invoke(cli_mod.main, ["sync", "--project-root", str(proj),
                                          "--since", "HEAD~1"])
    text = f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}\nexception: {r.exception!r}"
    assert r.exit_code != 0, f"`rmx sync --since HEAD~1` exited 0 over a failed purge\n{text}"
    assert MEMORY_X.search(r.stderr), f"the CLI's stderr does not name memory x\n{text}"
    resp = dm.call(root, "sync_since", {"project_root": str(proj), "git_ref": "HEAD~1",
                                        "semantic": False}, timeout=120.0, retries=0)
    assert resp.get("ok") is False, f"the daemon replied success over a failed purge: {resp}"
    assert MEMORY_X.search(str(resp.get("error"))), f"the error reply does not name x: {resp}"


# =============================================================================================
# 3. the generated git hooks
# =============================================================================================

_DISCARD = re.compile(r"2>\s*/dev/null|>\s*/dev/null\s+2>&1|&>\s*/dev/null|\|\|\s*(true|:)\b")


@pytest.mark.parametrize("name", sorted(hooks_mod.GIT_HOOK_SCRIPTS))
def test_generated_git_hook_does_not_discard_the_sync_failure(name):
    """Every hook line that runs `rmx sync` keeps its stderr and its exit status: no
    `2>/dev/null`, no `>/dev/null 2>&1`, no `&>/dev/null`, no `|| true`. (stdout may be
    quieted with `>/dev/null`; the job may stay backgrounded.)"""
    lines = [ln for ln in hooks_mod.GIT_HOOK_SCRIPTS[name].splitlines() if "rmx sync" in ln]
    assert lines, f"{name}: no `rmx sync` line"
    bad = [ln for ln in lines if _DISCARD.search(ln)]
    assert not bad, f"{name} discards the sync's error: {bad}"


@pytest.mark.timeout(300)
def test_installed_post_commit_hook_leaves_a_failing_sync_on_the_terminal(gitproj_inproc):
    base, proj, root = gitproj_inproc
    _init_repo(proj)
    memdir = _proj_memdir(proj, marker=False)
    _commit(proj, "c0")
    memdir, p = _broken_x(proj, root, daemon_up=False, memdir=memdir)
    out = hooks_mod._install_git_hooks(proj, apply=True, force=True)
    assert (proj / ".git" / "hooks" / "post-commit").exists(), f"hook not installed: {out}"
    bindir = base / "bin"
    bindir.mkdir()
    shim = bindir / "rmx"
    shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" -m refmatrix.cli "$@"\n',
                    encoding="utf-8")
    shim.chmod(0o755)
    _edit_x(memdir)
    _git(proj, "add", "-A")
    env = {**_cli_env(root), "PATH": f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}",
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    # hooks ON for this one commit. capture waits for EOF, i.e. for the backgrounded sync too.
    r = subprocess.run(["git", "-C", str(proj), "commit", "-q", "-m", "c1: edit a/x.md"],
                       capture_output=True, text=True, env=env, timeout=240)
    assert r.returncode == 0, f"the commit itself failed: {r.stdout}{r.stderr}"
    assert MEMORY_X.search(r.stderr), \
        f"the post-commit sync failed silently: nothing naming memory x on the terminal\n" \
        f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"


# =============================================================================================
# 4. the daemon watcher
# =============================================================================================

def _log_lines(root: Path) -> list[str]:
    p = root / dm.LOG_NAME
    return p.read_text(encoding="utf-8", errors="replace").splitlines() if p.exists() else []


def _poll_log(root: Path, pred, touch, *, bound: float = 120.0) -> list[str]:
    """Re-touch (each write is a fresh fs event) until a log line satisfies `pred`: the first
    event can land before the observer is scheduled (the test_task3_7_curator pattern)."""
    deadline = time.monotonic() + bound
    next_touch, n = 0.0, 0
    while time.monotonic() < deadline:
        hits = [ln for ln in _log_lines(root) if pred(ln)]
        if hits:
            return hits
        if time.monotonic() >= next_touch:
            n += 1
            touch(n)
            next_touch = time.monotonic() + 3.0
        time.sleep(0.2)
    raise AssertionError(f"no matching rmxd.log line in {bound}s ({n} touches):\n"
                         + "\n".join(_log_lines(root)[-20:]))


def _status() -> str:
    r = CliRunner().invoke(cli_mod.main, ["daemon", "status"])
    return f"{r.output}"


@pytest.mark.timeout(300)
def test_failed_watch_flush_is_printed_by_daemon_status_until_a_good_flush(gitproj):
    """The narrowest real trigger the watcher can reach (it drops hidden segments, so not the
    memdir): a project doc `docs/x.md` with GMD id `x` holds the `x#...` concepts while memory
    x's metadata is unreadable. Re-syncing the doc purges its path first, and the guard raises.

    Setup goes through the fixture's NON-watching daemon: an in-process `rmx sync` leaves this
    process holding the catalog (the command never closes its store), and the watching daemon
    then cannot start."""
    base, proj, root = gitproj
    _bridge(_proj_memdir(proj, marker=False))
    docs = proj / "docs"
    docs.mkdir()
    doc = docs / "x.md"
    doc.write_text(X_MD.format(id="x", body="a project doc that reuses the id x"),
                   encoding="utf-8")
    _invoke(["sync", "--project-root", str(proj), "-f", str(doc.resolve())])
    dm.stop_daemon(root)
    _set_metadata_raw(root, "x", "{not json")
    assert dm.spawn_daemon_subprocess(root, watch_root=[proj]) and dm.ping(root)
    try:
        failed = _poll_log(
            root, lambda ln: "watch flush failed" in ln,
            lambda n: doc.write_text(X_MD.format(id="x", body=f"doc rev {n}"), encoding="utf-8"))
        assert MEMORY_X.search(failed[-1]), f"fixture: the flush failed for another reason: {failed}"
        out = _status()
        assert re.search(r"watch|flush", out, re.I) and MEMORY_X.search(out), \
            f"`rmx daemon status` does not print the failed watch flush naming memory x:\n{out}"
        # a later successful flush clears it: wait until the NEWEST flush line is a success
        ok = docs / "ok.md"

        def _good(_ln: str) -> bool:
            flushes = [x for x in _log_lines(root) if "watch flush" in x]
            return bool(flushes) and "watch flush failed" not in flushes[-1]
        _poll_log(root, _good, lambda n: ok.write_text(f"# ok\n\nrev {n}\n", encoding="utf-8"))
        out = _status()
        assert not MEMORY_X.search(out), \
            f"`rmx daemon status` still prints the old failure after a good flush:\n{out}"
    finally:
        if dm.ping(root):
            dm.stop_daemon(root)
