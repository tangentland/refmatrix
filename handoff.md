---
gmd: "0.1"
id: handoff
title: "Session Handoff for refmatrix"
tags: [handoff, session]
metadata:
  node_type: handoff
---

# Session Handoff for refmatrix {#root}

Date: 2026-09-16 (session 96d2fc48). Prior handoff archived at
`workflow/past_handoffs/002-plans-7-10-longmemeval-brief-telemetry_2026-09-16.md`.

rel: depends-on -> [[plan-of-plans]]

## Where the work sits {#state}

**`master` at `3c7b470`, tree clean, 27 commits ahead of `origin/main` (`e815191`, confirmed by
`git fetch`, not a cached ref).** Version **0.71.0**, unchanged — nothing here is deployed;
`~/refmatrix` still serves the pre-plan-12 tree.

One task: *fix the bugs*. Every row in `workflow/bug_registry.md` that read `open` or `recurring`
is now `fixed`, via **plan-12** (`workflow/plans/plan-12-open-bug-remediation.md`, six task specs),
then five rounds of `@ch-bsd` ending **CLEAN**.

## The six bugs {#bugs}

| bug | what shipped |
|---|---|
| **bug-037** | `tools/pyc_guard.py` + a `pytest_sessionstart` guard: all `src/` bytecode is recompiled as PEP 552 `checked-hash` before any test runs, so validation is by source hash. The incident replays in a test that fails loud if it stops reproducing. |
| **bug-039** | `derive_stamps` (both DDLs) + `Store.stamp_derive` / `derive_status`; stamped by `ingest_path` and `ingest_gmd_paths`; surfaced on `_store_health`, `_op_derive_status` and `rmx daemon status`. An unstamped partition holding tracked files reads STALE, not unknown. |
| **bug-024** (G14) | `Daemon._maybe_adopt_shared` on the existing tick re-probes the shared socket, swaps under `_worker_lock`, closes the private worker, backs off to 1800 s. Split fleet is visible via `worker_kinds()` → hub row → `rmx hub queues`. |
| **bug-025** (G13) + **bug-019** | The rerank worker reports a seconds-per-doc EMA, the hub adds `queue_depth`, `estimate_rerank_s` is the one place the arithmetic lives, `RemoteReranker` holds a deadline and raises `RerankSkipped` with the numbers. The `rerank` frame carries the deadline and the worker drops it at dequeue. |
| **bug-032** | `reranker.window_doc`: half the budget on the head, half on a query-anchored window. **541 → 672** covered of 896 answer-bearing turns at 2048; byte-identical head truncation below 1024. |
| **bug-033** → **bug-040** | `RMX_TIME_PHASES=1` phase splits; the instrument found a real defect — the grep floor was `rg`-ing **`$HOME`** for memory-only stores (15.09 s → timeout → zero hits → swallowed). **15.13 s → 0.09 s.** The residual 8.5 s is cold I/O on an SD-card volume (94.7 MB/s, 432 MB adjacency cache). |

## Done since the first draft of this handoff {#closed}

All three items the user approved are complete:

1. **Deployed 0.72.0.** `~/refmatrix` ff-pulled to `66142c1`, `rmx daemon restart --relaunch`
   verified pid + version against the deploy code path, the hub was restarted onto 0.72.0 (its
   model workers must run this code for bug-025), and `rmx hub relaunch-fleet` took all 8 stores to
   0.72.0. No orphan pileup on :7777.
2. **Pushed.** `origin/main` is `66142c1`; 0 ahead at the time of the push.
3. **bug-025 acceptance MET.** Four runs of the exact deployed hook argv, two windows two and a
   half minutes apart, load 3.9-4.5: **20 of 20 rows reranked**, 4.77-5.15 s, against **0 of 5**
   with `rerank failed (TimeoutError)` four hours earlier. `workflow/measurements/
   rerank-cost-budget-0916.md#acceptance`. Plan-12 is `completed`.

bug-039's detector is live and behaved exactly as predicted for landing day: every store reads
`derive-unstamped` and the hub row is **cold**, so the alert did not flood.

## What is NOT done, and why {#open}

Nothing is outstanding from this session's asks. Both bugs raised after plan-12 are closed and
deployed:

