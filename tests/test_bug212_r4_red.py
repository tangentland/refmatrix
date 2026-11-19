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

import rmx_sandbox  # task-29.4 #r5: test roots live under the sandbox root (short_root)
import ast
import re
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
# b-1 bypass guard: the census of every in-process way a writer catalog is opened or replaced
# =============================================================================================
#
# r4 (L72) keyed the census on ONE constructor, `Store(`. ch-bsd r4 (03d7b27, 2026-11-14) found
# `rmx compact` and `rmx migrate-to-duckdb --overwrite` opening the same catalog FILE with the
# raw `open_duckdb` and renaming / unlinking over it -- invisible to a `Store(` scan, and both
# wrote a committed catalog. L95: the census keys on the guarded RESOURCE. Three families:
#   store -- a read-write `Store(` call, under any name `Store` is bound to;
#   raw   -- `open_duckdb(` / `duckdb.connect(` whose path is not the literal ":memory:" and
#            which pass no `read_only=True`;
#   move  -- `.rename(` / `.replace(` / `.unlink(` / `os.replace|rename|remove|unlink(` /
#            `shutil.move(` whose source or target is a catalog path: an expression whose text
#            names a writer catalog (`catalog.duckdb`, `catalog.{slot}.duckdb`,
#            `db_path`), or a local bound to one;
#   copy  -- `shutil.copy|copy2|copyfile|copyfileobj(` whose DESTINATION is a catalog path, and
#            `<catalog path>.write_bytes(` (ch-bsd r5 m-3, L98, 2026-11-14: a copy onto a slot
#            replaces its bytes as surely as a rename; a copy FROM a catalog writes nothing
#            guarded). `os` / `shutil` count under any import alias (daemon.py's `_shutil`).

# Sites (`module:qualname`) that must call the one store-level check (directly or via one
# wrapper) before they open or replace a catalog:
CHECKED_OPENERS = {
    "cli:_store_rw",          # the CLI's in-process writer (L72)
    "verbs:local_write",      # the verbs' in-process writer (L72)
    "cli:compact",            # raw open + rename over the writer slot (L95)
}
# Library sites that open or replace a catalog for a caller, by the function name callers
# call; every caller in src/ must be a checked site.
# S1 (2026-11-19) deleted the only one, `migrate:migrate_catalog` (`rmx migrate-to-duckdb`, L95),
# with the second catalog backend; the mechanism stays for the next library opener.
LIBRARY_OPENERS: "dict[str, str]" = {}
UNCHECKED_ALLOWED = {
    # The daemon IS the single writer; a tracked catalog written through it is the accepted
    # route (lead decisions a1/a2; only bug-214's untracking removes it).
    "daemon:Daemon._reopen_writer",
    "daemon:Daemon.serve_forever",
    "daemon:Daemon._bootstrap_rotation_if_needed",
    # Daemon-only: merges the A/B slots inside the daemon (held by
    # `test_daemon_only_sites_are_called_only_from_the_daemon`).
    "replica_merge:merge_slots",
    # The daemon's replica-merge op installs the merged file over its own slots (os.replace,
    # then `_shutil.copy2` of A onto B), and its slot repair re-clones a missing slot; the
    # rotation bootstrap above copies the legacy catalog onto A and B (`shutil.copy2`). The
    # daemon owns those files.
    "daemon:_op_replica_merge",
    "daemon:Daemon._repair_missing_slot_locked",
    # The hub's global store (`~/.refmatrix/global`), created and owned by the hub.
    "hub:_bootstrap_global_store",
    # The canon partition opened from inside an already-open writer of the same store.
    "store:Store.link_canon",
    # A Store method on an already-open writer (opened through a checked opener or the daemon):
    # rebuilding the index replaces that writer's own file.
    "store:Store.rebuild_index_from_log",
    # The backend opener internals behind every `Store` open (the guard sits at the Store).
    "backend:_open_write",
    "backend:DuckDBBackend.connect",
}

