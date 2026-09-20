---
gmd: "0.1"
id: impl-bug-052-telemetry-outcomes
title: "bug-052: the telemetry counted two conventions as failures"
tags: [implementation-summary, telemetry, grep, observability]
metadata:
  node_type: implementation-summary
  status: complete
  created: 2026-09-20
---

# bug-052: the telemetry counted two conventions as failures {#root}

rel: derives-from -> [[project_grep_learn_wall_and_queue]]
rel: amends -> [[impl-bug-051-stop-deadline]]
rel: reinforces -> [[feedback_no_silent_failures]]

## The defect {#defect}

`grep-replica` showed **278 "errors"** in `query.log`. 256 were `SystemExit: 1` — grep's no-match
exit, which `rmx grep` honours deliberately (`_grep_rg_fallback` prints the stderr note and exits
1) — and 22 were `BrokenPipeError`, which is a downstream `| head` closing the pipe. Real failures
were about six. `cli.log` carried the same distortion from the other side: `error_rate` was
computed as *nonzero exits / total*, so every no-match `rmx grep` counted as a failed command.
{#defect-lead}

The cost is not cosmetic. The reader who found bug-049 had to dismiss 272 rows by hand before the
30 s wall was visible in the same log. A telemetry surface whose error count is 98% convention is
a surface nobody trusts, which is the same as not having one.

## The fix {#fix}

`classify_outcome(exc_type, exc_val) -> (outcome, error)` with four outcomes —
`ok | empty | consumer-closed | error` — and `error` non-null only for the last. So a reader
counting `error` rows counts failures and nothing else, while the other two exits keep their
evidence under `outcome` rather than being dropped. {#fix-lead}

| where | change |
|---|---|
| `log_query.__exit__` | writes `outcome`; `error` only on a real failure |
| `cli_entry` | classifies both exception paths and passes `outcome` to `log_cli_invocation` |
| `summarize` | `by_outcome`; `error_count` counts failures |
| `_aggregate_cli_rows` | `error_rate` = failures/total; the old number kept, honestly named `nonzero_exit_rate`; `by_outcome` added |
| both renderers | print the outcome split, so the reclassified rows stay VISIBLE rather than quietly vanishing from the error line |

**Legacy rows are re-read, never rewritten.** `_outcome_of(row)` derives the outcome from
`error`/`exit_code` when the field is absent, so the months of rows already on disk are counted by
the same rules. Rewriting a log to make a metric look better is the thing this repo does not do.
{#legacy}

## Verified on the live store {#verified}

```
query.log total: 3556
by_outcome: {'ok': 3252, 'empty': 276, 'consumer-closed': 24, 'error': 4}
error_count (new rule): 4        error_count (old rule): 304
grep-replica: 1247 rows → ok 947, empty 276, consumer-closed 24, error 0
```

## Gates {#gates}

- RED: `workflow/review-output/pytest-bug052-red.log` — 13 failed.
- GREEN: `workflow/review-output/pytest-bug052-green.log` — 13 passed.
- Mutation: `workflow/review-output/pytest-bug052-mutation.log` — classifying `SystemExit(1)` as an
  error again kills 3 tests (the classifier, the written row, and the summary).
- Full suite: `workflow/review-output/pytest-bug052-full.log`.

## What this does NOT fix {#open}

The audit's remaining findings are untouched: **#s-2** (`_inflight_ops` keyed by op NAME) and
**#m-5** (the suite cannot run against a detached checkout of its own commit) rank next.
{#open-lead}
