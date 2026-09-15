---
gmd: "0.1"
id: bsd-plan1-deploy-runtime-r5-7b35e80
title: "plan-1 round 5: identity_error crosses the wire and every r4 finding is closed for real; residue is bookkeeping — a third unregistered-mock strike and a bug-008 deferral parked on a task that does not cover it"
tags: [bsd, findings, plan-1, deploy, re-review]
severity: BULLSHIT
plan: plan-1-deploy-runtime
task: task-1.1-plan-1-deploy-runtime, task-1.2-plan-1-deploy-runtime, task-1.3-plan-1-deploy-runtime
metadata:
  node_type: bsd-report
  commit_range: 54fceb9..7b35e80 (2b486ef), read at HEAD 191e510
  round: 5
---

# ch-bsd findings — plan-1-deploy-runtime round 5 (2b486ef / merge 7b35e80) {#root}

**Commits:** 2b486ef (fix(identity): identity_error crosses the ping wire; hub status renders its own; hub queues fails loud on a busy fleet), 7b35e80 (merge remedy-plan-1-r4). Read at HEAD 191e510, after 80021a4 (plan-3 r2) moved `verbs.queues` onto `_hub_rpc`.
**Date:** 2026-09-14
**Author:** Todd Holley / Fable 5.1 / orchestrator
**Files changed:** 11 (cli.py, daemon.py, hub.py, verbs.py, tests/test_plan1_remedy.py, tests/test_bigop_nonblocking.py, bug_registry, deferral_registry, remedy summary, plan-of-plans, plan-1)

