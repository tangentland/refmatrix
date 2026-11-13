## contra-b: context delivery (T3)   (files read: 31)

Sources: dev master `0d2a270`. Plan-10 rev 5 is read from the plan-10 clone, branch `task-plan10-revival` (`c04c9b9`), cited below as `[p10]`. 25.1 rev 8 is read from the 25.1 clone, branch `task-25.1-recall-hook-byte-budget` (`69da299`), cited as `[p25]`. The clones have their own commit histories: neither `c04c9b9` nor `4f95c23` exists in the dev repo.

### CB-1 [K6/K1] Two tasks own the same "still in play" names line, with different meanings
- side A: `[p25] task-25.1…md:801-802` "tier 4 the single names line (`still in play` / `+N more` names, cap 15)". That is: items demoted because the budget ran out.
- side B: `[p10] task-10.2…md:83` "one line `still in play: a, b, c (+N)` (h10) follows the header". Here the line holds items the session already has from an earlier prompt. And `:88-89` says "`hook_budget`, `fit_blocks`, the budgets, the generator, the argv and the trailer format are untouched". 10.2 was written against 25.1 **rev 7** (`:20-21` "spec rev 7").
- also: `[p10] task-10.2:130-132`, "R8 Offline parity … reproduces dd-10r's v2 names-only figures (0.470 block…)". Those figures come from the pack without the ladder. Rev 8's excerpts, pointers and spill page change both the baseline and the trailer (`[p25] :783` "+N more (output capped at 9,500 B)", `:808` "names line ends with that command").
- why it matters: whichever builds second gets either two lines with the same label, or one line meaning two things. 10.2's "untouched" claim and its parity gate cannot both hold once rev 8 ships.
- proposed resolution: one owner. 25.1 rev 8 owns the line, with two kinds of member (held / over budget). 10.2 is re-specced against rev 8 and its R8 parity figures are re-derived. The order in which held-item removal and the ladder apply is stated explicitly.

### CB-2 [K1] 25.1 rev 8 contradicts its own R3, R8 and AC-14, and adds no `amends` edges
- side A: `[p25] :190` R3 "whole bodies only, greedily in rank order". `:533` AC-14 mutation "a cut body (AC-9)" must FAIL a test. `:306-307` R8 "distinct named hits + trailer N = hits retrieved".
- side B: `[p25] :799-800` R13 "tier 2 a short excerpt (the item's first lines … at most ~3 lines / 300 B)". `:806-808` R14: items past the names cap and degraded bodies go to a spill page.
- why it matters: the AC-14 mutation "a cut body" now describes what tier 2 is supposed to do. R8's arithmetic has no term for spilled items. R9 (`:309-311`, "never for a trimmed hit") does not say whether an excerpt counts as `delivered`.
- proposed resolution: rev 8 amends R3, R8, R9, AC-9 and AC-14 by name, with `rel: amends` edges. Excerpt counts as a `form` in the delivered event.

### CB-3 [K3/K6] One task, one branch, split across two tracks; rev 8 has nowhere to be built after the merge
- side A: draft `plan-review-2026-11-13.md:107` T1 holds "25.1 rev 7 … → merge → release → fleet `install-hooks`". `:109` puts "25.1 rev 8" in T3. `handoff.md:60` "merge 25.1 → … release 0.83.0 → fleet `install-hooks` … → 25.1 rev 8 RED/GREEN".
- side B: `[p25] :793` "Sequenced after the rev-7 GREEN (`green-251c`): RED then GREEN as its own round", on the same task and branch (`cec8afe`, `4f95c23` are on top of `e5a516c`). The header still reads `:11` "updated: 2026-11-09" and `:20` "not built", status `pending`. `plan-review-2026-10-07.md:55` "C11 Batch the hook deploys … as few `install-hooks --apply --force` windows as possible".
- why it matters: merging the branch carries an unbuilt spec (R12-R14) into master. bug-164 gets marked fixed while rev 8 has no branch. Rev 8 regenerates every hook command, so the fleet needs a second reinstall right after 0.83.0's. That runs against C11, and the last fleet reinstall produced the bug-209/212/214 detour.
- proposed resolution: user decision. Either (a) split rev 8 into its own task id (25.1b) with its own branch and spec, or (b) hold the 25.1 merge until rev 8 is GREEN and ship one hook window. Update the frontmatter status either way.

### CB-4 [K3] 25.1 declares a dependency on 26.7, but is queued to merge before it
- side A: `[p25] :22-24` "Depends on: … plan-26 merged (… its 26.7 regroups `MEMORY.md`, which R3's curated-hook lookup reads)". `:34` `rel: depends-on -> [[task-26.7-memory-index-by-subject]]`.
- side B: draft `:146` queue 1, "T1 — finish 0.83.0", which merges 25.1. `:150` queue 5, "T2 — 26.7 → 26.8 → 26.9". Draft `:36` lists 26.7 as "Not started".
- why it matters: either the edge is stale (R4 `:196-199` already reads both key shapes) or 25.1 merges ahead of what it depends on.
- proposed resolution: if R4's dual-key lookup is the real contract, drop the 26.7 edge and the "plan-26 merged" clause. Otherwise move the merge.

