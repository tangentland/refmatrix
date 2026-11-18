"""bug-216 AC-5 (R5) — `scripts/check-rel-landing.py` reproduces hand-computed categories.

Spec: workflow/plans/task-bug216-rule-docs-in-graph.md (#r5, #ac-5).

WHY. bug-216 was first diagnosed from a probe that read `entity_links` source->target and
reported "66.9% of rel: lines missing"; the real figure, recounted against the ingester's own
`linkage_evidence` rows (file + line), was 4,048 of 4,490 landed. R5 commits that recount so the
next diagnosis starts from evidence, and AC-6 measures the fix with it.

The fixture catalog is built by the REAL ingester (`ingest_gmd_paths`) on a throwaway store
under a short `/tmp` root, then the corpus is edited so every category occurs. Hand count:

  docs/a.md  4 wikilink `rel:` lines (+1 URL rel: line, not a wikilink line, not counted)
             [[b#x]]                          landed
             [[claude#no-silent-failures]]    target unresolved  (claude)
             [[project-profile#constraints]]  target unresolved  (project-profile)
             [[claude#no-workarounds]]        target unresolved  (claude)
  docs/b.md  2 lines, both landed; then 2 lines inserted above them -> landed at another line
  docs/c.md  1 line, written AFTER the ingest -> file not ingested

  authored 7 = landed 1 + landed at another line 2 + file not ingested 1 + target unresolved 3
  unresolved by target doc: claude 2, project-profile 1

Output contract assumed here (the spec says "prints"; it does not fix a format): `--json` prints
ONE JSON object with the keys in `EXPECTED`. The human-readable default is free-form.
"""
from __future__ import annotations

import rmx_sandbox  # task-29.4 #r5: test roots live under the sandbox root (short_root)
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from refmatrix.ingest_gmd import ingest_gmd_paths
from refmatrix.store import Store

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "check-rel-landing.py"
SENTINEL = "ZEBRA-QUARTZ-PROSE-216"

A_MD = f"""---
gmd: "0.1"
id: a
title: "A"
tags: [t]
---

# A {{#root}}

## Swallow {{#swallow}}

{SENTINEL} body text that must never be printed.

rel: depends-on -> [[b#x]]
rel: contradicts -> [[claude#no-silent-failures]]

## Cite {{#cite}}

Text.

rel: related-to -> [[project-profile#constraints]]
rel: amends -> [[claude#no-workarounds]]
rel: related-to -> https://example.com/not-a-wikilink
"""

B_MD = """---
gmd: "0.1"
id: b
title: "B"
tags: [t]
---

# B {#root}

Pad.

## X {#x}

Text.

rel: related-to -> [[a#swallow]]

## Y {#y}

rel: part-of -> [[#x]]
"""

C_MD = """---
gmd: "0.1"
id: c
title: "C"
tags: [t]
---

# C {#root}

## Z {#z}

rel: related-to -> [[b#x]]
"""

EXPECTED = {
    "authored": 7,
    "landed": 1,
    "landed_other_line": 2,
    "file_not_ingested": 1,
    "target_unresolved": 3,
    "unresolved_by_target_doc": {"claude": 2, "project-profile": 1},
}


def _digest(d: Path) -> dict[str, str]:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(d.iterdir()) if p.is_file()}


@pytest.fixture
def catalog():
    base = Path(rmx_sandbox.short_root("b216l")).resolve()
    proj = base / "proj"
    (proj / "docs").mkdir(parents=True)
    a, b = proj / "docs" / "a.md", proj / "docs" / "b.md"
    a.write_text(A_MD)
    b.write_text(B_MD)
    root = proj / ".refmatrix"
    root.mkdir()
    s = Store(root)
    s.init()
    try:
        stats = ingest_gmd_paths(s, [a, b])
        db = Path(s.db_path)
    finally:
        s.close()
    # Preconditions the hand count rests on: the store really holds what the count says.
    assert stats.docs == 2, stats.report()
    assert stats.rels == 3, stats.report()        # a: [[b#x]]; b: [[a#swallow]], [[#x]]
    # Drift: two lines inserted above both of b's rel: lines AFTER the ingest.
    b.write_text(B_MD.replace("Pad.\n", "Pad.\n\nInserted after the ingest.\n"))
    # Never ingested.
    (proj / "docs" / "c.md").write_text(C_MD)
    yield db, proj
    shutil.rmtree(base)


