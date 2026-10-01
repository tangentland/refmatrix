---
gmd: "0.1"
id: bsd-plan3-verbs-parity-r7-e0b7df6
title: "ch-bsd findings — plan-3 verbs parity r7 (ffed3df..e0b7df6, remedy 763aaa0+732c755 at b252a09): both BULLSHIT findings closed and reproduced in all four daemon states; the two `skipped` producer guards the same commit added cannot fire, and `memory promote` still costs 180.2 s one leg over"
tags: [bsd, findings, plan-3, verbs, cli, search, remedy-r7]
severity: BULLSHIT
plan: plan-3-verbs-parity
task: task-3.1-plan-3-verbs-parity, task-3.2-plan-3-verbs-parity, task-3.3-plan-3-verbs-parity
metadata:
  node_type: bsd-report
  commit: e0b7df6
  remedy_commit: 763aaa08f96c0765683d379a1c38ec111e41f960, 732c7550a703f8befe45c5565ac6343269bc55ce
  merge_commit: b252a09
  range: "ffed3df..e0b7df6 scoped to plan-3 surfaces (verbs.py, search.py, the `rmx memory` group + `canon find` in cli.py, mcp.py, tests/test_plan3_remedy*.py); the range also carries plans 7-13, bugs 041-061 and three deploys, audited by their own rounds"
  head_at_audit: e0b7df6
  deployed: "0.73.0 at ~/refmatrix (7e76610, an ancestor of HEAD; e0b7df6 and 0714a11 are docs-only), `rmx version -v` code=/Users/tholley/refmatrix/src, fleet 8/8 up and supervised"
  verdict: DIRTY
  findings: 6
---

# ch-bsd findings — plan-3 remedy round 7 re-review {#root}

**Commit:** e0b7df6 (plan-3 content = `763aaa0` + `732c755`, merged at `b252a09`)
**Date:** 2026-10-01
**Author:** Todd Holley / Opus 5 (1M) / orchestrator
**Files changed (763aaa0):** 4 — `cli.py` (+109/−46 over three functions), `search.py` (+9/−2), `verbs.py` (+15/−3), `tests/test_plan3_remedy_r6.py` (new, 269 lines)

rel: amends -> [[bsd-plan3-verbs-parity-r6-ffed3df]]
rel: evidence-for -> [[plan-3-verbs-parity]]
rel: evidence-for -> [[impl-remedy-plan-3-verbs-parity]]

## Method {#method}

