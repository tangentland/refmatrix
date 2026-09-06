---
gmd: "0.1"
id: system_design_review
title: "refmatrix — System Design Interview"
tags: [design, architecture, interview, retrieval, memory]
---

# refmatrix — System Design Interview {#root}

A staff-level system design interview, reconstructed for refmatrix as the
system under review. **I** is the interviewer, **C** the candidate. The
answers reflect the system as actually built (v0.60.x, 2026-09), including
the numbers and the scars.

rel: related-to -> [[ARCHITECTURE]]
rel: related-to -> [[SYSTEM]]
rel: evidence-for -> [[PERFORMANCE]]

## Problem statement {#problem}

**I:** Design a memory and retrieval system for AI coding agents. The agent
works across many repositories over months; it should stop re-deriving what
it already learned, find code by meaning as well as by name, and survive its
own context window being wiped every session.

**C:** Three distinct problems hiding in one sentence:

1. **Code/document retrieval** — "where is X, what calls it, what talks
   about it" — must beat grep on precision and beat an embedding index on
   explainability, and must be fast enough to run on *every prompt*.
2. **Durable memory** — facts, decisions, feedback that outlive a session,
   with typed relationships (supersedes, amends, depends-on), not a flat
   note pile.
3. **Working memory (STM)** — what is happening *right now*, captured
   passively from the agent harness, promotable to durable memory at
   session end.

The consumers are agents, so every read surface must be token-budgeted:
the product is not "results", it is "the best 2000 tokens for this prompt."

## Requirements {#requirements}

**I:** Constrain it.

**C:** Functional:
- Symbolic graph: entities (code units, docs, concepts, memories) + typed
  weighted linkages (defines / calls / mentions / imports / is_a / …).
- Dense retrieval as a *complement*, never the spine (explainability).
- Per-prompt context injection (hook path) with a hard token budget.
- Multi-project: one machine, N repos, plus a global cross-project store.
- Multi-agent: concurrent Claude sessions sharing stores + a message bus.

Non-functional:
- Reads must never block on writes (an agent's prompt hook stalling on an
  ingest is a product failure — a lesson paid for twice).
- Always-on surfaces < ~1s; big operations (ingest, embed, merge) must be
  non-blocking and observable.
- Single machine, no server dependencies a laptop can't run. Crash-restart
  is the recovery model, supervised by launchd.
- Honest evaluation: benchmark the path users actually run, not a bespoke
  harness (a true number on a bypassed path hid four defects once).

