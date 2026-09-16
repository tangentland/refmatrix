---
gmd: "0.1"
id: rerank-cost-budget-0916
title: "Measurement: the rerank cost path, before deploy"
tags: [measurement, rerank, model-workers, bug-025]
metadata:
  node_type: measurement
  created: 2026-09-16
---

# Measurement: the rerank cost path, 2026-09-16 {#root}

rel: evidence-for -> [[task-12.2-rerank-cost-budget]]
rel: part-of -> [[plan-12-open-bug-remediation]]

## 1. bug-025 still reproduces on the DEPLOYED path {#reproduce}

Two runs of the exact deployed hook argv (`rmx memory recall --stdin-json --k 5 --scope both
--json --timeout 5`), load average 4.00, minutes apart, dev binary against the live store:

```
# rmx: warning: rerank failed (TimeoutError: timed out); hits unreranked
# rmx: warning: global rows omitted: recall not confirmed within 5s — daemon busy
```

**0 of 5 rows reranked, both runs.** Same as the 7/7 recorded on 2026-09-15.

The new skip did NOT fire, and that is the correct behaviour rather than a defect: the shared
worker answering was the DEPLOYED hub's (0.71.0, old code), whose `info` carries no
`cost_s_per_doc`. `estimate_rerank_s` returns None on absent data and the caller proceeds — a
guess would be acted on. **The fix is inert until the hub runs the new worker**, which is the
honest state of it, and the acceptance run belongs after that deploy.

## 2. The new path, end to end, on a REAL model worker {#live-private}

A `ModelServer` from the dev tree on a private socket (`RMX_MODEL_SOCK=/tmp/rmxlive.sock`), real
`cross-encoder/ms-marco-MiniLM-L-12-v2`, real frames:

| step | result |
|------|--------|
| cold `info` (model load) | 6.6 s — `cost_s_per_doc: null`, `scored_docs: 0`, `queue_depth: 0` |
| one 10-doc rerank | 0.10 s |
| `info` after it | `cost_s_per_doc: 0.0098`, `scored_docs: 10`, `queue_depth: 0` |
| `estimate_rerank_s(info, 10)` | 0.098 s |
| frame with a deadline 5 s in the past | `WorkerError: deadline expired 5.00s ago; not scored` |

So: the EMA is real, it stays `null` until a real call measures it, the server's `queue_depth`
rides the same handshake, and the worker drops an abandoned frame without touching the model.

## 3. What this does NOT show {#limits}

- **The skip did not fire here, because it should not have.** An idle private worker scores 10 docs
  in 0.098 s. The 3.72 / 9.26 / 14.08 s figures in bug-025 come from a LOADED, shared, queued
  worker — the condition that makes `(1 + queue_depth)` matter. The skip firing live needs that
  condition, i.e. the deployed fleet.
- **No acceptance claim is made here.** Acceptance for bug-025 is: two runs of the deployed hook
  argv, minutes apart, under ordinary load, counting RERANKED ROWS — after the deploy.

## 4. ACCEPTANCE, after the deploy {#acceptance}

Deployed 0.72.0 at 11:51 (fleet relaunched 11:54, hub restarted onto 0.72.0 at 11:52 so its model
workers run this code). The exact deployed hook argv, read out of `.claude/settings.json` rather
than retyped:

```
rmx memory recall --stdin-json --k 5 --scope both --json --timeout 5
```

| run | clock | load (1 min) | wall | rows | **reranked** |
|---|---|---|---|---|---|
| 1 | 11:53:34 | 4.44 | 4.84 s | 5 | **5** |
| 2 | 11:53:38 | 4.48 | 4.77 s | 5 | **5** |
| 3 | 11:56:03 | 3.88 | 5.14 s | 5 | **5** |
| 4 | 11:56:09 | 3.88 | 5.15 s | 5 | **5** |

Two windows two and a half minutes apart, under ordinary load, counting RERANKED ROWS — the
acceptance criterion bug-025 set for itself, and deliberately not wall time in a quiet minute.

**Before, on the same machine four hours earlier** (§1): `rerank failed (TimeoutError: timed out)`,
**0 of 5 reranked**, twice, at load 4.0. **After: 20 of 20 rows reranked across four runs.**

No `rerank skipped` warning fired in any run, which is the correct outcome rather than a missing
one: the shared worker answers with a real `cost_s_per_doc` now, the estimate fits the remaining
budget, and the leg runs. The skip exists for the case where it does not fit — covered by test, and
by construction unobservable while the worker is fast enough.

bug-025 is **closed**: the fix is no longer inert, and the claim is measured on the path users run.
