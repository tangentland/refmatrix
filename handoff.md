---
gmd: "0.1"
id: handoff
title: "Session Handoff for refmatrix"
tags: [handoff, session]
metadata:
  node_type: handoff
---

# Session Handoff for refmatrix {#root}

Date: 2026-09-14

## Completed {#completed}

- **0.66.1** memory bridge: save-state now ingests the curated memory dir (`finalize_save_state(sync=True)`),
  SessionStart re-runs it detached, `--session-start` widens an empty window. `~/.gstack` removed.
- **Live incident**: entities-table ART index phantom crash-looped the refmatrix daemon (39 launchd runs).
  Repaired by offline table rebuild (backup `.refmatrix/catalog.B.duckdb.bak-20260914-artfix`).
- **ch-bsd end-to-end audit** → DIRTY, 15 findings (`workflow/bullshit/2026-09-14-1900-e2e-audit-memory-bridge-f56a365.md`).
- **cat-herder template onboarded** (this commit): profile, CLAUDE.md, overlays, constitution, hooks.env, CI.

## Git State {#git-state}

- Branch `master`. Deploy tree `~/refmatrix` fast-forwarded to the same sha, BUT its venv imports
  the dev tree (BSD #bs-2) — fixed by plan 1.

## Next Steps {#next-steps}

Execute `workflow/plan-of-plans.md` in order (plans 1–6 remediate every BSD finding), TDD per
`workflow/TDD_GOVERNANCE.md`, `@ch-bsd` re-review after each plan until clean.

## Past Sessions {#past-sessions}

| # | Session | Date | Archive |
|---|---------|------|---------|
| — | rmx save-state handoffs (`savestate_*` memories) carry history before this template | — | `rmx recall-state` |

## User Preferences {#user-preferences}

- Hooks must be reproducible from `rmx install-hooks`; MCP tools must not bypass the verbs layer.
- Plans first, then execute one by one, TDD, BSD re-review loop until clean.
- The user pushes to GitHub; Claude does not.

## Hand-Off Notes {#hand-off-notes}

- Restart Claude Code after this commit so `.claude/settings.json` enforcement hooks load.
- `.mcp.json` is a workstation override (dev venv) and stays uncommitted.
