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

    def as_dict(self) -> dict:
        """The counters, structurally — for the daemon result and the
        bridge's callers (ch-bsd plan-5 #m-7: no report scraping)."""
        return {"docs": self.docs, "nodes": self.nodes, "rels": self.rels,
                "mentions": self.mentions, "unresolved": len(self.unresolved),
                "skipped_non_gmd": self.skipped_non_gmd,
                "skipped_unparseable": [[str(p), e] for p, e in self.skipped_unparseable],
                "skipped_index": list(self.skipped_index)}

    def report(self) -> str:
        lines = [
            f"ingested {self.docs} doc(s), {self.nodes} node(s), "
            f"{self.rels} rel: edge(s), {self.mentions} mention(s)",
            f"skipped_non_gmd: {self.skipped_non_gmd}",
            f"skipped_unparseable: {len(self.skipped_unparseable)}",
        ]
        if self.skipped_index:
            lines.append(f"skipped_index: {len(self.skipped_index)} "
                         f"({', '.join(self.skipped_index)})")
        for p, err in self.skipped_unparseable[:20]:
            lines.append(f"  {p}: {err}")
        if len(self.skipped_unparseable) > 20:
            lines.append(f"  ... and {len(self.skipped_unparseable) - 20} more")
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

    for path in paths:
        # Resume fast path: if an entity for this doc already exists
        # with a matching gmd_content_hash, skip both passes. The hash
        # is only set at the END of pass2, so a partial prior ingest
        # leaves the hash unset and we re-process.
        try:
            current_hash = _doc_content_hash(path)
        except Exception:
            current_hash = ""
        if as_memory and path.name in MEMORY_INDEX_FILES:
            # The flat index is not a memory (ch-bsd plan-5 #b-2: the deleted
            # walker excluded it; the rewrite ingested `MEMORY` as curated).
            stats.skipped_index.append(path.name)
            continue
        try:
            doc = parse_gmd(path, lenient=lenient or as_memory,
                            project_root=project_root, memory_ids=as_memory)
        except Exception as e:
            # Counted AND named in the report — a skipped memory file is a
            # memory that never reaches recall (plan-5 task 5.1).
            stats.skipped_unparseable.append((path, f"{type(e).__name__}: {e}"))
            if verbose:
                print(f"  skip {path}: {type(e).__name__}: {e}")
            continue
        if doc is None:
            stats.skipped_non_gmd += 1
            continue
        if current_hash:
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
            try:
                store._connect().execute(
                    "DELETE FROM entities WHERE partition_id = ? "
                    "AND kind = 'doc' AND name = ?",
                    (store._partition_id, doc.doc_id),
                )
                store._connect().commit()
            except Exception as exc:
                if verbose:
                    print(
                        f"  warn: doc->memory cleanup failed for "
                        f"{doc.doc_id}: {exc!r}"
                    )
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
                "source_path": str(path),
                "gmd_version": doc.gmd_version,
                "title": doc.title,
            }
            for k, v in raw_meta.items():
                if k not in mem_metadata:
                    mem_metadata[k] = v
            _mem_content = body or raw_text
            doc_eid = store.add_memory(
                name=doc.doc_id,
                content=_mem_content,
                mtype=mtype,
                tags=list(doc.tags) if doc.tags else None,
                metadata=mem_metadata,
            )
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
                kind="concept", name=name, path=str(path),
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

    return stats


# Files a memory dir carries that are indexes over memories, not memories.
MEMORY_INDEX_FILES = frozenset({"MEMORY.md"})


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
