---
gmd: "0.1"
id: task-27.0-organise-merge-from
title: "Task 27.0: rmx memory organise --merge-from — fold one memory dir into another, reconciling ids by content"
tags: [task, plan-27, verb, migration, merge, memory-dir]
metadata:
  node_type: task
  status: pending
  plan: plan-27-memory-fleet-rollout
---

# Task 27.0: organise --merge-from {#root}

> Plan: [[plan-27-memory-fleet-rollout]]
> Status: Pending
> Depends on: [[task-26.5-memory-organise-verb]] deployed

rel: part-of -> [[plan-27-memory-fleet-rollout]]
rel: amends -> [[task-26.5-memory-organise-verb]]

## Requirements {#requirements}

The viascope2 fold (27.2) must go through the verb, never a hand-move. That needs a merge mode
in the same verb, CLI and MCP tool.

1. **AC-1: preview.** `rmx memory organise <dest> --merge-from <src>` with no `--apply` lists:
   - each src file and its destination path under dest's type folders;
   - `same_id_identical` (bytes equal after frontmatter normalisation): dropped from src on
     apply;
   - `same_id_differs`: shown with a unified diff, and never applied without
     `--resolve <id>=keep-dest|import-as:<new_id>`;
   - every `[[id]]` or `rel:` target in src that resolves only inside src;
   - every dest file that links an id the merge would rename.
2. **AC-2: backup of BOTH dirs** comes before any change (26.5 AC-2 applied twice).
3. **AC-3: frozen fields survive.** An imported file keeps `id`, `created:` and
   `originSessionId` byte-identical. Only `updated:` is bumped, and only on files the merge
   rewrites.
4. **AC-4: renames rewrite edges, under MEMORY-RULES.** For `import-as:<new_id>`:
   - the imported file's `id` becomes `<new_id>`, and it gains
     `rel: supersedes|amends -> [[<old_id>]]`, with the verb chosen by `--resolve` (the user's
     call per the amend/supersede tree);
   - every `[[<old_id>]]` reference inside the imported set is rewritten to `<new_id>`;
   - references in dest are NOT rewritten, because they meant dest's file.
5. **AC-5: the source is tombstoned, not deleted.** On apply, src keeps a `README.md`
   ("merged into <dest> on <date>; backup <tarball>") and its now-empty folders. No file is
   deleted except `same_id_identical` duplicates, and those are in the backup.
6. **AC-6: bridge and recall.** Apply runs dest's bridge through dest's store daemon. In the
   end-to-end test, recall for a phrase unique to an imported file returns it from dest's store.
7. **AC-7: rollback.** `--rollback` takes both tarballs and restores both dirs.

## Files to Create / Modify {#files}

- Modify `src/refmatrix/memory_organise.py`, `verbs.py` and `cli.py`.
- Create `tests/test_memory_organise_merge.py`.

## Test Strategy {#test-strategy}

Two throwaway memdirs under one short `mkdtemp()` HOME, a throwaway dest store with a daemon, and
the real CLI plus the MCP verb. Fixtures: one identical overlap, one differing overlap, and one
src-local wikilink chain. Mutation check: skip the src-local link rewrite and the AC-4 chain
assertion goes RED.
