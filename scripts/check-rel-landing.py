#!/usr/bin/env python3
"""Recount authored GMD `rel:` lines against the edges a catalog actually holds.

`check-rel-landing.py <catalog> <root>... [--json]`

WHY (bug-216 R5 + R8, 2026-11-13). bug-216 was first diagnosed from a probe that read
`entity_links` in the wrong direction and reported "66.9% of rel: lines missing"; the recount
against the ingester's OWN evidence rows (`linkage_evidence` file + line) said 4,048 of 4,490
landed, and the misbinding the probe had half-seen (bsd-215m1: bare `[[doc-id]]` lines bound to a
same-named PATH-LESS concept) needed a second pass to classify. This commits that recount, so the
next diagnosis starts from evidence, and AC-6 measures the fix with it.

Every authored wikilink `rel:` line (a `rel:` line at column 0 whose target holds a `[[...]]`) in
every GMD doc under the roots falls in exactly one category:

  file_not_ingested   the file owns no entity in the catalog
  landed              an evidence row at this file + line joins a LIVE `entity_links` row whose
                      two entities both exist (R8)
  landed_other_line   no evidence at this line, a live one for the same verb + ref elsewhere in
                      the file (line drift since the ingest -- benign)
  stale               the only evidence rows for the line join no live edge (bug-219)
  target_unresolved   the file was ingested and nothing landed; grouped by the target's doc

Each landed line is classed by its target (R8, rev 3): `doc_or_memory` (a doc / memory / code
entity), `anchor_node` (a concept with a path: a `doc#anchor` node), `misbound` (a path-less
concept named after an ingested doc / memory, with no `denotes` link to it),
`bound_via_denotes` (the same, reaching the doc through `denotes`), `other_concept` (any other
path-less concept). `sum(binding) == landed`; `authored == landed + landed_other_line + stale +
file_not_ingested + target_unresolved`.

Read-only: the catalog (and its WAL, if any) is COPIED to a temporary directory and the copy is
opened read-only; the path given is never opened. Prints counts and paths only, never prose. Not
a gate: it always exits 0 once it has counted (line drift is benign); 2 on a usage error.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# This checkout's parser and verb canonicaliser, never an installed refmatrix's: the count must
# read the corpus the way the ingester that wrote the catalog read it.
sys.path.insert(0, str(ROOT / "src"))

from refmatrix.ingest_gmd import _WIKILINK_RE, _split_ref, parse_gmd  # noqa: E402
from refmatrix.store import DENOTES, _canonical_verb  # noqa: E402

CATEGORIES = ("landed", "landed_other_line", "stale", "file_not_ingested", "target_unresolved")
BINDINGS = ("doc_or_memory", "anchor_node", "misbound", "bound_via_denotes", "other_concept")


def _usage() -> int:
    print("usage: check-rel-landing.py <catalog> <root>... [--json]", file=sys.stderr)
    return 2


def _open_copy(catalog: Path, tmp: Path):
    """A read-only connection to a COPY of `catalog` (+ its `.wal`) under `tmp`."""
    dst = tmp / catalog.name
    shutil.copy2(catalog, dst)
    wal = catalog.with_name(catalog.name + ".wal")
    if wal.exists():
        shutil.copy2(wal, dst.with_name(dst.name + ".wal"))
    with open(dst, "rb") as fh:
        head = fh.read(16)
    if head.startswith(b"SQLite format 3"):
        import sqlite3
        return sqlite3.connect(f"file:{dst}?mode=ro", uri=True)
    import duckdb
    return duckdb.connect(str(dst), read_only=True)


def _authored(roots: list[Path]) -> list[dict]:
    """Every authored wikilink `rel:` line under `roots`, as the ingester parses it."""
    files: list[Path] = []
    for r in roots:
        if r.is_file():
            files.append(r)
        elif r.is_dir():
            files += sorted(p for ext in ("*.md", "*.gmd") for p in r.rglob(ext) if p.is_file())
    out: list[dict] = []
    seen: set[Path] = set()
    for f in files:
        key = f.resolve()
        if key in seen:
            continue
        seen.add(key)
        try:
            doc = parse_gmd(f)
        except Exception as exc:  # counted by the caller as a parse failure, never skipped
            out.append({"file": key, "parse_error": f"{type(exc).__name__}: {exc}"})
            continue
        if doc is None:
            continue
        for node in doc.nodes:
            for line_no, verb, target in node.rels:
                refs = [m.group(1).strip() for m in _WIKILINK_RE.finditer(target)]
                if not refs:
                    continue
                out.append({"file": key, "line": line_no, "verb": _canonical_verb(verb),
                            "refs": refs, "doc_id": doc.doc_id})
    return out


def recount(con, roots: list[Path]) -> dict:
    lt = {int(i): n for i, n in con.execute("SELECT id, name FROM linkage_types").fetchall()}
    den_lid = next((i for i, n in lt.items() if n == DENOTES), None)
    ents = {int(r[0]): (r[1], r[2], r[3], int(r[4])) for r in con.execute(
        "SELECT id, kind, name, path, partition_id FROM entities").fetchall()}
    ingested_paths: set[str] = set()
    for _k, _n, path, _p in ents.values():
        if path:
            ingested_paths.add(os.path.realpath(path))
    # (partition, name) of every doc / memory: what a path-less concept may be named after
    doc_names = {(p, n) for k, n, _path, p in ents.values() if k in ("doc", "memory")}
    denotes_from: set[int] = set()
    if den_lid is not None:
        denotes_from = {int(c) for (c,) in con.execute(
            "SELECT el.concept_id FROM entity_links el JOIN entities d ON d.id = el.entity_id "
            "WHERE el.linkage_id = ? AND d.kind IN ('doc', 'memory')", (den_lid,)).fetchall()}
    # Evidence rows of GMD `rel:` lines, each with whether it joins a LIVE edge whose two
    # entities exist (R8). The root mirror duplicates its line's evidence: dropped.
    ev: dict[str, list[dict]] = {}
    for e, l, c, f, line, detail, live in con.execute(
            "SELECT le.entity_id, le.linkage_id, le.concept_id, le.file, le.line, le.detail, "
            "  (EXISTS (SELECT 1 FROM entity_links el WHERE el.entity_id = le.entity_id "
            "           AND el.linkage_id = le.linkage_id AND el.concept_id = le.concept_id) "
            "   AND EXISTS (SELECT 1 FROM entities x WHERE x.id = le.entity_id) "
            "   AND EXISTS (SELECT 1 FROM entities y WHERE y.id = le.concept_id)) AS live "
            "FROM linkage_evidence le WHERE le.detail LIKE 'rel: %'").fetchall():
        if not f or (detail or "").endswith("(root-mirror)"):
            continue
        ref = detail.split(" -> ", 1)[1] if " -> " in detail else ""
        ev.setdefault(os.path.realpath(f), []).append(
            {"line": line, "verb": lt.get(int(l)), "ref": ref, "target": int(e),
             "live": bool(live)})

    counts = {k: 0 for k in CATEGORIES}
    binding = {k: 0 for k in BINDINGS}
    unresolved_by_doc: dict[str, int] = {}
    not_ingested_files: set[str] = set()
    parse_failures: list[str] = []
    authored = 0
    for a in _authored(roots):
        if "parse_error" in a:
            parse_failures.append(f"{a['file']}: {a['parse_error']}")
            continue
        authored += 1
        f = str(a["file"])
        if f not in ingested_paths:
            counts["file_not_ingested"] += 1
            not_ingested_files.add(f)
            continue
        rows = ev.get(f, [])
        here = [r for r in rows if r["line"] == a["line"] and r["verb"] == a["verb"]]
        if here:
            hit = next((r for r in here if r["live"]), None)
            if hit is None:
                counts["stale"] += 1
                continue
            counts["landed"] += 1
            binding[_bind(hit["target"], ents, doc_names, denotes_from)] += 1
            continue
        moved = [r for r in rows if r["verb"] == a["verb"] and r["ref"] in a["refs"]]
        if moved:
            counts["landed_other_line" if any(r["live"] for r in moved) else "stale"] += 1
            continue
        counts["target_unresolved"] += 1
        tdoc, _anchor = _split_ref(a["refs"][0])
        key = tdoc if tdoc is not None else a["doc_id"]
        unresolved_by_doc[key] = unresolved_by_doc.get(key, 0) + 1
    return {"authored": authored, **counts,
            "unresolved_by_target_doc": dict(sorted(unresolved_by_doc.items(),
                                                    key=lambda kv: (-kv[1], kv[0]))),
            "binding": binding,
            "files_not_ingested": sorted(not_ingested_files),
            "parse_failures": parse_failures}


def _bind(target: int, ents: dict, doc_names: set, denotes_from: set) -> str:
    kind, name, path, part = ents[target]
    if kind != "concept":
        return "doc_or_memory"
    if path:
        return "anchor_node"
    if (part, name) in doc_names:
        return "bound_via_denotes" if target in denotes_from else "misbound"
    return "other_concept"


def _render(r: dict) -> str:
    out = [f"authored wikilink rel: lines: {r['authored']}"]
    for k in CATEGORIES:
        out.append(f"  {k}: {r[k]}")
    out.append("binding of landed lines:")
    for k in BINDINGS:
        out.append(f"  {k}: {r['binding'][k]}")
    if r["unresolved_by_target_doc"]:
        out.append("target_unresolved by target doc:")
        for d, n in r["unresolved_by_target_doc"].items():
            out.append(f"  {d}: {n}")
    if r["files_not_ingested"]:
        out.append("files not ingested:")
        out += [f"  {f}" for f in r["files_not_ingested"]]
    if r["parse_failures"]:
        out.append(f"parse failures (not counted): {len(r['parse_failures'])}")
        out += [f"  {m}" for m in r["parse_failures"]]
    return "\n".join(out)


def main(argv: list[str]) -> int:
    as_json = "--json" in argv
    args = [a for a in argv if a != "--json"]
    if len(args) < 2:
        return _usage()
    catalog = Path(args[0])
    if not catalog.is_file():
        print(f"check-rel-landing: no catalog file at {catalog}", file=sys.stderr)
        return 2
    roots = [Path(a).resolve() for a in args[1:]]
    tmp = Path(tempfile.mkdtemp(prefix="rmx-rel-landing-"))
    try:
        con = _open_copy(catalog, tmp)
        try:
            result = recount(con, roots)
        finally:
            con.close()
    finally:
        shutil.rmtree(tmp)
    print(json.dumps(result, indent=1) if as_json else _render(result))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
