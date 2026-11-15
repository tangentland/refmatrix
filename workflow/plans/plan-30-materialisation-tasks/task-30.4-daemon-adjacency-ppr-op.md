---
gmd: "0.1"
id: task-30.4-daemon-adjacency-ppr-op
title: "Task 30.4: the daemon keeps the adjacency and the hook asks for the ranking — an in-memory adjacency service rebuilt off the store lock at each snapshot publish, a bounded ppr_rank read op, and a counted in-process fallback (fixes bug-243)"
tags: [task, plan-30, adjacency, daemon, ppr, scan-prompt, hooks, read-op, bug-243, no-silent-failures]
metadata:
  node_type: task
  status: pending
  plan: plan-30-materialisation
  created: 2026-11-14
  updated: 2026-11-14
---

# Task 30.4: the daemon keeps the adjacency; the hook asks for the ranking {#root}

> Plan: [[plan-30-materialisation]] ([[plan-30-materialisation#t4]])
> Status: Pending
> Depends on: release B deployed ([[task-30.1-adjacency-mapping-adapter]],
> [[task-30.2-vectorised-adjacency-build]], [[task-30.3-disk-tier-fate]]); 30.2's memory band
> ([[task-30.2-vectorised-adjacency-build#r0-memory-bands]]); plan-29 released; 23.0's test
> sandbox ([[task-23.0-test-sandbox]]).
> Ships alone, as release C. **It edits no derive-pass file** ([[#ac-12]]).
> Before the first `src/` edit: an ADR, authored by `ch-architect` ([[#r1]]).
> Fixes bug-243.
> User gates: plan-30 D1 (may the op answer from a graph that is behind). The spec is written
> to the recommendation, (a); (b) and (c) change two numbers in [[#r4]] and nothing else.

rel: part-of -> [[plan-30-materialisation]]
rel: implements -> [[plan-30-materialisation#t4]]
rel: implements -> [[bug_registry#registry]]
rel: depends-on -> [[task-30.2-vectorised-adjacency-build]]
rel: depends-on -> [[task-30.3-disk-tier-fate]]
rel: depends-on -> [[task-23.0-test-sandbox]]
rel: depends-on -> [[tdd-governance]]
rel: derives-from -> [[perf-bitmap-materialisation-2026-11-14#q2]]
rel: related-to -> [[project_worker_queue_measured_1109]]
rel: reinforces -> [[feedback_no_silent_failures]]
rel: reinforces -> [[feedback_errors_fail_loudly_on_the_console]]
rel: reinforces -> [[feedback_measure_the_outcome_not_the_wall]]
rel: reinforces -> [[feedback_measure_the_path_users_run]]
rel: reinforces -> [[feedback_daemon_call_retries_multiply_timeouts]]
rel: reinforces -> [[feedback_prefer_existing_infra]]
rel: reinforces -> [[feedback_go_no_go_ranges_not_predrop]]

## Why {#why}

After release B the installed hook still builds the whole adjacency once per prompt, about
0.5 s, because the hook is a one-shot process: a cache on its `Store` dies with it. The walk
itself, over an adjacency that already exists, was measured at 8.4 ms with identical output on
18 of 18 seed sets ([[perf-bitmap-materialisation-2026-11-14#q2]]). The one process that lives
long enough to hold the adjacency is the daemon. {#why-body}

The daemon already has the lifecycle this needs. After each write op it publishes a read
snapshot (`Daemon._snapshot_catalog`, debounced by the snapshot tick) and, inside the same
publish, refreshes an in-memory mirror of it (`_MemMirror.refresh`). The adjacency joins that
lifecycle: built from the published snapshot, off the store lock, swapped in whole. Nothing is
written to disk, so there is no merge, purge or slot path to census: the structure dies with
the process. {#why-primitive}

**History this must not repeat.** `scan-prompt` once queued on the daemon's 4-worker cli pool
and helped starve its liveness (bug-115); a client retry tripled a hook's wait (bug-116); the
hook still overruns its 5 s (bug-182). The bounds in [[#r5]] and [[#r6]] are requirements with
tests, not intentions. {#why-history}

## Design {#design}

```text
write op ─▶ _request_snapshot ─▶ snapshot tick ─▶ _snapshot_catalog
                                                    ├─ publish catalog.read.duckdb   (seq += 1)
                                                    ├─ mirror.refresh()              (existing)
                                                    └─ adjacency service: wake       (new)

rmxd-adjacency thread:  for each demanded key ─▶ open the published snapshot read-only
                        ─▶ build_adjacency (30.2) ─▶ swap entry {csr, seq}

hook (one-shot):  scan_prompt ─▶ _ppr_rerank ─▶ daemon op ppr_rank  ──ranked──▶ bundles
                                      │                  └─ rank_related_for_prompt(adj=entry.csr)
                                      └─ unavailable / absent / busy ─▶ in-process (30.2), counted
```
{#design-diagram}

- **One ranking function.** The op and the fallback both call `ppr.py::rank_related_for_prompt`.
  The op hands it the service's CSR; the fallback lets it read `cached_adjacency`.
- **The graph's version is the publish sequence**, a counter the daemon increments under
  `_snapshot_lock` at each successful publish.
- **A new module, `src/refmatrix/adjacency_service.py`,** holds the service, the op and the
  client. `daemon.py` gains wiring only: it is over the size target already.
{#design-list}

## Requirements {#requirements}

### R0: baseline and the policy measurement {#r0}

1. Re-resolve symbols at the base sha. Re-run [[#census]].
2. Read 30.2's memory band. Under a go row the service builds in the daemon process. Under the
   no-go row it takes [[#r3-child]].
3. **Publish and prompt replay.** `workflow/measurements/plan-30-daemon-adjacency/replay.py`
   reads 7 days of the live `rmxd.log` and `query.log` as text and replays publish times and
   `scan-prompt` times through [[#r3]]'s rebuild policy, for a debounce of 0, 1000 and 5000 ms,
   with 30.2's measured build time. It prints, per setting: builds per day; build seconds per
   day; and the share of prompts that would be answered fresh, answered behind within the
   bound, and `unavailable`. Counts only; no prompt text.
4. **Bands for the policy, stated now.**

   | Result | Action |
   |---|---|
   | some setting has build time at or under 2% of wall time AND 90% or more of prompts answered by the daemon | take the smallest such debounce as the default |
   | no setting meets both | no eager rebuild: [[#r3-ondemand]] |
   {#r0-policy-bands}
5. **The production-scale store for [[#ac-10]].** A throwaway store whose catalog is a copy of
   a read snapshot, with a daemon started on it inside 23.0's sandbox, so that no live hub is
   reachable. R0 writes the recipe and shows the daemon serves the copy. The measurements
   themselves are taken at GREEN; their bands are in [[#ac-10-bands]], written now.

### R1: the ADR {#r1}

`docs/adr/NNNN-daemon-held-read-models.md` (NNNN is the next free number at the base sha; 29.5's
layout ADR is numbered before it), authored by `ch-architect`, Proposed before the
first `src/` edit and Accepted when the user has answered plan-30 D1. It records:

- a derived read model that a per-prompt path needs lives in daemon memory, is built from the
  published snapshot off the store lock, and is versioned by the publish sequence;
- a one-shot process asks a bounded read op for the result and keeps an in-process path through
  the same function;
- no on-disk derived copy is added without a census of every writer of its inputs (bug-105,
  bug-216, bug-227), and none is added here;
- the op is transport for a hook, not a verb.

It gets its row in `docs/adr/0000-adr-overview.md` and `docs/INDEX.md`, and `rel:` edges to the
ADRs it builds on. {#r1-body}

### R2: the publish sequence {#r2}

- `Daemon` keeps a publish sequence as two counters: `begin`, incremented under
  `_snapshot_lock` just before the snapshot file is replaced, and `end`, incremented just after.
  Both start at 0; the snapshot a daemon finds on disk at start is sequence 0.
- `Daemon.open_snapshot_store(partition)` opens a private read-only store on the snapshot file
  (through `_open_read_store(partition, allow_mirror=False)`, so the swap gate still counts it)
  and returns it with its sequence: it reads the two counters before and after the open, and
  the sequence is `end` when all four reads are equal. Otherwise a publish overlapped the open,
  and the sequence is unknown (`None`). It takes no lock: a publish holds `_snapshot_lock` for
  the whole checkpoint and copy, and a read must not wait behind that.
- `_MemMirror.refresh`, which `_snapshot_catalog` calls inside the lock, records `end` as the
  mirror's sequence.
- After the mirror refresh, `_snapshot_catalog` wakes the adjacency service. It does not wait
  for it.
{#r2-list}

### R3: the service {#r3}

`adjacency_service.AdjacencyService`, one per daemon, started with the snapshot tick and
stopped with it.

- **Key:** partition name, `link_weight`, `exclude_operational`, the mentions mode and the
  shape version: the fields of `cached_adjacency`'s key, with the partition by name.
- **Entry:** the CSR, the publish sequence it was built from, when, how long the build took,
  its node and edge counts and its bytes.
- **Demand.** A key is built only if it has been asked for in the last `RMX_ADJ_IDLE_S`
  (default 1800). A key idle longer is dropped, counted and logged. Nothing is built at start.
- **Rebuild.** One thread, `rmxd-adjacency`. It wakes on a publish and on a first request for a
  key. For each demanded key whose entry is older than the current sequence it:
  1. opens the snapshot with `Daemon.open_snapshot_store` ([[#r2]]), and opens it again if the
     sequence came back unknown, so that the store it builds from is exactly one sequence;
  2. calls `build_adjacency` on it;
  3. closes the store and swaps the entry in, as one reference assignment.
  It never reads the writer, and takes neither `_store_lock` nor `_snapshot_lock`. It runs
  one build at a time. If a
  publish arrived during a build it goes round again, after the debounce R0 chose.
- **A failed build** is logged, recorded through `Daemon.record_sync_error` under the route
  `adjacency:<partition>` (cleared by the next good build), counted, and passed to
  `_fast_exit_if_invalidated`. The previous entry stays and ages out by [[#r4]]'s bound.
- **A partition that is not in the snapshot** gives no entry and the reason
  `partition-unknown`. An entry for a partition that has gone is dropped at the next rebuild.
- **Status.** The service publishes an immutable status object, replaced by one reference
  assignment whenever it changes: per key the entry's fields and `behind`; and the counters
  `served`, `served_behind`, `unavailable` by reason, `builds`, `build_failures`, `evicted`,
  `last_error`. Reading it takes no lock and touches no store, so `ping`, which is answered on
  the dispatcher thread, can carry it. `rmx daemon status` prints it. No lock of the service
  is held across a build.
- **Shutdown.** The thread has a stop event, is joined inside the existing drain budget, and
  abandons a build in flight. There is nothing on disk to clean.
- **Switch.** `RMX_ADJ_SERVICE=0` starts no service; the op then answers `unavailable:
  disabled`. Both settings are tested.
{#r3-list}

**If R0 chose no eager rebuild** ([[#r0-policy-bands]]): the thread does not wake on a publish.
A request for a key whose entry is behind wakes it, and the request waits as [[#r4]] says.
Concurrent requests share the one build. {#r3-ondemand}

**If 30.2's memory band is no-go:** step 2 runs in a child process that opens the snapshot
read-only, builds, and returns the CSR's arrays over a pipe. Nothing is written to disk. The
child is reaped; a child that dies is a failed build. Every other requirement is unchanged.
{#r3-child}

### R4: the op `ppr_rank` {#r4}

Registered in the daemon's op table and in `CLI_OPS`; not a write op.

- **Arguments:** `partition`, `seed_ids`, `k`, `alpha`, `eps`, `link_weight`, `clique_weight`,
  `coverage_alpha`, `kinds`, `include_seeds`: the parameters of `rank_related_for_prompt`.
- **Which graph** (plan-30 D1, option a). With the entry at the current sequence: serve it. With
  a newer publish pending: wait up to `RMX_PPR_WAIT_S` (default 0.25) for the build; then serve
  the newest entry if it was superseded no more than `RMX_ADJ_MAX_BEHIND_S` (default 10) ago.
  Otherwise the op does not rank.
- **`unavailable` is a result, not an error:** `{"unavailable": <reason>}`, with the reason one
  of `building` (no entry yet), `behind` (older than the bound), `build-failed`,
  `partition-unknown`, `disabled`, `names-unavailable`. Each is counted.
- **The ranking** is `rank_related_for_prompt(store, seed_ids, adj=entry.csr, …)`, run through
  `_read_with_fallback` with `writer_wait_s=0`, so that names and kinds come from the mirror or
  the snapshot and the op never waits for the writer. If no read store can answer without the
  writer, the result is `unavailable: names-unavailable`.
- **Reply:** `ranked` (the function's list), `graph` (`seq`, `current_seq`, `behind`, `age_s`,
  `nodes`, `edges`), and `walk_ms`.
- **The op never takes `_store_lock`,** directly or through anything it calls.

### R5: the client {#r5}

`scan.py::_ppr_rerank` asks `adjacency_service.rank_for_prompt(store, seed_ids, …)`, which:

1. goes straight to the in-process path, with the reason `no-daemon`, when the store's root has
   no daemon socket or `RMX_ADJ_SERVICE=0` (an eval harness, a test, a store with no daemon);
2. otherwise dials `ppr_rank` **once**, through the verbs module's daemon-call wrapper, with
   `retries=0` and a timeout of `RMX_PPR_DAEMON_TIMEOUT_S` (default 0.5);
3. on `ranked`, returns it with the path `daemon`;
4. on `unavailable`, on a typed transport error (absent, busy, unreachable), or on an error
   reply (an older daemon answers `unknown op`), runs the in-process path
   (`rank_related_for_prompt(store, …)`, which is 30.2's) and returns it with the path
   `inprocess` and the reason. A transport error is worded by the one classifier
   (`verbs.classify_transport_error`); the client words none itself.

The reason is one of: `no-daemon`, `daemon-absent`, `daemon-busy`, `daemon-old`,
`daemon-error`, or `unavailable:<the op's reason>`. {#r5-reasons}

### R6: every fallback is counted and named {#r6}

- **In the row.** `trace["rerank"]` ([[task-30.2-vectorised-adjacency-build#r5]]) gains `path`
  (`daemon` or `inprocess`), `fallback` (the reason, or null), `ms`, and for the daemon path
  `graph` (`seq`, `behind`, `age_s`). `scan_prompt_cmd` writes it to the `query.log` row.
- **In the daemon.** The counters of [[#r3-list]], in `ping` and `rmx daemon status`.
- **In the hook's output, when the daemon was reached and did not serve:** for `daemon-busy`,
  `daemon-old`, `daemon-error` and `unavailable:build-failed`, one line where the bundle
  warnings go: `# ppr ranked in-process: <reason>`. This is the rule the shared reranker
  already follows: a worker that was reached and failed is said in the output; one that is
  simply not there adds nothing. `no-daemon`, `daemon-absent`, `unavailable:building`,
  `unavailable:behind` and `unavailable:disabled` are operating states: row and counters only.
- **In a report.** The command that summarises `scan` rows of `query.log` (R0 names it) shows,
  for its window, the rerank paths: daemon, in-process by reason, did not run.
- The installed hook discards stderr, so nothing here depends on stderr.

### R7: the degree walk reads the same adjacency {#r7}

The daemon's `context` op runs on a private snapshot store (`_read_with_fallback` with
`private=True`), so the instance cache dies with each op: after release B every `context` op
with a degree walk builds its own adjacency, about 0.5 s, inside the daemon.

- `adjacency_service.adjacency_for(store, *, link_weight=2.0, exclude_operational=True)` is the
  one way to get an adjacency for a store. It asks `store.adjacency_provider`, if the store has
  one, and otherwise returns `pagerank.cached_adjacency(store, …)`.
- `Store` gains the public attribute `adjacency_provider`, `None` by default.
- **The daemon sets it on every read store it hands out whose sequence it knows:** the private
  stores of `_read_with_fallback(private=True)`, opened through `open_snapshot_store`, and the
  mirror. A store whose sequence is unknown gets none.
- The provider registers demand for the key, and returns the service's entry only when the
  entry's sequence equals the store's. Otherwise it returns `None`, and the caller builds as it
  does after release B.
- `context.py`'s degree walk, `ppr.py::rank_related`, `ppr.py::rank_related_for_prompt` (when
  `adj` is `None`), `enrich.py::enrich_concepts` and `net.py::build_net` call `adjacency_for`.
- No file named in `_DERIVE_PASS_MODULES` is edited: `cached_adjacency` is called, not changed.
- **Layering.** `adjacency_service` imports neither `daemon` nor `cli` at module level: the
  engine modules import `adjacency_for` from it, and the client reaches the daemon-call wrapper
  inside the function. 29.5's import-layering census stays green
  ([[task-29.5-split-giant-modules#r2b]]).
{#r7-list}

### R8: every write reaches a publish {#r8}

The service is as fresh as the publishes. A daemon op that changes the graph and never calls
`Daemon._request_snapshot` would leave the service, the mirror and every CLI reader on the old
graph.

- A census family on 29.3's kit lists every daemon op and background path that writes through
  the writer store, and whether it requests a snapshot. Each one that does not is either
  allow-listed with its reason or is a finding: logged in the bug registry (id from the lead)
  and fixed here if the fix is the one call.
- The family has a planted op that fails it.

### R9: docs {#r9}

`docs/ARCHITECTURE.md` (the daemon's read models: mirror and adjacency), `docs/PERFORMANCE.md`
(the measured numbers of [[#ac-10]]), `docs/INTEGRATION.md` (the hook's rerank path, the
switches of this spec), `docs/INDEX.md`. The bug registry row for bug-243 is closed with the
merge sha by the lead. {#r9-body}

## Acceptance criteria {#acceptance}

Each is RED at the base sha unless marked. Daemon tests use a short temp root inside 23.0's
sandbox. The fixture store and seed sets are [[task-30.1-adjacency-mapping-adapter#fixture]]'s.

- **AC-1: the daemon path equals the in-process path.** On one published snapshot, for every
  seed set, `ppr_rank`'s `ranked` equals `rank_related_for_prompt(store, …)` on a read-only
  store of the same snapshot: the same ids in the same order, scores within 1e-9. Recorded as
  sets equal of sets run. Test: `test_daemon_ranking_equals_inprocess` in
  `tests/test_adjacency_service.py`. {#ac-1}
- **AC-2: a write is followed.** Link a new edge that changes a seed set's ranking; after the
  publish and the rebuild, `ppr_rank` returns the new ranking with `graph.behind == 0`, and
  `graph.seq` grew by the number of publishes. The test waits on the service's entry sequence,
  not on a sleep. Test: `test_rebuild_follows_a_publish`. {#ac-2}
- **AC-3: behind is bounded and stated.** With the builder held (a build made to block on an
  event the test owns): within the bound, the op serves the previous entry with `behind >= 1`
  and the old ranking, and `served_behind` counts it; past `RMX_ADJ_MAX_BEHIND_S` (set small),
  it answers `unavailable: behind`; before any build, `unavailable: building`. Test:
  `test_behind_policy`. {#ac-3}
- **AC-4: the op never waits for the writer.** With `_store_lock` held by another thread for the
  whole test, 20 `ppr_rank` calls all return `ranked`, each inside the client timeout; and a
  census family asserts nothing reachable from the op or the service names `_store_lock`
  (planted site fails it). Test: `test_op_served_while_the_writer_is_held`. {#ac-4}
- **AC-5: one dial, bounded.** With the daemon's cli pool filled by blocked ops, 50 client calls
  each return a ranking (path `inprocess`, reason `daemon-busy`); none dials twice (a counting
  socket wrapper); each returns within the timeout plus one in-process ranking; after the
  blocked ops are released, the daemon's expired-read count has risen by the number of calls it
  never started and no `ppr_rank` is in flight. Test: `test_client_is_bounded_under_a_full_pool`. {#ac-5}
- **AC-6: every fallback reason is produced and named.** One case per reason of
  [[#r5-reasons]]: no socket; a socket nobody listens on; a full pool; a daemon whose op table
  lacks `ppr_rank`; an op that raises; `building`; `behind`; `build-failed`; `disabled`;
  `partition-unknown`; `names-unavailable`. For each: the ranking equals the in-process ranking;
  `trace["rerank"]` has the path and the reason; the row written by `scan_prompt_cmd` carries
  them; the output has the warning line exactly for the four reasons of [[#r6]] and for no
  other. Test: `test_every_fallback_is_named` (parametrised). {#ac-6}
- **AC-7: a failed build is loud.** With the build made to raise: `ping` carries a
  `sync_errors` entry for `adjacency:<partition>` and the service block shows `build_failures`
  and `last_error`; the next good build clears the entry; the daemon did not exit (the error
  was not an invalidation). With an invalidation error, the fast-exit path runs. Test:
  `test_build_failure_is_recorded_and_cleared`. {#ac-7}
- **AC-8: liveness during rebuilds.** While 20 rebuilds run back to back, pings sent every 50 ms
  are all answered inside the hub watchdog's ping budget (R0 reads the value). Recorded as
  answered of sent. Test: `test_pings_answered_during_rebuilds`. {#ac-8}
- **AC-9: the degree walk builds nothing.** After a publish and a rebuild, three `context` ops
  with degree 1 cost 0 builds between them (a counting wrapper on `build_adjacency`; RED at the
  base: 3) and each returns what it returned at the base sha. A store with no provider, and a
  store whose sequence differs from the entry's, behave as at the base. A store opened while a
  publish overlaps gets no provider (the publish is held between its two counter steps by an
  event the test owns). Tests: `test_context_walk_uses_the_service`,
  `test_overlapped_open_has_no_sequence`. {#ac-9}
- **AC-10: measured at production scale, under load, more than once.** On R0 item 5's store,
  three runs at least 5 minutes apart, each printing the 1-minute load at both ends, each with
  a writer loop running (a sync of touched files every few seconds) and each of 200 or more
  hook-shaped calls from seed sets taken in memory from recent prompts (nothing written but
  counts):
  - identical rankings, daemon path against in-process path on the same sequence: N of N;
  - the share of calls answered `daemon` fresh, `daemon` behind, and each fallback reason;
  - the op's time through the socket: median, p90, p99; and its own stage times (queue wait,
    graph wait, walk, names);
  - the hook leg's time (`trace["rerank"]["ms"]`): median and p90, beside 30.2's.

  The result is read against [[#ac-10-bands]]. {#ac-10}
- **AC-11: the hook's own path.** `rmx scan-prompt`, run through the CLI entry as the generated
  hook runs it, against the sandboxed daemon, for 30.2's synthetic prompts: the output is
  byte-equal to 30.2's in-process output while the graph is current; the row says
  `path: daemon`. `rmx install-hooks --check` is clean and the generated hook command is
  unchanged. The verb-parity test is green with no new verb. {#ac-11}
- **AC-12: no derive-pass file is edited.** The set of files this task changes under
  `src/refmatrix`, intersected with the files `_DERIVE_PASS_MODULES` names (read from the table
  at run time), is empty. `scripts/derive-digest.py check` exits 0. {#ac-12}
- **AC-13: shutdown and the switch.** A daemon stopped during a build exits inside the drain
  budget with no thread left; 29.4's session reaper finds nothing. With `RMX_ADJ_SERVICE=0` no
  `rmxd-adjacency` thread exists, the op answers `unavailable: disabled`, and the client does
  not dial. {#ac-13}
- **AC-14: every write reaches a publish.** [[#r8]]'s family passes on the tree and fails on
  its planted op. {#ac-14}
- **AC-15: the benchmark path is the production path.** The `eval/production` harness that runs
  `scan_prompt` (R0 names it) gives the same output as at the base sha on its smoke fixture,
  with `path: inprocess` and `fallback: no-daemon`. {#ac-15}
- **AC-16: after release, on the live logs** (the lead's, read as text, counts only): over 7
  days, the share of `scan` rows with `path: daemon`; the hook leg's median and p90; and
  `scan-prompt`'s total p50 and p90 beside the 2818 ms and 13,042 ms of the report. Reported as
  measured. No cause is claimed for the total beyond the leg's own time. {#ac-16}

### The bands for AC-10, stated before measuring {#ac-10-bands}

| Result, in every one of the three runs | Action |
|---|---|
| op p99 at or under 250 ms and fallbacks at or under 10% of calls | go |
| op p99 over 250 ms and at or under 500 ms, fallbacks at or under 10% | go; the summary names the slowest stage |
| op p99 over 500 ms, or fallbacks over 10% | no-go for release C; back to the design with the stage times |
{#ac-10-bands-table}

"Fallbacks" here are the reasons of [[#r6]] that put a line in the output, plus `behind`. A
call answered `building` in the first seconds after the daemon starts is not counted.
{#ac-10-bands-note}

## Mutations that must fail {#mutations}

Each alone, seen RED (not hung) on the named AC, reverted in its own command.

1. the builder reads the writer store → AC-4's census.
2. the service holds a lock across the build → AC-3 (the op cannot answer from the previous
   entry while a build is blocked; the test's own bound fails it, it does not hang).
3. the publish does not wake the service → AC-2.
4. the entry records the sequence read AFTER the build → AC-2 and AC-3.
5. the op serves any entry, whatever its age → AC-3.
6. the op answers `building` with an empty `ranked` instead of `unavailable` → AC-6.
7. `_read_with_fallback` is called with no `writer_wait_s` → AC-4.
8. the client passes `retries=2` → AC-5.
9. the client returns the salience order on `unavailable` instead of ranking in-process → AC-6.
10. the client drops the reason → AC-6.
11. the warning line is written for `daemon-absent` → AC-6.
12. the warning line is not written for `daemon-busy` → AC-6.
13. a failed build clears the previous entry at once → AC-3.
14. a failed build is logged and not recorded → AC-7.
15. the provider returns an entry of another sequence → AC-9 (a ranking from the old graph).
16. the op ranks with its own copy of the walk, not `rank_related_for_prompt` → AC-1 on the
    seed sets with coverage.
17. the thread is not joined at stop → AC-13.
18. an op that writes stops requesting a snapshot → AC-14.
19. `open_snapshot_store` returns `end` after reading the counters once → AC-9 (the overlapped
    open).
20. `begin` is incremented after the replace → AC-9 (the overlapped open).
{#mutations-list}

## Test strategy {#test-strategy}

- **RED first, by `ch-test-engineer`.** The tests named in [[#acceptance]] are written before
  any `src/` edit and run at the base sha; the red run is kept
  (`workflow/review-output/task-30.4/red.log`) with each test's E line. A test this spec marks
  characterization is recorded green at the base and says so. A test expected RED that passes
  at the base is a finding about the test.
- **GREEN by `ch-implementer`,** who writes no test.
- **Mutation gate.** The fix is committed before the first mutation. Each mutation of
  [[#mutations]] is applied alone, must FAIL its named test (a hang is not a failure), and is
  reverted in its own command; `__pycache__` is cleared after the batch; the fix is shown
  present after the last revert.
- **Test families are derived from imports** of the touched modules (29.4), and the merged dev
  tree runs them before the merge commit.
- **Daemon tests** run on short temp roots inside 23.0's sandbox, wait on outcomes (an entry's
  sequence, a counter, a reply) and never on a sleep, and leave no daemon behind (29.4's
  reaper fails the session otherwise).
- **Mocks.** The blocked build, the counting socket wrapper and the held lock act on
  collaborators; classified in `workflow/test_mock_registry.md`. The ranking function and the
  op are never patched.
- **Measurements** ([[#ac-10]]) are three runs at least 5 minutes apart, under a writer loop,
  each with its loads. A single quiet run is not accepted.
- **All output to files** under `workflow/review-output/task-30.4/`.
{#test-strategy-list}

## Caller census {#census}

At `6676f39`. R0 re-runs it.

| Changed | Callers and readers |
|---|---|
| `scan.py::_ppr_rerank` | `scan.py::scan_prompt`; `scan.py::_net_rerank` (two fallbacks); `tests/test_scan_prompt_dedup.py`; `eval/spike_hypertree/m4_render_tokens.py` |
| `ppr.py::rank_related_for_prompt` | `scan.py::_ppr_rerank`; the new op; tests as in 30.1 |
| `pagerank.cached_adjacency` (called through `adjacency_for`) | `context.py`'s degree walk; after 30.2: `ppr.py` (two), `enrich.py`, `net.py` |
| `Daemon._snapshot_catalog` (sequence, wake) | the snapshot tick; `_op_snapshot`; R0 lists any other |
| `_MemMirror.refresh` (sequence, provider) | daemon start; `_snapshot_catalog` |
| `Daemon._open_read_store` (reached through the new `open_snapshot_store`; unchanged itself) | `_read_with_fallback` and the read ops that call it (16 call sites at `6676f39`); `_op_context` is the one that passes `private=True` with a degree walk |
| `_read_with_fallback` (its private branch attaches the provider) | as above |
| the op table and `CLI_OPS` | `Daemon._handle`; tests that enumerate ops (R0 lists) |
| `_op_ping`'s result (the service block) | the hub watchdog; `rmx daemon status`; tests of the ping shape (R0 lists) |
| the `query.log` `scan` row (`rerank` object) | every reader of `scan` rows: the reports of plan-21 (`tests/test_task21_1_query_rows.py`), R0 lists the rest |
| `Store` (the `adjacency_provider` attribute) | `adjacency_for` only; 29.2's store host declarations |
| the generated hook command | unchanged ([[#ac-11]]) |
{#census-table}

## Invalidation {#invalidation}

- An entry is exact for one (key, publish sequence). A publish makes it behind; the rebuild
  replaces it.
- The publish is the write-batch boundary as every reader outside the writer sees it. [[#r8]]
  checks that every write reaches one.
- An entry is dropped when its key has been idle, when its partition is gone, and when the
  process exits. A failed build leaves the old entry to age out by the bound.
- The provider hands a read store an entry only of that store's own sequence; a store whose
  sequence is unknown gets no provider.
- Slot rotation, replica refresh, `rebuild_index_from_log` and the repair ops reach the service
  through the same publish. [[#r8]]'s census is where one that does not would show.
- Nothing is on disk. There is no merge, purge or slot census to owe.
{#invalidation-list}

## Files {#files}

| File | Change |
|---|---|
| `docs/adr/NNNN-daemon-held-read-models.md`, `docs/adr/0000-adr-overview.md`, `docs/INDEX.md` | [[#r1]] |
| `src/refmatrix/adjacency_service.py` | new: the service, the op, the client, `adjacency_for` |
| `src/refmatrix/daemon.py` | [[#r2]]; start and stop of the service; the op's registration; the `ping` block |
| `src/refmatrix/store.py` | the `adjacency_provider` attribute |
| `src/refmatrix/scan.py`, `src/refmatrix/cli/session_cmds.py` | [[#r5]], [[#r6]] |
| `src/refmatrix/context.py`, `ppr.py`, `enrich.py`, `net.py` | [[#r7]] |
| `src/refmatrix/cli/daemon_cmds.py` | `rmx daemon status` prints the block |
| the report command R0 names | [[#r6]] |
| `tests/test_adjacency_service.py`, `tests/census/` (two families) | new |
| `workflow/measurements/plan-30-daemon-adjacency/` | the replay, the socket measurement, their logs |
| `docs/ARCHITECTURE.md`, `docs/PERFORMANCE.md`, `docs/INTEGRATION.md` | [[#r9]] |
| `workflow/test_mock_registry.md` | the blocked build, the counting socket, the held lock |
| `workflow/implementation_summaries/task-30.4-daemon-adjacency-ppr-op.md` | new |
{#files-table}

## Risks {#risks}

- **The hook waits on the daemon.** One dial, 0.5 s, no retry, then the 30.2 path. AC-5 and
  AC-10 measure it under a full pool and under writes.
- **A deploy leaves an old daemon with a new hook.** The op is unknown to it; the client ranks
  in-process and says `daemon-old`. AC-6.
- **Rebuilds cost the daemon CPU during long ingests.** R0's replay sets the debounce by a
  stated band, or turns eager rebuild off.
- **Memory.** One CSR per demanded key and one more during a build: about 40 MB each at this
  store's size. 30.2's band decides in-process or child.
- **The ranking comes from a graph one batch old.** plan-30 D1. The reply says so, and the row
  records it.
- **Seeds are resolved on the hook's replica and ranked on the daemon's graph.** Entity ids are
  stable; a seed the graph does not hold is skipped by the function, as it is in-process.
- **The measured 8.4 ms was in-process.** The socket, the cli pool and the name lookups are not
  in it. AC-10 has the bands.
{#risks-list}

## Out of scope {#out-of-scope}

- `scan-prompt`'s other legs and a whole-command time bound (bug-182). This task records one
  leg's time in the row, which is part of what bug-182 asked for.
- Serving `enrich`, `net` or `assoc` from the daemon. They read `adjacency_for` in-process;
  none ran in the measured week.
- Moving the hook onto plan-24's transport.
- Pre-split rows and filter bitmaps ([[plan-30-materialisation#deferred]]).
{#out-of-scope-list}

## Decisions taken in this spec {#decisions}

- **plan-30 D5: the hook asks the daemon and keeps the in-process path.** The alternatives were
  a file the hook loads (an on-disk derived copy, which 30.0 is measuring the cost of) and
  shared memory (a second lifecycle to supervise). A read op returns 5 rows; the adjacency
  never crosses a process boundary.
- **The op returns the ranking, not the adjacency and not raw mass.** Names and kinds are
  filtered where the walk runs, by the same function as in-process, so there is one
  implementation to keep equal.
- **plan-30 D6: built from the published snapshot, versioned by publish sequence.** The writer
  is never read, so the build needs no store lock; and the version is the daemon's own counter,
  taken under the lock that publishes, so "which graph is this" has an exact answer.
- **Demand-driven.** A daemon serves several partitions. Only the ones a prompt path asks for
  are kept warm.
- **No verb, no MCP tool.** An agent does not call `ppr_rank`; `scan-prompt` does. The parity
  rule is about capabilities an agent can call.
- **The warning line follows the reranker's rule** (reached and failed: said; absent: not).
- **Timeout 0.5 s.** The fallback costs about 0.5 s, so waiting longer than that for the daemon
  is a loss. AC-10's bands can stop the release; they do not tune this number.
- **A new module.** `daemon.py` is 7,355 lines against a 3,000-line target.
{#decisions-list}
