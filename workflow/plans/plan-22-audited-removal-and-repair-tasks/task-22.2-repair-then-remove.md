---
gmd: "0.1"
id: task-22.2-repair-then-remove
title: "Task 22.2: repair what can be repaired, remove only what cannot — dry run, manifest, tombstones, ablation gate"
tags: [task, repair, removal, audit]
metadata:
  node_type: task
  status: pending
  created: 2026-10-07
---

# Task 22.2: the repair-then-remove engine {#root}

> Plan: [plan-22-audited-removal-and-repair](../plan-22-audited-removal-and-repair.md)
> Status: Pending
> Depends on: 22.1; plan-23 (bounded writes)

rel: part-of -> [[plan-22-audited-removal-and-repair]]
rel: depends-on -> [[task-22.1-audit-classes]]
rel: depends-on -> [[feedback_decay_never_loses_knowledge]]

## Requirements {#requirements}

1. **R1 Repairs** (user, 2026-10-07: "don't delete moves, repair them if possible"):
   - `moved` → re-point the evidence row's `line` to the recorded new line. The row, link and
     protection are kept.
   - `duplicate` → collapse to one row. Nothing distinct is lost.
   - `orphan-root` with a unique verifying root → rewrite to the absolute path.
   - `orphan-alias` whose canonical can be found by `canonical_name` → restore the `same_as` edge
     instead of deleting the alias.
2. **R2 Removals**, only for rows with no correct form:
   - `stale-line`, `out-of-range` and `missing-file` learned rows;
   - `orphan-root` rows with no verifying root;
   - `orphan-alias` rows with no canonical;
   - `empty-learned` concepts after their rows are removed.

   **`ambiguous` is never removed.**
3. **R3 The ablation gate** for concept classes (`orphan-alias`, `empty-learned`). The apply first
   runs the production eval path (`eval/production`: MemAware, CSN, cliquedb) with the candidates
   excluded. If hit@k or paired per-query MRR on the isolated concept path changes beyond noise,
   the apply refuses and reports the delta.
4. **R4 Dry run by default.** `--apply` writes. Every apply writes the manifest
   (`.refmatrix/removal/<ts>.jsonl`: for each repair the before/after, for each removal the full
   row) and emits tombstones. `rmx removal restore <manifest>` re-inserts removed rows.
5. **R5 Bounded.** Writes go through plan-23's bounded drain: one lock hold per batch, one Lance
   delete per kind.
6. **R6 Never ingest-owned.** An entity both ingested and learned keeps its ingest links. Only
   learned evidence and learned protection change.

## Acceptance criteria {#acceptance}

1. On a fixture, `moved` rows end on the correct line with link and protection intact, and **0**
   rows are deleted for them.
2. A dry run writes nothing (catalog hash, Lance versions and manifest dir all unchanged).
3. `--apply` then `restore <manifest>` returns the catalog to the pre-apply graph
   (`(linkage, concept, entity, weight)` tuples equal).
4. With a fixture eval where removing a candidate changes hit@k, the gate refuses and names the
   delta.
5. Mutations that must FAIL a test:
   - `moved` deleted instead of repaired;
   - `ambiguous` removed;
   - the manifest skipped;
   - the gate bypassed.
