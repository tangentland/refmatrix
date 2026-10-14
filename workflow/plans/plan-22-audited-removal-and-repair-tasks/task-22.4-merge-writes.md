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
> Whether plan-22 can close with this task handed over is listed in
> [[plan-22-audited-removal-and-repair#open-after-revision]] 3.

rel: part-of -> [[plan-22-audited-removal-and-repair]]
rel: depends-on -> [[plan-20-concept-similarity-eval]]
rel: depends-on -> [[refmatrix/adr-0004-unified-location-space-index]]
rel: depends-on -> [[task-22.2-repair-then-remove]]

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

Owner of ADR-0004 `#rule-no-delete`'s "merge" path. {#owner}

## Revision (2026-10-14 decision log) {#rev-2026-10-14}

| finding / decision | answered in |
|---|---|
| 22 #m-5 (blocks on a plan that does not exist; plan close) | [[#root]] |
| d8g, 22 #b-8 clause, d1a/d1b | R3, R4 |
