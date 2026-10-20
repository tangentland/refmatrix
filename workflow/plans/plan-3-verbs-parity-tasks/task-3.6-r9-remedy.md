---
gmd: "0.1"
id: task-3.6-r9-remedy
title: "Task 3.6: plan-3 r9 remedy — one transport classifier for every store-daemon site, one spawn deadline, the four #s-2 survivors pinned, memory add bootstraps, four LEGACY reasons made true"
tags: [task, plan-3, remedy, bsd, verbs, search, daemon]
metadata:
  node_type: task
  status: completed
  plan: plan-3-verbs-parity
  created: 2026-10-19
  amended: 2026-10-19 (#r10-amend — ch-bsd plan-3 r10; #r11-amend — r11)
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
rel: derives-from -> [[bsd-plan3-verbs-parity-r10-1081a05]]

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

## Amendment after r10 {#r10-amend}

ch-bsd plan-3 r10 at `1081a05` was DIRTY (0B/2S/2M). Every r9 finding is closed in behaviour and
13 of 14 remedy mutants are killed. Two SKETCHY findings and one MEH are folded in here; the other
MEH (#m-2) is task 3.7 itself.

rel: implements -> [[bsd-plan3-verbs-parity-r10-1081a05#s-1]]
rel: implements -> [[bsd-plan3-verbs-parity-r10-1081a05#s-2]]
rel: implements -> [[bsd-plan3-verbs-parity-r10-1081a05#m-1]]

### S1 — one legacy-partition detector (r10 #s-1) {#r10-s1}

The bug-135 fix made `search.cached_replica` refuse the writer's primary catalog. That cache was
the only way `verbs.memory_partition` saw a legacy `memory-<project>` partition on a
never-snapshotted store. With no daemon it now falls to absent and returns the project
partition, while `cli._legacy_memory_partition_exists` still finds the legacy one. On the same
store, MCP `rmx_memory_add` lands in `p` and CLI `memory add` lands in `memory-p`: the
split-brain family `memory_partition` exists to prevent.

- **Decision (orchestrator):** ONE detector, `verbs.legacy_memory_partition_exists(root,
  legacy) -> bool`. It does a read-only open, CLOSES it afterwards, and is never cached
  (the CLI's process cache goes). `verbs.memory_partition` uses it on the no-replica / absent
  branch. The CLI's memory-partition default (`_memory_partition_default` /
  `_legacy_memory_partition_exists`) uses it too.
- MCP `rmx_memory_add`, CLI `memory add` and `verbs.memory_partition` agree on `memory-<project>`
  for that store state.
- bug-135 stays fixed. After the detector runs, an in-process writer open in the same process
  succeeds (no lingering `rmx_ro` attach).

### S2 — the guard covers every spelling (r10 #s-2) {#r10-s2}

The r9 guard matched one spelling (`daemon_mod.call` plus literal words) and passed eight planted
evasions. It also misses one live site.

- **Guard** (`tests/transport_guard.py`). The dial set covers:
  - every module alias bound to `daemon` / `hub` by any import spelling, and any `*daemon*` name;
  - from-imported `call` / `global_call`;
  - dial WRAPPERS: any function that dials directly (`_memory_daemon_call`, …) and is not a
    clean delegate.

  Wording covers:
  - the handler's literals and f-strings;
  - module string constants it names;
  - text of helpers it calls (two levels);
  - synonyms: busy / down / wedged / hung / stuck / did not answer / not answering / not
    running / not confirmed / timed out / unreachable.

  It flags:
  - a handler or delegate that classifies on one branch and words its own error on another;
  - a handler that calls the classifier and discards the result.

  It passes:
  - a handler that raises or interpolates the classifier result;
  - a handler that calls a clean delegate;
  - a silent handler;
  - a handler that catches only typed errors (`Verb*Error`, `ClickException`).

  One planted fixture per shape.
- **Live sites to route through `classify_transport_error`** (both flagged at `1081a05`):
  - `cli.py:1341`: `focus summarize --promote`, around `_memory_daemon_call`. It words any
    OSError "daemon busy: promote not confirmed". Keep the "may still complete it" note for the
    timeout case.
  - `cli.py:12270`: `memory recall`'s dense leg, `_degrade_or_raise`. It words a raw OSError
    "daemon busy (recall not confirmed …)". The new guard found this one; r10 did not list it.
- **N8 pinned behaviourally:** `ingest-gmd --detach` against a refused socket says "not running",
  never "daemon busy".

### M1 — bug-135's registry row closed (r10 #m-1) {#r10-m1}

The bug-135 row's status becomes `fixed (1919764)`, with one line saying that the fix moved the
no-daemon legacy check and that S1 restores it as a closed-after read.

### Rider: bug-136 (owner plan-23 task 23.5) {#r10-bug136}

`Store(read_only=True)` with no snapshot resolves to the WRITER's own catalog. Any long-lived
read-only holder therefore reproduces bug-135; this is the enabler bug-135's fix left in place.
**Rider on task 23.5 (read path):** a read-only open with no snapshot either fails with the
read-worded error or opens a closed-after handle, never a cached attach of the writer's file.
Plan-3 does not fix it beyond S1's closed-after, never-cached detector.

rel: related-to -> [[task-23.5-read-path-and-holder-bounds]]

### Acceptance criteria (r10) {#r10-acceptance}

1. **AC-R10-1 (S1, RED).** `verbs.memory_partition` returns `memory-p` on a no-daemon,
   no-snapshot store that holds a legacy `memory-p`. {#ac-r10-1}
2. **AC-R10-2 (S1, RED).** MCP `rmx_memory_add` and CLI `memory add` both land in `memory-p`;
   an in-process write afterwards succeeds. {#ac-r10-2}
3. **AC-R10-3 (S1, RED).** `verbs.legacy_memory_partition_exists` sees a legacy partition created
   after its first call (never cached), and both `verbs.memory_partition` and the CLI default
   reach it (pass-through spy). {#ac-r10-3}
4. **AC-R10-4 (S2, RED).** The widened guard finds no src handler; at `1081a05` it names
   `cli.py:1341` and `cli.py:12270`. {#ac-r10-4}
5. **AC-R10-5 (S2).** Every planted evasion shape is flagged (12 plants), and every delegating,
   silent or typed-only plant passes (5 plants). {#ac-r10-5}
6. **AC-R10-6 (N8).** `ingest-gmd --detach` against a refused socket says "not running". This pin
   passes at HEAD and kills N8. {#ac-r10-6}
7. **AC-R10-7 (M1, RED).** bug-135's registry status is not `open`. {#ac-r10-7}

## Amendment after r11 {#r11-amend}

ch-bsd plan-3 r11 at `999313c` was DIRTY (0B/1S/3M). r10's S1, S2 and M1 are closed in behaviour,
and all eight r10 guard evasions are flagged. One sibling survives in the same command. Two
guarantees fail no test when reverted. Two records overstate. 3.7 is unchanged (AC-G4).

rel: derives-from -> [[bsd-plan3-verbs-parity-r11-999313c]]
rel: implements -> [[bsd-plan3-verbs-parity-r11-999313c#s-1]]
rel: implements -> [[bsd-plan3-verbs-parity-r11-999313c#m-1]]
rel: implements -> [[bsd-plan3-verbs-parity-r11-999313c#m-2]]

### R11-1 — the subject-filing leg and a fixed-point guard (r11 #s-1) {#r11-1}

`focus summarize --promote` makes three daemon writes. The `memory_add` leg goes through
`classify_transport_error(write=True)`. The subject-filing leg (`_file_under_active_subject`,
cli.py:1414-1419 at `999313c`) dials two wrappers deep (`_subject_upsert` / `_subject_link` →
`_memory_daemon_call`). It still says "not confirmed … the daemon may still complete it" for
any OSError, a refused socket included.

- Route it through `classify_transport_error(…, write=True)`, keeping the "promoted id=… but
  subject filing under …" prefix.
- `tests/transport_guard.py` computes the TRUE fixed point of dial wrappers (any depth). It also
  reads dict / list / tuple message tables as constants, treats `getattr(<daemon alias>,
  "call")(…)` as a dial, and adds the synonym "no answer".
- New plants that must be flagged: two-level wrapper, dict of messages, getattr dial, "no answer".

### R11-2 — pin P2 and P8 (r11 #m-1) {#r11-2}

- **P2:** the detector's `close()`. The test counts every Store the detector opens and requires
  each one closed before return; refcounting hides a missing close from behaviour tests.
- **P8:** the absent branch never guesses past an unreadable catalog. A REAL second process holds
  the catalog writer, and `verbs.memory_partition` must raise `VerbBusyError`.

### R11-3 — `focus summarize --promote --global` through `verbs.global_write` (orchestrator) {#r11-3}

It wrote with `hub.global_call("memory_add", args)` directly. That write was unbudgeted, ignored
`--timeout` and bypassed the one global-write helper. It goes through `verbs.global_write("memory_add",
args, timeout=<≤ --timeout>)`.

### R11-4 — records (r11 #m-2) {#r11-4}

- The mock-registry row for `test_cli_partition_probe_reads_the_replica_under_a_held_writer` is
  reworded: it runs on a socket double plus a real snapshot, not a real held writer.
- bug-136's rider is anchored in the dev tree's `task-23.5-read-path-and-holder-bounds#bug136-rider`
  and arrives here at the release merge. The bug row says so.

### Acceptance criteria (r11) {#r11-acceptance}

1. **AC-R11-1 (RED).** The live guard scan is empty. At `999313c` it names `cli.py:1415`. {#ac-r11-1}
2. **AC-R11-2.** The four new plants are flagged; the clean plants still pass. {#ac-r11-2}
3. **AC-R11-3 (RED).** The subject-filing leg on a refused socket says "not running", with no
   "not confirmed" and no "may still complete". {#ac-r11-3}
4. **AC-R11-4 (pins).** The P2 and P8 tests pass at HEAD and kill their mutants. {#ac-r11-4}
5. **AC-R11-5 (RED).** `focus summarize --promote --global --timeout 5` calls
   `verbs.global_write("memory_add", …, timeout≤5)` and never `hub.global_call` directly. {#ac-r11-5}
6. **AC-R11-6.** The two record corrections land; no test. {#ac-r11-6}

## Files to modify {#files-to-modify}

| File | Change |
|------|--------|
| `src/refmatrix/search.py` | where project leg, federated_query through the classifier |
| `src/refmatrix/verbs.py` | memory_partition through the classifier; LEGACY reasons (#6) |
| `src/refmatrix/cli.py` | derive log/status notes; ingest-gmd start op; memory add bootstrap (#5) |
| `src/refmatrix/daemon.py` | `spawn_daemon_subprocess` one deadline |
| `tests/test_task3_6_r9_remedy.py` | new (test engineer); #r10-amend tests |
| `tests/transport_guard.py` | the widened guard (#r10-amend S2) |
| `src/refmatrix/mcp.py` | bootstrap partition through the shared detector (#r10-amend S1) |
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
