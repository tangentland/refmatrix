---
gmd: "0.1"
id: bsd-plan3-verbs-parity-r5-dfc0e62
title: "ch-bsd findings — plan-3 verbs parity r5 (768f868..dfc0e62, remedy a035117): all seven r4 findings closed at the quoted lines and reproduced on both simulations; the bound lives in the verb and two of the three read twins the remedy's own constant names never call it (190 s on a held writer)"
tags: [bsd, findings, plan-3, verbs, mcp, cli, remedy-r5]
severity: BULLSHIT
plan: plan-3-verbs-parity
task: task-3.1-plan-3-verbs-parity, task-3.2-plan-3-verbs-parity, task-3.3-plan-3-verbs-parity
metadata:
  node_type: bsd-report
  commit: dfc0e62
  remedy_commit: a0351175fbdc24306ee977c5d22dceb9d171a44c
  range: 768f868..dfc0e62 (plan-3 content = a035117; the range also carries plan-4 r3, plan-5 r3, plan-6 6.2/6.3 and the rmxgrep change, audited by their own rounds)
  head_at_audit: 7bca4bb (plan-3 files at HEAD differ from a035117 by one line in verbs.py — `global_recall_rows(..., retries=_retries)` from plan-2 r7 — and by the plan-2 r7 / bug-015 edits to the `memory recall` twin, both read here at HEAD)
  deployed: 0.69.1 at ~/refmatrix (7bca4bb), `rmx version -v` code=/Users/tholley/refmatrix/src, daemon pid 55186 supervised, `rmx install-hooks --check` in sync
  verdict: DIRTY
  findings: 5
---

# ch-bsd findings — plan-3 remedy round 4 re-review (merge remedy-plan-3-r4) {#root}

**Commit:** dfc0e62 (merge of a035117 `fix(verbs): every read and write verb bounded on a held writer; recall-state says busy (plan-3 r5)`)
**Date:** 2026-09-15 02:08 PDT (audit 03:05–03:30)
**Author:** Todd Holley / Fable 5.1 / orchestrator
**Files changed (a035117):** 11 (src: cli.py ±55, handoff.py ±27, hub.py ±9, verbs.py ±83; tests: 1 new (229 lines), 2 adjusted; summary, plan Q10–Q12, registry ±3, todo G11/G12)

rel: amends -> [[bsd-plan3-verbs-parity-r4-768f868]]
rel: evidence-for -> [[plan-3-verbs-parity]]
rel: evidence-for -> [[impl-remedy-plan-3-verbs-parity]]

## Round-4 findings, verified against code, tests, scratch mutations and probes {#r4-status}