# A WRITER catalog name (`store.WRITER_CATALOG_FILES`, or a slot f-string), a `db_path`, or the
# helpers that return a writer slot path (`cli._active_slot_path()`, the daemon's
# `_replica_file()`); not the read replica `catalog.read.duckdb`, which no writer opens and no
# fleet repo commits. A path reached any other way (a helper not named here) is outside what a
# static scan can see -- the behaviour tests are the backstop.
_CATALOG_TEXT = re.compile(r"catalog(\.([AB]|\{[^}]*\}))?\.(duckdb|db)\b|db_path|_active_slot_path\(|_replica_file\(")


def _store_aliases(tree: ast.AST) -> set[str]:
    """Every name `Store` is bound to in a module: `Store` itself, `import Store as X`, and
    `X = Store` / `X = <mod>.Store`. cli.py's `partition_drop` opened `Store` imported as
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


def _module_aliases(tree: ast.AST, module: str) -> set[str]:
    """Every name the stdlib `module` (`os`, `shutil`) is bound to: itself and `import X as Y`."""
    names = {module}
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            names |= {a.asname for a in n.names if a.name == module and a.asname}
    return names


_COPY_FUNCS = ("copy", "copy2", "copyfile", "copyfileobj")


def _is_memory_literal(node: "ast.AST | None") -> bool:
    return isinstance(node, ast.Constant) and node.value == ":memory:"


def _scan_source(mod: str, text: str) -> list[tuple[str, int, str]]:
    """The census of ONE module's source: (`module:qualname`, line, family) per site."""
    tree = ast.parse(text, mod)
    aliases = _store_aliases(tree)
    os_names = _module_aliases(tree, "os")
    shutil_names = _module_aliases(tree, "shutil")
    found: list[tuple[str, int, str]] = []
    stack: list[str] = []
    catalog_names: list[set[str]] = [set()]

    def is_catalog(node: "ast.AST | None") -> bool:
        if node is None:
            return False
        if isinstance(node, ast.Name) and node.id in catalog_names[-1]:
            return True
        return bool(_CATALOG_TEXT.search(ast.unparse(node)))

    class V(ast.NodeVisitor):
        def visit_FunctionDef(self, n):
            stack.append(n.name)
            names = set()
            for a in ast.walk(n):
                if isinstance(a, ast.Assign) and _CATALOG_TEXT.search(ast.unparse(a.value)):
                    names |= {t.id for t in a.targets if isinstance(t, ast.Name)}
            catalog_names.append(names)
            self.generic_visit(n)
            catalog_names.pop()
            stack.pop()
        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_ClassDef(self, n):
            stack.append(n.name)
            self.generic_visit(n)
            stack.pop()

        def visit_Call(self, n):
            site = f"{mod}:{'.'.join(stack) or '<module>'}"
            f = n.func
            kw = {k.arg: k.value for k in n.keywords}
            ro = kw.get("read_only")
            read_only = isinstance(ro, ast.Constant) and ro.value is True
            if ((isinstance(f, ast.Name) and f.id in aliases)
                    or (isinstance(f, ast.Attribute) and f.attr == "Store")):
                if not read_only:
                    found.append((site, n.lineno, "store"))
            elif ((isinstance(f, ast.Name) and f.id == "open_duckdb")
                  or (isinstance(f, ast.Attribute) and f.attr == "open_duckdb")
                  or (isinstance(f, ast.Attribute) and f.attr == "connect"
                      and isinstance(f.value, ast.Name) and f.value.id == "duckdb")):
                path = n.args[0] if n.args else kw.get("database")
                if not read_only and not _is_memory_literal(path):
                    found.append((site, n.lineno, "raw"))
            elif (isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name)
                  and f.value.id in shutil_names and f.attr in _COPY_FUNCS):
                dst = n.args[1] if len(n.args) > 1 else (kw.get("dst") or kw.get("fdst"))
                if is_catalog(dst):
                    found.append((site, n.lineno, "copy"))
            elif (isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name)
                  and ((f.value.id in os_names
                        and f.attr in ("replace", "rename", "remove", "unlink"))
                       or (f.value.id in shutil_names and f.attr == "move"))):
                if any(is_catalog(a) for a in n.args):
                    found.append((site, n.lineno, "move"))
            elif isinstance(f, ast.Attribute) and f.attr == "write_bytes":
                if is_catalog(f.value):
                    found.append((site, n.lineno, "copy"))
            elif isinstance(f, ast.Attribute) and f.attr in ("rename", "replace", "unlink"):
                if is_catalog(f.value) or (f.attr != "unlink" and n.args
                                           and is_catalog(n.args[0])):
                    found.append((site, n.lineno, "move"))
            self.generic_visit(n)

    V().visit(tree)
    return found


