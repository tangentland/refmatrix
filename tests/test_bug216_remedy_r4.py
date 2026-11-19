"""bug-216 remedy r4 RED — bsd-216 r4 at dfbaa2d (DIRTY 1B/0S/2M, NO-GO), ruling L99.

Report: workflow/bullshit/2026-11-14-0333-bug216-r4-dfbaa2d.md (f1b1bc3 in the bug-216 clone).
Ruling: workflow/plan-review-2026-11-13.md row L99 (dev master).

  B1a  A's `shared` loses to B's NEWER `shared`, and B holds a different memory `b1` at A-shared's
       old id. A's fragment rows are copied as they are, so A-shared's bit stays on the old id —
       now `b1`'s. Asserted for EVERY (partition, linkage) fragment row: the decoded bits equal
       the `entity_links` pairs of that linkage.
  B1b  `remap_a` is not chained through the fresh-id move (bsd's 4 -> 3 -> 5): A's `shared` maps
       to B's `shared` id, which the fresh loop then moves because A's `only-a` holds it. A's
       `only-a` then takes the loser's body, link, evidence and pending row.
       Census of the id-keyed tables `remap_b` is applied to, checked here for the remap_a /
       chaining gap: entities and concepts (A losers are DROPPED, not redirected — no chain
       to follow), memory_content (step 7c redirects A losers — gap), entity_links and
       linkage_evidence (both remap A ids — gap), pending_refs (source_id remap — gap),
       bitmap_fragments (A rows not remapped at all — B1a), Lance vectors (the op deletes both
       ids of B's moves only; A losers' vectors are not at issue in L99). Each gap has an
       assertion below.
  M2   `vector_delete_error` driven for real: the (proj, memory) Lance dataset is made read-only
       on disk, so the delete raises inside the library. The catalog merge stays committed,
       the reply says so and names the table, and `rmx replica merge` exits 1 after printing,
       in text mode and with `--json`.
  M1   the reply's `vectors_deleted.deleted` is the number of rows actually removed, not the
       number of ids issued, when some moved ids have no vector row. Read through the op's
       reply, so the converged helper may take any name.

Throwaway stores under short `/tmp` mkdtemp roots only; no live `.refmatrix/` is touched.
"""
from __future__ import annotations

import rmx_sandbox  # task-29.4 #r5: test roots live under the sandbox root (short_root)
import os
import shutil
import stat
import tempfile
from pathlib import Path

import duckdb
import numpy as np
import pytest
from click.testing import CliRunner
from pyroaring import BitMap64

from refmatrix.store import _CONCEPT_SHIFT, _ENTITY_MASK, Store
from tests.test_bug216_remedy_r1 import _new_store, _open
from tests.test_bug216_remedy_r3 import _memory_slots, _op_daemon

DIM = 4


@pytest.fixture
def base():
    b = Path(rmx_sandbox.short_root("b216t")).resolve()
    yield b
    for p in b.rglob("*"):                          # undo any read-only fixture dirs
        if p.is_dir():
            os.chmod(p, 0o755)
    shutil.rmtree(b)


# ---------------------------------------------------------------- catalog readers


def _fragment_pairs(con) -> "dict[tuple[int, str], set[tuple[int, int]]]":
    out: dict = {}
    for pid, linkage, blob in con.execute(
            "SELECT partition_id, linkage, blob FROM bitmap_fragments").fetchall():
        out[(int(pid), str(linkage))] = {(b >> _CONCEPT_SHIFT, b & _ENTITY_MASK)
                                         for b in BitMap64.deserialize(bytes(blob))}
    return out


def _link_pairs(con) -> "dict[tuple[int, str], set[tuple[int, int]]]":
    out: dict = {}
    for pid, linkage, c, e in con.execute(
            "SELECT en.partition_id, lt.name, el.concept_id, el.entity_id FROM entity_links el "
            "JOIN linkage_types lt ON lt.id = el.linkage_id "
            "JOIN entities en ON en.id = el.entity_id").fetchall():
        out.setdefault((int(pid), str(linkage)), set()).add((int(c), int(e)))
    return out


