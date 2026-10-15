---
gmd: "0.1"
id: impl-bug-111-repair-dead-links
title: "bug-111: the fragment repair stops restoring dead-concept bits; the as-memory doc drop goes through purge_entity"
tags: [implementation-summary, bug-111, fragments, repair, ingest-gmd, part-of]
metadata:
  node_type: implementation-summary
  status: in-review
  created: 2026-10-14
  updated: 2026-10-14
---

# bug-111: dead `part-of` bit after the bug-105 repair {#root}

rel: implements -> [[bug_registry#registry]]
rel: amends -> [[impl-bug-105-fragment-partition]]

## The defect {#defect}

Six seconds after the bug-105 repair on cliquedb (2026-10-14 19:09:49), a dry run reported one
`part-of` bit, entity 724972 -> concept 2791209, whose concept is in neither `entities` nor
`concepts`. The registry row guessed a writer working from stale state. That guess was wrong.
`rmxd.log` shows no op between the apply and the dry run. The pre-repair backup has the bit in no
fragment but has the `entity_links` row. The 19:09:55 and 19:30:30 dry-run manifests are
byte-identical. **The repair wrote the bit itself.**

`Store.repair_fragments` builds `new` from `entity_links` while checking only that the entity is
alive. Its fragment half also checks the concept. So an orphan `entity_links` row came back as a
bit on every apply, and every later dry run flagged that bit as `dropped_dead_concept`. Nothing
was regrowing: the repair had reached a fixed point that kept reporting the same bit.

The orphan rows themselves come from deletes that bypass `purge_entity`. One live path is
`ingest_gmd_paths(as_memory=True)`, which dropped a prior kind='doc' entity with a raw
`DELETE FROM entities`. That leaves its `entity_links` rows on both sides, its fragment bits and its
vector behind. On cliquedb, 5,298 `entity_links` rows name a dead entity and 8 name a dead concept.
The deleter of ids 2791202-2791209 predates the current code and cannot be named from the data.

## The fix {#fix}

- `repair_fragments`: the links half applies the same concept-liveness gate as the fragment half.
  A dead-concept link is counted in a new `links_dead_concept` and not turned into a bit. The row
  itself is left in place: removing it is an audited removal (plan 22), not a fragment repair.
  The count is printed by `rmx repair-index --fragments`, by the offline merge's repair line, and
  by the daemon's `repair_fragments` log line.
- `ingest_gmd_paths(as_memory=True)`: the doc drop selects the ids and calls `purge_entity` on
  each. A failure is now counted in `IngestStats.doc_drop_failed`, returned by `as_dict()` and
  printed by `report()`. Before, it printed only under `verbose`, a silent failure on a memory
  path.

## Verification {#verification}

- RED at HEAD `ddce097`, all three in `tests/test_bug111_repair_dead_concept_links.py`
  (`workflow/review-output/bug111-red.log`): apply restores the dead bit; a bit already in a
  fragment is dropped and then restored; the as-memory drop leaves 3 orphan rows.
- GREEN: 3 passed (`bug111-green.log`); fragment/repair/gmd/merge/partition family in
  `bug111-family.log`.

## Live follow-up {#live}

After deploy, one applied `rmx repair-index --fragments` on cliquedb drops the bit for good. The
manifest records it, and the next dry run reads `dropped_dead_concept=0` with
`links_dead_concept=1`. The 5,298 + 8 orphan `entity_links` rows stay until an audited removal.
