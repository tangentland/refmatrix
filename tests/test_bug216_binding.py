"""bug-216 rev 2/3 — AC-7 (R6), AC-8 rev 3 (R7 `denotes`) and AC-10 (R9).

Spec: workflow/plans/task-bug216-rule-docs-in-graph.md (#rev-2, #r6, #ac-7, #rev-3,
#r7-denotes, #ac-8-rev3, #r9, #ac-10).

WHY (bsd-215m1, 2026-11-13). Of 5,431 `rel:` evidence rows in refmatrix, 3,662 land on a target
with NO path; at least 1,909 cite a doc that IS ingested under exactly that id. A bare doc-id link
`[[b-doc]]` binds a same-named PATH-LESS concept, because `ingest_gmd._resolve_target_eid` asks
`get_entity` for `concept`, then `doc`, then `memory`. The concept is minted the way production
mints it: a plain `[[b-doc]]` wikilink mention resolves and then calls `store.add_concept`, which
also writes the `b_doc` / `b doc` variants joined by `same_as`. The concept may appear AFTER the
doc and still win — the lookup is concept-first, not first-come.

Within ONE batch, pass 1 registers `eid_by_name[doc_id] = doc_eid`, so a target in the same
batch binds the doc already at HEAD: that case is a GUARD here, not a RED (bsd-215m1 precision 1).

Direction, as everywhere in this store: `rel: X verb -> Y` is `store.link(verb, X, Y)` =
`entity_links(entity_id = Y, concept_id = X)`. `denotes` (concept C -> doc D) is read the same
way: `concept_id = C, entity_id = D`.

Every store is a throwaway under a short `/tmp` mkdtemp root.
"""
from __future__ import annotations

import rmx_sandbox  # task-29.4 #r5: test roots live under the sandbox root (short_root)
import os
import shutil
import tempfile
from pathlib import Path

import pytest

from refmatrix.ingest_gmd import ingest_gmd_paths
from refmatrix.store import Store

# The one-time derive op of R7(a), looked up in the daemon's op registry. The spec names it
# only as "a one-time derive op, run through the daemon (`_op_*`)"; this is the name these
# tests assume (after `coref_link` / `memory_link` / `subject_link`).
DENOTES_OP = "denotes_link"


def _gmd(doc_id: str, body: str = "Body.\n") -> str:
    # The title is NOT the id: the ingester mints title-term concepts, so a title equal to a
    # hyphenated id would itself create the same-named concept and hide which producer did.
    return (f'---\ngmd: "0.1"\nid: {doc_id}\ntitle: "Fixture document"\ntags: [t]\n---\n\n'
            f"# Fixture document {{#root}}\n\n{body}")


B_MD = _gmd("b-doc", "Target body.\n\n## Sec {#sec}\n\nSection text.\n")
# The production producer of the same-named concept: a plain mention.
M_MD = _gmd("mention-doc", "See [[b-doc]] for context.\n")
A_MD = _gmd("a", "Intro.\n\n## Cite {#cite}\n\nCitation section.\n\n"
                 "rel: derives-from -> [[b-doc]]\n"
                 "rel: depends-on -> [[b-doc#sec]]\n")


@pytest.fixture
def env():
    base = Path(rmx_sandbox.short_root("b216b")).resolve()
    proj = base / "proj"
    (proj / "docs").mkdir(parents=True)
    root = proj / ".refmatrix"
    root.mkdir()
    s = Store(root)
    s.init()
    s.close()
    yield proj, root
    shutil.rmtree(base)


def _write(proj: Path, rel: str, body: str) -> Path:
    p = proj / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)
    return p


def _ingest(root: Path, paths: list[Path], **kw):
    s = Store(root)
    s.init()
    try:
        return ingest_gmd_paths(s, paths, **kw)
    finally:
        s.close()


def _open(root: Path) -> Store:
    s = Store(root)
    s.init()
    return s


def _lid(s: Store, verb: str) -> int | None:
    r = s._connect().execute("SELECT id FROM linkage_types WHERE name=?", (verb,)).fetchone()
    return None if r is None else r[0]


