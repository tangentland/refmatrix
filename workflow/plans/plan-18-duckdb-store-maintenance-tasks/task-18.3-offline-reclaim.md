---
gmd: "0.1"
id: task-18.3-offline-reclaim
title: "Task 18.3 (CONDITIONAL): an offline, hand-run catalog reclaim — rehearse on a copy, stop the daemon under a watchdog pause and daemon.lock, rewrite the writer slot in a child, gate it, swap it, restart through launchd, roll back on any mismatch"
tags: [task, duckdb, catalog, reclaim, offline, conditional, maintenance]
metadata:
  node_type: task
  status: pending
  created: 2026-10-15
  updated: 2026-10-15
---

# Task 18.3 (CONDITIONAL): offline catalog reclaim {#root}

> Plan: [plan-18-duckdb-store-maintenance](../plan-18-duckdb-store-maintenance.md)
> Status: Pending, and **CONDITIONAL**. It is built only if BOTH of these hold:
> (1) 18.1's verdict puts at least one store in band A1 or A2 with C0 or C1
>     ([[task-18.1-catalog-measurement#r5]]); and
> (2) the user lifts C12 for an OFFLINE, hand-run reclaim (plan open question Q1).
> Otherwise it is CLOSED with 18.1's report as the reason.
> Wave: 4 ([[plan-review-2026-10-14#t10-waves]]), after 18.1's verdict.
> Depends on: 18.1 (the bands and the rehearsal it must match), 18.2 (the `catalog` CLI group,
> `catalog_state.json`, whose baseline a reclaim resets), 23.0 (test sandbox, including its
> tier-2/3 lanes for the launchd path, d9x).
> Not on 17.2's tick: an offline rewrite is not a daemon op, and 17.2 R3 skips a paused store
> (R9).

rel: part-of -> [[plan-18-duckdb-store-maintenance]]
rel: depends-on -> [[task-18.1-catalog-measurement]]
rel: depends-on -> [[task-18.2-catalog-maintain-step]]
rel: depends-on -> [[task-23.0-test-sandbox]]
rel: related-to -> [[plan-review-2026-10-07#consolidations]]
rel: related-to -> [[plan-review-2026-10-14#t12-approvals]]
rel: depends-on -> [[feedback_decay_never_loses_knowledge]]
rel: depends-on -> [[feedback_hub_restart_via_launchctl]]
rel: related-to -> [[refmatrix/adr-0004-unified-location-space-index#rule-no-delete]]

## Why {#why}

On DuckDB 1.5.3 only a rewrite gives free blocks back ([[task-18.1-catalog-measurement#facts]]
F2). The one rewrite tool that exists, `rmx compact` (F3), is unsafe on today's fleet, for four
reasons:

- It stops the daemon without pausing the hub watchdog, so the watchdog can restart the daemon
  mid-rewrite (`hub.py` `_check`, `:257-321`).
- It restarts with `spawn_daemon`, outside launchd (`feedback_hub_restart_via_launchctl`).
- It opens the slot in-process.
- It swaps with two renames and checks nothing.

C12 kept plan-18 off slot rewrites "until the helix plan decides whether manifests replace A/B
slot reconciliation" ([[plan-review-2026-10-07#consolidations]]). That reconciliation is gone:
writer rotation is dropped and the inactive slots are frozen (d9ao). A rewrite of the WRITER slot
in place, with the store offline, touches no reconciliation. This task is that rewrite, if 18.1
says it pays and the user agrees. {#why-body}

## Facts at HEAD `55f043d` (`src/` unchanged through `0611d2f`) {#facts}

The catalog facts F1-F7 are in [[task-18.1-catalog-measurement#facts]], and the lock and liveness
facts L1-L6 in [[task-18.2-catalog-maintain-step#facts]]. The offline-path facts:

- **O1 Stopping stays stopped.** The LaunchAgent's `KeepAlive` is `{SuccessfulExit: false}`
  (`launchctl.py:258`). A clean stop exits 0 and is not respawned. `daemon.stop_daemon`
  (`daemon.py:6594`) signals first and never SIGKILLs a daemon with a fresh heartbeat; it returns
  False instead.
- **O2 The hub watchdog** restarts a root with no process after 2 consecutive no-process ticks,
  unless the root is paused (`hub.py:257-300`). `Watchdog.pause(root, seconds)` (`hub.py:207`)
  and `is_paused` (`:221`) exist, and the CLI reaches them through `_watchdog_pause` /
  `_watchdog_resume` (`cli.py:2885`). That path is best-effort: a hub that is down is printed
  and the caller proceeds.
- **O3 `daemon.lock`.** A supervised start (`serve_foreground`, `daemon.py:6708`) takes
  `daemon.lock` with `LOCK_EX | LOCK_NB` and refuses ("another daemon spawn holds") when it is
  held (`:6747-6755`). `spawn_daemon` (`:6306`) BLOCKS on the same lock (`:6342`).
- **O4 Restart through launchd** is `launchctl.kickstart(root)` (`launchctl.py:827`). The boot
  path re-binds the slot named by the `active` marker, reconciles the marker, and takes a fresh
  snapshot (`daemon.py:1712-1791`), so `catalog.read.duckdb` and the mem mirror are rebuilt from
  the new file. A new process has no DuckDB instance cache, so bug-112 cannot serve the old file.
- **O5 Health already proves the binding.** `_store_health` reports `db_file`, `active_slot`
  and `slot_bound` (`daemon.py:3787-3796`).

{#facts-body}

## Requirements {#requirements}

1. **R1 Verb, two modes, one ledger.** Verb `rmx_catalog_reclaim(rehearse: bool = True,
   confirm: str | None = None, window: bool = False, *, invoked_by: str) -> dict`, with
   `invoked_by` from the closed set `{cli, mcp}` (adapter-set, 17.1 R1; `hub` is not in the set,
   because the hub never reclaims). It is exposed as CLI `rmx catalog reclaim [--confirm <run_id>]
   [--window]` and through MCP via the verb-parity test. The gate is the record, not the surface
   (d8g): a real run needs a rehearsal the caller has read. Every completed run appends one
   `<root>/maintain/runs.jsonl` line with `step: "catalog_reclaim"` (17.1 R12 shape). {#r1-verb}
2. **R2 The rehearsal** (`rehearse=True`, the default). It runs with the daemon up, touches
   nothing live, and uses 18.1 R1's copy and three children: {#r2-rehearse}
   - copy `catalog.read.duckdb` with a child `/bin/cp -p`;
   - in one child, `CHECKPOINT`, then `ATTACH` + `COPY FROM DATABASE` + `CHECKPOINT` + `DETACH`
     into a scratch file;
   - in another child, the gate (R4).

   It reports `file_bytes`, `rewrite_bytes`, `r`, `reclaimable`, `rewrite_s` (median of 3), the
   18.1 A and C bands, and `rehearsal_sha` (sha256 of the canonical report JSON). The routine
   that does this is the PRODUCTION routine R3 runs on the live slot (AC-7 ties it to 18.1). The
   scratch files are deleted afterwards.
3. **R3 The real run** (`confirm=<rehearsal run_id>`). {#r3-real}
   - **Preconditions, all checked before anything is stopped.** Each failure returns
     `refused:<reason>` and changes nothing:
     - the rehearsal line exists in `runs.jsonl` with this `run_id`, `ok: true`,
       `invoked_by ∈ {cli, mcp}`, finished ≤ 24 h ago;
     - its band is A1 or A2, and C0, or C1 with `window=True`;
     - the writer slot's `file_bytes` now is within 10 % of the rehearsal's;
     - free disk ≥ 2 × `file_bytes`;
     - the hub answers.
   - **The sequence**, with each step's seconds recorded:
     1. **Pause the watchdog**, `pause(root, seconds=budget)` with
        `budget = C-band ceiling (30 or 120 s) + 120 s`. This must succeed: unlike O2's
        best-effort path, a failed pause REFUSES (`refused:hub_pause`).
     2. **Record the before-state through the daemon:** the per-table row counts (one daemon read
        op) and `rmx repair-index --fragments --dry-run`'s summary (the bug-105 contract's state,
        recorded, not gated).
     3. **Stop.** `stop_daemon(root)` must return True. On False: resume the watchdog and return
        `refused:daemon_would_not_stop` (O1). The daemon was not killed.
     4. **Take `daemon.lock`** with `LOCK_EX | LOCK_NB` for the whole offline window. If it is
        held: restart (step 9), resume, `refused:daemon_lock_held`. While it is held, a launchd
        start refuses and a `spawn_daemon` waits (O3), so no daemon can open the slot mid-rewrite.
     5. **In child A**, open the writer slot and `CHECKPOINT` it, which folds any WAL. Then
        `ATTACH 'catalog.<S>.reclaim-<run_id>.duckdb'`, `COPY FROM DATABASE`, `CHECKPOINT`,
        `DETACH`, and close. Every DuckDB statement runs in a child: the CLI process opens no
        descriptor on the slot or the new file (bug-110, bug-112; AC-6).
     6. **In child B**, run the gate (R4) between the slot and the new file.
     7. **Swap**, only after the gate passes:
        - the slot's `.wal` must be absent or 0 bytes, or the swap refuses;
        - `rename(slot → backups/catalog.<S>.pre-reclaim-<run_id>.duckdb)`;
        - `rename(new → slot)`;
        - `fsync` the root and `backups/` directories.

        The `active` marker is NOT changed: it is the same slot letter.
     8. **Release `daemon.lock`.**
     9. **Restart** with `launchctl.kickstart(root)`, then wait ≤ 120 s for a ping from a NEW pid.
     10. **Post-check through the daemon:**
         - the per-table row counts equal step 2's;
         - health `slot_bound: true` and `db_file == catalog.<S>.duckdb`;
         - one `rmx catalog maintain --dry-run` (18.2) reports `free_blocks / total_blocks` ≤
           the rehearsal's `1 − r` + 0.10.
     11. **Resume the watchdog.** Reset 18.2's `baseline_file_bytes` to the new size. Report
         `down_s` (step 3 to step 9's ping) against the C band; a `down_s` over the band is
         reported `down_over_band` (a warning, not a failure).
4. **R4 The gate**, in a child, with the old and new files both read-only: {#r4-gate}
   - for every table: `count(*)` and `sum(hash(<every column>))` are equal (an order-independent
     content hash);
   - every sequence's last value is equal;
   - the index name set and per-table constraint counts are equal;
   - `PRAGMA database_size` of the new file is reported.

   Any difference names the table and both values, and fails the run before the swap.
5. **R5 Rollback, never a guess.** {#r5-rollback}
   - **Before the swap fails** (steps 5-6): nothing is renamed. The new file is kept as
     `catalog.<S>.reclaim-failed-<run_id>.duckdb` and reported. The daemon is restarted on the
     untouched slot, the watchdog resumed, and the run returns `ok: false`.
   - **After the swap fails** (no new pid in 120 s, or the step 10 post-check differs): stop the
     daemon, rename the slot back from the pre-reclaim backup, rename the reclaimed file to the
     failed name, kickstart, re-run the post-check against step 2, and report `rolled_back`.
   - **A rollback that itself fails** (a rename error, or the original will not answer) leaves
     the watchdog PAUSED and the store down. The run returns a loud error naming the slot, the
     backup and the failed file, and never resumes onto a file it has not verified.
6. **R6 What it never touches** (d9ao; `feedback_decay_never_loses_knowledge`): the frozen
   inactive slot, the legacy `catalog.duckdb`, `facts.log` and both slot offset files,
   `vectors/`, and the `active` marker. {#r6-untouched}
   - The pre-reclaim backup is KEPT. `rmx catalog reclaim --list-backups` lists them with sizes,
     and they are removed only by the user after confirming, as 17.3's backups are.
   - This is not knowledge removal under ADR-0004 `#rule-no-delete`: every row is carried over
     and verified (R4), and the old file is kept whole.
7. **R7 `rmx compact` is retired onto the verb.** `rmx compact` (`cli.py:7630`) becomes a thin
   command that runs the rehearsal, prints it, and asks for the run id to confirm. Its own
   EXPORT/IMPORT path, its in-process `duckdb.connect` and its `spawn_daemon` restart are deleted,
   so no unsafe reclaim path is left. The CLI tree is regenerated, and the generated-artifact
   checks run with the family (`feedback_family_list_misses_generated_checks`). {#r7-compact}
8. **R8 The hand-run procedure**, for each store 18.1 put in A1/A2 with C0/C1, one store at a
   time, announced to the user first. Stores in C1 need a window the user names. {#r8-procedure}
   - rehearse;
   - read the report;
   - `--confirm <run_id>`;
   - read `down_s` and the post-check;
   - record the before/after table in the implementation summary.

   The store's next 18.2 night must show the new baseline and band A0.
9. **R9 Not on the nightly tick.** This step deletes nothing, but it stops a daemon. 17.2's
   steps are daemon ops on running stores (17.2 R2, R3), so a nightly reclaim would need a
   hub-side offline step type that 17.2 does not have. Adding one is out of scope; if the user
   wants it later, it is a 17.2 amendment plus Table C's C0 as its admission rule. {#r9-not-nightly}

## Acceptance criteria {#acceptance}

Tests run in the 23.0 sandbox. The supervisor is injected: `stop` / `start` callables whose
production defaults are `stop_daemon` and `launchctl.kickstart`, and whose test values stop and
start a real tmp daemon. The launchd path itself runs in 23.0's tier-2 / tier-3 lanes (d9x),
not in the in-process tier.

1. **AC-1 (round trip).** A tmp store gets 200,000 entities and links, 90 % of the entities are
   purged, and the WAL is checkpointed. A rehearsal followed by a real run gives:
   - the slot is ≥ 50 % smaller;
   - every table's count and content hash are equal (R4);
   - after the restart, a new entity's id is greater than the old max id (the sequence carried
     over);
   - the daemon answers from a new pid, and health has `slot_bound: true`;
   - the `active` marker, the frozen inactive slot and `facts.log` keep their bytes and mtime_ns;
   - the pre-reclaim backup exists and equals the old slot's bytes.

   {#ac-1}
2. **AC-2 (gate failure).** A test hook deletes one row of the new file before child B. The run
   returns `ok: false` naming the table; no rename happens; the daemon answers on the untouched
   slot; the failed file is kept. Mutation: the gate removed FAILS (the store loses a row).
   {#ac-2}
3. **AC-3 (rollback).** The injected `start` fails once (the new daemon never answers). The slot
   is renamed back, the daemon answers on the original bytes, and the report says `rolled_back`.
   With the rename-back also made to fail, the run returns the loud error and the watchdog stays
   paused (the injected hub records no resume). Mutation: resuming on rollback failure FAILS.
   {#ac-3}
4. **AC-4 (preconditions refuse before any stop).** Each of these refuses with its reason while
   the daemon's pid stays unchanged and no file changes:
   - no rehearsal line;
   - a rehearsal older than 24 h (injected clock);
   - band A0;
   - band C2;
   - band C1 without `window`;
   - a 15 % size drift;
   - not enough free disk (injected);
   - a hub that will not pause.

   Mutation: the pause made best-effort FAILS (the run proceeds without a pause). {#ac-4}
5. **AC-5 (`daemon.lock` excludes starts).** While a real run is between steps 4 and 8 (the
   injected child A blocks on an event): a `serve_foreground` start on the root raises "another
   daemon spawn holds"; a `spawn_daemon` call blocks and, after release, returns the new
   daemon's pid with no second daemon process. Mutation: the lock not taken FAILS (a daemon opens
   the slot mid-rewrite and child A's open hits a lock conflict). {#ac-5}
6. **AC-6 (no in-process descriptor; bug-110 / bug-112).** A spy on `duckdb.connect` and on
   `open()` of the slot and new-file paths in the CLI process counts zero over a real run. Every
   DuckDB statement ran in a child whose pid differs from the parent's. Mutation: an in-process
   gate FAILS. {#ac-6}
7. **AC-7 (production path = 18.1's path).** On the same synthetic copy, the production
   rehearsal's `rewrite_bytes` is within 1 % of 18.1's script and its median `rewrite_s` within
   ±25 %. This is 18.1 R4. {#ac-7}
8. **AC-8 (ledger and surfaces).** A CLI rehearsal and an MCP rehearsal append
   `step: "catalog_reclaim"` lines with `invoked_by` `cli` / `mcp` and `dry_run: true`. A real
   run appends `dry_run: false` with `down_s` and the before/after sizes. `invoked_by="hub"`
   raises `ValueError`. {#ac-8}
9. **AC-9 (`rmx compact` is safe).** `rmx compact` on a tmp store runs the rehearsal and refuses
   to touch the slot without a confirm. A search of `cli.py` finds no `EXPORT DATABASE` or
   `IMPORT DATABASE` and no `spawn_daemon` call in it. {#ac-9}
10. **AC-10 (pre-registered mutations, each must FAIL a named AC).** {#ac-10}
    - gate removed → AC-2;
    - resume after a failed rollback → AC-3;
    - best-effort pause → AC-4;
    - `daemon.lock` not held → AC-5;
    - in-process DuckDB → AC-6;
    - the `active` marker flipped, or the inactive slot used as the target → AC-1;
    - the backup deleted after success → AC-1;
    - `hub` accepted as `invoked_by` → AC-8.

## Test strategy {#test-strategy}

- Tier 1 (in-process, 23.0) covers AC-1..AC-10 with the injected supervisor.
- One AC-1 run goes through the real `launchctl.kickstart` path in 23.0's tier-2 user lane or
  tier-3 VM (d9x). It is never run against the user's own LaunchAgents.
- Real DuckDB files throughout; no DuckDB mocks.

## Files to modify {#files-to-modify}

| file | change |
|---|---|
| `src/refmatrix/catalog_reclaim.py` | new: rehearsal, gate, swap, rollback routines (children via `subprocess`) |
| `src/refmatrix/verbs.py`, `cli.py`, `mcp.py` | `rmx_catalog_reclaim`; `rmx catalog reclaim`; `rmx compact` retired onto it (R7) |
| `src/refmatrix/daemon.py` | a read op for per-table counts, if `stats` does not already return them |
| `tests/test_catalog_reclaim.py` | new: AC-1..AC-10 |
| CLI tree | regenerated |
