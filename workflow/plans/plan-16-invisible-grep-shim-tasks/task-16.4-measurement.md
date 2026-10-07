---
gmd: "0.1"
id: task-16.4-measurement
title: "Task 16.4: measure what the learner teaches against what the agent actually SAW, on complete outputs, now and as real use accrues"
tags: [task, grep, learning, measurement, eval]
metadata:
  node_type: task
  status: pending
  created: 2026-10-06
  revised: 2026-10-07
---

# Task 16.4: measurement {#root}

> Plan: [plan-16-invisible-grep-shim](../plan-16-invisible-grep-shim.md)
> Status: Pending (revision 3, after spec re-review `bsd-plan16-spec-rereview-42a5521`; precision
> gate KEPT by user decision 2026-10-07, scored on complete outputs only, with a forward-collected
> oracle)
> Depends on: [[task-16.1-argv-faithful-learner]], [[task-16.2-invisible-shim]]

rel: part-of -> [[plan-16-invisible-grep-shim]]
rel: depends-on -> [[task-16.2-invisible-shim]]
rel: derives-from -> [[plan-14-grep-learning-measurement]]
rel: amends -> [[bsd-plan16-spec-review-b587621]]
rel: amends -> [[bsd-plan16-spec-rereview-42a5521]]

## Why {#why}

The plan trades index ANSWERS for faithful LEARNING. Plan-14's 18.5% → 31.7% is stale (bug-074).
Two earlier versions of this spec had a precision gate that could not fail:

