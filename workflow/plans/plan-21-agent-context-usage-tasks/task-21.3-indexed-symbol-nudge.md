---
gmd: "0.1"
id: task-21.3-indexed-symbol-nudge
title: "Task 21.3: a PostToolUse nudge — when the agent greps an indexed identifier, one line says what rmx context knows"
tags: [task, hooks, context, agent, nudge]
metadata:
  node_type: task
  status: pending
  created: 2026-10-07
  updated: 2026-10-15
---

# Task 21.3: the indexed-symbol nudge {#root}

> Plan: [plan-21-agent-context-usage](../plan-21-agent-context-usage.md)
> Status: Pending (revision after the 2026-10-14 decision log)
> Wave: 3
> Depends on: 16.1 (the argv parser the trigger uses), 16.2 (the invisible shim removes the old
> stderr provenance hint), 21.1 (`session`, the `nudge` channel, the `--by-session` report), 21.2
> (TESTED BY and the `--brief` answer the nudge points at), 23.0 (sandbox)

rel: part-of -> [[plan-21-agent-context-usage]]
rel: derives-from -> [[exploration-agent-context-usage]]
rel: derives-from -> [[bsd-plan21-spec-review-3104a81]]
rel: derives-from -> [[plan-review-2026-10-14]]
rel: depends-on -> [[feedback_grep_is_observed_not_answered]]
rel: depends-on -> [[feedback_go_no_go_ranges_not_predrop]]
rel: depends-on -> [[task-16.1-argv-faithful-learner]]
rel: depends-on -> [[task-21.1-context-usage-telemetry]]
rel: depends-on -> [[task-21.2-precise-identifier-context]]

## Why {#why}

Once grep is passive, the agent's only cue that the index knew something is gone. The user
approved a nudge (2026-10-07): one line, in the turn where it would help, instead of a rule the
agent has to remember. A habit memory was rejected (d4e). It must NOT touch grep's output. Grep is
observed, not answered (the plan-16 rule), so the nudge is separate context added by a PostToolUse
hook.