def _assert_fragments_equal_links(path: Path, what: str) -> None:
    con = duckdb.connect(str(path), read_only=True)
    try:
        frags, links = _fragment_pairs(con), _link_pairs(con)
        names = {int(i): str(n) for i, n in con.execute(
            "SELECT id, name FROM entities").fetchall()}
    finally:
        con.close()
    nm = lambda ps: sorted((names.get(c, f"<{c}>"), names.get(e, f"<{e}>")) for c, e in ps)  # noqa: E731
    bad = {}
    for key in sorted(set(frags) | set(links)):
        f, ln = frags.get(key, set()), links.get(key, set())
        if f != ln:
            bad[key] = {"bits_not_links": nm(f - ln), "links_not_bits": nm(ln - f)}
    assert not bad, f"{what}: fragment bits differ from entity_links: {bad}"


def _memories(path: Path) -> "dict[str, tuple[int, str]]":
    con = duckdb.connect(str(path), read_only=True)
    try:
        return {str(n): (int(i), str(c)) for i, n, c in con.execute(
            "SELECT e.id, e.name, mc.content FROM entities e "
            "JOIN memory_content mc ON mc.entity_id = e.id WHERE e.kind = 'memory'").fetchall()}
    finally:
        con.close()


def _named(path: Path, sql: str) -> list:
    con = duckdb.connect(str(path), read_only=True)
    try:
        names = {int(i): str(n) for i, n in con.execute(
            "SELECT id, name FROM entities").fetchall()}
        return sorted(tuple(names.get(int(x), f"<{x}>") if isinstance(x, int) else x for x in r)
                      for r in con.execute(sql).fetchall())
    finally:
        con.close()


# ---------------------------------------------------------------- slot builders


def _slot_roots(base: Path) -> "tuple[Path, Path]":
    a_root = base / "A" / "proj" / ".refmatrix"
    b_root = base / "B" / "proj" / ".refmatrix"
    _new_store(a_root)
    s = _open(a_root)
    try:
        s.add_concept("topicx")
        try:
            s.get_linkage_id("related-to")
        except KeyError:
            s.add_linkage_type("related-to", directed=True)
    finally:
        s.close()
    b_root.mkdir(parents=True)
    shutil.copy2(a_root / "catalog.duckdb", b_root / "catalog.duckdb")
    return a_root, b_root


def _link_shared(s: Store, shared: int, *, file: str) -> None:
    """A-shared's own graph: `shared related-to topicx` with evidence, and a pending ref."""
    topic = s.get_entity("concept", "topicx").id
    s.link("related-to", shared, topic)
    s.add_evidence("related-to", shared, topic, file=file, line=7,
                   detail="rel: related-to -> topicx")
    s.add_pending_ref(shared, "depends-on", "missing-doc", ref="missing-doc", file=file, line=9)
    s.flush_fragments()


def _merge(a_root: Path, b_root: Path, target: Path) -> dict:
    from refmatrix.replica_merge import merge_slots
    target.parent.mkdir(parents=True, exist_ok=True)
    return merge_slots(a_root / "catalog.duckdb", b_root / "catalog.duckdb", target)


# ================================================================ B1a


def test_b1a_an_a_losers_bits_follow_it_and_never_name_the_b_entity_at_its_old_id(base):
    a_root, b_root = _slot_roots(base)
    s = _open(a_root)
    try:
        a_shared = s.add_memory("shared", "SHARED A")
        _link_shared(s, a_shared, file=str(base / "a.md"))
    finally:
        s.close()
    s = _open(b_root)
    try:
        b1 = s.add_memory("b1", "B ONE")
        s.add_memory("b-two", "B TWO")
        b_shared = s.add_memory("shared", "SHARED B (newer)")
        s.flush_fragments()
    finally:
        s.close()
    assert b1 == a_shared and b_shared != a_shared, (
        f"precondition: B's b1 holds A-shared's id ({a_shared}); B's shared is {b_shared}")
    for root in (a_root, b_root):
        _assert_fragments_equal_links(root / "catalog.duckdb", f"precondition {root.parent.parent.name}")
    target = base / "T" / "catalog.duckdb"
    res = _merge(a_root, b_root, target)
    assert res["remap"]["a_loser_count"] == 1, f"precondition: A's shared loses: {res['remap']}"
    _assert_fragments_equal_links(target, "merged catalog")
    links = _named(target, "SELECT el.concept_id, lt.name, el.entity_id FROM entity_links el "
                           "JOIN linkage_types lt ON lt.id = el.linkage_id "
                           "WHERE lt.name = 'related-to'")
    assert links == [("shared", "related-to", "topicx")], links


