---
gmd: "0.1"
id: agent-brief-green-251
title: "Brief: green-251 — task 25.1 GREEN (ch-implementer)"
tags: [agent-brief, dispatch]
---

# Brief: green-251 — task 25.1 GREEN (ch-implementer) {#root}

You are the implementer for refmatrix task 25.1 (recall hook byte budget). Make the already-RED
tests pass with concrete `src/` code. You write NO tests (separation of duties).

## Where {#where}

- Clone: `/Volumes/littlebig/refmatrix-plan25-1`, branch `task-25.1-recall-hook-byte-budget`,
  tip `45d8abf` (RED done by `red-251`). Work and commit ONLY in this clone. Dev repo
  `/Users/tholley/claude_tools/refmatrix` and the deploy tree `~/refmatrix` are off limits.
- Interpreter: `/Volumes/littlebig/refmatrix-plan25-1/.venv-eval/bin/python` (a symlink to the
  dev venv; untracked — never stage it). If conftest refuses the import path, set
  `PYTHONPATH=/Volumes/littlebig/refmatrix-plan25-1/src` (absolute).

## Read first (in this order) {#read-first-in-this-order}

1. Spec rev 6: `workflow/plans/plan-25-cliquedb-field-report-tasks/task-25.1-recall-hook-byte-budget.md`
   (R1-R11, AC-1..AC-15; R11/AC-15 = SessionStart `compact|clear` entry runs
   `rmx recall-state --max-bytes N`, N = `hook_budget.budget("recall_state")` <= 9,000, as its
   own hook command; `max_bytes` is a `recall_state` VERB parameter; output fitted whole-block;
   no daemon still exits 0; failure is one clean `Error:` line).
2. RED contract: `workflow/implementation_summaries/task-25.1-recall-hook-byte-budget.md`
   (`#red` maps every test to its AC and its HEAD RED line; `#ambiguities` a1-a13).
3. R0 measurement: `workflow/measurements/hook-output-cap-probe.md` — Claude Code caps EACH hook
   command at 10,000 UTF-16 units of trimmed stdout; budget 9,000 B per generated hook command;
   producers sharing one command share its budget.
4. Tests: `tests/test_task25_1_recall_budget.py`, `tests/test_mcp_memory_recall_routing.py`,
   plus whatever else commits `36bfaa7..45d8abf` touched (`git show --stat`).
5. `CLAUDE.md`, `.claude/PROJECT_PROFILE.md`, `workflow/TDD_GOVERNANCE.md`.

## Lead decisions on the RED ambiguities {#lead-decisions-on-the-red-ambiguities}

- **a3** accepted: AC-4 (h) is a guard (RMX_RERANK=0 on both legs), not a RED.
- **a4** accepted: the pack's API reads as the tests read it (`Packed.named` = list of names,
  `Packed.more` = trailer N, `fit_blocks(trailer=<callable of dropped count>)`, query mode
  `dense`, multi-line query collapses newline to space). A row's path is
  `metadata.source_path`, relative to the memdir. The AC-14 "id-only hook lookup" mutation is
  equivalent through `load_hooks` (26.1 aliases path keys to ids): do NOT change `load_hooks`;
  record it in `#green` as a spec finding.
- **a5** AC-5 stays RED until task 26.4 merges (another clone owns it: the bridge storing
  `session/recall-state` for save-states, `IngestStats.mtype_normalised`). Do NOT implement any
  26.4 code. After your GREEN, the only expected failures are AC-5's; name them exactly.
- **a12** AC-15 (e): an unreadable memdir ends in ONE clean `Error:` line (no traceback); the
  missing-daemon case (d) is said in the output and exits 0.
- **a13** after GREEN, run the mutations the spec's AC-14 names, plus AC-4 (i)'s
  "`shared_embedder` before the daemon" mutation, and record killed/survived in `#green`. A
  surviving mutation is a finding for the test engineer, not something you paper over. Also
  produce `workflow/measurements/plan-25-hook-bytes.md` (GMD): per generated hook command, bytes
  on the frozen fixture at HEAD (the numbers are in `workflow/review-output/plan25/25.1-red.log`
  and `#red`) vs after GREEN, against its budget.

## Merge-conflict hygiene (two sibling clones edit nearby code) {#merge-conflict-hygiene-two-sibling-clone}

