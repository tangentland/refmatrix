---
gmd: "0.1"
id: task-26.2-bridge-move-safety
title: "Task 26.2: a moved memory file is refreshed through the existing source_path, keeps its identity, and two files claiming one id are refused"
tags: [task, plan-26, bridge, ingest-gmd, memory, identity, move]
metadata:
  node_type: task
  status: pending
  plan: plan-26-memory-organisation
  updated: 2026-11-09
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
`gmd_content_hash` for its NAME matches. A file that is moved with its bytes unchanged is
therefore skipped. Its anchor concepts keep `path=<old path>`, and the memory row keeps
`source_path=<old path>`. ch-bsd r1 reproduced this on the production CLI. Identity is safe; the
provenance goes stale.

1. **AC-1: a move refreshes the row; it never creates a new one.**
   - Setup: a throwaway store and memory dir. Ingest `a/x.md` (id `x`, two `{#anchor}`
     headings). Move it unchanged to `b/x.md`. Run `rmx ingest-gmd --as-memory <dir>` again.
   - After the second run:
     - the memory entity id is unchanged;
     - `memory_content.metadata.source_path` is the RESOLVED `b/x.md`;
     - every `x#anchor` concept's `entities.path` is `b/x.md`;
     - the vector, `created_at`, protected/noise flags and inbound `rel:` edges are unchanged;
     - there is exactly one `x` memory row.
   - At HEAD the path assertions fail (RED).
2. **AC-2: the gate reuses the path already recorded; it adds no second record (ch-bsd r1 #s5).**
   - For memory rows, the skip requires two things: the hash matches, AND the row's existing
     `memory_content.metadata.source_path` equals the file's resolved path. For doc rows, the
     second condition is that `entities.path` equals the resolved path.
   - Compare on resolved paths on both sides. The daemon resolves its targets
     (`daemon.py:3771`), so a symlinked memdir (viascope) compares equal.
   - No `gmd_source_path` key is added.
   - An unchanged file at an unchanged path is still skipped. The stats count it as skipped, and
     the store write counter does not move.
3. **AC-3: the one-time re-ingest is stated and measured.** A row whose `source_path` is missing,
   or disagrees with the resolved file path, is re-ingested once. This task ships a read-only
   count, `rmx memory organise --check` field `refresh_pending`, so 26.8 and 27.1 can measure that
   cost per store BEFORE the deploy. The count is reported per dir.
4. **AC-4: an id claimed twice is refused, counted and named.**
   - When two files in one walk share a frontmatter `id`, neither overwrites the other.
   - Both are reported in `stats.duplicate_ids: [(id, [paths])]`.
   - This is printed in the bridge report and carried by `_bridge_stats` AND by
     `_bridge_wait_for_active_job`'s result (ch-bsd r1 #m5). It surfaces in the `rmx save-state`
     output.
   - The store row keeps its prior content.
   - At HEAD the last file walked silently wins (RED).
5. **AC-5: no forget path touches memory rows on a move (regression pin).** After the move in
   AC-1, run `rmx vacuum` and `rmx sync` over the throwaway project. The memory row and its
   anchors survive.
6. **AC-6: the doc→memory cleanup still matches.** The `kind='doc'` purge at `ingest_gmd.py:905`
   keeps matching on the CURRENT path. The bug-111 tests stay green.

## Files to Create / Modify {#files}

- Modify `src/refmatrix/ingest_gmd.py`: the gate, duplicate-id stats, the report line.
- Modify `src/refmatrix/cli.py`: `_bridge_stats` and `_bridge_wait_for_active_job` carry
  `duplicate_ids`; the save-state render prints them.
- Create `tests/test_bridge_move_safety.py`.

## Test Strategy {#test-strategy}

- Run the real `rmx ingest-gmd --as-memory` CLI against a throwaway store in task 23.0's sandbox,
  under a short `mkdtemp()` root.
- Run it in-process first, then through a throwaway daemon, because the daemon path is what
  save-state uses.
- Include one symlinked-memdir case.
- Read rows back with `Store` opened only on the THROWAWAY store. Nothing in the bridge is
  mocked.
- Mutation checks:

| mutation | result |
|---|---|
| drop the path term from the gate | AC-1 goes RED |
| drop the duplicate check | AC-4 goes RED |
| drop the field from the waited-job result | the AC-4 waited case goes RED |

## Revision round 1 (2026-11-09) {#rev-round-1}

| finding | change | anchor |
|---|---|---|
| S5 (a second copy of the path; an unstated full re-ingest) | Gate on the existing resolved `source_path` / `entities.path`; no new key; `refresh_pending` count; cost measured in 26.8/27.1 | AC-2, AC-3 |
| M5 (the waited-job branch) | `_bridge_wait_for_active_job` carries `duplicate_ids` | AC-4 |
