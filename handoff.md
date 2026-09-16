---
gmd: "0.1"
id: handoff
title: "Session Handoff for refmatrix"
tags: [handoff, session]
metadata:
  node_type: handoff
---

# Session Handoff for refmatrix {#root}

Date: 2026-09-15 → 09-16 (session 99ba458b). Prior handoff archived at
`workflow/past_handoffs/001-plan-1-to-6-remediation_2026-09-15.md`.

rel: depends-on -> [[plan-of-plans]]

## Where the work sits {#state}

**Branch `plan-7-8-authoring`, 15 commits, NOT merged to master.** That is a deviation from the
one-branch-per-task rule and is the first thing the next session should resolve.

Three new plans authored, specced, and mostly executed: **plan-7** (LongMemEval), **plan-8**
(`rmx memory brief`), **plan-9** (context-cost telemetry), **plan-10** (injection dedup — closed as
a negative result).

## Shipped {#shipped}

- **`rmx memory brief`** (plan 8) — four deterministic detectors over the memory graph
  (`corroborated`, `singleton`, `contradicted`, `orphan-concept`). Verb → daemon op → CLI → MCP.
  GMD index round-trips. 40 tests, mutation-checked.
- **Context-cost telemetry** (plan 9) — `query.log` carries `invocation`; `cli.log` carries
  `out_bytes` counted once around `sys.stdout` in `cli_entry`; `rmx telemetry --context` reports
  per-command bytes and the per-prompt hook budget. Live: `grep` 13,749 B mean (dominant by an
  order of magnitude), hook budget p50 13,752 B.
- **LongMemEval harness** — `eval/production/longmemeval/`, 19,829 session docs, 406,885 concepts.

## The two numbers that matter {#numbers}

**Latency, and it is the session's most consequential finding.** Daemon warm:
`rmx context` **62.9 s**, `rmx scan-prompt` **75.9 s** per query at 19,829 docs. agentmemory
publishes 14 ms p50. `scan-prompt` is the always-on UserPromptSubmit hook and cannot run per-prompt
at this scale. No cause claimed — no profile taken. `workflow/measurements/longmemeval-latency.md`.

**Recall, and it is SATURATED.** `context` MRR@20 0.679 / R@5 0.605 — with hit@5 exactly equal to
the depth-50 recall ceiling. It measures retrieval DEPTH, not ranking. Do not quote it against
agentmemory's 95.2%. `eval/production/longmemeval/REPORT.md`.

Per-type, two uncomfortable readings: preference retrieval nearly fails (0.200), and multi-session
(0.567) + temporal-reasoning (0.487) land BELOW the single-session types — inverted from what the
conceptual-memory thesis predicts. Qualifier: this corpus has no structural edges at all.

## Three negative results, each cheaper than the thing it prevented {#negatives}

- **`brief/unanswered`** — pre-registered confound gate FAILED. `query.log` records what the agent
  grepped for, not what the corpus was asked. Detector not built.
  `workflow/measurements/brief-unanswered-confound.md`.
- **Plan 10 injection dedup** — median consecutive scan-prompt overlap **0.000** against a
  pre-registered 0.40. Ledger, degraded rendering, PreCompact wiring and a permanent correctness
  hazard all avoided. Run was 187 pairs vs a 200 minimum and self-reported UNDERPOWERED; that
  limitation is kept attached. `workflow/measurements/injection-overlap.md`.
- **Latency** — nobody had measured retrieval COST at scale on the path users run.

## Bugs found by doing the work {#bugs}

- **bug-029 (FIXED)** — `.venv-eval/bin/rmx` called `refmatrix.cli:main`, bypassing `cli_entry`.
  The dev binary had NEVER written `cli.log`, so all dev-tree verification of CLI telemetry and the
  fork-safety re-exec was silently invalid. Script rewritten (not a pip reinstall — mixed-ABI tree).
- **bug-030 (OPEN)** — `WorkerClient.call(timeout=X)` mutates the PERSISTENT socket timeout and
  never restores it, so a bounded probe leaks its budget onto the next call. Killed the LongMemEval
  embed pass after a successful 4h23m ingest. **2nd sighting** of
  `impression_bsd_probe_timeout_leak`.

## Quality gates {#gates}

| gate | state |
|---|---|
| Full suite (idle machine) | **1833 passed, 7 failed, 940 s** |
| of those 7 | **5 fail identically on master**; 2 were mine and are FIXED |
| `rmx install-hooks --check` | in sync |
| GMD lint | 61 errors — unchanged all session, all pre-existing |

The 5 pre-existing failures are `test_bigop_nonblocking::test_pause_blocks_restart_of_a_dead_daemon`,
`test_daemon_liveness::test_daemon_status_reports_busy_for_a_live_unresponsive_process`,
`test_graph_landing::test_context_op_honors_partition_under_ambient_drift` (the perma-red named in
plan-6 task 6.4), `test_hub::test_watchdog_restarts_down_daemon_when_auto`, and
`test_memory_recall_exclude_mtype::test_scope_both_filters_global_rows`. Four are daemon/hub/
liveness — the area plan-4 is still in-progress on. **Not investigated this session.**

## Open decisions, deliberately NOT made {#decisions}

1. **Depth-200 LongMemEval rerun (~4 h) vs profiling the 63 s.** The recall number is depth-bound;
   the latency number is the one that changes what rmx IS.
2. **bug-030: proper fix vs env workaround.** The fix touches the shared model path every daemon
   uses.
3. **Merge the 15 commits before or after `@ch-bsd`.**

## Next session {#next}

1. Resolve the unmerged branch.
2. `@ch-bsd` over plans 7–10 (none has had a pass).
3. The three decisions above.
4. Embed retry resumes via `ingest.py --skip init --skip ingest-gmd` — the 4h23m ingest is
   persisted at `/Volumes/littlebig/longmemeval/`; do NOT rebuild it.

## Benchmark data, off-tree {#data}

`/Volumes/littlebig/longmemeval/` — corpus (240 MB), store (2.53 GB), results. Daemon STOPPED, store
out of the fleet. Rebuildable from `prepare.py` but that costs 4h23m.
