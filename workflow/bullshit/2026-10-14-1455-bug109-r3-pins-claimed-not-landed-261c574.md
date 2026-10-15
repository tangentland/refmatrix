---
gmd: "0.1"
id: bsd-bug109-r3-261c574
title: "ch-bsd r3 — bug-109 r2 remedies (0760fb7, 261c574): behaviour closed and the kernel lookup is right; two named pins never landed, and an old pointer for the current session is never repaired"
severity: BULLSHIT
plan: bug-109
task: d9s
tags: [bsd, audit, bug-109, stm, mcp, session, mutation, r3]
---

# ch-bsd r3 — fix(stm,verbs,handoff): bug-109 r2 remedies (0760fb7) + test (261c574) {#root}

**Commit range:** 320dc82..261c574, read against base a434f51.
**Date:** written 2026-10-14T14:55:08-0700.
**Author:** Todd Holley / Opus 5.5 / orchestrator.
**Files changed:** cli.py, handoff.py, stm.py, verbs.py, tests/test_mcp_session_pointer.py, the
r2 report, ledger files, the implementation summary.
**Tree:** isolated clone `/Volumes/littlebig/refmatrix-bug109`, branch `bug-109-mcp-session`,
HEAD 261c574. 13 mutations were each restored with `git checkout`, `__pycache__` was cleared, and
`git status -- src tests` is clean. No live store or socket was touched. Live evidence comes from
read-only `proc_pidinfo` / `ps` sampling and throwaway `/tmp` stores.

rel: evidence-for -> [[bsd-bug109-r2-320dc82]]

## r2 status {#r2-status}

| r2 id | Status | Evidence |
|-------|--------|----------|
| #b-1 ps failure silent | CLOSED in behaviour | `bug109-r3-bsd-psfail.log`, with the pointer on sess-B and the newest ring sess-C. Kernel ok: `('sess-B','pointer')`, 0 lines. `ps` fails but the kernel works: `('sess-B','pointer')`, 0 lines, because the kernel path needs no `ps`. Both fail: `('sess-C','latest')` plus an `owner-lookup-failed` row. M13 is killed. The hook's `owner-lookup-failed` label (P3) and the `$CLAUDE_PID` record trigger (P6) are unpinned; see [[#b-1]]. |
| #s-1 reads create stores | CLOSED | `bug109-r3-bsd-sim.log` §6: in a store-less root the resolve returns `default` and creates nothing. With an unwritable `stm/` it returns `default` and does not raise. M15 is killed. "Never raises" is unpinned (P8 survives). |
| #s-2 sink unread / CLI labels lie | CLOSED, with residue | The reader is `handoff.session_pointer_anomalies`, wired into `compose_recall_state` (handoff.py:561); M16 is killed by 261c574. The CLI note, task, change-subject and save-state paths now pass the raw `--session`, and `save-state` prints the source. Residue: `focus note` and `task` print no source; the task/save-state label change is unpinned (P10, P11); the anomaly text over-claims writes ([[#m-1]]); and a malformed line crashes `recall-state` ([[#m-2]]). |
| #s-3 9/11 mutants survive | PARTIAL | N1, N2, N3, N6, N7, N9 and N10 are now pinned (M13-M20 killed). **N4 (hook `write-failed` record) and N5 (`save_state` `session_source`) still survive as P5 and P4.** Neither the commit message nor the summary mentions them. See [[#b-1]]. |
| #m-1 +60 ms per hook | CLOSED | `bug109-r3-bsd-hookcost.log` shows hook and tail medians for each build. 54e13c6: 66 / 77 ms. 320dc82: 121 / 131 ms. 261c574: 69-70 / 75 ms. `owner_lookup` takes 2.4 ms with 0 subprocesses under a real `$CLAUDE_PID` (`bug109-r3-bsd-hookchain.log`). With `$CLAUDE_PID` unset, one `ps` runs: 123-125 ms per hook, about 55 ms per lookup. That path is rare, since every sampled hook child carries `$CLAUDE_PID`. |
| #m-2 R5 unamended | CLOSED (anchored) | 19.0 R5 on wave0-spec-reviews HEAD 734dc5f lists composite, helix, `focus record` / `focus clear`, the root split and by-pid cleanup, and routes the rest to 21.1 R9 D3-D8. Some of the specs' citations are now stale; see [[#m-3]]. |
| #m-3 embeds flake | CLOSED | bug-108 row on wave0-spec-reviews (bug_registry.md:161, `open`). |

## Hard checks {#hard-checks}

