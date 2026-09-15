---
gmd: "0.1"
id: bsd-plan1-deploy-runtime-r2-6cc33e9
title: "plan-1 re-review: alert, upgrade, hub surfaces closed; the relaunch guard still cannot fire in the incident state"
tags: [bsd, findings, plan-1, deploy, re-review]
severity: BULLSHIT
plan: plan-1-deploy-runtime
task: task-1.1-plan-1-deploy-runtime, task-1.2-plan-1-deploy-runtime, task-1.3-plan-1-deploy-runtime
metadata:
  node_type: bsd-report
  commit_range: cabce24..6cc33e9
  round: 2
---

# ch-bsd findings — plan-1-deploy-runtime re-review (cabce24..6cc33e9) {#root}

**Commits:** 0d2cba5 (remedy-plans-1-2, 0.68.1), 9fbbcd6/65f1858 (remedy-hooks-check-stability), 6cc33e9
**Date:** 2026-09-14
**Author:** Todd Holley / Fable 5.1 / orchestrator
**Files changed (plan-1 relevant):** hub.py, upgrade.py, daemon.py, cli.py (`_verify_relaunch`, `hub_status`), modelsrv.py, tests/test_plan1_remedy.py, tests/test_runtime_identity_surface.py, workflow/test_mock_registry.md, plan + 3 task specs, 20 memory files (outside git)

