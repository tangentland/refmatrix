---
gmd: "0.1"
id: bsd-plan3-verbs-parity-r9-1acadd2
title: "ch-bsd findings — plan-3 verbs parity r9 (tasks 3.4 + 3.5, c287f67..1acadd2): all five r8 findings closed in behaviour; the 50 'verb-it' paths are an unanchored deferral; 'one classifier' leaves four sites wording transport errors themselves; the global spawn overruns promote's 10 s by up to W+5 s (25.2 s measured); three #s-2 closures fail no test when reverted"
tags: [bsd, findings, plan-3, verbs, cli, search, task-3.4, task-3.5, remedy-r9]
severity: BULLSHIT
plan: plan-3-verbs-parity
task: task-3.4-internal-cli-allowlist, task-3.5-r8-remedy
metadata:
  node_type: bsd-report
  commit: 1acadd2
  range: "c287f67..1acadd2 = 0965546 (3.4/3.5 specs + RED), 5fcc3db / 6f6a474 / 46ebde8 (GREEN 3.4 + 3.5), 917ddc5 (3.5 amendment AC-12..16 + test fixes), b73fa29 / 1acadd2 (classify_transport_error)"
  head_at_audit: 1acadd2
  tree: "/Volumes/littlebig/refmatrix-plan3-close (branch plan3-close-w1). Tests, probes and mutations ran in three scratch clones (head = 1acadd2, base = c287f67, mut = 1acadd2) under the session scratchpad; no src/tests edit in the clone"
  written: "2026-10-19T17:44:59-0700"
  verdict: DIRTY
  findings: 6
---

# ch-bsd findings — plan-3 r9: tasks 3.4 and 3.5 {#root}

**Commit:** 1acadd2 (range c287f67..1acadd2, 7 commits)
**Date:** 2026-10-19
**Author:** Todd Holley / Opus 5.5 / ch-test-engineer + ch-implementer (orchestrated); auditor Opus 5.5
**Files changed:** 17 (src: `cli.py`, `verbs.py`, `search.py`, `hub.py`)

rel: amends -> [[bsd-plan3-verbs-parity-r8-d4bf001]]
rel: evidence-for -> [[plan-3-verbs-parity]]
rel: evidence-for -> [[task-3.4-internal-cli-allowlist]]
rel: evidence-for -> [[task-3.5-r8-remedy]]
rel: evidence-for -> [[impl-task-3.4-internal-cli-allowlist]]
rel: evidence-for -> [[impl-task-3.5-r8-remedy]]

## Method {#method}

Every run used `/Users/tholley/claude_tools/refmatrix/.venv-eval/bin/python` with an absolute
`PYTHONPATH=<scratch tree>/src`, and each probe asserts `refmatrix.__file__` resolves inside the
tree under test. Daemons were real (`Store.init` + `spawn_daemon_subprocess`) on `mkdtemp(dir="/tmp")`
roots (`/tmp/rmxs-*`); `HOME` and `RMX_HOME` pointed under each probe's own root, so the global
store was a throwaway. Nothing touched a live store, `~/.refmatrix`, a live socket or
`~/claude_tools/refmatrix`; no `rmxs-*` process was left behind (checked with `ps` at the end).

- **Targeted suite at 1acadd2:** 21 files (the 3.5 file, `test_verb_parity`, plan-3 r2-r7,
  `test_plan3_remedy`, `test_lance_drop_failures_loud`, `test_mcp_parity`, `test_verbs_migrated`,
  `test_locate`, `test_surface_parity`, `test_ui_server`, `test_memory_bulk_forget`,
  `test_memory_dedup`, `test_memory_reclassify`, `test_memory`, `test_global_memory`,
  `test_memory_tags_taxonomy`): **289 passed in 440 s**.
- **Write probe** (`probe_writes.py`): the seven routed writes plus `memory list`, each as a real
  `python -m refmatrix.cli` subprocess, in three daemon states (up / absent / held = the real
  daemon SIGSTOPped), on head AND base.