def _run(*args: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                          cwd=REPO, env=env, timeout=300)


def test_ac5_script_exists():
    assert SCRIPT.is_file(), f"{SCRIPT.relative_to(REPO)} does not exist (spec #r5)"


def test_ac5_recount_reproduces_the_hand_computed_categories(catalog):
    db, proj = catalog
    p = _run(str(db), str(proj), "--json")
    assert p.returncode == 0, p.stdout + p.stderr
    got = json.loads(p.stdout)
    assert {k: got.get(k) for k in EXPECTED} == EXPECTED, json.dumps(got, indent=1)
    assert got["authored"] == (got["landed"] + got["landed_other_line"]
                               + got["file_not_ingested"] + got["target_unresolved"])


def test_ac5_is_read_only_on_the_catalog(catalog):
    """R5: read-only on the catalog path it is given — no byte of any file in the store dir
    changes and no file (WAL, lock) appears."""
    db, proj = catalog
    before = _digest(db.parent)
    for args in ((str(db), str(proj), "--json"), (str(db), str(proj))):
        p = _run(*args)
        assert p.returncode == 0, p.stdout + p.stderr
    assert _digest(db.parent) == before


def test_ac5_prints_counts_and_paths_only(catalog):
    """R5: counts and paths only — never a doc's prose."""
    db, proj = catalog
    for args in ((str(db), str(proj), "--json"), (str(db), str(proj))):
        p = _run(*args)
        assert p.returncode == 0, p.stdout + p.stderr
        assert SENTINEL not in p.stdout + p.stderr, "doc prose reached the output"


def test_ac5_is_not_a_gate(catalog):
    """R5: 'Not a gate (line drift is benign)' — unresolved and drifted lines still exit 0."""
    db, proj = catalog
    p = _run(str(db), str(proj))
    assert p.returncode == 0, p.stdout + p.stderr


# ---------------------------------------------------------------- AC-9 (R8): binding classes
#
# Spec #r8 (rev 2, amended a306e71): a line is LANDED only when its evidence row joins a LIVE
# `entity_links` row whose two entities both still exist; an evidence row without one is STALE
# (bug-219). Every landed row is then classed by its target. Rev 3 (#ac-6-rev3) adds
# BOUND-VIA-DENOTES: a path-less concept sharing an ingested doc's name that reaches the doc by a
# `denotes` link. MISBOUND = the same concept with no such link.
#
# Assumed `--json` keys (on top of AC-5's): `stale` (int) and `binding`, a dict with
# `doc_or_memory`, `anchor_node`, `misbound`, `bound_via_denotes`, `other_concept`.
#
# The ingester writes rows 1-2 (the same at HEAD and after R6: one fresh batch). Rows 3-6 are the
# states HEAD left in live stores, written with the store API after the ingest and cited by rel:
# lines appended to a.md (appending shifts no earlier line):
#   L1 [[b-doc]]      -> B's doc                                  doc_or_memory
#   L2 [[b-doc#sec]]  -> B's sec node (path)                      anchor_node
#   L3 [[c-doc]]      -> path-less `c-doc`; c.md ingested as c-doc, no denotes   misbound
#   L4 [[d-concept]]  -> path-less `d-concept`; no doc of that id  other_concept
#   L5 [[e-doc]]      -> path-less `e-doc` -denotes-> e.md's doc  bound_via_denotes
#   L6 [[f-doc]]      -> evidence row only, no entity_links row     stale
#   authored 6 = landed 5 + stale 1

A9_HEAD = """---
gmd: "0.1"
id: a9
title: "A9"
tags: [t]
---

# A9 {#root}

## Cite {#cite}

Text.

rel: derives-from -> [[b-doc]]
rel: depends-on -> [[b-doc#sec]]
"""
A9_TAIL = ["rel: derives-from -> [[c-doc]]", "rel: derives-from -> [[d-concept]]",
           "rel: derives-from -> [[e-doc]]", "rel: related-to -> [[f-doc]]"]

