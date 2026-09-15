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

## Round 3 (bsd-plan5-r2, 90182c2) {#round-3}

rel: evidence-for -> [[bsd-plan5-memory-bridge-r2-90182c2]]

| Finding | Fix |
|---------|-----|
| #b-1-r2 a BOOTING daemon (pid written, socket not bound yet) was "absent" to the write control point — the in-process writer opened the live slot in the window plan 4 opens on every relaunch (the `Conflicting lock is held` boots) | `discovery.daemon_status`: a live pid whose command line names rmx/refmatrix (`pid_is_rmx`, `ps -o command=`) is BUSY with or without its socket; a gone pid or a foreign process that reused the number is absent; `socket` reported. `rmx daemon status` renders `busy … starting — socket not bound yet`. Tests: `_BootingDaemon` (seeded store, real child with `rmx daemon start` in argv, no socket) → `_store(write=True)` raises, `_sync_memory_dir` errors, slot mtime/size unchanged; a foreign-argv child and a dead pid classify absent — Q5 |
| #b-2-r2 `memory sync-disk` deleted while the p20-0 guardrail compiler of nine projects called it behind `>/dev/null 2>&1 \|\| true` | the alias is back as 15 lines that forward to `_sync_memory_dir` (the bridge) — deferral row names the removal trigger; this repo's `compile_guardrails.py` seeds via `rmx ingest-gmd --as-memory` and FAILS the compile when the seed step fails; the generated SessionStart entry is a plain `if … then python3 …; fi` (no redirect, no `\|\| true`) — Q6. The cat-herder template and the 8 fleet copies still call the alias (user's repos; handoff) |
| #s-3-r2 dead 60-line body | gone with the re-registration; `--mtype`/`--dry-run` exit 2; the "one release" comment is gone |
| #s-4-r2 unfailable "no catalog appears" | `_SilentDaemon(seeded=True)` — a real catalog; the bridge test asserts slot mtime/size unchanged |
| #m-5-r2 doubled "retry shortly"; hand docs teach sync-disk | once (`VerbBusyError` carries it); `ch-bsd.md`, `p20-0/README.md`, the compiler and `test_memory_reembed_on_edit` narratives name `ingest-gmd --as-memory` |

Also: `tests/conftest.py` resets `cli._partition_override` after every test — a memory command on one tmp store pinned the next test's bridge to the wrong partition (five `live` bridge tests looked up rows nothing wrote; found while bisecting this round). `_SilentDaemon` / `_PingOnlyDaemon` now point their pid file at a real rmx-lookalike child (`rmx_lookalike_process`), not the pytest process — bug-011.

TDD: RED `workflow/review-output/pytest-plan5-r3-red.log` (11 failed / 1 passed — the foreign-pid negative held already), GREEN `pytest-plan5-r3-green.log` (51 passed: plan5_remedy, memory_bridge, plan2_remedy), bisect `pytest-plan5-r3-bisect.log`. Mutations `pytest-plan5-r3-mutation.log`: (A) busy again requires the socket → 3 boot-window tests fail; (B) the SessionStart compile silenced again → `test_session_start_guardrail_entry_is_not_silenced` fails; (C) the seed step optional again → `test_compile_guardrails_seeds_via_the_bridge_and_fails_when_it_fails` fails.
