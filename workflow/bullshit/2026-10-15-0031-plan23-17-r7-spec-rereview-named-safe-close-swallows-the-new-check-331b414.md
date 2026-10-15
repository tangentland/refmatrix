---
gmd: "0.1"
id: bsd-plan23-17-spec-rereview-r7-331b414
title: "plan-23 + plan-17 spec re-review r7: all 9 round-6 findings closed. R1.6 calls an unlocked Store.close() 'safe' but gives no way to exempt it, so the new check raises inside close()'s bare except and the shutdown flush is silently skipped. Purge's check fires after its Lance delete. d9ao left 19.2 and 16.6 building on replica_merge"
severity: BULLSHIT
plan: plan-23-bounded-write-harness
task: spec-rereview-r7-23.1-23.4-and-17.1-17.4
round: 7
tags: [bsd, audit, spec-review, re-review, plan-23, plan-17, writer-lock, heartbeat, replica-merge, d9ag, d9ao, d9ap, d9as, wave-1]
---

# ch-bsd spec re-review r7 of plan-23 and plan-17 at `331b414` {#root}

**Commit reviewed:** `331b414` (branch `wave0-spec-reviews`). The plan-23/17 revision under review
is `6db632b` (2026-10-15 00:15:51). `55f043d` adds the d9as pin row. `9add65b` and `331b414`
revise plans 19/21 and 16/22; I read them only for cross-plan consistency. `src/` is identical to
`0e77da3` (0.78.1). **Written:** 2026-10-15T00:31:00-0700.

**Method:**
- Read only. No plan, spec or source file was edited, and no live store or socket was opened.
- Every code claim in the round-6 text was read at HEAD.
- Three claims were checked by running them on scratchpad copies with `.venv-eval` (and the
  deploy interpreter for DuckDB/Lance parity):
  - **DuckDB 1.5.2 / 1.5.3:**
    - a `read_only=True` open of a file with an un-checkpointed `.wal` sees the WAL's rows, and
      leaves the file and the WAL byte-identical;
    - the same open under another process's read-write handle raises
      `IOException: Could not set lock on file`;
    - a read-write open + close of the WAL file checkpoints it, so the file's hash changes and
      the `.wal` is gone;
    - a file whose first 4 KiB is zeroed raises
      `IOException: … is not a valid DuckDB database file!`.
  - **Lance 6.0.1:** `ds.delete("id = 99")` on a dataset without id 99 moves its version
    1 → 2. So a no-match delete DOES commit a version.
  - **Compaction cost:** `Store.dump_catalog_to_log()` ran on a `cp` of the live read snapshot
    (`catalog.read.duckdb`, 835 MB; 114,469 entities, 781,535 links, 253,023 evidence). It took
    **6.1 s** and wrote a 265.7 MB log.
- Live logs were read read-only: `.refmatrix/rmxd.log`, `cli.log`, `sync.log`,
  `daemon.stderr.log`, `~/.refmatrix/hub.log`.
- Two raw `grep`s were rewritten by the hook into `rmx grep`, and one with a BRE `\|` failed loudly
  and was redone with `-E`.

