---
gmd: "0.1"
id: task-3.5-r8-remedy
title: "Task 3.5: plan-3 r8 remedy — pin the three unguarded closures, classify an absent global store, and graduate the --degree test to a real daemon"
tags: [task, plan-3, remedy, bsd, verbs, search]
metadata:
  node_type: task
  status: approved
  plan: plan-3-verbs-parity
  created: 2026-10-19
---

# Task 3.5: plan-3 r8 remedy {#root}

> Plan: [[plan-3-verbs-parity]]
> Status: Approved
> Depends on: [[task-3.3-plan-3-verbs-parity]] (independent of [[task-3.4-internal-cli-allowlist]])

rel: part-of -> [[plan-3-verbs-parity]]
rel: derives-from -> [[bsd-plan3-verbs-parity-r8-d4bf001]]
rel: implements -> [[bsd-plan3-verbs-parity-r8-d4bf001#s-1]]
rel: implements -> [[bsd-plan3-verbs-parity-r8-d4bf001#s-2]]
rel: implements -> [[bsd-plan3-verbs-parity-r8-d4bf001#s-3]]
rel: implements -> [[bsd-plan3-verbs-parity-r8-d4bf001#m-1]]

## Why {#why}

ch-bsd plan-3 r8 (DIRTY, 0B/4S/1M) found every r7 finding closed in behaviour at `d4bf001`, but
three of those closures fail no test when reverted (mutants M4, M10, M12 survive the whole
plan-3 set; M8 survives its own file behind an `if`); an absent global store is reported as
busy/timed out on two plan-3 legs, and `memory promote` now fails a cold global store with a raw
errno in 0.0 s; and r7 #s-4's real-daemon `--degree` test was dropped without a word. #s-4 is
task 3.4. {#why-lead}

## Requirements {#requirements}

### #s-1 — pin the three unguarded closures (test-side) {#req-s1}

- **M4.** `tests/test_plan3_remedy_r7.py::test_promote_is_bounded_on_the_global_write_too`
  asserts `elapsed < verbs.MEMORY_READ_BUDGET_S + 3.0` (its sibling's bound), so a fixed
  `timeout=30.0` (30.3 s) fails it. The command promises 10 s.
- **M10.** The locate KEYWORD leg reports on its own: `federated_locate(keywords=["held"])` (no
  filename) on an up store with no replica names `(keyword 'held')` in `skipped`.
- **M12.** The omnibox zero-hit branch renders `skipNote`, never a bare "no hits", when stores
  were skipped. app.js is tested by source-level assertion in `tests/test_ui_server.py` (this
  repo runs no JS); the new test follows that pattern on the `if (!hits.length)` branch.
- **M8.** `test_canon_find_does_not_claim_nowhere_when_a_store_could_not_be_read` loses its `if`
  and asserts unconditionally: exit 0, the stderr `# rmx: skipped …` line, and the suffix
  `no live project hosts held_row (1 store skipped — see stderr)`.

### #s-2 — absent is not busy on the global legs {#req-s2}

- **One global-write helper.** `verbs.global_write(op, args, *, timeout=None) -> dict` is the
  only path from a verb to the global store's daemon for a write. `memory_add(to_global=True)`
  and `memory(action="promote")` both call it. `timeout=None` keeps `memory add --global`'s
  documented unbounded behaviour (ensure the daemon, then `global_call` defaults).
  With a `timeout`, the helper ensures the global daemon within that budget (the spawn's
  readiness wait is the remaining budget, not 30 s), then makes ONE attempt (`retries=0`) bounded
  by what is left.
- **Absent → started.** With no global daemon, `rmx memory promote X` starts it the same way
  `memory add --global` does, and the row lands in the global store. No raw errno.
- **Could not start → "not running".** If the spawn fails, the error says the global store
  daemon is not running (`VerbAbsentError`), never `[Errno 2] No such file or directory`.
- **Busy stays busy.** A held global store (answers ping, stalls ops) is not spawned over and is
  not called "not running"; promote still fails inside its budget (#s-1 M4 test).
- **search.py wording.** `federated_where`'s global leg words the reason from the exception
  type: `FileNotFoundError` / `ConnectionRefusedError` → "global store daemon not running";
  `TimeoutError` → "did not answer within Ns". An absent socket is never reported as a timeout.

### #s-3 — the real-daemon `--degree` test {#req-s3}

One test runs `rmx memory get <name> --degree 1` against a REAL daemon spawned on a short
`mkdtemp` root (`Store.init` + `spawn_daemon_subprocess`) — r7's probe shape — and asserts the
body, the `--- context ---` header, the bundle, and no `# rmx:` degradation warning. The
`answering` fixture row in `workflow/test_mock_registry.md` points its graduation at this test.

### #m-1 — record correction (doc-only) {#req-m1}

- `workflow/implementation_summaries/remedy-plan-3-r8.md#third-caller` gains an amendment line:
  the third `_replica_bundle` caller was fixed by `6675d17` (bug-069), not by r8; the r8 merge
  shipped that test red.
- The `canon_find` comment (`cli.py`, "was the last consumer discarding its fan-out's `skipped`
  list") becomes "one of three consumers".

## Acceptance criteria {#acceptance}

1. **AC-1 (M4).** The r7 promote test fails against `timeout=30.0, retries=0` on the global
   write and passes at the `_left(...)` bound. {#ac-1}
2. **AC-2 (M10).** `test_locate_reports_the_keyword_leg_on_its_own` fails when the keyword leg
   stops reading `errs`. {#ac-2}
3. **AC-3 (M12).** `test_the_omnibox_zero_hit_branch_says_which_stores_were_skipped` fails when
   the zero-hit branch renders a plain "no hits". {#ac-3}
4. **AC-4 (M8).** The r7 canon test has no conditional and fails when the nowhere line loses its
   skipped suffix. {#ac-4}
5. **AC-5 (cold promote).** With the global daemon absent, `rmx memory promote held_row` exits 0
   and the row is readable from the global store. RED at HEAD (`[Errno 2]`). {#ac-5}
6. **AC-6 (one helper).** `memory promote` and `memory add --global` both go through
   `verbs.global_write`. RED at HEAD (no such helper). {#ac-6}
7. **AC-7 (cannot start).** With the spawn failing, promote exits non-zero saying "not running"
   with no errno text. RED at HEAD. {#ac-7}
8. **AC-8 (search wording).** Absent and refused global sockets are "not running" in
   `federated_where`'s `skipped`; a held global store is still "did not answer within". The
   first two are RED at HEAD. {#ac-8}
9. **AC-9 (real --degree).** The real-daemon `--degree` test passes; the registry row for
   `tests/test_plan3_remedy_r6.py` names it as the graduation. {#ac-9}
10. **AC-10 (#m-1, doc-only).** The summary amendment line and the `cli.py` comment fix land; no
    test. {#ac-10}
11. **AC-11.** All plan-3 test files (r2-r7, `test_plan3_remedy`, `test_verb_parity`,
    `test_mcp_parity`, `test_verbs_migrated`, `test_locate`, `test_surface_parity`,
    `test_ui_server`, the new file) are green. {#ac-11}

## Files to modify {#files-to-modify}

| File | Change |
|------|--------|
| `src/refmatrix/verbs.py` | `global_write`; `memory_add(to_global)` and promote call it |
| `src/refmatrix/hub.py` | `ensure_global_daemon` accepts a readiness budget (if the helper needs it) |
| `src/refmatrix/search.py` | global leg reason worded from the exception type |
| `src/refmatrix/cli.py` | `canon_find` comment (#m-1) |
| `tests/test_plan3_remedy_r7.py` | M4 bound, M8 unconditional (test engineer) |
| `tests/test_task3_5_r8_remedy.py` | new (test engineer) |
| `workflow/test_mock_registry.md` | new doubles; r6 row graduation → the real-daemon test |
| `workflow/implementation_summaries/remedy-plan-3-r8.md` | #m-1 amendment |

## Test strategy {#test-strategy}

RED tests: `tests/test_task3_5_r8_remedy.py` and the two tightened r7 tests. #s-1's tests pin
behaviour that is already correct at HEAD, so their RED proof is the r8 mutant (M4, M8, M10,
M12) applied in a scratch copy; #s-2's are RED at HEAD; #s-3's is a graduation test, GREEN at
HEAD, with its RED proof by mutation of the `--degree` tail. RED run:
`workflow/review-output/task3.4-3.5-red.log`.

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation check noted in the implementation summary at
  `workflow/implementation_summaries/task-3.5-r8-remedy.md`.
- `@ch-bsd` re-review of plan-3 CLEAN before the plan flips to `completed`.
