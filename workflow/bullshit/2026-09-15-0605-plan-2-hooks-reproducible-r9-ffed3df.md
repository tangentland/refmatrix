---
gmd: "0.1"
id: bsd-plan2-hooks-reproducible-r9-ffed3df
title: "plan-2-hooks-reproducible rounds 8-9: the partition probe now answers from the replica for real (SessionStart 0.22 s / 10 rows under a held writer, four of my mutations kill their tests) and r7's socket-timeout leak is fixed on a live socket — but the rerank leg is STILL dead on the deployed hook (0 of 7 runs at 05:48-06:02), the capped pool costs the shared worker 3.7-14.1 s under ordinary load against the 1.7-2.8 s measured in the quiet minute after a fleet relaunch, and every prompt now pays the full 5 s budget to return exactly the rows --no-rerank returns in 0.79 s"
tags: [bsd, findings, plan-2, hooks, rerank, re-review]
severity: BULLSHIT
plan: plan-2-hooks-reproducible
task: task-2.1-plan-2-hooks-reproducible, task-2.2-plan-2-hooks-reproducible, task-2.3-plan-2-hooks-reproducible
metadata:
  node_type: bsd-report
  commit_range: f170a4c..ffed3df
  round: 9
---

# ch-bsd findings — plan-2-hooks-reproducible rounds 8-9 (f170a4c..ffed3df) {#root}

**Commits audited:** 7507584 + 3734e7f (the replica-first partition probe and the held-writer fixture, plan-2 round 9), the plan-2 slice of 26404fe + f5f0590 (`collect_rerank_docs(doc_chars=)`, `RERANK_DOC_CHARS`), with round 8 read as prior context (d576a81 the socket-timeout restore, e4ea1ad the pool multiplier — both before `f170a4c` and verified here because the task named them).
**Date:** 2026-09-15
**Author:** Todd Holley / Fable 5.1 / orchestrator
**Files changed (plan-2 surfaces):** `src/refmatrix/cli.py`, `verbs.py`, `search.py`, `reranker.py`, `modelsrv.py`; `tests/test_plan2_remedy_r7.py` (new), `test_plan2_remedy.py`, `test_plan2_remedy_r6.py`; plan Q10/Q11, bug-017/018/019/024, todo G13/G14, mock registry.
**Deployed:** `~/refmatrix` at ffed3df; `~/bin/rmx version -v` → 0.69.1, code `/Users/tholley/refmatrix/src/refmatrix/__init__.py`. Fleet 8/8 v0.69.1, hub pid 13847 with exactly two shared model workers (13863 embed, 14222 rerank). Snapshot lag at probe time 3 s.
**Tests:** `workflow/review-output/pytest-bsd-plan2-r9-ffed3df.log` — 65 passed (`test_plan2_remedy_r7`, `_r6`, `test_plan2_remedy`, `test_hooks_reproducible`). My mutations, each with `PYTHONDONTWRITEBYTECODE=1` and the tree restored after: A the replica-first block in `verbs.memory_partition` removed → `test_verb_memory_partition_reads_the_replica_under_a_held_writer` fails; B `doc_chars=RERANK_DOC_CHARS` dropped at the call → `test_replica_recall_leg_sends_a_capped_pool_to_the_reranker` fails; C the `finally` restore in `SharedWorkerClient.call` removed → both real-socket tests fail; D `RECALL_DAEMON_SLICE_S` removed → `test_session_start_hook_answers_from_the_replica_under_a_held_writer` fails; E the `text[:doc_chars]` slice removed → both cap tests fail (`pytest-bsd-plan2-r9-mutA..mutE.log`).
**Method:** the exact deployed hook argv with `RMX_INVOCATION_SOURCE=hook`, timed, seven runs spaced 8-10 s between 05:48 and 06:02 with the 1-minute load average recorded per run; a leg decomposition (`--no-rerank`, `--timeout 10`, `--scope project/global`); the hook's real capped pool sent straight to `models.sock` from the deployed venv; an in-process timer over every sub-step of `_replica_memory_recall`; the registered held-writer simulation (`_PingOnlyDaemon(seeded=True)` + snapshot) under the dev venv on a tmp root for the degrade message; read-only throughout — no `Store()` on the live slot, no signals, no dev-venv `rmx`.

rel: amends -> [[bsd-plan2-hooks-reproducible-r7-8d0a665]]
rel: evidence-for -> [[plan-2-hooks-reproducible]]

