---
gmd: "0.1"
id: task-9-summary
title: "Plan 9 summary: context cost measured, and who asked recorded"
tags: [implementation-summary, plan-9]
metadata:
  node_type: summary
  task: task-9.1-plan-9-context-cost-telemetry
  created: 2026-09-15
---

# Plan 9 summary (tasks 9.1, 9.2, 9.3) {#root}

rel: realizes -> [[task-9.1-plan-9-context-cost-telemetry]]
rel: realizes -> [[task-9.2-plan-9-context-cost-telemetry]]
rel: realizes -> [[task-9.3-plan-9-context-cost-telemetry]]
rel: part-of -> [[plan-9-context-cost-telemetry]]

## 9.1 — `query.log` records WHO asked {#invocation}

`log_query.__exit__` now writes `invocation` from the existing
`telemetry.invocation_source()`. The classifier was already correct and already
used by `cli.log`; the field was simply never on the query record, which is what
stopped the `brief/unanswered` gate.

`invocation` is a new key, deliberately not `source`: in `query.log` `source`
means the SURFACE (`scan-prompt`, `grep-replica`), in `cli.log` it means the
FORM. A mutation that overloads `source` with the form is killed by a test.

`summarize` gains `by_invocation` and `zero_by_invocation` — the exact slice the
failed gate needed. 2,527 rows predate the field and read as `"unknown"`.

10 tests, 5 mutants killed.

## 9.2 — `cli.log` records what it SPENT {#bytes}

`telemetry.CountingStream` wraps `sys.stdout` in `cli_entry` for the duration of
`main()`; `log_cli_invocation` gains `out_bytes` and `out_tokens_est`.

One wrapper, not N renderers. A hook captures this process's stdout and injects
exactly those bytes, so the count is the real payload rather than an estimate,
covers every command uniformly, and has one copy —
[[feedback_reuse_shared_stoplist]] is the record of what N copies costs.
Transparency is load-bearing: `rich.Console` branches on `isatty()`, so a proxy
that misreported it would change the very bytes it measures.

**Q2 gate — overhead measured, not asserted.** 24,000 bytes across 400 writes:
raw `StringIO` p50 **0.012 ms**, through the proxy p50 **0.074 ms** — a delta of
**+0.062 ms**. The relative figure (517%) is against an in-memory buffer and is
the wrong denominator; real stdout is a pipe, and the always-on hooks are
measured in SECONDS (`memory recall --stdin-json` p50 20.0 s, bsd-plan2-r5 #b-1).
62 µs on a multi-second command. Stated because
[[impression_bsd_cost_measured_idle]] is the record of a "0.13 s" claim that was
55 s live.

11 tests, 5 mutants killed.

## 9.3 — `rmx telemetry --context` {#report}

Per-command totals and percentiles, plus the **per-prompt hook budget**: hook
rows grouped into `--window` second buckets, one bucket ≈ one prompt's hook
fan-out. The grouping rule is returned in the payload and printed, because it is
a modelling choice and a reader must not have to infer it.

**A row without `out_bytes` is UNKNOWN, not free.** Legacy rows are excluded from
the counted set and reported as `uncounted`; folding them in as zeros would halve
every figure and make the surface look cheap. A mutant that does exactly that is
killed.

10 tests, 6 mutants killed (29 tests across the plan).

## Verified on real data {#verified}

Against this project's own log: **29,458 rows, all uncounted, 0 bytes claimed** —
the guard refusing to invent a number from pre-field history, which is the
correct output.

Against a throwaway store exercising the hook commands:

| command | n | total | mean |
|---|---:|---:|---:|
| `grep` | 3 | 41,247 | **13,749** |
| `telemetry` | 1 | 2,234 | 2,234 |
| `stats` | 1 | 1,451 | 1,451 |
| `context` | 1 | 57 | 57 |
| `memory recall` | 3 | 9 | 3 |
| `scan-prompt` | 3 | 0 | 0 |

Per-prompt hook budget: p50 **13,752 B (~3,438 tokens est)**.

`rmx grep` is the dominant context consumer by an order of magnitude, and the
`grep-rewrite-guard` hook makes it always-on. That is a finding this plan exists
to have produced; it is NOT yet a finding about the live store, because these
numbers come from a small throwaway corpus. The live figure arrives once the
deploy tree carries this code.

## Two defects found while verifying {#defects}

**The dev console script bypassed `cli_entry` entirely** (bug-029).
`.venv-eval/bin/rmx` called `refmatrix.cli:main` while `pyproject` declares
`refmatrix.cli:cli_entry` and the deploy script uses it. So the dev binary has
never written `cli.log`, and any dev-tree verification of CLI telemetry or the
fork-safety re-exec was silently invalid. Repaired by rewriting the script (not a
pip reinstall — [[reference_mixed_abi_python_tree]] records 19 phantom failures
from reinstalling under this tree).

**My own first grouping rule was wrong.** `_cmd` took `argv[:2]`, so
`scan-prompt <the user's whole prompt>` became a distinct command per prompt —
the highest-volume surface in the product scattered into rows of one, with
percentiles over samples of one. The live table showed it immediately. Now the
group set is read from the click tree itself, so a new subcommand cannot
reintroduce it, and two tests pin the behaviour.
