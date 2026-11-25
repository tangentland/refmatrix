---
gmd: "0.1"
id: agent-brief-spec-window-3
title: "Brief: spec window 3 (L232): I1.c, I1.d, I1.e, I1.g, I1.f, one page each"
tags: [agent-brief, planning, plan-32, i1, spec-window]
metadata:
  node_type: brief
  created: 2026-11-25
---

# Spec window 3 {#root}

rel: implements -> [[plan-of-plans#status-lifecycle]]
rel: depends-on -> [[orchestration#planning]]

**Why now.** The head is I1.b: I1.b1 is in its fold (verify and a confirm-lite running), and
I1.b2 and I1.b3 are approved (L234). The five queue rows after it are I1.c, I1.d, I1.e, I1.g
and I1.f, and none has an approved spec (L232, L233: a window item is a queue row, its next
task specced). The user said "do the specs", 2026-11-25. {#why}

## The work {#work}

One spec per row, its next task, under `workflow/plans/plan-32-tasks/` (I1.g's is
`workflow/plans/task-agent-start-context.md`, already `drafting`):

| Row | Spec | Start from |
|---|---|---|
| I1.c | `task-I1.c-first-denies.md` | the 152-line draft (92ec1050): rewrite to one page scaled |
| I1.d | `task-I1.d-first-skills.md` | the 158-line draft: same |
| I1.e | `task-I1.e-first-checks.md` (new) | the POP row, the census, ADR 0007 |
| I1.g | `task-agent-start-context.md` | the 82-line draft (23a02b35) plus L226's pull-in, the P3/P9/P11 verdicts |
| I1.f | `task-I1.f-rules-and-nested.md` (new) | the POP row, L229 (`practice/tdd`'s `test-authoring` unit) |

{#rows}

Each spec follows `workflow/ORCHESTRATION.md` `#one-page-scaled` (L244, Q77): goal, the
acceptance criteria (each with the test that proves it, through the entry point users call),
the files, the risks (answering the self-audit for this change), and the `src/` mutation table.
No fold tables, no revision history. A rewritten draft carries its criteria table and mutation
table over word for word where the criterion survives (L244's script check); say which rows
were dropped and why in your report, not in the spec. Set `metadata.status: approved-pending`
in each file; the lead sets `approved` after reading. {#shape}

## Inputs to read first {#inputs}

- `workflow/plan-of-plans.md`: rows I1 to I1.i and H1.c (the `{#queue}` table), rulings L214 to
  L246, especially L226 to L229, L234, L235, L240 (the I1.b0 probe verdicts: P3, P4, P6, P7, P8,
  P9, P11 change what a unit can rely on), L241 (per-file semver on packaged instructions, built
  in H1.c), L246 (the I1.b1 fold calls).
- `docs/adr/0007-instruction-architecture.md` and the census it cites.
- **I1.b1 as built, not merged yet:** `/Volumes/littlebig/refmatrix-i1b1-green`, branch
  `task-I1.b1-units-and-check` at `87a599c4`. Read `src/refmatrix/instructions.py` (the unit
  format, `KIND_DIR`, layers, refusals, fixtures, `rules replay`) and
  `workflow/agents/fold-i1b1.md` `#rulings` on master. Specs build on that unit format; a spec
  that needs a change to it names the change as a criterion, not an assumption.
- `workflow/plans/plan-32-tasks/task-I1.b2-marker-and-ledger.md` and
  `task-I1.b3-dispatcher.md` (approved): what the dispatcher and ledger will provide.
- The bsd-i1b1 r1 report `workflow/bullshit/2026-11-25-0751-i1b1-r1-2f392131.md`: b-1 (replay
  cannot measure `content`/`new_string` binds) bears on I1.c's pre-ship replays; m-5 (H1.c
  unspecced) on any "printed, not failed until H1.c" clause.

{#inputs-list}

## Rules {#rules}

- Planning only: no `src/`, no tests. Work in `/Volumes/littlebig/refmatrix-spec-window`; first
  `git fetch /Users/tholley/claude_tools/refmatrix master` and branch `spec-window-3` from that
  sha. Commit there; never touch the dev tree, never push.
- Look things up with `/Users/tholley/claude_tools/refmatrix/scripts/rmx-master <verb>` or the
  read-only MCP tools. Read-only against every live store; never `find /`.
- Run `./scripts/lint-gmd.sh` in the clone: zero errors.
- **Open decisions** go in each spec's `#open` section as a choice with your recommendation and
  why; do not assign Q ids (the lead does). Decide what the existing rulings already decide.
- Report as text (or a file in the clone's `workflow/review-output/` with the path): the
  sha, each spec's prose size against its one-page budget, criteria and mutation counts, the
  dropped draft rows with reasons, and the open decisions with recommendations.

{#rules-list}
