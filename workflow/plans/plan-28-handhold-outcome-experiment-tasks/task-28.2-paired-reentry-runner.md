---
gmd: "0.1"
id: task-28.2-paired-reentry-runner
title: "Task 28.2: the paired re-entry runner: real handoffs resumed by fresh agents on littlebig clones cut at the task's start commit, under cells A+dedupe, B and C set by the runner, after a new session and after /clear, with every memory read filtered to the task's start"
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
> Status: Drafting (spec wave 2026-11-13, G17; r1 fold of `bsd-spec-t3c`, [[#rev-r1]]).
> Depends on: [[task-28.1-session-arms-and-push-switch]] (the paired override and the as-of
> filter).
> Builds `eval/production/handhold/`. R0 is a probe whose answers can change R2's mechanics. If an
> answer is "no", the task stops, and the lead re-specifies it through a dated revision and a
> ch-bsd round before 28.4 freezes anything. Meanwhile the goal continues with the items that do
> not depend on it.

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
holds the task and the starting commit fixed and varies only the cell and the trigger. Four
hazards shape it:
- **Leakage.** Later commits, later memories and later global rows record how many past tasks
  ended. A fresh agent that can reach them is not resuming; it is reading the answer. The r1
  review found two leaks, git refs and the global store, that the first draft did not guard.
- **Unequal leakage.** Whatever leaks through the hooks reaches A and B and not C. That biases
  the primary B-vs-C contrast toward the handholds.
- **Fleet pollution.** A clone's store must never register with the hub or with launchd.
- **Pinning.** The runner, not a period record, sets each run's cell (28.1 a6).
{#why-body}

## Requirements {#requirements}

1. **R0 Probe first (a measurement; nothing is built on an unproven mechanic).** On one
   synthetic task in a tmp git repo on littlebig, establish and record: {#r0}
   - (a) the three `RMX_HANDHOLD_*` values exported by the runner reach the hooks, the MCP
     server process and the agent's Bash calls in a real `claude` session, as the SessionStart
     row's `arm_source: paired` and `arm_run` show;
   - (b) a `/clear` re-entry can be driven unattended (through a `screen` session that `stuff`s
     the text and then sends a separate `\r`, or headless) and fires SessionStart with source
     `clear`, while a fresh process fires `startup`;
   - (c) arm C's profile turns off every rmx hook for the session, project and user level alike
     (the probe checks a generated clone settings file carrying `disableAllHooks: true`, or the
     reap path of `rmx install-hooks` plus the user-level hooks); with no `.refmatrix/PRIMER.md`
     generated in a C clone, CLAUDE.md's import resolves to nothing and Claude Code starts
     cleanly; the MCP server stays (pull);
   - (d) the memory dir Claude Code reads for a clone path
     (`~/.claude/projects/<clone-slug>/memory`) can be populated by the runner and is bridged
     into the clone's store;
   - (e) a clone's store and daemon: the daemon runs unsupervised, appears in no hub registry
     and no launchd label, and stops at teardown (`rmx daemon status`, `rmx hub status` and the
     launchd domain, each read before and after);
   - (f) the cost of one run (tokens, wall time);
   - (g) whether the session id survives `/clear` (r1 #s2). If it does not, every record of
     the run is keyed on the runner's run id (`arm_run`), never on the session id;
   - (h) which paths outside the clone an agent's tool calls reach in practice: the source
     repo, the real memory dir and `~/.refmatrix`. This sizes R5's leak control.
2. **R1 The task set.** Candidates are real handoffs: refmatrix's `workflow/past_handoffs/` and
   save-states, and cliquedb's, read through a local read-only clone of the repo. Each task
   records:
   - its start sha (the commit the handoff was written at) and that commit's time, which is the
     task's as-of;
   - its handoff and save-state as of that sha;
   - its reference continuation (the files changed by the next session's commits, from git);
   - its resume prompt, ONE fixed template for all tasks.

   A task is excluded when its continuation deployed, touched a live store or a fleet repo, or
   needed the user mid-task. The draw (seed, date range, count per project) and the task-id
   list's sha256 are frozen by 28.4. Calibration tasks are drawn apart and never reused. {#r1}
3. **R2 One run.** For each task × paired cell (`A+dedupe`, `B`, `C`; P-6) × trigger: {#r2}
   - **The clone is cut at the start sha (r1 #s1).** A new clone at
     `/Volumes/littlebig/<project>-handhold-<run-id>`, built so that the start sha is the only
     head and no later commit is reachable or even present:
     - clone, then reset ONE local branch to the start sha;
     - delete every other ref (remote-tracking refs, tags, notes, stash) and remove the remote;
     - expire the reflog, then `git gc --prune=now`.

     It is verified before the run: `git rev-list --all` equals `git rev-list <start-sha>`, and
     `git cat-file --batch-all-objects --batch-check` lists no commit outside that set. A
     failed check aborts the run.
   - **Store.** Built by the deployed `rmx` ingest under the clone, as R0 (e) established.
   - **The memory snapshot carries no later knowledge.** The clone's memory dir gets only the
     project's memory files whose `created` AND `updated` are before the task's as-of, and only
     save-states and handoffs from before it. Each excluded file is counted, by reason. Arm C
     gets the same dir, because Claude Code's own memory index is not a refmatrix handhold.
   - **Every memory read is filtered to the as-of (r1 #s1).** The runner exports
     `RMX_HANDHOLD_AS_OF` = the task's as-of into the `claude` process in EVERY cell, so 28.1
     R4's filter applies to the global store and to every pull path, in C too.
   - **Cell (r1 #s2).** For `A+dedupe` and `B` the runner exports `RMX_HANDHOLD_CELL` and
     `RMX_HANDHOLD_RUN`. `C` gets the generated bare profile from R0 (c), plus
     `RMX_HANDHOLD_RUN` and `RMX_HANDHOLD_AS_OF`. No period record is used. The runner reads the
     run's SessionStart row and aborts the run unless it shows the cell set (C: no rmx hook row
     at all).
   - **Trigger.** For `new-session`, a fresh process gets the resume prompt. For `clear`, a
     fresh process gets ONE fixed warm-up prompt (template frozen by 28.4), then `/clear`, then
     the resume prompt.
   - **Stop.** At the endpoint 28.3 detects, or at a cap of tool calls and wall time frozen by
     28.4. A run stopped at the cap is `censored`.
   - **Archive (lead ruling 2026-11-13, on the report's contradiction 7).** The transcript (the
     parent file and every subagent file) and the clone store's telemetry are copied to a LOCAL
     archive at `/Volumes/littlebig/refmatrix-measurement-archive/plan-28/paired/<run-id>/`:
     - it is outside the repo and outside every watched tree;
     - it is mode `0700`, and nothing in it is ever committed;
     - only the run id, the cell, the trigger, the task id and a sha256 manifest are committed.

     **The archive's creation is announced to the user before the first run.** The lead makes
     the announcement, and its date is recorded in the implementation summary. If the volume is
     not mounted, the runner refuses (R4). The archive is deleted only on the user's word, after
     28.5's report.
   - **Teardown.** The daemon is stopped, and the clone and the clone's memory dir are removed.
     The hub, launchd and registry state are verified unchanged against the pre-run reading. A
     teardown mismatch stops the series loudly.
4. **R3 Order and blinding of the series.** The run order is shuffled by a frozen seed, so time
   trends spread across cells. Runs execute any time during 28.5's period. The scorer never
   sees the cell (28.3 R6). {#r3}
5. **R4 Isolation.** No experiment agent writes outside its clone and its clone memory dir, and
   no live store is opened. Every `find` is scoped to the clone. The runner refuses a clone path
   outside `/Volumes/littlebig/`, and refuses when the volume is not mounted. {#r4}
6. **R5 Leak control.** A run's transcript is scanned (by 28.3's scorer) for tool calls whose
   paths fall outside the clone, the clone memory dir and the archive. A run that reads the
   source repo, the real project memory dir, or a global store file is `leak_suspect`. It is
   excluded from the primary reading and counted per cell. 28.4 freezes the rule that unequal
   exclusion across cells voids the primary reading. {#r5}

## Acceptance criteria {#acceptance}

The runner's mechanics are tested without a model, through a stub `claude` executable that
records its argv and env and writes a synthetic transcript. The stub lives in `tests/`, is
registered in `workflow/test_mock_registry.md` as an external dependency, and is never in `src/`.
R0's probe and AC-6 use the real `claude`. Every AC names its mutation. {#acceptance-lead}

1. **AC-1 The memory snapshot.** A fixture memory dir holds files created and updated before,
   after, and straddling the as-of (created before, updated after). Only the "before" files are
   copied. The straddling one is excluded and counted `updated_after_start`. **Mutation:** a
   filter on `created` only, which copies the straddling file. {#ac-1}
2. **AC-2 The cell reaches the process.** For each of `A+dedupe` and `B`, the stub sees
   `RMX_HANDHOLD_CELL`, `RMX_HANDHOLD_RUN` and `RMX_HANDHOLD_AS_OF` in its environment, with the
   values set. For `C` it sees the run id and as-of, and no cell. A stubbed SessionStart row
   whose cell differs from the one set aborts the run. **Mutations:** the cell not exported, so
   the row mismatch aborts; the as-of not exported in `C`, so AC-2 fails on C's environment.
   {#ac-2}
3. **AC-3 Arm C's profile.** The clone settings generated for `C` carry the R0 (c) mechanism,
   produced by the generator of record: a re-run is byte-equal, and no hand-written settings file
   exists. A and B clones carry the generated full hook set. **Mutation:** one rmx hook left in
   the C profile; the check that C carries no rmx hook fails. {#ac-3}
4. **AC-4 Teardown.** After a run, the clone, the clone memory dir and the daemon are gone, and
   the hub registry and launchd domain readings equal the pre-run readings. **Mutation:** the
   daemon left running; AC-4 fails on the reading. {#ac-4}
5. **AC-5 Refusals.** The runner exits 1 before creating any clone when the clone path is
   outside `/Volumes/littlebig/`, when the volume is unmounted, or when the clone still has a
   remote or a ref other than the start branch. **Mutation:** the path check removed; a clone is
   created under the tmp root and AC-5 fails. {#ac-5}
6. **AC-6 One real run per cell and trigger** on a calibration task, with the real `claude`: six
   runs whose transcripts and SessionStart sources match their trigger, whose rows match their
   cell (C: no rmx hook row), and whose teardowns are clean. It is recorded in the implementation
   summary and is 28.4's calibration input. **Mutation:** the `clear` trigger driven without
   `/clear`; the SessionStart source reads `startup` and AC-6 fails. {#ac-6}
7. **AC-7 The clone is cut at the start sha (r1 #s1).** In a fixture repo with five commits after
   the start sha, a tag on one of them and a remote-tracking branch, the built clone's
   `git rev-list --all` equals `git rev-list <start-sha>`, and no later commit object is
   present. **Mutations:** the `git gc --prune=now` step skipped, so a later commit object is
   still present; tags kept, so a later commit is reachable. {#ac-7}
8. **AC-8 Leak control.** A synthetic transcript with one Read of a file under the source repo
   marks the run `leak_suspect`, and it is excluded and counted. A Read inside the clone does
   not. **Mutation:** the scan limited to Bash calls; the Read leak passes unflagged. {#ac-8}

## Files {#files}

| file | change |
|---|---|
| `eval/production/handhold/paired_runner.py` (new) | R1's task draw, R2's run (clone cut, snapshot, env, trigger, archive, teardown), R3's order, R4's refusals |
| `eval/production/handhold/bare_profile.py` (new) | arm C's generated clone settings (R0 (c)'s mechanism) |
| `tests/test_task28_2_paired_runner.py` (new) | AC-1 to AC-5, AC-7, AC-8 |
| `tests/fixtures/handhold/fake_claude` (new, test-only) | the stub executable; registered in `workflow/test_mock_registry.md` |
| `workflow/measurements/handhold-paired-probe-<date>.md` (new, GMD) | R0's answers (a)-(h), counts only |
| `/Volumes/littlebig/refmatrix-measurement-archive/plan-28/paired/` (LOCAL, `0700`, never committed; creation announced to the user) | R2's archive |

## Test strategy {#test-strategy}

- RED first on AC-1 to AC-5, AC-7 and AC-8 (no runner exists). AC-6 is a real run, recorded.
- The only mock is the external `claude` binary, and only in the stubbed ACs. The store, the
  ingest, the daemon, git and the hooks generator are real.
- Output is captured to `workflow/review-output/pytest-task28-2.log`.

## Definition of done {#done}

- R0 recorded (a)-(h); AC-1 to AC-5, AC-7 and AC-8 RED then GREEN; AC-6's six runs recorded with
  clean teardowns.
- Implementation summary at `workflow/implementation_summaries/task-28.2-paired-reentry-runner.md`.
- Committed on branch `task-28.2-paired-reentry-runner`, merged `--no-ff` to `master`.

## Revision r1 (2026-11-13, `bsd-spec-t3c`; lead rulings) {#rev-r1}

| finding | disposition | where |
|---|---|---|
| s1 git refs and the global store leak later knowledge, and unequally across cells | the clone is cut at the start sha with no later commit reachable or present; every cell runs with the as-of filter (28.1 R4); leak control by transcript scan | [[#r2]], [[#r5]], [[#ac-7]], [[#ac-8]], [[#ac-2]] |
| s2 the paired cell cannot be pinned through a period record; `/clear` may change the id | the runner sets the cell by env (28.1 a6); R0 (g) probes id survival; records key on the run id | [[#r0]], [[#r2]], [[#ac-2]] |
| m3 ACs without a named mutation | every AC names one | [[#acceptance]] |
| m10 who re-specs after a "no" in R0 | the lead, by a dated revision and a ch-bsd round; the goal continues meanwhile | header |
