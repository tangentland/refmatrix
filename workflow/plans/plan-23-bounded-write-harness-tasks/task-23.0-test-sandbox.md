---
gmd: "0.1"
id: task-23.0-test-sandbox
title: "Task 23.0: a test sandbox that no test, and no child a test spawns, can see past"
tags: [task, tests, sandbox, isolation, bug-088, bug-101, wave-1]
metadata:
  node_type: task
  status: pending
  created: 2026-10-14
  updated: 2026-10-14
---

# Task 23.0: the shared test sandbox {#root}

> Plan: [plan-23-bounded-write-harness](../plan-23-bounded-write-harness.md)
> Status: Pending (revision after the 2026-10-14 decision log)
> Depends on: — (the FIRST build of Wave 1, in parallel with 23.4)
> Blocks: 23.2, 23.1, 23.3, and every Wave 1 task's tests (21.1 needs only this task)

rel: part-of -> [[plan-23-bounded-write-harness]]
rel: implements -> [[plan-review-2026-10-14#t1-scope]]
rel: derives-from -> [[plan-review-2026-10-14#t1]]
rel: derives-from -> [[plan-review-2026-10-14#t8-revisited]]
rel: evidence-for -> [[bug_registry#registry]]
rel: related-to -> [[project_suite_reaches_live_sockets]]

## Why {#why}

The suite reaches live stores today. bug-088: 72 in-process connects to live sockets in one full
run, and the conftest recorder (`tests/conftest.py` `pytest_configure`, record-only) cannot see a
spawned `rmx` child. bug-101: the suite wrote 143,108 `facts.log` events on 1,655 pytest entities
into the live global store, and 235 fixture rows into the live `~/.refmatrix/query.log`. Every
review of Wave 0 (17 #b-5, 19 #b-7, 21 #s-7, 22 #b-8, 23 #s-7) asked for the same isolation, so it
is built once, first (d1a, d1b).

Facts at HEAD `b1c4324` the design depends on:
- `taxonomy.user_home()` reads `RMX_HOME`, else `Path.home() / ".refmatrix"`; `hub.hub_home()`,
  `hub.global_store_root()` and `discovery.registry_path()` all derive from it.
- `launchctl.LAUNCH_AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"` is computed at IMPORT
  time, so `$HOME` must be redirected before `refmatrix` is first imported.
- `cli._root()`: `REFMATRIX_ROOT` wins; else a `~/.claude/projects/<slug>` cwd; else the cwd walk,
  which from the repo finds the LIVE `.refmatrix/`; else `user_home()`.
- `discovery.discover_roots()` unions launchd plists, the registry, the cwd walk and `user_home()`.
{#why-body}

## Requirements {#requirements}

1. **R1 Redirect before import.** `tests/conftest.py`, at module top level and before any line
   that imports `refmatrix`, creates ONE short sandbox root (`tempfile.mkdtemp(prefix="rmx-",
   dir="/tmp")`, so `<root>/<store>/.refmatrix/rmxd.sock` stays under macOS's ~104-byte
   `sun_path`) and sets `HOME`, `RMX_HOME` (global root, registry, taxonomy, hub sockets) and
   `RMX_SANDBOX_ROOT` to paths inside it. `PATH` is pinned so `rmx` resolves to
   `.venv-eval/bin/rmx`, never the deploy `~/bin/rmx`. The REAL paths are captured first, for R3's
   deny set only. {#r1}
2. **R2 Store roots injected.** An autouse fixture sets `REFMATRIX_ROOT` to a per-test path under
   the sandbox, so `_root()` can never resolve the repo's live `.refmatrix/`. A test that needs the
   cwd walk must `chdir` into its own tmp dir and unset the variable itself; R3 catches one that
   does not. {#r2}
3. **R3 Refuse, not record (bug-088's refuse stage).** One deny set, built from the real paths
   captured in R1:
   - the real `~/.refmatrix/` (global store, `query.log`, `facts.log`, `registry.json`, hub
     `hub.sock` / `models.sock`);
   - this repo's own `.refmatrix/` (the conftest's `_REPO / ".refmatrix"`);
   - every root in the real registry AND every root in the real registered daemon list (the
     `com.refmatrix.daemon.*` plists in the real LaunchAgents dir; d8c counts 8 stores), which
     includes the viascope store the recorder omits today;
   - TCP `127.0.0.1:7777`, `localhost:7777` and `::1:7777`.

   A `sys.addaudithook` hook installed in R1 raises `SandboxViolation` on any `open` (write OR
   read), `os.*` mutation, or `socket.connect` whose target is in the deny set, appends the test id
   and target to `workflow/review-output/live-socket-touches.log`, and the test fails. The
   record-only `_recording_connect` is replaced by it. {#r3}
4. **R4 Children inherit the refusal.** Every child process a test spawns (an `rmx` CLI, a hook
   script, a `python -c`) gets the sandbox env and a `PYTHONPATH` entry for
   `tests/sandbox_site/sitecustomize.py`, which installs the SAME audit hook from
   `RMX_SANDBOX_ROOT` and exits the child nonzero with the violation on stderr. The refusal happens
   IN the child; the parent sees the nonzero exit. A spawn site that passes `-I`/`-E` (which drop
   `PYTHONPATH`) is listed in the implementation summary and given the hook explicitly. {#r4}
5. **R5 No new fixture rows in live logs (d8d).** With R1-R3 in place, the grep tests that wrote
   bug-101's rows (`tests/test_grep_dropin_contract.py`, `tests/test_grep_output_shape.py`) write
   their `query.log` / `facts.log` rows into the sandbox. The 235 rows already in the live
   `query.log` are not this task's: d8d's mark-and-filter owns them. {#r5}
6. **R6 No test skipped to get green.** A pre-existing test that breaks under the sandbox is FIXED
   (named in the implementation summary with the line it read from the live machine), never
   `--ignore`d or `-k`'d away (CLAUDE.md #system-dependent-tests). {#r6}

## Acceptance criteria {#acceptance}

1. **Redirect canary.** A test asserts that `taxonomy.user_home()`, `discovery.registry_path()`,
   `hub.global_store_root()`, `launchctl.LAUNCH_AGENTS_DIR`, `cli._root()` and every path
   `discovery.discover_roots()` returns lie under `RMX_SANDBOX_ROOT`. Mutation (pre-registered):
   move the R1 env assignments below the first `refmatrix` import in conftest; the canary MUST fail
   on `LAUNCH_AGENTS_DIR`. {#ac-1}
2. **In-process refusal.** Through `pytester`, an inner test that connects to the real
   `~/.refmatrix/rmxd.sock` path, one that opens the real `~/.refmatrix/query.log` for append, and
   one that connects to `::1:7777` each FAIL with `SandboxViolation`, and the touches log names
   them. Mutation: put back the record-only connect; the inner tests must then PASS, so the outer
   test fails. {#ac-2}
3. **Child refusal.** A test spawns `.venv-eval/bin/python -c` that connects to the real hub socket
   path, and a test spawns `rmx` with `REFMATRIX_ROOT` pointed at the repo's real `.refmatrix/`.
   Both children exit nonzero with `SandboxViolation` on stderr. Mutation: drop the `PYTHONPATH`
   entry; the children must then connect (or fail differently), and the test must fail. {#ac-3}
4. **Whole-suite proof.** A wrapper script OUTSIDE pytest stats the live `~/.refmatrix/query.log`,
   `~/.refmatrix/facts.log`, the repo's `.refmatrix/query.log` and `facts.log` (size + mtime) before
   and after a full suite run captured to `workflow/review-output/pytest-sandbox.log`. All four are
   unchanged, and the touches log gains 0 lines. {#ac-4}
5. **Short root.** A test asserts `len(str(sandbox / "s" / ".refmatrix" / "rmxd.sock")) <= 100`.
   {#ac-5}

## Test strategy {#test-strategy}

This task IS the sandbox, so its own tests run inside it: the canaries are ordinary tests under
the R1 conftest; the refusal checks use `pytester` (an inner session that inherits R1) and spawned
children (R4). No test of this task opens a live path except through the refusal it asserts; AC-4's
before/after stat runs outside pytest. Logs go to `workflow/review-output/` (the
`enforce-test-to-file` hook).

## Revision (2026-10-14 decision log) {#rev-2026-10-14}

| finding / decision | answered at |
|---|---|
| d1a (sandbox is Wave 1's first build) | [[#root]] header, [[plan-23-bounded-write-harness#tasks]] |
| d1b (task 23.0 at the front of plan-23) | this file |
| #t1-scope `$HOME`, global root, registry, LaunchAgents before import | [[#r1]], [[#ac-1]] |
| #t1-scope store roots injected | [[#r2]], [[#ac-1]] |
| #t1-scope children refuse sockets outside the tmp dir | [[#r4]], [[#ac-3]] |
| #t1-scope conftest guard fails a touch of `~/.refmatrix` / a live store | [[#r3]], [[#ac-2]] |
| d8d (23.0 prevents new fixture rows) | [[#r5]], [[#ac-4]] |
| 23 #s-7 (kill and sandbox unspecified, bug-088) | [[#r3]], [[#r4]]; 23.1's test strategy |
| bug-088 omissions (viascope store, `::1:7777`) | [[#r3]] |
