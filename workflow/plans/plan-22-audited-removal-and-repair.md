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
  updated: 2026-10-15
---

# Plan 22: audited removal and repair {#root}

**Date:** 2026-10-07 (revised 2026-10-14 after the Wave 0 decision log)
**Status:** Drafting — revision round 9 (2026-10-15) for the r9 diff check
[[bsd-plan16-22-spec-diffcheck-r9-29e335a]] (both-dead vacuum orphans, the drop's partition
field, the live-primitive kind helper, and the retired incremental replay path, d9bu;
[[#rev-round-9]]); revision round 8 (2026-10-15) for the r8 re-review
[[bsd-plan16-22-spec-rereview-r8-23ad703]] (the row ops after bug-117, 0.78.3) and the approvals
d9bk/d9bl ([[plan-review-2026-10-14#t12-approvals]]; [[#rev-round-8]]); round 7 for the r7
re-review [[bsd-plan16-22-spec-rereview-r7-331b414]] and d9av/d9aw/d9ay ([[#rev-round-7]]); round 6 (r6 re-review, d9aq/d9ar) in
[[#rev-round-6]]; round 5 (r4 re-review, d9ab/d9ac/d9z)
in [[#rev-round-5]], round 3 in [[#rev-round-3]], round 2 in [[#rev-round-2]]. Task
specs 22.1a, 22.1, 22.2, 22.3, 22.4 (blocked; handed to the helix plan on close, d9j), 22.5 and
22.6 (new in round 3) are written.
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
rel: implements -> [[refmatrix/adr-0004-unified-location-space-index#rule-no-delete]]
rel: implements -> [[refmatrix/adr-0004-unified-location-space-index#a14-removal-scope]]
rel: derives-from -> [[plan-review-2026-10-14#t9-approvals]]
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

ADR-0004 `#rule-no-delete`, as amended and APPROVED (d9k, folded at `3021cd6`, scoped by
`#a14-removal-scope`), says knowledge removal goes only through one audited path. Per d8a and d9k,
plan-22 is that path for every POLICY or CLASS-based removal of knowledge rows in any store, AND
for the user's explicit removal commands:
- grep-learned evidence rows, their file entities and `query/*` concepts;
- the concept free culls (`orphan-alias`, `empty-learned`);
- bug-086's global relative rows and the 1,655 pytest-tmp entities in the live global store (d1c,
  as amended by d8d);
- stale compiled subjects: plan-19's compile only MARKS them `stale` (protected, recall-invisible);
  their removal, if ever, is a plan-22 class (`stale-subject`, [[task-22.1a-provenance-free-classes#r1]]);
- concept merges (22.4, blocked), with `fold_concept_dups` as a merge entry point (d9o; 22.4 R5);
- **rows with a dead endpoint (d9an, d9ar; r6 m-7):** `dangling-link` (`entity_links` rows) and
  `dangling-evidence` (`linkage_evidence` rows of a live entity whose concept is dead), the
  owners of bug-111's deferral and of what every purge leaves behind; audited store-wide by
  22.1a ([[task-22.1a-provenance-free-classes#r1-dangling]]) and removed replay-safely by 22.2
  (tombstone and `unlink` by NAME, never an id-keyed event; d9aq;
  [[task-22.2-repair-then-remove#r9-dangling]]);
- **the selector entry points (d9k): `rmx forget`, `rmx memory forget`, `rmx memory bulk-forget`**
  build a plan manifest and need `--confirm <hash>`; restorable (task 22.6 R1).

**The paths ADR-0004 classifies outside the confirm (d9k, d9o), each owned by a task here:**

| path | classification | owner |
|---|---|---|
| `rmx untrack`, `rmx prune-noise --drop` | listed exceptions: print what they remove, write the same manifest form first | 22.6 R2 |
| `purge_path` on a deleted or ignored file (sync; `vacuum` step 2) | derived cleanup WITH a manifest; learned rows go to it | 22.6 R3 |
| sync's GMD legacy purge on a `.md` edit (and the non-GMD purge-before-re-add, the same act) | a BUG (bug-107), fixed to keep learned rows; 16.6's verifier judges them | 22.6 R4 |
| `vacuum`'s orphan-evidence delete | derived cleanup with a manifest AND a `facts.log` event | 22.6 R5 |
| `unprotect` | not removal; its `protect` event carries `source` | 22.6 R6 |
| `fold_concept_dups` (`rmx memory dedup`, MCP `rmx_memory` `dedup`) | a merge; plan-22 entry point owned with merge writes by the helix plan | 22.4 R5 (handed over, d9j) |
| `merge_partition` | a merge; plan-22 entry point owned by the helix plan; dropped fragment bits go to the bug-105 hotfix's manifest (d9ac) | 22.4 R5; 22.6 R7 |
| `rmx ingest`'s GMD legacy purge (`ingest.py:1179-1180`); `rmx sync --invalidate`; sync's existing-unsupported branch | re-ingest: learned rows kept (d9p; r4 s-2) | 22.6 R4, R9 |
| `ingest_gmd --as-memory`'s raw doc delete | derived conversion: tombstoned `purge_entity`, learned rows to a manifest | 22.6 R9 |
| the periodic `facts.log` compaction (`dump_catalog_to_log`) | not a removal, but it must keep every field and table these plans add (`source`, `learned_provenance`; d9ab) | 22.6 R6; 16.6 R1d |
| plan-17's orphan-vector reap; the bug-105 fragment repair | derived-index cleanup with a manifest (ADR text) | plan-17; the bug-105 hotfix |

Out of scope, stated so the wording matches the ADR (#m-7):
- plan-17's reap of DERIVED orphan vectors (d-4 below): derived-index garbage, restorable from its
  orphan list, not knowledge rows;
- the 235 pytest fixture rows in the live `query.log` (d8d): not catalog rows; mark-and-filter by
  readers, the log stays append-only. Plan-22 removes nothing from any log file.
- *(round 2, superseded by d9k/d9o):* the explicit-selector commands were "not absorbed here",
  pending the amendment. The amendment is approved, and the table above is the scope.

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
| 22.1a | 1 | provenance-free classes: `orphan-root` (incl. root-`ambiguous`, `home-readable`, `unverifiable`), `missing-file`, `duplicate`, `orphan-alias`, `stale-subject`, `dangling-link` and `dangling-evidence` (store scope, dead end named from `facts.log`); the `removal_audit` verb | fixture row per class; the recovered probe re-run on a global copy with a churn-bounded `reproduced`/`drift` verdict beside the applied split; independent recount equals audit count; one liveness predicate shared with `repair_fragments` (AST check); audit writes nothing |
| 22.2 | 1 | the engine: repair/move/remove primitives, row-level `facts.log` events in both replay paths, manifest + intent log + restore, `bind` + recorder, ablation gate on a copy of THIS store, `removal_apply`/`removal_restore`; dangling-row removal; with 22.6 R6 in its slice | rebuild reproduces post-apply; a rebuild after a dangling removal resurrects no dead endpoint; restore equal by name incl. evidence, protection, vectors, dangling rows; two-partition AC; gate refuses on a masked delta and on a store lacking the candidates |
| 22.5 | 1 | cross-store move: copy → verify → forget across two daemons, manifest-backed, idempotent, sidecar rows travelling with their evidence; the no-owner buckets reported and held until the user rules (d9b) | crash at each step leaves no loss and no duplicate; collision merges; only named store roots; nothing applied to a `pending` no-owner bucket |
| 22.3 | 1 | first apply, live global store: `orphan-root:unresolved` removed (`orphan-root:unverifiable` kept) (measured; 563 was the probe's no-verifying-file count, which included rows still readable today), 48 kept ambiguous, the 1,655 pytest-tmp entities' learned rows removed (the entities kept as user-asserted under d9ab; removing them is the user's selector step); learned-only members that a `cli.log` grep record attributes to the learner purged whole (≤ 90; the count printed and shown to the user before the apply, d9aw); resolved and `home-readable` entities handed to 22.5 (the no-owner ones held for the user's ruling, d9b) | total global `unreadable` over a pre-registered pattern set drops to the residual explained by class; memory count unchanged |
| 22.1 | 2 | flag-sensitive classes: `ok`, `moved` (per `(concept, file)` set), `grown`/`shrunk`, `stale-line`, `out-of-range`, `unverifiable`, `empty-learned`; every row decided by 16.6's `learned_verify` (no matcher here); 16.6's read-time marks read for ordering and reporting | two-hit shift ends re-pointed with 0 `ambiguous`; BRE, POSIX-class and `\<…\>` rows `ok`; exit 2 `unverifiable`; pre-provenance `-i` row stays `ok`; marked rows listed; `empty-learned` recount exact |
| 22.4 | blocked; handed over on close (d9j) | merge writes into the alias map; `fold_concept_dups` as a merge entry point (d9o) | blocked until ADR-0004's helix plan defines the alias map and plan-20 supplies the rule; that plan takes it over |
| 22.6 | 1 (after 22.2; parallel to 22.5) | entry points (`forget`, `memory forget`, `memory bulk-forget` with `--confirm`; `untrack`, `prune-noise --drop` manifest first) and the bug-107 paths (deleted/ignored-file purge with manifest; sync edits keep learned rows; `vacuum` orphan drop with manifest + event; `unprotect` source) | `forget` without `--confirm` writes nothing; bulk-forget restores bodies; edit keeps learned rows and a rebuild agrees; vacuum drops are logged and replayable |

Task specs: `workflow/plans/plan-22-audited-removal-and-repair-tasks/`.

## Dependencies and order (#t8-wave1) {#dependencies}

Wave 1 (the order of record, [[plan-review-2026-10-14#t10-waves]], d9t): 23.0 ∥ 23.4 → 23.2 →
23.1 (+ tick registry) → 23.3; after 23.1: **16.6 Wave-1 slice → 22.1a → 22.2 (with 22.6 R6) →
(22.5 ∥ the rest of 22.6) → 22.3**; 17.1 lands before 22.2's restore is built (d9z). The split is
named (r6 m-7): 22.6 R6 (`entities.protect_source`, the protect writers' `protect_source`
keyword, the compactor's `source`) is built in 22.2's slice, because 22.2 R5 reads it; 22.6's
other requirements follow 22.2.

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
- 22.6 needs: 22.2 (engine, intent-record form, restore), 22.1a (`removal_audit`), 16.6's Wave-1
  slice. Its R4 (sync edits keep learned rows) needs only the 16.6 slice and may land first. It
  is in `#t10-waves` since d9t (r4 m-5: round 3's "does not list 22.6 yet" is stale). 22.2 R5
  reads 22.6 R6's `entities.protect_source`, so R6 lands with or before 22.2's protection rule.
- 22.2 R4 calls 17.1's `vectors_restore(..., id_map=)` (d9z).

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
| d-10 | 22.3 removes the 1,655 pytest entities' learned rows (AMENDED by d9ab: the entities are user-asserted, kept unless the user names them in a selector plan); the 235 `query.log` rows are NOT a plan-22 removal | d1c, d8d, d9ab |
| d-11 | THE verifier for learned rows is 16.6's `learned_verify` (re-run the recorded tool; line-set API; named-subset permissive reading for rows without rules); plan-22 carries no matcher | re-review b-4; `#t9-fixes` |
| d-12 | plan-22 may close with 22.4 handed to the future helix plan | d9j |
| d-13 | `forget`, `memory forget` and `memory bulk-forget` are entry points to this path (plan manifest + `--confirm`); `untrack` and `prune-noise --drop` are listed exceptions writing the same manifest form first; the intent record restores memory bodies and whole entity rows | d9k; r3 b-3; 22.6, 22.2 R4 |
| d-14 | the bug-107 paths as d9o classifies them (table in [[#scope]]) | d9o; 22.6 |
| d-15 | the probe's walk and line check are the RECOVERED script's, a census reproduction only; the applied split uses the classifier's walk and 16.6's reading; a reproduction mismatch is reported (`drift`), never a blocking gate | r3 b-1; 22.1a R1 |
| d-16 | a protection's origin is trusted only from its event's `source` (persisted, kept by the compactor) or a CLI/MCP command record (AMENDED by d9ak(b), d-22: or a `cli.log` grep record); everything else is user-asserted and never class-removed, its learned rows may be (counts in 22.2 R5: 0 existing protections are learner-attributed by `source` or command record; 217 here and 90 global by the grep record) | d9ab; r4 b-2; d9ak |
| d-17 | `merge_partition` is a merge entry point owned by the helix plan, as `fold_concept_dups` | d9ac; r4 s-2 |
| d-18 | the intent record keeps each removed entity's old id and vector; restore calls `vectors_restore(..., id_map=)` | d9z |
| d-19 | the line hash pairs rows; it never proves a row stale | r4 b-1 |
| d-20 | rows with a dead endpoint are a store-scope class (`dangling-link`); their removal logs a `tombstone` BY NAME for each dead endpoint the log still names and an `unlink` by name for the row; a nameless dead end logs nothing; no id-keyed event exists | d9an, d9aq; r6 b-1, s-2 |
| d-21 | `linkage_evidence` rows of a live entity whose concept is dead are the `dangling-evidence` sub-class, audited and removed as d-20; 22.2's own purges remove concept-side evidence first | d9ar; r6 s-3 |
| d-22 | protections no class plan may remove are user-asserted ones (their learned rows go); a `cli.log` `rmx grep P` record is learner evidence for `query/P` and its learned-only entities (217 here, 90 global) | d9ak; r6 s-4 |
| d-23 | a fully verified cross-store move purges the global entity even when user-protected (protection and source travel); the protection `source` vocabulary is `learner`, `user`, `system`, `removal` | d9al, d9am |
| d-24 | replay applies `evidence` appends and row-level ops together in TIMESTAMP order (ties by log position): an `evidence_remove` / `unlink` at `T` affects only what was appended at or before `T`, never a row re-learned or re-ingested after it; a named dead concept's evidence row therefore logs `evidence_remove` by name beside the tombstone | d9av; r7 b-1 |
| d-25 | 22.3's live global apply purges the learned-only members d-22 attributes to the learner (≤ 90), printing the count before the apply for the user | d9aw; r7 s-3 |
| d-26 | restore re-checks every recorded dead id (never re-inserts a row onto an id that is live now) and maps every old id the same manifest restores through its `id_map`, surviving rows included | r7 s-1, s-2 |
| d-27 | every row-level event plans 16/22 add (`evidence_remove`, `evidence_repoint`, `unlink`, `evidence_orphan_drop`, `learned_provenance`, `learned_provenance_move`) names its concept end as `(c_kind, c)`, built by ONE builder (`edge_records.row_event`, or `edge_event` for `unlink`), matched by ONE key (`edge_records.row_key`), resolved by ONE function (`edge_records.resolve_c_kind`, the bug-117 legacy rule) and counted by ONE helper (`row_skips`); an AST test holds every site to them | d9bl; r8 b-1 |
| d-28 | `evidence_orphan_drop` decides "dead" on a rebuild by the LOG timeline (latest `tombstone` vs latest `entity` event at or before the op), matching on `(linkage, c_kind, c, file, line, detail)`; `purge_entity` still deletes no evidence | d9bk; r8 s-1 |
| d-29 | the rebuild is the ONE replay path: the uncalled incremental path (`apply_log_delta` → `_apply_one_event` → `_apply_event_body`, and `_replay_concept`) is deleted by 16.6 R1f, no plan-22 op gets a branch there, and bug-120 closes by removal | d9bu; r9 s-2 |
| d-30 | a vacuum orphan whose concept is also dead is named by 22.1a's `names_from_log` and its drop keyed on each covering logged key (22.2 R9 step 4's keying, incl. the appends' `partition` field); a nameless one logs no event and is counted `orphan_drop_nameless` | r9 s-1, m-4 |
| d-31 | a live primitive's extra row op is the constant `LEGACY_PREFERRED_KIND` (not the legacy rule over live kinds) whenever the catalog kind differs and the live concept holds 0 or 1 identical copies, carrying `keep = n`; `legacy_misresolved` only for `n >= 2` | r9 m-1, m-2 |

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
4. **ADR-0004 "only" vs the explicit-selector commands — SETTLED (d9k, d9o).** The amendment is
   APPROVED and folded into `#rule-no-delete` / `#a14-removal-scope`; [[#scope]] follows it, and
   task 22.6 owns every path it names (r3 b-3, s-5).
5. **Plan-16 table row — SETTLED (re-review m-3).** The plan-16 16.6 row says "nothing here
   removes a row".
6. **Where "marked ambiguous" persists — SETTLED (no user decision).** In every manifest, recomputed
   on every audit; no sidecar column.
7. **Plan-19's `stale` mark — SETTLED (re-review m-3).** Plan-19's 19.4 R5 writes it.
8. **Walk exclusions — SETTLED by the spec (r3 b-1, `#open-22` item 8).** The probe's walk is
   RECOVERED, not inferred ([[task-22.1a-provenance-free-classes#r1-probe]]); the classifier's walk
   is named separately ([[task-22.1a-provenance-free-classes#r1-applied]]). 22.1a AC-5b prints the
   reproduction (with its `reproduced`/`drift` verdict) and the applied split side by side; the
   user sees both with the 22.5 dry run.
9. **Protections with no attributable source — RE-SETTLED by d9ab (r4 b-2).** Round 2's reading
   was wrong: every `protect` directly follows its `entity` in both logs because the compactor
   (`dump_catalog_to_log`) writes them that way, not because the learner made them. Under d9ab
   the origin is trusted only from `source` or a command record, and the read-only count
   ([[task-22.2-repair-then-remove#r5]]) finds 0 learner-attributed protections in either store:
   all 4,946 global (4,793 learned-only, 1,655 of them pytest-tmp) and all 2,256 here (426
   learned-only) are user-asserted. Their learned rows may be removed; the entities stay unless
   the user names them through a selector plan ([[task-22.3-bug-086-global-repair#r6]]).
   **AMENDED by d9ak(b) and d9aw (round 7, r7 s-3):** the `cli.log` grep record is a third
   source, which attributes 217 of this repo's and 90 of the global store's learned-only
   protections to the learner; those are purgeable whole when they are class members, and 22.3
   prints its count before the live apply ([[task-22.3-bug-086-global-repair#r3]]).

## Revision round 9 (2026-10-15) {#rev-round-9}

Answers [[bsd-plan16-22-spec-diffcheck-r9-29e335a]] (plan-22: s-1, s-2, m-1, m-2, m-4; m-3 and
m-5 are plan-16's, [[plan-16-invisible-grep-shim#rev-round-9]]; m-6 is the registry's, the
orchestrator's) and d9bu ([[plan-review-2026-10-14#t12-approvals]]). Code claims re-read at
`428267f`; `src/` is unchanged since `23ad703`. Later rows win.

| finding / decision | answered in |
|---|---|
| s-1 (both-dead vacuum orphans cannot be named; 5,341 on cliquedb) | [[task-22.6-removal-entry-points#r5-both-dead]]; 22.6 AC-6c; d-30 |
| s-2 / d9bu (the incremental replay path has no caller) | [[task-16.6-learned-row-validation#r1f]] deletes it; [[task-22.2-repair-then-remove#r3]] ("Both replay paths", the incremental order and resolver sentences, "two paths agree", the incremental counter and `unlink` sentence dropped), 22.2 AC-3f's incremental clause dropped, [[task-22.6-removal-entry-points#r5-timeline]]'s catalog-check branch dropped; d-29 |
| m-1 (`_row_op_c_kinds` read LIVE kinds) | [[task-22.2-repair-then-remove#r3]] "Which kind a LIVE primitive's op names"; 22.2 AC-3f run 3; d-31 |
| m-2 (`keep = n`) | [[task-22.2-repair-then-remove#r3]]; 22.2 AC-3f run 2; d-31 |
| m-4 (the drop's `partition` field) | [[task-22.6-removal-entry-points#r5]] "The partition field"; 22.6 AC-6b variant; d-30 |

rel: amends -> [[bsd-plan16-22-spec-diffcheck-r9-29e335a]]
rel: derives-from -> [[plan-review-2026-10-14#t12-approvals]]

## Revision round 8 (2026-10-15) {#rev-round-8}

Answers [[bsd-plan16-22-spec-rereview-r8-23ad703]] (plan-22: b-1, s-1, m-2..m-5; s-2 and m-1 are
plan-16's, [[plan-16-invisible-grep-shim#rev-round-8]]) and [[plan-review-2026-10-14#t12-approvals]]
(d9bk, d9bl). Code claims re-read at `23ad703` (0.78.3, bug-117); `src/` is unchanged from
`23ad703` to the revision's HEAD. Later rows win.

| finding / decision | answered in |
|---|---|
| b-1 / d9bl (the row ops predate bug-117: "as kind `concept`", no `c_kind`) | [[task-22.2-repair-then-remove#r3]] (event spellings, "How the ends resolve", the one kind-naming helper `_row_op_c_kinds`, `unlink` with `c_kind`), [[task-22.2-repair-then-remove#r9-dangling]] step 4; [[task-22.6-removal-entry-points#r5]]; the shared builder, key, resolver and counter in [[task-16.6-learned-row-validation#r1d-one-format]]; 22.2 AC-3b..3f, 16.6 AC-9d; d-27 |
| s-1 / d9bk (the orphan drop's "at that point" on a rebuild) | [[task-22.6-removal-entry-points#r5-timeline]]; 22.6 AC-6b; d-28 |
| m-2 (naming and reborn by the one legacy rule) | [[task-22.1a-provenance-free-classes#r1-covering]], re-measured counts in [[task-22.1a-provenance-free-classes#r1-dangling]]; [[task-22.2-repair-then-remove#r9-dangling]] reborn rule per row and per live covering key |
| m-3 (incremental vs rebuild legacy resolution) | [[task-22.2-repair-then-remove#r3]], [[task-16.6-learned-row-validation#r1d]] qualified; bug-registry row left to the orchestrator |
| m-4 (the rebuild's counters) | 22.2 R3 "Counters", R9 step 5; 22.2 AC-3b..3f, 22.6 AC-6b, AC-9c |
| m-5 (pins) | 22.2 R3, R9; 22.6 [[task-22.6-removal-entry-points#facts]]; 16.6 R1d |

rel: amends -> [[bsd-plan16-22-spec-rereview-r8-23ad703]]
rel: derives-from -> [[plan-review-2026-10-14#t12-approvals]]

## Revision round 7 (2026-10-15) {#rev-round-7}

Answers [[bsd-plan16-22-spec-rereview-r7-331b414]] (plan-22: b-1, s-1, s-2, s-3, m-1..m-4; m-5 is
plan-23's) and [[plan-review-2026-10-14#t12-approvals]] (d9av, d9aw, d9ay). Code claims re-read at
`77ac38f`. Later rows win.

| finding / decision | answered in |
|---|---|
| b-1 / d9av (`evidence_remove` replayed after later appends: a rebuild deletes rows the live store holds) | [[task-22.2-repair-then-remove#r3]] one row pass in timestamp order; [[task-16.6-learned-row-validation#r1d]] (same pass, lockstep); [[task-22.2-repair-then-remove#r9-dangling]] step 4 (named dead concept: `evidence_remove` by name too); [[task-22.6-removal-entry-points#r3]]; 22.2 AC-3d, AC-3e, 22.6 AC-4 clause; d-24 |
| s-1 (restore re-inserts a dead id a rebuild may have reused) | [[task-22.2-repair-then-remove#r4]] dead-id re-check (`restore_dead_id_reused`); 22.2 AC-4c; d-26 |
| s-2 (restored concept under a new id, its inbound rows under the old one) | [[task-22.2-repair-then-remove#r4]] `id_map` re-attach (re-inserted and surviving rows); 22.2 AC-4d, 22.6 AC-9c; d-26 |
| s-3 / d9aw (22.3 and 22.2 R5 still said no existing entity is purged) | [[task-22.3-bug-086-global-repair#r3]], 22.3 AC-1, AC-5; [[task-22.2-repair-then-remove#r5]] stale sentence deleted; [[#tasks]] row 22.3; d-16 amended, d-25; [[#open-after-revision]] item 9 amended |
| m-1 (the 8 "nameless" are reborn) | [[task-22.1a-provenance-free-classes#r1-dangling]] `unnamed:reborn` and the measured counts; [[task-22.2-repair-then-remove#r9-dangling]] reborn rule and step 5's reason; 22.1a AC-8a/8b, 22.2 AC-3b |
| m-2 (AC-8c scope; the predicate's maps; the bit half) | [[task-22.1a-provenance-free-classes#r1-dangling]] "One shared predicate"; 22.1a AC-8c |
| m-3 (`unlink` partition; naming partition; census default partition; `facts_path`) | [[task-22.2-repair-then-remove#r9-dangling]] step 4; [[task-22.1a-provenance-free-classes#r1-dangling]], [[task-22.1a-provenance-free-classes#r3]]; [[task-16.6-learned-row-validation#r7]] `--default-partition`; 22.1a AC-8a/8b, 22.2 AC-3b |
| m-4 (R2's concept-side rule vs the learned-row guard) | [[task-22.2-repair-then-remove#r2]] `ingest_ok=True`, two named callers, `detail` in the event; 22.2 AC-3c |
| m-5 (23.4's census count and `dead-linkage` case) | plan-23's owner ([[task-23.4-option-a-measurement]]); not edited here |
| d9ay (16.6 R1c retired) | [[task-16.6-learned-row-validation#r1c]]; 22.2 R2's collapse rule now cites 16.6 R1 |

rel: amends -> [[bsd-plan16-22-spec-rereview-r7-331b414]]
rel: derives-from -> [[plan-review-2026-10-14#t12-approvals]]

## Revision round 6 (2026-10-15) {#rev-round-6}

Answers [[bsd-plan16-22-spec-rereview-r6-0e77da3]] (plan-22: b-1, s-1, s-2, s-3, s-4, m-1..m-7)
and [[plan-review-2026-10-14#t12-approvals]] (d9aq, d9ar); cites d9ak/d9al/d9am
([[plan-review-2026-10-14#t11-approvals]]). Later rows win.

| finding / decision | answered in |
|---|---|
| b-1 / d9aq (`link_remove` by id: no reader; a rebuild resurrects the dead endpoints) | [[task-22.2-repair-then-remove#r9-dangling]], [[task-22.2-repair-then-remove#r3]] (no id-keyed op; `link_remove` withdrawn); 22.2 AC-3b; naming in [[task-22.1a-provenance-free-classes#r1-dangling]], 22.1a AC-8b counts; d-20 |
| s-1 (no manifest form for a dangling row) | [[task-22.2-repair-then-remove#r4]] `link_row` / `evidence_row`, restore by name; 22.2 AC-4c |
| s-2 (no partition) | [[task-22.1a-provenance-free-classes#r1-dangling]] store scope; [[task-22.2-repair-then-remove#r6]]; 22.1a AC-8a, 22.2 AC-14 |
| s-3 / d9ar (`dangling-evidence`; R9's purge claim) | [[#scope]]; [[task-22.1a-provenance-free-classes#r1-dangling]]; [[task-22.2-repair-then-remove#r2]], [[task-22.2-repair-then-remove#r9-dangling]]; [[task-22.6-removal-entry-points#r9]]; 22.2 AC-3c, 22.6 AC-9b; d-21 |
| s-4 / d9ak(b) | [[task-22.2-repair-then-remove#r5-grep-record]]; 22.2 AC-6c; d-22 |
| m-1 (counts) | [[task-22.1a-provenance-free-classes#r1-dangling]] measured table |
| m-2 (liveness text vs code) | [[task-22.1a-provenance-free-classes#r1-dangling]] predicate table |
| m-3 (AC-8 cannot fail; 8b procedure) | 22.1a AC-8a/8b/8c; [[task-16.6-learned-row-validation#r7]] `--census dangling-link` |
| m-4 (22.1 mutations; `ok`) | [[task-22.1-audit-classes#r1]]; 22.1 AC-2, AC-5e |
| m-5 (22.6 R4 lead) | [[task-22.6-removal-entry-points#r4]] |
| m-6 (stale code claims and lines) | [[task-22.6-removal-entry-points#facts]] re-read at `3d3c798`; [[task-22.6-removal-entry-points#r7]], [[task-22.6-removal-entry-points#r9]]; symbols in 22.1, 22.2, 22.6 and 16.6 |
| m-7 (task table, scope, unnumbered AC, file list, wave split) | [[#scope]], [[#tasks]], [[#dependencies]]; 22.2 AC-14 and [[task-22.2-repair-then-remove#files-to-modify]] |
| d9ak, d9al, d9am (reflected, now cited) | d-22, d-23; [[task-22.2-repair-then-remove#rev-round-6]], [[task-22.5-cross-store-move#rev-round-6]], [[task-22.6-removal-entry-points#rev-round-6]] |

rel: amends -> [[bsd-plan16-22-spec-rereview-r6-0e77da3]]
rel: derives-from -> [[plan-review-2026-10-14#t12-approvals]]

## Revision round 5 (2026-10-14) {#rev-round-5}

Answers [[bsd-plan16-22-spec-rereview-r4-878647c]] (plan-22: b-1, s-1, s-2, s-4, m-1, m-5, m-6;
shared b-2, s-3, m-2; r3 partials s-5, s-6) and [[plan-review-2026-10-14#t11-approvals]] (d9ab,
d9ac, d9z). Later rows win.

| finding / decision | answered in |
|---|---|
| b-1 (hash step removes edited-but-matching rows) | [[task-22.1-audit-classes#r1]] (hash = pairing key); 22.1 AC-5e; d-19 |
| b-2 / d9ab (compaction erases `source` and the sidecar events; adjacency attributes all) | [[task-22.2-repair-then-remove#r5]] (rule + the count); [[task-22.6-removal-entry-points#r6]] (`protect_source`, compactor); [[task-16.6-learned-row-validation#r1d]] (`learned_provenance` in the dump); [[task-22.3-bug-086-global-repair#r6]]; [[#open-after-revision]] 9; d-16 |
| s-1 (GMD branch purges the doc graph on every edit) | [[task-22.6-removal-entry-points#r4]]; 22.6 AC-5b |
| s-2 / d9ac (unclassified removal paths) | [[#scope]] table; [[task-22.6-removal-entry-points#r9]]; [[task-22.4-merge-writes#r5]]; d-17 |
| s-3 (census `HOME` redirect) | [[task-16.6-learned-row-validation#r7]]; [[task-22.1a-provenance-free-classes#r1-applied]] |
| s-4 (confirm hash; daemon ops; fallback) | [[task-22.6-removal-entry-points#r1]]; 22.6 AC-1b, AC-1c |
| m-1 (appendix bytes; procedure; file list) | [[task-22.1a-provenance-free-classes#appendix-probe]]; 22.1a [[task-22.1a-provenance-free-classes#files-to-modify]]; 16.6 R7 `probe-reproduction` |
| m-2 (churn bound and compaction; instant) | 22.1a AC-5b item 2 |
| m-5 (wave and test hand-over drift) | [[#dependencies]]; 22.6 AC-5 and [[task-22.6-removal-entry-points#files-to-modify]] (16.6 AC-11) |
| m-6 (`rmx fold-concept-dups`) | [[task-22.6-removal-entry-points#r7]], [[task-22.4-merge-writes#r5]], [[#scope]] |
| d9z (`id_map` caller) | [[task-22.2-repair-then-remove#r4]], 22.2 AC-4b; [[task-22.5-cross-store-move#r3]]; d-18 |
| r3 s-5 partial (sync and vacuum) | closed by s-1 and s-2 |
| r3 s-6 partial (census procedure) | closed by s-3 |

rel: amends -> [[bsd-plan16-22-spec-rereview-r4-878647c]]
rel: derives-from -> [[plan-review-2026-10-14#t11-approvals]]

## Revision round 3 (2026-10-14) {#rev-round-3}

Answers [[bsd-plan16-22-spec-rereview-r3-6091648]] (plan-22: b-1, b-2, b-3, s-6, m-3, m-4; shared
s-3, s-4, s-5, m-1, m-2) and [[plan-review-2026-10-14#t9-approvals]] (d9k, d9o). d9b is unchanged.
Later rows win.

| finding / decision | answered in |
|---|---|
| b-1 (22.1a AC-5b gate unsatisfiable) | [[task-22.1a-provenance-free-classes#r1-probe]] (probe recovered), [[task-22.1a-provenance-free-classes#r1-applied]], 22.1a AC-5a/5b; d-15; [[#open-after-revision]] 8 |
| b-2 (shifted rows removed) | [[task-22.1-audit-classes#r1]] set rule; 22.1 AC-5; [[task-22.2-repair-then-remove#r1]] |
| b-3 / d9k (forget and bulk-forget unowned; manifest cannot restore bodies, path, tldr, meta) | [[#scope]]; [[task-22.6-removal-entry-points#r1]], [[task-22.6-removal-entry-points#r2]]; [[task-22.2-repair-then-remove#r4]] + AC-4; d-13; [[#open-after-revision]] 4 |
| s-5 → d9o (sync purge, `vacuum`, fold, `unprotect`) | [[#scope]] table; [[task-22.6-removal-entry-points]] R3-R7; [[task-22.4-merge-writes#r5]]; 16.6 R1e; d-14 |
| s-3 (`Unverifiable` entity in a removal class) | [[task-22.1a-provenance-free-classes#r1-outcome]] `orphan-root:unverifiable`; 22.2 R9; 22.5 R1; 22.3 R1 |
| s-4 (union AC cannot fail) | 22.1 AC-4b; 16.6 AC-3h |
| s-6 (census procedure) | [[task-16.6-learned-row-validation#r7]] (owned by plan-16, used here); 22.1a R3, 22.1 R5 |
| m-1 (one replay pass) | [[task-22.2-repair-then-remove#r3]]; 16.6 R1d |
| m-2 (line splitting) | 16.6 R2 `split_lines`; 22.1a / 22.1 cite it |
| m-3 (`out-of-range` two predicates) | [[task-22.1-audit-classes#r1]] step 4 |
| m-4 (bucket 2 mixes readable and unreadable) | [[task-22.5-cross-store-move#r1]] buckets 2a / 2b |
| d9b | unchanged ([[#open-after-revision]] 2) |

rel: amends -> [[bsd-plan16-22-spec-rereview-r3-6091648]]
rel: derives-from -> [[plan-review-2026-10-14#t9-approvals]]

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
