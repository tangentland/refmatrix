"""
Ingestion: turn a project directory into entities + linkages.

Sources, in order of preference:

1. **metadata** — `.tldr/cache/semantic/metadata.json` (llm-tldr's per-unit
   semantic dump). Strictly richer than call_graph.json: signature, unit_type
   (function/class/method/...), per-unit calls/called_by, dependencies, CFG
   and DFG summaries. Preferred when present.
2. **tldr** — `.tldr/cache/call_graph.json`. Just (from_file, from_func) ->
   (to_file, to_func) edges. Used when metadata.json isn't there.
3. **tree** — walk the directory, register every text file as a `doc` or
   `code`. No call graph; you still get a per-file entity to `link` against.
4. **semantic** (Python only, opt-in via --semantic) — stdlib ast pass that
   adds `imports` and docstring-keyword `mentions` linkages. Redundant when
   metadata.json is available, but harmless and cross-source-additive.
"""
from __future__ import annotations

import ast
import json
import re
from collections import Counter
from pathlib import Path

from refmatrix.store import Store

CODE_EXTS = {
    ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java",
    ".kt", ".swift", ".c", ".cc", ".cpp", ".h", ".hpp", ".rb", ".php",
    ".cs", ".scala", ".sh", ".bash", ".zsh", ".sql", ".lua", ".pseudo",
}
DOC_EXTS = {".md", ".markdown", ".rst", ".txt", ".adoc"}


def ingest_path(
    s: Store, path: Path, source: str = "auto", semantic: bool = False
) -> int:
    path = path.resolve()
    metadata_path = path / ".tldr" / "cache" / "semantic" / "metadata.json"
    call_graph_path = path / ".tldr" / "cache" / "call_graph.json"
    n = 0
    if source in ("auto", "metadata") and metadata_path.exists():
        n = _ingest_tldr_metadata(s, path)
    if n == 0 and source in ("auto", "tldr") and call_graph_path.exists():
        n = _ingest_tldr(s, path)
    if source in ("auto", "tree") and n == 0:
        n = _ingest_tree(s, path)
    if semantic:
        for p in path.rglob("*.py"):
            parts = set(p.parts)
            if any(seg in parts for seg in (".git", ".venv", "node_modules",
                                            ".tldr", ".refmatrix")):
                continue
            _ingest_python_semantics(s, p, path)
    for p in path.rglob("*.pseudo"):
        parts = set(p.parts)
        if any(seg in parts for seg in (".git", ".venv", "node_modules",
                                        ".tldr", ".refmatrix")):
            continue
        _ingest_pseudo_semantics(s, p, path)

    # ADR semantic extraction — two-pass so cross-references resolve.
    adr_files: list[tuple[Path, str]] = []
    adr_num_to_eid: dict[str, int] = {}
    for p in path.rglob("*.md"):
        parts = set(p.parts)
        if any(seg in parts for seg in (".git", ".venv", "node_modules",
                                        ".tldr", ".refmatrix")):
            continue
        adr_num = _is_adr_file(p)
        if adr_num is None:
            continue
        rel = (
            p.relative_to(path).as_posix() if p.is_relative_to(path) else str(p)
        )
        eid = s.upsert_entity(
            kind="doc", name=rel, path=str(p),
            meta={"adr_number": adr_num},
        )
        try:
            s.mark_tracked(str(p), p.stat().st_mtime)
        except OSError:
            pass
        adr_num_to_eid[adr_num] = eid
        adr_files.append((p, adr_num))
    for p, _ in adr_files:
        _ingest_adr_semantics(s, p, path, adr_num_to_eid)
    return n


# --- tldr metadata.json (richest source) ------------------------------------


# Fields kept on each unit's `meta` blob. Anything bulky (code_preview, full
# docstring) is stored when present; querying paths can ignore it.
_UNIT_META_FIELDS = (
    "language", "unit_type", "name", "line",
    "cfg_summary", "dfg_summary", "docstring", "code_preview", "signature",
)

