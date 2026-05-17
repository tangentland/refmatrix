# refmatrix — Architecture

## Layered view

```
┌──────────────────────────────────────────────────────────────────────┐
│                     CLI / Hook Surface                               │
│   cli.py · hooks.py                                                  │
└───────────────────────────────┬──────────────────────────────────────┘
                                │
┌───────────────────────────────┴──────────────────────────────────────┐
│                    Daemon / Concurrency Layer                        │
│   daemon.py  (per-store Unix socket, owns catalog lock,              │
│               embeds watcher, dispatches 21 named ops)               │
└───┬───────────────────┬─────────────────────────┬───────────────────┘
    │                   │                         │
┌───┴────────┐  ┌───────┴────────────┐   ┌────────┴────────────────────┐
│  Ingest    │  │     Query          │   │       Sync / Watch          │
│  Pipeline  │  │     Layer          │   │                             │
│ ingest.py  │  │ query.py           │   │ sync.py    incremental      │
│ ingest_gmd │  │ context.py         │   │ watch.py   watchdog observer│
│ scan.py    │  │ primer.py          │   │ scan.py    prompt → ctx     │
│            │  │ telemetry.py       │   │                             │
└───┬────────┘  └───────┬────────────┘   └────────┬────────────────────┘
    │                   │                         │
    └───────────────────┴─────────────────────────┘
                        │
┌───────────────────────┴──────────────────────────────────────────────┐
│                       Core Data Layer                                │
│  store.py    SQLite + roaring bitmap fragments                       │
│  backend.py  SQLite vs DuckDB backend selection                      │
│  duckdb_catalog.py   native DuckDB schema (phase 3)                  │
│  duckdb_view.py      read-only DuckDB facade over SQLite (phase 1)   │
│  migrate.py          one-shot SQLite → DuckDB migration              │
└──────────────────────────────────────────────────────────────────────┘
```

## Module inventory

| Module              | Purpose                                                     | Public surface                                    |
|---------------------|-------------------------------------------------------------|---------------------------------------------------|
| `store.py`          | Root abstraction: catalog + bitmap fragments                | `Store`, `Entity`                                 |
| `backend.py`        | Catalog backend selection (SQLite vs DuckDB)                | `select_backend`, `SQLiteBackend`, `DuckDBBackend`|
| `duckdb_catalog.py` | Native DuckDB schema (CATALOG_DDL)                          | `init_catalog`                                    |
| `duckdb_view.py`    | Read-only DuckDB view over SQLite catalog                   | `ReadConnection`, `DuckCatalogView`               |
| `migrate.py`        | One-shot SQLite → DuckDB migration                          | `migrate_catalog`                                 |
| `ingest.py`         | Multi-source ingestion (metadata/tldr/tree/semantic)        | `ingest_path`                                     |
| `ingest_gmd.py`     | GMD (Graph Markdown) parser + registration                  | `parse_gmd`, `ingest_gmd_paths`                   |
| `sync.py`           | Incremental sync (file batches → re-ingest)                 | `enqueue`, `drain_queue`, `sync_files`, `sync_since` |
| `watch.py`          | watchdog observer → debounced sync_files                    | `Debouncer`, `run_watcher`                        |
| `query.py`          | DSL set algebra + PQL Pilosa-style ops + RRF fusion         | `QueryEngine`, `Token`, `fuse_rrf`                |
| `context.py`        | Token-budgeted context bundles, RRF-fused symbol walk       | `build_context`, `render_text`, `estimate_tokens` |
| `primer.py`         | Density-ranked, symbol-shape-filtered concept map           | `build_primer`, `concept_density`                 |
| `scan.py`           | Prompt → matched concepts → context bundles (LLM hook)      | `scan_prompt`, `extract_candidates`               |
| `telemetry.py`      | JSONL query log (`query.log`)                               | `log_query`, `summarize`                          |
| `daemon.py`         | Per-store Unix-socket server; OPS dispatch                  | `Daemon`, `ping`, `call`, `spawn_daemon`          |
| `hooks.py`          | Git + Claude Code hook installer                            | `install`                                         |
| `cli.py`            | Click CLI; routes ~50 subcommands; daemon lifecycle         | `main`                                            |

