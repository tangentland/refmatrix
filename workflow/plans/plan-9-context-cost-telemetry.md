---
gmd: "0.1"
id: plan-9-context-cost-telemetry
title: "Context cost is measured: injected bytes per surface, and who asked"
tags: [plan, telemetry, observability, context]
metadata:
  node_type: plan
  status: in-progress
  created: 2026-09-15
---

# Proposed Plan: measure what rmx spends of the model's context, and who asked {#root}

**Date:** 2026-09-15
**Status:** Approved
**Location:** `workflow/plans/plan-9-context-cost-telemetry.md` — permanent home; stage is `metadata.status`.

rel: depends-on -> [[constitution]]
rel: implements -> [[tdd-governance]]
rel: derives-from -> [[brief-unanswered-confound]]
rel: reinforces -> [[feedback_measure_the_path_users_run]]
rel: related-to -> [[project_cli_telemetry]]
rel: specifies -> [[task-9.1-plan-9-context-cost-telemetry]]
rel: specifies -> [[task-9.2-plan-9-context-cost-telemetry]]
rel: specifies -> [[task-9.3-plan-9-context-cost-telemetry]]

## Context {#context}

Two gaps, found from two directions, that turn out to be the same record.

**1. Nobody knows what rmx costs the model.** Three hooks fire on every prompt — `scan-prompt`,
`memory recall --stdin-json`, and the grep rewrite — and each writes its output straight into the
context window. `query.log` and `cli.log` record LATENCY and never BYTES. So the project can say a
hook took 1.7 s and cannot say whether it spent 400 bytes or 40 KB of the window it was supposed
to be enriching. `context-mode` (23k stars) is built entirely around that number and reports it
per tool; rmx has richer retrieval and no idea what it charges for it.

This is [[feedback_measure_the_path_users_run]] pointed at ourselves. A retrieval surface that
measures its own quality and not its own cost is measuring half the trade.

**2. `query.log` cannot tell a question from a keystroke.** `telemetry.invocation_source()`
already exists, is already correct, and is already written into `cli.log` — and `log_query` simply
never writes it. The failed `brief/unanswered` gate named this as the cheapest signal that would
distinguish a question ASKED from a pattern GREPPED, and could not use it because the field is not
on the row. 174 of 465 zero-result rows came from the always-on `scan-prompt` hook firing on
"yes" and "go"; nothing in the record says so.

Both are one JSONL record and one measurement point. Hence one plan.

## Proposed Approach {#proposed-approach}

### Where bytes get counted {#where}

**At `cli_entry`, once, around `sys.stdout`** — not at N renderers.

That is the honest boundary: a hook captures this process's stdout and injects exactly those bytes.
Counting there measures the real payload rather than an estimate of it, covers every command
uniformly, and cannot drift — the alternative is an `out_bytes` set at each render site, which is
precisely the four-copies-of-one-thing failure [[feedback_reuse_shared_stoplist]] records.

Verified 2026-09-15: `rich.Console` resolves `sys.stdout` lazily at write time, so the module-level
`console` created at import picks up a wrapper installed afterwards. Both `console.print` and bare
`print` are counted by one proxy.

### What the records gain {#fields}

| Log | Field | Meaning |
|---|---|---|
| `query.log` | `invocation` | `hook` / `interactive` / `mcp` / `internal` / `unknown`, from the existing `invocation_source()` |
| `cli.log` | `out_bytes` | bytes this invocation wrote to stdout — what a hook injected |
| `cli.log` | `out_tokens` | a stated-approximation token estimate, never presented as exact |

`invocation` is a NEW key, deliberately not `source`: `query.log`'s `source` already means the
SURFACE (`scan-prompt`, `grep-replica`) while `cli.log`'s `source` means the FORM. Overloading the
name across two logs would make every future join wrong.

### The report {#report}

`rmx telemetry --context` over `cli.log`: total bytes, p50/p95 per command, and the per-prompt
hook budget — the summed bytes of the three always-on hooks per prompt, which is the number that
answers "what does rmx charge me every turn".

## Open Questions {#open-questions}

### Q1: Token estimate — how, and how honestly labelled? {#q1}
**Status:** RESOLVED

**Decision:** `bytes / 4`, labelled `out_tokens_est` in the report and documented as an
approximation at the one site that computes it. No tokenizer dependency.
**Rationale:** The decision this number drives is "is a hook spending 400 bytes or 40 KB", where
a 20% error changes nothing. Pulling in a real tokenizer to make a ratio look precise is the
expensive kind of false rigor, and a field named `_est` cannot be quoted as exact by accident.

### Q2: Does counting stdout slow the hot path? {#q2}
**Status:** RESOLVED

**Decision:** Ship the proxy, and measure it in task 9.2 before claiming it is free.
**Rationale:** One `len(s.encode())` per write on output already being serialized is not a
plausible regression — but "not plausible" is how the Stop-promote "0.13 s" claim got made when
the live number was 55 s ([[impression_bsd_cost_measured_idle]]). Measured, or not claimed.

## Decisions Log {#decisions-log}

| # | Question | Decision | Date |
|---|----------|----------|------|
| Q1 | Token estimate | `bytes / 4`, named `out_tokens_est`, documented as approximate. | 2026-09-15 |
| Q2 | Proxy overhead | Ship it, then measure it; no unmeasured "negligible" claim. | 2026-09-15 |

## Task Breakdown {#task-breakdown}

| Task ID | Title | Depends On |
|---------|-------|------------|
| 9.1 | `query.log` rows carry `invocation` | — |
| 9.2 | `cli.log` rows carry `out_bytes`, counted at the stdout boundary | — |
| 9.3 | `rmx telemetry --context`: bytes per command, per-prompt hook budget | 9.2 |

## Execution contract {#execution}

TDD per [[tdd-governance]]: RED test recorded to `workflow/review-output/` before GREEN; mutation
check on every new test; implementation summary per task; then `@ch-bsd` over the commit range.

**Plan-specific gates:**

- **Old rows must still read.** Both logs have months of history without these keys. Every reader
  defaults the missing field and a test drives a pre-field record through it — a backfill that
  silently drops history would destroy the only baseline this plan has.
- **Telemetry stays best-effort.** These logs are diagnostics, not memory: a failure to count
  bytes must never fail the command. That is the ONE place in this repo where a swallowed error is
  correct, and it is already how `log_cli_invocation` behaves. It does not license silence
  elsewhere — [[feedback_no_silent_failures]] governs the path between a memory FILE and the
  store, which this is not.
