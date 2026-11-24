---
gmd: "0.1"
id: impl-task-hook-writes-queue
title: "task-hook-writes-queue: hook writes enqueue and return (GREEN)"
tags: [implementation-summary, hooks, stop-hook, promote, queue, bug-309, bug-177]
metadata:
  node_type: implementation-summary
  status: complete
  created: 2026-11-24
---

# task-hook-writes-queue: hook writes enqueue and return {#root}

rel: implements -> [[task-hook-writes-queue]]
rel: implements -> [[task-23.1-queue-and-drain#r11]]
rel: depends-on -> [[self-audit]]

GREEN for RED `fbb9fd9d` (28 failing tests). The Stop hook's promote and the save-state promote
no longer wait out a busy writer: they append a durable entry to `<store>/hook_writes.spool/`
and return; the daemon drains it on its flush tick and at boot, newest authoring time winning.
{#lead}

## What changed {#changes}

- **`hook_writes.py` (new).** `enqueue(root, entry) -> Path` (`.tmp`, fsync, rename, directory
  fsync; name `<time_ns:020d>-<uuid4>.json`), `validate`, `read_pending`, `newest_by_ts`,
  `coalesce`, `drain`, `counts`, `sweep_stale_tmp`. An entry missing a key, with an unknown
  `op`, or with an `args` key `add_memory` does not take is unreadable and moves to `bad/`.
  The boot sweep leaves a `.tmp` younger than 60 s (by its name): a producer enqueues exactly
  when the daemon is busy, and a booting daemon is busy. {#c-module}
- **`store.py` (R11.3).** `add_memory(updated_at=)` plus `add_memory_checked -> (id, written)`,
  the one guard: a live write skips when the stored `updated_at >=` the given time; replay
  applies a tie in log order (see #replay-tie). The `memory_content` event carries
  `updated_at` in `add_memory`, `reclassify_memories`, `retag_memory` and
  `dump_catalog_to_log`; `_apply_one_event` and the rebuild's memory-bodies pass pass it; the
  rebuild picks its winner by `(ev.get("updated_at", ts), ts)`. {#c-store}
- **`daemon.py`.** `Daemon._drain_hook_writes()` (one entry point; a drain mutex so the boot
  drain and an early tick never share a spool), run on every flush tick before the periodic
  flush and once at boot after the slot rebind; `_sweep_stale_hook_writes_tmp` at startup;
  `_store_health` reports `hook_writes_pending` / `hook_writes_bad`; `_op_memory_add` passes
  `updated_at`. {#c-daemon}
- **`verbs.py` (R11.4).** `_call` split into probe + `_dial`; `_write_or_local` gains
  `queue=`, `deadline=`, `subject=`, `origin=`, `local_create=`, and `local=None` (only with
  `queue=`). `ENQUEUE_RESERVE_S = 1.0`, `MIN_DIAL_S = 0.5`, `QUEUED_WRITE_MSG`,
  `HOOK_WRITES_QUEUE`. {#c-verbs}
- **`cli.py`.** `focus summarize --promote` computes its deadline at entry, drops its own
  probe and routes through `_write_or_local(queue=…, local=None, origin="stop-hook")`; on
  `queued` it prints `queued: <name>` + the message and exits 0. `rmx save-state` prints the
  queued note in place of `promoted … (id=…)`. PreCompact reports a queued promote as a
  deferred store commit and records it (`handoff.record_precompact_save(promote_queued=)`).
  `rmx daemon status` prints a `hook_writes:` line when pending or bad is non-zero (read with
  `hook_writes.counts`, so it shows with the daemon up, busy or down). {#c-cli}
- **`handoff.py`.** `_promote_digest` uses `discovery.resolve_partition`, stamps
  `updated_at`, derives its deadline from its own `timeout`, routes through
  `_write_or_local(queue=…, origin="save-state")` with its in-process closure as `local=`.
  {#c-handoff}
- Docs: `docs/INTEGRATION.md#hook-writes-queue`. Deferral row D5 in
  `workflow/deferral_registry.md`. {#c-docs}

### Commits on the apply path (R11.3 m6) {#commit-census}

`drain` runs each partition in `store.transaction()` under one `_store_lock` acquisition and
binds the partition (`with_partition`, which may commit a new partition row) BEFORE the
transaction opens. Inside it: `add_memory_checked` → `upsert_entity` (`_maybe_commit`) and its
own `_maybe_commit`; `upsert_subject` → `add_memory` (same); `link_part_of` →
`add_linkage_type` (`_maybe_commit`) and `link` (`_maybe_commit`). No bare `con.commit()` is
reached. {#commit-census-body}

### The replay tie (a decision beyond RED's tests) {#replay-tie}

26.2's path-refresh event re-logs a row with its UNCHANGED `updated_at`. With R11.3's `>=` guard
applied in replay too, that event would be skipped on `apply_log_delta` and lose to the write it
refreshes in the rebuild (a tie kept the first). So: a live write skips a tie (the dial and its
queued entry are one write, AC-4), while replay applies a tie in log order, and the rebuild's
winner breaks a tie by append `ts`. A log holds only writes that happened, so an equal-time later
event is a later state; this is `newest_by_ts`'s own rule (a tie goes to the later line).
{#replay-tie-body}

## Verify {#verify}

Lane logs in `workflow/review-output/` (scripts/lane-local.sh, committed shas):

- `hwq-green-r1` at `f76db480`: RED's five files, **88 passed**.
- `hwq-green-replay-r2` at `b1b8df4d`: every replay / facts.log / reclassify / retag / bridge-move
  test file plus `test_hook_writes` and `test_deferrals_clean`, **191 passed**.
- The verify set at `adf0ff1d` (308 files: every test file importing `store`, `daemon`,
  `verbs`, `cli`, `handoff` or `hook_writes`, plus the nine repo guards), three local-lane
  shards: `hwq-green-final-s0` **1544 passed**; `hwq-green-final-s2` **1388 passed**;
  `hwq-green-final-s1` **1669 passed, 2 failed, 1 xpassed** (the xpass is
  `test_task25_1_recall_budget` `replica-on`, a pre-existing non-strict xfail, bug-312). The two
  failures are tests that assert the pre-L212 contract (a busy daemon FAILS the save-state
  promote), reported to the lead, not edited: `test_plan3_remedy_r3::test_promote_digest_
  reports_busy_and_never_opens_the_store` and `test_bug212_r6_red::test_mcp_save_state_error_
  reply_carries_the_result` (it uses a busy daemon only to make the promote fail).
- The same set at `f76db480` (`hwq-green-verify-s0..s2`) also failed
  `test_bridge_move_safety::test_ac1b_legacy_refresh_survives_rebuild_from_log` ("replay
  restored legacy-x at .../a/x.md, not .../b/x.md"): the replay tie of #replay-tie, fixed in
  `b1b8df4d` and green since. {#verify-body}

## Self-audit {#self-audit}

```
1 real:     not run on the host (subagents are read-only against live stores; dev rmx on the
            host risks the hub version handshake). The lane runs the real entry points on
            real daemons: the GENERATED Stop command (run_hook), `rmx save-state`,
            `rmx daemon status`, `rmx memory get`, `rmx rebuild --from-log`.
2 wiring:   test_plan2_remedy::test_stop_promote_queues_and_exits_0_while_the_writer_is_held
            (generated Stop command, real held _store_lock, tick drain, memory get, subject
            recall); test_save_state::test_save_state_on_a_held_writer_queues_the_promote_
            and_exits_0 (`rmx save-state`); test_hook_writes::test_an_entry_queued_before_a_
            daemon_death_is_applied_by_the_boot_drain (SIGKILL + `rmx daemon start`).
3 census:   memory_content emitters: add_memory, refresh_memory_source_path (already carried
            it), reclassify_memories, retag_memory, dump_catalog_to_log -> all carry
            updated_at. Replay consumers: _apply_one_event, rebuild memory-bodies pass -> both
            pass it. _write_or_local callers: forget x3, _matrix_write (unchanged path),
            focus_summarize, _promote_digest (queued). Producers that dial memory_add
            themselves for a hook: focus_summarize only (no generated hook runs `memory add`);
            `verbs._memory_add_write` stays synchronous by R11.5. Left: the --global legs
            (R11 non-goal).
4 bound:    Stop: deadline at entry; probe daemon_status(retries=0) <= 0.5 s; dial
            timeout = deadline - now - 1.0, retries=0, skipped under 0.5 s; enqueue = one
            file write + 2 fsyncs; subject filing (success path only) gets what is left.
            Worst case ~ --timeout - 1.0 + the enqueue. save-state: the same over its own
            `timeout` (default 30, PreCompact passes what is left).
5 busy:     busy (silent socket) -> probe says busy -> queued, exit 0, one probe
            (test_stop_promote_says_busy_not_absent_on_a_silent_daemon); held writer -> dial
            times out -> queued (AC-1); down -> Stop refuses, exit 1, no spool (AC-5);
            save-state down -> in-process write (test_bug212_r5 promote probe).
6 guard:    add_memory guard fires on a stored row at least as new: reached by the dial that
            lands after its queued entry and vice versa (AC-4 both orders), by a later sync
            write (AC-3), by replay of a later-appended older event (route apply_log_delta).
            Bad-entry guard fires on not-JSON / not-UTF-8 / missing keys (AC-6, 3 params).
            Empty-spool guard: 0 lock acquisitions (AC-3 tail).
7 loud:     unwritable spool -> exit 1, "Permission denied ... hook_writes.spool" on the
            console (test_stop_promote_fails_loud_when_the_enqueue_fails); bad entry -> rmxd.log
            names it + health + `rmx daemon status` line; drain partition failure -> logged,
            counted `failed`, entries kept; fatal invalidation -> re-raised to the tick's
            fast-exit.
8 handoff:  D5 re-base on BoundedQueue -> workflow/deferral_registry.md row, linked to
            task-23.1-queue-and-drain#r11.
```

## Notes for review {#notes}

- `store.transaction()` rolls back the relational rows of a failed partition, but facts.log
  events written inside it and bits set in in-memory bitmap fragments are not rolled back.
  This is the existing behaviour of every `transaction()` user (the bridge included), not
  new here; a partition apply that raises is the rare path. {#note-rollback}
- Two existing tests assert the pre-L212 contract and are not among RED's conversions (see
  #verify); reported to the lead, not edited. {#note-r3}
- Not done here: the mutation pass on the `src/` change (the spec's large-change step), which
  belongs to the review stage. {#note-mutations}