def _targets(s: Store, verb: str, src_id: int) -> list[tuple[str, str, str | None]]:
    """(kind, name, path) of every entity `src_id` reaches by `verb`, store direction."""
    lid = _lid(s, verb)
    if lid is None:
        return []
    rows = s._connect().execute(
        "SELECT e.kind, e.name, e.path FROM entity_links el JOIN entities e ON e.id=el.entity_id "
        "WHERE el.linkage_id=? AND el.concept_id=? ORDER BY e.kind, e.name",
        (lid, src_id)).fetchall()
    return [(k, n, (str(Path(p).resolve()) if p else None)) for k, n, p in rows]


def _link(s: Store, verb: str, concept_id: int, entity_id: int) -> None:
    """`store.link` for a verb the fixture writes by hand (registered first, as the GMD
    ingester's `_ensure_linkage` does)."""
    try:
        s.get_linkage_id(verb)
    except KeyError:
        s.add_linkage_type(verb, directed=True, description=f"bug-216 fixture '{verb}'")
    s.link(verb, concept_id, entity_id)


def _src(s: Store, name: str) -> int:
    e = s.get_entity("concept", name)
    assert e is not None, f"no `{name}` node"
    return e.id


def _assert_binds_doc(root: Path, b: Path, *, src: str = "a#cite") -> None:
    s = _open(root)
    try:
        got = _targets(s, "derives-from", _src(s, src))
    finally:
        s.close()
    assert got == [("doc", "b-doc", str(b.resolve()))], (
        f"bare [[b-doc]] must bind B's doc entity, never a path-less concept; got {got}")


def _assert_concept_exists(root: Path, name: str = "b-doc") -> None:
    s = _open(root)
    try:
        e = s.get_entity("concept", name)
    finally:
        s.close()
    assert e is not None and not e.path, (
        f"precondition: the production mention must mint a path-less `{name}` concept")


# ---------------------------------------------------------------- AC-7 (R6)


def test_ac7_target_ingested_earlier_concept_minted_after_binds_the_doc(env):
    """B ingested; then a plain mention mints the `b-doc` concept; then A. HEAD binds the
    concept: it was created after the doc, and the lookup is concept-first."""
    proj, root = env
    b = _write(proj, "docs/b.md", B_MD)
    _ingest(root, [b])
    s = _open(root)
    try:
        assert s.get_entity("concept", "b-doc") is None, (
            "precondition: ingesting B alone mints no `b-doc` concept (the mention must)")
    finally:
        s.close()
    _ingest(root, [_write(proj, "docs/m.md", M_MD)])
    _assert_concept_exists(root)
    _ingest(root, [_write(proj, "docs/a.md", A_MD)])
    _assert_binds_doc(root, b)


def test_ac7_citing_doc_ingested_first_then_resynced_binds_the_doc(env):
    """A first (its link is unresolved), then B, then the mention; A is edited and re-synced
    file by file — the watcher's per-file `sync_files` route."""
    from refmatrix.sync import sync_files
    proj, root = env
    a = _write(proj, "docs/a.md", A_MD)
    b = _write(proj, "docs/b.md", B_MD)
    m = _write(proj, "docs/m.md", M_MD)
    for p in (a, b, m):
        s = _open(root)
        try:
            sync_files(s, [str(p)], project_root=proj)
        finally:
            s.close()
    _assert_concept_exists(root)
    a.write_text(A_MD + "\nEdited.\n")
    t = os.stat(a).st_mtime + 10
    os.utime(a, (t, t))
    s = _open(root)
    try:
        sync_files(s, [str(a)], project_root=proj)
    finally:
        s.close()
    _assert_binds_doc(root, b)


