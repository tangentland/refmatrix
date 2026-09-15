---
gmd: "0.1"
id: ARCHITECTURE
title: "refmatrix — Architecture"
tags: [architecture, modules, storage, daemon]
---

# refmatrix — Architecture {#root}

rel: related-to -> [[SYSTEM]]
rel: related-to -> [[INTEGRATION]]
rel: related-to -> [[PERFORMANCE]]

## Layered view {#layered-view}

```
┌──────────────────────────────────────────────────────────────────────┐
│                     CLI / Hook Surface                               │
│   cli.py · hooks.py                                                  │
└───────────────────────────────┬──────────────────────────────────────┘
                                │
┌───────────────────────────────┴──────────────────────────────────────┐
│                    Daemon / Concurrency Layer                        │
│   daemon.py  (per-store Unix socket, owns the writer lock, serves    │
│              snapshot-tier reads, hosts embedder + watcher, ~40 ops)  │
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
│  store.py    DuckDB catalog + roaring bitmap fragments (BLOB)        │
│              + memory_content sidecar + Lance dense vectors          │
│  backend.py  SQLite vs DuckDB backend selection (new stores: DuckDB) │
│  duckdb_catalog.py   native DuckDB schema (phase 3, current default) │
│  duckdb_view.py      read-only DuckDB facade over SQLite (phase 1)   │
│  migrate.py          one-shot SQLite → DuckDB migration              │
└──────────────────────────────────────────────────────────────────────┘
```

## Module inventory {#module-inventory}

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

## Dependency flow {#dependency-flow}

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

## Core data layer {#core-data-layer}

### Catalog schema (DuckDB, native — `duckdb_catalog.py:CATALOG_DDL`) {#catalog-schema-duckdb-native-duckdb-catalog-py-catalog-ddl}

| Table                | Key columns                                              | Purpose                              |
|----------------------|----------------------------------------------------------|--------------------------------------|
| `entities`           | id, kind, name, path, tldr, meta, canonical_name, protected, noise | One row per doc/code/concept/memory/query (`kind ∈ {doc,code,concept,memory}`) |
| `concepts`           | id (entity_id), description                              | Concept-kinded entity sidecar        |
| `memory_content`     | entity_id, content, mtype, tags, metadata, timestamps   | Memory body sidecar (logged → replayable) |
| `linkage_types`      | id, name, directed, description, inverse                 | Open-set verb registry               |
| `entity_links`       | linkage_id, concept_id, entity_id, weight                | SQL-shadow of bitmap content (FK)    |
| `linkage_evidence`   | linkage_id, concept_id, entity_id, file, line, detail    | file:line provenance per linkage     |
| `tracked_files`      | path, mtime, last_synced                                 | Incremental skip on unchanged files  |
| `bitmap_fragments`   | partition_id, linkage_name, blob (BLOB), updated_at      | DuckDB-only bitmap persistence       |
| `partitions`         | id, name, description                                    | Multi-codebase shared catalog        |
| `canon_links`        | local_concept_id, canonical_concept_id                   | Cross-partition concept canonicalization |
| `saved_queries`      | name, expression, created_at                             | `rmx save-query` / `rmx run`         |

### Bitmap fragment storage (`store.py`) {#bitmap-fragment-storage-store-py}

| Concern               | Implementation                                                              |
|-----------------------|-----------------------------------------------------------------------------|
| In-memory shape       | `BitMap64` per `(partition, linkage_type)`                                  |
| Packing               | `(concept_id << 32) | entity_id`                                            |
| Disk layout (SQLite)  | `.refmatrix/fragments/<partition>/<linkage>.rb64`                           |
| Disk layout (DuckDB)  | `bitmap_fragments` BLOB column, UPSERTed per linkage                        |
| Read                  | `load_bitmap(linkage, concept) → BitMap32` via range mask on the packed key |
| Write                 | Lazy fragment load + dirty-set flush at transaction boundary                |
| Atomic persistence    | DuckDB: single transaction; SQLite: write-rename per fragment file          |

### Backend selection (`backend.py`) {#backend-selection-backend-py}

The catalog has gone through three phases:

1. **Phase 1 (SQLite + DuckDB view)** — SQLite owns writes, `duckdb_view.py`
   gives read-only DuckDB query access for analytics.
2. **Phase 2 (DuckDB catalog + SQLite fragments)** — DuckDB owns catalog
   tables, bitmap fragments still on disk.
