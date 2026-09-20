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
- **Composition is pre-registered before the set is built** (r2 #b-8). This task both builds the
  question set and is judged by it, so the gold-partition mix is declared first — 50% project-gold,
  50% session-gold, ±10% — and a set outside that band is rejected by the harness, not re-tuned.
  Every reported delta carries its 95% binomial interval; at n=60 a 0.05 difference is three
  questions.
- **Source 2 is dead and source 1 is all there is:** `rel:` edges cannot have a session endpoint,
  because `session_ingest.build_card` emits no `rel:` lines (r2 #b-7). The set comes from mined
  `kind="scan"` query.log bodies (2180 available on this store) paired with judged golds.
  `helix.log` is NOT a gold source — `project_helix_log_confounded` records it as structurally
  confounded on the hook path.
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

The first draft of this arm moved FOUR variables and read one (r2 addendum #b-10). It is split so
each gate is isolated:

| arm | partition | card name | mtype | what it isolates |
|---|---|---|---|---|
| **D** | `memaware` (default) | `answer_*` | `memaware/session` | today's harness — the ceiling reference |
| **P1** | `memaware` (default) | `session-<hex>` | `memaware/session` | **the name gates alone** — `_is_session_card`, `_OPERATIONAL_RE` ×2, `_is_operational_anchor` |
| **P2** | `sessions-memaware` | `session-<hex>` | `memaware/session` | P1 + the partition move |
| **P3** | `sessions-memaware` | `session-<hex>` | `session` | full production topology |

**Recovery is measured against P1**, because P1 is the only arm where `--include-sessions`'s gate is
the one that moved. On P2/P3 non-recovery is guaranteed by construction and would read as "the union
does work a flag cannot" — the branch that authorises building the sweep. An arm that can only
return "build it" is not an experiment.

**mtype is not cosmetic and P3 pays for it:** `consolidate.DEFAULT_EXCLUDE_MTYPES` is
`("session", "session/*", "digest", "digest/*", "subject")` (`consolidate.py:66`), so
`rmx memory compile` drops every P3 card by mtype at `:90` AND by name at `:92` — P3 has no subject
layer while D compiles fully. Fixing the mtype does not restore it; the name gate fires
independently. P3 is therefore reported as "production topology including its compile behaviour",
not as "D with a different label". One thing IS inert and must not be "fixed": bare mtype `session`
does not trip `rmx memory recall`'s exclusion, because `mt_excluded` uses `fnmatchcase` and
`session/*` does not match `session`.

**Vectors are a fourth variable and are declared, not discovered:** `rmx embed --kinds memory` walks
the ACTIVE partition only (`cli.py:6873`), so P2/P3 either have no vectors — a changed retrieval
stack — or receive an embed pass that production's `sessions-refmatrix` never gets (r2 #b-7). This
task embeds them and SAYS SO, so the arm is "production topology plus vectors production lacks",
and the session leg's missing dense half is reported as its own finding rather than smuggled in.

**The harness env must be overridden per arm or every arm-P condition reads the wrong partition**
(r2 addendum #b-11). `paths.rmx_env()` sets `RMX_PARTITION = PARTITION` (`paths.py:59`), and
`RMX_PARTITION` wins over `_sessions_partition_default()` in `cli._session_partition()` and over the
constructor argument in `Store.__init__` (`store.py:700-708`). Unfixed, `rmx session recall` cannot
answer P2/P3 at all and `context` returns ~nothing — and the collapse would be a PARTITION MISS
scored as the filter's cost. Every condition records the partition it actually queried, and a
condition whose recorded partition is not the arm's is a hard error, not a zero.

Conditions per arm: `rmx context` (control), `rmx context --include-sessions`, `rmx session recall`,
`rmx memory recall`, and the oracle union.

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
6. `test_each_arm_moves_exactly_the_variables_it_declares` — P1 differs from D in NAME only; P2
   adds partition; P3 adds mtype. Asserted field by field, not by "bodies are byte-identical" (which
   passes with three variables moved).
6b. `test_every_condition_records_the_partition_it_queried` — and a mismatch against the arm's
   partition raises rather than scoring 0 (the #b-11 guard).
7. `test_reencoded_cards_match_every_gate_that_keys_on_the_prefix` — the P cards satisfy
   `context._is_session_card` AND `consolidate._OPERATIONAL_RE` AND `pagerank._OPERATIONAL_RE` AND
   `scan._is_operational_anchor`. Asserting one of four was the original hole: `--include-sessions`
   lifts only the first.
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
