"""`--force`'s stamp clear must drop BOTH ingest gates.

An ingest stamp records that a file was read, never which extractor read it.
When the extractor changes (0.48.0) and the file does not, every pass skips and
a re-ingest re-derives nothing -- so the clear has to reach the tracked_files
mtimes AND the `gmd_content_hash` the GMD passes gate on, which live in
different places.
"""
from __future__ import annotations

import json

import pytest

from refmatrix.store import Store


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / ".refmatrix")
    s.init()
    yield s
    s.close()


def _meta_of(store, kind, name):
    row = store.get_entity(kind, name)
    assert row is not None
    meta = row.meta
    return json.loads(meta) if isinstance(meta, str) else (meta or {})


def test_clear_drops_both_gates_and_keeps_the_entity(store, tmp_path):
    md = tmp_path / "c.md"
    md.write_text("# Charter\n")
    store.upsert_entity(kind="doc", name="charter", path=str(md),
                        meta={"gmd_content_hash": "abc", "gmd_pass2_done": True,
                              "keep": "me"})
    store.mark_tracked(str(md), 123.0)
    store.mark_tracked(f"pysem:{tmp_path}/a.py", 456.0)
    assert store.get_tracked_mtime(str(md)) == 123.0

    r = store.clear_tracked_stamps()

    # The synthetic bulk-gate key counts too: it is what gates the semantic pass.
    assert r["stamps_cleared"] == 2
    assert r["gmd_hashes_cleared"] == 1
    assert store.list_tracked() == []

    # Non-destructive: unlike untrack_by_path, the entity and its unrelated
    # meta survive, so a forced re-ingest overwrites in place.
    meta = _meta_of(store, "doc", "charter")
    assert "gmd_content_hash" not in meta
    assert "gmd_pass2_done" not in meta
    assert meta["keep"] == "me"


def test_clear_scopes_to_a_like_glob(store):
    store.mark_tracked("/a/one.py", 1.0)
    store.mark_tracked("/b/two.py", 2.0)

    r = store.clear_tracked_stamps(like="/a/%")

    assert r["stamps_cleared"] == 1
    assert store.get_tracked_mtime("/a/one.py") is None
    assert store.get_tracked_mtime("/b/two.py") == 2.0


def test_clear_leaves_a_store_with_no_stamps_alone(store):
    r = store.clear_tracked_stamps()
    assert r == {"stamps_cleared": 0, "gmd_hashes_cleared": 0,
                 "partition": r["partition"]}
