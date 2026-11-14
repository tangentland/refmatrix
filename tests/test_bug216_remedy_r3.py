"""bug-216 remedy r3 RED — bsd-216 r3 at bff34c1 (DIRTY 0B/1S/3M), ruling L97.

Report: workflow/bullshit/2026-11-14-0210-bug216-r3-bff34c1.md (f75b1c5 in the bug-216 clone).
Ruling: workflow/plan-review-2026-11-13.md row L97 (dev master).

  S1  a fragment row BOTH slots hold (`mentions` included) keeps only A's bits at bff34c1: step
      12 copies A's rows, then B's rows only for (partition, linkage) pairs A lacks. B's moved
      entity (fresh id) is in `entities` and `entity_links` but in no bitmap. The bsd probe's
      shape: both slots add a doc mentioning one term; after the merge the term's `mentions`
      bitmap must equal its `entity_links` set (adoc, bdoc at its FRESH id, d0); A's bits are
      unchanged; no B bit stays at the old id of a moved entity.
  M1  after a (non-dry-run) merge with fresh moves, the Lance rows of BOTH ids of every move are
      gone, so a dense read misses rather than returning A's entity for B's text until the
      re-embed; other rows stay. The delete is ONE batched call per (partition, kind) table,
      never one per entity (bug-085) — counted through a pass-through spy on the Lance
      library's `LanceDataset.delete` (external; the function under test is the merge op).
  M2  the `vectors_updated_at = NULL` re-queue is pinned: both ids of each move are in
      `pending_embeddings` on the merged target, while an unmoved, embedded entity is not. The
      fixture marks every entity embedded first (at bff34c1 `add_memory` leaves it NULL, which
      is why bsd's removal mutation survived with 92 passed).

Throwaway stores under short `/tmp` mkdtemp roots only; no live `.refmatrix/` is touched.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import duckdb
import numpy as np
import pytest

from refmatrix.ingest_gmd import ingest_gmd_paths
from refmatrix.store import Store
from tests.test_bug216_remedy_r1 import _gmd, _new_store, _open, _write

TERM = "zebrafinch"


@pytest.fixture
def base():
    b = Path(tempfile.mkdtemp(prefix="b216s", dir="/tmp")).resolve()
    yield b
    shutil.rmtree(b)


def _diverged(base: Path) -> "tuple[Path, Path]":
    """(A_root, B_root): stores at `<X>/proj/.refmatrix` (partition `proj`), B a file copy of A."""
    a_root = base / "A" / "proj" / ".refmatrix"
    b_root = base / "B" / "proj" / ".refmatrix"
    _new_store(a_root)
    return a_root, b_root


def _copy_slot(a_root: Path, b_root: Path) -> None:
    b_root.mkdir(parents=True)
    shutil.copy2(a_root / "catalog.duckdb", b_root / "catalog.duckdb")


def _merge(a_root: Path, b_root: Path, target: Path) -> dict:
    from refmatrix.replica_merge import merge_slots
    target.parent.mkdir(parents=True, exist_ok=True)
    return merge_slots(a_root / "catalog.duckdb", b_root / "catalog.duckdb", target)


def _store_on(target: Path, base: Path, name: str) -> Store:
    """A Store over a COPY of a merged catalog (read-only use)."""
    root = base / name / "proj" / ".refmatrix"
    root.mkdir(parents=True)
    shutil.copy2(target, root / "catalog.duckdb")
    s = Store(root)
    s.init()
    return s


# ================================================================ S1


def _term_slots(base: Path) -> dict:
    """bsd's probe: a base doc d0 mentions the term; after the copy, A adds `adoc` and B adds
    `bdoc`, each mentioning it, so the new entities collide on id and B's are moved. Both slots
    hold the `(proj, mentions)` fragment row."""
    a_root, b_root = _diverged(base)
    src = base / "docs"
    d0 = _write(src, "d0.md", _gmd("d0", f"The {TERM} sings.\n"))
    s = _open(a_root)
    try:
        ingest_gmd_paths(s, [d0])
        s.flush_fragments()
    finally:
        s.close()
    _copy_slot(a_root, b_root)
    for root, doc in ((a_root, "adoc"), (b_root, "bdoc")):
        p = _write(src, f"{doc}.md", _gmd(doc, f"Another {TERM} here.\n"))
        s = _open(root)
        try:
            ingest_gmd_paths(s, [p])
            s.flush_fragments()
        finally:
            s.close()
    return {"a": a_root, "b": b_root}


def _term_state(s: Store) -> dict:
    """The term concept's `mentions` bitmap and its `entity_links` set, by entity id."""
    e = s.get_entity("concept", TERM)
    assert e is not None, f"no `{TERM}` concept"
    lid = s.get_linkage_id("mentions")
    links = {int(r[0]) for r in s._connect().execute(
        "SELECT entity_id FROM entity_links WHERE linkage_id=? AND concept_id=?",
        (lid, e.id)).fetchall()}
    with s.with_partition("proj"):
        bm = {int(x) for x in s.load_bitmap("mentions", e.id)}
    names = {int(i): str(n) for i, n in s._connect().execute(
        "SELECT id, name FROM entities").fetchall()}
    return {"links": links, "bits": bm, "names": names}


