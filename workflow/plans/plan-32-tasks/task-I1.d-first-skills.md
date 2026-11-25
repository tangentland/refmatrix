---
gmd: "0.1"
id: task-I1.d-first-skills
title: "Task I1.d: the first seven T3 skills, their gates and agent preloads, and C12's briefing line"
tags: [task, plan-32, instructions, skills, gate, preload, practice-tdd, release, local-units]
metadata:
  node_type: task
  status: drafting
  plan: plan-32-instruction-architecture
  created: 2026-11-24
  author: ch-architect (Fable 5.2)
---

# Task I1.d: the first skills {#root}

> Status: drafted for the spec window (L232); the lead approves. Queue row I1.d.
> Size: **small each after the first** (a skill, its bindings and fixtures); one `src/`
> string (C12). One isolated agent per batch; the lead reads the diff. Waits on
> [[task-I1.b3-dispatcher]] and on P11 ([[task-I1.b0-probes#verdicts]]). This spec is the
> first seven skills; the rest of the row is [[#second-batch]].

rel: implements -> [[refmatrix/adr-0007-instruction-architecture#contract]]
rel: implements -> [[refmatrix/adr-0007-instruction-architecture#t3-fallbacks]]
rel: implements -> [[refmatrix/adr-0007-instruction-architecture#practice-slots]]
rel: implements -> [[refmatrix/adr-0007-instruction-architecture#pointers]]
rel: part-of -> [[plan-32-instruction-architecture]]
rel: derives-from -> [[instruction-census-2026-11-24#build-list]]
rel: depends-on -> [[orchestration#release]]
rel: depends-on -> [[self-audit#questions]]
rel: depends-on -> [[plan-of-plans#queue]]

## Goal {#goal}

The procedures that were re-derived at every release, dispatch and mutation run arrive at the
call that starts them, or are already in the agent that runs them. Each has one source, a
skill; every other statement of it becomes a pointer. {#goal-body}

## The skills {#skills}

Layer: **T** the template (`src/refmatrix/templates/skills/`); **P** `practice/tdd`; **L**
refmatrix's own (`.claude/skills/`, never shipped). A gate stops the first matching call of a
context with the named checklist (at most 2,000 B) and passes the retry. {#skills-lead}

| Skill | Layer | Rows | Gate (main session unless said) | Preloaded in |
|---|---|---|---|---|
| `release-deploy` | L | R163, R036 to R039, R045, R196; L217; Q57 | an Edit of the `version` line in `pyproject.toml`, in the store tree → `#checklist-release`; Bash `git -C ~/refmatrix pull` → `#checklist-deploy` | — |
| `lane-verify` | L | R059 to R062, R194; C14 | Bash: a test run or `scripts/lane-*.sh` → `#checklist` | `ch-test-engineer`, `ch-implementer`, `ch-bsd` |
| `brief` | T | R136 | the Agent tool → `#checklist` | — |
| `bsd-pass` | T | R140, R141; B1's severity table; F4's cell | the Agent tool with `subagent_type` `ch-bsd` → `#checklist-lead` | `ch-bsd` |
| `self-audit` | T | R145 to R152 | — | `ch-implementer`, `ch-test-engineer`, `ch-architect`, `ch-bsd` |
| `dispatch-red-green` | P, slot `dispatch` | R057, R067 to R069 | the Agent tool → `#lead`, packed after `brief` | `ch-test-engineer`, `ch-implementer` |
| `mutation-loop` | P, slot `proof` | R064, R066 | any context: a Bash in-place edit of a tracked file outside the test paths (`sed -i`, `perl -pi`) → `#checklist` | `ch-test-engineer` |

- **`release-deploy`'s two checklists.** `#checklist-release`: the bump in both files; major
  or minor; **step 1b** (walk `OPEN.md`; a row fixed on `master` or ruled moves to
  `CLOSED.md`; an open BULLSHIT or GATE row on shipped code holds the release; the counts and
  `scripts/bsd-tally.py`'s lines go in the commit body); the gate by E line.
  `#checklist-deploy`: first `git -C ~/refmatrix status --short`, naming every file that
  differs (Q57 = b); the fast-forward; `daemon restart --relaunch`; `version -v`;
  `hub relaunch-fleet`, and for a stale hub `launchctl list`, `rmx hub stop`, one kickstart;
  `install-hooks --check` per fleet repo, `--apply --force` after backups; `/mcp` reconnect
  when `mcp.py` changed; a second restart for a stop-path fix; `FatalException` lines in
  `daemon.stderr.log`; the live check after backups. {#release-deploy}
- **Preloads are hand-written lists for now.** The installed agent files gain a `skills:`
  line, practice skills first; H1.c generates the lists later. Each skill here is at most
  6,000 B (`release-deploy` 10,000 B), so the largest list stays under 24,000 B. {#preloads}
- **Sources.** Each skill's text is taken from where the rule is stated today
  ([[orchestration#release]], [[orchestration#task]], [[orchestration#roles-briefs]],
  [[orchestration#task-verify]], `CLAUDE.md` `#test-discipline` rule 9, [[self-audit]],
  `ch-bsd.md` `#severity-levels`, and the memories the census rows name), then those places
  point at it (AC-7). {#sources}

## The second batch {#second-batch}

`pop-ruling`, `bug-row` (path-keyed: P6), `live-surgery` (R006: `ask` if P2 allows, else a
gate), `fleet-hooks` (R023) and the `invoked` ledger row (P8) each rest on a probe. They get
their own one-page spec when the verdicts are committed. {#second-batch-body}

## Acceptance criteria {#acceptance}

- **AC-1 Seven skills, each in its layer, each gate proven.** Every binding has `fire` and
  `pass` envelopes: packaged ones run in
  `tests/test_instruction_units.py::test_packaged_unit_fixtures`, local ones in
  `…::test_this_checkouts_local_units`, both through the generated command. Each `fire`
  envelope is shown not gated before its skill exists. {#ac-1}
- **AC-2 One graph node per skill.** A sandbox project that holds a packaged skill's source
  and its installed copy is synced by a sandbox daemon; the store holds one doc for the id.
  `…::test_a_packaged_skill_is_one_graph_node`. If it holds two, the fix is on the ingest
  path and this AC is built on the large path. {#ac-2}
- **AC-3 `bsd-pass` is the one home.** It holds `ch-bsd.md`'s severity table unchanged, the
  one-pass rules, and: "for each BULLSHIT name the self-audit question that should have
  caught it; the lead copies it into the row's `question` cell" ([[task-b1-f4-f7#d3]]). The
  summary diffs the table against `ch-bsd.md` at the base sha. {#ac-3}
- **AC-4 `release-deploy` carries L217 and Q57.** The summary maps each line of the two
  checklists to its row or ruling (R163, R036 to R039, R045, R196, L217, Q57); the lead
  reads it against [[orchestration#release]]. {#ac-4}
- **AC-5 The right text reaches the right context, once.** Fixtures show: the version edit
  from the main session in the store tree → gated with `#checklist-release`, and from a
  subagent → I1.c's deny, never both; an Agent call → `brief` then `dispatch-red-green#lead`,
  in that order, inside `instruction_pre`; with `subagent_type` `ch-bsd` →
  `bsd-pass#checklist-lead` as well; the same call again → nothing. {#ac-5}
- **AC-6 C12.** After `rmx install-hooks --apply` in a sandbox project, the generated
  `.refmatrix/CLAUDE.md` names the MCP tool `rmx_focus_note` first and the Bash form as the
  fallback when no server is connected. `tests/test_hooks.py::test_briefing_names_the_mcp_tool_first`
  (RED at base: the briefing has only the Bash form). {#ac-6}
- **AC-7 Then the pointers.** In a commit after AC-1 to AC-5 pass on the branch: `ch-bsd.md`
  `#severity-levels` and `ch-bsd.local.md`'s one-pass section; [[orchestration#task]] step
  5's severity sentence, [[orchestration#release]], [[orchestration#task-verify]] and
  [[orchestration#roles-briefs]]; the question texts of [[self-audit#questions]]; and the
  interim pointers I1.a left in the overlays: each keeps its anchor and names the skill in
  one line. `CLAUDE.md` is not touched (I1.h). `./scripts/lint-gmd.sh` exits 0. {#ac-7}
- **AC-8 A preload is seen in a real agent.** P11's script, pointed at this branch's clone,
  spawns `ch-bsd` and `ch-test-engineer`; each quotes the marker line of every skill in its
  list. The summary prints each agent's list and its bytes. {#ac-8}
- **AC-9 The gate patterns are replayed.** `rmx rules replay` over 30 days for the
  `lane-verify`, `mutation-loop` and `release-deploy` bindings, in
  `workflow/measurements/instruction-replay.md`. The ring holds no Agent-tool events, so the
  three Agent gates are not replayed; that is stated there. {#ac-9}

## Files {#files}

`src/refmatrix/templates/skills/{brief,bsd-pass,self-audit}/SKILL.md`;
`src/refmatrix/templates/practices/tdd/{dispatch-red-green,mutation-loop}/SKILL.md` and
`practice.md`; `.claude/skills/{release-deploy,lane-verify}/SKILL.md`; the generated copies
under `.claude/skills/`; the bindings (`triggers/` in each layer); `.claude/agents/{ch-bsd,ch-implementer,ch-test-engineer,ch-architect}.md`
(a `skills:` line); `src/refmatrix/hooks.py` (`CLAUDE_BRIEFING`); `tests/test_hooks.py`,
`tests/test_instruction_units.py`; then AC-7's pointer files. {#files-list}

## Risks (self-audit) {#risks}

1. **Real:** AC-8 is the real run for the preloads; for the gates the lead provokes
   `#checklist-deploy` once at the next deploy and pastes it.
2. **Wiring:** fixtures go through the generated command; the preload is proven by a spawned
   agent, not by reading the agent file.
3. **Census:** every place each rule is stated (the census's "stated in" column) is either
   an AC-7 pointer or listed for I1.h; both gates of `release-deploy`; the bare and the
   namespaced `ch-bsd` name.
4. **Bound:** a gate adds text under `instruction_pre`; three Agent-tool units together
   stay inside it (AC-5) or the lowest priority becomes a pointer line.
5. **Busy / down:** no daemon is read; AC-2's sync runs on a sandbox daemon.
6. **Guard:** each `who` and `where` on a gate has a `pass` envelope that differs only there.
7. **Loud:** a gate that fires on the wrong call costs one retry and a `gated` row the
   review reads; a preload that does not arrive is silent, which is why AC-8 exists and why
   I1.e's SubagentStop check on the self-audit section is its backstop.
8. **Handoff:** the practice's `completion` and `test-authoring` slots → I1.e and I1.f; the
   generated `skills:` lists and the preload budget check → H1.c; the security clause of
   `bsd-pass` → H1.e; `CLAUDE.md`'s copies of these rules → I1.h. Each is in that row's text
   already ([[plan-32-retriage-2026-11-24#i1-tasks]], [[plan-32-retriage-2026-11-24#h1-tasks]]).

## For the user {#for-the-user}

1. **`brief` and `lane-verify` as gates.** The ADR lets them ride beside the call if P1
   passes. A brief checklist that arrives beside the spawn is too late for that brief, and a
   lane reminder beside a test run is too late for that run. Recommended: both are gates
   whatever P1 says; the cost is one stopped call per context. The alternative is the
   `context` mode where P1 allows it.
