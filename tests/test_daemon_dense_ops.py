"""Daemon `embed` + `ann_search` op handler tests.

Direct in-process Daemon — no fork, no socket. Tests the handler
logic + cache behavior + cooperative shutdown.

Skipped without [dense] extra. Model-load tests skipped under
RMX_EMBED_OFFLINE=1.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

_HAS_DENSE = (
    importlib.util.find_spec("sentence_transformers") is not None
    and importlib.util.find_spec("lance") is not None
)
_OFFLINE = os.environ.get("RMX_EMBED_OFFLINE") == "1"

pytestmark = [
    pytest.mark.skipif(not _HAS_DENSE, reason="[dense] extra not installed"),
    pytest.mark.skipif(_OFFLINE, reason="RMX_EMBED_OFFLINE=1"),
]


def _make_daemon(tmp_path: Path):
    from refmatrix.daemon import Daemon
    from refmatrix.store import Store

    root = tmp_path / ".refmatrix"
    root.mkdir(parents=True, exist_ok=True)
    d = Daemon(root)
    s = Store(root)
    s.init()
    d.store = s
    return d


def test_op_embed_processes_pending_rows(tmp_path):
    from refmatrix.daemon import _op_embed

    d = _make_daemon(tmp_path)
    s = d.store
    a = s.upsert_entity(kind="code", name="a.py", tldr="Greeting helper.")
    b = s.upsert_entity(kind="code", name="b.py", tldr="Date arithmetic.")

    result = _op_embed(d, {"kinds": ["code"], "limit": 32})
    assert result["embedded"] == 2
    assert result["remaining"] == 0
    assert result["dim"] > 0

    # Subsequent call sees nothing pending.
    result2 = _op_embed(d, {"kinds": ["code"], "limit": 32})
    assert result2["embedded"] == 0


def test_op_embed_respects_kind_filter(tmp_path):
    from refmatrix.daemon import _op_embed

    d = _make_daemon(tmp_path)
    s = d.store
    code = s.upsert_entity(kind="code", name="a.py", tldr="Code.")
    doc = s.upsert_entity(kind="doc", name="a.md", tldr="Doc.")

    result = _op_embed(d, {"kinds": ["code"]})
    assert result["embedded"] == 1
    # Doc still pending after we asked for code only.
    remaining_doc = s.pending_embeddings(kinds=["doc"])
    assert any(r[0] == doc for r in remaining_doc)


def test_op_embed_skips_empty_text_rows(tmp_path):
    from refmatrix.daemon import _op_embed

    d = _make_daemon(tmp_path)
    s = d.store
    # Empty name + empty tldr → extractor returns "" → skipped.
    empty = s.upsert_entity(kind="code", name="")
    full = s.upsert_entity(kind="code", name="real.py", tldr="useful")
    result = _op_embed(d, {"kinds": ["code"]})
    assert result["embedded"] == 1


def test_op_embed_cooperative_cancel(tmp_path):
    from refmatrix.daemon import _op_embed

    d = _make_daemon(tmp_path)
    s = d.store
    for i in range(3):
        s.upsert_entity(kind="code", name=f"f{i}.py", tldr=f"file {i}")
    d._shutdown_event.set()
    result = _op_embed(d, {"kinds": ["code"]})
    assert result.get("cancelled") is True
    assert result["embedded"] == 0


def test_op_ann_search_finds_inserted_row(tmp_path):
    from refmatrix.daemon import _op_ann_search, _op_embed

    d = _make_daemon(tmp_path)
    s = d.store
    eid = s.upsert_entity(
        kind="code", name="tokenize.py",
        tldr="Lex source text into tokens.",
    )
    _op_embed(d, {"kinds": ["code"]})
    result = _op_ann_search(d, {"query": "lexer that splits text", "k": 5})
    hits = result["hits"]
    assert any(h["id"] == eid for h in hits)


def test_op_embed_rebuild_redoes_existing_rows(tmp_path):
    from refmatrix.daemon import _op_embed

    d = _make_daemon(tmp_path)
    s = d.store
    s.upsert_entity(kind="code", name="x.py", tldr="x")
    _op_embed(d, {"kinds": ["code"]})
    # Nothing pending now.
    assert _op_embed(d, {"kinds": ["code"]})["embedded"] == 0
    # rebuild=True ignores vectors_updated_at and re-embeds.
    r = _op_embed(d, {"kinds": ["code"], "rebuild": True})
    assert r["embedded"] == 1


def test_op_ann_search_rejects_dim_mismatch(tmp_path):
    from refmatrix.daemon import _op_ann_search

    d = _make_daemon(tmp_path)
    # Force-load embedder so we know its dim. Pass a vector with
    # a deliberately wrong shape.
    emb = d._embedder()
    bogus = [0.0] * (emb.dim + 5)
    result = _op_ann_search(d, {"vector": bogus, "k": 1})
    assert result.get("ok") is False
    assert "dim" in result["error"]
