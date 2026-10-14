---
gmd: "0.1"
id: bsd-bug109-r2-320dc82
title: "ch-bsd r2 — bug-109 r1 remedies (320dc82): a ps failure still falls silently to another session's ring; read verbs now create stores"
severity: BULLSHIT
plan: bug-109
task: d9s
tags: [bsd, audit, bug-109, stm, mcp, session, silent-failure, r2]
---

# ch-bsd r2 — fix(stm,verbs): bug-109 r1 remedies (320dc82) {#root}

**Commit range:** 54e13c6..320dc82 (the r1 remedy), read against base a434f51 and r1 HEAD 54e13c6.
**Date:** written 2026-10-14T14:37:56-0700.
**Author:** Todd Holley / Opus 5.5 / orchestrator.
**Files changed:** 8 (cli.py, mcp.py, stm.py, verbs.py, tests/conftest.py,
tests/test_mcp_session_pointer.py, the r1 report, the implementation summary).
**Tree:** isolated clone `/Volumes/littlebig/refmatrix-bug109`, branch `bug-109-mcp-session`,
HEAD 320dc82. Nothing in src/ or tests/ was left edited: 11 mutations were each restored with
`git checkout`, `__pycache__` was cleared, and `git status` is clean. No live store or socket was
touched. Live evidence is read-only `ps` sampling plus `strings` on the Claude binary.

rel: evidence-for -> [[bsd-bug109-mcp-session-54e13c6]]

## r1 status {#r1-status}

| r1 id | Status | Evidence |
|-------|--------|----------|
| #b-1 silent fallback | PARTIAL | **Closed:** a null start is refused (M8 killed). The long-lived server's unresolved resolve is recorded (M7 killed). `rmx_focus_note` returns `session_source` (M11 killed). **Open:** a `ps` failure in the per-call walk is indistinguishable from "outside Claude" and is silent ([[#b-1]]). Nothing reads the sink, and the CLI writes label a guess `explicit` ([[#s-2]]). |
| #s-1 owner | CLOSED in behaviour | The long-lived server keys on `os.getppid()`. The per-call walk accepts `$CLAUDE_PID` only if it is an ancestor (live chain `Python→bash→bash→claude(59363)`: owner 59363 with the env set, unset, or `=1`; `bug109-r2-bsd-hookchain.log`). Claude Code 2.1.293 builds each child env with `CLAUDE_PID:String(process.pid)` after the session fields, so nested-Claude hooks get the inner pid. Walk depth is unpinned ([[#s-3]] N10). Cost is in [[#m-1]]. |
| #s-2 vacuous test | CLOSED / coverage PARTIAL | The replaced test plus 5 new ones are RED at 54e13c6 (6 failed, 9 passed in `bug109-r1-red.log`) and GREEN at 320dc82. 9 of 11 r2 mutants survive ([[#s-3]]). |
| #s-3 promote-edges | CLOSED | The CLI resolves the session and sends it (cli.py:1496). M12 is killed. The daemon op and `promote.py` are unchanged, and both run on the same root. |
| #m-1..#m-4 | CARRIED, partly unanchored | See [[#m-2]]. |
| #m-5 summary / registry row | CLOSED | The summary is on the branch. The bug-109 row is on `wave0-spec-reviews` (bug_registry.md:162, status `open`), which is correct until merge. |

## Findings {#findings}

### BULLSHIT: under Claude, a `ps` failure in the owner walk reads as "not under Claude" and the resolve falls silently to another session's ring {#b-1}

**File:** `src/refmatrix/stm.py:144-186` (`_process_table`, `owner_claude_pid`) and
`src/refmatrix/verbs.py:542-557` (`if _LONG_LIVED or owner:` gate).

**What:** r1 #b-1 named "ps failure or timeout" as a silent path. The remedy records `ps-failed`
only inside `write_pid_pointer`. It also moved the per-call owner walk onto a new `ps -A` call
(timeout 3.0 s). When that call fails, `_process_table` returns None and `owner_claude_pid`
returns None, which is the same value it returns from a plain terminal. Two things follow:
- `resolve_session_source` records nothing, because `owner` is falsy and the process is not
  long-lived.
