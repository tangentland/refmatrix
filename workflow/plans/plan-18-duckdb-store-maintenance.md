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

> Status: DRAFTING. 18.1 ran 2026-10-15 and is IN-PROGRESS (ch-bsd r1 remedy, d9br;
> [[#verdict-18-1]]). 18.2 and 18.3 were rewritten 2026-10-15 for the 18.1 verdict (d9be-d9bt):
> 18.3 is an IN-DAEMON rewrite-and-swap on one shared hold helper (`Daemon._catalog_hold`, built
> by 18.2 R11), gated on bug-112's fix; there is no offline route. C12 is lifted (d9be). Split
> out of plan-17 by the user on 2026-10-07 (plan-17 d-3). Plan-17 keeps the Lance vectors lean;
> this plan does the same for the DuckDB catalog.

rel: depends-on -> [[plan-17-nightly-store-maintenance]]
rel: specifies -> [[task-18.1-catalog-measurement]]
rel: specifies -> [[task-18.2-catalog-maintain-step]]
rel: specifies -> [[task-18.3-offline-reclaim]]
rel: related-to -> [[plan-review-2026-10-07#consolidations]]

## 18.1 verdict (run 2026-10-15) {#verdict-18-1}

18.1 ran on copies of all 8 registered snapshots
(`workflow/review-output/plan18-catalog-measure-20261015.md`; re-run after the ch-bsd r1 remedy as `…-20261015-r2.md` under the nine-leg fingerprint gate, same bands and verdict). Every gate passed.

| store | A | B | C | writer MiB -> rewrite MiB |
|---|---|---|---|---|
| refmatrix | A2 | disagree | C0 (1.94 s) | 789.0 -> 176.8 |
| global | A2 | disagree | C0 (0.42 s) | 241.8 -> 34.0 |
| cliquedb | A2 | disagree | C0 (1.05 s) | 230.5 -> 99.8 |
| viascope | A1 | disagree | C0 (1.74 s) | 291.5 -> 158.3 |
| cliquet, orderly, atldb, thiquet | A0 | disagree | C0 | under 64 MiB each |

Fleet verdict: a reclaim pays on 4 stores, so C12 is lifted (d9be). Every rewrite is under 2 s,
so 18.3 becomes an in-daemon rewrite-and-swap gated on bug-112 and 23.1 R1.6 (d9bf). 18.2 bands
on growth, because the free-block proxy disagrees everywhere (d9bg). The 18.1 spec amendments
are d9bh. Q1-Q4 below are answered by d9be-d9bg, amended by d9bp-d9br after ch-bsd 18.1 r1.

rel: derives-from -> [[plan-review-2026-10-14#t12-approvals]]

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
  the writer slot into a sibling new file INSIDE the daemon (d9bf) and swaps it under the same
  slot letter, with the `active` marker unchanged ([[task-18.3-offline-reclaim#r13-untouched]]).
- **Daemon op shape:** the same rules as plan-17's `vectors_maintain`: under `_store_lock`, bounded,
  fingerprinted, and scheduled by plan-17's hub tick. **Answer:** 18.2 has ONE bounded hold with a
  lock-wait timeout and a WAL gate, and is single-flight. 18.3's gate is the fingerprint. The
  reclaim is a separate, armed tick step whose reason is 18.2's growth band
  ([[task-18.3-offline-reclaim#r9-tick-step]]). Both build on one catalog-hold helper
  ([[task-18.2-catalog-maintain-step#r11-hold-helper]]).

## Tasks {#tasks}

| task | what | acceptance (summary; the spec is authoritative) | wave / depends on |
|---|---|---|---|
| 18.1 | `eval/catalog_maint/measure_catalogs.py`. It copies each registered store's snapshot in a child, then in fresh children reads `PRAGMA database_size`, times a 3× `COPY FROM DATABASE` rehearsal and gates it. Its pre-registered Tables A-C give a per-store band and a fleet verdict. | Finds and bands a 90 %-deleted fixture; `r` comes from the rewrite, not the proxy; the live root is untouched (no socket, no descriptor, `/bin/cp` argv); the gate can fail; one opener per path; a failed store is counted (`INCOMPLETE`); the band constants are pinned; mutations FAIL | Wave 4 (read-only, could run earlier: Q2) / 23.0 |
| 18.2 | ONE catalog-hold helper (`catalog_maint.CatalogHold`, `Daemon._catalog_hold`), with the snapshot tick and `_op_checkpoint` ported onto it; the `catalog_maintain` daemon op + verb + CLI/MCP on it, registered on 17.2's `maintenance_steps` with `requires_arming=False` (Q4, d9bg) and `after_idle` on `vectors_maintain` / `memory_compile`. REASON-GATED (d9bc): a hold only for `hand` or `wal_unfolded`, else `skipped:no_reason` with the reason logged. Bands on GROWTH against the store's live size (18.1 `rewrite_bytes`, reset by each reclaim; d9bq), which is exactly `r ≥ 0.50`. WAL gate, bounded lock wait, one hold of CHECKPOINT + PRAGMA, Table D hold bands with a downgrade. Health and the hub row get `catalog_reclaim_due` / `catalog_wal_large` / `catalog_hold_over`. | One hold within 50 ms of the recorder; 2 statements; `skipped:lock_busy` within 2 s behind a 10 s holder; `refused:wal_large`; D2 downgrade; lock-free status; dry run; no fallback; `invoked_by`; registration and order; hot-row news; snapshot hold measured; constants pinned (`growth`); reason gate (no hold without a reason); baseline from `rewrite_bytes`, never overwritten by a file; one helper (AST, lock order); mutations FAIL | Wave 4 / 17.2, 17.1 R11-R12 shapes, 23.0, 23.2, 18.1 (its re-taken jsonl for the baselines, d9br) |
| 18.3 | IN-DAEMON reclaim (d9bf, amended by d9bp; PROVISIONAL). `rmx catalog reclaim`: an idle rehearsal on a snapshot copy in children; then a confirmed real run as ONE hold on 18.2's helper: flush, CHECKPOINT, `COPY FROM DATABASE` into a sibling new file, the shared six-leg gate (d9br), a sentinel row, close, link the old slot to `backups/`, `os.replace`, reopen through 23.1's `_install_writer_store`, sentinel read-back + identity check, snapshot refresh; rollback on any failure, fast exit if the rollback fails. Phase A is interrupted past a 5 s budget. A LOADED measurement (tmp daemon, 6 readers) decides feasibility per store; a store over 5 s is `refused:rewrite_too_slow` and goes to the helix plan (no offline route). After a hand run per store, an ARMED tick step uses 18.2's A2 band as its reason. The init rebind and both rotation-bootstrap branches move onto the helper; `rmx compact` is retired onto the verb. | Round trip in the daemon (≥ 50 % smaller, gate equal, pid unchanged, ONE hold, sequence continues, post-run writes reach the new file, frozen slot / marker / `facts.log` / offsets / `vectors/` untouched, backup kept); one gate variant per leg; deadline interrupt and `rewrite_too_slow`; rollback including a cached-old-database reopen caught by the sentinel; failed rollback exits 2 and reboots whole; crash consistency at every swap point; rehearsal and real run match 18.1 (2 %, ±25 %); preconditions refuse before any hold; hold over 10 s disables; F5 (snapshot refreshed, `store_bytes` falls, no stale inode held); armed, reason-gated tick step with a one-backup cap; surfaces; `rmx compact` retired; one helper (AST); lock order; bug-112's swap write-loss reproduced against the fix; loaded measurement on the product path; mutations FAIL | Wave 4 / bug-112 FIX merged (branch `bugs-112-113-118`), 23.1 R1.6, 18.2, 17.2, 23.0, 23.2; R14's loaded verdict before the rollout |

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

  An in-daemon reclaim would need every store `≤ 5 s`. Recorded 2026-10-15 before the run; after
  the run d9bf chose the in-daemon reclaim, and d9bp applies the 5 s edge to a LOADED full-hold
  measurement ([[task-18.3-offline-reclaim#r14-loaded]]), not to 18.1's idle rewrite time. A
  store over it gets Table C's `refused:rewrite_too_slow` and goes to the helix plan; there is no
  offline route ([[task-18.3-offline-reclaim#r11-offline-route]]). Table C's 30 / 120 s edges
  gate nothing now (Q3 moot, d9be).
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
  ([[task-18.2-catalog-maintain-step#r9-register]]). The reclaim is a SECOND step,
  `catalog_reclaim`, registered after it with `requires_arming=True` and 18.2's A2 band as its
  reason ([[task-18.3-offline-reclaim#r9-tick-step]]).
- **`requires_arming`:** 18.2 declares `False`, against the contract's expected `True`, with
  this reason: the step's CHECKPOINT is the statement the snapshot tick already runs unarmed
  after every write, plus a metadata PRAGMA. It deletes and rewrites nothing, and it runs only
  for a reason (d9bc). The file-replacing action (18.3) is armed per store by a hand rehearsal +
  hand real run. Q4 answered by d9bg: `False` stands.
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
  catalogs only. 18.3 no longer stops or starts a daemon, so it has no launchd path to test; its
  exit-code and SIGKILL ACs run the tmp daemon as a subprocess.

## Open questions for the user {#questions}

All four are ANSWERED (2026-10-15). The rows are kept as asked, with the answer under each.

1. **Q1 — lift C12 for 18.3?** If 18.1 finds any store in A1/A2 with C0/C1: may a hand-run,
   OFFLINE rewrite of the writer slot be built? **Answer: yes, C12 is lifted (d9be)**, and the
   reclaim is reshaped to run IN the daemon (d9bf), amended by d9bp: bug-112's fix + a sentinel
   read-back gate the swap, feasibility is a loaded measurement, and there is no offline route.
2. **Q2 — run 18.1 before Wave 4?** **Answer: yes (d9bb).** It ran 2026-10-15; its ch-bsd r1
   remedy and a re-taken fleet run are pending (d9br).
3. **Q3 — confirm Table C's edges** (30 s / 120 s of offline downtime). **Answer: moot (d9be).**
   They stay as pre-registered; nothing is near them, and with the offline route gone they gate
   nothing.
4. **Q4 — `requires_arming=False` for `catalog_maintain`.** **Answer: `False` stands (d9bg)**,
   because d9bc makes every run reason-gated. 18.3's `catalog_reclaim` step is `True`; that
   difference is 18.3's open question Q-A.

### Opened by the 2026-10-15 revision {#questions-rev}

Recommended answers are in [[task-18.3-offline-reclaim#open-questions]]:

- **Q-A:** `requires_arming=True` for the reclaim step. Recommended: yes.
- **Q-C:** put `facts.log` compaction on the same helper (a 23.1/23.5 amendment). Recommended:
  yes.
- **Q-D:** where the 5 s deadline falls. Recommended: Phase A only; the whole hold is measured
  against 10 s.
- **Q-E:** accept the in-daemon COPY's memory (884 MiB peak on refmatrix). Recommended: yes,
  stated per store, with a 2 GiB user-decision edge.

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

## Revision 2026-10-15 (18.1 verdict) {#rev-18-1-verdict}

Specs revised by ch-architect for the 18.1 verdict and ch-bsd 18.1 r1. The `#verdict-18-1`
section and the status lines are the orchestrator's and were not edited here.

| source | change |
|---|---|
| d9be | [[#questions]] Q1 and Q3 answered; [[#thresholds]] Table C note |
| d9bf + d9bp (PROVISIONAL) | [[#tasks]] 18.3 row rewritten (in-daemon, sentinel, loaded feasibility, no offline route); [[#open]] slot-rotation and op-shape answers; [[#contract-answers]] (a second registered step; no launchd tests) |
| d9bg + d9bq (PROVISIONAL) | [[#tasks]] 18.2 row (growth on `rewrite_bytes`, reason gate); Q4 answered |
| d9bc | 18.2 R12 (the reason gate), and 18.3 R9's trigger |
| d9br (PROVISIONAL) | one six-leg gate shared by 18.1 and 18.3; 2 % bytes tolerance |
| the user's convergence rule | [[task-18.2-catalog-maintain-step#r11-hold-helper]], used by 18.3 R8 |
| anchors | the plan links to `#r6-untouched` / `#r9-not-nightly` move to [[task-18.3-offline-reclaim#r13-untouched]] / [[task-18.3-offline-reclaim#r9-tick-step]] |
| new questions | [[#questions-rev]] |
