---
gmd: "0.1"
id: impl-task-3.5-r8-remedy
title: "Task 3.5: one global-write helper, absent is not busy on the global legs"
tags: [implementation, plan-3, remedy, bsd, verbs, search]
metadata:
  node_type: implementation-summary
  date: 2026-10-19
---

# Task 3.5: plan-3 r8 remedy {#root}

rel: implements -> [[task-3.5-r8-remedy]]
rel: evidence-for -> [[bsd-plan3-verbs-parity-r8-d4bf001#s-2]]
rel: evidence-for -> [[bsd-plan3-verbs-parity-r8-d4bf001#m-1]]
rel: amends -> [[impl-remedy-plan-3-r8]]
rel: part-of -> [[plan-3-verbs-parity]]

TDD GREEN for the RED group committed at `0965546` (`tests/test_task3_5_r8_remedy.py` and the
two tightened tests in `tests/test_plan3_remedy_r7.py`). #s-1 and #s-3 are test-side and were
already GREEN at HEAD. This step is the #s-2 production change and the #m-1 doc fixes. No tests
were written in this step.

## What changed {#changes}

- **`verbs.global_write(op, args, *, timeout=None) -> dict`** is now the one path from a verb to
  the global store's daemon for a write. `memory_add(to_global=True)` and `memory(action=
  "promote")` both call it. It classifies the global daemon before writing, with
  `discovery.daemon_status`:
  - **up**: one write.
  - **busy** (a live rmx pid that does not answer ping): `VerbBusyError`. It is never spawned
    over and never called "not running".
  - **absent**: `hub.ensure_global_daemon(wait_for_ready=<what is left>, errors=…)` starts it.
    If that fails, the result is `VerbAbsentError("global store daemon not running at … and
    could not be started (spawn failed: …)")`.
  With a `timeout`, the probe, the spawn readiness and the write all fit inside that budget,
  and the write is one attempt (`retries=0`). With `timeout=None` (`memory add --global`) the
  documented unbounded wait is kept. A transport `FileNotFoundError` / `ConnectionRefusedError`
  on the write is reported as "not running". A timeout is reported as "did not answer within".
- **`hub.ensure_global_daemon(*, wait_for_ready=30.0, errors=None)`**: the readiness window
  is now a parameter, and the spawn failure is handed back to the caller as well as logged
  to hub.log.
- **`search._global_leg_reason(e)`**: `federated_where`'s global leg now words its skip
  reason from the exception type. Absent or refused gives "global store daemon not running".
  A timeout gives "did not answer within Ns". Anything else gives "failed (Type: msg)".
- **#m-1 / AC-10**: the amendment line was added to [[impl-remedy-plan-3-r8#third-caller]]
  (`6675d17` / bug-069 fixed the third caller, not r8). The `canon_find` comment now reads
  "one of three consumers".

## Per-AC status {#acs}

| AC | Status | Evidence |
|----|--------|----------|
| AC-1 (M4) promote bound = budget + 3 s | GREEN | r7 test passes; the global write's bound is the remaining budget |
| AC-2 (M10) keyword leg reports alone | GREEN (at HEAD; test-side) | |
| AC-3 (M12) omnibox zero-hit `skipNote` | GREEN (at HEAD; test-side) | |
| AC-4 (M8) unconditional canon assertion | GREEN | |
| AC-5 cold promote starts the global daemon, row lands | GREEN | real spawn inside the ~10 s budget |
| AC-6 one helper | GREEN | `global_write` spy sees both commands |
| AC-7 spawn fails → "not running", no errno, inside budget + 3 s | GREEN | |
| AC-8 absent / refused → "not running"; held → "did not answer within" | GREEN | |
| AC-9 real-daemon `--degree` | GREEN; registry row already names it | |
| AC-10 doc-only | DONE | |
| AC-11 all plan-3 files | GREEN except the one flagged in [[impl-task-3.4-internal-cli-allowlist#flag]] | `workflow/review-output/task3.4-3.5-green-plan3.log` |

## Mutation check {#mutation}

Log: `workflow/review-output/task3.4-3.5-mutation.log`. Each mutant was applied to the committed
GREEN tree, run, and then reverted with `git checkout -- src` and a `__pycache__` purge.

| mutant | killed by |
|--------|-----------|
| `global_write` never starts an absent daemon | `test_promote_starts_an_absent_global_daemon…`, `…share_one_global_write_helper` |
| `_global_leg_reason` loses the absent/refused branch | `test_where_calls_an_absent…`, `test_where_calls_a_refused…` |
| promote calls `hub.global_call` directly (r8 shape) | three #s-2 tests |
| task 3.4: drop `CLI_ACTIONS[task swap]` | `test_every_invocable_cli_path_is_classified_exactly_once` |
| task 3.4: `memory forget` back to `_memory_daemon_call` | `test_cli_action_twin_calls_its_dispatcher_verb[memory-forget]` |
| task 3.4: add a LEGACY key (`memory get`) | `test_every_invocable_cli_path_is_classified_exactly_once` |
| **`verbs.memory` ignores an explicit write `timeout`** | **SURVIVES** (`test_verb_parity`, `test_verbs_migrated`, `test_memory_bulk_forget`, `test_mcp_tools`, `test_mcp_parity`). The AC-6 recorder replaces `verbs.memory`, so it proves the CLI passes 600 s but not that the verb uses it. Flagged for `ch-test-engineer`. |

## Notes for review {#notes}

- `spawn_daemon_subprocess` bounds its launcher with `wait_for_ready + 5 s`. A launcher that
  hangs (rather than fails) can overrun promote's budget by up to 5 s. No test covers that
  state. It is not widened here.
- ~~`verbs._call` still reports any transport error as "did not answer … busy"~~. This was
  closed by the amendment below.

## Amendment: one transport classifier (#req-amend, AC-12..16) {#amend}

rel: implements -> [[task-3.5-r8-remedy#req-amend]]

This is the follow-up GREEN for the RED group the test engineer committed at `917ddc5`.
`verbs.classify_transport_error(e, *, op, root, timeout) -> VerbError` is now the ONLY place
that turns a `daemon.call` transport exception into a message and an error type:

- **missing or refused socket** (`FileNotFoundError` / `ConnectionRefusedError`):
  `VerbAbsentError`, "daemon not running for <root> …".
- **`OSError` "AF_UNIX path too long"**: a plain `VerbError` saying the socket path is too long
  and the op was not sent. It is deliberately NOT absent, because absent permits the in-process
  store fallback (Q11).
- **a real timeout** (`TimeoutError` / `socket.timeout`): `VerbBusyError`, "did not answer
  within Ns".
- **anything else** (reset, broken pipe, empty reply): `VerbBusyError` naming the type and
  message. That is the classification `_call` always gave these errors.

Three callers use it. Each raises or renders what the classifier returns:

- `verbs._call` raises its result.
- `verbs.global_write` re-raises the same type with a "global store:" prefix. Its own
  isinstance ladder from the first 3.5 GREEN is removed.
- `search._global_leg_reason` renders the result (it calls `verbs.classify_transport_error`
  at call time, so the shared-classifier spy sees it).

The write-timeout pin and the bulk-forget warning label were already implemented in `5fcc3db`.
The amendment tests pass against that code. This closes the mutant that the
[[#mutation]] table recorded as surviving. `tests/test_lance_drop_failures_loud.py`'s forget
test was moved to the `verbs.memory` seam by the test engineer.

Runs:

- the two files: `workflow/review-output/task3.5-amend-green-targets.log`, 32 passed;
- the plan-3 files: `workflow/review-output/task3.5-amend-green-plan3.log`, 502 passed and 1
  failed. The failure was `test_plan3_remedy_r4::test_promote_digest_is_typed_busy_on_a_held_writer`:
  the first draft of the timeout message carried the class name `TimeoutError`, which r4 pins
  must not leak. The message now carries the exception's own words, as `_call` always did.
  The re-run of r4, r5, r7, the 3.5 file and the lance file is 67 passed
  (`task3.5-amend-green-recheck.log`);
- the full suite: `workflow/review-output/task3.5-amend-green-full.log`.
