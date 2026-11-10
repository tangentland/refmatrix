"""bug-178: no `executemany` reaches DuckDB — one bulk-write helper (TDD RED, 2026-11-09).

Spec: workflow/plans/task-bug178-bulk-write-helper.md (AC-1, AC-2, AC-4, AC-5; AC-3 is the
timing harness workflow/measurements/bug178-store-scores.py, not a test here).

WHY: DuckDB runs `executemany` one statement per row under the store's single writer lock. On
2026-11-09 a viascope reingest spent minutes in `pagerank.store_scores -> executemany` while a
CLI op and the periodic flush waited on that lock (the same writer-held shape failed two Stop-hook
promotes, bug-177).

The spy is two-layered on purpose:
  * a pass-through wrapper on `backend.DuckDBConnection.executemany` (the Store's wrapper), and
  * a `sys.setprofile` C-call observer that sees EVERY native `executemany` on a DuckDB
    connection — `replica_merge` holds a RAW `duckdb.DuckDBPyConnection`, which no Python-level
    patch can intercept, and a proxy object would change `isinstance` answers the helper may use
    to pick its branch. The observer changes nothing; it only counts.
It also counts native `execute` calls: a per-row `execute` loop would satisfy "zero executemany"
while being the same defect, so each op must stay O(1) statements in N.

Goldens (AC-2): `tests/fixtures/bug178_head_golden.json` holds a sha256 of each site's canonical
row dump produced by the src tree at HEAD_SHA (rows keyed by NAME, not by sequence-allocated id,
so a helper that consumes sequence values differently is not a false failure). Regenerate ONLY
with src/ byte-identical to HEAD_SHA:
    PYTHONPATH=src python tests/test_bug178_bulk_write.py --write-golden
Each AC-2 test ALSO checks an explicitly-named reference implementation (`_ref_*`), so the
equivalence has an anchor that is not the code under test.

FOR THE IMPLEMENTER: `HELPER` / `ALLOWED` below are placeholders for the helper's location. If
you name it differently, change these two constants (and only these) in the GREEN commit.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path

import pytest

# ---- placeholders the implementer pins --------------------------------------------------
HELPER = ("backend", "bulk_write")            # (module under refmatrix, function name)
# Functions (module-stem-qualified) where an `executemany` call may appear in src/refmatrix:
#   the helper (its SQLite branch) and the DuckDBConnection wrapper itself (R3: it raises
#   above a small row count or logs a counted warning — the runtime spy guards that).
ALLOWED = {"backend.bulk_write", "backend.DuckDBConnection.executemany"}

HEAD_SHA = "56e8d14890790d7696e772eaafab71998515456f"
N = 5_000
# A set-based write issues O(1) statements; a per-row loop issues >= N. Bound well below N.
MAX_NATIVE_EXECUTES = N // 10

_REPO = Path(__file__).resolve().parents[1]
GOLDEN = _REPO / "tests" / "fixtures" / "bug178_head_golden.json"


# ---- the spy ---------------------------------------------------------------------------

class _Spy:
    """Pass-through observer. `wrapper` = calls of DuckDBConnection.executemany; `native` =
    native DuckDB `executemany` C-calls (any connection, raw or wrapped), each with the nearest
    src/refmatrix frame; `executes` = native DuckDB `execute` C-calls."""

    def __init__(self) -> None:
        self.wrapper: list[str] = []
        self.native: list[str] = []
        self.executes = 0

    def _site(self, frame) -> str:
        f = frame
        while f is not None:
            fn = f.f_code.co_filename
            if (f"{os.sep}src{os.sep}refmatrix{os.sep}" in fn
                    and not fn.endswith(f"{os.sep}backend.py")):   # name the CALLER site
                return f"{Path(fn).name}:{f.f_lineno} {f.f_code.co_name}"
            f = f.f_back
        return f"{Path(frame.f_code.co_filename).name}:{frame.f_lineno}"

    def profile(self, frame, event, arg):
        if event != "c_call":
            return
        name = getattr(arg, "__name__", None)
        if name not in ("executemany", "execute"):
            return
        if isinstance(getattr(arg, "__self__", None), (sqlite3.Connection, sqlite3.Cursor)):
            return                                          # SQLite is allowed (AC-4)
        if name == "executemany":
            self.native.append(self._site(frame))
        else:
            self.executes += 1


@contextmanager
def spy(monkeypatch):
    from refmatrix import backend
    s = _Spy()
    real = backend.DuckDBConnection.executemany

    def wrapper(self, sql, seq_of_params):
        s.wrapper.append(" ".join(str(sql).split())[:80])
        return real(self, sql, seq_of_params)

    monkeypatch.setattr(backend.DuckDBConnection, "executemany", wrapper)
    prev = sys.getprofile()
    sys.setprofile(s.profile)
    threading.setprofile(s.profile)
    try:
        yield s
    finally:
        sys.setprofile(prev)
        threading.setprofile(None)
        monkeypatch.setattr(backend.DuckDBConnection, "executemany", real)


def _assert_no_duckdb_executemany(s: _Spy, site: str) -> None:
    assert not s.native and not s.wrapper, (
        f"{site}: DuckDB executemany reached {len(s.native)} time(s) natively "
        f"(sites: {sorted(set(s.native))}), {len(s.wrapper)} via DuckDBConnection "
        f"(sql: {sorted(set(s.wrapper))}) — per-row on DuckDB under the writer lock (bug-178)")
    assert s.executes <= MAX_NATIVE_EXECUTES, (
        f"{site}: {s.executes} native DuckDB execute() calls for N={N} rows — a per-row loop, "
        f"not a set-based write")


# ---- throwaway stores (short root: macOS sun_path) ---------------------------------------

def _short_dir(prefix: str = "b178") -> Path:
    return Path(tempfile.mkdtemp(prefix=prefix, dir="/tmp"))


@contextmanager
def _store(backend: str):
    from refmatrix.store import Store
    base = _short_dir()
    s = Store(base / ".refmatrix", backend=backend)
    s.init()
    try:
        yield s
    finally:
        s.close()
        shutil.rmtree(base, ignore_errors=True)


def _con(s):
    return s._connect()


def _rows(s, sql, params=()):
    return [tuple(r) for r in _con(s).execute(sql, params).fetchall()]


def _entities(s, kind: str, names: list[str], *, meta=None, path=None) -> list[int]:
    out: list[int] = []
    for i in range(0, len(names), 1000):
        out += s.bulk_upsert_entity([(kind, n, path, None, meta) for n in names[i:i + 1000]])
    return out


def _letters(i: int) -> str:
    """A digit-free word for index i (ingest._WORD_RE + text_phrases drop digit runs)."""
    out = ""
    i += 26 * 26                                             # >= 3 letters
    while i:
        i, r = divmod(i, 26)
        out = chr(97 + r) + out
    return "q" + out


# ---- the sites: each returns (op, dump, reference) on a prepared store -------------------
# `op()` is the only thing run under the spy. `dump()` is the canonical, name-keyed result.
# `ref` is the reference implementation's expected dump (None where only the golden applies).

def _site_pagerank(s):
    from refmatrix import pagerank
    names = [f"pr{i:05d}" for i in range(N)]
    ids = _entities(s, "doc", names)
    # conflict case: a previous run's rows for half the ids must be REPLACED, not merged
    pagerank.store_scores(s, {eid: 9.0 for eid in ids[: N // 2]}, now=1.0)
    scores = {eid: (i % 97) / 7.0 for i, eid in enumerate(ids)}
    by_id = dict(zip(ids, names))

    def op():
        return pagerank.store_scores(s, scores, now=1234.5)

    def dump():
        return sorted(_rows(s,
            "SELECT e.name, p.partition_id, p.score, p.computed_at FROM pagerank p "
            "JOIN entities e ON e.id = p.entity_id"))

    def _ref_pagerank():
        return sorted((by_id[eid], s._partition_id, sc, 1234.5) for eid, sc in scores.items())
    return op, dump, _ref_pagerank(), N


def _site_backfill_canonical(s):
    from refmatrix.identifier import canonicalize_name
    names = [f"HTTPServer{_letters(i).title()}Cfg_{i}" for i in range(N)]
    _entities(s, "concept", names)
    _con(s).execute("UPDATE entities SET canonical_name = NULL WHERE kind = 'concept'")
    _con(s).commit()

    def op():
        return s._backfill_canonical_name_if_needed()

    def dump():
        return sorted(_rows(s,
            "SELECT name, canonical_name FROM entities WHERE kind = 'concept'"))

    def _ref_backfill():
        return sorted((n, canonicalize_name(n)) for n in names)
    return op, dump, _ref_backfill(), N


def _site_link_many(s):
    concept = _entities(s, "concept", ["bug178_hub"])[0]
    names = [f"lm{i:05d}" for i in range(N)]
    ids = _entities(s, "doc", names)
    by_id = dict(zip(ids, names))
    # conflict cases: 1,000 links already exist WITH a weight (OR IGNORE keeps it), and the
    # batch repeats its first 500 ids
    s.bulk_link([("mentions", concept, eid, 2.5) for eid in ids[:1000]])
    batch = ids + ids[:500]

    def op():
        return s.link_many("mentions", concept, batch)

    def dump():
        return sorted(_rows(s,
            "SELECT e.name, lt.name, c.name, l.weight FROM entity_links l "
            "JOIN entities e ON e.id = l.entity_id JOIN entities c ON c.id = l.concept_id "
            "JOIN linkage_types lt ON lt.id = l.linkage_id"))

    def _ref_link_many():
        return sorted((by_id[eid], "mentions", "bug178_hub", 2.5 if i < 1000 else None)
                      for i, eid in enumerate(ids))
    return op, dump, _ref_link_many(), len(batch)


def _site_clear_gmd_hashes(s):
    names = [f"gd{i:05d}" for i in range(N)]
    for kind, chunk in (("doc", names[: N // 2]), ("memory", names[N // 2:])):
        for i in range(0, len(chunk), 1000):
            s.bulk_upsert_entity([
                (kind, n, None, None,
                 {"gmd_content_hash": f"h{n}", "gmd_pass2_done": True, "keep": n})
                for n in chunk[i:i + 1000]])
    # skipped shapes: a non-dict and an unparseable meta, both matching the LIKE
    _entities(s, "doc", ["gd_list", "gd_bad"])
    _con(s).execute("UPDATE entities SET meta = '[\"gmd_content_hash\"]' WHERE name='gd_list'")
    _con(s).execute("UPDATE entities SET meta = '{gmd_content_hash' WHERE name='gd_bad'")
    _con(s).commit()

    def op():
        return s.clear_tracked_stamps()["gmd_hashes_cleared"]

    def dump():
        return sorted(_rows(s,
            "SELECT name, meta FROM entities WHERE name LIKE 'gd%'"))

    def _ref_clear_gmd_hashes():
        out = [(n, json.dumps({"keep": n})) for n in names]
        out += [("gd_list", '["gmd_content_hash"]'), ("gd_bad", "{gmd_content_hash")]
        return sorted(out)
    return op, dump, _ref_clear_gmd_hashes(), N


def _site_save_coref(s):
    from refmatrix.coref import Resolution
    eid = _entities(s, "memory", ["coref_target"])[0]
    # conflict case: a prior set is REPLACED wholesale (DELETE then insert)
    s.save_coref(eid, [Resolution(offset=i, pronoun="it", antecedent="old", confidence=0.1)
                       for i in range(0, 2 * N, 3)])
    res = [Resolution(offset=i * 2, pronoun=("he", "she", "it")[i % 3],
                      antecedent=f"Ante{_letters(i)}", confidence=(i % 10) / 10)
           for i in range(N)]

    def op():
        return s.save_coref(eid, res)

    def dump():
        # confidence is REAL: float32 on DuckDB, float64 on SQLite — compare at 6 places
        return sorted(r[:5] + (round(r[5], 6),) for r in _rows(s,
            "SELECT e.name, r.partition_id, r.pos, r.pronoun, r.antecedent, r.confidence "
            "FROM coref_resolutions r JOIN entities e ON e.id = r.entity_id"))

    def _ref_save_coref():
        return sorted(("coref_target", s._partition_id, r.offset, r.pronoun, r.antecedent,
                       round(r.confidence, 6)) for r in res)
    return op, dump, _ref_save_coref(), N


def _compile_body() -> str:
    return " ".join(_letters(i) for i in range(2_000))


def _site_compile_pairs(s):
    from pyroaring import BitMap
    from refmatrix.ingest import text_phrases
    body = _compile_body()
    mids = _entities(s, "memory", ["cp_a", "cp_b", "cp_c", "cp_lone"])
    for mid, content in zip(mids, [body, body, body, "zzunique wwlonely"]):
        _con(s).execute(
            "INSERT INTO memory_content(entity_id, content, mtype, created_at, updated_at) "
            "VALUES (?, ?, 'observation', 1.0, 1.0)", (mid, content))
    _con(s).commit()
    # conflict case: a previous compilation's rows are replaced wholesale
    s.compile_pairs(min_df=1)
    keys = list(text_phrases(body, stop=frozenset()))
    assert len(keys) >= N, f"fixture yields only {len(keys)} pairs; need >= {N}"
    names = {mid: n for mid, n in zip(mids, ["cp_a", "cp_b", "cp_c", "cp_lone"])}

    def op():
        return s.compile_pairs(min_df=3)["kept"]

    def dump():
        return sorted(
            (k, pid, df, tuple(sorted(names[i] for i in BitMap.deserialize(bytes(docs)))))
            for k, pid, df, docs in _rows(s,
                "SELECT pair_key, partition_id, df, docs FROM pair_index"))

    def _ref_compile_pairs():
        return sorted((k, s._partition_id, 3, ("cp_a", "cp_b", "cp_c")) for k in keys)
    return op, dump, _ref_compile_pairs(), len(keys)


def _site_bulk_upsert_dups(s):
    """bulk_upsert_entity's DuckDB fallback: an intra-batch duplicate (kind, name) key sends the
    WHOLE batch through `executemany` on DuckDB (store.py:2326) — the spec's inventory had it as
    SQLite-only. HEAD semantics are a sequential merge: path/tldr/meta COALESCE (later non-NULL
    wins), protected ratchets up, canonical_name first-set wins."""
    pre = [f"bu{i:05d}" for i in range(0, N // 2, 5)]           # pre-existing keys
    for i in range(0, len(pre), 1000):
        s.bulk_upsert_entity([("doc", n, "old/path", "old tldr", {"v": 0})
                              for n in pre[i:i + 1000]])
    keys = [f"bu{i:05d}" for i in range(N // 2)]
    rows = [("doc", n, f"p/{n}", None, {"v": 1}) for n in keys]
    rows += [("doc", n, None, f"t {n}", None) for n in keys]    # same keys again
    rows += [("concept", "BuConcept", None, None, {"description": "first"}),
             ("concept", "BuConcept", None, None, {"description": "second"})]
    out: dict = {}

    def op():
        out["ids"] = s.bulk_upsert_entity(rows)
        return len(out["ids"])

    def dump():
        got = sorted(_rows(s,
            "SELECT e.kind, e.name, e.path, e.tldr, e.meta, e.protected, e.canonical_name, "
            "c.description FROM entities e LEFT JOIN concepts c ON c.id = e.id "
            "WHERE e.name LIKE 'bu%' OR e.name = 'BuConcept'"))
        # the returned ids must name the stored row for each input key
        by_key = {(k, n): i for k, n, i in _rows(s,
                  "SELECT kind, name, id FROM entities WHERE name LIKE 'bu%' "
                  "OR name = 'BuConcept'")}
        assert out["ids"] == [by_key[(r[0], r[1])] for r in rows]
        return got

    def _ref_bulk_upsert_sequential():
        from refmatrix.store import _canonical_for_kind
        state: dict = {}
        for n in pre:
            state[("doc", n)] = ["old/path", "old tldr", json.dumps({"v": 0}), None]
        for kind, name, path, tldr, meta in rows:
            m = json.dumps(meta) if meta else None
            cur = state.get((kind, name))
            if cur is None:
                state[(kind, name)] = [path, tldr, m,
                                       (meta or {}).get("description") if kind == "concept"
                                       else None]
            else:
                cur[0] = path if path is not None else cur[0]
                cur[1] = tldr if tldr is not None else cur[1]
                cur[2] = m if m is not None else cur[2]
        return sorted((k, n, p, t, m, 0, _canonical_for_kind(k, n), d)
                      for (k, n), (p, t, m, d) in state.items())
    return op, dump, _ref_bulk_upsert_sequential(), len(rows)


STORE_SITES = {
    "pagerank.store_scores": _site_pagerank,
    "store._backfill_canonical_name_if_needed": _site_backfill_canonical,
    "store.link_many": _site_link_many,
    "store._clear_gmd_content_hashes": _site_clear_gmd_hashes,
    "store.save_coref": _site_save_coref,
    "store.compile_pairs": _site_compile_pairs,
    "store.bulk_upsert_entity[dup-keys]": _site_bulk_upsert_dups,
}


# ---- replica_merge: two DuckDB slot files, merged into a third ---------------------------

def _make_slot(path: Path, sql: list[str]) -> None:
    import duckdb
    from refmatrix.duckdb_catalog import init_catalog
    con = duckdb.connect(str(path))
    try:
        init_catalog(con)
        con.execute("INSERT INTO partitions(id, name, kind, created_at) "
                    "VALUES (1, 'local', 'repo', 1000.0)")
        for q in sql:
            con.execute(q)
    finally:
        con.close()


def _ent_sql(lo: int, hi: int, id_off: int, ts: str) -> str:
    return ("INSERT INTO entities(id, partition_id, kind, name, created_at, updated_at, "
            f"protected, noise) SELECT i + {id_off}, 1, 'doc', 'n' || lpad(i::VARCHAR, 6, '0'), "
            f"1000.0, {ts}, 0, 0 FROM range({lo}, {hi}) t(i)")


def _merge_linkage_slots(base: Path):
    """_merge_linkage_types: every B linkage id is remapped — 5,000 B names clash on id with A
    (fresh ids), 2,500 B names exist in A under another id (map to A's id). B's links point
    at B ids, so the remap is what keeps each link on its NAMED linkage."""
    a, b = base / "a.duckdb", base / "b.duckdb"
    ents = _ent_sql(0, 10, 0, "1000.0")
    _make_slot(a, [ents,
        "INSERT INTO linkage_types(id, name, directed) "
        f"SELECT i, 'la' || i, 1 FROM range(1, {N} + 2501) t(i)"])
    _make_slot(b, [ents,
        "INSERT INTO linkage_types(id, name, directed) "
        f"SELECT i, 'lb' || i, 1 FROM range(1, {N} + 1) t(i)",
        "INSERT INTO linkage_types(id, name, directed) "
        f"SELECT i + 100000, 'la' || i, 1 FROM range(1, 2501) t(i)",
        "INSERT INTO entity_links(entity_id, linkage_id, concept_id, weight) "
        f"SELECT i % 10, i, (i + 1) % 10, NULL FROM range(1, {N} + 1) t(i)",
        "INSERT INTO entity_links(entity_id, linkage_id, concept_id, weight) "
        "SELECT i % 10, i + 100000, (i + 3) % 10, NULL FROM range(1, 2501) t(i)"])
    return a, b


def _merge_entity_slots(base: Path):
    """_merge_into remap_a / remap_b: 2 x 5,000 (partition, kind, name) collisions on different
    ids; even names are newer in A (B loses -> remap_b), odd names newer in B (remap_a)."""
    a, b = base / "a.duckdb", base / "b.duckdb"
    lk = "INSERT INTO linkage_types(id, name, directed) VALUES (1, 'mentions', 1)"
    _make_slot(a, [lk,
        _ent_sql(0, 2 * N, 0, "CASE WHEN i % 2 = 0 THEN 2000.0 ELSE 1000.0 END"),
        "INSERT INTO entity_links(entity_id, linkage_id, concept_id) "
        f"SELECT i, 1, (i + 1) % {2 * N} FROM range(0, {2 * N}) t(i)"])
    _make_slot(b, [lk,
        _ent_sql(0, 2 * N, 100000, "CASE WHEN i % 2 = 0 THEN 1000.0 ELSE 2000.0 END"),
        "INSERT INTO entity_links(entity_id, linkage_id, concept_id) "
        f"SELECT i + 100000, 1, ((i + 2) % {2 * N}) + 100000 FROM range(0, {2 * N}) t(i)"])
    return a, b


def _merged_dump(target: Path, res: dict):
    import duckdb
    con = duckdb.connect(str(target), read_only=True)
    try:
        q = lambda sql: [tuple(r) for r in con.execute(sql).fetchall()]  # noqa: E731
        return {
            "entities": sorted(q("SELECT id, partition_id, kind, name, updated_at FROM entities")),
            "linkage_types": sorted(q("SELECT id, name, inverse_of FROM linkage_types")),
            "entity_links": sorted(q(
                "SELECT entity_id, linkage_id, concept_id, weight FROM entity_links")),
            "link_names": sorted(q(
                "SELECT e.name, lt.name, c.name FROM entity_links l "
                "JOIN entities e ON e.id = l.entity_id JOIN entities c ON c.id = l.concept_id "
                "JOIN linkage_types lt ON lt.id = l.linkage_id")),
            "merged_counts": sorted(res["merged_counts"].items()),
            "remap": sorted(res["remap"].items()),
        }
    finally:
        con.close()


def _ref_merge_linkage(d) -> None:
    """Reference: every name once; a B link sits on the linkage carrying its B NAME."""
    names = [n for _i, n, _inv in d["linkage_types"]]
    assert len(names) == len(set(names)) == N + 2500 + N
    by_id = {i: n for i, n, _inv in d["linkage_types"]}
    assert by_id[1] == "la1"                                  # A keeps its ids
    lb = sorted((f"n{i % 10:06d}", f"lb{i}", f"n{(i + 1) % 10:06d}") for i in range(1, N + 1))
    la = sorted((f"n{i % 10:06d}", f"la{i}", f"n{(i + 3) % 10:06d}") for i in range(1, 2501))
    assert sorted(set(lb) | set(la)) == sorted(set(d["link_names"]))


def _ref_merge_entities(d) -> None:
    """Reference: one row per name; the newer slot's id survives; links follow the winner."""
    ents = {n: i for i, _p, _k, n, _u in d["entities"]}
    assert len(ents) == len(d["entities"]) == 2 * N
    for j in range(2 * N):
        assert ents[f"n{j:06d}"] == (j if j % 2 == 0 else j + 100000)
    exp = {(f"n{j:06d}", "mentions", f"n{(j + 1) % (2 * N):06d}") for j in range(2 * N)}
    exp |= {(f"n{j:06d}", "mentions", f"n{(j + 2) % (2 * N):06d}") for j in range(2 * N)}
    assert set(d["link_names"]) == exp
    assert dict(d["remap"])["a_loser_count"] == N and dict(d["remap"])["b_loser_count"] == N


MERGE_SITES = {
    "replica_merge._merge_linkage_types": (_merge_linkage_slots, _ref_merge_linkage),
    "replica_merge._merge_into": (_merge_entity_slots, _ref_merge_entities),
}


def _run_merge(site: str, monkeypatch=None):
    from refmatrix import replica_merge
    seed, ref = MERGE_SITES[site]
    base = _short_dir()
    try:
        a, b = seed(base)
        target = base / "t.duckdb"
        if monkeypatch is None:
            res, s = replica_merge.merge_slots(a, b, target), None
        else:
            with spy(monkeypatch) as s:
                res = replica_merge.merge_slots(a, b, target)
        return _merged_dump(target, res), ref, s
    finally:
        shutil.rmtree(base, ignore_errors=True)


# ---- golden ------------------------------------------------------------------------------

def _digest(rows) -> dict:
    blob = json.dumps(rows, default=lambda o: o.hex() if isinstance(o, bytes) else repr(o),
                      sort_keys=True)
    count = (len(rows["rows"]) if "rows" in rows
             else sum(len(v) for v in rows.values() if isinstance(v, list)))
    return {"rows": count, "sha256": hashlib.sha256(blob.encode()).hexdigest()}


def _golden() -> dict:
    data = json.loads(GOLDEN.read_text())
    assert data["head"] == HEAD_SHA, f"golden recorded at {data['head']}, not HEAD {HEAD_SHA}"
    return data["sites"]


def _run_store_site(site: str, backend: str, monkeypatch=None):
    with _store(backend) as s:
        op, dump, ref, _n = STORE_SITES[site](s)
        if monkeypatch is None:
            result, sp = op(), None
        else:
            with spy(monkeypatch) as sp:
                result = op()
        return {"result": result, "rows": dump()}, ref, sp


@pytest.fixture(autouse=True)
def _quiet_log(monkeypatch):
    # facts.log is not the write under test; per-link name lookups would dominate link_many.
    monkeypatch.setenv("RMX_LOG", "0")


# ---- AC-1: zero DuckDB executemany per reachable site (RED at HEAD) ----------------------

@pytest.mark.parametrize("site", sorted(STORE_SITES))
def test_ac1_store_site_issues_no_duckdb_executemany(site, monkeypatch):
    with _store("duckdb") as s:
        op, _dump, _ref, n = STORE_SITES[site](s)
        assert n >= N, f"{site}: only {n} rows written; AC-1 needs >= {N}"
        with spy(monkeypatch) as sp:
            op()
    _assert_no_duckdb_executemany(sp, site)


@pytest.mark.parametrize("site", sorted(MERGE_SITES))
def test_ac1_replica_merge_issues_no_duckdb_executemany(site, monkeypatch):
    _d, _ref, sp = _run_merge(site, monkeypatch)
    _assert_no_duckdb_executemany(sp, site)


# ---- AC-2 (DuckDB) + AC-4 (SQLite): rows equal HEAD's golden and the reference ----------

@pytest.mark.parametrize("backend", ["duckdb", "sqlite"])
@pytest.mark.parametrize("site", sorted(STORE_SITES))
def test_ac2_ac4_store_site_rows_match_head_and_reference(site, backend):
    got, ref, _ = _run_store_site(site, backend)
    assert got["rows"] == ref, f"{site}/{backend}: rows differ from the reference implementation"
    assert _digest(got) == _golden()[f"{site}/{backend}"], (
        f"{site}/{backend}: rows or return value differ from HEAD {HEAD_SHA[:7]}'s golden")


@pytest.mark.parametrize("site", sorted(MERGE_SITES))
def test_ac2_replica_merge_matches_head_and_reference(site):
    d, ref, _ = _run_merge(site)
    ref(d)
    assert _digest(d) == _golden()[f"{site}/duckdb"], (
        f"{site}: merged catalog differs from HEAD {HEAD_SHA[:7]}'s golden")


@pytest.mark.parametrize("backend", ["duckdb", "sqlite"])
def test_ac2_ac4_save_coref_duplicate_position_still_raises(backend):
    """Conflict case with no golden rows: a duplicate (entity, pos) is a PK violation on both
    backends at HEAD and must still RAISE (no silent failure on a memory path). HEAD leaves the
    rows before the duplicate behind (executemany is not atomic); a set-based insert is — the
    partial state is deliberately NOT pinned."""
    from refmatrix.coref import Resolution
    with _store(backend) as s:
        eid = _entities(s, "memory", ["dup_pos"])[0]
        r = Resolution(offset=7, pronoun="he", antecedent="A", confidence=0.5)
        with pytest.raises(Exception, match=r"(?i)constraint|unique|duplicate"):
            s.save_coref(eid, [r, r])


# ---- R2: the existing hand-rolled Arrow branches route through the ONE helper -----------

def _helper_spy(monkeypatch) -> list:
    import importlib
    mod, fn = HELPER
    owner = importlib.import_module(f"refmatrix.{mod}")
    real = getattr(owner, fn, None)
    assert real is not None, (
        f"refmatrix.{mod}.{fn} does not exist — R1's one bulk-write helper (bug-178). If it has "
        f"another name, update HELPER/ALLOWED at the top of this file")
    calls: list = []

    def counting(*a, **kw):
        calls.append(fn)
        return real(*a, **kw)

    for m in ("backend", "store", "pagerank", "replica_merge"):
        mm = importlib.import_module(f"refmatrix.{m}")
        if getattr(mm, fn, None) is real:
            monkeypatch.setattr(mm, fn, counting)
    return calls


@pytest.mark.parametrize("op", ["bulk_link", "bulk_mark_tracked", "bulk_upsert_entity"])
def test_r2_existing_arrow_branches_use_the_helper(op, monkeypatch):
    with _store("duckdb") as s:
        concept = _entities(s, "concept", ["r2hub"])[0]
        ids = _entities(s, "doc", [f"r2_{i}" for i in range(50)])
        calls = _helper_spy(monkeypatch)
        if op == "bulk_link":
            s.bulk_link([("mentions", concept, e, None) for e in ids])
        elif op == "bulk_mark_tracked":
            s.bulk_mark_tracked([(f"/x/{i}", float(i)) for i in range(50)])
        else:
            s.bulk_upsert_entity([("doc", f"r2new_{i}", None, None, None) for i in range(50)])
    assert calls, f"{op}: its DuckDB Arrow write did not go through {'.'.join(HELPER)} (R2)"


# ---- AC-5 guard: static scan -------------------------------------------------------------

def _executemany_sites() -> list[str]:
    out = []
    src = _REPO / "src" / "refmatrix"
    for py in sorted(src.rglob("*.py")):
        tree = ast.parse(py.read_text(), filename=str(py))
        stem = ".".join(py.relative_to(src).with_suffix("").parts)

        def walk(node, scope):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    walk(child, scope + [child.name])
                    continue
                if (isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute)
                        and child.func.attr == "executemany"):
                    out.append((".".join([stem] + scope), f"{py.name}:{child.lineno}"))
                walk(child, scope)
        walk(tree, [])
    return out


