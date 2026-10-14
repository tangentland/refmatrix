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
> Status: Pending (revision after the 2026-10-14 decision log)
> Wave: 1, after 22.2 and ahead of 22.3 (d8c; #t8-wave1).
> Depends on: 22.1a (`orphan-root:resolved` with its absolute path), 22.2 (engine, primitives,
> events, manifest, restore, apply interface), 23.1 (`bind`), 23.2 (recorder), 23.0 (sandbox).

d6b, as amended by d8c: the 476 uniquely verified global entities (2026-10-07 probe) are NOT
rewritten inside the memory-only global store (0.65.0 guard; 22 #s-3). An entity whose resolved
file lies under a registered project store's root MOVES to that store; an entity under no project
store's root gets an AUDITED forget whose manifest keeps it restorable (grep relearns it on real
use). **This knowingly changes those rows from "recovered" (the 2026-10-07 decision in memory
`project_global_relative_rows_repair`) to "forgotten, restorable"** (d8c). This task is the owner
the decision-log review asked for (DL #b-4).

rel: part-of -> [[plan-22-audited-removal-and-repair]]
rel: depends-on -> [[task-22.1a-provenance-free-classes]]
rel: depends-on -> [[task-22.2-repair-then-remove]]
rel: depends-on -> [[feedback_store_calls_via_daemon]]
rel: depends-on -> [[feedback_daemon_call_retries_multiply_timeouts]]
rel: derives-from -> [[plan-review-2026-10-14#t8-revisited]]
rel: amends -> [[project_global_relative_rows_repair]]
rel: motivates -> [[task-22.3-bug-086-global-repair]]

## Requirements {#requirements}

1. **R1 The root set and the split (d8c; DL #b-4).** {#r1}
   - **Registered project roots** = the registered daemon list: the launchd-supervised stores
     (`discovery._roots_from_launchd`, the 8 stores at the decision), NOT `registry.json` (which
     names 3). The global store is excluded from the target set: its project root is `$HOME`,
     which contains every path. A root whose daemon does not answer a ping is reported and its
     rows stay put (neither moved nor forgotten) until it is up.
   - **Owner** of a resolved absolute path = the DEEPEST registered project root that contains it.
   - The dry run reports three buckets with entity and row counts: `move → <store>` (per target
     store), `forget (no owning store)`, `held (target daemon down)`. The user sees these counts
     before any apply; the decision log's "≥ 114 forgotten" is a lower bound to compare against,
     not an expected value ([[plan-22-audited-removal-and-repair#open-after-revision]] 2).
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
4. **R4 Audited forget for no-owner rows.** Through 22.2 unchanged: manifest with the full rows,
   restorable with `removal_restore`. {#r4}
5. **R5 Interface (d8g; 22 #b-8 clause).** `rmx removal apply --root <global root> --target-root
   <project root> --manifest ID --confirm HASH` (one target per invocation; the forget bucket uses
   `--root` alone). Both roots must be named explicitly, must be in the R1 set (the target) or be
   the global root (the source), and must equal the roots of the daemons called. {#r5}
6. **R6 Restore of a move** reverses all four steps: re-insert into global by name, then remove
   the imported rows from the target (merged rows detach; entities created by the import are
   purged only if they hold no other link). {#r6}

## Acceptance criteria {#acceptance}

1. **Split.** On a sandbox with three project stores (one nested in another) and a global clone,
   the dry run assigns each resolved entity to the deepest containing root, puts the rest in
   `forget`, puts a down store's rows in `held`, and never picks the global store as a target.
2. **Crash at every step.** Killing the apply after each of read, copy, verify and forget, then
   resuming, ends with every row exactly once (in the target if verified, else still in global),
   0 lost, 0 duplicated. Mutation: forgetting before verify must FAIL.
3. **Idempotent copy.** Sending one batch twice adds 0 rows the second time.
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
