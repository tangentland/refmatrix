---
gmd: "0.1"
id: task-4.2-plan-4-daemon-resilience
title: "Task 4.2: repair-index --entities, in-band and at boot"
tags: [task, plan-4]
metadata:
  node_type: task
  status: pending
  plan: plan-4-daemon-resilience
---

# Task 4.2: repair-index --entities, in-band and at boot {#root}

> Plan: [[plan-4-daemon-resilience]]
> Status: Pending
> Depends on: 4.1

rel: part-of -> [[plan-4-daemon-resilience]]

## Requirements {#requirements}

- A tmp store whose entities PK index is corrupted (simulate: insert rows with duplicate ids into `entities_new` through a raw connection → real dup → RepairAbort; and a clean table → rebuild succeeds and delete+reinsert probes pass).
- Boot with a marker → log line `repaired entities` and marker removed.

## Files to Create / Modify {#files}

- `src/refmatrix/store.py:rebuild_entities_indexes() -> dict` (CREATE new/INSERT/DROP/RENAME/5 idx/CHECKPOINT; raises `RepairAbort` on real dup groups).
- `daemon._op_repair_entities`; `cli.py:repair_index --entities`; `serve_forever` runs the rebuild when `repair.needed` names `entities`, logs the report, clears the marker; `daemon status` prints `repair pending: <table>` when the marker exists.

## Test Strategy (RED first) {#test-strategy}

tests/test_repair_entities.py.

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation check noted in the implementation summary.
- Implementation summary at `workflow/implementation_summaries/task-4.2-plan-4-daemon-resilience.md`.
- Committed on branch `task-4.2-plan-4-daemon-resilience`; merged `--no-ff` to `master`.
