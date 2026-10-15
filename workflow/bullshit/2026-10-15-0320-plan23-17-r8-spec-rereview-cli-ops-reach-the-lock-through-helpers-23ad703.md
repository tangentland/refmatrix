---
gmd: "0.1"
id: bsd-plan23-17-spec-rereview-r8-23ad703
title: "plan-23 + plan-17 spec re-review r8: all 9 r7 findings closed in text. New 23.5 claims no cli op waits on _store_lock unbounded, but `snapshot` and 10 `_read_with_fallback(writer_wait_s=None)` calls in cli handlers still do, and R7's direct-body AST rule cannot see a helper. 23.1 AC-20's shutdown case passes on the pre-existing _final_flush. 17.4's restore verify cannot tell a bad log from a normal tombstone skip at 0.78.3"
severity: BULLSHIT
plan: plan-23-bounded-write-harness
task: spec-rereview-r8-23.1-23.5-and-17.1-17.4
round: 8
tags: [bsd, audit, spec-review, re-review, plan-23, plan-17, read-path, heartbeat, cli-pool, mem-mirror, compaction, restore, wave-1]
---

# ch-bsd spec re-review r8 of plan-23 and plan-17 at `23ad703` {#root}

**Commit reviewed:** `23ad703` (branch `wave0-spec-reviews`; `git log -1` confirmed). The plan-23/17
revision under review is `6fa243d` (round 7), plus `e23fae7` (bug-115 summary: ownership is d9az /
23.5) and `f2c7169` (d9ba pin). `src/` is 0.78.3: bug-115/116 (`607d759`, `1c86d9c`) and bug-117
(`391ffeb`) are merged and reachable from `master` (`b381b6d`). **Written:** 2026-10-15T03:20:08-0700.

**Method:**
- Read only. No plan, spec or source edit; no live store or socket opened. Live `cli.log` was
  read read-only.
- Every round-7 `#facts` claim was re-read at HEAD. An AST walk over `daemon.py` (scratchpad
  script) resolved each `CLI_OPS` name through `OPS` to its handler. For each handler it recorded
  whether the handler takes `_store_lock` directly, calls `_read_with_fallback` or `_writer_lock`,
  or calls a same-module helper that takes the lock.
- d9av..d9bd are read from `workflow/plan-review-2026-10-14.md`; later rows win.

