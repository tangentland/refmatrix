---
gmd: "0.1"
id: bsd-plan3-verbs-parity-r6-ffed3df
title: "ch-bsd findings — plan-3 verbs parity r6 (dfc0e62..ffed3df, remedy 26404fe): all five r5 findings closed and reproduced on both simulations; `memory get --degree` crashes with a NameError on the deployed build and `memory promote` still waits 180 s behind a bare ping"
tags: [bsd, findings, plan-3, verbs, cli, mcp, remedy-r6]
severity: BULLSHIT
plan: plan-3-verbs-parity
task: task-3.1-plan-3-verbs-parity, task-3.2-plan-3-verbs-parity, task-3.3-plan-3-verbs-parity
metadata:
  node_type: bsd-report
  commit: ffed3df
  remedy_commit: 26404fe6377bcd69df7ef9c3d1ac8c09b2f36762
  range: dfc0e62..ffed3df (plan-3 content = 26404fe; the range also carries plan-4 r4, plan-2 r8/r9, bug-014/015 and the hub-install race, audited by their own rounds)
  head_at_audit: ffed3df
  deployed: 0.69.1 at ~/refmatrix (ffed3df), `rmx version -v` code=/Users/tholley/refmatrix/src, daemon pid 16448 supervised, hub pid 13847, fleet 8/8 v0.69.1, `rmx install-hooks --check` in sync
  verdict: DIRTY
  findings: 6
---

# ch-bsd findings — plan-3 remedy round 5 re-review (merge remedy-plan3-r5-plan4-r3) {#root}

**Commit:** ffed3df (merge chain over 26404fe `fix(supervisors,twins,fan-outs): plan-3 round 6 and plan-4 round 4 remedies; the hook's rerank pool is capped`)
**Date:** 2026-09-15 05:27 PDT (audit 05:50–06:17)
**Author:** Todd Holley / Fable 5.1 / orchestrator
**Files changed (26404fe):** 26 (plan-3 src: `cli.py`, `search.py`, `verbs.py`; tests: 1 new (201 lines), 3 adjusted; summary round-6 block, plan Q15–Q18, registry ±4)

rel: amends -> [[bsd-plan3-verbs-parity-r5-dfc0e62]]
rel: evidence-for -> [[plan-3-verbs-parity]]
rel: evidence-for -> [[impl-remedy-plan-3-verbs-parity]]

## Method {#method}

