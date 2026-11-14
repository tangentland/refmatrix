"""bug-212 r4 RED: ch-bsd r2 (`workflow/bullshit/2026-11-13-1556-bug212-r2-r3-67f55cb.md`, DIRTY
1B/1S/4M, NO-GO) and the lead's ruling L72 (`workflow/plan-review-2026-11-13.md`, 2026-11-13).

WHY each group exists:

b-1 (BULLSHIT). r2 put the tracked-catalog refusal in `cli._store_rw()` on the premise that it is
    "the one in-process write control point". It is not: `verbs.local_write` is a second
    no-daemon writer (every `_write_or_local` / `_matrix_write` verb: `rmx add concept|entity`,
    `rmx protect|noise|...`), and four sites hand-roll `Store(root)` read-write
    (`mcp._t_memory_add`, `handoff._promote_digest`, `verbs.change_subject`, `cli.init`). On a
    store whose catalog git tracks, with no daemon, every one of them wrote the committed file
    (` M .refmatrix/catalog*`). The RED suite of r2 covered only the writers that happened to
    reach `_store_rw()`. L72: ONE store-level check, called by `_store_rw()` and `local_write`;
    the four copies route through `local_write`; an AST test fails when `src/` adds a read-write
    `Store(` outside an allowlist. A docstring that says "every writer" is a census claim -- so
    the census is a test here, not a sentence.
m-1. The read fall-through refusal's tail said "the write would modify a committed file ... so the
    write goes through it" for a READ. The read test now forbids "the write" as well as
    "in-process write" (the edit lives in `tests/test_bug212_r2_red.py`).
m-3. Neither git call in `store.git_tracked_catalogs` had a timeout: a hanging git (stuck mount,
    fsmonitor) hung every in-process writer, silently. L72: `timeout=10` on both calls; a
    timeout raises `TrackedCatalogCheckError` (fail closed, loud). A `git` PATH shim that sleeps
    stands in for the hang (registered, `external`).
m-4. A `git rev-parse` failure was read as "not in a repository" -> `[]` -> write (fail-open):
    a corrupted `.git/HEAD` in a repo that tracks the catalog let the write through. L72: only
    "no `.git` anywhere at or above the store dir" is `[]`. Also: the env strip on `rev-parse`
    was unpinned (mutation X3 survived 117/117); `GIT_DIR=/nonexistent` in the env pins it.

Everything is real: git, the CLI (a console-script-shaped entry file), the MCP stdio server, the
store. Stand-in: the sleeping `git` shim (m-3 only).
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from refmatrix import daemon as dm
from refmatrix import store as store_mod
from refmatrix.store import WRITER_CATALOG_FILES, Store
from tests.test_bug212_hooks_in_worktrees import (
    TRACEBACK, Repo, _base_env, _entry, _quiet,
)
from tests.test_bug212_r1_remedy import (  # noqa: F401 -- `tracked_repo` is used by name
    _refusal_head, _refusal_lines, _status_refmatrix_catalogs, _target_catalog, tracked_repo,
)

SRC = Path(__file__).resolve().parents[1] / "src" / "refmatrix"


def _digests(store: Path) -> dict[str, str]:
    return {n: hashlib.sha256((store / n).read_bytes()).hexdigest()
            for n in WRITER_CATALOG_FILES if (store / n).exists()}


def _changed(before: dict[str, str], after: dict[str, str]) -> list[str]:
    return sorted(n for n in before if after.get(n) != before[n])


def _errors(stderr: str) -> list[str]:
    return [ln for ln in stderr.splitlines() if ln.startswith("Error:")]


def _cli(repo: Repo, argv: list[str], env: "dict | None" = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(_entry(repo.base)), *argv], cwd=str(repo.proj),
                          env=env or _base_env(), capture_output=True, text=True, timeout=240)


def _assert_refused_cli(repo: Repo, layout: str, what: str, r: subprocess.CompletedProcess,
                        before: dict[str, str]) -> None:
    """The r2/r3 contract, for any in-process opener: no traceback; catalog bytes unchanged;
    exit non-zero; exactly ONE `Error:` line `refusing to open <full target> read-write
    in-process: ...` with both remedies; `git status` shows no catalog modified."""
    text = f"exit {r.returncode}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    changed = _changed(before, _digests(repo.store))
    status = _status_refmatrix_catalogs(repo.proj)
    assert TRACEBACK not in r.stderr, f"[{layout}] {what} crashed\n{text}"
    assert not changed and status == "", (
        f"[{layout}] {what} wrote the git-tracked catalog {changed} (exit {r.returncode})\n"
        f"git status:\n{status}\n{text}")
    assert r.returncode != 0, f"[{layout}] {what} on a tracked catalog exited 0\n{text}"
    target = repo.store / _target_catalog(layout)
    errs = _errors(r.stderr)
    assert len(errs) == 1 and _refusal_lines(r.stderr, target) == errs, (
        f"[{layout}] {what}: expected ONE `Error:` line `{_refusal_head(target)} ...` with both "
        f"remedies; got {errs}\n{text}")


# =============================================================================================
# b-1: every in-process opener refuses a git-tracked catalog, not only the `_store_rw()` ones
# =============================================================================================

SEED = "bug212_r4_seed"
EMPTY_PARTITION = "bug212r4empty"


def _seed_and_commit(repo: Repo) -> None:
    """Put a concept `SEED` (a target for `protect` / `noise`) and an empty partition
    `EMPTY_PARTITION` (a target for `partition drop`) in the committed store, and commit the
    catalog again, hooks off: the catalog is tracked AND clean before the op."""
    s = Store(repo.store)
    try:
        s.add_concept(SEED)
        with s.with_partition(EMPTY_PARTITION):   # registers an empty partition row
            pass
    finally:
        s.close()
    _quiet(repo.proj, repo, "add", "-A", ".refmatrix")
    _quiet(repo.proj, repo, "commit", "-q", "-m", "seed a concept")
    assert _status_refmatrix_catalogs(repo.proj) == "", "fixture: catalog dirty after seeding"


CLI_WRITERS = {
    "add-concept": ["add", "concept", "bug212_r4_new"],
    "add-entity": ["add", "entity", "bug212_r4_doc", "--kind", "doc"],
    "protect": ["protect", SEED],
    "noise": ["noise", SEED],
    "focus-change-subject": ["focus", "change-subject", "bug212 r4 subject", "-s",
                             "bug212-r4-session"],
    "init": ["init", "--no-hooks", "--no-agents"],
    # Found by this file's census, not by ch-bsd r2's: `partition drop` with no daemon opens
    # `Store` imported as `_Store` (cli.py `partition_drop`) and DELETEs the partition row.
    "partition-drop": ["partition", "drop", EMPTY_PARTITION, "-y"],
}


@pytest.mark.timeout(300)
@pytest.mark.parametrize("writer", list(CLI_WRITERS))
def test_every_cli_writer_outside_store_rw_refuses_a_git_tracked_catalog(tracked_repo, writer):
    """b-1: the CLI writers that reach `verbs.local_write` (`add concept|entity`, `protect`,
    `noise`) or hand-roll `Store(...)` (`focus change-subject` -> `verbs.change_subject`;
    `init`; `partition drop`), run in-process (no daemon) in the main checkout of a repo that commits its
    catalog. At 67f55cb every one of them writes the committed file."""
    repo, layout = tracked_repo
    assert not dm.ping(repo.store), "fixture: a daemon answers"
    _seed_and_commit(repo)
    before = _digests(repo.store)
    argv = list(CLI_WRITERS[writer])
    r = _cli(repo, argv)
    _assert_refused_cli(repo, layout, f"`rmx {' '.join(argv)}`", r, before)


@pytest.mark.timeout(300)
def test_the_mcp_memory_add_fallback_refuses_a_git_tracked_catalog(tracked_repo):
    """b-1: MCP `rmx_memory_add` with no daemon falls back to `mcp._t_memory_add`'s own
    `Store(root)`. On a tracked catalog the tool call must come back `isError` carrying the
    refusal (`refusing to open <full target> read-write in-process: ...`, both remedies), the
    server keeps serving, and the catalog bytes are unchanged."""
    repo, layout = tracked_repo
    assert not dm.ping(repo.store), "fixture: a daemon answers"
    before = _digests(repo.store)
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": "rmx_memory_add",
                        "arguments": {"name": "bug212_r4_mcp",
                                      "content": "probe (bug-212 r4)"}}},
            {"jsonrpc": "2.0", "id": 3, "method": "ping"}]
    stdin = "".join(json.dumps(m) + "\n" for m in msgs)
    r = subprocess.run([sys.executable, str(_entry(repo.base)), "mcp"], cwd=str(repo.proj),
                       env=_base_env(), input=stdin, capture_output=True, text=True,
                       timeout=240)
    text = f"exit {r.returncode}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    replies = {}
    for ln in r.stdout.splitlines():
        try:
            m = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if isinstance(m, dict) and "id" in m:
            replies[m["id"]] = m
    assert 2 in replies and 3 in replies, f"the MCP server stopped answering\n{text}"
    res = replies[2].get("result") or {}
    body = " ".join(c.get("text", "") for c in res.get("content", []))
    changed = _changed(before, _digests(repo.store))
    assert not changed and _status_refmatrix_catalogs(repo.proj) == "", \
        f"[{layout}] MCP rmx_memory_add wrote the git-tracked catalog {changed}: {body!r}"
    target = repo.store / _target_catalog(layout)
    low = body.lower()
    assert res.get("isError") is True and _refusal_head(target) in body \
        and ("untrack" in low or "rm --cached" in low) and "daemon" in low, \
        f"[{layout}] MCP rmx_memory_add did not come back as the refusal: " \
        f"isError={res.get('isError')} body={body!r}"


_PROMOTE_PROBE = r"""
import json, sys
from pathlib import Path
from refmatrix import handoff, stm
root = Path(sys.argv[1])
s = stm.Stm(root, "bug212-r4-promote")
s.record("note", "a focus event for the bug-212 r4 promote probe")
print(json.dumps(handoff._promote_digest(root, s), default=str))
"""


@pytest.mark.timeout(300)
def test_the_save_state_promote_fallback_refuses_a_git_tracked_catalog(tracked_repo):
    """b-1: `handoff._promote_digest` (save-state's STM promote) with no daemon opens
    `Store(root)` itself. Its contract is "never raises; returns {"error"}" -- so on a tracked
    catalog it must return `{"error": <the refusal>}` and no `id`, catalog bytes unchanged."""
    repo, layout = tracked_repo
    assert not dm.ping(repo.store), "fixture: a daemon answers"
    probe = repo.base / "promote_probe.py"
    probe.write_text(_PROMOTE_PROBE, encoding="utf-8")
    before = _digests(repo.store)
    r = subprocess.run([sys.executable, str(probe), str(repo.store)], cwd=str(repo.proj),
                       env=_base_env(), capture_output=True, text=True, timeout=240)
    text = f"exit {r.returncode}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    assert r.returncode == 0, f"the promote probe itself failed\n{text}"
    out = json.loads(r.stdout.strip().splitlines()[-1])
    changed = _changed(before, _digests(repo.store))
    assert not changed and _status_refmatrix_catalogs(repo.proj) == "", \
        f"[{layout}] the promote wrote the git-tracked catalog {changed}: {out}"
    target = repo.store / _target_catalog(layout)
    assert "id" not in out and _refusal_head(target) in str(out.get("error", "")), \
        f"[{layout}] the promote did not return the refusal as its error: {out}"


# =============================================================================================
# b-1 bypass guard: the census of read-write `Store(` constructions in src/
# =============================================================================================

# Read-write `Store(` constructions that may exist, by `module:qualname`. Everything else in
# src/ must go through one of the two CHECKED openers. Why each is allowed:
CHECKED_OPENERS = {
    "cli:_store_rw",          # the CLI's in-process writer (L72: calls the store-level check)
    "verbs:local_write",      # the verbs' in-process writer (L72: calls the store-level check)
}
UNCHECKED_ALLOWED = {
    # The daemon IS the single writer; a tracked catalog written through it is the accepted
    # route (lead decisions a1/a2; only bug-214's untracking removes it).
    "daemon:Daemon._reopen_writer",
    "daemon:Daemon.serve_forever",
    "daemon:Daemon._bootstrap_rotation_if_needed",
    # The hub's global store (`~/.refmatrix/global`), created and owned by the hub.
    "hub:_bootstrap_global_store",
    # The canon partition opened from inside an already-open writer of the same store.
    "store:Store.link_canon",
}


def _store_aliases(tree: ast.AST) -> set[str]:
    """Every name `Store` is bound to in a module: `Store` itself, `import Store as X`, and
    `X = Store` / `X = <mod>.Store`. cli.py's `partition_drop` opens `Store` imported as
    `_Store` -- a scanner keyed on the literal name missed it."""
    names = {"Store"}
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom):
            names |= {a.asname for a in n.names if a.name == "Store" and a.asname}
        elif isinstance(n, ast.Assign) and (
                (isinstance(n.value, ast.Name) and n.value.id == "Store")
                or (isinstance(n.value, ast.Attribute) and n.value.attr == "Store")):
            names |= {t.id for t in n.targets if isinstance(t, ast.Name)}
    return names


def _read_write_store_constructions() -> list[tuple[str, int]]:
    """Every call of `Store` -- under any name it is bound to in the module, or as
    `<mod>.Store` -- in src/refmatrix without a literal `read_only=True`, as
    (`module:qualname`, line)."""
    found: list[tuple[str, int]] = []
    for p in sorted(SRC.rglob("*.py")):
        mod = ".".join(p.relative_to(SRC).with_suffix("").parts)
        tree = ast.parse(p.read_text(encoding="utf-8"), str(p))
        aliases = _store_aliases(tree)
        stack: list[str] = []

        class V(ast.NodeVisitor):
            def visit_FunctionDef(self, n):
                stack.append(n.name)
                self.generic_visit(n)
                stack.pop()
            visit_AsyncFunctionDef = visit_FunctionDef
            visit_ClassDef = visit_FunctionDef

            def visit_Call(self, n):
                f = n.func
                hit = ((isinstance(f, ast.Name) and f.id in aliases)
                       or (isinstance(f, ast.Attribute) and f.attr == "Store"))
                if hit:
                    ro = {k.arg: k.value for k in n.keywords}.get("read_only")
                    if not (isinstance(ro, ast.Constant) and ro.value is True):
                        found.append((f"{mod}:{'.'.join(stack) or '<module>'}", n.lineno))
                self.generic_visit(n)

        V().visit(tree)
    return found


def _functions_calling(names: set[str], *, module: "str | None" = None) -> set[str]:
    """Top-level function and method names (bare) whose body calls any of `names` directly
    (as `f(...)` or `x.f(...)`); restricted to `module` (`store` for store.py) when given."""
    out: set[str] = set()
    for p in sorted(SRC.rglob("*.py")):
        mod = ".".join(p.relative_to(SRC).with_suffix("").parts)
        if module is not None and mod != module:
            continue
        for fn in ast.walk(ast.parse(p.read_text(encoding="utf-8"), str(p))):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for n in ast.walk(fn):
                if isinstance(n, ast.Call):
                    f = n.func
                    nm = f.id if isinstance(f, ast.Name) else (
                        f.attr if isinstance(f, ast.Attribute) else None)
                    if nm in names:
                        out.add(fn.name)
                        break
    return out


def _calls_in(module: str, qualname: str) -> set[str]:
    p = SRC / f"{module.replace('.', '/')}.py"
    tree = ast.parse(p.read_text(encoding="utf-8"), str(p))
    parts = qualname.split(".")
    body = tree.body
    node = None
    for part in parts:
        node = next(n for n in body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef,
                                                      ast.ClassDef)) and n.name == part)
        body = node.body
    calls = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            f = n.func
            calls.add(f.id if isinstance(f, ast.Name) else (
                f.attr if isinstance(f, ast.Attribute) else ""))
    return calls


def test_the_census_scanner_sees_the_known_openers():
    """The scanner is proven to FIND opens before its silence means anything (a gate over a
    clean corpus cannot tell you it stopped checking): the two checked openers and the daemon's
    writer reopen are always in the census."""
    seen = {site for site, _ in _read_write_store_constructions()}
    for must in ("cli:_store_rw", "verbs:local_write", "daemon:Daemon._reopen_writer"):
        assert must in seen, f"the census scanner did not find {must}; it is broken: {seen}"


def test_no_read_write_store_open_outside_the_allowlist():
    """b-1 bypass guard (L72): a read-write `Store(` in src/ is allowed only in the two checked
    openers and the named unchecked sites. At 67f55cb it fails on `cli.init`,
    `handoff._promote_digest`, `mcp._t_memory_add`, `verbs.change_subject` (ch-bsd r2's four)
    and `cli.partition_drop` (a fifth, through the `_Store` alias)."""
    allowed = CHECKED_OPENERS | UNCHECKED_ALLOWED
    stray = sorted({f"{site} (line {line})" for site, line in _read_write_store_constructions()
                    if site not in allowed})
    assert not stray, (
        "read-write `Store(` constructions outside the allowlist -- each is an in-process "
        "writer that skips the tracked-catalog check; route it through `verbs.local_write` "
        "(or `cli._store_rw()`), or add it to the allowlist WITH a reason:\n  "
        + "\n  ".join(stray))


def test_the_allowlist_names_no_site_that_no_longer_opens():
    """The allowlist cannot outlive its sites: an entry with no read-write `Store(` left is a
    standing hole for the next one, so it fails until removed."""
    seen = {site for site, _ in _read_write_store_constructions()}
    stale = sorted((CHECKED_OPENERS | UNCHECKED_ALLOWED) - seen)
    assert not stale, f"allowlist entries with no read-write `Store(`: {stale}"


def test_both_checked_openers_call_the_one_store_level_check():
    """L72: ONE store-level check -- a function in store.py that asks
    `git_tracked_catalogs` and refuses -- called by BOTH `cli._store_rw()` and
    `verbs.local_write`, directly or through one wrapper (e.g. a CLI wrapper that turns the
    refusal into a `ClickException`). At 67f55cb store.py has no such function (the refusal is
    cli-level) and `local_write` calls nothing that checks."""
    checks = _functions_calling({"git_tracked_catalogs"}, module="store") - {
        "git_tracked_catalogs"}
    assert checks, ("store.py has no function that calls `git_tracked_catalogs` -- the "
                    "tracked-catalog check is not store-level")
    wrappers = _functions_calling(checks)
    missing = []
    for site in sorted(CHECKED_OPENERS):
        mod, qual = site.split(":")
        calls = _calls_in(mod, qual)
        if not (calls & checks or calls & (wrappers - {qual.split(".")[-1]})):
            missing.append(site)
    assert not missing, (f"checked openers that do not call the store-level check "
                         f"{sorted(checks)} (directly or via one wrapper): {missing}")


# =============================================================================================
# m-3: a hanging git is a loud TrackedCatalogCheckError within the timeout, not a hang
# =============================================================================================

_TRACKED_PROBE = r"""
import json, sys, time
from pathlib import Path
from refmatrix import store
t0 = time.monotonic()
try:
    got = store.git_tracked_catalogs(Path(sys.argv[1]))
except BaseException as e:
    print(json.dumps({"raised": type(e).__name__, "msg": str(e),
                      "elapsed": time.monotonic() - t0}))
else:
    print(json.dumps({"raised": None, "got": got, "elapsed": time.monotonic() - t0}))
"""

# L72's timeout is 10 s per git call; the bound leaves headroom for interpreter start and two
# calls on a loaded machine, and stays far below the fake's 120 s sleep.
HANG_BOUND_S = 45


def _hanging_git(bindir: Path, mode: str) -> None:
    """A PATH shim named `git` (registered `external`): `all` sleeps on every call; `ls-files`
    passes everything but `ls-files` to the real git and sleeps on `ls-files`. `exec sleep`, so
    a kill on timeout leaves no grandchild holding the pipes."""
    real = shutil.which("git")
    assert real, "fixture: no git on PATH"
    bindir.mkdir(exist_ok=True)
    body = ("#!/bin/sh\nexec sleep 120\n" if mode == "all" else
            f'#!/bin/sh\ncase " $* " in *" ls-files "*) exec sleep 120 ;; esac\n'
            f'exec "{real}" "$@"\n')
    g = bindir / "git"
    g.write_text(body, encoding="utf-8")
    g.chmod(0o755)


def _run_bounded(argv: list[str], *, cwd: Path, env: dict,
                 bound: float) -> "subprocess.CompletedProcess | None":
    """Run `argv` in its own process group; None (and the group killed) past `bound`."""
    p = subprocess.Popen(argv, cwd=str(cwd), env=env, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        out, err = p.communicate(timeout=bound)
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL)
        p.communicate()
        return None
    return subprocess.CompletedProcess(argv, p.returncode, out, err)


@pytest.mark.timeout(180)
@pytest.mark.parametrize("mode", ["all", "ls-files"], ids=["rev-parse-hangs", "ls-files-hangs"])
def test_a_hanging_git_raises_the_check_error_within_the_timeout(tracked_repo, mode):
    """m-3 (L72): with `git` hanging -- on the first call (`rev-parse`) or only on `ls-files` --
    `git_tracked_catalogs` raises `TrackedCatalogCheckError` saying it timed out, within the
    bound. At 67f55cb neither call has a timeout: it hangs past the bound."""
    repo, layout = tracked_repo
    _hanging_git(repo.base / "hangbin", mode)
    probe = repo.base / "tracked_probe.py"
    probe.write_text(_TRACKED_PROBE, encoding="utf-8")
    env = _base_env()
    env["PATH"] = f"{repo.base / 'hangbin'}{os.pathsep}{env.get('PATH', '')}"
    t0 = time.monotonic()
    r = _run_bounded([sys.executable, str(probe), str(repo.store)], cwd=repo.proj, env=env,
                     bound=HANG_BOUND_S)
    assert r is not None, (f"[{layout}/{mode}] git_tracked_catalogs did not return within "
                           f"{HANG_BOUND_S}s with git hanging: no timeout on the git call")
    text = f"exit {r.returncode}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    assert r.returncode == 0, f"the probe itself failed\n{text}"
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["raised"] == "TrackedCatalogCheckError", \
        f"[{layout}/{mode}] a hanging git did not raise TrackedCatalogCheckError: {out}"
    assert "time" in out["msg"].lower(), \
        f"[{layout}/{mode}] the error does not say the git call timed out: {out['msg']!r}"
    assert time.monotonic() - t0 < HANG_BOUND_S


@pytest.mark.timeout(180)
def test_an_in_process_writer_with_a_hanging_git_fails_loudly(tracked_repo):
    """m-3, end to end: `rmx sync --files <f>`, no daemon, `git` hanging. One `Error:` line
    `refusing to open <full target> read-write in-process: ...` naming the timeout, exit
    non-zero, catalog bytes unchanged -- within the bound, never a silent hang."""
    repo, layout = tracked_repo
    _hanging_git(repo.base / "hangbin", "all")
    env = _base_env()
    env["PATH"] = f"{repo.base / 'hangbin'}{os.pathsep}{env.get('PATH', '')}"
    f = repo.proj / "README.md"
    before = _digests(repo.store)
    r = _run_bounded([sys.executable, str(_entry(repo.base)), "sync", "--files", str(f)],
                     cwd=repo.proj, env=env, bound=HANG_BOUND_S)
    assert r is not None, (f"[{layout}] `rmx sync --files` with git hanging did not finish "
                           f"within {HANG_BOUND_S}s: a silent hang")
    text = f"exit {r.returncode}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    assert _changed(before, _digests(repo.store)) == [], f"[{layout}] the catalog changed\n{text}"
    assert TRACEBACK not in r.stderr and r.returncode != 0, text
    errs = _errors(r.stderr)
    head = _refusal_head(repo.store / _target_catalog(layout))
    assert len(errs) == 1 and head in errs[0] and "time" in errs[0].lower(), \
        f"[{layout}] expected ONE `Error:` line `{head} ...` naming the timeout; got {errs}\n{text}"


# =============================================================================================
# m-4: `rev-parse` failure inside a repository is unknown (fail closed); the env strip is pinned
# =============================================================================================

def test_a_foreign_git_dir_in_the_env_does_not_hide_a_tracked_catalog(tracked_repo,
                                                                      monkeypatch):
    """m-4 / X3 (GUARD at 67f55cb -- both calls are stripped there; the mutation X3, which kept
    the hook's `GIT_*` on `rev-parse` only, survived 117/117): with `GIT_DIR=/nonexistent` in
    the environment, `rev-parse` must still ask the store's own repository."""
    repo, layout = tracked_repo
    monkeypatch.setenv("GIT_DIR", "/nonexistent")
    want = sorted(Path(p).name for p in subprocess.run(
        ["git", "-C", str(repo.proj), "ls-files", "--", ".refmatrix"], env=_base_env(),
        capture_output=True, text=True).stdout.split() if Path(p).name in WRITER_CATALOG_FILES)
    got = store_mod.git_tracked_catalogs(repo.store)
    assert sorted(got) == want, \
        f"[{layout}] with GIT_DIR=/nonexistent in the env the check answered {got}, not {want}"


@pytest.mark.timeout(300)
def test_a_writer_with_a_foreign_git_dir_in_the_env_still_refuses(tracked_repo):
    """m-4 / X3 end to end (GUARD at 67f55cb): `rmx sync --files <f>` with `GIT_DIR=/nonexistent`
    exported -- one refusal line, catalog bytes unchanged."""
    repo, layout = tracked_repo
    env = {**_base_env(), "GIT_DIR": "/nonexistent"}
    before = _digests(repo.store)
    r = _cli(repo, ["sync", "--files", str(repo.proj / "README.md")], env=env)
    _assert_refused_cli(repo, layout, "`rmx sync --files` (GIT_DIR=/nonexistent)", r, before)


def _corrupt_head(repo: Repo) -> None:
    (repo.proj / ".git" / "HEAD").write_text("not a ref -- bug-212 r4\n", encoding="utf-8")
    rp = subprocess.run(["git", "-C", str(repo.store), "rev-parse", "--is-inside-work-tree"],
                        env=_base_env(), capture_output=True, text=True)
    assert rp.returncode != 0, f"fixture: rev-parse still works on a corrupt HEAD: {rp.stdout}"


def test_a_failing_rev_parse_inside_a_repository_raises(tracked_repo):
    """m-4 (L72): a corrupted `.git/HEAD` in a repo that tracks the catalog makes `rev-parse`
    fail. A `.git` exists above the store, so the answer is UNKNOWN: `TrackedCatalogCheckError`,
    never `[]` (only "no `.git` anywhere at or above the store dir" is `[]`)."""
    repo, layout = tracked_repo
    _corrupt_head(repo)
    with pytest.raises(store_mod.TrackedCatalogCheckError):
        got = store_mod.git_tracked_catalogs(repo.store)
        pytest.fail(f"[{layout}] git_tracked_catalogs returned {got!r} with a corrupt .git/HEAD")


@pytest.mark.timeout(300)
def test_an_in_process_writer_in_a_repository_with_a_corrupt_head_refuses(tracked_repo):
    """m-4 end to end: `rmx sync --files <f>`, no daemon, corrupt `.git/HEAD`, catalog tracked.
    Refused (one `Error:` line with the full target), catalog bytes unchanged -- not a write."""
    repo, layout = tracked_repo
    _corrupt_head(repo)
    before = _digests(repo.store)
    r = _cli(repo, ["sync", "--files", str(repo.proj / "README.md")])
    text = f"exit {r.returncode}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    assert _changed(before, _digests(repo.store)) == [], \
        f"[{layout}] the in-process sync wrote the tracked catalog (corrupt HEAD read as 'not " \
        f"a repository')\n{text}"
    assert TRACEBACK not in r.stderr and r.returncode != 0, text
    errs = _errors(r.stderr)
    head = _refusal_head(repo.store / _target_catalog(layout))
    assert len(errs) == 1 and head in errs[0], \
        f"[{layout}] expected ONE `Error:` line `{head} ...`; got {errs}\n{text}"
