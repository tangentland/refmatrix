#!/usr/bin/env python3
"""Task 31.6 census: by which FORM does lint resolve each cross-doc wikilink, and does the
ingester's exact-name rule bind the same target?

`resolver_census.py <path>... [--memory-dir <dir>]... [--lines]`

Read-only, no store. The scope is whatever is passed (use `scripts/lint-gmd.sh`'s scope). For
every `[[doc]]` / `[[doc#anchor]]` ref (never a same-doc `[[#anchor]]`) in every GMD doc, it
replays `tools/gmd/lint.py`'s resolution order and records the FIRST form that hits:

  id            the target is a frontmatter `id:` of a scanned doc
  name_alias    the target is a legacy `name:` used as the doc id (no `id:`)
  stem_no_id    the doc has neither `id:` nor `name:`; lint keys it by its filename stem
  stem          the target is a filename stem of a doc whose id differs (lint.py stem binding)
  project       `<project>/<target>` is an id
  fold          the target matches an id only after lowercasing and `-` -> `_`
  fold_project  the same, with the project prefix
  dangling      lint does not resolve it

and whether the INGESTER binds it: the exact target name (`doc`, or `doc#anchor`) is a name
`refmatrix.ingest_gmd.parse_gmd` registers for some file of the scope (docs strict; memory
dirs `lenient=True, memory_ids=True`), or reaches one through the ADR slash alias. A bare
target that no doc owns may still bind a same-named concept in a live store; that is not
visible here and is counted as `ingest_miss`.

Output: one table per ref kind (`rel` = on a `rel:` line, `body` = any other wikilink):
form x {ingest_hit, ingest_miss}; then the `lint resolves, ingest misses` refs grouped by
target doc, and the stems shared by several docs. `--lines` prints each such ref.
"""
from __future__ import annotations

import importlib.util
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from refmatrix.ingest_gmd import _adr_slash_alias, _entity_name, parse_gmd  # noqa: E402

FORMS = ("id", "name_alias", "stem_no_id", "stem", "project", "fold", "fold_project", "dangling")


def _load_lint():
    spec = importlib.util.spec_from_file_location("_census_lint", ROOT / "tools" / "gmd" / "lint.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_census_lint"] = mod
    spec.loader.exec_module(mod)
    return mod