## Dependency flow

```
cli ────────────────────────────┐
   ├─→ hooks                    │
   ├─→ daemon ─────┬───────────→│
   │     └─→ watch ──→ sync ────│
   │                            │
   ├─→ ingest ──────────────────│
   ├─→ ingest_gmd ──────────────│→ store ─→ backend ─→ duckdb_catalog
   ├─→ migrate ──→ duckdb_catalog                ↘
   ├─→ query ─────────────────→ store             duckdb_view (phase 1)
   ├─→ context ──→ query ─────→ store
   ├─→ primer ────────────────→ store
   ├─→ scan ─────→ context ───→ store
   └─→ telemetry ─────────────→ store
```

All non-trivial reads and writes go through `Store`. `daemon.py` is the only
place that owns a `Store` instance long-term; CLI commands that talk to a
running daemon open no `Store` of their own.

## Core data layer

### Catalog schema (DuckDB, native — `duckdb_catalog.py:CATALOG_DDL`)

| Table                | Key columns                                              | Purpose                              |
|----------------------|----------------------------------------------------------|--------------------------------------|
| `entities`           | id, kind, name, path, tldr, meta, protected, noise       | One row per doc/code/concept/query   |
| `concepts`           | id (entity_id), description                              | Concept-kinded entity sidecar        |
| `linkage_types`      | id, name, directed, description, inverse                 | Open-set verb registry               |
| `entity_links`       | linkage_id, concept_id, entity_id, weight                | SQL-shadow of bitmap content (FK)    |
| `linkage_evidence`   | linkage_id, concept_id, entity_id, file, line, detail    | file:line provenance per linkage     |
| `tracked_files`      | path, mtime, last_synced                                 | Incremental skip on unchanged files  |
| `bitmap_fragments`   | partition_id, linkage_name, blob (BLOB), updated_at      | DuckDB-only bitmap persistence       |
| `partitions`         | id, name, description                                    | Multi-codebase shared catalog        |
| `canon_links`        | local_concept_id, canonical_concept_id                   | Cross-partition concept canonicalization |
| `saved_queries`      | name, expression, created_at                             | `rmx save-query` / `rmx run`         |

### Bitmap fragment storage (`store.py`)

| Concern               | Implementation                                                              |
|-----------------------|-----------------------------------------------------------------------------|
| In-memory shape       | `BitMap64` per `(partition, linkage_type)`                                  |
| Packing               | `(concept_id << 32) | entity_id`                                            |
| Disk layout (SQLite)  | `.refmatrix/fragments/<partition>/<linkage>.rb64`                           |
| Disk layout (DuckDB)  | `bitmap_fragments` BLOB column, UPSERTed per linkage                        |
| Read                  | `load_bitmap(linkage, concept) → BitMap32` via range mask on the packed key |
| Write                 | Lazy fragment load + dirty-set flush at transaction boundary                |
| Atomic persistence    | DuckDB: single transaction; SQLite: write-rename per fragment file          |

### Backend selection (`backend.py`)

The catalog has gone through three phases:

1. **Phase 1 (SQLite + DuckDB view)** — SQLite owns writes, `duckdb_view.py`
   gives read-only DuckDB query access for analytics.
2. **Phase 2 (DuckDB catalog + SQLite fragments)** — DuckDB owns catalog
   tables, bitmap fragments still on disk.
3. **Phase 3 (DuckDB native)** — all catalog + bitmaps in one DuckDB file.
   `migrate.py` performs the one-shot conversion. New stores default to DuckDB.

`backend.py:select_backend()` detects which phase a given `.refmatrix/`
directory is in and dispatches accordingly.

## Ingest pipeline

