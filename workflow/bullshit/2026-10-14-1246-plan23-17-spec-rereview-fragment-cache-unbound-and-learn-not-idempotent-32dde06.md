---
gmd: "0.1"
id: bsd-plan23-17-spec-rereview-32dde06
title: "plan-23 + plan-17 spec re-review: bind leaves the partition-agnostic fragment cache unbound (live store already cross-contaminated), learn is not idempotent, 23.3 stamps files before their semantics; plan-17 closes its 19 prior findings but mis-consumes 23.1 and has unrunnable rollout ACs"
severity: BULLSHIT
plan: plan-23-bounded-write-harness
task: spec-rereview-23.0-23.4-and-17.1-17.3
round: 2
tags: [bsd, audit, spec-review, re-review, plan-23, plan-17, partition, fragments, exactly-once, maintenance, wave-1]
---

# ch-bsd spec re-review of plan-23 and plan-17 at `32dde06` {#root}

**Commit reviewed:** `32dde06` (branch `wave0-spec-reviews`). **Written:** 2026-10-14T12:46:22-0700.
While I worked, HEAD moved to `c2e201a`. That commit adds task 17.4 (a daily facts.log backup) and
one row in the plan-17 table. 17.4 marks itself "NOT covered by the 32dde06 re-review". I did not
review it, except to note in [[#ns17-5]] that it inherits a cross-plan gap. `src/` and `tests/` are
byte-identical between `b1c4324` (the HEAD the specs cite) and `32dde06`.

**Scope:**
- plan-23 and tasks 23.0-23.4;
- plan-17 and tasks 17.1-17.3;
- the prior reviews [[bsd-plan23-spec-review-3104a81]] and [[bsd-plan17-spec-review-3104a81]];
- the decision-log review [[bsd-decision-log-review-a192ba2]] items that touch these plans;
- the decision log [[plan-review-2026-10-14]], including #t8, which wins over earlier rows;
- the consumers 19.2, 19.4 and 22.2, and the storage exploration's Option A / #measure.

**Method:** I read every revision-table claim in the spec text and checked it against code at HEAD.
Every cited line number (`cli.py`, `vectors.py`, `discovery.py`, `hub.py`, `launchctl.py`,
`daemon.py`, `sync.py`, `learn_queue.py`, `store.py`) matches.

Three throwaway probes ran, using `.venv-eval` with `-I` and `HOME`/`RMX_HOME`/`REFMATRIX_ROOT`
redirected:
1. **Fragment cache** (`/tmp/rmxp-*`): a fresh tmp store, `link` in the default partition, then
   `with_partition("pb")` + `link` + flush.
2. **Learn replay** (`/tmp/rmxe-*`): `_learn_grep_hits` called twice with the same hits.
3. **Snapshot census:** a `cp` of this repo's lock-free read snapshot (`catalog.read.duckdb`) into
   `mkdtemp`, opened `read_only`, then deleted.

Other checks: pylance 6.0.1 API signatures were read by introspection, with no dataset opened. I
ran `ls`/`plutil` on LaunchAgents plists and store `vectors/` directories.

Not done:
- no `rmx` against a live store, no `Store()` on a live root, no suite;
- no edits to `src/`, `tests/`, plans or ledgers.

**One slip to report:** one early search was a bare `grep` on a file. The `grep-rewrite-guard` hook
rewrote it to `rmx grep`, which fell back to `rg` (`# rmx grep fallback via rg`). That may have
added a learn/telemetry row to this repo's live `query.log`. After that I searched with Python
only.

rel: derives-from -> [[bsd-plan23-spec-review-3104a81]]
rel: derives-from -> [[bsd-plan17-spec-review-3104a81]]
rel: derives-from -> [[bsd-decision-log-review-a192ba2]]
rel: related-to -> [[plan-review-2026-10-14]]
rel: specifies -> [[plan-23-bounded-write-harness]]
rel: specifies -> [[plan-17-nightly-store-maintenance]]
rel: related-to -> [[project_bug098_writer_partition_race]]
rel: contradicts -> [[claude#no-silent-failures]]
rel: contradicts -> [[feedback_decay_never_loses_knowledge]]

## Prior findings: status {#prior-status}

### plan-23 r1 (13 findings) {#prior-23}

| id | status | evidence at `32dde06` |
|---|---|---|
| b-1 binding across yields | **partial** | Rows are fixed: 23.1 R1.1-R1.2 binds inside the hold, events carry names, and AC-3 has a two-partition competitor and a mutation. The OTHER half of the binding, `Store._fragments`, is partition-agnostic and nothing binds it ([[#nb23-1]]). |
| b-2 exactly-once window | **partial** | Closed for `scope="window"`: the offset is in the batch transaction, segments are kept, `*.draining` is adopted at boot, and AC-4 injects five faults including a SIGKILL child. Learn's `scope="segment"` rests on a false idempotence claim ([[#nb23-2]]). |
| b-3 per-row writes invisible | closed | 23.2 R3 write-count recorder (statements via `execute`/`executemany`/`_duck`, Lance versions, single-row upserts); 23.1 R2 `finalize`, AC-8, AC-9; 23.2 AC-3 pre-registered bug-085/093 mutations. `_ingest_python_semantics` (`ingest.py:1420`) still exists to re-introduce. |
| s-1 N-per-hold / stop paths | closed | R2 names `batch` (default 1), `budget_s`, `cancel`, `on_error`, `hold_alarm_s`, `finalize`, and resume-from-offset; R9.1 sets learn to `batch=1`. `Daemon._is_fatal_invalidation` (`daemon.py:1215`) and `_shutdown_event` (`:719`) exist. |
| s-2 key-only coalesce | closed | `merge_fn` is required, there is no last-wins default, AC-2 does a SUM over 10 keys plus a TypeError check, and AC-1 states distinct keys. |
| s-3 not queue-shaped / tick registry | closed | Three front-ends; R6 has one registry and one budget with round-robin; 23.3 runs on `bounded_steps`; plan-21 is listed as a consumer. |
| s-4 holds self-counted / `_FairLock` | closed | `recorded_daemon` on a real `_FairLock`; 4 ordered competitor wins; 23.2 is ordered before 23.1. |
| s-5 vacuous marker / bound is a warning | closed | 23.2 R4 fails on zero holds, R5 states that seconds are an alarm, and AC-4 tests this through `pytester`. |
| s-6 overflow has no route | closed | R6.5-R6.6 add `queue_counters`, the `queue_status` op, an unconditional print and an unreachable-daemon message; AC-12. |
| s-7 sandbox | closed | Task 23.0; each test strategy names it, and the kills are spawned children, never forks of a DuckDB holder. |
| m-1 `lock_free_during` signatures | closed | 23.2 R1: one plain function that takes any lock. |
| m-2 grep misses probes | closed | 23.2 R6 adopts `test_learn_queue.py:182` and `test_bigop_nonblocking.py:104/:176` (both verified); AC-6 fixes the pattern and its exclusion. |
| m-3 stale docstrings | closed | 23.1 R9.4, AC-15. |

**Correction to my own r1 (b-2):** I wrote that learn survives replays because its writes are
"`INSERT OR IGNORE`-shaped evidence". That is false. `add_evidence` is a plain `INSERT` into a table
with no key. The revision copied my error ([[#nb23-2]]).

### plan-17 r1 (19 findings) {#prior-17}

| id | status | evidence |
|---|---|---|
| b-1 phantom handle | closed | R4 and AC-3 are rewritten for out-of-daemon readers: a retry-once helper and `lance_retries` on the `cli.log` row. `vectors.py:114,131,146,171,258` each open `lance.dataset` fresh (verified). |
| b-2 AC-1 vs 24 h | closed | `older_than_s` (default 86400, env override); AC-1a uses window 0; AC-1b pins the default; the mutation is listed. |
| b-3 gate after cleanup | closed | The order is a→b(tag)→c→d→e(compare)→f(cleanup only on a match). A mismatch restores `v_reaped` and keeps every tag; AC-2 checks that versions are ≥ the count before the run and that the tag is present. pylance 6.0.1 `cleanup_old_versions(..., error_if_tagged_old_versions=)` and `restore()` exist. |
| b-4 circular orphan proof | closed | Whole-catalog id query with no binding; fail closed on an unreadable or empty catalog; ratio cap; vectors kept in the fsynced list; restore op; mutations for partition, cap and empty catalog. The cap's design has its own issue ([[#ns17-3]]). |
| b-5 live stores in tick tests | closed | Injected `roots`; 23.0 redirects `HOME` before import (`launchctl.py:20` is computed at import, confirmed); R8 takes no embedder; AC-11 and AC-3 record zero connects. |
| b-6 unanchored no-match filter | closed | R9 + AC-9. The Lance delete runs BEFORE the catalog delete in both `purge_path` (`store.py:5921-5923`) and `_bulk_purge_ids` (`:6054`), so the `vectors_updated_at` filter can be read in time. |
| s-1 plan-23 misnamed | **partial** | The dependencies are fixed, but the consumed names and per-hold seconds do not match 23.1's contract ([[#ns17-2]]). |
| s-2 alert thread | closed | Own `_maintain_loop`; AC-2 with interval 0; per-store budget; a timeout is `still_running`. A new gap: still_running is unbounded ([[#ns17-4]]). |
| s-3 first-run stamp | closed | d3d: unarmed means dry run (R7, AC-5). |
| s-4 17.3 measurements | **partial** | Store list, global dropped, 10k threshold, backups removed only on user confirm. The clone the latency and no-match legs need does not exist ([[#ns17-6]]). |
| s-5 `partition=None` | closed | Every directory under `vectors/`; AC-6. Name vs id: [[#ns17-2]]. |
| s-6 store set | closed | The launchd list (`discovery.py:70`; 8 plists verified); AC-3 has a launchd-only root. |
| s-7 Option A | closed | d2b plus the #option-a-revisit triggered by 23.4. |
| s-8 in-process fallback | closed | R1 refuses; AC-10. |
| m-1 stale citation | closed | `daemon.py:5792` verified. |
| m-2 checksum | closed | `Σ blake2b_64(id‖vector) mod 2^64`. |
| m-3 skip cost | closed | `check_s` is reported. |
| m-4 `missing` | closed | 17.1 R7, 17.2 R6. |
| m-5 (store, step) stamps | closed | 17.2 R1; `RMX_MAINTAIN_ALERT_AFTER`; AC-8. |

### Decision-log review items touching these plans {#prior-dlr}

| id | status | evidence |
|---|---|---|
| dlr #b-3 (Wave 1 order) | closed | plan-23 #dependencies and plan-17 #dependencies match #t8-wave1. |
| dlr #b-5 (17 #b-4 half answered) | closed | Cap, restore op, retention forever, partition mutation. |
| dlr #b-6 item 2 (d2b revisit unscheduled) | closed | The trigger is 23.4's verdict (plan-17 #option-a-revisit, 23.4 #ranges). |
| dlr #s-1 (fragments / `replica_merge` / retention) | closed | 23.1 R1.3 (fragments inside the transaction), R7, R8, R4.2/R4.4, AC-13, AC-14. |
| dlr #s-2 (d2e owner / rule / gate) | closed | Task 23.4 has ranges written BEFORE any run: no `option-a-measure-*` file or `eval/option_a/` exists at HEAD, and AC-1 requires the user confirmation commit to come first. Soundness: [[#ns23-1]]. |
| dlr #s-3 (23 #s-3 uncited) | closed | See 23 s-3. |
| dlr #s-6 (retries / single-flight) | closed | 17.2 R4 `retries=0`; 17.1 R11; 17.2 AC-6; 19.4 R1 matches. `daemon.call(..., retries: int = 2)` is the default (`daemon.py:575-576`), so `retries=0` must be passed explicitly, and it is. |
| dlr #s-7 (restore across 17/22) | **partial** | The 17.1 R6 list format is stable. `task-22.2` at `32dde06` names neither the orphan list nor `vectors_restore` ([[#nm17-3]]). |
| dlr #m-3 (16.6 on the dropping queue) | closed | Overflow is counted, persisted and printed. |
| dlr #m-4 (reader retry surface) | closed | `lance_retries` on the `cli.log` row. |
| dlr #m-5, #m-6 | closed | Recorded in the plan-23 revision table. |

**Closure:** plan-23 has 11 of 13 closed and 2 partial. Plan-17 has 17 of 19 closed and 2 partial.
Of the decision-log review items, 10 are closed and 1 is partial. {#prior-status-body}

## New findings: plan-23 {#findings-23}

### BULLSHIT nb23-1: `bind` binds `_partition_id` but not the fragment cache, which is partition-agnostic; the live store is already cross-contaminated, and AC-3 checks rows only {#nb23-1}

**Where:**
- 23.1 R1.1 (`daemon_bind` = `with d._store_lock: with st.with_partition(name)`);
- R1.3 (fragments flushed "keyed by the BOUND partition_id");
- AC-3 ("0 rows of the drain's batches are in `pb`");
- plan-23 #why ("a `bind` seam that takes the lock and the partition together").

**What the code does:**
- `Store._fragments: dict[str, BitMap64]` and `_dirty_fragments` are keyed by LINKAGE only
  (`store.py:1055-1056`). The comment there says "The Store is bound to one partition for its
  lifetime, so the cache is implicitly partition-scoped". That stopped being true when
  `with_partition` arrived.
- `with_partition` (`store.py:1911-1952`) swaps `_partition_id`/`_partition_name` and drops `_vs`.
  It never touches `_fragments` or `_dirty_fragments`.
- `link()` (`:4339`) mutates whatever `_load_fragment(linkage)` has cached. The flush writes it under
  the partition bound AT FLUSH TIME (`_flush_fragments_duckdb`, `:4156`).
- `_partition_keeping_yield` (`daemon.py:3313`), the bug-098 fix, restores only the two ids.

**Probe 1** (fresh tmp store):

```
tmp mentions [(1, 2)]
pb  mentions [(1, 2), (3, 4)]          <- pb's row holds tmp's bit
after returning to tmp and linking alpha->f5:
tmp mentions [(1, 2), (1, 5), (3, 4)]  <- tmp's row now holds pb's bit
```

**Probe 3** (a tmp copy of THIS repo's live read snapshot). Fragment bits whose entity id belongs
to a different partition than the fragment row:
- `sessions-refmatrix mentions`: 195,003 of 422,811;
- `sessions-refmatrix imports`: 2,364 of 2,410. The sessions partition holds no code, so these are
  project bits;
- `sessions-refmatrix lead`: 58,487 of 101,809;
- `refmatrix lead`: 17,901 of 125,865;
- rows under a `partition_id` that has no `partitions` row: 16 linkages.

This is the bug-098 class on the bitmap side. It is live, it is unlogged (the highest row is bug-104),
and every 23.x consumer would inherit it.

**Why it is bullshit:**
- Plan-23 exists to make "release between batches" binding-safe, and its own AC-3 cannot fail on
  this. The competitor in AC-3 "writes one row" in `pb` and releases while bound. Its link leaves a
  dirty `pb` fragment object in the cache. The drain's next batch, bound to `pa`, links into that
  object and flushes it, in-transaction (R1.3), under `pa`'s id. The relational rows are all
  correct, so AC-3 passes. Meanwhile `pa`'s `bitmap_fragments` row is overwritten with `pb`'s bits.
- R1.3's rollback rule ("drop the cache entries the batch dirtied") assumes the cache belongs to the
  bound partition, which it does not.
- R1.1 also contradicts R1.2. `with_partition` AUTO-CREATES an unknown partition row (`INSERT OR
  IGNORE INTO partitions`). R1.2 and AC-3 require `bind` to RAISE on an unknown name. The spec never
  says that `bind` must not be `with_partition` as it stands.

**Fix:**
- Key the fragment cache and the dirty set by `(partition_id, linkage)`, or make `with_partition`
  flush the dirty set under the OUTGOING id and swap in a per-partition cache on entry and exit.
  The fix belongs in `store.py`, inside the seam, and not in consumers.
- `bind` uses a lookup-only partition resolve (`create=False`).
- AC-3 adds: after the drain, `pa`'s and `pb`'s `bitmap_fragments` rows contain zero bits whose
  entity belongs to the other partition. Mutation: the cache keyed by linkage only must FAIL.
- Log a bug row (bug-105), with this census as evidence.
- Give the repair an owner: rebuild every partition's fragments from `entity_links`, a derived
  rebuild that loses nothing. The natural owner is 23.1 as a one-time migration at boot, or a task
  of its own.
- The exploration's Option A "Store-state audit" must list the fragment cache as binding state
  ([[#ns23-1]]).

**Pattern match:** YES. Impression `#imp-yield-owns-the-binding` (r1) said to ask what OTHER state
the holder owns. The revision answered that for `_partition_id` only.

### BULLSHIT nb23-2: learn is declared `idempotent=True`, but its evidence write is a plain INSERT, so the segment-scope replay duplicates rows, and AC-5 cannot see it {#nb23-2}

**Where:**
- 23.1 R3.5 (`scope="segment"` is refused unless `idempotent=True`; "Learn's writes are set-bit and
  insert-if-absent evidence, so learn declares it");
- R9.1;
- AC-5 ("no pattern applied twice");
- plan-23 open item 2.

**What:**
- `_learn_grep_hits` (`daemon.py:4295`) calls `store.add_evidence` once per `(file, line)`.
- `add_evidence` (`store.py`) is `INSERT INTO linkage_evidence(...) VALUES (...)`, and
  `linkage_evidence` has no primary key or unique constraint in either DDL (`store.py`,
  `duckdb_catalog.py`).
- **Probe 2:** two identical learns gave 4 evidence rows and 1 `entity_links` row.
- So a crash after a hold has committed only the covered PREFIX re-applies every entry past it, and
  each re-applied entry duplicates its evidence rows and its `facts.log` `evidence` events.
- The guard that is supposed to make `scope="segment"` safe is a self-declaration that nothing
  checks.
- AC-5 crashes before ANY apply, so nothing is re-applied, and it counts patterns, not evidence
  rows. It passes.

**Why it is bullshit:**
- The exactly-once claim for the one consumer that ships in 23.1 rests on a false code fact.
- Open item 2 asks the user to "confirm this reading of d2a for learn", which is a decision on a
  false premise.
- Duplicate evidence also inflates whatever plan-16/22 counts per `(file, line)`.

**Fix:**
- Choose one, and the spec can settle this without the user:
  - (a) Learn's evidence write becomes insert-if-absent on `(entity_id, linkage_id, concept_id,
    file, line)`, and the `facts.log` event is emitted only on an actual insert. This also cures
    today's duplication from re-learning the same pattern, the same probe without a crash.
  - (b) Learn moves to `scope="window"`.
- Add an AC: a child `os._exit`s after hold 1 of 3 in segment scope. After the restart, the evidence
  row count equals the number of distinct `(pattern, file, line)` triples.
- Mutation: the plain INSERT back must FAIL.
- Make `idempotent=True` a checked property (the AC above) rather than a declaration.

**Pattern match:** YES (impression `#imp-exactly-once-window`; and a guard computed from the
author's claim, `#imp-circular-guard`).

### BULLSHIT nb23-3: 23.3 commits each file's mtime stamp before its semantic pass, so a crash, cancel or budget stop between them loses that file's semantic layer until the file is edited again, and AC-5 asserts the loss as success {#nb23-3}

**Where:** 23.3 R1 (the per-file pass is one step; `.pseudo`/`.md`/ADR/Python semantics are later
steps), R4 ("uncommitted files are re-synced next time because their mtime stamp was not written (the
stamp commits in the file's own step)"), and AC-5.

**What:**
- In `_sync_paths`, the per-file pass purges the old entity together with its semantic links
  (`sync.py:241-242`) and stamps the mtime (`s.mark_tracked`, `:244`).
- The GMD batch (`:254`), tldr, `.pseudo`, ADR/markdown semantics (`:312`) and the bulk Python
  semantic pass (`:330`) run AFTERWARDS, over `touched_existing`.
- Under R1, steps 1-3 commit "file ingested, semantics purged, stamped". Then a crash, a cancel, or
  a `budget_s` stop (R2) hits before the semantic steps.
- The next sync skips those files as unchanged (the mtime gate at `:217-227`), so their semantic
  links never come back. AC-5 asserts exactly this outcome: "next sync processes exactly the other
  2".
- At HEAD the whole sync is ONE transaction, so a crash rolls everything back. A cancel already
  commits stamped files without semantics, because the `with` block exits normally. So that half is
  pre-existing, and 23.3 widens it to crashes and budget stops while R4 claims the opposite.

**Why it is bullshit:** this is a correctness regression written as a guarantee, plus an AC that
passes on the defect. It loses derived knowledge silently, against `feedback_decay_never_loses_knowledge`
and CLAUDE.md #no-silent-failures. Memory `project_sync_mtime_gate_strands_docs` records the
mtime gate stranding documents this way before.

**Fix:**
- Choose one:
  - make each FILE one step: ingest + its semantics in one transaction, with the ADR map read off
    the lock in `prepare`;
  - or stamp the mtime in the file's LAST step;
  - or write a `semantic_pending` marker that the next sync honours over the mtime gate.
- AC-5 becomes: a child exits after the per-file steps and before the semantic steps. The next sync
  re-applies the semantics of all 5 files, and the graph equals HEAD's on the same fixture (AC-6's
  row diff).
- Mutation: stamp in the per-file step must FAIL.

**Pattern match:** YES (the mtime gate outranking a later phase: memory
`project_sync_mtime_gate_strands_docs`).

### BULLSHIT nb23-4: bug-093's "op-start log line" is owned by no task (rule 9a) {#nb23-4}

The bug-093 row says "Still open: yield the writer BETWEEN files …, and the op-start log line". d2c
gave the yield to 23.3. Plan-23 open item 5 says "23.3 does not take it", and no task under
`workflow/plans/*-tasks/` covers it. A target exists, but no scheduled task does the work, so this is
an unanchored deferral. It costs one line to close: 23.3 R7, "the watch `_flush` logs
`watch flush start: N files, roots=[…]` before taking the first hold", plus an AC on `d._logs`.
This needs no user decision.

### SKETCHY ns23-1: 23.4's ranges are pre-registered but unsound in five places {#ns23-1}

The numbers were written before any run, and AC-1 pins the user confirmation commit ahead of the
first measured run. That part is right. The rule itself:

1. **It excludes the most contended row.**
   - R2's SQL shapes (entity upsert, `entity_links` insert, `UPDATE`, delete) omit
     `bitmap_fragments`.
   - R3 calls the "pyroaring fragment buffer" out of scope because it "keeps its own locks". On the
     DuckDB backend, the persisted fragment is ONE row per `(partition_id, linkage)`, upserted by
     every link-writing op (`_flush_fragments_duckdb`). 23.1 R1.3 now flushes it INSIDE every batch
     transaction.
   - DuckDB conflicts on same-row updates (exploration #duckdb-concurrency). Two concurrent batches
     that both touch `mentions` conflict every time.
   - A replay without that row measures a lower conflict rate than Option A would see, so the verdict
     is biased toward GO.
2. **It couples a correctness cure to a throughput number.** NO-GO forbids proposing Option A's
   binding-removal half. GO-serial permits only that half. But binding removal is the cure for the
   bug-098 class (and for [[#nb23-1]]), and a speedup below 1.1× says nothing about it. Decouple:
   the measurement decides concurrency only. Binding removal is decided on correctness.
3. **An error at N=1** is a broken copy or a DuckDB bug, not concurrency. It should invalidate the
   run, not return NO-GO for Option A.
4. **R6's "row counts equal the replay's expected counts"** has no consequence in the table.
   Round-robin dealing of one serial history reorders inserts and deletes, so "expected" is
   undefined. "Worst of the three runs" is also ambiguous for a ratio: is it the minimum speedup over
   paired runs?
5. **AC-5** compares the live cliquet active slot's and `facts.log`'s size and mtime before and after.
   A live daemon changes both from normal activity, so the AC fails without a defect. Assert instead
   that the measurement process opened no path outside its tmp dir (23.0's audit hook in the script).

**Fix:** amend #ranges before asking the user to confirm them. Item 1 alone can flip the verdict.

### SKETCHY ns23-2: 23.0 AC-4's size+mtime check on the repo's live logs fails on normal activity {#ns23-2}

During this read-only review, this repo's `.refmatrix/query.log` changed at 12:42 and `facts.log`
at 12:43, through the watcher and hooks. A 13-minute full run will see the same. AC-4 as written
("all four unchanged") therefore fails without a sandbox leak, and an implementer will drop the two
repo logs from the check: the cheap-fix path (rule 10). The global logs are quiet (last written on
10-07), so they are a fair check today, but not a guaranteed one.

**Fix:** assert on the DELTA's content. No row appended during the run has a cwd, root or path under
`RMX_SANDBOX_ROOT` or a pytest tmp dir (d8d's predicate), and the touches log gains 0 lines.

### MEH nm23-1: dead-letter has no retention and no re-drive (open item 4) {#nm23-1}

A counted dead-letter file with no reader repeats the "safety net with no reader" shape
(dlr #b-5). State the retention (forever) and add `queue_status --redrive <queue>`, which
re-appends dead-lettered lines, or say that a dead-lettered learn line is re-learned by the next
grep miss. The spec can settle this.

### MEH nm23-2: d8d's predicate owner (open item 3) can be settled by the spec {#nm23-2}

`telemetry.py` already owns `query.log` reading (`telemetry.py:668`). Put the one predicate there.
21.1's emitter, 19.2's fold and the 23.0 AC-4 delta check all import it. This needs no user
decision.

### MEH nm23-3: the bug-099 row is stale {#nm23-3}

The row says "the decision … is pending with the user". d2a decided it. Update the row in the
revision, or the docs step will copy the stale text.

### MEH nm23-4: R1.3's transaction is a new primitive and needs a name {#nm23-4}

`Store.transaction` flushes after `COMMIT` (`store.py:4256-4269`). R7 keeps that behaviour
outside the harness, while R1.3 needs the flush before `COMMIT`. Name the harness's primitive (for
example `Store.batch_transaction()`) so that an implementer does not "fix" `Store.transaction`
globally or nest the two. Nesting is a no-op today (`if self._in_transaction: yield`), which
would silently move the flush back after `COMMIT`.

{#findings-23-body}

## New findings: plan-17 {#findings-17}

### SKETCHY ns17-1: 17.2's step registry is not 23.1's tick registry and cannot be, yet 17.2 depends on a "23.1 tick-registry step interface" that 23.1 does not define {#ns17-1}

This settles plan-17's open item 1. The answer is **NO: two objects, two budgets, and no user
decision needed.**

| | 23.1 R6 `tick_registry` | 17.2 R2 step registry |
|---|---|---|
| process | the store daemon (`_runner`, every 30 s) | the hub (`_maintain_loop`, 03:30 + catch-up) |
| signature | `register(name, runner, *, kind)`, kind ∈ drain/tail/bounded_steps | `(name, callable(root, dry_run) → result)` |
| budget | ONE shared `LEARN_DRAIN_BUDGET_S` (5 s) per tick | per-store 600 s timeout / 1,800 s budget |
| consumers | learn, 19.2's fold, 16.6 marks | 17.1, 19.4 compile, plan-18, 17.4 |

23.1 R6.4 already says "17.1, 22.2 and 23.3 use `bounded_steps` from their own ops, not the tick".
In contradiction:
- 17.2's header ("Depends on: … 23.1 (tick-registry step interface)");
- 17.2 R2 ("using the step interface of plan-23 23.1's tick registry");
- plan-17 #dependencies.

C6 ("one tick, one stamp store") is about the HUB tick and `maintain.json`. #t8 d4a's "one
registry" is about the daemon's tick. They are different "ones".

There is also a smaller mismatch. 19.4's AC preamble says "17.2's tick enumerates only the sandbox
registry", while 17.2 R3 injects launchd roots and explicitly NOT `registry.json`.

**Fix:**
- Name them distinctly: daemon `tick_registry` and hub `maintenance_steps`.
- 17.2 defines its own step interface and drops the 23.1 dependency, except for the 23.0 sandbox.
- Plan-17 closes open item 1 with this table.
- 19.4's preamble says "injected roots".

### SKETCHY ns17-2: 17.1 consumes 23.1 under names and contracts 23.1 does not have {#ns17-2}

- **`bind`:** 17.1 R3/R10 and plan-17 #design say `bind(batch)`. 23.1 R1.1 defines
  `bind(partition_name) -> ContextManager[Handle]`.
- **`bounded_steps`:** the plan-23 consumer table puts 17.1 on `bounded_steps`. 17.1 never names it.
  Calling `bind` directly would skip R2's `cancel` (shutdown during a 19 s compaction), the
  `on_error` policy and the recorder hook.
- **Partition id vs name:** 17.1 R1 resolves "its own explicit partition id". 23.1 R1.2 says batches
  carry NAMES, never ids. The `vectors/` directories are names (`vectors/<partition_name>/`,
  `store.py:3647`), so the name is what is needed.
- **The "per-batch hold timer":** 23.1's `RunResult` exposes only `holds` and `max_hold_s`. 17.1
  R7 reports hold seconds PER DATASET, and 17.3 R2 reads them, but no source exists. The recorder
  is test-only (23.2: "nothing here enters `src/`").
- **AC-4's `lock_free_during`:** AC-4 says `lock_free_during` "acquires `_store_lock` between
  datasets". 23.2 R1's function is called by a fake from INSIDE the code under test. Between
  datasets there is no call site, and the test's `compact` seam runs inside the hold.

**Fix:**
- 17.1 R3: "each dataset is one `bounded_steps` step, `bind(partition_name)`, `on_error="stop"` on a
  fingerprint mismatch, `cancel` = shutdown".
- 23.1 R1.5 adds `hold_s` per step (a list, or an `on_step(result)` callback).
- AC-4 uses the recorder's ordered competitor wins (23.1 AC-1's shape) instead of
  `lock_free_during`.

### SKETCHY ns17-3: the ratio cap refuses the plan's own motivating case, and the refusal also blocks compaction, so a capped dataset regrows without end {#ns17-3}

- **The plan's own numbers trip the cap.** Plan-17 #why-numbers cites "559 of `code.lance`'s 5,495
  vectors" as orphans. That is 10.2 %, above max(50, 5 % = 275). Unless those orphans have been
  reaped since, which I could not check without opening a live store, 17.3 R1 step 3 stops this
  repo's rollout at `refused:orphan_cap`.
- **The refusal also blocks compaction.** 17.1 R6 says "no delete, no compaction of that dataset".
  A capped dataset's version count therefore grows without bound (the exact bug-085 growth), and it
  alerts every night.
- **There is no release.** Open item 2 names the release mechanism as unsettled, and 22.5 moves
  plus 22.3 forgets will produce legitimate bulk orphaning in the global store.

**Fix:**
- A cap refusal skips the REAP only. Compaction and cleanup still run behind the fingerprint gate,
  with expected B = A because nothing was reaped.
- The release is a hand-run `vectors_maintain --confirm-orphans <hash>`, where the hash is the
  dry-run orphan list's content hash: d8g's "the gate is the manifest, not the surface". The user
  only needs to confirm the form, not invent it.
- Add an AC: 60 of 100 rows orphaned → reap refused, version count drops, then a run with the
  matching hash reaps all 60.

### SKETCHY ns17-4: `still_running` has no ceiling: a wedged maintain op never fails, never alerts, and blocks the whole fleet's maintenance {#ns17-4}

17.2 R4 makes a timeout or `already_running` the outcome `still_running`, never `failed`. It
excludes that outcome from R5's alert, and it keeps the run strictly serial: the next store does not
start while one is still running. A bug-085-shaped wedge inside `vectors_maintain` therefore yields:
- `still_running` on every tick, forever;
- no alert;
- `deferred` for the other 7 stores, every night.

That is the silent failure CLAUDE.md #no-silent-failures names, moved from "failed" to "pending".
AC-7 covers one budget only.

**Fix:**
- A (store, step) that is still running across `RMX_MAINTAIN_STUCK_AFTER` (default 2) consecutive
  per-store budgets becomes outcome `stuck`. It alerts once and stops blocking.
- The other stores proceed. They are separate daemons, and the serial rule is a load rule, not a
  safety rule.
- Add an AC: an op that never returns → `stuck` alert on the second budget, and store 2 runs.

### SKETCHY ns17-5: arming is per (store, step), but only `vectors_maintain` has an arming owner; open item 4's "CLI-only pending a ruling" ignores d8g {#ns17-5}

- **The other steps would only ever dry-run.** 17.2 R7 makes every unarmed (store, step) dry-run
  only, and only 17.3 arms anything (`--step vectors_maintain`, the default). 19.4's compile step,
  plan-18's DuckDB step and 17.4's backup step (added at `c2e201a`) would dry-run forever. 19.4
  AC-2 asserts that the compile step "runs once per scheduled day" without arming it, so either
  19.4 fails or 17.2's per-step rule is bypassed.
- **d3d has a scope.** d3d was about vectors maintenance, where an unarmed real run deletes.
  Whether it applies to a non-destructive step, such as 17.4's copy, is a per-step property that
  nobody states.
- **d8g already ruled on the verb class.** Open item 4 says the CLI-only class is "unowned
  … pending that ruling". d8g ruled on it: "one verb on both surfaces (parity test holds) … The
  gate is the manifest, not the surface". The project constraint is also "every capability … is a
  verb first". A CLI-only `rmx hub maintain arm` violates both. And an agent running 17.3 arms
  through Bash anyway (dlr #s-5).

**Fix:**
- `hub_maintain_arm` becomes a verb on both surfaces. It refuses unless given the `run_id` of a
  successful non-dry hand run of that (store, step) recorded in `maintain.json`.
- Each registered step declares `requires_arming: bool`. vectors: true. Compile, plan-18 and 17.4
  state their own value, with a reason.
- 17.3 arms only the steps it hand-ran.

Open item 4 is then settled by the spec, not by the user.

### SKETCHY ns17-6: 17.3's latency and no-match ACs have no input {#ns17-6}

- **No live store qualifies.** The fleet's `code.lance` datasets were compacted on 10-07 and regrow
  at about 25-37 versions per day. cliquet had 4,941 versions summed over ALL datasets. No live store
  will have ≥ 10k `code.lance` versions at rollout.
- **The named fallback does not exist.** The fallback is "a 2026-10-07
  `vectors.bak-20261007-precompact` if one still exists". It does not exist: `find -maxdepth 3 -name
  'vectors.bak*'` under cliquedb, viascope, this repo and `~/refmatrix` returns nothing.
- **So the ACs are unrunnable.** AC-2 (latency ≤ 1/5) and AC-3 (0 versions on a 61k clone) will be
  waived at rollout, which is the pattern r1 #s-4 flagged.

**Fix:** make a synthetic clone the stated default. Copy one store's `vectors/` into a short
`mkdtemp()` root off the watched trees, and commit 30,000 single-row upsert/delete cycles to
`code.lance` with Lance directly. Record the version count, then measure. Real stores give only
the per-store before/after table.

### MEH nm17-1: the `status=True` and single-flight checks must not take `_store_lock` {#nm17-1}

Ops run on `bg_pool` (12 threads, `daemon.py:1820`). A `vectors_maintain(status=True)` or a
second call that took `_store_lock` would queue behind the 19 s dataset hold. 17.2's 30 s poll
would then time out, and the call would not "return immediately" (R11). State that both are
lock-free reads of an in-process run state.

### MEH nm17-2: small contract gaps {#nm17-2}

- 17.2 R3's `skipped:not_supervised` cannot be reached: every root comes from a plist by
  construction. Drop it, or define it.
- Plan-17 #option-a-revisit is binary (GO / NO-GO), while 23.4 has three verdicts. Add a sentence
  that GO-serial means 17.1 keeps `bind`.
- 17.1 AC-2's `compact` seam is an in-process routine parameter, not a daemon-op argument, because a
  callable cannot cross the JSON socket. Say so.

### MEH nm17-3: the vectors half of restore-across-plans is unowned on plan-22's side (open item 3) {#nm17-3}

17.1 R6 made the orphan list a stable format. `task-22.2` at `32dde06` mentions neither the orphan
list nor `vectors_restore`. dlr #s-7 asked for 22.2's restore AC to include vectors. The spec can
settle this: 22.2's restore calls `vectors_restore` over the orphan lists whose ids it restores.
The ADR-0004 sentence that scopes derived-vector reaping as restorable maintenance is an ADR
amendment, which follows the usual ADR approval.

### MEH nm17-4: 17.4 landed after `32dde06`, unreviewed {#nm17-4}

`c2e201a` adds task 17.4 to plan-17 without a revision-table row, and it inherits [[#ns17-5]].
It needs the next round.

{#findings-17-body}

## Cross-plan consistency {#cross-plan}

| question | answer |
|---|---|
| 17.2's registry = 23.1's tick registry? | **No.** Different process, signature and budget scale. 23.1 R6.4 already excludes `bounded_steps` ops. The specs settle it ([[#ns17-1]]). |
| 23.1 `bind` as consumed by 17.1 | Mismatched: `bind(batch)` vs `bind(partition_name)`; id vs name ([[#ns17-2]]). Both inherit [[#nb23-1]]. 17.1 writes no fragments, so the cache bug does not bite it directly. |
| recorder names (`HoldRecorder`, `recorded_daemon`, `lock_free_during`, `max_lock_hold`, `max_writes_per_*`) | Consistent across 23.2, 23.1, 23.3 and 17.1, except 17.1 AC-4's misuse of `lock_free_during` ([[#ns17-2]]). |
| `bounded_steps` | Named by plan-23 #consumers and by 22.2; never named by 17.1 ([[#ns17-2]]). |
| `retries=0` / single-flight | Consistent: 17.2 R4 + AC-6 (the default `retries` is a mutation), 17.1 R11, 19.4 R1 + its mutation. |
| per-hold seconds | 17.1 R7 and 17.3 R2 need them; 23.1 provides only `max_hold_s` ([[#ns17-2]]). |
| arming | 17.2 R7 per (store, step) vs 19.4 AC-2 and 17.4, which never arm ([[#ns17-5]]). |
| 23.4 GO / GO-serial / NO-GO vs the plan-17 revisit | Compatible in effect; plan-17 should name GO-serial ([[#nm17-2]]). |
| Option A's "Store-state audit" | Must include the fragment cache ([[#nb23-1]], [[#ns23-1]]). |

{#cross-plan-body}

## Open-after-revision items: classification {#open-items}

### plan-23 {#open-23}

1. **23.4's numbers.** This is a **user decision**: AC-1 requires the user's confirmation. But
   amend the ranges first ([[#ns23-1]]): fragment rows in the workload, binding removal decoupled
   from throughput, and an error at N=1 treated as an invalid run.
2. **d2a for learn (segment coalescing).** This is **not a user decision as framed.** Its premise
   is false ([[#nb23-2]]). The spec settles it: insert-if-absent evidence (recommended; it also
   fixes today's duplication), or window scope.
3. **d8d predicate owner.** The **spec settles it**: `telemetry.py` ([[#nm23-2]]).
4. **Dead-lettering.** The **spec settles it**: counted, retained forever, and re-drivable
   ([[#nm23-1]]). It is already consistent with #no-silent-failures, so no new user rule is needed.
5. **bug-093 op-start line.** The **spec settles it**: 23.3 R7 plus an AC. Until then it is an
   unanchored deferral ([[#nb23-4]]).

### plan-17 {#open-17}

1. **Same registry?** The **spec settles it**: no ([[#ns17-1]]).
2. **Bulk orphaning above the cap.** The **user confirms the form**; the spec proposes it. Reap
   refusal no longer blocks compaction, and the release is `--confirm-orphans <dry-run list hash>`
   (d8g's shape). This must be settled before 17.3, because the plan's own 559/5,495 example trips
   the cap ([[#ns17-3]]).
3. **Restore across plans.** The **spec settles it** on plan-22's side (22.2 calls `vectors_restore`).
   The ADR-0004 scoping sentence needs the user's usual ADR approval ([[#nm17-3]]).
4. **`hub maintain arm` verb class.** **Already ruled by d8g**: one verb on both surfaces, gated by
   a hand-run `run_id` ([[#ns17-5]]). It is a user decision only if the user wants to overturn d8g
   for this verb.

{#open-items-body}

## Verdict {#verdict}

**plan-23: NEEDS-REVISION.** 10 new findings: 4 BULLSHIT (nb23-1..4), 2 SKETCHY (ns23-1, ns23-2),
4 MEH (nm23-1..4). Prior: 11 closed, 2 partial (b-1 and b-2, each reopened by a new BULLSHIT). The
revision answered r1 thoroughly, and the harness's shape is right. But:
- `bind` leaves half the binding outside the seam, and the live store already shows the damage;
- the learn consumer's exactly-once rests on a false idempotence claim;
- 23.3 converts a crash into silent semantic loss.

**plan-17: NEEDS-REVISION.** 10 new findings: 0 BULLSHIT, 6 SKETCHY (ns17-1..6), 4 MEH
(nm17-1..4). Prior: 17 closed, 2 partial. Every r1 BULLSHIT is closed with an AC that can fail. What
remains:
- the contracts with 23.1 (registry, `bind`, `bounded_steps`, hold seconds);
- a cap that blocks compaction on the plan's own example;
- an unbounded `still_running`;
- per-step arming;
- rollout ACs with no input.

All of these can be settled by the spec except the form of the cap release.

**Totals:** 20 new findings (4B / 8S / 8M). {#verdict-body}

## Ledger entries (to merge) {#ledger}

INDEX.md row:

```
| 32dde06 (plan-23 + plan-17 SPEC re-review r2: 23.0-23.4, 17.1-17.3; HEAD moved to c2e201a = new task 17.4, unreviewed; written 2026-10-14T12:46:22-0700) | 2026-10-14 | Todd Holley / Opus 5.5 / orchestrator | DIRTY | 20 new (4B/8S/8M); prior 23: 11 closed/2 partial, 17: 17 closed/2 partial, dlr: 10 closed/1 partial | [[bsd-plan23-17-spec-rereview-32dde06]]. plan-23 NEEDS-REVISION: nb23-1 bind binds _partition_id but Store._fragments is keyed by linkage only and with_partition never swaps it (probe: pb row gets tmp's bit and back; LIVE snapshot copy: sessions-refmatrix mentions 195,003/422,811 bits are other-partition entities, imports 2,364/2,410), AC-3 checks rows only; with_partition auto-creates vs R1.2 raise; unlogged (bug-105). nb23-2 learn declared idempotent but add_evidence is a plain INSERT, no key (probe: 2 learns → 4 rows); AC-5 crashes before any apply. nb23-3 23.3 stamps mtime in the per-file step before semantics → crash/cancel/budget = semantic links purged and never re-applied; AC-5 asserts it. nb23-4 bug-093 op-start line unowned (9a). S: 23.4 ranges omit bitmap_fragments (the hottest row) and couple binding-removal to throughput; 23.0 AC-4 size/mtime of live repo logs (changed 12:42/12:43 during the review). plan-17 NEEDS-REVISION: S: 17.2 registry ≠ 23.1 tick registry (17.2 depends on an interface 23.1 lacks); 17.1 bind(batch)/ids/per-hold seconds/no bounded_steps vs 23.1; cap refuses the plan's own 559/5,495 and blocks compaction; still_running unbounded (wedge = no alert, fleet starves); per-step arming owned only for vectors (19.4/plan-18/17.4 dry-run forever), d8g already ruled verb class; 17.3 latency/no-match ACs have no input (no ≥10k store, no 10-07 backups). |
```

last_run.log (one line):

```
2026-10-14T12:46:22-0700 commit=32dde06 verdict=DIRTY findings=20 (4B/8S/8M) report=2026-10-14-1246-plan23-17-spec-rereview-fragment-cache-unbound-and-learn-not-idempotent-32dde06.md
```

IMPRESSIONS.md bullets:

- 2026-10-14 (plan-23/17 r2): A BINDING IS EVERY CACHE KEYED BY IT. bug-098's fix restored
  `_partition_id`, and the r2 `bind` seam did too. `Store._fragments` is keyed by linkage alone and
  survives every `with_partition`. The live snapshot shows 195k foreign bits in one sessions row.
  For any partition, tenant or binding fix, enumerate the instance attributes the bound id
  parameterizes, and demand an AC on each one's PERSISTED form, not only the rows.
  {#imp-binding-is-every-cache}
- 2026-10-14 (plan-23 r2): AN "IDEMPOTENT" FLAG IS A CLAIM. Read the INSERT and the DDL before
  accepting it. Learn's evidence write has no key, so a replay duplicates. My own r1 asserted the
  opposite, and the revision inherited my error. Run the replay twice in a tmp store; it takes 10
  lines. {#imp-idempotent-is-a-claim}
- 2026-10-14 (plan-23 r2): CHUNKING A TRANSACTION MOVES THE STAMP. When a single-transaction loop
  is split into steps, ask which step writes the "done" marker (the mtime) and whether a later step
  still owes work for that item. 23.3 stamped in step 1 of N. {#imp-chunking-moves-the-stamp}

Proposed impression memory: `impression_bsd_binding_is_every_cache` (type impression, tags
`[impression, ch-bsd, partition]`). Its lead line: a binding fix that restores the id but not the
caches keyed implicitly by it leaves the bug class live. Check the persisted form per cache. This
is a new pattern, the 4th instance of the bug-098 class.

Recommended bug row (the orchestrator files it; I did not edit the registry): **bug-105**.
- **Symptom:** the `Store._fragments` / `_dirty_fragments` cache is partition-agnostic across
  `with_partition`. The census numbers above are the evidence.
- **Files:** `store.py:1055`, `:1911`, `:4092`, `:4156`.
- **Fix:** an owner in 23.1 plus a derived fragment rebuild from `entity_links`.

rel: related-to -> [[impression_bsd_guard_cannot_fire]]
