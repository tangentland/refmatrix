---
gmd: "0.1"
id: task-24.0-hook-cost-baseline
title: "Task 24.0: a before/after baseline of what each hook process costs before it runs a line of refmatrix — a measurement, not a gate"
tags: [task, measurement, hooks, telemetry, spawn, plan-24, baseline]
metadata:
  node_type: task
  status: pending
  created: 2026-10-20
  updated: 2026-10-20
---

# Task 24.0: the hook-cost baseline {#root}

> Plan: [plan-24-mod-transport](../plan-24-mod-transport.md)
> Status: Pending (spec drafted 2026-10-20; re-scoped the same day from a gate to a baseline —
> the user: "the spawn cost is not the primary reason to make the transition. The main reason is
> tighter integration").
> Depends on: — (independent of 3.7; touches telemetry, hooks.py's generated env and an eval
> script only)
> Feeds: plan-24's secondary benefit, stated with numbers ([[plan-24-mod-transport#goals-tail]]);
> nothing waits on it

rel: part-of -> [[plan-24-mod-transport]]
rel: implements -> [[exploration-claude-code-mod-transport#gate]]
rel: part-of -> [[plan-24-mod-transport#goals-tail]]
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
async.
It decides nothing: plan-24 is built for integration (D0). It exists so the spawn cost the mod
removes is stated with a measured before and after, rather than the arithmetic estimate in the
exploration. The BEFORE window must open before the mod lands, which is why it starts now.
{#why-lead}

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
5. **R5 — the report is an eval script, not a CLI command.** `eval/hook_cost/report.py --since
   <date> [--until <date>] [--root <store>]` reads `cli.log` and prints, per the [[#report]]
   metric: prompts counted (a `UserPromptSubmit` `scan-prompt` row opens a prompt; rows of the
   same session up to the next one belong to it), blocking spawn seconds per prompt (p50 / p95),
   blocking spawn per tool call (`focus hook` pre + post, p50 / p95), all spawn (blocking or not)
   per prompt, `import_ms` p50 / p95 per command, and the two non-speed counts ([[#r6]]). Run
   over the before window and the after window, it prints both and their difference. Rows without `spawn_ms` are counted and printed as excluded, never
   dropped silently. No new `rmx` command, so no verb is owed. {#r5}
6. **R6 — the non-speed counts, from data that exists.** (a) hook rows whose `out_bytes` exceeds
   10,000 (the hook-output cap, [[reference_hook_output_10k_cap]]); (b) session-resolution
   misses as 21.1 records them. Reported beside the spawn numbers. {#r6}
7. **R7 — collection, before and after.** BEFORE: deploy R1-R4, re-apply `rmx install-hooks`,
   collect ≥ 7 calendar days AND ≥ 5 sessions on refmatrix (the only active project, user
   2026-10-20); rows before the deploy's timestamp are excluded by `--since`. AFTER: the same
   window once 24.6 moves the hot hooks into the mod; the mod's own calls carry no `spawn_ms`
   (no process), so the after window measures what is LEFT on shell hooks and the spawns 24.6
   falls back to. {#r7}
8. **R8 — what is committed.** The report's numbers and the script; never raw `cli.log` rows or
   argv ([[feedback_no_raw_prompts_in_public_repo]]). The report lands at
   `docs/measurements/hook-cost-baseline.md` (GMD), with the deploy sha, window, and session count.
   {#r8}

## What is reported, and why there are no bands {#report}

Metric: **blocking spawn seconds per prompt** = Σ `spawn_ms` over the prompt's rows with
`hook_blocking = 1`, p50 and p95, before and after. No go/no-go bands: the 2026-10-20 draft had
four, written as a gate on whether to build plan-24; the user's D0 removed the gate, and a band
with no decision behind it is decoration. Whether concurrent hooks of one event overlap in wall
time (so the sum overstates the wait) is stated in the report from the rows' timestamps, not
assumed either way. {#report-body}

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
   and the excluded count; a before/after pair of fixtures prints both windows and their
   difference. {#ac-4}
5. **AC-5 (R6).** The fixture's rows with `out_bytes` 10,001 and 10,000 count 1 truncation.
   {#ac-5}
6. **AC-6 (R7, R8).** After the window, `docs/measurements/hook-cost-baseline.md` exists, lints
   clean, names the deploy sha, window, session and prompt counts, and contains no argv; the
   after-window section is added once 24.6 has deployed. {#ac-6}

## Test strategy {#test-strategy}

New `tests/test_task24_0_hook_cost.py`: AC-1 and AC-2 as subprocess tests under 23.0's sandbox;
AC-3 over `hooks.py`'s generated config; AC-4 and AC-5 against `eval/hook_cost/report.py` with
a synthetic `cli.log` fixture committed under `tests/fixtures/hook_cost/`. RED run first, logged
to `workflow/review-output/`. No mocks of the function under test; `psutil.Process` is replaced
only in AC-2 and registered in `workflow/test_mock_registry.md`. {#test-strategy-body}

## Files to modify {#files}

| file | change |
|---|---|
| `pyproject.toml` | `psutil` runtime dependency (R2) |
| `src/refmatrix/cli.py` | `cli_entry` records its first-statement wall time (R1) |
| `src/refmatrix/telemetry.py` | `spawn_ms`, `import_ms`, `spawn_error`, `hook_event`, `hook_blocking`, `session` on rows (R1, R3, R4) |
| `src/refmatrix/hooks.py` | per-entry `RMX_HOOK_EVENT` / `RMX_HOOK_BLOCKING` in the generated env (R3) |
| `eval/hook_cost/report.py` | the report (R5, R6) |
| `tests/test_task24_0_hook_cost.py`, `tests/fixtures/hook_cost/` | AC-1..AC-5 |
| `docs/measurements/hook-cost-baseline.md` | the result (AC-6) |