The latency budget (the exploration's d-3) was never decided, and the replica cost of these same
identifiers measured 330–949 ms (bsd #s-13). d4d: the budget is decided by MEASUREMENT when this
task starts, against bands written before the run; the nudge is not dropped in advance. {#why-body}

## Requirements {#requirements}

1. **R0 Measure first, then pick the band** (d4d). Before any nudge code, a timing harness runs
   the GENERATED hook command (interpreter start included: the clock is the hook's WALL time, as
   Claude Code waits on it) with a recorded PostToolUse envelope on stdin, over the real
   identifier set: 21.2's [[task-21.2-precise-identifier-context#frozen-set]] plus every
   identifier-shaped grep pattern (R1's regex) of `kind=grep` rows in the LOCAL raw project
   `.refmatrix/query.log` up to `2026-10-07T11:06:35` (AC-6's cut). 21.1's committed fixture
   cannot supply them: its bodies are sha256-replaced (re-review #s-7). Per d8f the extracted
   list stays local (gitignored, beside `REPORT.md`); committed are its count and the sha256 of
   the sorted, newline-joined list, so a holder of the raw log can rebuild it byte-identically.
   It runs on a sandboxed catalog copy:
   - **quiet:** no other `rmx` work running;
   - **loaded:** while the copy's daemon re-syncs this tree's largest source file and 4 `rmx
     context` calls run concurrently.

   It records p50/p95 for both. The verdict uses the WORSE p95 of the two, against this table,
   verbatim from [[plan-review-2026-10-14#t4-nudge-ranges]] with the close-out amendment to the last
   band:

   | p95 | verdict |
   |---|---|
   | ≤ 100 ms | GO: fire inline on every eligible call |
   | 100–300 ms | GO, gated: at most once per symbol per session; report the per-prompt cost |
   | 300 ms–1 s | NOT YET: build a precomputed indexed-symbol set (written at SessionStart / on derive), so the hook check is a set lookup; re-measure, then apply this table again. Annotation: the d4d amendment and R6 make the DAEMON, on derive, the only writer; SessionStart may only request a rebuild (re-review #m-6) |
   | > 1 s after that | NO-GO in the hook. Revisited only if 21.3 is re-planned (amendment: no longer "after d2e") |

   The measured numbers and the verdict are committed to `REPORT.md` before the first nudge commit.
   In NO band does the hook build a full context bundle: the lookup is index-only (the `defines`
   row + CALLED BY / TESTED BY counts), never `build_context`.
2. **R1 Trigger, with a parser contract for three inputs** (bsd #m-6). The hook fires when the
   searched pattern is identifier-shaped: a single token matching `^[A-Za-z_][A-Za-z0-9_.:]*$`,
   optionally with `def ` / `class ` / `(` around it. The pattern is extracted:
   - from a PostToolUse(Bash) command as the agent wrote it (`grep …`, `rg …`), by 16.1's argv
     parser;
   - from a PostToolUse(Bash) command after `grep-rewrite-guard` rewrote it (`rmx grep …`), by the
     same parser;
   - from a PostToolUse(Grep) envelope's `tool_input.pattern` field directly (the Grep tool has no
     argv).

   Never a regex over the raw command line.
3. **R2 Content.** One line:
   `rmx: <symbol> is indexed — defined <path:line>; <n> callers, <m> tests (rmx context <symbol> --brief)`.
   `<m>` counts TESTED BY members by 21.2 R3's `is_test_entity`; `<n>` counts the rest of CALLED BY.
   It is emitted ONLY when the symbol resolves to a definition with `n + m ≥ 1`, which gates out
   the noise.
4. **R3 Budget and accounting.**
   - ≤ 1 nudge per symbol per session and ≤ 10 per session, where the session is the PostToolUse
     envelope's `session_id` (never `stm.latest_session`). The dedupe state is one append-only file
     per session under `.refmatrix/nudge/`, written only by the hook.
   - A hard deadline on the lookup, set from R0's band (the band's upper edge). Past it, the hook
     is silent. If the lookup is a daemon read, the hook passes that deadline as `daemon.call`'s
     `timeout` with `retries=0`, so the daemon's bug-116 deadline drop (0.78.2) discards the
     queued read too and a late answer never runs on a busy worker (round-8 #nm-5).
   - Every invocation writes one `query.log` row `kind=nudge` with `outcome` ∈ `fired`, `dedup`,
     `gated` (no callers/tests), `not_identifier`, `not_indexed`, `skipped_budget` (the deadline
     expired; the ONE budget-skip value of `telemetry.CALL_OUTCOMES`, 21.1 R4, renamed from this
     task's round-6 `timeout` so 21.1's report and 19.5 read one vocabulary), `disabled` (R4),
     `stale_set` (R6), and the 21.1 fields.
     A fired nudge also appends one `delivered` event to `recall-events.jsonl` with
     `channel=nudge`. Timeouts are counted on the row, never printed.
5. **R4 Off switch.** `RMX_CONTEXT_NUDGE=0`, respected by the generated hook (outcome `disabled` on
   the row), and shown in `rmx learn status` (`cli.py:7292`) as `context nudge: on|off` (bsd #m-3:
   there is no `rmx hooks status`).
6. **R5 Generated, batched.** The hook is GENERATED by `hooks.py` (never hand-authored), and
   `rmx install-hooks --check` covers it. Its deploy rides the C11 window shared with 16.2/16.3
   (bsd #m-5); it opens no regeneration window of its own.
7. **R6 The precomputed indexed-symbol set — only if R0 lands in 300 ms–1 s** (d4d amendment;
   decision-log #s-9).
   - **ONE writer: the daemon, on derive.** SessionStart may only REQUEST a rebuild through a
     daemon op; the hook only reads.
   - **Atomic replace:** written to a temp file in the same directory, then `os.replace`.
   - **Version stamp:** the file carries a schema version and the derive stamp it was built from;
     the hook checks the schema version and treats a mismatch as `not_indexed` with an
     `outcome=stale_set` row (counted, not silent).
   - **Staleness rule, stated:** between derives, a symbol defined after the last derive is not
     nudged (a false negative, the safe direction); a symbol removed since still resolves against
     the set and is checked against the replica row before printing.

## Acceptance criteria {#acceptance}

Every AC runs in 23.0's sandbox and asserts the live `query.log` / `recall-events.jsonl` line
counts are unchanged.

1. **R0 before code.** `REPORT.md` with quiet and loaded p50/p95 and the band verdict is committed
   before the first commit touching `src/refmatrix/nudge.py` (commit order checked). If the verdict
   is NO-GO, the task closes with the report and no hook ships.
2. **Fires once.** `grep -n "_op_context" src/refmatrix/daemon.py`, run through the GENERATED
   PostToolUse(Bash) hook command with a recorded envelope, yields one nudge line naming
   `daemon.py:<line of def>`, one `outcome=fired` row and one `channel=nudge` `delivered` event. A
   second identical grep in the same `session_id` yields none (`outcome=dedup`); the same grep under
   a different `session_id` fires again.
3. **All three inputs.** The rewritten form `rmx grep -n _op_context src/refmatrix/daemon.py` and a
   PostToolUse(Grep) envelope with `pattern: "_op_context"` each fire exactly as AC-2.
4. **Silent where it should be.** `grep -rn "error|warn" .` (not identifier-shaped), a grep for an
   unindexed token, and a symbol with no callers or tests yield no line, with outcomes
   `not_identifier`, `not_indexed`, `gated`.
5. **Deadline.** With the lookup artificially delayed past the deadline (a `sitecustomize.py` the test
   puts on the hook subprocess's `PYTHONPATH` wraps the lookup with a sleep; no `src/` flag), the hook prints nothing and writes `outcome=skipped_budget`.
6. **Usage before/after.** `rmx telemetry --agent-usage --by-session` over ≥ 3 sessions before and
   ≥ 3 after the deploy reports `invocation=agent` context calls per session (21.1 R2/R7), split by
   whether a `nudge` event preceded them in the session. The table and the verdict (rise or not)
   are in the implementation summary; a session with null `session` fails the report.
7. **R6, conditional:** only if R0 lands in 300 ms–1 s: a derive on the copy rewrites the set
   atomically (a reader polling during the rewrite never sees a partial file); the hook never
   writes it (a test asserts the hook process opens it read-only); a bumped schema version yields
   `outcome=stale_set`; and the re-measured p95 is recorded and the table re-applied.
8. **Mutations that must FAIL a test** (pre-registered):
   - the per-session dedupe removed (AC-2);
   - the session taken from `latest_session` (AC-2: the second session does not fire);
   - the callers/tests gate removed (AC-4);
   - the Grep-tool input path removed (AC-3);
   - the nudge written into the tool output instead of the hook context (AC-2 asserts grep's
     stdout is byte-identical with and without the hook);
   - `build_context` called from the hook (a test asserts it is never imported by `nudge.py`);
   - (R6 band only) the hook writing the set (AC-7);
   - the `channel=nudge` `delivered` append removed from `nudge.py` (AC-2: no event), the nudge
     leg of 21.1's per-channel emitter mutations ([[task-21.1-context-usage-telemetry#acceptance]]
     AC-8c, round-3 #b-3).

## Files to modify {#files-to-modify}

| file | change |
|---|---|
| `src/refmatrix/hooks.py` | the generated PostToolUse(Bash) and PostToolUse(Grep) entries |
| `src/refmatrix/nudge.py` (new) | the parse (16.1's parser; the Grep envelope field), the index-only lookup, the per-session dedupe file, the `query.log` row and the `nudge` event |
| `src/refmatrix/cli.py` | `rmx learn status` shows the switch |
| `src/refmatrix/daemon.py` | (R6 band only) the set writer on derive and the rebuild-request op |
| `eval/production/nudge_latency/` (new) | R0's harness and `REPORT.md` |

## Test strategy {#test-strategy}

- **Sandbox:** 23.0's sandbox for every test; the hook subprocesses get `HOME` = tmp,
  `REFMATRIX_ROOT` = tmp, `RMX_HUB_MODELS=0`, and run from a cwd inside the tmp tree so the
  hook's walk-up never resolves the live `.refmatrix` (bsd #s-7).
- **RED:** the generator test asserts the PostToolUse entries exist; the hook command, run with a
  recorded PostToolUse envelope on stdin against a fixture store, prints the expected line. Both
  fail at HEAD.
- **Generator, not runtime:** every hook AC runs the command `hooks.py` generates, never the
  installed `.claude/settings` copy.

## Revision (2026-10-14 decision log) {#rev-2026-10-14}

| finding or decision | answered at |
|---|---|
| bsd #s-13 / d4d (latency undecided; which clock) | R0 (wall clock, quiet + loaded, band table); AC-1 |
| d4d close-out amendment (last band; one owner) | R0 table; R6 |
| decision-log #b-6 (d4d's last band anchored on d2e) | R0 table, last row |
| decision-log #s-9 (set with two writers, no staleness rule) | R6; AC-7 |
| bsd #s-11 (tests undefined; gate depends on it) | R2 (21.2 R3's `is_test_entity`) |
| bsd #b-1 (no session for AC-4) | R3; AC-6 (21.1's `session`) |
| bsd #s-7 / d1a, d1b (hook walks up to the live store) | [[#test-strategy]] |
| bsd #m-3 (`rmx hooks status` does not exist) | R4 |
| bsd #m-5 (C11) | R5 |
| bsd #m-6 (parser for three inputs; 16.1 undeclared) | R1; header; AC-3 |
| d4e (no habit memory) | [[#why]] |
| decision-log #m-2 (adoption by channel, not invocation) | AC-6 |

## Revision round 2 (2026-10-14) {#rev-round-2}

Answers [[bsd-plan19-21-spec-rereview-32dde06]].

| finding / decision | answered at |
|---|---|
| re-review #s-7 (R0's identifiers drawn from a hashed fixture) | R0 (local raw project log, count + sha256 committed, d8f) |
| re-review #m-6 (band row 3 "written at SessionStart / on derive") | R0 table row 3 annotation; R6 |

## Revision round 3 (2026-10-14) {#rev-round-3}

Answers [[bsd-plan19-21-spec-rereview-r3-6091648]].

| finding / decision | answered at |
|---|---|
| round-3 #b-3 (the nudge emitter's removal mutation, one of 21.1's seven channels) | [[#acceptance]] AC-8 mutation list (the `channel=nudge` append removed, caught by AC-2) |

## Revision round 8 (2026-10-15) {#rev-round-8}

Answers [[bsd-plan19-21-spec-rereview-r8-23ad703]] #nm-5's 21.3 clause (marked optional there,
applied) and the user's rule to converge repeated shapes: a budgeted call's skip has ONE outcome
value across 21.1's recall / context rows and this nudge row. Code fact read at HEAD `23ad703`:
`daemon.call` sends `deadline_s` = its `timeout` (`daemon.py:644-645`) and the daemon drops a
queued read past it (`_note_expired_read`, `:1362`).

rel: derives-from -> [[bsd-plan19-21-spec-rereview-r8-23ad703]]
rel: depends-on -> [[task-21.1-context-usage-telemetry]]

| finding / decision | answered at |
|---|---|
| round-8 #nm-5 (21.3 clause: a daemon lookup should carry the hook's deadline) | R3 (deadline passed as `timeout` with `retries=0` when the lookup is a daemon read) |
| user rule: one outcome vocabulary | R3 (`timeout` renamed `skipped_budget`, from `telemetry.CALL_OUTCOMES`, 21.1 R4); AC-5 (`outcome=skipped_budget`) |
