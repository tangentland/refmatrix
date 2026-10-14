---
gmd: "0.1"
id: task-22.3-bug-086-global-repair
title: "Task 22.3: bug-086 as the first live apply — the global store's unresolvable relative rows and the 1,655 pytest-tmp entities, with the 48 ambiguous kept"
tags: [task, repair, global-store, bug-086, bug-101, wave-1]
metadata:
  node_type: task
  status: pending
  created: 2026-10-07
  revised: 2026-10-14
---

# Task 22.3: the global-store repair {#root}

> Plan: [plan-22-audited-removal-and-repair](../plan-22-audited-removal-and-repair.md)
> Status: Pending (revision round 2, 2026-10-14; [[#rev-round-2]])
> Wave: 1, last of plan-22's Wave-1 chain (16.6 slice → 22.1a → 22.2 → 22.5 → 22.3; #t8-wave1).
> Depends on: 22.1a, 22.2, 22.5 (the 476 resolved entities), 23.1, 23.0; the user's confirmation
> of the dry-run counts. The remedy that stopped new relative global rows is deployed (0.77.x).

rel: part-of -> [[plan-22-audited-removal-and-repair]]
rel: depends-on -> [[task-22.1a-provenance-free-classes]]
rel: depends-on -> [[task-22.2-repair-then-remove]]
rel: depends-on -> [[task-22.5-cross-store-move]]
rel: amends -> [[project_global_relative_rows_repair]]
rel: derives-from -> [[plan-review-2026-10-14#t1]]
rel: derives-from -> [[plan-review-2026-10-14#t8-revisited]]
rel: derives-from -> [[plan-review-2026-10-14#t9]]
rel: amends -> [[bsd-plan16-22-spec-rereview-32dde06]]

## Why {#why}

The global store (`~/.refmatrix`) holds 1,087 relative learned entities (probe log; the 5,159
evidence rows are a sourced, not re-measured, figure). About 700 read as unreadable on every global
grep (bug-086; probe `exists@0: 695`). The 2026-10-07 decision ("recover 476, forget 611") is
replaced by the 2026-10-14 decisions:
- the 48 ambiguous entities are KEPT (d6a);
- the uniquely verified entities (476 at the probe) are handled by [[task-22.5-cross-store-move]]
  (d6b/d8c); those under no project store are held there until the user rules (d9b);
- of the entities with no verifying walk candidate (563 at the probe), those that still read
  correctly today at `$HOME/<rel>` are `orphan-root:home-readable` (22.1a) and are held by 22.5 for
  the same ruling (d9b); only the rest, `orphan-root:unresolved`, are forgotten here through the
  audited path, restorable;
- the 1,655 `pytest-of-*` tmp entities the suite wrote into the live global store (22 #b-8; 143,108
  `facts.log` events, `query/ERROR` and `query/alpha`) are removed in the same audited apply (d1c);
- the 235 fixture rows in the live `query.log` are NOT removed here: they are log rows, not catalog
  rows (d8d, mark-and-filter by readers). {#why-body}

## Requirements {#requirements}

1. **R1 Audit on a copy, then re-audit live.** Run `removal_audit` (22.1a) on a `cp` of the global
   store's `catalog.read.duckdb` snapshot (22.1a AC-5b's operator procedure; s-3), not on a clone
   of a writer slot. The plan's buckets (applied split, counts measured, the probe's figures only
   for comparison): `orphan-root:unresolved` (removed here), `orphan-root:home-readable` (held by
   22.5 for the user's ruling, d9b), `ambiguous:root` (≈ 48, kept), `missing-file` under
   `/pytest-of-` (≈ 1,655), `orphan-root:resolved` (moved by 22.5, or still `held` /
   `held_for_ruling`). The probe split must be reproduced as 22.1a AC-5b states. Then
   `removal_audit` runs against the live global daemon (read-only) to produce the manifest the
   apply will take; its counts must match the copy's within the drift it explains.
2. **R2 Backup and confirmation.** An APFS clone of `~/.refmatrix` is taken before the apply and
   its path recorded in the manifest. The user confirms the live dry-run counts per bucket and the
   manifest hash before the apply.
3. **R3 Apply through 22.2.** `rmx removal apply --root ~/.refmatrix --manifest ID --confirm
   HASH`. `--root` is the global STORE root, `~/.refmatrix`, the value 22.2 R8 compares with the
   daemon's `Path(d.root)` (m-8); `$HOME` is refused. Removals are row-level with events and the
   intent-log manifest; entities are purged only under 22.2 R2/R5. The 48 are written into the
   manifest's `kept: ambiguous` list with all their candidate roots (d6a); the `home-readable`
   entities into `held_for_ruling` (d9b). No relative row is rewritten into an absolute global
   entity (22 #s-3).
4. **R4 Unchanged memory.** The global store's `kind=memory` row count and content hashes are equal
   before and after.
5. **R5 The pytest concepts.** `query/ERROR` and `query/alpha` keep any link that is not a
   pytest-tmp entity; the concepts themselves are not removed by this task (an emptied concept is
   an `empty-learned` candidate for a later 22.1 audit, behind the gate).

## Acceptance criteria {#acceptance}

1. **Counts confirmed.** The copy's and the live dry run's per-bucket counts are reported, the probe
   split is reproduced (22.1a AC-5), and the user's confirmation of the counts and the manifest
   hash is recorded before the apply.
2. **The symptom, not the touched rows (22 #s-7).** A pattern set is pre-registered in the dry-run
   manifest before the apply: `ERROR`, `alpha`, plus every `query/*` pattern linked to an
   `orphan-root` or pytest-tmp entity. For that set, the TOTAL global `unreadable` count reported by
   `rmx grep` is measured before and after. After: every residual `unreadable` row is explained by
   class (the 48 `ambiguous:root`, 22.5's `held` / `held_for_ruling` rows, or a named new row),
   and the count of
   unexplained residuals is 0. bug-086 is marked `fixed` only on that result.
3. **Memory untouched.** R4's count and hashes are equal.
4. **Restorable.** On the backup clone (never live), `restore` of the manifest returns the
   pre-apply state by name (22.2 AC-4).
5. **Nothing kept is lost.** All 48 ambiguous entities are present after the apply, with their
   rows.
6. **Only the named root.** The apply was invoked with `--root` naming the global store; a dry
   rehearsal in the sandbox shows the op refuses without it (22.2 AC-11).

## Test strategy {#test-strategy}

The engine's tests are 22.2's and 22.5's, inside task 23.0's sandbox (d1a/d1b). This task adds a
sandbox rehearsal: a fixture global store seeded with relative, ambiguous, pytest-tmp and memory
rows, run through the exact command sequence of R1-R3 against an in-process daemon with
`$HOME`/global root redirected; no `rmx` subprocess, the 23.0 guard active. The live apply is an
operator step (R2), never run by a test. Mutation for AC-2: measuring `unreadable` only over the
rows the apply touched must FAIL on the rehearsal fixture (it hides a seeded residual).

## Revision (2026-10-14 decision log) {#rev-2026-10-14}

| finding / decision | answered in |
|---|---|
| d1c as amended by d8d (1,655 removed here; 235 log rows not) | [[#why]], [[#requirements]] R1, R5 |
| d6a (48 kept) | R3; AC-5 |
| d6b / d8c (476 via 22.5) | [[#why]]; R1 |
| d6d (Wave 1, no 16.6 R1) | [[#root]] |
| 22 #b-4 (count composition, probe reproduced) | R1; AC-1 |
| 22 #b-8 (pytest rows; explicit root) | [[#why]]; R3; AC-6; [[#test-strategy]] |
| 22 #s-3 (no rewrite into global) | R3 |
| 22 #s-7 (symptom AC) | AC-2 |
| DL #b-3 (rewrite R3; 22.3's prerequisites in Wave 1) | [[#root]]; R3 |

## Revision round 2 (2026-10-14) {#rev-round-2}

The re-review found 22.3 sound "modulo m-8" ([[bsd-plan16-22-spec-rereview-32dde06]]); these rows
carry its other plan-22 items into this task.

| finding / decision | answered in |
|---|---|
| re-review m-8 (`--root ~/.refmatrix` vs `$HOME`) | R3 (the store root; `$HOME` refused); 22.2 R8 |
| d9b / re-review s-2 (rows readable today under no project store) | [[#why]]; R1 `home-readable` bucket held; R3 `held_for_ruling`; AC-2 residual classes |
| re-review s-3 (census on a live clone) | R1 audits a `cp` of `catalog.read.duckdb` (22.1a AC-5b) |
