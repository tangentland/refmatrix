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
- Fold of ch-bsd T0.8 r1 (ruling L143), on top of red-t08's `aca629c` / `c168f31`:
  - `#m1`: the comment over `CLI_QUERY_PAIR_WINDOW_S` names `rec.emit()` and gives the measured
    bound ([[#ts-window-bound]]).
  - `#m2`: recorded in [[#m8-1-two-nodes]]. No code change.
  - `#m3`: the unreachable, uncounted `if ch is None: continue` in
    `pair_cli_recalls_with_query_log` is removed. The docstring states the precondition: every
    query row is flagged, which the report's `rec` filter guarantees. It also says an unflagged
    row's end row is counted on the cli.log leg.
  - The optional `query_rows_unpaired` counter is not added (lead, L143).

### Direction of the `ts` window {#ts-window}

L130 says "`ts` within 1 s". GREEN pairs only an end row 0 to 1 s AFTER its query row, not 1 s
either side. Both rows are stamped at second precision, and `log_query.__exit__` runs inside
`main()` before `cli_entry`'s `finally` writes the end row, so an end row earlier than its query
row is not produced by one call. The narrower window cannot pair a later call's end row with an
earlier call's query row. The lead may rule it symmetric; the RED node passes either way.

The ordering proves only the sign, not the 1 s bound (ch-bsd T0.8 r1 `#m1`, ruling L143).
Between the two stamps `memory_recall` runs `rec.emit()` (`cli.py:12746`), and `cli_entry`'s
`finally` then runs `render_phase_report` and `_root()`. Under load that can pass 1 s, and the
pair is lost, so the call is counted on both legs. The bound comes from measurement: ch-bsd
copied the live logs on 2026-11-15 and found 613 query-to-end gaps, 610 at 0 s and 3 at 1 s.
Widening the window to 2, 3, 5, 10 or 30 s paired no further row, while recall latency reached
p95 3.6 s and max 10.8 s. The comment over `CLI_QUERY_PAIR_WINDOW_S` now says this. {#ts-window-bound}

## Acceptance {#acceptance}

| AC | Node | Log | Result |
|---|---|---|---|
| AC-8.1 | `tests/test_task21_1_agent_usage_report.py::test_ac6_frozen_fixture_prints_the_exact_counts` | `workflow/review-output/t0.8/green-file.log` | PASSED |
| AC-8.1 | `tests/test_task21_1_agent_usage_report.py::test_ac6_cli_log_recalls_are_split_per_channel` | `green-file.log` | PASSED |
| AC-8.1 (fixture 201 / 6 / 3 / 34, L130) + AC-8.2 | `tests/test_task21_1_agent_usage_report.py::test_t0_8_a_call_in_cli_log_and_query_log_is_counted_once` | `green-file.log` | PASSED |

### M8.1 now fails two nodes, not three {#m8-1-two-nodes}

The RED map (`red-report.md#l130`) recorded M8.1 failing three nodes. With this GREEN it fails
two (ch-bsd T0.8 r1 `#m2`, ruling L143): `test_ac6_cli_log_recalls_are_split_per_channel` (`:434`
`chan("prompt_recall", 5)` → `E assert []`) and the new node's fixture block (`:551`
`chan(fx, "prompt_recall", 201)` → `E assert []`).
`test_ac6_frozen_fixture_prints_the_exact_counts` survives M8.1. Under that mutation the
per-channel line reads `cli.log memory_recall recall: 244 invocation hook=210 unknown=34`. The
test accepts any line that contains "recall" and the word `34`, and the per-invocation figure
`unknown=34` meets that. AC-8.1 still fails under M8.1, now through the L130 fixture block. No
test was edited (R8.3). The per-invocation breakdown is kept because it is 21.1 R7's own
per-invocation rule. {#m8-1-two-nodes-body}

## Runs {#runs}

All at the GREEN working tree on `102db9a` + the `telemetry.py` change (committed as the GREEN
commit), each wrapped in `/usr/bin/lockf /private/tmp/claude-501/rmx-test-lane.lock`.

| Run | Log | Exit | Collected | Result | SkipGate |
|---|---|---|---|---|---|
| owned file | `workflow/review-output/t0.8/green-file.log` | 0 | 34 | 34 passed / 0 failed / 0 skipped | none |
| verify set | `workflow/review-output/t0.8/green-verify.log` | 0 | 706 | 706 passed / 0 failed / 0 skipped | none |
| owned file, after the L143 fold (red `c168f31` + M1-M3) | `workflow/review-output/t0.8/green-r1-file.log` | 0 | 41 | 41 passed / 0 failed / 0 skipped | none |
| verify set, after the L143 fold | `workflow/review-output/t0.8/green-r1-verify.log` | 0 | 713 | 713 passed / 0 failed / 0 skipped (856.77 s) | none |

The first two rows ran at `102db9a` plus the GREEN change. The last two ran at `c168f31` plus the
M1-M3 fold, and both printed a `collected` line.

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
