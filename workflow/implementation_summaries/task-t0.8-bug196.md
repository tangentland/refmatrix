---
gmd: "0.1"
id: impl-task-t0-8-bug196
title: "T0.8 GREEN: the cli.log recall leg is split per channel and counts only calls query.log does not hold (bug-196)"
tags: [implementation-summary, t0, task-29.4, telemetry, agent-usage, bug-196]
metadata:
  node_type: implementation-summary
  status: green
  created: 2026-11-15
---

# T0.8 GREEN: cli.log recall leg per channel, each call once {#root}

rel: implements -> [[task-t0-suite-trust-sweep#t0-8]]
rel: implements -> [[task-t0-suite-trust-sweep#r8-1]]
rel: implements -> [[task-t0-suite-trust-sweep#r8-2]]
rel: derives-from -> [[task-t0-suite-trust-sweep#r0-1]]
rel: derives-from -> [[t0-8-red-report#l130]]
rel: derives-from -> [[bug_registry]] {bug: "bug-196"}

Plan-29 task 29.4, stage 2. Branch `task-t0.8-bug196` in `/Volumes/littlebig/refmatrix-t08-green`,
cut from the RED tip `102db9a` (RED base `c4b44d0`). Ruling L130. No test was authored or edited
by GREEN; the RED author's sketch logs were not read. Mutations M8.1 and M8.2 are the lead's and
are not recorded here. `workflow/bug_registry.md` row 196 is left to the lead (registry rows are
the lead's, `workflow/ORCHESTRATION.md#registry`).

## R0: cited sites re-read at `c4b44d0` {#r0}

| Citation | At `c4b44d0` | Status |
|---|---|---|
| `recall_channel` `telemetry.py:1313` | `:1313` | holds |
| `agent_usage_report` `:1866`, single total line | `:1866`; total printed at `:1982` (`cli.log: memory recall commands=`) | holds |
| query.log `ts` stamped in `log_query.__exit__` | `telemetry.py:599` | holds |
| cli.log end row `ts` stamped in `log_cli_invocation` | `telemetry.py:380`, called from `cli_entry`'s `finally` at `cli.py:15228`, after `main()` returns | holds |
| recall flags on the query.log row | `cli._RecallCall.close_row`, `cli.py:13328` | holds |
| AC-8.1 breakdown 201 / 6 / 3 / 34 | reproduced by the GREEN report over the fixture (`green-fixture-report.log`) | holds |

## What changed {#changes}

Only `src/refmatrix/telemetry.py`:

- `from datetime import datetime` (module import).
- `cli_recall_channel(row: dict) -> str | None` (new, `:1359`): the R11 channel of a cli.log
  `memory recall` end row, via the existing `recall_channel` fed from the argv flag names
  (`--session-start`, `--stdin-json`, `--recent`) and `source`. None for any other command.
- `_log_ts_seconds(ts: str | None) -> float | None` (new, `:1380`): parses a row's `ts`; None
  when it does not parse.
- `CLI_QUERY_PAIR_WINDOW_S = 1` (new, `:1394`).
- `pair_cli_recalls_with_query_log(cli_rows: list[dict], query_rows: list[dict]) ->
  tuple[list[dict], int, int, int]` (new, `:1397`): returns (unpaired cli rows, paired count,
  cli rows with an unparseable `ts`, query rows with an unparseable `ts`). The key is ruling
  L130's: cwd + channel + invocation (`invocation` on query.log, `source` on cli.log) + `ts`, the
  end row 0 to 1 s after the query row. No new log field. One-to-one: each query row absorbs at
  most one end row, end rows taken in `ts` order against the earliest eligible query row.
- `agent_usage_report` (signature unchanged): the cli.log leg's single
  `cli.log: memory recall commands=<n>` line is replaced by one accounting line and one line per
  channel, for the calls query.log does not hold. Over the frozen fixture:

  ```
  cli.log: memory_recall end_rows=244 paired_with_query_log=0 counted=244 ts_unparseable=0 query_ts_unparseable=0 internal_excluded=0 excluded_test_rows=0 unparseable=0
    cli.log memory_recall precompact: 3 invocation hook=3
    cli.log memory_recall prompt_recall: 201 invocation hook=201
    cli.log memory_recall recall: 34 invocation unknown=34
    cli.log memory_recall session_start: 6 invocation hook=6
  ```

  `internal_excluded` is new: an `invocation=internal` cli.log recall row was skipped uncounted
  before; it is now counted.

### Direction of the `ts` window {#ts-window}

L130 says "`ts` within 1 s". GREEN pairs only an end row 0 to 1 s AFTER its query row, not 1 s
either side. Both rows are stamped at second precision, and `log_query.__exit__` runs inside
`main()` before `cli_entry`'s `finally` writes the end row, so an end row earlier than its query
row is not produced by one call. The narrower window cannot pair a later call's end row with an
earlier call's query row. The lead may rule it symmetric; the RED node passes either way.

## Acceptance {#acceptance}

| AC | Node | Log | Result |
|---|---|---|---|
| AC-8.1 | `tests/test_task21_1_agent_usage_report.py::test_ac6_frozen_fixture_prints_the_exact_counts` | `workflow/review-output/t0.8/green-file.log` | PASSED |
| AC-8.1 | `tests/test_task21_1_agent_usage_report.py::test_ac6_cli_log_recalls_are_split_per_channel` | `green-file.log` | PASSED |
| AC-8.1 (fixture 201 / 6 / 3 / 34, L130) + AC-8.2 | `tests/test_task21_1_agent_usage_report.py::test_t0_8_a_call_in_cli_log_and_query_log_is_counted_once` | `green-file.log` | PASSED |

## Runs {#runs}

All at the GREEN working tree on `102db9a` + the `telemetry.py` change (committed as the GREEN
commit), each wrapped in `/usr/bin/lockf /private/tmp/claude-501/rmx-test-lane.lock`.

| Run | Log | Exit | Collected | Result | SkipGate |
|---|---|---|---|---|---|
| owned file | `workflow/review-output/t0.8/green-file.log` | 0 | 34 | 34 passed / 0 failed / 0 skipped | none |
| verify set | `workflow/review-output/t0.8/green-verify.log` | 0 | 706 | 706 passed / 0 failed / 0 skipped | none |

The verify set is `tests/test_verb_parity.py` plus every test file that imports
`refmatrix.telemetry`, found with
`grep -lE "refmatrix\.telemetry|from refmatrix import .*\btelemetry\b|from refmatrix\.telemetry import" tests/*.py`
(19 files) and cross-checked against `grep -lw telemetry tests/*.py tests/sandbox_site/*.py`: the
four extra hits (`task21_1_support.py`, `test_learn_broker_bounded.py`, `test_task_cli_session.py`,
`test_verb_parity.py`) hold the word but no import of the module.

No failure in either run, so there is no E line to compare with `release-0.84.0-full.log`. Neither log prints a `collected` line (`-q`); the collected count is the sum of the outcomes, with no deselected or skipped tests. The verify set ran 20 files, 706 tests, in 460.34 s.

## Not done here {#not-done}

- Mutations M8.1, M8.2: the lead's.
- `workflow/bug_registry.md` row 196: the lead's.
- The spec's `#t0-8-files` names the summary `task-t0.8-bug196-recall-channels.md`; the lead's
  brief named `task-t0.8-bug196.md`, which this file follows.
