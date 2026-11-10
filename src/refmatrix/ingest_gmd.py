"""GMD (Graph Markdown) ingest for refmatrix.

Parses `.gmd` / `.md` files with `gmd:` frontmatter and registers them in the
store:
  - Each `{#id}` node → entity of kind 'doc', name=<doc-id>#<node-id>.
  - Each `rel: <verb> -> <target>` → linkage (auto-create type).
  - Heading hierarchy → implicit `part-of` linkage on direct parents.
  - Frontmatter `imports:` → `imports` linkage on doc-level entity.
  - Title tokens + `alias=[...]` attribute → mentions concepts for retrieval.
  - `[[ref]]` outside rel: lines → `mentions` linkage.

This is what makes `rmx context <doc-id>#<node-id>` return a useful slice.
Node body text IS indexed: body term frequencies land as weighted `mentions`
edges through the weight-aware `bulk_link` path (0.35.0/0.36.1), which is what
`content_rank`'s BM25 scores over.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from refmatrix.store import Store


def _doc_content_hash(path: Path) -> str:
    """SHA1 of file bytes. Used as the resume primitive — when a file's
    hash matches the hash stored in its entity meta from a prior
    fully-completed ingest, both passes are skipped. Hash is written
    only at the END of pass2 so a crashed mid-pass2 file is re-ingested
    cleanly on resume."""
    try:
        return hashlib.sha1(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def _existing_hash_for(store: Store, name: str, kinds: tuple[str, ...]) -> str | None:
    """Read `gmd_content_hash` from an entity's meta. Returns None when
    the entity doesn't exist, has no meta, or the hash key is absent.
    Used by both the auto-resume skip path and `prestage_hashes`."""
    con = store._connect()
    placeholders = ",".join("?" * len(kinds))
    row = con.execute(
        f"SELECT meta FROM entities "
        f"WHERE partition_id=? AND kind IN ({placeholders}) AND name=? "
        f"LIMIT 1",
        (store._partition_id, *kinds, name),
    ).fetchone()
    if row is None or row[0] is None:
        return None
    try:
        meta = json.loads(row[0])
    except (ValueError, TypeError):
        return None
    h = meta.get("gmd_content_hash")
    return h if isinstance(h, str) and h else None


def _write_content_hash(store: Store, eid: int, content_hash: str) -> None:
    """Merge `gmd_content_hash` + `gmd_pass2_done=True` into an entity's
    meta JSON. Called at the END of pass2 file processing so the hash
    only marks fully-ingested state. Re-running ingest after a hash
    write is fast: hash match -> skip both passes for this file."""
    con = store._connect()
    row = con.execute(
        "SELECT meta FROM entities WHERE id=?", (eid,)
    ).fetchone()
    try:
        existing = json.loads(row[0]) if row and row[0] else {}
    except (ValueError, TypeError):
        existing = {}
    if not isinstance(existing, dict):
        existing = {}
    if existing.get("gmd_content_hash") == content_hash and existing.get("gmd_pass2_done") is True:
        # Already marked with this content: a no-op, so no write -- and no
        # `updated_at` bump. A moved file re-ingested with unchanged bytes
        # (task 26.2 AC-1) would otherwise re-stale its vector on every move
        # (`pending_embeddings` reads vectors_updated_at < updated_at).
        return
    existing["gmd_content_hash"] = content_hash
    existing["gmd_pass2_done"] = True
    con.execute(
        "UPDATE entities SET meta=?, updated_at=? WHERE id=?",
        (json.dumps(existing), time.time(), eid),
    )
    con.commit()


def prestage_hashes(store: Store, paths: list[Path], *,
                    kinds: tuple[str, ...] = ("memory", "doc"),
                    lenient: bool = False,
                    project_root: "Path | None" = None) -> dict:
    """Backfill `gmd_content_hash` for files whose entities are already
    fully ingested in the active partition.

    Bootstraps the resume feature without re-running the full pipeline:
    walks `paths`, matches each file by doc-id (frontmatter `id:` or
    filename stem) against the partition's `kind IN kinds` entities,
    and writes the current file hash + `gmd_pass2_done=True` into the
    entity meta. After this, the next `ingest_gmd_paths` call will
    skip files whose content hasn't changed.

    Assumes the current DB state reflects a successful ingest. If a
    prior ingest was interrupted mid-pass2 for some file, prestaging
    will mark that file as done — the file's stale rels won't be
    refreshed. Run a full `ingest_gmd_paths` over the suspect files
    instead.

    Returns `{"considered": N, "written": M, "skipped": K, "missing": K}`.
    """
    considered = written = skipped = missing = 0
    for path in paths:
        considered += 1
        try:
            doc = parse_gmd(path, lenient=lenient, project_root=project_root)
        except Exception:
            doc = None
        if doc is None:
            skipped += 1
            continue
        eid_row = store._connect().execute(
            "SELECT id, meta FROM entities "
            "WHERE partition_id=? AND name=? AND kind IN " +
            "(" + ",".join("?" * len(kinds)) + ") "
            "LIMIT 1",
            (store._partition_id, doc.doc_id, *kinds),
        ).fetchone()
        if eid_row is None:
            missing += 1
            continue
        existing_hash = None
        try:
            meta = json.loads(eid_row[1]) if eid_row[1] else {}
            if isinstance(meta, dict):
                existing_hash = meta.get("gmd_content_hash")
        except (ValueError, TypeError):
            pass
        current_hash = _doc_content_hash(path)
        if existing_hash == current_hash and current_hash:
            skipped += 1
            continue
        _write_content_hash(store, eid_row[0], current_hash)
        written += 1
    return {"considered": considered, "written": written,
            "skipped": skipped, "missing": missing}

# ---- spec syntax patterns -------------------------------------------------

_ID_RE = re.compile(r"\{#([a-z0-9][a-z0-9._/-]*)([^}]*)\}")
_WIKILINK_RE = re.compile(r"\[\[([^\[\]]+)\]\]")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_REL_RE = re.compile(
    r"^rel:\s+([a-z][a-z0-9-]*)\s*->\s*(\S+(?:\s+\S+)*?)(?:\s*\{([^}]*)\})?\s*$"
)
# Inline code is matched as CommonMark backtick RUNS — an opening run of N
# backticks, not adjacent to another, closes at the next run of exactly N. The
# old single-run pattern read a double-backtick span as two empty spans and
# exposed an anchor quoted inside it. Same pattern as the vendored
# tools/gmd/lint.py and slice.py, so the three parsers agree (bug-179 R3b,
# 2026-11-09). Masking keeps the line length, so column offsets stay valid.
_INLINE_CODE_RE = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)")
_CODE_FENCE_RE = re.compile(r"^(```|~~~)")
_FRONTMATTER_DELIM = "---"
_TITLE_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")
_BODY_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
_BODY_STOPWORDS = {
    "the", "and", "for", "with", "from", "this", "that", "have", "has", "had",
    "are", "was", "were", "but", "not", "any", "all", "can", "will", "would",
    "should", "could", "into", "out", "off", "via", "per", "non", "such",
    "than", "then", "when", "where", "what", "which", "while", "after", "before",
    "user", "you", "your", "they", "them", "their", "its", "it's", "don't",
    "wasn't", "isn't", "doesn't", "didn't",
}
_ATTR_LIST_RE = re.compile(r'([a-zA-Z_][\w-]*)=("[^"]*"|\[[^\]]*\]|\S+)')

# Verbs from spec §8 with their rmx linkage direction conventions.
# rmx `link(linkage, concept_id, entity_id)` packs (a, b) where the bitmap
# semantic is whatever the linkage type defines. For GMD, we always pack
# (src_node, dst_node) — query side filters by `from=` to walk forward.
RECOMMENDED_VERBS = {
    "supports", "contradicts", "derives-from", "supersedes",
    "depends-on", "instance-of", "part-of", "mentions",
    "defines", "example-of", "parent", "defined-in",
    "evidence-for", "motivates", "solves",
}


@dataclass
class GmdNode:
    id: str
    line: int
    level: int
    title: str
    parent: str | None = None
    body_lines: list[str] = field(default_factory=list)
    rels: list[tuple[int, str, str]] = field(default_factory=list)
    refs: list[tuple[int, str]] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    attrs: dict[str, str] = field(default_factory=dict)


@dataclass
class GmdDoc:
    path: Path
    doc_id: str
    title: str
    gmd_version: str
    imports: list[str]
    nodes: list[GmdNode]
    tags: list[str] = field(default_factory=list)


# ---- frontmatter (minimal YAML) -------------------------------------------

def _parse_frontmatter(lines: list[str]) -> tuple[dict, int]:
    if not lines or lines[0].strip() != _FRONTMATTER_DELIM:
        return {}, 0
    fm: dict = {}
    i = 1
    list_key: str | None = None
    while i < len(lines) and lines[i].strip() != _FRONTMATTER_DELIM:
        stripped = lines[i].strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue
        if stripped.startswith("- ") and list_key:
            fm[list_key].append(stripped[2:].strip().strip("\"'"))
            i += 1
            continue
        if ":" in stripped:
            key, _, val = stripped.partition(":")
            key, val = key.strip(), val.strip()
            if val == "":
                fm[key] = []
                list_key = key
            elif val.startswith("[") and val.endswith("]"):
                inner = val[1:-1].strip()
                fm[key] = (
                    [x.strip().strip("\"'") for x in inner.split(",") if x.strip()]
                    if inner else []
                )
                list_key = None
            else:
                fm[key] = val.strip("\"'")
                list_key = None
        i += 1
    return fm, (i + 1 if i < len(lines) else i)


def _parse_attrs(raw: str) -> tuple[dict[str, str], list[str]]:
    """Return (key=value attrs, alias list extracted from alias=[...])."""
    attrs: dict[str, str] = {}
    aliases: list[str] = []
    for k, v in _ATTR_LIST_RE.findall(raw):
        v = v.strip()
        if k == "alias" and v.startswith("[") and v.endswith("]"):
            for tok in v[1:-1].split(","):
                tok = tok.strip().strip("\"'")
                if tok:
                    aliases.append(tok)
        else:
            attrs[k] = v.strip('"')
    return attrs, aliases


# ---- doc parsing ----------------------------------------------------------

def _lenient_doc_id(path: Path, project_root: "Path | None") -> str:
    """Collision-free doc id for markdown that carries no `id:` frontmatter.

    The id IS the project-relative path, which normalizes document references
    onto one rule: **an authored doc is named by its `id:`, everything else by
    its path — the same way code entities are named.**

    `path.stem` is what authored GMD falls back to, and it is fine there because
    an author picks the filename. For plain markdown it collides immediately —
    every `README.md` in a repo becomes the doc id `README`, and they would all
    upsert onto ONE entity, silently merging unrelated documents.

    A slug (`docs-architecture-decisions`) would also be unique, but it is
    synthetic: nobody would write `[[docs-architecture-decisions#ordering]]`,
    and `resolve_entity("docs/architecture/DECISIONS.md")` — the reference a
    human or an agent actually reaches for — would miss. Using the path keeps
    the natural reference working and makes anchors read as
    `docs/architecture/DECISIONS.md#ordering`.
    """
    try:
        rel = path.resolve().relative_to(Path(project_root).resolve()) \
            if project_root else Path(path.name)
    except Exception:
        rel = Path(path.name)
    return rel.as_posix() or path.name


def parse_gmd(path: Path, *, lenient: bool = False,
              project_root: "Path | None" = None,
              memory_ids: bool = False) -> GmdDoc | None:
    """Parse a GMD doc.

    Strict (default): returns None unless the file carries `gmd:` frontmatter.

    `lenient=True` parses PLAIN markdown with the same machinery. The heading
    tree, body lines, anchors and `part-of` containment all come from the
    markdown structure itself — the only things frontmatter adds are the
    explicit `id:`, `title:`, `tags:` and `imports:`, and of those only the id
    matters for correctness (see `_lenient_doc_id`). `rel:` lines are still
    read if present, so a plain file that happens to use them keeps its edges.

    This exists because the main ingest path must content-index markdown that
    is NOT authored GMD — generated reports, vendored READMEs, sub-project
    docs. Without it those files register as entities with no body terms and
    are unretrievable by their own content at any k.
    """
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    fm, body_start = _parse_frontmatter(lines)
    if "gmd" not in fm and not lenient:
        return None
    # `memory_ids`: a curated memory file is named by its frontmatter `id`,
    # else its STEM (the memory-file rule: id == filename stem) — never the
    # path-shaped lenient id, which would name it `note.md`.
    doc_id = fm.get("id") or (
        path.stem if memory_ids else
        (_lenient_doc_id(path, project_root) if lenient else path.stem))
    title = fm.get("title") or doc_id
    _tags = fm.get("tags")
    tags = _tags if isinstance(_tags, list) else []
    _imports = fm.get("imports")
    imports = _imports if isinstance(_imports, list) else []

    nodes: list[GmdNode] = []
    by_id: dict[str, GmdNode] = {}
    root = GmdNode(id="__root__", line=body_start, level=0, title=title)
    nodes.append(root)
    by_id[root.id] = root

    stack: list[GmdNode] = [root]
    current = root
    in_code = False
    auto = 0

    for idx in range(body_start, len(lines)):
        line = lines[idx]
        line_no = idx + 1

        if _CODE_FENCE_RE.match(line.strip()):
            in_code = not in_code
            current.body_lines.append(line)
            continue
        if in_code:
            current.body_lines.append(line)
            continue

        scan = _INLINE_CODE_RE.sub(lambda m: " " * len(m.group(0)), line)

        hm = _HEADING_RE.match(line)
        if hm:
            level = len(hm.group(1))
            rest = hm.group(2)
            # The anchor is read from `scan`, as the body branch and lint read
            # it: on the raw heading a backtick-quoted `{#x}` in the title was
            # taken for the id (bug-179 R3, 2026-11-09). `scan` has the same
            # length as `line`, so the match maps onto `rest` by the heading-
            # prefix offset, and the title cuts only that one span — never
            # `_ID_RE.sub`, which would also delete the quoted `{#x}`.
            off = hm.start(2)
            idm = _ID_RE.search(scan, off)
            if idm:
                nid = idm.group(1)
                node_attrs, aliases = _parse_attrs(idm.group(2))
                a, b = idm.start() - off, idm.end() - off
                heading_text = (rest[:a] + rest[b:]).strip()
            else:
                auto += 1
                nid = f"_h{auto}"
                node_attrs, aliases = {}, []
                heading_text = rest.strip()
            if nid in by_id:
                auto += 1
                nid = f"{nid}_{auto}"
            while stack and stack[-1].level >= level:
                stack.pop()
            parent = stack[-1] if stack else root
            node = GmdNode(
                id=nid, line=line_no, level=level,
                title=heading_text, parent=parent.id,
                attrs=node_attrs, aliases=aliases,
            )
            stack.append(node)
            nodes.append(node)
            by_id[nid] = node
            current = node
            continue

        rm = _REL_RE.match(line) if line.startswith("rel:") else None
        if rm:
            verb = rm.group(1)
            target = rm.group(2).strip()
            current.rels.append((line_no, verb, target))
            current.body_lines.append(line)
            continue

        current.body_lines.append(line)

        # A `rel:`-prefixed line is never a block, well-formed or not: SPEC §5
        # gives its trailing `{...}` to edge attributes. A malformed one used to
        # fall through to the anchor scan below and register its id, while lint
        # keys the same rule on the bare prefix (bug-179 R2/d8, 2026-11-09).
        # Its wikilinks are still harvested below, as before.
        is_rel_line = line.startswith("rel:")

        # A `{#id}` on a paragraph or list item is a NODE, not decoration.
        # GMD's primer says an anchor is "a stable node id for any heading,
        # paragraph, or list item"; `tools/gmd/lint.py` implemented that and
        # this parser did not, so for months a `rel:` edge aimed at a
        # list-item anchor linted clean and resolved to nothing in the graph.
        # 71 of the 73 anchors in workflow/bullshit/IMPRESSIONS.md — every
        # per-run `{#imp-*}` the audit ledger cites — were invisible here
        # (bug-036). Two parsers, one syntax, never compared.
        bm = None if is_rel_line else _ID_RE.search(scan)
        if bm and line.strip():
            bid = bm.group(1)
            # Never shadow an existing id: the heading branch owns collisions,
            # and a body anchor that silently displaced one would move edges.
            if bid not in by_id:
                b_attrs, b_aliases = _parse_attrs(bm.group(2))
                b_node = GmdNode(
                    id=bid, line=line_no, level=current.level + 1,
                    title=_ID_RE.sub("", line).strip().lstrip("-*").strip(),
                    parent=current.id, attrs=b_attrs, aliases=b_aliases,
                )
                b_node.body_lines.append(line)
                nodes.append(b_node)
                by_id[bid] = b_node
        # `current` is deliberately NOT reassigned. The spec attaches a `rel:`
        # to the nearest enclosing block with an id, which now includes a list
        # item — but measured over docs/, workflow/, eval/ and CLAUDE.md that
        # would move 32 of 599 existing edges (5.3%) to a different owner.
        # Making ids RESOLVABLE is reversible; re-pointing live edges is not,
        # so it is a separate decision with its own measurement (bug-036).

        for wm in _WIKILINK_RE.finditer(scan):
            current.refs.append((line_no, wm.group(1).strip()))

    return GmdDoc(
        path=path, doc_id=doc_id, title=title,
        gmd_version=str(fm.get("gmd", "lenient")),
        imports=imports, nodes=nodes, tags=tags,
    )


# ---- ref resolution -------------------------------------------------------

def _split_ref(ref: str) -> tuple[str | None, str]:
    ref = ref.strip()
    if ref.startswith("#"):
        return None, ref[1:]
    if "#" in ref:
        d, _, a = ref.partition("#")
        return d, a
    return ref, ""


def _entity_name(doc_id: str, node_id: str) -> str:
    if node_id == "__root__" or not node_id:
        return doc_id
    return f"{doc_id}#{node_id}"


_ADR_GMD_ID_RE = re.compile(r"^adr-(\d{4})-")


def _adr_slash_alias(doc_id: str) -> str | None:
    """If `doc_id` is an ADR-style GMD id like `adr-0078-json-schema-as-type-
    authority`, return the slash-form alias `adr/0078` used by the
    non-GMD ADR ingester. Allows GMD rel: edges and prose searches to
    resolve regardless of which form the caller used."""
    m = _ADR_GMD_ID_RE.match(doc_id)
    return f"adr/{m.group(1)}" if m else None


def _resolve_target_eid(
    store, eid_by_name: dict, target_name: str
) -> int | None:
    """Look up a wikilink target across this batch (`eid_by_name`) AND the
    persistent store. The batch-only dict misses any target that was
    ingested in a prior call — per-file watcher ingests and partial-tree
    invocations would silently drop every cross-file rel: edge without
    this DB fallback."""
    eid = eid_by_name.get(target_name)
    if eid is not None:
        return eid
    # Try concept (node anchors `doc#id`) then doc, then memory (a bare doc-id
    # ingested with --as-memory is a `kind=memory` entity, NOT a doc/concept).
    # `memory` MUST be in this list: once the duplicate `__root__` concept is no
    # longer minted, a cross-doc `[[slug]]` target only exists as the memory,
    # and omitting it here would drop every memory->memory rel: edge.
    for kind in ("concept", "doc", "memory"):
        e = store.get_entity(kind, target_name)
        if e is not None:
            eid_by_name[target_name] = e.id  # cache for the rest of this batch
            return e.id
    return None


# ---- ingest ---------------------------------------------------------------

@dataclass
class IngestStats:
    docs: int = 0
    nodes: int = 0
    rels: int = 0
    mentions: int = 0
    linkage_types_added: set[str] = field(default_factory=set)
    unresolved: list[tuple[Path, int, str]] = field(default_factory=list)
    # Files the pass-1 loop did NOT ingest, COUNTED (plan-5 task 5.1: the
    # 0.66.1 bridge skipped 21 memory files with a bare `continue`, and the
    # SessionStart recall said "no memories" on a store that was behind).
    skipped_non_gmd: int = 0                       # strict mode: no `gmd:` frontmatter
    skipped_unparseable: list[tuple[Path, str]] = field(default_factory=list)
    skipped_index: list[str] = field(default_factory=list)   # MEMORY.md: an index, not a memory
    # --as-memory replaces a prior kind='doc' entity; a purge that failed is counted (bug-111).
    doc_drop_failed: list[tuple[Path, str]] = field(default_factory=list)
    # Task 26.2 (2026-11-10): the path-aware resume gate's terms. A memory file
    # whose stored `source_path` disagrees with its resolved path is re-ingested
    # once and lands in exactly ONE term, by the stored path's shape (spec
    # #impl-notes-r5 m3): missing or symlink-form -> `stale_before`; a real,
    # different path -> `moved`. `moved_legacy` is a ROW count: the other rows
    # (legacy `memory_sync_disk` duplicates) on a moved file's old path,
    # refreshed with it (AC-1b, r6-lite n2). `forced` counts save-states 26.5
    # AC-5 forces through the gate; nothing forces yet, so it reads 0 until
    # 26.5 lands -- it is printed so the post-apply comparison (26.8) has the
    # same four terms before and after. `skipped_unchanged`: files the gate
    # skipped (hash match, and in an organised memdir a literal path match).
    moved: int = 0
    stale_before: int = 0
    forced: int = 0
    moved_legacy: int = 0
    skipped_unchanged: int = 0
    # AC-4: an id claimed by two or more files in one walk -- neither is
    # written; `(id, [paths])`, in walk order.
    duplicate_ids: list[tuple[str, list[Path]]] = field(default_factory=list)
    # An unreadable `.memory-layout` met by the gate (the path-aware rule was
    # applied there; `_OrganisedDirs`), named in the report.
    marker_errors: list[str] = field(default_factory=list)

    @property
    def refresh_pending(self) -> int:
        """AC-3's pre-registered quantity (r6-lite n2): the three file terms +
        `moved_legacy`. 26.5 AC-8 re-exports the same number."""
        return self.moved + self.stale_before + self.forced + self.moved_legacy

    def as_dict(self) -> dict:
        """The counters, structurally — for the daemon result and the
        bridge's callers (ch-bsd plan-5 #m-7: no report scraping)."""
        return {"docs": self.docs, "nodes": self.nodes, "rels": self.rels,
                "mentions": self.mentions, "unresolved": len(self.unresolved),
                "skipped_non_gmd": self.skipped_non_gmd,
                "skipped_unparseable": [[str(p), e] for p, e in self.skipped_unparseable],
                "skipped_index": list(self.skipped_index),
                "doc_drop_failed": [[str(p), e] for p, e in self.doc_drop_failed],
                "moved": self.moved, "stale_before": self.stale_before,
                "forced": self.forced, "moved_legacy": self.moved_legacy,
                "skipped_unchanged": self.skipped_unchanged,
                "duplicate_ids": [[i, [str(p) for p in ps]]
                                  for i, ps in self.duplicate_ids],
                "marker_errors": list(self.marker_errors)}

    def refresh_lines(self, *, always: bool = False) -> list[str]:
        """`<term>: N` for the four refresh terms (AC-3). The bridge report
        prints the non-zero ones; `--dry-run` prints all four plus
        `refresh_pending` (`always=True`)."""
        terms = [("moved", self.moved), ("stale_before", self.stale_before),
                 ("forced", self.forced), ("moved_legacy", self.moved_legacy)]
        lines = [f"{t}: {n}" for t, n in terms if always or n]
        if always:
            lines.insert(0, f"refresh_pending: {self.refresh_pending}")
        return lines

    def duplicate_lines(self) -> list[str]:
        """AC-4: the refused ids, every claiming path named (never truncated:
        each one is a memory that did not reach the store)."""
        if not self.duplicate_ids:
            return []
        lines = [f"duplicate_ids: {len(self.duplicate_ids)} (neither file written; "
                 f"give each memory its own frontmatter id)"]
        for i, ps in self.duplicate_ids:
            lines.append(f"  {i}: " + ", ".join(str(p) for p in ps))
        return lines

    def report(self) -> str:
        lines = [
            f"ingested {self.docs} doc(s), {self.nodes} node(s), "
            f"{self.rels} rel: edge(s), {self.mentions} mention(s)",
            f"skipped_non_gmd: {self.skipped_non_gmd}",
            f"skipped_unparseable: {len(self.skipped_unparseable)}",
        ]
        if self.skipped_unchanged:
            lines.append(f"skipped_unchanged: {self.skipped_unchanged}")
        lines.extend(self.refresh_lines())
        lines.extend(self.duplicate_lines())
        for err in self.marker_errors:
            lines.append(f"marker_error: {err}")
        if self.skipped_index:
            lines.append(f"skipped_index: {len(self.skipped_index)} "
                         f"({', '.join(self.skipped_index)})")
        for p, err in self.skipped_unparseable[:20]:
            lines.append(f"  {p}: {err}")
        if len(self.skipped_unparseable) > 20:
            lines.append(f"  ... and {len(self.skipped_unparseable) - 20} more")
        if self.doc_drop_failed:
            lines.append(f"doc_drop_failed: {len(self.doc_drop_failed)}")
            for p, err in self.doc_drop_failed[:20]:
                lines.append(f"  {p}: {err}")
        if self.linkage_types_added:
            lines.append(
                "new linkage types: "
                + ", ".join(sorted(self.linkage_types_added))
            )
        if self.unresolved:
            lines.append(f"unresolved refs: {len(self.unresolved)}")
            for p, ln, r in self.unresolved[:10]:
                lines.append(f"  {p}:{ln}: [[{r}]]")
            if len(self.unresolved) > 10:
                lines.append(f"  ... and {len(self.unresolved) - 10} more")
        return "\n".join(lines)


