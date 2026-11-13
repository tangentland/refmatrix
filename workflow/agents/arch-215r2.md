---
gmd: "0.1"
id: agent-brief-arch-215r2
title: "Brief: arch-215r2 — task 21.5 spec revision 3 (closes ch-bsd spec r2)"
tags: [agent-brief, dispatch]
---

# Brief: arch-215r2 — task 21.5 spec revision 3 {#root}

Revise the task 21.5 spec to close ch-bsd spec review r2. Spec text and measurement only: no
`src/`, no tests.

rel: amends -> [[agent-brief-arch-215r1]]
rel: depends-on -> [[agent-brief-green-251#hard-rules]]

## Where {#where}

- Clone `/Volumes/littlebig/refmatrix-plan21-5`, branch `task-21.5-tool-used-signal`, tip
  `b8b06df`. Work and commit (pathspec) only there. Your previous brief:
  `/Users/tholley/claude_tools/refmatrix/workflow/agents/arch-215r1.md` — its rules still apply.
- The review to close: `workflow/bullshit/2026-11-13-1053-task-21.5-spec-r2-540ab50.md` on the
  branch (DIRTY 14: 1B/5S/8M). Its auditor's count-only scripts are in
  `/private/tmp/claude-501/-Users-tholley-claude-tools-refmatrix/f0521bff-0006-479a-9e0f-6df02d50937e/scratchpad/b215/`.

## Scope {#scope}

- **b-1 (blocker):** the Bash leg takes its base directory from a leading `cd <dir>`,
  `pushd <dir>` or `git -C <dir>` in the command; a base outside the project counts
  `refs_outside_project` and never matches. Add AC-7's negative case. RE-RUN `#why-data` under
  the fix on read-only APFS copies (counts only; never commit raw prompts, commands, query logs
  or STM rings) and rewrite that section's claims from the new numbers.
- **s-1..s-5** and **m-1..m-8** as the report's Fix lines say. For s-5, file the
  `tool_result` leg's row (plan-21 task row or `workflow/deferral_registry.md` row with ACs) —
  a registry row edited on this branch is fine; the lead merges it.
- If 24.6 needs a matching change (s-1 git branch through `stm.tool_event_fields`, m-3 park
  record fields), amend 24.6 as r7 in the same change, as r6 was.
- **Do NOT decide OD-4 or OD-5** — they are the user's, still open. Leave `#open-for-user`
  as is, updating only numbers the b-1 re-run changes (e.g. OD-5's lag histogram if it moves).

## Deliverables {#deliverables}

A `#rev-3` disposition table (every r2 finding → where closed), spec metadata `revision: 3`,
GMD lint 0 errors on every file touched, commits on the branch. Text report: shas, the re-run
`#why-data` numbers before → after, every lead decision you made "as the user would", and
anything that needs the user beyond OD-4/OD-5.
