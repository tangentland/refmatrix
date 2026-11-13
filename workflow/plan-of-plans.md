---
gmd: "0.1"
id: plan-of-plans
title: "Plan of Plans"
tags: [planning]
metadata:
  node_type: index
---

# Plan of Plans — sequenced execution order + status {#root}

**Single source of truth for what to implement next, and the status of every plan.** All plans
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
| 10 | plan-10-injection-dedup | in-progress (negative result; ch-bsd r5 #b-1: measured on `--format json`, which omits the composite; re-measure after 19.6 = W3-a, plan-10 closes into 19.6) | yes (3) | `workflow/plans/plan-10-injection-dedup.md` | plan 9 (its instrument) |
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

## Notes {#notes}

- A plan is **approved** only when every task in it has a written spec under
  `workflow/plans/<plan>-tasks/`.
- The Complete Plan Gate (see `CLAUDE.md`) still applies before implementing a multi-task plan.
- See `workflow/PLAN_GOVERNANCE.md` for staleness rules and the question-forcing gate.