def _doc_authority(doc) -> float:
    """Source-authority multiplier for a GMD doc's typed `rel:` edges.

    An ADR's `supersedes`/`implements`/`depends-on` is a decision record;
    a design doc's is a commitment; ordinary prose is baseline. Applies to
    rel: edges ONLY — the mentions/content channels carry term frequency
    and must stay multiplier-free. Env-tunable: RMX_ADR_AUTHORITY (3.0),
    RMX_DESIGN_AUTHORITY (1.5)."""
    import os as _os
    tags = {str(tg).lower() for tg in (doc.tags or [])}
    path_l = str(doc.path).lower()
    try:
        adr = float(_os.environ.get("RMX_ADR_AUTHORITY", "3.0") or "3.0")
    except ValueError:
        adr = 3.0
    try:
        design = float(_os.environ.get("RMX_DESIGN_AUTHORITY", "1.5") or "1.5")
    except ValueError:
        design = 1.5
    if "adr" in tags or "/adr/" in path_l:
        return adr
    if tags & {"design", "plan", "architecture"}:
        return design
    return 1.0


def _ensure_linkage(store: Store, verb: str, stats: IngestStats) -> None:
    """Ensure linkage type exists; record in stats if newly created."""
    try:
        store.get_linkage_id(verb)
    except KeyError:
        store.add_linkage_type(
            verb, directed=True,
            description=f"GMD verb '{verb}'",
        )
        stats.linkage_types_added.add(verb)


