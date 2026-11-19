---
gmd: "0.1"
id: impl-task-s1-drop-sqlite-backend
title: "Task S1: one catalog backend (DuckDB); a legacy catalog.db dir is refused"
tags: [implementation-summary, s1, store, backend, duckdb, deletion]
metadata:
  node_type: implementation-summary
  status: complete
  task: task-s1-drop-sqlite-backend
  created: 2026-11-19
---

# Task S1: one catalog backend, and the legacy refusal {#root}

GREEN half (green-s1) of [[task-s1-drop-sqlite-backend]]. RED (red-s1) wrote the tests at
`6b4e7e1a`; GREEN changed `src/`, `scripts/`, one `eval/` comment and the docs, no test.

rel: implements -> [[task-s1-drop-sqlite-backend]]
rel: derives-from -> [[s1-r0-census]]
rel: related-to -> [[task-29.2-mypy-gate#r7-t0-docstrings]]

## Release {#release}

**Not store-changing (D1 = b, L187).** `pagerank.py`, `ingest.py` and `vectors.py` are
byte-identical to the base `1fadfb61`, so no derive pass's code hash moves and no fleet store
re-derives. No schema change: the DuckDB DDL gained comments only. No version bump in this
branch. {#release-line}

## What shipped {#shipped}

| where | what |
|---|---|
| `backend.py` | `select_backend`, the `Backend` ABC, `ConnLike`, `SQLiteBackend`, `import sqlite3`, `DuckDBConnection.executescript` / `row_factory` and `attach_file(db_type=)` deleted. `DuckDBBackend` is a plain class; its `kind` is read only by the daemon's two reporters. `bulk_write` keeps `sqlite_sql=`, accepted and ignored, for `pagerank.py`'s one call (D1 = b) |
| `store.py` | `CATALOG_DDL`, `Store(backend=)`, the connect-time SQLite arm and `_migrate_to_partitions_if_needed` deleted; the 13 kind branches collapsed; the 9 `sqlite_sql=` kwargs gone; the file arms of the fragment load / flush / repair paths gone. NEW `refuse_legacy_catalog(root)` + `LegacyCatalogError` + `LAST_CONVERTING_RELEASE = "0.84.0"`; `Store.__init__` calls it first. `git_tracked_catalogs` / `refuse_tracked_catalog_open` lose `names` (its one caller was the deleted command). `repair_fragments`' `unread_dirs` names every on-disk layout dir, `fragments/` and `bitmaps/` (`_unread_fragment_dirs`). The two `_connect` file moves and their helpers went in the fold ([[#fold]]) |
| `duckdb_catalog.py` | Header rewritten; the incident notes it cited from the SQLite DDL moved in (memory sidecar, bug-039 `derive_stamps`, task 15.2 `derive_history`, the FK list the app enforces). `TABLE_LOAD_ORDER` (migrate-only) deleted |
| `migrate.py` | deleted, with `rmx migrate-to-duckdb` |
| `cli.py` | The group callback runs `_refuse_legacy_root()` before any command except `mcp`; `_RmxGroup.invoke` turns `LegacyCatalogError` into one `Error:` line; `cli_entry` writes no `cli.log` under a refused root. The compact-path kind branch collapsed; the `replica disabled` lines print the daemon's reason instead of "non-duckdb backend". CLI tree regenerated |
| `daemon.py` | 11 kind branches collapsed; skip reasons say "no store" where a branch used to say "non-duckdb" |
| `mcp.py` | `_resolve_root` = `_target_root` + `refuse_legacy_catalog`: an `isError` reply, the server keeps serving |
| `verbs.py` | `snapshot_read`'s kind branch collapsed; `_writer_catalog_files` docstring reworded; `migrate-to-duckdb` dropped from `LEGACY_UNPAIRED` |
| `scripts/check-rel-landing.py` | SQLite arm deleted |
| comments | `replica_merge.py` :7, `eval/retrievers/rmx_retriever.py` :1102 |
| docs | `ARCHITECTURE.md` (box, module table, fragment table, backend section), `agent-doc-primer.md`, `INTEGRATION.md`, `SYSTEM.md`, `PERFORMANCE.md`: one backend, the refusal named |

## The refusal {#refusal}

`store.refuse_legacy_catalog(root)` raises when `<root>/catalog.db` exists and none of
`catalog.duckdb`, `catalog.A.duckdb`, `catalog.B.duckdb` does. Two to four `stat`s; it creates
nothing. The line:

```
<root>/catalog.db: legacy SQLite catalog, this rmx reads DuckDB only. Convert it with refmatrix 0.84.0 (rmx migrate-to-duckdb), or move it aside and run rmx init
```

Call sites (L190): `Store.__init__` (first statement after resolving the root); the CLI group
callback (before any command body, so `daemon start`'s binary-export note and its fork never come
first); `cli_entry`'s telemetry (no `cli.log` written under a refused root); `mcp._resolve_root`.
`catalog.db` stays in `WRITER_CATALOG_FILES`, so the generated hook text is unchanged and a
legacy dir's hooks reach the refusal. {#refusal-sites}

## Kept, against the spec's list, then deleted in the fold {#kept}

Superseded by [[#fold]]: the moves are gone. As first shipped (`56a7ee04`): R3 listed "its two `_migrate_*` moves" for deletion, subject to the caller proof. The proof
failed for both: `_migrate_legacy_bitmaps_if_needed` and
`_migrate_fragments_to_partitions_if_needed` run at the end of EVERY writer `_connect`, both
backends, at `1fadfb61` (:1684 :1687). So they stay, with their helpers (`_partition_fragments_dir`,
`_fragment_path`, `bitmaps_dir`) and the `fragments/` handling in `rename_partition`,
`merge_partition` and `rebuild_index_from_log`. On DuckDB they move files the catalog never
reads; deleting them is a separate decision. {#kept-moves}

## Verification {#verify}

- AC-1/2/3: `tests/test_single_backend.py` 16 passed on the mini at `56a7ee04`
  (`workflow/review-output/s1-green-ac.log`).
- AC-4 mutations (throwaway commits under `refs/mutations/s1-M*`, local lane): M1 (refusal never
  fires) 10 failed; M3 (rotation slots ignored) 1 failed, the `catalog.A.duckdb+active` AC-2
  case; M4 (CLI check dropped) 2 failed, both `daemon-start` cases, first at the traceback
  assert (the detached spawn waits 15 s for a daemon that refused, then raises); M2 survives,
  see [[#m2]].
- AC-5: `git diff 1fadfb61 -- pagerank.py ingest.py vectors.py` is empty; `hooks.py`,
  `search_hooks.py` and `templates/` are unchanged and `hooks.render_managed` + `_store_gate`
  render byte-identical text at base and head (one sha256); `gen-cli-tree.py --check` clean.
- AC-6: full suite at `56a7ee04` in 3 shards: 1801 passed / 4 failed, 1530 / 12 / 1 skipped,
  2006 / 2 / 2 skipped. One failure is S1's, a RED-side baseline ([[#parity]]); every other one
  has the same E line at `1fadfb61` on the same lane (mini: no upstream gmd repo or memory dir,
  bug-282; both lanes: the wall-clock census' stale `< 4.0` entry, `test_models_offline`'s
  hub-constant check). `./scripts/lint-gmd.sh` 0 errors. {#verify-body}

**Tip `7d9cdca8`** (RED's 89ffc465 M2 backstop cases + 68653aeb verb-parity S1 batch,
cherry-picked): `test_verb_parity.py`, `test_single_backend.py`, `test_bug212_r4_red.py` 235
passed on the mini (`s1-green-tip.log`). RED reports M2 now fails all 6 new cases. {#verify-tip}

## For the lead {#for-the-lead}

- **Verb parity, RED side.** `test_legacy_shrinks_by_exactly_the_batched_paths` pins
  `LEGACY_UNPAIRED` to a test-side baseline that still holds `migrate-to-duckdb`; keeping the key
  instead fails the stale-key hygiene test. The baseline needs an S1 batch subtracted (size 90).
  {#parity}

- **AC-4 M2 survives** RED's tests: every AC-1 entry is refused by the CLI group callback or
  `mcp._resolve_root` before `Store.__init__`. A user path that reaches only the `Store.__init__`
  check is `rmx init --path <legacy project>` from a non-legacy cwd (run once by hand: exit 1, the
  one line, nothing created). Reported to the lead; a test would be RED's. {#m2}
- Every command in a legacy dir is refused, `rmx version` and `rmx grep` included; `rmx mcp` is
  the one exemption (it refuses per call). {#scope}
- The callback refuses whatever `_root()` resolves, so a command run from a legacy cwd that
  targets ANOTHER root (`rmx init` from a subdirectory, `rmx init --path <fresh dir>`,
  `rmx focus rebuild --root <other store>`, `rmx hub status`) is refused too. Accepted as design
  (bsd-s1 r1 #m-2, L191): the line is loud and its own fix works; no fleet store is legacy.
  {#scope-m2}

## Fold: bsd-s1 r1 (ruling L191) {#fold}

rel: derives-from -> [[bsd-s1-r1-be1c6b6c]]

- **#b-1 + #s-1.** Deleted `_migrate_legacy_bitmaps_if_needed`,
  `_migrate_fragments_to_partitions_if_needed`, their two calls at the end of `_connect`,
  `_fragment_path`, `_partition_fragments_dir`, the `bitmaps_dir` and `fragments_dir`
  attributes, and the `fragments/` arms in `rename_partition`, `merge_partition` and
  `rebuild_index_from_log`. Their only product was another layout nothing reads, and the
  `bitmaps/` move deleted its `.rb` originals. `_unread_fragment_dirs` stays and now names
  `bitmaps/` dirs too, left in place. RED's
  `test_the_repair_names_and_keeps_every_unread_file_layout_dir` [cli|store × dry-run|applied]
  (59dfea5a) is the test that kills MX4. {#fold-b1}
- **#m-1.** RED pinned the `backend.py` allow entry to its two exact lines; both lines are
  unchanged. {#fold-m1}
- **#m-2.** Accepted as design ([[#scope-m2]]). **#m-3.** ARCHITECTURE's refusal paragraph names
  the `rmx mcp` exemption. **#b-2.** The lead's (29.2 spec amended). {#fold-rest}

