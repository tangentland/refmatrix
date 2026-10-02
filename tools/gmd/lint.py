#!/usr/bin/env python3
"""gmd lint — validate Graph Markdown documents.

Two phases:
  Phase 1 (doc-level) — always hard errors. Per-file structure the author
    controls: duplicate {#id}, malformed rel:, dangling SAME-DOC [[#id]],
    frontmatter sanity. Runs for every target.
  Phase 2 (cross-doc) — corpus resolution: dangling [[doc#id]] / wrong anchor
    in another doc. These are hard errors ONLY when a directory/corpus is in
    scope (the scan can actually see the targets). For single-file / file-list
    targets they downgrade to WARNINGS, so linting one new file never throws
    on links to docs outside the scan. CI lints the tree (dir → phase 2 on).

Phase selection:
  - default: AUTO — phase 2 on iff any target is a directory.
  - --phase1 : force doc-level only (cross-doc unresolved → warning).
  - --phase2 : force cross-doc errors (e.g. file targets + --scope corpus).
  - --scope <path> : add files to the resolution set without reporting their
    own issues (resolve cross-tree refs without scanning the whole tree).
  - --reconcile : link-reconciliation mode. AUTO-DISCOVERS the corpus for each
    target — walks up to the repo root (nearest ancestor with a `.git`), adds
    that whole tree as resolution scope, and ALSO adds the project's Claude
    memory dir (~/.claude/projects/<dashified-repo-path>/memory) when it exists
    — then forces phase 2. Turns a single-file lint's "dangling because
    unscanned" WARNINGS into real cross-doc checks: links that resolve anywhere
    in the repo/memory corpus pass; only genuinely-missing targets error. Use
    it to validate one file's cross-doc links without enumerating every --scope.

Usage:
  gmd lint <file-or-dir> [...] [--phase1|--phase2] [--reconcile] [--scope P]

Exit codes:
  0 = no errors (warnings allowed)
  1 = errors found
  2 = invocation error
"""

from __future__ import annotations

import fnmatch
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

