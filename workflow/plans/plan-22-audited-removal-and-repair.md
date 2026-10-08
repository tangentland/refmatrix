---
gmd: "0.1"
id: plan-22-audited-removal-and-repair
title: "Plan 22: one audited path for every repair and removal — repair first, remove only what cannot be repaired"
tags: [plan, removal, repair, audit, grep-learning, concepts, bug-086]
metadata:
  node_type: plan
  status: drafting
  created: 2026-10-07
---

# Plan 22: audited removal and repair {#root}

**Date:** 2026-10-07
**Status:** Drafting. Task specs 22.1–22.4 are written.
**Origin:** the plan review's C1/C2/C3, applied by the user on 2026-10-07: "apply all the
consolidations, don't delete moves repair them if possible".

rel: derives-from -> [[plan-review-2026-10-07]]
rel: depends-on -> [[feedback_decay_never_loses_knowledge]]
rel: depends-on -> [[task-16.6-learned-row-validation]]
rel: depends-on -> [[plan-23-bounded-write-harness]]
rel: related-to -> [[plan-20-concept-similarity-eval]]
rel: related-to -> [[refmatrix/adr-0004-unified-location-space-index]]

## Why {#why}

Removal had four homes, and they disagreed:
- task 16.6's prune of learned rows;
- the "free culls" the concept exploration routed to 16.6. 16.6's evidence-row classes could not
  express them: orphan aliases are not grep-learned, and a df≤1 `query/*` row with one valid
  evidence row classifies `ok`.
- bug-086's global-store repair, planned both as a standalone daemon op and as
  `prune --class orphan-root`;
- concept merges, named as a removal path in ADR-0004 `#rule-no-delete` with no owner.

The user's rule ([[feedback_decay_never_loses_knowledge]]) allows removal ONLY through an explicit,
audited dry-run → apply path, and the 2026-10-07 decision adds: **repair before removal** ("don't
delete moves, repair them if possible"). This plan is that one path. {#why-body}

## Principles {#principles}

1. **Audit is read-only.** It classifies; it never writes (except plan-23's queued marks).
2. **Repair first.**
   - A row that can be made correct is re-pointed, never deleted. That covers: text that moved
     to another line; a relative path that resolves uniquely; an alias whose canonical can be
     found.
   - Removal is only for rows with no correct form.
3. **An ambiguous row is kept, never guessed.** Text found on several lines, or a path that
   resolves several ways, is reported `ambiguous` and left in place.
4. **Dry run by default; `--apply` writes.** Every apply prints counts by class, writes a
   recoverable manifest (`.refmatrix/removal/<ts>.jsonl`: every repaired and removed row, before
   and after) and emits tombstones so it replays.
5. **Never touch what ingest owns.** Only learned provenance (16.6 R1) and the classes below are in
   scope.
6. **Bounded writes:** plan-23's queue, drain and lock-hold discipline; one Lance delete per kind.

{#principles-body}

## Tasks {#tasks}

| task | what | acceptance (summary) |
|---|---|---|
| 22.1 | `rmx learn audit` / `rmx audit` classes: `ok`, `moved` (repairable), `ambiguous`, `stale-line`, `out-of-range`, `missing-file`, `duplicate`, `orphan-root`, plus the concept classes `orphan-alias` and `empty-learned` | one fixture row per class audits to exactly that class; read-only (catalog bytes unchanged) |
| 22.2 | the repair-then-remove engine: re-point `moved`, collapse `duplicate`, resolve `orphan-root` where unique; remove only `stale-line`/`out-of-range`/`missing-file`/unresolvable; the free-cull classes only behind the ablation gate | moved rows re-pointed (line correct, nothing deleted); the manifest round-trips; ablation gate blocks a cull that moves the eval |
| 22.3 | bug-086 as the first apply: the global store's relative learned rows — re-point the 476 that resolve uniquely, remove the 611 that cannot (user decision 2026-10-07) | dry-run count matches the catalog copy; post-apply global greps report 0 unreadable for those rows |
| 22.4 | merge writes: the owner of alias-map merges once ADR-0004's helix plan defines the alias map and plan-20 supplies the rule | blocked until both exist; spec says so |

Task specs: `workflow/plans/plan-22-audited-removal-and-repair-tasks/`.

## Decisions {#decisions}

| # | decision | source |
|---|---|---|
| d-1 | one removal path for learned rows, free culls, bug-086 and merges | user, 2026-10-07 (C1/C2) |
| d-2 | `moved` rows are repaired, never deleted; ambiguous rows are kept | user, 2026-10-07 |
| d-3 | the free culls (9,182 orphan aliases, 747 empty learned rows) pass an ablation gate before apply | exploration recommendation, C1 |
| d-4 | plan-17's nightly orphan-VECTOR reap stays in plan-17 (derived-index garbage, logged, with a recoverable list) | user, 2026-10-07 |
