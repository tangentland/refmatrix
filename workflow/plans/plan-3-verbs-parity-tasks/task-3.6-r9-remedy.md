---
gmd: "0.1"
id: task-3.6-r9-remedy
title: "Task 3.6: plan-3 r9 remedy — one transport classifier for every store-daemon site, one spawn deadline, the four #s-2 survivors pinned, memory add bootstraps, four LEGACY reasons made true"
tags: [task, plan-3, remedy, bsd, verbs, search, daemon]
metadata:
  node_type: task
  status: approved
  plan: plan-3-verbs-parity
  created: 2026-10-19
---

# Task 3.6: plan-3 r9 remedy {#root}

> Plan: [[plan-3-verbs-parity]]
> Status: Approved
> Depends on: [[task-3.5-r8-remedy]]

rel: part-of -> [[plan-3-verbs-parity]]
rel: derives-from -> [[bsd-plan3-verbs-parity-r9-1acadd2]]
rel: implements -> [[bsd-plan3-verbs-parity-r9-1acadd2#s-1]]
rel: implements -> [[bsd-plan3-verbs-parity-r9-1acadd2#s-2]]
rel: implements -> [[bsd-plan3-verbs-parity-r9-1acadd2#s-3]]
rel: implements -> [[bsd-plan3-verbs-parity-r9-1acadd2#s-4]]
rel: implements -> [[bsd-plan3-verbs-parity-r9-1acadd2#m-1]]
rel: amends -> [[task-3.5-r8-remedy#amend-reqs]]

## Why {#why}

ch-bsd plan-3 r9 at `1acadd2` was DIRTY (1B/4S/1M). Every r8 finding is closed in behaviour, but
"THE one classifier" covers three of the sites that word a store-daemon transport error; the
global spawn overruns promote's 10 s budget by up to W + 5 s (25.2 s measured); four #s-2
closures fail no test when reverted (ME, MD, ML, MF); `rmx memory add` breaks plan-3's own
bootstrap promise on a store with no daemon and no replica; and four LEGACY reasons are false.
#b-1 (the `verb-it` backlog) is [[task-3.7-verb-it-backlog]]. {#why-lead}

## Requirements {#requirements}

### #2 — every store-daemon transport site words through the classifier (r9 #s-1) {#req-2}

Each of these handlers words its error through `verbs.classify_transport_error(e, op=…, root=…,
timeout=…)` (or raises what it returns). The degrade-to-replica sites keep degrading; only their
WORDS change.

| site | today | after |
|------|-------|-------|
| `search._where_one_project` memory leg (search.py:171-174) | "memory_search did not answer within 3s (X)" for any exception | the classifier's words in `reasons` |
| `search.federated_query` (search.py:313-314) | "daemon busy: query did not answer within 20s (X)" | the classifier's words in `skipped` |
| `verbs.memory_partition` (verbs.py:372-378) | `VerbBusyError` "partition_list did not answer" | raises the classifier's error (absent → `VerbAbsentError`) |
| `cli` derive log / derive status (cli.py:7064, :7227) | "# rmx: daemon did not answer (X); reading the lock-free replica" | "# rmx: <classifier words>; reading the lock-free replica" |
| `cli ingest-gmd --detach/--progress` start op (cli.py:10066, found by the guard) | `daemon busy … did not accept the ingest job` for any `OSError` | the classifier's type and words, keeping the budget detail |

`verbs._hub_rpc` dials the HUB, not a store daemon, and is out of scope (r9).

**Guard.** A test scans `src/refmatrix/**/*.py` with `ast`: any `try` whose body dials a store
daemon (`daemon_mod.call` / `hub.global_call`, the module aliases used in src) and whose handler
writes transport words ("did not answer", "busy", "not running", "timed out", …) without calling
`classify_transport_error` or a function that does, fails the test with `file:line`. A planted
fixture proves the guard flags a second classifier and passes a delegating or a silent handler.

### #3 — one spawn deadline (r9 #s-2) {#req-3}

`daemon.spawn_daemon_subprocess` sets ONE deadline at entry (`time.monotonic() +
wait_for_ready`). The launcher runs with `timeout = remaining`, and the readiness poll runs until
the SAME deadline. The worst case is `W`, not `2W + 5`. The error states the real elapsed window.
The launcher's own `RMX_DAEMON_SPAWN_WAIT` stays the caller's window (bug-129 r6).

### #4 — the four survivors pinned (r9 #s-3) {#req-4}

- **ME** — a held global store is typed busy and never spawned over: a REAL global daemon,
  SIGSTOPped (pid alive, socket present, no answer); not `_PingOnlyDaemon`, which answers ping.
- **MD** — a can't-start global root (real over-long `RMX_HOME`, no spawn patch) fails inside
  `MEMORY_READ_BUDGET_S + 3`.
- **ML** — `global_write`'s transport error is typed by the classifier: a daemon that vanished
  after the probe is `VerbAbsentError`; a stalled write is `VerbBusyError`.
- **MF** — `_memory_write` falls back to `local()` ONLY on `VerbAbsentError`; busy raises and never
  opens the store (unit test + a real SIGSTOPped project daemon).

These pin behaviour that is correct at `1acadd2`; each must kill its mutant.

### #5 — `memory add` bootstraps with no daemon and no replica (r9 #s-4, bug-135) {#req-5}

On a store with no daemon and no `catalog.read.duckdb`, `rmx memory add z1 -c b` exits 0 and the
row is in the store (cli.py:11377-11385's promise, plan-3 r2 #b-2). Today:
`StaleDuckDBInstanceError … already attached by database "rmx_ro"`. Measure the mechanism before
naming it (the `rmx_ro` read-only attach in the same process is r9's hypothesis only), then fix
it. Logged as bug-135.

### #6 — four LEGACY reasons made true (r9 #m-1) {#req-6}

| path | from | to | reason must say |
|------|------|----|-----------------|
| `focus record` | hook | `harness` | not a generated hook (every focus hook runs `focus hook --event …`) |
| `install-hooks` | hook | `operator` | the operator's install command |
| `memory sync-disk` | hook ("SessionStart / save-state bridge") | `maintenance` | a by-hand bridge run; SessionStart runs `ingest-gmd`, save-state calls the bridge in-process |
| `curator scan` | verb-it | `maintenance` | driven by `scheduler.py` |

## Acceptance criteria {#acceptance}

1. **AC-1 (#2 where).** `_where_one_project` on a refused socket: the memory reason says "not
   running", no "did not answer"/"busy". RED. {#ac-1}
2. **AC-2 (#2 query).** `federated_query` on a refused socket: `skipped` says "not running". RED. {#ac-2}
3. **AC-3 (#2 partition).** `memory_partition` (status up, refused dial) raises `VerbAbsentError`
   "not running". RED. {#ac-3}
4. **AC-4 (#2 derive).** `derive log` and `derive status` (ping up, refused dial) print a stderr
   note saying "not running". RED. {#ac-4}
5. **AC-5 (#2 guard).** No src handler words a store-daemon transport error itself; the planted
   fixture is flagged. RED (6 sites at 1acadd2). {#ac-5}
6. **AC-6 (#3).** `spawn_daemon_subprocess(wait_for_ready=3)` with a 20 s launcher fails within
   5 s; `memory promote` with a 20 s launcher on a cold global fails within budget + 3 s. RED. {#ac-6}
7. **AC-7 (#4 ME).** Held real global daemon → promote exits non-zero with "busy", no "not
   running", no lock error, zero spawns, within budget + 3. Pin; kills ME. {#ac-7}
8. **AC-8 (#4 MD).** Over-long real `RMX_HOME` → "not running" within budget + 3. Pin; kills MD. {#ac-8}
9. **AC-9 (#4 ML).** `global_write` vanished-daemon → `VerbAbsentError`; stalled → `VerbBusyError`.
   Pins; kill ML. {#ac-9}
10. **AC-10 (#4 MF).** `_memory_write` busy → ClickException, `local` not called; absent → `local`;
    a SIGSTOPped project daemon never opens the store. Pins; kill MF. {#ac-10}
11. **AC-11 (#5).** `memory add` on a no-daemon, no-replica store exits 0 and the row is readable.
    RED (bug-135). {#ac-11}
12. **AC-12 (#6).** The four paths carry the categories above and reasons true to the code. RED. {#ac-12}
13. **AC-13.** All plan-3 test files stay green; `task-3.5-r8-remedy#amend-reqs`'s "ONLY place"
    claim is true after #2. {#ac-13}

## Files to modify {#files-to-modify}

| File | Change |
|------|--------|
| `src/refmatrix/search.py` | where project leg, federated_query through the classifier |
| `src/refmatrix/verbs.py` | memory_partition through the classifier; LEGACY reasons (#6) |
| `src/refmatrix/cli.py` | derive log/status notes; ingest-gmd start op; memory add bootstrap (#5) |
| `src/refmatrix/daemon.py` | `spawn_daemon_subprocess` one deadline |
| `tests/test_task3_6_r9_remedy.py` | new (test engineer) |
| `workflow/bug_registry.md` | bug-135 |

## Test strategy {#test-strategy}

`tests/test_task3_6_r9_remedy.py`. Real refused/missing socket files and real daemons; the race
(status up, dial fails) is the registered `discovery.daemon_status`→up / `daemon.ping`→True
double. The slow launcher is a `sitecustomize` on the children's PYTHONPATH that chains the
sandbox's. RED log: `workflow/review-output/task3.6-3.7-red.log`; #4 pins are proven by mutants
in a scratch copy.

## Definition of done {#done}

- RED, GREEN, mutation check in `workflow/implementation_summaries/task-3.6-r9-remedy.md`.
- `@ch-bsd` re-review CLEAN before plan-3 flips to `completed`.