# Canonical memory `metadata.type` enum (mirrors ~/.claude/MEMORY-RULES.md
# #frontmatter). Files carrying `metadata.node_type: memory` should declare a
# `metadata.type` drawn from this set. `guardrail` = enforceable action-policy
# rule compiled into auto-mode (p20-0). This is a WARN-only gate: an unknown
# type never fails lint (exit stays 0), so it can't regress other projects — it
# only flags drift. `curated`/`observation`/`note`/`decision` are the
# rmx-side sync-disk defaults and are accepted alongside the authored types.
KNOWN_MEMORY_TYPES = {
    "user", "feedback", "project", "reference", "impression", "guardrail",
    "curated", "observation", "note", "decision",
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


# Project-local additions to RECOMMENDED_VERBS, loaded from `.gmd/config.yml`
# (`extra_verbs:`). Populated by main() before ingest. Previously that config key
# was written by `gmd init` and never read by anything.
EXTRA_VERBS: set[str] = set()


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
    if isinstance(doc.doc_id, str):
        shape = id_shape_issue(path, 1, "bad-doc-id", doc.doc_id)
        if shape:
            issues.append(shape)
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

    # Memory `metadata.type` enum check (WARN-only, never fails lint). The
    # minimal frontmatter parser flattens nested `metadata.*` keys to the top
    # level, so `metadata.type: guardrail` surfaces as fm["type"]. Only assess
    # files that self-identify as memories.
    _meta = fm.get("metadata")
    _nested_node_type = _meta.get("node_type") if isinstance(_meta, dict) else None
    if fm.get("node_type") == "memory" or _nested_node_type == "memory":
        _mtype = fm.get("type")
        if isinstance(_meta, dict) and _meta.get("type"):
            _mtype = _meta.get("type")
        if isinstance(_mtype, str) and _mtype and _mtype not in KNOWN_MEMORY_TYPES:
            issues.append(Issue(
                path, 1, "warn", "unknown-memory-type",
                f"metadata.type `{_mtype}` not in known memory-type enum "
                f"({', '.join(sorted(KNOWN_MEMORY_TYPES))})",
            ))

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
    in_frontmatter = body_start == 0 and lines and lines[0].strip() == FRONTMATTER_DELIM
    if in_frontmatter:
        in_frontmatter = False

    for idx, line in enumerate(lines):
        line_no = idx + 1
        if idx < body_start:
            continue
        if CODE_FENCE_RE.match(line.strip()):
            in_code = not in_code
            continue
        if in_code:
            continue

        scan_line = strip_inline_code(line)

        # Extract {#id} anchors (heading or end-of-line on other blocks)
        for m in ID_RE.finditer(scan_line):
            _shape = id_shape_issue(path, line_no, "bad-id", m.group(1))
            if _shape:
                issues.append(_shape)
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
            if verb not in RECOMMENDED_VERBS and verb not in EXTRA_VERBS:
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


def resolve_refs(
    docs: dict[str, Doc],
    paths_by_id: dict[str, Doc],
    cross_doc_severity: str = "error",
    literal_ids: set[str] | None = None,
    ambiguous_stems: set[str] | None = None,
) -> list[Issue]:
    # Build a normalized lookup table alongside the literal one so
    # legacy kebab `name:` ids match new snake `id:` ids and vice
    # versa. Literal hits take precedence.
    #
    # `cross_doc_severity` is the severity for PHASE-2 cross-doc misses
    # (`dangling-doc`, `dangling-anchor`). "error" in corpus/dir mode;
    # "warn" in single-file / file-list mode where the scan can't be
    # expected to contain every referenced doc. Same-doc `[[#id]]`
    # (`dangling-local`) is PHASE 1 — always an error.
    norm_by_id = {_norm_id(k): v for k, v in paths_by_id.items()}
    literal_ids = literal_ids or set()
    ambiguous_stems = ambiguous_stems or set()
    issues: list[Issue] = []
    _proj_cache: dict[Path, str | None] = {}
    for doc in docs.values():
        # A doc's own project scopes its unprefixed refs: inside project `foo`,
        # `[[bar#x]]` may address `foo/bar`. Keeps every pre-existing unprefixed
        # link working once ids gain a project prefix.
        _dir = doc.path.parent
        if _dir not in _proj_cache:
            _proj_cache[_dir] = project_name(doc.path)
        _project = _proj_cache[_dir]
        for line_no, raw, doc_id, anchor, in_rel in doc.refs:
            if doc_id is None:
                if anchor and anchor not in doc.node_ids and anchor not in doc.external_ids:
                    issues.append(Issue(
                        doc.path, line_no, "error", "dangling-local",
                        f"[[#{anchor}]] does not resolve to any anchor in this doc",
                    ))
                continue
            # Literal id, then project-scoped, then the normalized
            # kebab/snake variants of each.
            target = paths_by_id.get(doc_id)
            if target is None and _project:
                target = paths_by_id.get(f"{_project}/{doc_id}")
            if target is None:
                target = norm_by_id.get(_norm_id(doc_id))
            if target is None and _project:
                target = norm_by_id.get(_norm_id(f"{_project}/{doc_id}"))
            if target is not None and doc_id in ambiguous_stems and doc_id not in literal_ids:
                issues.append(Issue(
                    doc.path, line_no, "warn", "ambiguous-stem",
                    f"[[{raw}]] resolves by filename stem `{doc_id}`, which "
                    f"matches several docs; use the project-prefixed id",
                ))
            if target is None:
                issues.append(Issue(
                    doc.path, line_no, cross_doc_severity, "dangling-doc",
                    f"[[{raw}]] — no doc with id `{doc_id}` in scanned set",
                ))
                continue
            if anchor and anchor not in target.node_ids and anchor not in target.external_ids:
                issues.append(Issue(
                    doc.path, line_no, cross_doc_severity, "dangling-anchor",
                    f"[[{raw}]] — doc `{doc_id}` has no anchor `{anchor}`",
                ))
    return issues


def _repo_root(path: Path) -> Path | None:
    """Nearest ancestor (including path's own dir) containing a `.git` entry."""
    start = path if path.is_dir() else path.parent
    for p in [start, *start.parents]:
        if (p / ".git").exists():
            return p
    return None


def load_config(root: Path) -> dict:
    """Read `.gmd/config.yml` from `root`. Minimal reader: the three keys the
    linter honours (`project`, `extra_verbs`, `ignore`). Missing file or
    unparseable lines yield defaults — config is always optional."""
    cfg: dict = {"project": None, "extra_verbs": [], "ignore": []}
    f = root / ".gmd" / "config.yml"
    if not f.is_file():
        return cfg
    current_list = None
    for raw in f.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("- ") and current_list is not None:
            cfg[current_list].append(line[2:].strip().strip("\"'"))
            continue
        if ":" in line:
            key, _, val = line.partition(":")
            key, val = key.strip(), val.strip()
            if key not in cfg:
                current_list = None
                continue
            if val == "":
                cfg[key] = []
                current_list = key
            elif val.startswith("[") and val.endswith("]"):
                inner = val[1:-1].strip()
                cfg[key] = [x.strip().strip("\"'") for x in inner.split(",")] if inner else []
                current_list = None
            else:
                cfg[key] = val.strip("\"'")
                current_list = None
    return cfg


def project_name(path: Path) -> str | None:
    """The id namespace for docs under `path`. `.gmd/config.yml` `project:` wins;
    otherwise the repo directory name. SPEC §2: a doc id is unique *within a
    project*, so the project is what makes an id globally addressable."""
    resolved = (path if path.is_dir() else path.parent).resolve()
    # `~/.claude/` is not a repo but is a real shared namespace: the global
    # agents, commands and memory dirs all live there, and their ids collide
    # with every project copy unless they get a namespace of their own.
    claude_home = (Path.home() / ".claude").resolve()
    if resolved == claude_home or claude_home in resolved.parents:
        return "claude"
    # Resolve first: `_repo_root(Path("SPEC.md"))` walks from `Path(".")`, whose
    # `.name` is the empty string — that silently yielded no project at all for
    # every relative target.
    root = _repo_root(resolved)
    if root is None:
        return None
    configured = load_config(root).get("project")
    return configured or root.resolve().name or None


def id_shape_issue(path: Path, line: int, kind: str, ident: str) -> Issue | None:
    """SPEC §3: ids MAY contain `/` for hierarchy but MUST NOT start or end with
    `/`, and MUST NOT contain `//`. These were unenforced."""
    if ident.startswith("/") or ident.endswith("/"):
        return Issue(path, line, "error", kind,
                     f"id `{ident}` must not start or end with `/` (SPEC \u00a73)")
    if "//" in ident:
        return Issue(path, line, "error", kind,
                     f"id `{ident}` must not contain consecutive `//` (SPEC \u00a73)")
    return None


def _claude_memory_dir(repo_root: Path) -> Path | None:
    """The Claude memory dir for a repo, per the ~/.claude convention.

    Claude Code slugifies the project abspath by replacing every
    non-alphanumeric character with `-` (so `claude_tools` becomes
    `claude-tools`), not just the slashes. Try that form first; keep the
    old slash-only form as a fallback for dirs created by other tooling."""
    import re as _re
    base = Path.home() / ".claude" / "projects"
    for slug in (_re.sub(r"[^A-Za-z0-9]", "-", str(repo_root)),
                 str(repo_root).replace("/", "-")):
        cand = base / slug / "memory"
        if cand.is_dir():
            return cand
    return None


def _discover_corpus(target_files: list[Path]) -> list[str]:
    """--reconcile: auto-discover the resolution scope for each target.

    Walk up from each target to its repo root (nearest ancestor with a
    `.git`) and add that whole tree; also add the project's Claude memory
    dir (GMD memories are part of the cross-doc corpus) when it exists.
    Returns a deduped list of scope directories to feed the resolver, so
    a single-file lint resolves its cross-doc links against the full repo
    + memory corpus instead of warning on every unscanned target.
    """
    scopes: list[str] = []
    seen: set[Path] = set()
    for f in target_files:
        root = _repo_root(f.resolve())
        if root is None or root in seen:
            continue
        seen.add(root)
        scopes.append(str(root))
        mem = _claude_memory_dir(root)
        if mem is not None and mem.is_dir():
            scopes.append(str(mem))
    return scopes


def collect_files(targets: list[str], ignore: list[str] | None = None) -> list[Path]:
    ignore = ignore or []
    out: list[Path] = []
    for t in targets:
        p = Path(t)
        if p.is_file():
            out.append(p)
        elif p.is_dir():
            for ext in ("*.gmd", "*.md"):
                # `is_file()` filter: `gmd init` creates a `.gmd/` DIRECTORY,
                # which `rglob("*.gmd")` matches as an entry — it then surfaced
                # as a bogus `parse-fail` (IsADirectoryError) on every recursive
                # lint of a scaffolded project.
                out.extend(sorted(
                    f for f in p.rglob(ext)
                    if f.is_file() and not _is_ignored(f, ignore)
                ))
        else:
            print(f"gmd lint: not found: {t}", file=sys.stderr)
    return out


def _is_ignored(f: Path, patterns: list[str]) -> bool:
    """Match `.gmd/config.yml` `ignore:` globs against the path and its parents."""
    s = f.as_posix()
    for pat in patterns:
        pat = pat.strip()
        if not pat:
            continue
        if f.match(pat) or fnmatch.fnmatch(s, pat) or fnmatch.fnmatch(s, f"*/{pat}"):
            return True
        bare = pat.rstrip("/*").lstrip("*/")
        if bare and f"/{bare}/" in f"/{s}/":
            return True
    return False


def _parse_args(argv: list[str]) -> tuple[list[str], list[str], int | None, bool]:
    """Split argv into (targets, scope_paths, force_phase).

    `--scope <path>` (repeatable): files scanned for doc-id resolution
    only — refs from `targets` can resolve to anchors / doc-ids in
    these paths, but no issues from scope files are reported.

    Use case: a memory file references `[[task-spec-XYZ]]` that lives
    in a sibling project tree. Without scope, the ref dangles because
    the lint scan never crossed the tree boundary. With
    `--scope ~/proj/docs/`, the ref resolves and only memory-side
    issues surface in the output.

    `--phase1` / `--phase2` override phase auto-detection (returned as
    `force_phase`; None = auto = phase 2 iff a target is a directory).
    """
    targets: list[str] = []
    scopes: list[str] = []
    force_phase: int | None = None
    reconcile = False
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
        if a in ("--phase1", "--phase-1"):
            force_phase = 1
            i += 1
            continue
        if a in ("--phase2", "--phase-2"):
            force_phase = 2
            i += 1
            continue
        if a in ("--reconcile", "--reconcile-corpus"):
            reconcile = True
            i += 1
            continue
        targets.append(a)
        i += 1
    return targets, scopes, force_phase, reconcile


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    targets, scope_paths, force_phase, reconcile = _parse_args(argv)
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
    # Project-local config: extra_verbs widens the recommended vocabulary so a
    # project's own verbs stop warning. Read from the first target's repo root.
    _root = _repo_root(target_files[0])
    if _root is not None:
        _cfg = load_config(_root)
        EXTRA_VERBS.update(_cfg.get("extra_verbs") or [])
        _ignore = _cfg.get("ignore") or []
        if _ignore:
            target_files = collect_files(targets, _ignore)
    # --reconcile: auto-discover the repo + memory corpus as resolution
    # scope so a single-file lint checks its cross-doc links for real.
    if reconcile:
        scope_paths = list(scope_paths) + _discover_corpus(target_files)
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
    literal_ids = set(docs.keys())
    # A stem shared by several docs is an ambiguous address: `setdefault` below
    # silently binds it to whichever was ingested first. Record those so a ref
    # relying on one gets a warning instead of an arbitrary target.
    stem_counts: dict[str, int] = {}
    for d in docs.values():
        stem_counts[d.path.stem] = stem_counts.get(d.path.stem, 0) + 1
    ambiguous_stems = {s for s, n in stem_counts.items() if n > 1} - literal_ids
    for d in docs.values():
        by_id_or_stem.setdefault(d.path.stem, d)

    # Two-phase selection. Phase 2 (cross-doc errors) is on when a
    # directory/corpus is in scope (the scan can see referenced docs),
    # off for file-only targets so linting one new file never throws on
    # links to docs outside the scan. --phase1/--phase2 override.
    if force_phase == 1:
        cross_doc = False
    elif force_phase == 2:
        cross_doc = True
    elif reconcile:
        # --reconcile implies phase 2 (the corpus is now loaded), unless the
        # caller explicitly forced --phase1 above.
        cross_doc = True
    else:
        cross_doc = any(Path(t).is_dir() for t in targets)
    cross_doc_severity = "error" if cross_doc else "warn"

    # `resolve_refs` walks every doc in `docs` (which now includes
    # scope docs) and emits issues for any unresolved ref. Filter the
    # results to keep only issues whose source path is a target file —
    # scope files contribute resolution-only, not issue-reporting.
    ref_issues = resolve_refs(
        docs, by_id_or_stem, cross_doc_severity,
        literal_ids=literal_ids, ambiguous_stems=ambiguous_stems,
    )
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
        f" [phase {'2 cross-doc' if cross_doc else '1 doc-level'}]"
        + (
            f" (scope: +{len(scope_files)} doc(s) used for resolution only)"
            if scope_files else ""
        ),
        file=sys.stderr,
    )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
