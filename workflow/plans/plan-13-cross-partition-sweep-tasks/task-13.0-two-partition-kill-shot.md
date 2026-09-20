---
gmd: "0.1"
id: task-13.0-two-partition-kill-shot
title: "Task 13.0: the oracle-union measurement that can end plan-13 without a verb"
tags: [task, plan-13, measurement, sessions, partitions]
metadata:
  node_type: task
  status: pending
  plan: plan-13-cross-partition-sweep
  gate: GO/STOP
---

# Task 13.0: the oracle-union measurement {#root}

> Plan: [[plan-13-cross-partition-sweep]]
> Status: Pending
> Gate: **GO/STOP for the entire plan**
> Depends on: nothing — this task exists so nothing depends on an unmeasured claim

rel: part-of -> [[plan-13-cross-partition-sweep]]
rel: derives-from -> [[bsd-plan13-cross-partition-sweep-0cb8b1a]]
rel: reinforces -> [[feedback_measure_the_path_users_run]]

## Requirements {#requirements}

- The audit's #b-1 killed the first arbiter: the MemAware store is ONE partition
  (`eval/memaware/paths.py:44`), so a cross-partition mechanism cannot fire there. This task builds
  the arbiter that can: **this repo's own store, which has both a project partition and
  `sessions-refmatrix`.**
- **No new production code.** Every condition runs through shipped surfaces. If this task needs a
  `sweep` verb to produce its number, it has been written wrong.
