---
gmd: "0.1"
id: impl-task-4.4-plan-4-daemon-resilience
title: "Task 4.4 — a supervised start adopts an unsupervised daemon; orderly"
tags: [implementation-summary, plan-4]
metadata:
  node_type: implementation-summary
  task: task-4.4-plan-4-daemon-resilience
---

# Task 4.4 — adopt, don't loop {#root}

rel: implements -> [[task-4.4-plan-4-daemon-resilience]]

## What shipped {#shipped}

- `Daemon._adopt_unsupervised(sock_path) -> bool`: when a live daemon answers on the root's socket, log `adopted unsupervised daemon pid=N …`, ask it to stop (`stop_daemon`, bounded by `RMX_ADOPT_GRACE_S` = 20) and return True; a survivor is escalated by the existing `_reap_predecessor` at serve time. False when nothing answers.
- `daemon.serve_foreground` (launchd's `rmx daemon start --no-detach` entry) constructs the `Daemon` first and calls `_adopt_unsupervised` where it used to raise `daemon already running … stop it before launching under a supervisor` — the exit-1 that KeepAlive retried every 10 s.
- `serve_forever` keeps a log handle opened by the adoption instead of opening a second one.

## Live {#live}

Before deploy: orderly's launchd job read `runs = 12253`, `last exit code = 1`, `daemon.stderr.log` full of the old error, `rmx daemon status` `[UNVERIFIED]` (the 0.65.0 manual daemon pid 39128 from Sep 13). After deploying 0.69.0 the next KeepAlive spawn adopted it — see the plan's remedy summary for the post-deploy numbers (pid, `runs` static, `code_path` under `~/refmatrix/src`, no `[UNVERIFIED]` row in `rmx hub status`).

## TDD record {#tdd}

RED `workflow/review-output/pytest-task-4.4-red.log` (2 failed). GREEN `pytest-task-4.4-green.log` (24 passed with reap/liveness/shutdown/watchdog). Mutation `pytest-task-4.4-mutation.log`: adopting without stopping the predecessor fails `test_supervised_start_adopts_an_unsupervised_daemon` (the old daemon still answers). The test spawns a REAL unsupervised daemon on a tmp store; nothing is faked.
