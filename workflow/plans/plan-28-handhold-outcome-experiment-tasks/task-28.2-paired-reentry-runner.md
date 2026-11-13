---
gmd: "0.1"
id: task-28.2-paired-reentry-runner
title: "Task 28.2: the paired re-entry runner: real handoffs resumed by fresh agents on littlebig clones under cells A+dedupe, B and C, after a new session and after /clear, with no knowledge from after the task's start"
tags: [task, plan-28, experiment, paired, clones, littlebig, handoff, hooks]
metadata:
  node_type: task
  status: drafting
  plan: plan-28-handhold-outcome-experiment
  created: 2026-11-13
  updated: 2026-11-13
---

# Task 28.2: the paired re-entry runner {#root}

> Plan: [[plan-28-handhold-outcome-experiment]]
> Status: Drafting (spec wave 2026-11-13, G17).
> Depends on: [[task-28.1-session-arms-and-push-switch]] (the paired-leg arm record).
> Builds `eval/production/handhold/`. R0 is a probe whose answers can change R2's mechanics. A
> changed mechanic is a revision of this spec before 28.4 freezes anything.

rel: part-of -> [[plan-28-handhold-outcome-experiment]]
rel: depends-on -> [[task-28.1-session-arms-and-push-switch]]
rel: derives-from -> [[exploration-handhold-outcome-experiment#assignment]]
rel: derives-from -> [[plan-review-2026-11-13#lead]]
rel: reinforces -> [[feedback_isolate_work_in_littlebig_clones]]
rel: reinforces -> [[feedback_no_raw_prompts_in_public_repo]]
rel: reinforces -> [[feedback_never_search_from_root]]

## Why {#why}

The primary outcome is orientation cost at a re-entry, on the paired leg (Q3; L20 adds the
new-session trigger beside `/clear`). Session-level randomisation dilutes continuity, so this leg
holds the task and the starting commit fixed and varies only the cell and the trigger. Three
hazards shape it:
- **Leakage.** Today's memories record how many past tasks ended. A fresh agent that sees them
  is not resuming; it is reading the answer.
- **Fleet pollution.** A clone's store must never register with the hub or launchd.
- **Arm pinning.** `draw` is pure, so a run is pinned by choosing its session id, not by a
  flag.
{#why-body}

## Requirements {#requirements}

1. **R0 Probe first (a measurement; nothing is built on an unproven mechanic).** On one
   synthetic task in a tmp git repo on littlebig, establish and record each item. {#r0}
   - (a) `claude --session-id <uuid>` makes the hooks see that id, so the runner can pick an id
     whose `arms.draw(…, root=clone)` gives the wanted cell (rejection sampling over uuid4).
   - (b) A `/clear` re-entry can be driven unattended, either through a `screen` session
     (`stuff` the text, then a separate `\r`) or headless, and fires SessionStart with source
     `clear`. A fresh process fires source `startup`.
   - (c) Arm C's profile turns off every rmx hook for the session, project and user level
     alike. The probe checks a generated clone settings file carrying `disableAllHooks: true`,
     or the reap path of `rmx install-hooks` plus the user-level hooks. With no
     `.refmatrix/PRIMER.md` generated in a C clone, CLAUDE.md's import resolves to nothing,
     and Claude Code starts cleanly. The MCP server stays (pull).
   - (d) The memory dir that Claude Code reads for a clone path
     (`~/.claude/projects/<clone-slug>/memory`) can be populated by the runner and is bridged
     into the clone's store.
   - (e) A clone's store and daemon: the daemon runs unsupervised, appears in no hub registry
     and no launchd label, and stops at teardown (`rmx daemon status`, `rmx hub status`, the
     launchd domain all read before and after).
   - (f) The cost of one run (tokens, wall time), for 28.4's calibration.

   A "no" on (a) to (e) stops the task. The mechanic is re-specified, and nothing is worked
   around.
2. **R1 The task set.** Candidates are real handoffs: refmatrix's `workflow/past_handoffs/` and
   save-states, and cliquedb's, read through a local read-only clone of the repo. Each task
   records:
   - its start sha (the commit the handoff was written at);
   - its handoff and save-state as of that sha;
   - its reference continuation (the files changed by the next session's commits, from git);
   - its resume prompt, ONE fixed template for all tasks.

   It is excluded when its continuation deployed, touched a live store or a fleet repo, or
   needed the user mid-task. The draw (seed, date range, count per project) and the task-id
   list's sha256 are frozen by 28.4. K calibration tasks are drawn apart and never reused.
   {#r1}
3. **R2 One run.** For each task × paired cell (`A+dedupe`, `B`, `C`; P-6) × trigger: {#r2}
   - **Clone.** A new clone at `/Volumes/littlebig/<project>-handhold-<run-id>`, checked out at
     the start sha, with its git remote removed (nothing can be pushed).
   - **Store.** Built by the deployed `rmx` ingest under the clone, as R0 (e) established.
   - **Memory snapshot (no leakage).** The clone's memory dir gets only the project's memory
     files whose `created` AND `updated` are at or before the start sha's commit time, and only
     save-states and handoffs from before it. Each excluded file is counted, by reason. Arms A
     and B bridge them. Arm C gets the same dir, because Claude Code's own memory index is not a
     refmatrix handhold.
   - **Cell.** `A+dedupe` and `B` take a session id whose draw lands in the cell, under the
     paired-leg record (28.1 R1). `C` gets the generated bare profile from R0 (c).
   - **Trigger.** For `new-session`, a fresh process gets the resume prompt. For `clear`, a
     fresh process gets ONE fixed warm-up prompt (template frozen by 28.4), then `/clear`, then
     the resume prompt.
   - **Stop.** At the endpoint 28.3 detects, or at a cap of tool calls and wall time frozen by
     28.4. A run stopped at the cap is `censored`.
   - **Archive.** The transcript (the parent and every subagent file) and the clone store's
     telemetry are copied to a LOCAL archive outside the repo
     (`~/.refmatrix/measurements/plan-28/paired/<run-id>/`). Only the run id, the cell, the
     trigger, the task id and hashes are committed.
   - **Teardown.** Daemon stopped, clone and clone memory dir removed, hub, launchd and
     registry state verified unchanged against the pre-run reading. A teardown mismatch stops
     the series loudly.
4. **R3 Order and blinding of the series.** A run order shuffled by a frozen seed, so time
   trends spread across cells. Runs execute any time during 28.5's period. The scorer never
   sees the cell (28.3 R6). {#r3}
5. **R4 Isolation.** No experiment agent writes outside its clone and its clone memory dir. No
   live store is opened. Every `find` is scoped to the clone. The runner refuses a clone path
   outside `/Volumes/littlebig/` and refuses when the volume is not mounted. {#r4}

## Acceptance criteria {#acceptance}

The runner's mechanics are tested without a model, through a stub `claude` executable that
records its argv and env and writes a synthetic transcript. The stub lives in `tests/`, is
registered in `workflow/test_mock_registry.md` as an external dependency, and is never in `src/`.
R0's probe and AC-6 use the real `claude`. {#acceptance-lead}

1. **AC-1 The memory snapshot.** A fixture memory dir with files created and updated before,
   after, and straddling (created before, updated after) a start time: only the "before" files
   are copied; the straddling one is excluded and counted `updated_after_start`. **Mutation:**
   the filter on `created` only copies the straddling file. {#ac-1}
2. **AC-2 Arm pinning.** For each of `A+dedupe` and `B`, the chosen session id draws that cell
   under the paired-leg record for the clone root, and the stub sees `--session-id` with that
   id. **Mutation:** a random id used without the draw check: the cell mismatches. {#ac-2}
3. **AC-3 Arm C's profile.** The clone settings generated for `C` carry the R0 (c) mechanism, and
   the generator of record produced them: a byte-equal re-run of it matches, and no
   hand-written settings file exists. A and B clones carry the generated full hook set.
   {#ac-3}
4. **AC-4 Teardown.** After a run, the clone, the clone memory dir and the daemon are gone, and
   the hub registry and launchd domain readings equal the pre-run readings. **Mutation:** the
   daemon left running: AC-4 fails on the reading. {#ac-4}
5. **AC-5 Refusals.** A clone path outside `/Volumes/littlebig/`, or an unmounted volume, makes
   the runner exit 1 before any clone. A clone with a git remote is refused. {#ac-5}
6. **AC-6 One real run per cell and trigger** on a calibration task, with the real `claude`:
   six runs whose transcripts and SessionStart sources match their trigger, whose `session_arm`
   rows match their cell (C: no rmx hook row at all), and whose teardowns are clean. This is
   recorded in the implementation summary, and it is 28.4's calibration input. {#ac-6}

## Files {#files}

| file | change |
|---|---|
| `eval/production/handhold/paired_runner.py` (new) | R1's task draw, R2's run, R3's order, R4's refusals |
| `eval/production/handhold/bare_profile.py` (new) | arm C's generated clone settings (R0 (c)'s mechanism) |
| `tests/test_task28_2_paired_runner.py` (new) | AC-1 to AC-5 |
| `tests/fixtures/handhold/fake_claude` (new, test-only) | the stub executable; registered in `workflow/test_mock_registry.md` |
| `workflow/measurements/handhold-paired-probe-<date>.md` (new, GMD) | R0's answers (a)-(f), counts only |

## Test strategy {#test-strategy}

- RED first on AC-1 to AC-5 (no runner exists). AC-6 is a real run, recorded.
- The only mock is the external `claude` binary, and only in AC-1 to AC-5. The store, the
  ingest, the daemon and the hooks generator are real.
- Output is captured to `workflow/review-output/pytest-task28-2.log`.

## Definition of done {#done}

- R0 recorded; AC-1 to AC-5 RED then GREEN; AC-6's six runs recorded with clean teardowns.
- Implementation summary at `workflow/implementation_summaries/task-28.2-paired-reentry-runner.md`.
- Committed on branch `task-28.2-paired-reentry-runner`, merged `--no-ff` to `master`.
