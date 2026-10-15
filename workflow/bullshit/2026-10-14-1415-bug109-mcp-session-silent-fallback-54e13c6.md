---
gmd: "0.1"
id: bsd-bug109-mcp-session-54e13c6
title: "ch-bsd audit — bug-109 MCP session pointer (06ecd0f) + conftest tree guard (54e13c6)"
severity: BULLSHIT
plan: bug-109
task: d9s
tags: [bsd, audit, bug-109, stm, mcp, session, silent-failure]
---

# ch-bsd findings — fix(stm,mcp): resolve the MCP session through a per-Claude-process pointer (bug-109) {#root}

**Commit range:** a434f51..54e13c6 (06ecd0f = the fix; 54e13c6 = conftest guard)
**Date:** 2026-10-14 (written 2026-10-14T14:15:01-0700)
**Author:** Todd Holley / Opus 5.5 / orchestrator
**Files changed:** 6 (cli.py, mcp.py, stm.py, verbs.py, tests/conftest.py, tests/test_mcp_session_pointer.py)
**Tree:** isolated clone `/Volumes/littlebig/refmatrix-bug109`, branch `bug-109-mcp-session`, HEAD 54e13c6.
Nothing in src/ or tests/ was edited. No live store or socket was touched. Live evidence came from
read-only `ps` sampling only.

## Wiring verdict {#wiring}

The fix is live in production on this workstation's happy path. The new code is reached, and the
pointer is written and read.

- **Hooks see `$CLAUDE_PID`.** I sampled live hook processes read-only and logged them to
  `workflow/review-output/bug109-bsd-hook-env-sample.log`. Both the `/bin/sh -c "... rmx focus hook
  --event tool-pre|tool ..."` wrapper and its Python child carry `CLAUDE_PID=59363` and the current
  `CLAUDE_CODE_SESSION_ID`. The chain is `python → /bin/sh → claude(59363)`, so the ancestor walk
  would also find `claude` in two hops. UserPromptSubmit runs through the same hook runner.
  `claude` itself and every `rmx mcp` server have no `CLAUDE_PID` in their env (10 claude and 5 mcp
  pids surveyed). Claude Code therefore sets the variable per child.
- **The MCP server's owner is found.** In production its ppid is `claude`. Probe A in
  `bug109-bsd-probe2.log` (a sh copy named `claude`, no env) resolves the pointer: `sess-B`, not
  the newest ring `sess-C`.
- **Subagents.** Subagents share the parent's Claude process and session id. Their tool hooks carry
  the parent's `CLAUDE_CODE_SESSION_ID`, and their tool events land in the parent ring
  (`742dab0d….jsonl`). UserPromptSubmit does not fire for a subagent's prompt: this audit's prompt
  has no input event in the ring. A subagent hand-back fires the parent's input hook with the same
  session id, so the write short-circuits and nothing is re-pointed.
- **The Stop/PreCompact `focus summarize --promote`** goes through `_resolve_stm_session(prefer_latest=True)`.
  It now resolves through the pointer, which fixes the same bug for the digest write.
- **Nobody exports `$RMX_SESSION`.** A search of src/, .claude/ and scripts/ found no exporter, so
  the CLI order (env before pointer) leaves no stale path in practice. It is a manual override only.
- **Tests:** 248 passed across 17 targeted files (`bug109-bsd-targeted.log`). The full suite was
  not run because it reaches live sockets (memory: project_suite_reaches_live_sockets).

## Findings {#findings}

### BULLSHIT: every pointer failure falls back silently to the newest ring, and the "loud" claim is dead on arrival {#b-1}

**File:** `src/refmatrix/cli.py:1972-1981` (input hook), `src/refmatrix/hooks.py:146` (generated
`rmx focus hook --event input 2>/dev/null || true`), `src/refmatrix/verbs.py:524-548`
(`resolve_session`), `src/refmatrix/stm.py:127-138,169-199`.

**What:** The hook comment says "Loud on failure: the hook's stderr is the only place it can go".
The resolver then falls through pointer → `$RMX_SESSION` → `latest_session` → `default` and does
not report which source it used.

**Why it's bullshit:**
1. The generated hook sends that stderr to `/dev/null || true`, so the "loud" line reaches nobody.
2. The `owner is None` branch prints nothing even before the redirect.
3. `_proc_start` returning None (ps failure or timeout) stores `pid_start: null`. After that,
   `read_pid_pointer` returns None for that pid forever, and nothing says so.
4. When the pointer does not resolve, the long-lived MCP server falls to the newest ring. That is
   bug-109's exact misroute, on `rmx_focus_note` / `rmx_save_state` / `rmx_task`, with no signal.

