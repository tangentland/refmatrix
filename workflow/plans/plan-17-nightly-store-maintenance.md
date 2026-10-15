---
gmd: "0.1"
id: plan-17-nightly-store-maintenance
title: "Plan 17: the hub keeps every store lean — nightly vector compaction, old-version cleanup, and orphan reaping as a daemon op"
tags: [plan, hub, daemon, lance, maintenance, performance]
metadata:
  node_type: plan
  status: drafting
  created: 2026-10-07
  updated: 2026-10-15
---

# Plan 17: nightly store maintenance from the hub {#root}

> Status: DRAFTING, revision round 7 after the 331b414 re-review ([[#rev-round-7]]); revision
> round 6 after the 0e77da3 re-review ([[#rev-round-6]]); revision
> round 5 after the 878647c re-review and d9z ([[#rev-round-5]]);
> revision round 3 after the 6091648 re-review ([[#rev-round-3]]); round 2 after
> the 32dde06 re-review and #t9 ([[#rev-round-2]]); first
> revised after the 2026-10-14 decision log ([[#rev-2026-10-14]]). The user asked
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
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r7-331b414]]
rel: derives-from -> [[bsd-decision-log-review-a192ba2]]
rel: depends-on -> [[plan-23-bounded-write-harness]]
rel: related-to -> [[exploration-storage-concurrency-redesign#option-a]]
rel: related-to -> [[plan-18-duckdb-store-maintenance]]
rel: related-to -> [[task-19.4-keep-derived-layers-current]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-32dde06]]
rel: derives-from -> [[plan-review-2026-10-14#t9]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r3-6091648]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r4-878647c]]
rel: derives-from -> [[plan-review-2026-10-14#t11-approvals]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r6-0e77da3]]

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
- **Per dataset, one bounded step** (23.1's `bounded_steps`, one dataset per step, each step one
  `_store_lock` hold through `bind(partition_name)` with the dataset's partition NAME, hold
  seconds from `RunResult.hold_s`, observed by the 23.2 recorder; no queue; [[#d2b]]):
  1. fingerprint (a): rows + an order-independent, per-id subtractable hash of (id, vector);
  2. tag the current version as the run's rollback point ([[#d3b]]);
  3. compute orphans against the WHOLE catalog ([[#d3a]]); above the ratio cap, skip the REAP only
     (compaction and cleanup still run) unless a hand run confirms that dataset's dry-run
     orphan-list sha, which releases the confirmed ids that are STILL orphans
     ([[#d9c]]); write the orphan list WITH vectors; reap;
  4. `compact_files()`;
  5. fingerprint (b), compared with (a) minus the reaped orphans. A mismatch restores the post-reap
     version, keeps every version on disk, returns `ok:false` and stops the run;
  6. only on a match: `cleanup_old_versions(older_than=<param, default 24 h>,
     error_if_tagged_old_versions=False)`, which never removes a tagged version; then the PREVIOUS
     successful run's tag is released.
- **A restore op** reads an orphan list back and re-upserts the vectors of ids whose entity is in
  the catalog again ([[#d3a]], the #t8 amendment), under the SAME id or, through `id_map`, under
  the NEW id a name-checked restore gave it (plan-22's 22.2), in the dataset of the entity's
  current partition and kind; it never overwrites an existing vector.
- **The hub only schedules**, on its OWN maintenance thread with its OWN step registry,
  `maintenance_steps` (plan-review C6; [[#d3e]]), not on the queue-alert thread and not on 23.1's
  daemon `tick_registry`:
  - stores come from the registered daemon list (the launchd-supervised set, 8 today), injected in
    tests;
  - SERIAL, one store at a time, with a per-store budget; `retries=0` and a single-flight op, so a
    timed-out store is "still running", never re-sent and never overlapped;
  - skips paused and not-running stores, and names them;
  - a (store, step) still running across two per-store budgets becomes `stuck`, alerts once and
    stops blocking the other stores;
  - per store, the steps run in registration order with the `facts.log` backup FIRST, and they
    are independent: a later step runs even when an earlier one is still running or stuck,
    unless it declares `after_idle` on it;
  - a stale daily `facts.log` copy (over 48 h) alerts on every hub wake, due or not, and shows
    in the daemon's health without the hub;
  - stamps per (store, step) in `~/.refmatrix/maintain.json`; each step declares
    `requires_arming`; an unarmed (store, step) that requires arming runs a DRY RUN only
    ([[#d3d]]); arming is the `hub_maintain_arm` verb, gated by the `run_id` of a successful hand
    run that follows a successful dry run of the same step;
  - logs per-store results to `hub.log`;
  - publishes one summary to `global:queues`, which bus retention already bounds.
- **No silent failures.** A failed store is logged and counted in the summary, and the next store
  still runs. A (store, step) that fails N runs in a row alerts once. {#design-body}

## Dependencies {#dependencies}

Wave 1 order ([[plan-review-2026-10-14#t8-wave1]]): 23.0 ∥ 23.4 → 23.2 → 23.1 (+ tick registry)
→ 23.3; after 23.1: … 17.1 → 17.2.

- **17.1** depends on 23.0 (the test sandbox, d1a/d1b), 23.2 (the hold and write-count recorder)
  and 23.1 (`bounded_steps`, `bind(partition_name)`, `RunResult.hold_s`; the names are
  [[task-23.1-queue-and-drain#r10-contract]]).
- **17.2** depends on 17.1 and 23.0 only. Its `maintenance_steps` is the hub's own registry; it
  does not use 23.1's daemon `tick_registry` (ns17-1).
- **17.4** depends on 17.2 and 23.0.
- **17.3** depends on 17.1, 17.2 and 17.4 being deployed.
- **Option A revisit** ([[#option-a-revisit]]) is triggered by task 23.4's verdict.

rel: depends-on -> [[task-23.1-queue-and-drain]]
rel: depends-on -> [[task-23.2-lock-hold-fixture]]

## Tasks {#tasks}

| task | what | acceptance (summary; the task spec is authoritative) | depends on |
|---|---|---|---|
| 17.1 | `vectors_maintain` + `vectors_restore` daemon ops, verbs, CLI/MCP, on 23.1's `bounded_steps` with `bind(partition_name)`: whole-catalog orphans with a ratio cap that skips only the reap and a `--confirm-orphans <sha>` release, orphan list with vectors, tagged rollback point, fingerprint gate before any cleanup, every partition by name, lock-free single-flight, a `runs.jsonl` ledger, no in-process fallback, no-match delete filter, reader retry | `older_than_s=0` → versions 1; default 24 h keeps a fresh version; forced mismatch → restored, old versions on disk; cross-partition entity's vector survives; capped dataset still compacts, a confirmed per-dataset sha reaps the confirmed ids still orphaned and leaves new ones to the cap; reap → restore round-trips, by same id and by `id_map` to new ids; competitor wins between datasets, `hold_s` per dataset; a reader opened before the pass scans to the end; a no-match re-sync commits 0 versions; pre-registered mutations FAIL | 23.0, 23.2, 23.1 |
| 17.2 | hub maintenance thread with its own `maintenance_steps`: 03:30 + catch-up, injected roots and clock, serial with per-store budget, `retries=0`, still-running vs failed with a `stuck` ceiling, (store, step) stamps, per-step `requires_arming`, the `hub_maintain_arm` verb gated by a hand-run `run_id`, summary | one run per scheduled day; catch-up exactly once; alert interval ≤ 0 still maintains; an unarmed step that requires arming dry-runs, one that does not runs; the backup runs first and a blocked step does not stop later ones; a stale backup alerts once; a blocking op is received once and becomes `stuck` on the second budget while the next store runs; arm refused without a matching hand run; zero connects outside the sandbox; pre-registered mutations FAIL | 17.1, 23.0 |
| 17.3 | fleet rollout over the 8 registered daemons: dry run, backup, hand run, user-confirmed orphan release, arm by `run_id`, Time Machine exclusion after the first backup copy; measure on a synthetic ≥ 30k-version clone; docs | before/after table per store; latency ratio ≤ 1/5 and a 0-version no-match re-sync on the synthetic clone; holds < `HEARTBEAT_STALE_S − 2 × HEARTBEAT_INTERVAL_S` (50 s; round 7); one night observed; backups removed only after the user confirms | 17.1, 17.2, 17.4 deployed |
| 17.4 | `factslog_backup` step on 17.2's `maintenance_steps` (`requires_arming=False`): once-a-day copy of `facts.log` to `backups/facts.log.daily` (+ `.prev`), lock-free from an open descriptor, skipped when unchanged; the live log is then excluded from Time Machine (added 2026-10-14, user) | one copy per injected day; the copy equals the old inode's prefix under a concurrent compaction; replays to the source catalog's state; still copies while `vectors_maintain` blocks; stale alert; restore: a damaged log under a healthy catalog is a forced compaction, a lost catalog with an intact, parsing live log is rebuilt from the LIVE log (nothing lost; the copy only if that rebuild fails verification: exit 0, `*_unresolved == 0`, counts equal an independent strict fold; `*_skipped_dead` printed, never a failure), a lost catalog with a lost or unparseable log is rebuilt from the copy, verified and promoted, and the daemon then holds the copy's learned rows; the daemon refusal and a read-only catalog probe come first; unchanged = untouched; loud non-destructive failure; runs unarmed, single-flight, ledger line; pre-registered mutations FAIL | 17.2, 23.0 |

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

- **d2b. No per-dataset Lance lock now** {#d2b}. 17.1 goes through plan-23's `bounded_steps` with
  `bind(partition_name)` per dataset and the 23.2 recorder, and not through the lossy queue. `_store_lock` is what excludes the daemon's
  Lance writers during a dataset step.
- **Option A revisit** {#option-a-revisit}. Under Option A
  ([[exploration-storage-concurrency-redesign#option-a]]) appends would run without `_store_lock`,
  so 17.1's exclusion would no longer hold. Trigger: task 23.4's verdict (#t8-amendments d2b/d2e),
  not "when Option A lands". If 23.4 returns GO for Option A, 17.1 is re-opened to add a
  per-dataset maintenance lock taken by every Lance writer path (`upsert_vectors`, `drop_for`,
  `_drop_lance_for_purge`, `_drop_lance_for_purge_batch`). If NO-GO or GO-serial (no concurrency
  proposed), the revisit closes and 17.1 keeps `bind` (nm17-2). An INVALID run gives no verdict
  and triggers nothing.
- **d3a. Orphan = id absent from the WHOLE catalog** {#d3a} (every partition), with the orphan
  list storing the vectors. Amended at close-out: KEEP the orphan ratio cap (refuse a reap above
  it) and add a restore op that reads the orphan list back.
- **d9c. The cap refuses the reap only, and a hand run releases it** {#d9c} (user, 2026-10-14,
  [[plan-review-2026-10-14#t9]]): a cap refusal skips the reap but still compacts; the release
  is `--confirm-orphans <sha of the dry-run orphan list>`.
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

Round 5 status (2026-10-14): items 1-6 are settled; item 3 is re-settled by d9z and carries the
exact fields plan-22 must write; item 7 is a note for plan-18. Round 6 status (2026-10-15): item 3
is WRITTEN on both sides (22.2 R4 / AC-4b), with the in-process `invoked_by` value; item 5 gains
the third restore scenario. Original text kept as history.

1. **SETTLED (ns17-1): two registries.** 17.2's hub `maintenance_steps` and 23.1's daemon
   `tick_registry` differ in process, signature and budget scale; 17.2 no longer depends on 23.1
   ([[task-17.2-hub-nightly-tick#r2-registry]]). Original text: **Which registry is 17.2's?** d3e and plan-review C6 put maintenance on "17.2's tick" with a
   step registry; #t8-amendments d4a puts a TICK REGISTRY (one registry, one shared budget) in
   plan-23 23.1, which today means the daemon's tick. 17.2 is written as a hub-side registry that
   uses 23.1's step interface. Whether it must be the SAME registry object (and share its budget)
   is not settled.
2. **SETTLED (d9c):** the refusal skips the reap only and still compacts; the release is a hand
   run with `--confirm-orphans <sha>` ([[task-17.1-vectors-maintain-op#r6-orphans]]).
   Original text: **A legitimate bulk orphaning above the ratio cap.** 22.5's cross-store move (d8c) and 22.3's
   audited forgets can orphan more than max(50, 5 %) of a global dataset in one night. The cap then
   refuses every night and alerts. The log does not say how such a reap is released (a hand-run
   override, a 22.x manifest hand-off, or a raised cap for that dataset).
3. **WRITTEN, both sides (d9z, option a; ns17-r4-1; round 6 nm17-r6-1): 17.1 R10 / AC-8b, and
   22.2 R4 / AC-4b ([[task-22.2-repair-then-remove#r4]]).** 22.2 R4 now keeps `old_id`, writes
   `removal/<apply_id>.vectors.jsonl` in 17.1 R6's format, builds `id_map` and calls
   `vectors_restore("removal/<apply_id>.vectors.jsonl", id_map=id_map,
   invoked_by="removal_restore")`, where `removal_restore` is the in-process caller value 17.1 R1
   defines ([[task-17.1-vectors-maintain-op#r1-verb]]). Round-5 text, kept as history: "Plan-17's
   side is written; plan-22's side is plan-22's to write, and this item does not claim it is
   written". 22.2's restore
   gives entities NEW ids, so `vectors_restore` takes `id_map: dict[int, int] | None` (old id →
   new id) and restores the vector under the new id
   ([[task-17.1-vectors-maintain-op#r10-restore]], AC-8b). The caller-facing signature is
   `vectors_restore(orphan_file: str, ids: list[int] | None = None, id_map: dict[int, int] |
   None = None, dry_run: bool = False) -> dict` (`invoked_by` is adapter-set, 17.1 R1). Round 4
   found that 22.2's manifest dropped the old id and that 22.2's own finalize deletes the
   vectors, so the map had no caller; d9z keeps both in 22.2. **What 17.1 needs from 22.2,
   exactly** (for the plan-16/22 pair to write into 22.2 R4 and its AC-4):
   - **A vectors file, written before finalize's Lance delete.** Path
     `<root>/removal/<apply_id>.vectors.jsonl` (17.1 R10 reads only `<root>/maintain/` and
     `<root>/removal/`). One line per removed entity that has a vector, appended and fsynced
     BEFORE the finalize deletes any vector of that kind; a failed write aborts the finalize
     (the 17.1 R6 rule). Fields, exactly 17.1 R6's orphan-list format:
     - `run_id`: the apply's id (`<apply_id>`);
     - `ts`: the write time (ISO-8601, as R6);
     - `partition`: the entity's partition NAME at removal time;
     - `kind`: its kind (which names its dataset, `vectors/<partition>/<kind>.lance`);
     - `id`: its OLD entity id (the id the vector is stored under);
     - `dim`: the vector's dimension (from the dataset schema);
     - `vector`: the Lance row's vector as `list[float]`, read from the dataset, byte-equal on
       round trip;
     - `dataset_version`: the Lance version it was read from.
   - **The OLD id in the manifest.** Each entity `intent` record keeps `old_id` beside its
     name-keyed before-state (22.2 R4 now records "its whole `entities` row, its OLD `id`
     included as `old_id`"; round 5's "today it keeps … except `id`" is superseded).
   - **The call.** After `removal_restore` re-inserts the entities by name and they have NEW
     ids, it builds `id_map = {old_id: new_id}` from the manifest's `old_id` and the restored
     rows, and calls `vectors_restore("removal/<apply_id>.vectors.jsonl", id_map=id_map,
     invoked_by="removal_restore")` in-process (nm17-r6-1). **Round 7 (nm17-r7-2): the
     in-process entry point is the op function, `_op_vectors_restore(d, {"orphan_file": …,
     "id_map": …}, in_process_caller="removal_restore")`, not the verb** (a verb is a socket
     client of the same daemon; 17.1 R1), and the closed-set check is in the op; 22.2 R4's
     "verb" wording is plan-22's to align. The call is made with no 23.1 `bind` held (restore takes its own per-dataset `bind`, 17.1 R10; the lock is not
     re-entrant). `present` means a newer vector already exists and wins; `dim` (the dataset's
     dimension changed since the removal) cannot be restored from the file and is re-embedded;
     `absent` cannot happen after a successful re-insert and is reported as an error, not
     skipped.
   - **22.2 AC-4** asserts byte-equal vectors under the new ids, with no model call for the
     ones the file held.
   - 17.1's own orphan lists (`<root>/maintain/orphans-<run_id>.jsonl`) stay the source for
     same-id restores of plan-17 reaps, and 22.2's R4 fallback "from plan-17's orphan list" is
     only for an entity whose vector a plan-17 reap took before 22.2 ran.
   ADR-0004 `#rule-no-delete` (d9k) scopes the reap as manifest-backed derived cleanup.
   Round-3 text (superseded): "22.2 passes the map from its manifest (plan-22's revision names
   the parameter)". Original text:
   **Restore across plans** (decision review #s-7): whether 22.2's restore AC brings vectors back
   by reading 17.1's orphan list or by re-embedding, and the ADR-0004 `#rule-no-delete` sentence
   that scopes derived-vector reaping as restorable maintenance. Neither is a plan-17 file.
4. **SETTLED (ns17-5, d8g):** one verb `hub_maintain_arm` on both surfaces, gated by the `run_id`
   of a successful hand run of that (store, step) in the store's `runs.jsonl`; each step declares
   `requires_arming` ([[task-17.2-hub-nightly-tick#r7-unarmed]]). Original text: **The verb class
   of `rmx hub maintain arm`** (17.2 R7). d3d says the stamp is written "by
   hand"; an MCP twin would let an agent arm a store. The CLI-only verb class is unowned in the
   decision review (#s-5, d8g), so 17.2 ships it CLI-only pending that ruling.
5. **SETTLED BY SPEC (ns17-r3-3, ns17-r3-4, ns17-r4-2): 17.4's exclusion safety.** The backup
   is the first, independent step; a stale copy alerts by age whether or not a run happened
   ([[task-17.2-hub-nightly-tick#r8-backup-age]]). The restore serves two named scenarios
   ([[task-17.4-factslog-backup-snapshot#r6-restore]]): a damaged log under a healthy catalog is
   `rmx compact-log --force`; a lost catalog is rebuilt from the copy in a throwaway root,
   verified, and PROMOTED into the live root with the copy as its log; a lost catalog with an
   intact live log (round 6, ns17-r6-1) is rebuilt the same way from the LIVE log, so nothing is
   lost. The script refuses while the daemon answers and probes the catalog read-only, a lock
   error counting as "daemon up". The slot offsets are
   bookkeeping only (nothing reads them at HEAD). Round-3 text (superseded): "moves the live log
   aside and resets both slot offsets".
6. **SETTLED in plan-19 (nm17-r3-5, nm17-r4-1):** 19.4 AC-2 now asserts day-1
   `dry_run:unarmed`, then a hand dry run and a real run, then arming by `run_id`, so it agrees
   with 17.2 R7. Original text: "19.4 AC-2 still asserts plan + apply on the scheduled day for a
   step it registers with `requires_arming=True`".
7. **For plan-18 (not edited here; nm17-r4-1):** plan-18 `#contract-2026-10-14` says the backup
   and a CHECKPOINT "must not run on the same store at the same time". 17.4 R2 copies from an open
   descriptor of `facts.log` and never reads the catalog, so a CHECKPOINT cannot tear it, and
   17.2 R2 already lets plan-18's step declare `after_idle=("factslog_backup",)` if it wants the
   order anyway. Plan-18 should either state why the overlap matters or drop the constraint.

## Revision round 2 (2026-10-14) {#rev-round-2}

Source: [[bsd-plan23-17-spec-rereview-32dde06]] (ns17-1..6, nm17-1..4) and
[[plan-review-2026-10-14#t9]] (d9c) with [[plan-review-2026-10-14#t9-fixes]].

| finding / decision | answered at |
|---|---|
| ns17-1 (17.2's registry is not 23.1's; phantom dependency) | [[#design]], [[#dependencies]], [[#open-after-revision]] 1, [[task-17.2-hub-nightly-tick#r2-registry]] |
| ns17-2 (17.1 mis-consumes 23.1: `bind(batch)`, ids, no `bounded_steps`, no per-hold seconds, `lock_free_during`) | [[#design]], [[#dependencies]], [[#d2b]], [[task-17.1-vectors-maintain-op#r3-holds]], [[task-23.1-queue-and-drain#r10-contract]] |
| ns17-3 (cap trips on the plan's own 559/5,495 and blocks compaction; no release), d9c | [[#design]] step 3, [[#d9c]], [[#open-after-revision]] 2, [[task-17.1-vectors-maintain-op#r6-orphans]], [[task-17.3-fleet-rollout#r1-hand-run]] |
| ns17-4 (`still_running` has no ceiling) | [[#design]], [[task-17.2-hub-nightly-tick#r4-call]] |
| ns17-5 (arming per (store, step) for every step; verb class) | [[#design]], [[#open-after-revision]] 4, [[task-17.2-hub-nightly-tick#r7-unarmed]], [[task-17.1-vectors-maintain-op#r12-ledger]], [[task-17.4-factslog-backup-snapshot#rev-round-2]] |
| ns17-6 (17.3 latency / no-match ACs had no input) | [[#tasks]] 17.3 row, [[task-17.3-fleet-rollout#r2-measure]] |
| nm17-1 (status / single-flight lock-free) | [[task-17.1-vectors-maintain-op#r11-single-flight]] |
| nm17-2 (`not_supervised` unreachable; GO-serial unnamed; `compact` seam) | [[#design]], [[#option-a-revisit]], [[task-17.2-hub-nightly-tick#r3-roots]], [[task-17.1-vectors-maintain-op#acceptance]] AC-2 |
| nm17-3 (vectors half of restore unowned on plan-22's side) | [[#open-after-revision]] 3 (plan-22's revision) |
| nm17-4 (17.4 landed unreviewed, no revision row) | [[#tasks]] 17.4 row, [[#dependencies]], [[task-17.4-factslog-backup-snapshot#rev-round-2]] |
| nb23-1 (`bind` never creates a partition) | [[task-17.1-vectors-maintain-op#r1-verb]] |

## Revision round 3 (2026-10-14) {#rev-round-3}

Source: [[bsd-plan23-17-spec-rereview-r3-6091648]] (0 BULLSHIT, 4 SKETCHY, 6 MEH for plan-17).

| finding / decision | answered at |
|---|---|
| ns17-r3-1 (`vectors_restore` by id vs 22.2's new ids) | [[#design]], [[#tasks]] 17.1 row, [[#open-after-revision]] 3, [[task-17.1-vectors-maintain-op#r10-restore]] |
| ns17-r3-2 (`--confirm-orphans` per run vs per dataset; churn loop) | [[#design]] step 3, [[#tasks]] 17.1 row, [[task-17.1-vectors-maintain-op#r6-orphans]], [[task-17.3-fleet-rollout#r1-hand-run]] |
| ns17-r3-3 (no staleness alarm; intra-store step order) | [[#design]], [[#tasks]], [[#open-after-revision]] 5, [[task-17.2-hub-nightly-tick#r2-registry]], [[task-17.2-hub-nightly-tick#r8-backup-age]], [[task-17.4-factslog-backup-snapshot#rev-round-3]] |
| ns17-r3-4 (restore runbook overwrites the live log; offsets) | [[#tasks]] 17.4 row, [[#open-after-revision]] 5, [[task-17.4-factslog-backup-snapshot#rev-round-3]] |
| nm17-r3-1 (17.1 R10 `bind(batch)`; AC numbering; AC-13 mutation) | [[task-17.1-vectors-maintain-op#rev-round-3]] |
| nm17-r3-2 (arm gate proves a run, not d3d's order) | [[#design]], [[task-17.2-hub-nightly-tick#r7-unarmed]] |
| nm17-r3-3 (R4 polls `vectors_maintain` for every step) | [[task-17.2-hub-nightly-tick#r4-call]] |
| nm17-r3-4 (17.3 clone `HOME`; build time) | [[task-17.3-fleet-rollout#r2-measure]] |
| nm17-r3-5 (19.4 AC-2 vs `requires_arming`) | [[#open-after-revision]] 6 (plan-19's file; not edited) |
| nm17-r3-6 (17.4 AC-3 identical bytes; `fclonefileat` binding) | [[task-17.4-factslog-backup-snapshot#rev-round-3]] |
| nm17-3 / dlr #s-7 (restore across plans, partial in r3) | [[#open-after-revision]] 3 |

## Revision round 5 (2026-10-14) {#rev-round-5}

Source: [[bsd-plan23-17-spec-rereview-r4-878647c]] (plan-17: 0 BULLSHIT, 2 SKETCHY, 1 MEH) and
[[plan-review-2026-10-14#t11-approvals]] (d9z, option a).

| finding / decision | answered at |
|---|---|
| ns17-r4-1 (`id_map` has no caller), d9z option a | [[#open-after-revision]] 3 (the exact fields 22.2 must write, for plan-22's own revision), [[task-17.1-vectors-maintain-op#r10-restore]], [[task-17.1-vectors-maintain-op#rev-round-5]] |
| ns17-r3-1 (partial) | the ns17-r4-1 row |
| ns17-r4-2 (17.4's restore never restores the catalog; offsets unread) | [[#tasks]] 17.4 row, [[#open-after-revision]] 5, [[task-17.4-factslog-backup-snapshot#rev-round-5]], [[task-17.3-fleet-rollout#rev-round-5]] |
| nm17-r4-1 (17.4 AC-8 daemon clock; restore signature; stale item 6; plan-18 overlap) | [[task-17.4-factslog-backup-snapshot#rev-round-5]] (clock), [[task-17.1-vectors-maintain-op#rev-round-5]] (signature, ledger), [[#open-after-revision]] 6 and 7 |

## Revision round 6 (2026-10-15) {#rev-round-6}

Source: [[bsd-plan23-17-spec-rereview-r6-0e77da3]] (plan-17: 0 BULLSHIT, 1 SKETCHY, 2 MEH; round
4: 3 of 3 closed). Code facts re-read at HEAD `3d3c798`. The round-5 table above is unchanged
history.

| finding / decision | answered at |
|---|---|
| ns17-r6-1 (17.4 restore classifies by "the catalog opens" alone; a lost catalog with an intact live log loses up to a day; probe position and mode unstated) | [[#tasks]] 17.4 row, [[#open-after-revision]] 5, [[task-17.4-factslog-backup-snapshot#rev-round-6]], [[task-17.3-fleet-rollout#rev-round-6]] |
| nm17-r6-1 (item 3 trails plan-22; `invoked_by` has no value for 22.2's in-process call) | [[#open-after-revision]] 3 (WRITTEN, both sides; the call carries `invoked_by="removal_restore"`), [[task-17.1-vectors-maintain-op#rev-round-6]]; 22.2 R4 names the value (plan-22's file, not edited here) |
| nm17-r6-2 (R9's no-match filter misses the single-id delete the memory bridge now uses) | [[task-17.1-vectors-maintain-op#rev-round-6]] |

## Revision round 7 (2026-10-15) {#rev-round-7}

Source: [[bsd-plan23-17-spec-rereview-r7-331b414]] (plan-17: 0 BULLSHIT, 0 SKETCHY, 3 MEH;
round 6: 3 of 3 closed). The user bounded the holds per the report (nm17-r7-3: "≤ 50 s or
30 s", citing the coupling); this revision takes the watchdog-derived 50 s. Code facts re-read
at HEAD `77ac38f`. The round-6 table above is unchanged history.

| finding / decision | answered at |
|---|---|
| nm17-r7-1 (17.4 AC-9's second (c) run is class (b); the fallback unreachable; the lock discriminator; the ART-index precedent) | [[#tasks]] 17.4 row, [[task-17.4-factslog-backup-snapshot#rev-round-7]], [[task-17.3-fleet-rollout#rev-round-7]] (runbook text) |
| nm17-r7-2 (`removal_restore`'s entry point unnamed; the verb is a socket client of its own daemon) | [[task-17.1-vectors-maintain-op#rev-round-7]]; 22.2 R4's "calls the verb in-process" wording is plan-22's to align |
| nm17-r7-3 (17.3's < 60 s bound equals the heartbeat-stale threshold) | [[#tasks]] 17.3 row, [[task-17.3-fleet-rollout#rev-round-7]], [[task-17.1-vectors-maintain-op#rev-round-7]] (alarm default); the reads' wait on the lock itself is plan-23's (d9az, [[task-23.5-read-path-and-holder-bounds]]) |

## Revision round 8 (2026-10-15) {#rev-round-8}

Source: [[bsd-plan23-17-spec-rereview-r8-23ad703]] (plan-17: 0 BULLSHIT, 1 SKETCHY, 1 MEH, plus
17.3's share of nm23-r8-4's line drift). Code facts re-read at HEAD `23ad703`. The round-7 table
above is unchanged history.

| finding / decision | answered at |
|---|---|
| ns17-r8-1 (17.4's restore verify undefined for a real live log; the (c) fallback fixture is a normal `links_skipped_dead` at 0.78.3) | [[#tasks]] 17.4 row, [[task-17.4-factslog-backup-snapshot#rev-round-8]]; replay's silent skip of a non-JSON line is bug-119 (`workflow/bug_registry.md`) |
| nm17-r8-1 (17.1 AC-13 names a connect log that records only DENY-set targets) | [[task-17.1-vectors-maintain-op#rev-round-8]] |
| nm23-r8-4 (17.3's `daemon.py` cites) | [[task-17.3-fleet-rollout#rev-round-8]] |

rel: derives-from -> [[bsd-plan23-17-spec-rereview-r8-23ad703]]
