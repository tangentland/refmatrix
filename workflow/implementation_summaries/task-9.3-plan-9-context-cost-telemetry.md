---
gmd: "0.1"
id: impl-task-9.3-plan-9-context-cost-telemetry
title: "Task 9.3: rmx telemetry --context, and a hook budget that first had to learn what a prompt is"
tags: [implementation-summary, plan-9, telemetry, context-cost, retroactive]
metadata:
  node_type: implementation-summary
  status: complete
  plan: plan-9-context-cost-telemetry
  task: task-9.3-plan-9-context-cost-telemetry
  created: 2026-10-19
---

# Task 9.3: `rmx telemetry --context`, and a hook budget that first had to learn what a prompt is {#root}

rel: implements -> [[task-9.3-plan-9-context-cost-telemetry]]
rel: part-of -> [[plan-9-context-cost-telemetry]]
rel: depends-on -> [[impl-task-9.2-plan-9-context-cost-telemetry]]
rel: related-to -> [[task-9-summary#report]]
rel: evidence-for -> [[bsd-plan8-9-10-r5-e0b7df6#s-6-r5]]
rel: related-to -> [[bsd-plan7-10-r1-399d0a3#b-7]]
rel: related-to -> [[plan-review-2026-10-14#t11-folded-waves]]

## Written retroactively {#retroactive}

This summary was written on 2026-10-19 in the W1-d bookkeeping sweep
([[plan-review-2026-10-14#t11-folded-waves]]). The task spec's `#done` names this exact path, and
r5 `#s-6-r5` reported it absent. The plan-wide summary `task-9-summary` covered 9.3 in its
`#report` and `#verified` sections. Sources: commit `4ae41ce`, remedy commit `9cb6c25`, and the
plans 7-10 ch-bsd ledgers r1-r5. Values that none of them recorded are marked "not recorded".
{#retroactive-body}

## What was built {#shipped}

9.3 landed in `4ae41ce` (2026-09-15), the single commit for plan 9's tasks 9.1-9.3, merged at
`399d0a3`. There was no per-task branch. {#shipped-lead}

- **`rmx telemetry --context`** reads `cli.log` and reports per-command totals and percentiles,
  plus a per-prompt hook budget. The grouping rule is returned in the payload and printed.
  {#shipped-report}
- **A row without `out_bytes` is unknown, not free.** Legacy rows are excluded from the counted
  set and reported as `uncounted`. Folding them in as zeros would halve every figure.
  {#shipped-uncounted}
- **Commands are grouped by subcommand path, read from the click tree.** The first rule took
  `argv[:2]` and scattered `scan-prompt <prompt>` into one row per prompt. This was found on the
  live table before the commit and fixed in it. {#shipped-grouping}
- **Tests**: 10 in `tests/test_context_cost.py`. {#shipped-tests}

## The hook budget was wrong at first, and was fixed in review {#b7}

ch-bsd r1 `#b-7` (BULLSHIT): every rmx hook template exports `source == "hook"`, not just the
UserPromptSubmit hooks. So the 5 s windows mostly held `focus hook` tool-call pairs. On the real
log, 1,271 of 10,740 windows (11.8%) contained a `scan-prompt`. `9cb6c25` anchored each window on a
`scan-prompt` row, excluded windows without one, and added `anchored_on` to the payload. r2
re-measured it by replaying the live `cli.log`'s 23,662 hook rows: 10,802 windows became 1,273, p50
went from 0 to 4,370 B, and 3.0% of anchored bytes came from non-UserPromptSubmit commands. r2
closed `#b-7`. {#b7-body}

The `/dev/null` over-count and the under-count from non-rmx hooks (r1 `#s-11`) are not fixed in the
data. `f3c23b1` names both in the docstring and the payload. {#b7-caveat}

## Verification {#verification}

| gate | result | source |
|---|---|---|
| RED run | not recorded | — |
| GREEN run | not recorded as a log; 31 tests across plan 9 (commit) / 29 (plan summary) | `4ae41ce`; `task-9-summary` |
| Mutations | 6 killed for 9.3, including the spec's "fold uncounted rows in as zeros" | `task-9-summary` `#report` |
| First real-data run | this project's log: 29,458 rows, all uncounted, 0 bytes claimed | `4ae41ce` |
| Throwaway-store run | `grep` mean 13,749 B; per-prompt hook budget p50 13,752 B (~3,438 tokens est). Taken before the `#b-7` anchoring fix | `4ae41ce` |
| Live run after the fixes | `counted 6968`, `uncounted 32120`, `total_bytes 5,053,668`; budget anchored on `scan-prompt`, 139 windows, p50 14,555 B, p95 27,087 B; `grouping` and `caveat` strings present | r5 `#verified-live` |

The throwaway-store p50 and the live p50 come from different populations and different windowing
rules. Neither one is a baseline for the other. {#verification-note}

## What is still open {#open}

No r5 finding is filed against 9.3's code. r5's per-plan verdict for plan-9 reads "DIRTY (no
BULLSHIT)", and the only missing items it names are `#s-5-r5` and `#s-6-r5`. This file closes the
9.3 part of `#s-6-r5`. The plan's other open items, r5 `#m-11` (the stdout proxy's second traceback)
and `#s-5` (the Q2 proxy-overhead number), belong to task 9.2's surface. They are owned by **W1-c**
and ride task 21.1's close-out ([[plan-review-2026-10-14#t11-folded-waves]]). Plan-9 closes when
that host lands. {#open-body}

## Not verified here {#not-verified}

No RED or GREEN log for 9.3 exists in the tree. This sweep ran no tests and did not re-run `rmx
telemetry --context`. Every figure above is quoted from the commit or ledger named beside it.
{#not-verified-body}