def main(argv: list[str]) -> int:
    show = "--lines" in argv
    args = [a for a in argv if a != "--lines"]
    paths: list[str] = []
    mem: list[str] = []
    it = iter(args)
    for a in it:
        (mem if a == "--memory-dir" else paths).append(next(it) if a == "--memory-dir" else a)
    if not paths and not mem:
        print(__doc__, file=sys.stderr)
        return 2
    lint = _load_lint()
    files = lint.collect_files(paths)
    root = lint._repo_root(files[0]) if files else None
    ignore = (lint.load_config(root).get("ignore") or []) if root else []
    if ignore:
        files = lint.collect_files(paths, ignore)
    mem_files = lint.collect_files(mem) if mem else []
    mem_set = {f.resolve() for f in mem_files}

    # ---- lint side: the docs table, as lint.main builds it --------------------------------
    docs: dict = {}
    origin: dict[str, str] = {}          # docs key -> how the key was chosen
    dup_ids: list[str] = []
    for f in [*files, *mem_files]:
        try:
            doc, _issues = lint.parse_doc(f)
        except Exception as e:
            print(f"lint.parse_doc raised on {f}: {type(e).__name__}: {e}", file=sys.stderr)
            continue
        if doc.gmd_version is None:
            continue
        fm, _b = lint.parse_frontmatter(f.read_text(encoding="utf-8").splitlines())
        key = doc.doc_id or f.stem
        if key in docs:
            dup_ids.append(key)
            continue
        docs[key] = doc
        origin[key] = "id" if fm.get("id") else ("name_alias" if fm.get("name") else "stem_no_id")
    by: dict = dict(docs)
    stem_owners: dict[str, list] = defaultdict(list)
    for d in docs.values():
        stem_owners[d.path.stem].append(d)
    stem_only: set[str] = set()
    for d in docs.values():
        if d.path.stem not in by:
            by[d.path.stem] = d
            stem_only.add(d.path.stem)
    norm = {lint._norm_id(k): v for k, v in by.items()}
    ambiguous = {s for s, o in stem_owners.items() if len(o) > 1} - set(docs)

    # ---- ingest side: every name the ingester registers -----------------------------------
    names: set[str] = set()
    for f in [*files, *mem_files]:
        memory = f.resolve() in mem_set
        try:
            gd = parse_gmd(f, lenient=True, memory_ids=True) if memory else parse_gmd(f)
        except Exception as e:
            print(f"parse_gmd raised on {f}: {type(e).__name__}: {e}", file=sys.stderr)
            continue
        if gd is None:
            continue
        names.add(gd.doc_id)
        slash = _adr_slash_alias(gd.doc_id)
        if slash:
            names.add(slash)
        for n in gd.nodes:
            names.add(_entity_name(gd.doc_id, n.id))

    def ingest_hit(tdoc: str, anchor: str) -> bool:
        name = f"{tdoc}#{anchor}" if anchor else tdoc
        if name in names:
            return True
        slash = _adr_slash_alias(tdoc)
        return bool(slash and (f"{slash}#{anchor}" if anchor else slash) in names)

    table: dict[str, Counter] = {"rel": Counter(), "body": Counter()}
    miss_by_target: dict[str, Counter] = {"rel": Counter(), "body": Counter()}
    miss_form: dict[tuple, str] = {}
    amb_refs = Counter()
    lines_out: list[str] = []
    proj_cache: dict = {}
    for doc in docs.values():
        pdir = doc.path.parent
        if pdir not in proj_cache:
            proj_cache[pdir] = lint.project_name(doc.path)
        project = proj_cache[pdir]
        for line_no, raw, tdoc, anchor, in_rel in doc.refs:
            if tdoc is None:
                continue
            kind = "rel" if in_rel else "body"
            if tdoc in docs:
                form = origin[tdoc]
            elif tdoc in stem_only:
                form = "stem"
            elif project and f"{project}/{tdoc}" in by:
                form = "project"
            elif lint._norm_id(tdoc) in norm:
                form = "fold"
            elif project and lint._norm_id(f"{project}/{tdoc}") in norm:
                form = "fold_project"
            else:
                form = "dangling"
            hit = ingest_hit(tdoc, anchor)
            table[kind][(form, hit)] += 1
            if tdoc in ambiguous and form == "stem":
                amb_refs[tdoc] += 1
            if form != "dangling" and not hit:
                miss_by_target[kind][tdoc] += 1
                miss_form[(kind, tdoc)] = form
                lines_out.append(f"{doc.path}:{line_no}: {kind} [[{raw}]] form={form}")

    print(f"scope: {len(files)} file(s) + {len(mem_files)} memory file(s); {len(docs)} GMD docs; "
          f"{len(dup_ids)} duplicate doc id(s) skipped; {len(names)} ingester names")
    for kind in ("rel", "body"):
        total = sum(table[kind].values())
        print(f"\n{kind} refs (cross-doc): {total}")
        print("  form           ingest_hit  ingest_miss")
        for form in FORMS:
            h, m = table[kind][(form, True)], table[kind][(form, False)]
            if h or m:
                print(f"  {form:14s} {h:10d}  {m:11d}")
        lm = sum(n for (f_, hit), n in table[kind].items() if f_ != "dangling" and not hit)
        print(f"  lint resolves, ingest misses: {lm}")
        for tdoc, n in miss_by_target[kind].most_common():
            print(f"    {tdoc}: {n}  (form {miss_form[(kind, tdoc)]})")
    shared = {s: len(o) for s, o in stem_owners.items() if len(o) > 1}
    print(f"\nstems shared by several GMD docs: {len(shared)}; of them not also a literal id "
          f"(lint's ambiguous-stem set): {len(ambiguous)}; refs resolved through one: "
          f"{sum(amb_refs.values())}")
    if show:
        print()
        print("\n".join(sorted(lines_out)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