rel: amends -> [[bsd-plan1-deploy-runtime-r4-54fceb9]]
rel: evidence-for -> [[plan-1-deploy-runtime#q3]]

## Verified {#verified}

- **#b-1-r4 producer → wire → consumers:** CLOSED. `daemon._op_ping` (daemon.py:2591-2592) copies `identity_error` from `_process_identity()` onto the response. `test_real_ping_carries_identity_error_and_every_consumer_sees_unknown` starts at `upgrade.runtime_identity` raising, resets `_PROCESS_IDENTITY`, calls the REAL `_op_ping` on a `Daemon`, and feeds that exact dict to `_daemon_identity` and the relaunch guard. My own mutation on a scratch copy (forward deleted from `_op_ping`) fails the test at its first assertion (`workflow/review-output/pytest-bsd-plan1-r5-mutation-7b35e80.log`). Hub's own line: `_op_hub_info` spreads `**_hub_identity()` (hub.py:375), `hub.status()` does `info.update(r["result"])` with no key filter (hub.py:1076), and `cli.hub_status` now renders `st["identity_error"]` as `[UNVERIFIED] — hub could not compute its identity: …` (cli.py:2494-2498); `test_hub_status_flags_the_hubs_own_identity_error` asserts both strings.
- **#s-2-r4 busy fleet:** CLOSED. `verbs.queues` is `_hub_rpc("queues")` (verbs.py:880-881) and `_hub_rpc` converts `TimeoutError`/`socket.timeout`/`OSError` and `ok:false` into a typed `VerbError` (verbs.py:1050-1069); `cli.hub_queues` prints it as a ClickException. `_gather_queues` marks a root whose 10 s stats call failed as `identity: unknown` + `identity_error` and `_annotate_identity` skips the 2 s ping for it (hub.py:566-572, 1034). Mutation (skip removed) fails `test_gather_queues_skips_the_identity_ping_when_the_status_call_failed` with `['stats', 'ping']`. Live: `hub queues` at 22:16:24 on a just-relaunched fleet took 21.4 s and exited 0; 22:19:41 took 1.6 s; the 21:43:07 30 s traceback was the last one (`.refmatrix/cli.log`).
- **#m-3-r4 status agreement:** CLOSED. `workflow/plans/plan-1-deploy-runtime.md:8` and `workflow/plan-of-plans.md:21` both say `in-progress`.
- **#m-4-r4 RED record:** CLOSED. `pytest-plan1-r3-red-all5.log`: all five r3 tests selected against c9d75af, 3 failed / 2 passed, matching the summary's account. Round-4 RED (`pytest-plan1-r4-red.log`, 4 failed) and GREEN (94 passed) present.
- **bug-008 live state:** `~/.claude/hooks/rmxgrep-rewrite.py` (mtime 21:52) carries `RMXGREP = "/Users/tholley/refmatrix/bin/rmxgrep"` / `RMXRG = "/Users/tholley/refmatrix/bin/rmxrg"` — the deploy render. `~/bin/rmx install-hooks --check` → hooks in sync; `tests/test_repo_hooks_in_sync.py` green in my run.
- **Deploy / fleet (read-only, `~/bin/rmx`):** `~/refmatrix` at 0036d80 (191e510 differs by `handoff.md` only, so the runtime is that of the brief); `~/refmatrix/.venv` imports `/Users/tholley/refmatrix/src/refmatrix/__init__.py` 0.69.1; `rmx version -v` no `[DEV TREE]`. Hub pid 38024 started 22:15:55 on 0.69.1; `hub status` shows 8 stores up, deploy code path, no UNVERIFIED row (orderly adopted at 0.69.1 under plan 4.4). `hub queues --json`: all 8 rows `dev_tree: false`, deploy `code_path`, no `identity_error`. `daemon status` (refmatrix, pid 30867, started 22:02:12) prints the deploy `code:` line, supervised.
- **Tests (dev tree, `.venv-eval`, `--timeout=300`):** `test_plan1_remedy.py` + `test_runtime_identity_surface.py` + `test_upgrade.py` + `test_bigop_nonblocking.py` + `test_verb_parity.py` + `test_repo_hooks_in_sync.py` → 89 passed in 1.89 s (`workflow/review-output/pytest-bsd-plan1-r5-7b35e80.log`). Parity gate (E2E surface for this project) green.
- **Deferral sweep over the added `src/` lines of 2b486ef:** no hard or soft deferral phrases. Hard sweep of `src/refmatrix` for plan-1 references: none. The one new deferral in the diff is in `workflow/deferral_registry.md` ([[#b-2-r5]]).

### Round-4 findings — status {#status}

| # | Status | Evidence |
|---|--------|----------|
| #b-1-r4 `identity_error` dropped by the producer; hub's own unread | CLOSED | producer-side test through the real `_op_ping`; mutation fails it; `hub_status` renders the hub's own error |
| #s-2-r4 `hub queues` traceback on a busy fleet | CLOSED | typed VerbError at the one hub boundary; per-root cap; live 21.4 s run succeeded on a restarting fleet |
| #m-3-r4 plan-of-plans vs plan file | CLOSED | both `in-progress` |
| #m-4-r4 RED covered 4 of 5 | CLOSED | all-five RED log at the pre-remedy commit |

## Findings {#findings}

### BULLSHIT: third unregistered-mock strike in plan 1 — `hub.status`, `hub.rpc`/`is_running`, and the `discovery.*` patches in the new tests have no row naming `tests/test_plan1_remedy.py` {#b-1-r5}

**File:** `tests/test_plan1_remedy.py:333-341` (`hub_mod.status` lambda — not in the registry under any name), `:343-355` (`hub_mod.is_running` / `hub_mod.rpc` fakes — registry row for `hub.rpc`/`hub.is_running` at `workflow/test_mock_registry.md:36` names only `test_mcp_bus_passthrough.py` and `test_mcp_channels.py`), `:357-376` (`discovery.discover_roots` / `daemon_status` / `store_name` — rows 38 and 41 name `test_verbs_migrated.py` and `test_plan2_remedy.py`; row 30 mentions the discovery patch only inside a graduation note)
**What:** the commit adds four tests and three new mock shapes; `workflow/test_mock_registry.md` was not touched. The summary's Round 4 table does not claim registration this time, so this is an omission, not a false claim.
**Why it's bullshit:** the mocks are legitimate (process boundaries, CLI-surface tests), so on its own this is SKETCHY. It is the third registry omission in plan 1 (r1: surface-test mocks; r3: FakeBus/FakeHub; r5: these) and the escalation rule was armed in writing after r3 ([[bsd-impressions#imp-registry-2-strikes]]): SKETCHY seen 3+ times → BULLSHIT. The rule exists because a registry nobody updates stops being the mock inventory CLAUDE.md `#no-mocks` relies on.
**Evidence:** `grep -n "test_plan1_remedy\|hub.status" workflow/test_mock_registry.md` → rows 28, 29, 30, 33, 34 only; no row contains `hub.status`; rows 36/38/41 do not list `test_plan1_remedy.py`.
**Fix:** three edits to `workflow/test_mock_registry.md`: a new row for `hub.status` (fake dict; the hub process; external; permanent for the render test, real path = `_op_hub_info` → `status()` covered by live `rmx hub status`); add `tests/test_plan1_remedy.py` to the `hub.rpc`/`hub.is_running` row and to the `discovery.daemon_status`/`discover_roots` rows. Effort: five minutes. No code change.
**Pattern match:** YES — [[bsd-impressions#imp-registry-2-strikes]], [[bsd-impressions#imp-summary-claims-bookkeeping]].

rel: contradicts -> [[claude#no-mocks]]

### BULLSHIT: bug-008's durable fix is deferred to "plan 6 task 6.4 (or a new 6.5)" — task 6.4 does not cover it and 6.5 does not exist (unanchored deferral, rule 9a) {#b-2-r5}

**File:** `workflow/deferral_registry.md:37` (new row in this diff), `workflow/bug_registry.md:51` (bug-008, `recurring`, Seen 2), `src/refmatrix/search_hooks.py` `render_scripts` (bakes `RMXGREP =` / `RMXRG =` absolute paths of the GENERATOR's tree into the user-global `~/.claude/hooks/rmxgrep-rewrite.py`)
**What:** the remedy found the live rewriter hook overwritten with dev-tree paths for the second time today (21:43), regenerated it from the deploy build, and deferred the durable fix ("resolve the wrappers at runtime from the tree of the `rmx` on PATH; `install_search_hooks` refuses to write the user-global dir from a tree that is not the one `~/bin/rmx` runs") to "plan 6 task 6.4 (or a new 6.5)".
**Why it's bullshit:** `workflow/plans/plan-6-deferrals-docs-benchmark-tasks/task-6.4-*.md` is "Loud verbs.py partition detect, perma-red test, mock registry" — its requirements and files name `verbs.py:148`, `test_graph_landing.py`, the mock and bug registries, and nothing about `search_hooks.py`, the rewriter, or the user-global hooks dir. No task under `plan-6-*-tasks/` mentions `hook`, `rewriter`, or `bug-008`. "Or a new 6.5" is the parking-lot clause rule 9a names: an open plan with no task for the deferred item. The gap it defers is plan 1's own shape — a deployed artifact executing dev-tree paths — and it has recurred twice in one day; the row's "tripwire" (`install-hooks --check`) fired only because a test happened to run. The "cheap fix" test also applies: the shipped remedy is regenerate-by-hand, twice.
**Evidence:** `grep -rn -i "hook\|rewriter\|bug-008" workflow/plans/plan-6*.md workflow/plans/plan-6*-tasks/*.md` → only task 6.2's README hooks-table lines; task 6.4 spec quoted above (status `pending`, plan `approved`).
**Fix:** one of: (a) write `task-6.5-plan-6-deferrals-docs-benchmark.md` with acceptance criteria — the rendered rewriter resolves `rmxgrep`/`rmxrg` at runtime from the `rmx` on PATH (or `~/bin/rmx`'s tree), `install_search_hooks` refuses the user-global dir when `runtime_identity()["dev_tree"]` is true or the venv tree is not `~/refmatrix`, and a RED test that applies from a dev-tree identity and asserts the live hook is untouched — then point the deferral row and bug-008 at that task and add it to plan 6's task table; or (b) build it now (the refusal is ~10 lines in `install_search_hooks` and closes the recurrence even before the runtime-resolve half). Effort for (a): one task spec.
**Pattern match:** YES — [[bsd-impressions#imp-two-paths]] (a user-global script that carries one tree's paths while `rmx` on PATH is another), [[bsd-impressions#imp-guard-vs-incident-state]]; rule 9a (unanchored deferral) in the ch-bsd definition.

rel: contradicts -> [[claude#no-workarounds]]

### MEH: `cli.hub_queues` keeps an `except (TimeoutError, OSError)` clause that nothing can reach {#m-3-r5}

**File:** `src/refmatrix/cli.py:2536-2539`
**What:** 2b486ef added the clause when `verbs.queues` still called `hub_mod.rpc` directly. 80021a4 (merged in the same range) moved `queues` onto `_hub_rpc`, which converts every `TimeoutError`/`socket.timeout`/`OSError` into `VerbError` and whose `is_running()` gate swallows its own exceptions. The only remaining path into the clause would be `_root()`, which raises neither.
**Why it matters:** dead branch in the CLI twin; the next reader assumes the CLI still owns the timeout wording when the verb does. Not a runtime defect — `test_hub_queues_reports_a_busy_fleet_instead_of_a_traceback` passes through the `VerbError` arm.
**Fix:** delete the four lines (the verb's message already names the busy daemon).
**Pattern match:** NO.

## Plan status {#plan-status}

Every round-4 finding is closed and each closure was reproduced (producer mutation, gather-queues mutation, live fleet on 0.69.1, all-five RED log). The two BULLSHIT findings are bookkeeping: registry rows and a task spec. **Plan 1 may flip to `completed` in the commit that adds the three registry rows ([[#b-1-r5]]) and anchors the bug-008 deferral to a concrete plan-6 task spec with acceptance criteria ([[#b-2-r5]]).** Flip both `workflow/plans/plan-1-deploy-runtime.md` and `workflow/plan-of-plans.md` in that commit; no further source change is required for closure ([[#m-3-r5]] can ride along).

## Also reviewed {#also}

- `_gather_queues` fleet sum: 8 roots × (0.5 s × 3 ping + 10 s stats) can still exceed the 30 s rpc if three or more daemons stall on stats; the difference from r4 is that the CLI and MCP twins now fail loud with the busy-daemon wording instead of a traceback, and the 12 s per-root worst case is 10 s. Accepted as the finding's "and/or".
- `hub status` CLI still pings each up daemon for identity (2 s, retries=1) after the health rpc — up to ~32 s on a fully busy fleet, rendered as `[UNVERIFIED]` per row, never a traceback. Pre-existing, not a finding.
- `hub.status()` swallows the `hub_info` rpc failure (`except Exception: pass`, hub.py:1077-1078); the CLI then prints `hub running` with `pid=None port=None`. Pre-existing, not on a memory path; noted for plan 6.1's stale-deferral sweep, not filed.
- The brief's deploy sha (191e510) is one docs commit ahead of the deploy tree (0036d80, `handoff.md` only). Runtime identical; record it as 0036d80 in the handoff.
- Commits 23549ae / 0036d80 / 190a9d1 in the merge range are plan-4 scope and were not audited here beyond the `test_bigop_nonblocking.py` kwarg fix (a stub signature catching up with `_restart(root, alive=…)`; the test still exercises the pause gate).
- Known out-of-scope red `test_graph_landing.py::test_context_op_honors_partition_under_ambient_drift` was not run, per the brief.

## Verdict {#verdict}

**DIRTY — 3 findings (2 BULLSHIT, 1 MEH). Blockers: [[#b-1-r5]], [[#b-2-r5]] — both closable without a source change.**

The substance of plan 1 is done: the identity field crosses the socket, every consumer renders the fallback as unverified, the busy-fleet path is loud and typed, and the live fleet at 0.69.1 reports the deploy tree on all 8 stores. What remains is the ledger discipline the plan itself keeps tripping on — three registry omissions in five rounds, and a recurrence of the plan's own incident shape (dev-tree paths in a deployed artifact) parked on a task that does not mention it. Add the rows, write task 6.5, flip the plan.

rel: contradicts -> [[claude#no-mocks]]
rel: contradicts -> [[deferral_registry]]
