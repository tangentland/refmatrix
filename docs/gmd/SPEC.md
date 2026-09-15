---
gmd: "0.1"
id: gmd-spec
title: "GMD v0.1 — Graph Markdown Conformance Spec"
tags: [gmd, spec, reference]
metadata:
  node_type: spec
---

# GMD v0.1 — Graph Markdown Conformance Spec {#root}

**Graph Markdown.** A markdown-compatible convention for documents that carry typed relations and stable addressability. Designed to replace plain Markdown in Claude projects (CLAUDE.md, SKILL.md, memory files, notes) while remaining readable in any Markdown viewer.

Status: draft v0.1
Date: 2026-05-16

## 1. File {#file}

- Extension: `.gmd` (preferred) or `.md` when filename is hardcoded by tooling (e.g. `CLAUDE.md`, `SKILL.md`, `MEMORY.md`).
- Encoding: UTF-8, LF line endings.
- MIME type (proposed): `text/markdown+graph`.
- A conforming document is valid CommonMark with the optional extensions defined below.
- Any non-GMD-aware reader MUST be able to render the file as Markdown without error.
- A document is recognized as GMD by the presence of `gmd:` in its frontmatter, regardless of file extension.

## 2. Frontmatter {#frontmatter}

YAML frontmatter is optional. When present, it occupies the first block of the file, delimited by `---` lines.

Reserved keys:

| Key | Type | Meaning |
|-----|------|---------|
| `gmd` | string | Schema version, e.g. `"0.1"`. Presence signals GMD-awareness. |
| `id` | string | Document-level stable ID. Globally unique within a project. May contain `/` to express namespace hierarchy. |
| `title` | string | Human title. Falls back to first H1. |
| `tags` | list | Free-form labels. |
| `imports` | list | Other GMD docs whose IDs may be referenced unprefixed. |

All other keys are user-defined and preserved verbatim.

## 3. Block IDs {#block-ids}

Any block-level element MAY carry a stable ID using the CommonMark attribute-list syntax:

```
## Section title {#section-id}

A paragraph with an ID. {#para-1}

- list item with id {#item-a}
```

Rules:

- ID syntax: `{#` followed by `[a-z0-9][a-z0-9._/-]*` followed by `}`.
- IDs MAY contain `/` to express hierarchy (e.g. `project/foo`,
  `reference/bar`). Convention: slash mirrors filesystem subdirectory layout
  or namespace grouping. IDs MUST NOT start or end with `/`, and MUST NOT
  contain consecutive `//`.
- IDs MUST be unique within the document.
- IDs MUST be stable across edits to surrounding content. Renames are breaking changes.
- IDs MAY appear at end of heading, paragraph, list item, blockquote, code fence info string, or table row.
- Attribute lists MAY carry additional key/value pairs: `{#s1 kind=store status=draft}`.
- Attribute values containing whitespace MUST be quoted: `{#s1 title="my store"}`.

A reader that does not understand `{#id}` MUST render the attribute list as plain text or hide it; either is conforming.

## 4. References {#references}

Three reference forms, in order of preference:

1. **Local**: `[[#section-id]]` — same document.
2. **Cross-document**: `[[doc-id#section-id]]` — `doc-id` matches another doc's frontmatter `id` or filename stem.
3. **External**: standard Markdown link `[text](url)` for non-GMD targets.

`[[...]]` syntax is permitted at any inline position. Renderers without wikilink support render it as literal text; this is conforming.

## 5. Typed edges {#typed-edges}

Typed relations are declared with `rel:` lines. A `rel:` line is a single line at any block position that matches:

```
rel: <verb> -> <target> [{attrs}]
```

- `<verb>` is a kebab-case identifier. Recommended vocabulary in §8.
- `<target>` is a reference (`[[#id]]`, `[[doc#id]]`, or URL).
- `{attrs}` is an optional attribute list (`{weight=0.8 confidence=high}`).
- A `rel:` line attaches the edge to its nearest enclosing block with an ID. If no enclosing block has an ID, the edge attaches to the document root.
- Multiple `rel:` lines MAY appear consecutively. Order is not significant.
- A `rel:` line MUST start at column 0 and occupy the entire line.

Conforming Markdown renderers display `rel:` lines as plain text. GMD-aware tools extract them into the graph index.

Example:

```
## Persistent memory layer {#s1}

Append-only log of facts referenced by ID.

rel: solves -> [[#p1]]
rel: depends-on -> [[#s1.1]]
rel: supersedes -> [[old-design#stateless]] {confidence=high}
```

## 6. Hierarchy {#hierarchy}