rel: amends -> [[bsd-plan1-deploy-runtime-cabce24]]
rel: evidence-for -> [[plan-1-deploy-runtime#q3]]

## Verified (read-only, live 0.68.1) {#verified}

- Deploy: `~/refmatrix` at 6cc33e9 = master; `~/refmatrix/.venv` `.pth` → `/Users/tholley/refmatrix/src`; `rmx version -v` → `code: ~/refmatrix/src/refmatrix/__init__.py`, no `[DEV TREE]`. Daemon pid 73565 and hub pid 73575 relaunched 20:35–20:36 via `rmx daemon restart --relaunch` (cli.log exit 0).
- `rmx hub status` live: hub prints its own `code:` line (#s-4 closed); orderly row renders `[UNVERIFIED v0.65.0]` (#s-3 closed); other 7 rows clean.
- Dev-tree pytest (`.venv-eval`): `tests/test_plan1_remedy.py` + `test_upgrade.py` + `test_runtime_identity_surface.py` + `test_modelsrv.py::test_daemon_falls_back_when_shared_socket_does_not_answer` → 27 passed in 5.9 s (`workflow/review-output/pytest-bsd-plan1-r2-6cc33e9.log`). The modelsrv fallback test that previously hit the 300 s wedge now completes inside that 5.9 s.
- RED/GREEN on file: `pytest-remedy12-RED.log` 19 failed → `pytest-remedy12-GREEN.log` 48 passed.
- Deferral sweep over added lines in hub.py/upgrade.py/daemon.py/modelsrv.py/cli.py: no hard or soft deferrals. No `plan 1` references in `src/`.

### First-round findings — status {#status}

| # | Status | Evidence |
|---|--------|----------|
| #b-1 alert gate | CLOSED | `hub._queue_row_is_hot` includes `dev_tree`; `_queue_alert_loop` uses it (hub.py:559); `test_gather_queues_carries_identity_end_to_end` drives the real `_gather_queues` with only `discovery.*` and `daemon.call` patched and asserts a hot row. Predicate mutation is caught. |
| #b-2 (a) `upgrade()` | CLOSED | `runtime_identity()` is the first statement on every path and raises on `dev_tree` (upgrade.py:227); up-to-date path runs `verify_editable`; tests cover `--check`, changed head, and same-head-wrong-.pth on fake trees. Incident replay on paper: prefix `~/refmatrix/.venv`, import from dev → `dev_tree=True` → raise. |
| #b-2 (b) relaunch guard | **OPEN** → [[#b-1-r2]] | see below |
| #s-3 unknown ≠ clean | CLOSED (live) | `_daemon_identity` → `{unknown, version}`; three-state row; CliRunner test. |
| #s-4 hub's own tree | CLOSED (live) | `_op_hub_info` spreads `_hub_identity()` (cached, never raises); `hub_status` prints `code:`. |
| #s-5 tests bypass wiring / registry | CLOSED | end-to-end gather test; `hub status` CliRunner test; 5 registry rows added (grep confirmed, not summary-read). |
| #s-8 finder-style marker | CLOSED | `editable_target(strict=True)` raises; `verify_editable` uses strict; test. |
| #m-6 memory text / bridge | PENDING (expected) | reworded; 20 files migrated 20:12–20:35 all parse with `doc_id == stem` via the dev-tree `parse_gmd` (dry run, no store). No bridge run since 20:04:08 (cli.log), so `rmx memory get feedback_save_state_means_handoff` still errors — resolves at the next save-state/SessionStart; re-check then. |
| #m-7 ping identity cached | CLOSED | `daemon._process_identity()`; `test_ping_uses_cached_identity` fails if the op calls `runtime_identity` again. |
| #m-9 status before gate | CLOSED | plan `in-progress`; tasks `complete`. |

## Findings {#findings}

### BULLSHIT: `rmx daemon restart --relaunch` cannot fire in the incident state — CLI and daemon share the same bad venv, so their code paths always match {#b-1-r2}

**File:** `src/refmatrix/cli.py:2740-2756` (`_verify_relaunch`), `~/Library/LaunchAgents/com.refmatrix.daemon.*.plist` (`ProgramArguments` = `/Users/tholley/bin/rmx daemon start --no-detach`)
**Claimed:** Q3 decision (b): "`rmx daemon restart --relaunch` compares the new daemon's `code_path` to this CLI's `import_path` and fails loud on mismatch, because ff + relaunch IS the documented deploy path and never enters `upgrade()`." Memory: "`rmx daemon restart --relaunch` fails when the new daemon's code path differs from the CLI's."
**Actual:** the guard only compares `theirs != mine`. Every daemon is launched by launchd through `/Users/tholley/bin/rmx` — the same interpreter and the same `.pth` as the CLI. In the 2026-09-14 state (deploy `.pth` → dev `src/`) the CLI imports the dev tree AND the relaunched daemon imports the dev tree: `mine == theirs`, both `dev_tree=True`, and the command prints `relaunch verified pid a→b version=0.68.1 code=/Users/tholley/claude_tools/refmatrix/src/refmatrix/__init__.py` and exits 0. The ping already carries `dev_tree`; the CLI already has `runtime_identity()["dev_tree"]` in hand (it reads `import_path` from the same dict); neither bit is consulted. Second time in this plan a guard is built for a state other than the incident (first: `verify_editable` on the imported tree's venv).
**Evidence:** scratch replay `workflow/review-output/pytest-bsd-plan1-r2-relaunch-incident.log` — `test_incident_state_both_on_dev_tree_passes_silently`: `runtime_identity` patched to `dev_tree=True` with the dev import path, ping returns the same `code_path` + `dev_tree=True`; result exit 0, output contains `relaunch verified`. The shipped test (`test_daemon_restart_relaunch_fails_on_code_path_mismatch`) only exercises a path mismatch, which is not the incident.
**Fix (3 lines):** in `_verify_relaunch`, after computing `ident = _up.runtime_identity()`: raise `ClickException` if `ident["dev_tree"]`; raise if the ping result's `dev_tree` is true; keep the path comparison as the third check. Add the incident-state test above to `tests/test_plan1_remedy.py` with the assertion inverted. Reword the memory sentence to "fails when either side runs a dev tree or the paths differ".
**Pattern match:** YES — [[bsd-impressions#imp-guard-vs-incident-state]] (2nd occurrence, same plan). Cheap-fix shape per rule 10: the correct check was one extra key read from a dict already in scope.

rel: contradicts -> [[plan-1-deploy-runtime#q3]]

### SKETCHY: the relaunch code-path check passes on "could not read" {#s-2-r2}

**File:** `src/refmatrix/cli.py:2746-2750`
**What:** `try: r = daemon_mod.call(root, "ping", …) except Exception: theirs = None`, then `if theirs and theirs != mine: raise` — a ping that raises, times out, or returns without `code_path` yields `theirs=None` and the command prints `relaunch verified pid a→b version=X` (no `code=`) and exits 0. This is exactly the shape #s-8 closed in `editable_target(strict=True)` one commit earlier: a verify step that treats "unreadable" as "verified". `served_identity` succeeded a moment before, so the only ways here are a transient socket error or a daemon that answers the version but not the field; both should be loud, not green.
**Evidence:** `test_ping_exception_during_code_path_check_passes_silently` in the same scratch log: `daemon.call` raises `OSError`; exit 0; output has `relaunch verified` and no `code=`.
**Fix:** on exception or missing `code_path`, raise `ClickException("relaunched daemon did not report its code path — cannot verify the tree; run `rmx daemon status`")`. One retry is fine; a silent pass is not.

rel: contradicts -> [[bsd-plan1-deploy-runtime-cabce24#s-8]]

### MEH: no test asserts a `global:queues` publish for a `dev_tree` row {#m-3-r2}

**File:** `src/refmatrix/hub.py:556-570` (`_queue_alert_loop`), `tests/`
**What:** the predicate was extracted and tested, and the gather wiring is tested end to end, but nothing references `_queue_alert_loop` or asserts `bus.publish` (grep of `tests/` for either: empty). Reverting the loop to the old inline predicate passes every test. Single call site, verified by reading, so MEH — but the first-round fix asked for the publish assertion, and the loop is the thing that actually alerts.
**Fix:** factor the loop body into `_queue_alert_once(self) -> bool` and test it with a fake bus.

### MEH: `identity: unknown` rows stay off the alert; task 4.4 still lacks the code-path criterion {#m-4-r2}

**File:** `src/refmatrix/hub.py:940-950` (`_queue_row_is_hot` ignores `identity == "unknown"`), `workflow/plans/plan-4-daemon-resilience-tasks/task-4.4-plan-4-daemon-resilience.md`
**What:** orderly is still served by the unsupervised pid 39128 at 0.65.0 (direct ping in this audit); its launchd service is in `spawn scheduled / last exit code = 1`. `hub status` now says `[UNVERIFIED v0.65.0]` (good), but the queue row is not hot, so the alert channel is silent about a daemon the fleet cannot identify. First round asked for "orderly reports `code_path` under `~/refmatrix/src`" as a 4.4 acceptance criterion; the spec is unchanged. Carry-over, not re-escalated: nothing in the summary claims otherwise.
**Fix:** `or q.get("identity") == "unknown"` in `_queue_row_is_hot`; add the criterion to task 4.4.

### MEH: memory-dir lint is not clean; migrated memories unverified in the store until the next bridge run {#m-5-r2}

**File:** `~/.claude/projects/-Users-tholley-claude-tools-refmatrix/memory/` (`feedback_mcp_first_agent_stm.md:35,48`, `project_memory_compile_design.md:22`, `project_memory_compile_shipped.md:22`, `project_phase_b_intuition_memory.md:96`, `project_phase_c_shipped.md:93`)
**What:** `python3 tools/gmd/lint.py <memory dir>` → 209 files, 6 errors: dangling `[[adr-0002-subject-memory-container]]` / `[[0001-intuition-lance-integration]]` wikilinks to ADR ids the memory dir cannot see. Task 1.3 says "memories linted". These are cross-tree references the lint scope does not include, so it is a scope/lint-invocation gap, not broken files. Separately, the 20 migrated files (`tools/gmd/migrate_memory.py`, already in git since 435df29) parse cleanly in the dev-tree parser with `doc_id == stem`, but no bridge has run since they were written; `rmx memory get feedback_save_state_means_handoff` still returns "no memory matching". Expected, not a defect — verify at the next SessionStart/save-state and record the result in the round-3 report.
**Fix:** lint the memory dir together with `docs/adr` (or use `lint --scope`), or repoint the four links to `[[adr-0002…]]` ids that exist; confirm the bridge after it runs.

## Also reviewed {#also}

- `modelsrv.SharedWorkerClient.info(timeout=)` / `call(timeout=)`: `TimeoutError` is re-raised after `close()` instead of falling into the reconnect-and-retry branch (which reconnected with the 300 s default); the daemon adoption probe passes `PROBE_TIMEOUT_S` (env `RMX_SHARED_PROBE_TIMEOUT_S`, 5 s). Read-verified and the fallback test runs in seconds. No finding.
- `daemon._process_identity` fallback carries `identity_error` so a broken identity is visible, not swallowed. No finding.

## Verdict {#verdict}

**DIRTY — 5 findings (1 BULLSHIT, 1 SKETCHY, 3 MEH).**

Seven of nine first-round findings are closed and three of the surfaces are proven live (hub `code:` line, `[UNVERIFIED v0.65.0]`, upgrade identity-first). What remains open is one half of #b-2: the documented deploy path (`git pull --ff-only` + `rmx daemon restart --relaunch`) still has no machine guard for the incident state, because the check compares two processes that share the same venv. Fixing it is a two-key read from dicts the code already holds. Plan 1 stays `in-progress` until [[#b-1-r2]] and [[#s-2-r2]] land with the incident-state test; the three MEHs can ride the same commit.

rel: contradicts -> [[plan-1-deploy-runtime#q3]]
