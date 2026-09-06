---
gmd: "0.1"
id: 0001-intuition-lance-integration
title: "ADR-0001: Intuition memory layer + Lance vector backend"
tags: [adr, memory, lance, dense]
---

# ADR-0001: Intuition memory layer + Lance vector backend {#root}

rel: part-of -> [[adr-0000-adr-overview]]
rel: related-to -> [[adr-format]]
rel: specifies -> [[intuition-style-hooks]]

Status: Proposed
Date: 2026-05-27
Authors: tholley, Claude Opus 4.7
Governs: MemoryEntity, MemoryContent, ReinforcementLinkage, LanceVectors, HybridScorer
Cross-references: project_queued_work, project_daemon_arch, project_csn_eval_baseline

## Context {#context}

Two ongoing threads converge:

1. **Lance integration was queued (phase 4 of DuckDB+Lance migration).**
   Phases 1–3 landed (DuckDB read-view, native catalog, BLOB-packed
   bitmap fragments). Phase 4 — Lance for dense vectors — was deferred
   "until dense embeddings come back in a hybrid story." That moment
   is now.

2. **`~/claude_tools/intuition` runs as a parallel memory layer for
   Claude Code.** It's a SQLite-backed MCP server with FTS5,
   sentence-transformers embeddings via FAISS sidecars, concept
   graphs, hooks for SessionStart/UserPromptSubmit/PreCompact/Stop,
   and a 22 KB README of features. Functionally it overlaps with
   rmx by ~80%: observations are documents, concepts are concepts,
   `observation_concepts(score)` is a weighted linkage. The pieces
   rmx is missing for full overlap are (a) raw-content storage on
   memory rows, (b) dense-vector retrieval, (c) explicit reinforce/
   contradict semantics that amplify scoring weight.

The user wants intuition's role absorbed into rmx so there's one
substrate, with memories in their own partition so they stay
isolated but can be fused across partitions when scoring. CLI only —
no MCP server expansion. Lance enables the semantic-recall surface
intuition relied on FAISS for.

Prior context lives in [[project-queued-work]], [[project-daemon-arch]],
and the csn-eval baseline showing the symbolic stack already beats
CodeRankEmbed on csn_python *without* embeddings. Adding embeddings
should be additive (fused via RRF), not a replacement.

## Decision {#decision}

Land intuition's memory-layer capabilities natively in rmx, backed
by a new Lance-based vector store. CLI-only. Three components:

```
MemoryEntity(entities):
    kind: 'memory'
    name: str               # short slug, unique-per-partition
    canonical_name: str     # standard identifier expansion
    path: nullable str      # optional source pointer
    content -> MemoryContent  # sidecar 1:1

MemoryContent (sidecar table):
    entity_id: int64 PK FK entities(id) ON DELETE CASCADE
    content: text
    mtype: str              # 'observation' | 'note' | 'decision' | 'feedback' ...
    tags: json text         # ["..."]
    metadata: json text     # {...}
    created_at: timestamp
    updated_at: timestamp

ReinforcementLinkage(entity_links):
    linkage: 'reinforces' | 'contradicts' | 'recalls' | 'informs'
    concept_id: int          # target concept entity
    entity_id: int           # source memory entity (or any other kind)
    weight: float            # signed contribution; reinforces > 0, contradicts < 0
    -- evidence rows in linkage_evidence carry the quote/citation
```

```
LanceVectors:
    layout_root: <root>/.refmatrix/vectors/<partition>/
    dataset_per_kind: memory.lance, code.lance, doc.lance, concept.lance
    schema: id int64, vector fixed-size float32[D], updated_at timestamp
    upsert_vectors(entity_ids, vectors)
    ann_search(query_vec, k, kinds=None) -> [(entity_id, score)]
    drop_for(entity_ids)
```

```
HybridScorer:
    -- existing bm25_docstring30_cov30_cm20 stack
    + reinforcement_signal: per-concept sum_{m in memories}(
            weight(m -> concept) * decay(now - m.created_at)
      )  # signed, capped
    + dense_signal: fuse_rrf(ann_hits, symbolic_hits, k=60)
    feature weights: env-configurable; default ablation shipped with eval
```

