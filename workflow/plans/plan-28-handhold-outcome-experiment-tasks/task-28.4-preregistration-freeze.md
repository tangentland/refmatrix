---
gmd: "0.1"
id: task-28.4-preregistration-freeze
title: "Task 28.4: calibrate the paired leg, settle every P-item, and freeze the handhold experiment's pre-registration (outcomes, bands, sizes, period) with its sha, before the user-gated start"
tags: [task, plan-28, experiment, preregistration, calibration, bands]
metadata:
  node_type: task
  status: drafting
  plan: plan-28-handhold-outcome-experiment
  created: 2026-11-13
  updated: 2026-11-13
---

# Task 28.4: the pre-registration freeze {#root}

> Plan: [[plan-28-handhold-outcome-experiment]]
> Status: Drafting (spec wave 2026-11-13, G17).
> Depends on: 28.1, 28.2 (R0 and AC-6) and 28.3 merged; bug-216 live; 21.5 phase M reported
> ([[task-21.5-tool-used-signal#done-m]]); the m1 r2-lite confirm (G32) CLEAN or MEH-only
> (L36).
> Builds nothing in `src/`. Its output is one frozen measurement-plan file.

rel: part-of -> [[plan-28-handhold-outcome-experiment]]
rel: depends-on -> [[task-28.1-session-arms-and-push-switch]]
rel: depends-on -> [[task-28.2-paired-reentry-runner]]
rel: depends-on -> [[task-28.3-outcome-scorer]]
rel: depends-on -> [[task-21.5-tool-used-signal#done-m]]
rel: derives-from -> [[plan-review-2026-11-13#lead]]
rel: reinforces -> [[feedback_go_no_go_ranges_not_predrop]]

## Why {#why}

L36: the four 21.5 measurements that this experiment derives from were corrected after their
ch-bsd round with no confirm row, so bands drawn before the confirm would rest on unconfirmed
numbers. The exploration requires a minimum detectable effect for the paired leg before
running. Paired tasks are expensive (10-20 pairs per arm is the likely ceiling). Every choice
plan-28 leaves open (P-1 to P-10) must be fixed before any outcome is seen. {#why-body}

## Requirements {#requirements}

1. **R1 Calibration powers the PRIMARY contrast, `B` vs `C` (lead ruling on r1 #s9).** K
   calibration tasks (28.2 R1; never reused) run under `B` and `C`, both triggers, and under
   `A+dedupe` beside them for the secondary contrast. 28.2's AC-6 runs count toward them.
   - From the variance of the `B`/`C` per-task log cost ratio, compute the number of tasks that
     distinguishes a 30% cut from a 10% cut, at two-sided α 0.05 and power 0.8, on P-3's scalar.
   - The same computation for `A+dedupe` vs `C` is reported, and it is secondary.
   - n is capped at 20 tasks per cell per trigger. If the cap binds for `B` vs `C`, the paired
     leg can read only whether "≥ 30%" holds, and that is written into the file before the
     start.
   {#r1}
2. **R2 The file.** `workflow/measurements/handhold-experiment-prereg.md` (GMD,
   `node_type: measurement`, `status: frozen`) holds: {#r2}
   - every P-item's chosen value, with the lead's (or the user's) decision row cited;
   - outcomes (1)-(7) as 28.3 computes them, with their function names and the scorer's sha;
   - the primary comparison (P-2), the effect estimator (1 − the geometric mean of per-task cost
     ratios, a bootstrap 95% CI over tasks, pooled over both triggers, with per-trigger results
     reported), and the band table with P-8's CI rule;
   - the push reading: `A+dedupe` vs `B` on outcomes (2)-(4) only (P-11; r1 #b1). "Better"
     means that the session-bootstrap test of the A − B difference, Holm-adjusted across the
     three outcomes, rejects at family-wise α 0.05 in A's favour; Holm-adjusted CIs are printed
     (r2-m5). `shrink`
     fires when A is better on none of them while costing more on (5). Outcome (6) is read
     within the A cells only;
   - 10.2 R7's nested bands, copied verbatim with their source;
   - the `cited_in_answer` gate: 50 blind labels, weight only at precision ≥ 0.80 with a Wilson
     lower bound ≥ 0.65, else outcome (6) is R12 explicit only (r1 #s5);
   - the labellers: blind labeller agents (28.3 R6), the R12 pilot's rubric for the gate, and the
     rubrics for (3), (4) and the endpoint's "correct statement of the resume point", each
     written here with its label set and two worked examples;
   - sizes: paired tasks per cell and trigger (R1); labelled sessions per cell per store for
     outcomes (3)-(4); the gate's 50 pairs; the 20% second-rater share;
   - the leak rule (28.2 R5): `leak_suspect` runs are excluded, and a per-cell exclusion count
     that differs by more than one run between `B` and `C` voids the primary reading;
   - the period: the salt (generated at freeze, committed), the start (set by 28.5 at the
     user's go), and the end rule. The end is the later of 14 active days and 40 sessions per
     cell per store; at 42 active days without the minimums, the session leg reads report-only.
     Active days are days with an active record, so paused days do not count;
   - **the pause (P-12; r1 #s8).** It is a user-gated step that sets the active record's `end`
     to now, by one commit and a deploy. Sessions in flight keep the cell their SessionStart
     recorded (28.1 R2). A deploy that touches `scan.py`, `recall_pack.py`, `hook_budget.py`,
     context rendering, the hooks generator or `arms.py` lands ONLY while no record is active. The record's own start, pause and end commits, which set its dates in `arms.py`, are exempt by name (r2-m3).
     Resuming means a NEW record (new id, new salt) committed at the user's go. Readings are
     stratified by record id, and each record's deploy sha is recorded;
   - the transcript cleanup period that Claude Code is configured with, read before the start
     (28.5 R2), and the session-leg archive's sweep interval (28.5 R3);
   - **limits (r1 #m11):**
     - the user is not blind: they know their cell, because `B` has no per-prompt push;
     - the goal's own orchestration sessions in refmatrix fall inside the session leg;
     - the as-of filter and the clone cut cannot stop an agent from reasoning from what the
       model already knows;
   - the task set's seed and the task-id list's sha256; the resume and warm-up prompt templates;
     the run caps;
   - the abort rule: the user may stop at any time, and a defect in a cell that blocks work
     stops the period (recorded, nothing read);
   - the charter-decision inputs that are not outcomes: 21.5 phase M's band reading, and the
     `denotes` evaluation's, if run.
3. **R3 Freeze.** The file is committed and its sha is written into plan-28's `#ordering` notes
   and the queue line before 28.5's start. Any later change is a dated revision with its
   reason, committed before any outcome is computed. A change after an outcome is computed
   voids that outcome's reading. {#r3}
4. **R4 Review.** A ch-bsd round over the file comes back CLEAN or MEH-only before the user is
   asked to start. {#r4}

## Acceptance criteria {#acceptance}

1. **AC-1** The file lints with 0 errors. Every P-item, size, seed, template, rubric, band, the
   pause rule and the limits have a value: a checker script lists any unset field and exits 1.
   **Mutation:** one field deleted from a fixture copy of the file; the checker must exit 1, and
   AC-1 fails if it exits 0. {#ac-1}
2. **AC-2** The calibration's inputs (run ids, per-task `B`/`C` and `A+dedupe`/`C` ratios) and
   its n are in the file, and recomputing n from the committed ratios reproduces it.
   **Mutation:** one committed ratio altered by 10%; the recomputed n differs and the checker
   exits 1. {#ac-2}
3. **AC-3** The file's sha is recorded in plan-28 before 28.5's start commit, as the git order
   shows. {#ac-3}
4. **AC-4** The ch-bsd round over the file is CLEAN or MEH-only. {#ac-4}

## Files {#files}

| file | change |
|---|---|
| `workflow/measurements/handhold-experiment-prereg.md` (new) | R2 |
| `eval/production/handhold/prereg_check.py` (new) | AC-1's checker; R1's n computation |
| `workflow/plans/plan-28-handhold-outcome-experiment.md` | the frozen sha (R3) |

## Definition of done {#done}

- AC-1 to AC-4 met. Implementation summary at
  `workflow/implementation_summaries/task-28.4-preregistration-freeze.md`.
- Committed on branch `task-28.4-preregistration-freeze`, merged `--no-ff` to `master`.

## Revision r1 (2026-11-13, `bsd-spec-t3c`; lead rulings) {#rev-r1}

| finding | disposition | where |
|---|---|---|
| s9 the calibration powers the wrong contrast | calibrated on `B` vs `C`, the primary; `A+dedupe` vs `C` reported as secondary | [[#r1]], [[#ac-2]] |
| b1 / s5 / s8 the push reading, the `cited_in_answer` gate and the pause rule | frozen as the lead ruled them (P-11, the gate, P-12) | [[#r2]] |
| m3 ACs without a named mutation | AC-1 and AC-2 name one | [[#acceptance]] |
| m5 / m11 the labellers and the limits | written into the file | [[#r2]] |

## Revision r2 (2026-11-13, `bsd-spec-t3c` r2; lead rulings) {#rev-r2}

| finding | disposition | where |
|---|---|---|
| r2-m3 | the record's own commits are exempt from the pause ban | [[#r2]] |
| r2-m5 | the push reading's Holm correction is frozen here | [[#r2]] |
