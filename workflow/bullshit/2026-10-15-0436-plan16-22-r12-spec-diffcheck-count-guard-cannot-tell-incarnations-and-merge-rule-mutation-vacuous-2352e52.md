---
gmd: "0.1"
id: bsd-plan16-22-spec-diffcheck-r12-2352e52
title: "plan-16 + plan-22 spec diff check r12: round 11 (2352e52) closes all 4 r11 findings and plan-16 is approval-ready. The L > N count guard passes F1-F4 and AC-6b/6c but fails a fifth shape (untrack, re-ingest, untrack, restore) because a count cannot say which incarnation was re-attached. One AC-6d substitute mutation cannot fail under 17.4's set fold."
severity: SKETCHY
plan: plan-16-invisible-grep-shim, plan-22-audited-removal-and-repair
task: spec-diffcheck-r12-16.6-22.2-22.6
round: 16 (plan-16) / 12 (plan-22)
tags: [bsd, audit, spec-review, diff-check, vacuum, orphan-drop, restore, reattach, fold-ops, d9cc]
---

# ch-bsd r12 diff check: plans 16 and 22 after revision round 11 (`2352e52`) {#root}

**Commit reviewed:** HEAD `2352e52` on `wave0-spec-reviews` (confirmed with `git log -1`), diffed
against `d8188ee` for `workflow/plans/plan-16-*` and `plan-22-*`: 4 files, +185/-37. `src/` is
unchanged. **Written:** 2026-10-15T04:36-0700.

**Method (read-only):**
- I checked every r11 finding and decision d9cc against the text at HEAD.
- I re-ran the r11 model, rewritten to follow the text as now specified. The new copy is
  `scratchpad/r12/reattach_model_r12.py`. It keys the drop on the entity end and applies the
  `L > N` guard with `N` exactly as written, plus a variant `N` per concept. It also runs every
  AC-6e mutation and two new shapes, F5 and F6.