### CB-5 [K3] Rev 8 relies on 10.6 and 10.3, which come after it; the draft queue leaves out 10.3 and 10.5
- side A: `[p25] :804` "Kind labels (10.6) apply at every tier". `:808` spill page "removed at compaction". `:820` AC-18 "the page is gone after a compaction marker". `rmx grep`/`grep` finds no `last_marker` or `compact-marker` anywhere in `src/refmatrix/`, so the marker is not built.
- side B: `[p10] task-10.6:18` "Depends on: [[task-25.1…]] merged". `[p10] plan-10:178` "10.3 | **Compaction marker** — 19.6 R8a's writer". 25.1 has no edge to 10.3.
- also: draft `:149` "25.1 rev 8 → 10.6 → 10.4 → 10.2 → handhold" omits 10.3 and 10.5. But `[p10] task-10.6:19-20` needs 10.3 for the composite, and `[p10] plan-10:191` "10.2 starts only on 10.5's GO". `[p10] task-10.2:18-19` "the 50-probe read-back test is still to run".
- proposed resolution: 10.3 goes first (plan-10 `:183` already says it "can start now"). 25.1 rev 8 gains `depends-on 10.3`, and its label clause is restated so 10.6 adds labels later. The queue line becomes 10.3 ∥ 10.5 probe → 25.1 rev 8 → 10.6 → 10.4 → 10.2.

### CB-6 [K6/K1] A second "already said, don't repeat" mechanism, with no compaction reset and no trace
- side A: `task-25.3…md:148-152`, R7 "A per-session sidecar `.refmatrix/stm/<session>.helix.json` … holds the keys already RENDERED this session". The title (`:4`) says "helix says a stale line once per session". The file contains no "compact" or "marker" text (0 matches).
- side B: `[p10] plan-10:63-65` "Whatever this plan stops re-sending may have been compacted … resets 'held' at every compaction marker … nothing is removed by rule". `[p10] plan-10:165` L3 "compaction the only reset". The 19.6 split table (`[p10]` 19.6 `#split-plan-10`) puts per-session emitted state in `stm/<session>.emitted/`.
- why it matters: helix lines are part of scan-prompt's render, which is exactly the payload plan-10 dedupes. After a compaction, 25.3 keeps a stale-line warning silent for the rest of the session, which is the failure plan-10 was designed around. Its state also lives outside `.emitted/`.
- proposed resolution: 25.3 R7 adopts 10.3's marker as the reset and keeps its state in `.emitted/`. Better still, a suppressed helix note moves to plan-10's names line instead of disappearing.

### CB-7 [K2/K5] 10.6 builds 19.6 R5's `unchanged` line without the pre-registered gate, and cites a stale premise
- side A: `task-19.6…md:184-185` "R5 Versioned blocks … built only in the bands of Table A that say so", and "the STM composite is TWO blocks". `plan-review-2026-10-14.md:344` d9v: "19.6's pre-registered ranges are CONFIRMED".
- side B: `[p10] task-10.6:49` p6 "The composite is versioned as ONE block now". `:66-69` R4 "After deploy, that share is recorded against 19.6 Table A's bands as a check (… recorded, nothing reverted)". `:36-38` concedes Table A "was measured on the two per-prompt ids only … never on the composite".
- also: `[p10] task-10.6:26` `implements -> [[exploration-session-phased-context#vi-unchanged]]`. That exploration still says, at `session-phased-context.md:174-177`, "dedup of scan-prompt's ranked entries does not pay … recall packs … near-identical across turns by design". The 2026-11-13 numbers refute both claims: `injection-already-held…md:39` "48.0%", and `[p10] plan-10:57-58` "`prompt-recall` 0.00% / 3.32%".
- proposed resolution: user decision. Either run Table A on the composite before 10.6's R3 (it is offline and cheap), or record explicitly that the user waives d9v for the composite. Revise the exploration's `#vi-evidence` either way.

### CB-8 [K5] The 21.5 spec was not revised after its own pre-registered band fired
- side A: `task-21.5…md:775-776` R12 "`p_w < 0.50` | the matcher or the kernel is revised and re-measured". The spec is still rev 3.1 and still contains the `bash_name` leg. `plan-21-agent-context-usage.md:56` "21.5 | now (user, 2026-11-11)".
- side B: `task-21.5-r12-pilot-2026-11-13.md:4` "p_w 0.07 CAUSED / 0.19 CAUSED+INFORMED". `:81` "the instrument measures proximity, not use". `:88` "Drop or gate `bash_name` (0/46 CAUSED…)", one of seven matcher changes.
- why it matters: the pilot ran on the legacy window, not R12's 21-day post-deploy window, but its result is below the lowest pre-registered band. Approving rev 3.1 as written would build a matcher the labels already reject.
- proposed resolution: a rev 4 folds the seven matcher changes before any approval decision. Plan-21's 21.5 row stops saying "now".

