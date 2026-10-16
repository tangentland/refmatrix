---
gmd: "0.1"
id: bsd-plan18-r1-spec-review-b84fd8d
title: "ch-bsd plan-18 r1 spec review (18.2 + 18.3 rewrite): rollback can boot the old file under the new file's WAL; a deadline interrupt between statements is lost; growth band flags A2 where Table A says A0; the lock-order mutations cannot fail"
tags: [ch-bsd, plan-18, task-18.2, task-18.3, spec-review, duckdb, reclaim, swap, wal, lock-order]
severity: BULLSHIT
plan: plan-18-duckdb-store-maintenance
task: task-18.2-catalog-maintain-step + task-18.3-offline-reclaim
round: 1
---

# ch-bsd plan-18 r1 spec review: 18.2 catalog_maintain + 18.3 in-daemon reclaim {#root}

**Spec commit:** `b84fd8d` (plan-18 rewrite). The branch is `wave0-spec-reviews`. During the run
HEAD moved to `428267f` (r9 ledgers, d9bu) and then `879faa7` (18.1 r2 re-run, d9bv). The only
plan-18 change in those commits is one line in `#verdict-18-1` citing the r2 report. Every 18.2
and 18.3 spec line reviewed here is unchanged, and B-3 is re-checked against the r2 jsonl.
**src:** HEAD `src/` is identical to `23ad703` (`git diff 23ad703 HEAD -- src` is empty).
**bug-112/113 fix:** read-only from `/Volumes/littlebig/refmatrix-bugs112-118` (branch
`bugs-112-113-118`, uncommitted diff on `b381b6d`).
**Probes:** run with duckdb 1.5.3 (`~/refmatrix/.venv/bin/python -I`), on scratch files and on
a `/bin/cp` copy of orderly's snapshot under `/private/tmp/claude-501/p18r1/`. No live store
was opened and no socket was touched.
**Written:** 2026-10-15T03:51-0700.

