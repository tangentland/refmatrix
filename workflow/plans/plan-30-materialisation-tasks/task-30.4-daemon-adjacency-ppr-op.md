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
  updated: 2026-11-15
---

# Task 30.4: the daemon keeps the adjacency; the hook asks for the ranking {#root}

> Plan: [[plan-30-materialisation]] ([[plan-30-materialisation#t4]])
> Status: Pending
> Depends on: release B deployed ([[task-30.1-adjacency-mapping-adapter]],
> [[task-30.2-vectorised-adjacency-build]], [[task-30.3-disk-tier-fate]]); 30.2's memory band
> ([[task-30.2-vectorised-adjacency-build#r0-memory-bands]]) and its two-step build
> ([[task-30.2-vectorised-adjacency-build#r1-two-steps]]); plan-29 released, with 29.3's slice d
> ([[task-29.3-converge-shapes#slice-d]], checked at [[#r0]] item 7); 23.0's test sandbox
> ([[task-23.0-test-sandbox]]).
> Ships alone, as release C. **It edits no derive-pass file** ([[#ac-12]]).
> Before the first `src/` edit: an ADR, authored by `ch-architect` ([[#r1]]).
> Fixes bug-243.
> User gates: plan-30 D1 (may the op answer from a graph that is behind): decided (a) by the
> user on 2026-11-15: yes, bounded, as [[#r4]] specifies. The ADR of [[#r1]] can be Accepted.
> Revised 2026-11-15 after ch-bsd r1 and ruling L116 ([[#rev-note-2]]), and after ch-bsd r2
> ([[#rev-note-3]]).

rel: part-of -> [[plan-30-materialisation]]
rel: implements -> [[plan-30-materialisation#t4]]
rel: implements -> [[bug_registry#registry]]
rel: depends-on -> [[task-30.2-vectorised-adjacency-build]]
rel: depends-on -> [[task-30.3-disk-tier-fate]]
rel: depends-on -> [[task-23.0-test-sandbox]]
rel: depends-on -> [[task-29.3-converge-shapes#slice-d]]
rel: depends-on -> [[tdd-governance]]
rel: derives-from -> [[perf-bitmap-materialisation-2026-11-14#q2]]
rel: related-to -> [[bsd-plan30-spec-r1]]
rel: related-to -> [[project_worker_queue_measured_1109]]
rel: reinforces -> [[feedback_no_silent_failures]]
rel: reinforces -> [[feedback_errors_fail_loudly_on_the_console]]
rel: reinforces -> [[feedback_measure_the_outcome_not_the_wall]]
rel: reinforces -> [[feedback_measure_the_path_users_run]]
rel: reinforces -> [[feedback_daemon_call_retries_multiply_timeouts]]
rel: reinforces -> [[feedback_prefer_existing_infra]]
rel: reinforces -> [[feedback_go_no_go_ranges_not_predrop]]
rel: reinforces -> [[feedback_clean_corpus_hides_a_dead_gate]]

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

rmxd-adjacency thread:  for each live key ─▶ open the published snapshot read-only
                        ─▶ read the build's inputs ─▶ digest equal?  yes: entry is valid at seq
                                                                     no:  assemble, swap entry

hook (one-shot):  scan_prompt ─▶ _ppr_rerank ─▶ daemon op ppr_rank  ──ranked──▶ bundles
                                      │                  └─ rank_related_for_prompt(adj=entry.csr)
                                      └─ unavailable / absent / busy ─▶ in-process (30.2), counted
```
{#design-diagram}

- **One ranking function.** The op and the fallback both call `ppr.py::rank_related_for_prompt`.
  The op hands it the service's CSR; the fallback lets it read `cached_adjacency`.
- **The snapshot's version is the publish sequence**, a counter pair the daemon moves under
  `_snapshot_lock` around each replace of the snapshot file.
- **A key is rebuilt only when its own inputs changed.** At each publish the service reads what
  the build reads, for each live key, and assembles only if that differs from what the entry
  was built from ([[#r3-inputs]]).
- **Only the hook's op creates demand,** and the number of live keys is capped.
- **A new module, `src/refmatrix/adjacency_service.py`,** holds the service, the op and the
  client. `daemon.py` gains wiring only: it is over the size target already.
{#design-list}

## Requirements {#requirements}

### R0: baseline and the policy measurement {#r0}

1. Re-resolve symbols at the base sha. Re-run [[#census]].
2. Read 30.2's memory band, which prices the steady state of this service as well as one build
   ([[task-30.2-vectorised-adjacency-build#r0-memory-bands]]). Under a go row the service builds
   in the daemon process. Under the no-go row it takes [[#r3-child]].
3. **The cost of the input check**, on the production-scale store of item 6: the time to read a
   key's inputs, take their effective edges and digest them ([[#r3-inputs]]), and the time to
   reduce them to the CSR, each as a median and
   p90 over 7 or more runs, two sessions minutes apart, loads printed.

   | Read-and-digest median | Action |
   |---|---|
   | at or under 25% of the full build's median | the input check is on |
   | over 25% | the input check is off: every live key is assembled at every publish, and item 4 prices it so |
   {#r0-check-bands}
4. **Publish and prompt replay, per key.** `workflow/measurements/plan-30-daemon-adjacency/replay.py`
   reads 7 days of the live `rmxd.log` and `query.log` as text.
   - It takes the **demanded key set** from the `scan` rows: partition × the rerank parameters
     each prompt ran with. `context` rows create no demand ([[#r7]]) and are counted only to
     show how many walks a live key would have served.
   - It replays publish times and prompt times through [[#r3]]'s policy, for a debounce of 0,
     1000 and 5000 ms, **for every live key at every publish**: one read-and-digest per key per
     publish, plus one assemble when the publish followed a write signal for that key's
     partition. That split is an estimate: the log names the source of a write, not its rows.
     The replay also prints the worst case, an assemble for every key at every publish.
   - It prints, per setting: live keys over time (median, maximum); read-and-digest seconds and
     assemble seconds per day, summed over keys; and the share of prompts answered fresh,
     answered behind within the bound, and `unavailable` by reason.
   - Counts only; no prompt text.
5. **Bands for the policy, stated now.** "Service time" is the sum over all live keys, **from
   the replay's worst case**: an assemble for every live key at every publish. The estimated
   split is printed beside it and decides nothing, because its attribution of writes to
   partitions is not reliable.

   | Result | Action |
   |---|---|
   | some setting has service time at or under 2% of wall time AND 90% or more of prompts answered by the daemon | take the smallest such debounce as the default |
   | no setting meets both | no eager rebuild: [[#r3-ondemand]] |
   {#r0-policy-bands}
6. **The production-scale store for [[#ac-10]].** A throwaway store whose catalog is a copy of
   a read snapshot, with a daemon started on it inside 23.0's sandbox, so that no live hub is
   reachable. R0 writes the recipe and shows the daemon serves the copy. The measurements
   themselves are taken at GREEN; their bands are in [[#ac-10-bands]], written now.
7. **Slice d.** Confirm that 29.3's slice d converted `merge-verb-aliases`' route gate: its
   no-daemon branch is reached only when the typed classifier says the daemon is absent, and
   slice d's AC-d3 has a row for it. If it is still a bare `ping`, converting it, with slice d's
   test shape, is this task's first commit ([[#r8]]).

### R1: the ADR {#r1}

`docs/adr/NNNN-daemon-held-read-models.md` (NNNN is the next free number at the base sha; 29.5's
layout ADR is numbered before it), authored by `ch-architect`, Proposed before the
first `src/` edit and Accepted when the user has answered plan-30 D1. It records:

- a derived read model that a per-prompt path needs lives in daemon memory, is built from the
  published snapshot off the store lock, and is versioned by the publish sequence;
- it is rebuilt when its own inputs changed, decided by reading those inputs from the snapshot,
  not by marks left by the write path;
- a one-shot process asks a bounded read op for the result and keeps an in-process path through
  the same function;
- no on-disk derived copy is added without a census of every writer of its inputs (bug-105,
  bug-216, bug-227), and none is added here;
- the op is transport for a hook, not a verb.

It gets its row in `docs/adr/0000-adr-overview.md` and `docs/INDEX.md`, and `rel:` edges to the
ADRs it builds on. {#r1-body}

### R2: the publish sequence {#r2}

- `Daemon` keeps a publish sequence as two counters, `begin` and `end`, both moved only under
  `_snapshot_lock`. Both start at 0; the snapshot a daemon finds on disk at start is sequence 0.
- **`begin` is incremented immediately before the `os.replace` of the snapshot file, and `end`
  in a `finally` around it.** A checkpoint or a copy that fails before the replace moves
  neither. A replace that fails moves both: the sequence steps, the file is the old one, and
  the two counters are equal again. `begin != end` is therefore seen only while a replace is in
  progress.
- **A failed publish is recorded.** `_snapshot_catalog` returns an error today and logs it. It
  now also sets the service's `publish_failed` state (when, and the detail) and records it
  through `Daemon.record_sync_error` under the route `adjacency:publish`. The next publish that
  succeeds clears both.
- After each successful replace, and at start, the daemon records the snapshot file's identity
  (device, inode, modification time in nanoseconds, size), under the lock.
- `Daemon.open_snapshot_store(partition)` opens a private read-only store on the snapshot file
  (through `_open_read_store(partition, allow_mirror=False)`, so the swap gate still counts it)
  and returns it with its sequence. **`partition` is required: `None` raises.** With no
  partition `_open_read_store` falls back to the writer's current binding
  (`self._st()._partition_name`), which is a read of the writer and the bug-098 transient
  binding. It reads the two counters before and after the open; the
  sequence is `end` when all four reads are equal **and** the opened file's identity equals the
  recorded one. Otherwise the sequence is unknown (`None`), with the cause: `overlap` (a
  replace was in progress) or `foreign` (the file is not the one this daemon published). It
  takes no lock: a publish holds `_snapshot_lock` for the whole checkpoint and copy, and a read
  must not wait behind that.
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
- **Entry:** the CSR; `built_seq`, the sequence whose snapshot it was assembled from;
  `valid_seq`, the newest sequence at which its inputs were read and found equal; the digest of
  those inputs; when; how long the read and the assemble took; node and edge counts; bytes.
- **Demand comes from `ppr_rank` only.** A key is live while it has been asked for by the op in
  the last `RMX_ADJ_IDLE_S` (default 1800). A key idle longer is dropped, counted and logged.
  Nothing is built at start.
- **At most `RMX_ADJ_MAX_KEYS` keys are live** (default 2). A request for another key while
  that many are live gets `unavailable: capacity` and is counted; it does not evict a live key.
- **Rebuild.** One thread, `rmxd-adjacency`. It wakes on a publish and on a first request for a
  key. For each live key whose `valid_seq` is older than the current sequence it:
  1. opens the snapshot with `Daemon.open_snapshot_store` ([[#r2]]). On `overlap` it opens
     again, **at most 3 times**, a short pause apart. On `foreign`, or after the third
     `overlap`, the attempt is a failed build with that cause;
  2. reads the build's inputs from that store, takes their effective edges, and digests them
     ([[#r3-inputs]]);
  3. if the digest equals the entry's, sets `valid_seq` to the store's sequence and counts a
     `revalidated`; otherwise reduces the edges it has just computed to the CSR, and swaps the
     entry in, as one reference assignment, counting a `built`;
  4. closes the store.
  It runs one key at a time. If a publish arrived meanwhile it goes round again, after the
  debounce R0 chose.
- **It never reads the writer.** Nothing in `adjacency_service`, and nothing the service calls
  to build, touches the daemon's writer store: not `Daemon.store`, not `Daemon._st()`, not a
  `Store(` open of a slot file, not `_store_lock`, not `_snapshot_lock`. Its only store is the
  one `open_snapshot_store` returns, **always for a named partition**: the service's keys
  carry the partition by name and it never opens with none. [[#ac-17]] tests where the data came from; a census
  forbids the access.
- **A failed build** (the read or the assemble raises; the snapshot's sequence cannot be
  established) is logged, recorded through `Daemon.record_sync_error` under the route
  `adjacency:<partition>` (cleared by the next good build or revalidation), counted, and passed
  to `_fast_exit_if_invalidated`. The previous entry stays. It is retried at the next wake, not
  in a loop.
- **A partition that is not in the snapshot** gives no entry and the reason
  `partition-unknown`. An entry for a partition that has gone is dropped at the next rebuild.
- **Status.** The service publishes an immutable status object, replaced by one reference
  assignment whenever it changes: per key the entry's fields and `behind`; `publish_failed`;
  and the counters `served`, `served_behind`, `unavailable` by reason, `built`, `revalidated`,
  `build_failures` by cause, `evicted`, `last_error`. Reading it takes no lock and touches no
  store, so `ping`, which is answered on the dispatcher thread, can carry it.
  `rmx daemon status` prints it. No lock of the service is held across a read or an assemble.
- **Shutdown.** The thread has a stop event, is joined inside the existing drain budget, and
  abandons work in flight. There is nothing on disk to clean.
- **Switch.** `RMX_ADJ_SERVICE=0` starts no service; the op then answers `unavailable:
  disabled`. Both settings are tested.
{#r3-list}

**The inputs, and why the check is exact.** 30.2 splits the build into steps
([[task-30.2-vectorised-adjacency-build#r1-two-steps]]): `read_adjacency_inputs` does every read
of the store; `effective_edges` turns what was read into the edge list the graph is made of,
after the `denotes` fold and after the filters (self-loops, non-positive weights, and every
edge with an operational endpoint); the reduction sorts and sums that list into the CSR. The
service calls the same `read_adjacency_inputs` and `effective_edges`, and digests the edge
list:
- the digest is of the edges **after** the operational filter. A session-card mention bit in
  the project's fragment (`build_adjacency`'s comment says a code partition's fragment can carry
  them) changes what was read and does not change the graph; digested before the filter, every
  session ingest would cost an assemble for nothing;
- it is of the edges after the fold, so a `denotes` row that is added or removed changes it
  exactly when it changes where a typed row's weight lands;
- it is independent of the order of the list, because `entity_links` is read without an order,
  and it counts repeats, because parallel edges sum;
- the reduction's only argument is that list, so equal digests mean the reduction would return
  the graph the entry already holds.
There is no second definition of what the build reads or of what it keeps. {#r3-inputs}

**Why not a mark per partition set by the write path** (the form ruling L116 names). Two facts
of the base code make it unsound:
1. `Daemon._request_snapshot` is called at the tail of a write handler, after the store lock is
   released. A publish already in flight can carry that write's rows before its mark arrives,
   and would then label the old graph current for one publish cycle. The whole-catalog sequence
   has no such window; the input check has none either, because it reads the snapshot itself.
2. A partition's graph is not written only under that partition's binding: typed rows are keyed
   by entity ids and written under whichever binding the op has, and the operational exclusion
   reads names from every partition (`build_adjacency`'s own comment says "NOT
   partition-scoped").
The input check gives what the ruling asks for, a key rebuilt only when its partition's graph
inputs changed, and is exact where a mark would be a claim. {#r3-why-not-marks}

**If R0 chose no eager rebuild** ([[#r0-policy-bands]]): the thread does not wake on a publish.
A request for a key whose entry is behind wakes it, and the request waits as [[#r4]] says.
Concurrent requests share the one pass. {#r3-ondemand}

**If 30.2's memory band is no-go:** the read and the assemble run in a child process that opens
the snapshot read-only and returns the digest, and the CSR's arrays when it assembled, over a
pipe. Nothing is written to disk. The child is reaped; a child that dies is a failed build.
Every other requirement is unchanged. {#r3-child}

### R4: the op `ppr_rank` {#r4}

Registered in the daemon's op table and in `CLI_OPS`; not a write op.

- **Arguments:** `partition`, `seed_ids`, `k`, `alpha`, `eps`, `link_weight`, `clique_weight`,
  `coverage_alpha`, `kinds`, `include_seeds`: the parameters of `rank_related_for_prompt`.
  **`partition` is required.** A request without one is an error reply (the client's
  `daemon-error`); the op never substitutes the writer's binding, and the client always sends
  its store's partition name.
- **Which graph** (plan-30 D1, option a). With the entry valid at the current sequence: serve
  it. With a newer publish pending: wait up to `RMX_PPR_WAIT_S` (default 0.25) for the service;
  then serve the newest entry if it was superseded no more than `RMX_ADJ_MAX_BEHIND_S` (default
  10) ago. Otherwise the op does not rank.
- **Behind because of a failure is not `behind`.** `unavailable: behind` is answered only when
  the last publish attempt and the key's last build attempt both succeeded: the service is
  merely late. When `publish_failed` is set, or the key's last attempt failed (a raise, an
  unstable sequence, a foreign snapshot), the entry is served inside the same bound, counted
  from the first failure, with `graph.failing` naming the cause; past the bound the answer is
  `unavailable: build-failed` with the cause.
- **`unavailable` is a result, not an error:** `{"unavailable": <reason>, "detail": …}`, with
  the reason one of `building` (no entry yet), `behind`, `build-failed`, `partition-unknown`,
  `names-unavailable`, `capacity`, `disabled`. Each is counted.
- **The ranking** is `rank_related_for_prompt(store, seed_ids, adj=entry.csr, …)`, run through
  `_read_with_fallback` with a new keyword, `writer="never"`: names and kinds come from the
  mirror or the snapshot file, and where the helper would take the writer it raises instead.
  That raise is `unavailable: names-unavailable`. The keyword's default keeps today's behaviour
  for the helper's other callers.
- **Reply:** `ranked` (the function's list), `graph` (`seq`, the entry's `valid_seq`;
  `built_seq`; `current_seq`; `behind`; `age_s`; `failing`; `nodes`; `edges`), and `walk_ms`.
- **The op never reads the writer and never takes `_store_lock`,** directly or through anything
  it calls.

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
  `graph` (`seq`, `built_seq`, `behind`, `age_s`, `failing`). `scan_prompt_cmd` writes it to
  the `query.log` row.
- **In the daemon.** The counters of [[#r3-list]], in `ping` and `rmx daemon status`.
- **In the hook's output, for a daemon that was reached and failed.** One line where the bundle
  warnings go: `# ppr ranked in-process: <reason>`. This is the rule the shared reranker
  already follows: a worker that was reached and failed is said in the output; one that is
  simply not there adds nothing. Every reason is classified, and none is left out:

  | Reason | In the output? | Why |
  |---|---|---|
  | `daemon-busy` | said | reached; did not answer in the budget |
  | `daemon-old` | said | reached; runs code without the op: a daemon not restarted after a deploy |
  | `daemon-error` | said | reached; the op raised |
  | `unavailable:build-failed` | said | the service cannot build or the daemon cannot publish |
  | `unavailable:names-unavailable` | said | reached; neither the mirror nor the snapshot could answer without the writer |
  | `unavailable:partition-unknown` | said | the hook only dials with seeds it resolved in that partition on its own replica; a daemon whose snapshot lacks the partition disagrees with the file the hook just read |
  | `no-daemon` | row and counters only | no socket: an eval harness, a test, a store that never had a daemon |
  | `daemon-absent` | row and counters only | not running; every status surface already says so |
  | `unavailable:building` | row and counters only | the first request for a key, or the seconds after a start |
  | `unavailable:behind` | row and counters only | the service is late and nothing has failed ([[#r4]]) |
  | `unavailable:capacity` | row and counters only | a configured bound ([[#r3-list]]) |
  | `unavailable:disabled` | row and counters only | a switch somebody set |
  {#r6-table}
- **In a report.** The command that summarises `scan` rows of `query.log` (R0 names it) shows,
  for its window, the rerank paths: daemon, in-process by reason, did not run.
- The installed hook discards stderr, so nothing here depends on stderr.

### R7: the degree walk reads the same adjacency, and asks for nothing {#r7}

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
- **The provider reads; it registers no demand.** It returns the service's entry for the key
  only when one is live and its `valid_seq` equals the store's sequence. Otherwise it returns
  `None`, and the caller builds as it does after release B. A degree walk therefore gains only
  on a key the hook is keeping live, which is the project partition with the default
  parameters, and can never add a key, a rebuild or 40 MB of its own.
- `context.py`'s degree walk, `ppr.py::rank_related`, `ppr.py::rank_related_for_prompt` (when
  `adj` is `None`), `enrich.py::enrich_concepts` and `net.py::build_net` call `adjacency_for`.
- No file named in `_DERIVE_PASS_MODULES` is edited: `cached_adjacency` is called, not changed.
- **Layering.** `adjacency_service` imports neither `daemon` nor `cli` at module level: the
  engine modules import `adjacency_for` from it, and the client reaches the daemon-call wrapper
  inside the function. 29.5's import-layering census stays green
  ([[task-29.5-split-giant-modules#r2b]]).
{#r7-list}

### R8: every write reaches a publish, and only the daemon publishes {#r8}

The service is as fresh as the publishes, and it trusts the snapshot file to be the daemon's.

- **Writes.** A census family on 29.3's kit lists every daemon op and background path that
  writes through the writer store, and whether it requests a snapshot. Each one that does not
  is either allow-listed with its reason or is a finding: logged in the bug registry (id from
  the lead) and fixed here if the fix is the one call. The family has a planted op that fails
  it.
- **Publishers.** A second family lists every site in `src/` that writes
  `catalog.read.duckdb`: by the literal, through `Daemon._snapshot_file`, or through a name
  bound to either. At `6676f39` there are two: `Daemon._snapshot_catalog`, and the no-daemon
  branch of the `merge-verb-aliases` command, which copies the active slot over the snapshot
  after a bare `ping` said no daemon runs.
  - `Daemon._snapshot_catalog` is the allowed publisher.
  - The command's branch is allow-listed on one recorded condition: it is reached only when the
    typed classifier says the daemon is absent ([[#r0]] item 7). A busy daemon read as absent
    would otherwise have its snapshot replaced behind its back.
  - Any other writer fails the family. It has a planted writer that fails it.
- **And at run time.** A snapshot replaced by anything else is seen by
  `open_snapshot_store` as `foreign` ([[#r2]]): a failed build, recorded and said
  ([[#r4]], [[#r6-table]]), not a graph labelled current.

### R9: docs {#r9}

`docs/ARCHITECTURE.md` (the daemon's read models: mirror and adjacency), `docs/PERFORMANCE.md`
(the measured numbers of [[#ac-10]]), `docs/INTEGRATION.md` (the hook's rerank path, the
switches of this spec), `docs/INDEX.md`. The bug registry row for bug-243 is closed with the
merge sha by the lead. {#r9-body}

## Acceptance criteria {#acceptance}

Each AC says what it is at the base sha: **RED** (the test fails there, and the red run is
recorded), **characterization** (green there, proven able to fail by the mutations named), or
**gate** (a check on the final tree, with a planted input that fails it). Daemon tests use a
short temp root inside 23.0's sandbox. The fixture store and seed sets are
[[task-30.1-adjacency-mapping-adapter#fixture]]'s. {#acceptance-labels}

- **AC-1 (RED): the daemon path equals the in-process path.** On one published snapshot, for
  every seed set, `ppr_rank`'s `ranked` equals `rank_related_for_prompt(store, …)` on a
  read-only store of the same snapshot: the same ids in the same order, scores within 1e-9.
  Recorded as sets equal of sets run. Test: `test_daemon_ranking_equals_inprocess` in
  `tests/test_adjacency_service.py`. {#ac-1}
- **AC-2 (RED): a write is followed.** Link a new edge that changes a seed set's ranking; after
  the publish and the service's pass, `ppr_rank` returns the new ranking with
  `graph.behind == 0`, `graph.built_seq` equal to that publish, and `graph.seq` grown by the
  number of publishes. The test waits on the entry's sequence, not on a sleep. Test:
  `test_rebuild_follows_a_publish`. {#ac-2}
- **AC-3 (RED): behind is bounded and stated.** With the service held (its pass made to block
  on an event the test owns): within the bound, the op serves the previous entry with
  `behind >= 1` and the old ranking, and `served_behind` counts it; past `RMX_ADJ_MAX_BEHIND_S`
  (set small), it answers `unavailable: behind`; before any build, `unavailable: building`.
  Test: `test_behind_policy`. {#ac-3}
- **AC-4 (RED): the op is served while the writer is held, and names come from a read store.**
  With `_store_lock` held by another thread for the whole test, 20 `ppr_rank` calls all return
  `ranked`, each inside the client timeout. Then, in this order: the entry is built and valid
  (the daemon runs with the mirror off); the snapshot file and the reader-slot files are
  removed, so that `_open_read_store` has nothing to open; the lock is FREE; the op is called.
  It answers `unavailable: names-unavailable` (not `building`: the entry exists) and the writer
  store's connection was not used (counted by a wrapper on the writer's connection). Test:
  `test_op_never_reads_the_writer`. {#ac-4}
- **AC-5 (RED): one dial, bounded.** With the daemon's cli pool filled by blocked ops, 50 client
  calls each return a ranking (path `inprocess`, reason `daemon-busy`); none dials twice (a
  counting socket wrapper); each returns within the timeout plus one in-process ranking; after
  the blocked ops are released, the daemon's expired-read count has risen by the number of
  calls it never started and no `ppr_rank` is in flight. Test:
  `test_client_is_bounded_under_a_full_pool`. {#ac-5}
- **AC-6 (RED): every reason is produced, named, and said or not said as the table says.** One
  case per row of [[#r6-table]]: no socket; a socket nobody listens on; a full pool; a daemon
  whose op table lacks `ppr_rank`; an op that raises; `building`; `behind`; `build-failed`;
  `names-unavailable`; `partition-unknown`; `capacity`; `disabled`. For each: the ranking equals
  the in-process ranking; `trace["rerank"]` has the path and the reason; the row written by
  `scan_prompt_cmd` carries them; the output has the warning line if and only if the row's
  second column says "said". The test reads the expected column from one table in the test
  module that has a row for every reason the client and the op can produce; a reason with no
  row fails. Test: `test_every_fallback_is_named` (parametrised). {#ac-6}
- **AC-7 (RED): a failed build is loud.** With the read made to raise: `ping` carries a
  `sync_errors` entry for `adjacency:<partition>` and the service block shows `build_failures`
  and `last_error`; the next good pass clears the entry; the daemon did not exit (the error was
  not an invalidation); the thread did not retry before the next wake (attempts counted). With
  an invalidation error, the fast-exit path runs. Test:
  `test_build_failure_is_recorded_and_cleared`. {#ac-7}
- **AC-8 (RED): liveness during rebuilds.** While 20 assembles run back to back, pings sent
  every 50 ms are all answered inside the hub watchdog's ping budget (R0 reads the value).
  Recorded as answered of sent. Test: `test_pings_answered_during_rebuilds`. {#ac-8}
- **AC-9 (RED): the degree walk builds nothing and asks for nothing.** With the project key
  live and valid, three `context` ops with degree 1 cost 0 builds between them (a counting
  wrapper on `build_adjacency`; at the base: 3) and each returns what it returned at the base
  sha. A `context` op on a partition with no live key builds as at the base, and afterwards the
  service has the same live keys as before (no demand). A store with no provider, and a store
  whose sequence differs from the entry's `valid_seq`, behave as at the base. A store opened
  while a replace overlaps gets no provider (the replace is held between its two counter steps
  by an event the test owns). Tests: `test_context_walk_uses_the_service`,
  `test_context_walk_registers_no_demand`, `test_overlapped_open_has_no_sequence`. {#ac-9}
- **AC-10 (measurement): at production scale, under load, more than once.** On R0 item 6's
  store, three runs at least 5 minutes apart, each printing the 1-minute load at both ends, each
  with a writer loop running (a sync of touched files every few seconds, and a second loop
  writing to ANOTHER partition) and each of 200 or more hook-shaped calls from seed sets taken
  in memory from recent prompts (nothing written but counts):
  - identical rankings, daemon path against in-process path on the same sequence: N of N;
  - the share of calls answered `daemon` fresh, `daemon` behind, and each fallback reason;
  - `built` and `revalidated` counts, and the service's seconds, per live key;
  - the daemon's resident memory before the first request and with the keys live;
  - the op's time through the socket: median, p90, p99; and its own stage times (queue wait,
    graph wait, walk, names);
  - the hook leg's time (`trace["rerank"]["ms"]`): median and p90, beside 30.2's.

  The result is read against [[#ac-10-bands]]. {#ac-10}
- **AC-11 (RED): the hook's own path.** `rmx scan-prompt`, run through the CLI entry as the
  generated hook runs it, against the sandboxed daemon, for 30.2's synthetic prompts: the row
  says `path: daemon` (RED at the base, where the row has no path); the output is byte-equal to
  30.2's in-process output while the graph is current. `rmx install-hooks --check` is clean and
  the generated hook command is unchanged; the verb-parity test is green with no new verb
  (both gates). {#ac-11}
- **AC-12 (gate): no derive-pass file is edited.** A function takes a list of changed paths and
  the files `_DERIVE_PASS_MODULES` names (read from the table at run time) and fails on an
  overlap. It is run on this task's `git diff --name-only <base>..<final>`; its unit test feeds
  it a list containing `src/refmatrix/pagerank.py` and sees it fail.
  `scripts/derive-digest.py check` exits 0. {#ac-12}
- **AC-13 (RED): shutdown and the switch.** A daemon stopped during a build exits inside the
  drain budget with no thread left; 29.4's session reaper finds nothing. With
  `RMX_ADJ_SERVICE=0` no `rmxd-adjacency` thread exists, the op answers `unavailable: disabled`,
  and the client does not dial. {#ac-13}
- **AC-14 (gate): every write reaches a publish, and only the daemon publishes.** Both families
  of [[#r8]] pass on the tree, and each fails on its planted site: an op that writes and
  requests no snapshot; a function that replaces `catalog.read.duckdb`. The allow-list entry
  for the `merge-verb-aliases` branch fails if that branch is reachable through a bare `ping`.
  {#ac-14}
- **AC-15 (RED): the benchmark path is the production path.** The `eval/production` harness
  that runs `scan_prompt` (R0 names it) gives the same output as at the base sha on its smoke
  fixture (characterization), with `path: inprocess` and `fallback: no-daemon` in its trace
  (RED at the base). {#ac-15}
- **AC-16 (measurement): after release, on the live logs** (the lead's, read as text, counts
  only): over 7 days, the share of `scan` rows with `path: daemon`; the hook leg's median and
  p90; and `scan-prompt`'s total p50 and p90 beside the 2818 ms and 13,042 ms of the report.
  Reported as measured. No cause is claimed for the total beyond the leg's own time. {#ac-16}
- **AC-17 (RED): the graph comes from the published snapshot, never from the writer.** The test
  owns the publishes (the snapshot tick is off).
  1. Publish. Link a new edge E through a write op, and do not publish.
  2. Make the first request for the key. Wait for the entry. **The entry's CSR does not hold
     E**, `built_seq` is the publish of step 1, and the op's ranking is the pre-E ranking.
  3. Publish. Wait for the entry. It holds E and `built_seq` moved.
  And a census family forbids writer access. **Its scope is `adjacency_service.py` and the three
  build steps in `pagerank.py`** (`read_adjacency_inputs`, `effective_edges`,
  `assemble_adjacency`). It does not scan `Daemon._open_read_store`, which must construct a
  read-only `Store` to open the snapshot; that function's one reach into the writer, the
  partition default, is closed by the required argument and tested directly:
  `open_snapshot_store(None)` raises, and `ppr_rank` without a partition is an error reply. In
  scope, the forbidden forms are `.store` on a daemon, `_st(`, a `Store(` construction,
  `_writer_lock`, `_store_lock`, `_snapshot_lock`. The allow list is empty, and there is one
  planted site per form, each failing it by name. Tests:
  `test_entry_is_built_from_the_published_snapshot`, `test_partition_is_required`. {#ac-17}
- **AC-18 (RED): the input check is exact, and a write elsewhere costs no assemble.**
  - **Sound.** For every operation of 30.0's probe table that applies to a daemon store
    ([[task-30.0-disk-tier-probe#r1-table]]) and every targeted change of 30.2's AC-1
    ([[task-30.2-vectorised-adjacency-build#ac-1]]): run it, publish, let the service pass.
    Whenever a fresh `build_adjacency` on the new snapshot differs from the previous entry's
    graph, the service assembled, and the new entry equals the fresh build. Recorded as changes
    detected of changes made; a miss fails.
  - **The digest is of the effective edges.** On edge lists built by hand: adding an edge,
    removing one, changing one weight, and repeating one each change the digest; any
    permutation of the list does not. The service's digest input is the value `effective_edges`
    returned (asserted by identity in the test), which is the reduction's only argument.
  - **A write elsewhere.** After each of these, the project key's `valid_seq` moved,
    `revalidated` grew by one, `built` did not grow, and the op answers with `behind == 0`:
    a memory added in another partition; a session card ingested into a sessions partition;
    **a session card whose ingest also writes a mention bit for it into the project's
    fragment** (the project fragment's values changed, the graph did not); a no-op publish.
  - **An endpoint changes sides.** An entity that is an endpoint here is renamed into the
    operational pattern, and back: each time the service assembled, and the entry equals a
    fresh build.
  Test: `test_input_check` (parametrised). {#ac-18}
- **AC-19 (RED): live keys are bounded.** With `RMX_ADJ_MAX_KEYS=2`: a third key's request
  answers `unavailable: capacity`, is counted, and no key is evicted; after one key has been
  idle past `RMX_ADJ_IDLE_S` (set small) it is dropped and the third key is admitted. The
  status object's live-key count never exceeds the cap during the test. Test:
  `test_live_keys_are_capped`. {#ac-19}
- **AC-20 (RED): a failed publish leaves the sequence usable and is said.** With the daemon
  module's `os.replace` made to raise for one publish (a fault on a collaborator):
  - afterwards `begin == end`, and `open_snapshot_store` returns a sequence;
  - `ping`'s `sync_errors` has `adjacency:publish`, and the status object has `publish_failed`;
  - the op serves the entry with `graph.failing` set while inside the bound, and past the bound
    answers `unavailable: build-failed`, **not** `behind`; the hook's output has the warning
    line;
  - the next good publish clears all three.
  With the copy made to fail instead (before the replace): neither counter moves, and the same
  three surfaces hold.
  With a replace held in progress for the whole test: the service opens the snapshot 3 times,
  records one failed build with the cause `overlap`, and waits for the next wake (opens counted;
  the test has its own bound and fails, it does not hang). Tests:
  `test_failed_publish_is_a_completed_step_and_is_said`, `test_reopen_is_bounded`. {#ac-20}
- **AC-21 (RED): a snapshot replaced by someone else is not served as current.** With the
  snapshot file replaced by a copy of the writer's slot behind the daemon's back (what the
  `merge-verb-aliases` branch does): the next pass records a failed build with the cause
  `foreign`; the op does not answer with `behind == 0` from the old entry beyond the bound; it
  answers `unavailable: build-failed`; the daemon's next own publish clears it. Test:
  `test_foreign_snapshot_is_detected`. {#ac-21}

### The bands for AC-10, stated before measuring {#ac-10-bands}

| Result, in every one of the three runs | Action |
|---|---|
| op p99 at or under 250 ms and fallbacks at or under 10% of calls | go |
| op p99 over 250 ms and at or under 500 ms, fallbacks at or under 10% | go; the summary names the slowest stage |
| op p99 over 500 ms, or fallbacks over 10% | no-go for release C; back to the design with the stage times |
{#ac-10-bands-table}

"Fallbacks" here are the reasons of [[#r6-table]] that are said, plus `behind`. A call answered
`building` in the first seconds after the daemon starts is not counted. The daemon's resident
memory must also grow, from before the first request to the keys being live, by no more than
1.25 × (K × E + P) as 30.2 measured them. More means something else is retained: that stops
release C the same way, with the largest live objects listed. {#ac-10-bands-note}

## Mutations that must fail {#mutations}

Each alone, seen RED (not hung) on the named AC, reverted in its own command.

1. the builder reads the writer store (`Daemon._st()`), with no lock → AC-17 step 2 (the entry
   holds E) and AC-17's census.
2. the service holds a lock across a pass → AC-3 (the op cannot answer from the previous entry
   while a pass is blocked; the test's own bound fails it, it does not hang).
3. the publish does not wake the service → AC-2.
4. the entry records the sequence read AFTER the build → AC-2 and AC-3.
5. the op serves any entry, whatever its age → AC-3.
6. the op answers `building` with an empty `ranked` instead of `unavailable` → AC-6.
7. the op calls `_read_with_fallback` without `writer="never"` → AC-4 (the writer's connection
   is used).
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
21. `end` is incremented after the replace, outside any `finally` → AC-20 (`begin != end` after
    the failed replace).
22. the reopen has no bound → AC-20 (`test_reopen_is_bounded` fails on its count).
23. a failed publish sets no state → AC-20 (the op answers `behind`).
24. the digest leaves out the weights → AC-18 (sound; the hand-built lists).
25. the digest is taken before the operational filter → AC-18 (a write elsewhere: `built` grew
    on the session card with a project-fragment bit).
26. the digest hashes the edges in arrival order → AC-18 (a permutation changes it).
27. the service sets `valid_seq` without reading the inputs → AC-18 (sound) and AC-2.
28. the provider registers demand → AC-9 (`test_context_walk_registers_no_demand`).
29. the cap is not enforced → AC-19.
30. `open_snapshot_store` does not compare the file's identity → AC-21.
31. `names-unavailable` is classed as an operating state → AC-6.
32. the `merge-verb-aliases` branch is allow-listed without its condition → AC-14.
33. `open_snapshot_store` accepts `partition=None` → AC-17 (`test_partition_is_required`).
34. the digest is taken before the `denotes` fold and leaves the `denotes` rows out → AC-18
    (sound: a removed `denotes` row moves a weight and is not detected).
{#mutations-list}

## Test strategy {#test-strategy}

- **RED first, by `ch-test-engineer`.** The tests of the ACs labelled RED are written before
  any `src/` edit and run at the base sha; the red run is kept
  (`workflow/review-output/task-30.4/red.log`) with each test's E line. A characterization part
  is recorded green at the base and says so. A test labelled RED that passes at the base is a
  finding about the test.
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
- **Mocks.** The blocked pass, the counting socket wrapper, the held lock, the failing
  `os.replace` and the counting wrapper on the writer's connection all act on collaborators;
  classified in `workflow/test_mock_registry.md`. The ranking function, the op, the service
  and the digest are never patched.
- **Measurements** ([[#ac-10]]) are three runs at least 5 minutes apart, under two writer
  loops, each with its loads. A single quiet run is not accepted.
- **All output to files** under `workflow/review-output/task-30.4/`.
{#test-strategy-list}

## Caller census {#census}

At `6676f39`. R0 re-runs it.

| Changed | Callers and readers |
|---|---|
| `scan.py::_ppr_rerank` | `scan.py::scan_prompt`; `scan.py::_net_rerank` (two fallbacks); `tests/test_scan_prompt_dedup.py`; `eval/spike_hypertree/m4_render_tokens.py` |
| `ppr.py::rank_related_for_prompt` | `scan.py::_ppr_rerank`; the new op; tests as in 30.1 |
| `pagerank.cached_adjacency` (called through `adjacency_for`) | `context.py`'s degree walk; after 30.2: `ppr.py` (two), `enrich.py`, `net.py` |
| `pagerank.read_adjacency_inputs`, `pagerank.effective_edges`, `pagerank.assemble_adjacency` (30.2's; called, not changed) | `pagerank.build_adjacency`; the service |
| `Daemon._snapshot_catalog` (the counters, the identity, the failure state, the wake) | the snapshot tick; `_op_snapshot`; R0 lists any other |
| `_MemMirror.refresh` (sequence, provider) | daemon start; `_snapshot_catalog` |
| `Daemon._open_read_store` (reached through the new `open_snapshot_store`; unchanged itself) | `_read_with_fallback` and the read ops that call it |
| `_read_with_fallback` (the `writer` keyword; its private branch attaches the provider) | 16 call sites at `6676f39`; each keeps the default except the new op; `_op_context` is the one that passes `private=True` with a degree walk |
| the op table and `CLI_OPS` | `Daemon._handle`; tests that enumerate ops (R0 lists) |
| `_op_ping`'s result (the service block) | the hub watchdog; `rmx daemon status`; tests of the ping shape (R0 lists) |
| the `query.log` `scan` row (`rerank` object) | every reader of `scan` rows: the reports of plan-21 (`tests/test_task21_1_query_rows.py`), R0 lists the rest |
| `Store` (the `adjacency_provider` attribute) | `adjacency_for` only; 29.2's store host declarations |
| writers of `catalog.read.duckdb` | `Daemon._snapshot_catalog`; the `merge-verb-aliases` command's no-daemon branch ([[#r8]]) |
| the generated hook command | unchanged ([[#ac-11]]) |
{#census-table}

## Invalidation {#invalidation}

- An entry is exact for the inputs it was assembled from, and is known valid at `valid_seq`.
  A publish makes it behind until the service has read the new snapshot's inputs: equal, and
  `valid_seq` moves; different, and the entry is replaced.
- The publish is the write-batch boundary as every reader outside the writer sees it.
  [[#r8]] checks that every write reaches one and that only the daemon publishes; a snapshot
  from anywhere else is `foreign`.
- An entry is dropped when its key has been idle, when its partition is gone, and when the
  process exits. A failed pass leaves the old entry to age out by the bound, and says so.
- The provider hands a read store an entry only when the entry is valid at that store's own
  sequence; a store whose sequence is unknown gets no provider.
- Slot rotation, replica refresh, `rebuild_index_from_log` and the repair ops reach the service
  through the same publish.
- Nothing is on disk. There is no merge, purge or slot census to owe.
{#invalidation-list}

## Files {#files}

| File | Change |
|---|---|
| `docs/adr/NNNN-daemon-held-read-models.md`, `docs/adr/0000-adr-overview.md`, `docs/INDEX.md` | [[#r1]] |
| `src/refmatrix/adjacency_service.py` | new: the service, the digest, the op, the client, `adjacency_for` |
| `src/refmatrix/daemon.py` | [[#r2]]; `open_snapshot_store`; `_read_with_fallback`'s keyword; start and stop of the service; the op's registration; the `ping` block |
| `src/refmatrix/store.py` | the `adjacency_provider` attribute |
| `src/refmatrix/scan.py`, `src/refmatrix/cli/session_cmds.py` | [[#r5]], [[#r6]] |
| `src/refmatrix/context.py`, `ppr.py`, `enrich.py`, `net.py` | [[#r7]] |
| `src/refmatrix/cli/daemon_cmds.py` | `rmx daemon status` prints the block |
| the module that holds `merge-verb-aliases` after 29.5 | only if [[#r0]] item 7 finds the gate unconverted |
| the report command R0 names | [[#r6]] |
| `tests/test_adjacency_service.py`, `tests/census/` (three families: writer access, writes that publish, publishers) | new |
| `workflow/measurements/plan-30-daemon-adjacency/` | the replay, the input-check timing, the socket measurement, their logs |
| `docs/ARCHITECTURE.md`, `docs/PERFORMANCE.md`, `docs/INTEGRATION.md` | [[#r9]] |
| `workflow/test_mock_registry.md` | the collaborators of [[#test-strategy]] |
| `workflow/implementation_summaries/task-30.4-daemon-adjacency-ppr-op.md` | new |
{#files-table}

## Risks {#risks}

- **The hook waits on the daemon.** One dial, 0.5 s, no retry, then the 30.2 path. AC-5 and
  AC-10 measure it under a full pool and under writes.
- **A deploy leaves an old daemon with a new hook.** The op is unknown to it; the client ranks
  in-process and says `daemon-old`. AC-6.
- **The service costs the daemon CPU at every publish, per live key.** R0 prices it per key
  and per publish, the input check removes the assemble when the key's inputs did not change,
  and the cap bounds the keys. If the check is too slow to be worth it, R0's band turns it off
  and prices the full build instead.
- **Memory.** At most `RMX_ADJ_MAX_KEYS` entries, about 40 MB each at this store's size, plus
  one build's peak. 30.2's band prices that sum and decides in-process or child; AC-10 reads
  the daemon's resident memory against it.
- **The digest and the build drift apart.** They cannot: the service calls the build's own read
  and its own `effective_edges`, and digests the one value the reduction takes.
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
- Keeping an adjacency live for degree walks on partitions the hook does not use ([[#r7]]).
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
  is never read, so the build needs no store lock; and the version is the daemon's own counter
  pair, moved under the lock that publishes, so "which graph is this" has an exact answer.
- **plan-30 D12: a key is rebuilt when its inputs changed, decided by reading them, not by
  per-partition marks** ([[#r3-why-not-marks]]). This departs from the wording of ruling L116
  ("per-partition versions") and keeps its purpose. **Accepted** by ch-bsd r2
  ([[bsd-plan30-spec-r2]]) and by the lead (ruling L117, written on `master` at the merge).
- **plan-30 D13: demand comes from the hook's op only, and live keys are capped at 2.** A
  degree walk reads a live key and never creates one. Without this, any `context` op on any
  partition would add a key that every publish then pays for.
- **No verb, no MCP tool.** An agent does not call `ppr_rank`; `scan-prompt` does. The parity
  rule is about capabilities an agent can call.
- **The warning line follows the reranker's rule** (reached and failed: said; absent: not),
  and every reason has a row in [[#r6-table]].
- **Timeout 0.5 s.** The fallback costs about 0.5 s, so waiting longer than that for the daemon
  is a loss. AC-10's bands can stop the release; they do not tune this number.
- **A new module.** `daemon.py` is 7,355 lines against a 3,000-line target.
{#decisions-list}

## Revision note 2 (2026-11-15, ch-bsd r1 and ruling L116) {#rev-note-2}

| Finding ([[bsd-plan30-spec-r1]]) | Answered in |
|---|---|
| S1: "never the writer" had no test that could fail | [[#ac-17]] (a write held unpublished must not be in the entry; a census of writer access with an empty allow list and a planted site per form); [[#ac-4]] and `writer="never"` in [[#r4]] for the op's own reads; mutations 1 and 7 |
| S2: one key was priced, every key rebuilt | [[#r0]] items 3-5 (per key, per publish; the check's own cost band); [[#r3-inputs]] and [[#ac-18]] (assemble only when the key's inputs changed); [[#r3-why-not-marks]] (why the check and not a mark); the cap and [[#ac-19]]; [[#r7]] and [[#ac-9]] (a degree walk registers no demand); 30.2's band now prices the steady state |
| S3: a publish failing after `begin` | [[#r2]] (`end` in a `finally`; failure recorded); [[#r3-list]] (at most 3 opens); [[#r4]] (a failure is `build-failed`, never `behind`); [[#ac-20]]; mutations 21-23 |
| M1: RED labels on tests green at the base | [[#acceptance-labels]]: every AC is labelled; AC-12 and AC-14 are gates with a planted failing input; AC-15's output part is characterization |
| M2: two reasons unclassified | [[#r6-table]]: `names-unavailable` and `partition-unknown` are said, each with its reason; AC-6 reads the table and fails on a reason with no row; mutation 31 |
| M5: a snapshot writer outside the daemon | [[#r8]] (a family over every writer of the snapshot file; slice d as a checked precondition); the file identity in [[#r2]]; [[#ac-21]]; mutations 30 and 32 |
{#rev-note-2-table}

Also changed in this round, not from a finding: the op takes its names through
`_read_with_fallback(writer="never")`. Round 1 passed `writer_wait_s=0`, which reads the writer
whenever its lock is free; that contradicted the spec's own "never reads the writer".
{#rev-note-2-also}

## Revision note 3 (2026-11-15, ch-bsd r2: GO with four MEHs) {#rev-note-3}

| Finding ([[bsd-plan30-spec-r2]]) | Answered in |
|---|---|
| M1: the digest was taken before the operational filter | [[#r3-inputs]]: the digest is of `effective_edges`' output, after the fold and the filters; [[#ac-18]] gains the session card that writes a project-fragment bit, and an endpoint renamed into and out of the operational pattern; mutations 25 and 34 |
| M2: the census scope, and the writer's binding behind `partition=None` | [[#ac-17]] states the scope (`adjacency_service.py` and the three build steps); `partition` is required in `open_snapshot_store` ([[#r2]]) and in the op ([[#r4]]); mutation 33 |
| M3: which service time the 2% band reads | [[#r0]] item 5: the worst case |
| M4: AC-4's no-read-store leg answered `building` | [[#ac-4]]: the entry is built first, then the read stores are removed |
{#rev-note-3-table}