def _census() -> list[tuple[str, int, str]]:
    out: list[tuple[str, int, str]] = []
    for p in sorted(SRC.rglob("*.py")):
        mod = ".".join(p.relative_to(SRC).with_suffix("").parts)
        out += _scan_source(mod, p.read_text(encoding="utf-8"))
    return out


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


def _sites_calling(name: str) -> set[str]:
    """`module:qualname` of every function in src/ whose body calls `name`."""
    out: set[str] = set()
    for p in sorted(SRC.rglob("*.py")):
        mod = ".".join(p.relative_to(SRC).with_suffix("").parts)
        tree = ast.parse(p.read_text(encoding="utf-8"), str(p))

        def walk(body, prefix):
            for n in body:
                if isinstance(n, ast.ClassDef):
                    walk(n.body, prefix + [n.name])
                elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    q = prefix + [n.name]
                    for c in ast.walk(n):
                        if isinstance(c, ast.Call):
                            f = c.func
                            nm = f.id if isinstance(f, ast.Name) else (
                                f.attr if isinstance(f, ast.Attribute) else None)
                            if nm == name:
                                out.add(f"{mod}:{'.'.join(q)}")
                                break
        walk(tree.body, [])
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
    clean corpus cannot tell you it stopped checking): one known site from EACH family --
    `cli:_store_rw` (store), `cli:compact` (raw, and move: its rename over the slot) -- plus the
    daemon's writer reopen (L95: a "sees" guard on `cli:compact`). S1 deleted the other raw
    site this named, `migrate:migrate_catalog`."""
    seen = {(site, fam) for site, _, fam in _census()}
    for must in (("cli:_store_rw", "store"), ("verbs:local_write", "store"),
                 ("daemon:Daemon._reopen_writer", "store"), ("cli:compact", "raw"),
                 ("cli:compact", "move")):
        assert must in seen, f"the census scanner did not find {must}; it is broken"


_SYNTHETIC = """
from refmatrix.store import Store as _S
from refmatrix import store as store_mod
from refmatrix.backend import open_duckdb
import duckdb, os

def aliased_import(root):
    _S(root)

def aliased_assign(root):
    X = store_mod.Store
    X(root)

def attribute_ctor(root):
    store_mod.Store(root)

def read_only_ok(root):
    store_mod.Store(root, read_only=True)
    _S(root, read_only=True)

def raw_open(root):
    con = open_duckdb(root / "catalog.duckdb")

def raw_connect(p):
    duckdb.connect(p)

def memory_ok():
    open_duckdb(":memory:")
    duckdb.connect(database=":memory:")
    duckdb.connect(":memory:")

def raw_read_only_ok(p):
    open_duckdb(p, read_only=True)

def move_onto(root, new):
    src = root / f"catalog.{'A'}.duckdb"
    new.rename(src)

def move_away(root, backup):
    (root / "catalog.duckdb").rename(backup)

def unlink_one(root):
    legacy = root / "catalog.duckdb"
    legacy.unlink()

def os_replace(root, tmp):
    os.replace(tmp, root / "catalog.B.duckdb")

def not_a_catalog(root):
    (root / "notes.txt").unlink()
    (root / "x.json").rename(root / "y.json")
