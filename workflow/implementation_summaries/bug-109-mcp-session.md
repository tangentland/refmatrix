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
rel: related-to -> [[task-19.0-stm-cluster-hygiene#requirements]]
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
  (`focus hook --event input`) writes it at the top of every turn. Process facts (parent,
  executable, start time) come from the kernel with no subprocess (macOS libproc
  `proc_pidinfo`/`proc_pidpath`, ~1 us; Linux `/proc`), so the hook's owner lookup is ~3 ms
  instead of the r1 `ps -A` (~60 ms, could time out under load). A pid reuse is caught by the
  kernel start time; a pid whose start cannot be read is REFUSED and recorded, never stored with a
  null start. The hook skips the rewrite only when the pointer names this session AND this
  process's start time (r3 #s-1), so an old-format or stale pointer for the current session is
  repaired on the next turn instead of reading as stale all session.
- **Owner.** The long-lived server: `os.getppid()` (19.0 R5), its environment ignored. A per-call
  process (`stm.owner_lookup() -> (pid, status)`): `$CLAUDE_PID` only if it is a real ancestor
  (Claude Code sets it per child); else the NEAREST ancestor that is Claude by executable
  (`.../claude`, or the native installer's `.../claude/versions/<x.y.z>`, whose kernel name is the
  version) or by argv[0] (one `ps` call, only on this rare path: an npm CLI runs as `node`).
  `status` distinguishes `none` (a plain terminal) from `failed` (the lookup could not run): r2
  #b-1, UNKNOWN is not absent.
- **Resolution** (`verbs.resolve_session_source` → `(session, source)`): explicit; then the
  pointer before `$RMX_SESSION` in the server, after it in the CLI; then the newest ring; then
  `default`. Under Claude, a fallback to the newest ring is recorded in
  `stm/by-pid/_errors.jsonl` (`pointer-unresolved`) because every hook ends in
  `2>/dev/null || true`; the hook records `no-owner`, `owner-lookup-failed`, `ps-failed` and
  `write-failed` there too. A resolve records `owner-lookup-failed`, or `pointer-unresolved` when
  this process is the server, has a Claude owner, or carries `$CLAUDE_PID`; a plain terminal
  guesses silently, having no pointer to miss. The sink writes only into a store whose STM dir
  exists and never raises (r2 #s-1: a read must not create `<cwd>/.refmatrix`), is capped at
  256 KiB, and has a reader: `rmx recall-state` reports the last day's failures as an anomaly
  ("STM calls may have used a guessed session": rows do not say read or write, r3 #m-1). A
  malformed line is counted as `unreadable-line`, never raised out of recall-state (r3 #m-2).
  CLI writes no longer pass a pre-resolved session as explicit, so their source is real (r2 #s-2).
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
- r2: 9 more tests, 6 RED at 320dc82 and 3 that pin behaviour 320dc82 already had (source on
  task/change_subject, CLI env-before-pointer, deep-chain walk) (`bug109-r2-red.log`); 25 GREEN
  (`bug109-r2-green.log`); families 259 passed (`bug109-r2-families.log`).
- r3 (ch-bsd `bsd-bug109-r3-261c574`, BULLSHIT: 12/13 mutants survived, r2 N4/N5 among them):
  17 more tests. 13 pins (P1, P3-P13; P2 was already killed) pass at 261c574 by design and are
  proven by mutation below; 4 are RED at 261c574 for the right reasons (`bug109-r3remedy-red.log`:
  stale same-session pointer not rewritten, `AttributeError` on a `[1, 2]` sink line, unreadable
  lines not surfaced, "writes" wording). GREEN 42/42 (`bug109-r3remedy-green.log`); families
  276 passed (`bug109-r3remedy-families.log`; the brief's `test_focus*`/`test_handoff*`/
  `test_promote*` globs match no file in this tree).
- Mutations: `bug109-mutations.log` (r0, 6 killed), `bug109-r1-mutations.log`,
  `bug109-r2-mutations.log`, `bug109-r3remedy-mutations.log` (the r3 ch-bsd script extended with
  R1-R4 for the r3 fixes, `bug109-r3remedy-mut.py`): **17/17 killed** (P1-P13, R1-R4), each
  restored with `git checkout --`, `__pycache__` cleared, tree clean after the run. P1 is killed
  by the zero-subprocess assertion, so the `ps` fallback can no longer mask a bad struct offset.

## Open, owned elsewhere {#open}

- `composite.py:103` (scan-prompt composite) and `helix.py:96` read the newest ring; reads, owned
  by 19.0 R5, which must list them (r1 #m-1, #m-2).
- `focus record` / `focus clear` bypass the resolver (pre-existing, r1 #m-3).
- No SessionStart pointer write, the hook/server store-root split, and `stm/by-pid/` cleanup are
  19.0 R5's (r1 #m-4).
- Per-row `verb=`/`write=` in the sink, so the anomaly can count write guesses only: 21.1 R9 D6
  (r3 #m-1, anchored). The 19.0 R5 / 21.1 R9 citations of removed code (`_process_table`,
  `ps lstart`) are re-read at this branch's merge sha before either starts (r3 #m-3; the specs
  live in another tree).

## Deploy {#deploy}

r4 additions: no daemon or hub code changed, so `rmx daemon restart --relaunch` delivers nothing
for bug-109; the hooks pick it up as soon as `~/refmatrix` fast-forwards (editable install).
Verify by `git -C ~/refmatrix rev-parse HEAD` equal to the merge sha and by
`stm/by-pid/<claude_pid>.json` appearing after the next prompt. A second main-tree MCP server is
hosted by IntelliJ (it also runs `.venv-eval`) and needs its own restart.

The hooks run the deployed `~/bin/rmx`; other projects' MCP servers run `~/bin/rmx mcp`. Both get
the fix on deploy (merge to `master`, fast-forward `~/refmatrix`, `rmx daemon restart --relaunch`)
plus `/mcp` reconnect.

**This project's MCP server is different (r3 #s-2).** Its `.mcp.json` runs
`.venv-eval/bin/rmx mcp`, which imports the MAIN checkout's `src`
(`/Users/tholley/claude_tools/refmatrix`), not the deploy tree. So the fix reaches the session
that reported bug-109 only after `master` is merged into the branch that checkout is on (today
`wave0-spec-reviews`, a shared tree: with the peer session's agreement, never a branch switch),
followed by `/mcp` reconnect. Until then that server keeps base behaviour (newest ring,
unlabelled, nothing recorded); no regression, but no fix. Verify with `rmx_focus_note` returning
`session_source: pointer`.
