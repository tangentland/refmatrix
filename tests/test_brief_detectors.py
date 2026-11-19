"""`rmx memory brief` detectors — what the corpus knows, and what it lacks.

RED first for task 8.1 (plan-8). `memory compile` says what the store HAS;
nothing said what it LACKS, and every coverage failure this project hit was
invisible from inside the store until a benchmark or an audit went looking:
43-83% of entities carrying no terms, 179 docs stranded by an mtime gate, a
helix log too self-suppressed to decide anything.

A brief is a DERIVED row over signal that already exists. The contract these
tests enforce:

  * Every brief carries `evidence` — entity ids a reader can resolve. A brief
    with no evidence is a bug, and the constructor refuses it. That is the one
    rule that keeps this a diagnostic rather than a generator of plausible
    sentences.
  * Detectors are deterministic, and their thresholds are parameters. A fixture
    driven to two different outcomes by two different thresholds proves the
    knob is real rather than decorative.
  * Operational rows (session/*, digest/*) never enter. They are per-session
    artifacts, not knowledge, and they are numerous enough to dominate every
    class. `consolidate` already excludes them with a constant and a regex, and
    `brief` must REUSE those rather than redeclare them — the same junk-token
    bug appeared at four call sites because each one grew its own copy.
  * Skips are counted. `feedback_no_silent_failures` applies here: an
    unembedded or unreadable row is reported, never quietly dropped.
  * The plan-derived classes are reached through the WIRING (T0.5 R5.1, ch-bsd
    plan-8 r5 #b-2): the "every class" test builds its plan with the real
    `consolidate.compile_memories` over a seeded store and hands it to
    `compile_briefs`. Before T0.5 that test passed no plan, so `corroborated`
    and `singleton` sat in `classes_not_run` and mutation C1 (corroborated's
    call replaced by `[]`) left the whole file green.
  * `brief` exports nothing production never reaches (T0.5 R5.2 / AC-5.3,
    ruling O2): `parse_gmd` / `_parse_evidence` were deleted under plan-6 Q1's
    rule, and a no-dead-exports guard pins it.
"""
from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pytest

from refmatrix import brief, consolidate
from refmatrix.store import Store

import importlib.util  # noqa: E402

# Skip ONLY when lance is not installed; an installed-but-broken lance fails
# here instead of skipping (ch-bsd r8 #s-4).
if importlib.util.find_spec("lance") is None:
    pytest.skip("lance not installed", allow_module_level=True)
import lance  # noqa: E402,F401

PART = "memory-proj"
DIM = 8


def _unit(*components: float) -> np.ndarray:
    v = np.zeros(DIM, dtype="float32")
    for i, c in enumerate(components):
        v[i] = c
    return v / (np.linalg.norm(v) or 1.0)


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("RMX_BACKEND", "sqlite")
    root = tmp_path / "proj" / ".refmatrix"
    root.mkdir(parents=True)
    s = Store(root)
    s.init()
    yield s
    s.close()


# A memory set the REAL `consolidate.compile_memories` clusters at its DEFAULT knobs (the
# knobs `memory brief --compile` and the verb's `compile=True` plan with): four near-parallel
# vectors written on four distinct authored days (one subject, corroborated) and fourteen
# mutually orthogonal rows (each joins no subject: singletons). Fourteen, so the four's six
# pairs are under 5% of the 153 and the 95th-percentile auto threshold lands at 0.0 -- with
# fewer it climbs to ~0.9997 and the cluster rests on float noise. No `mentions`: the concept
# leg stays empty and cannot weld the singletons together. Plus three memories with NO
# vector (bsd-t05 r1 #b-1): `compile_memories` clusters embedded rows only, so these join no
# subject and are not in the plan's `unclustered` either; a brief must COUNT them
# (`skipped_by["unembedded"]`), never let them vanish between `stats.memories` and the briefs.
SUBJECT = ("corr-0", "corr-1", "corr-2", "corr-3")
SUBJECT_DAYS = ("2026-10-01", "2026-10-03", "2026-10-05", "2026-10-07")
LONERS = tuple(f"lone-{j}" for j in range(14))
UNEMBEDDED = ("unemb-0", "unemb-1", "unemb-2")
SEED_DIM = 32


def _seed_vec(*components: float) -> np.ndarray:
    v = np.zeros(SEED_DIM, dtype="float32")
    for i, c in enumerate(components):
        v[i] = c
    return v / (np.linalg.norm(v) or 1.0)


