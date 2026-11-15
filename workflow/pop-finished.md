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

### POP header wording replaced on 2026-11-15 {#pop-header-2026-11-15}

Replaced because it said the table mirrors the files; the files now follow the POP
([[orchestration#pop-truth]]).

> **Single source of truth for what to implement next, and the status of every plan** (the user, 2026-11-15: "the source of truth must be the POP"; every state change updates this file in the same commit, [[orchestration#pop-truth]]). All plans
> live in `workflow/plans/` and never move — a plan's lifecycle is tracked by the `status` field in
> its GMD frontmatter (`metadata.status`), mirrored in the table below. `@ch-gap-master` keeps this
> current.

### Plans finished: rows removed from `#plans` {#plans-finished-2026-11-15}

Plans 1, 4, 5, 12 and 14 were `completed`; plan 11 was `superseded`. Plans 3 and 9 were closed by
the user's D-Q6 on 2026-11-13 ([[plan-review-2026-11-13#d-q6]]): 3.7 merged `91ddbe0` and
released in 0.81.0, and 21.1's summary records plan-9's riders. Their rows still read
`in-progress` and are kept as they stood.

| # | Plan | Status | Tasks specced? | File | Depends on |
|---|------|--------|----------------|------|------------|
| 1 | plan-1-deploy-runtime | completed | yes (3) | `workflow/plans/plan-1-deploy-runtime.md` | — |
| 3 | plan-3-verbs-parity | in-progress (3.1-3.3 completed: 82bbc2b, merged 8ba4799; tasks 3.4-3.6 built (W1-b) and released in 0.80.1; ch-bsd r12 at b18d7e8 MEH-only (0B/0S/3M: #m-1/#m-2 registered as deferrals riding 3.7, #m-3 = 3.7 itself); task 3.7 verb-it backlog = W2-d; plan-3 closes with 3.7 per AC-G4) | yes (7) | `workflow/plans/plan-3-verbs-parity.md` | plan 2 (deploy path) |
| 4 | plan-4-daemon-resilience | completed (W1-a: task 4.5 r4 remedy + task 4.6 r5 remedy and r6 amendment; ch-bsd r7 at 10d45e1 0 blocking, 1 MEH registered; todo G9 closed; released in 0.80.0) | yes (4) | `workflow/plans/plan-4-daemon-resilience.md` | — |
| 5 | plan-5-memory-bridge-complete | completed | yes (3) | `workflow/plans/plan-5-memory-bridge-complete.md` | — |
| 9 | plan-9-context-cost-telemetry | in-progress (built; ch-bsd r5 at e0b7df6: paperwork only — 9.2/9.3 summaries written in W1-d; r5 #m-11 and #s-5 ride 21.1's close-out = W1-c) | yes (3) | `workflow/plans/plan-9-context-cost-telemetry.md` | — |
| 11 | plan-11-helix-phase2-versioned-graph | superseded (user 2026-10-07: "helix's design supersedes plan 11's" — ADR-0004's helix half replaces the prolly store; never built) |
| 12 | plan-12-open-bug-remediation | completed (@ch-bsd CLEAN; deployed 0.72.0; bug-025 acceptance 20/20 reranked) | yes (6) | `workflow/plans/plan-12-open-bug-remediation.md` | — |
| 14 | plan-14-grep-learning-measurement | completed (plan review C10: re-measure lives in task 16.4) | yes (4) | `workflow/plans/plan-14-grep-learning-measurement.md` | — |
{#plans-finished-table}

### `#plans` intro and rows replaced by the 2026-11-15 rewrite {#plans-replaced-2026-11-15}

The rows of the plans that stay live, as they stood before the rewrite replaced them with
current state.

Rows corrected 2026-10-19 (W1-d bookkeeping sweep). Where a row names a W-item, that
plan's remaining work is scheduled in the folded wave list [[plan-review-2026-10-14#t11-folded-waves]].

| # | Plan | Status | Tasks specced? | File | Depends on |
|---|------|--------|----------------|------|------------|
| 2 | plan-2-hooks-reproducible | in-progress (ch-bsd r9 DIRTY; #b-1 closed by bug-025, #m-5 registered; #s-2 + #s-3 + #m-4 OPEN, re-verified 2026-10-01; remaining work is W1-c: #s-3 rides 23.5, #s-2/#m-4 ride 19.1, the scan-prompt rerank observation is measured by 19.5) | yes (3) | `workflow/plans/plan-2-hooks-reproducible.md` | plan 1 (deploy path) |
| 6 | plan-6-deferrals-docs-benchmark | in-progress (ch-bsd r1 DIRTY at e0b7df6, may NOT flip; remedy #b-1, #b-2, #s-1, #s-3, #m-1..#m-5 + todo G7/G8 = W2-a; r1 #m-4 docstring also listed under W1-d) | yes (5) | `workflow/plans/plan-6-deferrals-docs-benchmark.md` | — |
| 7 | plan-7-longmemeval | in-progress (symbolic reported; bug-030 fixed 2026-09-16, dense/fused re-run is W2-c; deferrals W4-a) | yes (4) | `workflow/plans/plan-7-longmemeval.md` | — |
| 8 | plan-8-derived-coverage-notes | in-progress (ch-bsd r5 may NOT flip; remedy W2-b, deferrals W3-b) | yes (4) | `workflow/plans/plan-8-derived-coverage-notes.md` | plan 7 (measures it) |
| 10 | plan-10-injection-dedup | drafting (reopened 2026-11-13: 48.0% of delivered items already held; names-only dedupe of the per-prompt payloads, Q13; no non-human gate, Q10; 10.4 predicate + curator silent, Q9; 10.3 builds 19.6 R8a's marker; 10.5 replay PASSED, read-back probe to run; 19.6 block diff not used for these payloads, Q11; ch-bsd spec review next. 10.1's 2026-09 negative result is history) | yes (3) | `workflow/plans/plan-10-injection-dedup.md` | plan 9 (its instrument); 25.1 (10.2, 10.4); 19.6 R8a ([[task-19.6-phased-context-and-topic-cache#split-plan-10]]) |
| 13 | plan-13-cross-partition-sweep | DORMANT (C9 re-scope corrected by d4b 2026-10-14: 21.4's gold set is code+docs only; the sessions question waits for its own gold set) | yes | `workflow/plans/plan-13-cross-partition-sweep.md` | 21.4 |
| 15 | plan-15-derive-impact-tracking | in-progress (15.1-15.4 all built + deployed at 0.76.0; flipped `completed` before the @ch-bsd gate, which found 15.1's test writing `src/refmatrix/store.py` — ch-bsd r1 #b-3, fixed on `bsd-r1-remedy`; returns to completed after a clean full suite on the main tree, with r13 #s-1/#m-1/#m-2 = W1-e) | yes (4) | `workflow/plans/plan-15-derive-impact-tracking.md` | plan 14 (same instrument-first shape); bug-039's stamp |
| 16 | plan-16-invisible-grep-shim | APPROVED 2026-10-15 (d9ck; ch-bsd r13 `be965bb`; 16.1-16.6; no `rmx learn on` before 16.3 deploys) | yes (6) | `workflow/plans/plan-16-invisible-grep-shim.md` | plan 15 (bsd-r1-remedy merged); plan-23 (23.1) for the 16.6 Wave-1 slice |
| 17 | plan-17-nightly-store-maintenance | APPROVED 2026-10-15 (d9cn; ch-bsd r10 approval-ready)
| 18 | plan-18-duckdb-store-maintenance | APPROVED specs 2026-10-15 (d9co; 18.1 completed; Wave 4)
| 19 | plan-19-adaptive-memory-budget | APPROVED 2026-10-15 (d9ce; ch-bsd r13 CLEAN `a0c0060`; 19.0-19.6 approval-ready; helix substrate per d9bi; execution of 19.0 AC-6f waits on 23.0 merge)
| 20 | plan-20-concept-similarity-eval | drafting (plan + task specs 20.1-20.3 written 2026-10-07: frozen labelled pairs, signals scored across 6 stores, conditional dense synonyms; read-only; merges target ADR-0004's alias map) |
| 21 | plan-21-agent-context-usage | in-progress (APPROVED 2026-10-15, d9ce; 21.1 built through ch-bsd r3 at cf7e4bb and released in 0.80.0, its AC-6 frozen fixture BLOCKED on the user's cut (deferral registry); 21.2-21.4 approval-ready; 21.3 AC-5 execution waits on 23.0 merge) | yes (4) | `workflow/plans/plan-21-agent-context-usage.md` | 16 (21.3), 23 |
| 22 | plan-22-audited-removal-and-repair | APPROVED 2026-10-15 (d9cm; ch-bsd r15 CLEAN `8fbfb0c`) | yes (7) | `workflow/plans/plan-22-audited-removal-and-repair.md` | 16.6, 23 |
| 23 | plan-23-bounded-write-harness | in-progress (APPROVED 2026-10-15, d9cn; 23.0 completed in 0.79.1, master d4bf001; 23.1 + 23.2 freshness fold 2026-11-09: 23.1 R11 `hook_writes` queue closes bug-177; freshness confirm folded 2026-11-09: 23.1 + 23.2 BUILD-READY, `memory_compile` apply bounded in 23.5 R9; 23.5's bug-112 gate met at 74f8f98; 23.3 + 23.5 freshness fold 2026-11-09 ([[bsd-plan23-3-5-freshness-62a2465]]): the measured bug-177 holder is the GMD re-ingest (bug-185, `workflow/plans/task-bug185-bulk-gmd-ingest.md`), 23.3 steps one GMD document at a time over all five daemon sync sites, 23.5 re-walks the op set after 3.7; build order 3.7 → bug-178 → plan-26 → bug-185 → 23.2 → 23.1 → 23.3 ∥ 23.5, with 23.5 R9 after 26.6) | yes (6) | `workflow/plans/plan-23-bounded-write-harness.md` | — |
| 24 | plan-24-mod-transport | drafting 2026-10-20 (DECIDED for tighter integration; 24.0 baseline specified, 24.1-24.8 next; the hook-shaped Wave 2-3 work retargets to it) | partial (1) | `workflow/plans/plan-24-mod-transport.md` | — (24.0/24.1 independent; 24.4 depends on task 3.7) |
| 25 | plan-25-cliquedb-field-report | approved 2026-11-09 (bug-181 folded into 25.1 R10 by the user, revision round 5; not started) (plan + task specs 25.1-25.4 written 2026-11-08, session 8d9a255f: bug-164 recall byte budget (builds 19.1 + 19.5 R1), bug-165 thin-prompt gate, bug-166 STM ref admission (builds 19.0 R1) + helix once-per-session, bug-167 BRE translation; task 25.5 added 2026-11-09 in revision round 2 (`cba1745`): bug-174 substring-mode `a.b` read as BRE via 25.4's translator, follows 25.4; spec reviews r1+r2+r3 folded (r3 DIRTY 0B/4S/9M: bug-id collision renumbered bug-173 → bug-180 in `9bcf464`, MCP silent cwd fallback logged as bug-181); r4-lite confirm (DIRTY 0B/1S/5M) folded in revision round 4; bug-181 folded into 25.1 per [[#goal-2026-11-09-scope]] in revision round 5, then `approved` ([[plan-25-cliquedb-field-report#approval]]); bug-174 re-measure queued at M ≥ 30 or 2026-12-31; after plan-26/27 and before plan-24 per [[#override-2026-11-08b]]) | yes (5) | `workflow/plans/plan-25-cliquedb-field-report.md` | 3.7 merged; plan-26 (26.4, 26.7); plan-27; 23.0; 21.1 |
| 26 | plan-26-memory-organisation | approved 2026-11-09 (ch-bsd r1-r5 folded; r6-lite confirm at `d396317` MEH-only 0B/0S/2M, n1/n2 folded into 26.2; earlier: r1 `8af766a`, r2 `696c3cb`; 10 task specs 26.0-26.9; 26.6/26.7 BUILD approved 19.4/19.3; 19.4 AC-4 recall leg → 25.1) | yes (10) | `workflow/plans/plan-26-memory-organisation.md` | 3.7 |
| 27 | plan-27-memory-fleet-rollout | approved 2026-11-09 (ch-bsd r1-r5 folded; r6-lite confirm at `d396317` MEH-only; r1 `8af766a`, r2 `696c3cb`; 8 task specs 27.0-27.6 + 27.2a) | yes (8) | `workflow/plans/plan-27-memory-fleet-rollout.md` | plan-26 deployed |
| 29 | plan-29-code-quality | in-progress 2026-11-15: 29.4 runs first (L118, Q29 a). Stage 0 (R0 durations) merged `3b930e4` (L121: 8 shards, tier (d) breach → R3). T0 spec merged `0e55687` (L122, L123). **Stage 1 T0.1' merged at this commit** (skip gate exact-reason + one memory-dir resolver; bug-155 residual, bug-254, bug-215 R1.5; ch-bsd r1 MEH-only GO, 12 mutations killed, L124, L126). Next: stage 2 (T0.2 + 29.4b ∥ T0.3 + 29.4c ∥ T0.8; bug-253 helper), then stage 3 T0.4 → T0.5, stage 4 29.4a, stage 5 T0.7 + 29.4d; then 29.1 → 29.5 → 29.2 ∥ 29.3 → 29.6. Ships in the next major release (0.N.0) with its full-suite gate | yes (6) | `workflow/plans/plan-29-code-quality.md` | 0.83.1 deployed (bug-241 + bug-240); `.venv-eval` duckdb 1.5.3 before any 29.4/29.5 baseline (L106) |
| 30 | plan-30-materialisation | approved 2026-11-15 (L117; D1-D3 user-decided) 2026-11-14 (plan + 6 task specs 30.0-30.5 written by ch-architect on Fable 5.2 from the bitmap-materialisation measurement report; ch-bsd spec r1 at `a169c17` DIRTY 0B/3S/5M NO-GO, all eight folded in revision round 2 per ruling L116; confirm-lite r2 at `5914997` MEH-only 0B/0S/4M GO, its four folded; plan-30 D12 accepted; fixes bug-243; plan-30 D1-D3 open for the user; three releases, release B re-derives the `pagerank` pass fleet-wide) | yes (6), in review | `workflow/plans/plan-30-materialisation.md` | plan-29 released (module split, census kit, derive digest); 30.4 also 23.0's sandbox |
| 31 | plan-31-pre-mod-loose-ends | drafting 2026-11-15 (admitted under the pre-mod freeze, [[plan-of-plans#freeze]]); six items — 31.1 bug-244 + bug-255 (lint/ingest parity on frontmatter types), 31.2 bug-107 + bug-247 (+ 22.6 R4), 31.3 bug-242 guard, 31.4 retire standing lint warnings, 31.5 scan-prompt per-block measure + cut (Q27 = b), 31.6 bug-251 one wikilink resolver (Q30 = a); task specs in flight on Fable: 31.5/31.3/31.4 (branch `spec-plan31a`, decisions D1-D10), 31.1/31.6/31.2 (branch `spec-plan31b`, D11+); then ch-bsd spec review; approved on bsd MEH-only GO (L125) | specs in flight | `workflow/plans/plan-31-pre-mod-loose-ends.md` | 31.1 after 0.84.0; 31.2 after 29.5 |
{#plans-replaced-table}

### Freeze list as it stood before the rewrite {#freeze-2026-11-15}

Item 1 is finished: 0.84.0 replaced 0.83.1 (L119), released `cab0a7d`, deployed `fb6e339`, live
AC-6 recount 0 at `4c6a0c6`. Item 2's order was replaced by L118, and its duckdb step is done.
Item 4 gained bug-255 and 31.6 (Q30 = a). Item 5 was amended by L128 (plan-10's dedupe moved
post-mod; G22, G30, G32 and the `rel:` probe admitted; the plan-24 freshness revision added as
the last step). Item 3 is shown for context.

1. **0.83.1** (bug-241 + bug-240 + L112/L114) — ship, deploy, live AC-6 recount.
2. **Plan-29** code quality (29.1 → 29.4 → 29.5 → 29.2 ∥ 29.3 → 29.6), then `.venv-eval` duckdb 1.5.3.
3. **Plan-30** adjacency + bitmap materialisation (30.0-30.5), plus **30.6** edge-type value
   measurement ([[plan-30-materialisation#t6]]).
4. **Plan-31** pre-mod loose ends ([[plan-31-pre-mod-loose-ends]]): 31.1 bug-244, 31.2 bug-107 +
   bug-247, 31.3 the bug-242 ledger-anchor guard, 31.4 retire the standing lint warnings, 31.5 the
   scan-prompt injection measured per block, then cut and tightened (Q27 = b).
5. **From the L106 queue** (the user, Q28 = a, 2026-11-15; [[freeze-triage-2026-11-15]]):
   T2 memory organisation (26.5 → 26.7 → 26.6 R3 → 26.8 → 26.9 ∥ plan-27); bug-218; 25.2, 25.3,
   10.3; T4 bounded writes (bug-185 → 23.2 → 23.1 → 23.3 ∥ 23.5); T3 injection dedup (10.5 → 10.6
   → 10.4 → 10.2; 21.2 → 21.4), after 31.5; 21.5 phase M; 22.6 R4 folded into 31.2.

### Sequence rationale (the whole `#sequence` section) {#sequence}

Removed whole: the order now lives in the POP's `#queue`.

**Override (user, 2026-11-08, session 8d9a255f): cliquedb's field-report bugs land BEFORE the mod transition.** Order: (1) close task 3.7 (merge + release); (2) bug-164 (recall hook overflow), bug-165 (bare-ack prompt noise), bug-166 (STM junk topics + stale helix line), bug-167 (BRE `\|`) — the consumer-visible defects in [[bug_registry#registry]], cliquedb's priority order; (3) only then plan-24 (spec r7 → approval → 24.0/24.1). Why: the shell-hook surface is what every project runs today, and the mod is weeks out; fixing what the consumer sees now is not throwaway, since recall budgeting and prompt gating are verb-side logic the mod reuses. {#override-2026-11-08}

**Amended (user, 2026-11-08, same session): the memory-layer fixes land BEFORE the cliquedb bugs.** Order: (1) task 3.7; (2) plan-26 memory-layer organisation (save-states into a `savestates/` subfolder — writer + reader + migration, since `handoff.py` writes and globs the top level; compile subject-label quality; MEMORY.md grouped by subject; organisation by TYPE/lifecycle in folders, topic by derived subjects, never topic folders); (3) plan-27 roll plan-26 out to every other project's memory dir (18 non-empty dirs, 130 save-states; cliquedb last, at its session boundary); (4) plan-25 cliquedb bugs 164-167; (5) plan-24. {#override-2026-11-08b}

**Goal set (user, 2026-11-09, session 7aea273d): finish every item ahead of plan-24, and bug-177 + bug-179 join the queue.** Before plan-24 starts: (1) task 3.7 merged + released; (2) bug-178 (one bulk-write helper) merged + released, one version bump per merge, serialised with 3.7; (3) plan-26 built + deployed + 26.8 rollout; (4) plan-27; (5) plan-25 (spec review r3 started now, in parallel, because it is the critical path); (6) **bug-177** (hook writes blocked behind a long writer) — owned by plan-23 task 23.1, so 23.1 is pulled forward into this queue, with **bug-182** (the scan-prompt overrun; measure first) as part of bug-177's original scope; (7) **bug-179** (lint accepts several anchors per line, the store ingester registers only the first) — needs a short task spec: make lint and ingester agree. Steps the plans gate on the user stay gated: 26.8 MEMORY-RULES apply, 27.2a conversions, every announced live step, cliquedb at its acknowledged session boundary. {#goal-2026-11-09}

**Progress 2026-11-09 (evening):** (1) task 3.7 merged `91ddbe0` (ch-bsd r7 GO), released + deployed 0.81.0; (2) bug-178 merged `76ec748`, released + deployed 0.81.1 (hub + 8 daemons on 0.81.1, hooks in sync). bug-183 fixed (memory lint hook wired, user-level). bug-179 approved `26d36f4` (viascope consent) and GREEN in littlebig clones (gmd `efb514a`, refmatrix `44c6196`); landing (viascope split → upstream → merge) waits on its ch-bsd audit. New rows: bug-187 (fixed), bug-188 (float knobs), bug-189 (streak-end test). Next: plan-26 → bug-185 → 23.2 → 23.1 → 23.3 ∥ 23.5; plan-25 and plan-27 after their dependencies. {#goal-2026-11-09-progress}

**Decisions + progress 2026-11-10 (user, session 7aea273d):** (a) AC-6 fixture: merge now — `ac6-fixture` merged `69ecb21`, bug-156 fixed, AC-6 now RED only on bug-196 (renumbered from the branch's colliding bug-137); (b) `rmx_bus_pub`: split the field — new `about` message field, `project` transport-only under 25.1 R10 (`d6e0ec1`); (c) bug-191: merge the branch — `wave0-spec-reviews` merged `9eaf00b`, lint gate exit 0; (d) littlebig: the 23 merged clones go (user runs the script), store-copy scratch kept. 26.1 follow-up merged `25af9ca` (ch-bsd r4 GO); bug-193 fixed, its restore is bug-195 (in build); 26.6 r1 remedy in build. {#goal-2026-11-10-progress}

**Scope decisions (user, 2026-11-09, session 7aea273d):** (a) plan-23 tasks **23.3** (sync yields between files) and **23.5** (read-path and holder bounds, incl. the `memory_compile` hold item R9) join the pre-plan-24 goal — they bound the lock holders bug-177's queue only works around, together with **bug-185's bulk GMD ingest** (the measured holder; added 2026-11-09 by [[bsd-plan23-3-5-freshness-62a2465#b1]]); (b) **bug-181** (MCP `project=` that resolves nothing silently reads the cwd store) is folded into plan-25 task **25.1**, which removes plan-25's last approval blocker. {#goal-2026-11-09-scope}

**Queued re-measure (plan-25 r4, 2026-11-09):** bug-174 / task 25.5 R3 re-runs when `rmx telemetry --agent-usage` shows ≥ 30 `bre_meta_literal` grep rows (M ≥ 30) or on 2026-12-31, whichever comes first; the 25.5 R4 bands decide again, unchanged ([[plan-25-cliquedb-field-report#rev-round-4]]). {#queue-bug174-remeasure}

**Queued exploration (user, 2026-11-13, session f0521bff): the handhold outcome experiment** ([[exploration-handhold-outcome-experiment]]) runs after the user's decision on task 21.5. The 21.5 measurements (R12 pilot, term/clique, relation gaps; all provisional, ch-bsd pending) showed ambient push injection is mostly unused and topical overlap is not use; the experiment tests the charter itself — push / boundary / pull arms against pre-registered orientation-cost, churn, re-derivation and repeated-mistake outcomes. bug-216 (GMD `rel:` edges missing from `entity_links`) lands before its arm-A baseline. {#queue-handhold-outcome-experiment}

**Current order (2026-10-19, user-requested fold of plans 1-15): [[plan-review-2026-10-14#t11-folded-waves]], amending [[plan-review-2026-10-14#t10-waves]] for EVERY wave** (bug-105 hotfix first; Wave 1 starts with 23.0 ∥ 23.4). Superseded: (2026-10-07) [[plan-review-2026-10-07#order]]. The numbered rationale below is historical.


1. **deploy-runtime** first — until `rmx` runs the deploy tree, every later "deploy + verify" step is fiction.
2. **hooks-reproducible** — the user's first irritation; also decides how PreCompact calls save-state (feeds plan 5).
3. **verbs-parity** — the user's second irritation; moves recall semantics where both surfaces reach them.
4. **daemon-resilience** — a read must never kill the daemon; in-band index repair; watchdog grace; orderly loop.
5. **memory-bridge-complete** — coverage, overlap, real tests (depends on plan 2's PreCompact decision).
6. **deferrals-docs-benchmark** — cleanup chunk: stale prose, generated docs, artifact, registries, perma-red test.
7. **longmemeval** — an outside-comparable memory-retrieval number on the production path; also the
   measuring stick for plan 8, which is otherwise unfalsifiable.
8. **derived-coverage-notes** (briefs) — the store says what it has; nothing says what it lacks. Depends on 7 for
   evidence that a coverage note predicts a retrieval miss.
9. **context-cost-telemetry** — rmx measured its own retrieval quality and never its own cost. Three hooks fire
   every prompt and nothing said whether they spent 400 bytes or 40 KB of the window they were enriching.
10. **injection-dedup** — scan-prompt re-pays for context the turn may already hold. Task 10.1 is a
    PRE-REGISTERED measurement that decides whether 10.2/10.3 are built at all; a result under the
    threshold ships as a negative finding, not as a lowered bar.

11. **grep-learning-measurement** — the grep→graph teach has run for weeks with its COST measured and
    its BENEFIT uninstrumented: `query.log` never recorded whether the index or the tool floor answered a
    call. Task 14.1 ships that field, 14.2/14.3 give the loop an off switch the hook also obeys, and 14.4
    replays the real workload against both arms against a PRE-REGISTERED threshold.

12. **derive-impact-tracking** — bug-039's stamp says WHICH CODE built the graph; it cannot say what a
    change DID. One hash over three whole modules flagged this store because a READ method was added to
    `store.py`, the stamp upserts so there is no history to compare against, and nothing records what a
    derive produced. Per-pass hashes, an append-only history with the counts, and `rmx derive log/diff`.

Each plan ends with `@ch-bsd` over its commit range; remedy → re-review until CLEAN before the next plan starts.

### Status lifecycle wording replaced on 2026-11-15 {#status-lifecycle-2026-10}

```
drafting → approved → in-progress → completed
```

- **drafting** — being designed; no task specs yet.
- **approved** — every task has a written spec under `workflow/plans/<plan>-tasks/`; ready to build.
- **in-progress** — implementation underway.
- **completed** — done; kept in place with `status: completed` (not moved to an archive dir).

Set the stage by editing `metadata.status` in the plan's frontmatter **and** the Status column
above. Files stay put; links never rot.

### Finished work the POP never recorded (compiled 2026-11-15) {#finished-compiled-2026-11-15}

Compiled from `git log master` and rulings L1-L126, not removed text: the tasks of live plans,
and the standalone tasks and releases, that finished between 2026-11-09 and 2026-11-15. Each sha
is an ancestor of `master`.

| item | finished | evidence |
|---|---|---|
| task 3.7, the verb-it backlog | merged, released 0.81.0 | `91ddbe0`, `021f3af` |
| bug-178, one bulk-write helper | merged, released 0.81.1 | `76ec748` |
| bug-179, lint and ingester agree on anchors | merged, released 0.81.2 | `aea4098` |
| 26.0 ADR-0005; 26.1; 26.2; 26.3; 26.4 | merged | `61b3bde`; `9b2c4ac` + `25af9ca`; `05164ce` + `078c951`; `fdc6359`; `0c74872` |
| 26.6 compile subject hygiene, less its R3 residual | merged | `8a867bc` |
| bug-195, the cut-hook repair | merged | `102524d` |
| release 0.82.0 | plan-26's 26.1-26.3 and 26.6; bug-195, 197-200; user-level `/save-state` and `/recall-state` | `9432b83` |
| 21.1's AC-6 fixture | merged | `69ecb21` |
| 25.1, the recall-hook byte budget (it realizes 19.1 and 19.5 R1; closes bug-164 and bug-181) | merged | `d44e359`, `d1be40a` |
| bug-212, worktree hooks and the tracked-catalog guard | merged | `cc061f4` |
| bug-216, GMD rule docs in the graph, with bug-227 | merged | `7aed8df` |
| bug-225, the handoff trunk from `origin/HEAD` | merged | `3e37fb3` |
| release 0.83.0 | deployed fleet-wide (L77) | `af83867` |
| bug-241 and bug-240, with L112 and L114; the scan-prompt order, 9.5k budget and STM gate (L120) | merged | `b11e5e5`, `62cafc9` |
| release 0.84.0 (it replaced the undeployed 0.83.1, L119) | released, deployed; the live AC-6 recount is 0 | `cab0a7d`, `fb6e339`, `4c6a0c6` |
| `.venv-eval` duckdb 1.5.3 (store review D5) | done; the venv imports 1.5.3 | L106 |
| plan-29's specs; plan-30's specs | merged, approved | `33d85bb` + `d227cc6`, `b12724d`; `df75516` |
| 29.4 stage 0, the serial durations run | merged | `3b930e4`; L121 |
| the T0 spec with its 29.4 fold | merged | `0e55687`; L122, L123 |
| 29.4 stage 1, T0.1': the skip gate and the one memdir resolver (bug-215 R1.5, bug-155's residual, bug-254) | merged | `a0c7560`; L124, L126 |
| the six frozen spec branches | merged as they stand | `3be7676`, `327703d`, `e2010bd`, `b1be2e4`, `0a40f4b`, `88c2900` |
| task 29.7, the learned-row re-key | dropped (L115); branch `spec-29-7-learned-rekey` at `a63d120` stays unmerged | L115 |
| 25.4 and 25.5 | closed as superseded by 16.5 | L32, L42 |
{#finished-compiled-table}

### Bookkeeping done: POP rewrite and archive (2026-11-15) {#archive-2026-11-15}

The user, 2026-11-15: "the source of truth must be the POP" and "archive any other doc that acts
as an alternate source of truth". In flight: the POP rewrite (corrected `#plans` rows; one
`plan-of-plans#queue` to mod start), compiled by arch-triage from the agreed decisions. When it lands, in the
same commit: `plan-review-2026-10-07`, `plan-review-2026-10-14`, [[plan-review-2026-11-13]], the
three `plan-review-fable-2026-11-14-*` reviews, both freeze triages, triage-3 and
`workflow-practice-review-2026-11-15` move to `workflow/archive/` with an ARCHIVED banner and
`status: archived` (ids unchanged, so links hold); `handoff.md`'s queue becomes a pointer to
`plan-of-plans#queue`. [[open-questions]] (Q1-Q22, history) is archived with them. Rulings, decisions and questions live in [[plan-of-plans#ledgers]]. {#archive-2026-11-15-body}

Done in one commit: the POP body replaced by arch-triage's draft (`triage-3` `d3550c9`, against `8b80f1d`), the removed content appended above, 16 files' links to the removed `#sequence` anchors repointed here, the eleven docs moved to `workflow/archive/` with a banner and `status: archived`, and `handoff.md`'s queue replaced by a pointer.

### Pending-status rows applied by the bookkeeping pass (2026-11-15) {#pending-status-applied-2026-11-15}

Rows of the POP's `#pending-status` table whose edit is made (branch `bookkeeping-1115`), as they
stood. Two more rows were applied in part and stay in the POP for the part that is left: plan-31's
wording (its status waits for its spec merge), and the decision-row citations (eleven files cite
their row; plan-24's and 26.5's wait).

| file | edit | evidence |
|---|---|---|
| `plan-3-verbs-parity.md`; `task-3.7-verb-it-backlog.md` | `status: in-progress` → `completed` | D-Q6; `91ddbe0` |
| `plan-9-context-cost-telemetry.md` | `status: in-progress` → `completed` | D-Q6 |
| `task-25.1-recall-hook-byte-budget.md` | `status: pending` → `completed` | `d44e359`, `d1be40a`; 0.83.0 `af83867` |
| `task-26.1-…`, `task-26.4-…` | `status: pending` → `completed` | `9b2c4ac` + `25af9ca`; `0c74872` |
| `task-19.1-pack-recall-under-budget.md` | `status: pending` → `completed` (its own text: "nothing left to build here") | L14; `d44e359` |
| `plan-21-…`, `plan-25-…`, `plan-26-…`, `plan-29-…` | `status: approved` → `in-progress`; plan-21's body "Drafting" and plan-25's "not started" removed | `535231e`; `d44e359`; `9432b83`; `3b930e4` |
| `task-29.4-suite-health.md`; `task-t0-suite-trust-sweep.md` | `status` → `in-progress`; plan-29 `#decisions-next` "Next: 29.1" → "Next: 29.4 stage 2" | `3b930e4`, `a0c7560`; L118 |
| `task-bug178-…`, `task-bug179-…`, `task-bug195-…`, `task-bug216-rule-docs-in-graph.md` | `status: approved` → `completed` | `76ec748`, `aea4098`, `102524d`, `7aed8df` |
| `task-bug216-rule-docs-in-graph.md` | add the order edge to bug-185 and L50's wording, owed at the bug-216 merge | L57 M6, L62 M4 |
| `task-bug218-…`, `task-dq1-…` | body "Status: Drafting" → "Approved" (frontmatter already says so); the dq1 spec's queue slot: after plan-30 release C | L69, L74, L128 |
| `task-7.4-plan-7-longmemeval.md` | status note "dense blocked on bug-030" → "the dense re-run is T0.6" | bug-030 fixed 2026-09-16 |
| `task-compaction-as-handoff.md`, `task-agent-start-context.md`, `task-linked-readonly-store.md` | "queued right after 0.83.0" → "post-mod" | Q28 = a; L128 |
| `task-10.2-…`, `task-10.4-…`, `task-10.5-…`, `task-10.6-…` | header line: post-mod with 25.1b | L128 |
{#pending-status-applied-table}

### Pending status applied by the lead (2026-11-15) {#pending-status-lead-2026-11-15}

| file | edit | evidence | why it stayed |
|---|---|---|---|
| `.claude/PROJECT_PROFILE.md` `#corpus` | "unverified until a Claude Code restart" → verified: spawned agents are offered the read-only MCP tools | **stays:** an agent-instruction file that `CLAUDE.md` imports; left for the lead or the user to edit, not a subagent | [[plan-review-fable-2026-11-14-queue#st-3]] |
{#pending-status-lead-2026-11-15-table}

Applied: `.claude/PROJECT_PROFILE.md` `#corpus` now states the read-only MCP tools are offered to spawned agents (verified 2026-11-14, L85).

### Question withdrawn (Q39) {#q39}

| id | asked | question | options (lead's recommendation first) | status |
|---|---|---|---|---|
| Q39 | 2026-11-15 | bug-203 (`rmx sync -i` reaches the read replica when a daemon is up) is not on the freeze line; 31.2 rewrites what `sync -i` does, and arch-31b wrote the routing fix in (AC-14). Admit it into 31.2? | (a) admit it into 31.2 (recommended: the same lines are rewritten anyway; leaving it means re-opening them after the mod); (b) cut it from 31.2, bug-203 stays post-mod | **withdrawn** by the lead (L136): bug-203 is already pre-mod via T4 (queue step 13); which step routes `sync -i` is sequencing, ruled: 31.2 |
{#q39-table}

### Withdrawn queue note (R1.1 contingency, L140) {#r1-1-withdrawn}

**Contingent:** if 31.5's live cost check (AC-0.17) fails after R1, the cheaper capture path ships as **R1.1**, a major (it changes a hook's output), before R2 opens. {#r1-1-withdrawn-body}

### Questions answered and applied (Q38, Q40, Q41) {#q38-q41}

| id | asked | question | options (lead's recommendation first) | status |
|---|---|---|---|---|
| Q38 | 2026-11-15 | plan-31 D14 says "migrate them if they can be resolved, if not, delete them". What does "resolved" mean for the 30,131 orphaned learned rows? (Split re-measured by arch-31b after the 2026-11-15 archive commit `903f7f5`, which moved two review docs that 254 orphans name; the dry run at the store event binds, since the split follows the tree.) | (a) **matched to the current entity** (concept is a `query/` concept, exactly one same-named entity of the learner's kind, file on disk): **29,824 re-attached, 307 deleted** with a manifest (11 concept gone, 42 no entity, 254 file gone); at read time only rows whose recorded line still holds the pattern are served (recommended: a learned row is a query-to-file association; a moved line is a serve-time question the line check already answers); (b) **the recorded line still holds the pattern**: **12,647 re-attached** (latest run) (9,634 literal, 3,011 regex only), **17,486 deleted**. Under either reading, a file that is archived or moved takes its learned rows to the manifest. ch-bsd (bsd-31b, 2026-11-15): (a) is testable as written; (b) is not yet (it relies on `verify_evidence_rows`, whose regex and case flags are undefined for a stored learned row) | **(a)** (the user, 2026-11-15: "q38-q41 a"); applied by L162 |
| Q40 | 2026-11-15 | Three admitted tasks edit `ingest_gmd.py` / `ingest.py` (pass files): 31.1, 31.6 and 26.5. Each release flips derive verdicts fleet-wide, and each store then needs a forced reingest (refmatrix ≈ 63 min at 0.84.0, bug-252), a store-on-disk change needing your go. How should the reingests be windowed? | (a) **one window**: land 31.1, 31.6 and 26.5 first, then one forced reingest per store — refmatrix at 26.8, the rest in their plan-27 windows (recommended: one reingest per store instead of up to three; 31.6's re-bind and the 114-edge cleanup ride the same window); (b) a reingest after each release; (c) decide per release when it ships | **(a)** (the user, 2026-11-15: "q38-q41 a"); applied by L162 |
| Q41 | 2026-11-15 | The two freshness revisions that ran past the lead's stop found the frozen specs not fully actionable: about ten T2 ACs cannot be built as written on master (green at base, unreachable, a forbidden tree walk, 176 dangling links), and bug-218 holds ten traps for a RED author ([[agent-brief-t2-red-notes]], [[agent-brief-bug218-red-notes]]). t4, t3a and t3b are likely the same. How should a frozen track be readied? | (a) **just in time**: when a track reaches the head of the queue, an architect re-read plus a ch-bsd confirm-lite right before its RED (about an hour per track, only when it is next) (recommended); (b) build as they stand, the RED author reconciling as it goes (the user's 2026-11-15 call) | **(a)** (the user, 2026-11-15: "q38-q41 a"); applied by L162 |
{#q38-q41-table}

### Question answered and applied (Q42) {#q42}

| id | asked | question | options (lead's recommendation first) | status |
|---|---|---|---|---|
| Q42 | 2026-11-15 | T0.3's spec proves a flake fix only by **45 consecutive passes** on the harness at the reproducer's level ([[task-t0-suite-trust-sweep#t0-3-band-fixed]]). green-t03 was briefed to run one confirm trial per row instead, and its summary flags the 45-pass bands for bug-228 and bug-231 as not run. At ~77 s a trial, that is ~1 h of serial lane time per row per attempt (~2 h for both, up to ~4 h if a second attempt is needed). Run them before T0.3 merges? | (d) **run each row to the count its own reproducer needs** (the 95% Clopper-Pearson lower bound of its observed rate: bug-228 5/9 → 0.212 → **13** straight passes; bug-231 6/9 → 0.299 → **9**; ~30 min of lane in all), after ch-bsd's review and before the merge; the rows close `fixed` only on a clean run; the spec's 45 stays as the ceiling for a 3/10 reproducer (recommended, revised after the user asked what 45 buys); (a) run both 45-pass bands as the spec says (~2 h); (b) merge on the one confirm trial each, rows set `deferred: diagnosed-loud` until the bands run later; (c) amend the spec to one confirm trial | **(c)** (the user, 2026-11-15: "this all seems excessive" → "make the changes"); applied by L164 |

### Questions answered and applied (Q43, Q44) {#q43-q44}

| id | asked | question | options (lead's recommendation first) | status |
|---|---|---|---|---|
| Q43 | 2026-11-15 | Act on [[test-suite-audit-2026-11-15]]? | (a) **after T0.2 and T0.3 merge (they edit the same test files), two small-fix agents:** one deletes the 7 detail-pinning source-text tests and the 2 confirmed duplicates and trims 3 assertions; one makes the waits cheap (short test-daemon shutdown, test-sized budgets keeping one real-default test each, gated small ingest job instead of 350 docs, modelsrv probe), ~60 → ~45 min release suite (recommended); (b) deletions only; (c) neither now | **(a)** (the user, 2026-11-15: "q43-a, q44-a"); applied by L168; the 49-test conversion split out as Q45 |
| Q44 | 2026-11-15 | The user: "can we drop the per-round tests" (111 files, 1,439 tests, 1,927 s = 59% of the runtime), then: "there has to be a bunch of partial overlaps … 2-4 variants of tests that could be consolidated … groupings [must] facilitate modular execution (focused testing)". Static estimate: 26 cross-file groups (69 tests), 66 same-file groups (163 tests) and 23 groups of 5+ (167 tests) share an exact call set; focused runs are blocked by `cli.py`/`store.py` (136 and 220 of 357 test files import them, [[task-29.4-suite-health#r6]]) | (a) **two steps (recommended):** (1) after T0.2/T0.3 merge: one per-test coverage run (`--cov-context=test`, ~70 min on the lane); drop tests with no unique line or branch (unless a registry row's only test); fold the 2-4 variants into parametrized tests; merge cross-file duplicates, within today's files. (2) at 29.5/29.4f: move tests into directories mirroring the split `src` layout (`tests/cli/`, `tests/store/`, `tests/daemon/` …), tier markers for the runner, and `ptest.sh --family` derives focused families from them; (b) drop all 111 files now; (c) consolidate only, no regrouping | **(a)** (the user, 2026-11-15: "q43-a, q44-a"); applied by L168 |

### Question answered and applied (Q45) {#q45}

| id | asked | question | options (lead's recommendation first) | status |
|---|---|---|---|---|
| Q45 | 2026-11-15 | Q43 (a) did not say whether to convert the **49 tests that prove busy/down behaviour against a patched `ping`/`daemon.call`** ([[test-suite-audit-2026-11-15#vs-new-rules]]) to a real busy test daemon (L167). They would then prove the behaviour; the cost is ~4-8 min of suite time | (a) **yes, as a third small-fix agent in the T1 row, worst files first** (`test_plan2_remedy.py` 8, `test_daemon_liveness.py` 3, `test_task3_7_refine.py` 3, `test_plan2_remedy_r7.py` 3 …) (recommended); (b) only new tests follow L167; (c) later, with the 29.5 regroup | **(a)** (the user, 2026-11-15: "fix the 49 too"); T1 step 4 |

### Question answered and applied (Q46) {#q46}

| id | asked | question | options (lead's recommendation first) | status |
|---|---|---|---|---|
| Q46 | 2026-11-15 | The user: "we need a setup that supports running multiple test daemons". Today 93 test files start a daemon their own way, 17 via a `daemon start` subprocess, ~15 local daemon fixtures, one shared class (`SandboxDaemon` in `task21_1_support.py`), and no held-writer / busy fixture (23.2's was never built); the machine-wide lane runs one test process at a time | (a) **both, in order (recommended):** **T0.9a, R0 probe** (one short task): build a Linux arm64 image with the Python 3.14 venv and the model cache baked in; run ~5 portable files; record wheel availability (duckdb, lance, pyroaring, torch), wall time vs host. If it passes: **T0.9b, the Docker lane**: `scripts/ptest-docker.sh` runs N containers (start 3), each on a copy of the clone (no live mount, no host `~/.refmatrix`, no host sockets), sharding the portable files; the 55 macOS files, the timing tier and the dev-tree tier stay on the host lane; the release gate stays on the macOS host. **T0.9c, the test-daemon kit** (`tests/daemons.py` `daemon_factory` with `hold_writer()`, `saturate()`, `stall()`, `stop()`/`kill()`, `wait_ready()`, `wait_models_warm()`; one shared model worker per process), which T1 step 4 and the 93 ad-hoc starters converge on. CLAUDE.md and the profile's "no container" lines are updated. After 29.4 stage 2; a large change (one-page spec, RED/GREEN, one bsd pass); (b) the kit plus a multi-slot host lane, no Docker; (c) Docker only for agents' verify runs, no kit; (d) later | **(a)**, with the macOS lane on the Mac mini (the user, 2026-11-15: "q46 yes - plus the mac mini is up"); applied by L170 |

### Question answered and applied (Q47) {#q47}

| id | asked | question | options (lead's recommendation first) | status |
|---|---|---|---|---|
| Q47 | 2026-11-15 | The user: "does pinning the venv make sense". There is no lock file; `pyproject.toml` has only floors (`duckdb>=1.5.3`, `pylance>=0.20`), and an unpinned install on the mini took **duckdb 2.0.0 and pylance 14**, the two libraries that define the store's on-disk format. `.venv-eval` and the deploy venv already differ (click 8.3.3/8.4.1, numpy 2.4.4/2.4.6, transformers 5.8.1/5.9.0, sentence-transformers 5.5.0/5.5.1) | (d) **flexibility on purpose (recommended, revised):** `pyproject.toml` keeps its ranges, with caps only on the two storage-format libraries (`duckdb>=1.5.3,<2`, `pylance>=6,<7`); a committed `requirements.lock` *records* the deploy venv's versions; the mini's `rmxtest1`/`rmxtest2` slots and `.venv-eval` run the lock (verify runs and the release gate: a failure means a bug); `rmxtest3` is a **canary** on the latest versions the ranges allow, rebuilt weekly, whose failures are logged as upstream warnings, not release blockers; the lock is bumped when the canary is green; (a) every environment strictly on the one lock, no canary; (b) the lanes pin to `.venv-eval` (today's interim), production left as is; (c) only the storage caps | **(d)** (the user, 2026-11-15: "q47-d"); applied by L172 |

### Question answered and applied (Q48) {#q48}

| id | asked | question | options (lead's recommendation first) | status |
|---|---|---|---|---|
| Q48 | 2026-11-15 | After the isolated-user pilot (L173): move small-fix agents to isolated `rmxtest` users, keeping large changes and reviews in-process? (Asked without a Q id; entered after the answer, L174.) | (a) **yes, small fixes isolated; large changes and reviews in-process** (recommended); (b) keep all agents in-process | **(a)** (the user, 2026-11-15: "yes for the small fixes"); applied by L174 |
