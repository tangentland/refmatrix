---
gmd: "0.1"
id: agent-brief-bug218-red-notes
title: "bug-218 RED author notes (arch-t56, 2026-11-15): what would trip the RED, from a read of today's code"
tags: [agent-brief, bug-218, red, notes]
metadata:
  node_type: brief
  created: 2026-11-15
---

# bug-218 RED author notes {#root}

From arch-t56's freshness read (branch `spec-t56-fresh` `b2e2451`, held for a ch-bsd
confirm-lite before bug-218's RED; ruling L137). Hand these to the bug-218 RED author with the
spec. Decisions P1-P5 are in [[plan-of-plans#decisions]].

rel: related-to -> [[plan-of-plans#queue]]
rel: related-to -> [[task-bug218-reinforcement-edge-direction]]

## Measured on read-only copies (2026-11-15) {#measured}

All 1,368 `reinforces` / `contradicts` rows on the dev store are in the GMD orientation, 0 in
`memory link`'s; the global store holds 1 (GMD). So O-1 = A holds and R4 likely builds nothing.
The reader, `memory link` (CLI and op), the fixtures and the benches are byte-identical to
`1cf3b9f`. {#measured-body}

## Traps {#traps}

1. R1's "one body" is undefined for linkages other than reinforces / contradicts; P1 decides:
   only those two flip, every linkage gets the evidence row. {#t1}
2. R0b's "no evidence" class also holds GMD rows whose evidence `clear_rel_evidence` removed
   since 0.83.0 (20 on the dev store, as `m#root` + `m` pairs); count them as their own
   sub-class. {#t2}
3. R0b names `scripts/census_on_copy.py`, which is 16.6's and post-mod; use
   [[orchestration#measure]]. {#t3}
4. Every `store.py` / `ingest_gmd.py` line number has moved (`Store.link` ≈ 5110, the `rel:`
   write ≈ 1881, the `RMX_BOOST_REINFORCE` block ≈ 5910-5925, `resolve_concept_ids` ≈ 3567);
   cite by symbol, and after 29.5 the files are split. {#t4}
5. A third GMD write site exists: `ingest_gmd.resolve_pending_refs`, in the ingester's
   orientation; R0a and AC-2 must cover it. {#t5}
6. R7's sibling sweep belongs to 29.3 by then; 29.3's owned-handler list names bug-223's handler,
   so R7 needs a paired test commit removing that entry. {#t6}
7. `Store.memory_link` must join 29.2's writer Protocol and the daemon-writer proxy. {#t7}
8. AC-11's unlink is built by 31.6 (L136, bug-185 R10's rule); the `UNOWNED_REL_PRODUCERS`
   entry bug-218 removes exists from 31.6 on, and its support clause counts a no-file, no-line
   evidence row. {#t8}
9. Removing that entry edits `ingest_gmd.py`, a pass file; P4 keeps the producer list outside the
   pass files so bug-218's release leaves no pass `behind_code`. {#t9}
10. R2b's name leg calls 31.6's `ingest_gmd.resolve_link_target(store, ref, *, project,
    batch=None)` (P5); an ambiguous stem returns candidates and binds nothing, and
    `memory score` must say so. {#t10}

## Design gaps the measurement showed {#gaps}

- 32 of 158 statements in memory files sit under a sub-anchor, so R3's `kind='memory'` filter
  drops them (P2: count through the owning memory). {#g1}
- 9 statements would be counted twice: R2b sums a memory and the concept that `denotes` it, and
  stale evidence-less rows sit on those concepts (P3; the rows are among the 114 edges 31.6's
  store step cleans, L136). {#g2}
