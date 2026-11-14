---
gmd: "0.1"
id: task-28.4-preregistration-freeze
title: "Task 28.4: calibrate the paired leg, settle every P-item, and freeze the handhold experiment's pre-registration (outcomes, bands, minimum n per cell, sizes) with its sha, before the paired series starts (the orchestrator's start, L78)"
tags: [task, plan-28, experiment, preregistration, calibration, bands]
metadata:
  node_type: task
  status: pending
  plan: plan-28-handhold-outcome-experiment
  created: 2026-11-13
  updated: 2026-11-14
---

# Task 28.4: the pre-registration freeze {#root}

> Plan: [[plan-28-handhold-outcome-experiment]]
> Status: Pending: approved to build (2026-11-14, [[#approval]]; spec wave 2026-11-13, G17).
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
   calibration tasks (28.2 R1; never reused) run under all four cells (`A+dedupe`, `A+full`,
   `B`, `C`; L83) and both triggers. 28.2's AC-6 runs count toward them.
   - From the variance of the `B`/`C` per-task log cost ratio, compute the number of tasks that
     distinguishes a 30% cut from a 10% cut, at two-sided α 0.05 and power 0.8, on P-3's scalar.
   - The same computation is reported for `A+dedupe` vs `C` (secondary), `A+dedupe` vs `B` (the
     push reading's pairs) and `A+dedupe` vs `A+full` (10.2's nested reading).
   - n is capped at 20 tasks per cell per trigger. If the cap binds for `B` vs `C`, the paired
     series can read only whether "≥ 30%" holds, and that is written into the file before the
     start.
   {#r1}
2. **R2 The file.** `workflow/measurements/handhold-experiment-prereg.md` (GMD,
   `node_type: measurement`, `status: frozen`) holds: {#r2}
   - every P-item's chosen value, with the lead's (or the user's) decision row cited;
   - outcomes (1)-(7) as 28.3 computes them over the paired runs, with their function names and
     the scorer's sha;
   - the primary comparison (P-2), the effect estimator (1 − the geometric mean of per-task cost
     ratios, a bootstrap 95% CI over tasks, pooled over both triggers, with per-trigger results
     reported), and the band table with P-8's CI rule;
   - the push reading: `A+dedupe` vs `B` on outcomes (2)-(4) only (P-11; r1 #b1), paired by
     task. "Better" means that the paired bootstrap test over tasks of the A − B difference,
     Holm-adjusted across the three outcomes, rejects at family-wise α 0.05 in A's favour.
     Holm-adjusted CIs are printed (r2-m5). `shrink` fires when A is better on none of them
     while costing more on (5). Outcome (6) is read within the A cells only;
   - 10.2 R7's nested bands, copied verbatim with their source, read on `A+dedupe` vs `A+full`
     from the paired series (L83);
   - the `cited_in_answer` gate: 50 blind labels, weight only at precision ≥ 0.80 with a Wilson
     lower bound ≥ 0.65, else outcome (6) is R12 explicit only (r1 #s5);
   - the labellers: blind labeller agents (28.3 R6), the R12 pilot's rubric for the gate, and the
     rubrics for (3), (4) and the endpoint's "correct statement of the resume point", each
     written here with its label set and two worked examples;
   - sizes: paired tasks per cell and trigger (R1); labelled runs per cell for outcomes (3)-(4);
     the gate's 50 pairs; the 20% second-rater share;
   - the leak rule (28.2 R5): `leak_suspect` runs are excluded, and a per-cell exclusion count
     that differs by more than one run between `B` and `C` voids the primary reading;
   - **the minimum n of paired tasks per cell, for EVERY reading (L79, L83),** each frozen here
     and counted after the `leak_suspect` and `arm_error` exclusions:
     - the primary (`B`, `C`): R1's n per cell per trigger;
     - the push reading (`A+dedupe`, `B`);
     - 10.2's nested reading (`A+dedupe`, `A+full`): its minimum n of paired tasks per cell is
       FROZEN HERE, and 10.2 R7 cites it (spec-t3b, 2026-11-14: 10.2 no longer states "40
       sessions per cell per store" and defers the number to 28.4). It is computed like the
       others, from R1's `A+dedupe` vs `A+full` calibration;

     Any reading below its minimum is "underpowered, no verdict": neither pass nor fail, and no
     default changes. The report states the n reached per cell. **A power note** records, from
     R1's calibration and 28.2 R0 (f)'s cost per run, how many runs and how much agent time each
     minimum costs (tasks × 4 cells × 2 triggers), so that "underpowered" is foreseen;
   - **the series' end (L83):** the series is not time-boxed. It ends when every reading's
     minimum n is reached, at R1's cap, or when the user stops it;
   - **the pause (P-12, restated by L83).** It is user-gated: on the user's word, the runner
     finishes or aborts the run in flight (recorded) and starts no new run. Resuming is on the
     user's word. A deploy that touches `scan.py`, `recall_pack.py`, `hook_budget.py`, context
     rendering, the hooks generator or `arms.py` lands ONLY while the series is paused. Every run
     records its deployed `rmx` sha, and readings are stratified by sha when the series spans
     more than one;
   - the paired archive (28.2 R2) and its announcement to the user;
   - **limits (r1 #m11, restated by L83):**
     - the runs are fresh agents resuming real handoffs, not the user's own live work, so the
       result speaks to re-entry by an agent and generalises to live sessions only by argument;
     - the user's own sessions are never assigned to an arm, so the earlier blinding concern
       about the user no longer applies;
     - the as-of filter and the clone cut cannot stop an agent from reasoning from what the
       model already knows;
   - the task set's seed and the task-id list's sha256; the resume and warm-up prompt templates;
     the run caps;
   - the abort rule: the user may stop at any time, and a defect in a cell that breaks runs
     stops the series (recorded, nothing read);
   - the charter-decision inputs that are not outcomes: 21.5 phase M's band reading, and the
     `denotes` evaluation's, if run.
3. **R3 Freeze.** The file is committed and its sha is written into plan-28's `#ordering` notes
   and the queue line before 28.5's start. Any later change is a dated revision with its
   reason, committed before any outcome is computed. A change after an outcome is computed
   voids that outcome's reading. {#r3}
4. **R4 Review.** A ch-bsd round over the file comes back CLEAN or MEH-only before the user is
   told the experiment is starting (L78). {#r4}

## Acceptance criteria {#acceptance}

1. **AC-1** The file lints with 0 errors. Every P-item, size, seed, template, rubric, band, the
   pause rule and the limits have a value: a checker script lists any unset field and exits 1.
   **Mutation:** one field deleted from a fixture copy of the file; the checker must exit 1, and
   AC-1 fails if it exits 0. {#ac-1}
2. **AC-2** The calibration's inputs (run ids, per-task `B`/`C` and `A+dedupe`/`C` ratios) and
   its n are in the file, and recomputing n from the committed ratios reproduces it.
   **Mutation:** one committed ratio altered by 10%; the recomputed n differs and the checker
   exits 1. {#ac-2}
3. **AC-3** The file's sha is recorded in plan-28 before 28.5 starts the series, as the git order
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

## Approval (2026-11-14) {#approval}

rel: derives-from -> [[bsd-spec-t3c-r3-c5d1b79]]
rel: derives-from -> [[plan-review-2026-11-13#goal-horizon]]

**Decision row (2026-11-14):** approved by the lead on the user's pattern (d9co) after ch-bsd `bsd-spec-t3c` r3 came back MEH-only (0B/0S/2M at `c5d1b79`), with both MEHs folded (r3 m1, m2). The ch-bsd rounds were r1 DIRTY 1B/9S/11M, r2 DIRTY 0B/3S/7M and r3 MEH-only; every finding is folded, as each spec's revision tables show. This task is `pending`, which means approved to build in plan-28's order. {#approval-row}

## Revision L79 (2026-11-14, the user: "the plan 28 arms should only be 3 days"; Q11 answered (a)) {#rev-l79}

rel: derives-from -> [[plan-review-2026-11-13#lead]]

The status stays `pending` pending a confirm-lite ch-bsd round.

| change | where |
|---|---|
| the end rule: 3 calendar days, never extended; the 14-day / 40-session / 42-day rule removed | [[#r2]] |
| a minimum n per cell and outcome (10.2 R7's 40 sessions included), below which a reading is "underpowered, no verdict" | [[#r2]] |


**Refinement (dev master `8d88d29`; the user, the same day: "3 real days will be sufficent", Q11 a):** the period is 3 CALENDAR days from its start, with the arms concurrent. A pause does NOT extend it: the period ends 3 calendar days (72 hours) after the start, whatever was paused, and paused time is not made up. The "active days" wording is replaced. The rest of L79 is unchanged. {#rev-l79-refined}

## Revision L80 (2026-11-14, `bsd-spec-t3c` L79 confirm-lite 0B/1S/4M; lead ruling L80) {#rev-l80}

rel: derives-from -> [[plan-review-2026-11-13#lead]]

| finding | disposition | where |
|---|---|---|
| S1 the start is delegated (L78) | the title, R2's period line and R4 now say the orchestrator's start, with the user told first | header, [[#r2]], [[#r4]] |
| m3 the #rev-l79 table did not render; "Q11 assumed" | blank line added; "Q11 answered (a)" | [[#rev-l79]] |

## Approval of the L79/L80/L82 amendment (2026-11-14, d9co) {#approval-l79-2026-11-14}

| decision | basis | status |
|---|---|---|
| The 3-calendar-day session period (L79, Q11 answered a), the orchestrator-run start under L78 (L80) and the end committed with the start (L82) are approved by the lead on the user's pattern (d9co) after the L80 confirm-lite MEH-only (0B/0S/2M), folded at `49a603c` per L82 with no further round | `workflow/bullshit/2026-11-14-0200-spec-t3c-r5-l80-d42c72b.md` (with the L79 confirm-lite `2026-11-14-0150-spec-t3c-r4-l79-7758d2a.md`, over `spec-wave-t3c` `be03148..d42c72b`) | status unchanged; Q14 (where the verdicts come from) may amend this plan again |

rel: derives-from -> [[bsd-spec-t3c-r5-l80-d42c72b]]

## Revision L83 (2026-11-14, the user, Q14: "drop the live part"; lead ruling L83) {#rev-l83}

rel: derives-from -> [[plan-review-2026-11-13#lead]]

The status stays `pending` pending a confirm-lite.

| change | where |
|---|---|
| calibration runs all four cells, and reports n for the push and nested pairs beside the primary | [[#r1]] |
| a minimum n of paired tasks per cell for every reading (10.2's nested minimum frozen here and cited by 10.2), with a power note in runs and agent time | [[#r2]] |
| the period, its 72-hour end and the record-based pause are removed; the series ends at its minimum n, at the cap, or by the user; the pause is restated for the series | [[#r2]] |
| the push test is a paired bootstrap over tasks; the limits are restated for an agent-only experiment | [[#r2]] |