def test_ac7_guard_one_batch_with_an_unchanged_target_binds_the_doc(env):
    """GUARD (green at HEAD): one batch [A, B] where B is UNCHANGED since an earlier ingest and
    the concept already exists (the whole-tree re-ingest shape). Pass 1 still registers B's
    doc id in the batch dict on the resume skip, so A binds the doc. Must keep passing."""
    proj, root = env
    b = _write(proj, "docs/b.md", B_MD)
    _ingest(root, [b, _write(proj, "docs/m.md", M_MD)])
    _assert_concept_exists(root)
    _ingest(root, [_write(proj, "docs/a.md", A_MD), b])
    _assert_binds_doc(root, b)


@pytest.mark.parametrize("order", ["a-b-m", "m-a-b", "b-m-a"])
def test_ac7_guard_fresh_one_batch_binds_the_doc(env, order):
    """GUARD (green at HEAD): every file new in one batch — pass 1 puts `b-doc -> doc` in the
    batch dict before any link resolves. Must keep passing."""
    proj, root = env
    files = {"a": _write(proj, "docs/a.md", A_MD), "b": _write(proj, "docs/b.md", B_MD),
             "m": _write(proj, "docs/m.md", M_MD)}
    _ingest(root, [files[k] for k in order.split("-")])
    _assert_binds_doc(root, files["b"])


def test_ac7_two_citing_docs_in_one_batch_both_bind_the_doc(env):
    """The batch dict must not hand a later citation a concept id under the bare name: B and
    the concept pre-exist, then ONE batch holds two citing docs (each also carrying the plain
    mention that calls `add_concept`). Kills 'let the batch dict cache the concept'."""
    proj, root = env
    b = _write(proj, "docs/b.md", B_MD)
    _ingest(root, [b, _write(proj, "docs/m.md", M_MD)])
    a1 = _write(proj, "docs/a1.md", A_MD.replace("id: a\n", "id: a1\n").replace(
        "Intro.", "Intro, see [[b-doc]]."))
    a2 = _write(proj, "docs/a2.md", A_MD.replace("id: a\n", "id: a2\n"))
    _ingest(root, [a1, a2])
    _assert_binds_doc(root, b, src="a1#cite")
    _assert_binds_doc(root, b, src="a2#cite")


def test_ac7_guard_anchored_target_binds_the_section_node(env):
    """GUARD: `[[b-doc#sec]]` keeps concept-first — it is B's `sec` node (kind concept, with
    B's path), in the order where the bare link misbinds at HEAD."""
    proj, root = env
    b = _write(proj, "docs/b.md", B_MD)
    _ingest(root, [b])
    _ingest(root, [_write(proj, "docs/m.md", M_MD)])
    _ingest(root, [_write(proj, "docs/a.md", A_MD)])
    s = _open(root)
    try:
        got = _targets(s, "depends-on", _src(s, "a#cite"))
    finally:
        s.close()
    assert got == [("concept", "b-doc#sec", str(b.resolve()))], got


def test_ac7_memory_target_binds_the_memory(env):
    """A memory (`--as-memory`, kind `memory`) cited by bare id binds the memory row, not the
    concept a plain mention of it minted."""
    proj, root = env
    mem = _write(proj, "mem/b-mem.md", _gmd("b-mem", "A memory.\n"))
    _ingest(root, [mem], as_memory=True)
    _ingest(root, [_write(proj, "docs/m.md", _gmd("mention-doc", "See [[b-mem]].\n"))])
    _assert_concept_exists(root, "b-mem")
    _ingest(root, [_write(proj, "docs/a.md", _gmd(
        "a", "Intro.\n\n## Cite {#cite}\n\nText.\n\nrel: derives-from -> [[b-mem]]\n"))])
    s = _open(root)
    try:
        got = _targets(s, "derives-from", _src(s, "a#cite"))
    finally:
        s.close()
    assert [(k, n) for k, n, _p in got] == [("memory", "b-mem")], got


# ---------------------------------------------------------------- AC-8 rev 3 (R7 denotes)


