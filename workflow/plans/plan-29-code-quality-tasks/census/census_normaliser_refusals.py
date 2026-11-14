"""Do the derive-pass files read annotations or docstrings at run time, or use a field-defining
class the normal form does not recognise? (task 29.2 R7, ruling L111) -- the spec's measurement,
run at the commit it names. Read-only AST; imports nothing from refmatrix.

Usage: python3 census_normaliser_refusals.py <src/refmatrix>

The files are read from `_DERIVE_PASS_MODULES` (via census_derive_modules.py's reader would need
an import; the table is parsed here the same way). For each pass file it reports every:
  RUNTIME-ANNOTATION  an attribute `__annotations__`; a call whose final name is `get_type_hints`
                      or `get_annotations`
  RUNTIME-DOCSTRING   an attribute `__doc__`; a call whose final name is `getdoc`, `getsource`
                      or `getsourcelines`. NOT `ast.get_docstring`: it reads the docstring of a
                      tree parsed from ANOTHER file (ingest.py calls it twice on the files it
                      ingests), not the pass file's own docstrings.
  ALIASED-DATACLASS   `dataclass` imported under another name (`import ... as`), or a decorator
                      whose final name is not `dataclass` but is bound to it by an assignment
  ATTRS-CLASS         an import of `attr` or `attrs`; a decorator whose dotted name starts with
                      `attr.` or `attrs.`, or is `define`, `frozen`, `mutable`, `s`, `attrs`
                      imported from one of those packages
It also counts the classes the normal form DOES recognise: decorated `dataclass` /
`dataclasses.dataclass` (with or without arguments), or deriving `NamedTuple` / `TypedDict`.
"""
from __future__ import annotations

import ast
import pathlib
import sys

ANN_CALLS = {"get_type_hints", "get_annotations"}
DOC_CALLS = {"getdoc", "getsource", "getsourcelines"}
ATTRS_NAMES = {"define", "frozen", "mutable", "s", "attrs", "attributes"}


def dotted(n: ast.AST) -> str:
    if isinstance(n, ast.Call):
        n = n.func
    parts = []
    while isinstance(n, ast.Attribute):
        parts.append(n.attr)
        n = n.value
    if isinstance(n, ast.Name):
        parts.append(n.id)
    return ".".join(reversed(parts))


def pass_files(src: pathlib.Path) -> list[str]:
    files: set[str] = set()
    for p in sorted(src.rglob("*.py")):
        for n in ast.parse(p.read_text()).body:
            tgt = val = None
            if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
                tgt, val = n.targets[0].id, n.value
            elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and n.value is not None:
                tgt, val = n.target.id, n.value
            if tgt == "_DERIVE_PASS_MODULES" and isinstance(val, ast.Dict):
                for v in val.values:
                    files |= {e.value for e in v.elts}
    return sorted(files)


def main(argv: list[str]) -> int:
    src = pathlib.Path(argv[1])
    total = 0
    recognised = 0
    for f in pass_files(src):
        tree = ast.parse((src / f).read_text())
        hits: list[str] = []
        attrs_imported: set[str] = set()
        dataclass_aliases: set[str] = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                for a in n.names:
                    if a.name.split(".")[0] in ("attr", "attrs"):
                        hits.append(f"{f}:{n.lineno}: ATTRS-CLASS import {a.name}")
            if isinstance(n, ast.ImportFrom):
                mod = (n.module or "").split(".")[0]
                for a in n.names:
                    if mod in ("attr", "attrs"):
                        attrs_imported.add(a.asname or a.name)
                        hits.append(f"{f}:{n.lineno}: ATTRS-CLASS from {n.module} import {a.name}")
                    if mod == "dataclasses" and a.name == "dataclass" and a.asname and a.asname != "dataclass":
                        dataclass_aliases.add(a.asname)
                        hits.append(f"{f}:{n.lineno}: ALIASED-DATACLASS dataclass as {a.asname}")
            if isinstance(n, ast.Assign) and dotted(n.value) in ("dataclass", "dataclasses.dataclass"):
                for t in n.targets:
                    if isinstance(t, ast.Name) and t.id != "dataclass":
                        dataclass_aliases.add(t.id)
                        hits.append(f"{f}:{n.lineno}: ALIASED-DATACLASS {t.id} = dataclass")
            if isinstance(n, ast.Attribute) and n.attr == "__annotations__":
                hits.append(f"{f}:{n.lineno}: RUNTIME-ANNOTATION .__annotations__")
            if isinstance(n, ast.Attribute) and n.attr == "__doc__":
                hits.append(f"{f}:{n.lineno}: RUNTIME-DOCSTRING .__doc__")
            if isinstance(n, ast.Call):
                last = dotted(n).split(".")[-1]
                if last in ANN_CALLS:
                    hits.append(f"{f}:{n.lineno}: RUNTIME-ANNOTATION {dotted(n)}()")
                if last in DOC_CALLS:
                    hits.append(f"{f}:{n.lineno}: RUNTIME-DOCSTRING {dotted(n)}()")
            if isinstance(n, ast.ClassDef):
                decs = [dotted(d) for d in n.decorator_list]
                bases = [dotted(b) for b in n.bases]
                if any(d in ("dataclass", "dataclasses.dataclass") for d in decs) or any(
                        b.split(".")[-1] in ("NamedTuple", "TypedDict") for b in bases):
                    recognised += 1
                for d in decs:
                    if d.split(".")[0] in ("attr", "attrs") or d in attrs_imported & ATTRS_NAMES \
                            or d in dataclass_aliases:
                        hits.append(f"{f}:{n.lineno}: class {n.name} decorated @{d}")
        print(f"{f:20} refusal triggers: {len(hits)}")
        for h in hits:
            print("  " + h)
        total += len(hits)
    print(f"pass files with a refusal trigger: see above; total triggers: {total}; "
          f"field-defining classes the normal form recognises: {recognised}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