### CB-9 [K5] 19.6's Table C success metric scores read-back with the matcher the pilot refuted
- side A: `task-19.6…md:371-373` "For `tool` it calls 21.5's ONE matcher, `telemetry.tool_touches(…)`". `:407` Table C verdicts are on `readback_per_1k`. `plan-19-adaptive-memory-budget.md:213` d21-5a (user, 2026-11-13) binds them together.
- side B: `task-21.5-r12-pilot…md:81` "about 90% of headline credits are touches the agent would have made anyway, or coincidences".
- why it matters: phased/cache arms would be judged GO or NO-GO on a proximity count.
- proposed resolution: 19.6's read-back definition waits on 21.5 rev 4's matcher, or Table C counts only R12 explicit uses plus `cited_in_answer` until then.

### CB-10 [K2/K6] The draft's P3 freezes "19.0-19.6", against d9bi and against work its own queue builds
- side A: draft `:125-126` "19.0-19.6, 21.2-21.4, the 21.5 build and 21.7 are frozen".
- side B: `plan-review-2026-10-14.md:388` d9bi (user): "Plan 19 … LEADS Wave 1 … 'I want the context adaptive/variable stm handling in-place so we can build helix on top of that substrate'".
- In-flight work that builds plan-19 pieces:
  - `[p25] task-25.1:26-27` "Builds: 19.1 R1-R8 …; runs 19.5 R1 (the probe) as R0"
  - `task-25.3:24-25` "Builds: 19.0 R1"
  - `[p10] plan-10:178` 10.3 = "19.6 R8a's writer"
  - `[p10] task-10.6:27` `realizes -> 19.6`
- Plan-19 still records 19.1 and 19.5 as its own Wave-1 tasks: `plan-19…md:159` "19.1 … 1 (after 23.1)", `:163` "19.5 … R1: Wave 1, before 19.1", and `task-19.1:16-21` "Scheduled after 23.1 … deploys in the C11 batched hook-install window".
- why it matters: P3 reverses a user decision without citing it. Plan-19's table and 19.1's header would let a second implementer build 19.1 again.
- proposed resolution: P3 cites d9bi and asks the user to amend it explicitly. Plan-19's task table marks 19.1 and 19.5 R1 "realized by 25.1", 19.0 R1 "by 25.3", and 19.6 R8a and R5-composite "by 10.3 / 10.6". The freeze names only what is left: 19.2, 19.3, 19.6 phasing and cache, and Table C.

### CB-11 [K5] P3 also freezes the pull-side tasks the measurements favour
- side A: draft `:76-78` F4 "Building 19.x and 21.2-21.4 refinements before the handhold experiment … risks building on a premise the next measurement removes". `:125` freezes 21.2-21.4.
- side B: `task-21.5-r12-pilot…md:68` "scan_prompt C+I 8/113 = 0.07; prompt_recall 2/4; context 1/3; session_start 1/1". `handhold-outcome-experiment.md:47` "Pulled and boundary handholds look better". `:117-118`: every band short of "premise in trouble" says "keep boundary + pull". 21.2 and 21.4 are pull-side (`rmx context` precision, NL ranking, steering surfaces). Only 21.3 (PostToolUse nudge) is push.
- proposed resolution: freeze 21.3 only. 21.2 and 21.4 can proceed.

### CB-12 [K3] Ordering cycle between the 21.5 decision and the handhold experiment
- side A: `handhold-outcome-experiment.md:15` "Runs after the user's decision on task 21.5". `:144` "After the user's decision on 21.5". `plan-of-plans.md:68` "runs after the user's decision on task 21.5". `handoff.md:60` "→ 21.5 approval decision → handhold outcome experiment".
- side B: draft `:127` "21.5's approval decision becomes part of that charter decision", which comes after the experiment (`:151` queue 6).
- also: `[p10] task-10.2:111-116` nests 10.2's A/B inside the experiment ("its arm A (push on) splits into `A+dedupe` / `A+full`", ≥ 14 days). The draft `:149` serialises "10.2 → handhold experiment". The exploration's arms table (`:67-71`) has no dedupe factor.
- proposed resolution: user decision on which gates which. Whichever wins, the exploration's `#sequence`, POP `#queue-handhold-outcome-experiment` and the handoff are updated to match, and the exploration gains 10.2's nested arm.