CLI surface (no MCP):

```
rmx memory add <name> --content '...' [--type observation] [--tags ...]
rmx memory get <name|id>
rmx memory search <query> [--partition intuition] [--cross-partition]
rmx memory recall <concept-or-text> [--k N]  # hybrid retrieval
rmx memory link <src> <linkage> <concept> [--weight W] [--evidence ...]
rmx memory forget <name|id>
rmx memory import-sqlite <path-to-intuition-db>
rmx memory embed [--rebuild] [--kinds memory,code,doc,concept]
```

Memory partition defaults to `intuition`. Cross-partition fusion uses
the existing partition_fuse infrastructure ([[project-partitions-canon]]).

Hooks ported from intuition land as documented `.claude/settings.local.json`
templates under `docs/hooks/`, not auto-installed.

## Phased build {#phased-build}

**Phase A — Lance foundation** (~1.5–2 weeks).
- Add `pylance` and `sentence-transformers` to optional deps
  (`[dense]` extra). Keep core install lean.
- `src/refmatrix/vectors.py`: `LanceVectorStore` with the API above.
  One `.lance` dataset per entity-kind per partition.
- `Store.upsert_vector(entity_id, vector, kind=...)` + `Store.ann_search(...)`
  wrappers that route through `LanceVectorStore` lazily so SQLite-only
  installs still work.
- Embedding pipeline: per-kind extractor → text → model → vector.
  Default model: `BAAI/bge-small-en-v1.5` (384-dim, fast on CPU).
- Daemon op handlers: `embed`, `ann_search`. Daemon spins the embedder
  once at startup; queries reuse it. Disabled when `[dense]` extra
  not installed (gracefully degrade — symbolic-only retrieval).
- `rmx embed` CLI: walk entities, emit vectors. Incremental: skip rows
  with up-to-date `vectors_updated_at` (new entities table column).
- Hybrid scorer: extend the scoring stack to optionally include
  `dense_signal` fused via `fuse_rrf`. Feature off by default; on via
  `--dense` flag.
- Eval gate: re-run `bm25_docstring30_cov30_cm20` on csn_python with
  and without `--dense`. **Symbolic-only must not regress.** Hybrid
  may help or hurt — record the number either way.

**Phase B — Intuition core** (~1 week).
- Schema migration: `memory_content` table; ON DELETE CASCADE from
  `entities`. Migration is idempotent; existing stores get it on
  next daemon start.
- Linkage types `reinforces`, `contradicts`, `recalls`, `informs`
  added to the default linkage seed in `Store.init()`.
- `rmx memory` CLI subgroup (see surface above). Every op routes
  through the daemon (already standard for mutations).
- Reinforcement scoring feature: new scoring-stack component
  computing the per-concept Σ reinforces.weight − Σ contradicts.weight
  with exponential time decay. Feature weight is env-configurable;
  default tuned on a held-out memory benchmark we'll synthesize as
  part of this work (10–20 paired memory/concept pairs, manually
  labeled).
- Memory partition mechanics: `--partition intuition` flag honored.
  Cross-partition fuse defaults on for `rmx memory recall`.

