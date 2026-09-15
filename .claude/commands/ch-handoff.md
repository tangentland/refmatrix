---
name: ch-handoff
description: Create a session handoff — rotate handoff.md, archive the prior session, and record what changed this session
argument-hint: [optional one-line session theme]
allowed-tools: [Read, Write, Edit, Bash, Glob, Grep]
model: inherit
enabled: true
---

# Session Handoff ("save state")

Produce a handoff-ready state so the next session resumes with full context. Follows the
**Handoff Rotation** rule in `CLAUDE.md`: `handoff.md` keeps only the latest session; previous
sessions are archived under `workflow/past_handoffs/`.

## Steps

1. **Gather state.** `git log --oneline -10`, `git status -sb`, current branch, merged/unmerged
   task branches, and any deltas this session to `workflow/plan-of-plans.md` (plan index +
   Status column) and the `metadata.status` of any plans in `workflow/plans/`.

2. **Archive the current handoff.** Move the existing `handoff.md` body to
   `workflow/past_handoffs/<seq>-<desc>_<date>.md`:
   - `<seq>` zero-padded (001, 002, …), next in sequence
   - `<desc>` kebab-case from the prior session header
   - Add a row to the Past Sessions table.

3. **Write the new `handoff.md`** using `workflow/templates/handoff-session.md`:
   - Header: `refmatrix` + today's date + session theme (from the argument if given).
   - Completed: what was implemented this session (files, tests).
   - Git State: branch + latest commit hash + message.
   - Next Steps: the concrete next task and its spec path; blockers.
   - User Preferences: anything learned this session.
   - Hand-Off Notes: pending decisions, gotchas.

4. **Record durable learnings** as GMD memory files (see `docs/gmd/SPEC.md`) rather than burying
   them in the handoff, if memory is wired for this project.

5. **Commit** on the current branch: `docs(handoff): session <seq> save state — <theme>`.

## Checklist before finishing

- [ ] `handoff.md` header date/branch/commit reflect THIS session (no stale values)
- [ ] Prior session archived under `workflow/past_handoffs/` and indexed in Past Sessions
- [ ] Next Steps names a concrete next task + spec path
- [ ] Uncommitted source changes are either committed or explicitly listed as parked
