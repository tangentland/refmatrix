---
gmd: "0.1"
id: bug_registry
title: "Bug Registry — known bugs, root causes, and fixes"
tags: [process, bugs, governance]
metadata:
  node_type: registry
---

# Bug Registry {#root}

Curated log of bugs encountered and fixed — sibling to the mock and deferral registries. Where
[[test_mock_registry]] classifies test-side mocks and [[deferral_registry]] tracks deferred
functionality, this registry captures **bugs**: what broke, why, and the fix — so the same mistake
is not re-derived across sessions. Managed the same way (curated, classified, GMD-linted);
`@ch-gap-master` keeps it current, `@ch-bsd` mines it for recurring cheap-fix patterns.

rel: part-of -> [[test_mock_registry]]

## When to log {#when}

The threshold is LOW — when in doubt, log it. Log an entry whenever:

- The user reports an error, bug, or problem ("doesn't work", "broken", "shows wrong X").
- A test, build, lint, or type check fails, or a runtime/import/type/syntax error occurs.
- You fix something that was broken, or change error-handling / validation logic.
- You edit the same file more than twice to get one thing right (a signal it was a bug).

**Before fixing:** search this registry first — the fix may already be known. If `rmx` is present,
`rmx memory search "<symptom>"` also surfaces past occurrences.

## Status {#status}

| Status | Meaning |
|--------|---------|
| `open` | Reproduced, not yet fixed |
| `fixed` | Fix landed + verified |
| `recurring` | Seen again after a prior fix — needs a durable/root fix |

## Registry {#registry}

