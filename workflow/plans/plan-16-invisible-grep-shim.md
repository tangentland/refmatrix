---
gmd: "0.1"
id: plan-16-invisible-grep-shim
title: "Invisible grep shim: the real tool always answers, the graph learns in the background"
tags: [plan, grep, hooks, learning, drop-in]
metadata:
  node_type: plan
  status: drafting
  created: 2026-10-06
  revised: 2026-10-14
  updated: 2026-10-15
---

# Plan 16: the grep shim stops answering and only watches {#root}

**Date:** 2026-10-06
**Status:** Drafting (revision round 9, 2026-10-15: 16.6 deletes the uncalled incremental replay
path and every spec clause that extended it (d9bu; the rebuild is the one replay path), AC-9d's
checks are scoped, and 16.3 R5 lands over bug-118's one hook renderer, for the r9 diff check
`bsd-plan16-22-spec-diffcheck-r9-29e335a`, [[#rev-round-9]]; revision round 8, 2026-10-15: today's `learn.off` operator state is
stated and owned (d9bj: 16.3 retires `enforce-rmx-grep.sh`'s redirect, `learn.off` comes off only
after 16.2 and 16.3 deploy together, 16.4's window opens after that flip), and 16.6's row events
carry `c_kind` through one builder, key, resolver and counter (d9bl), for the r8 re-review
`bsd-plan16-22-spec-rereview-r8-23ad703`, [[#rev-round-8]]; revision round 7, 2026-10-15: 16.6 R1d's one row pass replays `evidence`
appends and row ops together in timestamp order (d9av, lockstep with 22.2 R3) and 16.6 R1c is
retired (d9ay), for the r7 re-review `bsd-plan16-22-spec-rereview-r7-331b414`, which made plan-16
approvable together with that R1d edit, [[#rev-round-7]]; revision round 6, 2026-10-15: 16.6 R7 names the `dangling-link` census and
cites code by symbol, for the r6 re-review `bsd-plan16-22-spec-rereview-r6-0e77da3`, which found
plan-16 APPROVABLE, [[#rev-round-6]]; revision round 5, 2026-10-14: 16.1 and 16.6 revised for the r4 re-review
`bsd-plan16-22-spec-rereview-r4-878647c` and d9ab, [[#rev-round-5]]; revision round 3 revised
16.1 and 16.6 for the r3 re-review
`bsd-plan16-22-spec-rereview-r3-6091648`, [[#rev-round-3]]; round 2 revised 16.2 and 16.6 for
`bsd-plan16-22-spec-rereview-32dde06`, [[#rev-round-2]]). Task specs revision 6
(2026-10-14) answers spec review r5 `bsd-plan16-spec-review-r5-cd7c923` (NEEDS-REVISION: 2
BULLSHIT, 6 SKETCHY, 7 MEH, plus r4's partials) and every 2026-10-14 decision that touches plan-16
(d6d, d7a, #t6-fixes, #t7-fixes, #t8-amendments; [[#revision-6]]). Both former decisions-needed are
settled ([[#decisions-needed]]). 16.6 is split by dependency: its Wave-1 slice runs after plan-23's
23.1; 16.1-16.5 are Wave 2 ([[#waves]]). The precision gate is KEPT by user decision, scored on
complete outputs with a minimum n and a forward-collected oracle. Awaiting spec review r6 before
`approved`. No plan-16 code yet, except the `-f/--flags` removal (`d559567`, d-4), which landed
ahead of 16.5. `bsd-r1-remedy` has merged to `master`.

rel: depends-on -> [[plan-15-derive-impact-tracking]]
rel: derives-from -> [[plan-14-grep-learning-measurement]]
rel: derives-from -> [[bsd-r1-remedy-r3-bb5b97f]]
rel: amends -> [[feedback_rmxgrep_no_plain_escape]]
rel: related-to -> [[project_grep_surface_defect_family]]
rel: amends -> [[bsd-plan16-spec-review-r4-33809ab]]
rel: related-to -> [[plan-review-2026-10-07]]
rel: amends -> [[bsd-plan16-spec-review-r5-cd7c923]]
rel: derives-from -> [[plan-review-2026-10-14]]
rel: depends-on -> [[plan-23-bounded-write-harness]]
rel: depends-on -> [[task-23.0-test-sandbox]]
rel: amends -> [[bsd-plan16-22-spec-rereview-r3-6091648]]

## Why {#why}

Today every bare `grep`/`rg` an agent runs through the Bash tool is rewritten to `rmxgrep`/`rmxrg`
by the PreToolUse hook, and the agent shell exports `RMXGREP_MODE=rich`. In rich mode the shim
calls `rmx grep`, which answers from the index when no path is named and from its own rendering of
the `rg` floor when one is. So rmx stands in for grep on every agent search. {#today}

**The operator state since 2026-10-15 (r8 s-2).** That paragraph describes the shipped design, not
what runs today. The user's instruction of 2026-10-15 ("block the grep rewrite until the passive
version exists") set the GLOBAL learn switch off: `~/.refmatrix/learn.off` exists (written 00:29;
this repo's `.refmatrix/learn.off` does not). With it set, `learn_switch.decision()` returns
`global-marker`, and every route stands down: route 1's rewrite (`grep-rewrite-guard.sh`) and the
Grep-tool teach hook exit early (`search_hooks.py`, "The learn switch, both scopes"); route 2's
shims take their learning-off exit to the real tool (16.2 R1); the daemon drains nothing; and the
project hook `.claude/hooks/enforce-rmx-grep.sh`, which `hooks._add_enforce_entries` wires as a
PreToolUse(Bash) hook and which REDIRECTS every corpus grep to `rmx grep`, stands down only
because of the same marker (`0611d2f`). Removing the marker today would re-arm that redirect,
the cli-pool load bug-115 removed and the opposite of [[#d-1]]. So the switch stays off until the
passive shim and the redirect's retirement ship together (d9bj, [[#waves]]). {#today-learn-off}

Standing in has been the single largest source of defects in this project. Each item below gave a
wrong grep answer to every script and agent on the machine:

- bug-058, 059, 060, 062, 063, 064 and 066, bug-073 and bug-074 (the drop-in family; bug-061 and
  bug-065 are NOT drop-in bugs, per task 16.5 #why);
- ch-bsd r3's four blockers (bug-076 to bug-079);
- the `\b` false negative found on 2026-10-06, where `/usr/bin/grep -c 'self.root\b'` prints 26
  and exits 0 while deployed `rmx grep` prints `0` and exits 1.

Three audit rounds in a row found new drop-in defects in the fixes for the previous ones. {#cost}

The benefit is smaller than the cost. Index answers reach only path-less invocations: plan-14
measured an index share of 18.5% → 31.7%, and that figure is now stale because bug-074 changed
what counts as an index answer. Learning does not need rmx to answer. It needs rmx to SEE the
search, and the shim already does that. {#benefit}

The shim already has an invisible mode. `bin/rmxgrep`'s plain mode, used today only when stdout is
piped and rich mode is off, execs the real tool (byte-exact output, grep's exit codes) and fires a
detached, throttled teach ping. This plan makes that mode the only one, and replaces the ping with a
learner that is faithful to the search. {#already-built}

## Goal {#goal}

1. A rewritten `grep`/`rg` is **byte-identical** to the real tool, on stdout, stderr and the exit
   code, on every invocation. This holds by construction, because the real tool runs; nothing
   renders in its place.
2. Every invocation the shim sees still teaches the graph, from a background re-run in canonical
   `file:line` form, with the same matching rules the caller used.
3. `rmx grep` remains as an explicit command: the index-first exploration read for an agent or a
   human who asks for it by name.

## Design {#design}

**The shim** (`bin/rmxgrep`, `bin/rmxrg`, generated hook config). {#shim}

- Delete the rich branch and `RMXGREP_MODE`. Every path ends in `exec "$REAL" "$@"`.
- The learner starts BEFORE the exec with stdio on `/dev/null`. It detaches itself (`os.setsid()`,
  task 16.1 R0), because `/bin/sh`'s `&` alone leaves it in the caller's process group (measured).
- Unchanged in BOTH wrappers: the outside-a-project branch, the pipe-filter branch (a grep reading a
  pipe teaches nothing), and the learn toggle. `rmxrg` gained the toggle in `321ff97`.
- The throttle stamp is re-keyed on cwd + NUL-joined argv, and every throttled call is counted
  (task 16.2 R3).
- Remove `RMXGREP_MODE: rich` from `~/.claude/settings.json` env and `agent-bashrc.sh`, through the
  generator, never by hand.

**The learner** — `src/refmatrix/grep_learn.py`, reached through the hidden command `rmx grep-learn`.
It is NOT a verb: `verbs.VERBS` is exactly the MCP tool set, and only hooks call the learner.
It re-runs the SAME tool the caller ran, never rmx's floor, so the regex dialect is the caller's
by construction. Hits go through `learn_queue.enqueue`, a file append, so no socket and no daemon
are needed. Full spec: task 16.1. {#learner}

- **It re-runs the caller's OWN binary** (`--bin`) with the caller's MATCHING rules and match
  CUTOFFS, so the dialect is the caller's by construction. Task 16.1 R1's per-tool table is the
  authority, and this summary defers to it:
  - match flags are kept, in short and long forms;
  - cutoffs are honoured: `-m N` is kept, and `-l` is re-run as `-m 1`;
  - shape flags are dropped;
  - teaching nothing: `-v`, `-L`, `-q`, `-f`, more than one `-e`, the decompress flags, and flags
    the tool rejects;
  - canonical `-nH --null` output is appended.
- **It prunes the re-run to the corpus and keeps only corpus hits** (16.1 R1b/R3). BSD `grep -r`
  ignores `.gitignore`. A whole-tree re-run takes 103 s on this repo, and without the corpus filter
  it would teach `.refmatrix/` logs and `.venv-eval/` as protected entities.
- **Paths are absolute** from `realpath(cwd)`, and `kind` follows ingest's `CODE_EXTS`, so a taught
  file is the SAME entity ingest made (16.1 R2/R4).
- **It is bounded on every leg.**
  - At most 200 corpus hits, under a wall-clock cap.
  - An in-flight cap of 2 per store, which the shim checks BEFORE spawning.
  - Store-side, a fully known re-teach writes nothing, not even to `facts.log`.
  - Every call appends one record to `<store_root>/grep-learn.log`, and the learner opens no
    `Store`.
- **The dedicated Grep tool uses it too.** `grep-tool-teach.sh` (PostToolUse(Grep)) calls the same
  learner, so all three surfaces learn from one implementation. Each spawner names itself
  (`--spawned-by shim | grep-tool-hook | rmx-grep`, 16.1 R6), so 16.4 attributes records by route.
- **It writes provenance at learn time** (16.1 R10, moved from 16.6 by d6d): every taught evidence
  row gets a `learned_evidence` sidecar row with the tool, binary, dialect, kept match tokens and
  the matched line's hash, so a later re-check can replay the caller's own rules (16.6 R2).

**The explicit command (task 16.5, user decision 2026-10-07).** With paths or a pipe, `rmx grep`
execs the real grep plus the learner, exactly like the shim. Only the path-less `rmx grep PAT` still
answers, from the index, with a corpus-pruned `grep -r` floor. rmx's own options are parsed from the
RAW argv by one parser and click parses nothing, not even `--help` (click drops `--`, and a
declared `--help` ate `-e --help`; both probed). Each option has a row per route (exec, index,
floor) in 16.5's d-4 table. The Python re-implementation of grep's output, where four audit rounds
kept finding sibling bugs, is deleted. {#explicit}

## What we give up {#tradeoffs}

1. **Index answers for path-less agent greps.** That is the 18.5–31.7% share above. Agents that
   want the index call `rmx grep`, `rmx context` or the MCP `rmx_search` by name, as the PRIMER
   already tells them. Task 16.4 measures what is actually lost.
2. **The provenance hints** (`# rmx: 'pat' in the index …` on stderr). These were the agent's only
   sign that the index knew something. Not replaced; reconsider if 16.4 shows a loss.
3. **A command rewrite still happens.** `rmxgrep-rewrite.py` parses the command string, and a
   misparse breaks the command whatever mode the shim is in. That risk is unchanged by this plan.
   Fully passive (PostToolUse only, no rewrite) would remove it, but would lose sight of greps
   inside compound commands, and their pre-truncation context. Out of scope; noted as the fallback
   design if the rewriter keeps producing defects.
4. **Shim startup cost** (`sh` plus the learn-toggle reads) on every grep. 16.4 measures it against
   bare grep.

## Tasks {#tasks}

Specs go in `workflow/plans/plan-16-invisible-grep-shim-tasks/` before approval.

| Task | Builds | Acceptance (sketch) |
|---|---|---|
| 16.1 | `grep_learn.py` behind the hidden `rmx grep-learn` (not a verb); `corpus.py` predicate; `_learn_grep_hits` dedupe; short clusters expanded before classification; learn-time provenance into 16.6's sidecar (R10, d6d) incl. the caller's locale; `spawned_by` | flag fidelity with proven power (space forms included); cutoffs honoured; corpus-only; pruning only on recursive re-runs; entity identity under symlinked cwd; detached; slots; switch on `store_root`; idempotent store; provenance on every taught row |
| 16.2 | invisible shim in both wrappers; cwd+argv throttle, counted; `RMXGREP_TEACH` retired via the log; generators + `check()` extended | differential 100% byte-identical with power shown on the current shim; caller never delayed; overhead with the REAL learner |
| 16.3 | Grep-tool hook rebuilt from the tool's real rg argv (`--hidden`, VCS globs, constants pinned); every doc/help surface; `enforce-rmx-grep.sh`'s redirect RETIRED (d9bj) | taught set equals the tool's captured RESPONSE; paging inputs do not kill; no stale claim anywhere; with no marker, a corpus `grep -rn X src` is not redirected |
| 16.4 | measurement, historical + forward (learner log joined to transcripts); window opens after `rmx learn on --global` (d9bj) | precision ≥ 0.99 / recall ≥ 0.95 (micro, timeouts counted) on COMPLETE outputs only, gated at n ≥ 30 else `insufficient-n`; no carve-out; a gate shown able to fail; routes measured |
| 16.5 | explicit `rmx grep` with paths or a pipe execs the real grep + learner; path-less keeps the index read with a pruned `grep -r` floor; rmx options parsed from the raw argv with a per-route table; the Python re-implementation (argv order, `-c` rows, stdin filter, delegate) is DELETED | differential 100% incl. round 4's cases, bug-081 and the `--`/`-e`/`--file` rows; every d-4 cell has a case; nothing beyond the tool's bytes; deletions verified by `rg -w` |
| 16.6 | **Wave-1 slice (d6d), after plan-23's 23.1, no dependency on 16.1:** the `learned_evidence` sidecar keyed on the evidence row's identity + `rules_sha` (replayable from `facts.log` through a `learned_provenance` event, in ONE timestamp-ordered row pass with the `evidence` appends, d9av; the `replica_merge` step R1c is RETIRED, d9ay), THE verifier for learned rows (`learned_verify`: re-runs the recorded tool with only pattern-semantics tokens, returns the matching line set, exit 2 is `unverifiable`; the recorded locale pinned, value arity honoured; a named-subset permissive reading for rows without rules), the ONE census procedure (R7), read-time marks that record staleness under the row's own rules (never a reader-rule drop) through plan-23's queue and that plan-22's 22.1 reads, the backfill, and legacy-writer rows until 16.1 lands. The learn-time write is 16.1 R10. The audit, repair and removal engine MOVED to [[plan-22-audited-removal-and-repair]] (plan review C1-C3, user 2026-10-07); nothing here removes a row | sidecar rows survive a rebuild and a compaction, and the row pass is one timestamp order; BRE, POSIX-class, cutoff and absolute-exclude rows verify `ok`; exit 2 is never `stale-line`; a reader-rule drop writes no mark; backfill leaves no learned row without provenance; marks applied in bounded batches; overflow counted |

## Waves and dependencies {#waves}

From [[plan-review-2026-10-14#t8-wave1]] and d6d. Plan-16 has tasks in two waves.

| wave | order | depends on |
|---|---|---|
| 1 | **16.6 Wave-1 slice**, after plan-23's 23.1 (`23.0 ∥ 23.4 → 23.2 → 23.1`); it feeds plan-22's `22.1a → 22.2 → 22.5 → 22.3` | plan-23 23.1 (queue, `bind(partition_name)` drain), 23.0 (sandbox). NOT 16.1 (#t8-amendments d1c/d6d) |
| 2 | **16.1 → 16.2 ∥ 16.3 → 16.5**; 16.2 and 16.3 DEPLOY TOGETHER, then the user runs `rmx learn on --global` (d9bj), then 16.4's acceptance window opens | 16.1 depends on the 16.6 slice (its R10 writes the sidecar), so there is no Wave 1 → Wave 2 inversion |

Every plan-16 test runs inside plan-23 task 23.0's shared sandbox (d1a/d1b).

**The learn-switch flip (d9bj; r8 s-2).** {#learn-flip} `learn.off` comes off only after 16.2 (the
passive shim) and 16.3 (which retires `enforce-rmx-grep.sh`'s redirect,
[[task-16.3-grep-tool-hook-and-docs#r5]]) are deployed TOGETHER, so the rewrite returns only when
it feeds the passive shim and nothing redirects a corpus grep to `rmx grep`. The USER runs
`rmx learn on --global` (the marker is the user's; no task removes it), and the handoff of that
deploy names the step. 16.4's measurement window opens only after the flip
([[task-16.4-measurement#r0]]).
**No `rmx learn on` in ANY scope (global or project) before 16.3 is deployed (r9 m-3).** Once
bug-118's fix deploys, the generator propagates an optional project hook's exit status, so
`enforce-rmx-grep.sh` really BLOCKS (exit 2) wherever no `learn.off` marker covers the project.
Today the global marker covers every project; removing it, or a project-scope `learn on`, before
16.3 retires the script turns every corpus grep there into a block. Every deploy handoff between
bug-118's deploy and 16.3's states this line.

rel: derives-from -> [[plan-review-2026-10-14#t8-wave1]]

Tasks 16.7–16.10 (the agent's `rmx context` usage) moved to [[plan-21-agent-context-usage]] as 21.1–21.4 (plan review C8, user 2026-10-07), so that review loop and 16.1–16.5's do not block each other.

## Decisions (user, 2026-10-06) {#decisions}

1. **Yes, this supersedes the 2026-09-06 stance.** The rewrite no longer exists so that grep is
   ANSWERED by the index; grep is observed, and the index is asked by name. The 2026-09-15
   no-bypass rule stands: every grep still teaches, and the learn switch is the only off switch.
   Recorded in memory `feedback_grep_is_observed_not_answered`. {#d-1}
2. **Fold `RMXGREP_TEACH=0` into `learn_switch`.** One off switch, not two. 16.2 deletes the env
   var from the shims. If the env var is still set, the shims learn anyway; the learner's log
   record names it and `rmx learn status` points to `RMX_LEARN=0`. Nothing goes to stderr, because
   byte-identity includes stderr (task 16.2 R3). {#d-2}
3. **Invisible shim, not fully passive.** The rewrite stays, because it sees greps inside compound
   commands along with their exact argv and cwd. Fully passive remains the fallback only if 16.2's
   rewriter differential finds misparses. {#d-3}

4. **(2026-10-07, revised the same day) The `-f/--flags` bundle is REMOVED** (user: "change the
   grep to not use -flags"), superseding option B's translation of it. Done in code ahead of 16.5
   (`d559567`): `--flags` is refused with a pointer, `-f FILE`/`--file=FILE` is grep's pattern
   file. 16.5's remaining d-4 rows (index-only options on the hand-off route, the index route and
   the floor) are re-specified in revision 5 ([[task-16.5-explicit-grep-hands-off#d-4]]). {#d-4}

**Interim (user, 2026-10-06):** `RMXGREP_MODE=plain` in `~/.claude/settings.json` and
`.claude/settings.local.json`. Any value other than `rich` is auto, and the agent shell is not a
tty, so greps already run the real tool plus today's flag-stripped ping until 16.2 ships. The 63
env-sensitive tests pass under it (`workflow/review-output/rmxgrep-mode-plain.log`). {#interim}

Next gate: `@ch-bsd` spec review r6 of task specs 16.1–16.6 revision 6, then `approved`.

## Decisions needed (user) — both SETTLED 2026-10-14 {#decisions-needed}

1. **`-k/--kind` and `--linkage` on the path-less floor (b-r4-1). SETTLED by d7a** (user,
   2026-10-14), verbatim from [[plan-review-2026-10-14#t7]]: "dn-1, option (a): `-k`/`--linkage` on
   a path-less call never runs the grep floor; an index miss exits 1, and a call that would go
   straight to the floor exits 2 with a message that the option needs the index. Nothing is
   silently widened. The plan's stated reason is corrected: the blockers are a caller's own
   `--include` widening the translated globs, BSD glob case-sensitivity, and `--linkage` having no
   file-level translation — not a "wider kind"." Revision 5's stated reason ("a wider reading of
   kind") is withdrawn. ([[task-16.5-explicit-grep-hands-off#d7a]]) {#dn-1}
2. **Where 16.6's remaining half lives (C1). SETTLED by d6d** (user, 2026-10-14): neither option
   as stated. 16.6 is split by dependency: the sidecar table, backfill and read-time marks are a
   Wave-1 slice after plan-23 (with no dependency on 16.1, #t8-amendments); the learn-time
   provenance write moves into 16.1 (R10, Wave 2). This also settles plan-22 #b-7.
   ([[task-16.6-learned-row-validation#split]], [[#waves]]) {#dn-2}

rel: derives-from -> [[plan-review-2026-10-14#t6]]
rel: derives-from -> [[plan-review-2026-10-14#t7]]

## Revision round 9 (2026-10-15) {#rev-round-9}

Answers [[bsd-plan16-22-spec-diffcheck-r9-29e335a]] where it touches plan-16 (s-2 and m-5 in
16.6, m-3 in 16.3) and d9bu ([[plan-review-2026-10-14#t12-approvals]]). Plan-22's findings are
answered in [[plan-22-audited-removal-and-repair#rev-round-9]]. Code read at `428267f`; the bug-118
branch read at `462bd0b`.

| finding / decision | answered in |
|---|---|
| s-2 / d9bu (the incremental replay path has no caller; the specs kept extending it; bug-120's Planned cell cited a task that declined it) | [[task-16.6-learned-row-validation#r1f]] (16.6 deletes `apply_log_delta`, `_apply_one_event`, `_apply_event_body`, `_replay_concept`, their test and every mention, with a scan that can fail, AC-12); every clause extending the path dropped from 16.6 R1d and AC-9 / AC-9d; bug-120 closes by removal (the registry row is the orchestrator's) |
| m-5 (AC-9d checks 3 and 4 mis-fire) | 16.6 AC-9d check 3 scoped to the link and row passes (memory-body test allowed by name); check 4 takes values from `row_key` |
| m-3 (16.3 R5 vs bug-118) | [[task-16.3-grep-tool-hook-and-docs#r5]] (`tests/test_bug118_optional_hook_exit.py`, one tuple through `_optional_project_hook`, prose sweep, AC-10 note); [[#learn-flip]] (no `rmx learn on` in any scope before 16.3 deploys) |

rel: amends -> [[bsd-plan16-22-spec-diffcheck-r9-29e335a]]
rel: derives-from -> [[plan-review-2026-10-14#t12-approvals]]

## Revision round 8 (2026-10-15) {#rev-round-8}

Answers [[bsd-plan16-22-spec-rereview-r8-23ad703]] where it touches plan-16 (s-2; b-1, m-1, m-3,
m-5 in 16.6) and d9bj, d9bl ([[plan-review-2026-10-14#t12-approvals]]). Plan-22's findings are
answered in [[plan-22-audited-removal-and-repair#rev-round-8]]. Code and marker state read at
`23ad703`; `src/` is unchanged from `23ad703` to the revision's HEAD.

| finding / decision | answered in |
|---|---|
| s-2 / d9bj (`learn.off` is set globally; no owner for the flip; the redirect re-arms) | [[#today-learn-off]] (the operator state); [[#learn-flip]] and [[#waves]] row 2 (16.2 + 16.3 deploy together, then the user's `rmx learn on --global`); [[task-16.2-invisible-shim#rich]] (stale "today" text); [[task-16.3-grep-tool-hook-and-docs#r5]] (retire `enforce-rmx-grep.sh`'s redirect) + its AC; [[task-16.4-measurement#r0]] (window opens after the flip; switch decision in the header; `learning-off` runs refused) |
| b-1 / d9bl (16.6's row events lack `c_kind`; one format, one resolver) | [[task-16.6-learned-row-validation#r1d]], [[task-16.6-learned-row-validation#r1d-one-format]]; 16.6 AC-9d |
| m-1 (the row pass keeps Pass 2b) | [[task-16.6-learned-row-validation#r1d]]; 16.6 AC-9c |
| m-3 (incremental vs rebuild legacy resolution) | [[task-16.6-learned-row-validation#r1d]] qualified |
| m-5 (pins) | [[task-16.6-learned-row-validation#r1d]] re-read at `23ad703` |

rel: amends -> [[bsd-plan16-22-spec-rereview-r8-23ad703]]
rel: derives-from -> [[plan-review-2026-10-14#t12-approvals]]

## Revision round 7 (2026-10-15) {#rev-round-7}

Answers [[bsd-plan16-22-spec-rereview-r7-331b414]] where it touches plan-16 (verdict: approvable
only together with the lockstep 16.6 R1d edit of b-1) and d9av/d9ay
([[plan-review-2026-10-14#t12-approvals]]). Plan-22's findings are answered in
[[plan-22-audited-removal-and-repair#rev-round-7]].

| finding / decision | answered in |
|---|---|
| b-1 / d9av (16.6 R1d's pass ran every row op after all appends) | [[task-16.6-learned-row-validation#r1d]] ONE row pass in timestamp order; 16.6 AC-9c; lockstep with [[task-22.2-repair-then-remove#r3]] |
| d9ay (16.6 R1c, a slot-merge path) | [[task-16.6-learned-row-validation#r1c]] RETIRED; 16.6 AC-2 retired; [[#tasks]] row 16.6 |
| m-3 (census default partition) | [[task-16.6-learned-row-validation#r7]] `--default-partition` |

rel: amends -> [[bsd-plan16-22-spec-rereview-r7-331b414]]
rel: derives-from -> [[plan-review-2026-10-14#t12-approvals]]

## Revision round 6 (2026-10-15) {#rev-round-6}

Answers [[bsd-plan16-22-spec-rereview-r6-0e77da3]] where it touches plan-16 (verdict: APPROVABLE
for 16.1-16.6; every r4 item closed). Plan-22's findings are answered in
[[plan-22-audited-removal-and-repair#rev-round-6]].

| finding / decision | answered in |
|---|---|
| m-3 (22.1a AC-8b's census has no procedure) | [[task-16.6-learned-row-validation#r7]] `--census dangling-link`; [[task-16.6-learned-row-validation#rev-round-6]] |
| m-6 (stale line numbers) | 16.6 [[task-16.6-learned-row-validation#r1d]], [[task-16.6-learned-row-validation#r1e]], AC-9b and its file list cite by symbol |

rel: amends -> [[bsd-plan16-22-spec-rereview-r6-0e77da3]]

## Revision round 5 (2026-10-14) {#rev-round-5}

Answers [[bsd-plan16-22-spec-rereview-r4-878647c]] (plan-16: m-3, m-4; shared b-2, s-3, m-1, m-2;
the r3 partial s-6) and d9ab ([[plan-review-2026-10-14#t11-approvals]]). Verdict at r4: 16.2-16.5
approvable; 16.1 and 16.6 revised here. Plan-22's findings are answered in
[[plan-22-audited-removal-and-repair#rev-round-5]].

| finding / decision | answered in |
|---|---|
| b-2 / d9ab (the compactor drops the sidecar's events) | [[task-16.6-learned-row-validation#r1d]] the dump emits `learned_provenance`; 16.6 AC-9b; `source` on `protect` is 22.6 R6's |
| s-3 (census `HOME` redirect empties the deny set and `home_base`) | [[task-16.6-learned-row-validation#r7]] steps 4-5; 16.6 AC-5c |
| m-1 (probe outside the procedure) | [[task-16.6-learned-row-validation#r7]] `--census probe-reproduction` |
| m-2 (compaction and the churn bound) | [[task-16.6-learned-row-validation#r7]] step 4 header |
| m-3 (locale details) | [[task-16.6-learned-row-validation#r2]] `setlocale` probe; 16.6 R1 `rules_sha` serialization; [[task-16.1-argv-faithful-learner#r10]] `locale` in the queue record |
| m-4 (rg `-E`, `-j`) | [[task-16.1-argv-faithful-learner#r1-clusters]]; [[task-16.6-learned-row-validation#r2-argv]] |
| r3 s-6 (partial) | closed by s-3 |

rel: amends -> [[bsd-plan16-22-spec-rereview-r4-878647c]]
rel: derives-from -> [[plan-review-2026-10-14#t11-approvals]]

## Revision round 3 (2026-10-14) {#rev-round-3}

Answers [[bsd-plan16-22-spec-rereview-r3-6091648]] (plan-16: s-1, s-2, m-2, m-6; shared s-3, s-4,
s-5, s-6, m-1, m-5) and d9o ([[plan-review-2026-10-14#t9-approvals]]). Verdict at r3: 16.2-16.5
approvable; 16.1 and 16.6 revised here.

| finding / decision | answered in |
|---|---|
| s-1 (locale not recorded; daemon verifies in C) | [[task-16.1-argv-faithful-learner#r10]] `locale`; [[task-16.6-learned-row-validation#r1]] `locale` in `rules_sha`; [[task-16.6-learned-row-validation#r2]] constructed env, `locale-missing`; 16.6 AC-3i |
| s-2 (clusters; arity) | [[task-16.1-argv-faithful-learner#r1-clusters]]; [[task-16.6-learned-row-validation#r2-argv]]; 16.1 AC-1d; 16.6 AC-3b |
| s-3 (permissive subset not rare) | [[task-16.6-learned-row-validation#r2-permissive]] (counts cited); 22.1a `orphan-root:unverifiable` |
| s-4 (union AC cannot fail) | 16.6 AC-3h (disagreeing readings, both orders) |
| s-5 → d9o (purges and the sidecar) | [[task-16.6-learned-row-validation#r1e]]; [[task-22.6-removal-entry-points]] owns the paths |
| s-6 (census procedure) | [[task-16.6-learned-row-validation#r7]] (the ONE procedure, owned here, used by plan-22) |
| m-1 (one replay pass) | [[task-16.6-learned-row-validation#r1d]]; 16.6 AC-9 |
| m-2 (contract details), m-6 (`bin` pinned) | [[task-16.6-learned-row-validation#r2]] |
| m-5 (plan-of-plans row 16) | [[#open-after-revision]] 4: still an orchestrator edit, outside this plan's files |

rel: amends -> [[bsd-plan16-22-spec-rereview-r3-6091648]]
rel: derives-from -> [[plan-review-2026-10-14#t9-approvals]]

## Revision round 2 (2026-10-14) {#rev-round-2}

Answers [[bsd-plan16-22-spec-rereview-32dde06]] (plan-16: 3 BULLSHIT, 1 SKETCHY, 3 MEH, the b-r5-1
partial, the shared s-3 and m-4) and [[plan-review-2026-10-14#t9]] (`#t9-fixes`). Verdict at the
re-review: 16.1, 16.3, 16.4 and 16.5 approvable; 16.2 and 16.6 revised here.

| finding / decision | answered in |
|---|---|
| b-1 (re-run calls matching rows stale) | [[task-16.6-learned-row-validation#r2-argv]], [[task-16.6-learned-row-validation#r2]]; 16.6 AC-3, AC-3b |
| b-2 (sidecar not replayable) | [[task-16.6-learned-row-validation#r1d]]; [[task-16.1-argv-faithful-learner#r10]]; 16.6 AC-9 |
| b-3 (marks have no reader) | [[task-16.6-learned-row-validation#r4-reader]]; [[task-22.1-audit-classes#r1-marks]] |
| b-4 (cross-plan verifier conflict; line-set API) | [[task-16.6-learned-row-validation#r2]]; [[#open-after-revision]] 1 |
| s-3 (census ACs vs the 23.0 sandbox) | 16.6 AC-5 (5a sandbox, 5b operator census on a copied read snapshot) |
| s-4 (16.2 fixture unscrubbed; d8f) | [[task-16.2-invisible-shim#ac-1-fixture]] |
| s-5 (repairs move sidecar keys) | [[task-16.6-learned-row-validation#r1]] (`move_learned_provenance`, owners named in 22.2/22.5) |
| m-1 (dialect premise) | [[#open-after-revision]] 3; 16.6 R1 |
| m-2 (stale open item 4; plan-of-plans rows) | [[#open-after-revision]] 4 (plan-of-plans cells handed to the orchestrator) |
| m-4 (vocabulary; "22.1b"; `root` setter) | 16.6 [[task-16.6-learned-row-validation#rev-round-2]] |
| m-6 (AC-6 count) | 16.6 AC-6 |
| r5 b-r5-1 (partial) | closed by b-1, b-2, b-4 |
| #t9-fixes rows for plan-16 (verifier + line set + three holes; `facts.log` event; sandbox-safe clones; scrubber) | the rows above |

rel: amends -> [[bsd-plan16-22-spec-rereview-32dde06]]
rel: derives-from -> [[plan-review-2026-10-14#t9]]

## Revision 6 changelog {#revision-6}

Every r5 finding, the r4 partials it carried, the plan-22 review items naming plan-16, and the
2026-10-14 decision-log rows and review items that touch plan-16, by id.

| finding / decision | answered in |
|---|---|
| r5 b-r5-1 (16.6 provenance cannot replay the caller's rules) | [[task-16.6-learned-row-validation#r1]], [[task-16.6-learned-row-validation#r2]], [[task-16.1-argv-faithful-learner#r10]] |
| r5 b-r5-2 (AC-5b's BRE-routing mutation cannot fire) | [[task-16.5-explicit-grep-hands-off#ac-5-seed]] |
| r5 s-r5-1, r4 b-r4-2 (partial) (click still parses `--help`; `-k` cluster rule) | [[task-16.5-explicit-grep-hands-off#r0]] |
| r5 s-r5-2, r4 s-r4-7 (partial) (16.2 AC-4b vs 16.1 R1b's `--include` pruning) | [[task-16.1-argv-faithful-learner#r1b]]; 16.2 AC-4b kept ([[task-16.2-invisible-shim#revision-6]]) |
| r5 s-r5-3 (marks record reader-rule drops) | [[task-16.6-learned-row-validation#r4]] |
| r5 s-r5-4 (sidecar on `evidence_rowid`) | [[task-16.6-learned-row-validation#r1]], [[task-16.6-learned-row-validation#r1c]] |
| r5 s-r5-5, plan-22 #b-7, decision-log review #b-3 (16.6 unscheduled; Wave 1 → Wave 2 inversion) | [[#waves]]; [[task-16.6-learned-row-validation#split]]; 16.6 header |
| r5 s-r5-6 (route 2 absorbs Grep-tool and `rmx grep` records) | [[task-16.1-argv-faithful-learner#r6]]; [[task-16.4-measurement#r1-forward]]; 16.2/16.3/16.5 pass `--spawned-by` |
| r5 m-r5-1 (`handed-off` mis-read) | [[task-16.5-explicit-grep-hands-off#r6]] |
| r5 m-r5-2 (AC-5d/5f miss pattern absent from disk) | [[task-16.5-explicit-grep-hands-off#acceptance]] 5d/5f |
| r5 m-r5-3 (index-flag folder and format sets unnamed) | [[task-16.5-explicit-grep-hands-off#r3]], [[task-16.5-explicit-grep-hands-off#r4]] |
| r5 m-r5-4 (`spawn()`'s interpreter) | [[task-16.2-invisible-shim#r2b]]; [[task-16.5-explicit-grep-hands-off#sandbox]] |
| r5 m-r5-5 (space-form rows) | [[task-16.1-argv-faithful-learner#r1-space-forms]] |
| r5 m-r5-6 (`$` rule after shlex) | [[task-16.4-measurement#r1-forward]] |
| r5 m-r5-7 (truncated floor exit) | [[task-16.5-explicit-grep-hands-off#d-4]], [[task-16.5-explicit-grep-hands-off#r3]] |
| plan-22 #b-1 (no line hash) | [[task-16.6-learned-row-validation#r3]]; [[task-16.1-argv-faithful-learner#r10]] |
| plan-22 #b-2 (no flags on rows) | [[task-16.6-learned-row-validation#r1]] (rules recorded); pre-provenance rows are plan-22's most-permissive re-check ([[task-16.6-learned-row-validation#r2]]) |
| plan-22 #s-6 (no row identity; unstable rowid) | [[task-16.6-learned-row-validation#r1]] |
| plan-22 #m-3 (this file said 16.6 prunes) | [[#tasks]] row 16.6 (closed in r5; re-checked: no prune text) |
| decision-log review #m-3 (`stale_seen` on a lossy queue) | [[task-16.6-learned-row-validation#r4-lower-bound]] |
| decision-log review #s-1 (only the sidecar got a `replica_merge` fix) | [[task-16.6-learned-row-validation#r1c]] (sidecar); the other tables are plan-23's |
| decision-log review #m-6 (MEH ids enumerated) | this table lists every r5 MEH id (m-r5-1..m-r5-7) |
| d6d, #t8-amendments d1c/d6d | [[#waves]], [[#dn-2]], [[task-16.6-learned-row-validation#split]], [[task-16.1-argv-faithful-learner#r10]] |
| d7a | [[#dn-1]], [[task-16.5-explicit-grep-hands-off#d7a]] |
| #t6-fixes (line hash; tool + dialect + hash; reader-rule drops vs staleness; key survives `replica_merge`) | 16.6 R1-R4; 16.1 R10 |
| #t7-fixes (seed + pre-check; click parses nothing; recursive-only pruning, AC-4b kept; `spawned_by`; the MEH list) | 16.5 AC-5 / R0; 16.1 R1b / R6; 16.2 AC-4b; 16.4 R1; the m-r5 rows above |
| bug-102 (`--context` space-value, `cli.py:5540`) | [[task-16.1-argv-faithful-learner#r1]] (`value` column); 16.5 R4 deletes the set, R8 marks it fixed |
| d1a/d1b (tests in 23.0's sandbox) | each task's test strategy; [[#waves]] |

rel: amends -> [[bsd-plan16-spec-review-r5-cd7c923]]

## Revision 5 changelog (history) {#revision-5}

| finding (r4) | answered in |
|---|---|
| m-r4-1 stale header, out-of-scope bullet, #why bug list | this file: status line, [[#out-of-scope]] bullet 2, [[#cost]] list |
| b-r4-1, b-r4-2, s-r4-1, s-r4-2, s-r4-3, s-r4-6, m-r4-3, m-r4-6 | [[task-16.5-explicit-grep-hands-off#revision-5]] |
| s-r4-4, s-r4-7, m-r4-5 | [[task-16.2-invisible-shim#revision-5]] (and 16.3, 16.1 for s-r4-4) |
| s-r4-4, m-r4-2, m-r4-4 | [[task-16.3-grep-tool-hook-and-docs#revision-5]] |
| s-r4-5, m-r4-7 | [[task-16.4-measurement#revision-5]] |
| m-r4-2, m-r4-8, `ts` (s-r4-5) | [[task-16.1-argv-faithful-learner#revision-5]] |
| plan review C1/C2/C3 (16.6) | [[task-16.6-learned-row-validation#revision-5]] |
| gaps: "plan-16 header says revision 3" | this file's status line |

rel: amends -> [[plan-review-2026-10-07#gaps]]

## Out of scope {#out-of-scope}

- **Route 3: Claude Code's own `grep()` (spec review #s-5).** In the top-level Bash-tool shell,
  Claude Code's snapshot function runs its embedded ugrep and shadows the agent-bashrc `grep()`.
  So a grep the rewrite does not touch is not observed: non-head (`if grep -q …`), git-exempt, or
  in a command with a heredoc. Capturing it would reopen d-3. Task 16.4 measures its share as
  `unobserved_share`, and the decision is revisited if that share is large.

- *(Superseded by task 16.5, kept as history.)* This bullet once put `rmx grep`'s own drop-in gaps
  (`\b`/`\<` BRE escapes, the missing-path exit code, `-w` verification) out of scope as "the
  explicit command's backlog". Task 16.5 now brings them IN scope: named-path and pipe calls exec
  the real grep, BRE patterns route to the grep floor, and 16.5 R8 marks bug-081 fixed and the
  named-path rows superseded. Nothing of the explicit command's drop-in surface remains out of
  scope.
- A PATH-level `grep` alias. CORRECTION (task 16.2): scripts the agent runs under bash DO reach the
  shim today, through the `grep()`/`rg()` functions that `BASH_ENV` defines in
  `agent-bashrc.sh`. They become invisible along with everything else. Shells outside the agent are
  untouched.

## Open after revision {#open-after-revision}

Revision round 2 (2026-10-14) closed all four items the revision-6 list carried; the re-review
classified none of them as a user decision ([[bsd-plan16-22-spec-rereview-32dde06#open-16]]).
Kept by number so earlier links still resolve.

1. **Two verifiers — CLOSED.** 16.6 R2 (re-run the recorded tool) is THE verifier; plan-22's 22.1
   calls it and carries no matcher of its own. 16.6 R2 exposes `matching_lines` (the line set 22.1
   classifies on) and closes its three false-stale holes; rows without rules use 16.6's
   `permissive_matching_lines`, which names its subset. `stale_seen` is read by 22.1 for ordering
   and reporting only, as a lower bound ([[task-16.6-learned-row-validation#r2]],
   [[task-16.6-learned-row-validation#r4-reader]], [[task-22.1-audit-classes#r1-verify]]).
2. **16.6 R1b vs a re-backfill — CLOSED, R1b kept.** It is strictly more informative (`learned_at`,
   `root`) and closes the window; d6d moved only the RULE-bearing write to 16.1. 16.6 AC-6 now
   counts distinct evidence identities (m-6).
3. **The dialect enum — CLOSED, premise withdrawn (m-1).** `#t6-fixes` names no enum. The enum is
   exactly what 16.1 R10 writes (`bre`, `ere`, `fixed`, `rust`, `pcre2`, `mixed`); `python` and its
   dead verifier branch are gone ([[task-16.6-learned-row-validation#r1]]).
4. **Wave lists — CLOSED here (m-2).** `workflow/plan-of-plans.md` already lists the 16.6 slice in
   Wave 1 and marks `plan-review-2026-10-07#order` superseded. Two plan-of-plans cells still lag
   (row 16's "+ tasks 16.7-16.10", which moved to plan-21; row 22's task count). That file is
   outside this plan's files and is handed to the orchestrator, not edited here. Round 3 (r3
   m-5): still lagging at `6091648`; still handed to the orchestrator.