3. **Phase 3 (DuckDB native)** — all catalog + bitmaps in one DuckDB file.
   `migrate.py` performs the one-shot conversion. New stores default to DuckDB.

`backend.py:select_backend()` detects which phase a given `.refmatrix/`
directory is in and dispatches accordingly.

## Ingest pipeline {#ingest-pipeline}

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

### Verb policy {#verb-policy}

| Verb            | Source                                  | Inverse        |
|-----------------|-----------------------------------------|----------------|
| `defines`       | code-implements-concept, doc-defines    | `defined_by`   |
| `specifies`     | plan/spec/issue declares intent         | `specified_by` |
| `calls`         | call graph                              | `called_by`    |
| `imports`       | AST imports, GMD frontmatter            | `imported_by`  |
| `mentions`      | docstring keywords, `[[wikilinks]]`     | `mentioned_by` |
| `is_a`          | subclass hierarchies (ADR/markdown)     | (none)         |
| `related_to`    | ADR-NNNN cross-references               | (symmetric)    |
| `part-of`       | GMD heading hierarchy                   | `has-part`     |
| (any kebab)     | author-declared GMD `rel:` line         | (none unless registered) |

## Query layer {#query-layer}

### DSL (infix set algebra) — `query.py:QueryEngine` {#dsl-infix-set-algebra-query-py-queryengine}

```
rmx query "defines:parser AND NOT mentions:parser"
rmx query "calls:foo OR (mentions:bar AND NOT imports:legacy)"
rmx query "parser"                          # bare term: union across all linkages
```

Operators: `AND` / `&&`, `OR` / `||`, `NOT` / `!`, parentheses. A term is
`linkage:concept` (or just `concept`). Compiles to BitMap32 union / intersect /
difference over the loaded fragments.

### PQL (Pilosa-style) — power-user form {#pql-pilosa-style-power-user-form}

For when the infix form gets clumsy:

```
Intersect(Row(defines='parser'), Difference(Row(any='parser'), Row(mentions='parser')))
```

### Context bundling — `context.py` {#context-bundling-context-py}

`rmx context Foo --max-tokens 2000` returns a token-budgeted bundle of
entities related to `Foo`, walking linkages and **fusing rankings via
Reciprocal Rank Fusion** (`fuse_rrf`, k=60) so multi-linkage signals combine
without per-linkage hyperparameters. The walk knows about `linkage_evidence`,
so the rendered bundle carries `file:line` markers back to where each linkage
was extracted.

### Scoring stack (when ranking, not pure set ops) — `eval/retrievers/rmx_retriever.py` {#scoring-stack}

