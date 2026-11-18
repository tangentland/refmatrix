"""bug-216 rev 4 — AC-11 (R10 pending refs), AC-12 (R11 built-in include), AC-13 (R12 one ignore
list), and `ingest-gmd <subdir>` finding the project root (#rev-4-accepted).

Spec: workflow/plans/task-bug216-rule-docs-in-graph.md (#rev-4, #r10, #r11, #r12, #ac-11,
#ac-12, #ac-13).

WHY.
- R10: GMD ingest skips unchanged files and nothing retried a dangling `rel:` target when it
  appeared later, so un-ignoring the rule docs (R4) alone would leave the 247 lines dangling.
- R11: the R3 gate went red in every clone / CI checkout (no `.refmatrix_ignore` there, and the
  hidden-dir rule drops `.claude/PROJECT_PROFILE.md`). Precedence: `!path` > explicit ignore >
  built-in include of GMD `CLAUDE.md` / `.claude/PROJECT_PROFILE.md` > hidden-dir and
  INGEST_IGNORE_DIRS.
- R12: `watch.py` kept its own `IGNORE_DIRS` (`__pycache__`, `dist`, `build`), so the watcher and
  the ingest walk disagreed on those dirs.

Everything is behavioural on throwaway stores under short `/tmp` roots; pending rows are observed
through what they DO (an edge appears; evidence is never duplicated; a purged citer leaves
nothing), not through a table name the spec does not fix.
"""
from __future__ import annotations

import rmx_sandbox  # task-29.4 #r5: test roots live under the sandbox root (short_root)
import ast
import os
import shutil
import tempfile
from pathlib import Path

import pytest

from refmatrix.ingest_gmd import ingest_gmd_paths
from refmatrix.store import Store
from tests.test_bug216_rule_docs_e2e import (
    CLAUDE_LINE,
    _all_files,
    _assert_edge_landed,
    _eid,
    _ingested,
    _lid,
    _make_proj,
    _open,
    _run,
    _write_spec,
)

REPO = Path(__file__).resolve().parents[1]


def _gmd(doc_id: str, body: str = "Body.\n") -> str:
    return (f'---\ngmd: "0.1"\nid: {doc_id}\ntitle: "Fixture document"\ntags: [t]\n---\n\n'
            f"# Fixture document {{#root}}\n\n{body}")


@pytest.fixture
def store_env():
    base = Path(rmx_sandbox.short_root("b216p4")).resolve()
    proj = base / "proj"
    (proj / "docs").mkdir(parents=True)
    root = proj / ".refmatrix"
    root.mkdir()
    s = Store(root)
    s.init()
    s.close()
    yield proj, root
    shutil.rmtree(base)


def _ingest(root: Path, paths: list[Path]):
    s = Store(root)
    s.init()
    try:
        return ingest_gmd_paths(s, paths)
    finally:
        s.close()


def _write(proj: Path, rel: str, body: str) -> Path:
    p = proj / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)
    return p


# ---------------------------------------------------------------- AC-11 (R10)

A_CITES = _gmd("a", "Intro.\n\n## Cite {#cite}\n\nText.\n\n"
                    "rel: derives-from -> [[b-doc]]\n"
                    "rel: depends-on -> [[b-doc#sec]]\n")
B_DOC = _gmd("b-doc", "Target.\n\n## Sec {#sec}\n\nS.\n")
DERIVES_LINE = A_CITES.splitlines().index("rel: derives-from -> [[b-doc]]") + 1
DEPENDS_LINE = A_CITES.splitlines().index("rel: depends-on -> [[b-doc#sec]]") + 1


def _rows_from(s: Store, verb: str, src: int) -> list[tuple[str, str, str | None]]:
    lid = _lid(s, verb)
    if lid is None:
        return []
    return [(k, n, str(Path(p).resolve()) if p else None) for k, n, p in s._connect().execute(
        "SELECT e.kind, e.name, e.path FROM entity_links el JOIN entities e ON e.id=el.entity_id "
        "WHERE el.linkage_id=? AND el.concept_id=?", (lid, src)).fetchall()]


def _evidence_at(s: Store, file: Path, line: int) -> int:
    return s._connect().execute(
        "SELECT count(*) FROM linkage_evidence WHERE file=? AND line=?",
        (str(file), line)).fetchone()[0]


