---
gmd: "0.1"
id: handoff
title: "Session Handoff for refmatrix"
tags: [handoff, session]
metadata:
  node_type: handoff
---

# Session Handoff for refmatrix {#root}

Date: 2026-11-25 (session 8adeba5c). **0.85.1 is deployed.** Master `f011677c`. The previous handoff
(2026-11-15) is archived as [[handoff-025-0851-c1-handoff-0085]].

rel: supersedes -> [[handoff-025-0851-c1-handoff-0085]]
rel: depends-on -> [[plan-of-plans#queue]]
rel: depends-on -> [[plan-of-plans#ledgers]]
rel: depends-on -> [[orchestration]]

## Active goal {#active-goal}

**`/goal finish the development schedule to reach the beginning of the mod transition`** (set
2026-11-25, L238): the POP queue through row 16 (the plan-24 freshness revision, approved); row 17
(mod start) is the end. Restore with that exact `/goal` text. Open questions: Q67-Q69 (not
blocking; I1.c/I1.d outside the window). Approvals standing: **the next release's deploy** (C2 +
bug-318, L239) and **the curator fleet rollout** (after H1.a releases, L240). {#active-goal-body}

**Agents in flight at save** (each in its own clone; read the report, then continue the pipeline):

| agent | work | where | next for the lead |
|---|---|---|---|
| bsd-c2 | one ch-bsd pass on C2 `04c25731..9afff800` | `/Volumes/littlebig/refmatrix-bsd-c2` (its probe test failed: a finding) | persist report, OPEN rows; fold or merge; full suite on merged master; release + deploy (L239) |
| ~~build-h1a~~ | H1.a template reconcile (bug-319) — **merged `ec537111`** | `/Volumes/littlebig/refmatrix-h1a` | done; ships in the C2 release; then the curator fleet rollout, Q70, Q71 |
| build-b1 | B1 F4/F7 | isolated `rmxtest3` (`scripts/agent-peek.sh 3 build-b1`) | merge; write the F7 memory fold from `workflow/review-output/b1-f7-fold.txt` + bridge |
| build-i1a | I1.a contradiction edits | `/Volumes/littlebig/refmatrix-i1a` | merge; apply `workflow/review-output/i1a-memory-edits.md` (memory edits are the lead's) |
| p1b-review | P1 (b) proportionality review (Fable) | `/Volumes/littlebig/refmatrix-p1b` | merge the review; its cuts go to the user as Q ids |
| red-i1b1 | I1.b1 RED | `/Volumes/littlebig/refmatrix-i1b1-red` | GREEN (ch-implementer) in a separate clone, mutations, one bsd pass |
| t09a-probe | T0.9 (a) Docker probe | `/Volumes/littlebig/refmatrix-t09a` | read the band; (b) per its action |

## This session {#did}

- **C1** (compaction as a handoff) merged, released in 0.85.0/0.85.1; its first live compaction
  exposed **bug-318** (handoff over the Read cap, junk milestones) → fixed parts 1-2, merged
  `4ae4ecef` after ch-bsd r1 + confirm + lead verify; part 3 (agents in flight) open with the lead.
- **ADR 0007 instruction architecture: Accepted** (L220-L230): enforce > inject at trigger >
  always-on; TDD as the default replaceable practice pack (L229); mandatory 30-day context review
  (L225); project-local unit layer (L227); stack packs (L228); PRIMER improved, never cut (L224).
- **Admitted-items audit** + POP rewrite to the re-triage (L231); **five-item spec window** of
  queue rows (L232, L233), specced and approved (L234, L235). **I1.b0 probes done** (L240).
- **bug-309 holder measured** (spy309b: per-concept upsert in `ingest_gmd_paths` holds the lock up to
  ~88 s); **bug-319** (fleet curator pre-task-3.7) → H1.a now (L237).
- Status line shows the rmxtestN lanes and agents (`scripts/lane-status.sh`).

## Next {#next}

1. Collect the in-flight reports above; persist/merge in order C2 → H1.a → B1 → I1.a.
2. Release (major; full suite on merged master by E line vs 0.85.1) → deploy (approved, L239) →
   curator fleet rollout (L240) → Q70 cat-herder commit → Q71 user-level curator removal.
3. Lead-owed probes before I1.b3: P1b and P2 (interactive; `workflow/measurements/instruction-probes/run.sh P1b|P2`), teammate forms of P3/P9/P11.
4. I1.b2 RED when a lane frees; I1.b3 after b1/b2; refill the spec window (L232) as rows enter.

## Open {#open}

- **Not pushed:** master is ahead of `origin/main`; the user pushes.
- bug-318 part 3 (agents in flight in the handoff) — lead.

## Resume {#resume}

1. Read the compaction handoff file if one is named; `/recall-state`; this file; [[plan-of-plans#queue]].
2. `ListAgents`; for each row above: alive → wait; done → read its report/log yourself.
3. Lanes: `scripts/lane-status.sh`. Never the dev-venv `rmx` against a live store.
