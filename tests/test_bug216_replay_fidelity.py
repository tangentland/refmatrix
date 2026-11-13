"""bug-216 R13 — every GMD-path write bug-216 adds is a facts.log event that BOTH replay paths
apply.

Spec: workflow/plans/task-bug216-rule-docs-in-graph.md (#r13, #ac-14).

WHY (spec-t4, lead decision 2026-11-13). The GREEN (2fc5554) added GMD-path writes that facts.log
never recorded:
  - `Store.clear_rel_evidence(file)` deletes a re-ingested doc's `rel:` evidence rows with no
    event, while every earlier `evidence` event stays in the log, so a replay of a changed doc
    holds the old AND the new rows where the catalog holds one per line;
  - `pending_refs` rows (`add_pending_ref`, `delete_pending_ref`, `clear_pending_refs_for_file`)
    are never logged, so a replay loses every dangling ref that should bind later.
Before bug-216 both sides held the evidence duplicates and matched. "Declared outside replay" was
rejected for pending refs: a rebuild would silently lose knowledge on a memory path.

The two replay paths:
  rebuild   `Store.rebuild_index_from_log()` — collapses the log, then materializes;
  delta     `Store.apply_log_delta(0)` — event by event through `_apply_event_body` (the daemon's
            rotation refresh).
Each replay is a FRESH catalog under a short `/tmp` mkdtemp root holding a byte copy of the
source store's facts.log. Rows are compared by NAMES (partition, kinds, names, file, line), as a
multiset, so a duplicate is a difference.
"""
from __future__ import annotations

import json
import shutil
import tempfile
from collections import Counter
from pathlib import Path

import pytest

from refmatrix.ingest_gmd import ingest_gmd_paths
from refmatrix.store import Store

REL_VERBS = ("derives-from", "depends-on", "related-to", "amends")
# The ops a log written before bug-216 R13 can hold.
LEGACY_OPS = {"entity", "tombstone", "protect", "noise", "linkage_type", "link", "unlink",
              "evidence", "memory_content", "track", "untrack"}


def _gmd(doc_id: str, body: str) -> str:
    return (f'---\ngmd: "0.1"\nid: {doc_id}\ntitle: "Fixture document"\ntags: [t]\n---\n\n'
            f"# Fixture document {{#root}}\n\n{body}")


B_MD = _gmd("b-doc", "Target.\n\n## Sec {#sec}\n\nS.\n")
C_MD = _gmd("c-doc", "The late target.\n")
A_V1 = _gmd("a", "Intro.\n\n## Cite {#cite}\n\nText.\n\n"
                 "rel: derives-from -> [[b-doc]]\n"
                 "rel: depends-on -> [[c-doc]]\n")
# v2: the existing-target line changes verb, the missing-target line MOVES (a line inserted
# above it), and a second missing target appears.
A_V2 = _gmd("a", "Intro.\n\n## Cite {#cite}\n\nText, edited.\n\nInserted line.\n\n"
                 "rel: related-to -> [[b-doc]]\n"
                 "rel: depends-on -> [[c-doc]]\n"
                 "rel: amends -> [[d-doc]]\n")


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("RMX_LOG", "1")
    base = Path(tempfile.mkdtemp(prefix="b216l", dir="/tmp")).resolve()
    proj = base / "proj"
    (proj / "docs").mkdir(parents=True)
    root = proj / ".refmatrix"
    root.mkdir()
    s = Store(root)
    s.init()
    s.close()
    yield {"base": base, "proj": proj, "root": root, "n": [0]}
    shutil.rmtree(base)


def _write(e, rel: str, body: str) -> Path:
    p = e["proj"] / rel
    p.write_text(body)
    return p


def _ingest(e, paths):
    s = Store(e["root"])
    s.init()
    try:
        return ingest_gmd_paths(s, paths)
    finally:
        s.close()


# ---------------------------------------------------------------- reading a catalog by names


def _snapshot(root: Path) -> dict:
    s = Store(root)
    s.init()
    try:
        con = s._connect()
        ev = Counter(tuple(r) for r in con.execute(
            "SELECT p.name, lt.name, c.kind, c.name, e.kind, e.name, ev.file, ev.line, ev.detail "
            "FROM linkage_evidence ev "
            "JOIN linkage_types lt ON lt.id = ev.linkage_id "
            "JOIN entities c ON c.id = ev.concept_id "
            "JOIN entities e ON e.id = ev.entity_id "
            "JOIN partitions p ON p.id = c.partition_id").fetchall())
        pending = Counter(tuple(r) for r in con.execute(
            "SELECT p.name, s.kind, s.name, pr.linkage, pr.target_name, pr.ref, pr.file, "
            "pr.line, pr.weight, pr.detail FROM pending_refs pr "
            "JOIN entities s ON s.id = pr.source_id "
            "JOIN partitions p ON p.id = pr.partition_id").fetchall())
        orphan_pending = con.execute(
            "SELECT count(*) FROM pending_refs pr WHERE NOT EXISTS "
            "(SELECT 1 FROM entities e WHERE e.id = pr.source_id)").fetchone()[0]
        ph = ",".join("?" * len(REL_VERBS))
        rel_links = Counter(tuple(r) for r in con.execute(
            f"SELECT lt.name, c.kind, c.name, e.kind, e.name FROM entity_links el "
            f"JOIN linkage_types lt ON lt.id = el.linkage_id "
            f"JOIN entities c ON c.id = el.concept_id "
            f"JOIN entities e ON e.id = el.entity_id WHERE lt.name IN ({ph})",
            REL_VERBS).fetchall())
        return {"evidence": ev, "pending": pending, "orphan_pending": orphan_pending,
                "rel_links": rel_links}
    finally:
        s.close()


