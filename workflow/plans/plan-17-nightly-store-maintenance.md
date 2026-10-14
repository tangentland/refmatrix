---
gmd: "0.1"
id: plan-17-nightly-store-maintenance
title: "Plan 17: the hub keeps every store lean — nightly vector compaction, old-version cleanup, and orphan reaping as a daemon op"
tags: [plan, hub, daemon, lance, maintenance, performance]
metadata:
  node_type: plan
  status: drafting
  created: 2026-10-07
  updated: 2026-10-14
---

# Plan 17: nightly store maintenance from the hub {#root}

> Status: DRAFTING, revised after the 2026-10-14 decision log ([[#rev-2026-10-14]]). The user asked
> on 2026-10-07: "we should add a nightly compaction job to the hub process to keep projects lean
> and fast". Task specs 17.1-17.3 are rewritten against the spec review
> ([[bsd-plan17-spec-review-3104a81]]) and the decisions d2b, d3a-d3e and the close-out
> amendments ([[plan-review-2026-10-14#t3]], [[plan-review-2026-10-14#t8]]). Next: re-review.

rel: motivates -> [[bug_registry#registry]]
rel: related-to -> [[project_daemon_wedge_per_entity_lance_delete]]
rel: related-to -> [[project_bus_retention_global_queues]]
rel: derives-from -> [[plan-review-2026-10-14#t3]]
rel: derives-from -> [[plan-review-2026-10-14#t8]]
rel: derives-from -> [[bsd-plan17-spec-review-3104a81]]
rel: derives-from -> [[bsd-decision-log-review-a192ba2]]
rel: depends-on -> [[plan-23-bounded-write-harness]]
rel: related-to -> [[exploration-storage-concurrency-redesign#option-a]]
rel: related-to -> [[plan-18-duckdb-store-maintenance]]
rel: related-to -> [[task-19.4-keep-derived-layers-current]]

## Why {#why}

Lance commits a new dataset VERSION on every write (append, delete, upsert), and nothing in
refmatrix ever compacts a dataset or removes its old versions. No `compact_files` or
`cleanup_old_versions` call exists in `src/` (verified at `b1c4324`). The cost compounds:

- **bug-085.** Each Lance delete on a 60,944-version `code.lance` cost about 1-2 s. A file re-sync
  issued one delete per entity under `_store_lock`, and the daemon wedged for 7+ minutes per edit.
  The batching fix (0.76.1) cuts the COUNT of deletes; it does not stop the growth.
- **Measured on 2026-10-07**, the one-off compaction of this project's store
  (`workflow/review-output/lance-compact-live.log`):
  - `vectors/` went from 1.3 GB to 105 MB.
  - `code.lance` went from 61,395 versions / 168 fragments / 10,192 deletion files to 1 / 1 / 0.
  - rows, the id set and a vector checksum were identical before and after on all 5 datasets;
  - the whole pass took 27 s with the daemon stopped.
- **The rest of the fleet** (version directories summed per store, 2026-10-07):

| store | vectors | Lance versions |
|---|---|---|
| cliquedb | 1.1 GB | 59,382 |
| viascope | 925 MB | 32,113 |
| cliquet | 75 MB | 4,941 |
| atldb | 24 MB | 1,354 |
| orderly | 9.5 MB | 225 |
| global, thiquet | < 1 MB | ≤ 5 |

- **The first fleet run, by hand, 2026-10-07** (backups `vectors.bak-20261007-precompact`; logs
  `workflow/review-output/lance-compact-{viascope,cliquedb}.log`): viascope went from 925 MB to
  229 MB and cliquedb from 1.1 GB to 62 MB. cliquedb's `concept.lance` was 739 MB with 46,606
  versions (18.9 s to compact, the worst single-dataset time measured). The fingerprints were
  identical everywhere.
- **Regrowth is fast** (spec review [[bsd-plan17-spec-review-3104a81#verified]]): 7 days after the
  hand compaction, this store's datasets held 17-261 versions each and `vectors/` was 150 MB again,
  about 25-37 versions per day per busy dataset.
- **Per-file commits remain (ch-bsd r7 #m-1).** After bug-085, a watch flush still commits one Lance
  version per changed file per kind, even when no id matches. r7 measured a 20-file flush at 10.2 s on
  the 61k-version dataset and 0.2 s after compaction. Nightly compaction bounds it, and task 17.1
  R9 removes the no-match commit itself ([[task-17.1-vectors-maintain-op#r9-no-match-filter]]).
- **Orphan vectors.** After the compaction, 559 of `code.lance`'s 5,495 vectors and 1 doc vector had
  no catalog row. They surface in `search-dense` as `kind ? name ?` hits. `Store.gc_vectors`
  (`store.py:3489`, behind `rmx embed --gc`) reaps them, but nothing runs it, and its orphan rule
  (absent from the BOUND partition + kind) is not the one this plan uses ([[#d3a]]).
  {#why-numbers}

## Design {#design}

- **One daemon op does the work.** `vectors_maintain` is a verb first, with CLI
  `rmx vectors maintain` and MCP parity per the verbs rule. The CLI never falls back to an
  in-process `Daemon(root)` when the daemon does not answer (unlike `embed --gc`,
  `cli.py:10544-10549`); it exits with a named error.
- **What the daemon owns, and what it does not.** `LanceVectorStore` (`vectors.py:46`) caches no
  Lance handle: every method opens `lance.dataset(path)` fresh, so there is no in-daemon handle to
  refresh. The readers that CAN hold a version across a cleanup run OUT of the daemon, lock-free:
  `_replica_memory_recall` (`cli.py:10971`, the prompt hooks), `rmx recall` (`cli.py:10791`) and
  `memory compile` (`compile_memories(_read_store())`, `cli.py:12861`). They are protected by the
  kept pre-compaction version ([[#d3b]]) and by a single retry ([[#d3c]]).
- **Per dataset, one bounded step** (one `_store_lock` hold per dataset through plan-23's
  `bind(batch)` seam and the 23.2 recorder, no queue; [[#d2b]]):
  1. fingerprint (a): rows + an order-independent, per-id subtractable hash of (id, vector);
  2. tag the current version as the run's rollback point ([[#d3b]]);
  3. compute orphans against the WHOLE catalog ([[#d3a]]); refuse above the ratio cap; write the
     orphan list WITH vectors; reap;
  4. `compact_files()`;
  5. fingerprint (b), compared with (a) minus the reaped orphans. A mismatch restores the post-reap
     version, keeps every version on disk, returns `ok:false` and stops the run;
  6. only on a match: `cleanup_old_versions(older_than=<param, default 24 h>,
     error_if_tagged_old_versions=False)`, which never removes a tagged version; then the PREVIOUS
     successful run's tag is released.
- **A restore op** reads an orphan list back and re-upserts the vectors of ids whose entity is in
  the catalog again ([[#d3a]], the #t8 amendment).
- **The hub only schedules**, on its OWN maintenance thread with a step registry (plan-review C6;
  [[#d3e]]), not on the queue-alert thread:
  - stores come from the registered daemon list (the launchd-supervised set, 8 today), injected in
    tests;
  - SERIAL, one store at a time, with a per-store budget; `retries=0` and a single-flight op, so a
    timed-out store is "still running", never re-sent and never overlapped;
  - skips paused stores (`rmx hub pause`), not-running and not-supervised ones, and names them;
  - stamps per (store, step) in `~/.refmatrix/maintain.json`; a (store, step) with no stamp runs a
    DRY RUN only ([[#d3d]]);
  - logs per-store results to `hub.log`;
  - publishes one summary to `global:queues`, which bus retention already bounds.
- **No silent failures.** A failed store is logged and counted in the summary, and the next store
  still runs. A (store, step) that fails N runs in a row alerts once. {#design-body}

## Dependencies {#dependencies}

Wave 1 order ([[plan-review-2026-10-14#t8-wave1]]): 23.0 ∥ 23.4 → 23.2 → 23.1 (+ tick registry)
→ 23.3; after 23.1: … 17.1 → 17.2.

- **17.1** depends on 23.0 (the test sandbox, d1a/d1b), 23.2 (the hold and write-count recorder)
  and 23.1 (the `bind(batch)` seam and per-batch hold timer).
- **17.2** depends on 17.1 and on 23.1's tick-registry step interface.
- **17.3** depends on 17.1 and 17.2 being deployed.
- **Option A revisit** ([[#option-a-revisit]]) is triggered by task 23.4's verdict.

rel: depends-on -> [[task-23.1-queue-and-drain]]
rel: depends-on -> [[task-23.2-lock-hold-fixture]]

## Tasks {#tasks}

| task | what | acceptance (summary; the task spec is authoritative) | depends on |
|---|---|---|---|
| 17.1 | `vectors_maintain` + `vectors_restore` daemon ops, verbs, CLI/MCP: whole-catalog orphans with ratio cap, orphan list with vectors, tagged rollback point, fingerprint gate before any cleanup, every partition, single-flight, no in-process fallback, no-match delete filter, reader retry | `older_than_s=0` → versions 1; default 24 h keeps a fresh version; forced mismatch → restored, old versions on disk; cross-partition entity's vector survives; cap refuses; reap → restore round-trips; a reader opened before the pass scans to the end; a no-match re-sync commits 0 versions; pre-registered mutations FAIL | 23.0, 23.2, 23.1 |
| 17.2 | hub maintenance thread: 03:30 + catch-up, injected roots and clock, serial with per-store budget, `retries=0`, still-running vs failed, (store, step) stamps, unarmed = dry run, step registry, summary | one run per scheduled day; catch-up exactly once; alert interval ≤ 0 still maintains; unarmed store gets a dry run only; a blocking op is received once; zero connects outside the sandbox; pre-registered mutations FAIL | 17.1, 23.1 |
| 17.3 | fleet rollout over the 8 registered daemons: dry run, backup, hand run, arm; measure; latency on refmatrix, cliquedb, thiquet; docs | before/after table per store; latency ratio on a store or clone ≥ 10k versions; 0-version no-match re-sync on a 61k clone; holds < 60 s; one night observed; backups removed only after the user confirms | 17.1, 17.2 deployed |
| 17.4 | `factslog_backup` step on 17.2's tick: once-a-day copy of `facts.log` to `backups/facts.log.daily` (+ `.prev`), lock-free from an open descriptor, skipped when unchanged; the live log is then excluded from Time Machine (added 2026-10-14, user) | one copy per injected day; consistent under concurrent append and compaction; replay-equivalent; unchanged = untouched; loud non-destructive failure; pre-registered mutations FAIL | 17.2, 23.0 |

rel: specifies -> [[task-17.4-factslog-backup-snapshot]]

## Decisions (user, 2026-10-07) {#decisions}

- **d-1. A fixed local time with catch-up** {#d-1}. Default 03:30, overridable by
  `RMX_HUB_MAINTAIN_AT`. A night missed while the machine slept runs at the next wake.
- **d-2. Keep a 24 h window of old versions** {#d-2}: `cleanup_old_versions(older_than=24h)` is the
  production default. The window is a PARAMETER (`older_than_s`, default 86400) so tests can use 0
  and a test pins the 24 h default (spec review #b-2). The rollback point for a quiet dataset is
  the tagged pre-compaction version ([[#d3b]]), not this window.
- **d-3. DuckDB maintenance is plan-18, not part of this plan** {#d-3}
  ([[plan-18-duckdb-store-maintenance]]). Plan-17 covers vectors only; plan-18 joins 17.2's step
  registry.
- **d-4. Orphans are reaped nightly** {#d-4}, automatic and logged, under d3a's definition and the
  ratio cap. An orphan vector's entity is gone from the whole catalog, so it is derived-index data,
  and the orphan list keeps the vectors, so a reap is restorable without a model.

## Decisions (user, 2026-10-14) {#decisions-2026-10-14}

- **d2b. No per-dataset Lance lock now** {#d2b}. 17.1 goes through plan-23's `bind(batch)` seam and
  the 23.2 recorder, and not through the lossy queue. `_store_lock` is what excludes the daemon's
  Lance writers during a dataset step.
- **Option A revisit** {#option-a-revisit}. Under Option A
  ([[exploration-storage-concurrency-redesign#option-a]]) appends would run without `_store_lock`,
  so 17.1's exclusion would no longer hold. Trigger: task 23.4's verdict (#t8-amendments d2b/d2e),
  not "when Option A lands". If 23.4 returns GO for Option A, 17.1 is re-opened to add a
  per-dataset maintenance lock taken by every Lance writer path (`upsert_vectors`, `drop_for`,
  `_drop_lance_for_purge`, `_drop_lance_for_purge_batch`). If NO-GO, the revisit closes.
- **d3a. Orphan = id absent from the WHOLE catalog** {#d3a} (every partition), with the orphan
  list storing the vectors. Amended at close-out: KEEP the orphan ratio cap (refuse a reap above
  it) and add a restore op that reads the orphan list back.
- **d3b. Tag the pre-compaction version** {#d3b}, keep it until the next successful run; cleanup
  never removes it.
- **d3c. Out-of-daemon readers** {#d3c} are protected by d3b; a reader that hits a missing file
  retries once on the current version and counts it. No N-newest retention floor.
- **d3d. No stamp → dry run only** {#d3d}; the real op starts only after 17.3 writes the stamp by
  hand, after its dry run and backup.
- **d3e. Its own step on 17.2's tick** {#d3e} (plan-review C6), not on the queue-alert thread;
  serial stores with a per-store budget; a hub-side timeout is "still running", not "failed".
  Amended at close-out: `retries=0` and single-flight per store.

## Revision (2026-10-14 decision log) {#rev-2026-10-14}

| finding / decision | answered at |
|---|---|
| 17 #b-1 phantom handle | [[#design]]; [[task-17.1-vectors-maintain-op#r4-readers]] |
| 17 #b-2 AC-1 vs 24 h | [[#d-2]]; [[task-17.1-vectors-maintain-op#acceptance]] AC-1a/1b |
| 17 #b-3 gate after cleanup | [[#design]] steps 5-6; [[task-17.1-vectors-maintain-op#r2-order]] |
| 17 #b-4 circular orphan proof | [[#d3a]]; [[task-17.1-vectors-maintain-op#r6-orphans]] |
| 17 #b-5 live stores in tick tests | [[task-17.2-hub-nightly-tick#r3-roots]]; test strategies (23.0) |
| 17 #b-6 unanchored no-match filter | [[#why-numbers]]; [[task-17.1-vectors-maintain-op#r9-no-match-filter]] |
| 17 #s-1 plan-23 misnamed, header | [[#dependencies]]; [[task-17.1-vectors-maintain-op#r3-holds]] |
| 17 #s-2 alert thread | [[#d3e]]; [[task-17.2-hub-nightly-tick#r1-schedule]] |
| 17 #s-3 first-run stamp | [[#d3d]]; [[task-17.2-hub-nightly-tick#r7-unarmed]] |
| 17 #s-4 17.3 latency | [[task-17.3-fleet-rollout#r2-measure]] |
| 17 #s-5 partition=None | [[task-17.1-vectors-maintain-op#r1-verb]] |
| 17 #s-6 store set | [[#design]]; [[task-17.2-hub-nightly-tick#r3-roots]] |
| 17 #s-7 Option A | [[#d2b]]; [[#option-a-revisit]] |
| 17 #s-8 in-process fallback | [[#design]]; [[task-17.1-vectors-maintain-op#r1-verb]] |
| 17 #m-1 stale `daemon.py:5538` | [[task-17.1-vectors-maintain-op#why]] (`_op_embed_gc` is `daemon.py:5792` at `b1c4324`) |
| 17 #m-2 checksum | [[task-17.1-vectors-maintain-op#r2-order]] |
| 17 #m-3 skip cost | [[task-17.1-vectors-maintain-op#r5-skip]] |
| 17 #m-4 `missing` | [[task-17.1-vectors-maintain-op#r7-report]]; [[task-17.2-hub-nightly-tick#r6-report]] |
| 17 #m-5 (store, step) stamps | [[task-17.2-hub-nightly-tick#r1-schedule]], R5 |
| d2b + #t8 revisit trigger (decision review #b-6 item 2) | [[#option-a-revisit]] |
| d3a + #t8 ratio cap + restore (decision review #b-5) | [[task-17.1-vectors-maintain-op#r6-orphans]], R10 |
| d3b (+ tag lifecycle across failed runs) | [[task-17.1-vectors-maintain-op#r2-order]] |
| d3c (+ decision review #m-4 count surface) | [[task-17.1-vectors-maintain-op#r4-readers]] |
| d3d | [[task-17.2-hub-nightly-tick#r7-unarmed]]; [[task-17.3-fleet-rollout#r1-hand-run]] |
| d3e + #t8 retries/single-flight (decision review #s-6) | [[task-17.2-hub-nightly-tick#r4-call]]; [[task-17.1-vectors-maintain-op#r11-single-flight]] |
| decision review #s-7 (restore across 17/22) | [[task-17.1-vectors-maintain-op#r6-orphans]] (list format); [[#open-after-revision]] |
| #t3-fixes (all items) | the rows above |
| #t8-wave1 order | [[#dependencies]]; [[#tasks]] |

## Open after revision {#open-after-revision}

Gaps the decision log does not settle; listed, not decided.

1. **Which registry is 17.2's?** d3e and plan-review C6 put maintenance on "17.2's tick" with a
   step registry; #t8-amendments d4a puts a TICK REGISTRY (one registry, one shared budget) in
   plan-23 23.1, which today means the daemon's tick. 17.2 is written as a hub-side registry that
   uses 23.1's step interface. Whether it must be the SAME registry object (and share its budget)
   is not settled.
2. **A legitimate bulk orphaning above the ratio cap.** 22.5's cross-store move (d8c) and 22.3's
   audited forgets can orphan more than max(50, 5 %) of a global dataset in one night. The cap then
   refuses every night and alerts. The log does not say how such a reap is released (a hand-run
   override, a 22.x manifest hand-off, or a raised cap for that dataset).
3. **Restore across plans** (decision review #s-7): whether 22.2's restore AC brings vectors back
   by reading 17.1's orphan list or by re-embedding, and the ADR-0004 `#rule-no-delete` sentence
   that scopes derived-vector reaping as restorable maintenance. Neither is a plan-17 file.
4. **The verb class of `rmx hub maintain arm`** (17.2 R7). d3d says the stamp is written "by
   hand"; an MCP twin would let an agent arm a store. The CLI-only verb class is unowned in the
   decision review (#s-5, d8g), so 17.2 ships it CLI-only pending that ruling.