rel: derives-from -> [[bsd-plan23-17-spec-rereview-r7-331b414]]
rel: related-to -> [[plan-review-2026-10-14]]
rel: specifies -> [[plan-23-bounded-write-harness]]
rel: specifies -> [[plan-17-nightly-store-maintenance]]
rel: contradicts -> [[claude#no-silent-failures]]

## Round-7 findings: status {#prior-status}

| id | status | evidence at `23ad703` |
|---|---|---|
| nb23-r7-1 named-safe census route | **closed in text; AC residue** [[#ns23-r8-4]] | 23.1 R1.6 item 4 says "every site is MOVED UNDER THE LOCK … There is no 'named safe' route". `_do_close` now has a bounded acquire and logs `<n> dirty fragment(s) NOT flushed`. The init rebind runs in `with self._store_lock:` with `close()` in a `finally`. `Store.close()` re-raises `WriterLockNotHeld` after the closes and collects other errors in `close_errors`. Files table added. **Correction to my r7:** the claim that bits are "dropped on every daemon stop" was wrong. `serve_forever` runs `_final_flush` under a bounded `_store_lock` acquire (`daemon.py:1478`, called at `:2033`) BEFORE `_do_close` (`:2052`), and r7 missed it. The silent-raise defect was real, but its impact was overstated. |
| ns23-r7-1 purge check after Lance | **closed** | R1.6 item 3: "`purge_entity`, `_bulk_purge_ids` and `purge_path` call `_require_writer_lock("purge")` as their first statement". AC-20 runs the case through all three entry points and asserts Lance `version`, the vector and `vectors_updated_at`. Mutation: "check only in `_clear_purged_bits`". |
| ns-x-r7-1 19.2/16.6 on `replica_merge` | **closed (d9ay)** | `plan-19…:199` "RETIRED, not closed by 23.1 R8 (round 7, d9ay"; `task-16.6…:188` "R1c … RETIRED (d9ay)". Residue: plan-23 open item 8 still says "plans 19 and 16 own that decision" ([[#nm23-r8-4]]). |
| nm23-r7-1 one-installer AST rule | **closed** | Any `Assign`/`AugAssign`/`AnnAssign`-with-value/tuple element/`setattr(…,"store",…)`, exactly one exemption. The `AnnAssign` is now at `daemon.py:746` (was `:728`). |
| nm23-r7-2 `HoldRecorder` surface | **closed** | 23.1 adds an explicit `HoldRecorder.held_by_current_thread()` in `tests/lockhold.py` (files table), with a mutation. 23.5 repeats the pattern ([[#nm23-r8-2]]). |
| nm23-r7-3 AC-3b dangling row alive | **closed** | "the concept's `concepts` row AND its `entities` row are both deleted". |
| nm17-r7-1 restore classes | **closed in text; residue** [[#ns17-r8-1]] | Lock discriminator "`Could not set lock on file`"; an unparseable log is (b); there is a new (c) verify-fail run; the ART-index precedent moved to (a); a class-keyed mutation added. The new run's fixture no longer discriminates at 0.78.3. |
| nm17-r7-2 in-process entry point | **closed; residue** [[#nm17-r8-1]] | `_op_vectors_restore(d, args, *, in_process_caller="removal_restore")`; the closed-set check lives in the op; the wire cannot claim the value. AC-13's "no socket connect" has no instrument. |
| nm17-r7-3 hold bound | **closed** | 17.3 `HOLD_BOUND_S = HEARTBEAT_STALE_S − 2 × HEARTBEAT_INTERVAL_S` (50 s), "A hold of 55 s FAILS"; 17.1 `RMX_MAINTAIN_HOLD_S` default from the same formula. |

**Closure:** 9 of 9 closed in text. Three have residue, filed below.
{#prior-status-body}

## New findings: task 23.5 (first review) {#findings-235}

### BULLSHIT nb23-r8-1: 23.5's central claim is false as specified. `snapshot` and ten `_read_with_fallback` calls in cli handlers still wait on `_store_lock` without a bound; #facts says the memory reads "take no lock"; R7's AST rule sees only a handler's own body {#nb23-r8-1}

**Where:** 23.5 `#facts` ("`memory_get`, `memory_search` and the other memory reads already use
it and take no lock"); R1 (the 11 ops); R6 ("With R1-R3, no cli op waits on `_store_lock` longer
than `RMX_CLI_WRITER_WAIT_S`"); R7; AC-1; the files table ("the 11 read ops").

**What, at HEAD:**
- **`snapshot` is in `CLI_OPS`** (`daemon.py:6378`). `_op_snapshot` (`:4088`) calls
  `d._snapshot_catalog(force=True)`, which holds `with self._store_lock:` (`:2700`) across a
  `CHECKPOINT` and a child `cp -p` of the writer slot. The wait is unbounded and the hold grows
  with the catalog. 23.5 lists the snapshot only as a "non-harness holder … measured, not
  changed". It never names it as a cli op that parks a worker.
- **Ten calls in cli handlers pass no `writer_wait_s`, so it defaults to `None`, meaning
  unbounded** (`_read_with_fallback` signature `:4895-4897`). They are `context` `:4810`,
  `describe` `:4866`, `memory_get` `:5033`, `memory_iter` `:5047`, `memory_search` `:5063`,
  `memory_recent` `:5080`, `memory_score` `:5211`, `subject_list` `:5366`, `subject_leaves`
  `:5374`, and `memory_recall`'s prefilter `:6101`.
  - When the read stores lack the partition, each call checks the writer under
    `with _writer_lock(d, None)` (`:4957`).
  - The same happens when no snapshot exists at all (the final fallback, `:4975`).
  - The `missing="empty"` default exists because "a memory partition a fresh project never
    wrote is normal". On such a project, every memory read takes the writer lock unbounded.
- **R7 checks only each handler's own body.** `_op_snapshot` contains no `_store_lock` text, so
  it passes. The ten calls above are in handler bodies, so R7 as written FAILS at HEAD on nine
  handlers that R1 and the files table do not touch. The spec contradicts itself, and its claim
  "A new `CLI_OPS` op that takes the lock fails it" is false for any op that reaches the lock
  through a helper.
- **AC-1 exercises only R1's 11 ops.** A `memory_search` on an absent partition, or a `snapshot`,
  parks a worker for the whole 10 s hold, and no AC sees it.

**Fix (spec text):**
- `#facts`: replace "take no lock" with: "they take `_store_lock` UNBOUNDED through
  `_read_with_fallback`'s writer fallback (`writer_wait_s=None`) when the read stores lack the
  partition or no snapshot exists (the 10 sites listed above). `snapshot` is a cli op that holds
  `_store_lock` through `_snapshot_catalog`."
- **R1 gains item 1b:** every `_read_with_fallback` call reachable from a `CLI_OPS` handler passes
  `writer_wait_s=_cli_writer_wait(d)`, the same bound as R2. On `LookupError` the op answers
  `writer busy: <holder> …; not run` (R4's name). List the 10 sites.
- **R1 gains item 1c:** `snapshot` leaves `CLI_OPS` for the bg pool. It is a forced writer-side
  checkpoint and copy, and no production caller exists (only `tests/test_save_state_embeds_memories.py:89`
  and `tests/test_snapshot_tier.py:179`, which must be updated).
  - Alternative: `_snapshot_catalog(force, wait_s=)` takes the lock through `_writer_lock(self, wait_s)`.
- **R7 becomes transitive:** from each `CLI_OPS` handler, follow calls to same-module functions
  and `d.<method>` / `self.<method>` `Daemon` methods to a fixpoint. Any reachable
  `with <x>._store_lock`, `<x>._store_lock.acquire(` without a timeout, `_writer_lock(…, None)`,
  or `_read_with_fallback(` without a non-`None` `writer_wait_s=` fails.
  - New mutations (each must FAIL): `snapshot` back in `CLI_OPS` unchanged;
    `_op_memory_search` without `writer_wait_s`.
- **AC-1 gains:** during the hold, `memory_search` against a partition absent from the
  snapshot, and (if R1c keeps `snapshot` on the cli pool) `snapshot`, each answer within
  `RMX_CLI_WRITER_WAIT_S` + 0.5 s.
- Files table: "the 11 read ops" becomes "the 11 read ops, the 10 `_read_with_fallback` call
  sites, `snapshot`".

**Pattern match:** YES. This is `#imp-consolidated-0914` "guards built for the fixed state", and
nm23-r7-1's sibling: a static rule that matches one spelling of the thing it forbids.

rel: contradicts -> [[claude#no-silent-failures]]

### SKETCHY ns23-r8-1: R1 routes `stats(include_health)` through `_read_with_fallback`, but `_store_health` nests `_read_with_fallback` (the mirror's use-lock is non-re-entrant) and reads the WRITER (`d._st()`) {#ns23-r8-1}

**What:**
- `_store_health(d)` (`daemon.py:3829`) calls `_read_with_fallback(…, writer_wait_s=0)` once
  for the partition list and once per partition (`:3903`, `:3909`).
- The mirror path holds `mirror.acquire_use()`, a plain `threading.Lock()` ("one reader at a
  time", `:365`). Called from inside an outer mirror `fn`, the cli worker self-deadlocks forever.
- Called outside, `_store_health` still runs `d._st().recent_memories(limit=1)` and reads
  `d._st()._partition_name` on the WRITER without the lock (`:3855`, `:3902`). That is the
  writer's DuckDB connection used concurrently with whatever holds the lock, which is bug-098's
  class. 23.1 R1.6's check guards writers only, so nothing raises.
- R1 says only "including `include_stale` and `include_health`, see AC-7". AC-6 would hang on
  the deadlock shape. No AC sees the unlocked writer read.

**Fix:**
- R1 adds: `_op_stats` calls `_read_with_fallback(d, d.partition, lambda rs: rs.stats(),
  private=False, writer_wait_s=…)`. `include_stale` uses the same pattern with
  `rs.stale_files()` (see [[#nm23-r8-3]]). `_store_health(d)` runs OUTSIDE any
  `_read_with_fallback` `fn`.
- `_store_health` stops touching the writer connection:
  - `memory_read_ok` comes from `_read_with_fallback(d, <memory partition>, lambda rs:
    rs.recent_memories(limit=1), writer_wait_s=0)`. Recommended decision: health checks the READ
    path, which is what serves every memory read after R1.
  - `db_file` / `slot_bound` read `d.store.db_path` (an attribute, no connection).
  - `own_name` = `d.partition`.
- AC-6 adds `include_health=True` during the hold; it must answer within 1 s with
  `memory_read_ok: true`.
- Mutation: `_store_health` called inside the outer `fn` FAILS (the op hangs).
- An AST assertion: `_store_health` contains no `d._st()` call.

### SKETCHY ns23-r8-2: R1 moves long reads onto the mirror's single use-lock; the coupling moves from `_store_lock` to `_use_lock` {#ns23-r8-2}

**What:**
- R1 makes only `memory_recall` and `ann_search` `private=True`. `query`, `grep_indexed`,
  `derive_history`, `derive_status`, `partition_audit` and `stats` run on the shared mirror under
  its one `_use_lock`.
- `_MemMirror`'s own docstring says "reads must complete quickly so `_use_lock` doesn't gate
  everyone". The r9 #b-2 precedent is the same defect (the context rerank).
- One multi-second `query` on the mirror parks the other 3 cli workers on `_use_lock`. Four such
  queries stop the heartbeat exactly as four `stats` on `_store_lock` did.
- AC-1 runs on a small fixture with 8 clients, so it cannot see this.

**Fix:**
- R1 adds a rule: an op is non-private only if its measured p99 on a copy of the live read
  snapshot (835 MB, the r7 copy method) is under 50 ms. Otherwise it is `private=True`. R8's
  census records each op's p99 and its path.
- AC-1b: a test seam stalls one `query`'s `fn` for 3 s on the mirror path. Meanwhile `stats` ×4
  each answer within 1 s and the heartbeat age stays under 1 s.
- Mutation: `query` non-private with the seam FAILS.

### SKETCHY ns23-r8-3: R2's `min(<remaining deadline_s>, …)` has no plumbing, and its writes contradict 0.78.2's shipped rule; #facts item 3 is stale {#ns23-r8-3}

**What:**
- 23.5 `#facts` 0.78.2 item 3 says the deadline drop "also covers the two cli-pool writes …
  although the code comment says 'Writes are never dropped'".
- At HEAD, `1c86d9c` (prompted by r7) added `CLI_WRITE_OPS = {partition_add, partition_rename,
  stop}` (`daemon.py:6352`), and `expires` is `None` for them (`:3236`).
- So for R2's two writes there is no deadline to take a minimum of. For `replica_audit`, the
  `expires` value lives only in `_handle`'s closure and never reaches the handler.
- R2 also makes those writes answer "not run" after 5 s. That reverses the rule `1c86d9c` just
  shipped ("a caller that timed out on a write has not withdrawn it"), and the spec does not say
  so.

**Fix (recommended decision):**
- Move `partition_add` and `partition_rename` out of `CLI_OPS` to the bg pool. Writes are then
  never dropped, as shipped, and no write parks a cli worker. The cli pool becomes read-only plus
  `stop`.
- R2 then covers `replica_audit` only.
- The remaining deadline reaches the handler through a thread-local set INSIDE the wrapped `run`
  (on the worker thread): `_op_deadline.expires`. `_cli_writer_wait(d)` returns
  `min(expires − now, RMX_CLI_WRITER_WAIT_S)`, or `RMX_CLI_WRITER_WAIT_S` when no deadline was
  sent.
- `#facts` item 3 is rewritten to HEAD.
- AC-2 is rewritten:
  - `partition_add` during the hold is accepted on the bg pool, completes after the release,
    and no cli worker is occupied (the 8-client reads still answer).
  - `replica_audit` answers `writer busy:` within 1.5 s.

### MEH nm23-r8-1: R5 says "replay folds events in order", but replay sorts by `ts`; hold 1 copies the whole writer slot; AC-5 bounds no hold {#nm23-r8-1}

- **Ordering:** `rebuild_index_from_log` does `events.sort(key=lambda e: e.get("ts", 0))`
  (`store.py:7941`). Dumped events carry catalog `created_at` / `updated_at` /
  `GREATEST(c.updated_at, e.updated_at)`, so R5's correctness rests on every dumped ts being
  earlier than every tail ts.
  - Fix: state that invariant.
  - AC-5's competitor adds an `unlink` of a dumped edge and a tombstone of a dumped entity; the
    rebuild must lack both.
  - Mutation: the tail written BEFORE the dump bytes still passes (ts sort), so drop that framing
    from the text.
- **Hold 1** runs a full `CHECKPOINT` + `cp` of the writer slot (835 MB on the live store; a
  41 GB catalog is on record), and doubles the disk use.
  - Recommended: reuse the snapshot. `_snapshot_catalog` already CHECKPOINTs and copies under
    the lock, so record `L0` inside that hold and `os.link` the fresh snapshot before releasing
    `_snapshot_lock`, then dump from the link. Compaction then adds no copy hold, only hold 2.
  - Either way, AC-5 asserts each hold is ≤ `RMX_HOLD_ALARM_S` on the fixture, and R8 records
    hold 1 on the 835 MB copy.

### MEH nm23-r8-2: R4's thread-local is set on the wrong thread; the recorder lacks the accessor; AC-6's "hold inside a `stats` test op" violates R7; existing `_inflight_ops` ignored {#nm23-r8-2}

- "the dispatcher sets a thread-local op name before it runs a handler". The dispatcher thread
  only `submit`s. Handlers run on cli or bg workers (`daemon.py:3255`). Fix: set it in the
  wrapped `run` on the worker.
- `writer_holder` is read "under `_FairLock._mu`". On a recorded daemon `_store_lock` is 23.2's
  `HoldRecorder` with its closed surface, so this is nm23-r7-2 again. Fix: add
  `tests/lockhold.py` (`HoldRecorder.holder()` explicit pass-through) to 23.5's files table.
- AC-6 takes the hold "inside a `stats` test op", but a cli op taking the lock fails R7. Fix:
  use a test-registered bg-pool op.
- `#facts` "no log line names a holder" is partly false: `_final_flush` already names in-flight
  ops from `_inflight_ops` (`daemon.py:1527-1541`). R4 should extend that registry with the
  holder flag rather than add a parallel one.

### MEH nm23-r8-3: AC-7 branches on its own result; private reads' freshness ignores open bug-112 {#nm23-r8-3}

- AC-7 says "If they differ, `include_stale` takes R2's bounded writer path instead". That is an
  AC that decides the design at test time.
- The `_op_stats` comment "the replica/snapshot never refreshes" `tracked_files` dates from the
  rotation era. The snapshot is a full post-CHECKPOINT copy, so `tracked_files` lags by one
  debounce.
- Fix: R1 decides that `include_stale` uses the snapshot. Delete the branch and correct the
  comment.
- R1's freshness contract ("at most `RMX_SNAPSHOT_DEBOUNCE_MS` + one refresh") does not hold on
  the `private=True` path while bug-112 is open. DuckDB's instance cache returns a replaced,
  unlinked snapshot to a second in-process opener (`bug_registry.md` bug-112).
  - Fix: R1 cites bug-112 as the known exception for private reads.
  - AC-7 adds a case: a private reader open across a forced snapshot, then a second private read
    sees the new link. If it fails, bug-112 becomes a 23.5 dependency.

### MEH nm23-r8-4: line drift and stale labels (23.1, 23.5, plan-23, 17.3) {#nm23-r8-4}

- `src/` moved under the specs, so these cites are stale (77ac38f → HEAD):

  | cited at 77ac38f | at HEAD |
  |---|---|
  | `_do_close` `:2018` | `:2052` |
  | init rebind `:1727-1732` | `:1757-1766` |
  | `srv.bind` `:1807` | `:1841` |
  | installer sites 1665/1734/1757/2888/2924/5490/5508/5557 | 1699/1768/1791/2936/2972/5575/5593/5642 |
  | `CLI_OPS` `:6264` | `:6355` |
  | heartbeat `:1305-1342` | `:1323-1358` |
  | `_op_stats` lock `:3732` | `:3817` |
  | compaction lock `:2346` | `:2380` |
  | tick `:2380` | `:2428` |
  | `_read_with_fallback` `:4810` | `:4895` |
  | `_writer_lock` `:4911` | `:4996` |
  | `_op_context` learn `:4747` | `:4832` |

  - 17.3 cites `daemon.py:1319-1337` and `:3732`.
  - AC-20's mutation names "the `:5557` site". Fix: cite by symbol ("the third
    `d.store = Store(` in `_op_replica_merge`").
- 23.5's dependency is now satisfied. `607d759`, `1c86d9c` and `391ffeb` are ancestors of
  `master` (`b381b6d`).
  - Fix the header and `#facts` "NOT on `master`".
  - `CLI_OPS` still has 31 entries, but `ping` is now answered on the dispatcher, so 30 reach
    the cli pool.
- plan-23 open item 8 still says "plans 19 and 16 own that decision". Fix: "SETTLED (d9ay, both
  plans applied)".

{#findings-235-body}

## New findings: task 23.1 {#findings-231}

### SKETCHY ns23-r8-4: AC-20's shutdown case passes on the pre-existing `_final_flush`; the "close() swallows" mutation survives {#ns23-r8-4}

**What:**
- `serve_forever` flushes under a bounded `_store_lock` acquire in `_final_flush`
  (`daemon.py:1478`, called at `:2033`) BEFORE `_do_close` (`:2052`). 23.1's round-7 `#facts`
  omits it.
- So the positive case's "the `bitmap_fragments` row holds the bit" holds with or without the
  fix.
- The mutation "`Store.close()` swallowing `WriterLockNotHeld` as before" is exercised by
  neither case:
  - In the positive case `_do_close` holds the lock, so nothing raises.
  - In the lock-held case `close()` is never called.
  - Its stated failure ("the bit is missing AND no 'store close failed' line") cannot occur.
- "`_do_close` without the lock" IS killed, but by the log line, not the missing bit.

**Fix:**
- `#facts` names `_final_flush`.
- The shutdown case asserts mechanism, not outcome. On the recorded daemon, a test seam inside
  `Store.flush_fragments` records `writer_lock().held_by_current_thread()` and the thread name;
  the flush run by `close()` reports `True` on `rmxd-close`; and there is no "store close" error
  line.
- A Store-level case: a Store with `writer_lock` installed and one dirty fragment.
  `close()` from a thread without the lock raises `WriterLockNotHeld`, AND its connection is
  closed (`_conn is None`), AND the fragment row is unchanged.
  - Mutation: swallowing FAILS (no raise).
  - Mutation: re-raising before the closes FAILS (`_conn` still open).
- Drop "bit missing" as the stated failure of both mutations.

{#findings-231-body}

## New findings: plan-17 {#findings-17}

### SKETCHY ns17-r8-1: 17.4 R6 step 3's verification is undefined for a real live log, and at 0.78.3 the AC-9 (c) fallback fixture is indistinguishable from a normal tombstone skip {#ns17-r8-1}

**What:**
- Step 3 verifies the throwaway "against the source's own event counts (AC-3's check)". AC-3
  compares against the SOURCE CATALOG's recorded counts, and a restore has no catalog.
- On a real live log (a dump plus appends: re-links, unlinks, tombstones), raw event counts
  never equal rebuilt row counts. A count rule therefore routes nearly every (c) to the day-old
  backup, which is the loss ns17-r6-1 closed.
- 0.78.3 (bug-117) made the rebuild report `links_unresolved`, `evidence_unresolved`,
  `links_skipped_dead` and `evidence_skipped_dead` (`store.py:8075-8080`).
  - `*_skipped_dead` is normal: a link whose end was tombstoned.
  - The new AC-9 (c) fixture ("a `link` event whose entity name has no `entity` event … rebuild
    skips it, `store.py:8079-8085`") is exactly a `links_skipped_dead`.
  - Its line cite is stale.
- So a verify keyed on skips also fails every real log. A verify that ignores skips never
  reaches the fallback the AC claims to prove.
- Related, pre-existing in `src/`: the rebuild `continue`s silently on a non-JSON line
  (`store.py:7938`), so 17.4's parse probe is the only guard against a corrupt line.

**Fix:**
- Define step 3 as three checks, all required:
  1. `rmx rebuild --from-log` exits 0;
  2. its reported `links_unresolved == evidence_unresolved == 0`;
  3. the rebuilt entity, link and evidence counts equal an independent fold of the source log
     with replay's rules (ts order; tombstones; the last `link`/`unlink` per key; both ends
     alive).
- `*_skipped_dead` is printed, never a failure.
- AC-9's fallback fixture becomes a legacy `link` event with no `c_kind`, whose concept name is
  held by two non-`concept` kinds in the partition. `resolve_legacy_kind` returns `None`, so
  `links_unresolved = 1`, and verification fails for a reason a real log can have.
- Mutation: a verify that ignores `links_unresolved` FAILS (no fallback, `source: live`).
- Optional bug-registry row: the silent bad-line `continue` in `rebuild_index_from_log` (a
  no-silent-failures violation on a memory path).

### MEH nm17-r8-1: 17.1 AC-13's "the 23.0 sandbox's connect log is empty for the daemon's socket" names a log that does not record such connects {#nm17-r8-1}

- 23.0 R3's audit hook appends only connects whose target is in the DENY set
  (`task-23.0…:75-77`). It replaced the record-all `_recording_connect`. A tmp daemon's socket is
  not in that set, so the log is empty whether or not the in-process call went through the verb.
- **Fix:**
  - AC-13 installs its own counter for the call's duration: a `sys.addaudithook` counting
    `socket.connect` events whose address equals the tmp daemon's socket path.
  - Assert 0.
  - Mutation: routed through the verb, count ≥ 1 FAILS.

{#findings-17-body}

## Approval readiness {#approval}

| task | verdict | what remains |
|---|---|---|
| 23.0 | approved (d9at) | none |
| 23.2 | approved (d9at) | 23.1 and 23.5 each add one explicit `HoldRecorder` pass-through in `tests/lockhold.py`; no reopen |
| 23.1 | **needs edit pass** (small) | ns23-r8-4 (AC-20 shutdown case + `_final_flush` fact); nm23-r8-4 drift (symbol cites) |
| 23.3 | **ready** | unchanged since r6/r7 |
| 23.4 | **ready** | d9ba pin `6fa243d` = `git log -1` of the file. 23.4's `store.py:4377-4395` order is verified at HEAD (`:4376-4396`): entity-dead → linkage skipped → concept-dead. d9ba is orchestrator-recorded ("flagged to the user"), so a one-word user ack is advisable because it supersedes a user-backed pin |
| 23.5 | **needs edit pass** (not blocked) | nb23-r8-1, ns23-r8-1/2/3, nm23-r8-1/2/3/4. Two decisions, both recommended above: `partition_add`/`partition_rename` (and `snapshot`) to the bg pool; health checks the read path |
| 17.1 | **ready after a one-line edit** | nm17-r8-1 |
| 17.2 | **ready** | unchanged |
| 17.3 | **ready** | drift only (nm23-r8-4) |
| 17.4 | **needs edit pass** | ns17-r8-1 (verify definition + fallback fixture) |

{#approval-body}

## Verdict {#verdict}

**DIRTY. 11 findings (1 BULLSHIT, 5 SKETCHY, 5 MEH).** All 9 r7 findings are closed in text, with
residue on 3. The trend is 19 → 17 → 10 → 9 → 9 → 11; the rise is the first review of 23.5. The
BULLSHIT is in 23.5: its R6 promise ("no cli op waits on `_store_lock` longer than
`RMX_CLI_WRITER_WAIT_S`") is false as specified, because `snapshot` and ten
`_read_with_fallback(writer_wait_s=None)` calls in cli handlers stay unbounded and R7's AST rule
cannot see a helper. Every fix is spec text; the two design calls each have a recommendation.
Plan-17 needs one SKETCHY edit (17.4) and one MEH (17.1). Plan-23: 23.3 and 23.4 are approvable
now, 23.1 after one AC edit, and 23.5 after one edit pass.
{#verdict-body}
