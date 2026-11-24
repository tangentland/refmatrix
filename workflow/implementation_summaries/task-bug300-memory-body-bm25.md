---
gmd: "0.1"
id: impl-task-bug300-memory-body-bm25
title: "bug-300: a memory's body is searchable by BM25, and an empty fuse leg is said"
tags: [implementation-summary, bug-300, recall, fuse, bm25, memory, gmd-blocks]
metadata:
  node_type: implementation-summary
  status: complete
  created: 2026-11-23
  author: green-b300
---

# bug-300: a memory's body is searchable by BM25 {#root}

rel: implements -> [[task-bug300-memory-body-bm25]]
rel: derives-from -> [[b300-r0#join-choice]]
rel: implements -> [[task-bug300-memory-body-bm25#r1-scope]]

## Why {#why}

`memory recall --fuse` runs `Store.content_rank(terms, kinds=["memory"])` as its symbolic leg. A
memory entity's own `mentions` are its title and tag words; its body words hang off its GMD block
nodes (`<memory-id>#<anchor>`, `kind=concept`), which `kinds=["memory"]` filters out. On the
LongMemEval store the leg returned [] for 40 of 40 questions, so `--fuse` equalled plain recall on
120 of 120 rankings (T0.6), and nothing said so. {#why-body}

## What shipped {#shipped}

| where | what |
|---|---|
| `store.py` `content_rank` | when `kinds` includes `memory` and excludes `concept` (L199), the memory's block postings are merged into its own: tf = own + blocks per concept, dl = own length + every block's length. The length holds for every memory scored on that path, including one that matched only on its own postings (fold `8cd15f00`, L209 / bsd-b300 r1 b-1). N, avgdl and df stay the partition's. Block ids are never returned on this path. |
| `store.py` `_memory_block_postings` | ONE grouped SQL pass: `mentions` rows of block nodes for the query concepts, joined to the memory named by `split_part(b.name, '#', 1)` (same partition, `m.kind='memory'`), `GROUP BY m.id, concept_id`, returning the weight sum and the NULL-weight count (resolved by `RMX_NULL_TF`, as a memory's own postings are). |
| `store.py` `_memory_block_doclen` | `memory_id -> summed block length`, built from the existing `_mentions_doclen` cache plus one `entities` scan for the tie (never a second pass over the 12.8M LongMemEval block postings). Cached per (instance, partition); dropped by `_invalidate_content_rank_caches`, with the same one-flush staleness contract as the other BM25 caches (m-1, accepted under L209). |
| `store.py` `_MEMORY_BLOCK_JOIN` | the one join both helpers use: the block name prefix, never `part-of` and never `LIKE m.name || '#%'`. An orphan block or a doc's block joins nothing. |
| `recall.py` `hybrid_memory_recall` | new `warnings` kwarg; when the symbolic leg returns nothing (no content term, no match, all stopwords) it appends `fuse: symbolic leg empty (...)` (`FUSE_LEG_EMPTY` prefix). |
| `daemon.py` `_op_memory_recall` | passes a `fuse_warnings` list; both returns (the reranked early return and the plain return) carry it in `warnings`. |
| `recall.py` `replica_memory_recall` | collects the warning locally and appends it to `ws` only when the replica leg SERVES, so a leg that fails after fusing and hands over to the daemon RPC does not say it twice. |

The verb, the CLI (stderr `# rmx: warning: ...`) and MCP already passed `warnings` through; no
change there. {#shipped-body}

## Scope rule as built (L199) {#scope}

`credit_blocks = bool(kinds) and "memory" in kinds and "concept" not in kinds`. So
`context.py:792/805` (`code, doc, memory, concept`) and `net.py:114` (`kinds=None`) are unchanged:
they already get the blocks as hits of their own. `recall.py` `hybrid_memory_recall` is the only
caller that takes the credit today. {#scope-body}

## R4: cost on the LongMemEval copy {#r4}

Measured 2026-11-23 on a COPY of `/Volumes/littlebig/longmemeval/.refmatrix/catalog.read.duckdb`
(2,437,689,344 bytes) opened by `Store(root, read_only=True)`, partition `longmemeval`, base
`d478752c` src vs GREEN `a448f0bb` src (identical to `a5887fd8`), `content_rank(terms,
kinds=["memory"], limit=60)`; cold = caches dropped first, warm = median of 5. The copy was deleted
after. The worst term is `turn` (199,563 block postings, R0 #counts). {#r4-lead}

| terms | base hits | base cold / warm ms | GREEN hits | GREEN cold / warm ms |
|---|---|---|---|---|
| `turn` (worst) | 0 | 189.0 / 119.9 | 60 | 518.1 / 201.4 |
| `commute` | 0 | 67.0 / 23.5 | 60 | 354.9 / 42.3 |
| `daily commute` | 0 | 73.4 / 37.7 | 60 | 403.4 / 82.1 |
| `work` | 0 | 86.0 / 46.1 | 60 | 429.1 / 104.7 |
| `turn assistant some` | 0 | 264.1 / 227.4 | 60 | 711.5 / 435.2 |

Breakdown for `turn`: the grouped block-postings SQL is 34.6 ms (199,563 block rows -> 19,206
memory rows); the rest of the warm delta is BM25 over the 19,206 credited (memory, concept) pairs
the base never scored, since its leg returned nothing. The cold delta is the one-time cache build
per write batch: `_mentions_doclen` 139.1 ms (239,734 entities; at base this cache was never
built, because the leg had no rows) and `_memory_block_doclen` 114.9 ms (19,829 memories). One
indexed join per query, no per-memory loop. {#r4-breakdown}

## Verification {#verification}

**RED going green.** `tests/test_context_nl_ref.py` + `tests/test_hybrid_recall.py`: 39 passed at
`a448f0bb` (`b300-green-owned.log`) and at `a5887fd8` (with RED `d14d6793`,
`b300-green-owned-d14d.log`), 15 of them RED at base. {#verify-owned}

**Mutations** (each a detached commit off GREEN, run on the local lane on both owned files; logs
`workflow/review-output/b300-mut-<M>.log`): {#mutations}

| M | mutation | failing tests (intended reason) |
|---|---|---|
| M1 | drop the block join (`_block_rows = []`) | 10: AC-1 x3, one-row, lighthouse, one-document, length, AC-2, no-warning (leg ran) |
| M2 | return block nodes (`SELECT b.id`) | 9: AC-1 x3, one-row/no-block, lighthouse, one-document, length, AC-2 |
| M3 | drop the warning | 6: AC-4 on verb/CLI/MCP x2 queries |
| M4 | credit with `concept` in kinds | 1: `_PIN_WITH_CONCEPT` moved |
| M5b | credit with `kinds=None` (`19d85af2`) | 1: `_PIN_KINDS_NONE` moved (`s0042_1` 0.548 replaces `s0042_1#root` at index 4) |
| M6 | dl = memory's own postings only | 1: length test (`s0063_1` before `s0062_1`) |
| M7 | `part-of` join | 9: AC-1 x3, one-row, lighthouse, one-document, length, AC-2, no-warning |
| M8 | `LIKE m.name || '#%'` join | 1: `ferry` credits `s0042_1` |
| M9 | `MAX` instead of `SUM` | 1: one-document (`s0061_1` before `s0060_1`) |
| M10 | credit doc blocks (`m.kind IN ('memory','doc')`) | 1: `ferry` returns doc `s0042x1` |
| M11 | warn always | 1: no-warning test (`daily commute`, fuse on) |

The first M5 (`(not kinds or "memory" in kinds) and "concept" not in kinds`) raised `TypeError` on
`kinds=None`, so it failed for the wrong reason. M5b (`kinds is None or (...)`) replaces it and is killed. 11 of 11 killed.
{#mutations-m5}

**The L209 fold (`8cd15f00`, RED `5d968e6d`).** The owned files gave 42 passed
(`b300-fold-owned.log`). Mutation MB1 (`ed665e9f`) applies the length only when a block
matched, and it is killed: `test_the_length_rule_holds_when_a_memory_matches_only_on_its_own_postings[terms0]`,
`assert [1, 4] == [4, 1]` (`b300-mut-MB1.log`). The 9 guards gave 370 passed (`b300-fold-guards.log`). {#fold-l209}

**Verify set, merged with master `3e4d3b51`** (pre-fold `5d28d2a5`; 289 files: every importer of
`store`, `recall`, `context`, `net`, `daemon`, `verbs`, `mcp` plus the 9 guards, in 4 lane batches):

| batch | log | result |
|---|---|---|
| 0 | `b300-green-verify-0.log` | 1112 passed |
| 1 | `b300-green-verify-1.log` | 1166 passed |
| 2 | `b300-green-verify-2.log` | 956 passed |
| 3 | `b300-green-verify-3.log` | 1088 passed |

4322 passed, 0 failed. The fold changes `src/` in `content_rank`'s credited branch only, so it was
verified on the owned files and the guards, as the lead directed. {#verify-set}

**Not reached by any test:** the replica leg's warning append in `recall.replica_memory_recall`.
Review it by reading it. {#untested}

## Release note {#release-note}

Retrieval-changing, not store-changing: fused recall (and any `content_rank` caller passing
`memory` without `concept`) ranks memories by their body words; `--fuse` with an empty symbolic leg
now carries a `fuse: symbolic leg empty` warning. No schema, migration, or re-ingest. {#release-body}
