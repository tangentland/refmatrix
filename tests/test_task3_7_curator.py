"""Task 3.7 batch A — `rmx_curator` over a spool directory (RED).

Spec #fam-refine-drain (r1 B3, redesigned r4, refined r5/r6). The shared mutable
`curator.queue` is the defect, so it goes:
  - the daemon watcher writes each flush as ONE new file
    `.refmatrix/curator.spool/<time_ns zero-padded to 20>-<uuid4>.jsonl`, written to
    a `.tmp` name, fsynced, renamed; readers glob `*.jsonl` only; the daemon deletes
    stale `*.tmp` at startup;
  - ONE JSON-lines parser of the watcher's `{ts, path, reason}` format; a bad line is
    counted and warned; an OSError is raised EXCEPT ENOENT on a listed file or on the
    legacy rename (a concurrent drain took it): skipped, out of the token, in `missing`;
  - `status(max_entries=500)` → whole oldest files up to `max_entries`, `token` = the
    file names read (oldest first), `spool = {files, bytes, remaining_files}`;
  - `drain(token)` unlinks exactly those; a gone name is `missing`; no token is
    `VerbArgsError`; a file written after `status` is never drained unread;
  - rollout: `status` first moves a legacy `curator.queue` into the spool with ONE
    `os.rename`; nothing unlinks the legacy file;
  - no src path other than `drain(token)` and the startup `*.tmp` sweep deletes a spool
    file (r4 M1 grep test);
  - CLI: `curator status --json` emits the token, `curator drain --token <names…|@file>`
    takes it back; `curator status --drain` (the hooks' form) is status → drain(token);
    `--limit` stays a CLI-only render option; the gmd-curator flow is rewritten.

Interpretations (named in the RED report):
  - `--token` is a repeatable click option; `@file` holds the `status --json` output;
  - `max_entries` smaller than the oldest file still returns that one whole file (so a
    big flush can never wedge the spool);
  - a token name must be a bare spool file name — a path is never followed.
"""
from __future__ import annotations

import ast
import json
import os
import re
import time
import uuid
from pathlib import Path

import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod
from refmatrix import daemon as dm
from refmatrix import gmd_curator, verbs
from refmatrix.store import Store
from tests.task3_7_helpers import rm, short_root

_REPO = Path(__file__).resolve().parent.parent
_SRC = _REPO / "src" / "refmatrix"
_NAME = re.compile(r"^\d{20}-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.jsonl$")


@pytest.fixture
def root(monkeypatch):
    base, r = short_root("r37q-")
    monkeypatch.setattr(cli_mod, "_root", lambda: r)
    yield r
    rm(base)


def spool(root: Path) -> Path:
    return root / "curator.spool"


_SEQ = [0]


def flush(root: Path, paths, *, raw_lines=()) -> str:
    """One watcher flush in the WATCHER's format, named the way the spec names it."""
    d = spool(root)
    d.mkdir(exist_ok=True)
    _SEQ[0] += 1
    name = f"{time.time_ns() + _SEQ[0]:020d}-{uuid.uuid4()}.jsonl"
    lines = [json.dumps({"ts": time.time(), "path": str(p), "reason": "fs-change"})
             for p in paths] + list(raw_lines)
    (d / name).write_text("\n".join(lines) + "\n")
    return name


def _paths(out):
    return [e["path"] for e in out["entries"]]


# ---- status ---------------------------------------------------------------------


def test_status_on_an_empty_spool_is_empty(root):
    out = verbs.curator(root, action="status")
    assert out["entries"] == [] and out["token"] == [], out
    assert out["spool"] == {"files": 0, "bytes": 0, "remaining_files": 0}, out


def test_status_reads_whole_files_oldest_first_and_names_them(root):
    a = flush(root, ["/p/a.md", "/p/b.md"])
    b = flush(root, ["/p/c.md"])
    out = verbs.curator(root, action="status")
    assert out["token"] == [a, b], out
    assert _paths(out) == ["/p/a.md", "/p/b.md", "/p/c.md"], out
    assert out["entries"][0]["reason"] == "fs-change"
    assert out["spool"]["files"] == 2 and out["spool"]["remaining_files"] == 0, out
    assert out["spool"]["bytes"] == sum(f.stat().st_size for f in spool(root).iterdir())


