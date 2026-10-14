---
gmd: "0.1"
id: plan-22-audited-removal-and-repair
title: "Plan 22: one audited path for every repair and removal — repair first, remove only what cannot be repaired"
tags: [plan, removal, repair, audit, grep-learning, concepts, bug-086, bug-101]
metadata:
  node_type: plan
  status: drafting
  created: 2026-10-07
  revised: 2026-10-14
---

# Plan 22: audited removal and repair {#root}

**Date:** 2026-10-07 (revised 2026-10-14 after the Wave 0 decision log)
**Status:** Drafting — revision round 2 (2026-10-14) for the re-review
[[bsd-plan16-22-spec-rereview-32dde06]] and [[plan-review-2026-10-14#t9]] ([[#rev-round-2]]). Task
specs 22.1a, 22.1, 22.2, 22.3, 22.4 (blocked; handed to the helix plan on close, d9j) and 22.5 are
written.
**Origin:** the plan review's C1/C2/C3, applied by the user on 2026-10-07: "apply all the
consolidations, don't delete moves repair them if possible". Revised from
[[bsd-plan22-spec-review-3104a81]] (22 findings) and the decisions of
[[plan-review-2026-10-14#t6]] and [[plan-review-2026-10-14#t8]].

rel: derives-from -> [[plan-review-2026-10-07]]
rel: derives-from -> [[plan-review-2026-10-14#t6]]
rel: derives-from -> [[plan-review-2026-10-14#t8]]
rel: derives-from -> [[bsd-plan22-spec-review-3104a81]]
rel: derives-from -> [[bsd-decision-log-review-a192ba2]]
rel: depends-on -> [[feedback_decay_never_loses_knowledge]]
rel: depends-on -> [[feedback_store_calls_via_daemon]]
rel: depends-on -> [[task-16.6-learned-row-validation]]
rel: depends-on -> [[plan-23-bounded-write-harness]]
rel: related-to -> [[plan-20-concept-similarity-eval]]
rel: related-to -> [[refmatrix/adr-0004-unified-location-space-index]]
rel: related-to -> [[plan-17-nightly-store-maintenance]]
rel: amends -> [[project_global_relative_rows_repair]]

## Why {#why}

Removal had four homes, and they disagreed:
- task 16.6's prune of learned rows;
- the "free culls" the concept exploration routed to 16.6. 16.6's evidence-row classes could not
  express them: orphan aliases are not grep-learned.
- bug-086's global-store repair, planned both as a standalone daemon op and as
  `prune --class orphan-root`;
- concept merges, named as a removal path in ADR-0004 `#rule-no-delete` with no owner.

The user's rule ([[feedback_decay_never_loses_knowledge]]) allows removal ONLY through an explicit,
audited dry-run → apply path, and the 2026-10-07 decision adds: **repair before removal** ("don't
delete moves, repair them if possible"). This plan is that one path. {#why-body}

**Not a cull class (d6c).** A `query/*` concept with df ≤ 1 that still has a valid (`ok`) evidence
row is verified knowledge. Removing it on a counter threshold is forbidden by the decay rule, so no
class in this plan selects it. The exploration's "747 protected `query/*` with df ≤ 1" is therefore
NOT a cull count; `empty-learned` ([[task-22.1-audit-classes#r2]]) is a different, defined
predicate whose count is measured, not assumed (#b-6). {#why-not-df}

## Scope of "the one path" {#scope}

ADR-0004 `#rule-no-delete` says removal goes "only" through one audited path. Per d8a, plan-22 is
that path for every POLICY or CLASS-based removal of knowledge rows in any store:
- grep-learned evidence rows, their file entities and `query/*` concepts;
- the concept free culls (`orphan-alias`, `empty-learned`);
- bug-086's global relative rows and the 1,655 pytest-tmp entities in the live global store (d1c,
  as amended by d8d);
- stale compiled subjects: plan-19's compile only MARKS them `stale` (protected, recall-invisible);
  their removal, if ever, is a plan-22 class (`stale-subject`, [[task-22.1a-provenance-free-classes#r1]]);
- concept merges (22.4, blocked).

Out of scope, stated so the wording matches the ADR (#m-7):
- plan-17's reap of DERIVED orphan vectors (d-4 below): derived-index garbage, restorable from its
  orphan list, not knowledge rows;
- the 235 pytest fixture rows in the live `query.log` (d8d): not catalog rows; mark-and-filter by
  readers, the log stays append-only. Plan-22 removes nothing from any log file.
- the user-explicit, named-selector commands (`forget`, `memory bulk-forget`, `untrack`) and the
  counter-threshold `prune-noise --drop`: not absorbed here. d9i decides that ONE ADR-0004
  amendment, drafted by the orchestrator for the user's approval, scopes them (each either routes
  through this plan's audited path or carries a stated exception). That amendment is PENDING and is
  not written in this plan's files ([[#open-after-revision]] 4).

{#scope-body}

## Principles {#principles}

1. **Audit is read-only.** It classifies and writes a dry-run plan file under
   `.refmatrix/removal/`; it writes nothing to the catalog, Lance, the queues or `facts.log`.
2. **Repair first.**
   - A row that can be made correct is re-pointed or moved, never deleted: lines that moved inside
     the same file (repaired per `(concept, file)` set, #b-1); a relative path that resolves
     uniquely (moved to its owning store, d6b; when no project store owns it, held until the user
     rules on the dry-run counts, d9b);
     an alias whose canonical is named in its own text (#s-5).
   - Removal is only for rows with no correct form.
3. **An ambiguous row is kept, never guessed.** A path that resolves under several roots, or a
   pairing the rule cannot make, is classified `ambiguous`, kept, and listed in every manifest
   (d6a: the 48 global entities).
4. **Dry run by default; apply needs the manifest (d8g).** The audit writes a plan manifest with a
   content hash. Apply takes that manifest id AND `--confirm <manifest-hash>`, refuses a manifest
   from another store, and refuses any store root not named on its own command line (22 #b-8).
   Every apply writes an intent-logged manifest (before/after of every repaired and moved row, the
   full row of every removal) and row-level `facts.log` events that both replay paths apply (#b-3).
   `restore` reverts repairs and re-inserts removals, checked by NAME (#b-3, DL #s-7).
5. **Never touch what ingest owns.** Only learned evidence rows, learned-only entities and the named
   concept classes are in scope. The apply never clears `protected` on an entity that survives it;
   protection leaves only with a whole-entity purge of a learned-only entity (#s-4).
6. **Bounded writes without the lossy queue.** The apply is a bounded step loop over an in-memory
   plan, each batch bound through plan-23's `bind(partition_name)` seam inside its own hold, counted by the
   23.2 recorder, with one Lance finalize per kind after the loop (#s-1, #s-2).
7. **Tests are sandboxed by task 23.0** (d1a/d1b). No test in this plan reaches `~/.refmatrix` or a
   registered live store; the live applies (22.5, 22.3) are operator steps after a user-confirmed
   dry run on a copy.

{#principles-body}

## Interface (d6e as amended by d8g; #m-6) {#interface}

One CLI group, three verbs, each on BOTH surfaces (the `tests/test_verb_parity.py` set equality
holds; no `CLI_ONLY` class is introduced):

| verb | CLI | MCP tool | writes |
|---|---|---|---|
| `removal_audit` | `rmx removal audit --root R [--class C] [--list] [--json]` | `rmx_removal_audit` | the plan manifest file only |
| `removal_apply` | `rmx removal apply --root R --manifest ID --confirm HASH` | `rmx_removal_apply` | catalog + `facts.log` + manifest |
| `removal_restore` | `rmx removal restore --root R --manifest ID --confirm HASH` | `rmx_removal_restore` | catalog + `facts.log` |

The cross-store move (22.5) adds `--target-root T` to `apply`, and both roots must be named. The
concept classes do not live under `rmx learn` (#m-6).

## Tasks {#tasks}

| task | wave | what | acceptance (summary) |
|---|---|---|---|
| 22.1a | 1 | provenance-free classes: `orphan-root` (incl. root-`ambiguous`), `missing-file`, `duplicate`, `orphan-alias`, `stale-subject`; the `removal_audit` verb | fixture row per class; probe split reproduced on a global copy; independent recount equals audit count; audit writes nothing |
| 22.2 | 1 | the engine: repair/move/remove primitives, row-level `facts.log` events in both replay paths, manifest + intent log + restore, `bind` + recorder, ablation gate on a copy of THIS store, `removal_apply`/`removal_restore` | rebuild reproduces post-apply; restore equal by name incl. evidence, protection, vectors; two-partition AC; gate refuses on a masked delta and on a store lacking the candidates |
| 22.5 | 1 | cross-store move: copy → verify → forget across two daemons, manifest-backed, idempotent, sidecar rows travelling with their evidence; the no-owner buckets reported and held until the user rules (d9b) | crash at each step leaves no loss and no duplicate; collision merges; only named store roots; nothing applied to a `pending` no-owner bucket |
| 22.3 | 1 | first apply, live global store: `orphan-root:unresolved` removed (measured; 563 was the probe's no-verifying-file count, which included rows still readable today), 48 kept ambiguous, 1,655 pytest-tmp entities removed; resolved and `home-readable` entities handed to 22.5 (the no-owner ones held for the user's ruling, d9b) | total global `unreadable` over a pre-registered pattern set drops to the residual explained by class; memory count unchanged |
| 22.1 | 2 | flag-sensitive classes: `ok`, `moved` (per `(concept, file)` set), `grown`/`shrunk`, `stale-line`, `out-of-range`, `unverifiable`, `empty-learned`; every row decided by 16.6's `learned_verify` (no matcher here); 16.6's read-time marks read for ordering and reporting | two-hit shift ends re-pointed with 0 `ambiguous`; BRE, POSIX-class and `\<…\>` rows `ok`; exit 2 `unverifiable`; pre-provenance `-i` row stays `ok`; marked rows listed; `empty-learned` recount exact |
| 22.4 | blocked; handed over on close (d9j) | merge writes into the alias map | blocked until ADR-0004's helix plan defines the alias map and plan-20 supplies the rule; that plan takes it over |

Task specs: `workflow/plans/plan-22-audited-removal-and-repair-tasks/`.

## Dependencies and order (#t8-wave1) {#dependencies}

Wave 1: 23.0 ∥ 23.4 → 23.2 → 23.1 (+ tick registry) → 23.3; after 23.1: **16.6 Wave-1 slice →
22.1a → 22.2 → 22.5 → 22.3**.

- 22.1a needs: 23.0 (sandbox), 16.6's Wave-1 slice (sidecar + backfill + read-time marks, d6d;
  16.6 no longer depends on 16.1).
- 22.2 needs: 22.1a (classifier output contract), 16.6's Wave-1 slice
  (`move_learned_provenance`, the sidecar's `facts.log` events), 21.1 R5 (`telemetry.row_provenance`,
  for the gate's query set; d8d's owner per `#t9-fixes`), 23.1 (`bind(partition_name)`, `bounded_steps`),
  23.2 (the write-count recorder).
- 22.5 needs: 22.2 (engine, manifest, events, removal primitive).
- 22.3 needs: 22.5 (the 476), 22.2, 22.1a; the user's confirmation of the dry-run counts.
- 22.1 (Wave 2) needs: 16.1's learn-time provenance write (tool + dialect + flags + line hash,
  d6d); it extends 22.2's engine with the `moved` / `stale-line` / `out-of-range` repairs and
  removals.
- 22.4: blocked (see its spec); plan-22 may reach `completed` with it handed to the helix plan
  (d9j).

Plan-16's 16.6 is owned by the plan-16 revision; this plan references it and does not edit it.

rel: depends-on -> [[task-16.6-learned-row-validation]]
rel: depends-on -> [[task-16.1-argv-faithful-learner]]
rel: depends-on -> [[task-23.1-queue-and-drain]]
rel: depends-on -> [[task-23.2-lock-hold-fixture]]
rel: depends-on -> [[task-21.1-context-usage-telemetry]]

## Decisions {#decisions}

| # | decision | source |
|---|---|---|
| d-1 | one removal path for learned rows, free culls, bug-086, pytest-tmp rows, stale subjects and merges; scope as [[#scope]] | user 2026-10-07 (C1/C2); d8a; #m-7 |
| d-2 | `moved` rows are repaired, never deleted; ambiguous rows are kept | user 2026-10-07; d6a |
| d-3 | the concept classes (`orphan-alias`, `empty-learned`, `stale-subject`) pass an ablation gate on a COPY of the store they live in before apply; no count is presumed (the "747" is withdrawn, #b-6) | exploration C1; #t6-fixes #b-5 |
| d-4 | plan-17's nightly orphan-VECTOR reap stays in plan-17 (derived-index garbage, logged, with a recoverable list and a ratio cap) | user 2026-10-07; d3a |
| d-5 | the 48 ambiguous global entities are KEPT and listed as ambiguous | d6a |
| d-6 | the uniquely verified global entities MOVE to the project store whose root contains the resolved file (22.5). AMENDED by d9b: rows that read correctly today but lie under no project store (22.5's `no project store` and `global root only` buckets) are decided by the user AFTER 22.5's dry run shows the real split; nothing is applied to them until then. d8c's "≥ 114 forgotten" is withdrawn (the probe was misread: all 362 `$HOME`-verified entities matched under the global store's own root) | d6b, d8c, d9b |
| d-7 | `query/*` with df ≤ 1 and a valid row is not a cull class | d6c |
| d-8 | 22.1 splits; 22.1a runs in Wave 1 without 16.1 | d6d; #t8-amendments |
| d-9 | one verb per action on both surfaces; apply needs manifest id + `--confirm <manifest-hash>` + an explicitly named root | d6e, d8g, 22 #b-8 |
| d-10 | 22.3 removes the 1,655 pytest entities; the 235 `query.log` rows are NOT a plan-22 removal | d1c, d8d |
| d-11 | THE verifier for learned rows is 16.6's `learned_verify` (re-run the recorded tool; line-set API; named-subset permissive reading for rows without rules); plan-22 carries no matcher | re-review b-4; `#t9-fixes` |
| d-12 | plan-22 may close with 22.4 handed to the future helix plan | d9j |

## Open after revision {#open-after-revision}

Revision round 2 (2026-10-14) settled every item the re-review said the specs or the orchestrator
could settle, and records the user's answers from [[plan-review-2026-10-14#t9]]. Kept by number so
earlier links still resolve.

1. **Owner of d8d's mark-and-filter — SETTLED (`#t9-fixes`; re-review s-6).** Task 21.1 owns it in
   `telemetry.py` (`telemetry.row_provenance`, `telemetry.is_test_artifact_row`); 22.2 R7 calls it
   and carries no copy ([[task-22.2-repair-then-remove#r7]]).
2. **The 362 and d8c's "≥ 114" — SETTLED by d9b.** All 362 `$HOME`-verified entities matched under
   the global store's own root, none under the 7 project roots, so "≥ 114" was a misreading and is
   withdrawn (not a lower bound). 22.5 R1 reports the real split (`move`, `no project store`,
   `global root only`, `held`) and applies NOTHING to the no-owner buckets until the user rules
   ([[task-22.5-cross-store-move#r1]]). **Waiting on the user, after the dry run.**
3. **Plan close — SETTLED by d9j.** Plan-22 can reach `completed` with 22.4 handed to the future
   helix plan ([[task-22.4-merge-writes#root]]).
4. **ADR-0004 "only" vs the explicit-selector commands — DECIDED (d9i), amendment PENDING.** One
   ADR-0004 amendment (the floor formula; removal-path scoping for `forget`, `prune-noise --drop`,
   `untrack`, `memory bulk-forget`, and the derived-vector reaping sentence of DL #s-7) is drafted
   by the orchestrator for the user's approval. It is not written in this plan's files; [[#scope]]
   matches it once approved.
5. **Plan-16 table row — SETTLED (re-review m-3).** The plan-16 16.6 row says "nothing here
   removes a row".
6. **Where "marked ambiguous" persists — SETTLED (no user decision).** In every manifest, recomputed
   on every audit; no sidecar column.
7. **Plan-19's `stale` mark — SETTLED (re-review m-3).** Plan-19's 19.4 R5 writes it.
8. **Walk exclusions — user confirms, non-blocking.** 22.1a AC-5b prints the probe reproduction
   (exclusions OFF) and the applied split (exclusions ON) side by side with the delta; the user sees
   it with the 22.5 dry run.
9. **Protections with no attributable source — SETTLED (re-review m-3).** On the global store every
   `protect` event on the in-scope entities directly follows an `entity` event (re-review
   `#ev-facts`), so the `unknown` bucket is empty there; "unknown = asserted" stays the safe
   default for project stores ([[task-22.2-repair-then-remove#r5]]).

## Revision round 2 (2026-10-14) {#rev-round-2}

Answers [[bsd-plan16-22-spec-rereview-32dde06]] (plan-22: b-4, s-1, s-2, s-5, m-3, m-5, m-7, m-8;
shared b-2, b-3, s-3, s-6, m-4; the r1 partials b-2, b-3, b-4, m-7 and the open m-5) and
[[plan-review-2026-10-14#t9]] (d9b, d9i, d9j, `#t9-fixes`). Later rows win.

| finding / decision | answered in |
|---|---|
| b-4 (22.1's Python translation vs 16.6's re-run; line-set API) | [[task-22.1-audit-classes#r1-verify]]; d-11 |
| b-3 (16.6's marks have no reader) | [[task-22.1-audit-classes#r1-marks]] |
| b-2 (sidecar not replayable; 22.2 AC-3) | [[task-22.2-repair-then-remove#r3]]; 22.2 AC-3; 16.6 R1d |
| s-1 (22.1a candidate set; duplicate candidates) | [[task-22.1a-provenance-free-classes#r1]]; 22.1a AC-5 |
| s-2, d9b ("≥ 114" misread; readable-today rows) | [[task-22.5-cross-store-move#r1]]; [[task-22.1a-provenance-free-classes#r1-outcome]]; d-6; [[#open-after-revision]] 2 |
| s-3 (census ACs vs the 23.0 sandbox) | 22.1a AC-5/6/7, 22.1 AC-6, 22.3 R1: sandbox test + operator census on a `cp` of `catalog.read.duckdb` |
| s-5 (repairs change sidecar keys) | [[task-22.2-repair-then-remove#r2]] (owner); [[task-22.5-cross-store-move#r2]] (`learned_import`) |
| s-6 (d8d predicate unowned) | [[#open-after-revision]] 1; [[task-22.2-repair-then-remove#r7]] |
| m-3 (items 5, 7, 9 settled) | [[#open-after-revision]] 5, 7, 9 |
| m-4 (vocabulary) | 22.1 `unverifiable` = 16.6's `UNVERIFIABLE_REASONS`; class names shared |
| m-5 (`N` across readings) | [[task-22.1-audit-classes#r1]]; 22.1 AC-4b |
| m-7 (displacement by construction) | [[task-22.2-repair-then-remove#r7]]; 22.2 AC-10 |
| m-8 (two root spellings) | [[task-22.2-repair-then-remove#r8]]; 22.3 R3; 22.5 R5 |
| r1 m-5 (plan close with 22.4), d9j | [[#open-after-revision]] 3; d-12; [[task-22.4-merge-writes#root]] |
| r1 m-7 (ADR "only"), d9i | [[#scope]]; [[#open-after-revision]] 4 (amendment pending, orchestrator) |
| `#t9-fixes` rows for plan-22 | the rows above |

rel: amends -> [[bsd-plan16-22-spec-rereview-32dde06]]
rel: derives-from -> [[plan-review-2026-10-14#t9]]

## Revision (2026-10-14 decision log) {#rev-2026-10-14}

| finding / decision | answered in |
|---|---|
| 22 #b-1 (`moved` key, per-row uniqueness) | [[task-22.1-audit-classes#r1]], [[task-22.2-repair-then-remove#r1]] |
| 22 #b-2 (no flags on existing rows) | [[task-22.1-audit-classes#r1-verify]] |
| 22 #b-3 (no row-level replay) | [[task-22.2-repair-then-remove#r3]], [[task-22.2-repair-then-remove#r4]] |
| 22 #b-4 (the 48, candidate roots, units) | [[task-22.1a-provenance-free-classes#r1]], [[task-22.3-bug-086-global-repair#requirements]] |
| 22 #b-5 (gate on wrong stores) | [[task-22.2-repair-then-remove#r7]] |
| 22 #b-6 (`empty-learned` ≤ 747) | [[#why-not-df]], [[task-22.1-audit-classes#r2]] |
| 22 #b-7 (16.6 unscheduled) | [[#dependencies]], [[task-22.1a-provenance-free-classes#root]] |
| 22 #b-8 (live global writes, sandbox, explicit root) | [[#principles]] 4, 7; each task's test strategy; [[task-22.3-bug-086-global-repair#requirements]] |
| 22 #s-1 (`bind`, two partitions) | [[task-22.2-repair-then-remove#r6]] |
| 22 #s-2 (queue, intent log, re-check) | [[task-22.2-repair-then-remove#r6]] |
| 22 #s-3 (rename collision, memory-only global) | [[task-22.2-repair-then-remove#r2]], [[task-22.5-cross-store-move#requirements]] |
| 22 #s-4 (learned protection), DL #b-2, d8b | [[#principles]] 5, [[task-22.2-repair-then-remove#r5]], [[#open-after-revision]] 9 |
| 22 #s-5 (alias canonical) | [[task-22.2-repair-then-remove#r1]] |
| 22 #s-6 (removal primitive) | [[task-22.2-repair-then-remove#r2]] |
| 22 #s-7 (22.3 AC scope) | [[task-22.3-bug-086-global-repair#acceptance]] |
| 22 #m-1 | [[task-22.1a-provenance-free-classes#acceptance]], [[task-22.1-audit-classes#acceptance]] |
| 22 #m-2 | [[task-22.1a-provenance-free-classes#r3]] |
| 22 #m-3 | [[#open-after-revision]] 5 (plan-16 file) |
| 22 #m-4 | [[task-22.2-repair-then-remove#r4]] |
| 22 #m-5 | [[#open-after-revision]] 3; [[task-22.4-merge-writes#root]] |
| 22 #m-6 | [[#interface]] |
| 22 #m-7 | [[#scope]], [[#open-after-revision]] 4 |
| d1c (as amended by d8d) | [[#scope]], d-10, [[task-22.3-bug-086-global-repair#requirements]] |
| d6a | d-5, [[task-22.3-bug-086-global-repair#requirements]] |
| d6b (as amended by d8c) | d-6, [[task-22.5-cross-store-move#root]] |
| d6c | [[#why-not-df]], d-7 |
| d6d (+ #t8-amendments 22.1a) | d-8, [[#dependencies]], [[task-22.1a-provenance-free-classes#root]] |
| d6e (as amended by d8g) | [[#interface]], d-9, [[task-22.2-repair-then-remove#r8]] |
| d8a | [[#scope]], [[task-22.1a-provenance-free-classes#r1]] (`stale-subject`) |
| #t6-fixes | the task specs, per id above |
| #t8 22 #b-8 clause | [[task-22.2-repair-then-remove#r8]] |
| #t8-wave1 | [[#tasks]], [[#dependencies]] |
| DL #b-1, #b-3, #b-4, #s-5, #s-7, #m-6 (decision-log review) | [[#scope]]; [[#dependencies]]; [[task-22.5-cross-store-move#root]]; [[#interface]]; [[task-22.2-repair-then-remove#r4]]; this table |
