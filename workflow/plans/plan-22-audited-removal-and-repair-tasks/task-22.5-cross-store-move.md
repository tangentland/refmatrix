---
gmd: "0.1"
id: task-22.5-cross-store-move
title: "Task 22.5: move the global store's uniquely resolved learned rows into their owning project store — copy, verify, forget across two daemons, manifest-backed"
tags: [task, repair, global-store, cross-store, bug-086, wave-1]
metadata:
  node_type: task
  status: pending
  created: 2026-10-14
---

# Task 22.5: the cross-store move {#root}

> Plan: [plan-22-audited-removal-and-repair](../plan-22-audited-removal-and-repair.md)
> Status: Pending (revision round 3, 2026-10-14; [[#rev-round-3]])
> Wave: 1, after 22.2 and ahead of 22.3 (d8c; #t8-wave1).
> Depends on: 22.1a (`orphan-root:resolved` with its absolute path), 22.2 (engine, primitives,
> events, manifest, restore, apply interface), 23.1 (`bind`), 23.2 (recorder), 23.0 (sandbox).

d6b, as amended by d8c and d9b: the uniquely verified global entities (476 at the 2026-10-07
probe) are NOT rewritten inside the memory-only global store (0.65.0 guard; 22 #s-3). An entity
whose resolved file lies under a registered project store's root MOVES to that store. **What
happens to the rest is NOT decided yet (d9b, superseding d8c's "≥ 114 forgotten").** d8c's number
came from a misread probe: the "8 registered roots" included the global store's own launchd root
(`com.refmatrix.daemon.tholley`, `REFMATRIX_ROOT=/Users/tholley/.refmatrix`), and all 362
`$HOME`-verified entities matched there and under none of the 7 project roots, so "476 − 362 =
114 under no store" does not follow; the no-owner count can be anywhere from 0 to 476, and those
rows read correctly today (`grep_evidence` resolves global rows against `$HOME`), so they are not
bug-086's symptom. R1's dry run reports the real split; for the no-owner buckets this task applies
NOTHING until the user rules on those counts. This task is the owner the decision-log review asked
for (DL #b-4).

rel: part-of -> [[plan-22-audited-removal-and-repair]]
rel: depends-on -> [[task-22.1a-provenance-free-classes]]
rel: depends-on -> [[task-22.2-repair-then-remove]]
rel: depends-on -> [[feedback_store_calls_via_daemon]]
rel: depends-on -> [[feedback_daemon_call_retries_multiply_timeouts]]
rel: derives-from -> [[plan-review-2026-10-14#t8-revisited]]
rel: derives-from -> [[plan-review-2026-10-14#t9]]
rel: amends -> [[bsd-plan16-22-spec-rereview-32dde06]]
rel: amends -> [[bsd-plan16-22-spec-rereview-r3-6091648]]
rel: depends-on -> [[task-16.6-learned-row-validation]]
rel: amends -> [[project_global_relative_rows_repair]]
rel: motivates -> [[task-22.3-bug-086-global-repair]]

## Requirements {#requirements}

1. **R1 The root set and the split (d8c, d9b; DL #b-4; s-2; m-8).** {#r1}
   - **Registered store roots** = the registered daemon list, `discovery._roots_from_launchd()`
     (the `REFMATRIX_ROOT` of each `com.refmatrix.daemon.*` plist: 8 at the decision), NOT
     `registry.json` (which names 3). Each is a STORE root (`<project>/.refmatrix`); its PROJECT
     root is its parent.
   - **The target set** = those roots minus the global store (`discovery.is_global_root(r)`, true
     for `~/.refmatrix`, whose project root `$HOME` contains every path). A root whose daemon does
     not answer a ping is reported and its rows stay put (neither moved nor forgotten) until it is
     up.
   - **Owner** of a resolved absolute path = the target root with the DEEPEST project root that
     contains it.
   - **The dry run's buckets**, each with entity AND row counts and a per-top-level-prefix
     breakdown under the project or home base (e.g. `github/atollogy/<x>`, `Library/`,
     `lib/python3.10`), so the user can rule on what they are:
     1. `move → <store>` (per target store): `orphan-root:resolved` (22.1a) under a target's
        project root;
     2. `no project store`: `orphan-root:resolved` under NO target's project root, SPLIT by
        22.1a's readable-today attribute (r3 m-4): `2a readable today` (the row also reads
        correctly at `$HOME/<rel>`, where global rows resolve today) and `2b unreadable today`
        (bug-086's symptom: the walk found the file, `$HOME/<rel>` does not hold it). d9b's
        ruling is about readable rows; the user rules on 2a and 2b as separate numbers;
     3. `global root only`: `orphan-root:home-readable` (22.1a): no walk candidate verified, but
        the row reads correctly today at `$HOME/<rel>`, the global store's own resolution base;
     4. `held (target daemon down)`;
     5. `held (unverifiable)`: `orphan-root:unverifiable` (22.1a, r3 s-3): no candidate decided
        and at least one reading was `Unverifiable` (counted by reason). Never moved, never
        forgotten by this task; reported every run.
   - **Buckets 2 (2a and 2b) and 3 are held for the user (d9b).** The plan manifest records
     `no_owner_ruling: pending`. An apply of a `pending` manifest performs bucket 1 only and counts
     buckets 2 and 3 as `held_for_ruling`; it never forgets them. After the user rules, a new dry
     run records `--no-owner-ruling forget|keep` in the manifest (and so in its hash, d8g):
     `forget` routes them through R4; `keep` leaves them in global untouched, recorded. No count is
     presumed: the decision log's "≥ 114" is withdrawn, and the re-review's log-population proxy
     (about 89% of `$HOME`-resolvable learned files lie under no project root) is context, not an
     expected value.
2. **R2 Copy → verify → forget, two daemons, two transactions (DL #b-4).** Per batch of entities,
   in this order, each step recorded in the 22.2 intent-log manifest (kept in the GLOBAL store's
   `.refmatrix/removal/`, with a copy of each step's record in the target's): {#r2}
   1. **Read** the batch's entities, evidence rows, sidecar rows, links and flags from the global
      daemon (read op).
   2. **Copy** into the target through a new TARGET-daemon write op `learned_import`: each row's
      `file` rewritten relative to the target's project root (the learner's convention in project
      stores); the `query/<pattern>` concept upserted; collisions with an existing entity of the
      same `(partition, kind, name)` MERGE exactly as 22.2's `rename_entity` merge (evidence and
      links attach, `protected` = max, ingest state untouched). Idempotent by row identity: a
      re-sent batch adds nothing.
      - **Sidecar rows travel with their evidence (s-5; owner: this op).** Every global sidecar
        row of a copied identity is written in the target, in the same transaction as its
        evidence row, through 16.6's `Store.add_learned_provenance` with the TARGET's key
        (`entity_id`, `linkage_id`, `concept_id` of the target; `file` rewritten; same `line`
        and `rules_sha`) and `root` set to the target's project root (16.6 R1's `root` row);
        every other column is copied unchanged. The target logs the `evidence` and
        `learned_provenance` events (16.6 R1d), so the target's rebuild reproduces them. A
        global evidence row with no sidecar row is imported and then backfilled in the target by
        16.6 R5's routine (counted).
   3. **Verify** on the target through a read op: every imported row exists by NAME and its line
      verifies (22.1a's permissive reading). A row that fails to verify on the target is NOT
      forgotten in global; it is reported and the batch stays `copied`, not `verified`.
   4. **Forget** in global through 22.2's engine (row-level `remove_evidence`, then the entity
      purge rule of 22.2 R2), only for rows whose target verify succeeded.
   - Every cross-daemon call uses `retries=0` and a single-flight guard per manifest
     (`feedback_daemon_call_retries_multiply_timeouts`); a timeout re-reads state, it never
     re-sends blindly.
   - **Crash rule:** re-running `apply` with the same manifest resumes from the last recorded step
     of each batch. A crash after copy and before forget leaves a duplicate that the resume removes
     from global only after verify; it never loses a row.
3. **R3 Vectors (DL #s-7).** The target store embeds the moved entities through its normal embed
   path (shared embedder); the global vectors are dropped with the forget and recorded in the
   manifest as "had a vector", so restore re-embeds ([[task-22.2-repair-then-remove#r4]]). {#r3}
4. **R4 Audited forget for no-owner rows, only on the user's ruling (d9b).** Runs only for a
   manifest whose `no_owner_ruling` is `forget`. Through 22.2 unchanged: manifest with the full
   rows (sidecar rows included), restorable with `removal_restore`. {#r4}
5. **R5 Interface (d8g; 22 #b-8 clause; m-8).** `rmx removal apply --root ~/.refmatrix
   --target-root <project>/.refmatrix --manifest ID --confirm HASH` (one target per invocation; the
   forget bucket, once ruled, uses `--root` alone). Both are STORE roots, spelled as 22.2 R8 states
   ([[task-22.2-repair-then-remove#r8]]): the source must satisfy `discovery.is_global_root`, the
   target must be in R1's target set, and each must equal `Path(d.root)` of the daemon called. A
   project root (`$HOME`, or a target's parent dir) is refused. {#r5}
6. **R6 Restore of a move** reverses all four steps: re-insert into global by name, then remove
   the imported rows from the target (merged rows detach; entities created by the import are
   purged only if they hold no other link). {#r6}

## Acceptance criteria {#acceptance}

1. **Split (s-2, d9b).** On a sandbox with three project stores (one nested in another), a global
   fixture store, and injected launchd roots INCLUDING the global store's own root: the dry run
   assigns each resolved entity to the deepest containing project root; puts a resolved entity
   under no project root in `no project store`, in `2a` when its `$HOME/<rel>` reads correctly and
   in `2b` when it does not (r3 m-4); puts a `home-readable` entity in `global root only`; puts a
   down store's rows in `held`; puts an `orphan-root:unverifiable` entity in `held
   (unverifiable)`; never picks the global store as a target; and prints entity and row counts per
   bucket with the prefix breakdown. Mutations: "count the global store's root as a project root"
   FAILS it (the `no project store` entity is assigned to global); "one `no project store`
   bucket" FAILS the 2a/2b split; "forget `orphan-root:unverifiable` with bucket 2" FAILS it.

   **1b. Nothing applied to the no-owner buckets until the ruling (d9b).** Applying a `pending`
   manifest moves bucket 1 and leaves every bucket-2 and bucket-3 row in global byte-equal
   (counted `held_for_ruling`); a manifest with `--no-owner-ruling keep` also leaves them; only
   `forget` removes them, restorably. Mutation "forget bucket 2 on a pending manifest" FAILS it.
2. **Crash at every step.** Killing the apply after each of read, copy, verify and forget, then
   resuming, ends with every row exactly once (in the target if verified, else still in global),
   0 lost, 0 duplicated. Mutation: forgetting before verify must FAIL.
3. **Idempotent copy; sidecar joins (s-5).** Sending one batch twice adds 0 rows the second time.
   After the copy, every imported sidecar row joins its target evidence row on all five identity
   columns and carries `root` = the target's project root; a rebuild of a sandbox copy of the
   target reproduces them. Mutation "import evidence without its sidecar rows" FAILS it.
4. **Collision merge.** A moved entity whose name already exists in the target as an ingested
   file entity merges: ingest links and `tracked_files` byte-equal, learned evidence attached.
5. **Verify failure keeps the row.** A row whose file changed on disk between audit and copy fails
   the target verify and stays in global.
6. **Restore.** `restore` of a completed move returns both stores to their pre-apply state by name
   (22.2 AC-4's comparison, in both stores), vectors re-embedded where they existed.
7. **Roots.** Apply refuses a target not in the registered set, the global store as a target, and
   any unnamed root. Mutation: falling back to `registry.json` must FAIL AC-1 (a launchd-only store
   receives no rows).
8. **No direct Store().** The move opens no `Store()` on either side outside the daemon ops
   (asserted by the 23.0 guard on the sandbox).

## Test strategy {#test-strategy}

All tests run inside task 23.0's sandbox (d1a/d1b): two or more in-process daemons on short
`mkdtemp` roots, `$HOME`/global root/registry/LaunchAgents redirected before import, launchd roots
injected (no real `launchctl`), the 23.2 recorder on both daemons, no `rmx` subprocess. Crashes are
injected between steps, not by killing a real process. Every mutation is pre-registered and must
turn its test RED.

## Revision (2026-10-14 decision log) {#rev-2026-10-14}

| finding / decision | answered in |
|---|---|
| d6b (move, not rewrite; audited forget) | [[#root]], [[#r2]], [[#r4]] |
| d8c (registered daemon list; 22.5 ahead of 22.3; knowing change) | [[#root]], [[#r1]] |
| DL #b-4 (owner, root set, two daemons, the ≥ 114 flip, vectors) | [[#r1]], [[#r2]], [[#r3]]; AC-1, AC-2 |
| DL #s-7 (vectors) | [[#r3]]; AC-6 |
| 22 #s-3 (memory-only global; collision merge) | [[#root]], [[#r2]]; AC-4 |
| 22 #b-8 clause, d8g | [[#r5]]; AC-7 |

## Revision round 2 (2026-10-14) {#rev-round-2}

Answers [[bsd-plan16-22-spec-rereview-32dde06]] and [[plan-review-2026-10-14#t9]]. Later rows win;
d9b supersedes d8c's "≥ 114 forgotten".

| finding / decision | answered in |
|---|---|
| d9b / re-review s-2 (d8c's "≥ 114" misread the probe; no-owner rows read correctly today) | [[#root]] (the misreading stated, "≥ 114" and "lower bound" withdrawn); [[#r1]] buckets `no project store` and `global root only`, held with `no_owner_ruling: pending`; [[#r4]] forget only on a `forget` ruling; AC-1, AC-1b + mutations |
| re-review s-5 / #t9-fixes "22.2/22.5 update provenance keys" | [[#r2]] step 2 "Sidecar rows travel with their evidence" (owner: `learned_import`); AC-3 |
| re-review m-4 (16.6's `root` NULL "until 22.3") | [[#r2]] step 2 sets `root` to the target's project root |
| re-review m-8 (root spellings) | [[#r1]] store roots vs project roots; [[#r5]]; 22.2 R8 |

## Revision round 3 (2026-10-14) {#rev-round-3}

Answers [[bsd-plan16-22-spec-rereview-r3-6091648]]. Later rows win; d9b is unchanged.

| finding / decision | answered in |
|---|---|
| r3 m-4 (bucket 2 mixes readable-today and unreadable rows) | [[#r1]] bucket 2 split into 2a / 2b, ruled on separately; AC-1 + mutation |
| r3 s-3 (`orphan-root:unverifiable`) | [[#r1]] bucket 5 `held (unverifiable)`; AC-1 + mutation |
| d9b | unchanged: buckets 2a, 2b and 3 held until the user rules |

rel: amends -> [[bsd-plan16-22-spec-rereview-r3-6091648]]