# What counts as a "trivial" callee. These would explode `calls`-bitmap
# cardinality without adding signal — every test has __init__, every async
# class has __aexit__, etc. Keep them out of the concept layer entirely.
_CALLEE_BLOCKLIST = frozenset({
    "__init__", "__new__", "__call__", "__enter__", "__exit__",
    "__aenter__", "__aexit__", "__repr__", "__str__", "__hash__",
    "__eq__", "__ne__", "__lt__", "__le__", "__gt__", "__ge__",
})


def _ingest_tldr_metadata(s: Store, project: Path) -> int:
    """Ingest llm-tldr's per-unit semantic dump. Returns the number of units
    processed (not linkages). See the module docstring for source priority."""
    cache = project / ".tldr" / "cache" / "semantic" / "metadata.json"
    payload = json.loads(cache.read_text())
    units = payload.get("units") or []
    if not units:
        return 0

    # Pre-pass: dedup file paths so we make one entity per file (used both for
    # tracked_files and as the target of file-level imports linkage).
    file_ids: dict[str, int] = {}
    for u in units:
        rel = u.get("file")
        if not rel or rel in file_ids:
            continue
        ap = project / rel
        eid = s.upsert_entity(kind="code", name=rel, path=str(ap))
        try:
            s.mark_tracked(str(ap), ap.stat().st_mtime)
        except OSError:
            pass
        file_ids[rel] = eid

    # Concept caches — bare-name concepts collide naturally with user
    # concepts (desired join behavior); namespaced ones don't.
    bare_concept_ids: dict[str, int] = {}
    kind_concept_ids: dict[str, int] = {}
    import_concept_ids: dict[str, int] = {}

    def bare_concept(name: str) -> int:
        if name in bare_concept_ids:
            return bare_concept_ids[name]
        cid = s.add_concept(name, description=f"symbol '{name}'")
        bare_concept_ids[name] = cid
        return cid

    def kind_concept(unit_type: str) -> int:
        if unit_type in kind_concept_ids:
            return kind_concept_ids[unit_type]
        cid = s.add_namespaced_concept(
            "kind", unit_type, description=f"unit_type '{unit_type}'"
        )
        kind_concept_ids[unit_type] = cid
        return cid

    def import_concept(mod: str) -> int:
        if mod in import_concept_ids:
            return import_concept_ids[mod]
        cid = s.add_namespaced_concept(
            "import", mod, description=f"module '{mod}'"
        )
        import_concept_ids[mod] = cid
        return cid

    # Per-unit pass: create the unit entity, plus its defines / is_a / calls.
    # Aggregate file-level imports as we go so we can write them in batch.
    file_imports: dict[int, set[int]] = {}
    unit_count = 0
    qname_to_eid: dict[str, int] = {}

    for u in units:
        qname = u.get("qualified_name")
        rel = u.get("file")
        bare = u.get("name")
        if not qname or not rel or not bare:
            continue

        ap = project / rel
        meta = {k: u[k] for k in _UNIT_META_FIELDS if u.get(k)}
        signature = u.get("signature") or f"{u.get('unit_type', 'symbol')} {bare} in {rel}"
        unit_eid = s.upsert_entity(
            kind="code", name=qname, path=str(ap),
            tldr=signature, meta=meta,
        )
        qname_to_eid[qname] = unit_eid
        unit_count += 1

        # bare-name concept defines this unit
        s.link("defines", bare_concept(bare), unit_eid)

        # kind/<unit_type> categorical concept
        utype = u.get("unit_type")
        if utype:
            s.link("is_a", kind_concept(utype), unit_eid)

        # calls / called_by — callees are bare names per llm-tldr's schema
        for callee in u.get("calls") or ():
            if not callee or callee in _CALLEE_BLOCKLIST:
                continue
            cc = bare_concept(callee)
            # caller-unit-entity is in the `calls` bitmap of the callee concept
            s.link("calls", cc, unit_eid)

        for caller in u.get("called_by") or ():
            if not caller or caller in _CALLEE_BLOCKLIST:
                continue
            cc = bare_concept(caller)
            s.link("called_by", cc, unit_eid)

        # dependencies: comma-separated module list. Aggregate to file-level
        # so a 50-function file with 5 imports doesn't make 250 link rows.
        deps = u.get("dependencies") or ""
        if deps and rel in file_ids:
            fid = file_ids[rel]
            bucket = file_imports.setdefault(fid, set())
            for raw in deps.split(","):
                mod = raw.strip().split(".")[0]
                if mod:
                    bucket.add(import_concept(mod))

    # Flush file-level imports in one batch per (concept, file) pair.
    for fid, cids in file_imports.items():
        for cid in cids:
            s.link("imports", cid, fid)

    return unit_count


