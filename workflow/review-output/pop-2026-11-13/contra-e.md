## contra-e: cross-cutting governance   (files read: ~32, plus the frontmatter of ~70 task specs and `git log --merges master`)

Repo state when I read it: master = origin/main = `0d2a270`. Everything was read-only; this file is the only write.

### Ce-1 [K3] Queue item 7 (plan-22) is gated on queue item 8 (plan-16's 16.6 slice)
- side A: `workflow/plan-review-2026-11-13.md:152-153` "7. T6 — bug-218, bug-219, bug-186, then plan-22. 8. T5 — plan-16 with 25.4/25.5."
- side B: `workflow/plans/plan-22-audited-removal-and-repair-tasks/task-22.1a-provenance-free-classes.md:20` "Depends on: 23.0 (test sandbox), 16.6 Wave-1 slice (sidecar + backfill)". The POP agrees at `workflow/plan-of-plans.md:45` (Depends on "16.6, 23").
- why it matters: plan-22's first task cannot start until 16.6 lands, so item 7 stalls behind item 8.
- proposed resolution: put the 16.6 Wave-1 slice into T6, or ahead of item 7. This was already the order in `plan-review-2026-10-14.md:480` ("16.6 slice → 22.1a → 22.2").

### Ce-2 [K2/K3] Plan-24 D1 holds the work the draft queues or unfreezes, and nothing in the queue builds what releases the hold
- side A: `workflow/plans/plan-24-mod-transport.md:63` "D1 | The hook-shaped work (plan-16's build, 19.5 R1, 19.6's injection design, 21.2-21.4) retargets to the mod instead of being built on hooks". `:91-92` "re-specified once 24.5 and 24.6 define the mod's events … their current hook-based specs are kept as records, not built." Same in `plan-review-2026-10-14.md:541-545` (#t13-mod-gate).
- side B: `plan-review-2026-11-13.md:154` queues "8. T5 — plan-16 with 25.4/25.5". `:125-127` says 19.0-19.6 and 21.2-21.4 stay frozen "until the handhold experiment reports; the experiment's result decides which of them is built, rewritten or dropped". `:132` "plan-24 stays drafting".
- also: POP rows `plan-of-plans.md:39` (16 "APPROVED … 16.1-16.6"), `:42` (19 "19.0-19.6 approval-ready") and `:44` (21 "21.2-21.4 approval-ready") show no D1 hold.
- why it matters: after the charter decision those items are still blocked behind 24.5/24.6, and no queue line builds 24.5/24.6. T5 (16.1-16.4) and the post-charter T3 rebuild cannot be reached as written.
- proposed resolution: user decision. Either reaffirm D1 and queue 24.5/24.6 ahead of T5 and the T3 rebuild, or record that the charter decision supersedes D1 and add `rel: supersedes` to plan-24 #decisions. Either way, mark the hold in POP rows 16, 19 and 21.

### Ce-3 [K3] 23.5 (queue item 3) depends on 26.7 (queue item 5)
- side A: `plan-review-2026-11-13.md:148` "3. T4 — bug-185 → 23.2 → 23.1 (bug-177) → 23.3 ∥ 23.5." and `:151` "5. T2 — 26.7 → 26.8 → 26.9 → plan-27."
- side B: `workflow/deferral_registry.md:54` "task 26.7 merged; built as [[task-26.6-compile-subject-hygiene#r3-residual]], 26.6 completes then; 23.5 R9/AC-9 depends on it". Also `workflow/plans/plan-23-bounded-write-harness-tasks/task-23.5-read-path-and-holder-bounds.md:643-644` "AC-9 is written and registered after 26.6 merges … so K counts the apply WITH 26.6's hygiene". POP `:46`: "with 23.5 R9 after 26.6".
- why it matters: 23.5 R9's write bound K would be measured before the compile residual (19.4 R3 MEMORY.md regen) lands, and would need re-measuring afterwards.
- proposed resolution: split 23.5 R9/AC-9 out to run after 26.7, or move 26.7 ahead of item 3.

### Ce-4 [K3] 25.1 is built and merging first, ahead of its recorded dependencies 26.7 and plan-27
- side A: `workflow/plans/plan-25-cliquedb-field-report.md:134` "3.7 ──► plan-26 ──► plan-27 ──► 25.1 ──► 25.2 ──► 25.3 ──► (plan-24)". `:379-381` "the build order stays [[#ordering]] (3.7, plan-26, plan-27, then 25.1-25.5, before plan-24), and every task still records RED at HEAD after its dependencies merge". `workflow/plans/plan-25-cliquedb-field-report-tasks/task-25.1-recall-hook-byte-budget.md:22-24` "plan-26 merged (… its 26.7 regroups `MEMORY.md`, which R3's curated-hook lookup reads)", and `:34` `rel: depends-on -> [[task-26.7-memory-index-by-subject]]`.
- side B: `plan-review-2026-11-13.md:107` puts T1 ("25.1 rev 7") at queue position 1 (`:146`), and `:151` puts 26.7 and plan-27 at position 5. `handoff.md:49` "25.1: GREEN `16ace00`; rev 7 … GREEN in flight".
- I found no recorded decision relaxing this, in `workflow/open-questions.md`, the 25.1 spec, `handoff.md` or `workflow/past_handoffs/019-0830-pipeline-paused_2026-11-11.md`.
- why it matters: R3's curated-hook lookup was built against a MEMORY.md layout that 26.7 will change. The cliquedb after-check assumes plan-27 migrated cliquedb's dir first (`plan-25…md:141`).
- proposed resolution: user decision. Record the relaxation in plan-25 #ordering (with a re-check of R3 after 26.7), or hold the 25.1 merge.

### Ce-5 [K2] The draft drops 25.2/25.3 (bug-165, bug-166) from the queue, and P3's freeze cuts through work plan-25 builds
- side A: `plan-of-plans.md:54` (user override 2026-11-08) "(2) bug-164 (recall hook overflow), bug-165 (bare-ack prompt noise), bug-166 (STM junk topics + stale helix line), bug-167 … (3) only then plan-24". `:56` "(4) plan-25 cliquedb bugs 164-167; (5) plan-24". `:58` goal item "(5) plan-25".
- side B: `plan-review-2026-11-13.md:109` lists 25.2 and 25.3 under T3, but no line of the queue (`:146-154`) schedules them. `:125` freezes "19.0-19.6", yet `task-25.1-recall-hook-byte-budget.md:26-27` says "Builds: [[task-19.1-pack-recall-under-budget]] R1-R8 …; runs [[task-19.5-measure-delivery]] R1 (the probe) as R0", and `plan-25-cliquedb-field-report-tasks/task-25.3-stm-ref-admission-and-helix-repeat.md:24` says "Builds: [[task-19.0-stm-cluster-hygiene]] R1".
- why it matters: two consumer-visible cliquedb bugs the user ordered ahead of plan-24 disappear from the queue. The "freeze 19.x" rule is also contradicted by items the queue does build.
- proposed resolution: queue 25.2 and 25.3 explicitly, or ask the user (Q-id). Reword P3 to "19.x except 19.1 R1-R8, 19.5 R1 and 19.0 R1, which plan-25 builds".

### Ce-6 [K2/K3] The draft reverses the recorded order of the 21.5 decision and the handhold experiment
- side A: `plan-of-plans.md:68` (user, 2026-11-13) "the handhold outcome experiment … runs after the user's decision on task 21.5". `docs/architecture/explorations/handhold-outcome-experiment.md:15` "Runs after the user's decision on task 21.5; nothing is built yet." `:144` "After the user's decision on 21.5 (ch-bsd over the four 21.5 measurements first)". `handoff.md:60` "… → 26.5 → 21.5 approval decision → handhold outcome experiment".
- side B: `plan-review-2026-11-13.md:127` "21.5's approval decision becomes part of that charter decision". The queue runs the experiment at item 4 (`:149`) and holds "6. T3 charter decision (with 21.5)" (`:152`).
- proposed resolution: this changes a user-dated order, so it needs its own question in `#questions`, which currently lacks one. Otherwise keep the order 21.5 → experiment.

### Ce-7 [K6] P1's track table assigns four bugs to the wrong owner
- side A: `plan-review-2026-11-13.md:111` T5 holds "bugs 081, 086, 102, 106, 107, 167, 174, 180". F6 `:83-85` repeats this. `:112` and `:152` put bug-186 in T6 at queue item 7.
- side B:
  - `workflow/bug_registry.md:159` (bug-106): "Spec owner: plan-23 (23.1: evidence write insert-if-absent, or window-scoped replay); existing duplicates are plan-22's to audit". `task-23.1-queue-and-drain.md:1003` "5. Learn's evidence write is insert-if-absent (nb23-2, bug-106 …)". That makes it T4, plus T6 for the audit.
  - `workflow/bug_registry.md:160` (bug-107): "… 22.6 R4 keeps them on any edit". That is plan-22, T6.
  - bug-086 is plan-22's `workflow/plans/plan-22-audited-removal-and-repair-tasks/task-22.3-bug-086-global-repair.md:19` "Depends on: 22.1a, 22.2, 22.5 …". That is T6.
  - `workflow/bug_registry.md:237` (bug-186): "… RED/GREEN in [[task-bug185-bulk-gmd-ingest#ac-8]]". It is fixed by bug-185 at queue item 3 (T4).
- why it matters: T5 would claim three bugs that T4 and T6 tasks already fix (double build), and bug-186 is listed for item 7 although item 3 fixes it.
- proposed resolution: move 086 and 107 to T6, 106 to T4 (plus T6 for the audit), and 186 to T4 under bug-185.

### Ce-8 [K4] The closure conditions for plan-3 and plan-9 are already met; they are not "riders on unstarted tasks"
- side A: `plan-review-2026-11-13.md:65-67` "Plans 2, 3, 6, 7, 8, 9 and 15 carry MEH/SKETCHY remnants that were placed as riders on Wave 1-3 tasks that have not started." `:109` T3 holds "plan-9 remnants".
- side B, plan-3: `workflow/plans/plan-3-verbs-parity-tasks/task-3.7-verb-it-backlog.md:448` "AC-G4. Plan-3 closes when this task is `completed`." 3.7 was merged in `91ddbe0` (`plan-of-plans.md:60` "task 3.7 merged `91ddbe0` (ch-bsd r7 GO), released + deployed 0.81.0"), yet `task-3.7…md:8` still says `status: in-progress`, and so does plan-3 frontmatter.
- side B, plan-9: `plan-review-2026-10-14.md:493-494` "plan-9 r5 #m-11 … and #s-5 … ride 21.1's close-out. Closes plan-2 and plan-9 when their hosts land." `workflow/implementation_summaries/task-21.1-context-usage-telemetry.md:58` records "plan-9 r5 #m-11 | … now prints the interpreter's one BrokenPipe line" and `:59` "plan-9 r5 #s-5 | The Q2 proxy-overhead table is recorded in [[plan-9-context-cost-telemetry#q2-measured]]". `plan-of-plans.md:32` still says "r5 #m-11 and #s-5 ride 21.1's close-out = W1-c".
- proposed resolution: plan-3 (with 3.7) and plan-9 flip to `completed` now, as bookkeeping, after the ledger check. They need no deferral rows. Drop "plan-9 remnants" from T3. The open plan-3-adjacent rows bug-188 and bug-189 are already in the bug registry.

### Ce-9 [K2] P2 would flip plans 6, 7, 8 and 15 past recorded "may NOT flip" gates
- side A: `plan-review-2026-11-13.md:117-118` "Plans 2, 3, 6, 7, 8, 9 and 15 move to `completed`; each residual finding becomes a deferral row naming its host track". `:65` says "only residual findings left".
- side B:
  - `plan-of-plans.md:29` (plan-6) "ch-bsd r1 DIRTY at e0b7df6, may NOT flip; remedy #b-1, #b-2, #s-1, #s-3, #m-1..#m-5". These are BLOCKING findings, not MEH/SKETCHY.
  - `:31` (plan-8) "ch-bsd r5 may NOT flip; remedy W2-b". `plan-review-2026-10-14.md:509-511` "r5 #b-2 (`corroborated` call site unpinned), #b-3 (`brief.parse_gmd` no production caller)".
  - `:517-518` (plan-7) W2-c "task 7.4's dense and fused rows (bug-030 fixed 2026-09-16, never re-run)". That is build work, not a residual.
  - `:499-501` (plan-15) W1-e "a clean full suite on the committed master tree … returns plan-15 to `completed`; its r13 #s-1 … and #m-1/#m-2 are fixed in the same pass."
  - W2-a, W2-c and W1-e are standalone items, not riders on 16-23 tasks.
- why it matters: these are user-folded closure conditions from 2026-10-19 ("fold the remaining 1-15 items into the waves", `plan-review-2026-10-14.md:468`). Flipping would close plans with open blocking audit findings and an unmet clean-suite gate. The draft's own F8 says the suite is not yet trustworthy.
- proposed resolution: user decision, per plan. At minimum the P2 question (`:165`) must name the blocking findings and the W1-e gate, not call them "residual".

### Ce-10 [K6] Plan-2's r9 #s-2/#m-4 riders lose their host
- side A: `plan-of-plans.md:25` "#s-3 rides 23.5, #s-2/#m-4 ride 19.1". `workflow/plans/plan-19-adaptive-memory-budget-tasks/task-19.1-pack-recall-under-budget.md:270` "## Folded riders: plan-2 r9 #s-2 and #m-4 (2026-10-19)".
- side B: `plan-25-cliquedb-field-report.md:217-218` "No plan-19 completion beyond 19.1 and 19.0 R1. 19.0 R0, R2-R7, the 19.1 folded riders and 19.2-19.6 stay in plan-19." So 25.1 builds 19.1 without them, P3 (`plan-review-2026-11-13.md:125`) freezes 19.x, and P2 (`:117`) closes plan-2.
- proposed resolution: move the two riders into 25.1 rev 8 (same recall-budget code), or give them a deferral row owned by T3. Do not close plan-2 with them unhosted.

### Ce-11 [K6] Plan-7's deferrals and todo G11 lose their host
- side A: `plan-review-2026-10-14.md:529-530` "W4-a plan-7 deferrals: Layer B, `longmemeval_m`, CLI candidate prefilter, settled-store latency re-measure — scheduled with the plan-20 evals". `:533` "plan-20 needs approval before Wave 4".
- side B: `plan-review-2026-11-13.md:112` "plan-20 (dormant)" and `:119` "plan-13 and plan-20 stay dormant". POP `:43` has plan-20 as `drafting`, not dormant. P2 closes plan-7.
- affected rows: `workflow/deferral_registry.md:40`, `:41`, `:42` and `:46` (Owner "plan 7"), and `docs/architecture/todo.md:36` G11, owner "plan 7 (to write)" (the user's 2026-09-15 request for a universal `--like` selector).
- proposed resolution: re-own these rows in the P2 pass, or keep plan-20 at `drafting` with W4-a attached.

### Ce-12 [K4] Plan-10's queued tasks do not exist on master, and its POP fold is stale
- side A: `plan-review-2026-11-13.md:149` "4. T3 — 25.1 rev 8 → 10.6 → 10.4 → 10.2 → handhold experiment". `:109` T3 next step "plan-10 names-only (10.6 → 10.4 → 10.2)".
- side B:
  - `workflow/plans/plan-10-injection-dedup-tasks/task-10.2-plan-10-injection-dedup.md:8` "status: cancelled (10.1 did not clear)".
  - Only 10.1-10.3 exist under `plan-10-injection-dedup-tasks/` on master, and `git` cannot resolve `c04c9b9` (rev 5, cited at `handoff.md:31`) in this repo.
  - `plan-of-plans.md:33` "re-measure after 19.6 = W3-a, plan-10 closes into 19.6" and `plan-review-2026-10-14.md:524` "Plan-10 closes into 19.6" conflict with `workflow/open-questions.md:43` (Q11) "19.6 block diff not used for these payloads" and `:41` (Q13) "names-only (design 3) now".
- proposed resolution: merge the plan-10 revival branch before any queue line cites it. Mark W3-a and POP row 10 superseded by Q11/Q13.

### Ce-13 [K4] Status drift that the draft's F1 misses
These all quote frontmatter or POP against `git log --merges master`:
- `workflow/plans/task-bug178-bulk-write-helper.md:8`, `task-bug179-lint-ingest-anchor-parity.md:8` and `task-bug195-cut-hook-repair.md:8` say `status: approved`, but they were merged in `76ec748`, `aea4098` and `102524d`.
- `task-3.7-verb-it-backlog.md:8` says `status: in-progress`, but it was merged in `91ddbe0` (see Ce-8).
- plan-25 and plan-26 frontmatter say `status: approved`, with 26.0-26.4 and 26.6 merged and 25.1 GREEN. By POP `:109` ("in-progress — implementation underway") they should be `in-progress`.
- plan-21 frontmatter says `status: approved`, but POP `:44` says "in-progress".
- POP `:44` says "its AC-6 frozen fixture BLOCKED on the user's cut", against POP `:62` "`ac6-fixture` merged `69ecb21`" and `deferral_registry.md:50` "The fixture is in. AC-6 is now RED on a product defect, not BLOCKED."
- POP `:47` says "partial (1) … 24.0 baseline specified, 24.1-24.8 next", against `plan-24-mod-transport.md:73-83`, where all ten tasks (24.0-24.8 + 24.2a) say "spec written" (merged `9eaf00b`).
- POP `:42` says "execution of 19.0 AC-6f waits on 23.0 merge", though 23.0 merged `d4bf001` (0.79.1).
- proposed resolution: fold all of these into the P1 rewrite.

### Ce-14 [K4] todo.md rows are stale against plan-3 and plan-4 reality
- side A: `docs/architecture/todo.md:27` (G2) "plan-4 stays `in-progress` on the supervision findings listed under G3, owned by W1-a". `:28` (G3) lists r4 #s-2, #s-3, #m-5, #m-6 as "Open … All owned by W1-a". `:31` (G6) "The round-8 remedy (0e3002f, merged 273cc16) answers them and is NOT yet audited. The r8 audit and task 3.4 … are W1-b".
- side B: `plan-of-plans.md:27` "plan-4 … completed (W1-a: task 4.5 r4 remedy + task 4.6 r5 remedy …; released in 0.80.0)". `:26` "ch-bsd r12 at b18d7e8 MEH-only". `todo.md:34` itself says G9 "Done 2026-10-19 (closed as bookkeeping by task 4.5 R6)". Merge `e494311` "plan-4 tasks 4.5 + 4.6 (W1-a), plan-4 completed".
- proposed resolution: refresh G2, G3, G5 and G6 in the same bookkeeping pass (G5 follows Ce-10's outcome).

### Ce-15 [K2] plan-24 #phase-now was never amended for the 2026-11-08 override
- side A: `workflow/plans/plan-24-mod-transport.md:87-88` "24.0 and 24.1 start now, in parallel with Wave 1's engine work: 24.0 needs a week of pre-mod data". Same in `plan-review-2026-10-14.md:544-545` "24.0 and 24.1 start in Wave 1 alongside it".
- side B: `plan-of-plans.md:54` "(3) only then plan-24 (spec r7 → approval → 24.0/24.1)". `:58` "finish every item ahead of plan-24". `plan-review-2026-11-13.md:132` "plan-24 stays drafting".
- proposed resolution: add an amends note to plan-24 #phasing whichever way P4 lands.

### Fact-check of the draft (wrong claims)

#### Fx-1 [K4] "after the 25.1 merge"
- side A: `plan-review-2026-11-13.md:14` "after the 25.1 merge and the push".
- side B: `git log --merges master` has no 25.1 merge, and `handoff.md:60` still has "→ merge 25.1 → bug-212 → bug-216 → release 0.83.0" ahead. The draft also contradicts itself at `:37` ("25.1 is in flight") and `:107` (T1 holds 25.1 rev 7). The push is real: origin/main = master = `0d2a270`.

#### Fx-2 Detour-table counts
- side A: `:43` "bug-193/195/197-200 cut-hook fallout | 26.1 follow-up | 3 merges". `:46` "21.5 used-signal | … 2 ch-bsd rounds".
- side B: there were 4 merges: `102524d` (bug-195), `a0056fc` (bug-197/198), `6c2abb2` (bug-199/200 r1) and `54e4f70` (bug-199/200 r2), plus `25af9ca` (26.1 follow-up, bug-193). For 21.5, `workflow/bullshit/INDEX.md:259`, `:261` and `:262` show 3 rounds (spec r1 `15e8f64`, spec r2 `540ab50`, measurements m1 `4b57796`).

#### Fx-3 Citation for "half already held"
- side A: `:75-77` "The R12 pilot ([[measurement-task-21.5-r12-pilot-2026-11-13]]): 7% CAUSED, 19% CAUSED+INFORMED; about half of injected items were already held."
- side B: the 7%/19% figures are right (`workflow/measurements/task-21.5-r12-pilot-2026-11-13.md:4` "p_w 0.07 CAUSED / 0.19 CAUSED+INFORMED"). The "half held" figure is from `workflow/measurements/injection-already-held-2026-11-13.md:39` ("7,641 / 15,934 = 48.0%"). The R12 pilot file never mentions "held".
- resolution: cite [[measurement-injection-already-held-2026-11-13]] for the second clause.

#### Fx-4 Bug count
- side A: `:94` "66 bug rows are not `fixed`."
- side B: by literal Status cell in `workflow/bug_registry.md` I count 67 of 217 rows:
  - 60 `open` (including bug-088 "open (deferred by user)", `:141`)
  - bug-015 `remedied` (`:58`)
  - bug-085 and bug-087 "fix on branch (undeployed)" (`:138`, `:140`)
  - bug-091 and bug-209 `recurring`
  - bug-216 "in progress"
  - bug-218 "suspected"

  It is 66 only if "remedied" counts as fixed. The count is also fragile because rows bug-183 (`:234`, `|| true`) and bug-209 (`:260`) contain unescaped `|` inside backticks, which shifts their Status column. That is worth a registry or lint row.

#### Fx-5 In-progress plan count and age
- side A: `:65` "seven plans are 'in-progress' for 4-8 weeks".
- side B: frontmatter has nine `status: in-progress` (plans 2, 3, 6, 7, 8, 9, 10, 15, 23), and the POP Status column has ten (it adds 21, `:44`). Plans 2-9 were created 2026-09-14/15 (about 8.5 weeks); plan-15 was created 2026-10-06. A minor point, but the "seven" reads as the whole in-progress set.

### Clean areas
- Every "landed" sha in the draft (`:31-33`) is a real merge on master with the stated content: 3.7 `91ddbe0`, bug-178 `76ec748`, bug-179 `aea4098`, 26.0 `61b3bde`, 26.1 `9b2c4ac` + `25af9ca`, 26.2 `05164ce` + `078c951`, 26.3 `fdc6359`, 26.6 `8a867bc`, 26.4 `0c74872`. 0.81.0, 0.81.1 and 0.82.0 releases are confirmed (`9432b83` lists 26.1/26.2/26.3/26.6; 26.4 came after 0.82.0).
- Every item in the "Not started" list (`:36-37`) is `pending` in its spec, with no merge on master: 26.5, 26.7-26.9, 27.x, 25.2-25.5, 23.1-23.3, 23.5 and bug-185.
- There is an implementation summary for every merged task since 3.7: 3.7, bug-178, bug-179, 26.0, 26.1, 26.2, 26.3, 26.4, 26.6, bug-195, bug-197-198, bug-199-200, and user-level-state-commands.
- The W1-c riders are physically present in their hosts: 23.5 `#w1c-rider` at :1075, 19.1 `#w1c-riders` at :270, 19.5 at :182. bug-136's rider is on 23.5 (`bug_registry.md:189`).
- T2's holdings (bug-208 and bug-213 → 26.5; deferral rows `:55` and `:57` → 26.5) match the bug and deferral registries. The bug-216 → handhold arm-A ordering matches the exploration (`:144-145`).
- bug-177 was logged 2026-11-09 (`8ddf68e`). The T4 order bug-185 → 23.2 → 23.1 → 23.3 ∥ 23.5 matches POP `:46`.
- T1's contents match `handoff.md:23-31,60`. bug-088 is "deferred by user" as the draft says. Plan-11 is superseded in both the POP and frontmatter.
- POP and frontmatter agree for plans 1, 4, 5, 11, 12, 14, 16-20, 22 and 23. One nit: plan-13 is "DORMANT" in the POP (`:36`) and `drafting` in frontmatter.
- Plan-21 row 21.6 exists (`plan-21-agent-context-usage.md:57`), so deferral row `:56`'s owner is real. The draft's T3 list (`:109`) omits 21.6; it gated after 24.6 R4.
- `plan-review-2026-10-07.md#order` is properly superseded via `rel:` in 10-14 `:430`. I did not check its decision rows further.
