---
gmd: "0.1"
id: bsd-task23-0-sandbox-r1-ccdefef
title: "ch-bsd r1 task 23.0 test sandbox: no live reach found, but a shutil exemption bypasses the refusal and 18 tests stopped running"
tags: [ch-bsd, audit, task-23.0, plan-23, sandbox, isolation, bug-127]
severity: BULLSHIT
plan: plan-23-bounded-write-harness
task: task-23.0
metadata:
  node_type: audit
  created: 2026-10-15
  updated: 2026-10-15
---

# ch-bsd findings: task 23.0 test sandbox, round 1 {#root}

**Commit:** `ccdefef673dc87fa35d1b8f831d0f089f758d52a` (branch `task-23.0-test-sandbox`, clone
`/Volumes/littlebig/refmatrix-task-23.0`; range `b86809a..ccdefef` on master `b381b6d`)
**Date:** 2026-10-15T05:43-0700
**Author:** Todd Holley / Opus 5.5 / ch-implementer + ch-test-engineer
**Files changed:** 23 (2566+/47-)

rel: specified-by -> [[task-23.0-test-sandbox]]
rel: evidence-for -> [[impl-task-23.0-test-sandbox]]
rel: derives-from -> [[plan-review-2026-10-14]]

## Method {#method}

- **Decoy gate, extended:** `scratchpad/bsd230/gate.py`, `gate2.py`. The outer `HOME` points at a
  decoy home with listening `rmxd.sock` / `hub.sock` / `models.sock`, decoy logs, and a decoy TCP
  listener (`RMX_SANDBOX_HUB_PORT`). Added beyond the implementer's harness:
  (a) a decoy `<clone>/.refmatrix/` with a listening `rmxd.sock` and three logs, so the clone
  behaves like the main tree, where the repo store exists;
  (b) PATH shims for `launchctl` (lets `print` through, refuses every mutating verb), `lsof`, and
  `kill`;
  (c) a probe (`-p bsd230probe` in-process, and `RMX_SANDBOX_PRELOAD` in children) that logs
  every C-level `duckdb.connect` / `lance.dataset` / `lance.write_dataset` and every `os.kill`,
  and RAISES on a live root or on one of the 9 live pids (8 daemons and the hub);
  (d) the `rmx_sandbox.check_logs` content check, with a fresh tag, over the 4 real live logs.
- **Runs:** two full suites. `bsd-23.0-r1-decoy-full.log` had a decoy HF cache, which made the
  model tests fail for the gate's own reason. `bsd-23.0-r1-decoy-full2.log` used the real HF
  cache plus a temporary `.venv-eval` symlink in the clone, so the `RMX`-gated end-to-end child
  tests run, as they do in the main tree. There were also targeted runs
  (`bsd-23.0-r1-decoy-skipped-and-models.log`, `bsd-23.0-r1-probes.log`) and 3 mutations
  (`bsd-23.0-r1-mut-M{A,C,F}.log`), all under the gate. The clone was restored with
  `git checkout` after each mutation. `git status` is clean, and the probe file and symlink are
  removed.

## What held (evidence, not findings) {#held}

- **No live reach in two full runs.**
  - Decoy socket accepts: 0. Repo-decoy logs: 0 bytes. Live-pid kills: 0 of 214 `os.kill`
    events, and all 9 live pids are alive afterward.
  - Shims: 112 `launchctl` calls, all `print`. 0 mutators.
  - C-level opens on a live root: 0. Scanned: 8,714 `duckdb.connect` and 320 lance opens, both
    in-process and in children.
  - Touches-log lines outside the 3 deliberate modules: 0.
  - Live `~/.refmatrix/{query,facts}.log` delta: 0 lines.
