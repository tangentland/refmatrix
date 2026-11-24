---
gmd: "0.1"
id: task-hook-writes-queue
title: "Hook writes enqueue and return: 23.1 R11 pulled forward on an interim spool (bug-309, bug-177)"
tags: [task, hooks, stop-hook, promote, memory-add, queue, durability, bug-309, bug-177]
metadata:
  node_type: task
  status: approved
  created: 2026-11-24
---

# Task: hook writes enqueue and return {#root}

> Status: approved 2026-11-24 (L212; the user: "can't we just fix the contention as we see it
> now", after L211 made a durable `memory_add` the condition for dropping the Stop-hook warning).
> A large change (daemon, store, verbs, cli, handoff): RED and GREEN in separate hands, mutations
> on the `src/` change, one ch-bsd pass (L165).

rel: implements -> [[task-23.1-queue-and-drain#r11]]
rel: depends-on -> [[bug_registry]]
rel: amends -> [[task-23.1-queue-and-drain]]

## Why {#why}

The Stop hook's turn-end promote (`focus summarize --promote --timeout 8`) waits on the daemon's
single writer. Since 2026-11-23, 72 of 136 promotes timed out at 8.04 s and printed a hook error
(bug-309, measured 2026-11-24). Whatever holds `_store_lock` (being identified separately), the
hook should not wait on it. [[task-23.1-queue-and-drain#r11]] already specifies the cure and was
reviewed through 13 rounds; it is blocked only by 23.1's unbuilt core (R1-R3, `bounded.py`). This
task builds **R11's contract on an interim spool**, so the hook stops failing now and the write
is durable, which is L211's condition for dropping the warning. {#why-body}

## The contract is R11's, except these deltas {#deltas}

Everything in [[task-23.1-queue-and-drain#r11]] items 1-7 holds (entry shape; `newest_by_ts` with
the subject-label union; the `add_memory(updated_at=)` authoring-time guard with R11.3's three
`store.py` edits for the event and both replay paths; the fourth `_write_or_local` outcome with
`queue=`, `local=None`, `deadline=`, `ENQUEUE_RESERVE_S`, `MIN_DIAL_S`, `QUEUED_WRITE_MSG`; both
producers converged; `focus_summarize` computes its deadline first and drops its own probe;
`_promote_digest` uses `discovery.resolve_partition`; absent daemon still refuses with no queue
line), with these deltas: {#deltas-lead}

- **D1 Storage.** Not R3's `BoundedQueue`. One file per entry under `<store root>/hook_writes.spool/`,
  written exactly like `gmd_curator.write_spool` (`.tmp`, fsync, rename, fsync the directory),
  names `<time_ns:020d>-<uuid4>.json`. A small module `src/refmatrix/hook_writes.py` owns
  `enqueue`, `read_pending`, `newest_by_ts`, `drain`, and the startup `*.tmp` sweep. {#d1}
- **D2 Drain.** The daemon's existing flush thread runs `drain` on every tick (30 s) before the
  periodic flush, and once at boot after the store opens: ONE `_store_lock` acquisition, every
  pending entry read, coalesced by `(op, partition, name)` with `newest_by_ts`, applied in one
  transaction per partition (`add_memory(**args)` then each subject label's `upsert_subject` +
  `link_part_of`), and the applied spool files deleted only AFTER the commit. A crash between the
  commit and the delete re-applies them next time and the `updated_at` guard skips them
  (`superseded`). A snapshot is requested after a committing drain. {#d2}
- **D3 Unreadable entries** are counted, named in `rmxd.log`, moved to `hook_writes.spool/bad/`,
  never deleted and never silently skipped. {#d3}
- **D4 Status.** `_store_health` reports `hook_writes_pending` and `hook_writes_bad`; `rmx daemon
  status` prints a line when either is non-zero. No `queue_status` op (that is 23.1's R6.5). {#d4}
- **D5 Re-base later.** When 23.1 builds R3, it re-bases this spool on `BoundedQueue` the way its
  R9 re-bases `learn_queue`; a deferral row records it. {#d5}
- **D6 The warning.** On `queued` the Stop hook exits 0 and prints `queued: <name>` plus
  `QUEUED_WRITE_MSG`, so Claude Code shows no hook error. Absent daemon, refused, undiallable
  and an enqueue that fails (disk) stay loud: exit 1 with the cause. {#d6}

## Acceptance {#acceptance}

Through the entry points (the hook command, `rmx save-state`, the daemon), on a sandbox daemon
under a short `mkdtemp` root; the held writer is the real lock-hold fixture, never a patched
`ping` / `daemon.call`. {#acceptance-lead}

- **AC-1 Busy → queued, exit 0.** With the writer held, the generated Stop command exits 0 within
  `--timeout`, prints `queued: focus_summary_<slug>` and the message, and leaves one spool file.
  After the hold is released and one tick runs, `rmx memory get` shows the digest and the spool is
  empty. (Mutations: the hook dials without `queue=` → times out, exit 1; drain never deletes →
  spool not empty.) {#ac-1}
- **AC-2 Survives a daemon death.** Enqueue under a held writer, SIGKILL the daemon before any
  tick, start it again: the boot drain applies the entry. (Mutation: no boot drain → fails.) {#ac-2}
- **AC-3 Newest authoring time wins.** Two queued entries for one name (ts T1 < T2, appended in
  the order T2 then T1) and a later synchronous write at T3 > T2: the stored content is T3's, and
  the drain counts the two queued entries `superseded`; without T3, it is T2's. (Mutations: merge
  by line order; drop the `add_memory` guard → fails.) {#ac-3}
- **AC-4 One write when both land.** A timed-out dial that lands after release plus its queued
  entry (same `updated_at`) leave one row and ONE `memory_content` event in `facts.log`. {#ac-4}
- **AC-5 Absent daemon refuses.** No daemon: the Stop command exits 1 with today's refusal and
  writes no spool file. {#ac-5}
- **AC-6 Nothing silent.** A malformed spool file is counted, logged, moved to `bad/`, and shows
  in `_store_health` and `rmx daemon status`; a failing enqueue (unwritable dir) exits 1 with the
  cause. {#ac-6}
- **AC-7 Replay keeps the authoring time.** After `rebuild --from-log`, a queued entry authored
  before the rebuild still applies (R11.3 item 3; mutation: drop `updated_at` from the event →
  fails). {#ac-7}
- **AC-8 Save-state promote.** `rmx save-state` with the writer held prints the queued note in
  place of `promoted … (id=…)`, exits 0, and the digest lands at the next drain. {#ac-8}

## Files {#files}

`src/refmatrix/hook_writes.py` (new), `daemon.py` (tick + boot drain, `_store_health`,
`_op_memory_add` passes `updated_at`), `store.py` (R11.3), `verbs.py` (`_write_or_local` R11.4),
`cli.py` (`focus_summarize`, `daemon status` line), `handoff.py` (`_promote_digest`, the queued
render); tests in the existing promote / Stop-hook test files (CLAUDE.md test discipline rule 1),
plus `tests/test_hook_writes.py` for the module; `workflow/test_mock_registry.md` if a boundary is
faked; `workflow/deferral_registry.md` (D5).
