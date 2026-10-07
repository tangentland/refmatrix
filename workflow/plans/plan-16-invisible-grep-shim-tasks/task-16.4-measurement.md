---
gmd: "0.1"
id: task-16.4-measurement
title: "Task 16.4: measure what the learner teaches, against the ping it replaces, on real agent greps"
tags: [task, grep, learning, measurement, eval]
metadata:
  node_type: task
  status: pending
  created: 2026-10-06
---

# Task 16.4: measurement {#root}

> Plan: [plan-16-invisible-grep-shim](../plan-16-invisible-grep-shim.md)
> Status: Pending
> Depends on: [[task-16.1-argv-faithful-learner]], [[task-16.2-invisible-shim]]

rel: part-of -> [[plan-16-invisible-grep-shim]]
rel: depends-on -> [[task-16.2-invisible-shim]]
rel: derives-from -> [[plan-14-grep-learning-measurement]]

## Why {#why}

The plan trades index ANSWERS for faithful LEARNING, and it claims that trade is worth it. Neither
half is measured yet. Plan-14's 18.5% → 31.7% index share is stale since bug-074 (ch-bsd r3 #s-5).
Its corpus was `query.log` patterns WITHOUT argv, so it could not tell whether a call named files,
and it could not replay flags at all. This task measures on what agents actually ran. {#why-lead}

## Requirements {#requirements}

**R1. The corpus is real agent argv.**
- Extract every Bash-tool command whose segment starts with `grep` or `rg` from this project's
  transcripts (`~/.claude/projects/<slug>/*.jsonl`), keeping argv, cwd and timestamp.
- Drop pipe-stage greps, which neither arm teaches, and count them.
- The extraction uses the same segment rule as `rmxgrep-rewrite.py`, imported, not re-implemented.
- The corpus is a generated file OFF the watched tree (`feedback_generated_data_off_watched_tree`).
  Only its summary statistics are committed. {#r1}

**R2. Two arms on one corpus snapshot, built through the production ingest** (as plan-14's
harness does, in a throwaway store; no daemon is registered with the hub):
- **A (old).** For each invocation, the flag-stripped `rmx grep --limit 3` ping exactly as
  `bin/rmxgrep` at the pre-16.2 sha builds it. The ping script is taken from that sha, not
  re-typed.
- **B (new).** `grep_learn` on the full argv.

Both drain through the real `Daemon._drain_learn_queue`. {#r2}

**R3. Pre-registered metrics and thresholds,** written into the harness docstring BEFORE the first
run:

| metric | definition | threshold |
|---|---|---|
| precision_B | taught `(file,line)` that the caller's own command matches (real tool, same argv, run against the snapshot) / taught | **= 1.000** |
| recall_B | taught / caller-matched, per invocation, under the hit cap | ≥ 0.99 median |
| precision_A | same definition for arm A | reported, no threshold |
| taught_invocations | invocations with ≥1 taught hit, B vs A | B ≥ A |
| forgone_index_share | path-less invocations in the corpus that explicit `rmx grep` answers from the index after arm B's teaching, / all invocations | reported; this is the cost side |
| shim_overhead | from 16.2 AC-8 | as 16.2 |

If B misses a threshold, the plan is re-decided. Thresholds are not edited after the run
(`feedback_causal_story_before_evidence`). {#r3}

**R4. The report** is `docs/measurements/grep-observed-learning.md` (GMD). It holds the numbers,
the corpus size and what was dropped, the shas of both arms, and a scope line saying what the
corpus does and does not represent. `docs/measurements/grep-learning-replay.md` gets a banner
pointing here, which closes ch-bsd r3 #s-5's re-run gap for this question. {#r4}

## Acceptance criteria {#acceptance}

1. The harness runs end to end from one command and writes the report plus a JSON results file.
2. Every metric in R3 is present, with its threshold verdict.
3. A precision_B spot check: 20 randomly sampled taught rows are re-read by hand against their
   real lines, and the sample is listed in the report.
4. The corpus extraction has a unit test: a transcript fixture with a leading grep, a pipe-stage
   grep, a heredoc that mentions grep, and a quoted `grep` yields exactly one extracted
   invocation.
5. The report states how many invocations arm A could not even attempt (for example, the ping died
   on a flag) and why.

## Files to modify {#files-to-modify}

| File | Change |
|------|--------|
| `eval/production/grep_observed_learning.py` (new) | corpus extraction, two arms, metrics |
| `tests/test_grep_observed_learning.py` (new) | AC-4 + a 3-invocation smoke run |
| `docs/measurements/grep-observed-learning.md` (new) | the report |
| `docs/measurements/grep-learning-replay.md`, `docs/INDEX.md` | superseded banner + index row |

## Test strategy {#test-strategy}

- The smoke test runs both arms on 3 invocations over a fixture tree and asserts that
  precision_B = 1.0 and that arm A's flag-stripped `-i` case teaches fewer lines than B's. That is
  the defect, observed through the harness.
- The full run is not in the suite; its log goes to `workflow/review-output/`. {#tests}
