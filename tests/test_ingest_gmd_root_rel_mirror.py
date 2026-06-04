"""Mirror root-anchor rel: edges onto the doc-level memory entity.

A GMD memory file declares its `rel: <verb> -> [[target]]` edges below
the H1 `{#root}` heading. Without the mirror, those edges land only on
the `<doc>#root` concept (kind=concept), invisible to:
  * `rmx neighbors <memory-name>` (which resolves to the doc-level
    kind=memory entity)
  * `rmx context --degree N` walks starting from the memory anchor
  * the GMD-curator + memory-recall flows that treat memory→memory
    edges as the primary navigation surface

With the mirror, the same edge is ALSO emitted from the doc-level
memory entity to the resolved target, so the memory graph traverses
naturally without requiring degree>=2 BFS.

These tests run against an in-process Store + `ingest_gmd_paths` —
no daemon, no socket.
"""
from __future__ import annotations

import pytest

from refmatrix.store import Store
from refmatrix.ingest_gmd import ingest_gmd_paths


def _seed_store(tmp_path):
    s = Store(tmp_path / ".refmatrix", backend="sqlite")
    s.init()
    return s


def _write_memory(tmp_path, name: str, body: str) -> "object":
    """Drop a minimal GMD memory file under tmp_path/memories/ and
    return its path."""
    from pathlib import Path
    mem_dir = tmp_path / "memories"
    mem_dir.mkdir(exist_ok=True)
    path = mem_dir / f"{name}.md"
    path.write_text(body)
    return path


def test_root_rel_mirrors_onto_doc_level_memory(tmp_path):
    s = _seed_store(tmp_path)
    src = _write_memory(tmp_path, "source-mem", '''---
gmd: "0.1"
id: source-mem
title: "Source"
tags: [feedback]
metadata:
  type: feedback
---

# Source {#root}

Body content.

rel: related-to -> [[target-mem]]
''')
    tgt = _write_memory(tmp_path, "target-mem", '''---
gmd: "0.1"
id: target-mem
title: "Target"
tags: [reference]
metadata:
  type: reference
---

# Target {#root}

Body.
''')
    stats = ingest_gmd_paths(s, [src, tgt], as_memory=True)
    # 1 explicit rel: edge declared.
    assert stats.rels >= 1
    src_eid = s.get_memory("source-mem")["id"]
    tgt_eid = s.get_memory("target-mem")["id"]
    # The mirrored edge: from doc-level src memory to doc-level target
    # memory under the `related-to` linkage.
    con = s._connect()
    # entity_links column convention: concept_id = the SRC side of
    # `store.link(linkage, concept_id, entity_id)`. The mirror emits
    # `store.link("related-to", doc_eid, target_eid)` so the row is
    # (entity_id=target_eid, concept_id=doc_eid).
    row = con.execute(
        "SELECT 1 FROM entity_links el "
        "JOIN linkage_types lt ON lt.id = el.linkage_id "
        "WHERE lt.name='related-to' "
        "  AND el.concept_id=? AND el.entity_id=?",
        (src_eid, tgt_eid),
    ).fetchone()
    assert row is not None, "root-rel mirror to doc-level memory missing"


def test_non_root_rel_does_not_mirror(tmp_path):
    """Only the `{#root}` anchor's rels mirror onto the doc-level
    memory. A sub-section's rel: still attaches to the sub-section
    node (which is the documented behavior for in-document
    organization)."""
    s = _seed_store(tmp_path)
    src = _write_memory(tmp_path, "src-with-section", '''---
gmd: "0.1"
id: src-with-section
title: "Source"
tags: [feedback]
metadata:
  type: feedback
---

# Source {#root}

## Sub-section {#sub}

rel: related-to -> [[target-mem]]
''')
    tgt = _write_memory(tmp_path, "target-mem", '''---
gmd: "0.1"
id: target-mem
title: "Target"
tags: [reference]
metadata:
  type: reference
---

# Target {#root}

body
''')
    ingest_gmd_paths(s, [src, tgt], as_memory=True)
    src_eid = s.get_memory("src-with-section")["id"]
    tgt_eid = s.get_memory("target-mem")["id"]
    con = s._connect()
    # entity_links column convention: concept_id = the SRC side of
    # `store.link(linkage, concept_id, entity_id)`. The mirror emits
    # `store.link("related-to", doc_eid, target_eid)` so the row is
    # (entity_id=target_eid, concept_id=doc_eid).
    row = con.execute(
        "SELECT 1 FROM entity_links el "
        "JOIN linkage_types lt ON lt.id = el.linkage_id "
        "WHERE lt.name='related-to' "
        "  AND el.concept_id=? AND el.entity_id=?",
        (src_eid, tgt_eid),
    ).fetchone()
    # No mirror: the rel: is on the sub-section node, not root.
    assert row is None


def test_root_rel_does_not_mirror_when_not_as_memory(tmp_path):
    """The mirror is `as_memory`-gated. A non-memory ingest keeps the
    old behavior (rel: edges attach to the node concept only) so the
    classic doc/code use case is unchanged."""
    s = _seed_store(tmp_path)
    src = _write_memory(tmp_path, "doc-src", '''---
gmd: "0.1"
id: doc-src
title: "Doc"
tags: [reference]
---

# Doc {#root}

rel: related-to -> [[doc-tgt]]
''')
    tgt = _write_memory(tmp_path, "doc-tgt", '''---
gmd: "0.1"
id: doc-tgt
title: "Target"
tags: [reference]
---

# Target {#root}

body
''')
    ingest_gmd_paths(s, [src, tgt], as_memory=False)
    # Doc-level entities exist as kind='doc', not memory.
    src_ent = s.resolve_entity("doc-src")
    tgt_ent = s.resolve_entity("doc-tgt")
    assert src_ent is not None and tgt_ent is not None
    con = s._connect()
    row = con.execute(
        "SELECT 1 FROM entity_links el "
        "JOIN linkage_types lt ON lt.id = el.linkage_id "
        "WHERE lt.name='related-to' "
        "  AND el.entity_id=? AND el.concept_id=?",
        (src_ent.id, tgt_ent.id),
    ).fetchone()
    # Pre-fix behavior preserved for non-memory ingest.
    assert row is None