EXPECTED_AC9 = {
    "authored": 6, "landed": 5, "landed_other_line": 0, "stale": 1,
    "file_not_ingested": 0, "target_unresolved": 0,
    "binding": {"doc_or_memory": 1, "anchor_node": 1, "misbound": 1,
                "bound_via_denotes": 1, "other_concept": 1},
}


def _gmd9(doc_id: str, extra: str = "") -> str:
    # title != id: a hyphenated title mints its own same-named concept (title terms)
    return (f'---\ngmd: "0.1"\nid: {doc_id}\ntitle: "Fixture document"\ntags: [t]\n---\n\n'
            f"# Fixture document {{#root}}\n\nBody.\n{extra}")


def _link9(s: Store, verb: str, c: int, e: int) -> None:
    try:
        s.get_linkage_id(verb)
    except KeyError:
        s.add_linkage_type(verb, directed=True, description=f"bug-216 fixture '{verb}'")
    s.link(verb, c, e)


@pytest.fixture
def catalog9():
    base = Path(rmx_sandbox.short_root("b216n")).resolve()
    proj = base / "proj"
    d = proj / "docs"
    d.mkdir(parents=True)
    a = d / "a9.md"
    a.write_text(A9_HEAD)
    files = {"b": _gmd9("b-doc", "\n## Sec {#sec}\n\nS.\n"), "c": _gmd9("c-doc"),
             "e": _gmd9("e-doc"), "f": _gmd9("f-doc")}
    paths = [a]
    for k, body in files.items():
        p = d / f"{k}.md"
        p.write_text(body)
        paths.append(p)
    root = proj / ".refmatrix"
    root.mkdir()
    s = Store(root)
    s.init()
    try:
        stats = ingest_gmd_paths(s, paths)
        assert stats.rels == 2, stats.report()
        lines = A9_HEAD.splitlines() + [""] + A9_TAIL
        a.write_text("\n".join(lines) + "\n")
        src = s.get_entity("concept", "a9#cite").id
        doc = {n: s.get_entity("doc", n).id for n in ("c-doc", "e-doc", "f-doc")}
        for n in ("c-doc", "d-concept", "e-doc"):
            assert s.get_entity("concept", n) is None, f"precondition: no `{n}` concept yet"
        cc = s.upsert_entity(kind="concept", name="c-doc")
        dc = s.upsert_entity(kind="concept", name="d-concept")
        ec = s.upsert_entity(kind="concept", name="e-doc")
        _link9(s, "denotes", ec, doc["e-doc"])
        for tail_line, verb, tgt, ref in (
                (A9_TAIL[0], "derives-from", cc, "c-doc"),
                (A9_TAIL[1], "derives-from", dc, "d-concept"),
                (A9_TAIL[2], "derives-from", ec, "e-doc"),
                (A9_TAIL[3], "related-to", doc["f-doc"], "f-doc")):
            line = lines.index(tail_line) + 1
            if ref != "f-doc":                       # L6: evidence with NO live edge
                _link9(s, verb, src, tgt)
            else:
                try:
                    s.get_linkage_id(verb)
                except KeyError:
                    s.add_linkage_type(verb, directed=True)
            s.add_evidence(verb, src, tgt, file=str(a), line=line,
                           detail=f"rel: {verb} -> {ref}")
        db = Path(s.db_path)
    finally:
        s.close()
    yield db, proj
    shutil.rmtree(base)


def test_ac9_recount_classifies_binding_and_stale_rows(catalog9):
    db, proj = catalog9
    p = _run(str(db), str(proj), "--json")
    assert p.returncode == 0, p.stdout + p.stderr
    got = json.loads(p.stdout)
    assert {k: got.get(k) for k in EXPECTED_AC9} == EXPECTED_AC9, json.dumps(got, indent=1)
    assert sum(got["binding"].values()) == got["landed"], got
    assert got["authored"] == sum(got[k] for k in (
        "landed", "landed_other_line", "stale", "file_not_ingested", "target_unresolved"))


def test_ac9_the_ac5_fixture_has_no_stale_rows(catalog):
    """Every AC-5 row is live: R8's stricter `landed` must not move AC-5's numbers."""
    db, proj = catalog
    p = _run(str(db), str(proj), "--json")
    assert p.returncode == 0, p.stdout + p.stderr
    assert json.loads(p.stdout).get("stale") == 0, p.stdout