def _title_concept_tokens(title: str) -> list[str]:
    """Identifier-shaped tokens from a heading title for retrieval surfaces.

    Stopword-filtered on the same list as the body TF pass. Without this,
    a prose heading ("What the config does after boot") files `What`, `the`,
    `after` as weight-2.0 `mentions` concepts — they then dominate the
    `mentions` walk on the doc entity and pull in unrelated nodes from other
    repos that happen to share a common word."""
    return [t for t in _TITLE_TOKEN_RE.findall(title)
            if t.lower() not in _BODY_STOPWORDS]


def _body_term_frequencies(body_lines: list[str]) -> dict[str, int]:
    """TF map over node body. Lowercase, stopword-filtered, length>=3."""
    tf: dict[str, int] = {}
    for line in body_lines:
        if line.startswith("rel:"):
            continue
        for m in _BODY_TOKEN_RE.findall(line):
            t = m.lower()
            if len(t) < 3 or t in _BODY_STOPWORDS:
                continue
            tf[t] = tf.get(t, 0) + 1
    return tf


# How many leading body lines count as the "lead" of a node.
_LEAD_LINES = 3


def _body_terms_on() -> bool:
    """Emit the per-node body term-frequency sweep. ON by default.

    `RMX_GMD_BODY_TERMS=0` ingests a document's STRUCTURE without its PROSE:
    entities, `part-of` containment, title tokens, aliases, tags and every
    `rel:` edge still land; only the body tf sweep is skipped.

    This exists for operational content — plans, handoffs, session summaries.
    The standing rule keeps that material out of the concept graph because it
    "co-mentions nearly everything, so it dominates co-mention weights and
    drowns out specs/code". That objection is specifically about BODY TERMS.
    A plan's durable residue is its decisions and its `supersedes` /
    `implements` / `depends-on` edges, which outlive the process narrative and
    carry none of the co-mention mass. This flag keeps the second and drops
    the first."""
    return os.environ.get("RMX_GMD_BODY_TERMS", "1") not in ("0", "false", "False")


def _coref_on() -> bool:
    """Resolve pronouns to antecedents during the memory ingest and emit the
    counts as a `coref` linkage (see coref.py). OFF by default until the
    retrieval effect is measured; `RMX_INGEST_COREF=1` enables. The stored
    resolutions also let the embedder substitute antecedents into the text
    it encodes, so both channels ride one sidecar."""
    return os.environ.get("RMX_INGEST_COREF", "0") not in ("0", "false", "False")


def _lead_terms_on() -> bool:
    """Record which terms appear in a node's OPENING lines, as a `lead`
    linkage. OFF by default; `RMX_LEAD_TERMS=1` enables. Requires re-ingest.

    `_body_term_frequencies` is position-blind: a term on line 1 and a term on
    line 400 produce the same tf and are indistinguishable afterwards. Lead
    position is one of the oldest signals in IR — prose states its subject
    early — and it is free to capture here because the parser already has the
    body split into lines.

    Recorded as a LINKAGE, not folded into `mentions.weight`, for the same
    reason title tokens should not be: `weight` is read as term frequency by
    BM25 and summed into document length, so an importance judgement placed
    there is both saturated and self-penalising.

    ON by default as of the measurement below — the only structural signal of
    eight that this corpus could test AND that paid. MemAware `context`,
    90 HELD-OUT questions (disjoint from the set the boost weight was tuned
    on): MRR 0.206 -> 0.248 (+20%), hit@20 0.378 -> 0.511 (+35%). The gain
    replicates the tuning set's +21% MRR, so it is not selection.

    Costs ~7% more edges (44.5k `lead` rows on a 1307-document corpus) and
    needs a re-ingest before an existing store benefits.
    `RMX_LEAD_TERMS=0` opts out."""
    return os.environ.get("RMX_LEAD_TERMS", "1") not in ("0", "false", "False")


def _lead_term_keys(body_lines: list[str]) -> set[str]:
    """Terms occurring in the first `_LEAD_LINES` non-empty, non-`rel:` lines."""
    lead: list[str] = []
    for line in body_lines:
        if not line.strip() or line.startswith("rel:"):
            continue
        lead.append(line)
        if len(lead) >= _LEAD_LINES:
            break
    return set(_body_term_frequencies(lead))


def _title_phrases_on() -> bool:
    """Emit the multi-word structure of a HEADING as `phrase/*` concepts.
    OFF by default; `RMX_TITLE_PHRASES=1` enables. Requires re-ingest.

    Distinct from the body phrase miner that was measured and closed. That one
    mined prose automatically: 549k keys, 82% hapax, no reachability gain.
    A title is the opposite population -- author-ASSERTED, curated, and tiny
    (1626 title tokens over 811 nodes on the MemAware corpus, so ~1.3k pairs
    against the body miner's 549k). `_title_concept_tokens` currently shreds
    "Worker lifecycle" into two independent concepts and discards the fact
    that a human wrote them as a unit.

    The reachability ceiling still applies -- a pair's documents are a subset
    of its tokens' -- so this cannot move hit@20. It can only move ranking, by
    separating documents that merely share both words from the one actually
    about the pair. That is the metric the mined version lost on, and it lost
    there because of volume, which is the objection this population does not
    have."""
    return os.environ.get("RMX_TITLE_PHRASES", "0") not in ("0", "false", "False")


def _title_phrase_keys(title: str) -> list[str]:
    """Alphabetized co-occurring token pairs from a heading, same identity the
    body miner uses (see `ingest.text_phrases`) so the two agree on what a
    phrase key looks like."""
    from refmatrix.ingest import text_phrases
    toks = _title_concept_tokens(title)
    if len(toks) < 2:
        return []
    return list(text_phrases(" ".join(toks), stop=frozenset()))


