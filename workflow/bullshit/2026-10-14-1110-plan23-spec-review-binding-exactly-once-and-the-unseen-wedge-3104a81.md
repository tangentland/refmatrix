---
gmd: "0.1"
id: bsd-plan23-spec-review-3104a81
title: "plan-23 spec review: the drain yields the shared writer with no partition rule (bug-098), promises exactly-once with a marker outside the transaction, and its probes cannot see the per-row-write wedge that motivates it"
severity: BULLSHIT
plan: plan-23-bounded-write-harness
task: spec-review-23.1-23.2
round: 1
tags: [bsd, audit, spec-review, queue, drain, lock, harness, partition, bug-085, bug-093, bug-098]
---

# ch-bsd spec review of plan-23, round 1 (pre-implementation) {#root}

**Commit reviewed:** `3104a81` (branch `wave0-spec-reviews`). HEAD moved to `03bd532` while I
worked. Those two commits touch only the handoff, and `git diff 3104a81..HEAD` is empty for every
file reviewed here. **Written:** 2026-10-14T11:10:30-0700.

**Scope:** the plan file `workflow/plans/plan-23-bounded-write-harness.md` and task specs 23.1 and
23.2. I also read its consumers (19.2, 17.1, 16.6 R4, 22.1 R3, 22.2 R5), the plan review's C5, and
the storage exploration's Option A.

**Method:** every factual claim was checked against code at `3104a81`:
- `daemon.py`: `_FairLock` :200-276, `LEARN_DRAIN_BUDGET_S` :647, the flush tick `_runner`
  :2030-2077, `_drain_learn_queue` :2079-2180, `_partition_keeping_yield` :3313-3335,
  `_learn_grep_hits` :4295;
- `learn_queue.py` (all 175 lines);
- `store.py` `with_partition` :1911;
- `cli.py` `_broker_learn_from_grep` :640-680 and `learn status` :7292-7370;
- the three tests that 23.2 R4 names, plus `tests/test_learn_queue.py`;
- `workflow/bug_registry.md` rows bug-049, bug-085, bug-088 and bug-093;
- memories `project_bug098_writer_partition_race` and `project_suite_reaches_live_sockets`.

No suite or mutation was run, and no store or socket was touched. Nothing in `src/`, `tests/`,
the ledger files or any plan file was edited.

