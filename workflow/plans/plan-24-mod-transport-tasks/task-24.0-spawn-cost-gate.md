---
gmd: "0.1"
id: task-24.0-spawn-cost-gate
title: "Task 24.0: measure what each hook process costs before it runs a line of refmatrix, for one week, against bands written before the data"
tags: [task, measurement, hooks, telemetry, spawn, plan-24, gate]
metadata:
  node_type: task
  status: pending
  created: 2026-10-20
  updated: 2026-10-20
---

# Task 24.0: the spawn-cost gate {#root}

> Plan: [plan-24-mod-transport](../plan-24-mod-transport.md)
> Status: Pending (spec drafted 2026-10-20; ranges pre-registered here, before any data).
> Depends on: — (independent of 3.7; touches telemetry, hooks.py's generated env and an eval
> script only)
> Feeds: plan-24 Phase 1 scope ([[plan-24-mod-transport#phase-1]]); the held items in
> [[plan-review-2026-10-14#t13-mod-gate]]

rel: part-of -> [[plan-24-mod-transport]]
rel: implements -> [[exploration-claude-code-mod-transport#gate]]
rel: related-to -> [[feedback_go_no_go_ranges_not_predrop]]
rel: related-to -> [[feedback_measure_the_path_users_run]]
rel: related-to -> [[feedback_no_raw_prompts_in_public_repo]]

## Why {#why}

`cli.log`'s `latency_ms` is timed by `log_query` from `__enter__` (`telemetry.py` ~546), after
the interpreter has started and imported refmatrix, so a 0.14 s process records `focus hook` as
1 ms ([[exploration-claude-code-mod-transport#measured-spawn]]). The question plan-24 rests on —
how much of a prompt's wall time is the turn waiting on `rmx` processes STARTING — is invisible
to the telemetry that exists. And the settings show the cost is on the hot path: `focus hook`
runs on BOTH PreToolUse and PostToolUse for every Edit/Write/Read/Bash/Grep/Glob call, neither
async. {#why-lead}

## Requirements {#requirements}

1. **R1 — spawn time per process.** Every `cli.log` row gains `spawn_ms` = (the wall time at
   `cli_entry`'s first statement) − (the kernel's process start time,
   `psutil.Process().create_time()`), and `import_ms` = (`log_query.__enter__`'s wall time) −
   (`cli_entry`'s first statement). The `cli_entry` timestamp is taken with `time.time()` as its
   FIRST statement, before any refmatrix import it triggers; `psutil` is imported lazily when the
   row is written, so it adds nothing to the time it measures. A failure to read the start time
   records `spawn_ms: null` plus `spawn_error` naming why — never a silent omission and never a
   failed command (telemetry never fails what it describes). {#r1}
2. **R2 — psutil is a declared dependency.** Added to `pyproject.toml`'s runtime dependencies
   (user, 2026-10-20: "we can install psutil"); installed into `.venv-eval` and the deploy venv as
   part of the deploy; `discovery._rss_mb`'s "no psutil dependency" note is left as it is (out of
   scope). {#r2}
3. **R3 — the hook's event and blocking class come from the generator.** `hooks.py` already
   prefixes every generated rmx hook with `HOOK_ENV` (`export RMX_INVOCATION_SOURCE=hook; `). It
   now also exports `RMX_HOOK_EVENT=<Claude Code event>` and `RMX_HOOK_BLOCKING=1|0` per entry:
   `0` when the generated command backgrounds itself (`& disown`) or detaches (`--detach`), `1`
   otherwise. Telemetry copies both into the row as `hook_event` and `hook_blocking`. One source:
   the generator that writes the command, never a table re-derived from argv. `rmx install-hooks
   --check` stays clean after a regenerate. {#r3}
4. **R4 — session on every hook row.** The row carries `session` from
   `telemetry.resolve_event_session` (21.1's resolver), so hook rows group by session and prompt
   without assuming one session is active. {#r4}
5. **R5 — the report is an eval script, not a CLI command.** `eval/spawn_gate/report.py --since
   <date> [--until <date>] [--root <store>]` reads `cli.log` and prints, per the [[#ranges]]
   metric: prompts counted (a `UserPromptSubmit` `scan-prompt` row opens a prompt; rows of the
   same session up to the next one belong to it), blocking spawn seconds per prompt (p50 / p95),
   blocking spawn per tool call (`focus hook` pre + post, p50 / p95), all spawn (blocking or not)
   per prompt, `import_ms` p50 / p95 per command, the band and its action, and the two
   non-speed counts ([[#r6]]). Rows without `spawn_ms` are counted and printed as excluded, never
   dropped silently. No new `rmx` command, so no verb is owed. {#r5}
6. **R6 — the non-speed counts, from data that exists.** (a) hook rows whose `out_bytes` exceeds
   10,000 (the hook-output cap, [[reference_hook_output_10k_cap]]); (b) session-resolution
   misses as 21.1 records them. Reported beside the band, not folded into it. {#r6}
7. **R7 — collection.** Deploy R1-R4, re-apply `rmx install-hooks`, then collect ≥ 7 calendar
   days AND ≥ 5 sessions on refmatrix (the only active project, user 2026-10-20). Rows before
   the deploy's timestamp are excluded by `--since`. {#r7}
8. **R8 — what is committed.** The report's numbers and the script; never raw `cli.log` rows or
   argv ([[feedback_no_raw_prompts_in_public_repo]]). The report lands at
   `docs/measurements/spawn-cost-gate.md` (GMD), with the deploy sha, window, and session count.
   {#r8}

## Go/no-go ranges (pre-registered) {#ranges}

Metric: **blocking spawn seconds per prompt, p50** = Σ `spawn_ms` over the prompt's rows with
`hook_blocking = 1`. Written 2026-10-20, before any `spawn_ms` exists. {#ranges-lead}

| p50 blocking spawn per prompt | action (plan-24 Phase 1) |
|---|---|
| < 0.5 s | speed is not a reason. Decide on the defect families alone; if built, scope 24.1-24.5 + 24.7 (identity, verb host, discovery, generated tools, Option C surfaces, distribution); the held items proceed on hooks |
| 0.5 - 2 s | build 24.1-24.7 for the hottest hooks with shell hooks as fallback; re-scope plan-16 onto `tool.call` |
| 2 - 5 s | build plan-24 in full (24.1-24.8); plan-16, 19.6 and 21.2-21.4 retarget to the mod |
| > 5 s | as above, and plan-24 moves ahead of Wave 2 |

A boundary value takes the higher band. The p95 is reported, not banded. {#ranges-tail}

## Acceptance criteria {#acceptance}

1. **AC-1 (R1).** A test runs the real `cli_entry` (CliRunner is not enough: it does not start a
   process) as a subprocess under a short tmp store with `RMX_INVOCATION_SOURCE=hook` and a
   deliberate 200 ms sleep injected before `cli_entry` through a `sitecustomize` on
   `PYTHONPATH`; the row's `spawn_ms` is ≥ 200 and `import_ms` is > 0. RED at base. {#ac-1}
2. **AC-2 (R1).** With `psutil.Process` made to raise, the command still exits 0 and the row has
   `spawn_ms: null` and a non-empty `spawn_error`. {#ac-2}
3. **AC-3 (R3).** For every entry the generator emits, the command exports `RMX_HOOK_EVENT` equal
   to the entry's event and `RMX_HOOK_BLOCKING` equal to 0 exactly for the backgrounded /
   detached commands; a test walks the generated config. `install-hooks --check` is clean after
   regenerate. {#ac-3}
4. **AC-4 (R4, R5).** A fixture `cli.log` (synthetic rows, no real argv) with two interleaved
   sessions, a non-blocking row, and a row lacking `spawn_ms` produces the exact per-prompt sums,
   the right band, and the excluded count. A boundary fixture at exactly 0.5 s reports the
   0.5-2 s band. {#ac-4}
5. **AC-5 (R6).** The fixture's rows with `out_bytes` 10,001 and 10,000 count 1 truncation.
   {#ac-5}
6. **AC-6 (R7, R8).** After the window, `docs/measurements/spawn-cost-gate.md` exists, lints
   clean, names the deploy sha, window, session and prompt counts and the band, and contains no
   argv. The plan-24 amendment ([[plan-24-mod-transport#phase-1]]) cites it. {#ac-6}

## Test strategy {#test-strategy}

New `tests/test_task24_0_spawn_gate.py`: AC-1 and AC-2 as subprocess tests under 23.0's sandbox;
AC-3 over `hooks.py`'s generated config; AC-4 and AC-5 against `eval/spawn_gate/report.py` with
a synthetic `cli.log` fixture committed under `tests/fixtures/spawn_gate/`. RED run first, logged
to `workflow/review-output/`. No mocks of the function under test; `psutil.Process` is replaced
only in AC-2 and registered in `workflow/test_mock_registry.md`. {#test-strategy-body}

## Files to modify {#files}

| file | change |
|---|---|
| `pyproject.toml` | `psutil` runtime dependency (R2) |
| `src/refmatrix/cli.py` | `cli_entry` records its first-statement wall time (R1) |
| `src/refmatrix/telemetry.py` | `spawn_ms`, `import_ms`, `spawn_error`, `hook_event`, `hook_blocking`, `session` on rows (R1, R3, R4) |
| `src/refmatrix/hooks.py` | per-entry `RMX_HOOK_EVENT` / `RMX_HOOK_BLOCKING` in the generated env (R3) |
| `eval/spawn_gate/report.py` | the report (R5, R6) |
| `tests/test_task24_0_spawn_gate.py`, `tests/fixtures/spawn_gate/` | AC-1..AC-5 |
| `docs/measurements/spawn-cost-gate.md` | the result (AC-6) |