def _split_title_links() -> bool:
    """Write title tokens and aliases as their own linkages instead of as
    weighted `mentions`. OFF by default; `RMX_SPLIT_TITLE_LINKS=1` enables.

    `mentions.weight` is read as TERM FREQUENCY by `content_rank`'s BM25 (and,
    summed, as document length). Writing 2.0 for a title token and 3.0 for an
    alias puts an importance judgement into a frequency field, and the two are
    then indistinguishable downstream: a stored 3.0 could mean "occurred three
    times" or "is an alias", and nothing can tell them apart afterwards.

    It is not a rounding error either. Measured on the MemAware corpus, 99.5%
    of title tokens (1618 of 1626) never appear in their node's body, so the
    fabricated 2.0 is what BM25 actually scores for them -- and title tokens
    are the most discriminative terms a document has.

    With this on, `mentions` carries only real counts (a title token occurred
    once, in the heading) and the structural fact moves to `titles`/`aliases`,
    where a ranker can consult it deliberately. Requires re-ingest."""
    return os.environ.get("RMX_SPLIT_TITLE_LINKS", "0") not in ("0", "false", "False")


def _body_phrases(body_lines: list[str]) -> dict[str, int]:
    """Co-occurring content-word pairs over a node body, as `phrase/*` keys.

    Same miner the docstring pass uses, handed the PROSE stoplist so phrases
    and body terms agree on what counts as content. Bodies are joined with
    newlines because the miner treats a line break as a clause break -- a
    phrase never spans two lines.
    """
    from refmatrix.ingest import text_phrases
    text = "\n".join(l for l in body_lines if not l.startswith("rel:"))
    return dict(text_phrases(text, stop=_BODY_STOPWORDS))


# ---- task 26.2: the path-aware memory gate + the duplicate-id refusal ----------
#
# WHY (ch-bsd plan-26 r1, reproduced on the production CLI): the resume gate
# skipped a memory file when the stored `gmd_content_hash` for its NAME
# matched, so a file moved with its bytes unchanged was skipped and its row
# kept `source_path=<old path>` and its `x#anchor` concepts `path=<old path>`.
# Organising a memdir (26.5) moves every file. The gate below reuses the path
# the row ALREADY records (no second key, r1 #s5) and is marker-gated (AC-3b):
# only files under an organised memdir (`memory_layout.is_organised`) get it,
# so the deploy causes no fleet-wide refresh. ONE classifier serves the bridge
# and `--dry-run`, so the measured `refresh_pending` is the refresh the bridge
# then performs.


@dataclass
class _MemRow:
    """The id row a memory file maps to: its entity id, the stored hash, and
    the stored `memory_content.metadata.source_path` (None when absent)."""
    eid: int
    content_hash: "str | None"
    source_path: "str | None"


def _memory_row(store: Store, name: str) -> "_MemRow | None":
    con = store._connect()
    row = con.execute(
        "SELECT e.id, e.meta, mc.metadata FROM entities e "
        "LEFT JOIN memory_content mc ON mc.entity_id = e.id "
        "WHERE e.partition_id = ? AND e.kind = 'memory' AND e.name = ? LIMIT 1",
        (store._partition_id, name)).fetchone()
    if row is None:
        return None

    def _obj(raw) -> dict:
        try:
            v = json.loads(raw) if raw else {}
        except (TypeError, ValueError):
            return {}
        return v if isinstance(v, dict) else {}
    h = _obj(row[1]).get("gmd_content_hash")
    sp = _obj(row[2]).get("source_path")
    return _MemRow(int(row[0]), h if isinstance(h, str) and h else None,
                   sp if isinstance(sp, str) and sp else None)


def parse_path_map(specs) -> list[tuple[str, str]]:
    """`--path-map FROM=TO` specs -> `[(from, to)]`, longest `from` first.
    Fail-closed: a spec without `=` or with an empty side RAISES (a silently
    dropped map would report the ~100% relocation it exists to remove)."""
    out: list[tuple[str, str]] = []
    for spec in specs or ():
        frm, sep, to = str(spec).partition("=")
        frm, to = frm.strip().rstrip("/"), to.strip().rstrip("/")
        if not sep or not frm or not to:
            raise ValueError(f"--path-map {spec!r}: expected FROM=TO with both sides non-empty")
        out.append((frm, to))
    out.sort(key=lambda ft: len(ft[0]), reverse=True)
    return out


def _map_path(p: "str | None", path_map: "list[tuple[str, str]] | None") -> "str | None":
    """Rewrite a STORED path through `--path-map` (AC-3 relocated twin): the
    first `from` that is `p` or a directory prefix of it wins."""
    if p is None or not path_map:
        return p
    for frm, to in path_map:
        if p == frm or p.startswith(frm + "/"):
            return to + p[len(frm):]
    return p


class _OrganisedDirs:
    """Which files are under an organised memdir (AC-3b): the nearest ancestor
    carrying `.memory-layout`, read by `memory_layout.is_organised`. Cached per
    directory: one stat per ancestor per run.

    An UNREADABLE marker is never read as 'not organised' (ADR-0005
    #marker-encoding) and never fails the ingest (task 26.6: the memories are
    saved, the index is not regenerated). The gate takes the path-aware rule
    there -- a refresh only re-points provenance, identity is the id -- and the
    error is kept on `errors` for the report (CLAUDE.md #no-silent-failures)."""

    def __init__(self) -> None:
        self._cache: dict[Path, bool] = {}
        self.errors: list[str] = []

    def __call__(self, path: Path) -> bool:
        from refmatrix.memory_layout import MARKER_NAME, MemoryLayoutError, is_organised
        seen: list[Path] = []
        result = False
        for d in Path(path).resolve().parents:
            if d in self._cache:
                result = self._cache[d]
                break
            seen.append(d)
            if (d / MARKER_NAME).exists():
                try:
                    result = is_organised(d)
                except MemoryLayoutError as exc:
                    self.errors.append(f"{exc} -- the path-aware gate applied under {d}")
                    result = True
                break
        for d in seen:
            self._cache[d] = result
        return result


class _SourcePathIndex:
    """Memory rows by RESOLVED stored `source_path` (after `--path-map`), built
    lazily once per run -- the lookup HEAD never had (AC-1b: HEAD only wrote
    `source_path`). Kept current as the run refreshes rows."""

    def __init__(self, store: Store, path_map) -> None:
        self._store = store
        self._map = path_map
        self._by_path: "dict[str, list[tuple[int, str]]] | None" = None

    def _load(self) -> dict:
        if self._by_path is None:
            self._by_path = {}
            for eid, name, meta in self._store._connect().execute(
                    "SELECT e.id, e.name, mc.metadata FROM entities e "
                    "JOIN memory_content mc ON mc.entity_id = e.id "
                    "WHERE e.partition_id = ? AND e.kind = 'memory'",
                    (self._store._partition_id,)).fetchall():
                try:
                    sp = (json.loads(meta) if meta else {}).get("source_path")
                except (TypeError, ValueError, AttributeError):
                    sp = None
                if isinstance(sp, str) and sp:
                    key = str(Path(_map_path(sp, self._map)).resolve())
                    self._by_path.setdefault(key, []).append((int(eid), str(name)))
        return self._by_path

    def rows_on(self, resolved_old: str, exclude: "set[int]") -> list[tuple[int, str]]:
        return [r for r in self._load().get(resolved_old, []) if r[0] not in exclude]

    def moved(self, eids: "list[int]", old: str, new: str) -> None:
        idx = self._load()
        gone = set(eids)
        keep = [r for r in idx.get(old, []) if r[0] not in gone]
        moved = [r for r in idx.get(old, []) if r[0] in gone]
        idx[old] = keep
        idx.setdefault(new, []).extend(moved)


@dataclass
class _GateDecision:
    """What the memory gate decided for one file. `term` is the ONE refresh
    term (`moved` / `stale_before`) or None; `legacy` the other rows on a
    moved file's old path, refreshed with it."""
    skip: bool
    term: "str | None" = None
    legacy: list = field(default_factory=list)
    old_resolved: "str | None" = None


def _memory_gate(row: "_MemRow | None", current_hash: str, resolved: str, *,
                 path_aware: bool, path_map, index: "_SourcePathIndex",
                 walk_eids: "set[int]") -> _GateDecision:
    """THE memory resume gate (bridge and `--dry-run` alike).

    Hash-only (HEAD's gate, un-organised dirs, AC-3b): skip when the stored
    hash matches. Path-aware (organised dirs, and every `--dry-run`): skip
    only when the hash matches AND the stored `source_path` EQUALS the
    resolved file path -- literally (#rd-literal): a stored path that only
    resolves to it is the symlink form and is refreshed once. A path that
    disagrees is ONE term by the stored path's shape (#impl-notes-r5 m3):
    missing, or not equal to its own resolution (symlink form) ->
    `stale_before`; otherwise -> `moved`. Whenever the file's old path
    (resolved) differs from its new one, every OTHER memory row on that old
    path -- not an id row of any file in this walk -- is refreshed with it
    (AC-1b), whatever term the id row lands in (r6-lite n2)."""
    if row is None:
        return _GateDecision(skip=False)
    hash_match = bool(current_hash) and row.content_hash == current_hash
    if not path_aware:
        return _GateDecision(skip=hash_match)
    stored = _map_path(row.source_path, path_map)
    if stored == resolved:
        return _GateDecision(skip=hash_match)
    if stored is None:
        return _GateDecision(skip=False, term="stale_before")
    old_resolved = str(Path(stored).resolve())
    term = "stale_before" if old_resolved != stored else "moved"
    legacy = []
    if old_resolved != resolved:
        legacy = index.rows_on(old_resolved, walk_eids | {row.eid})
    return _GateDecision(skip=False, term=term, legacy=legacy, old_resolved=old_resolved)


def split_claims(claims: "dict[str, list[Path]]") -> "tuple[set[str], list]":
    """AC-4: which ids this walk may write. An id claimed by ONE file is
    written; an id claimed by two or more is refused -- neither file is
    written, the stored row keeps its prior content, and the claim is
    returned as `(id, [paths])` to be counted and named (at HEAD the last file
    walked silently won). Not marker-gated: a silent last-wins is a defect in
    every dir (#rd-fresh-duplicate).

    THE single place a claim is judged. Task 26.3 (built in parallel) owns the
    one sanctioned pair -- a save-state at the top level and its
    `savestates/` copy mid-move (#rd-262-263, 26.3 #rd-duplicate-vs-262);
    its exemption and its preference between the two belong HERE, so the
    bridge and `--dry-run` cannot judge a claim two ways."""
    refused: set[str] = set()
    dups: list = []
    for doc_id, ps in claims.items():
        if len(ps) > 1:
            refused.add(doc_id)
            dups.append((doc_id, list(ps)))
    return refused, dups