**Phase C — Hooks + migration** (~½ week).
- `docs/hooks/intuition-style-hooks.md`: copy-pasteable
  `.claude/settings.local.json` payloads that drive the memory hooks
  via `rmx memory ...`. Hook payloads:
  - SessionStart: `rmx memory recall --session-start` (injects top-k
    memories matching the session's prior context)
  - UserPromptSubmit: `rmx memory recall --prompt "$PROMPT" --k 5`
  - PreCompact: `rmx memory recall --recent --since 1h`
  - Stop: `rmx memory add --auto-extract` (LLM-side; details TBD)
- `rmx memory import-sqlite`: reads `.memory.db` (intuition's schema),
  maps rows → entities + memory_content + linkages. Preserves
  `observation_concepts.score` as linkage weight. Preserves
  `concept_relations.weight` + `relation_type`. Preserves
  `concept_aliases` via existing canonical_name machinery.
  Embedding vectors imported through Lance if `[dense]` installed
  (BLOB → numpy → upsert_vector).

## Consequences {#consequences}

- **Positive:** one substrate, one mental model. The existing rmx
  scoring stack already beats CE on symbolic — adding dense recall
  is additive, not a replacement. Memories live in a dedicated
  partition so noise from `~/claude_tools/intuition`-style auto-
  capture doesn't pollute code/doc retrieval. Lance opens the door
  for any future dense-embedding work (hybrid retrieval on code,
  not just memories). CLI-only keeps the surface small and
  scriptable.

- **Negative:** wheel size grows when `[dense]` is installed
  (sentence-transformers + torch backbone is ~500 MB). Mitigated by
  optional extra. Lance file layout multiplies on-disk artifacts:
  `vectors/<partition>/<kind>.lance` per kind per partition. Each is
  cheap when empty but the dir tree gets busier.

- **Negative:** signed-weight reinforcement is a novel scoring
  feature; needs its own benchmark to tune. Without that benchmark
  we'd be guessing at the decay constant + feature weight.

- **Neutral:** explicit `reinforces`/`contradicts` linkages mean
  callers must actively assert the relationship — there's no
  inference of reinforcement from "two memories shared a concept."
  Cleaner semantics; more work for the writer.

- **Neutral:** daemon embedder process state grows by ~200 MB
  resident for `bge-small-en-v1.5`. Acceptable for one long-lived
  daemon per store; not for a re-spawn-per-call pattern.

## Alternatives considered {#alternatives-considered}

1. **Keep intuition as a separate MCP and have rmx import it on
   demand** — rejected. Two substrates, two databases, two query
   surfaces. The whole point of consolidation is to make memory
   reinforcement a first-class signal in retrieval, which it can't
   be when it lives in a foreign process.

2. **Skip Lance, embed via FAISS sidecars like intuition does** —
   rejected. FAISS is a great library but storing one .faiss file
   per partition per kind is an ad-hoc layout. Lance gives us
   versioned columnar storage with ANN index, zero-copy mmap into
   numpy, and a path toward incremental rebuilds. Lance was already
   queued as the long-term backing store; this just brings the
   timeline forward.

3. **Defer dense embeddings entirely; ship symbolic-only memory
   integration** — considered. We can technically run intuition's
   role on rmx without embeddings, leaning on identifier expansion +
   FTS5 + the reinforcement signal. But intuition's value to the
   user has been semantic recall ("show me what I learned about X
   even if I phrase it differently this time"). Without dense recall
   the migration is a feature regression. Defer-able only if Lance
   itself slips materially.

4. **Derive reinforcement from shared concepts instead of explicit
   linkages** — considered. Auto-deriving "memory A reinforces
   memory B if both link to concept C with high score" is cheap and
   needs no user input. Rejected because *contradicts* has no
   symmetric heuristic — sharing a concept can mean either
   reinforcement OR contradiction, and the system has no way to
   tell. Explicit linkages preserve the signed semantics.

5. **Drop the secondary index on `entity_links` instead of adding
   periodic repair** — out of scope for this ADR; tracked under
   [[project_daemon_index_drift_recurrence]]. Mention here only
   because reinforcement linkages will *increase* entity_links churn
   and may stress the index more. The 1.5.3 upgrade + option D
   defense from commits ad06f41/96ffe47 are presumed sufficient; if
   reinforcement traffic exposes a new drift surface, dropping the
   index becomes Plan B.

## Open questions {#open-questions}

- **Embedding model choice.** `bge-small-en-v1.5` is the default
  proposal but `gte-base` and `e5-small-v2` are alternatives.
  Decision deferred to Phase A eval.
- **Auto-extraction policy for Stop-hook memory writes.** Should
  the hook write *every* prompt as a memory, or selectively?
  Intuition leans toward "every session has a sidecar". Open.
- **Cross-partition weight decay.** When a code partition's
  scoring borrows the memory partition's reinforcement signal,
  should the borrowed weight be discounted? Probably yes (a memory
  in another store is less trustworthy by default) but the rate is
  open.

## Land plan {#land-plan}

This branch (`feat/intuition-lance`) holds the entire work. Master
stays at the post-option-D state. Final merge is one squash commit
landing all three phases plus the ADR. Phase boundaries are commits
on the branch; squash on land. No partial intermediate releases.
