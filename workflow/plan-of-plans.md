---
gmd: "0.1"
id: plan-of-plans
title: "Plan of Plans"
tags: [planning]
metadata:
  node_type: index
---

# Plan of Plans — sequenced execution order + status {#root}

**Single source of truth for what to implement next, and the status of every plan** (the user, 2026-11-15: "the source of truth must be the POP"; every state change updates this file in the same commit, [[orchestration#pop-truth]]). All plans
live in `workflow/plans/` and never move — a plan's lifecycle is tracked by the `status` field in
its GMD frontmatter (`metadata.status`), mirrored in the table below. `@ch-gap-master` keeps this
current.

## Plans {#plans}

Rows corrected 2026-10-19 (W1-d bookkeeping sweep). Where a row names a W-item, that
plan's remaining work is scheduled in the folded wave list [[plan-review-2026-10-14#t11-folded-waves]].

| # | Plan | Status | Tasks specced? | File | Depends on |
|---|------|--------|----------------|------|------------|
| 1 | plan-1-deploy-runtime | completed | yes (3) | `workflow/plans/plan-1-deploy-runtime.md` | — |
| 2 | plan-2-hooks-reproducible | in-progress (ch-bsd r9 DIRTY; #b-1 closed by bug-025, #m-5 registered; #s-2 + #s-3 + #m-4 OPEN, re-verified 2026-10-01; remaining work is W1-c: #s-3 rides 23.5, #s-2/#m-4 ride 19.1, the scan-prompt rerank observation is measured by 19.5) | yes (3) | `workflow/plans/plan-2-hooks-reproducible.md` | plan 1 (deploy path) |
| 3 | plan-3-verbs-parity | in-progress (3.1-3.3 completed: 82bbc2b, merged 8ba4799; tasks 3.4-3.6 built (W1-b) and released in 0.80.1; ch-bsd r12 at b18d7e8 MEH-only (0B/0S/3M: #m-1/#m-2 registered as deferrals riding 3.7, #m-3 = 3.7 itself); task 3.7 verb-it backlog = W2-d; plan-3 closes with 3.7 per AC-G4) | yes (7) | `workflow/plans/plan-3-verbs-parity.md` | plan 2 (deploy path) |
| 4 | plan-4-daemon-resilience | completed (W1-a: task 4.5 r4 remedy + task 4.6 r5 remedy and r6 amendment; ch-bsd r7 at 10d45e1 0 blocking, 1 MEH registered; todo G9 closed; released in 0.80.0) | yes (4) | `workflow/plans/plan-4-daemon-resilience.md` | — |
| 5 | plan-5-memory-bridge-complete | completed | yes (3) | `workflow/plans/plan-5-memory-bridge-complete.md` | — |
| 6 | plan-6-deferrals-docs-benchmark | in-progress (ch-bsd r1 DIRTY at e0b7df6, may NOT flip; remedy #b-1, #b-2, #s-1, #s-3, #m-1..#m-5 + todo G7/G8 = W2-a; r1 #m-4 docstring also listed under W1-d) | yes (5) | `workflow/plans/plan-6-deferrals-docs-benchmark.md` | — |
| 7 | plan-7-longmemeval | in-progress (symbolic reported; bug-030 fixed 2026-09-16, dense/fused re-run is W2-c; deferrals W4-a) | yes (4) | `workflow/plans/plan-7-longmemeval.md` | — |
| 8 | plan-8-derived-coverage-notes | in-progress (ch-bsd r5 may NOT flip; remedy W2-b, deferrals W3-b) | yes (4) | `workflow/plans/plan-8-derived-coverage-notes.md` | plan 7 (measures it) |
| 9 | plan-9-context-cost-telemetry | in-progress (built; ch-bsd r5 at e0b7df6: paperwork only — 9.2/9.3 summaries written in W1-d; r5 #m-11 and #s-5 ride 21.1's close-out = W1-c) | yes (3) | `workflow/plans/plan-9-context-cost-telemetry.md` | — |
| 10 | plan-10-injection-dedup | drafting (reopened 2026-11-13: 48.0% of delivered items already held; names-only dedupe of the per-prompt payloads, Q13; no non-human gate, Q10; 10.4 predicate + curator silent, Q9; 10.3 builds 19.6 R8a's marker; 10.5 replay PASSED, read-back probe to run; 19.6 block diff not used for these payloads, Q11; ch-bsd spec review next. 10.1's 2026-09 negative result is history) | yes (3) | `workflow/plans/plan-10-injection-dedup.md` | plan 9 (its instrument); 25.1 (10.2, 10.4); 19.6 R8a ([[task-19.6-phased-context-and-topic-cache#split-plan-10]]) |
| 11 | plan-11-helix-phase2-versioned-graph | superseded (user 2026-10-07: "helix's design supersedes plan 11's" — ADR-0004's helix half replaces the prolly store; never built) |
| 12 | plan-12-open-bug-remediation | completed (@ch-bsd CLEAN; deployed 0.72.0; bug-025 acceptance 20/20 reranked) | yes (6) | `workflow/plans/plan-12-open-bug-remediation.md` | — |
| 13 | plan-13-cross-partition-sweep | DORMANT (C9 re-scope corrected by d4b 2026-10-14: 21.4's gold set is code+docs only; the sessions question waits for its own gold set) | yes | `workflow/plans/plan-13-cross-partition-sweep.md` | 21.4 |
| 14 | plan-14-grep-learning-measurement | completed (plan review C10: re-measure lives in task 16.4) | yes (4) | `workflow/plans/plan-14-grep-learning-measurement.md` | — |
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
| 29 | plan-29-code-quality | in-progress 2026-11-15: 29.4 runs first (L118, Q29 a). Stage 0 (R0 durations) merged `3b930e4` (L121: 8 shards, tier (d) breach → R3). T0 spec merged `0e55687` (L122, L123). **Stage 1 T0.1' merged at this commit** (skip gate exact-reason + one memory-dir resolver; bug-155 residual, bug-254, bug-215 R1.5; ch-bsd r1 MEH-only GO, 12 mutations killed, L124, L126). Next: stage 2 (T0.2 + 29.4b ∥ T0.3 + 29.4c ∥ T0.8; bug-253 helper), then stage 3 T0.4 → T0.5, stage 4 29.4a, stage 5 T0.7 + 29.4d; then 29.1 → 29.5 → 29.2 ∥ 29.3 → 29.6. Ships in the next minor release with its full-suite gate | yes (6) | `workflow/plans/plan-29-code-quality.md` | 0.83.1 deployed (bug-241 + bug-240); `.venv-eval` duckdb 1.5.3 before any 29.4/29.5 baseline (L106) |
| 30 | plan-30-materialisation | approved 2026-11-15 (L117; D1-D3 user-decided) 2026-11-14 (plan + 6 task specs 30.0-30.5 written by ch-architect on Fable 5.2 from the bitmap-materialisation measurement report; ch-bsd spec r1 at `a169c17` DIRTY 0B/3S/5M NO-GO, all eight folded in revision round 2 per ruling L116; confirm-lite r2 at `5914997` MEH-only 0B/0S/4M GO, its four folded; plan-30 D12 accepted; fixes bug-243; plan-30 D1-D3 open for the user; three releases, release B re-derives the `pagerank` pass fleet-wide) | yes (6), in review | `workflow/plans/plan-30-materialisation.md` | plan-29 released (module split, census kit, derive digest); 30.4 also 23.0's sandbox |
| 31 | plan-31-pre-mod-loose-ends | drafting 2026-11-15 (admitted under the pre-mod freeze, [[#freeze]]); six items — 31.1 bug-244 + bug-255 (lint/ingest parity on frontmatter types), 31.2 bug-107 + bug-247 (+ 22.6 R4), 31.3 bug-242 guard, 31.4 retire standing lint warnings, 31.5 scan-prompt per-block measure + cut (Q27 = b), 31.6 bug-251 one wikilink resolver (Q30 = a); task specs in flight on Fable: 31.5/31.3/31.4 (branch `spec-plan31a`, decisions D1-D10), 31.1/31.6/31.2 (branch `spec-plan31b`, D11+); then ch-bsd spec review; approved on bsd MEH-only GO (L125) | specs in flight | `workflow/plans/plan-31-pre-mod-loose-ends.md` | 31.1 after 0.84.0; 31.2 after 29.5 |

## Pre-mod freeze (user, 2026-11-15) {#freeze}

**The freeze line.** Before the mod transition (plan-24) begins, only this work is admitted:

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

**Specs on master (2026-11-15).** The approved frozen spec branches are merged as they stand (the user: "although they are stale, they should be actionable still"): `spec-wave-t2` (26.5-26.9, plan-27) `3be7676`, `spec-wave-t4` (bug-185, plan-17/18 records) `327703d`, `spec-wave-t3b` (plan-10 10.2-10.6) `e2010bd`, `spec-wave-t3c` (21.5, plan-28 record) `b1be2e4`, `spec-wave-t56` (bug-218, 22.6 with R4; plan-16 / rest of plan-22 as post-mod records) `0a40f4b`, `spec-wave-t3a` (plan-19, 25.1b record, 25.2/25.3 inputs) at this commit. Stale citations are reconciled by RED and GREEN at build time (TDD_GOVERNANCE: stale ground truth is reconciled before the test). Every freeze item except 30.6 and plan-31 now has an approved spec on master.

**Amended by L128 (2026-11-15, Q32-Q36 = a).** Admitted: G22 (after plan-30 release C), G30 (folded into 30.6), G32 (the m1 r2-lite confirm; 25.2 and 21.5 phase M wait on it), the cross-partition `rel:` probe (26.5 needs it). Moved post-mod: plan-10's dedupe 10.5 / 10.6 / 10.4 / 10.2 (10.3 and 31.5 stay). **The last pre-mod step:** the plan-24 freshness revision to approval (evidence: 31.5, 21.5 phase M, 30.6; 24.6 takes the tool-event builder); the mod starts when it is approved. The L127 re-evaluation of every post-mod item runs after the initial mod work is finished (L129).

**The rule.** Nothing else is admitted before the mod except a bug that breaks something live
(a crash, data loss, a wrong answer on the production path, a wedge). Everything else — new ideas,
the lead's included — goes to the post-mod list below, with one line saying why it waits. A bug
found during the frozen work is logged in the registry as always; it joins the queue only if it
breaks something live, else it is marked `post-mod`. The goal the freeze serves (the user,
2026-11-15): the core concept/graph representation more useful, context succinct and relevant,
performance improved, busywork removed, loose ends tied up — "at some point I need to stop adding
things and let the work finish."

rel: depends-on -> [[plan-29-code-quality]]
rel: depends-on -> [[plan-30-materialisation]]
rel: depends-on -> [[plan-31-pre-mod-loose-ends]]
rel: depends-on -> [[orchestration]]

## Post-mod list {#post-mod}

Admitted after the mod transition, not before (each with why it waits). **Every item here is re-evaluated against the mod before it is built (L127): keep, re-spec onto the mod surface, merge, or drop. The re-evaluation runs after the initial mod work is finished (L129).**

- **Branch-aware GMD lint** (resolve links against the target branch ∪ `master`; bug-249's shape) —
  the code-span-then-wikilink workaround is cheap and rare.
- **Generated frontmatter / heading anchors** — new tooling; reduces ceremony but adds a feature.
- **A before/after node check on GMD edits** (an edit is a graph mutation) — new machinery.
- **Injection presentation work beyond plan-31 31.5** — the mod changes how context is delivered;
  tool-keyed rules are its design input ([[design-note-tool-keyed-context-2026-11-15]]).
- **bug-248** (transaction rollback leaves log events and bitmap bits) — a design change; nothing
  live is known to roll back mid-write today.
- **bug-250** (a missing path is not refused on the verb/op ingest routes) — validation; the
  daemon's ingest errors on a missing path anyway.
- **Pre-split rows / filter bitmaps** — already deferred with a trigger ([[plan-30-materialisation#deferred]]).
- **Inline term introspection (`term...`)** (the user, 2026-11-15: "the ability to inline access
  the metadata of a word/term/concept using something like adding an ellipsis… making every
  word/term introspectable (descend into its associative network)"): an ellipsis-marked prompt
  term gets the top scan-prompt tier and a fuller associative bundle (neighbours, defining docs,
  memories, depth 2 for that term only); interactive descent in the hub graph view / the mod. An
  explicit pull that replaces scan-prompt's guess at which words matter. A UX feature: the mod.
  **Extension (the user, 2026-11-15):** `w1...w2` / `w1...w2...w3` name seeds whose connecting
  subgraph to explore (a steered multi-seed walk: paths / connector set between the named terms,
  the opposite of the unconstrained degree-2 walk that retrieved ~5x worse); three terms read as
  waypoints. `..` (two dots) walks the type/instance axis instead (`is_a` / kind / instance-of:
  `function..` = instances, `Store..parse` = the instance's type or siblings). Open: telling it
  apart from prose ellipsis, Rust/Swift ranges and dotted paths (operators only when glued to
  tokens, ignored inside code spans); the gestures compile to the `rmx query` DSL, not a second
  engine.
- **From freeze-triage-3 (L128, Q32 / Q36 = a):** plan-10's dedupe 10.5 / 10.6 / 10.4 / 10.2 (needs 25.1b); 19.0's remainder with bug-100 / 103 / 104; 19.2; the frozen parts of 19.5 and 19.6; 21.3; 21.5 phase B; 21.6; 21.7; plan-20; plan-7's four W4-a deferral rows; the linked read-only store and its measurement; the `legs_ms` pair (follows 25.1b); bug-182, bug-224, bug-167 / bug-174 with their hosts (bug-182's overruns re-counted after plan-30 release C).
- **From the L106 queue (Q28 = a):** compaction-as-handoff, agent-start context, 25.1b (new hook
  features; the mod replaces the hook surface); plan-28 (paired series); 23.4, the 16.6 slice and
  plan-17 (nightly maintenance); plan-22 except 22.6 R4; plan-16 (grep shim; learning stays off
  until 31.2); plan-18 (duckdb maintenance).

## Sequence rationale {#sequence}

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

## Status lifecycle (no file moves) {#status-lifecycle}

```
drafting → approved → in-progress → completed
```

- **drafting** — being designed; no task specs yet.
- **approved** — every task has a written spec under `workflow/plans/<plan>-tasks/`; ready to build.
- **in-progress** — implementation underway.
- **completed** — done; kept in place with `status: completed` (not moved to an archive dir).

Set the stage by editing `metadata.status` in the plan's frontmatter **and** the Status column
above. Files stay put; links never rot.

## Ledgers: rulings, decisions, questions {#ledgers}

The user, 2026-11-15: "any L, D, or Q must be placed in the POP before being amended to a plan".
A ruling (`L<n>`), a plan decision (`plan-N D<n>`) or a question to the user (`Q<n>`) is entered
here first, with its state; only then is it amended into a plan, spec or task file, which cites
the row here ([[orchestration#pop-truth]]). A row that is resolved and applied is appended to
[[pop-finished]] and then deleted here, in one commit. Earlier rows: L1-L124 in
[[plan-review-2026-11-13#lead]], Q1-Q22 in [[open-questions]], Q23 on in [[pop-finished]].

### Rulings (L125 on) {#rulings}

| L | date | source | ruling | applied to |
|---|---|---|---|---|
| L125 | 2026-11-15 | the user: "for p31, once bsd is happy they are approved" | plan-31's plan and task specs are **approved on ch-bsd MEH-only GO**, the MEHs folded before the merge; no separate user approval. Their `plan-31 D<n>` decisions are entered in [[#decisions]] first and take the architect's recommendation, **except** a decision that changes a store on disk (31.2's fate for the existing orphaned learned rows; any fleet re-derive or reingest 31.6 needs), which goes to the user ([[orchestration#release]] step 4) | plan-31 row; `plan-31-pre-mod-loose-ends.md` at merge |
| L126 | 2026-11-15 | ch-bsd r1 of T0.1' (MEH-only 5, GO; [[bsd-t01-r1-fff91a8]]) | GO; mutations M1.1-M1.11 recorded by the reviewer. MEH-1: RED adds a chained-clone case run with `GIT_DIR`/`GIT_WORK_TREE` exported at an unrelated repo, plus M1.12 'drop the scrub' (must turn it red). MEH-2: the three gate-root helpers copy the resolver unconditionally, stale comment dropped. MEH-3: the mock-registry row states the current clone behaviour. MEH-4: the summary keeps `task-t0.1-skip-gate-memdir.md`; `#t0-1-files` is amended. MEH-5: anchored to stage 2, no fold now. The lead checks the fold (small MEHs, [[orchestration#task]] step 5); then merge `--no-ff` | T0.1' branch; `task-t0-suite-trust-sweep#t0-1-files` |
| L127 | 2026-11-15 | the user: "all of the post-mod feature work needs to be re-evaluated to make sure they are still relevant to the design" | Every post-mod item ([[#post-mod]], plus the post-mod plans 16, 17, 18, 22 except 22.6 R4, 28, the frozen parts of 19, 21.3 / 21.6 / 21.7, 25.1b) is re-evaluated against the mod design before any is built: each gets **keep** (as specced), **re-spec** (onto the mod's surface), **merge** (into another item or a plan-24 task) or **drop**, with a one-line reason, entered here first. It runs with the plan-24 freshness revision, because that revision fixes the design it is measured against (Q33); until then no post-mod item is scheduled | [[#post-mod]] header; plan-24 revision brief |
| L128 | 2026-11-15 | Q32-Q36 = (a) (the user, with L127) | Applied to [[#freeze]] and [[#post-mod]] in this commit: **post-mod** plan-10's dedupe 10.5 / 10.6 / 10.4 / 10.2 with 25.1b (10.3 and 31.5 stay pre-mod) (Q32); **the freeze's last step** is the plan-24 freshness revision to approval, with 31.5, 21.5 phase M and 30.6 as evidence, and the L127 re-evaluation of every post-mod item (Q33); **24.6 builds** the tool-event builder (`stm.tool_event_fields`) in that revision (Q34); **admitted** G22 (after plan-30 release C) and G30 (folded into 30.6) (Q35); **admitted** G32 and the cross-partition `rel:` probe; **post-mod** 19.0 rest (+ bug-100/103/104), 19.2, 19.5/19.6 frozen parts, 21.3, 21.5 phase B, 21.6, 21.7, plan-20, plan-7 W4-a rows, linked-readonly-store, `legs_ms`; bug-182, bug-224, bug-167/174 follow their post-mod hosts, bug-182's overruns re-counted after plan-30 release C (Q36). Source: freeze-triage-3 (arch-triage, `42f5aa0`) | [[#freeze]], [[#post-mod]]; Q32-Q36 → [[pop-finished]] |
| L129 | 2026-11-15 | the user: "the re-eval of the post-mod work can happen after the initial mod work is finished" | Amends L127 and L128's Q33 step: the plan-24 freshness revision to approval stays the **last pre-mod step**, without the post-mod re-evaluation. The L127 re-evaluation (keep / re-spec / merge / drop for every post-mod item) runs **after the initial mod work is finished**, against the mod as built; no post-mod item is built before it | [[#freeze]], [[#post-mod]] |
| L130 | 2026-11-15 | T0.8 RED (red-t08, `04a2c9b`; report `workflow/review-output/t0.8/red-report.md` on the branch) | RED accepted: one new node RED at base (`assert []`, a call in both cli.log and query.log is not counted once), the AC-6 pair the red record for R8.1. (1) The new R8.2 test also asserts the frozen fixture's per-channel counts 201 / 6 / 3 / 34 (the AC-6 tests stay untouched, R8.3). (2) The cli.log section counts only calls query.log does not hold: the spec's intent, accepted. (3) The pairing key is cwd + channel + invocation + `ts` within 1 s; no new log field (old rows stay matchable). The RED author's throwaway fix sketch was reverted (`src/` clean at `c4b44d0`) and is not given to GREEN | T0.8 branch |
{#rulings-table}

### Plan decisions {#decisions}

Open decisions first; a decided row keeps its answer and the plan anchor it was amended into.
Allocated ranges in flight: plan-31 D1-D10 (specs 31.5 D1-D6, 31.3 D7, 31.4 D8-D10; branch `spec-plan31a`),
plan-31 D11+ (specs 31.1 / 31.6 / 31.2, branch `spec-plan31b`); none entered yet.

| D | plan | decision | options (recommendation first) | state | amended into |
|---|---|---|---|---|---|
| plan-31 D14 | plan-31 (31.2) | What happens to the existing orphaned learned evidence rows (28,164 on the refmatrix store, 26%, `measurement-learned-rows-cli-store-2026-11-14`)? | — | **decided by the user, 2026-11-15:** "migrate them if they can be resolved, if not, delete them". Resolvable rows are re-attached to their current entity; the rest are deleted through the audited removal path with a manifest (never a silent drop; `feedback_decay_never_loses_knowledge`). The store write is the lead's, announced and backed up | to be amended into `task-31.2` by arch-31b |
| plan-31 D7 | plan-31 (31.3) | The 15 id-less dated bullets in six folded ledger memories | (rec) the lead appends ids to them, merged together with 31.3; alt: allow-list | **decided** by L125 (the architect's recommendation; not a store-on-disk change) | to be amended into `task-31.3` at the spec merge |
| plan-31 D8 | plan-31 (31.4) | Disposition of the four standing warning classes | (rec) all four fail the gate (`--strict`), none retired | **decided** by L125 (the architect's recommendation; not a store-on-disk change) | to be amended into `task-31.4` at the spec merge |
| plan-31 D9 | plan-31 (31.4) | `amended-by` / `superseded-by` inverse verbs on 5 older memories | (rec) drop them; add the forward edge on `project_daemon_ingest_hard_death_open` first | **decided** by L125 (the architect's recommendation; not a store-on-disk change) | to be amended into `task-31.4` at the spec merge |
| plan-31 D1 | plan-31 (31.5) | Where the injection capture is on | (rec) on by default in every store, local and bounded (64 MiB / 42 days, prompt sha256 only); alt: marker-file opt-in | **decided** by L125 (the architect's recommendation; not a store-on-disk change) | to be amended into `task-31.5` at the spec merge |
| plan-31 D2 | plan-31 (31.5) | How 'a week' is counted | (rec) 400 prompts, 6 sessions of ≥ 20, ≥ 80 per block kind; closes at 800 | **decided** by L125 (the architect's recommendation; not a store-on-disk change) | to be amended into `task-31.5` at the spec merge |
| plan-31 D3 | plan-31 (31.5) | The per-kind band action table | (rec) confirm it before the numbers; the composite's cut (`--no-composite` in the generated hook) is re-asked with the number in hand | **decided** by L125 (the architect's recommendation; not a store-on-disk change) | to be amended into `task-31.5` at the spec merge |
| plan-31 D4 | plan-31 (31.5) | What to do about `ignored` | (rec) report only; handed to 10.6 and the mod design note | **decided** by L125 (the architect's recommendation; not a store-on-disk change) | to be amended into `task-31.5` at the spec merge |
| plan-31 D5 | plan-31 (31.5) | A kind whose band is ambiguous or under-sampled | (rec) `shrink` by default; S3 ablation only on the user's go | **decided** by L125 (the architect's recommendation; not a store-on-disk change) | to be amended into `task-31.5` at the spec merge |
| plan-31 D6 | plan-31 (31.5) | The capture after 31.5 | (rec) stays on, bounded; 21.5 phase M, plan-10 and 30.6 read it | **decided** by L125 (the architect's recommendation; not a store-on-disk change) | to be amended into `task-31.5` at the spec merge |
| plan-31 D10 | plan-31 (31.4) | Changing the upstream GMD linter (`~/claude_tools/gmd`: a `--strict` flag, the `session/recall-state` enum line) and one line in the user's global `~/.claude/MEMORY-RULES.md` | (rec) yes: `--strict` upstream, opt-in, passed only by `scripts/lint-gmd.sh` | **decided by the user** (Q37 = a, 2026-11-15): `--strict` and the `session/recall-state` enum line upstream, plus one line in `~/.claude/MEMORY-RULES.md`; spec anchors `task-31.4-retire-standing-warnings#r1`, `#r3`, `#ac-4`-`#ac-6` | — |
{#decisions-table}

### Questions to the user {#questions}

Next id: **Q38**. None open. Each reply that asks anything ends with the ids still open.

| id | asked | question | options (lead's recommendation first) | status |
|---|---|---|---|---|
{#questions-table}

## Pending bookkeeping (2026-11-15) {#pending-bookkeeping}

The user, 2026-11-15: "the source of truth must be the POP" and "archive any other doc that acts
as an alternate source of truth". In flight: the POP rewrite (corrected `#plans` rows; one
`#queue` to mod start), compiled by arch-triage from the agreed decisions. When it lands, in the
same commit: `plan-review-2026-10-07`, `plan-review-2026-10-14`, [[plan-review-2026-11-13]], the
three `plan-review-fable-2026-11-14-*` reviews, both freeze triages, triage-3 and
`workflow-practice-review-2026-11-15` move to `workflow/archive/` with an ARCHIVED banner and
`status: archived` (ids unchanged, so links hold); `handoff.md`'s queue becomes a pointer to
`#queue`. [[open-questions]] (Q1-Q22, history) is archived with them. Rulings, decisions and questions live in [[#ledgers]]. {#pending-bookkeeping-body}

## Notes {#notes}

- A plan is **approved** only when every task in it has a written spec under
  `workflow/plans/<plan>-tasks/`.
- The Complete Plan Gate (see `CLAUDE.md`) still applies before implementing a multi-task plan.
- See `workflow/PLAN_GOVERNANCE.md` for staleness rules and the question-forcing gate.