- **bug-041 FIXED (0.72.1), proven live.** The 0.72.1 daemon stops in **1 second** with no drain
  timeout and no skipped flush; the whole restart is 4 s against 29-32 s. Note the trap for anyone
  re-checking: the FIRST restart after a deploy is performed by the OLD daemon, which still prints
  the old lines — a shutdown fix can only be observed by restarting a process that already carries
  it. The 431,809 -> 422,127 index-row delta that looked like lost work was ordinary churn: four
  boots today read 431809 / 422127 / 431666 / 431669, moving both ways with purge and re-derive.
- **bug-042 FIXED (0.72.1).** `MEMORY.md` is generated under a hard cap: 234 -> 193 lines, 257
  memories all accounted for (192 listed, 65 collapsed, 0 unaccounted), `--check` in sync on the
  DEPLOYED build. Wired into `handoff._ss_update_index`, so save-state now caps the index it grows.

- **bug-043 FIXED (0.72.2).** The `global:queues` alert re-published the whole fleet snapshot every
  30 minutes with every row clean, because the gate read `hot or pending_refine` and one bus-test
  candidate from 2026-09-14 (body: the string `hi`) had been pending for two days. A hot row still
  alerts every tick; a pending candidate alerts once, on arrival; a quiet tick prunes drained ids.
  The stale candidate was rejected after `rmx refine show` confirmed what it was.

Live confirmation of the plan-12 gate design, visible in `rmx hub queues` right now: `refmatrix`
reads **`derive-drift@0.72.1`** — its graph was stamped by 0.72.1 while 0.72.2 runs, but 0.72.2
changed `hub.py`, not `ingest.py` / `ingest_gmd.py` / `store.py`, so `behind_code` is False and the
row is carried COLD instead of alerting. That is exactly the version-vs-distance distinction ch-bsd
forced in r2/r4, working on the real fleet.

The one open item is a judgement call rather than a defect: the memory-index and shutdown work
landed AFTER `@ch-bsd`'s CLEAN range (`c92274b..34aeddf`) and has had no adversarial audit — 22
tests and six killing mutations, but no BSD round.

## Quality gates {#gates}

| gate | state |
|---|---|
| Full suite | **2026 passed, 0 failed, 850 s** at `ca884b2` (`workflow/review-output/pytest-plan-12-r5.log`) |
| Suite per round | 2011 → 2016 → 2021 → 2025 → 2026, zero failures throughout |
| GMD lint | 0 errors, 14 pre-existing warnings |
| `rmx install-hooks --check` | in sync |
| `@ch-bsd` | **CLEAN**, 0 findings at `34aeddf`; 22 findings across five rounds, all closed |

The contaminated first run is preserved as `pytest-plan-12-CONTAMINATED.log` rather than replaced —
`@ch-bsd`'s mutation harness edited `src/` while it ran, and a log that describes no tree is worse
than no log.

## What the audit changed, not just confirmed {#audit}

Worth reading before trusting any number in this session:

- Both round-1 blockers were **the same defect in two instruments**: a number sampled outside the
  interval it claimed to describe. `queue_depth` was read after `_handle`'s `finally` drained it;
  the phase report labelled each interval with the phase that ended at its START.
- My round-1 alert gate fired on version inequality and would have turned **all 8 stores
  permanently hot within two days** (34 version bumps in ten days). It is now a content hash of
  `ingest.py` / `ingest_gmd.py` / `store.py`, stamped at derive time.
- That hash's cache then reproduced **bug-037's own shape** — `(mtime, size)` is not a content
  identity — inside bug-039's detector. Key is now a 5-tuple with `ctime_ns` and `ino`.
- One published A/B number was wrong: the 700-char split arm is **338, not 500** (the 0.7 arm's
  number on the 0.5 row), under a comment reading "Measured, not chosen". Caught by re-running the
  committed harness, which is the argument for committing harnesses.

## Next session {#next}

1. Read `workflow/bullshit/2026-09-16-1146-plan-12-r3-r5-close-34aeddf.md` (CLEAN) and
   `workflow/bug_registry.md` bug-041.
2. Decide the deploy. If deploying: `git -C ~/refmatrix pull --ff-only origin master` →
   `rmx daemon restart --relaunch` → then run bug-025's acceptance and record it.
3. Settle bug-041 with `rmx stats` + `replica audit` on an idle machine.
4. plan-12 flips to `completed` only after (2) and (3).
