---
gmd: "0.1"
id: task-10.1-plan-10-injection-dedup
title: "Task 10.1: Measure consecutive scan-prompt overlap on real prompts"
tags: [task, plan-10]
metadata:
  node_type: task
  status: pending
  plan: plan-10-injection-dedup
---

# Task 10.1: Measure consecutive scan-prompt overlap on real prompts {#root}

> Plan: [[plan-10-injection-dedup]]
> Status: Pending
> Depends on: plan 9

rel: part-of -> [[plan-10-injection-dedup]]

## Requirements {#requirements}

- **This task decides whether the rest of the plan is built.** Pre-registered threshold (plan Q1): median pairwise entry overlap between CONSECUTIVE `scan-prompt` calls >= **40%**, over >= **200** replayed real prompts. Below that, the plan stops here and the measurement ships as the deliverable.
- Input is REAL prompts, not synthetic: `query.log` holds 1,568 rows with `kind="scan"`, whose `body` is the actual prompt (truncated to 200 chars at write time — that truncation is a KNOWN limitation and must be stated in the report, not silently ignored, since a truncated prompt may select different concepts than the original did).
- Replay runs the PRODUCTION path — `rmx scan-prompt --format json` against the live store, read-only — and extracts the entry identity set per call. No bespoke re-implementation of the selection logic ([[feedback_measure_the_path_users_run]]).
- Overlap is computed on ENTRY IDENTITY (`name` + `path:line`), not on rendered bytes: two calls that pick the same entry but window a different snippet line are a repeat for dedup purposes, and byte-diffing would score them as new.
- Report, per consecutive pair: Jaccard and (more useful here) `|prev ∩ cur| / |cur|` — the fraction of THIS call that the turn already had. The second is the number the mechanism would actually save; the first is reported beside it so a reader can see set-size effects.
- Also report, from `cli.log` (plan 9), the LIVE per-prompt cost of `scan-prompt` and `grep` side by side — plan Q3 is unresolved and this run is where it gets answered.
- Ordering: pairs are consecutive within one SESSION. `query.log` carries no session id, so consecutive-by-timestamp with a stated gap cutoff is the approximation; the cutoff is a parameter and appears in the output. A wrong grouping rule silently invents or destroys overlap, so it is stated, not assumed.
- Read-only. Runs against the live store through the replica path; opens no writer, starts no daemon.

## Files to Create / Modify {#files}

- create `eval/injection_overlap.py`
- create `workflow/review-output/injection-overlap.md` (the pre-registered criteria + the result)

## Test Strategy (RED first) {#test-strategy}

`tests/test_injection_overlap.py`, on hand-built ranking fixtures (no store):
- overlap of identical entry sets is 1.0; of disjoint sets, 0.0; a hand-computed partial case matches
- `|prev ∩ cur| / |cur|` and Jaccard are BOTH reported and are different numbers on an asymmetric fixture (one call returning 2 entries, the next 10)
- entry identity uses name + path:line — two entries differing only in snippet TEXT count as the same entry
- the session-grouping cutoff is a parameter: the same fixture yields different pair counts at two cutoffs
- a pair spanning the cutoff is not counted as consecutive
- the summary carries the cutoff and the replay count, so a figure cannot be quoted without them
- an empty result set on either side contributes no pair rather than a 0.0 that drags the median

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation check noted in the implementation summary.
- Implementation summary at `workflow/implementation_summaries/task-10.1-plan-10-injection-dedup.md`.
- Committed on branch `task-10.1-plan-10-injection-dedup`; merged `--no-ff` to `master`.
