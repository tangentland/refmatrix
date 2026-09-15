---
gmd: "0.1"
id: bsd-plan1-deploy-runtime-r3-e6c4081
title: "plan-1 round 3: relaunch guard fires in the incident state; all round-2 BULLSHIT/SKETCHY closed; residue is registry + lint scope + two unread branches"
tags: [bsd, findings, plan-1, deploy, re-review]
severity: SKETCHY
plan: plan-1-deploy-runtime
task: task-1.1-plan-1-deploy-runtime, task-1.2-plan-1-deploy-runtime, task-1.3-plan-1-deploy-runtime
metadata:
  node_type: bsd-report
  commit_range: 6cc33e9..e6c4081
  round: 3
---

# ch-bsd findings — plan-1-deploy-runtime round 3 (6cc33e9..e6c4081) {#root}

**Commits:** 3f88873 (test(subject) spawned-daemon promote), 76bdc9e (fix(deploy) relaunch guard / alert publish / unknown hot), e6c4081 (merge remedy-plan-1-r2)
**Date:** 2026-09-14
**Author:** Todd Holley / Fable 5.1 / orchestrator
**Files changed:** 9 (cli.py, hub.py, tests/test_plan1_remedy.py, tests/test_subject.py, task-4.4 spec, ledger files)

rel: amends -> [[bsd-plan1-deploy-runtime-r2-6cc33e9]]
rel: evidence-for -> [[plan-1-deploy-runtime#q3]]

## Verified (read-only, live 0.68.1) {#verified}

- Deploy: `~/refmatrix` at e6c4081 (reflog: ff-pull 20:47:23); `~/refmatrix/.venv` imports `/Users/tholley/refmatrix/src/refmatrix/__init__.py` 0.68.1; `rmx version -v` shows no `[DEV TREE]`. Daemon pid 83633 started 20:47:39 via `~/bin/rmx daemon start --no-detach` (after the pull, so it runs the new guard); cli.log records `daemon restart --relaunch` at 20:47:42 exit 0 in 19.2 s. Hub pid 83679 restarted 20:47:46 (version handshake), `code:` under `~/refmatrix/src`; orderly still renders `[UNVERIFIED v0.65.0]`.
- **Incident replay on paper (#b-1-r2):** CLI under `~/refmatrix/.venv` with `.pth` → dev `src/`: `runtime_identity()` → `venv_tree=~/refmatrix`, `code_root=dev`, `dev_tree=True`. Daemon (same venv via launchd) → `_process_identity()` → ping `{code_path: dev, dev_tree: True}`. `_verify_relaunch` (cli.py:2745-2780): ping succeeds → `res` has `code_path` → `mine_ident["dev_tree"] or res["dev_tree"]` → `ClickException("[DEV TREE] …")` before the path compare. Fires. Path-mismatch is now the third check; `relaunch verified` prints only after all three.
- **Ping failure / missing field (#s-2-r2):** `daemon.call` raising → `ClickException("… code path cannot be read")`; `ok: False` → `res={}` → "reports no code path"; `ok: True` without `code_path` → same raise. No path reaches `relaunch verified` without a non-empty `code_path`; the `code=` suffix is now unconditional.
- **Alert publish (#m-3-r2):** `Hub._queue_alert_once` (hub.py:561-575) is the loop body; `_queue_alert_loop` (hub.py:557) calls it; the thread starts at hub.py:718-720. `test_queue_alert_once_publishes_on_dev_tree` runs the real method body against a fake bus and asserts the `global:queues` publish for a `dev_tree` row and silence otherwise.
- **Unknown identity hot (#m-4-r2):** `_queue_row_is_hot` (hub.py:957) includes `identity == "unknown"`; `_annotate_identity` (hub.py:989) sets that key live (orderly). `test_unknown_identity_row_is_hot` covers the predicate. Live bus proof is pending: `QUEUE_ALERT_INTERVAL_S` is 1800 s and the hub restarted 20:47:46, so the first tick with the new predicate is ~21:17:46; the newest `global:queues` entry is 20:19:51 (previous hub). Not a defect; re-check after 21:18.
- **Task 4.4 spec** carries the orderly `code_path` + no-`[UNVERIFIED]` criterion.
- **Memory / bridge (#m-5-r2 part):** bridge job 961a8791ca36 `status=done 209/209`; `rmx memory get feedback_save_state_means_handoff` → id 2888079 and `feedback_refmatrix_dev_deploy_split` → id 2888078 both resolve. `feedback_deploy_tree_is_the_runtime` in the store carries the reworded sentence ("fails when either side reports `dev_tree`, when the daemon's code path cannot be read, or when it differs from the CLI's").
- Tests (dev tree, `.venv-eval`): `test_plan1_remedy.py` + `test_subject.py` + `test_runtime_identity_surface.py` + `test_upgrade.py` → 39 passed in 1.8 s (`workflow/review-output/pytest-bsd-plan1-r3-e6c4081.log`); the spawned-daemon promote test ran for 1.07 s, not skipped (`pytest-bsd-plan1-r3-subject-e6c4081.log`). Mutation strength: the new incident test is the same fixture my r2 scratch test used to prove the old code printed `relaunch verified` (exit 0), with the assertion inverted, so it fails on the pre-fix guard.
- Deferral sweep over added lines in cli.py/hub.py/tests: no hard or soft deferrals. Plan status honest: plan `in-progress`, tasks `complete`.
- test_subject.py (also in range): the in-proc promote test was split into a daemon-down refusal test (asserts the real "daemon not running" ClickException) and a real-path test on a spawned daemon; direction is correct (mock graduated, not added).

### Round-2 findings — status {#status}

| # | Status | Evidence |
|---|--------|----------|
| #b-1-r2 relaunch guard blind in incident | CLOSED | dev_tree check on both sides before the path compare; incident-state test; live relaunch at e6c4081 printed `code=~/refmatrix/src/…` |
| #s-2-r2 ping error → verified | CLOSED | exception and missing-field both raise; `code=` unconditional; test for the missing-field path |
| #m-3-r2 publish untested | CLOSED | `_queue_alert_once` + fake-bus test |
| #m-4-r2 unknown not hot / task 4.4 | CLOSED (code + spec); live tick pending 21:17 | predicate + test; spec criterion added |
| #m-5-r2 lint + bridge | HALF | bridge done, memories resolve; memory-dir lint 6 → 3 errors, see [[#m-2-r3]] |

## Findings {#findings}

### SKETCHY: `FakeBus` / `FakeHub` / `QuietHub` added without a registry row {#s-1-r3}

**File:** `tests/test_plan1_remedy.py:197-215`, `workflow/test_mock_registry.md`
**What:** `test_queue_alert_once_publishes_on_dev_tree` fakes the hub's bus (`publish`, `refinement_queue`) and the Hub instance itself (`_gather_queues`), calling `Hub._queue_alert_once(FakeHub())`. The registry has rows for `runtime_identity`, `daemon.call/ping/served_identity`, and `hub._daemon_identity`; none for `hub.bus` or a fake Hub self (grep for `FakeBus|FakeHub|QuietHub|bus` in the registry: empty).
**Why it's sketchy:** rule 3 — every mock is classified or it is invisible to the graduation plan. The fake bus is the right shape (the real method body runs; only the process boundary is faked), so the fix is bookkeeping, not a rewrite. Second registry omission in plan 1 (#s-5 round 1 added rows after the fact); a third is BULLSHIT.
**Fix:** two rows: `hub.bus` (fake publish/refinement_queue) — internal-active, permanent for the alert unit test, real-bus coverage = the hub integration path; `Hub` self with stubbed `_gather_queues` — internal-active, graduated by `test_gather_queues_carries_identity_end_to_end`.
**Pattern match:** YES — [[bsd-impressions#imp-summary-claims-bookkeeping]] (registry untouched while the surface test lands).

rel: contradicts -> [[test_mock_registry#root]]

### MEH: memory-dir lint still reports 3 dangling ADR links; task 1.3 says "memories linted" {#m-2-r3}

**File:** `~/.claude/projects/-Users-tholley-claude-tools-refmatrix/memory/project_memory_compile_shipped.md:22`, `project_phase_b_intuition_memory.md:96`, `project_phase_c_shipped.md:93`
**What:** `python3 tools/gmd/lint.py <memory dir>` → 3 errors (down from 6 in round 2): `[[adr-0002-subject-memory-container]]` and `[[0001-intuition-lance-integration]]` resolve to `docs/adr/0002-…md` and `docs/adr/0001-…md` in this repo, which the memory-dir lint scope cannot see. Carry-over of #m-5-r2; not touched by this range.
**Fix:** lint the memory dir together with `docs/adr` (or `lint --scope`), and say so in task 1.3, or repoint the three links.

### MEH: the ping-exception branch of the relaunch guard has no test {#m-3-r3}

**File:** `src/refmatrix/cli.py:2755-2759`, `tests/test_plan1_remedy.py:186-197`
**What:** `test_relaunch_fails_when_the_daemons_code_path_cannot_be_read` docstring says "A ping without code_path (or a ping error) is not 'verified'", but the fixture only returns a result without `code_path`; no test makes `daemon.call` raise. The structure covers it (an exception cannot reach `relaunch verified`), so MEH, but round 2's finding named both branches and the r2 scratch test `test_ping_exception_during_code_path_check_passes_silently` was the ready-made RED case.
**Fix:** a second case with `daemon.call` raising `OSError`, asserting exit != 0 and "cannot be read" in output.

### MEH: `identity_error` is emitted by two producers and read by nobody {#m-4-r3}

**File:** `src/refmatrix/daemon.py` (`_process_identity` fallback), `src/refmatrix/hub.py:1015` (`_hub_identity` fallback); consumers `_annotate_identity` (hub.py:979-995), `_verify_relaunch`, `daemon status`
**What:** when `runtime_identity()` raises inside a daemon, the ping reports `code_path=refmatrix.__file__`, `dev_tree=False`, `identity_error=<msg>`. Every consumer keys on `code_path`/`dev_tree` only: the hub row is annotated as verified-clean, `daemon status` prints a clean `code:` line, and the relaunch guard passes the dev-tree check on that side (the CLI-side check still fires in the shared-venv incident). Round 2 called the fallback "visible"; on inspection it is visible only in raw JSON. A guard that rewrites "could not compute" into "not a dev tree" is the `except → green` shape one call site over.
**Fix:** treat `identity_error` like `unknown`: `_annotate_identity` → `identity: "unknown"` (hot); `_verify_relaunch` → raise "identity could not be computed"; `daemon status` → `[UNVERIFIED]` suffix.
**Pattern match:** YES — [[bsd-impressions#imp-silent-pass-migrates]].

## Also reviewed {#also}

- `_queue_alert_once` returns a bool the loop ignores; the test does not assert it either. Harmless; drop the return or assert it.
- `_verify_relaunch` calls `runtime_identity()` unguarded — a raise there propagates as a traceback, which is loud, not silent. No finding.
- The four untracked plan-4 RED tests (`test_daemon_adopt.py`, `test_daemon_learn_guard.py`, `test_hub_watchdog.py`, `test_repair_entities.py`) were not run and are not counted.

## Verdict {#verdict}

**DIRTY — 4 findings (0 BULLSHIT, 1 SKETCHY, 3 MEH). No blocker.**

Every round-2 BULLSHIT and SKETCHY is closed and proven against the live fleet: the relaunch guard now fails on `dev_tree` on either side before comparing paths, a ping that errors or lacks `code_path` is "not verified", the alert loop body is a testable method, and unknown-identity rows are hot. The bridge ran and the migrated memories resolve. What remains is bookkeeping (two registry rows), a lint-scope note, one untested branch, and one unread diagnostic field. Plan 1 may flip to `completed` once [[#s-1-r3]] is addressed in the same commit as the flip; the MEHs can ride any later sweep. Re-check the `global:queues` channel after 21:18 for an alert carrying the orderly `identity: unknown` row.

rel: contradicts -> [[test_mock_registry#root]]