rel: specifies -> [[plan-23-bounded-write-harness]]
rel: related-to -> [[task-23.1-queue-and-drain]]
rel: related-to -> [[task-23.2-lock-hold-fixture]]
rel: related-to -> [[exploration-storage-concurrency-redesign]]
rel: related-to -> [[project_bug098_writer_partition_race]]
rel: contradicts -> [[claude#no-silent-failures]]

## Verified facts {#verified}

| claim in the spec | at `3104a81` | verdict |
|---|---|---|
| learn_queue: "append without the lock, coalesce by key, cap with a counted overflow" | `enqueue` is one `O_APPEND` line with no lock or socket. `read_rotated` coalesces by pattern and UNIONS hits by `(file, line)`. Overflow is counted at drain time, after parsing, and the newest entries win. | true. The coalesce is a MERGE, not a key ([[#s-2]]). |
| learn drain = "one `_store_lock` hold per batch" | `_drain_learn_queue` takes the lock **once per coalesced entry**. `test_the_drain_yields_the_writer_lock_between_entries` asserts `acquisitions == 8` for 8 entries, and its docstring calls the batch-wide hold "starvation written as a test". bug-049 says the batch-wide design "was corrected in review". | the plan's R2 shape is the contract that was SUPERSEDED ([[#s-1]]) |
| learn drain has a time bound with a warning | it has a whole-tick deadline (`LEARN_DRAIN_BUDGET_S`=5 s), a shutdown stop, fatal-invalidation handling (mark repair + deferred exit), and it REQUEUES the remainder. Nothing measures a single hold. | the spec's per-hold warning is a different, new mechanism. The learn drain's four stop paths are missing from R2's signature ([[#s-1]]). |
| crash safety | `read_rotated` UNLINKS the rotated file after parsing and BEFORE any entry is applied. Nothing in `src/` or `tests/` ever reads an orphaned `*.draining` file. A SIGKILL mid-drain (the bug-085 watchdog kills) loses the in-memory batch, and nothing counts it. | R3 is a real fix to a live silent loss, not "identical behaviour" ([[#b-2]]) |
| overflow "counted in `rmx learn status`" | the overflow appears only in the daemon's `rmxd.log` drain line. `learn status` prints `pending_lines` and only when learning is OFF. No persisted counter exists. | a new surface with no defined route ([[#s-6]]) |
| `_store_lock` semantics | `_FairLock`: strict FIFO, ownership handed explicitly on release, no owner check, not reentrant. `acquire(blocking=False)` is False if the lock is held OR waiters are queued. | The fakes in all three adoption tests use `threading.RLock()` / `threading.Lock()`, so none runs on the production lock ([[#s-4]]). |
| the binding a yield must keep | `with_partition` mutates the ONE writer Store's `_partition_id`/`_partition_name`. Only `_partition_keeping_yield` (0.77.1, bug-098) restores them after a reacquire. `_learn_grep_hits` writes into whatever binding the store has at rest. | the spec never mentions it ([[#b-1]]) |
| who drains | only `_drain_learn_queue` runs on the 30 s `_runner` tick, and it has its own 5 s budget. Nothing registers queues. | each consumer would wire its own call and its own budget ([[#s-3]]) |
| consumers | 19.2 R4 / AC-4, 17.1 R3 / AC-4, 16.6 R4 / AC-3, 22.1 R3, 22.2 R5. plan-of-plans also has plan-21 depending on 23, but no 21.x spec names plan-23. | See [[#consumer-fit]]. |

{#verified-body}

## Consumer fit {#consumer-fit}

| consumer | what it needs | what plan-23 provides | gap |
|---|---|---|---|
| 19.2 R4 / AC-4 (usage events) | exact counts (`lifetime_hits`, `lifetime_used`), coalesce = SUM, `partition_id` in the key, ≤ 2 holds per 500, "never held longer than the batch bound" | key-only coalesce; a marker outside the transaction; a hold warning, not a bound; no partition rule | [[#b-1]], [[#b-2]], [[#s-2]], [[#s-5]] |
| 16.6 R4 / AC-3 (marks) | `stale_seen` = a COUNT (sum), `last_verified_at` = max | key-only coalesce; double apply on a crash | [[#b-2]], [[#s-2]] |
| 17.1 R3 / AC-4 (per-dataset holds) | a bounded STEP loop over an in-memory list of datasets, released between steps, a hold recorder, and a handle refresh before release | `drain(queue, …)` takes a durable JSONL queue. A dataset list is not a queue. | [[#s-3]] |
| 22.2 R5 (repair/remove) | "one lock hold per batch, **one Lance delete per kind**" | no post-drain finalize step, so a per-batch apply issues one Lance delete per batch: bug-085 one level up | [[#b-3]] |
| bug-093 follow-up (yield between files in the watch flush) | a yield inside `_sync_paths`, which today holds the lock across a transaction by design (`_drain_learn_queue`'s own comment: "the rule `ingest_path` follows and `_sync_paths` deliberately does not") | nothing. It is not queue-shaped, and no task spec owns it. | [[#s-3]] |
| r8 #s-2 / r9 #s-1 (model call under a lock) | a free/held probe fired from INSIDE the model call, on `_store_lock` AND on the mirror `_use_lock` (r9 #b-2's shape) | `lock_free_during`, under two different signatures | [[#m-1]] |

{#consumer-fit-body}

## Findings {#findings}

### BULLSHIT b-1: the drain multiplies yields on the shared writer and says nothing about its partition binding (bug-098 by construction) {#b-1}

**Where:** 23.1 R2 (`drain(queue, apply_batch, lock, …)`, "release between batches"). The plan's
consumer list.

**What:** the harness exists to add a RELEASE point between every batch of every writer. The daemon
has ONE writer `Store` whose partition is mutable state. bug-098, the third bug from this mechanism
in a week (r9 #b-1, r10 #s-1, bug-098), happened exactly when a holder kept a `with_partition`
across a release: another op bound its own partition, and the first resumed writing into it. The
only binding-safe yield is `_partition_keeping_yield` (`daemon.py:3313`), and it is daemon-coupled
(`d._st()`, `d._store_lock`). R2 takes a bare `lock` and an opaque `apply_batch`, so the harness
cannot even see the binding. A consumer that writes the obvious code does `with
st.with_partition(p): drain(q, apply, d._store_lock)`, which re-creates bug-098 at every batch
boundary. The consumers are multi-partition: 19.2 keys rows by `partition_id`, 16.6/22.x run
against the global store and both partitions, and the learn drain writes into "whatever is bound at
rest".

**Why it is bullshit:** the plan is the shared cure for lock-hold bugs. It ships the yield and
leaves out the part of the yield that caused this month's data-corrupting bug. No AC can fail on it,
because no AC runs a concurrent op on another partition.

**Fix:**
- R2: the drain binds per batch, inside the hold, in ONE `with` (`with lock,
  st.with_partition(ev_partition):`). It never holds a binding across a release. Events carry
  their partition NAME (not an id; see r10 #s-1's id-1 fallback).
- Or: the drain takes a `bind(batch) -> context manager` from the daemon, which is Option A's seam
  ([[#option-a]]).
- AC: queue 2 batches for partition `pa`. Between them, a competitor takes the lock, binds `pb`,
  writes, and releases while still bound. Assert 0 rows of the drain's batch land in `pb`.
- Mutation: hoist the bind outside the batch loop. It must FAIL.

**Pattern match:** YES (impression `#imp-lock-fix-moves-the-answer`, memory
`project_bug098_writer_partition_race`).

### BULLSHIT b-2: R3's exactly-once cannot hold with a marker outside the transaction, and AC-2 kills at the one moment with no window {#b-2}

**Where:** 23.1 R3 ("applied events are not re-applied (an applied-offset marker)") and AC-2
("killed after batch 2 resumes at batch 3").

**What:**
- The batch commits in DuckDB, and the marker is a file. A crash between the commit and the marker
  write re-applies the batch on restart. A crash between the marker write and the commit loses it.
- Killing "after batch 2" means at a batch BOUNDARY, where both are already durable. So AC-2 passes
  for a marker written in either order, and it cannot fail on the defect R3 names.
- The consumers that need exactly-once are counters:
  - 19.2's `lifetime_hits` / `lifetime_used` (its R2 says "exact");
  - 16.6's `stale_seen`.

  A double apply over-counts them forever. The learn drain survives replays only because its writes
  are idempotent (set bits, `INSERT OR IGNORE`-shaped evidence).
- R3 also contradicts R4's "identical behaviour". Today `read_rotated` unlinks the file BEFORE it
  applies anything, and no code ever reads an orphaned `*.draining` file. A SIGKILL mid-drain
  silently loses the batch, uncounted, on the memory path that `CLAUDE.md#no-silent-failures`
  covers. bug-085's wedges ended in exactly those kills.

**Fix:**
- Store the offset in the catalog, in the SAME transaction as the batch (a `queue_offsets(queue,
  segment, offset)` row). Or give every event an id and make `apply_batch` idempotent through a
  dedupe table. State which one.
- Keep the segment file until its last offset commits.
- Recover orphaned `*.draining` files at boot.
- AC: inject a fault between the commit and the marker (and the reverse) for a COUNTING apply.
  Assert the count equals the number of events, never more or less.
- Name R3 as a behaviour change for learn (a bug row for the pre-existing loss), and give it its own
  RED test.

**Pattern match:** YES (`feedback_decay_never_loses_knowledge`; impression `#imp-count-in-a-dict`
family: a loss nobody can see).

### BULLSHIT b-3: the probes cannot see the wedge shape the plan was written for {#b-3}

**Where:** plan `#why` ("bug-085: one Lance delete per entity. bug-093: one upsert per concept"),
23.1 R2 (per-batch time bound "logs a warning"), and 23.2 R1-R3 (free/held probe, hold durations,
`max_lock_hold`).

**What:**
- Both named wedges were many small WRITES inside ONE hold. Neither was a hold that was too
  frequent, and neither was a model call.
- The harness detects two things:
  - a held lock at a probe instant;
  - a hold longer than T seconds.
- On a test fixture, a per-row Lance delete or upsert costs milliseconds. bug-085's 1-2 s per
  delete came from 61k uncompacted versions (impression `#imp-batch-one-level-down`). So a
  consumer whose `apply_batch` loops per row passes `max_lock_hold` and every 23.x AC.
- bug-085's and bug-093's own RED tests counted what happened: Lance versions committed, and
  single-row upserts. That count is the detector that works, and plan-23 does not include it.
- 22.2 R5 needs "one Lance delete per kind" across all batches. R2 has no finalize step after the
  drain, so the natural implementation deletes once per batch: the same loop, one level up.

**Why it is bullshit:** the plan claims this harness makes the cure tested "once, in one place".
For the two incidents it names, no AC in 23.1 or 23.2 fails when the cure is reverted.

**Fix:**
- 23.2 adds a write-count recorder: DuckDB statements executed and Lance version delta per hold.
  The marker asserts `O(1)` per batch, not only seconds.
- 23.1 R2 adds `finalize(applied)` after the last batch, run under its own hold.
- AC: a consumer `apply_batch` that loops one upsert per event, or one Lance delete per batch, must
  FAIL through the fixture.

**Pattern match:** YES (`impression_bsd_guard_cannot_fire`, `#imp-batch-one-level-down`).

### SKETCHY s-1: R2's "N per hold" re-imposes the superseded learn contract, and R4's "unchanged tests" forces N=1 plus four stop paths R2 omits {#s-1}

**What:** `test_the_drain_yields_the_writer_lock_between_entries` pins one acquisition per entry, and
its `_CountingLock` wraps only `__enter__`/`__exit__`. A drain that calls `lock.acquire()` breaks it.
The budget, shutdown and invalidation tests patch `dmod.LEARN_DRAIN_BUDGET_S` and
`dmod._learn_grep_hits` and read `d._logs`. R2's signature (`batch`, `hold_s`) has no:
- whole-drain budget;
- cancel or shutdown check;
- error policy (fatal invalidation → mark repair, arm deferred exit, stop);
- requeue of the remainder.

So "existing tests pass unchanged" is reachable only if learn runs at N=1 through `with lock:`, and
the drain grows four parameters the spec does not name.

**Fix:** write the full signature: `drain(…, budget_s, cancel, on_error, requeue)`. Say that learn
runs at N=1 and why (its entries are per-pattern transactions). Say that the per-hold T is an
alarm, not a stop.

### SKETCHY s-2: "coalesce by key" cannot express the merges the consumers need {#s-2}

**What:** learn UNIONS hits per pattern. 19.2 must SUM counts per `(partition, name, channel)`.
16.6 must sum `stale_seen` and take the max of `last_verified_at`. `BoundedQueue(path, key_fn,
max_lines)` gives no way to say which merge applies. A last-wins or first-wins default silently
undercounts 19.2, which violates its `#rule-no-undercount`.
Also, with coalescing, "1,000 events take ⌈1000/N⌉ holds" holds only for 1,000 DISTINCT keys.

**Fix:** add `merge_fn(acc, ev)` as a required parameter. AC-1 states distinct keys. Add an AC that
coalesces 1,000 events over 10 keys with a SUM merge and checks the totals.

### SKETCHY s-3: three named consumers do not fit `drain(queue, …)`, and nothing registers a drain on the tick {#s-3}

**What:**
- 17.1's per-dataset steps and the bug-093 between-file yield are bounded loops over an in-memory
  list. They are not durable queues.
- The bug-093 follow-up also has to yield inside `_sync_paths`, which deliberately holds across a
  transaction. That makes it a design problem, not a harness call. No task spec owns it, so it is
  an unanchored consumer.
- The `_runner` tick knows one drain (learn, 5 s budget). Each new queue would add its own call and
  its own budget, so N queues stretch the tick to N×5 s ahead of the fragment flush. That is the
  "re-derive per consumer" problem C5 was meant to end, one level up.

**Fix:**
- Split the API: `bounded_steps(items, apply, lock, …)` (no durability) under `drain(queue, …)`.
- Add a queue registry on the tick, with ONE shared budget and an order.
- File the bug-093 yield as its own task, or drop it from the consumer list.
- Add plan-21 to the consumers or remove the plan-of-plans edge.

### SKETCHY s-4: 23.1 AC-1 can pass on a drain that holds across batches, and the tests never touch `_FairLock` {#s-4}

**What:** "exactly 5 holds" does not say who counts them. If the count is the drain's own
`batches` return value, the AC is a tautology. "A probe thread acquires the lock between batches"
passes when it wins ONCE, so a drain that holds batches 1-4 together passes.

Every existing fake daemon uses `threading.RLock()` or `Lock()`. Under an RLock, a nested
reacquire on the same thread is invisible. The production lock is `_FairLock`, whose hand-off
semantics are the reason a yield works at all (its docstring).

**Fix:** count holds with 23.2's recorder, on a real `_FairLock`. A queued competitor must win
between EVERY consecutive pair of batches (4 ordered wins). Mutation: one hold around all batches
must FAIL. Move 23.2 ahead of 23.1, or merge them, because 23.1's ACs need 23.2's recorder (today
23.2 "depends on 23.1").

### SKETCHY s-5: `max_lock_hold` is vacuous when no recorder is installed, and "the bound" is a warning {#s-5}

**What:**
- The marker does not name a lock. A test that carries the marker but never installs
  `hold_recorder` on `d._store_lock` records zero holds and passes. A test that installs it after a
  callee captured the lock reference (`ingest_path(lock=d._store_lock)`) records nothing either.
- The plan table promises "each ≤ the bound", but 23.1 R2 only logs a warning. 19.2 AC-4 ("never
  held longer than the batch bound") and 17.1 AC-4 inherit a guarantee that does not exist.

**Fix:** the marker fails on zero recorded holds. It requires a fixture that patches the lock
before the code under test runs. The plan text calls T an alarm, and consumers assert on the
recorder at fixture scale.

### SKETCHY s-6: the overflow "counted in `rmx learn status`" has no route from the daemon to the CLI {#s-6}

**What:** the overflow is counted inside the daemon's drain and lands only in a log line.
`learn status` runs in the CLI and shows queue depth only when learning is off. AC-3 has no
persisted counter and no daemon health key to read.

**Escalated** from MEH: this is the third "count in a dict / log line is not a surface" round
(r7, r8, impression `#imp-count-in-a-dict`).

**Fix:** a cumulative overflow counter persisted next to the queue, or a `_store_health` key.
`learn status` prints it unconditionally. Test it through the CLI on a tmp store.

### SKETCHY s-7: the tests the spec implies are not sandboxed (bug-088) {#s-7}

**What:** AC-2 "killed" is undefined. A real kill means a spawned daemon, and spawned subprocesses
are invisible to the conftest recorder. The recorder only records, has no refuse stage, and
`_root()`/`$HOME` are not isolated (bug-088, deferred by the user). A drain test with an unpatched
`_root()` reaches the LIVE daemon socket, as the 2026-10-07 bulk-forget dry run did.

**Fix:** the spec states it:
- in-process `Daemon(root)` + `Store` on a short `mkdtemp` root (the `test_learn_queue.py`
  `_daemon_with_store` shape);
- faults injected with an exception or `os._exit` in a forked child of the drain only;
- `_root` patched, `daemon.ping` False;
- no `rmx` subprocess;
- the recorder count is unchanged before and after.

### MEH m-1: `lock_free_during` has two signatures and cannot be a context manager "from inside" {#m-1}

The plan says `lock_free_during(fn)`, and 23.2 R1 says `lock_free_during(lock)` as a context
manager. A context manager wraps the CALL. It cannot fire at the moment the model runs, which is
why the inline probes are hooks inside fake `score` / `embed_texts`. Spec a `probe(lock) -> bool`
for fakes to call, plus the recorder. It must accept any lock, because the r9 #b-2 probe in
`test_read_path_partition_and_budget.py` targets the mirror's `_use_lock`, not `_store_lock`.

### MEH m-2: AC-3's grep will fail on files R4 does not adopt {#m-2}

`tests/test_learn_queue.py` (`_CountingLock` and the competitor thread) and
`tests/test_bigop_nonblocking.py` also carry inline lock probes. Adopt them in R4, or define the
AC-3 grep pattern and its exclusions.

### MEH m-3: stale "ONE lock acquisition" docstrings ride along {#m-3}

The `learn_queue.py` module docstring ("applied under ONE lock acquisition") and the
`tests/test_learn_queue.py` module docstring (plus the section header at :125) state the
superseded contract. The re-base touches both. R4 should correct them, because a reader of the new
harness will take them as its spec.

## Option A (storage exploration) {#option-a}

**Recommendation: stay NEUTRAL, but cut the seam now.**
- **Do not absorb A.** Option A is a ~7k-line refactor of every `self._partition_id` read.
  Measurement #4 (its concurrency and ART risk) has not run. The exploration is "In progress …
  nothing measured yet". Making wave 1's first build wait on that would stall 17/19/22.
- **Do not build a harness that hard-codes today's shared binding either.** Make the drain take a
  `bind(batch) -> ContextManager[handle]` from its owner:
  - today it is `with d._store_lock, d._st().with_partition(p): yield d._st()`;
  - under A it becomes a per-op cursor handle;
  - the `apply_batch(handle, events)` code of the consumers does not change.

  That one parameter closes [[#b-1]] and makes plan-23 the first adopter of A's interface, not a
  second thing A has to refactor.
- **Is bug-098 covered?** No. Plan-23 does not mention it, and its yields widen bug-098's surface
  ([[#b-1]]).
- **Order conflict.** The exploration says "A first … absorbs parts of plans 22 and 23". The plan
  review puts 23 first in wave 1. These conflict, and the user should rule ([[#decisions]]).

{#option-a-body}

## User decisions needed {#decisions}

1. **Exactly-once mechanism** ([[#b-2]]): an offset row in the catalog transaction, or event ids +
   an idempotent apply (a dedupe table)? Counting consumers (19.2, 16.6) need one of them.
2. **Option A ordering:** keep 23 first with the `bind` seam (recommended), or run A's measurement
   #4 first, as the exploration's "A first" suggests?
3. **bug-093 between-file yield:** a new task (it needs a transaction-boundary design in
   `_sync_paths`), or drop it from plan-23's consumers?
4. **Learn crash loss** ([[#b-2]]): log it as a bug row now (a pre-existing silent loss), fixed by
   23.1 R3?

{#decisions-body}

## Verdict {#verdict}

**NEEDS-REVISION.** 13 findings: 3 BULLSHIT (b-1, b-2, b-3), 7 SKETCHY (s-1 … s-7), 3 MEH (m-1 …
m-3).

The queue half (append without a lock, coalesce, counted overflow) is real and matches
`learn_queue.py`. The drain and fixture halves are under-specified in exactly the places this month's
bugs lived:
- the partition binding across a yield;
- the crash window between two durable writes;
- per-row writes inside one hold.

{#verdict-body}

## Ledger entries (to merge) {#ledger}

INDEX.md row:

```
| 3104a81 (plan-23 spec review r1, pre-implementation; HEAD 03bd532 handoff-only; written 2026-10-14T11:10:30-0700) | 2026-10-14 | Todd Holley / Opus 5.5 / orchestrator | DIRTY | 13 (3B/7S/3M) | [[bsd-plan23-spec-review-3104a81]]. NEEDS-REVISION. BULLSHIT: (1) the drain yields the ONE writer Store between batches with no partition rule (bug-098 by construction; consumers are multi-partition; fix = bind inside the hold, or a `bind()` seam = Option A's interface); (2) R3 exactly-once with an offset file outside the DuckDB transaction; AC-2 kills at a batch boundary (no window); 19.2/16.6 are counters; today read_rotated unlinks BEFORE apply and no code recovers *.draining (silent loss on SIGKILL); (3) the probes (free/held, hold seconds) cannot see bug-085/093's per-row writes inside one hold at fixture scale; there is no write-count recorder and no finalize step (22.2's one-Lance-delete-per-kind becomes one per batch). SKETCHY: N-per-hold re-imposes the superseded learn contract, and unchanged tests force N=1 plus budget/cancel/error/requeue missing from R2; key-only coalesce (SUM/MAX/UNION); 17.1 + bug-093 not queue-shaped, no tick registry, bug-093 yield unowned; AC-1 passes on a drain holding across batches, tests never use _FairLock, 23.1 needs 23.2's recorder; max_lock_hold vacuous with no recorder, "bound" is a warning; learn-status overflow has no route (3rd count-not-surface); kill/sandbox unspecified (bug-088). MEH: lock_free_during two signatures; AC-3 grep misses test_learn_queue/test_bigop_nonblocking probes; stale ONE-acquisition docstrings. Option A: neutral, cut the bind seam. |
```

IMPRESSIONS.md bullets:

- 2026-10-14 (plan-23 spec r1): A HARNESS THAT ADDS YIELDS MUST OWN WHAT A YIELD RELEASES. The
  shared bounded drain takes a bare lock, while the lock's holder also owns the ONE writer's
  partition binding (bug-098). For any "release between batches" spec, ask what other state the
  holder owns (binding, open transaction, cached handle), and demand a test with a competitor that
  changes it between batches.
  {#imp-yield-owns-the-binding}
- 2026-10-14 (plan-23 spec r1): EXACTLY-ONCE ACROSS TWO STORES IS A CLAIM ABOUT THE WINDOW BETWEEN
  THEM. An offset file next to a DuckDB commit double-applies or loses, depending on the order. An
  AC that kills "after batch 2" sits at the boundary, where there is no window. Put the fault
  BETWEEN the two writes, on a counting consumer.
  {#imp-exactly-once-window}
- 2026-10-14 (plan-23 spec r1): A TIMING PROBE CANNOT SEE A COST THAT LIVES IN ACCUMULATED STATE.
  bug-085/093 were per-row writes inside one hold, slow only on a 61k-version dataset or a 600 MB
  catalog. The detector is a COUNT (statements, Lance versions per hold), which is what both RED
  tests used. A seconds bound at fixture scale passes the regression.
  {#imp-count-not-seconds}

rel: related-to -> [[impression_bsd_guard_cannot_fire]]
