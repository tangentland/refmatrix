---
gmd: "0.1"
id: plan-review-2026-11-13
title: "Plan-of-plans re-evaluation and consolidation, 2026-11-13 (DRAFT, provisional until ch-bsd)"
tags: [plan-review, decisions, consolidation, plan-of-plans]
metadata:
  node_type: review
  status: drafting
  created: 2026-11-13
---

# Plan-of-plans re-evaluation and consolidation, 2026-11-13 {#root}

The user, 2026-11-13 (session 37b7498f), after the 25.1 merge and the push: "given the number of
detours, I think we should re-evaluate the POP and consolidate." This file is the lead's DRAFT:
findings, a proposed structure, a proposed queue and the questions it needs answered. Every
decision row is provisional until a ch-bsd round over this file comes back clean.

rel: amends -> [[plan-review-2026-10-14#t11-folded-waves]]
rel: derives-from -> [[plan-of-plans#goal-2026-11-09]]
rel: derives-from -> [[plan-of-plans#goal-2026-11-09-scope]]
rel: depends-on -> [[open-questions]]
rel: related-to -> [[exploration-handhold-outcome-experiment]]

## What the 2026-11-09 goal said, and what happened {#goal-vs-actual}

The goal [[plan-of-plans#goal-2026-11-09]] set one queue ahead of plan-24: 3.7 → bug-178 →
plan-26 → plan-27 → plan-25 → bug-177 (23.1, with bug-182) → bug-179, widened the same day by
23.3, 23.5 and bug-185 ([[plan-of-plans#goal-2026-11-09-scope]]).

**Landed from the queue (2026-11-09 to 11-13):** 3.7 (`91ddbe0`, 0.81.0), bug-178 (`76ec748`,
0.81.1), bug-179 (`aea4098`), 26.0 (`61b3bde`), 26.1 (`9b2c4ac` + follow-up `25af9ca`), 26.2
(`05164ce`, `078c951`), 26.3 (`fdc6359`), 26.6 (`8a867bc`), 26.4 (`0c74872`); 0.82.0 released.
{#landed}

**Not started from the queue:** 26.5, 26.7, 26.8, 26.9; all of plan-27; 25.2-25.5; bug-177 /
23.1; 23.2; 23.3; 23.5; bug-185. 25.1 is in flight but is now at spec rev 8. {#not-started}

**Work that entered without a queue slot (the detours):** {#detours}

| detour | trigger | size so far |
|---|---|---|
| bug-193/195/197-200 cut-hook fallout | 26.1 follow-up | 3 merges, a live repair held |
| user-level `/save-state` + `/recall-state` | 26.3 | 1 merge, 2 ch-bsd rounds |
| bug-209 / bug-212 / bug-214 fleet hooks | 0.82.0 fleet re-install | r1 GREEN, r2 in flight; 3 fleet repos committed, unpushed |
| 21.5 used-signal | plan-21 approval track | spec revs 1 → 3.1, four measurements, 2 ch-bsd rounds; approval still open |
| 24.6 revisions r5-r7 | 21.5 addenda | spec only |
| plan-10 revival | 21.5 measurements | revs 1-5, three measurements, Q9-Q13 |
| bug-216 (GMD `rel:` misbinding) | 21.5 m1 review | spec revs 1-4, RED, GREEN over 13 `src/` files in flight; spawned bug-218, bug-219 |
| handhold outcome experiment | 21.5 measurements | exploration doc, Q3-Q5 |
| 25.1 revs 7-8 | Q14 (9.5k hook cap) | rev 8 now caps EVERY hook command, adds a degrade ladder and a spill page |

Of nine detours, five (21.5, 24.6, plan-10, handhold, 25.1 r7/r8) sit in ONE subsystem: what the
hooks push into the agent's context and whether it is used. Three more (cut-hook, fleet hooks,
user-level commands) are fallout from shipping plan-26 to a fleet. bug-216 is a real correctness
defect found by a measurement. {#detour-shape}

## Findings {#findings}

- **F1 — the POP is not the source of truth any more.** The table's rows are stale against the
  plans' own state (26.1 and 26.4 merged but `pending` in their specs; plan-10's row still says
  "negative result"; 25.1 "not started"), and the current order lives in five stacked override
  paragraphs plus the 2026-10-19 wave list. The working order this week lived only in
  `handoff.md#open`. {#f1}
- **F2 — seven plans are "in-progress" for 4-8 weeks with only residual findings left.** Plans 2,
  3, 6, 7, 8, 9 and 15 carry MEH/SKETCHY remnants that were placed as riders on Wave 1-3 tasks
  that have not started. They are debt rows, not plans, and they inflate the active surface.
  {#f2}
- **F3 — context delivery is spread across eight plans.** plan-9 (cost telemetry), plan-10
  (dedupe), plan-19 (adaptive budget, 19.0-19.6), plan-21 (usage: 21.1-21.5, 21.7), 24.6
  (context and observation), 25.1-25.3 (recall budget, thin-prompt gate, STM admission) and the
  handhold experiment all change or measure the same pipeline. Each edits the others' specs
  (21.5 → 24.6 → plan-10 → 25.1 this week), which is the main detour engine. {#f3}
- **F4 — the measured premise of that cluster is in doubt.** The R12 pilot
  ([[measurement-task-21.5-r12-pilot-2026-11-13]]): 7% CAUSED, 19% CAUSED+INFORMED; about half
  of injected items were already held. Building 19.x and 21.2-21.4 refinements before the
  handhold experiment says whether push earns its place risks building on a premise the next
  measurement removes. {#f4}
- **F5 — the write-lock cluster is coherent but unstarted.** plan-23 (23.1-23.5), bug-185,
  bug-177, bug-182, and the store-maintenance plans 17/18 all bound or schedule the single
  writer. bug-177 is consumer-visible (Stop-hook write errors) and has waited since 2026-11-09.
  {#f5}
- **F6 — grep surface work is split.** plan-16 (shim, learner, validation) and 25.4/25.5 (BRE
  translation, substring metas) plus bugs 081, 086, 102, 106, 107, 167, 174, 180 are one
  contract: `rmx grep` is a faithful drop-in. {#f6}
- **F7 — graph-integrity work is split.** bug-216 (in flight), bug-218, bug-219, bug-186,
  bug-119-121, bug-124, bug-206 and plan-22 (audited removal) all concern whether the stored
  edges match the files. {#f7}
- **F8 — the test instrument costs every round.** bug-215 (clone pytest exits 1), bug-170,
  bug-168, bug-155, bug-127, bug-130, bug-190, bug-091 and the isolation rows bug-088/bug-101
  make "is it green?" a per-round argument in the littlebig clones. {#f8}
- **F9 — no WIP limit.** At the pause: three implementers, two spec revisions and four
  measurements ran at once, and every ch-bsd round over them filed new rows that became tasks.
  66 bug rows are not `fixed`. {#f9}

## Contradictions found {#contradictions}

The user, 2026-11-13: "there have to be contradictions". Sweep dispatched (contra-a..e, brief
`workflow/agents/contra-pop.md`); findings are folded here as they land.

- **X1 [K1] 26.1 AC-2 vs bug-216 R2** (surfaced by `green-216` mid-GREEN). The test
  `tests/test_memory_bridge.py::test_ac2_doc_ingest_keeps_its_own_walk` expects the doc walk
  (`collect_gmd_files`, no `as_memory`) to return files inside `.organise-rollback-1/` and
  `.hidden/`. bug-216 R2 sends every ingest-gmd walk through `should_ignore`, which excludes
  them. Lead ruling: R2 wins, because it is the newer spec and the user directed it. AC-2 only
  meant that the memory-walk rule does not leak into doc ingest. `red-216` amends the test and
  notes the supersession in the bug-216 spec. **The user's condition (2026-11-13):** "as long as
  the files [in] hidden directories don't pollute the graph because of incorrect classification".
  So the amended tests pin three things on every route that reaches the store: no entity, edge or
  evidence row under a dot-dir; the one re-included file, `.claude/PROJECT_PROFILE.md`, lands once
  as `kind=doc` in the project partition; and each assertion is mutation-proven. The related,
  pre-existing hole is logged as bug-220: a doc walk over a memory dir lands memory files as
  `kind=doc`. It goes to T2. {#x1}
- **X2 [K2] "memories into the graph" vs "operational content stays out of the graph".** The
  user, 2026-11-13: "we should have a way to bridge memories into the graph as they are sometimes
  relevant". The memory `feedback_operational_content_not_in_graph` lists "save-states, plan-of-plans,
  task-status" and "a project's `workflow/` dir" as content that must NOT enter the graph. In this
  store the bridge does put them in. Measured on `mentions:store_lock` (live, read path): of 247
  mentioners, 211 are `workflow/` anchors, 29 are memory-dir section anchors and 3 are
  `kind=memory` rows. viascope excludes `workflow/` and refmatrix does not. Which rule holds needs
  a user decision. A third option: memories get IN (the bridge, correctly classified, per bug-220's
  route-not-refuse fix) while save-states and `workflow/` stay OUT. One related observation:
  `kind=memory` rows carry no `path` (only their section anchors do), and bug-216 R8's recount
  class "doc / memory with a path" has to allow for that. {#x2}

## Proposal {#proposal}

### P1 — one queue, six tracks, POP rewritten {#p1}

The POP becomes: (1) a single numbered **Queue** of at most ~12 lines, the only place order
lives; (2) a **Tracks** table, one row per track with its plans, bugs and next step; (3) a
**Closed / dormant** list. The override paragraphs and the folded-wave list move here as history.
`handoff.md#open` points at the queue instead of repeating it.

| track | holds | next step |
|---|---|---|
| **T1 Ship 0.83.0** | 25.1 rev 7, bug-212 r2, bug-216 (in flight) | collect → ch-bsd each → merge → release → fleet `install-hooks` (by hook marker) → bug-216 live steps |
| **T2 Memory organisation** | 26.5 (+ bug-208, bug-213), 26.7, 26.8, 26.9; plan-27; bug-206, bug-210 | 26.5 |
| **T3 Context delivery** | plan-9 remnants, plan-10, plan-19, plan-21 (21.2-21.5, 21.7), 24.6, 25.1 rev 8, 25.2, 25.3, handhold experiment; bugs 100, 103, 104, 164-166, 181, 196 | 25.1 rev 8 → plan-10 names-only (10.6 → 10.4 → 10.2) → handhold experiment → charter decision |
| **T4 Write path** | plan-23 (23.1-23.5), bug-185, bug-177, bug-182, bug-097, bug-099, bug-136, bug-207; then plan-17, plan-18 | bug-185 → 23.2 → 23.1 → 23.3 ∥ 23.5 |
| **T5 Grep surface** | plan-16 + 25.4/25.5 moved in; bugs 081, 086, 102, 106, 107, 167, 174, 180 | after T4's 23.1 (16.6 needs it) |
| **T6 Graph integrity** | bug-218, bug-219, bug-186, bug-119-121, bug-124; plan-22; plan-20 (dormant) | after bug-216 lands |
| **T0 Instrument trust** (sweep, not a track) | bug-215, 170, 168, 155, 127, 130, 190, 091; bug-088/101 stay deferred unless the user lifts it | one short pass, before T4's test-heavy work |

### P2 — close the legacy in-progress plans {#p2}

Plans 2, 3, 6, 7, 8, 9 and 15 move to `completed`; each residual finding becomes a deferral row
naming its host track (or is closed with a reason). plan-10 folds into T3. plan-13 and plan-20
stay dormant; plan-11 stays superseded. Each closure is checked against the plan's latest
ch-bsd ledger, not asserted. {#p2-body}

### P3 — freeze T3 building behind the charter gate {#p3}

Only what is already decided and cheap proceeds in T3: 25.1 rev 8 (the hard 9.5k cap, Q14) and
plan-10's names-only dedupe (Q13). 19.0-19.6, 21.2-21.4, the 21.5 build and 21.7 are frozen until
the handhold experiment reports; the experiment's result decides which of them is built, rewritten
or dropped. 21.5's approval decision becomes part of that charter decision. {#p3-body}

### P4 — plan-24 waits on the charter decision {#p4}

plan-24 (mod transport) retargets the hook-shaped work. If the charter decision moves the product
from push to pull, 24.6 and the hook retargeting change shape. plan-24 stays drafting; the
"everything before plan-24" goal of 2026-11-09 is replaced by the queue. {#p4-body}

### P5 — the detour rule {#p5}

1. **WIP:** at most two tracks building at once, plus one lane for specs or measurements.
2. **New bugs enter a track** by tag; a standalone task spec is only for a live-store, data-loss
   or fleet-breaking hotfix, which takes the queue's head.
3. **A new measurement or exploration names the queued decision it changes**; otherwise it goes
   to the track's backlog.
4. **Any insertion into the queue is a user decision with a Q-id**, dated in the queue line.

## Proposed queue {#queue}

1. T1 — finish 0.83.0 (in flight; nothing new joins it).
2. T0 sweep ∥ T2 26.5 (+ bug-208, bug-213).
3. T4 — bug-185 → 23.2 → 23.1 (bug-177) → 23.3 ∥ 23.5.
4. T3 — 25.1 rev 8 → 10.6 → 10.4 → 10.2 → handhold experiment (arm A after bug-216 is live).
5. T2 — 26.7 → 26.8 → 26.9 → plan-27.
6. T3 charter decision (with 21.5) → re-plan T3 and plan-24.
7. T6 — bug-218, bug-219, bug-186, then plan-22.
8. T5 — plan-16 with 25.4/25.5.
9. T4 tail — plan-17, plan-18.

Rationale for 3 before 4: bug-177 is a consumer-visible error that has waited since 2026-11-09,
and T4 has no open spec questions; T3's next steps are small and can share the WIP slot with
T2. {#queue-why}

## Questions {#questions}

Recorded in [[open-questions]] with ids once this draft clears ch-bsd. {#questions-body}

- Adopt P1 (one queue, six tracks, POP rewritten)?
- Adopt P2 (close plans 2, 3, 6, 7, 8, 9, 15; residuals to deferral rows)?
- Adopt P3 (freeze T3 building behind the handhold experiment)?
- Queue order: T4 before T3 (proposed), or T3 first?
- Adopt P5's WIP limit of two building tracks?
- P4: plan-24 waits on the charter decision?