def _parse_memory_walk(paths: list[Path], stats: "IngestStats", *,
                       project_root, verbose: bool) -> list:
    """Parse every memory file once: `[(path, doc, hash)]`, with the index /
    unparseable / non-GMD skips counted on `stats` exactly as pass 1 counted
    them, and contested ids (AC-4) removed and recorded. Shared by the bridge
    and `--dry-run`."""
    parsed: list = []
    for path in paths:
        try:
            current_hash = _doc_content_hash(path)
        except Exception:
            current_hash = ""
        if path.name in MEMORY_INDEX_FILES:
            # The flat index is not a memory (ch-bsd plan-5 #b-2).
            stats.skipped_index.append(path.name)
            continue
        try:
            doc = parse_gmd(path, lenient=True, project_root=project_root, memory_ids=True)
        except Exception as e:
            # Counted AND named in the report (plan-5 task 5.1).
            stats.skipped_unparseable.append((path, f"{type(e).__name__}: {e}"))
            if verbose:
                print(f"  skip {path}: {type(e).__name__}: {e}")
            continue
        if doc is None:
            stats.skipped_non_gmd += 1
            continue
        parsed.append((path, doc, current_hash))
    claims: dict[str, list[Path]] = {}
    for path, doc, _h in parsed:
        claims.setdefault(doc.doc_id, []).append(path)
    refused, dups = split_claims(claims)
    stats.duplicate_ids.extend(dups)
    return [e for e in parsed if e[1].doc_id not in refused]


def _count_term(stats: "IngestStats", decision: _GateDecision) -> None:
    if decision.term == "moved":
        stats.moved += 1
    elif decision.term == "stale_before":
        stats.stale_before += 1
    stats.moved_legacy += len(decision.legacy)


def plan_memory_refresh(store: Store, paths: list[Path], *,
                        path_map=None, project_root: "Path | None" = None) -> "IngestStats":
    """`rmx ingest-gmd --as-memory --dry-run` (AC-3): what the bridge's
    path-aware gate WOULD refresh, writing nothing. Evaluates the MARKER-ON
    rule for every file whatever the dir's marker says (r4 s2: it answers
    "what would organising refresh"); `path_map` rewrites stored paths before
    comparing (the relocated twin, r3 s2). Read-only: every statement here is
    a SELECT, so it runs on a `--store-snapshot` copy opened read-only."""
    stats = IngestStats()
    entries = _parse_memory_walk(paths, stats, project_root=project_root, verbose=False)
    rows = {doc.doc_id: _memory_row(store, doc.doc_id) for _p, doc, _h in entries}
    walk_eids = {r.eid for r in rows.values() if r is not None}
    index = _SourcePathIndex(store, path_map)
    for path, doc, h in entries:
        d = _memory_gate(rows[doc.doc_id], h, str(Path(path).resolve()), path_aware=True,
                         path_map=path_map, index=index, walk_eids=walk_eids)
        if d.skip:
            stats.skipped_unchanged += 1
        _count_term(stats, d)
    return stats


