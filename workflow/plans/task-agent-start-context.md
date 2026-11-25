---
gmd: "0.1"
id: task-agent-start-context
title: "Task I1.g: agent-start context: the SubagentStart dispatcher entry gives every subagent its rules, the primer and a recall for its brief"
tags: [task, plan-32, hooks, subagents, context, recall, instructions]
metadata:
  node_type: task
  status: approved
  plan: plan-32-instruction-architecture
  created: 2026-11-14
  updated: 2026-11-25
  author: ch-architect (Fable 5.2)
---

# Task I1.g: agent-start context for subagents {#root}

> Status: rewritten 2026-11-25 for the spec window (L232). Decided by the user as Q15 option
> 2; pulled in from post-mod by L226 as queue row I1.g; its probe is done (L240: P9, P11, P3).
> The lead approves. **Large** (hook output is a shared path): RED and GREEN in separate
> hands, mutations, one ch-bsd pass. Waits on [[task-I1.b3-dispatcher]]. Its entry goes live
> at install window 2.

rel: implements -> [[refmatrix/adr-0007-instruction-architecture#contract]]
rel: implements -> [[refmatrix/adr-0007-instruction-architecture#ledger-writers]]
rel: implements -> [[refmatrix/adr-0007-instruction-architecture#amend-8]]
rel: part-of -> [[plan-32-instruction-architecture]]
rel: derives-from -> [[open-questions#answered-37b7498f]]
rel: depends-on -> [[task-I1.b0-probes#verdicts]]
rel: depends-on -> [[task-I1.b2-marker-and-ledger#d7]]
rel: depends-on -> [[plan-of-plans#queue]]

## Goal {#goal}

Measured 2026-11-14 over 30 subagent transcripts: 4 of 30 saw any injected refmatrix
context, and 522 of their 662 `rmx` calls were greps that fall back to `rg` in a clone. The
session's prompt scan and SessionStart recall never fire for a subagent. After this task a
subagent starts with the rules that bind every agent, the top of the primer and the memories
that match its brief, and each start is a ledger row. {#goal-body}

The probe this task began with is done: [[task-I1.b0-probes#verdicts]] P9 names the
SubagentStart envelope's fields and shows that injected context reaches the subagent. {#r0}

## What is built {#design}

- **D1 The entry is the dispatcher's.** `rmx rules fire --event SubagentStart` is rendered
  when `SubagentStart` is in the recorded `instructions` option. `hook_budget` gains
  `agent_start` (9,000 B) with its command row. {#d1}
- **D2 Three labelled blocks, the most important first.** (1) The inject units bound to
  `SubagentStart` for this agent type. Two ship here: `agent-lookups` (R137, refmatrix's own:
  the store answers for `master`; look things up with `scripts/rmx-master` read verbs or the
  read-only MCP tools; a clone's own changes are read from its files) and
  `agent-no-registry-ids` (R161, template). (2) The top of `.refmatrix/PRIMER.md`. (3) The
  recall for the brief. {#d2}
- **D3 A SubagentStart inject needs no fallback.** P9 showed `additionalContext` from
  SubagentStart reaching foreground, background and forked agents. So `mode: context` on that
  event compiles and is delivered whatever `CONTEXT_VERIFIED` says; on every other event
  I1.b1's refusal stands. A change to `instructions._check_probes` and `_outcome`. {#d3}
- **D4 The parent makes the recall.** The SubagentStart envelope holds no task prompt (P9);
  the prompt is in the parent's PreToolUse on `Agent`. There the dispatcher runs the recall
  for `tool_input.prompt` (`--k 8 --scope both --pack`, bounded at 3 s, a knob) and writes
  the pack to `stm/<session>.emitted/spawns/`, one file per call, named by time and
  `subagent_type`. SubagentStart takes the oldest file for its session and agent type and
  deletes it; a file older than 120 s is reaped, never delivered. A busy or absent daemon
  leaves the skip line in the file. SubagentStart itself never calls the daemon. Two spawns
  of one type made in the same moment may swap packs. {#d4}
- **D5 The ladder.** Over the channel, the recall block becomes one pointer line first; then
  the primer is cut from its tail; units follow I1.b3's overflow rule. {#d5}
- **D6 The rows.** One `spawned` row per start (agent type, bytes, the units carried, the
  cause of any skip or drop) and one `preloaded` row per skill in that agent file's `skills:`
  list; an agent type with no file here gets none, with the cause. No prompt text is written
  to the ledger. {#d6}
- **D7 It never fails a spawn.** Any error ends at exit 0 with what could be built, and is
  counted by I1.b3's failure counter. {#d7}
- **D8 The recall's cost has a band, written before the run.** The added wall time of the
  parent's PreToolUse per spawn, over 20 spawns on an idle daemon: a p95 of at most 1 s →
  the recall ships; over it → the recall block is left out of window 2 and the numbers go to
  the user. {#d8}

## Acceptance criteria {#acceptance}

Through the generated PreToolUse and SubagentStart commands, each run by `/bin/bash -c` with
its envelope on stdin, in a sandbox project with a sandbox daemon and a seeded memory. The
cases extend `tests/test_instruction_dispatch.py`. {#acceptance-lead}

- **AC-1 Generated config.** With `SubagentStart` enabled there is exactly one SubagentStart
  entry; without it none; `--check` is clean after `--apply` in both; the import-time budget
  check covers `agent_start`. `tests/test_hooks_reproducible.py`. {#ac-1}
- **AC-2 The three blocks, in order.** After the PreToolUse command is fired with an `Agent`
  envelope whose prompt names the seeded memory, the SubagentStart command for that agent
  type returns `additionalContext` holding the units, then the primer, then a recall block
  that names the memory, each labelled. `…::test_agent_start_blocks`. {#ac-2}
- **AC-3:** with the daemon down, the payload carries the skip line and the primer block; exit 0.
- **AC-4 The cap, and what goes first.** On a fixture whose units, primer and recall exceed
  the channel: the payload is within it, the recall is a pointer line, the primer is whole or
  cut from its tail, the units are whole, and the `spawned` row names the drop.
  `…::test_agent_start_ladder[case]`. {#ac-4}
- **AC-5 The rows.** A start writes one `spawned` row with the agent type, the bytes and the
  unit ids; an agent file with a `skills:` list writes one `preloaded` row per skill; an
  unknown agent type writes none and says why. No row holds prompt text.
  `…::test_agent_start_rows[case]`. {#ac-5}
- **AC-6 The right pack reaches the right start.** Two pending calls of different agent
  types: each start gets its own. No pending call: the payload says `recall: none pending`
  and still carries the units and the primer. A file past 120 s (the clock knob) is reaped
  and not delivered. `…::test_spawn_pack_pairing[case]`. {#ac-6}
- **AC-7 Busy is not absent.** With the writer held by C2's fixture, the parent's PreToolUse
  command returns inside its bound and the start's payload carries the skip line.
  `…::test_agent_start_busy`. {#ac-7}
- **AC-8 The fallback rule moves for one event only.** A `context` inject bound to
  `SubagentStart` with no `fallback` compiles; the same on PreToolUse is still refused.
  `tests/test_instruction_units.py::test_apply_refuses` and a new accept case. {#ac-8}
- **AC-9 Seen in real agents.** P9's script, pointed at this branch's clone with the entry
  enabled, spawns a foreground, a background and a forked agent; each quotes the first line
  of `agent-lookups`. The summary pastes the three and D8's measured band. {#ac-9}
- **AC-10 A failure never reaches the spawn.** With an unreadable compiled file, and with an
  unwritable `spawns/` directory, both commands exit 0, the start returns what it could
  build, and the failure counter gains a row. `…::test_agent_start_failures[case]`. {#ac-10}

## Mutations {#mutations}

| # | Mutation | Must fail |
|---|---|---|
| M1 | the SubagentStart entry is not generated | AC-1 |
| M2 | the recall block is placed before the units | AC-2 |
| M3 | SubagentStart calls the daemon itself when no pack is pending | AC-3 |
| M4 | the primer is dropped before the recall | AC-4 |
| M5 | no cap on the payload | AC-4 |
| M6 | the `spawned` row is not written | AC-5 |
| M7 | prompt text is written to a row | AC-5 |
| M8 | the pairing ignores the agent type | AC-6 |
| M9 | a stale pack is delivered | AC-6 |
| M10 | no skip line when the daemon is busy | AC-7 |
| M11 | the recall has no bound | AC-7 |
| M12 | a fallback is demanded at `SubagentStart`, or not demanded at PreToolUse | AC-8 |
| M13 | a failure exits non-zero | AC-10 |

## Files {#files}

| File | Change |
|---|---|
| the dispatcher module (I1.b3's) | the SubagentStart payload, the PreToolUse `Agent` step, the pairing, the rows |
| `src/refmatrix/instructions.py` | D3 |
| `src/refmatrix/hooks.py`, `src/refmatrix/hook_budget.py` | the entry; the channel and its command row |
| `.claude/triggers/agent-lookups.md`, `src/refmatrix/templates/triggers/agent-no-registry-ids.md` | the two units |
| `tests/test_instruction_dispatch.py`, `test_instruction_units.py`, `test_hooks_reproducible.py` | the ACs |
| `docs/INTEGRATION.md` | the hooks section |

## Risks (self-audit) {#risks}

1. **Real:** AC-9 is the run with real agents; the lead repeats one spawn in the dev tree at
   window 2 and pastes the `spawned` row.
2. **Wiring:** every AC fires the generated commands; the payload builder is called directly
   only in addition.
3. **Census:** the agent forms: foreground, background and fork are observed; a teammate is
   not, and a fork has no `skills:` list, so it writes no `preloaded` row. The other
   PreToolUse producers on `Agent` (I1.d's three gates) run in the same command; a gated call
   still writes its pack, and the retry replaces it. Both stores a recall may answer from
   (`--scope both`).
4. **Bound:** the parent's step is one recall under 3 s with `retries=0`; SubagentStart reads
   files only. The worst case added to a spawn is that bound, once.
5. **Busy / down:** AC-7 and AC-3, on a real held writer and with no daemon.
6. **Guard:** the stale branch, the no-pending branch and the unknown-agent branch are each
   reached by real files and envelopes (AC-5, AC-6).
7. **Loud:** a skip is a line in the payload and a cause on the row; an error is counted and
   said at the next SessionStart. Nothing is printed into the spawn but the payload.
8. **Handoff:** the overlay rendered as `<role>-local` and the generated `skills:` lists →
   H1.c; the review's reading of `spawned` and `preloaded` rows → I1.i; the names-only
   dedupe between this recall and the prompt recall → plan-10, post-mod.

## Open decisions {#open}

None. D8's band decides whether the recall block ships; only a reading over it goes to the
user.