- bug-212 (clone `refmatrix-bug212`) rewrites `hooks.GIT_HOOK_SCRIPTS`, the git-hook store gate,
  `sync.GitRefError`, `cli._cwd()`, `cli_entry`. Do not touch those.
- 26.4 (clone `refmatrix-plan26-4`) edits the bridge, `IngestStats`, `cli._ingest_gmd_sync`. Do
  not touch those.
- If 25.1 truly needs one of them, stop and say so in your report instead.

## Hard rules {#hard-rules}

- NEVER run a dev-venv `rmx` against the live store, never open `Store()` on a live
  `.refmatrix/`, never touch `~/.refmatrix`, `~/refmatrix`, any fleet repo, or the live memory dir
  `~/.claude/projects/*/memory`. Throwaway stores only, under a SHORT `mkdtemp()` root (macOS
  `sun_path` ~104 bytes). No version bump.
- If the generator change makes the clone's committed `.claude/settings.json` /
  `.claude/rmx-hooks.json` differ from the generated output (`test_repo_hooks_in_sync`),
  regenerate them in the clone by calling the generator from Python with the clone's
  interpreter — not by running `rmx install-hooks` against any live store.
- Every test run captures output: `... 2>&1 | tee workflow/review-output/plan25/<name>.log`.
- All tests in the files you touch run; never `-k`/`--ignore` a failing group away.
- `src/` fully concrete (no stubs); no silent failures on memory paths (no `2>/dev/null`,
  `|| true`, bare `except: pass`); an error that stops an operation fails loudly on the console
  (exit code + stderr), never only in a log.
- Mutations: commit the GREEN first; one mutation at a time; restore each in its OWN command
  (`git checkout -- <file>`); clear `__pycache__` after the batch; a mutation must FAIL a test,
  not hang it; grep the fix after the restore.
- Commit by pathspec only (never `git add -A`; `.venv-eval` is untracked). Never `rm -rf *`.
  Never search the filesystem from `/`; scope any find to the clone.
- Docstrings say WHY and name the incident/date (2026-11-11, plan-25 / bug-164 / bug-181).

## Verify before reporting {#verify-before-reporting}

- The RED files: all pass except AC-5's (named).
- Family run over every test file touching hooks, recall, verbs, MCP, scan-prompt, focus,
  handoff/recall-state, hook_budget; then a wide run (the full suite is ~13 min; known
  pre-existing failures are bug-127/168, bug-168 rewriter x9, bug-170, bug-196 x2 — compare by
  the E line, not the test name).
- GMD lint zero errors on every doc you wrote (`python3 tools/gmd/lint.py <path>`).

## Deliverables {#deliverables}

Commits on the branch: src, then `#green` in the implementation summary (signatures, runs with
counts and log paths, mutation table, the measurement file, flags for the lead). Final report
(text): shas, pass/fail counts per run, mutation results, the expected AC-5 failures by name,
every flag or spec finding, and anything you could not do and why.

## Amendment 1 (sent after dispatch, 2026-11-11) {#amendment-1-sent-after-dispatch-2026-11-}

After GREEN also run red-251's AC-15 mutation map (each must be killed by the named test):
entry chained into another hook command or matcher drops `compact` → test_ac15a; output not
fitted or `--max-bytes` not passed → test_ac15b + test_ac15c; traceback instead of one `Error:`
line → test_ac15e; `max_bytes` missing from the recall_state verb schema → test_ac15f. Also
measure whether a bare `rmx recall-state` on an unreadable memdir (throwaway store) fails cleanly
with the GREEN code (red-251 a12). Record all in the #green mutation table.

## Amendment 2 (sent after dispatch, 2026-11-11, after the interim report) {#amendment-2-sent-after-dispatch-2026-11-}

The user paused the pipeline after the current agents; red-251 is NOT briefed on the six interim
failures. Do not change tests. In `#green`, list the six non-AC-5 failures (ac9 multiline trailer,
ac4f doc-in-top-8, ac6 include-subjects x2, ac9 session-start bodies, ac10 delivered events) as
"for the lead to judge", each with its measured numbers. Measure #3/#4 (the daemon's default
rerank buries all 5 subjects at ranks 32-36 — may mean AC-6's opt-in never shows a subject in
production) and #2 (no doc reaches the top 8) as possible PRODUCT findings; say which rerank
setting each leg ran with.
