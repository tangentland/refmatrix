---
gmd: "0.1"
id: exploration-adaptive-memory-budget
title: "Exploration: adaptive memory storage and retrieval, getting more than the load limits into the agent's context"
tags: [exploration, memory, recall, budget, memory-index, hooks, adaptive]
metadata:
  node_type: exploration
  status: in-progress
  created: 2026-10-07
---

# Exploration: adaptive memory under the load limits {#root}

**Date:** 2026-10-07
**Status:** Research Complete. Decisions are pending with the user ([[#decisions]]).
**Motivation:** The user, 2026-10-07: "we need a way to automatically optimize memory storage and
retrieval to make it adaptive to keep more than the byte limit". The agent receives memory through
several budgeted channels, and most of what the store holds never reaches it. The goal is to let
usage, not fixed rules, decide what fills each channel, and to fit more into each one.

rel: related-to -> [[project_memory_compile_shipped]]
rel: related-to -> [[project_memory_bridge_never_ran]]
rel: related-to -> [[exploration-concept-similarity-cull-merge]]

## Background: the channels and their limits {#background}

| channel | limit (unit) | size today | selection rule | adaptive? |
|---|---|---|---|---|
| `MEMORY.md` index | the loader cuts at ~24.4 KiB **chars**; rmx folds to `MAX_INDEX_CHARS=24000` (`memory_index.py:40-63`) | **22,812 chars, 137 lines (95%)** | fixed type order (feedback → reference → project), alphabetical; oldest projects **by file mtime** folded first (86 folded); feedback never folded | no |
| SessionStart recall (`--session-start --k 10`) | k=10, 10 s; **no size budget** | **26,567 B** (10 full bodies + metadata) | newest-first, 7-day window | no |
| per-prompt recall (`--stdin-json --k 5`) | k=5, 5 s; **no size budget** | **16,347 B** on a sample prompt | dense cosine, no fusion or rerank | no |
| scan-prompt | 2,000 tokens (estimate) | ~1.6k tokens | symbols in the prompt + periodic composite | partly |
| PreCompact recall (`--recent --since 1h --k 20`) | k=20; no size budget | 0–~50 KB | recency | no |
| resume `focus context --top 15` | top 15 | — | STM score (decay 0.85/turn) | yes (STM only) |

{#channels}

**The harness limit decides what the agent actually reads.** Hook output above roughly 10 KB is
replaced by a ~2 KB preview with a file pointer. That is visible all through this session: every
recall-hook output arrived as "persisted-output … Preview (first 2KB)". So SessionStart delivers
about **1 of its 10** hits and per-prompt recall about **1 of 5**. The other 80–90% is produced,
paid for, and never read. The ~10 KB threshold is inferred from behaviour; measuring it is the first
step of any option below. {#harness}

**The corpus:** 160 project, 50 feedback, 10 reference, 32 save-state and 66 impression files,
~976k chars. Inline in the index: 50 + 10 + 74. Reachable only through recall: 86 folded projects,
66 impressions and 31 older save-states. {#corpus}

**There is no usage signal.**
- Memory rows carry only `gmd_content_hash` and `gmd_pass2_done`. No recall count and no
  last-recalled anywhere in `src/`.
- `query.log` has 0 memory-recall rows.
- `helix.log` logs concept anchors, not memory ids.
- The only "age" is file mtime, which moves on edit, not on use.

Every selection rule is therefore recency or a hand-fixed order: nothing can learn. {#no-signal}

**Adaptive pieces that already exist:**
- STM decay and promotion (`stm.py`, `promote.py`);
- digest graduation (`handoff.py:308`);
- helix staleness;
- **memory compile**, with 39 subject nodes and `part-of` edges, run by hand. `recall --subject`
  walks them, but the index does not use them.

{#exists}

## Option A: count usage first (the signal everything else ranks on) {#option-a}

- **Record each recall hit**: `{memory id, channel, rank, ts}`, as a `query.log` kind
  `memory_recall` row.
- **Keep `recall_hits` and `last_recalled`** in memory metadata, updated through the learn-queue
  pattern (never inline under the lock).
- **A "used" signal**: the memory's name or an anchor appears in a later `rmx memory get`, in a
  focus note, or in the agent's subsequent tool calls (the STM ring already sees refs).

This is cheap, and without it every "adaptive" policy is recency in disguise. {#option-a-body}

## Option B: budget every hook by what the harness shows (pack, don't truncate) {#option-b}

`memory recall --max-chars N` (N under the preview threshold, ~9,000) packs greedily:
- the hook/tldr line for every hit;
- full bodies only for the top 1–2;
- a pointer (`rmx memory get <id>`) for the rest.

`k` becomes a consequence of the budget instead of a constant. The same knob applies to SessionStart
and PreCompact. A per-channel record of produced vs delivered bytes lets the budget track the
harness. This is the biggest immediate gain: the same bytes carry 5–10x more memories, because hooks
replace bodies. {#option-b-body}

## Option C: value-ranked index fold {#option-c}

- Replace `key=e.mtime` (`memory_index.py:275`) with a score: Option A's usage with time decay, plus
  subject centrality, plus recency.
- Order entries by score within type, not alphabetically.
- Allow low-value feedback to fold behind a floor (today an all-feedback index would hit
  `STILL OVER`).
- Run the index on every memory write (the ingest-gmd bridge) and at SessionStart, not only at
  save-state.

{#option-c-body}

## Option D: subject-tiered index (more memories per line) {#option-d}

- Render one line per compiled subject, e.g.
  `subject X: N memories — rmx memory recall --subject X`.
- Keep only each subject's top-scoring members inline.
- That compresses ~300 entries into ~40 lines, and the freed chars carry more hooks.
- This depends on memory compile running automatically (today it is manual `--apply`). It inherits
  the concept-similarity exploration's merge and cull work.

{#option-d-body}

## Recommendation {#recommendation}

**B first.** It is mechanical, it needs no new signal, and it turns today's mostly-unread 26 KB and
16 KB into payloads the agent actually sees. **A alongside it**, because it is cheap and starts
accumulating the data C needs. **C** once A has a few weeks of counts. **D** after memory compile
runs on a schedule (plan-17's nightly tick is the natural home). One honest caveat: "used" is
hard to observe. A starts with "returned and then fetched or cited", and the plan should say how
the definition will be validated. {#rec-body}

## Decisions for the user {#decisions}

- **d-1. Order:** B + A now, with C and D after data accrues? Or is D (subjects) wanted sooner?
- **d-2. Budget target:** pack each hook under the harness preview (~9k chars; measure the exact
  threshold first), or set budgets per channel by hand?
- **d-3. Feedback folding:** may low-value feedback memories fold out of the inline index behind a
  floor, or is feedback always inline?
- **d-4. Scope:** a new plan (memory budget and adaptivity), with D scheduled through plan-17's
  nightly tick?

## Transition Summary {#transition-summary}

**Status:** IN PROGRESS. User decisions, 2026-10-07:

- **d-1:** B (budget packing) + A (usage log) + **D (subject-tiered index) now**, not deferred.
  D needs memory compile to run on a schedule, which means plan-17's nightly tick, or a
  compile-on-save step if that tick lands later.
- **d-4:** a new plan, **plan-19 (adaptive memory budget)**.
- **Order:** it follows the remedy merge and is the first track after it.
- **d-2 / d-3:** settled in the plan's spec. The default is to pack under the measured harness
  preview, with feedback folding behind a floor.