def _misbound_store(proj: Path, root: Path) -> dict:
    """The state HEAD wrote, built explicitly (the fixed ingester no longer produces it): A and B
    ingested, a `b-doc` concept minted by `add_concept` (with its `b_doc` / `b doc` variants and
    `same_as`), and A's `derives-from` row + evidence pointing at that path-less concept."""
    a = _write(proj, "docs/a.md", _gmd("a", "Intro.\n\n## Cite {#cite}\n\nText.\n"))
    b = _write(proj, "docs/b.md", B_MD)
    _ingest(root, [a, b])
    s = _open(root)
    try:
        cid = s.add_concept("b-doc")
        names = {"b-doc", "b_doc", "b doc"}
        ids = {}
        for n in names:
            e = s.get_entity("concept", n)
            assert e is not None, f"add_concept did not mint the `{n}` variant"
            ids[n] = e.id
        exact = ids["b-doc"]
        src = _src(s, "a#cite")
        _link(s, "derives-from", src, exact)
        s.add_evidence("derives-from", src, exact, file=str(a), line=12,
                       detail="rel: derives-from -> b-doc")
        doc = s.get_entity("doc", "b-doc")
        assert doc is not None
        return {"a": a, "b": b, "concepts": ids, "exact": exact, "canonical": cid,
                "src": src, "doc": doc.id}
    finally:
        s.close()


def _denotes_rows(s: Store, concept_ids) -> set[tuple[int, int]]:
    lid = _lid(s, "denotes")
    if lid is None:
        return set()
    ph = ",".join("?" * len(concept_ids))
    return {(int(c), int(e)) for c, e in s._connect().execute(
        f"SELECT concept_id, entity_id FROM entity_links WHERE linkage_id=? "
        f"AND concept_id IN ({ph})", (lid, *concept_ids)).fetchall()}


def _run_op(root: Path) -> dict:
    from refmatrix import daemon as dm
    op = dm.OPS.get(DENOTES_OP) if isinstance(getattr(dm, "OPS", None), dict) else None
    assert op is not None, f"no `{DENOTES_OP}` op in the daemon's OPS registry (spec #r7-denotes)"
    d = dm.Daemon(root)
    d.store = _open(root)
    try:
        res = op(d, {})
    finally:
        d.store.close()
    return res


def test_ac8_derive_op_links_the_misbound_concept_and_its_variants_to_the_doc(env):
    proj, root = env
    st = _misbound_store(proj, root)
    cids = list(st["concepts"].values())
    s = _open(root)
    try:
        before = _denotes_rows(s, cids)
        evid_before = s._connect().execute(
            "SELECT count(*) FROM linkage_evidence").fetchone()[0]
    finally:
        s.close()
    res = _run_op(root)
    s = _open(root)
    try:
        after = _denotes_rows(s, cids)
        # every variant of the concept denotes B's doc — "skip the variants" mutation
        assert after == {(c, st["doc"]) for c in cids}, after
        # not via same_as — "link via same_as" mutation
        sa = _lid(s, "same_as")
        stray = s._connect().execute(
            f"SELECT count(*) FROM entity_links WHERE linkage_id=? AND entity_id=? "
            f"AND concept_id IN ({','.join('?' * len(cids))})",
            (sa, st["doc"], *cids)).fetchone()[0]
        assert stray == 0, "the concept was linked to the doc by same_as"
        # the original misbound row and its evidence are untouched
        assert _targets(s, "derives-from", st["src"]) == [("concept", "b-doc", None)]
        assert s._connect().execute(
            "SELECT count(*) FROM linkage_evidence").fetchone()[0] == evid_before
    finally:
        s.close()
    added = len(after - before)
    assert isinstance(res, dict) and res.get("added") == added, (
        f"the op must count what it added (spec: counted and printed); got {res}")


def test_ac8_a_second_run_adds_nothing(env):
    proj, root = env
    st = _misbound_store(proj, root)
    _run_op(root)
    s = _open(root)
    try:
        n1 = s._connect().execute("SELECT count(*) FROM entity_links").fetchone()[0]
    finally:
        s.close()
    res = _run_op(root)
    s = _open(root)
    try:
        n2 = s._connect().execute("SELECT count(*) FROM entity_links").fetchone()[0]
        assert _denotes_rows(s, list(st["concepts"].values())), "first run linked nothing"
    finally:
        s.close()
    assert n2 == n1 and res.get("added") == 0, (n1, n2, res)


