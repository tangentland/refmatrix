"""Task S1 (drop the SQLite catalog backend; spec `workflow/plans/task-s1-drop-sqlite-backend.md`,
L182, Q52 = a, D1 = b / L187): refmatrix reads ONE catalog backend, DuckDB.

WHY each group exists:

AC-1  A store dir holding only a legacy `catalog.db` (no `catalog.duckdb`, no rotation slot)
      is REFUSED, never opened. Before S1 `select_backend` autodetected it and opened it as
      SQLite, so a legacy root silently got the dead backend (and a zero-byte `catalog.db` was
      turned into a fresh SQLite catalog). After S1: through the entry points users run (a read
      verb, `rmx sync`, `rmx init`, an MCP tool) the command fails with ONE stderr line naming
      the file, "legacy SQLite catalog, this rmx reads DuckDB only" and the fix, no traceback,
      nothing in the directory created or changed, and no daemon started for it (R5).
AC-2  `catalog.db` lying beside a DuckDB catalog does not make the dir legacy: beside
      `catalog.duckdb`, and beside `catalog.A.duckdb` + `active` (a rotated store has no
      `catalog.duckdb`, which is exactly where the old autodetect picked SQLite), the store
      opens and answers a query.
AC-3  A census guard: no `sqlite`, `catalog.db`, `RMX_BACKEND`, `select_backend` or
      `_backend.kind ==`/`!=` in src/, scripts/, eval/**/*.py, tests/, outside the hub bus
      (`bus.py` and its test, R6), the refusal and this file, and an allow-list whose every
      entry carries a reason and an owner. It plants must-fail files and fails on them
      (CLAUDE.md test-discipline rule 5).

Everything is real: the CLI (a console-script-shaped entry file), the MCP stdio server, a real
SQLite file written with the stdlib `sqlite3` module (this file is the refusal's test, so it may
name SQLite), a real DuckDB store. Roots are short `rmx_sandbox.short_root()` dirs.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

import rmx_sandbox  # task-29.4 #r5: test roots live under the sandbox root (short_root)
from refmatrix import daemon as dm
from refmatrix.store import Store
from tests.test_bug212_hooks_in_worktrees import TRACEBACK, _base_env, _entry

_REPO = Path(__file__).resolve().parents[1]

# The refusal's text (spec #r5). `BASE_VERSION` is `refmatrix.__version__` read at the S1 task
# base (1fadfb61): the last release that still carries `rmx migrate-to-duckdb`.
BASE_VERSION = "0.84.0"
PHRASE = "legacy SQLite catalog, this rmx reads DuckDB only"
FIX_PARTS = (f"refmatrix {BASE_VERSION}", "rmx migrate-to-duckdb", "move it aside", "rmx init")


# =============================================================================================
# helpers: a throwaway project, its snapshot, the CLI, the MCP server, daemon detection
# =============================================================================================

def _project(prefix: str) -> tuple[Path, Path, Path]:
    """(base, proj, store): `<short root>/proj/.refmatrix`, resolved (the CLI resolves its cwd,
    so a `/tmp` vs `/private/tmp` spelling would not match the path in the refusal)."""
    base = Path(rmx_sandbox.short_root(prefix)).resolve()
    proj = base / "proj"
    store = proj / ".refmatrix"
    store.mkdir(parents=True)
    return base, proj, store


def _write_real_sqlite(path: Path) -> None:
    """A real SQLite database file shaped like a legacy catalog's first table (rollback
    journal, so no -wal/-shm siblings outlive the connection)."""
    con = sqlite3.connect(str(path))
    try:
        con.executescript(
            "CREATE TABLE entities (id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, "
            "name TEXT NOT NULL, UNIQUE(kind, name));"
            "INSERT INTO entities (kind, name) VALUES ('doc', 's1_legacy_row.md');")
        con.commit()
    finally:
        con.close()
    assert path.read_bytes().startswith(b"SQLite format 3\x00"), "fixture: not a SQLite file"


def _snapshot(proj: Path) -> dict[str, str]:
    """Every path under the project (dirs too) -> a sha256 of its bytes ('dir' for a dir): the
    'directory listing and file bytes unchanged' check covers files a command might create
    anywhere under the project, not only under `.refmatrix/`."""
    out: dict[str, str] = {}
    for p in sorted(proj.rglob("*")):
        rel = str(p.relative_to(proj))
        if p.is_symlink():
            out[rel] = f"link:{os.readlink(p)}"
        elif p.is_dir():
            out[rel] = "dir"
        else:
            out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def _diff(before: dict[str, str], after: dict[str, str]) -> list[str]:
    return sorted([f"+{k}" for k in after.keys() - before.keys()]
                  + [f"-{k}" for k in before.keys() - after.keys()]
                  + [f"~{k}" for k in before.keys() & after.keys() if before[k] != after[k]])


def _env() -> dict:
    """The CLI resolves its store from the cwd walk, as in a real project: no
    `REFMATRIX_ROOT`/`RMX_PARTITION` (stripped by `_base_env`), and no `RMX_BACKEND` either, so
    a stray env var cannot pick the backend for the command under test."""
    env = _base_env()
    env.pop("RMX_BACKEND", None)
    return env


def _cli(base: Path, proj: Path, argv: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(_entry(base)), *argv], cwd=str(proj),
                          env=_env(), capture_output=True, text=True, timeout=120)


def _mcp(base: Path, proj: Path, tool: str, args: dict) -> tuple[dict, subprocess.CompletedProcess]:
    """`rmx mcp` with `initialize`, ONE tool call (id 2) and a trailing `ping` (id 99)."""
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": tool, "arguments": args}},
            {"jsonrpc": "2.0", "id": 99, "method": "ping"}]
    r = subprocess.run([sys.executable, str(_entry(base)), "mcp"], cwd=str(proj), env=_env(),
                       input="".join(json.dumps(m) + "\n" for m in msgs),
                       capture_output=True, text=True, timeout=120)
    replies: dict = {}
    for ln in r.stdout.splitlines():
        try:
            m = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if isinstance(m, dict) and "id" in m:
            replies[m["id"]] = m
    return replies, r


def _text(r: subprocess.CompletedProcess) -> str:
    return f"exit {r.returncode}\nstdout:\n{r.stdout[-3000:]}\nstderr:\n{r.stderr[-3000:]}"


def _daemon_evidence(store: Path, t0: float) -> list[str]:
    """Bounded, no waiting: every trace a daemon start for `store` leaves.

    - its pid file or socket under the store;
    - a spawn-ledger record (`rmx_sandbox` writes one per exec'd child and per `os.fork()`
      child, with its argv, at start) made since `t0`, not by the command under test itself
      (whose parent is this process), that is a daemon start: a fork (the daemon's double
      fork; the CLI forks for nothing else) or an argv `... daemon start`;
    - any of those processes still alive.
    The ledger line of a forked child is written in the fork, before the CLI exits, so a daemon
    that started and died at once is still seen."""
    out = []
    for p in (dm.pid_path(store), dm.socket_path(store)):
        if p.exists():
            out.append(f"{p.name} exists")
    recs = rmx_sandbox.read_ledger(rmx_sandbox.sandbox_root() / rmx_sandbox.LEDGER,
                                   lambda msg: out.append(msg))
    for rec in recs:
        if float(rec.get("t") or 0) < t0 or rec.get("ppid") == os.getpid():
            continue                                 # older, or the command under test itself
        argv = [str(a) for a in rec.get("argv") or []]
        tail = argv[1:]
        if rec.get("how") == "fork" or ("daemon" in tail and "start" in tail):
            alive = rmx_sandbox.proc_info(int(rec["pid"])) is not None
            out.append(f"daemon spawn pid={rec['pid']} how={rec.get('how')} alive={alive} "
                       f"argv={' '.join(argv)[:200]}")
    return out


def _stop_any_daemon(store: Path) -> None:
    """Teardown for the RED run (the base opens the legacy file and may start a daemon on it):
    stop it with a short, bounded grace; the sandbox reaper is the backstop."""
    if dm.read_pid(store) is not None or dm.socket_path(store).exists():
        dm.stop_daemon(store, timeout=5.0)


# =============================================================================================
# AC-1: a dir holding only `catalog.db` is refused through every entry point
# =============================================================================================

LEGACY_FILES = {"real-sqlite": _write_real_sqlite,
                "zero-byte": lambda p: p.write_bytes(b"")}


@pytest.fixture(params=sorted(LEGACY_FILES))
def legacy_root(request):
    base, proj, store = _project("s1l-")
    LEGACY_FILES[request.param](store / "catalog.db")
    try:
        yield request.param, base, proj, store
    finally:
        try:
            _stop_any_daemon(store)
        finally:
            shutil.rmtree(base, ignore_errors=True)


def _refusal_problems(line: str, legacy: Path) -> list[str]:
    missing = [s for s in (str(legacy), PHRASE, *FIX_PARTS) if s not in line]
    return [f"the line lacks {m!r}" for m in missing]


CLI_ENTRIES = {
    "read-verb": ["query", "mentions:s1_probe"],
    "sync": ["sync", "--files", "note.md"],
    "init": ["init"],
    # Not in the spec's list, added by RED: the one CLI entry whose whole job is to spawn a
    # daemon. With the CLI-side check dropped (AC-4 M4) the daemon is forked before any Store
    # refuses, and this case sees it.
    "daemon-start": ["daemon", "start", "--no-watch"],
}


@pytest.mark.timeout(180)
@pytest.mark.parametrize("entry", sorted(CLI_ENTRIES))
def test_a_legacy_catalog_alone_is_refused_by_the_cli(legacy_root, entry):
    """AC-1 (CLI): non-zero exit; exactly ONE non-blank stderr line carrying the path, the
    phrase and the fix; no traceback; nothing under the project created or changed; no daemon.
    At the base `select_backend` opens the file as SQLite: a zero-byte file becomes a fresh
    SQLite catalog (exit 0), a real one crashes in the SQLite self-heal DDL, and `daemon start`
    forks a daemon on it."""
    kind, base, proj, store = legacy_root
    legacy = store / "catalog.db"
    _entry(base)                                    # written before the snapshot: not proj
    (proj / "note.md").write_text("# a note `rmx sync --files` would index\n")
    before = _snapshot(proj)
    t0 = time.time()
    r = _cli(base, proj, CLI_ENTRIES[entry])
    after = _snapshot(proj)
    daemon = _daemon_evidence(store, t0)
    text = _text(r)
    where = f"[{kind}] `rmx {' '.join(CLI_ENTRIES[entry])}` on a dir holding only catalog.db"
    assert TRACEBACK not in r.stderr, f"{where} crashed\n{text}"
    assert not daemon, f"{where} started a daemon: {daemon}\n{text}"
    assert r.returncode != 0, f"{where} exited 0: the legacy catalog was opened, not refused\n{text}"
    lines = [ln for ln in r.stderr.splitlines() if ln.strip()]
    assert len(lines) == 1, f"{where}: expected ONE stderr line, got {len(lines)}\n{text}"
    problems = _refusal_problems(lines[0], legacy)
    assert not problems, f"{where}: {problems}\nline: {lines[0]}\n{text}"
    changed = _diff(before, after)
    assert not changed, f"{where} changed the project: {changed}\n{text}"


@pytest.mark.timeout(180)
def test_a_legacy_catalog_alone_is_refused_by_an_mcp_tool(legacy_root):
    """AC-1 (MCP): the server keeps answering (a refusal is a reply, not a dead server), the
    `rmx_query` call is an error reply carrying the path, the phrase and the fix, no traceback
    in the reply or on stderr, nothing under the project created or changed, no daemon."""
    kind, base, proj, store = legacy_root
    legacy = store / "catalog.db"
    _entry(base)
    before = _snapshot(proj)
    t0 = time.time()
    replies, r = _mcp(base, proj, "rmx_query", {"dsl": "mentions:s1_probe"})
    after = _snapshot(proj)
    daemon = _daemon_evidence(store, t0)
    text = _text(r)
    where = f"[{kind}] MCP rmx_query on a dir holding only catalog.db"
    assert 1 in replies and 99 in replies, f"{where}: the MCP server stopped answering\n{text}"
    reply = replies.get(2) or {}
    blob = json.dumps(reply)
    is_error = "error" in reply or bool((reply.get("result") or {}).get("isError"))
    assert TRACEBACK not in r.stderr and TRACEBACK not in blob, f"{where} crashed\n{blob}\n{text}"
    assert is_error, f"{where} answered as a success: the legacy catalog was opened\n{blob}\n{text}"
    problems = _refusal_problems(blob.replace('\\"', '"'), legacy)
    assert not problems, f"{where}: {problems}\nreply: {blob[:2000]}"
    changed = _diff(before, after)
    assert not changed, f"{where} changed the project: {changed}\n{text}"
    assert not daemon, f"{where} started a daemon: {daemon}\n{text}"


@pytest.mark.timeout(120)
def test_the_daemon_check_sees_a_real_daemon_start():
    """Rule 5 for AC-1's "no daemon" leg: on a DuckDB store `rmx daemon start` really forks a
    daemon, and `_daemon_evidence` names it (pid file, socket, the fork's ledger record) and
    not the CLI process itself."""
    base, proj, store = _project("s1d-")
    try:
        _duckdb_store_with_a_doc(store)
        _entry(base)
        t0 = time.time()
        r = _cli(base, proj, ["daemon", "start", "--no-watch"])
        assert r.returncode == 0, f"fixture: the daemon did not start\n{_text(r)}"
        ev = _daemon_evidence(store, t0)
        assert "rmxd.pid exists" in ev and "rmxd.sock exists" in ev, ev
        forks = [e for e in ev if e.startswith("daemon spawn ") and "how=fork" in e]
        assert forks, f"the ledger leg did not see the daemon's fork: {ev}"
        assert not [e for e in ev if "how=exec" in e], \
            f"the check flagged the command under test itself: {ev}"
    finally:
        try:
            _stop_any_daemon(store)
        finally:
            shutil.rmtree(base, ignore_errors=True)


# =============================================================================================
# AC-2: `catalog.db` beside a DuckDB catalog is not a legacy dir
# =============================================================================================

def _duckdb_store_with_a_doc(store: Path) -> None:
    s = Store(store)
    s.init()
    cid = s.add_concept("s1_ac2_probe")
    eid = s.upsert_entity(kind="doc", name="s1_ac2_doc.md")
    s.link("mentions", cid, eid)
    s.close()


def _rotate_to_slot_a(store: Path) -> None:
    """The rotated layout: the live catalog is `catalog.A.duckdb` named by `active`, and there
    is no `catalog.duckdb` (the shape the old autodetect sent to SQLite)."""
    (store / "catalog.duckdb").rename(store / "catalog.A.duckdb")
    (store / "active").write_text("A\n")


BESIDE = {"catalog.duckdb": lambda store: None, "catalog.A.duckdb+active": _rotate_to_slot_a}


@pytest.mark.timeout(180)
@pytest.mark.parametrize("layout", sorted(BESIDE))
def test_catalog_db_beside_a_duckdb_catalog_opens_and_answers(layout):
    """AC-2: through the CLI read verb, the DuckDB catalog answers (exit 0, the seeded doc
    listed) and the stray `catalog.db` is left byte-identical."""
    base, proj, store = _project("s1a-")
    try:
        _duckdb_store_with_a_doc(store)
        BESIDE[layout](store)
        _write_real_sqlite(store / "catalog.db")
        legacy_digest = hashlib.sha256((store / "catalog.db").read_bytes()).hexdigest()
        r = _cli(base, proj, ["query", "mentions:s1_ac2_probe"])
        text = _text(r)
        where = f"[{layout}] `rmx query` with catalog.db beside the DuckDB catalog"
        assert TRACEBACK not in r.stderr, f"{where} crashed\n{text}"
        assert r.returncode == 0, f"{where} failed\n{text}"
        assert "s1_ac2_doc.md" in r.stdout, \
            f"{where} did not answer from the DuckDB catalog (seeded doc missing)\n{text}"
        assert PHRASE not in r.stdout + r.stderr, f"{where} was refused as legacy\n{text}"
        assert hashlib.sha256((store / "catalog.db").read_bytes()).hexdigest() == legacy_digest, \
            f"{where} changed the stray catalog.db\n{text}"
    finally:
        try:
            _stop_any_daemon(store)
        finally:
            shutil.rmtree(base, ignore_errors=True)


# =============================================================================================
# AC-3: the census guard
# =============================================================================================

FORBIDDEN = {
    "sqlite": re.compile(r"(?i)sqlite"),
    "catalog.db": re.compile(r"catalog\.db(?!\w)"),
    "RMX_BACKEND": re.compile(r"RMX_BACKEND"),
    "select_backend": re.compile(r"select_backend"),
    "_backend.kind ==/!=": re.compile(r"_backend\.kind\s*[!=]="),
}

# Whole files outside the census: the hub bus (R6: `~/.refmatrix/bus/bus.db` is a SQLite file
# by design and stays) and this file (the refusal's test).
EXCLUDED_FILES = {
    "src/refmatrix/bus.py": "R6: the hub bus is SQLite by design (bus.db); untouched by S1",
    "tests/test_bus_retention.py": "R6: the bus's own tests",
    "tests/test_single_backend.py": "the refusal's test: it writes a real SQLite file",
}

# One entry per allowed line shape: (path, line regex, token regex the entry permits, reason,
# owner). A line is allowed when an entry's line regex matches it and no forbidden pattern is
# left once the entry's token is removed. Every entry must carry a reason and an owner, and
# must still match a line (a stale entry fails).
ALLOW = [
    # D1 = b (L187): the derive-pass modules stay byte-identical in S1 (a code edit flips the
    # 29.2 R7 pass hash on every fleet store); 29.2 R7 deploy B edits these 7 lines and deletes
    # `bulk_write`'s `sqlite_sql` parameter.
    ("src/refmatrix/pagerank.py", r"^\s*# INSERT \.\.\. SELECT \(executemany on SQLite\)\.$",
     r"SQLite", "D1=b: pass module byte-identical", "29.2 R7 deploy B"),
    ("src/refmatrix/pagerank.py", r"^\s*sqlite_sql=\(\"INSERT INTO pagerank \(",
     r"sqlite_sql", "D1=b: pagerank's bulk_write call keeps its keyword", "29.2 R7 deploy B"),
    ("src/refmatrix/pagerank.py",
     r"^\s*# swallowed by `except Exception: pass`, so a SQLite commit refused at$",
     r"SQLite", "D1=b: pass module byte-identical", "29.2 R7 deploy B"),
    ("src/refmatrix/pagerank.py",
     r"^\s*# COMMIT time \(in production: SQLITE_BUSY or an I/O error; the FK on$",
     r"SQLITE_BUSY", "D1=b: pass module byte-identical", "29.2 R7 deploy B"),
    ("src/refmatrix/pagerank.py",
     r"^\s*# SQLite raises here\. Roll the half-done replace back first so the$",
     r"SQLite", "D1=b: pass module byte-identical", "29.2 R7 deploy B"),
    ("src/refmatrix/ingest.py",
     r"^\s*# writes flush as one Arrow batch \(DuckDB\) or one executemany \(SQLite\)\.$",
     r"SQLite", "D1=b: pass module byte-identical", "29.2 R7 deploy B"),
    ("src/refmatrix/vectors.py", r"^SQLite-only installs don't pay the import cost\.$",
     r"SQLite", "D1=b: pass module byte-identical", "29.2 R7 deploy B"),
    ("src/refmatrix/backend.py", r"\bsqlite_sql\b", r"\bsqlite_sql\b",
     "D1=b: bulk_write keeps `sqlite_sql`, accepted and unused, for pagerank.py's one call",
     "29.2 R7 deploy B"),
    # R5: a legacy dir is still a store, so the generated hooks' store gate reaches the refusal
    # and their text is unchanged.
    ("src/refmatrix/store.py", r"^\s*\"catalog\.A\.duckdb\", \"catalog\.B\.duckdb\", "
                               r"\"catalog\.duckdb\", \"catalog\.db\"\)$",
     r"\"catalog\.db\"", "R5: catalog.db stays in WRITER_CATALOG_FILES", "S1 R5"),
    # R6: the sandbox's audit hook maps `sqlite3.connect`'s path argument; the hub bus opens
    # bus.db through it.
    ("tests/sandbox_site/rmx_sandbox.py", r"\"sqlite3\.connect\": \(0,\)",
     r"sqlite3\.connect", "R6: the bus opens bus.db via sqlite3.connect; the sandbox audits it",
     "S1 R6"),
]


def _refusal_spans(rel: str, text: str) -> list[tuple[int, int]]:
    """The refusal (spec #r5, ONE function) is exempt: the def span of every function in
    src/refmatrix whose source holds the refusal phrase literally."""
    if not (rel.startswith("src/refmatrix/") and rel.endswith(".py")) or PHRASE not in text:
        return []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    spans = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            seg = ast.get_source_segment(text, node) or ""
            if PHRASE in seg:
                spans.append((node.lineno, node.end_lineno or node.lineno))
    return spans


def _in_scope(rel: str) -> bool:
    if "__pycache__" in rel:
        return False
    if rel.startswith(("src/", "scripts/", "tests/")):
        return True
    return rel.startswith("eval/") and rel.endswith(".py")


def _census(files: "list[tuple[str, str]]") -> tuple[list[str], set[int]]:
    """(violations as `path:line: [pattern] text`, indexes of ALLOW entries that matched)."""
    out: list[str] = []
    used: set[int] = set()
    for rel, text in files:
        if not _in_scope(rel) or rel in EXCLUDED_FILES:
            continue
        spans = _refusal_spans(rel, text)
        entries = [(i, e) for i, e in enumerate(ALLOW) if e[0] == rel]
        for n, line in enumerate(text.splitlines(), start=1):
            hits = [k for k, rx in FORBIDDEN.items() if rx.search(line)]
            if not hits or any(a <= n <= b for a, b in spans):
                continue
            ok = False
            for i, (_p, line_re, token_re, _r, _o) in entries:
                if re.search(line_re, line):
                    rest = re.sub(token_re, "", line)
                    if not any(rx.search(rest) for rx in FORBIDDEN.values()):
                        used.add(i)
                        ok = True
                        break
            if not ok:
                out.append(f"{rel}:{n}: [{', '.join(hits)}] {line.strip()[:140]}")
    return out, used


def _tree_files() -> list[tuple[str, str]]:
    """Tracked plus untracked-not-ignored files (a new uncommitted file counts), text only."""
    r = subprocess.run(["git", "-C", str(_REPO), "ls-files", "-co", "--exclude-standard", "-z",
                        "--", "src", "scripts", "eval", "tests"],
                       capture_output=True, timeout=60)
    assert r.returncode == 0, f"git ls-files failed: {r.stderr.decode(errors='replace')}"
    out = []
    for rel in sorted(filter(None, r.stdout.decode().split("\0"))):
        if not _in_scope(rel):
            continue
        p = _REPO / rel
        if not p.is_file():
            continue                                 # deleted in the worktree, not yet staged
        data = p.read_bytes()
        if b"\0" in data[:8192]:
            continue                                 # binary (grep -I)
        out.append((rel, data.decode("utf-8", errors="replace")))
    return out


def test_the_allow_list_entries_each_carry_a_reason_and_an_owner():
    bad = [e for e in ALLOW if len(e) != 5 or not e[3].strip() or not e[4].strip()]
    assert not bad, f"allow-list entries without a reason or an owner: {bad}"
    assert all(v.strip() for v in EXCLUDED_FILES.values())


def test_no_sqlite_backend_trace_outside_the_bus_the_refusal_and_the_allow_list():
    """AC-3. At the base this lists every site GREEN deletes (src/, scripts/, eval/**/*.py);
    test-side sites were removed by RED."""
    files = _tree_files()
    assert len(files) > 100, f"the census read only {len(files)} files; it is not looking"
    violations, used = _census(files)
    stale = [ALLOW[i][:2] for i in range(len(ALLOW)) if i not in used]
    assert not violations, (
        f"{len(violations)} SQLite-backend trace(s) outside the bus, the refusal and the "
        f"allow-list (S1 AC-3):\n  " + "\n  ".join(violations))
    assert not stale, f"allow-list entries that match no line any more (remove them): {stale}"


# Planted files: each MUST be flagged (rule 5), except the ones out of scope or excluded.
_PLANTS = {
    "src/refmatrix/planted_import.py": ("import sqlite3\n", True),
    "src/refmatrix/planted_env.py": ("BACKEND = os.environ.get('RMX_BACKEND')\n", True),
    "src/refmatrix/planted_branch.py": ("if s._backend.kind == 'duckdb':\n    pass\n", True),
    "src/refmatrix/planted_ne.py": ("if s._backend.kind != \"duckdb\": pass\n", True),
    "scripts/planted.sh": ("ls .refmatrix/catalog.db\n", True),
    "eval/retrievers/planted.py": ("from refmatrix.backend import select_backend\n", True),
    "tests/test_planted.py": ("# a SQLite-pinned fixture\n", True),
    "eval/planted_report.md": ("recorded: sqlite\n", False),            # eval: *.py only
    "src/refmatrix/bus.py": ("import sqlite3\n", False),                # excluded (R6)
    "src/refmatrix/planted_ok.py": ("x = 'catalog.duckdb'\n", False),   # not catalog.db
}


def test_the_census_flags_planted_traces_and_spares_the_exempt():
    """Rule 5: the guard can fail. Planted lines in every scope are flagged; out-of-scope and
    excluded files are not; an allow-listed file that gains a NEW trace is flagged; a planted
    refusal function's own lines are exempt, the same text outside it is not."""
    files = [(rel, text) for rel, (text, _) in _PLANTS.items()]
    allowed_line = '        sqlite_sql=("INSERT INTO pagerank (partition_id, entity_id, score) "\n'
    files.append(("src/refmatrix/pagerank.py", allowed_line + "import sqlite3  # new\n"))
    refusal = (f"def refuse_legacy(root):\n    p = root / 'catalog.db'\n"
               f"    raise LegacyCatalogError(f'{{p}}: {PHRASE}')\n\n"
               f"LEGACY = 'catalog.db'\n")
    files.append(("src/refmatrix/planted_refusal.py", refusal))
    violations, _used = _census(files)
    flagged = {v.split(":", 1)[0] for v in violations}
    want = {rel for rel, (_, must) in _PLANTS.items() if must}
    assert want <= flagged, f"the census missed planted traces in {sorted(want - flagged)}"
    spared = {rel for rel, (_, must) in _PLANTS.items() if not must}
    assert not (spared & flagged), f"the census flagged exempt files: {sorted(spared & flagged)}"
    pr = [v for v in violations if v.startswith("src/refmatrix/pagerank.py:")]
    assert pr == ["src/refmatrix/pagerank.py:2: [sqlite] import sqlite3  # new"], \
        f"an allow-listed file: the new line must be flagged and only it: {pr}"
    rf = [v for v in violations if v.startswith("src/refmatrix/planted_refusal.py:")]
    assert rf == ["src/refmatrix/planted_refusal.py:5: [catalog.db] LEGACY = 'catalog.db'"], \
        f"the refusal's own lines are exempt, a line outside it is not: {rf}"
