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
    base = Path(tempfile.mkdtemp(prefix="b216l", dir="/tmp")).resolve()
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