`ingest_path(store, root, source=..., semantic=...)` is the single entry
point. It dispatches on source priority (richest first):

```
ingest_path
  │
  ├─ source=metadata  → _ingest_tldr_metadata()  (reads .tldr/semantic/metadata.json)
  │                       │
  │                       ├─ entity per unit (kind=code, tldr=signature)
  │                       ├─ calls / called_by linkages
  │                       └─ kind / unit_type / language category linkages
  │
  ├─ source=tldr      → _ingest_tldr()           (reads .tldr/call_graph.json)
  │                       └─ file-level entities + calls only
  │
  ├─ source=tree      → tree walker               (no .tldr cache present)
  │                       └─ file-level entities only
  │
  └─ semantic=True (additive, regardless of source)
       │
       ├─ _ingest_python_semantics()    AST imports + docstring keywords
       ├─ _ingest_pseudo_semantics()    .pseudo type/func parsing
       ├─ _ingest_adr_semantics()       ADR class specs + ADR-NNNN xrefs
       └─ _ingest_markdown_semantics()  H1/H3 + fenced class specs
                ├─ concept-doc path  → defines
                └─ plan-doc path     → specifies   (PLAN|ISSUE|SPEC|ROADMAP files
                                                    or plans/specs/issues/ dirs)
```

GMD files (`.gmd`, or `.md` with `gmd:` frontmatter) go through
`ingest_gmd.py` instead of the markdown semantic pass. The GMD ingestor
auto-creates linkage types from any `rel: <verb> -> <target>` line, so
authors can introduce verbs without code changes.

### Verb policy

| Verb            | Source                                  | Inverse        |
|-----------------|-----------------------------------------|----------------|
| `defines`       | code-implements-concept, doc-defines    | `defined_by`   |
| `specifies`     | plan/spec/issue declares intent         | `specified_by` |
| `calls`         | call graph                              | `called_by`    |
| `imports`       | AST imports, GMD frontmatter            | `imported_by`  |
| `mentions`      | docstring keywords, [[wikilinks]]       | `mentioned_by` |
| `is_a`          | subclass hierarchies (ADR/markdown)     | (none)         |
| `related_to`    | ADR-NNNN cross-references               | (symmetric)    |
| `part-of`       | GMD heading hierarchy                   | `has-part`     |
| (any kebab)     | author-declared GMD `rel:` line         | (none unless registered) |

## Query layer

### DSL (infix set algebra) — `query.py:QueryEngine`

```
rmx query "defines:parser AND NOT mentions:parser"
rmx query "calls:foo OR (mentions:bar AND NOT imports:legacy)"
rmx query "parser"                          # bare term: union across all linkages
```

Operators: `AND` / `&&`, `OR` / `||`, `NOT` / `!`, parentheses. A term is
`linkage:concept` (or just `concept`). Compiles to BitMap32 union / intersect /
difference over the loaded fragments.

### PQL (Pilosa-style) — power-user form

For when the infix form gets clumsy:

```
Intersect(Row(defines='parser'), Difference(Row(any='parser'), Row(mentions='parser')))
```

### Context bundling — `context.py`

`rmx context Foo --max-tokens 2000` returns a token-budgeted bundle of
entities related to `Foo`, walking linkages and **fusing rankings via
Reciprocal Rank Fusion** (`fuse_rrf`, k=60) so multi-linkage signals combine
without per-linkage hyperparameters. The walk knows about `linkage_evidence`,
so the rendered bundle carries `file:line` markers back to where each linkage
was extracted.

### Scoring stack (when ranking, not pure set ops) — `eval/retrievers/rmx_retriever.py`

```
score = BM25(query, entity)
      × coverage(query, entity) ** α      # what fraction of query terms hit
      × Σ_linkage  w_linkage × hits        # weighted by linkage type
      × co_mention(query, entity) ** β     # linkage-coupled, not raw
```

