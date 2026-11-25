---
gmd: "0.1"
id: task-agent-start-context
title: "Agent-start context: a generated SubagentStart hook gives every subagent the primer and a recall for its brief"
tags: [task, hooks, subagents, context, recall]
metadata:
  node_type: task
  status: drafting
  created: 2026-11-14
---

# Task: agent-start context for subagents {#root}

> Status: drafting (2026-11-14). Decided by the user as Q15 option 2 ("q15 - 1 and 2"); option 1
> (read-only refmatrix MCP tools in every `ch-*` agent and `gmd-curator`) shipped the same day as a
> config change. Queue slot: **post-mod** (Q28 = a; re-evaluated against the mod first, L127 and L129;
> [[plan-of-plans#post-mod]]); a ch-bsd spec round precedes approval.

rel: derives-from -> [[open-questions#answered-37b7498f]]
rel: related-to -> [[plan-review-2026-11-13#lead]]

## Why {#why}

Measured 2026-11-14 over the 30 subagent transcripts of session 37b7498f: subagents get refmatrix
only as a Bash CLI. 16 of 30 ran `rmx` at all; 522 of their 662 `rmx` calls were `rmx grep`, which
falls back to `rg` inside a littlebig clone (no store), and 8 were `rmx context`. 4 of 30 saw any
injected refmatrix context, and only as text the lead pasted into a brief. The per-prompt
scan-prompt hook and the SessionStart recall fire for the user's session, never for a subagent, so
the graph, the primer and memory recall never reach the agents that do most of the work. {#why-body}

## Depends on {#depends}

- 0.83.0 released (25.1's `hook_budget` emitter and channel accounting are the output path).
- 25.1b's single emitter (R12) if it has landed; otherwise this hook joins 25.1's channel table.

## Requirements {#requirements}

1. **R0 Probe first (no build before it).** {#r0} In a throwaway Claude Code session, register a
   `SubagentStart` command hook and record, from a real spawned subagent: the stdin payload fields
   (is the agent's prompt / description / type present?), whether `additionalContext` (or any
   output field) reaches the subagent's context, the size cap that applies, and whether it fires
   for background, forked and workflow agents. Commit the probe script and its transcript-derived
   evidence (hashes and field names, never raw prompts) under `workflow/measurements/`. If no
   output route reaches the subagent, stop and report: the fallback is the plan-24 mod route
   (`agent.spawn` rewrite, probed 2026-10-20), which needs its own decision.
2. **R1 Generated, never hand-written.** {#r1} The hook is emitted by `hooks.py` like every other
   rmx hook, appears in `rmx install-hooks --check` parity, and is installed fleet-wide by the next
   `install-hooks --apply`.
3. **R2 Content, in priority order under the per-hook cap.** {#r2} (a) a one-line header naming
   the store the tools answer from (`master` of the dev tree) and that a clone's own changes must be
   read from files; (b) a memory recall for the agent's prompt text (dense + rerank, `scope=both`,
   k from a pre-registered band); (c) the top of `.refmatrix/PRIMER.md`. Each block is labelled by
   kind, the most important first, per `feedback_injection_presentation_rules`.
4. **R3 Budget and failure.** {#r3} The output stays under the measured hook cap: its channel in
   `hook_budget.CHANNEL_BUDGET_BYTES` (`src/refmatrix/hook_budget.py`). A skipped or degraded
   recall says so in one line inside the payload (25.1b R18's skip-line shape); the hook never
   exits non-zero into the spawn, and never prints nothing silently.
5. **R4 Telemetry.** {#r4} One telemetry row per firing (channel `agent_start`), with
   `payload_bytes`, the recall's ids and the cause of any skip, so a later measurement can ask
   whether agents used what they were given.

## Acceptance {#acceptance}

- **AC-1:** R0's probe report exists and names the payload fields and the output route, or the
  task stops with the fallback recorded.
- **AC-2:** a spawned test agent in a sandbox session receives the three labelled blocks; the
  mutation "hook not generated" fails `install-hooks --check`.
- **AC-3:** with the daemon down, the payload carries the skip line and the primer block; exit 0.
- **AC-4:** payload ≤ budget on a fixture whose recall and primer together exceed it (the ladder
  drops the primer tail first); mutation "no cap" fails.
- **AC-5:** the telemetry row is written with the channel and byte count.

## Files {#files}

`src/refmatrix/hooks.py` (generator), the recall CLI path the hook calls, `hook_budget.py`,
telemetry channel table, tests under `tests/test_agent_start_context*.py`,
`docs/INTEGRATION.md` (hooks section).

## Done {#done}

Implementation summary `workflow/implementation_summaries/task-agent-start-context.md`; fleet
re-install at the next release.
