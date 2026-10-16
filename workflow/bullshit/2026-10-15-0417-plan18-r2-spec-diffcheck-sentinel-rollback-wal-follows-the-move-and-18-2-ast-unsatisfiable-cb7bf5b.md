---
gmd: "0.1"
id: bsd-plan18-r2-spec-diffcheck-cb7bf5b
title: "ch-bsd plan-18 r2 diff check (18.2 + 18.3 at cb7bf5b): the r1 mechanisms hold when re-probed, but a sentinel rollback serves through a WAL that moved to backups/, 18.2's AST cannot pass at 18.2 and cannot see store.py, and the single-shot-interrupt and single-step rollback mutations cannot fail"
tags: [ch-bsd, plan-18, task-18.2, task-18.3, spec-review, diff-check, duckdb, wal, rollback, deadline, ast]
severity: BULLSHIT
plan: plan-18-duckdb-store-maintenance
task: task-18.2-catalog-maintain-step + task-18.3-offline-reclaim
round: 2
---

# ch-bsd plan-18 r2: diff check of `b84fd8d..cb7bf5b` {#root}

**Spec commit:** `cb7bf5b` on `wave0-spec-reviews`. HEAD was `e8672d6` during the run. Only
the plan-23 files changed after `cb7bf5b`, and those were read for 23.5 `#cross-plan-18` and
23.1 R1.6 only.
**Compared against:** the r1 report [[bsd-plan18-r1-spec-review-b84fd8d]], and decisions d9bw
and d9by (plus d9bp-d9bv) in [[plan-review-2026-10-14]].
**Bug branch:** `/Volumes/littlebig/refmatrix-bugs112-118`, read-only. It is at `462bd0b`, with
an uncommitted diff to `daemon.py`, `backend.py`, `replica_merge.py` and others, so it may still
change.
**Probes:** run with duckdb 1.5.3 (`~/refmatrix/.venv/bin/python -I -u`) on synthetic scratch
files under `/private/tmp/claude-501/p18r2/`. The scripts are `q1_rollback_order.py`,
`q2_sentinel_case.py` / `q2b.py` / `q2c.py` and `q3_deadline.py`, and each has a `.log`. No live
store was opened and no socket was touched.

