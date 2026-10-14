---
gmd: "0.1"
id: impl-bug-109-mcp-session
title: "bug-109: the MCP server resolves the CURRENT session through a per-Claude-process pointer"
tags: [implementation-summary, bug-109, stm, mcp, session]
metadata:
  node_type: implementation-summary
  status: in-review
  created: 2026-10-14
  updated: 2026-10-14
---

# bug-109: MCP session attribution {#root}

rel: implements -> [[plan-review-2026-10-14#t11-approvals]]
rel: related-to -> [[task-19.0-stm-cluster-hygiene#r5]]
rel: related-to -> [[task-21.1-context-usage-telemetry#req-session]]

## The defect {#defect}

`rmx mcp` is spawned once per Claude Code process, so its `CLAUDE_CODE_SESSION_ID` is frozen at
spawn: after `/clear` it names the OLD session. `verbs.resolve_session` never read it, but fell
through to the newest STM ring on disk, which is another session's whenever two run at once. MCP
`rmx_focus_note`, `rmx_save_state`, `rmx_task` and `rmx_change_subject` therefore wrote into
whichever session touched STM last. Decided as d9s (user, 2026-10-14: "fix it"), a subset of
19.0 R5 / 21.1 R9 shipped ahead of them.

## The fix {#fix}

- **Pointer.** `stm/by-pid/<claude_pid>.json` = `{session, pid, pid_start, t}`. The input hook
  (`focus hook --event input`) writes it at the top of every turn; an unchanged pointer costs one
  read and no `ps`. A pid reuse is caught by `ps lstart`; a pid whose start `ps` cannot report is
  REFUSED and recorded, never stored with a null start.
- **Owner.** The long-lived server: `os.getppid()` (19.0 R5), its environment ignored. A per-call
  process: `$CLAUDE_PID` only if it is a real ancestor, else the nearest `claude` ancestor; one
  `ps -A` call builds the chain.
- **Resolution** (`verbs.resolve_session_source` → `(session, source)`): explicit; then the
  pointer before `$RMX_SESSION` in the server, after it in the CLI; then the newest ring; then
  `default`. Under Claude, a fallback to the newest ring is recorded in
  `stm/by-pid/_errors.jsonl` (`pointer-unresolved`) because every hook ends in
  `2>/dev/null || true`; the hook records `no-owner`, `ps-failed` and `write-failed` there too.
  `rmx_focus_note`, `rmx_task` (push/pop/swap), `rmx_change_subject` and `rmx_save_state` return
  `session_source`.
- **`focus promote-edges`** resolves the session in the CLI and sends it; the daemon has no
  Claude ancestry, so it always took the newest ring for a durable write.
- **Checkout guard** (d9w): `tests/conftest.py` refuses to run when `refmatrix` imports from
  another tree.

## TDD {#tdd}

- RED: `tests/test_mcp_session_pointer.py`, 10 at 06ecd0f against a434f51 (one, the old
  no-pointer test, was vacuous; ch-bsd r1 #s-2 replaced it), then 6 more for r1, RED at 54e13c6
  (`bug109-r1-red.log`).
- GREEN: 15 passed (`bug109-r1-green.log`); STM/MCP/verbs/session/hook/handoff/save-state/promote
  families 249 passed (`bug109-r1-families.log`).
- Mutations: `bug109-mutations.log` (r0, 6 killed), `bug109-r1-mutations.log`.

## Open, owned elsewhere {#open}

- `composite.py:103` (scan-prompt composite) and `helix.py:96` read the newest ring; reads, owned
  by 19.0 R5, which must list them (r1 #m-1, #m-2).
- `focus record` / `focus clear` bypass the resolver (pre-existing, r1 #m-3).
- No SessionStart pointer write, the hook/server store-root split, and `stm/by-pid/` cleanup are
  19.0 R5's (r1 #m-4).

## Deploy {#deploy}

The hook runs the deployed `~/bin/rmx`; the MCP server runs `.venv-eval/bin/rmx` and reloads only
on `/mcp` reconnect. Deploy first, then reconnect `/mcp`; until both run the new code the old
newest-ring behaviour stays.
