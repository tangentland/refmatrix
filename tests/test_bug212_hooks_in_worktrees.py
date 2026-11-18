"""bug-212: the 0.82.0 git hooks fail loudly, but in throwaway worktrees the loudness is a crash
dump, and some of the "errors" are not errors at all.

WHY. Seen 2026-11-11 committing through throwaway worktrees (`git worktree add /tmp/x main;
git -C /tmp/x commit ...; git worktree remove /tmp/x`) in fleet repos carrying the 0.82.0 hooks
(`hooks.GIT_HOOK_SCRIPTS`). 0.82.0 made the hooks loud because the user asked for it (2026-11-10,
verbatim: "if the sync stops in an error, it needs to fail loudly on the commandline or console,
not just logs"). What printed was raw Python tracebacks:

(a) post-checkout on `git worktree add` gets a NULL previous HEAD (`$1` = 40 zeros, `$3` = 1) and
    ran `rmx sync --since 0000...0000..<sha>`; `sync.changed_since` let git's
    `CalledProcessError` escape;
(b) the backgrounded post-commit outlived `git worktree remove`, and `cli_entry`'s `Path.cwd()`
    raised `FileNotFoundError`;
(c) the hooks' only gate, `[ -d "$ROOT/.refmatrix" ]`, passes in a fresh worktree or clone of a
    repo that TRACKS `.refmatrix/CLAUDE.md` (cliquet, atldb, viascope do) although no store
    exists there, so the hook synced a non-store dir -- and created a store in it;
(d) `rmx sync --since <ref git rejects>` is a traceback rather than a clean `Error:` line.

The contracts (team-lead, 2026-11-11):

1. no store, no sync: in a worktree or clone with no store of its own, every generated hook
   exits 0, runs no `rmx`, writes nothing under the checkout's `.refmatrix/`, and never syncs the
   main checkout's store with the checkout's paths;
2. an initial checkout (post-checkout `$1` all zeros) is not a branch switch: no sync, exit 0,
   nothing printed -- pinned in the MAIN checkout, where a store exists, so it is not contract 1;
3. a real git failure under `rmx sync --since` is a clean error -- non-zero exit, an `Error:`
   line naming the ref and git's own message, no traceback -- on the in-process route and the
   daemon route;
4. a vanished working directory is never a traceback: a project command fails as a clean
   `Error:` naming the directory; `rmx version` may instead succeed and print the version;
5. end to end: worktree add + commit + remove, generated hooks installed, a store in the main
   checkout: no traceback anywhere, no `rmx sync FAILED` line, and the main store holds no path
   of the worktree's.

Plus a guard against the over-broad fix (a gate that never syncs): the MAIN checkout, which has
a store, still syncs on commit and on a branch switch. It passes at HEAD; it is proven by a
mutation that makes every hook gate `exit 0`.

What is real: git, the GENERATED hook bodies (written by `hooks._install_git_hooks` into tmp
repos only), the sync, the store, a throwaway daemon for contract 3's daemon leg. The one stand-in
is a PATH shim named `rmx` (registered in workflow/test_mock_registry.md): it appends `$PWD` and
argv to a log, then execs THIS checkout's real CLI through a console-script-shaped entry file (the
shape `~/bin/rmx` has; `python -m` would put the cwd on `sys.path`). It replaces nothing -- the
recorded invocation is the observation, and the sync it runs is the real one. Whether a hook RAN
at all is read from `GIT_TRACE` (git logs each hook it starts), so a "no rmx call" assertion can
never pass because the hook did not fire.

Store predicate. The tests never name catalog files: "the hook created no store" is "the
checkout's `.refmatrix/` holds exactly what git checked out". A store in the main checkout is a
`Store(root).init()`, the way every throwaway store in this suite is made.
"""
from __future__ import annotations

import rmx_sandbox  # task-29.4 #r5: test roots live under the sandbox root (short_root)
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from refmatrix import daemon as dm
from refmatrix import hooks as hooks_mod
from refmatrix.store import Store
from tests.test_bridge_move_safety_r1 import (  # noqa: F401 -- fixtures are used by name
    _commit, _init_repo, absolute_pythonpath, gitproj, gitproj_inproc,
)

