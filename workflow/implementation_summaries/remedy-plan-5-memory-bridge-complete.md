---
gmd: "0.1"
id: impl-remedy-plan-5-memory-bridge-complete
title: "Plan-5 remediation after ch-bsd plan-5 r1 (1eea8ed): the bridge never writes around a busy daemon"
tags: [implementation-summary, plan-5, remediation]
metadata:
  node_type: implementation-summary
  plan: plan-5-memory-bridge-complete
---

# Plan-5 remediation (round 1) {#root}

rel: implements -> [[plan-5-memory-bridge-complete]]
rel: evidence-for -> [[bsd-plan5-memory-bridge-1eea8ed]]

| Finding | Fix |
|---------|-----|
| #b-1 bridge opened the writer slot under a busy daemon (live: 4 runs, ART corruption, fast-exit) | `_store(write=True)` — THE write control point — and `_ingest_gmd_sync` classify through `verbs.require_daemon`: busy REFUSES with a named error (the next save-state / SessionStart retries), only ABSENT opens the slot in-process; `test_bridge_never_opens_the_slot_under_a_busy_daemon` on a real silent socket asserts no catalog file appears through the bridge or `_store()` — plan Q3 |
| #b-2 `MEMORY.md` became a curated memory | `MEMORY_INDEX_FILES` skipped and COUNTED (`skipped_index`), asserted; the live row `MEMORY` is forgotten after deploy — Q4 |
| #s-3 any finished job over the dir counted as the bridge | coverage requires the job's `as_memory` and the same partition; the resume gate looks at the kind THIS run produces (`skip_lookup_kinds` by mode), so a memory bridge after a doc ingest of the same files creates the memory rows — `test_bridge_does_not_take_a_non_memory_job_as_its_report` |
| #s-4 dead `--mtype`, stale docstring; #s-6 unanchored "one release" | `memory sync-disk` deleted; Q2 revised; docs point at `ingest-gmd --as-memory` |
| #s-5 counter that could not move | `test_strict_ingest_counts_non_gmd_files` (strict mode counts 1); the redundant daemon `lenient=` kwarg removed — `ingest_gmd_paths` decides once |
| #s-8 `waited`/`waited_job` unread | save-state prints `waited for ingest job <id>` and the skipped index files |
| #m-7 report scraping | `IngestStats.as_dict()` → daemon result `stats` → `_sync_memory_dir` (`_bridge_stats`); `_parse_bridge_report` deleted |
| #m-9 bookkeeping | `docs/architecture/todo.md` G1–G6 rows reflect the plans that shipped them; `cli._root` registry row lists every file that patches it; the live requirement is now the counters + `skipped_index: 1 (MEMORY.md)` on the live bridge run after deploy |

TDD: RED `workflow/review-output/pytest-plan5-r1-red.log` (6 failed), GREEN `pytest-plan5-r1-green.log` (57 passed: bridge, widen, save-state, GMD ingest suites). Mutations `pytest-plan5-r1-mutations.log`: (A) letting busy fall through to the in-process writer fails the silent-socket bridge test; (B) ingesting `MEMORY.md` again fails the bridge test.
