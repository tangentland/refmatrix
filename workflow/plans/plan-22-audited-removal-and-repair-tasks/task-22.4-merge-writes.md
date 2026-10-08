---
gmd: "0.1"
id: task-22.4-merge-writes
title: "Task 22.4 (blocked): concept merges written into the term-space alias map through the audited path"
tags: [task, merge, alias-map, concepts]
metadata:
  node_type: task
  status: blocked
  created: 2026-10-07
---

# Task 22.4: merge writes (blocked) {#root}

> Plan: [plan-22-audited-removal-and-repair](../plan-22-audited-removal-and-repair.md)
> Status: BLOCKED until ADR-0004's helix implementation plan defines the term-space alias map, and
> plan-20 recommends a merge rule.

rel: part-of -> [[plan-22-audited-removal-and-repair]]
rel: depends-on -> [[plan-20-concept-similarity-eval]]
rel: depends-on -> [[refmatrix/adr-0004-unified-location-space-index]]

## Requirements (to be completed when unblocked) {#requirements}

1. **R1** A merge is a REPAIR, not a removal: the merged concept becomes an alias pointing at its
   canonical in the alias map, and every edge stays reachable through the canonical.
2. **R2** Merges use plan-20's rule and threshold; nothing below the rule's precision bound is
   merged.
3. **R3** Dry run, manifest, tombstones and `restore`, exactly as 22.2.

Owner of ADR-0004 `#rule-no-delete`'s "merge" path. {#owner}