"""


def test_the_census_scanner_finds_every_family_in_a_synthetic_module():
    """Y6 (ch-bsd r4 m-1, L95): the alias logic was unpinned -- `_store_aliases` returning
    `{"Store"}` left every census test green, because the one aliased site in src/ had been
    routed. A synthetic module carries a positive (and a negative) for every family, so the
    scanner's own logic is tested whether or not src/ still has an example."""
    got = {(site.split(":")[1], fam) for site, _, fam in _scan_source("synthetic", _SYNTHETIC)}
    want = {("aliased_import", "store"), ("aliased_assign", "store"),
            ("attribute_ctor", "store"), ("raw_open", "raw"), ("raw_connect", "raw"),
            ("move_onto", "move"), ("move_away", "move"), ("unlink_one", "move"),
            ("os_replace", "move")}
    assert want <= got, f"the scanner missed {sorted(want - got)}"
    never = {"read_only_ok", "memory_ok", "raw_read_only_ok", "not_a_catalog"}
    false = sorted(x for x in got if x[0] in never)
    assert not false, f"the scanner flagged sites that open nothing read-write: {false}"


_SYNTHETIC_COPY = """
import shutil
import shutil as _sh
import os as _os

def copy2_onto(root, src):
    shutil.copy2(src, root / "catalog.A.duckdb")

def copy_onto_slot(root, src):
    slot = root / f"catalog.{'B'}.duckdb"
    shutil.copy(src, slot)

def copyfile_aliased(root, src):
    _sh.copyfile(src, root / "catalog.duckdb")

def copyfileobj_onto(root, fsrc):
    with open(root / "catalog.A.duckdb", "wb") as fdst:
        shutil.copyfileobj(fsrc, open(root / "catalog.A.duckdb", "wb"))

def write_bytes_onto(root):
    (root / "catalog.duckdb").write_bytes(b"")

def move_aliased(root, tmp):
    _sh.move(tmp, root / "catalog.duckdb")
    _os.replace(tmp, root / "catalog.A.duckdb")

def copy_from_catalog_ok(root, backup):
    shutil.copy2(root / "catalog.duckdb", backup)
    _sh.copyfile(root / "catalog.A.duckdb", root / "snapshot.tmp")

def copy_to_the_read_replica_ok(root, active):
    shutil.copy2(active, root / "catalog.read.duckdb")

def write_bytes_elsewhere_ok(root):
    (root / "notes.bin").write_bytes(b"")
"""


def test_the_census_scanner_finds_the_copy_family_on_the_destination():
    """m-3 (ch-bsd r5, L98, 2026-11-14): `shutil.copy` / `copy2` / `copyfile` / `copyfileobj`
    and `Path.write_bytes` ONTO a writer-catalog path replace its bytes as surely as a rename,
    and the census did not scan them (today only the daemon does it, so nothing escaped; a
    future CLI copy onto `catalog.A.duckdb` would have passed). Keyed on the DESTINATION: a copy
    FROM a catalog (a backup, a snapshot) writes nothing guarded. `shutil` / `os` under an alias
    (`import shutil as _shutil`, as daemon.py does) count too."""
    got = {(site.split(":")[1], fam)
           for site, _, fam in _scan_source("synthetic", _SYNTHETIC_COPY)}
    want = {("copy2_onto", "copy"), ("copy_onto_slot", "copy"), ("copyfile_aliased", "copy"),
            ("copyfileobj_onto", "copy"), ("write_bytes_onto", "copy"),
            ("move_aliased", "move")}
    assert want <= got, f"the scanner missed {sorted(want - got)}"
    never = {"copy_from_catalog_ok", "copy_to_the_read_replica_ok", "write_bytes_elsewhere_ok"}
    false = sorted(x for x in got if x[0] in never)
    assert not false, f"the scanner flagged copies that write no writer catalog: {false}"


def test_the_census_sees_the_daemons_slot_copies():
    """m-3: the real copies onto writer slots -- the daemon's replica merge
    (`_shutil.copy2(d._replica_file("A"), slot_path)`) and its rotation bootstrap
    (`shutil.copy2(legacy, a)` / `(legacy, b)`) -- are in the census, so the allowlist's
    reasons for those two sites cover what they actually do."""
    seen = {(site, fam) for site, _, fam in _census()}
    for must in (("daemon:_op_replica_merge", "copy"),
                 ("daemon:Daemon._bootstrap_rotation_if_needed", "copy")):
        assert must in seen, f"the census does not see {must}"