# ================================================================ B1b


def test_b1b_an_a_loser_is_chained_through_the_fresh_move_and_no_a_entity_inherits_it(base):
    a_root, b_root = _slot_roots(base)
    s = _open(a_root)
    try:
        only_a = s.add_memory("only-a", "ONLY A")
        a_shared = s.add_memory("shared", "SHARED A")
        _link_shared(s, a_shared, file=str(base / "a.md"))
    finally:
        s.close()
    s = _open(b_root)
    try:
        b_shared = s.add_memory("shared", "SHARED B (newer)")
        s.flush_fragments()
    finally:
        s.close()
    assert b_shared == only_a and a_shared != b_shared, (
        f"precondition (bsd's 4 -> 3 -> 5): B's shared {b_shared} must sit at only-a's id "
        f"{only_a}; A's shared {a_shared}")
    target = base / "T" / "catalog.duckdb"
    res = _merge(a_root, b_root, target)
    moved = {int(o): int(n) for o, n in (res.get("fresh_moved") or [])}
    assert b_shared in moved, f"precondition: B's shared is moved: {res.get('fresh_moved')}"
    final = moved[b_shared]
    # Every table the chain gap reaches, checked and reported together.
    got = {
        "memory_content": _memories(target),
        "entity_links": _named(target, "SELECT el.concept_id, lt.name, el.entity_id "
                                       "FROM entity_links el JOIN linkage_types lt "
                                       "ON lt.id = el.linkage_id WHERE lt.name = 'related-to'"),
        "linkage_evidence": _named(target, "SELECT le.concept_id, le.entity_id, "
                                           "CAST(le.line AS VARCHAR) "
                                           "FROM linkage_evidence le JOIN linkage_types lt "
                                           "ON lt.id = le.linkage_id "
                                           "WHERE lt.name = 'related-to'"),
        "pending_refs": _named(target, "SELECT source_id, target_name FROM pending_refs"),
    }
    want = {
        "memory_content": {"only-a": (only_a, "ONLY A"), "shared": (final, "SHARED B (newer)")},
        "entity_links": [("shared", "related-to", "topicx")],
        "linkage_evidence": [("shared", "topicx", "7")],
        "pending_refs": [("shared", "missing-doc")],
    }
    got["memory_content"] = {k: v for k, v in got["memory_content"].items()
                             if k in ("only-a", "shared")}
    wrong = {t: {"want": want[t], "got": got[t]} for t in want if got[t] != want[t]}
    assert not wrong, (
        f"A's loser (`shared`, {a_shared}) -> B's `shared` ({b_shared}) -> moved to {final}; "
        f"tables that followed the stale remap_a onto `only-a` ({only_a}): {wrong}")
    _assert_fragments_equal_links(target, "merged catalog")


# ================================================================ M2 / M1 (the op)


def _seed_vectors(droot: Path, ids) -> None:
    from refmatrix.vectors import LanceVectorStore
    ids = sorted(ids)
    LanceVectorStore(droot / "vectors", partition="proj", dim=DIM).upsert_vectors(
        ids, np.ones((len(ids), DIM), dtype="float32"), kind="memory")


def _vector_ids(droot: Path) -> "set[int]":
    from refmatrix.vectors import LanceVectorStore
    ids, _ = LanceVectorStore(droot / "vectors", partition="proj", dim=0).read_vectors(
        kind="memory")
    return set(ids)


def _read_only_tree(p: Path) -> None:
    for q in [p, *p.rglob("*")]:
        mode = q.stat().st_mode
        os.chmod(q, (mode | stat.S_IRUSR | (stat.S_IXUSR if q.is_dir() else 0))
                 & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))


