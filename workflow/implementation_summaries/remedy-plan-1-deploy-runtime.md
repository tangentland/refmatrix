---
gmd: "0.1"
id: impl-remedy-plan-1-deploy-runtime
title: "Plan-1 remediation after ch-bsd bsd-plan1 (cabce24): the guard fires in the incident state"
tags: [implementation-summary, plan-1, remediation]
metadata:
  node_type: implementation-summary
  plan: plan-1-deploy-runtime
---

# Plan-1 remediation {#root}

rel: implements -> [[plan-1-deploy-runtime]]
rel: evidence-for -> [[bsd-plan1-deploy-runtime-cabce24]]

| Finding | Fix |
|---------|-----|
| #b-1 alert never gates on dev_tree | `hub._queue_row_is_hot(row)` includes `dev_tree`; `_queue_alert_loop` uses it; `test_gather_queues_carries_identity_end_to_end` drives the real `_gather_queues` with only discovery/daemon RPC patched |
| #b-2 verify skippable | `upgrade.upgrade()` calls `runtime_identity()` FIRST on every path and raises on `dev_tree`; the "already up to date" path runs `verify_editable`; `rmx daemon restart --relaunch` compares the new daemon's `code_path` to the CLI's import path and fails loud |
| #s-3 unknown rendered clean | `_daemon_identity` returns `{unknown, version}`; queue rows get `identity: unknown`; `hub status` prints `[UNVERIFIED vX]` / `[DEV TREE]` / clean as three states (CliRunner test) |
| #s-4 hub's own tree | `_op_hub_info` carries `version/code_path/dev_tree` (`_hub_identity`, cached); `hub status` prints the hub's `code:` line |
| #s-5 tests bypass wiring | end-to-end `_gather_queues` test; `hub status` test; mock registry rows added |
| #s-8 finder-style marker passes | `editable_target(strict=True)` raises "marker present but target unreadable"; `verify_editable` uses strict |
| #m-6 memory overstates | `feedback_deploy_tree_is_the_runtime` reworded; 19 legacy memories migrated to GMD frontmatter (`tools/gmd/migrate_memory.py`) + four legacy wikilinks repointed, so the bridge takes them |
| #m-7 identity per ping | `daemon._process_identity()` cached once per process, never raises |
| #m-9 status before gate | plan back to `in-progress`; task specs `complete`; `completed` only after CLEAN |

Also folded in (found by the plan-3 full suite): `SharedWorkerClient.info(timeout=)` bounded adoption probe (`RMX_SHARED_PROBE_TIMEOUT_S`, 5 s) and no reconnect-retry on `TimeoutError` — a mute `models.sock` cost a daemon 300 s (the wedge the watchdog SIGKILLed on 2026-09-14). `test_daemon_falls_back_when_shared_socket_does_not_answer` now passes in seconds; it timed out at the session-start commit too.

RED `workflow/review-output/pytest-remedy12-RED.log` (19 failed); GREEN `pytest-remedy12-GREEN.log`.
