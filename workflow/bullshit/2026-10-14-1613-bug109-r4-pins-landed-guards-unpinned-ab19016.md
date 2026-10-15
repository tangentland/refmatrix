---
gmd: "0.1"
id: bsd-bug109-r4-ab19016
title: "ch-bsd r4 — bug-109 r3 remedies (9fe45fa, ab19016): every claimed pin landed (17/17 reproduced), the stale pointer is repaired, the hook costs base +1 ms; the remedy's own exception guards are unpinned again and corrupt input still raises on two read paths"
severity: SKETCHY
plan: bug-109
task: d9af
tags: [bsd, audit, bug-109, stm, mcp, session, mutation, r4]
---

# ch-bsd r4 — fix(stm,handoff): bug-109 r3 remedies (9fe45fa) + docs (ab19016) {#root}

**Commit range:** 261c574..ab19016, read against base a434f51.
**Date:** written 2026-10-14T16:13:20-0700.
**Author:** Todd Holley / Opus 5.5 / orchestrator.
**Files changed:** handoff.py, stm.py, tests/test_mcp_session_pointer.py (9fe45fa); the r3 report,
ledger files and the implementation summary (ab19016).
**Tree:** isolated clone `/Volumes/littlebig/refmatrix-bug109`, branch `bug-109-mcp-session`,
HEAD ab19016. 30 mutations (17 remedy + 13 own) were each restored with `git checkout --`,
`__pycache__` cleared, `git status` clean afterwards. No live store or socket was touched: hook
runs used throwaway roots under `/private/tmp/claude-501/r4h`, built from `git archive` copies of
a434f51, 261c574 and ab19016; the process facts are read-only `proc_pidinfo` / `ps`.

rel: evidence-for -> [[bsd-bug109-r3-261c574]]

## r3 status {#r3-status}

| r3 id | Status | Evidence |
|-------|--------|----------|
| #b-1 pins claimed, not landed | CLOSED | `bug109-r4-bsd-remedy-rerun.log`: the remedy script re-run by me, **17/17 KILLED** (P1-P13, R1-R4), each by the test the summary names, tree clean after. r2's N4/N5 are P5/P4, both killed. P1 is killed by the zero-subprocess assertion, so the `ps` fallback no longer masks the struct. Every claim in 9fe45fa's message checks out. |
| #s-1 same-session shortcut never repairs | CLOSED | Code: the shortcut now requires `start is not None and session == and pid_start == _proc_start(pid)`. Live (`bug109-r4-bsd-hookcost.log`, "stale"): an r1-format `lstart` pointer for the current session under the real Claude pid 59363. 261c574: 10 hooks, pointer unchanged, 10 `pointer-unresolved`. ab19016: rewritten on the first hook to `"pid_start": "1791350876.439486"`, 0 errors. R1 killed. |
| #s-2 deploy misses this project's MCP | CLOSED | The summary's Deploy section names it. Verified: `.mcp.json` runs `.venv-eval/bin/rmx mcp` with `PYTHONPATH=""`. That interpreter imports `/Users/tholley/claude_tools/refmatrix/src/refmatrix/__init__.py`, and the tree is on `wave0-spec-reviews` (d5ad060), which lacks bug-109. Live servers: 59378 (under Claude 59363) and 5555 (under IntelliJ 4405) run the main tree. 31287, 57974 and 14297 run `~/bin/rmx mcp`. d9af already decides to merge `master` into `wave0-spec-reviews`. Residue in [[#m-3]]. |
| #m-1 anomaly says "writes" | CLOSED | The text now says "STM calls may have used a guessed session". R4 killed. Per-row `verb=` / `write=` is anchored to 21.1 R9 D6. |
| #m-2 malformed sink line crashes recall-state | PARTIAL | `bug109-r4-bsd-probe.log`: a non-dict line, a non-numeric `t`, a missing `t` and a `null` `t` are each counted as `unreadable-line`, and recall-state survives. **A non-UTF-8 byte still raises `UnicodeDecodeError` out of `session_pointer_anomalies`**, so recall-state still fails. The KeyError and TypeError arms are unpinned (Q10, Q11). See [[#s-1]] and [[#m-1]]. |
| #m-3 19.0 / 21.1 cite removed code | OPEN, anchored | On `wave0-spec-reviews` d5ad060, task-19.0 still reads bug-109 "at `320dc82`" and names `owner_claude_pid` (lines 60-228). task-21.1 still has 2 `_process_table` / `lstart` hits. Both specs' dependency line requires a re-read at the merge, so this is anchored and not blocking. |