- It returns the newest ring, labelled `latest`, and the CLI discards that label (see [[#s-2]]).

The affected callers are the CLI write paths (`rmx focus note`, `rmx task push/pop/swap`,
`rmx save-state`), the PreCompact `save-state --no-promote` hook, and the Stop hook
`focus summarize --promote`. The last of these writes a durable `session/digest` memory, so on
this path another session's STM is promoted under the wrong session, and no record is left
anywhere. On the hook side, the same failure is recorded as `no-owner` rather than `ps-failed`.

**Evidence:** `workflow/review-output/bug109-r2-bsd-psfail.log`, run under Claude with a pointer
naming `sess-B` while the newest ring is `sess-C`:
```
ps ok   : ('sess-B', 'pointer')
ps fails: ('sess-C', 'latest')
_errors lines: 0
```
Under the load seen during this audit (load average 45-89, 1190 processes), `_process_table` took
a median of 56 ms but up to 1.0 s (`bug109-r2-bsd-cost.log`). The 3 s timeout is therefore a
plausible failure, not only a theoretical one.

**Fix (about 5 lines):**
- Make "could not tell" a value distinct from "no Claude ancestor". For example,
  `owner_claude_pid` could raise or return a sentinel when the table is None.
- In `resolve_session_source`, record `ps-failed` whenever the walk failed or `$CLAUDE_PID` is
  set. Claude Code sets `$CLAUDE_PID` for every child, so its presence means "under Claude" without
  a `ps` call.
- Have the hook record `ps-failed` instead of `no-owner` in the same case.
- Pin the change with a test that monkeypatches `_process_table` to None under a set `$CLAUDE_PID`.

**Pattern match:** YES. This is the r1 #b-1 shape on the branch the r1 report enumerated, and the
standing "silent drop on a memory path" pattern (impression imp-consolidated-0914). The remedy
fixed the quoted site (`write_pid_pointer`) while the sibling `ps` call keeps the bug
(imp-fix-at-quoted-line).

rel: contradicts -> [[claude-md#no-silent-failures]]

### SKETCHY: read verbs now write; one `rmx_focus` read creates `<cwd>/.refmatrix` and hijacks `_root()`, and an unwritable root turns a read into PermissionError {#s-1}

**File:** `src/refmatrix/verbs.py:555-557`, which calls `record_pointer_error` with no guard, and
`src/refmatrix/stm.py:194-197`, which runs `mkdir(parents=True)`.

**What:** `resolve_session_source` is shared by the read verbs `focus`, `task list/current` and
`recall_state`. On every unresolved resolve it now appends to `<root>/stm/by-pid/_errors.jsonl`,
creating parent directories as needed. `mcp._resolve_root` falls back to `<cwd>/.refmatrix` even
when that directory does not exist.

**Evidence:** `bug109-r2-bsd-readside.log` and `bug109-r2-bsd-readonly.log`, MCP read tools in a
cwd with no store:
- **At 54e13c6:** files created: `[]`. `cli._root()` stays at `~/.refmatrix`. A read in an
  unwritable cwd returns `default`.
- **At 320dc82:** the reads create `.refmatrix/stm/by-pid/_errors.jsonl`. After that, `cli._root()`
  in that tree becomes `/private/tmp/b9o…/.refmatrix`, a junk store, which breaks
  `_root`'s "never auto-create cwd/.refmatrix" contract (cli.py:88-90). A read in an unwritable
  cwd raises `PermissionError [Errno 13]`.

Write verbs already created the store at base: `rmx_focus_note` in a store-less cwd makes
`.refmatrix/stm/default.jsonl` at 54e13c6. The regression is that reads now do it too, and that
error logging can fail the operation it logs. Exposure on this workstation is low: refmatrix MCP is
configured in only one project scope. refmatrix is public, though.

**Fix:**
- Record only when `stm_dir(root)` already exists, and never `mkdir` the store root.
- Catch `OSError` around the record in `resolve_session_source`, falling back to one stderr line,
  so the log can never fail a read.

rel: contradicts -> [[claude-md#no-silent-failures]]

### SKETCHY: `_errors.jsonl` is write-only and unbounded, and the CLI write paths label a guessed session `explicit` {#s-2}

**File:** `src/refmatrix/stm.py:190-197` (the docstring says "where `rmx` can surface it"),
`src/refmatrix/cli.py:1420` (`focus note`), cli.py:2070 (`_task_verb`), cli.py:13129
(`save-state`) and cli.py:1674 (`change-subject`).

**What:**
- **No reader.** Nothing in `src/` reads `_errors.jsonl`: no hit outside the writer and tests.
  `recall-state` anomalies, `daemon status` and the `focus context` header do not show it. The
  sink has no rotation and no cap.
- **Growth, measured** (`bug109-r2-bsd-growth.log`, 30 calls each of `focus tail/context`, `task
  list`):
  - Under Claude with a pointer: 0 lines.
  - Under Claude with no pointer for that store: 30 lines, one per call, about 85 B each.
  - Detached from Claude (reparented to launchd, the plain-terminal shape): 0 lines, with and
    without a stale `$CLAUDE_PID`.

  So the answer to "none outside Claude" is yes. In a normal session the steady state is 0, plus 1
  line per resume start (the SessionStart `focus context` runs before the first prompt writes the
  pointer). Every STM call from Claude in a store the hook does not write to adds 1 line, for
  example a Bash-tool `cd` into another project, or a project with MCP but no input hook.
- **CLI labels lie.** Each CLI write command resolves the session itself and then passes it to the
  verb as an explicit argument. The verb therefore reports `session_source: explicit` for what was a
  newest-ring guess, and the CLI prints neither the session nor the source.

So the remedy surfaces a guess only on the MCP write tools. That is the core of bug-109, and it
works there. On the CLI and hook write paths the guess is visible only in a file nobody reads.

**Fix:**
- Have the CLI pass the raw `--session` (or None) and let the verb resolve and label it. Print the
  source when it is `latest`.
- Show the `_errors.jsonl` count (and its last reason) in `recall-state` anomalies.
- Cap or rotate the file.

**Pattern match:** YES. "Diagnostic fields written and read by nobody" (imp-consolidated-0914). The
remedy also followed my r1 one-line prescription ("record to a sink, label the source") verbatim,
and that prescription was narrower than the rule ("counted and printed").

rel: contradicts -> [[claude-md#no-silent-failures]]

### SKETCHY: 9 of 11 r2 mutants survive; the record gate, the hook records, three labels and the walk depth are unpinned {#s-3}

**Evidence:** `workflow/review-output/bug109-r2-bsd-mutations.log`. Suite: test_mcp_session_pointer,
test_task_cli_session, test_save_state, test_mcp_write, test_mcp_tools, test_stm, test_hooks.

| Mutant | Result |
|--------|--------|
| N1 record on every fallback (a plain terminal would log) | SURVIVED |
| N2 CLI-under-Claude fallback unrecorded | SURVIVED |
| N3 hook `no-owner` record removed | SURVIVED |
| N4 hook `write-failed` record removed | SURVIVED |
| N5 `save_state` without `session_source` | SURVIVED |
| N6 `task` push/pop/swap without `session_source` | SURVIVED |
| N7 `change_subject` without `session_source` | SURVIVED |
| N8 nearest-claude walk skips the immediate parent | KILLED |
| N9 CLI order pointer-before-`$RMX_SESSION` | SURVIVED |
| N10 walk depth 2 (the real hook chain `python→sh→claude` needs 3) | SURVIVED |
| N11 sink to /dev/null | KILLED |

N1 and N2 together mean the "nothing outside Claude, something under Claude" property is untested
in both directions. N10 can blind every installed input hook while the suite stays green: the tests
use `$CLAUDE_PID=os.getpid()` or a one-hop fake. r1's M7-M12 are all killed, and that claim checks
out. The remedy's tests pin 2 of 5 recording sites and 1 of 4 label sites.

**Fix:** Add one test per mutant above, and a hook test that drives
`focus hook --event input` through a 3-hop `sh` chain with `$CLAUDE_PID` unset.

### MEH: `ps -A` on every per-call resolve and every input hook adds about 60 ms {#m-1}

**Evidence:** `bug109-r2-bsd-hookcost.log` and `bug109-r2-bsd-cost.log`. Both trees used compiled
`.pyc`, runs were alternated, the store was a tmp store, and the machine had 1190 processes at load
about 45.

| Path | 54e13c6 (median) | 320dc82 (median) |
|------|------------------|------------------|
| `focus hook --event input` (pointer current) | 74 ms | 135 ms |
| `focus tail` | 85 ms | 146 ms |
| MCP resolve (getppid + `ps lstart`) | — | 2.5-3 ms |

- On the MCP path the resolve uses `getppid` plus one `ps lstart`, which is fine.
- The walk runs even when `$RMX_SESSION` will win. The summary's "an unchanged pointer costs one
  read and no `ps`" is no longer true of the hook.
- Claude Code sets `$CLAUDE_PID` to its own pid in every child, so a two- or three-hop
  `ps -o ppid= -p` check against it (r0's cost) would do.

Acceptable as it stands: the Stop and UserPromptSubmit hooks have 5 s bounds and run alongside
scan-prompt.

### MEH: r1 #m-1..#m-4 are carried to a spec that was not amended {#m-2}

**What:** The summary says that `composite.py:103`, `helix.py:96`, `focus record/clear`,
SessionStart, the store-root split and `by-pid/` cleanup are "owned by 19.0 R5, which must list
them".
- R5 is at `task-19.0-stm-cluster-hygiene.md:187-216`, on `wave0-spec-reviews` (a820b22), which
  is not on master.
- It anchors the SessionStart pointer write and newest-ring labelling for reads.
- Its umbrella ("every resolver of 'this session' used by STM") arguably covers composite, helix
  and record/clear, but it lists none of them.
- No acceptance criterion anywhere covers `by-pid/` cleanup, the store-root split, or the new
  `_errors.jsonl` retention.

**Fix:** Amend R5's site list and add an acceptance criterion for by-pid/errors retention. Until
then those three items are unanchored (rule 9a).

### MEH: pre-existing flake in test_save_state_embeds_memories (DuckDB WAL lock conflict) {#m-3}

**Evidence:** `bug109-r2-bsd-targeted.log` shows 1 failed out of 197:
`Could not set lock on file …/catalog.A.duckdb.wal: Conflicting lock is held`, in a tmp store owned
by the test's own daemon.
- Reruns at 320dc82: 1 failed, then 18 passed (`bug109-r2-bsd-embeds-rerun.log`).
- At a434f51: 18 passed, 18 passed, then 2 failed (`bug109-r2-bsd-embeds-at-base.log`).

This diff did not cause it. It has no bug_registry row; log one.

## Wiring {#wiring}

- **MCP.** `serve_stdio` sets `_LONG_LIVED`, and the tools dispatch to verbs that return
  `session_source`. The result is JSON-dumped whole (mcp.py:213), so the agent sees it.
- **Hook.** The input hook goes through the same `owner_claude_pid` as before, with records on the
  no-owner and write-failed branches.
- **promote-edges.** It is CLI-resolved. No dead code was found.
- **Callers that changed behaviour.** All of them go through `resolve_session_source`: CLI
  `_resolve_stm_session(prefer_latest=True)`, verbs `focus` / `recall_state` / `focus_note` /
  `change_subject` / `task` / `save_state`, and Stop/PreCompact via the CLI. The changes are the
  record and mkdir ([[#s-1]]) and one `ps -A` per call ([[#m-1]]). The resolution order is
  unchanged from 06ecd0f.
- **Tests.** 196 of 197 targeted tests pass, plus 1 skip. The single failure is the [[#m-3]] flake.

## Merge / deploy {#merge-deploy}

- **Merge gate:** not clean, because of 1 BULLSHIT ([[#b-1]]).
- **Compared with base:** on the happy path this branch is strictly better than a434f51. Base fell
  silently to the newest ring in every case. This branch does so only when `ps` fails under Claude.
- [[#b-1]] and [[#s-1]] together are about 10 lines plus 2 tests. Fix them, then merge.
- If the user chooses to deploy now, the residual risk is a misrouted Stop digest during a `ps`
  failure. That is narrower than today's behaviour on master.

## Verdict {#verdict}

DIRTY — 7 findings (1 BULLSHIT, 3 SKETCHY, 3 MEH). Merge-blocking: [[#b-1]].

rel: contradicts -> [[claude-md#no-silent-failures]]
rel: evidence-for -> [[task-19.0-stm-cluster-hygiene]]