def test_ac11_a_pending_ref_resolves_when_its_target_is_ingested(store_env):
    """A cites `[[b-doc]]` and `[[b-doc#sec]]` before b-doc exists; ingesting b-doc LATER, in a
    separate call, lands both edges with evidence — A is not re-ingested."""
    proj, root = store_env
    a = _write(proj, "docs/a.md", A_CITES)
    st = _ingest(root, [a])
    assert len(st.unresolved) >= 2, f"precondition: both lines unresolved; {st.report()}"
    b = _write(proj, "docs/b.md", B_DOC)
    _ingest(root, [b])
    s = _open(root)
    try:
        src = _eid(s, "concept", "a#cite")
        assert _rows_from(s, "derives-from", src) == [("doc", "b-doc", str(b.resolve()))], (
            "the pending bare ref did not resolve (to B's doc) when B was ingested")
        assert _rows_from(s, "depends-on", src) == [("concept", "b-doc#sec", str(b.resolve()))]
        assert _evidence_at(s, a, DERIVES_LINE) == 1
        assert _evidence_at(s, a, DEPENDS_LINE) == 1
    finally:
        s.close()


def test_ac11_a_resolved_pending_row_is_cleared(store_env):
    """Mutation 'never clear pending rows': ingesting b-doc a second time (changed) must not
    resolve the same line again — exactly one edge and one evidence row per line."""
    proj, root = store_env
    a = _write(proj, "docs/a.md", A_CITES)
    _ingest(root, [a])
    b = _write(proj, "docs/b.md", B_DOC)
    _ingest(root, [b])
    b.write_text(B_DOC + "\nEdited.\n")
    _ingest(root, [b])
    s = _open(root)
    try:
        src = _eid(s, "concept", "a#cite")
        assert len(_rows_from(s, "derives-from", src)) == 1
        assert _evidence_at(s, a, DERIVES_LINE) == 1, "a cleared pending row resolved twice"
        assert _evidence_at(s, a, DEPENDS_LINE) == 1, "a cleared pending row resolved twice"
    finally:
        s.close()


def test_ac11_purging_the_citer_drops_its_pending_rows(store_env):
    """Purge A while its refs are pending; ingesting b-doc then writes nothing for A — no edge,
    no evidence for A's file, and no `entity_links` row naming an entity that no longer
    exists."""
    proj, root = store_env
    a = _write(proj, "docs/a.md", A_CITES)
    _ingest(root, [a])
    s = _open(root)
    try:
        s.purge_path(str(a))
        assert _eid(s, "concept", "a#cite") is None, "precondition: the purge removed A"
    finally:
        s.close()
    _ingest(root, [_write(proj, "docs/b.md", B_DOC)])
    s = _open(root)
    try:
        con = s._connect()
        ev = con.execute("SELECT count(*) FROM linkage_evidence WHERE file=?",
                         (str(a),)).fetchone()[0]
        dead = con.execute(
            "SELECT count(*) FROM entity_links el WHERE NOT EXISTS "
            "(SELECT 1 FROM entities e WHERE e.id = el.concept_id) OR NOT EXISTS "
            "(SELECT 1 FROM entities e WHERE e.id = el.entity_id)").fetchone()[0]
        assert (ev, dead) == (0, 0), f"a purged citer's pending ref resolved: ev={ev} dead={dead}"
    finally:
        s.close()


def test_ac11_resolution_is_counted_in_the_ingest_report(store_env):
    """R10: 'Counted and printed' — the ingest that resolves pending refs says so."""
    proj, root = store_env
    _ingest(root, [_write(proj, "docs/a.md", A_CITES)])
    st = _ingest(root, [_write(proj, "docs/b.md", B_DOC)])
    assert "pending" in st.report().lower(), st.report()


def test_ac11_the_rule_doc_lines_land_when_claude_md_is_unignored_without_touching_citers():
    """The R4 apply, end to end through `sync_files`: the citing doc was synced while CLAUDE.md
    was ignored; the ignore line goes, ONLY CLAUDE.md is synced, and the citing line lands on
    CLAUDE.md's node with its evidence. (AC-3 touched the citer; R10 makes that unnecessary.)"""
    from refmatrix.sync import sync_files
    base, proj, root = _make_proj()
    try:
        _write_spec(proj, [".claude", "CLAUDE.md"])
        s = _open(root)
        try:
            sync_files(s, [str(p) for p in _all_files(proj)], project_root=proj)
            assert _eid(s, "concept", "claude#no-silent-failures") is None, "precondition"
        finally:
            s.close()
        _write_spec(proj, [".claude"])
        s = _open(root)
        try:
            sync_files(s, [str(proj / "CLAUDE.md")], project_root=proj)
            _assert_edge_landed(s, proj, "claude#no-silent-failures", "finding#swallow",
                                CLAUDE_LINE)
        finally:
            s.close()
    finally:
        shutil.rmtree(base)


