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
> Status: Pending (added 2026-10-14 after commit 32dde06; first reviewed in
> [[bsd-plan23-17-spec-rereview-r3-6091648]]; revision round 3: ns17-r3-3, ns17-r3-4, nm17-r3-6,
> see [[#rev-round-3]]. Revision round 5: ns17-r4-2, nm17-r4-1, see [[#rev-round-5]]. Round 2:
> [[#rev-round-2]])
> Depends on: 17.2 (the hub tick and its `maintenance_steps` registry, NOT 23.1's daemon tick
> registry), 23.0 (sandbox)

rel: part-of -> [[plan-17-nightly-store-maintenance]]
rel: depends-on -> [[task-17.2-hub-nightly-tick]]
rel: depends-on -> [[task-23.0-test-sandbox]]
rel: related-to -> [[project_factslog_audit_verdict]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-32dde06#nm17-4]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-32dde06#ns17-5]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r3-6091648#ns17-r3-3]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r3-6091648#ns17-r3-4]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r3-6091648#nm17-r3-6]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r4-878647c#ns17-r4-2]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r4-878647c#nm17-r4-1]]

## Why {#why}

The user, 2026-10-14: "spec the facts.log daily rotation". Time Machine's `backupd` was running hot
(76% CPU, load average 26) because every refmatrix store is inside the backup set and rewrites
large files constantly. The catalogs and Lance vectors are being excluded by fixed path (the
user's `tm-exclusions.sh`, options b and c). That leaves `facts.log`: 261 MB in this project
alone, appended on every write, so Time Machine copies the whole file on every hourly backup.

It is also the one store file that cannot be regenerated from source: learned grep rows and
protect/noise flags exist only in the catalog and in `facts.log` (curated memories live in
`~/.claude/projects/…/memory`, backed up separately). So it cannot simply be excluded.

**Why not rotate the live log into daily segments.** The live log is the replay source of
`rmx rebuild --from-log` (`Store.rebuild_index_from_log`), and compaction
(`_compact_factslog_if_needed`, `daemon.py:2274`; `Store.dump_catalog_to_log`) rewrites the whole
file atomically. Segmenting it would change replay, compaction and the rebuild. Out of proportion
to the goal, which is only to give the backup a file that changes once a day. (Round 3 also said
"delta-replay reads from" the A/B slot offsets. That is false at HEAD `39dffbb`: offsets are
written, by compaction at `daemon.py:2318-2321` and by the rotation bootstrap at `:2841-2846`,
but `_read_slot_offset` (`daemon.py:2796`) has no caller, and writer rotation and its refresh
thread are dropped (`_refresh_replica_now`, `daemon.py:2812-2826`; ns17-r4-2, nm23-r4-2).)

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
     changes")`, registered FIRST on `maintenance_steps` (17.2 R2, ns17-r3-3). It therefore runs
     for real from its first scheduled day, needs no `hub_maintain_arm`, and runs before, and
     independently of, every other step on the same store: a `still_running`, `stuck`, failed or
     refused `vectors_maintain` (or any later step) never stops the day's copy (17.2 R2).
   - **The step obligations of 17.2 R2:** `dry_run=True` reports what it would copy (source
     inode and size, target path) and writes nothing; `invoked_by` (`cli` / `mcp` / `hub`, set by
     the adapter, 17.1 R1) is accepted and recorded; single-flight
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
   - **The clone call, stated (nm17-r3-6).** Python has no `fclonefileat` binding. The op calls
     it through `ctypes`: `libc = ctypes.CDLL(None, use_errno=True)`;
     `libc.fclonefileat(c_int(src_fd), c_int(AT_FDCWD = -2), c_char_p(tmp_path_bytes),
     c_uint32(0))`; a non-zero return reads `ctypes.get_errno()`. `ENOTSUP` / `EXDEV` (a volume
     without clones) falls back to the streamed copy and reports `method: "stream"`; any other
     errno is a named failure (R5). The report says which method ran (`clone` / `stream`).
5. **R5 No silent failure.** Any failure (missing log, ENOSPC, rename error) is returned as a
   named error, counted in the (store, step) stamp, and reaches 17.2's per-step alert
   (`#r5-alert`). The previous good copy is never deleted by a failed run. A run that is still
   running past 17.2's ceiling becomes `stuck` like any other step (17.2 R4).
   - **A copy that stops being made is loud too (ns17-r3-3).** R5's errors cover runs that
     execute. The copy can also stop without any run failing: `RMX_HUB_MAINTAIN_AT=off`, the hub
     down or its thread dead, or a step that never gets called. That is caught by AGE, not by a
     run: the daemon's health reports `factslog_backup_age_h` / `factslog_backup_stale` (over 48 h)
     from the meta file, and the hub alerts once per stale store on every wake, due or not
     (17.2 `#r8-backup-age`). The exclusion of the live log (R7) is permanent, so this alarm is
     what keeps it safe.
6. **R6 Restore: two scenarios, each with its own path (ns17-r3-4, ns17-r4-2).** {#r6-restore}
   The catalog is the authority and the log is re-derivable from it, so which file is restored
   from which depends on what was lost. The runbook (17.3 R3) names both; the script refuses the
   case it does not serve.
   - **(a) The live log is damaged or missing, and the catalog is healthy.** The backup is NOT
     used: a day-old copy installed beneath a newer catalog would lose that day from the log.
     The fix is a forced compaction, `rmx compact-log --force` (daemon up: the
     `compact_factslog` op, `daemon.py:4020`; it rewrites the full log from the catalog by
     `dump_catalog_to_log`, atomic tmp + rename). Nothing is lost. `scripts/factslog-restore.py`
     detects this case (an active-slot catalog file exists in the live root and opens) and
     refuses with the message "catalog present: run `rmx compact-log --force`, not a restore".
   - **(b) The disaster 17.4 exists for: the catalog is gone.** The catalogs and Lance data
     are excluded from Time Machine (#why) and so is the live log (R7), so after a machine
     restore only `backups/` comes back for this store. `scripts/factslog-restore.py <root>`
     (run with the DEPLOY interpreter) then, in this order:
     1. **Refuses while the store's daemon answers** `daemon_mod.ping(root)` (checked first and
        again before step 5; the daemon is stopped by hand).
     2. **Rebuilds into a THROWAWAY root:** copies `backups/facts.log.daily` to
        `<mkdtemp>/.refmatrix/facts.log` and runs `rmx rebuild --from-log --yes` there with
        `REFMATRIX_ROOT=<mkdtemp>` (the command rebuilds whatever store `_store()` resolves, so
        the env var keeps it off the live root).
     3. **Verifies** the throwaway's entity, link and learned-evidence counts against the copy's
        own event counts (AC-3's check) and prints them; a mismatch stops here with the live root
        unchanged.
     4. **Moves aside, never deletes,** anything already in the live root that step 5 would
        replace: `facts.log`, `catalog.A.duckdb`, `catalog.B.duckdb`, `catalog.duckdb`,
        `catalog.read.duckdb` and their `.wal` files, each renamed to `<name>.pre-restore-<ts>`.
     5. **Promotes the verified throwaway into the live root:** the throwaway's catalog file is
        copied (+ `fsync`) to the file the live `Store` will open as its writer slot: if the
        live root's `active` marker names slot X, `catalog.X.duckdb`; with no marker,
        `catalog.duckdb` (the daemon's rotation bootstrap then migrates it, as for any
        pre-rotation store). The copy is installed as the live `facts.log` by copy + `fsync` +
        rename, so the installed log is the log the promoted catalog was rebuilt from.
     6. **Writes the slot offsets only as consistent bookkeeping:** both `catalog.A.offset` and
        `catalog.B.offset` (where present) are set to the installed log's size, as compaction
        does. Nothing reads them at HEAD (#why), so this is consistency with the promoted slot,
        not a correctness step, and it has no AC of its own.
     7. **Prints the follow-up** the operator runs: start the daemon (`rmx daemon start`); Lance
        vectors are not in the log and are not restored by this script, so the runbook names
        the store's embed path to regenerate them.
   Up to one day of events is lost in scenario (b) by design (the copy is daily). Scenario (a)
   loses nothing. Running the script against a live root is store surgery: the runbook says to
   announce it and to keep the moved-aside files until the restored store is verified.
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
3. **AC-3 Replay equivalence against the SOURCE catalog (nm17-r3-6).** A test writer drives a tmp
   `Store`; at a quiesced point the test records the SOURCE catalog's entity and link counts and
   a name-keyed hash of `entities` and `entity_links`, then the op copies the log, then the writer
   resumes and appends more. `rmx rebuild --from-log` on a tmp root seeded from the copy yields
   exactly the recorded counts and hash (the copy replays to the catalog state at the copy's
   offset, not merely to "whatever the same bytes replay to"). Mutation: a copy that includes the
   post-copy appends FAILS (counts above the recorded ones).
4. **AC-4 Unchanged means untouched.** With no appends since the last copy, the backup file's
   mtime and inode do not change.
5. **AC-5 Failure is loud and non-destructive.** With `backups/` made read-only, the op returns a
   named error, the stamp records the failure, `.daily` and `.prev` are byte-identical to before.
6. **AC-6 Mutations that must FAIL a test:** take the size after the copy instead of at open
   (AC-2); drop the newline truncation (AC-2); copy by path instead of by the open descriptor
   (AC-2 compaction case); delete `.prev` before the rename (AC-5); skip the unchanged check
   (AC-4); register the step with `requires_arming=True` (AC-7: the unarmed store gets no copy);
   drop the `runs.jsonl` line (AC-7); register the step after `vectors_maintain`, or skip it
   while an earlier step is `still_running` (AC-8); drop the age check (AC-8); the restore script
   copying over the live log before the throwaway rebuild (AC-9);
   the streamed fallback removed (AC-10); the restore script promoting nothing into the live
   root (AC-9 scenario (b): the daemon starts with an empty catalog); the restore script
   installing the copy when a healthy catalog is present (AC-9 scenario (a)).
7. **AC-7 Step obligations (17.2 R2, ns17-5).** Registered with `requires_arming=False`, the step
   runs for real (a copy appears) on the first due day of an UNARMED store; a dry run writes
   nothing; a second call during a blocked copy returns `already_running`, and `status=True`
   returns within 1 s; each completed run appends one `runs.jsonl` line with
   `step: "factslog_backup"`.

8. **AC-8 The copy is independent and its absence is loud (ns17-r3-3).** One tmp store, its
   `vectors_maintain` op blocked on an event (17.2 AC-10's shape): on the due day the backup step
   still copies (a new `.daily`, a `runs.jsonl` line). Then the injected clock advances 3 days with
   no step due and with `RMX_HUB_MAINTAIN_AT=off`: the next hub wake publishes exactly one
   stale-backup alert naming the store. The daemon side reads its OWN wall clock, which no
   hub clock injection reaches (nm17-r4-1), so for that clause the test BACK-DATES the meta
   file instead (17.2 AC-14's shape): `copied_at` in `backups/facts.log.daily.meta.json` is
   rewritten to 3 days before the daemon's now; then `_store_health` reports
   `factslog_backup_stale: true` and `factslog_backup_age_h` >= 72 with the hub stopped.
9. **AC-9 The restore runbook, both scenarios (ns17-r3-4, ns17-r4-2).** {#ac-9}
   - **Scenario (b), the disaster.** A tmp store whose daemon has run: learned grep rows
     (`linkage_evidence` rows written by learn) and ordinary rows exist, the daily copy is
     taken, then more appends. The test then deletes every catalog file (`catalog.*.duckdb`,
     `catalog.read.duckdb`, their `.wal`) AND the live `facts.log`, keeping `backups/` and the
     `active` marker, as a Time Machine restore of an excluded store would. With the daemon
     running the script refuses and changes nothing. With it stopped: the throwaway rebuild
     runs and verifies first (a corrupted copy stops the script with the live root unchanged);
     the script promotes the catalog and installs the copy; the test starts the daemon; the
     store's entity count, link count and learned-evidence row count equal the counts recorded
     at the copy point (AC-3's), and a read through the daemon returns a learned row.
   - **Scenario (a), log only.** The same store with its catalog intact and `facts.log`
     truncated to half: the script refuses with the "run `rmx compact-log --force`" message and
     changes nothing; `rmx compact-log --force` then restores a log whose replay (AC-3's check)
     equals the live catalog, with the post-copy appends included.
   - Until step 5 the script writes nothing in the tmp store's own root, and any file it
     replaces is at `<name>.pre-restore-<ts>`, byte-identical to before.
10. **AC-10 Both copy methods (nm17-r3-6).** On the sandbox volume the op reports
    `method: "clone"` when `fclonefileat` succeeds; with a test seam that makes the call return
    `ENOTSUP`, it reports `method: "stream"`, and both copies are byte-identical to the old
    inode's prefix cut at its last newline (AC-2's check).

## Files to modify {#files-to-modify}

| file | change |
|---|---|
| `src/refmatrix/daemon.py` | `_op_factslog_backup` (R1-R5) |
| `src/refmatrix/verbs.py` | `factslog_backup` verb (CLI + MCP parity) |
| `src/refmatrix/hub.py` (17.2 `maintenance_steps`) | register the step, `requires_arming=False` |
| `scripts/factslog-restore.py` | R6's restore: refuses scenario (a); for scenario (b) throwaway rebuild, verify, move aside, promote the catalog, install the log, print the follow-up |
| `docs/` runbook (17.3) | both restore scenarios (R6: (a) `rmx compact-log --force`, (b) the script, then the daemon start and re-embed), exclusion order (R7), the backup-age alarm (R5) |

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

## Revision round 3 (2026-10-14) {#rev-round-3}

Source: [[bsd-plan23-17-spec-rereview-r3-6091648]] (17.4's first review).

| finding / decision | answered at |
|---|---|
| ns17-r3-3 (no staleness alarm after the TM exclusion; step order) | R1 (registered FIRST, independent of later steps), R5 (age alarm), AC-8; 17.2 [[task-17.2-hub-nightly-tick#r2-registry]], [[task-17.2-hub-nightly-tick#r8-backup-age]] |
| ns17-r3-4 (restore runbook overwrites the live log; slot offsets ignored) | R6 (ordered `scripts/factslog-restore.py`; offsets reset to the new EOF), AC-9, [[#files-to-modify]] |
| nm17-r3-6 (AC-3 compared identical bytes; `fclonefileat` has no binding) | AC-3 (against the source catalog), R3 (the `ctypes` call; fallback reported), AC-10 |
| nm17-r3-2 (`invoked_by` is the surface) | R1 |

## Revision round 5 (2026-10-14) {#rev-round-5}

Source: [[bsd-plan23-17-spec-rereview-r4-878647c]].

| finding / decision | answered at |
|---|---|
| ns17-r4-2 (restore never restores the catalog; resets offsets nothing reads; serves no stated failure) | [[#why]] (offsets unread, corrected), [[#r6-restore]] (scenario (a) = forced compaction, refused by the script; scenario (b) = throwaway rebuild, verify, move aside, PROMOTE the catalog, install the log; offsets as bookkeeping only), [[#ac-9]] (both scenarios; learned rows counted after a daemon start), AC-6 mutations, [[#files-to-modify]] |
| nm17-r4-1 item 1 (AC-8's daemon clause cannot pass under an injected hub clock) | AC-8 (the meta file is back-dated for the daemon clause) |