def ingest_gmd_paths(
    store: Store, paths: list[Path], verbose: bool = False,
    yield_lock: Callable[[], None] | None = None,
    yield_every: int = 10,
    as_memory: bool = False,
    memory_mtype_default: str = "curated",
    progress_cb: Callable[[str, int, int, Path], None] | None = None,
    lenient: bool = False,
    project_root: "Path | None" = None,
) -> IngestStats:
    """Two-pass ingest: parse all docs first (build id table), then link.

    Two-pass so cross-doc `[[doc-id#anchor]]` references resolve against the
    full set being ingested in this call, not just docs seen earlier.

    `yield_lock`: optional callable invoked every `yield_every` docs in
    each pass. The daemon passes a callback that releases + reacquires its
    `_store_lock` so CLI ops can interleave during a long ingest. Without
    this, a multi-thousand-file ingest holds the lock the entire time and
    `rmx query`, `rmx stats`, etc. queue behind it until completion. See
    daemon `_op_ingest_gmd` for the standard daemon callback.

    `as_memory`: when True, each doc-level entity is registered as
    `kind=memory` and a memory_content sidecar is upserted from the doc
    body + frontmatter. This is the path curated `.md` memories take
    so they participate in `rmx memory recall`. Node-level anchors stay
    `kind=concept` regardless — they're still graph-citation points,
    not memory bodies. The frontmatter's `metadata.type` becomes the
    memory mtype (falls back to `memory_mtype_default`).
    """
    stats = IngestStats()

    # Resolved once per run, not per node: `phrases_enabled()` reads the
    # environment and both emission sites sit inside the per-doc loop.
    from refmatrix.ingest import phrases_enabled
    _phrases_on = phrases_enabled()

    # Intra-doc lock-yield cadence. `yield_lock` fires between DOCS, but a
    # single huge doc (e.g. a live session transcript with thousands of
    # nodes) would otherwise hold `_store_lock` for its entire node loop —
    # long enough to time out CLI pings and stall every queued write. Tick
    # the same yield callback every N node-ops so one giant file can't
    # monopolize the writer. Same safety as the inter-doc yield (per-batch
    # commits; no open transaction spans the release).
    import os as _os
    node_yield_every = max(1, int(
        _os.environ.get("RMX_INGEST_NODE_YIELD_EVERY", "200") or "200"
    ))
    _node_ops = [0]

    def _node_tick() -> None:
        if yield_lock is None:
            return
        _node_ops[0] += 1
        if _node_ops[0] % node_yield_every == 0:
            yield_lock()

    # ---- pass 1: parse + register entities -------------------------------
    docs: list[GmdDoc] = []
    eid_by_name: dict[str, int] = {}
    # Doc-level entity ids, indexed by doc_id. Kept separate from
    # `eid_by_name` because that map is overwritten by the `__root__`
    # anchor (its `_entity_name` collapses to the bare doc_id). Pass2's
    # resume marker writes the file hash onto THIS eid — the
    # memory/doc-kind row — not the concept eid that ends up under the
    # same key in `eid_by_name`.
    doc_level_eid: dict[str, int] = {}
    pass1_processed = 0
    # The resume gate must look at the kind THIS ingest produces: a file
    # ingested earlier as a doc is not "already bridged" for a memory run
    # (ch-bsd plan-5 #s-3 follow-up: the bridge after a plain doc ingest over
    # the memory dir created no memory rows because the doc row's hash
    # matched).
    skip_lookup_kinds = ("memory",) if as_memory else ("doc",)
    # Map doc_id -> SHA1 of the file content captured at pass1 entry.
    # Used by pass2's final per-file step to mark the entity as fully
    # ingested with this content. Recorded once at the START so a
    # concurrent file edit during ingest doesn't pollute the marker.
    file_hashes: dict[str, str] = {}
    # Files we recognize as "fully ingested with this content" — both
    # passes skip work for these. Just register the entity id in
    # `eid_by_name` so cross-doc wikilink resolution still finds them.
    skip_docs: set[str] = set()

    # Parse first, write second (task 26.2 AC-4): a contested id must be known
    # before EITHER claimant is written, or the last file walked silently wins.
    entries: list = []
    if as_memory:
        entries = _parse_memory_walk(paths, stats, project_root=project_root,
                                     verbose=verbose)
    else:
        for path in paths:
            # Resume fast path: if an entity for this doc already exists
            # with a matching gmd_content_hash, skip both passes. The hash
            # is only set at the END of pass2, so a partial prior ingest
            # leaves the hash unset and we re-process.
            try:
                current_hash = _doc_content_hash(path)
            except Exception:
                current_hash = ""
            try:
                doc = parse_gmd(path, lenient=lenient, project_root=project_root)
            except Exception as e:
                # Counted AND named in the report (plan-5 task 5.1).
                stats.skipped_unparseable.append((path, f"{type(e).__name__}: {e}"))
                if verbose:
                    print(f"  skip {path}: {type(e).__name__}: {e}")
                continue
            if doc is None:
                stats.skipped_non_gmd += 1
                continue
            entries.append((path, doc, current_hash))

    # The memory gate's inputs (task 26.2): each file's id row, read once; the
    # id rows of the whole walk (never refreshed as some other file's legacy
    # row); the organised-dir test (AC-3b); the old-path index (AC-1b).
    mem_rows: dict[str, "_MemRow | None"] = {}
    walk_eids: set[int] = set()
    organised = _OrganisedDirs()
    path_index = _SourcePathIndex(store, None)
    if as_memory:
        mem_rows = {doc.doc_id: _memory_row(store, doc.doc_id) for _p, doc, _h in entries}
        walk_eids = {r.eid for r in mem_rows.values() if r is not None}

    for path, doc, current_hash in entries:
        gate: "_GateDecision | None" = None
        path_aware = False
        resolved_path = str(Path(path).resolve())
        if as_memory:
            path_aware = organised(path)
            gate = _memory_gate(mem_rows.get(doc.doc_id), current_hash, resolved_path,
                                path_aware=path_aware, path_map=None, index=path_index,
                                walk_eids=walk_eids)
            if current_hash:
                file_hashes[doc.doc_id] = current_hash
            row = mem_rows.get(doc.doc_id)
            if gate.skip and row is not None:
                # Unchanged (hash, and in an organised dir the literal path):
                # register the id for pass-2 cross-refs and write nothing.
                stats.skipped_unchanged += 1
                docs.append(doc)
                stats.docs += 1
                eid_by_name[doc.doc_id] = row.eid
                doc_level_eid[doc.doc_id] = row.eid
                skip_docs.add(doc.doc_id)
                pass1_processed += 1
                if progress_cb is not None:
                    progress_cb("pass1-skip", pass1_processed, len(paths), path)
                continue
            _count_term(stats, gate)
        elif current_hash:
            file_hashes[doc.doc_id] = current_hash
            existing_hash = _existing_hash_for(
                store, doc.doc_id, skip_lookup_kinds,
            )
            if existing_hash == current_hash:
                # Lookup the entity id once and stash it for pass2
                # cross-ref resolution. Skip all writes for this file.
                row = store._connect().execute(
                    "SELECT id FROM entities "
                    "WHERE partition_id=? AND name=? "
                    f"  AND kind IN ({', '.join('?' for _ in skip_lookup_kinds)}) LIMIT 1",
                    (store._partition_id, doc.doc_id, *skip_lookup_kinds),
                ).fetchone()
                if row is not None:
                    docs.append(doc)
                    stats.docs += 1
                    eid_by_name[doc.doc_id] = row[0]
                    doc_level_eid[doc.doc_id] = row[0]
                    skip_docs.add(doc.doc_id)
                    pass1_processed += 1
                    if progress_cb is not None:
                        progress_cb(
                            "pass1-skip", pass1_processed, len(paths), path,
                        )
                    continue
        docs.append(doc)
        stats.docs += 1

        # doc-level entity (represents the whole file). When
        # `as_memory`, route through add_memory so the entity lands in
        # kind=memory + a memory_content sidecar gets populated. That
        # is the path curated .md memory files need to participate in
        # `rmx memory recall`'s kind-filtered ann_search.
        if as_memory:
            # Drop a prior kind=doc entity for this name if one exists
            # (typical: a previous `rmx ingest-gmd` without --as-memory).
            # Leaves the (partition, kind=memory, name) slot free for
            # add_memory below. Idempotent — no-op when none exists.
            # Through purge_entity, never a bare DELETE: the raw row delete
            # left the doc's entity_links rows (both sides), fragment bits and
            # vector naming a dead id, which the fragment repair later turned
            # back into bits (bug-111, cliquedb 2026-10-14).
            # Matched on path as well as name (r1 #4): a project doc in the same partition whose
            # GMD id equals a memory file's id is a different file and is not this one's prior row.
            try:
                vec_failed0 = getattr(store, "vector_delete_failures", 0)
                for (old_id,) in store._connect().execute(
                    "SELECT id FROM entities WHERE partition_id = ? "
                    "AND kind = 'doc' AND name = ? AND path IN (?, ?)",
                    (store._partition_id, doc.doc_id, str(path), str(Path(path).resolve())),
                ).fetchall():
                    store.purge_entity(int(old_id))
                vec_failed = getattr(store, "vector_delete_failures", 0) - vec_failed0
                if vec_failed:
                    # purge_entity prints and counts a failed Lance delete on the store; the
                    # ingest result names it too (r1 #5).
                    raise RuntimeError(f"{vec_failed} vector delete(s) failed")
            except Exception as exc:
                # Counted and printed, never verbose-only (memory-path rule).
                stats.doc_drop_failed.append((path, repr(exc)))
                print(f"  warn: doc->memory cleanup failed for "
                      f"{doc.doc_id}: {exc!r}")
            try:
                raw_text = path.read_text(encoding="utf-8")
                fm_lines = raw_text.splitlines()
                fm_data, body_start = _parse_frontmatter(fm_lines)
            except Exception:
                fm_data, body_start, raw_text = {}, 0, ""
                fm_lines = []
            body = "\n".join(fm_lines[body_start:]).lstrip("\n") if raw_text else ""
            # _parse_frontmatter doesn't unwrap nested `metadata:` blocks.
            # Pull `metadata.type` directly off the raw frontmatter slice.
            mtype = memory_mtype_default
            raw_meta: dict[str, str] = {}
            in_meta_block = False
            for line in fm_lines[: body_start - 1] if body_start else []:
                if line.strip() == "metadata:":
                    in_meta_block = True
                    continue
                if in_meta_block:
                    if line.startswith("  ") and ":" in line:
                        k, _, v = line.strip().partition(":")
                        raw_meta[k.strip()] = v.strip().strip("\"'")
                    elif line.strip() and not line.startswith("  "):
                        in_meta_block = False
            if raw_meta.get("type"):
                mtype = raw_meta["type"]
            mem_metadata = {
                "source": "ingest_gmd_as_memory",
                # In an organised dir the RESOLVED path is stored, since the
                # path-aware gate compares it literally (task 26.2 AC-1/AC-2).
                "source_path": resolved_path if path_aware else str(path),
                "gmd_version": doc.gmd_version,
                "title": doc.title,
            }
            for k, v in raw_meta.items():
                if k not in mem_metadata:
                    mem_metadata[k] = v
            _mem_content = body or raw_text
            legacy_eids = [eid for eid, _n in (gate.legacy if gate else [])]
            # The id row and the legacy rows on its old path are ONE store
            # write (AC-1b, r6-lite n1): an id row is never refreshed without
            # them. Both writers use `_maybe_commit` inside the transaction.
            with store.transaction():
                doc_eid = store.add_memory(
                    name=doc.doc_id,
                    content=_mem_content,
                    mtype=mtype,
                    tags=list(doc.tags) if doc.tags else None,
                    metadata=mem_metadata,
                )
                if legacy_eids:
                    store.refresh_memory_source_path(legacy_eids, resolved_path)
            if legacy_eids and gate is not None and gate.old_resolved:
                path_index.moved(legacy_eids, gate.old_resolved, resolved_path)
            if _coref_on():
                # Resolutions are stored against EXACTLY the string that
                # became memory_content.content -- the embedder re-applies
                # them to that same string, so offsets never drift.
                from refmatrix import coref as _coref
                from refmatrix.ingest import \
                    _bulk_add_concepts as _coref_add_concepts
                _res = _coref.resolve_text(_mem_content, min_confidence=0.25)
                store.save_coref(doc_eid, _res)
                if _res:
                    _ensure_linkage(store, "coref", stats)
                    _c_specs = [(t, f"coref antecedent '{t}'")
                                for t in _coref.antecedent_counts(_res)]
                    _c_ids = _coref_add_concepts(store, _c_specs)
                    store.bulk_link(
                        [("coref", _c_ids[t], doc_eid, float(n))
                         for t, n in _coref.antecedent_counts(_res).items()],
                        update_weight=True)
        else:
            doc_eid = store.upsert_entity(
                kind="doc", name=doc.doc_id, path=str(path),
                tldr=doc.title,
                meta={"gmd_version": doc.gmd_version, "tags": doc.tags},
            )
        eid_by_name[doc.doc_id] = doc_eid
        doc_level_eid[doc.doc_id] = doc_eid
        # ADR same_as bridge: link the GMD-id form (adr-0078-foo-bar) to the
        # non-GMD ADR ingester's slash-form (adr/0078) so wikilinks against
        # either form resolve to a unified concept. The slash form is a
        # `concept` entity created by ingest._ingest_adr; here we use
        # upsert_entity to ensure it exists, then add a same_as edge.
        slash = _adr_slash_alias(doc.doc_id)
        if slash is not None:
            slash_eid = store.upsert_entity(
                kind="concept", name=slash,
                meta={"description": f"ADR slug alias of '{doc.doc_id}'"},
            )
            _ensure_linkage(store, "same_as", stats)
            store.link("same_as", doc_eid, slash_eid)
            eid_by_name[slash] = slash_eid

        # node entities (one per {#id})
        # Registered as kind='concept' so they're queryable via the standard
        # `rmx neighbors / context / scan-prompt` paths (which resolve refs
        # to concepts first). The doc-level file remains kind='doc'.
        for node in doc.nodes:
            name = _entity_name(doc.doc_id, node.id)
            # The synthetic `__root__` node maps to the bare doc-id, which is
            # ALREADY materialized as the doc-level entity above (a `memory`
            # under as_memory, else a `doc`). Minting a parallel `kind=concept`
            # here created a duplicate node per subject and split this subject's
            # inbound rel: edges across the two (cross-doc targets resolved to
            # the concept via _resolve_target_eid, while pass-2 mentions landed
            # on the memory). Skip it: the doc-level entity IS the root node.
            # eid_by_name[doc_id] already points at doc_eid (set above), so
            # pass-2 title/body/rel edges land on it.
            if name == doc.doc_id:
                eid_by_name.setdefault(name, doc_eid)
                continue
            tldr = (
                f"{node.title}\n\n"
                + "\n".join(node.body_lines[:8]).strip()
            )[:500]
            meta = {
                "doc": doc.doc_id, "anchor": node.id,
                "level": node.level, "line": node.line,
                "gmd_node": True,
                **({"aliases": node.aliases} if node.aliases else {}),
                **node.attrs,
            }
            eid = store.upsert_entity(
                kind="concept", name=name,
                # the moved file's anchors follow it (task 26.2 AC-1)
                path=resolved_path if path_aware else str(path),
                tldr=tldr, meta=meta,
            )
            eid_by_name.setdefault(name, eid)
            stats.nodes += 1
            _node_tick()

        pass1_processed += 1
        if progress_cb is not None:
            progress_cb("pass1", pass1_processed, len(paths), path)
        if yield_lock and pass1_processed % yield_every == 0:
            # Lock-yield window: daemon releases + reacquires _store_lock so
            # CLI ops queued behind us get a turn. See module docstring.
            yield_lock()

    stats.marker_errors.extend(organised.errors)

    # ---- pass 2: hierarchy + rel: + mentions ----------------------------
    _ensure_linkage(store, "part-of", stats)
    _ensure_linkage(store, "mentions", stats)
    # Title/alias structure as its OWN linkage rather than as a magic weight.
    # See `_split_title_links`.
    _split_titles = _split_title_links()
    _tphrases = _title_phrases_on()
    _lead_on = _lead_terms_on()
    _body_on = _body_terms_on()
    if _split_titles:
        _ensure_linkage(store, "titles", stats)
        _ensure_linkage(store, "aliases", stats)
    if _lead_on:
        _ensure_linkage(store, "lead", stats)
    _ensure_linkage(store, "imports", stats)
    # Bulk concept creation (mirrors add_concept, batched). Lazy import to
    # avoid a circular import with refmatrix.ingest (which calls this module).
    from refmatrix.ingest import _bulk_add_concepts

    pass2_processed = 0
    for doc in docs:
        doc_eid = eid_by_name[doc.doc_id]
        # Resume skip: pass1 found a matching gmd_content_hash. The
        # file's rels were persisted in the prior ingest's pass2 (hash
        # is only set after pass2 completes). Skip the whole rel loop.
        if doc.doc_id in skip_docs:
            pass2_processed += 1
            if progress_cb is not None:
                progress_cb(
                    "pass2-skip", pass2_processed, len(docs), doc.path,
                )
            if yield_lock and pass2_processed % yield_every == 0:
                yield_lock()
            continue

        # Pre-collect this doc's UNCONDITIONAL concepts (tags + per-node title
        # tokens / aliases / body terms) in add_concept order, then bulk-create
        # them so the link pass below is a map lookup, not ~1 upsert per term
        # (the dominant cost in the GMD ingest profile). First-description-wins
        # is preserved by collection order. Conditional wikilink-anchor
        # concepts stay inline -- they depend on link resolution.
        concept_specs: list[tuple[str, str]] = []
        for tag in doc.tags:
            concept_specs.append((tag, f"tag '{tag}'"))
        for node in doc.nodes:
            _seen_tok: set[str] = set()
            for tok in _title_concept_tokens(node.title):
                if tok in _seen_tok:
                    continue
                _seen_tok.add(tok)
                concept_specs.append((tok, f"title token '{tok}'"))
            for alias in node.aliases:
                concept_specs.append((alias, f"alias '{alias}'"))
            if _tphrases:
                for ph in _title_phrase_keys(node.title):
                    concept_specs.append((
                        f"phrase/{ph}",
                        f"title phrase '{ph.replace(chr(95), chr(32))}'"))
            if _body_on:
                for term in _body_term_frequencies(node.body_lines):
                    concept_specs.append((term, f"body term '{term}'"))
            if _phrases_on:
                for ph in _body_phrases(node.body_lines):
                    concept_specs.append((
                        f"phrase/{ph}",
                        f"phrase '{ph.replace(chr(95), chr(32))}'"))
        cids = _bulk_add_concepts(store, concept_specs)

        # Unconditional links are batched and written with ONE weight-aware
        # bulk_link per doc. They used to go per-row because bulk_link was
        # first-wins (DO NOTHING), which corrupts a `mentions` weight whenever
        # one concept reaches the same node twice -- as a title token (2.0)
        # and again as a body term (tf). `update_weight=True` gives bulk_link
        # link()'s own last-non-null-wins conflict rule, so append order here
        # carries exactly the semantics the sequential calls had.
        #
        # This is the dominant cost of the pass: the body term-frequency sweep
        # emits one link per unique term per node, which on prose-sized
        # documents is thousands per file (measured: ~2.3 s/doc, 20 min for a
        # 1307-document corpus).
        #
        # rel: edges stay per-row below -- they are few, and each needs
        # _ensure_linkage plus target resolution before its weight is known.
        link_batch: list[tuple[str, int, int, float | None]] = []

        # frontmatter imports
        for imp in doc.imports:
            target = eid_by_name.get(imp)
            if target is None:
                # cross-batch reference may not be in this ingest; skip silently
                continue
            link_batch.append(("imports", doc_eid, target, None))

        # tags as mentions
        for tag in doc.tags:
            # tf=1.0, not NULL. A tag OCCURS -- once, as a tag -- and NULL was
            # read by `content_rank` as `float(w or 0.0)` = 0.0, so a
            # frontmatter tag scored NOTHING in BM25 while still counting in
            # `concept_df` and depressing its own concept's idf. A pure penalty
            # for existing, on the highest-precision term signal a document has
            # (a human wrote it to say what the doc is about). Tags are only
            # 0.7-1.9% of edges, so this will not move an aggregate metric --
            # it makes the few that exist capable of mattering at all.
            link_batch.append(("mentions", cids[tag], doc_eid, 1.0))
            stats.mentions += 1

        # Source authority for this doc's typed rel: edges (ADR 3x,
        # design 1.5x, else 1x). Computed once per doc.
        _authority = _doc_authority(doc)

        # per-node processing
        for node in doc.nodes:
            src_name = _entity_name(doc.doc_id, node.id)
            src_eid = eid_by_name[src_name]

            # part-of: heading hierarchy
            if node.parent:
                parent_name = _entity_name(doc.doc_id, node.parent)
                parent_eid = eid_by_name.get(parent_name)
                if parent_eid is not None and parent_eid != src_eid:
                    link_batch.append(("part-of", src_eid, parent_eid, None))

            # title tokens → mentions (lets prose queries find this node)
            title_concepts: set[str] = set()
            for tok in _title_concept_tokens(node.title):
                if tok in title_concepts:
                    continue
                title_concepts.add(tok)
                if _split_titles:
                    # An honest tf: the token occurred ONCE, in the heading.
                    # The fact that it was a TITLE is structure, and structure
                    # belongs in a linkage, not in a fabricated frequency.
                    link_batch.append(("mentions", cids[tok], src_eid, 1.0))
                    link_batch.append(("titles", cids[tok], src_eid, 1.0))
                else:
                    link_batch.append(("mentions", cids[tok], src_eid, 2.0))
                stats.mentions += 1

            # aliases → mentions with high weight
            for alias in node.aliases:
                if _split_titles:
                    link_batch.append(("mentions", cids[alias], src_eid, 1.0))
                    link_batch.append(("aliases", cids[alias], src_eid, 1.0))
                else:
                    link_batch.append(("mentions", cids[alias], src_eid, 3.0))
                stats.mentions += 1

            # body terms → mentions with weight = tf (BM25 will normalize)
            # Appended AFTER the title/alias passes: on a collision the tf wins,
            # which is what the sequential link() calls did.
            if _body_on:
                for term, tf in _body_term_frequencies(node.body_lines).items():
                    link_batch.append(("mentions", cids[term], src_eid, float(tf)))
                    stats.mentions += 1

            # phrase pairs → mentions, same tf weighting as unigrams. Namespaced
            # so `--no-phrases` recall and the noise pruner can tell the two
            # apart, and so a pair key can never collide with a real symbol.
            if _phrases_on:
                for ph, tf in _body_phrases(node.body_lines).items():
                    link_batch.append(
                        ("mentions", cids[f"phrase/{ph}"], src_eid, float(tf)))
                    stats.mentions += 1

            if _tphrases:
                for ph in _title_phrase_keys(node.title):
                    link_batch.append(
                        ("mentions", cids[f"phrase/{ph}"], src_eid, 1.0))
                    stats.mentions += 1

            if _lead_on:
                # Structure only — the term already carries its tf on the
                # `mentions` edge; this records WHERE it first appeared.
                for term in _lead_term_keys(node.body_lines):
                    cid = cids.get(term)
                    if cid is not None:
                        link_batch.append(("lead", cid, src_eid, 1.0))

            # rel: edges
            for line_no, verb, target in node.rels:
                _ensure_linkage(store, verb, stats)
                resolved = False
                for wm in _WIKILINK_RE.finditer(target):
                    ref = wm.group(1).strip()
                    target_doc, anchor = _split_ref(ref)
                    if target_doc is None:
                        # local ref; resolves within same doc
                        target_name = _entity_name(doc.doc_id, anchor)
                    else:
                        target_name = (
                            _entity_name(target_doc, anchor) if anchor
                            else target_doc
                        )
                    target_eid = _resolve_target_eid(store, eid_by_name, target_name)
                    if target_eid is None and target_doc:
                        # ADR slug/slash bridge: a wikilink like
                        # [[adr-0078-json-schema-as-type-authority]] also
                        # resolves against the non-GMD ADR ingester's
                        # `adr/0078` entity.
                        slash = _adr_slash_alias(target_doc)
                        if slash:
                            target_eid = _resolve_target_eid(
                                store, eid_by_name, slash
                            )
                    if target_eid is None:
                        stats.unresolved.append((doc.path, line_no, ref))
                        continue
                    store.link(verb, src_eid, target_eid,
                               weight=(_authority if _authority != 1.0
                                       else None))
                    store.add_evidence(
                        verb, src_eid, target_eid,
                        file=str(doc.path), line=line_no,
                        detail=f"rel: {verb} -> {ref}",
                    )
                    stats.rels += 1
                    resolved = True
                    # Mirror root-level rels onto the doc-level entity.
                    # The GMD primer puts most cross-doc edges on the H1
                    # `{#root}` node, which lands the linkage on the
                    # `<doc>#root` concept entity — invisible to
                    # `rmx neighbors <doc>` and to the degree-walk that
                    # starts from the doc-level memory. Mirror the edge
                    # to the doc-level entity so memory→memory rel:
                    # chains traverse naturally in build_context.
                    if (
                        node.id == "root"
                        and doc_eid != src_eid
                        and doc_eid != target_eid
                    ):
                        store.link(verb, doc_eid, target_eid,
                                   weight=(_authority if _authority != 1.0
                                           else None))
                        store.add_evidence(
                            verb, doc_eid, target_eid,
                            file=str(doc.path), line=line_no,
                            detail=f"rel: {verb} -> {ref} (root-mirror)",
                        )
                if not resolved and not target.startswith(("http://", "https://")):
                    stats.unresolved.append((doc.path, line_no, target))

            # plain wikilinks → mentions linkage on resolved targets
            for line_no, ref in node.refs:
                target_doc, anchor = _split_ref(ref)
                if target_doc is None:
                    target_name = _entity_name(doc.doc_id, anchor)
                else:
                    target_name = (
                        _entity_name(target_doc, anchor) if anchor
                        else target_doc
                    )
                target_eid = _resolve_target_eid(store, eid_by_name, target_name)
                if target_eid is None and target_doc:
                    slash = _adr_slash_alias(target_doc)
                    if slash:
                        target_eid = _resolve_target_eid(
                            store, eid_by_name, slash
                        )
                if target_eid is None:
                    stats.unresolved.append((doc.path, line_no, ref))
                    continue
                # represent "node X mentions node Y" by indexing the target's
                # anchor-id as a concept and linking to source
                concept_name = anchor or target_doc or ""
                if concept_name:
                    cid = store.add_concept(
                        concept_name,
                        description=f"GMD anchor '{concept_name}'",
                    )
                    store.link("mentions", cid, src_eid)
                    stats.mentions += 1

            _node_tick()

        # One weight-aware write for every unconditional link in this doc.
        # Ordering against the per-row wikilink `mentions` above does not
        # matter: those pass weight=None, and both conflict rules leave a
        # stored weight untouched when the incoming one is NULL.
        if link_batch:
            store.bulk_link(link_batch, update_weight=True)

        # Mark file fully ingested for resume. The hash was captured at
        # pass1 entry (before any writes), so this writes the snapshot
        # of the source-of-truth at the time work began. Files modified
        # mid-ingest will still match on the next run only if their
        # mid-ingest hash equals the post-ingest hash — a rare benign
        # case.
        # Use `doc_level_eid` (NOT `doc_eid` / `eid_by_name`): the
        # `__root__` concept node shares the bare doc_id name and
        # overwrites `eid_by_name[doc.doc_id]` during pass1's node loop.
        captured = file_hashes.get(doc.doc_id)
        write_eid = doc_level_eid.get(doc.doc_id)
        if captured and write_eid is not None:
            try:
                _write_content_hash(store, write_eid, captured)
            except Exception as exc:
                if verbose:
                    print(
                        f"  warn: hash write failed for {doc.doc_id}: "
                        f"{exc!r}"
                    )

        pass2_processed += 1
        if progress_cb is not None:
            progress_cb("pass2", pass2_processed, len(docs), doc.path)
        if yield_lock and pass2_processed % yield_every == 0:
            yield_lock()

    # Which code derived this partition's GMD graph (bug-039). The GMD passes
    # changed under a store that kept reading green — the body-anchor fix
    # (bug-036) alone re-shaped what a `{#anchor}` becomes — so the deriving
    # version has to be on the record. Failure is said, never swallowed.
    try:
        store.stamp_derive("gmd")
    except Exception as exc:          # noqa: BLE001 — said, never mute
        import sys as _sys
        print(f"warning: derive stamp `gmd` failed: "
              f"{type(exc).__name__}: {exc}", file=_sys.stderr)

    return stats