# --- tldr -------------------------------------------------------------------


def _ingest_tldr(s: Store, project: Path) -> int:
    cache = project / ".tldr" / "cache" / "call_graph.json"
    data = json.loads(cache.read_text())
    edges = data.get("edges", [])
    n = 0

    file_ids: dict[str, int] = {}
    func_ids: dict[tuple[str, str], int] = {}
    concept_ids: dict[str, int] = {}

    def file_id(rel: str) -> int:
        if rel in file_ids:
            return file_ids[rel]
        ap = project / rel
        eid = s.upsert_entity(kind="code", name=rel, path=str(ap))
        try:
            s.mark_tracked(str(ap), ap.stat().st_mtime)
        except OSError:
            pass
        file_ids[rel] = eid
        return eid

    def func_id(rel: str, fn: str) -> int:
        key = (rel, fn)
        if key in func_ids:
            return func_ids[key]
        name = f"{rel}::{fn}"
        eid = s.upsert_entity(
            kind="code", name=name, path=str(project / rel),
            tldr=f"function {fn} in {rel}",
            meta={"file": rel, "func": fn, "kind": "function"},
        )
        func_ids[key] = eid
        return eid

    def concept_id(fn: str) -> int:
        if fn in concept_ids:
            return concept_ids[fn]
        cid = s.add_concept(fn, description=f"function name '{fn}'")
        concept_ids[fn] = cid
        return cid

    for e in edges:
        from_file = e.get("from_file") or ""
        from_func = e.get("from_func") or ""
        to_file = e.get("to_file") or ""
        to_func = e.get("to_func") or ""

        if from_file:
            file_id(from_file)
        if to_file:
            file_id(to_file)

        if from_file and from_func:
            ff_id = func_id(from_file, from_func)
            from_concept = concept_id(from_func)
            s.link("defines", from_concept, ff_id)
            n += 1

        if to_file and to_func:
            tf_id = func_id(to_file, to_func)
            to_concept = concept_id(to_func)
            s.link("defines", to_concept, tf_id)
            n += 1

        if from_file and from_func and to_func:
            ff_id = func_id(from_file, from_func)
            tc = concept_id(to_func)
            # function entity ff_id 'calls' the to_func concept
            s.link("calls", tc, ff_id)
            # inverse: to_concept's callers
            if to_file and to_func:
                tf_id = func_id(to_file, to_func)
                from_concept = concept_id(from_func)
                s.link("called_by", from_concept, tf_id)
            n += 1
    return n


# --- tree -------------------------------------------------------------------


def _ingest_tree(s: Store, root: Path) -> int:
    n = 0
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        parts = set(p.parts)
        if any(seg in parts for seg in (".git", ".venv", "node_modules", ".tldr", ".refmatrix")):
            continue
        rel = p.relative_to(root).as_posix()
        ext = p.suffix.lower()
        if ext in DOC_EXTS:
            kind = "doc"
        elif ext in CODE_EXTS:
            kind = "code"
        else:
            continue
        s.upsert_entity(kind=kind, name=rel, path=str(p))
        s.mark_tracked(str(p), p.stat().st_mtime)
        n += 1
    return n


# --- Python semantic enrichment --------------------------------------------

