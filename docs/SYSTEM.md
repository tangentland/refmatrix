---
gmd: "0.1"
id: SYSTEM
title: "refmatrix — System Overview"
tags: [system, overview, bitmaps, discovery]
---

# refmatrix — System Overview {#root}

rel: related-to -> [[ARCHITECTURE]]
rel: related-to -> [[INTEGRATION]]
rel: related-to -> [[PERFORMANCE]]

## What refmatrix is {#what-refmatrix-is}

refmatrix (CLI: `rmx`) is a **roaring-bitmap-backed reference matrix** for the
three concrete things that live in a software project: **documents, code, and
concepts**. Every entity gets a stable integer column id; every concept gets a
row; every linkage type (`defines`, `calls`, `mentions`, `imports`, `is_a`,
`related_to`, `specifies`, ... open set) is a field whose
`(linkage_type, concept_id)` cells are roaring bitmaps of entity column ids.

The conceptual model mirrors [Pilosa](https://github.com/FeatureBaseDB/featurebase)
(index → field → row → column) but storage is in-process via
[pyroaring](https://github.com/Ezibenroc/PyRoaringBitMap) plus a SQLite or
DuckDB catalog. No server, no HTTP, single-binary CLI. A long-lived per-store
daemon (Unix socket) serializes all access so concurrent CLI clients and
filesystem-watcher writes never race on the catalog.

The headline capability is **set-algebra queries that grep can't answer**:

```bash
rmx query "defines:auth AND NOT mentions:auth"
# code that implements `auth` but is documented nowhere

rmx query "specifies:Zone AND NOT defines:Zone"
# plan/issue/spec docs that named a concept no code has produced yet
```

## Mental model — three layers {#mental-model-three-layers}

| Layer    | What lives here                       | Backed by                          |
|----------|---------------------------------------|------------------------------------|
| Catalog  | entities, concepts, linkage types     | SQLite or DuckDB (`.refmatrix/`)   |
| Bitmaps  | per-(linkage, concept) entity sets    | pyroaring `BitMap64` fragments     |
| Evidence | file:line provenance for each linkage | catalog `linkage_evidence` table   |

Entities are kinded — `doc`, `code`, `concept`, `query`. Each entity carries a
`tldr` field (one-line summary) and a `meta` JSON blob (language, signature,
docstring, code preview, CFG/DFG summaries when available). Linkage types are
created on demand; ingesters that encounter an unknown verb auto-register it.

## How refmatrix extends and enhances `llm-tldr` {#how-refmatrix-extends-and-enhances-llm-tldr}

refmatrix **composes with** [llm-tldr](https://github.com/parcadei/llm-tldr) —
tldr is the per-function extractor, refmatrix is the indexer and query layer.
Where tldr produces a per-unit semantic dump and a call graph, refmatrix
turns those into a queryable bitmap matrix and adds extraction passes that
tldr does not perform.

### What tldr produces (and refmatrix consumes) {#what-tldr-produces-and-refmatrix-consumes}

- `.tldr/cache/semantic/metadata.json` — per-unit semantic dump: signature,
  docstring, code preview, CFG/DFG summary, unit_type, language.
- `.tldr/cache/call_graph.json` — leaner: `(from_file, from_func) → [callees]`.

`rmx tldr-warm` shells out to `llm-tldr` (`src/refmatrix/cli.py:1425`), then
`rmx ingest` chooses the richest available source in this priority order
(`src/refmatrix/ingest.py:40-48`):

```
.tldr/cache/semantic/metadata.json   (richest — full semantic)
  ↓ fallback
.tldr/cache/call_graph.json          (leaner — calls only)
  ↓ fallback
filesystem tree walk                 (file-level entities, no call graph)
```

Override with `rmx ingest . --source metadata|tldr|tree`.

### What tldr does NOT do (refmatrix adds) {#what-tldr-does-not-do-refmatrix-adds}

| Extractor                                  | Where                                          | What it emits |
|--------------------------------------------|------------------------------------------------|---------------|
| Python AST imports + docstring keywords    | `ingest.py:_ingest_python_semantics`           | `imports`, keyword `mentions` |
| Pseudocode type/func parser                | `ingest.py:_ingest_pseudo_semantics`           | `defines`, `is_a` from `.pseudo` files |
| ADR-aware markdown extractor               | `ingest.py:_ingest_adr_semantics`              | `defines` from ADR class specs, `related_to` from `ADR-NNNN` xrefs |
| Concept-doc H1/H3 + fenced class specs     | `ingest.py:_ingest_markdown_semantics`         | `defines` from PascalCase headings + fenced `Class:` blocks |
| Plan/spec/issue extractor (`specifies`)    | same, `_is_plan_file()` branch                 | `specifies` (and inverse `specified_by`) — provenance from plan/issue/spec doc to concept it declares intent for |
| GMD (Graph Markdown) parser                | `ingest_gmd.py`                                | typed `rel:` edges, `mentions` from `[[wikilinks]]`, `part-of` from heading hierarchy, `imports` from frontmatter |
| Bare-name + kind/unit_type categorization  | `ingest.py:205-240`                            | universal entity → category linkages over tldr units |

### Plans, specs, and issues are first-class {#plans-specs-and-issues-are-first-class}

The `specifies` edge promotes plan / spec / issue / roadmap markdown from
*generic ingest* (one entity per file, weak `mentions` from docstrings) to
**typed semantic citizens** of the same authority hierarchy as ADRs, concept
docs, and code:

```
authority hierarchy (strongest → weakest)
    ADR              defines
    plan / spec      specifies      ← new, was invisible to discovery
    concept doc      defines
    pseudocode       defines, is_a
    code             defines (from tldr units + AST)
```

A markdown file is treated as a plan-doc when **either** condition matches
(`ingest.py:_is_plan_file`):

| Trigger        | Matches                                                  |
|----------------|----------------------------------------------------------|
| Filename       | `^(PLAN\|ISSUE\|SPEC\|ROADMAP)([-_].*)?\.md$` (case-insensitive) |
| Path segment   | any of `plans/`, `plan/`, `specs/`, `spec/`, `issues/`, `issue/`, `roadmap/` |

Plan-docs flow through the same H1 + H3 + fenced-class-spec emitter as
concept docs, but the verb flips: `defines` → `specifies`. Inverse
`specified_by` is registered so queries traverse both directions.

**What this unlocks** — queries that were structurally impossible before:

```bash
rmx query "specifies:Zone AND NOT defines:Zone"
# concepts named in a plan/spec/issue but never built

rmx query "specifies:Zone OR defines:Zone"
# everything that touched Zone, from intent through implementation

rmx neighbors PLAN-zone-overhaul.md
# walk the concepts a plan declared intent for, then their code
```

Without `specifies`, this answered "nothing" — the discovery ladder
structurally could not find the design that drove a concept. With it, plans
participate in the same set algebra as code and docs. See
`ISSUE-adr-semantic-extraction.md` for the failure mode that motivated the
edge type (ADR-0087 specified `Zone` across 52 sessions; agents pattern-
matched code instead and built five fragmented alternatives because the
ADR was invisible to `rmx context Zone`).

GMD plan-docs (with `gmd:` frontmatter) get the same edge type via
author-declared `rel: specifies -> [[#X]]` — the heuristic and the
explicit author path emit the *same* `specifies` linkage type
(`store.py:DEFAULT_LINKAGES`).

### Net result {#net-result}

`tldr` answers *what does this function do?*  
`rmx` answers *what set of entities satisfy this combination of relations?* —
including relations tldr never sees (markdown semantics, design docs,
cross-file `is_a`, plan→concept intent), and answers them as bitmap algebra
over a stable column space rather than as cache lookups.

## Lifecycle — how a project becomes an index {#lifecycle-how-a-project-becomes-an-index}

```
┌──────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────┐
│  source  │ →  │   ingest     │ →  │   catalog    │ →  │  query   │
│  files   │    │              │    │   + bitmap   │    │  + ctx   │
└──────────┘    │ tldr warm    │    │   fragments  │    │          │
                │ ast / md /   │    │              │    │ rmx q    │
                │ adr / gmd /  │    │ .refmatrix/  │    │ rmx ctx  │
                │ plan         │    │              │    │ rmx grep │
                └──────────────┘    └──────────────┘    └──────────┘
                       ↑                   ↑                  ↑
                       │                   │                  │
                ┌──────┴──────┐     ┌──────┴──────┐    ┌──────┴──────┐
                │   watcher   │     │   daemon    │    │ scan-prompt │
                │ (watchdog)  │     │ (rmxd.sock) │    │ (LLM hook)  │
                └─────────────┘     └─────────────┘    └─────────────┘
```

1. **`rmx init`** creates `.refmatrix/` (catalog + fragments dir).
2. **`rmx tldr-warm . --semantic`** runs `llm-tldr` and ingests its output.
3. **`rmx install-hooks`** wires git post-commit/merge/checkout/rewrite hooks
   plus Claude Code `PostToolUse`/`Stop`/`SessionStart`/`UserPromptSubmit`
   hooks. From here, edits trigger incremental `rmx sync` automatically.
4. **`rmx daemon start`** (optional but recommended): owns the catalog lock,
   serves a Unix socket for all read/write ops, embeds the file watcher.
   Without it, every CLI invocation pays SQLite/DuckDB open cost.
5. **Queries** route through the daemon when present; otherwise the CLI
   opens the catalog directly (read-only ops only — writes need the daemon
   if one is running).

## Primary use cases {#primary-use-cases}

The recommended **discovery ladder** for an agent (or human) trying to find
something in a codebase, in order of increasing cost and decreasing semantic
density:

```
rmx context <symbol>     →  semantic neighborhood, token-budgeted
       ↓ miss
rmx query <expression>   →  set-algebra over linkage bitmaps
       ↓ miss
rmx grep <pattern>       →  index-first pattern match, rg fallback,
                            promotes hits back into the index
```

Each step is faster + more answer-shaped than the next; falling through to
`rmx grep` is the explicit "I don't know what concept I'm looking for, give
me anything that matches this string" escape hatch — and it teaches the
index, so the next equivalent query lands at the `rmx query` step instead.

### By task {#by-task}

| Task                                       | Command                                                                 |
|--------------------------------------------|-------------------------------------------------------------------------|
| Pattern search (index-first, rg fallback)  | `rmx grep <pattern>` — learns on miss, promotes rg hits into the index  |
| Semantic neighborhood walk                 | `rmx context <symbol> --max-tokens 2000`                                |
| Walk a symbol's edges                      | `rmx neighbors <symbol> --depth 2`                                      |
| Find implementation gap                    | `rmx query "defines:X AND NOT mentions:X"` — code with no docs          |
| Find documentation orphan                  | `rmx query "mentions:X AND NOT defines:X"` — docs with no code          |
| Find unimplemented spec                    | `rmx query "specifies:X AND NOT defines:X"` — plan with no code yet     |
| Find what a symbol calls / is called by    | `rmx query "calls:X"` / `rmx query "called_by:X"`                       |
| Find co-mentioned concepts                 | `rmx co-occur <symbol> --type defines`                                  |
| Dump all metadata for one file / node      | `rmx describe <path\|id\|name>` — row, edges, evidence, tracked, vectors |
| Surface a project's top concepts           | `rmx top --limit 50` / `rmx primer` (writes `.refmatrix/PRIMER.md`)     |
| Project orientation for a new agent        | `rmx install-hooks` + `rmx primer` (briefing written to `.refmatrix/CLAUDE.md`) |
| Cross-codebase concept matching            | `rmx canon link <local-concept> <canonical-concept>`                    |
| Multi-codebase shared catalog              | `rmx partition add <name>` — keep multiple repos in one rmx instance    |
| Save + replay a complex query              | `rmx save-query <name> "<expr>"` then `rmx run <name>`                  |
| Audit query history                        | `rmx telemetry` — p50/p99 per op from `.refmatrix/query.log`            |

### By role {#by-role}

| Role                          | Workflow                                                                 |
|-------------------------------|--------------------------------------------------------------------------|
| **LLM agent (Claude Code)**   | Hooks fire automatically: `UserPromptSubmit` injects scan-prompt context; `PostToolUse` enqueues edits; `Stop` flushes the queue. Agent uses the discovery ladder for explicit lookups. |
| **Developer (interactive)**   | `rmx query` for set-algebra questions, `rmx grep` for pattern search, `rmx context` when prepping a refactor or briefing a teammate. |
| **CI / batch**                | `rmx query --ids-only` for machine-readable output; pipe to other tooling. `rmx stats` + `rmx telemetry` for health dashboards. |
| **Architect / design lead**   | `rmx query "specifies:X AND NOT defines:X"` to find unimplemented ADRs / plans / specs. `rmx neighbors` to audit cross-references between design docs. |
| **Maintainer**                | `rmx vacuum` + `rmx prune-noise` + `rmx compact` weekly. `rmx telemetry` to find slow queries. |

## What refmatrix is not {#what-refmatrix-is-not}

- **Not a vector store.** No embeddings in the core. The scoring stack
  (BM25 + docstring linkage + coverage^3 + linkage-coupled co-mention^2)
  consistently beats CodeRankEmbed on CSN Python/JavaScript MRR@10 — see
  `eval/` and [[PERFORMANCE#benchmark-results]]. Embedding integration is on the roadmap
  but not currently in the index path.
- **Not a code-execution sandbox.** rmx never runs project code; all
  extraction is static (AST / regex / fenced-block parsing).
- **Not a server.** Single-process CLI + per-store daemon. No HTTP, no
  central service, no cluster.

## File layout in a project {#file-layout-in-a-project}

```
my-project/
├── .refmatrix/                  # created by `rmx init`
│   ├── catalog.duckdb (or .db)  # entities, concepts, linkage types, evidence
│   ├── fragments/
│   │   └── <partition>/
│   │       ├── defines.rb64     # roaring bitmap per linkage type
│   │       ├── calls.rb64
│   │       └── ...
│   ├── rmxd.sock                # daemon Unix socket (when running)
│   ├── rmxd.pid                 # daemon pidfile
│   ├── dirty.queue              # pending paths from PostToolUse hook
│   ├── query.log                # JSONL telemetry
│   ├── PRIMER.md                # auto-generated symbol primer
│   └── CLAUDE.md                # briefing for Claude Code agents
├── .tldr/                       # populated by `llm-tldr`; rmx reads only
│   └── cache/
│       ├── semantic/metadata.json
│       └── call_graph.json
└── .tldrignore                  # exclusions (shared with llm-tldr)
```

## Where to go next {#where-to-go-next}

- **[[ARCHITECTURE]]** — module layout, dependency graph, storage internals.
- **[[INTEGRATION]]** — hooks, GMD spec, watcher, daemon socket protocol,
  external CLI dependencies.
- **[[PERFORMANCE]]** — bitmap operations, daemon hot-path, scoring stack,
  eval methodology, benchmark numbers vs. CodeRankEmbed.
