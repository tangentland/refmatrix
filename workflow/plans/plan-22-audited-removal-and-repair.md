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
**Status:** Drafting — revision after the 2026-10-14 decision log. Task specs 22.1a, 22.1, 22.2,
22.3, 22.4 (blocked) and 22.5 are written; all are "Pending (revision after the 2026-10-14 decision
log)".
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
  counter-threshold `prune-noise --drop`: listed in [[#open-after-revision]], not absorbed here.

{#scope-body}

## Principles {#principles}

1. **Audit is read-only.** It classifies and writes a dry-run plan file under
   `.refmatrix/removal/`; it writes nothing to the catalog, Lance, the queues or `facts.log`.
2. **Repair first.**
   - A row that can be made correct is re-pointed or moved, never deleted: lines that moved inside
     the same file (repaired per `(concept, file)` set, #b-1); a relative path that resolves
     uniquely (moved to its owning store, or forgotten-restorable when no store owns it, d6b/d8c);
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
   plan, each batch bound through plan-23's `bind(batch)` seam inside its own hold, counted by the
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
| 22.5 | 1 | cross-store move: copy → verify → forget across two daemons, manifest-backed, idempotent | crash at each step leaves no loss and no duplicate; collision merges; only named roots |
| 22.3 | 1 | first apply, live global store: 563 removed, 48 kept ambiguous, 1,655 pytest-tmp entities removed; the 476 handed to 22.5 | total global `unreadable` over a pre-registered pattern set drops to the residual explained by class; memory count unchanged |
| 22.1 | 2 | flag-sensitive classes: `ok`, `moved` (per `(concept, file)` set), `grown`/`shrunk`, `stale-line`, `out-of-range`, `unverifiable`, `empty-learned` | two-hit shift ends re-pointed with 0 `ambiguous`; pre-provenance `-i` row stays `ok`; `empty-learned` recount exact |
| 22.4 | blocked | merge writes into the alias map | blocked until ADR-0004's helix plan defines the alias map and plan-20 supplies the rule |

Task specs: `workflow/plans/plan-22-audited-removal-and-repair-tasks/`.

## Dependencies and order (#t8-wave1) {#dependencies}

Wave 1: 23.0 ∥ 23.4 → 23.2 → 23.1 (+ tick registry) → 23.3; after 23.1: **16.6 Wave-1 slice →
22.1a → 22.2 → 22.5 → 22.3**.

- 22.1a needs: 23.0 (sandbox), 16.6's Wave-1 slice (sidecar + backfill + read-time marks, d6d;
  16.6 no longer depends on 16.1).
- 22.2 needs: 22.1a (classifier output contract), 23.1 (`bind(batch)`, `bounded_steps`), 23.2 (the
  write-count recorder).
- 22.5 needs: 22.2 (engine, manifest, events, removal primitive).
- 22.3 needs: 22.5 (the 476), 22.2, 22.1a; the user's confirmation of the dry-run counts.
- 22.1 (Wave 2) needs: 16.1's learn-time provenance write (tool + dialect + flags + line hash,
  d6d); it extends 22.2's engine with the `moved` / `stale-line` / `out-of-range` repairs and
  removals.
- 22.4: blocked (see its spec).

Plan-16's 16.6 is owned by the plan-16 revision; this plan references it and does not edit it.

rel: depends-on -> [[task-16.6-learned-row-validation]]
rel: depends-on -> [[task-16.1-argv-faithful-learner]]
rel: depends-on -> [[task-23.1-queue-and-drain]]
rel: depends-on -> [[task-23.2-lock-hold-fixture]]

## Decisions {#decisions}

| # | decision | source |
|---|---|---|
| d-1 | one removal path for learned rows, free culls, bug-086, pytest-tmp rows, stale subjects and merges; scope as [[#scope]] | user 2026-10-07 (C1/C2); d8a; #m-7 |
| d-2 | `moved` rows are repaired, never deleted; ambiguous rows are kept | user 2026-10-07; d6a |
| d-3 | the concept classes (`orphan-alias`, `empty-learned`, `stale-subject`) pass an ablation gate on a COPY of the store they live in before apply; no count is presumed (the "747" is withdrawn, #b-6) | exploration C1; #t6-fixes #b-5 |
| d-4 | plan-17's nightly orphan-VECTOR reap stays in plan-17 (derived-index garbage, logged, with a recoverable list and a ratio cap) | user 2026-10-07; d3a |
| d-5 | the 48 ambiguous global entities are KEPT and listed as ambiguous | d6a |
| d-6 | the 476 uniquely verified global entities MOVE to the project store whose root contains the resolved file; those under no store root get an audited, restorable forget (22.5); this knowingly changes those rows from "recovered" (2026-10-07) to "forgotten, restorable" | d6b, d8c |
| d-7 | `query/*` with df ≤ 1 and a valid row is not a cull class | d6c |
| d-8 | 22.1 splits; 22.1a runs in Wave 1 without 16.1 | d6d; #t8-amendments |
| d-9 | one verb per action on both surfaces; apply needs manifest id + `--confirm <manifest-hash>` + an explicitly named root | d6e, d8g, 22 #b-8 |
| d-10 | 22.3 removes the 1,655 pytest entities; the 235 `query.log` rows are NOT a plan-22 removal | d1c, d8d |

## Open after revision {#open-after-revision}

Gaps the 2026-10-14 decision log does not settle. Listed, not decided.

1. **Owner of d8d's mark-and-filter.** d8d says every `query.log` / `recall-events.jsonl` reader
   skips pytest-tmp rows through one shared predicate. No task owns that predicate. Plan-22
   removes no log rows and does not take it.
2. **The 362 `$HOME`-relative rows and d8c's "≥ 114".** The probe verified 362 entities under
   `/Users/tholley`, the global store's own parent, not under a project store root. d8c reads them
   as "under a registered root". If the 362 are in the 476 and no project root contains their
   files, they fall into the forget bucket, and the forget count can exceed 114 by up to 362.
   22.5 R1 computes the real split; the user must see it before the apply (DL #b-4).
3. **Plan-22's close (#m-5).** Whether plan-22 can reach `completed` with 22.4 handed to the
   ADR-0004 helix plan (which does not exist yet), or stays open until that plan lands.
4. **ADR-0004 "only" vs the explicit-selector commands (#m-7).** `forget`, `memory bulk-forget`,
   `untrack` stay as user-explicit commands, and `prune-noise --drop` is a df-threshold removal
   that the decay rule forbids. Whether the ADR wording narrows to "policy or class-based removal",
   or those commands are routed through a manifest, is an ADR decision. The ADR sentence that scopes
   derived-vector reaping (DL #s-7) is also an ADR edit, not in this plan's files.
5. **Plan-16 table row (#m-3).** `plan-16-invisible-grep-shim.md` still says 16.6 "removes every
   non-`ok` class"; that file belongs to the plan-16 revision.
6. **Where "marked ambiguous" persists (d6a).** This revision persists it in every manifest and
   recomputes it on every audit. A durable per-row mark would be a column in 16.6's sidecar, which
   plan-22 does not own.
7. **Which plan-19 task sets the `stale` subject mark (d8a).** `stale-subject` is inert until it
   exists.
8. **Exclusions of the candidate-root walk.** [[task-22.1a-provenance-free-classes#r1]] names a
   pre-registered exclusion list for the suffix walk; the user has not confirmed it.
9. **Pre-existing protections with no attributable source (DL #b-2).** 22.2 R5 treats them as
   `unknown` = asserted (the safe direction: the entity is not purged, its learned rows may still
   be removed). DL #b-2 asked the user to choose between a backfill rule and "unknown = asserted";
   d8b removed plan-19's need for the source but did not answer that choice for plan-22.

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