The document tree is defined by CommonMark heading nesting. Non-heading blocks belong to the nearest preceding heading.

A node's address is the chain of IDs from document root, joined by `/`:

```
project-alpha/p1/p1.1
```

This is derived, not authored. Authors reference by leaf ID only.

## 7. Graph {#graph}

The graph layer is the union of:

- Implicit parent/child edges from heading hierarchy (verb: `parent`).
- Explicit `rel:` edges.
- Implicit `mentions` edges from any `[[...]]` reference that does not appear inside a `rel:` line.

Edge directionality is from source (the enclosing block) to target.

## 8. Recommended verb vocabulary {#verb-vocabulary}

Open set — any kebab-case identifier is legal. The following verbs SHOULD be used where applicable for interoperability:

| Verb | Meaning |
|------|---------|
| `supports` | source provides evidence for target |
| `contradicts` | source conflicts with target |
| `derives-from` | source is computed/inferred from target |
| `supersedes` | source replaces target (target is stale) |
| `amends` | source refines target — keeps target valid but narrows / adds exceptions |
| `depends-on` | source requires target |
| `instance-of` | source is an instance of target type |
| `part-of` | source is a component of target |
| `mentions` | weak reference, no semantic claim |
| `defines` | source is the definition of target term |
| `example-of` | source illustrates target |

Tools MAY warn on unrecognized verbs but MUST NOT reject the document.

## 9. Memory and skills profile {#memory-skills-profile}

When a GMD document is used as a Claude memory file or skill:

- Document frontmatter `id` is REQUIRED.
- Each top-level concept SHOULD have a stable `{#id}`.
- Cross-memory links SHOULD use `[[memory-id#node-id]]` rather than slug-based wikilinks.
- A `supersedes` edge marks a memory as replacing an older one. Loaders MAY filter superseded nodes from retrieval results.

## 10. Index (non-normative) {#index}

GMD-aware tooling MAY generate a sidecar index for retrieval acceleration. The index is derived and regenerable. Recommended location: `<file>.gmd.db` (DuckDB) alongside the document, gitignored.

Schema sketch:

```sql
CREATE TABLE nodes (
  doc TEXT, id TEXT, path TEXT, title TEXT,
  kind TEXT, attrs JSON, content TEXT, content_hash TEXT,
  PRIMARY KEY (doc, id)
);
CREATE TABLE edges (
  src_doc TEXT, src_id TEXT,
  verb TEXT,
  dst_doc TEXT, dst_id TEXT,
  attrs JSON, weight REAL
);
CREATE TABLE embeddings (
  doc TEXT, id TEXT, model TEXT, vec FLOAT[]
);
```

Index format is not part of conformance. Any tool may use any format.

## 11. Conformance levels {#conformance-levels}

| Level | Requirement |
|-------|-------------|
| **Reader** | Renders document as Markdown without error. Ignores `{#id}`, `[[...]]`, `rel:` lines, or shows them as plain text. |
| **Resolver** | Reader behavior plus: resolves `[[...]]` references to anchors when targets exist. |
| **Indexer** | Resolver behavior plus: extracts `rel:` edges and node tree; produces a queryable graph. |
| **Retriever** | Indexer behavior plus: returns subtree/ego-graph slices on demand, optionally ranked by vector similarity. |

A document is conforming if it parses as CommonMark and respects §3, §4, §5 syntax.

## 12. Reserved syntax {#reserved-syntax}

Future versions may assign meaning to: `@id`, `^id`, `(())`, `==text==`, lines beginning with `:` or `>>`. Authors SHOULD NOT use these forms.

## 13. Example {#example}

```markdown
---
gmd: "0.1"
id: project-alpha
title: Project Alpha
tags: [planning, draft]
---

# Problem {#p1}

Users lose context across sessions.

rel: motivates -> [[#s1]]
rel: observed-in -> [[incident-2026-03-12#root-cause]]

## Symptom {#p1.1}

Repeated questions about the same file.

rel: evidence-for -> [[#p1]]

# Solution {#s1}

Persistent memory layer keyed by stable IDs.

rel: depends-on -> [[#s1.1]]
rel: supersedes -> [[old-design#stateless]] {confidence=high}

## Append-only store {#s1.1 kind=store}

Facts written once, referenced by ID, never mutated in place.
```

## 14. Open questions (v0.1 → v0.2) {#open-questions}

- Inline `rel:` shorthand for high-density authoring?
- Namespaces for cross-project doc IDs.
- Whether `parent` edge should be explicit or remain implicit-only.
- Conflict resolution when two docs claim the same `id`.
- Index file format standardization (DuckDB chosen here, others possible).
