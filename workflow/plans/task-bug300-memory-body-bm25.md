---
gmd: "0.1"
id: task-bug300-memory-body-bm25
title: "Task bug-300: a memory's body is searchable by BM25, so `memory recall --fuse` fuses something"
tags: [task, bug-300, recall, fuse, bm25, memory, gmd-blocks]
metadata:
  node_type: task
  status: approved
  created: 2026-11-24
---

# Task bug-300: a memory's body is searchable by BM25 {#root}

> The user chose option (a), 2026-11-24 (L193). Large change: RED and GREEN in separate hands,
> mutations on the `src/` change, one ch-bsd pass. Read side only; no derive pass module.

rel: implements -> [[bug_registry]]
rel: depends-on -> [[plan-of-plans#rulings]]

## Why {#why}

`Store.content_rank(terms, kinds=["memory"])`, the symbolic leg of `memory recall --fuse`, reads
a memory entity's own `mentions` edges, which hold its title and tag words only. A memory's
body words hang off its GMD block nodes (`kind=concept`), which `kinds=["memory"]` filters out.
On the LongMemEval store (memories titled by session id) the leg returned [] for 40 of 40
questions, so `recall-fuse` equalled `recall` on 120 of 120 rankings (T0.6, 2026-11-24). On the
live store fusion only ever matched titles. {#why-body}

## R0 (RED's first commit, before any test) {#r0}

On a COPY of a live `catalog.read.duckdb` (opened `read_only`) and on a COPY of the LongMemEval
read catalog, establish and record:

1. how a GMD block node is tied to its memory (a `part-of` edge, the entity `path`, the anchor
   name `memory-id#anchor`, or something else), and whether every block of every memory has it;
2. which other `content_rank` callers pass `kinds` that include `memory` (`context.py:792/805`,
   `net.py:114`, `recall.py:149`), and what (a) would change for each;
3. the postings counts: memory self-mentions vs block-node mentions, per store.

If the tie is not total (some blocks cannot be mapped to a memory), stop and report to the
lead before writing tests. {#r0-body}

## Requirements {#requirements}

1. **R1.** When `kinds` includes `memory`, `content_rank` also scores the `mentions` postings of
   each memory's block nodes and credits them to that memory (one score per memory: the block
   postings and the memory's own postings are one document for BM25's tf and length). Block
   nodes are not returned as hits on their own under `kinds=["memory"]`. {#r1}
2. **R2.** A caller that does not ask for `memory` is unchanged (`rmx context` over code and
   docs ranks exactly as before; a test pins one query's ranking at base and after). {#r2}
3. **R3.** When the symbolic leg of `--fuse` still returns nothing, the recall result says so
   (a `fuse: symbolic leg empty` warning through the verb, CLI and MCP), so a no-op fuse is
   never silent ([[claude#no-silent-failures]]). {#r3}
4. **R4.** Bounded cost: R0's block-posting counts give the extra rows per query; the change
   adds at most one indexed join per query (no per-memory loop), measured on the LongMemEval
   copy, before and after, and quoted. {#r4}

## Acceptance {#acceptance}

- **AC-1.** On a fixture store with a memory titled by an id whose BODY contains `commute`,
  `content_rank(["commute"], kinds=["memory"])` returns that memory; RED at base (returns []).
- **AC-2.** `rmx memory recall "<body word query>" --fuse --json` ranks differently from the
  same call without `--fuse` on that fixture, and every hit carries `fused: true`; RED at base.
- **AC-3.** R2's pinned `context` ranking is byte-identical before and after.
- **AC-4.** R3's warning appears when the leg is empty, through the verb, the CLI and MCP.
- **AC-5.** Mutations: drop the block join (AC-1 red); return block nodes as hits (R1's
  "not returned on their own" test red); drop the warning (AC-4 red).
- **AC-6.** Verify set: the edited test files, every importer of `store`, `recall`, `context`,
  `net`, and the 9 repo guards. Release note: retrieval-changing (fused recall and any
  `content_rank` caller over memories rank differently); not store-changing.

## Follow-up {#follow-up}

After merge and deploy, T0.6's `recall-fuse` rows are re-taken on the LongMemEval store (a
lead step, recorded in REPORT.md's history), and bug-301 (punctuation in `content_terms`) is
merged first so the re-take measures both.