# crude stop-list to keep docstring-mined concepts useful
_DOCSTRING_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "for", "in", "is", "are",
    "be", "this", "that", "it", "as", "on", "from", "with", "by", "if",
    "into", "out", "not", "but", "so", "we", "you", "i", "me", "my", "our",
    "use", "used", "uses", "using", "see", "also", "can", "may", "must",
    "will", "should", "would", "could", "args", "arg", "kwargs", "kwarg",
    "param", "params", "return", "returns", "raise", "raises", "yields",
    "yield", "note", "notes", "example", "examples", "default", "true", "false",
    "none", "self", "cls", "type", "types", "value", "values", "object", "objects",
}
_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")


def _ingest_python_semantics(s: Store, file_path: Path, project_root: Path) -> int:
    """Emit namespaced concepts so noise is filterable:
    - import/<module>  for ImportNode targets
    - keyword/<word>   for docstring keywords
    Function-name concepts (from the call graph) stay bare so they collide
    naturally with user concepts (which is the desired join behavior).
    Records linkage_evidence with file:line for explainability.
    """
    try:
        src = file_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(src)
    except (SyntaxError, OSError):
        return 0
    rel = (
        file_path.relative_to(project_root).as_posix()
        if file_path.is_relative_to(project_root)
        else str(file_path)
    )
    file_id = s.upsert_entity(kind="code", name=rel, path=str(file_path))
    s.mark_tracked(str(file_path), file_path.stat().st_mtime)
    n = 0

    for node in ast.walk(tree):
        line = getattr(node, "lineno", None)
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod = alias.name.split(".")[0]
                cid = s.add_namespaced_concept("import", mod,
                                               description=f"Python module '{mod}'")
                s.link("imports", cid, file_id)
                s.add_evidence("imports", cid, file_id, file=rel, line=line,
                               detail=f"import {alias.name}")
                n += 1
        elif isinstance(node, ast.ImportFrom):
            mod = (node.module or "").split(".")[0]
            if mod:
                cid = s.add_namespaced_concept("import", mod,
                                               description=f"Python module '{mod}'")
                s.link("imports", cid, file_id)
                s.add_evidence("imports", cid, file_id, file=rel, line=line,
                               detail=f"from {node.module} import ...")
                n += 1
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node)
            if not doc:
                continue
            fname = f"{rel}::{node.name}"
            f_id = s.upsert_entity(
                kind="code", name=fname, path=str(file_path),
                meta={"file": rel, "func": node.name, "kind": "function"},
            )
            words = [
                w.lower() for w in _WORD_RE.findall(doc)
                if w.lower() not in _DOCSTRING_STOP and not w.isdigit()
            ]
            for word, count in Counter(words).items():
                cid = s.add_namespaced_concept("keyword", word,
                                               description=f"keyword '{word}'")
                s.weighted_link("mentions", cid, f_id, weight=float(count))
                s.add_evidence("mentions", cid, f_id, file=rel, line=line,
                               detail=f"docstring keyword (×{count})")
                n += 1
    return n


# --- .pseudo pseudocode semantic enrichment --------------------------------

_PSEUDO_TYPE_RE = re.compile(r'^([A-Z][A-Za-z0-9]+):\s*(?:#.*)?$')
_PSEUDO_FUNC_RE = re.compile(
    r'^([a-z_][a-z0-9_]*)\s*\(([^)]*)\)(?:\s*->\s*(.+?))?\s*:\s*(?:#.*)?$'
)
_PSEUDO_FUNC_MULTILINE_RE = re.compile(r'^([a-z_][a-z0-9_]*)\s*\(')
_PSEUDO_FIELD_RE = re.compile(r'^\s+([a-z_][a-z0-9_]*)\s*:\s*(.+?)(?:\s*#.*)?$')
_PSEUDO_ENUM_VALUE_RE = re.compile(r'^\s+([A-Z][A-Z_0-9]+)(?:\s*=\s*.+)?\s*(?:#.*)?$')
_PSEUDO_IMPORT_RE = re.compile(r'^from\s+(\w+)\s+import\s+(.+)')
_PSEUDO_TYPE_REF_RE = re.compile(r'[A-Z][A-Za-z0-9]{2,}')
_PSEUDO_CALL_RE = re.compile(r'\b([a-z_][a-z0-9_]{2,})\s*\(')