- `scratchpad/r12/reversal_model.py` models the fix proposed in [[#s-1]].
- `scratchpad/r12/fold_rename_model.py` models AC-7's merge under 17.4's fold as 17.4 specifies
  it: a set fold.
- GMD lint on the 4 changed files: 0 errors.
- No store or socket was opened. No spec was edited and nothing was committed.

rel: amends -> [[bsd-plan16-22-spec-diffcheck-r11-d8188ee]]
rel: specifies -> [[plan-16-invisible-grep-shim]]
rel: specifies -> [[plan-22-audited-removal-and-repair]]
rel: contradicts -> [[task-22.6-removal-entry-points#r5-reattach-guard]]
rel: contradicts -> [[task-22.6-removal-entry-points#acceptance]]

## Round-11 findings: status {#prior-status}

| r11 id | status | evidence at HEAD |
|---|---|---|
| s-1 (i): the drop carries the entity end | **closed** | <ul><li>22.6 `#r5`, `#r5-own-appends`, `#r5-timeline`, "The fold", and the files rows for `store.py`, `edge_records.py` and `factslog-restore.py` are all updated.</li><li>16.6 "Spelling" and "Key" are updated, and AC-9d now raises on `e=None` for every op.</li><li>d-28 and d-30 are amended.</li><li>No stale "null entity end" or "concept-side fields only" wording is left outside the history tables.</li></ul> |
| s-1 (ii): the `L > N` guard | **in the text; incomplete** | `#r5-reattach-guard`. See [[#s-1]] (a fifth shape) and [[#m-1]] (`N` is not defined per concept). |
| s-1 (iii): AC-6e | **closed** | Base, variant, three mutations and the `L >= N` boundary are all present. Every one is traced in [[#model]]. |
| s-2 (i) and (ii): rename links logged, fold rule | **closed** | <ul><li>22.2 R2 logs `unlink` / `link` for each re-attached link.</li><li>The R3 replay sentence and the fold row are updated.</li><li>AC-7 adds live == rebuild and a mutation; its trace is correct (`links_skipped_dead`).</li><li>d-32 is amended.</li></ul> |
| s-2 (iii): AC-6d fixtures and mutation | **fixtures closed; departure partly refuted** | See [[#departure]] and [[#s-2]]. |
| m-1: d9cb cited, (c) noted | **closed** | 22.6 and plan-22 `#rev-round-10` rows; the `c_kind` bullet carries the 0-drift measurement. |
| m-2: "unresolved" ambiguous | **closed** | "among the revivable appends only". |

## Model re-run, text as specified {#model}

Each cell compares the rebuild with live, by name.

| fixture | spec (`L > N`, `N` as written) | `N` per `c` | no guard | drop w/o entity end (guard kept) | c-match only | `L >= N` |
|---|---|---|---|---|---|---|
| F1 | EQ | EQ | DIFF | — | EQ | EQ |
| F2 = AC-6e base | EQ | EQ | **DIFF** (mutation fails, as claimed) | — | **DIFF** (as claimed) | EQ |
| F3 | EQ | EQ | DIFF | — | DIFF | EQ |
| F4 = AC-6e variant | EQ | EQ | DIFF | **DIFF**: rebuild `{}` against live 1 (as claimed) | DIFF | EQ |
| L1, AC-6b base | EQ | EQ | EQ | — | EQ | EQ |
| L2, AC-6b swapped | EQ | EQ | EQ | — | EQ | **DIFF**: 2 against 1 (the boundary mutation fails, as claimed) |
| L3, AC-6c(a) | EQ | EQ | EQ | — | EQ | EQ |
| **F5**: untrack, re-ingest, untrack, restore | **DIFF**: 2 against 1 | DIFF | DIFF (0) | — | DIFF | DIFF |
| F6: `(C2,k)` re-appended, `(C,k)` re-attached | **DIFF** (E's `C` copy lost) | EQ | DIFF | — | DIFF | EQ |
| F7: reversed, then re-purged and re-ingested | EQ | — | — | — | — | — |

- All four r11 shapes pass, and so do AC-6b base, AC-6b swapped and AC-6c(a).
- Every AC-6e mutation fails on the fixture it names, and so does the `L >= N` boundary.
- What is left is F5 ([[#s-1]]) and F6 ([[#m-1]]).

## The reviser's departure on r11 S-2(iii) {#departure}

The reviser made three claims. My verdict on each, modelled in `fold_rename_model.py` on AC-7's
merge (old `O` into surviving `S`; `O` links `C1`, which `S` lacks; each holds one evidence row):

| claim | verdict | evidence (entities, links, evidence) |
|---|---|---|
| "The fold keeps a merged rename's links on the old key" cannot fail, because 17.4 counts an edge only when both ends are alive | **The stated reason is false. Dropping the mutation is still acceptable.** | <ul><li>Leaving the rename's `unlink` / `link` pair unapplied gives (3, **1**, 2) against the rebuild's (3, 2, 2). The links left on the dead old key are exactly why it fails.</li><li>Still, the rule at HEAD gives the fold no rename-specific link code. Links follow their generic events, so the mutation has nothing distinct to mutate. Accept the drop; correct the rationale ([[#s-2]]).</li></ul> |
| Substitute 1: round 10's merge rule makes AC-7's `entities` one lower | **Refuted: the mutation is vacuous** | <ul><li>17.4 R6 step 3 defines a set fold: "an entity alive unless its last event is a tombstone".</li><li>Marking `O` dead at the rename and then tombstoning it is idempotent, and moving `O`'s links duplicates the `link` events.</li><li>Result: (3, 2, 2), equal to the rebuild, so the mutation passes AC-6d.</li><li>It goes RED only if the fold is rewritten as a decrementing counter. That would bend 17.4's fold to fit the test.</li></ul> |
| Substitute 2: "the fold ignores `entity_rename`" makes evidence lower | **Accepted** | (3, 2, **1**) against (3, 2, 2). The unmoved copy stays on the tombstoned key. |

## Findings {#findings}

### SKETCHY s-1: the `L > N` count guard cannot tell which incarnation a restore re-attached (F5) {#s-1}

**File:** `task-22.6-removal-entry-points.md` [[task-22.6-removal-entry-points#r5-reattach-guard]],
`#r5-timeline`, AC-6e.

**What happens.** The F5 sequence is AC-6b swapped followed by AC-6e, before one nightly vacuum:
1. `E` appends `a(-1)`.
2. `rmx untrack` logs tombstone `t1`. `a(-1)`'s row is orphaned under dead id1.
3. The file is re-tracked. `E` is re-created and appends `a0`.
4. `rmx untrack` again logs tombstone `t2`.
5. `removal restore` of the `t2` manifest re-attaches `a0`'s row in place. Only this manifest's `id_map` is used, so `a(-1)`'s row stays orphaned under id1 (22.2 R4).

**At vacuum time:**
- Both appends are revivable, `L = 1` and `N = 0`, so the guard skips both. No drop is logged.
- The rebuild revives `a(-1)` and `a0`: **2 against live 1**.

**Why the alternatives fail too:**
- Without the guard, a drop keyed `e: E` deletes both copies, because both have a tombstone after them: **0 against 1**.
- No count-based rule can pick the right copy. The copies are identical by `row_key` plus
  `detail`, and both have a tombstone after them. Only the restore knows that `t2`, and not `t1`,
  was undone.

**Impact.** There are 0 rows today, since no matched append is revivable (r11 `ownapp.py`). The
shape needs only operations the specs ship (22.6 R2 `untrack`, sync re-track, 22.2
`removal_restore`), and nothing catches it: AC-6b swapped and AC-6e each pass alone. This is the
fifth round in which the vacuum drop's identity has been too coarse in one dimension: concept (r9),
timeline (r10), entity (r11), incarnation (r12).

**Fix: make the reversal exact, and replace the count guard.** `reversal_model.py` gives EQ on
F1-F8, L1, L2 and L3, with no `L` or `N` at all.

**(i) 22.2 [[task-22.2-repair-then-remove#r4]].** After "Each re-attached row is counted
`restore_reattached` by kind.", insert:
> Every `tombstone` a manifest-writing purge logs (the engine's batches; 22.6 R2/R3 and the
> `--as-memory` conversion) carries `manifest: <apply_id>`. The `entity` event with which restore
> re-creates an entity carries `restored_from: <apply_id>`. From that event on, a tombstone whose
> `manifest` it names is REVERSED: its incarnation's surviving copies were re-attached in place
> ([[task-22.6-removal-entry-points#r5-timeline]]). Both fields are additive. Replay and 17.4's
> fold ignore them except in the revivable predicate.

**(ii) 22.6 `#r5-timeline`.** Replace "whose entity key `(partition, e_kind, e)` has a `tombstone`
AFTER `a` and at or before `T`" with:
> whose entity key `(partition, e_kind, e)` has a `tombstone` AFTER `a` and at or before `T` that
> is not REVERSED at or before `T` (an `entity` event at or before `T` whose `restored_from`
> equals that tombstone's `manifest`; [[task-22.2-repair-then-remove#r4]])

Make the same edit in "The fold" bullet and in the `factslog-restore.py` files row. The scan
uses `T` = now, as before.

**(iii) 22.6 `#r5-reattach-guard`.** Replace the paragraph's body, from "For a matched revivable
append" through "the guard's boundary (`L = N = 1` … drop logged);", with:
> A matched append whose every tombstone after it is reversed (its incarnation was re-attached in
> place by 22.2 R4's `id_map`, with no new append) fails the predicate, so it is not collected. It
> is counted `orphan_drop_reattached` (once per such append) and printed. An orphan key whose
> every tombstoned append is reversed logs no drop and is also counted `orphan_drop_unlogged`.
> No catalog count is read. An earlier incarnation of the same name, whose tombstone was not
> reversed, is still collected (AC-6e's second variant).

The trailing "AC-6e is its firing case." stays.

**(iv) AC-6e.**
- In the base: replace "(`a0` is revivable, since `E`'s tombstone follows it, but `E` is live with
  `L = 1` against `N = 0`)" with "(`E`'s tombstone after `a0` is reversed by the restore's
  `entity{restored_from}`)".
- Add a second variant:
  > *Variant 2 (two incarnations):* `E` appends `a(-1)`; `untrack`; the file is re-tracked (append
  > `a0`); `untrack` again; `removal restore` of the second manifest. `vacuum` logs ONE drop keyed
  > `e: E`, which matches `a(-1)` only, and prints `orphan_drop_reattached: 1`. A rebuild on a copy
  > holds `E`'s row once, equal to live.
- Replace the mutation "no `L > N` guard" with:
  > "the predicate ignores reversal": the base collects `a0`, and the copy loses `E`'s row.
- Replace the boundary mutation "guard on `L >= N`" with:
  > "the count guard `L > N` instead of reversal": variant 2 logs no drop, and the copy holds 2.
- Keep "drop without the entity end" and "d9cb(b)'s `c`-match only" unchanged. Both still fail
  as traced.

**(v) Matching edits.**
- d-28: append "a tombstone a later restore reversed (`restored_from`) does not count (r12 s-1)".
- d-30: replace "a re-attached copy (`L > N`) is not collected" with "a copy whose tombstones a
  restore reversed is not collected".
- 22.2's `store.py` / `removal_apply.py` files rows: add "`manifest` on purge tombstones;
  `restored_from` on restore's `entity` events".

This supersedes d9cc (ii), so the orchestrator needs to rule on it.

rel: contradicts -> [[task-22.6-removal-entry-points#r5-reattach-guard]]
rel: depends-on -> [[task-22.2-repair-then-remove#r4]]

### SKETCHY s-2: AC-6d's "round 10's merge rule" mutation cannot fail under 17.4's set fold {#s-2}

**File:** 22.6 AC-6d; 22.6 `#rev-round-11`, the s-2(iii) row.

**What:** see [[#departure]]. Under the fold 17.4 R6 step 3 specifies, the mutation leaves AC-7's
counts equal to the rebuild's. A pre-registered mutation must go RED. This one can be made to fail
only by turning 17.4's set fold into a counter: that would bend the code to fit the test, a cheap
fix the spec would invite.

**Fix, two edits:**
- **In AC-6d,** delete from "; \"the fold keeps a merged rename's links and entity on the old
  key\"" through "already removed it)", leaving "the fold ignores `entity_rename`" as the rename
  mutation, then insert:
  > Round 10's merge rule (drop the old key, move its links) is count-equivalent to this rule
  > under 17.4's set fold (the old key's `tombstone` and the rename's `link` events reach the same
  > state), so it is not a mutation.
- **In 22.6 `#rev-round-11`, the s-2(iii) row,** replace "because a fold that only skips … never
  count" with:
  > because the fold holds no rename-specific link code (links follow their own `unlink` / `link`
  > events, applied generically), so the mutation has nothing distinct to mutate (r12: had it
  > been expressible, AC-7's `links` would have been one lower)

rel: contradicts -> [[task-22.6-removal-entry-points#acceptance]]
rel: depends-on -> [[task-17.4-factslog-backup-snapshot#r6-restore]]

### MEH m-1: `N` counts the entity's appends on any concept, `L` on one concept (F6) {#m-1}

**What:** "`N` is the number of that entity key's matched appends with no tombstone after them".
"Matched" means matched on the orphan key `(linkage, file, line, detail)`, with no `c`. When `E`
holds the same key on two concepts, one copy re-attached and the other re-appended, the second
copy's append counts against the first copy's guard, and the re-attached copy is dropped (F6).
The r11 model, which this guard derives from, counted per `c`.

**Fix:** this is moot if [[#s-1]] is adopted. If the count guard is kept instead, replace
"`N` is the number of that entity key's matched appends" with:
> `N` is the number of that entity key's matched appends on the same `c`

## Per-task verdict {#readiness}

| task | verdict | what is left |
|---|---|---|
| 16.1, 16.2, 16.3, 16.4, 16.5, 16.6 | **approval-ready** | none. The 16.6 round-11 edits are consistent, and AC-9d's builder clause matches. If [[#s-1]] is adopted, 16.6 is unaffected (`tombstone` and `entity` are not row ops). |
| 22.1, 22.1a, 22.3, 22.4, 22.5 | **approval-ready** | none |
| 22.2 | **needs one insert** | [[#s-1]](i) and the files-row edit; AC-7 and R2/R3 are otherwise ready |
| 22.6 | **needs a small edit pass** | [[#s-1]](ii)-(v); [[#s-2]]; [[#m-1]] only if the count guard stays |

## Verdict {#verdict}

DIRTY: 3 findings (0 BULLSHIT, 2 SKETCHY, 1 MEH).

- All 4 r11 findings are closed in substance.
- The `L > N` guard passes F1-F4, AC-6b base, AC-6b swapped and AC-6c(a), and every AC-6e
  mutation, including `L >= N`, fails as traced. The guard fails one more shape, F5, which only an
  exact restore marker closes.
- The reviser's departure on S-2(iii) is accepted for dropping my mutation, though the stated
  reason was false. Substitute 1 is refuted as vacuous; substitute 2 is accepted.
- Plan-16 is approval-ready. Plan-22 is not yet: it needs one orchestrator ruling ([[#s-1]]
  supersedes d9cc (ii)) and the edits above.
