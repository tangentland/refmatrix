---
gmd: "0.1"
id: task-9.2-plan-9-context-cost-telemetry
title: "Task 9.2: cli.log rows carry `out_bytes`, counted at the stdout boundary"
tags: [task, plan-9]
metadata:
  node_type: task
  status: complete
  plan: plan-9-context-cost-telemetry
---

# Task 9.2: cli.log rows carry `out_bytes`, counted at the stdout boundary {#root}

> Plan: [[plan-9-context-cost-telemetry]]
> Status: Complete
> Depends on: —

rel: part-of -> [[plan-9-context-cost-telemetry]]

## Requirements {#requirements}

- A counting proxy wraps `sys.stdout` in `cli_entry` for the duration of `main()`; `log_cli_invocation` gains `out_bytes` and `out_tokens_est`.
- **One point, not N renderers.** The hook captures this process's stdout and injects exactly those bytes, so counting there measures the real payload instead of estimating it, covers every command uniformly, and cannot drift. An `out_bytes` set at each render site is the four-copies-of-one-thing failure [[feedback_reuse_shared_stoplist]] records.
- Verified 2026-09-15: `rich.Console` resolves `sys.stdout` lazily at write time, so the module-level `console` bound at import picks up a wrapper installed later. Both `console.print` and bare `print` must be counted, and a test asserts both.
- Bytes, not characters: `len(s.encode("utf-8"))`. A multi-byte prompt must not under-count.
- `out_tokens_est` is `out_bytes // 4`, named `_est`, documented as an approximation at the site that computes it. No tokenizer dependency (Q1).
- The proxy is transparent: `isatty()`, `encoding`, `flush()`, and `fileno()` pass through, because code downstream branches on all of them. A wrapper that reports the wrong ttyness would change rich's rendering and therefore the very bytes it is measuring.
- Restored in a `finally`, including on `SystemExit` — click exits that way on every run.
- **Overhead measured, not asserted (Q2).** The implementation summary carries a before/after timing of a representative hook command. No unmeasured "negligible" claim ([[impression_bsd_cost_measured_idle]]).

## Files to Create / Modify {#files}

- modify `src/refmatrix/cli.py` (`cli_entry`)
- modify `src/refmatrix/telemetry.py` (`log_cli_invocation` signature + record)

## Test Strategy (RED first) {#test-strategy}

`tests/test_context_cost.py`:
- the proxy counts bytes from `print` AND from a `rich.Console` created BEFORE it was installed
- multi-byte output is counted in bytes, not characters
- `isatty`/`encoding`/`flush`/`fileno` pass through to the wrapped stream
- `sys.stdout` is restored after a normal return AND after `SystemExit`
- `log_cli_invocation` writes `out_bytes` + `out_tokens_est`; `out_tokens_est == out_bytes // 4`
- a reader handles a legacy record with no `out_bytes`
- a proxy whose count raises does not fail the command (telemetry stays best-effort)
- mutation check: making the proxy count characters instead of bytes turns the multi-byte test RED

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation check noted in the implementation summary.
- Implementation summary at `workflow/implementation_summaries/task-9.2-plan-9-context-cost-telemetry.md`.
- Committed on branch `task-9.2-plan-9-context-cost-telemetry`; merged `--no-ff` to `master`.