## Hard checks {#hard-checks}

- **Targeted suite.** 21 files: 289 passed, 1 skipped, 1 failed (`bug109-r4-bsd-targeted.log`). The
  failure is `test_save_state_embeds_memories::test_no_memory_row_is_left_without_a_vector` with the
  WAL-lock signature of bug-108 (`open`, bug_registry.md:161 on wave0-spec-reviews). Re-run alone:
  18/18 passed (`bug109-r4-bsd-embeds-rerun.log`). This is the known flake, not bug-109.
- **Hook cost** (`bug109-r4-bsd-hookcost.log`). Ordinary load (load averages 10.7 / 10.9 / 10.4), 30
  runs each, compiled trees, real `$CLAUDE_PID`:

  | Build | Hook median | Hook p90 | Tail median |
  |-------|-------------|----------|-------------|
  | a434f51 | 68 ms | 71 ms | 74 ms |
  | 261c574 | 69 ms | 70 ms | 75 ms |
  | ab19016 | 69 ms | 72 ms | 74 ms |
  | ab19016, `$CLAUDE_PID` unset | 127 ms | 133 ms | 132 ms |

  The fix costs base +1 ms. The unset path pays one `ps`, about +58 ms. Every sampled hook child
  carries `$CLAUDE_PID` (r3 hookchain log), so that path is rare. All runs exited 0 with empty
  stderr and 0 sink rows.
- **Concurrency** (`bug109-r4-bsd-concurrent.log`). 24 simultaneous input hooks, with three sessions
  racing for one Claude pid (a `/clear` storm). All 24 exited 0 with no stderr and no sink rows.
  One pointer remained, naming the last session. Rings: 8 / 8 / 8, so no prompt was lost.
