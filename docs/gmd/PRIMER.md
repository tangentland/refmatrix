---
gmd: "0.1"
id: gmd-primer
title: "GMD Primer"
tags: [gmd, reference]
---

# GMD Primer {#root}

Spec: [`docs/gmd/SPEC.md`](SPEC.md). Lint: `python3 tools/gmd/lint.py <path>` (or `./scripts/lint-gmd.sh`).

A doc is **GMD** (Graph Markdown) when its frontmatter has `gmd: "0.1"`. GMD adds three
constructs on top of plain Markdown. Interpret them as a graph, not prose noise.

## Anchor {#anchor}

`## Heading {#stable-id}` — a stable node id for any heading, paragraph, or list item. Reference
nodes by their leaf id. Ids stay stable when surrounding prose changes, so links don't rot.

## Wikilink {#wikilink}

`[[#id]]` — same-doc reference. `[[doc-id#id]]` — cross-doc (doc-id matches another file's
frontmatter `id`, or its filename stem). These are **edges** — resolve them to the anchored node;
don't grep prose for the text.

## Typed edge {#rel}

```
rel: <verb> -> [[target]] [{attrs}]
```

A single line at column 0. It attaches a typed edge to the nearest enclosing block that has an id.
The verb is kebab-case. Standard vocabulary: `supersedes`, `amends`, `implements`, `realizes`,
`derives-from`, `evidence-for`, `depends-on`, `contradicts`, `defined-in`, `encoded-as`,
`part-of`, `motivates`, `catalogs`, `specifies`, `specified-by`. Custom verbs are legal (lint
warns, doesn't fail).

## Read GMD as a graph {#interpret}

- Anchors are node ids — stable addresses. Don't rename casually.
- Wikilinks are edges — follow them instead of grepping prose.
- `rel:` lines are typed edges. `rel: supersedes -> [[adr-0042#old-spec]]` means the current node
  REPLACES that target — load the target only as historical context.
- Frontmatter `imports: [foo]` makes `[[foo]]` resolve to that doc's id without the doc prefix.

## Authoring new GMD files {#authoring}

When this project's rules require GMD (ADRs, concept docs, design tenets, plan/task specs,
memory files, and any markdown other docs will reference):

1. **Frontmatter**: `gmd: "0.1"` + a unique `id` + `title` + `tags: [...]`. The `id` should match
   the filename stem.
2. **`{#anchor}` on every heading** (H1, H2, H3 — all of them).
3. **`rel:` edges** wherever the doc cites, depends on, supersedes, amends, implements, or derives
   from another doc. No bare prose citations.

Validate before committing: `python3 tools/gmd/lint.py <path>` — zero errors. The full
conformance spec is [`docs/gmd/SPEC.md`](SPEC.md).

## Tooling {#tooling}

Bundled under `tools/gmd/`:

| Command | Purpose |
|---------|---------|
| `tools/gmd/gmd lint <path>` | Validate GMD docs (exit 1 on errors) |
| `tools/gmd/gmd init <root>` | Scaffold a project for GMD authoring |
| `tools/gmd/gmd slice <file> "<query>"` | Retrieve a relevant subset of a GMD doc |
| `./scripts/lint-gmd.sh` | Lint `CLAUDE.md` + `docs/` with the right scope |
