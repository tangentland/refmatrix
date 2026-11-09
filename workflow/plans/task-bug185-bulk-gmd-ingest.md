---
gmd: "0.1"
id: task-bug185-bulk-gmd-ingest
title: "Task bug-185: ingest_gmd_paths writes nodes, anchor concepts and mention links in bulk; a GMD re-ingest's hold stops growing with its anchor count"
tags: [task, bug-185, gmd, ingest-gmd, writer-lock, performance, bug-093, bug-177, bug-178]
metadata:
  node_type: task
  status: drafting
  created: 2026-11-09
  updated: 2026-11-09
---

# Task bug-185: bulk GMD ingest {#root}

> Status: Drafting (2026-11-09). Decided by [[bsd-plan23-3-5-freshness-62a2465#b1]] fix step 2:
> no user decision remained; the user's goal ([[plan-of-plans#goal-2026-11-09-scope]]) puts
> bug-177's holders in scope.
> Depends on: bug-178 merged to `master` ([[task-bug178-bulk-write-helper]]: `backend.bulk_write`,
> and `bulk_upsert_entity` lifted onto it) AND plan-26 merged to `master` (26.1 and 26.2 edit
> `ingest_gmd.py`, [[task-26.2-bridge-move-safety]]).
> Blocks: [[task-23.3-sync-between-file-yield#ac-4b]] (needs this task's bulk path to go GREEN).

rel: derives-from -> [[bug_registry]] {bug: "bug-185"}
rel: derives-from -> [[bsd-plan23-3-5-freshness-62a2465#b1]]
rel: evidence-for -> [[bsd-plan23-3-5-freshness-62a2465#p-gmd-cost]]
rel: depends-on -> [[task-bug178-bulk-write-helper]]
rel: depends-on -> [[task-26.2-bridge-move-safety]]
rel: related-to -> [[task-23.3-sync-between-file-yield#r1]]
rel: reinforces -> [[feedback_converge_repeated_shapes]]
rel: related-to -> [[feedback_go_no_go_ranges_not_predrop]]

## Why {#why}

On 2026-11-09 the four longest `_store_lock` windows on the live store (87.4 s, 71.7 s, 94.2 s,
53.9 s) each started at a commit that touched `workflow/bullshit/IMPRESSIONS.md`. In each window,
one sync did the work (the watch flush or the first `sync --since`) and re-ingested that GMD
ledger. The others logged `touched=0`, so they were waiting behind it
([[bsd-plan23-3-5-freshness-62a2465#p-holder]]).

Profiled on an APFS clone of the read catalog (`workflow/review-output/bsd-probe-sync-impr.log`):
- `IMPRESSIONS.md` (219 anchors) takes **39.5 s** inside one `ingest_gmd_paths` call.
- That time is 854 single-row `Store.upsert_entity` calls at 41 ms each. `Store.add_concept` is
  called 211 times at 124 ms each, and each call upserts the canonical name and its variants one
  row at a time.

That is bug-093's per-row shape. Its 0.76.3 fix moved the Python semantic pass onto
`bulk_upsert_entity` / `_bulk_add_concepts`. The GMD path's unconditional concepts are already
bulk (`ingest_gmd.py`, the `concept_specs` → `_bulk_add_concepts` block in pass 2). Three writes
are still per-row:
- pass 1's per-node `store.upsert_entity(kind="concept", …)`;
- pass 2's per-wikilink `store.add_concept(anchor)`, followed by `store.link("mentions", …)`;
- `_resolve_target_eid`'s per-target `store.get_entity` lookups (3 kinds each).

The ingest-gmd job (the bridge, session cards) runs the same code and yields only every 10
documents, so its per-document hold has the same cause: 29 s for one session card at
2026-11-08 23:59:16. {#why-fact}

## Requirements {#requirements}

1. **R1 Pass 1's node entities are written in bulk.**
   - For each document, collect the node rows `(kind="concept", name, path, tldr, meta)` in
     today's order, then write them with ONE `store.bulk_upsert_entity(rows)` call. Today's
     per-node `upsert_entity` loop is removed.
   - `eid_by_name` is filled from the returned ids in input order, keeping `setdefault`'s
     first-wins rule.
   - Duplicate names inside one batch merge in input order, as a row-by-row sequence would.
     bug-178 already guarantees this for `bulk_upsert_entity`.
   - The doc-level row, the ADR slash alias and the `as_memory` sidecar stay as they are, a
     constant number of writes per document that does not depend on the anchor count, so that
     26.2's single-transaction id-row path is untouched ([[#compose-26-2]]).
   - `_node_tick`'s intra-document yield cadence (`RMX_INGEST_NODE_YIELD_EVERY`) now counts
     batches instead of rows. Its yield point moves to between documents (and between chunks,
     R4). It must never fire inside a bulk write.
   {#r1}
2. **R2 Pass 2's wikilink anchor concepts and their mention links are written in bulk.**
   - Pass 2 first resolves every wikilink target for the document. Names not in `eid_by_name`
     are looked up in ONE batched store read: `(kind, name) → id` for the list of names, in
     today's precedence order `concept`, `doc`, `memory`, at most one statement per kind. This
     replaces `_resolve_target_eid`'s per-target `get_entity` calls. Results are cached in
     `eid_by_name`, as today.
   - The resolved anchor concepts are created in one `_bulk_add_concepts(store, specs)` call,
     with the description `GMD anchor '<name>'`, first description wins, so variant expansion is
     unchanged.
   - The `mentions` links (`concept → source`, weight `None`) are written with ONE
     `store.bulk_link` call per document, using the conflict rule that leaves a stored weight
     untouched when the incoming weight is NULL, the same as `store.link` with no weight today.
     If that rule cannot be expressed through `bulk_link` (`update_weight=False` vs `True` with
     NULL weights), the implementer states which flag reproduces HEAD and AC-2 proves it.
   - `stats.mentions` and `stats.unresolved` (path, line, ref) stay identical, including the
     unresolved list's order.
   {#r2}
3. **R3 Semantics unchanged.** The same input produces, compared with HEAD:
   - the same `entities`, `entity_links`, `linkage_evidence`, `bitmap_fragments` and
     `memory_content` rows (ids may differ only where HEAD's own allocation order would differ,
     and AC-2 states that rule exactly);
   - the same `IngestStats`;
   - the same `gmd_content_hash` stamps and resume behaviour (a hash is written only after
     pass 2 completes).

   facts.log events are unchanged as a multiset: `bulk_upsert_entity` already emits one entity
   event per row. Replaying the new code's facts.log into a fresh store gives the same catalog
   digest as replaying HEAD's. A causal order that replay depends on (an entity event before any
   link event that names it) is kept. {#r3}
4. **R4 Bounded batch size.** A document with more node or concept rows than
   `RMX_GMD_BULK_CHUNK` (default 2,000, read once per call) is written in chunks of that size.
   Chunks are the only place an intra-document yield may fire, and only when no transaction is
   open (today's rule for `_node_tick`). Under `_sync_paths`'s outer transaction there is no
   `yield_lock`, so no yield happens there. {#r4}
5. **R5 No new mechanism.** The writes go through `bulk_upsert_entity`, `_bulk_add_concepts`
   and `bulk_link`, which all sit on bug-178's `backend.bulk_write`. No second Arrow or
   executemany path is added, and bug-178's executemany guard (its R3) still passes. {#r5}

## How it composes with 26.2's one-transaction legacy-row refresh {#compose-26-2}

[[task-26.2-bridge-move-safety]] (n1 in its round-6 notes) wraps the `as_memory` id row's
`add_memory` and the moved file's legacy-row refresh in ONE `store.transaction()`, and it
switches `add_memory`'s unconditional `con.commit()` to `_maybe_commit`. This task:
- does not touch that scope. The doc-level write stays a constant per-document write, outside
  R1's node batch;
- runs its bulk writes AFTER the doc-level transaction closes, or inside an enclosing outer
  transaction when there is one (`_sync_paths`' `with s.transaction()`). It never opens a
  transaction that crosses 26.2's scope;
- relies on `bulk_upsert_entity` / `bulk_link` committing through `_maybe_commit` (verified on
  the bug-178 branch at `e6da8c3`: `bulk_upsert_entity` calls `self._maybe_commit(con)`), so a
  bulk write never ends an enclosing transaction early. That is the same defect 26.2 n1 fixed
  for `add_memory`. AC-6 asserts it.

The two edits are disjoint in `ingest_gmd.py`. 26.2 changes the resume gate, the duplicate-id
stats, the move refresh and the report line. This task changes the pass-1 node loop and pass 2's
wikilink block. Because this task lands second, it is written against 26.2's merged code, and
its line references are re-stamped at RED.

## Acceptance criteria {#acceptance}

All tests run on a throwaway store under a short `mkdtemp()` root. No live store is opened.
Logs go to `workflow/review-output/pytest-bug185.log`.

1. **AC-1 (RED at HEAD): no per-row writes.** Re-ingest an IMPRESSIONS-shaped GMD fixture with
   ≥ 200 anchors and ≥ 200 resolvable wikilinks. The fixture is generated deterministically and
   committed under `tests/fixtures/`, never a copy of the live ledger.
   - Pass-through spies count `Store.upsert_entity`, `Store.add_concept` and `Store.get_entity`
     calls made from `ingest_gmd_paths`.
   - Calls that scale with the document are ZERO. The per-document constant (doc row, slash
     alias, memory sidecar) is ≤ 3 calls per document and is the same at 50 and at 200 anchors.
   - At HEAD this fails: the spies see hundreds of calls.
   - Mutation: restoring the pass-1 per-node `upsert_entity` loop FAILS.
   {#ac-1}
2. **AC-2 (equivalence, golden from HEAD).** For the AC-1 fixture, a 50-anchor fixture, an
   `as_memory` fixture, and a fixture that includes intra-document duplicate anchors, an ADR
   slash alias, cross-document targets already in the store (the batched lookup's `concept` →
   `doc` → `memory` precedence) and unresolved targets:
   - a canonical dump of the five tables in [[#r3]], plus `IngestStats.as_dict()`, is hashed
     and compared with a golden recorded at HEAD on the RED commit
     (`tests/fixtures/bug185_head_golden.json`, recording the HEAD sha, in the same shape as
     bug-178's `bug178_head_golden.json`);
   - the facts.log replay digest ([[#r3]]) matches as well.
   - Mutation: a `bulk_link` flag that overwrites NULL-weight mentions FAILS.
   {#ac-2}
3. **AC-3 (statements per hold are flat).** Run inside one `with s.transaction()` (one hold),
   with a pass-through spy on the DuckDB wrapper's `execute` (and on `executemany` / `bulk_write`
   on the bug-178 branch). Re-ingesting the 50-anchor and the 200-anchor fixtures executes the
   same number of statements, ± 2. At HEAD the counts differ by hundreds. 23.3 AC-4b later
   asserts the same thing per `bounded_steps` step under 23.2's recorder
   ([[task-23.3-sync-between-file-yield#ac-4b]]). {#ac-3}
4. **AC-4 (timing; pre-registered bar, measured before GREEN is accepted).** Wall time of one
   re-ingest of the AC-1 fixture, HEAD vs new, on the same machine, store and fixture. Run 5
   times and take the median.
   - **Pre-registered bar: the new path is ≥ 10× faster than HEAD.** For scale, the measured
     HEAD cost on the live-catalog clone is 39.5 s for 219 anchors, so the bar there is ≤ 3.95 s.
   - The same re-ingest of `IMPRESSIONS.md` on a fresh APFS clone of the live read catalog
     (`cp -c`, scratchpad, deleted afterwards, the report's probe method) is recorded with its
     wall time and per-call profile.
   - Bands, written now:
     - ≥ 10×: GO;
     - 5-10×: GO only if the profile names the remaining per-row cost and a follow-up row is
       logged;
     - < 5×: STOP and report to the user. The bar is not lowered
       ([[feedback_go_no_go_ranges_not_predrop]]).
   {#ac-4}
5. **AC-5 (SQLite).** The same fixtures still ingest on the SQLite backend, and the existing
   GMD ingest tests stay green (`tests/test_ingest_gmd*.py`, the bridge and memory-bridge tests,
   bug-179's parity test if it has merged). {#ac-5}
6. **AC-6 (no early commit).** Run `ingest_gmd_paths` inside an outer `store.transaction()`
   that is rolled back on purpose after the call returns. The store must hold none of the
   call's rows. This proves no bulk write committed the enclosing transaction. Mutation: an
   unconditional `con.commit()` in the bulk path FAILS. {#ac-6}
7. **AC-7 (full suite).** No new failures compared with the pre-change `master` sha, compared by
   error text ([[feedback_compare_failures_by_error_not_name]]). {#ac-7}

## Merge order {#merge-order}

3.7 → bug-178 → plan-26 → **this task** → 23.2 → 23.1 → 23.3 ∥ 23.5. This task does not need
the 23.x harness or recorder, so it ships as a standalone bug release right after plan-26. It is
the largest single cut in live hold time ([[bsd-plan23-3-5-freshness-62a2465#order]]). 23.3's
per-document `bounded_steps` step and its AC-4b build on it.

## Files to modify {#files}

- `src/refmatrix/ingest_gmd.py`: the pass-1 node loop, pass 2's wikilink block, and a batched
  target lookup that replaces `_resolve_target_eid`'s per-target reads.
- `src/refmatrix/store.py`: only if no batched `(kind, name) → id` read exists. If one is
  added, it is a single read method, not a second write path.
- New `tests/test_bug185_bulk_gmd_ingest.py`, plus `tests/fixtures/bug185_*` (generated
  fixtures and the HEAD golden).
- `workflow/bug_registry.md` (the bug-185 row), and the implementation summary
  `workflow/implementation_summaries/bug-185-bulk-gmd-ingest.md`, which records AC-4's table
  and the RED sha.
