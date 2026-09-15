---
gmd: "0.1"
id: handoff
title: "Session Handoff for refmatrix"
tags: [handoff, session]
metadata:
  node_type: handoff
---

# Session Handoff for refmatrix {#root}

Date: 2026-09-15 (~03:10; session ac8e7c3f, continued across compactions)

## Completed {#completed}

All on `master`, each merged `--no-ff`, deployed (`git -C ~/refmatrix pull --ff-only` → global daemon
`restart --relaunch` → hub kickstart → `rmx hub relaunch-fleet` → `~/bin/rmx install-hooks --apply --force`).
Deploy tree and fleet at **7bca4bb** (0.69.1, 8/8 daemons, every daemon on the hub's shared model workers).

- **Plan 1** — completed (r5 bookkeeping closed in ebdd9c7).
- **Plan 2 r7** (4a8260d, 8d0a665): the per-prompt recall budget covers every leg — clock before the
  partition probe, shared-worker sockets + rerank probe (1 s) under the deadline, rerank skipped/said,
  global leg one attempt on both paths, PreCompact `--timeout 30`, `RMX_INVOCATION_SOURCE=hook` is hook
  mode, CLI default 30 s = verb default. Live: 2.4 s / 5 rows on the exact hook argv. Awaiting bsd r7.
- **Plan 3 r5** (dfc0e62): recall-state says busy; memory read verbs under one 10 s deadline; MCP recall
  default 30 s; promote + per-hit get typed; `memory_partition` raises on op-level busy; read-worded
  no-replica error; canned locate carries `CANARY-skip`. Awaiting bsd r5.
- **Plan 4 r3** (168820d, ef4365a): `XPC_SERVICE_NAME` supervised gate; plist `--check`/`reinstall`,
  `relaunch-fleet` reinstalls drift; heartbeat ticks on completion; `daemon.graceful_stop` signals first;
  typed foreground gate; kill grace 45 s + one more grace while ticking. bug-012 (zombie is_alive),
  bug-013 (`install --force` silent no-op → two daemons ran standalone; fixed + live-repaired 01:33). Awaiting bsd r3.
- **Plan 5 r3** (a965805): a booting daemon is busy (`pid_is_rmx`); `memory sync-disk` alias restored
  (fleet's p20-0 compiler calls it); this repo's compiler seeds via `ingest-gmd --as-memory` and fails
  loud; SessionStart guardrail entry un-silenced; seeded silent fixture. bug-011. Awaiting bsd r3.
- **Plan 6** in-progress: 6.2 (generated CLI tree + hooks table, `scripts/gen-cli-tree.py`) and 6.3
  (`eval/production/results/csn_python/metrics.json`, full corpus MRR@10 0.961, cited) done. 6.1/6.4/6.5 open.
- **bug-015/014** (f4187d6, 4ab21eb, 7bca4bb): the project daemon wedged 3× (01:47/01:53/02:26; ping
  alive, heartbeat stale). `kill -USR1 <pid>` now dumps every thread's stack to daemon.stderr.log;
  daemon shared-worker ops bounded (30 s); `scan-prompt --timeout 5`; the hub's "BrokenPipe" lines were
  daemons' 5 s probes giving up on a cold worker (warm 15–33 s) → `PROBE_TIMEOUT_S` 45 s, hub keeps a
  worker when the client left, drops only a worker whose own pipe died. Root cause of the wedge still
  a hypothesis (rerank-under-lock on a mute worker); the next wedge gets a dump.
- **`RMXGREP_MODE=plain` removed** (50ca938) — user: it was a bypass. Lookups: `rmx context`,
  `rmx grep`, `tldr context`; never `/usr/bin/grep`, never `cat | grep`.

## Git State {#git-state}

- Branch `master` at 7bca4bb = deploy. `rmx install-hooks --check` in sync (settings.json regenerated
  with the deployed rmx). Full suite last run at e1dba80: 3 red (2 fake-signature drifts fixed as bug-010,
  `test_graph_landing` perma-red = plan 6.4); not re-run since — run it before the next deploy.
- Four ch-bsd re-reviews running: plan-2 r7, plan-3 r5, plan-4 r3, plan-5 r3 (reports land in
  `workflow/bullshit/`).
- User-gated: Claude Code restart (hooks unobserved live), `/mcp` reconnect (dev-venv `rmx mcp` pids
  5555/10278 serve the old tool list), push to GitHub.

## Next Steps {#next-steps}

1. Read the four verdicts; remediate; re-review until CLEAN; flip statuses (plan file AND plan-of-plans).
2. Plan 6: 6.1 stale deferrals (+ delete `duckdb_view.py`), 6.4 perma-red + mock-registry sweep, 6.5 rewriter
   hook runtime resolution (bug-008). Then BSD loop for plan 6.
3. Queued by the user (after the loops): universal `--like` pre/post filter on every read surface
   (todo G11, plan 7 to write). Also G12: the project index has no `defines` edge for
   `Daemon._snapshot_catalog`; `rmx stats --stale` raw TimeoutError on a busy daemon.
4. thiquet restarted by the watchdog at 03:04:29 — check hub.log/rmxd.log for a wedge (bug-015 shape);
   if so `kill -USR1` it first, read `daemon.stderr.log`.

## Past Sessions {#past-sessions}

| # | Session | Date | Archive |
|---|---------|------|---------|
| — | rmx save-state handoffs (`savestate_*` memories) carry history before this template | — | `rmx recall-state` |

## User Preferences {#user-preferences}

- Hooks must be reproducible from `rmx install-hooks`; MCP tools must not bypass the verbs layer.
- Plans first, then execute one by one, TDD, BSD re-review loop until clean.
- The user pushes to GitHub; Claude does not.

## Hand-Off Notes {#hand-off-notes}

- Restart Claude Code after this commit so the regenerated `.claude/settings.json` hooks load
  (`--timeout 5` on both per-prompt hooks, `--timeout 30` on the PreCompact recall).
- `.mcp.json` is a workstation override (dev venv) and stays uncommitted.
