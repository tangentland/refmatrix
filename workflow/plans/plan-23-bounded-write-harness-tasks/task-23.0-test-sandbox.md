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
> Status: Pending (revision round 2, 2026-10-14: AC-4 checks content, ns23-2; see
> [[#rev-round-2]]. Amended after 878647c by d9w/d9x: three isolation tiers, R7-R9, see
> [[#amend-2026-10-14-lanes]])
> Depends on: — (the FIRST build of Wave 1, in parallel with 23.4)
> Blocks: 23.2, 23.1, 23.3, and every Wave 1 task's tests (21.1 needs only this task)

rel: part-of -> [[plan-23-bounded-write-harness]]
rel: implements -> [[plan-review-2026-10-14#t1-scope]]
rel: derives-from -> [[plan-review-2026-10-14#t1]]
rel: derives-from -> [[plan-review-2026-10-14#t8-revisited]]
rel: evidence-for -> [[bug_registry#registry]]
rel: related-to -> [[project_suite_reaches_live_sockets]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-32dde06#ns23-2]]
rel: implements -> [[plan-review-2026-10-14#t9-fixes]]

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
   `RMX_SANDBOX_ROOT` to paths inside it. When `RMX_SANDBOX_TAG` is set (AC-4's wrapper sets it to
   6 random hex characters), the prefix becomes `rmx-<tag>-`, so every path the sandbox creates
   carries the run's tag. `PATH` is pinned so `rmx` resolves to
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

## Isolation tiers: in-process, separate user, macOS VM (d9w, d9x) {#amend-2026-10-14-lanes}

Added 2026-10-14 after the round-4 re-review started at 878647c; the next review reads it as new
text. R1-R6 isolate one test run IN-PROCESS: every run, every developer, every agent. They cannot
remove what the run shares with the live machine: the same user (so the same `~`, Keychain,
launchd `gui/<uid>` domain and file permissions), the same kernel, `/tmp` and port namespace. Two
outer tiers remove those, each for a different gate. Tiers nest: R1-R4 still run inside both.

| tier | where | isolates | runs when |
|---|---|---|---|
| 0 in-process (R1-R6, R9) | the developer's own user and venv | env, roots, sockets via the audit hook | every run |
| 1 separate user (R7) | macOS user `rmxtest` on this Mac | `~`, `~/.refmatrix`, launchd `user/<uid>` domain, file permissions | the full suite before any merge to `master` |
| 2 macOS VM (R8) | a Tart VM on Apple's Virtualization framework | everything: kernel, `/tmp`, ports, `gui/<uid>` launchd, disk | before every deploy; on a tier-1/tier-0 disagreement |

7. **R7 Tier 1: the separate-user lane.** {#r7}
   - **Setup, once, by the operator** (needs admin; the script prints the commands and refuses to
     run them itself): a standard, non-admin user `rmxtest` (`sysadminctl -addUser rmxtest`); a
     sudoers drop-in allowing `tholley` to run ONLY `scripts/test-lane-user.sh` as `rmxtest`
     without a password; `rmxtest`'s own `.venv-lane` built from `pyproject.toml`; a READ-ONLY
     copy of the HuggingFace model cache under `~rmxtest/.cache/huggingface`, loaded offline
     (`HF_HUB_OFFLINE=1`, the external-calls rule). Recorded in `docs/INTEGRATION.md`.
   - **Preconditions the script asserts, failing loudly:** `~tholley/.refmatrix`, every
     registered store's `.refmatrix/` and `~tholley/Library/LaunchAgents` are NOT readable by
     `rmxtest` (`sudo -u rmxtest test -r <path>` is false for each); the hub port 7777 is not
     bound by an `rmxtest` process.
   - **Per run:** `scripts/test-lane-user.sh <sha>` clones that commit into
     `~rmxtest/lane/<sha>` (`git clone --no-hardlinks`, then checkout), runs the full suite there
     as `rmxtest` with `PYTHONPATH=<lane>/src` prepended (R9 enforces it), and copies the log back
     to `workflow/review-output/pytest-lane-user-<sha>.log`. Any test that binds a TCP port binds
     an ephemeral one; 7777 is in R3's deny set already.
   - **Known limits, stated, not hidden:** `sudo -u` creates no `gui/<uid>` launchd domain, so a
     test that bootstraps into `gui/` cannot run here. Each such test is LISTED by the script
     (from a first run, by test id, with its error) and runs in tier 2; it is never skipped to
     get green (R6). Same kernel, `/tmp` and ports as the host: R1-R4 still apply.
8. **R8 Tier 2: the macOS VM lane (Tart).** {#r8}
   - **Setup, once, by the operator:** install Tart (Cirrus Labs) — a new dependency, so it is
     proposed and approved, never installed by an agent (CLAUDE.md #no-workarounds). Build one
     golden image `rmx-golden` from a macOS base image matching the host's major release:
     auto-login of a test user (so a `gui/<uid>` launchd domain exists), Python 3.14, the lane
     venv, the offline model cache, SSH enabled. Pulling the base image is the one explicit
     network step; nothing at run time reaches the network.
   - **Per run:** `scripts/test-lane-vm.sh <sha>`: `tart clone rmx-golden rmx-run-<sha>` (a
     copy-on-write clone), `tart run --no-graphics` with the lane clone of `<sha>` shared
     READ-ONLY, copy it onto the VM disk, run the full suite over SSH, copy the log to
     `workflow/review-output/pytest-lane-vm-<sha>.log`, `tart stop`, `tart delete`. Nothing on
     the host is shared writable.
   - **Limits:** Apple's licence allows at most two macOS VMs per Mac at once; the script refuses
     a third. Boot time, run time and disk are recorded per run in
     `workflow/review-output/lane-vm-runs.jsonl` (unmeasured today; the first run measures them).
9. **R9 The checkout guard (d9w, shipped in bug-109's 54e13c6).** `tests/conftest.py` raises
   `pytest.UsageError` when `refmatrix.__file__` is not under `<checkout>/src`, because
   `.venv-eval`'s editable install silently tests the dev tree from any clone. R1's redirect
   keeps it as its FIRST statement after `_REPO`, so a mis-pointed run never reaches the sandbox
   at all. Tiers 1 and 2 depend on it to prove which code they ran. {#r9}

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
4. **Whole-suite proof, by content (ns23-2).** The live logs change from normal activity during a
   13-minute run (the re-review saw the repo's `query.log` and `facts.log` written at 12:42 and
   12:43 while it only read), so size and mtime cannot be the check. A wrapper script OUTSIDE
   pytest, `scripts/sandbox-proof.sh`:
   - draws a fresh `RMX_SANDBOX_TAG` and runs the full suite with it, captured to
     `workflow/review-output/pytest-sandbox.log`;
   - before the run, records each live log's `(inode, size)`: `~/.refmatrix/query.log`,
     `~/.refmatrix/facts.log`, and the repo's `.refmatrix/query.log` and `facts.log`;
   - after the run, reads the DELTA of each log (the bytes past the recorded size; if the inode
     changed because a compaction rewrote `facts.log`, the whole new file) and FAILS if any delta
     line contains the run's tag, the string `/pytest-of-`, or the sandbox root, or (for
     `query.log`) has the d9g fixture shape: a learn/grep row with the `alpha|beta` pattern and no
     `cwd`. Once 21.1 has landed, every delta row also goes through
     `telemetry.is_test_artifact_row(row)` (21.1 R5, the one shared d8d predicate in
     `telemetry.py`, nm23-2), and a true result fails the check;
   - prints, per log, the delta line count and the number of rows that failed;
   - and the touches log gains 0 lines.
   Live activity during the run (other sessions' greps, the watcher) adds rows that carry none of
   these markers, so it cannot fail the check. A leaked sandbox row carries the tag (every sandbox
   path does), a pytest temp path, or the fixture shape; a leak with none of these is a new shape
   and is added to the check when found.
   - Pre-registered detector check, with no live write: the wrapper takes `--live-logs <dir>`
     (default: the four real paths). Pointed at a decoy directory holding copies of the four logs,
     with one grep test mutated to write its `query.log` row into the decoy (`REFMATRIX_ROOT` at a
     decoy store), the wrapper must FAIL on that tagged or fixture-shaped row. A detector that
     passes the mutated run is the defect. {#ac-4}
5. **Short root.** A test asserts `len(str(sandbox / "s" / ".refmatrix" / "rmxd.sock")) <= 100`.
   {#ac-5}
6. **Checkout guard (R9).** Through `pytester`, an inner session whose `sys.path` imports
   `refmatrix` from a decoy tree fails with `pytest.UsageError` naming both paths, before any test
   is collected. Mutation: compare against `_REPO` without `/src`; the decoy session must then
   collect, and the outer test fails. {#ac-6}
7. **Tier 1 isolation (R7).** On the lane, at one sha: (a) the precondition check fails when any
   one denied path is made readable by `rmxtest` (operator-run, recorded in the summary); (b) the
   lane log's collected count equals the developer run's at the same sha, plus the listed
   `gui/`-only tests (a silently shrunk collection is the defect, not a pass); (c) AC-4's
   content check over `~tholley`'s four live logs finds 0 lane rows; (d) a deliberately leaking
   test (writes `~/.refmatrix/query.log`) writes into `~rmxtest`, never `~tholley`. {#ac-7}
8. **Tier 2 isolation (R8).** On the VM, at the same sha: (a) every test tier 1 listed as
   `gui/`-only RUNS (none skipped); (b) the pass set equals tier 1's plus those tests, and any
   difference is reported per test id; (c) after `tart delete`, the host's live logs carry 0 rows
   from the run (AC-4's check), and `tart list` shows no `rmx-run-*` VM. {#ac-8}

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

## Revision round 2 (2026-10-14) {#rev-round-2}

| finding / decision | answered at |
|---|---|
| ns23-2 (size + mtime of live logs fails on normal activity), #t9-fixes "23.0 AC-4 checks added row content" | [[#r1]] (`RMX_SANDBOX_TAG`), [[#ac-4]] |
| nm23-2 (d8d predicate owner is `telemetry.py`) | [[#ac-4]] (`telemetry.is_test_artifact_row`, owned by 21.1 R5) |

## Amendment after round 3 (2026-10-14) {#rev-amend-lanes}

| finding / decision | answered at |
|---|---|
| d9w (checkout guard; `.venv-eval` editable install tested the dev tree from a clone) | [[#r9]], [[#ac-6]] |
| d9x (user: "both, write it into 23.0": separate-user lane and Tart macOS VM lane) | [[#amend-2026-10-14-lanes]], [[#r7]], [[#r8]], [[#ac-7]], [[#ac-8]] |

