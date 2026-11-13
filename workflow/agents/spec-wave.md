---
gmd: "0.1"
id: agent-brief-spec-wave
title: "Brief: spec wave for the 2026-11-13 consolidated goal (spec-t0, t2, t3a, t3b, t3c, t4, t56)"
tags: [agent-brief, spec-wave, plan-review, goal]
metadata:
  node_type: brief
  created: 2026-11-13
---

# Spec wave brief {#root}

The user will run the consolidated plan as an unattended `/goal`, so every queue item must reach
an `approved`, current task spec ("we will turn this consolidated plan into a goal. so need to
make sure the plans are complete", 2026-11-13). The source of truth for WHAT each spec must say is
`workflow/plan-review-2026-11-13.md` on dev master `1cf3b9f` (rev 6): the `#decisions` (D-Q1..D-Q7),
`#lead` (L1-L45), `#queue` and `#spec-gaps` (G1-G32) sections. Evidence:
`workflow/review-output/pop-2026-11-13/contra-{a..e}.md` and
`workflow/bullshit/2026-11-13-22*-pop-review-r*.md`. Read the plan review first.

rel: part-of -> [[plan-review-2026-11-13]]

## Rules {#rules}

- **Spec text only.** No `src/`, no tests, no live store, no daemons, no pytest.
- **Work only in your own clone, on your branch** (table below). Commit by pathspec. Never touch
  another clone. Read other clones only with `git -C <clone> show <branch>:<path>`; agents are
  building in `refmatrix-plan25-1`, `refmatrix-bug216` and `refmatrix-bug212`.
- **GMD:** every touched file passes `python3 tools/gmd/lint.py <file>` with 0 errors. New specs
  get full frontmatter, `{#anchor}` on every heading, and `rel:` edges (no bare prose citations).
  Follow the shape of the existing task specs in `workflow/plans/*-tasks/`: Depends on, Requirements
  R#, Acceptance AC# with named mutations, Files, a `#done` naming the implementation summary.
- **Status:** a new spec is `metadata.status: drafting`. A revised spec keeps its status and gains
  a dated revision-round section that cites the L-row / D-Q / G-row driving it. You never set
  `approved`; the lead does that after a clean ch-bsd round (the d9co route, `#goal-horizon`).
- **Q8 is open.** Write T1-T3 specs so they hold under Q8 a OR c: save-states stay bridged as
  `session/recall-state` rows. Name any line that would change under Q8 b in a `#q8-b` note.
  G22 (the D-Q1 work) is HELD; write nothing for it.
- **No new decisions.** If a spec needs a choice that no D-Q or L-row settles, do not pick one.
  List it in your report as an open item, with options and your recommendation first.
- **Never search from `/`.** Scope to the repo. `rmx context` / `rmx grep` are fine (read path).
- **Report as text** (the lead persists it), listing:
  - your commits;
  - per G-row: the files changed and what changed;
  - open items;
  - any contradiction you hit that the plan review missed.

## Assignments {#assignments}

| agent | clone (`/Volumes/littlebig/…`) · branch | G-rows / L-rows |
|---|---|---|
| spec-t0 | `refmatrix-spec-t0` · `spec-wave-t0` | **G5** new `workflow/plans/task-t0-suite-trust-sweep.md`. Covers bug-215, 170, 168, 155, 127, 130, 190, 091 + the SkipGate UNPINNED row (bug-212 r2 flag 8 m-4), and the plan-gate remedies W2-a (plan-6 ch-bsd r1 at e0b7df6), W2-b (plan-8 r5), W2-c (plan-7 task 7.4 dense/fused re-run), W1-e (plan-15 clean suite + r13 #s-1/#m-1/#m-2) as named sub-tasks (D-Q6). Read each bug row and each cited ch-bsd report; every sub-task carries ACs that close its finding |
| spec-t2 | `refmatrix-spec-t2` · `spec-wave-t2` | **G4** 26.5 (L9: bug-208 precondition AC; bug-202 restore checked for existence first; L37: bug-220 as its own requirement + AC, location-based classification, route-not-refuse, per the bug-220 row). **G6** 26.7 (D-Q2: AC that 25.1's curated-hook lookup survives the regroup). **G19** 26.8 (L11: ADR-0005 Appendix A MEMORY-RULES text carries the marker condition; L12: forget-flow step 5 offered at AC-8; counts re-read), 26.9 ∥ plan-27 (L10), plan-27 (L13 survey/facts refresh at 27.1, Q3 re-hosted; Ca-8). Owns `plan-26*`, `plan-27*`, `docs/adr/0005-*` |
| spec-t3a | `refmatrix-spec-t3a` · `spec-wave-t3a` | **G3** 25.1 waiver (D-Q2): plan-25 `#ordering`/`#approval-order`, task-25.1 `:22-24`/`:34`, written on THIS copy (the 25.1 branch's spec conflict is resolved at merge by the lead). **G12** new task 25.1b: rev 8's R12-R14/AC-16-18 (read `git -C /Volumes/littlebig/refmatrix-plan25-1 show task-25.1-recall-hook-byte-budget:workflow/plans/plan-25-cliquedb-field-report-tasks/task-25.1-recall-hook-byte-budget.md`), plus L15 amends, `depends-on 10.3`, R15 (bug-182) under L44's band (L39), plan-2 r9 #s-2/#m-4 riders (D-Q6, from task-19.1 `#w1c-riders`). **G13** 25.2 (L34 bands, L43 else-branch), 25.3 (L16, L43 STM/helix split). **G24's plan-25 side**: 25.4/25.5 closed as superseded by 16.5 (L42, L24), with the plan-25 task table, fixed list and `#approval-order` amended. **G28** 19.0 rest (L41), 21.2, 21.4 (D-Q5: drop plan-24 D1 hold; re-read vs bug-216's resolver); plan-19 realized-by lines (L14) and L26's freeze. Owns `plan-25*`, `plan-19*`, `task-21.2*`, `task-21.4*` |
| spec-t3b | `refmatrix-spec-t3b` · `spec-wave-t3b` (plan-10 rev 5 already merged in at `dee6f07`) | **G11** plan-10 rev 5: 10.2 re-spec against 25.1b (L15; the "still in play" line is 25.1b's, with held / over-budget members); L27 outcome rule; L17 Table A on the composite as 10.6's precondition; L30 order (only 10.3 early); Q11 → Q13/Q10 supersession (L23); CB-1, CB-6, CB-7 in `contra-b.md`. Owns `plan-10*` |
| spec-t3c | `refmatrix-spec-t3c` · `spec-wave-t3c` | **G16** 21.5 rev 4 (D-Q4): fold the R12 pilot's seven matcher changes (`workflow/measurements/task-21.5-r12-pilot-2026-11-13.md`), drop or gate `bash_name`, the R12 re-measure with the spec's bands (L35), decision row "no build until the handhold experiment reports"; CB-8/CB-9. **G17** new plan `workflow/plans/plan-28-handhold-outcome-experiment.md` + tasks from `docs/architecture/explorations/handhold-outcome-experiment.md`: arms incl. arm A × {dedupe, full} nested (L20, 10.2 R7), arm-B switch via `arms.SESSION_ARMS`, Q3 folded fully, the user-gated start, pre-registered outcomes/bands, measures only R12 explicit uses + `cited_in_answer` (L18/L27). **G30** new task: per-type evaluation of bug-216's `denotes` PageRank fold, with bands (L29), and the ADR-0004 decision-log line (L7). Owns `task-21.5*`, the new plan-28 files, `docs/adr/0004-*` (decision-log line only) |
| spec-t4 | `refmatrix-spec-t4` · `spec-wave-t4` | **G8** bug-185 freshness (L3, L4): R6 precedence, "minted earlier" never beats a same-named doc/memory, `denotes` (bug-216 R7) and pending refs (R10) join R1's batched writes, golden regenerated from post-bug-216 HEAD, gate narrowed to 26.1+26.2. **G9** 23.x body status lines (Cc-9), `#merge-order` per L1 (23.5 R9 after the 26.6 R3 residual), 23.3 freshness vs revised bug-185 (L31). **G10** 16.6 freshness vs revised bug-185 (L31). **G25** plan-17/18 body status lines and 18.2/18.3 PROVISIONAL marks vs the CONFIRMED d9 rows. **G29** 17.3 order 17.4 → 17.3 (L40), user-gated; 17.2 hosts 26.6's 19.4 R1 tick (L28). Owns `task-bug185*`, `plan-23*`, `plan-17*`, `plan-18*`, `task-16.6*` |
| spec-t56 | `refmatrix-spec-t56` · `spec-wave-t56` | **G20** new `workflow/plans/task-bug218-reinforcement-edge-direction.md` from the bug-218 row (it is "suspected": R0 confirms or refutes before any fix). **G21** 22.1a widened to a dead entity side (L6, CD-6), plan-22 body status (CD-9), 22.4 + the two merge entry points as deferral rows in `workflow/deferral_registry.md` (L22, d9j). **G23** 16.1 vs bug-216 (L5: `corpus.is_relevant` delegates to `should_ignore`, the prune keeps `!path` re-includes), plan-16 body status (CD-9). **G24's task side**: the closing lines in task-25.4/25.5 (plan-25's main file is spec-t3a's). Owns `plan-22*`, `plan-16*` (except 16.6), `task-25.4*`, `task-25.5*`, the new bug-218 spec, `deferral_registry.md` |

The lead keeps: G27 (bookkeeping, the POP rewrite, registry rows), G32 (the m1 confirm ch-bsd),
every ch-bsd spec review of this wave's output, and every merge to master. {#lead-keeps}