So bug-109 is closed on the happy path and kept alive, silently, on every failure path. This is a
memory-critical path under CLAUDE.md #no-silent-failures, and the diff adds a new failure surface
whose only reporting channel is the one the installed hook discards.

**Evidence:** Probe D in `workflow/review-output/bug109-bsd-probe2.log`: a `node`-named parent and
no `claude` within 4 hops give `owner None` → `resolved sess-C` (the other session's newest ring),
`stderr: ''`.

**Fix (small):**
- Record pointer failures (no owner, ps failure, write OSError) to a counted on-disk sink that
  survives the hook's redirect, e.g. a `cli.log` fact row or `stm/by-pid/_errors.jsonl`.
- Have `resolve_session` return or record its source, so write verbs can label results
  `session_source: newest-ring`.
- 19.0 R5 is the scheduled end state for the fallback itself: `SessionUnresolved` on write verbs.
  Until it lands, the fallback must at least be visible.

**Pattern match:** YES. See feedback_no_silent_failures and the 0.66.1 bridge audit (bsd-0661 #bs-1):
the same silent skip on a memory path.

rel: contradicts -> [[claude#no-silent-failures]]

### SKETCHY: owner resolution trusts an inherited `$CLAUDE_PID` and a comm-name match, not the spec's `os.getppid()` {#s-1}

**File:** `src/refmatrix/stm.py:144-166` (`owner_claude_pid`).

**What:** `$CLAUDE_PID` wins outright. Otherwise the walk climbs up to 4 ancestors looking for a
`comm` basename of `claude`. task-19.0 R5, which d9s says this ships a subset of, specifies "the
long-lived `rmx mcp` goes pid pointer for `os.getppid()`".

**Why:** Two shapes resolve to the wrong Claude process's pointer, which is a cross-session write
(bug-109's shape) or a silent fallback ([[#b-1]]):
- **(a) Inherited env.** A Claude launched from a Bash tool (the screen-pair pattern) inherits the
  outer `CLAUDE_PID`, and so does the MCP server it spawns. Probe C: the real parent is
  `claude`-named, but owner = 59363 (outer) → `sess-OUTER`.
- **(b) npm/node installs.** There `comm` is `node`. The walk skips the real parent and either finds
  an unrelated outer `claude` (probe B → `sess-OUTER`) or returns None (probe D → newest ring).

Both are unobserved on this workstation today: no running claude carries `CLAUDE_PID`, and all
are native `claude`. refmatrix is public, though.

**Fix:**
- When `_LONG_LIVED`, use `os.getppid()` per the spec.
- For per-call processes, accept `$CLAUDE_PID` only if it is an actual ancestor; otherwise take the
  nearest `claude` ancestor.
- Count the no-owner case under [[#b-1]].

**Pattern match:** NO.

rel: contradicts -> [[task-19.0-stm-cluster-hygiene]]

### SKETCHY: one of the "10 RED at a434f51" tests passes on unfixed code and enshrines the misroute {#s-2}

**File:** `tests/test_mcp_session_pointer.py:84-88` (`test_mcp_with_no_pointer_never_uses_its_frozen_env`).

**What:** It asserts `resolve_session(...) != "sess-A"`. Base code never read
`CLAUDE_CODE_SESSION_ID`, so the test passes at a434f51: the base resolves to `sess-C`
(`workflow/review-output/bug109-bsd-vacuous-at-base.log`). The commit message's "10, RED at
a434f51" is therefore false (9 at most). Its only passing value is `sess-C`, which the test's own
fixture describes as another session's ring, so it blesses the misroute as correct.

**Fix:**
- Assert the no-pointer behaviour you actually want: a labelled/counted fallback ([[#b-1]]) or,
  after 19.0 R5, `SessionUnresolved`.
- Correct the RED count in the summary/registry row.
- No test covers the no-owner or ps-failure paths.

**Pattern match:** YES. A "RED test that passes at HEAD" is recorded in memory
feedback_red_test_must_fail_at_head.

### SKETCHY: `focus promote-edges --apply` writes the durable graph from the newest ring, resolved inside the daemon {#s-3}

**File:** `src/refmatrix/promote.py:161` (`session = session or latest_session(root)`),
`src/refmatrix/cli.py:1491-1498` (passes `session` only when `--session` is given), daemon op
`promote_edges` (`daemon.py:5827`, registered at 6269).

**What:** The session is resolved in the daemon process. The daemon has no `$CLAUDE_PID` and no
`claude` ancestor (launchd), so the pointer can never help there. With two sessions active, the
`--apply` run promotes the other session's co-occurrence pairs into durable `co-occurs` edges.

**Scope:** Outside bug-109's letter (the MCP verbs), but the same defect on a durable write. It is
not enumerated in 19.0 R5's site list (scan.py, verbs, cli `_resolve_stm_session`, focus hook), so
it is unanchored.

**Fix (one line):** In the CLI, pass `session=_resolve_stm_session(session, prefer_latest=True)`
to the op. Also enumerate the site in 19.0 R5, or file a bug row.

**Pattern match:** YES. Same family as bug-100 / bug-109.

### MEH: composite.py:103 and its swallowing caller pick the newest ring for scan-prompt injection {#m-1}

**File:** `src/refmatrix/composite.py:103` (`session or latest_session(root)`),
`src/refmatrix/scan.py:887-893` (`except Exception: comp = ""`). The sibling STM seed is at
`scan.py:535-537`.

**What:** A read/injection path, not a write. With two sessions, this session's prompt can carry
the other session's topic composite, and any composite error vanishes. It is out of bug-109's
scope. scan.py:535 is enumerated in 19.0 R5. composite.py is covered only by R5's umbrella clause
("every resolver of 'this session' used by STM") and is not listed. Add it to the list, and count
the swallowed exception there.

### MEH: helix.py:96 uses the newest ring, and its docstring claims "the hook exports RMX_SESSION" {#m-2}

**File:** `src/refmatrix/helix.py:84-98` (`_current_session`), used by `annotate` at helix.py:323.

**What:** Nothing exports `RMX_SESSION` (search above), so this is always `latest_session`. With two
sessions, the wrong ring is excluded from `last_touch`, which is the phase-1 confound returning.
It is a read/annotation path, out of scope, and not enumerated in R5. List it and fix the
docstring.

### MEH: CLI `focus record` and `focus clear` bypass the resolver entirely {#m-3}

**File:** `src/refmatrix/cli.py:1093`, `cli.py:1624` (`_stm()` with `prefer_latest=False`).

**What:** From a Bash tool these write to, or clear, the `default` ring, not the session's. `focus
clear` ("for this session") is a no-op for the real session. This is pre-existing and does not
misroute into another session. The pointer would fix it for free.

### MEH: deferred sub-parts of R5 that this subset leaves {#m-4}

- **No SessionStart pointer write** (R5 specifies `startup|resume|clear|compact`). After `/clear`,
  the SessionStart `focus context` resolves through the pointer to the pre-clear session until the
  first prompt. This is anchored to 19.0 R5.
- **Store-root mismatch.** The hook resolves its root from its cwd and the MCP server from its spawn
  cwd. If the session's cwd moves into another tree with a `.refmatrix`, the pointer lands in that
  store and the MCP root's pointer goes stale.
- **No cleanup of `stm/by-pid/`.** One file per Claude pid accumulates.
- **Cost.** The read side spawns `ps` on every resolve: `lstart`, plus one walk `ps` in the MCP
  server. That measured 2.5–12 ms per call (`bug109-bsd-probe.log`). The hook's unchanged-write
  path is 0.02 ms with no `ps`. Acceptable, but the commit's "no ps call" is true only for the
  hook write.

### MEH: no bug_registry row and no implementation summary for bug-109 on the branch {#m-5}

`workflow/bug_registry.md` has 0 mentions of bug-109, and `workflow/implementation_summaries/` has
none either. Both are mandatory before merge (CLAUDE.md #task-completion-workflow).

## Conftest guard (54e13c6) {#conftest-guard}

The guard is correct.
- **Without PYTHONPATH in the clone** it refuses: `pytest.UsageError` naming both paths, exit 4
  (`bug109-bsd-guard-noPYTHONPATH.log`).
- **With PYTHONPATH prepended** it passes.
- **In the dev tree**, the `.venv-eval` editable install resolves to `<dev>/src/refmatrix`, so it
  passes with no env.
- **Worktrees and clones** must prepend `src`.
- **`tests/test_brief_real_daemon.py`** is unaffected. Its subprocesses inherit `os.environ`, which
  includes PYTHONPATH. In a clone it is skipped because `RMX` points at `<clone>/.venv-eval/bin/rmx`,
  which does not exist. That skip predates the guard.
- **Limit:** the guard checks only the pytest process, not subprocess children that build a
  scrubbed env.

## Deploy note {#deploy-note}

The pointer is written by the DEPLOYED `rmx` (the hook) and read by the MCP server. That server is
`.venv-eval/bin/rmx` on this workstation and is only reloaded on `/mcp` reconnect. Until both
happen, the old newest-ring behaviour remains, and per [[#b-1]] nothing shows it.

## Verdict {#verdict}

DIRTY — 9 findings (1 BULLSHIT, 3 SKETCHY, 5 MEH). Merge-blocking: [[#b-1]].

rel: contradicts -> [[claude#no-silent-failures]]
rel: evidence-for -> [[task-19.0-stm-cluster-hygiene]]
