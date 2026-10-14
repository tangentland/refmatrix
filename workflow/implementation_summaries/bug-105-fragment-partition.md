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
  The OFFLINE merge (daemon down, no concurrent writer) stays. The redesign belongs to the helix
  plan, which owns merge (d9ac). The daemon's job API (`job_status`, `rmx daemon job`) now has no
  producer and is kept for the next async big-op.

## TDD and audits {#tdd}

- Tests: `tests/test_fragment_partition_scope.py`, `test_fragment_repair_audit.py` (r1),
  `_r2.py`, `_r3.py`, `_r4.py`; each round's new tests RED at the previous commit
  (`workflow/review-output/bug105-*-red.log`).
- Families (fragment/partition/merge/snapshot/ingest-yield): 536 passed, 4 skipped at 325d702
  (`bug105-r5-families.log`). Known flake bug-108 is not in this code.
- Mutations: `bug105-mutant*.log`, `bug105-r4-mutations.log`, `bug105-r5-mutations.log` (8/8
  killed, including the four repair-path survivors M1/M11/M12/M14).
- ch-bsd rounds r1 (20c5ab4), r2 (4fb803b), r3 (27b3653), r4 (fb285cc): reports under
  `workflow/bullshit/`.

## Deploy and live repair {#deploy}

1. Merge `--no-ff` to `master`, bump the version, deploy (`git -C ~/refmatrix pull --ff-only`,
   `rmx daemon restart --relaunch`).
2. Per store: back up the ACTIVE slot (`catalog.<A|B>.duckdb`); the manifest records drops, never
   moves, so it is not a restore point.
3. `rmx repair-index --fragments --dry-run`; read every counter (on this repo's copy,
   `dropped_dead_concept` about 410).
4. Apply; a day later dry-run again: a non-zero `moved` measures what the known m-3 gap (links
   written to the bound partition) regrew.

## Open, owned elsewhere {#open}

- Live merge redesign: the helix plan (d9ac, d9ae).
- SQLite merge's best-effort fragment-dir skip (r3 #m3-1): non-production backend.
- 23.1 R1.6 (d9ag): a held-writer-lock check in every Store writer, the structural guard against
  this class.
