---
gmd: "0.1"
id: impl-task-3.6-r9-remedy
title: "Task 3.6: plan-3 r9 remedy — every store-daemon transport site through one classifier, one spawn deadline, bug-135 measured and fixed, four LEGACY reasons made true"
tags: [implementation, plan-3, remedy, bsd, verbs, search, daemon]
metadata:
  node_type: implementation-summary
  date: 2026-10-19
---

# Task 3.6: plan-3 r9 remedy {#root}

rel: implements -> [[task-3.6-r9-remedy]]
rel: evidence-for -> [[bsd-plan3-verbs-parity-r9-1acadd2]]
rel: amends -> [[impl-task-3.5-r8-remedy#amend]]
rel: amends -> [[impl-task-3.4-internal-cli-allowlist#legacy-table]]
rel: part-of -> [[plan-3-verbs-parity]]

TDD GREEN for the RED group committed at `95b81ac` (`tests/test_task3_6_r9_remedy.py`, 11 RED of
20). The code is in `1919764`. No tests were written in this step.

## #2: six sites through the classifier {#req-2}

Each of these handlers now gets its words and its error type from
`verbs.classify_transport_error`:

| site | change |
|------|--------|
| `search._where_one_project` memory leg | `reasons` gets the classifier's text (op `memory_search`) |
| `search.federated_query` | `skipped` gets the classifier's text (op `query`) |
| `verbs.memory_partition` | raises the classifier's error. A refused socket is now `VerbAbsentError`, not "daemon busy … partition_list" |
| `cli` `derive log` / `derive status` | new `cli._say_degraded_read(exc, *, op, root)` prints `# rmx: <classifier words>; reading the lock-free replica`. The read still degrades |
| `cli ingest-gmd --detach/--progress` start op | the ClickException leads with the classifier's text and keeps the pid and the budget detail (`test_detach_is_bounded…` still pins `busy` + `pid=` for a stall) |

With these, task 3.5's "ONLY place" claim is true. The 3.5 summary carries a correction pointing
here.

## #3: one spawn deadline {#req-3}

`daemon.spawn_daemon_subprocess` sets `deadline = monotonic() + wait_for_ready` at entry. The
launcher runs with `timeout = remaining`. The readiness poll runs until the same deadline. The
error states the elapsed time, the window, and which leg ran out ("the launcher was still running
at the deadline and was killed" or "the daemon never answered ping"). `RMX_DAEMON_SPAWN_WAIT` is
still the caller's window (bug-129 r6). The worst case is now `W`. Before it was `2W + 5`
(25.2 s measured against promote's 10 s budget).

## #5: bug-135, measured then fixed {#req-5}

Measurement log: `workflow/review-output/bug135-measure.log`. The probe scripts traced every
`duckdb.connect` and then isolated each opener. The registry row was updated with the cause
before the fix landed.

**Measured cause.** With no `catalog.read.duckdb` (and no `read_only.duckdb`),
`Store(read_only=True)` resolves `db_path` to the writer's primary `catalog.duckdb`. Two read-only
openers run before `memory add`'s in-process bootstrap write:

1. `cli._legacy_memory_partition_exists` → `_reader_store()` opens that file and closes it. When
   isolated, a write afterwards succeeds.
2. `verbs.memory_partition`'s replica-first probe → `search.cached_replica(root)` opens the same
   primary file read-only (the `rmx_ro` attach) and caches it for the life of the process in
   `search._REPLICA_CACHE`. When isolated, the next in-process write fails with exactly bug-135's
   error. Popping and closing that cache entry makes the write succeed.

The r9 hypothesis (an `rmx_ro` attach in the same process) was right about the mechanism. It did
not say which opener. The seven 3.4-routed writes pass `partition=` explicitly, so they never
reach this probe, which is why they still worked.

**Fix.** `search.cached_replica` refuses with `FileNotFoundError` ("no replica catalog") when the
read-only Store resolves to anything other than a snapshot file (`_REPLICA_FILES`). A replica
cache now holds replicas only. Every caller already treats that error as "no replica yet".
`memory_partition` then takes its documented bootstrap branch: with no daemon, it uses the
project partition.

## #6 and 3.7 AC-G1: LEGACY_UNPAIRED {#req-6}

| path | was | now | reason (true against the code) |
|------|-----|-----|-------------------------------|
| `focus record` | hook | harness | a manual STM append. Every generated focus hook runs `focus hook --event …` |
| `install-hooks` | hook | operator | the operator's hook installer. `--check` is a pre-commit gate |
| `memory sync-disk` | hook | maintenance | a by-hand bridge run. The automatic bridge is `ingest-gmd`, plus an in-process call from save-state |
| `curator scan` | verb-it | maintenance | driven by `scheduler.py`'s `curator-scan` op |

Every remaining `verb-it` reason names its `task-3.7#fam-<family>`. New counts (140 total):
**verb-it 49, operator 44, maintenance 29, harness 10, hook 8**.

## Per-AC status {#acs}

| AC | Status |
|----|--------|
| AC-1 where leg, refused → "not running" | GREEN |
| AC-2 federated_query, refused → "not running" | GREEN |
| AC-3 memory_partition, refused → `VerbAbsentError` | GREEN |
| AC-4 derive log / status note | GREEN |
| AC-5 `ast` guard (planted fixture flagged) | GREEN |
| AC-6 one spawn deadline; promote with a 20 s launcher inside budget + 3 s | GREEN |
| AC-7 ME held real global daemon | GREEN (pin) |
| AC-8 MD over-long `RMX_HOME` | GREEN (pin) |
| AC-9 ML vanished / stalled | GREEN (pin) |
| AC-10 MF only absent falls back | GREEN (pin) |
| AC-11 bug-135 bootstrap | GREEN |
| AC-12 four reasons | GREEN |
| AC-13 plan-3 files, "ONLY place" true | GREEN; see [[#runs]] |
| 3.7 AC-G1 family names | GREEN |

## Mutation check {#mutation}

Log: `workflow/review-output/task3.6-mutation.log`. Each mutant was applied to `1919764`, the
3.6 file was run, then the mutant was reverted with `git checkout -- src` and a `__pycache__`
purge. All seven were killed:

| mutant | killed by |
|--------|-----------|
| ME: drop `global_write`'s busy branch | `test_a_held_real_global_daemon_is_busy_and_never_spawned_over` |
| MD: spawn readiness back to the 30 s default | `…slow_launcher…`, `…overlong_global_root…` (30.1 s) |
| ML: `global_write` raises a raw `VerbError` | both `test_global_write_types_…` |
| MF: `_memory_write` falls back on any `VerbError` | both MF tests |
| #3: launcher `W + 5` and a fresh poll window | `test_spawn_holds_one_deadline…`, `…slow_launcher…` (25.1 s) |
| #5: `cached_replica` caches the primary catalog again | `test_memory_add_bootstraps…` |
| #2: `federated_query` words its own error again | `test_federated_query_…`, the `ast` guard |

## Runs {#runs}

- RED: `workflow/review-output/task3.6-3.7-red.log` (test engineer, `95b81ac`).
- 3.6 file: 20 passed (`task3.6-green-target.log`).
- Plan-3 files (incl. 3.5, 3.6, plan-2 remedy, hub, lance): 551 passed (`task3.6-green-plan3.log`).
- Full suite: 3018 passed, 20 failed, 19 skipped (`task3.6-green-full.log`). The failures are the 19 clone-only DEV TREE refusals plus the gmd repo-scope gate, and nothing else.

## Amendment after r10 (#r10-amend) {#r10}

rel: implements -> [[task-3.6-r9-remedy#r10-amend]]
rel: evidence-for -> [[bsd-plan3-verbs-parity-r10-1081a05]]

This is the GREEN for the test engineer's `a420c90`. The tests there were 6 RED.

- **S1: one legacy-partition detector.** `verbs.legacy_memory_partition_exists(root, legacy)
  -> bool` does a read-only open (the snapshot if there is one, else the primary catalog),
  is closed in a `finally`, and is never cached. A store with no catalog file has no legacy
  partition.
  - `verbs.memory_partition` uses it on the no-replica, absent-daemon branch. A read failure
    there is `VerbBusyError`, never a guessed partition.
  - `cli._memory_partition_default` now delegates to `verbs.memory_partition`. On a
    `VerbError` it keeps the CLI's old behaviour: warn, and use the project partition for this
    command only.
  - `cli._legacy_memory_partition_exists` and its process cache are deleted, along with
    `_ingest_partition`'s now-unused `daemon_up` parameter. MCP `rmx_memory_add` already went
    through `verbs.memory_partition`.
  - Result: MCP, CLI and the verb all land in `memory-p` on a pre-merge store that has never
    been snapshotted, and an in-process write afterwards succeeds, so bug-135 stays fixed.
- **S2: two more sites through the classifier.**
  - **`focus summarize --promote`** (`cli.py:1341`). The "may still complete it" note for a
    timeout is a transport fact, so it now comes from the classifier:
    `classify_transport_error(..., write=True)`. On a timeout of a write op it says "the daemon
    is busy — the write is not confirmed within Ns and the daemon may still complete it". A
    refused or missing socket gets the plain absent wording.
  - **`memory recall`'s dense leg** (`_degrade_or_raise`, `cli.py:12270`). It now types and
    words raw OSErrors through the classifier. An already-typed `VerbError` keeps its own
    words. The hook-mode stdout note interpolates the classified error, escaped for Rich.
- **M1:** bug-135's status is now `fixed (1919764; …)`. A closure line says the fix moved the
  no-daemon legacy check, S1 restores that check as a closed-after read, and the enabler is
  bug-136, which belongs to task 23.5. bug-136 itself is not touched.

**Tests that pin the deleted CLI detector.** The spec deletes the CLI detector, so these
three fail with `AttributeError: module 'refmatrix.cli' has no attribute
'_legacy_memory_partition_exists'`. They need updating by the test engineer:

- `tests/test_plan2_remedy.py::test_legacy_partition_probe_warns_and_does_not_cache_a_timeout`:
  the intent (warn on a failed probe, cache nothing) still holds in
  `cli._memory_partition_default`.
- `tests/test_plan2_remedy_r7.py::test_cli_partition_probe_reads_the_replica_under_a_held_writer`:
  it asserts the CLI process cache is populated, which contradicts "never cached". Its replica
  intent is covered by the sibling verb test in the same file.
- `tests/test_memory.py::test_memory_partition_default_resolves_to_project_scoped`: it fails
  on line 291, `hasattr(cli_mod._legacy_memory_partition_exists, "_cache")`. The behaviour it
  asserts still holds.

r10 runs:

- 3.6 file, plus the plan-2 and memory files: `workflow/review-output/task3.6-r10-green-target.log`.
- Plan-3, `test_memory*` (including `test_memory_recall*`), plan-2 and embed-routing files: 595
  passed, 3 failed — the three detector-pinning tests above (`task3.6-r10-green-plan3.log`).
- Full suite: 3037 passed, 23 failed, 19 skipped (`task3.6-r10-green-full.log`). The failures
  are the 19 clone-only DEV TREE refusals, the gmd repo-scope gate, and the same three
  detector-pinning tests.

## Amendment after r11 (#r11-amend) {#r11}

rel: evidence-for -> [[bsd-plan3-verbs-parity-r11-999313c]]

GREEN in `e31ade1`, against the test engineer's `01dad2e`.

- **r11 #s-1:** `_file_under_active_subject` (the subject-filing leg of `focus summarize
  --promote`) now types and words its transport errors with
  `classify_transport_error(e, op=<subject_upsert|subject_link>, root=…, timeout=…,
  write=True)`. The "promoted id=… but subject filing under …" prefix stays. A refused socket
  no longer claims that the daemon may still complete the filing; only a timeout says so. The
  guard's wrapper set is now a fixed point (test side, `01dad2e`), so it sees this two-level
  dial.
- **r11 #obs-summarize-global:** `focus summarize --promote --global` used to write with an
  unbudgeted, direct `hub.global_call`. It now writes through `verbs.global_write(...,
  timeout=--timeout)`. A failure is a ClickException that carries the typed verb error.
- **r11 #m-1:** `legacy_memory_partition_exists` still closes in a `finally`, and the absent
  branch's read failure still raises `VerbBusyError`. `01dad2e` pins both (P2, P8). Neither
  changed here.

r11 runs:

- the 3.6 file: 53 passed (`task3.6-r11-green-target.log`);
- the plan-3 files plus the focus, STM and subject files (`test_stm*`, `test_subject`,
  `test_composite`, `test_hook_wiring`, `test_bug115_liveness_under_load`, …) and the plan-2
  files: 712 passed, 0 failed (`task3.6-r11-green-plan3.log`);
- the full suite: 3050 passed, 21 failed, 19 skipped (`task3.6-r11-green-full.log`). The
  failures are the 19 clone-only DEV TREE refusals, the gmd repo-scope gate, and one recurrence
  of the known flaky bug-091, `test_watch.py::test_run_watcher_picks_up_new_file` ("watcher did
  not fire"). That file passed 3/3 alone afterwards; its registry row now reads Seen 2, recurring.