def test_status_max_entries_takes_whole_files_and_reports_the_rest(root):
    names = [flush(root, [f"/p/{i}a.md", f"/p/{i}b.md"]) for i in range(3)]
    out = verbs.curator(root, action="status", max_entries=4)
    assert out["token"] == names[:2], out
    assert len(out["entries"]) == 4
    assert out["spool"] == {"files": 3, "bytes": out["spool"]["bytes"], "remaining_files": 1}
    out3 = verbs.curator(root, action="status", max_entries=3)
    assert out3["token"] == names[:1], ("whole files only", out3["token"])


def test_status_returns_at_least_one_whole_file_even_over_max_entries(root):
    big = flush(root, [f"/p/{i}.md" for i in range(5)])
    out = verbs.curator(root, action="status", max_entries=2)
    assert out["token"] == [big] and len(out["entries"]) == 5, out


def test_a_bad_line_is_counted_and_warned_not_dropped_silently(root):
    flush(root, ["/p/good.md"], raw_lines=["not json at all", "/p/raw-path.md"])
    out = verbs.curator(root, action="status")
    assert _paths(out) == ["/p/good.md"], out
    assert out["warnings"] and any("2" in w for w in out["warnings"]), out


def test_readers_ignore_tmp_files(root):
    keep = flush(root, ["/p/a.md"])
    (spool(root) / f"{time.time_ns():020d}-{uuid.uuid4()}.jsonl.tmp").write_text(
        json.dumps({"ts": 1, "path": "/p/half.md", "reason": "x"}) + "\n")
    out = verbs.curator(root, action="status")
    assert out["token"] == [keep] and _paths(out) == ["/p/a.md"], out


def test_status_never_deletes_anything(root):
    flush(root, ["/p/a.md"])
    before = sorted(p.name for p in spool(root).iterdir())
    verbs.curator(root, action="status")
    assert sorted(p.name for p in spool(root).iterdir()) == before


# ---- drain ----------------------------------------------------------------------


def test_drain_without_a_token_is_an_args_error_and_deletes_nothing(root):
    flush(root, ["/p/a.md"])
    with pytest.raises(verbs.VerbArgsError):
        verbs.curator(root, action="drain")
    assert len(list(spool(root).glob("*.jsonl"))) == 1


def test_drain_unlinks_exactly_the_token_and_reports_missing(root):
    a = flush(root, ["/p/a.md"])
    b = flush(root, ["/p/b.md"])
    out = verbs.curator(root, action="drain", token=[a, "00000000000000000001-gone.jsonl"])
    assert out["drained"] == [a], out
    assert out["missing"] == ["00000000000000000001-gone.jsonl"], out
    assert [p.name for p in spool(root).glob("*.jsonl")] == [b]


def test_a_token_name_is_never_followed_outside_the_spool(root):
    flush(root, ["/p/a.md"])
    victim = root / "victim.jsonl"
    victim.write_text("keep me\n")
    try:
        verbs.curator(root, action="drain", token=["../victim.jsonl"])
    except verbs.VerbArgsError:
        pass
    assert victim.exists(), "drain followed a token path out of the spool"


def test_the_race_status_hook_drain_new_flush_old_token(root):
    """The r1 B3 loss: entries appended between the agent's snapshot and its drain
    were destroyed unread. status → the hook's `status --drain` → a new flush →
    `drain(old token)` removes nothing new; the next status returns the new entries."""
    flush(root, ["/p/old.md"])
    snap = verbs.curator(root, action="status")
    r = CliRunner().invoke(cli_mod.main, ["curator", "status", "--drain"])
    assert r.exit_code == 0, r.output
    new = flush(root, ["/p/new.md"])
    out = verbs.curator(root, action="drain", token=snap["token"])
    assert out["drained"] == [] and out["missing"] == snap["token"], out
    assert (spool(root) / new).exists(), "drain(old token) deleted a file it never read"
    nxt = verbs.curator(root, action="status")
    assert nxt["token"] == [new] and _paths(nxt) == ["/p/new.md"], nxt


# ---- ENOENT = a concurrent drain (r5 S2) ----------------------------------------