@pytest.fixture
def op_env(base):
    m = _memory_slots(base, n_moves=2)
    d, droot = _op_daemon(base, m)
    yield {"m": m, "d": d, "droot": droot}
    if d.store is not None:
        d.store.close()


def test_m2_a_failed_vector_delete_is_named_and_the_merge_stays_committed(op_env):
    from refmatrix import daemon as dm
    m, d, droot = op_env["m"], op_env["d"], op_env["droot"]
    _seed_vectors(droot, m["ids"] + [m["keep"]])
    table = droot / "vectors" / "proj" / "memory.lance"
    _read_only_tree(table)
    probe = table / "_rmx_write_probe"
    try:
        probe.write_text("x")
        probe.unlink()
        pytest.fail("precondition: the read-only Lance table dir is still writable "
                    "(running as root?)")
    except PermissionError:
        pass
    r = dm._op_replica_merge(d, {"dry_run": False})
    assert r.get("ok") is True, f"a vector-delete failure must not fail the merge: {r}"
    err = str(r.get("vector_delete_error") or "")
    assert err and "committed" in err and "memory.lance" in err, (
        f"the reply must say the merge is committed and name the table: {r}")
    # read through the reopened writer: a second connection to the slot from this process
    # would be refused by DuckDB (different configuration)
    assert d.store is not None and d.store.db_path.name == "catalog.A.duckdb", d.store
    names = {str(n) for (n,) in d.store._connect().execute(
        "SELECT name FROM entities WHERE kind = 'memory'").fetchall()}
    assert {"mem-a0", "mem-a1", "mem-b0", "mem-b1", "keep"} <= names, (
        f"the merged catalog is not installed on slot A: {names}")


@pytest.mark.parametrize("as_json", [False, True], ids=["text", "json"])
def test_m2_rmx_replica_merge_exits_1_after_printing_on_a_vector_delete_failure(op_env,
                                                                               monkeypatch,
                                                                               as_json):
    """`rmx replica merge --yes [--json]` through the REAL op (the transport answered in
    process): exit 1, the error on stderr, and the summary / JSON printed first."""
    from refmatrix import cli as cli_mod
    from refmatrix import daemon as dm
    m, d, droot = op_env["m"], op_env["d"], op_env["droot"]
    _seed_vectors(droot, m["ids"] + [m["keep"]])
    _read_only_tree(droot / "vectors" / "proj" / "memory.lance")
    monkeypatch.setattr(cli_mod, "_root", lambda: droot)
    monkeypatch.setattr(dm, "ping", lambda *a, **k: True)
    monkeypatch.setattr(dm, "call", lambda root, op, args, **kw:
                        {"ok": True, "result": dm.OPS[op](d, dict(args))})
    argv = ["replica", "merge", "--yes"] + (["--json"] if as_json else [])
    r = CliRunner().invoke(cli_mod.main, argv)
    assert r.exit_code == 1, f"exit {r.exit_code}:\n{r.output}"
    assert "memory.lance" in (r.stderr or ""), f"stderr does not name the table:\n{r.stderr!r}"
    printed = r.stdout
    if as_json:
        assert '"vector_delete_error"' in printed and '"fresh_moved"' in printed, printed
    else:
        assert "MERGED" in printed, f"the summary was not printed before the error:\n{printed}"


def test_m1_vectors_deleted_counts_the_rows_actually_removed(op_env):
    """Two moves -> four ids to delete; only THREE of them have a vector row. The reply's
    `vectors_deleted.deleted` must be 3 (rows removed), not 4 (ids issued)."""
    from refmatrix import daemon as dm
    m, d, droot = op_env["m"], op_env["d"], op_env["droot"]
    fresh_guess = list(range(max(m["ids"]) + 1, max(m["ids"]) + 1 + len(m["ids"])))
    seeded = [m["ids"][0], m["ids"][1], fresh_guess[0], m["keep"]]   # fresh_guess[1] has none
    _seed_vectors(droot, seeded)
    before = _vector_ids(droot)
    r = dm._op_replica_merge(d, {"dry_run": False})
    assert r.get("ok") is True and not r.get("vector_delete_error"), r
    moved = [(int(o), int(n)) for o, n in (r.get("fresh_moved") or [])]
    both = {i for pair in moved for i in pair}
    assert both == set(m["ids"]) | set(fresh_guess), f"precondition: moves {moved}"
    removed = len(before - _vector_ids(droot))
    assert removed == 3, f"precondition: 3 rows actually deleted, measured {removed}"
    assert r["vectors_deleted"]["deleted"] == removed, (
        f"`deleted` = {r['vectors_deleted']['deleted']} for {removed} rows removed "
        f"({len(both)} ids issued): it must count rows, not ids")


