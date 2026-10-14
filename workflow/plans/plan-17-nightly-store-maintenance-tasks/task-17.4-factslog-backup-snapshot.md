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
> Status: Pending (added 2026-10-14 after commit 32dde06; checked in revision round 2 against the
> 32dde06 re-review's plan-17 findings, see [[#rev-round-2]]; its first review is the next round)
> Depends on: 17.2 (the hub tick and its `maintenance_steps` registry, NOT 23.1's daemon tick
> registry), 23.0 (sandbox)

rel: part-of -> [[plan-17-nightly-store-maintenance]]
rel: depends-on -> [[task-17.2-hub-nightly-tick]]
rel: depends-on -> [[task-23.0-test-sandbox]]
rel: related-to -> [[project_factslog_audit_verdict]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-32dde06#nm17-4]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-32dde06#ns17-5]]

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

1. **R1 Daily copy as a maintenance step.** A `factslog_backup` daemon op and verb, registered
   on 17.2's hub `maintenance_steps` (17.2 R2; plan-review C6's one hub tick), copies
   `<store>/facts.log` to `<store>/backups/facts.log.daily` once per local day per store. It runs
   on every store the tick visits (the registered daemon list, 17.2 `#r3-roots`), including the
   global store.
   - **Registration** (ns17-5): `MaintenanceStep(name="factslog_backup", op="factslog_backup",
     requires_arming=False, reason="a copy; never deletes the last good copy; no store state
     changes")`. It therefore runs for real from its first scheduled day and needs no
     `hub_maintain_arm`.
   - **The step obligations of 17.2 R2:** `dry_run=True` reports what it would copy (source
     inode and size, target path) and writes nothing; `invoked_by` is accepted; single-flight
     with the 17.1 R11 reply shape, and `status=True` answered from an in-process run state
     without `_store_lock`; every completed run appends one `<root>/maintain/runs.jsonl` line
     with `step: "factslog_backup"` (17.1 R12 shape).
   - **The day comes from the caller** (op args cannot carry a callable): 17.2 passes `today`
     (its injected clock's local date); a hand call defaults to the daemon's local date.
2. **R2 Consistent without the lock.** The log is append-only between compactions, and compaction
   swaps it by atomic rename. The op opens `facts.log` once, records the size at open, copies
   exactly that many bytes from the open descriptor, and truncates the copy back to its last
   complete newline. A compaction during the copy cannot tear it, because the open descriptor keeps
   the old inode. The op never takes `_store_lock` and holds no writer state.
3. **R3 Cheap on disk, one change per day for the backup.** The copy is written to
   `backups/facts.log.daily.tmp` FROM THE OPEN DESCRIPTOR of R2 (an APFS clone through
   `fclonefileat(fd, …)` where the volume supports it, then truncated to R2's size and last
   newline; otherwise a streamed copy of R2's byte count from that descriptor; never `clonefile`
   or `shutil.copy` by path, which could read a newer inode), `fsync`ed, then renamed over
   `backups/facts.log.daily`. One
   previous copy is kept as `backups/facts.log.daily.prev` (renamed before the swap). At most two
   copies exist; there are no unbounded dated files.
4. **R4 Skip when nothing changed, or already done today.** The values of the last good copy are
   kept in `backups/facts.log.daily.meta.json` (`{inode, size, copied_day, copied_at}`, written
   by tmp + rename after the copy's rename). If the log's (inode, size) equals the recorded
   values, the op writes nothing and reports `skipped: unchanged`, so an idle store's backup file
   does not change and Time Machine copies nothing for it. If `copied_day` equals `today`, it
   reports `skipped: already-today`.
5. **R5 No silent failure.** Any failure (missing log, ENOSPC, rename error) is returned as a
   named error, counted in the (store, step) stamp, and reaches 17.2's per-step alert
   (`#r5-alert`). The previous good copy is never deleted by a failed run. A run that is still
   running past 17.2's ceiling becomes `stuck` like any other step (17.2 R4).
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
   - A compaction swaps the log mid-copy: the copy equals the OLD file's first `size_at_open`
     bytes cut to its last newline (the descriptor pins the old inode), byte for byte. A copy of
     the new file, or a mix, fails.
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
   (AC-4); register the step with `requires_arming=True` (AC-7: the unarmed store gets no copy);
   drop the `runs.jsonl` line (AC-7).
7. **AC-7 Step obligations (17.2 R2, ns17-5).** Registered with `requires_arming=False`, the step
   runs for real (a copy appears) on the first due day of an UNARMED store; a dry run writes
   nothing; a second call during a blocked copy returns `already_running`, and `status=True`
   returns within 1 s; each completed run appends one `runs.jsonl` line with
   `step: "factslog_backup"`.

## Files to modify {#files-to-modify}

| file | change |
|---|---|
| `src/refmatrix/daemon.py` | `_op_factslog_backup` (R1-R5) |
| `src/refmatrix/verbs.py` | `factslog_backup` verb (CLI + MCP parity) |
| `src/refmatrix/hub.py` (17.2 `maintenance_steps`) | register the step, `requires_arming=False` |
| `docs/` runbook (17.3) | restore path (R6), exclusion order (R7) |

## Test strategy {#test-strategy}

Every test runs in 23.0's sandbox (tmp `HOME`, global root, registry, injected roots, the guard
that fails on a live store). The day is injected (17.2's injected clock). The concurrent append
and compaction in AC-2 use threads in-process against a tmp `Store`, not a live daemon.

## Out of scope {#out-of-scope}

Segmenting the live log (see #why-body). Off-machine backup. Changing compaction.

## Revision round 2 (2026-10-14) {#rev-round-2}

Checked against the 32dde06 re-review's plan-17 findings it inherits (nm17-4).

| finding / decision | answered at |
|---|---|
| nm17-4 (17.4 unreviewed, inherits ns17-5) | this table; plan-17 [[plan-17-nightly-store-maintenance#rev-round-2]] |
| ns17-5 (per-step arming owner) | [[#requirements]] R1 (registration, `requires_arming=False` with reason), AC-7 |
| ns17-1 (17.2's registry is the hub's `maintenance_steps`, not 23.1's) | header, R1 |
| 17.2 R2 step obligations (dry run, single-flight, lock-free status, `runs.jsonl`) | R1, AC-7 |
| ns17-4 (`stuck` ceiling applies to every step) | R5 |
| a vacuous mutation found in this check: "copy by path" could not fail an AC that accepted a prefix of either file | R3 (`fclonefileat` from the descriptor), AC-2 (old file only) |
| R4's "values recorded at the last copy" had no stated home; "already-today" had no source of `today` | R1 (`today` from the caller), R4 (meta file) |