def test_ac8_ingest_links_a_preexisting_concept_and_purge_removes_it(env):
    """R7(b): the concept exists first; ingesting the doc with that id links every concept
    named after it (variants too); purging the doc removes the links."""
    proj, root = env
    s = _open(root)
    try:
        s.add_concept("b-doc")
        cids = [s.get_entity("concept", n).id for n in ("b-doc", "b_doc", "b doc")]
    finally:
        s.close()
    b = _write(proj, "docs/b.md", B_MD)
    _ingest(root, [b])
    s = _open(root)
    try:
        doc = s.get_entity("doc", "b-doc").id
        assert _denotes_rows(s, cids) == {(c, doc) for c in cids}, _denotes_rows(s, cids)
        s.purge_path(str(b))
        assert s.get_entity("doc", "b-doc") is None, "precondition: the purge removed the doc"
        assert _denotes_rows(s, cids) == set(), "purging the doc left its denotes links"
    finally:
        s.close()


# ---------------------------------------------------------------- AC-10 (R9)

WALK_TERM = "xylophonist"


def _walk_store(proj: Path, root: Path) -> dict:
    """A's ONLY route to B: A's root node -derives-from-> path-less `b-doc` concept -denotes->
    B's doc. Both edges are written explicitly so the case does not depend on R6/R7's writers.
    The rel sits on A's root node, where the walk's lexical seed (the term) is."""
    a = _write(proj, "docs/a.md", _gmd("a", f"The {WALK_TERM} plays alone.\n"))
    b = _write(proj, "docs/b.md", _gmd("b-doc", "Unrelated target body.\n"))
    _ingest(root, [a, b])
    s = _open(root)
    try:
        c = s.upsert_entity(kind="concept", name="b-doc")
        a_root = _src(s, "a#root")
        a_doc = s.get_entity("doc", "a").id
        b_doc = s.get_entity("doc", "b-doc").id
        for src in (a_root, a_doc):          # the root-mirror ingest writes both
            _link(s, "derives-from", src, c)
        _link(s, "denotes", c, b_doc)
        return {"a_root": a_root, "a_doc": a_doc, "b_doc": b_doc, "c": c}
    finally:
        s.close()


def test_ac10_expansion_walk_reaches_b_at_one_hop(env, monkeypatch):
    proj, root = env
    st = _walk_store(proj, root)
    monkeypatch.setenv("RMX_EXPAND_HOPS", "1")
    s = _open(root)
    try:
        base = {e for e, _ in s.content_rank([WALK_TERM], limit=200)}
        assert st["c"] in base or st["a_root"] in base or st["a_doc"] in base, base
        assert st["b_doc"] in base, (
            "hops=1 from A must reach B through the path-less concept: `denotes` is a "
            "zero-cost hop")
        monkeypatch.setenv("RMX_EXPAND_HOPS", "0")
        lexical = {e for e, _ in s.content_rank([WALK_TERM], limit=200)}
        assert st["b_doc"] not in lexical, "precondition: B is not a lexical hit"
    finally:
        s.close()


def test_ac10_neighbors_of_a_lists_b(env):
    from refmatrix.graphread import neighbors_payload
    proj, root = env
    st = _walk_store(proj, root)
    s = _open(root)
    try:
        out = neighbors_payload(s, "a#root", depth=1)
    finally:
        s.close()
    ids = {e["id"] for e in out["entities"]}
    assert st["b_doc"] in ids, out


def test_ac10_pagerank_folds_the_in_edge_onto_b(env):
    from refmatrix.pagerank import build_adjacency
    proj, root = env
    st = _walk_store(proj, root)
    s = _open(root)
    try:
        adj = build_adjacency(s)
    finally:
        s.close()
    assert adj.get(st["a_root"], {}).get(st["b_doc"], 0) > 0, (
        "PageRank must fold the concept's typed in-edge onto its `denotes` target: no A-B edge "
        f"in {adj.get(st['a_root'])}")
