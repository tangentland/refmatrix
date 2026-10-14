---
gmd: "0.1"
id: task-17.4-factslog-backup-snapshot
title: "Task 17.4: a once-a-day facts.log backup copy, so Time Machine can skip the live log"
tags: [task, facts-log, backup, time-machine, maintenance]
metadata:
  node_type: task
  status: pending
  created: 2026-10-14
  updated: 2026-10-14
---

# Task 17.4: daily facts.log backup copy {#root}

> Plan: [plan-17-nightly-store-maintenance](../plan-17-nightly-store-maintenance.md)
> Status: Pending (added 2026-10-14 after commit 32dde06; NOT covered by the 32dde06 re-review —
> review in the next round)
> Depends on: 17.2 (the tick and its step registry), 23.0 (sandbox)

rel: part-of -> [[plan-17-nightly-store-maintenance]]
rel: depends-on -> [[task-17.2-hub-nightly-tick]]
rel: depends-on -> [[task-23.0-test-sandbox]]
rel: related-to -> [[project_factslog_audit_verdict]]

## Why {#why}

The user, 2026-10-14: "spec the facts.log daily rotation". Time Machine's `backupd` was running hot
(76% CPU, load average 26) because every refmatrix store is inside the backup set and rewrites
large files constantly. The catalogs and Lance vectors are being excluded by fixed path (the
user's `tm-exclusions.sh`, options b and c). That leaves `facts.log`: 261 MB in this project
alone, appended on every write, so Time Machine copies the whole file on every hourly backup.

It is also the one store file that cannot be regenerated from source: learned grep rows and
protect/noise flags exist only in the catalog and in `facts.log` (curated memories live in
`~/.claude/projects/…/memory`, backed up separately). So it cannot simply be excluded.

**Why not rotate the live log into daily segments.** The live log is the replication transport:
the A/B slot offsets are byte positions into it (`daemon.py:2789` `_slot_offset_path`,
`_write_slot_offset` `:2805`), delta-replay reads from those offsets, and compaction
(`_compact_factslog_if_needed`, `daemon.py:2274`; `Store.dump_catalog_to_log`, `store.py:7210`)
rewrites the whole file atomically and resets both offsets. Segmenting it would change the
offset model, replay, compaction and `rmx rebuild --from-log`. Out of proportion to the goal,
which is only to give the backup a file that changes once a day.

So: the live `facts.log` keeps its contract unchanged and is excluded from Time Machine; a
once-a-day COPY under `backups/` is what Time Machine backs up. {#why-body}

## Requirements {#requirements}

1. **R1 Daily copy as a maintenance step.** A `factslog_backup` daemon op, registered as its own
   step on 17.2's tick (one tick, plan-review C6), copies `<store>/facts.log` to
   `<store>/backups/facts.log.daily` once per local day per store. It runs on every store the
   tick visits (the registered daemon list, 17.2 `#r3-roots`), including the global store.
2. **R2 Consistent without the lock.** The log is append-only between compactions, and compaction
   swaps it by atomic rename. The op opens `facts.log` once, records the size at open, copies
   exactly that many bytes from the open descriptor, and truncates the copy back to its last
   complete newline. A compaction during the copy cannot tear it, because the open descriptor keeps
   the old inode. The op never takes `_store_lock` and holds no writer state.
3. **R3 Cheap on disk, one change per day for the backup.** The copy is written to
   `backups/facts.log.daily.tmp` (an APFS clone via `clonefile` where the volume supports it,
   otherwise a streamed copy), `fsync`ed, then renamed over `backups/facts.log.daily`. One
   previous copy is kept as `backups/facts.log.daily.prev` (renamed before the swap). At most two
   copies exist; there are no unbounded dated files.
4. **R4 Skip when nothing changed.** If the log's (inode, size) equals the values recorded at the
   last copy, the op writes nothing and reports `skipped: unchanged`, so an idle store's backup
   file does not change and Time Machine copies nothing for it.
5. **R5 No silent failure.** Any failure (missing log, ENOSPC, rename error) is returned as a
   named error, counted in the (store, step) stamp, and reaches 17.2's per-step alert
   (`#r5-alert`). The previous good copy is never deleted by a failed run.
6. **R6 A restore path that is tested.** The runbook names the restore:
   `cp backups/facts.log.daily facts.log` with the daemon stopped, then `rmx rebuild --from-log`
   into a THROWAWAY root first. Up to one day of events is lost by design; the catalog itself is
   the primary copy of the live state.
7. **R7 Time Machine exclusion of the live log comes AFTER the copy exists.** 17.3's rollout adds
   `sudo tmutil addexclusion -p <store>/facts.log` for a store only after that store has a
   `backups/facts.log.daily` no older than one day. `backups/` stays included in Time Machine.
   `sessions/`, `stm/` and `compiled/` stay included.

## Acceptance criteria {#acceptance}

All in 23.0's sandbox, on tmp stores; no live store is touched.

1. **AC-1 One copy per day.** Two tick runs on the same injected day produce one copy (the second
   run reports `skipped: already-today` or `skipped: unchanged`); a run on the next injected day,
   after appends, produces a new copy, and the old one becomes `.prev`.
2. **AC-2 Consistency under a concurrent append and a concurrent compaction.**
   - A writer thread appends while the copy runs: the copy ends on a newline and every line in it
     parses as JSON.
   - A compaction swaps the log mid-copy: the copy is a valid prefix of either the old or the new
     file, never a mix (byte-compare against both).
3. **AC-3 Replay equivalence.** `rmx rebuild --from-log` on a tmp root seeded from the copy yields
   the same entity and link counts as the source store at the copy's size (a log replayed to the
   same byte offset).
4. **AC-4 Unchanged means untouched.** With no appends since the last copy, the backup file's
   mtime and inode do not change.
5. **AC-5 Failure is loud and non-destructive.** With `backups/` made read-only, the op returns a
   named error, the stamp records the failure, `.daily` and `.prev` are byte-identical to before.
6. **AC-6 Mutations that must FAIL a test:** take the size after the copy instead of at open
   (AC-2); drop the newline truncation (AC-2); copy by path instead of by the open descriptor
   (AC-2 compaction case); delete `.prev` before the rename (AC-5); skip the unchanged check
   (AC-4).

## Files to modify {#files-to-modify}

| file | change |
|---|---|
| `src/refmatrix/daemon.py` | `_op_factslog_backup` (R1-R5) |
| `src/refmatrix/verbs.py` | `factslog_backup` verb (CLI + MCP parity) |
| hub step registry (17.2) | register the step |
| `docs/` runbook (17.3) | restore path (R6), exclusion order (R7) |

## Test strategy {#test-strategy}

Every test runs in 23.0's sandbox (tmp `HOME`, global root, registry, injected roots, the guard
that fails on a live store). The day is injected (17.2's injected clock). The concurrent append
and compaction in AC-2 use threads in-process against a tmp `Store`, not a live daemon.

## Out of scope {#out-of-scope}

Segmenting the live log (see #why-body). Off-machine backup. Changing compaction.
