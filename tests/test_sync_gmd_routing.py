"""The mtime gate must not outrank the GMD dispatch.

`sync` skips a file whose on-disk mtime matches what it indexed, on the premise
that "the previous ingest's output is still current". That premise fails when
the ROUTING changed rather than the file: a `.md` first indexed by the plain-doc
branch is stamped `mark_tracked(mtime)` there, and if it later becomes
GMD-eligible its mtime is unchanged, so the gate fires and it never reaches the
dispatch. It stays a content-less doc entity until somebody edits it.

Measured on a real store before the fix: 199 `.md` files with zero `mentions`
edges, 179 valid GMD, 100% skipped by this gate — 43% of that store's documents
present in the index and unretrievable by their own content. The failure is
invisible by construction: it increments a "skipped_unchanged" counter and
looks like healthy caching.
"""

from __future__ import annotations

import pytest

from refmatrix.store import Store
from refmatrix.sync import _gmd_route_pending, _is_gmd_file

GMD_DOC = """---
gmd: "0.1"
id: sample-doc
title: "Sample"
tags: [t]
---

# Sample {#root}

The daemon warms the embedder before serving.
"""

PLAIN_DOC = """# Just markdown

No frontmatter here.
"""


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.delenv("RMX_BACKEND", raising=False)
    s = Store(tmp_path / ".refmatrix")
    s.init()
    yield s
    s.close()


def test_gmd_file_never_ingested_is_not_skippable(store, tmp_path):
    """The bug: GMD-eligible, tracked, unchanged — and no GMD ingest ever ran."""
    f = tmp_path / "doc.md"
    f.write_text(GMD_DOC)
    assert _is_gmd_file(f)
    # a doc entity exists (the plain branch made one) but carries no GMD hash
    store.upsert_entity(kind="doc", name="sample-doc", path=str(f))
    assert _gmd_route_pending(store, f, ".md") is True


def test_gmd_file_already_ingested_stays_skippable(store, tmp_path):
    """Once pass2 has stamped the content hash, the gate may skip freely —
    otherwise every sync would re-ingest every GMD file forever."""
    from refmatrix.ingest_gmd import _write_content_hash, _doc_content_hash
    f = tmp_path / "doc.md"
    f.write_text(GMD_DOC)
    eid = store.upsert_entity(kind="doc", name="sample-doc", path=str(f))
    _write_content_hash(store, eid, _doc_content_hash(f))
    assert _gmd_route_pending(store, f, ".md") is False


def test_plain_markdown_is_not_forced_through_the_gmd_path(store, tmp_path):
    f = tmp_path / "plain.md"
    f.write_text(PLAIN_DOC)
    assert _is_gmd_file(f) is False
    assert _gmd_route_pending(store, f, ".md") is False


def test_non_markdown_extensions_are_untouched(store, tmp_path):
    f = tmp_path / "mod.py"
    f.write_text("def f():\n    return 1\n")
    assert _gmd_route_pending(store, f, ".py") is False


def test_unreadable_file_does_not_raise(store, tmp_path):
    """The gate runs on every sync; it must degrade to 'skippable', never
    throw, or one bad file stops the whole pass."""
    assert _gmd_route_pending(store, tmp_path / "missing.md", ".md") is False
