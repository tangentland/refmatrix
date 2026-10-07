---
gmd: "0.1"
id: task-16.6-learned-row-validation
title: "Task 16.6: grep-learned rows carry provenance and read-time marks (audit/prune/repair moved to plan-22)"
tags: [task, grep, learning, validation, cull, provenance]
metadata:
  node_type: task
  status: drafting
  created: 2026-10-07
---

# Task 16.6: validate and cull grep-learned rows {#root}

> Plan: [plan-16-invisible-grep-shim](../plan-16-invisible-grep-shim.md)
> Status: DRAFTING, with the decisions taken (user, 2026-10-07; [[#decisions]]). The user asked for
> it on 2026-10-07: "rmx grep learning entries should be cullable and/or at least have a validation
> process to check for stale entries". Next: spec review with 16.1-16.5.
> Depends on: 16.1, which is the only writer that survives plan-16.

rel: part-of -> [[plan-16-invisible-grep-shim]]
rel: depends-on -> [[task-16.1-argv-faithful-learner]]
rel: related-to -> [[project_global_relative_rows_repair]]

## Why {#why}

Every grep-learned row is written by ONE writer, `_learn_grep_hits` (`daemon.py:4254`). It is
reached from three feeders:

- the RPC op `learn_from_grep`;
- the learn-queue drain;
- the daemon's context backstop.

Each feeder writes:

- a `query/<pattern>` concept, `protected=True`;
- an entity for each hit file, `protected=True`;
- a `mentions` link;
- one `linkage_evidence(file, line, detail="learned from grep '<pat>'")` row per hit. {#why-writes}

Nothing ever removes these rows, and nothing can tell they have gone stale:

1. **No provenance.** `linkage_evidence` has no learned-at, source or root column. The only marker is
   the free-text `detail`. A learned file entity shares `UNIQUE(partition, kind, name)` with the
   ingester's entity, so learning a file the ingester owns PROTECTS the ingested row, because
   `protected` only ratchets up. Learned rows cannot be selected apart from ingested ones.
2. **Read-time verification sees staleness and forgets it.** `verify_evidence_rows` drops a row
   whose file is unreadable, whose line is out of range, or whose line no longer matches, and counts
   it (`unreadable`, `dropped`). It writes nothing back, so the same dead row is re-read and
   re-dropped on every grep, forever.
3. **`protected` blocks every reaper.** `prune_noise` and `vacuum` skip protected rows. The only
   targeted cull is `rmx forget --namespace query`, which removes ALL learned concepts. It is not
   selective, and it leaves the protected file entities behind.
4. **`add_evidence` is an unconditional INSERT.** The same `(concept, entity, line)` accumulates once
   per learning run. 16.1 adds store-side idempotence for NEW rows; the existing duplicates stay. {#why-gaps}

Scale today: the global store holds 1,087 relative learned entities with 5,159 evidence rows, of
which about 700 read as unreadable on every global grep (bug-086). {#why-scale}

## Requirements (draft) {#requirements}

- **R1 Provenance.** Every learned evidence row records:
  - `source = 'grep-learn'`;
  - `learned_at`;
  - the absolute root it was learned under;
  - the pattern and its matching flags (`-i`, `-w`, `-F`/regex), so it can be re-checked under the
    caller's own rules.

  It lives in a sidecar table ([[#d-a]]).
- **R2/R3 moved to plan-22** (plan review C1, user 2026-10-07). The audit (`rmx learn audit`), its
  classes, and the prune/repair engine now live in [[plan-22-audited-removal-and-repair]]. That is
  ONE audited path for every removal, and it REPAIRS `moved` rows instead of deleting them. This
  task keeps what belongs to the learner: provenance (R1), read-time marks (R4), the provenance
  backfill (R5) and loud counting (R6).
- **R4 Passive marking.** Read-time verification records what it saw (`last_verified_at`,
  `stale_seen` count) through the shared durable queue and bounded drain of
  [[plan-23-bounded-write-harness]] (plan review C5), never inline under the lock ([[#d-b]]).
- **R5 Provenance backfill.** Rows learned before R1 have no provenance. One migration:
  - Backfill `source='grep-learn'` from `detail LIKE 'learned from grep%'`.
  - Set root = the project root, for project stores.
  - Leave the global store's roots NULL. Repairing or removing those rows (bug-086) is plan-22's
    first apply (task 22.3), not this task.
- **R6 No silent failures.** Every skipped, unreadable or un-culled row is counted and printed
  (project rule: memory-path discipline applies to the store).

## Acceptance (draft) {#acceptance}

1. Every evidence row written by the learner after this task carries the R1 provenance in the
   sidecar, and a re-learn of the same `(concept, entity, line)` writes no second row.
2. R5's backfill on a catalog COPY marks every `learned from grep` row and leaves no learned row
   without a provenance record. Global-store rows have root NULL.
3. A grep read that drops a stale learned row enqueues one mark, and the drain applies it in a
   bounded batch (plan-23's lock-hold probe).
4. Mutations that must FAIL a test:
   - provenance not written;
   - a mark written inline under the lock;
   - the backfill skipping rows silently.

The audit/prune/repair acceptance moved to plan-22. {#acceptance-moved}

## Decisions (user, 2026-10-07) {#decisions}

- **d-a. Provenance lives in a SIDECAR table** {#d-a}:
  `learned_evidence(evidence_rowid, source, learned_at, root, pattern, flags, last_verified_at,
  stale_seen)`. Ingest's `linkage_evidence` is untouched, so the migration is cheap and reversible.
- **d-b. Audit and prune run on demand, and read-time verification records marks** {#d-b}. The
  verification `grep_evidence` already does updates `last_verified_at` / `stale_seen` for learned
  rows, which makes audit cheap. Nothing deletes automatically: no scheduled prune.
- **d-c. (moved to plan-22, and AMENDED by the user 2026-10-07: "don't delete moves, repair them
  if possible").** `prune --apply` removes the non-`ok` classes EXCEPT `moved`, which is re-pointed.
  {#d-c}
- *(original d-c, superseded):* `prune --apply` removes every non-`ok` class by default: `moved`, `stale-line`,
  `out-of-range`, `missing-file`, `duplicate` and `orphan-root`. `--class` narrows it. The dry run
  remains the default.
- **d-d. Scope: inside plan-16, after 16.1** {#d-d}, reviewed in the same spec rounds.

**For the spec review (ch-bsd r7 #m-5):** `moved` is the one class whose row could be re-pointed
(the same text is now on another line) instead of deleted. d-c stands as decided. Whether
`prune --repoint-moved` belongs in 16.6 is a question for the review to put to the user, not a
change made here. {#d-c-review}

The read-time marks (d-b) are writes on a READ path, so they never take `_store_lock` inline. They
queue the way the learn queue does (`learn_queue.py`), and the daemon tick drains them in bounded
batches (the 0.72.3 lesson in `project_grep_learn_wall_and_queue`). The spec review must check this.
{#d-b-write-path}
