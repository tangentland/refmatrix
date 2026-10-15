---
gmd: "0.1"
id: handoff-012-r10-r13-remedies-0770-0772-storage-explore
title: "Session Handoff for refmatrix"
tags: [handoff, session]
metadata:
  node_type: handoff
---

# Session Handoff for refmatrix {#root}

Date: 2026-10-07/08 (session 9ff85914). Prior handoff archived at
`workflow/past_handoffs/011-r6-r9-remedies-0763-plans-17-23_2026-10-07.md`.

rel: supersedes -> [[handoff-011-r6-r9-remedies-0763-plans-17-23]]

## State {#state}

- **Branch:** `bsd-r1-remedy`. It is now IDENTICAL to `master` (fast-forwarded each step). There
  is no branch switch in this tree: another Claude session (pid 4405) lives here.
- **Deployed:** 0.77.2 on the hub and all 8 daemons, each relaunched and verified. The hub runs
  one embed worker and one rerank worker.
- **Pushed:** NO. `master` is about 114 commits ahead of `origin/main`. The auto-mode classifier
  blocks the push; the user runs
  `git -C /Users/tholley/claude_tools/refmatrix push origin master:main`.
- **Stores:** every project partition is re-derived at 0.77.x ("version drift only").
  sessions-refmatrix is repaired.

{#state-body}

## What this session did {#did}

1. **ch-bsd r10-r13 on the rerank-budget remedies.** r10 DIRTY 1B, r11 DIRTY 1B, r12 DIRTY 0B,
   r13 0B with no blocker. Summaries: `remedy-bsd-r9..r12-*.md`.
   - Context reranks open their own hub connection (`fork`).
   - Private workers are `reserve()`d, warm in the background, and are `retire()`d at adoption and
     shutdown.
   - The hub's `info(nowait)` is lock-free.
   - An unknown partition answers empty, or raises for context.
   - Embed ops serialize on their own lock.
   - A context answer from the writer is unreranked.
2. **0.77.0:** merged (`5a085be`, conflicts resolved to the branch side, as approved) and deployed.
   Fleet `reingest --force`; the refmatrix and cliquedb embeds were redone with `--batch 64`
   (bug-097).
3. **bug-098, "where are refmatrix's stamps":** a WRITER-side partition race.
   - Two cooperative ingests kept their `with_partition` binding across `_yield` (the lock
     release), and three lock-free ops (`_store_health` on every ping, `memory_score`, and the
     recall prefilter) re-bound the shared writer.
   - 0.77.1 fixed all of them. `tests/test_ingest_partition_yield_race.py` was RED with 30 rows
     crossed and the writer re-bound 92x.
   - sessions-refmatrix was backed up, its stray rows forgotten, and it was re-indexed from its 77
     cards.
   - The fix was confirmed on a throwaway store with 80 interleaved job lines.
4. **0.77.2:** `rmx derive unstamp PASS` (daemon op `derive_unstamp`). Used to remove the two stray
   `ingest`/`semantic` stamps from sessions-refmatrix.
5. **Exploration** `docs/architecture/explorations/storage-concurrency-redesign.md`, options A-E:
   - A: partition-scoped handles on per-op cursors (recommended first).
   - B: one partition per store.
   - C: DuckDB read-only over Lance.
   - D: Vortex roaring. Checked on `vortex-data` 0.88: the format and DuckDB work, but no roaring
     encoding is reachable from Python.
   - E: viascope's BSI sidecar. Measured: queries are sub-ms; the build pays a per-row Python tax.
   - The user's evidence for "slow Python bitmaps" is cliquedb/thiquet (PL/pgSQL loops).

{#did-body}

## Next {#next}

1. **Pushed** 2026-10-14 (`1452875..a434f51`). Wave 0 runs on `wave0-spec-reviews`.
2. **Wave 0 (docs)** per `workflow/plan-of-plans.md`: plan-16 rev 5 plus its spec review, and spec
   reviews of plans 17/19/21/22/23. Option A of the exploration overlaps plans 22/23; fold it in
   there.
3. **Wave 1:** plan-23 (the bounded-write harness) first, then 17.1/17.2, 19.1/19.2, 21.1 and
   22.1-22.3.
4. **Open bugs:**
   - bug-096: `rmx reingest` exits 0 on a failed step.
   - bug-097: a fixed 256-row embed batch against the 45 s op timeout under load.
5. **Needs the user's time:** the 19.5 hook-limit probe, and the 20.1 gold-label review.

{#next-body}

## Open, not forgotten {#open}

- **viascope (done 2026-10-14):** the 40 stray doc rows in `sessions-viascope` were forgotten
  after a backup (`viascope/.refmatrix/backups/catalog.read.pre-sessions-forget-20261014-105529.duckdb`,
  306 MB); memories 155 before and after. The backup can go once the user is satisfied.
- **Exploration measurements 1-7** are unmeasured. Option D's next step is a Rust-encoding spike,
  if the user wants D costed.
- **The full suite** stays unrun until bug-088 isolates it. Families ran with `RMX_MODEL_SOCK`
  isolated, and the live-socket recorder stayed at 145.
- **The bug-098 backup** `catalog.read.pre-bug098-repair-*.duckdb` (712 MB) was deleted 2026-10-14 by
  the user's OK, and so was `vectors-sessions-refmatrix-20261008-165958/` (268 KB) from the same
  repair. `.refmatrix/backups/` is empty.

{#open-body}