def seed_compilable(s: Store, part: str) -> dict[str, int]:
    """Write `SUBJECT` + `LONERS` with vectors and `UNEMBEDDED` without into `part`; returns
    name -> id. Shared with tests/test_brief_real_daemon.py and
    tests/test_read_path_partition_and_budget.py, whose stores get the same corpus."""
    ids: dict[str, int] = {}
    vecs: dict[str, np.ndarray] = {}
    with s.with_partition(part):
        for i, (name, day) in enumerate(zip(SUBJECT, SUBJECT_DAYS)):
            ids[name] = s.add_memory(name, f"the daemon owns the catalog, take {i}",
                                     mtype="project", metadata={"created": day})
            vecs[name] = _seed_vec(1.0, 0.02 * (i + 1))
        for j, name in enumerate(LONERS):
            ids[name] = s.add_memory(name, f"an unrelated note {j}", mtype="project",
                                     metadata={"created": "2026-10-02"})
            vecs[name] = _seed_vec(*([0.0] * (2 + j) + [1.0]))
        s.upsert_vector([ids[n] for n in vecs], np.vstack([vecs[n] for n in vecs]),
                        kind="memory", dim=SEED_DIM)
        for name in UNEMBEDDED:
            ids[name] = s.add_memory(name, f"a note nobody embedded ({name})", mtype="project",
                                     metadata={"created": "2026-10-09"})
        s.flush_fragments()
    return ids


@pytest.fixture
def compiled(store):
    """`store` seeded with `seed_compilable`, plus the plan the REAL `compile_memories` builds
    over it at its default knobs. No hand-written plan (T0.5 R5.1)."""
    ids = seed_compilable(store, PART)
    with store.with_partition(PART):
        plan = consolidate.compile_memories(store)
    return store, ids, plan


# ── the evidence contract ──────────────────────────────────────────────────

def test_a_brief_without_evidence_cannot_be_constructed():
    """The rule that keeps this a diagnostic and not a sentence generator."""
    with pytest.raises(ValueError):
        brief.Brief(cls="singleton", label="x", finding="y", evidence=[])


def test_a_brief_keeps_its_evidence_ids_and_its_class():
    b = brief.Brief(cls="singleton", label="x", finding="y", evidence=[7, 9])
    assert b.evidence == [7, 9]
    assert b.cls == "singleton"


# ── corroborated ───────────────────────────────────────────────────────────

def _cluster(label, members, ids):
    return {"label": label, "size": len(members),
            "members": [{"id": ids[m], "name": m, "mtype": "project"}
                        for m in members],
            "evidence": []}


def test_corroborated_fires_on_a_subject_spanning_several_dates(store):
    ids = {n: i for i, n in enumerate(["a", "b", "c", "d"], start=100)}
    plan = {"clusters": [_cluster("daemon-writes", ["a", "b", "c", "d"], ids)],
            "unclustered": [], "stats": {}}
    dates = {100: 1.0, 101: 200000.0, 102: 400000.0, 103: 600000.0}
    out = brief.corroborated(plan, dates=dates, min_members=3, min_dates=3)
    assert [b.label for b in out] == ["daemon-writes"]
    assert sorted(out[0].evidence) == [100, 101, 102, 103]


def test_corroborated_does_not_fire_when_every_member_lands_on_one_day(store):
    """Four memories written in one sitting are one observation, not four."""
    ids = {n: i for i, n in enumerate(["a", "b", "c", "d"], start=100)}
    plan = {"clusters": [_cluster("daemon-writes", ["a", "b", "c", "d"], ids)],
            "unclustered": [], "stats": {}}
    same_day = {i: 1000.0 + i for i in ids.values()}
    assert brief.corroborated(plan, dates=same_day, min_members=3,
                              min_dates=3) == []


def test_corroborated_thresholds_are_real_knobs(store):
    ids = {n: i for i, n in enumerate(["a", "b"], start=100)}
    plan = {"clusters": [_cluster("small", ["a", "b"], ids)],
            "unclustered": [], "stats": {}}
    dates = {100: 1.0, 101: 400000.0}
    assert brief.corroborated(plan, dates=dates, min_members=3, min_dates=2) == []
    assert len(brief.corroborated(plan, dates=dates, min_members=2,
                                  min_dates=2)) == 1


# ── singleton ──────────────────────────────────────────────────────────────

