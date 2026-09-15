---
gmd: "0.1"
id: bsd-pattern-guard-cannot-fire
title: "PATTERN: a guard that measures a value its caller has already ruled out — four sightings, three of them the daemon heartbeat"
tags: [bsd, pattern, daemon, hub, heartbeat, guards]
---

# PATTERN: the guard cannot fire {#root}

**Filed:** 2026-09-15 (4th sighting, plan-4 round 3)

rel: derives-from -> [[bsd-plan4-daemon-resilience-r1-6ae4b6f]]
rel: derives-from -> [[bsd-plan4-daemon-resilience-r2-e1dba80]]
rel: derives-from -> [[bsd-plan4-daemon-resilience-r3-ef4365a]]
rel: derives-from -> [[impression_bsd_same_input_guard]]

## Shape {#shape}

A remedy adds a branch that reads some state S and takes the safe path when S says "working / shutting down / same venv". The caller reaches that branch only after it has ALREADY established the opposite of S (or S is produced by the very process the branch waits on, which stops producing it first). The branch is correct in isolation, its unit test manufactures S by patching, and in production it is a straight line through the unsafe path. The tell: the test patches the input the branch reads (`heartbeat_age`, `is_alive`, a venv marker) to a constant instead of driving the CALLER into the branch. {#lead}

## Sightings {#sightings}

| Plan / round | Guard | Why it cannot fire |
|---|---|---|
| plan-1 r2 | same-venv check `A == B` from one marker | both sides read the same file; the incident state (deploy venv importing the dev tree) is A == B |
| plan-4 r1 #s-7 | heartbeat file ticked by an idle thread → "busy" | the tick touches nothing the server does; a deadlocked daemon ticks forever |
| plan-4 r2 #b-2 | heartbeat = no-op completes within `interval` on the cli pool | that is the ping; the state task 4.3 protects (busy, progressing) fails it after 60 s |
| plan-4 r3 #b-2 | `_await_shutdown`: wait while `heartbeat_age < 45` | the caller restarts only when `heartbeat_age > 60`; the daemon's first act of shutdown is `_stop_heartbeat()`; the test patches `heartbeat_age` → 0.0 |

## Rule for the next round {#rule}

For every new guard in a diff: (1) write the caller's precondition beside the callee's condition and check they can both hold; (2) name the producer of the value the guard reads and check it is still running when the guard runs; (3) reject any test that patches that value — the test drives the caller (`Watchdog._check`, not `_restart`) on a real daemon in the named state. A guard whose only green test patches its input is unverified until a probe from the caller's side reaches it.

rel: contradicts -> [[project-profile#constraints]]