_PSEUDO_BUILTIN_TYPES = frozenset({
    "None", "True", "False", "int", "int32", "int64", "uint32", "uint64",
    "float", "double", "string", "bool", "bytes", "UUID", "JSON",
    "list", "dict", "map", "set", "tuple", "optional",
})


def _ingest_pseudo_semantics(s: Store, file_path: Path, project_root: Path) -> int:
    """Extract types, enums, functions, and their cross-references from .pseudo files."""
    try:
        lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return 0

    rel = (
        file_path.relative_to(project_root).as_posix()
        if file_path.is_relative_to(project_root)
        else str(file_path)
    )
    file_id = s.upsert_entity(kind="code", name=rel, path=str(file_path))
    s.mark_tracked(str(file_path), file_path.stat().st_mtime)
    n = 0

    STATE_TOP, STATE_TYPE, STATE_ENUM, STATE_FUNC = range(4)
    state = STATE_TOP
    cur_eid: int | None = None
    cur_name: str | None = None

    concept_cache: dict[str, int] = {}

    def get_concept(name: str) -> int:
        if name in concept_cache:
            return concept_cache[name]
        cid = s.add_concept(name, description=f"pseudo symbol '{name}'")
        concept_cache[name] = cid
        return cid

    def extract_type_refs(annotation: str) -> list[str]:
        return [
            t for t in _PSEUDO_TYPE_REF_RE.findall(annotation)
            if t not in _PSEUDO_BUILTIN_TYPES
        ]

    for lineno, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith('#') or stripped.startswith('//'):
            continue

        indent = len(line) - len(line.lstrip())

        # Top-level definitions (col 0)
        if indent == 0:
            # Import statement
            m = _PSEUDO_IMPORT_RE.match(line)
            if m:
                mod = m.group(1)
                cid = s.add_namespaced_concept(
                    "import", mod, description=f"pseudo module '{mod}'")
                s.link("imports", cid, file_id)
                s.add_evidence("imports", cid, file_id, file=rel, line=lineno,
                               detail=f"from {mod} import {m.group(2).strip()}")
                n += 1
                state = STATE_TOP
                continue

            # Type/struct/enum definition
            m = _PSEUDO_TYPE_RE.match(line)
            if m:
                name = m.group(1)
                qname = f"{rel}::{name}"
                cur_eid = s.upsert_entity(
                    kind="code", name=qname, path=str(file_path),
                    meta={"file": rel, "func": name, "kind": "type", "line": lineno},
                )
                cur_name = name
                cid = get_concept(name)
                s.link("defines", cid, cur_eid)
                s.add_evidence("defines", cid, cur_eid, file=rel, line=lineno,
                               detail=f"type {name}")
                n += 1
                state = STATE_TYPE
                continue

            # Function definition
            m = _PSEUDO_FUNC_RE.match(line)
            if not m:
                m = _PSEUDO_FUNC_MULTILINE_RE.match(line)
            if m:
                name = m.group(1)
                qname = f"{rel}::{name}"
                cur_eid = s.upsert_entity(
                    kind="code", name=qname, path=str(file_path),
                    meta={"file": rel, "func": name, "kind": "function", "line": lineno},
                )
                cur_name = name
                cid = get_concept(name)
                s.link("defines", cid, cur_eid)
                s.add_evidence("defines", cid, cur_eid, file=rel, line=lineno,
                               detail=f"function {name}")
                n += 1
                # Extract type refs from params and return type
                if hasattr(m, 'group') and m.lastindex and m.lastindex >= 2:
                    params = m.group(2) or ""
                    ret = m.group(3) if m.lastindex >= 3 else None
                    for tref in extract_type_refs(params):
                        tc = get_concept(tref)
                        s.link("mentions", tc, cur_eid)
                        n += 1
                    if ret:
                        for tref in extract_type_refs(ret):
                            tc = get_concept(tref)
                            s.link("mentions", tc, cur_eid)
                            n += 1
                state = STATE_FUNC
                continue

            # Anything else at col 0 resets state
            state = STATE_TOP
            cur_eid = None
            continue

        # Indented lines — context-dependent
        if cur_eid is None:
            continue

        if state == STATE_TYPE:
            # Check if this is actually an enum
            if _PSEUDO_ENUM_VALUE_RE.match(line):
                state = STATE_ENUM
                continue
            # Field: extract type references
            m = _PSEUDO_FIELD_RE.match(line)
            if m:
                annotation = m.group(2)
                for tref in extract_type_refs(annotation):
                    tc = get_concept(tref)
                    s.link("mentions", tc, cur_eid)
                    s.add_evidence("mentions", tc, cur_eid, file=rel, line=lineno,
                                   detail=f"field type ref {tref}")
                    n += 1

        elif state == STATE_ENUM:
            pass  # enum values don't generate linkages

        elif state == STATE_FUNC:
            # Scan for function calls
            for call_match in _PSEUDO_CALL_RE.finditer(line):
                callee = call_match.group(1)
                if callee == cur_name:
                    continue
                cc = get_concept(callee)
                s.link("calls", cc, cur_eid)
                n += 1
            # Scan for type references
            for tref in extract_type_refs(line):
                tc = get_concept(tref)
                s.link("mentions", tc, cur_eid)
                n += 1

    return n


