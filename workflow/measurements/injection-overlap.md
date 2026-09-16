---
gmd: "0.1"
id: injection-overlap
title: "Task 10.1: consecutive scan-prompt overlap — STOP (underpowered but decisive)"
tags: [plan-10, measurement, negative-result]
metadata:
  node_type: measurement
  task: task-10.1-plan-10-injection-dedup
  created: 2026-09-15
  verdict: STOP
---

# Consecutive scan-prompt overlap {#root}

rel: evidence-for -> [[task-10.1-plan-10-injection-dedup]]
rel: contradicts -> [[plan-10-injection-dedup]]
rel: implements -> [[project_helix_phase2_decision_criterion]]

**Verdict: STOP. Plan 10.2 and 10.3 are not built.**

## Pre-registered, before any number was read {#criteria}

Median `|prev ∩ cur| / |cur|` over consecutive `scan-prompt` calls must be **>= 0.40**, over
**>= 200** pairs.

## Result {#result}

| metric | value |
|---|---:|
| **median carried** | **0.000** |
| mean carried | 0.156 |
| p25 / p75 carried | 0.000 / 0.100 |
| median Jaccard | 0.000 |
| pairs | 187 |
| prompts replayed | 400, in 73 runs |
| median entries per call | 10 |
| empty results | 112 / 400 (28%) |

The median consecutive call shares **zero** entries with the one before it. The 75th percentile is
0.10. The premise of plan 10 — that scan-prompt re-pays for context the turn already holds — is
false on this project's real prompt stream.

## The caveat, stated because it is real {#underpowered}

187 pairs against a registered minimum of 200, so the harness self-reported `UNDERPOWERED`. That
flag exists so a thin run cannot be quoted as a clean negative, and it is honoured here: **this is
not a clean negative result.**

It does not change the decision. A 7% sample shortfall is not the distance between 0.00 and 0.40,
and enlarging the sample to clear an arbitrary bar after seeing the direction would be fishing.
The finding is recorded with its limitation attached rather than laundered into a cleaner one.

Two further limitations, by construction:

- `query.log` truncates `body` to 200 chars, so this replays a PROXY for the original selection.
- `query.log` carries no session id; consecutive-ness is a 900 s gap cutoff, stated in the output.

Neither plausibly moves a 0.000 median to 0.40.

## Why {#why}

`median_entries_per_call = 10` and 28% of calls return nothing. Scan-prompt emits a small,
tightly prompt-specific set, and real work moves between topics faster than a 10-entry window can
overlap. A dedup ledger would have guarded against repetition that does not occur.

## What this avoided {#avoided}

A per-session ledger, a degraded rendering path, PreCompact wiring, a turn TTL, and a permanent
correctness hazard in the always-on prompt path — where a ledger records what was SENT and cannot
record what SURVIVES compaction. Cost of avoiding it: one measurement.

## The finding I was not looking for {#unexpected}

**28% of scan-prompt calls return nothing.** That is a live number about the surface that fires on
every single prompt. Whether it is correct on short control prompts ("yes", "go") or a real
retrieval gap is a separate, now-measurable question. Registered as a follow-up, not chased here.