## Round-7 findings: status after remediation {#status}

| # | Finding | Status | Evidence |
|---|---------|--------|----------|
| #b-1 | the rerank leg was dead: the 1 s `info` probe's timeout stayed on the shared-worker socket and the `rerank` after it inherited 1 s | **the LEAK is closed; the LEG is still dead — reopened as [[#b-1]]** | Live on the real `models.sock` from the deployed venv: `info(timeout=1.0)` then `c._sock.gettimeout()` → **60.0**, the client's own value (`modelsrv.py` `call`, the `finally` branch). Mutation C kills both real-socket tests. But the deployed hook still reranks nothing: 0 of 7 runs, "rerank failed (TimeoutError: timed out)" every time — the seconds are now in the score call itself, [[#b-1]]. |
| #s-2 | third plan-2 registry gap | CLOSED (one thin residue → [[#m-5]]) | Six rows added: `_FakeModelSock`, the `_RR` + modelsrv/dense fakes, the `dm.call` "asked the daemon" sentinel, `hub.global_store_root` / `ensure_global_daemon`, `cli._root`, and the `_PingOnlyDaemon(seeded=True)` held-writer row rewritten for bug-017. |
| #m-3 | `ensure_global_daemon()` (bare ping + a 30 s spawn wait) outside every budget | CLOSED | `hub.global_call` runs it only when `retries > 0`; `test_budgeted_global_call_never_spawns_the_global_daemon` asserts both directions. |

## Round-9's own claims, checked {#round-9-claims}

