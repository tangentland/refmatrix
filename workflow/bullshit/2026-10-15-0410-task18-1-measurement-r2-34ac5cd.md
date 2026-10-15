---
gmd: "0.1"
id: bsd-plan18-task18-1-measurement-r2-34ac5cd
title: "ch-bsd task 18.1 r2: all 12 r1 findings closed; 24 of 26 mutations killed; the fingerprint's sequence leg only holds between two fresh opens, so 18.3's in-session gate as specced fails every reclaim"
tags: [ch-bsd, plan-18, task-18.1, duckdb, measurement, gate]
severity: SKETCHY
plan: plan-18-duckdb-store-maintenance
task: task-18.1-catalog-measurement
---

# ch-bsd findings — task 18.1 catalog measurement, round 2 {#root}

**Commits:** `886386b`, `34ac5cd` on `8a93ab1` (clone `/Volumes/littlebig/refmatrix-task-18.1`,
branch `task-18.1-catalog-measurement`). Decision side: d9bp, d9bq, d9br, d9bt, d9bv, d9bw in
`workflow/plan-review-2026-10-14.md`; the task-18.1/18.2/18.3 specs and the plan-18 status lines
(main tree, `wave0-spec-reviews` @ `451b505` + uncommitted 18.2/18.3 edits).
**Date:** 2026-10-15T04:10:12-0700
**Author:** Todd Holley / Opus 5.5 / orchestrator
**Files changed:** 2 (`eval/catalog_maint/measure_catalogs.py`, `tests/test_catalog_measure.py`)

rel: evidence-for -> [[task-18.1-catalog-measurement]]
rel: amends -> [[bsd-plan18-task18-1-measurement-r1-8a93ab1]]

## Method {#method}

- Tests: 27 passed in 24.5 s (`.venv-eval`, duckdb 1.5.2), log
  `/Volumes/littlebig/refmatrix-task-18.1/workflow/review-output/bsd181r2-tests.log`.
- Mutations: 26 run on the clean clone at `34ac5cd` (the fix is committed). Each was applied, the
  file was run, then restored by `git checkout` in its own command and `__pycache__` was cleared.
  The clone is clean at `34ac5cd`. Logs are `bsd181r2-m-<name>.log`.
- Probes: run with the deploy interpreter (duckdb 1.5.3) on a `/bin/cp -p` copy of the refmatrix
  snapshot (832,843,776 B) under `/private/tmp/claude-501/bsd181r2/`. No live file was opened
  in-process, no socket was touched, and the scratch is deleted.

## r1 findings: all closed {#r1-closed}

| r1 | Closed by | Evidence |
|---|---|---|
| B-1 | d9bp (a), plus the 18.3 prerequisite "bug-112 FIXED and reachable from master", plus the sentinel read-back (18.3 R4 step 5, I4) | spec text |
| B-2 | d9bp (b) and d9bw (b): no offline route; the store is refused `rewrite_too_slow` and gets an honest terminal state (hot row, bug row, user decides) | spec text |
| S-1 | d9bp (c), d9bt Q-D/Q-E, 18.3 R14 (loaded hold in a tmp daemon with 6 readers; `interruptible`; RSS stated) | spec text |
| S-2 | d9bq + d9bw (a) (baseline = `rewrite_bytes`, plus the 64 MiB floor); 18.2 `:87-91` uses the same definition | spec text |
| S-3 | `catalog_fingerprint` / `gate` with nine legs, and one AC-4 variant per leg | each leg's removal is killed by its own variant (see `#mutations`) |
| S-4 | AC-1 pins total/used/free/`f` to the test's own `pragma_database_size` | `free:=used` killed |
| S-5 | AC-1 is 95 % deleted; `rewrite_bytes` = median of the runs; d9bv tolerance | 12 of 12 repeats OK, big r 0.862-0.883, full r ≤ 0.014 (`bsd181r2-ac1-repeat.log`); median→last killed |
| M-1 | d9bq: range 0.115-0.657, thiquet named, no cause claimed | spec text |
| M-2 | `rewrite_s_max` over every run | final-batch-only killed |
| M-3 | `mkdtemp` work dir per store, `rmtree` in a `finally`, any `Exception` becomes a row, interrupt rows | rmtree(scratch), no-finally, no-Exception-row and no-interrupt-rows all killed |
| M-4 | `duckdb_version` per row plus a refusal when versions mix; `store_name` → "global" | removing the version check is killed; r2 fleet shows `global` and 1.5.3 on all 8 rows |
| M-5 | task-18.1 `status: in-progress`; plan-18 status line says IN-PROGRESS | spec text (pointer is stale, see `#m-2`) |

