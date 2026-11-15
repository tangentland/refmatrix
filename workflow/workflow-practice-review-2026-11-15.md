---
gmd: "0.1"
id: workflow-practice-review-2026-11-15
title: "The workflow the lead actually runs (sessions a9b75923, 070141d0) vs CLAUDE.md, and proposed amendments"
tags: [workflow, governance, orchestration, proposal]
metadata:
  node_type: proposal
  status: applied
  created: 2026-11-15
---

# The workflow in practice, and what to amend {#root}

The user, 2026-11-15: "summarize the workflow steps you've been using. They seem to be working
well, but they diverge from what is specified in CLAUDE.md. Let's review them and amend the
instructions where need be." This file records the practice as run in the 0.83.0 / 0.83.1 /
plan-29 / plan-30 work, where it departs from the written instructions, and the amendments
proposed. **Applied 2026-11-15:** the user answered Q23-Q26 = a; A1-A6 are in
[[orchestration]], CLAUDE.md, [[tdd-governance]] and [[PLANNING_WORKFLOW]].

rel: amends -> [[claude]]
rel: amends -> [[tdd-governance]]
rel: amends -> [[PLANNING_WORKFLOW]]
rel: derives-from -> [[plan-review-2026-11-13#lead]]
rel: related-to -> [[open-questions]]

## 1. Roles {#roles}

- **The lead** (the main session) orchestrates. It writes no `src/` and no tests. It dispatches,
  rules on findings, allocates registry ids, commits by pathspec on `master`, merges, releases,
  deploys, and does every write to a live store (announced, backed up). {#roles-lead}
- **Agents** work in their own `/Volumes/littlebig/<project>-<worker>` clone, never the dev tree
  and never a git worktree. They are read-only against every live store; lookups go through
  `scripts/rmx-master` read verbs. Two agents on one branch (RED and GREEN) share it by
  `git fetch <other clone> <branch> && git merge --ff-only FETCH_HEAD`; a reviewer gets its own
  clone and never works in the implementer's while a suite runs there. {#roles-agents}
- **Planning authors run on Fable** (`model: fable`); RED, GREEN and reviews keep their
  agent's default model. {#roles-models}

## 2. Planning path (plans, task specs, revisions) {#planning}

1. ch-architect (Fable) writes the plan + every task spec, `status: drafting`, on a branch in a
   clone, from a brief that names the evidence (measurements, bugs) and the constraints.
2. **ch-bsd spec review r1**, full depth, in its own clone. Report written in its clone (or
   returned as text); the lead persists it.
3. **Lead ruling** `L<n>` in `workflow/plan-review-2026-11-13.md#lead`: every finding folded,
   deferred, or overruled, with the reason.
4. Revision round by the same author on Fable, with a per-spec fold table.
5. **Confirm-lite r2..rN** until MEH-only GO; MEHs folded before merge.
6. **Only then** the plan's user decisions (`plan-N Dk`) go to the user, each with a
   recommendation (memory `feedback_bsd_iterate_before_surfacing`). If a later measurement
   removes a decision's premise, the decision is re-asked with the number (plan-29 D23, L115).
7. Merge `--no-ff` to `master`; code-span citations become wikilinks; `status: approved`;
   plan-of-plans row; registries. A review report that links docs not yet on `master` travels on
   the plan branch until its merge.

The SDD chain (`/ch-specify → … → /ch-implement`) and `ch-alignment` / `pseudocode/` were not used
(there is no `pseudocode/` directory). {#planning-unused}

## 3. Task / bug path {#task}

1. **RED** — ch-test-engineer: failing tests from the criteria, proven RED **at base by reading
   the E lines** (the right reason, not just "failed"). Real inputs over patches; a patch of a
   dependency is registered in the mock registry.
2. **GREEN** — ch-implementer, no tests authored.
3. **Mutations** — commit first; one mutation at a time, restored in its own command;
   `__pycache__` cleared after the batch; the fix confirmed present after the restore; each
   mutation must FAIL a test, not hang it.
4. **Family run** + **one full suite on the branch**, failures compared **by E line** with the
   last release's full-suite log (`release-<ver>-full.log`), never by test name.
5. **ch-bsd over the commit range** (own clone). Ruling `L<n>`. Findings fold as a new RED → GREEN
   round; then confirm-lite. Small MEH folds may skip a further bsd round when the lead checks the
   RED→GREEN pair and the mutations itself (L114).
6. Implementation summary in the branch; registry rows (ids allocated by the lead on `master`,
   never by an agent).
7. Merge `--no-ff`; then the release.

`/ch-review` (four-phase) was not run on any of this work; ch-bsd was the only review gate.
{#task-unused}

## 4. Release and deploy path {#release}

1. Release commit on `master`: bump `pyproject.toml` + `src/refmatrix/__init__.py` only.
2. **The gating full suite runs on merged `master`** (a clone cannot see failures that need the
   dev tree's live `.refmatrix/`; memory `feedback_review_clones_cannot_see_dev_tree_failures`),
   E lines vs the previous release's log. A second branch full suite after a small fold is
   skipped (L114).
3. Deploy: ff `~/refmatrix`, `rmx daemon restart --relaunch`, `rmx version -v` (no `[DEV TREE]`),
   `rmx hub relaunch-fleet`; hub STALE → `rmx hub stop` + ONE `launchctl kickstart`;
   `install-hooks --check` (re-install only if out of sync).
4. Live verification of the release's claim (e.g. bug-216 AC-6 recount), after a backup of
   `catalog.read.duckdb` + `facts.log` + `active`. Store-changing releases need their own go.

## 5. Lead discipline {#discipline}

- **Measure before deciding**, read-only: copy `catalog.read.duckdb` to the scratchpad and open
  it with duckdb `read_only=True` under `.venv-eval` (never `Store()` on a live slot). This
  reversed D23 and sized bug-244's exposure.
- **Every ruling is an `L<n>` row; every user question a `Q<n>` or a plan `Dk`**; asked with
  AskUserQuestion, recommendation first.
- **Every defect found by anyone gets a registry row at once**, by the lead.
- **Review reports** are persisted by the lead: report file, INDEX row, `last_run.log` line,
  IMPRESSIONS bullets copied as whole blocks each ending in one `{#id}` (bug-242).
- **Long agent runs are watched by the lead**: tail the log after the expected duration (memory
  `feedback_check_the_log_when_an_agent_idles_on_a_background_run`).
- **Merge messages go through a file** (`git merge -F <file>`; `-F -` fails).

## 6. Divergences from the written instructions {#divergences}

| written | where | practice |
|---|---|---|
| Review = `/ch-review` then `@ch-bsd` | CLAUDE.md `#task-completion-workflow` 6; `#before-commit`; TDD_GOVERNANCE `#pipeline` 4 | ch-bsd only, with confirm-lite rounds and L-rulings |
| Step 0 alignment refresh with `ch-alignment` over `pseudocode/` | TDD_GOVERNANCE `#pipeline` 0 | not run; no `pseudocode/` exists |
| "Verify — full relevant tests captured to a log" | CLAUDE.md step 5 | family + branch full suite + master release suite, compared by E line |
| "Commit on the task branch, merge; deploy when a release lands" | CLAUDE.md step 10 | release commit + master full suite gate + deploy steps + live verification |
| Planning: SDD chain; plan approval = specs exist | CLAUDE.md `#agent-skill-workflow`; PLANNING_WORKFLOW | Fable architect → bsd spec rounds → rulings → user Dk → merge → approved |
| (nothing) | — | the lead/agent split, clones, read-only agents, lead-persisted reports, L-ledger |
| "Docker where applicable" | TDD_GOVERNANCE `#rules` | host venv; no Docker in this repo |
| Cleanup phase after each plan | CLAUDE.md `#cleanup-phase` | not yet exercised this cycle |

## 7. Proposed amendments {#amendments}

- **A1.** New `workflow/ORCHESTRATION.md` holds sections 1-5 above as the operating procedure.
  CLAUDE.md's `#task-completion-workflow` shrinks to a ten-line summary that points to it, so the
  file loaded every session stays short. (Q24)
- **A2.** The review gate becomes ch-bsd + L-ruling + confirm-lite to MEH-only GO; `/ch-review` is
  optional, for large `src/` changes or on request. CLAUDE.md `#before-commit` and TDD_GOVERNANCE
  `#pipeline` 4 change to match. (Q23)
- **A3.** TDD_GOVERNANCE step 0 becomes conditional: "where `pseudocode/` or an Accepted ADR
  governs the slice"; Docker wording becomes "the host venvs (`.venv-eval`)". (Q25)
- **A4.** PLANNING_WORKFLOW gains the planning path (section 2) as the default; the SDD chain stays
  listed as available, not default. (Q26)
- **A5.** CLAUDE.md `#before-commit` adds: RED proven by E lines; mutations recorded; failures
  compared by E line to the last release log; the release's gating suite runs on merged `master`.
- **A6.** CLAUDE.md `#development-commands` adds the read-only measurement rule (copy the read
  snapshot to the scratchpad, duckdb `read_only=True`), next to the "never `Store()` on a live
  `.refmatrix/`" rule.