- **The `proc_bsdinfo` struct is correct.** Size 136. Offsets: ppid 16, comm 48, name 64, nice 116,
  start_sec 120, start_usec 128. These match xnu `sys/proc_info.h`: 4 u32, then ppid, 7 ids, comm[16],
  name[32], 5 u32, nice, and 2 u64 fields aligned at 120. Checked against `ps` for every process on the
  machine (`bug109-r3-bsd-struct.log`): 1182 processes, 801 readable, **801/801 ppid and start
  matched** (start within 1 s of `lstart`), 0 mismatches. That set includes Claude processes
  (native `.../claude/versions/2.1.27x-2.1.292`, all `_is_claude` True), the own chain
  `Python→bash→claude(59363)→bash→iTermServer→iTerm2`, and launchd children.
- **Other users' processes and pid 1** return None for all 379 such pids. xnu applies
  `CHECK_SAME_USER` to PROC_PIDTBSDINFO. The walk stops at the first root-owned ancestor, which
  is always above Claude in real chains. If fewer than 2 links are readable, the code falls back
  to one `ps`.
- **IntelliJ ACP Claude** runs under `node`, so `_is_claude` is False for its executable. It is
  still found through `$CLAUDE_PID`, or through the `ps` argv[0]. Its MCP server (5555 under 4405)
  keys on `getppid`.
