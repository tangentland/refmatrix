# contra-a: memory organisation (T2) — files read: 26

Persisted by the lead from the agent's text (2026-11-13, dev master 0d2a270, read-only sweep).
Brief: workflow/agents/contra-pop.md. 9 findings.

## Ca-1 [K3] 25.1 ships in 0.83.0 before 26.7 and plan-27; three recorded orderings forbid it, no waiver found
- A: workflow/plans/plan-26-memory-organisation.md:358 "25.1 reads the index 26.7 writes, so 26.7 (19.3) closes before 25.1 starts."
- A: workflow/plans/plan-25-cliquedb-field-report.md:134 "3.7 ──► plan-26 ──► plan-27 ──► 25.1 ──► 25.2 ──► 25.3 ──► (plan-24)"; :140 "26.7 regroups `MEMORY.md`, which 25.1's pack reads for curated hooks (19.1 R3(b)); 27 migrates cliquedb's dir last, so the live after-check on cliquedb runs on the organised dir."
- A: task-25.1-recall-hook-byte-budget.md:22-24 "Depends on: … plan-26 merged (… its 26.7 regroups `MEMORY.md`, which R3's curated-hook lookup reads)"; :34 `rel: depends-on -> [[task-26.7-memory-index-by-subject]]`; :576 "`memory_index.py` | none expected … re-read after 26.7".
- A: workflow/plan-of-plans.md:48 row 25 depends-on "3.7 merged; plan-26 (26.4, 26.7); plan-27; 23.0; 21.1".
- B: plan-review-2026-11-13.md:120 "T1 Ship 0.83.0 | 25.1 rev 7, …"; handoff.md:60 "merge 25.1 → bug-212 → bug-216 → release 0.83.0"; queue puts 26.7 at step 5, plan-27 after.
- Searched open-questions.md, POP overrides, handoff.md, past_handoffs/019 for a pull-forward decision: none.
- Why: pack's hook lookup ships against pre-26.7 MEMORY.md; nothing re-reads it after 26.7; 26.7 ACs don't protect it; cliquedb after-check runs on an un-organised dir.
- Resolution: user decision. Record the waiver (amend 25.1:22-24/:34, plan-25 #ordering, POP row 25) and add a 26.7 AC that 25.1's hook lookup survives the regroup (AC-9 already runs both key shapes), or hold 25.1 out of 0.83.0.

## Ca-2 [K1/K6] P3 freezes 19.0-19.6, but T2 builds 19.3 and 26.6 already built most of 19.4; plan-19 records neither
- A: plan-review-2026-11-13.md:138 "19.0-19.6, 21.2-21.4, the 21.5 build and 21.7 are frozen until the handhold experiment reports …"
- B: task-26.7-memory-index-by-subject.md:39 "This task builds 19.3. Its R1-R8, ACs and mutations are this task's requirements verbatim"; plan-26-memory-organisation.md:26 "tasks 26.6 and 26.7 BUILD the approved plan-19 tasks 19.4 and 19.3"; draft :163 queues 26.7 at step 5.
- B: task-19.4-keep-derived-layers-current.md:280 "recording 19.4's realized-by-26.6 status is left to plan-19's owner when 26.6 lands"; 26.6 merged 8a867bc, yet task-19.3:8 and task-19.4:8 `status: pending`; plan-19.md has no 26.x reference.
- Same in T3: 25.1 (in T1) builds 19.1 and 19.5 R1 (25.1 title, :25).
- Why: P3 blocks T2 step 5 or step 5 builds a frozen item; a later 19.x re-plan would re-spec 19.3/19.4.
- Resolution: P3 excludes by name 19.3/19.4 (owned by plan-26) and 19.1/19.5 R1 (owned by 25.1); plan-19 owner records realized-by lines per plan-26 #plan-19 (:230-234).

## Ca-3 [K3/K6] Queue drops 26.6's R3 residual and sequences 23.5 R9/AC-9 ahead of it
- A: task-26.6-compile-subject-hygiene.md:16 "Status: In progress — … the R3 residual open"; :240 "built right after 26.7 merges and 26.6 is `completed` only then"; :250 "Task 23.5 R9/AC-9 reads R3's index write"; past_handoffs/019-0830-pipeline-paused_2026-11-11.md:106 "26.4 → 26.5 → … → 26.7 → 26.6 R3 residual → 26.8".
- A: task-23.5-read-path-and-holder-bounds.md:643-645 "AC-9 is written and registered after 26.6 merges …, so K counts the apply WITH 26.6's hygiene; a later change that adds per-row writes to the apply fails AC-9".
- B: draft :33 lists 26.6 as landed; queue step 3 runs 23.5, step 5 "26.7 → 26.8 → 26.9 → plan-27"; R3 residual in no line.
- Why: 23.5 registers K without R3's in-hold index render; R3 later fails AC-9's ratchet or is bent to dodge it; 26.8 AC-7 expects compile to regenerate the index.
- Resolution: "26.6 R3" right after 26.7; hold 23.5 AC-9 registration until R3, or move 26.7 + R3 ahead of 23.5.

## Ca-4 [K1] ADR-0005's MEMORY-RULES text (applied at 26.8) is unconditional; shipped save-state template gates on the marker
- A: docs/adr/0005-memory-dir-layout.md:323 "Write a new memory into its type folder: `feedback/`, `project/`, …"; :317 "it is applied at task 26.8, with the text below" (user-global MEMORY-RULES.md, every project).
- B: src/refmatrix/templates/commands/save-state.md:23-27 "A dir with a `.memory-layout` marker is organised: write into the type folder … A dir without the marker stays flat: write at the top level." (3842f6d).
- B: ADR-0005:17-18 "Every new on-disk behaviour is gated on a per-dir marker … so a deploy changes no un-organised dir's files"; plan-26:367-369 forbids changing other projects' dirs before plan-27.
- Why: after 26.8 only refmatrix is organised; agents elsewhere follow MEMORY-RULES into type folders plan-27 hasn't backed up; same agent gets opposite instruction from /save-state.
- Resolution: amend ADR-0005 Appendix A before 26.8 AC-8 so the MEMORY-RULES text carries the marker condition.

## Ca-5 [K6] bug-208 has no AC anywhere; bug-206 and bug-210 have no queue slot
- bug-208 A: bug_registry.md:259 "open — fix before 26.5 ships the marker writer"; B: task-26.5 has no bug-208 reference (inherited sections :299-348 cover 26.1 r4, 26.3 GREEN, 26.4 r1/bug-213); draft :121/:160 "26.5 (+ bug-208, bug-213)".
- bug-206: bug_registry.md:257 open, no plan/task owner; draft lists it in F7 (:86-87) and T2 (:121), T6 (:125) doesn't hold it, no queue line.
- bug-210: bug_registry.md:261 open, only ref task-26.2:16 "follow-ups bug-210"; draft T2 lists it, no queue line.
- Resolution: anchor bug-208 as a 26.5 precondition with its own AC (mirror #inherit-264-r1); 206 one home (T2), drop from F7; 206/210 in a queue line or explicit backlog.

## Ca-6 [K6] bug-202's restore points at a force input that covers save-states only
- A: bug_registry.md:253 "2 of 349 bridged memories lost ALL anchors (`guardrail-coordinator-lane-dispatch`, `guardrail-two-writers-one-logical-db`) … restoring those needs a forced re-bridge (26.5 AC-5's force input)"; row marked fixed.
- B: task-26.5-memory-organise-verb.md:129-130 "`--apply` re-ingests EVERY save-state file in the dir, bypassing the hash gate for those paths only."
- Caveat: files with those ids not found in the refmatrix memdir.
- Resolution: 26.5 or 26.8 names the restore with a check.

## Ca-7 [K3] Draft makes plan-27 wait on 26.9, which plan-26 says gates nothing
- A: plan-26:356 "26.9's live step (AC-5) does NOT gate plan-26's close"; task-26.9:19 same; plan-27:20 "Depends on: plan-26 merged, released AND deployed (26.8 green)."
- B: draft :163 "26.7 → 26.8 → 26.9 → plan-27".
- Resolution: 26.9 ∥ plan-27 after 26.8.

## Ca-8 [K5] Plan-27's hook premise stale after 0.82.0 re-install; its Q3 rests on plan-24, which P4 defers
- A: plan-27-memory-fleet-rollout.md:67-68 "cliquedb and viascope have neither the hook nor (in viascope's case) any save-state"; :50 "**no** (stale hooks…)"; Q3 :187-188 "DECIDED (r4): report only, and leave them to plan-24's mod"; :135 "plan-24's mod replaces the shell hooks anyway".
- B: ~/github/atollogy/bdep/viascope/.claude/settings.json:51 and ~/github/atollogy/bdep/cliquedb/.claude/settings.json:45 carry the `rmx ingest-gmd` SessionStart bridge; draft :145 "plan-24 stays drafting"; memory project_fleet_hooks_found_by_marker_not_hub: bdep/thiquet missed by the re-install.
- Resolution: refresh plan-27 #survey/#facts at 27.1 start; re-word Q3 to "T1's marker-found install-hooks + 27.6's report".

## Ca-9 [K2/K5] (probable; verify at HEAD) MEMORY-RULES forget flow ends at deleting the file; the bridge never forgets a deleted file
- A: ~/.claude/MEMORY-RULES.md:71-80 "## Forget flow … 3. Update `MEMORY.md` … 4. Delete the file." — no `rmx memory forget` step.
- B: plan-26:117-118 "No code path forgets a moved memory. `Store.vacuum` purges dead `tracked_files` rows, but the bridge never calls `mark_tracked`." `rmx memory forget` exists (cli.py:13410).
- Resolution: with 26.8 AC-8's MEMORY-RULES edit, add "5. `rmx memory forget <id>`".

## Clean areas
- ADR-0005 vs plan-26 vs 26.1-26.8 (folder table, marker gating, id identity, `savestates/` authority, four every-dir changes): consistent.
- ADR-0002 vs ADR-0005/26.6 on subjects, `part-of`, "topic": consistent.
- 26.5 depends-on (26.1-26.4) all merged; 3.7 rebase prerequisite met; 26.5 buildable once bug-208 is anchored.
- bug-213 anchored in 26.5 #inherit-264-r1 (R-264a..d, AC-264).
- POP #goal-2026-11-09 user-gated steps match 26.8 AC-8 and plan-27.
- MEMORY.md budgets (200 lines; 24,000 chars, memory_index.py:59/:78) both enforced, no conflict.
- 26.8 expected counts stale (40 + 250 vs today 44 + 262, 80 impressions); self-correcting via fresh preview, but 26.8 should re-read.
- Status drift: 26.1, 26.4 frontmatter `pending` though merged (9b2c4ac / 0c74872); 26.6 `in-progress` correct; all ADRs Proposed (convention).
- Unverified risk next to X1: bug-216 R2 (task-bug216:61-64) routes "`ingest-gmd`'s walk" through `should_ignore(p, root)`; it should say the `as_memory` walk (memdir under the ignored `.claude`) is not in that set. (Lead: pinned via red-216 addendum 2.)
