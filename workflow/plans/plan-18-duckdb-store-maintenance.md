---
gmd: "0.1"
id: plan-18-duckdb-store-maintenance
title: "Plan 18: DuckDB catalog maintenance (checkpoint / vacuum) on the nightly maintenance tick"
tags: [plan, hub, daemon, duckdb, maintenance]
metadata:
  node_type: plan
  status: drafting
  created: 2026-10-07
  updated: 2026-10-15
---

# Plan 18: DuckDB store maintenance {#root}

> Status: DRAFTING. Task specs 18.1-18.3 were written 2026-10-15 at the user's request; they wait
> for a ch-bsd spec review and then the user's approval. Split out of plan-17 by the user on
> 2026-10-07 (plan-17 d-3). Plan-17 keeps the Lance vectors lean; this plan does the same for the
> DuckDB catalog.
> **Scope kept MINIMAL** (plan review C12, user 2026-10-07): measure + `CHECKPOINT` as a step on
> plan-17's tick. No slot-rewrite VACUUM until ADR-0004's helix plan decides whether snapshot
> manifests replace A/B slot reconciliation. 18.3, an offline rewrite, is CONDITIONAL on the
> user lifting C12 for it ([[#questions]] Q1).

rel: depends-on -> [[plan-17-nightly-store-maintenance]]
rel: specifies -> [[task-18.1-catalog-measurement]]
rel: specifies -> [[task-18.2-catalog-maintain-step]]
rel: specifies -> [[task-18.3-offline-reclaim]]
rel: related-to -> [[plan-review-2026-10-07#consolidations]]

## Why {#why}

The catalog is the DuckDB writer slots `catalog.A/B.duckdb`, plus a read snapshot. On this store
`catalog.read.duckdb` was 603 MB on 2026-10-07; on 2026-10-15 the writer slot was 834,940,928
bytes ([[task-18.1-catalog-measurement#facts]] F4). The cliquet repair (memory
`project_cliquet_catastrophic_repair`) took an 82 GB catalog down to 46 MB. Nothing reclaims free
blocks on a schedule. {#why-body}

## The premise, corrected at HEAD (2026-10-15) {#premise-2026-10-15}

Reading the code for the specs changed two things the stub assumed. Details are in
[[task-18.1-catalog-measurement#facts]].

- **A CHECKPOINT already runs after every write burst.** The snapshot tick runs it inside
  `_snapshot_catalog`'s `_store_lock` hold (`daemon.py:2621`, `:2653`). "Nothing runs
  CHECKPOINT on a schedule" was wrong: it runs about every 250 ms after a write.
- **CHECKPOINT and VACUUM give no space back on DuckDB 1.5.3.** A probe deleted 90 % of the
  rows and the file stayed at 68 MB with 236 of 261 blocks free. Only a rewrite into a new file
  (`COPY FROM DATABASE`) reclaimed the space, to 6.6 MB.

So C12's "measure + CHECKPOINT" by itself reclaims nothing. The plan becomes:

- MEASURE (18.1, on copies, against bands written before the run);
- a nightly measured step (18.2) that turns free space into a hot hub row and puts a number on
  every CHECKPOINT hold;
- a reclaim (18.3), built only if 18.1 shows it pays AND the user lifts C12 for an offline
  rewrite.

## To decide before specs (answered 2026-10-15) {#open}

- **Measure first:** catalog file size against live data size per fleet store, the WAL size, and
  the free-block ratio (`PRAGMA database_size`). **Answer:** that is 18.1, on copies, with a
  timed rewrite rehearsal as the measure of live data ([[task-18.1-catalog-measurement#r1]]).
- **Slot rotation:** a VACUUM or rewrite must respect the A/B writer slots and the `active` marker
  (`project_slot_drift_root_cause_fixed`). That probably means a rewrite into the inactive slot plus
  an atomic swap, not an in-place VACUUM. **Answer:** writer rotation is dropped and the inactive
  slots are frozen evidence (d9ao), so 18.3 must NOT write into the inactive slot. It rewrites
  the writer slot into a new file offline and swaps it under the same slot letter, with the
  `active` marker unchanged ([[task-18.3-offline-reclaim#r6-untouched]]).
- **Daemon op shape:** the same rules as plan-17's `vectors_maintain`: under `_store_lock`, bounded,
  fingerprinted, and scheduled by plan-17's hub tick. **Answer:** 18.2 has ONE bounded hold with a
  lock-wait timeout and a WAL gate, and is single-flight. 18.3's gate is the fingerprint. The
  reclaim is not on the tick ([[task-18.3-offline-reclaim#r9-not-nightly]]).

## Tasks {#tasks}

| task | what | acceptance (summary; the spec is authoritative) | wave / depends on |
|---|---|---|---|
| 18.1 | `eval/catalog_maint/measure_catalogs.py`. It copies each registered store's snapshot in a child, then in fresh children reads `PRAGMA database_size`, times a 3× `COPY FROM DATABASE` rehearsal and gates it. Its pre-registered Tables A-C give a per-store band and a fleet verdict. | Finds and bands a 90 %-deleted fixture; `r` comes from the rewrite, not the proxy; the live root is untouched (no socket, no descriptor, `/bin/cp` argv); the gate can fail; one opener per path; a failed store is counted (`INCOMPLETE`); the band constants are pinned; mutations FAIL | Wave 4 (read-only, could run earlier: Q2) / 23.0 |
| 18.2 | `catalog_maintain` daemon op + verb + CLI/MCP, registered last on 17.2's `maintenance_steps` with `requires_arming=False` and `after_idle` on `vectors_maintain` / `memory_compile`. It has a WAL gate and a bounded lock wait, ONE hold of CHECKPOINT + PRAGMA, and hold bands (Table D) that downgrade to PRAGMA-only. Health and the hub row get `catalog_reclaim_due` / `catalog_wal_large` / `catalog_hold_over`. The snapshot tick's own CHECKPOINT hold is timed. | One hold within 50 ms of the recorder; 2 statements; `skipped:lock_busy` within 2 s behind a 10 s holder; `refused:wal_large`; D2 downgrade persisted and cleared only by a hand run; lock-free status; dry run; no fallback; `invoked_by`; registration and order; hot-row news; snapshot hold measured; constants pinned; mutations FAIL | Wave 4 / 17.2, 17.1 R11-R12 shapes, 23.0, 23.2, 18.1 (band-mode default only) |
| 18.3 | CONDITIONAL. `rmx catalog reclaim`: a rehearsal on a copy; then a confirmed offline run that pauses the watchdog (must succeed), stops the daemon, holds `daemon.lock`, rewrites and gates in children, swaps under the same slot letter, kickstarts through launchd, post-checks and rolls back on any mismatch. `rmx compact` is retired onto it. | Round trip (≥ 50 % smaller, counts and hashes equal, sequence continues, marker / frozen slot / `facts.log` untouched, backup kept); gate failure; rollback, and a failed rollback stays paused; preconditions refuse before any stop; `daemon.lock` excludes starts; no in-process descriptor; matches 18.1's rehearsal; ledger; mutations FAIL | Wave 4 / 18.1 verdict + Q1, 18.2, 23.0 (tiers 2-3 for launchd) |

## Pre-registered thresholds (2026-10-15, before any data) {#thresholds}

Each band has an action. Changing an edge after 18.1's run needs a user decision row.

- **Table A, reclaim worth it** (`r = 1 − rewrite_bytes / file_bytes`, from the rehearsal):
  - A0: `reclaimable < 64 MiB` or `r < 0.20` → nothing;
  - A1: `0.20 ≤ r < 0.50` → one hand reclaim in a window;
  - A2: `r ≥ 0.50` → recommended, and the hub row is hot.

  ([[task-18.1-catalog-measurement#r3]])
- **Table B, proxy trust:** `abs(f − r) ≤ 0.10` on every store → 18.2 bands nightly on
  `f = free_blocks / total_blocks`; otherwise it bands on growth (`file_bytes ≥ 2 ×` baseline).
- **Table C, offline rewrite time** (median of 3 on a copy):
  - C0: `≤ 30 s` → admissible;
  - C1: `30-120 s` → only in a user-announced window;
  - C2: `> 120 s` → refused; the store goes to the helix plan;
  - noisy: `max > 1.5 × median` → re-run once.

  An in-daemon reclaim would need every store `≤ 5 s`. That is recorded and not built.
- **Table D, the nightly step's `_store_lock` hold**, measured in production by `time.monotonic()`
  around the one hold and checked against 23.2's recorder in tests
  ([[task-18.2-catalog-maintain-step#r4-hold]]):
  - D0: `≤ 2 s` (the hub's ping timeout);
  - D1: `2-10 s` → warning;
  - D2: `> 10 s` (a sixth of the 60 s heartbeat staleness that ends in a restart) → hot row, and
    later hub runs skip the CHECKPOINT until a hand run measures `≤ 10 s`.

  Around the hold: the lock wait is bounded at 30 s (`skipped:lock_busy`), and the WAL gate is
  64 MiB, 4× DuckDB's 16 MiB auto-checkpoint threshold (`refused:wal_large`).

## Contract to meet (drift note, 2026-10-14) {#contract-2026-10-14}

Plan-17's tick changed in the Wave 0 revisions; this plan's task specs, when written, start from it:

- **A registered step on 17.2's hub `maintenance_steps` registry** (17.2 `#r2-registry`), not on
  plan-23's daemon tick registry. It declares `requires_arming` and the reason. A CHECKPOINT that
  rewrites the catalog is user-visible state, so the expected answer is `True`: it dry-runs until
  the `run_id` of a successful hand run arms it (17.2 `#r7-unarmed`, the per-step ledger
  `<root>/maintain/runs.jsonl`).
- **Calls with `retries=0`, single-flight per store** (d3e), reported as `still_running` /
  `stuck` under 17.2's ceiling (`RMX_MAINTAIN_STUCK_AFTER`), never re-sent onto a running pass.
- **Order against 17.4:** the daily `facts.log` copy (17.4) and a CHECKPOINT must not run on the
  same store at the same time; state which runs first in the store's serial pass.
- **Order against the bug-105 repair:** the first CHECKPOINT on a store runs after
  `rmx repair-index --fragments` has been applied there.
- **Tests** in plan-23 task 23.0's sandbox only (d1a/d1b), on catalog copies.
- **Wave:** [[plan-review-2026-10-14#t10-waves]] (Wave 4).

rel: depends-on -> [[plan-review-2026-10-14#t10-waves]]
rel: depends-on -> [[task-17.2-hub-nightly-tick]]

### How the specs meet it (2026-10-15) {#contract-answers}

- **Registered step:** 18.2 registers `catalog_maintain` on `maintenance_steps`, last
  ([[task-18.2-catalog-maintain-step#r9-register]]). The reclaim is not a step (18.3 R9).
- **`requires_arming`:** 18.2 declares `False`, against the contract's expected `True`, with
  this reason: the step's CHECKPOINT is the statement the snapshot tick already runs unarmed
  after every write, plus a metadata PRAGMA. It deletes and rewrites nothing. The deleting action
  (18.3) is a hand run gated by a rehearsal record. Put to the user as Q4.
- **`retries=0`, single-flight:** 17.2 makes the call. 18.2 R3 gives the 17.1 R11 reply shape and
  a lock-free status.
- **Order against 17.4: DROPPED, with the reason** (closes plan-17
  [[plan-17-nightly-store-maintenance#open-after-revision]] item 7). 17.4 R2 copies `facts.log`
  from an open descriptor and never reads the catalog, and a CHECKPOINT never writes
  `facts.log`, so the two cannot tear each other. 18.2 declares `after_idle` on the two
  lock-holding steps (`vectors_maintain`, `memory_compile`) instead, and an AC proves a blocked
  backup does not defer it.
- **Order against bug-105:** satisfied at HEAD. The live repair was applied 2026-10-14 to the four
  affected stores, and the other four were clean (bug-105 row). The snapshot tick has
  checkpointed every store since. 18.3 records the `repair-index --fragments --dry-run` summary
  before a reclaim.
- **Tests:** every 18.x AC runs in the 23.0 sandbox. 18.1 and 18.3 work on copies or synthetic
  catalogs only; 18.3's launchd path runs in 23.0's tier-2/3 lanes.

## Open questions for the user {#questions}

1. **Q1 — lift C12 for 18.3?** If 18.1 finds any store in A1/A2 with C0/C1: may a hand-run,
   OFFLINE rewrite of the writer slot be built? It would keep the same slot letter, leave the
   frozen slots alone, and keep the old file as a backup. C12's premise, A/B slot
   reconciliation, is gone with writer rotation (d9ao). If no, 18.3 closes.
2. **Q2 — run 18.1 before Wave 4?** It is read-only (child `cp` of each snapshot to a scratch dir,
   under 2 GB in total) and changes no `src/` file. Running it now would tell whether 18.3 exists
   before Wave 4 plans around it.
3. **Q3 — confirm Table C's edges** (30 s / 120 s of offline downtime). They are judgement, not
   derived. Tables A, B and D are derived from code or stated in their rows.
4. **Q4 — `requires_arming=False` for `catalog_maintain`** (against the contract's expected
   `True`). If the user prefers `True` for uniformity, each of 8 stores needs one hand dry run, one
   hand real run, and an arm before the step runs for real.

## Observed while writing the specs (handed on, not this plan's) {#observed}

- **The facts.log compaction will run again soon.** On 2026-10-15 this store's facts.log
  compaction reclaimed 10.06 % (`294090489 -> 264498314`, rmxd.log 00:11:15). That is just above
  the 10 % floor rule (`_FACTSLOG_MIN_RECLAIM`, `daemon.py:2302`), so no floor was set. By ~00:20
  the log was 283,937,960 bytes, over the 256 MiB threshold again. The compaction will therefore
  re-run on its next 30-min tick, under `_store_lock`.
- **The 00:13 restart's cause is not measured.** The daemon was restarted at 00:13:18 as not
  answering. How long that compaction holds the lock, and what held the daemon from 00:11:15 to
  00:13:16, are not measured. That is plan-23/plan-17 territory (the lock-hold recorder) and the
  orchestrator's to route. 18.2 only avoids stacking behind it.