def test_a_listed_file_that_vanishes_before_its_read_is_missing(root, monkeypatch):
    a = flush(root, ["/p/a.md"])
    b = flush(root, ["/p/b.md"])
    victim = spool(root) / a
    real_open, real_read_text, real_read_bytes = (Path.open, Path.read_text, Path.read_bytes)
    import builtins
    real_builtin_open = builtins.open

    def _vanish(p):
        if Path(p).name == a and victim.exists():
            victim.unlink()

    def b_open(file, *args, **kw):
        _vanish(file)
        return real_builtin_open(file, *args, **kw)

    def p_open(self, *args, **kw):
        _vanish(self)
        return real_open(self, *args, **kw)

    def p_read_text(self, *args, **kw):
        _vanish(self)
        return real_read_text(self, *args, **kw)

    def p_read_bytes(self, *args, **kw):
        _vanish(self)
        return real_read_bytes(self, *args, **kw)
    monkeypatch.setattr(builtins, "open", b_open)
    monkeypatch.setattr(Path, "open", p_open)
    monkeypatch.setattr(Path, "read_text", p_read_text)
    monkeypatch.setattr(Path, "read_bytes", p_read_bytes)
    out = verbs.curator(root, action="status")
    assert out["token"] == [b] and _paths(out) == ["/p/b.md"], out
    assert out["missing"] == [a], out


def test_an_unreadable_spool_file_raises_not_skipped(root):
    a = flush(root, ["/p/a.md"])
    (spool(root) / a).chmod(0)
    try:
        with pytest.raises((OSError, verbs.VerbError)) as ei:
            verbs.curator(root, action="status")
        assert a in str(ei.value), str(ei.value)
    finally:
        (spool(root) / a).chmod(0o644)


# ---- the legacy queue rollout ---------------------------------------------------


def _legacy(root, paths):
    q = root / "curator.queue"
    q.write_text("".join(json.dumps({"ts": 1.0, "path": p, "reason": "fs-change"}) + "\n"
                         for p in paths))
    return q


def test_status_moves_a_legacy_queue_into_the_spool_with_one_rename(root):
    q = _legacy(root, ["/p/legacy.md"])
    ino = q.stat().st_ino
    out = verbs.curator(root, action="status")
    assert not q.exists()
    assert "/p/legacy.md" in _paths(out), out
    moved = [n for n in out["token"] if (spool(root) / n).stat().st_ino == ino]
    assert len(moved) == 1, ("the legacy file was copied, not renamed", out["token"])


def test_the_legacy_queue_drains_like_any_spool_file(root):
    _legacy(root, ["/p/legacy.md"])
    out = verbs.curator(root, action="status")
    d = verbs.curator(root, action="drain", token=out["token"])
    assert d["drained"] == out["token"] and not list(spool(root).glob("*.jsonl"))


def test_a_legacy_queue_taken_by_a_concurrent_drain_is_missing(root, monkeypatch):
    q = _legacy(root, ["/p/legacy.md"])
    real_rename, real_replace = os.rename, os.replace
    real_p_rename, real_p_replace = Path.rename, Path.replace

    def _take(src):
        if Path(src).name == "curator.queue" and Path(src).exists():
            Path(src).unlink()
    monkeypatch.setattr(os, "rename", lambda s, d, *a, **k: (_take(s), real_rename(s, d))[1])
    monkeypatch.setattr(os, "replace", lambda s, d, *a, **k: (_take(s), real_replace(s, d))[1])
    monkeypatch.setattr(Path, "rename", lambda self, t: (_take(self), real_p_rename(self, t))[1])
    monkeypatch.setattr(Path, "replace", lambda self, t: (_take(self), real_p_replace(self, t))[1])
    out = verbs.curator(root, action="status")
    assert out["missing"] == ["curator.queue"], out
    assert out["token"] == [] and not q.exists()


# ---- nothing else deletes a spool file or the legacy queue (r4 M1) --------------


_DELETES = {"unlink", "remove", "rmtree", "truncate"}
_LEGACY_NAMES = ("curator.queue", "curator_queue")
_SPOOL_NAMES = ("curator.spool", "curator_spool")


def _own_nodes(fn):
    """`fn`'s AST without the bodies of functions nested in it (each nested
    function is judged on its own)."""
    stack = list(fn.body)
    while stack:
        n = stack.pop()
        yield n
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        stack.extend(ast.iter_child_nodes(n))


