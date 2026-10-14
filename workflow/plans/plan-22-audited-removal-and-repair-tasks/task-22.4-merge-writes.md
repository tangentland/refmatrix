---
gmd: "0.1"
id: task-22.4-merge-writes
title: "Task 22.4 (blocked): concept merges written into the term-space alias map through the audited path"
tags: [task, merge, alias-map, concepts]
metadata:
  node_type: task
  status: blocked
  created: 2026-10-07
  revised: 2026-10-14
---

# Task 22.4: merge writes (blocked) {#root}

> Plan: [plan-22-audited-removal-and-repair](../plan-22-audited-removal-and-repair.md)
> Status: Pending (revision after the 2026-10-14 decision log) — BLOCKED until ADR-0004's helix
> implementation plan defines the term-space alias map, and plan-20 recommends a merge rule. That
> helix plan does not exist yet (`plan-review-2026-10-07` `#gaps`, "No plan yet"; 22 #m-5).
> **Hand-over (d9j, user 2026-10-14):** plan-22 may close with this task handed to the future
> ADR-0004 helix implementation plan; when that plan is written it takes this spec as its merge
> task, and plan-22's engine (22.2) is its only removal/repair path.

rel: part-of -> [[plan-22-audited-removal-and-repair]]
rel: depends-on -> [[plan-20-concept-similarity-eval]]
rel: depends-on -> [[refmatrix/adr-0004-unified-location-space-index]]
rel: depends-on -> [[task-22.2-repair-then-remove]]
rel: derives-from -> [[plan-review-2026-10-14#t9]]
rel: derives-from -> [[plan-review-2026-10-14#t9-approvals]]
rel: related-to -> [[task-22.6-removal-entry-points]]

## Requirements (to be completed when unblocked) {#requirements}

1. **R1** A merge is a REPAIR, not a removal: the merged concept becomes an alias pointing at its
   canonical in the alias map, and every edge stays reachable through the canonical.
2. **R2** Merges use plan-20's rule and threshold; nothing below the rule's precision bound is
   merged.
3. **R3** Through 22.2's engine unchanged: `removal_audit` plan manifest, `removal_apply` with
   manifest id + `--confirm <hash>` + explicit `--root` (d8g; 22 #b-8 clause), row-level events,
   intent-logged manifest, `removal_restore` by name, `bind` per batch, the ablation gate on a
   copy of the same store.
4. **R4** Tests run in task 23.0's sandbox (d1a/d1b).
5. **R5 `fold_concept_dups` travels with this task (d9o).** {#r5} The user classified
   `fold_concept_dups` (`store.py:5808`: folds a concept into the same-named memory, migrates its
   edges, purges the concept) as a MERGE: a plan-22 entry point owned with merge writes by the
   helix plan. So the helix plan takes it over with this spec, and it becomes an entry point to
   R3's path. Until then it is unchanged, and 22.6 R7 lists it as an unrouted merge path in every
   `removal_audit --list` ([[task-22.6-removal-entry-points#r7]]). Its surfaces are `rmx memory
   dedup` (`cli.py:12628`) and MCP `rmx_memory` action `dedup` (`verbs.py:1029`) (r4 m-6).
   **`merge_partition` travels with it (d9ac).** `Store.merge_partition` (`store.py:1606`; it
   deletes source `memory_content` at `:1765` and source entities at `:1812`) is a MERGE entry
   point owned by the same helix plan. Its dropped fragment bits already go to a manifest through
   the bug-105 hotfix (`repair_fragments(..., manifest_dir=...)`, branch
   `bug-105-fragment-partition`), which the helix plan builds on once it is merged to `master`.
   22.6 R7 lists it as `merge-partition` in `removal_audit --list`.

Owner of ADR-0004 `#rule-no-delete`'s "merge" path. {#owner}

## Revision (2026-10-14 decision log) {#rev-2026-10-14}

| finding / decision | answered in |
|---|---|
| 22 #m-5 (blocks on a plan that does not exist; plan close) | [[#root]] |
| d8g, 22 #b-8 clause, d1a/d1b | R3, R4 |

## Revision round 2 (2026-10-14) {#rev-round-2}

| finding / decision | answered in |
|---|---|
| d9j (plan-22 closes with 22.4 handed to the helix plan; re-review open item 3, plan-22 r1 m-5) | [[#root]] hand-over note |

## Revision round 3 (2026-10-14) {#rev-round-3}

| finding / decision | answered in |
|---|---|
| d9o (`fold_concept_dups` = a merge, plan-22 entry point owned by the helix plan) | [[#r5]]; [[task-22.6-removal-entry-points#r7]] |

## Revision round 5 (2026-10-14) {#rev-round-5}

| finding / decision | answered in |
|---|---|
| d9ac / r4 s-2 (`merge_partition` is a helix-owned merge entry point) | [[#r5]]; [[task-22.6-removal-entry-points#r7]] |
| r4 m-6 (real command names) | [[#r5]] |

rel: amends -> [[bsd-plan16-22-spec-rereview-r4-878647c]]
rel: derives-from -> [[plan-review-2026-10-14#t11-approvals]]
