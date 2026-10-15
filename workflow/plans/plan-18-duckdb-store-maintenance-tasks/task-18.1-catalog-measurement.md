---
gmd: "0.1"
id: task-18.1-catalog-measurement
title: "Task 18.1: measure every fleet catalog on a copy — free blocks, a timed rewrite rehearsal, and pre-registered bands that decide whether a reclaim is worth building"
tags: [task, duckdb, catalog, measurement, maintenance, pre-registered]
metadata:
  node_type: task
  status: in-progress
  created: 2026-10-15
  updated: 2026-10-15
---

# Task 18.1: measure the fleet's catalogs on copies {#root}

> Plan: [plan-18-duckdb-store-maintenance](../plan-18-duckdb-store-maintenance.md)
> Status: IN-PROGRESS (d9br). Script `8a93ab1`, then the ch-bsd r1/r2 remedies `886386b`,
> `34ac5cd` and `8281a7f` (clone `/Volumes/littlebig/refmatrix-task-18.1`, branch
> `task-18.1-catalog-measurement`). Fleet report: `workflow/review-output/plan18-catalog-measure-20261015-r2.md`
> (GMD id `plan18-catalog-measure-20261015-r2`). Verdict [[plan-18-duckdb-store-maintenance#verdict-18-1]].
> The amendments d9bh, d9br and d9bv are folded into this body ([[#rev-round-3]]).
> Wave: 4 ([[plan-review-2026-10-14#t10-waves]]). It is read-only on copies and changes no
> `src/` file, so it CAN run earlier if the user says so (plan open question Q2).
> Depends on: 23.0 (the script's tests run in the sandbox). Nothing else: no daemon op, no store
> write, no hub.
> Decides: whether 18.3 is built at all (Tables A and C), and how 18.2 bands its nightly signal
> (Table B).

rel: part-of -> [[plan-18-duckdb-store-maintenance]]
rel: depends-on -> [[task-23.0-test-sandbox]]
rel: depends-on -> [[feedback_go_no_go_ranges_not_predrop]]
rel: depends-on -> [[feedback_measure_the_path_users_run]]
rel: related-to -> [[plan-review-2026-10-07#consolidations]]
rel: related-to -> [[plan-review-2026-10-14#t12-approvals]]
rel: motivates -> [[task-18.3-offline-reclaim]]
rel: motivates -> [[task-18.2-catalog-maintain-step]]
rel: derives-from -> [[bsd-plan18-task18-1-measurement-r2-34ac5cd]]

## Why {#why}

The plan's first open item is "measure first" ([[plan-18-duckdb-store-maintenance#open]]). Reading
the code at HEAD changed what there is to measure:

- A `CHECKPOINT` already runs after every write burst, inside the snapshot tick (F1). A nightly
  CHECKPOINT adds almost nothing.
- On DuckDB 1.5.3, neither `CHECKPOINT` nor `VACUUM` shrinks the file. A probe deleted 90 % of a
  table: the file stayed at 68 MB with 236 of 261 blocks free. Only a REWRITE into a new file
  (`COPY FROM DATABASE`) gave the space back, 6.6 MB (F2).

So the question is whether a rewrite is worth building, and that depends on two numbers nobody
has measured. One is how much each fleet catalog would give back. The other is how long the
rewrite takes, which is the downtime of an offline reclaim (18.3). This task measures both on
copies, against bands written here BEFORE the run. {#why-body}

## Facts at HEAD `55f043d` (`src/` unchanged through `0611d2f`) {#facts}

Read 2026-10-15 from `src/refmatrix/` and by `stat` of the live files. No live store was opened.

- **F1 The CHECKPOINT that already runs.** Write ops call `_request_snapshot()`
  (`daemon.py:2693`). `_start_snapshot_tick` (`:2706`) waits `RMX_SNAPSHOT_DEBOUNCE_MS` (default
  250) and then calls `_snapshot_catalog(force=True)` (`:2621`). That function takes `_store_lock`
  and, INSIDE that one hold, runs `CHECKPOINT` (`:2652-2657`), copies the writer slot to
  `catalog.read.duckdb.tmp` with `_copy_out_of_process` (`:203`, `/bin/cp -p` in a child, bug-110)
  and `os.replace`s it (`:2665-2666`). The boot path runs it too: the init slot rebind at `:1728`
  and the startup snapshot at `:1791`. So `catalog.read.duckdb` is a byte copy of the writer slot
  just after a CHECKPOINT. DuckDB's own auto-checkpoint threshold is the default
  `checkpoint_threshold = 16.0 MiB` (read from DuckDB 1.5.3; `src/` never sets it).
- **F2 What reclaims space on DuckDB 1.5.3.** This was a throwaway probe in the session scratch
  dir under the deploy venv's `duckdb 1.5.3` (`.venv-eval` has 1.5.2). Nothing was committed;
  AC-1 re-runs the same shape as a test. The steps and what they showed:
  - 2,000,000 rows and a CHECKPOINT: 62.1 MB, 237 of 237 blocks used.
  - `DELETE` of 90 % of the rows, then `CHECKPOINT`: 68.4 MB; `PRAGMA database_size` showed
    `total_blocks 261, used_blocks 25, free_blocks 236`, `block_size 262144`.
  - `VACUUM` + `CHECKPOINT`, then `FORCE CHECKPOINT`: both left the file and the block counts
    unchanged.
  - `ATTACH '<new>'` + `COPY FROM DATABASE t TO n` + `CHECKPOINT n`: a 6.57 MB file, in 0.08 s.
  - A second probe showed `COPY FROM DATABASE` keeps a sequence's state (`nextval` gives 6 after
    5 inserts), the index, and the PRIMARY KEY / UNIQUE / NOT NULL constraints.
  - Free blocks are counted from a checkpointed file, which is the state the snapshot copy is
    in (F1).
- **F3 The commands that exist, and what they really do.**
  - `_op_checkpoint` (`daemon.py:3871-3888`; `rmx checkpoint`, `cli.py:7740`) DROPs and
    re-CREATEs `idx_entity_links_lk_concept` and then CHECKPOINTs, all under `_store_lock`. That
    index covered 776,359 rows on this store (rmxd.log, 2026-10-15T00:13:19, the boot repair).
  - `_op_vacuum` (`:3905`) calls `Store.vacuum` (`store.py:7260`), which drops empty concepts
    and missing tracked files. It is not a DuckDB VACUUM.
  - `rmx compact` (`cli.py:7630`) is an offline EXPORT/IMPORT through Parquet. It has four
    flaws: it stops the daemon without pausing the hub watchdog; it restarts it with
    `spawn_daemon` rather than launchd; it opens the slot in-process; and its docstring still
    describes writer rotation.
- **F4 The fleet** (sizes in bytes, `stat` only, 2026-10-15 ~00:20 local; the 8 launchd-registered
  roots):

  | store | writer slot | writer bytes | snapshot bytes | frozen inactive slot | legacy `catalog.duckdb` | `facts.log` |
  |---|---|---|---|---|---|---|
  | refmatrix | B | 834,940,928 | 834,940,928 | A 14,430,208 | 2,633,728 | 283,937,960 |
  | viascope | A | 305,672,192 | 305,672,192 | B 386,412,544 | 2,633,728 | 439,774,594 |
  | global (`~/.refmatrix`) | A | 253,505,536 | 253,505,536 | B 1,847,296 | 5,255,168 | 109,385,413 |
  | cliquedb | A | 241,709,056 | 241,709,056 | B 3,158,016 | 21,508,096 | 201,932,578 |
  | cliquet | A | 74,723,328 | 74,723,328 | B 4,730,880 | 6,828,032 | 96,191,227 |
  | atldb | A | 32,780,288 | 32,780,288 | B 14,430,208 | 14,430,208 | 40,558,364 |
  | orderly | A | 22,818,816 | 22,818,816 | B 1,847,296 | 1,847,296 | 18,176,997 |
  | thiquet | A | 2,895,872 | 2,895,872 | B 1,847,296 | 2,109,440 | 1,199 |

- **F5 What the store-size alert counts.** `_store_health` `store_bytes` (`daemon.py:3775-3785`)
  sums every `catalog*.duckdb` and `*.wal`: the writer, the snapshot, the frozen slot and the
  legacy file. The hub alerts above `RMX_HUB_STORE_BYTES_ALERT` (2 GiB; `hub.py:77`,
  `:657-659`). A writer with high free space therefore counts twice (writer + snapshot), and
  nothing reports free space.
- **F6 Writer rotation is dropped** (`_refresh_replica_now`, `daemon.py:2814`, is a no-op; d9ao,
  [[plan-review-2026-10-14#t12-approvals]]). The inactive slots are frozen and some hold rows
  found only there (viascope's 386 MB B slot: 113,985 ids). They are a separate item. This plan
  never writes, moves or measures them beyond `stat`.
- **F7 The copy is cheap.** `/bin/cp -p` of this store's 834,940,928-byte snapshot to the session
  scratch dir (same APFS volume) took 0.16-0.20 s over three runs, warm. The copy was deleted
  unread.

{#facts-body}

## Requirements {#requirements}

1. **R1 The script** `eval/catalog_maint/measure_catalogs.py`. It is evaluation code, not
   product, and it lives in `eval/` beside 23.4's prototype. {#r1}
   - **Inputs.** `roots: list[Path]`; the default is `discovery._roots_from_launchd()`, the
     registered set, and tests inject it. `scratch: Path` is a short tmp root (the macOS
     `sun_path` rule does not apply, but copies stay off the watched tree,
     `feedback_generated_data_off_watched_tree`). `out: Path` is the report path.
   - **The copy.** Per root, it `stat`s the F4 columns (writer slot from the `active` marker,
     snapshot, inactive slot, legacy file, `facts.log`, the writer's `.wal`). It copies
     `catalog.read.duckdb` to `<scratch>/<store>/snap.duckdb` with `/bin/cp -p` in a child
     process (the `_copy_out_of_process` shape, F1). It never opens a descriptor on any file under
     a live root (bug-110: a close drops the daemon's lock), it never connects to a socket, and it
     never reads a writer slot. The snapshot's mtime is recorded as the measurement's `as_of`.
   - **One child process per copy, for every DuckDB statement** (bug-112: a second in-process
     `duckdb.connect` to a path returns the cached database). Child 1 opens the copy read-only
     and measures `PRAGMA database_size` (`block_size`, `total_blocks`, `used_blocks`,
     `free_blocks`) and the copy's `catalog_fingerprint` (below). Every child reports its
     `duckdb.__version__`; children on different builds make the store an error row (d9br), and
     each row records `duckdb_version`.
   - **The rewrite rehearsal.** Child 2 opens the copy READ-WRITE (d9bh: a read-only connection
     attaches its target read-only) and runs `ATTACH '<work>/rewrite.duckdb' AS n`,
     `COPY FROM DATABASE snap TO n`, `CHECKPOINT n`, `DETACH n`. `rewrite_s` is
     `time.monotonic()` around those four statements. The rehearsal runs three times on fresh
     targets. It reports `rewrite_s` as the median of the runs and `rewrite_s_max` as the max over
     EVERY run (a noisy first batch included), and `rewrite_bytes` as the MEDIAN of the runs'
     new-file sizes (d9br; one rewrite's size moves in whole 256 KiB blocks).
   - **The gate** (d9br). Child 3 opens `rewrite.duckdb` read-only, and the gate is
     `gate(catalog_fingerprint(copy), catalog_fingerprint(rewrite))`, empty on a pass. The
     fingerprint has NINE legs, each compared key by key:
     - `rows`: per table, `count(*)`;
     - `content`: per table, an order-independent `sum(hash(row)::HUGEINT)` over every column
       (a SUM, not `bit_xor`, so duplicate rows cannot cancel);
     - `columns`: per table, `duckdb_columns()` index, name, `data_type`, `column_default`,
       `is_nullable`;
     - `constraints`: per table, `duckdb_constraints()` type, `constraint_text` and sorted column
       names;
     - `indexes`: `duckdb_indexes()` table and `sql`;
     - `sequences`: `duckdb_sequences()` start, min, max, increment, cycle and `last_value`;
     - `views`, `macros`, `types`: the non-internal `duckdb_views()` sql,
       `duckdb_functions()` macro definitions and `duckdb_types()`.

     A leg missing on one side is itself a difference. **Precondition** (ch-bsd 18.1 r2 S-1,
     `8281a7f`): both fingerprints come from FRESH opens of checkpointed files. On a connection
     that has issued sequence values, `duckdb_sequences()` reports `start_value` / `last_value`
     differently from a fresh open of the same state, so the `sequences` leg is not comparable
     on a live session. 18.3 gates a live session and therefore defines that leg on
     session-stable invariants ([[task-18.3-offline-reclaim#r5-gate]]); the leg is never dropped.
     A store whose gate fails gets no band (R3).
   - **Derived values.** `f = free_blocks / total_blocks`; `r = 1 − rewrite_bytes / file_bytes`
     (`file_bytes` is the copy's size); `reclaimable = file_bytes − rewrite_bytes`. The reclaim
     estimate is `r`, which comes from the rewrite. `f` is the cheap proxy that 18.2 can read
     nightly, and Table B decides whether it can be trusted.
2. **R2 Output.** `workflow/review-output/plan18-catalog-measure-<YYYYMMDD>.jsonl` gets one line
   per store with every R1 field and its band. `…-<YYYYMMDD>.md` is a GMD report: the per-store
   table, each band with the edge it fell in, and the fleet verdict (R5). The scratch copies and
   rewrite files are deleted after the report is written; they are copies, and the live files
   are untouched. Each store works in its own `mkdtemp` dir under `scratch`, removed in a
   `finally`; the script never removes `scratch` itself (d9br). A re-run on the same day writes a
   suffixed report whose GMD id is its file stem (`…-<YYYYMMDD>-r2`), so two reports never share
   a node id. {#r2}
3. **R3 Pre-registered bands** (`feedback_go_no_go_ranges_not_predrop`). These are written
   2026-10-15, before any fleet run. The script holds them as one constant table, and AC-7 pins
   its literal values to this section. Changing an edge after the run needs a user decision row
   in the plan review. {#r3}

   **Table A: is a reclaim worth it, per store** (on `r` and `reclaimable`).

   | band | condition | action |
   |---|---|---|
   | A0 | `reclaimable < 64 MiB` OR `r < 0.20` | nothing; the store is excluded from 18.3 |
   | A1 | `0.20 ≤ r < 0.50` AND `reclaimable ≥ 64 MiB` | worth one hand reclaim in a window (18.3, if built); no alert |
   | A2 | `r ≥ 0.50` AND `reclaimable ≥ 64 MiB` | hand reclaim recommended; 18.2 marks the store `catalog_reclaim_due` (a hot hub row) |

   Why these edges: 64 MiB is small beside the fleet's two largest catalogs (F4) and is
   above a rounding error on the small stores. With `r < 0.20` the file is mostly live data, so
   a rewrite buys under a fifth of it back. With `r ≥ 0.50` the writer AND its snapshot (F5)
   are each at least twice the live data.

   **Table B: can 18.2 trust the cheap proxy `f`** (per store, then fleet).

   | band | condition | action |
   |---|---|---|
   | B-agree | `abs(f − r) ≤ 0.10` | the store's `f` predicts `r` |
   | B-disagree | `abs(f − r) > 0.10` | `f` is reported but not banded for that store |
   | fleet | every measured store B-agree | 18.2 bands nightly on `f` with Table A's edges (`RMX_CATALOG_BAND_MODE=free_ratio`) |
   | fleet | any store B-disagree | 18.2 bands on growth only: `catalog_reclaim_due` when the writer's `file_bytes ≥ 2 ×` its 18.1 `file_bytes` (`RMX_CATALOG_BAND_MODE=growth`) |

   Why 0.10: `f` misses partly used blocks, which a rewrite also packs, so `f ≤ r` is
   expected. A gap of more than 10 points would move a store across Table A's 0.20 or 0.50 edge
   on the proxy alone.

   **Table C: is an offline rewrite admissible, per store** (median `rewrite_s` of 3 on the
   copy). The rewrite is the downtime of 18.3's offline reclaim; the daemon restart adds its boot
   time.

   | band | condition | action |
   |---|---|---|
   | C0 | `rewrite_s ≤ 30` | an offline hand reclaim is admissible as 18.3 specifies |
   | C1 | `30 < rewrite_s ≤ 120` | admissible only in a user-announced window, one store at a time (18.3 `window=True`) |
   | C2 | `rewrite_s > 120` | not admissible; 18.3 refuses the store (`refused:rewrite_too_slow`) and it goes to the helix plan |
   | noisy | `max > 1.5 × median` | the three runs are repeated once; still noisy → the store is reported `noisy` with no C band |

   Why these edges: they are judgement, not derived, and they are the user's to confirm (plan
   open question Q3). A supervised restart on this store took 3 s from `daemon starting` to
   `pools` (rmxd.log, 2026-10-15T00:13:18-21), so C0 caps the reclaim's outage at roughly ten
   restarts. 120 s is the longest outage this spec proposes without the user announcing a window.

   **Recorded, not built: an in-daemon reclaim.** A rewrite under `_store_lock` with the daemon
   up would hold the lock for `rewrite_s`. 18.2's hold ceiling is 10 s (Table D, in
   [[task-18.2-catalog-maintain-step#r4-hold]]), so an in-daemon variant could only be proposed
   if EVERY store's max `rewrite_s ≤ 5`. That leaves a 2× margin, because the live writer is
   also serving. The report states whether that holds; nothing builds it.
4. **R4 The production path is this path** (`feedback_measure_the_path_users_run`). If 18.3 is
   built, its own rehearsal runs on the same copy through ITS production routine. The result must
   land within ±25 % of this task's median `rewrite_s` and within `max(2 %, 512 KiB)` of its
   median `rewrite_bytes` (d9br as amended by d9bv: the r2 fleet re-run measured a 3-run spread
   of up to 2.17 %, in whole 262,144-byte blocks; [[task-18.3-offline-reclaim#acceptance]] AC-7). If it does not, 18.1's verdict is re-taken
   with the production routine before any live reclaim. {#r4}
5. **R5 The verdict and its hand-off.** The implementer runs the script once over the 8
   registered roots (copies only; announced to the user first, because it reads every store's
   snapshot) and writes the R2 report. The plan file then records the per-store bands and one
   fleet verdict: {#r5}
   - every store A0 → **18.3 CLOSED, not needed**; 18.2 still ships (monitoring);
   - any store A1 or A2 with C0 or C1 → **18.3 goes to the user** with the table, as a request to
     lift C12 for an OFFLINE hand-run reclaim ([[plan-review-2026-10-07#consolidations]]; plan
     open question Q1);
   - any store A1/A2 with C2 → that store is named for the helix plan and excluded from 18.3;
   - the Table B fleet row sets 18.2's `RMX_CATALOG_BAND_MODE` default.
6. **R6 No silent failure.** A store whose copy, a child, or the gate fails becomes a row with
   `error` and the failing step; any `Exception` raised for one root becomes that root's row,
   and an interrupt still writes a row per root (d9br). It is counted, and the remaining stores
   are still measured. The
   script exits 1 if any store failed, and the verdict is `INCOMPLETE`: no fleet-wide band is
   applied until every store has a row. {#r6}

## Acceptance criteria {#acceptance}

All tests run inside the 23.0 sandbox, on tmp roots whose catalog files are real DuckDB databases
written by `Store.init()` plus synthetic rows. No test reads a live root.

1. **AC-1 (reclaim found and measured).** A tmp root has a `catalog.read.duckdb` with 200,000
   `entities` rows, 95 % of them deleted and checkpointed (the F2 shape; d9bh/d9br: at 90 % `r`
   sat on the 0.80 edge and failed 1 run in 8, at 95 % it measured 0.874-0.887). The row's
   `total_blocks` / `used_blocks` / `free_blocks` equal the test's own `PRAGMA database_size`
   reading of the file and `f` equals `free / total` from it (a `free := used` fails). The row
   reports `r ≥ 0.80`, `0 < f ≤ r` (on the real schema the index blocks keep `f` near 0.6, so
   `f ≥ 0.80` cannot hold; d9bh), `reclaimable > 0`, a passing gate, `rewrite_bytes` equal to
   the median of its runs, and band A2 (with the test's 64 MiB edge scaled down through the
   script's `min_reclaim_bytes` parameter, whose default is pinned by AC-7). A second root of
   200,000 rows with no deletes (a margin fixture: at 20,000 rows block steps moved `r` to 0.04,
   at 200,000 it stayed ≤ 0.014) gets `r < 0.20` and band A0. {#ac-1}
2. **AC-2 (r is the rewrite, not the proxy).** The pure derive function is given
   `file_bytes=200 MiB, rewrite_bytes=80 MiB, free_blocks=10, total_blocks=100` and returns
   `r = 0.60`, `f = 0.10`, band A2 and B-disagree (d9bh: 100/40 MiB gave 60 MiB reclaimable,
   under Table A's own 64 MiB edge). Mutation: `r := f` FAILS (band A0,
   B-agree). {#ac-2}
3. **AC-3 (the live root is untouched).** The sandbox records zero socket connects. Over the run,
   every file under the injected root keeps its (name, size, mtime_ns, inode). The copy's argv
   recorded by the test's subprocess spy is `["/bin/cp", "-p", <snapshot>, <scratch copy>]`.
   Mutations: an in-process `shutil.copy2` FAILS (no `/bin/cp` argv); reading the writer slot
   instead of the snapshot FAILS (the argv names `catalog.<S>.duckdb`). {#ac-3}
4. **AC-4 (the gate can fail, one variant per leg; d9br).** A test hook changes
   `rewrite.duckdb` before child 3 runs, and CHECKPOINTs it. Each variant's row says
   `gate: fail` with a diff naming its leg and object, has no band, and the exit code is 1:
   - `rows`: one row deleted (the diff names the table and both counts);
   - `content`: one non-key value changed, counts equal (no `rows` diff);
   - `columns`: one column's type changed; separately one column's DEFAULT changed;
   - `constraints`: a NOT NULL dropped; separately `check-text`, the table rebuilt with
     `CHECK (a > 1)` in place of `CHECK (a > 0)` over the same rows (ONLY the constraint diff);
   - `indexes`: an index re-created under the same name on a different column;
   - `sequences`: one `nextval`;
   - `views`, `macros`, `types`: one of each added.

   A further test pins the precondition (r2 S-1): a fingerprint of an in-session connection that
   has issued a sequence value differs from a fresh read of its own rewrite ONLY on the
   `sequences` leg, and a fresh reopen of the same file matches exactly.
   Mutations: the gate removed FAILS (the row is banded); each leg removed in turn FAILS its own
   variant; `constraint_text` dropped from the query FAILS `check-text`. {#ac-4}
5. **AC-5 (one opener per path; bug-112).** Every DuckDB statement runs in a child. The test
   asserts child 1, child 2 and child 3 each report a pid different from the parent's, and that
   a spy on `duckdb.connect` in the parent process counts zero calls. Mutation: measuring
   in-process FAILS. {#ac-5}
6. **AC-6 (failure is counted).** There are three injected roots, and the middle one has no
   `catalog.read.duckdb`. The middle row has `error: "no snapshot"`, the other two are measured,
   the exit code is 1, and the verdict is `INCOMPLETE`. Mutation: a `continue` that skips the
   missing root without a row FAILS. {#ac-6}
7. **AC-7 (the bands are the pre-registered ones).** The script's band constant equals R3's
   tables: 64 MiB, 0.20, 0.50, 0.10, 30, 120, 1.5 and 5. Mutation: changing any edge FAILS
   this test. {#ac-7}
8. **AC-8 (rehearsal repeats).** `rewrite_s` is the median of 3 runs. With a test hook that makes
   one run take 4× the others, the store is re-run once and, still noisy, reported `noisy`
   with no C band. {#ac-8}

## Test strategy {#test-strategy}

- `tests/test_catalog_measure.py` runs in task 23.0's sandbox (decisions d1a/d1b): `$HOME`, the
  global root, the registry and the LaunchAgents dir are redirected before `refmatrix` is
  imported, and the `roots` list is injected. Synthetic catalogs are real DuckDB files.
- The subprocess spy wraps `subprocess.run` / `Popen` argv recording only; the copies and
  children really run.
- The fleet run (R5) is a hand run, not a test. Its log is captured to
  `workflow/review-output/plan18-catalog-measure-<date>.log`.

## Files to modify {#files-to-modify}

| file | change |
|---|---|
| `eval/catalog_maint/measure_catalogs.py` | new: R1-R3, R6 |
| `tests/test_catalog_measure.py` | new: AC-1..AC-8 |
| `workflow/review-output/plan18-catalog-measure-<date>.{jsonl,md,log}` | the fleet run's output (R2, R5) |
| `workflow/plans/plan-18-duckdb-store-maintenance.md` | the verdict (R5) |

## Revision round 3 {#rev-round-3}

From ch-bsd 18.1 r2 ([[bsd-plan18-task18-1-measurement-r2-34ac5cd]]) M-2 and S-1: the
decision rows d9bh, d9br and d9bv in [[plan-review-2026-10-14]] are folded into the body, so the
spec no longer contradicts the code at `8281a7f`.

| source | change |
|---|---|
| r2 M-2 (status pointer) | header status: script commits `886386b`, `34ac5cd`, `8281a7f`; report `…-20261015-r2.md`, id `plan18-catalog-measure-20261015-r2` |
| d9br / r2 M-2 (gate) | [[#r1]] "The gate": the nine-leg `catalog_fingerprint`, a missing leg is a difference; child 1 measures the fingerprint; per-row `duckdb_version` and the mixed-build refusal |
| r2 S-1 (fresh-open precondition) | [[#r1]] "The gate" states it and points 18.3 at its session-stable sequence leg; [[#ac-4]] pins it with a test |
| d9br (medians, max over every run) | [[#r1]] rehearsal: `rewrite_bytes` = median, `rewrite_s_max` over every run; [[#r2]] per-store `mkdtemp` + `finally`; [[#r6]] any `Exception` / interrupt is a row |
| d9bh (AC-1, AC-2, read-write rewrite child) | [[#ac-1]] 95 %, pinned block counts, `0 < f ≤ r`, 200,000-row margin fixture; [[#ac-2]] 200/80 MiB; [[#r1]] the rewrite child opens read-write |
| d9br / r2 M-1 (one variant per leg) | [[#ac-4]] one variant per leg, including `check-text` |
| d9bv (bytes tolerance) | [[#r4]] `max(2 %, 512 KiB)` |
| r2 M-2 (report id) | [[#r2]] a same-day re-run's GMD id is its suffixed stem |