- **Global probe** (`probe_global.py`): `memory promote` / `memory add --global` /
  `federated_where` against a cold, can't-start (110-char `RMX_HOME`), held (SIGSTOPped) and
  slow-launcher global store, on head and base. The slow launcher is an environment fault: a
  `sitecustomize.py` on the launcher's `PYTHONPATH` that sleeps N s only in the
  `rmx daemon start` interpreter `spawn_daemon_subprocess` runs. No src was touched.
- **Timeout probe** (`probe_bulk.py`): a PASS-THROUGH `sitecustomize` recorder of `daemon.call`
  (op, timeout, retries) inside the real CLI process.
- **Mutations:** 20 mutants in the `mut` clone, each reverted with `git checkout -- src` plus a
  `__pycache__` purge, and the clone confirmed clean after every one. A kill is rc=1 with a named
  FAILED test. Survivors were re-run against a 14-file, 221-test plan-3 set.

Scratch evidence (not committed): `pytest-r9-head.log`, `pw-{head,base}-{up,absent,held}.json`,
`pg-*.json`, `mutations-r9.log`, `mutations-r9-r8survivors.log`, `mutations-r9-wide.log` under the
session scratchpad `r9/`. {#method-body}

## Round-8 findings, verified {#r8-status}

- **#s-1 CLOSED in behaviour and in tests.** M4 (promote global write at a fixed 30 s) is killed by
  `test_promote_is_bounded_on_the_global_write_too` (34 s), as is an unbounded `timeout=None`
  variant (MP). M8 is killed by the now-unconditional r7 canon test, M10 by
  `test_locate_reports_the_keyword_leg_on_its_own`, and M12 by
  `test_the_omnibox_zero_hit_branch_says_which_stores_were_skipped`. {#v-s1}
- **#s-2 CLOSED in behaviour; three of its closures are unpinned, see [[#s-3]].** Real daemons,
  head vs base:

  | case | base c287f67 | head 1acadd2 |
  |------|--------------|--------------|
  | cold global, `memory promote` | 0.26 s, exit 1, `[Errno 2] No such file or directory` | **0.61 s, exit 0**, global daemon started, row readable in 0.42 s |
  | held global (SIGSTOPped daemon) | 10.22 s, `global store memory_add failed: timed out` | **0.78 s**, `global store daemon busy pid=… (alive, not answering …)` |
  | can't start (110-char global root) | 0.26 s, raw `AF_UNIX path too long` | **10.42 s**, `global store daemon not running … could not be started (spawn failed: …)`, no `Errno` |
  | `federated_where`, refused global socket | `did not answer within 3s (ConnectionRefusedError)` | `global store: daemon not running … (ConnectionRefusedError)` |
  | `memory add --global`, cold | 0.63 s, exit 0 | 0.61 s, exit 0 (unchanged) |

  {#v-s2}
- **#s-3 CLOSED.** `test_memory_get_degree_renders_the_bundle_from_a_real_daemon` passes on a real
  spawned daemon. The `test_plan3_remedy_r6.py` registry row names it as the graduation. {#v-s3}
- **#s-4 CLOSED as specified.** The walk classifies 195 paths (26 twins + 15 + 8 + 6 + 140).
  The seven memory writes call `verbs.memory`. With the daemon **up**, 13/13 steps are
  byte-identical to base (rc, stdout, stderr). With it **absent**, 13/13 are byte-identical
  (in-process fallback). With it **held**, every write is a typed busy error in 0.7-2.3 s and none
  opens the slot. bulk-forget's write carries **600 s end to end**: the pass-through recorder in
  the real CLI process logged `memory_bulk_forget timeout=120.0 dry_run=True`, then
  `timeout=600.0 dry_run=False`, on both trees. The spec's own build list is where [[#b-1]]
  comes from. {#v-s4}
- **#m-1 CLOSED.** `remedy-plan-3-r8.md` has the amendment line pointing at `6675d17` / bug-069,
  and `cli.py:4364` reads "one of three consumers". {#v-m1}

## Findings {#findings}

### BULLSHIT: the 50 `verb-it` paths are an unanchored deferral — "owes a verb" with no task, plan or registry row {#b-1}

**File:** `src/refmatrix/verbs.py:1612-1645` (the comment "Each owes a verb; MCP agents cannot
reach them" and eight `verb-it` families); `workflow/plans/plan-3-verbs-parity-tasks/task-3.4-internal-cli-allowlist.md#r5-legacy`
("`verb-it` | agent-facing; owes a verb (the decision is \"verb it\")");
`workflow/deferral_registry.md` (no row).

**What:** 50 of the 140 LEGACY_UNPAIRED paths are classified `verb-it`. These include
`neighbors`, `recall`, `canon find`, `protect`/`noise`/`forget`, eleven `focus` navigation
commands, `session recall` and `refine *`. The code states that each one owes a verb. `rg -i
"verb-it|LEGACY_UNPAIRED"` finds no deferral_registry row, no plan and no task spec that schedules
any of those verbs. The only references are the 3.4 spec and plan-3's Task Breakdown row. Row 47
was marked RESOLVED, and it covered only the eight internal paths.

**Why it's bullshit:** Rule 9a says that a deferral naming no concrete, scheduled task is a
parking lot. The shrink-only pin stops the set from GROWING. It does not schedule any of it to
shrink. Plan-3's thesis is "every capability an agent can call is a verb first" (PROJECT_PROFILE
#constraints), and it would close with 50 agent-facing capabilities written down as owed and
nobody committed to build them. I own part of this: my r8 `#t34-build` item 5 asked for a
decision per path and did not require an anchor for the `verb-it` decision.

**Evidence:** `verbs.LEGACY_UNPAIRED` category counts at 1acadd2: `verb-it 50, operator 43,
maintenance 27, hook 11, harness 9`. `rg -n -i "verb-it|LEGACY_UNPAIRED" workflow/deferral_registry.md
workflow/plan-of-plans.md workflow/plans/*.md docs/architecture/todo.md` returns only the
deferral row 47 text (about INTERNAL_CLI) and plan-3:102.

**Fix (docs only, about 30 minutes):** add a deferral_registry row (`scaffold-no-caller` or
similar) for the 50 `verb-it` paths, grouped by the eight families. Point it at a concrete task
spec, either a follow-on plan or `task-3.6`, with acceptance criteria per family (a verb, a
`CLI_MAP` twin, and the path leaving LEGACY). Then point the `verb-it` comment at that row. The
other way to close it is to re-decide a family as `internal`, with the user's words, the way row
47 was decided.

**Pattern match:** YES. This is rule 9a's "an open plan with no task for the deferred item is a
parking lot".

rel: contradicts -> [[project-profile#constraints]]

### SKETCHY: "THE one classifier" is not one — four store-daemon transport sites still word their own errors, one in the same function as the fixed global leg {#s-1}

**File:** `src/refmatrix/search.py:171-174` (`_where_one_project` memory leg:
`memory_search did not answer within 3s ({type})` for any exception);
`src/refmatrix/search.py:313-314` (`federated_query`: `daemon busy: query did not answer within
20s`); `src/refmatrix/verbs.py:372-378` (`memory_partition`: `daemon busy … partition_list did not
answer within`); `src/refmatrix/cli.py:7064` and `:7227` (`derive log` / `derive status`: `daemon
did not answer ({type})`). The claim is in `task-3.5-r8-remedy.md#amend-reqs` ("the ONLY place a
transport exception becomes words") and in `impl-task-3.5-r8-remedy#amend`.

**What:** `classify_transport_error` has three callers: `_call`, `global_write` and
`search._global_leg_reason`. The PROJECT memory leg of `federated_where` is twenty lines above the
global leg that was fixed, and it still calls every exception a timeout. Probe
(`probe_sibling.py`, a real bound-then-closed socket file handed to the fan-out):

- where project leg: `memory_search did not answer within 3s (ConnectionRefusedError)`
- `federated_query`: `daemon busy: query did not answer within 20s (ConnectionRefusedError)`
- `verbs._call` on the same root: `VerbAbsentError daemon not running …`

That is r8 probe P4b's lie, one leg over.

**Why SKETCHY, not escalated:** both fan-outs pre-filter with `_live_roots`, and
`memory_partition` runs after `require_daemon`. These sites therefore see absent or refused only
in the race where a daemon dies after a positive liveness probe. The global leg had no such
filter. Nothing opens a slot. But the user asked whether any site still words transport errors
itself, and the spec says none does.

**Fix:** route the three search/verbs sites through `verbs.classify_transport_error(e, op=…,
root=…, timeout=…)`, about 3 lines each. The derive degrade sites can keep falling through to the
replica but should word the reason through the classifier. `verbs._hub_rpc:1393-1395` is the
hub's transport, not a store daemon, and is out of scope. Then make the docstring claim true, or
narrow it to the call sites it covers.

**Pattern match:** YES. This is [[bsd-impressions#imp-quoted-line-sibling]]: the fix landed on the
quoted leg, and the sibling in the same function kept the wording.

rel: contradicts -> [[task-3.5-r8-remedy#amend-reqs]]

### SKETCHY: `global_write`'s spawn is NOT inside the budget — a slow launcher costs up to W + 5 s more; 25.2 s measured against promote's 10 s {#s-2}

**File:** `src/refmatrix/daemon.py:6796` (`subprocess.run(…, timeout=wait_for_ready + 5.0)`) and
`:6810` (`deadline = time.time() + wait_for_ready`, a FRESH window after the launcher returns or
times out). Reached from `verbs.py:312` (`ensure_global_daemon(wait_for_ready=wait, …)`). The
summary is `workflow/implementation_summaries/task-3.5-r8-remedy.md:83-84` ("can overrun
promote's budget by up to 5 s").

**What:** `spawn_daemon_subprocess` uses two windows. The launcher is allowed `W + 5` s. After it
exits 0 or is killed, the readiness poll starts a new `W`. The worst case is therefore
`2W + 5`, not `W + 5`. Probe with the slow-launcher fault (real promote, real cold global root):

| launcher delay | elapsed | result |
|----------------|---------|--------|
| 20 s (> W + 5) | **25.24 s** | `not running … could not be started (… did not start … within 10s)` — the message says 10 s at 25 s |
| 12 s | **12.65 s** | the global daemon came UP, the write was not sent: `not confirmed within 9.9s — … busy` |

**Why SKETCHY:** promote promises 10 s, and r7/r8 pinned this exact budget to the decimal. The
fault needs a launcher that takes longer than the remaining budget, which happens under load
(r-memory: 16 torch processes once made the fleet 10× slower). The summary names the hole and
states it at less than a third of its size.

**Fix:** in `spawn_daemon_subprocess`, set one deadline at entry. The launcher gets `timeout =
remaining`, and the poll runs until the SAME deadline. That is about 5 lines, and bug-129 r6's
launcher-window fix is its sibling. Pin it with a slow-launcher test. The `sitecustomize` fault
used here needs no src seam.

**Pattern match:** YES. This is the partial-bound family ([[bsd-impressions#imp-consolidated-0914c]]
"partial bounds placed where the diagnosis pointed rather than on every leg").

rel: contradicts -> [[task-3.5-r8-remedy#req-s2]]

### SKETCHY: three #s-2 closures hold in behaviour and fail no test when reverted (ME, MD, ML); `_memory_write`'s "ONLY absent" rule is pinned by nothing in it (MF) {#s-3}

**File:** `src/refmatrix/verbs.py:304-307` (busy global is never spawned over), `:312` (spawn
readiness budget), `:325-331` (global write through the classifier);
`src/refmatrix/cli.py:11240-11266` (`_memory_write`); `src/refmatrix/cli.py` `memory_score`
`local()` (explain components). Tests: `tests/test_task3_5_r8_remedy.py:200-213` (spawn patched to
raise instantly), `:238-252` (`_PingOnlyDaemon` answers ping, so it is UP and the busy branch is
never taken).

| mutant | change | 221-test plan-3 set | behaviour under the mutant (real daemons) |
|--------|--------|---------------------|-------------------------------------------|
| ME | drop `if st.get("busy")` in `global_write` | **SURVIVES** | held global → spawned over → `IOException: Could not set lock on file … catalog.A.duckdb: Conflicting lock is held` from the in-process bootstrap, reported as "not running" (2.77 s). That is the 2026-09-14 lock-crash shape |
| MD | spawn readiness back to the 30 s default | **SURVIVES** | can't-start promote takes **30.45 s** (head 10.42 s) |
| ML | `global_write` raises a raw `VerbError` (classifier bypassed) | **SURVIVES** | the absent/busy/too-long typing of the global write is unpinned |
| MF | `_memory_write` falls back to `local()` on ANY `VerbError` | **SURVIVES** (171 tests, 10 files, including the memory CLI files) | still safe: `_store()`'s own control point raises busy (`… — writes go through the daemon`). Defence in depth holds; `_memory_write`'s rule is unpinned |
| MO | `memory score --explain` local branch drops components | **SURVIVES** | probe-verified correct at head (absent mode byte-identical to base) |

Killed (14): MA, MB, MC, MG, MH, MI, MJ, MK, MM, MN, MP, M4', plus the r8 M8, M10 and M12.

**Why it matters:** this is r8 #s-1's family in its second consecutive round: closures that are
correct and unguarded. ME is the important one. #req-s2 says "a held global store is not spawned
over", and the only held-global test uses a double that answers ping, so it never reaches the
branch.

**Fix:** (a) a held-global test on a REAL SIGSTOPped global daemon (pid alive, socket present, no
answer) that asserts busy, no spawn and no lock error, which kills ME. (b) a can't-start test on a
real over-long `RMX_HOME` (no spawn patch) with `elapsed < budget + 3`, which kills MD. (c) a
global-write transport test (the daemon goes away between the probe and the write), which kills
ML. (d) a `_memory_write` test on a SIGSTOPped project daemon that asserts `local` is never
called, which kills MF.

**Pattern match:** YES. This is [[bsd-plan3-verbs-parity-r8-d4bf001#s-1]] again.

rel: contradicts -> [[task-3.5-r8-remedy#req-s2]]

### SKETCHY (pre-existing on a plan-3 contract): `rmx memory add` with no daemon and no read replica crashes instead of bootstrapping {#s-4}

**File:** `src/refmatrix/cli.py:11377-11385` (`memory_add`: "a fresh store has NO daemon and the
first memory must still land", citing ch-bsd plan-3 r2 #b-2).

**What:** on a store with no daemon and no `catalog.read.duckdb`, `rmx memory add z1 -c b` exits 1
with a traceback: `StaleDuckDBInstanceError: …/catalog.duckdb: another connection in this process
still holds this path … Binder Error: Unique file handle conflict: Cannot attach "catalog" … is
already attached by database "rmx_ro"`. Reproduced at **base c287f67 and head 1acadd2**, on a
short root and a 100-char root, and after `rmx daemon stop` on a store whose daemon had never
snapshotted. The seven writes routed by 3.4 do NOT have this problem: they all succeed in-process
on the same never-daemoned store, on both trees (`probe_fresh.py`). It is not a regression from
this range.

**Why SKETCHY:** the contract is plan-3's own and it is false. The in-process connection name
`rmx_ro` points at a read-only attach of the writer file earlier in the same process. That is a
hypothesis only; the mechanism was not measured. Plan-3 should not close on a bootstrap promise
it does not keep.

**Fix:** a bug_registry row now (none matches `rmx_ro` / bootstrap). Then measure the mechanism
and fix it, either inside plan-3 or as a registered bug that plan-3's closure explicitly carries.

rel: contradicts -> [[plan-3-verbs-parity#decisions-log]]

### MEH: four LEGACY reasons are false when checked against the code {#m-1}

**File:** `src/refmatrix/verbs.py:1641-1653`.

- `focus record` is filed `hook` ("invoked by a generated Claude Code hook"), but no generated
  hook calls it. Every focus hook runs `rmx focus hook --event …` (`hooks.py:131-157`), and `rg
  "focus record"` over `hooks.py` / `search_hooks.py` / `.claude/settings.json` finds 0.
- `install-hooks` is filed `hook`. No hook runs it; it is the operator's install command.
- `memory sync-disk` is filed as "the memory bridge, run by SessionStart and save-state". The
  SessionStart hook runs `ingest-gmd` (`hooks.py:285`), and save-state calls the bridge in-process
  (`handoff.py:407`). sync-disk is a by-hand and p20 guardrail-compiler command.
- `curator scan` is in the `verb-it` family "the gmd-curator agent drives". It is run by
  `scheduler.py:126`. The gmd-curator template calls only `curator status` / `curator drain`, and
  no `refine` subcommand.

Spot-checks the user asked for that DO hold: `bus sub` → `operator` (it streams to a terminal;
`rmx_bus_read` is the agent verb); `grep` → `hook` (reached through the PreToolUse rewrite);
`curator drain` (the template calls it). No LEGACY path's callback calls a capability verb
(AST scan for `verbs.<fn>(` in each callback; the only hits are `require_daemon`).

**Fix:** re-file `focus record` / `install-hooks` / `memory sync-disk` (`harness` / `operator` /
`maintenance`) and `curator scan` (`maintenance`), and reword the curator family's reason. The
category is the decision, so a wrong reason is a wrong decision record.

## Observations (not findings) {#observations}

- **The path-too-long decision is right, and production barely reaches it.** `_call` and
  `global_write` both classify with the pid-aware `daemon_status` before dialling. On a too-long
  root with no daemon, `require_daemon` says ABSENT (ping cannot connect, no pid) and the
  in-process fallback runs. A hung daemon with a live pid is BUSY. The classifier's too-long
  branch is reached only when status says up and the dial then fails. That is how the amendment's
  motivating case arose, from a test that patched `ping` to True. Keeping it non-absent is the
  conservative choice, and it costs nothing. {#obs-too-long}
- The can't-start error carries the launcher's last 2,000 bytes of stderr: a 30-line traceback
  ending `daemon did not start within 9.9s (see …/rmxd.log)`. The real cause (`AF_UNIX path too
  long`) is in rmxd.log, not in the message. It is readable, but noisy. {#obs-cantstart-noise}
- The busy error lost its suffix `— writes go through the daemon` (`_store`'s words) because the
  verb now says busy first. The type and the meaning are unchanged. {#obs-busy-suffix}
- Pre-existing and identical on base: after in-process (absent) writes, `memory list` reads the
  stale replica. `federated_where` lists the global store twice when its socket is refused, once
  from `_live_roots` (`/private/tmp/…`) and once from the global leg (`/tmp/…`). {#obs-preexisting}
- Deferral sweep over the added src lines (both families): 4 hits. All are innocent; they cite
  row 47 or describe the defect being fixed. The [[#b-1]] deferral is in the `verb-it` comment's
  meaning ("owes a verb"), not in its wording. {#obs-deferrals}
- `IMPRESSIONS.md` is about 280 lines against the 50-line rule, and consolidation is out of scope
  again. {#obs-impressions}

## Verdict {#verdict}

**DIRTY: 6 findings (1 BULLSHIT, 4 SKETCHY, 1 MEH). Plan-3 may NOT flip to `completed`.**

All five r8 findings are closed in behaviour on real daemons. Cold promote went from Errno 2 in
0.26 s to started-and-written in 0.61 s. Held global went from 10.22 s to a typed busy in 0.78 s.
The seven routed writes are byte-identical to base, up and absent, and typed busy when held.
bulk-forget's 600 s reaches the transport. r8's four survivors are now killed. What blocks
closure:

1. The 50 `verb-it` decisions have no task behind them ([[#b-1]]).
2. The spawn path breaks promote's 10 s by up to W + 5 s ([[#s-2]]).
3. Three #s-2 closures are unpinned ([[#s-3]]). ME guards against a lock-conflict spawn.
4. The classifier is shared by three of seven sites ([[#s-1]]).
5. Plan-3's own `memory add` bootstrap promise is broken, pre-existing ([[#s-4]]).

Items 1 and 5 are mostly records. Item 2 is about 5 lines of code. Items 3 and 4 are about 4
tests and 9 lines.

rel: contradicts -> [[plan-3-verbs-parity#execution]]