rel: evidence-for -> [[system_design_review#eval]]

## Scale envelope {#scale}

**I:** Numbers?

**C:** Measured, not estimated: catalogs from 50MB to ~1GB; the largest
store carries ~1.5M entities / 100M+ bitmap memberships; 47k-document eval
corpora; 2.5k-file markdown trees; STM rings in the tens per project, KBs
each. Embeddings: hundreds of thousands of vectors per store. This is
single-node scale — the design goal is *latency and isolation*, not
horizontal scale-out.

## High-level architecture {#architecture}

**I:** Draw it.

**C:**

```
Claude sessions (CLI / hooks / MCP stdio)
        │  verbs.py — ONE typed function per capability
        │  (schemas generated; payloads built once)
        ▼
per-store daemon (unix socket, owns DuckDB writer)
        │        ├─ replica slots A/B (lock-free readers)
        │        ├─ change queue + watcher (debounced sync)
        │        └─ helix / STM / memory ops
        ▼
storage: DuckDB catalog + roaring bitmaps (symbolic)
         Lance (dense vectors)  ·  facts.log (JSONL replication log)
         stm/*.jsonl rings (working memory)

hub (:7777) — supervises daemons (watchdog + grace), hosts the web UI,
agent message bus, global memory store, shared model workers (embed/rerank
out-of-process; 14 workers → 2 shared, 6.8GB → 0.9GB fleet RSS)
```

Key structural decisions, each earned the hard way:

- **One daemon per store, owning the writer.** DuckDB takes an exclusive
  cross-process lock; two writers means SIGABRT or lock storms. Every write
  routes through the daemon (`_store(write=True)` returns an RPC proxy);
  direct opens are the documented bootstrap exception. {#daemon-owner}
- **Read/write split via replica slots.** The daemon snapshots the catalog
  to alternating A/B files; CLI reads open the replica read-only, so a
  saturated writer can't stall a prompt hook. The active-slot marker is the
  single source of truth — a daemon-down CLI once wrote the legacy file and
  produced weeks of "drift". {#replica}
- **The log is the replication boundary.** `facts.log` (JSONL) records
  every write; replica refresh is delta-replay. Any table written outside
  the log is structurally invisible to recovery — that invariant is now a
  review rule. {#log-boundary}
- **Shared verb layer.** CLI and MCP handlers were twin hand-built payloads
  and drifted (a dead MCP query tool, a semantic-less ingest). Now one
  `@verb` function per capability; MCP schemas are *generated* from verb
  signatures and a CI gate asserts CLI defaults equal verb defaults.
  Drift became structural, not disciplinary. {#verbs}

rel: implements -> [[system_design_review#requirements]]

## Data model deep-dive {#data-model}

**I:** Why roaring bitmaps? Why not just Postgres + pgvector, or a graph DB?

**C:** The core query shape is set algebra over sparse membership:
`mentions:parser AND defines:parser`, `calls:foo AND NOT imports:legacy`.
A (linkage, concept) pair maps to a roaring bitmap of entity ids; AND/OR/
NOT are bitmap ops — microseconds at 100M memberships, embarrassingly
explainable (`--explain` walks file:line evidence for every membership).
A property-graph DB models this fine but pays pointer-chasing for what is
really columnar set math; pgvector solves the wrong half (dense is the
complement here, not the spine). DuckDB was chosen over SQLite when
catalogs crossed ~100M rows — SQLite chokes on the bitmap-set-ops scale.

Weighted linkages carry evidence rows (path, line) — the trust mechanism.
Concepts are namespaced (`keyword/`, `import/`, `kind/`) so auto-extracted
noise can be marked and hidden non-destructively (`prune-noise` marks, only
`--drop` deletes).

Dense side: Lance holds vectors keyed by entity id, partition-routed
(memory vs code partitions — the wrong-partition family of bugs is the
single most recurrent defect class in the project's history). Dual-write
discipline: every catalog purge must drop Lance rows inline or orphans
leak; audited and enforced. {#dual-write}

## Retrieval ranking {#ranking}

**I:** A query comes in from a prompt hook. Walk me through ranking.

**C:** The stack, in order of what actually paid:

1. **BM25 over a content forward-index** (`content_rank`) — terms from
   docstrings, bodies, identifiers. The single biggest lesson: the main
   ingest path once content-indexed *nothing* for 43-83% of entities and
   every retrieval number was invalid. "The main path must exercise core
   mechanisms" is now a design rule, not a preference.
2. **Structural fusion** — docstring/code linkage boosts, coverage³,
   co-mention². Only signals that change the candidate *set* moved
   recall; rerank-position signals mostly washed. Lead position wins.
3. **Dense ANN + cross-encoder rerank** — pool of 10 beats 30; bodies
   (not filenames!) must be what gets encoded — code vectors accidentally
   encoding paths cost 0.34 MRR before it was caught (0.63 → 0.97).
4. **RRF fusion is default-OFF for memory recall** — measured: dense-only
   0.848 MRR vs fused 0.794; fusion helps recall@k, hurts precision@1.
   Defaults follow measurement, not architecture aesthetics.
5. **Grep floor** — an index miss degrades to ranked literal grep, never
   to nothing, and fallback hits are *learned* into the graph (protected
   `query/<term>` concepts), so the index improves from its own misses.

Rejected with data: degree-2 graph walks (5x worse), pseudo-relevance
feedback (worse), phrase layer (identical hit@20 to its components),
LatticeDB as a backend (index fine, scoring broken). {#negatives}

rel: evidence-for -> [[PERFORMANCE]]

## Working memory and the helix {#stm}

**I:** Sessions are stateless. How does "what was I doing" survive?

**C:** Three tiers:

- **STM rings** — append-only JSONL per session, written by harness hooks
  (prompt, tool use, stop). Passive capture is the design center:
  voluntary channels measured ~0 uses/session, so capture binds to
  mandatory artifacts. A per-prompt *composite* renders the focus graph
  into the context under its own token budget.
- **Durable memory** — GMD documents (anchors + typed `rel:` edges),
  ingested into a memory partition; save-state compiles STM into a
  handoff memory + promotes a digest, filed under the active subject.
- **Helix (temporal layer)** — when retrieval touches a concept whose
  last STM touch is older than the working window, the bundle carries a
  point-in-time snapshot: *"last worked 77d ago; then: <what>; neighborhood
  then: <files>"*. Every emission is telemetry-logged; that readership
  signal decides whether the next phase is cheap mutable edge-timestamps
  or a versioned (prolly-tree) store. The instrument itself had to be
  debugged: the always-on hook retrieves what the prompt mentions, which
  the ring just recorded — self-suppressing by construction until the
  current session was excluded from last-touch and stale *neighbors*
  became annotatable. Measure the instrument before trusting it. {#helix}

## Concurrency and failure modes {#failure}

**I:** What breaks, and what did you do about it?

**C:** The honest list:

- **Memory pressure (jetsam).** A resident embedder + a fat ingest =
  SIGKILL on macOS. Fix: models out of process (shared hub workers),
  batched purges, jetsam-safe vacuum. Daemon RSS 695→203MB.
- **DuckDB secondary-index drift.** `INSERT ON CONFLICT` races and
  phantom UNIQUE-index leaves SIGABRT the daemon. Mitigations: repair
  index on startup, `repair-index` triage command, and one catastrophic
  store rebuilt 82GB→46MB after a corrupt zonemap — behind a health
  check that read green while serving nothing. Health checks must probe
  the serving path, not the process.
- **Watchdog false positives.** Ping-only liveness with a 0.5s timeout
  SIGKILLed daemons that were merely busy — a crash loop diagnosed from
  timestamps matching restarts. Fix: dead-vs-busy distinction (pid
  check), grace misses, and making the long op yield the lock.
- **Stale processes serve stale code.** The daemon serves what it
  imported at start; the MCP server is a per-client stdio process. Deploy
  is not release until the process is respawned — `restart --relaunch`
  verifies the new pid AND version.
- **Big ops starving always-on surfaces.** A partition merge once blew
  every prompt-hook deadline. Fix: lock-yield batching, async job API,
  replica-first hook reads, hub maintenance pause. The invariant is now
  stated as a rule: big ops must not block the always-on surfaces.

## Evaluation {#eval}

**I:** How do you know any of this works?

**C:** Fixed benchmarks, production path, adversarial re-runs:

- CodeSearchNet code retrieval, *production ingest path*: MRR@10 0.961
  (python) vs CodeRankEmbed 0.959 — defended over the bespoke 0.972
  because the bespoke harness bypassed ingest and hid four defects.
  JS: 0.939 vs 0.916 — the symbolic margin grows with cross-file density.
- Proactive retrieval (MemAware): scan-prompt is the weak surface —
  0.149 → 0.241 after body indexing + rerank tuning; ceiling is recall.
- Doc-doc similarity: co-occurrence pair overlap AUC 0.929 vs dense
  0.815 — dense has no discriminative range inside one project's jargon.
- Perf: content_rank 260ms → 21ms (cached derived constants, not index
  work); GMD ingest 9.8x via weight-aware bulk linking, byte-identical
  graph as the proof of equivalence.

Negative results get memorialized with the same care as wins — they are
the fence posts that stop re-litigating settled questions. {#eval-negatives}

## Trade-offs I'd defend {#tradeoffs}

**I:** Steel-man the criticisms.

**C:**
- *"Just use embeddings."* Dense alone lost on every within-project
  comparison we ran, and cannot answer "why did this match" — the
  explainability contract (`--explain` → file:line) is load-bearing for
  agent trust.
- *"A graph database would be cleaner."* The query mix is set algebra +
  BM25 + ANN. The bitmap/DuckDB hybrid keeps all three columnar and
  keeps the whole system embeddable in a laptop process tree.
- *"The daemon adds operational surface."* It does — watchdogs, slots,
  relaunch semantics. It bought the one non-negotiable: reads never
  block on writes. Every attempt to do without it (direct opens,
  in-process second connections) died on DuckDB's lock model.
- *"Two storage engines (DuckDB + Lance) is complexity."* Yes, plus a
  dual-write discipline. The alternative — one engine doing both — was
  evaluated (LatticeDB) and failed on scoring correctness.

## Evolution {#evolution}

**I:** Next 12 months?

**C:** The helix decides its own future: if the annotation readership
signal fills, edge-time gets a real versioned store (prolly/Merkle search
tree — which also subsumes replica diff/merge, today's hand-rolled
id-remap union). Concept canonicalization across partitions (`canon`)
grows into cross-codebase concept matching — the same concept recognized
in N repos. And every new capability lands as a verb, so the CLI, MCP,
and any future surface (HTTP?) stay one signature wide.

rel: depends-on -> [[system_design_review#helix]]
rel: motivates -> [[system_design_review#verbs]]
