---
gmd: "0.1"
id: bsd-plan16-22-spec-diffcheck-r13-be965bb
title: "plan-16 + plan-22 closing diff check r13 (rounds 12-15, d9cf/d9cg/d9ch/d9ci): every r12 finding is closed and every new mutation can fail, but the absorb rule's 'not already absorbed by another tagged append' makes AC-4e's own re-purge variant fail (2 against 1), and the vacuum scan's 'each matched, unabsorbed append' skips the copy a restore was absorbed into (AC-6e counters wrong; restore, re-purge, vacuum, re-ingest holds 2 against 1)"
severity: SKETCHY
plan: plan-16-invisible-grep-shim, plan-22-audited-removal-and-repair
task: spec-diffcheck-r13-16.6-22.2-22.6-17.4
round: 17 (plan-16) / 13 (plan-22)
tags: [bsd, audit, spec-review, diff-check, restore, restated-copy, absorb, vacuum, sidecar, d9cf, d9cg, d9ch, d9ci]
---

# ch-bsd r13 closing diff check: plans 16 and 22, rounds 12-15 {#root}

**Commit reviewed:** HEAD `be965bb` on `wave0-spec-reviews` (confirmed with `git rev-parse`),
plus this run's uncommitted round-15 edit (step 1, d9ci). Diffed against `2352e52` for
`workflow/plans/plan-16-*`, `plan-22-*` and 17.4's pointer lines. `src/` is unchanged.
**Written:** 2026-10-15T05:10-0700.

