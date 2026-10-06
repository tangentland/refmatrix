---
gmd: "0.1"
id: handoff
title: "Session Handoff for refmatrix"
tags: [handoff, session]
metadata:
  node_type: handoff
---

# Session Handoff for refmatrix {#root}

Date: 2026-10-06 (session b92019bc). Prior handoff archived at
`workflow/past_handoffs/007-plan14-grep-measured-plan15-derive_2026-10-06.md`.

rel: supersedes -> [[handoff-007-plan14-grep-measured-plan15-derive]]

## State {#state}

`master` = **b32bc35**, clean tree. **Pushed:** `origin/main` = `cb35e21`
(41 commits, the first push in this repo's history of the backlog) — the four
merges above it are NOT pushed yet. `~/claude_tools/gmd` pushed too
(`a84af28..8a65aa2`). Deploy `~/refmatrix` = **cb35e21 / 0.75.0**, fleet 8/8 +
hub on 0.75.0 — plan-15 was deployed before this session opened, so the prior
handoff's "Next #1" was already done. `rmx install-hooks --check` in sync.
{#state-body}

**Not deployed:** everything this session landed. No version bump taken — the
four merges sit on `master` only. {#state-deploy}

## What this session did {#did}

One ask — "proceed with the task and the 3 bugs" — closed task 15.4 (finishing
plan 15), the three named bugs, and one more the first full suite surfaced.
{#did-lead}

- **Task 15.4 / plan 15 COMPLETE.** `sessions`, `embed` and `pagerank` now stamp
  at the end of a successful pass (`_op_pagerank` inside its write lock; embed
  only when the batch loop ran to completion, so a `--max-batches` run claims
  nothing; sessions on both index routes and on all-cards-unchanged, never under
  `--no-index`). Both CLI-owned passes route through a new daemon op,
  `derive_stamp`. `derive_status()` gained `partition_kind`, `expected_passes`
  and `missing_passes`, expected per partition KIND
  (`_DERIVE_EXPECTED_PASSES`), and missing is NOT an alert — it sets neither
  `stale` nor `behind_code`, so release day does not turn the fleet hot.
  22 tests, 17 RED first, 8 mutations killed.
- **bug-072 (found here).** The first full suite since plan-15 landed showed 5
  failures, not the 3 the prior handoff recorded. Two were plan-12 guard tests
  that had been failing since 15.1 gave `derive_code_hash` a `pass_name`: their
  zero-arg doubles raised, `_store_health` swallowed it into `derive_error`, and
  the whole `derive` key vanished from health. **Nothing in `src/` read
  `derive_error`** — a store whose derive DETECTOR is broken produced a hub row
  identical to a clean one. `hub._gather_queues` now carries it.
- **bug-069.** Two causes, and the registry's own question resolved as "the test
  asserted something r8 never shipped". `_locate_one_project` was the THIRD
  caller of `_replica_bundle`; r8 fixed the two its finding quoted and left this
  one with a bare `except: pass` on the filename leg and no `on_error` on the
  keyword leg. It returns `(hits, reasons)` now and the fan-out names each one.
  The other two failures were stale test doubles: r8 added `on_error=` and two
  2-positional lambdas rejected it.
- **bug-065.** The memory bridge wrote `kind=memory` rows with no vectors, so
  every save-state produced durable, unreachable memories.
  `ingest_gmd.drain_memory_vectors` drains at the BRIDGE's completion point —
  the daemon's `_run_ingest_gmd_body` (both the sync op and the detached job)
  and `_ingest_gmd_sync`'s in-process branch. The acceptance is the RECALL the
  row demanded: a phrase unique to a memory is ranked first, on a spawned daemon
  with the real embedder.
- **bug-070.** The canonical grep predicate is a SPELLING bridge, not a family.
  Four arms measured over one store; the obvious fix (plain equality) destroyed
  the bridge and the measurement is what said so. Report:
  `docs/measurements/grep-canonical-breadth.md`.

## The correction worth carrying {#correction}

bug-065's first cut put the drain in `finalize_save_state`. The user asked "so
as-memory now implies embed - yes?" and the honest answer was **no** — `rmx
ingest-gmd --as-memory`, `rmx memory sync-disk` and the SessionStart `--detach`
catch-up hook all kept writing vectorless rows. The rule belonged to the WRITE,
not to one of its callers, and it moved down a layer. A fix placed at a caller
is a fix for that caller. {#correction-body}

rel: reinforces -> [[feedback_main_path_must_exercise_core_mechanisms]]

## Next {#next}

1. **Version bump + deploy** — nothing from this session is live. Four merges on
   `master`; `rmx derive log` on the live store will only show the new passes'
   history after a deploy runs them, and bug-065's drain only protects
   save-states taken by the DEPLOYED build.
2. **Push the four merges** — `origin/main` is at `cb35e21`, four merges behind.
3. **`@ch-bsd` over this range** — plans 14 and 15 have had NO audit pass, and
   neither has anything in this session. `workflow/bullshit/last_run.log`'s
   newest entry is 2026-10-01, three DIRTY runs.
4. **bug-070's other half** — `ERROR` and `timeout` still draw 74/26 and 26/6
   rows through `c.name ILIKE '%pattern%'`, the pre-bug-067 contract. The
   registry's cap-the-distinct-concepts candidate applies to THAT predicate and
   is still an open decision with its own trade.
5. **The three plan-12-era DIRTY rounds** (plans 2/4/6 findings) remain open in
   `workflow/plan-of-plans.md`.

## Open, not forgotten {#open}

- `rmx hub launchctl status` reports plist drift on the hub's env `PATH` —
  pre-existing, untouched.
- `RMXGREP_MODE=rich` lives in `.claude/settings.local.json`; bug-066's config
  half is still the user's call.
- `docs/measurements/` vs `workflow/measurements/` — this session added to
  `docs/`, consistent with the one already there; the split still wants a
  decision.
- `eval/production/grep_evidence_breadth.py` is a new instrument with no test.
  It is eval code, not `src/`, but it is now the thing a future retune of the
  name predicate would be judged by.

## Gates {#gates}

- Full suite: see `workflow/review-output/pytest-session-full.log` (the run over
  all four merges).
- GMD lint: 0 errors / 543 docs.
- `rmx install-hooks --check`: in sync.
- Mutations: 8 (task 15.4) + 2 (bug-069) + 3 (bug-065) + 4 (bug-070), all killed.
  One mutation pair in the bug-070 loop reported a pass it never ran, because
  `git checkout --` restored HEAD over an uncommitted arm — re-run after
  committing.

rel: realizes -> [[feedback_save_state_means_handoff]]
rel: related-to -> [[refmatrix/grep-canonical-breadth]]
