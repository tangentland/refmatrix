"""`rmx memory compile` — dense⊕concept fusion, labeling, apply idempotence.

The signal under test is a synthesis: dense cosine sets the topology, concept
overlap confirms dense pairs and adds bridges dense missed. The fixtures below
are built so each half is provably load-bearing — one pair groups ONLY via
vectors (no shared concept), another groups ONLY via a shared rare concept
(orthogonal vectors). A regression that drops either half fails a test rather
than quietly producing worse clusters.
"""
from __future__ import annotations

import numpy as np
import pytest

from refmatrix import consolidate
from refmatrix.store import Store

pytest.importorskip("lance")

PART = "memory-proj"
DIM = 8


def _unit(*components: float) -> np.ndarray:
    v = np.zeros(DIM, dtype="float32")
    for i, c in enumerate(components):
        v[i] = c
    n = np.linalg.norm(v)
    return v / (n or 1.0)


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("RMX_BACKEND", "sqlite")
    root = tmp_path / "proj" / ".refmatrix"
    root.mkdir(parents=True)
    s = Store(root)
    s.init()
    yield s
    s.close()


def _seed(s: Store) -> dict[str, int]:
    """Six memories in three deliberate shapes.

    paraphrase-a/b : near-identical vectors, ZERO shared concepts  -> dense only
    bridge-a/b     : orthogonal vectors, shared rare concept `jetsam` -> bridge
    hubbed-a/b     : share only the corpus-wide hub concept `rmx`  -> no edge
    """
    ids: dict[str, int] = {}
    with s.with_partition(PART):
        rmx = s.add_concept("rmx")           # hub: mentioned by everything
        jetsam = s.add_concept("jetsam")     # rare: exactly the bridge pair
        embed = s.add_concept("embedder")
        lance_c = s.add_concept("lance")

        spec = [
            ("paraphrase-a", "the daemon dies under load", [rmx, embed]),
            ("paraphrase-b", "process killed when memory grows", [rmx, lance_c]),
            ("bridge-a", "jetsam killed the resident model", [rmx, jetsam]),
            ("bridge-b", "watchdog restarts after jetsam", [rmx, jetsam]),
            ("hubbed-a", "unrelated note about tables", [rmx]),
            ("hubbed-b", "another unrelated note", [rmx]),
        ]
        vecs = {
            "paraphrase-a": _unit(1.0, 0.05),
            "paraphrase-b": _unit(1.0, 0.06),
            "bridge-a": _unit(0.0, 1.0),
            "bridge-b": _unit(0.0, 0.0, 1.0),
            "hubbed-a": _unit(0.0, 0.0, 0.0, 1.0),
            "hubbed-b": _unit(0.0, 0.0, 0.0, 0.0, 1.0),
        }
        for name, content, concepts in spec:
            mid = s.add_memory(name, content, mtype="project")
            ids[name] = mid
            for c in concepts:
                s.link("mentions", c, mid)
        s.upsert_vector(
            [ids[n] for n in vecs],
            np.vstack([vecs[n] for n in vecs]),
            kind="memory", dim=DIM,
        )
    return ids


def _plan(s: Store, **kw):
    defaults = dict(threshold=0.5, k=4, min_size=2, hub_df_frac=0.5,
                    bridge_min=0.35)
    defaults.update(kw)
    with s.with_partition(PART):
        return consolidate.compile_memories(s, **defaults)


# ------------------------------------------------------------- primitive ---

def test_read_vectors_round_trips_ids_and_matrix(store):
    ids = _seed(store)
    with store.with_partition(PART):
        got_ids, mat = store.read_vectors(kind="memory")
    assert sorted(got_ids) == sorted(ids.values())
    assert mat.shape == (6, DIM)
    assert mat.dtype == np.dtype("float32")


def test_read_vectors_filters_to_requested_ids(store):
    ids = _seed(store)
    want = [ids["bridge-a"], ids["bridge-b"]]
    with store.with_partition(PART):
        got_ids, mat = store.read_vectors(kind="memory", ids=want)
    assert sorted(got_ids) == sorted(want)
    assert mat.shape == (2, DIM)


def test_read_vectors_on_missing_dataset_is_empty_not_an_error(store):
    with store.with_partition(PART):
        ids, mat = store.read_vectors(kind="nonexistent")
    assert ids == [] and mat.shape == (0, 0)


