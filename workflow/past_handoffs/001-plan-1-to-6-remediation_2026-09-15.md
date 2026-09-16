---
gmd: "0.1"
id: handoff
title: "Session Handoff for refmatrix"
tags: [handoff, session]
metadata:
  node_type: handoff
---

# Session Handoff for refmatrix {#root}

Date: 2026-09-15 (~06:50; session ac8e7c3f, continued across compactions)

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
  (`RERANK_DOC_CHARS` 700 — the extracted pool cost the shared worker 4.8 s, bug-019). Live after the
  deploy: SessionStart 0.2 s / 10 rows (was `[]` under a held writer) — that half holds. The rerank
  half does NOT: my "5/5 reranked" was the quiet window 40 s after the relaunch; see [[#verdicts]].
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
- Three ch-bsd verdicts landed and are committed at 3dc118e — all DIRTY, see [[#verdicts]]. Plan-5 r3
  is CLEAN/completed; plans 2, 3, 4, 6 stay `in-progress` in both the plan file and plan-of-plans.
- Branch `task-6.1-plan-6-deferrals-docs-benchmark` holds one RED test, unmerged, by design.
- The live hub.log carries lines from pytest runs (`Watchdog._check` tests log through `hub._log`
  to `~/.refmatrix/hub.log`; `/tmp/rmxp4-*`, `/nowhere` roots) — test pollution of a live log, unfixed.
- User-gated: Claude Code restart (hooks unobserved live), `/mcp` reconnect (the dev-venv `rmx mcp`
  serves the old tool list — `partition` on `rmx_memory_recall` is new), push to GitHub.

## Verdicts in hand (all three DIRTY — no plan may flip) {#verdicts}

Reports in `workflow/bullshit/`, committed at 3dc118e. Every prior-round finding
closed in each; these are the new ones.

**plan-2 r9** (`2026-09-15-0605-…-r9-ffed3df.md`) — 1B/2S/2M:
- #b-1 BULLSHIT: the rerank leg is STILL dead as deployed. 0 of 7 runs of the exact
  hook argv reranked at 05:48–06:02 under load 3.5–5.8, each burning the whole 5 s to
  return what `--no-rerank` returns in 0.79 s; the capped 10×700 pool cost the shared
  worker 3.72 / 9.26 / 14.08 s. My "5/5 reranked, 1.7–2.8 s" was the quiet window 40 s
  after the relaunch. G13 has no task spec behind it (rule 9a).
- #s-2 the rerank eats the global leg's budget: `--scope both` returned project-only
  rows 7/7 while blaming a healthy global daemon it never asked.
- #s-3 the replica-first probe was applied to EVERY caller, so `verbs.memory_add`
  routes a WRITE off the lagging snapshot — one-line fix (`timeout is not None`).
- #m-4 the degrade line reports the 1.5 s daemon slice as the budget, then prints rows.
- #m-5 `rerank_available` patch unregistered (4th plan-2 registry residue).

**plan-3 r6** (`…-0617-…-r6-ffed3df.md`) — 2B/2S/2M:
- #b-1 BULLSHIT: `rmx memory get <name> --degree 1` raises a bare `NameError` at
  cli.py:9708 on the DEPLOYED build, every daemon state — a035117 dropped the
  function-local `daemon_mod` import above the surviving call; no test uses the flag.
- #b-2 BULLSHIT: `rmx memory promote` is the group's third read path, still bare-ping
  + 60 s × 3 = 180.2 s on a held writer, exit 1 with an EMPTY message.
- #s-3 `federated_concept` is the fourth fan-out and still drops a busy store
  (`rmx canon find` says "no live project hosts X").
- #s-4 three of the four new "said, never mute" branches in `federated_where` survive
  deletion with the suite green. #m-5 `_RECALL_FORWARD`'s `partition` has no guard.
  #m-6 interactive recall now spends its whole budget on the daemon before the replica.

**plan-4 r4** (`…-0600-…-r4-ffed3df.md`) — 1B/3S/2M. The launchd fix is confirmed
live by the auditor against launchd's own log (0 SIGKILL lines since 05:20 vs 24
before; a real 29 s drain exited 0 where 5 s would have killed it):
- #b-1 BULLSHIT: the hub's OWN plist is the one with no `rmx=`, no `_refuse_dev_tree`
  and no `check_hub` — a dev shell can point the fleet's supervisor at a dev venv.
- #s-2 `binary_identity` returns `dev_tree: None` for an old/broken binary and the
  falsy guard passes it, against its own "unknown, never fine" docstring.
- #s-3 the stop grace reaches 3 of 7 stop paths (`daemon stop`, vacuum, upgrade and
  `_respawn` still take the 5 s default; `_respawn` also discards the False).
- #s-4 the tests append to the LIVE `~/.refmatrix/hub.log` (43 lines).
- #m-5 `allow_dev` is unreachable from any command. #m-6 the session-indexer label
  still carries launchd's 5 s.

## Next Steps {#next-steps}

1. **Round 7, in this order** — plan-3 first (two of its three are one-liners on the
   deployed build): restore the `daemon_mod` import + a `--degree 1` test; route
   `memory promote` through the verb; `skipped` render in `canon_find`; guard the three
   `federated_where` branches. Then plan-4: `rmx=` + refusal + `check_hub` for the hub
   plist, `dev_tree is not False` as the guard, the grace into the other four stop
   paths, redirect the tests' hub log. Then plan-2: reserve the global leg's slice,
   scope the replica-first probe to budgeted callers (`timeout is not None`), and give
   G13 a task spec — the worker must report seconds-per-doc so a caller can decide
   BEFORE it commits. Re-review each until CLEAN; flip statuses only then.
2. Plan 6: **6.1 is parked RED on branch `task-6.1-plan-6-deferrals-docs-benchmark`**
   (test committed, GREEN patch archived at `workflow/review-output/task-6.1-green-patch.py.txt`
   — it drops the `yield_lock`/`yield_every` params `_sync_paths` ignored, which touches
   five daemon call sites and wants a full suite run). Then 6.4, 6.5.
3. G14 (shared-worker re-adoption after a hub outage) and G13 (worker-reported cost).
4. Queued by the user for after the loops: universal `--like` pre/post filter (G11,
   plan 7 to write). G12: no `defines` edge for `Daemon._snapshot_catalog`.
5. MEMORY.md is 213 lines — third flag; entries past ~195 do not load. User's call.

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
