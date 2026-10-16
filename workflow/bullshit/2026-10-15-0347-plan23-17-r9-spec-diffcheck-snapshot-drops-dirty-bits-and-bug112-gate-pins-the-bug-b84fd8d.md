---
gmd: "0.1"
id: bsd-plan23-17-spec-diffcheck-r9-b84fd8d
title: "plan-23 + plan-17 spec diff check r9: 10 of 11 r8 findings closed (one carries residue: nm23-r8-3, the bug-112 gate). 23.1, 17.1, 17.2 and 17.3 are ready. 23.5 still has two BULLSHIT findings. (1) Its freshness promise is false for bitmap reads: the snapshot never flushes dirty fragments, and AC-7 checks only a relational count. (2) Its bug-112 gate pins the bug as passing, and the bound it states for overlapping readers is false. 17.4's strict fold fails on the torn last line that the probe tolerates."
severity: BULLSHIT
plan: plan-23-bounded-write-harness
task: spec-diffcheck-r9-23.1-23.5-and-17.1-17.4
round: 9
tags: [bsd, audit, spec-review, diff-check, plan-23, plan-17, read-path, bitmap-freshness, bug-112, cross-plan, restore, wave-1]
---

# ch-bsd spec diff check r9 of plan-23 and plan-17 {#root}

**Revision reviewed:** `9dd923c` (round 8, `git log -1 -- workflow/plans/plan-23-bounded-write-harness.md`).
It was diffed against `23ad703` for `workflow/plans/plan-23-*`, `workflow/plans/plan-17-*`,
`workflow/bug_registry.md` and `workflow/plan-review-2026-10-14.md` (d9bn).

**HEAD at write time:** `b84fd8d` on `wave0-spec-reviews`. `29e335a` (plans 16/22) and `b84fd8d`
(the plan-18 rewrite) landed during the run. Neither touches the plan-23/17 files or `src/`. The
cross-plan check below reads 18.2/18.3 as committed at `b84fd8d`. `src/` is 0.78.3, unchanged
since `23ad703`. **Written:** 2026-10-15T03:47:10-0700.

**Method.** Read only: no plan or source edit, and no live store or socket.
- A transitive AST walk over `daemon.py` started at every `CLI_OPS` handler. It followed
  same-module functions and `d.`/`self.` `Daemon` methods to a fixpoint (scratchpad `walk.py`).
- DuckDB 1.5.2 (`.venv-eval`) was probed on a scratch file to check how the instance cache
  behaves under overlapping readers (scratchpad `chain.py`).
- The bug-112 fix branch (`/Volumes/littlebig/refmatrix-bugs112-118`, uncommitted) was read, not
  run.

