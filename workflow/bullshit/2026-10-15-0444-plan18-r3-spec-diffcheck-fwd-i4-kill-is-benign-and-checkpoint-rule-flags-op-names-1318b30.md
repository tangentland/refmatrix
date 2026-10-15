---
gmd: "0.1"
id: bsd-plan18-r3-spec-diffcheck-1318b30
title: "ch-bsd plan-18 r3 diff check (cb7bf5b..1318b30): every r2 finding closed at its text; two pre-registered checks still cannot behave as written — AC-6 fwd-I4's kill is a benign replay, and 18.2's CHECKPOINT rule flags op-name strings at module level"
tags: [ch-bsd, plan-18, task-18.2, task-18.3, spec-review, diff-check, duckdb, wal, rollback, ast, sequences]
severity: BULLSHIT
plan: plan-18-duckdb-store-maintenance
task: task-18.2-catalog-maintain-step + task-18.3-offline-reclaim
round: 3
---

# ch-bsd plan-18 r3: diff check of `cb7bf5b..1318b30` {#root}

**Spec commit:** `1318b30` on `wave0-spec-reviews`. HEAD was `1318b30` at the start and
`d15a414` at write time. The three commits in between touch no plan-18 file.
**Compared against:** [[bsd-plan18-r2-spec-diffcheck-cb7bf5b]], the 18.1 r2 report
[[bsd-plan18-task18-1-measurement-r2-34ac5cd]] (S-1, M-2), and decision d9cd in
[[plan-review-2026-10-14]].
**Bug branch:** `/Volumes/littlebig/refmatrix-bugs112-118` at `69ea55b` with a clean tree. It
was read-only.
**18.1 clone:** `/Volumes/littlebig/refmatrix-task-18.1` at `8281a7f`. It was read-only.
**Probes:** run with duckdb 1.5.3 and the deploy interpreter `~/refmatrix/.venv/bin/python -I`.
That interpreter imports `~/refmatrix` at `b381b6d`, where `Store._connect` uses a raw
`duckdb.connect`, so the instance cache applies. Every probe ran on synthetic Stores under
`/private/tmp/claude-501/p18r3/`. No live store was opened and no socket was touched.

| script | log | what it measures |
|---|---|---|
| `p1_fwd_i4.py` | `p1.log` | d9cd (d) item 1 |
| `p1b_replay_check.py` | `p1b.log` | |
| `p1c_init_update_replay.py` | `p1c.log` | |
| `p1d_what_writes.py` | `p1d.log` | |
| `p2_b2.py` | `p2.log` | d9cd (d) item 2 |
| `p3_seq_leg.py` | `p3.log` | the R5 sequence leg |
| `census.py` | `census.log` | the AST census at `b381b6d`, as written |
| `census2.py` | `census2.log` | the AST census at `b381b6d`, with the proposed rule |