- **(6) Baseline: 31 of 32 confirmed.** The learn.off family (17 + 14) passes under the sandbox.
  The 19 "dev tree" failures are clone-only: `upgrade.runtime_identity` sets
  `dev_tree = venv_tree != code_root`. `.venv-eval` belongs to the main tree, so only a clone's
  `PYTHONPATH` trips it. The 32nd case is [[#s4]].
- **(5)** Every `refmatrix` module-level `Path.home()` (`launchctl.LAUNCH_AGENTS_DIR`,
  `cctree.PROJECTS`, `gmd_curator.DEFAULT_LINT`) is computed after the redirect. Nothing imports
  `refmatrix` before the conftest: no `tests/__init__.py`, no `pytest11` entry point, and
  `find_spec` does not execute the package. No `src/` code reads `pwd`, and none hardcodes
  `/Users/...`.

## Findings {#findings}

### BULLSHIT: the bug-127 exemption lets relative-path `shutil` copy, move and rmtree of a denied store through, with no touches line {#b1}

**File:** `tests/sandbox_site/rmx_sandbox.py:383-394` (`_caller_is_fd_walker`) and `:333-337`
(`violation(... dir_fd_relative)`).
**What:** any relative path whose triggering frame is in `shutil.py` is skipped. That includes
`shutil`'s OWN public audit events (`shutil.copyfile`, `shutil.rmtree`, `shutil.move`'s
`os.rename`), which `sys.audit` raises from inside `shutil`.
**Why it's bullshit:** the refusal is bypassed silently. Neither a raise nor a record nor a
touches-log line happens, so AC-4 cannot see it either. From the repo cwd (the default in the
main tree), `shutil.copyfile(".refmatrix/catalog.read.duckdb", x)`,
`shutil.rmtree(".refmatrix/queries")` or `shutil.move(".refmatrix/...", y)` reach the live store.
**Evidence:**
- Standalone probe on a scratch deny set: `open rel: refused`,
  `shutil.copyfile rel: NOT REFUSED`, `shutil.copy2 rel: NOT REFUSED`,
  `shutil.move rel: NOT REFUSED`, `shutil.rmtree rel: NOT REFUSED`. The denied file's content
  ("secret") ended up in `out/stolen`.
- Inside the real conftest under the gate,
  `test_p3_relative_shutil_copy_of_denied_store` PASSED (`bsd-23.0-r1-probes.log`), and the
  touches log gained no line for it.

**Fix (cheap fix, rule 10):** the false positive was in `shutil`'s fd-based traversal only.
1. Never apply the skip to `shutil.*` events.
2. Apply it to `open` and `os.*` events only when the raw argument is a bare entry name (no
   `os.sep`) AND the frame's `co_name` is one of the fd-walk internals (`_rmtree_safe_fd`,
   `_rmtree_safe_fd_step`, ...).
3. Pin both directions in `test_sandbox_refusal.py`: relative `copyfile`, `move` and `rmtree` on
   a denied root are refused; the sandbox's own `remove_tree` from the repo cwd still passes.

Effort: about 10 lines.
**Pattern match:** YES. A check placed so that a false positive is suppressed by widening the
exemption.

### BULLSHIT: 18 pre-existing tests now silently skip under the sandbox (R6) {#b2}

**Files:**
- `tests/test_models_offline.py:22`: `HF_HUB = Path.home() / ".cache" / "huggingface" / "hub"`.
  12 tests, including the external-calls / offline-load guards.
- `tests/test_cctree_web.py:127-131`: "no Claude Code transcripts on this host". 5 tests.
- `tests/test_rewriter_wrapper_resolution.py:114`: "no deploy tree". 1 test.

**What:** each skip condition reads a HOME-derived path. Under the redirect, each condition is
now true.
**Why it's bullshit:** the baseline main-tree run (`pytest-baseline-23ad703.log`) has 0 skipped.
The implementer's run reports "37 skipped" with no accounting. R6: "a pre-existing test that
breaks under the sandbox is FIXED ... never `--ignore`d or `-k`'d away". A self-skip is the same
shrink, and less visible. The offline-model tests are the regression guard for the
no-implicit-network rule.
**Evidence:** `bsd-23.0-r1-decoy-full2.log` SKIPPED lines: 12 `embed/rerank/CodeRankEmbed model
not cached`, 5 `no Claude Code transcripts on this host`, 1 `no deploy tree on this machine`.
These ran with `HF_HOME` pointing at the real cache, which `sandbox_env` already exports.
**Fix:**
- `test_models_offline`: resolve `HF_HUB` from `os.environ["HF_HOME"]`; R1 already exports it.
- `test_cctree_web`: the fixture writes a synthetic transcript under the sandbox's
  `~/.claude/projects/<slug>/` and asserts on that.
- The deploy-tree test: build a stand-in `$HOME/refmatrix/bin/rmxgrep`, as `test_agent_env` now
  does.
- Add a guard to R6: the sandboxed run's skip count must equal the baseline's, plus any listed
  clone-only skips.

**Pattern match:** YES (silent scope shrink).

### SKETCHY: a child's refusal is invisible when the spawner ignores its exit code {#s1}

