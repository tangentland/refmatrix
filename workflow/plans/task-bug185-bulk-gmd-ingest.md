---
gmd: "0.1"
id: task-bug185-bulk-gmd-ingest
title: "Task bug-185: ingest_gmd_paths writes nodes, anchor concepts, mention links and rel edges in bulk; a GMD re-ingest's hold stops growing with its anchor count"
tags: [task, bug-185, bug-186, gmd, ingest-gmd, writer-lock, performance, facts-log, replay, bug-093, bug-177, bug-178, bug-216]
metadata:
  node_type: task
  status: approved
  created: 2026-11-09
  updated: 2026-11-13
---

# Task bug-185: bulk GMD ingest {#root}

> Status: **Approved** (2026-11-09, revision round 1: every finding of
> [[bsd-bug185-spec-r1-da67220]] (0B/4S/5M) folded, see [[#rev-round-1]]; no user decision
> remained). Decided by [[bsd-plan23-3-5-freshness-62a2465#b1]] fix step 2: no user decision
> remained; the user's goal ([[plan-of-plans#goal-2026-11-09-scope]]) puts bug-177's holders in
> scope.
> **Revision round 2 (2026-11-13): freshness against bug-216** ([[#rev-round-2]]; plan review
> L3, L4, L31). R2 resolves with bug-216 R6's precedence. The "minted earlier" rule never beats a
> same-named doc or memory. bug-216's pending-ref (R10) and `denotes` (R7) writes join the bulk
> writes ([[#r8]]), and a fourth entry point, `gmd_finish`, carries them. AC-2's golden is recorded
> on the post-bug-216 tree. The gate is narrowed. **Two open items block RED:**
> [[#open-replay-216]] and [[#open-finish-stop]]. The lead settles them; this revision picks
> neither.
> Depends on (narrowed by L4, round 2; the old text was "plan-26 merged"):
> - bug-178 merged to `master` ([[task-bug178-bulk-write-helper]]: `backend.bulk_write`, and
>   `bulk_upsert_entity` lifted onto it). SATISFIED: `76ec748`.
> - 26.1 + 26.2 merged to `master`. SATISFIED: `9b2c4ac` and `05164ce`. These are the plan-26
>   tasks that edit what this task rewrites ([[task-26.2-bridge-move-safety]]; 26.2 n1 already
>   moves `add_memory` to `_maybe_commit`). 26.3, 26.4 and 26.6 also touched `ingest_gmd.py`, but
>   not R1/R2's code ([[#rev-round-2-facts]]). The plan-26 tasks still to come (26.5, 26.7-26.9)
>   do not gate this task.
> - **bug-216 merged to `master`** ([[task-bug216-rule-docs-in-graph]]; L3). R2 and [[#r8]] are
>   written against its resolver and its pending-ref / `denotes` writes. AC-2's golden is
>   recorded on a `master` that contains them.
> Also fixes: bug-186 (facts.log replay drops link weights), [[#r6]].
> Blocks: [[task-23.3-sync-between-file-yield#ac-4b]] (needs this task's bulk path and its
> per-document entry points, [[#r7]], to go GREEN).

rel: derives-from -> [[bug_registry]] {bug: "bug-185"}
rel: derives-from -> [[bsd-plan23-3-5-freshness-62a2465#b1]]
rel: evidence-for -> [[bsd-plan23-3-5-freshness-62a2465#p-gmd-cost]]
rel: depends-on -> [[task-bug178-bulk-write-helper]]
rel: depends-on -> [[task-26.2-bridge-move-safety]]
rel: depends-on -> [[task-bug216-rule-docs-in-graph]]
rel: derives-from -> [[plan-review-2026-11-13#lead]]
rel: related-to -> [[task-23.3-sync-between-file-yield#r1]]
rel: reinforces -> [[feedback_converge_repeated_shapes]]
rel: related-to -> [[feedback_go_no_go_ranges_not_predrop]]
rel: implements -> [[bug_registry]] {bug: "bug-186"}

## Why {#why}

On 2026-11-09 the four longest `_store_lock` windows on the live store (87.4 s, 71.7 s, 94.2 s,
53.9 s) each started at a commit that touched `workflow/bullshit/IMPRESSIONS.md`. In each window,
one sync did the work (the watch flush or the first `sync --since`) and re-ingested that GMD
ledger. The others logged `touched=0`, so they were waiting behind it
([[bsd-plan23-3-5-freshness-62a2465#p-holder]]).

Profiled on an APFS clone of the read catalog (`workflow/review-output/bsd-probe-sync-impr.log`):
- `IMPRESSIONS.md` took **39.5 s** (profiled `sync_files`) inside one `ingest_gmd_paths` call.
  At `4965b12` the file has 221 parsed nodes (220 node rows), 211 wikilink refs and **0** `rel:`
  lines ([[bsd-bug185-spec-r1-da67220#p-rels]]). Unprofiled, r1 measured a median of 36.40 s for
  `ingest_gmd_paths` and 37.81 s for `sync_files` ([[bsd-bug185-spec-r1-da67220#p-baseline]]).
- That time is 854 single-row `Store.upsert_entity` calls at 41 ms each. Only ~220 of them are
  pass-1 node rows; the rest are `add_concept`'s canonical + variant upserts (211 calls, up to 3
  rows each). `Store.add_concept` is called 211 times at 124 ms each. 854 is a call count, not a
  node count.

That is bug-093's per-row shape. Its 0.76.3 fix moved the Python semantic pass onto
`bulk_upsert_entity` / `_bulk_add_concepts`. The GMD path's unconditional concepts are already
bulk (`ingest_gmd.py`, the `concept_specs` → `_bulk_add_concepts` block in pass 2). Four writes
are still per-row:
- pass 1's per-node `store.upsert_entity(kind="concept", …)`;
- pass 2's per-wikilink `store.add_concept(anchor)`, followed by `store.link("mentions", …)`;
- pass 2's per-`rel:` `store.link(verb, …)` + `store.add_evidence(…)`, and the same pair again for
  the root mirror (`ingest_gmd.py:~1256-1286`). `IMPRESSIONS.md` has 0 rels, so the profile could
  not show them; the 23.5 spec has 50, the memory corpus averages ~4.6 per document;
- `_resolve_target_eid`'s per-target `store.get_entity` lookups (up to 3 kinds each).

bug-216 (merged before this task, L3) adds more per-row writes to the same path
([[#rev-round-2-facts]]):
- one pending row per unresolved `rel:` line (`add_pending_ref`, a SELECT and an INSERT each);
- per pending row its batch resolves, a `link`, an `add_evidence` and a `delete_pending_ref`;
- per new `denotes` pair, a `link` (`Store.link_denotes`).

[[#r8]] makes them bulk. The `ingest_gmd.py` line numbers in this section are `4965b12`'s, and
they are re-stamped at RED.

The bulk floor for the same 220 node rows, 195 distinct anchor concepts and 211 mention links,
written with `bulk_upsert_entity` + `_bulk_add_concepts` + `bulk_link` in one transaction on the
same clone, is **0.61 s** including commit and fragment flush.

The ingest-gmd job (the bridge, session cards) runs the same code. `_op_ingest_gmd` passes
`yield_every=int(RMX_INGEST_YIELD_EVERY or 1)` (`daemon.py:~3656`), so the job yields after EVERY
document, and its per-document hold has the same cause: 29 s for one session card at
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
2. **R2 Pass 2 is written in bulk, in a pinned order that reproduces HEAD's resolution.**
   "HEAD" means the post-bug-216 `master` this task's RED is recorded on (round 2, L3). Its
   resolver is [[task-bug216-rule-docs-in-graph#r6]], not the concept-first order this spec
   pinned in round 1. For each document, in this order:
   0. **The document's previous `rel:` evidence and pending rows are cleared** (bug-216 R10,
      unchanged): `clear_rel_evidence(path)` and `clear_pending_refs_for_file(path)` run before
      step 1. Each is one count and at most one delete per document, so the cost is constant.
   1. **Unconditional concepts** (unchanged): `cids = _bulk_add_concepts(store, concept_specs)`.
      It runs BEFORE any target is resolved, as at HEAD, because 2 `rel:` targets and 7 refs in
      the real corpus resolve only through the document's own unconditional concepts (e.g.
      `docs/INDEX.md:19 catalogs -> system_design_review`,
      [[bsd-bug185-spec-r1-da67220#p-corpus]]).
   2. **One batched read.** Every candidate name the document's walk can ask for is collected:
      `rel:` targets, ref targets, and each one's ADR slash fallback (`_adr_slash_alias`). The
      names not in `eid_by_name` are looked up in ONE batched store read, `(kind, name) → id`,
      at most one statement per kind. Each name resolves in bug-216 R6's precedence (round 2,
      L3):
      - a BARE target (no `#anchor`) tries `doc`, then `memory`, then `concept`; a concept
        counts only when no doc or memory of that name exists;
      - an ANCHORED target (`doc#id`) tries `concept`, then `doc`, then `memory`.

      This replaces the per-target `get_entity` calls of `_resolve_target_eid` and of bug-216's
      `_resolve_ref` (the ADR slash bridge). Hits are cached in `eid_by_name` under bug-216's
      rule: a bare name's `concept` hit is never cached there. The walk keeps such hits in a
      per-document table instead. Round 1's text read the concept-first order for every
      target, and that order is the misbinding bug-216 removes.
   3. **Resolution walk in HEAD's order**: node by node; within a node its `rel:` lines, then its
      refs; within each target the plain name, then the slash fallback. The walk reproduces one
      HEAD behaviour the batched read alone cannot see: HEAD does not cache a miss, so a target
      that misses the store but was MINTED EARLIER IN THE SAME DOCUMENT by a ref's `add_concept`
      (its canonical name or a space/dash variant, e.g. `[[#zeta-x]]` minting `zeta-x` before a
      later `rel: depends-on -> [[zeta-x]]`) resolves to that concept. The walk keeps the set of
      names the document's earlier refs mint (the same variant expansion `add_concept` uses) and
      resolves such a target to that concept, whose id is filled in after step 4.
      **The rule never beats a same-named doc or memory (round 2, L3).** A ref mints only bare
      names (an anchor id or a target doc id, and their variants), so the rule applies to bare
      targets only. Under R6 a bare target takes a `doc` or `memory` before any `concept`. So
      the walk resolves a target to a minted concept ONLY when `eid_by_name` holds no doc or
      memory id for it AND step 2's read found no `doc` or `memory` of that name. Otherwise the
      doc (or memory) wins, as it does at post-bug-216 HEAD.
      `stats.unresolved` is appended in walk order, so its order is unchanged. Each unresolved
      `rel:` target also becomes a pending row ([[#r8]] (a)), recorded in walk order.
   4. **Anchor concepts**: ONE separate `_bulk_add_concepts(store, anchor_specs)` call AFTER
      step 1, never folded into `concept_specs`. `anchor_specs` is the walk's anchor names in
      walk order, each with the description `GMD anchor '<name>'`. Description rule: HEAD's
      `entities.meta` is COALESCE, last non-null wins ACROSS calls, so the anchor description
      overwrites a body-term or title-token description written in step 1 for the same concept
      ([[bsd-bug185-spec-r1-da67220#p-semantics]]). Keeping it a later, separate call reproduces
      that; folding it into step 1 would let the body-term description win.
   5. **`rel:` edges** (decided: bulk, [[#rev-round-1]] m1): every resolved rel and its root
      mirror are written with ONE `store.bulk_link(rel_items, update_weight=True)` (per-row
      `link()`'s last-non-null-wins rule; the weight is `_authority` when it is not 1.0, else
      `None`) and ONE `store.bulk_add_evidence(evidence_items)` (new, [[#r5]]), both in walk
      order, written BEFORE `link_batch` (HEAD's direct-call order). `_ensure_linkage` runs once
      per distinct verb. `stats.rels` is unchanged. The document's unresolved `rel:` lines
      become pending rows with ONE batched insert, [[#r8]] (a), in the same position.
   6. **Unconditional links** (unchanged): `store.bulk_link(link_batch, update_weight=True)`.
   7. **Mention links**: ONE `store.bulk_link(mention_items)` per document, weight `None`,
      AFTER `link_batch`. With the bit already set by `link_batch` (a concept that is both a
      body term and an anchor), a `None` weight leaves the stored tf weight untouched under
      either flag, as at HEAD; and because the bit is not new, no `None` event is logged after
      the weighted one ([[#r6]]). `stats.mentions` is unchanged.
   8. The `gmd_content_hash` stamp, as today (after pass 2 completes).
   {#r2}
3. **R3 Semantics unchanged: the equivalence contract.** The same input, in the same calling
   context, produces, compared with HEAD:
   - (a) **the same catalog**: the canonical dump ([[#ac-2]]) of `entities`, `entity_links`,
     `linkage_evidence`, `bitmap_fragments`, `memory_content` and (round 2) bug-216's
     `pending_refs`, keyed by name. Also the same `IngestStats` (round 2: its `as_dict()` carries
     bug-216's `pending_recorded`, `pending_resolved`, `pending_dropped` and `denotes_added`),
     the same `gmd_content_hash` stamps and resume behaviour (a hash is written only after
     pass 2 completes; where it sits relative to [[#r7]]'s `gmd_finish` is
     [[#open-finish-stop]]);
   - (b) **a facts.log that names every row**: every `entity_links` row the call leaves has at
     least one `link` event naming it, and every entity event precedes any link event that names
     that entity;
   - (c) **replay fidelity**: rebuilding a fresh store from the NEW code's facts.log reproduces
     the NEW code's own catalog dump (minus the excluded columns). **Round 2: this cannot hold
     as written on the post-bug-216 tree, and the cause is not this task.** bug-216's
     `clear_rel_evidence` deletes evidence rows and logs no event, and its `pending_refs` table
     has no event at all. So a job-path v1 → v2 re-ingest leaves one evidence row per `rel:`
     line in the catalog and two in a replay, and every replay loses the pending rows. How (c)
     treats both is [[#open-replay-216]], settled by the lead before RED. This spec does not
     weaken (c) to fit.

   facts.log is NOT a multiset match with HEAD's, by construction: per-row `link()` logs every
   call, `bulk_link` logs only newly set bits (plus, after [[#r6]], weight updates), and
   `_bulk_add_concepts` dedups the repeated `add_concept` calls. HEAD's own replay is lossy
   (bug-186: catalog weight 3.0, replay `None`), so "replay matches HEAD's replay" would pin that
   defect. HEAD's replay digest is RECORDED in the golden, and every key where it differs from
   HEAD's catalog is listed there and attributed to bug-186. {#r3}
4. **R4 Bounded batch size.** A document with more node or concept rows than
   `RMX_GMD_BULK_CHUNK` (default 2,000, read once per call) is written in chunks of that size.
   Chunks are the only place an intra-document yield may fire, and only when no transaction is
   open (today's rule for `_node_tick`). Under `_sync_paths`'s outer transaction there is no
   `yield_lock`, so no yield happens there. {#r4}
5. **R5 No new mechanism.** The writes go through `bulk_upsert_entity`, `_bulk_add_concepts`,
   `bulk_link` and one new `Store.bulk_add_evidence(items)`, all on bug-178's
   `backend.bulk_write`. `bulk_add_evidence` is one `INSERT … SELECT FROM {view}` (with the
   per-row `sqlite_sql` for SQLite), ends in `_maybe_commit`, and logs one `evidence` event per
   row in one batched `_names_of` + `_log_events`, the same fields `add_evidence` logs. No
   second Arrow or executemany path is added, and bug-178's executemany guard (its R3) still
   passes. Round 2 adds two more, both on the same helper and of the same shape:
   `Store.bulk_add_pending_refs(items)` and a batched pending-row delete ([[#r8]]). {#r5}
6. **R6 bug-186 is fixed here: facts.log replay keeps link weights.** In scope because it is
   the same calls (`bulk_link`) and [[#r3]] (c) cannot hold without it. Two halves:
   - (a) `Store.bulk_link(…, update_weight=True)` also logs a `link` event, with its weight,
     for every row whose bit was ALREADY set and whose incoming weight is not `None` (it changed
     or re-asserted the stored weight). Same batch, same `_names_of` call. First-wins mode is
     unchanged (it writes no weight to an existing bit, so it logs none).
   - (b) `rebuild_index_from_log`'s fold (the `link_state` pass, last-event-wins by `ts`,
     weight included) applies the catalog's conflict rule: a later `link` event with weight
     `None` for a key whose previous state is a `link` keeps the previous weight. `unlink` still
     resets. Last-event-wins stays the rule for everything else. The per-event replay
     (`_apply_event_body`) already calls `link()`, which keeps a stored weight on `None`, so it
     is unchanged; AC-8 runs both replays.
   {#r6}
7. **R7 Per-document entry points (decided here, for 23.3).** This task cuts the seam 23.3 R1
   needs ([[task-23.3-sync-between-file-yield#r1]]), because it rewrites both loops anyway and
   AC-2's golden pins the cut:
   - `gmd_prepare(paths, …) -> GmdBatch`: parse, hash, and the name table (`eid_by_name`,
     `doc_level_eid`, `file_hashes`, `stats`), no writes;
   - `gmd_pass1_document(store, batch, doc)`: the doc-level row(s) + R1's bulk node rows;
   - `gmd_pass2_document(store, batch, doc)`: R2 steps 0-8 for one document;
   - **`gmd_finish(store, batch)`** (round 2, L3/L31). This is bug-216's batch-level tail, which
     runs after every document's pass 2, as at post-bug-216 HEAD:
     - pending-ref resolution for every name the batch registers ([[#r8]] (b)). The names come
       from documents skipped as unchanged as well, so they are collected in `gmd_prepare`;
     - then `denotes` maintenance for the ids the batch wrote and the concept names it minted
       ([[#r8]] (c)).

     `GmdBatch` carries both name sets. Pass 2 adds the concept names it mints to the
     `denotes` set, in memory, as bug-216's loop does. The tail is batch-level and not
     per-document, because a per-document tail would miss the names of skipped documents. It
     would also change the order of resolution against HEAD, which [[#r3]] (a) pins.

   `ingest_gmd_paths` becomes `gmd_prepare` + every `gmd_pass1_document` + every
   `gmd_pass2_document` + `gmd_finish` + `stamp_derive("gmd")`, with its resume gate and yields
   where they are today. 23.3 wraps each entry point in its own `bounded_steps` step and adds
   nothing inside them. A stop between the last pass-2 step and `gmd_finish` is
   [[#open-finish-stop]]. {#r7}
8. **R8 bug-216's GMD writes are bulk too (round 2, L3).** These are the writes bug-216 adds to
   this path ([[task-bug216-rule-docs-in-graph#r10]], [[task-bug216-rule-docs-in-graph#r7-denotes]]).
   They join R1/R2's rule: per document, or per `gmd_finish`, a constant number of statements
   that does not grow with the rows written. Semantics are bug-216's; only the write shape
   changes.
   - (a) **Pending rows, recorded.** Each unresolved `rel:` line's pending row (and its root
     mirror's row, on `{#root}`) is collected in walk order. Each document writes them with ONE
     batched insert (`Store.bulk_add_pending_refs`, on `backend.bulk_write` like
     `bulk_add_evidence`). The insert is deduplicated in Python on
     `(source, verb, target_name, file, line)`, keeping the first: that is `add_pending_ref`'s
     duplicate rule. No row of this file pre-exists after R2 step 0's clear. `pending_recorded`
     counts what bug-216 counts, the source-row inserts and not the mirror rows.
   - (b) **Pending rows, resolved** (in `gmd_finish`). Steps, in order:
     - ONE read of the batch's pending rows, as `pending_refs_for`;
     - ONE batched existence read of their sources;
     - their targets through R2 step 2's batched read, in the same precedence;
     - ONE `bulk_link(update_weight=True)` for the resolved edges, then ONE `bulk_add_evidence`;
     - ONE batched delete of the resolved rows and of the rows whose source is gone.

     bug-216's rules stay: a resolved target equal to its source is deleted and not linked, and
     a row whose target still misses stays pending. `pending_resolved`, `pending_dropped` and
     `rels` count as at HEAD.
   - (c) **`denotes`.** `Store.link_denotes(names)` keeps its batched reads, which are chunked
     IN-lists. It writes its new pairs with ONE `bulk_link` and not its per-pair `link()`
     loop. `denotes_added` is unchanged. The one-time derive op (`OPS["denotes_link"]`,
     `names=None`) runs the same method, so it gets the same write.
   - (d) Chunked reads (`link_denotes`' 450-name chunks, R4's `RMX_GMD_BULK_CHUNK`) count as
     batched. Their statements grow with names divided by the chunk size, not with rows.
     AC-3's fixtures stay inside one chunk.
   {#r8}

## How it composes with 26.2's one-transaction legacy-row refresh {#compose-26-2}

[[task-26.2-bridge-move-safety]] (n1 in its round-6 notes) wraps the `as_memory` id row's
`add_memory` and the moved file's legacy-row refresh in ONE `store.transaction()`, and it
switches `add_memory`'s unconditional `con.commit()` to `_maybe_commit`. This task:
- does not touch that scope. The doc-level write stays a constant per-document write, outside
  R1's node batch;
- runs its bulk writes AFTER the doc-level transaction closes, or inside an enclosing outer
  transaction when there is one (`_sync_paths`' `with s.transaction()`). It never opens a
  transaction that crosses 26.2's scope;
- relies on `bulk_upsert_entity` / `bulk_link` / `bulk_add_evidence` committing through
  `_maybe_commit` (verified on the bug-178 branch at `e6da8c3`: `bulk_upsert_entity` calls
  `self._maybe_commit(con)`), and switches the two remaining unconditional commits on this path,
  `ingest_gmd._write_content_hash` (`ingest_gmd.py:~87`) and `Store.stamp_derive`
  (`store.py:~6552`), to `_maybe_commit`.

**Premise corrected (r1 s2):** an unconditional `con.commit()` ends an enclosing transaction on
**SQLite only**. `DuckDBConnection.commit()` is a no-op (`backend.py:584`), so on DuckDB the
early-commit defect cannot occur through `con.commit()`; HEAD already passes a DuckDB rollback
test and fails the SQLite one (6 rows survive, [[bsd-bug185-spec-r1-da67220#p-ac6]]). The same
holds for 26.2 n1's `add_memory` premise; [[#rev-round-1]] records the note for 26.2. AC-6
tests each backend the way that can fail on it.

The two edits are disjoint in `ingest_gmd.py`. 26.2 changes the resume gate, the duplicate-id
stats, the move refresh and the report line. This task changes the pass-1 node loop, pass 2's
wikilink and rel blocks, and cuts R7's entry points around them. Because this task lands
second, it is written against 26.2's merged code, and its line references are re-stamped at
RED.

## Acceptance criteria {#acceptance}

All tests run on a throwaway store under a short `mkdtemp()` root, except AC-4's clone run. No
live store is opened. Logs go to `workflow/review-output/pytest-bug185.log`.

**Two calling contexts** are named wherever a criterion says "both contexts":
- **sync**: inside `with s.transaction(), s.deferred_links():`, as `_sync_paths` calls it
  (`sync.py:191`); per-row `link()` is buffered and flushed first-wins at scope exit;
- **direct**: no transaction, as `_op_ingest_gmd`, the CLI fallbacks and `ingest.py:1203` call
  it; per-row `link()` writes immediately.

1. **AC-1 (RED at HEAD): no per-row writes.** Re-ingest an IMPRESSIONS-shaped GMD fixture with
   ≥ 200 anchors, ≥ 200 resolvable wikilinks and a fixed 10 `rel:` lines (2 on `{#root}`). The
   fixture is generated deterministically and committed under `tests/fixtures/`, never a copy of
   the live ledger.
   - Pass-through spies count `Store.upsert_entity`, `Store.add_concept`, `Store.get_entity`,
     `Store.link` and `Store.add_evidence` calls made from `ingest_gmd_paths`.
   - Calls that scale with the document are ZERO. The per-document constant (doc row, slash
     alias, memory sidecar) is ≤ 3 calls per document and is the same at 50 and at 200 anchors.
   - **Round 2 (bug-216's writes).** Three of the 10 `rel:` lines are unresolved at the first
     ingest. A second batch ingests their targets. The spies also count
     `Store.add_pending_ref`, `Store.delete_pending_ref`, `Store.entity_exists`, and `Store.link`
     calls made from `resolve_pending_refs` / `link_denotes`. Those that scale are ZERO, in both
     batches. bug-216's two per-document clears ([[#r2]] step 0) are constant and are not
     counted.
   - At HEAD this fails: the spies see hundreds of calls.
   - Mutations, each FAILS: restoring the pass-1 per-node `upsert_entity` loop; restoring the
     per-rel `link` + `add_evidence` pair; (round 2) restoring the per-row `add_pending_ref`;
     restoring `link_denotes`' per-pair `link()`.
   {#ac-1}
2. **AC-2 (equivalence, golden from HEAD, both contexts).**
   - **Fixtures:** the AC-1 fixture; a 50-anchor fixture with the same 10 rels; an `as_memory`
     fixture; and a shapes fixture holding:
     - intra-document duplicate anchors; an ADR slash alias; cross-document targets already in
       the store (the batched read's `concept` → `doc` → `memory` precedence); unresolved
       targets;
     - a bare `[[t]]` and a `rel: … -> [[t]]` whose `t` is one of the document's own body terms
       or title tokens (resolves only through step 1's unconditional concept);
     - `[[#x-y]]` followed later in the document by a bare `[[x-y]]` and a
       `rel: depends-on -> [[x-y]]` (intra-document minting, canonical and variant);
     - a node linking an anchor named like its own title token or body term (the collision:
       the anchor description must win, the tf weight must stay);
     - a `rel:` with an authority weight ≠ 1.0, on `{#root}` (root mirror).
   - **bug-216 shapes fixture (round 2, L3)**, ingested on a store that already holds these
     targets:
     - a doc `b-doc` AND a same-named path-less concept `b-doc`. A bare
       `rel: derives-from -> [[b-doc]]` and a plain `[[b-doc]]` bind the doc (R6);
     - an anchored `[[b-doc#sec]]`, which binds the `sec` node (concept-first);
     - a memory target ingested `--as-memory`, which binds the memory;
     - `[[#x-y]]` followed by a bare `rel: depends-on -> [[x-y]]`, in two variants: with a doc
       `x-y` in the store (the doc wins, L3), and without one (the minted concept wins, as in
       round 1);
     - an unresolved `rel:` target, which becomes a pending row. A second batch ingests the
       target, and the row resolves to its edge and evidence;
     - a document whose title spells another doc's id, which gets a `denotes` link (bug-216
       `#rev-3-contracts`).
   - **v1 → v2 fixture:** a document ingested at v1, then re-ingested at v2 with one anchor and
     one wikilink removed, through BOTH paths: sync (`purge_path` first: the old node rows and
     their links are gone) and the job path (`ingest_gmd_paths` alone: the stale node rows
     persist at HEAD and must persist after).
   - **Dump rules (fixed here, not delegated):** rows are keyed by `(kind, name)`; every id
     column is mapped to its entity's `(kind, name)` or linkage name and raw ids are never
     compared (HEAD's repeated `add_concept` consumes sequence values the bulk call does not);
     `created_at`, `updated_at` and `ts` columns are excluded; dirty fragments are flushed
     before the dump; `bitmap_fragments` are compared as the decoded set of
     `(linkage, concept name, entity name)`; `linkage_evidence` as a multiset; (round 2)
     `pending_refs` as a multiset keyed by source `(kind, name)`, verb, `target_name`, `ref`,
     `file`, `line`, `weight`, `detail`, with `created_at` excluded.
   - **Golden:** the hash of the dump plus `IngestStats.as_dict()`, per fixture and per
     context, recorded at HEAD on the RED commit (`tests/fixtures/bug185_head_golden.json`,
     recording the HEAD sha, in the shape of bug-178's `bug178_head_golden.json`). The new code
     must match it in BOTH contexts ([[#r3]] (a)). **Round 2 (L3): HEAD is a `master` that
     contains bug-216's merge.** The RED commit records `git merge-base --is-ancestor
     <bug-216 merge sha> HEAD` and its exit 0. A golden recorded on an earlier tree pins the
     concept-first misbinding, and it is regenerated, never adapted.
   - **facts.log checks** ([[#r3]] (b), (c)), both contexts: every `entity_links` row has a
     `link` event naming it; each entity event precedes any link event naming that entity; a
     fresh-store rebuild from the new code's facts.log reproduces the new code's dump. The
     golden also records HEAD's replay digest and the keys where it differs from HEAD's catalog
     (each attributed to bug-186); the new code is not compared with it.
   - **Mutations, each FAILS:** the anchor mentions written with weight `0.0` instead of
     `None` (or with `weight = excluded.weight` as the conflict rule) — fails on the collision
     fixture; the anchor specs folded into step 1's `concept_specs` call — fails on the
     description; the batched read moved ahead of step 1 — fails on the body-term target; the
     intra-document minting emulation removed — fails on `[[x-y]]`; the mention `bulk_link`
     moved before `link_batch` — fails on replay fidelity in the direct context. Round 2: the
     batched read in concept-first order for bare targets — fails on `b-doc`; the minted-concept
     rule applied even when a same-named doc exists — fails on the `x-y`-with-doc variant;
     `gmd_finish` skipped — fails on the pending row and the `denotes` link.
   {#ac-2}
3. **AC-3 (statements per hold are flat).** Run inside one `with s.transaction()` (one hold),
   with a pass-through spy on the DuckDB wrapper's `execute` and on `executemany` /
   `bulk_write`. Re-ingesting the 50-anchor and the 200-anchor fixtures, which carry the SAME 10
   rels, executes the same number of statements, ± 2. At HEAD the counts differ by hundreds.
   Mutation: restoring the per-ref `add_concept` + `link` FAILS (the counts diverge). 23.3 AC-4b
   later asserts the same thing per `bounded_steps` step under 23.2's recorder, on fixtures with
   the same equal-rel-count rule ([[task-23.3-sync-between-file-yield#ac-4b]]).
   **Round 2 (bug-216's writes).** Both fixtures carry the same 3 unresolved `rel:` lines, so
   they record the same pending rows. A separate `gmd_finish` case is also run: a batch whose
   pending set resolves 50 rows and one that resolves 200 rows, each inside one hold, with the
   same number of new `denotes` names. Both execute the same number of statements, ± 2. Every
   fixture stays inside one read chunk ([[#r8]] (d)). Mutation: per-row pending resolution
   (`link` + `add_evidence` + `delete_pending_ref` per row) FAILS. {#ac-3}
4. **AC-4 (timing; pre-registered bar, measured before GREEN is accepted).**
   - **File (pinned):** `IMPRESSIONS.md` at `4965b12`
     (`git show 4965b12:workflow/bullshit/IMPRESSIONS.md`, 41,679 bytes, 220 node rows, 0 rels),
     never the live file.
   - **Store (gating):** an APFS clone (`cp -c`) of the live `catalog.read.duckdb` in the
     scratchpad, deleted afterwards, imports warmed by one non-GMD sync. The same runs on the
     AC-1 fixture store are recorded beside it as a ratio; they do not gate.
   - **Each run is a real re-ingest:** before every run the pinned file's `tracked_files` row is
     deleted and the run is `sync_files` on it (the r1 probe's method: `purge_path`, then a full
     `ingest_gmd_paths`), or each run gets a fresh clone. Each run asserts its
     `IngestStats.nodes` is 220, not a resume-gate skip.
   - **Quantity (gating):** the wall time of the `ingest_gmd_paths` call, timed by a
     pass-through wrapper. `sync_files`' wall time is recorded beside it.
   - **Baseline:** HEAD's median of 5 runs, measured the same way on the same clone, unprofiled.
     Reference values from r1 (median of 3): **36.40 s** `ingest_gmd_paths`, **37.81 s**
     `sync_files` ([[bsd-bug185-spec-r1-da67220#p-baseline]]). Both are recorded; the gate uses
     the former.
   - **Pre-registered bar: new median ≤ HEAD median / 10** (≈ 3.64 s against the reference).
   - Bands, written now:
     - ≥ 10×: GO;
     - 5-10×: GO only if the profile names the remaining per-row cost and a follow-up row is
       logged;
     - < 5×: STOP and report to the user. The bar is not lowered
       ([[feedback_go_no_go_ranges_not_predrop]]).
   - The implementation summary records the 5+5 runs, both medians, the ratio and a per-call
     profile of one new run.
   {#ac-4}
5. **AC-5 (SQLite and the existing GMD tests).** The AC-1/AC-2 fixtures ingest on the SQLite
   backend, and these existing tests stay green: `test_ingest_gmd_root_rel_mirror.py`,
   `test_gmd_body_anchors.py`, `test_sync_gmd_routing.py`, `test_memory_bridge.py`,
   `test_memory.py`, `test_bulk_link_weighted.py`, `test_coref.py`,
   `test_ingest_concurrency.py`, `test_ingest_partition_yield_race.py`, `test_derive_stamp.py`,
   `test_bug111_repair_dead_concept_links.py` (29 test files reference `ingest_gmd`; AC-7's full
   suite covers the rest), and bug-179's parity test if it has merged. {#ac-5}
6. **AC-6 (no early commit, per backend).**
   - **SQLite (RED at HEAD):** run `ingest_gmd_paths` inside an outer `store.transaction()`
     that is rolled back on purpose after the call returns, with and without `deferred_links`.
     The store must hold none of the call's rows. At HEAD 6 rows survive
     ([[bsd-bug185-spec-r1-da67220#p-ac6]]). Mutations (SQLite), each FAILS: `_write_content_hash`
     back to `con.commit()`; `stamp_derive` back to `con.commit()`.
   - **DuckDB (spy):** the same call inside an outer transaction, with a pass-through spy on
     the connection wrapper's `commit` and on every `execute` / `bulk_write`: `commit` is never
     called during the call, and `Store._in_transaction` is True at every write the call makes.
     Mutation: an unconditional `con.commit()` in any bulk write or in `_write_content_hash`
     FAILS (the spy sees the call).
   {#ac-6}
7. **AC-7 (full suite).** No new failures compared with the pre-change `master` sha, compared by
   error text ([[feedback_compare_failures_by_error_not_name]]). {#ac-7}
8. **AC-8 (bug-186: replay keeps link weights; RED at HEAD).**
   - The r1 probe shape, direct context: node `findings` with body
     `Findings findings here. See [[#findings]]`. Catalog `mentions findings → d1#findings` weight 3.0; a fresh-store replay
     of the call's facts.log gives 3.0 (HEAD: `None`), through both `rebuild_index_from_log` and
     the per-event replay.
   - `bulk_link` unit: a bit set with weight `None`, then `bulk_link([(…, 2.5)],
     update_weight=True)` → facts.log gains one event with 2.5; replay gives 2.5. First-wins
     mode on the same bit logs nothing.
   - Fold unit: `link(…, weight=2.0)` then `link(…, weight=None)` → catalog 2.0, replay 2.0;
     `link(2.0)`, `unlink`, `link(None)` → replay `None`, as the catalog.
   - Mutations, each FAILS: drop R6 (a)'s existing-bit logging; revert R6 (b)'s fold rule.
   - **The per-event half is its own test function** (round 2, L31). In
     `tests/test_bug186_replay_link_weight.py`, `test_ac8_per_event_replay_keeps_weight` holds
     every `_apply_event_body` call; no other test function calls it. Task 16.6 R1f deletes
     `_apply_event_body` (d9bu: the rebuild is the one replay path), and it deletes that
     function with it ([[task-16.6-learned-row-validation#rev-round-15]]). The
     `rebuild_index_from_log` half stays and guards R6 (b) through 16.6's row-pass rewrite.
   {#ac-8}
9. **AC-9 (per-document entry points).** For a two-document fixture whose documents link each
   other (both new), calling `gmd_prepare`, then `gmd_pass1_document` for each document, then
   `gmd_pass2_document` for each, each call in its own `store.transaction()` (23.3's step
   shape), gives the same AC-2 dump as one `ingest_gmd_paths` call, and both links resolve.
   Round 2: the sequence ends with `gmd_finish` in its own transaction. The fixture also
   carries one pending row that its second document resolves, and one `denotes` name, and both
   land as in the single call. Mutations, each FAILS: building `eid_by_name` per document
   instead of once in `gmd_prepare` (the forward link goes unresolved); dropping `gmd_finish`
   from the sequence (the pending row stays and no `denotes` link is written). {#ac-9}
10. **AC-10 (R8 units, round 2).**
    - `bulk_add_pending_refs` on rows with one duplicate key writes the first row only, and
      returns the count `add_pending_ref` would have returned True for.
    - `link_denotes` on 3 names with 5 new pairs makes one `bulk_link` call, and a second run
      adds 0 (idempotent).
    - Pending resolution with one row whose source is purged deletes it and counts it
      `pending_dropped`, and does not link it.

    Mutation: dedupe keeping the last row FAILS on `detail`. {#ac-10}

## Merge order {#merge-order}

Round 2 (L1, L3, L4; plan review `#queue` item 5): 3.7 → bug-178 → 26.1 + 26.2 (all merged) →
bug-216 (queue item 1, 0.83.0) → **this task** (with its revision L3 applied) → 23.2 → 23.1
(bug-177) → 23.3 ∥ 23.5. 23.5's R9/AC-9 waits for the 26.6 R3 residual, after 26.7 (L1). This
task does not need the 23.x harness or recorder, so it ships as a standalone bug release. It is
the largest single cut in live hold time ([[bsd-plan23-3-5-freshness-62a2465#order]]). 23.3's
per-document `bounded_steps` steps wrap R7's entry points, `gmd_finish` included, and its
AC-4b builds on them. Round 1's order ("3.7 → bug-178 → plan-26 → this task") is superseded.

rel: depends-on -> [[plan-review-2026-11-13#queue]]

## Files to modify {#files}

- `src/refmatrix/ingest_gmd.py`: the pass-1 node loop, pass 2's rel and wikilink blocks (R2's
  order), the batched target lookup that replaces `_resolve_target_eid`'s per-target reads,
  R7's entry points (round 2: with `gmd_finish`), and `_write_content_hash`'s `con.commit()` →
  `store._maybe_commit(con)`. Round 2: `resolve_pending_refs` on R8 (b)'s batched shape, and
  the walk's pending rows collected for R8 (a).
- `src/refmatrix/store.py`:
  - a batched `(kind, name) → id` read, only if none exists (a single read method);
  - `bulk_add_evidence` on `backend.bulk_write` (R5);
  - `bulk_link`'s weight-update logging (R6 (a));
  - the `rebuild_index_from_log` fold's `None`-weight rule (R6 (b));
  - `stamp_derive`'s `con.commit()` → `_maybe_commit(con)`;
  - (round 2) `bulk_add_pending_refs` and a batched pending-row delete (R8 (a), (b));
    `link_denotes`' per-pair `link()` loop → one `bulk_link` (R8 (c)).
  - (`add_memory`'s switch is 26.2 n1's, already merged per the dependency.)
- New `tests/test_bug185_bulk_gmd_ingest.py` and `tests/test_bug186_replay_link_weight.py`,
  plus `tests/fixtures/bug185_*` (generated fixtures and the HEAD golden).
- `workflow/bug_registry.md` (the bug-185 and bug-186 rows), and the implementation summary
  `workflow/implementation_summaries/bug-185-bulk-gmd-ingest.md`, which records AC-4's table
  and the RED sha. {#files-list}

## Revision round 1 (2026-11-09) {#rev-round-1}

Source: [[bsd-bug185-spec-r1-da67220]], the pre-implementation review of this spec at `da67220`
(DIRTY 0B/4S/5M). No user decision remained; every fix the report names is adopted. Facts
re-checked at `a16b29e` against master `src/`, the bug-178 clone at `e6da8c3` and the r1 probe
logs (`workflow/review-output/bsd-bug185-r1-probe-*.log`); no store was opened.

| finding | answered at | rationale |
|---|---|---|
| s1 (R3's multiset claim false; AC-2's "replay matches HEAD's" pins HEAD's replay defect; no calling context) | [[#r3]] (catalog dump equality, facts.log names every row, replay fidelity against the NEW code's own catalog), [[#ac-2]] (golden in both contexts; HEAD replay recorded, not compared), [[#r6]], [[#ac-8]]; bug-186 logged | an equivalence gate against a defective baseline either bends the test or keeps the bug ([[feedback_never_explain_away_a_failing_guard]]). bug-186 is fixed IN this task: its half (a) is a few lines in `bulk_link`, the call this task routes every link through, and R3 (c) cannot pass without it; half (b) is the same contract in the replay fold. A separate task would leave R3 (c) unprovable here |
| s2 (AC-6 cannot go RED on DuckDB nor GREEN on SQLite) | [[#ac-6]] (SQLite rollback, RED at HEAD; DuckDB spy on `commit` + `_in_transaction`), [[#compose-26-2]] (premise corrected to SQLite only; `_write_content_hash`, `stamp_derive` → `_maybe_commit`), [[#files-list]] | `DuckDBConnection.commit()` is `pass` (`backend.py:584`); only SQLite makes an early commit observable through rollback. Note for 26.2 n1: its `add_memory` premise is SQLite-only too; the switch stays right, the stated harm is backend-specific |
| s3 (AC-4 times the skip path; no quantity, store or pinned file) | [[#ac-4]] | real re-ingest per run asserted by `nodes == 220`; gate on `ingest_gmd_paths` on the clone; file pinned at `4965b12`; baseline HEAD median of 5 the same way; references 36.40 s / 37.81 s recorded; bar = baseline / 10 |
| s4 (R2 order and description rule open; golden lacks the shapes) | [[#r2]] (steps 1-8: resolve after the unconditional write, HEAD walk order, intra-doc minting emulated, rel targets + slash fallback in the batched read, anchor concepts a separate later call, mentions after `link_batch`), [[#ac-2]] (shapes fixture + three mutations) | the corpus has 2 rel + 7 ref targets that resolve only through a document's own unconditional concepts; the description is last-non-null-wins across calls |
| m1 (rel edges per-row, unstated) | [[#why]] (fourth per-row write), [[#r2]] step 5, [[#r5]] (`bulk_add_evidence`), [[#ac-1]], [[#ac-3]] (same 10 rels in both fixtures) | **decided: bulk.** `backend.bulk_write` takes any `INSERT … SELECT FROM {view}`, so `bulk_add_evidence` is one method on the existing helper, not a new mechanism; per-row rels would leave a hold that scales with rel count on the 23.5-spec-shaped documents (50 rels). Fixtures still carry an equal rel count so AC-3 and 23.3 AC-4b do not depend on the choice |
| m2 (stale facts) | [[#why]], [[#why-fact]], [[#ac-5]] | the job yields after every document (`RMX_INGEST_YIELD_EVERY` default 1); 221 nodes / 220 node rows / 0 rels; 854 = node + variant upserts; the real GMD test set listed |
| m3 (dump rules delegated) | [[#ac-2]] (key by `(kind, name)`, ids mapped to names, timestamps excluded, fragments flushed; v1 → v2 through both paths: sync purges stale nodes, the job path keeps them, preserved) | HEAD's repeated `add_concept` consumes sequence values, so raw ids cannot match |
| m4 (mutations that cannot fail; AC-3 had none) | [[#ac-2]] (code mutations on the collision fixture), [[#ac-3]] (per-ref `add_concept` + `link` restored), [[#ac-6]] | neither `bulk_link` flag overwrites with NULL, so the old wording described no mutation |
| m5 (23.3 composition) | [[#r7]], [[#ac-9]]; [[task-23.3-sync-between-file-yield#ac-4b]] (count and rel-count condition) | **decided: bug-185 provides the per-document pass-1 / pass-2 entry points.** It rewrites both loops anyway and AC-2's golden pins the cut; 23.3 re-cutting freshly merged code would be a second rewrite with no golden. 23.3 AC-4b's "854" quoted the live file; it now says "> 0, scaling with anchors" on equal-rel-count fixtures (23.3 [[task-23.3-sync-between-file-yield#rev-round-7]]) |

rel: derives-from -> [[bsd-bug185-spec-r1-da67220]]
rel: derives-from -> [[bsd-bug185-spec-r1-da67220#s1]]
rel: derives-from -> [[bsd-bug185-spec-r1-da67220#s2]]
rel: derives-from -> [[bsd-bug185-spec-r1-da67220#s3]]
rel: derives-from -> [[bsd-bug185-spec-r1-da67220#s4]]
rel: derives-from -> [[bsd-bug185-spec-r1-da67220#m1]]
rel: derives-from -> [[bsd-bug185-spec-r1-da67220#m2]]
rel: derives-from -> [[bsd-bug185-spec-r1-da67220#m3]]
rel: derives-from -> [[bsd-bug185-spec-r1-da67220#m4]]
rel: derives-from -> [[bsd-bug185-spec-r1-da67220#m5]]

## Revision round 2 (2026-11-13): freshness against bug-216 {#rev-round-2}

Source: [[plan-review-2026-11-13#lead]] L3 (contra-c Cc-1, contra-d CD-4), L4 (Cc-7) and L31
(the composition with 16.6 and 23.3, [[bsd-pop-r2-d99f41c#n7]], [[bsd-pop-r2-d99f41c#n17]]).
The facts were read on dev master `1cf3b9f` and on bug-216's branch
`task-bug216-rule-docs-in-graph` at `f75cbc3` (its GREEN is `2fc5554`), with
`git show`/`git diff` only. No store was opened. The round-1 table above is unchanged history.

rel: derives-from -> [[plan-review-2026-11-13#lead]]
rel: derives-from -> [[bsd-pop-r2-d99f41c#n7]]
rel: derives-from -> [[bsd-pop-r2-d99f41c#n17]]
rel: amends -> [[#rev-round-1]]

### Facts re-read {#rev-round-2-facts}

- **Merges since round 1 that touched `ingest_gmd.py`** (`git log --since=2026-11-08`):
  - 26.3 `3733dab` changes 3 lines in `render_memory_skip_line`;
  - 26.4 `1a1f189` adds the `session/recall-state` mtype override inside the `as_memory`
    sidecar block (a constant per-document write) and the `mtype_normalised` stat;
  - 26.6 `d77dd68` adds `regenerate_memory_index`, which the daemon op and the CLI call AFTER
    `ingest_gmd_paths` returns.

  None of them touches R1's node loop, R2's rel and wikilink blocks, or R7's cut. The
  `mtype_normalised` stat joins `IngestStats.as_dict()` and so the golden.
- **bug-216's GREEN on this path** (`git diff 758bca1 2fc5554 -- src/refmatrix/ingest_gmd.py`):
  - `_resolve_target_eid` uses R6's precedence and never caches a bare concept hit;
  - `_target_name` and `_resolve_ref` (the ADR slash bridge) are factored out, and both pass-2
    loops call them;
  - each changed document runs `clear_rel_evidence(path)` + `clear_pending_refs_for_file(path)`
    before its unconditional concepts;
  - an unresolved `rel:` target is recorded with `add_pending_ref`, for its source and for its
    root mirror;
  - `batch_names` (doc ids, node names and slash aliases of EVERY document, skipped ones
    included) and `denotes_names` (doc ids, tags, title tokens, minted mention concepts) are
    collected;
  - after the pass-2 loop, `resolve_pending_refs(store, batch_names, …)` runs, then
    `store.link_denotes(denotes_names)`, then `stamp_derive("gmd")`.
- **bug-216's store writes** (`store.py` on the branch): `add_pending_ref` is a SELECT plus an
  INSERT per row; `delete_pending_ref` is one DELETE per row; `link_denotes` reads in
  450-name chunks and writes one `link()` per new pair; `clear_rel_evidence` and
  `clear_pending_refs_for_file` are one count and one DELETE per file. **None of
  `clear_rel_evidence`, `add_pending_ref`, `delete_pending_ref` or `clear_pending_refs_for_file`
  calls `_log_event`.** `rebuild_index_from_log` appends every `evidence` event (master
  `store.py`, pass 3's `evidence_events` loop).

### What changed {#rev-round-2-changes}

| finding | answered at | rationale |
|---|---|---|
| L3 / Cc-1 / CD-4: R2.2 pinned concept-first for every target | [[#r2]] step 2 (R6 precedence; a bare concept hit not cached), [[#ac-2]] (bug-216 shapes; concept-first mutation) | bug-216 wins (newer, user-directed). Read literally, round 1 would rebuild the misbinding and its golden would lock it in |
| L3: "minted earlier" could beat a same-named doc | [[#r2]] step 3 (applies only when no doc or memory of that name exists), [[#ac-2]] (`x-y` with and without a doc) | under R6 a bare target takes `doc` and `memory` first. The emulation must follow that order, or it becomes a second concept-first path |
| L3: `denotes` (R7) and pending refs (R10) join the batched writes | [[#r8]], [[#r5]], [[#ac-1]], [[#ac-3]], [[#ac-10]] | each is a per-row write on the measured holder's path. Left per-row, a document with many unresolved lines, or a first `denotes` pass, scales with rows inside one hold. That is the defect this task exists to remove |
| L3: golden regenerated from post-bug-216 HEAD | [[#ac-2]] (HEAD = a `master` containing bug-216's merge; the ancestry check recorded), header dependency | a golden from the old tree pins the misbinding |
| L3: bug-216 gains an order edge to bug-185 | not here | that edge belongs in [[task-bug216-rule-docs-in-graph]], which is not this spec owner's file. Handed to the lead. This spec carries the reverse `depends-on` |
| L4 / Cc-7: "plan-26 merged" gate over-broad | header (26.1 + 26.2 merged, satisfied), [[#merge-order]] | only 26.1 and 26.2 edit what this task rewrites. 26.3/26.4/26.6 were checked ([[#rev-round-2-facts]]) |
| L31 / N17: 23.3 consumes R7's entry points | [[#r7]] (`gmd_finish`, the fourth entry point), [[#ac-9]]; [[task-23.3-sync-between-file-yield#rev-round-8]] | bug-216's tail runs once per batch after pass 2. If no entry point held it, 23.3's per-step wrapping would either drop it or run it unbounded |
| L31 / N7: 16.6 deletes `_apply_event_body`, which AC-8 replays | [[#ac-8]] (the per-event half isolated in one named test function); [[task-16.6-learned-row-validation#rev-round-15]] | this task lands first (queue item 5, before item 8). 16.6's AC-12 scan would fail on a surviving caller, so the caller is made deletable as one unit |

### Open item: replay fidelity after bug-216 {#open-replay-216}

[[#r3]] (c) cannot hold on the job-path v1 → v2 fixture once bug-216 is merged, for a cause
outside this task ([[#rev-round-2-facts]]):
- bug-216 deletes `rel:` evidence unlogged and re-appends it logged;
- its `pending_refs` rows have no event.

This is not a bug-185 choice, so this revision picks nothing. The options:
1. **(recommended) bug-216 logs what it writes before it merges.** `clear_rel_evidence` writes
   one event per file (or per row), and the rebuild applies it in timestamp order. That is the
   shape 16.6's row pass and plan-22's `evidence_remove` already plan
   ([[task-16.6-learned-row-validation#r1d]]). `pending_refs` is declared outside replay, with
   the reason: it is a residue that a re-ingest of the citer re-records. R3 (c) then excludes
   `pending_refs` by name and keeps everything else. Cost: a new event op. 17.4's `FOLD_OPS`
   and 16.6's row pass must name it.
2. bug-185 R3 (c) excludes `rel:` evidence rows on the job path and `pending_refs`, and the
   divergence is logged as a new bug row owned by bug-216. Cost: R3 (c) stops proving replay
   for exactly the rows this task rewrites.
3. Defer to plan-22's `evidence_remove` (22.2 R3) as the logged delete, and accept the
   divergence until 22.2 lands. Cost: replay double-counts `rel:` evidence for several queue
   items, and every evidence recount (bug-216 R5/R8) reads a replayed store wrong.

### Open item: a stop between the last pass-2 step and `gmd_finish` {#open-finish-stop}

At post-bug-216 HEAD, each document's `gmd_content_hash` is stamped at the end of its pass 2.
The batch tail runs after that. Under 23.3's steps, and in the direct context when a yield
falls there (`RMX_INGEST_YIELD_EVERY`), a stop after the last pass-2 step leaves every
document hash-stamped with no tail. The next sync skips them. Their pending rows stay unresolved
until a later batch names the target, and their `denotes` links wait for the derive op. That
contradicts 23.3 R1's "a stop between steps … the next sync's resume gate re-ingests it". The
options:
1. **(recommended) The hash stamps move into `gmd_finish`**, after the pending resolution and
   `denotes`, as one batched write. A stop anywhere before the end leaves the documents
   unstamped, so they re-ingest. The final catalog is unchanged (R3 (a)'s golden holds). Cost:
   one more batched statement per batch, and R2 step 8 moves.
2. The tail's inputs are persisted (a pending-names marker per batch), and the next ingest
   replays a marker it finds. Cost: a new table and a recovery path.
3. Accept and report it: the gap is counted, and the documented recovery is the derive op plus
   the next batch that names the target. Cost: a silent-until-counted loss on a memory path.