The r2 fleet re-run reproduces r1's bands and verdict: 8/8 gates pass under nine legs, every row
is duckdb 1.5.3, and `in_daemon_feasible` is True (idle). d9bv's spread checks out: orderly
12,070,912 → 12,333,056 B = 2.17 %, one 256 KiB block, and that fits inside `max(2 %, 512 KiB)`.

## Mutations {#mutations}

24 of 26 mutations were killed.

**One leg removed at a time.** Each of `content`, `columns`, `constraints`, `indexes`,
`sequences`, `views`, `macros` and `types` is killed by its own AC-4 variant.

**Leg internals, each killed:**
- index NAMES only (sql dropped);
- `data_type` dropped;
- `column_default` dropped;
- `bit_xor` instead of `sum`, caught by the duplicate-rows test.

**The `rows` caveat is acceptable.** Removing the leg is caught first by the `KeyError` at
`row["rows"] = sum(...)`. I also ran it with that line changed to `0`, so the `KeyError` path
was gone. `test_ac4_gate_can_fail` still failed, because it asserts the `rows main.entities:
copy=1000 rewrite=999` diff by name. So the leg has its own killer whichever way the code
changes (`bsd181r2-m-rows-nokeyerror.log`). The content leg would also flag a dropped row on its
own.

**Two survived:**
- `constraint_text` dropped from the query (see `#m-1`).
- `last_value` dropped from the sequence leg. Here the variant's `nextval` also moves
  `start_value` on reopen, so another field of the same leg catches it. That redundancy is
  harmless. It is also the clue that led to `#s-1`.

## Fingerprint cost {#cost}

Measured on the refmatrix snapshot copy (2,291,703 rows; `linkage_evidence` 1.13 M rows /
186 MB of text) with the deploy interpreter, duckdb 1.5.3:

| Condition | Full `catalog_fingerprint` |
|---|---|
| warm, idle | 0.064 / 0.069 / 0.081 s |
| under 6 concurrent read loops | 0.098-0.129 s |

The largest per-table content hash was 0.057 s (entities), and 0.103 s single-threaded. Two
fingerprints, one per side, cost under 0.3 s loaded. That is about 5 % of 18.3's 5 s Phase A
budget, so cost is not a concern.

## Findings {#findings}

### SKETCHY: the sequence leg only holds between two FRESH opens; 18.3's in-session gate as specified fails every reclaim {#s-1}

**File:** `eval/catalog_maint/measure_catalogs.py` (`catalog_fingerprint`, sequences leg,
docstring "Plan-18.3's reclaim gates its swap on this function"); task-18.3 R5 `#r5-gate`
("every sequence's last value is equal").

**What:** 18.1 compares two fingerprints, both read by fresh read-only children. In that setup
the sequences leg is right: on a fixture, copy and rewrite both read `seq_entities_id` (201,
201). 18.3 R5, however, runs the gate inside the hold. It compares the live writer connection's
database with the ATTACHed rewrite (`h.gate("rc")`, R4 Phase A step 4).

**Why it's sketchy:** DuckDB's `duckdb_sequences()` reports different numbers for the same
state, depending on how the database was opened. I probed with duckdb 1.5.3:
- **Fresh open after a checkpoint:** `(start, last) = (6, 6)`, and the next id issued is 6.
- **After the daemon issues id 6:** still `(6, 6)`, although the next id is now 7.
- **The rewrite, read in the same session:** `('n', 7, 7)` against the live `(6, 6)`. Reopened,
  it issues 7, so the data is correct.
- **First case, created and used in one session:** live `[1,…,5]`, rewrite `[6,…,6]`.

`catalog_fingerprint` taken on the live connection and compared with `gate()` against a
fresh-read rewrite gave `sequences main.sq: copy=[1, …, 5] rewrite=[6, …, 6]`. The same live
file reopened gave `[]`.

