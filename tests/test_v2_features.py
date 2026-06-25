"""Tests for primer, scan-prompt, vacuum, prune-noise, --explain, --since, evidence."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from refmatrix.cli import main as cli_main
from refmatrix.primer import build_primer, is_symbol_like
from refmatrix.scan import extract_candidates, match_concepts, scan_prompt
from refmatrix.store import Store, default_partition_name


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / ".refmatrix")
    s.init()
    yield s
    s.close()


# --- primer -----------------------------------------------------------------


@pytest.mark.parametrize("name,want", [
    ("register_graph_object", True),
    ("channel_aid", True),
    ("foo.bar.baz", True),
    ("Module::method", True),
    ("camelCase", True),
    ("data", False),
    ("value", False),
    ("input", False),
])
def test_is_symbol_like(name, want):
    assert is_symbol_like(name) is want


def test_build_primer_filters_symbols_and_namespaces(store):
    sym = store.add_concept("register_graph_object")
    nope = store.add_concept("data")
    noise = store.add_namespaced_concept("keyword", "data")
    e = store.upsert_entity(kind="code", name="x.py")
    for cid in (sym, nope, noise):
        store.link("mentions", cid, e)
    out = build_primer(store, top_n=10, max_tokens=500, min_refs=1)
    assert "register_graph_object" in out
    assert "\ndata(" not in out          # English noun — filtered
    assert "keyword/data" not in out     # namespace excluded


def test_build_primer_min_refs_threshold(store):
    cid = store.add_concept("foo_bar")
    e = store.upsert_entity(kind="code", name="x.py")
    store.link("mentions", cid, e)            # df = 1
    out = build_primer(store, min_refs=2, max_tokens=500)
    assert "foo_bar" not in out


# --- scan-prompt ------------------------------------------------------------


def test_extract_candidates_picks_identifier_shapes():
    cands = extract_candidates(
        "please fix register_graph_object and channel.aid; "
        "ignore plain words like the and of"
    )
    assert "register_graph_object" in cands
    assert "channel.aid" in cands


def test_match_concepts_excludes_noise_namespace(store):
    store.add_concept("register_graph_object")
    store.add_namespaced_concept("keyword", "register_graph_object")
    matches = match_concepts(store, ["register_graph_object"])
    # only the bare concept, never the keyword/ one
    assert matches == ["register_graph_object"]


def test_primer_keeps_import_namespace_by_default(store):
    cid = store.add_namespaced_concept("import", "requests")
    e = store.upsert_entity(kind="code", name="x.py")
    store.link("imports", cid, e)
    out = build_primer(store, top_n=10, max_tokens=500, min_refs=1)
    assert "import/requests" in out


def test_scan_prompt_emits_bundle_for_known_symbol(store):
    cid = store.add_concept("register_graph_object")
    e = store.upsert_entity(kind="code", name="src/a.py", tldr="implementation")
    store.link("defines", cid, e)
    out = scan_prompt(store, "fix register_graph_object please")
    assert "register_graph_object" in out
    assert "src/a.py" in out


def test_scan_prompt_silent_for_unknown_prompt(store):
    assert scan_prompt(store, "what is the weather") == ""


# --- pagerank prior (stage 2) ----------------------------------------------


def test_pagerank_hub_outranks_leaf(store):
    from refmatrix import pagerank as pr
    hub = store.add_concept("hub")
    leaf = store.add_concept("leaf")
    ents = [store.upsert_entity(kind="code", name=f"f{i}.py") for i in range(6)]
    store.add_linkage_type("defines", directed=True, description="x")
    for e in ents:
        store.link("defines", hub, e)
        store.link("mentions", hub, e)
    store.link("defines", leaf, ents[0])
    store.link("mentions", leaf, ents[0])
    scores = pr.compute(store)
    assert scores[hub] > scores[leaf]
    # centrality ratio: hub well above the 1.0 average, leaf below
    assert scores[hub] > 1.0 > scores[leaf]
    n = pr.store_scores(store, scores)
    assert n == len(scores)
    assert pr.get_score(store, hub) == pytest.approx(scores[hub])
    assert len(pr.load_scores(store)) == n


def test_pagerank_prior_lifts_central_concept_in_match_ranking(store):
    """A central concept should outrank a peripheral one of identical token
    shape once the PageRank prior is computed."""
    from refmatrix import pagerank as pr
    # two same-shaped lowercase concepts; only graph centrality differs
    central = store.add_concept("alpha")
    fringe = store.add_concept("omega")
    ents = [store.upsert_entity(kind="code", name=f"m{i}.py") for i in range(6)]
    store.add_linkage_type("defines", directed=True, description="x")
    for e in ents:
        store.link("defines", central, e)
        store.link("mentions", central, e)
    store.link("mentions", fringe, ents[0])
    pr.store_scores(store, pr.compute(store))
    ranked = match_concepts(store, ["omega", "alpha"])
    assert ranked.index("alpha") < ranked.index("omega")


# --- local-push PPR (stage 3) ----------------------------------------------


def test_ppr_surfaces_related_concept_not_in_prompt(store):
    """Seed PPR on concept A; concept B (shares A's entities) should rank high
    among related concepts, while an unrelated concept C does not appear."""
    from refmatrix import ppr
    a = store.add_concept("alpha")
    b = store.add_concept("beta")
    c = store.add_concept("gamma")
    shared = [store.upsert_entity(kind="code", name=f"s{i}.py") for i in range(4)]
    lone = store.upsert_entity(kind="code", name="lone.py")
    for e in shared:
        store.link("mentions", a, e)
        store.link("mentions", b, e)      # B co-mentions everything A does
    store.link("mentions", c, lone)        # C is off on its own
    related = ppr.rank_related(store, [a], k=5, kinds=("concept",),
                               include_seeds=False)
    names = [r["name"] for r in related]
    assert "beta" in names                 # discovered neighbor
    assert "gamma" not in names            # disconnected — never reached


def test_ppr_excludes_operational_session_cards(store):
    """A high-degree session card hub must not surface as a related concept."""
    from refmatrix import ppr
    a = store.add_concept("alpha")
    card = store.add_concept("session-deadbeef")   # operational card anchor
    ents = [store.upsert_entity(kind="code", name=f"e{i}.py") for i in range(4)]
    for e in ents:
        store.link("mentions", a, e)
        store.link("mentions", card, e)            # card co-mentions everything
    related = ppr.rank_related(store, [a], k=5, include_seeds=False)
    assert "session-deadbeef" not in [r["name"] for r in related]


def test_ppr_local_push_mass_concentrates_on_seed_cluster(store):
    from refmatrix import ppr
    from refmatrix.pagerank import build_adjacency
    a = store.add_concept("alpha")
    b = store.add_concept("beta")
    ents = [store.upsert_entity(kind="code", name=f"e{i}.py") for i in range(3)]
    for e in ents:
        store.link("mentions", a, e)
        store.link("mentions", b, e)
    adj = build_adjacency(store)
    p = ppr.local_push_ppr(adj, [a], alpha=0.15, eps=1e-5)
    # seed holds the most mass; connected nodes get positive mass
    assert p[a] == max(p.values())
    assert p.get(b, 0.0) > 0.0
    assert abs(sum(p.values())) <= 1.0 + 1e-6


# --- vacuum -----------------------------------------------------------------


def test_vacuum_drops_empty_concepts_and_missing_files(tmp_path, store):
    used = store.add_concept("used")
    empty = store.add_concept("empty")
    e = store.upsert_entity(kind="code", name="present.py",
                            path=str(tmp_path / "present.py"))
    (tmp_path / "present.py").write_text("x")
    store.link("defines", used, e)
    store.mark_tracked(str(tmp_path / "present.py"),
                       (tmp_path / "present.py").stat().st_mtime)
    store.mark_tracked(str(tmp_path / "gone.py"), 0.0)
    out = store.vacuum()
    assert out["concepts_dropped"] >= 1
    assert out["files_purged"] >= 1
    assert store.get_entity_by_id(used) is not None
    assert store.get_entity_by_id(empty) is None


# --- prune-noise ------------------------------------------------------------


def test_prune_noise_marks_singletons_and_too_common_by_default(store):
    entities = [store.upsert_entity(kind="code", name=f"f{i}.py") for i in range(20)]
    rare = store.add_namespaced_concept("keyword", "rare")        # df=1 → mark
    common = store.add_namespaced_concept("keyword", "common")     # df=20 → mark
    just_right = store.add_namespaced_concept("keyword", "okay")   # df=3 → keep
    store.link("mentions", rare, entities[0])
    for e in entities:
        store.link("mentions", common, e)
    for e in entities[:3]:
        store.link("mentions", just_right, e)
    out = store.prune_noise(min_df=2, max_df_ratio=0.25)
    assert out["marked"] == 2
    assert out["dropped"] == 0
    # Concepts still exist — they're flagged, not deleted.
    assert store.get_entity_by_id(rare) is not None
    assert store.get_entity_by_id(common) is not None
    assert store.get_entity_by_id(just_right) is not None
    assert store.is_noise(rare)
    assert store.is_noise(common)
    assert not store.is_noise(just_right)


def test_prune_noise_drop_actually_deletes(store):
    entities = [store.upsert_entity(kind="code", name=f"f{i}.py") for i in range(20)]
    rare = store.add_namespaced_concept("keyword", "rare")
    store.link("mentions", rare, entities[0])
    out = store.prune_noise(min_df=2, max_df_ratio=0.25, drop=True)
    assert out["dropped"] == 1
    assert out["marked"] == 0
    assert store.get_entity_by_id(rare) is None


def test_prune_noise_unmarks_when_threshold_passed(store):
    entities = [store.upsert_entity(kind="code", name=f"f{i}.py") for i in range(20)]
    cid = store.add_namespaced_concept("keyword", "borderline")
    store.link("mentions", cid, entities[0])  # df=1 → noise
    store.prune_noise(min_df=2, max_df_ratio=0.25)
    assert store.is_noise(cid)
    # Add another link → df=2, should clear noise on next pass.
    store.link("mentions", cid, entities[1])
    out = store.prune_noise(min_df=2, max_df_ratio=0.25)
    assert out["unmarked"] == 1
    assert not store.is_noise(cid)


def test_prune_noise_skips_protected(store):
    entities = [store.upsert_entity(kind="code", name=f"f{i}.py") for i in range(20)]
    pinned = store.add_namespaced_concept("keyword", "pinned")
    # Manually re-upsert with protected=True (or use add_concept with the flag).
    store.upsert_entity(kind="concept", name="keyword/pinned", protected=True)
    store.link("mentions", pinned, entities[0])  # df=1 — would normally be noise
    out = store.prune_noise(min_df=2, max_df_ratio=0.25)
    # Protected concept never enters the loop.
    assert out["marked"] == 0
    assert not store.is_noise(pinned)
    assert store.get_entity_by_id(pinned) is not None


# --- --explain --------------------------------------------------------------


def test_explain_entity_returns_linkages_with_evidence(store):
    cid = store.add_concept("auth")
    e = store.upsert_entity(kind="code", name="auth.py")
    store.link("defines", cid, e)
    store.add_evidence("defines", cid, e, file="auth.py", line=10, detail="def login")
    rows = store.explain_entity(e)
    assert len(rows) == 1
    r = rows[0]
    assert r["linkage"] == "defines"
    assert r["concept_name"] == "auth"
    assert r["evidence"][0]["line"] == 10


# --- --since ----------------------------------------------------------------


def test_context_since_finds_concepts_for_changed_files(tmp_path, monkeypatch):
    if subprocess.run(["git", "--version"], capture_output=True).returncode != 0:
        pytest.skip("git not available")

    proj = tmp_path / "proj"
    proj.mkdir()
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}

    def run(*args):
        subprocess.run(["git", "-C", str(proj), *args], env={**__import__("os").environ, **env},
                       check=True, capture_output=True)
    run("init", "-q", "-b", "main")
    (proj / "a.py").write_text("# a\n")
    run("add", "a.py")
    run("commit", "-q", "-m", "init")

    rmx_root = proj / ".refmatrix"
    rmx_root.mkdir()
    s = Store(rmx_root)
    s.init()
    cid = s.add_concept("parser")
    e = s.upsert_entity(kind="code", name="b.py", path=str(proj / "b.py"))
    s.link("defines", cid, e)
    s.close()

    (proj / "b.py").write_text("# b\n")
    run("add", "b.py")
    run("commit", "-q", "-m", "add b")

    monkeypatch.setenv("REFMATRIX_ROOT", str(rmx_root))
    runner = CliRunner()
    result = runner.invoke(cli_main, ["context", "--since", "HEAD~1"])
    assert result.exit_code == 0, result.output
    assert "parser" in result.output


# --- query --explain --------------------------------------------------------


def test_query_explain_flag(tmp_path, monkeypatch):
    rmx_root = tmp_path / ".refmatrix"
    s = Store(rmx_root)
    s.init()
    cid = s.add_concept("auth")
    e = s.upsert_entity(kind="code", name="auth.py")
    s.link("defines", cid, e)
    s.add_evidence("defines", cid, e, file="auth.py", line=42)
    s.close()

    monkeypatch.setenv("REFMATRIX_ROOT", str(rmx_root))
    runner = CliRunner()
    result = runner.invoke(cli_main, ["query", "defines:auth", "--explain"])
    assert result.exit_code == 0, result.output
    assert "auth.py" in result.output
    # explain-table contains the linkage column header and the line evidence
    assert "linkage" in result.output.lower() or "defines" in result.output
    assert "42" in result.output


# --- legacy bitmap migration -----------------------------------------------


def test_legacy_per_concept_bitmaps_migrate_to_fragments(tmp_path, monkeypatch):
    # SQLite-only legacy migration: DuckDB has no equivalent on-disk legacy.
    monkeypatch.setenv("RMX_BACKEND", "sqlite")
    """Simulate a pre-fragment catalog: write some .rb files into
    .refmatrix/bitmaps/<linkage>/<concept_id>.rb, open the Store, and verify
    the migration packs them into fragments and deletes the originals."""
    from pyroaring import BitMap as _BitMap

    root = tmp_path / ".refmatrix"
    root.mkdir()
    s = Store(root)
    s.init()
    # Create concepts + an entity so there's something for linkage to point at.
    cid_a = s.add_concept("alpha")
    cid_b = s.add_concept("beta")
    eid = s.upsert_entity(kind="code", name="x.py")
    # Forge legacy .rb files (don't go through s.link — that'd write to
    # fragments). Mirror the pre-migration on-disk layout exactly.
    legacy_dir = root / "bitmaps" / "mentions"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    bm_a = _BitMap()
    bm_a.add(eid)
    (legacy_dir / f"{cid_a}.rb").write_bytes(bm_a.serialize())
    bm_b = _BitMap()
    bm_b.add(eid)
    (legacy_dir / f"{cid_b}.rb").write_bytes(bm_b.serialize())
    s.close()

    # Reopen — _connect() should run the migration.
    s2 = Store(root)
    # Force a connect so migration actually runs.
    s2._connect()
    # Fragments live under fragments/<partition>/ since the partition split.
    assert (root / "fragments" / default_partition_name(root)
            / "mentions.rb64").exists()
    # Legacy dir should be cleaned up.
    assert not list(legacy_dir.glob("*.rb"))
    # And load_bitmap should return the migrated rows.
    out_a = s2.load_bitmap("mentions", cid_a)
    out_b = s2.load_bitmap("mentions", cid_b)
    assert eid in out_a
    assert eid in out_b
    s2.close()


# --- sync.log ---------------------------------------------------------------


def test_existing_catalog_auto_heals_missing_tables(tmp_path):
    """Simulate viascope-style catalog created before linkage_evidence existed:
    drop the table, close, reopen, verify it's recreated and add_evidence works.
    """
    import sqlite3 as _sql

    s = Store(tmp_path / ".refmatrix")
    s.init()
    cid = s.add_concept("auth")
    e = s.upsert_entity(kind="code", name="auth.py")
    s.link("defines", cid, e)

    # Drop the linkage_evidence table (and tracked_files for good measure) —
    # mimicking an older catalog version.
    con = s._connect()
    con.execute("DROP TABLE IF EXISTS linkage_evidence")
    con.execute("DROP TABLE IF EXISTS tracked_files")
    con.commit()
    s.close()

    # Reopen — _connect() should self-heal via CATALOG_DDL.
    s2 = Store(tmp_path / ".refmatrix")
    # No init() call — exactly what `rmx ingest` etc. do.
    s2.add_evidence("defines", cid, e, file="auth.py", line=1, detail="ok")
    rows = s2.get_evidence(e)
    assert len(rows) == 1 and rows[0]["line"] == 1
    s2.close()


def test_legacy_catalog_without_protected_noise_self_heals(tmp_path, monkeypatch):
    """Simulate a catalog created before protected/noise existed: drop the
    columns, reopen, verify the migration adds them and indexes work."""
    import sqlite3 as _sql

    # SQLite-only path: DuckDB schema starts with these columns and has no
    # equivalent self-heal migration.
    monkeypatch.setenv("RMX_BACKEND", "sqlite")
    s = Store(tmp_path / ".refmatrix")
    s.init()
    cid = s.add_concept("legacy_concept", protected=True)
    s.close()

    # Rebuild the entities table without the new columns, exactly as it
    # would have looked before this migration shipped.
    con = _sql.connect(s.db_path)
    con.executescript("""
        CREATE TABLE entities_legacy (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            path TEXT,
            name TEXT NOT NULL,
            tldr TEXT,
            meta TEXT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            UNIQUE(kind, name)
        );
        INSERT INTO entities_legacy (id, kind, path, name, tldr, meta, created_at, updated_at)
            SELECT id, kind, path, name, tldr, meta, created_at, updated_at FROM entities;
        DROP INDEX IF EXISTS idx_entities_protected;
        DROP INDEX IF EXISTS idx_entities_noise;
        DROP TABLE entities;
        ALTER TABLE entities_legacy RENAME TO entities;
        CREATE INDEX IF NOT EXISTS idx_entities_kind ON entities(kind);
        CREATE INDEX IF NOT EXISTS idx_entities_path ON entities(path);
    """)
    con.commit()
    con.close()

    # Reopen — should ALTER in the missing columns and indexes.
    s2 = Store(tmp_path / ".refmatrix")
    e = s2.get_entity_by_id(cid)
    assert e is not None
    # protected was lost in the legacy round-trip (column didn't exist), but
    # the new column should default to 0 — that's the documented behavior.
    assert e.protected is False
    assert e.noise is False
    # And the column is real now: re-set protected and verify it sticks.
    s2.upsert_entity(kind="concept", name="legacy_concept", protected=True)
    assert s2.get_entity_by_id(cid).protected is True
    s2.close()


def test_telemetry_logs_record(tmp_path):
    from refmatrix.telemetry import log_query, read_log, summarize

    s = Store(tmp_path / ".refmatrix")
    s.init()
    with log_query(s, kind="dsl", body="defines:foo", source="query") as t:
        t.cardinality = 3
    rows = read_log(s)
    assert len(rows) == 1
    r = rows[0]
    assert r["kind"] == "dsl"
    assert r["body"] == "defines:foo"
    assert r["cardinality"] == 3
    assert r["error"] is None
    assert isinstance(r["latency_ms"], int)
    summary = summarize(s)
    assert summary["total"] == 1
    assert summary["zero_result_count"] == 0
    s.close()


def test_telemetry_records_errors(tmp_path):
    from refmatrix.telemetry import log_query, read_log

    s = Store(tmp_path / ".refmatrix")
    s.init()
    try:
        with log_query(s, kind="dsl", body="bad query", source="query"):
            raise ValueError("simulated parse error")
    except ValueError:
        pass
    rows = read_log(s)
    assert len(rows) == 1
    assert "ValueError" in rows[0]["error"]
    s.close()


def test_telemetry_disabled_by_env(tmp_path, monkeypatch):
    from refmatrix.telemetry import log_query, read_log

    s = Store(tmp_path / ".refmatrix")
    s.init()
    monkeypatch.setenv("REFMATRIX_NO_TELEMETRY", "1")
    with log_query(s, kind="dsl", body="x", source="query") as t:
        t.cardinality = 0
    assert read_log(s) == []
    s.close()


def test_telemetry_top_queried_skips_dsl_bodies(tmp_path):
    from refmatrix.telemetry import log_query, top_queried_concepts

    s = Store(tmp_path / ".refmatrix")
    s.init()
    # `context` calls — counted
    with log_query(s, kind="context", body="parser", source="context") as t:
        t.cardinality = 5
    with log_query(s, kind="context", body="parser", source="context") as t:
        t.cardinality = 5
    with log_query(s, kind="neighbors", body="parser", source="neighbors") as t:
        t.cardinality = 7
    # DSL — should be skipped
    with log_query(s, kind="dsl", body="defines:parser AND mentions:parser",
                   source="query") as t:
        t.cardinality = 0
    rows = top_queried_concepts(s)
    assert ("parser", 3) in rows
    bodies = [b for b, _ in rows]
    assert "defines:parser AND mentions:parser" not in bodies
    s.close()


def test_sync_writes_log_line(tmp_path):
    from refmatrix.sync import sync_files

    proj = tmp_path / "proj"
    proj.mkdir()
    f = proj / "a.py"
    f.write_text("x")
    s = Store(tmp_path / ".refmatrix")
    s.init()
    sync_files(s, [str(f)], project_root=proj)
    log = (s.root / "sync.log").read_text()
    assert "+1" in log
    assert "paths=1" in log
    s.close()


# --- protected & noise round-trip ------------------------------------------


def test_add_concept_protected_survives_vacuum(store):
    pinned = store.add_concept("pinned_thing", protected=True)
    floats = store.add_concept("just_added")
    out = store.vacuum()
    assert out["concepts_dropped"] >= 1
    assert store.get_entity_by_id(pinned) is not None
    assert store.get_entity_by_id(floats) is None


def test_link_protect_pins_both_endpoints(store):
    cid = store.add_concept("auto", protected=False)
    eid = store.upsert_entity(kind="code", name="auto.py", protected=False)
    store.link("defines", cid, eid, protect=True)
    assert store.get_entity_by_id(cid).protected
    assert store.get_entity_by_id(eid).protected


def test_auto_ingest_does_not_lower_protected_flag(store):
    cid = store.add_concept("user_marked", protected=True)
    # Auto-ingester re-touches by calling add_concept with default protected=False.
    store.add_concept("user_marked", description="re-described", protected=False)
    assert store.get_entity_by_id(cid).protected


def test_query_excludes_noise_concepts_by_default(store):
    from refmatrix.query import QueryEngine
    entities = [store.upsert_entity(kind="code", name=f"f{i}.py") for i in range(3)]
    rare = store.add_concept("noisy_thing")
    store.link("mentions", rare, entities[0])
    # Manually flag as noise (skip prune_noise namespace gating).
    store._connect().execute("UPDATE entities SET noise=1 WHERE id=?", (rare,))
    store._connect().commit()

    cleaned = QueryEngine(store, include_noise=False)
    full = QueryEngine(store, include_noise=True)
    # neighbors() should skip the noise concept in expansion. The frontier walk
    # starts from a non-noise concept; we add a non-noise sibling for the test.
    other = store.add_concept("clean_thing")
    store.link("mentions", other, entities[0])
    # co_occurrence: cleaned should drop noisy_thing from the candidates.
    co_clean = cleaned.co_occurrence("clean_thing", linkage="mentions")
    co_full = full.co_occurrence("clean_thing", linkage="mentions")
    co_clean_names = {n for n, _ in co_clean}
    co_full_names = {n for n, _ in co_full}
    assert "noisy_thing" not in co_clean_names
    assert "noisy_thing" in co_full_names


def test_primer_excludes_noise_by_default(store):
    e = store.upsert_entity(kind="code", name="x.py")
    sym = store.add_concept("good_symbol_name")
    noisy = store.add_concept("bad_symbol_name")
    store.link("mentions", sym, e)
    store.link("mentions", noisy, e)
    store._connect().execute("UPDATE entities SET noise=1 WHERE id=?", (noisy,))
    store._connect().commit()
    cleaned = build_primer(store, top_n=10, max_tokens=500, min_refs=1)
    full = build_primer(store, top_n=10, max_tokens=500, min_refs=1,
                        include_noise=True)
    assert "good_symbol_name" in cleaned
    assert "bad_symbol_name" not in cleaned
    assert "bad_symbol_name" in full


def test_match_concepts_skips_noise_by_default(store):
    store.add_concept("Foo")
    noisy = store.add_concept("Bar")
    store._connect().execute("UPDATE entities SET noise=1 WHERE id=?", (noisy,))
    store._connect().commit()
    cleaned = match_concepts(store, ["Foo", "Bar"])
    full = match_concepts(store, ["Foo", "Bar"], include_noise=True)
    assert "Foo" in cleaned
    assert "Bar" not in cleaned
    assert "Bar" in full


def test_export_import_roundtrips_protected_and_noise(tmp_path, store):
    cid = store.add_concept("pinned", protected=True)
    e = store.upsert_entity(kind="code", name="x.py")
    store.link("mentions", cid, e)
    noisy = store.add_concept("flagged")
    store._connect().execute("UPDATE entities SET noise=1 WHERE id=?", (noisy,))
    store._connect().commit()
    store.close()

    monkey_root = tmp_path / "out.json"
    runner = CliRunner()
    import os
    os.environ["REFMATRIX_ROOT"] = str(store.root)
    try:
        r1 = runner.invoke(cli_main, ["export", "-o", str(monkey_root)])
        assert r1.exit_code == 0, r1.output

        # Import into a fresh store.
        new_root = tmp_path / "new.refmatrix"
        Store(new_root).init()
        os.environ["REFMATRIX_ROOT"] = str(new_root)
        r2 = runner.invoke(cli_main, ["import", str(monkey_root)])
        assert r2.exit_code == 0, r2.output

        s2 = Store(new_root)
        pin2 = s2.get_entity("concept", "pinned")
        flag2 = s2.get_entity("concept", "flagged")
        assert pin2 is not None and pin2.protected
        assert flag2 is not None and flag2.noise
        s2.close()
    finally:
        os.environ.pop("REFMATRIX_ROOT", None)
