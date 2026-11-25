---
gmd: "0.1"
id: task-I1.b0-probes
title: "Task I1.b0: probes P1 to P11 as committed evidence, and the cost baseline of a shell-prefiltered hook (I1.b's R0)"
tags: [task, plan-32, instructions, probes, measurement, hooks]
metadata:
  node_type: task
  status: drafting
  plan: plan-32-instruction-architecture
  created: 2026-11-24
  author: ch-architect (Fable 5.2)
---

# Task I1.b0: the probes {#root}

> Status: drafted for the spec window (L232); the lead approves. Part of queue row I1.b
> ([[task-I1.b-substrate#split]]). No `src/`, no tests: a measurement on the M lane. One
> isolated agent (`scripts/agent-isolated.sh`, a local `rmxtestN` user, so the probes' hooks,
> rules and plugin live in that user's HOME and never in the user's `~/.claude`); the lead
> drives the two probes that need a permission prompt. Starts now.

rel: implements -> [[refmatrix/adr-0007-instruction-architecture#open]]
rel: part-of -> [[task-I1.b-substrate]]
rel: depends-on -> [[refmatrix/adr-0007-instruction-architecture#context-facts]]
rel: related-to -> [[task-agent-start-context#r0]]

## Goal {#goal}

Replace each "not documented" and "not verified" fact the ADR rests on with an observation
from a real Claude Code session, committed as field names, hashes and a verdict, so that no
unit is built on a guess. Each probe's outcomes and what they decide are written here, before
the run. {#goal-body}

## Method {#method}

Each probe is a throwaway project under the slot's HOME with a hand-written hook that appends
the envelope's key names, value lengths and sha256 hashes to a file, a scripted session that
provokes the event, and a **positive control** in the same session (a deny whose reason is a
nonce, a mechanism the docs verify), so "nothing observed" is told apart from "the probe is
broken". A session asks the model to repeat any nonce it was shown; the nonce is synthetic and
may be committed. Each row records the Claude Code version and whether the session was
headless or interactive; a permission behaviour seen only headless is not accepted. A probe
that cannot provoke its event inside its bound (10 minutes; P5 30) is recorded
`not observable`, with the safe default named. {#method-body}

## The probes and what each decides {#verdicts}

| # | Provoked by | Outcome → what it decides |
|---|---|---|
| P1 | a PreToolUse hook returning `additionalContext` and no `permissionDecision`, on a call that needs no permission and on one that prompts (interactive) | nonce seen and the prompt unchanged → `context` mode is built ([[task-I1.b3-dispatcher#d4]]); otherwise each unit takes its declared fallback |
| P2 | a hook returning `permissionDecision: ask`, in default and in auto mode (interactive) | a prompt in both → the `ask` kind is built and R006 is `ask`; no prompt in auto mode → R006 is a `gate` |
| P3 | an `InstructionsLoaded` hook; `CLAUDE.md`, a path rule and a skill loaded in the main session and in a subagent | `agent_id` present for a subagent's load → `loaded` rows are per context; absent → they are per session and the review says so |
| P4 | the docs and one experiment: a hook entry limited by the content of `tool_input` before any process starts | exists → the generated entries use it beside the shell prefilter; not → the shell prefilter alone |
| P5 | a subagent driven to compaction; bsd-cah r1's probe p5 (bug-307) is the starting evidence | PreCompact or SessionStart `compact` fires with `agent_id` → the per-agent marker resets a subagent's entries; not observable → the time bound of [[task-I1.b3-dispatcher#d5]] |
| P6 | a skill with `paths:`; a matching file touched in the main session and in a subagent | body nonce seen → path-keyed skills use their own `paths:`; listing only → the generated path rule ([[refmatrix/adr-0007-instruction-architecture#t3-fallbacks]]) |
| P7 | a user-level rule whose `paths:` matches a file outside the project (a memory dir) | loads → `MEMORY-RULES.md` is a user-level rule (I1.f); not → the user-level inject |
| P8 | a `Skill` call and a slash command, with a hook on every event | the event and field that carry the skill or command name → the `invoked` row's writer |
| P9 | a SubagentStart hook returning `additionalContext`; a spawned agent | the envelope's field names (is the task prompt there?) and whether the nonce reaches the subagent → [[task-agent-start-context#r0]] (I1.g) |
| P10 | a throwaway local plugin with one agent and one skill | how each is named, and whether a project agent's `skills:` may name the plugin's skill → [[refmatrix/adr-0007-instruction-architecture#dist-agent-lists]] |
| P11 (added) | a project agent whose `skills:` names a project skill holding a nonce; the agent spawned | nonce seen → the preloads of I1.d stand; not → they fall back to SubagentStart (I1.g) |

## The cost baseline {#cost}

The read gate C1 installed is already a shell-prefiltered PreToolUse command of the form the
dispatcher will use. Render it (`hooks._handoff_cmd(root, "gate", per_session=True)`) for a
`mkdtemp()` root with no gate file and run it 200 times by `/bin/bash -c` with a tool
envelope on stdin, timed around the process; time `bash -c 'exit 0'` the same way as the
floor. Bands, written before the run: {#cost-body}

- median at most 10 ms → the form stands
  ([[refmatrix/adr-0007-instruction-architecture#dispatcher-cost]]);
- median over 10 ms with a floor under it → the form is fixed in b3 (the candidate is the
  `$(cat)` subshell);
- floor over 10 ms → no shell prefilter meets the band on this machine: reported to the lead
  with P4's verdict before b3's GREEN.

## Acceptance criteria {#acceptance}

A measurement has no pytest; each AC names the committed artifact that proves it.
{#acceptance-lead}

- **AC-1 Eleven verdicts.** `workflow/measurements/instruction-probes.md` (GMD) holds one row
  per probe: version, mode, the observed field names and hashes, the control's result, and a
  verdict from the outcomes above or `not observable` with its safe default. {#ac-1}
- **AC-2 Re-runnable.** `workflow/measurements/instruction-probes/run.sh P<n>` rebuilds the
  probe's project in a fresh directory and prints its observation; the summary shows one
  re-run. It is the canary's script on a Claude Code upgrade. {#ac-2}
- **AC-3 No raw content.** The evidence holds key names, lengths, hashes, event and tool
  names and nonces only; the summary pastes a grep of the evidence directory for any other
  envelope value. {#ac-3}
- **AC-4 The baseline.** The same file holds the median, p95 and floor, the command, the
  machine's load at the time, and the band it falls in. {#ac-4}
- **AC-5 A contradiction is escalated.** A verdict that contradicts a fact
  [[refmatrix/adr-0007-instruction-architecture#context-facts]] lists as verified is tagged
  `ARCH-DRIFT` in the report and sent to ch-architect before b3's RED. {#ac-5}

## Files {#files}

`workflow/measurements/instruction-probes.md` and `workflow/measurements/instruction-probes/`
(one directory per probe: its hook, its session script, its evidence; `run.sh`). Nothing
under `src/`, `tests/` or any project's `.claude/`. {#files-list}

## Risks (self-audit) {#risks}

1. **Real:** every row is a real session; a row from the docs alone is marked `docs`.
2. **Wiring:** the probes' hooks are hand-written throwaways in a throwaway project; none is
   installed in a real project or generated by `hooks.py`.
3. **Census:** headless and interactive sessions differ (the 2026-10-20 mod probe); the
   teammate, background and forked agent forms are each tried for P3, P9 and P11 and listed.
4. **Bound:** each session has its wall bound; past it the row is `not observable`.
5. **Busy / down:** not applicable: no daemon and no store are used.
6. **Guard:** the positive control in each session.
7. **Loud:** a probe that fails to run is recorded `error`, never as `no`.
8. **Handoff:** P7 → I1.f; P9 → I1.g; P10 → H1.c and 24.7; P6 and P8 →
   [[task-I1.d-first-skills#second-batch]]. Each is named in that task's POP row.

## For the user {#for-the-user}

None. For the lead: P1's prompting half and P2 need an interactive session, driven by
`screen` in the slot's HOME.
