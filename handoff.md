---
gmd: "0.1"
id: handoff
title: "Session Handoff for refmatrix"
tags: [handoff, session]
metadata:
  node_type: handoff
---

# Session Handoff for refmatrix {#root}

Date: 2026-09-15 (~05:50; session ac8e7c3f, continued across compactions)

## Completed {#completed}

All on `master`, each merged `--no-ff`, deployed. Deploy tree and fleet at **ffed3df** (0.69.1, 8/8
daemons supervised, every daemon on the hub's two shared model workers, every launchd label
`exit timeout = 45`). Earlier rounds: see the previous handoff in `workflow/past_handoffs/` and the
`savestate_*` memories.

- **Plan 2 rounds 8–9** (3734e7f, part of f5f0590): r8 restored the per-call socket timeout (the rerank
  leg was dead) and a budgeted `global_call` never spawns a daemon. r9 (self-found live): the partition
  probe reads the replica first (`verbs.memory_partition`, `_legacy_memory_partition_exists`) — a
  watcher flush had made every hook answer `[]`; `cached_replica` raises a typed miss; `--json` empty
  prints `[]`; the held-writer simulation HOLDS its catalog (bug-017); the hook's rerank pool is capped
  (`RERANK_DOC_CHARS` 700 — the extracted pool cost the shared worker 4.8 s, bug-019). Live now:
  SessionStart 0.2 s / 10 rows, per-prompt 4.6–5.0 s / 5 rows, 5/5 reranked, no warnings.
- **Plan 3 round 6** (26404fe → f5f0590): `memory list`/`search` call the memory verb (one bounded
  attempt, busy → replica); `_read_store` never hands a read to the write proxy; every fan-out names
  the stores it did not hear from; `memory_recall(partition=)` — one probe per command. Q15–Q18.
- **Plan 4 round 4** (26404fe, ffed3df): launchd is a supervisor — `ExitTimeOut` = one grace
  (`launchctl.EXIT_TIMEOUT_S` 45) on every plist incl. the hub; `daemon restart` pauses the watchdog,
  stops gracefully, kicks without `-k`; heartbeat-gated SIGKILL in `_verify_relaunch`; standalone
  refuses to spawn beside a live predecessor; forced plist/hub reinstalls stop the process before the
  bootout and `install_hub` waits for the unload + re-checks (bug-022); `shutdown.started` marker
  drives `_await_shutdown` (the heartbeat guard could never fire, bug-021); dead branch needs two ticks;
  `check`/`reinstall`/`install` take the caller's binary and refuse a dev tree (`rmx version --json`);
  `stop_daemon` keeps the discovered pid; heartbeat touch failure said once. Q12–Q16. **Live: 0 launchd
  SIGKILLs on `com.refmatrix.*` since the deploy** (24 in the 4 h before).
- Bugs logged 017–024. Todo G13 (worker-reported rerank cost; two hooks race one worker) and G14
  (daemons never re-adopt the shared worker after a hub outage — bug-024: 16 private workers after the
  05:28 hub-label loss; fixed by state with a second relaunch-fleet, not yet in code).

## Git State {#git-state}

- Branch `master` at ffed3df = deploy tree. `rmx install-hooks --check` in sync. GMD lint: 61 errors,
  all pre-existing inside `workflow/bullshit/` reports (BSD-authored; plan-4's q5/q6 anchors are
  theirs to fix); none in files this session touched.
- Full suite NOT re-run since e1dba80; the regression set for plans 2–5 + supervisors + parity + hooks
  ran at 374 passed (`pytest-plan3-r6-plan4-r4-regression.log`); the 9 legacy-contract failures were
  updated after and pass (`pytest-plan4-r4-green2.log` 90 passed). Run the full suite before the next
  deploy (`test_graph_landing` perma-red = plan 6.4).
- Three ch-bsd re-reviews running (spawned ~05:50): plan-2 r9, plan-3 r6, plan-4 r4 — reports land in
  `workflow/bullshit/`. Plan-5 r3 is CLEAN/completed.
- The live hub.log carries lines from pytest runs (`Watchdog._check` tests log through `hub._log`
  to `~/.refmatrix/hub.log`; `/tmp/rmxp4-*`, `/nowhere` roots) — test pollution of a live log, unfixed.
- User-gated: Claude Code restart (hooks unobserved live), `/mcp` reconnect (the dev-venv `rmx mcp`
  serves the old tool list — `partition` on `rmx_memory_recall` is new), push to GitHub.

## Next Steps {#next-steps}

1. Read the three verdicts; remediate; re-review until CLEAN; flip statuses (plan file AND
   plan-of-plans) only on CLEAN.
2. Plan 6: 6.1 stale deferrals (+ delete `duckdb_view.py`), 6.4 perma-red + mock-registry sweep, 6.5
   rewriter hook runtime resolution (bug-008). Then the BSD loop for plan 6.
3. G14 (shared-worker re-adoption) and G13 (worker-reported rerank cost) — small, worth a task.
4. Queued by the user for after the loops: universal `--like` pre/post filter on every read surface
   (todo G11, plan 7 to write). G12: no `defines` edge for `Daemon._snapshot_catalog`.
5. MEMORY.md is 208 lines (past the 200-line load budget) — the user's call on pruning.

## Past Sessions {#past-sessions}

| # | Session | Date | Archive |
|---|---------|------|---------|
| — | rmx save-state handoffs (`savestate_*` memories) carry history before this template | — | `rmx recall-state` |

## User Preferences {#user-preferences}

- Hooks must be reproducible from `rmx install-hooks`; MCP tools must not bypass the verbs layer.
- Plans first, then execute one by one, TDD, BSD re-review loop until clean.
- The user pushes to GitHub; Claude does not.
- Lookups only via `rmx context` / `rmx grep` / `tldr context`; never `/usr/bin/grep`, never
  `RMXGREP_MODE=plain` (removed), never `cat | grep`. Exact line ranges via `sed -n` / `awk`.

## Hand-Off Notes {#hand-off-notes}

- Deploy recipe now: `git -C ~/refmatrix pull --ff-only origin master` → (hub plist changed?)
  `~/bin/rmx hub launchctl install --force` (graceful) → warm workers → `~/bin/rmx hub relaunch-fleet`
  (re-renders drifted plists gracefully, restarts each) → verify `launchctl print` exit timeouts and
  launchd's SIGKILL log → `~/bin/rmx install-hooks --check`. If the hub is ever down while daemons
  boot, relaunch the fleet again once it is up (G14).
- `.mcp.json` is a workstation override (dev venv) and stays uncommitted.
- Restart Claude Code after the next hook-generator change so the regenerated hooks load.
