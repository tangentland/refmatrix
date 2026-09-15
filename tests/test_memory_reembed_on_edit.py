"""An edited memory body must re-queue for embedding.

Regression for the silent-staleness class reported from cliquedb (0.25.10):
the memory bridge (then `memory sync-disk`) reported `updated=217` and `embed --kinds memory` then
reported `embedded=0`, so recall kept serving the PRE-EDIT vector while both
commands exited 0.

Cause: memory bodies live in the `memory_content` sidecar, but
`pending_embeddings` keys staleness off `entities.updated_at` — and
`upsert_entity`'s no-op gate (f3b7c9d, the re-embed-tax fix) never bumps it for
kind='memory' because path/tldr/meta are all NULL on that call. `add_memory`
now ratchets the entity clock itself when an EMBEDDED field really changed.

The metadata-only case is the other half of the contract: the bridge rewrites
`source_mtime` on every scan, so bumping on metadata would re-stale every row
each cycle — the exact tax f3b7c9d removed.
"""
from __future__ import annotations

from refmatrix.store import Store


def _pending_names(s: Store) -> set[str]:
    return {name for _, _, name in s.pending_embeddings(kinds=["memory"])}


def _mark_embedded(s: Store, name: str) -> None:
    """Simulate a completed embed pass for one memory row: the vector is now
    current as of this row's updated_at, so it is no longer pending."""
    con = s._connect()
    con.execute(
        "UPDATE entities SET vectors_updated_at = updated_at, "
        "vectors_partition = ? WHERE kind='memory' AND name=?",
        (s.partition_name, name),
    )
    con.commit()


def test_edited_body_requeues_for_embedding(tmp_path):
    s = Store(tmp_path / ".refmatrix")
    s.init()
    s.add_memory(name="m1", content="original body", mtype="project")
    _mark_embedded(s, "m1")
    assert _pending_names(s) == set()

    s.add_memory(name="m1", content="rewritten body, much longer", mtype="project")
    assert "m1" in _pending_names(s), "edited body must re-queue for embed"
    s.close()


def test_changed_mtype_or_tags_requeues(tmp_path):
    # Both are part of the embedded text (embedder._extract_memory).
    s = Store(tmp_path / ".refmatrix")
    s.init()
    s.add_memory(name="m1", content="body", mtype="project", tags=["a"])
    _mark_embedded(s, "m1")

    s.add_memory(name="m1", content="body", mtype="feedback", tags=["a"])
    assert "m1" in _pending_names(s), "mtype is embedded — must re-queue"

    _mark_embedded(s, "m1")
    s.add_memory(name="m1", content="body", mtype="feedback", tags=["a", "b"])
    assert "m1" in _pending_names(s), "tags are embedded — must re-queue"
    s.close()


def test_metadata_only_rewrite_does_not_requeue(tmp_path):
    """The re-embed tax must stay dead: the bridge stamps a fresh source_mtime
    on every scan, and that alone must not re-stale the row."""
    s = Store(tmp_path / ".refmatrix")
    s.init()
    s.add_memory(
        name="m1", content="body", mtype="project",
        metadata={"source": "memory_sync_disk", "source_mtime": 1.0},
    )
    _mark_embedded(s, "m1")

    s.add_memory(
        name="m1", content="body", mtype="project",
        metadata={"source": "memory_sync_disk", "source_mtime": 2.0},
    )
    assert _pending_names(s) == set(), "metadata churn must not re-stale"
    s.close()


def test_new_memory_is_pending(tmp_path):
    s = Store(tmp_path / ".refmatrix")
    s.init()
    s.add_memory(name="fresh", content="body", mtype="project")
    assert "fresh" in _pending_names(s)
    s.close()
