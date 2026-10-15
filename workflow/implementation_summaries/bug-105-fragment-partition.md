---
gmd: "0.1"
id: impl-bug-105-fragment-partition
title: "bug-105: the bitmap fragment cache follows the partition binding; repair-index --fragments; live merge fenced"
tags: [implementation-summary, bug-105, store, fragments, partition, hotfix]
metadata:
  node_type: implementation-summary
  status: in-review
  created: 2026-10-14
  updated: 2026-10-14
---

# bug-105: fragment cache vs partition binding {#root}

rel: implements -> [[plan-review-2026-10-14#t9-approvals]]
rel: related-to -> [[task-23.1-queue-and-drain#r1]]

## The defect {#defect}

`Store._fragments` / `_dirty_fragments` were keyed by linkage only, on the false assumption that a
Store stays bound to one partition. `with_partition` and several daemon paths rebind
`_partition_id`, so bits crossed partitions and were flushed under whichever partition was bound
at flush time: the bug-098 class on the bitmap side. Measured on a copy of this repo's read
snapshot (2026-10-14): 538,094 bits in the wrong partition, 466,163 bits for deleted entities,
104,283 `entity_links` bits missing from their fragment.

## The fix {#fix}

- **Cache per binding** (0d05525): keyed on `(partition_id, partition_name)`; every flush writes
  each binding's dirty set under its own partition id; every "is anything dirty" check spans all
  bindings (`has_dirty_fragments`, `dirty_fragment_count`; the daemon tick goes through
  `daemon._periodic_flush`).
- **`rmx repair-index --fragments`** (20c5ab4): a UNION repair (entity_links ∪ every fragment bit
  whose entity lives in the partition), so no live bit is lost; only dead-entity and dead-concept
  bits are dropped, into a JSONL manifest under `backups/`. A concept is alive if its id is in
  `entities` or `concepts` (27b3653). `--dry-run` writes nothing but the manifest. Every counter
  reaches the CLI and `rmxd.log` (`moved`, `added_from_links`, `dropped_dead`,
  `dropped_dead_concept`, `links_skipped`, `unread_dirs`, `manifest`).
- **Rename/merge keep their bits** (4fb803b, 27b3653, fc4c8d1): flush every binding first; the
  merge's end FLUSHES (never clears), runs under the writer lock, and re-homes its colliding ids
  through `repair_fragments(id_map=...)`, remapping both halves of each bit.
- **Live merge fenced** (325d702, user decision d9ae): the daemon's `partition_merge` op refuses
  anything but a dry run and `rmx partition merge` refuses with the daemon up. A live merge's
  rebind and SRC drop sat in separate holds of the FIFO writer lock, so queued ops ran bound to
  the dropped partition (r4 #b4-1), and a SRC write between chunks orphaned its entity (#s4-1).
  The OFFLINE merge (daemon down, no concurrent writer) stays; the fence asks `require_daemon`,
  so a BUSY daemon is refused too (r5 #m5-1). The redesign belongs to the helix plan, which owns
  merge (d9ac). The daemon's job API (`job_status`, `rmx daemon job`) had no other producer and
  is removed (r5 #b5-1); `merge_partition`'s `lock`/`progress` parameters are kept for the helix
  merge, which is named in its docstring. The repair report gains `remapped` (r5 #s5-2).

## TDD and audits {#tdd}

- Tests: `tests/test_fragment_partition_scope.py`, `test_fragment_repair_audit.py` (r1),
  `_r2.py`, `_r3.py`, `_r4.py` (r4, r5 and r6 pins, including the auditor's probes P1-P4); each
  round's new tests RED at the previous commit (`workflow/review-output/bug105-*-red.log`).
- Families (fragment/partition/merge/snapshot/ingest-yield, verb + MCP parity, hooks, and the
  generated-docs check that r6 found missing from the list): see `bug105-r7-families.log`.
- Mutations: `bug105-mutant*.log`, `bug105-r4-mutations.log`, `bug105-r5-mutations.log`,
  `bug105-r6-mutations.log`; F3/M5 are near-equivalent offline (r5/r6).
- ch-bsd rounds r1 (20c5ab4) through r6 (fe7abea): reports under `workflow/bullshit/`.

## Deploy and live repair {#deploy}

Corrected after ch-bsd r5 #s5-1 (the first version relaunched one daemon and named no backup
method).

1. **Merge and deploy.** Merge `--no-ff` to `master`, bump the version, then
   `git -C ~/refmatrix pull --ff-only origin master`. Relaunch the WHOLE fleet:
   `rmx hub relaunch-fleet` (one `rmx daemon restart --relaunch` restarts one store and leaves
   every other daemon on the defective cache; plan-4 r1 #b-6). Verify: `rmx version -v` names
   `~/refmatrix/src` and the new version; `rmx hub status` lists every store on it.
Steps 2-4 run as ONE block per store, because `rmx daemon stop/start` and `rmx repair-index`
take no store argument: they act on `REFMATRIX_ROOT` or the cwd's store (r6 #m6-2). Begin each
block with `export REFMATRIX_ROOT=<project>/.refmatrix` (the global store: `~/.refmatrix`).

2. **Back up each store's active slot, consistently.** A `cp` under a live daemon is not a
   consistent copy and misses the WAL. Per store: `rmx hub pause <store>`, `rmx daemon stop`,
   copy `catalog.<active>.duckdb` and its `.wal` if present (the `active` marker names the slot)
   to `backups/pre-bug105-repair-<date>/`, `rmx daemon start`, `rmx hub resume <store>`. The
   manifest records drops, never moves, so it is not a restore point.
3. **Dry run.** `rmx repair-index --fragments --dry-run` (write-free on a live daemon apart from
   the manifest and one rmxd.log line, r5 Q3); read every counter (on this repo's copy,
   `dropped_dead_concept` about 410).
4. **Apply.** `rmx repair-index --fragments`. A day later dry-run again: a non-zero `moved`
   measures what the known m-3 gap (links written to the bound partition) regrew.

An OFFLINE `rmx partition merge` (the only kind now) needs `rmx hub pause` first, or the hub
respawns the stopped daemon within ~30 s; the CLI's refusal message says so.

## Open, owned elsewhere {#open}

- Live merge redesign: the helix plan (d9ac, d9ae).
- SQLite merge's best-effort fragment-dir skip (r3 #m3-1): non-production backend.
- 23.1 R1.6 (d9ag): a held-writer-lock check in every Store writer, the structural guard against
  this class.
