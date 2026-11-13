---
gmd: "0.1"
id: plan-review-2026-11-13
title: "Plan-of-plans re-evaluation and consolidation, 2026-11-13 (rev 2, provisional until ch-bsd)"
tags: [plan-review, decisions, consolidation, plan-of-plans, contradictions]
metadata:
  node_type: review
  status: drafting
  created: 2026-11-13
  updated: 2026-11-13
---

# Plan-of-plans re-evaluation and consolidation, 2026-11-13 {#root}

The user, 2026-11-13 (session 37b7498f), after merging dev master into the 25.1 branch and pushing:
"given the number of detours, I think we should re-evaluate the POP and consolidate". Then: "there
have to be contradictions". **Rev 2** folds in the five-way contradiction sweep: contra-a..e,
57 findings, reports in `workflow/review-output/pop-2026-11-13/`, brief
`workflow/agents/contra-pop.md`. Lead resolutions (L-rows) are provisional until a ch-bsd round over
this file comes back clean. User decisions are asked by id in [[open-questions]] (session 37b7498f).

rel: amends -> [[plan-review-2026-10-14#t11-folded-waves]]
rel: derives-from -> [[plan-of-plans#goal-2026-11-09]]
rel: derives-from -> [[plan-of-plans#goal-2026-11-09-scope]]
rel: depends-on -> [[open-questions]]
rel: related-to -> [[exploration-handhold-outcome-experiment]]

## What the 2026-11-09 goal said, and what happened {#goal-vs-actual}

The goal [[plan-of-plans#goal-2026-11-09]] set one queue ahead of plan-24: 3.7 → bug-178 →
plan-26 → plan-27 → plan-25 → bug-177 (23.1, with bug-182) → bug-179. The same day it widened to
take in 23.3, 23.5 and bug-185 ([[plan-of-plans#goal-2026-11-09-scope]]).

**Landed (2026-11-09 to 11-13; every sha verified by contra-e):** 3.7 (`91ddbe0`, 0.81.0), bug-178
(`76ec748`, 0.81.1), bug-179 (`aea4098`), 26.0 (`61b3bde`), 26.1 (`9b2c4ac`, then `25af9ca`),
26.2 (`05164ce`, `078c951`), 26.3 (`fdc6359`), 26.6 (`8a867bc`, R3 residual still open) and
26.4 (`0c74872`). 0.82.0 released. {#landed}

**Not started:** 26.5, 26.7, 26.8, 26.9; all of plan-27; 25.2-25.5; 23.1-23.5 except 23.0;
bug-185. 25.1 is GREEN at rev 7 on its branch, unmerged, and its spec is now at rev 8.
{#not-started}

**Work that entered without a queue slot (the detours):** {#detours}

| detour | trigger | size so far |
|---|---|---|
| bug-193/195/197-200 cut-hook fallout | 26.1 follow-up | 5 merges (`25af9ca`, `102524d`, `a0056fc`, `6c2abb2`, `54e4f70`); one live repair held |
| user-level `/save-state` + `/recall-state` | 26.3 | 1 merge, 2 ch-bsd rounds |
| bug-209 / bug-212 / bug-214 fleet hooks | 0.82.0 fleet re-install | bug-212 r1 GREEN, r2 in flight; 3 fleet repos committed, unpushed |
| 21.5 used-signal | plan-21 approval track | spec revs 1 → 3.1, four measurements, 3 ch-bsd rounds; approval open |
| 24.6 revisions r5-r7 | 21.5 addenda | spec only |
| plan-10 revival | 21.5 measurements | revs 1-5 (on its clone branch, not on master), three measurements, Q9-Q13 |
| bug-216 (GMD `rel:` misbinding) | 21.5 m1 review | spec revs 1-4, RED, GREEN over 13 `src/` files in flight; spawned bug-218, bug-219, bug-220 |
| handhold outcome experiment | 21.5 measurements | exploration doc, Q3-Q5 |
| 25.1 revs 7-8 | Q14 (9.5k hook cap) | rev 8 caps every hook command, adds a degrade ladder and a spill page |

Five of the nine sit in one subsystem: what the hooks push into the agent's context, and whether
it gets used. Three more are fallout from shipping plan-26 to the fleet. {#detour-shape}

## Findings {#findings}

- **F1: the POP is not the source of truth.** Rows are stale (contra-e Ce-13 lists 12 status
  drifts; contra-c Cc-9 and contra-d CD-9 find body status lines contradicting frontmatter in
  plans 16, 17, 18, 22 and 23). The working order lived in `handoff.md#open`. {#f1}
- **F2: nine plans carry `status: in-progress`** (2, 3, 6, 7, 8, 9, 10, 15, 23); plans 2-9 are
  ~8.5 weeks old. They are NOT all residual-only. Plans 3 and 9 have met their closure
  conditions. Plans 6, 7, 8 and 15 carry blocking findings or build work behind recorded "may NOT
  flip" gates (Ce-8, Ce-9). {#f2}
- **F3: context delivery is spread across eight plans** (9, 10, 19, 21, 24.6, 25.1-25.3, the
  handhold experiment). Four in-flight tasks already BUILD plan-19 pieces (25.1 → 19.1 + 19.5 R1;
  25.3 → 19.0 R1; 10.3 → 19.6 R8a; 10.6 → 19.6 R5). Plan-19 records none of that (CB-10). {#f3}
- **F4: the cluster's premise is in doubt.** R12 pilot
  ([[measurement-task-21.5-r12-pilot-2026-11-13]]): 7% CAUSED, 19% CAUSED+INFORMED; the
  matcher measures proximity, not use. 48.0% of injected items were already held
  ([[measurement-injection-already-held-2026-11-13]]). The pull-side legs look better than push
  (CB-11). {#f4}
- **F5: the write-lock cluster (T4) is coherent, but it carries three ordering faults.** 23.5
  R9/AC-9 needs the 26.6 R3 residual, which comes after 26.7. bug-185 still pins the concept-first
  resolution that bug-216 removes. Its "plan-26 merged" gate is over-broad (Cc-1, Cc-2, Cc-7). {#f5}
- **F6: grep work is two contradictory plans, not one contract.** 25.4/25.5 build BRE
  translation into the code that 16.5 deletes. Both rest on a live rewrite that has been off
  since 2026-10-15 (CD-1, CD-8). {#f6}
- **F7: graph-integrity work overlaps owners elsewhere.** bug-186 is fixed inside bug-185.
  bug-120 is removed by 16.6. bug-219's purge must go through plan-22's audited path.
  bug-216's `denotes` adds a ranking change that ADR-0004 gates (CD-3, CD-6, CD-7). {#f7}
- **F8: the test instrument costs every round** (bug-215, 170, 168, 155, 127, 130, 190, 091;
  isolation rows 088/101 deferred by the user). {#f8}
- **F9: no WIP limit, and 67 of 217 bug rows are not `fixed`.** Literal count: 60 `open`, 2
  `recurring`, 2 "fix on branch", 1 `remedied`, 1 in progress, 1 suspected. The count is
  fragile: rows bug-183 and bug-209 hold unescaped `|` (Fx-4). {#f9}

## Contradictions found {#contradictions}

- **X1 [K1] 26.1 AC-2 vs bug-216 R2.** The doc walk over hidden directories. Ruled for R2,
  under the user's condition: "as long as the files [in] hidden directories don't pollute the
  graph because of incorrect classification". `red-216` pins three things on every route:
  - no entity, edge or evidence row under a dot-dir;
  - `.claude/PROJECT_PROFILE.md` lands once, as `kind=doc`;
  - a memdir under a `.claude` path still lands its memories as `kind=memory` (the bridge guard
    contra-a raised).

  All are mutation-proven. bug-220 (a doc walk over a memory dir lands `kind=doc` memories) is
  logged with a route-not-refuse fix, per the user: "we should have a way to bridge memories into
  the graph". {#x1}
- **X2 [K2] memories-in-graph vs `feedback_operational_content_not_in_graph`.** That memory
  says save-states and `workflow/` stay OUT. This store has them IN: `mentions:store_lock` has
  211 `workflow/` anchors, 29 memory-dir anchors and 3 memory rows out of 247. → **Q1**. {#x2}
- **X3 [K3] 25.1 is built ahead of its recorded dependency on 26.7 and plan-27** (Ca-1, CB-3,
  CB-4, Ce-4; re-read at source by the lead). Rev 7 is GREEN and queued for 0.83.0. Rev 8 is
  specced on the same branch and is unbuilt. The rev-1 draft claimed that shipping rev 7 first
  costs an extra fleet hook window. That was wrong: 0.83.0 needs a window for bug-212 anyway, so
  both orders cost two. → **Q2** (options restated). {#x3}
- **X4 [K2] the draft's P3 freeze reverses user decision d9bi** ("Plan 19 … LEADS Wave 1 … the
  substrate for helix", `plan-review-2026-10-14.md:388`). It also freezes work the queue builds
  (Ca-2, CB-10, Ce-5). Separately, it freezes the pull-side tasks 21.2/21.4 that the
  measurements favour (CB-11). → **Q3**. {#x4}
- **X5 [K2/K3] the draft reversed the user-dated order "21.5 decision → handhold experiment"**
  (`plan-of-plans.md:68`, exploration `:15`) by folding 21.5 into a post-experiment charter
  (CB-12, Ce-6). Meanwhile the 21.5 spec was never revised after its own pre-registered band
  fired (p_w 0.07 < 0.50; CB-8). → **Q4**. {#x5}
- **X6 [K2/K3] plan-24 D1 vs the queue.** D1 says hook-shaped work (plan-16, 19.5 R1, 19.6
  injection, 21.2-21.4) "retargets to the mod … kept as records, not built". The 2026-11-08
  override put plan-24 last, and 25.1 already builds 19.5 R1 on hooks. No queue line builds
  24.5/24.6, the steps that would release D1's hold (Ce-2, Ce-15, CB-14). → **Q5**. {#x6}
- **X7 [K2] the draft's P2 closes plans past recorded "may NOT flip" gates** (plan-6 r1
  blocking findings, plan-8 r5 #b-2/#b-3, plan-7 dense/fused re-run, plan-15 W1-e clean-suite
  gate). It also leaves the plan-2 #s-2/#m-4 riders, plan-7's deferrals and todo G11 with no
  host (Ce-9, Ce-10, Ce-11). → **Q6**. {#x7}
- **X8 [K1/K6] 25.4/25.5 vs 16.5.** BRE translation is built into legs that 16.5 deletes
  (user decision 2026-10-07). bug-081, bug-167 and bug-174 each have two planned fixes (CD-1).
  → **Q7**. {#x8}

## Lead resolutions (dependency or user-directed spec wins; provisional until ch-bsd) {#lead}

| id | finding(s) | resolution |
|---|---|---|
| L1 | Ca-3, Ce-3, Cc-2 | 26.7 → 26.6 R3 residual move AHEAD of T4; 23.5 R9/AC-9 then registers on the real hold. POP and plan-23 `#merge-order` say "after the 26.6 R3 residual (after 26.7)" |
| L2 | Ce-1, Cc-5, CD-2 | plan-22 runs after 16.6's Wave-1 slice and 17.1 (the order of record, `plan-review-2026-10-14.md:480`). The 16.6 slice moves into T4 after 23.1, then 17.1; only 16.1 → 16.2 ∥ 16.3 → 16.5 → 16.4 stay in T5 |
| L3 | Cc-1, CD-4 | bug-216 wins over bug-185 R2. Before bug-185's RED, a freshness revision on the post-bug-216 tree: R6 precedence (bare id doc-first, anchor concept-first); the "minted earlier" rule never beats a same-named doc or memory; `denotes` (R7) and pending refs (R10) join R1's batched writes; golden regenerated; bug-216 gains an order edge to bug-185 |
| L4 | Cc-7 | bug-185's, 23.2's and POP's "plan-26 merged" gate narrows to "26.1 + 26.2 merged" (satisfied) |
| L5 | CD-5 | bug-216 wins over 16.1: `corpus.is_relevant` delegates to `should_ignore`, and the hidden-dir prune keeps `!path` re-includes. Revised before T5 builds |
| L6 | CD-6 | bug-219 ships only its "count joins a live edge" half (= bug-216 R8). Its delete half becomes census input for plan-22's dangling classes, and 22.1a widens to a dead entity side (7,752 rows) |
| L7 | CD-7 | bug-216's ch-bsd round takes this up. Default: ship R7 (`denotes`) and R9's walker hop; hold R9's PageRank fold until a per-type evaluation (ADR-0004 `:297`). The handhold arm-A baseline is taken without the fold |
| L8 | CD-3, Ce-7, Cc-3, Cc-4, Ca-5 | A bug's track = its owning task's track. T5: 081, 102, 167, 174, 180, 120. T6: 086, 107, 119, 121, 124, 218, 219. T4: 106, 186 (fixed by bug-185 R6), 097, 099, 136, 207. T3: 182 (measurement lane first), 164-166, 181, 100, 103, 104, 196. T2: 206 (single home), 208, 210, 213, 220 |
| L9 | Ca-5, Ca-6 | bug-208 becomes a 26.5 precondition with its own AC (mirroring `#inherit-264-r1`); 26.5 or 26.8 names the restore of bug-202's two anchor sets, with a check |
| L10 | Ca-7 | 26.9 runs in parallel with plan-27 after 26.8 |
| L11 | Ca-4 | ADR-0005 Appendix A's MEMORY-RULES text carries the marker condition before 26.8 AC-8 (the user approves that text at AC-8) |
| L12 | Ca-9 | put to the user at 26.8 AC-8 (same MEMORY-RULES window): forget flow step 5, `rmx memory forget <id>` |
| L13 | Ca-8 | plan-27 refreshes `#survey`/`#facts` at 27.1's start; its Q3 is re-hosted on the marker-found install-hooks + 27.6 report, not plan-24 |
| L14 | Ca-2, CB-10 | plan-19 records realized-by lines: 19.1 + 19.5 R1 by 25.1; 19.0 R1 by 25.3; 19.3 by 26.7; 19.4 by 26.6; 19.6 R8a by 10.3; 19.6 R5-composite by 10.6 |
| L15 | CB-1, CB-2, CB-5 | the 25.1 rev-8 spec owns the "still in play" line (members: held / over budget); it amends R3, R8, R9, AC-9 and AC-14 by name with `rel: amends`; it gains `depends-on 10.3` (compaction marker); 10.2 is re-specced against rev 8 and its R8 parity figures re-derived |
| L16 | CB-6 | 25.3 R7's helix once-per-session resets at 10.3's compaction marker and keeps its state in `stm/<session>.emitted/` |
| L17 | CB-7 | Table A runs on the composite (offline, cheap) before 10.6 R3. The exploration's `#vi-evidence` is revised against the 2026-11-13 numbers |
| L18 | CB-9 | 19.6 Table C counts only R12 explicit uses + `cited_in_answer` until 21.5's matcher is revised |
| L19 | CB-13 | 25.2's ack-only gate is scored against the labelled and R12 explicit uses that sank Q10's gate, before it is built |
| L20 | CB-15 | the handhold exploration folds Q3 fully (a new-session trigger on the paired leg); arm B's push-off switch is specified (`arms.SESSION_ARMS`); the "switch already exists" premise is struck |
| L21 | Cc-6 | 23.4 (read-only, cliquet copy) goes in the measurement lane before plan-17; not retired |
| L22 | Cc-8, CD-9 | 22.4 and the two merge entry points become deferral rows under T6: "no host plan; plan-20 drafting". plan-20 is `drafting` (waiting on the user's 20.1 labels), not dormant |
| L23 | Ce-12 | the plan-10 revival branch merges to master before any queue line cites 10.x; POP row 10 and W3-a are marked superseded by Q11/Q13 |
| L24 | CD-8 | 25.4/25.5's premise ("every agent grep reaches `rmx grep`") is corrected, and so is `PROJECT_PROFILE.md:79` (the rewrite is off while `learn.off` exists) |
| L25 | Ce-13, Ce-14, Cc-9, CD-9, Fx-1..5 | one bookkeeping commit: frontmatter and body status lines, POP rows, todo G2/G3/G5/G6, bug-081/bug-216 fix columns, the escaped `\|` in rows 183/209, plan-13 `drafting`/DORMANT, Q7/Q11 rows marked superseded |

## Revised proposal {#proposal}

### P1: one queue, tracks, POP rewritten {#p1}

The rev-1 shape stands: one numbered queue (the only place order lives), a tracks table, and a
closed/dormant list. Track membership follows L8. The POP rewrite lands after Q2-Q7 are answered,
so it is written once. {#p1-body}

### P2: legacy plans close per their recorded gates (Q6) {#p2}

Plans 3 and 9 close now, as bookkeeping: 3.7 merged `91ddbe0` (AC-G4), and 21.1's summary
records plan-9's riders. Plans 6, 7, 8 and 15 keep their recorded gates unless the user waives
them. Plan-2's riders need a host before plan-2 closes. {#p2-body}

### P3: freeze push refinement only (Q3) {#p3}

Only 19.2, 19.6 phasing/cache + Table C, 21.3 (the PostToolUse push nudge) and the 21.5 build are
frozen until the handhold experiment reports. Everything that in-flight tasks realize (L14)
proceeds, and so do the pull-side 21.2 and 21.4. This narrows d9bi; it does not reverse it, and
it needs the user. {#p3-body}

### P4: plan-24 (Q5) {#p4}

D1's hold is either reaffirmed (and 24.5/24.6 get queued) or superseded by the charter decision.
Either way, plan-24 `#phasing` gains an amends note (Ce-15), and 24.8 R5 gains rows for plan-10
and 25.1-25.3 (CB-14). {#p4-body}

### P5: the detour rule {#p5}

1. **WIP:** at most two tracks building at once, plus one lane for specs or measurements.
2. **A new bug joins its owning task's track** (L8). A standalone spec is only for a
   live-store, data-loss or fleet-breaking hotfix.
3. **A new measurement or exploration names the queued decision it changes.** Otherwise it goes
   to the backlog.
4. **Any insertion into the queue is a user decision with a Q-id**, dated in the queue line.

## Proposed queue (rev 2; items marked by a Q move with its answer) {#queue}

1. **T1 0.83.0:** bug-212 r2 + bug-216 (its ch-bsd takes L7 and the X1 pins; R4 applied with
   the merge); 25.1 rev 7 per **Q2**; then the fleet `install-hooks`, with repos found by hook
   marker.
2. **T2:** 26.5 (+ bug-208 AC, bug-213, bug-220) ∥ T0 suite-trust sweep.
3. **T2:** 26.7 → 26.6 R3 residual (L1).
4. **T4:** bug-185 (freshness rev, L3) → 23.2 → 23.1 (bug-177) → 23.3 ∥ 23.5 → 16.6 Wave-1
   slice → 17.1 (L2).
5. **T3:** 10.3 ∥ 10.5 probe → 25.1 rev 8 (L15) → 10.6 (after L17) → 10.4 → 10.2; 25.2 (after
   L19) → 25.3 (L16); bug-182 measurement.
6. **T3:** 21.5 / handhold experiment, in the order set by **Q4**, then the charter decision; plan-24
   per **Q5**.
7. **T2:** 26.8 → 26.9 ∥ plan-27.
8. **T6:** bug-218; plan-22 with bug-219 as census (L6).
9. **T5:** 16.1 (L5) → 16.2 ∥ 16.3 → 16.5 → 16.4; 25.4/25.5 per **Q7**.
10. **T4 tail:** 23.4 (measurement lane, L21) → 17.2 → 17.4; plan-18.

Measurement lane, alongside: 23.4, the bug-182 per-leg timing, the 10.5 read-back probe, and
L17's Table A on the composite.
{#queue-body}

## Questions {#questions}

Asked in [[open-questions]] under session 37b7498f: Q1 (X2), Q2 (X3), Q3 (X4), Q4 (X5), Q5 (X6),
Q6 (X7), Q7 (X8). {#questions-body}