**File:** `tests/conftest.py:183-195` (d9bo #5 covers in-process only).
**What:** a child exits 86 and writes the touches log. If the code that spawned it ignores the
return code (a best-effort hook, a detached `rmx daemon start`, `check=False`), the test passes
and `pytest` exits 0. Only `sandbox-proof.sh` reads the touches log.
**Evidence:** `test_p1_child_violation_ignored_rc_passes` PASSED and the session exited 0
(`bsd-23.0-r1-probes.log`), while the touches log named it. No live path was reached, because
the child refused, so the safety held and the reporting did not.
**Fix:** record the touches-log size at setup. In `pytest_runtest_makereport(when=="teardown")`,
fail the test for any new line whose test-id field equals `item.nodeid` and whose pid differs
from `os.getpid()`. Express the deliberate probes as `@pytest.mark.sandbox_probe` rather than a
module prefix.

### SKETCHY: violations recorded under a key no report pops are dropped; the "outside any test" leg is unpinned {#s2}

**File:** `tests/conftest.py:191,198-204`.
**What:** `RECORD` is keyed by `PYTEST_CURRENT_TEST`. Some keys are never popped:
- an in-process `pytester` inner nodeid;
- a background thread in the window after the teardown report but before pytest unsets the
  variable.

`pytest_sessionfinish` pops only `NO_TEST`, so these entries are never checked.
**Evidence:**
- `test_p2_pytester_inner_swallowed_violation_passes` PASSED and the session exited 0.
- Mutation MC (`session.exitstatus = ...` replaced by `pass`) SURVIVED all 5 sandbox test files
  (`bsd-23.0-r1-mut-MC.log`).

**Fix:** `pytest_sessionfinish` fails on ANY non-empty `RECORD` left, not just `NO_TEST`. Add a
test that records a violation under `NO_TEST` (a thread that runs between tests) and asserts the
session's exit status.

### SKETCHY: R4's spawn-hook propagation (`child_env`) has no test {#s3}

**File:** `tests/sandbox_site/rmx_sandbox.py:281` (`_SPAWN_EVENTS`) and `:236` (`child_env`).
**What:** the module docstring says "a test that builds its own `env={...}` cannot launch an
unsandboxed child". Every child test passes `dict(os.environ)`, which already carries the
sandbox.
**Evidence:** mutation MA (`_SPAWN_EVENTS = {}`) SURVIVED all 7 sandbox and lane test files
(`bsd-23.0-r1-mut-MA.log`, exit 0).
**Fix:** add a test that spawns `[sys.executable, "-c", <dial the real hub socket>]` with
`env={"PATH": os.environ["PATH"]}` (no `PYTHONPATH`, no `HOME`) and asserts all of:
- exit `CHILD_EXIT`;
- `SandboxViolation` on stderr;
- a second child, with the same scratch env, prints `Path.home()` under `RMX_SANDBOX_ROOT`.

### SKETCHY: the baseline claim "all 32 gone" counts a SKIP as a fix; `test_brief_real_daemon` still fails identically {#s4}

**File:** `workflow/implementation_summaries/task-23.0-test-sandbox.md#results`.
**What:** `tests/test_brief_real_daemon.py` is `skipif(not <repo>/.venv-eval/bin/rmx)`. A clone
has no `.venv-eval`, so the test never ran in `task-23.0-full.log`.
**Evidence:** with `.venv-eval` linked into the clone, the test FAILS with the same baseline text:
`_duckdb.IOException: ... Could not set lock on file "/private/tmp/bd.*/.refmatrix/catalog.A.duckdb": Conflicting lock is held ...`
(`bsd-23.0-r1-decoy-skipped-and-models.log`, `bsd-23.0-r1-decoy-full2.log`). The same clone
artifact hid every `RMX`-gated end-to-end child-spawn test from the implementer's verification.
With the link, those tests passed and touched nothing (216 passed).
**Fix:** correct #results: 31 gone, 1 still failing (a pre-existing tmp-store lock race, not the
sandbox). Log that race in `workflow/bug_registry.md`; no row exists. Run the full suite in the
main tree, or a clone with `.venv-eval` linked, before claiming child-spawn coverage.

### SKETCHY: AC-4 has never run whole-suite, and its `/pytest-of-` marker fails on live doc ingestion {#s5}

**File:** `scripts/sandbox-proof.sh`; `rmx_sandbox.leak_reasons`.
**What:**
1. `workflow/review-output/pytest-sandbox.log` is a 1-test run. AC-4's full proof was never
   executed.
2. My full-run content check flagged 2 rows in the live repo `facts.log` as "pytest temp path".
   They are the live watcher ingesting ch-bsd ledgers that QUOTE bug-101's
   `/private/var/folders/…/pytest-of-tholley/…` shape. AC-4 says live activity "cannot fail the
   check", but the ledger proves it can, and this report will add more.

**Fix:**
- Apply the `/pytest-of-` marker to row FIELDS that are paths (`path`, `cwd`, `root`), not to
  free text (`tldr`, `content`, `meta.description`).
