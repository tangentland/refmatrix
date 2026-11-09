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
1. **AC-1b: a move refreshes EVERY row on the old path, not only the id row (r5 s1).**
   - **Why.** A store that predates the `sync-disk` alias (`cli.py:13141`) can hold a second,
     legacy row for one file: `source: memory_sync_disk`, named by the frontmatter `name:`, with
     the same `source_path`. HEAD's bridge only WRITES `source_path` (`ingest_gmd.py:948`) and
     never looks a row up by path, so a move leaves the legacy row on a dead path, and no
     per-file count sees it. Probe of a copy of refmatrix's read snapshot at 3ded49e: 376 memory
     rows under the memdir for 357 files, i.e. 19 files with two rows each.
   - **Rule.** When a marker-on bridge refreshes a moved file (AC-1), it refreshes
     `memory_content.metadata.source_path` on EVERY row in the memory partition whose stored
     `source_path` equals the moved file's OLD path (resolved on both sides, as AC-2), not only
     the row keyed by the file's id. Only `source_path` changes on those extra rows: their entity
     id, name, content, vector, `created_at`, protected/noise flags and edges are untouched.
     The id-row refresh and the extra-row refresh are ONE store write per file, so an id row is
     never refreshed without its legacy rows. HEAD has no primitive for that write; see
     [[#impl-notes-r6]] (r6-lite n1).
   - **Count.** The extra rows are reported as a fourth term, `moved_legacy` (the id row stays
     under `moved`). It is printed in the bridge report, carried by `_bridge_stats` and
     `_bridge_wait_for_active_job`'s result, and reported by `--dry-run`: for each file that
     MOVED, the rows other than the id row that share its stored old path, whatever term the id
     row itself lands in (`moved`, or `stale_before` when its stored path is in symlink form;
     r6-lite n2). A symlinked memdir (viascope, plan-27) is the case where an id row can be
     `stale_before` while its legacy rows still need refreshing; they are counted here, never
     dropped.
   - **RED fixture.** Ingest `a/x.md` (id `x`) in a marker-on dir. Seed a second row with
     `Store` on the THROWAWAY store only: name `legacy-x`, `source: memory_sync_disk`, the same
     resolved `source_path` as `a/x.md`. Move the file to `b/x.md` and bridge again. Expected:
     both rows carry the resolved `b/x.md`; `legacy-x`'s id, content and flags are unchanged;
     the report says `moved = 1`, `moved_legacy = 1`. At HEAD `legacy-x` keeps `a/x.md` and
     there is no such term (RED). Marker-off twin: HEAD behaviour (AC-3b), nothing refreshed.
   - **Out of scope.** Merging or forgetting the legacy duplicate is NOT done here. Both rows
     stay, and recall may still serve the older one; that is a pre-existing condition, and
     removing knowledge is a separate, audited decision
     ([[feedback_decay_never_loses_knowledge]]). This task only keeps their provenance live and
     counted.
2. **AC-2: the gate reuses the path already recorded; it adds no second record (ch-bsd r1 #s5).**
   - For memory rows, the skip requires two things: the hash matches, AND the row's existing
     `memory_content.metadata.source_path` equals the file's resolved path. For doc rows, the
     second condition is that `entities.path` equals the resolved path.
   - Compare on resolved paths on both sides. The daemon resolves its targets
     (`daemon.py:3771`), so a symlinked memdir (viascope) compares equal.
   - No `gmd_source_path` key is added.
   - An unchanged file at an unchanged path is still skipped. The stats count it as skipped, and
     the store write counter does not move.
3. **AC-3: the one-time re-ingest is stated and measured (r2 m4, s2).**
   - A row whose `source_path` is missing, or disagrees with the resolved file path, is
     re-ingested once.
   - This task ships the count itself: `rmx ingest-gmd --as-memory --dry-run <dir>` reports
     `refresh_pending` and writes nothing. The count is NOT a field of the later `organise`
     command, which depends on this task. 26.5's `--check` re-exports the same stat.
   - **Measuring before the deploy (r3 s2).** The dry-run writes nothing, so it runs on the LIVE
     memdir path as a read-only walk. Every row in a store copy stores the live path, so a COPY of
     the memdir would count the relocation the copy made, not the refresh. The store side is the
     one that is copied: the dev build reads a copy of that store's read snapshot in a sandbox
     under a short `mkdtemp()` root. The live store is never opened.
     - **Three NEW flags on `rmx ingest-gmd` (r4 s2).** HEAD's `cli.py:10230` has none of them.
       - `--dry-run`: writes nothing and reports the stats.
       - `--store-snapshot <catalog copy>`: opens that copied catalog IN-PROCESS and read-only.
         It is fully daemonless: it never calls `daemon_mod`, never touches the hub, and never
         resolves the live root.
       - `--path-map <from>=<to>`: rewrites stored paths before comparing them. It is required
         for the relocated twin, so it is NOT an alternative to `--store-snapshot`; the twin uses
         both.
     - **Which gate the dry-run evaluates.** It computes the MARKER-ON path-aware rule (AC-2) for
       every file, whatever the dir's marker says. It answers "what would organising refresh". A
       faithful marker-off run would report 0 in every un-organised dir and measure nothing.
     - **Daemonless is asserted.** The test runs under task 23.0's sandbox connect recorder, with
       `RMX_HOME` pointed at an empty sandbox. The `--store-snapshot` run must succeed and record
       ZERO socket connects to any daemon or hub socket.
     - **Stats split for the post-apply check (r4 s3; r5 s1).** The bridge reports re-ingested
       rows as three terms: `moved`, `stale_before` (a path that disagreed before any move:
       missing or symlink-form `source_path`) and `forced` (save-states forced by 26.5 AC-5 that
       were not moved). A fourth term, `moved_legacy` (AC-1b), counts the extra rows refreshed
       alongside ANY id row whose file moved, including an id row classified `stale_before`
       (r6-lite n2); it is a row count, not a file count.
     - **Relocated-twin RED case.** Copy the memdir with nothing changed and dry-run it through
       `--path-map`. It must report `refresh_pending = 0`. Without the map it reports about 100%,
       and that "~100%" is exactly the defect this case pins.
     - **Pre-registered expectation (r6-lite n2).** `refresh_pending` = rows with a missing
       `source_path` + rows whose stored path is a symlink form of the file's resolved path +
       files moved since their last ingest + `moved_legacy` (the extra rows on a moved file's old
       path, AC-1b). This is the same quantity 26.5 AC-8 re-exports. The measurement script, and
       the dry-run report, print each of the four terms on its own line.
   - 26.8 AC-0 records the result for every store before the deploy.
4. **AC-3b: the gate is marker-gated (r2 s2).** The path-aware gate and its refresh writes apply
   only to files under a memdir with `.memory-layout` (26.1 `is_organised`). In an un-organised
   dir the gate is HEAD's hash-only gate, so the deploy causes no fleet-wide refresh. Test: the
   AC-1 move in an un-organised dir behaves as at HEAD (stale path kept); with the marker, it
   refreshes.
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
- Modify `src/refmatrix/cli.py` `ingest-gmd` options (`:10230`): `--dry-run`, `--store-snapshot`
  (an in-process read-only open of the copied catalog, never `daemon_mod`) and `--path-map`
  (r4 s2).
- Modify `src/refmatrix/ingest_gmd.py`: dry-run stats with the `moved` / `stale_before` /
  `forced` split, plus `moved_legacy` (r5 s1).
- Modify `src/refmatrix/ingest_gmd.py`: the move refresh updates every row on the old
  `source_path` in one write (AC-1b).
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
| refresh the id row only (HEAD's write) | AC-1b goes RED |
| drop the field from the waited-job result | the AC-4 waited case goes RED |

## Revision round 1 (2026-11-09) {#rev-round-1}

| finding | change | anchor |
|---|---|---|
| S5 (a second copy of the path; an unstated full re-ingest) | Gate on the existing resolved `source_path` / `entities.path`; no new key; `refresh_pending` count; cost measured in 26.8/27.1 | AC-2, AC-3 |
| M5 (the waited-job branch) | `_bridge_wait_for_active_job` carries `duplicate_ids` | AC-4 |

## Revision round 2 (2026-11-09) {#rev-round-2}

Answers [[bsd-plan26-27-spec-review-r2-8af766a]].

| finding | change | anchor |
|---|---|---|
| m4 (26.2 shipped a field of a command 26.5 creates) | `refresh_pending` is a bridge `--dry-run` stat; 26.5 re-exports it | AC-3 |
| s2 (refresh before plan-27's backups; "before the deploy" impossible) | Measured with the dev build on copies of each memdir plus a store-snapshot copy; refresh writes marker-gated | AC-3, AC-3b |

## Revision round 3 (2026-11-09) {#rev-round-3}

Answers [[bsd-plan26-27-spec-review-r3-696c3cb]].

| finding | change | anchor |
|---|---|---|
| s2 (copying the memdir counts the relocation, ~100% pending) | Dry-run on the LIVE memdir path (read-only) against a snapshot COPY of the store; `--path-map` alternative; relocated twin must report 0; expectation pre-registered term by term | AC-3 |

## Revision round 4 (2026-11-09) {#rev-round-4}

Answers [[bsd-plan26-27-spec-review-r4-f89e640]].

| finding | change | anchor |
|---|---|---|
| s2 (three flags that did not exist; which gate; daemonless unspecified) | `--dry-run`, `--store-snapshot` and `--path-map` added to `rmx ingest-gmd` (`cli.py:10230`); the dry-run evaluates the marker-on rule; the `--store-snapshot` path is in-process and asserted socket-free under 23.0's connect recorder | AC-3, [[#files]] |
| s3 (the post-apply comparison mixed terms) | Bridge stats split into `moved` / `stale_before` / `forced` | AC-3 |

## Implementation notes (r5) {#impl-notes-r5}

Answers [[bsd-plan26-27-spec-review-r5-3ded49e]] findings that ride as notes.

- **m3, term precedence.** A re-ingested row is in exactly ONE term, chosen by its stored
  path's shape: a missing or symlink-form `source_path` → `stale_before`; otherwise a real,
  different path → `moved`. `forced` is only a save-state in neither. `moved_legacy` counts the
  extra rows of AC-1b and never an id row. The comparable pre-deploy number for `stale_before`
  is AC-3's first two pre-registered terms (missing + symlink-form), not the whole
  `refresh_pending` (26.8 AC-2).
- **m4, the socket assertion.** Task 23.0's sandbox REFUSES live sockets
  (`rmx_sandbox.violation`, `tests/conftest.py:176`); it does not record a connect to a sandbox
  socket. The AC-3 "ZERO connects" assertion therefore installs a test-local
  `sys.addaudithook` that appends every `socket.connect` address to a list while a flag the
  test sets is on (audit hooks cannot be removed, so the hook is gated, installed once per
  process). The `--store-snapshot` run must leave that list empty.

## Implementation notes (r6-lite) {#impl-notes-r6}

Answers [[bsd-plan26-27-spec-confirm-r6-lite-d396317]] n1 and n2, which ride as notes.

rel: derives-from -> [[bsd-plan26-27-spec-confirm-r6-lite-d396317]]

- **n1, AC-1b's "ONE store write" has no primitive at HEAD.** Read at 2390e57:
  - `Store.add_memory` (`store.py:2447`) ends with an unconditional `con.commit()`
    (`store.py:2506`), not `_maybe_commit` (`store.py:4534`). Inside an outer
    `store.transaction()` (`store.py:4546`) that commit ends the transaction early.
  - The bridge (`ingest_gmd.py`) opens no `transaction()` at all.
  - An UPDATE of the legacy rows' `memory_content.metadata` emits no facts.log event, so replay
    (`_apply_one_event`, `store.py:7778`; the `memory_content` branch at `store.py:7879`)
    restores the OLD path on `rebuild --from-log`.

  Required:
  - Wrap the id-row `add_memory` and the legacy-row refresh in ONE `store.transaction()`:
    switch `add_memory`'s commit to `_maybe_commit`, or add a dedicated store method that does
    both writes in one scope.
  - Log each legacy row's refresh as a `memory_content` event carrying the updated metadata,
    so replay reproduces it. **Cross-plan note from 23.1 (r6 round, 2026-11-09):** the event
    also carries `updated_at` (the row's stored `memory_content.updated_at` after the refresh),
    the field 23.1 R11.3 adds to every `memory_content` event and makes both replay paths read
    ([[task-23.1-queue-and-drain#r11]] item 3.3); 26.2 merges first, so replay ignores the field
    until 23.1 lands, and nothing in 26.2's ACs changes. See [[#rev-round-6]].
  - Test: after the AC-1b fixture, replay the throwaway store's facts.log into a FRESH store and
    assert `legacy-x` carries the resolved `b/x.md`. Mutation: drop the legacy event and the
    test goes RED.
- **n2, where `moved_legacy` sits.** `refresh_pending` is four terms: the three file terms of
  AC-3 + `moved_legacy` (AC-3, matching 26.5 AC-8). `moved_legacy` is counted beside ANY id row
  whose file moved, whatever term that id row lands in under [[#impl-notes-r5]]'s precedence,
  including `stale_before` (symlink-form stored path). refmatrix has 0 such rows (r6-lite probe),
  so 26.8 is unchanged; viascope's symlinked memdir (plan-27) is where it can occur. Test: the
  AC-1b fixture under a symlinked memdir whose id row stored the symlink form reports the id
  row as `stale_before` and `moved_legacy = 1`.

## Revision round 5 (2026-11-09) {#rev-round-5}

Answers [[bsd-plan26-27-spec-review-r5-3ded49e]].

rel: derives-from -> [[bsd-plan26-27-spec-review-r5-3ded49e]]

| finding | change | anchor |
|---|---|---|
| s1 (19 legacy `memory_sync_disk` rows keep the pre-move `source_path`, uncounted) | Every row on the old path is refreshed in one write; fourth term `moved_legacy`; RED fixture with a second, differently named row; merge/forget out of scope | AC-1b, AC-3, [[#files]] |
| m3 (terms defined two ways; no precedence) | Precedence by stored-path shape; `stale_before` compares with AC-3's first two terms | [[#impl-notes-r5]] |
| m4 (23.0 does not record sandbox connects) | Test-local `sys.addaudithook` on `socket.connect` | [[#impl-notes-r5]] |

## Revision round 6 (2026-11-09) {#rev-round-6}

Cross-plan implementation note only; plan-26 stays approved and no requirement, AC or mutation
of 26.2 changes. Source: [[bsd-plan23-fold-additions-a9147d5#s1]], folded into 23.1 as
[[task-23.1-queue-and-drain#rev-round-13]]: 23.1's authoring-time guard compares stored
`memory_content.updated_at`, so every `memory_content` event must carry that value for
`rebuild --from-log` to reproduce it.

rel: derives-from -> [[bsd-plan23-fold-additions-a9147d5]]
rel: related-to -> [[task-23.1-queue-and-drain#rev-round-13]]

| finding | change | anchor |
|---|---|---|
| 23.1 s1 (cross-plan note from 23.1: the authoring time must survive replay) | The n1 legacy-row `memory_content` event carries `updated_at`, the stored value | [[#impl-notes-r6]] |