# --- ADR markdown semantic enrichment --------------------------------------

_ADR_FILENAME_RE = re.compile(r'^(\d{4})-.*\.md$')
_ADR_HEADER_FIELD_RE = re.compile(r'^([A-Z][A-Za-z-]+):\s*(.+?)\s*$')
_ADR_REF_RE = re.compile(r'\bADR-(\d{4})\b')
_ADR_CLASS_RE = re.compile(
    r'^([A-Z][A-Za-z0-9_]+)\s*(?:\(([A-Za-z0-9_,\s]+)\))?\s*:\s*(?:#.*)?$'
)
_ADR_TREE_CHILD_RE = re.compile(
    r'^\s*[+\-|]+--\s*([A-Z][A-Za-z0-9_]+)'
    r'(?:\s*\(([A-Za-z0-9_,\s]+)\))?'
)
_ADR_METHOD_RE = re.compile(
    r'^\s+([a-z_][a-z0-9_]*)\s*\(([^)]*)\)\s*(?:->\s*([^#]+?))?\s*(?:#.*)?$'
)
_ADR_GOVERNS_TOKEN_RE = re.compile(r'\b([A-Z][A-Za-z0-9_]{2,})\b')

_ADR_STATUS_WEIGHT = {
    "Accepted": 1.0,
    "Proposed": 0.3,
    "Draft": 0.2,
    "Superseded": 0.0,
    "Deprecated": 0.0,
    "Rejected": 0.0,
}


def _is_adr_file(p: Path) -> str | None:
    """Return zero-padded ADR number if p looks like an ADR markdown, else None."""
    if p.suffix.lower() != ".md":
        return None
    if not any(part.lower() == "adr" for part in p.parts):
        return None
    m = _ADR_FILENAME_RE.match(p.name)
    return m.group(1) if m else None


def _parse_adr_header(lines: list[str]) -> dict[str, str]:
    """Pull YAML-ish header fields from the top of an ADR.

    Stops at the first ## section heading. Tolerates a leading '# Title' line
    and blank lines. Continuation lines (indented under a field) are joined
    with a space so multi-line Governs/Cross-references survive.
    """
    header: dict[str, str] = {}
    last_key: str | None = None
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            break
        if not stripped:
            last_key = None
            continue
        if stripped.startswith("# ") and last_key is None:
            continue
        m = _ADR_HEADER_FIELD_RE.match(stripped)
        if m:
            last_key = m.group(1)
            header[last_key] = m.group(2).strip()
        elif last_key and (line.startswith(" ") or line.startswith("\t")):
            header[last_key] = (header[last_key] + " " + stripped).strip()
        else:
            last_key = None
    return header