### CB-13 [K6] 25.2 and 25.3 have no slot in the draft
- side A: draft `:109` T3 holds "bugs … 164-166" (165 = 25.2, 166 = 25.3) and "25.2, 25.3". P3 (`:124-126`) names neither as proceeding nor as frozen. Queue `:144-154` has no 25.2 or 25.3 line.
- side B: `plan-of-plans.md:48` plan-25 "approved 2026-11-09". `[p10] task-10.2:99` "25.2's ack-only gate still runs first where it applies".
- why it matters: 10.2 assumes a gate that has no scheduled build, and the helix half of CB-6 has no owner slot.
- proposed resolution: add both to P3, one way or the other. Note that 25.2's gate (`task-25.2:67` g6 "A gated call prints nothing") has the same shape the user rejected for non-human turns in Q10 (`open-questions.md:42`). It was never scored against the 11 labelled / 16 R12 uses that killed that gate. That check belongs to the user decision.

### CB-14 [K2/K6] The plan-24 retarget is blind to Q11, plan-10 and plan-25
- side A: `task-24.8…md:91`, the 19.6 row: "R5's versioned blocks build on `refmatrix.injected` and `rmx_scan_prompt(skip_block_shas)` (the verb decides and emits `unchanged`)". 24.8 R5's held-items table has no row for 10.2-10.6, 25.1, 25.2 or 25.3, and plan-24 contains no "25.1" or "plan-10" text. `task-24.6:116-118` R2 "Budgets and sizes come from 24.5's `userConfig` (`scan_max_tokens` …)".
- side B: `open-questions.md:43` Q11 "19.6 block diff not used for these payloads". `[p10]` 19.6 `#split-plan-10`: R5/R6 for `prompt-recall` and `scan-prompt` are built by "nobody". `[p25] :160-180` R1 "One budget module, one unit … UTF-8 bytes".
- why it matters: once 24.8 retires the hooks, the ladder, the spill page, names-only dedupe and the curator entry have no defined host, and the mod budgets in a different unit.
- proposed resolution: this goes in P4's re-plan. 24.8 R5 gains rows for plan-10 and 25.1-25.3, and its 19.6 row drops `scan_prompt` from R5.

### CB-15 [K2] Handhold exploration: Q3 is only half folded, and the off-switch premise is false
- side A: `open-questions.md:48` Q3 "b: both; same measure … one measure, two triggers (session start and `/clear`)". `handhold-outcome-experiment.md:104` "Primary outcome: (1) on the paired re-entry leg". That leg is `/clear` only (`:85` "resumed after `/clear`").
- side B (off-switch): `:73-74` "A full off-switch for push already exists in the hook layer's budget gates". `[p25] :306` R8 "never empty". No push-off switch exists in `hooks.py` or `scan.py` (env reads checked). The only planned switch is 10.2's `arms.py` (`[p10] task-10.2:111-114`).
- proposed resolution: the paired leg gains a new-session trigger, or the session leg carries (1) as a co-primary. Arm B's switch is specified, probably by extending `arms.SESSION_ARMS`.

### Minor (one line each)
- `open-questions.md:52` Q7 ("19.6's versioned injection … is the dedupe; … the non-human gate (10.4) stands") and `:43` Q11 ("4+3") read as live answers. Q13 and Q10 superseded both, but neither row says so. Plan-10's log (`[p10] :156-161`) does record the chain.
- Draft `:14` "after the 25.1 merge": `git log master` has no 25.1 merge, and the branch is unmerged (contra-e may also flag this).

### Clean areas
- Q9, Q10, Q12 and Q13 are folded into plan-10 rev 5 and 10.2/10.4. 10.4 R4 explicitly amends 25.1's `HOOK_COMMAND_CHANNELS` for the separate curator entry.
- Q11 is folded into 19.6 `#split-plan-10` and into the POP plan-10 row on the plan-10 branch, which also records the override of W3-a ("plan-10 closes into 19.6").
- Q14 is folded into 25.1 rev 8 (R12-R14, AC-16-18), apart from CB-2's internal conflicts.
- Q4 and Q5 are folded in the handhold exploration and in 10.2 R7. Q6 became the 21.7 row in plan-21 and the task stub.
- 21.5's OD-4 and OD-5 are folded (d21-5a in plan-19 and 21.5 rev 3.1). The cliquedb-copy and pilot-first pre-ledger decisions are reflected in 21.5 `#open-for-user`.
- Plan-9's tasks 9.1-9.3 are complete and its residuals rode 21.1's close-out, so P2's proposal to close plan-9 is consistent (plan-10's `depends-on plan-9` stays satisfied).
- 10.6's budgets (2,000 / 4,000 / 9,000 B) match 25.1 R1. The 9,500 B hard cap sits above every per-command channel sum.
- The draft's F4 numbers (7% / 19% / ~half held) match the measurement files.
