---
gmd: "0.1"
id: plan-review-2026-10-07
title: "Plan review 2026-10-07: consolidation proposals and execution order across the open plans"
tags: [planning, review, consolidation, sequencing]
metadata:
  node_type: review
  status: applied
  created: 2026-10-07
---

# Plan review, 2026-10-07 {#root}

The user, 2026-10-07: "given the amount of plan restructuring, we should review all open plans
looking for areas to consolidate and determine the optimal execution order". A read-only review of
`plan-of-plans` and every open plan, task spec, ADR-0004, the explorations and the open bugs. Every
proposal below was **APPLIED** by the user on 2026-10-07 ("apply all the consolidations, don't
delete moves repair them if possible"): plans 21/22/23 were created, and 13/14/16/17/18/19/20 and
ADR-0004 were amended. {#lead}

rel: related-to -> [[plan-of-plans]]
rel: related-to -> [[refmatrix/adr-0004-unified-location-space-index]]

## Contradictions to resolve {#contradictions}

| # | contradiction | where | proposal |
|---|---|---|---|
| C1 | The "free culls" (9,182 orphan aliases, 747 empty protected `query/*`) are routed to task 16.6, but 16.6's classes are evidence-row classes. Orphan aliases are not grep-learned, and a df≤1 `query/*` row with one valid evidence row classifies `ok`. The exploration's ablation gate is missing too. | plan-20 #scope; task-16.6 R2 | ONE audited removal plan: 16.6's audit/prune engine moves there; new `orphan-alias` and `empty-learned` classes behind an ablation gate; later, the alias-map merge writes. 16.1 keeps only the provenance write. |
| C2 | bug-086's repair has two vehicles: a standalone daemon op (bug row, handoff) vs `prune --class orphan-root` (16.6 R5). | bug_registry bug-086; task-16.6 R5 | The first slice of C1's engine. |
| C3 | Defaults that can delete outside an audited path: 16.6 d-c prunes `moved` rows (re-pointable knowledge), and 17.1 reaps orphan vectors nightly. ADR #rule-no-delete names "plan-20 evidence" as a removal path, but plan-20 writes nothing. | task-16.6 #d-c; task-17.1 R2/R6; ADR #rule-no-delete | `moved` → re-point, not delete. 17.1's orphan reap is derived-index cleanup (the entity is already gone; R6 writes a recoverable orphan list), but the user decides whether it runs nightly or as dry-run + audited apply. Fix the ADR wording: merge writes belong to C1's plan. |
| C4 | Three decay formulas (ADR intropretor row step decay; ADR #rule-floor `log(1+lifetime)`; 19.2 R5 14-day half-life + `base*log1p(hits+2*used)`) and two flush designs. | ADR :167, :250; task-19.2 R4/R5 | 19.2's module is the ONE decay/floor library; the ADR references it. |

{#contradictions-body}

## Consolidations {#consolidations}

- **C5 One queue + bounded drain + lock-hold probe harness.**
  - Today the learn queue, the 16.6 marks, the 19.2 usage events and 17.1's per-dataset holds are
    built separately.
  - Four specs (19.2 AC-4, 16.6 AC-4, 17.1 AC-4, and the r9 #s-1 shape) re-derive the same test.
  - Build it once, first.
- **C6 One tick, one stamp store.**
  - 19.4 registers a step on 17.2's tick (17.2 R7). There is no second stamp file and no
    save-state fallback.
  - 19.4 needs a hub-callable compile op that plans AND applies (today only
    `memory_compile_apply` is a daemon op).
- **C7 One recall-event schema** (retrieved vs delivered) for 16.7 R2, 19.2 R3 and 19.5 R2, or the
  counts double.
- **C8 Split plan-16.** 16.7–16.10 (agent context) become their own plan, so their review loop and
  16.1–16.5's r4 NEEDS-REVISION loop do not block each other.
- **C9 One ranking-eval harness:** 16.10's frozen NL set serves 16.10 R3, ADR-0004's sentence
  co-location rerank (needs bug-075) and plan-13's session question. Plan-13 is re-scoped into it or
  marked dormant.
- **C10 Close plan-14** into 16.4 (its re-measure already lives there).
- **C11 Batch the hook deploys.** 19.1 R3, 16.2/16.3 and 16.9 all regenerate hooks; ship them in as
  few `install-hooks --apply --force` windows as possible.
- **C12 Keep plan-18 minimal** (measure + CHECKPOINT) until the helix plan decides whether
  manifests replace A/B slot reconciliation.

{#consolidations-body}

## Execution order {#order}

> **Superseded 2026-10-14** by [[plan-review-2026-10-14#t10-waves]] for every wave; kept as history.

- **Wave 0 (now)**
  - ch-bsd round 10 → CLEAN → merge + deploy the remedy branch.
  - **bug-093 hotfix (added by me).** The deployed daemon wedges on every large-file edit (the
    watch semantic pass's per-row upserts; three watchdog kills today). It is the same hotfix shape
    as bug-085: batch the upserts, yield between files, measure a `cli.py` re-sync.
  - Docs in parallel: plan-16 revision 5 + its spec review; spec reviews of 17 and 19; the C1/C8
    splits; a `plan-of-plans` + handoff refresh.
  - No repo code, waits on the user: the 19.5 R1 threshold probe (scratch project) and 20.1 gold
    labelling.
- **Wave 1**
  - The C5 harness.
  - 17.1 → 17.2.
  - 19.1, 19.2.
  - 16.7 (telemetry, with the C7 schema).
  - The C1/C2 removal engine, with bug-086 its first apply.
- **Wave 2**
  - 19.3, 19.4 (as a registered step), 19.5.
  - 17.3.
  - 16.1 → 16.2 ∥ 16.3 → 16.5.
- **Wave 3**
  - 16.4 (closes 14).
  - 16.8 → 16.9.
  - 16.10, with co-location and bug-075 as candidates.
  - The free-cull classes, behind the ablation gate.
- **Wave 4**
  - 20.2 → 20.3.
  - plan-18 measurement.
  - Draft the ADR-0004 helix plan, reusing 19.2's counters, 17.2's tick and plan-20's merge rule.
- **Wave 5:** build the helix: age tiers, manifests, the alias map + merge writes.

{#order-body}

**Deviations from the user's stated order** (merge → memory → plan-16/context → concepts):
- plan-17's 17.1/17.2 run WITH plan-19, because 19.4 hard-depends on 17.2 and 17.1 closes
  bug-085's growth.
- 16.7 moves to wave 1 as the instrument 19.5 reuses.
- 20.1 and the 19.5 probe start in wave 0, read-only, because both wait on the user's time.
- bug-093 jumps the queue, because it is live.

{#deviations}

## Gaps and stale entries {#gaps}

**No plan yet:**
- the ADR-0004 helix implementation;
- the sentence co-location rerank (+ bug-075);
- the free-cull spec (C1);
- an owner for alias-map merge writes;
- the C5 harness;
- the bug-085/093 op-start log line;
- owners for bug-055, bug-088 (refuse stage) and bug-091.

**Stale:**
- `plan-of-plans`:
  - the plan-16 row ("no specs", "awaiting 3 decisions");
  - rows 11 and 17–20 are missing their columns;
  - the "drafting — no task specs yet" note;
  - `#sequence` stops at 12;
  - plan-15's gate wording;
  - plans 2–4 and 6–10 are still `in-progress` with dirty 10-01 findings.
- `plan-16` header (says revision 3).
- `handoff.md #state` (33 commits, 0.76.0, r6).
- The concept exploration's transition summary (d-1 now decided).

{#gaps-body}
