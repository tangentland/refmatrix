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


def test_root_rel_mirrors_for_plain_doc_ingest(tmp_path):
    """The mirror is NOT `as_memory`-gated. A plain `rmx ingest-gmd <dir>`
    (the form the memory rules document) must also put root-level rel: edges
    on the doc-level entity — otherwise seeding retrieval with the frontmatter
    `id:` returns mention noise and none of the graph."""
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
        "  AND el.concept_id=? AND el.entity_id=?",
        (src_ent.id, tgt_ent.id),
    ).fetchone()
    assert row is not None


def test_root_node_does_not_duplicate_doc_level_memory(tmp_path):
    """The synthetic `__root__` node maps to the bare doc-id, which is already
    the doc-level memory. It must NOT mint a parallel kind=concept (the dup
    that split a subject's inbound edges across two nodes)."""
    s = _seed_store(tmp_path)
    a = _write_memory(tmp_path, "alpha-mem", '''---
gmd: "0.1"
id: alpha-mem
title: "Alpha"
tags: [project]
metadata:
  type: project
---

# Alpha {#root}

Body referencing beta.

rel: related-to -> [[beta-mem]]
''')
    b = _write_memory(tmp_path, "beta-mem", '''---
gmd: "0.1"
id: beta-mem
title: "Beta"
tags: [project]
metadata:
  type: project
---

# Beta {#root}

Body.
''')
    ingest_gmd_paths(s, [a, b], as_memory=True)
    con = s._connect()
    # Exactly one entity per slug, and it is the memory — no concept duplicate.
    for slug in ("alpha-mem", "beta-mem"):
        rows = con.execute(
            "SELECT kind, count(*) FROM entities WHERE name=? GROUP BY kind",
            (slug,),
        ).fetchall()
        kinds = {r[0]: r[1] for r in rows}
        assert kinds == {"memory": 1}, f"{slug} not deduped: {kinds}"
    # The cross-doc `[[beta-mem]]` target resolves to beta's MEMORY, and the
    # root-mirror lands the edge on alpha's MEMORY (memory->memory rel: chain).
    a_eid = s.get_memory("alpha-mem")["id"]
    b_eid = s.get_memory("beta-mem")["id"]
    row = con.execute(
        "SELECT 1 FROM entity_links el "
        "JOIN linkage_types lt ON lt.id = el.linkage_id "
        "WHERE lt.name='related-to' AND el.concept_id=? AND el.entity_id=?",
        (a_eid, b_eid),
    ).fetchone()
    assert row is not None, "memory->memory related-to edge missing"


def test_prose_heading_tokens_are_stopword_filtered(tmp_path):
    """Title tokens are filed as weight-2.0 `mentions` concepts. A prose
    heading must not file `What`/`the`/`after` — those outrank real terms in
    the BM25 mentions walk and drag in unrelated docs that share a common
    word."""
    s = _seed_store(tmp_path)
    src = _write_memory(tmp_path, "prose-doc", '''---
gmd: "0.1"
id: prose-doc
title: "Prose"
tags: [reference]
---

# Prose {#root}

## What the config does after boot {#detail}

body
''')
    ingest_gmd_paths(s, [src], as_memory=True)
    for junk in ("What", "the", "after"):
        assert s.get_entity("concept", junk) is None, (
            f"stopword '{junk}' filed as a concept from a heading"
        )
    # The signal-bearing token from the same heading survives.
    assert s.get_entity("concept", "config") is not None


def test_context_on_doc_id_surfaces_root_graph(tmp_path):
    """Seeding `rmx context` with the frontmatter `id:` must return the typed
    rel: edges that live on the `<id>#root` node, not only mention noise."""
    from refmatrix.context import build_context

    s = _seed_store(tmp_path)
    src = _write_memory(tmp_path, "seed-doc", '''---
gmd: "0.1"
id: seed-doc
title: "Seed"
tags: [reference]
---

# Seed {#root}

rel: amends -> [[other-doc]]

body text
''')
    tgt = _write_memory(tmp_path, "other-doc", '''---
gmd: "0.1"
id: other-doc
title: "Other"
tags: [reference]
---

# Other {#root}

body
''')
    ingest_gmd_paths(s, [src, tgt], as_memory=True)
    bundle = build_context(s, "seed-doc", degree=1, grep_backstop=False)
    linkages = set(bundle.groups)
    assert "amends" in linkages, (
        f"root-anchored rel: edge missing from bare-id context: {linkages}"
    )


def test_memory_context_surfaces_its_own_outbound_rels(tmp_path):
    """`store.link(verb, src, dst)` packs src into the concept_id column
    whatever the src kind, so a memory's own rel: edges are keyed by its id.
    The entity-anchored walk reads only the entity_id side, so a memory's
    declared graph was missing from its own bundle."""
    from refmatrix.context import build_context

    s = _seed_store(tmp_path)
    src = _write_memory(tmp_path, "outbound-src", '''---
gmd: "0.1"
id: outbound-src
title: "Outbound"
tags: [reference]
---

# Outbound {#root}

rel: depends-on -> [[outbound-tgt]]

body
''')
    tgt = _write_memory(tmp_path, "outbound-tgt", '''---
gmd: "0.1"
id: outbound-tgt
title: "Target"
tags: [reference]
---

# Target {#root}

body
''')
    ingest_gmd_paths(s, [src, tgt], as_memory=True)
    bundle = build_context(s, "outbound-src", degree=1, grep_backstop=False)
    assert "depends-on" in bundle.groups, (
        f"outbound rel: edge missing from its own context: {set(bundle.groups)}"
    )
    names = {en.entity.name for en in bundle.groups["depends-on"]}
    assert "outbound-tgt" in names


def test_context_rows_are_deduped_per_linkage(tmp_path):
    """Merging the outbound, inbound, and `#root`-companion row sources must
    not list the same (linkage, entity) twice."""
    from refmatrix.context import build_context

    s = _seed_store(tmp_path)
    src = _write_memory(tmp_path, "dedup-src", '''---
gmd: "0.1"
id: dedup-src
title: "Dedup"
tags: [reference]
---

# Dedup {#root}

rel: depends-on -> [[dedup-tgt]]

body
''')
    tgt = _write_memory(tmp_path, "dedup-tgt", '''---
gmd: "0.1"
id: dedup-tgt
title: "Target"
tags: [reference]
---

# Target {#root}

body
''')
    ingest_gmd_paths(s, [src, tgt], as_memory=True)
    bundle = build_context(s, "dedup-src", degree=1, grep_backstop=False)
    for linkage, entries in bundle.groups.items():
        ids = [en.entity.id for en in entries]
        assert len(ids) == len(set(ids)), f"duplicate rows under '{linkage}'"