rel: derives-from -> [[bsd-plan23-17-spec-rereview-r8-23ad703]]
rel: related-to -> [[plan-review-2026-10-14]]
rel: specifies -> [[plan-23-bounded-write-harness]]
rel: specifies -> [[plan-17-nightly-store-maintenance]]
rel: contradicts -> [[claude#no-silent-failures]]

## Claims verified at HEAD {#verified}

| claim in round 8 | result |
|---|---|
| The transitive walk flags 24 of the 31 `CLI_OPS` | **Reproduced exactly.** The same 24 are flagged: the 15 direct `with d._store_lock`, `snapshot` via `_snapshot_catalog:2700`, and 8 bare `_read_with_fallback` handlers (`context` and `memory_recall` appear in both lists). Clean: `ingest_gmd_status`, `mem_mirror_status`, `ping`, `replica_refresh` (a no-op, rotation dropped), `replica_relink`, `replica_status`, `stop`. |
| `_cli_read` with a required `writer_wait_s` and `WriterBusy` | Consistent with `_read_with_fallback` (`:4895`) and `_writer_lock` (`:4996`). A bounded `LookupError` is raised at both lock sites (`:4957`, `:4975`). A bare call becomes a `TypeError`. Its mutations (AC-1, AC-3) FAIL as stated. |
| `MIRROR_OPS` starts empty | It is consistent, but it makes every cli read private. This is what turns bug-112 into a load-bearing dependency ([[#nb23-r9-2]]). |
| `_op_ctx` thread-local on the worker | Matches HEAD: `run` executes on the worker (`:3240-3248`) and `expires` lives only in its closure. The plumbing is sound, and AC-2's 0.5 s deadline mutation FAILS. |
| `_inflight_ops` is extended | The registry is real (`:787`, `:3250-3267`, `_final_flush` `:1520-1541`). The value change misses a second reader and the tests ([[#nm23-r9-1]]). |
| `_FairLock.holder()` | `_FairLock` (`:247`) has no owner at HEAD. 23.1 R1.6 item 1 adds `_owner`, and R4's `_owner_since` builds on it. There is a hand-off window ([[#nm23-r9-3]] a). |
| `_snapshot_catalog(pin_to=)` and the ts-order invariant | Feasible at HEAD. L0 can be read inside `_store_lock` (`:2700-2721`), and `os.link` can run before `_snapshot_lock` (`:2692`) releases. The replay sort `store.py:7941` is verified. AC-5's four mutations FAIL. The snapshot itself drops dirty bitmap bits ([[#nb23-r9-1]]). |
| 17.4 strict-fold verify | `cli.py:9797-9800` prints `  <key>: <value>`, and bug-117's counters exist. The legacy two-kind fixture resolves to `None`, giving `links_unresolved: 1`, so the discrimination is real. The torn-tail interaction is new ([[#ns17-r9-1]]), and so is the op drift ([[#ns17-r9-2]]). |
| bug-119 row | `rebuild_index_from_log` `:7936-7940` and `apply_log_delta` `:7751-7754` are both verified. However, `apply_log_delta` has NO production caller ([[#nm-x-r9-1]]). |
| 23.1 ns23-r8-4 (spy plus Store-level case) | **Closed.** `Store.close()` at HEAD swallows the flush error and then closes `_duck_view` and `_conn`. Both new mutations FAIL: swallow means no raise, and re-raise-before-close means `_conn` is still open. The spy's `rmxd-close` record exists even after `_final_flush`, because `close()` always calls `flush_fragments()`. |
| 17.1 nm17-r8-1 | **Closed.** `socket.connect` audit events carry the AF_UNIX path, and the flag-gated hook is sound. |

{#verified-body}

## Round-8 findings: status {#prior-status}

| id | status |
|---|---|
| nb23-r8-1 (helper-reached lock) | **closed** (helper, 10 sites, `snapshot` to bg, R7 to a fixpoint; 24/31 verified). Residue: R7 recognises only one lock spelling ([[#nm23-r9-2]]). |
| ns23-r8-1 (`_store_health`) | **closed** (three steps; health off the writer connection; AST check). Residue: the mutation hangs rather than fails ([[#nm23-r9-3]] b). |
| ns23-r8-2 (mirror use-lock) | **closed** (`MIRROR_OPS` by p99; AC-1b). |
| ns23-r8-3 (R2 plumbing, writes) | **closed** (d9bn ruling 4; `_op_ctx`). |
| nm23-r8-1 (ts order, hold 1) | **closed** (`pin_to`, order invariant with a logged refusal). Residue: liveness ([[#nm23-r9-3]] d). |
| nm23-r8-2 (thread, accessor, AC-6, registry) | **closed**. Residue: readers ([[#nm23-r9-1]]). |
| nm23-r8-3 (AC-7 branch, bug-112) | **branch closed; the bug-112 gate is wrong** ([[#nb23-r9-2]]). |
| nm23-r8-4 (drift) | **closed** (cited by symbol; open item 8 SETTLED). |
| ns23-r8-4 (23.1 AC-20) | **closed**. |
| ns17-r8-1 (17.4 verify) | **closed in text**. Residue: [[#ns17-r9-1]], [[#ns17-r9-2]]. |
| nm17-r8-1 (17.1 AC-13) | **closed**. |

{#prior-status-body}

## Findings: task 23.5 {#findings-235}

### BULLSHIT nb23-r9-1: moving reads to the snapshot makes bitmap reads stale with no bound, because the snapshot never flushes dirty fragments; R1.8's freshness contract is false, and AC-7 checks only a relational count {#nb23-r9-1}

**Where:**
- R1.3 moves `query`, `grep_indexed`, `derive_*`, `partition_*` and `stats` off the writer.
- R1.8 promises "Mirror and snapshot reads are at most `RMX_SNAPSHOT_DEBOUNCE_MS` behind the
  writer plus one refresh".
- AC-7's first bullet is "A `link` through a daemon op, then `stats`".

**Evidence at HEAD:**
- `Store.link` (`store.py:4622`) sets the bit in the in-memory fragment cache and adds the
  linkage to `_dirty_fragments` (+19..+24). It flushes nothing. `_op_link` (`daemon.py:6156`)
  runs it under `_store_lock` with no transaction, then calls `_request_snapshot()`.
- Fragments reach disk only in three ways:
  - at a transaction's COMMIT (`store.py:4562-4566`);
  - from the periodic tick, every `RMX_DAEMON_FLUSH_S` = 30 s (`_periodic_flush`, `daemon.py:232`);
  - at close.
- `_periodic_flush` does not request a snapshot.
- `_snapshot_catalog` (`:2700-2721`) runs `CHECKPOINT` plus a file copy, with no
  `flush_fragments()`.
- So the snapshot taken 250 ms after the `link` holds the `entity_links` row but not the bit.
  The bit reaches the snapshot only at the next snapshot after the next flush, which needs
  another write. With no further write, that never happens.
- `QueryEngine` reads only bitmaps (`query.py:258-337`, `self.s.load_bitmap`). At HEAD
  `_op_query` runs on the writer, whose cache holds the dirty bit, so it is fresh today. After
  23.5 it is stale with no bound.
- `Store.stats` counts `entity_links` rows (`SELECT COUNT(*) … FROM entity_links`), so AC-7 passes
  on the broken path.
- plan-18 already knows this. 18.3's hold step 1 is `st.flush_fragments()` because "dirty bitmap
  fragments are in memory, and the COPY reads tables" (`task-18.3…:222`, at `b84fd8d`).
- The same gap exists today for the mirror-served `context` and `memory_*` reads. 23.5 extends it
  to every bitmap read and certifies the extension as a freshness contract.

**Fix (spec text):**
- **R5.1 / new R1.9:** inside `_snapshot_catalog`'s `_store_lock` hold, before `CHECKPOINT`, run
  `if self.store.has_dirty_fragments(): self.store.flush_fragments()`. It runs under the lock, so
  23.1 R1.6's check holds.
- **Cross-plan:** the same line goes into 18.2's `CatalogHold.snapshot()` body (R8/R11 port).
  State this in 18.2's text, not only here.
- **AC-7 adds:** with `RMX_DAEMON_FLUSH_S=3600`, a `link` op, then `query "<linkage>:<concept>"`
  must return the entity within `RMX_SNAPSHOT_DEBOUNCE_MS` + 1 s. The same holds for
  `grep_indexed` on a learned hit.
- **Mutation:** the snapshot without the flush FAILS (the entity is absent).
- **R8's census** records, per op, whether the op reads bitmaps.

**Pattern match:** YES. This is `#imp-consolidated-0914`, "guards built for the fixed state": the
AC samples the one counter the defect cannot move.

rel: contradicts -> [[claude#no-silent-failures]]

### BULLSHIT nb23-r9-2: the bug-112 gate pins the bug as passing, and R1.8's bound for overlapping readers is false; with `MIRROR_OPS` empty, every cli read is exposed {#nb23-r9-2}

**Where:** R1.7 (the set starts empty), R1.8 ("its freshness is bounded by the oldest
overlapping private reader"), AC-7 ("bug-112, pinned as the known exception … B' returns A's
database … bug-112's fix owns inverting this assertion"), the 23.5 header and plan-23
`#dependencies`.

**Evidence:**
- **Measured on DuckDB 1.5.2** (`.venv-eval`, a scratch file). Sequence:
  - A opens; the file is replaced (2); B opens while A is open and sees 1.
  - A closes; the file is replaced again (3); C opens while B is still open and sees **1**.
  - B closes; D opens while C is open and sees 1. Only E, opened after every reader had
    closed, sees 3.
  - So staleness is bounded by the end of a continuous chain of overlapping readers, not by the
    oldest reader. Under hook load (4 cli workers, seven agents) such a chain can last
    indefinitely.
- **Every cli read is now private:** R1.7 leaves `MIRROR_OPS` empty until the census, so every
  cli read opens `catalog.read.duckdb` privately. At HEAD the memory reads go through the mirror,
  which re-ATTACHes on each refresh and is never stale this way. 23.5 therefore regresses their
  freshness from one debounce to unbounded.
- **The fix in flight inverts AC-7's pin:**
  - The fix (`bugs-112-113-118`, uncommitted: `backend.open_duckdb`) opens read-only through a
    private `:memory:` ATTACH. B' then reads the new file, so AC-7's pinned assertion goes RED.
  - That fix is being built now, ahead of Wave 1, and d9bp / 18.3 already gate on it (header
    "bug-112 FIXED and reachable from `master`").
  - As written, 23.5 asserts the bug at implementation time. Its REQUIRED half (A closes before
    B opens) does not exercise the chain.

**Fix (spec text):**
- Add a 23.5 header and plan-23 `#dependencies` entry: "**bug-112 FIXED and reachable from
  `master`**", in the same form as bug-115/116 and 18.3's header.
- Delete R1.8's "Known exception" sentence. Replace it with: "private reads open through
  `backend.open_duckdb` (bug-112's fix); each open reads the file at the path now."
- AC-7 has three parts:
  - **Positive:** B', opened WHILE A is open after a forced snapshot, sees the new link.
  - **Chain case (the sequence above):** C sees the newest file.
  - **Mutation:** a private open through bare `duckdb.connect(path, read_only=True)` FAILS (the
    chain case reads 1).
- Delete the "pinned as the known exception" bullet.

## Findings: task 23.5 (continued) {#findings-235b}

### SKETCHY ns23-r9-1: the cross-plan interface binds only one side; 18.2/18.3 at `b84fd8d` carry none of 23.5's obligations, and compaction ownership bounces between the plans {#ns23-r9-1}

At `b84fd8d` (the plan-18 rewrite):
- **(a) Holder registration and the alarm.** 23.5 R4 says `_catalog_hold` "registers its holder
  through `Daemon._inflight(<step name>)`" and has "no second alarm". 18.2 R11 never mentions
  `_inflight` and specifies its OWN line: "One `rmxd.log` line is written for any hold over D1's
  2 s edge" (`task-18.2…:323`). Two alarms at two thresholds, and the registration exists only
  on 23.5's side.
- **(b) The snapshot port.** 23.5 R5 says `pin_to` / L0 "is part of the snapshot port's
  contract". 18.2 R8 says instead: "The snapshot's behaviour does not change". `CatalogHold.snapshot()`
  returns no L0, and 18.2's `after` callbacks run after the release.
- **(c) Compaction ownership bounces.**
  - 23.5 R5: "18.2/18.3's port list gains the compaction site".
  - 18.3 R8: "**Not ported** … 23.1 owns it".
  - 18.3 Q-C: "as a 23.1 or 23.5 amendment, not here".
  - Each plan assigns the port to the other.
- **(d) A dependency edge that would block Wave 1.** 23.5 has `rel: depends-on ->
  [[task-18.2-catalog-maintain-step]]`. plan-23 `#dependencies` does not list 18.2, R5 makes it
  conditional ("when 18.2 is merged before 23.5"), and plan-18 is Wave 4 (`#t10-waves`). Read
  as written, the edge blocks a Wave 1 task on Wave 4.

**Fix:**
- 23.5 stands alone. Compaction stays on `with self._store_lock:` under
  `Daemon._inflight("compact")`, and `pin_to` lives on `_snapshot_catalog`.
- Change the `depends-on` edge to `related-to`.
- Write the obligations INTO 18.2 R11 / R8:
  - `_catalog_hold` enters `Daemon._inflight(label)`;
  - the snapshot port keeps `pin_to`, with L0 read and the link made inside the body, and the
    dirty-fragment flush from [[#nb23-r9-1]];
  - the 2 s line is either R4's `lock hold:` alarm with a per-label threshold, or 23.5 R4 names
    both lines.
- 18.3 R8's "Not ported" becomes "ported by 18.3: 23.5 R5's compaction (hold 2) moves onto the
  helper; 18.3 lands later and owns the port". Q-C is then closed.
- Since 18.2/18.3 are being rewritten now, the plan-18 reviser should carry this.

### SKETCHY ns23-r9-2: "writer busy" is untyped on the wire; the verb layer turns it into a generic `VerbError`, not the `VerbBusyError` that exists for exactly this {#ns23-r9-2}

- After 23.5, `writer busy:` is a routine answer from 22 read sites plus `replica_audit`.
  `Daemon._handle` returns `{"ok": false, "error": <message>}`.
- `verbs._call` (`verbs.py:207-221`) maps any `ok: false` to plain `VerbError`. `VerbBusyError`'s
  docstring names "holding the writer lock" and says callers must "retry or report; … NEVER treat
  it as absent", and `require_daemon` types busy so that "no caller string-matches a message".
- The same applies to 0.78.2's `deadline exceeded`.
- MCP clients and hooks therefore see an untyped error and cannot retry correctly.

**Fix:**
- R1.1 adds `"code": "writer_busy"` (and `"deadline"` for `DeadlineExceeded`) to the refusal
  response. `verbs._call` raises `VerbBusyError` when `code` is one of them.
- **AC-2 adds:** `rmx_memory_search` through the MCP adapter, on an absent partition during the
  hold, yields the busy class, and no client-side `Store(` open happens.
- **Mutation:** the code dropped from the response FAILS (a plain `VerbError`).

### MEH nm23-r9-1: the 3-field `_inflight_ops` value misses a second reader and the tests; tick entries break an existing assertion {#nm23-r9-1}

- R4 names only `_final_flush`'s reader. `_drain_pool`'s log at `daemon.py:1578-1579` does
  `for op, _t0 in self._inflight_ops.values()`, which raises `ValueError` on a 3-tuple during
  shutdown.
- These tests unpack or build 2-tuples: `tests/test_inflight_registry.py:67, :91, :169-170, :196`
  and `tests/test_daemon_shutdown_drain.py:148`.
- `test_inflight_registry.py:151` asserts `_inflight_ops == {}` after an op. A `snapshot` tick
  entering `Daemon._inflight` after that op's write makes it flaky.

**Fix:**
- The value becomes a `NamedTuple InflightEntry(op, t0, ident, kind)`, read by attribute.
- The files table lists both readers and the two test files.
- The `== {}` assertion filters to `kind == "op"`.

### MEH nm23-r9-2: R7 recognises the lock by its spelling, so a lock passed as an argument escapes {#nm23-r9-2}

- R7 fails `with <x>._store_lock` and `<x>._store_lock.acquire(`. HEAD already passes the lock as
  a value: `_periodic_flush(self.store, self._store_lock, self._log)` → `with lock:` (`:232-238`).
  23.1's `bounded.py` front-ends will take it the same way.
- So a cli op calling `_periodic_flush(d.store, d._store_lock, d._log)` passes R7 and parks a
  worker. This is nm23-r7-1's shape again.

**Fix:** R7 also fails any reachable call that passes `<x>._store_lock` as an argument, except to
`_writer_lock`. **Mutation:** that `_periodic_flush` call added to `_op_list_linkages` FAILS.

### MEH nm23-r9-3: four small gaps (hand-off window, a mutation that hangs, the clamp's inputs, refusal liveness) {#nm23-r9-3}

- **(a) Hand-off window.** 23.1 sets `_owner` in the woken waiter after `ev.wait` returns,
  outside `_mu`. Between `_pass_or_release_locked` clearing the owner and the waiter setting it,
  `holder()` reads `_held=True, _owner=None`, so `writer_holder` is null, contrary to R4's
  "never null".
  - Fix: `_waiters` holds `(ev, ident)`, and `_pass_or_release_locked` sets
    `_owner, _owner_since` to the waiter's ident under `_mu`.
- **(b) A mutation that hangs.** AC-6's "`_store_health` inside the outer `fn`" mutation
  deadlocks a worker forever on the non-reentrant `_use_lock`, so the test hangs at teardown
  instead of failing (`feedback_mutation_must_fail_not_hang`).
  - Fix: a test seam makes the mirror's use-lock acquire bounded (2 s, then it raises), or the
    case runs in a killable child.
- **(c) The clamp's inputs.** `HEARTBEAT_INTERVAL_S` and `HEARTBEAT_STALE_S` are read at import
  (`:63`, `:66`), while the heartbeat thread re-reads `RMX_HEARTBEAT_S` at start (`:1331`).
  - Fix: R6's clamp and the heartbeat read their inputs through ONE start-time function, which
    AC-8 checks against the test env.
- **(d) Refusal liveness.** One catalog row whose `updated_at` lies past every tail event's ts
  (an import, or a clock step back) refuses EVERY compaction while the tail is non-empty, which
  under load is always.
  - Fix: count consecutive `ts-order` refusals, add `factslog_compaction_refused: <n>` to
    `stats(include_health)` and make it a hub hot row, so the refusal is never silent across
    ticks.

{#findings-235b-body}

## Findings: plan-17 and the registry {#findings-17}

### SKETCHY ns17-r9-1: 17.4's strict fold fails on the torn last line that the parse probe tolerates; after a crash, every (c) restore falls back to the day-old backup {#ns17-r9-1}

- R6 step 3 of the probe accepts a live log whose final line is torn ("a torn final line is
  ignored, as R3 cuts a copy").
- Step 2 copies `<source>` WHOLE into the throwaway.
- The new step-3 fold "parses every line STRICTLY and fails on a non-JSON line". The rebuild
  silently skips the torn line (bug-119), but the fold fails, so verification fails and (c)
  falls back to `backups/facts.log.daily`.
- A crash mid-append is the likeliest way a catalog and a log tail are lost together. That is
  exactly the loss ns17-r6-1 closed.

**Fix:**
- Step 2 copies `<source>` cut at its last newline (R3's rule), and prints `cut <n> torn
  byte(s)`. The rebuild and the fold both run on the cut copy.
- **AC-9's main (c) run** ends its live log with a torn half-line, and must print `source:
  live` and the cut.
- **Mutation:** an uncut copy FAILS (`source: backup`).

### SKETCHY ns17-r9-2: the independent fold diverges silently when replay gains an event op; plans 16/22 add six in Wave 1 {#ns17-r9-2}

- Replay at HEAD handles `entity`, `tombstone`, `protect`, `noise`, `link`, `unlink`,
  `evidence`, `track`, `untrack`, `memory_content` and `linkage_type` (`store.py:7969-8027`).
- d9bl adds `evidence_remove`, `evidence_repoint`, `evidence_orphan_drop`, `learned_provenance`
  and `learned_provenance_move` (plans 16/22, Wave 1, after 17.4).
- A fold written today over-counts evidence on any log carrying them, so every (c) restore after
  22.x lands fails verification and loses the day.

**Fix:**
- A test pins the fold's handled-op set to replay's dispatch set (an AST read of
  `rebuild_index_from_log`'s `op ==` / `op in` branches). Adding an op then fails CI, not a
  restore.
- The script prints, and fails on, any op the fold does not know, naming it.
- Plan-22's task files tables list `scripts/factslog-restore.py` beside each new op.

### MEH nm-x-r9-1: the bug-119 row names a dead path as live and plans a fix that a torn tail would break; 17.4 parses rich console output {#nm-x-r9-1}

- **A dead path named as live.** bug-119 calls `apply_log_delta` "the rotation delta replay".
  Rotation is dropped (`_refresh_replica_now` is a no-op, `daemon.py:2862`), and
  `apply_log_delta` has no production caller: only `daemon.py:516`'s comment and two tests
  mention it.
  - Fix: the row names it dead (delete it with `REPLICA_REBUILD_DELTA_BYTES`, or keep it
    test-only) and scopes the fix to `rebuild_index_from_log`.
- **The planned fix and a torn tail.** "`rmx rebuild --from-log` exits non-zero when
  [unparseable lines] above 0" must separate a torn FINAL line (no trailing newline: a crash
  mid-append, reported as `tail_torn_bytes`, exit 0) from a corrupt INTERIOR line (exit
  non-zero). Otherwise every rebuild after a crash fails.
- **Parsing rich output.** 17.4 step 3 parses `console.print` output (`cli.py:9798-9800`),
  which rich may wrap or mark up. This is the r3 "renderer ate the wikilinks" precedent.
  - Fix: `rmx rebuild --from-log --json` prints the result dict, and the script parses that.

{#findings-17-body}

## Approval readiness {#approval}

| task | verdict | what remains |
|---|---|---|
| 23.0 / 23.2 / 23.4 | approved / approved / ready | unchanged |
| 23.1 | **READY** | none; ns23-r8-4 and nm23-r8-4 are closed and verified |
| 23.3 | **READY** | unchanged |
| 23.5 | **needs one edit pass** | nb23-r9-1 (flush in the snapshot hold, plus a query freshness AC); nb23-r9-2 (depend on the bug-112 fix merged, invert AC-7); ns23-r9-1 (write the obligations into 18.2/18.3, `related-to` edge); ns23-r9-2 (typed refusal); nm23-r9-1..3. The design is sound: every d9bn ruling checks out against `src/`, and the 24/31 count is exact |
| 17.1 | **READY** | none |
| 17.2 | **READY** | none |
| 17.3 | **READY** | none (cites verified at `23ad703`) |
| 17.4 | **needs a small edit** | ns17-r9-1 (cut the copy at the last newline); ns17-r9-2 (pin the fold's op set); the `--json` parse from nm-x-r9-1 |

**The bug-112 question.** 23.5 does NOT gate on bug-112 correctly. It gates only on the
sequential case, and it pins the overlapping case as acceptable with a bound that measurement
shows is false. With `MIRROR_OPS` empty, every cli read goes through that path. The right gate
is the same one 18.3 uses: bug-112 FIXED and reachable from `master` before 23.5 is
implemented.
{#approval-body}

## Verdict {#verdict}

**DIRTY. 10 findings (2 BULLSHIT, 4 SKETCHY, 4 MEH).**
- Round 8 closed 10 of 11 r8 findings in text. nm23-r8-3 closed its branch, but its bug-112 gate
  is wrong ([[#nb23-r9-2]]).
- Both BULLSHIT findings are in 23.5's freshness contract. Neither is a design change: one is a
  single line in the snapshot hold plus an AC that reads a bitmap, the other a dependency row
  plus an inverted AC.
- Wave 1 readiness: 23.1, 23.3, 17.1, 17.2 and 17.3 can be approved now. 23.5 and 17.4 need one
  edit pass and a diff check.
- Trend for plans 23/17: 19 → 17 → 10 → 9 → 9 → 11 → 10.
{#verdict-body}