# ---------------------------------------------------------------- AC-12 (R11)


def _tree(root: Path, files: dict[str, str]) -> None:
    for rel, body in files.items():
        _write(root, rel, body)


@pytest.fixture
def bare_root():
    base = Path(rmx_sandbox.short_root("b216r11")).resolve()
    yield base
    shutil.rmtree(base)


def test_ac12_no_ignore_file_includes_the_gmd_profile(bare_root):
    """No `.refmatrix_ignore` at all: a profile with GMD frontmatter is included, the rest of
    `.claude/` is not, and CLAUDE.md (GMD) is included."""
    from refmatrix.ingest import should_ignore
    _tree(bare_root, {"CLAUDE.md": _gmd("claude"),
                      ".claude/PROJECT_PROFILE.md": _gmd("project-profile"),
                      ".claude/agents/x.md": _gmd("agent-x")})
    assert should_ignore(bare_root / ".claude/PROJECT_PROFILE.md", bare_root) is False
    assert should_ignore(bare_root / "CLAUDE.md", bare_root) is False
    assert should_ignore(bare_root / ".claude/agents/x.md", bare_root) is True


def test_ac12_guard_a_profile_without_frontmatter_is_not_included(bare_root):
    """GUARD (green at HEAD): the built-in include needs GMD frontmatter."""
    from refmatrix.ingest import should_ignore
    _tree(bare_root, {".claude/PROJECT_PROFILE.md": "# Profile\n\nPlain markdown.\n"})
    assert should_ignore(bare_root / ".claude/PROJECT_PROFILE.md", bare_root) is True


def test_ac12_guard_explicit_ignore_lines_beat_the_builtin_include(bare_root):
    """GUARD: the fleet's ignore file lists `CLAUDE.md` and `.claude`; it keeps excluding both
    until the user removes the lines (R11, Q-2)."""
    from refmatrix.ingest import should_ignore
    _tree(bare_root, {"CLAUDE.md": _gmd("claude"),
                      ".claude/PROJECT_PROFILE.md": _gmd("project-profile")})
    _write(bare_root, ".refmatrix/.refmatrix_ignore", ".claude\nCLAUDE.md\n")
    assert should_ignore(bare_root / "CLAUDE.md", bare_root) is True
    assert should_ignore(bare_root / ".claude/PROJECT_PROFILE.md", bare_root) is True


def test_ac12_reinclude_beats_an_explicit_ignore(bare_root):
    from refmatrix.ingest import should_ignore
    _tree(bare_root, {"CLAUDE.md": _gmd("claude"),
                      ".claude/PROJECT_PROFILE.md": _gmd("project-profile")})
    _write(bare_root, ".refmatrix/.refmatrix_ignore",
           ".claude\nCLAUDE.md\n!CLAUDE.md\n!.claude/PROJECT_PROFILE.md\n")
    assert should_ignore(bare_root / "CLAUDE.md", bare_root) is False
    assert should_ignore(bare_root / ".claude/PROJECT_PROFILE.md", bare_root) is False


@pytest.mark.parametrize("route", ["sync", "watcher", "op-ingest-gmd", "cli-ingest-gmd",
                                   "ingest-path"])
def test_ac12_every_walker_ingests_the_rule_docs_with_no_ignore_file(route, monkeypatch):
    base, proj, root = _make_proj()
    try:
        _run(route, proj, root, monkeypatch)
        s = _open(root)
        try:
            got = _ingested(s, proj)
        finally:
            s.close()
        want = {"CLAUDE.md", ".claude/PROJECT_PROFILE.md", "docs/finding.md", "docs/other.md",
                "src/refmatrix/templates/t.md"}
        assert got == want, f"{route}: missing {sorted(want - got)}, extra {sorted(got - want)}"
    finally:
        shutil.rmtree(base)


def _gate_root() -> Path:
    import sys
    root = Path(rmx_sandbox.short_root("b216g")).resolve()
    (root / ".git").mkdir()
    (root / "scripts").mkdir()
    for f in ("check-gmd-parity.py", "lint-gmd.sh"):
        shutil.copy2(REPO / "scripts" / f, root / "scripts" / f)
    # T0.1' R1.4: lint-gmd.sh asks scripts/gmd_memdir.py for its memory dir; a gate root that
    # copies the script copies its resolver.
    shutil.copy2(REPO / "scripts" / "gmd_memdir.py", root / "scripts" / "gmd_memdir.py")
    (root / "tools" / "gmd").mkdir(parents=True)
    shutil.copy2(REPO / "tools" / "gmd" / "lint.py", root / "tools" / "gmd" / "lint.py")
    (root / "src").symlink_to(REPO / "src")
    (root / ".venv-eval").symlink_to(Path(sys.prefix))
    _tree(root, {"CLAUDE.md": _gmd("claude"),
                 ".claude/PROJECT_PROFILE.md": _gmd("project-profile"),
                 "docs/d.md": _gmd("d"), "workflow/w.md": _gmd("w"), "eval/e.md": _gmd("e")})
    return root


