---
gmd: "0.1"
id: bsd-plan6-deferrals-docs-benchmark-r1-e0b7df6
title: "plan-6 first-pass audit: the plan's own resolved Q1 was reversed on three false facts, and task 6.4's one measurable requirement is disproved by one grep"
severity: BULLSHIT
plan: plan-6-deferrals-docs-benchmark
task: "6.1, 6.2, 6.3, 6.4, 6.5"
tags: [bsd, audit, plan-6, deferrals, docs, benchmark]
---

# ch-bsd findings — plan-6 (deferrals / generated docs / benchmark artifact / mock registry / bug-008) {#root}

**Audited tree:** `e0b7df6` on `master` (dev tree); deployed build 0.73.0 at `7e76610`
**Written:** 2026-10-01T16:29-0700 (audit ran 11:45-16:29 local; the filename, this line and
`last_run.log` all name the time the artifact was COMPLETED. The body was drafted at 12:26 and held open
until the third full-suite attempt returned at 12:57 — see [[#suite]]. Per ch-bsd r4 #m-1-r4, one value, no
override on the commit date.)
**Round:** r1 — FIRST PASS. plan-6 has never been through this gate.
**Plan:** `workflow/plans/plan-6-deferrals-docs-benchmark.md` (`metadata.status: in-progress`; all five task specs read `status: complete`)
**Authors in range:** Todd Holley / Fable 5.1 (tasks 6.2, 6.3) and Todd Holley / Opus 5 (1M) (tasks 6.1, 6.4, 6.5) / orchestrator
**Commits examined:** `2e65d98`, `1aedb41` (6.2) · `6e5d534`, `098774a` (6.3) · `33bdda4`, `f926768` (6.5) · `1f65b0d`, `8efef73` (6.1) · `89b179a`, `9a3b5d8` (6.4 / bug-034) · `8469632` (6.5 anchor)

rel: evidence-for -> [[plan-6-deferrals-docs-benchmark]]
rel: derives-from -> [[bsd-0661-e2e-memory-bridge]]

## Ancestry and build checks {#ancestry}

Every commit above is an ancestor of `master` (`git merge-base --is-ancestor` → true for 11 of 12).
The single exception is **`c1f9c03` "test(plan-6 6.1): RED — no stale deferral phrases in src/"**, which
lives only on the abandoned branch `task-6.1-plan-6-deferrals-docs-benchmark`; the work shipped instead
through the branch `task-6.1-deferrals` merged at `8efef73`, and `tests/test_deferrals_clean.py` IS on
master. So the bug-058 shape (a recorded fix never merged) does **not** repeat here — noted because it
was the trap I was asked to check. {#ancestry-ok}

The build claim checks out too: `pyproject.toml:7` and `src/refmatrix/__init__.py:2` both read `0.73.0`,
and `rmx version -v` reports `0.73.0` from `/Users/tholley/refmatrix/src/refmatrix/__init__.py` — so the
live verification below was taken on the deployed build, not on `[UNVERIFIED]` code (bug-055's shape). {#build-ok}

## Per-task verdicts {#task-verdicts}

| Task | Requirement | Verdict | Findings |
|------|-------------|---------|----------|
| 6.1 | banned-phrase grep empty; suite green; deferral registry linted | **PARTIAL** | [[#s-3]], and [[#b-1]] straddles it |
| 6.2 | both doc sections equal their render | **PASS** (mutation-proven) | — |
| 6.3 | README's figure exists in a committed `metrics.json` | **PASS** (mutation-proven) | [[#m-3]] |
| 6.4 | full suite 0 failures; registry lists **every** file that monkeypatches an external boundary | **FAIL** | [[#b-2]], [[#s-2]] |
| 6.5 | rewriter names no tree; foreign-tree refusal; `--check` clean after a deploy | **PASS — and now verified live** | [[#s-1]], [[#m-1]] |

## Findings {#findings}

### BULLSHIT: plan-6 resolved Q1 as "delete `duckdb_view.py`", then un-resolved it on a re-check whose three stated facts are all false {#b-1}

**File:** `src/refmatrix/duckdb_view.py:1-7`, `src/refmatrix/store.py:713-717` and `:1753-1769`,
`workflow/plans/plan-6-deferrals-docs-benchmark.md#q1` / `#decisions-log`,
`workflow/plans/plan-6-deferrals-docs-benchmark-tasks/task-6.1-plan-6-deferrals-docs-benchmark.md` (the
"Correction to this spec" paragraph)

**What:** The originating finding this whole plan exists to close said of `duckdb_view.py`: *"the facade is
reachable only via an env flag that no production path sets (only `tests/test_duckdb_read_routing.py` sets
it). 133 lines of dead-in-production code kept alive by two tests"*
(`workflow/bullshit/2026-09-14-1900-e2e-audit-memory-bridge-f56a365.md:74`). plan-6 opened Q1, answered it
**RESOLVED — "Delete. The store is DuckDB-native; an env-flag facade nobody sets is a second path,"** and
recorded that in the Decisions Log. Task 6.1 then shipped a paragraph headed **"Correction to this spec:
`src/refmatrix/duckdb_view.py` is NOT deleted"** and the module stayed. Q1's `**Status:** RESOLVED` and the
Decisions Log row were never amended, so the plan now says "delete" and "do not delete" in the same file.

**Why it's bullshit:** all three facts the reversal rests on are wrong, and the module is exactly as dead as
the original finding said.

1. *"It is live — `store.py:1762` imports `DuckCatalogView` at runtime."* The import is at
   `store.py:1765`, inside `_read()`, whose **first statement** is
   `if not self._read_via_duckdb: return self._connect()` (`store.py:1753-1758`). `_read_via_duckdb` is
   `os.environ.get("RMX_READ_VIA_DUCKDB") in ("1","true","True")` (`store.py:717`). Reachable-behind-a-flag
   is the overlay's named hiding place (`.claude/agents/ch-bsd.local.md` — "env-flag-only facades (`RMX_*`
   read once, no caller)"), not "live".
2. *"`tests/test_duckdb_read_routing.py` does not exist."* It has existed continuously since
   `2ec66e8` (2026-05-16) and `git ls-tree 8efef73 -- tests/test_duckdb_read_routing.py` lists it, i.e. it
   was in the tree at the very commit that merged task 6.1. It is also the **only** place in the repository
   that sets the flag — the one file the original finding named by name.
3. *"Deleting it would have broken the read path."* The read path never reaches it. An exhaustive search for
   `RMX_READ_VIA_DUCKDB` across the repo, `~/Library/LaunchAgents/`, and `.claude/hooks/hooks.env` returns
   only: the stale docstring, the two `store.py` sites, and that one test. No plist, no hook, no daemon, no
   CLI path sets it.

Worse than unreachable: the facade cannot work against the production backend even if the flag were set.
`DuckCatalogView` mounts the catalog with `INSTALL sqlite_scanner` / `ATTACH '<db>' ... (TYPE SQLITE,
READ_ONLY)` (`duckdb_view.py:96-99`), and `tests/test_duckdb_read_routing.py:33` pins
`Store(..., backend="sqlite")` with the comment *"this test is about the SQLite→DuckCatalogView read
routing toggle, which only makes sense against a SQLite catalog."* Production is DuckDB by default since
2026-05-16 (`backend.py:45-61`) and the live store holds `catalog.A.duckdb` / `catalog.B.duckdb` /
`catalog.read.duckdb` and **no** `catalog.db`.

The module docstring is the stale-prose defect task 6.1 was written to remove, still sitting in the file
task 6.1 re-examined: *"Read-only DuckDB facade over the SQLite catalog (`.refmatrix/catalog.db`). Phase 1
of the DuckDB+Lance migration. The SQLite catalog stays the system of record for writes"*
(`duckdb_view.py:1-7`). There is no SQLite catalog and no system of record for it to be.

**Evidence:**
```
store.py:717   self._read_via_duckdb: bool = os.environ.get("RMX_READ_VIA_DUCKDB") in ("1","true","True",)
store.py:1757  if not self._read_via_duckdb:
store.py:1758      return self._connect()
store.py:1765  from refmatrix.duckdb_view import DuckCatalogView
# every setter of the flag, whole repo + launchd + hooks.env:
tests/test_duckdb_read_routing.py:28   monkeypatch.setenv("RMX_READ_VIA_DUCKDB", "1")
# and that test pins the non-production backend:
tests/test_duckdb_read_routing.py:33   s = Store(tmp_path / ".refmatrix", backend="sqlite")
$ git ls-tree 8efef73 --name-only -- tests/test_duckdb_read_routing.py
tests/test_duckdb_read_routing.py
```

**Fix:** execute Q1 as decided — delete `src/refmatrix/duckdb_view.py`, the `_read_via_duckdb` /
`_duck_view` / `_read_conn` state and the `_read()` branch in `store.py`, `tests/test_duckdb_read_routing.py`
and `tests/test_duckdb_parity.py`, and the `duckdb_view.ReadConnection` mentions at `store.py:870`
and `:1757`. If the module is wanted, the other half of the fork is open: amend Q1 to "wire", set the flag
on a production path, and make it work against the DuckDB backend. What is not available to a plan that
wrote its decision down is a third option reached by misreporting the facts — and a reversal of a RESOLVED
question must amend `#q1` and the Decisions Log, not only a task spec.

**Pattern match:** YES — the inverse of [[bsd-impressions#imp-gap-that-already-ships]] (there, a plan claimed something was
unbuilt that shipped; here, a task claimed something is live that is not), plus `imp-dead-flag-surface`.

rel: contradicts -> [[plan-6-deferrals-docs-benchmark#q1]]
rel: contradicts -> [[claude#no-mocks]]

### BULLSHIT: task 6.4's only measurable requirement — "registry lists **every** file that monkeypatches an external boundary" — is disproved by one grep, and four of the six offenders predate the task's own close {#b-2}

**File:** `workflow/test_mock_registry.md`,
`workflow/plans/plan-6-deferrals-docs-benchmark-tasks/task-6.4-plan-6-deferrals-docs-benchmark.md#requirements`
and `#closing`

**What:** Task 6.4's `## Requirements` is two clauses; the second is *"registry lists every file that
monkeypatches an external boundary."* Its closing note reports the scan found exactly three such files
(`test_daemon_liveness.py`, `test_hub_plist_devtree.py`, `test_sync_and_extras.py`), adds their rows, and
marks the task `status: complete` on 2026-09-16.

**Why it's bullshit:** six files monkeypatch an external boundary and have no registry row. Four of them
were already in the tree on 2026-09-16, so the "every file" claim was false the day it was written — not
drift afterwards. The most consequential one fakes `os.execv`, the objc fork-safety re-exec that
`project_session_0620_stm_forksafety` exists because of.

**Evidence:**
```
tests/test_fork_safety_reexec.py:21,40,51,69   monkeypatch.setattr(os, "execv", ...)   added 2026-06-20 (2f4aa93)
tests/test_read_surface_grammar.py:30          monkeypatch.setattr(sys, "stdin", _FakeStdin(...))  added 2026-06-11 (55ea0c8)
tests/test_reupsert_staleness.py:19            monkeypatch.setattr(store_mod.time, "time", ...)    added 2026-06-11 (f3b7c9d)
tests/test_grep_stdin_dialect.py:53            monkeypatch.setattr(sys, "stdin", fake)             added 2026-09-13 (583ad1c)
tests/test_learn_queue.py:46                   monkeypatch.setattr(socket, "socket", _boom)        added 2026-09-17 (9d8e4b9)
tests/test_session_raw_link.py:112             monkeypatch.setattr(os, "link", _boom)              added 2026-09-20 (0b9eb30)
```
89 test files call `monkeypatch.setattr`; the registry names 55. And nothing guards the claim: the only
reference to `workflow/test_mock_registry.md` anywhere under `tests/` is a prose mention in a docstring
(`tests/test_verbs_migrated.py:5`). There is no coverage lint, which is why the registry has already
regressed twice since the task closed (`test_learn_queue.py` 2026-09-17, `test_session_raw_link.py`
2026-09-20) with nothing noticing.

**Fix:** add the six rows with classifications; then add the guard the requirement implies — a test in the
shape of `test_deferrals_clean.py::test_no_stale_phase_language_in_src` that scans `tests/` for
external-boundary patch targets (`os.*`, `sys.stdin`, `socket.*`, `shutil.which`, `subprocess.*`,
`time.time`/`monotonic`, launchd) and asserts each matching file has a row. A one-time manual sweep cannot
satisfy a requirement phrased "every file".

**Pattern match:** YES — registry omission, 4th sighting in this ledger
([[impression_bsd_registry_row_deferral]], whose own index line already reads "3rd mock-registry strike").
Per the escalation rule (SKETCHY → BULLSHIT at 3+), filed as BULLSHIT.

rel: contradicts -> [[claude#no-mocks]]

### SKETCHY: task 6.5 left `wrapper_paths()` computing a value nobody reads, and left two docstrings describing the behaviour it had just removed {#s-1}

**File:** `src/refmatrix/search_hooks.py:18-20`, `:300-310`, `:313-322`; `src/refmatrix/hooks.py:464-467`, `:635`

**What:** Task 6.5 moved wrapper resolution from render time into the rendered script. The resolution code
it replaced was not removed; it was orphaned.

**Why it's sketchy:** the data path is circular and dead, and the prose now lies.

- `render_scripts(wrappers=...)` **accepts and ignores** the argument; the code says so at
  `search_hooks.py:318-322`.
- Its only non-default caller is `hooks.py:635`, `render_scripts(flags.get("wrappers"))`.
- That value exists solely to be passed there: `hooks.py:464-467` calls `wrapper_paths()` only to write
  `wrappers=` into `.claude/rmx-hooks.json`. A search of `src/`, `tests/`, `scripts/`, `bin/`, `eval/` and
  `src/refmatrix/templates/` finds no other reader. The live `.claude/rmx-hooks.json` duly records
  `["/Users/tholley/refmatrix/bin/rmxgrep", ".../rmxrg"]`, and nothing consumes it.
- So `wrapper_paths()` is a production function whose entire output is written to a file and never read, and
  the in-code justification is the circle itself: *"The parameter stays because `check()` still passes the
  paths recorded at apply time, and removing it would break that caller for no gain."*
- `search_hooks.py:18-20` (module docstring) still reads *"Wrapper paths are resolved at install time — PATH
  first, then this package's repo `bin/` — and baked in absolute, because the guard's own history shows
  aliasable names get aliased out from under hooks."* That is precisely the behaviour task 6.5 deleted, in
  the file task 6.5 edited.
- `render_scripts`' own docstring (`:315-317`) says *"`wrappers` = (rmxgrep, rmxrg) paths to bake; default =
  this process's `wrapper_paths()`"*. Nothing is baked and `wrapper_paths()` is never called from there.

A plan whose task 6.1 removes five false sentences from `src/` and whose task 6.5 adds two has not met its
own bar. The *behaviour* is correct — hence SKETCHY, not BULLSHIT.

**Evidence (mutation M5):** re-introducing baking in `render_scripts` turns
`test_rewriter_bakes_no_tree_path` and `test_rewriter_renders_identically_from_any_tree` RED (2 failed, 22
passed), confirming the removal is real and the prose is the stale half. Note also that
`test_rewriter_renders_identically_from_any_tree` monkeypatches `sh.wrapper_paths`, which `render_scripts`
no longer calls — so its `a == b` is trivially true for any implementation that ignores the parameter; the
assertion that actually carries the property is `test_rewriter_bakes_no_tree_path`.

**Fix:** drop the `wrappers` parameter from `render_scripts`, drop `wrappers=` from the `record_flags` call
at `hooks.py:467`, delete `wrapper_paths()` (that was its last caller), and rewrite `search_hooks.py:18-20`
to describe runtime resolution with the bug-008 incident it came from.

rel: contradicts -> [[claude#development-guidelines]]

### SKETCHY: task 6.4 is marked `complete` with no implementation summary, which its own Definition of done and CLAUDE.md both call mandatory {#s-2}

**File:** `workflow/implementation_summaries/` (51 files; none for 6.4),
`workflow/plans/plan-6-deferrals-docs-benchmark-tasks/task-6.4-plan-6-deferrals-docs-benchmark.md#done`

**What:** 6.1, 6.2, 6.3 and 6.5 each have `workflow/implementation_summaries/task-6.N-plan-6-deferrals-docs-benchmark.md`.
6.4 does not, while its `## Definition of done` requires *"Implementation summary at
`workflow/implementation_summaries/task-6.4-plan-6-deferrals-docs-benchmark.md`"* and
`CLAUDE.md#task-completion-workflow` step 8 marks it **(MANDATORY)**.

**Why it's sketchy:** the summary is where this repo records the mutation check. 6.4's spec says
*"mutation check noted in the implementation summary"* and its Test Strategy is *"Existing suite + registry
lint"* — no new tests at all. So the loud-logging change at `verbs.py` `memory_partition` shipped with no
test and no recorded mutation, and there is no artifact that says what was proven. (The change itself is
real and correct — `verbs.py:252` logs a `debug` naming root and error when the replica is unavailable, and
`:275-277` logs a `warning` naming root, error and the partition it falls back to when `partition_list`
answers an error. The silent guess is genuinely gone.) Separately, 6.4's `#closing` note asserts
`tests/test_graph_landing.py` was a stale fake rather than a partition bug, and that holds: the file passes,
and bug-034 records four mutations each killing its test.

**Fix:** write `workflow/implementation_summaries/task-6.4-plan-6-deferrals-docs-benchmark.md` naming what
was changed, the suite run that covers it, and the mutation applied to the two new log branches — or add a
test that asserts the `warning` fires on an answered-error `partition_list`, since nothing does today.

rel: contradicts -> [[claude#task-completion-workflow]]

### SKETCHY: the task 6.1 guard is a five-literal allow-list, so three stale deferrals that were in `src/` on the day it declared `src/` clean are still there {#s-3}

**File:** `src/refmatrix/session_ingest.py:3-5`, `src/refmatrix/cli.py:5645-5646`,
`src/refmatrix/vectors.py:14`; guard at `tests/test_deferrals_clean.py:42-71`

**What:** Task 6.1's requirement is `grep -rn "deferred to v1\|Phase 2 will\|Phase A stub\|unused for now" src/`
→ empty, and `tests/test_deferrals_clean.py` freezes exactly five literal phrases. That grep is empty. The
*class* it was built to stop is not.

**Why it's sketchy:** three stale deferrals predate the task and survived its sweep, one of them stating the
opposite of the truth.

1. `session_ingest.py:3-5` — *"Phase A of the session-index plan (ISSUE-session-index.md). … CLI surface,
   daemon ops, and partition routing land in later phases."* Added 2026-06-03 (`c8ece04`). Two of the three
   **already shipped**: `rmx session` exposes `ingest / recall / show / list / launchctl` on the deployed
   0.73.0, and partition routing is `cli._session_partition()` at `cli.py:12366`, used at `:12380` and
   `:12395`, against a dedicated `sessions-<project>` partition. A docstring that defers work which has
   landed is worse than a stale one: it tells the next reader the surface does not exist. `ISSUE-session-index.md`
   is a root-level issue doc with no task specs, so there is nothing to anchor the remaining item to either
   (rule 9a).
2. `cli.py:5645-5646` — the `_render_grep_rows` docstring says `-v invert → printed in caller … for now we
   honor it as a no-op on the indexed path`. The code **three lines below** does the opposite: it prints
   *"-v (invert) is not implemented on the indexed path"* and returns, punting to the rg/grep fallback.
   Introduced 2026-05-17 (`0930b92`), so it was in `src/` for task 6.1's sweep; the phrase is "for now",
   which the five-literal list cannot see.
3. `vectors.py:14` — *"ANN search is L2-distance based for now."* Added 2026-05-27 (`12e850b`); "for now"
   names no plan and no task (rule 9a: unanchored).

And the meta-test meant to stop the guard being neutered counts entries rather than content:

**Evidence (mutation M3):** replacing `"deferred to v1"` with `"ZZZ-never-matches"` in `BANNED` — same list
length, zero coverage — leaves all 14 tests passing. `test_this_guard_names_the_phrases_it_bans` asserts
only `len(BANNED) >= 4`. (M2 confirms the guard does fire for a real hit: appending `# unused for now` to
`helix.py` turns `test_no_stale_phase_language_in_src` RED.)

**Fix:** fix the three sites (delete the landed claims in `session_ingest.py`; make the `cli.py` docstring
say "refused, falls back to rg"; give `vectors.py` either a task id or no promise). Then widen the guard
from five literals to the phrase *families* — `for now`, `in v1`, `later phase(s)`, `eventually`,
`when needed`, `not yet`, `TODO` with no plan id — with an explicit allow-list of reviewed exceptions, so
the next instance fails the suite instead of waiting for an audit. A guard whose coverage can be emptied
without changing its length is not a guard; assert on the phrase set, not on its size.

**Pattern match:** YES — `imp-existence-check-tests` (counting the population instead of the compared set).

rel: contradicts -> [[task-6.1-plan-6-deferrals-docs-benchmark#requirements]]

### MEH: bug-008's registry row still reads "NOT verified live" fifteen days after its sibling registry recorded the live verification — and the caveat is in fact closed {#m-1}

**File:** `workflow/bug_registry.md:51` vs `workflow/deferral_registry.md:37`

**What:** The lead asked me to test bug-008's caveat, so here is the live reading on 0.73.0. It has
converted, and `--check` is clean:

```
$ rmx version -v
refmatrix 0.73.0   code: /Users/tholley/refmatrix/src/refmatrix/__init__.py
$ rmx install-hooks --check
hooks in sync /Users/tholley/claude_tools/refmatrix/.claude/settings.json
# live user-global scripts vs the current render, read-only, via the DEPLOY interpreter:
grep-rewrite-guard.sh  exists IDENTICAL
rmxgrep-rewrite.py     exists IDENTICAL
grep-tool-teach.sh     exists IDENTICAL
tree literal in live rewriter ('/refmatrix/bin/'): False
```
`~/.claude/hooks/rmxgrep-rewrite.py` (mtime 2026-09-16 04:08) defines `RMXGREP()` / `RMXRG()` at lines
59 / 63 resolving through `shutil.which("rmx")` at line 40, with no tree literal anywhere. And `--check`
genuinely covers this: `hooks.py:630-639` compares all three user-global scripts byte-for-byte against the
render and emits *"script <name> differs from the generator's render"* on any drift — it is not a
settings.json-only check.

**Why it's a finding anyway:** `workflow/bug_registry.md:51` still carries *"**NOT verified live:** `rmx` on
PATH is the 0.69.1 deploy build … the live hook still carries `RMXGREP = "/Users/tholley/refmatrix/bin/rmxgrep"`
… Converts on the next deploy + `install-hooks --apply --force`"*, while
`workflow/deferral_registry.md:37` already records *"GRADUATED LIVE 2026-09-16 on 0.72.2: … now defines
`RMXGREP()`/`RMXRG()` as functions with no baked tree path, and `rmx install-hooks --check` reads in sync."*
Two registries, same fact, opposite readings, for fifteen days. Session 1 of anyone reading
`bug_registry.md` first will re-do this verification.

**Fix:** replace the `NOT verified live` sentence in `bug_registry.md:51` with the 0.73.0 reading above and
a pointer to `deferral_registry.md:37`. (While there: that row's line citations for the launchd guards say
`:305/:465/:505`; they are now `:308/:468/:508`.)

### MEH: the `degraded` counter task 6.1 added is dropped on `_op_embed`'s shutdown-cancel return {#m-2}

**File:** `src/refmatrix/daemon.py:5390-5400`

**What:** `_op_embed` resets the counter, runs `extract_batch`, reads `degraded`, and then has a cancel
branch that returns without it:
```
5390  embmod.reset_degraded()
5391  triples = embmod.extract_batch(d.store, rows)
5392  degraded = embmod.degraded_report()
...
5399  if d._shutdown_event.is_set():
5400      return {"embedded": 0, "remaining": len(rows), "cancelled": True}
```
**Why:** extraction has already run by line 5399, so a batch cancelled by a shutdown discards whatever
degradations it counted. The wiring is otherwise complete and genuinely end-to-end — `embedder._note_degraded`
(`embedder.py:40-55`, called at `:253`, `:259`, `:275`) → `_op_embed`'s `degraded` → `cli.py:9623-9624`
aggregation → `cli._degraded_embed_line` at `cli.py:9638` — which is the strongest part of task 6.1. And the
per-row `log.warning` at `embedder.py:42` still reaches `rmxd.log`, so the fact survives; only the count
the CLI prints is lost. Hence MEH, not a silent-failure violation.

**Fix:** carry `"degraded": degraded` on the cancel return, the same way the `skipped_empty` return at
`:5395-5396` already does.

### MEH: `test_eval_artifact_cited.py` checks one of the four figures in the README table it guards {#m-3}

**File:** `tests/test_eval_artifact_cited.py:47-51`

**What:** Task 6.3 is otherwise clean and mutation-proven — README's `0.961` matches
`eval/production/results/csn_python/metrics.json` (`MRR@10: 0.961`, `full_run: true`, 43827 docs / 14918
queries, `refmatrix_version 0.69.1`, `git_sha a965805`), README names that run and that sha explicitly, and
mutating the README figure to `0.962` turns `test_cited_figure_matches_the_artifact` RED (M1). But the test
compares `MRR@10` only, and the same README table publishes `Recall@1 0.944`, `Recall@10 0.984`,
`nDCG@10 0.967` from the same artifact.

**Evidence (mutation M6):** editing README's `Recall@1` from `**0.944**` to `**0.911**` — a figure the
artifact contradicts — leaves all four tests passing.

**Fix:** loop the comparison over `{MRR@10, Recall@1, Recall@10, nDCG@10}` with the artifact's own rounding,
instead of asserting one row of a four-row table.

### MEH: `store._log_event`'s rewritten docstring still says the commit is a SQLite commit {#m-4}

**File:** `src/refmatrix/store.py:762`

**What:** Task 6.1 rewrote this docstring well — it now names the 2026-09 facts.log audit, the missing
edge-time history and the three unlogged write paths, and correctly refuses to call the log a journal. The
first line of the body still reads *"Called after the SQLite commit on every mutation."* The backend has
been DuckDB by default since 2026-05-16 (`backend.py:45-61`).

**Fix:** "after the catalog commit".

### MEH: "run the full suite from any checkout" does not hold, which is what made task 6.4's first requirement unmeasurable for me {#m-5}

**File:** `workflow/bug_registry.md:110` (bug-054), `.venv-eval` site-path resolution

**What:** bug-054 is recorded `fixed` on the claim that a detached `git worktree` at the sha under test
reproduces a commit's full-suite result. It does not, for a second reason the fix did not cover, and the
mechanism is an **ambient environment variable clobbered by assignment**. This shell already exports a
four-entry `PYTHONPATH`:
```
$ echo "$PYTHONPATH"
/Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/site-packages:
/opt/local/Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/site-packages:
/Users/tholley/Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/site-packages:
/Users/tholley/python_libraries/lib/python3.14
```
`.venv-eval`'s base interpreter is MacPorts `/opt/local/`, but `typing_inspection` (a pydantic 2.13
dependency, reached through `lance`) lives only in `/Library/Frameworks/` — i.e. only in that ambient
variable. So `PYTHONPATH=<wt>/src`, the obvious way to give a second checkout its own `src/`, is an
ASSIGNMENT that silently replaces the one path to that package:
```
$ .venv-eval/bin/python -c "import sys;print([p for p in sys.path if 'Frameworks' in p])"
['/Library/Frameworks/.../site-packages', '/opt/local/.../site-packages', '/Users/tholley/Library/.../site-packages', ...]
$ PYTHONPATH=/x/src .venv-eval/bin/python -c "import sys;print([p for p in sys.path if 'Frameworks' in p])"
['/opt/local/.../python314.zip', '/opt/local/.../python3.14', '/opt/local/.../lib-dynload']
```
My first worktree run reported **43 failed / 7 errors**; 31 of the failures were
`ModuleNotFoundError: No module named 'typing_inspection'`, and `tests/test_vectors.py` passes 7/7 in-tree
while failing 7/7 in the worktree for that reason alone. Re-appending the system site-packages directories
makes the worktree faithful again.

**The dangerous shape is not the one I hit.** My selection reached the pydantic dependency and died loudly.
bsd-plan8910-r5 hit the same clobber on a selection where `lance` is behind `pytest.importorskip`, so the
degraded path reported **"133 passed, 8 skipped" where the healthy path collects 219** — 78 tests silently
uncollected, no failure, no warning, a green-looking verdict. bsd-plan3-r7 confirmed the mechanism
independently (1 site-packages entry instead of 4) on an 11-file selection that never reaches pydantic and so
gave the SAME 152 passed on both paths. Those three results together give the rule: **a green run on the
degraded path is not evidence the path was healthy, and pass/fail cannot tell you which you got — only the
COLLECTED COUNT can.** Compare collection, not the verdict. See [[#suite]] for the count check on the figure
this report actually cites, and note that `refmatrix.__file__` resolving into the worktree does NOT catch
this: `refmatrix` imports fine either way; it is `lance` / `typing_inspection` that vanish.

**Fix:** three layers, cheapest first. (1) Never assign — `PYTHONPATH=<wt>/src:$PYTHONPATH` prepends and
keeps the ambient entries; better still, derive them rather than hardcode
(`$(python -c "import sys;print(':'.join(p for p in sys.path if 'site-packages' in p))")`, bsd-plan3-r7's
recipe). (2) Make `.venv-eval` self-sufficient (`pip install typing_inspection` into it) so no suite run
depends on an exported variable at all — this is the same mixed-ABI hazard
`reference_mixed_abi_python_tree` records. (3) Best: have `tests/conftest.py` put the repo root's `src/` on
`sys.path` itself, so a second checkout needs no `PYTHONPATH` and bug-054's claim becomes true by
construction. Until one of these lands, any suite result from a worktree must cite its collected count or be
treated as void.

One correction to a neighbouring claim, since it was offered as part of this fix: the venv's OWN
site-packages is not at risk from the assignment. It is added by the `site` module from `pyvenv.cfg`, not by
`PYTHONPATH` — verified above, where `.venv-eval/lib/python3.14/site-packages` appears in `sys.path` despite
not being one of the four `PYTHONPATH` entries. Only the three framework dirs are lost.

## Full suite {#suite}

Task 6.4's first requirement is **"Full suite 0 failures."** It holds, measured in the canonical tree at
`e0b7df6`:

```
$ .venv-eval/bin/python -m pytest -q -p no:cacheprovider
2238 passed, 1 warning in 1279.97s (0:21:19)
```
`workflow/review-output/bsd-plan6-r1-fullsuite-intree.log` — **2238 passed, 0 failed, 0 skipped, 0 errors.**
The single warning is a third-party `StarletteDeprecationWarning` from `tests/test_cctree_web.py:16`.

It took three attempts to get one measurement, and the two discarded attempts are [[#m-5]] and the
concurrency note in [[#adjacent]]:

| Run | Tree | Result | Status |
|-----|------|--------|--------|
| 1 | shared checkout, 11:58 | killed | invalid — a parallel agent modified `src/refmatrix/cli.py` and `verbs.py` at 12:04:59 and 12:06:26, mid-run |
| 2 | `git worktree --detach` at `e0b7df6` + `PYTHONPATH=<wt>/src` | 43 failed, 2062 passed, 13 skipped, 7 errors | invalid — 31 failures are `ModuleNotFoundError: typing_inspection`; see [[#m-5]] |
| 3 | shared checkout, 12:35-12:57, tree verified clean at start | **2238 passed** | **valid** |

**Which figure this report cites, and why it is not the degraded path.** The headline is run 3: the
**shared checkout, with no `PYTHONPATH` assignment of any kind**, so it inherited the healthy ambient
four-entry variable. Three independent confirmations, because [[#m-5]] shows that pass/fail alone cannot
distinguish a healthy run from a silently-truncated one:

1. **Collected == passed.** `pytest --collect-only -q --ignore=tests/test_plan3_remedy_r7.py` collects
   exactly **2238**; the run reports **2238 passed**. Nothing was dropped. (With that file: 2244 — see below.)
2. **No skips, no errors.** The degraded path manifests as `importorskip` skips and collection errors; run 2
   produced 13 skipped + 7 errors, run 3 produced **0 of each**. `grep -cE "^SKIPPED|^ERROR|importorskip"`
   over the log returns 0.
3. **The imports that vanish on the degraded path resolve.** Under run 3's environment,
   `.venv-eval/bin/python -c "import typing_inspection, lance"` succeeds and `sys.path` carries **4**
   site-packages entries, `typing_inspection` resolving from
   `/Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/site-packages`.

Run 2 (the worktree) is **void and is not cited for anything**. Its 43 failures were environmental, confirmed
two ways: every file that failed there passes in-tree (`tests/test_onboard_huballd_curator.py`,
`test_plan1_remedy.py`, `test_plan4_remedy_r2.py`, `test_plan4_remedy_r3.py`, `test_upgrade.py` →
**89 passed** in `workflow/review-output/bsd-plan6-r1-intree-candidates.log`), and run 3 passed the same
positions clean. It is reported here only as evidence for [[#m-5]].

Two further guards on run 3, because a suite log is only evidence about the tree it ran in:

- `git status --short` returned no `src/` or `tests/` entry at launch, and the only in-flight writes during
  the run were to `workflow/bullshit/` reports.
- The other auditor's new `tests/test_plan3_remedy_r7.py` appeared at 15:14, **after** collection. Proof it
  was not in the run: `pytest --collect-only --ignore=tests/test_plan3_remedy_r7.py` collects exactly
  **2238** items and `--collect-only` with it collects 2244. The run passed 2238, so it collected the tree as
  committed and nothing else.

The plan-6 acceptance tests specifically (`test_docs_generated.py`, `test_deferrals_clean.py`,
`test_eval_artifact_cited.py`, `test_search_hooks.py`, `test_graph_landing.py`, `test_duckdb_parity.py`,
`test_duckdb_read_routing.py`) are **71 passed** in
`workflow/review-output/bsd-plan6-r1-focused.log`.

So 6.4's first clause is satisfied; its second clause is [[#b-2]].

## Mutation checks run {#mutations}

Six, all behaving as the tests claim except M3:

| # | Mutation | Expected | Result |
|---|----------|----------|--------|
| M1 | README `MRR@10` `0.961` → `0.962` | RED | RED — `test_cited_figure_matches_the_artifact` |
| M2 | append `# unused for now` to `src/refmatrix/helix.py` | RED | RED — `test_no_stale_phase_language_in_src` |
| M3 | `BANNED[0]` `"deferred to v1"` → `"ZZZ-never-matches"` (same length) | RED | **GREEN, 14 passed** → [[#s-3]] |
| M4 | add a visible click command `bsd-mutation-probe` | RED | RED — `test_cli_tree_section_equals_its_render` + `test_check_mode_reports_drift_and_apply_fixes_it` |
| M5 | re-bake the generator tree into the rendered rewriter | RED | RED — `test_rewriter_bakes_no_tree_path` + `test_rewriter_renders_identically_from_any_tree` |
| M6 | README `Recall@1` `0.944` → `0.911` | RED | **GREEN, 4 passed** → [[#m-3]] |

Every mutation was reverted with `git checkout <path>` and `git status` confirmed clean after each pair.

## E2E (per `.claude/agents/ch-bsd.local.md#e2e`) {#e2e}

- `rmx install-hooks --check` — **clean**, and proven to cover the three user-global scripts byte-for-byte
  (`hooks.py:630-639`), not just `.claude/settings.json`. See [[#m-1]].
- `./scripts/lint-gmd.sh` — **zero errors**, run from the MAIN tree only. It derives `MEMDIR` from the
  checkout path, so inside a worktree it looks for `~/.claude/projects/-private-tmp-rmx6/memory`, silently
  drops the memory dir from SCOPE and reports a meaningless error count (bsd-plan8910-r5 saw 347 that way).
  Memory files were linted with `python3 ~/claude_tools/gmd/lint.py` against the real memory dir.
- Verb parity (`tests/test_verb_parity.py`) and the save-state/recall-state round trip — carried by the
  full-suite run in [[#suite]].
- Production benchmark harness — not re-run (a 43827-doc / 14918-query run is ~45 min of ingest alone); the
  committed artifact was verified against README instead, which is exactly what task 6.3 asks for.

## Adjacent, outside plan-6's range — flagged, not counted {#adjacent}

`cli._session_all_rows` (`cli.py:12389-12395`) falls back to a **read-write** `Store(root, partition=...)`
open when `daemon_mod.ping(root)` is falsy. Busy is not absent: a daemon holding the writer fails a bare
ping, so this opens the active slot — the DuckDB lock-crash class, and the **5th** sighting of
[[bsd-pattern-busy-is-not-absent]], against both `PROJECT_PROFILE.md#constraints` and
`feedback_store_calls_via_daemon`. Introduced with the session index, not by plan-6; it belongs in the bug
registry rather than in this plan's gate.

Process hazard, not a code finding: **THREE** ch-bsd agents ran mutation checks in this one working tree
concurrently (plan-3 r7, plans-8/9/10 r5, and this audit). At 12:06 `src/refmatrix/cli.py` and
`src/refmatrix/verbs.py` were uncommitted-modified, plus `bsd_probe_r7.py` / `bsd_probe_r7b.py` at the repo
root, which invalidated a full-suite run of mine already in progress. Symmetrically, my six
mutate-and-revert windows between 11:50 and 12:06 could have poisoned the others' readings, and plan-3's
`git checkout -- src/` restores did revert my in-flight edits — that run died from both sides at once.

**Correction to my own first reading of this.** I initially attributed all of the 12:06 churn to
`bsd-plan3-r7`. That was over-attribution from a single `git status`. plan-3 accounts for exactly three
files — `search.py`, `cli.py` (a `canon_find` render loop and a `memory_get --degree` ping) and the
`verbs.py` promote timeout, which is the edit I named and is correctly theirs. The other `cli.py` edit I
saw, `default=("contradicted",)` on `memory brief --class`, is **not** plan-3's: `brief --class` is a
plan-8 surface, outside plan-3's scope, so it belongs to the plans-8/9/10 auditor. Two agents were writing
to `cli.py` in the same window. The lesson for the detection recipe below: a foreign modification tells you
the tree is contaminated, it does not tell you BY WHOM, and `git status` cannot separate two writers to one
file — ask each party what it touched before naming anyone.

Future parallel rounds want one `git worktree --detach` per auditor, with [[#m-5]] fixed first so a
worktree is actually usable, and with each auditor's suite result citing its collected count. The reusable
detection route: a `git status` showing foreign uncommitted modifications or foreign probe files at the repo
root, with their **mtimes compared against your run's start time** — that is what made the contamination
visible, and nothing in pytest's own output would have.

## Verdict {#verdict}

**DIRTY — 9 findings (2 BULLSHIT, 3 SKETCHY, 4 MEH). plan-6 may NOT flip to `completed`.**

Tasks 6.2, 6.3 and 6.5 are real work with guards my own mutations kill — the CLI tree went from 24
hand-drawn commands to 204 rendered ones that fail the suite on drift, the headline benchmark number now
has a committed artifact and a named run, and bug-008's rewriter is verified converted on the live
0.73.0 hook. Task 6.1's central fix (the degraded-embed counters) is wired end to end through daemon and
CLI, and bug-034 turned five "known pre-existing failures" into four real contracts with mutations behind
each.

The two blockers are the two places the plan graded its own homework. [[#b-1]]: the plan RESOLVED Q1 as
"delete `duckdb_view.py`", a task spec reversed it, and all three facts in the reversal are false — the
module is still 133 lines reachable only through an env flag nothing sets, against a backend it cannot
even attach. [[#b-2]]: task 6.4's one measurable requirement says "every file" and one grep finds six
missing, four of them already present when the task closed, with no lint to keep it true.

Close [[#b-1]] and [[#b-2]]; fix the three stale sites and widen the guard in [[#s-3]]; write 6.4's
summary [[#s-2]]; and amend `#q1` and the Decisions Log so the plan stops contradicting itself.

rel: contradicts -> [[plan-6-deferrals-docs-benchmark#execution]]
