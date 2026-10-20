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
| 23 | plan-23-bounded-write-harness | in-progress (APPROVED 2026-10-15, d9cn; 23.0 completed in 0.79.1, master d4bf001; 23.5 gated on bug-112 merge) | yes (6) | `workflow/plans/plan-23-bounded-write-harness.md` | — |

## Sequence rationale {#sequence}

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
