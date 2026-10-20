---
gmd: "0.1"
id: bsd-plan3-verbs-parity-r8-d4bf001
title: "ch-bsd findings — plan-3 verbs parity r8 (remedy 0e3002f at 273cc16, judged at master d4bf001): all six r7 findings closed in behaviour at master; three closures are held by behaviour alone, not by tests (3 mutants survive the full plan-3 set); absent and busy are still confused on the global legs; task 3.4's spec does not match today's CLI surface and the plan does not list the task"
tags: [bsd, findings, plan-3, verbs, cli, search, remedy-r8, task-3.4]
severity: SKETCHY
plan: plan-3-verbs-parity
task: task-3.1-plan-3-verbs-parity, task-3.2-plan-3-verbs-parity, task-3.3-plan-3-verbs-parity, task-3.4-internal-cli-allowlist
metadata:
  node_type: bsd-report
  commit: d4bf001
  remedy_commit: 0e3002fb09b237893001915d31c0662390217005 (+ 3ca99f9 RED, 5960208 test + summary)
  merge_commit: 273cc16
  later_fix: "6675d17 (bug-069) — the third `_replica_bundle` caller, which r8's summary says r8 fixed"
  range: "e0b7df6..d4bf001, limited to plan-3 surfaces (search.py fan-outs, verbs.memory promote, cli canon find / locate / memory promote / _echo_skipped, ui app.js doWhere, tests/test_plan3_remedy_r7.py, test_verb_parity.py); 388 commits after the remedy merge were checked only for drift on these surfaces"
  head_at_audit: d4bf001
  tree: "/Volumes/littlebig/refmatrix-plan3-close (branch plan3-close-w1 = master d4bf001); mutations and probes ran in two scratch copies under the session scratchpad, never in the clone"
  verdict: DIRTY
  findings: 5
---

# ch-bsd findings — plan-3 remedy round 8 re-review {#root}

**Commit:** d4bf001 (master). Plan-3 r8 content is `3ca99f9` + `0e3002f` + `5960208`, merged at `273cc16`.
`6675d17` (bug-069) completed the third caller later.
**Date:** 2026-10-19
**Author:** Todd Holley / Opus 5 (1M) / orchestrator (remedy); auditor Opus 5.5
**Files changed (0e3002f):** 7. Of these, 4 are src: `cli.py`, `search.py`, `ui/static/app.js`, `verbs.py`.

rel: amends -> [[bsd-plan3-verbs-parity-r7-e0b7df6]]
rel: evidence-for -> [[plan-3-verbs-parity]]
rel: evidence-for -> [[impl-remedy-plan-3-r8]]
rel: evidence-for -> [[task-3.4-internal-cli-allowlist]]

## Method {#method}