# ================================================================ vector owners (lead's L99 extension)


def test_b1a_op_deletes_the_vector_at_an_id_an_a_loser_vacated_and_requeues_its_new_owner(base):
    """PIN for the lead's extension of L99 (green-216, at 9def24a: dropping the two `remap_a`
    UNION branches from replica_merge's `vector_rows` query survived r3 + r4, 9 passed).

    The B1a shape through the REAL `_op_replica_merge`: A's `shared` loses to B's newer twin and
    B's `b1` holds A-shared's old id. The Lance row at that id is A-shared's vector, so after the
    merge it names `b1` wrongly: it must be deleted and `b1` re-queued. B-shared's row (the
    canonical, owner unchanged) and an unrelated memory's row stay; the unrelated memory is
    not re-queued."""
    from refmatrix import daemon as dm
    a_root = base / "A" / "proj" / ".refmatrix"
    b_root = base / "B" / "proj" / ".refmatrix"
    _new_store(a_root)
    s = _open(a_root)
    try:
        keep = s.add_memory("keep", "an unrelated, embedded memory")
    finally:
        s.close()
    b_root.mkdir(parents=True)
    shutil.copy2(a_root / "catalog.duckdb", b_root / "catalog.duckdb")
    s = _open(a_root)
    try:
        a_shared = s.add_memory("shared", "SHARED A")
    finally:
        s.close()
    s = _open(b_root)
    try:
        b1 = s.add_memory("b1", "B ONE")
        s.add_memory("b-two", "B TWO")
        b_shared = s.add_memory("shared", "SHARED B (newer)")
    finally:
        s.close()
    assert b1 == a_shared and b_shared not in (a_shared, keep), (
        f"precondition: b1 at A-shared's id {a_shared}; b_shared {b_shared}; keep {keep}")
    for root in (a_root, b_root):                 # every entity embedded, as after `rmx embed`
        con = duckdb.connect(str(root / "catalog.duckdb"))
        try:
            con.execute("UPDATE entities SET vectors_updated_at = updated_at + 1, "
                        "vectors_partition = 'proj'")
        finally:
            con.close()
    droot = base / "D" / "proj" / ".refmatrix"
    droot.mkdir(parents=True)
    shutil.copy2(a_root / "catalog.duckdb", droot / "catalog.A.duckdb")
    shutil.copy2(b_root / "catalog.duckdb", droot / "catalog.B.duckdb")
    (droot / "active").write_text("A")
    _seed_vectors(droot, [a_shared, b_shared, keep])
    d = dm.Daemon(droot, partition="proj")
    d._log = lambda msg: None
    d.store = Store(droot, partition="proj")
    d.store.init()
    d.store._connect()
    try:
        r = dm._op_replica_merge(d, {"dry_run": False})
        assert r.get("ok") is True and not r.get("vector_delete_error"), r
        assert r["remap"]["a_loser_count"] == 1, f"precondition: A's shared loses: {r['remap']}"
        with d.store.with_partition("proj"):
            pending = {int(row[0]) for row in d.store.pending_embeddings()}
    finally:
        if d.store is not None:
            d.store.close()
    left = _vector_ids(droot)
    assert a_shared not in left, (
        f"the Lance row at {a_shared} (A-shared's vector, now under b1) survived the merge")
    assert {b_shared, keep} <= left, (
        f"the merge deleted a vector whose owner did not change: kept {sorted(left)}")
    assert b1 in pending, f"b1 ({b1}) holds a vacated id but was not re-queued: {sorted(pending)}"
    assert keep not in pending, "an unrelated, embedded memory was re-queued"