def test_ac5_executemany_only_in_the_helper():
    stray = sorted(f"{where} ({fn})" for fn, where in _executemany_sites() if fn not in ALLOWED)
    assert not stray, (
        f"{len(stray)} executemany call(s) outside {sorted(ALLOWED)} — every bulk write goes "
        f"through the one helper (bug-178 R1/R3):\n  " + "\n  ".join(stray))


# ---- golden writer (run at HEAD_SHA only) ------------------------------------------------

def _write_golden() -> None:
    diff = subprocess.run(["git", "-C", str(_REPO), "diff", "--quiet", HEAD_SHA, "--", "src"])
    if diff.returncode != 0:
        sys.exit(f"refusing: src/ differs from {HEAD_SHA}; the golden is HEAD's output")
    os.environ["RMX_LOG"] = "0"
    sites = {}
    for site in sorted(STORE_SITES):
        for backend in ("duckdb", "sqlite"):
            got, ref, _ = _run_store_site(site, backend)
            assert got["rows"] == ref, f"{site}/{backend}: HEAD disagrees with the reference"
            sites[f"{site}/{backend}"] = _digest(got)
            print(site, backend, sites[f"{site}/{backend}"], flush=True)
    for site in sorted(MERGE_SITES):
        d, ref, _ = _run_merge(site)
        ref(d)
        sites[f"{site}/duckdb"] = _digest(d)
        print(site, sites[f"{site}/duckdb"], flush=True)
    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN.write_text(json.dumps({"head": HEAD_SHA, "n": N, "sites": sites}, indent=1,
                                 sort_keys=True) + "\n")


if __name__ == "__main__":
    if sys.argv[1:] != ["--write-golden"]:
        sys.exit(__doc__)
    os.environ.setdefault("RMX_HOME", tempfile.mkdtemp(prefix="b178h", dir="/tmp"))
    _write_golden()
