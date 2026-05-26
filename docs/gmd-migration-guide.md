---
gmd: "0.1"
id: gmd-migration-guide
title: "GMD Migration Guide — Converting an Existing Project to Full GMD Compliance"
tags: [migration, gmd, authoring]
imports: [agent-doc-primer]
---

# GMD Migration Guide {#root}

Step-by-step playbook for taking a project's existing markdown
documentation and converting it to **full GMD compliance**, so every
doc participates in `rmx context` / `rmx neighbors` walks as a graph
of typed, walkable nodes instead of opaque prose.

Read [[agent-doc-primer#root]] first for the form-selection decision
tree. This guide assumes you've already decided that GMD is the right
target form (i.e. your doc is a graph of small retrievable pieces, not
an ADR or .pseudo file).

rel: depends-on -> [[agent-doc-primer#root]]
rel: part-of -> docs/

## Phase 1 — Audit existing docs {#audit}

Inventory before you cut. Run from the project root:

```bash
# All markdown candidates (skip vendored + cache trees).
fd -e md -E node_modules -E .venv -E .tldr -E .git -E graphify-out

# Which already carry GMD frontmatter?
rg -l "^gmd:" -g '*.md'

# Which look like graph-y content (multi-section reasoning, decision
# trails, dependency catalogs)? Those convert cheapest.
rg -l "depends on|supersedes|see also|related to" -g '*.md'
```

Bucket each candidate:

| Bucket | What to do |
|---|---|
| Already has `gmd:` | Skip — already compliant. Just audit anchor coverage. |
| Reasoning / decision trails | Convert first — highest ROI. |
| Reference / catalog docs | Convert second — each entry becomes a node. |
| Tutorial / linear prose | Last — value depends on whether sections will be cited. |
| Plain notes / sessions | Don't convert. Leave as plain markdown. |

rel: part-of -> [[#root]]

## Phase 2 — Add frontmatter {#frontmatter}

Every GMD doc starts with a YAML frontmatter block. Minimum:

```markdown
---
gmd: "0.1"
id: <doc-id-in-kebab-case>
title: "Human-readable title"
---
```

Optional but recommended:

```markdown
---
gmd: "0.1"
id: spatial-zone-design
title: "Spatial Zone — Design Reasoning"
tags: [spatial, design, geometry]
imports: [adr/0087, [[spatial-bbox-tradeoffs]]]
---
```

Rules:

1. `gmd:` must be quoted (`"0.1"`) — bare `0.1` parses as float and
   may confuse the YAML reader.
2. `id:` must be kebab-case (`[a-z0-9][a-z0-9._/-]*`). It's the
   namespace prefix for every anchor in this doc.
3. `imports:` declares cross-doc refs you'll resolve later. Listed
   doc-ids resolve via the ingest batch — list them up-front so
   `[[other-doc#anchor]]` refs land instead of dangling.

rel: part-of -> [[#root]]

## Phase 3 — Anchor headings {#anchors}

Convert every heading that names a walkable concept into an
`{#anchor-id}` heading. Headings without `{#...}` still nest into the
implicit `part-of` tree but aren't directly addressable.

Before:

```markdown
## Why polygons over rectangles

Polygons capture occlusion better than BBOXes.
```

After:

```markdown
## Why polygons over rectangles {#polygon-choice}

Polygons capture occlusion better than BBOXes.
```

Rules:

1. One concept per heading. Don't combine ("### Zones, Places,
   Stations" packs three concepts under one anchor — split them).
2. Anchor ids are kebab-case + may use `.` `_` `/` `-`. Keep them
   short and stable; they show up in `rmx context` paths.
3. Don't reuse an anchor id within a doc. The parser auto-disambiguates
   (`#choice_2`) which breaks any incoming refs.
4. Skip the marker on purely structural headings ("## Notes",
   "## TODO") that no other doc will ever cite.

rel: part-of -> [[#root]]

## Phase 4 — Add typed edges {#edges}

For each anchored node, declare its semantic relationships with
`rel:` lines immediately under the heading.

```markdown
## Polygon implementation notes {#polygon-implementation}

rel: defined-in -> src/viascope/spatial/shapes.py
rel: depends-on -> adr/0087 {weight=0.8}
rel: supports -> [[polygon-choice]]
rel: contradicts -> [[bbox-trade]]

Polygons pack worse than BBOXes but capture occlusion better.
```

Rules:

1. **`rel:` MUST start at column 0.** The parser is line-based, not
   Markdown-block-aware. Indented `rel:` lines are silently ignored.
2. Prefer the recommended verbs (see [[agent-doc-primer#root]]):
   `supports`, `contradicts`, `derives-from`, `supersedes`,
   `depends-on`, `instance-of`, `part-of`, `mentions`, `defines`,
   `example-of`, `parent`, `defined-in`, `evidence-for`, `motivates`,
   `solves`. Custom verbs work (auto-registered) but reduce cross-doc
   traversal payoff because no other doc speaks them.
3. Targets resolve in three forms:
   - `[[anchor]]` — local node id within this doc
   - `[[other-doc#anchor]]` — node in another GMD doc
   - `path/to/file.py` — bare path (works for file refs without `[[]]`)
4. `{weight=0.8}` weights the edge. Default 1.0. Use lower weights
   for soft / probabilistic relations.

rel: part-of -> [[#root]]

## Phase 5 — Add wikilink mentions {#mentions}

Inside prose (not on `rel:` lines), use `[[ref]]` to cross-reference
concepts. These emit `mentions` linkages and let `rmx context` find
the doc via concept-name search.

```markdown
The [[polygon-choice]] decision was driven by occlusion semantics; see
[[adr/0087#geometry-rationale]] for the binding ADR.
```

Wikilink rules:

1. `[[ref]]` outside `rel:` lines → `mentions` linkage (light weight).
2. Unresolved refs become standalone `mentions` concepts, so they're
   still retrievable by text — but cross-doc walks break.
3. Don't use `[[ref]]` for HTTP links — plain Markdown `[text](url)`
   for those.

rel: part-of -> [[#root]]

## Phase 6 — Aliases for retrievability {#aliases}

If a node has alternate names (acronyms, spelled-out forms,
synonyms), declare them as aliases. Each alias becomes a high-weight
`mentions` concept pointing at this node, so queries with any name
land here.

```markdown
## Polygon implementation {#polygon-implementation alias=[poly-impl, polygon-impl, polygon code]}
```

Rules:

1. `alias=[...]` lives inside the `{#...}` braces.
2. Comma-separated. Quote any alias containing whitespace.
3. Aliases are first-class — they're indexed at higher weight (3.0)
   than title tokens (2.0) and body terms (TF).

rel: part-of -> [[#root]]

## Phase 7 — Ingest + validate {#validate}

Run the GMD ingest, inspect the report, fix issues.

```bash
# Ingest just GMD docs (skip the heavy code walk)
rmx ingest-gmd docs/

# Or full project ingest (GMD detected via frontmatter sniff)
rmx ingest .
```

Watch for the report's tail:

```
ingested 12 doc(s), 87 node(s), 134 rel: edge(s), 256 mention(s)
new linkage types: solves, motivates
unresolved refs: 4
  docs/spatial-design.md:42: [[polygon-impl]]
  docs/spatial-design.md:88: [[adr/0091#missing]]
  ...
```

Triage `unresolved refs`:

| Unresolved | Fix |
|---|---|
| `[[some-doc]]` (no `#`) | Add `some-doc` to your `imports:` list, or check the target doc's `id:` matches. |
| `[[some-doc#anchor]]` | Verify the target's anchor id (no typo, no auto-disambig). |
| `[[anchor]]` (local) | Check the local heading has `{#anchor}` and no duplicate elsewhere in the doc. |

Then per-node smoke check:

```bash
rmx context <doc-id>#<node-id>     # should return your node + neighbors
rmx neighbors <doc-id>#<node-id>   # walks the typed rels you declared
rmx query "mentions:<some-token>"  # should return docs that mention it
```

rel: part-of -> [[#root]]
rel: depends-on -> [[#edges]]
rel: depends-on -> [[#mentions]]

## Phase 8 — Iterate to zero unresolved {#iterate}

Cross-doc references are the hard part. Re-run the loop until
`unresolved refs: 0`:

1. Note the unresolved set from the last ingest.
2. For each, decide: fix source doc, fix target doc id, or add to
   `imports:`.
3. Re-ingest the affected docs (or all GMD docs, cheap).
4. Repeat.

GMD ingest is per-file destructive — sync purges a doc's prior
entities before re-walking it. Safe to re-run as many times as
needed.

rel: part-of -> [[#root]]

## Phase 9 — Lock it in {#lockin}

Once docs are GMD-compliant:

1. **Commit the docs.** GMD docs are pure markdown; they round-trip
   through git unchanged.
2. **Install hooks.** `rmx install-hooks` wires post-Edit + git
   hooks so docs re-ingest on save / commit. Drift dies.
3. **Add a primer link.** Reference [[agent-doc-primer#root]] from
   your `CLAUDE.md` / `README.md` so future agents author in the
   right form from day one instead of writing prose that needs
   re-migration.

rel: part-of -> [[#root]]

## Common conversion patterns {#patterns}

### Decision log → GMD {#pattern-decision-log}

A markdown decision log with `## YYYY-MM-DD: <decision>` headings
converts cleanly:

- Anchor: `{#YYYY-MM-DD-slug}` (dates are valid in kebab-case).
- Verbs: `supersedes` (newer over older), `depends-on` (one decision
  enabled by another), `motivates` (decision → spec / plan it
  enables).

rel: part-of -> [[#patterns]]
rel: example-of -> [[#edges]]

### Architecture catalog → GMD {#pattern-arch-catalog}

A doc listing system components becomes a node-per-component graph:

- Anchor per component: `{#component-name}`.
- Verbs: `part-of` (component → subsystem), `depends-on` (component →
  dependency), `defined-in` (component → source path).

rel: part-of -> [[#patterns]]

### Migration / runbook → GMD {#pattern-runbook}

A linear runbook becomes a `depends-on` chain:

- Anchor per step: `{#step-1-name}`, `{#step-2-name}`.
- Each step: `rel: depends-on -> [[step-N-prev]]`.
- Enables `rmx neighbors <step-N> --depth 5` to walk forward through
  the whole sequence.

rel: part-of -> [[#patterns]]

## What NOT to convert {#do-not}

GMD is overhead. Don't convert:

- **Session notes / retros** — transient, no one walks the graph.
- **README / CHANGELOG** — already discoverable by every tool; GMD
  buys nothing.
- **Tutorials with linear prose flow** — the part-of tree fights the
  narrative; readers want the prose, not nodes.
- **Generated docs** (API references emitted from code) — re-emit
  from source, don't hand-edit.

rel: part-of -> [[#root]]

## Self-check matrix {#selfcheck}

After migration, every converted doc should pass:

| Check | Command | Expected |
|---|---|---|
| Doc is indexed | `rmx context <doc-id>` | returns the doc + immediate children |
| Anchors walkable | `rmx context <doc-id>#<anchor>` | returns just that node + neighbors |
| Edges resolved | last ingest report | `unresolved refs: 0` |
| Concepts retrievable | `rmx query "mentions:<key-term>"` | doc shows in results |
| Inverse walks work | `rmx neighbors <target-doc>#<anchor>` | source doc appears as inbound `part-of` / `depends-on` etc. |

rel: part-of -> [[#root]]