def test_ac12_the_gate_passes_a_checkout_with_no_ignore_file():
    """R11's point: a fresh clone / CI has no `.refmatrix/` at all, and the R3 gate must pass.
    Green at HEAD (no scope check yet) — a guard against R3 landing without R11."""
    import subprocess
    root = _gate_root()
    try:
        assert not (root / ".refmatrix").exists()
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        p = subprocess.run(["bash", str(root / "scripts" / "lint-gmd.sh")], capture_output=True,
                           text=True, cwd=root, env=env, timeout=600)
        assert p.returncode == 0, p.stdout + p.stderr
    finally:
        shutil.rmtree(root)


# ---------------------------------------------------------------- AC-13 (R12)

TOOL_DIRS = ("dist", "build", "__pycache__")


def test_ac13_ingest_ignore_dirs_holds_the_watchers_dirs():
    from refmatrix.ingest import INGEST_IGNORE_DIRS
    assert set(INGEST_IGNORE_DIRS) >= {"node_modules", "venv", *TOOL_DIRS}, INGEST_IGNORE_DIRS


def test_ac13_watch_py_defines_no_ignore_list():
    import refmatrix.watch as w
    tree = ast.parse(Path(w.__file__).read_text())
    names = [t.id for n in tree.body if isinstance(n, (ast.Assign, ast.AnnAssign))
             for t in (n.targets if isinstance(n, ast.Assign) else [n.target])
             if isinstance(t, ast.Name) and "IGNORE" in t.id.upper()]
    assert names == [], f"watch.py still defines its own ignore list: {names}"


@pytest.mark.parametrize("route", ["sync", "watcher", "op-ingest-gmd", "cli-ingest-gmd",
                                   "ingest-path"])
def test_ac13_tool_dirs_are_ignored_by_every_walker(route, monkeypatch):
    base, proj, root = _make_proj()
    try:
        for d in TOOL_DIRS:
            _write(proj, f"{d}/x.md", _gmd(f"tool-{d.strip('_')}"))
            _write(proj, f"pkg/{d}/y.md", _gmd(f"nested-{d.strip('_')}"))
        _write_spec(proj, [".claude", "!.claude/PROJECT_PROFILE.md"])
        _run(route, proj, root, monkeypatch)
        s = _open(root)
        try:
            got = _ingested(s, proj)
        finally:
            s.close()
        leaked = sorted(p for p in got if any(seg in TOOL_DIRS for seg in Path(p).parts))
        assert leaked == [], f"{route} ingested {leaked}"
    finally:
        shutil.rmtree(base)


# ---------------------------------------------------------------- ingest-gmd <subdir>


@pytest.mark.parametrize("route", ["op", "cli"])
def test_ingest_gmd_on_a_subdir_reads_the_spec_from_the_project_root(route, monkeypatch):
    """`rmx ingest-gmd docs/` must find the project root by walking up to `.refmatrix/` and
    apply the spec relative to IT: the anchored `docs/private` line excludes
    `docs/private/p.md`. (Taking the target dir as the root would anchor the line at
    `docs/docs/private` and let it through.)"""
    base, proj, root = _make_proj()
    try:
        _write(proj, "docs/private/p.md", _gmd("private-p"))
        _write_spec(proj, [".claude", "!.claude/PROJECT_PROFILE.md", "docs/private"])
        target = proj / "docs"
        if route == "op":
            from refmatrix.daemon import Daemon, _op_ingest_gmd
            d = Daemon(root)
            d.store = _open(root)
            try:
                _op_ingest_gmd(d, {"targets": [str(target)]})
            finally:
                d.store.close()
        else:
            from click.testing import CliRunner

            from refmatrix import cli as cli_mod
            monkeypatch.setenv("REFMATRIX_ROOT", str(root))
            monkeypatch.delenv("RMX_PARTITION", raising=False)
            r = CliRunner().invoke(cli_mod.main, ["ingest-gmd", str(target)],
                                   catch_exceptions=False)
            assert r.exit_code == 0, r.output
        s = _open(root)
        try:
            got = _ingested(s, proj)
        finally:
            s.close()
        assert "docs/private/p.md" not in got, got
        assert "docs/finding.md" in got, got
    finally:
        shutil.rmtree(base)