# ---------------------------------------------------------------- fusion ---

def _cluster_of(plan, name):
    for c in plan["clusters"]:
        if any(m["name"] == name for m in c["members"]):
            return c
    return None


def test_dense_groups_paraphrase_with_no_shared_concept(store):
    _seed(store)
    plan = _plan(store)
    c = _cluster_of(plan, "paraphrase-a")
    assert c is not None
    assert {m["name"] for m in c["members"]} == {"paraphrase-a", "paraphrase-b"}


def test_concept_bridges_a_pair_dense_alone_would_miss(store):
    _seed(store)
    fused = _plan(store)
    dense_only = _plan(store, signal="dense")

    # Orthogonal vectors: dense cannot see this pair at all.
    assert _cluster_of(dense_only, "bridge-a") is None
    c = _cluster_of(fused, "bridge-a")
    assert c is not None
    assert {m["name"] for m in c["members"]} == {"bridge-a", "bridge-b"}
    assert fused["stats"]["bridges"] >= 1
    assert dense_only["stats"]["bridges"] == 0


def test_hub_concept_alone_never_forms_an_edge(store):
    _seed(store)
    plan = _plan(store)
    # `rmx` is in every memory -> outside the informative concept space, so
    # the two memories sharing ONLY it stay apart.
    assert _cluster_of(plan, "hubbed-a") is None
    assert "hubbed-a" in plan["unclustered"]


def test_concept_signal_alone_misses_the_paraphrase_pair(store):
    _seed(store)
    plan = _plan(store, signal="concept")
    assert _cluster_of(plan, "paraphrase-a") is None
    assert _cluster_of(plan, "bridge-a") is not None


def test_fused_edges_carry_concept_confirmation(store):
    _seed(store)
    plan = _plan(store)
    # bridge-a/bridge-b are also each other's concept-confirmed neighbours
    # only via the bridge; the confirmed counter tracks dense pairs that had
    # concept support, so it must never exceed the dense edge count.
    st = plan["stats"]
    assert st["confirmed"] + st["bridges"] <= st["edges"]


# -------------------------------------------------------------- labeling ---

def test_label_is_the_highest_lift_shared_concept(store):
    _seed(store)
    plan = _plan(store)
    c = _cluster_of(plan, "bridge-a")
    assert c["label"] == "jetsam"
    assert c["evidence"][0]["concept"] == "jetsam"
    assert c["evidence"][0]["df_in"] == 2


def test_cluster_without_a_shared_concept_is_kept_and_named_after_a_member(store):
    _seed(store)
    plan = _plan(store)
    c = _cluster_of(plan, "paraphrase-a")
    # Grouped by vectors, named by no shared concept — still kept, and still
    # honest about having no evidence.
    assert c["evidence"] == []
    # But NOT `unlabeled-N`: a positional name is unusable as an index entry.
    # Fall back to the richest member so the label is a handle back into the
    # corpus.
    assert not c["label"].startswith("unlabeled"), c["label"]
    # Compared canonically: labels are slug-formed (`-` folded to `_`), which
    # is how subject identity is derived downstream.
    def _canon(x: str) -> str:
        return x.replace("-", "_")

    member_names = {m["name"] for m in c["members"]}
    assert any(c["label"] in _canon(n) for n in member_names), (
        f"label {c['label']!r} not derived from a member of {member_names}"
    )


def test_crosscutting_excludes_hubs(store):
    _seed(store)
    plan = _plan(store)
    assert "rmx" not in {x["concept"] for x in plan["crosscutting"]}


# ---------------------------------------------------------- corpus gating ---

def test_operational_mtypes_are_excluded_by_default(store):
    _seed(store)
    with store.with_partition(PART):
        store.add_memory("session-card-1", "a session card", mtype="session")
        store.add_memory("digest-2", "a digest", mtype="session/digest")
    plan = _plan(store)
    names = {m["name"] for c in plan["clusters"] for m in c["members"]}
    assert "session-card-1" not in names
    assert "digest-2" not in names


def test_unembedded_memories_are_counted_not_silently_dropped(store):
    _seed(store)
    with store.with_partition(PART):
        store.add_memory("no-vector", "never embedded", mtype="project")
    plan = _plan(store)
    assert plan["stats"]["unembedded"] == 1
    assert plan["stats"]["embedded"] == 6