def test_no_read_write_store_open_outside_the_allowlist():
    """b-1 bypass guard (L72, L95): every in-process way a writer catalog is opened read-write
    or replaced -- any family -- is allowed only in a checked opener, a library opener whose
    callers check, or a named unchecked site."""
    allowed = CHECKED_OPENERS | set(LIBRARY_OPENERS) | UNCHECKED_ALLOWED
    stray = sorted({f"{site} [{fam}] (line {line})" for site, line, fam in _census()
                    if site not in allowed})
    assert not stray, (
        "in-process catalog opens / replaces outside the allowlist -- each skips the "
        "tracked-catalog check; route it through a checked opener, or add it to the "
        "allowlist WITH a reason:\n  " + "\n  ".join(stray))


def test_the_allowlist_names_no_site_that_no_longer_opens():
    """The allowlist cannot outlive its sites: an entry the census no longer sees is a
    standing hole for the next one, so it fails until removed."""
    seen = {site for site, _, _ in _census()}
    stale = sorted((CHECKED_OPENERS | set(LIBRARY_OPENERS) | UNCHECKED_ALLOWED) - seen)
    assert not stale, f"allowlist entries the census no longer sees: {stale}"


def _library_callers() -> set[str]:
    out: set[str] = set()
    for site, fn in LIBRARY_OPENERS.items():
        out |= _sites_calling(fn) - {site}
    return out


def test_every_checked_opener_calls_the_one_store_level_check():
    """L72 + L95: ONE store-level check -- a function in store.py that asks
    `git_tracked_catalogs` and refuses -- called by every checked opener and by every caller
    of a library opener, directly or through one wrapper (e.g. a CLI wrapper that turns the
    refusal into a `ClickException`). At 03d7b27 `cli:compact` and `cli:migrate_to_duckdb`
    (the caller of `migrate.migrate_catalog`) call nothing that checks."""
    checks = _functions_calling({"git_tracked_catalogs"}, module="store") - {
        "git_tracked_catalogs"}
    assert checks, ("store.py has no function that calls `git_tracked_catalogs` -- the "
                    "tracked-catalog check is not store-level")
    wrappers = _functions_calling(checks)
    missing = []
    for site in sorted(CHECKED_OPENERS | _library_callers()):
        mod, qual = site.split(":")
        calls = _calls_in(mod, qual)
        if not (calls & checks or calls & (wrappers - {qual.split(".")[-1]})):
            missing.append(site)
    assert not missing, (f"checked openers that do not call the store-level check "
                         f"{sorted(checks)} (directly or via one wrapper): {missing}")


