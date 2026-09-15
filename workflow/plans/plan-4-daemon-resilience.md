---
gmd: "0.1"
id: plan-4-daemon-resilience
title: "A read never kills the daemon; index corruption is repaired in-band; supervisors never SIGKILL a working daemon"
tags: [plan, remediation, bsd]
metadata:
  node_type: plan
  status: approved
  created: 2026-09-14
  bsd_findings: "#bs-3, incident 2026-09-14, G3, G9"
---

# Proposed Plan: A read never kills the daemon; index corruption is repaired in-band; supervisors never SIGKILL a working daemon {#root}

**Date:** 2026-09-14
**Status:** Accepted
**Location:** `workflow/plans/plan-4-daemon-resilience.md` — permanent home; stage is `metadata.status`.

rel: evidence-for -> [[bsd-0661-e2e-memory-bridge]]
rel: depends-on -> [[constitution]]
rel: implements -> [[tdd-governance]]
rel: specifies -> [[task-4.1-plan-4-daemon-resilience]]
rel: specifies -> [[task-4.2-plan-4-daemon-resilience]]
rel: specifies -> [[task-4.3-plan-4-daemon-resilience]]
rel: specifies -> [[task-4.4-plan-4-daemon-resilience]]

## Context {#context}

BSD #bs-3 + the 2026-09-14 incident: `_op_learn_from_grep` (fed by every `rmx grep` miss, including the PreToolUse rewrite)
upserts entities unguarded; with a drifted entities PK/UNIQUE ART index the daemon fast-exits, launchd respawns it, the next grep
kills it again (39 runs). Boot-time repair rebuilds only `idx_entity_links_lk_concept`. The corruption itself came from the hub
watchdog `kickstart -k` (SIGKILL) on a daemon that was merely reconnecting to an idle-evicted model worker. Separately, the
orderly launchd service spawned 11,251 times behind a manual unsupervised daemon.

## Proposed Approach {#proposed-approach}

1. Read surfaces degrade: `_op_learn_from_grep` catches DuckDB fatals, logs `learn skipped: store invalid`, returns
   `{"added": 0, "skipped": "store-invalid"}`, and sets `d._repair_needed = "entities"` + writes `.refmatrix/repair.needed`.
   Fast-exit remains for write ops.
2. `rmx repair-index --entities` (in-band, daemon-routed op `repair_entities`) = the offline recipe: rebuild `entities` from
   itself with fresh PK/UNIQUE + 5 secondary indexes, abort on real dup groups, CHECKPOINT; boot runs it when `repair.needed`
   exists (before serving) and clears the marker; `daemon status` shows `repair pending`.
3. Watchdog: a daemon heartbeat file (`.refmatrix/heartbeat`, touched every 5 s by a thread that holds no locks) lets
   `hub.Watchdog._check` classify `dead` (pid gone or heartbeat > 60 s stale) vs `busy` (pid alive, heartbeat fresh, ping slow);
   busy never restarts; `_restart` sends graceful `daemon stop` first and only `kickstart -k` after `RMX_HUB_KILL_GRACE_S` (30).
   The model-worker reconnect path becomes non-blocking for the ping responder.
4. `rmx daemon start` under a supervisor that finds an unsupervised live daemon on the same root: stop it gracefully, adopt the
   root, log `adopted unsupervised daemon pid=…` — no permanent exit-1 loop. Apply to orderly.

## Open Questions {#open-questions}

### Q1: Q1 Repair in the daemon process or a lean subprocess? {#q1}
**Status:** RESOLVED

**Decision:** In the daemon at boot BEFORE the store is opened for serving (single writer, no contention); the 0.3 s rebuild on 75k rows makes it cheap.
**Rationale:** see Decisions Log.

### Q2: Q2 Heartbeat file vs richer ping? {#q2}
**Status:** RESOLVED

**Decision:** File. A ping that must go through the socket accept loop is exactly what blocks when the daemon is busy.
**Rationale:** see Decisions Log.

## Decisions Log {#decisions-log}

| # | Question | Decision | Date |
|---|----------|----------|------|
| Q1 | Q1 Repair in the daemon process or a lean subprocess? | In the daemon at boot BEFORE the store is opened for serving (single writer, no contention); the 0.3 s rebuild on 75k rows makes it cheap. | 2026-09-14 |
| Q2 | Q2 Heartbeat file vs richer ping? | File. A ping that must go through the socket accept loop is exactly what blocks when the daemon is busy. | 2026-09-14 |

## Task Breakdown {#task-breakdown}

| Task ID | Title | Depends On |
|---------|-------|------------|
| 4.1 | learn_from_grep never fast-exits | — |
| 4.2 | repair-index --entities, in-band and at boot | 4.1 |
| 4.3 | Heartbeat + watchdog grace + graceful restart | — |
| 4.4 | Supervised start adopts an unsupervised daemon; fix orderly | — |

## Execution contract {#execution}

TDD per [[tdd-governance]]: RED test recorded to `workflow/review-output/` before GREEN; mutation check on every new test;
implementation summary per task under `workflow/implementation_summaries/`; then `@ch-bsd` over the plan's commit range —
remedy and re-review until the verdict is CLEAN; then the plan's `metadata.status` → `completed`.
