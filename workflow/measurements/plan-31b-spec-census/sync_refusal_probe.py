#!/usr/bin/env python3
"""Task 31.1: (B1) does a refused GMD file keep its rows and stay refused on the SECOND sync
flush, and (bug-264) does a plain edit of a synced GMD doc keep its anchors and their inbound
`rel:` edges?

Throwaway store under a short `/tmp` root, dev code from this checkout, no daemon, no live
store. Nothing in `src/` is edited: the two designs are simulated at run time.

  arm A  R1 only: `parse_gmd` raises on a list-valued `id` / `title` (what the spec's first
         draft specified for the sync route). This is ch-bsd's probe, repeated.
  arm B  R1 plus the fold of B1 (`task-31.1` `#r2-sync`): `_sync_one` asks the frontmatter
         check BEFORE the relpath-row guard's `purge_path`; a refused path is returned as
         refused, is never put on `gmd_paths`, so it is not in `touched_existing` (no semantic
         pass, no `mark_tracked`); the flush puts it back on the dirty queue.
  arm C  arm B plus the bug-264 fix (`task-31.1` `#r6`): the GMD dispatch's guard purges
         ONLY the relpath-named `doc` row, never the whole path.

Each arm: sync a and b; edit a; turn a's title into a list; flush; flush again with no change.
Printed per step: the ids of a's doc row and anchor, whether b's `rel:` edge to the anchor is
live, the refusals the flush reported, the tracked mtime against the disk mtime, the queue.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
os.environ.pop("RMX_BACKEND", None)

from refmatrix import ingest_gmd as G  # noqa: E402
from refmatrix import sync as S  # noqa: E402
from refmatrix.store import Store  # noqa: E402

A1 = '---\ngmd: "0.1"\nid: adoc\ntitle: "A"\ntags: [t]\n---\n\n# A {#root}\n\n## Sec {#sec}\n\nBody one.\n'
A2 = A1.replace("Body one.", "Body two, edited.")
A3 = A2.replace('title: "A"', "title: [a, b]")
B1 = ('---\ngmd: "0.1"\nid: bdoc\ntitle: "B"\ntags: [t]\n---\n\n# B {#root}\n\n'
      "rel: depends-on -> [[adoc#sec]]\n\nBody.\n")

_real_parse = G.parse_gmd
_real_sync_one = S._sync_one


def frontmatter_refusal(path: Path) -> "str | None":
    """The one check (spec R1): why this file is refused, or None."""
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except Exception as e:  # unreadable / not UTF-8
        return f"{type(e).__name__}: {e}"
    fm, _b = G._parse_frontmatter(lines)
    for key in ("id", "title"):
        v = fm.get(key)
        if isinstance(v, list) and v:
            return f"GmdFrontmatterError: frontmatter `{key}` must be a string, got a list: {v!r}"
    return None


def parse_r1(path, **kw):
    why = frontmatter_refusal(path)
    if why and why.startswith("GmdFrontmatterError"):
        raise ValueError(why)
    return _real_parse(path, **kw)


REFUSED: list[list[str]] = []
RELPATH_ONLY = [False]


def purge_relpath_row_only(s, ap: Path, project_root: Path) -> int:
    """The bug-264 rule: only the `doc` row named by the file's relpath goes."""
    e = s.get_entity("doc", S._relpath(ap, project_root))
    if e is None:
        return 0
    s.purge_entity(e.id)
    return 1


def sync_one_folded(s, ap, project_root, gmd_paths):
    ext = ap.suffix.lower()
    if ap.exists() and not S.should_ignore(ap, project_root) and (
            ext == ".gmd" or (ext == ".md" and S._is_gmd_file(ap))):
        why = frontmatter_refusal(ap)
        if why:
            REFUSED.append([str(ap), why])
            return "gmd_refused"      # nothing purged, not on gmd_paths, not touched
        if RELPATH_ONLY[0]:
            # for an existing GMD file the guard's is the only `purge_path` call in `_sync_one`
            s.purge_path = lambda _p: purge_relpath_row_only(s, ap, project_root)
            try:
                return _real_sync_one(s, ap, project_root, gmd_paths)
            finally:
                del s.purge_path
    return _real_sync_one(s, ap, project_root, gmd_paths)


def state(s: Store, a: Path, b_edge_src: str = "bdoc#root") -> str:
    con = s._connect()
    ids = {n: i for i, n in con.execute(
        "SELECT id, name FROM entities WHERE name IN ('adoc', 'adoc#sec', 'docs/a.md')").fetchall()}
    edge = con.execute(
        "SELECT count(*) FROM entity_links el JOIN entities t ON t.id = el.entity_id "
        "JOIN entities c ON c.id = el.concept_id JOIN linkage_types lt ON lt.id = el.linkage_id "
        "WHERE t.name = 'adoc#sec' AND c.name LIKE 'bdoc%' AND lt.name = 'depends-on'").fetchone()[0]
    tm = s.get_tracked_mtime(str(a))
    dm = a.stat().st_mtime
    return (f"ids={ids} b->adoc#sec edges={edge} "
            f"tracked==disk mtime: {tm == dm}")


def flush(s: Store, proj: Path, folded: bool) -> dict:
    """`flush_queue` as the fold specifies it: drain, sync, put refused paths back."""
    raws = S.drain_queue(s.root)
    REFUSED.clear()
    rep = S._sync_paths(s, [Path(p) for p in raws], proj, False)
    refused = [p for p, _w in REFUSED] if folded else []
    if refused:
        S.enqueue(s.root, refused)
    return {"paths": len(raws), "touched": rep["touched"],
            "gmd_refused": [[Path(p).name, w.split(":")[0]] for p, w in REFUSED] if folded else "n/a",
            "queue_after": [Path(p).name for p in (s.root / S.QUEUE_FILE).read_text().split()]
            if (s.root / S.QUEUE_FILE).exists() else []}


def arm(name: str, folded: bool, relpath_only: bool = False) -> None:
    print(f"== arm {name}")
    RELPATH_ONLY[0] = relpath_only
    proj = Path(tempfile.mkdtemp(prefix="b1p.", dir="/tmp")).resolve()
    try:
        (proj / "docs").mkdir()
        a, b = proj / "docs" / "a.md", proj / "docs" / "b.md"
        a.write_text(A1)
        b.write_text(B1)
        s = Store(proj / ".refmatrix")
        s.init()
        G.parse_gmd = parse_r1
        S._sync_one = sync_one_folded if folded else _real_sync_one
        steps = [("sync 1 (a, b)", None, [a, b]), ("sync 2 (a edited)", A2, [a]),
                 ("flush 1 (a -> list title)", A3, [a]), ("flush 2 (no change)", None, [])]
        for label, text, paths in steps:
            if text is not None:
                time.sleep(0.02)
                a.write_text(text)
            if paths:
                S.enqueue(s.root, [str(p) for p in paths])
            rep = flush(s, proj, folded)
            print(f"{label:28s} {state(s, a)}")
            print(f"{'':28s} flush: {rep}")
        s.close()
    finally:
        G.parse_gmd = _real_parse
        S._sync_one = _real_sync_one
        shutil.rmtree(proj, ignore_errors=True)


if __name__ == "__main__":
    arm("A: R1 only (first draft; ch-bsd's B1)", folded=False)
    arm("B: R1 + the B1 fold", folded=True)
    arm("C: R1 + the B1 fold + the bug-264 fix", folded=True, relpath_only=True)
