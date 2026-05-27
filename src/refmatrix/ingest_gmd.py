"""GMD (Graph Markdown) ingest for refmatrix.

Parses `.gmd` / `.md` files with `gmd:` frontmatter and registers them in the
store:
  - Each `{#id}` node → entity of kind 'doc', name=<doc-id>#<node-id>.
  - Each `rel: <verb> -> <target>` → linkage (auto-create type).
  - Heading hierarchy → implicit `part-of` linkage on direct parents.
  - Frontmatter `imports:` → `imports` linkage on doc-level entity.
  - Title tokens + `alias=[...]` attribute → mentions concepts for retrieval.
  - `[[ref]]` outside rel: lines → `mentions` linkage.

This is the minimum that makes `rmx context <doc-id>#<node-id>` return a
useful slice. Full BM25 over node body text is deferred to v1.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from refmatrix.store import Store

# ---- spec syntax patterns -------------------------------------------------

_ID_RE = re.compile(r"\{#([a-z0-9][a-z0-9._/-]*)([^}]*)\}")
_WIKILINK_RE = re.compile(r"\[\[([^\[\]]+)\]\]")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_REL_RE = re.compile(
    r"^rel:\s+([a-z][a-z0-9-]*)\s*->\s*(\S+(?:\s+\S+)*?)(?:\s*\{([^}]*)\})?\s*$"
)
_INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
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

def parse_gmd(path: Path) -> GmdDoc | None:
    """Parse a GMD doc. Returns None if file lacks `gmd:` frontmatter."""
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    fm, body_start = _parse_frontmatter(lines)
    if "gmd" not in fm:
        return None
    doc_id = fm.get("id") or path.stem
    title = fm.get("title") or doc_id
    tags = fm.get("tags") if isinstance(fm.get("tags"), list) else []
    imports = fm.get("imports") if isinstance(fm.get("imports"), list) else []

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
            idm = _ID_RE.search(rest)
            if idm:
                nid = idm.group(1)
                node_attrs, aliases = _parse_attrs(idm.group(2))
                heading_text = _ID_RE.sub("", rest).strip()
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
        for wm in _WIKILINK_RE.finditer(scan):
            current.refs.append((line_no, wm.group(1).strip()))

    return GmdDoc(
        path=path, doc_id=doc_id, title=title, gmd_version=str(fm["gmd"]),
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
    # Try concept (node anchors) then doc (file-level refs).
    for kind in ("concept", "doc"):
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

    def report(self) -> str:
        lines = [
            f"ingested {self.docs} doc(s), {self.nodes} node(s), "
            f"{self.rels} rel: edge(s), {self.mentions} mention(s)",
        ]
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
    """Identifier-shaped tokens from a heading title for retrieval surfaces."""
    return [t for t in _TITLE_TOKEN_RE.findall(title)]


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


def ingest_gmd_paths(
    store: Store, paths: list[Path], verbose: bool = False,
    yield_lock: Callable[[], None] | None = None,
    yield_every: int = 10,
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
    """
    stats = IngestStats()

    # ---- pass 1: parse + register entities -------------------------------
    docs: list[GmdDoc] = []
    eid_by_name: dict[str, int] = {}
    pass1_processed = 0

    for path in paths:
        try:
            doc = parse_gmd(path)
        except Exception as e:
            if verbose:
                print(f"  skip {path}: {type(e).__name__}: {e}")
            continue
        if doc is None:
            continue
        docs.append(doc)
        stats.docs += 1

        # doc-level entity (represents the whole file)
        doc_eid = store.upsert_entity(
            kind="doc", name=doc.doc_id, path=str(path),
            tldr=doc.title,
            meta={"gmd_version": doc.gmd_version, "tags": doc.tags},
        )
        eid_by_name[doc.doc_id] = doc_eid
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
                kind="concept", name=name, path=str(path),
                tldr=tldr, meta=meta,
            )
            eid_by_name[name] = eid
            stats.nodes += 1

        pass1_processed += 1
        if yield_lock and pass1_processed % yield_every == 0:
            # Lock-yield window: daemon releases + reacquires _store_lock so
            # CLI ops queued behind us get a turn. See module docstring.
            yield_lock()

    # ---- pass 2: hierarchy + rel: + mentions ----------------------------
    _ensure_linkage(store, "part-of", stats)
    _ensure_linkage(store, "mentions", stats)
    _ensure_linkage(store, "imports", stats)

    pass2_processed = 0
    for doc in docs:
        doc_eid = eid_by_name[doc.doc_id]

        # frontmatter imports
        for imp in doc.imports:
            target = eid_by_name.get(imp)
            if target is None:
                # cross-batch reference may not be in this ingest; skip silently
                continue
            store.link("imports", doc_eid, target)

        # tags as mentions
        for tag in doc.tags:
            cid = store.add_concept(tag, description=f"tag '{tag}'")
            store.link("mentions", cid, doc_eid)
            stats.mentions += 1

        # per-node processing
        for node in doc.nodes:
            src_name = _entity_name(doc.doc_id, node.id)
            src_eid = eid_by_name[src_name]

            # part-of: heading hierarchy
            if node.parent:
                parent_name = _entity_name(doc.doc_id, node.parent)
                parent_eid = eid_by_name.get(parent_name)
                if parent_eid is not None and parent_eid != src_eid:
                    store.link("part-of", src_eid, parent_eid)

            # title tokens → mentions (lets prose queries find this node)
            title_concepts: set[str] = set()
            for tok in _title_concept_tokens(node.title):
                if tok in title_concepts:
                    continue
                title_concepts.add(tok)
                cid = store.add_concept(tok, description=f"title token '{tok}'")
                store.link("mentions", cid, src_eid, weight=2.0)
                stats.mentions += 1

            # aliases → mentions with high weight
            for alias in node.aliases:
                cid = store.add_concept(alias, description=f"alias '{alias}'")
                store.link("mentions", cid, src_eid, weight=3.0)
                stats.mentions += 1

            # body terms → mentions with weight = tf (BM25 will normalize)
            for term, tf in _body_term_frequencies(node.body_lines).items():
                cid = store.add_concept(term, description=f"body term '{term}'")
                store.link("mentions", cid, src_eid, weight=float(tf))
                stats.mentions += 1

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
                    store.link(verb, src_eid, target_eid)
                    store.add_evidence(
                        verb, src_eid, target_eid,
                        file=str(doc.path), line=line_no,
                        detail=f"rel: {verb} -> {ref}",
                    )
                    stats.rels += 1
                    resolved = True
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

        pass2_processed += 1
        if yield_lock and pass2_processed % yield_every == 0:
            yield_lock()

    return stats


def collect_gmd_files(targets: list[Path]) -> list[Path]:
    """Expand a list of files or directories to candidate GMD paths."""
    out: list[Path] = []
    seen: set[Path] = set()
    for t in targets:
        if t.is_file():
            if t not in seen:
                out.append(t)
                seen.add(t)
        elif t.is_dir():
            for ext in ("*.gmd", "*.md"):
                for p in sorted(t.rglob(ext)):
                    if p not in seen:
                        out.append(p)
                        seen.add(p)
    return out