def _replay(e, how: str, log_bytes: "bytes | None" = None) -> dict:
    """A FRESH catalog replayed from (a byte copy of) the source store's facts.log."""
    e["n"][0] += 1
    # `.../<n>-<how>/proj/.refmatrix`: the default partition is the project dir's name, so the
    # replay's default partition is `proj`, as the source's is (legacy events carry none).
    root = e["base"] / f"r{e['n'][0]}-{how}" / "proj" / ".refmatrix"
    root.mkdir(parents=True)
    s = Store(root)
    s.init()
    try:
        s.log_path.write_bytes(log_bytes if log_bytes is not None
                               else (e["root"] / "facts.log").read_bytes())
        if how == "rebuild":
            s.rebuild_index_from_log()
        else:
            s.apply_log_delta(0)
    finally:
        s.close()
    return _snapshot(root)


def _diff(want: dict, got: dict) -> str:
    out = []
    for k in ("evidence", "pending", "rel_links"):
        extra, missing = got[k] - want[k], want[k] - got[k]
        if extra or missing:
            out.append(f"{k}: replay has extra {dict(extra)}; replay is missing {dict(missing)}")
    if got["orphan_pending"] != want["orphan_pending"]:
        out.append(f"orphan pending rows: {got['orphan_pending']} vs {want['orphan_pending']}")
    return "\n".join(out)


def _v1_then_v2(e) -> dict:
    b = _write(e, "docs/b.md", B_MD)
    _ingest(e, [b])
    a = _write(e, "docs/a.md", A_V1)
    _ingest(e, [a])
    a.write_text(A_V2)
    st = _ingest(e, [a])
    assert st.docs == 1, st.report()
    want = _snapshot(e["root"])
    # Preconditions the comparison rests on: the CATALOG is right.
    a_rel = [k for k in want["evidence"] if k[6] == str(a) and str(k[8]).startswith("rel: ")]
    assert all(want["evidence"][k] == 1 for k in a_rel), f"catalog duplicates: {a_rel}"
    lines = sorted(k[7] for k in a_rel)
    assert lines == [A_V2.splitlines().index("rel: related-to -> [[b-doc]]") + 1], lines
    targets = sorted(k[4] for k in want["pending"])
    assert targets == ["c-doc", "d-doc"], f"catalog pending rows: {dict(want['pending'])}"
    assert want["orphan_pending"] == 0
    return want


# ---------------------------------------------------------------- AC-14


@pytest.mark.parametrize("how", ["rebuild", "delta"])
def test_ac14_a_replay_after_a_changed_doc_matches_the_catalog(env, how):
    """v1 then v2 of a doc with an existing and a missing `rel:` target: the replay holds the
    catalog's evidence rows (no v1 leftovers, no duplicates) and its pending rows."""
    want = _v1_then_v2(env)
    got = _replay(env, how)
    assert got == want, f"{how} replay differs from the catalog:\n{_diff(want, got)}"


@pytest.mark.parametrize("how", ["rebuild", "delta"])
def test_ac14_a_pending_ref_binds_identically_after_replay(env, how):
    """Then the missing target is ingested: the pending ref binds (edge + evidence, row gone) in
    the catalog, and the replay holds exactly the same."""
    _v1_then_v2(env)
    _ingest(env, [_write(env, "docs/c.md", C_MD)])
    want = _snapshot(env["root"])
    assert [k[4] for k in want["pending"]] == ["d-doc"], dict(want["pending"])
    assert any(k[0] == "depends-on" and k[3] == "doc" and k[4] == "c-doc"
               for k in want["rel_links"]), dict(want["rel_links"])
    got = _replay(env, how)
    assert got == want, f"{how} replay differs from the catalog:\n{_diff(want, got)}"


@pytest.mark.parametrize("how", ["rebuild", "delta"])
def test_ac14_guard_a_log_without_the_new_events_replays_as_before(env, how):
    """GUARD: a log written before R13 (only the legacy ops) still replays, materializing one
    evidence row per `evidence` event as it always did."""
    _v1_then_v2(env)
    events = [json.loads(ln) for ln in (env["root"] / "facts.log").read_text().splitlines()
              if ln.strip()]
    legacy = [ev for ev in events if ev.get("op") in LEGACY_OPS]
    data = ("\n".join(json.dumps(ev, sort_keys=True) for ev in legacy) + "\n").encode()
    got = _replay(env, how, data)
    n_ev = sum(1 for ev in legacy if ev.get("op") == "evidence")
    assert sum(got["evidence"].values()) == n_ev, (sum(got["evidence"].values()), n_ev)
    assert not got["pending"], "a legacy log carries no pending rows"
