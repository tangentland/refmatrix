---
gmd: "0.1"
id: task-16.4-measurement
title: "Task 16.4: measure what the learner teaches, against what the agent actually SAW and against the ping it replaces"
tags: [task, grep, learning, measurement, eval]
metadata:
  node_type: task
  status: pending
  created: 2026-10-06
  revised: 2026-10-07
---

# Task 16.4: measurement {#root}

> Plan: [plan-16-invisible-grep-shim](../plan-16-invisible-grep-shim.md)
> Status: Pending (revision 2, after ch-bsd spec review `bsd-plan16-spec-review-b587621`)
> Depends on: [[task-16.1-argv-faithful-learner]], [[task-16.2-invisible-shim]]

rel: part-of -> [[plan-16-invisible-grep-shim]]
rel: depends-on -> [[task-16.2-invisible-shim]]
rel: derives-from -> [[plan-14-grep-learning-measurement]]
rel: amends -> [[bsd-plan16-spec-review-b587621]]

## Why {#why}

The plan trades index ANSWERS for faithful LEARNING. Neither side of that trade is measured.
Plan-14's 18.5% → 31.7% is stale (bug-074, ch-bsd r3 #s-5). Its corpus was argv-less `query.log`
patterns, so it could not tell whether a call named files, and it could not replay flags.

Revision 1 of this spec scored the learner against "the real tool, same argv". That is the
learner's own computation, so its thresholds could not fail (#b-2). This revision scores against
what the agent actually SAW. {#why-lead}

## Requirements {#requirements}

**R1. The corpus is real agent invocations, with what they returned.**
- **Sources:** the project's transcripts `~/.claude/projects/<slug>/*.jsonl` AND their subagent
  transcripts in the per-session `subagents/` directories (#s-13).
- **Extraction:**
  - Each Bash `tool_use` whose command holds a `grep`/`rg` segment is kept, paired with its
    `tool_result`.
  - Segments are found with the guard's real rules: the rendered `render_scripts()[REWRITER_NAME]`
    is exec'd as a module, and the bash guard's git-exemption and heredoc tests are applied. These
    are imported and exec'd, not re-implemented (#s-13).
  - Each Grep-tool `tool_use` is kept with its `tool_response`.
- **The cwd is tracked (#s-13).** It is the message cwd, adjusted for a leading `cd X &&` / `cd X;`
  in the same command. Any other in-command directory change is counted as `cwd-uncertain` and
  excluded from the line-level metrics.
- **Each invocation is classified by ROUTE (#s-5):**
  - rewritten (route 1);
  - child-bash function (route 2: detected when the grep runs inside a script file the command
    executes);
  - unobserved (route 3: a non-head grep, a git-exempt command, or a heredoc);
  - pipe-stage (a filter: neither arm teaches).

  Each route's count is reported.
- **Storage:** the corpus file lives OFF the watched tree. Only summary statistics are committed.

**R2. Two arms on one snapshot,** built through the production ingest in a throwaway store with no
daemon registered with the hub:
- **A (old):** the flag-stripped ping, taken from `bin/rmxgrep` at the pre-16.2 sha (taken, not
  retyped).
- **B (new):** `grep_learn` on the full argv.

Both are drained through the real `Daemon._drain_learn_queue`. The snapshot is the tree at the
transcript's commit where recoverable (`git log` before the timestamp). Otherwise the invocation is
counted as `drifted` and line-level metrics exclude it.

**R3. The oracle is independent of the learner (#b-2).**
- **O1, transcript lines.** For a route-1/2 invocation whose recorded output is line-addressed
  (`file:line:` present, i.e. `-n` with filenames), the agent saw a set of `(file, line)` pairs.
  Each pair is kept only if the file's line at the snapshot still holds the recorded text (a hash
  check). Its coverage (share of invocations) is reported.
- **O2, the tool's own response,** for Grep-tool invocations in `content` mode.
- **Never the learner's own re-run.** No metric compares `grep_learn` to a command
  `grep_learn` built.

**R4. Pre-registered metrics,** written into the harness docstring BEFORE the first run:

| metric | definition (over O1 ∪ O2, corpus-filtered on both sides) | threshold |
|---|---|---|
| precision_B | taught pairs the agent saw / taught pairs | ≥ 0.98 (not 1.000: the agent may have seen a truncated `tool_result`, so a taught pair can be real and unseen; those are counted separately as `unseen-but-verified` by re-reading the line) |
| recall_B | seen pairs taught / seen pairs, under the hit cap | ≥ 0.95 median per invocation |
| precision_A, recall_A | same, arm A | reported |
| taught_invocations | invocations with ≥1 taught pair, B vs A | B ≥ A |
| unobserved_share | route-3 invocations / all grep invocations | reported; the cost of d-3 |
| forgone_index_share | path-less invocations the PRE-16.2 rich path answered from the index, replaying arm A's sha in rich mode on a snapshot store that has NOT seen arm B's teaching (#s-13: never train-on-test) / all invocations | reported; the cost of d-1 |
| shim_overhead | 16.2 AC-9 | as 16.2 |

If B misses a threshold, the plan is re-decided. Thresholds are not edited after the run.

**R5. The report** is `docs/measurements/grep-observed-learning.md` (GMD). It contains:
- every metric with its verdict;
- oracle coverage, the route breakdown, and the drifted and cwd-uncertain counts;
- the shas of both arms;
- a scope line.

`grep-learning-replay.md` already carries a SUPERSEDED banner pointing here (321ff97); this report
fulfils it.

## Acceptance criteria {#acceptance}

1. One command runs the harness end to end and writes the report plus a JSON results file.
2. Every R4 metric is present with its verdict and its oracle coverage.
3. **Extraction unit test.** One transcript fixture holds:
   - a leading grep;
   - `cd sub && grep -rn x .`;
   - a pipe-stage grep;
   - `if grep -q x f; then …`;
   - a heredoc mentioning grep;
   - a quoted `grep`;
   - a git command with grep;
   - a Grep-tool call;
   - a subagent transcript.

   It yields the expected route class and cwd for each.
4. **The oracle is independent.** A unit test feeds a synthetic invocation whose recorded
   `tool_result` DISAGREES with the re-run (one line edited after the fact), and precision_B drops
   below 1. Under revision 1's oracle it could not.
5. A 20-pair hand-check of taught rows against real lines is listed in the report.
6. **Smoke test.** On 3 invocations over a fixture tree, arm A's `-i` case teaches fewer seen pairs
   than arm B's. That is the defect, seen through the harness.

## Files to modify {#files-to-modify}

| File | Change |
|------|--------|
| `eval/production/grep_observed_learning.py` (new) | extraction, routes, oracle, two arms, metrics |
| `tests/test_grep_observed_learning.py` (new) | AC-3, AC-4, AC-6 |
| `docs/measurements/grep-observed-learning.md` (new), `docs/INDEX.md` | report + index row |

## Test strategy {#test-strategy}

The unit tests in AC-3, AC-4 and AC-6 run in the suite. The full run does not; its log goes to
`workflow/review-output/`. Pre-registered mutation: point the oracle at the learner's re-run, and
AC-4 must fail. {#tests}