# Files a memory dir carries that are indexes over memories, not memories.
MEMORY_INDEX_FILES = frozenset({"MEMORY.md"})


# How many skipped names one skip line spells out; the rest are counted.
MEMORY_SKIP_NAMES_SHOWN = 20


def render_memory_skip_line(skipped) -> str:
    """THE line that says what the memory walk did not take: the count of every
    skip and the names (ch-bsd 26.1 #s-3, 2026-11-09). One renderer for the
    in-process bridge, the daemon-backed CLI and the detached-start report, so
    the three cannot drift. Empty when nothing was skipped."""
    names = [str(p) for p in skipped]
    if not names:
        return ""
    shown = names[:MEMORY_SKIP_NAMES_SHOWN]
    more = len(names) - len(shown)
    return (f"ingest-gmd --as-memory: skipped {len(names)} non-memory path(s) "
            f"(dot-path, README.md, nested MEMORY.md, symlinked folder, dangling "
            f"link or .gmd; ADR-0005 #one-walk): {', '.join(shown)}"
            f"{f' … and {more} more' if more else ''}")


def collect_gmd_files(targets: list[Path], *, as_memory: bool = False,
                      skipped: "list | None" = None) -> list[Path]:
    """Expand a list of files or directories to candidate GMD paths.

    `as_memory=True` (task 26.1 AC-2, ADR-0005 #one-walk, 2026-11-09): a
    directory target is a MEMORY DIR and is expanded with
    `memory_layout.iter_memory_files` -- the one walk of a memdir. The doc walk
    below (`rglob`) took dot-dirs, so a `.organise-rollback-1/x.md` aside was
    ingested as a memory (ch-bsd plan-26 r1 #s3). Every memory call site passes
    the flag -- the daemon sync and detached ops, both prestage twins, the
    in-process bridge -- so prestage stamps hashes on exactly the set the bridge
    ingests (r2 m1, r3 m7). Doc ingest keeps its own walk.

    Two details on the memory path, both so nothing is skipped silently:
    - the memdir's own top-level `MEMORY.md` is still passed through, so
      `ingest_gmd_paths` keeps COUNTING and naming it as `skipped_index`
      (ch-bsd plan-5 #b-2's report contract);
    - every other path the walk excluded (dot-paths, `README.md`, a nested
      `MEMORY.md`, a symlinked folder, a dangling `.md` link, a `.gmd`) is
      counted and named. With `skipped=` the caller takes the list and reports
      it to ITS caller (the daemon ops return it in their result, the CLI
      prints it); without it, the line goes to stderr here. At HEAD the daemon
      ops printed it to the daemon's own stderr log, which no caller reads
      (ch-bsd 26.1 #s-3, 2026-11-09).
    """
    import sys as _sys
    out: list[Path] = []
    seen: set[Path] = set()
    for t in targets:
        if t.is_file():
            if t not in seen:
                out.append(t)
                seen.add(t)
        elif t.is_dir() and as_memory:
            from refmatrix.memory_layout import iter_memory_files
            excluded: list[Path] = []
            for p in iter_memory_files(t, skipped=excluded):
                if p not in seen:
                    out.append(p)
                    seen.add(p)
            index = [p for p in excluded
                     if p.parent == t and p.name in MEMORY_INDEX_FILES]
            for p in index:
                if p not in seen:
                    out.append(p)
                    seen.add(p)
            other = [p for p in excluded if p not in index]
            if skipped is not None:
                skipped.extend(other)
            elif other:
                print(render_memory_skip_line(other), file=_sys.stderr)
        elif t.is_dir():
            for ext in ("*.gmd", "*.md"):
                for p in sorted(t.rglob(ext)):
                    if p not in seen:
                        out.append(p)
                        seen.add(p)
    return out


