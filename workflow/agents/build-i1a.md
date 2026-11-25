---
gmd: "0.1"
id: agent-brief-build-i1a
title: "Brief: build-i1a — I1.a contradiction edits (docs, small path)"
tags: [agent-brief, docs, plan-32, i1]
metadata:
  node_type: brief
  created: 2026-11-25
---

# build-i1a {#root}

rel: implements -> [[task-I1.a-contradiction-edits]]

You are one small-path agent. Build `workflow/plans/plan-32-tasks/task-I1.a-contradiction-edits.md`
exactly (read it first, then ADR 0007 `#contradictions`, `#user-calls`, `#amend-7` and the POP
rulings L221-L237). Docs and overlays only: no `src/`. Agent CORE files are not edited here (their
edits ride H1.b); overlays (`.claude/agents/*.local.md`) are. Memory files are the lead's: put the
exact memory edits the spec lists in `workflow/review-output/i1a-memory-edits.md` for the lead.
Each AC's proof as the spec names it; `./scripts/lint-gmd.sh` 0 errors (RMX_DEV_PYTHON pointing at
the dev tree's `.venv-eval` python if the parity step needs it); the guard tests the spec names, on
a lane on a committed sha. Read-only against every live store; never `find /`; never export
`REFMATRIX_ROOT`; no POP edits. Commit; report: sha, each AC's evidence, what is left for the lead. {#role}