Every check below was run by me at HEAD ffed3df on the dev tree (`.venv-eval`), never against the live store. Suites: `workflow/review-output/pytest-bsd-plan3-r6-suites.log` — **169 passed in 343 s** (`test_plan3_remedy_r5`, `_r4`, `_r3`, `_r2`, `test_plan3_remedy`, `test_verb_parity`, `test_mcp_parity`, `test_verbs_migrated`, `test_locate`, `test_surface_parity`, `test_plan2_remedy`). Probes on both registered simulations, each in four states (`_PingOnlyDaemon` / `_SilentDaemon` × replica present / absent): `pytest-bsd-plan3-r6-probe.log` (every read twin, every `memory` verb action, the MCP recall defaults, all three fan-outs, with a per-command op log and a `catalog*.duckdb` size+mtime check), `-probe-concept.log`, `-probe-promote.log`, `-probe-siblings.log`. Mutations on a scratch copy under `PYTHONDONTWRITEBYTECODE=1`, each restored and the copy diffed back to the dev tree at the end (`src identical`): `pytest-bsd-plan3-r6-mutations.log` (M1–M8). Live reads on the idle deployed fleet for the partition-override parity question. {#method-body}

## Round-5 findings, verified {#r5-status}

- **#b-1 CLOSED — and reproduced on both simulations.** `rmx memory list --limit 3` and `rmx memory search held` on a `_PingOnlyDaemon` holding the writer with a replica present: **10.0 s each, exit 0, rows served from the replica**, ops exactly `['ping','ping','memory_iter']` / `['…','memory_search']` — ONE op attempt, not the library's three (r5: 190.2 s each). On `_SilentDaemon`: 0.5 s. Slot untouched in all four states. My mutation **M1** puts the *search* twin (not the `list` twin the remedy's own P3-A mutated) back on the bare ping gate → 3 tests fail, so both twins are guarded, not just the one the mutation table names. {#v-b1}
- **#s-2 CLOSED — including the state the finding named.** `_read_store` on an UP daemon without a replica raises one read-worded error; `memory get` / `list` / `search` / `recall` on `_PingOnlyDaemon` without a replica all print exactly one line (`daemon up pid=… — and there is no read replica yet …`), never "reading the replica", never `snapshot not built`, slot untouched, 10.0 / 10.0 / 10.0 / 30.0 s. Mutation **M6** (hand the write proxy back for an UP daemon) fails the suite. {#v-s2}
- **#s-3 CLOSED for the three fan-outs Q17 enumerates — see [[#s-3]] for the fourth.** Held writer: `federated_query` **20.0 s**, `projects: []`, `skipped: [{… 'daemon busy: query did not answer within 20s (TimeoutError)'}]`, one `query` op (r5: 60.2 s and dropped from both lists); `federated_where` 3.0 s with the memory leg named; `federated_locate` 0.0 s and `skipped: []` — honest, it asks no daemon, and the r5 test file says so on both sides. Mutation **M8** (drop the query skip) fails its test. {#v-s3}
- **#m-4 CLOSED.** `rmx_memory_recall({'recent': True, 'partition': 'p-given'})` on a held writer: ops `['ping','memory_recent']` — no `partition_list` probe; without the partition: `['ping','partition_list']`. Mutation **M7** (verb ignores the passed partition) fails `test_recall_twin_probes_the_partition_once…`. {#v-m4}
- **#m-5 CLOSED.** Every monkeypatch target in `tests/test_plan3_remedy_r5.py` (`cli._root`, `verbs.memory`, `discovery.discover_roots`, `search._locate_one_project`, `search.LOCATE_FANOUT_S`) now has a registry row. First plan-3 round with no registry gap. {#v-m5}
- **Parity gate, `partition` in the recall no-twin set — legitimate.** `test_no_twin_exclusions_are_honest` permits an exclusion only when the paired click command has no same-named option: `rmx memory recall` has none (`-p` is on the `rmx` group), so the exclusion is declared, not hidden, and the gate still fires the day a `--partition` option is added to the subcommand. Behaviour matches live on real partitions: `rmx -p sessions-refmatrix memory recall --recent` returns session rows, `-p memory-viascope` returns `[]`, and `list` / `search` / `get` route the same way. {#v-parity}
- **Deferral sweep** over 26404fe's `+` lines in `src/` and `tests/` (hard and soft families) → two hits, both innocent: a docstring saying "a restart is not a wedge" and the test module's own "round 6 of plan 3". **Plan status honest:** `in-progress`, plan-of-plans `in-progress`. **Deploy:** 0.69.1 at ffed3df, code path `/Users/tholley/refmatrix/src`, hooks in sync, fleet 8/8. Live idle reads: `memory list` 0.19 s, `search` 0.19 s, `get` 0.19 s, `recall` 0.17 s, `locate` 0.22 s. {#v-misc}

## Findings {#findings}

### BULLSHIT (crashed command, shipped): `rmx memory get <name> --degree 1` dies with a raw `NameError` on the DEPLOYED build, in every daemon state {#b-1}

**File:** `src/refmatrix/cli.py:9708` (`if daemon_mod.ping(root):` inside `memory_get`'s `--degree` tail), against `:9662-9690` (the `memory_get` body the r5 remedy rewrote, which no longer imports `daemon_mod`)
**What:** The r5 remedy (a035117, in dfc0e62) replaced `memory get`'s daemon branch with `_verbs.memory(action="get", …)` and removed the function-local `from refmatrix import daemon as daemon_mod`. The `--degree` tail thirty lines below still calls `daemon_mod.ping(root)`. There is no module-level `daemon_mod` in `cli.py`, so the name is unbound at that line for every invocation with `--degree > 0`.
**Why it's bullshit:** Run against the live healthy daemon on the deployed 0.69.1:

```
$ rmx memory get feedback_dry_run_match_real_cost --degree 1
  File "/Users/tholley/refmatrix/src/refmatrix/cli.py", line 9708, in memory_get
    if daemon_mod.ping(root):
       ^^^^^^^^^^
NameError: name 'daemon_mod' is not defined. Did you mean: 'daemon_job'?
```

The body prints first, then the command crashes with a Python traceback — so `--degree` is a dead flag on `memory get` and has been since the r5 remedy was deployed. `git show 768f868:src/refmatrix/cli.py` has the import at line 9400; `git show dfc0e62:` does not, and the `daemon_mod.ping` line survives at 9577. The held-writer probe reaches it too (`pytest-bsd-plan3-r6-probe-siblings.log`: 10.1 s, replica rows rendered, then `NameError`). 169 tests pass at HEAD because no test invokes `memory get --degree`, and round 6 rewrote the two sibling twins in the same file without exercising the twin it was copying. I did not catch it in r5 either — the r5 probe ran `memory get` without the flag.
**Evidence:** `pytest-bsd-plan3-r6-probe-siblings.log`; the live run above; `sed -n 9700,9712p src/refmatrix/cli.py`; `git show 768f868:src/refmatrix/cli.py | grep -n "daemon as daemon_mod"` inside `memory_get` → present, at dfc0e62 → gone.
**Fix:** restore `from refmatrix import daemon as daemon_mod` in `memory_get` (one line), or route the tail through `_verbs.attach_context` the way the recall twin does. One test: `memory get <name> --degree 1` against a healthy spawned daemon asserting the context block renders and exit is 0. Effort: minutes.
**Pattern match:** YES — [[bsd-impressions#imp-consolidated-1]] (dead flags — a flag that cannot run), and the tests-prove-existence family: the flag has no test at all.

rel: contradicts -> [[project-profile#constraints]]
rel: contradicts -> [[plan-3-verbs-parity#decisions-log]]

### BULLSHIT (partial bound, 7th; verb bypass, 2nd in plan-3): `rmx memory promote` waits 180.2 s on a held writer and ends with an empty message — the third read path of the `memory` group, behind the same bare ping gate #b-1 was filed for {#b-2}

**File:** `src/refmatrix/cli.py:9744-9750` (`memory_promote`: `if daemon_mod.ping(root): resp = _memory_daemon_call("memory_get", args)`), `:9513-9525` (`_memory_daemon_call` defaults `timeout=60.0, retries=2`), `src/refmatrix/verbs.py:1100-1104` (`memory(action="promote")`: `_call(root, "memory_get", …, timeout=30.0)` at the default `retries=2`)
**What:** Round 6 routed `list` and `search` through the bounded verb because a held writer answers ping. `memory promote` reads the same row through the same op with the same gate and was not touched, and the `promote` action of the same verb — which `verbs.memory` already implements — is never called by it.
**Why it's bullshit:** Held writer with the replica holding the row (`pytest-bsd-plan3-r6-probe-promote.log`, `-probe-siblings.log`):

| path | wall | ops | outcome |
|------|------|-----|---------|
| `rmx memory promote held_row` | 180.2 s | `ping`, `memory_get` ×3 | exit 1, **output empty** — an unhandled `TimeoutError` (a raw traceback in a terminal) |
| `verbs.memory(root, "promote", name=…)` | 90.2 s | `ping`, `ping`, `memory_get` ×3 | `VerbBusyError` after 3 × 30 s |

That is r5 #b-1's number one command over, and the MCP path is 3× its own stated bound: Q11 says the promote read goes through `_call(retries=0)`, and this `_call` takes the library default. The commit title says "twins"; two of the group's four read paths are bounded, the third waits three minutes and says nothing, the fourth is [[#b-1]].
**Evidence:** the two probe logs above; `sed -n 9736,9760p src/refmatrix/cli.py`; `sed -n 1098,1106p src/refmatrix/verbs.py`; `grep -n "_verbs.memory(" src/refmatrix/cli.py` → three sites (get, list, search), none of them promote.
**Fix:** `memory_promote` → `_verbs.memory(root, action="promote", partition=_resolve_partition(), timeout=…)` with the `get` twin's typed busy/absent handling; give the verb's promote read `retries=0` under the action's budget. One `_PingOnlyDaemon` test asserting a typed busy message inside ~30 s. Effort: under an hour — the `get` twin is the template, again.
**Pattern match:** YES — [[bsd-pattern-partial-bound]] (7th), [[bsd-impressions#imp-verb-bound-twin-bypass]] (the impression written after r5 says: list the twins from the click tree and grep each for the verb call — `promote` is on that list).

rel: contradicts -> [[bsd-pattern-partial-bound]]
rel: contradicts -> [[project-profile#constraints]]
rel: contradicts -> [[plan-3-verbs-parity#decisions-log]]

### SKETCHY (the universal is false; producer with no reader): the fourth fan-out, `federated_concept`, drops a busy store — `rmx canon find X` answers "no live project hosts X" {#s-3}

**File:** `src/refmatrix/search.py:247-263` (`federated_concept`: `_live_roots()` then a per-root `except Exception: pass`, returning `skipped`), `src/refmatrix/cli.py:3810-3823` (`canon_find`: reads `res["projects"]`, never `res["skipped"]`)
**What:** The commit message says "every fan-out names the stores it did not hear from" and Q17 enumerates three. The fourth fan-out in the same module produces a `skipped` list that its only consumer discards, and keeps the silent per-root swallow the other three lost.
**Why it's sketchy:** `pytest-bsd-plan3-r6-probe-concept.log`, `_SilentDaemon` with a replica:

```
federated_concept("held_row") -> projects=0 skipped=[{... 'daemon busy pid=28564 (alive, not answering)'}]
rmx canon find held_row       -> "no live project hosts held_row"
```

That is verbatim the r3 #b-2 defect (`rmx locate` turning a busy daemon into "no matches") which this plan fixed for `locate` and left standing one command over: the operator is told a concept exists nowhere when the truth is that the store was busy. The r3 test `test_federated_query_and_concept_carry_skipped` asserts the dict carries the key — existence, not rendering. SKETCHY rather than BULLSHIT because the code is untouched by this diff and Q17's enumeration does not name `canon find`; the commit's universal does.
**Evidence:** the probe log above; `sed -n 247,264p src/refmatrix/search.py`; `sed -n 3806,3824p src/refmatrix/cli.py`.
**Fix:** in `canon_find`, echo each `skipped` row to stderr and append "(N stores skipped — see stderr)" to the empty message, exactly as `locate_cmd` does at `cli.py:7752-7763`; give `federated_concept`'s per-root `except` a reason instead of `pass`. One `_SilentDaemon` test asserting the busy pid appears in the output. Effort: minutes.
**Pattern match:** YES — [[bsd-impressions#imp-consolidated-2]] and the quoted-line-sibling family (5th sighting).

rel: contradicts -> [[plan-3-verbs-parity#decisions-log]]
rel: contradicts -> [[project-profile#constraints]]

### SKETCHY (guards that cannot fail): three of the four "said, never mute" branches this commit added to `federated_where` are guarded by nothing {#s-4}

**File:** `src/refmatrix/search.py:146-148` (the replica-bundle leg's reason), `:230-239` (the global memory leg's reason), `:212` (`_name_stragglers(futs, done, skipped, WHERE_FANOUT_S)`)
**What:** Q17 says every fan-out names every store it did not hear from, and the summary's mutation table offers P3-C2 ("pool stragglers unnamed") and P3-C3 ("the where memory leg silent") as proof. P3-C3 covers the memory leg only, and the straggler mutation is caught only at the `locate` call site — by a test that replaces `_locate_one_project` with a sleeper.
**Why it's sketchy:** my mutations on the scratch copy (`pytest-bsd-plan3-r6-mutations.log`):

| mutation | result |
|----------|--------|
| M3 — replica-bundle leg back to `except Exception: pass` | 4 passed, 0 failed |
| M4 — global memory leg back to `except Exception: pass` | 4 passed, 0 failed |
| M5 — delete `_name_stragglers(...)` from `federated_where` entirely | 4 passed, 0 failed |

The behaviour is real at HEAD (the probe shows the memory-leg reason), but three of the four legs can be silently reverted with the suite green, on a remedy whose whole subject is "no silent failures in a fan-out". The `_where_one_project` replica-bundle leg is the unbounded one (`build_context` on a cold big store), so it is also the leg most likely to produce a straggler in the field.
**Evidence:** the mutation log (M3/M4/M5); `grep -n "federated_where" tests/*.py` → one test, asserting the memory leg only.
**Fix:** one test per leg on the held-writer fixture (bundle raise → reason; global root patched to a held store → reason) plus a `WHERE_FANOUT_S`-shrunk straggler case mirroring the locate one.

### MEH: the MCP `rmx_memory(action="recall", partition=…)` forwarding Q18 added has no guard {#m-5}

**File:** `src/refmatrix/verbs.py:1060-1063` (`_RECALL_FORWARD` gained `"partition"`), `tests/test_verb_parity.py:57` (`rmx_memory` PAIRING is `"ALL"`, so the gate compares nothing for this verb)
**What:** Mutation **M2** removes `"partition"` from `_RECALL_FORWARD` — the MCP dispatcher then silently drops the caller's partition and re-probes — and **59 tests pass, 0 fail**. The wiring is real (probe: `rmx_memory({'action':'recall','partition':'p-given'})` → ops `['ping','memory_recent']`, no probe); nothing proves it stays.
**Fix:** assert the forwarded partition in the r5 file (the `_PingOnlyDaemon` op log already distinguishes the two cases: `['ping','memory_recent']` vs `['ping','partition_list']`).

### MEH: with a replica present the interactive `memory recall` now spends its WHOLE budget on the stalled daemon before reading the replica — 30.0 s where r5 measured 15.0 s {#m-6}

**File:** `src/refmatrix/cli.py:10365` (`_replica = _reader_store() if hook_mode else None`), `:10374-10379` (`_verb_timeout = _left(budget)` when `_replica is None`), `verbs.py:695` (the probe the twin now skips)
**What:** Removing the second partition probe (#m-4) handed the freed seconds to the stalled op, not to the answer: probe A at HEAD shows `rmx memory recall --recent --json --timeout 30` on a held writer WITH a replica taking **30.0 s** (ops `['ping','memory_recent']`), against the 15.0 s r5 measured when two probes burned the budget first. The result is correct and the budget is honoured — the hook modes are unaffected (they take `_replica` first and cap the daemon slice at `RECALL_DAEMON_SLICE_S` = 1.5 s) — but nobody should read "one probe per command" as "faster to the rows".
**Fix:** either apply a `RECALL_DAEMON_SLICE_S`-style slice when a replica is already on disk in the non-hook path too, or record the trade in Q18 so the next round does not re-file it.

## Observations (not plan-3 findings) {#observations}

- **The remedy's own evidence checks out.** RED `pytest-plan3-r6-red.log` 12 failed / 1 passed (the one pass is the `get` probe count, which is what #m-4 said); GREEN 14 passed; the mutation log's P3-A/B/C2/D and the two redo lines each fail the test they name, and the void first P3-C / P3-C3 attempts are marked as void in the summary. The regression log's 9 failures are the legacy-contract tests the commit body says were updated afterwards; all of them pass at HEAD in my 169-test run. {#obs-remedy-evidence}
- **An unknown `-p` silently reads the default partition:** `rmx -p nonexistent-xyz memory list` returns the project's rows rather than an empty set or an error (live, deployed). Pre-existing store behaviour, outside this diff, but it is what made the partition-parity question hard to answer. {#obs-unknown-partition}
- **`federated_where`'s global-leg `except` re-calls `hub_mod.global_store_root()`** to build its reason; if that call is what raised, the fan-out dies instead of reporting. Unreachable in practice (it reads an env var and `Path.home()`). {#obs-global-except}
- **One leaked tmp-root daemon** was alive at audit start (`pgrep -f "daemon start --no-watch"` → 1, on a deleted root); bug-016's fixture fix cut the 22 of two nights ago to one. {#obs-leaked-daemon}
- **My own probes and mutations** ran only on `/tmp` roots and a scratch copy of `src/`; the copy was diffed back to the dev tree after the last restore (`src identical`). No write reached the live `.refmatrix/`, and every held-writer probe asserts the slot's size+mtime unchanged. {#obs-readonly}

## Verdict {#verdict}

**DIRTY — 6 findings (2 BULLSHIT, 2 SKETCHY, 2 MEH).**

Round 5 is closed everywhere it was quoted and, for the first time in this plan, closed on the simulation each finding named: both twins reach the replica in 10.0 s with one op attempt, a read never goes to the write proxy in any of the four daemon states, `federated_query` names the store it could not hear from in 20 s, the recall twin probes once, and the registry is complete. My mutations kill the search twin, the proxy fallthrough, the query skip and the partition forward.

What blocks the plan is the surface nobody listed. `memory get --degree 1` has been raising a bare `NameError` on the deployed fleet since the r5 remedy dropped an import thirty lines above the call that needed it — a user-facing flag that cannot run, with no test anywhere. `memory promote` is the third read path of the same command group, still behind the bare ping gate, still 180 s, and it ends with an empty message. Both are the twin-inventory the r5 impression asked for and neither round took it. Beyond that: the commit's "every fan-out" is four fan-outs, and the fourth turns a busy store into "no live project hosts"; three of the four new anti-silence branches in `federated_where` can be deleted with the suite green.

Round 7 is small: one import, one twin routed through the verb it already has, one `skipped` render in `canon find`, and four tests.

rel: contradicts -> [[bsd-pattern-partial-bound]]
rel: contradicts -> [[project-profile#constraints]]