# ---- memory rows need VECTORS, or recall cannot see them (bug-065) --------

# How many embed batches ONE as-memory ingest will pay for. The bridge writes
# a handoff plus whatever memory files a session produced — single digits in
# normal use — so 8 x 256 is ~2000 rows, far past any real session. A store
# that is thousands of vectors behind (a first run, a model switch) is NOT
# silently re-embedded inside a bridge call: the cap is hit, the remainder is
# COUNTED, and `rmx embed --kinds memory` is named.
MEMORY_EMBED_DRAIN_BATCHES = 8
MEMORY_EMBED_BATCH = 256


def drain_memory_vectors(embed_batch, *, partition: str,
                         batches: int = MEMORY_EMBED_DRAIN_BATCHES,
                         limit: int = MEMORY_EMBED_BATCH) -> dict:
    """Embed the `kind=memory` rows an as-memory ingest just wrote.

    WHY THIS LIVES HERE (bug-065, 2026-10-01): this module inserts memory rows
    with no vectors, and nothing drained them. `finalize_save_state` had zero
    occurrences of `embed`, so every save-state produced durable, UNREACHABLE
    memories — hit twice in one day, by me (four new memories; `rmx memory
    search "verify fix reachable from master"` returned NO matches while
    `memory get` found every row) and independently by a ch-bsd run whose
    distinctive phrase returned five OTHER documents. recall is the only way
    the next session reaches a memory, so a row without a vector is half
    saved.

    The first fix put the drain in `finalize_save_state`, which made `rmx
    save-state` correct and left `rmx ingest-gmd --as-memory` — the SessionStart
    catch-up hook, `rmx memory sync-disk`, and any by-hand run — still writing
    vectorless rows. The rule belongs to the WRITE, not to one of its callers:
    an as-memory ingest implies memory vectors
    (`feedback_main_path_must_exercise_core_mechanisms`).

    `embed_batch(args) -> dict` is injected so this module never imports the
    daemon: the daemon op passes `_op_embed`, and the CLI's in-process branch
    passes the same function over its own store. One implementation, two
    injection points, no import cycle.

    Bounded, counted, and SAID — never raises, and never returns silence.
    Returns {"partition", "embedded", "remaining", "batches", "capped",
    "error"}.
    """
    out: dict = {"partition": partition, "embedded": 0, "remaining": None,
                 "batches": 0, "capped": False, "error": None}
    try:
        for i in range(int(batches)):
            res = embed_batch({"kinds": ["memory"], "limit": int(limit),
                               "rebuild": False, "partition": partition})
            if not isinstance(res, dict):
                out["error"] = f"embed returned {type(res).__name__}, not a dict"
                return out
            if res.get("ok") is False:
                out["error"] = res.get("error", "embed failed")
                return out
            out["batches"] = i + 1
            embedded = int(res.get("embedded", 0))
            out["embedded"] += embedded
            out["remaining"] = int(res.get("remaining", 0))
            if not out["remaining"]:
                return out
            # `embedded == 0` ends it too: a pass that can make no progress
            # would otherwise spin the full budget for nothing. EXCEPT a batch
            # whose rows all changed while the model ran (ch-bsd r10 #m-1):
            # they are still pending and the next batch embeds their new text.
            # The batch budget still bounds a row rewritten on every pass.
            if not embedded and not res.get("changed_while_encoding"):
                return out
        out["capped"] = True
    except Exception as e:      # noqa: BLE001 — reported, never hidden
        out["error"] = f"{type(e).__name__}: {e}"
    return out


def render_memory_embed_line(emb: "dict | None") -> str:
    """One line for the drain's outcome, or "" when there was nothing to do.

    Shared so the daemon's report and the CLI's in-process report say the same
    thing — and so a FAILED drain is impossible to render as success. A memory
    that is saved and unreachable names the command that finishes the job.
    """
    if not emb:
        return ""
    if emb.get("error"):
        return (f"memory embed FAILED: {emb['error']} — the memories are "
                f"SAVED but recall cannot see them; run "
                f"`rmx embed --kinds memory` by hand")
    if emb.get("capped"):
        return (f"memory embed capped after {emb.get('batches')} batches: "
                f"{emb.get('embedded')} embedded, {emb.get('remaining')} "
                f"still without vectors — finish with "
                f"`rmx embed --kinds memory`")
    if emb.get("embedded"):
        return (f"memory embed: {emb['embedded']} row(s) now reachable by "
                f"recall in {emb.get('partition')}")
    return ""


def regenerate_memory_index(store_root: Path, files: list, *,
                            memory_only: bool) -> dict:
    """Regenerate `MEMORY.md` after a bridge batch — plan-19's 19.4 R2, built by
    task 26.6 (plan-26), 2026-11-09.

    The index used to be written only by save-state, so a memory that reached
    the store any other way (the SessionStart `--detach` catch-up, a by-hand
    `ingest-gmd --as-memory`) was absent from the index until the next
    save-state. Rules:

    - The memdir is the STORE's memory root, `handoff.default_memory_dir(<the
      store's project root>)`, never the bridge's target: a target such as
      `impressions/` or one file resolves to the same root, and no index is
      ever written inside the target.
    - Only a batch that ingested at least one file under that root regenerates
      it (a sessions-card ingest does not).
    - MARKER-GATED (task-26.6 r2 s2): only a root that `memory_layout.
      is_organised` (the ONE marker reader) is rewritten. An un-organised dir
      keeps HEAD's behaviour — the bridge writes no index there.
    - The global store has no project memory root: skipped and SAID.

    Returns `{status, memdir?, lines?, report?, reason?}` with status one of
    `written`, `unorganised`, `skipped`. A marker that cannot be read RAISES
    (`memory_layout.MemoryLayoutError`) — the caller reports it; it is never
    read as "not organised"."""
    import io

    from refmatrix import handoff, memory_index, memory_layout

    if memory_only:
        return {"status": "skipped", "no_memory_root": True,
                "reason": "the global store has no project memory root"}
    memdir = handoff.default_memory_dir(Path(store_root).parent)
    mroot = memdir.resolve()
    inside = False
    for f in files:
        try:
            Path(f).resolve().relative_to(mroot)
        except ValueError:
            continue
        inside = True
        break
    if not inside:
        return {"status": "skipped", "memdir": str(memdir),
                "reason": "no ingested file under the store's memory root"}
    if not memory_layout.is_organised(memdir):
        return {"status": "unorganised", "memdir": str(memdir)}
    buf = io.StringIO()
    lines = memory_index.write(memdir, out=buf)
    return {"status": "written", "memdir": str(memdir), "lines": lines,
            "report": buf.getvalue().strip()}


def render_memory_index_line(idx: "dict | None") -> str:
    """One report line for `regenerate_memory_index`, or "" when there is
    nothing a reader needs (an un-organised dir, a non-memory batch). Shared by
    the daemon's report and the CLI's in-process report, like the embed line."""
    from refmatrix.memory_index import INDEX_NAME

    if not idx:
        return ""
    st = idx.get("status")
    if st == "error":
        return (f"{INDEX_NAME} NOT regenerated: {idx.get('error')} — "
                f"the memories are SAVED; fix the cause and run save-state")
    if st == "written":
        rep = idx.get("report") or ""
        return (f"{INDEX_NAME} regenerated in {idx.get('memdir')} "
                f"({idx.get('lines')} line(s))" + (f"\n{rep}" if rep else ""))
    if st == "skipped" and idx.get("no_memory_root"):
        return f"{INDEX_NAME} not regenerated: {idx.get('reason')}"
    return ""


def regenerate_memory_index_reported(store_root: Path, files: list, *,
                                     memory_only: bool) -> dict:
    """`regenerate_memory_index`, with a failure CAPTURED as `status: error`
    instead of raised: by the time the index is regenerated the batch's rows are
    committed, and failing the whole ingest would report saved memories as
    lost. The error is carried in the result and rendered into the report by
    `render_memory_index_line` (CLAUDE.md #no-silent-failures). Every exception
    type is captured, as `drain_memory_vectors` does: this runs after the
    daemon's ingest try-block, so an escaped error would leave the job reading
    `running` forever and every bridge waiting on it would time out."""
    try:
        return regenerate_memory_index(store_root, files, memory_only=memory_only)
    except Exception as exc:      # noqa: BLE001 — reported in the result, never hidden
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
