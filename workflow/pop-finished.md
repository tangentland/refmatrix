---
gmd: "0.1"
id: pop-finished
title: "POP finished items — append-only record of what left the plan-of-plans"
tags: [workflow, planning, pop, ledger, history]
metadata:
  node_type: ledger
  created: 2026-11-15
---

# POP finished items {#root}

The user, 2026-11-15: "the POP should be a living doc" and "append finished items to a
pop-finished.md doc before deleting them from the POP". [[plan-of-plans]] holds current state
only. When a row there is finished (a plan or task done, a ruling applied, a decision amended into
its plan, a question answered and applied), it is appended here, whole and unedited, under the
date it left, and then deleted from the POP in the same commit. This file is append-only and is
history, not state: nothing here is consulted to decide what is next.

rel: part-of -> [[plan-of-plans]]
rel: depends-on -> [[orchestration#pop-truth]]

## 2026-11-15 {#d-2026-11-15}

### Questions answered and applied (Q23-Q31, session 070141d0) {#q23-q31}

| id | asked | question | options (lead's recommendation first) | status |
|---|---|---|---|---|
| Q23 | 2026-11-15 | Review gate: drop `/ch-review` as a mandatory step (ch-bsd + L-ruling + confirm-lite is the gate)? | (a) optional, on large src changes or request; (b) keep mandatory | "Q23 a, Q24 a, Q25 a, Q26 a" (user, 2026-11-15): (a), applied in [[orchestration]] |
| Q24 | 2026-11-15 | Where the operating procedure lives | (a) new `workflow/ORCHESTRATION.md` + short CLAUDE.md summary; (b) all inline in CLAUDE.md | "Q23 a, Q24 a, Q25 a, Q26 a" (user, 2026-11-15): (a), applied in [[orchestration]] |
| Q25 | 2026-11-15 | TDD step 0 (`ch-alignment` over `pseudocode/`, which does not exist) and the Docker wording | (a) conditional step 0, host-venv wording; (b) keep as written | "Q23 a, Q24 a, Q25 a, Q26 a" (user, 2026-11-15): (a), applied in [[orchestration]] |
| Q26 | 2026-11-15 | Planning default path | (a) Fable architect → bsd spec rounds → rulings → user Dk → merge; SDD chain kept as available; (b) keep the SDD chain as default | "Q23 a, Q24 a, Q25 a, Q26 a" (user, 2026-11-15): (a), applied in [[orchestration]] |
| Q27 | 2026-11-15 | Write up the context-feeding view? | (a) design note for plan-24 only; (b) note + admit trimming the per-prompt keyword injection before the mod; (c) neither | "Q27 b" (user, 2026-11-15): note [[design-note-tool-keyed-context-2026-11-15]] + plan-31 31.5 (measure per block, cut and tighten, not remove) |
| Q28 | 2026-11-15 | The freeze line omitted L106 queue steps 6-15: which stay before the mod? | (a) the triage in [[freeze-triage-2026-11-15]]; (b) all of L106 stays; (c) the freeze as written (6-15 post-mod) | "Q28 a" (user, 2026-11-15): applied to [[plan-of-plans#freeze]] |
| Q29 | 2026-11-15 | Test coverage: adopt the process rules and pull 29.4's runner ahead of 29.1? | (a) both; (b) process only; (c) neither | "Q29 a" (user, 2026-11-15): applied, L118, [[orchestration#one-suite]] |
| Q30 | 2026-11-15 | bug-251 (lint resolves `[[doc]]` by id, filename stem and case/dash-folded id; ingest binds the exact id only; 37 rel: lines lint clean and land nowhere): admit under the freeze? | (a) admit as plan-31 task 31.6: one resolver shared by lint and ingest (recommended: graph correctness, and the lint is the gate that hides it); (b) post-mod list; (c) fix the 37 links by hand now, defer the resolver | "Q30 a" (user, 2026-11-15): admitted as [[plan-31-pre-mod-loose-ends#t6]] |
| Q31 | 2026-11-15 | Plans 2-15 and 21-25 the freeze line did not name ([[freeze-triage-2-2026-11-15]]); plan-24 depends on task 3.7, which the freeze omitted: apply the triage? | (a) the table as proposed: admit 3.7, 25.4, 25.5; post-mod plan-13, 21.3, 21.7; close plans 2, 8, 9 and 25.1 now, 6/7/15 at their named events (recommended); (b) admit 3.7 only, everything else as (a) but 25.4/25.5 post-mod; (c) other | **withdrawn** (lead, 2026-11-15): built from file statuses, not the 2026-11-13/14 consolidation; 3.7 is merged (`91ddbe0`, 0.81.0), 25.4/25.5 superseded (L42). The user: \"include 2-31\"; re-asked from the rewritten triage |
{#q23-q31-table}

### Questions answered and applied (Q32-Q36, freeze-triage-3) {#q32-q36}

| id | asked | question | options (lead's recommendation first) | status |
|---|---|---|---|---|
| Q32 | 2026-11-15 | plan-10's dedupe (10.5, 10.6, 10.4, 10.2) requires 25.1b merged; 25.1b is post-mod (contradiction in the freeze, freeze-triage-3) | (a) the four go post-mod with 25.1b; 10.3 and 31.5 stay pre-mod; (b) admit 25.1b; (c) re-spec plan-10 without 25.1b | **(a)** (the user, 2026-11-15: "given what I just said q32-36 agree to your recommendations" (with L127)); applied by L128 |
| Q33 | 2026-11-15 | What triggers the plan-24 re-plan, now that plan-28 (the charter experiment D-Q5 waited on) is post-mod? Plan-24 is `drafting`, last bsd round DIRTY (2026-10-20), nine of ten specs stale | (a) the freeze's last step is a plan-24 freshness revision to approval, with 31.5, 21.5 phase M and 30.6 as its evidence; (b) run plan-28 before the mod | **(a)** (the user, 2026-11-15: "given what I just said q32-36 agree to your recommendations" (with L127)); applied by L128 |
| Q34 | 2026-11-15 | 24.6 R4 calls `stm.tool_event_fields`, which is in 21.5's frozen build phase and not in `src/`: who builds it? | (a) the plan-24 revision moves the builder into 24.6; (b) un-freeze 21.5 R1 alone, pre-mod | **(a)** (the user, 2026-11-15: "given what I just said q32-36 agree to your recommendations" (with L127)); applied by L128 |
| Q35 | 2026-11-15 | G22 (operational content out of the skew) and G30 (the `denotes` fold evaluation): the first triage's table kept them 'with step 10', its summary and the freeze line omit them | (a) admit both: G22 after plan-30 release C, G30 folded into 30.6; (b) both post-mod; (c) G30 only | **(a)** (the user, 2026-11-15: "given what I just said q32-36 agree to your recommendations" (with L127)); applied by L128 |
| Q36 | 2026-11-15 | The rest of the un-triaged list (U3-U17 in freeze-triage-3): admit G32 and the cross-partition `rel:` probe (25.2, 21.5 phase M and 26.5 wait on them); post-mod 19.0 rest, 19.2, 19.5/19.6 frozen parts, 21.3, 21.5 phase B, 21.6, 21.7, plan-20, plan-7 W4-a rows, linked-readonly-store, `legs_ms`; bug-182, bug-224, bug-167/174 follow their post-mod hosts | (a) apply as proposed; (b) item by item | **(a)** (the user, 2026-11-15: "given what I just said q32-36 agree to your recommendations" (with L127)); applied by L128 |
{#q32-q36-table}

### Question answered and applied (Q37) {#q37}

| id | asked | question | options (lead's recommendation first) | status |
|---|---|---|---|---|
| Q37 | 2026-11-15 | plan-31 D10: 31.4 reaches zero standing warnings by an opt-in `--strict` flag and one enum line (`session/recall-state`) in the upstream GMD linter (`~/claude_tools/gmd`, vendored here as a committed upstream blob), plus one line in your `~/.claude/MEMORY-RULES.md`. May the plan change the upstream linter and that file? | (a) yes, both; (b) linter only, MEMORY-RULES unchanged; (c) no: 31.4 keeps the change inside this repo's wrapper | **(a)** (the user, 2026-11-15: "q37-a yes"): plan-31 D10 decided |
{#q37-table}
