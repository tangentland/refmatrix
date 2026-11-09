---
gmd: "0.1"
id: bsd-plan23-1-2-freshness-confirm-1c0b66a
title: "ch-bsd focused confirm (lite), plan-23 23.1 + 23.2 freshness fold at 1c0b66a: DIRTY 1B/2S/7M; all 11 findings closed in text, and R11's queue can overwrite a newer digest"
tags: [bsd, spec-review, freshness, confirm, plan-23, queue, hooks, bug-177, bug-182, replica-merge]
severity: BULLSHIT
plan: plan-23-bounded-write-harness
task: "23.1, 23.2"
---

# ch-bsd focused confirm (lite): plan-23 23.1 + 23.2 freshness fold {#root}

**Commits:** the fold is `b51f31b` (specs) and `1c0b66a` (registry). HEAD is `86197ce`, and no
commit after `1c0b66a` touches `plan-23*`, the 23.x task specs, or the bug-177 / bug-182 rows.
`src/` is unchanged since `9bcf464`.
**Date:** 2026-11-09T02:15:57-0800
**Author:** Todd Holley / Opus 5.5 / orchestrator (fold)
**Scope:**
- the `9901589..1c0b66a` diff under `workflow/`;
- read-only reads of master `src/` and `tests/`;
- the 3.7 clone (`task-3.7-verb-it-backlog`), now at `e4faf32` (the fold cites `d093f65`; the
  only commits since are r4 docs and a test);
- the bug-178 clone (`fix-bug178-bulk-write`), now at `ae7c0c7` (the fold cites `d13c4d7`).

No store was opened. No `rmx` command touched a store; `rmx focus summarize --help` was run only
to time the CLI's startup.

rel: evidence-for -> [[task-23.1-queue-and-drain]]
rel: evidence-for -> [[task-23.2-lock-hold-fixture]]
rel: derives-from -> [[bsd-plan23-1-2-freshness-9bcf464]]
rel: related-to -> [[task-23.5-read-path-and-holder-bounds]]
rel: related-to -> [[task-bug178-bulk-write-helper]]
rel: related-to -> [[task-3.7-verb-it-backlog]]

## Prior findings {#prior}