NULL_SHA = "0" * 40
TRACEBACK = "Traceback (most recent call last)"
FAILED_LINE = "rmx sync FAILED"
CLAUDE_MD = "# refmatrix briefing\n\nThis file is tracked; the store beside it is not.\n"
# The fleet shape: `.refmatrix/CLAUDE.md` tracked, everything else under `.refmatrix/` ignored.
GITIGNORE = ".refmatrix/*\n!.refmatrix/CLAUDE.md\n"


# =============================================================================================
# the tmp repo, the shim, and git with / without hooks
# =============================================================================================

class Repo:
    def __init__(self, base: Path):
        self.base = base
        self.proj = base / "proj"
        self.store = self.proj / ".refmatrix"
        self.bindir = base / "bin"
        self.calls_log = base / "rmx-calls.log"
        self.trace = base / "git-trace.log"
        self.nohooks = base / "nohooks"          # never created: hooksPath to an empty place


def _base_env() -> dict:
    """Git identity, no system / global git config (a developer's `core.hooksPath` must not
    route the throwaway repo's hooks elsewhere), no store pinned by env: the hooks resolve their
    store from the cwd, as they do in a real repo. The sandbox's HOME / RMX_HOME ride in from
    `os.environ` (tests/sandbox_site), so a fallback to the global store lands in the sandbox."""
    env = {k: v for k, v in os.environ.items()
           if k not in ("REFMATRIX_ROOT", "RMX_PARTITION", "GIT_DIR", "GIT_WORK_TREE",
                        "GIT_INDEX_FILE", "GIT_TRACE")}
    env.update({"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
                "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
                "PYTHONPATH": absolute_pythonpath(os.environ.get("PYTHONPATH"))})
    return env


def _hook_env(repo: Repo) -> dict:
    env = _base_env()
    env["PATH"] = f"{repo.bindir}{os.pathsep}{env.get('PATH', '')}"
    env["GIT_TRACE"] = str(repo.trace)
    return env