- **Revision 1** scored the learner against its own re-run (#b-2).
- **Revision 2** added an "unseen-but-verified" carve-out. Arm B runs on the snapshot, so every
  taught pair re-verifies by construction (#b-n1).

**Revision 3:** precision is scored ONLY where the agent's recorded output is COMPLETE. There, a
taught pair the agent did not see is a genuine over-teach, for example a dropped `-w`. Nothing is
carved out.

The data is thin. Measured on this project's 62 transcripts:
- O1 (Bash greps with line-addressed, attributable output) covers 55 of 2,342 grep commands, 2.3%;
- 76% of grep commands are piped;
- 46% contain more than one grep segment;
- O2 (Grep-tool calls) has 0.

So the gate has a pre-registered minimum n. A FORWARD oracle grows that n from real use after 16.2
ships: the learner's own log record makes attribution exact. {#why-lead}

## Requirements {#requirements}

**R1. Corpus, historical and forward.**
- **Historical.** The project's transcripts, plus their `subagents/` transcripts.
  - Each Bash `tool_use` containing a `grep`/`rg` segment is kept with its `tool_result`. Segments
    are found by exec'ing the rendered `render_scripts()[REWRITER_NAME]` plus the guard's
    git-exemption and heredoc tests.
  - Each Grep-tool `tool_use` is kept with its `tool_response`.
  - The cwd is the message cwd, adjusted for a leading `cd X &&` or `cd X;`. Any other in-command
    directory change is counted as `cwd-uncertain` and excluded.
- **Forward (#s-n10).** After 16.2 ships, every observed grep leaves a `grep-learn.log` record with
  `ts`, `cwd`, `argv`, `argv_sha` and `bin`. A transcript command is ATTRIBUTED to a learner record
  when the record's `argv`, joined, equals one of the command's grep segments, its `cwd` matches,
  and its `ts` falls within the tool call's window.
  - Attribution is exact even for multi-segment commands: each segment has its own record.
  - It is also the ROUTE oracle. A grep segment with a record was observed (route 1 or 2). A
    segment with no record and no learn-off, throttle or busy explanation was unobserved (route 3).
  - Route 2 is a record whose `argv` appears in no top-level segment, i.e. it ran inside a script
    (#m-n7).
- **Multi-segment historical commands** cannot be attributed and are EXCLUDED and counted.
- **Storage.** The corpus file lives off the watched tree. Summary statistics only are committed.

**R2. Arms on one snapshot,** built through the production ingest into a throwaway store with no
hub registration.
- **A (old):** a `git worktree` at the pre-16.2 sha, with its own venv. The old shim runs with
  `RMXGREP_RMX` pinned to THAT venv's `rmx` (#m-n5), because the old ping execs `$RMX grep --limit
  3` after `cd "$root"`, so replaying it with today's `rmx` is not what ran.
- **B (new):** `grep_learn` on the full argv.
- Both drain through the real `Daemon._drain_learn_queue`.
- The snapshot is the tree at the transcript's commit (`git log` before the timestamp). Where that
  cannot be determined, the invocation is counted as `drifted` and excluded from the line metrics.

**R3. The oracle: what the agent SAW, on COMPLETE outputs only (#b-n1).**
- An invocation is **complete** when all of these hold:
  1. no pipe stage follows the grep segment;
  2. the `tool_result` holds no `Output too large` / persisted-output marker;
  3. its size is under the tool-output limit;
  4. its output is line-addressed (`file:line:`);
  5. it is attributed to exactly one segment (R1);
  6. the number of seen pairs is below the learner's hit cap (200).
- On complete invocations, `seen` is the set of corpus-filtered `(file, line)` pairs in the output,
  each kept only if the snapshot's line hashes equal the recorded text (file drift excludes the
  pair and counts it).
- `taught` is arm B's set for that invocation.
- **There is no carve-out.** taught∖seen is an over-teach.
- On INCOMPLETE invocations (truncated, piped), only the visible prefix is known, so they feed
  `recall_visible` and nothing else.
- O2 (Grep-tool `content` mode) uses the same rules. Historical O2 is empty, so 16.3 is measured by
  its own AC-1 until forward O2 accrues.

**R4. Pre-registered metrics,** written in the harness docstring before the first run:

| metric | definition | gate |
|---|---|---|
| n_complete | complete invocations scored (O1 + O2) | **≥ 30** for the precision/recall gates to be EVALUATED; below that the verdict is `insufficient-n`, never pass |
| precision_B | Σ\|taught ∩ seen\| / Σ\|taught\| over complete invocations (micro) | **≥ 0.99** |
| recall_B | Σ\|taught ∩ seen\| / Σ\|seen\| over complete invocations (micro), timeouts INCLUDED in the denominator (#s-n10) | **≥ 0.95** |
| share_recall_lt_1 | complete invocations with any seen pair untaught / n_complete | reported, with each case listed |
| recall_visible | same as recall_B, over the visible prefix of incomplete invocations | reported |
| precision_A, recall_A, taught_invocations (A vs B) | same definitions for arm A | reported, not gated (#m-n5: 31 of 72 recent old pings exited 2) |
| unobserved_share | route-3 segments / all grep segments (forward oracle) | reported; the cost of d-3 |
| forgone_index_share | path-less invocations the pre-16.2 rich path answered from the index, replayed in arm A's worktree in rich mode on a snapshot store that has NOT seen arm B's teaching / all | reported; the cost of d-1 |
| timeouts | learner `outcome=timeout` / observed | reported; 16.1 R1b claims it is near 0 |
| shim_overhead | 16.2 AC-9 | as 16.2 |

If B misses an evaluated gate, the plan is re-decided. Thresholds are not edited after a run.

**R5. Re-runnable as n grows.**
- The harness takes `--since` and re-scores historical plus forward data. Each run appends a dated
  row to the report's results table.
- The gate verdict is stated per run, with the n it was evaluated on.
- The first run after 16.2 ships is the plan's acceptance run. Later runs track drift.

**R6. The report** is `docs/measurements/grep-observed-learning.md` (GMD), holding:
- the metrics with their verdicts and n;
- the complete/incomplete split;
- the counts excluded as multi-segment, drifted and cwd-uncertain;
- the route breakdown;
- both arms' shas;
- a scope line.

## Acceptance criteria {#acceptance}

1. One command runs the harness end to end and writes the report plus a JSON results file. A
   second run with `--since` appends a row.
2. Every R4 metric is present, each with its n and a gate verdict, or `insufficient-n` /
   `reported`.
3. **Extraction and attribution unit test.** The fixture transcript holds:
   - a leading grep;
   - `cd sub && grep -rn x .`;
   - a pipe-stage grep, which is incomplete;
   - `if grep -q x f; then …`;
   - a heredoc mentioning grep;
   - a quoted `grep`;
   - a git command containing grep;
   - a two-grep command, with and without matching learner records;
   - a Grep-tool call;
   - a subagent transcript;
   - an `Output too large` result.

   Each yields the expected completeness, route and attribution.
4. **The gate can fail (#b-n1).** A synthetic COMPLETE invocation scored against a stub learner
   that drops `-w` over-teaches, and precision_B falls below 0.99. The same invocation with the real
   learner scores 1.0.
5. **The minimum n holds.** With n_complete = 29, the verdict is `insufficient-n` even when
   precision is 1.0.
6. A 20-pair hand-check of taught rows against real lines is listed in the report.
7. **Smoke test.** On 3 complete invocations over a fixture tree, arm A's `-i` case has lower
   recall than arm B's.

## Files to modify {#files-to-modify}

| File | Change |
|------|--------|
| `eval/production/grep_observed_learning.py` (new) | extraction, completeness, forward join, routes, two arms (worktree), metrics, `--since` |
| `tests/test_grep_observed_learning.py` (new) | AC-3, 4, 5, 7 |
| `docs/measurements/grep-observed-learning.md` (new), `docs/INDEX.md` | report + index row |

## Test strategy {#test-strategy}

AC-3, AC-4, AC-5 and AC-7 run in the suite. Full runs log to `workflow/review-output/`.

Pre-registered mutations:
- restore the unseen-but-verified carve-out: AC-4 fails;
- drop the n gate: AC-5 fails;
- score precision on incomplete invocations: AC-3's pipe case is wrongly scored. {#tests}
