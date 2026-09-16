---
gmd: "0.1"
id: handoff-002-plans-7-10
title: "Session Handoff 002: plans 7-10, LongMemEval, brief, telemetry (archived)"
tags: [handoff, session]
metadata:
  node_type: handoff
---

# Session Handoff 002 — plans 7-10 (archived 2026-09-16) {#root}

Date: 2026-09-15 → 09-16 (session 99ba458b). Prior handoff archived at
`workflow/past_handoffs/001-plan-1-to-6-remediation_2026-09-15.md`.

**Updated after three @ch-bsd rounds and the profiling gate. Read [[#bsd]] and [[#unverified]]
before trusting anything else here.**

rel: depends-on -> [[plan-of-plans]]

## Where the work sits {#state}

**MERGED to `master` at `399d0a3`, then three BSD remediation commits → HEAD `6b6a610`.** Version
bumped **0.69.1 → 0.70.0**. Tree clean. NOT deployed — `~/refmatrix` still serves 0.69.1, and
deploying restarts the fleet, so it is a decision, not a default.

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

**Latency — the 62.9 s claim is RETRACTED.** It was measured while the daemon built a 432 MB
adjacency cache (file mtime TEN MINUTES after the measurement) and replicated three 2.4 GB catalog
slots. Profiled quiet: `build_context` warm is **0.45 s**, of which BM25 over 406,885 concepts plus
the graph walk is **0.37 s**. The retrieval core is not slow. What remains open is an unattributed
**~8.5 s** gap between `build_context` (0.45 s) and the full daemonless CLI (9.0 s), only 2.8 s of
which is CPU. **bug-033** (open — the gap has its own row now; bug-031 is the RETRACTED 62.9 s
figure and is `fixed`, so citing it here said the gap was closed — ch-bsd r4 #m-2-r4);
`workflow/measurements/longmemeval-latency.md`.

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

## @ch-bsd: three rounds, 19 → 5 → 5, all addressed {#bsd}

Reports in `workflow/bullshit/2026-09-16-00{30,50}-*` and `-0105-plan-7-10-r3-4f451c5.md`.

**r1's opening line is the durable lesson:** *"110/110 of the new tests pass at HEAD. That is the
problem: they pass and the command still dies on its first real invocation."*

- **r1 (19)** — `--gmd` crashed on every real call; `contradicted` could never fire (endpoints are
  concept `#anchor` nodes); top production brief was the word `the` (6th site of the shared-stoplist
  bug). All fixed and verified on a copy of the live read replica.
- **r2 (5)** — my fixes were BSD's r1 wording implemented verbatim without measuring. `_endpoint`
  over-permissive (45/47 emitted were BSD's own citation convention); the `--max-tokens` depth
  translation was inert. `scan` is now permanently `DEPTH_UNCONTROLLED` rather than guessed at a
  third time.
- **r3 (5)** — **the blocker: `console.print` parsed `[[note-1]]` as rich markup and deleted every
  wikilink and `rel:` edge from `--gmd` output, and `tools/gmd/lint.py` reports 0 errors on that,
  because `[[]]` is not a wikilink.** Fixed with `click.echo` at both sites. See
  [[project_bsd_three_round_arc_plans_7_10]].

BSD has NOT re-reviewed `4f451c5..6b6a610` (the r3 remediation). Plans 7/8/9/10 stay `in-progress`.

## The memory bridge did NOT run — first thing to check {#bridge}

`rmx save-state --commit` was **killed at a 400 s timeout** (exit 137) with the project daemon at
92% CPU rebuilding an index. What DID complete: the `savestate_99ba458bcae2.md` handoff memory (86
lines, well-formed). What did NOT: **the memory bridge**, so these four files are on disk and
**NOT in the store**:

- `savestate_99ba458bcae2.md`
- `feedback_causal_story_before_evidence.md`
- `feedback_green_tests_are_not_a_working_command.md`
- `project_bsd_three_round_arc_plans_7_10.md`

Verified absent: `rmx memory get feedback_causal_story_before_evidence` → "no memory matching".

SessionStart has a bridge catch-up path ([[project_memory_bridge_never_ran]]), so this should
self-heal on the next session — **but confirm it, don't assume it.** If it hasn't, run
`rmx ingest-gmd --as-memory <memory-dir>` once the daemon is idle. The daemon was NOT wedged (STAT
R, CPU advancing 33 s per 40 s wall); it was busy, and a full pytest suite was competing with it.

## UNVERIFIED — read before trusting {#unverified}

- **The full suite at HEAD `6b6a610` was still RUNNING when this handoff was written.** The last
  completed run describes a tree three commits old (`workflow/review-output/pytest-post-bsd-r2.log`:
  **6 failed, 1872 passed**). The in-flight log is `pytest-post-bsd-r3.log`.
- **That pre-r3 run had a SIXTH failure not in the master baseline:**
  `tests/test_plan4_remedy_r2.py::test_foreground_start_refuses_a_busy_daemon_without_reaping_it`.
  The other five match master exactly. **It is NOT attributed.** Candidates: my `daemon.py` changes
  (`_op_memory_brief`, `_names_for` — neither touches start/reap), the 0.70.0 version bump, or
  flakiness in a daemon-timing test. **Run it against `master` before believing any "0 added"
  claim** — that check has corrected me twice this session.

## Open decisions, NOT made {#decisions}

1. **Deploy 0.70.0?** Version is bumped; `~/refmatrix` is not updated. Fleet restart.
2. **bug-030** (probe timeout leaks onto the shared model socket, 2nd sighting): proper fix vs env
   workaround. Touches the shared model path every daemon uses. Still OPEN — it is why the
   LongMemEval dense rows do not exist.
3. **bug-032** (rerank head-truncates at 2048; 36.9% of answer-bearing turns invisible): a ranking
   change on the always-on hook path, so it wants its own plan. **Its effect may be zero** — after
   correction it can only reach `scan`/0.150, and only if the shared worker answered during the
   6,983 s run at all.
4. **helix plan-11**: Q1–Q4 tentatively approved, held at `drafting`. The profiling gate is
   satisfied and it CHANGES THE CASE — the retrieval core is 0.45 s, so the versioned store has no
   performance argument behind it. It stands on the product claim and on the two bugs it
   incidentally solves.

## Next session, in order {#next}

1. **Read `pytest-post-bsd-r3.log`** and attribute the plan-4 failure against `master`.
2. **Request `@ch-bsd` r4** over `4f451c5..6b6a610`; send it the suite log (it asked).
3. Cleanup pass, then **helix plan-11** (write task specs to move it off `drafting`), then
   benchmarks — the user's stated order.
4. Embed retry resumes via `ingest.py --skip init --skip ingest-gmd`; the 4h23m ingest is persisted
   at `/Volumes/littlebig/longmemeval/`. **Do NOT rebuild it.**

## What I got wrong, so the next session does not repeat it {#wrong}

Five times I reached a causal story ahead of the evidence, and each was caught externally, never by
re-examining my own reasoning: the storm-window latency; "the 7 test failures are contention
starvation" (an idle machine gave the same 7); "oversized bodies flood the reranker"
(`MAX_DOC_CHARS` truncates everything); bug-032 blamed on `context`'s 0.200 (`rmx context` never
constructs a reranker); and "the b-4 mutation is unclosable without a second writer" (polling the
daemon closes it). See [[feedback_causal_story_before_evidence]] and
[[feedback_green_tests_are_not_a_working_command]].

## Benchmark data, off-tree {#data}

`/Volumes/littlebig/longmemeval/` — corpus (240 MB), store (2.53 GB), results. Daemon STOPPED, store
out of the fleet. Rebuildable from `prepare.py` but that costs 4h23m.
