---
gmd: "0.1"
id: task-16.4-measurement
title: "Task 16.4: measure what the learner teaches against what the agent actually SAW, on complete outputs, now and as real use accrues"
tags: [task, grep, learning, measurement, eval]
metadata:
  node_type: task
  status: pending
  created: 2026-10-06
  revised: 2026-10-14
---

# Task 16.4: measurement {#root}

> Plan: [plan-16-invisible-grep-shim](../plan-16-invisible-grep-shim.md)
> Status: Pending (revision after the 2026-10-14 decision log; revision 6, answering spec review
> r5 `bsd-plan16-spec-review-r5-cd7c923`). The precision gate is KEPT by user decision 2026-10-07,
> scored on complete outputs only, with a forward-collected oracle.
> **Wave:** 2, after 16.2 ships ([[plan-16-invisible-grep-shim#waves]]).
> Depends on: [[task-16.1-argv-faithful-learner]], [[task-16.2-invisible-shim]]. Tests run in
> plan-23 task 23.0's sandbox.

rel: part-of -> [[plan-16-invisible-grep-shim]]
rel: depends-on -> [[task-16.2-invisible-shim]]
rel: derives-from -> [[plan-14-grep-learning-measurement]]
rel: amends -> [[bsd-plan16-spec-review-b587621]]
rel: amends -> [[bsd-plan16-spec-rereview-42a5521]]
rel: amends -> [[bsd-plan16-spec-review-r3-c8278b1]]
rel: amends -> [[bsd-plan16-spec-review-r4-33809ab]]
rel: amends -> [[bsd-plan16-spec-review-r5-cd7c923]]
rel: derives-from -> [[plan-review-2026-10-14#t7]]

## Revision 6 changelog {#revision-6}

Answers spec review r5 ([[bsd-plan16-spec-review-r5-cd7c923]]) and the 2026-10-14 decision log
([[plan-review-2026-10-14]]).

| finding / decision | answered in |
|---|---|
| r5 s-r5-6 / #t7-fixes (route 2 absorbs Grep-tool and explicit `rmx grep` learner records; `spawned_by`) | R1 step 4 [[#r1-forward]]: records split by 16.1 R6's `spawned_by`; Grep-tool records join to Grep `tool_use`s, `rmx-grep` records to `rmx grep` segments; route 2 counts `spawned_by=shim` only. AC-3 rows; mutation |
| r5 m-r5-6 / #t7-fixes MEH ("$ rule before quote stripping") | R1 step 3: the `$`/backtick test reads the RAW segment text, before `shlex` removes quotes; `$` inside single quotes is literal. AC-3 rows; mutation |
| d1a/d1b (tests sandboxed by task 23.0) | [[#test-strategy]] |

## Revision 5 changelog {#revision-5}

Answers spec review r4 ([[bsd-plan16-spec-review-r4-33809ab]]).

| finding | answered in |
|---|---|
| s-r4-5 both joins kept; route 2 by text equality (m-n7); zero-candidate segments read as route 3; `ts` undefined; learn-off unevaluable | R1 [[#r1-forward]]: the exact-join text is DELETED; one approximate join on shlex tokens; routes re-defined; an `unattributable` bucket that is never route 3; `ts` from 16.1 R6; learn-off reported as a known confound. AC-3 rows |
| s-r4-4 no join rule for keyed lines | R1 [[#r1-keyed]]: epoch window + cwd, `throttled-explained`, no argv equality |
| m-r4-7 one snapshot vs per-commit; models socket | R2 [[#r2]]: at most 10 snapshots, nearest-later + line-hash rule, private local-cache models (`RMX_SHARED_MODELS=0`), no hub socket |
| m-r4-6 (16.5's BRE concepts) | R4 metric `bre_concept_share` |

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
  `ts`, `cwd`, `argv`, `argv_sha` and `bin`; `ts` is the learner's START (16.1 R6). The transcript
  holds SHELL TEXT and the record holds EXPANDED argv, so attribution is the approximate join below
  — there is no exact (argv-equality) join (s-r4-5: the revision-4 sentence claiming one is
  deleted).
- **Multi-segment historical commands** cannot be attributed and are EXCLUDED and counted.
- **rmx-rendered historical outputs are EXCLUDED and counted (#s-r3-6).** Of 37 complete-looking
  historical invocations, 28 carry rmx rendering markers: `# rmx`, the `[linkage]  concept` row
  shape, `rmx grep:` notes, `# rmx grep fallback via rg`. Scoring the learner against rmx's own old
  output would grade it on rmx's old bugs. About 9 historical invocations remain, so the gate in
  practice rests on the forward oracle.
- **Forward join, honestly approximate (#s-r3-7, s-r4-5).** {#r1-forward} Equality fails for `$`,
  backticks, globs, loops and `xargs` (probed: 117, 109 and 134 commands respectively). r4 measured,
  over 2,824 producing segments: 8.5% ambiguous, 5.3% in a loop, 2.4% with a `$`/backtick pattern,
  3.6% whose argv pattern is not a literal substring of the text because of escaped quotes. So:
  1. **Tokens, not text.** Each segment is split with POSIX `shlex` (quotes removed, NO expansion).
     A segment `shlex` cannot split is `unattributable`.
  2. **Candidates, by spawner (s-r5-6).** Every forward record carries 16.1 R6's `spawned_by`, and
     it is joined only to the call shape its spawner observes:
     - `spawned_by=shim`: candidate for a Bash `grep`/`rg` segment when its `ts` falls inside the
       tool call's window, its `cwd` equals the segment's cwd (R1 historical rule; compared after
       `realpath` on both sides), and its PATTERN operand equals one of the segment's shlex tokens.
       The escaped-quote case matches, because the quotes are gone.
     - `spawned_by=rmx-grep`: the same rule against Bash segments that lead with `rmx grep` (the
       first two shlex tokens are `rmx` or a path ending in `/rmx`, then `grep`).
     - `spawned_by=grep-tool-hook`: candidate for a Grep `tool_use` when its `ts` is inside that
       call's window, its `cwd` equals the message cwd, and the `-e` value in its `argv` equals the
       call's `tool_input.pattern`.
  3. **Buckets for a segment**, each counted and reported:
     - `attributed` — exactly one candidate;
     - `ambiguous` — two or more candidates;
     - `unattributable` — the segment's pattern token carries an EXPANDING `$` or backtick, or the
       segment sits inside `for`/`while`/`xargs` (one segment, N records), or `shlex` failed.
       **The `$` test reads the RAW text, before quote stripping (m-r5-6):** shlex turns `'alpha$'`
       and `"$x"` into `alpha$` and `$x` alike (probed in r5). A `$` or backtick inside SINGLE
       quotes is literal, so `grep 'alpha$' f` stays attributable; one unquoted or inside double
       quotes expands, so `grep "$x" f` is unattributable. **An
       unattributable segment is NEVER route 3** and never counted in `unobserved_share`'s
       numerator or denominator;
     - `throttled-explained` — zero candidates, and a keyed line explains it ([[#r1-keyed]]);
     - `unobserved` — zero candidates, no keyed line, and the segment is not unattributable.
       Only these are route 3.
  4. **Routes.** Route 1 = an `attributed` `spawned_by=shim` record. Route 2 = a
     `spawned_by=shim` learner record that is a candidate for NO segment of any tool call in its
     window (it ran inside a script; m-n7: defined by the join, not by text equality). Route 3 =
     `unobserved` segments. Grep-tool and `rmx-grep` records are NEVER route 2 (s-r5-6): they are
     reported in their own buckets (`grep-tool attributed/unmatched`, `rmx-grep
     attributed/unmatched`), and an unmatched one is a join failure to list, not a script.
  5. **Learn-off is a known confound (s-r4-5).** A learn-off shim exit writes nothing (16.2 AC-5,
     by design: learning off means no writes), so a segment run with learning off reads as
     `unobserved`. `unobserved_share` is therefore an UPPER bound; the report says so, and lists
     any `RMX_LEARN`/marker change the harness can see in `grep-learn.log` gaps.
- **Keyed lines (s-r4-4).** {#r1-keyed} 16.2 R3 writes `<epoch> <cksum> <PWD>` to `throttled` and
  `busy`. A zero-candidate segment is `throttled-explained` when a line in either file has its epoch
  inside the tool call's window and its `PWD` equals the segment's cwd (after `realpath`). No argv
  or `cksum` recomputation is attempted (it would need the expanded argv). One keyed line explains
  at most one segment; the surplus is counted.
- **Storage.** The corpus file lives off the watched tree. Summary statistics only are committed.

**R2. Arms on bounded snapshots (m-r4-7),** each built through the production ingest into a
throwaway store with no hub registration. {#r2}
- **Models.** The throwaway ingest embeds. It runs with `RMX_SHARED_MODELS=0` (a private worker,
  never the hub's live `models.sock`; `92c374c` logged 66 test touches of that socket) and
  `HF_HUB_OFFLINE=1`; models load from the local cache only, and `ModelNotCached` is a loud failure
  of the run, never a skip.
- **A (old):** a `git worktree` at the pre-16.2 sha, with its own venv. The old shim runs with
  `RMXGREP_RMX` pinned to THAT venv's `rmx` (#m-n5), because the old ping execs `$RMX grep --limit
  3` after `cd "$root"`, so replaying it with today's `rmx` is not what ran.
- **B (new):** `grep_learn` on the full argv.
- Both drain through the real `Daemon._drain_learn_queue`.
- **Snapshot count (m-r4-7).** The candidate snapshot for an invocation is the tree at the
  transcript's commit (`git log` before the timestamp). The transcript span covers 366 commits, so
  the harness builds AT MOST 10 snapshots: the commits holding the most complete invocations,
  largest n first (`RMX_GREP_EVAL_MAX_SNAPSHOTS`, default 10, printed in the report). An invocation
  at any other commit is scored on the NEAREST LATER built snapshot only if every one of its seen
  pairs' line hashes matches there (R3); otherwise it is `drifted`, excluded from the line metrics
  and counted. An invocation whose commit cannot be determined is `drifted`.

**R3. The oracle: what the agent SAW, on COMPLETE outputs only (#b-n1).**
- An invocation is **complete** when all of these hold:
  1. no pipe stage follows the grep segment;
  2. the `tool_result` holds no `Output too large` / persisted-output marker;
  3. its size is under the tool-output limit;
  4. its output is line-addressed (`file:line:`);
  5. it is attributed to exactly one segment (R1);
  6. the number of seen pairs is below the learner's hit cap (200);
  7. the `tool_result` holds the output of THIS command only: no other `&&`/`;` segment printed
     (#s-r3-8);
  8. for Grep-tool calls, no pagination marker (16.3).
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
| unobserved_share | `unobserved` segments / (all grep segments − `unattributable`) (forward oracle); an upper bound (learn-off confound, R1) | reported; the cost of d-3 |
| attribution buckets | counts of `attributed`, `ambiguous`, `unattributable`, `throttled-explained`, `unobserved`, and route-2 records | reported |
| bre_concept_share | taught `query/*` concepts whose pattern carries a BRE meta / all taught concepts (16.5 R3: `rmx grep` never reads them) | reported |
| forgone_index_share | path-less invocations the pre-16.2 rich path answered from the index, replayed in arm A's worktree in rich mode on a snapshot store that has NOT seen arm B's teaching / all | reported; the cost of d-1 |
| timeouts | learner `outcome=timeout` / observed | reported; 16.1 R1b claims it is near 0 |
| shim_overhead | 16.2 AC-9 | as 16.2 |

If B misses an evaluated gate, the plan is re-decided. Thresholds are not edited after a run.

**Closure rule (#s-r3-9).** plan-16 cannot move to `completed` while `n_complete < 30`. If 14 days
after 16.2 is deployed the forward oracle still has `n_complete < 30`, the harness's dated row says
so and the precision decision goes back to the user, with the n reached and the remaining options.
This deferral is anchored to that date and to this task. It is not open-ended.

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
   - an escaped-quote pattern (`grep "a\"b" f`) that attributes through shlex tokens;
   - a `$var` pattern and a `for … do grep …` loop, each `unattributable` and NOT route 3;
   - a zero-candidate segment with a matching keyed line (`throttled-explained`) and one without
     (`unobserved`, route 3);
   - a learner record with no candidate segment (route 2), `spawned_by=shim`;
   - a `spawned_by=grep-tool-hook` record that joins to the fixture's Grep `tool_use` (not route 2)
     and a `spawned_by=rmx-grep` record that joins to a `rmx grep -rn alpha src` Bash segment (not
     route 2) (s-r5-6);
   - `grep 'alpha$' f` (attributable: `$` in single quotes) and `grep "$x" f` (unattributable)
     (m-r5-6);
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

AC-3, AC-4, AC-5 and AC-7 run in the suite, inside plan-23 task 23.0's shared sandbox (d1a/d1b:
`$HOME`, global root, registry and LaunchAgents dir in a tmp dir before `refmatrix` is imported;
the conftest guard fails any touch of `~/.refmatrix` or a registered live store). The arms' throwaway
stores (R2) are built inside that sandbox too. Full runs log to `workflow/review-output/`.

Pre-registered mutations:
- restore the unseen-but-verified carve-out: AC-4 fails;
- drop the n gate: AC-5 fails;
- score precision on incomplete invocations: AC-3's pipe case is wrongly scored;
- count `unattributable` segments as route 3: AC-3's `$var`/loop cases fail;
- join on raw text instead of shlex tokens: AC-3's escaped-quote case fails;
- join keyed lines without the cwd: AC-3's keyed-line cases fail (a keyed line from another cwd
  must not explain);
- count every candidate-less record as route 2 regardless of `spawned_by`: AC-3's Grep-tool and
  `rmx-grep` rows fail;
- apply the `$` rule after shlex: AC-3's `'alpha$'` row reads unattributable and fails. {#tests}