rel: derives-from -> [[bsd-plan23-17-spec-rereview-r6-0e77da3]]
rel: related-to -> [[plan-review-2026-10-14]]
rel: specifies -> [[plan-23-bounded-write-harness]]
rel: specifies -> [[plan-17-nightly-store-maintenance]]
rel: contradicts -> [[claude#no-silent-failures]]

## Round-6 findings: status {#prior-status}

| id | status | evidence at `331b414` |
|---|---|---|
| ns23-r6-1 PROPOSED labels after d9ag | **closed** | The 23.1 header reads "(R1.6, ADOPTED (d9ag))"; R1.1 item 5: "R1.6 (ADOPTED (d9ag)) turns this rule into a check"; R1.6 is now headed "**ADOPTED (d9ag): a held-writer-lock check in the Store's writers**"; AC-20 reads "**ADOPTED (d9ag) with R1.6**". A search for `declines` finds nothing in plan-23. The plan-23 23.1 row says "ADOPTED (d9ag)", and open item 7 is "SETTLED (d9ag, round 6)". The remaining PROPOSED hits are history (rev tables, "Original text:"), as d9aj says they should be. The anchor `{#r1-6-proposed}` is kept as a stable id, which is correct. |
| ns23-r6-2 `writer_lock` lost on reopen | **closed** | R1.6 item 2 makes `Store.writer_lock: Callable[[], Lock] | None` "resolved at check time", with "ONE installer. `Daemon._install_writer_store(st)`" at all 8 sites. I verified them at HEAD: `daemon.py:1665, 1734, 1757, 2888, 2924, 5490, 5508, 5557`, and no other `.store = Store(` exists in `daemon.py`. Item 5 adds the scope note: "the THREAD lock only … blind to DuckDB's `fcntl` lock … never cited as evidence against bug-110's class". AC-20 adds the reopen case (`:2924` then `:2888`; both run under `_store_lock` at HEAD, so the case can be built), the AST case, and the replaced-lock case. I traced the mutations: a direct site FAILS the AST case. A captured lock FAILS the replaced-lock case, because 23.2's `HoldRecorder` wraps a fresh `_FairLock()` by default (23.2 R2), so the old lock reports not-held. The AST rule is narrower than the claim: [[#nm23-r7-1]]. |
| ns23-r6-3 R8 on a broken `replica_merge` | **closed in plan-23 (d9ao b)** | R8 and AC-13 are both "RETIRED (d9ao)", with their reasons. The header says "Not gated on bug-113". `_refresh_replica_now` (`daemon.py:2814`) is the no-op the spec says it is. The same retirement reason was not carried to the sibling plans: [[#ns-x-r7-1]]. |
| ns23-r6-4 23.4 dangling links | **closed (d9ap, d9as)** | R6 hashes `entity_links` "over the ALIVE rows only … The resolver CLASSIFIES each row before it resolves it". The census counts the entity-dead and concept-dead rows per linkage, plus the untouched triples. The mismatch rule is extended. AC-3: the fixture has 2 dangling rows, there is a new negative control, and two new mutations. Traced: a resolver that raises makes N=1 INVALID, so the positive control FAILS. An inner join with no census hides the negative control's inserted row, so it reports no mismatch and FAILS. d9as pins `6db632b`, and `git log -1 -- task-23.4…` at HEAD = `6db632b`. |
| nm23-r6-1 hotfix drift, item 7 not run | **closed** | `#facts` round 6 lists the fence (`daemon.py:4051`, the refusal string at `:4065`), the five files, the links-half liveness gate (`store.py:4379-4395`, read), and `_clear_purged_bits`' direct rebind (`:6315`). I checked that all four `_r4.py` test names exist (`:75`, `:117`, `:130`, `:143`). Merge is dropped from the live-writer list. The alive-links oracle is defined and used in AC-3b/AC-4/AC-16. One fixture detail: [[#nm23-r7-3]]. |
| nm23-r6-2 "same hold" vs a non-re-entrant lock | **closed** | R3.7 step 3 factors out `Daemon._compact_factslog_locked()`, which "REQUIRES the caller to hold `_store_lock`". Read, compact and clear happen in one hold. At HEAD, `_compact_factslog_if_needed` takes the lock at `:2346`, as `#facts` says. I traced the AC-16b self-deadlock mutation: the second case FAILS whether or not the boot check sits before `srv.bind` (`:1807`). With the hang, the flag stays true and the evidence count stays < D, so the case fails even when `ping` answers. |
| ns17-r6-1 restore loses a day | **closed** (MEH residue: [[#nm17-r7-1]]) | 17.4 R6's classification, in order: the ping refusal first; the probe `duckdb.connect(path, read_only=True)` + `SELECT count(*)`; then "A DuckDB lock-conflict error … is classified **'daemon up'**"; then the live-log parse probe. A new scenario (c) rebuilds from the LIVE log, falls back to the backup only after a failed verify, and prints `source:`. I ran the read-only and lock claims on DuckDB 1.5.2/1.5.3, and both hold. The read-write-probe mutation is killed: the WAL case's file hash changes. |
| nm17-r6-1 `invoked_by` for 22.2 | **closed** (MEH residue: [[#nm17-r7-2]]) | 17.1 R1: `invoked_by: "cli" | "mcp" | "hub" | "removal_restore"`, a closed set per verb, `ValueError` otherwise. AC-13 has an in-process case and a mutation. 22.2 R4 (`task-22.2…:188-194`) passes `invoked_by="removal_restore"`, and its AC adds "omit `invoked_by`" as a mutation. Plan-17 item 3 now reads "WRITTEN, both sides". |
| nm17-r6-2 single-id Lance drop | **closed** | R9 filters `_drop_lance_for_purge` (`store.py:3679`; it is called at `:6015`, before the row delete at `:6063`; the line numbers are right). AC-9 has a single-id case. Its mutation is real: Lance 6.0.1 commits a version on a no-match delete (1 → 2, run above). All 6 `purge_entity` callers (`ingest_gmd.py:910`, `store.py:2832, 3043, 6174, 6209, 7379, 7817`) reach the filter or pass `_skip_lance`. |

**Closure:** 9 of 9 round-6 findings are closed (plan-23 6 of 6, plan-17 3 of 3). Two of them
have MEH residue that is filed as new findings below.
{#prior-status-body}

## New findings: plan-23 {#findings-23}

### BULLSHIT nb23-r7-1: R1.6 lets the census mark an unlocked site "safe", but the check still raises there. At shutdown it raises inside `Store.close()`'s bare `except`, and the final fragment flush is silently skipped {#nb23-r7-1}

**Where:** 23.1 R1.6 item 4. The text: "Each is either moved under the lock or named in the
implementation summary with why it is safe (for example `Store.close()` at daemon shutdown after
every op has stopped, or `serve_forever`'s init slot rebind flush at `:1729`…). Only then does the
check raise." The `:1729` example is new in round 6.

**What:**
- R1.6 defines no exemption mechanism. A site that is "named safe" and not moved under the lock
  still calls `flush_fragments()` without the lock, so once the check is switched on it raises
  `WriterLockNotHeld` there.
- **At shutdown:**
  - `serve_forever`'s finally closes the writer on a NEW thread that takes no lock
    (`_do_close` → `self._st().close()`, `daemon.py:2018-2020`, thread `rmxd-close`).
  - `Store.close()` runs `try: self.flush_fragments() except Exception: pass`
    (`store.py:2173-2176`). So the check's exception is swallowed, the flush does not happen, and
    nothing is logged.
  - The periodic flush has already been stopped (`_flush_stop.set()`). The bits dirtied since its
    last 30 s tick are therefore dropped on every daemon stop: every deploy, every `--relaunch`,
    every watchdog restart (one ran today at 00:13:18). That is silent `bitmap_fragments` drift
    against `entity_links`, which is the bug-105/bug-111 class this plan exists to close.
- **At boot:** the `:1729` site is not under any lock (`daemon.py:1727-1731`). The check raises
  inside its `try`, which logs "init slot rebind: close failed" and SKIPS `close()`. The old
  Store's connection and dirty cache are then abandoned while a new Store opens.
- The census cannot catch this. It runs in WARN mode, where nothing raises, and the failure
  only appears after the switch.

**Fix:**
- Delete the "named … safe" route from item 4: every census site is moved under the lock.
- `_do_close` takes `self._store_lock.acquire(timeout=close_budget)` around `close()`. On a
  timeout it logs the dirty-fragment count it could not flush, and never skips silently.
- The `:1727-1731` rebind runs inside `with self._store_lock:`, as both
  `_bootstrap_rotation_if_needed` branches already do (`:2871`, `:2911`).
- `Store.close()` must not swallow `WriterLockNotHeld`: re-raise it, or log and count it.
  Narrowing the bare `except` is in 23.1's file list.
- AC-20 adds a shutdown case: a locked `link` leaves a dirty fragment, then `d.stop` with no
  periodic tick in between; after a fresh open, the bit is in the `bitmap_fragments` row.
  - Mutation: `_do_close` without the lock → FAILS (bit missing).
  - Mutation: `close()` swallowing the exception → FAILS (no log line, bit missing).

**Pattern match:** YES. This is `#imp-consolidated-0914` "silent drops on memory paths" plus
"guards built for the fixed state, not the incident". A gate that turns on cleanly in the suite
lands its first raise inside an `except: pass`.

rel: contradicts -> [[claude#no-silent-failures]]

### SKETCHY ns23-r7-1: the purge case puts the check where it fires AFTER the Lance delete, so the AC's "write nothing" is false and its table list cannot see it {#ns23-r7-1}

**Where:** R1.6 item 3 (the check at `_clear_purged_bits`' rebind); AC-20 ("`purge_entity(<id>)`
… raise … and write nothing (the `bitmap_fragments`, `partitions` and `entities` rows are
unchanged; for `purge_entity` the raise comes from `_clear_purged_bits`' rebind").

**What:**
- `purge_entity` drops the vector first (`_drop_lance_for_purge`, `store.py:6015`) and reaches
  `_clear_purged_bits` only at `:6059`. `_bulk_purge_ids` drops its batch at relative line 23 and
  clears bits at line 38, and `purge_path` does the same through it.
- So an unlocked purge commits one Lance delete and only then raises. The entity keeps its row
  and its non-NULL `vectors_updated_at`, so `pending_embeddings` never re-queues it, and its
  vector is gone until an `embed --gc` notices.
- The AC asserts three catalog tables and none of the Lance state, so it passes on exactly this
  partial write.

**Fix:**
- `_require_writer_lock("purge")` at the TOP of `purge_entity`, `_bulk_purge_ids` and
  `purge_path`, before any Lance or SQL write. Keep the rebind check too.
- AC-20's purge case also asserts that the dataset version is unchanged and the vector is still
  readable.
- Mutation: the check only in `_clear_purged_bits` → FAILS (version +1).

### SKETCHY ns-x-r7-1 (cross-plan; owners plan-19 and plan-16): d9ao retired 23.1 R8 for "no producer of diverged slots", but 19.2 R6/AC-10 and 16.6 R1c still build and test rules on `replica_merge`, and plan-19 still calls R8 the closure {#ns-x-r7-1}

**Where:**
- `plan-19…:194`: "**The `replica_merge` offset row:** CLOSED: 23.1 R8".
- `task-19.2…:138-143`: R6 "Survives a slot merge … 23.1 R8's `queue_offsets` rule … is
  plan-23's"; AC-10 is "`replica_merge` keeping the A-side row"; the file list includes
  `replica_merge.py`.
- `task-16.6…:332-335`: R1c adds `learned_evidence` to `replica_merge`'s table lists.
- `plan-19…:314` scopes d9ao to plans 16/17/22/23 and changes nothing in plan-19.

**What:**
- d9ao's two reasons apply word for word to 19.2 and 16.6:
  - nothing produces diverged slots;
  - `merge_slots` builds on `init_catalog`, which bug-113 breaks on every real store.
- A 19.2 AC-10 or 16.6 fixture built on `init_catalog` slots passes, while the production command
  fails before it reaches their tables. That is ns23-r6-3's defect, now in two Wave-1 tasks.
- 19.2 R6 cites a requirement that is now RETIRED.
- d9ao's separate frozen-slot item ("recover after bug-113's fix, or discard") is exactly what
  would decide whether these rules are ever needed.

**Fix (user decision):**
- Either extend d9ao to 19.2 R6/AC-10 and 16.6 R1c (retire them, with the same evidence), and
  restate plan-19 item 4 as "RETIRED with 23.1 R8 (d9ao)".
- Or keep them, give them a `Depends on:` bug-113's fix, and test them through
  `_op_replica_merge` on `Store.init()` slots (the ns23-r6-3 (a) shape).

**Pattern match:** YES, `#imp-adopt-by-merge-not-sha`'s sibling: a decision applied to the plan
that asked, not to the plans that share its premise.

### MEH nm23-r7-1: the one-installer AST rule matches only `x.store = Store(…)`, so a two-statement bypass passes it {#nm23-r7-1}

- **Rule:** AC-20 checks for "no `Assign` whose target is an `Attribute` named `store` and whose
  value is a `Call` to `Store`".
- **Bypass:** `st = Store(…); …; self.store = st` (the shape the `:1734` rebind would naturally
  take, since it sets `db_path` before `init()`) evades it.
- The reopen case covers only `:2924`/`:2888`.
- **Fix:** the rule rejects ANY assignment to an attribute named `store` on `self`/`d` in
  `daemon.py` outside `_install_writer_store`, whatever its value. At HEAD there is no
  `store = None` assignment to exempt.
- **Mutation:** the two-statement form at `:5557` FAILS the case.

### MEH nm23-r7-2: R1.6 says 23.2's `HoldRecorder` "forwards `held_by_current_thread` like the rest of the surface", but the 23.2 spec approved today (d9at) lists a closed surface without it {#nm23-r7-2}

- **The mismatch:** 23.2 R2 lists the surface as "`acquire`, `release`, `locked`, `__enter__`,
  `__exit__`". 23.0/23.2 began implementation under d9at, and `_FairLock.held_by_current_thread`
  does not exist until 23.1.
- **Result:** every R1.6 check, `_compact_factslog_locked`'s guard and AC-20's replaced-lock case
  would raise `AttributeError` on a recorded daemon. The failure is loud, but it is not in either
  spec's file list.
- **Fix:** either 23.2 R2 forwards unknown attributes to the wrapped lock (`__getattr__`), or
  23.1 names the `HoldRecorder` edit as its own change.

### MEH nm23-r7-3: AC-3b's dangling fixture row deletes only the concept's `entities` row; its `concepts` row keeps it ALIVE under item 6 {#nm23-r7-3}

- **What:**
  - AC-3b: "one dangling `(pa, mentions)` row (its concept's `entities` row deleted by SQL …)".
    Item 6 and the 0.78.1 gate (`store.py:4388`, `concept_ids` = entities ∪ concepts) call a
    concept dead only if its id is in NEITHER table.
  - A concept entity has a `concepts` row (`store.py:282`, "equals entities.id where
    kind='concept'"; inserts at `:1860`, `:2246`, `:2421-2429`).
  - So the fixture row is alive, and "its bit is in no row" fails against correct code.
- **Fix:** delete the concept from `entities` AND `concepts`, or seed an entity-dead row instead.

{#findings-23-body}

## New findings: plan-17 {#findings-17}

### MEH nm17-r7-1: 17.4 AC-9's second (c) run contradicts R6's own classification; the (c) fallback branch is unreachable by any AC; two classification details are unstated {#nm17-r7-1}

- **Class contradiction.** AC-9 (c) second run: "the live log's middle line also corrupted
  prints `source: backup (live log failed …)`".
  - R6 probes the log BEFORE classifying: a non-JSON middle line fails "every line … is a JSON
    object with an event `op`", which is class **(b)**, not (c)'s verify-fail fallback.
  - So the expected message belongs to a branch the input never reaches.
  - Nothing reaches "(c) parses, rebuild fails verification, fall back". A mutant that drops the
    fallback (and stops instead) therefore survives.
  - **Fix:** pin the corruption and expected class for this run: non-JSON middle line → (b), with
    `source: backup (live log failed to parse: line N)`. Then add a (c) run whose log PARSES but
    fails verification (for example a `link` event naming an undeclared linkage), so it reaches
    the fallback. Mutation: the fallback removed → FAILS.
- **Lock discriminator.** A lock conflict and a corrupt header are BOTH `duckdb.IOException`
  (shown above). R6 should name the discriminator: the message text "Could not set lock on file".
  AC-9's (c) case already kills a class-based classifier.
- **Wrong precedent.** R6 (c) cites "the 2026-09-14 ART-index crash loop". That catalog OPENED
  and served reads (memory `project_refmatrix_entities_index_crashloop_0914`: phantom index
  entries, failing only on writes).
  - R6's `count(*)` probe classifies it as (a), and the script tells the operator to run
    `rmx compact-log --force` against a daemon that is crash-looping.
  - **Fix:** drop that precedent, or say (a)'s refusal covers it and its fix is the offline table
    rebuild, not a restore.

### MEH nm17-r7-2: "calls the `vectors_restore` verb in-process" does not say which entry point; the verb is a socket client of the same daemon {#nm17-r7-2}

- **What:**
  - 17.1 R1 and 22.2 R4 say `removal_restore` "runs inside the daemon and calls the
    `vectors_restore` verb in-process (no adapter)".
  - `verbs.py`'s verbs reach the daemon through `daemon_mod.call` (`verbs.py:208-215`). Called
    from inside a daemon op, that is a socket round trip into its own daemon. It takes a second
    pool worker, and it is bounded by `daemon.call`'s timeout × (retries+1) (memory
    `feedback_daemon_call_retries_multiply_timeouts`).
  - If 22.2 instead calls `_op_vectors_restore(d, args)` directly, the verb-layer closed-set
    check that 17.1 R1 relies on is bypassed.
- **Fix:**
  - Name the entry point: the op function, called directly.
  - Put the closed-set `invoked_by` check in the op (the verb forwards the value), so both paths
    check it.
  - AC-13's in-process case calls that same entry point.

### MEH nm17-r7-3: 17.3's hold bound (< 60 s) equals the watchdog's heartbeat-stale threshold with no margin, and the heartbeat is a no-op on the 4-worker cli pool {#nm17-r7-3}

- **The coupling, in code:**
  - The heartbeat is "a no-op submitted to the pool", and the file is touched only when it
    completes (`daemon.py:1319-1335`).
  - The hub restarts after `WATCHDOG_GRACE_MISSES` missed pings AND a heartbeat older than
    `HEARTBEAT_STALE_S` = 60 s (`hub.py:305-317`; `daemon.py:66`).
  - The cli pool has 4 workers (`rmxd.log` 00:13:21 "pools cli=4").
  - Four cli ops queued behind one `_store_lock` hold therefore stop the beat for the whole hold.
- **What goes wrong:** 17.3 AC-4 accepts holds up to 59.9 s. A hold that long, during a catch-up
  run that lands under agent hook load (17.2's catch-up runs when the machine wakes, not only at
  03:30), crosses the stale threshold by the next 5 s tick, and the watchdog restarts the daemon
  mid-step.
- **Fix:** set the bound from the watchdog: `hold_s < HEARTBEAT_STALE_S − 2 × RMX_HEARTBEAT_S`
  (50 s today), or a flat 30 s, and cite the coupling.

{#findings-17-body}

## Live evidence, 2026-10-15 (asked) {#live-evidence}

1. **00:11:15 compaction, then ~2 min unresponsive.**
   - `rmxd.log`: "facts.log compacted 294090489 -> 264498314 bytes (entity=114219
     link=775720…)" at 00:11:15. That line is written AFTER the lock is released. The start is
     not logged.
   - My copy run of the same dump took **6.1 s**. The compaction hold itself is therefore not
     the 2-minute stall.
   - From 00:11:15 to 00:13:14, `rmxd.log` has no lock-taking line: no watch flush and no learn
     drain.
   - `cli.log` shows every `sync --flush-queue --async` at ~1,980 ms (the ping-timeout
     fallback).
   - The 00:13:16 stop line names 3 `stats` ops in flight on the disp pool. `_op_stats` takes
     `_store_lock` (`daemon.py:3732`).
   - `hub.log` 00:13:18: "not answering ping (SIGTERM sent now)".
   - I do not name a mechanism: the logs do not hold one (`feedback_causal_story_before_evidence`).
2. **00:16:52-00:17:44 heartbeat stall.** It coincides with two concurrent CLI
   `sync --since HEAD~1` calls, which ended at 00:17:11 (80,429 ms) and 00:17:45 (109,993 ms). The
   stall ends within a second of the second sync. 23.3 (one sync at a time per store, the lock
   released between files) is the plan that bounds this shape.
3. **Learn backlog.** The learn queue grew from 49 to 116 patterns between 00:14:15 and 00:22:41,
   while each drain applied 1-2 patterns per tick and "stopped on budget". This is an observation,
   not a finding: 23.1 bounds each hold, not drain throughput.
4. **Adequacy:**
   - **23.1 R3.7:** the boot compaction is about 6 s on this store, so AC-16b's 10 s is
     adequate here. Placing it before `srv.bind` (`:1807`), where the cli pool does not exist
     yet and the beat ticks unconditionally, would make it independent of hook load. The spec
     says only "before the first tick".
   - **What the plans do not bound:** 23.1 bounds harness consumers only. No plan bounds the
     non-harness holders the live logs implicate: `_op_stats` under the lock, and the 30-min
     compaction tick. No plan owns the heartbeat-on-cli-pool coupling. That is
     `#imp-consolidated-0914b` "a liveness tick that waits on the cli pool is the ping wearing a
     file", sighted again. See [[#needs-user]].
   - **17.x:** 17.1's per-dataset holds and 17.4's lock-free copy are bounded. 17.3's bound is
     [[#nm17-r7-3]].

{#live-evidence-body}

## Needs the user {#needs-user}

1. **ns-x-r7-1:** extend d9ao to 19.2 R6/AC-10 and 16.6 R1c, or keep them gated on bug-113's fix.
2. **Ownership:** which plan owns the non-harness lock holders (`_op_stats` under
   `_store_lock`, the compaction tick) and the heartbeat's dependence on the cli pool? None of
   plans 17/23 does today, and both live incidents went through it.
3. Everything else is a spec edit with no new decision. nb23-r7-1's fix only removes a route
   the user never decided on.

{#needs-user-body}

## Verdict {#verdict}

**plan-23: NOT YET.** 23.1 needs one more edit (nb23-r7-1, ns23-r7-1, nm23-r7-1, nm23-r7-3). 23.4
is approvable as pinned (d9as = `6db632b`). 23.3 is unchanged and approvable. 23.0/23.2 are
approved (d9at); nm23-r7-2 is a one-line 23.2 or 23.1 edit. New findings: 1 BULLSHIT,
1 SKETCHY, 3 MEH, plus ns-x-r7-1 (SKETCHY, owned by plans 19/16).

**plan-17: APPROVABLE** once its 3 MEH edits are made (nm17-r7-1..3). There is no BULLSHIT and no
SKETCHY. Its implementation still waits on 23.1 (17.1's `Depends on:`).

**Totals:** 9 new findings (1B / 2S / 6M). Round 6: 9 of 9 closed. The trend is
19 → 17 → 10 → 9 → 9. The one BULLSHIT is a pre-existing route, sharpened by round 6's `:1729`
example, and it surfaced only by reading `Store.close()` beside the census rule.
{#verdict-body}