A daemon issues ids from the moment it opens its writer. So 18.3's gate, as specified, refuses
every real reclaim. This failure is safe (it fails closed), but the 18.1 code tells 18.3 to
reuse this exact function and "not grow a second gate". The likely cheap fix under pressure is
to drop the sequence leg, and that would let a rewrite that really lost sequence state through.
The metadata alone cannot express "next value" in a used session (`currval` reads 6 both before
and after id 6 is issued), so the fix is a definition change, not a field swap. 18.1's tests
never see this: every fingerprint they take comes from a fresh open.

**Fix:**
- **In 18.1, before merge:** the docstring states the precondition ("both fingerprints from fresh
  opens of checkpointed files; on a live session `duckdb_sequences()` is not comparable"). Add a
  test that pins it: fingerprint a used in-session connection against its rewrite, and assert the
  only diff is the sequences leg.
- **In 18.3 R5** (route to the plan-18 spec reviewer): define the sequence leg on invariants that
  hold in a session. Other fields are equal, and two conditions hold:
  - `rewrite.start_value >= live.last_value`;
  - `rewrite.start_value >` the max of every column whose default is `nextval(<seq>)`.
- **Add an 18.3 AC** that runs the gate on a daemon-shaped session that has issued ids.

**Pattern match:** YES. This repeats `#imp-181-child-vs-inproc`: a property measured in fresh
children is handed to an in-process design.

rel: contradicts -> [[task-18.3-offline-reclaim#r5-gate]]

### MEH: no variant changes a CHECK's text; dropping `constraint_text` survives {#m-1}

**File:** `tests/test_catalog_measure.py` `_AC4_VARIANTS["constraint"]`

**What:** The only constraint variant drops a NOT NULL. That removes the whole row, so
`constraint_type` alone still catches it. r1 named "CHECK text" explicitly, and d9br says
"constraint text".

**Fix:** Give `fp_probe` a `CHECK (a > 0)`. Add a variant that rebuilds `fp_probe` with
`CHECK (a > 1)` over the same rows, and assert a `constraints main.fp_probe:` diff. With that in
place, dropping `constraint_text` must fail.

### MEH: the 18.1 spec body and 18.3 AC-7 still carry the r1 text the code now contradicts {#m-2}

**Files:** `workflow/plans/plan-18-duckdb-store-maintenance-tasks/task-18.1-catalog-measurement.md`
(`:16`, `:138-140`, `:204`, `:228-233`, `:241-243`); task-18.3 `:774`; the r2 report frontmatter.

**What:** The amendments exist only as decision rows:
- the status line points at `8a93ab1`, not at `34ac5cd` and the `-r2` report;
- "The gate" (`:138`) still describes the counts-only gate, and 18.3 R5 links to it as the
  shared definition;
- AC-1 still says 90 % and `f ≥ 0.80`;
- AC-2 still says 100/40 MiB;
- AC-4 still has one variant;
- R4 still says "within 1 %";
- 18.3 AC-7 says "within 2 %", not d9bv's `max(2 %, 512 KiB)`;
- the r2 report reuses the r1 report's GMD id `plan18-catalog-measure-20261015`, so two docs
  share one node id.

**Fix:**
- Fold d9bh/d9br/d9bv into the 18.1 spec body, with a pointer per amendment.
- Point the status line at `34ac5cd` and the r2 report.
- Write d9bv into 18.3 AC-7.
- Give the r2 report the id `plan18-catalog-measure-20261015-r2`. `render_md` already takes the
  day; add a suffix argument.

## Verdict {#verdict}

3 findings (0 BULLSHIT, 1 SKETCHY, 2 MEH).

The r2 remedy is real. Every r1 finding is closed with evidence, 24 of 26 mutations are killed,
AC-1 is stable (12/12), scratch handling is safe, versions are recorded, and the fingerprint
costs about 0.1 s on refmatrix under load.

Merging needs `#s-1`'s 18.1 half: the docstring precondition plus one pinning test. The 18.3 R5
re-definition goes to the plan-18 spec loop. `#m-1` and `#m-2` are small and can ride the same
commit.

rel: contradicts -> [[task-18.3-offline-reclaim#r5-gate]]
rel: related-to -> [[impression_bsd_cost_measured_idle]]