def test_empty_corpus_returns_an_empty_plan(store):
    plan = _plan(store)
    assert plan["clusters"] == [] and plan["crosscutting"] == []


# ----------------------------------------------------------------- apply ---

def test_apply_writes_subjects_and_part_of_edges(store):
    _seed(store)
    plan = _plan(store)
    with store.with_partition(PART):
        res = consolidate.apply_plan(store, plan)
        subjects = store.list_subjects()
        assert len(subjects) == len(plan["clusters"])
        assert res["linked"] == sum(c["size"] for c in plan["clusters"])
        by_label = {s["label"]: s for s in subjects}
        assert "jetsam" in by_label
        leaves = store.subject_leaves(by_label["jetsam"]["id"])
        assert {m["name"] for m in leaves} == {"bridge-a", "bridge-b"}


def test_reapply_refiles_instead_of_accreting(store):
    _seed(store)
    plan = _plan(store)
    with store.with_partition(PART):
        consolidate.apply_plan(store, plan)
        second = consolidate.apply_plan(store, plan)
        # Same subjects, same leaf counts — the prune pass unlinked exactly
        # what it re-linked. Without it, leaves would double-count.
        assert second["unlinked"] == second["linked"]
        for s in store.list_subjects():
            assert s["leaves"] == len(store.subject_leaves(s["id"]))
            assert s["leaves"] <= 2


def test_reapply_after_the_corpus_shifts_drops_the_stale_filing(store):
    _seed(store)
    with store.with_partition(PART):
        consolidate.apply_plan(store, _plan(store))
        jid = {s["label"]: s["id"] for s in store.list_subjects()}["jetsam"]
        assert len(store.subject_leaves(jid)) == 2

    # bridge-b loses the shared concept, so it must leave the subject.
    with store.with_partition(PART):
        ids = {m["name"]: m["id"] for m in store.iter_memories(limit=50)}
        store.unlink("mentions", store.add_concept("jetsam"), ids["bridge-b"])
        consolidate.apply_plan(store, _plan(store))
        remaining = {s["label"]: s for s in store.list_subjects()}
        if "jetsam" in remaining:
            leaves = {m["name"]
                      for m in store.subject_leaves(remaining["jetsam"]["id"])}
            assert "bridge-b" not in leaves


def test_hand_declared_subjects_are_never_pruned(store):
    _seed(store)
    with store.with_partition(PART):
        mine = store.upsert_subject("hand declared")
        ids = {m["name"]: m["id"] for m in store.iter_memories(limit=50)}
        store.link_part_of(ids["hubbed-a"], mine["id"])
        consolidate.apply_plan(store, _plan(store))
        leaves = store.subject_leaves(mine["id"])
        assert {m["name"] for m in leaves} == {"hubbed-a"}


# ------------------------------------------------------------------- gmd ---

def test_render_gmd_is_wellformed_and_anchored(store):
    _seed(store)
    plan = _plan(store)
    doc = consolidate.render_gmd(plan, partition=PART)
    assert doc.startswith("---\ngmd: \"0.1\"\n")
    assert "# Compiled memory subjects {#root}" in doc
    for i, _c in enumerate(plan["clusters"], 1):
        assert f"{{#subject-{i}}}" in doc
    # Container direction: the subject catalogs its leaves. Emitting part-of
    # here would claim the subject is part of its own members.
    assert "rel: catalogs -> [[bridge-a]]" in doc
    assert "rel: part-of ->" not in doc


def test_default_out_path_stays_out_of_the_memory_dir(tmp_path):
    p = consolidate.default_out_path(tmp_path / ".refmatrix")
    assert p.parent.name == "compiled"
    assert "memory" not in p.parts


# --------------------------------------------------- threshold + topology ---

def test_auto_threshold_tracks_the_corpus_not_an_absolute_cosine():
    """A narrow corpus (everything similar) must yield a HIGHER floor than a
    wide one. This is the property an absolute threshold cannot have, and its
    absence is what collapsed the real corpus into one cluster."""
    rng = np.random.default_rng(0)
    base = rng.normal(size=(1, 16))
    narrow = np.repeat(base, 40, axis=0) + rng.normal(scale=0.05, size=(40, 16))
    wide = rng.normal(size=(40, 16))
    t_narrow = consolidate.auto_threshold(narrow.astype("float32"), 95)
    t_wide = consolidate.auto_threshold(wide.astype("float32"), 95)
    assert t_narrow > t_wide