**Method:**
- Step 1 applied d9ci to `task-22.2-repair-then-remove.md` and `plan-22-audited-removal-and-repair.md` only. See [[#step1]].
- I checked every r12 finding against the text, and checked decisions d9cf, d9cg, d9ch and d9ci.
- I rewrote the r12 model as a live-store simulator. It runs the live ops, the facts.log they write, the dump, the rebuild row pass, the vacuum scan, `revivable` and `restated_copy`, all as the text specifies. Files are in `scratchpad/r13/`:
  - `model13.py` and `fixtures13.py`: 34 fixtures. They cover F1-F8, L1-L3, every AC-4e leg and variant (evidence, link, sidecar, d9ci re-insert; compacted and uncompacted), re-purge variants, a two-manifest shape and F7 variants.
  - `mutations13.py`: every AC-4e and AC-6e mutation.
  - Logs: `out_readings.log`, `out_mutations.log`, `out_reattached.log`, `out_new_variants.log`.
- GMD lint on the two edited files: 0 errors.
- No store or socket was opened, and nothing was committed.

rel: amends -> [[bsd-plan16-22-spec-diffcheck-r12-2352e52]]
rel: specifies -> [[plan-16-invisible-grep-shim]]
rel: specifies -> [[plan-22-audited-removal-and-repair]]
rel: contradicts -> [[task-22.2-repair-then-remove#r4-restate]]
rel: contradicts -> [[task-22.6-removal-entry-points#r5-scan]]

## Step 1: d9ci applied (round 15) {#step1}

**Edits to `task-22.2-repair-then-remove.md`:**
- New R4 bullet `{#r4-reinsert-sidecar}`.
  - When restore re-inserts an `evidence_row` LIVE through its `id_map` (AC-4d's shape), that row's sidecar rows go back through 16.6's `Store.add_learned_provenance`. That is the table's only INSERT path, and 22.5 R2 is the precedent.
  - The one `learned_provenance` event that call logs per inserted row (`row_event`) is the re-log. It comes after the row's own plain `evidence` append and carries the same `ts`.
  - The same rule covers every other evidence row a restore re-inserts live with its sidecar rows (22.6 R3's learned rows).
  - No absorb rule is needed: the purge's `evidence_remove` deleted the old copy and its sidecar rows, both live and on replay.
  - The count is printed as `restore_sidecar_reinserted`. A failed insert or append aborts the restore.
  - The bullet states that a row re-inserted DANGLING is not covered.
- AC-4e: the title is extended, and a *dead-side re-insert sidecar leg* is added (AC-4d's engine purge of `query/foo` with a learned row of `B`, run uncompacted and compacted). Two new mutations are added and traced:
  - "re-insert without re-logging the sidecar";
  - "re-log the re-inserted sidecar before the row's append".
- `#files-to-modify`: the `removal_apply.py` row is updated.
- `#rev-round-14`: the last row is marked CLOSED by d9ci.
- New `## Revision round 15 {#rev-round-15}` section. Its last row records one raised item: the sidecar of a dangling re-insert ([[#m-1]]).

**Edits to `plan-22-audited-removal-and-repair.md`:**
- Status line updated.
- New decision d-36.
- New `## Revision round 15 {#rev-round-15}` section.
- The "raised, not ruled" row of `#rev-round-14` is marked CLOSED by d9ci.

## Round-12 findings and decisions: status {#prior-status}

| item | status | evidence at HEAD |
|---|---|---|
| r12 s-1 / d9cf (revival by reversal) | **closed** | <ul><li>22.2 `#r4-reversal`: one builder and one reader.</li><li>22.6 `#r5-timeline`, `#r5-revivable-fn` and `#r5-reattach-guard`: the guard is removed and `orphan_drop_reattached` is redefined.</li><li>AC-6e has variant 2 and both replacement mutations.</li><li>AC-6f is the AST check.</li><li>d-28, d-30 and d-33 are updated.</li><li>17.4 step 3 names `revivable`.</li></ul> |
| r12 s-2 (vacuous merge-rule mutation) | **closed** | AC-6d replaces the mutation with the count-equivalence note, and the `#rev-round-11` row's rationale is corrected. |
| r12 m-1 (`N` per concept) | **moot** | No `N` remains. |
| d9cg (restating append) | **in the text; one defect** | 22.2 `#r4-restate`, 22.6 `#r5-restated-fn`, AC-4e and AC-9c are present. See [[#s-1]] and [[#s-2]]. |
| d9ch (link and sidecar re-attached in place) | **closed** | <ul><li>22.2 `#r4-relink` is present.</li><li>16.6 R1d states the dead-end skip and adds `provenance_not_dumped`.</li><li>17.4 step 3 names `restated_copy`.</li><li>AC-4e's link and sidecar legs are present.</li><li>All four mutations fail ([[#mutations]]).</li></ul> |
| d9ci (re-inserted sidecar) | **closed by step 1** | [[#step1]]. Both mutations fail in both runs. One adjacent shape is still unruled ([[#m-1]]). |

## Model re-run, text as specified {#model}

I modelled two reading choices; the text admits each of them:
- **Absorb mark.** The text says "not already absorbed by another tagged append" (22.2), "not yet absorbed" (22.6 `restated_copy`) and "marked absorbed". As written, the mark is global. The alternative is a mark kept per manifest.
- **Scan judge.** The text says "asks `revivable` of each matched, unabsorbed append" (22.6 `#r5-scan`). As written, this skips the copy that a tagged append was absorbed into. The alternative skips only the absorbed tagged append.

| fixture | text as written (global mark, scan skips the copy) | global mark, scan judges the copy | per-manifest mark, scan skips the copy | **per-manifest mark, scan judges the copy** |
|---|---|---|---|---|
| AC-4e base, concept-end, multiplicity (compacted and uncompacted) | EQ | EQ | EQ | EQ |
| **AC-4e re-purge variant** (uncompacted) | **DIFF 2 vs 1** | **DIFF 2 vs 1** | EQ | EQ |
| re-purge × multiplicity 2 | **DIFF 4 vs 2** | **DIFF 4 vs 2** | EQ | EQ |
| re-purge, compacted before restore 1 or before restore 2 | EQ | EQ | EQ | EQ |
| AC-4e link leg, sidecar leg (both runs) | EQ | EQ | EQ | EQ |
| AC-4e d9ci leg (both runs; also re-learned before the restore) | EQ | EQ | EQ | EQ |
| AC-4d | EQ | EQ | EQ | EQ |
| **two manifests**: `E` and `C` untracked separately, both restored (either order, with or without a vacuum) | **DIFF 2 vs 1** | **DIFF 2 vs 1** | EQ | EQ |
| AC-6e base, variant 1, variant 2, compacted variant; F5 compacted before restore | EQ (but see the counters below) | EQ | EQ | EQ |
| **F7**: restore, untrack again (not restored), vacuum, re-ingest | **DIFF 2 vs 1** | EQ | **DIFF 2 vs 1** | EQ |
| F7b (re-ingest before vacuum) | **DIFF 2 vs 1** | EQ | **DIFF 2 vs 1** | EQ |
| F7c, F8, L1, L2, restore onto a live-by-name re-ingested `E`, a three-purge chain | EQ | EQ | EQ | EQ |

**AC-6e's printed counters** (`out_reattached.log`):

| reading | base | variant 1 | variant 2 | compacted | what AC-6e expects |
|---|---|---|---|---|---|
| scan skips the copy | 0 | 0 | 0 | 0 | 1 / 1 / 1 / 0 |
| scan judges the copy | 1 | 1 | 1 | 0 | 1 / 1 / 1 / 0 |

- Only "per-manifest mark, scan judges the copy" matches live on all 34 fixtures and produces AC-6e's counters.
- The text as written reads as neither choice.

## Mutations: every new one can fail {#mutations}

These were run under the matching reading (`out_mutations.log`).

| mutation | fixture | result |
|---|---|---|
| re-attach without logging (d9cg) | AC-4e base and concept-end, compacted | **FAILS**: 0 vs 1 |
| the tagged append always adds | uncompacted control | **FAILS**: 2 vs 1 |
| absorb by `row_key` plus `detail` idempotently | multiplicity, compacted | **FAILS**: 1 vs 2 |
| the window ignores reversal of the earlier tombstone | re-purge variant | **FAILS**: 2 vs 1 |
| re-attach a link without logging (d9ch) | link leg, both runs | **FAILS**: 0 links vs 1 |
| log the re-attached link without `weight` | link leg | **FAILS**: NULL vs 0.5 |
| re-attach the sidecar without re-logging it | sidecar leg, compacted | **FAILS**: 0 rows vs 1 |
| log the sidecar event before the restating append | sidecar leg | **FAILS** compacted (unresolved 1). It passes uncompacted, which is correct: the AC claims the compacted run only. |
| **d9ci** re-insert without re-logging the sidecar | d9ci leg, both runs | **FAILS**: 0 rows vs 1 in both runs |
| **d9ci** re-log the re-inserted sidecar before the row's append | d9ci leg, both runs | **FAILS**: unresolved 1, 0 rows, in both runs |
| the predicate ignores reversal (d9cf) | AC-6e base, variant 1, variant 2 | **FAILS**: 0 vs 1 |

17.4's fold calls the same two functions (step 3), so the AC-6d fold-equals-rebuild check inherits these results.

## Findings {#findings}

### SKETCHY s-1: the absorb mark is global, so AC-4e's own re-purge variant fails, and so does a row whose two ends two manifests purged {#s-1}

**Files:**
- `task-22.2-repair-then-remove.md` [[task-22.2-repair-then-remove#r4-restate]]: "ABSORBS the earliest copy still held, and not already absorbed by another tagged append".
- `task-22.6-removal-entry-points.md` [[task-22.6-removal-entry-points#r5-restated-fn]]: "`held` … not yet absorbed" and "is marked absorbed".
- [[task-22.6-removal-entry-points#r5-scan]]: "over the earlier matched, unabsorbed appends".

**What:** a copy, once absorbed, is unavailable to every later tagged append. The re-purge variant then fails as follows:
1. `a0` is absorbed by restore `M`'s `r'`.
2. Restore `M2`'s `r''` finds no available copy.
3. `r''` adds a copy, so the rebuild holds **2 against live's 1**.

The spec's own bullet "a second restore (manifest `M2`) finds it again" relies on the opposite rule. With multiplicity 2, the result is 4 against 2. The same defect hits a shape no AC covers: `E` and `C` are untracked separately (`Me`, `Mc`), and each restore re-attaches the same physical row and logs one tagged append. The rebuild then holds **2 against 1**.

**Why it matters:**
- An implementer who follows the text fails AC-4e's re-purge variant. The cheap way out is to bend that AC, or to switch to idempotence by key, which the spec rejects.
- The two-manifest shape is silent data drift, and no AC covers it.

**Fix: key the mark per manifest.** The model gives EQ on all 34 fixtures, and the multiplicity variant still holds 2.
- **22.2 `#r4-restate`:** replace "and not already absorbed by another tagged\n         append, with the same" with:
  > and not already absorbed by another tagged append carrying the same `restored_from: M` (a copy absorbed under one manifest stays available to another manifest's tagged append: the re-purge variant below, and a row whose two ends two manifests purged), with the same
- **22.6 `#r5-restated-fn`:**
  - Replace "field not compared) and not yet absorbed;" with:
    > field not compared) and not yet absorbed by another tagged append carrying the same `M`;
  - Replace "and is marked absorbed);" with:
    > and is marked absorbed for `M`);
- **22.6 `#r5-scan`:** replace "For a matched append carrying `restored_from` it asks `edge_records.restated_copy` over the earlier matched, unabsorbed appends of the same `row_key` plus `detail`" with:
  > For a matched append carrying `restored_from: M` it asks `edge_records.restated_copy` over the earlier matched appends of the same `row_key` plus `detail` not yet absorbed for `M`
- **22.2 AC-4e:** after the re-purge variant, insert:
  > *Two-manifest variant:* `E` and `C` are untracked separately (`Me`, then `Mc`; the row is orphaned on both ends), and both are restored, in each order, uncompacted. Each restore logs one tagged append, and each is absorbed into `a0`'s copy (each finds it under its own manifest). The rebuild holds the row once, equal to live.

  Add this mutation to the list:
  > "a copy absorbed by any tagged append is unavailable to every other (the mark not keyed by manifest)": the re-purge variant and the two-manifest variant each hold 2 against live's 1.
- **plan-22 d-34:** append "; a copy is absorbed at most once per manifest (r13 s-1)".

rel: contradicts -> [[task-22.2-repair-then-remove#r4-restate]]
rel: contradicts -> [[task-22.6-removal-entry-points#r5-restated-fn]]

### SKETCHY s-2: the vacuum scan skips the copy a restore was absorbed into, so a re-purged, never-restored incarnation is not dropped (F7), and AC-6e's counters read 0 {#s-2}

**File:** `task-22.6-removal-entry-points.md` [[task-22.6-removal-entry-points#r5-scan]]: "After the pass it asks `edge_records.revivable` of each matched, unabsorbed append". `#r5-restated-fn` marks the held COPY absorbed, and `#rev-round-13` says the scan "skips absorbed appends".

**What:** read literally, `a0`, the copy that `r'` was absorbed into, is never judged.
- *AC-6e:* base, variant 1 and variant 2 print `orphan_drop_reattached: 0` against the expected 1.
- *F7 (no AC covers it):*
  1. Restore `M`.
  2. `untrack` again (`M2`, never restored). `M2`'s tombstone after `a0` is not reversed, so `a0` is revivable.
  3. `vacuum` skips `a0` and logs no drop. Live deletes the orphan.
  4. The file is re-tracked (`a1`).

  The rebuild holds `a0` and `a1`: **2 against live's 1**. F7b, with the re-ingest before the vacuum, gives the same result.
- `#r5-restated-fn` itself says the opposite ("its copy is the absorbing append's, which the predicate judges"), so the text contradicts itself.

**Fix:**
- **22.6 `#r5-scan`:** replace "asks `edge_records.revivable` of each matched, unabsorbed append with `T` = the end of the log" with:
  > asks `edge_records.revivable` of each matched append the pass holds as a copy (a tagged append that was absorbed holds none and is skipped; the copy it was absorbed into is judged like any other) with `T` = the end of the log
- **22.6 AC-6e:** add:
  > *Variant 3 (restored, then purged again; r13 F7):* the base's restore, then `untrack` again (`M2`, never restored), `vacuum`, then the file is re-tracked (append `a1`). `vacuum` logs ONE drop keyed `e: E`, which matches `a0` (`M2`'s tombstone after it is not reversed), and prints `orphan_drop_reattached: 0`. A rebuild on a copy holds `E`'s row once, equal to live.

  Add this mutation:
  > "the scan skips the copy a tagged append was absorbed into": variant 3 logs no drop and the copy holds 2 against live's 1; the base prints `orphan_drop_reattached: 0` (expected 1).

  Model: variant 3 gives 1 drop, reattached 0, EQ. Under the mutation: 0 drops, 2 against 1.
- **22.6 files row (tests):** add "AC-6e variant 3".

rel: contradicts -> [[task-22.6-removal-entry-points#r5-scan]]

### MEH m-1: the sidecar of a row restored DANGLING has no specified insert path {#m-1}

**What:**
- 22.2 R4 re-inserts a dangling `evidence_row` (dead-id step (3); also 22.6 R5's vacuum rows, whose AC-6 fixture has a sidecar row) as catalog-only, with no event. The manifest holds its sidecar rows.
- 16.6 R1 makes `add_learned_provenance`, which logs, the table's ONLY insert path.
- An implementer must therefore either:
  - log a `learned_provenance` event the rebuild counts `unresolved_provenance` (a nameless dead concept makes `row_event` raise on an empty `c_kind`), or
  - add a second, non-logging insert that nothing pins.

Step 1 states that d9ci does not reach this case and records it as raised (22.2 and plan-22 `#rev-round-15`).

**Proposed ruling text (22.2 `#r4-reinsert-sidecar`, last sentence):**
> A row re-inserted DANGLING is catalog-only, and so are its sidecar rows: restore inserts them through `Store.add_learned_provenance(rows, log=False)`, the one non-logging call, whose only caller is this branch (16.6 AC-9d's site list pins it). A later rebuild drops both, counted beside the row's own drop.

This needs a matching one-line edit in 16.6 R1's writer-API bullet. An alternative ruling is to not restore a dangling row's sidecar rows, and to count them `restore_sidecar_dangling`. Either is acceptable; the spec must pick one.

rel: depends-on -> [[task-16.6-learned-row-validation#r1]]

## Per-task verdict {#readiness}

| task | verdict | what is left |
|---|---|---|
| 16.1-16.5 | **approval-ready** | none |
| 16.6 | **approval-ready** | Round 14's stated dead-end skip and `provenance_not_dumped` are correct (the model's dump). If [[#m-1]] is ruled with `log=False`, a one-line edit to R1 is needed. |
| 17.4 (pointer lines only) | **consistent** | Step 3 names `revivable` and `restated_copy`. The [[#s-1]] fix changes no 17.4 text. |
| 22.1, 22.1a, 22.3, 22.4, 22.5 | **approval-ready** | none |
| 22.2 | **needs one edit pass** | [[#s-1]] (`#r4-restate`, AC-4e two-manifest variant and mutation); a ruling on [[#m-1]] |
| 22.6 | **needs one edit pass** | [[#s-1]] (`#r5-restated-fn`, `#r5-scan`); [[#s-2]] (`#r5-scan`, AC-6e variant 3 and mutation, tests row) |

## Verdict {#verdict}

DIRTY: 3 findings (0 BULLSHIT, 2 SKETCHY, 1 MEH).

- All r12 findings are closed.
- d9cf, d9ch and d9ci (step 1) are fully in the text, and every new mutation goes RED on the fixture it names.
- d9cg's absorb rule has a marking defect ([[#s-1]]) and a scan-reading defect ([[#s-2]]). Both are wording fixes, and the per-manifest, judge-the-copy reading matches live on all 34 modelled fixtures.
- Plan-16 is approval-ready. Plan-22 is not, until the s-1 and s-2 edits land and [[#m-1]] is ruled.

rel: contradicts -> [[task-22.2-repair-then-remove#acceptance]]
