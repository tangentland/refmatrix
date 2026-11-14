---
gmd: "0.1"
id: plan-review-2026-11-13
title: "Plan-of-plans re-evaluation and consolidation, 2026-11-13 (rev 6, provisional until ch-bsd r5)"
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
- **F9: no WIP limit, and 68 of 218 bug rows are not `fixed`** (bug-220 included). At rev 2:
  60 `open`, 2 `recurring`, 2 "fix on branch", 1 `remedied`, 1 in progress, 1 suspected,
  plus bug-220. The count is
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
| L7 | CD-7; bsd-pop-r1 S1 | R7 and R9 (including the PageRank fold) ship as specced. The user accepted rev 3 and confirmed it in Q8 ("rev 3-4 stand"); AC-10 asserts the fold. CD-7's ADR-0004 gap is closed by a decision-log line in ADR-0004: `denotes` is a binding repair the user accepted, not an alias merge, and its fold is evaluated per type after deploy (rev-2 L7 held the fold, overriding Q8; withdrawn) |
| L8 | CD-3, Ce-7, Cc-3, Cc-4, Ca-5 | A bug's track = its owning task's track. T1: 164, 181 (25.1 rev 7). T5: 081, 102, 167, 174, 180. T6: 086, 107, 119, 121, 124, 218, 219. T4: 106, 186 (fixed by bug-185 R6), 120 (16.6 R1f; the slice is in T4 per L2), 097, 099, 136, 207. T3: 182 (measurement lane first), 165, 166, 100, 103, 104, 196. T2: 206 (single home), 208, 210, 213, 220. Owner-less rows sit on their track's backlog line in `#queue` (bsd-pop-r1 S10) |
| L9 | Ca-5, Ca-6 | bug-208 becomes a 26.5 precondition with its own AC (mirroring `#inherit-264-r1`). For bug-202's two anchor sets, 26.5 first checks whether the files still exist (bsd-pop-r1 M4: not found on disk). If they do, it restores them with a check; if not, the bug-202 row's restore note is closed with that reason |
| L10 | Ca-7 | 26.9 runs in parallel with plan-27 after 26.8 |
| L11 | Ca-4 | ADR-0005 Appendix A's MEMORY-RULES text carries the marker condition before 26.8 AC-8 (the user approves that text at AC-8) |
| L12 | Ca-9 | put to the user at 26.8 AC-8 (same MEMORY-RULES window): forget flow step 5, `rmx memory forget <id>` |
| L13 | Ca-8 | plan-27 refreshes `#survey`/`#facts` at 27.1's start; its Q3 is re-hosted on the marker-found install-hooks + 27.6 report, not plan-24 |
| L14 | Ca-2, CB-10; bsd-pop-r1 M3 | plan-19 records realized-by lines: 19.1 + 19.5 R1 + 19.4 AC-4's recall leg by 25.1; 19.0 R1 by 25.3; 19.3 by 26.7; 19.4 (the rest) by 26.6; 19.6 R8a by 10.3; 19.6 R5-composite by 10.6 |
| L15 | CB-1, CB-2, CB-5; bsd-pop-r1 S5 | 25.1b (rev 8) owns the "still in play" line, whose members are either held or over budget. It amends R3, R8, R9, AC-9 and AC-14 by name with `rel: amends` and gains `depends-on 10.3` (the compaction marker). Its kind-label clause is restated so that 10.6 adds labels at every tier later, which means 25.1b does NOT depend on 10.6 (CB-5's restatement). 10.2 is re-specced against 25.1b and its R8 parity figures re-derived |
| L16 | CB-6 | 25.3 R7's helix once-per-session resets at 10.3's compaction marker and keeps its state in `stm/<session>.emitted/` |
| L17 | CB-7 | Table A runs on the composite (offline, cheap) before 10.6 R3. The exploration's `#vi-evidence` is revised against the 2026-11-13 numbers |
| L18 | CB-9 | 19.6 Table C counts only R12 explicit uses + `cited_in_answer` until 21.5's matcher is revised |
| L19 | CB-13 | 25.2's ack-only gate is scored against the labelled and R12 explicit uses that sank Q10's gate, before it is built |
| L20 | CB-12, CB-15; bsd-pop-r1 S8 | the handhold exploration folds Q3 fully (a new-session trigger on the paired leg). Arm B's push-off switch is specified (`arms.SESSION_ARMS`), and the "switch already exists" premise is struck. 10.2's live A/B is NESTED in the experiment as a declared factor (arm A splits into `A+dedupe` / `A+full`, 10.2 R7), so 10.2 is built before the experiment starts and its ≥ 14-day A/B is the experiment's run, not a serial step |
| L21 | Cc-6; bsd-pop-r1 S3 | 23.4 (read-only, cliquet copy) runs before 17.1 is built, because its verdict is what reopens 17.1. Not retired |
| L22 | Cc-8, CD-9; bsd-pop-r1 M5 | 22.4 and the two merge entry points become deferral rows under T6: "no host plan; plan-20 drafting" (d9j). plan-20 is `drafting` (waiting on the user's 20.1 labels), not dormant |
| L23 | Ce-12; bsd-pop-r1 M6 | plan-10 rev 5 gets its ch-bsd spec review, then the revival branch merges to master (`#queue` item 4's head) before any 10.x builds. POP row 10 and W3-a are marked superseded by Q13 (names-only) and Q10 |
| L24 | CD-8 | 25.4/25.5's premise ("every agent grep reaches `rmx grep`") is corrected, and so is `PROJECT_PROFILE.md:79` (the rewrite is off while `learn.off` exists) |
| L25 | Ce-13, Ce-14, Cc-9, CD-9, Fx-1..5 | one bookkeeping commit: frontmatter and body status lines, POP rows, todo G2/G3/G5/G6, bug-081/bug-216 fix columns, the escaped `\|` in rows 183/209, plan-13 `drafting`/DORMANT, Q7/Q11 rows marked superseded |
| L26 | bsd-pop-r2 N1 | 19.5's remaining work stays frozen with 19.2. It depends on 19.1-19.3 (task-19.5:17-19), and its R4 baseline serves only the frozen 19.6 work. Only 19.5 R1 proceeds, inside 25.1 |
| L27 | N2 | 10.2 R7's nested outcome counts only R12 explicit uses + `cited_in_answer` (L18's rule), never 21.5's unbuilt legs |
| L28 | N3 | 17.3 (fleet rollout) is queued in item 8, because without its stamp 17.1/17.2/17.4 and plan-18 only ever dry-run (d3d). 26.6's 19.4 R1 tick registration and its AC-2 are hosted by 17.2 |
| L29 | N5 | the per-type evaluation of bug-216's `denotes` PageRank fold is a measurement-lane task after bug-216 is live (pre-registered bands, ADR-0004 `:297`). The ADR-0004 decision-log line (L7) names it |
| L30 | N6 | only 10.3 builds early (25.1b and 25.3 need its marker). 10.5 probe → 10.6 → 10.4 → 10.2 move after T4, ahead of the experiment that nests 10.2, which keeps the user's order (plan-25 → bug-177) with no new insertion |
| L31 | N7, N17 | 16.6 (its `rebuild_index_from_log` fold as "the one replay path") and 23.3 (consumes bug-185 R7) get freshness revisions against the revised bug-185 (L3) |
| L32 | N8 | lead decision, on the user's pattern: the path-less index leg keeps 16.5 R3's floor for BRE metas (the user's 2026-10-07 decision), so 25.4/25.5 build no translator. 25.5 R4's queued re-measure (M ≥ 30 or 2026-12-31) stays outside the goal; a "translate" result there reopens it as a user question |
| L33 | N9 | plan-7's W4-a deferrals stay with the plan-20 evals (order of record). G11 (the universal `--like` selector) is a curation-verb backlog row. Both sit outside the goal |
| L34 | N11 | L19's bands, pre-registered: 25.2's gate is built only if, replayed on the labelled and R12 sets, it drops 0 CAUSED/INFORMED and 0 explicit uses. Otherwise 25.2 is re-specced, and Q10's rule stands |
| L35 | N13 | 21.5 rev 4 includes the R12 re-measure on the revised matcher, with the spec's own bands, before the experiment starts |
| L36 | N14; bsd-pop-r3 R3 | the m1 round at `4b57796` was DIRTY 13 (2B), and its corrections (`36f0251`, `8db3497`, `3ddba55`) landed after the audited range with no confirm row. An r2-lite confirm over `4b57796..` the files' current head runs in the measurement lane before G17 draws its bands (G32). The rev-4 rejection is withdrawn |
| L37 | N15 | bug-220 folds into 26.5 (same memdir walk, same marker gate) as its own requirement and AC |
| L38 | N16 | G27 adds: plan-24 `#decisions`/`#phasing` amends notes (D-Q5); the ADR-0004 decision-log lines (L7, L29) — WRITTEN by spec-t3c (denotes) and spec-t56 (step 3b, bug-218 R4), not the lead (bsd-spec-t3c r2 m7); and per D-Q1, after Q8, a new memory that amends `feedback_operational_content_not_in_graph` |
| L39 | N20 | bug-182's fix is hosted by 25.1b as R15 (scan-prompt wall bound per leg; one budget module, one hook window), with the per-leg timing measurement as its R0 |
| L40 | bsd-pop-r3 R2 | plan-17 order is 17.1 → 17.2 → 17.4 → 17.3 (task-17.3:20: depends on 17.4). 17.3 is user-gated (the orphan release `:57`; backup deletion `:70`, `:177`) |
| L41 | R6, R7 | 19.0's remainder follows 25.3 (its ACs assume R1 is built, task-19.0:423) and includes R1's rebuild remainder (`:925`). bugs 100, 103 and 104 are owned by 19.0 (R5, R2, R1), so they leave the backlog and ride item 4 |
| L42 | R9 | under L32's floor nothing of 25.4/25.5 remains to build. Both close as superseded by 16.5; bug-167 and bug-174 close when 16.5 lands (fixed by its R3 floor). The 25.5 R4 re-measure stays in the backlog as the trigger to reopen |
| L43 | R10; bsd-pop-r4 X2 | L34's else-branch is pre-decided: if the gate fails its bands, 25.2 is not built and bug-165 moves to the T3 backlog. 25.3's STM half has no dependency on 25.2 (task-25.3:21-22) and always builds; only its helix half follows 25.2, and it drops with 25.2 if L43 fires |
| L44 | R11 | R15's band, pre-registered: R0 records per-leg scan-prompt wall time on ≥ 100 hook runs. If the overrun (bug-182: 36 of 101 > 5 s) sits in a leg 25.1b's budget module controls, R15 bounds that leg. If it sits in a lock or daemon wait, R15 is not built and bug-182 moves to the T4 backlog |
| L45 | R4, R12 | user gates are taken from the specs, not only from `#queue`: the horizon restores the catch-all, and `#queue` marks 17.3, 22.5 R4 (the no-owner forget, d9b), the experiment start (randomises live sessions ≥ 14 days in refmatrix and cliquedb), 18.3's per-store announcements and 27.2's viascope2 archive go |
| L46 | spec-t4 early flag (missed by the sweep and five ch-bsd rounds) | bug-216's GREEN (`2fc5554`) adds unlogged GMD-path writes: `clear_rel_evidence` deletes with no facts.log event, and `pending_refs` add/delete/clear are never logged, so a replay diverges from the catalog (duplicate evidence, lost pending rows). Lead decision on the user's pattern (no silent loss on memory paths; decay never loses knowledge): bug-216 gains **R13** before merge. Both are facts.log events that both replay paths apply; RED by `red-216`, GREEN by `green-216`. "Pending refs outside replay" is rejected. bug-185's revision consumes R13 (its batched writes emit the same events) |
| L47 | spec-t2 open items T2-O1..O5 (`workflow/review-output/pop-2026-11-13/spec-t2.md`) | lead rulings on the user's pattern: O1 bug-220's reroute writes through the memdir's OWN store (ADR-0005 `#store-resolution`); O2 bug-202's re-bridge (if the files are found) uses `organise --apply --force-rebridge <id>`; O3 R-208b/R-208c stay in 26.5; O4 the reroute is ungated (store-side, writes no file); O5 the forget step stays a user decision at 26.8 AC-8. spec-t2's 7 contradictions are fixed in its branch (`db2aa9b`) |
| L48 | spec-t0 open items O1..O5 (`a3b1979`) | O1 bug-196 joins T0 as T0.8, because W1-e's clean-suite gate cannot pass while it sits in the backlog; O2 `brief.parse_gmd` is deleted (no production caller, plan-6 Q1 rule); O3 plan-8 deferral rows 43/44 move to T3, held with the frozen 19.2, and T0.6 re-takes the symbolic rows on the same build; O4 master's repo-scope GMD gate, red on the lead's own artifacts, is fixed at `35e1e0d`; O5 a failure no T0 row owns stops T0's closure and goes to the lead. bug-215 = the SkipGate UNPINNED row (one item). bug-222 (`rmx grep -- '-x'`) is logged and owned by 16.5 R2 |
| L49 | spec-t56 open items (`17ed5d7`, `17eaa7a`, `9e5c4b9`) | bug-218 has TWO writers in opposite orientations (`rmx memory link` vs the GMD ingester), so its row's "swap the reader's join" fix was wrong. O-1: the GMD orientation is canonical, `memory_link` changes and the reader follows. O-2: existing rows are re-oriented by a bug-195-shape repair (manifest, logged unlink+link), a USER-GATED live step. O-3: `stale-evidence` rows are removed by a 22.6-style derived cleanup with a manifest, with learned-grep rows excluded. O-4: the 25.5 R4 re-measure trigger moves to 16.4's report. O-5: L6's widening is report-only (vacuum step 3 / 22.6 R5 stay the remover). bug-223 (silent except in the reinforcement boost) is owned by bug-218. bug-216's watcher `base=` defect (a project under a dot-dir or `build/` ancestor syncs nothing) goes to bug-216's next RED |
| L50 | spec-t4 (`913d386`) contradiction | **amends L46.** L46 said bug-216 R13's events apply on "both replay paths", but d9bu (CONFIRMED under d9ck) RETIRED the incremental path (`apply_log_delta` / `_apply_event_body`, no caller in `src/`, deletion owned by 16.6). R13 applies in `rebuild_index_from_log` only; red-216 amends the spec and tests, green-216 adds no `_apply_event_body` branches, and bug-185 / 16.6 drop their per-event legs. The lead's earlier instruction was the error. bug-185 also folds bug-221 (R10: replace semantics for the doc's own `rel:` edges, removing only those that lose all evidence) and flag 7 (R9: one read + one delete per doc; an index only if the clear's median exceeds 50 ms, pre-registered) |
| L51 | spec-t3a open items (`89bddda`, `de74c97`, `841ca70`; report `workflow/review-output/pop-2026-11-13/spec-t3a.md`) | all 10 recommendations adopted. 25.1b: `rmx memory recall --page <token>`; tokens of the form `<session[:8]>-<seq>`; `legs_ms` lands first and deploys ahead (a query.log field, no hook change); R0 closes 19.5's rerank rider (a third plan-2 rider); L44's "sits in" means each run's dominant leg. 21.4: bug-216's ranking code is forbidden to its drafter; G30 uses its own bands; R4 rides the first user-gated install window after it lands. 21.2: dedupe fixture for a doc reached via a denoting concept. Consequence stated: 26.7's 19.3 value fold stays virtual for the whole goal (19.2 is frozen). D-Q6 corrected: plan-2 has THREE riders (#s-2, #m-4, 19.5's rerank rider) |
| L52 | spec-t3b, spec-t4, spec-t56 open items | 10.2 "held" is tier-aware (an item is held only at renderings no richer than the one shown), and held names on the shared line carry a short marker. bug-185 `#open-finish-stop`: the first ruling (stamps in `gmd_finish`) is WITHDRAWN on spec-t4's evidence, because under 23.3's `budget_s` stop a batch larger than one budget would never stamp and would re-ingest forever. Ruling: option 1, the tail runs per document inside `gmd_pass2_document` before that document's stamp (23.3 R4's "stamp in the last step that owes it work"), and `gmd_finish` keeps only the residue for skipped documents. bug-223 raises instead of counting (the boost is an opt-in tuning channel). spec-t56's L49 folds are at `fecda59`; G27 repoints POP `#queue-bug174-remeasure` to 16.4 `#r4-reopen`. 25.1b ⇄ plan-10 converged (`841ca70`, `d363c67`, `5badd4e`) |
| L53 | spec-t3c open items (`5ac42e5`; report in the session scratchpad) | lead decided every option (a), on the user's pattern; the user may overturn any. 21.5: the unit is the first delivery per segment; bands read CAUSED+INFORMED; the other name legs are underpowered strata with no weight; cliquedb is covered by the AC-15 allowance. plan-28 pre-registration: equal thirds; primary B vs C; orientation cost in tool calls; churn window 3; `cited_in_answer` precision labelled blind (50 pairs, Wilson upper bound < 0.50 → explicit uses only); the paired leg uses A+dedupe only; curator stays on in B; a band holds only if its CI excludes 0; κ < 0.6 → report-only; C only in the paired leg. G30: band ON vs OFF, refmatrix only. Transcripts are pruned, so phase M / plan-28 archive the transcripts they use locally (outside the repo and the watched tree, never committed; announced). `arms.py` has one creator per piece (10.2 file, cell table, `draw`; plan-28 `push_on`, period values, start, scorer, deletion). Q8 citations name their ledger session |
| L54 | bsd-spec-t3ab (DIRTY 1B/10S/10M) | B1: 25.1b's renderer prints `·held` (adopts 10.2 h16) and 10.2 supplies the flag, so 10.5's gate can run on 25.1b's renderer. S1: tier shapes are 1 = hook line + full body, 2 = hook line + excerpt, 3 = hook line + pointer, 4 = name on the line (25.1 R3/J5 kept). S2: the still-in-play line is LAST in the payload (user-agreed presentation rule). S3: `legs_ms` gets its own RED→GREEN pair and a ch-bsd lite round before the early deploy; with < 100 runs, R15 is not built. S4: R0 times the recall hook's legs too. S5: R15 budgets = R0 p90 per leg, scaled to fit the timeout minus 0.5 s. S6: v3's re-run is keyed to G22 deploying (Q8 = a). S7: 10.3's PreCompact entry rides an install window (G31). S8: 10.2 creates the `arms.py` deferral row. S9: bytes saved < 30% → no default change; < 40 sessions per arm → one 14-day extension, then inconclusive. S10: the m1 confirm (G32) moves before 25.2's build |
| L55 | bsd-spec-t2 r2 (0B/2S/6M); the joint report's final m4 | bug-220 cross-store dispatch STARTS a detached `ingest_gmd_start` job on B (retries=0) and never waits; the daemon body is the one dispatcher on daemon routes; B absent, busy or refusing → `rerouted_failed`, named, with the remedy (the CLI never opens another store in-process); AC (k) plus a non-vacuous (i). 25.1b pins `Packed`'s tier fields; `overflow` ranks lowest in 10.2's `covers` (never held) |
| L56 | bsd-spec-t3c (1B/9S/11M) | plan-28 pre-registration corrected. Outcome (6) leaves the push reading, which compares A+dedupe vs B on (2)-(4); (6) is reported within the A cells only. Paired-leg clones are cut at the task-start commit, and global-store rows are filtered to before the start. On the paired leg the runner sets the cell explicitly. Phase M excludes the pilot's labelled pairs. `cited_in_answer` keeps 19.6's scope, its tokeniser keeps `/` and `#`, and it counts only at precision ≥ 0.80 with a Wilson lower bound ≥ 0.65 (overrides L53's P-5). G30's M2 uses explicit uses + cited. The session-leg archive runs incrementally. "Pause" = a user-gated end-now. Calibration powers B vs C. A session's cell is fixed at SessionStart. Labellers are blind agents using the pilot's rubric |
| L57 | bsd-spec-t4 (1B/5S/7M) | bug-185's per-document tail passes its own id, its minted names, and every batch id matching a concept name the document wrote, so the links equal HEAD's batch-end call. AC-13's mutant runs outside a transaction. R10 unlinks after step 7 against the document's whole write set. AC-12 is scoped to R13's four ops. gmd_prepare is off the lock and stamp_derive is its own step (the hold formula is re-derived). 16.6 owns the R13 fold rules (rel_evidence_clear is not count-neutral) and 17.4 imports them. 18.3's live slot swaps are user-gated. M6 (bug-216's spec: an order edge to bug-185 and L50's wording) is done by the lead at the bug-216 merge |
| L58 | the writers' own calls in the revision rounds | ACCEPTED as decided, not provisional: 25.1b's spill retention (a session's newest 50 pages; other sessions' spill dirs dropped after 7 days; page ids are write-time based and never reused); R0's ≥ 100 runs pooled across stores with per-store reporting; 26.5's same-store reroute group runs as a detached `ingest_gmd_start` on A itself, counted `rerouted_failed` if A is busy, with tests waiting on the dispatched job ids; spec-t56's B1 op `evidence_stale_drop`; bug-218's repair as `_op_repair_reinforce_orientation` |
| L59 | bsd-spec-t3ab r2 (0B/2S/8M) | 25.1b is the ONE owner of `pack(held=…)`; `held` is the `recall_pack.Held` protocol (`covers(key, full_run_tier) -> bool`), which 10.2's `stm.HeldSet` implements. 10.2 R7 defers its period end to plan-28 28.4. Tier 3 is the hook line (which carries its fetch pointer). #k10 retention gets an AC. AC-21's < 100 branch gets a mutation. Cross-branch anchors are cited at doc level. 21.1 now names plan-28 28.3 R7 as `cited_in_answer`'s owner. 10.2's dedupe read goes through `arms.session_cell`, so the factor cannot flip mid-session (spec-t3c's request, accepted) |
| L60 | G22 rev 2 (spec-t56 `d9296bd`), per Q9 | `workflow/` stays ingested. One gate, `memory_layout.is_operational` + `operational_ids` (location per rev 3, accepted; covering save-state/digest/session prefixes, `workflow/`-path docs, their anchors and the concepts that `denotes` them) replaces the four disagreeing gates. It drops those ids from pagerank adjacency, concept_df, the mentions BM25 stats and co_occurrence; BM25 scoring, embeddings and ingest are untouched. Context and scan rank operational hits last, and only the doc or anchor the query names is exempt. Frozen bands: mean top-k Jaccard ≥ 0.90 with no query < 0.60 (DOESN'T SKEW); name 20/20, anchor 20/20, rel: 10/10, BM25 ≥ 8/10, no drop from BEFORE (USEFUL). The memory SUPERSEDES feedback_operational_content_not_in_graph (a reversed mechanism, per MEMORY-RULES). Depends only on bug-216; 22.6 is not needed. Rev 4 adds rev 3's re-tune-once action bands (skew: mean 0.80-0.90 or any query 0.45-0.60 → extend the filter to BM25 corpus statistics, re-measure once; useful: the exemption also matches a workflow doc's exact title, re-measure once; still failing → report to the user) |
| L61 | bsd-spec-t56 r3 (0B/6S/7M) | G22 rev 5: (S1) `memory_layout` keeps a separate session-card facet; `context` filters ONLY session cards (behind `--include-sessions`, as today at :360/:671/:834) and ranks other operational hits last, with an AC for each behaviour. (S2) the `denotes` clause is dropped: operational status comes from path/kind only. (S3) a per-site table: derivation sites (pagerank, compile, concept_df, co_occurrence) exclude operational ids from their inputs; output sites (ppr, net, enrich, scan, brief, consolidate, context) never remove, only rank last; each row names the call form. (S4) W and N are both built fresh from one commit in a 23.0 sandbox store (memdir bridge pointed at a copy, never live), N ignoring `workflow/`, with the same named derive passes run on both. (S5) Jaccard is defined over raw top-k ids (an operational id in W's top-k is in the union, never the intersection), and `measure.py` is proven to FAIL on a planted-divergence fixture and score 1.0 on an identical pair. (S6) the re-tune is BM25-only and exempts a query whose terms all appear in one workflow doc's title or heading; a name/anchor/rel: miss is a defect reported straight (rev 3's rule restored), with an AC that the re-tune changes one fixture outcome. MEH: M1 a mutation that fails; M2 port, not delete; M3 case-insensitive like `(?i)`; M4 `operational_ids` invalidates on whatever invalidates `concept_df` plus the snapshot swap, named in code; M5 ADR-0003 decision-log line + `depends-on` repointed; M6 project stores only, the global store a deferral row, queue slot after bug-216 (lead places it in the POP rewrite); M7 22.6 AC-10 names the `e_kind` that keeps 1 from its own R-line |
| L62 | bsd-spec-t4 r3 (0B/0S/4M, MEH-only) | T4 meets the approval bar. spec-t4 folds M1 (AC-10's other writer uses `Store.delete_pending_ref` + `link` + `add_evidence`), M2 (the signature in stored sides: linkage, concept-side kind, entity-side kind) and M3 (census restores the `rel:`-verb condition and excludes the document's whole own write set, pass 1 included); the lead sets `approved` on that fold without another round. M4 (bug-216 → bug-185 order edge) is applied by the lead at the bug-216 merge |
| L63 | bsd-spec-t2 r6 (0B/2S/3M) | (Y1) the daemon invocation opens INSIDE the pool-submitted callable (wrap `run` at daemon.py:3376) and drains there in try/finally; `_handle` opens none. (Y2) (p) gates X in its yield window (`_partition_keeping_yield`, between release and re-acquire), Y is a `sync_files` op, and the test asserts Y's reply arrived while X's gate was closed. (Y3) the invariant is never two Stores open at once per root: the drain reuses a Store still open in the invocation, else opens and closes its own; the guard counts concurrent opens. (Y4) `enqueue` raises on a missing invocation on every call, groups or not; the ingest_path fallback's `except Exception` re-raises that error type. (Y5) an inner `invocation()` owns its own queue and drains at its own exit; the outer drains only what it enqueued outside inner scopes; the detached-job and ingest_path_start runner share one wrap, named once |
| L64 | bsd-spec-t2 r7 (0B/1S/2M) | (Z1) the every-call `NoInvocationError` stands; its blast radius is met by per-call-site `with memory_reroute.invocation():` wraps only, every affected test/eval/script file listed in 26.5's Files as "wrap only, no assertion change"; AC-220 (f) reads "the bug-216 family re-runs green with only the wrap added"; no autouse or conftest fixture opens an invocation, and a guard test fails if one does (it would disarm (n)/(r)). Eval harnesses wrap at their entry, so the benchmark path stays the production path. (Z2) (p)'s Y fixture maps to store B. (Z3) on an error reply the drain result rides on the raised exception and `_handle`'s except copies it into the `{"ok": False}` reply; (q)'s daemon leg asserts it |
| L65 | spec-t56 G22 rev 5 open item | `brief` stays an output site as written: a `contradicted` / `orphan-concept` finding with an operational endpoint is listed last, not skipped-and-counted. The process-citation noise stays filtered by `brief._WORKFLOW_NODE_RE`, which G22 does not touch. The ADR-0003 `depends-on` repoint lands in R5's commit (the superseding memory must exist first) |
| L66 | bsd-spec-t2 r8 (0B/0S/2M, MEH-only) | T2 meets the approval bar; spec-t2 folds M1-M2 and the lead sets `approved` on that fold with no further round. (M1) `run_watcher`'s flush opens an invocation unconditionally on the debounce thread (the table drops "if long-lived" and the root-drain claim); `Debouncer._safe_fire` re-raises `NoInvocationError` (a missing boundary is a code defect and fails loudly), with an AC. (M2) (t) becomes a fixture-less test asserting `memory_reroute.current() is None` (autouse fixtures apply to it) plus a `pytester` must-fail case with a planted generator conftest fixture; the AST leg is dropped |
| L67 | bsd-spec-t56 r4 (1B/1S/5M); AMENDS L61 S3 | L61 S3 contradicted itself: every walker (ppr, net, enrich, scan's PPR expansion, the context walk) reads the pagerank adjacency, which excludes operational ids. Ruling (a): walkers inherit the derivation exclusion. Their rows read "unreachable: excluded by the adjacency; the site's own check is deleted"; AC-5 asserts no walk output holds an operational id (mutation: `build_adjacency(exclude_operational=False)`). "Rank last, never remove" holds for the NAME-MATCHED legs only (`content_rank` hit lists, scan's matched-concept injection, the recall pack, `rmx context`'s hit list); an operational entity never seeds PPR, and an AC shows scan-prompt naming `p` still injects `p.md` through the match leg. The writer confirms from code that USEFUL's `rel:` channel (`rmx neighbors`) reads links, not the adjacency, and names it; if it reads the adjacency that is a defect to report. ADR-0003 `#d-2026-11-14-dq1` and the memory text match. (S1) each build's memdir copy lives under `$SANDBOX_HOME/.claude/projects/<slug of that build's unpacked root>/memory`; `build.py` prints each bridge run's resolved store root, asserts it is W's or N's, and exits non-zero before any write on a mis-slugged copy (AC). (M1) the disk adjacency cache key gains `memory_layout.OPERATIONAL_RULES_VERSION`; AC: an old-key file is rebuilt. (M2) bug-218's Files names the bug-185 AC-15 edit (shipped-list assertion becomes `[]`) as an amendment. (M3) AC-7's BEFORE fixture: BEFORE divergent at 1/3, AFTER identical at 1.0, the printed verdict named. (M4) closed by L65. (M5) 22.2:1187 names where a count-neutral op is declared under 16.6 r15 |
| L68 | bsd-251 on 25.1 at `f656f78` (1B/2S/5M) | (b-1) d8 stands for 25.1 (it ships in 0.83.0 with the empty-stdout degrade); bug-224's cause is CONFIRMED as that degrade path, so 25.1b gains a requirement + AC: a hook-mode skip emits one skip line in the payload through `hook_budget.emit`, inside the budget, naming the cause; bug-224's row points at it and T0.3 keeps only the load reproduction. spec-t3a amends 25.1b; a confirm-lite ch-bsd round follows. (s-1) a `--max-bytes` CLI test pins an exactly-N-byte pack (the three one-byte guards). (s-2) `verbs.pack_recall` never drops a `load_hooks` failure: with no warnings list it raises or the caller passes one, and the busy fall-through (cli.py:12803) passes one. (m-1) j4 pinned. (m-2) `by_producer` pinned for all 8 channels. (m-3) stale comment fixed. (m-4) `EVENT_SPLIT` and `MIN_USEFUL_RECALL_BYTES` are read where 25.1's spec says, or deleted if no requirement names them; the focus_input cap stays with 25.1b AC-26. (m-5) recall-state turns any exception into one `Error:` line with a non-zero exit. RED first (s-2, m-5 fail at HEAD; s-1, m-1, m-2 proven by mutation), then GREEN, then a bsd-251 confirm round |
| L69 | bsd-spec-t56 r5 (0B/1S/2M) | bug-218, 22.2 and 22.6 meet the bar. G22: (S1) R4 pins the order: `build.py` resolves each memdir copy with the bridge's own resolver (`_root_from_projects_slug`), asserts the result is W's or N's `.refmatrix/` root, and only then runs the bridge; an AC plants a copy whose slug decodes to a different existing store root, `build.py` exits non-zero, and that root's catalog and `facts.log` are byte-identical afterwards; mutation "assert after the bridge run". (M1) the `rel:` query is `rmx neighbors <S> --linkage <verb> --limit <cardinality>`, and the draw samples only edges whose source is an anchored `{#…}` concept, recording the verb. (M2) converge: the adjacency caches key on the pagerank pass's code identity (the module hash derive staleness already uses, covering `memory_layout.py`); the hand-bumped constant is dropped; AC-6 shows an edit to `is_operational`'s rules rebuilds the cache. A confirm-lite round follows |
| L70 | bsd-spec-t3ab on 25.1b R18 (1B/1S/2M) | (B1) SessionStart/PreCompact never skip on a missing daemon (they fall through to the replica/reader and print a pack): AC-28 tests those modes with a busy daemon AND no reader, and adds a guard leg that no-daemon SessionStart/PreCompact still print their pack (mutation "absent treated as skip"). (S1) the cause comes from the exception TYPE: `VerbDeadlineError(VerbBusyError)` is raised by `_left` and the replica deadline → "budget spent" (stays `skipped_budget` through subclass matching); plain `VerbBusyError` → "daemon busy"; a daemon op `TimeoutError` → "daemon timeout" ("worker timeout" is dropped: it never reaches the degrade path); `VerbAbsentError` and a refused connect → "daemon absent"; a reset or other transport error → "transport error". Every leg's asserted cause is deterministic (no timing race); the writer names each setup, and a held sandbox daemon is preferred to a lowered `--timeout` where it removes the race. (m1) `_degrade_or_raise` joins R12's writer list and AC-26's structural set. (m2) a unit leg on the line builder kills the over-300 B mutation |
| L71 | bsd-spec-t56 r6 (0B/1S/1M) | (S1) R4 names the bridge invocation: a subprocess with `cwd` = that build's memdir copy and `REFMATRIX_ROOT` UNSET, so `cli._root()` resolves through the same `_root_from_projects_slug` the guard asserts (the production SessionStart path); W and N are registered so discovery finds them, and the spec says how. AC-13 unsets `REFMATRIX_ROOT` for the bridge subprocess as a stated override of 23.0's autouse value, its positive leg asserts W GAINED the copy's memory rows, and the mutation "assert after the bridge" then fails as specified. (M1) AC-6's on-disk leg asserts only that the stale file is rebuilt and rewritten under a new key (mutation: the old file's mtime and contents unchanged); no new mock. A confirm-lite follows |
| L72 | bsd-212r2 on bug-212 at `67f55cb` (1B/1S/4M, NO-GO); AMENDS the lead's r2 placement of the refusal in `cli._store_rw()` | (b-1) the tracked-catalog refusal moves to ONE store-level check called by both `cli._store_rw()` and `verbs.local_write`; `mcp._t_memory_add`, `handoff._promote_digest`, `verbs.change_subject` and `cli.init` route through `local_write`; an AST test fails when `src/` adds a read-write `Store(` outside an allowlist; RED tests first for `rmx add concept`, MCP `rmx_memory_add` and `rmx init` on a tracked store (no daemon, both layouts). (m-1) neutral tail on the read refusal, the read test forbids "the write", docstring fixed in r4. (m-2) INTEGRATION.md states the real reader order (with an `active` marker only the inactive slot is a fallback); no code change. (m-3) `timeout=10` on both git calls, a timeout raises `TrackedCatalogCheckError`; the ~30-100 ms cost is one sentence in INTEGRATION.md. (m-4) a `rev-parse` failure with a `.git` at or above the store dir raises `TrackedCatalogCheckError` (only "no .git anywhere up" is `[]`); a `GIT_DIR=/nonexistent` test pins the env strip. (s-1) the r4 audit covers `f7c0d39..HEAD`, including the r1 remedy GREEN. bug-212 does not block 25.1 or bug-216 from merging first |
| L73 | spec-t3a's 25.1b rev-round-4 choice | ACCEPTED: "a held sandbox daemon" is one paused with SIGSTOP; the leg first asserts the daemon's ping timeout is below the hook budget, so busy cannot read as budget spent |
| L74 | bsd-spec-t56 r7 confirm-lite (0B/0S/1M, MEH-only) | T56 meets the approval bar. spec-t56 folds M1 (AC-6's on-disk leg runs in the same process with the instance cache dropped by a new `Store` on the same root while `_DERIVE_SRC_DIR` still points at the copy; mutation unchanged) and the lead sets `approved` on that fold with no further round |
| L75 | bsd-spec-t3ab 25.1b R18 r2 (0B/1S/1M) | (S1) `verbs.memory_recall`'s own `_left` (verbs.py:1386-1394) raises `VerbDeadlineError`; the verb's re-wrap under its deadline (verbs.py:1522-1526) keeps the subclass (raises `VerbDeadlineError` when the caught error is one); the Files row names verbs.py, not recall.py; AC-28 gains a leg where the deadline expires inside the verb, mutation "verb `_left` raises plain `VerbBusyError`". (m1) leg (d) asserts the partition-probe ping plus `require_daemon`'s ping together fit inside the budget. A confirm-lite r3 follows |
| L76 | bsd-spec-t3ab 25.1b R18 r3 (0B/0S/1M, MEH-only) | 25.1b's R18 amendment meets the approval bar. spec-t3a folds m1 (AC-28 (c2) passes `partition=` so the deadline goes through the verb's re-wrap, as the live CLI does) and the lead records the amendment's approval on that fold with no further round |
| L77 | the user, 2026-11-14: "when 0.83 is ready, go ahead and deploy to all projects" | USER AUTHORIZATION for 0.83.0's fleet step (queue item 1's user gate): once 0.83.0 is released and deployed here (hub + daemons on the new version), run `install-hooks --apply --force` in every fleet repo whose `.git/hooks/post-commit` carries the marker `refmatrix: refresh`, checked over a KNOWN candidate list, never a tree walk: the hub registry and launchd-supervised roots (`discovery.discover_roots`), the repos named in `project_fleet_hooks_found_by_marker_not_hub` (incl. `~/github/atollogy/bdep/atlftpd` and `bdep/thiquet`), the direct children of `~/claude_tools`, and this repo. Resolved list (user-reviewed 2026-11-14): refmatrix, bdep/cliquedb, bdep/viascope, bdep/orderly, bdep/cliquet, bdep/atldb, bdep/atlftpd, bdep/thiquet; EXCLUDED by the user: `~/enduris/thiquet` (its launchd daemon uninstalled the same day, plist backed up to `~/.refmatrix/backups/enduris-thiquet-daemon-2026-11-14/`, store left on disk) and bdep/prep_prolific. All 8 get the full git + Claude hook layer (Q12 b for atlftpd and bdep/thiquet). bdep/atlftpd gained a launchd daemon at the user's request the same day (`com.refmatrix.daemon.atlftpd-45572437f9b9`, hub-supervised, 0.82.0, never derive-stamped). The user, 2026-11-14: "don't scan ~/github its too big and includes the other directories listed", then "and drop enduris as well" (Q10, interpretation assumed until confirmed); the user confirmed `--force` explicitly the same day, with hooks backed up first to `~/.refmatrix/backups/hooks-0.83.0/`, a per-repo diff of foreign hooks kept (0 lost), `.git/hooks` verified by reading them (bug-209), and `install-hooks --check` clean in each. Scope: hook re-install + daemon restarts only; it does not authorize plan-27's memdir migration, plan-28's start or any other user-gated step |
| L78 | the user, 2026-11-14: "The plan-27 memory-folder migration and the start of the plan-28 experiment can proceed when you feel its time" | DELEGATED to the orchestrator. plan-27 runs when its own preconditions hold (plan-26 merged, released and deployed with 26.8 green; 27.1's survey refreshed), with every migration step backed up as plan-27 specifies. plan-28 starts (28.5) when its own preconditions hold, as plan-28's Depends-on states them: bug-216 live; 10.2 built (`arms.py` and the nested dedupe); 21.5 phase M reported (D-Q4); the m1 r2-lite confirm CLEAN or MEH-only (G32); and the bands frozen in 28.4 before the start. The orchestrator tells the user at each start, names the backups and the stop condition, and does not change a spec's preconditions to start sooner. G18 and other user gates are unchanged |
| L79 | the user, 2026-11-14: "the plan 28 arms should only be 3 days" | plan-28's session leg runs 3 real (calendar) days from its start, confirmed by the user the same day ("3 real days will be sufficent", Q11 a), replacing "at least 14 days and at least 40 sessions per cell per store, whichever is later". The arms stay concurrent (one cell drawn per session at SessionStart), so 3 days is the whole period, not 3 days per arm in sequence (Q11 a, confirmed). A pause does not extend it: the period ends 3 calendar days after the start whatever was paused, and the end rule's "active days" wording is replaced. The n-floor no longer extends the period: any cell or outcome below its pre-registered minimum n (incl. 10.2 R7's) reports "underpowered, no verdict" instead of pass/fail, and the report states the n reached per cell. The paired re-entry leg is unchanged (it is not time-boxed by the period). spec-t3c amends plan-28, 28.5 and the exploration doc; any 10.2 text that assumes the longer period is amended by its owner; a confirm-lite ch-bsd round follows |
| L80 | bsd-spec-t3c L79 confirm-lite (0B/1S/4M) | (S1) plan-28 follows L78: 28.5's title, R1 and AC-1, the L45 row and #approval read "the orchestrator starts the experiment when plan-28's Depends-on holds and tells the user first (L78)"; AC-1 checks that the tell precedes the start commit; pause, the end and G18 stay user-gated. (m1) 28.5 R5: the report waits for the paired series, which may outrun the 72 hours. (m2) AC-10 gains a primary-reading minimum-n case. (m3) the `#rev-l79` table headers render, and "Q11 assumed" reads "Q11 answered (a)". (m4) spec-t3b's (`ca4b9a7`). A confirm-lite follows |
| L81 | bsd-216 on bug-216 at `df092ac` (1B/2S/4M, NO-GO) | (B1) the segment and spec rules judge a path against the PROJECT ROOT the store belongs to, never the ingest target: `base` defaults to that project root, so `rmx ingest <memdir>`, MCP `rmx_ingest` on a memdir and `rmx ingest <proj>/.claude` store no doc rows, as at `758bca1`; RED tests for all three; routing a memdir target into the memory bridge stays bug-220's (26.5), not this branch. (S1) R4 at merge = the ignore-file edit THEN `rmx ingest .` on the live store so old-code citers re-process; AC-6 covers the store built by old code; the R10 docstring is corrected. (S2) `pending_refs` joins replica_merge's three table lists and merge_partition (rows repointed to the surviving partition; rows whose source entity is gone are dropped and counted), with tests. (M1) tests that kill the three surviving mutations. (M2) `build_context`'s mention chain does not cross `denotes`, matching PageRank, until G30 decides the fold; `neighbors` keeps listing raw links. (M3) the watcher's delete path purges a built-in-included GMD doc (decide before unlink), with a test. (M4) doc drift fixed. RED first, then GREEN, then a bsd-216 r2 over the remedy |
| L82 | bsd-spec-t3c L80 confirm-lite (MEH-only); red-212r2's r4 flags; red-225's census | (plan-28) spec-t3c folds m1 (plan-28:222 and 28.5:158 drop the start "go") and m2 (the start commit writes `end = start + 72 h`; R4 becomes the check plus the user step; the scorer drops and counts sessions whose SessionStart is at or after `end`); the lead records the L79/L80 approval on that fold; Q14 (verdict source) may amend plan-28 again. (bug-212) `cli.partition_drop` is the fifth bypass and routes through the one store-level check like the other four; `rmx focus change-subject` turns the refusal into one `Error:` line; `sync.changed_since`'s `git diff` gets `timeout=10` raising loudly; `rmx save-state` prints a promote refusal on stderr with a non-zero exit — red-212r2 adds RED tests for the last two before GREEN. (bug-225) the fix reads `refs/remotes/origin/HEAD` first (each candidate verified with `rev-parse --verify`), then the list; the `/recall-state` template's trunk wording names `refs/remotes/origin/HEAD` |
| L83 | the user, 2026-11-14, Q14: "drop the live part" (measured: refmatrix ~0.5 sessions/day, cliquedb ~0.1/day) | plan-28 has ONE leg, the paired re-entry leg (fresh agents resuming real handoffs on isolated littlebig clones). Every reading (the primary, the push reading and 10.2's nested dedupe reading, A+dedupe vs A+full) comes from it, each against its own pre-registered minimum n of paired tasks per cell, and the series is not time-boxed. REMOVED: the live session leg, live randomisation of the user's sessions at SessionStart, the 3-day period (L79's period text), the `end`/`after_end` rules (L82 m2) and every live-leg outcome; the user's own sessions are never assigned to an arm. KEPT: L78/L80's start rule, applied to the paired series (the orchestrator starts it when Depends-on holds and tells the user first); pause and G18 stay user-gated; the series ends when its frozen n is reached or the user pauses it; below a minimum n a reading is "underpowered, no verdict". 10.2: the paired runner sets each run's cell explicitly through `arms` (no SessionStart draw); 10.2's nested reading is read from the paired series. spec-t3c amends plan-28 and spec-t3b amends plan-10/10.2, each followed by a confirm-lite |

## Revised proposal {#proposal}

### P1: one queue, tracks, POP rewritten {#p1}

One numbered queue (`#queue`) is the only place order lives, followed by the tracks table below and
a closed/dormant list. Track membership follows L8. The POP rewrite lands once, after this review
clears ch-bsd. {#p1-body}

| track | holds |
|---|---|
| **T0 Instrument trust** (sweep) | bug-215, 170, 168, 155, 127, 130, 190, 091, the SkipGate UNPINNED row; plan gates W2-a (plan-6 r1), W2-b (plan-8 r5), W1-e (plan-15 clean suite), W2-c (plan-7 dense/fused re-run) per D-Q6; bug-088/101 stay deferred by the user |
| **T1 Ship 0.83.0** | bug-212 r2, bug-216, 25.1 rev 7 (bug-164, bug-181) |
| **T2 Memory organisation** | 26.5 (+ bug-208, 213, 220), 26.7, 26.6 R3, 26.8, 26.9, plan-27; D-Q1 belongs to T6; backlog 206, 210 |
| **T3 Context delivery** | plan-10 (rev 5), 25.1b (+ bug-182 R15 per L44), 25.2, 25.3, 19.0 rest (+ 100, 103, 104), 21.2, 21.4, 21.5 rev 4, handhold experiment; frozen per D-Q3 + L26: 19.2, 19.5 rest, 19.6 phasing/cache + Table C, 21.3, the 21.5 build; backlog 196 |
| **T4 Write path** | bug-185 (+ 186), 23.1-23.5 (+ 099, 106, 136, 177), 16.6 Wave-1 slice (+ 120), plan-17, plan-18; backlog 097, 207 |
| **T5 Grep surface** | 16.1-16.5, 16.4; 25.4/25.5 superseded (L42); bugs 081, 102, 167, 174 (closed by 16.5); backlog 180 |
| **T6 Graph integrity** | bug-218, bug-219 (count half = bug-216 R8; census to plan-22), D-Q1 work per Q8 (held), plan-22 (22.1 after 16.1), 22.4 as deferral rows; bugs 086, 107; backlog 119, 121, 124 |

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

## Queue (rev 4: user order; bsd-pop-r2 folded) {#queue}

The user's recorded order of 2026-11-08 (b) and 2026-11-09 holds: plan-26 → plan-27 → plan-25 →
bug-177 (23.1) / 23.3 / 23.5 / bug-185. D-Q2 waives that order for 25.1 rev 7 only. A line placed
by a user decision carries its id, and a line placed by an L-row carries that row's id.
{#queue-lead}

1. **T1 0.83.0:** bug-212 r3 + bug-216 (R7/R9 as specced, L7; its ch-bsd round takes the X1
   pins; R4 applied with the merge) + 25.1 rev 7 (D-Q2). **User-gated:** the fleet
   `install-hooks` window (repos found by hook marker) and bug-216's live re-ingest.
2. **T2:** 26.5 (+ bug-208 AC, bug-213, bug-220 per L37) ∥ T0 sweep.
3. **T2:** 26.7 (+ the AC that 25.1's lookup survives, D-Q2) → 26.6 R3 residual (L1) → 26.8
   (**user-gated:** the `--apply` go-ahead, and AC-8's MEMORY-RULES apply with L11/L12) → 26.9
   (**user-gated:** per-document approval) ∥ plan-27 (L10; **user-gated:** 27.2a, 27.2's viascope2 archive go, cliquedb at its
   session boundary).
4. **T3, plan-25:** plan-10 rev 5 ch-bsd spec review → revival branch merged (L23) → 10.3 →
   25.1b (L15; + bug-182 fix as R15 under L44's band, L39; + plan-2's riders, D-Q6; **user-gated:** install
   window) ∥ 25.2 (after L34's scoring; else-branch L43) → 25.3 (after 10.3; L16); 19.0 R0, R2-R7 + R1's rebuild remainder, after 25.3's STM half (d9bi, D-Q3; L41, L43; bugs 100, 103, 104).
5. **T4:** bug-185 (freshness rev L3; gate per L4) → 23.2 → 23.1 (bug-177) → 23.3 (fresh vs
   bug-185, L31) ∥ 23.5 (R9/AC-9 on the real hold, L1).
6. **T3:** 10.5 probe → 10.6 (after L17's Table A) → 10.4 (**user-gated:** install window) →
   10.2 (built; outcome per L27) (L30); pull side 21.2 → 21.4 (D-Q3).
7. **T3:** m1 confirm (L36) → 21.5 rev 4 with its R12 re-measure (D-Q4, L35) → handhold
   experiment (**user-gated:** the start), arm A × {dedupe, full} nested (L20). It runs ≥ 14 days in the background while items 8-11 build.
   **Goal stop:** the charter decision on its result; the T3 re-plan and the plan-24 re-plan
   (D-Q5) follow it.
8. **T4:** 23.4 (L21) → 16.6 Wave-1 slice (fresh vs bug-185, L31; L2) → 17.1 → 17.2 (+ 26.6's
   19.4 R1 tick, L28) → 17.4 → 17.3 (L40; **user-gated:** orphan release, backup deletion).
9. **T6:** bug-218; 22.1a (widened, L6) → 22.2 (after the 16.6 slice, 17.1, 23.1, 23.2) → D-Q1's
   live purge, if Q8 makes it one (**user-gated**; N10) → 22.5 (**user-gated:** R4's no-owner forget,
   d9b) ∥ 22.6 → 22.3 (**user-gated:** the count confirmation).
10. **T5:** 16.1 (L5) → 16.2 ∥ 16.3 (**user-gated:** install window) → 16.5 → 16.4; then 22.1
    (needs 16.1). 25.4/25.5 close as superseded by 16.5 (L42).
11. **T4 tail:** plan-18 (18.2, 18.3; **user-gated:** 18.3's per-store announcements).

**Measurement lane:** the m1 confirm (L36, L54: before item 4's 25.2 build); 23.4; bug-182 per-leg timing (25.1b R15's R0); the 10.5 read-back probe;
L17's Table A; L34's 25.2 scoring; L29's `denotes` fold evaluation (after bug-216 is live).
**Install windows** are batched where they fall together (C11).

**Backlog (outside the goal; it ends listing them):** T2 206, 210; T3 165 + 166's helix half only if L43 fires (196 moved to T0, L48); T4 097,
207; T5 180; T6 119, 121, 124; plan-7 W4-a deferrals with the plan-20 evals; G11 `--like`
selector (L33); 25.5 R4 re-measure (L42). {#queue-body}

## User decisions, 2026-11-13 {#decisions}

The user: "q1-a, q2-ship it, q-3-7 your recommendations". D-Q1 to D-Q7 are final (D-Q1 confirmed by Q8 = a). They supersede the proposal text above wherever it differs. {#decisions-quote}

- **D-Q1 (X2), FINAL per Q8 = a as amended by Q9 (user, 2026-11-13):** `workflow/` STAYS in the project partition, "as long as it is useful and doesn't skew whats returned". It is excluded from co-mention / concept-weight derivation and ranked below code/docs by default unless the query names a workflow doc or anchor; a frozen query set pins both conditions. Save-states and digests stay IN the store and in memory recall, excluded from co-mention. There is no ingest exclusion and no purge. Earlier text, kept as history: memories go INTO the graph, correctly classified (bug-220 route-not-refuse).
  Save-states and `workflow/` stay OUT of the concept graph fleet-wide. The lead's reading, stated
  to the user: OUT means excluded from co-mention / concept-weight derivation, the pollution
  `feedback_operational_content_not_in_graph` names. It does not mean excluded from ingest:
  `workflow/` is a corpus root (`PROJECT_PROFILE.md#corpus`), so its docs stay addressable by name,
  anchor and `rel:`. Option a's text named viascope's rule, which excludes at INGEST, so this reading is put back to the user as Q8 (restated twice for honest costs) and G22 is held until then. A T6 task stub specs whichever Q8 picks. Live purges go through plan-22's audited path, and
  every live step is announced and backed up. {#d-q1}
- **D-Q2 (X3):** 25.1 rev 7 ships in 0.83.0.
  - The 26.7 / plan-27 order is waived on the record: plan-25 `#ordering`, the 25.1 spec
    `:22-24`/`:34`, and POP row 25.
  - 26.7 gains an AC that 25.1's curated-hook lookup survives the regroup.
  - Rev 8 (R12-R14, AC-16-18) becomes task **25.1b**, on its own branch after 10.3. Its spec
    text leaves the 25.1 branch before the merge.
  - 25.1b also hosts plan-2's #s-2/#m-4 riders (D-Q6). {#d-q2}
- **D-Q3 (X4):** P3 as revised. Frozen until the handhold experiment reports: 19.2, the
  19.6 phasing/cache work plus Table C, 21.3, and the 21.5 build; L26 adds 19.5's remainder
  (it depends on the frozen 19.2). d9bi is narrowed, not reversed.
  {#d-q3}
- **D-Q4 (X5):** the user's order stands: 21.5 decision → handhold experiment. 21.5 rev 4
  folds the pilot's seven matcher changes and drops or gates `bash_name`. The 21.5 decision is
  "no build until the experiment reports". {#d-q4}
- **D-Q5 (X6):** plan-24 D1 is superseded. Verb-side logic builds on the hook transport now,
  and plan-24 is re-planned after the charter decision. plan-24 gains `rel: supersedes` /
  amends notes on `#decisions` and `#phasing`, and 24.8 R5 gains rows for plan-10 and
  25.1-25.3. {#d-q5}
- **D-Q6 (X7):** plans 3 and 9 close now. Plans 6, 7, 8 and 15 keep their gates (W2-a, W2-c,
  W2-b, W1-e), which are scheduled in the T0 sweep or the backlog. Plan-2 closes when its riders
  land in 25.1b. Plan-7's deferrals and todo G11 are re-owned. {#d-q6}
- **D-Q7 (X8):** 16.5 wins on the named-path and stdin legs. 25.4/25.5 shrink to the
  path-less index leg, where translate vs floor is decided. bug-167 ships as an interim fix only
  if 0.83.0 needs it, with a "deleted by 16.5" note. {#d-q7}

## Spec completeness for the goal {#spec-gaps}

The user, 2026-11-13: "we will turn this consolidated plan into a goal. so need to make sure the
plans are complete". A goal runs unattended, so every item it reaches needs an `approved`,
current task spec (CLAUDE.md `#plans-pre-written`). Status of each queue item: **ok** = an
approved spec exists and needs no change; **rev** = the spec exists but must fold a decision or
L-row first; **new** = no spec yet; **review** = written but not through ch-bsd. {#spec-gaps-lead}

| G | queue | item | state | what is needed |
|---|---|---|---|---|
| G1 | 1 | bug-212 r2 | in build | `red-212r2` round (K6/K8, K5, tldr fake, read-path wording), then GREEN wording, then ch-bsd |
| G2 | 1 | bug-216 | in build | `red-216` addenda 1-2, GREEN, ch-bsd (takes L7); spec row bug-216 refreshed (L25) |
| G3 | 1 | 25.1 rev 7 | rev | waiver into the 25.1 spec, plan-25 `#ordering`, POP row 25 (D-Q2); rev-8 text moved off the branch; then ch-bsd over the rev-7 GREEN |
| G4 | 2 | 26.5 | rev | bug-208 precondition AC; bug-202 restore checked for existence first (L9); bug-220 folded in as its own requirement + AC (L37) |
| G5 | 2 | T0 suite-trust sweep | **new** | task spec: bug-215, 170, 168, 155, 127, 130, 190, 091 + the SkipGate UNPINNED row; plan-gate remedies W2-a (plan-6 r1), W2-b (plan-8 r5), W2-c (plan-7 dense/fused re-run), W1-e (plan-15 clean suite) as named sub-tasks (D-Q6) |
| G6 | 3 | 26.7 | rev | AC: 25.1's curated-hook lookup survives the regroup (D-Q2) |
| G7 | 3 | 26.6 R3 residual | ok | spec in 26.6 `#r3-residual` |
| G8 | 5 | bug-185 | rev | freshness revision against post-bug-216 HEAD (L3); gate narrowed (L4) |
| G9 | 5 | 23.2, 23.1, 23.3, 23.5 | rev | body status lines (Cc-9); `#merge-order` per L1; 23.3 freshness vs revised bug-185 (L31) |
| G10 | 8 | 16.6 Wave-1 slice, 17.1 | rev | 16.6 freshness vs revised bug-185 (L31); 17.1 ok; moved by L2 |
| G11 | 4 | 10.3, 10.5 probe, 10.6, 10.4, 10.2 | review | plan-10 rev 5 ch-bsd spec review + branch merge (L23); 10.3 early (L30); 10.2 re-spec vs 25.1b (L15) with L27's outcome; L17 Table A before 10.6 |
| G12 | 4 | 25.1b | **new** | task spec from rev 8's R12-R14/AC-16-18 + L15 amends + `depends-on 10.3` + R15 bug-182 wall bound under L44's band (L39) + plan-2 #s-2/#m-4 riders (D-Q6) |
| G13 | 4 | 25.2, 25.3 | rev | 25.2: L34 scoring with L43's else-branch; 25.3: R7 reset on 10.3's marker (L16); its STM half is independent of 25.2 and its helix half follows 25.2 (L43, from task-25.3:21-22) |
| G15 | 2 | bug-220 | rev | folded into 26.5 as its own requirement + AC (L37) |
| G16 | 7 | 21.5 rev 4 | rev | fold the pilot's seven matcher changes; R12 re-measure with the spec's bands (L35); decision row "no build until the experiment reports" (D-Q4) |
| G17 | 7 | handhold outcome experiment | **new** | plan + task specs from the exploration (arms, outcomes, bands, the arm-B switch, Q3 fully folded per L20, 10.2's nested arm) |
| G18 | 7 | charter decision, T3 re-plan, plan-24 re-plan | — | a USER gate: the goal stops here; cannot be pre-specced |
| G19 | 3 | 26.8, 26.9, plan-27 | rev | 26.8: ADR-0005 Appendix A marker condition (L11), forget step for the user at AC-8 (L12), counts re-read; plan-27: survey refresh + Q3 re-host (L13) |
| G20 | 9 | bug-218 | **new** | task spec (reinforcement reads edges reversed; currently "suspected") |
| G21 | 9 | bug-219 count half + plan-22 | rev | bug-219 = bug-216 R8 (no new spec); 22.1a widened to a dead entity side (L6); plan-22 body status (CD-9); 22.4 deferral rows (L22) |
| G22 | 9 | D-Q1 (Q8 a + Q9) | **new** | spec: `workflow/` stays in the project partition. (1) A derive-time filter excludes `workflow/`, save-states and digests from co-mention / concept-weight derivation. (2) Default `rmx context` and the push hooks rank `workflow/` hits below code/docs unless the query names a workflow doc/anchor. (3) Pre-registered acceptance: a frozen code/doc query set's top-k is unchanged with vs without `workflow/` within a band (DOESN'T SKEW), and a frozen workflow-targeted set finds its docs by name/anchor/`rel:`/BM25 (USEFUL). No ingest exclusion, no purge. Memory amending `feedback_operational_content_not_in_graph` |
| G23 | 10 | 16.1-16.5, 16.4 | rev | 16.1 vs bug-216 (L5); plan-16 body status (CD-9) |
| G24 | 10 | 25.4/25.5 | close | 25.4/25.5 close as superseded by 16.5 (L42); premise note (L24) in the closing line; plan-25's task table, fixed list and `#approval-order` amended by name; cliquedb told on the bus (bug-167 closed by 16.5) when 16.5 ships |
| G25 | 8, 11 | 23.4, 17.2, 17.4, plan-18 | rev | plan-17/18 body status lines (Cc-9); 18.2/18.3 PROVISIONAL marks cleared against the CONFIRMED rows |
| G26 | backlog | bug-206, bug-210, plan-7 deferrals + G11 | backlog | explicit backlog rows with owners (Ca-5, D-Q6) |
| G27 | — | bookkeeping | rev | L14 realized-by lines, L25 status sweep, POP rewrite (P1), plan-24 amends notes, ADR-0004 decision-log line (L7/L29), D-Q1 memory amendment after Q8 (L38) |
| G28 | 4, 6 | 19.0 R0/R2-R7, 21.2, 21.4 | rev | approved plans; each spec records what 25.1/25.3/26.6/26.7 already realize (L14) and drops plan-24 D1's hold (D-Q5); 21.2/21.4 re-read against bug-216's resolver; 19.5 rest frozen (L26) |
| G29 | 8 | 17.3 fleet rollout; 26.6's 19.4 R1 tick via 17.2 | rev | 17.3 approved; order 17.4 → 17.3 (L40), user-gated; 26.6 AC-2's tick registration named in 17.2 (L28) |
| G30 | lane | `denotes` fold per-type evaluation | **new** | measurement task with pre-registered bands (L29) |
| G31 | 1, 4, 6, 10 | install windows (0.83.0, 25.1b + 10.3's PreCompact entry, 10.4 + 21.4 R4's briefing, 16.3) | — | user-gated; batched where they fall together (C11) |
| G32 | lane, before 4's 25.2 (L54) | m1 r2-lite confirm over `4b57796..` the four measurement files' current head (incl. `36f0251`, `8db3497`, `3ddba55`) | **new** | ch-bsd confirm of the folded 21.5 measurement corrections before G17 draws bands (L36) |

**Proposed goal horizon:** queue items 1-11 plus the T0 sweep, in `#queue` order, with the
measurement lane alongside. The goal stops for the user at item 7's charter decision (G18), at every step `#queue` marks
**user-gated**, and at every user step a spec names, whether `#queue` marks it or not (L45). The backlog is outside the goal.

**Preconditions for launching the goal** (bsd-pop-r4 W2, W3):
1. **Q8 is answered.** Option b changes what items 1-3 build: 25.1 rev 7's packed save-states,
   26.5's re-bridge, and 26.8/plan-27's fleet rollout.
2. **Every spec the goal reaches is `approved`.** That covers the new ones (G5, G12, G17 as a
   whole plan, G20, G30, G32) and every `rev` row. The precedent of record is d9co: a CLEAN or
   MEH-only ch-bsd round over the spec, then `approved` set by the orchestrator on the user's
   pattern, with the decision row written. Only G18 and the user-gated steps stay with the user.

**Delegated user gates (2026-11-14, L77/L78):** the 0.83.0 fleet deploy with `install-hooks --apply
--force` (L77), plan-27's memory-folder migration and plan-28's experiment start (L78) no longer stop
the goal; the orchestrator runs each when its spec's preconditions hold and tells the user at the
start. G18's charter decision and every other user-gated step still stop the goal.
{#goal-horizon}

## Questions {#questions}

Asked in [[open-questions]] under session 37b7498f: Q1 (X2), Q2 (X3), Q3 (X4), Q4 (X5), Q5 (X6),
Q6 (X7), Q7 (X8). {#questions-body}
