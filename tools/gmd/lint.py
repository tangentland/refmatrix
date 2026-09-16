#!/usr/bin/env python3
"""gmd lint — validate Graph Markdown documents.

Checks:
  - duplicate {#id} within a document
  - dangling [[#id]] (local) and [[doc#id]] (cross-doc) references
  - malformed rel: lines
  - unknown verbs (warning only)
  - frontmatter sanity (gmd version, id presence)

Usage:
  gmd lint <file-or-dir> [<file-or-dir> ...]

Exit codes:
  0 = no errors (warnings allowed)
  1 = errors found
  2 = invocation error
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

RECOMMENDED_VERBS = {
    # GMD primer + ADR vocab.
    "supports", "contradicts", "derives-from", "supersedes",
    "amends",
    "depends-on", "instance-of", "part-of", "mentions",
    "defines", "example-of", "parent", "defined-in",
    "evidence-for", "motivates", "solves",
    "implements", "realizes", "specifies", "specified-by",
    "encoded-as", "catalogs",
    # MEMORY-RULES memory-layer vocab.
    "related-to", "reinforces", "recalls",
}

ID_RE = re.compile(r"\{#([a-z0-9][a-z0-9._/-]*)([^}]*)\}")
WIKILINK_RE = re.compile(r"\[\[([^\[\]]+)\]\]")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
REL_RE = re.compile(
    r"^rel:\s+([a-z][a-z0-9-]*)\s*->\s*(\S+(?:\s+\S+)*?)(?:\s*\{([^}]*)\})?\s*$"
)
FRONTMATTER_DELIM = "---"
CODE_FENCE_RE = re.compile(r"^(```|~~~)")
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")


def strip_inline_code(line: str) -> str:
    return INLINE_CODE_RE.sub(lambda m: " " * len(m.group(0)), line)


@dataclass
class Issue:
    path: Path
    line: int
    severity: str  # "error" | "warn"
    code: str
    msg: str

    def fmt(self) -> str:
        return f"{self.path}:{self.line}: {self.severity}: [{self.code}] {self.msg}"


@dataclass
class Doc:
    path: Path
    doc_id: str | None = None
    gmd_version: str | None = None
    imports: list[str] = field(default_factory=list)
    node_ids: dict[str, int] = field(default_factory=dict)  # id -> line
    refs: list[tuple[int, str, str | None, str, bool]] = field(default_factory=list)
    # (line, raw, target_doc, target_anchor, in_rel)
    rels: list[tuple[int, str, str]] = field(default_factory=list)
    # (line, verb, target_raw)
    external_ids: set[str] = field(default_factory=set)


def parse_frontmatter(lines: list[str]) -> tuple[dict, int]:
    """Return (frontmatter_dict, body_start_line_index). Minimal YAML."""
    if not lines or lines[0].strip() != FRONTMATTER_DELIM:
        return {}, 0
    fm: dict = {}
    i = 1
    current_list_key: str | None = None
    while i < len(lines) and lines[i].strip() != FRONTMATTER_DELIM:
        line = lines[i]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue
        if stripped.startswith("- ") and current_list_key:
            fm[current_list_key].append(stripped[2:].strip())
            i += 1
            continue
        if ":" in stripped:
            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip()
            if val == "":
                fm[key] = []
                current_list_key = key
            elif val.startswith("[") and val.endswith("]"):
                inner = val[1:-1].strip()
                if inner:
                    fm[key] = [x.strip().strip("\"'") for x in inner.split(",")]
                else:
                    fm[key] = []
                current_list_key = None
            else:
                fm[key] = val.strip("\"'")
                current_list_key = None
        i += 1
    body_start = i + 1 if i < len(lines) else i
    return fm, body_start


def parse_doc(path: Path) -> tuple[Doc, list[Issue]]:
    issues: list[Issue] = []
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    fm, body_start = parse_frontmatter(lines)
    doc = Doc(path=path)
    # `id:` is canonical per MEMORY-RULES. Legacy memory files used
    # `name:` instead; treat that as an alias so old files keep
    # resolving against their filename-stem wikilinks. If neither is
    # present, the filename stem is the last-resort fallback so a
    # well-named legacy file still indexes.
    doc.doc_id = fm.get("id") or fm.get("name") or path.stem
    doc.gmd_version = fm.get("gmd")
    # Memory files are GMD-equivalent even when the legacy frontmatter
    # never set `gmd:`. Detect via the memory marker the
    # MEMORY-RULES schema mandates (`metadata.node_type: memory`) and
    # treat as GMD so cross-references between memories resolve. The
    # minimal YAML parser in parse_frontmatter flattens nested keys,
    # so the marker shows up at the top level too — accept either.
    if doc.gmd_version is None:
        meta = fm.get("metadata")
        nested_node_type = (
            meta.get("node_type") if isinstance(meta, dict) else None
        )
        if fm.get("node_type") == "memory" or nested_node_type == "memory":
            doc.gmd_version = "0.1"
    imports = fm.get("imports", [])
    if isinstance(imports, list):
        doc.imports = imports

    # MEMORY.md is the per-project memory index (flat one-line-per-memory
    # list) per MEMORY-RULES — explicitly NOT GMD. Skip the missing-gmd
    # warning for that filename so the lint output isn't drowned in
    # false-positives from every project's index.
    if doc.gmd_version is None and path.name != "MEMORY.md":
        issues.append(Issue(
            path, 1, "warn", "no-gmd-version",
            "frontmatter missing `gmd:` key — file not recognized as GMD",
        ))

    in_code = False
    fence_opened_at = 0
    in_frontmatter = body_start == 0 and lines and lines[0].strip() == FRONTMATTER_DELIM
    if in_frontmatter:
        in_frontmatter = False

    for idx, line in enumerate(lines):
        line_no = idx + 1
        if idx < body_start:
            continue
        if CODE_FENCE_RE.match(line.strip()):
            in_code = not in_code
            if in_code:
                fence_opened_at = line_no
            continue
        if in_code:
            continue

        scan_line = strip_inline_code(line)

        # Extract {#id} anchors (heading or end-of-line on other blocks)
        for m in ID_RE.finditer(scan_line):
            anchor = m.group(1)
            attrs = m.group(2).strip()
            if anchor in doc.node_ids:
                issues.append(Issue(
                    path, line_no, "error", "duplicate-id",
                    f"duplicate anchor `{anchor}` (also at line {doc.node_ids[anchor]})",
                ))
            else:
                doc.node_ids[anchor] = line_no
            if "external=true" in attrs:
                doc.external_ids.add(anchor)

        # rel: lines
        if line.startswith("rel:"):
            m = REL_RE.match(line)
            if not m:
                issues.append(Issue(
                    path, line_no, "error", "malformed-rel",
                    f"rel: line does not match `rel: <verb> -> <target> [{{attrs}}]`: {line!r}",
                ))
                continue
            verb = m.group(1)
            target_raw = m.group(2).strip()
            doc.rels.append((line_no, verb, target_raw))
            if verb not in RECOMMENDED_VERBS:
                issues.append(Issue(
                    path, line_no, "warn", "unknown-verb",
                    f"verb `{verb}` not in recommended vocabulary",
                ))
            for wm in WIKILINK_RE.finditer(target_raw):
                ref = wm.group(1)
                doc_id, anchor = _split_ref(ref)
                doc.refs.append((line_no, ref, doc_id, anchor, True))
            if not WIKILINK_RE.search(target_raw):
                if not (target_raw.startswith("http://") or target_raw.startswith("https://")
                        or target_raw == "[]"):
                    issues.append(Issue(
                        path, line_no, "warn", "rel-target-shape",
                        f"rel target `{target_raw}` is not a [[wikilink]] or URL",
                    ))
            continue

        # Other wikilinks in body (skip inline code)
        for wm in WIKILINK_RE.finditer(scan_line):
            ref = wm.group(1)
            doc_id, anchor = _split_ref(ref)
            doc.refs.append((line_no, ref, doc_id, anchor, False))

    # An UNCLOSED fence is the one malformation this linter was structurally
    # blind to: every heading, anchor and `rel:` edge after it is read as code
    # and simply never exists. That is not a formatting nit — it silently
    # DELETES graph nodes, and the linter reports zero errors while it does.
    # A stray fence in eval/production/longmemeval/REPORT.md removed its
    # `#next` node this way, in the very commit that fixed a renderer for
    # deleting graph edges (ch-bsd r4 #b-2-r4). r3's own sentence: a linter
    # that only reports malformed constructs cannot report absent ones.
    if in_code:
        issues.append(Issue(
            path, fence_opened_at or 1, "error", "unclosed-fence",
            f"code fence opened at line {fence_opened_at} is never closed — "
            f"every heading, anchor and rel: edge after it is invisible",
        ))

    return doc, issues


def _split_ref(ref: str) -> tuple[str | None, str]:
    """[[#id]] -> (None, 'id'); [[doc#id]] -> ('doc', 'id'); [[doc]] -> ('doc', '')."""
    ref = ref.strip()
    if ref.startswith("#"):
        return None, ref[1:]
    if "#" in ref:
        doc_id, _, anchor = ref.partition("#")
        return doc_id, anchor
    return ref, ""


def _norm_id(s: str) -> str:
    """Normalize a doc id for cross-form lookup. Kebab-case and
    snake-case slugs reference the same logical doc — `project-foo-bar`
    and `project_foo_bar` resolve to one another. Lowercase too so
    case drift doesn't break links."""
    return s.replace("-", "_").lower()


def resolve_refs(docs: dict[str, Doc], paths_by_id: dict[str, Doc]) -> list[Issue]:
    # Build a normalized lookup table alongside the literal one so
    # legacy kebab `name:` ids match new snake `id:` ids and vice
    # versa. Literal hits take precedence.
    norm_by_id = {_norm_id(k): v for k, v in paths_by_id.items()}
    issues: list[Issue] = []
    for doc in docs.values():
        for line_no, raw, doc_id, anchor, in_rel in doc.refs:
            if doc_id is None:
                if anchor and anchor not in doc.node_ids and anchor not in doc.external_ids:
                    issues.append(Issue(
                        doc.path, line_no, "error", "dangling-local",
                        f"[[#{anchor}]] does not resolve to any anchor in this doc",
                    ))
                continue
            target = paths_by_id.get(doc_id) or norm_by_id.get(_norm_id(doc_id))
            if target is None:
                issues.append(Issue(
                    doc.path, line_no, "error", "dangling-doc",
                    f"[[{raw}]] — no doc with id `{doc_id}` in scanned set",
                ))
                continue
            if anchor and anchor not in target.node_ids and anchor not in target.external_ids:
                issues.append(Issue(
                    doc.path, line_no, "error", "dangling-anchor",
                    f"[[{raw}]] — doc `{doc_id}` has no anchor `{anchor}`",
                ))
    return issues


def collect_files(targets: list[str]) -> list[Path]:
    out: list[Path] = []
    for t in targets:
        p = Path(t)
        if p.is_file():
            out.append(p)
        elif p.is_dir():
            for ext in ("*.gmd", "*.md"):
                out.extend(sorted(p.rglob(ext)))
        else:
            print(f"gmd lint: not found: {t}", file=sys.stderr)
    return out


def _parse_args(argv: list[str]) -> tuple[list[str], list[str]]:
    """Split argv into (targets, scope_paths).

    `--scope <path>` (repeatable): files scanned for doc-id resolution
    only — refs from `targets` can resolve to anchors / doc-ids in
    these paths, but no issues from scope files are reported.

    Use case: a memory file references `[[task-spec-XYZ]]` that lives
    in a sibling project tree. Without scope, the ref dangles because
    the lint scan never crossed the tree boundary. With
    `--scope ~/proj/docs/`, the ref resolves and only memory-side
    issues surface in the output.
    """
    targets: list[str] = []
    scopes: list[str] = []
    i = 1
    while i < len(argv):
        a = argv[i]
        if a == "--scope":
            if i + 1 >= len(argv):
                print(
                    "gmd lint: --scope requires a path argument",
                    file=sys.stderr,
                )
                sys.exit(2)
            scopes.append(argv[i + 1])
            i += 2
            continue
        if a.startswith("--scope="):
            scopes.append(a.split("=", 1)[1])
            i += 1
            continue
        targets.append(a)
        i += 1
    return targets, scopes


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    targets, scope_paths = _parse_args(argv)
    if not targets:
        print(
            "gmd lint: at least one target file or directory required",
            file=sys.stderr,
        )
        return 2
    target_files = collect_files(targets)
    if not target_files:
        print("gmd lint: no files matched", file=sys.stderr)
        return 2
    scope_files = collect_files(scope_paths) if scope_paths else []
    # Scope files supplement the resolution set but never produce
    # issues themselves. Deduplicate against target files so a path
    # that appears in both surfaces as a target (issues reported).
    target_set = {f.resolve() for f in target_files}
    scope_files = [
        f for f in scope_files if f.resolve() not in target_set
    ]
    target_paths = {f.resolve() for f in target_files}

    docs: dict[str, Doc] = {}
    all_issues: list[Issue] = []

    def _ingest(f: Path, *, report_issues: bool) -> None:
        try:
            doc, issues = parse_doc(f)
        except Exception as e:
            if report_issues:
                all_issues.append(Issue(
                    f, 0, "error", "parse-fail",
                    f"{type(e).__name__}: {e}",
                ))
            return
        if report_issues:
            all_issues.extend(issues)
        if doc.gmd_version is None:
            return
        key = doc.doc_id or f.stem
        if key in docs:
            if report_issues:
                all_issues.append(Issue(
                    f, 1, "error", "duplicate-doc-id",
                    f"doc id `{key}` also used by {docs[key].path}",
                ))
            return
        docs[key] = doc

    for f in target_files:
        _ingest(f, report_issues=True)
    for f in scope_files:
        _ingest(f, report_issues=False)

    # Every file is ALSO addressable by its filename stem, regardless
    # of `id` / `name`. Lets cross-refs use the stable filename even
    # when the file's frontmatter slug drifts (legacy `name:` rename,
    # `id:` typo, etc.). Literal id still wins; stem is a fallback.
    by_id_or_stem: dict[str, Doc] = {}
    for key, d in docs.items():
        by_id_or_stem.setdefault(key, d)
    for d in docs.values():
        by_id_or_stem.setdefault(d.path.stem, d)

    # `resolve_refs` walks every doc in `docs` (which now includes
    # scope docs) and emits issues for any unresolved ref. Filter the
    # results to keep only issues whose source path is a target file —
    # scope files contribute resolution-only, not issue-reporting.
    ref_issues = resolve_refs(docs, by_id_or_stem)
    all_issues.extend(
        i for i in ref_issues if i.path.resolve() in target_paths
    )

    errors = [i for i in all_issues if i.severity == "error"]
    warns = [i for i in all_issues if i.severity == "warn"]

    for i in sorted(all_issues, key=lambda x: (str(x.path), x.line)):
        print(i.fmt())

    print(
        f"\ngmd lint: {len(target_files)} files, {len(docs)} GMD docs, "
        f"{len(errors)} errors, {len(warns)} warnings"
        + (
            f" (scope: +{len(scope_files)} doc(s) used for resolution only)"
            if scope_files else ""
        ),
        file=sys.stderr,
    )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
