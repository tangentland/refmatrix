---
gmd: "0.1"
id: task-bug185-bulk-gmd-ingest
title: "Task bug-185: ingest_gmd_paths writes nodes, anchor concepts, mention links and rel edges in bulk; a GMD re-ingest's hold stops growing with its anchor count"
tags: [task, bug-185, bug-186, bug-221, gmd, ingest-gmd, writer-lock, performance, facts-log, replay, bug-093, bug-177, bug-178, bug-216]
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
> on the post-bug-216 tree. The gate is narrowed. Lead inputs folded the same day
> ([[#rev-round-2-lead]]):
> - the replay-fidelity gap is resolved by bug-216 R13 ([[#open-replay-216]]), and this
>   task's bulk writes emit R13's events;
> - bug-221 is fixed here: a re-ingest replaces the doc's own `rel:` edges ([[#r10]]);
> - the cost of the per-file evidence clear is measured and bounded here ([[#r9]]).
>
> - the stop before the batch tail is ruled (option 1): the tail runs per document inside
>   `gmd_pass2_document`, before that document's hash stamp, and `gmd_finish` keeps only the
>   residue for skipped documents ([[#open-finish-stop]], resolved; [[#ac-13]]).
>
> No open item remains.
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
> Also fixes: bug-186 (facts.log replay drops link weights), [[#r6]]; bug-221 (a changed `rel:`
> line leaves its old typed edge with no evidence after a re-ingest), [[#r10]] (round 2).
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
rel: implements -> [[bug_registry]] {bug: "bug-221"}

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
      logged by its R13): `clear_rel_evidence(path)` and `clear_pending_refs_for_file(path)`
      run before step 1. Round 2 changes two things. The evidence clear also returns the
      `(verb, source, target)` keys of the rows it removed: these are the edges the OLD text
      stated, which [[#r10]] needs. Its statement shape and its cost bound are [[#r9]]. Both
      clears are constant per document, and each logs its R13 event.
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
   8. **The document's tail** (round 2, lead ruling on [[#open-finish-stop]], option 1). This is
      bug-216's batch tail, cut down to this document:
      - (a) pending-ref resolution ([[#r8]] (b)) for the names THIS document registered in
        pass 1: its doc id, its node names and its ADR slash alias. The rows come from the
        batch's ONE pending read ([[#r8]] (b), r1 M1), filtered in memory. Rows recorded from a
        file that this batch passes through pass 2 are excluded, because that document's own
        R2 step 0 clears them and its walk re-derives them. A row from a document already
        processed in this batch cannot target a batch name, because pass 1 registered every
        batch name before any pass 2. So this rule reproduces HEAD's batch-level counts
        exactly.
      - (b) `link_denotes` ([[#r8]] (c)) for this name set (r1 B1, lead ruling):
        - the document's HEAD contributions: its own id and the names its pass 2 put in
          bug-216's `denotes_names` (tags, title tokens, mention concepts);
        - PLUS every doc or memory id of the batch, skipped documents included (`GmdBatch`
          holds them all after pass 1), one of whose `_concept_variants` spellings equals a
          concept name THIS document's pass 2 wrote. That covers step 1's specs (tags, title
          tokens, aliases, body terms), step 4's anchor specs, the mention names, and each
          one's variants.

        The intersection is computed in Python and adds no statement. Without it, a concept
        that a body term or alias mints, or a variant spelling such as `d1 id` for `d1-id`,
        would miss the link that HEAD's single batch-end call writes. The common case is a
        memory `m_one` followed in the same bridge batch by a memory whose body says `m_one`.
   9. **The `gmd_content_hash` stamp**, LAST, after the tail (r1 S1). When a transaction is open
      (23.3's step, or `_sync_paths`' outer one), the stamp and the tail are in it, and a stop
      rolls both back. When none is open (the job path), each write commits on its own, and
      the stamp's position AFTER the tail is what keeps a stopped document unstamped
      ([[#ac-13]]). Either way the stamp sits in the last step that owes the document work
      (23.3 R4's rule). A stop before it leaves the document unstamped, so the next run
      re-processes it. A stop after it leaves the document complete.
   {#r2}
3. **R3 Semantics unchanged: the equivalence contract.** The same input, in the same calling
   context, produces, compared with HEAD:
   - (a) **the same catalog**: the canonical dump ([[#ac-2]]) of `entities`, `entity_links`,
     `linkage_evidence`, `bitmap_fragments`, `memory_content` and (round 2) bug-216's
     `pending_refs`, keyed by name. Also the same `IngestStats` (round 2: its `as_dict()` carries
     bug-216's `pending_recorded`, `pending_resolved`, `pending_dropped` and `denotes_added`;
     the new `rel_unlink_skipped_unowned` ([[#r10]]) is 0 on every golden fixture, and HEAD's
     golden has no such key, so the comparison takes an absent key as 0),
     the same `gmd_content_hash` stamps once the call returns. Resume behaviour: a hash is
     written only after that document's pass 2 INCLUDING its tail (R2 steps 8-9; round 2, lead
     ruling, [[#open-finish-stop]]), so a stamped document is always complete
     ([[#ac-13]]);
   - (b) **a facts.log that names every row**: every `entity_links` row the call leaves has at
     least one `link` event naming it, and every entity event precedes any link event that names
     that entity;
   - (c) **replay fidelity**: rebuilding a fresh store from the NEW code's facts.log reproduces
     the NEW code's own catalog dump (minus the excluded columns), `pending_refs` included.
     **Round 2:** this holds on the post-bug-216 tree because bug-216 R13 logs its per-file
     `rel:`-evidence clear and its pending-ref add / delete / per-file-clear writes as facts.log
     events, and `rebuild_index_from_log` applies them (the one replay path, d9bu; R13 as
     amended by the lead's 2026-11-13 ruling)
     ([[task-bug216-rule-docs-in-graph]] R13, `#r13` on its branch until it merges; [[#open-replay-216]]). This task's batched forms
     of those writes emit the SAME events ([[#r8]] (e)). [[#r10]]'s unlinks are ordinary
     `unlink` events. The v1 → v2 fixture is where (c) is proven ([[#ac-11]]).

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
     (`_apply_event_body`) has no caller in `src/`. d9bu retired it and 16.6 R1f deletes it, so
     this task adds nothing to it and AC-8 replays through `rebuild_index_from_log` only. That
     changed in round 2, by the lead's d9bu ruling; round 1 ran both replays.
   {#r6}
7. **R7 Per-document entry points (decided here, for 23.3).** This task cuts the seam 23.3 R1
   needs ([[task-23.3-sync-between-file-yield#r1]]), because it rewrites both loops anyway and
   AC-2's golden pins the cut:
   - `gmd_prepare(paths, …) -> GmdBatch`: parse, hash, and the name table (`eid_by_name`,
     `doc_level_eid`, `file_hashes`, `stats`). It does no store I/O, so it runs OFF the lock
     (r1 S4). The resume gate's stored-hash read stays in `gmd_pass1_document`, where HEAD's
     pass 1 does it, so it reads the writer's state. **26.2's walk-wide `--as-memory` gate
     inputs (r2 S1, lead ruling)** are HEAD's pre-loop reads: `mem_rows` (one `_memory_row`
     per document), `walk_eids` and `_SourcePathIndex(store, None)`. They are read ONCE per
     batch, in the FIRST `gmd_pass1_document` call, under its hold, as a constant number of
     statements, and kept in `GmdBatch` for every later `_memory_gate(…, walk_eids=…)` call.
     With `as_memory=False` (23.3's sync path) there are no such reads. `gmd_prepare` stays
     free of store I/O in both cases ([[#ac-9]]);
   - `gmd_pass1_document(store, batch, doc)`: the resume gate (a document whose stored hash
     matches is counted `skipped_unchanged` and writes nothing), then the doc-level row(s) and
     R1's bulk node rows;
   - `gmd_pass2_document(store, batch, doc)`: R2 steps 0-9 for one document, including its
     tail (step 8) and its hash stamp (step 9, last);
   - **`gmd_finish(store, batch)`** (round 2, L3/L31; reduced by the lead's ruling on
     [[#open-finish-stop]], option 1). It holds only the RESIDUE of bug-216's batch tail, for
     documents with no pass 2 in this batch (skipped as unchanged):
     - pending-ref resolution ([[#r8]] (b)) for their doc ids, node names and slash aliases;
     - then `link_denotes` ([[#r8]] (c)) for their doc ids;
     - then `stamp_derive("gmd")`, the last write of `gmd_finish` (r1 S4).

     The first two are idempotent, and `gmd_finish` writes no content hash. A stop before
     `gmd_finish` delays only this residue and the derive stamp; the next batch that carries
     those documents, or the one-time derive op, writes the residue. `gmd_pass1_document`
     records the skipped documents' names in `GmdBatch`.
     **Equivalence with HEAD's single batch tail.** The per-document tails plus `gmd_finish`
     apply the same pending resolutions and the same `denotes` links as post-bug-216 HEAD.
     - Pending: R2 step 8 (a)'s exclusion rule.
     - `denotes`: R2 step 8 (b)'s intersection. HEAD links every concept that spells a batch
       id, minted by any producer in any spelling, because its call runs after every pass 2.
       The intersection hands each batch id to the step of every document that writes a
       spelling of it, and the batch id's own step covers concepts that already existed.

     [[#ac-2]]'s golden and [[#ac-9]] check this. The round-2 text first claimed it without
     the intersection, which was false (r1 B1).

   `ingest_gmd_paths` becomes `gmd_prepare` + every `gmd_pass1_document` + every
   `gmd_pass2_document` for the admitted documents + `gmd_finish` (which ends with
   `stamp_derive("gmd")`), with its yields where they are today. 23.3 wraps each WRITING entry
   point (`gmd_pass1_document`, `gmd_pass2_document`, `gmd_finish`) in its own `bounded_steps`
   step and adds nothing inside them. `gmd_prepare` runs off the lock, before the steps. A stop between any two entry points leaves every processed document
   complete and stamped, and every other document unstamped ([[#ac-13]]). {#r7}
8. **R8 bug-216's GMD writes are bulk too (round 2, L3).** These are the writes bug-216 adds to
   this path ([[task-bug216-rule-docs-in-graph#r10]], [[task-bug216-rule-docs-in-graph#r7-denotes]]).
   They join R1/R2's rule: per document (R2 step 8) and per `gmd_finish` (the residue), a
   constant number of statements
   that does not grow with the rows written. Semantics are bug-216's; only the write shape
   changes.
   - (a) **Pending rows, recorded.** Each unresolved `rel:` line's pending row (and its root
     mirror's row, on `{#root}`) is collected in walk order. Each document writes them with ONE
     batched insert (`Store.bulk_add_pending_refs`, on `backend.bulk_write` like
     `bulk_add_evidence`). The insert is deduplicated in Python on
     `(source, verb, target_name, file, line)`, keeping the first: that is `add_pending_ref`'s
     duplicate rule. No row of this file pre-exists after R2 step 0's clear. `pending_recorded`
     counts what bug-216 counts, the source-row inserts and not the mirror rows.
   - (b) **Pending rows, resolved** (in R2 step 8 (a), per document; and in `gmd_finish`, for
     the residue). Steps, in order:
     - ONE read of the pending table per BATCH (r1 M1), not per document. It runs at the
       batch's first pass-2 step, or in `gmd_finish` when no document is admitted, under the
       lock, and is held in `GmdBatch`. Each document's tail and the residue filter it in
       memory and drop the rows they resolve or drop. A row another writer adds between steps
       cannot target a batch name, because every batch name is registered by then (pass 1
       precedes every pass 2). A source another writer removes between steps is caught by the
       existence read below;
     - ONE batched existence read of their sources;
     - their targets through R2 step 2's batched read, in the same precedence;
     - **ONE `DELETE … RETURNING`** (r2 M4; R9's pattern) of the rows about to be resolved and
       of the rows whose source is gone. Where a backend lacks `RETURNING`, a read and a
       delete on the same predicate under the same hold are used instead;
     - ONE `bulk_link(update_weight=True)`, then ONE `bulk_add_evidence`, for the RETURNED
       resolved rows only. A cached row that another writer already resolved and deleted
       between steps is not returned, so it is neither linked nor given a second evidence row
       (the double count bug-216 R10 removes). `pending_ref_delete` events are logged for the
       returned resolved rows only ([[#r8]] (e)).

     bug-216's rules stay: a resolved target equal to its source is deleted and not linked, and
     a row whose target still misses stays pending. `pending_resolved`, `pending_dropped` and
     `rels` count as at HEAD.
   - (c) **`denotes`.** `Store.link_denotes(names)` keeps its batched reads, which are chunked
     IN-lists. It writes its new pairs with ONE `bulk_link` and not its per-pair `link()`
     loop. `denotes_added` is unchanged. The one-time derive op (`OPS["denotes_link"]`,
     `names=None`) runs the same method, so it gets the same write.
   - (d) Chunked reads (`link_denotes`' 450-name chunks, R4's `RMX_GMD_BULK_CHUNK`) count as
     batched. Their statements grow with names divided by the chunk size, not with rows.
     **The bound counts every name a document hands `link_denotes`** (r1 M2): its id, its
     tags, every node's title tokens, its mention names, and the batch ids R2 step 8 (b)'s
     intersection adds. Anchors alone undercount it. AC-3's and 23.3 AC-4b's fixture
     generators pin each document's distinct name count at ≤ 450, and the tests assert that
     count before they compare statements.
   - (e) **R13's events, from the batched writes (round 2, lead decision).** Every batched
     write above logs exactly the events bug-216 R13 defines for its per-row form, with the
     same fields, by names, partition-qualified, in walk order, through one batched
     `_names_of` + `_log_events` per write:
     - `rel_evidence_clear`: one per file;
     - `pending_ref`: one per row inserted (none for a duplicate the dedupe drops);
     - `pending_ref_delete`: one per row RESOLVED. A row DROPPED because its source is gone
       logs nothing, as bug-216's `delete_pending_ref` logs nothing when it cannot name a gone
       source. The rebuild drops such a row with its source's `tombstone` (r1 S3);
     - `pending_refs_clear`: one per file.

     The R13 event set stays the one bug-216 defines. This task adds no event op of its own
     ([[#r10]]'s unlink uses the existing `unlink` op).
   {#r8}
9. **R9 The per-file evidence clear is one statement pair with a measured bound (round 2;
   bug-216 GREEN flag 7, lead input).** `Store.clear_rel_evidence(file)` scans
   `linkage_evidence` by `file`, and no index covers `file` (`idx_evidence_entity`,
   `idx_evidence_lookup` only, in both DDLs). It runs once per re-processed GMD document,
   inside that document's hold, so its cost grows with the whole store's evidence table.
   - **Shape.** Per document, ONE read of the rows to remove (`linkage_id`, `concept_id`,
     `entity_id`, for [[#r10]] and the R13 event) and ONE delete on the same predicate. It may
     be one `DELETE … RETURNING` where both backends support it. Bug-216's count-then-delete,
     which is two scans plus the delete, is replaced. Constant per document, as R1 requires.
   - **Measured, with a pre-registered band** ([[#ac-4]]; accepted by the lead, 2026-11-13). On AC-4's clone, each run records
     the clear's wall time for the pinned file and the clone's `linkage_evidence` row count:
     - median clear ≤ 50 ms: no schema change; the figures are recorded;
     - median clear > 50 ms: this task adds `CREATE INDEX IF NOT EXISTS idx_evidence_file ON
       linkage_evidence(file)` to BOTH DDLs (`store.py` for SQLite, `duckdb_catalog.py` for
       DuckDB), re-runs AC-4, and the clear's median must then be ≤ 50 ms. The one-time build
       on the clone is timed and recorded, because an existing catalog builds the index at its
       next `init()` under the writer. The release notes announce that build. The index is an
       ART index on DuckDB, like the two `linkage_evidence` indexes that already exist; that
       shape is not new to the live catalog.
     - The bar is not lowered if the index misses it. That case STOPs and is reported
       ([[feedback_go_no_go_ranges_not_predrop]]).
   {#r9}
10. **R10 A re-ingest replaces the doc's own `rel:` edges (bug-221; round 2, lead input).** At
    post-bug-216 HEAD, a re-ingest adds the current `rel:` edges and clears the file's `rel:`
    evidence, but never unlinks an edge the new text no longer states. A changed verb or
    target therefore leaves the old typed edge in `entity_links` with no evidence. The R8
    recount (evidence-joined) never sees it, and replay reproduces it, so replay fidelity
    hides it.
    - **Which edges are the doc's own.** These are the `(verb, source, target)` keys of the
      `rel:` evidence rows the R9 clear removes for this file: the doc's direct lines, its
      root-mirror rows, and the rows its pending refs resolved earlier. They are keyed by
      evidence, never by "every edge whose source is one of this doc's nodes". A `rel:` verb
      can also be a hierarchy or extraction linkage (`part-of`), and those edges are not this
      text's.
    - **Replace, AFTER step 7 (r1 S2).** It runs once the document's whole own write set is in:
      step 5's `rel:` edges, step 6's `link_batch` (the `part-of` hierarchy, `imports`, and
      every other unconditional link) and step 7's mention links. It runs before the tail
      (step 8). An old key is unlinked only when ALL of these hold:
      - the document's own write set (steps 5-7) does not state it. This is what "stated"
        means. So a dropped `rel: part-of -> [[#parent]]` line whose key the hierarchy writes
        again keeps its edge;
      - no `linkage_evidence` row supports it after those writes (another file or another
        producer states the same edge). **This UNLESS clause stays in force under the
        "stated = steps 5-7's write set" rule; the write-set rule does not replace it**
        (bsd-spec-t56 r2 M3, lead). It is the only thing that keeps a `memory_link` edge
        alive: once bug-218 lands, that edge has the same key as a memory's `{#root}` `rel:`
        line ([[#ac-15]]). The unlink is ONE batched write per document,
      `Store.bulk_unlink(items)`. It mirrors `bulk_link`: the bitmap fragments are updated
      in-process, there is one relational delete, and one `unlink` event is logged per bit
      actually cleared through one `_names_of`, as `unlink()` logs. Nothing is unlinked for a
      document whose clear removed no rows.
    - **Both contexts (corrected, r2 S2).** `_sync_one` purges a GMD path only when a `doc` row
      named by its RELPATH exists (`sync.py:216-218` at `1cf3b9f`), and a GMD document's `doc`
      is named by its GMD id. So on the sync path the purge fires only for a document that
      carries a legacy relpath `doc` row. Otherwise sync goes through the same pass-2 steps as
      the job path, R10 does the same real work there, and its unlinks are the same
      ([[#ac-11]]'s sync leg). The round-2 text ("on the sync path `purge_path` has already
      removed … a no-op there") was false.
    - **Every producer of a `rel:`-verb edge writes evidence (lead decision, 2026-11-13;
      [[#rev-round-2-lead]]).** An edge with the same key that another producer wrote WITHOUT
      an evidence row cannot be told apart from a stale `rel:` edge. So the rule is that no
      such producer exists, the same fix bug-218 S3 applies to `memory_link`. There is no
      user stop:
      - **Census, at RED, bounded (r2 S3 (a), lead ruling).** The implementer walks the
        `link` / `bulk_link` / `link_batch` callers in `src/` that are OTHER producers and
        meet BOTH conditions (r3 M3 restores the first):
        - their linkage can be a GMD `rel:` verb: a literal that matches `_REL_RE`
          (`[a-z][a-z0-9-]*`) after `_canonical_verb`, or a caller-supplied (computed)
          linkage, which counts as `"*"`;
        - the edge's CONCEPT side can be a GMD entity: a doc, a memory, or a node (`doc#id`).

        Excluded: this document's WHOLE own write set, pass 1 included (r3 M3). That covers
        pass 1's ADR-alias `store.link("same_as", doc_eid, slash_eid)` (`same_as` can never be
        a `rel:` verb anyway), the doc-level and node rows, and pass 2's steps 5-7 (`rel:`
        edges, the `part-of` hierarchy, `imports`, mentions), which "stated" already protects.
        None of them gets new evidence, so [[#ac-2]]'s golden is untouched. The census covers callers on the
        sync path and the job path alike. Each call site is classified as writes-evidence /
        no-evidence-in-reach / no-evidence-unowned and listed in the implementation summary
        with its path, symbol and sha.
      - **In reach: fixed here.** A no-evidence producer is in reach when its code has no
        other open owning plan or task. Each one gains an evidence write as part of this task
        ([[#ac-14]] (a): a test per producer, plus a mutation).
      - **Unowned: skipped and counted.** A no-evidence producer that another plan or task
        owns (for example `memory_link`, owned by bug-218) gets its own bug row in
        `workflow/bug_registry.md`. It is also entered in
        `ingest_gmd.UNOWNED_REL_PRODUCERS`, a list of signatures:
        `(linkage, concept-side kind, entity-side kind)` plus the owning bug id (r3 M2: the
        sides as `entity_links` stores them, `concept_id` / `entity_id`, not source and target,
        because `memory_link` writes its source memory on the ENTITY side today). `linkage` may
        be `"*"` (r2 S3 (b)) for a producer whose linkage comes from its caller.
        - **The shipped list, pinned to the shape `memory_link` ACTUALLY writes at the merge
          base (lead ruling, 2026-11-13):** exactly one entry,
          `("*", "concept", "memory", "bug-218")`. Verified in the code: the daemon op
          `_op_memory_link` does `cid = d._st().add_concept(concept_name)` and then
          `d._st().link(linkage, cid, m["id"], weight=weight)` (`daemon.py:5433-5434` at
          `1cf3b9f`; `:5483-5484` on bug-216 at `4b4b96e`). The CLI local path in `cli.py`'s
          `memory_link` does the same `s.add_concept(concept)` + `s.link(linkage, cid,
          m["id"], …)`, and `Store` has no `memory_link` method. `add_concept` writes
          `kind="concept"`. So in stored sides (r3 M2, L62) the CONCEPT side is a concept, the
          ENTITY side is the memory, and the linkage is the caller's. The entry describes today's shape, not bug-218's
          future orientation. **bug-218 removes it when it re-orients `memory_link`**; that is
          on bug-218's DoD, forwarded to spec-t56 by the lead.
        - **What this costs (stated; accepted by the lead as a decision row):** until bug-218
          removes the entry, a stale `rel:` key from a concept-kind source (a document's NODE
          entity, `doc#id`, which pass 1 writes as `kind="concept"`) to a memory target, with
          no other evidence, is SKIPPED and counted in `rel_unlink_skipped_unowned`, not
          unlinked. bug-221 is fixed for that class only when the entry comes off. Root-mirror
          keys (doc- or memory-kind source) and node → non-memory keys are unaffected.

        Until that bug is fixed,
        R10 does not unlink an otherwise-stale key whose edge matches a listed signature. It
        counts it in a new `IngestStats.rel_unlink_skipped_unowned`, printed in the report
        whenever it is nonzero ([[#ac-14]] (b)). When the owning fix lands, its row is removed
        from the list.
    - **Out of scope:** stale edges already in live stores from earlier re-ingests. Each one
      has no evidence row, so no key names it. Their census and repair belong with plan-22's
      dangling classes, next to bug-219's census input (plan review L6). This task stops new
      ones.
    {#r10}

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
       `#rev-3-contracts`);
     - **(r1 B1)** an `--as-memory` batch `[m_one, citer]` where `citer`'s BODY says `m_one`
       (a body term, not a title) and no concept `m_one` exists beforehand, run in both
       orders, `[m_one, citer]` and `[citer, m_one]`. `m_one`'s title is pinned to a phrase
       that does not spell `m_one` (r2 M1: the root title defaults to the doc id, whose title
       token would mint `m_one` at `m_one`'s own step and hide the intersection). Plus a
       variant case: a document whose TAG is `d1 id`, against a batch doc `d1-id`, in the order
       `[d1-id, tagger]`. A body term cannot carry a space (`_BODY_TOKEN_RE`), which is why
       the variant uses a tag. In every case the `denotes` links equal the golden, which is
       HEAD's single batch-end call.
   - **v1 → v2 fixture:** a document ingested at v1, then re-ingested at v2 with one anchor and
     one wikilink removed, through BOTH paths: sync and the job path (`ingest_gmd_paths`
     alone). The expectation on each path is HEAD's golden, with no prose claim. r2 S2: sync
     purges only a document with a relpath-named `doc` row, so for this id-named fixture
     both paths keep the stale node rows at HEAD, and must keep them after.
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
     the per-document tail (R2 step 8) skipped — fails on the pending row and the `denotes`
     link; (r1 B1) step 8 (b)'s names reduced to the document's HEAD contributions (the
     intersection dropped) — fails on `[m_one, citer]` and on `d1 id`.
   {#ac-2}
3. **AC-3 (statements per hold are flat).** Run inside one `with s.transaction()` (one hold),
   with a pass-through spy on the DuckDB wrapper's `execute` and on `executemany` /
   `bulk_write`. Re-ingesting the 50-anchor and the 200-anchor fixtures, which carry the SAME 10
   rels, executes the same number of statements, ± 2. At HEAD the counts differ by hundreds.
   Mutation: restoring the per-ref `add_concept` + `link` FAILS (the counts diverge). 23.3 AC-4b
   later asserts the same thing per `bounded_steps` step under 23.2's recorder, on fixtures with
   the same equal-rel-count rule ([[task-23.3-sync-between-file-yield#ac-4b]]).
   **Round 2 (bug-216's writes).** Both fixtures carry the same 3 unresolved `rel:` lines, so
   they record the same pending rows. A separate tail case is also run: one document whose R2
   step 8 resolves 50 pending rows, and one whose step 8 resolves 200, each inside one hold,
   with the same number of new `denotes` names. The same pair is run through `gmd_finish`'s
   residue. The pending table is read once per batch (R8 (b)), so a three-document batch
   executes exactly one pending-table read; the mutation "one read per document" FAILS that
   count. Each fixture document's distinct `link_denotes` name count is asserted ≤ 450 first
   (R8 (d)). Both execute the same number of statements, ± 2. Every
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
   - **Round 2 ([[#r9]]):** each new run also records the evidence clear's wall time and the
     clone's `linkage_evidence` row count. R9's 50 ms band decides the index, and the index
     build time is recorded if the index is added.
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
     of the call's facts.log gives 3.0 (HEAD: `None`), through `rebuild_index_from_log`
     (round 2: the per-event replay leg is dropped, d9bu).
   - `bulk_link` unit: a bit set with weight `None`, then `bulk_link([(…, 2.5)],
     update_weight=True)` → facts.log gains one event with 2.5; replay gives 2.5. First-wins
     mode on the same bit logs nothing.
   - Fold unit: `link(…, weight=2.0)` then `link(…, weight=None)` → catalog 2.0, replay 2.0;
     `link(2.0)`, `unlink`, `link(None)` → replay `None`, as the catalog.
   - Mutations, each FAILS: drop R6 (a)'s existing-bit logging; revert R6 (b)'s fold rule.
   - **No test calls `_apply_event_body` or `apply_log_delta`** (round 2, lead ruling: d9bu
     wins). The `rebuild_index_from_log` tests guard R6 (b) through 16.6's row-pass rewrite
     ([[task-16.6-learned-row-validation#rev-round-15]]), and 16.6 R1f has nothing of this
     task's to delete.
   {#ac-8}
9. **AC-9 (per-document entry points).** For a two-document fixture whose documents link each
   other (both new), calling `gmd_prepare`, then `gmd_pass1_document` for each document, then
   `gmd_pass2_document` for each, each call in its own `store.transaction()` (23.3's step
   shape), gives the same AC-2 dump as one `ingest_gmd_paths` call, and both links resolve.
   Round 2: the sequence ends with `gmd_finish` in its own transaction. The fixture also
   carries a pending row from an earlier batch that its second document resolves (in that
   document's tail), one `denotes` name, and a third, unchanged document whose name a pending
   row targets. That row is created through `Store.add_pending_ref`, the real API, and it
   resolves in `gmd_finish`'s residue. All three land as in the single call. Mutations, each
   FAILS:
   - building `eid_by_name` per document instead of once in `gmd_prepare` (the forward link
     goes unresolved);
   - dropping the per-document tail (the pending row stays and no `denotes` link is written);
   - (r2 S1) the `--as-memory` gate inputs read per `gmd_pass1_document` call instead of once.
     An `--as-memory` three-document batch must execute exactly one `mem_rows` /
     `walk_eids` / `_SourcePathIndex` read set, counted by a pass-through spy, and the
     mutation makes it three;
   - dropping `gmd_finish` (the unchanged document's pending row stays);
   - the tail's pending read without the in-batch-file exclusion (`pending_resolved` exceeds
     the single call's on a fixture whose citer is re-processed later in the same batch).
   {#ac-9}
10. **AC-10 (R8 units, round 2).**
    - `bulk_add_pending_refs` on rows with one duplicate key writes the first row only, and
      returns the count `add_pending_ref` would have returned True for.
    - `link_denotes` on 3 names with 5 new pairs makes one `bulk_link` call, and a second run
      adds 0 (idempotent).
    - Pending resolution with one row whose source is purged deletes it and counts it
      `pending_dropped`, and does not link it. It logs NO `pending_ref_delete` event for that
      row (r1 S3), and a rebuild from the log holds no pending row for it, because the
      source's `tombstone` drops it.

    - **Concurrent resolver (r2 M4).** The batch caches its pending rows. Before a document's
      tail, the test plays the other writer with the real per-row Store calls bug-216's
      per-row resolver made (r3 M1: this task rewrites `resolve_pending_refs` into the
      batched shape, so the per-row version is gone after GREEN): `Store.delete_pending_ref(row)`,
      `Store.link(…)` and `Store.add_evidence(…)` for one cached row. It does this on the same
      store, between two `gmd_pass2_document` calls (AC-9's step shape, no transaction
      spanning them). That is the window another writer has when
      the lock is released between steps. The tail then writes no edge or evidence for that row: one
      evidence row in total, and no `pending_ref_delete` event from this batch for it.

    Mutations, each FAILS: dedupe keeping the last row (on `detail`); a `pending_ref_delete`
    logged for the dropped row (the event check); linking every cached row instead of the
    `RETURNING` set (two evidence rows). {#ac-10}
11. **AC-11 (bug-221 + replay fidelity on v1 → v2; RED at post-bug-216 HEAD; round 2).**
    The fixture mirrors red-216's `tests/test_bug216_replay_fidelity.py` (bug-216 AC-14, read
    on its branch at `f79dab1`):
    - doc `a` v1 has `rel: derives-from -> [[b-doc]]` (existing) and
      `rel: depends-on -> [[c-doc]]` (missing);
    - v2 changes the first line's verb to `related-to`, moves the second line, and adds
      `rel: amends -> [[d-doc]]` (missing);
    - and, in this task, a third v2 change: a `{#root}` line's TARGET changes, which exercises
      the root mirror.

    Throwaway store, `RMX_LOG=1`, direct context (`ingest_gmd_paths` alone, no purge):
    - **After v2, the catalog holds no `derives-from` edge `a → b-doc`** and no edge to the
      old root target. Every `rel:` edge whose source is a node of `a` has at least one
      evidence row. At HEAD this FAILS: the old edges survive with no evidence (bug-221).
    - **Edges R10 must keep (r1 S2), each asserted present after v2:**
      - **Another producer's edge with no evidence row and a key no `rel:` line ever stated:**
        before v2 the fixture calls `Store.link("part-of", a#cite, ext)`, where `ext` is an
        external concept, and writes no evidence. The evidence-keyed replace never sees it.
      - **The hierarchy collision:** v1 carries `rel: part-of -> [[#parent]]` on a child node
        whose heading hierarchy writes the same `part-of` key in step 6. v2 drops the line,
        and the edge stays, because the document's own write set still states it.
    - **A still-supported edge survives.** Another `rel:` line cannot state an edge from
      `a`'s nodes, so the case comes from another producer. v1 also carries
      `rel: depends-on -> [[b-doc]]` on node `cite`. Before v2, the fixture writes one more
      evidence row for that key (`depends-on`, `a#cite`, `b-doc`) under a non-`rel:` detail,
      through `Store.add_evidence`, the real API every producer uses. v2 drops the line, and
      the edge stays because that evidence row still supports it.
    - **Replay fidelity.** A FRESH catalog rebuilt from a byte copy of the log through
      `rebuild_index_from_log` holds the same `linkage_evidence`, `pending_refs` and `rel:`
      `entity_links` rows as the source (by names, as a multiset), [[#r3]] (c). Then `c-doc`
      is ingested, the pending ref binds, and the catalog and the replay agree again.
    - **The sync leg (r2 S2).** The same v1 → v2 runs through the watcher/sync route
      (`_sync_paths` over the changed file, no relpath-named `doc` row). It asserts the SAME
      unlinks as the job path: the same `unlink` events by names, and the same final `rel:`
      edges and evidence. Mutation: R10 skipped when called from `_sync_paths` → FAILS (the
      old `derives-from` edge survives on sync).
    - **Mutations, each FAILS:**
      - drop [[#r10]]'s unlink (the old edge survives);
      - unlink by "source is a node of `a`" instead of by evidence key (the `a#cite → ext`
        edge, which no step re-writes, is removed);
      - "stated" narrowed to the `rel:` lines (step 5) only (the hierarchy collision's edge is
        removed);
      - the unlink moved before step 6 (r2 M2). Step 6 re-writes the bit, so the catalog and
        the replay end equal. The test therefore asserts that facts.log holds NO `unlink`
        event naming the collision key, and this mutation fails on that assertion;
      - skip the "still supported" check (the evidence-backed `a#cite → b-doc` edge goes);
      - `bulk_unlink` without its `unlink` events (replay holds the old edge).

    Replay is through `rebuild_index_from_log` only. There is no per-event leg (d9bu; lead
    ruling, round 2).
    {#ac-11}
12. **AC-12 (R8 (e) events and R9's shape; round 2).**
    - **Only R13's four ops are compared (r1 S3)**: `rel_evidence_clear`, `pending_ref`,
      `pending_ref_delete` and `pending_refs_clear`. For one re-ingest of the AC-11 fixture,
      the batched path's events of those four ops equal, as a multiset and field for field (by
      names, partition-qualified), a golden of the same four ops recorded at post-bug-216
      HEAD. The rest of the log is not compared, because [[#r3]] already says facts.log is not
      a multiset match with HEAD's: `bulk_link` logs only new bits, and R10 adds `unlink`s.
      R13 logs no per-row delete for a dropped row, and neither does this path.
    - A spy on the DuckDB wrapper's `execute` sees R9's clear as ≤ 2 statements per document
      against `linkage_evidence`, and none of them is a `count(*)`.
    - Mutations, each FAILS: `bulk_add_pending_refs` logs no `pending_ref` events; the clear
      goes back to count-then-delete. The dropped-row mutation lives in [[#ac-10]] only, whose
      fixture has a purged source (r2 M3).
    {#ac-12}
13. **AC-13 (a stop leaves processed documents complete and stamped, the rest unstamped;
    round 2, lead ruling on [[#open-finish-stop]], option 1).**
    - **Fixture.**
      - An earlier batch ingests doc `x`, which cites the missing `d1-id`; its line is pending.
      - Then a batch of three documents: `d1` (id `d1-id`), `d2` (title spells `d1-id`, which
        gives a `denotes` link) and `d3`.
    - **Mid-batch stop** (the shape of 23.3's `budget_s` / `cancel` stop):
      - call `gmd_prepare`, every `gmd_pass1_document`, then `gmd_pass2_document` for `d1` and
        `d2` only, each in its own transaction, then stop;
      - `d1` and `d2` are complete and stamped: `x`'s pending row is resolved, with its edge and
        evidence, at `d1`'s tail; the `denotes` link is written at `d2`'s tail; both carry
        their `gmd_content_hash`;
      - `d3` is unstamped.
    - **Re-run.** A following `ingest_gmd_paths` over the same three paths skips `d1` and `d2`
      (`IngestStats.skipped_unchanged == 2`) and processes `d3`. The AC-2 dump then equals one
      uninterrupted call's dump.
    - **Context.** This AC runs in the direct context. At this task's merge, `_sync_paths`
      still wraps the whole call in one outer transaction, so a stop there rolls everything
      back. The per-step stop is 23.3's to test ([[task-23.3-sync-between-file-yield#r1]]).
    - **Stamp-order case (r1 S1): NO enclosing transaction.** This is the job path's own
      shape, where each write commits on its own. Call `gmd_pass2_document` for `d1` outside
      any `store.transaction()`, with a test-side pass-through wrapper that raises once at the
      tail's FIRST write (the pending resolution's `bulk_link`, R2 step 8 (a)). With the
      correct order, `d1` is left UNSTAMPED, and the re-run processes it and resolves `x`'s
      row. Inside a transaction the order cannot be observed, because both writes roll back
      together, so this case runs only without one.
    - **Mutations, each FAILS:**
      - the stamp written before the per-document tail (R2 step 9 ahead of step 8). In the
        stamp-order case `d1` is left stamped with `x`'s row unresolved; the re-run skips `d1`,
        so the row stays pending;
      - the stamps deferred to `gmd_finish` (option 2's shape). After the mid-batch stop `d1`
        and `d2` are unstamped, and the re-run re-processes them (`skipped_unchanged == 0`).
    {#ac-13}
14. **AC-14 (every `rel:`-verb producer writes evidence; the unowned skip; round 2, lead
    decision).**
    - (a) **Per in-reach producer** that [[#r10]]'s census found writing no evidence: run it on
      a throwaway store, and its edge has an evidence row naming its producer. Mutation per
      producer: remove its evidence write → FAILS. If the census finds none, the
      implementation summary says so, and (a) is the census record. It is not a vacuous pass,
      because (b) below and AC-11 still exercise R10.
    - (b) **Unowned skip.** The test adds a signature to `UNOWNED_REL_PRODUCERS` for its own
      run, through the test-side fixture, not a production default. It writes an edge
      matching that signature, with a key that doc `a`'s v1 `rel:` line states and v2 drops.
      After v2 the edge is still linked and `rel_unlink_skipped_unowned == 1`. **A second edge
      (r2 M7)** has the same linkage but a different ENTITY-SIDE kind, so its signature is not
      listed. It sits on its own `rel:` line, which v2 also drops, and it is unlinked.
      Mutations, each FAILS: the signature check removed (the first edge is unlinked); the
      counter not incremented (the count is 0); the signature matched on linkage alone (the
      second edge is kept).
    - (c) **The census is recorded.** The implementation summary's census table lists every
      call site with its class. Each `no-evidence-unowned` site has a bug-row id that exists
      in `workflow/bug_registry.md` and an entry in `UNOWNED_REL_PRODUCERS`. A unit test
      asserts that every entry's bug id has a registry row whose status is not `fixed`, so a
      fixed owner's entry cannot linger.
    {#ac-14}
15. **AC-15 (a `memory_link` edge with its own evidence survives a dropped `rel:` line;
    bsd-spec-t56 r2 M3, lead).**
    - **Fixture.** A memory `m` is ingested `--as-memory`. Its v1 carries `{#root}`
      `rel: reinforces -> [[c]]`, and **`c` is a CONCEPT, not a memory** (r2 S3 (c)). So the root
      mirror writes the key `(reinforces, m, c)`: concept side `m` (memory), entity side `c`
      (concept). In stored sides (r3 M2, L62) its signature is `(reinforces, memory, concept)`. The run uses the SHIPPED `UNOWNED_REL_PRODUCERS`, and the test first asserts
      it equals `[("*", "concept", "memory", "bug-218")]` ([[#r10]]). Leg 1's target `c` is a
      concept, so none of leg 1's keys has a memory on its entity side, and none can match the
      entry. The test also asserts this directly: no leg-1 key's
      `(linkage, concept-side kind, entity-side kind)` matches a listed signature.
    - The same key is then written the way bug-218 S3 specifies for `memory_link`: GMD
      orientation, plus its own `linkage_evidence` row with `memory_link`'s detail. bug-218
      merges after this task (`#queue` item 9 vs 5), so the fixture writes it through
      `Store.link` + `Store.add_evidence`, the real APIs, in bug-218's shape. Switching the
      fixture to the real `memory_link` op is bug-218's, once its S3 lands.
    - **v2 drops the line**, and `m` is re-ingested on the job path.
    - **Expected:** the edge `(reinforces, m, c)` is still linked; its `memory_link` evidence
      row is untouched (R9's clear removes only `rel: `-detail rows);
      `rel_unlink_skipped_unowned == 0`. The survival is the evidence clause's doing, not the
      unowned skip's: `(reinforces, memory, concept)` (concept-side memory, entity-side
      concept) does not match the shipped entry `("*", "concept", "memory")`.
    - **Second leg (lead ruling, adjusted to the entry's shape).** `m`'s v1 also carries, on a
      NON-root node `{#sec}`, `rel: reinforces -> [[m2]]`, where `m2` is a memory. That gives
      the key `(reinforces, m#sec, m2)`: concept side the node `m#sec` (`kind="concept"`),
      entity side the memory `m2`. That is the signature `(reinforces, concept, memory)`,
      `memory_link`'s stored shape. The edge has no evidence row besides its own `rel:` row, which R9
      clears. v2 drops the line. The edge survives through the shipped wildcard entry:
      `rel_unlink_skipped_unowned == 1`. This is the stated partial-bug-221 cost, observed.
    - **Mutations, each FAILS:** drop R10's evidence check (leg 1's edge is unlinked); ship
      the list empty (leg 2's edge is unlinked, count 0).
    {#ac-15}

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
    `link_denotes`' per-pair `link()` loop → one `bulk_link` (R8 (c)); the batched writes'
    R13 events (R8 (e)); `clear_rel_evidence` as one read + one delete that returns the removed
    keys (R9); `bulk_unlink` (R10).
- `src/refmatrix/store.py` (`CATALOG_DDL`) and `src/refmatrix/duckdb_catalog.py`:
  `idx_evidence_file`, ONLY if R9's band calls for it.
  - (`add_memory`'s switch is 26.2 n1's, already merged per the dependency.)
- New `tests/test_bug185_bulk_gmd_ingest.py`, `tests/test_bug186_replay_link_weight.py` and
  (round 2) `tests/test_bug221_rel_replace.py` (AC-11, AC-12, AC-14, AC-15),
  plus `tests/fixtures/bug185_*` (generated fixtures and the HEAD golden).
- `src/refmatrix/ingest_gmd.py` (round 2): `UNOWNED_REL_PRODUCERS` and the R10 skip + counter;
  each in-reach no-evidence producer's file gains its evidence write ([[#ac-14]] (a)).
- `workflow/bug_registry.md` (the bug-185, bug-186 and bug-221 rows, plus one row per unowned
  no-evidence producer the census finds), and the implementation summary
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
| L31 / N7: 16.6 deletes `_apply_event_body`, which AC-8 replayed | [[#ac-8]] (the per-event leg dropped; rebuild only); [[task-16.6-learned-row-validation#rev-round-15]] | this task lands first (queue item 5, before item 8). First drafted as an isolated, deletable test function; replaced by the lead's d9bu ruling ([[#rev-round-2-lead]]): no new caller of a retired path |

### Resolved: replay fidelity after bug-216 (bug-216 R13) {#open-replay-216}

**Resolved by the lead, 2026-11-13: bug-216 gains R13 before it merges**
([[task-bug216-rule-docs-in-graph]] R13 and AC-14, anchors `#r13` / `#ac-14` on its branch, RED at `f79dab1`; the wikilink is doc-level until that branch merges). The per-file evidence clear
and every pending-ref write become facts.log events that `rebuild_index_from_log` applies (R13
as amended by the lead's d9bu ruling: rebuild only). "Pending refs
outside replay" was rejected: it would be a silent knowledge loss on rebuild. So [[#r3]] (c)
holds on the post-bug-216 tree. This task's batched writes emit the same events ([[#r8]] (e)),
and [[#ac-11]] proves (c) on the v1 → v2 fixture. The problem and the options as first written
are kept below as history. The recommended option 1 was adopted, except for its
"outside replay" half. {#open-replay-216-resolved}

rel: depends-on -> [[task-bug216-rule-docs-in-graph]] {req: "R13"}

[[#r3]] (c) could not hold on the job-path v1 → v2 fixture once bug-216 was merged, for a
cause outside this task ([[#rev-round-2-facts]]):
- bug-216 deleted `rel:` evidence unlogged and re-appended it logged;
- its `pending_refs` rows had no event.

The options as first written:
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

### Resolved: a stop between the last pass-2 step and `gmd_finish` {#open-finish-stop}

**Ruled by the lead, 2026-11-13: option 1.** The tail runs per document inside
`gmd_pass2_document`, before that document's hash stamp, and `gmd_finish` keeps only the
residue for skipped documents. Folded into [[#r2]] steps 8-9, [[#r3]] (a), [[#r7]], [[#r8]],
[[#ac-3]], [[#ac-9]] and [[#ac-13]] (mutation: stamp before the per-document tail → FAIL).

The lead's first ruling the same day picked option 2 (stamps in `gmd_finish`). It was folded
in `fd7dc06` and withdrawn after the livelock below was confirmed: under 23.3's `budget_s` a
batch larger than one budget never stamps. Option 1 matches 23.3 R4 (the stamp goes in the last
step that owes the file work). The analysis and the options as last written follow, as
history. {#open-finish-stop-ruling}

**The window.** At post-bug-216 HEAD, `ingest_gmd_paths` stamps each document's
`gmd_content_hash` at the end of that document's pass 2. bug-216's batch tail runs only after
the LAST document's pass 2:
- `resolve_pending_refs(batch_names)` binds pending `rel:` rows whose target this batch
  registered;
- `link_denotes(denotes_names)` links path-less concepts to the doc or memory they name.

A stop after any pass-2 document and before the tail therefore leaves that document
hash-stamped while the tail has not run for its names. The stop can be a crash, a daemon
fast-exit, 23.3's `cancel`, or 23.3's `budget_s`. The next sync's resume gate sees a matching
hash and skips the document. Its target names never reach `resolve_pending_refs` again, unless
a later batch happens to carry that document. Its own and its minted names never reach
`link_denotes` again, unless the one-time derive op is re-run.

**Where it can happen.**
- In the **direct context** (the job path) between documents, because `_op_ingest_gmd` yields
  the lock after every document (`RMX_INGEST_YIELD_EVERY` default 1) and a daemon exit can fall
  in any yield.
- Under **23.3** at every step boundary of the GMD phase. 23.3 R1 promises that "a stop
  between steps leaves a document without its hash, so the next sync's resume gate re-ingests
  it", and 23.3 R4 states the rule that "a file's stamp is written in the same transaction as
  the LAST step that still owes it work". With the tail in a separate `gmd_finish` step, every
  pass-2 step stamps a document that `gmd_finish` still owes work, which breaks R4's rule.

**Options (recommendation first).**

1. **(recommended) The tail runs per document, inside `gmd_pass2_document`, before that
   document's hash stamp. `gmd_finish` keeps only the residue for skipped documents.**
   - **Per document, at the end of pass 2.** First, pending resolution for the names THIS
     document registered in pass 1 (its doc id, its node names, its ADR slash alias). Then
     `link_denotes` for this document's id and the concept names its pass 2 minted (tags,
     title tokens, mention concepts). Last, the hash stamp. All of it goes in the same
     transaction, so the stamp is in the last step that owes the document work (23.3 R4's
     rule).
   - **`gmd_finish`** keeps only the names of documents that had NO pass 2 in this batch
     (skipped as unchanged): pending resolution and `link_denotes` for those names. Both are
     idempotent. A stop before it loses only that residue, and the residue is re-offered by
     the next batch that carries those documents.
   - **Why the final catalog is the same as the batch-level tail's.**
     - Pass 1 registers every document of the batch before any pass 2. So a pending row whose
       target is document D resolves at D's own pass 2 with the same precedence and the same
       `eid_by_name`.
     - `denotes` (corrected after r1 B1): a later document D2's concept that names D is linked
       at D2's step only if D's id is in D2's name set. bug-216's `denotes_names` alone does
       not hold body terms, aliases or variant spellings. So the per-document name set adds
       every batch id that one of D2's written concept names spells ([[#r2]] step 8 (b)), and
       then the link set equals HEAD's. The first text of this bullet ("is in D2's minted set,
       so it is linked") was false; [[#ac-2]]'s `[m_one, citer]` case pins it.
     - R3 (a) compares the catalog dump, not the event order. So AC-2's golden holds, and
       AC-9 shows it for the per-document entry points.
   - **Statement cost.** Per document it adds one `pending_refs_for` read, ≤ 1 batched
     resolution write set ([[#r8]] (b)) and one `link_denotes` (chunked reads, one
     `bulk_link`). That is constant per document, as [[#r1]] requires, and AC-3 covers it.
   - **Resume granularity is unchanged.** Every finished document stays finished, so 23.3's
     budget stops always make progress.
   - **Spec changes if adopted:**
     - [[#r7]]'s `gmd_pass2_document` absorbs the per-document tail before R2 step 8.
     - `gmd_finish` shrinks to the skipped-document residue.
     - [[#ac-9]] gains a stop injected after one document's pass 2. The next call re-offers
       nothing for that document, because its tail already committed with its stamp.
       Mutation: the tail moved back after the stamp FAILS.
     - 23.3 R1's "stop between steps" sentence holds again. Its `gmd_finish` step stays, for
       the residue.
   - **Residual risk:** a stop before `gmd_finish` can still delay the residue, which affects
     only names of unchanged documents. A pending row can target such a document only if its
     target existed when the citer was ingested but went unresolved, for example after an
     ignore-rule change. The derive op and the next batch carrying that document recover it.
     The residue counts are reported (`pending_resolved` / `denotes_added` in the batch's
     report).

2. **The hash stamps move into `gmd_finish`, as one batched write after the tail.**
   - Closes the window completely: a stop anywhere leaves every document of the batch
     unstamped, so all of them re-ingest.
   - **Cost: a stop now throws away the whole batch's progress, not one document's.** Under
     23.3's `budget_s`, a GMD batch larger than one budget never reaches `gmd_finish`, so it
     is re-ingested in full on every sync and never stamps: a livelock. The memory bridge's
     batches (hundreds of files, a yield per document) re-do all of them after any daemon
     exit.
   - R2 step 8 moves, and R3 (a)'s "a hash is written only after pass 2 completes" becomes
     "after `gmd_finish` completes".
   - The final catalog is unchanged.

3. **The tail's inputs are persisted.** A per-batch marker row holds the names the tail still
   owes. It is written in the first pass-2 step, cleared by `gmd_finish`, and replayed by the
   next ingest that finds it.
   - Closes the window and keeps per-document progress.
   - **Cost:** a new table with its own R13-style facts.log events, a recovery path at ingest
     start, and a 16.6 row-pass entry. It is a second mechanism for what option 1 gets by
     placing existing writes.

4. **Accept and report.** The batch tail stays as it is. A stop before it is counted (the
   batch report names the documents whose tail did not run), and recovery is the derive op
   plus the next batch that names each target.
   - **Cost:** knowledge on a memory path stays missing until someone acts on a report. That
     goes against `feedback_no_silent_failures` and `feedback_decay_never_loses_knowledge`'s
     intent, even when the gap is counted.

**This revision picks none.** The draft first recommended option 2. I revised the
recommendation to option 1 after reading 23.3 R4's stamp rule and its `budget_s` stop, under
which option 2 can livelock.

### Lead inputs folded the same day {#rev-round-2-lead}

Three team-lead messages, 2026-11-13, after the first round-2 draft (`f9c2fa7`):

rel: implements -> [[bug_registry]] {bug: "bug-221"}

| input | answered at | rationale |
|---|---|---|
| replay fidelity decided: bug-216 R13 logs the evidence clear and every pending-ref write; pending refs are NOT outside replay | [[#open-replay-216]] (resolved), [[#r3]] (c), [[#r8]] (e), [[#ac-11]], [[#ac-12]] | a batched write that skipped R13's events would reopen the gap R13 closes, on the path this task makes hot |
| bug-216 GREEN flag 7: `clear_rel_evidence` scans `linkage_evidence` by `file` with no index, once per re-processed doc | [[#r9]], [[#ac-4]], [[#ac-12]], [[#files-list]] | the scan grows with the store, not the document, so it is a per-hold cost this task owns. A pre-registered band decides between index and no index; the count-then-delete double scan goes either way |
| bug-221 (owner: this revision): a changed `rel:` line leaves its old edge with no evidence | [[#r10]], [[#ac-11]], [[#files-list]] | replace semantics keyed by the evidence the clear removes, so hierarchy and extraction edges sharing a verb are never touched. Logged as `unlink` events, so replay reproduces the removal. Existing stale edges are a plan-22 census item, not repaired here |

| decision (lead, 2026-11-13) | answered at | rationale |
|---|---|---|
| d9bu wins over bug-216 R13's "both replay paths": rebuild only | [[#r3]] (c), [[#r6]], [[#ac-8]], [[#ac-11]] | `apply_log_delta` has no caller in `src/`; no spec extends a retired path |
| R9's 50 ms band accepted | [[#r9]] | pre-registered before any run |
| `#open-finish-stop` = option 1 (the first ruling, option 2, withdrawn) | [[#open-finish-stop]], [[#r2]] steps 8-9, [[#r7]], [[#ac-13]] | a stamped document is always complete; per-document progress survives every stop; option 2 livelocks under 23.3's `budget_s` |
| r1 S4 wording: `stamp_derive("gmd")` is the LAST WRITE of `gmd_finish`, not a step of its own | [[#r7]]; [[task-23.3-sync-between-file-yield#r1]] (`N + A + 1`) | the ruling text "its own step inside gmd_finish" was contradictory; the writer's reading stands |
| bsd-spec-t56 r2 M3: R10's "UNLESS a `linkage_evidence` row still supports it" clause is kept explicitly under the write-set rule, with its own AC | [[#r10]], [[#ac-15]] | bug-218's `memory_link` edges survive R10 only through that clause; without an AC of its own, a later simplification to "stated = write set" alone would pass every other test |
| r2 S1: 26.2's `--as-memory` gate reads happen once, in the first `gmd_pass1_document`, cached in `GmdBatch`; `gmd_prepare` stays free of store I/O | [[#r7]], [[#ac-9]] | HEAD reads them before its pass-1 loop. Per-document reads would change 26.2's gate, and reads in `gmd_prepare` would break the off-lock contract |
| r2 S2: sync purges only a relpath-named `doc`, so R10 works on sync too | [[#r10]], [[#ac-2]], [[#ac-11]] (sync leg) | the round-2 premise was false; a "no-op" assertion would fail against correct code |
| r2 S3: census = OTHER producers of an edge whose concept side is a GMD entity, the document's own write set excluded; `*` linkage allowed; shipped list = `("*", "concept", "memory", "bug-218")` (see the next row); AC-15 pins `c` a concept, plus a memory-target leg | [[#r10]], [[#ac-14]], [[#ac-15]] | bounds the lead's c8deca7 rule (its wording was too wide); AC-2's golden is untouched |
| r2 M4: pending resolution by `DELETE … RETURNING`, linking only the returned rows | [[#r8]] (b), [[#ac-10]] | the per-batch cache can be stale across a released lock |
| UNOWNED entry pinned to the shape `memory_link` writes at the merge base, `("*", "concept", "memory", "bug-218")`, verified at `1cf3b9f` and `4b4b96e`; bug-218 removes it when it re-orients; the partial-bug-221 cost (a stale node → memory `rel:` key with no other evidence is skipped and counted until then) is accepted | [[#r10]], [[#ac-15]] (second leg on a node → memory key) | the skip list must describe what the unowned producer actually writes, or it either misses that producer's edges or skips edges no producer wrote |
| bsd-spec-t4 r3 (MEH-only, 4M), ruled by the lead as L62 (dev master `8bf3660`, [[plan-review-2026-11-13#lead]]: "T4 meets the approval bar"; `approved` is set on this fold, with no further ch-bsd round): M1 AC-10's other writer uses `Store.delete_pending_ref` + `link` + `add_evidence`; M2 the signature is `(linkage, concept-side kind, entity-side kind)`; M3 the census keeps the `rel:`-verb (or `"*"`) condition and excludes the document's whole write set, pass 1's `same_as` ADR alias included. M4 is the lead's | [[#r10]], [[#ac-10]] | the per-row resolver does not survive GREEN; `memory_link`'s source is on the entity side; without the verb condition the census catches pass 1's alias and breaks AC-2's golden |
| r1 S2 census: no user stop. Every producer of a `rel:`-verb edge writes an evidence row; an in-reach producer is fixed here; an unowned one gets a bug row and is skipped by signature, counted `rel_unlink_skipped_unowned` | [[#r10]], [[#ac-14]], [[#r3]] (a), [[#files-list]] | evidence is the only provenance R10 can read. Making it universal removes the ambiguity, matches bug-218 S3's `memory_link` fix, and the counted skip keeps an unowned edge from being unlinked silently before its owner lands |

**Two further lead rulings, 2026-11-13** (the decision table above records them):
- **d9bu wins** over R13's "both replay paths". `apply_log_delta` has no caller in `src/`.
  bug-216 R13 is amended to apply its events in `rebuild_index_from_log` only. This task
  therefore has NO per-event replay leg: AC-8's, which round 1 had, and AC-11's are dropped,
  and nothing here extends `_apply_event_body`. 16.6 R1f's deletion list is unchanged by this
  task ([[task-16.6-learned-row-validation#rev-round-15]]).
- **[[#r9]]'s pre-registered band** (median clear ≤ 50 ms, else `idx_evidence_file`) is
  accepted as written.

### bsd-spec-t4 r1 folded (2026-11-13) {#rev-round-2-bsd-r1}

Source: the ch-bsd spec review of `spec-wave-t4` at `db701e8` (DIRTY 1B/5S/7M), with the lead's
rulings. Folded from the spec text, not from the writer's report (r1 M7). This task's
findings:

rel: derives-from -> [[plan-review-2026-11-13#lead]]

| finding | answered at | rationale |
|---|---|---|
| B1: the per-document `denotes` tail dropped HEAD's links for body terms, aliases and variant spellings, and the proof said otherwise | [[#r2]] step 8 (b) (name set = HEAD contributions ∪ batch ids spelled by any concept name this document wrote); [[#r7]] equivalence paragraph; [[#open-finish-stop]] option-1 proof corrected; [[#ac-2]] (`[m_one, citer]` both orders, `d1 id`; intersection-dropped mutation) | `link_denotes(names)` takes TARGET ids. HEAD's single call runs after every concept exists, so a per-document call must be handed every batch id this document's concepts spell. A Python intersection costs no statement |
| S1: stamp-before-tail mutations could not fail inside one transaction | [[#r2]] step 9 (transaction-aware wording); [[#ac-13]] (stamp-order case with no enclosing transaction, raise at the tail's first write); 23.3 AC-4b's mutation replaced ([[task-23.3-sync-between-file-yield#rev-round-8-r1]]) | the order is observable only where each write commits on its own |
| S2: R10's position and "stated" were open | [[#r10]] (after step 7; stated = steps 5-7's write set; evidence check; RED census of evidence-less producers of `rel:` verbs); [[#ac-11]] (`a#cite → ext` edge with no evidence, hierarchy collision; mutations) | before step 6 the hierarchy edge is re-written and the mutation survives. Counting only the `rel:` lines as stated drops a `part-of` edge the document still writes |
| S3: R8 (e) and AC-12 did not match R13's event shape | [[#r8]] (e) (no event for a dropped row), [[#ac-10]] (event check), [[#ac-12]] (four ops only, field for field) | R13's `delete_pending_ref` cannot name a gone source; the full log is not a match by construction ([[#r3]]) |
| S4: `gmd_prepare` / `stamp_derive` placement | [[#r7]] (`gmd_prepare` off the lock; resume gate in `gmd_pass1_document`; `stamp_derive("gmd")` last in `gmd_finish`; 23.3 wraps writing entry points only) | fixes 23.3's hold formula, `N + A + 1` ([[task-23.3-sync-between-file-yield#r1]]) |
| M1: a pending-table read per document | [[#r8]] (b) (one read per batch, cached in `GmdBatch`), [[#ac-3]] (exactly one read) | the read scans the whole partition table, so per document it scales with the batch |
| M2: the 450-name premise counted anchors only | [[#r8]] (d), [[#ac-3]] (distinct name count pinned and asserted) | the names include tags, title tokens, mention names and the intersection's ids |

S5 is folded in [[task-16.6-learned-row-validation#rev-round-15]] and
[[task-17.4-factslog-backup-snapshot#rev-round-15]]. M3 is folded in 23.5 / 23.1, M4 in plan-18,
and M5 in 18.3. M6 belongs to the lead: the bug-216 spec edits at merge.

## Approval (2026-11-14, d9co) {#approval-2026-11-14}

| decision | basis | status |
|---|---|---|
| The spec-wave revisions in this file are approved by the lead on the user's pattern (d9co) after ch-bsd bsd-spec-t4 r3 MEH-only (0B/0S/4M) and r4-lite MEH-only (0B/0S/1M, the lead's bug-216 order edge), L62 | `workflow/bullshit/2026-11-14-0045-spec-t4-r3-e591c60.md`, `workflow/bullshit/2026-11-14-0055-spec-t4-r4-lite-ff44120.md` (over `spec-wave-t4` up to `ff44120`; `6a87bfb` finishes M2 wording only) | `metadata.status` stays `approved` |

rel: derives-from -> [[bsd-spec-t4-r4-lite-ff44120]]
