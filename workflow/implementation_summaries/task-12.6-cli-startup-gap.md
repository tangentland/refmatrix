---
gmd: "0.1"
id: task-12.6-cli-startup-gap-summary
title: "Implementation summary: the 8.5 s got a name — and half of it was a defect"
tags: [summary, plan-12, performance, measurement]
metadata:
  node_type: summary
  task: task-12.6-cli-startup-gap
  created: 2026-09-16
---

# Implementation summary: task 12.6 (bug-033, and bug-040 found on the way) {#root}

rel: implements -> [[task-12.6-cli-startup-gap]]
rel: part-of -> [[plan-12-open-bug-remediation]]
rel: evidence-for -> [[cli-startup-gap-0916]]

## What shipped {#shipped}

- `cli.phase_mark` / `render_phase_report` / `RMX_TIME_PHASES=1` — per-phase splits on the
  `context` path, to **stderr**, off by default, with stdout bytes provably unchanged.
- `context.build_context` skips the grep backstop for a memory-only store.
- `context._grep_backstop` says when it times out instead of swallowing it;
  `RMX_GREP_BACKSTOP_TIMEOUT_S` names the bound.
- `tests/test_cli_time_phases.py` — 6 tests.

## The task was measurement-only; the measurement found a defect {#found}

The first instrumented run pointed at a phase nobody suspected, and bisecting it with `--no-grep`
took a reproducible **15.09 s to 0.133 s**. The grep floor was `rg`-ing **`$HOME`**, because for
the global memory-only store `s.root.parent` IS the home directory — for a phrase a path-less store
can never have a floor hit for. It ran to the hard 15 s timeout every time, returned nothing, and
the timeout was swallowed as "no match". Fixed here and logged as **bug-040**; 15.13 s -> 0.09 s.

The residual on the LongMemEval store is cold first-touch I/O: that volume is an **SD card** at a
measured 94.7 MB/s, and the 432 MB adjacency cache alone is 4.6 s of I/O against 0.09 s warm. Warm,
the whole daemonless command is 0.70 s with 0.67 s in `build_context` — consistent with the 0.45 s
profiled core. **Not a defect**, and bug-033 closes as attributed rather than as a fix.

## RED / GREEN {#evidence}

- RED: `workflow/review-output/red-task-12.6.log` — 3 failed (instrument), then 2 more for the
  defect found mid-task.
- GREEN: 6 passed; `tests/test_grep_backstop.py` + every `test_context*` — 74 passed.
- Measurement: `workflow/measurements/cli-startup-gap-0916.md`.

## Honest limit {#limits}

The cold 8.75 s is ONE observation plus arithmetic that fits it (432 MB / 94.7 MB/s). The page
cache cannot be evicted on demand here, so it is not a repeated mean and the summary says so.
