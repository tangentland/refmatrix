---
gmd: "0.1"
id: bsd-plan1-deploy-runtime-cabce24
title: "plan-1-deploy-runtime: the fleet is on the deploy tree, but the alert never fires and the upgrade guard cannot run in the incident state"
tags: [bsd, findings, plan-1, deploy]
severity: BULLSHIT
plan: plan-1-deploy-runtime
task: task-1.1-plan-1-deploy-runtime, task-1.2-plan-1-deploy-runtime, task-1.3-plan-1-deploy-runtime
metadata:
  node_type: bsd-report
  commit_range: cf4da79..cabce24
---

# ch-bsd findings — plan-1-deploy-runtime (cf4da79..cabce24) {#root}

**Commits:** 99b8440 (0.66.3 code), 8aa4cfb (merge tasks 1.1/1.2), cabce24 (task 1.3 ops + docs)
**Date:** 2026-09-14
**Author:** Todd Holley / Fable 5.1 / orchestrator
**Files changed:** 20 (+439/-16)

rel: evidence-for -> [[plan-1-deploy-runtime]]
rel: amends -> [[bsd-0661-e2e-memory-bridge]]

## What is verified live (read-only) {#verified}

- `~/refmatrix/.venv` editable marker = `/Users/tholley/refmatrix/src`; `refmatrix.__file__` under `~/refmatrix/src`, version 0.66.3, `sys.prefix` = `~/refmatrix/.venv`.
- `rmx version -v` prints `code: /Users/tholley/refmatrix/src/refmatrix/__init__.py`, venv tree `~/refmatrix`, no `[DEV TREE]`.
- `rmx daemon status` prints the DAEMON's `code:` line from its ping (pid 48422, deploy path).
- Direct ping of all 8 registered roots: 7 daemons report `version=0.66.3`, `code_path` under `~/refmatrix/src`, `dev_tree=False`. The 8th (orderly, pid 39128, unsupervised) reports `version=0.65.0` with no `code_path` at all.
- Hub pid 48432 started 19:41:10 via `~/bin/rmx` (deploy venv). Its own import path is not observable from any surface (finding #s-4).
- `.claude/commands/{save-state,commit-state}.md` are byte-identical to the shipped templates; neither contains `pip install -e /Users`.
- Dev-tree pytest (`.venv-eval`) on the three touched test files: 36 passed (`workflow/review-output/pytest-bsd-plan1-cabce24.log`). RED log shows 11 real failures before implementation; GREEN 16 passed; t1.2 20 passed.
- The environment half of #bs-2 is closed. What follows is about the code that is supposed to stop it recurring.

## Findings {#findings}

### BULLSHIT: the `global:queues` alert never fires on `dev_tree` — the annotation rides a gate that ignores it {#b-1}

**File:** `src/refmatrix/hub.py:556-568` (`_queue_alert_loop`), `src/refmatrix/hub.py:544` (`_gather_queues` → `_annotate_identity`)
**Claimed:** Plan Q2 decision: "Alert (hub `queues` channel + red status line)". Summary 1.1: "`hub._annotate_identity` stamps `dev_tree`/`code_path` on queue rows so the `global:queues` alert carries it." New memory `feedback_deploy_tree_is_the_runtime`: "the `global:queues` alert carries `dev_tree` per root."
**Actual:** `_gather_queues` does call `_annotate_identity`, but `_queue_alert_loop` publishes only when `hot or pending_refine`, and `hot` is `stale_files > 0 or memory_read_ok is False or serving_legacy_catalog or store_bytes`. `dev_tree` is not in the predicate. A fleet where every daemon runs the wrong tree and nothing is stale publishes nothing. The identity only appears as a passenger on an alert raised for some other reason, once per 1800 s.
**Evidence:** `grep -n dev_tree src/refmatrix/hub.py` → lines 939, 950, 954, 962 only; none inside the alert loop. Mutation A (`return _annotate_identity(out)` → `return out` on a scratchpad copy): `tests/test_runtime_identity_surface.py` 5/5 still pass (`workflow/review-output/pytest-bsd-plan1-mutA.log`) — nothing tests the wiring or the publish.
**Fix:** add `or q.get("dev_tree")` to `hot`; add a test that feeds a `dev_tree=True` row through the loop body (extract the `hot` predicate into a function) and asserts a publish. Correct the memory sentence once landed.
**Pattern match:** YES — [[bsd-impressions#imp-two-paths]] ("which path does production take") and [[bsd-impressions#imp-mock-the-sut]].

rel: contradicts -> [[plan-1-deploy-runtime#q2]]

### BULLSHIT: `upgrade()` verification is skippable on exactly the paths the incident presents {#b-2}

**File:** `src/refmatrix/upgrade.py:205-215` (early returns), `:243-248` (verify), `:44-54` (`package_root`), `:139-158` (`verify_editable`)
**Claimed:** Summary 1.2 / lead brief: "`verify_editable()` runs INSIDE `upgrade.upgrade()` after any install_fn (not injectable)." Memory: "`rmx upgrade --from-dev` now refuses to finish when the editable target is another tree." Task 1.2 spec: "after `pip install -e {root}` call `runtime_identity()`; if `dev_tree` → raise."
**Actual:** three ways past the guard, two of which are the 2026-09-14 state:
1. `if target_head == old_head: return` — "already up to date" exits before install and before verify. On 2026-09-14 `~/refmatrix` WAS at the same sha as master; the bad `.pth` was the whole problem. `rmx upgrade --from-dev` in that state prints "already up to date" and verifies nothing.
2. `package_root()` resolves the root from `refmatrix.__file__`. In the incident state the deploy binary imports the dev tree, so `root` = the dev tree; `verify_editable(dev)` looks for `dev/.venv`, which does not exist (the dev venv is `.venv-eval`), and returns `None` = pass. The check inspects the venv of the tree the code came from, not the venv of the interpreter that is running — the precise confusion the incident was. The spec'd `runtime_identity()` (prefix vs import path) would have said `dev_tree=True`; the implementation substituted a `.pth`-under-`root/.venv` check that cannot.
3. `--check` returns before verify (acceptable for a dry-run, listed for completeness).
Also: the deploy procedure the templates and memory now teach (`git pull --ff-only` + `rmx daemon restart --relaunch`) never enters `upgrade()`, so `verify_editable` is not on the documented deploy path at all; the only guard there is a human reading `rmx version -v`. `daemon restart --relaunch` itself verifies pid + version only (`cli.py:2707-2725`, `daemon.served_identity`), not `code_path`.
**Evidence:** code above; `tests/test_upgrade.py::test_upgrade_from_dev_verifies_editable_after_install` only exercises the changed-head path (mutation D confirms it covers that path: `pytest-bsd-plan1-mutD.log`, 1 failed).
**Fix:** (a) call `runtime_identity()` first thing in `upgrade()` and raise `UpgradeError` when `dev_tree` is True — before git, on every path including `--check` and "already up to date"; (b) run `verify_editable(root)` on the up-to-date path too; (c) make `daemon restart --relaunch` compare `code_path` from the ping against `runtime_identity()["import_path"]` of the CLI and fail loud on mismatch, so the documented deploy path has a machine guard. Tests for each path on the fake trees already in `test_upgrade.py`.
**Pattern match:** YES — cheap-fix shape: spec named `runtime_identity()`, implementation shipped a narrower check that passes the incident state.

rel: contradicts -> [[task-1.2-plan-1-deploy-runtime#files]]

### SKETCHY: `rmx hub status` renders "cannot tell" as clean; one fleet member is in that state right now {#s-3}

**File:** `src/refmatrix/hub.py:938-950` (`_daemon_identity`), `src/refmatrix/cli.py:2427-2430` (`hub_status`)
**Claimed:** Task 1.3 requirement "verify every fleet daemon reports the deploy path"; summary: "`rmx hub status` shows 0 DEV TREE flags."
**Actual:** `_daemon_identity` returns `{}` on exception, on `ok=False`, and on a ping without `code_path` (any pre-0.66.3 daemon). `hub_status` prints a flag only when `dev_tree` is truthy, so unknown and verified-clean are the same green row. Live: orderly's daemon (pid 39128, since Sep 13 01:00) answers `version=0.65.0`, no `code_path` — shown as a plain row. The summary discloses orderly and defers it to plan 4.4; task 4.4's acceptance criteria are about adopting an unsupervised daemon and never mention the code path (it is covered only implicitly, by the respawn). "0 flags" is therefore not evidence for the whole fleet.
**Evidence:** direct ping output in this audit; `hub status` output above. Mutation B (drop `{devflag}` from `hub_status`): all tests pass (`pytest-bsd-plan1-mutB.log`) — the `hub status` surface has no test.
**Fix:** distinguish three states in the row: `code: <path>`, `[DEV TREE]`, and `[UNVERIFIED v0.65.0]` (or `identity: unknown` in the queue row); add a CliRunner test for `hub status` with `hub_mod.status`, `rpc`, and `_daemon_identity` patched as inputs. Add "orderly reports `code_path` under `~/refmatrix/src`" to task 4.4's requirements.
**Pattern match:** YES — [[bsd-impressions#imp-silent-memory]] (silent-skip rendered as success).

rel: contradicts -> [[task-1.3-plan-1-deploy-runtime#requirements]]

### SKETCHY: the hub does not say which tree the hub runs {#s-4}

**File:** `src/refmatrix/hub.py` (`_op_hub_info`), `src/refmatrix/cli.py:2405-2415` (`hub_status`)
**Claimed:** Plan title: "`rmx`, daemons, and hub execute the deploy tree, and say so."
**Actual:** `hub_info` returns `pid, port, home, watch_interval_s, registry_size`. No `code_path`, no `dev_tree`, no version. `rmx hub status` prints per-daemon flags only. The hub process (pid 48432) was launched from `~/bin/rmx`, so it is almost certainly on the deploy tree today, but no surface can show it, and the hub is the process that supervises everything else.
**Evidence:** `sed -n '/def _op_hub_info/,/def /p' src/refmatrix/hub.py`.
**Fix:** add `version`, `code_path`, `dev_tree` (from `runtime_identity()`) to `_op_hub_info`; print a `code:` line for the hub in `hub_status` via `_print_code_identity`.

### SKETCHY: surface tests bypass the wiring they are cited for; mocks unregistered despite the summary saying otherwise {#s-5}

**File:** `tests/test_runtime_identity_surface.py:57-62`, `workflow/test_mock_registry.md`, `workflow/implementation_summaries/task-1.1-plan-1-deploy-runtime.md` (TDD record)
**Claimed:** Summary 1.1: "surface tests patch [`runtime_identity`] as an external input to the CLI, registered in the mock registry."
**Actual:** `test_hub_queue_rows_carry_dev_tree` monkeypatches `_daemon_identity` and calls `_annotate_identity` directly — it proves a dict copy, not that `_gather_queues` or the alert carry anything (mutation A). No test covers `hub status`. The mock registry has no plan-1 rows; its only catch-all is "monkeypatch.setattr sites (184, unregistered) — plan 6 sweep". The identity tests themselves (`test_upgrade.py`, fake trees + injected prefix/import_file) are honest and do not mock the SUT; `_op_ping` and `daemon status` tests patch `runtime_identity`/`daemon_mod.call` as inputs, which is acceptable.
**Evidence:** `grep -n -iE "runtime_identity|_daemon_identity|plan-1" workflow/test_mock_registry.md` → empty; mutation logs A and B.
**Fix:** test `_gather_queues` end-to-end with `discovery.discover_roots`/`daemon_status` and `daemon_mod.call` patched as inputs; CliRunner test for `hub status`; register the three monkeypatch sites (`up.runtime_identity`, `daemon_mod.call`, `hub._daemon_identity`) as `external`/`internal-active` with a graduation note. Correct the summary.
**Pattern match:** YES — [[bsd-impressions#imp-mock-the-sut]], second run in a row → escalated MEH→SKETCHY.

rel: contradicts -> [[bsd-impressions#imp-mock-the-sut]]

### SKETCHY: `verify_editable` passes silently on a finder-style editable install (unanchored deferral) {#s-8}

**File:** `src/refmatrix/upgrade.py:78-92` (`editable_target` docstring: "None when no editable marker exists (wheel install, or a finder-style marker that carries no path)"), `:139-158` (`verify_editable`: "None when the venv carries no editable marker (nothing to verify)")
**What:** pip/setuptools emit a finder-style marker (`__editable___refmatrix_<v>_finder.py` + a `.pth` containing only `import ...`) whenever the layout is not "simple". `editable_target` skips `import` lines and returns `None`; `verify_editable` treats `None` as nothing to verify and returns success. A finder-style install pointing at the wrong tree passes the guard. This project's src layout produces the path-style marker today, so there is no live impact; no task spec covers the gap, so it is an unanchored deferral by rule 9a (kept at SKETCHY only because the layout that triggers it is not this project's).
**Fix:** when a `__editable__.refmatrix*.pth` exists but yields no path, raise `UpgradeError("editable marker present but target unreadable")` instead of returning `None` — fail loud, two lines.

### MEH: memory text overstates what shipped, and two amended memories cannot reach the store {#m-6}

**File:** `~/.claude/projects/-Users-tholley-claude-tools-refmatrix/memory/feedback_deploy_tree_is_the_runtime.md:24-29`, `feedback_save_state_means_handoff.md`, `feedback_refmatrix_dev_deploy_split.md`, `MEMORY.md:66`
**What:** The new memory states the alert carries `dev_tree` (#b-1) and that `rmx upgrade --from-dev` refuses a foreign target (#b-2, only on a changed head). Keeping the three superseded/amended memories with back-edges instead of deleting them is per MEMORY-RULES (new file + edge over destructive overwrite) and is fine; the `superseded-by`/`amended-by` verbs only warn. But `feedback_save_state_means_handoff.md` and `feedback_refmatrix_dev_deploy_split.md` have no `gmd:`/`id:` frontmatter, and per #bs-1 the bridge drops non-GMD files silently — `rmx memory get` finds neither, so the rewritten step 4 exists only on disk. `feedback_deploy_tree_is_the_runtime` is also absent from the store, but the last bridge run (`cli.log` 19:06:51) predates the file; that resolves at the next save-state. `MEMORY.md:66` still indexes the superseded memory with an unqualified hook.
**Fix:** reword the two sentences after #b-1/#b-2 land; add GMD frontmatter (`gmd`, `id` = stem, `title`, `tags`, `{#root}`) to the two legacy files so the bridge takes them (or fold into plan 3); mark the superseded index line.

### MEH: the health probe now depends on site-packages globbing on every ping {#m-7}

**File:** `src/refmatrix/daemon.py:2412-2424` (`_op_ping`)
**What:** `runtime_identity()` runs on every ping: `sys.prefix` resolve, a `pyproject.toml` stat, `glob("lib/python*/site-packages")`, `glob("__editable__.refmatrix*.pth")`, `read_text`. The hub watchdog pings every daemon every interval, and `ping()` returns False on any `ok=False` — an exception inside the op would make a healthy daemon look dead to the watchdog. Identity cannot change within a process.
**Fix:** compute once at import (`_IDENTITY = runtime_identity()` guarded by try/except that records the error string) and return the cached dict from `_op_ping`.

### MEH: plan marked `completed` before the ch-bsd gate ran {#m-9}

**File:** `workflow/plans/plan-1-deploy-runtime.md:8` (`status: completed`, set in cabce24), `workflow/plan-of-plans.md:21`
**What:** The plan's own execution contract says "`@ch-bsd` over the plan's commit range — remedy and re-review until the verdict is CLEAN; then the plan's `metadata.status` → `completed`." `INDEX.md` shows no ch-bsd run on cf4da79..cabce24 before this one; the status flip and the audit request came in that order. Also minor: the three task specs still carry `status: pending` while the plan says completed.
**Fix:** revert the plan to `approved` (or `in-review`) until #b-1/#b-2 are closed and a CLEAN verdict is on file; set task statuses.

## Deferral sweep {#deferrals}

No hard deferrals in the diff. Soft hits (docstring caveats) at `hub.py:940` ("best-effort … contributes nothing" → #s-3) and `upgrade.py:81,143` ("carries no path", "nothing to verify" → #s-8). No stale references to plan 1 in `src/`.

## Verdict {#verdict}

**DIRTY — 9 findings (2 BULLSHIT, 4 SKETCHY, 3 MEH).**

The operational remediation for #bs-2 is real and verified: the deploy venv imports `~/refmatrix/src`, seven of eight daemons run 0.66.3 from the deploy path, `rmx version -v` and `rmx daemon status` show the truth. What is not real yet is the recurrence guard: the alert channel cannot raise the flag (#b-1), and the upgrade check cannot fire in the state that caused the incident (#b-2). Plan 1 should not be marked `completed` until #b-1 and #b-2 are closed; #s-3/#s-4/#s-5 can ride the same fix commit.

rel: contradicts -> [[plan-1-deploy-runtime#execution]]