Tuned production variant: `bm25_docstring30_cov30_cm20` — BM25 + docstring
linkage weight 0.30 + coverage^3 + linkage-coupled co-mention^2. Beats
CodeRankEmbed on CSN Python (0.972 vs 0.959 MRR@10) and on CSN JavaScript
(0.939 vs 0.916 MRR@10). See `PERFORMANCE.md` for full eval methodology.

## Daemon / concurrency layer

The catalog's storage engine (DuckDB or SQLite) holds a writer lock that
blocks concurrent processes. With editor + watcher + CLI all wanting to
touch the catalog, lock contention used to corrupt indexes. The daemon
solves this by being the sole owner.

### Lifecycle

```
rmx daemon start
  └─ double-fork
  └─ acquire flock on .refmatrix/rmxd.pid
  └─ open Store (own the catalog lock)
  └─ embed watchdog observer on a worker thread
  └─ serve_forever() on .refmatrix/rmxd.sock
  └─ wait for ping-based readiness signal

rmx <op>           # client side
  └─ socket_path() → check if rmxd.sock alive
  └─ if alive: send JSON op, parse JSON result
  └─ if not:   open Store directly (read-only ops) or fail (writes)
```

### OPS dispatch (`daemon.py:OPS` — 21 named ops)

| Category    | Ops                                                                       |
|-------------|---------------------------------------------------------------------------|
| Health      | `ping`, `stats`, `stop`                                                   |
| Write       | `enqueue`, `flush_queue`, `flush_queue_async`, `sync_files`, `sync_since` |
| Mutate      | `upsert_entity`, `add_concept`, `add_linkage_type`                        |
| Read        | `iter_entities`, `list_linkages`, `list_saved_queries`                    |
| Query       | `query`, `context`, `grep_indexed`                                        |
| Learn       | `learn_from_grep`                                                         |
| Maintain    | `prune_noise`, `vacuum`, `checkpoint`                                     |

`flush_queue_async` exists so the Claude Code `Stop` hook doesn't block agent
shutdown on a slow ingest pass — it returns immediately and the daemon drains
the queue on a background thread.

## CLI / hook surface

The CLI is Click-based with subgroups:

```
rmx
├── init / info
├── daemon         start / stop / status
├── partition      list / add
├── canon          link / siblings
├── add            entity / concept / linkage-type
├── list           entities / linkages / queries
├── link / unlink
├── query / explain
├── neighbors / context / co-occur / top
├── grep                                         (index-backed + rg fallback)
├── save-query / run
├── ingest / tldr-warm / ingest-gmd
├── sync           --files / --since / --flush-queue / --enqueue-only
├── queue
├── watch
├── primer / scan-prompt
├── install-hooks
├── stats / telemetry
├── compact / checkpoint / vacuum / prune-noise
├── export / import / dump-log / rebuild
└── migrate-to-duckdb
```

Hyphenated aliases (`add-entity`, `list-linkages`, etc.) are hidden but
preserved for backwards compatibility with older scripts and hooks.

## How tldr fits in

`llm-tldr` produces `.tldr/cache/`. refmatrix:

- **Reads** `metadata.json` and `call_graph.json` (`ingest.py:40-48`).
- **Shells out** to `tldr warm` from `rmx tldr-warm` (`cli.py:1425`).
- **Augments** with 5 ingest passes tldr does not perform (Python AST, ADR,
  markdown semantics, plan-doc `specifies`, GMD).
- **Stages** tldr's per-unit semantic dump into the entity `meta` JSON blob
  (`store.py:72`) so all of tldr's signature / docstring / code-preview /
  CFG/DFG summary survives the indexing pass and is queryable.
- **Re-runs** tldr-aware ingest on `.py` change if `call_graph.json` exists
  (`sync.py:171-178`). Other-language changes trigger only the tree walk.

The relationship is composition: tldr is the per-function extractor, rmx is
the cross-entity index + query engine + agent surface. Either tool is useful
alone; together they cover the *what does this do?* → *what set satisfies
this combination of relations?* spectrum.
