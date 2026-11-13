"""bug-212 r2 RED: kill the four mutations GREEN r1 left alive (G3, E1, E2, W1), and move the
a2 refusal to the write control point so EVERY in-process writer refuses a git-tracked catalog.

WHY (2026-11-13; brief `workflow/agents/red-212r2.md`; GREEN r1 `faabdfe`, its mutation table
`workflow/implementation_summaries/task-bug212-worktree-hook-crashes.md#green-r1-mutations`):

G3 / E2. Both fail-closed `git ls-files` failure paths -- the shell gate's
    `|| { echo "refmatrix: <hook>: git ls-files failed; not syncing" >&2; exit 0; }` and
    `store.git_tracked_catalogs`' `TrackedCatalogCheckError` -- survived because no test made
    `ls-files` fail. Here it fails for real: a corrupt `.git/index` in a throwaway repo. A
    commit, checkout or merge cannot run on a corrupt index, so the GENERATED hook files are
    executed directly, the way git runs them (cwd = the top level, the hook's own argv/stdin);
    `git rev-parse --show-toplevel` does not read the index, `ls-files` does.
E1. `git_tracked_catalogs` drops the hook's repository-local `GIT_*` variables. That matters
    only when the store's repository is NOT the hook's: `REFMATRIX_ROOT` names a store in repo B
    while a WORKTREE hook of repo A runs -- git exports an absolute `GIT_DIR` into a worktree
    hook (recorded here by the shim, so the fixture proves the shape), and with it kept,
    `git -C <B store>` reads A's index and calls B's tracked catalog untracked.
W1. The vanished-cwd remedy depends on `REFMATRIX_ROOT`: telling a user who already set it to
    "set REFMATRIX_ROOT" sends them in a circle (ch-bsd r1 impression: an error message's remedy
    is a test case). No test read the remedy text, so the env check could be deleted unseen.
    cctree's own remedy is `--project`.
a2 at the write control point (lead decision 2026-11-13, as the user would: one control point,
    every writer). GREEN r1 refused only `rmx sync`; `rmx ingest`, `rmx memory add` and the
    memory bridge (`rmx ingest-gmd --as-memory`) still reach `cli._store_rw()` and write a
    tracked catalog in-process. The fix moves the check into `_store_rw()`. A store in no
    repository, or whose catalog git ignores, still writes (guards).

Everything is real: git, the generated hooks, the CLI (through a console-script-shaped entry
file), the store. Stand-in: the registered recording `rmx` PATH shim (`external`); E1's variant
also records `$GIT_DIR`, which is the observation that makes the fixture the E1 shape.
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from refmatrix import daemon as dm
from refmatrix import hooks as hooks_mod
from refmatrix import store as store_mod
from refmatrix.store import WRITER_CATALOG_FILES, Store
from tests.test_bug212_hooks_in_worktrees import (
    CLAUDE_MD, FAILED_LINE, TRACEBACK, Repo, _base_env, _calls, _entry, _hook_env, _hooked,
    _quiet, _write_shim,
)
from tests.test_bug212_r1_remedy import (  # noqa: F401 -- `tracked_repo` is used by name
    _refusal_head, _refusal_lines, _status_refmatrix_catalogs, _target_catalog, _vanished,
    tracked_repo,
)


def _digests(store: Path) -> dict[str, str]:
    return {n: hashlib.sha256((store / n).read_bytes()).hexdigest()
            for n in WRITER_CATALOG_FILES if (store / n).exists()}


def _changed(before: dict[str, str], after: dict[str, str]) -> list[str]:
    return sorted(n for n in before if after.get(n) != before[n])


def _errors(stderr: str) -> list[str]:
    return [ln for ln in stderr.splitlines() if ln.startswith("Error:")]


def _corrupt_index(proj: Path) -> None:
    """Overwrite `.git/index` with bytes that are not an index, and prove `ls-files` now fails
    while `rev-parse --show-toplevel` (the hooks' first line) still works."""
    (proj / ".git" / "index").write_bytes(b"not a git index -- bug-212 r2\n" * 4)
    ls = subprocess.run(["git", "-C", str(proj), "ls-files"], env=_base_env(),
                        capture_output=True, text=True, timeout=60)
    assert ls.returncode != 0, f"fixture: ls-files still works on the corrupt index: {ls.stdout}"
    top = subprocess.run(["git", "-C", str(proj), "rev-parse", "--show-toplevel"],
                         env=_base_env(), capture_output=True, text=True, timeout=60)
    assert top.returncode == 0 and Path(top.stdout.strip()).resolve() == proj, \
        f"fixture: rev-parse --show-toplevel fails on the corrupt index: {top.stdout}{top.stderr}"


@pytest.fixture
def corrupt_index_repo():
    """A repo `proj` whose store is COMMITTED (catalog.duckdb tracked -- the b-1 shape) and whose
    `.git/index` is then corrupted. Generated hooks installed, recording shim written. No daemon."""
    base = Path(tempfile.mkdtemp(prefix="b212x-", dir="/tmp")).resolve()
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
        _quiet(r.proj, r, "add", "-A")
        _quiet(r.proj, r, "commit", "-q", "-m", "c0 (the store committed)")
        (r.proj / "two.py").write_text("def two():\n    return 2\n", encoding="utf-8")
        _quiet(r.proj, r, "add", "-A")
        _quiet(r.proj, r, "commit", "-q", "-m", "c1")
        hooks_mod._install_git_hooks(r.proj, apply=True, force=True)
        _write_shim(r)
        _corrupt_index(r.proj)
        assert not (r.store / dm.SOCKET_NAME).exists(), "fixture: a daemon socket exists"
        yield r
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _rev(proj: Path, ref: str) -> str:
    r = subprocess.run(["git", "-C", str(proj), "rev-parse", ref], env=_base_env(),
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, f"rev-parse {ref}: {r.stderr}"
    return r.stdout.strip()


# =============================================================================================
# G3: the shell gate -- a failing `git ls-files` is said on stderr and syncs nothing
# =============================================================================================

@pytest.mark.timeout(300)
@pytest.mark.parametrize("hook", sorted(hooks_mod.GIT_HOOK_SCRIPTS))
def test_a_hook_whose_git_ls_files_fails_says_so_and_does_not_sync(corrupt_index_repo, hook):
    """G3: the gate cannot ask git whether the catalog is tracked (corrupt index). Unknown is
    not "untracked": the hook prints `refmatrix: <hook>: git ls-files failed; not syncing`,
    runs no `rmx`, and exits 0 (a hook failure must not fail the user's git op)."""
    repo = corrupt_index_repo
    head, prev = _rev(repo.proj, "HEAD"), _rev(repo.proj, "HEAD~1")
    argv = {"post-checkout": [prev, head, "1"]}.get(hook, [])
    stdin = f"{prev} {head}\n" if hook == "post-rewrite" else None
    before = _digests(repo.store)
    r = subprocess.run([str(repo.proj / ".git" / "hooks" / hook), *argv], cwd=str(repo.proj),
                       env=_hook_env(repo), input=stdin, capture_output=True, text=True,
                       timeout=240)
    text = f"exit {r.returncode}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}\nrmx calls: {_calls(repo)}"
    assert r.returncode == 0, f"{hook} with a failing ls-files exited non-zero\n{text}"
    assert TRACEBACK not in r.stderr, f"{hook} crashed\n{text}"
    said = f"refmatrix: {hook}: git ls-files failed; not syncing"
    assert said in r.stderr.splitlines(), \
        f"{hook}: `git ls-files` failed and the hook did not say `{said}` on stderr\n{text}"
    assert not _calls(repo), f"{hook} ran rmx although it could not tell whether git tracks " \
                             f"the catalog\n{text}"
    assert _changed(before, _digests(repo.store)) == [], f"{hook} wrote the catalog\n{text}"


# =============================================================================================
# E2: the Python check -- a failing `git ls-files` raises, and the CLI refuses in one line
# =============================================================================================

def test_git_tracked_catalogs_raises_when_ls_files_fails(corrupt_index_repo):
    """E2, the function: inside a repository whose `ls-files` fails, the answer is UNKNOWN --
    `TrackedCatalogCheckError` naming the git failure -- never `[]` ("untracked")."""
    repo = corrupt_index_repo
    with pytest.raises(store_mod.TrackedCatalogCheckError) as ei:
        got = store_mod.git_tracked_catalogs(repo.store)
        pytest.fail(f"git_tracked_catalogs returned {got!r} on a corrupt index")
    assert "ls-files" in str(ei.value), f"the error does not name the failing git call: {ei.value}"


@pytest.mark.timeout(300)
def test_an_in_process_sync_refuses_when_git_ls_files_fails(corrupt_index_repo):
    """E2, end to end: `rmx sync --files <f>`, no daemon. Whether git tracks the catalog is
    unknown, so the in-process open is refused: ONE `Error:` line
    `refusing to open <full catalog path> read-write in-process: ...` that names the failing
    `ls-files` with its exit code and both remedies; exit non-zero, catalog bytes unchanged.
    The full path is required because GREEN r2's mutation K8 (the target dropped from this
    line) survived a basename check (r3 RED, lead 2026-11-13)."""
    repo = corrupt_index_repo
    f = repo.proj / "two.py"
    before = _digests(repo.store)
    r = subprocess.run([sys.executable, str(_entry(repo.base)), "sync", "--files", str(f)],
                       cwd=str(repo.proj), env=_base_env(), capture_output=True, text=True,
                       timeout=240)
    text = f"exit {r.returncode}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    changed = _changed(before, _digests(repo.store))
    assert TRACEBACK not in r.stderr, f"`rmx sync` crashed on a failing ls-files\n{text}"
    assert not changed, f"`rmx sync` wrote {changed} although git could not say whether it " \
                        f"tracks them\n{text}"
    assert r.returncode != 0, f"`rmx sync` exited 0 on a failing ls-files\n{text}"
    errs = _errors(r.stderr)
    assert len(errs) == 1, f"expected exactly one `Error:` line, got {errs}\n{text}"
    low = errs[0].lower()
    head = _refusal_head(repo.store / "catalog.duckdb")
    assert head in errs[0], f"the refusal does not start `{head}`: {errs[0]!r}"
    assert "ls-files exited" in low and ("untrack" in low or "rm --cached" in low) \
        and "daemon" in low, \
        f"the refusal does not name the failing ls-files (with its exit code) and both " \
        f"remedies: {errs[0]!r}"


# =============================================================================================
# E1: the store's repository answers, not the hook's
# =============================================================================================

def _make_tracked_store_repo(proj: Path, repo: Repo) -> Path:
    """`proj` becomes a repo whose store (legacy `catalog.duckdb`) is committed."""
    proj.mkdir()
    _quiet(proj, repo, "init", "-q", "--template=", "-b", "main")
    store = proj / ".refmatrix"
    s = Store(store)
    s.init()
    s.close()
    (proj / "b.txt").write_text("b\n", encoding="utf-8")
    _quiet(proj, repo, "add", "-A")
    _quiet(proj, repo, "commit", "-q", "-m", "B: the store committed")
    ls = subprocess.run(["git", "-C", str(proj), "ls-files", ".refmatrix/catalog.duckdb"],
                        env=_base_env(), capture_output=True, text=True, timeout=60)
    assert ls.stdout.split() == [".refmatrix/catalog.duckdb"], f"fixture: B tracks {ls.stdout!r}"
    return store


@pytest.fixture
def two_repos():
    """Repo A (`proj`, store ignored) with a linked worktree `wt` that holds its own ignored
    store (so the generated gate lets the hook through), the generated hooks, and a shim that
    records `$GIT_DIR`. Repo B (`b`) whose store's catalog is COMMITTED. No daemon anywhere."""
    base = Path(tempfile.mkdtemp(prefix="b212e-", dir="/tmp")).resolve()
    r = Repo(base)
    try:
        r.proj.mkdir()
        _quiet(r.proj, r, "init", "-q", "--template=", "-b", "main")
        (r.proj / ".gitignore").write_text(".refmatrix/\n", encoding="utf-8")
        (r.proj / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
        _quiet(r.proj, r, "add", "-A")
        _quiet(r.proj, r, "commit", "-q", "-m", "A c0")
        wt = base / "wt"
        _quiet(r.proj, r, "worktree", "add", "-q", "-b", "feature", str(wt), "main")
        s = Store(wt / ".refmatrix")
        s.init()
        s.close()
        hooks_mod._install_git_hooks(r.proj, apply=True, force=True)
        r.bindir.mkdir()
        entry = r.bindir / "rmx_entry.py"
        entry.write_text("import sys\nfrom refmatrix.cli import cli_entry\nsys.exit(cli_entry())\n",
                         encoding="utf-8")
        shim = r.bindir / "rmx"
        shim.write_text("#!/bin/sh\n"
                        f"printf '%s\\t%s\\t%s\\n' \"$PWD\" \"${{GIT_DIR-<unset>}}\" \"$*\" "
                        f">> '{r.calls_log}'\n"
                        f"exec '{sys.executable}' '{entry}' \"$@\"\n", encoding="utf-8")
        shim.chmod(0o755)
        b_store = _make_tracked_store_repo(base / "b", r)
        yield r, wt, b_store
    finally:
        dm.stop_daemon(base / "b" / ".refmatrix")
        shutil.rmtree(base, ignore_errors=True)


def _git_dir_calls(repo: Repo) -> list[tuple[str, str, str]]:
    if not repo.calls_log.exists():
        return []
    out = []
    for ln in repo.calls_log.read_text(encoding="utf-8").splitlines():
        pwd, git_dir, argv = (ln.split("\t", 2) + ["", ""])[:3]
        out.append((pwd, git_dir, argv))
    return out


def test_git_tracked_catalogs_ignores_a_foreign_git_dir_in_the_environment(two_repos,
                                                                          monkeypatch):
    """E1, the function: with A's worktree `GIT_DIR` (absolute) in the environment, the answer
    for B's store is B's -- its committed `catalog.duckdb` -- not what A's index says."""
    repo, wt, b_store = two_repos
    gd = subprocess.run(["git", "-C", str(wt), "rev-parse", "--absolute-git-dir"],
                        env=_base_env(), capture_output=True, text=True, timeout=60).stdout.strip()
    assert "/worktrees/" in gd, f"fixture: not a linked worktree's git dir: {gd}"
    monkeypatch.setenv("GIT_DIR", gd)
    assert store_mod.git_tracked_catalogs(b_store) == ["catalog.duckdb"], \
        "git_tracked_catalogs answered from the hook's repository (GIT_DIR in the env), not " \
        "from the repository that contains the store"


@pytest.mark.timeout(300)
def test_a_worktree_hook_of_one_repo_cannot_vouch_for_a_store_in_another(two_repos):
    """E1, end to end: `REFMATRIX_ROOT` names B's store; a commit in A's worktree fires the
    generated post-commit, which runs `rmx sync` with A's absolute `GIT_DIR` exported. B's
    catalog is tracked, so the in-process sync into it is refused, loudly, bytes unchanged."""
    repo, wt, b_store = two_repos
    (wt / "w.py").write_text("def w():\n    return 3\n", encoding="utf-8")
    _quiet(wt, repo, "add", "w.py")
    before = _digests(b_store)
    env = {**_hook_env(repo), "REFMATRIX_ROOT": str(b_store)}
    r = subprocess.run(["git", "-C", str(wt), "commit", "-q", "-m", "commit in A's worktree"],
                       env=env, capture_output=True, text=True, timeout=240)
    calls = _git_dir_calls(repo)
    text = f"exit {r.returncode}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}\nrmx calls: {calls}"
    assert r.returncode == 0, f"the commit itself failed\n{text}"
    syncs = [c for c in calls if c[2].startswith("sync")]
    assert syncs, f"fixture: post-commit in A's worktree ran no `rmx sync`\n{text}"
    git_dir = syncs[0][1]
    assert git_dir.startswith("/") and "/worktrees/" in git_dir, \
        f"fixture: the worktree hook did not export an absolute GIT_DIR (got {git_dir!r}); " \
        f"this is not the E1 shape\n{text}"
    changed = _changed(before, _digests(b_store))
    assert TRACEBACK not in r.stderr, f"the hook's rmx crashed\n{text}"
    assert not changed, (f"the in-process sync wrote B's git-tracked {changed}: the tracked-"
                         f"catalog check read A's repository through the exported GIT_DIR\n{text}")
    target = b_store / "catalog.duckdb"
    assert len(_refusal_lines(r.stderr, target)) == 1 and FAILED_LINE in r.stderr, \
        f"the refusal was not loud (one `Error:` `{_refusal_head(target)} ...` + the remedy, " \
        f"then `{FAILED_LINE}`)\n{text}"
    assert _status_refmatrix_catalogs(b_store.parent) == "", "git sees B's catalog modified"


# =============================================================================================
# W1: the vanished-cwd remedy never tells the user to set what they already set
# =============================================================================================

def test_the_cwd_gone_remedy_depends_on_refmatrix_root(monkeypatch):
    """W1, the function: unset -> "set REFMATRIX_ROOT" is offered; set -> it is not."""
    from refmatrix.workdir import cwd_gone_message
    monkeypatch.delenv("REFMATRIX_ROOT", raising=False)
    assert "set REFMATRIX_ROOT" in cwd_gone_message(), cwd_gone_message()
    monkeypatch.setenv("REFMATRIX_ROOT", "/tmp/somewhere/.refmatrix")
    msg = cwd_gone_message()
    assert "set REFMATRIX_ROOT" not in msg, \
        f"with REFMATRIX_ROOT already set the remedy still says to set it: {msg!r}"
    assert "exist" in msg.lower(), f"the remedy does not say to cd to an existing dir: {msg!r}"


@pytest.fixture
def w1_store():
    base = Path(tempfile.mkdtemp(prefix="b212w-", dir="/tmp")).resolve()
    root = base / "st" / ".refmatrix"
    s = Store(root)
    s.init()
    s.close()
    try:
        yield base, root
    finally:
        shutil.rmtree(base, ignore_errors=True)


@pytest.mark.timeout(120)
@pytest.mark.parametrize("root_set", [True, False], ids=["root-set", "root-unset"])
def test_a_vanished_cwd_error_offers_refmatrix_root_only_when_unset(w1_store, root_set):
    """W1, end to end (`rmx stats` in a deleted cwd): the one `Error:` line names the gone
    directory; it says "set REFMATRIX_ROOT" exactly when REFMATRIX_ROOT is unset."""
    base, root = w1_store
    env = _base_env()
    if root_set:
        env["REFMATRIX_ROOT"] = str(root)
    r = _vanished([sys.executable, str(_entry(base)), "stats"], env)
    text = f"exit {r.returncode}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    assert TRACEBACK not in r.stderr and r.returncode != 0, text
    errs = _errors(r.stderr)
    assert len(errs) == 1 and "director" in errs[0].lower(), \
        f"expected one `Error:` line naming the gone working directory\n{text}"
    if root_set:
        assert "set REFMATRIX_ROOT" not in errs[0], \
            f"REFMATRIX_ROOT is set and the remedy still says to set it: {errs[0]!r}"
    else:
        assert "set REFMATRIX_ROOT" in errs[0], \
            f"REFMATRIX_ROOT is unset and the remedy does not offer it: {errs[0]!r}"


@pytest.mark.timeout(120)
@pytest.mark.parametrize("root_set", [True, False], ids=["root-set", "root-unset"])
def test_cctree_in_a_vanished_cwd_says_pass_project(w1_store, root_set):
    """W1, cctree: its remedy is its own flag. `rmx cctree` in a deleted cwd says
    "pass --project", and never "set REFMATRIX_ROOT" (cctree does not read it)."""
    base, root = w1_store
    env = _base_env()
    if root_set:
        env["REFMATRIX_ROOT"] = str(root)
    r = _vanished([sys.executable, str(_entry(base)), "cctree"], env)
    text = f"exit {r.returncode}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    assert TRACEBACK not in r.stderr and r.returncode != 0, text
    errs = _errors(r.stderr)
    assert len(errs) == 1, f"expected one `Error:` line\n{text}"
    assert "pass --project" in errs[0] and "set REFMATRIX_ROOT" not in errs[0], \
        f"cctree's remedy is not `pass --project`: {errs[0]!r}"


# =============================================================================================
# a2 at the write control point: every in-process writer refuses a git-tracked catalog
# =============================================================================================

_MEMORY_FILE = """---
gmd: "0.1"
id: feedback_bug212_r2_probe
title: "bug-212 r2 probe memory"
tags: [feedback, probe]
metadata:
  node_type: memory
  type: feedback
---

# bug-212 r2 probe memory {#root}

A probe body for the write-control-point refusal (bug-212 r2).
"""

WRITERS = ["ingest", "memory-add", "bridge"]


def _writer_argv(writer: str, proj: Path, base: Path) -> list[str]:
    """The CLI argv for one in-process writer, with its input made under `proj` / `base`."""
    if writer == "ingest":
        pkg = proj / "pkg"
        pkg.mkdir(exist_ok=True)
        (pkg / "mod_r2.py").write_text("def mod_r2():\n    return 7\n", encoding="utf-8")
        return ["ingest", str(pkg)]
    if writer == "memory-add":
        return ["memory", "add", "bug212_r2_probe", "-c", "a probe body (bug-212 r2)"]
    assert writer == "bridge"
    memdir = base / "memdir"
    memdir.mkdir(exist_ok=True)
    (memdir / "feedback_bug212_r2_probe.md").write_text(_MEMORY_FILE, encoding="utf-8")
    return ["ingest-gmd", "--as-memory", str(memdir)]


def _landed(writer: str, store: Path, proj: Path) -> bool:
    """Did the writer's row reach the catalog (read after the process exited; no daemon)?"""
    s = Store(store)
    try:
        con = s._connect()
        if writer == "ingest":
            n = con.execute("SELECT count(*) FROM entities WHERE path = ?",
                            (str(proj / "pkg" / "mod_r2.py"),)).fetchone()[0]
        elif writer == "memory-add":
            n = con.execute("SELECT count(*) FROM entities WHERE kind = 'memory' AND name = ?",
                            ("bug212_r2_probe",)).fetchone()[0]
        else:
            n = con.execute("SELECT count(*) FROM entities WHERE kind = 'memory' AND "
                            "(name LIKE ? OR path LIKE ?)",
                            ("%bug212_r2_probe%", "%feedback_bug212_r2_probe%")).fetchone()[0]
    finally:
        s.close()
    return int(n) > 0


def _run_writer(writer: str, proj: Path, base: Path) -> subprocess.CompletedProcess:
    argv = _writer_argv(writer, proj, base)
    return subprocess.run([sys.executable, str(_entry(base)), *argv], cwd=str(proj),
                          env=_base_env(), capture_output=True, text=True, timeout=240)


@pytest.mark.timeout(300)
@pytest.mark.parametrize("writer", WRITERS)
def test_every_in_process_writer_refuses_a_git_tracked_catalog(tracked_repo, writer):
    """a2 at `_store_rw()`: no daemon, cwd = the main checkout of a repo that commits its
    catalog. The writer refuses with ONE `Error:` line naming the file the write would land in
    and both remedies (untrack it, or start the daemon), exit non-zero, catalog bytes
    unchanged, `git status` clean."""
    repo, layout = tracked_repo
    assert not dm.ping(repo.store), "fixture: a daemon answers"
    before = _digests(repo.store)
    r = _run_writer(writer, repo.proj, repo.base)
    text = f"exit {r.returncode}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    changed = _changed(before, _digests(repo.store))
    assert TRACEBACK not in r.stderr, f"[{layout}] `{writer}` crashed\n{text}"
    assert not changed, (f"[{layout}] in-process `{writer}` wrote the git-tracked catalog "
                         f"{changed} (exit {r.returncode})\n{text}")
    assert r.returncode != 0, f"[{layout}] `{writer}` on a tracked catalog exited 0\n{text}"
    errs = _errors(r.stderr)
    target = repo.store / _target_catalog(layout)
    assert len(errs) == 1 and _refusal_lines(r.stderr, target) == errs, \
        f"[{layout}] `{writer}`: expected ONE `Error:` line `{_refusal_head(target)} ...` " \
        f"with the remedy (untrack it, or start the daemon); got {errs}\n{text}"
    assert _status_refmatrix_catalogs(repo.proj) == "", \
        f"[{layout}] git sees the tracked catalog modified after `{writer}`"


def test_the_write_control_point_itself_refuses_a_git_tracked_catalog(tracked_repo,
                                                                     monkeypatch):
    """a2: the refusal lives IN `cli._store_rw()` -- the one in-process writer every command
    reaches -- not per command. Called directly on a tracked store, it raises a
    `ClickException` `refusing to open <full target path> read-write in-process: ...` BEFORE
    the catalog opens; the bytes are unchanged.

    "Before it opens" is observed, not inferred from the bytes (GREEN r2 mutation K5 -- a
    `s._connect()` ahead of the refusal -- left the bytes unchanged and passed this test; only
    the subprocess writers caught it): `Store._connect` is wrapped by a RECORDER that calls the
    real method and notes the catalog it opened. A double of a collaborator, not of the SUT
    (registered in workflow/test_mock_registry.md); no connect may name this store's catalog."""
    import click

    from refmatrix import cli
    repo, layout = tracked_repo
    monkeypatch.setenv("REFMATRIX_ROOT", str(repo.store))
    monkeypatch.chdir(repo.proj)
    connects: list[str] = []
    real_connect = Store._connect

    def recording_connect(self, *a, **kw):
        connects.append(str(getattr(self, "db_path", "?")))
        return real_connect(self, *a, **kw)

    monkeypatch.setattr(Store, "_connect", recording_connect)
    before = _digests(repo.store)
    opened = None
    try:
        with pytest.raises(click.ClickException) as ei:
            opened = cli._store_rw()
    finally:
        if opened is not None:
            opened.close()
    target = repo.store / _target_catalog(layout)
    assert _refusal_head(target) in ei.value.message, \
        f"[{layout}] the refusal does not start `{_refusal_head(target)}`: {ei.value.message!r}"
    opened_here = [c for c in connects if Path(c).parent == repo.store]
    assert not opened_here, \
        f"[{layout}] `_store_rw()` connected to {opened_here} BEFORE refusing: the refusal " \
        f"must come before the catalog opens"
    assert _changed(before, _digests(repo.store)) == [], f"[{layout}] the catalog changed"


# A READ with no replica file and no daemon reaches `_store_rw()` too: `_read_store()` ->
# `_reader_store()` finds no replica -> `_store()` -> `_store_rw()`, which opens the WRITER
# catalog read-write and flushes on close. Refusing that on a tracked catalog is correct
# (fail-closed; lead ruling on GREEN r2 flag 5, 2026-11-13), but the line must not claim a
# write -- hence "open ... read-write".
#
# Measured 2026-11-13 at ed36b6a: "no catalog.read.duckdb" alone does NOT reach that path.
# `cli._replica_reader_path()` falls back to the INACTIVE slot (`active` marker) or to the
# legacy `catalog.duckdb`, and opens it read-only -- so in `tracked_repo`'s two layouts a read
# is served (`pairs show` exit 0, bytes unchanged). The fall-through needs every reader file
# absent: `active` = A with only `catalog.A.duckdb` on disk (no B, no legacy file, no snapshot,
# no `read_only.duckdb`). That is the RED fixture; the two common layouts are the GUARD.
READ_ARGVS = [["pairs", "show", "foo_bar"], ["memory", "get", "bug212_r2_absent"]]


@pytest.fixture
def slot_only_tracked_repo():
    """A repo whose committed store is ONE rotation slot: `active` = A, `catalog.A.duckdb`, and
    no other catalog or reader file. No daemon. Short resolved `/tmp` root."""
    base = Path(tempfile.mkdtemp(prefix="b212r-", dir="/tmp")).resolve()
    r = Repo(base)
    try:
        r.proj.mkdir()
        _quiet(r.proj, r, "init", "-q", "--template=", "-b", "main")
        r.store.mkdir()
        (r.store / "CLAUDE.md").write_text(CLAUDE_MD, encoding="utf-8")
        s = Store(r.store)
        s.init()
        s.close()
        legacy = r.store / "catalog.duckdb"
        shutil.copyfile(legacy, r.store / "catalog.A.duckdb")
        legacy.unlink()
        (r.store / "active").write_text("A\n", encoding="utf-8")
        for name in ("catalog.B.duckdb", "catalog.duckdb", "catalog.read.duckdb",
                     "read_only.duckdb"):
            assert not (r.store / name).exists(), f"fixture: {name} exists"
        _quiet(r.proj, r, "add", "-A")
        _quiet(r.proj, r, "commit", "-q", "-m", "c0 (one slot committed)")
        assert store_mod.git_tracked_catalogs(r.store) == ["catalog.A.duckdb"], \
            "fixture: catalog.A.duckdb is not tracked"
        yield r
    finally:
        dm.stop_daemon(r.store)
        shutil.rmtree(base, ignore_errors=True)


def _run_read(repo: Repo, argv: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(_entry(repo.base)), *argv], cwd=str(repo.proj),
                          env=_base_env(), capture_output=True, text=True, timeout=240)


@pytest.mark.timeout(300)
@pytest.mark.parametrize("argv", READ_ARGVS, ids=["pairs-show", "memory-get"])
def test_a_read_with_no_replica_on_a_tracked_catalog_is_refused_as_an_open(
        slot_only_tracked_repo, argv):
    """GREEN r2 flag 5, lead ruling: no reader file of any kind, no daemon, a tracked catalog.
    The read falls to the writer catalog through `_store_rw()`; it is refused with ONE
    `Error:` line `refusing to open <full target path> read-write in-process: ...` (both
    remedies), exit non-zero, catalog bytes unchanged -- and the line does not say "write"."""
    repo = slot_only_tracked_repo
    assert not dm.ping(repo.store), "fixture: a daemon answers"
    before = _digests(repo.store)
    r = _run_read(repo, argv)
    text = f"exit {r.returncode}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    changed = _changed(before, _digests(repo.store))
    assert TRACEBACK not in r.stderr, f"`rmx {' '.join(argv)}` crashed\n{text}"
    assert not changed, f"`rmx {' '.join(argv)}` (a read) changed the tracked catalog " \
                        f"{changed}\n{text}"
    assert r.returncode != 0, f"`rmx {' '.join(argv)}` exited 0\n{text}"
    errs = _errors(r.stderr)
    target = repo.store / "catalog.A.duckdb"
    assert len(errs) == 1 and _refusal_lines(r.stderr, target) == errs, \
        f"`rmx {' '.join(argv)}`: expected ONE `Error:` line `{_refusal_head(target)} ...` " \
        f"with both remedies; got {errs}\n{text}"
    assert "in-process write" not in errs[0], f"a READ's refusal claims a write: {errs[0]!r}"


@pytest.mark.timeout(300)
def test_a_read_on_a_tracked_store_with_a_reader_file_is_served_not_refused(tracked_repo):
    """GUARD (passes at ed36b6a) against an over-broad fix: in `tracked_repo`'s layouts a
    reader file exists (the inactive slot, or the legacy catalog), so `rmx pairs show` is served
    read-only from it -- exit 0, no refusal line, catalog bytes unchanged."""
    repo, layout = tracked_repo
    assert not dm.ping(repo.store), "fixture: a daemon answers"
    before = _digests(repo.store)
    r = _run_read(repo, ["pairs", "show", "foo_bar"])
    text = f"exit {r.returncode}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    assert r.returncode == 0 and TRACEBACK not in r.stderr and not _errors(r.stderr), \
        f"[{layout}] a read with a reader file on disk failed\n{text}"
    assert _changed(before, _digests(repo.store)) == [], f"[{layout}] the read changed the catalog"


@pytest.fixture(params=["no-repo", "ignored"])
def writable_store(request):
    """GUARD fixture: a store `proj/.refmatrix` that is in no git repository, or in one whose
    `.gitignore` ignores `.refmatrix/` (the catalog is untracked)."""
    kind = request.param
    base = Path(tempfile.mkdtemp(prefix="b212g-", dir="/tmp")).resolve()
    r = Repo(base)
    try:
        r.proj.mkdir()
        if kind == "ignored":
            _quiet(r.proj, r, "init", "-q", "--template=", "-b", "main")
            (r.proj / ".gitignore").write_text(".refmatrix/\n", encoding="utf-8")
        s = Store(r.store)
        s.init()
        s.close()
        if kind == "ignored":
            _quiet(r.proj, r, "add", "-A")
            _quiet(r.proj, r, "commit", "-q", "-m", "c0 (store ignored)")
            assert store_mod.git_tracked_catalogs(r.store) == [], "fixture: catalog tracked"
        else:
            probe = subprocess.run(["git", "-C", str(r.proj), "rev-parse", "--git-dir"],
                                   env=_base_env(), capture_output=True, text=True)
            assert probe.returncode != 0, f"fixture: {r.proj} is inside a git repo"
        yield r, kind
    finally:
        dm.stop_daemon(r.store)
        shutil.rmtree(base, ignore_errors=True)


@pytest.mark.timeout(300)
@pytest.mark.parametrize("writer", WRITERS)
def test_every_in_process_writer_still_writes_an_untracked_catalog(writable_store, writer):
    """GUARD (passes at HEAD) against an over-broad fix: a store in no repository, or with an
    ignored catalog, is written in-process -- exit 0, no `Error:` line, the row lands."""
    repo, kind = writable_store
    assert not dm.ping(repo.store), "fixture: a daemon answers"
    r = _run_writer(writer, repo.proj, repo.base)
    text = f"exit {r.returncode}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    assert r.returncode == 0 and TRACEBACK not in r.stderr and not _errors(r.stderr), \
        f"[{kind}] in-process `{writer}` on an untracked catalog failed\n{text}"
    assert _landed(writer, repo.store, repo.proj), \
        f"[{kind}] in-process `{writer}` exited 0 but its row is not in the catalog\n{text}"