Every check was run by me at HEAD 7bca4bb. Suites: `workflow/review-output/pytest-bsd-plan3-r5-suites.log` — **60 passed in 148 s** (`test_plan3_remedy_r4`, `test_verb_parity`, `test_plan3_remedy_r3`; the committed GREEN log carries one failure of the #m-6 test that was fixed and re-run singly, so the whole r4 file green at the committed code is this log, not that one). Probes on the two registered simulations: `pytest-bsd-plan3-r5-probe-a.log` (held writer `_PingOnlyDaemon` + silent socket `_SilentDaemon`: every verb, the promote, recall-state, the CLI `get` and `recall` twins), `probe-b.log` (the CLI `list`/`search` twins and the fan-outs on a held writer), `probe-c.log` (held writer WITHOUT a replica). Mutations on a scratch copy with `PYTHONDONTWRITEBYTECODE=1` and the copy diffed back to the dev tree after each restore: `pytest-bsd-plan3-r5-mutations.log`, `-mutations-b.log`. {#method}

- **#b-1 CLOSED.** `compose_recall_state` classifies through `discovery.daemon_status(root, retries=0)`; `daemon = {running, busy, pid}`. Probe A on the silent socket: `daemon={'running': False, 'busy': True, 'pid': 64902}`, anomaly `alive but not answering (busy: …)`, no "stale"; `rmx recall-state` prints `daemon busy pid 64902` (0.6 s). Held writer: ping answers → `running: True`. Dead pid keeps "stale" (`test_recall_state_still_says_stale_for_a_dead_pid`). The remedy's mutation A (bare ping) fails the test — confirmed in its log. `handoff.py` now has zero `daemon_mod.ping(`/`daemon_mod.call(` sites. Q10 records it. {#v-b1}
- **#b-2 CLOSED as quoted — and see [[#b-1]].** Held writer, probe A: `verbs.memory(get)` 10.0 s busy, `list` 10.0 s, `search` 10.0 s, `get timeout=3` 3.0 s; `VERBS["rmx_memory_recall"].run(root, {})` 10.0 s busy and `.run(root, {"timeout": None})` also 10.0 s (`Verb.run` drops None, so the MCP default 30 s applies); dense `memory_recall(query=…)` 10.0 s; CLI `memory get held_row` reaches the replica in 10.0 s; CLI `memory recall --recent --json` (default `--timeout 30`) reaches the replica in 15.0 s. The parity gate compares `rmx_memory_recall.timeout` (30.0) against the click default (30.0) for real (`rmx_memory_recall` is not `ALL`). My mutation M1b (read `_call` back to `retries=2`) fails `test_memory_get_cli_reads_the_replica_within_the_budget_on_a_held_writer` at 20.5 s and costs the verb 30.2 s with a given partition — the op-line bound is guarded by the CLI test (the verb-level test cannot see it: the partition probe spends the whole budget first). {#v-b2}
- **#s-3 CLOSED.** `_promote_digest` → `_call(root, "memory_add", …, timeout=30.0, retries=0)`; probe A held writer: `{'error': 'VerbBusyError: daemon op memory_add … did not answer within 30s … the daemon is busy'}` in 30.0 s, `slot untouched: True` (size + mtime of every `catalog*.duckdb`). The dense per-hit get goes through `_call(retries=_retries)`; remedy mutation C fails its test. {#v-s3}
- **#s-4 CLOSED.** `memory_partition` makes one `partition_list` attempt and raises `VerbBusyError` on a transport failure (probe A: 10.0 s, message names the op and pid); an ANSWERED `ok:false` keeps the project default with a warning. Remedy mutation B fails its test. Q11 records it. {#v-s4}
- **#s-5 CLOSED as quoted — see [[#m-5]].** Rows 41 and 48 name the r3 and r4 files and the patched seams. {#v-s5}
- **#m-6 CLOSED on the silent socket — OPEN on the held writer, see [[#s-2]].** `_read_store` raises the read-worded error on `VerbBusyError`; my mutation M2 (busy → pass) fails `test_read_on_a_busy_store_without_a_replica_is_read_worded`. Probe C on a `_PingOnlyDaemon` without a replica shows the two contradicting lines again. {#v-m6}
- **#m-7 CLOSED.** The canned `rmx_locate` result carries `CANARY-skip`; the wiring gate passes. {#v-m7}
- **hub.global_call / global_recall_rows `retries`:** wired end to end — `memory_recall` passes `retries=_retries` (the one-line HEAD delta from plan-2 r7), `global_recall_rows` forwards it, `global_call` forwards it to `daemon.call`; `test_global_recall_rows_passes_retries_to_the_hub_call` sees `retries=0`. {#v-global}
- **Deferral sweep** over a035117's `+` lines in `src/` and `tests/`: hard and soft families → 0 (the one hit is the test module's own docstring "round 5 of plan 3"). **Plan status honest:** `in-progress`, tasks 3.1–3.3 `pending`. **Deploy:** 0.69.1 at 7bca4bb, code path `/Users/tholley/refmatrix/src`, `install-hooks --check` in sync. Live at 03:15 (idle fleet): `memory get` 0.17 s, `memory list` 0.14 s, `memory search` 0.13 s, `recall-state` 0.22 s. {#v-misc}

## Findings {#findings}

### BULLSHIT (partial bound, 6th sighting; verb bypass): `rmx memory list` and `rmx memory search` wait 190 s on a held writer — the bound the remedy built lives in the `memory` verb, and those two twins never call it {#b-1}

**File:** `src/refmatrix/cli.py:9777-9800` (`memory_list`: `if daemon_mod.ping(root): resp = _memory_daemon_call("memory_iter", args)`), `:9814-9835` (`memory_search`, same shape), `:9423-9436` (`_memory_daemon_call` defaults `timeout=60.0, retries=2`), `src/refmatrix/verbs.py:980-981` (`MEMORY_READ_ACTIONS = frozenset({"get", "list", "search"})`, `MEMORY_READ_BUDGET_S = 10.0`)
**What:** The remedy generalised the read budget to three actions and wrote the constant naming them. `grep -n "_verbs.memory(" src/refmatrix/cli.py` → one site (line 9582, `memory get`). The `list` and `search` twins keep their own routing: a bare `daemon_mod.ping(root)` gate (0.5 s × 3) picks the daemon branch whenever the daemon ANSWERS a ping, then `_memory_daemon_call` runs `memory_iter`/`memory_search` at the library default — 60 s × 3 attempts — and the `else` branch with `_read_store()` is reachable only when the ping fails. A daemon holding the writer lock answers the ping.
**Why it's bullshit:** Probe B (`pytest-bsd-plan3-r5-probe-b.log`, `_PingOnlyDaemon`, replica present): `rmx memory list --limit 3` → **190.2 s, exit 1**; `rmx memory search held` → **190.2 s, exit 1** (10 s `_memory_intent` probe + 180 s of retried op), while `catalog.read.duckdb` with the row sat there the whole time and the same twins would have served it in 0.1 s had the ping failed. That is the r4 #b-2 number (390 s) one command over, on the two read surfaces the remedy's own constant lists. The commit title says "every read and write verb bounded on a held writer" — true of the verb, false for two of the three CLI reads it bounds, and the plan's thesis (task 3.2: "`memory_list` … or one `memory(action=…)`"; profile: "CLI and MCP expose it, never implement it") is exactly that these twins should not have their own routing. The MCP `rmx_memory` list/search are bounded (10.0 s in probe A); the CLI is not.
**Evidence:** probe-b log; `sed -n 9777,9800p src/refmatrix/cli.py`; `sed -n 9814,9835p`; `_memory_daemon_call` signature; PAIRING in `tests/test_verb_parity.py:57` pairs `rmx_memory` with `("memory", "get")` only, so the wiring gate cannot see `list`/`search`.
**Fix:** route both twins through `_verbs.memory(root, action="list"/"search", partition=_resolve_partition(), timeout=remaining, …)` with the same `except (VerbAbsentError, VerbBusyError)` → `_read_store()` fallthrough `memory get` has (the verb already returns `{"rows": …}`); drop the bare `ping` gates. One `_PingOnlyDaemon` test per twin asserting the replica rows arrive within 16 s. Effort: under an hour — the `get` twin is the template.
**Pattern match:** YES — [[bsd-pattern-partial-bound]] (6th: "the bound was put where the diagnosis pointed"), [[bsd-impressions#imp-plan3-r3-progress]] ("grep the decision's universal quantifiers against the file"), [[bsd-pattern-tests-prove-existence-not-wiring]] (PAIRING covers one action of a thirteen-action verb).

rel: contradicts -> [[bsd-pattern-partial-bound]]
rel: contradicts -> [[project-profile#constraints]]
rel: contradicts -> [[plan-3-verbs-parity#decisions-log]]

### SKETCHY (wrong simulation, again): #m-6 was closed on the silent socket; on a held writer without a replica the twins still say "reading the replica" and then die — because `_read_store` hands back the daemon proxy when the ping answers {#s-2}

**File:** `src/refmatrix/cli.py:572-587` (`_read_store`: busy → read-worded raise; absent → pass; **up → `_store()`**, which is the `_DaemonWriter` proxy), `:199-206` (`_DaemonWriter._get_reader`: "daemon is up but no lock-free reader is available yet"), `:9592-9593` (`memory get`: `s = _read_store()` then `click.echo("… reading the replica")`), `:10271-10272` (`memory recall --recent`, same order)
**What:** Q12 says "the twins print 'reading the replica' only after the replica opened". `_read_store()` returning without raising is taken as "the replica opened", but for a daemon that answers ping it returns the RPC proxy, and the first read on that proxy raises the reader error.
**Why it's sketchy:** Probe C (`_PingOnlyDaemon`, rotation layout, no `catalog.read.duckdb`): `rmx memory get x` → stderr `… the daemon is busy; reading the replica` then `Error: daemon is up but no lock-free reader is available yet (snapshot not built). Run rmx replica refresh and retry.` (10.0 s, exit 1); `memory recall --recent --timeout 5` → the same pair in 5.0 s. The second line is at least read-worded now (that half of #m-6 holds), but the two lines contradict each other exactly as r4 described, and the remedy's test is on `_SilentDaemon` only — the same file's `_PingOnlyDaemon` fixture was not run through this path. On a fresh store during its first daemon boot the socket is absent (busy via `pid_is_rmx`), so the silent-socket fix covers that window; the held-writer-without-replica state is a store whose daemon is up and mid-ingest before its first snapshot.
**Evidence:** probe-c log; `sed -n 572,587p src/refmatrix/cli.py`; `sed -n 199,206p`; `grep -n "_PingOnlyDaemon" tests/test_plan3_remedy_r4.py` → the `held` fixture is used by six tests, none of them the #m-6 test.
**Fix:** in the twins, take `_reader_store()` first and print "reading the replica" only when it is not None; otherwise raise the one read-worded message (the `_read_store` busy text, or the proxy's reader text) without the "reading the replica" line. Add the `_PingOnlyDaemon` no-replica case to `test_read_on_a_busy_store_without_a_replica_is_read_worded`. Effort: minutes.
**Pattern match:** YES — [[bsd-impressions#imp-socket-sim-probe]] (r4: "the wrong simulation was run" — repeated on the very finding that said so), MEH escalated to SKETCHY on the second sighting.

rel: contradicts -> [[plan-3-verbs-parity#decisions-log]]

### SKETCHY (silent failure in a fan-out, Q14 not honoured): `federated_query` on a held writer waits 60 s per store and drops it from BOTH `projects` and `skipped` {#s-3}

**File:** `src/refmatrix/search.py:215-234` (`federated_query`: sequential loop, `daemon_mod.call(root, "query", …, timeout=20.0)` at the library `retries=2`, `except Exception: pass`), `:147-166` / `:301-337` (`federated_where` / `federated_locate`: thread pools whose stragglers past 6 s / 8 s are dropped with `except Exception: pass`), `src/refmatrix/verbs.py:922` (`verbs.query` → `federated_query`)
**What:** Q14 says every fan-out returns `skipped: [{project, root, reason}]`. `_live_roots()` classifies BEFORE the op: a held writer answers the ping, lands in `roots`, stalls the op, and vanishes.
**Why it's sketchy:** Probe B: `search.federated_query("kind:memory")` with the held store as the only live root → **60.2 s** and `{'projects': [], 'skipped': []}` — no result, no reason, and on an eight-store fleet the loop is sequential (8 × 60 s worst case). `federated_locate` on the same root returned in 0.0 s with `skipped: []` because its pool abandons the stalled `memory_search` thread silently (bounded, but the store is still not reported). SKETCHY rather than BULLSHIT: the code is unchanged in this diff and r4 credited #b-2-r3 on the silent-socket state, where `_live_roots` does report; this is the held-writer half of the same decision.
**Evidence:** probe-b log; `sed -n 215,234p src/refmatrix/search.py`; `grep -n "except Exception" src/refmatrix/search.py` → 14 sites.
**Fix:** `federated_query`: `retries=0`, catch the transport failure and append `{"project": proj, "root": str(root), "reason": f"daemon busy: query did not answer within 20s"}` to `skipped`; the pools: after `as_completed` times out, append every unfinished future's root to `skipped` with "did not answer within 6s/8s". One `_PingOnlyDaemon` test per fan-out asserting the root is in `skipped` and elapsed < 25 s.
**Pattern match:** YES — [[bsd-pattern-partial-bound]] (a bound with a silent drop behind it), `no-silent-failures` in CLAUDE.md.

rel: contradicts -> [[plan-3-verbs-parity#decisions-log]]
rel: contradicts -> [[project-profile#constraints]]

### MEH: the "no second probe" applies to `memory get` only — `memory recall` on a held writer spends 5 s + 10 s of its 30 s on two `partition_list` probes {#m-4}

**File:** `src/refmatrix/cli.py:10106-10108` (`_memory_intent("memory_recall", partition_timeout=min(5.0, budget))`), `src/refmatrix/verbs.py:681` (`memory_recall`: `memory_partition(root, timeout=_left(10.0))` — the CLI does not pass the partition it just resolved)
**What:** Probe A: CLI `memory recall --recent --json` on a held writer reaches the replica in 15.0 s — bounded, correct, but 10 of those seconds are the verb re-probing what the twin probed (and guessed) five seconds earlier. In the hook modes (`--timeout 5`) the second probe is cut to zero by the deadline, so the always-on surface is unaffected.
**Fix:** pass `partition=_resolve_partition()` from the recall twin the way `memory get` now does (the verb accepts it). Also: no test guards the `get` twin's `partition=` either — my mutation M3 (drop it) passes the 16 s test because the deadline absorbs the second probe; if "no second probe" is a claim worth making, assert on the op count via the `_PingOnlyDaemon`'s connection log.

### MEH: registry rows for the r4 file are two seams short (second registry gap in plan-3) {#m-5}

**File:** `workflow/test_mock_registry.md:31` (`cli._root` row lists r3 and earlier — not `test_plan3_remedy_r4.py`, which patches it in four tests), `:48` (the r4 row names `hub.global_call`, `daemon.call`, `verbs._call`, `memory_partition`, `require_daemon` — not the `hub.global_store_root` / `hub.ensure_global_daemon` lambdas in `test_global_recall_rows_passes_retries_to_the_hub_call`, nor `discovery.store_name`)
**What:** Rule 3. r4 #s-5 was the first strike in plan-3 and was closed for the seams it named; the new test file added two more unlisted. The third strike escalates per the ledger's standing rule.
**Fix:** add the r4 file to row 31; add `hub.global_store_root` / `hub.ensure_global_daemon` / `discovery.store_name` to row 48.

## Observations (not plan-3 findings) {#observations}

- **The remedy's own evidence:** the three mutations in `pytest-plan3-r5-mutation.log` each fail the test they name (A → recall-state, B → memory_partition, C → promote); the RED log (10 failed / 2 passed, 22 min) finished at 02:09, one minute after the commit, so it ran concurrently with the GREEN run — on a scratch copy that is fine, and the numbers match r4's. {#obs-remedy-evidence}
- **`_reader_store` on a legacy single-file layout** (probe C, `_SilentDaemon` seeded root with only `catalog.duckdb`) returns a read-only `Store` on `catalog.duckdb` itself — the writer file — although its docstring says "replica reader slot only". Under a real daemon the read-only attach conflicts with the exclusive lock and returns None, so this is unreachable on the fleet (all rotation layout); it is why the probe's silent-socket `memory get x` said "reading the replica" and read the seeded catalog. {#obs-legacy-layout}
- **MCP `rmx_memory_recall.timeout` description** still says "omit for the library defaults"; the default is now the explicit 30 s. Wording only. {#obs-mcp-desc}
- **Plan-2 r7 holding live:** 30 hook `memory recall` rows in `cli.log` since the 03:03 relaunch, max 4.5 s, none over 5 s (the 18 rows over 10 s today all predate it). {#obs-hook-live}
- **Working tree at audit time** carried the plan-5 r3 audit's uncommitted ledger edits and an unstaged `tests/test_verbs_migrated.py` / `bug_registry.md`; none touch plan-3 regions. A stray `.err` at the repo root was mine (a broken timing loop) and is removed. {#obs-tree}

## Verdict {#verdict}

**DIRTY — 5 findings (1 BULLSHIT, 2 SKETCHY, 2 MEH).**

Round 4 is closed where it was quoted, and closed for real on both simulations: recall-state says busy on the silent socket and running on the held writer; every `memory` verb action, the MCP recall default, the dense path, the promote and `memory_partition` are bounded at 10 s / 30 s on a held writer with the slot untouched; the CLI `get` and `recall` twins reach the replica in 10 s / 15 s; the op-line bound survives my mutation only because the CLI test catches it. What remains is the r4 pattern one surface over: the constant that bounds `get`/`list`/`search` bounds the verb, and the `list`/`search` twins never call the verb — 190 s each on a held writer, the same number r4 filed for `get`. Plus the #m-6 closure tested on the simulation the finding did not name, and a fan-out that Q14 says reports every skipped store and that drops a held one after 60 s without a word. Round 6 should be short: route two twins through the verb they bypass, print "reading the replica" only when `_reader_store()` is not None, and make `federated_query` say what it skipped.

rel: contradicts -> [[bsd-pattern-partial-bound]]
rel: contradicts -> [[project-profile#constraints]]