rel: derives-from -> [[bsd-plan18-task18-1-measurement-r1-8a93ab1]]
rel: related-to -> [[bsd-plan23-17-spec-diffcheck-r9-b84fd8d#ns23-r9-1]]
rel: contradicts -> [[task-18.3-offline-reclaim#r6-rollback]]
rel: contradicts -> [[task-18.3-offline-reclaim#r4-hold]]
rel: contradicts -> [[task-18.2-catalog-maintain-step#r5-band]]

## Verified (no finding) {#verified}

- **The six I1 sites and their lines** match HEAD: snapshot `:2669/2702/2714`, `_op_checkpoint`
  `:3956/3971`, init rebind `:1762/1768/1791`, bootstrap `:2878/2924/2930/2936/2960/2972`,
  merge `:5485/5533/5575/5593/5642`, `rmx compact` `cli.py:7630`. The only other `_snapshot_lock`
  user is `_snapshot_catalog`, and nothing calls `_snapshot_catalog` while holding `_store_lock`.
  So the order rule in I2 holds at HEAD.
- **The sentinel and `total_blocks` catch the cached reopen.** On orderly's copy: writer 87
  blocks, rewrite 48. After `DETACH`, close, link, replace, and a fresh `Store` + `init()`, the
  reopened file reports `total_blocks` 48, the same as step 5. The sentinel reads back. The
  inode matches. A cached old database would show 87 blocks and no sentinel table.
- **An interrupted COPY is clean.** Interrupting `COPY FROM DATABASE` into an ATTACHed file
  raised `InterruptException` after 0.55 s. The writer then took an insert and a CHECKPOINT. The
  partial target was 350 MB, with no `.wal`. So R6 A's "delete the partial file" is needed and
  sufficient.
- **The forward swap (link + replace) is sound for the main file.** The slot name always points
  at a complete inode, `backups/` is on the same filesystem (it already exists in live roots),
  and step 8's WAL check covers the forward direction.
- **The arming record matches 17.2 R7:** a hand dry-run line, then a later hand real-run line.
  R13's untouched list matches d9ao.

## Findings {#findings}

### BULLSHIT B-1: a rollback after the reopen restores the old inode beside the NEW file's WAL, and DuckDB 1.5.3 replays that foreign WAL silently and corrupts the restored file {#b-1}

**Where:** 18.3 R6 B (rollback), R4 steps 10-11, AC-6.

**What the spec says:** "Only `os.link` and `os.replace` touch the slot's NAME, so a crash at
any point leaves the slot naming a complete file". R6 B restores with
`os.link(backup, <slot>.rollback)` + `os.replace(<slot>.rollback, slot)`. It does not say to
close the reopened writer first. It does not check `<slot>.wal`. AC-6's crash points are all
in the forward Phase B.

**Measured:**

- **Every reopen writes a WAL.** `Store.init()` runs `UPDATE linkage_types SET inverse_of=…` on
  every open (`store.py:1199-1206`). After step 10 on orderly's copy, `catalog.A.duckdb.wal`
  was 1,204 bytes. So any rollback that runs after step 10 (identity mismatch, sentinel absent,
  count mismatch) leaves a WAL that belongs to the NEW file next to the slot.
- **A foreign WAL is replayed without an error** (`p3b_wal.py`).
  - The old file had 200,000 rows, then `DELETE i < 150000` and a CHECKPOINT.
  - The new file was a `COPY FROM DATABASE` of it.
  - A child opened the new file at the slot path, deleted 10 rows (`i` 150000-150009), and hard
    exited, leaving `slot.wal` (188 bytes).
  - The old inode was then restored with link + replace, the way R6 B does it.
  - The open SUCCEEDED and returned count 52,038 (expected 50,000), `min(i)` 122,890 (rows
    deleted in the old file came back), and the 10 targeted rows still present.
  - DuckDB logs deletes by row id, and a rewrite renumbers row ids. So replaying the new file's
    WAL onto the old file lands on the wrong rows. Nothing reports it.

**Why it matters:** this is the store-corruption mode that R6 exists to prevent. It is reached
on the path R6 calls safe:

- the `rolled_back:sentinel` case (bug-112's class);
- the failed-rollback `os._exit(2)` (the respawn replays the WAL);
- a SIGKILL between the restoring replace and the moment the reopened connection closes.

The bug-112 fix's `_close_stale_holders` happens to close the new-file connection before the
next write open, but that is luck of ordering, not a stated step.

**Fix (R6 B, in this order):**

1. `h.close_writer()` on the reopened writer. That checkpoints and removes its WAL.
2. Require `<slot>.wal` to be absent or 0 bytes. If it is not, `os.replace(<slot>.wal,
   backups/catalog.<S>.reclaim-failed-<run_id>.duckdb.wal)` BEFORE the restore.
3. Then the link + replace restore.
4. Then `reopen_writer`.

Also:

- **State the invariant as "the slot name, plus a `.wal` that belongs to the inode at that
  name".** `CatalogHold.swap` asserts that no `<slot>.wal` is present at every replace,
  forward or back.
- **AC-6 gains three rollback crash points:** after the reopened writer writes (the seam
  inserts one row), after the close, and after the restoring replace. Each boot is judged by the
  R5 GATE against the backup (row content hash), not by per-table counts: the corruption above
  keeps some counts plausible.
- **Mutation:** a restore without step 1 or 2 FAILS (the gate differs after the boot).

**Pattern match:** YES. Same class as bug-110 and bug-112: a file-level operation that is
correct for the main file and wrong for a sidecar or cache that DuckDB keys by path.

### BULLSHIT B-2: the Phase A deadline is a single-shot `con.interrupt()`, and DuckDB drops an interrupt that arrives between statements; the 5 s budget is not a bound {#b-2}

**Where:** 18.2 R11 "The deadline" (one timer that calls `interrupt()` if the body has not
called `h.end_interruptible()`), 18.3 R4 Phase A, AC-3, d9bt Q-D.

**Measured (`p1_interrupt.py`, duckdb 1.5.3):**

- `con.interrupt()` with no statement running, then a 10 s query: the query ran to completion
  (10.32 s).
- A timer that fires during 0.5 s of Python-side work between two statements: the next query
  also ran the full 10.32 s.
- An interrupt during a running `COPY FROM DATABASE` works (0.55 s).

**Why it is not a bound:** Phase A is mostly many statements with Python between them:

- `flush_fragments` is one UPSERT per dirty fragment in a Python loop (`store.py` `_flush_fragments_duckdb`);
- the R5 gate runs several legs per table, roughly 30 tables × count/hash/columns/constraints
  queries;
- the sentinel is a CREATE, an INSERT and a CHECKPOINT.

If the 5 s mark falls in any gap, the interrupt is lost and Phase A runs to its natural end. On
a loaded refmatrix that end is 3.6-3.9 s for the rewrite alone (I9), with no bound after it.
AC-3's seam is ONE 20 s statement, so it cannot see this. The AC passes while the production
bound fails.

**Fix:**

- The timer sets `h.deadline_hit = True` and then re-issues `con.interrupt()` every 50 ms until
  `end_interruptible()`.
- Every Phase A `CatalogHold` method calls `h.check_deadline()` (raise `DeadlineExceeded`)
  before each statement, including inside the gate's per-table loop and the fragment loop.
- **AC-3b:** `phase_a_seam` sleeps 1 s in Python between two short statements with
  `RMX_CATALOG_RECLAIM_BUDGET_S=0.5`. Outcome `failed:deadline`, `hold_s < 1.5`.
- **Mutation:** a single-shot timer FAILS AC-3b (the second statement runs, `hold_s ≥ 1`).
- Also see M-5: arm the deadline after step 2, so the snapshot-tick statements stay
  uninterruptible.

**Pattern match:** YES (`feedback_never_explain_away_a_failing_guard` /
`clean_corpus_hides_a_dead_gate`). The gate is proven only on the one input it was built for.

### BULLSHIT B-3: the growth band is not Table A; it flags A2 where 18.1 says A0, and once flagged a store never leaves it {#b-3}

**Where:** 18.2 R5 ("`file_bytes ≥ 2 × baseline` … is exactly Table A's A2 edge, `r ≥ 0.50`"),
d9bq, 18.3 R9, AC-16.

**From the 18.1 jsonl the spec cites** (`plan18-catalog-measure-20261015.jsonl`):

- **(a) No reclaimable floor.** Table A's A0 includes `reclaimable < 64 MiB`. Growth has no
  such leg.
  - cliquet: `file_bytes` 74,723,328 ≥ 2 × `rewrite_bytes` 31,207,424 = 62,414,848, so growth
    gives A2 on night one, but 18.1 banded it A0 (43.5 MB reclaimable).
  - The r2 jsonl (`…-20261015-r2.jsonl`) gives the same result: cliquet 74,723,328 against
    2 × 31,469,568 = 62,939,136, so growth A2, while its reclaimable is only 41.2 MiB.
  - Growth's first-night set is {refmatrix, global, cliquedb, cliquet}. 18.1's due set is
    {refmatrix, global, cliquedb, viascope}. It is four stores, but not the same four:
    viascope (A1, 132.8 MiB reclaimable) never flags, and cliquet (A0) always does.
  - Each night 18.3's step then sees A2 and runs an unarmed rehearsal (snapshot copy + 3
    child rewrites + gate). A hand confirm would refuse `refused:band_a0`, so the store can never
    be armed. The hot row never clears.
- **(b) The baseline is frozen.** It moves only by the 18.1 file, by a rehearsal when none
  exists, or by a reclaim ("Nothing else moves it").
  - Take a store that grows legitimately from 177 MiB to 354 MiB of live data. Its r is about
    0, but growth flags A2.
  - Every rehearsal measures the true live size and returns A0, yet R5 forbids it from
    re-seeding the baseline.
  - The result is a permanent false hot row and a nightly futile rehearsal.
  - "Exactly r ≥ 0.50" is true only at the instant the baseline is taken.

**Fix:**

- **R5:** A2 iff `file_bytes ≥ 2 × baseline` AND `file_bytes − baseline ≥ 64 MiB` (Table A's
  floor).
- **A rehearsal whose band is A0 re-seeds the baseline** with its median `rewrite_bytes`
  (`baseline_source: "rehearsal:<run_id>"`). It is a measured live size, the same kind of
  number R5 already accepts.
- **AC-16 adds the cliquet row → A0.**
- **A new AC:** a store at 2.1× baseline whose rehearsal returns A0 re-seeds, and the next
  night is A0 with no rehearsal.
- **Correct d9bq's "exactly" sentence** in the decision row.

**Pattern match:** YES. The r1 S-2 baseline defect, fixed for the big stores and wrong at the
small and the growing ends.

### BULLSHIT B-4: the lock-order mutation in 18.2 AC-17 and 18.3 AC-15 cannot fail {#b-4}

**Where:** 18.2 AC-17 ("the helper taking `_store_lock` before `_snapshot_lock` with
`snapshot=True` FAILS (a deadlock, caught by the 5 s bound)"), 18.3 AC-15, AC-17 / AC-14 lists.

**Why it cannot fail:**

- After R11, every `_snapshot_lock` user goes through the ONE helper. The only one at HEAD is
  `_snapshot_catalog`.
- Inverting the order inside the helper therefore inverts it for every caller. Consistent order
  means no deadlock.
- In 18.2 AC-17 the holder is `catalog_maintain`, which uses `snapshot=False` and never takes
  `_snapshot_lock` at all. The snapshot tick (inverted) just queues on `_store_lock`.
- In 18.3 AC-15 both the reclaim and the tick take store→snapshot under the mutation. That is
  still one order.
- Both tests pass under the mutation.

**What the inversion does change:** a `snapshot=True` caller holds `_store_lock` while it waits
for `_snapshot_lock`. The snapshot tick holds `_snapshot_lock` through its link swing and mirror
refresh, about 100-300 ms, more on an 800 MB mirror. So every writer stalls behind that wait.

**Fix (an observable that fails):** a competitor holds ONLY `_snapshot_lock` on an event. A
`snapshot=True` hold with `lock_wait_s=1` returns `skipped:lock_busy`. During that second a
write op (`upsert_entity`) completes, and the 23.2 recorder shows no `_store_lock` acquisition
by the helper. Under the mutation the write op blocks for the full second, and the recorder
shows the helper holding `_store_lock`. Alternatively, wrap both locks in a recorder that logs
the per-thread acquisition order and assert snapshot→store.

### BULLSHIT B-5: "goes to the helix plan" is an unanchored deferral (rule 9a), the same shape as r1 B-2 {#b-5}

**Where:** 18.3 R11 ("The store gets a bug-registry row … and goes to the helix plan, as Table
C's C2 does"), plan-18 `#thresholds`, d9bp (b).

**Evidence:**

- There is no helix plan file. `plan-11-helix-phase2-versioned-graph` is superseded.
- The helix plan's inheritance list in `plan-review-2026-10-14#t10-waves` names 22.4, 19.2's
  counts, 17.2's registry, plan-20's merge rule and the amendment. It does not name "catalog
  reclaim for a store over 5 s".
- No task spec covers it.
- r1 B-2 was "the offline route points at a route d9bf deletes". The remedy repointed the
  deferral at another target that has no line for it.

**Fix:** pick one.

- (a) Add "catalog reclaim for a store `rewrite_too_slow` under 18.3 R11" to the `#t10-waves`
  helix inheritance list (a one-line edit to the decision-log deliverable).
- (b) State the terminal state honestly: "the store stays unreclaimed with a hot row and a
  bug-registry row; the user decides" and delete "goes to the helix plan".

Zero stores are in this state today, so (b) costs nothing.

### SKETCHY S-1: the "one helper" AST can be bypassed by moving the hold out of `daemon.py`, and the site census misses daemon-reached CHECKPOINTs {#s-1}

**Where:** 18.2 AC-17, 18.3 AC-14, I1 ("six times").

**The AST is too narrow.** It checks named functions in `daemon.py` for `_store_lock`,
`_snapshot_lock` and the `"CHECKPOINT"` literal. Two bypasses pass it:

- `_op_catalog_maintain` calling `catalog_maint.run(d)`, which does `with d._store_lock:` (the
  new module is where the code lives);
- a CHECKPOINT kept in a `Store` method.

**The census misses daemon-reached CHECKPOINTs that hold the lock:**

- `store.py:3899`: the entities rebuild, reached under the daemon's hold by `_run_pending_repair`
  at boot and by the repair op;
- `replica_merge.py:391`;
- `cli.py:3785`: an offline verb-alias merge, outside the daemon like `rmx compact`.

None of these is timed, but 18.2 `#why` says the helper "times every CHECKPOINT that holds
`_store_lock`".

**Fix:**

- Run the AST over `daemon.py` AND `catalog_maint.py`.
- In `catalog_maint.py`, `_store_lock` / `_snapshot_lock` are referenced nowhere.
- In `daemon.py`, they are referenced in catalog code only inside `_catalog_hold`.
- The `"CHECKPOINT"` literal appears only in `CatalogHold.checkpoint` / `snapshot` /
  `rewrite_into` (and the child entry point).
- I1 lists the three extra sites, each either ported or named as an exemption with its reason.
- **Mutation:** a `with d._store_lock:` inside `catalog_maint.py` FAILS.

This is the r8 impression `imp-static-rule-walks-helpers`, recurring.

### SKETCHY S-2: 23.5's obligations are not in 18.2, and the `after` semantics drop HEAD's `_snapshot_lock` ordering (concurs with ns23-r9-1) {#s-2}

ns23-r9-1 (the parallel r9 diff check of `b84fd8d`) already files the missing pieces in 18.2
R11:

- `Daemon._inflight(label)` registration;
- the `pin_to` / L0 snapshot contract;
- a second 2 s alarm line;
- the compaction-ownership loop. 18.3 R8 says "Not ported … 23.1 owns it", Q-C says "a 23.1 or
  23.5 amendment, not here", and 23.5 R5 says "18.2/18.3's port list gains" it.

Reproduced and agreed.

**One addition:** at HEAD the read-only link swing and the mirror refresh run AFTER
`_store_lock` is released but INSIDE `_snapshot_lock` (`daemon.py:2692-2738`). 23.5's `pin_to`
link must also land before `_snapshot_lock` releases. R11 only says "`after` callbacks run after
the release", so an implementation that releases both locks first passes every 18.2 AC and
breaks 23.5 R5.

**Fix:**

- R11 gets two phases: `after_locked` (with `snapshot=True`: after `_store_lock` release, before
  `_snapshot_lock` release) and `after` (both released).
- The snapshot port puts the link swing, the mirror refresh and `pin_to` in `after_locked`.
- AC-12 asserts that `_snapshot_lock` is held during the mirror refresh.
- Close Q-C as ns23-r9-1 proposes: 18.3 owns the hold-2 port.

### SKETCHY S-3: three writer-reopen and writer-lost exits for one condition; 18.3's named exit is a no-op for its cause, and AC-14 contradicts the merge reopens {#s-3}

**Where:** 18.3 R6 ("exits through the fast-exit path (`os._exit(2)`, I6)"), R8, AC-14.

**Three mechanisms:**

- 23.1 R1.6: `_install_writer_store`.
- The bug-113 fix: `_reopen_writer_after_merge` + `_writer_lost`. It assigns `d.store = st`
  directly, sets shutdown, sleeps `RMX_DEGRADE_EXIT_S` = 2 s with the lock released, then calls
  `os._exit(2)`.
- 18.3: `CatalogHold.reopen_writer` + "the fast-exit path".

**The named exit does not fire:** `_fast_exit_if_invalidated` (`daemon.py:1443`) RETURNS
unless `_is_fatal_invalidation(exc)`. A failed link or a failed identity check is not a DuckDB
invalidation, so it does not exit. Where it does fire, it queues an entities rebuild
(`_mark_repair_needed`) for the respawn.

**AC-14 contradicts R8:** "`_install_writer_store` is called only from
`CatalogHold.reopen_writer` and boot's first open". `_op_replica_merge`'s three reopens are
exempt in R8 only for CHECKPOINT and copy.

**Fix:**

- One `Daemon._exit_for_respawn(where, detail)`: log, write the state, and `os._exit(2)`
  immediately while STILL holding `_store_lock`, so no queued op runs on a closed writer, and
  with no repair marker. 18.3 R6 and bug-113's `_writer_lost` both call it.
- `_reopen_writer_after_merge` delegates to `CatalogHold.reopen_writer`, or AC-14 names
  `_op_replica_merge` as the one exemption.
- Raise this on the bug-112/113 branch before it merges, so the convergence lands once.

### SKETCHY S-4: `hold_over` clearing contradicts the refusal it shares a key with {#s-4}

**The contradiction:**

- R7 (c): a hold over 10 s writes `reclaim_disabled` (cause `hold_over`). "Only a hand run whose
  `hold_s ≤ 10` clears it."
- R3 (g): EVERY real run, hand included, refuses `refused:reclaim_disabled` until
  `--clear-disabled <run_id>`.
- AC-8's last case agrees with R3 (g). AC-9 ("A hand run with no seam clears it") cannot pass
  with R3 (g).

**Fix:**

- `hold_over` gets its own key, `reclaim_hold_over`. It blocks hub runs only, and a hand run
  with `hold_s ≤ 10` clears it, as 18.2 D2 does for its own flag.
- `reclaim_disabled` stays for failed rollbacks and write-through failures, cleared only by
  `--clear-disabled`.
- AC-9 and AC-8 name the keys.

Related, under the same fix: R11's `rewrite_too_slow` has no `run_id` for `--clear-disabled` to
name, and R14's verdict never reaches the live store's `catalog_state.json`. A too-slow R14
verdict is enforced only by R12's procedure. Either `--clear-disabled` takes the mark's key, or
R3 (b) reads the latest R14 report for the root.

### SKETCHY S-5: two ops read-modify-write `catalog_state.json`, which holds safety latches, with no shared lock {#s-5}

**The writers:**

- 18.2 writes band, reasons and `checkpoint_disabled` on every run.
- 18.3 writes the baseline (rehearsal and reclaim), `reclaim_disabled` (after the release and in
  the failed-rollback path) and `rewrite_too_slow`.

**The race:** each op is single-flight on its own, but a hand run on one op and a hub run on
the other can overlap, and 18.3's after-release callbacks run outside every hold. Two atomic
tmp + rename writes from stale reads lose a key. A lost `reclaim_disabled` re-enables a reclaim
on a store whose write-through check failed.

**Fix:**

- One `catalog_maint.update_state(root, mutate)` under a process-wide `threading.Lock`: read,
  mutate, write tmp with a unique name, fsync, rename, fsync the directory. Both ops use it.
- **AC:** a `catalog_maintain` write and a `reclaim_disabled` write interleaved by seams keep
  both keys.

### SKETCHY S-6: crash residue is never cleaned; a leftover sentinel table makes every later reclaim fail {#s-6}

**What is left behind:**

- **A sentinel in the live slot.** A SIGKILL after step 9's replace and before step 11's
  `DROP TABLE _rmx_reclaim_sentinel` (AC-6's "after the replace" and "after the reopen" points)
  boots with the sentinel table in the live catalog. The next reclaim's `COPY FROM DATABASE`
  copies it, and step 5's `CREATE TABLE rc._rmx_reclaim_sentinel` then fails "already exists"
  on every run. That is a permanent Phase A failure, outside both `failed:gate` and
  `failed:deadline`.
- **Orphan files in the root.** A crash in Phase A or in the rollback leaves
  `catalog.<S>.reclaim-<run_id>.duckdb` or `<slot>.rollback`. Both match `store_bytes`'s
  `catalog*.duckdb` glob (`daemon.py:3864`) and `discovery.footprint`'s.
- **AC-6 cannot see either.** It asserts "counts equal the pre counts" over the pre table set.

**Fix:**

- R3 gains a residue sweep before any hold:
  - a leftover sentinel is dropped through the writer, under the hold, with a log line;
  - orphan `reclaim-*` / `.rollback` files are moved to `backups/` with a log line (never
    deleted).
- AC-6 asserts table-set equality with the backup (the R5 gate) after each boot, then a second
  reclaim succeeds.

### SKETCHY S-7: a closed writer `Store` reopens itself lazily; a reference captured before the lock writes through a zombie {#s-7}

**The mechanism:**

- `Store._connect()` reconnects whenever `_conn is None` (`store.py:1232`), and `close()` sets
  `_conn = None`.
- The flush tick evaluates `_periodic_flush(self.store, self._store_lock, …)`
  (`daemon.py:2136`) BEFORE it acquires the lock. Any op that captures `st = d._st()` outside
  `_store_lock` does the same.
- So after a swap, the old `Store` object is still referenced, and its next `_connect()` opens
  the slot path again. With the bug-112 fix that returns the new writer's cached instance, so
  nothing is lost. But a second `Store` with stale caches (partition binding, fragment cache:
  bug-098 and bug-105's classes) now writes into the live file.

**Fix:** `close_writer()` marks the old Store terminally closed. `_connect` raises
`StoreClosed` on a closed writer instead of reconnecting. An AC calls a method on the
pre-swap Store object after a reclaim and expects the raise.

### SKETCHY S-8: R14's loaded measurement cannot run as written in the sandbox {#s-8}

**Where:** 18.3 R14, AC-19, d9bt Q-D.

**Why:**

- **`context` needs model workers.** A tmp daemon that may not touch live sockets cannot use
  the hub's `models.sock`. Private workers change the CPU load that "loaded" is meant to
  reproduce.
- **The production 5 s Phase A deadline truncates the measurement.** A store whose loaded
  Phase A is 6 s reports a `failed:deadline` run with `hold_s` ≈ 5, not its loaded number.
- **"readers" is a configuration value, not a measured load.** AC-19's
  `readers count is 0` mutation is killed by a constant.
- **A tmp root with only `catalog.A.duckdb`** goes through the asymmetric bootstrap, which
  copies A to B (another 800 MB).

**Fix:**

- The reader mix is `stats` + `query` + a model-free read (or `context` with dense disabled,
  stated).
- R14 runs with `RMX_CATALOG_RECLAIM_BUDGET_S` raised (for example 60) and reports
  `phase_a_s` raw. The verdict compares it with 5 s.
- Each row records reader calls COMPLETED during `[acquire, release]` from the client side, and
  refuses a row where any loop completed zero.
- The tmp root gets both slots and `active`.

### MEH M-1: 18.2's facts cite stale lines and a false "src unchanged" {#m-1}

The header says "Facts at HEAD `55f043d` (`src/` unchanged through `0611d2f`)". daemon.py
changed through bug-115/116 (`607d759`, `1c86d9c`).

| fact | spec line | HEAD line |
|---|---|---|
| `_FairLock` | 242 | 247 |
| `_start_heartbeat` | 1305 | 1323 |
| `_factslog_threshold` | 2267 | 2301 |
| `_FACTSLOG_MIN_RECLAIM` | 2302 | 2336 |
| compact tick | 2380 | 2428 |
| `_op_stats` | 3731 | 3816 |
| `_op_checkpoint` | 3871 | 3956 |

Re-cite at `23ad703`, as 18.3 does.

### MEH M-2: the `st_ino` identity leg is vacuous for I4 {#m-2}

It stats the PATH, which `os.replace` just set. A cached old database passes it. Only the
sentinel and `total_blocks` detect I4. Say so in R4 step 11, so nobody drops one of those two
believing the inode check backs it up.

### MEH M-3: AC-18 (a) contradicts itself {#m-3}

It says both "with no refmatrix code" and "with bug-112's fix in the code path". Plain
`duckdb.connect` always loses the row on 1.5.3. The fix (`backend.open_duckdb`) closes only
REGISTERED holders. AC-18 (a) must open both connections through `open_duckdb`, and must FAIL
with `duckdb.connect` substituted.

### MEH M-4: Phase A's scope differs from d9bt {#m-4}

d9bt Q-D says Phase A is "rewrite + gate". 18.3 R4 makes `flush_fragments` + CHECKPOINT
interruptible too. Those are the snapshot tick's own, normally short, statements. Arm the
deadline after step 2, and align d9bt's wording.

### MEH M-5: two AC fixtures under-specify what they assert {#m-5}

- **18.3 AC-1** ("an entity written after the run is seen by a fresh child opening a copy of the
  slot"): the write sits in the WAL until a CHECKPOINT. Force a `snapshot` op first, or copy the
  `.wal` too.
- **18.2 AC-1**'s wait-included mutation needs a competitor holding the lock for 0.5 s. The AC's
  fixture has none, so add the variant.

### MEH M-6: AC-10's `lsof` assertion races in-flight readers {#m-6}

With bug-112's fix, a read-only open is a private ATTACH that "keeps its own (old) snapshot
until it closes". An in-flight `open_read_store` reader may legitimately hold the replaced
snapshot inode at the instant of the check. Wait for `_read_inflight == 0` (or the swap gate)
before the `lsof`.

### MEH M-7: 18.2 AC-17's "each calls `_catalog_hold` once" conflicts with AC-5's routine/seam split {#m-7}

The routine with the `checkpoint` seam, not the op, holds the call. Assert "exactly one
`_catalog_hold` call reachable from each op" (the S-1 walk).

### MEH M-8: the hand rollout's "announced to the user first" is not enforced {#m-8}

That is acceptable under d8g ("the gate is the record, not the surface"), and an MCP agent can
rehearse, confirm and arm. Say it explicitly in R12, so the R12 procedure is not read as a
control.

## Answers to the brief's questions {#answers}

1. **The helper.** It covers the six I1 sites at HEAD. It misses three daemon-reached
   CHECKPOINTs (S-1). The AST can be bypassed by moving code out of `daemon.py` (S-1). The lock
   order matches the snapshot tick, but the AC cannot catch an inversion (B-4). It conflicts with
   23.5 on `pin_to`, `_inflight`, the alarm and compaction ownership (S-2, with ns23-r9-1). It
   coexists with 23.1 R1.6, but bug-113's fix adds a second reopen and a second exit (S-3).
2. **18.3 phases A/B/C.**
   - Forward crash safety holds.
   - The rollback is unsafe through a foreign WAL (B-1, measured corruption).
   - The sentinel plus `total_blocks` do prove that the reopen got the new file (verified);
     `st_ino` adds nothing there (M-2).
   - The failed-rollback exit names a path that does not exit (S-3).
   - Crash residue is never cleaned (S-6).
   - Frozen slots, legacy, `facts.log` and offsets are untouched (verified).
3. **R14 and Q-D.** Not measurable as written (S-8). The deadline itself is not a bound (B-2).
   On Q-D, keep the recommendation (Phase A only, 10 s whole hold) once B-2 and M-4 are fixed.
4. **Growth, reason and arm.** No path rewrites a live writer without the arm and a reason. But
   the reason is wrong for cliquet and for any growing store (B-3), which makes a permanent
   false hot row plus a nightly rehearsal.
5. **Mutations.** Those that cannot fail: lock order (B-4) and the one-statement deadline seam
   (B-2). Those that hit a contradiction: AC-9 against R3 (g) (S-4). Those killable by a
   constant: AC-19's readers (S-8).

## Verdict {#verdict}

**21 findings (5 BULLSHIT, 8 SKETCHY, 8 MEH).**

- **18.2: NEEDS-REVISION.** B-3, B-4, S-1, S-2, S-5, M-1, M-5, M-7.
- **18.3: NEEDS-REVISION.** B-1, B-2, B-4, B-5, S-3, S-4, S-5, S-6, S-7, S-8, M-2, M-3, M-4,
  M-5, M-6, M-8.
- **Plan-18 body:** correct d9bq's "exactly r ≥ 0.50" (B-3) and close Q-C with an owner (S-2).

B-1 and B-2 are measured defects in the safety mechanisms that d9bp made the price of the
in-daemon design. Neither is a reason to drop that design: both fixes are a few lines of
specification each.
