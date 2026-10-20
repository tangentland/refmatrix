---
gmd: "0.1"
id: task-24.0-hook-cost-baseline
title: "Task 24.0: a before/after baseline of what each hook process costs before it runs a line of refmatrix — interpreter, fork-safety re-exec and import split, per event instance — a measurement, not a gate"
tags: [task, measurement, hooks, telemetry, spawn, plan-24, baseline]
metadata:
  node_type: task
  status: pending
  created: 2026-10-20
  updated: 2026-10-20
---

# Task 24.0: the hook-cost baseline {#root}

> Plan: [plan-24-mod-transport](../plan-24-mod-transport.md)
> Status: Pending. Drafted 2026-10-20 as a gate, re-scoped the same day to a baseline (the user:
> "the spawn cost is not the primary reason to make the transition. The main reason is tighter
> integration"), revised after ch-bsd [[bsd-plan24-spec-review-cdcfbc3]] ([[#rev-r1]]).
> Depends on: — (independent of 3.7; touches the entry point, telemetry, hooks.py's generated env
> and an eval script)
> Feeds: plan-24's secondary benefit, stated with numbers ([[plan-24-mod-transport#goals-tail]]);
> nothing waits on it

rel: part-of -> [[plan-24-mod-transport]]
rel: depends-on -> [[task-3.7-verb-it-backlog]]
rel: derives-from -> [[bsd-plan24-spec-review-r2-03c2d1f]]
rel: part-of -> [[plan-24-mod-transport#goals-tail]]
rel: derives-from -> [[bsd-plan24-spec-review-cdcfbc3]]
rel: related-to -> [[feedback_measure_the_path_users_run]]
rel: related-to -> [[feedback_no_raw_prompts_in_public_repo]]
rel: related-to -> [[feedback_prefer_existing_infra]]

## Why {#why}

Nothing in `cli.log` sees what a hook costs before refmatrix code runs. Its rows are written by
`telemetry.log_cli_invocation` from `cli_entry`'s `finally` (cli.py ~15069), and `latency_ms` is
taken after imports. The console script (`rmx = "refmatrix.cli:cli_entry"`) imports the package
`__init__` and the 15,085-line `cli.py` BEFORE `cli_entry`'s first statement. Then
`_reexec_for_fork_safety` (cli.py ~14974) `execv`s the whole process again when
`OBJC_DISABLE_INITIALIZE_FORK_SAFETY` is unset, as it is in every generated hook, keeping the same
pid and kernel start time. Measured on deploy by the review: `rmx version` 0.13-0.14 s, 0.07 s
with the variable set; a bare interpreter 0.01 s; `import refmatrix.cli` 0.07 s. And `focus
hook` runs on both PreToolUse and PostToolUse for every Edit/Write/Read/Bash/Grep/Glob call,
neither async. {#why-lead}

It decides nothing: plan-24 is built for integration (D0). It exists so the cost the mod removes
is stated with a measured before and after. The BEFORE window must open before the mod lands.
{#why-tail}

## Requirements {#requirements}

1. **R1 — a tiny entry module stamps time before anything heavy.** The console scripts point at
   a new `refmatrix/_entry.py:main`, which imports only `os`, `sys` and `time`.
   - On pass 1 it records `t_start1 = time.time()`.
   - It performs the fork-safety re-exec itself, before importing `refmatrix.cli`, passing pass
     1's stamp in `RMX_T_PASS1`.
   - On the final pass it records `t_entry`, then imports `refmatrix.cli` and calls `cli_entry`.

   `_reexec_for_fork_safety` moves into `_entry.py`, so there is ONE re-exec site; behaviour is
   unchanged: re-exec when the variable is unset. {#r1}
2. **R2 — the split, from the kernel start time we already read.** The process's kernel start time
   comes from `stm._proc_info(os.getpid())` (libproc on macOS, no subprocess, ~1 µs), not a new
   dependency. (The user allowed psutil, 2026-10-20; it isn't needed.) Each row records, in ms:
   - `interp_ms` = pass-1 stamp − kernel start;
   - `reexec_ms` = final-pass `t_entry` − pass-1 stamp (0 when there was no re-exec);
   - `import_ms` = time from `t_entry` to `cli_entry`'s first statement;
   - `t_start_ms` / `t_end_ms` = epoch ms of the kernel start and of the row write.

   These field names, `hook_event`, `hook_blocking`, `session`, `prompt_id` and `agent_id` are ONE
   row schema shared with the verb host's mod rows (24.2 R9), defined once in `telemetry.py`
   (`HOOK_ROW_FIELDS`) and validated by one schema test. `hook_event` takes a value from
   `telemetry.HOOK_EVENTS`: the Claude Code settings-hook event names (`SessionStart`,
   `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `Stop`, `SubagentStop`, `PreCompact`) plus the
   mod-only `SessionAppend` and `ModelTool`; the mod maps its engine events onto these names (24.6
   d16). `prompt_id` is null on shell rows (the report assigns them to prompts by time, R5) and is
   the mod's `<session>:<n>` per-session prompt counter on mod rows. A failed start-time lookup records those fields `null` plus `timing_error` with the reason. It
   never fails the command and never silently omits the field. {#r2}
3. **R3 — blocking is per invocation, set by one generator helper.** `hooks.py` emits every rmx
   invocation through ONE helper that prefixes `RMX_HOOK_EVENT=<event>` and `RMX_HOOK_BLOCKING=1|0`
   to THAT invocation (not once per entry). `0` only for a command backgrounded with `& disown`.
   A `--detach` parent blocks until it forks, so it is `1`. The p20-0 guardrail entry's `rmx`
   children get the same prefix, and so does every generated entry, the ones lacking `HOOK_ENV`
   today included. `install-hooks --check` stays clean after a regenerate. {#r3}
4. **R4 — session from the envelope, never guessed per row.** Commands that already read the hook's
   stdin envelope (`focus hook`, `scan-prompt`, `memory recall --stdin-json`) stash its
   `session_id` for the row. Other rows carry `session: null` and record NO resolution miss. The
   pid-pointer fallback is not used for telemetry rows, because it races the concurrent input hook
   after `/clear` and `/resume`. {#r4}
5. **R5 — per event instance, not a plain sum.** `eval/hook_cost/report.py --since <date>
   [--until <date>] [--root <store>]` reads `cli.log` and groups rows by session into prompts.
   - A prompt opens at the EARLIEST `UserPromptSubmit` row of a burst, by `t_start_ms`, not by
     which row was written first; rows sharing one event inside one burst are one event instance.
   - A mod row (`invocation: "mod"`) joins the prompt its `prompt_id` names; its cost is its
     `wall_ms` (no pre-code fields), reported as the in-engine wait beside the shell's.
   - Per prompt, the report prints:
     - **the wait**: Σ over blocking event instances of the LONGEST row's pre-code time
       (`interp_ms + reexec_ms + import_ms`), since hooks of one event run in parallel;
     - the plain sum beside it, labelled as an upper bound;
     - each component separately.
   - It also prints:
     - per tool call: `focus hook` pre and post;
     - `import_ms` p50 / p95 per command;
     - the R6 counts.
   - Rows without timing fields are counted and printed as excluded.
   - Intent rows (`focus hook --event intent` and the like) are grouped under the prompt that
     contains them.

   It is not a CLI command, so no verb is owed. {#r5}
6. **R6 — what the metric cannot see, listed.**
   - (a) Hook rows whose `out_bytes` exceeds 10,000 ([[reference_hook_output_10k_cap]]).
   - (b) The hooks that are not `rmx` (enforce-test-to-file, enforce-rmx-grep, grep-rewrite-guard
     via python3, adr-gate, grep-tool-teach) are listed as unmeasured, each with a one-time
     wall-clock timing taken when the report is written. {#r6}
7. **R7 — the mod's calls are rows too, so "after" means something.** The verb host (24.2) writes
   one row per mod call with `invocation: "mod"`, `hook_event`, `session`, a prompt id from the
   mod and `wall_ms`. So the after window has prompts and a cost, and the comparison is the mod's
   per-call wall time against the shell hook's pre-code plus work. {#r7}
8. **R8 — the fork-safety variable is held constant across windows.** Setting
   `OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES` in the generated hook env roughly halves every hook's
   pre-code time with no mod. That fix is NOT this task's work: it is task 3.7's remedy row R-OBJC
   ([[task-3.7-verb-it-backlog]], section "Remedy round 1", decided in the 3.7 clone at 6fd9b7c and not yet merged here: `HOOK_ENV`
   exports `OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES` and `TOKENIZERS_PARALLELISM=false`, with a RED
   test over the generated config), from the user's 2026-10-20 "yes, ship the OBJC fix with 3.7".
   This task depends on it being merged and deployed before the BEFORE window opens (AC-7 checks
   the deployed `HOOK_ENV`). Both windows then have `reexec_ms` ≈ 0 for hook rows, and the mod is
   not credited with it. The report states the fix's deploy sha, and rows earlier than it are
   outside both windows. {#r8}
9. **R9 — collection.**
   - BEFORE: deploy R1-R4, re-apply `rmx install-hooks`, collect ≥ 7 calendar days AND ≥ 5
     sessions on refmatrix (the only active project). `--since` excludes earlier rows.
   - AFTER: the same window once 24.6 is deployed. {#r9}
10. **R10 — what is committed.** The report's numbers and the script, never raw `cli.log` rows or
    argv ([[feedback_no_raw_prompts_in_public_repo]]). The report goes to
    `docs/measurements/hook-cost-baseline.md` (GMD), with the deploy sha, windows, and session and
    prompt counts. {#r10}

## What is reported, and why there are no bands {#report}

Primary number: **pre-code wait per prompt** (R5), p50 and p95, before and after, with the plain
sum as the upper bound. There are no go/no-go bands: the first draft's four were a gate on whether
to build, and D0 removed the gate. {#report-body}

## Acceptance criteria {#acceptance}

1. **AC-1 (R1, R2).** A subprocess test runs the real console script under a short tmp store.
   - The import of `refmatrix.cli` is made to take ≥ 200 ms by a `sitecustomize.py` in a test
     directory on `PYTHONPATH` that installs a `sys.meta_path` finder which sleeps 200 ms when
     `refmatrix.cli` is imported, then defers to the normal finders. No src change and no test
     switch in the package (r2 s8); the finder is registered as a double. It runs at interpreter
     start on both passes of a re-exec, but only the final pass imports `refmatrix.cli`, so the
     sleep lands in `import_ms`.
   - The row's `import_ms` is ≥ 200, and `interp_ms` is < 200.
   - With the variable unset, `reexec_ms` > 0; with it set, `reexec_ms` == 0.

   RED at base. {#ac-1}
2. **AC-2 (R2).** With the start-time lookup made to fail, the command exits 0, and the row has
   `null` timings and a non-empty `timing_error`. {#ac-2}
3. **AC-3 (R3).** A walk of the generated config checks every `rmx` invocation, including those
   inside `( … ) & disown`, `--detach` and p20-0. Each must carry its own `RMX_HOOK_EVENT` /
   `RMX_HOOK_BLOCKING`, with `0` exactly for the disowned ones. `install-hooks --check` is clean.
   {#ac-3}
4. **AC-4 (R4).** A `focus hook` row carries the envelope's `session_id`. A row from a command
   without an envelope carries `null`, and the run records no resolution miss. {#ac-4}
5. **AC-5 (R5, R6).** A synthetic `cli.log` fixture (no real argv) produces exact numbers. It holds:
   - two interleaved sessions;
   - an overlapping trio of UserPromptSubmit rows whose scan-prompt row is written last;
   - a disowned row;
   - an intent row;
   - a row without timings;
   - rows with `out_bytes` of 10,001 and 10,000;
   - two mod rows (`invocation: "mod"`, `hook_event: "UserPromptSubmit"` and `"PreToolUse"`) whose
     `prompt_id` names one of the prompts, and one whose `hook_event` is outside `HOOK_EVENTS`.

   The expected outputs: per-instance-max and plain-sum waits, the prompt opened at the earliest
   row, the mod rows' `wall_ms` attributed to the prompt their `prompt_id` names, the out-of-
   vocabulary row counted as invalid (never silently dropped), the excluded count, and 1
   truncation. Every fixture row validates against `HOOK_ROW_FIELDS` except the invalid one. A before/after pair prints both windows and the
   difference. {#ac-5}
6. **AC-6 (R7).** Listed here, built in 24.2: a mod-invoked verb writes one `invocation: "mod"`
   row carrying session, prompt id and `wall_ms`. {#ac-6}
7. **AC-7 (R9, R10).** After the before window, `docs/measurements/hook-cost-baseline.md` exists,
   lints clean, names sha, window, sessions, prompts and the R8 state, and contains no argv; before
   the window opens, the deployed `~/refmatrix` `hooks.py` `HOOK_ENV` is read and shown to export
   `OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES` (3.7 R-OBJC), and its sha is the one the report names. The
   after section is added once 24.6 has deployed. {#ac-7}

## Test strategy {#test-strategy}

New `tests/test_task24_0_hook_cost.py`: AC-1 and AC-2 as subprocess tests under 23.0's sandbox;
AC-3 over `hooks.py`'s generated config; AC-4 through the real `focus hook` with an envelope on
stdin; AC-5 against `eval/hook_cost/report.py` with fixtures under `tests/fixtures/hook_cost/`.
RED run first, logged to `workflow/review-output/`. The AC-1 `sitecustomize` meta-path finder and
the AC-2 lookup failure are the only doubles, both registered in `workflow/test_mock_registry.md`.
{#test-strategy-body}

## Files to modify {#files}

| file | change |
|---|---|
| `pyproject.toml` | console scripts → `refmatrix._entry:main` (R1) |
| `src/refmatrix/_entry.py` | new: stamps, the one fork-safety re-exec, then `cli_entry` (R1) |
| `src/refmatrix/cli.py` | `_reexec_for_fork_safety` moves out; `cli_entry` stamps its first statement (R1, R2) |
| `src/refmatrix/telemetry.py` | `HOOK_ROW_FIELDS`, `HOOK_EVENTS` (shared with 24.2), `interp_ms`, `reexec_ms`, `import_ms`, `t_start_ms`, `t_end_ms`, `timing_error`, `hook_event`, `hook_blocking`, envelope `session` in `log_cli_invocation` rows (R2-R4) |
| `src/refmatrix/hooks.py` | one per-invocation prefix helper for every generated rmx call (R3) |
| `eval/hook_cost/report.py` | the report (R5, R6, R8) |
| `tests/test_task24_0_hook_cost.py`, `tests/fixtures/hook_cost/` | AC-1..AC-5 |
| `docs/measurements/hook-cost-baseline.md` | the result (AC-7) |

## Revision r1 (2026-10-20, ch-bsd cdcfbc3) {#rev-r1}

| finding | change |
|---|---|
| b2 `spawn_ms` held the import (twice) and `import_ms` missed it; rows come from `log_cli_invocation`, not `log_query` | R1 `_entry.py`, R2 split into interp / reexec / import, AC-1 delay moved into an imported module |
| s1 blocking set per entry, but one entry mixes blocking and disowned calls; `--detach` blocks; p20-0 lacks HOOK_ENV; non-rmx hooks invisible | R3 per-invocation helper, `--detach` = 1; R6(b) lists non-rmx hooks with a one-time timing |
| s2 parallel hooks overstated by a sum; 1 s `ts` written at exit misorders prompts; intent rows | R2 ms start/end; R5 per-instance max, prompt at earliest row, intent rows grouped; AC-5 fixture |
| s3 per-row session lookup races, inflates misses, costs unmeasured time | R4 envelope `session_id`; no miss recorded |
| s4 the after window had no prompts and no mod cost | R7 mod-call rows from the verb host (24.2) |
| m1 psutil unneeded | R2 uses `stm._proc_info` |
| m2 stale `#gate` edge and a wrong `telemetry.py ~546` premise | edge removed; Why rewritten |
| (new) the fork-safety re-exec doubles start-up today and is independent of the mod | R8 held constant / reported apart |

## Revision r2 (2026-10-20, ch-bsd r2 03c2d1f) {#rev-r2}

| finding | change |
|---|---|
| b3 the OBJC fix was anchored to a 3.7 that lacked it | R8 cites 3.7 remedy R-OBJC (clone 6fd9b7c, with its RED test) as the fix, not this task's work; `depends-on` 3.7; AC-7 reads the deployed `HOOK_ENV` before the window opens |
| s7 rows did not join 24.2's | R2: one shared row schema (`HOOK_ROW_FIELDS`), the `HOOK_EVENTS` vocabulary, `prompt_id` from the mod's per-session counter; R5 joins mod rows by `prompt_id`; AC-5 fixture has mod rows and an out-of-vocabulary row |
| s8 AC-1 needed a test switch in src | AC-1: a `sitecustomize` `meta_path` finder sleeps on the `refmatrix.cli` import; no src change |

