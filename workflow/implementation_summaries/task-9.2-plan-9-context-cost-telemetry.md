---
gmd: "0.1"
id: impl-task-9.2-plan-9-context-cost-telemetry
title: "Task 9.2: cli.log counts what each command wrote to stdout, at one boundary"
tags: [implementation-summary, plan-9, telemetry, context-cost, retroactive]
metadata:
  node_type: implementation-summary
  status: complete
  plan: plan-9-context-cost-telemetry
  task: task-9.2-plan-9-context-cost-telemetry
  created: 2026-10-19
---

# Task 9.2: cli.log counts what each command wrote to stdout, at one boundary {#root}

rel: implements -> [[task-9.2-plan-9-context-cost-telemetry]]
rel: part-of -> [[plan-9-context-cost-telemetry]]
rel: related-to -> [[task-9-summary#bytes]]
rel: evidence-for -> [[bsd-plan8-9-10-r5-e0b7df6#s-6-r5]]
rel: related-to -> [[bsd-plan8-9-10-r5-e0b7df6#s-5-r5]]
rel: related-to -> [[bsd-plan8-9-10-r5-e0b7df6#m-11-r5]]
rel: related-to -> [[plan-review-2026-10-14#t11-folded-waves]]

## Written retroactively {#retroactive}

This summary was written on 2026-10-19 in the W1-d bookkeeping sweep
([[plan-review-2026-10-14#t11-folded-waves]]). The task spec's `#done` names this exact path, and
r5 `#s-6-r5` reported it absent. The plan-wide summary `task-9-summary` (filed as
`task-9.1-plan-9-context-cost-telemetry.md`) already covered 9.2 in its `#bytes` section; this
file exists so the path the spec names holds the record. Sources: commit `4ae41ce`, the remedy
commits named below, and the plans 7-10 ch-bsd ledgers r1-r5. Values that none of them recorded
are marked "not recorded". {#retroactive-body}

## What was built {#shipped}

All of 9.2 landed in one commit, `4ae41ce` ("feat(telemetry): measure what rmx spends of the
context window, and who asked", 2026-09-15). That commit holds plan 9's tasks 9.1-9.3 and was
merged with plans 7-10 at `399d0a3`. There was no per-task branch. {#shipped-lead}

- **`telemetry.CountingStream`** wraps `sys.stdout` in `cli_entry` while `main()` runs, and is
  restored in a `finally`. It counts once, at the stdout boundary, not once per renderer. It
  passes `isatty()`, `encoding`, `flush()` and `fileno()` through, because `rich` branches on
  ttyness and a proxy that misreported it would change the bytes it measures. {#shipped-proxy}
- **`log_cli_invocation`** gains `out_bytes` (UTF-8 bytes) and `out_tokens_est` (`out_bytes //
  4`, named `_est` so it cannot be quoted as exact). {#shipped-log}
- **Tests**: 11 in `tests/test_context_cost.py`, covering print and pre-built `rich.Console`
  counting, multi-byte, pass-through, restore on return and on `SystemExit`, legacy records, and
  best-effort counting failure. {#shipped-tests}

Remedy commits from the plans 7-10 ch-bsd rounds that touched 9.2's surface: {#shipped-remedies}

- `9cb6c25` — r1 `#s-12`: `test_a_counting_failure_does_not_fail_the_command` patched
  `CountingStream` but not `log_cli_invocation`, so test runs wrote rows into the live
  `.refmatrix/cli.log`. The commit counted 44 such rows. Patched.
- `f3c23b1` — r1 `#s-11`: the docstring had claimed `out_bytes` is exactly what the hook
  injected. It over-counts hooks that redirect stdout to `/dev/null` and misses shell hooks that
  never pass through `rmx`. Restated as "bytes this process wrote to stdout". r3 closed it as a
  restatement.
- `4f451c5` — r2 `#m-2-r2`: the same live-log leak through `log_cli_intent`. Patched.

## Verification {#verification}

| gate | result | source |
|---|---|---|
| RED run | not recorded | — |
| GREEN run | not recorded as a log; 31 tests across plan 9 (commit) / 29 (plan summary) | `4ae41ce`; `task-9-summary` |
| Mutations | 5 killed for 9.2 (`task-9-summary`); 21 across the plan (`4ae41ce`). Which mutant was the spec's "count characters instead of bytes" is not recorded | as named |
| Byte exactness | 8 real invocations, counted = actual for each (e.g. `stats` 1536/1536, `--help` 2250/2250) | r1 `#s-11` |
| Q2 micro-benchmark | 24,000 bytes over 400 writes: raw `StringIO` p50 0.012 ms, through the proxy p50 0.074 ms (+0.062 ms) | `4ae41ce` |
| Q2 on a hook command | measured by the r5 auditor, not by the task — see below | r5 `#s-5-r5` |

The plan-wide counts disagree: 31 tests in `4ae41ce` against 29 in `task-9-summary`, and 21
mutants against the 5 + 5 + 6 = 16 in the summary's per-task lines. Both are quoted; this sweep
did not recount them. {#verification-discrepancy}

**Q2, before and after on a hook command.** The spec asked for "a before/after timing of a
representative hook command". `4ae41ce` measured the proxy against an in-memory `StringIO`, which
is not that. r5 `#s-5-r5` then took the hook-command measurement itself: `cli_entry` with the real
`CountingStream` vs a pass-through subclass, on `scan-prompt --max-tokens 2000 --composite-every
1`, deployed interpreter, live store, 28 runs alternating, under load average 3.69: {#q2}

```
proxy ON  : n=7 median=1308.3ms  mean=1329.7  min=1297.9  max=1387.1
proxy OFF : n=7 median=1350.0ms  mean=1351.8  min=1285.7  max=1440.7
proxy ON  : n=7 median=1341.4ms  mean=1363.7  min=1314.3  max=1465.5
proxy OFF : n=7 median=1357.1ms  mean=1361.5  min=1334.4  max=1412.4
```

The auditor read this as overhead below run-to-run noise on a 1.3 s command: |Δ| < 50 ms, sign
indeterminate. The table is the auditor's measurement, quoted here. The task did not take it.
{#q2-attribution}

## What is still open {#open}

- **r5 `#s-5-r5` (SKETCHY)** — "plan-9 Q2 required the proxy overhead to be measured and
  recorded; it never was." The auditor's number is now recorded above. The wave plan still lists
  the Q2 proxy-overhead number as open. {#open-s5}
- **r5 `#m-11-r5` (MEH)** — the stdout proxy adds a second stderr traceback when the consumer
  closes (`BrokenPipeError` from `CountingStream.flush` while the object is being finalized,
  naming `telemetry.py`). Also from that finding: `REFMATRIX_NO_TELEMETRY=1` gates only the log
  write, and the proxy is installed regardless. The proposed fix is a `close()` override that
  swallows `BrokenPipeError`, plus one docstring sentence. {#open-m11}
- **r5 `#s-6-r5`** — the missing summary. This file closes the 9.2 part. {#open-s6}

**Owner: W1-c.** [[plan-review-2026-10-14#t11-folded-waves]] places plan-9 r5 `#m-11` and `#s-5`
on task 21.1's close-out, and plan-9 closes when that host lands. {#open-owner}

## Not verified here {#not-verified}

No RED or GREEN log for 9.2 exists in the tree. This sweep ran no tests and did not re-run either
Q2 measurement.
{#not-verified-body}