def _ingest_adr_semantics(
    s: Store,
    file_path: Path,
    project_root: Path,
    adr_num_to_eid: dict[str, int],
) -> int:
    """Extract semantic linkages from an ADR markdown file.

    Emits, weighted by Status (Accepted=1.0, Proposed=0.3, Superseded=0):
      - defines:<ClassName> for class/struct specs (fenced or indented blocks)
      - is_a from parent class concept to child class entity
      - mentions for type refs inside class bodies and Governs-line concepts
      - related_to between ADR entities for ADR-NNNN cross-references
        (mediated by adr/NNNN namespaced concept)
    """
    adr_num = _is_adr_file(file_path)
    if adr_num is None:
        return 0
    adr_eid = adr_num_to_eid.get(adr_num)
    if adr_eid is None:
        return 0

    try:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return 0
    lines = text.splitlines()

    rel = (
        file_path.relative_to(project_root).as_posix()
        if file_path.is_relative_to(project_root)
        else str(file_path)
    )

    header = _parse_adr_header(lines)
    status_raw = header.get("Status", "Proposed")
    status = status_raw.split()[0] if status_raw else "Proposed"
    weight = _ADR_STATUS_WEIGHT.get(status, 0.3)
    if weight == 0.0:
        return 0

    n = 0
    concept_cache: dict[str, int] = {}

    def get_concept(name: str) -> int:
        if name in concept_cache:
            return concept_cache[name]
        cid = s.add_concept(name, description=f"symbol '{name}'")
        concept_cache[name] = cid
        return cid

    # Governs line → mentions linkage on CamelCase tokens
    governs = header.get("Governs", "")
    for tok in _ADR_GOVERNS_TOKEN_RE.findall(governs):
        if tok in _PSEUDO_BUILTIN_TYPES:
            continue
        cid = get_concept(tok)
        s.weighted_link("mentions", cid, adr_eid, weight=weight)
        s.add_evidence("mentions", cid, adr_eid, file=rel, line=1,
                       detail=f"Governs: {tok}")
        n += 1

    # Cross-references → related_to via adr/NNNN namespaced concept hub
    seen_refs: set[str] = set()
    for m in _ADR_REF_RE.finditer(text):
        ref_num = m.group(1)
        if ref_num == adr_num or ref_num in seen_refs:
            continue
        seen_refs.add(ref_num)
        target_eid = adr_num_to_eid.get(ref_num)
        if target_eid is None:
            continue
        ref_concept = s.add_namespaced_concept(
            "adr", ref_num, description=f"ADR-{ref_num}"
        )
        s.link("related_to", ref_concept, adr_eid)
        s.link("related_to", ref_concept, target_eid)
        s.add_evidence("related_to", ref_concept, adr_eid,
                       file=rel, detail=f"references ADR-{ref_num}")
        n += 1

    # Class / struct specs + subclass trees
    in_fence = False
    cur_class_eid: int | None = None
    cur_class_name: str | None = None
    class_block_indent: int = -1

    for lineno, line in enumerate(lines, 1):
        stripped = line.strip()

        if stripped.startswith("```"):
            in_fence = not in_fence
            cur_class_eid = None
            cur_class_name = None
            class_block_indent = -1
            continue

        if not stripped:
            continue

        if not in_fence and stripped.startswith("#"):
            cur_class_eid = None
            cur_class_name = None
            class_block_indent = -1
            continue

        indent = len(line) - len(line.lstrip())

        # Subclass tree line e.g. "+-- AnnotatedZone(Zone)"
        tm = _ADR_TREE_CHILD_RE.match(line)
        if tm:
            child = tm.group(1)
            parents_str = tm.group(2) or ""
            child_qname = f"{rel}::{child}"
            child_eid = s.upsert_entity(
                kind="doc", name=child_qname, path=str(file_path),
                meta={"file": rel, "func": child, "kind": "class",
                      "adr": adr_num, "line": lineno},
            )
            cc = get_concept(child)
            s.weighted_link("defines", cc, child_eid, weight=weight)
            s.add_evidence("defines", cc, child_eid, file=rel, line=lineno,
                           detail=f"ADR-{adr_num} subclass {child}")
            n += 1
            for parent in (p.strip() for p in parents_str.split(",")):
                if not parent or parent in _PSEUDO_BUILTIN_TYPES:
                    continue
                pc = get_concept(parent)
                s.weighted_link("is_a", pc, child_eid, weight=weight)
                s.add_evidence("is_a", pc, child_eid, file=rel, line=lineno,
                               detail=f"{child} subclass of {parent}")
                n += 1
            cur_class_eid = None
            cur_class_name = None
            class_block_indent = -1
            continue

        # Class definition: CamelCase at col 0 inside fence, OR CamelCase at
        # col 0 outside fence (indented pseudocode block under a heading)
        cm = _ADR_CLASS_RE.match(line) if indent == 0 else None
        if cm and (in_fence or _looks_like_class_block(lines, lineno)):
            name = cm.group(1)
            parents_str = cm.group(2) or ""
            qname = f"{rel}::{name}"
            cur_class_eid = s.upsert_entity(
                kind="doc", name=qname, path=str(file_path),
                meta={"file": rel, "func": name, "kind": "class",
                      "adr": adr_num, "line": lineno},
            )
            cur_class_name = name
            class_block_indent = 0
            cid = get_concept(name)
            s.weighted_link("defines", cid, cur_class_eid, weight=weight)
            s.add_evidence("defines", cid, cur_class_eid, file=rel, line=lineno,
                           detail=f"ADR-{adr_num} class {name}")
            n += 1
            for parent in (p.strip() for p in parents_str.split(",")):
                if not parent or parent in _PSEUDO_BUILTIN_TYPES:
                    continue
                pc = get_concept(parent)
                s.weighted_link("is_a", pc, cur_class_eid, weight=weight)
                s.add_evidence("is_a", pc, cur_class_eid, file=rel, line=lineno,
                               detail=f"{name} subclass of {parent}")
                n += 1
            continue

        # Body of an open class block: methods + type refs
        if cur_class_eid is not None and indent > class_block_indent:
            mm = _ADR_METHOD_RE.match(line)
            if mm:
                method = mm.group(1)
                mc = get_concept(method)
                s.weighted_link("mentions", mc, cur_class_eid, weight=weight)
                n += 1
                # Type refs in params + return
                for blob in (mm.group(2) or "", mm.group(3) or ""):
                    for tref in _PSEUDO_TYPE_REF_RE.findall(blob):
                        if tref in _PSEUDO_BUILTIN_TYPES or tref == cur_class_name:
                            continue
                        tc = get_concept(tref)
                        s.weighted_link("mentions", tc, cur_class_eid, weight=weight)
                        n += 1
            else:
                for tref in _PSEUDO_TYPE_REF_RE.findall(line):
                    if tref in _PSEUDO_BUILTIN_TYPES or tref == cur_class_name:
                        continue
                    tc = get_concept(tref)
                    s.weighted_link("mentions", tc, cur_class_eid, weight=weight)
                    n += 1
        elif cur_class_eid is not None and indent <= class_block_indent:
            # Dedent back to col 0 with non-class content closes the block
            cur_class_eid = None
            cur_class_name = None
            class_block_indent = -1

    return n


def _looks_like_class_block(lines: list[str], lineno_1based: int) -> bool:
    """Heuristic: a 'Name:' line outside a fence opens a class block only if
    the next non-blank line is indented. Avoids treating markdown labels like
    'Status:' or 'Decision:' as class definitions (they're caught by header
    parser, but also appear in prose)."""
    idx = lineno_1based  # next line index in 0-based
    while idx < len(lines):
        nxt = lines[idx]
        if not nxt.strip():
            idx += 1
            continue
        return nxt.startswith(" ") or nxt.startswith("\t")
    return False