def test_singleton_fires_on_a_memory_that_joined_no_cluster(store):
    plan = {"clusters": [], "unclustered": ["lonely-note"], "stats": {}}
    out = brief.singleton(plan, name_to_id={"lonely-note": 42})
    assert [b.label for b in out] == ["lonely-note"]
    assert out[0].evidence == [42]


def test_singleton_does_not_fire_on_a_clustered_memory(store):
    ids = {"a": 1, "b": 2}
    plan = {"clusters": [_cluster("pair", ["a", "b"], ids)],
            "unclustered": [], "stats": {}}
    assert brief.singleton(plan, name_to_id=ids) == []


def test_a_singleton_whose_id_cannot_be_resolved_is_counted_not_emitted(store):
    """An unresolvable name would produce a brief with no evidence."""
    plan = {"clusters": [], "unclustered": ["ghost"], "stats": {}}
    out, skipped, why = brief.singleton(plan, name_to_id={}, count_skips=True)
    assert out == []
    assert skipped == 1
    # The reason travels with the count, so `compile_briefs` can balance its
    # breakdown against its total (ch-bsd r4 #s-2-r4).
    assert why == {"singleton_unresolved": 1}, why


# ── contradicted ───────────────────────────────────────────────────────────

def test_contradicted_fires_on_an_unresolved_pair(store):
    with store.with_partition(PART):
        a = store.add_memory("claim-a", "the fix is X", mtype="project")
        b = store.add_memory("claim-b", "the fix is not X", mtype="project")
        store.link("contradicts", a, b)
        out = brief.contradicted(store)
    assert len(out) == 1
    assert sorted(out[0].evidence) == sorted([a, b])


def test_contradicted_does_not_fire_when_one_side_is_superseded(store):
    """A contradiction someone already resolved is history, not a finding."""
    with store.with_partition(PART):
        a = store.add_memory("claim-a", "the fix is X", mtype="project")
        b = store.add_memory("claim-b", "the fix is not X", mtype="project")
        store.link("contradicts", a, b)
        store.add_linkage_type("supersedes")
        store.link("supersedes", b, a)
        out = brief.contradicted(store)
    assert out == []


def test_contradicted_ignores_operational_rows(store):
    with store.with_partition(PART):
        a = store.add_memory("session-1", "a handoff", mtype="session/digest")
        b = store.add_memory("session-2", "another handoff", mtype="session/digest")
        store.link("contradicts", a, b)
        out = brief.contradicted(store)
    assert out == []


# ── orphan-concept ─────────────────────────────────────────────────────────

def test_orphan_concept_fires_on_a_term_talked_about_but_never_pinned_down(store):
    with store.with_partition(PART):
        c = store.add_concept("fast-exit")
        for i in range(4):
            m = store.add_memory(f"m{i}", f"mentions fast-exit {i}", mtype="project")
            store.link("mentions", c, m)
        out = brief.orphan_concept(store, min_mentions=3)
        # add_concept canonicalises the name; the brief must carry whatever
        # the store stored, not the string the caller typed.
        canonical = store.get_entity_by_id(c).name
    assert [b.label for b in out] == [canonical]
    assert len(out[0].evidence) >= 1


def test_orphan_concept_does_not_fire_when_something_defines_the_term(store):
    with store.with_partition(PART):
        c = store.add_concept("fast-exit")
        for i in range(4):
            m = store.add_memory(f"m{i}", f"mentions fast-exit {i}", mtype="project")
            store.link("mentions", c, m)
        anchor = store.add_memory("spec", "fast-exit is defined thus", mtype="project")
        store.link("defines", c, anchor)
        out = brief.orphan_concept(store, min_mentions=3)
    assert out == []


def test_orphan_concept_threshold_is_a_real_knob(store):
    with store.with_partition(PART):
        c = store.add_concept("rare-term")
        for i in range(2):
            m = store.add_memory(f"m{i}", "mentions rare-term", mtype="project")
            store.link("mentions", c, m)
        assert brief.orphan_concept(store, min_mentions=3) == []
        assert len(brief.orphan_concept(store, min_mentions=2)) == 1


# ── the shared exclusions ──────────────────────────────────────────────────

