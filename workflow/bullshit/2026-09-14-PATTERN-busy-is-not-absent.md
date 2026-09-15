---
gmd: "0.1"
id: bsd-pattern-busy-is-not-absent
title: "PATTERN: a failed ping is read as 'no daemon' — four plans, six sites, three of them SIGKILL or open the writer slot"
tags: [bsd, pattern, daemon, busy-absent]
---

# PATTERN: busy is not absent {#root}

**Filed:** 2026-09-14 (4th sighting, plan-4 round 1)

rel: derives-from -> [[bsd-plan2-hooks-reproducible-r3-c9d75af]]
rel: derives-from -> [[bsd-plan2-hooks-reproducible-r4-d68856d]]
rel: derives-from -> [[bsd-plan3-verbs-parity-r2-209270d]]
rel: derives-from -> [[bsd-plan4-daemon-resilience-r1-6ae4b6f]]

## Shape {#shape}

A single short `ping(root)` (0.3–0.5 s, often `retries=0`) gates a decision, and the FALSE branch is written as if the daemon does not exist: open `Store()` on the active slot, print "daemon not running", skip the store in a fan-out, or — in plan 4 — fall through to `_reap_predecessor` and SIGKILL the process 3 s later. A daemon that is alive with a saturated `cli_pool` (a 19 s `memory recall`, an ingest, an index rebuild) fails exactly that ping. Observed live three times in one audit day: `ingest-status` "daemon not running" on a live pid, `memory recall` "reading the store directly" 8 s after a restart, and the refmatrix daemon reading `busy-heartbeat` on eight consecutive checks while three `sync` runs held it.

## Sites {#sites}

| Plan / round | Site | Consequence of the false branch |
|---|---|---|
| plan-2 r3 | `ingest-gmd --detach` guard, `focus summarize` bare `ping` | "not running" on a busy daemon |
| plan-2 r4 | SessionStart bridge hook | `partition_list` 10 s × 3 behind the writer lock |
| plan-3 r2 | `verbs._call`, `federated_locate`, four CLI twins matching `"daemon not running" in str(e)` | `memory add` WRITES through a direct `Store()` under a held catalog |
| plan-4 r1 | `Daemon._adopt_unsupervised` (`ping(timeout=0.5, retries=0)`) | busy predecessor not adopted → `_reap_predecessor` SIGTERM/3 s/SIGKILL (probe: dead in 3.54 s) |
| plan-4 r1 | `rmx repair-index --entities` offline branch | direct writer open on the active slot under a busy daemon |
| plan-3 r4 | `handoff.compose_recall_state` (`rmx_recall_state`, bare `ping` at handoff.py:494) | resume report says `stale pid N` + anomaly "socket unreachable (stale)" on a busy daemon; the CLI's `busy pid` render branch (0.41.0) has no producer |

## Rule {#rule}

Any diff that adds a bare `ping(` gate or a `"daemon not running" in str(e)` match is BULLSHIT on sight. The classifier is `discovery.daemon_status` (typed up / busy / absent, 80021a4) — and since plan 4 the daemon's own `heartbeat_age(root)` is a second, socket-free liveness signal that the same plan then ignored in its own adoption path. Probe: the pid-file + listening-socket simulation, or SIGSTOP a spawned tmp daemon, and watch what the false branch does to it.

rel: contradicts -> [[project-profile#constraints]]
rel: reinforces -> [[bsd-impressions#imp-busy-absent-verb-layer]]