| ID | Symptom / error | File(s) | Root cause | Fix | Tags | Status | Seen |
|----|-----------------|---------|------------|-----|------|--------|------|
| bug-001 | deploy venv `.pth` → dev checkout; `rmx`/daemons/hub ran uncommitted code (2026-09-14) | `~/refmatrix/.venv/.../__editable__.refmatrix-*.pth`, save-state memory step 4 | absolute `pip install -e <dev tree>` into the deploy venv | `upgrade.runtime_identity` + `verify_editable`; `rmx version -v`; memory rewritten (0.66.3) | deploy, venv | fixed | 1 |
| bug-002 | `rmx install-hooks --enforce` accepted but ignored (want() only honoured it with no project root) | src/refmatrix/hooks.py | forced branch unreachable from every production caller | `if enforce is True: return True` (0.68.1) | hooks | fixed | 1 |
| bug-003 | `--force` stripped user hooks named `enforce-*.sh` | src/refmatrix/hooks.py `_RMX_HOOK_SIGNATURES` | prefix signature `.claude/hooks/enforce-` | exact script names (0.68.1) | hooks | fixed | 1 |
| bug-004 | daemon wedged 300 s adopting a mute `models.sock`; `test_daemon_falls_back_when_shared_socket_does_not_answer` timed out | src/refmatrix/modelsrv.py, daemon.py `_model_client` | probe used the worker op timeout; a socket timeout (an OSError) triggered reconnect with the default timeout | bounded `info(timeout=PROBE_TIMEOUT_S)`, no retry on TimeoutError (0.68.1) | daemon, models | fixed | 1 |
| bug-005 | Claude Code shell snapshots contained `set -o #`; user function bodies had grep rewritten to rmxgrep | bin/rmxgrep, hooks.AGENT_BASHRC_SECTION, cli.py `_grep_stdin_addendum` | BASH_ENV alias + expand_aliases + RMXGREP_MODE=rich in the snapshot shell; index note on stdout | note → stderr (0.66.2); piped stdin = real grep; grep()/rg() functions (cf3d87d) | grep, hooks | fixed | 1 |
| bug-006 | `rmx ingest-gmd --detach` said "no daemon running" to a busy daemon; SessionStart catch-up skipped after every deploy | src/refmatrix/cli.py ingest_gmd | ping cannot tell busy from absent | discovery.daemon_status busy → retry then busy-specific error (0.68.1) | daemon, bridge | fixed | 1 |
| bug-007 | `rmx_where` / `rmx_locate` / `rmx locate` returned stale (or empty) results from a long-lived process after the store changed; `test_locate_verb_finds_an_ingested_file_by_basename` → `{'results': []}` | src/refmatrix/search.py `cached_replica` | the cached read-only DuckDB connection stays bound to the OLD `catalog.read.duckdb` inode after the daemon's tmp+rename snapshot; the MCP server / hub never reopen | `_snapshot_sig` (ino, mtime_ns, size) recorded at open; `cached_replica` reopens when it changes (plan-3 r1 remedy) | search, replica, staleness | fixed | 1 |
| bug-008 | `tests/test_repo_hooks_in_sync.py` red: `script rmxgrep-rewrite.py differs from the generator's render` — live `~/.claude/hooks/rmxgrep-rewrite.py` carried `RMXGREP = "/Users/tholley/claude_tools/refmatrix/bin/rmxgrep"` (dev tree) at 21:43 after a 21:31 deploy regen | src/refmatrix/search_hooks.py `install_search_hooks` / `render_scripts` | the rewriter bakes the GENERATOR's tree into a USER-GLOBAL script; any `install-hooks --apply` from the dev venv (a test without the `RMX_CLAUDE_HOOKS_DIR` redirect, an audit probe) overwrites the live hook with dev paths | regenerated from `~/bin/rmx` (deploy) both times; durable fix = plan 6: the rewriter resolves the wrappers at RUNTIME from the tree of the `rmx` on PATH instead of baking paths (see deferral) | hooks, dev-deploy | recurring | 2 |
| bug-009 | pytest died silently mid-run (no summary line) after `test_daemon_learn_guard` — `...........F.........` then nothing | tests/test_daemon_learn_guard.py, src/refmatrix/daemon.py `_arm_deferred_exit` | the degrade path arms a deferred `os._exit` thread (2 s); the test's `os._exit` monkeypatch was undone before it fired, so the REAL exit killed the test process | the test sets `RMX_DEGRADE_EXIT_S=0.2` and asserts the deferred exit inside its patch; also `test_hub_watchdog` now records `hub.graceful_stop` instead of letting it signal a fake pid | tests, daemon | fixed | 1 |
| bug-010 | full suite at e1dba80: `test_coref.py::test_as_memory_ingest_emits_coref_linkage` → `assert None is not None` (row looked up as `note.md`); `test_phase8_mcp_sched.py::test_federated_concept_groups_by_project` → `assert set() == {'a', 'b'}` | tests/test_coref.py, tests/test_phase8_mcp_sched.py | production changes outran their tests' fakes: plan-5 5.1 (3039d2e) names bridged memories by stem, and plan-3 r2 moved `_live_roots` from `daemon_mod.ping` to `discovery.daemon_status` (busy ≠ absent) — the test patched the old seam, so the real probe ran against `/a/.refmatrix` and classified it absent | tests look up `note` and patch `search.discovery.daemon_status`; the fake-signature sweep is the plan-6 6.4 registry pass | test-fake, seam-drift, plan-6 | fixed | 1 |
| bug-011 | SessionStart in nine projects: `compile_guardrails: rmx memory sync-disk … exited 2: No such command 'sync-disk'` behind `>/dev/null 2>&1 \|\| true` — edited guardrails never reached the store; plus two daemon boots died on `Could not set lock on file catalog.B.duckdb: Conflicting lock is held` | src/refmatrix/discovery.py `daemon_status`, src/refmatrix/cli.py `memory_sync_disk` / `_store` / `_ingest_gmd_sync`, src/refmatrix/hooks.py `_add_enforce_entries`, .claude/p20-0/compile_guardrails.py | (a) `daemon_status` said busy only when the socket file existed, but `serve_forever` binds the socket LAST — the boot window (pid alive, Store open, no socket) classified absent and the CLI opened the slot in-process; (b) plan-5 deleted `memory sync-disk` without sweeping callers, and the generated hook silenced the compiler | (a) `pid_is_rmx` (live pid + command line names rmx/refmatrix) → busy with or without socket; `daemon status` renders `starting — socket not bound yet`; (b) alias restored as a thin forward to the bridge, compiler calls `ingest-gmd --as-memory` and fails the compile on a failed seed, SessionStart entry is a plain `if` with no redirect; tests `tests/test_plan5_remedy.py` | busy-not-absent, boot-window, silent-hook, sync-disk | fixed | 1 |
| bug-012 | `test_stop_daemon_signals_first_when_ping_fails` → `stop_daemon` returned False after 7.5 s with `kill: SIGKILL (heartbeat infs stale)` although the SIGTERM'd child was dead | src/refmatrix/daemon.py `is_alive` | `os.kill(pid, 0)` succeeds on a ZOMBIE (our own exited child before `wait`), so a signalled child daemon looked alive for the whole grace and drew the stale-heartbeat SIGKILL | `is_alive` first tries `os.waitpid(pid, WNOHANG)` — reaps/sees an exited child; a foreign pid (launchd's daemons) falls to the signal probe | zombie, liveness, plan-4 | fixed | 1 |
| bug-013 | after `rmx hub relaunch-fleet` (098774a) the project and global labels were UNLOADED (`launchctl print` rc 113) while their daemons ran standalone (ppid 1, no adoption); the plist files on disk were current | src/refmatrix/launchctl.py `install` / `_wait_loaded`, src/refmatrix/cli.py `daemon_restart` (relaunch) | `install(force=True)` bootouts a RUNNING label, waits 3 s for it to leave the domain and IGNORES the result; the bootstrap then fails against the still-loaded (draining) label and the `load` fallback too, and `_wait_loaded(True)` only proves *something* is loaded; a moment later the old job finishes booting out → nothing loaded. `daemon restart --relaunch` then took the not-loaded branch and spawned a standalone daemon | `install(force)` waits for the bootout to complete (up to the kill grace) and raises if the label is still loaded; after bootstrap it re-reads `launchctl print` and requires the rendered env; `check` compares the LOADED job's env too; `relaunch` on an installed-but-unloaded plist bootstraps it instead of spawning standalone. Live fix 2026-09-15 01:33: plain `install` on both roots → supervised daemons adopted the standalone ones | launchd, install-force, plist, plan-4 | fixed | 2 |
| bug-014 | every daemon logs `embed: hub-shared worker unusable (TimeoutError('timed out')); falling back to a private worker` at boot; `hub.log`: `models worker[rerank] warm in 2195.3s`, repeated `models role=rerank op=info failed: BrokenPipeError`; fleet back on 16 private workers (~450 MB each) | src/refmatrix/modelsrv.py `SharedWorkerClient` (daemon side), src/refmatrix/hub.py models supervisor | the daemon probes the shared worker with a 5 s timeout, but a COLD worker (first spawn, or re-created after the 900 s idle-evict) needs 10–20 s to load its model (36 min under the benchmark's CPU saturation), so every daemon that boots or reconnects while the worker is cold falls back to a private worker for good; the hub's `info` op on a still-loading worker breaks the pipe | ROOT CAUSE (2026-09-15 02:35, hub.log): the `BrokenPipeError` lines are the hub failing to SEND the reply to a daemon whose bounded probe (5 s) had already given up while the worker was still loading (measured warm: embed 14.9 s, rerank 33 s) — the worker was never broken. Fix: `PROBE_TIMEOUT_S` 5 → 45 s so a booting daemon waits for a cold worker instead of going private; `ModelServer._handle` treats a client-side send failure as "client left" (worker kept) and drops a worker only when ITS pipe failed after `WorkerClient`'s own respawn-and-retry, and only that worker (a stale reference must not close the replacement — the bug-015 follow-up's first version did exactly that and cascaded across the fleet) | models, hub, memory-footprint, cold-start | fixed | 2 |
| bug-015 | the project daemon wedges minutes after boot: ping answers, heartbeat goes stale (88 s), `rmx partition list` > 25 s, `hub queues` says busy, no job lines in rmxd.log; the hub watchdog restarted it 01:47, 01:53, 02:26 (`graceful stop … not answering ping (SIGTERM sent now)`); every hook probe in the window returned `[]` | src/refmatrix/daemon.py (`_reranker` / `_model_client`, the rerank under an op), src/refmatrix/modelsrv.py (hub worker proxy), src/refmatrix/scan.py `scan_prompt` (`shared_reranker()` unbounded) | hypothesis (no stacks: the daemon has no dump signal): the hub's shared rerank worker is broken (`models role=rerank op=rerank failed: BrokenPipeError` on every call) and a daemon-side rerank inside an op waits on it at the worker's 300 s default while holding the store lock; the CLI's `scan-prompt` blocks on the same worker for 20 s+ (killed at 20 s in the probe) | remedied (root cause still a hypothesis; bug-014's cold-worker finding makes the daemon-side rerank-under-lock on a cold/mute worker the leading one): `SHARED_OP_TIMEOUT_S` (30 s) on the daemon's shared-worker client, `scan-prompt --timeout 5` (rerank probe 1 s) in the generator, `ModelServer._drop_worker` on a broken pipe, `kill -USR1 <pid>` dumps every thread's stack to daemon.stderr.log — `workflow/implementation_summaries/bug-015-daemon-wedge.md`; the next wedge gets a dump | wedge, rerank, shared-worker, heartbeat | remedied | 3 |

<!--
Entry conventions:
- ID: bug-NNN, zero-padded, monotonic.
- Symptom: the exact error string or user complaint (quote errors verbatim).
- Root cause: WHY it broke, not just where.
- Fix: what changed to resolve it (file:function or the concrete edit).
- Tags: kebab keywords for search (e.g. auth, off-by-one, import, migration).
- Seen: occurrence count; bump + flip Status to `recurring` if it reappears.
-->