def test_brief_reuses_consolidates_exclusion_constants_rather_than_copying_them():
    """The same junk-token bug appeared at four call sites because each grew
    its own copy of the list. One definition, EXTENDED — never re-typed.

    Identity no longer holds because `brief/*` was added (ch-bsd r1 #b-4: a
    saved brief re-entered its own corpus). Superset is the invariant that
    survives that: every consolidate exclusion must still be here, sourced
    rather than copied.
    """
    assert set(consolidate.DEFAULT_EXCLUDE_MTYPES) <= set(brief.EXCLUDE_MTYPES)
    assert brief.OPERATIONAL_RE is consolidate._OPERATIONAL_RE
    # and the shared stoplist, by identity — the sixth-site fix
    from refmatrix import terms
    assert brief.STOPWORDS is terms.STOPWORDS


# ── the whole run ──────────────────────────────────────────────────────────

def test_compile_brief_returns_every_class_and_a_reconciled_skip_count(compiled):
    """All FOUR classes, from a plan the real `compile_memories` built (T0.5 R5.1, AC-5.1).

    This test used to pass no plan and assert two classes, so `corroborated` and `singleton`
    were never reached and mutation C1 survived (ch-bsd plan-8 r5 #b-2). Each class is pinned
    to the rows that must produce it, so a detector whose call is replaced by `[]` (C1-C4)
    fails here by name."""
    store, ids, plan = compiled
    assert [sorted(m["name"] for m in c["members"]) for c in plan["clusters"]] == \
        [sorted(SUBJECT)], f"the seed no longer clusters as designed: {plan['stats']}"
    with store.with_partition(PART):
        c = store.add_concept("orphan-term")
        for i in range(4):
            m = store.add_memory(f"om{i}", "about orphan-term", mtype="project")
            store.link("mentions", c, m)
        a = store.add_memory("claim-a", "X", mtype="project")
        b = store.add_memory("claim-b", "not X", mtype="project")
        store.link("contradicts", a, b)
        orphan = store.get_entity_by_id(c).name   # add_concept canonicalises the name
        result = brief.compile_briefs(store, plan=plan, min_mentions=3)
    by_cls: dict = {}
    for br in result["briefs"]:
        by_cls.setdefault(br.cls, []).append(br)
    assert set(by_cls) == {"corroborated", "singleton", "contradicted", "orphan-concept"}, (
        sorted(by_cls), result["stats"].get("classes_not_run"))
    assert result["stats"]["classes_not_run"] == {}, result["stats"]["classes_not_run"]
    assert [sorted(br.evidence) for br in by_cls["corroborated"]] == \
        [sorted(ids[n] for n in SUBJECT)]
    assert sorted(br.label for br in by_cls["singleton"]) == sorted(LONERS)
    assert [sorted(br.evidence) for br in by_cls["contradicted"]] == [sorted([a, b])]
    assert [br.label for br in by_cls["orphan-concept"]] == [orphan]
    # A caller-supplied plan counts the rows it could not cluster, like the compiling op
    # (bsd-t05 r1 #b-1): the three unembedded memories are skipped WITH a reason.
    assert result["stats"]["skipped_by"].get("unembedded") == len(UNEMBEDDED), result["stats"]
    assert result["stats"]["skipped"] == sum(result["stats"]["skipped_by"].values())
    assert isinstance(result["stats"]["skipped"], int)


def test_a_class_that_did_not_run_says_how_to_run_it(store):
    """bsd-t05 r1 #m-2: the hint for a plan-derived class that did not run names the switch
    that runs it (`compile=true`, CLI `--compile`) or a caller plan (`plan=`). It used to say
    "or run `rmx memory compile` first", which does nothing for a brief: no op reads a stored
    plan."""
    hint = brief.compile_briefs(store)["stats"]["classes_not_run"]["corroborated"]
    assert ("compile=true" in hint.lower() and "--compile" in hint and "plan=" in hint
            and "rmx memory compile` first" not in hint), hint


def test_every_emitted_brief_has_evidence_that_resolves_to_a_real_row(store):
    with store.with_partition(PART):
        c = store.add_concept("orphan-term")
        for i in range(4):
            m = store.add_memory(f"om{i}", "about orphan-term", mtype="project")
            store.link("mentions", c, m)
        result = brief.compile_briefs(store, min_mentions=3)
        for b in result["briefs"]:
            assert b.evidence, b
            for eid in b.evidence:
                assert store.get_entity_by_id(eid) is not None, (b, eid)