def _quiet(cwd: Path, repo: Repo, *args: str) -> None:
    """Setup git: hooks OFF (hooksPath to a dir that does not exist)."""
    r = subprocess.run(["git", "-C", str(cwd), "-c", f"core.hooksPath={repo.nohooks}", *args],
                       env=_base_env(), capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, f"setup git {' '.join(args)}: {r.stdout}{r.stderr}"


def _hooked(cwd: Path, repo: Repo, *args: str, stdin: "str | None" = None
            ) -> subprocess.CompletedProcess:
    """The git op under test, hooks ON. `capture_output` reads both pipes to EOF, and the
    hooks' backgrounded `( cd ... && rmx sync ... ) &` holds them, so this returns only after
    every backgrounded sync has finished."""
    return subprocess.run(["git", "-C", str(cwd), *args], env=_hook_env(repo), input=stdin,
                          capture_output=True, text=True, timeout=240)


def _write_shim(repo: Repo) -> None:
    repo.bindir.mkdir()
    entry = repo.bindir / "rmx_entry.py"
    entry.write_text("import sys\nfrom refmatrix.cli import cli_entry\nsys.exit(cli_entry())\n",
                     encoding="utf-8")
    shim = repo.bindir / "rmx"
    shim.write_text("#!/bin/sh\n"
                    f"printf '%s\\t%s\\n' \"$PWD\" \"$*\" >> '{repo.calls_log}'\n"
                    f"exec '{sys.executable}' '{entry}' \"$@\"\n", encoding="utf-8")
    shim.chmod(0o755)


def _calls(repo: Repo) -> list[tuple[str, str]]:
    if not repo.calls_log.exists():
        return []
    out = []
    for ln in repo.calls_log.read_text(encoding="utf-8").splitlines():
        pwd, _, argv = ln.partition("\t")
        out.append((pwd, argv))
    return out


def _hooks_ran(repo: Repo) -> str:
    return repo.trace.read_text(encoding="utf-8", errors="replace") if repo.trace.exists() else ""


def _tree(d: Path) -> list[str]:
    return sorted(str(p.relative_to(d)) for p in d.rglob("*")) if d.exists() else []


def _store_paths_under(repo: Repo, prefix: Path) -> list[str]:
    """Every entity path in the MAIN store under `prefix` (all partitions)."""
    s = Store(repo.store)
    try:
        rows = s._connect().execute("SELECT path FROM entities WHERE path LIKE ?",
                                    (f"{prefix}/%",)).fetchall()
    finally:
        s.close()
    return sorted(str(r[0]) for r in rows)


def _store_has_path(repo: Repo, path: Path) -> bool:
    s = Store(repo.store)
    try:
        n = s._connect().execute("SELECT count(*) FROM entities WHERE path = ?",
                                 (str(path),)).fetchone()[0]
    finally:
        s.close()
    return int(n) > 0


@pytest.fixture
def repo():
    """A git repo `proj` on `main` with the fleet layout (`.refmatrix/CLAUDE.md` tracked, a real
    store beside it), a branch `other` one commit ahead (adds `other.py`), the GENERATED hooks
    installed, and the recording shim. Everything under a short resolved `/tmp` root."""
    base = Path(rmx_sandbox.short_root("b212-")).resolve()
    r = Repo(base)
    try:
        r.proj.mkdir()
        _quiet(r.proj, r, "init", "-q", "--template=", "-b", "main")
        (r.proj / ".gitignore").write_text(GITIGNORE, encoding="utf-8")
        (r.proj / "README.md").write_text("r\n", encoding="utf-8")
        r.store.mkdir()
        (r.store / "CLAUDE.md").write_text(CLAUDE_MD, encoding="utf-8")
        s = Store(r.store)
        s.init()
        s.close()
        _quiet(r.proj, r, "add", "-A")
        _quiet(r.proj, r, "commit", "-q", "-m", "c0")
        tracked = subprocess.run(["git", "-C", str(r.proj), "ls-files", ".refmatrix"],
                                 capture_output=True, text=True).stdout.split()
        assert tracked == [".refmatrix/CLAUDE.md"], f"fixture: tracked under .refmatrix: {tracked}"
        _quiet(r.proj, r, "checkout", "-q", "-b", "other")
        (r.proj / "other.py").write_text("def other():\n    return 1\n", encoding="utf-8")
        _quiet(r.proj, r, "add", "-A")
        _quiet(r.proj, r, "commit", "-q", "-m", "c1 on other")
        _quiet(r.proj, r, "checkout", "-q", "main")
        out = hooks_mod._install_git_hooks(r.proj, apply=True, force=True)
        for name in hooks_mod.GIT_HOOK_SCRIPTS:
            assert (r.proj / ".git" / "hooks" / name).exists(), f"hook not installed: {out}"
        _write_shim(r)
        yield r
    finally:
        shutil.rmtree(base, ignore_errors=True)


# =============================================================================================
# 1. no store, no sync -- in a worktree and in a clone
# =============================================================================================

def _storeless_checkout(repo: Repo, where: str) -> Path:
    """A second checkout of `main` that has `.refmatrix/CLAUDE.md` (tracked) and no store.
    Made with hooks OFF: the op under test is the only hooked one."""
    if where == "worktree":
        co = repo.base / "wt"
        _quiet(repo.proj, repo, "worktree", "add", "-q", "-b", "feature", str(co), "main")
    else:
        co = repo.base / "clone"
        r = subprocess.run(["git", "clone", "-q", "--template=", str(repo.proj), str(co)],
                           env=_base_env(), capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, f"clone: {r.stdout}{r.stderr}"
        hooks_mod._install_git_hooks(co, apply=True, force=True)
    assert _tree(co / ".refmatrix") == ["CLAUDE.md"], \
        f"fixture: the {where} is not storeless: {_tree(co / '.refmatrix')}"
    return co


def _op(hook: str, repo: Repo, co: Path, where: str) -> subprocess.CompletedProcess:
    other = "other" if where == "worktree" else "origin/other"
    if hook == "post-commit":
        (co / f"new_in_{where}.py").write_text("def new():\n    return 2\n", encoding="utf-8")
        _quiet(co, repo, "add", "-A")
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
def test_a_checkout_without_a_store_of_its_own_runs_no_sync(repo, hook, where):
    co = _storeless_checkout(repo, where)
    r = _op(hook, repo, co, where)
    text = f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    assert r.returncode == 0, f"the git op itself failed\n{text}"
    assert f"hooks/{hook}" in _hooks_ran(repo), \
        f"fixture: git never ran {hook} (GIT_TRACE), so 'no rmx call' would prove nothing"
    calls = _calls(repo)
    assert not calls, \
        f"{hook} in a {where} with no store of its own ran rmx: {calls}\n{text}"
    assert TRACEBACK not in r.stderr, f"{hook} in a {where} printed a raw traceback\n{text}"
    assert _tree(co / ".refmatrix") == ["CLAUDE.md"], \
        f"{hook} in a {where} wrote into its .refmatrix/ (a store where none was): " \
        f"{_tree(co / '.refmatrix')}"
    assert _store_paths_under(repo, co) == [], \
        f"{hook} in a {where} synced the MAIN store with the {where}'s paths: " \
        f"{_store_paths_under(repo, co)}"


# =============================================================================================
# 2. an initial checkout (null previous HEAD) is not a branch switch
# =============================================================================================

@pytest.mark.timeout(300)
def test_post_checkout_with_a_null_previous_head_runs_no_sync_and_prints_nothing(repo):
    """Git passes `$1` = 40 zeros on an initial checkout (`git worktree add`, `git clone`). It
    is driven in the MAIN checkout, which HAS a store, so the null sha alone must stop it."""
    head = subprocess.run(["git", "-C", str(repo.proj), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    hook = repo.proj / ".git" / "hooks" / "post-checkout"
    r = subprocess.run([str(hook), NULL_SHA, head, "1"], cwd=str(repo.proj),
                       env=_hook_env(repo), capture_output=True, text=True, timeout=240)
    text = f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    assert r.returncode == 0, f"post-checkout exited {r.returncode}\n{text}"
    assert not _calls(repo), \
        f"post-checkout with a null previous HEAD ran rmx: {_calls(repo)}\n{text}"
    assert r.stdout == "" and r.stderr == "", \
        f"post-checkout with a null previous HEAD printed something\n{text}"


# =============================================================================================
# the guard: the main checkout, which has a store, still syncs
# =============================================================================================

@pytest.mark.timeout(300)
@pytest.mark.parametrize("hook", ["post-commit", "post-checkout"])
def test_the_main_checkout_with_a_store_still_syncs(repo, hook):
    """Passes at HEAD; proven by the mutation `[ -d "$ROOT/.refmatrix" ] || exit 0` -> `exit 0`
    in every GIT_HOOK_SCRIPTS body. A bug-212 fix that silences the hooks everywhere fails it."""
    if hook == "post-commit":
        path = repo.proj / "main_new.py"
        path.write_text("def main_new():\n    return 3\n", encoding="utf-8")
        _quiet(repo.proj, repo, "add", "-A")
        r = _hooked(repo.proj, repo, "commit", "-q", "-m", "commit in the main checkout")
    else:
        path = repo.proj / "other.py"
        r = _hooked(repo.proj, repo, "checkout", "-q", "other")
    text = f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    assert r.returncode == 0, f"the git op itself failed\n{text}"
    assert TRACEBACK not in r.stderr, f"{hook} in the main checkout crashed\n{text}"
    syncs = [c for c in _calls(repo) if c[1].startswith("sync")]
    assert syncs and all(Path(pwd).resolve() == repo.proj for pwd, _ in syncs), \
        f"{hook} in the main checkout (store present) ran no sync there: {_calls(repo)}\n{text}"
    assert _store_has_path(repo, path), \
        f"{hook} in the main checkout did not sync {path.name} into the main store\n{text}"


# =============================================================================================
# 3. a ref git rejects is a clean error (in-process and daemon routes)
# =============================================================================================

BAD_REFS = ["no-such-ref-bug212", f"{NULL_SHA}..HEAD"]


def _git_says(proj: Path, ref: str) -> str:
    """git's OWN message for this ref (read, not hardcoded: the wording is git's), without the
    `fatal: ` prefix, which a clean error may drop."""
    r = subprocess.run(["git", "-C", str(proj), "diff", "--name-only", ref],
                       capture_output=True, text=True)
    assert r.returncode != 0, f"fixture: git accepts {ref!r}"
    first = next(ln for ln in r.stderr.splitlines() if ln.strip())
    return first.removeprefix("fatal: ").strip()


def _entry(base: Path) -> Path:
    e = base / "rmx_entry.py"
    e.write_text("import sys\nfrom refmatrix.cli import cli_entry\nsys.exit(cli_entry())\n",
                 encoding="utf-8")
    return e


def _assert_clean_since_error(r: subprocess.CompletedProcess, ref: str, says: str,
                              route: str) -> None:
    text = f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    assert r.returncode != 0, f"[{route}] `rmx sync --since {ref}` exited 0\n{text}"
    assert TRACEBACK not in r.stderr, \
        f"[{route}] `rmx sync --since {ref}` failed as a raw traceback\n{text}"
    err = [ln for ln in r.stderr.splitlines() if ln.startswith("Error:")]
    assert any(ref in ln and says in ln for ln in err), \
        f"[{route}] no `Error:` line naming the ref {ref!r} and git's message {says!r}\n{text}"


@pytest.mark.timeout(300)
@pytest.mark.parametrize("ref", BAD_REFS)
def test_sync_since_a_ref_git_rejects_is_a_clean_error_in_process(gitproj_inproc, ref):
    base, proj, root = gitproj_inproc
    _init_repo(proj)
    _commit(proj, "c0")
    assert not dm.ping(root), "fixture: a daemon is up; this is the in-process leg"
    says = _git_says(proj, ref)
    r = subprocess.run([sys.executable, str(_entry(base)), "sync", "--project-root", str(proj),
                        "--since", ref], cwd=str(proj), capture_output=True, text=True,
                       env={**_base_env(), "REFMATRIX_ROOT": str(root)}, timeout=240)
    _assert_clean_since_error(r, ref, says, "in-process")


@pytest.mark.timeout(300)
@pytest.mark.parametrize("ref", BAD_REFS)
def test_sync_since_a_ref_git_rejects_is_a_clean_error_through_the_daemon(gitproj, ref):
    base, proj, root = gitproj
    _init_repo(proj)
    _commit(proj, "c0")
    assert dm.ping(root), "fixture: the daemon is down; this is the daemon-routed leg"
    says = _git_says(proj, ref)
    r = subprocess.run([sys.executable, str(_entry(base)), "sync", "--project-root", str(proj),
                        "--since", ref], cwd=str(proj), capture_output=True, text=True,
                       env={**_base_env(), "REFMATRIX_ROOT": str(root)}, timeout=240)
    _assert_clean_since_error(r, ref, says, "daemon")
    assert dm.ping(root), "the daemon died over a bad --since ref"


# =============================================================================================
# 4. a vanished working directory is a clean error
# =============================================================================================

@pytest.mark.timeout(120)
@pytest.mark.parametrize("argv", [["sync", "--since", "HEAD~1"], ["stats"], ["version"]],
                         ids=["sync-since", "stats", "version"])
def test_rmx_started_in_a_vanished_cwd_is_a_clean_error(argv):
    """The shape of the backgrounded post-commit that outlives `git worktree remove`: the shell
    `cd`s into the dir, the dir goes, then `rmx` starts. No `REFMATRIX_ROOT` (a hook has none).
    A project command fails as a clean `Error:` naming the directory; `version` may also
    succeed (it needs no project) -- either way, never a traceback."""
    base = Path(rmx_sandbox.short_root("b212v-")).resolve()
    try:
        gone = base / "gone"
        gone.mkdir()
        entry = _entry(base)
        r = subprocess.run(["/bin/sh", "-c", 'cd "$1" && rmdir "$1" && shift && exec "$@"',
                            "sh", str(gone), sys.executable, str(entry), *argv],
                           cwd=str(base), env=_base_env(), capture_output=True, text=True,
                           timeout=110)
    finally:
        shutil.rmtree(base, ignore_errors=True)
    text = f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    assert TRACEBACK not in r.stderr, \
        f"`rmx {' '.join(argv)}` in a vanished cwd crashed with a raw traceback\n{text}"
    err = [ln for ln in r.stderr.splitlines() if ln.startswith("Error:")]
    if argv == ["version"]:
        # team-lead, 2026-11-11: `rmx version` needs no project, so it MAY succeed in a vanished
        # cwd -- then it must really print the version. Otherwise it fails as a clean `Error:`.
        if r.returncode == 0:
            assert re.search(r"^refmatrix \S+", r.stdout, re.M), \
                f"`rmx version` exited 0 in a vanished cwd without printing the version\n{text}"
        else:
            assert err, f"`rmx version` failed in a vanished cwd with no `Error:` line\n{text}"
        return
    assert r.returncode != 0, f"`rmx {' '.join(argv)}` in a vanished cwd exited 0\n{text}"
    assert any("director" in ln.lower() or "cwd" in ln.lower() for ln in err), \
        f"`rmx {' '.join(argv)}`: no `Error:` line saying the working directory is gone\n{text}"


# =============================================================================================
# 5. end to end: worktree add, commit, remove
# =============================================================================================

@pytest.mark.timeout(420)
def test_worktree_add_commit_remove_prints_no_traceback_and_leaves_the_main_store_alone(repo):
    """The 2026-11-11 session, in a tmp repo: every hook git fires on the way is the GENERATED
    one. The commit's backgrounded post-commit is left running while the worktree is removed
    (git returns first; the pipes are drained afterwards), which is how (b) happened."""
    wt = repo.base / "wt"
    errs: dict[str, str] = {}

    add = _hooked(repo.proj, repo, "worktree", "add", "-q", "-b", "feature", str(wt), "main")
    errs["worktree add"] = add.stderr
    assert add.returncode == 0, f"worktree add failed: {add.stdout}{add.stderr}"

    (wt / "feature_only.py").write_text("def feature_only():\n    return 4\n", encoding="utf-8")
    _quiet(wt, repo, "add", "-A")
    commit = subprocess.Popen(["git", "-C", str(wt), "commit", "-q", "-m", "commit in wt"],
                              env=_hook_env(repo), stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True)
    try:
        assert commit.wait(timeout=120) == 0, "the commit in the worktree failed"
        rm = _hooked(repo.proj, repo, "worktree", "remove", str(wt))
        errs["worktree remove"] = rm.stderr
        # drain the commit's pipes to EOF: its backgrounded post-commit holds them until done
        _out, errs["commit"] = commit.communicate(timeout=240)
    finally:
        if commit.poll() is None:
            commit.kill()
    assert rm.returncode == 0, f"worktree remove failed: {rm.stdout}{rm.stderr}"
    assert not wt.exists(), "the worktree is still on disk after `git worktree remove`"

    ran = _hooks_ran(repo)
    assert "hooks/post-checkout" in ran and "hooks/post-commit" in ran, \
        "fixture: git did not run post-checkout and post-commit (GIT_TRACE)"
    dump = "\n".join(f"--- {k} stderr:\n{v}" for k, v in errs.items())
    crashed = [k for k, v in errs.items() if TRACEBACK in v]
    assert not crashed, f"raw traceback(s) during {crashed}\n{dump}\nrmx calls: {_calls(repo)}"
    failed = [k for k, v in errs.items() if FAILED_LINE in v]
    assert not failed, \
        f"a hook reported a failed sync during {failed} (there was no store to sync)\n{dump}"
    assert _store_paths_under(repo, wt) == [], \
        f"the main store was synced with the worktree's paths: {_store_paths_under(repo, wt)}"