All runs used `.venv-eval` with `PYTHONPATH=<tree>/src:$PYTHONPATH`, which prepends the tree and
keeps the four ambient entries (r7's recipe). `tests/conftest.py` refuses to run unless
`refmatrix` resolves inside the tree under test. Probe P0 also asserts this for six modules. The
following artifacts are in `workflow/review-output/`:

- `pytest-bsd-plan3-r8-suites.log`: **169 passed in 397 s** at d4bf001 across 13 files: the
  plan-3 remedy files r2-r7, `test_plan3_remedy`, `test_verb_parity`, `test_mcp_parity`,
  `test_verbs_migrated`, `test_locate`, `test_surface_parity` and `test_ui_server`.
- `bsd-plan3-r8-probe.log` and `bsd-plan3-r8-probe-p2.log`: behaviour probes at master, run in a
  scratch copy. The test file was never committed.
- `pytest-bsd-plan3-r8-mutations.log`: 12 mutations against the targeted test, run in a scratch
  copy with its own git. Each mutation was reverted with `git checkout -- src/` and the copy was
  confirmed clean afterwards. The baseline was 17/17 green first.
- `bsd-plan3-r8-mutations-wide.log`: the four survivors re-run against all 11 plan-3 behaviour
  files.
- `bsd-plan3-r8-clitree.log`: the full click tree walk, used for the 3.4 assessment.

{#method-body}

## Round-7 findings, verified on master {#r7-status}

- **#b-1 CLOSED in behaviour, and held by tests.** At d4bf001, `_replica_bundle`
  (`search.py:76-106`) appends to `on_error` at `:95-96` / `:104-105`. All three callers read the
  list: `_where_one_project` at `:160`, `federated_concept` at `:276-281`, and
  `_locate_one_project` at `:368-370` / `:378-379`. Probe P4 ran on an up-classified daemon with
  no `catalog.read.duckdb` and no patching. Concept, where and locate each name `no replica to
  read (FileNotFoundError: no replica catalog to read at …)`. P3: `rmx canon find held_row` echoes
  the skipped line to stderr and prints `no live project hosts held_row (1 store skipped — see
  stderr)`, exit 0. Mutations M1 (drop the append), M2 (concept stops reading), M3 (where stops
  reading) and M9 (locate filename leg back to `pass`) each kill their test. M10 (locate keyword
  leg stops reading) survives; see [[#s-1]]. **Caveat on history:** at the merge `273cc16` the
  third caller was NOT fixed, although the summary says it was. See [[#m-1]]. It is closed on
  master by `6675d17`. {#v-b1}
- **#b-2 CLOSED in behaviour.** `verbs.py:1240-1244`: the global write passes
  `timeout=_left(30.0), retries=0`. Probe P1 used a project read that answers and a held GLOBAL
  `_PingOnlyDaemon`. Result: **10.0 s**, exit 1, `global store memory_add failed: timed out`,
  global ops `['memory_add']`, one attempt. r7 measured 180.2 s. M5 (keywords dropped) kills the
  test at 60.0 s. M4 survives (fixed `timeout=30.0`, which takes 30.3 s against the 10 s promise);
  see [[#s-1]]. The new absent-global behaviour is in [[#s-2]]. {#v-b2}
- **#s-3 CLOSED in behaviour.** There is one renderer, `cli._echo_skipped` at `cli.py:4338`,
  called from `canon_find` at `:4369` and from `locate` at `:9217`. `app.js:578-598` renders
  `skipped` in both the zero-hit branch (`:587`) and the grouped branch (`:598`). M7 kills the
  test. M11 (grouped branch) is killed by `test_ui_server`. M12, which brings back exactly r7's
  "no hits" symptom in the zero-hit branch, survives the whole plan-3 set; see [[#s-1]]. {#v-s3}
- **#s-4 HALF closed.** Registry rows 106/107 name both remedy files and the `_replica_bundle`
  fake. r7's Fix also asked for one real-daemon `--degree` test to graduate the `answering`
  fixture. That test was not written, and the summary does not mention dropping it; see
  [[#s-3]]. {#v-s4}
- **#m-5 CLOSED.** `cli.py:11477-11483` passes `max(0.5, _budget - (now - _t0))`. M6 (whole
  budget) makes the test fail at 15.0 s, which is r7's number. {#v-m5}
- **#m-6 CLOSED.** `plan-3-verbs-parity.md:91` adds Q19 and records "Q17 is AMENDED". Q19 does
  not mention the third caller, which is covered by bug-069's own row. {#v-m6}
- **Drift since 273cc16:** `search.py` was touched only by `6675d17` (an improvement).
  `verbs.py` was touched by bug-109 and other commits, but the promote block is unchanged.
  `cli.py` grew by 1,652 lines, but `_echo_skipped`, `canon_find` and `memory_promote` behave as
  probed. No regression was found. {#v-drift}
- **Deferral sweep:** both families were run over `273cc16^1..d4bf001` on `search.py`,
  `verbs.py` and `app.js`. There is one hit, "indistinguishable" in `search.py:280`, and it
  describes the fixed defect, so it is innocent. No stale or unanchored deferral was found in
  plan-3 src. {#v-deferrals}

## Findings {#findings}

### SKETCHY: three r7 closures hold in behaviour but not under test — M4, M10 and M12 survive the full plan-3 set {#s-1}

**File:** `tests/test_plan3_remedy_r7.py:181`, `:231`, `:99`; `tests/test_ui_server.py:158`;
against `src/refmatrix/verbs.py:1244`, `search.py:379` and `ui/static/app.js:587`.

**What:** I re-ran the three survivors against all 11 plan-3 behaviour files
(`bsd-plan3-r8-mutations-wide.log`). The fourth survivor, M8, is killed there by r6's canon test.

| mutant | change | result |
|--------|--------|--------|
| M4 | promote global write `timeout=30.0, retries=0` (not `_left`) | **SURVIVES**: 30.3 s passes `elapsed < 40.0` (`:181`), while the command promises 10 s and runs in 10.0 s at master |
| M10 | `_locate_one_project` keyword leg stops reading `errs` | **SURVIVES** 125/125: `:231` accepts `"failed"`, and the filename leg supplies it |
| M12 | `doWhere` zero-hit branch back to plain `no hits` | **SURVIVES** 125/125: the r1 #b-4 test only checks the grouped branch, and `"skipNote" in body` (`:158`) is satisfied elsewhere |
| M8 | `canon_find` prints a different "nowhere" line with no suffix | survives the r7 file, because its assertion is wrapped in `if "no live project hosts" in out:` (`:99`). Killed by r6's test |

**Why it matters:** the round-8 summary says "7 of 7 kill their target". Those were the remedy's
own mutations. The three above are the regressions most likely to happen next time someone
edits these lines, and none of them is pinned. M4 is the partial-bound family's test half: the
command promises 10 s, the test allows 40 s, and a 3× regression passes. M12 is the exact
symptom r7 #s-3 filed.

**Fix:** tighten `:181` to `< verbs.MEMORY_READ_BUDGET_S + 3.0`, as its sibling at `:205` does.
Assert the keyword-only locate case (P4c's shape) needs `(keyword 'held')` in the reason. Add a
static assertion that the `!hits.length` branch uses `skipNote`. Remove the `if` at `:99` and
assert the skipped line unconditionally.

**Pattern match:** YES. This is [[bsd-impressions#imp-quoted-line-sibling]], and the
guard-cannot-fire family's test-side twin: the test agrees with the code for the input it
chose.

rel: contradicts -> [[plan-3-verbs-parity#execution]]

### SKETCHY: absent is still reported as busy on the global legs; promote now fails a cold global store with a raw errno in 0.0 s {#s-2}

**File:** `src/refmatrix/verbs.py:1240-1244` (promote, `retries=0` skips `ensure_global_daemon`);
`src/refmatrix/search.py:243-246` (`federated_where` global leg, since `26404fe`); compare
`verbs.py:652` (`memory add --global`, still ensures the daemon).

**What:** Probe P2 used a project read that answers and a global root with no daemon. The
result was **0.0 s, exit 1, `Error: global store memory_add failed: [Errno 2] No such file or
directory`**, with `ensure_global_daemon` calls = 0. Before r8 this case spawned the global
daemon and wrote the row. Its sibling `memory add --global` still does that. r7's Fix said the
absent case "fails fast with the wording `global_call`'s docstring prescribes". The fail-fast
landed; the wording did not. Separately, P4b shows `federated_where` naming an absent global
socket `global memory_search did not answer within 3s (FileNotFoundError)`. That is a timeout
claim for an op that failed instantly with ENOENT.

**Why SKETCHY:** no store is opened and no row is lost, so this is not the slot-opening
busy≠absent defect from earlier rounds. But Q11's contract is that busy and absent are
classified, not inferred from an exception string. Two plan-3 legs still say "busy/timed out"
for "not running". And a command that worked cold before r8 now fails with an errno.

**Fix:** classify before the global write. Use `discovery.daemon_status(global_store_root())`
under `_left`, and raise `VerbAbsentError("global store daemon not running — start the hub
(rmx hub start)")`, or call `ensure_global_daemon` inside the remaining budget. In
`search.py:243`, word the reason from the exception type: `ConnectionRefusedError` and
`FileNotFoundError` mean "not running"; `TimeoutError` means "did not answer within".

**Pattern match:** YES. This is the busy≠absent lineage (Q11), in its inverse shape. It is not
escalated because nothing writes to a slot.

rel: contradicts -> [[plan-3-verbs-parity#decisions-log]]

### SKETCHY: r7 #s-4's real-daemon `--degree` test was dropped silently, and the registry's graduation note names no task {#s-3}

**File:** `workflow/test_mock_registry.md:106`. Its graduation column reads "graduate the
remaining patches toward the real-daemon fixture". Also `tests/test_plan3_remedy_r6.py:56-99`:
`answering` is the only `--degree` healthy-path evidence. Also
`workflow/implementation_summaries/remedy-plan-3-r8.md` (the `#s-4` row mentions the registry
only).

**What:** r7 #s-4's Fix had two parts: seven registry edits, and one real-daemon `--degree` test
built on the `Store.init` + `spawn_daemon_subprocess` shape. The first part landed. The second
was neither built nor declared dropped. The graduation text is a soft deferral with no task
behind it (rule 9a).

**Why SKETCHY rather than BULLSHIT:** r7 verified the behaviour itself (0.1 s on a real daemon,
3.6 s live), and the gap is in the test, not production. If it reaches a fourth plan-3 round
open, it escalates.

**Fix:** write the test (about 30 lines; r7's probe is the template), or file a task spec and
point the registry column at it.

rel: contradicts -> [[claude#no-mocks]]

### SKETCHY: task 3.4's spec is not accurate against today's CLI surface, and plan-3 does not list the task {#s-4}

**File:** `workflow/plans/plan-3-verbs-parity-tasks/task-3.4-internal-cli-allowlist.md`
(`#requirements`, `#acceptance`); `workflow/plans/plan-3-verbs-parity.md:93-99` (the Task
Breakdown lists 3.1-3.3, and there is no `rel: specifies` for 3.4);
`workflow/plan-of-plans.md:23` ("yes (3)").

**What:** the click tree walk (`bsd-plan3-r8-clitree.log`) finds **195 invocable paths**: 193
leaves plus the `invoke_without_command` groups `learn` and `queue`. The spec's three-way split
(CLI_MAP twin / INTERNAL_CLI / LEGACY_UNPAIRED) gets six things wrong:

1. **There is no slot for dispatcher-action twins.** `rmx_memory` and `rmx_task` are verbs with
   an `action` enum, but `CLI_MAP` names one path each. As written, 15 commands that ARE covered
   by a verb would land in LEGACY_UNPAIRED: `memory list/search/promote/brief/forget/reclassify/
   retag/link/score/bulk-forget/dedup` and `task push/pop/current/swap`.
2. **Seven of those bypass the verb that covers them.** `memory forget` (`cli.py:12642`),
   `reclassify` (`:11496`), `retag` (`:11554`), `link` (`:12415`), `score` (`:12454`),
   `bulk-forget` (`:12977`) and `dedup` (`:12673`) build their own daemon payloads instead of
   calling `verbs.memory`, even though `verbs._MEMORY_OPS` / `_memory_payload` define the same
   ops. This is anti-drift (CLAUDE.md: "CLI and MCP expose it, never implement it"). Neither the
   forward check nor the spec's reverse check can see it.
3. **The seed list is incomplete.** `derive unstamp` came in the same commit as the spec
   (`321ff97`) and is not seeded. The bare `rmx learn` invocation is not covered.
4. **Hidden aliases are not addressed.** These are `add-concept`, `add-entity`,
   `add-linkage-type`, `list-entities`, `list-linkages` and `list-queries`. Plan-16's
   `grep-learn` will also be hidden (task 16.1:319), so "skip hidden" is not a safe rule.
5. **The copy instruction is a trap.** Acceptance 1 says to add a throwaway command "on a COPY of
   the group". A `copy.copy(cli.main)` shares its `.commands` dict, so `add_command` mutates the
   real tree.
6. **LEGACY_UNPAIRED is 140 paths, not a handful.** 55 are top-level; then focus 18, hub 9,
   daemon 9, session 8, partition 6, replica 5, and others. "Each listed with a decision" is a
   140-row table, and the spec has no rule that stops the set from growing.

The plan also does not reference 3.4. Plan-3's Execution contract flips `completed` after a
CLEAN ch-bsd, so a CLEAN round could close plan-3 with 3.4 still `pending`.

**Fix:** amend the spec as listed in [[#t34-build]]. Add 3.4 to plan-3's Task Breakdown with
`rel: specifies -> [[task-3.4-internal-cli-allowlist]]`, and change plan-of-plans to "(4)".

rel: contradicts -> [[plan-3-verbs-parity#task-breakdown]]
rel: contradicts -> [[project-profile#constraints]]

### MEH: the r8 summary says r8 fixed the third `_replica_bundle` caller; it merged that test RED, and the record was never corrected {#m-1}

**File:** `workflow/implementation_summaries/remedy-plan-3-r8.md:50-58` (#third-caller: "Both
legs now report, and `federated_locate` merges per-project reasons into `skipped`");
`src/refmatrix/cli.py:4365` (the comment still says `canon find` "was the last consumer
discarding its fan-out's `skipped` list", which is r7 #s-3's disproved universal).

**What:** `5960208` ("fix(search): the THIRD _replica_bundle caller reports too") changed only
the test and docs. `_locate_one_project` at `273cc16` still had `except Exception: pass` and no
`on_error`. `6675d17`'s own message says "Three tests had been failing since plan-3 round 8,
undiagnosed". So the r8 merge shipped red, and its summary claims a fix that did not exist until
bug-069.

**Fix:** add an amendment line to `#third-caller` that points at `6675d17` / bug-069. Change the
comment at `cli.py:4365` to "one of three consumers".

## 3.4 build list (what exactly must be built) {#t34-build}

1. **`verbs.INTERNAL_CLI: dict[tuple[str, ...], str]`**, keyed by click path tuples (the same
   shape as `CLI_MAP` values). Seed with `derive log`, `derive diff`, `derive status`,
   **`derive unstamp`**, **`learn`** (the bare invocation), `learn on`, `learn off` and
   `learn status`. Each reason quotes deferral_registry row 47. Do NOT seed `grep-learn`: it does
   not exist, and the hygiene check would fail. Task 16.1 adds it (16.1:319 already says so).
2. **`verbs.CLI_ACTIONS: dict[tuple, tuple[str, str]]`** (new): path → (dispatcher verb,
   action), for the 15 action twins in [[#s-4]] item 1, each with a wiring class.
3. **The seven memory writes:** route `forget`, `reclassify`, `retag`, `link`, `score`,
   `bulk-forget` and `dedup` through `verbs.memory(action=…)` (wiring `calls`), or record each in
   LEGACY with a reason. The first option is what plan-3's premise requires.
4. **`verbs.HIDDEN_ALIASES: dict[tuple, tuple]`** for the six hidden aliases. Each maps to its
   visible target, and the target's classification applies.
5. **`verbs.LEGACY_UNPAIRED: dict[tuple, str]`** for the remaining **140** paths. Each gets a
   decision ("verb it" or "internal"); grouping by family is fine. Add a test that pins the set
   as a subset of a frozen baseline, so it can shrink but never grow.
6. **`test_verb_parity.py` reverse walk.** It takes the group as a parameter and includes
   `invoke_without_command` groups. It asserts that every path is in **exactly one** of
   {CLI_MAP twin, CLI_ACTIONS, INTERNAL_CLI, HIDDEN_ALIASES, LEGACY_UNPAIRED}. The failure
   message names the path and both remedies (a verb + `CLI_MAP`, or `INTERNAL_CLI`).
7. **RED proof for acceptance 1:** `g = copy.copy(cli.main); g.commands = dict(cli.main.commands);
   g.add_command(click.Command("zz-probe"))`, then walk `g`. Assert afterwards that
   `"zz-probe" not in cli.main.commands`.
8. **Acceptance 2/3:** `monkeypatch.delitem(verbs.INTERNAL_CLI, ("derive", "log"))` → fails.
   A stale key in any of the five maps → fails.
9. **Wiring for CLI_ACTIONS:** use `test_cli_twin_calls_its_verb`'s recorder shape (CliRunner +
   `sig.bind`) for every `calls` action twin, asserting `action=<x>` arrives.
10. **Docs:** add 3.4 to plan-3's Task Breakdown with `rel: specifies`; plan-of-plans "(4)";
    deferral row 47 → resolved on completion; an implementation summary with the LEGACY decision
    table.

## Observations (not findings) {#observations}

- The mutation runner first ran without `tools/` in the scratch copy, and every mutant "killed"
  with rc=3 (an INTERNALERROR from the pyc guard). I re-ran with `tools/` copied and counted only
  rc=1 as a kill. The logged run is the valid one. {#obs-invalid-first-run}
- Nothing touched a live store, `~/.refmatrix`, a live socket or `~/claude_tools/refmatrix`.
  `HOME` was redirected for the tree walk. The probe daemons ran on `/tmp/rmxs-*` mkdtemp roots.
  {#obs-readonly}
- `IMPRESSIONS.md` is 276 lines against a 50-line rule. Consolidating it is out of scope for this
  run. {#obs-impressions}

## Verdict {#verdict}

**DIRTY: 5 findings (0 BULLSHIT, 4 SKETCHY, 1 MEH). Plan-3 may NOT flip to `completed`.**

All six r7 findings are closed in behaviour on master. #b-1 and #b-2 were checked on real
sockets with no patching of the collaborator: promote takes 10.0 s where r7 measured 180.2 s,
and canon find, where and locate all name an unreadable store. But r8's merge went in with a
red test and a summary claiming a fix that bug-069 delivered later. Three of the closures fail
no test when reverted. The global legs still call "not running" "timed out". Task 3.4, which
plan-3 needs before closing, is missing from the plan and its spec does not describe the
surface it gates.

rel: contradicts -> [[plan-3-verbs-parity#execution]]
