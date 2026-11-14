"""bug-216 remedy RED — bsd-216 r1 at df092ac (DIRTY 1B/2S/4M, NO-GO), ruling L81.

Report: workflow/bullshit/2026-11-13-1619-bug216-r1-df092ac.md (dev master).
Ruling: workflow/plan-review-2026-11-13.md, row L81.

  B1  the segment and spec rules judge a path against the PROJECT ROOT the store belongs to,
      never the ingest target: `rmx ingest <memdir>`, MCP `rmx_ingest` on a memdir and
      `rmx ingest <proj>/.claude` store no doc rows, as at 758bca1 (at df092ac `base` defaults to
      the TARGET, so a target under `.claude/` sheds its hidden ancestor and memories land as
      kind=doc — bug-220's door, opened a second way).
  S1  R4 at merge = the ignore edit THEN `rmx ingest .`: a store built by OLD code (758bca1)
      binds its rule-doc citers only through the ingest step; the edit + a sync of the two docs
      alone binds nothing (old-code citers have no pending rows and are mtime-skipped).
  S2  `pending_refs` survives a replica slot merge (all three `replica_merge` table lists) and
      `merge_partition` (rows repointed to the surviving partition; rows whose source entity is
      gone dropped AND counted).
  M1  kills the three mutations that survived r1: the `build_context` denotes chain, the dump's
      pending emission, `resolve_pending_refs`' source-exists check.
  M2  `build_context`'s MENTION chain does not cross `denotes` (as PageRank's fold, until G30);
      `neighbors` still lists the raw `denotes` link.
  M3  the watcher's delete event for a built-in-included GMD doc purges it (the GMD sniff ran on
      a file that no longer exists, so the event was judged irrelevant and dropped).

Contracts this file assumes where the ruling names no field: `merge_partition`'s result counts
the dropped rows as `pending_refs_dropped`; the slot-merge and audit results count the table as
`pending_refs` in their per-table count dicts.

Every store is a throwaway under a short `/tmp` mkdtemp root; no live `.refmatrix/` is touched.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod
from refmatrix import daemon as daemon_mod
from refmatrix import verbs
from refmatrix.ingest_gmd import ingest_gmd_paths
from refmatrix.store import Store

REPO = Path(__file__).resolve().parents[1]
OLD_SHA = "758bca1"          # the branch base: the code every live store was built by


def _gmd(doc_id: str, body: str = "Body.\n", extra_fm: str = "") -> str:
    return (f'---\ngmd: "0.1"\nid: {doc_id}\ntitle: "Fixture document"\ntags: [t]\n{extra_fm}'
            f"---\n\n# Fixture document {{#root}}\n\n{body}")


def _write(root: Path, rel: str, body: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)
    return p


def _new_store(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    s = Store(root)
    s.init()
    s.close()


def _open(root: Path) -> Store:
    s = Store(root)
    s.init()
    return s


@pytest.fixture
def base():
    b = Path(tempfile.mkdtemp(prefix="b216r", dir="/tmp")).resolve()
    yield b
    shutil.rmtree(b)


def _lid(s: Store, verb: str) -> "int | None":
    r = s._connect().execute("SELECT id FROM linkage_types WHERE name=?", (verb,)).fetchone()
    return None if r is None else int(r[0])


def _link_any(s: Store, verb: str, c: int, e: int) -> None:
    try:
        s.get_linkage_id(verb)
    except KeyError:
        s.add_linkage_type(verb, directed=True, description=f"bug-216 fixture '{verb}'")
    s.link(verb, c, e)


# ================================================================ B1

MEM = ".claude/projects/x/memory"


@pytest.fixture
def b1(base, monkeypatch):
    proj = base / "proj"
    _write(proj, "docs/d.md", _gmd("d"))
    _write(proj, f"{MEM}/feedback_a.md", _gmd("feedback_a", extra_fm="metadata:\n  type: feedback\n"))
    _write(proj, f"{MEM}/feedback/feedback_b.md",
           _gmd("feedback_b", extra_fm="metadata:\n  type: feedback\n"))
    _write(proj, ".claude/agents/x.md", _gmd("agent-x"))
    root = proj / ".refmatrix"
    _new_store(root)
    monkeypatch.setenv("REFMATRIX_ROOT", str(root))
    monkeypatch.delenv("RMX_PARTITION", raising=False)
    monkeypatch.setattr(cli_mod, "_partition_override", None, raising=False)
    return {"proj": proj, "root": root, "mem": proj / MEM, "claude": proj / ".claude"}


def _rows_under(root: Path, under: Path) -> "list[tuple[str, str]]":
    s = _open(root)
    try:
        return sorted((str(k), str(n)) for k, n, p in s._connect().execute(
            "SELECT kind, name, path FROM entities WHERE path IS NOT NULL").fetchall()
            if str(Path(p).resolve()).startswith(str(under) + "/"))
    finally:
        s.close()


def _assert_no_rows_under(root: Path, under: Path, what: str) -> None:
    rows = _rows_under(root, under)
    docs = [r for r in rows if r[0] == "doc"]
    assert docs == [], f"{what}: kind=doc rows from under {under.name}/: {docs}"
    assert rows == [], f"{what}: rows from under {under.name}/: {rows}"


def test_b1_cli_ingest_of_a_memdir_under_the_project_stores_no_doc_rows(b1):
    """`rmx ingest <proj>/.claude/projects/x/memory` (daemon down: the CLI's in-process branch).
    Judged against the project root, every path carries `.claude`."""
    r = CliRunner().invoke(cli_mod.main, ["ingest", str(b1["mem"])], catch_exceptions=False)
    assert r.exit_code == 0, r.output
    _assert_no_rows_under(b1["root"], b1["claude"], "rmx ingest <memdir>")


def test_b1_cli_ingest_of_dot_claude_stores_no_doc_rows(b1):
    r = CliRunner().invoke(cli_mod.main, ["ingest", str(b1["claude"])], catch_exceptions=False)
    assert r.exit_code == 0, r.output
    _assert_no_rows_under(b1["root"], b1["claude"], "rmx ingest <proj>/.claude")


def test_b1_mcp_rmx_ingest_of_a_memdir_stores_no_doc_rows(b1, monkeypatch):
    """MCP `rmx_ingest(path=<memdir>)`, the REAL `_op_ingest_path` on an in-process daemon. The
    transport fake answers `ingest_path_start` by running the op body synchronously (the
    detached job runs the same `_op_ingest_path`)."""
    import refmatrix.mcp as mcp
    d = daemon_mod.Daemon(b1["root"])
    d.store = _open(b1["root"])

    def _call(root, op, args, **kw):
        if op == "ingest_path_start":
            daemon_mod._op_ingest_path(d, dict(args))
            return {"ok": True, "result": {"job_id": "sync", "status": "done"}}
        return {"ok": True, "result": daemon_mod.OPS[op](d, dict(args))}
    monkeypatch.setattr(verbs, "require_daemon", lambda *a, **k: None)
    monkeypatch.setattr(daemon_mod, "call", _call)
    try:
        res = mcp.TOOLS["rmx_ingest"]["fn"]({"root": str(b1["root"]), "path": str(b1["mem"])})
        assert "error" not in res, res
    finally:
        d.store.close()
    _assert_no_rows_under(b1["root"], b1["claude"], "MCP rmx_ingest(<memdir>)")


def test_b1_guard_the_project_root_ingest_still_lands_its_docs(b1):
    """GUARD: `rmx ingest <proj>` lands `docs/d.md` and nothing from `.claude/`."""
    r = CliRunner().invoke(cli_mod.main, ["ingest", str(b1["proj"])], catch_exceptions=False)
    assert r.exit_code == 0, r.output
    assert ("doc", "d") in _rows_under(b1["root"], b1["proj"])
    _assert_no_rows_under(b1["root"], b1["claude"], "rmx ingest <proj>")


# ================================================================ S1

CLAUDE_MD = _gmd("claude", "Rules.\n\n## No silent failures {#no-silent-failures}\n\nNever.\n")
PROFILE_MD = _gmd("project-profile", "Facts.\n\n## Constraints {#constraints}\n\nDaemon.\n")
FINDING_MD = _gmd("finding", "Intro.\n\n## Swallow {#swallow}\n\nA bare except.\n\n"
                             "rel: contradicts -> [[claude#no-silent-failures]]\n\n"
                             "## Profile cite {#profile-cite}\n\nDirect open.\n\n"
                             "rel: contradicts -> [[project-profile#constraints]]\n")
OLD_SPEC = ".claude\nCLAUDE.md\nsrc/refmatrix/templates\n"
R4_SPEC = ".claude\n!.claude/PROJECT_PROFILE.md\nsrc/refmatrix/templates\n"

_OLD_BUILD = """
import sys
sys.path.insert(0, sys.argv[1])
import refmatrix
assert refmatrix.__file__.startswith(sys.argv[1]), refmatrix.__file__
from pathlib import Path
from refmatrix.store import Store
s = Store(Path(sys.argv[2]))
s.init()
proj = Path(sys.argv[3])
try:
    if sys.argv[4] == "ingest":
        from refmatrix.ingest import ingest_path
        print("old ingest_path ->", ingest_path(s, proj))
    elif sys.argv[4] == "sync":
        from refmatrix.sync import sync_files
        files = [str(p) for p in sorted(proj.rglob("*.md")) if ".refmatrix" not in p.parts]
        print("old sync_files ->", sync_files(s, files, project_root=proj))
    else:
        from refmatrix.ingest_gmd import ingest_gmd_paths
        files = [p for p in sorted(proj.rglob("*.md")) if ".refmatrix" not in p.parts
                 and ".claude" not in p.parts and p.name != "CLAUDE.md"]
        print("old ingest_gmd_paths ->", ingest_gmd_paths(s, files).report())
finally:
    s.close()
"""


def _old_src(base: Path) -> Path:
    """`src/` at OLD_SHA, extracted from this checkout's history (read-only on the repo)."""
    out = base / "oldsrc"
    out.mkdir()
    arch = subprocess.run(["git", "-C", str(REPO), "archive", OLD_SHA, "src"],
                          capture_output=True, check=True)
    subprocess.run(["tar", "-x", "-C", str(out)], input=arch.stdout, check=True)
    return out / "src"


@pytest.fixture(params=["ingest", "sync", "ingest-gmd"])
def old_store(base, request):
    """A project and its store built by 758bca1 code, with the 2026-09-04 ignore file
    (`.claude`, `CLAUDE.md`): the shape of every live store before bug-216. Two builders,
    because they leave different rows (measured, 2026-11-14): 758bca1's `ingest_path` and its
    `sync_files` both leave a plain relpath `doc` row (`docs/finding.md`) beside the GMD doc
    (`finding`, content hash stamped); its `ingest_gmd_paths` (the `rmx ingest-gmd <dir>` route,
    the old code honouring no ignore spec there, so the rule docs are left out by the caller)
    leaves the GMD doc only. The new `_ingest_tree` purges a legacy relpath row by PATH before
    the GMD pass, which takes the GMD doc with it and defeats the content-hash resume skip — so
    `rmx ingest .` re-processes the citer only where the relpath row exists. Without it the citer
    is skipped as unchanged, records no pending rows, and binds nothing."""
    proj = base / "proj"
    _write(proj, "CLAUDE.md", CLAUDE_MD)
    _write(proj, ".claude/PROJECT_PROFILE.md", PROFILE_MD)
    _write(proj, "docs/finding.md", FINDING_MD)
    root = proj / ".refmatrix"
    root.mkdir()
    (root / ".refmatrix_ignore").write_text(OLD_SPEC)
    env = dict(os.environ)
    p = subprocess.run([sys.executable, "-c", _OLD_BUILD, str(_old_src(base)), str(root),
                        str(proj), request.param], capture_output=True, text=True, env=env,
                       timeout=600)
    assert p.returncode == 0, p.stdout + p.stderr
    s = _open(root)
    try:
        assert s.get_entity("concept", "finding#swallow") is not None, "old build: no citer"
        assert s.get_entity("concept", "claude#no-silent-failures") is None, "old build: rule doc in"
    finally:
        s.close()
    return {"proj": proj, "root": root, "built_by": request.param}


def _bound(root: Path) -> "dict[str, int]":
    """`contradicts` rows landing on each rule doc's NODE (entity side = the target)."""
    s = _open(root)
    try:
        lid = _lid(s, "contradicts")
        out = {}
        for tgt in ("claude#no-silent-failures", "project-profile#constraints"):
            e = s.get_entity("concept", tgt)
            out[tgt] = 0 if (e is None or lid is None) else int(s._connect().execute(
                "SELECT count(*) FROM entity_links WHERE linkage_id=? AND entity_id=?",
                (lid, e.id)).fetchone()[0])
        return out
    finally:
        s.close()


def _r4(o) -> None:
    f = o["root"] / ".refmatrix_ignore"
    t = f.stat().st_mtime
    f.write_text(R4_SPEC)
    os.utime(f, (t + 5, t + 5))


def test_s1_on_an_old_code_store_the_r4_edit_and_a_sync_of_the_docs_bind_nothing(old_store):
    """Documents WHY R4's procedure has an ingest step: the edit makes no file event, and a sync
    of the two rule docs lands them but binds none of the old-code citers (no pending rows; the
    citer is mtime-skipped)."""
    from refmatrix.sync import sync_files
    _r4(old_store)
    s = _open(old_store["root"])
    try:
        sync_files(s, [str(old_store["proj"] / "CLAUDE.md"),
                       str(old_store["proj"] / ".claude/PROJECT_PROFILE.md")],
                   project_root=old_store["proj"])
        assert s.get_entity("concept", "claude#no-silent-failures") is not None
        assert s.get_entity("concept", "project-profile#constraints") is not None
    finally:
        s.close()
    assert _bound(old_store["root"]) == {"claude#no-silent-failures": 0,
                                         "project-profile#constraints": 0}


def test_s1_on_an_old_code_store_the_r4_edit_then_ingest_dot_binds_the_citers(old_store):
    """R4 at merge (L81 S1): the ignore edit THEN `rmx ingest .` (here `ingest_path(proj)`, the
    op `rmx ingest .` runs): both citing lines bind on the rule docs' nodes — for a store whose
    citers came in through the watcher / sync too, where the citer's GMD doc carries a matching
    content hash and nothing else forces it to be re-processed."""
    from refmatrix.ingest import ingest_path
    _r4(old_store)
    s = _open(old_store["root"])
    try:
        ingest_path(s, old_store["proj"])
    finally:
        s.close()
    got = _bound(old_store["root"])
    assert all(v > 0 for v in got.values()), f"citers did not bind after `rmx ingest .`: {got}"


# ================================================================ S2


def _pending(con, *, by_name: bool = True) -> Counter:
    return Counter(tuple(r) for r in con.execute(
        "SELECT p.name, s.kind, s.name, pr.linkage, pr.target_name, pr.file, pr.line "
        "FROM pending_refs pr JOIN entities s ON s.id = pr.source_id "
        "JOIN partitions p ON p.id = pr.partition_id").fetchall())


def _orphans(con) -> int:
    return int(con.execute(
        "SELECT count(*) FROM pending_refs pr WHERE NOT EXISTS "
        "(SELECT 1 FROM entities e WHERE e.id = pr.source_id) OR NOT EXISTS "
        "(SELECT 1 FROM partitions p WHERE p.id = pr.partition_id)").fetchone()[0])


def _citer(doc_id: str, target: str) -> str:
    return _gmd(doc_id, f"Intro.\n\n## Cite {{#cite}}\n\nText.\n\nrel: depends-on -> [[{target}]]\n")


@pytest.fixture
def slots(base):
    """Slot A and slot B diverged from one base: each gained a different citer AFTER the copy,
    so their new entities collide on id and B's are remapped by the merge."""
    proj = base / "proj"
    a_root, b_root = base / "A" / "proj" / ".refmatrix", base / "B" / "proj" / ".refmatrix"
    _new_store(a_root)
    s = _open(a_root)
    try:
        ingest_gmd_paths(s, [_write(proj, "docs/base.md", _citer("base-doc", "missing-1"))])
    finally:
        s.close()
    b_root.mkdir(parents=True)
    shutil.copy2(a_root / "catalog.duckdb", b_root / "catalog.duckdb")
    for root, doc, tgt in ((a_root, "a-only", "missing-a"), (b_root, "b-only", "missing-b")):
        s = _open(root)
        try:
            ingest_gmd_paths(s, [_write(proj, f"docs/{doc}.md", _citer(doc, tgt))])
        finally:
            s.close()
    return {"a": a_root / "catalog.duckdb", "b": b_root / "catalog.duckdb",
            "target": base / "T" / "catalog.duckdb"}


def test_s2_a_slot_merge_keeps_every_pending_row_with_its_source(slots):
    import duckdb

    from refmatrix.replica_merge import merge_slots
    want = Counter()
    for k in ("a", "b"):
        con = duckdb.connect(str(slots[k]), read_only=True)
        try:
            want |= _pending(con)
        finally:
            con.close()
    assert {r[4] for r in want} == {"missing-1", "missing-a", "missing-b"}, want
    slots["target"].parent.mkdir()
    res = merge_slots(slots["a"], slots["b"], slots["target"])
    assert res["merged_counts"].get("pending_refs") == 3, res["merged_counts"]
    con = duckdb.connect(str(slots["target"]), read_only=True)
    try:
        got = _pending(con)
        orphans = _orphans(con)
    finally:
        con.close()
    assert got == want, f"merged pending rows by name: missing {dict(want - got)}, extra {dict(got - want)}"
    assert orphans == 0, "a merged pending row points at no entity (B's source_id not remapped)"


def test_s2_both_slot_audits_count_pending_refs(slots):
    """The other two `replica_merge` table lists: `audit_slots` and `audit_via_writer`."""
    import duckdb

    from refmatrix.replica_merge import audit_slots, audit_via_writer
    a = audit_slots(slots["a"], slots["b"])
    assert "pending_refs" in a["a_counts"] and "pending_refs" in a["b_counts"], a["a_counts"]
    con = duckdb.connect(str(slots["a"]))
    try:
        w = audit_via_writer(con, "A", slots["b"], "B")
    finally:
        con.close()
    assert "pending_refs" in w["a_counts"], w["a_counts"]


def _pending_in(s: Store, part: str) -> Counter:
    return Counter((r[0], r[1], r[2]) for r in s._connect().execute(
        "SELECT s.name, pr.linkage, pr.target_name FROM pending_refs pr "
        "JOIN entities s ON s.id = pr.source_id JOIN partitions p ON p.id = pr.partition_id "
        "WHERE p.name = ?", (part,)).fetchall())


def test_s2_merge_partition_repoints_pending_rows_and_drops_dead_ones_counted(base):
    proj = base / "proj"
    root = proj / ".refmatrix"
    _new_store(root)
    shared = _write(proj, "docs/shared.md", _citer("shared", "missing-s"))
    s = _open(root)
    try:
        with s.with_partition("src"):
            ingest_gmd_paths(s, [shared, _write(proj, "docs/src-only.md",
                                                _citer("src-only", "missing-x"))])
            src_pid = s._partition_id
        with s.with_partition("dst"):
            ingest_gmd_paths(s, [shared])            # collides with src's `shared` entities
        con = s._connect()
        con.execute(
            "INSERT INTO pending_refs(partition_id, source_id, linkage, target_name, ref, file, "
            "line, weight, detail, created_at) VALUES (?, 987654321, 'depends-on', 'missing-z', "
            "'missing-z', ?, 9, NULL, 'rel: depends-on -> missing-z', 0)",
            (src_pid, str(proj / "docs" / "gone.md")))
        s._maybe_commit(con)
        res = s.merge_partition("src", "dst")
        got = _pending_in(s, "dst")
        orphans = _orphans(s._connect())
    finally:
        s.close()
    assert got == Counter({("shared#cite", "depends-on", "missing-s"): 1,
                           ("src-only#cite", "depends-on", "missing-x"): 1}), (
        f"dst pending rows after the merge (repointed, deduped on the collided source): {got}")
    assert orphans == 0, "a pending row kept a dead partition or a dead source after the merge"
    assert res.get("pending_refs_dropped") == 1, f"the dead-source row is not counted: {res}"


# ================================================================ M1 / M2


@pytest.fixture
def walk(base):
    """A's `#cite` -derives-from-> path-less concept `b-doc` -denotes-> B's doc (the misbound
    row); and X MENTIONS that concept as a plain term (concept side = the term, entity = X)."""
    proj = base / "proj"
    root = proj / ".refmatrix"
    _new_store(root)
    a = _write(proj, "docs/a.md", _gmd("a", "Intro.\n\n## Cite {#cite}\n\nText.\n"))
    b = _write(proj, "docs/b.md", _gmd("b-doc", "The target.\n"))
    x = _write(proj, "docs/x.md", _gmd("x-doc", "Unrelated prose.\n"))
    s = _open(root)
    try:
        ingest_gmd_paths(s, [a, b, x])
        c = s.upsert_entity(kind="concept", name="b-doc")
        cite = s.get_entity("concept", "a#cite").id
        x_doc = s.get_entity("doc", "x-doc").id
        b_doc = s.get_entity("doc", "b-doc").id
        _link_any(s, "derives-from", cite, c)
        _link_any(s, "mentions", c, x_doc)
        _link_any(s, "denotes", c, b_doc)
        return {"root": root, "c": c, "cite": cite, "x": x_doc, "b": b_doc}
    finally:
        s.close()


def _context_ids(w) -> "dict[int, set[str]]":
    """build_context anchored on B's DOC entity: entity id -> the linkages it arrived by."""
    from refmatrix.context import build_context
    s = _open(w["root"])
    try:
        # `doc:` names the doc: a bare `b-doc` resolves to the path-less concept first.
        b = build_context(s, "doc:b-doc", max_entities=200, max_tokens=200_000,
                          grep_backstop=False)
        assert b.anchor is not None and b.anchor.id == w["b"], (
            f"precondition: the bundle must anchor on B's doc, got {b.anchor}")
        out: "dict[int, set[str]]" = {}
        for entries in b.groups.values():
            for en in entries:
                out.setdefault(en.entity.id, set()).add(en.linkage)
        return out
    finally:
        s.close()


def test_m1_build_context_crosses_denotes_for_typed_edges(walk):
    """R9 / M1a: B's context lists A's `#cite` — reached only through the concept that
    denotes B, by its typed `derives-from` in-edge."""
    got = _context_ids(walk)
    assert walk["cite"] in got, f"the typed edge through `denotes` is missing: {got}"


def test_m2_build_context_mention_chain_does_not_cross_denotes(walk):
    """L81 M2: a doc that merely MENTIONS the term concept is not B's neighbour (PageRank folds
    typed edges only; until G30 decides the fold, build_context does the same)."""
    got = _context_ids(walk)
    assert walk["x"] not in got, (
        f"a plain `mentions` of the denoting concept reached B's context via {got.get(walk['x'])}")


def test_m2_neighbors_of_the_concept_lists_its_raw_denotes_link(walk):
    """L81 M2: `neighbors` keeps listing raw `denotes` links — `rmx neighbors <concept>` names
    the doc the concept denotes. At df092ac `QueryEngine.neighbors` drops `denotes` from its
    linkage list (it only folds the hop through equivalents of the NEXT frontier), so a concept's
    own denotes target is never listed."""
    from refmatrix.graphread import neighbors_payload
    s = _open(walk["root"])
    try:
        out = neighbors_payload(s, "b-doc", depth=1)
    finally:
        s.close()
    assert walk["b"] in {e["id"] for e in out["entities"]}, out


def test_m1_a_compaction_dump_keeps_pending_rows(base, monkeypatch):
    """M1b: `dump_catalog_to_log` (the facts.log compaction) emits the pending rows, so a
    rebuild of the compacted log keeps them."""
    monkeypatch.setenv("RMX_LOG", "1")
    proj = base / "proj"
    root = proj / ".refmatrix"
    _new_store(root)
    s = _open(root)
    try:
        ingest_gmd_paths(s, [_write(proj, "docs/a.md", _citer("a", "missing-m"))])
        want = _pending(s._connect())
        assert [r[4] for r in want] == ["missing-m"], want
        s.dump_catalog_to_log()
        log = s.log_path.read_bytes()
    finally:
        s.close()
    r2 = base / "r" / "proj" / ".refmatrix"
    _new_store(r2)
    s = _open(r2)
    try:
        s.log_path.write_bytes(log)
        s.rebuild_index_from_log()
        got = _pending(s._connect())
    finally:
        s.close()
    assert got == want, f"the compacted log lost pending rows: want {dict(want)}, got {dict(got)}"


def test_m1_a_pending_row_whose_source_is_gone_is_dropped_and_counted(base):
    """M1c: a pending row whose source was removed by a path that does not run `purge_entity`
    is deleted and counted when its target arrives — never linked from a dead id."""
    proj = base / "proj"
    root = proj / ".refmatrix"
    _new_store(root)
    s = _open(root)
    try:
        con = s._connect()
        con.execute(
            "INSERT INTO pending_refs(partition_id, source_id, linkage, target_name, ref, file, "
            "line, weight, detail, created_at) VALUES (?, 987654321, 'depends-on', 'late-doc', "
            "'late-doc', ?, 9, NULL, 'rel: depends-on -> late-doc', 0)",
            (s._partition_id, str(proj / "docs" / "gone.md")))
        s._maybe_commit(con)
        try:
            st = ingest_gmd_paths(s, [_write(proj, "docs/late.md", _gmd("late-doc"))])
        except Exception as e:          # noqa: BLE001 — a crash is a failure, said plainly
            pytest.fail(f"resolving a dead-source pending row raised {type(e).__name__}: {e}")
        con = s._connect()
        left = con.execute("SELECT count(*) FROM pending_refs").fetchone()[0]
        dead = con.execute("SELECT count(*) FROM entity_links WHERE concept_id = 987654321 "
                           "OR entity_id = 987654321").fetchone()[0]
    finally:
        s.close()
    assert (left, dead) == (0, 0), f"pending rows left {left}, links from the dead id {dead}"
    assert st.pending_dropped == 1, st.report()


# ================================================================ M3


def test_m3_the_watcher_purges_a_deleted_builtin_included_profile(base, monkeypatch):
    """No ignore file: the GMD profile is in by the R11 built-in include. Delete it: the
    watcher's delete event must reach `_sync_one`, which purges the doc. At df092ac the include
    sniffs the (gone) file, the hidden-dir rule wins, and the event is dropped."""
    import watchdog.observers as wo
    from watchdog.events import FileDeletedEvent

    from refmatrix.sync import sync_files
    from tests.test_bug216_rule_docs_e2e import _FakeObserver
    proj = base / "proj"
    root = proj / ".refmatrix"
    _new_store(root)
    prof = _write(proj, ".claude/PROJECT_PROFILE.md", PROFILE_MD)
    s = _open(root)
    try:
        sync_files(s, [str(prof)], project_root=proj)
        assert s.get_entity("doc", "project-profile") is not None, "precondition: profile in"
    finally:
        s.close()
    prof.unlink()
    _FakeObserver.instances = []
    monkeypatch.setattr(wo, "Observer", _FakeObserver)
    d = daemon_mod.Daemon(root, watch_root=proj, watch_debounce_ms=50)
    d.store = _open(root)
    try:
        d._start_watcher()
        (handler, _p), = _FakeObserver.instances[0].handlers
        handler.on_deleted(FileDeletedEvent(str(prof)))
        d._watch_stop.set()
        d._watch_thread.join(timeout=30)
        assert not d._watch_thread.is_alive()
        assert d.sync_errors() == [], d.sync_errors()
    finally:
        d.store.close()
    s = _open(root)
    try:
        left = s.get_entity("doc", "project-profile")
        node = s.get_entity("concept", "project-profile#constraints")
    finally:
        s.close()
    assert left is None and node is None, "the deleted profile's doc / node survived the watcher"


def test_m3_guard_a_sync_of_the_deleted_profile_purges_it(base):
    """GUARD: `sync_files` naming the deleted path purges it already (ignored -> purge)."""
    from refmatrix.sync import sync_files
    proj = base / "proj"
    root = proj / ".refmatrix"
    _new_store(root)
    prof = _write(proj, ".claude/PROJECT_PROFILE.md", PROFILE_MD)
    s = _open(root)
    try:
        sync_files(s, [str(prof)], project_root=proj)
        prof.unlink()
        sync_files(s, [str(prof)], project_root=proj)
        assert s.get_entity("doc", "project-profile") is None
    finally:
        s.close()