rel: derives-from -> [[bsd-plan18-r1-spec-review-b84fd8d]]
rel: contradicts -> [[task-18.3-offline-reclaim#r6-rollback]]
rel: contradicts -> [[task-18.3-offline-reclaim#ac-3]]
rel: contradicts -> [[task-18.2-catalog-maintain-step#ac-17]]
rel: related-to -> [[task-23.5-read-path-and-holder-bounds#cross-plan-18]]
rel: related-to -> [[task-23.1-queue-and-drain#r1-6-proposed]]

## r1 closures verified {#closures}

- **B-1 is closed at the mechanism** (`q1`). This is the r1 case: a reopened new-file writer
  writes, and there is a SIGKILL-equivalent at the restoring replace. With R6 B's order (close,
  then move a non-empty `.wal`, then restore) the boot equals the old file: 50,000 rows,
  `min(i)` 150,000, the same content hash. The step-1 close removes the 361-byte WAL. With both
  steps removed, the boot is corrupted: 52,048 rows, `min(i)` 122,890. A new hole in the
  sentinel case is filed as [[#n-b1]], and the mutations are filed as [[#n-s1]].
- **B-2 is closed at the mechanism** (`q3`). With a budget of 0.5 s, a flag, a 50 ms
  re-interrupt and a per-statement check, AC-3b's sequence (short statement, 1 s Python gap,
  short, 20 s) ends `Deadline` before s2 at 1.01 s, and s2 never runs. A deadline that passes
  between the check and the statement's start is interrupted at 0.62 s. One of the
  pre-registered mutations cannot fail ([[#n-b3]]), and the cleanup path is open ([[#n-s2]]).
- **B-3 is closed.**
  - 18.2 R5 has the 64 MiB floor and the A0 re-seed. 18.3 R2, R7 (b), R9 and AC-11 (f) carry
    them.
  - The numbers check out:
    - cliquet: 74,723,328 − 31,207,424 = 43.5 MB, under 64 MiB, so A0. The r2 line gives
      43.3 MB, also A0.
    - refmatrix: 827,338,752 ≥ 2 × 185,348,096, and the difference is far above 64 MiB, so A2.
  - The plan's tasks row and `#why` drop "exactly". d9bq is annotated in place.
- **B-4 is closed.**
  - 18.2 R11 says a `_snapshot_lock` timeout returns before `_store_lock` is touched.
  - AC-17 and 18.3 AC-15 put a competitor on `_snapshot_lock` ONLY.
  - Under the inversion, the helper holds `_store_lock` while it waits, and the write op blocks
    for the second. The mutation can fail.
- **B-5 is closed.** 18.3 R11 states the terminal state honestly. The plan's Table C note
  annotates the pre-registered C2 wording. No live pointer to a helix plan is left.
- **S-2 is closed, apart from one carry-over.** 23.5 `#cross-plan-18` items 1-5 are all in the
  text:
  - `_inflight(label)` and the innermost-entry naming (18.2 R11);
  - a per-label threshold on the ONE `lock hold:` alarm (R11, R4 D1);
  - `pin_to` / `L0` inside the body, with the link in `after_locked` (R8, AC-12);
  - the flush before CHECKPOINT (R8, AC-12);
  - the compaction hold 2 ported by 18.3 R8, with Q-C closed.

  The flush-order AST hand-off is the one item not carried ([[#n-m3]]).
- **S-3:** the names converged with the branch, but the signatures did not ([[#n-s3]]).
- **S-4:** the keys are separated (`reclaim_hold_over` / `reclaim_disabled`), and each mark has
  a `run_id`. The AC fixtures cannot reach the clear ([[#n-s4]]).
- **S-5:** `update_state` is the only writer named. Every 18.3 write cites it (R2, R4 before
  and after, R6, R11). The enforcement is weak ([[#n-m2]]).
- **S-6, S-7 and S-8 are closed.**
  - S-6: R3 (h) sweep and AC-22.
  - S-7: `Store.retire`, `StoreClosed` and AC-20.
  - S-8: R14 has both slots, a model-free mix, per-loop completions, a 60 s budget, and the two
    d9by(b) edges. AC-19 carries them.
- **M-1 through M-8 are closed** at the quoted text.

## Findings {#findings}

### BULLSHIT N-B1: after `rolled_back:sentinel`, the daemon serves through the cached instance whose WAL handle followed the moved `.wal` into `backups/`; a crash before the next CHECKPOINT loses every write since the rollback {#n-b1}

**Where:** 18.3 R6 B steps 2 and 4, and AC-4 (b).

**What the spec does:** step 2 moves a non-empty `<slot>.wal` to `backups/` "BEFORE the
restore". In the sentinel case (AC-4 b, an unregistered holder keeps the OLD database cached),
the step-1 close does not shut the instance, so the WAL survives the close and step 2 moves it.

**Measured** (`q2b`; step-10's write is an insert + delete):

| point | `slot.wal` | moved file |
|---|---|---|
| after the reopen's write | 238 | — |
| after the step-1 close | 238 | — |
| after the step-2 move | none | 238 |
| after a post-rollback insert, no CHECKPOINT | **none** | **369** |

The boot after `os._exit` has count 50,000 and **0** copies of the post-rollback row. The
cached instance holds the WAL file open, so its commits after the rollback land in
`backups/…duckdb.wal`. Every AC-4 (b) assertion still passes:

- the inode is the original;
- the counts equal the pre counts;
- "a write succeeds";
- "the slot has no `.wal` after the run".

**The forward direction in the same scenario.** After the step-10 reopen (the cached OLD
instance), the 238-byte WAL of the OLD database sits at `<slot>.wal` beside the NEW inode. A
SIGKILL before R6 B step 1 replays it into the new file. This is r1 B-1 in reverse, and no AC-6
point covers it.

**Measured fix leg** (`q2c`): a `CHECKPOINT` right after the rollback reopen makes the next WAL
appear at `<slot>.wal` (139 bytes). The boot then has the post-rollback row (count 50,001).

**Fix:**

- **R6 B step 4:** `h.reopen_writer(slot)`, then `h.checkpoint()` BEFORE the identity check and
  before the hold releases. The text says why: a cached instance keeps its WAL handle across
  the step-2 move, and a CHECKPOINT re-creates the WAL at the slot path.
- **Read back before the first write.** The step-11 sentinel and `total_blocks` read-back runs
  BEFORE `Store.init()`'s first write. `_reopen_writer` takes a `verify(con)` callback that it
  runs between `open_duckdb` and `init()`. A cached old database is then refused before it
  writes a WAL beside the new inode.
- **AC-4 (b) gains a check:** after `rolled_back:sentinel`, a write op, then SIGKILL, then a
  fresh boot that sees the write's row.
  - **Mutation:** no CHECKPOINT after the rollback reopen FAILS (the row is lost; measured).
  - **Mutation:** the read-back after `init()` FAILS a new AC-6 forward point, "AC-4 (b)'s
    holder + SIGKILL after the reopen". The gate then differs.

**Pattern match:** YES. This is the r1 B-1 / bug-112 class: a file-level move that is right by
name and wrong for a handle DuckDB already holds.

### BULLSHIT N-B2: 18.2's bypass rule cannot pass at 18.2 and cannot see `store.py`, so its own named mutation cannot fail {#n-b2}

**Where:** 18.2 R11 "The bypass rule", and AC-17 and its mutation list.

**The rule cannot pass at 18.2.** It walks `daemon.py` and `catalog_maint.py` only, and allows
the `"CHECKPOINT"` literal only in the `CatalogHold` methods "plus the named exemptions of 18.3
I1". At 18.2 GREEN, `daemon.py` still carries the literal in two functions:

- the init rebind (`:1762`);
- `_bootstrap_rotation_if_needed` (`:2924`, `:2960`).

18.2 R11 "Not here" leaves both for 18.3 R8. They are ported in 18.3, not exempted in 18.3 I1.
So 18.2's AC-17 is red on 18.2's own correct code. The likely "fix" at build time is to weaken
the walk.

**The named mutation cannot fail.** "A raw `.execute("CHECKPOINT")` in a `Store` method called
from the body FAILS (AST)" cannot fail, because `store.py` is not walked at 18.2.

**18.3's walk is a fixed list of files.** AC-14 walks `daemon.py`, `catalog_maint.py`,
`store.py` and `cli.py`. It names `replica_merge.merge_slots` as an exemption in a file it does
not walk. A lock or a CHECKPOINT moved into any other module (`backend.py`, `migrate.py`, a new
`catalog_swap.py`) passes it. That is r1 S-1's shape, one module over.

**Fix:**

- Both walks cover every `src/refmatrix/*.py`. Exemptions are by qualified function name.
- 18.2 adds STAGED exemptions, each marked "pending 18.3 R8 / R10":
  - the init rebind function;
  - `_bootstrap_rotation_if_needed`;
  - `cli.compact`.

  The permanent ones are `Store.rebuild_entities_indexes`, `cli.merge_verb_aliases`,
  `_op_replica_merge` and `replica_merge.merge_slots`.
- 18.3 AC-14 asserts the staged list is EMPTY.
- 18.2's `store.py` mutation then fails as written.

**Pattern match:** YES. `imp-static-rule-walks-helpers` and r1 B-4/S-1. This is the third round
in which a bypass check or a mutation was pre-registered without being run against the code it
must reject.

### BULLSHIT N-B3: the "single-shot `interrupt()`" mutation SURVIVES AC-3b; the re-interrupt is load-bearing only in a window AC-3b never opens {#n-b3}

**Where:** 18.3 AC-3b, and the AC-17 list ("a single-shot interrupt … → AC-3b").

**Measured** (`q3`, budget 0.5 s, AC-3b's sequence):

| design | outcome | hold | statements run |
|---|---|---|---|
| spec | Deadline before s2 | 1.01 s | s1 |
| single-shot timer, flag + check kept | Deadline before s2 | 1.01 s | s1 |

The two rows are identical. The flag the single shot sets is enough for the check before s2.
The re-interrupt matters only when the deadline passes AFTER `check_deadline()` and BEFORE
DuckDB starts the statement. On that race (`race` rows):

- the spec ends with `InterruptException` at 0.62 s;
- the single shot runs the full 11.62 s.

**Fix:**

- Add **AC-3d**. `_exec` takes a `pre_exec_seam` that runs after the check. The seam sleeps
  0.6 s with the budget at 0.5 s, and a long statement follows. Outcome `failed:deadline` with
  `phase_a_s < 1.0`.
- Point the single-shot mutation at AC-3d, not AC-3b. AC-3b keeps the "no check" mutation:
  measured, s2 runs.

**Pattern match:** YES. r1 B-4: a mutation that cannot fail.

### SKETCHY N-S1: AC-6's rollback mutations "without step 1 OR step 2" each survive; only removing both corrupts {#n-s1}

**Where:** 18.3 AC-6 mutations and AC-17.

**Measured** (`q1`, at the restoring-replace crash point):

| mutation | boot |
|---|---|
| no step 1 | equals old |
| no step 2 | equals old |
| neither | 52,048 rows (corrupt) |

- **Step 1 or step 2 alone is enough here.** Either one clears the slot's WAL.
- **"The assertion removed together with step 2"** also survives, because step 1 already
  closed the WAL.
- **Step 2 matters only when the close cannot shut the instance** ([[#n-b1]]'s AC-4 b case).
- **Step 1 is caught by nothing listed.**

**Fix (re-register the mutations):**

- Steps 1 and 2 and the swap assertion all removed → AC-6 FAILS (gate differs; measured).
- Steps 1 and 2 removed, assertion kept → AC-6 FAILS (the assertion fires, the run exits 2 and
  writes `reclaim_disabled`, and the second reclaim is refused).
- Step 2 alone removed → AC-4 (b) FAILS (the assertion fires on the WAL the cached instance
  left, measured at 238 bytes; the outcome is an exit instead of `rolled_back:sentinel`).
- Step 1 alone removed → a new AC-4 (a) leg FAILS. After `rolled_back:reopen`, the reopened
  new-file `Store` raises `StoreClosed`, and `lsof` shows no descriptor on the
  `reclaim-failed` inode.

### SKETCHY N-S2: the deadline flag outlives Phase A and the re-interrupt can hit R6 A's cleanup, which can leave `rc` attached {#n-s2}

**Where:** 18.3 R4 "How the deadline bounds Phase A", and R6 A.

**What the spec says:**

- `_exec` raises `DeadlineExceeded` whenever `h.deadline_hit` is set.
- Every `CatalogHold` statement goes through `_exec` (18.2 R11).
- R6 A's `DETACH` "runs in a `finally`".

**Two failure modes:**

- If that `finally` runs after the block exits, the persisting flag makes the cleanup `DETACH`
  raise.
- If it runs inside the block, the 50 ms re-interrupts can abort it.

Either way the writer keeps `rc` attached to a file R6 A then deletes. The next reclaim's
`ATTACH … AS rc` fails, so the store fails every run until a restart. AC-3's "the daemon then
serves a write" cannot see this.

**Fix:**

- `check_deadline()` is active only inside `interruptible`, and the flag is reset on exit.
- R6 A's `DETACH` and partial-file removal run AFTER the block has stopped and joined its timer.
- AC-3 asserts that after `failed:deadline`, `duckdb_databases()` on the writer has no `rc`, and
  that an immediate second rehearsal + confirm reaches its `ATTACH`.
- **Mutation:** the cleanup inside the block, or the flag not reset, FAILS.

### SKETCHY N-S3: THE reopen and THE writer-lost exit match the branch by name only; three installer signatures exist {#n-s3}

**Where:** 18.3 R8 "THE reopen" / "THE writer-lost exit", I6, and AC-14. Compared with the
branch `daemon.py:1446-1487`, `:5554`, and 23.1 R1.6.

**The three contracts:**

| | 18.3 R8 | bug branch | 23.1 R1.6 |
|---|---|---|---|
| reopen | `_reopen_writer(path: Path, *, where) -> Store` | `_reopen_writer(slot: str \| None = None) -> None` | — |
| reopen order | install, then `init()`, then connect | `init()` + connect, then install; `_force_close_store` on failure | construct, install, then `init()` |
| lock assert | `held_by_current_thread()` | `.locked()` | — |
| installer | `_install_writer_store(st)` | `_install_writer_store(st, slot)`: also sets `_active_slot` and refreshes the read-only link | `_install_writer_store(st) -> Store`: sets `writer_lock` |
| exit | `_writer_lost(where, exc) -> NoReturn` | `_writer_lost(reason: str)`; immediate, already | — |

**Consequences:**

- **18.3's install-before-init order** would leave `d.store` a half-open Store on an `init()`
  failure. The branch's order is right.
- **A slot-letter `_reopen_writer` cannot open the legacy `catalog.duckdb`**, which R8 says the
  init rebind's fallback keeps.
- **The branch's installer refreshes the read-only link** inside the Phase B hold. 18.2 R8 puts
  the link swing in `after_locked`.
- **I6 still describes the branch's old 2 s timer.**

**Fix:**

- 18.3 R8 cites the branch's names, signatures and order as merged.
- It states how the legacy fallback opens: either an added `path=` keyword, or the fallback
  named as the one remaining `Store(` site with its reason.
- It states that the installer's link refresh inside the hold is accepted, or moves it to
  `after_locked`.
- It raises the 23.1 R1.6 installer reconciliation (`writer_lock` + `slot`) on the plan-23
  thread.
- I6 is updated.
- The AC-14 exit rule becomes "no `os._exit(<non-literal-0>)` outside `_writer_lost` and
  `_fast_exit_if_invalidated`". The branch writes `os._exit(self.WRITER_LOST_EXIT_CODE)`, which
  a literal-`2` match misses.

### SKETCHY N-S4: the "second run" fixtures are A0 after a successful swap, and R3 has no check order {#n-s4}

**Where:** 18.3 AC-6, AC-9 and AC-5, and R3.

**The second run is refused before any hold:**

- **AC-6.** At the forward points from the replace on, the boot has the reclaimed file. "Then a
  second real reclaim on the same root succeeds" cannot hold: the rehearsal is A0, so R3 (b)
  refuses `refused:band_a0` before any hold.
- **AC-9.** The `hold_over` run succeeded, so the store is A0, and the "hand run with no seam"
  that should clear `reclaim_hold_over` is refused the same way.

**AC-5 depends on an order R3 never states.** AC-5 expects `refused:reclaim_disabled` on a slot
that may be A0, which needs (g) checked before (b).

**Fix:**

- R3 states the evaluation order: (h) sweep, (g) disabled, then (a)-(f).
- AC-6 and AC-9 re-bloat the fixture (insert and delete 90 %, then a CHECKPOINT) before the
  second run, so that run reaches step 5. That is what S-6's sentinel check needs.

### MEH N-M1: R3 (h) never clears `reclaim_inflight` after the sentinel drop {#n-m1}

AC-22 asserts that `reclaim_inflight` is cleared, but R3 (h) never says so. Without the clear,
every later call re-takes the residue hold. Add "then `update_state` clears
`reclaim_inflight`".

### MEH N-M2: `update_state`'s ownership check is attributed to AC-17 but absent there, and a path match is defeatable {#n-m2}

18.2 R13 says "An AST check (AC-17) finds no other writer", but AC-17 lists no such check. A
rule that matches "onto a `catalog_state.json` path" misses `p = state_path(root);
p.write_text(…)`.

**Fix:** the literal `"catalog_state.json"` appears once, as a `catalog_maint` constant, and
that constant is referenced only in `update_state` / `read_state`. Put the check in AC-17, and
add the mutation "a second writer FAILS".

### MEH N-M3: 23.5 item 4's flush-order AST hand-off is not carried {#n-m3}

23.5 `#cross-plan-18` item 4 says "23.5 R7's flush-order AST assertion moves to that body with
the port". 18.2 has only the behavioural AC-12 leg. After the port, an AST test that walks
`_snapshot_catalog` either fails or is deleted.

**Fix:** 18.2 R8 says the assertion moves to `CatalogHold.snapshot`, and AC-12 lists it.

## Answers to the brief {#answers}

- **Every r1 finding at the quoted text:** closed. The exceptions are the new holes and the
  mutation defects above: N-B1 inside B-1's fix, N-B2 inside S-1's, N-B3 inside B-2's, and
  N-S1 inside B-1's AC-6.
- **The probes re-run:**
  - Moving `<slot>.wal` (with the close) does prevent the foreign replay.
  - The flag + 50 ms re-interrupt + per-statement check does bound Phase A with gaps: 1.01 s
    with s2 never run, and 0.62 s in the race.
- **23.5 `#cross-plan-18`:** items 1-5 are carried. The AST hand-off in item 4 is not
  (N-M3).
- **`_reopen_writer` / `_writer_lost` against the branch:** the names converged, and the branch
  already exits immediately with the lock held. The signatures, the order and the installer
  differ (N-S3).
- **The AST covers `catalog_maint.py`, `store.py` and `cli.py`:**
  - in 18.3, yes, and it can fail, but only within four named files;
  - in 18.2, no: `store.py` is not walked, and the rule is red at 18.2 GREEN (N-B2).
- **`update_state` is the only writer:** in the text, yes. The enforcement is misplaced and can
  be bypassed (N-M2).

## Verdict {#verdict}

**10 findings (3 BULLSHIT, 4 SKETCHY, 3 MEH).**

- **18.2: NEEDS-REVISION.** N-B2 and N-M2/N-M3. One small edit makes it approval-ready: walk
  all of `src/refmatrix`, with a staged exemption list.
- **18.3: NEEDS-REVISION.** N-B1, N-B2 (its walk), N-B3, N-S1 to N-S4, and N-M1. Each fix is
  a few lines of spec. N-B1's fix is measured (`q2c`).
- **Plan file:** clean.