- Build a question set of **40–60 known-item questions** whose gold documents are identified, per
  [[plan-13-cross-partition-sweep#question-set]]:
  - mined from `.refmatrix/query.log` `kind="scan"` bodies (real prompts; `eval/memory_recall/mine_queries.py`
    already mines these) paired with a gold document that is a memory, an ADR, or a session card;
  - and/or `rel:` edges whose two endpoints resolve in DIFFERENT partitions — a labelled positive
    by construction.
  - Pooled + judged in the style of `eval/memory_recall/`. Every question records which PARTITION
    its gold lives in; a set whose golds are all in one partition cannot measure a union and must
    be rejected by the task's own check.
- **Freshness check before measuring** (plan risk): report the lag of `sessions-refmatrix` — newest
  session card vs newest session JSONL in `~/.claude/projects/`. A stale partition understates the
  union. The lag is REPORTED, never silently accepted.
- Conditions, all on the same question set and the same store:
  | condition | command |
  |---|---|
  | control | `rmx context <q>` |
  | sessions-on | `rmx context <q> --include-sessions` |
  | sessions-only | `rmx session recall <q>` |
  | memory | `rmx memory recall <q>` |
  | **oracle union** | set-union of control ∪ sessions-only ∪ memory, scored as one list |
- The oracle union is the SWEEP'S CEILING measured without building it: a perfect fusion cannot
  retrieve a document no leg returned.

## The re-encoding arm — MemAware under production topology {#reencode}

The harness ingests the MemAware corpus into the store's DEFAULT partition with doc names
`answer_*` / `<hex>_*` (`eval/memaware/ingest.py:83`,
`ingest-gmd --as-memory --memory-mtype memaware/session`, `paths.py:44` `PARTITION = "memaware"`).
Production puts the same kind of content — past chat — in `sessions-<project>` under `session-<hex>`
names, where `context.py:346` filters it out of `rmx context` by default
(`_is_session_card` is `name.startswith("session-")`, so the MemAware docs never match it).

**So the benchmark measures a topology the product does not run**, and it measures the favourable
one: `rmx context` scores 0.511 there because nothing filters the corpus. That violates
[[claude#development-guidelines]]'s benchmark rule (the benchmark path IS the production path) and
it is the cheapest available answer to the audit's #b-1 — the corpus already carries 90 labelled
questions, so no bespoke question set has to be mined for THIS arm. {#reencode-lead}

Re-ingest the same corpus a second time, unchanged in content, changed only in encoding:

| arm | partition | card name | mtype |
|---|---|---|---|
| **D** (today's harness, the ceiling reference) | `memaware` (default) | `answer_*` | `memaware/session` |
| **P** (production topology) | `sessions-memaware` | `session-<hex>` | `session` |

Conditions on arm P: `rmx context` (expected to collapse toward zero — that collapse is the
measurement), `rmx context --include-sessions`, `rmx session recall`, `rmx memory recall`, and the
oracle union.

**What each outcome means, written before the run:**

- `context` on P ≈ `context` on D → the filter is not reached by these queries; the plan's premise
  weakens and 13.0's own known-item set ([[#requirements]]) becomes the deciding arbiter.
- `context` on P collapses AND `--include-sessions` recovers D's score → **the default-off filter is
  the whole cost**, [[task-13.4-include-sessions-policy]] is the answer, and the sweep is not needed.
- `context` on P collapses and `--include-sessions` does NOT recover it → the union is doing work a
  flag cannot, which is the only outcome that justifies building the sweep.

This arm is run FIRST because it is hours, not days, and it can end the plan.

## Acceptance criteria {#acceptance}

- **GO** — oracle-union hit@20 ≥ best single condition **+ 0.05 absolute**, on EITHER
  the re-encoding arm ([[#reencode]]) or the known-item set — and the report says which.
- **STOP** — it is not. Write the negative into `docs/PERFORMANCE.md#negatives` and
  `workflow/bug_registry.md` is untouched (this is not a bug), flip the plan to `closed`, and stop.
- Either way the report records, per condition: hit@1, hit@20, MRR@20, and **the partition
  breakdown of the winning documents**. A GO whose gain is carried entirely by the session leg is
  reported as such, because it makes [[task-13.4-include-sessions-policy]] the cheap answer and the
  sweep unnecessary.
- The D-vs-P delta is reported as a number in its own right: it is the measured cost of
  `include_sessions=False`, which no artifact currently records.
- The report is committed to `eval/partition_sweep/REPORT.md` with the question set, the store sha
  (`rmx daemon status` version + `derive_status`), and the freshness lag.

## Files {#files}

- create `eval/partition_sweep/reencode_memaware.py` — re-ingests the SAME corpus under
  production topology (arm P); content byte-identical, only partition + card name change
- create `eval/partition_sweep/build_questions.py` — mines + pools + records gold partition
- create `eval/partition_sweep/run_conditions.py` — drives the five conditions through the CLI
- create `eval/partition_sweep/REPORT.md` — the artifact
- create `tests/test_partition_sweep_harness.py`
- no change under `src/`

## Test strategy (RED first) {#test-strategy}

The harness is code, so it is tested; the eval it produces is not a test.

1. `test_a_question_set_whose_golds_share_one_partition_is_rejected` — the check that stops this
   task from measuring a union with nothing to union.
2. `test_gold_partition_is_recorded_per_question` — every question carries its gold's partition id.
3. `test_oracle_union_is_the_union_of_its_inputs` — on a fixture: union of three ranked lists
   contains every id from each, deduped, and hit@20 is monotone ≥ each input's.
4. `test_a_condition_that_returns_nothing_is_an_error_line_not_an_empty_list` —
   [[feedback_no_silent_failures]]; a dead condition must not be scored as 0.0 silently.
5. `test_freshness_lag_is_computed_from_the_newest_card_and_the_newest_jsonl` — on fixture dirs.
6. `test_reencode_changes_only_partition_and_name` — arm P's card bodies are byte-identical
   to arm D's; a re-encoding that also rewrites content would measure two things at once.
7. `test_reencoded_cards_match_the_session_card_predicate` — the P cards DO satisfy
   `context._is_session_card`, else arm P is not production topology and the arm is void.
8. `test_scoring_matches_the_layer_a_metric` — same hit@k / MRR definitions as
   `eval/memaware/retrieval_eval.py`, asserted against a hand-computed fixture, so the two reports
   are comparable.

**Mutations that must kill a test:** return the control list as the oracle union (kills 3); drop
the single-partition guard (kills 1); score a failed condition as an empty list (kills 4).

## Implementation notes {#notes}

- `rmx` on PATH is the DEPLOY build; the conditions must run the deployed surfaces deliberately
  ([[feedback_rmx_binary_is_deploy]]), and the report records the version.
- `--include-sessions` already exists on `context`; confirm the flag name at write time from
  `cli.py` rather than from this spec ([[feedback_read_identifiers_at_write_time]]).
- Run against a COPY of the read replica where possible; never open `Store()` on the live slot.