def test_s1_a_shared_fragment_row_keeps_b_bits_on_their_remapped_ids(base):
    sl = _term_slots(base)
    sa = _open(sl["a"])
    try:
        a_before = _term_state(sa)
    finally:
        sa.close()
    res = _merge(sl["a"], sl["b"], base / "T" / "catalog.duckdb")
    moved = {int(o): int(n) for o, n in (res.get("fresh_moved") or [])}
    assert moved, f"precondition: the fixture must produce fresh moves: {res.get('remap')}"
    s = _store_on(base / "T" / "catalog.duckdb", base, "probe")
    try:
        st = _term_state(s)
    finally:
        s.close()
    nm = lambda ids: sorted(st["names"].get(i, f"<{i}>") for i in ids)  # noqa: E731
    assert {"adoc#root", "bdoc#root", "d0#root"} <= set(nm(st["links"])), nm(st["links"])
    assert st["bits"] == st["links"], (
        f"`mentions`[{TERM}] bitmap {nm(st['bits'])} != its entity_links {nm(st['links'])} — "
        f"B's bits in a row A also holds were dropped")
    assert a_before["bits"] <= st["bits"], "A's own bits changed in the merged row"
    bdoc_root = next(i for i, n in st["names"].items() if n == "bdoc#root")
    assert bdoc_root in moved.values() and bdoc_root in st["bits"], (
        f"bdoc#root (id {bdoc_root}) must be in the bitmap at its fresh id; moved={moved}")


# ================================================================ M1 / M2


def _memory_slots(base: Path, n_moves: int = 2) -> dict:
    """Both slots diverge from one copy that already holds an embedded memory (`keep`), then
    each writes `n_moves` new memories: same ids, different names, so B's are moved. Every
    entity is marked embedded in its slot (the state a live store is in after `rmx embed`)."""
    a_root, b_root = _diverged(base)
    s = _open(a_root)
    try:
        keep = s.add_memory("keep", "an unmoved, embedded memory")
    finally:
        s.close()
    _copy_slot(a_root, b_root)
    ids = {}
    for root, side in ((a_root, "a"), (b_root, "b")):
        s = _open(root)
        try:
            ids[side] = [s.add_memory(f"mem-{side}{k}", f"body {side}{k}")
                         for k in range(n_moves)]
            con = s._connect()
            con.execute("UPDATE entities SET vectors_updated_at = updated_at + 1, "
                        "vectors_partition = 'proj'")
            s._maybe_commit(con)
        finally:
            s.close()
    assert ids["a"] == ids["b"], f"precondition: colliding ids {ids}"
    return {"a": a_root, "b": b_root, "ids": ids["a"], "keep": keep}


