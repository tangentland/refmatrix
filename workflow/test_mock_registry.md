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
| `cli._sync_memory_dir` (lambda) | the memory bridge itself | internal-active | tests/test_save_state.py | task 5.3 (`task-5.3-plan-5-memory-bridge-complete`, "real tests replace mocks"): replace with a real tmp-store ingest test |
| `upgrade.runtime_identity` (fake dict) | interpreter identity (environment) | external | tests/test_runtime_identity_surface.py, tests/test_plan1_remedy.py | permanent — the identity of the test interpreter is not the identity under test; the identity function itself is tested on fake trees |
| `daemon.call` / `daemon.ping` / `daemon.served_identity` (fake RPC) | the daemon process (external process boundary) | external | tests/test_runtime_identity_surface.py, tests/test_plan1_remedy.py, tests/test_hooks_reproducible.py, tests/test_plan2_remedy.py | permanent for CLI-surface tests; real-daemon coverage lives in tests/test_verbs_memory_recall.py (spawned daemon) |
| `hub._daemon_identity` (fake dict) | hub → daemon ping | internal-active | tests/test_runtime_identity_surface.py, tests/test_plan1_remedy.py | graduated: `test_gather_queues_carries_identity_end_to_end` patches only `daemon.call`/discovery and exercises the real `_gather_queues` → `_annotate_identity` wiring |
| `cli._root` (tmp root) | cwd resolution | external | tests/test_hooks_reproducible.py, tests/test_plan2_remedy.py | permanent — root discovery is an environment input |
| `search_hooks.hooks_dir` (tmp dir) | `~/.claude/hooks` location | external | tests/test_plan2_remedy.py | permanent |
| `hub.bus` (FakeBus: publish/refinement_queue) | the hub's bus (process boundary) | internal-active | tests/test_plan1_remedy.py | permanent for the alert unit test — the real `_queue_alert_once` body runs, only the bus is recorded; real-bus coverage = the hub integration path (`test_gather_queues_carries_identity_end_to_end` + live `rmx hub status`) |
| `Hub` self with stubbed `_gather_queues` (FakeHub/QuietHub/HotHub/ColdHub) | queue gathering | internal-active | tests/test_plan1_remedy.py | graduated: `test_gather_queues_carries_identity_end_to_end` drives the real `_gather_queues`; the stubs isolate the gate + publish only |
| `fakermx` (fake `rmx` shell binary on PATH) | the rmx CLI as seen by bin/rmxgrep | internal-active | tests/test_rmxgrep.py | permanent for the pipe-is-a-filter test (the property under test is that rmx is NEVER invoked on a pipe); real-CLI coverage = `test_grep_flags.py` |
| `hub.rpc` / `hub.is_running` (recording fake) | the hub process | external | tests/test_mcp_bus_passthrough.py, tests/test_mcp_channels.py | permanent for arg-passthrough assertions; graduated for behaviour by `tests/test_verbs_migrated.py::test_bus_verbs_round_trip_on_a_real_bus` (real `Bus`, real `hub.rpc` socket, real `Hub._op_bus_*`) |
| `_MiniHub` (thread on the real hub socket path, real `Bus` on a tmp RMX_HOME, real `Hub._op_bus_*`) | the hub PROCESS only | internal-active | tests/test_verbs_migrated.py | graduation = a full `Hub.run()` integration test once the hub can start headless without touching discovery/global store (plan 6 sweep); everything below the process boundary is real |
| `discovery.discover_roots` (pinned to the tmp store) | machine-wide store discovery (launchd + registry + cwd) | external | tests/test_verbs_migrated.py | permanent — an environment input; the federated verbs run their REAL per-project path against a real spawned daemon |
| `daemon.ping` / `daemon.call` (fake) + `verbs.<fn>` recorder | the daemon process / the verb under wiring test | external / internal-active | tests/test_verb_parity.py (wiring gate) | the recorder is the assertion itself (did the click command call the verb); behaviour of each verb is covered by test_verbs_migrated.py / test_verbs_memory_recall.py on real daemons |
| `_SilentDaemon` (real pid file + real unix socket that never answers) | a daemon that is alive but not answering | internal-active | tests/test_plan2_remedy.py | permanent as the "busy" simulation — nothing is faked below the socket; the alternative is a real daemon wedged on purpose |
| `discovery.daemon_status` (dict) | the up/busy/absent classifier | internal-active | tests/test_plan2_remedy.py (`test_stop_promote_bounds_subject_filing_and_is_loud`, `test_promote_timeout_message_says_not_confirmed`) | the busy/absent classification itself is covered for real by the `_SilentDaemon` tests; the two remaining patches isolate the bounded-call assertions (graduated for the detach path 2026-09-14) |
| `launchctl.is_loaded` / `launchctl.kickstart` / `daemon.stop_daemon` / `daemon.spawn_daemon_subprocess` (recording lambdas) + `daemon.heartbeat_age` / `read_pid` / `ping` (values) | launchd + the daemon process (external process boundaries) | external | tests/test_hub_watchdog.py, tests/test_hub_watchdog_grace.py, tests/test_hub.py | permanent — the watchdog's decision (restart / graceful-first / never) is the unit under test; the heartbeat thread itself is tested for real (`test_daemon_heartbeat_thread_touches_file`) |
| `_QueuesHub` (`_MiniHub` + a `queues` op over canned `_gather_queues` rows) | the hub process | internal-active | tests/test_plan3_remedy_r2.py | same graduation as `_MiniHub`; the `queues` rows are canned because gathering walks the fleet |
| `_PingOnlyDaemon` (`_SilentDaemon` that answers ping and stalls every other op) | a daemon holding the writer lock | internal-active | tests/test_plan2_remedy.py | permanent as the "held writer" simulation; nothing faked below the socket |
| `monkeypatch.setattr` sites (≈187 remaining, unregistered) | various | internal-active | tests/ | plan 6 sweep: register or graduate |

## Graduation Log {#graduation-log}

| Date | Mock | From → To | Notes |
|------|------|-----------|-------|
| 2026-09-14 | `discovery.daemon_status` + `daemon.ping` patches (detach busy branch) | dict/lambda → real pid + real silent socket (`_SilentDaemon`) | `test_detach_on_a_silent_daemon_costs_one_probe_plus_the_budget` replaces `test_detach_busy_branch_waits_wall_clock_and_names_the_pid` |
| 2026-09-14 | `hub.rpc` fake (bus behaviour) | fake → real `Bus` + real socket via `_MiniHub` | tests/test_verbs_migrated.py; the passthrough fakes stay for arg-shape assertions only |
