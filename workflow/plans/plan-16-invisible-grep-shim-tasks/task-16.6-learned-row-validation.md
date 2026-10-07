---
gmd: "0.1"
id: task-16.6-learned-row-validation
title: "Task 16.6: grep-learned rows carry provenance, are validated against the files they claim, and can be culled"
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
- **R2 Validation, `rmx learn audit`.** A read-only pass over every learned row. It re-reads the
  claimed line and classifies the row:
  - `ok`;
  - `moved` (the same text is now on another line);
  - `stale-line` (the line no longer matches the pattern);
  - `out-of-range`;
  - `missing-file`;
  - `duplicate`;
  - `orphan-root` (a relative row whose root is unknown, which is bug-086's shape).

  It prints counts per class and per pattern, and lists rows with `--list`. Exit 0 when the scan
  completes; the counts are the answer. This uses the verifier `grep_evidence` already uses
  (`evidence_line_matches`); there is no second matcher.
- **R3 Cull, `rmx learn prune`.** Removes the rows `audit` classified, by class (default: every
  non-`ok` class, per [[#d-c]]; `--class` narrows it).
  - Dry run by default; `--apply` writes.
  - It goes through a daemon op under one `_store_lock` hold per bounded batch. That is bug-085's
    lesson: no unbounded lock hold, and one Lance delete per kind.
  - It removes evidence and `mentions` links. It drops a `query/*` concept that has no evidence left.
  - It NEVER purges an entity the ingester owns. It only clears the protection that learning
    added (needs R1).
  - It emits tombstones so the delete replays.
- **R4 Passive marking.** Read-time verification records what it saw (`last_verified_at`,
  `stale_seen` count) through a queue, never inline under the lock ([[#d-b]]).
- **R5 Repair of existing rows.** Rows learned before R1 have no provenance. One migration:
  - Backfill `source='grep-learn'` from `detail LIKE 'learned from grep%'`.
  - Set root = the project root, for project stores.
  - Leave the global store's roots NULL, which classifies those rows `orphan-root`. bug-086's
    scheduled repair then becomes `rmx learn prune --class orphan-root --apply` in the global store,
    after its 476 uniquely verifiable rows are rewritten to absolute paths.
- **R6 No silent failures.** Every skipped, unreadable or un-culled row is counted and printed
  (project rule: memory-path discipline applies to the store).

## Acceptance (draft) {#acceptance}

1. A fixture store with one learned row of each class makes `rmx learn audit` print exactly one in
   each class. The same fixture after a file edit moves the right rows to `stale-line` or `moved`.
2. `rmx learn prune` (dry run) changes nothing: catalog bytes and Lance versions are unchanged.
   `--apply` removes exactly the non-`ok` rows, and a second `audit` reports only `ok`.
3. An entity both ingested and learned survives prune with its ingest links intact, and loses only
   its learned protection and learned evidence.
4. A prune of N rows across K kinds issues at most K Lance deletes and holds `_store_lock` no longer
   than the batch bound (measured, not asserted from code).
5. On a COPY of the live global catalog (never the live store), audit's `orphan-root` count matches
   bug-086's ~700 unreadable rows, to within rows learned since that count.
6. The CLI and MCP surfaces are one verb (verb-parity test).

## Decisions (user, 2026-10-07) {#decisions}

- **d-a. Provenance lives in a SIDECAR table** {#d-a}:
  `learned_evidence(evidence_rowid, source, learned_at, root, pattern, flags, last_verified_at,
  stale_seen)`. Ingest's `linkage_evidence` is untouched, so the migration is cheap and reversible.
- **d-b. Audit and prune run on demand, and read-time verification records marks** {#d-b}. The
  verification `grep_evidence` already does updates `last_verified_at` / `stale_seen` for learned
  rows, which makes audit cheap. Nothing deletes automatically: no scheduled prune.
- **d-c. `prune --apply` removes EVERY non-`ok` class by default** {#d-c}: `moved`, `stale-line`,
  `out-of-range`, `missing-file`, `duplicate` and `orphan-root`. `--class` narrows it. The dry run
  remains the default.
- **d-d. Scope: inside plan-16, after 16.1** {#d-d}, reviewed in the same spec rounds.

The read-time marks (d-b) are writes on a READ path, so they never take `_store_lock` inline. They
queue the way the learn queue does (`learn_queue.py`), and the daemon tick drains them in bounded
batches (the 0.72.3 lesson in `project_grep_learn_wall_and_queue`). The spec review must check this.
{#d-b-write-path}
