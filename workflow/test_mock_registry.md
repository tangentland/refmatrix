---
gmd: "0.1"
id: test_mock_registry
title: "Test Mock Registry — mock governance"
tags: [process, testing, governance]
metadata:
  node_type: registry
---

# Test Mock Registry {#root}

Mock governance for `refmatrix`. Every mock in `tests/` is classified here. Production
code (`src/`) contains **no mocks** — see CLAUDE.md "No Mocks in Production Code".

## Classification {#classification}

| Classification | Meaning | Allowed? |
|----------------|---------|----------|
| `external` | External library, platform API, third-party service | Permanent |
| `internal-active` | Internal subsystem with existing implementation | **Must graduate** |
| `internal-pending` | Internal subsystem not yet built | Temporary |

## Registry {#registry}

| Mock | Target | Classification | Test File(s) | Graduation Plan |
|------|--------|----------------|--------------|-----------------|
| `cli._sync_memory_dir` (lambda) | the memory bridge itself | internal-active | (none — graduated) | graduated 2026-09-14 (task 5.3): tests/test_memory_bridge.py runs the real bridge on a spawned daemon |
| `upgrade.runtime_identity` (fake dict) | interpreter identity (environment) | external | tests/test_runtime_identity_surface.py, tests/test_plan1_remedy.py | permanent — the identity of the test interpreter is not the identity under test; the identity function itself is tested on fake trees |
| `daemon.call` / `daemon.ping` / `daemon.served_identity` (fake RPC) | the daemon process (external process boundary) | external | tests/test_runtime_identity_surface.py, tests/test_plan1_remedy.py, tests/test_hooks_reproducible.py, tests/test_plan2_remedy.py | permanent for CLI-surface tests; real-daemon coverage lives in tests/test_verbs_memory_recall.py (spawned daemon) |
| `hub._daemon_identity` (fake dict) | hub → daemon ping | internal-active | tests/test_runtime_identity_surface.py, tests/test_plan1_remedy.py | graduated: `test_gather_queues_carries_identity_end_to_end` patches only `daemon.call`/discovery and exercises the real `_gather_queues` → `_annotate_identity` wiring |
| `cli._root` (tmp root) | cwd resolution | external | tests/test_hooks_reproducible.py, tests/test_plan2_remedy.py, tests/test_plan1_remedy.py, tests/test_plan3_remedy.py, tests/test_plan3_remedy_r2.py, tests/test_plan3_remedy_r3.py, tests/test_verb_parity.py, tests/test_memory_bridge.py, tests/test_memory_recall_widen.py | permanent — root discovery is an environment input |
| `search_hooks.hooks_dir` (tmp dir) | `~/.claude/hooks` location | external | tests/test_plan2_remedy.py | permanent |
| `hub.bus` (FakeBus: publish/refinement_queue) | the hub's bus (process boundary) | internal-active | tests/test_plan1_remedy.py | permanent for the alert unit test — the real `_queue_alert_once` body runs, only the bus is recorded; real-bus coverage = the hub integration path (`test_gather_queues_carries_identity_end_to_end` + live `rmx hub status`) |
| `Hub` self with stubbed `_gather_queues` (FakeHub/QuietHub/HotHub/ColdHub) | queue gathering | internal-active | tests/test_plan1_remedy.py | graduated: `test_gather_queues_carries_identity_end_to_end` drives the real `_gather_queues`; the stubs isolate the gate + publish only |
| `fakermx` (fake `rmx` shell binary on PATH) | the rmx CLI as seen by bin/rmxgrep | internal-active | tests/test_rmxgrep.py | permanent for the pipe-is-a-filter test (the property under test is that rmx is NEVER invoked on a pipe); real-CLI coverage = `test_grep_flags.py` |
| `hub.rpc` / `hub.is_running` (recording fake) | the hub process | external | tests/test_mcp_bus_passthrough.py, tests/test_mcp_channels.py, tests/test_plan1_remedy.py, tests/test_plan3_remedy_r2.py | permanent for arg-passthrough assertions; graduated for behaviour by `tests/test_verbs_migrated.py::test_bus_verbs_round_trip_on_a_real_bus` (real `Bus`, real `hub.rpc` socket, real `Hub._op_bus_*`) |
| `_MiniHub` (thread on the real hub socket path, real `Bus` on a tmp RMX_HOME, real `Hub._op_bus_*`) | the hub PROCESS only | internal-active | tests/test_verbs_migrated.py | graduation = a full `Hub.run()` integration test once the hub can start headless without touching discovery/global store (plan 6 sweep); everything below the process boundary is real |
| `discovery.discover_roots` (pinned to the tmp store) | machine-wide store discovery (launchd + registry + cwd) | external | tests/test_verbs_migrated.py, tests/test_plan1_remedy.py (with `discovery.daemon_status` / `store_name` values for the gather-queues cap test), tests/test_plan3_remedy_r2.py | permanent — an environment input; the federated verbs run their REAL per-project path against a real spawned daemon |
| `daemon.ping` / `daemon.call` (fake) + `verbs.<fn>` recorder | the daemon process / the verb under wiring test | external / internal-active | tests/test_verb_parity.py (wiring gate), tests/test_plan3_remedy_r3.py (`verbs.queues` canned rows for the busy render) | the recorder is the assertion itself (did the click command call the verb); behaviour of each verb is covered by test_verbs_migrated.py / test_verbs_memory_recall.py on real daemons |
| `_SilentDaemon` (real pid file + real unix socket that never answers) | a daemon that is alive but not answering | internal-active | tests/test_plan2_remedy.py | permanent as the "busy" simulation — nothing is faked below the socket; the alternative is a real daemon wedged on purpose |
| `discovery.daemon_status` (dict) | the up/busy/absent classifier | internal-active | tests/test_plan2_remedy.py (`test_stop_promote_bounds_subject_filing_and_is_loud`, `test_promote_timeout_message_says_not_confirmed`, `test_stop_promote_never_exceeds_its_timeout_across_calls`, `test_subject_filing_refusal_is_not_reported_as_a_timeout`, `test_verb_recall_timeout_is_a_deadline_across_calls`), tests/test_plan1_remedy.py, tests/test_plan3_remedy.py | the busy/absent classification itself is covered for real by the `_SilentDaemon` tests; these patches isolate the bounded-call assertions (graduated for the detach path 2026-09-14) |
| `launchctl.is_loaded` / `launchctl.kickstart` / `daemon.stop_daemon` / `daemon.spawn_daemon_subprocess` (recording lambdas) + `daemon.heartbeat_age` / `read_pid` / `ping` (values) | launchd + the daemon process (external process boundaries) | external | tests/test_hub_watchdog.py, tests/test_hub_watchdog_grace.py, tests/test_hub.py | permanent — the watchdog's decision (restart / graceful-first / never) is the unit under test; the heartbeat thread itself is tested for real (`test_daemon_heartbeat_thread_touches_file`) |
| `_QueuesHub` (`_MiniHub` + a `queues` op over canned `_gather_queues` rows) | the hub process | internal-active | tests/test_plan3_remedy_r2.py | same graduation as `_MiniHub`; the `queues` rows are canned because gathering walks the fleet |
| `_PingOnlyDaemon` (`_SilentDaemon` that answers ping and stalls every other op) | a daemon holding the writer lock | internal-active | tests/test_plan2_remedy.py | permanent as the "held writer" simulation; nothing faked below the socket |
| `_BootingDaemon` (seeded store + real child process with `rmx daemon start` in its argv, pid file, NO socket) + `rmx_lookalike_process` (the child `_SilentDaemon` / `_PingOnlyDaemon` now point their pid file at) | a daemon in its boot window / the daemon process identity `discovery.pid_is_rmx` reads | internal-active | tests/test_plan5_remedy.py, tests/test_plan2_remedy.py | permanent as the "booting" simulation; nothing faked below the pid file — the alternative is racing a real `serve_forever` boot |
| `rmx` PATH shim (shell script recording argv; fails `ingest-gmd` on demand) | the deployed `rmx` binary the p20-0 compiler shells out to | external | tests/test_plan5_remedy.py (`test_compile_guardrails_seeds_via_the_bridge_and_fails_when_it_fails`) | permanent: the compiler is a subprocess-driving script; the real bridge command is covered by `test_memory_bridge.py` |
| `hub.status` (fake dict) | the hub process (`hub_info` rpc + pid file) | external | tests/test_plan1_remedy.py | permanent for the `hub status` render test; the real path (`_op_hub_info` → `status()`) is covered by live `rmx hub status` |
| `dm.os._exit` (counter) + `dm._learn_grep_hits` (raising fake) + `_request_snapshot` / `_log` (no-op / capture) | the process exit and the learn collaborator | external / internal-active | tests/test_daemon_learn_guard.py, tests/test_plan4_remedy.py, tests/test_repair_entities.py, tests/test_daemon_adopt.py | permanent for the degrade / fast-exit unit tests (a real `os._exit` ends pytest); the production wiring is covered on a spawned daemon by `test_boot_repair_runs_on_a_spawned_daemon` |
| DuckDB `con.execute` (fake for the GROUP BY/HAVING dup queries) | the duplicate-detection SQL | internal-active | tests/test_repair_entities.py | permanent by construction: PK + UNIQUE make real duplicates impossible on a DuckDB store, so the abort branch is only reachable with the query faked |
| `_DeadPool` / `_LivePool` (Future that never / immediately completes) | the daemon's cli pool | internal-active | tests/test_plan4_remedy.py | permanent for the serving-derived heartbeat test; the real pool path runs on every spawned daemon in the suite |
| `hub.status` / `hub._daemon_identity` (fake dicts) + `subprocess.run` (recorder) | hub process / daemon pings / the child `rmx` | external | tests/test_plan4_remedy.py | permanent for the `hub status` version render and the `relaunch-fleet` orchestration test; the real path is the live fleet relaunch recorded in the remedy summary |
| `monkeypatch.setattr` sites (≈187 remaining, unregistered) | various | internal-active | tests/ | plan 6 sweep: register or graduate |

## Graduation Log {#graduation-log}

| Date | Mock | From → To | Notes |
|------|------|-----------|-------|
| 2026-09-14 | `discovery.daemon_status` + `daemon.ping` patches (detach busy branch) | dict/lambda → real pid + real silent socket (`_SilentDaemon`) | `test_detach_on_a_silent_daemon_costs_one_probe_plus_the_budget` replaces `test_detach_busy_branch_waits_wall_clock_and_names_the_pid` |
| 2026-09-14 | `cli._sync_memory_dir` lambda (save-state bridge) | lambda → real bridge on a spawned daemon | tests/test_memory_bridge.py::test_finalize_save_state_bridges_the_handoff_dir_for_real + ::test_finalize_skips_the_bridge_on_sync_false_and_dry_run replace tests/test_save_state.py::test_finalize_runs_memory_bridge_over_the_handoff_dir |
| 2026-09-14 | `hub.rpc` fake (bus behaviour) | fake → real `Bus` + real socket via `_MiniHub` | tests/test_verbs_migrated.py; the passthrough fakes stay for arg-shape assertions only |
