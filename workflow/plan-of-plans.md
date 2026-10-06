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

| # | Plan | Status | Tasks specced? | File | Depends on |
|---|------|--------|----------------|------|------------|
| 1 | plan-1-deploy-runtime | completed | yes (3) | `workflow/plans/plan-1-deploy-runtime.md` | — |
| 2 | plan-2-hooks-reproducible | in-progress (ch-bsd r9 DIRTY; #b-1 closed by bug-025, #m-5 registered; #s-2 + #s-3 + #m-4 OPEN, re-verified 2026-10-01) | yes (3) | `workflow/plans/plan-2-hooks-reproducible.md` | plan 1 (deploy path) |
| 3 | plan-3-verbs-parity | in-progress | yes (3) | `workflow/plans/plan-3-verbs-parity.md` | plan 2 (deploy path) |
| 4 | plan-4-daemon-resilience | in-progress (ch-bsd r4 DIRTY; #b-1 closed by bug-028; #s-2 + #s-3 + #s-4 + #m-5 + #m-6 OPEN, re-verified 2026-10-01) | yes (4) | `workflow/plans/plan-4-daemon-resilience.md` | — |
| 5 | plan-5-memory-bridge-complete | completed | yes (3) | `workflow/plans/plan-5-memory-bridge-complete.md` | — |
| 6 | plan-6-deferrals-docs-benchmark | in-progress | yes (5) | `workflow/plans/plan-6-deferrals-docs-benchmark.md` | — |
| 7 | plan-7-longmemeval | in-progress (symbolic reported; dense blocked bug-030) | yes (4) | `workflow/plans/plan-7-longmemeval.md` | — |
| 8 | plan-8-derived-coverage-notes | in-progress (built; awaiting @ch-bsd) | yes (4) | `workflow/plans/plan-8-derived-coverage-notes.md` | plan 7 (measures it) |
| 9 | plan-9-context-cost-telemetry | in-progress | yes (3) | `workflow/plans/plan-9-context-cost-telemetry.md` | — |
| 10 | plan-10-injection-dedup | in-progress (negative result; awaiting BSD clean) | yes (3) | `workflow/plans/plan-10-injection-dedup.md` | plan 9 (its instrument) |
| 11 | plan-11-helix-phase2-versioned-graph | drafting (storage fork A/B undecided; the pre-registered criterion now reads B — 444 rendered helix rows, 27 sessions, 48% neighbour-role) | no | `workflow/plans/plan-11-helix-phase2-versioned-graph.md` | helix phase 1 (0.55.0) |
| 12 | plan-12-open-bug-remediation | completed (@ch-bsd CLEAN; deployed 0.72.0; bug-025 acceptance 20/20 reranked) | yes (6) | `workflow/plans/plan-12-open-bug-remediation.md` | — |
| 13 | plan-13-cross-partition-sweep | drafting (@ch-bsd r1 DIRTY 12 → revised; r2 DIRTY 17, 10 of 12 closed; gate 13.0 must return GO before any build) | yes (7) | `workflow/plans/plan-13-cross-partition-sweep.md` | — |
| 14 | plan-14-grep-learning-measurement | in-progress (all 4 tasks done; threshold NOT met — index share 18.5% -> 31.7%; bug-067 fixed, bug-068/069/070 filed; awaiting @ch-bsd + the install-hooks decision) | yes (4) | `workflow/plans/plan-14-grep-learning-measurement.md` | plan 9 (its telemetry record) |

## Sequence rationale {#sequence}

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