rel: evidence-for -> [[PERFORMANCE#benchmark-results]]

```
score = BM25(query, entity)
      × coverage(query, entity) ** α      # what fraction of query terms hit
      × Σ_linkage  w_linkage × hits        # weighted by linkage type
      × co_mention(query, entity) ** β     # linkage-coupled, not raw
```

Tuned production variant: `bm25_docstring30_cov30_cm20` — BM25 + docstring
linkage weight 0.30 + coverage^3 + linkage-coupled co-mention^2.

The symbolic stack beats dense `CodeRankEmbed` on CodeSearchNet — the edge is
biggest in **top-rank recall** (no embeddings, no GPU, no reranker):

| Dataset | Recall@1 (rmx / CE) | Recall@10 (rmx / CE) | MRR@10 (rmx / CE) |
|---------|:-------------------:|:--------------------:|:-----------------:|
| CSN Python      | **0.971** / 0.934 | **0.997** / 0.993 | **0.982** / 0.959 |
| CSN JavaScript  | **0.920** / 0.895 | **0.970** / 0.951 | **0.939** / 0.916 |
| CSN TypeScript  | **0.244** / 0.241 | **0.660** / 0.644 | **0.365** / 0.358 |

(TS absolutes are low — real-world corpus with fork/copy dupes — but rmx still
leads at every cutoff. JS margin is *larger* than Python: rmx's linkage-aware
scorer benefits from JS's denser cross-file relations.) Full methodology +
tuning ablation in [[PERFORMANCE#benchmark-results]].

## Daemon / concurrency layer {#daemon-concurrency-layer}

The catalog's storage engine (DuckDB or SQLite) holds a writer lock that
blocks concurrent processes. With editor + watcher + CLI all wanting to
touch the catalog, lock contention used to corrupt indexes. The daemon
solves this by being the sole owner.

### Lifecycle {#lifecycle}

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

### Read path — snapshot-tier (writer rotation retired in 0.7.7) {#read-path-snapshot-tier-writer-rotation-retired-in-0-7-7}

Reads never touch the write-locked catalog. After each write op the daemon
regenerates `catalog.read.duckdb` — a full lock-free copy of the writer's
catalog — and points `read_only.duckdb` at it. Every read-only CLI command and
the in-process replica reader open that snapshot, so a `query` never blocks on
an ingest.

The writer stays **pinned** to its catalog slot (`catalog.A.duckdb` or
`catalog.B.duckdb`, named by the `active` marker) for the daemon's life. The old
A/B writer *rotation* — which caught up the inactive slot by `facts.log`
delta-replay then swapped the writer onto it — was **dropped**: any state not
fully captured by the log (e.g. the `memory_content` body sidecar, or an off-log
direct write made while the daemon was down) was absent from the promoted slot,
and the snapshot rebuilt from it silently lost that data. `memory_content` is now
logged too (so `rmx rebuild --from-log` reconstructs bodies), and the swap is a
no-op; A/B persist only as the writer's slot. Invariant: **no swap can ever
promote a slot missing committed data.**

### OPS dispatch (`daemon.py:OPS`) {#ops-dispatch-daemon-py-ops}

| Category    | Ops                                                                       |
|-------------|---------------------------------------------------------------------------|
| Health      | `ping`, `stats`, `stop`                                                   |
| Write/sync  | `enqueue`, `flush_queue`, `flush_queue_async`, `sync_files`, `sync_since`, `ingest_path`, `ingest_gmd` |
| Mutate      | `upsert_entity`, `add_concept`, `add_linkage_type`                        |
| Query/read  | `query`, `context`, `grep_indexed`, `iter_entities`, `list_linkages`, `list_saved_queries` |
| Memory      | `memory_add`, `memory_get`, `memory_iter`, `memory_search`, `memory_recall`/`ann_search`, `memory_forget`, `memory_bulk_forget`, `memory_dedup`, `memory_link`, `memory_score` |
| Dense       | `embed`, `embed_gc`                                                       |
| Partition   | `partition_add`, `partition_list`, `partition_rename`, `replica_status`, `replica_refresh` (no-op) |
| Maintain    | `prune_noise`, `vacuum`, `checkpoint`, `rebuild_index`                    |

`flush_queue_async` exists so the Claude Code `Stop` hook doesn't block agent
shutdown on a slow ingest pass — it returns immediately and the daemon drains
the queue on a background thread. Latency-sensitive ops run on a small `cli_pool`;
mutating/bulk ops run on `bg_pool`.

## CLI / hook surface {#cli-hook-surface}

The CLI is Click-based with subgroups:

<!-- cli-tree:start -->
Generated by `scripts/gen-cli-tree.py` from `refmatrix.cli.main` (199 visible commands); `tests/test_docs_generated.py` fails when this drifts from the code.

```
rmx
├── add                            Add concepts, entities, and linkage types.
│   ├── concept                    Add a concept (= entity of kind 'concept'). Pinned by default.
│   ├── entity                     Insert or update an entity. Manual adds are protected by defaul…
│   └── linkage-type               Define a custom linkage type.
├── audit-same-as                  Health check on `same_as` identifier variant-unification.
├── bus                            Agent message bus (hub-hosted). Intra-project (proj:<name>:<top…
│   ├── archive                    Move messages to the archive (still readable via `history --sta…
│   ├── channels                   List channels with message counts.
│   ├── delete                     Soft-delete a message by id (hidden from history/read, recovera…
│   ├── history                    Show the last N messages on a channel.
│   ├── mark-read                  Mark a channel read up to a point (default: everything).
│   ├── pub                        Publish a message to a channel.
│   ├── purge                      Hard-remove messages — the only destructive path. Default reaps…
│   ├── read                       Show messages you haven't read yet across matching channels, ad…
│   ├── stats                      Per-status totals + per-channel breakdown (+ unread counts).
│   ├── sub                        Subscribe and stream messages (Ctrl-C to stop). Patterns: exact,
│   └── unarchive                  Restore an archived message to active.
├── canon                          Wire concepts across partitions through a canonical hub.
│   ├── find                       Find which projects host CONCEPT (cross-project canon view).
│   ├── link                       Wire the active partition's CONCEPT to a canonical concept.
│   └── siblings                   List concepts in other partitions that share a canon hub with C…
├── cctree                         Prompt -> action tree for Claude Code sessions.
├── checkpoint                     DuckDB CHECKPOINT: flush WAL and compact the catalog file. Run…
├── cli-log                        Inspect the rmx CLI invocation log (.refmatrix/cli.log).
├── co-occur                       Concepts that share entities with the given concept under a lin…
├── compact                        Compact the writer-slot catalog via EXPORT/IMPORT round-trip.
├── compact-log                    Compact .refmatrix/facts.log, reclaiming its unbounded growth.
├── concept                        Concept-scoped cross-index queries.
│   └── timeline                   When was CONCEPT introduced / worked on, directly or indirectly.
├── context                        Token-budgeted context bundle: anchor + neighbors + their tldr…
├── coref                          Pronoun dereferencing (coref.py). Within-doc resolution runs at
│   └── link                       Cross-document resolution: bind each document's doc-INITIAL
├── curator                        gmd-curator coordination — watcher-populated queue + dispatch
│   ├── drain                      Empty the curator queue without printing anything.
│   ├── scan                       Lint queued GMD docs → file curation candidates into the refine…
│   └── status                     Summarize the curator queue for hook injection.
├── daemon                         Per-store background process that holds the catalog open and
│   ├── job                        Status of a daemon background job (e.g. `partition merge --asyn…
│   ├── launchctl                  Generate + manage a macOS launchd LaunchAgent for the active st…
│   │   ├── install                Install + bootstrap the LaunchAgent plist for the active store.
│   │   ├── kickstart              Ensure the supervised daemon for the active store is running.
│   │   ├── print                  Render the plist to stdout without installing. Useful for review
│   │   ├── status                 Show plist path, label, and whether it is installed + loaded.
│   │   └── uninstall              Bootout the LaunchAgent and remove its plist file.
│   ├── restart                    Restart the daemon for the active store.
│   ├── start                      Start the rmx daemon for the active store. Idempotent: re-runni…
│   ├── status                     Report whether the daemon is running for the active store, plus…
│   └── stop                       Stop the daemon for the active store, if any. Idempotent.
├── describe                       Dump EVERY stored fact about one entity — the whole row plus the
├── dump-log                       Snapshot the catalog into .refmatrix/facts.log (overwrites exis…
├── embed                          Embed entities into Lance for dense ANN retrieval.
├── export                         Export the entire matrix as a single JSON file (entities, linka…
├── focus                          Short-term (working) memory — a per-project, isolated focus gra…
│   ├── change-subject             Set the active SUBJECT — a named STM partition + durable LTM co…
│   ├── clear                      Clear short-term memory + task stack for this session.
│   ├── clear-subject              Unset the active subject (revert to the bare session ring). The…
│   ├── composite                  Emit a GMD topic-composite subgraph of the current STM focus.
│   ├── context                    Show the current focus mini-graph (recency-weighted).
│   ├── detour                     Soft branch detour — bookmark the current focus before chasing a
│   ├── detours                    List open soft-detour return-points (most recent first).
│   ├── export                     Dump the FULL session focus log — every event, untrimmed. The r…
│   ├── hook                       Record a short-term event from a Claude Code hook envelope on s…
│   ├── note                       Record a deliberate reasoning note into STM — the WHY behind a…
│   ├── promote-edges              Promote recurring STM co-occurrence into durable `co-occurs` ed…
│   ├── rebuild                    Recompute focus graph(s) from the event ring, purging machine n…
│   ├── record                     Append an event to short-term memory (used by hooks).
│   ├── return                     Return from a soft detour — rewind focus to the bookmark. Defau…
│   ├── show                       Show the full event(s) at a log line (the L<n> refs in `focus c…
│   ├── size                       Show the STM ring size + current event count.
│   ├── subject                    Show the active subject for this session (or none).
│   ├── subjects                   List durable subjects in this project (newest-active first) wit…
│   ├── summarize                  Condense the session's STM (topics + milestones + intent arc) i…
│   ├── tail                       Show recent short-term events (defaults to the active session).
│   └── topics                     Cluster the session into topics — its distinct threads of work…
├── forget                         Delete entities — row, bitmap memberships, linkage evidence, an…
├── graphify-warm                  Run `graphify <path>`, then ingest the resulting graph.json int…
├── grep                           Index-backed grep: find concepts whose name matches PATTERN and
├── hub                            User-level control plane: supervises every per-project daemon
│   ├── launchctl                  Supervise the hub itself via macOS launchd (com.refmatrix.hub).
│   │   ├── install                Install + load the hub LaunchAgent.
│   │   ├── status                 Show hub LaunchAgent status.
│   │   └── uninstall              Unload + remove the hub LaunchAgent.
│   ├── pause                      Maintenance pause: the hub watchdog observes TARGET's daemon bu…
│   ├── queues                     Change-queue visibility: pending sync/stale work per project +…
│   ├── relaunch-fleet             Relaunch EVERY launchd-supervised store's daemon on the install…
│   ├── resume                     Lift a maintenance pause set by `rmx hub pause`.
│   ├── start                      Start the hub (idempotent).
│   ├── status                     Show hub + supervised-store health.
│   └── stop                       Stop the hub.
├── import                         Import a JSON dump produced by `rmx export`.
├── info                           Print the active refmatrix version, root, and partition.
├── ingest                         Ingest a directory. Prefers .tldr/cache/semantic/metadata.json…
├── ingest-gmd                     Ingest Graph Markdown (GMD) docs. Walks dirs for *.gmd/*.md fil…
├── ingest-status                  Inspect ingest job state. With no JOB_ID, lists all known jobs.
├── init                           Initialize a refmatrix in the given directory (default: cwd).
├── install-hooks                  Install, preview, or verify the hooks that keep refmatrix in sy…
├── link                           Set bit (linkage, concept, entity). Pins both endpoints by defa…
├── list                           List entities, linkages, saved queries.
│   ├── entities                   List entities. --protected / --noise filter by flag and show th…
│   ├── linkages                   List linkage types.
│   └── queries                    List saved queries.
├── locate                         Locate full filesystem paths by FILENAME and/or keywords/concep…
├── log                            List or tail refmatrix's logs under .refmatrix/.
├── mcp                            Run the refmatrix MCP server over stdio. Configure in Claude Co…
├── memory                         Intuition memory layer (ADR-0001). add / get / search / recall /
│   ├── add                        Add or update a memory entity.
│   ├── bulk-forget                Bulk-delete memories by id / name / mtype.
│   ├── compile                    Group memories into subjects and link crosscutting concepts.
│   ├── dedup                      Fold concept↔memory duplicate nodes into the memory (pre-0.7.6…
│   ├── forget                     Drop a memory: its entity row, sidecar, and every entity_link.
│   ├── get                        Fetch a memory by name (current partition) or id (any partition…
│   ├── link                       Link a memory to a concept. Auto-creates the concept if new.
│   ├── list                       List memories in the active partition.
│   ├── promote                    Copy a project memory into the shared global behavior store. Bo…
│   ├── recall                     Memory retrieval. Three modes:
│   ├── reclassify                 Bulk-change the mtype of memories (selector: --like / --from /…
│   ├── retag                      Add/remove/replace a memory's tags.
│   ├── score                      Phase B5: signed reinforcement score for a concept.
│   └── search                     Case-insensitive substring search over memory name + content.
├── merge-verb-aliases             Fold legacy snake_case linkage verbs into their kebab canonical.
├── migrate-to-duckdb              One-shot copy of the SQLite catalog into a native DuckDB catalo…
├── neighbors                      Walk linkages from a concept (depth-N closure).
├── noise                          Flag entities as noise (hidden from default queries; reaped by
├── pagerank                       Recompute the global PageRank prior over the concept⇄entity gra…
├── pairs                          Central df-filtered skip-pair inventory with document postings.
│   ├── compile                    Scan the partition's memories + docs and (re)build the inventor…
│   └── show                       Documents containing PAIR_KEY (alphabetized `a_b` form).
├── partition                      Inspect and manage named partitions inside the active refmatrix.
│   ├── add                        Register a partition explicitly. (Writes auto-create a partitio…
│   ├── list                       List all partitions in the active refmatrix, marking the active…
│   ├── merge                      Merge SRC partition into DST. Drops SRC on success.
│   └── rename                     Rename partition OLD to NEW.
├── primer                         Density-ranked map of the top-N reference-dense symbols. CLAUDE…
├── projects                       List all refmatrix projects on this machine: name, store root,
├── protect                        Pin entities (protected=1) so prune-noise / vacuum never reap t…
├── prune-noise                    Mark (or with --drop, delete) noisy auto-generated concepts.
├── query                          Run a query. DSL: `mentions:parser AND defines:parser`. PQL: `R…
├── queue                          Show or manage the dirty (change) queue.
│   └── clear                      Empty the dirty queue.
├── rebuild                        Rebuild derived state. Currently only --from-log is supported.
├── recall                         Hybrid retrieval: bitmap-prefiltered Lance ANN + RRF fusion
├── recall-state                   Pull the prior session's handoff and orient — the mirror of sav…
├── refine                         Review promotion candidates queued from the bus + the GMD curat…
│   ├── accept                     Promote candidates into memories. Writes are daemon-routed.
│   ├── list                       List promotion candidates, oldest first.
│   ├── reject                     Drop candidates without writing a memory.
│   └── show                       Show one candidate in full, including the body that would be wr…
├── reingest                       Run every ingest pass over all sources in canonical order, then…
├── repair-index                   Drop + recreate idx_entity_links_lk_concept to fix DuckDB secon…
├── replica                        Read-replica (snapshot-tier) management.
│   ├── audit                      Detect drift between rotation slots: per-table row diffs + enti…
│   ├── merge                      Drift recovery: merge rotation slots A and B into one canonical
│   ├── path                       Print the absolute path of the *reader* slot file. CLI tools th…
│   ├── refresh                    Force an immediate catch-up + slot swap. Returns size + latency.
│   └── status                     Show rotation state: writer + reader slots, file sizes, freshne…
├── run                            Run a saved query by name.
├── save-query                     Persist a named query.
├── save-state                     Compile + persist a session handoff — the resume point for the…
├── scan-prompt                    Read a prompt; emit context bundles for symbols it mentions.
├── schedule                       Per-project scheduled maintenance, run by the hub (sync/embed/v…
│   ├── add                        Schedule OP for the current project every <interval>.
│   ├── list                       Show all scheduled jobs across projects.
│   └── remove                     Remove a scheduled OP for the current project.
├── search-dense                   Dense ANN search via Lance. Embeds QUERY with the same model
├── session                        Past Claude Code session index. ingest / (recall, show, list —…
│   ├── ingest                     Parse Claude Code session JSONLs into GMD cards + index them.
│   ├── launchctl                  macOS launchd integration for the session-index backfill ticker.
│   │   ├── install                Install + bootstrap the session-indexer LaunchAgent.
│   │   ├── status                 Report whether the session-indexer agent is installed + loaded.
│   │   └── uninstall              Bootout + remove the session-indexer LaunchAgent.
│   ├── list                       Paginated index of sessions, sorted by ended DESC.
│   ├── recall                     BM25-style search over session cards with metadata filters.
│   ├── show                       Load a session by id (full uuid or 8-char prefix).
│   └── stats                      Aggregate stats: session count, turns, tool usage, top files.
├── stats                          Print catalog and bitmap stats.
├── sync                           Incrementally update the matrix for given files / git changes /…
├── task                           Pushdown task stack — track interrupted work when tangents get
│   ├── current                    Show the current (top) task.
│   ├── list                       Show the stash stack with 1-based indices (top = 1 = most recen…
│   ├── pop                        Pop a stash and restore ITS focus (git-stash semantics). Defaul…
│   ├── push                       Push a task (snapshots current focus).
│   └── swap                       Swap the top two tasks.
├── taxonomy                       Shared memory-tag vocabulary (~/.refmatrix/taxonomy.json). Vali…
│   ├── add                        Add (or update) a tag under a category.
│   ├── list                       Show the tag vocabulary grouped by category.
│   └── remove                     Remove a tag from the vocabulary.
├── telemetry                      Summarize the query telemetry log.
├── tldr-warm                      Run `tldr warm <path>`, then ingest the resulting call graph in…
├── tools-primer                   Produce an agent-consumable primer describing the rmx CLI surfa…
├── top                            Top-K entities by weight under (linkage, concept).
├── ui                             Open the web UI (starts the hub if needed).
├── unlink                         Clear bit (linkage, concept, entity).
├── unnoise                        Clear the noise flag.
├── unprotect                      Clear protected so an entity can be pruned or forgotten.
├── untrack                        Stop tracking files matching a path glob, purging their entitie…
├── upgrade                        Self-update this install: fast-forward its git tree, `pip insta…
├── vacuum                         Drop empty concepts and tracked files that no longer exist.
├── version                        Print the installed version; with -v, the runtime identity.
└── watch                          Watch a directory and sync on debounced batches of changes. Ctr…
```

6 hidden hyphenated aliases (`add-concept`, `add-entity`, `add-linkage-type`, `list-entities`, `list-linkages`, `list-queries`) are preserved for older scripts and hooks but are not part of the documented surface.
<!-- cli-tree:end -->


## How tldr fits in {#how-tldr-fits-in}

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