- Run `scripts/sandbox-proof.sh` once, full-suite, on the main tree. That is safe after [[#b1]]
  is fixed, given this round's decoy evidence.

### SKETCHY: unaudited non-Python reach to live processes is neither refused nor declared {#s6}

**Files:**
- `src/refmatrix/launchctl.py:272,405,445`: `HUB_LABEL` is global, so `install_hub` and
  `uninstall_hub` boot out the LIVE hub regardless of `HOME`.
- `src/refmatrix/hub.py:1110-1166`: `stop_hub` runs `_pid_on_port(7777)` via `lsof`, then
  `os.kill`. That is the live hub, pid 4191 today.

**What:** the audit hook sees none of these: a `launchctl` or `lsof` child is not Python, and
`os.kill` is not in the deny events. `#limits` in the summary lists only DuckDB/Lance and `stat`.
**Evidence:** 0 occurrences today. Both full runs show only `launchctl print` (112) and no kill on
a live pid, because every current caller is mocked (`test_hub.py:178-199`,
`test_hub_plist_devtree.py:65`). One unmocked `rmx hub stop` or `install_hub` test would kill or
boot out the live hub.
**Fix:**
- Prepend `tests/sandbox_site/bin/` to the sandbox `PATH` with a `launchctl` shim that lets
  `print` and `list` through and refuses mutating verbs (exit 86 plus a touches line).
- Have the audit hook refuse `os.kill` / `os.killpg` on pids captured at `enter()`: the deny
  roots' `rmxd.pid`, the hub pid, and the 7777 listener.
- State the remainder in `#limits`.

### SKETCHY: R7/R8 (tiers 1 and 2) have not run; R7 makes tier 1 the gate for "any merge to master" {#s7}

**File:** spec [[task-23.0-test-sandbox#r7]]; summary `#limits`.
**What:** the summary's status is `complete` while AC-7 and AC-8 are unexecuted (no `rmxtest`
user, no Tart). Both lane scripts are pinned only by argument and refusal tests. The
implementer's summary is not hiding this. But the caller states that this task gates the merge
and the next deploy, and R7 names tier 1 as that gate.
**Fix:** either run tier 1 (operator setup), or record an explicit decision that this merge
proceeds on tier 0 plus this decoy evidence. Keep AC-7 and AC-8 open as tracked items in
plan-23, not "complete".

### MEH: "`RMX_SANDBOX_DENY_EXTRA` can only ADD" is unpinned {#m1}

Mutation MF replaced the union with `sorted(add)`. It drops the whole live deny set for any child
given an extra, and it SURVIVED (`bsd-23.0-r1-mut-MF.log`). Fix: the AC-3(b) child also dials the
real hub socket path and must still exit 86.

### MEH: `DELIBERATE_PROBE_MODULES` excludes whole modules from AC-4's touches check {#m2}

Any future accidental touch by a test added to those three modules is excluded too. Key the
exclusion on a marker or on an expected (test, target) list.

### MEH: the lint-test fix hands the real `HOME` to a child, and it is unproven {#m3}

`tests/test_gmd_lint_requires_version.py:119-125`. `RMX_SANDBOX_REAL_HOME` is now a documented
way out of the sandbox, visible to every test and child, and `~/.claude/**` is not in the deny
set. The test still fails in every clone ("unproven until a main-tree run"). Fix: give
`lint-gmd.sh` a `RMX_LINT_MEMORY_DIR` override and point it at the real memory dir read-only,
leaving `HOME` sandboxed. Prove it once in the main tree.

### MEH: a spawn's `cwd` inside a denied root is not checked {#m4}

The `subprocess.Popen` event carries `cwd` (argument 2). Refusing a deny-set cwd costs one line.

### MEH: no in-process way to expect a violation {#m5}

`pytest.raises(SandboxViolation)` in an ordinary test is flipped to failed by the report hook.
Wave-1 tests that want an in-process deliberate refusal need `@pytest.mark.sandbox_probe` (shared
with [[#s1]]).

## Verdict {#verdict}

DIRTY: 14 findings (2 BULLSHIT, 7 SKETCHY, 5 MEH).

Hunt (1) found NO live reach in two full decoy runs plus the C-level probe. The blocking items:
- [[#b1]]: a real refusal bypass, invisible to every check.
- [[#b2]]: 18 tests that silently stopped running.

The merge to master should wait for both.

rel: contradicts -> [[task-23.0-test-sandbox#r3]]
rel: contradicts -> [[task-23.0-test-sandbox#r6]]
rel: contradicts -> [[task-23.0-test-sandbox#ac-4]]
