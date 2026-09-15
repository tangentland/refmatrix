---
gmd: "0.1"
id: task-4.4-plan-4-daemon-resilience
title: "Task 4.4: Supervised start adopts an unsupervised daemon; fix orderly"
tags: [task, plan-4]
metadata:
  node_type: task
  status: pending
  plan: plan-4-daemon-resilience
---

# Task 4.4: Supervised start adopts an unsupervised daemon; fix orderly {#root}

> Plan: [[plan-4-daemon-resilience]]
> Status: Pending
> Depends on: —

rel: part-of -> [[plan-4-daemon-resilience]]

## Requirements {#requirements}

- Spawned unsupervised test daemon + `serve_foreground(supervised=True)` on the same root → old pid gone, new one serving, one log line. Orderly launchd `runs` static for 5 minutes.
- After adoption, orderly's ping reports `code_path` under `~/refmatrix/src` and `rmx hub status` shows no `[UNVERIFIED]` row (bsd-plan1 #s-3).

## Files to Create / Modify {#files}

- `src/refmatrix/daemon.py:serve_foreground` / `cli.py:daemon_start`: when launched under launchd (env/flag) and `daemon.pid` names a live unsupervised process, send it `daemon stop`, wait, then serve; log `adopted`.
- Operate: `cd ~/github/atollogy/bdep/orderly && rmx daemon stop`; confirm launchd takes over (`runs` stops growing).

## Test Strategy (RED first) {#test-strategy}

tests/test_daemon_adopt.py.

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation check noted in the implementation summary.
- Implementation summary at `workflow/implementation_summaries/task-4.4-plan-4-daemon-resilience.md`.
- Committed on branch `task-4.4-plan-4-daemon-resilience`; merged `--no-ff` to `master`.