def test_daemon_only_sites_are_called_only_from_the_daemon():
    """`replica_merge:merge_slots` is allowed unchecked as daemon-only; that reason is held
    here, not asserted in a comment: every caller lives in daemon.py."""
    callers = _sites_calling("merge_slots") - {"replica_merge:merge_slots"}
    assert callers and all(c.startswith("daemon:") for c in callers), \
        f"merge_slots has a caller outside the daemon: {sorted(callers)}"


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
    """A PATH shim named `git` (registered `external`): `all` sleeps on every call; any other
    `mode` names ONE git subcommand (`ls-files`, `diff`) that sleeps, while every other call
    goes to the real git. `exec sleep`, so a kill on timeout leaves no grandchild holding the
    pipes."""
    real = shutil.which("git")
    assert real, "fixture: no git on PATH"
    bindir.mkdir(exist_ok=True)
    body = ("#!/bin/sh\nexec sleep 120\n" if mode == "all" else
            f'#!/bin/sh\ncase " $* " in *" {mode} "*) exec sleep 120 ;; esac\n'
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
    # 29.4 R3 class A (T0.3 + 29.4c, 2026-11-15): the old `elapsed < HANG_BOUND_S` repeated the
    # kill bound above. `_run_bounded` kills the probe at HANG_BOUND_S and the test fails on
    # `r is None`, so the outcome (the probe returned, raised the check error, said "time") is
    # the whole assertion. HANG_BOUND_S keeps its own name as the four kill bounds' value (L141).


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


# =============================================================================================
# L82 (2026-11-13): the save-state promote refusal is loud; `sync.changed_since` cannot hang
# =============================================================================================

@pytest.mark.timeout(300)
@pytest.mark.parametrize("commit", [False, True], ids=["plain", "commit"])
def test_save_state_whose_promote_is_refused_says_so_on_stderr_and_exits_non_zero(tracked_repo,
                                                                                  commit):
    """L82: `rmx save-state` with no daemon on a store whose catalog git tracks. The handoff is
    written (it lands in the memory dir, outside the store, BEFORE the promote), the STM promote
    is refused -- and that refusal is printed on STDERR with a non-zero exit. At 67f55cb the
    promote wrote the tracked catalog; with only the r4 refusal in place it would come back as
    `{"error": ...}`, which the command prints as `promote skipped:` on stdout and exits 0 --
    a silent refusal (ch-bsd r2 flag, red-212r2 r4 flag). `--no-sync` keeps the memory bridge
    (another in-process writer, already covered) out of this test, so the promote is the only
    store write.

    `commit` (ch-bsd r4 m-2, mutation Y7, L95): the user-level `/save-state` runs
    `rmx save-state --commit`, so the exit code is pinned on THAT path too -- the commit lands,
    and the command still exits non-zero."""
    from refmatrix import stm
    repo, layout = tracked_repo
    assert not dm.ping(repo.store), "fixture: a daemon answers"
    session = "bug212-r4-savestate"
    st = stm.Stm(repo.store, session)
    st.record("note", "a focus event for the bug-212 r4 save-state probe")
    memdir = repo.base / "memdir"
    memdir.mkdir()
    before = _digests(repo.store)
    head_before = subprocess.run(["git", "-C", str(repo.proj), "rev-parse", "HEAD"],
                                 env=_base_env(), capture_output=True, text=True).stdout.strip()
    argv = ["save-state", "-s", session, "--memory-dir", str(memdir), "--no-sync",
            "--no-lint", "-m", "bug-212 r4 probe"] + (["--commit"] if commit else [])
    r = _cli(repo, argv)
    text = f"exit {r.returncode}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    changed = _changed(before, _digests(repo.store))
    assert TRACEBACK not in r.stderr, f"[{layout}] save-state crashed\n{text}"
    assert not changed and _status_refmatrix_catalogs(repo.proj) == "", \
        f"[{layout}] save-state's promote wrote the git-tracked catalog {changed}\n{text}"
    saved = sorted(p.name for p in memdir.rglob("savestate_*.md"))
    assert saved, f"[{layout}] save-state wrote no handoff file under {memdir}\n{text}"
    head = _refusal_head(repo.store / _target_catalog(layout))
    assert any(head in ln for ln in r.stderr.splitlines()), \
        f"[{layout}] the promote refusal (`{head} ...`) is not on stderr\n{text}"
    assert r.returncode != 0, f"[{layout}] save-state exited 0 although its promote was " \
                              f"refused\n{text}"
    if commit:
        head_after = subprocess.run(["git", "-C", str(repo.proj), "rev-parse", "HEAD"],
                                    env=_base_env(), capture_output=True, text=True).stdout.strip()
        assert head_after != head_before, f"[{layout}] --commit made no commit\n{text}"


_CHANGED_SINCE_PROBE = r"""
import json, sys, time
from pathlib import Path
from refmatrix import sync
t0 = time.monotonic()
try:
    got = sync.changed_since(Path(sys.argv[1]), sys.argv[2])
except BaseException as e:
    print(json.dumps({"raised": type(e).__name__, "runtime_error": isinstance(e, RuntimeError),
                      "msg": str(e), "elapsed": time.monotonic() - t0}))
else:
    print(json.dumps({"raised": None, "got": [str(p) for p in got],
                      "elapsed": time.monotonic() - t0}))
"""


@pytest.fixture
def ignored_store_repo():
    """A repo with two commits and a real store whose catalog git IGNORES (the store gate and
    the tracked-catalog check both let a sync through), no daemon. Short resolved `/tmp` root."""
    base = Path(rmx_sandbox.short_root("b212d-")).resolve()
    r = Repo(base)
    try:
        r.proj.mkdir()
        _quiet(r.proj, r, "init", "-q", "--template=", "-b", "main")
        (r.proj / ".gitignore").write_text(".refmatrix/\n", encoding="utf-8")
        (r.proj / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
        _quiet(r.proj, r, "add", "-A")
        _quiet(r.proj, r, "commit", "-q", "-m", "c0")
        (r.proj / "b.py").write_text("def b():\n    return 2\n", encoding="utf-8")
        _quiet(r.proj, r, "add", "-A")
        _quiet(r.proj, r, "commit", "-q", "-m", "c1")
        s = Store(r.store)
        s.init()
        s.close()
        assert store_mod.git_tracked_catalogs(r.store) == [], "fixture: catalog tracked"
        yield r
    finally:
        dm.stop_daemon(r.store)
        shutil.rmtree(base, ignore_errors=True)


@pytest.mark.timeout(180)
def test_changed_since_with_a_hanging_git_diff_raises_within_the_bound(ignored_store_repo):
    """L82: `sync.changed_since` (what the post-commit hook's `rmx sync --since` runs) with
    `git diff` hanging raises within the bound -- a `RuntimeError` (every `--since` caller
    turns a RuntimeError into one `Error:` line; a bare `subprocess.TimeoutExpired` would be a
    traceback) saying it timed out. At 67f55cb `git diff` has no timeout: it hangs."""
    repo = ignored_store_repo
    _hanging_git(repo.base / "hangbin", "diff")
    probe = repo.base / "changed_since_probe.py"
    probe.write_text(_CHANGED_SINCE_PROBE, encoding="utf-8")
    env = _base_env()
    env["PATH"] = f"{repo.base / 'hangbin'}{os.pathsep}{env.get('PATH', '')}"
    r = _run_bounded([sys.executable, str(probe), str(repo.proj), "HEAD~1"], cwd=repo.proj,
                     env=env, bound=HANG_BOUND_S)
    assert r is not None, (f"sync.changed_since did not return within {HANG_BOUND_S}s with "
                           f"`git diff` hanging: no timeout on the git call")
    text = f"exit {r.returncode}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    assert r.returncode == 0, f"the probe itself failed\n{text}"
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["raised"] is not None and out["runtime_error"], \
        f"a hanging `git diff` did not raise a RuntimeError: {out}"
    assert "time" in out["msg"].lower(), f"the error does not say git timed out: {out['msg']!r}"


@pytest.mark.timeout(180)
def test_sync_since_with_a_hanging_git_diff_fails_loudly(ignored_store_repo):
    """L82, end to end -- the post-commit path: `rmx sync --since HEAD~1`, no daemon, an
    ignored catalog (so the store opens), `git diff` hanging. One `Error:` line naming the
    timeout, exit non-zero, within the bound; never a silent hang in the backgrounded hook."""
    repo = ignored_store_repo
    _hanging_git(repo.base / "hangbin", "diff")
    env = _base_env()
    env["PATH"] = f"{repo.base / 'hangbin'}{os.pathsep}{env.get('PATH', '')}"
    r = _run_bounded([sys.executable, str(_entry(repo.base)), "sync", "--since", "HEAD~1"],
                     cwd=repo.proj, env=env, bound=HANG_BOUND_S)
    assert r is not None, (f"`rmx sync --since HEAD~1` with `git diff` hanging did not finish "
                           f"within {HANG_BOUND_S}s: a silent hang")
    text = f"exit {r.returncode}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    assert TRACEBACK not in r.stderr and r.returncode != 0, text
    errs = _errors(r.stderr)
    assert len(errs) == 1 and "time" in errs[0].lower(), \
        f"expected ONE `Error:` line naming the git timeout; got {errs}\n{text}"
