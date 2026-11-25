---
gmd: "0.1"
id: task-I1.b-substrate
title: "Task I1.b: the instruction substrate, split into four specs (probes; units and the parity gate; marker and ledger; the dispatcher)"
tags: [task, plan-32, instructions, hooks, substrate, split]
metadata:
  node_type: task
  status: drafting
  plan: plan-32-instruction-architecture
  created: 2026-11-24
  author: ch-architect (Fable 5.2)
---

# Task I1.b: the substrate {#root}

> Status: drafted for the spec window (L232); the lead approves. Queue row I1.b.
> One page cannot hold it, so it is four specs. This page is the split, the order and the
> constraints all four share.

rel: implements -> [[refmatrix/adr-0007-instruction-architecture#generation]]
rel: implements -> [[refmatrix/adr-0007-instruction-architecture#dispatcher]]
rel: implements -> [[refmatrix/adr-0007-instruction-architecture#telemetry]]
rel: part-of -> [[plan-32-instruction-architecture]]
rel: derives-from -> [[plan-32-retriage-2026-11-24#i1-tasks]]
rel: depends-on -> [[plan-of-plans#queue]]

## The split {#split}

| Spec | Builds | Size, lane | Waits on |
|---|---|---|---|
| [[task-I1.b0-probes]] | R0: probes P1 to P11 as committed evidence, and the cost baseline of a shell-prefiltered hook | no `src/`; M lane; starts now | nothing |
| [[task-I1.b1-units-and-check]] | the unit schema, the compiler and the compiled file, the fixture runner, `rmx rules replay`, and `install-hooks --check` over every instruction artifact including the git hooks (bug-209) | large; T | nothing (agent and command drift is printed, not failed, until H1.c: [[task-I1.b1-units-and-check#agents-leg]]) |
| [[task-I1.b2-marker-and-ledger]] | 10.3's compaction marker with four deltas; the instruction ledger on a helper shared with the handoff ledger; the `loaded` writer; the `instructions` view of `rmx telemetry --context` | large; T | nothing; P3 for one field |
| [[task-I1.b3-dispatcher]] | `rmx rules fire`, one generated entry per event behind a shell prefilter; deny, gate, and the probe-gated ask and context modes; inject once; the cap channels; counted failures; C13's hook half | large; T | b1, b2; P1, P2, P4, P5 |

b0, b1 and b2 run beside each other; b3 is last. {#split-order}

## Shared constraints {#constraints}

- **No unit ships here.** The first units are [[task-I1.c-first-denies]] and
  [[task-I1.d-first-skills]]. b1 to b3 are tested on units written into a sandbox project's
  local layer, the path a consumer uses. `check` units compile in b1 and are run by I1.e's
  `rmx rules check`; the `spawned` row is I1.g's. {#c-no-units}
- **No unit that depends on a probe is built before the probe passes.** Each probe-gated mode
  is switched by a constant that cites the committed evidence
  ([[task-I1.b0-probes#verdicts]]). {#c-probes}
- **New modules.** The code is new modules beside `hooks.py`; `cli.py` gains thin
  registrations only, merged before queue row 4's sha or after 29.5
  ([[plan-of-plans#queue-quiet]]). `install-hooks` lives in `cli.py`: b1 changes
  `hooks.check`, not the command body, where it can. {#c-modules}
- **Each of b1, b2, b3 is a large change** ([[orchestration#task]]): RED and GREEN in separate
  hands, mutations on the `src/` change, one ch-bsd pass at its merge. Tests go through the
  generated hook command with the envelope on stdin (`tests/task21_1_support.py`), in a
  sandbox project under a short `mkdtemp()` root. {#c-large}
- **A window is a recorded option, not a held merge.** The generator gains one recorded
  option in `.claude/rmx-hooks.json`, `instructions`: the list of events whose instruction
  entries are rendered. A flags file without the key renders exactly as today, so merging b2
  and b3 changes no installed hook, `install-hooks --check` stays clean here and in every
  fleet repo, and no branch carries a regenerated `settings.json` (this replaces 10.3's
  "regenerated in the task's clone" line). `--apply` keeps the recorded value; only an
  explicit `--instructions <events>` changes it. A unit bound to an event that is not enabled
  is compiled, inert, and printed by `--check` as inert. {#c-flag}
- **Install window 1** is `rmx install-hooks --apply --instructions
  PreToolUse,PostToolUse,PreCompact,SessionStart,InstructionsLoaded` in the dev tree, on the
  user's go, after b3 and the first denies: b2's two marker entries and the
  `InstructionsLoaded` entry, b3's dispatcher entries and the four unmasked focus entries.
  Window 2 adds `Stop`, `SubagentStop` and `SubagentStart`. After window 1 a new unit on an
  enabled event goes live when its branch's regenerated compiled file merges; the lead's diff
  read is that gate. A consumer's windows are H1.f's. {#c-window}
- **C2 first.** b2 and b3 edit `hooks._claude_hook_block`, which C2 (`task-hook-writes-queue`)
  changes; their RED bases on `master` after C2 merges. {#c-c2}

## ADR amendments these specs carry {#adr-amendments}

Recorded in [[refmatrix/adr-0007-instruction-architecture#amend-7]], for the lead's read:
the once-ledger is one file per key in 10.3's directory, not one JSON file; the marker is
per context, with a time bound on a subagent's entries if P5 cannot show its compaction
fires a hook; a gate denies only after its entry is written; an install window is the
recorded `instructions` option; probe P11 is added; agent and command drift is printed, not
failed, until H1.c; `paths:` on `bug-registry.md` moves from I1.a to I1.e. {#adr-amendments-body}

## For the user {#for-the-user}

None at this level; each sub-spec lists its own.