- **Failure modes on the live hook path.** The hook catches only `OSError` around the pointer block.
  Anything else aborts the hook before `s.record("input", …)`, and the hook's `2>/dev/null || true`
  makes that silent. What can still raise:
  - **Non-dict pointer:** handled. `write_pid_pointer` catches `AttributeError` and rewrites (probe:
    `[1]`, `null` and `"s"` each give True). This handling is unpinned (Q2, [[#s-1]]).
  - **Sink over 256 KiB containing a non-UTF-8 byte:** `record_pointer_error` raises
    `UnicodeDecodeError` from the trim read, out of the hook's `no-owner` / `owner-lookup-failed`
    branch and out of every guessing resolve ([[#m-1]]). Every writer emits `json.dumps` ASCII, and a
    torn ASCII write is still valid UTF-8, so only disk corruption or a hand edit reaches it.
  - **Nothing else** was found that is reachable from data this code writes.
- **Watcher.** `stm/by-pid/` lives under the hidden `.refmatrix/`, which `watch.is_relevant` excludes.
  The pointer and the sink never reach ingest.
- **Wiring is unchanged since r3.** `owner_lookup` is called from the hook (cli.py:1981) and the
  resolve (verbs.py:545). `session_pointer_anomalies` is called from `compose_recall_state`
  (handoff.py:569), which serves both the CLI and `rmx_recall_state`. `serve_stdio` sets
  `_LONG_LIVED`. The daemon, the hub and the hooks generator are untouched (`hooks.py` is not in
  a434f51..ab19016), so `install-hooks --check` is unaffected. The verb parity test passed in the
  targeted run.
- **Version.** `pyproject.toml` reads 0.77.2 at a434f51, at ab19016, on main-tree `master` and
  `wave0-spec-reviews`, and in `~/refmatrix`. This branch bumps nothing, so no dev-venv MCP can trip
  the hub's version handshake (that handshake is hub against worker in `modelsrv`, not MCP clients).

## Own mutants {#own-mutants}

These were run with the remedy's harness and suite (7 files, 113 tests). The log is
`bug109-r4-bsd-mutations.log`. 13 mutants: 7 killed, 6 survived.

| Mutant | Result | Note |
|--------|--------|------|
| Q1 sink trim keeps the OLDEST half | SURVIVED | P7 checks the size only. The docstring's "the oldest half is dropped" is unpinned. A flip would drop recent failures, which are the ones the anomaly window reads. |
| Q2 `write_pid_pointer` drops the `AttributeError` arm (new in 9fe45fa) | SURVIVED | Without it, a non-dict pointer raises out of the hook (which catches only `OSError`), and the prompt goes unrecorded silently. |
| Q3 blank sink lines counted as unreadable | SURVIVED | Cosmetic; no writer emits blank lines. |
| Q4 unreadable rows filtered by the window | KILLED | — |
| Q5 only-unreadable branch removed | KILLED | — |
| Q6 `ps-failed` not recorded | KILLED | — |
| Q7 hook points at its own parent, not the owner | KILLED | — |
| Q8 reader ignores `pid_start` | KILLED | — |
| Q9 shortcut drops `start is not None` | SURVIVED | Equivalent in practice: a null `start` means the owner is gone, and nothing writes a null `pid_start`. |
| Q10 `read_pointer_errors` drops the `KeyError` arm (r3 #m-2 fix) | SURVIVED | A dict without `t` would take recall-state down again, which is exactly r3 #m-2. |
| Q11 `read_pointer_errors` drops the `TypeError` arm (r3 #m-2 fix) | SURVIVED | Same for `"t": null`. |
| Q12 `$CLAUDE_PID` accepted without the ancestry check | KILLED | — |
| Q13 anomaly window default widened to a week | KILLED | — |

## Findings {#findings}

### SKETCHY: the r3 remedy's own exception guards are unpinned, the fourth bug-109 round in a row where a remedy's new branches ship untested {#s-1}

**File:** `src/refmatrix/stm.py`. The guards are in `write_pid_pointer` (the `AttributeError` arm) and
`read_pointer_errors` (the `KeyError` and `TypeError` arms). The cap direction is in
`record_pointer_error`.

**What:** 9fe45fa added these guards and they work: the probe exercises every one of them live.
But Q2, Q10 and Q11 each delete one and the suite stays green. Q1 shows the P7 "cap" pin checks the
size and not which half is dropped.

**Why SKETCHY and not escalated to BULLSHIT:** the escalation rule would allow it, since this pattern
appeared in r1 #s-2, r2 #s-3 and r3 #b-1. But r3's blocker was a false claim: named mutants were
said to be pinned and were not. Here every claimed pin landed (17/17 reproduced). The survivors are
exception-tuple members the commit never claimed individually. They guard input this code never
writes, and their behaviour is correct at HEAD. So the gap is one of discipline, not of truth.

**Fix (tests only, about 20 lines):**
- Q2: write `[1]` as the pointer, run the input hook through `CliRunner`, and assert the pointer
  then reads the session and the prompt is in the ring.
- Q10 and Q11: add `{"reason":"x"}` and `{"t":null}` lines to
  `test_a_malformed_sink_line_does_not_break_recall_state`.
- Q1: after the trim, assert the newest seeded row survives and the oldest does not.

**Pattern match:** YES. imp-route-named-helper-tested, imp-heal-runs-once, r3 #b-1.

rel: contradicts -> [[claude#task-completion-workflow]]

### MEH: corrupt input still raises on two read paths; the write side got the guard, the read side did not {#m-1}

**Evidence:** `bug109-r4-bsd-probe.log`.
- **`read_pid_pointer`** catches `(OSError, ValueError)` only. A pointer holding `[1]`, `null` or
  `"s"` raises `AttributeError` out of `resolve_session_source`, and so out of every MCP STM verb and
  CLI focus read. The next input hook rewrites the pointer (the write side catches it), so this heals
  within one turn.
- **`read_pointer_errors`** catches `OSError` around `read_text`. A non-UTF-8 byte raises
  `UnicodeDecodeError` out of recall-state, which is r3 #m-2's symptom. `record_pointer_error`'s
  trim read does the same once the file exceeds 256 KiB.
- A `NaN` `t` is dropped without being counted.

All three need corruption or a hand edit, because the writers emit atomic, ASCII-only JSON.

**Fix (about 4 lines):**
- `isinstance(d, dict)` in `read_pid_pointer`.
- `read_text(encoding="utf-8", errors="replace")` in both sink readers, so a bad byte becomes an
  `unreadable-line` row.
- Treat a non-finite `t` as unreadable.

rel: contradicts -> [[claude#no-silent-failures]]

### MEH: no full-suite run is recorded on the branch {#m-2}

**What:** `CLAUDE.md` before-commit gate: "Tests pass (all), log captured". The summary records only
the families: 276 at r3, 259 at r2, 249 at r1. This audit ran 21 files (289 passed). I did not run
the full suite, because it reaches live sockets
(project_suite_reaches_live_sockets: models.sock and global), which this audit's rules forbid. The
diff touches cli.py's click tree and verbs.py's resolver, both shared by many test files outside the
families.

**Fix:** run the full suite once where live sockets are acceptable, or under the 23.0 sandbox, before
the merge commit. Record the log in the summary.

### MEH: the deploy note is right, but its verification step cannot tell old code from new {#m-3}

**What:**
- **The note is correct for the hooks.** The hooks call `~/bin/rmx` from an editable deploy venv, so
  they run the fix from the moment `~/refmatrix` fast-forwards. `rmx daemon restart --relaunch`
  delivers nothing for bug-109, because no daemon or hub code changed.
- **The version cannot tell builds apart.** It stays 0.77.2, so `rmx version -v` and the relaunch's
  version check read the same before and after.
- **One MCP server is missing from the note.** It names `/mcp` reconnect for this project's server,
  but the IntelliJ-hosted server (pid 5555 under 4405) also imports the main tree and needs that
  client's own restart.

**Fix:**
- Verify the deploy by observation: `git -C ~/refmatrix rev-parse HEAD` equals the merge sha, and a
  `stm/by-pid/<claude_pid>.json` appears in this project's store after the next prompt.
- After the main-tree merge and the reconnect, `rmx_focus_note` should return
  `session_source: pointer` (already in the note).
- Name the IntelliJ server in the note.

## Merge / deploy {#merge-deploy}

- **Merge gate (d9af: one more audit, then merge):** holds. There is no BULLSHIT, every r3 BULLSHIT
  and SKETCHY item is closed with evidence, and the remaining items are tests-only or corrupt-input
  hardening.
- **Live hooks:** nothing found that breaks them. Cost is base +1 ms under ordinary load, with 0
  stderr and 0 sink rows on the real chain. 24-way concurrency loses no prompt. The only raise left
  on the hook path needs a corrupted sink over 256 KiB.
- **Deploy note:** correct as far as it goes. Add [[#m-3]]'s verification and the IntelliJ server.
- **Recommended before the merge commit, not blocking:** the [[#s-1]] pins and the [[#m-1]] guards
  (about 25 lines total), plus one full-suite log ([[#m-2]]).

## Verdict {#verdict}

DIRTY — 4 findings (0 BULLSHIT, 1 SKETCHY, 3 MEH). No merge blocker. Safe to merge and deploy: yes.

rel: contradicts -> [[claude#no-silent-failures]]
rel: evidence-for -> [[task-19.0-stm-cluster-hygiene]]
rel: evidence-for -> [[task-21.1-context-usage-telemetry]]