| Claim (summary {#round-9}, plan Q10/Q11) | Verdict |
|---|---|
| the partition probe reads the replica first; SessionStart answers rows instead of `[]` under a held writer | **TRUE, reproduced.** Live SessionStart argv: 0.22 s / 0.23 s, 10 rows, empty stderr (twice), against `[]` + "partition_list did not answer" at 03:36. On the registered held-writer fixture the CLI probe answers in < 0.8 s without touching the daemon, and mutations A and D each kill a test. |
| `cached_replica` raises a typed `FileNotFoundError` on a bootstrap-window root and caches nothing; `--json` with no hits prints `[]` | TRUE (`search.py`, both `--json` empty branches in `cli.memory_recall`); `test_cached_replica_never_creates_a_catalog` covers the first. |
| the seeded held-writer simulation now HOLDS its writer (bug-017) | TRUE — mutation C of the remedy (the writer released) is reproduced by my mutation D's sibling: the fixture's held connection is what makes the legacy catalog unreadable as a replica. |
| Q11: the capped 10-doc pool costs the shared worker 1.7-2.8 s; "5 of 5 reranked in all three runs, no warnings" | **DOES NOT REPRODUCE — [[#b-1]].** Same code, same fleet, 10-24 minutes later: 0 of 7. |

## Findings {#findings}

### BULLSHIT: the rerank leg is still dead on the deployed hook — the capped pool costs the shared worker 3.7-14.1 s under ordinary workstation load against the 1.7-2.8 s measured in the quiet minute after the fleet relaunch, so every prompt pays the whole 5 s budget to return exactly the rows `--no-rerank` returns in 0.79 s, and the gap is parked in a todo row with no task spec behind it {#b-1}

**File:** `src/refmatrix/cli.py:9375-9395` (`_replica_memory_recall`: `rem = _l(30.0)`, `shared_reranker(timeout=rem, probe_timeout=min(rem, RERANK_PROBE_S))`, `collect_rerank_docs(..., doc_chars=RERANK_DOC_CHARS)`), `cli.py` `RERANK_DOC_CHARS = 700`, `src/refmatrix/reranker.py:188-244` (`doc_chars`), `:45-54` (`DEFAULT_POOL_MULT = 2`), `workflow/plans/plan-2-hooks-reproducible.md` Q11, `docs/architecture/todo.md` G13.
**What:** The deployed per-prompt argv, `RMX_INVOCATION_SOURCE=hook`, on the live store, spaced, with the 1-minute load average beside each run (load 3.5-5.8, driven by macOS `mediaanalysisd` / `mds_stores` / Firefox, not by this audit):

| time | runs | wall | reranked | stderr |
|---|---|---|---|---|
| 05:48 | 3 | 5.26 / 5.24 / 5.24 s | 0 of 5 each | `rerank failed (TimeoutError: timed out)` + `global rows omitted … daemon busy` |
| 05:59-06:02 | 4 | 5.27 / 5.23 / 5.24 / 5.26 s | 0 of 5 each | the same two lines, every run |

Leg decomposition on the same store: `--no-rerank --scope both --timeout 5` → **0.79 s**, 5 rows; `--timeout 10` (rerank on) → 5.57 s, 5 of 5 reranked; `--scope project --timeout 5` → 5.25 s, 0 reranked. So the rerank leg costs ~4.5-4.8 s and the whole budget buys nothing: the rows returned after a failed rerank are the same rows returned without it. In-process timers over the leg (deployed venv, replica read-only): imports 0.08 s, `shared_available` 0.00 s, replica open 0.04 s, `dense_recall` 0.67 s, `shared_reranker` probe 0.00 s, `collect_rerank_docs` 0.01 s with a pool of exactly 10 docs / 7000 chars / max 700 — and `apply_rerank` **TimeoutError at 4.00 s**, the client's whole remaining budget. The worker is healthy and the pool is capped as designed; the cost is simply not what Q11 says: the identical real pool sent straight to `models.sock` took **9.26 s**, then **14.08 s**, then **3.72 s** on three consecutive attempts, while a synthetic 10 × 700-char pool of repeated filler took 1.00-1.05 s and 10 × 2048 chars took 3.2-3.3 s. Real memory prose at 700 chars is the expensive case, and one serialized worker serves every hook of every session on the machine.
**Why it's bullshit:** Q7's stated acceptance ("wall ≤ budget + 0.6 s") passes at 5.23-5.27 s, which is exactly the shape my round-7 impressions named: the bound holds and the answer is dead ([[impression_bsd_cost_measured_idle]], [[impression_bsd_tests_bypass_wiring]]). `apply_rerank` on the hook path is unreachable in production under ordinary load — rule 1 — and the acceptance number that closed the round was taken at 05:38, in the minutes right after `relaunch-fleet` re-adopted the shared workers, on the quietest machine state of the night; ten minutes later the same command on the same code reranks nothing. The remedy is also a cheap fix under rule 10: the diagnosis (the pool is too expensive for the budget) was answered by shrinking the pool until one measurement fit, not by making the caller able to know the cost — and the leg it protects is the same leg round 7 found dead, so this is the second consecutive round in which the hook's rerank never runs. The remaining half is parked in `todo.md` G13 ("the worker should report its seconds-per-doc"; "the two per-prompt hooks race one serialized worker"), and no task spec under `workflow/plans/plan-2-hooks-reproducible-tasks/` — or under any plan's task dir — has acceptance criteria that close it: `rg -l "G13|seconds-per-doc|worker-reported cost" workflow/plans/*-tasks/` returns nothing. A gap whose only anchor is a todo row is an unanchored deferral (rule 9a). Meanwhile the user-visible cost is the thing plan 2 exists to remove: the per-prompt hook holds the turn 5.25 s on every prompt, where `--no-rerank` answers in 0.79 s.
**Evidence:** the seven timed runs above with per-run load averages; `--no-rerank` 0.79 s vs `--timeout 10` 5.57 s; the sub-step timers; the three direct `rerank` calls with the hook's own pool (9.26 / 14.08 / 3.72 s) beside the synthetic 1.00 s; `workflow/review-output/live10-hook-remeasure.log` (the 05:38 acceptance run: "10 docs -> 2.79s / 1.73s / 1.83s", hooks 4.58-5.02 s, 5 of 5 reranked) — its numbers are real and were taken 40 s after the last daemon in the fleet re-adopted the shared worker.
**Fix:** make the caller able to decide before it spends the budget — `info` returns the worker's EMA seconds-per-doc (or a queue depth), and the leg skips with a said reason when `docs × cost > remaining` instead of timing out; a deadline in the `rerank` frame so an abandoned request is dropped rather than left to starve the next caller. That is G13; it needs a task spec with acceptance criteria, not a todo row. Until it exists, the honest interim is `RMX_RERANK=0` on the per-prompt hook (the 0.79 s path) rather than a 5 s budget spent on a leg that does not complete. Whatever lands, the acceptance must be measured under ordinary load with a second and third run minutes apart, and must count `reranked` rows, not wall time.
**Pattern match:** YES — [[impression_bsd_cost_measured_idle]] (3rd sighting, and the first two are mine from rounds 6 and 7 of this same plan), [[impression_bsd_acceptance_in_the_quiet_window]], [[impression_bsd_registry_row_deferral]] (the "or a todo row" anchor).

rel: contradicts -> [[plan-2-hooks-reproducible#decisions-log]]
rel: contradicts -> [[claude#no-workarounds]]
rel: contradicts -> [[feedback_measure_the_path_users_run]]

### SKETCHY: the rerank spends the global leg's budget and then the hook blames the daemon — `--scope both` returned project-only rows in 7 of 7 runs, with a warning that names a daemon the command never asked {#s-2}

**File:** `src/refmatrix/cli.py:9375-9380` (the rerank takes `_l(30.0)`, i.e. the entire remaining budget), `cli.py` `_global_rows` (`timeout=_left(30.0)`, and `_left` raises once the budget is spent), `src/refmatrix/verbs.py` `memory_recall._left` (the message: "recall not confirmed within {timeout}s — daemon busy; the hook skipped this turn").
**What:** Every live run of the deployed per-prompt argv ends with `# rmx: warning: global rows omitted: recall not confirmed within 5s — daemon busy; the hook skipped this turn`, and every returned row carries `scope: project`. The global daemon (pid 16407, `~/.refmatrix`) was up and healthy throughout and was never contacted on those runs — the budget had already been spent by the rerank. The wording is wrong three ways: no daemon was busy, no daemon was asked, and the hook did not skip the turn (it printed five rows). With the rerank succeeding instead (`--timeout 10`, 5.57 s) the global leg still got nothing, because the rerank had taken 4.8 s of the 10 s.
**Why it's sketchy:** the hook's own argv asks for `--scope both`, so the global behaviour memories are part of the contract the plan is measuring; as deployed, that leg cannot run whenever the rerank runs, and the operator-facing explanation points at the wrong component — the same misattribution round 7 found in the "shared worker unavailable" warning. Not filed as BULLSHIT only because the global store's answer for these queries would have been empty anyway (its lexical top-50 for a prompt is `session/*`, which the hook filters), so no user-visible row is provably lost yet.
**Fix:** reserve the global leg's slice before handing the remainder to the rerank (`rem = _l(30.0) - GLOBAL_SLICE_S`), and word the omission after the cause: "global rows omitted: the budget was spent before this leg (rerank 4.8 s)" when the deadline was consumed locally, versus a genuine daemon answer failure.
**Pattern match:** YES — [[impression_bsd_quoted_line_sibling]] (a misattributing warning fixed in one place, alive in the next), [[impression_bsd_unread_diagnostic_field]] (a diagnostic that describes a state nobody measured).

rel: contradicts -> [[claude#no-silent-failures]]

### SKETCHY: the replica-first partition probe was applied to EVERY caller, so memory WRITE routing is now resolved from a lagging snapshot — the split-brain family this function exists to prevent {#s-3}

**File:** `src/refmatrix/verbs.py:224-267` (`memory_partition`: the replica block runs before `require_daemon` for every caller, regardless of `timeout`), callers `verbs.py:592` (`memory_add` → `{**payload, "partition": memory_partition(root)}`), `verbs.py:900`, `verbs.py:1120`, `src/refmatrix/mcp.py:97,113`.
**What:** Round 9's fix is right for the budgeted hook probe (the daemon-side `partition_list` takes the writer lock). It was not scoped to it. `verbs.memory_add` — the write path behind the MCP memory tool, the bus, and save-state — now takes its target partition from `catalog.read.duckdb`, a file the daemon regenerates by tmp+rename after write ops. The function's own docstring says it is "THE routing every memory verb must use — one handler skipping it caused the 0.21.1 / 0.25.x / 2026-09-06 split-brain family". A partition merge removes the legacy `memory-<project>` row from the writer; until the next snapshot, the replica still has it and every `memory_add` routes into the retired partition. Nothing bounds the snapshot's age here and no test covers a write caller (the three new tests all call `memory_partition` directly or through the read path). Observed lag at probe time: 3 s (`catalog.read.duckdb` and `catalog.B.duckdb` both 05:58:24), so the window is narrow today — it is the absence of a bound, not today's lag, that is the finding.
**Why it's sketchy:** a demotion of the authoritative source for write routing, made to fix a read-path stall, with the hazard the function was written to prevent left unmentioned in Q10.
**Fix:** one line — take the replica only when the caller is budgeted, which the signature already distinguishes: `if timeout is not None:` around the replica block (the hook probe passes a timeout; `memory_add` does not). Or compare `_snapshot_sig` mtime against a freshness bound and fall through to the daemon when stale. Plus one test: a write caller whose replica says `legacy` while the daemon says otherwise must follow the daemon.
**Pattern match:** YES — [[bsd-impressions#imp-one-rule-drops-exceptions]] (a rewrite that drops the special case the old ordering carried).

rel: contradicts -> [[claude#no-workarounds]]

### MEH: the degrade line contradicts itself and reports the 1.5 s slice as if it were the budget — on a 30 s PreCompact argv {#m-4}

**File:** `src/refmatrix/cli.py` (the `except (VerbBusyError, VerbAbsentError)` branch: `click.echo(f"# rmx: {e}; reading the replica")`), `src/refmatrix/verbs.py` `memory_recall._left` (the message text), `cli.py` `RECALL_DAEMON_SLICE_S = 1.5`.
**What:** On the registered held-writer simulation, both hook argvs print one line: `# rmx: recall not confirmed within 1.5s (daemon op memory_recent … did not answer within 1.49999s …) — daemon busy; the hook skipped this turn; reading the replica`, then return rows and exit 0. Two problems in one line: the hook did not skip the turn, and the "1.5 s" is the daemon slice, not the command's budget — the second argv was the PreCompact `--recent --since 1h --k 20 --timeout 30`, which an operator reading that line would believe had been given 1.5 s. The slice applies to every hook-mode invocation with a replica on disk, so the 30 s PreCompact budget r7 credited is a 1.5 s daemon slice followed by a replica read in practice.
**Fix:** in the degrade branch, print the outcome rather than re-printing the verb's exception verbatim ("daemon did not answer within the 1.5 s hook slice of a 30 s budget; reading the replica"), and drop "the hook skipped this turn" from the message when a replica read follows. Round 4 of plan 3 (#m-6) fixed the same contradiction one degrade path over.

### MEH: `reranker.rerank_available` is patched in the new test file and no registry row names it there — fourth plan-2 round with a registry residue, on a round that added six rows {#m-5}

**File:** `tests/test_plan2_remedy_r7.py:100` vs `workflow/test_mock_registry.md:54` (the `rerank_enabled` / `rerank_available` row names `tests/test_plan2_remedy_r6.py` only).
**What:** Six new rows landed this round and they cover everything else in the file. This one patch is not named.
**Fix:** add the file to row 54. Four words.

## Deferral sweep {#deferrals}

Hard and soft patterns over every added line of the plan-2 commits in `src/`: none. Two soft hits in the range belong to plan 4 (`launchctl.py` "Best-effort: a restart is not a wedge", `hub.py` "unknown is said, not assumed fine") and are that auditor's. The unanchored deferral in this round is not a comment but the plan's own Q11 "Open (todo G13)" — treated in [[#b-1]]: no task spec under any `workflow/plans/*-tasks/` covers the worker-reported cost or the two-hooks-one-worker race.

## Verdict {#verdict}

**DIRTY — 5 findings (1 BULLSHIT, 2 SKETCHY, 2 MEH).**

Round 9's headline fix is real and I reproduced it: the partition probe reads the lock-free replica, the SessionStart hook answers 10 rows in 0.22 s where it answered `[]` under a held writer at 03:36, the held-writer fixture now holds its writer the way the daemon holds its slot, and four of my five mutations kill a test apiece (the fifth kills two). Round 8's socket-timeout restore is proven on a real socket from the deployed venv — `info(timeout=1)` leaves the client at 60.0 — and the budgeted `global_call` no longer spawns a daemon.

**May plan-2 flip to `completed`? No.** The leg that round 7 blocked on is still dead as deployed: seven runs of the exact hook argv between 05:48 and 06:02, load 3.5-5.8, reranked 0 of 5 every time, each spending the full 5 s budget to return precisely what `--no-rerank` returns in 0.79 s. The capped pool is not 1.7-2.8 s — it is 3.7-14.1 s at the worker for the hook's own docs, and the acceptance run that closed the round was taken in the quietest minute of the night, 40 s after the last daemon re-adopted the shared worker. Q7's wall-clock acceptance passes while the answer is dead, which is the criterion's flaw as much as the code's. Close it by making the worker's cost knowable before the caller commits its budget (G13, which needs a task spec), reserve the global leg's slice, scope the replica-first probe to budgeted callers, and re-measure on a loaded machine counting `reranked` rows — twice, minutes apart.

rel: evidence-for -> [[feedback_measure_the_path_users_run]]
rel: contradicts -> [[plan-2-hooks-reproducible#decisions-log]]
