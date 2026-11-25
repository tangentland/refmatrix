---
gmd: "0.1"
id: task-I1.a-contradiction-edits
title: "Task I1.a: the contradiction edits (docs and overlays only), with the Q55, Q56, Q57, Q58 and L232 wordings"
tags: [task, plan-32, instructions, contradictions, docs, overlays]
metadata:
  node_type: task
  status: drafting
  plan: plan-32-instruction-architecture
  created: 2026-11-24
  author: ch-architect (Fable 5.2)
---

# Task I1.a: contradiction edits {#root}

> Status: drafted for the spec window (L232); the lead approves. Queue row I1.a.
> Size: **small**, docs and overlays only, no `src/`, no settings edit. One agent; the lead
> reads the diff. Waits on nothing. H1.b is not next, so the edits inside neutral agent files
> go here ([[refmatrix/adr-0007-instruction-architecture#implementation]]).

rel: implements -> [[refmatrix/adr-0007-instruction-architecture#contradictions]]
rel: implements -> [[refmatrix/adr-0007-instruction-architecture#r007-q57]]
rel: part-of -> [[plan-32-instruction-architecture]]
rel: derives-from -> [[plan-32-retriage-2026-11-24#i1-tasks]]
rel: derives-from -> [[instruction-census-2026-11-24#contradictions]]
rel: depends-on -> [[plan-of-plans#queue]]
rel: depends-on -> [[plan-of-plans#status-lifecycle]]

## Goal {#goal}

Remove every contradiction that an edit can remove today, so that no loaded text tells an
agent the opposite of the rule that wins. Each edit replaces the losing text with a pointer to
the winner; none restates a rule. {#goal-body}

## The edits {#edits}

| # | Where | Edit |
|---|---|---|
| C1 | `.claude/agents/general-purpose.md`, `ch-code-reviewer.md`, `ch-test-engineer.md` (`#docker-only-execution`), and any other sentence under `.claude/agents/` that states tests run in Docker only | replaced by "tests run as the project profile's `#commands` says". `ch-test-engineer.md`'s appended host-venv line moves to `ch-test-engineer.local.md`. Conditional mentions ("Docker where applicable") stay. H1.b extracts the `docker` pack from these files as they are at this task's base sha |
| C2 | `ch-test-engineer.local.md` | the `lockf` sentence becomes a pointer to `CLAUDE.md` `#test-discipline` rule 9 |
| C3 | `CLAUDE.md` `#agent-skill-workflow`; `PLANNING_WORKFLOW` `#default-planning-path` | the "ch-bsd spec rounds" chain is deleted; both point at [[orchestration#planning]] |
| C4, L232 | `CLAUDE.md` `#plans-pre-written`; `PLAN_GOVERNANCE` `#lifecycle-gates` | [[#lifecycle-text]] |
| C5 | new `.claude/agents/gmd-curator.local.md` | "In refmatrix the curator is read-only against every live store: it returns the ingest, sync and primer commands for the lead to run." The packaged and the installed `gmd-curator.md` are not touched (Q58 = b) |
| C5b | `ch-bsd.local.md` | the same rule for ch-bsd: it writes an impression memory file and never runs `rmx ingest-gmd`; the SessionStart bridge or the lead's save-state brings it in. `ch-bsd.md` `#save-impression-memory` tells it to run the ingest. Not in the census; same rule as C5 |
| C6 | `.claude/rules/bug-registry.md` | one sentence: "A subagent writes the row under an id the lead allocated in its brief; agents allocate no ids." The `paths:` switch is **not** made here ([[#c6-order]]) |
| C7 | `ch-implementer.local.md` | the version-bump line becomes "the lead bumps the version in the release commit; never on a task branch" |
| C8 | `PROJECT_PROFILE` `#commands` | "hub self-restarts on version mismatch" becomes a pointer to [[orchestration#release]] step 3 |
| C11 | [[orchestration#ledgers]] | adds "or the plan's own D label" |
| C13 | `CLAUDE.md` `#no-silent-failures` | "hooks" becomes "hooks (STM capture included)" (Q56 = a). The four masked entries change in [[task-I1.b3-dispatcher#ac-8]] |
| C14 | `CLAUDE.md` `#development-commands`, `#test-discipline`; `PROJECT_PROFILE` `#layout`; `ch-test-engineer.local.md` | every undated suite count and duration is deleted; `#test-discipline`'s sentence keeps its figure as the audit's dated measurement; `#development-commands` gains the collect command (`pytest --collect-only -q \| tail -1`) until `lane-verify` holds it |
| C15 | `ch-alignment.md`, `ch-architect.md`, `ch-performance-tuner.md`, `general-purpose.md` | "write the full report to `workflow/review-output/…`" becomes "return the full report as text; the lead persists it ([[orchestration#reports]])". An isolated agent keeps `REPORT.md` |
| C16 | `ch-code-reviewer.md` | "Docstrings on public APIs only" becomes "docstrings follow the project's convention" |
| C18 | [[task-agent-start-context]] R3 | "the 9,000-unit working budget" becomes "its channel in `hook_budget.CHANNEL_BUDGET_BYTES`" |
| C19 | `ch-test-engineer.local.md` | the pre-GREEN mutation sentence becomes "mutations come after GREEN, on the `src/` change only; RED runs them (L200); none on the small path" |

Not here: C12 ([[task-I1.d-first-skills#ac-6]], a `src/` string); C13's hook half
(I1.b); C9, C10 and C17 have no repo text to edit. {#edits-not-here}

**C4 and L232, the text.** [[plan-of-plans#status-lifecycle]] is the one statement. Both
files replace their own definition with: "`approved`: the plan is approved and its next task
has an approved one-page spec. No production code for a task before that task's spec is
approved. The five queue items after the one in flight always hold such a spec (L232). The
definition is [[plan-of-plans#status-lifecycle]]." `PLAN_GOVERNANCE`'s Complete-Plan Gate
paragraph is deleted. {#lifecycle-text}

**C6's order.** [[plan-32-retriage-2026-11-24#i1-tasks]] puts `paths:` on `bug-registry.md`
in this task. The file is always-on today only because its `globs:` key is not read, but that
is the only delivery of "after fixing a bug, append a row" (R158).
[[refmatrix/adr-0007-instruction-architecture#removal-order]] removes always-on text only after its unit is installed, and
R158's unit is I1.e's registry check. So `paths:` moves to the I1.e commit that installs that
check. {#c6-order}

## The lead's memory edits {#lead-edits}

Memory files are the lead's; each follows the amend tree of `MEMORY-RULES.md`. {#lead-lead}

- **C17** `feedback_rmxgrep_no_plain_escape`, amended: "`RMXGREP_MODE=plain` in the global
  settings is the user's standing setting and is not a violation; the value is inert at the
  shim. What stays: never `/usr/bin/grep`; a grep reading a pipe stays byte-exact." (Q57 = b)
- **R007** `feedback_refmatrix_dev_deploy_split`, amended: "refmatrix is edited only in
  `~/claude_tools/refmatrix`. The deploy tree is never edited in place. A file is copied into
  it only under a grant the user has given; a granted copy leaves it dirty, so a deploy first
  reads `git -C ~/refmatrix status --short` and names every file that differs." (Q57 = b)
- **C8** `feedback_deploy_tree_is_the_runtime`: the hub sentence is corrected to
  [[orchestration#release]] step 3. If `hub.py`'s handshake is meant to restart the hub, the
  90 s miss gets a registry row.
- **C9** `feedback_proportionate_process`: SKETCHY earns no second round (L213).
- **C10** `feedback_track_questions_by_id`: the POP's counter, across sessions.
- **C11** `feedback_plan_decisions_are_questions` and the four other superseded memories of
  [[instruction-census-2026-11-24#superseded-indexed]] lose their index lines; if the renderer
  restores a line, it waits for I1.h's index rule.
- **C13** `feedback_no_silent_failures` loses its carve-out for capture hooks.
- **C18** `reference_hook_output_cap_measured`: 9,000 becomes a pointer to
  `hook_budget.HOOK_COMMAND_BUDGET_BYTES`.

## Acceptance criteria {#acceptance}

Doc edits have no pytest of their own; each AC names the command whose output the summary
pastes. {#acceptance-lead}

- **AC-1 One lifecycle statement.** `grep -n "every task" CLAUDE.md workflow/PLAN_GOVERNANCE.md`
  finds no "every task has a spec" gate; both files carry [[#lifecycle-text]] and the link.
  {#ac-1}
- **AC-2 One planning path.** `grep -n "spec rounds\|spec review r1" CLAUDE.md
  workflow/PLANNING_WORKFLOW.md` is empty. {#ac-2}
- **AC-3 The overlays agree with the winners.** `grep -n "lockf\|Version bump\|Mutation check
  before\|5,000 tests" .claude/agents/*.local.md` shows only C2's pointer. {#ac-3}
- **AC-4 The neutral files stop contradicting.** `grep -n -i "docker" .claude/agents/*.md`
  shows no "only" or "never on host" rule; `grep -n -i "write the full report\|save reports to"
  .claude/agents/*.md` is empty; `grep -rn "public APIs only" .claude/agents/` is empty. {#ac-4}
- **AC-5 C5 without touching the packaged curator.** `git diff <base> --
  src/refmatrix/templates/agents/gmd-curator.md .claude/agents/gmd-curator.md` is empty;
  `gmd-curator.local.md` and `ch-bsd.local.md` each carry their sentence. {#ac-5}
- **AC-6 The single-site edits.** C6's sentence with `globs:` unchanged; C8's pointer; C11's
  clause; C13's clause; C18's line; and `grep -n "~13 min\|1380\|~60 min" CLAUDE.md
  .claude/PROJECT_PROFILE.md .claude/agents/` is empty. {#ac-6}
- **AC-7 The gates.** `./scripts/lint-gmd.sh` exits 0. The verify set passes on a lane: the
  nine repo guards plus every test file that names an edited doc (`grep -l` over `tests/` for
  each edited filename; the list is in the summary). {#ac-7}
- **AC-8 The memory edits are done and findable.** The lead checks each amended memory with
  `rmx memory recall` on a phrase unique to the new text. {#ac-8}

## Files {#files}

`CLAUDE.md`; `.claude/PROJECT_PROFILE.md`; `.claude/rules/bug-registry.md`;
`.claude/agents/{general-purpose,ch-code-reviewer,ch-test-engineer,ch-alignment,ch-architect,ch-performance-tuner}.md`;
`.claude/agents/{ch-test-engineer,ch-implementer,ch-bsd}.local.md`;
`.claude/agents/gmd-curator.local.md` (new); `workflow/ORCHESTRATION.md`,
`PLANNING_WORKFLOW.md`, `PLAN_GOVERNANCE.md`; `workflow/plans/task-agent-start-context.md`.
No `src/`, no `tests/`, no `settings*.json`. {#files-list}

## Risks (self-audit) {#risks}

1. **Real:** each AC's grep is run and pasted; the lint run is pasted.
2. **Wiring:** an overlay reaches its agent only because the agent file says to read it; the
   new `gmd-curator.local.md` is checked by reading `gmd-curator.md`'s profile section.
3. **Census:** before each edit, `grep -rn` the losing phrase over `CLAUDE.md`, `.claude/`,
   `workflow/*.md` and `docs/`; the summary lists every site found and edited. The census
   table ([[instruction-census-2026-11-24#contradictions]]) is the checklist, not the search.
4. **Bound:** not applicable: no call is added.
5. **Busy / down:** not applicable.
6. **Guard:** not applicable: no guard is added; the greps are one-time proofs.
7. **Loud:** a `CLAUDE.md` edit changes what every session loads; the diff is read by the
   lead before the merge.
8. **Handoff:** `paths:` on `bug-registry.md` goes to I1.e ([[#c6-order]]; the lead adds the
   clause to that row). C13's clause states a rule the installed hooks break until window 1
   ([[task-I1.b3-dispatcher#ac-8]]). The pointer targets `lane-verify`, `mutation-loop` and
   `release-deploy` replace C2's, C19's and C8's interim pointers in
   [[task-I1.d-first-skills#ac-7]].

## For the user {#for-the-user}

None: Q55 to Q58 and L232 decide every call in this task. For the lead: [[#c6-order]] moves
one clause from the I1.a row to the I1.e row; C5b is one edit beyond the census's list.