| finding | status | evidence |
|---|---|---|
| b1 (no requirement covered bug-177) | CLOSED in text; buildable once n1, m4, m5 and m6 are folded | [[task-23.1-queue-and-drain#r11]], [[task-23.1-queue-and-drain#ac-21]], the `hook_writes` row in [[plan-23-bounded-write-harness#consumers]], and the bug-177 row (corrected: confirmation lost, not the digest) |
| b2 (scan-prompt overrun unowned) | CLOSED; m3 residual | the bug-182 row and [[task-23.1-queue-and-drain#non-goals]] |
| s1 (installer / AC-20 described pre-0.79.0 code) | CLOSED; m2 residual | R1.6 item 2 and [[task-23.1-queue-and-drain#ac-20]] match HEAD (see below) |
| s2 (R8 retirement premise gone) | CLOSED in intent. R8.2 has a false premise (n2) | [[task-23.1-queue-and-drain#r8]], [[task-23.1-queue-and-drain#ac-13]] |
| s3 (AC-6 failed on a correct build) | CLOSED for what the AC-6 pattern finds; m1 residual (the census misses three files) | [[task-23.2-lock-hold-fixture#r6]], [[task-23.2-lock-hold-fixture#ac-6]] |
| m1 (line drift) | CLOSED | `file::symbol` citations; numbers appear only "at <sha>" |
| m2 (`acquire_use`) | CLOSED | `daemon.py:384` `_MemMirror.acquire_use`; `test_read_path_partition_and_budget.py:163` |
| m3 (R3 proxy vs `bulk_write`) | CLOSED; m1 residual (wrong error text) | `backend.py:684` `duck_executemany_calls` exists at `ae7c0c7` |
| m4 (learn-off gate, old return shape) | CLOSED | R6.1 `enabled()`, R9.3 adapter, the gate case in [[task-23.1-queue-and-drain#ac-11]] |
| m5 (verbs vs 3.7) | CLOSED | `verbs.py:2970` `INTERNAL_CLI` on 3.7 holds `("learn","status")` under `_INTERNAL_DECISION` |
| m6 (plan-26 overlap) | PARTIAL: the merge order, the `_maybe_commit` precondition and the census are closed; the `memory_compile` apply is not anchored (b-n1) | [[task-23.1-queue-and-drain#merge-order]] |

What was checked for s1:
- `_install_writer_store(self, st, slot: str)` is at `daemon.py:1529`.
- `_reopen_writer` is at `:1536`, and its assert at `:1540`.
- The four direct sites are at `:1832`, `:1901`, `:1924` and `:3077`, and the legacy bootstrap's
  `self._active_slot = "A"` is at `:3080`.
- `_reopen_writer_after_merge` is at `:5605`, and `_repair_missing_slot_locked` at `:1477`.

## Answers to the seven questions {#answers}

1. **`_write_or_local` with `queue=` and `local=None`** (3.7 `verbs.py:554`).
   - **The contract fits.** Today the function has three outcomes. Its other callers are curate
     `set_flag`, `forget` (twice) and `_matrix_write`; all pass `local=`, and none passes `queue=`.
   - **The return shape fits.** `{"queued", "queue", "source": "queue"}` is the same shape as the
     `source: daemon` and `source: in-process` returns.
   - **`local=None` refuses as the spec says.** It raises on absent. But nothing states that
     `focus_summarize` keeps its own "daemon not running … start it" wording and exit 1, or that
     no queue line is written in that case (m6).
   - **`_promote_digest` is underspecified.** Today it has an in-process fallback, and the spec
     does not say which `local=` it passes (m6).
   - **No collision with 25.1.** 25.1 (at HEAD, after `55890cf`) budgets stdout bytes for
     UserPromptSubmit, SessionStart and PreCompact. It keeps the promote and save-state legs (R7),
     and it edits `hooks.py` recall commands. R11 changes no hook string. The only overlap is that
     the PreCompact promote now prints `queued: <name>`, which is shorter than the line it
     replaces.
2. **The enqueue is bounded.**
   - **How it writes.** R3.2 is one `O_APPEND` line from the CLI process, with no lock and no
     socket. It is the same mechanism as today's `learn_queue.enqueue` (`learn_queue.py:55`).
   - **Where the file lives.** It is under `.refmatrix/`, beside `learn_queue.queue_path`.
   - **Nothing in the path waits on the holder.** Overflow trimming happens at drain time
     (`read_rotated`, `:117`), not at append time. So the enqueue cannot block behind
     `_store_lock`.
   - **What is not bounded is the time before the enqueue (m5).** `focus_summarize` runs its own
     `daemon_status` probe, then `_write_or_local` → `_call` → `require_daemon` probes a second
     time (each up to 0.5 s), and the interpreter starts before either. A flat
     `timeout - 1.0` does not guarantee the < 5 s that AC-21 step 2 asserts on wall clock.
   - The append/rotate race is safe for learn but not for this queue (m7).
3. **Duplicate apply.**
   - **The row and the edge are idempotent:**
     - `add_memory` upserts on `memory_content.entity_id`;
     - `upsert_subject` is idempotent on the slug;
     - `link_part_of` sets a bit.
   - **facts.log is not.** `add_memory` logs a `memory_content` event on every call (`store.py`,
     after `con.commit()`), so the dual case logs two events. Replay is an upsert, so this is
     harmless, but AC-21 does not state it.
   - **The real hole is ordering, not duplication (n1).** A queued older digest can land after a
     newer synchronous one.
4. **User-run `memory add` and MCP stay synchronous. Confirmed.** `hooks.py` at HEAD and on 3.7
   generates:
   - Stop: `focus summarize --promote --timeout 5` (`:211`);
   - PreCompact: `focus summarize --promote --timeout 30` (`:355` / `:357`);
   - PreCompact: `save-state --no-promote --no-sync` (`:374` / `:376`).

   No generated hook runs `rmx memory add`, and the installed `.claude/settings.json` agrees.

   This also means the save-state promote (`_promote_digest`) is **not on any hook path**: only a
   user-run `rmx save-state` reaches it. The spec calls it a hook-path producer (m6).
5. **s2 against bug-178 now.**
   - At `ae7c0c7`, bug-178 still edits only `_fill_remap` / `_merge_linkage_types` / `_merge_into`'s
     remap fill. No `tables` tuple changes. That is consistent with the fold.
   - Three `tables` tuples exist: `merge_slots` (`:84`) and the two audit functions (`:527`,
     `:629`). R8 rightly touches only `merge_slots`.
   - R8.2's premise is wrong, though (n2).
6. **Census: both numbers are right, measured two ways.**
   - AC-6's literal pattern, filtered to `_store_lock` / `_use_lock` assignments, gives
     **14 lines in 13 files** (my figure).
   - The fold's "15 lines in 14 files" adds `test_learn_queue.py:190`
     (`d._store_lock = _CountingLock()`). The pattern hits only that file's `class` line, which
     does not assign.
   - The scope R6 lists (14 files) is right. Its stated method is off by one.
   - The census misses `__import__('threading').Lock()` and a hand-rolled recorder (m1).
7. **23.5's holder list.**
   - 23.1 does not depend on the bounding decision. R11 queues hook writes during a
     `memory_compile` apply, and R1.6's census only lists unlocked sites; that apply runs under
     `with d._store_lock` (`daemon.py:5385`).
   - But "decided when 23.5 is next revised", with no line in 23.5, is an unanchored deferral
     (b-n1).

## Findings {#findings}

### BULLSHIT b-n1: the `memory_compile` apply's bounding is deferred to a 23.5 revision that does not exist {#b-n1}

**File:** `task-23.1-queue-and-drain.md#merge-order` ("bounding it … is decided when 23.5 is next
revised, not here"); the `26.6 memory_compile apply` row in `plan-23-bounded-write-harness.md#consumers`;
`task-23.5-read-path-and-holder-bounds.md` (no mention of `memory_compile`).
**What:** The fold names the apply as a long holder and defers both options (`bounded_steps`
consumer, or a 23.5 named holder) to an unscheduled revision.
**Why it's bullshit:**
- Rule 9a, second bullet: the target task exists, but no task spec's acceptance criteria cover
  the deferred work.
- `_op_memory_compile_apply` already holds `_store_lock` for the whole `apply_plan` at HEAD, and
  26.6 (approved) lengthens it.
- This is b1's pattern a second time: a row says "owned by X", and X has no text for it.

**Fix (decided as the user would: 23.5 already owns named non-harness holders):**
- Add the apply to 23.5's named-holder list, with one AC: its hold is measured under 23.2's
  recorder on a fixture memory dir, with a pre-registered `max_writes_per_hold`.
- Or record it in 23.5 as a `bounded_steps` consumer.
- Either way, add one line in 23.5 and point the 23.1 / plan-23 text at it.
- This does not gate 23.2. It must land before 23.1 is marked build-ready.

**Pattern match:** YES ([[bsd-plan23-1-2-freshness-9bcf464#b1]]).

### SKETCHY s-n1: a queued older digest can overwrite a newer synchronous promote {#n1}

**File:** `task-23.1-queue-and-drain.md#r11` items 1, 3 and 4; [[task-23.1-queue-and-drain#ac-21]] step 3.
**What:** Last-wins-by-name orders lines only within the queue. The synchronous path is a second
writer of the same name (`focus_summary_<slug>`, one per session, re-promoted every turn), and
nothing orders the two paths.
**Why it's sketchy:**
- The tick runs every 30 s (`RMX_DAEMON_FLUSH_S` default, `daemon.py:2240`).
- Sequence:
  1. Turn N's Stop meets a holder and queues vN.
  2. The holder releases.
  3. Turn N+1's Stop (often under 30 s later) finds the daemon free, and its dial writes vN+1.
  4. The next tick applies vN, so the digest regresses.
- If N+1 was the session's last Stop, the regression is permanent: the newest turns' digest is
  lost. That breaks "never loses".
- AC-21 runs only one producer, so a correct build of the spec as written passes it.

**Fix:**
- In R11.3's apply, skip the content upsert when the row's `memory_content.updated_at` is ≥ the
  entry's `ts`. Both are `time.time()` on the same host.
- Still apply the `part-of` filing, because the bit is order-free.
- This also removes the dual-apply case's second `memory_content` facts.log event: the late dial
  lands after the enqueue `ts`, so the queued copy is skipped.
- Add an AC-21 case: queue v1 under a holder; release; promote v2 synchronously before the tick;
  tick. Expect the row to hold v2 and facts.log to hold no v1 event after v2.
- Mutation: the unguarded apply FAILS this case.

**Pattern match:** NO (new).

### SKETCHY s-n2: R8.2 forbids the one place the queue tables must be declared {#n2}

**File:** `task-23.1-queue-and-drain.md#r8` item 2 ("adds them to the `tables` handling in
`merge_slots` only, not to `duckdb_catalog.init_catalog` (no longer the target builder)");
`replica_merge.py:262-273`; `duckdb_catalog.py:249`; `store.py:1324`.
**What:** `_merge_into` builds the merge target with `init_catalog(con, sequence_starts=…)`. That
is bug-113's fix: "the target's schema is `init_catalog`'s, the Store's own". The Store's DuckDB
schema is also `init_catalog`, through `backend.init_catalog` at `store.py:1324`.
**Why it's sketchy:**
- The tables "exist in the target" (R8.2's own premise) only if their DDL is in `init_catalog`.
- An implementer who follows "not to `init_catalog`" creates them somewhere else (for example
  lazily in `bounded.py`). The merged target then lacks them, the carry's INSERT fails, and the
  slot is half-built.
- `duckdb_catalog.py` is still not in [[task-23.1-queue-and-drain#files]].
- `merge_slots(a_path, b_path, target)` also has no way to know which side is the writer. Only
  `_op_replica_merge` knows (`prev_writer`, `daemon.py:~5680`).

**Fix:**
- The DDL for `queue_offsets`, `queue_counters` and `bounded_runs` goes in
  `duckdb_catalog.init_catalog` (the Store schema, and therefore the merge target's).
- `merge_slots` gains `writer_side: "A" | "B"`, passed from `prev_writer`.
- `duckdb_catalog.py` joins [[task-23.1-queue-and-drain#files]].
- AC-13 stays as written; its slots come from `Store.init()`, which then has the tables.

**Pattern match:** NO.

### MEH m1: residuals in 23.2's census and error text {#m1}

- **Files the census misses.** R6's "every file that assigns a fake `_store_lock`" misses:
  - `__import__('threading').Lock()` at `test_derive_coverage.py:193`, `test_derive_stamp.py:179`
    and `test_plan12_remedy.py:340,:381,:430`;
  - the hand-rolled `_CtxRecorder` at `test_brief_surfaces.py:215` (a lock-entry recorder,
    defined at `:240`).

  AC-6's pattern cannot see any of them, so it can go green while they stay.
- **The census count.** The "15 lines in 14 files, AC-6's pattern" figure is 14 lines in 13 files
  under that pattern ([[#answers]] Q6).
- **R3's error text.** R3 quotes the error a stand-in wrapper would raise as "SQLite connection
  reached a DuckDB-only bulk write". At `ae7c0c7` a non-sqlite stand-in raises
  `bulk_write: unsupported connection type …` (`backend.py:743`).

**Fix:**
- Widen the census to `_store_lock\s*=` (any value other than `_FairLock()` or the recorder),
  list the three files, and widen AC-6's pattern the same way.
- Correct the count wording and the quoted message, and cite the bug-178 sha as `ae7c0c7`.

### MEH m2: `_install_writer_store(st, None)` changes the two slotless sites {#m2}

The installer always calls `_refresh_read_only_link()`. The boot open (`:1832`) and the legacy
fallback (`:1924`) do not call it today. R1.6 says `None` keeps "today's behaviour at those two
sites" for `_active_slot` only.

**Fix:** State whether `slot=None` also skips the link refresh, or that the refresh at boot is
intended. If it is intended, cover it in AC-20's boot case.

### MEH m3: bug-182 says it is in the goal queue; the goal does not list it {#m3}

The bug-182 row says "In the pre-plan-24 queue ([[plan-of-plans#goal-2026-11-09]])". The goal
line (`plan-of-plans.md:57`) names items (1)-(7) with bug-177 and bug-179, and no bug-182 (0 hits).

**Fix:** Add bug-182 to the goal line as its own item (measure first), or drop the claim from
the row.

### MEH m4: the queued apply never requests a snapshot {#m4}

`_op_memory_add`, `_op_subject_upsert` and `_op_subject_link` each end in `d._request_snapshot()`
(`daemon.py:5011`, `:5371`, `:5381`). Today's learn drain does too.

R11.3 calls the Store methods directly, and neither R9 nor R11 mentions a snapshot. A queued
digest would therefore be invisible to `memory recall`, `recall-state` and scan-prompt (all of
which read the lock-free replica) until some unrelated write.

**Fix:**
- After any committed `hook_writes` or `learn` batch that wrote rows, the registrant calls
  `_request_snapshot()`.
- AC-21 step 3 also reads the digest through the replica path (`rmx memory get`), not only by SQL
  on the writer.

### MEH m5: the queued path's budget is not derived {#m5}

The time before the enqueue adds up as follows:
- interpreter start (`rmx … --help` 0.13-0.14 s; the promote path imports more);
- `focus_summarize`'s probe (`daemon_status`, 0.5 s cap);
- `_call`'s `require_daemon` probe (another 0.5 s);
- then `timeout - 1.0`.

Under bug-176-style CPU contention this can exceed 5 s. In AC-21's sandbox, where ping answers
instantly, it will not, so the AC passes while production overruns.

**Fix:**
- Use the deadline `focus_summarize` already computes: the dial gets
  `deadline - now - ENQUEUE_RESERVE_S`.
- Probe once (pass the probe result in, or let `_write_or_local` own the only probe).
- AC-21 step 2 asserts both `latency_ms < 5000` in `cli.log` and a stated wall bound.

### MEH m6: producer details R11.4/R11.5 leave open {#m6}

- **`_promote_digest`'s fallback.** It has an in-process fallback today (`handoff.py:~340`).
  Say whether it passes `local=` (keeping it) or `local=None`.
- **The save-state label.** The save-state promote is user-run, not a hook path ([[#answers]]
  Q4). Either justify queuing it on its own grounds (it is best-effort, its GMD file is the
  primary artifact, and queuing lets the digest land), or drop it. The "hook-path" label and
  R11.5's reason for keeping `memory add` synchronous (not a hook, 30 s budget) currently
  contradict each other.
- **The partition resolver.** The two producers resolve partitions differently:
  - `focus_summarize` uses `_memory_daemon_call` → `_resolve_partition()`;
  - `_promote_digest` uses `discovery.store_name(root)`.

  So the `(op, partition, name)` key can split for one digest. Name the one resolver. It must be
  lock-free: not `memory_partition`'s `partition_list` fallback, which takes the writer lock.
- **Absent daemon with `local=None`.** Add a case: exit 1, the existing refusal wording, and no
  queue line appended.
- **Where the queued wording lives.** Put it beside `classify_transport_error` as a constant. Do
  not put it inside the function: it returns errors, and a queued promote is not one.

### MEH m7: rotate and append race, harmless for learn, not for `hook_writes` {#m7}

**The race.** `enqueue` opens the path and then writes. If a drain renames the file between those
two steps, the line lands in the rotated segment, possibly after the drain has read it. R3.3
unlinks a segment when "its LAST offset commits", and that offset is measured at read time.

**Why it differs by queue.** Learn tolerates losing one line. A lost `hook_writes` line is a
digest and a filing that never land.

**Fix:** Unlink a segment only when its committed offset equals its size by `stat` at unlink
time. Otherwise re-read the tail at the next tick. Add one AC-21 sub-case that appends to a
just-rotated segment.

## Build readiness {#readiness}

**23.2 is build-ready after the m1 fold.** That fold is text only, with no user decision. Its
merge gate is unchanged: bug-178 merges first.

**23.1 is not build-ready until all of the following are folded:**
- b-n1 (one line in 23.5);
- s-n1 (the `updated_at` guard plus one AC case);
- s-n2 (DDL in `init_catalog`, plus `writer_side`);
- m2 and m4-m7 in the same pass.

No user decision remains, so a short confirm can follow the fold. Order stays as before: 3.7 →
bug-178 → plan-26 → 23.2 → 23.1.

## Verdict {#verdict}

DIRTY: 10 findings (1 BULLSHIT, 2 SKETCHY, 7 MEH). All 11 findings from the prior report are
closed in text, with m6 partial and four MEH residuals.

rel: contradicts -> [[plan-23-bounded-write-harness#consumers]]
