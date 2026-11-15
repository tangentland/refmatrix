---
gmd: "0.1"
id: task-t0.9-test-isolation
title: "Task T0.9: test isolation: the Docker lane, the test-daemon kit, the macOS lane on the mini"
tags: [task, t0.9, tests, isolation, docker, lanes, daemon-kit, mac-mini, sandbox]
metadata:
  node_type: task
  status: drafting
  created: 2026-11-15
---

# Task T0.9: test isolation {#root}

> Queue row T0.9 (L170, Q46 = a). Order: (a) → (b) → (c) → (d), after 29.4 stage 2 (T0.2 and
> T0.3 on `master`). (c) and (d) need neither (a) nor (b); (d) waits on the user's setup of the
> mini ([[#d-setup]]). Four small builds, one agent each. No `src/` change, so no mutations and
> no ch-bsd round. Open decisions: [[#decisions]].

rel: part-of -> [[plan-of-plans#queue]]
rel: depends-on -> [[orchestration]]
rel: depends-on -> [[self-audit]]
rel: derives-from -> [[task-29.4-suite-health#r2]]
rel: depends-on -> [[task-29.4-suite-health#r4]]
rel: derives-from -> [[test-suite-audit-2026-11-15#vs-new-rules]]
rel: amends -> [[task-23.2-lock-hold-fixture#r4]]
rel: amends -> [[project_test_isolation_tiers_m1_mini]]
rel: derives-from -> [[reference_mac_mini_test_host]]
rel: reinforces -> [[feedback_external_calls_policy]]
rel: reinforces -> [[feedback_go_no_go_ranges_not_predrop]]

## Goal {#goal}

Every test run on the workstation queues behind one lock, beside the live fleet, and 49 tests
"prove" busy or down daemon behaviour against a patched value. After this task the portable
files run in containers that cannot reach a live store, a test gets a real busy, held, stalled
or dead daemon in one line, and the macOS-only files and the release gate run on a machine that
holds no store. **Linux is a test lane, not a supported runtime:** a Docker result never gates
a release.

## What is built {#build}

**One rule says where a file runs:** `tests/tiering.py::lane_of(path)`, first match wins.
`devtree` and `timing` by 29.4's rules ([[task-29.4-suite-health#r1]] items 1 and 2). `macos`
when the source matches `launchctl|launchd|\.plist|LaunchAgents|darwin|sys\.platform|fsevents|`
`caffeinate|taskpolicy|sysctl|sun_path|kickstart|com\.refmatrix\.`, or the file is listed in
`MACOS_FILES` with a reason and a registry row. Else `portable`. At `ce246c3`: 367 files, 55
match. 29.4 stage 4 adds `tier_of` to the same module. {#lane-of}

### (a) Docker probe {#a-probe}

`docker/test/Dockerfile`: `python:3.14-slim-bookworm` (linux/arm64) with `git`; an unprivileged
user (root ignores file modes); a venv installed from `.venv-eval`'s `pip freeze` (the editable
`refmatrix` line dropped) with an `rmx` script beside the interpreter (where `tests/devbin.py`
looks); the two default models copied from the host's HF cache; `HF_HUB_OFFLINE=1`. Only
`scripts/ptest-docker.sh --build` builds it (PyPI and the base image are the explicit network
steps). The probe runs `test_kwic.py`, `test_ingest_concurrency.py`, `test_sandbox_children.py`,
`test_models_offline.py`, `test_task21_1_query_rows.py` and `test_modelsrv.py` (87.1 s on the
host by `tests/shard_weights.json`) in one `--network none` container, and on the host the same
day. It records in `workflow/measurements/t0.9-docker-probe.md`: for duckdb, pylance, pyroaring, torch
and sentence-transformers the host version, container version and wheel / source build /
absent; image size; wall time per file on both sides with the load average; outcomes by node
and E line; peak memory.

Bands, committed before the run (r = container wall ÷ host wall): {#a-bands}

| Band | Condition | Action |
|---|---|---|
| go | five wheels; outcomes equal; r ≤ 1.5 | build (b) with 3 containers |
| go, re-size | as above but 1.5 < r ≤ 3 | build (b); N from a second run at 2, 3 and 4 containers |
| fix first | outcomes differ in ≤ 2 files for a test-side reason (a path, a tool) | fix, or list in `MACOS_FILES`; one re-run |
| stop | no 3.14 arm64 wheel and no source build under 15 min; or r > 3; or `src/` causes a difference | (b) stops, numbers to the user; (c), (d) go on |

### (b) Docker lane {#b-docker}

`scripts/ptest-docker.sh [--files F… | --select portable] [--shards N] [--name RUN]
[--max-minutes M]` wraps `scripts/ptest.py --where docker`. **`ptest.py` is 29.4's runner,
started here** to 29.4's text ([[task-29.4-suite-health#r2]]): the greedy placer over
`tests/shard_weights.json`, the printed per-shard command, the run directory
`workflow/review-output/<RUN>/` (`docker-<k>.log`, `failures.jsonl` from T0.2's
`RMX_FAILURES_OUT`, `summary.txt`), exit code = the worst shard's, and a summary that names
every lane it did not run and never says "all green". Stage 4 adds the host tiers, the serial
group and `--compare` to the same file.
- One container per shard: `docker create --network none`, no volume, mount, port, host pid or
  ipc. The clone goes in by `docker cp`: its `.git` and every file git does not ignore, with
  `.refmatrix/` and `.venv*` also excluded by name, so a container is a clone like any littlebig
  clone. Results come out by `docker cp`. The summary records the sha and the number of
  uncommitted paths.
- Three slots for the machine (`/private/tmp/claude-501/rmx-docker-slot-<k>.lock`, taken by the
  script). With none free the run waits and prints the holder.
- Exit 3, with the reason and the fix on stderr, when the engine is down or the image's
  `rmx.deps` label is not the hash of the Dockerfile, the pins and the model list.

### (c) Test-daemon kit {#c-kit}

`tests/daemons.py` (a conftest plugin). `daemon_factory(n=1, *, models=False, **env)` returns
`n` `KitDaemon`s: each a real `rmx daemon start --no-detach --no-watch` child in its own process
group, on `rmx_sandbox.short_root("d")` with its own `HOME` and `RMX_HOME` there, 2 cli and 2
bg workers, `RMX_DAEMON_SHUTDOWN_TIMEOUT_S=2`, and a `register_spawn` entry. Never in-process:
`kill()` needs a pid, and an in-process daemon's stop belongs to its host (L142).
- `wait_ready()`, `wait_models_warm()`: `timing.wait_for` under `HANG_GUARD_S`, no elapsed bound.
- `stop()` runs `rmx daemon stop` and waits for the exit. `kill()` SIGKILLs the group and leaves
  the stale pid file and socket: the "down" state. Teardown kills what is left and fails the
  test only for a `stop()` that did not finish.
- `hold_writer()`, `saturate()`, `stall()` are `with` blocks over **test ops inside the real
  daemon**, registered in `OPS` / `CLI_OPS` by `tests/daemon_testops.py`, which the child loads
  through the sandbox's `RMX_SANDBOX_PRELOAD` (a no-op in any other process). `hold_writer`:
  one bg op takes the real `_store_lock` and waits on a gate file. `saturate`: one held op per
  cli worker. `stall`: both pools full, so `ping` answers and no op does. An unreleased hold
  raises in the daemon at `HANG_GUARD_S`. Nothing is patched; the test ops get a row in
  `workflow/test_mock_registry.md`.
- `models=True` points the daemon (`RMX_MODEL_SOCK`) at **one `ModelServer` child per pytest
  process**, a session fixture that replaces `tests/task25_1_support.py`'s `_MODELSRV`.
- `SandboxDaemon` moves here from `tests/task21_1_support.py` as `KitDaemon`'s base; its 9
  importers are re-pointed and no alias stays. [[task-23.2-lock-hold-fixture]] keeps its
  write-count recorder and builds no second way to make a daemon busy.
- Not here: converting the 49 patched tests (POP row T1 step 4).

### (d) macOS lane on the mini {#d-mini}

`scripts/test-lane-host.sh <sha> --host <ssh-target> [--select macos|gate | --files F…] [--vm]`
pushes `<sha>` to a bare mirror on the host, clones it fresh, runs the selection with
`~/.venv-lane` (`HF_HUB_OFFLINE=1`, `PYTHONPATH=<clone>/src`), copies the run directory back
and deletes the clone. One run at a time (`/usr/bin/lockf` on the host). `gate` is every lane
but `devtree`. `--vm` hands the sha to the existing `scripts/test-lane-vm.sh --host`; what the
two share moves to `scripts/lane-lib.sh`.
- **Unreachable is loud:** `ssh -o BatchMode=yes -o ConnectTimeout=10` fails → exit 3, stderr
  `<host> unreachable: the macOS lane DID NOT RUN`, summary `macos: NOT RUN`. No automatic
  fallback. `--host local` is the explicit one: the same selection on the workstation under the
  host lock, named in the summary.
- Preflight, in order, exit 3 with the setup text: `xcode-select -p` (so `git` and `python3` are
  never called while they would open the install dialog), `git`, `~/.venv-lane` on 3.14 with the
  workstation's package versions, the model directories. Exit 4 if a remote host has a
  `~/.refmatrix` or a `com.refmatrix.*` LaunchAgent: the lane host holds no store.
- `--provision` (explicit, run by the lead, never part of a run) builds `~/.venv-lane` from PyPI
  and rsyncs the model directories from the workstation. It touches the lane user's home only.

**The user installs on the mini; no agent installs a system tool there:** {#d-setup}
1. Command Line Tools: `xcode-select --install`.
2. MacPorts for macOS 15, then `sudo port install python314` (the workstation runs MacPorts
   3.14.2). Homebrew's `python@3.14` also works: the lane needs `python3.14` on `PATH`.
3. Recommended: a standard user `rmxtest` with Remote Login allowed and the workstation's public
   key in its `authorized_keys`; the lane host is then `rmxtest@mini`.
4. Energy settings: prevent automatic sleep. Optional, not needed now: Tart and `rmx-golden`.

### Lanes, for agents and the release {#lanes}

| Run | Lane | Bound by |
|---|---|---|
| verify set, `portable` files | `scripts/ptest-docker.sh --files …` | 3 container slots |
| verify set with `macos` or `timing` files | `scripts/test-lane-host.sh <sha> --host mini --files …` | the mini's lock |
| `devtree` files; `--host local`; everything in row 2 until (d) is live | the workstation | `lockf /private/tmp/claude-501/rmx-test-lane.lock` |
| major release gate | the mini, `--select gate`, plus `devtree` in the dev tree | both locks |

## Acceptance criteria {#acceptance}

Suite tests fake only `docker` and `ssh` (external binaries on `PATH`, registered like the fake
`tart`). A **check** is a real run pasted in the build's summary.

| AC | Statement | Proved by |
|---|---|---|
| a1 | the probe table and its band are recorded, the bands were committed first, and `test_models_offline.py` passes with `--network none` | check: the measurement file, `git log` order, the probe log |
| b1 | every `docker create` has `--network none` and no `-v`, `--mount`, `--volumes-from`, `-p`, `--pid`, `--ipc`, `--privileged`; a fourth container waits for a slot and prints the holder | `tests/test_test_lanes.py` (extended) |
| b2 | `lane_of` gives every `tests/test_*.py` one lane; a planted `launchctl` file is never `portable`; an unreadable file is an error | `tests/test_suite_tiers.py` (29.4's file, created here) |
| b3 | same files and weights → same shards; a failing test in shard k fails the run and is in `failures.jsonl` with its E line; a container exiting 137 is `died`, never passed; engine down or stale image → exit 3 | `tests/test_ptest_runner.py` (29.4's file, created here) |
| b4 | 3 containers over the `portable` files at one sha: `docker inspect` shows no mounts and `NetworkMode none`; failures equal the host's by E line; wall time recorded | check |
| c1 | `daemon_factory(2)`: two pids and roots, socket paths under 104 bytes, both answer `ping` through `daemon.call`; after teardown no pid lives and the reaper reports nothing | `tests/test_daemon_kit.py` (new: `SandboxDaemon` has no test file) |
| c2 | one parametrized test through unpatched `daemon.call` (`retries=0`): under `hold_writer` a write op does not return while `ping` and a lock-free read do; under `saturate` a read does not return while `ping` and a write do; under `stall` neither returns and `ping` does; after release each returns | `tests/test_daemon_kit.py` |
| c3 | `stop()`: exit, no socket. `kill()`: no pid, stale pid file and socket, `rmx daemon status` says down. A fixture suite that leaves a hold and a daemon behind leaves no process, and its unfinished `stop()` fails that test by name | `tests/test_daemon_kit.py` over a `case_*.py` fixture |
| c4 | two `models=True` tests in one process share one `ModelServer` pid; `SandboxDaemon` and the model-server child are each defined once under `tests/`; `tests/daemons.py` has no `wallclock_allow.json` entry | `tests/test_daemon_kit.py`; check: grep; `tests/test_wallclock_census.py` |
| d1 | no sha → refused; unreachable host → exit 3, `DID NOT RUN`, no local run starts; no `git` or `python3` reaches the host before `xcode-select -p` succeeds; a host with `~/.refmatrix` → exit 4 | `tests/test_test_lanes.py` (extended), fake `ssh` recording argv |
| d2 | `--select macos`, then `--select gate`, on the mini at one sha: failures equal the workstation's by E line; wall time recorded | check |
| e1 | none of the files in [[#docs]] says "no Docker" or "There is no container" | check: grep, 0 lines |

## Docs {#docs}

With (b): CLAUDE.md `#development-commands` (the product runs on the host with no service
container; tests run in the lanes of [[#lanes]]) and `#test-discipline` rule 9 (the lane table);
`.claude/PROJECT_PROFILE.md` `#commands` and `#stack` (Linux is a test lane only);
[[orchestration#one-suite]]; `workflow/development_resources.md`;
`.claude/agents/ch-test-engineer.local.md`. With (c): rule 4 names `daemon_factory`. With (d):
the mini rows.

## Files {#files}

New: `docker/test/Dockerfile`, `scripts/ptest-docker.sh`, `scripts/ptest.py`,
`scripts/test-lane-host.sh`, `scripts/lane-lib.sh`, `tests/tiering.py`, `tests/daemons.py`,
`tests/daemon_testops.py`, `tests/test_daemon_kit.py`, `tests/test_suite_tiers.py`,
`tests/test_ptest_runner.py`, the measurement file. Changed: `scripts/ptest.sh`,
`scripts/test-lane-vm.sh`, `tests/conftest.py`, `tests/task21_1_support.py`,
`tests/task25_1_support.py`, the 9 `SandboxDaemon` importers, `tests/test_test_lanes.py`,
`workflow/test_mock_registry.md`, the docs. `src/`: none; a Linux-only failure caused by `src/`
is a registry row and a `MACOS_FILES` entry, never a patch to get green.

## Risks (self-audit) {#risks}

1. **Real:** b4, c1 and d2 are real runs; the fakes of `docker` and `ssh` prove only the scripts.
2. **Wiring:** the kit is tested through `rmx daemon start`, `rmx daemon stop` / `status` and
   `daemon.call` on the socket; the lane scripts are run as subprocesses.
3. **Census:** 9 `SandboxDaemon` files are covered; the 28 `spawn_daemon_subprocess` callers and
   the 49 patched tests are T1 step 4's. Lock text: CLAUDE.md, ORCHESTRATION, the local overlay.
4. **Bound:** kit waits and holds end at `HANG_GUARD_S` (60 s); ssh connects in 10 s and drops a
   dead link in 60 s; a container past `--max-minutes` (30) is killed and `died`. Slot and lock
   waits are unbounded on purpose and print the holder.
5. **Busy:** engine down → exit 3; slots or the mini busy → wait; mini down → exit 3, `NOT RUN`.
6. **Guard:** stale image (a `pyproject.toml` edit), store on the host, `lane_of` on a planted
   file: each has a must-fail case (b2, b3, d1).
7. **Loud:** every refusal is an exit code and a stderr line; a lane not run is in the summary.
8. **Handoff:** the 49 → POP row T1 step 4; `ptest.py` and `tiering.py` → 29.4 stage 4, its ACs
   unchanged; 23.2 by the edge above; the mini's setup → the user.

## Open decisions {#decisions}

**Decided 2026-11-15:** D1 yes and D5 as written (lead, L171); D2, D3, D4 as recommended (the user: "d2-4 agree").


- **D1 (lead, order):** (b) starts 29.4's runner before stage 4. Recommended: yes. A container
  cannot reach a live store, so the live-touch gate ([[task-29.4-suite-health#ac-12]]) binds
  host sharding only.
- **D2 (user):** the mini is down at a major release: (a) the lead runs `--host local`, named in
  the summary, or (b) the release waits. Recommended: (a), today's gate.
- **D3 (user):** a `rmxtest` user on the mini: recommended yes. Tart: not now (the mini holds no
  store, so a VM adds little).
- **D4 (user):** retire `scripts/test-lane-user.sh` ([[task-23.0-test-sandbox#r7]], never set
  up) once (d) is green. Recommended: yes; another machine isolates more than another user.
- **D5 (lead):** busy states come from test ops preloaded into a real daemon, not a debug op in
  `src/` (CLAUDE.md `#no-mocks`). Recommended as written.
