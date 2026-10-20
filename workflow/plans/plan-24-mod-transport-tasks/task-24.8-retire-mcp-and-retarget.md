---
gmd: "0.1"
id: task-24.8-retire-mcp-and-retarget
title: "Task 24.8: rmx mcp leaves the Claude Code path (it stays for other MCP clients), .mcp.json goes, and the held hook-shaped work — plan-16's build, 19.5 R1, 19.6's injection, 21.2-21.4 — is re-specified against the mod's events"
tags: [task, plan-24, mcp, retire, retarget, plan-16, plan-19, plan-21]
metadata:
  node_type: task
  status: pending
  created: 2026-10-20
  updated: 2026-10-20
---

# Task 24.8: retire `rmx mcp` on the Claude Code path; re-specify the held items {#root}

> Plan: [plan-24-mod-transport](../plan-24-mod-transport.md)
> Status: Pending (spec written 2026-10-20).
> Depends on: [[task-24.7-distribution]] (the deploy copy loads in every session),
> [[task-24.5-mod-core]] R12's P-sub-tools and P-print (the retirement is gated on them),
> [[task-24.6-context-and-observation]] (the events the held items build on).

rel: part-of -> [[plan-24-mod-transport]]
rel: depends-on -> [[task-24.7-distribution]]
rel: depends-on -> [[task-24.5-mod-core]]
rel: depends-on -> [[task-24.6-context-and-observation]]
rel: implements -> [[plan-24-mod-transport#phase-held]]
rel: amends -> [[plan-16-invisible-grep-shim]]
rel: amends -> [[task-19.5-measure-delivery]]
rel: amends -> [[task-19.6-phased-context-and-topic-cache]]
rel: amends -> [[task-21.2-precise-identifier-context]]
rel: amends -> [[task-21.3-indexed-symbol-nudge]]
rel: amends -> [[task-21.4-surfaces-and-nl-ranking]]
rel: related-to -> [[feedback_mcp_server_reload_and_orphans]]
rel: implements -> [[exploration-claude-code-mod-transport#facilities-priority]]

## Why {#why}

G4: tools in the engine, so no `rmx mcp` process per client, no `/mcp` reconnect after a deploy,
no orphans, and no long-lived process whose spawn-time environment names a dead session (the
reason `_LONG_LIVED` and the pid ladder exist). D1: the hook-shaped work held at the gate is
re-specified onto the mod once 24.5 and 24.6 define its events, and the hook-based specs stay as
records. This task does both. {#why-lead}

## Decisions {#decisions}

| # | decision | reason |
|---|----------|--------|
| d1 | `rmx mcp` STAYS as a command and module; it is removed only from the Claude Code path (this repo's `.mcp.json`, the docs' Claude Code setup) | refmatrix is usable from any MCP client (Claude Desktop, other agents); `mcp.py` is a thin adapter over the same verbs, so keeping it costs no drift (the parity gate covers it); removing it would end that use for no gain |
| d2 | The retirement is GATED: it lands only when P-sub-tools (24.5) shows registered tools serve subagents and P-print shows them callable under `claude -p`; otherwise this task stops and the user decides | MCP tools reach subagents and `-p` today; removing them before the mod is shown to would take tools away from those contexts |
| d3 | The `claude/channel` bus bridge stays in `mcp.py` for MCP clients; on Claude Code the bus wake (24.5 R10) replaces it | the bridge is an experimental capability of the MCP transport; the mod has a native wake |
| d4 | The pid-pointer ladder and `_LONG_LIVED` are KEPT: the shell fallback and non-Claude-Code MCP clients still need them; the Claude Code path no longer reaches them | G1 retires the ladder on the Claude Code path, not everywhere; the fallback must keep working |
| d5 | Tool names do not change (24.4 d4: `mcp__refmatrix__rmx_*`), so agent overlays, skills and memories that name them need no edit | an edit sweep across templates and memories would be churn with risk and no gain |
| d6 | The held specs are REWRITTEN in place as new revisions (status back to `drafting`, a `## Retargeted to the mod (24.8)` section at the top with `rel: amends -> [[task-24.8-retire-mcp-and-retarget]]`), the hook-based text kept below as the record | D1 says the hook specs are kept as records; one file per task keeps every inbound wikilink valid |

## Requirements {#requirements}

1. **R1 — the gate (d2).** Before any change: `eval/mod_probe/sub_tools.json` and `print.json`
   (24.5 R12) both positive, cited in the implementation summary. Negative → stop, write the
   finding to the plan, ask the user. {#r1}
2. **R2 — `.mcp.json`.** Remove the `refmatrix` server entry (the file's only entry: delete the
   tracked file). The mod's collision rule (24.5 d13) then stops firing on this repo, and the
   mod's tools register; the implementation summary records the first session where `rmx mod
   status` shows them served (24.7 d8). {#r2}
3. **R3 — docs.** `CLAUDE.md` `#mcp-servers` and `docs/INTEGRATION.md`: Claude Code uses the mod;
   `rmx mcp` is for other MCP clients, with its `.mcp.json` snippet moved under that heading.
   `docs/SYSTEM.md` / `docs/ARCHITECTURE.md` gain the two HTTP tiers and the mod (pointing at
   24.2's ADR). The memory `feedback_mcp_server_reload_and_orphans` gains an amend note (via a new
   memory with `rel: amends`, the memory rules' path) that it no longer applies on Claude Code.
   {#r3}
4. **R4 — no Claude Code caller of `rmx mcp`.** A test walks `hooks.py`'s render, the templates
   under `src/refmatrix/templates/`, and `install.sh` for a `.mcp.json` writer or a `rmx mcp`
   Claude Code instruction; none (the MCP section of `docs/INTEGRATION.md` is the one allowed
   mention). {#r4}
5. **R5 — the held items, re-specified (d6).** Each rewrite lands as a spec revision this task
   commits, reviewed by ch-architect and `@ch-bsd` like any spec: {#r5}

   | held item | what changes against the mod |
   |---|---|
   | [[task-16.1-argv-faithful-learner]] | For Claude Code calls the learner is fed the output the agent SAW: 24.6's `tool.call` passes `ran.text` (and whether it was cut) to a new engine verb `rmx_grep_learn(argv, cwd, output, truncated)`; the re-run of the caller's search remains ONLY for the shell shim (terminals, non-Claude callers). The "corpus hits only, each line once" rule is unchanged |
   | [[task-16.2-invisible-shim]] | Scoped to non-Claude-Code shells. On Claude Code the Bash command is no longer rewritten to `rmxgrep`: `tool.call` observes it unchanged, so 24.6's `rmx_shell_rewrite` step and the user-global grep-rewrite-guard retire on that path (the guard's stand-down becomes permanent there) |
   | [[task-16.3-grep-tool-hook-and-docs]] | The Grep-tool hook becomes 24.6's `tool.call` on Grep: argv is built from the tool's input, the learner gets the real result; `grep-tool-teach.sh` and `rmx_grep_teach` retire on Claude Code. The docs half ("grep is observed") is unchanged |
   | [[task-16.4-measurement]] | "What the agent actually saw" is now recorded, not reconstructed: the measurement reads the observed outputs (complete, with the cut flag) from the learner's input log; the re-run comparison stays for the shim path only |
   | [[task-16.5-explicit-grep-hands-off]], [[task-16.6-learned-row-validation]] | No change (CLI semantics and store-side validation); each gains a one-line note that it is unaffected by 24.x |
   | [[task-19.5-measure-delivery]] R1 | The hook-output threshold probe is replaced, for the mod path, by recording the engine's stated limits for `prompt.submit` `context` (past 100,000 characters per entry, 200,000 together, the model reads a head and a path) and verifying them once in a scratch project; the shell probe runs only for contexts 24.6 R7 left on the fallback. R2-R5 add the mod as a delivery channel source (24.2 R9 rows, `invocation: "mod"`) |
   | [[task-19.6-phased-context-and-topic-cache]] | Injection lands through 24.6's two routes: session-fixed blocks in the `refmatrix:session` compose section, per-prompt blocks in `prompt.submit` context. R5's versioned blocks build on `refmatrix.injected` and `rmx_scan_prompt(skip_block_shas)` (the verb decides and emits `unchanged`); R6's deltas are verb output; R4's budget stays verb-side; R8's compaction lever becomes 24.6's `session.compact` hook rewriting `instructions` (24.6 passes them unchanged; this is where that changes). R4's per-prompt budget reads the session's real headroom from `session.measure` (context fill and rate-limit windows, pushed per turn) instead of a fixed allotment — the same retarget applies to plan-19's other budget tasks (19.1) as a stated input, not a rewrite of their method |
   | [[task-21.2-precise-identifier-context]] | Not hook-shaped: `--brief` becomes an `rmx_context(brief=True)` parameter so the mod tool and MCP reach it; the replay harness calls the verb. Otherwise unchanged |
   | [[task-21.3-indexed-symbol-nudge]] | The nudge is a `tool.call` hook on Bash / Grep that returns `ran` with one `context` line (`ToolCallResult.context`: read after the result, never shown); R0's timing harness times the 24.2 HTTP verb call, not a hook spawn; R4's off switch is a mod `userConfig` field plus `RMX_CONTEXT_NUDGE`; R5's "generated by hooks.py" becomes "generated in the mod's event map"; the shell variant exists only for fallback contexts. ALSO evaluated as an arm: the nudge at the source, a `tool.describe` hook on Grep (and Bash) whose description points at `rmx_context` for indexed identifiers — cached per session, so it costs no per-call request; R0 measures both arms |
   | plan-21's usage telemetry ([[task-21.1-context-usage-telemetry]], shipped) | No rewrite; a follow-up spec adds two event sources: `turn.step` / `turn.start` for per-step model usage beside each recall delivery, and `mcp.call` for OTHER MCP servers' calls entering `used` evidence and STM |
| [[task-21.4-surfaces-and-nl-ranking]] | "Every steering surface" adds the generated tool descriptions (they come from the verbs' descriptions, so one edit covers mod and MCP) and the `refmatrix:session` compose section's preamble; the rule is written into the verbs and the section, not into a hook's printed text |

6. **R6 — the plans.** `plan-16`, `plan-19`, `plan-21` and `plan-24` task tables record the
   rewrites (status `drafting`), and `workflow/plan-of-plans.md` moves them out of "held". {#r6}
7. **R7 — the follow-up candidates.** Each "follow-up" row of
   [[exploration-claude-code-mod-transport#facilities]] is written into `workflow/plan-of-plans.md`
   as a candidate task (one line: facility → refmatrix use → the existing verb or store primitive
   it builds on), NOT specified here: {#r7}

   | facility (verified in the 2.1.293 types) | candidate |
   |---|---|
   | `prompt.mention` | an `@file` read adds that file's graph neighbourhood (`rmx_context`) as `context` |
   | `prompt.autocomplete` | typeahead rows for symbol / concept / memory / subject names from the store |
   | `prompt.suggest` | the dim Tab suggestion from STM focus and the task stack |
   | `skill.prompt` | ch-* skills and `/recall-state` expanded with live store facts |
   | `$.agent.register` / `$.agent.spawn` / `agent.offer` | ship gmd-curator and ch-* with the mod; spawn the curator when its queue fills instead of the per-prompt `curator status --drain` line |
   | `$.command.register` / `command.run` | `/recall-state`, `/save-state`, `/detour`, `/stash` as native commands over their verbs; `/remember` quoting `$.ui.selection()` |
   | `ui.open` / `ui.press` / `ui.select` / `ui.input` | curator and refine review panes: a home for the `refine accept / reject` approval gate |
   | `$.model.fork` | save-state digests and "what did we decide?" answered over the session's own transcript, cache-served |
   | `$.model.complete` | subject / cluster labels and tag suggestions |
   | `session.receive` / `session.send` | the bus as real deliveries (24.5's P-send result decides) |
   | `telemetry.log` / `telemetry.mark` | join 21.x usage with Claude Code's own OTel records |

## Acceptance criteria {#acceptance}

1. **AC-1 (R1).** The implementation summary cites both probe files with positive results, or
   the task is closed blocked with the user's decision recorded. {#ac-1}
2. **AC-2 (R2, R4).** `.mcp.json` is gone from the tree; R4's walk finds no Claude Code
   `rmx mcp` caller; `tests/test_mcp_*.py` still pass (the server works for other clients). {#ac-2}
3. **AC-3 (R3).** `./scripts/lint-gmd.sh` is clean; `docs/INTEGRATION.md` holds the MCP snippet
   only under its non-Claude-Code heading. {#ac-3}
4. **AC-4 (R5, R6).** Each listed spec has the `## Retargeted to the mod (24.8)` section with the
   change of R5's table, an `amends` edge to this task, status `drafting`, and lints clean; the
   plan tables and plan-of-plans agree. {#ac-4}

5. **AC-5 (R7).** `workflow/plan-of-plans.md` lists the eleven candidates, each naming its
   facility and the primitive it builds on; none has a task spec yet. {#ac-5}

## Test strategy {#test-strategy}

`tests/test_task24_8_mcp_retired.py` (R4's walk, the deleted file, AC-2); the MCP suites run
unchanged; GMD lint over every rewritten spec. The probes are 24.5's, not repeated. RED first: R4's
walk fails while `.mcp.json` exists, logged to `workflow/review-output/task24_8-red.log`.
{#test-strategy-body}

## Files to modify {#files}

| file | change |
|---|---|
| `.mcp.json` | deleted (R2) |
| `CLAUDE.md`, `docs/INTEGRATION.md`, `docs/SYSTEM.md`, `docs/ARCHITECTURE.md` | R3 |
| the memory dir: a new `feedback_mcp_reload_not_on_claude_code` memory amending the old one | R3 |
| `workflow/plans/plan-16-invisible-grep-shim-tasks/task-16.1..16.6`, `plan-19-…/task-19.5`, `task-19.6`, `plan-21-…/task-21.2..21.4` | R5 |
| `workflow/plans/plan-16-invisible-grep-shim.md`, `plan-19-adaptive-memory-budget.md`, `plan-21-agent-context-usage.md`, `plan-24-mod-transport.md`, `workflow/plan-of-plans.md` | R6 |
| `tests/test_task24_8_mcp_retired.py` | AC-2 |