def test_auto_threshold_is_deterministic():
    rng = np.random.default_rng(1)
    m = rng.normal(size=(60, 16)).astype("float32")
    assert consolidate.auto_threshold(m, 90) == consolidate.auto_threshold(m, 90)


def test_mutual_knn_drops_the_hub_that_welds_groups_together():
    """One generic vector sitting between two tight groups lands in everyone's
    top-k. Plain kNN lets it fuse them; mutual kNN does not."""
    a = np.array([[1.0, 0.0, 0.0], [0.99, 0.14, 0.0]], dtype="float32")
    b = np.array([[0.0, 1.0, 0.0], [0.14, 0.99, 0.0]], dtype="float32")
    hub = np.array([[0.71, 0.71, 0.0]], dtype="float32")
    mat = np.vstack([a, b, hub])

    loose = consolidate._dense_knn(mat, 4, 0.5, mutual=False)
    strict = consolidate._dense_knn(mat, 1, 0.5, mutual=True)
    # index 4 is the hub; with k=1 it is nobody's mutual nearest neighbour.
    assert any(4 in key for key in loose)
    assert not any(4 in key for key in strict)
    # The two genuine pairs survive.
    assert (0, 1) in strict and (2, 3) in strict


def test_threshold_override_beats_the_percentile(store):
    _seed(store)
    plan = _plan(store, threshold=0.99, threshold_pct=50)
    assert plan["stats"]["threshold"] == 0.99
    assert plan["stats"]["threshold_auto"] is False


# ---------------------------------------------- crosscutting bridge score ---

def test_crosscutting_prefers_attested_and_concentrated_over_rare_and_wide():
    """`df * idf / (spread - 1)`: a term in many memories but only two
    subjects must outrank both a df=2 curiosity and a corpus-wide hub."""
    sets = {}
    idf = {1: 2.5, 2: 4.1, 3: 0.4}   # 1=bridge, 2=rare noise, 3=hub
    names = {1: "bridge", 2: "noise", 3: "hub"}
    clusters = [[10, 11, 12], [20, 21, 22], [30, 31, 32]]
    for eid in [10, 11, 12, 20, 21, 22]:
        sets[eid] = {1, 3}           # bridge: 6 memories, 2 clusters
    sets[30] = {3}
    sets[31] = {2, 3}
    sets[10] = {1, 2, 3}             # noise: 2 memories, 2 clusters
    for eid in [32, 21, 22, 12, 11, 20]:
        sets[eid] = sets.get(eid, set()) | {3}   # hub: everywhere

    out = consolidate._crosscutting(clusters, sets, idf, names)
    ranked = [x["concept"] for x in out]
    assert ranked[0] == "bridge"
    assert ranked.index("bridge") < ranked.index("hub")


# ------------------------------------------------- vector-claim integrity ---

def test_gc_requeues_rows_claiming_a_vector_lance_does_not_have(store):
    """The inverse dual-write leak: `vectors_updated_at` set, no vector on
    disk. `pending_embeddings` trusts the stamp, so without this the row is
    permanently invisible to dense retrieval AND to `rmx embed`.
    """
    ids = _seed(store)
    victim = ids["bridge-a"]
    with store.with_partition(PART):
        # Vector disappears (a merge remap / partial purge) but the catalog
        # still claims it.
        store._vector_store(DIM).drop_for([victim], kind="memory")
        assert victim not in store.read_vectors(kind="memory")[0]
        # Invisible to embed: the stamp still says "current".
        assert not any(e == victim for e, *_ in
                       store.pending_embeddings(kinds=["memory"]))

        res = store.gc_vectors(kinds=["memory"], dim=DIM)
        assert res["memory"]["missing"] == 1
        assert any(e == victim for e, *_ in
                   store.pending_embeddings(kinds=["memory"]))


def test_gc_dry_run_reports_missing_without_clearing_the_stamp(store):
    ids = _seed(store)
    victim = ids["bridge-b"]
    with store.with_partition(PART):
        store._vector_store(DIM).drop_for([victim], kind="memory")
        res = store.gc_vectors(kinds=["memory"], dim=DIM, dry_run=True)
        assert res["memory"]["missing"] == 1
        assert not any(e == victim for e, *_ in
                       store.pending_embeddings(kinds=["memory"]))
