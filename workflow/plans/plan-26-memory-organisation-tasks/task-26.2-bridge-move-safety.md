---
gmd: "0.1"
id: task-26.2-bridge-move-safety
title: "Task 26.2: a moved memory file is re-ingested, keeps its identity, and two files claiming one id are refused"
tags: [task, plan-26, bridge, ingest-gmd, memory, identity, move]
metadata:
  node_type: task
  status: pending
  plan: plan-26-memory-organisation
---

# Task 26.2: bridge move-safety {#root}

> Plan: [[plan-26-memory-organisation]]
> Status: Pending
> Depends on: [[task-26.1-layout-module-and-index-walk]]

rel: part-of -> [[plan-26-memory-organisation]]
rel: reinforces -> [[feedback_decay_never_loses_knowledge]]
rel: reinforces -> [[feedback_no_silent_failures]]

## Requirements {#requirements}

The bridge's resume gate (`ingest_gmd.py:826-875`) skips a file when the stored
`gmd_content_hash` for its NAME matches. A file moved with unchanged bytes is skipped, so its
anchor concepts keep `path=<old path>` and the memory row keeps `source_path=<old path>`.
Nothing forgets the row, so identity is safe. The provenance goes stale.

1. **AC-1: move = refresh, not new row.** Set up a throwaway store and memory dir. Ingest
   `a/x.md` (id `x`, with two `{#anchor}` headings). Move it to `b/x.md` with unchanged bytes.
   Run `rmx ingest-gmd --as-memory <dir>` again. Then all of these hold:
   - the memory entity id is unchanged;
   - `memory_content.metadata.source_path` is `b/x.md`;
   - every `x#anchor` concept's `entities.path` is `b/x.md`;
   - the vector, `created_at`, protected/noise flags and inbound `rel:` edges are unchanged;
   - there is still exactly one `x` memory row.
   At HEAD the path assertions fail (RED).
2. **AC-2: the gate keys on content AND path.** `_write_content_hash` also records
   `gmd_source_path`. The skip requires both to match. An unchanged file at an unchanged path is
   still skipped: assert the stats count it as skipped and the store write counter does not move.
3. **AC-3: an id claimed twice is refused, counted and named.** Put two files with the same
   frontmatter `id` in one walk (`x.md` and `savestates/x.md`). Neither overwrites the other.
   Both are reported in a new `stats.duplicate_ids: [(id, [paths])]` list. They are printed in
   the bridge report and surfaced by `_sync_memory_dir` → `rmx save-state` output. The store row
   keeps its prior content. At HEAD the last file walked silently wins (RED).
4. **AC-4: no forget path touches memory rows on a move.** A regression test pins today's
   behaviour, so a later change cannot regress it. After the move in AC-1, run `rmx vacuum` and
   `rmx sync` over the throwaway project. The memory row and its anchors survive.
5. **AC-5: the doc→memory cleanup still matches.** The `kind='doc'` purge at
   `ingest_gmd.py:905` keeps matching on the CURRENT path. The bug-111 tests stay green.

## Files to Create / Modify {#files}

- Modify `src/refmatrix/ingest_gmd.py` (the gate, `_write_content_hash`, duplicate-id stats,
  the report line).
- Modify `src/refmatrix/cli.py` (`_bridge_stats` carries `duplicate_ids`; the save-state render
  prints them).
- Create `tests/test_bridge_move_safety.py`.

## Test Strategy {#test-strategy}

Use the real `rmx ingest-gmd --as-memory` CLI against a throwaway store in a short `mkdtemp()`
root. Run in-process first. A second case runs through a throwaway daemon, because the daemon
path is what save-state uses. Read the rows back with `Store` opened on the THROWAWAY store only.
Nothing in the bridge is mocked. Mutation check: drop the path term from the gate and AC-1 goes
RED. Drop the duplicate check and AC-3 goes RED.
