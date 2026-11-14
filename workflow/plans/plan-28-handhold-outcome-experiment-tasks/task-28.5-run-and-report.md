---
gmd: "0.1"
id: task-28.5-run-and-report
title: "Task 28.5: the run: the orchestrator starts the period when plan-28's Depends-on holds and tells the user first (L78), runs both legs, read every band as frozen, report, and stop the goal for the user's charter decision"
tags: [task, plan-28, experiment, run, report, charter, user-gated]
metadata:
  node_type: task
  status: pending
  plan: plan-28-handhold-outcome-experiment
  created: 2026-11-13
  updated: 2026-11-14
---

# Task 28.5: run and report {#root}

> Plan: [[plan-28-handhold-outcome-experiment]]
> Status: Pending: approved to build (2026-11-14, [[#approval]]; spec wave 2026-11-13, G17).
> Depends on: [[task-28.4-preregistration-freeze]] frozen and reviewed. **The start:** the orchestrator starts the experiment when plan-28's Depends-on holds and tells the user first (L78).
> **User-gated:** every pause and the end. **Goal stop:** the charter decision (G18).

rel: part-of -> [[plan-28-handhold-outcome-experiment]]
rel: depends-on -> [[task-28.4-preregistration-freeze]]
rel: derives-from -> [[plan-review-2026-11-13#lead]]
rel: derives-from -> [[plan-review-2026-11-13#goal-horizon]]
rel: related-to -> [[task-10.2-plan-10-injection-dedup]]
rel: reinforces -> [[feedback_errors_fail_loudly_on_the_console]]

## Why {#why}

The experiment randomises the user's own work sessions in two projects for 3 calendar days (L79).
L45 made its start a user step. L78 (the user, 2026-11-14: "the start of the plan-28 experiment
can proceed when you feel its time") delegated it to the orchestrator, who tells the user first. Its
result is an input to a user decision (G18), not a goal step. {#why-body}

## Requirements {#requirements}

1. **R1 The start (L78, L80).** The orchestrator starts the experiment when plan-28's
   Depends-on holds: bug-216 live; 10.2 built; 21.5 phase M reported; the m1 r2-lite confirm
   CLEAN or MEH-only (G32); and 28.4's file frozen and reviewed. For each precondition it
   records the evidence (a sha, a file, a verdict). It never changes a precondition to start
   sooner. It **tells the user first**, citing:
   - the frozen pre-registration's sha;
   - the cells and the stores;
   - the period (3 calendar days);
   - what cell `B` feels like (no per-prompt push);
   - the backups and the archive;
   - the stop condition (the user may stop at any time).

   The tell is recorded with its date. Every pause, the end and G18 stay user-gated. {#r1}
2. **R2 Start.** Before the commit, three checks are recorded:
   - Claude Code's transcript cleanup period is read, and the start needs it to be at least 7
     days, longer than R3's sweep interval (r1 #s7);
   - every registered store whose slug is in the record's scope is listed, and only the
     refmatrix and cliquedb roots may match (r1 #m9);
   - the session-leg archive's creation is announced to the user.

   Then one commit on `master` sets the plan-28 record's salt (from the frozen file), its
   `start`, AND its `end = start + 72 hours` in the same record (L82). That commit is followed
   by a deploy per the project's deploy rules. The period therefore closes on time without a
   later commit. `rmx install-hooks --check` stays
   clean (28.1 AC-9). The first SessionStart rows in each store show `arm_period`, and they are
   checked within one day. {#r2}
3. **R3 During the period.** {#r3}
   - **The archive runs incrementally (lead ruling on r1 #s7).** A daily sweep copies into the
     LOCAL session-leg archive at
     `/Volumes/littlebig/refmatrix-measurement-archive/plan-28/session/`:
     - every transcript of an in-scope session that has ended or gained lines since the last
       sweep, meaning the parent file and every subagent file;
     - the read-only copies of the stores' telemetry.

     The archive is outside the repo and outside every watched tree, mode `0700`, and never
     committed; only a sha256 manifest is. Each sweep counts sessions per cell whose transcript
     was already gone (`no_transcript`). The daily count reports them, and the report lists
     them as a limit.
   - A daily count (the period is 3 calendar days, L79) of sessions per cell per store, of
     suppressed rows and of `arm_error` sessions, posted to the user.
   - **The pause (P-12; r1 #s8).** A deploy that touches a module the pause rule names lands
     only while no record is active. The record's own start and pause commits (R2, this pause)
     are exempt by name (r2-m3). The end needs no commit (L82). To pause, the lead asks the user, and on the user's word
     one commit sets the active record's `end` to now and is deployed. Sessions in flight keep
     their cell (28.1 R2). A pause does not extend the period (L79, refined). Resuming is a NEW
     record (new id, new salt), with its `end` at the original window's end, committed at the user's
     go. Every deploy sha and date in the period is recorded, with the record id that was active.
   - The paired runs (28.2) execute in the frozen shuffled order.
   - A defect that blocks work in any cell stops the period loudly: the user is told, the period
     record's `end` is set, nothing is read, and the stop is recorded.
4. **R4 End: the check and the user step (L82).** `end` was written by R2's start commit, at
   3 calendar days after the start (the end rule, L79 refined; never extended for sessions, n or
   pauses). No end commit is needed.
   - At `end`, a new session in each store is checked to draw the default, and the result is
     recorded.
   - The user is told that the session leg has ended, with the n reached per cell. This is the
     end's user step. The user may also end earlier, by the pause step.
   - **Late sessions are dropped.** 28.3's scorer drops any session whose SessionStart `t` is at
     or after its record's `end`, and counts it per cell (`after_end`). A late check therefore
     cannot admit sessions randomised past 72 hours.
   {#r4}
5. **R5 Final sweep, then score and read (L80 m1).** Scoring waits for BOTH legs: the session
   period has ended (R4), AND the frozen paired series has completed or was stopped, with the
   reason recorded. The paired series may outrun the 72 hours. Then one last sweep runs (R3), and
   28.3's
   scorer runs over the archive and `readings.py` (28.3 R9) reads every band. Readings are
   stratified by record id. Every outcome is computed, every band is read as frozen, and every deviation from the
   pre-registration is listed. 10.2 R7's nested bands are read and handed to 10.2's
   implementation summary. {#r5}
6. **R6 Report.** `workflow/measurements/handhold-experiment-<date>.md` (GMD) holds the counts,
   the readings and the CIs, the charter-decision inputs that are not outcomes, and the
   limits. Only counts, labels and hashes are committed. A ch-bsd round over it must come back
   CLEAN or MEH-only. {#r6}
7. **R7 The goal stops.** The report goes to the user as a charter decision with the readings
   and the inputs (G18). The T3 re-plan and the plan-24 re-plan (D-Q5) follow the user's
   decision, not this task. {#r7}
8. **R8 Cleanup.** If the charter decision keeps no arm, `arms.py` (10.2's), arm B's branch,
   `push_on` and the period records are deleted per the widened deferral row (28.1 R5), and the
   row is closed. If it keeps one, the decision amends the row. {#r8}

## Acceptance criteria {#acceptance}

1. **AC-1** The tell to the user (R1) and each precondition's evidence are recorded, with
   their dates, BEFORE the start commit, as the git order shows (L80). {#ac-1}
2. **AC-2** The period ended after 3 calendar days. Every reading whose cell or outcome is
   below its frozen minimum n says "underpowered, no verdict", and the report states the n
   reached per cell (L79). {#ac-2}
3. **AC-3** Every band in the frozen file has a reading in the report, and no reading uses a
   rule absent from the frozen file. {#ac-3}
4. **AC-4** The start commit holds `end = start + 72 hours` (L82). After `end`, a new session
   in each store draws the default, checked and recorded. The scorer's `after_end` count per cell
   is in the report. {#ac-4}
5. **AC-5** The report passes its ch-bsd round, and the charter decision is put to the user.
   {#ac-5}

## Files {#files}

| file | change |
|---|---|
| `src/refmatrix/arms.py` | the period's salt, start and end, in one start commit (R2, L82); the deletion (R8) |
| `workflow/measurements/handhold-experiment-<date>.md` (new) | R6 |
| `workflow/deferral_registry.md` | the `arms.py` row closed or amended (R8) |

## Definition of done {#done}

- AC-1 to AC-5 met. Implementation summary at
  `workflow/implementation_summaries/task-28.5-run-and-report.md` (the start and end shas, the
  pause log, the readings).
- The start, end and cleanup commits are each made on branch `task-28.5-run-and-report` and
  merged `--no-ff` to `master`, then deployed.

## Revision r1 (2026-11-13, `bsd-spec-t3c`; lead rulings) {#rev-r1}

| finding | disposition | where |
|---|---|---|
| s7 the session-leg archive ran only at the end, after early transcripts may be pruned | a daily incremental sweep; the cleanup period is checked at the start; `no_transcript` is counted per cell | [[#r2]], [[#r3]], [[#r5]] |
| s8 the pause is undefined | a user-gated end-now commit; sessions keep their cell; resuming is a new record; readings by record | [[#r3]] |
| m9 the scope is a basename slug | the start lists the matching stores | [[#r2]] |

## Revision r2 (2026-11-13, `bsd-spec-t3c` r2; lead rulings) {#rev-r2}

| finding | disposition | where |
|---|---|---|
| r2-m3 | the record's own start, pause and end commits are exempt from the pause ban | [[#r3]] |

## Approval (2026-11-14) {#approval}

rel: derives-from -> [[bsd-spec-t3c-r3-c5d1b79]]
rel: derives-from -> [[plan-review-2026-11-13#goal-horizon]]

**Decision row (2026-11-14):** approved by the lead on the user's pattern (d9co) after ch-bsd `bsd-spec-t3c` r3 came back MEH-only (0B/0S/2M at `c5d1b79`), with both MEHs folded (r3 m1, m2). The ch-bsd rounds were r1 DIRTY 1B/9S/11M, r2 DIRTY 0B/3S/7M and r3 MEH-only; every finding is folded, as each spec's revision tables show. This task is `pending`, which means approved to build in plan-28's order. Its user steps stay user-gated: every pause and the end (L82; the start is the orchestrator's under L78). {#approval-row}

## Revision L79 (2026-11-14, the user: "the plan 28 arms should only be 3 days"; Q11 answered (a)) {#rev-l79}

rel: derives-from -> [[plan-review-2026-11-13#lead]]

The status stays `pending` pending a confirm-lite ch-bsd round.

| change | where |
|---|---|
| 3 calendar days; a daily count; the end after 3 calendar days, never extended; AC-2 reads "underpowered, no verdict" below the minimum n | [[#why]], [[#r3]], [[#r4]], [[#ac-2]] |


**Refinement (dev master `8d88d29`; the user, the same day: "3 real days will be sufficent", Q11 a):** the period is 3 CALENDAR days from its start, with the arms concurrent. A pause does NOT extend it: the period ends 3 calendar days (72 hours) after the start, whatever was paused, and paused time is not made up. The "active days" wording is replaced. The rest of L79 is unchanged. {#rev-l79-refined}

## Revision L80 (2026-11-14, `bsd-spec-t3c` L79 confirm-lite 0B/1S/4M; lead ruling L80) {#rev-l80}

rel: derives-from -> [[plan-review-2026-11-13#lead]]

| finding | disposition | where |
|---|---|---|
| S1 the start still required the user's go | title, Depends-on, #why, R1 and AC-1: the orchestrator starts the experiment when plan-28's Depends-on holds and tells the user first (L78); AC-1 checks that the tell and the evidence precede the start commit; pause, end and G18 stay user-gated | header, [[#why]], [[#r1]], [[#ac-1]] |
| m1 the report could score before the paired series ends | R5 waits for the session period's end AND the paired series' completion (or recorded stop) | [[#r5]] |
| m3 the #rev-l79 table did not render; "Q11 assumed" | blank line added; "Q11 answered (a)" | [[#rev-l79]] |


## Revision L82 (2026-11-14, `bsd-spec-t3c` L80 confirm-lite MEH-only 0B/0S/2M; lead ruling L82) {#rev-l82}

rel: derives-from -> [[plan-review-2026-11-13#lead]]

| finding | disposition | where |
|---|---|---|
| m1 #approval-row still listed "the go" | "every pause and the end" | [[#approval]] |
| m2 the end waited on a user-gated commit; sessions past 72 hours could be scored | R2's start commit writes `end = start + 72 h`; R4 is the check plus the user step; the scorer drops and counts sessions whose SessionStart is at or after `end` | [[#r2]], [[#r4]], [[#ac-4]], [[#files]] |

