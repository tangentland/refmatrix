---
gmd: "0.1"
id: impl-task-23.0-test-sandbox
title: "Task 23.0: the test sandbox -- redirect before import, audit-hook refusal, children inherit it"
tags: [implementation-summary, task-23.0, tests, sandbox, isolation, bug-088, bug-101, plan-23]
metadata:
  node_type: implementation-summary
  status: complete
  created: 2026-10-15
  updated: 2026-10-15
---

# Task 23.0: the shared test sandbox {#root}

rel: implements -> [[task-23.0-test-sandbox]]
rel: derives-from -> [[plan-review-2026-10-14#t1-scope]]
rel: evidence-for -> [[bug_registry#registry]]

Clone `/Volumes/littlebig/refmatrix-task-23.0`, branch `task-23.0-test-sandbox`, RED tests at
`b86809a`, GREEN at `63d72db`, `26f80f2`, `7ba1dd4`. Rulings followed: d9bo (plan-review-2026-10-14,
2026-10-15), all seven plus the learn.off AC.

## What was built {#built}

- **`tests/sandbox_site/rmx_sandbox.py`** -- the one module. The three repeated shapes are each ONE
  function (the user's standing rule): `sandbox_env()` (the redirect of every HOME-derived
  path), `violation()` (the deny rule) and `child_env()` (propagation into a child). The
  conftest, every child (`sitecustomize.py`) and the three scripts call these; nothing is
  copied. Also: `enter()` (root + real-path capture + `deny.json` + hook on), `redirect()`,
  `new_store_root()`, `assert_under_sandbox()`, and the AC-4 content check
  (`leak_reasons`, `snapshot`, `delta_lines`, `check_logs`, CLI `snapshot` / `check`).
- **`tests/sandbox_site/sitecustomize.py`** -- R4: installs the same hook in every child from
  `$RMX_SANDBOX_ROOT/deny.json`; a violation writes the touches log, prints
  `SandboxViolation: ...` to stderr and `os._exit(86)` (d9bo #5). Fails closed (exit 86) if the
  site is on `PYTHONPATH` but no deny set is found.
- **`tests/conftest.py`** -- R9 guard first, via `importlib.util.find_spec` (no import, d9bo #6);
  then `enter()`, `redirect()`, then the first refmatrix import (`launchctl`, checked
  fail-closed, see [[#ac1-survivor]]). R2 autouse fixture: a fresh, INITIALIZED per-test store
  as `REFMATRIX_ROOT`, removed at teardown. `pytest_runtest_makereport` fails any test whose
  violation record is non-empty (d9bo #5); `pytest_sessionfinish` fails the run on a violation
  outside any test. The record-only `_recording_connect` is gone.
- **`scripts/sandbox-proof.sh`** -- AC-4, interface per d9bo #1.
- **`scripts/test-lane-user.sh`**, **`scripts/test-lane-vm.sh`** -- R7/R8. Operator setup is
  printed (`--setup`) and never run; the user lane runs through a root-owned installed copy
  (`/usr/local/libexec/rmx/test-lane-user.sh`, refused if it differs from the repo copy) so the
  sudoers grant is not a tholley-writable script; the VM lane refuses a third macOS VM before
  `tart clone` and records boot/run/disk to `lane-vm-runs.jsonl`. Both run AC-4's content
  check over the developer's four live logs after the run (AC-7(c), AC-8(c)).

## R4 round-10 extensions (#rev-amend-r10, d9bx) {#r4-ext}

In `rmx_sandbox.py` (one sitecustomize; CPython imports only the first on the path):
`CHILD_EXIT = 86` (refusal, and a child with no deny set) and `PRELOAD_EXIT = 87`, named once.
`$RMX_SANDBOX_CONNECT_LOG`: `_log_unix_connect()` appends `<path>\t<pid>` for every AF_UNIX
`socket.connect` BEFORE the deny check (a refused dial is logged and still exits 86); a log path
inside the deny set exits 86 at install. `$RMX_SANDBOX_PRELOAD`: `_run_preload()` runs an absolute
`.py` with `runpy.run_path` after `install_from_env()`; not absolute / not `.py` / raises (SystemExit
included) exits 87 with the cause on stderr. Consumers: 19.0 AC-6f, 21.3 AC-5.

## R6: pre-existing tests the sandbox broke, fixed {#r6-fixes}

Each read the live machine; each is fixed, none skipped.

| test(s) | what it read from the live machine | fix |
|---|---|---|
| `test_derive_surface.py` (10), `test_grep_case_every_path.py` (3), `test_grep_learned_reachable.py` (2), `test_grep_verify_before_cap.py` (2), `test_reingest.py::test_reingest_runs_code_then_memory_in_order`, `test_untrack.py::test_cli_untrack_dry_run_then_apply` | nothing live: they chdir into their own store and need the cwd walk, which R2's `REFMATRIX_ROOT` now overrides | `monkeypatch.delenv("REFMATRIX_ROOT")` next to each `monkeypatch.chdir` (R2's rule) |
| `test_agent_env.py::test_bashrc_section_parses_and_grep_function_calls_the_wrapper` | `[ -x "$HOME/refmatrix/bin/rmxgrep" ]` -- the DEPLOY tree's wrapper (`hooks.py:916`) | a stand-in `$HOME/refmatrix/bin/rmxgrep` under `tmp_path` |
| `test_gmd_lint_requires_version.py::test_the_repo_scope_is_clean_under_the_stricter_gate` | `$HOME/.claude/projects/<slug>/memory` (`scripts/lint-gmd.sh` scope) | the lint subprocess gets `RMX_SANDBOX_REAL_HOME` as `HOME` (memory files are not in the deny set). Fails in ANY clone anyway (557 errors on the host, slug of the clone path); unproven until a main-tree run |
| `test_mcp_memory_recall_routing.py::test_root_decodes_projects_slug_to_project_store` | none: `cli._root_from_projects_slug` compares a RESOLVED cwd with an UNRESOLVED `Path.home()`, which only a symlinked home (`/tmp`) exposes | the sandbox root is `realpath`ed. The latent `src/` defect is FLAGGED, not fixed (out of scope) |

## The deny set and the redirect {#deny}

Deny (R3), captured BEFORE the hook is on: `<real home>/.refmatrix`, the account home's
`.refmatrix` (pwd) if different, `<repo>/.refmatrix`, every root in both homes' registry and
`com.refmatrix.daemon.*` plists (8 roots on this workstation, viascope's included), each as
named and as resolved; TCP 7777 (+ `RMX_SANDBOX_HUB_PORT` in the mutation gate) on 127.0.0.0/8,
`localhost`, `::1`, `0.0.0.0`, `::`. Events: `open` (read and write), the `os.*` / `shutil.*`
mutations, `os.listdir`/`scandir`/`chdir`, `sqlite3.connect`, `glob`, `socket.connect`. "Real
home" is `RMX_SANDBOX_REAL_HOME`, else the outer `$HOME`, else pwd -- which is how the mutation
gates point a whole run at a decoy home (d9bo #3). A nested sandbox (a child pytest) inherits
the parent's `deny.json` instead of re-reading the live registry.

Redirect (R1): `HOME=<root>/h`, `RMX_HOME=<root>/h/.refmatrix`, `RMX_SANDBOX_ROOT`,
`RMX_SANDBOX_REAL_HOME`, `REFMATRIX_ROOT` (session default; per test in R2), `HF_HOME` (the
real model cache, read-only use), `PATH` (the interpreter's venv first, so `rmx` is
`.venv-eval/bin/rmx`), `PYTHONPATH` (+ `tests/sandbox_site`). Root:
`mkdtemp(prefix="rmx-[<tag>-]", dir="/tmp")`, removed at exit.

## Spawn sites (R4) {#spawn-sites}

No spawn site in `src/` or `tests/` at `b86809a` passes `-I`, `-E` or `-S` to a Python child
(searched for the flags in every `subprocess`/`sh` call). A test that builds its own `env={...}`
is covered by the spawn audit events: `child_env()` adds `tests/sandbox_site` to its
`PYTHONPATH`, the sandbox keys, and -- only when the test gave no `HOME` -- `HOME`, `RMX_HOME`,
`HF_HOME`. A test that set its own `HOME` keeps it, and `~/.refmatrix` follows it.

## Deviations, each named {#deviations}

- **d9bo-sanctioned test edits (only these).** `tests/test_sandbox_refusal.py`: `_real_home()`
  reads `RMX_SANDBOX_REAL_HOME`; the AC-2 `::1` probe uses `RMX_SANDBOX_HUB_PORT` (default
  7777). `tests/test_sandbox_children.py`: same `_real_home()`; AC-3(b) builds a decoy store
  with `Store.init()`, writes a `rmxd.pid` naming the test process (so `daemon status` READS a
  file in the store -- a fresh store has none it reads), and names the decoy to the child via
  `RMX_SANDBOX_DENY_EXTRA` (additive only: it can add a denied path, never remove one).
- **The per-test store is initialized** (~40 ms, removed at teardown), and the sandbox global
  store exists. Before the sandbox `_root()` always resolved to a store that existed (the repo's
  or the live global); 13 grep tests and R5's RED test write their row through it and failed on
  an empty dir ("no refmatrix at ...").
- **fd-relative opens.** `shutil`'s fd-based `rmtree`/`copytree` open bare names relative to a
  directory descriptor the `open` event does not carry; a relative path whose triggering frame is
  in `shutil.py` is skipped (the absolute root is checked by the `shutil.rmtree` event). Found on
  the first GREEN run: the sandbox's own cleanup opened `.refmatrix` by bare name with the cwd
  at the repo.
- **One fixture pass per process.** `from tests.conftest import source_of` (two test modules)
  executes the conftest again under another name; `enter()`/`redirect()` are once per process so
  that cannot move `HOME` or reset a test's `REFMATRIX_ROOT` mid-session.
- **AC-6's mutated decoy session errors instead of collecting**: past the bypassed guard, the
  conftest's `from refmatrix import launchctl` fails on the decoy package. The outer test still
  fails (killed), on the missing `UsageError`.

## The AC-1 survivor {#ac1-survivor}

The pre-registered AC-1 mutation SURVIVED at `63d72db`: the conftest's first refmatrix import
was `cli`, which does not import `launchctl` at module level, so `LAUNCH_AGENTS_DIR` was still
computed after the moved redirect. `26f80f2` makes the first import `launchctl` and checks
`LAUNCH_AGENTS_DIR` under the sandbox at conftest load for EVERY run (a one-file run never
reaches the canary, and `launchctl.install` writes plists there). Re-run: M1 killed by the
self-check (UsageError naming it); M1b (self-check removed) killed by the canary on
`LAUNCH_AGENTS_DIR` alone.

## Results {#results}

Second full run, clone at `7ba1dd4` (`workflow/review-output/task-23.0-full.log`): **23 failed,
2771 passed, 37 skipped** (21:21). Baseline: main tree at `23ad703`
(`pytest-baseline-23ad703.log`): 32 failed, 2776 passed. Compared by test id AND error text:

- **All 32 baseline failures are gone.** 17 carry the learn.off signature verbatim
  (`learning-disabled`, `learn drain: skipped (learning-disabled)`, `assert 0 == N` on learned
  rows): test_learn_queue (6), test_learn_broker_bounded (3), test_grep learn_from_grep (3),
  test_daemon_learn_guard (2), test_plan4_remedy degraded learn, test_grep_answered_by,
  test_grep_backstop. 14 more are the hook copies that read
  `$HOME/.refmatrix/learn.off` (`search_hooks.py:380`): test_search_hooks rewriter (9),
  test_rmxgrep (3), test_grep_stdin_dialect rmxrg (2) -- consistent with the redirect, not
  individually traced. test_brief_real_daemon was a DuckDB `Could not set lock` conflict.
- **New, 23, none caused by the sandbox's behaviour:**
  - 19 "dev tree" refusals (test_upgrade 4, test_plan4_remedy_r2 10, test_plan4_remedy_r3 2,
    test_plan1_remedy 2, test_onboard_huballd_curator 1): `.venv-eval` belongs to the main tree
    and refuses a clone's `src`. The identical 19 fail in the earlier clone run
    `bsd-0916-range-fullsuite-clean-00d0ded.log`; clone artifact.
  - 1 test_gmd_lint_requires_version (clone artifact, see [[#r6-fixes]]).
  - 3 test_sandbox_refusal: the RED-test defect in [[#red-defect]] (their 15 inner `test_inner.py`
    FAILED lines are the deliberate refusals, as expected).
- First full run (at `26f80f2`) had 44 failed; the 21 sandbox-induced ones are the R6 rows above.

Mutations: `workflow/review-output/task-23.0-mutations.log` -- every pre-registered mutation
(AC-1 x2, AC-2, AC-3, AC-4 x2, AC-6) and d9bo #5 KILLED; AC-2/AC-3 under a decoy home with
listening decoy sockets (d9bo #3), 0 decoy touches in the unmutated run. R4 round-10: MX1-MX9
KILLED by the candidate legs.

## The RED-test defect {#red-defect}

The three `test_sandbox_refusal.py` tests assert `"SandboxViolation" in` the inner session's
`FAILED` summary line, which pytest truncates to the terminal width. Under `| tee` (the mandated
run form) the width is 80 and `FAILED test_inner.py::test_connect_real_global_daemon_socket`
leaves ~17 columns: the type name is cut. With `COLUMNS=200` all four tests pass
(`task-23.0-refusal-cols200.log`); every inner probe does fail with `SandboxViolation` (the long
report shows it). Not edited (the RED tests are not mine). Recommended one-line fix: run the inner
session with `"-vv"` in `_run_inner` (pytest does not truncate at verbosity 2), or assert on
`result.stdout.str()`.

## Limits, stated {#limits}

- The audit hook sees what CPython audits. DuckDB and Lance open files in C: a live catalog
  opened only through `duckdb.connect` raises no event; the redirect (R1/R2) is what keeps a test
  off it. `os.stat`/`exists` are not audited (an existence probe is not refused).
- Tier 1 and tier 2 (AC-7, AC-8) are operator work and were not run: no `rmxtest` user, no Tart.
  Their scripts are pinned only by `tests/test_test_lanes.py` (no-sha refusal, third-VM refusal).
- The tests for d9bo #5 (a swallowed violation fails its test), the learn.off AC and the
  round-10 R4 legs are NOT committed: ch-implementer writes no tests. They were verified by probes
  (`task-23.0-probes.log`, `task-23.0-r10-*.log`); the round-10 candidate file is handed to
  ch-test-engineer.
- AC-4's `telemetry.is_test_artifact_row` hook-in belongs to 21.1 (it owns the predicate); the
  check here keys on the tag, `/pytest-of-` and the d9g shape.
