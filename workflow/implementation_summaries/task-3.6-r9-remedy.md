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
- Full suite: `task3.6-green-full.log`.
