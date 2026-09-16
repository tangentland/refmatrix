---
gmd: "0.1"
id: task-10.1-summary
title: "Task 10.1 summary: consecutive scan-prompt overlap is 0.000 — plan 10 stopped here"
tags: [implementation-summary, plan-10, negative-result]
metadata:
  node_type: summary
  task: task-10.1-plan-10-injection-dedup
  created: 2026-09-16
---

# Task 10.1 summary {#root}

rel: realizes -> [[task-10.1-plan-10-injection-dedup]]
rel: part-of -> [[plan-10-injection-dedup]]
rel: evidence-for -> [[injection-overlap]]

## What shipped {#shipped}

`eval/injection_overlap.py` and the measurement at `workflow/measurements/injection-overlap.md`.
**No production code.** Tasks 10.2 and 10.3 were cancelled by this result.

## The result {#result}

Pre-registered before any number was read: median `|prev ∩ cur| / |cur|` >= **0.40** over >= 200
consecutive pairs, or the plan stops.

Measured: median carried **0.000**, mean 0.156, p75 0.100, median Jaccard 0.000, over 187 pairs
from 400 replayed real prompts in 73 runs. The median consecutive `scan-prompt` call shares ZERO
entries with the one before it.

**The run was underpowered and says so** — 187 pairs against a registered minimum of 200, flagged
`UNDERPOWERED` by the harness itself. That flag exists so a thin run cannot be quoted as a clean
negative, and it is honoured: this is not a clean negative result. It also does not change the
decision, and enlarging the sample after seeing the direction would be fishing.

## What it avoided {#avoided}

A per-session ledger, a degraded rendering path, PreCompact wiring, a turn TTL, and a permanent
correctness hazard in the always-on prompt path — where a ledger records what was SENT and cannot
record what SURVIVES compaction. Cost of avoiding all of it: one measurement.

## The finding nobody was looking for {#unexpected}

**112 of 400 replayed prompts (28%) produced an EMPTY scan-prompt bundle** — on the surface that
fires on every single prompt. Registered as a deferral; not chased here.

## Why the plan is not `completed` {#status}

It was flipped to `completed` and then back to `in-progress` (ch-bsd r1 #m-16): `plan-of-plans.md`
requires `@ch-bsd` over the range first, that pass is `bsd-plan7-10-r1-399d0a3`, and it is DIRTY.
The negative result stands; the plan's closure does not, yet.