def test_m2_both_ids_of_every_move_are_requeued_for_embedding(base):
    m = _memory_slots(base)
    res = _merge(m["a"], m["b"], base / "T" / "catalog.duckdb")
    moved = [(int(o), int(n)) for o, n in (res.get("fresh_moved") or [])]
    assert sorted(o for o, _n in moved) == sorted(m["ids"]), f"precondition: {moved}"
    s = _store_on(base / "T" / "catalog.duckdb", base, "probe")
    try:
        with s.with_partition("proj"):
            pending = {int(r[0]) for r in s.pending_embeddings()}
    finally:
        s.close()
    want = {i for pair in moved for i in pair}
    assert want <= pending, (
        f"moved ids not re-queued for embedding: missing {sorted(want - pending)}")
    assert m["keep"] not in pending, "an unmoved, embedded entity was re-queued"


DIM = 4


def _op_daemon(base: Path, m: dict):
    from refmatrix import daemon as dm
    droot = base / "D" / "proj" / ".refmatrix"
    droot.mkdir(parents=True)
    shutil.copy2(m["a"] / "catalog.duckdb", droot / "catalog.A.duckdb")
    shutil.copy2(m["b"] / "catalog.duckdb", droot / "catalog.B.duckdb")
    (droot / "active").write_text("A")
    d = dm.Daemon(droot, partition="proj")
    d._log = lambda msg: None
    d.store = Store(droot, partition="proj")
    d.store.init()
    d.store._connect()
    return d, droot


def test_m1_the_merge_deletes_the_vectors_of_both_ids_of_every_move_in_one_batch(base,
                                                                               monkeypatch):
    import lance

    from refmatrix import daemon as dm
    from refmatrix.vectors import LanceVectorStore
    m = _memory_slots(base, n_moves=2)
    d, droot = _op_daemon(base, m)
    fresh_guess = list(range(max(m["ids"]) + 1, max(m["ids"]) + 1 + len(m["ids"])))
    seeded = sorted(set(m["ids"]) | {m["keep"]} | set(fresh_guess))
    vs = LanceVectorStore(droot / "vectors", partition="proj", dim=DIM)
    vs.upsert_vectors(seeded, np.ones((len(seeded), DIM), dtype="float32"), kind="memory")
    calls: list = []
    real = lance.LanceDataset.delete

    def counting(self, *a, **k):                       # pass-through spy on the library
        calls.append((str(getattr(self, "uri", "")), a, k))
        return real(self, *a, **k)
    monkeypatch.setattr(lance.LanceDataset, "delete", counting)
    try:
        r = dm._op_replica_merge(d, {"dry_run": False})
    finally:
        if d.store is not None:
            d.store.close()
    assert r.get("ok") is True, r
    moved = [(int(o), int(n)) for o, n in (r.get("fresh_moved") or [])]
    assert sorted(o for o, _n in moved) == sorted(m["ids"]), f"precondition: {moved}"
    both = sorted({i for pair in moved for i in pair})
    got_ids, _mat = LanceVectorStore(droot / "vectors", partition="proj", dim=0).read_vectors(
        kind="memory", ids=both)
    assert got_ids == [], (
        f"Lance rows of moved ids survive the merge: {sorted(got_ids)} (a dense read returns "
        f"A's entity for B's text until the re-embed)")
    kept, _ = LanceVectorStore(droot / "vectors", partition="proj", dim=0).read_vectors(
        kind="memory", ids=[m["keep"]])
    assert kept == [m["keep"]], "the merge deleted an unmoved entity's vector"
    memory_deletes = [c for c in calls if "memory.lance" in c[0]]
    assert len(memory_deletes) == 1, (
        f"{len(memory_deletes)} Lance delete call(s) on the (proj, memory) table for "
        f"{len(both)} ids: the delete must be ONE batched call per (partition, kind) table "
        f"(bug-085)")
