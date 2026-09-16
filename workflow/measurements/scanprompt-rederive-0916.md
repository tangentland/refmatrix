---
gmd: "0.1"
id: scanprompt-rederive-0916
title: "scan-prompt over the project store, before and after a re-derive"
tags: [measurement, scan-prompt, gmd, context-cost]
metadata:
  node_type: measurement
  date: 2026-09-16
  version: 0.71.0
---

# scan-prompt over the project store, before and after a re-derive {#root}

rel: evidence-for -> [[bug-registry#registry]]
rel: related-to -> [[feedback_measure_the_path_users_run]]

## What was asked, and what it actually answered {#question}

The question was whether bug-036 (a body `{#anchor}` was not a graph node) changed retrieval over
this project's own corpus. It did not, materially. The re-derive that was supposed to demonstrate it
demonstrated something larger and unrelated. {#lead}

## Method {#method}

`eval/production/scanprompt_graph_delta.py`, 12 fixed prompts, same order, `RMX_RERANK=0`, STM
composite excluded. **Both runs on 0.71.0** — the deploy landed BEFORE the baseline, so the
re-derive is the only variable between the two measurements. Measuring across the deploy would have
confounded a code change with a graph change. {#controls}

## The fix, measured directly {#fix}

| | before | after |
|---|---|---|
| body anchors on disk (memory dir) | 483 | 483 |
| present as entities in the store | **0** | **483 (100%)** |

Counted against a copy of the live read replica, independent of ranking. The mechanism works. {#fix-result}

## What actually moved scan-prompt {#confound}

| | before | after | |
|---|---|---|---|
| bundles | 31 | 63 | 2.0x |
| nodes | 206 | 466 | 2.3x |
| tokens | 11,425 | 28,157 | **2.46x** |
| mean tokens/prompt | 952 | 2,346 | |

**321 nodes newly returned; only 25 of them (7.8%) are body anchors.** The harness prints an
explicit "do not credit the fix" line for the zero case; 25 is a real but minor contribution and
does not explain the change. {#attribution}

The tell: **7 of the 12 prompts sat at exactly 1 bundle / 10 nodes before** — a floor, not a
ranking. Those went to 4-6 bundles. 483 anchors appearing cannot do that. A store that had not been
force-re-derived since 0.49.1, through ten days and several ingest changes, can. {#floor}

61 nodes STOPPED being returned. Not investigated. {#lost}

## The finding worth keeping {#finding}

**This project's own store had decayed, and no surface said so.** `stale_files: 35` was the only
signal, it reads as routine log churn, and it was dismissed as exactly that three times in one
session — by me, in this session, while looking directly at it. A store can be structurally
under-derived while every health check is green: `daemon_up`, `dev_tree: false`, versions matching,
`stale_files` in the tens. That is the same shape as `project_cliquet_catastrophic_repair` (green
health, dead store), one severity down. {#decay}

## Open, and NOT claimed {#open}

- **The anchor fix is not isolated.** Before/after a re-derive conflates it with the re-derive
  itself. Isolating needs a re-derive with the OLD parser on a copy (~30 min). The 483/483 entity
  count is the honest substitute: it proves the mechanism, not a retrieval gain. {#not-isolated}
- **Context cost nearly tripled and that is not self-evidently good.** 952 -> 2,346 mean tokens per
  prompt is injected into every turn. Plan 9's `rmx telemetry --context` exists to watch exactly
  this and has not been read against the new numbers. More context is a cost. {#cost}
- Any figure previously measured over this project's store predates the re-derive and should be
  re-derived before being requoted. {#requote}
