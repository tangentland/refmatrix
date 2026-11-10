---
gmd: "0.1"
id: impl-task-26.2-bridge-move-safety
title: "Task 26.2 GREEN: the bridge refreshes a moved memory through its recorded source_path, and refuses two files claiming one id"
tags: [implementation-summary, plan-26, bridge, ingest-gmd, memory, identity, move]
metadata:
  node_type: implementation-summary
  status: complete
  created: 2026-11-10
---

# Task 26.2 GREEN: bridge move-safety {#root}

rel: implements -> [[task-26.2-bridge-move-safety]]
rel: implements -> [[refmatrix/adr-0005-memory-dir-layout]]
rel: depends-on -> [[task-26.1-layout-module-and-index-walk]]
rel: related-to -> [[task-26.3-savestate-subfolder]]
rel: reinforces -> [[feedback_decay_never_loses_knowledge]]
rel: reinforces -> [[feedback_no_silent_failures]]

## Why {#why}

The bridge's resume gate skipped a memory file when the stored `gmd_content_hash` for its NAME
matched. A file moved with unchanged bytes was skipped, so its row kept `source_path=<old>` and
its `x#anchor` concepts kept `path=<old>`. A later `rmx sync` of the old path then purged those
anchors (AC-5, #rd-ac5-defect). Organising a memdir (26.5) moves every file, so this had to be
fixed before 26.5 ships. The RED group is `27e21dc` + `75cd42e`
(`tests/test_bridge_move_safety.py`, 25 tests). {#why-lead}

## What changed {#changes}

- **One classifier** (`ingest_gmd._memory_gate`) runs in both the bridge and `--dry-run`.
  {#c-gate}
  - Hash-only gate (HEAD's rule): files in an un-organised memdir (AC-3b).
  - Path-aware gate: files whose nearest ancestor has a readable `.memory-layout`
    (`_OrganisedDirs` → `memory_layout.is_organised`), and every `--dry-run`. The file is skipped
    only when the hash matches AND the stored `source_path` is *literally* equal to the resolved
    path (#rd-literal).
  - When the paths disagree, the row lands in exactly one term, chosen by the shape of the
    stored path (r5 m3): a missing or symlink-form path is `stale_before`, any other path is
    `moved`.
  - An unreadable marker is never read as "not organised", and it never fails the ingest. The
    path-aware rule applies there and the problem is named as a `marker_error:` line. This keeps
    26.6's "the memories are SAVED" twins green.
- **AC-1b, one logged write.** {#c-legacy}
  - Every other memory row on a moved file's old path is refreshed by
    `Store.refresh_memory_source_path`. Rows are matched on the resolved old path, and the id
    rows of the current walk are excluded.
  - That call and the id-row `add_memory` run inside one `store.transaction()`.
    `Store.add_memory` now commits through `_maybe_commit`.
  - Each legacy refresh logs a full `memory_content` event that carries the stored
    `updated_at`, which is not bumped, so `rebuild --from-log` restores the new path.
  - The refreshed rows are counted as `moved_legacy`. A lazy `_SourcePathIndex` supplies the
    rows, so an unchanged run pays no scan.
- **AC-4, parse then write.** {#c-dup}
  - Memory files are all parsed before anything is written (`_parse_memory_walk`).
  - `split_claims` refuses an id that two or more files claim, and writes neither file.
  - The refusals are carried by `IngestStats.duplicate_ids`, by `_bridge_stats` (all three
    legs, including the waited job) and by the report line `duplicate_ids: N` with every path.
    `save-state` prints that report.
  - `split_claims` is the **single hook point** for 26.3's exemption of the `savestate_*`
    top-level/`savestates/` pair. 26.3's preference between the two is NOT implemented here.
- **AC-3, the measurement.** `rmx ingest-gmd --as-memory --dry-run` calls
  `plan_memory_refresh`, which only reads the store. It prints `refresh_pending` and the four
  terms. {#c-dry}
  - `--store-snapshot F` opens a copied catalog in-process and read-only. The branch runs
    before `_root()`, so there is no `daemon_mod` call and no hub contact. It needs `-p`, and
    that partition must exist in the copy.
  - `--path-map FROM=TO` rewrites stored paths before they are compared.
  - Misuse is refused: either flag without `--dry-run`, a dry-run without `--as-memory`, or a
    dry-run combined with `--prestage`/`--detach`.
- **Two supporting fixes, both found by the RED group.** {#c-support}
  - `_write_content_hash` writes nothing when the marker is already current. Before, it bumped
    `entities.updated_at` on every pass-2 run, which re-staled the vector of a moved, unchanged
    file (`vectors_updated_at` moved).
  - The daemon-down `_ingest_gmd_sync` now closes its writer, the same pattern as the session
    ingest in task 3.7. The open writer had kept DuckDB's lock and an un-checkpointed WAL for
    the whole life of the process (save-state from the MCP server), so a copied catalog was
    missing the rows just written.

## Verification {#verify}

- RED file: 25/25 (`workflow/review-output/plan26/26.2-green.log`).
- Family (`test_bridge_move_safety`, `test_memory*`, `test_ingest_gmd*`, `test_save_state*`,
  `test_bug111*`, `test_sync*`, `test_verb_parity`, `test_docs_generated`): 645 passed
  (`26.2-green-family.log`). The first family run caught the two 26.6 unreadable-marker twins;
  they are fixed by the non-fatal marker rule in [[#c-gate]].
- Full suite: `26.2-green-full.log`.
- Mutations: 9 run, 9 killed, each restored in its own command (`26.2-mutations.log`).

| mutation | killed by |
|---|---|
| gate never path-aware (marker ignored → hash-only) | AC-1 in-process, AC-1b |
| gate always path-aware (marker ignored → on) | AC-1b marker-off twin |
| gate drops the path term | AC-1, AC-3 missing path, AC-3 dry-run |
| duplicate check dropped | AC-4 in-process, AC-4 stats |
| waited-job result drops `duplicate_ids` | AC-4 waited |
| anchors keep the old path (AC-5 purge restored) | AC-5 |
| `--store-snapshot` opens the live store | AC-3 daemonless, AC-3 relocated twin |
| id row refreshed only | AC-1b |
| legacy `memory_content` event dropped | AC-1b rebuild-from-log |

## Open points {#open}

- `forced` is printed and carried, but nothing in 26.2 increments it. 26.5 AC-5 owns the
  forcing. Flagged so ch-bsd reads it as a declared seam, not a placeholder. {#o-forced}
- AC-5 is fixed by the refresh: after the bridge, the anchors carry the new path. A watcher
  `sync` of the old path that runs BEFORE the bridge, or a move in an un-organised dir (where
  anchors keep the old path by design, AC-3b), still purges a memory's anchor concepts.
  `purge_path` has no guard for memory anchors. This is not pinned by a test and is not built
  here; it is a follow-up candidate. {#o-ac5-window}