- **Pointer compatibility.** `_proc_start` is the only writer and reader of `pid_start`, so a
  single build always agrees with itself; the round-trip passes. The format changed from r1's
  `lstart` string to `sec.usec`. A mixed build therefore reads every old pointer as stale, and
  **the new hook never repairs one that names the current session** ([[#s-1]]). This was
  demonstrated: 30 unresolved records across 30 reads. No live store has a `by-pid/` directory
  today, so nothing live is stranded.
- **Real hook chain** (`bug109-r3-bsd-hookchain.log`), python→sh→bash→claude:
  - `$CLAUDE_PID` set: `(59363,'found')` with 0 subprocesses.
  - Unset: `(59363,'found')` with 1 `ps`.
  - `=1` (not an ancestor): `(59363,'found')`.
  - Detached to launchd, with or without a stale env: `(None,'none')`. With the stale env the
    resolver records the guess, which is acceptable.
  - `=61114` (an ancestor that is bash, not Claude) is accepted, as designed since r1.
- **Write verbs.** `focus_note`, `task`, `change_subject` and `save_state` all return
  `session_source` (verbs.py:901/961/988/1034). The CLI now hands them the raw `--session`, and
  resolution is unchanged, because `_resolve_stm_session(prefer_latest=True)` is `resolve_session`.
  The removed `sess` variable has no remaining readers in `save_state` or `change_subject`. The
  Stop hook (`focus summarize --promote`) still resolves through the same function.
- **Tests:** 219 passed, 1 skipped, across 17 files (`bug109-r3-bsd-targeted.log`).

## Findings {#findings}

### BULLSHIT (escalated): two mutants the r2 report named are still unpinned while the commit says "pins added", and the r2 remedy's own new branches are unpinned {#b-1}

**Evidence:** `workflow/review-output/bug109-r3-bsd-mutations.log`. Suite: test_mcp_session_pointer,
test_task_cli_session, test_save_state, test_mcp_write, test_stm, test_subject, test_hooks
(97 tests). 13 mutants: 1 killed, 12 survived.

| Mutant | Result | What it means |
|--------|--------|---------------|
| P1 struct ppid offset wrong (size kept at 136) | SURVIVED | A broken struct cannot be seen. The walk breaks at length 1 and the `ps` fallback hides it, so the "no subprocess on the common path" claim is unpinned. |
| P2 kernel lookup disabled | KILLED | — |
| P3 hook records `no-owner` for a FAILED lookup | SURVIVED | The r2 #b-1 hook half is unpinned. |
| P4 `save_state` without `session_source` | SURVIVED | **r2 N5, named in #s-3, still survives.** |
| P5 hook `write-failed` record removed | SURVIVED | **r2 N4, named in #s-3, still survives.** |
| P6 `$CLAUDE_PID` is not a record trigger | SURVIVED | The r2 #b-1 rule "a set `$CLAUDE_PID` counts as under Claude" is unpinned. |
| P7 sink uncapped | SURVIVED | The 256 KiB cap is unpinned (it works: 499,732 B to 250,569 B in the sim). |
| P8 sink re-raises OSError | SURVIVED | r2 #s-1 "never raises" is unpinned. |
| P9 anomaly window ignored | SURVIVED | — |
| P10 CLI task passes a pre-resolved session as explicit | SURVIVED | r2 #s-2 is pinned on `note` only. |
| P11 CLI save-state passes a pre-resolved session as explicit | SURVIVED | Same as P10. |
| P12 native `.../claude/versions/<v>` not recognised | SURVIVED | Hidden by `$CLAUDE_PID` and the argv[0] fallback. |
| P13 `pid_start` in seconds only | SURVIVED | Harmless. |

**Why this blocks:**
- The behaviour is correct; I verified every branch live above.
- The r2 report asked for N4 and N5 by name. 0760fb7 says "#s-3: pins for …" and lists the others
  without mentioning those two. That is a silent scope shrink (rule 10).
- The remedy's own new branches (P3, P6, P8, P10, P11) ship unpinned. Those are the branches that
  close r2's BULLSHIT and two of its SKETCHY findings.
- This is the third round in a row on bug-109 where the remedy's tests pin less than claimed:
  r1 #s-2 (a vacuous test), r2 #s-3 (9/11 survive), and r3. The same pattern appears in the
  ledger at r12 (K3 "claimed pinned") and in imp-route-named-helper-tested. Per the escalation
  rule, SKETCHY becomes BULLSHIT.

**Fix (tests only, about 40 lines):** add one test per survivor, P1 to P11.
- **P1:** assert `owner_lookup()` with `$CLAUDE_PID=os.getppid()` makes no `subprocess.run` call.
  Better, also assert `_proc_info(os.getpid())[0] == os.getppid()`.
- **P3:** use `owner_lookup → (None,'failed')`, then check the hook writes the
  `owner-lookup-failed` row.
- **P5:** make `write_pid_pointer` raise OSError, then check for the `write-failed` row.
- **P6:** use `owner_lookup → (None,'none')` with `$CLAUDE_PID` set; expect one row.
- **P8:** make `p.open` raise; expect `record_pointer_error` to return False.
- **P4:** add `save_state` to the parametrize in `test_every_stm_write_verb_reports_its_source`.
- **P10, P11:** spy tests like `test_cli_note_reports_the_real_source_not_explicit`.

**Pattern match:** YES. imp-heal-runs-once, imp-route-named-helper-tested, and the r2 #s-3 row.

rel: contradicts -> [[claude#task-completion-workflow]]

### SKETCHY: the hook's same-session shortcut never repairs a pointer whose `pid_start` no longer matches, so an older-build pointer stays stale for the whole session {#s-1}

**File:** `src/refmatrix/stm.py`, `write_pid_pointer`. It returns False when the file already
names `session`, and never compares `pid_start`.

**What:**
- r2 changed `pid_start` from `ps lstart` (`"Tue Oct  6 22:27:56 2026"`) to `sec.usec`.
- `read_pid_pointer` compares exactly. A pointer written by 06ecd0f, 54e13c6 or 320dc82 therefore
  reads as stale on 261c574.
- The input hook does run every turn, but its shortcut sees the same session and skips the
  rewrite. The pointer stays stale for the rest of that Claude session.
- As a result, every MCP or CLI resolve falls to the newest ring and records a generic
  `pointer-unresolved`.

**Evidence:** `bug109-r3-bsd-hookcost.log`, three builds against one tmp root. 54e13c6 wrote
`{"session":"sess-H","pid_start":"Tue Oct  6 22:27:56 2026"}`, then 261c574's hook ran 30 times and
did not repair it. Every 261c574 `focus tail` produced a `pointer-unresolved` row (30 rows). The
same harness on a fresh root gave 0 rows. `bug109-r3-bsd-sim.log` §2 isolates it:
`write_pid_pointer(..., same session)` returns `False` and `read_pid_pointer` returns `None`.

**Exposure:**
- **Latent today.** No live store has `stm/by-pid/`, and no pre-r2 build was ever deployed or ran
  in the main tree.
- **But the next format change, or any start-time drift, reproduces it.** 21.1 R9 (task-21.1:204)
  carries the same shortcut ("an unchanged pointer costs one read").
- **The shortcut no longer buys anything.** It existed to avoid a `ps`, and `_proc_start` is now a
  microsecond kernel call.

**Fix (2 lines):** take the shortcut only when `session` matches AND `pid_start == _proc_start(pid)`.
Pin it with an old-format pointer for the current session, which the hook must rewrite.

rel: contradicts -> [[claude#no-silent-failures]]

### SKETCHY: merge plus deploy does not reach the MCP server that bug-109 was found in {#s-2}

**What:** In this project, `.mcp.json` runs `.venv-eval/bin/rmx mcp`. That server imports
`/Users/tholley/claude_tools/refmatrix/src` (checked with `env PYTHONPATH= …`: `owner_lookup`
False, `read_pid_pointer` False). That tree is on `wave0-spec-reviews`, which has neither
06ecd0f nor any later bug-109 commit, and it is a shared tree with uncommitted work, so no branch
switch is allowed.

After the bug-109 branch is merged to master and deployed:
- The hooks (`~/bin/rmx`) write pointers.
- The other projects' servers (`~/bin/rmx mcp`: 31287, 57974, 14297) get the fix after `/mcp`
  reconnect.
- This project's server (59378, and 5555 under IntelliJ) keeps base behaviour: the newest ring,
  unlabelled, with nothing recorded.

The summary's Deploy section ("Deploy first, then reconnect `/mcp`") does not name this. The
outcome is no regression, but the fix is not live in the session that reported it.

**Fix:** state it in the summary and the deploy step. Either merge master into
`wave0-spec-reviews` (with the peer session's agreement), or point the refmatrix-project MCP at
`~/bin/rmx` until it does. Then verify with `rmx_focus_note` returning `session_source: pointer`.

### MEH: the anomaly says "STM writes may have used a guessed session" for read-path guesses, and each resume adds one {#m-1}

**Evidence:** `bug109-r3-bsd-sim.log` §1. A single `verbs.focus` READ under Claude with no pointer
produces `pointer-unresolved`. Then `session_pointer_anomalies` says "STM writes may have used a
guessed session".
- The rows carry no op or verb, so read guesses and write guesses cannot be told apart.
- The SessionStart(resume) hook runs `rmx focus context` in a new Claude process before the first
  prompt writes its pointer, so every `claude --resume` or `-c` adds one row.
- On a normal day, then, the anomaly fires on reads alone. A warning that fires on most days
  stops being read.

**Fix:** record `verb=`/`write=` in each row, and count only write rows in the anomaly; or word the
anomaly as "resolves". This is covered in substance by 21.1 R9 D6, so it is anchored.

### MEH: one malformed `_errors.jsonl` line makes `rmx recall-state` raise {#m-2}

**Evidence:** `bug109-r3-bsd-sim.log` §5. A non-dict JSON line (`[1, 2]`) makes
`read_pointer_errors` raise `AttributeError: 'list' object has no attribute 'get'`. A non-numeric
`t` raises ValueError, which the outer `except OSError` does not catch.
`compose_recall_state` calls it unguarded, so recall-state fails outright. Unparseable lines are
skipped and not counted.

Truncation keeps whole lines, so corruption is unlikely, but this is a diagnostic reader that can
take down the session-resume command.

**Fix:** validate `isinstance(row, dict)`, catch `(TypeError, ValueError)` per row, and count the
skipped rows into the anomaly.

### MEH: 19.0 R5 / 21.1 R9 cite code that 0760fb7 removed {#m-3}

**What:** task-21.1 lines 207 and 280 at 734dc5f cite `_proc_start` as `ps -o lstart=` and name
`stm._process_table()` for the D7 by-pid cleanup. 0760fb7 deleted `_process_table`; it is now
`_proc_info` and `_ps_comm_chain`, and `pid_start` is `sec.usec`. 19.0 R5 reads bug-109 "at
`320dc82`" and names `owner_claude_pid` as the entry point; it now wraps `owner_lookup`. D6 also
specifies a SessionStart surfacer with a watermark, while r2 shipped a 24 h recall-state reader,
so there will be two surfacers unless the spec absorbs the shipped one.

**Fix:** re-read bug-109 at its merge sha and update both specs before 19.0 or 21.1 starts. Their
own dependency line ("the merge, not a sha") already requires this.

## Wiring {#wiring}

- **Kernel lookup.** `owner_lookup` is reached from the hook (cli.py:1981) and from the per-call
  resolve (verbs.py:545). The MCP server keys on `getppid`.
- **Sink reader.** `session_pointer_anomalies` is reached from `compose_recall_state`, which serves
  both the CLI `recall-state` and `rmx_recall_state`.
- **Cap.** It is live inside `record_pointer_error`.
- **Dead code.** None. `owner_claude_pid` is still called by tests and by the long-lived branch
  wrapper.
- **Linux `/proc` branch.** Unexecuted on this host. By inspection, `fields[1]` is ppid and
  `fields[19]` is starttime, which is correct.

## Merge / deploy {#merge-deploy}

- **Behaviour:** safe. Every r2 branch was verified live, the struct matches the kernel on 801/801
  processes, and the hook costs base +3 ms. This branch is strictly better than a434f51 on every
  path probed.
- **Merge gate:** not clean, because of [[#b-1]]. That fix is tests only, about 40 lines.
- **Before merge:** take [[#s-1]], 2 lines plus 1 test.
- **Deploy:** reaches every project except this one's MCP server ([[#s-2]]).

## Verdict {#verdict}

DIRTY — 6 findings (1 BULLSHIT, 2 SKETCHY, 3 MEH). Merge-blocking: [[#b-1]] (test pins; escalated).

rel: contradicts -> [[claude#no-silent-failures]]
rel: evidence-for -> [[task-19.0-stm-cluster-hygiene]]
rel: evidence-for -> [[task-21.1-context-usage-telemetry]]