def _deleting_functions():
    """(file, function, curator names it uses) for every src function whose OWN
    body both names the curator queue / spool and deletes (`unlink`, `os.remove`,
    `rmtree`, `truncate`, `write_text("")`)."""
    out = []
    for p in sorted(_SRC.rglob("*.py")):
        tree = ast.parse(p.read_text())
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            nodes = list(_own_nodes(fn))
            text = " ".join(ast.unparse(n) for n in nodes
                            if isinstance(n, (ast.Constant, ast.Name, ast.Attribute,
                                              ast.JoinedStr)))
            names = [n for n in _LEGACY_NAMES + _SPOOL_NAMES if n in text]
            if not names:
                continue
            deletes = False
            for c in nodes:
                if not isinstance(c, ast.Call):
                    continue
                f = c.func
                attr = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
                if attr in _DELETES:
                    deletes = True
                if attr == "write_text" and c.args and isinstance(c.args[0], ast.Constant) \
                        and c.args[0].value == "":
                    deletes = True
            if deletes:
                out.append((p.name, fn.name, names))
    return out


def test_no_src_path_unlinks_the_legacy_queue_or_a_spool_file_but_drain_and_the_sweep():
    """Allowed: the curator `drain(token)` and the daemon's startup `*.tmp` sweep —
    functions whose name says so (`drain` / `sweep`). Everything else that deletes or
    truncates is the r1 B3 loss window again (today: cli.py `curator status --drain`
    and `curator drain`, `gmd_curator.drain_queue`). Nothing at all unlinks the legacy
    `curator.queue`: the rollout moves it into the spool with one rename."""
    found = _deleting_functions()
    bad = [f"{f}:{fn} ({', '.join(n)})" for f, fn, n in found
           if not ("drain" in fn.lower() or "sweep" in fn.lower())]
    legacy = [f"{f}:{fn} (unlinks the legacy queue)" for f, fn, n in found
              if any(x in n for x in _LEGACY_NAMES) and not any(x in n for x in _SPOOL_NAMES)]
    offenders = sorted(set(bad) | set(legacy))
    assert not offenders, ("these delete the curator queue/spool outside drain(token):\n"
                           + "\n".join(offenders))


# ---- the scheduled scan reads the watcher's format and drains by token -----------


def _bad_gmd(proj: Path) -> Path:
    p = proj / "docs" / "bad.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('---\ngmd: "0.1"\nid: bad\n---\n# no anchor here\n')
    return p


def _failing_lint(tmp_path, monkeypatch):
    lint = tmp_path / "lint.py"
    lint.write_text("import sys; print('E: bad'); sys.exit(1)\n")
    monkeypatch.setenv("RMX_GMD_LINT", str(lint))


def test_scan_finds_files_named_in_the_watchers_format(root, tmp_path, monkeypatch):
    """r2 B1: `read_queue` read each line as a raw path; the watcher writes JSON, so
    the scheduled scan found zero files and then deleted the queue."""
    _failing_lint(tmp_path, monkeypatch)
    bad = _bad_gmd(root.parent)
    flush(root, [str(bad)])
    cands = gmd_curator.scan(root)
    assert [c["path"] for c in cands] == [str(bad)], cands


def test_scan_and_enqueue_drains_only_the_files_it_read(root, tmp_path, monkeypatch):
    _failing_lint(tmp_path, monkeypatch)
    monkeypatch.setattr("refmatrix.bus.refine_path", lambda: tmp_path / "refine.jsonl")
    bad = _bad_gmd(root.parent)
    flush(root, [str(bad)])
    tmpf = spool(root) / f"{time.time_ns():020d}-{uuid.uuid4()}.jsonl.tmp"
    tmpf.write_text("{}\n")
    res = gmd_curator.scan_and_enqueue(root, drain=True)
    assert res["candidates"] == 1, res
    assert not list(spool(root).glob("*.jsonl")), "the scanned file was not drained"
    assert tmpf.exists(), "the scan deleted a file it never read"


# ---- the CLI carries the token ---------------------------------------------------


def test_cli_status_json_emits_the_token_and_entries(root):
    a = flush(root, ["/p/a.md"])
    r = CliRunner().invoke(cli_mod.main, ["curator", "status", "--json"])
    assert r.exit_code == 0, r.output
    doc = json.loads(r.output)
    assert doc["token"] == [a] and [e["path"] for e in doc["entries"]] == ["/p/a.md"], doc


