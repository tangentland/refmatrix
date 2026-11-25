---
gmd: "0.1"
id: instruction-probes-2026-11-25
title: "Instruction probes P1-P11 and the prefilter cost baseline (I1.b0), Claude Code 2.1.331"
tags: [measurement, plan-32, probes, hooks, instructions]
metadata:
  node_type: measurement
  created: 2026-11-25
---

# Instruction probes P1 to P11 and the cost baseline {#root}

rel: implements -> [[task-I1.b0-probes]]
rel: evidence-for -> [[refmatrix/adr-0007-instruction-architecture#open]]
rel: related-to -> [[refmatrix/adr-0007-instruction-architecture#context-facts]]

Every row below is a real `claude -p` session on **Claude Code 2.1.331** (macOS arm64, slot user
`rmxtest1`, throwaway projects under `~/agents/probes-b0/work`), headless unless the row says
otherwise. A verdict that rests on a permission behaviour seen only headless is not accepted
([[task-I1.b0-probes#method]]); P1's prompting half and P2 are therefore `pending (lead,
interactive)`. Each session carries a positive control. No probe contradicts a fact the ADR lists
as verified: **no `ARCH-DRIFT`** (see [[#drift-none]]). {#lead}

## Verdicts {#verdicts}

| # | Version / mode | Observed (key paths; hashes in the evidence) | Control | Verdict → decision |
|---|---|---|---|---|
| P1 no-prompt half | 2.1.331 headless | PreToolUse hook returned `additionalContext`, no `permissionDecision`, on an allowed `Bash` call: the nonce is in the transcript as an `attachment` of type `hook_additional_context` and the model repeated it | a second hook's deny reason nonce was repeated (yes) | **context delivered without a decision** → `context` mode is buildable, **provisional** until P1b shows the permission prompt is unchanged |
| P1b prompting half | interactive | not run | | `pending (lead, interactive)`: `run.sh P1b` builds the project and prints the steps |
| P2 | interactive | not run | | `pending (lead, interactive)`: `run.sh P2` builds the project and prints the steps |
| P3 | 2.1.331 headless; main, foreground, background, fork | `InstructionsLoaded` envelope keys: `agent_id, agent_type, cwd, effort.level, file_path, globs, hook_event_name, load_reason, memory_type, parent_file_path, prompt_id, session_id, transcript_path, trigger_file_path`. A path rule loaded by a subagent's Read has `agent_id` + `agent_type` (`p3agent` / `fork`); the main session's loads have neither. `memory_type` is only `User` or `Project`: **a skill load produced no `InstructionsLoaded` row** (Skill tool called in the main session and in the subagent). A subagent gets no `session_start` rows of its own | main: PreToolUse deny nonce repeated (yes); rule nonce reached main, fg, bg and fork subagents (yes) | `agent_id` present for a subagent's load → **`loaded` rows are per context** (rules and CLAUDE.md-family files); skills have no `loaded` row, so a skill's `invoked` row comes from P8. Teammate form: `not observable` (headless: the model found no team tool, replied `TEAMS-UNAVAILABLE`; safe default: treat a teammate as a subagent, key by `agent_id`) |
| P4 | 2.1.331 headless | a `Bash` hook entry with `"if": "Bash(echo p4hit*)"` ran its logger 1 time for 3 Bash calls; the unfiltered twin ran 3 times; the filtered deny entry ran once, on its match | the unfiltered entry (3/3) shows the logger runs; the filtered deny's nonce was repeated (yes) | **exists** (`if`, permission-rule syntax, on a hook entry; the logger process never ran for a non-match) → generated entries use `if` beside the shell prefilter. Source: experiment only; not checked against the docs by this agent |
| P5 | 2.1.331 headless, `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=20`, bound 30 min (took 104 s) | the subagent compacted 3 times: `PreCompact` ×3 (`trigger=auto`), `PostCompact` ×3 and `SessionStart` `source=compact` ×3, **every one with `agent_id` and `agent_type=p5agent`**; the main session had no compaction (0 boundary records); one `compact_boundary` in a subagent transcript | the `SubagentStart` record (same `agent_id` key) and the lead's `SessionStart source=startup` (no `agent_id`) in the same run | **fire inside a subagent with `agent_id`** → the per-agent marker resets a subagent's entries on `PreCompact` / `SessionStart compact`; the time bound of [[task-I1.b3-dispatcher#d5]] is not needed. Confirms bsd-cah r1's p5 (bug-307) |
| P6 | 2.1.331 headless; main and subagent | a skill with `paths: ["p6dir/**"]`, a matching file Read: the skill-body nonce was **not** seen, in the main session or in the subagent (not in the transcript either); the listing change was not examined | a path rule with the same `paths:` delivered its nonce on the same Read in both (yes) | **body not loaded** → path-keyed skills use the generated path rule ([[refmatrix/adr-0007-instruction-architecture#t3-fallbacks]]) |
| P7 | 2.1.331 headless | a user-level rule (`~/.claude/rules`) with `paths:` as an absolute glob, as `**/memory/*.md` and as `~/…/**`, a file outside the project Read (with and without `--add-dir`): **none loaded** | a user-level rule with `paths: p7inside/**` loaded on a file inside the project (yes) | **not loaded** → `MEMORY-RULES.md` is delivered by the user-level inject, not a user-level rule (I1.f). The rule files were removed after the run |
| P8 | 2.1.331 headless, hook on 20 events | **Skill tool:** `PreToolUse` and `PostToolUse` with `tool_name=Skill`, `tool_input.skill` = the name (`PostToolUse` also `tool_response.commandName`). **Slash command and `/skill`:** `UserPromptExpansion` with `command_name`, `command_args` and `prompt`; `UserPromptSubmit` carries the raw `prompt` only; **no PreToolUse for a slash-invoked skill** | `SessionStart`, `Stop`, `SessionEnd` fired in every session | the `invoked` row has **two writers**: `PreToolUse`/`PostToolUse` on `Skill` (field `tool_input.skill`) and `UserPromptExpansion` (field `command_name`) |
| P9 | 2.1.331 headless; foreground, background, fork | `SubagentStart` keys: `agent_id, agent_type, cwd, hook_event_name, prompt_id, session_id, transcript_path` — **no task prompt**. The prompt is in the parent's `PreToolUse` on tool `Agent` (`tool_input.prompt`, `tool_input.subagent_type`). The hook's `additionalContext` nonce reached the subagent as an `attachment` `hook_additional_context` in all three forms | the Agent-call envelope carries the task token (yes), so the field search is sound | **task prompt not in the envelope** → the brief-keyed recall of [[task-agent-start-context#r0]] reads it from the `PreToolUse` Agent call (or the transcript), not from `SubagentStart`; injection itself works for fg, bg and fork. Teammate: `not observable` (see P3) |
| P10 | 2.1.331 headless, `--plugin-dir` | plugin `p10plug`: agent is `p10plug:p10agent` (accepted as `subagent_type`; `SubagentStart.agent_type` is the same string), skill is `p10plug:p10skill` (Skill tool accepted it). A **project** agent with `skills: [p10plug:p10skill]` received the body (yes) and so did one with the bare `skills: [p10skill]` (yes) | the plugin skill's nonce reached the main session through the Skill tool (yes) | **namespaced `<plugin>:<name>`; a project agent's `skills:` may name a plugin skill, namespaced or bare** → [[refmatrix/adr-0007-instruction-architecture#dist-agent-lists]]: both spellings work in 2.1.331; use the namespaced one (the bare match was not tested against a name clash) |
| P11 | 2.1.331 headless; foreground, background, fork | agent `p11with` (`skills: [p11skill]`): the body nonce was in the subagent's first user message (transcript kind `subagent:user`) and the agent repeated it, foreground and background | agent `p11without` in the same project did **not** see it (no); a fork has no `skills:` list and did not either | **preloads work** → the preloads of I1.d stand. Teammate: `not observable` (see P3) |

Forms tried for P3, P9 and P11 ([[task-I1.b0-probes#risks]] 3): foreground, background
(`run_in_background`), fork (`agent_type=fork`) all observed; **teammate** not observable headless
(`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`, the model found no team tool; `Pteam/` is the attempt,
to be retried interactively by the lead). {#forms}

## Notes the verdicts rest on {#notes}

- The matcher `Task` and `Agent` both fired for a subagent spawn; the envelope's `tool_name` is
  `Agent` in 2.1.331. {#note-agent-name}
- `InstructionsLoaded` also carries `globs` (the rule's `paths:` list) and `parent_file_path`
  (for `include` loads). {#note-globs}
- Evidence is per hook call: `label`, `form`, `event`, `has_agent_id`, and for each envelope leaf
  the key path, type, length and `sha256[:12]`; a raw value only for a short enum key, a synthetic
  probe name or a declared nonce. {#note-evidence}
- Where a nonce sits in the transcript is found by `common/where.py` (record type, attachment
  type, role; counts only). {#note-where}

## The cost baseline {#baseline}

rel: implements -> [[task-I1.b0-probes#cost]]
rel: evidence-for -> [[refmatrix/adr-0007-instruction-architecture#dispatcher-cost]]

Command: `workflow/measurements/instruction-probes/run.sh cost` (`cost/baseline.py`): renders
`hooks._handoff_cmd(root, "gate", per_session=True)` for a `mkdtemp()` root with no gate file,
runs it 200 times by `/bin/bash -c` with a PreToolUse envelope on stdin, 10 warm-ups discarded,
timed around the process; floor is `bash -c 'exit 0'` the same way. Machine: Mac15,8, arm64,
16 cores; load average at the run 3.14, 3.00, 3.15 (1, 5, 15 min). {#baseline-cmd}

| | median | p95 | min | max |
|---|---|---|---|---|
| prefiltered gate hook (no gate file) | **3.68 ms** | 4.49 ms | 3.09 ms | 4.66 ms |
| floor `bash -c 'exit 0'` | 1.69 ms | 2.25 ms | 1.52 ms | 2.60 ms |
| added by the hook | 1.99 ms | | | |

Three earlier runs the same hour gave medians 3.55, 3.20 and 3.47 ms (floor 1.86, 1.64, 1.78).
**Band: median at most 10 ms → the form stands** ([[refmatrix/adr-0007-instruction-architecture#dispatcher-cost]]).
The raw result is `instruction-probes/cost/baseline-2.1.331.json`. {#baseline-band}

## Re-run {#rerun}

`./workflow/measurements/instruction-probes/run.sh P4 --save` rebuilt P4's project in a fresh
directory and printed `calls per hook entry: {'unfiltered': 3, 'if-filtered': 1, 'control-deny': 1}`
and `control … : yes`, the same as the first run; it saved
`P4/evidence/2.1.331-headless.jsonl`. `run.sh P<n>` does the same for every probe;
`P1b` and `P2` build the project and print the interactive steps. {#rerun-p4}

## No raw content {#ac3}

Evidence check: every evidence leaf has only the keys `path, type, len, sha, tokens, val`; `val`
appears only on enum keys (`hook_event_name, tool_name, load_reason, memory_type, agent_type,
source, trigger, permission_mode, subagent_type, reason`), synthetic names (`p3dir`, `p10plug:…`,
`p8skill`, …) and nonces. The grep for an absolute path or a long raw value:

`grep -rEho '/Users/[A-Za-z0-9_./-]+|"val": "[^"]{25,}' workflow/measurements/instruction-probes/P*/evidence` → 0 hits. {#ac3-grep}

## Contradictions with the ADR {#drift-none}

None. Each fact [[refmatrix/adr-0007-instruction-architecture#context-facts]] lists as verified
that a probe touched held: path rules load on Read in the main session and in subagents (P3, P6,
P7 controls), an agent's `skills:` preloads the full body (P11), SubagentStart injection (P9),
`InstructionsLoaded` is observation with the documented fields (P3; extra fields `agent_id`,
`agent_type`, `globs`, `parent_file_path`). The "not verified" and "documented only in part" items
resolved as above. No `ARCH-DRIFT`. {#ac5}

## Left for the lead {#lead-left}

- **P1b** (does the permission prompt stay as it was, with a context-only hook) and **P2**
  (`ask` in default and auto mode): `run.sh P1b`, `run.sh P2` print the steps; they need an
  interactive session. P1's `context` verdict stays provisional until P1b.
- The **teammate** form of P3, P9 and P11 (`Pteam/probe.sh`), interactive.
- P6's listing change (the body is not loaded; whether the listing differs was not examined).
- Whether to retest bare vs namespaced `skills:` against a name clash (P10). {#lead-items}