rel: derives-from -> [[bsd-plan18-r2-spec-diffcheck-cb7bf5b]]
rel: derives-from -> [[bsd-plan18-task18-1-measurement-r2-34ac5cd]]
rel: contradicts -> [[task-18.3-offline-reclaim#ac-6]]
rel: contradicts -> [[task-18.2-catalog-maintain-step#r11-hold-helper]]
rel: contradicts -> [[task-18.2-catalog-maintain-step#ac-17]]

## r2 closures verified {#closures}

- **N-B1 is closed at the mechanism** (`p2`). With `verify` before `init()`, then a CHECKPOINT
  right after the rollback reopen:
  - **(b2/spec):** the boot has the post-rollback row (20,001, 1).
  - **No-CHECKPOINT mutation:** the boot lacks the row (20,000, 0). The moved WAL grew from
    1,749 to 2,215 bytes, and `<slot>.wal` stayed absent.
- **N-B2** is closed in its shape: the walk covers every module, and exemptions are by
  qualified name, with a staged list that 18.3 empties. The census it rests on is wrong; see
  [[#n3-b2]].
- **N-B3 is closed.** AC-3d adds a `pre_exec_seam` after the check, and the single-shot
  mutation now points at it. This matches r2 `q3`'s race rows.
- **N-S1 is closed** (`p2`).
  - Step 2 alone removed, assertion kept: (b2) exits 2. Measured: the assertion fires on a
    582-byte `<slot>.wal`.
  - Step 1 alone removed: AC-4 (a2) `StoreClosed`, by reasoning.
  - Steps 1 and 2 removed together: AC-6.
- **N-S2, N-S4, N-M1, N-M2 and N-M3 are closed** at the quoted text (R4, AC-3, R3's order and
  the re-bloat preamble, R3 (h)'s clear, the R13 string-constant rule with its AC-17 mutation,
  and R8/AC-12's flush-order AST).
- **N-S3 is closed against the branch at `69ea55b`.** Each element matches `daemon.py`:
  - `_reopen_writer(self, slot=None) -> None` (`:1472`);
  - `.locked()`;
  - `Store` → `init()` → `_connect()`, then `_force_close_store` + raise, then
    `_install_writer_store(st, slot)` (`:1465`, which sets `store` and `_active_slot` and
    refreshes the link);
  - `_writer_lost(reason)` with `os._exit(self.WRITER_LOST_EXIT_CODE)` in a `finally`
    (`:1446`), where `WRITER_LOST_EXIT_CODE = 2`;
  - `_reopen_writer_after_merge` delegates (`:5554`).

  The plan-23 installer item is raised, not edited. The `modelsrv` `_os._exit(1)` exemption
  (d9cd b) is the only non-`0` exit outside the two named exits. The exit census agrees at
  both `b381b6d` and `69ea55b`; see [[#answers]].
- **18.1 r2 S-1 is closed** on both halves. 8281a7f's docstring states the fresh-open
  precondition and a test pins it. 18.3 R5's session-stable leg holds on the production shape
  (`p3`); see [[#answers]].
- **18.1 r2 M-2 is closed.**
  - The status line names `34ac5cd` / `8281a7f`, and the report id is
    `plan18-catalog-measure-20261015-r2` (verified in the clone).
  - The body carries 95 %, `0 < f ≤ r`, 200/80 MiB, one variant per leg including
    `check-text`, and `max(2 %, 512 KiB)`.
  - 18.3 AC-7 carries d9bv.
- **The ordering deviation is sound** (verify before the CHECKPOINT). See [[#answers]].
- **GMD lint:** the four plan-18 files have 0 errors. The warnings are cross-doc dangles from
  linting one file at a time.

## Findings {#findings}

### BULLSHIT N3-B1: AC-6 (fwd-I4) cannot kill "verify moved after `init()`": the open's write replays benign, and the fixture proof the AC requires can never hold {#n3-b1}

**Where:** 18.3 AC-6 "(fwd-I4)" and its fixture precondition, the AC-6 mutation list, AC-4's
mutation list ("the read-back moved after `init()` FAILS AC-6's (fwd-I4) point"), AC-17, and
I10's attribution.

**Measured (`p1`, `p1c`).** The real `Store(root).init()` ran through the cached OLD instance
after step 9, then `os._exit`, then a fresh open of the slot, compared with the rewrite by
count and `sum(hash(row))` per table. Three fixtures were used:

- PLAIN;
- `linkage_types` deleted, CHECKPOINTed, then re-inserted (row ids 0-13 in both files);
- the spec's shape: deleted and re-inserted before ONE CHECKPOINT. The old file's live row ids
  are 14-27 and the rewrite's are 0-13.

| fixture | spec order | mutation (verify after `init()`) |
|---|---|---|
| plain | boot EQUAL | `<slot>.wal` 1,175 B beside the new inode; boot EQUAL, Store boot EQUAL |
| relink, checkpoint between | EQUAL | 1,175 B; EQUAL, EQUAL |
| relink, spec shape | EQUAL | 1,175 B; EQUAL, EQUAL |

**Why the mutation survives:**

- `Store.init()`'s `UPDATE linkage_types SET inverse_of=…` writes NO WAL when the values are
  unchanged. Run alone through the cached instance, the slot had no `.wal` (`p1c`
  `init_sql`), so its row ids never reach a replay.
- The 1,175 bytes come from elsewhere in the open path. They do not come from `init_catalog`,
  which wrote nothing in `p1d`. They replay content-neutral.
- A value-changing UPDATE at a renumbered row id does reach the replay: it aborts the boot
  (`p1b`, `p1c` `value_change`, rc 1). The open writes no such UPDATE.

**Consequence:**

- AC-6's setup proof ("replaying a WAL of `Store.init()` taken on the old file into the rewrite
  changes the R5 gate (or fails the open)") is false on every fixture, the spec's included.
- By the AC's own rule, AC-6 is then "a broken fixture … never reported green". So AC-6 can
  never pass, and the pressure at build time will be to drop the proof.
- The mutation the proof was for has a cheaper, measured kill elsewhere. Under the mutation,
  the old instance's 1,175-byte WAL sits at `<slot>.wal` when R6 B runs, and step 2 MOVES it.
- In the spec order, AC-4 (b)'s step 2 finds no WAL (`p2` b/spec: `slot.wal=None moved=None`
  after step 2).

**Fix (replacement text):**

- **AC-6 (fwd-I4):** delete the paragraph from "**Fixture precondition:**" to "never reported
  green." Replace it with:

  > The point asserts the R5 gate after the boot. It kills nothing on its own: the open's
  > write replays content-neutral (ch-bsd plan-18 r3 N3-B1, `p1`: the `linkage_types` UPDATE
  > writes no WAL when its values are unchanged, and the 1,175-byte open WAL replayed into the
  > rewrite left the gate equal on three fixtures). The verify-after-`init()` mutation is
  > killed by AC-4 (b).

- **AC-4 (b):** after "and the slot has no `.wal` after the run", add:

  > R6 B step 2 moved nothing: there is no `backups/catalog.<S>.reclaim-failed-<run_id>.duckdb.wal`,
  > and the rollback's log line reports a foreign WAL of 0 bytes (the reopen's `verify` refused
  > before the open's first write, so the cached instance wrote no WAL beside the new inode).

- **AC-4 mutations:** replace "the read-back moved after `init()` FAILS AC-6's (fwd-I4) point"
  with:

  > the read-back moved after `init()` FAILS (b): the open's write goes through the cached
  > old instance into a `<slot>.wal` beside the new inode (measured 1,175 bytes), step 2
  > moves it, and the `reclaim-failed-<run_id>.duckdb.wal` file exists.

- **AC-6 mutations:** delete the bullet "the reopen's `verify` moved after `init()` FAILS
  (fwd-I4) …".
- **AC-17:** change "the read-back moved after `init()` → AC-6 (fwd-I4)" to "… → AC-4 (b)".
- **I10:** change "`Store.init()` runs `UPDATE linkage_types SET inverse_of=…` on every open
  (`store.py:1199-1206`); after a reopen on orderly's copy the slot's `.wal` was 1,204 bytes"
  to:

  > every writer open writes a WAL (1,204 bytes on orderly's copy; 1,175 on the r3 probe
  > Store). The `linkage_types` UPDATE in `Store.init()` is not the writer: with unchanged
  > values it logs nothing (ch-bsd plan-18 r3 `p1c`).

  Then also edit the round-3 row that says "the one whose kill depends on a fixture property
  not yet run is marked as such": the property was run, and it does not hold.

**Pattern match:** YES. This is the fourth round running in which a pre-registered kill was
written before it was run (r1 B-4, r2 N-B3/N-S1, and here). The reviser flagged it honestly
as unmeasured, and d9cd (d) routed it here. That is the process working, but the AC as
written would have shipped unpassable.

### BULLSHIT N3-B2: 18.2's CHECKPOINT rule, as written, is red at 18.2 GREEN: the case-insensitive match flags six op-name and message strings, two at module level where no exemption can reach {#n3-b2}

**Where:** 18.2 R11 "the CHECKPOINT rule" and its census sentence, AC-17, and the AC-14
inheritance in 18.3.

**Measured (`census.py`, every `src/refmatrix/*.py` at `b381b6d`, docstrings skipped,
`^\s*(FORCE\s+)?CHECKPOINT\b` with `re.I`).** The rule flags the 10 SQL sites R11 names, plus
these six constants:

| site | constant |
|---|---|
| `cli.schedule_add:2492` | the click `Choice` `"checkpoint"` |
| `cli.checkpoint:7747` | `"checkpoint requires a running daemon …"` |
| `cli.checkpoint:7749` | the op name in `daemon_mod.call(root, "checkpoint", …)` |
| `daemon` **module level** `:6307` | the `OPS` key `"checkpoint"` |
| `scheduler` **module level** `:22` | `ALLOWED_OPS` |
| `Daemon._snapshot_catalog:2705` | `{"error": "checkpoint"}`, which 18.2 R8 ports verbatim into `CatalogHold.snapshot` |

None of the first five is on either exemption list. Two of them sit in no function, so an
exemption "by qualified function name" cannot cover them. So R11's sentence "the census at
`master` `b381b6d` … the seven functions above plus `_snapshot_catalog` and `_op_checkpoint`
… So the rule is green on 18.2's own correct code" is false, and AC-17 is red on correct code.
This is r2 N-B2's defect again, one layer down.

**Measured fix (`census2.py`).** Two legs over every module:

- **Leg 1:** any non-docstring str constant (f-string literal parts included) that matches
  `^\s*(FORCE\s+)?CHECKPOINT\b`, **case-sensitive**.
- **Leg 2:** the first argument of a call to `.execute` / `.executemany` / `.sql` / `._exec`,
  as a constant or an f-string literal part, that matches **case-insensitively**.

At `b381b6d` both legs flag exactly the same 10 sites in the 9 functions R11 names (`leg1 ==
leg2: True`) and nothing else. A lowercase `con.execute("checkpoint")` is still caught (leg 2),
and the op name is not (leg 1 is case-sensitive, and leg 2 only reads SQL call arguments).

**Fix (replacement text):** in 18.2 R11, replace the sentence that begins "**the CHECKPOINT
rule.** A CHECKPOINT statement is any string constant …" and ends "docstrings are not
statements and are skipped." with:

> **the CHECKPOINT rule** (two legs, ch-bsd plan-18 r3 N3-B2). A CHECKPOINT statement is
> (1) any non-docstring string constant, or literal part of an f-string, matching
> `^\s*(FORCE\s+)?CHECKPOINT\b` CASE-SENSITIVELY; or (2) the first argument of a call whose
> attribute is `execute`, `executemany`, `sql` or `_exec`, as a constant or an f-string literal
> part, matching the same pattern case-INsensitively. The op name `"checkpoint"` (the `OPS` key,
> `scheduler.ALLOWED_OPS`, `cli.schedule_add`'s choice, `cli.checkpoint`'s call and message, and
> the `{"error": "checkpoint"}` return value) is not a statement under either leg.

Keep the census sentence, and add after it: "(measured: both legs flag exactly these 10
constants and no other, `census2.py`; a single case-insensitive leg also flags the six op-name
and message constants above, two of them at module level)". Then add an AC-17 mutation: "a
lowercase `con.execute("checkpoint")` in a `Store` method FAILS (leg 2)". 18.3 AC-14 inherits
this unchanged.

**Pattern match:** YES. This is `imp-static-rule-walks-helpers` and r1 S-1 → r2 N-B2 → r3: the
third consecutive round in which this bypass rule was pre-registered against a census nobody
ran. That is a 3+ BULLSHIT pattern. A PATTERN file is recommended (not written: this run was
scoped read-only apart from the report and `last_run.log`).

### MEH N3-M1: the sequence leg matches `nextval('<seq>')` literally and passes vacuously on no match; AC-2 seq-b's seam must restore the identical default text {#n3-m1}

**Measured (`p3`, the production shape).** The live writer issues ids in-session, then
`ATTACH rc` and `COPY FROM DATABASE`, and the gate reads both sides in that session.

- **Legitimate cases pass:** fresh with no issue, 1 issued, 3 issued plus 2 orphan nextvals,
  and created-in-session. In each, a fresh open of the rewrite issues an id above the old max.
- **seq-b fails on `start ≤ max`,** and **seq-c fails on `start < live.last`.** So both
  condition-removal mutations can fail.

**Two gaps:**

- **The leg is spelling-sensitive.** `COPY FROM DATABASE` writes `nextval('seq_e')`
  unqualified (measured), but `nextval('rc.seq_e')` and `nextval('rc.main.seq_e')` are legal
  spellings. A literal match misses them, and the `>` max condition then goes vacuous,
  "no such column".
- **The seed can be killed by the wrong leg.** If seq-b's seam restores the default qualified,
  the variant fails on the COLUMNS leg instead (default text differs), so its "naming the
  sequence" assertion fails in the spec run itself.

**Fix:**

- **R5, sequences bullet 3:** append "A column belongs to a sequence when its `column_default`
  contains `nextval('…')` whose last dotted identifier, unquoted, is that sequence's name. A
  `nextval(` default that resolves to no sequence in the set is reported as a difference (fail
  closed)."
- **AC-2 (seq-b):** after "restore the default", add "with the identical text
  `nextval('seq_entities_id')`, and the seam asserts the columns leg is equal before the
  compare".

### MEH N3-M2: R6's invariant "at every instant" is false under the AC-4 (b2) holder; state its scope {#n3-m2}

**Measured (`p2` b2/fwd_crash).** The holder writes an insert + delete after step 9, `verify`
refuses, and the process is SIGKILLed before R6 B step 2. The boot replays the OLD instance's
582-byte WAL into the NEW inode: the deleted `holder` row comes back (20,001 rows, 1 holder).
The same state follows (b2/no_step2)'s exit 2.

The holder is a test-planted raw `duckdb.connect`. On the branch,
`test_every_file_backed_duckdb_connect_goes_through_open_duckdb` makes such a holder
impossible in `src/`.

**Fix:** R6 invariant, append:

> This holds for every connection the process opened through `backend.open_duckdb`, which
> bug-112's AST guard makes every file-backed one. An UNREGISTERED writer (AC-4 b2's planted
> holder) that commits after step 9 leaves its WAL beside the new inode until R6 B step 2, and
> a crash in that window replays it (ch-bsd plan-18 r3 `p2`: a deleted row reappeared). The
> sentinel detects such a holder; it cannot make that window crash-safe.

### MEH N3-M3: R8 does not say `verify` is one-shot (the Files table does); a reconnect after the sentinel DROP would re-run it and fail {#n3-m3}

**What R8 says:** `Store._connect` "runs it on the DuckDB write connection right after
`self._backend.connect(…)` returns". `_connect` reconnects whenever `_conn is None` (I12).
`check_new` requires the sentinel, and step 11 drops it. So if the new writer Store ever
reconnects, it raises. The Files-to-modify row says "one-shot", but R8 does not.

**Fix:** in R8, after "BEFORE `init_catalog`", add: "It runs once: `_connect` clears it after
the first successful run, so a later reconnect of the same Store never re-runs a check whose
sentinel step 11 has dropped."

### MEH N3-M4: the init-rebind port changes HEAD's behaviour on a close error, while R8 says "behaviour is unchanged" {#n3-m4}

**HEAD's behaviour** (and the branch's, `daemon.py:1829-1862` at `69ea55b`): it logs `init
slot rebind: close failed` and still attempts the slot rebind.

**The port's behaviour:** `h.close_writer()` raises on an error or on a non-empty
`close_errors` (R4 step 7), and R8 sends "a raise" to the legacy fallback. So a close error
that HEAD survived with a bound slot now serves the legacy file.

**Fix:** in R8 Ports, init rebind bullet, add: "A `close_writer()` error is logged as HEAD's
`close failed` line and the reopen is still attempted; only a reopen failure takes the legacy
fallback." Alternatively, state the change and its reason.

## Answers to the brief {#answers}

- **(1) AC-6 fwd-I4: can "verify moved after `init()`" FAIL?** No ([[#n3-b1]]). The open's
  write replays content-neutral on all three fixtures, including the spec's delete+re-insert.
  The linkage UPDATE logs no WAL at all when its values are unchanged. The AC's setup proof can
  never hold. The measured kill is AC-4 (b)'s "no moved WAL" assertion.
- **(2) AC-4 (b)/(b2) under verify-before-init + immediate CHECKPOINT:** (b2) kills BOTH
  mutations.
  - No CHECKPOINT: the boot lacks the post-rollback row.
  - Step 2 removed with the assertion kept: the assertion fires on the 582-byte `<slot>.wal`,
    and the run exits 2.
  - (b) alone does not kill no-CHECKPOINT: the boot has the row, as the spec says.
  - `check_old` passes in (b2): count 20,000 = 20,000, `total_blocks` 119 = 119. This works
    because the holder's write is net-zero; an insert-only holder would fail `check_old` and
    exit 2. The fixture says insert + delete, which is correct.
- **The ordering deviation (verify before CHECKPOINT): sound.**
  - `verify` reads only and must precede `init()`'s write.
  - The CHECKPOINT is then the first statement after `_reopen_writer` returns, and it folds
    `init()`'s write and the holder's from the moved WAL into the restored inode. Measured:
    the moved WAL went 1,749 → 1,809, then the next WAL appeared at `<slot>.wal` (474 bytes).
  - In the crash window between `verify` and the CHECKPOINT, only content-neutral writes are
    lost.
  - r2's order would CHECKPOINT an instance before its identity was proven.
- **The AST census at `b381b6d`:**
  - The SQL CHECKPOINT sites are exactly R11's: 7 exempt or staged functions plus
    `_snapshot_catalog` and `_op_checkpoint` (10 constants).
  - The init rebind is inline in `Daemon.serve_forever:1762`, as the staged entry says.
  - The rule AS WRITTEN also flags six op-name and message strings ([[#n3-b2]]). The two-leg
    rule is measured exact.
  - `os._exit` at `b381b6d`:
    - `_fast_exit_if_invalidated` → `os._exit(2)`;
    - `serve_forever`, `spawn_daemon` ×2 and `hub.spawn_hub` → `os._exit(0)`;
    - `modelsrv.ModelServer._check_worker_version` → `_os._exit(1)`.

    There is no `from os import _exit`. The rule with the modelsrv exemption is green at
    `b381b6d` and at `69ea55b`, where `_writer_lost` is added.
- **R8 against the branch at `69ea55b`:** it matches in every element (see [[#closures]]).
  - `_install_writer_store` is called only from `_reopen_writer` on the branch. Boot's first
    open does not call it yet, so AC-14's "only from" holds.
  - The branch's init rebind still constructs `Store(` inline (`:1837`, `:1860`), which the 18.3
    port replaces.
- **The 18.3 R5 sequence leg against the 18.1 `8281a7f` fresh-open precondition:** consistent.
  - 8281a7f's docstring says "do NOT drop the leg; define it on session-stable invariants (18.3
    R5)".
  - R5's two conditions pass every legitimate in-session and fresh-open case on the production
    ATTACH+COPY shape, and fail seq-b and seq-c (`p3`). That also holds between two fresh
    opens, so 18.1 can import it.
  - The spelling gap is [[#n3-m1]].

## Verdict {#verdict}

**6 findings (2 BULLSHIT, 0 SKETCHY, 4 MEH).**

- **18.2: NEEDS-REVISION; approval-ready once [[#n3-b2]]'s replacement text is applied
  verbatim.** That text is the two-leg rule plus one mutation. It is measured exact at
  `b381b6d`, so no new probe is needed.
- **18.3: NEEDS-REVISION; approval-ready once [[#n3-b1]]'s replacement text is applied.** That
  means re-pointing the verify-after-init kill to AC-4 (b), deleting the fixture-proof
  paragraph and correcting I10. Fold in N3-M1 to N3-M4 (each one sentence). Every mechanism
  the design rests on held when probed this round. A closing diff check, with no probes, should
  be enough.
- **Plan file:** clean.
- **18.1 spec:** clean (M-2 folded).

rel: contradicts -> [[task-18.3-offline-reclaim#ac-6]]
rel: contradicts -> [[task-18.2-catalog-maintain-step#ac-17]]
