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
| `cli._sync_memory_dir` (lambda) | the memory bridge itself | internal-active | tests/test_save_state.py | plan 3: replace with a real tmp-store ingest test |
| `upgrade.runtime_identity` (fake dict) | interpreter identity (environment) | external | tests/test_runtime_identity_surface.py, tests/test_plan1_remedy.py | permanent — the identity of the test interpreter is not the identity under test; the identity function itself is tested on fake trees |
| `daemon.call` / `daemon.ping` / `daemon.served_identity` (fake RPC) | the daemon process (external process boundary) | external | tests/test_runtime_identity_surface.py, tests/test_plan1_remedy.py, tests/test_hooks_reproducible.py, tests/test_plan2_remedy.py | permanent for CLI-surface tests; real-daemon coverage lives in tests/test_verbs_memory_recall.py (spawned daemon) |
| `hub._daemon_identity` (fake dict) | hub → daemon ping | internal-active | tests/test_runtime_identity_surface.py, tests/test_plan1_remedy.py | graduated: `test_gather_queues_carries_identity_end_to_end` patches only `daemon.call`/discovery and exercises the real `_gather_queues` → `_annotate_identity` wiring |
| `cli._root` (tmp root) | cwd resolution | external | tests/test_hooks_reproducible.py, tests/test_plan2_remedy.py | permanent — root discovery is an environment input |
| `search_hooks.hooks_dir` (tmp dir) | `~/.claude/hooks` location | external | tests/test_plan2_remedy.py | permanent |
| `hub.bus` (FakeBus: publish/refinement_queue) | the hub's bus (process boundary) | internal-active | tests/test_plan1_remedy.py | permanent for the alert unit test — the real `_queue_alert_once` body runs, only the bus is recorded; real-bus coverage = the hub integration path (`test_gather_queues_carries_identity_end_to_end` + live `rmx hub status`) |
| `Hub` self with stubbed `_gather_queues` (FakeHub/QuietHub/HotHub/ColdHub) | queue gathering | internal-active | tests/test_plan1_remedy.py | graduated: `test_gather_queues_carries_identity_end_to_end` drives the real `_gather_queues`; the stubs isolate the gate + publish only |
| `monkeypatch.setattr` sites (≈187 remaining, unregistered) | various | internal-active | tests/ | plan 6 sweep: register or graduate |

## Graduation Log {#graduation-log}

| Date | Mock | From → To | Notes |
|------|------|-----------|-------|
| — | — | — | — |
