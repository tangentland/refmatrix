---
gmd: "0.1"
id: refmatrix/refmatrix_system_design_interview
title: "refmatrix — The System Design Interview (model answer)"
tags: [system-design, interview, refmatrix, retrieval, agent-memory, architecture]
metadata:
  node_type: design-review
  subject_version: "0.84.0 (master 338c6dfb, 2026-11-19)"
  created: 2026-11-23
---

# refmatrix — The System Design Interview {#root}

A complete staff-level system design interview, worked end to end, with refmatrix (`rmx`) as
the system under design. **I** is the interviewer and **C** the candidate. The candidate's
answers are a model answer: they reach the design refmatrix actually ships (v0.84.0, master
`338c6dfb`), they cite the numbers measured on the live fleet, and they defend each decision
with the incident or measurement that forced it.

Use it three ways: as a rehearsal script (cover **C** and answer aloud), as an onboarding
tour of the codebase (each section names the module and `file:line` that implements it), or as
a grading key (the rubric in [[#rubric]]).

rel: derives-from -> [[refmatrix/SYSTEM]]
rel: derives-from -> [[refmatrix/ARCHITECTURE]]
rel: derives-from -> [[refmatrix/PERFORMANCE]]
rel: supersedes -> [[refmatrix/system_design_review]] {note: "the in-repo v0.60 interview still describes A/B replica rotation, retired since"}

## Interview timeline {#timeline}

| Minute | Phase | What a strong candidate produces |
|---|---|---|
| 0–5 | Problem + clarifying questions | Splits the prompt into three problems; names the consumer (an agent with a token budget) |
| 5–10 | Requirements + estimates | Hard latency/size budgets for the hook path; single-node scale envelope |
| 10–15 | API | One typed verb per capability, three transports (CLI, MCP, daemon socket) |
| 15–22 | Data model | Pilosa-shaped matrix: entities × concepts × linkage types as roaring bitmaps |
| 22–30 | High-level architecture | Per-store daemon owning the single writer; user-level hub above it |
| 30–45 | Deep dives | Write path, read path, ranking, memory tiers |
| 45–52 | Failure modes + scaling | The incident list; what breaks at 10× and 100× |
| 52–60 | Trade-offs + evolution | Alternatives rejected with data; the ADR-0004 roadmap |

## 1. The prompt {#prompt}

**I:** Design a code-and-memory retrieval system for AI coding agents. One developer runs
several Claude Code sessions at once, across about ten repositories, for months. The agent
loses its context window at every session boundary. It should find code by name and by
meaning, stop re-deriving what it already learned, and get the right context injected before
it starts working on a prompt.

## 2. Clarifying questions {#clarify}

**C:** Before drawing anything I want to pin down six things.

| # | Candidate asks | Interviewer answers | Why it matters |
|---|---|---|---|
| 1 | Who consumes the results, a human or the model? | Mostly the model, through hooks and tool calls | The product is "the best ~2 kB for this prompt", not a results page. Every read surface needs a hard byte budget. |
| 2 | Is there a server, or does this run on the laptop? | Laptop. macOS. No cloud dependency. | Embedded storage, a process supervisor (launchd), memory pressure (jetsam) becomes a design input. |
| 3 | How fresh must the index be after an edit? | The next prompt should see the edit | Incremental sync on every tool write, not a nightly rebuild. |
| 4 | Must answers be explainable? | The agent must be able to verify a hit | Every result traces to `file:line`. That rules out a pure embedding index as the spine. |
| 5 | Is memory per project or global? | Both: project knowledge, plus cross-project behaviour rules | Two store scopes: one store per repo, one global memory-only store. |
| 6 | Do the concurrent sessions need to talk to each other? | Yes, coordination would help | A message bus, hosted above the per-project stores. |

**C:** So the one sentence hides three problems:

1. **Code and document retrieval.** "Where is X, what calls it, what documents it, what plan
   specified it and was never built." It has to beat grep on precision and an embedding index
   on explainability, and it has to be cheap enough to run on every prompt. {#p-retrieval}
2. **Durable memory.** Decisions, feedback and incidents that outlive a session, with typed
   relationships (`supersedes`, `amends`, `depends-on`), not a flat pile of notes. {#p-ltm}
3. **Working memory.** What is happening right now, captured passively from the agent
   harness and promoted to durable memory at the session boundary. {#p-stm}

## 3. Requirements {#requirements}

### Functional {#functional}

- **F1 — Symbolic graph.** Entities (files, functions, doc sections, concepts, memories) joined
  by typed, weighted linkages: `defines`, `calls`, `mentions`, `imports`, `is_a`, `specifies`,
  plus any verb an author declares.
- **F2 — Set algebra.** Questions grep cannot answer at any speed, such as
  `defines:auth AND NOT mentions:auth` (implemented, documented nowhere) and
  `specifies:Zone AND NOT defines:Zone` (planned, never built).
- **F3 — Ranked retrieval.** Natural-language and symbol queries ranked with evidence;
  dense vectors as a complement, never the spine.
- **F4 — Proactive context.** A `UserPromptSubmit` hook injects bundles for whatever the prompt
  mentions, inside the hook's output cap.
- **F5 — Memory.** Curated memories (authored as files on disk), session transcripts, and a
  working-memory focus graph, each with its own recall surface.
- **F6 — Fleet.** N project stores plus one global store on one machine, supervised, with a
  message bus between live agents.

### Non-functional {#non-functional}

- **NF1 — Reads never block on writes.** A prompt hook that stalls behind an ingest is a
  product failure. The project paid this lesson twice before it became a rule.
- **NF2 — Always-on surfaces finish in about a second**; big operations (ingest, embed, merge)
  are non-blocking and observable.
- **NF3 — Embeddable.** No server dependency a laptop can't run. Crash-and-restart under
  launchd is the recovery model.
- **NF4 — Fail loud on memory paths.** Between a memory file and the store, no
  `2>/dev/null`, no `|| true`, no uncounted `continue`. A skipped file is counted and printed.
- **NF5 — Honest evaluation.** Benchmark the code path users actually run.

### Explicit non-goals {#non-goals}

Horizontal scale-out, multi-tenant serving, an HTTP API for third parties, and executing
project code (all extraction is static: AST, regex, fenced-block parsing).

## 4. Back-of-the-envelope {#estimates}

**C:** I'll estimate, then check against what the live fleet reports.

| Quantity | Estimate | Measured on the fleet (2026-11-23) |
|---|---|---|
| Stores per machine | ~10 | 8 (7 projects + `global`), all launchd-supervised |
| Entities in a mid-size repo store | 10⁵ | refmatrix store: 129,297 concepts · 6,994 code · 2,169 doc · 583 memory |
| Catalog size | 0.1–1 GB | refmatrix writer slot 1.3 GB; dense vectors 428 MB |
| Daemon RSS | < 500 MB | 172–733 MB per daemon, models out of process |
| Hook output cap | "a few kB" | **10,000 UTF-16 code units** of trimmed stdout per hook command (measured on Claude Code 2.1.322) |
| Per-prompt hook budget | < 5 s worst case | `scan-prompt --timeout 5`, `memory recall --timeout 5`, Stop hook bounded at 8 s |
| Bitmap key space | 2³² × 2³² | `BitMap64` key = `(concept_id << 32) | entity_id` per partition |

**C:** Three consequences fall out of these numbers:

- The hook cap of 10,000 UTF-16 units is roughly 2,500 tokens. Every producer on a hook needs a
  shared byte budget, or the model sees a 2 kB preview of the first producer and nothing else.
  That happened: the recall hook printed 15–59 kB of JSON and arrived truncated on 95% of
  prompts (bug-164). {#est-hook}
- At 10⁵–10⁶ entities, set algebra over roaring bitmaps costs microseconds. The bottleneck will
  be ranking, I/O and lock contention, not the algebra. {#est-bitmap}
- One writer per store is affordable. Ten stores of single writers is just ten processes, but
  ten copies of a 600 MB embedding model is 6 GB, so the models must be shared. {#est-models}

## 5. API {#api}

**C:** Agents reach the system three ways: shell commands fired by hooks, MCP tool calls, and
interactive CLI use. In this project's history, a hand-built CLI payload and a separate
hand-built MCP payload for the same operation drifted apart. There was a dead `rmx_query` MCP
tool (`{"dsl"}` sent where `args["expr"]` was read), an MCP ingest with no semantic pass, and a
partition split-brain. So I make drift structural rather than a matter of discipline:

```
@verb("query", "...")                 # src/refmatrix/verbs.py:191
def query(root, *, expr, partition=None, limit=50, explain=False) -> dict: ...
     │
     ├── CLI:  click command; CI gate asserts its defaults == the verb's defaults
     ├── MCP:  tool JSON schema GENERATED from the signature (Verb.schema)
     └── daemon op payload built in exactly one place: the verb body
```

**C:** The core surface:

| Verb / command | Purpose | Called by |
|---|---|---|
| `query EXPR` | DSL (`AND/OR/NOT`) or PQL (`Intersect(Row(..))`) → bitmap result | agent, CI |
| `context NAME` | Token-budgeted bundle: body + graph neighbourhood + KWIC + `file:line` | agent, scan-prompt |
| `scan-prompt` | Prompt → matched concepts → ranked bundles under the hook budget | `UserPromptSubmit` |
| `memory recall Q` | Dense (default) or hybrid recall over curated memories, packed pointer-first | `UserPromptSubmit`, `SessionStart` |
| `grep PAT` | Byte-exact grep drop-in; index-first, teaches the graph on every search | PreToolUse rewrite |
| `ingest` / `sync` / `reingest` | Full, incremental and canonical-order rebuilds | git hooks, PostToolUse, scheduler |
| `ingest-gmd --as-memory DIR` | The memory bridge: curated `.md` files → `kind=memory` rows | SessionStart, save-state |
| `save-state` / `recall-state` | Compile a session handoff memory; resume from it | session boundary, PreCompact |
| `focus hook` | Record a working-memory event from a harness envelope | every hook event |

**Daemon wire protocol.** Newline-delimited JSON over `<root>/.refmatrix/rmxd.sock`:
`{"op": "...", "args": {...}}` → `{"ok": true, "result": ...}` or
`{"ok": false, "error": "..."}`. A Unix socket rather than HTTP: no port allocation across ten
stores, filesystem permissions are the auth model, and connect costs about 1 ms. {#wire}

## 6. Data model {#data-model}

### The matrix {#matrix}

**C:** The core query shape is set algebra over sparse membership, so I model it the way
Pilosa does: index → field → row → column.

| Pilosa | refmatrix | Example |
|---|---|---|
| Index | the store (`.refmatrix/`) | one per repo |
| Field | linkage type | `defines`, `calls`, `mentions`, `specifies`, `amends` |
| Row | concept id | `parser`, `import/json`, `keyword/tokenizer` |
| Column | entity id | `src/parser.py`, `parse_args`, `ARCHITECTURE#read-path` |

**C:** One fragment per `(partition, linkage)`: a single `BitMap64` whose bit positions are
`(concept_id << 32) | entity_id`. Reading a row, meaning "every entity that `defines` concept
42", is a range-mask intersection over `[42 << 32, 43 << 32)`. `AND`, `OR` and `NOT` are native
roaring operations. Concepts are entities too, so concepts can link to concepts. {#packing}

### The catalog {#catalog}

**C:** The ids, names, metadata and provenance live in one embedded DuckDB file
(`duckdb_catalog.py:CATALOG_DDL`):

| Table | Key columns | Role |
|---|---|---|
| `entities` | id, kind, name, path, tldr, meta (JSON), protected, noise | One row per doc / code / concept / memory |
| `linkage_types` | id, name, directed, inverse | Open verb registry; GMD `rel:` lines auto-register verbs |
| `bitmap_fragments` | partition_id, linkage, blob | The serialized `BitMap64` per (partition, linkage) |
| `entity_links` | linkage_id, concept_id, entity_id, weight | SQL shadow of the bitmaps, with weights (top-N, density); makes deletes O(links) |
| `linkage_evidence` | linkage, concept, entity, file, line, detail | `file:line` provenance: the trust mechanism behind `--explain` |
| `memory_content` | entity_id, content, mtype, tags, metadata | Memory body sidecar, logged so it replays |
| `tracked_files` | path, mtime, last_synced | Incremental skip of unchanged files |
| `partitions`, `canon_links`, `saved_queries` | | Namespaces, cross-partition concept hubs, named queries |

**C:** The bitmaps and `entity_links` hold the same facts in two shapes on purpose. Bitmaps
answer set algebra in microseconds. The SQL table answers "top 10 by weight" and "delete
everything this file contributed" without iterating a bitmap. Writes keep them in sync inside
one transaction. {#dual-shape}

### Concept hygiene {#namespacing}

**C:** Auto-extracted concepts are namespaced (`keyword/`, `import/`, `query/`) so noise can be
flagged and hidden without deleting it. `prune-noise` marks; only `--drop` deletes. Anything a
human adds is `protected` by default so maintenance never reaps it.

### Partitions are three things at once (ADR-0003) {#partitions}

**C:** A partition is simultaneously a **BM25 statistics base** (its own N, avgdl and document
frequencies), a **vector dataset** (`vectors/<partition>/<kind>.lance`) and a **wikilink
resolution scope**. The layout follows from making those three agree:

- **Things that cite each other co-reside.** Code, docs and memories share one partition.
  Splitting memory into its own partition was tried and reversed, because memory-to-memory
  `rel:` edges stopped resolving.
- **Things that distort the statistics are isolated.** Session cards would inflate the concept
  space by 24% on refmatrix and 74% on viascope, which would move idf for every term. They get
  `sessions-<project>`.

The canonical shape is exactly two partitions per project store and one for global. A
partition is only registered together with its first rows, in the same transaction, so a
zero-row registration (a leak) can't exist. {#partition-shape}

### Dense side {#dense-model}

**C:** Vectors live in Lance, one dataset per `(partition, kind)`, keyed by entity id. The
embedder is `BAAI/bge-small-en-v1.5` (384 dimensions, CPU-friendly). Two storage engines means
a dual-write rule: every catalog purge drops the matching Lance rows inline, or orphans leak.
The partition audit reports vector directories with no matching partition (the fleet survey
found about 143 MB of them).

## 7. High-level architecture {#architecture}

```
  Claude Code sessions ×N                          developer terminal
  ┌──────────────────────────────────────┐        ┌──────────────┐
  │ hooks: SessionStart · UserPromptSubmit│        │ rmx CLI      │
  │        PreToolUse · PostToolUse · Stop│        │ rmxgrep/rmxrg│
  │        PreCompact · SubagentStop      │        └──────┬───────┘
  │ MCP:   rmx mcp (stdio, one per client)│               │
  └──────────────────┬───────────────────┘               │
                     │   verbs.py — one typed function per capability
                     ▼                                    ▼
  ┌────────────────────────────────────────────────────────────────────────┐
  │ per-store daemon  (.refmatrix/rmxd.sock, launchd KeepAlive)            │
  │   disp_pool ─► cli_pool (4)  interactive reads                         │
  │             └► bg_pool (12)  ingest · sync · learn · vacuum            │
  │   _store_lock: strict-FIFO mutex serializes the ONE writer Store       │
  │   read tiers: in-memory mirror ─► catalog.read.duckdb ─► writer slot   │
  │   ticks: snapshot (250 ms debounce) · fragment flush · learn-queue     │
  │          drain · facts.log rotation · fs watcher (debounced sync)      │
  └───────┬─────────────────────────────┬──────────────────────────────────┘
          ▼                             ▼
  ┌──────────────────────┐     ┌──────────────────────────┐   ┌───────────────┐
  │ DuckDB catalog       │     │ Lance vectors            │   │ stm/*.jsonl   │
  │ + bitmap_fragments   │     │ vectors/<part>/<kind>    │   │ *.focus.json  │
  │ facts.log (JSONL)    │     └──────────────────────────┘   └───────────────┘
  └──────────────────────┘
                  ▲ watchdog / kickstart            ▲ embed / rerank RPC
  ┌───────────────┴──────────────────────────────────┴─────────────────────┐
  │ hub (user-level, launchd; ~/.refmatrix/hub.sock, UI on :7777)          │
  │   watchdog (dead vs busy vs wedged) · shared model workers (embed,     │
  │   rerank) · agent message bus + refine queue · global memory store ·   │
  │   per-project scheduler · fleet discovery · web UI                     │
  └────────────────────────────────────────────────────────────────────────┘
          ▲ upstream extractor: llm-tldr (.tldr/cache/{semantic,call_graph})
```

**C:** Four structural decisions carry the design. Each one was paid for by an incident:

1. **One daemon per store, owning the writer.** DuckDB is embedded and takes an exclusive
   cross-process file lock. When hooks fire in parallel (Edit, Stop, SubagentStop,
   SessionStart), the second process gets `IOException: Could not set lock on file`. The
   daemon makes every concurrent client a socket round-trip against one long-lived `Store`.
   Direct `Store()` opens on a live store are forbidden by project rule. {#d-daemon}
2. **Reads come from a snapshot tier, never the writer.** NF1 is satisfied structurally, not by
   tuning ([[#read-path]]). {#d-snapshot}
3. **The hub sits above the daemons and owns nothing of theirs.** It supervises, hosts shared
   models and the bus, and owns only the global store. A hub crash never takes a project's
   catalog with it. {#d-hub}
4. **One verb layer for every transport** ([[#api]]). {#d-verbs}

## 8. Deep dive: the write path {#write-path}

### Sources and freshness triggers {#freshness}

| Trigger | Mechanism | Cost |
|---|---|---|
| Agent edits a file | `PostToolUse` hook appends the path to `dirty.queue`; `Stop` fires `sync --flush-queue --async` | One `O_APPEND`; zero processes held |
| Git operation | `post-commit` / `post-merge` / `post-checkout` / `post-rewrite` → `sync --since` the diff | Proportional to the diff |
| Out-of-band change (build step, other tool) | Watchdog observer inside the daemon → debounced `sync_files` | Only when files change outside the routes above |
| Cadence | Hub scheduler runs `sync` / `embed` / `vacuum` / `checkpoint` per project | Amortized |
| Full rebuild | `rmx reingest`: code+docs → memory → sessions → embed, in canonical order | Minutes |

**C:** `sync._sync_paths` (`sync.py:287`) compares each file's mtime with `tracked_files` and
skips unchanged files before any extraction. A missing file purges its entities. A commit that
touches three files costs three re-ingests, not a full reindex. {#mtime-gate}

### The ingest pipeline {#ingest}

```
ingest_path(store, root, source=auto, semantic=True)     # ingest.py:385
  ├─ source=metadata  .tldr/cache/semantic/metadata.json → code units, calls/called_by, kinds
  ├─ source=tldr      .tldr/cache/call_graph.json        → file entities + calls
  ├─ source=tree      filesystem walk                    → file entities only
  └─ semantic passes (additive)
       ├─ Python AST: imports, docstring keywords
       ├─ ADR extractor: class specs → defines; ADR-NNNN → related_to
       ├─ plan/spec/issue docs → specifies (inverse specified_by)
       └─ markdown → GMD parser (ingest_gmd.py): {#anchors} → entities, rel: lines →
          typed edges (verbs auto-registered), heading tree → part-of, body terms →
          weighted mentions via bulk_link
```

**C:** Two performance details matter here:

- **Deferred cross-file links.** `store.deferred_links()` (`store.py:4509`) buffers linkages
  that point across files and flushes them in one batch at the end of the pass.
- **Weight-aware bulk linking.** `bulk_link` (`store.py:4686`) made GMD ingest 9.8× faster. The
  proof of equivalence was a byte-identical graph before and after.

**C:** The `specifies` edge is a product decision. Plans and specs used to be invisible to
discovery. In a sister project an ADR specified a `Zone` concept across 52 sessions, agents
never found the ADR through `context Zone`, and they built five fragmented alternatives. Making
plans first-class citizens of the same set algebra is what makes "specified but never built"
a query. {#specifies}

### Persisting a write {#persist}

1. The mutation runs under `_store_lock` in the daemon.
2. Bitmap changes land in the in-memory fragment; the linkage is added to a dirty set.
3. At the transaction boundary, `_flush_fragments_duckdb` (`store.py:4192`) UPSERTs one BLOB
   row per dirty `(partition, linkage)`, in the same DuckDB transaction as the
   `entity_links` / `linkage_evidence` rows.
4. After commit, one JSON event is appended to `.refmatrix/facts.log`. The log is replayable:
   `rmx rebuild --from-log` reconstructs the catalog, memory bodies included.

### Long writes must not starve reads {#cooperative}

**C:** An ingest can run for minutes. Pools alone don't help, because pools shape scheduling,
not lock ownership. Three mechanisms do:

- **Cooperative yield.** Long ingests release `_store_lock` every N units, sleep briefly and
  reacquire it.
- **A strict-FIFO lock.** `threading.Lock` is not fair: the releasing thread is still hot on
  the CPU and re-wins most cycles, so CLI ops queued for the whole ingest anyway. `_FairLock`
  (`daemon.py:258`) hands ownership explicitly to the next queued waiter.
- **Yield preserves the lock holder's state.** The writer `Store` has one partition binding.
  Job A yielded, job B bound its own partition, and A resumed writing rows and derive stamps
  into B's partition (bug-098). `_partition_keeping_yield` (`daemon.py:3606`) records the
  binding before releasing the lock and restores it after reacquiring.

### Learning grep: teach without blocking {#learn}

**C:** Every agent `grep`/`rg` is rewritten by a PreToolUse hook into `rmxgrep`, a byte-exact
drop-in that teaches the graph what it found. A miss becomes a protected `query/<term>`
concept, so the same search next time lands at the `query` step. The first version taught
through a write RPC per grep. Against a busy writer, with default retries, that cost up to
30 s per call after the results were already printed: 104 of 1,165 calls sat at about 30.2 s.
Now the client does one `O_APPEND` to a coalescing learn queue (`learn_queue.py:55`) and the
daemon drains it on its own tick. A marker file, not a catalog key, carries the global
learn on/off switch, because the hook that reads it can't afford to open DuckDB on every tool
call. Anything the wrapper can't reproduce byte-exactly exits 2, and the wrapper falls back to
the real tool. The worst case is plain grep, never a silently wrong answer. {#learn-detail}

## 9. Deep dive: the read path {#read-path}

### Three read tiers {#read-tiers}

`Daemon._open_read_store` (`daemon.py:2681`) resolves a read in this order:

| Tier | What | Latency | Staleness |
|---|---|---|---|
| 1. In-memory mirror | One shared in-memory `Store`, refreshed from the snapshot | ~1 ms | ≤ 250 ms + refresh |
| 2. Snapshot file | `catalog.read.duckdb`, opened read-only | ~10 ms per open | ≤ 250 ms debounce |
| 3. Writer slot | Only during early bootstrap, before a snapshot exists | Contends with the writer | Fresh |

### How the snapshot is made {#snapshot}

**C:** `_snapshot_catalog` (`daemon.py:2851`) runs a `CHECKPOINT` to fold the WAL into the main
file, copies the file to a temp path, `os.replace`s it into place, and swings the
`read_only.duckdb` symlink. It is debounced by `RMX_SNAPSHOT_DEBOUNCE_MS` (250 ms by default),
and `_op_snapshot(force=True)` bypasses the debounce for a caller that needs read-your-writes.

**C:** The copy runs in a **child process** (`_copy_out_of_process`, `daemon.py:219`). This is
the subtlest bug in the system and worth explaining. DuckDB guards its file with a POSIX
`fcntl` record lock, and POSIX record locks belong to the (process, file) pair. *Any* `close()`
of *any* descriptor for that file in the same process drops the lock. The original in-process
`shutil.copy2` therefore released the daemon's writer lock on its first run, and a second
process could open the slot and commit (bug-110). A child's descriptors are its own. A failed
copy can leave a partial file, so the caller never installs the destination when the copy
raises. {#fcntl}

### Why the A/B writer rotation was retired {#rotation}

**C:** An earlier design kept two writer slots, A and B, caught the inactive slot up by
replaying `facts.log`, then swapped the writer onto it. It failed on one invariant: **any state
not captured by the log is missing from the promoted slot.** The `memory_content` sidecar
wasn't logged, and neither were writes made while the daemon was down. The swap silently
dropped them, and the reader snapshot rebuilt from the swapped slot served the loss as truth.
That produced weeks of "slot drift" and a `replica merge` recovery tool with id remapping.
The fix: log `memory_content`, pin the writer to one slot for the daemon's life, make the swap
a no-op, and derive reads from a file copy instead of a replay. The rule that came out of it:
**no swap may ever promote a slot missing committed data**, and **the log is the recovery
boundary**. Any table written outside the log is structurally invisible to recovery, and that
is now a review rule. {#rotation-lesson}

### Thread pools {#pools}

**C:** The accept loop hands each connection to `disp_pool`, which classifies by op name and
forwards to `cli_pool` (4 workers by default, latency-sensitive reads) or `bg_pool` (12
workers, bulk and mutating ops). A `query` that arrives while `bg_pool` is saturated lands at
the head of `cli_pool`'s own queue instead of behind N ingest tasks. The pools don't change lock
semantics. Reads don't take the writer lock at all, because they ride the mirror or the
snapshot.

**C:** One concurrency bug from this design is worth naming. The mirror is one shared `Store`,
and readers re-pointed its partition outside the mirror's use-lock. Under concurrent load,
39 of 40 `context` ops answered from the wrong partition. Binding the partition inside the
use-lock fixed it. A shared mutable cursor needs its configuration under the same lock as its
use. {#mirror-race}

## 10. Deep dive: retrieval and ranking {#ranking}

### Unranked set algebra {#set-algebra}

**C:** `QueryEngine` (`query.py`) compiles the DSL (`AND`/`&&`, `OR`/`||`, `NOT`/`!`,
parentheses; a term is `linkage:concept` or a bare concept meaning "any linkage") or PQL
(`Row`, `Intersect`, `Union`, `Difference`, `Xor`, `TopN`, `Neighbors`, `Count`) into roaring
operations. `--explain` walks `linkage_evidence` and returns `file:line` for every membership.

### Content ranking {#content-rank}

**C:** `Store.content_rank` (`store.py:5147`) is the ranker that `context` and the benchmarks
share:

```
score(q, e) = BM25(q, e)
            × coverage(q, e) ** 3          # fraction of query terms hitting e
            × Σ_linkage w_linkage · hits    # docstring linkage weighted 0.30
            × co_mention(q, e) ** 2         # linkage-coupled, not raw frequency
```

**C:** Multi-linkage neighbourhood walks in `build_context` (`context.py:136`) fuse their
per-linkage rankings with Reciprocal Rank Fusion (`fuse_rrf`, `query.py:33`, k = 60), so no
per-linkage weight needs tuning.

### The proactive path: `scan-prompt` {#scan-prompt}

`scan_prompt` (`scan.py:893`) runs on every `UserPromptSubmit`:

```
prompt
  → extract candidates (shared stoplist; identifier splitting)
  → match against the concept set; drop operational anchors (session cards etc.)
  → salience score  × global PageRank prior   (pagerank.py, offline, sidecar table)
  → personalized PageRank, Andersen–Chung–Lang local push (ppr.py)
        α = 0.15 restart; work bounded by O(1/(ε·α)), independent of graph size
  → lift-scored association: lift(c) = (co(c)/|A|) / (df(c)/N)   (assoc.py)
        favours concepts that are *specifically* co-located, not globally central
  → build_context bundle per surviving concept
  → cross-encoder rerank over bodies (pool 10, not 30)
  → hook_budget.fit_blocks: one shared byte budget across every producer on the hook
  → every third prompt: an STM topic composite under its OWN token budget
```

**C:** PPR beats a degree-2 walk because a bipartite concept⇄entity graph is small-world: two
hops from any hub reaches most of the corpus. PPR's restart probability bounds reach per node,
and a fixed hop count can't. Measured on MemAware: PPR MRR 0.065 against 0.013 for the walk, 5×.

### Dense, rerank and fusion {#dense}

- **Recall.** `dense_recall` (`recall.py:45`) is pure ANN. `hybrid_recall` (`recall.py:65`)
  RRF-fuses a symbolic ranking with ANN, optionally after a bitmap prefilter.
- **Fusion is off by default for memory recall.** Measured: dense-only MRR@10 0.848 against
  fused 0.794. Fusion wins Recall@10 (+0.143) and nDCG (+0.095), which suits set-shaped
  surfaces, but it loses top-1. The default follows the measurement; `--fuse` is opt-in.
- **Rerank.** A cross-encoder (`ms-marco-MiniLM-L-12-v2`) over a pool of `k × 4`, capped at 100.
  It reorders and can't recall. The L-6 sibling returns NaN for every pair under the current
  transformers/torch versions, so `reranker._checked` rejects non-finite scores. NaN compares
  false against everything and would silently scramble a sort.
- **What gets encoded matters.** Code vectors that accidentally encoded file paths instead of
  bodies cost 0.34 MRR (0.63 → 0.97 once fixed).

### Packing for the hook {#pack}

**C:** `recall_pack.pack` (`recall_pack.py:167`) renders hits pointer-first. Each hit is one
line (name, curated hook, and the exact `rmx memory get` command that fetches it), about
200–370 B. Every hit fits under the budget, and whole bodies follow only while they still fit.
Twelve hits that used to be 15–59 kB of JSON now arrive whole.

### Degrade, never go empty {#grep-floor}

**C:** When the index has nothing for a term that exists in the tree, `context` falls through to
a ranked literal-grep floor, and the fallback hits are learned into the graph. The index
improves from its own misses.

## 11. Deep dive: memory {#memory}

### Three tiers {#memory-tiers}

| Tier | Storage | Written by | Read by |
|---|---|---|---|
| **Working (STM)** | `stm/<session>.jsonl` append-only event ring + `<session>.focus.json` focus graph | every harness hook via `focus hook` | per-prompt composite; `focus context`; helix |
| **Durable (LTM)** | GMD files on disk under `~/.claude/projects/<slug>/memory/`, bridged into `kind=memory` rows + Lance vectors | humans, agents, `save-state` | `memory recall` (prompt, SessionStart, PreCompact); `context` |
| **Episodic** | Session JSONL → one GMD "session card" per session in `sessions-<project>` | `session ingest` (launchd ticker) | `session recall` (BM25 + metadata filters) |

**C:** Files on disk are the source of truth for durable memory, and the store is an index over
them. That keeps memories diffable, reviewable and `git`-able. The bridge
(`ingest-gmd --as-memory`) runs on every SessionStart and on save-state. ADR-0005 makes
`memory_layout.iter_memory_files` the *only* walk of a memory directory, after three readers
with three walks disagreed and one of them turned a 157-line index into one line. {#files-truth}

### The focus graph {#focus-graph}

**C:** STM isn't a ring buffer. It's a small graph (`stm.py:1113`). Nodes are addressable by
reference name and refreshed in place, never duplicated. Every turn multiplies recency by a
decay factor. Admission is capped per turn (`MAX_ADMIT_PER_TURN`) so one noisy turn can't churn
the graph. Admitted refs form a clique whose edge weights grow by 1.0 per co-occurrence
(`_apply_turn`, `stm.py:1434`). Eviction is by a composite of recency, frequency, centrality
and pin, so structural hubs survive. Evicting a node that still has a live neighbour leaves a
**frontier stub**, a breadcrumb that can be rehydrated from LTM.

**C:** The design centre is **passive capture**. A voluntary reasoning-capture command logged
zero calls across twenty turns of design work. A capture channel bound to a mandatory hook gets
used, and a voluntary one doesn't.

### Graduation: STM → LTM {#graduation}

- **save-state** (`verbs.py:1621`) compiles one durable GMD handoff memory (git facts, the top
  focus symbols, the task stack, recently touched memories), refreshes `MEMORY.md` under its
  200-line cap, and promotes an STM digest. **recall-state** (`verbs.py:2011`) is the mirror
  image, and also fires automatically on `SessionStart` after `compact` or `clear`.
- **Edge promotion** (`promote.py`) moves recurring co-occurrence into a durable `co-occurs`
  verb, gated on recurrence across several turns. Without the gate, the top STM nodes measured
  mid-session were `multiple`, `cross`, `terms`, `prompt`: the vocabulary of a conversation
  about retrieval, not its subject. Associative edges decay. Structural edges (`calls`,
  `defines`, `imports`) never do, and promotion never touches them.
- **Signed reinforcement** (`reinforcement.py`): a concept's confidence is
  Σ(+|w| for `reinforces`) + Σ(−|w| for `contradicts`), exponentially decayed by age and
  clamped. The sign comes from the verb, never from the stored weight, so a mis-signed weight
  can't flip polarity.

### The helix: time as a retrieval dimension {#helix}

**C:** When retrieval touches a concept whose last STM touch is outside the working window,
`helix.annotate` (`helix.py:307`) attaches a point-in-time snapshot reconstructed from the STM
rings: *"last worked 77 days ago; then: <what>; neighbourhood then: <files>"*. It needs no
schema change, because the rings already carry `ts`. Every emission is telemetry-logged, so
whether to build phase 2 (mutable edge-time columns or a versioned store) is decided by
whether anyone reads phase 1. The instrument needed its own debugging first. The per-prompt
hook retrieves what the prompt mentions, which the current ring has just recorded, so the
annotation suppressed itself by construction until the current session was excluded from
last-touch.

### The global store {#global}

**C:** `~/.refmatrix` holds cross-project behaviour memories and is memory-only **by
construction**. Every ingest route, daemon op and direct CLI call alike, refuses filesystem
code and doc paths there. `ingest-gmd --as-memory` is the one sanctioned write shape.

## 12. Deep dive: the fleet control plane {#fleet}

### Watchdog: dead, busy or wedged {#watchdog}

**C:** The first watchdog pinged with a 0.5 s timeout and SIGKILLed any daemon that missed. A
daemon busy in a lock-holding embed is indistinguishable from a dead one by ping alone, so the
watchdog killed busy daemons mid-write, which caused the next restart: a crash loop diagnosed
by restart timestamps lining up with the start of long ops. The current hub (`hub.py:41-56`,
`316-330`) separates three states:

| Observation | Verdict | Action |
|---|---|---|
| Process gone | dead | restart now (`launchctl kickstart`, or exec) |
| Process alive, ping missed, heartbeat fresh | busy | record `busy-heartbeat-Ns`, no restart |
| Process alive, heartbeat stale, misses ≥ `WATCHDOG_GRACE_MISSES` | wedged | graceful restart: `daemon stop` → SIGTERM, escalate only after that |
| Store under `rmx hub pause` | maintenance | observe, never restart; reset the miss counter |

### Shared model workers {#model-workers}

**C:** A resident sentence-transformers model is about 610 MB, and macOS jetsam SIGKILLs the
fattest process under memory pressure. That kill is uncatchable and lands mid-ingest.
In-process eviction doesn't work: dropping the model and calling `gc.collect()` returned
84 MB of 610, because torch's caching allocator never gives memory back on macOS. So:

1. **Out of process.** `embed_worker` is a separate process speaking a framed protocol. Evicting
   it means `kill()`, which actually returns the memory. Daemon RSS went from 695 MB to 203 MB.
2. **Shared across the fleet.** Seven stores × two models made 14 workers and about 6.5 GB
   resident, all serving one user typing in one project. `modelsrv` hosts one embed worker and
   one rerank worker in the hub, and daemons connect over a Unix socket using the same framed
   protocol. Fleet model RSS dropped to about 0.9 GB. `SharedWorkerClient`
   (`modelsrv.py:131`) slots in with no changes to `RemoteEmbedder` or `RemoteReranker`.
3. **Contained failure.** The worker never opens a store, holds no locks and sees no catalog.
   Text goes in and numbers come out. If it dies, it dies alone, and every caller degrades to
   retrieval order with a logged reason.

### Message bus {#bus}

**C:** The hub hosts pub/sub for live agents. Channels are `proj:<name>:<topic>` within a
project and `global:<topic>` across projects. Messages fan out in memory and persist in a
small SQLite table, so late joiners can replay, with per-agent read cursors (rowid as the
sequence), soft-delete, archive and purge. High-signal kinds (`announce`, `decision`) go into a
**refinement queue** that a human or agent must approve before anything becomes memory. Nothing
gets written into memory without review.

### Deploy is not release {#deploy}

**C:** A daemon serves the code it imported at start, and the MCP server is a per-client stdio
process. Fast-forwarding the install tree changes nothing until the processes are respawned.
`rmx daemon restart --relaunch` verifies the new pid *and* the new version, and the hub's
version handshake relaunches the fleet. The flip side is a standing hazard: a dev-venv `rmx`
with a bumped version pointed at a live store triggers that handshake. The project rule forbids
it, and tests run under separate macOS users (`rmxtest1..3`, locally and on a Mac mini), each
with its own HOME, launchd domain and no write access to live stores.

## 13. Consistency and durability {#consistency}

| Property | Guarantee | Mechanism |
|---|---|---|
| Write serialization | Total order per store | One writer `Store` behind a strict-FIFO lock |
| Atomicity | Bitmaps, shadows and evidence commit together | One DuckDB transaction per flush |
| Durability / recovery | Replayable from the log | `facts.log` appended after commit; `rebuild --from-log`; `compact-log` bounds growth |
| Read consistency | Bounded staleness, about 250 ms | Debounced snapshot; `snapshot force=True` when read-your-writes is needed |
| Catalog ↔ vectors | Eventually consistent, audited | Inline Lance drop on purge; orphan audit |
| Legacy formats | Refused, never guessed | A store holding only a SQLite `catalog.db` raises `LegacyCatalogError` in one line (`store.py:73`) before any command runs |

**C:** I accept bounded staleness on reads because the consumers are prompt hooks, which only
need to see an edit by the *next* prompt. 250 ms is well inside the gap between two human
prompts. I would not accept it for the learning loop's own writes, which is why those are
queued to the writer rather than read back.

## 14. Failure modes the system was hardened against {#failures}

**C:** The index's failure mode isn't absence. It's **confident wrongness**. Every row here is
a real incident with a structural fix:

| Incident | Symptom | Structural fix |
|---|---|---|
| Main-path indexing gap | 43–83% of entities across the fleet had **zero indexed terms**; every surface still returned plausible results; 8 published experiments invalidated | Markdown → GMD dispatch, semantic on by default, `reingest --force`; rule: *the main path must exercise core mechanisms*; `memory brief` reports where the store is thin |
| Hook output truncation (bug-164) | Recall arrived as a 2 kB preview on 95% of prompts | Measured the cap; one shared `hook_budget`; pointer-first packing |
| fcntl lock drop (bug-110) | Snapshot copy released the writer lock | Copy in a child process |
| Partition binding across yield (bug-098) | A reingest wrote rows into the sessions partition | Yield restores the holder's binding |
| Mirror partition race | 39/40 concurrent reads from the wrong partition | Bind inside the use-lock |
| Slot drift | Swapped writer lost unlogged state | Rotation retired; log is the recovery boundary |
| Watchdog false positive | Busy daemons SIGKILLed into a crash loop | Dead/busy/wedged distinction, heartbeat, grace, graceful restart |
| Jetsam | Uncatchable SIGKILL mid-ingest | Out-of-process, fleet-shared models |
| DuckDB secondary-index drift | `ON CONFLICT` races and phantom UNIQUE leaves → SIGABRT; one store bloated to 82 GB behind a health check that read green while serving nothing | Repair on startup, `repair-index`; health checks probe the serving path, not the process |
| Learning-grep stall | 30 s per grep after results printed | Append-only learn queue drained by the daemon |
| Grep pipe-detection race | Drop-in grep searched the wrong corpus | Fail loud (exit 2) on anything not reproducible byte-exactly |
| Big op vs. always-on surfaces | A partition merge blew every prompt-hook deadline | Lock-yield batching, replica-first hook reads, hub maintenance pause; rule: big ops must not block always-on surfaces |

**C:** The meta-lesson for the interviewer: an index this ambitious earns trust per surface. The
defences are generic. Exit codes fail loud, guards refuse rather than remember, benchmarks are
pinned to the production path, and a measurement's provenance (`fingerprint.py`) is recorded
with the number.

## 15. Evaluation and observability {#evaluation}

### Benchmarks on the production path {#benchmarks}

| Benchmark | rmx | Baseline | Note |
|---|---|---|---|
| CodeSearchNet Python, **production ingest path** (43,827 docs · 14,918 queries) | **MRR@10 0.961**, R@1 0.944 | CodeRankEmbed (dense, GPU) 0.959 / 0.934 | CPU only; ~3–4 min ingest vs ~100 min GPU encode; every score traces to `file:line` |
| CSN JavaScript (historical harness) | 0.939 | 0.916 | Margin grows with cross-file density |
| CSN TypeScript (historical, fork duplicates) | 0.365 | 0.358 | Low absolute, still ahead |
| Doc–doc relatedness (138 author-linked pairs) | co-occurrence AUC **0.929** | dense cosine 0.815 | Dense cosines compress into a 0.70–0.79 band inside one project |
| MemAware proactive retrieval, `scan-prompt` | MRR@20 0.043 → **0.241** | flat BM25 0.242 | At parity; the ceiling is **recall**, not ranking |

**C:** The headline number I'd defend is 0.961, not the 0.972 the earlier bespoke harness
produced. That harness never called `ingest` and so hid four defects. A CI test fails when the
README table and the committed metrics artifact disagree.

### Measured negatives {#negatives}

**C:** I keep rejected ideas as fence posts so nobody re-litigates them: the degree-2 walk (5×
worse than PPR), PRF expansion from tldr bodies (0.217 → 0.208), concept prefilter for ANN
(exact null), a phrase layer (identical hit@20), RRF as the default for memory recall (−0.054
MRR), 7 of 8 structural ranking signals (flat; only lead position paid, +20% MRR), and LatticeDB
as a backend (reachability fine, BM25 scored 0.0).

### Telemetry {#telemetry}

**C:** `query.log` is JSONL with `kind`, `source` (which surface answered), `invocation` (hook,
interactive, mcp, internal), `outcome` (ok, empty, consumer-closed, error), `answered_by` (for
grep: index, replica or floor), `latency_ms` and the effective learn state. That is how the
project found it had dozens of greps and few voluntary `context` calls per session, which
argued for the grep rewrite hook. The tool fits the agent's existing habit instead of asking
the agent to change.

### Self-verification gates {#gates}

- `install-hooks --check` exits 1 if a project's installed hook block differs from the
  generator's render.
- The verb parity test fails if CLI defaults drift from verb defaults.
- The generated CLI tree in `ARCHITECTURE.md` fails a test when it drifts from the code.
- 4,356 tests, run on committed shas in isolated per-user lanes.

## 16. Scaling: what breaks at 10× and 100× {#scaling}

**I:** The developer now has 10× the code, or a team wants to share a store. What breaks first?

**C:** In the order I expect to hit them:

1. **Snapshot write amplification.** The snapshot is a full file copy (`cp -p`) of the writer
   slot, debounced at 250 ms. At 1.3 GB, a sustained write burst costs O(catalog) I/O per
   snapshot. Fixes, from cheapest: an APFS clone (`cp -c`, `clonefile(2)`), which is
   copy-on-write and near-free; a longer adaptive debounce under write load; and in the long
   run, ADR-0004's **snapshot manifests**, where readers pin a content-hashed list of immutable
   tier blobs instead of a file copy. {#scale-snapshot}
2. **Fragment write amplification.** One BLOB per `(partition, linkage)` means touching one bit
   of `mentions` re-serializes and UPSERTs the whole `mentions` fragment. Pilosa solves this by
   sharding columns (2²⁰ per shard). Shard fragments by entity-id range so a flush rewrites only
   the dirty shards. {#scale-fragments}
3. **Single writer lock.** With all ingest work on one lock, throughput is serial. Partitions
   are already the natural shard key, so a writer per partition (separate DuckDB files) lifts
   that, at the cost of cross-partition queries becoming a federated merge, which the MCP layer
   already does across stores. {#scale-writer}
4. **Id space.** 32-bit entity and concept ids per partition cap a partition at about 4 × 10⁹.
   That's not a near-term limit. ADR-0004's u64 location ids
   (`entity(32) | sid(32)`) spend the space on sub-document granularity instead.
5. **Team sharing.** The facts log is already a replication stream. Put a hub-side follower that
   tails `facts.log` behind HTTP for read-only teammates, and keep the single-writer model per
   store. Auth becomes real at that point. Today the Unix-socket permissions are the auth model.

**C:** What I would *not* do is move to a distributed graph database. The query mix is set
algebra + BM25 + ANN, all columnar. A property graph pays pointer-chasing for what is really
bitmap math.

## 17. Trade-offs I'd defend {#tradeoffs}

| Criticism | Answer |
|---|---|
| "Just use embeddings." | Dense alone lost every within-project comparison measured (AUC 0.815 vs 0.929; memory MRR fusion −0.054), and it can't answer *why* a result matched. `--explain` → `file:line` is load-bearing for agent trust. Dense stays as a complement. |
| "Postgres + pgvector." | It solves the wrong half and adds a server, which violates NF3. |
| "Neo4j / a graph DB." | It models the data fine, but the hot path is set algebra, which bitmaps do in microseconds. |
| "Elasticsearch / Tantivy for BM25." | It would cover ranking, but not typed-edge set algebra or memory semantics, and it's a second server or a second index to keep in sync. |
| "SQLite is simpler." | It owned the catalog first. DuckDB won when catalogs passed about 100M rows and analytics (top-N, density, eval) needed vectorized plans. SQLite was deleted in task S1 (2026-11-19). Legacy stores are refused by name, not autodetected. |
| "The daemon adds operational surface." | It does: watchdog, snapshot tier, relaunch semantics. It bought NF1. Every attempt to do without it (direct opens, a second in-process connection) died on DuckDB's lock model. |
| "Two storage engines is complexity." | Yes, plus a dual-write rule. The one-engine candidate (LatticeDB) failed on scoring correctness. |
| "Hooks on every event are invasive." | Voluntary channels measured near zero use. Bound channels get used. Every hook is time- and byte-bounded and exits 0, so it can't block a prompt. |

## 18. Evolution {#evolution}

**C:** The next twelve months follow ADR-0004, *one location space*:

1. **Location ids.** Every unit of text (section, paragraph, sentence; for code: file, class,
   def, block) gets a stable u64 `entity(32) | sid(32)`. A per-document map translates it to its
   Dewey position, so edits don't reset history: unchanged units keep their sid by hash.
2. **Tiered bitmaps.** One mechanism for tf tiers (≥1, ≥2, ≥4…), age tiers (day, week, month)
   and session tiers. This is a BSI-lite, because pyroaring has no bit-sliced index.
3. **Sentence co-location ranking.** `BM25_norm + 2.0 × sentence_coloc` is already measured as a
   win at the L1 layer.
4. **Snapshot manifests.** "The graph as of X", replica merge and slot reconciliation all
   become a manifest diff. This replaces both the file-copy snapshot ([[#scale-snapshot]]) and
   helix phase 2's versioned-store fork.
5. **A confidence cascade, as a latency device only.** If BM25 top-1/top-2 > 1.25, skip
   co-location, expansion and rerank (~87% of near-verbatim queries). Measured: it never
   improves accuracy, so it's adopted only for speed.
6. **Cross-codebase canon.** `canon link` grows into recognizing the same concept across N repos.

rel: depends-on -> [[#helix]]
rel: motivates -> [[#scale-snapshot]]

## 19. Curveball follow-ups {#curveballs}

**I:** A memory file is edited on disk while the daemon is down. What happens?

**C:** Nothing is lost, because the file is the source of truth. The SessionStart bridge
re-ingests the memory directory, the mtime gate picks up the change, and recall sees it. The
risk is the reverse: a *store-only* write made while the daemon was down. That's why direct
store opens on a live store are forbidden and why every write path goes through the daemon and
the log.

**I:** Two Claude sessions ingest into the same store at once.

**C:** Both requests land in `bg_pool` and serialize on `_store_lock`. Each yields
cooperatively, the FIFO lock gives the other a turn, and each yield restores its own partition
binding. Reads from both sessions ride the snapshot and never wait.

**I:** The embedding worker hangs.

**C:** `RMX_WORKER_TIMEOUT_S` (300 s) kills it. A worker that dies twice is not retried for that
call, the caller degrades to symbolic retrieval order, and the log names the reason. The daemon
never held the model, so its catalog is untouched.

**I:** How do you know the index isn't silently empty?

**C:** Three layers. `memory brief` and the derive log report coverage per pass (which code
derived this partition, and what each derive changed). The partition audit reports shape
drift. And benchmarks run the production ingest, so a coverage regression shows up as an MRR
regression rather than staying invisible.

**I:** Why not let the LLM summarize memories into the store?

**C:** Briefs and digests are deterministic detectors over signal already in the store, with
named thresholds, and every brief must carry entity ids a reader can resolve
(`Brief.__post_init__` refuses an empty evidence list). A model in that loop becomes a
plausible-sentence generator with no provenance, which is the confident-wrongness failure
mode again.

**I:** A user greps for something the index has never seen.

**C:** The wrapper runs the real tool (or the indexed path where it can be byte-exact), prints
the real bytes, and appends a learn record. The daemon drains it into a protected `query/<term>`
concept with the hit files linked, so the next lookup resolves at `query` or `context`.

## 20. Interviewer rubric {#rubric}

### Signals by level {#levels}

| Dimension | Senior | Staff | Principal |
|---|---|---|---|
| Problem framing | Builds "a vector DB for code" | Separates retrieval, durable memory and working memory; names the token budget | Also names the agent's *behaviour* (voluntary channels go unused) as a design input |
| Data model | Tables + embeddings | Bitmap matrix with evidence; explains the packing | Explains why bitmaps and a SQL shadow both exist, and partition-as-statistics-base |
| Concurrency | "Use a lock" | Single-writer daemon, snapshot reads | fcntl per-process lock semantics, lock fairness, state carried across a yield |
| Durability | "DuckDB is ACID" | Replay log | "The log is the recovery boundary"; why a slot swap can promote missing data |
| Ranking | BM25 or cosine | Fusion, rerank, PPR | Defaults chosen by measurement; knows what fusion buys (recall) and costs (precision@1) |
| Operations | "Restart on crash" | Supervisor + health checks | Dead/busy/wedged; health checks must probe the serving path; deploy ≠ release |
| Evaluation | Quotes a benchmark | Production-path benchmark | Provenance of numbers; negative results as fence posts |

### Red flags {#red-flags}

- Putting an LLM in the indexing loop with no evidence requirement.
- Health checks that ping the process rather than exercising a read.
- A benchmark harness that doesn't call the production ingest.
- `|| true` / `2>/dev/null` on the path between a memory file and the store.
- "We'll add a server later" with no account of the laptop memory budget.

## Appendix A — Numbers cheat sheet {#numbers}

| Number | Value |
|---|---|
| Version / master | 0.84.0 / `338c6dfb` |
| Source | 76 modules, ~77k lines of Python (`cli.py` 15.3k, `store.py` 8.7k, `daemon.py` 7.5k) |
| Tests | 4,356 test functions across ~400 files |
| Fleet | 8 supervised daemons, 172–733 MB RSS each |
| Hook output cap | 10,000 UTF-16 units per hook command |
| Snapshot debounce | 250 ms (`RMX_SNAPSHOT_DEBOUNCE_MS`) |
| Daemon pools | cli 4, bg 12, disp cli+bg+4 |
| PPR | α = 0.15, local push O(1/(ε·α)) |
| RRF | k = 60 |
| Rerank pool | k × 4, cap 100 (scan-prompt pool 10) |
| Embedder | bge-small-en-v1.5, 384-d |
| Model RSS, fleet | 6.5 GB → 0.9 GB (shared workers) |
| Daemon RSS with model out of process | 695 → 203 MB |
| CSN Python MRR@10 | 0.961 vs 0.959 (CodeRankEmbed) |
| Bug registry | 296 rows, each with a test or a strict xfail |

## Appendix B — Code map {#code-map}

| Concern | Location |
|---|---|
| Verb layer + generated MCP schemas | `src/refmatrix/verbs.py:87`, `:191` |
| Store, fragments, flush | `src/refmatrix/store.py:4192`, `:4509`, `:4686`, `:5147` |
| Legacy catalog refusal | `src/refmatrix/store.py:73` |
| Daemon pools | `src/refmatrix/daemon.py:2038-2080` |
| FIFO lock | `src/refmatrix/daemon.py:258` |
| Out-of-process snapshot copy | `src/refmatrix/daemon.py:219`, `:2851` |
| Read tiers | `src/refmatrix/daemon.py:2681` |
| Partition-keeping yield | `src/refmatrix/daemon.py:3606` |
| Ingest entry | `src/refmatrix/ingest.py:385`; GMD `src/refmatrix/ingest_gmd.py:1279` |
| Incremental sync | `src/refmatrix/sync.py:75`, `:84`, `:287` |
| scan-prompt | `src/refmatrix/scan.py:893` |
| Context bundles | `src/refmatrix/context.py:136` |
| RRF | `src/refmatrix/query.py:33` |
| Hybrid / dense recall | `src/refmatrix/recall.py:45`, `:65` |
| Hook budget, packing | `src/refmatrix/hook_budget.py:219`, `src/refmatrix/recall_pack.py:167` |
| STM focus graph | `src/refmatrix/stm.py:1113`, `:1434` |
| Helix | `src/refmatrix/helix.py:307` |
| Hub watchdog | `src/refmatrix/hub.py:41-56`, `:316-330` |
| Shared model workers | `src/refmatrix/modelsrv.py:131` |
| Partition layout | `docs/adr/0003-canonical-partition-layout.md` |
| Location-space roadmap | `docs/adr/0004-unified-location-space-index.md` |