Everything below was run by me at HEAD `e0b7df6` on the dev tree (`.venv-eval`), plus three
read-only commands on the deployed `~/bin/rmx` 0.73.0. Suites:
`workflow/review-output/pytest-bsd-plan3-r7-suites.log` — **152 passed in 377 s** across
`test_plan3_remedy_r6`, `_r5`, `_r4`, `_r3`, `_r2`, `test_plan3_remedy`, `test_verb_parity`,
`test_mcp_parity`, `test_verbs_migrated`, `test_locate`, `test_surface_parity`. Probes:
`pytest-bsd-plan3-r7-probe.log` (the fan-out producers, a REAL spawned daemon for the `--degree`
tail, and the promote command against a held GLOBAL store) and
`pytest-bsd-plan3-r7-probe-states.log` (`memory get --degree 1` and `memory promote` on both
registered simulations × replica present/absent, with the per-command op log and a
`catalog*.duckdb` size+mtime assertion). Mutations in-tree under `PYTHONDONTWRITEBYTECODE=1`,
each restored with `git checkout -- src/` and the tree verified clean afterwards. {#method-body}

**Ancestry, per the trap the lead named:** `763aaa0`, `732c755` and `b252a09` are each
`git merge-base --is-ancestor … master` → YES, and the deploy tree at `~/refmatrix` (7e76610)
carries `served_by_replica` / `MEMORY_CONTEXT_TAIL_S` (6 hits), `budgeted = is_read or action ==
"promote"` (1) and the `said, never mute (r6 #s-3)` marker (1). The fix is reachable on the
running build, not just committed. `search.py` has not been touched since the remedy merge; the
three edited `cli.py` functions and the `verbs.py` promote block are byte-identical at HEAD to
`b252a09` (`git diff b252a09..e0b7df6` on those hunks is empty). {#method-ancestry}

## Round-6 findings, verified {#r6-status}

- **#b-1 CLOSED — and reproduced three ways, including live.** `memory get --degree 1` no longer
  raises. On a REAL spawned daemon (`Store.init` + two memories + `spawn_daemon_subprocess`):
  **0.1 s, exit 0, `r.exception is None`**, body then `--- context ---` then the rendered bundle.
  On the deployed 0.73.0 against the live store: **3.6 s**, body + a 7-neighbor degree-1 bundle,
  no traceback. On both simulations × replica present/absent: 10.1 s / 0.6 s / 10.0 s / 3.0 s,
  no `NameError` in any state, and the writer slot's size+mtime unchanged in all four. My
  **mutation A** (the tail back to a bare `daemon_mod.ping` with the import still gone)
  reproduces `NameError("name 'daemon_mod' is not defined")` verbatim and kills 2 of the 3
  `--degree` tests — the flag is now guarded, where before it had no test at all. {#v-b1}
- **#b-2 CLOSED for the state it named.** `rmx memory promote held_row` on a `_PingOnlyDaemon`
  holding the project writer: **10.0 s** with a replica and **15.0 s** without (was 180.2 s), ops
  `['ping','ping','memory_get']` — ONE `memory_get`, not three — exit 1 with a typed, non-empty
  message (`daemon op memory_get … did not answer within 9.99565s (timed out); the daemon is
  busy`). On `_SilentDaemon`: 0.5 s. The verb leg is single-attempt under the action's budget:
  my **mutation C** (the promote read back to the library default retries) fails both promote
  tests **in 210 s**, which is the cost the finding measured. The empty-message half of #b-2 is
  closed everywhere. The 180.2 s half is not — see [[#b-2]]. {#v-b2}
- **#s-3 HALF closed.** The consumer half is real and load-bearing: `canon_find` echoes each
  `skipped` row to stderr and appends the count, and my **mutation E** (drop the echo loop) fails
  `test_canon_find_names_the_skipped_store` on the pid assertion. A daemon that never answers
  ping is named, because `_live_roots` classifies it `busy` — that path predates this commit. The
  producer half, the per-root `except` this commit added to `federated_concept`, cannot fire, and
  the symptom the finding filed reproduces at HEAD — see [[#b-1]]. {#v-s3}
- **#s-4 PARTLY closed.** Three leg tests were added and all three kill their mutation: M3 (the
  replica-bundle leg), M4 (the global memory leg), M5 (`_name_stragglers` deleted) each fail
  exactly one test now. M4 and M5 are honest — the global leg really does raise
  (`hub_mod.global_call`), and the straggler path really does miss a deadline. M3 is not: it
  feeds `_replica_bundle` an input `_replica_bundle` cannot produce — see [[#b-1]]. {#v-s4}
- **#m-5 / #m-6 (r6) not re-filed.** `_RECALL_FORWARD`'s `partition` guard and the recall
  budget trade are unchanged and were MEH advisories; `test_recall_twin_probes_the_partition_once`
  still passes at HEAD. {#v-meh}
- **Deferral sweep** over `763aaa0`'s `+` lines (hard and soft families) → two hits, both
  innocent: the test module's own "round 7 of plan 3", and the word *indistinguishable* inside the
  comment describing the defect [[#b-1]] shows is still live. A plan-completion sweep of
  `src/refmatrix/{search,verbs,mcp}.py` and `cli.py`'s memory group (lines 10100-11950) for both
  families and for `plan 3` pointers → **no stale and no unanchored deferral**. {#v-deferrals}
- **Plan status honest.** `metadata.status: in-progress` and `plan-of-plans.md` row 23
  `in-progress`; nothing was flipped ahead of this gate. {#v-status}

## Findings {#findings}

### BULLSHIT (guards that cannot fire; the #s-3 symptom reproduces verbatim): both `skipped` producer legs this commit added sit above a swallow that never lets them run, and the two tests that certify them feed an input the collaborator's own docstring forbids {#b-1}

**File:** `src/refmatrix/search.py:262-269` (`federated_concept`'s new `except Exception as e` →
`skipped.append`), `:145-146` (`_where_one_project`'s replica-bundle `except`, r6 #s-4's M3 leg),
against `:76-97` (`_replica_bundle`, whose two `except Exception: return {}` are the swallow) and
`:55-66` (`cached_replica`'s dedicated `FileNotFoundError(f"no replica catalog to read at …")`)
**What:** The remedy added a reason to `federated_concept`'s per-root `except`, with the comment
"a store that could not be read was indistinguishable from one that does not host the concept".
The only call inside that `try` is `_replica_bundle(root, name, degree=0)`, and
`_replica_bundle`'s docstring states its contract: *"Returns the render_json dict or {} on
failure."* It catches `cached_replica` failing (`:86-87`) and `build_context`/`render_json`
failing (`:96-97`) and returns `{}` for both. `if b:` is then False, no entry is appended, no skip
is appended, and the new `except` is never entered. The identical shape is at `:145-146`.
**Why it's bullshit:** two probes, deterministic
(`workflow/review-output/pytest-bsd-plan3-r7-probe.log`), on a root whose daemon is classified
**up**:

| state | `federated_concept` | `rmx canon find held_row` |
|-------|---------------------|---------------------------|
| no `catalog.read.duckdb` (the boot window) | `projects=[] skipped=[]` | `no live project hosts held_row`, exit 0 |
| `build_context` raises | `projects=[] skipped=[]` | same |

and for the `where` leg: `federated_where` with `build_context` raising → `results=0`,
`skipped=[]`, no reason. That is the finding's sentence, unchanged: a store that could not be read
is still indistinguishable from one that does not host the concept, and the operator is still told
the concept exists nowhere. The state is not hypothetical — `cached_replica` raises a purpose-built
`no replica catalog to read at …` for exactly the daemon boot window plan 4 opens on every
relaunch, with a comment saying the point is that the caller gets "the plain fact — no replica
yet". Its immediate caller throws that sentence away.

The two tests that certify these legs patch `search._replica_bundle` with a function that
**raises** (`tests/test_plan3_remedy_r6.py:200-212`, `:216-230`). My mutations D (the
`federated_concept` except back to `pass`) and M3 (the where leg back to `pass`) do each fail
their test — so the tests are load-bearing — but only against an input the real collaborator
cannot emit, while my probe output is byte-identical before and after the mutation. A test that
makes a collaborator violate its documented contract proves the branch exists, not that it runs.
Q17 in the plan already records the covered legs as including "the replica bundle"; that row is
false at HEAD and round 7 did not amend it.
**Evidence:** `pytest-bsd-plan3-r7-probe.log` (P1a/P1b/P1c/P2); `/tmp/claude-501/mut.log`
(mutations D and M3); `sed -n 76,97p src/refmatrix/search.py`; `sed -n 247,270p
src/refmatrix/search.py`. Caveat stated plainly: the live fleet does not exhibit the precondition
right now — all 8 stores are up with a readable `catalog.read.duckdb`, and `rmx canon find
refmatrix` returning 7 of 8 projects with no skipped line is correct (I checked `thiquet` through
its own daemon: `context refmatrix` → `(unknown symbol)`, so it genuinely does not host it). The
defect is proven on the probe, not on today's weather.
**Fix:** stop swallowing one frame down. Give `_replica_bundle` a strict twin — or an
`on_error: list | None` parameter — so the two `except` blocks append `(root, reason)` instead of
returning a bare `{}`, and have `federated_concept` / `_where_one_project` read it. Then rewrite
the two tests to break the real thing: delete `catalog.read.duckdb` under an up-classified root
(no patching at all) and assert the reason, which is the state the probe used. Effort: under an
hour; the reason string already exists at `search.py:65`.
**Pattern match:** YES — the guard-cannot-fire PATTERN filed in plan-4 r3, and
[[bsd-impressions#imp-consolidated-2]] (a fix at the quoted line while the frame below keeps the
bug). New shape worth naming: the collaborator's docstring was the contract the test violated.

rel: contradicts -> [[plan-3-verbs-parity#decisions-log]]
rel: contradicts -> [[project-profile#constraints]]

### BULLSHIT (partial bound, 8th): `rmx memory promote` still costs **180.2 s** — the same number — because the budget the fix added covers the project read and the global write takes `hub.global_call`'s default `timeout=60, retries=2`, the exact cost that function's own docstring says `retries=0` exists to prevent {#b-2}

**File:** `src/refmatrix/verbs.py:1152-1156` (`hub_mod.global_call("memory_add", {...})`, no
`timeout=`, no `retries=`), `src/refmatrix/cli.py:10362-10365` (the CLI passes
`timeout=_verbs.MEMORY_READ_BUDGET_S` = 10 s), `src/refmatrix/hub.py:152-165` (`global_call`
defaults, and the docstring that names both costs)
**What:** Round 7 budgeted the promote path's *project-side* leg
(`budgeted = is_read or action == "promote"`, `_left(30.0)`, `retries=0`). The global write two
lines below was left on the library default. `global_call`'s docstring states what that costs:
"`ensure_global_daemon` pings bare and waits up to 30 s for a spawn, all outside the caller's
deadline" and "`retries=0` also keeps a held global store from costing 3× the timeout
(bsd-plan2-r6 #b-1)". The promote leg takes the default on both counts.
**Why it's bullshit:** probe P4 — a REAL spawned daemon serving the project store (so the read
leg succeeds in milliseconds) and a `_PingOnlyDaemon` at the patched `global_store_root()`:

```
P4 promote, project healthy + GLOBAL held: 180.2s exit=1
   out='Error: global store memory_add failed: timed out'
   global ops=['ping', 'memory_add', 'memory_add', 'memory_add']
```

**180.2 s** is r6 #b-2's number to one decimal, on the command r6 #b-2 was filed against, three
rounds after the plan began removing it — the leg moved, the wall clock did not. The command's
stated bound is 10 s. With the global daemon *absent* rather than held, `ensure_global_daemon`'s
spawn wait is added on top (its own docstring: up to 30 s), so the worst case is ~211 s. Two
things are genuinely better than r6 and I want them on the record: the message is no longer empty
(`global store memory_add failed: timed out` is the verb's typed wrapper doing its job), and the
retried write cannot duplicate a row, because `Store.add_memory` is an upsert on name
(`store.py:2082-2093`) — this is a latency finding, not a corruption one.
**Evidence:** `pytest-bsd-plan3-r7-probe.log` (P4); `sed -n 1148,1160p src/refmatrix/verbs.py`;
`sed -n 152,166p src/refmatrix/hub.py`; `pytest-bsd-plan3-r7-probe-states.log` for the
project-held leg now answering in 10.0 s.
**Fix:** `hub_mod.global_call("memory_add", {...}, timeout=_left(30.0), retries=0)` — the same
two keywords the read leg six lines up already passes, with `_left` already in scope — and let the
`except Exception` below keep turning it into the typed `VerbError`. The absent-global case then
fails fast with the wording `global_call`'s docstring prescribes instead of spawning inside the
command. One test: the existing `_PingOnlyDaemon` at a patched `global_store_root()` (registry row
55 already covers that fixture), asserting the whole command finishes inside the budget. Effort:
one line plus one test.
**Pattern match:** YES — [[bsd-pattern-partial-bound]], 8th sighting, and
[[bsd-impressions#imp-partial-bound]] in its purest form: the bound was put on the leg the finding
quoted, and the sibling three lines down kept the cost.

rel: contradicts -> [[bsd-pattern-partial-bound]]
rel: contradicts -> [[project-profile#constraints]]
rel: contradicts -> [[plan-3-verbs-parity#decisions-log]]

### SKETCHY (a false universal, and the renderer now exists twice): "`canon find` was the last consumer discarding a `skipped` list" is disproved by one grep — the web omnibox drops it, and the fix was pasted rather than extracted {#s-3}

**File:** `src/refmatrix/ui/server.py:451-462` (`/api/where`, `/api/query`, `/api/concept` return
the fan-out dict whole), `src/refmatrix/ui/static/app.js:567-572` (`doWhere` reads
`r.result?.results` only and renders `no hits`), against `src/refmatrix/cli.py:4245-4257`
(`canon_find`'s new renderer) and `:8307-8319` (`locate_cmd`'s, verbatim the same six lines)
**What:** Two claims in one commit. (a) `canon find` was not the last consumer: `search.py`'s own
module docstring calls the module "the engine behind the web omnibox, `rmx where`, and the MCP
`where` tool", and `grep -rn skipped src/refmatrix/ui/` returns **nothing** — the server passes
`skipped` to the browser and `app.js` prints `no hits` for a store it could not reach. The MCP
tools are fine (`verbs.where` / `verbs.search` return the dict whole, so an agent sees the field);
the browser is the surface that drops it. (b) the fix is a verbatim copy of `locate_cmd`'s
renderer — the stderr echo loop and the `(N stores skipped — see stderr)` suffix now live at two
call sites with no shared helper, which is the shape the lead flagged after `_grep_run` inlined a
copy of `_grep_rg_fallback` and a round patched both.
**Why it's sketchy rather than BULLSHIT:** the UI leg was never named in a finding, and the
server end is correct — the field crosses the wire. But the commit's own universal is what makes
it checkable, and the third copy of the renderer is now owed to whoever fixes the omnibox.
**Evidence:** `grep -rn "skipped" src/refmatrix/ui/` → no matches; `sed -n 554,590p
src/refmatrix/ui/static/app.js`; the two renderers side by side at `cli.py:4245` and `:8307`.
**Fix:** extract `_echo_skipped(res) -> str` in `cli.py`, call it from both commands, and add one
line to `doWhere` (and the concept/query handlers) rendering `r.result?.skipped` as a muted row.
One UI assertion in the server test, one `CliRunner` assertion per command.
**Pattern match:** YES — the false-universal family and
[[bsd-impressions#imp-quoted-line-sibling]].

rel: contradicts -> [[project-profile#constraints]]

### SKETCHY (3rd registry gap in this plan): `tests/test_plan3_remedy_r6.py` — 11 tests, eight new patch targets — is named nowhere in the mock registry, and the one healthy-path claim it makes rests on a monkeypatched socket with no real-daemon twin {#s-4}

**File:** `workflow/test_mock_registry.md` (no row names `test_plan3_remedy_r6.py`; `grep -rn
test_plan3_remedy_r6 workflow/test_mock_registry.md` → no matches), against
`tests/test_plan3_remedy_r6.py:57-82` (the `answering` fixture: `discovery.daemon_status` dict +
`dm.call` canned + `cli._root`), `:100-110` (`verbs.attach_context` pass-through spy), `:147-160`
(`verbs.memory` spy), `:200-212` / `:216-230` (`search._replica_bundle` raising fake),
`:232-247` (`hub.global_call` raising + `hub.global_store_root`), `:249-269`
(`search._where_one_project` sleeper + `search.WHERE_FANOUT_S`), plus `search._live_roots` and
`discovery.discover_roots` in four tests
**What:** CLAUDE.md `#no-mocks` classifies every double in `workflow/test_mock_registry.md`, and
`#before-commit` requires the registries current. r6 #m-5 recorded r5 as "the first plan-3 round
with no registry gap"; round 7 added a whole file and no row. Rows 40/49/55/57/63 cover the same
*targets* for other files, so the fix is mostly appending this filename to five existing rows plus
one new row for `verbs.attach_context` and one for `search._replica_bundle`.
**Why it matters beyond bookkeeping:** the `search._replica_bundle` fake is the one that hides
[[#b-1]], which is exactly what the registry's own graduation column is for; and `answering`
replaces the socket for the only test of `--degree`'s healthy path, so the suite cannot prove the
flag against a real daemon. I verified that path myself on a spawned daemon (0.1 s) and live
(3.6 s), so the behaviour is real — but the repo's own evidence for it is a canned `dm.call`, and
registry row 40 promises the opposite ("the federated verbs run their REAL per-project path
against a real spawned daemon").
**Why SKETCHY and not BULLSHIT:** this is the 3rd plan-3 registry gap (r3, r4, r5-clean, r7), and
both prior filings were MEH, so the MEH→SKETCHY step lands here; one more puts it at BULLSHIT.
Saying the arithmetic out loud rather than inflating the blocker count with a docs gap.
**Fix:** seven registry edits, and one real-daemon `--degree` test on the `realdaemon` fixture
shape my probe used (`Store.init` + two memories + `spawn_daemon_subprocess`, assert the bundle
renders and the exit is 0) to graduate `answering` for that one case.
**Pattern match:** YES — [[bsd-impressions#imp-registry-three-strikes]] ("registry untouched + tests
added = unregistered on sight").

rel: contradicts -> [[claude#no-mocks]]

### MEH: `memory promote` is the one twin of the four that does not subtract the partition probe from its budget — measured 15.0 s against a stated 10 s {#m-5}

**File:** `src/refmatrix/cli.py:10356-10365` (`timeout=_verbs.MEMORY_READ_BUDGET_S`, flat)
against `:10267-10275` (`memory_get`), `:10489-10500` (`memory_list`), `:10537-10548`
(`memory_search`) — each of which passes `max(0.5, _budget - (_time.monotonic() - _t0))`
**What:** `_memory_intent(..., partition_timeout=min(5.0, MEMORY_READ_BUDGET_S))` can spend 5 s
on the `partition_list` probe before the verb's deadline even starts, and promote then hands the
verb the full 10 s. Measured on `_PingOnlyDaemon` without a replica: **15.0 s**, ops
`['ping','partition_list','ping','ping','memory_get']`, where `memory get` in the same state took
10.0 s. The three siblings carry `_t0`; promote does not.
**Evidence:** `pytest-bsd-plan3-r7-probe-states.log`, the `[ping/replica=False]` pair.
**Fix:** copy the siblings' two lines — `_t0 = _time.monotonic()` before `_memory_intent`, then
`timeout=max(0.5, _budget - (_time.monotonic() - _t0))`. The existing
`test_promote_on_a_held_writer_says_busy_within_the_budget` only needs its `< 36.0` tolerance
tightened to the budget to hold it.

### MEH: round 7 left no row in the plan's decisions log, and Q17 — the row [[#b-1]] contradicts — was not amended {#m-6}

**File:** `workflow/plans/plan-3-verbs-parity.md:87-90` (the log ends at Q18, dated 2026-09-15)
**What:** Rounds 5 and 6 each recorded their contract as a Q row; round 7 recorded nothing, so
`MEMORY_CONTEXT_TAIL_S`, the `budgeted = is_read or promote` rule, the "no replica fallthrough on
promote" decision and the `canon find` render exist only in the commit body and the
implementation summary. Q17 meanwhile asserts the pooled fan-outs name "every per-leg failure
`_where_one_project` reports (its 3 s `memory_search` on a held writer; **the replica bundle**)",
and the replica-bundle half is false at HEAD.
**Fix:** a Q19 for round 7's four decisions, and an amendment on Q17 scoping its claim to the
legs that can actually report — which the [[#b-1]] fix will widen again.

## Observations (not findings) {#observations}

- **The remedy's own evidence checks out where I could re-run it.** Mutations A, C, D, E and M3
  each fail exactly the test the summary's table names, and C's failure takes 210 s — the summary
  said B takes 240 s for the same reason, which is consistent. The RED/GREEN logs are present and
  the 7× GREEN speedup really is the bound. {#obs-remedy-evidence}
- **No post-remedy drift.** `search.py` is untouched since `b252a09`; `verbs.py` and `mcp.py` were
  touched once (the `memory brief` feature, `7cc26d8`), which added `brief` to
  `MEMORY_READ_ACTIONS` with an `and not (action == "brief" and save)` clause and routes its CLI
  twin through `_verbs.memory` — the twin inventory held across 80 commits. {#obs-no-drift}
- **The read-path inventory is now five and all five go through the verb:** `get`, `list`,
  `search`, `recall`, `promote`, plus `brief`. The remaining `_memory_daemon_call` sites in the
  group are writes (`reclassify`, `retag`, `link`, `score`, `forget`, `compile_apply`,
  `bulk_forget`) and the dense legs inside `memory_recall`, which carry that command's own
  deadline. {#obs-inventory}
- **My probes touched no live store.** Every simulation ran on a `mkdtemp` root and every
  held-writer case asserts `catalog*.duckdb` size+mtime unchanged; the three live commands
  (`memory get --degree 1`, `canon find`, `projects`) were reads on the deployed 0.73.0 binary,
  never a dev-venv `rmx`. The two probe files were deleted and `git status` is clean. {#obs-readonly}

## Verdict {#verdict}

**DIRTY — 6 findings (2 BULLSHIT, 2 SKETCHY, 2 MEH). Plan-3 may NOT flip to `completed`.**

Round 7 is the strongest remedy in this plan's lineage on the two findings it was ordered to fix.
`memory get --degree 1` runs — on a real spawned daemon, on the deployed build against the live
store, and in all four simulated daemon states — and my mutation reproduces the exact `NameError`
it used to raise, so the flag is guarded for the first time. `memory promote` answers the held
project writer in 10.0 s with a typed, non-empty message where it used to spend 180.2 s and print
nothing, and the verb's read is single-attempt under the action's budget. `canon find` names a
busy store, and that render is load-bearing.

What blocks the plan is that both of the round's *smaller* fixes are fixes to the wrong frame.
The `skipped` reason added to `federated_concept` — and the matching one in `_where_one_project`,
r6 #s-4's M3 leg — sit directly above `_replica_bundle`, whose documented contract is to return
`{}` for every failure, so neither `except` can run; the probe prints `skipped=[]` and `rmx canon
find` still answers "no live project hosts X" for a store whose replica cannot be opened, which is
the sentence the finding was written to delete. Both certifying tests patch `_replica_bundle` into
raising, which the real one never does. And `memory promote` still costs **180.2 s** — r6 #b-2's
number, to the decimal — on the write leg two lines below the read the fix bounded, taking the
default that `hub.global_call`'s own docstring says `retries=0` exists to avoid.

Round 8 is small and all of it is named above: three lines in `_replica_bundle` so a failed
replica read carries a reason, two keywords on the `global_call`, two lines of `_t0` arithmetic in
the promote twin, one extracted renderer plus one `app.js` line, seven registry edits, and a Q19.
The two tests that need rewriting should delete `catalog.read.duckdb` instead of patching a
collaborator — that is the input the probe used, and it needs no doubles at all.

rel: contradicts -> [[bsd-pattern-partial-bound]]
rel: contradicts -> [[project-profile#constraints]]