def test_operational_memories_never_appear_in_any_class(store):
    with store.with_partition(PART):
        c = store.add_concept("session-term")
        for i in range(5):
            m = store.add_memory(f"session-{i}", "a handoff", mtype="session/digest")
            store.link("mentions", c, m)
        result = brief.compile_briefs(store, min_mentions=2)
    for b in result["briefs"]:
        for eid in b.evidence:
            ent = store.get_entity_by_id(eid)
            assert not str(ent.name).startswith("session-"), b


# ── no dead exports (T0.5 R5.2 / AC-5.3, ruling O2) ────────────────────────

REPO = Path(__file__).resolve().parents[1]
BRIEF_PY = REPO / "src" / "refmatrix" / "brief.py"

# Every function of `brief.py` that code OUTSIDE it in `src/` calls, each with the caller that
# makes it production. The guard computes this set from `src/` and requires it to EQUAL the
# list, so the list cannot exempt dead code: a name here that lost its caller fails, and a new
# external caller has to be written down with its reason.
ENTRY_POINTS = {
    "compile_briefs": "daemon `_op_memory_brief` derives every brief through it (the verb, "
                      "the CLI and MCP all reach it there)",
    "render_gmd": "CLI `rmx memory brief --gmd` renders the index with it",
}


def _brief_aliases(tree: ast.AST) -> tuple[set, set]:
    """Names a caller binds to the module (`from refmatrix import brief as brief_mod`,
    `import refmatrix.brief as b`), and names it imports from it directly."""
    aliases: set = set()
    direct: set = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name == "refmatrix.brief" and a.asname:
                    aliases.add(a.asname)
        elif isinstance(node, ast.ImportFrom):
            if node.module == "refmatrix":
                aliases |= {a.asname or a.name for a in node.names if a.name == "brief"}
            elif node.module == "refmatrix.brief":
                direct |= {a.name for a in node.names}
    return aliases, direct


_DEFS = (ast.FunctionDef, ast.AsyncFunctionDef)


def _refs(trees) -> tuple[set, set]:
    """(Names, attribute names) used anywhere under `trees`."""
    names: set = set()
    attrs: set = set()
    for t in trees:
        for n in ast.walk(t):
            if isinstance(n, ast.Name):
                names.add(n.id)
            elif isinstance(n, ast.Attribute):
                attrs.add(n.attr)
    return names, attrs


