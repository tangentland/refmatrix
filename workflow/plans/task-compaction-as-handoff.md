---
gmd: "0.1"
id: task-compaction-as-handoff
title: "Compaction as a handoff: PreCompact saves state and shrinks the summary to one line; SessionStart(compact) injects recall-state"
tags: [task, hooks, compaction, handoff, save-state, recall-state]
metadata:
  node_type: task
  status: drafting
  created: 2026-11-14
---

# Task: compaction as a handoff {#root}

> Status: drafting (2026-11-14). The user asked for compaction to behave like save-state → /clear
> → recall-state without the compacted session, and chose Q17 a (automatic). Queued right after
> 0.83.0, which ships 25.1 (it drops the PreCompact recall command and adds recall-state on
> `compact`). A ch-bsd spec round precedes approval.

rel: depends-on -> [[open-questions#answered-37b7498f]]
rel: related-to -> [[task-agent-start-context]]

## Facts this rests on {#facts}

From Claude Code's hooks and context-window docs, checked 2026-11-14: no hook or setting replaces
or suppresses the compaction summary, and no hook can trigger `/clear`. A PreCompact hook can block
compaction (exit 2), and its stdout on exit 0 becomes instructions for the summary. SessionStart
hooks matching `compact` run after compaction and their output is added to the compacted context.
Project CLAUDE.md and auto memory are re-read from disk after compaction. So the summary cannot be
removed; it can be steered to a single line, with the handoff carrying the state. {#facts-body}

## Requirements {#requirements}

1. **R1 PreCompact saves state first.** {#r1} The generated PreCompact entry runs `rmx save-state`
   (with promote) before anything else, and only then prints the summary instruction. A failed
   save-state prints its cause on stderr and the instruction still names the last good handoff,
   never silence.
2. **R2 One-line summary instruction.** {#r2} PreCompact's stdout is exactly the instruction:
   summarise in at most one line naming the task in progress; the handoff injected after
   compaction is authoritative; do not restate files, decisions or plans. No other generated
   PreCompact entry prints to stdout (an existing recall or digest print would become summary
   instructions too).
3. **R3 Handoff after compaction, pulled whole (L91).** {#r3} The user, 2026-11-14: "I would use
   the bash output path only for the recall-state after compaction". A full `rmx recall-state`
   handoff measured 45,870 B on 2026-11-14: over the hook cap (~9-10 KB) and over the Bash tool's
   default 30,000-character output limit. So the SessionStart `compact` entry writes the full
   `rmx recall-state` output to a per-session file (under the store's `.refmatrix/handoffs/`, one
   file per session, the newest kept per session) and injects only a short block: the file's path,
   its byte count, and the instruction "read this file before any other action; it is the
   authoritative state". The model then pulls it with a file read, which carries no hook cap and no
   Bash output cap at this size. The PreCompact summary instruction (R2) names the same first
   action. If the write fails, the injected block says so and falls back to 25.1's budgeted inline
   recall-state. The `clear` trigger keeps 25.1's inline handoff unchanged (only compaction uses the
   pulled form, per the user's "only for").
4. **R4 Manual /compact.** {#r4} A manual `/compact <instructions>` keeps the user's instructions:
   the R2 instruction applies to the `auto` trigger only, unless the user passes none.
5. **R5 Generated and installed.** {#r5} Emitted by `hooks.py`, covered by `install-hooks --check`,
   rolled out by the next fleet `install-hooks --apply`.

## Acceptance {#acceptance}

- **AC-1:** the generated PreCompact entries print exactly the R2 text to stdout and nothing else
  (mutation: a second stdout writer → fails); save-state runs before the print.
- **AC-2:** the SessionStart `compact` entry writes the full handoff file (byte-identical to `rmx recall-state` stdout) and injects only the pointer block naming its path and size; a failed write injects the fallback (mutation: the inline handoff on `compact` → fails); `clear` is unchanged.
- **AC-3:** a sandbox session forced to auto-compact shows a summary of at most a few lines and the
  injected handoff after it (an R0-style probe recorded under `workflow/measurements/`, hashes not
  raw prompts).
- **AC-4:** save-state failing leaves a stderr line and an instruction naming the last handoff.

## Files {#files}

`src/refmatrix/hooks.py`, the PreCompact command bodies, tests under
`tests/test_compaction_handoff*.py`, `docs/INTEGRATION.md` (hooks section).

## Done {#done}

Implementation summary `workflow/implementation_summaries/task-compaction-as-handoff.md`; fleet
re-install at the next release.