def test_cli_drain_token_from_a_status_json_file(root, tmp_path):
    a = flush(root, ["/p/a.md"])
    snap = tmp_path / "snap.json"
    r = CliRunner().invoke(cli_mod.main, ["curator", "status", "--json"])
    snap.write_text(r.output)
    b = flush(root, ["/p/b.md"])
    r2 = CliRunner().invoke(cli_mod.main, ["curator", "drain", "--token", f"@{snap}"])
    assert r2.exit_code == 0, r2.output
    assert [p.name for p in spool(root).glob("*.jsonl")] == [b]
    assert a not in [p.name for p in spool(root).glob("*.jsonl")]


def test_cli_drain_with_repeated_token_names(root):
    a = flush(root, ["/p/a.md"])
    b = flush(root, ["/p/b.md"])
    c = flush(root, ["/p/c.md"])
    r = CliRunner().invoke(cli_mod.main, ["curator", "drain", "--token", a, "--token", b])
    assert r.exit_code == 0, r.output
    assert [p.name for p in spool(root).glob("*.jsonl")] == [c]


def test_cli_drain_without_a_token_fails_and_deletes_nothing(root):
    flush(root, ["/p/a.md"])
    r = CliRunner().invoke(cli_mod.main, ["curator", "drain"])
    assert r.exit_code != 0, r.output
    assert len(list(spool(root).glob("*.jsonl"))) == 1


def test_cli_hook_form_prints_the_summary_within_limit_and_drains_what_it_read(root):
    flush(root, [f"/p/f{i}.md" for i in range(5)])
    r = CliRunner().invoke(cli_mod.main, ["curator", "status", "--drain", "--limit", "2"])
    assert r.exit_code == 0, r.output
    assert "curator-queue: 5" in r.output and "+3 more" in r.output, r.output
    assert not list(spool(root).glob("*.jsonl"))


# ---- the gmd-curator flow carries the token (r5 S1) ------------------------------


@pytest.mark.parametrize("rel", ["src/refmatrix/templates/agents/gmd-curator.md",
                                 ".claude/agents/gmd-curator.md"])
def test_the_gmd_curator_flow_snapshots_with_json_and_drains_by_token(rel):
    text = (_REPO / rel).read_text()
    assert "rmx curator status --json" in text, rel
    drains = [ln for ln in text.splitlines() if re.search(r"rmx curator drain\b", ln)]
    assert drains, rel
    bare = [ln for ln in drains if "--token" not in ln]
    assert not bare, f"{rel}: a drain without the token:\n" + "\n".join(bare)


# ---- the watcher writes the spool; startup sweeps stale tmp (real daemon) ---------


@pytest.mark.timeout(120)
def test_a_real_daemon_watcher_writes_one_spool_file_per_flush_and_sweeps_tmp(monkeypatch):
    monkeypatch.delenv("RMX_PARTITION", raising=False)
    base, root = short_root("r37w-")
    proj = root.parent
    try:
        Store(root).init()
        (proj / "docs" / "adr").mkdir(parents=True)   # a curator-relevant segment
        spool(root).mkdir()
        stale = spool(root) / f"{1:020d}-{uuid.uuid4()}.jsonl.tmp"
        stale.write_text("{}\n")
        pid = dm.spawn_daemon_subprocess(root, watch_root=[proj])
        assert pid and dm.ping(root)
        deadline = time.monotonic() + 20
        while stale.exists() and time.monotonic() < deadline:
            time.sleep(0.2)
        assert not stale.exists(), "the daemon did not sweep its stale *.tmp at startup"
        (proj / "docs" / "adr" / "ADR-0001-notes.md").write_text(
            '---\ngmd: "0.1"\nid: notes\n---\n# N {#root}\n')
        deadline = time.monotonic() + 30
        files: list = []
        while time.monotonic() < deadline:
            files = sorted(spool(root).glob("*.jsonl"))
            if files:
                break
            time.sleep(0.3)
        assert files, "the watcher wrote no spool file"
        assert all(_NAME.match(f.name) for f in files), [f.name for f in files]
        rows = [json.loads(ln) for f in files for ln in f.read_text().splitlines() if ln]
        assert any(r.get("path", "").endswith("ADR-0001-notes.md") for r in rows), rows
        assert all({"ts", "path", "reason"} <= set(r) for r in rows), rows
        assert not (root / "curator.queue").exists(), "the watcher still appends the legacy queue"
    finally:
        if dm.ping(root):
            dm.stop_daemon(root)
        rm(base)