def dead_brief_functions(brief_src: str, caller_srcs: list[str]) -> tuple[list, set]:
    """`(dead, roots)`: what in `brief_src` nothing in `caller_srcs` reaches, and the functions
    the callers name directly (the roots).

    The graph's nodes are module-level functions, classes, each METHOD of a class (as
    `Class.method`), and module-level bindings (`X = ...`). A walk starts at the callers' roots
    and at module-level statements that are not bindings (they run on import), and follows the
    Names each reached node uses. A private helper reached only from a dead function is dead too:
    that is how `_parse_evidence` was named beside `parse_gmd`. bsd-t05 r1 #m-3 closed two blind
    spots of the first version:
    - a reached class no longer reaches every method: a method is reached when the class is and
      it is a dunder, or its name is used as an attribute by production code or by a reached
      node (B1: a dead `_Reader.from_gmd` kept its helper alive);
    - a module-level binding's right-hand side is walked only when the binding itself is
      reached (B2: an unread `_FORMATS = {"gmd": parse_gmd}` kept `parse_gmd` alive)."""
    tree = ast.parse(brief_src)
    body: dict = {}          # node key -> the subtrees its references come from
    funcs: set = set()
    classes: set = set()
    methods: dict = {}       # "Class.method" -> (class name, method name)
    on_import: list = []
    for st in tree.body:
        if isinstance(st, _DEFS):
            funcs.add(st.name)
            body.setdefault(st.name, []).append(st)
        elif isinstance(st, ast.ClassDef):
            classes.add(st.name)
            body.setdefault(st.name, []).extend(
                [*st.decorator_list, *st.bases, *st.keywords,
                 *(b for b in st.body if not isinstance(b, _DEFS))])
            for b in st.body:
                if isinstance(b, _DEFS):
                    key = f"{st.name}.{b.name}"
                    methods[key] = (st.name, b.name)
                    body[key] = [b]
        elif isinstance(st, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = st.targets if isinstance(st, ast.Assign) else [st.target]
            for t in targets:
                for n in ast.walk(t):
                    if isinstance(n, ast.Name):
                        body.setdefault(n.id, []).extend([st.value] if st.value else [])
        else:
            on_import.append(st)
    roots: set = set()
    attrs: set = set()
    for src in caller_srcs:
        t = ast.parse(src)
        aliases, direct = _brief_aliases(t)
        roots |= direct
        roots |= {n.attr for n in ast.walk(t) if isinstance(n, ast.Attribute)
                  and isinstance(n.value, ast.Name) and n.value.id in aliases}
        attrs |= _refs([t])[1]
    reached: set = set()
    todo = list(roots | _refs(on_import)[0])
    while True:
        while todo:
            key = todo.pop()
            if key in reached or key not in body:
                continue
            reached.add(key)
            names, used = _refs(body[key])
            attrs |= used
            todo += [n for n in names if n in body and n not in reached]
        todo = [k for k, (cls, m) in methods.items() if k not in reached and cls in reached
                and ((m.startswith("__") and m.endswith("__")) or m in attrs)]
        if not todo:
            break
    return sorted((funcs | classes | set(methods)) - reached), roots & funcs


def _src_callers() -> list[str]:
    return [p.read_text() for p in sorted((REPO / "src").rglob("*.py")) if p != BRIEF_PY]


def test_brief_exports_no_function_production_never_calls():
    """AC-5.3: every function in `brief.py` is reached from `src/`, and the set `src/` calls
    from outside is exactly `ENTRY_POINTS`. At `b2bf3c36` this named `parse_gmd` and
    `_parse_evidence` (the store <- GMD direction, no production caller; ruling O2)."""
    dead, roots = dead_brief_functions(BRIEF_PY.read_text(), _src_callers())
    assert not dead, (f"brief.py functions no production path reaches (plan-6 Q1: delete them, "
                      f"or name the caller in ENTRY_POINTS): {dead}")
    assert roots == set(ENTRY_POINTS), (
        f"src/ calls {sorted(roots)} from outside brief.py; ENTRY_POINTS declares "
        f"{sorted(ENTRY_POINTS)}")
    assert all(why.strip() for why in ENTRY_POINTS.values())


def test_the_dead_export_guard_names_a_planted_dead_function():
    """Rule 5's must-fail cases, each planted into the REAL `brief.py`:
    - M5.3: a `parse_gmd` stub with a private helper only it calls -- both named;
    - B1 (bsd-t05 r1 #m-3): a dead method of a class production DOES reach, and the helper only
      that method calls -- both named (the first guard counted every name inside a reached class
      as reached);
    - B2 (#m-3): `parse_gmd` named only in a module-level dict nothing reads -- named (the first
      guard seeded the walk from every module-level statement);
    and, as the control, a planted function and a planted class some caller reaches are not."""
    planted = BRIEF_PY.read_text() + (
        "\n\ndef parse_gmd(doc):\n    return _planted_helper(doc)\n"
        "\n\ndef _planted_helper(doc):\n    return [doc]\n"
        "\n\ndef planted_live(x):\n    return x\n")
    caller = "from refmatrix import brief as bm\nbm.planted_live(1)\n"
    dead, roots = dead_brief_functions(planted, _src_callers() + [caller])
    assert "parse_gmd" in dead and "_planted_helper" in dead, dead
    assert "planted_live" not in dead and "planted_live" in roots, (dead, roots)

    b1 = BRIEF_PY.read_text() + (
        "\n\nclass _PlantedReader:\n"
        "    def __init__(self, doc):\n        self.doc = doc\n"
        "    def planted_read(self):\n        return self.doc\n"
        "    def planted_from_gmd(self):\n        return _planted_method_helper(self.doc)\n"
        "\n\ndef _planted_method_helper(doc):\n    return [doc]\n")
    caller = "from refmatrix import brief as bm\nbm._PlantedReader('x').planted_read()\n"
    dead, _roots = dead_brief_functions(b1, _src_callers() + [caller])
    assert "_PlantedReader.planted_from_gmd" in dead, dead
    assert "_planted_method_helper" in dead, dead
    assert "_PlantedReader" not in dead and "_PlantedReader.planted_read" not in dead, dead
    assert "_PlantedReader.__init__" not in dead, dead

    b2 = BRIEF_PY.read_text() + (
        "\n\ndef parse_gmd(doc):\n    return [doc]\n"
        "\n\n_PLANTED_FORMATS = {\"gmd\": parse_gmd}\n")
    dead, _roots = dead_brief_functions(b2, _src_callers())
    assert "parse_gmd" in dead, dead
