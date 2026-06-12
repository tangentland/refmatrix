"""The tldr metadata-cache ingest honors `.refmatrix_ignore`.

The cache indexes the whole tree, so without filtering it re-adds units from
ignored paths (e.g. a vendored/duplicate tree) that the tree-walk + semantic
passes already exclude. Regression for the viascope `uat-workspace` dup.
"""
from __future__ import annotations

import json

from refmatrix.ingest import _ingest_tldr_metadata
from refmatrix.store import Store


def test_tldr_metadata_ingest_skips_ignored_units(tmp_path):
    proj = tmp_path / "proj"
    (proj / ".refmatrix").mkdir(parents=True)
    (proj / ".refmatrix" / ".refmatrix_ignore").write_text("vendored\n")
    cache = proj / ".tldr" / "cache" / "semantic"
    cache.mkdir(parents=True)
    cache.joinpath("metadata.json").write_text(json.dumps({"units": [
        {"qualified_name": "src/app.py::handler", "file": "src/app.py",
         "name": "handler", "unit_type": "function"},
        {"qualified_name": "vendored/dup/app.py::handler",
         "file": "vendored/dup/app.py", "name": "handler",
         "unit_type": "function"},
    ]}))

    s = Store(tmp_path / "store")
    s.init()
    with s.with_partition("p"):
        _ingest_tldr_metadata(s, proj)
        paths = [
            r[0] for r in s._connect().execute(
                "SELECT path FROM entities WHERE kind='code'"
            ).fetchall()
        ]
    assert any("src/app.py" in p for p in paths)
    assert not any("vendored" in p for p in paths)
    s.close()


def test_tldr_metadata_mtime_gate_skips_unchanged(tmp_path, monkeypatch):
    """Front-door no-op gate: a re-ingest over an unchanged metadata.json mtime
    skips the bulk upserts + link flush and returns the recorded unit count.
    This is the viascope-shaped path (metadata.json present) — the ~18s no-op
    write tax the gate removes. Touching the file re-arms the pass."""
    import os
    proj = tmp_path / "proj"
    (proj / ".refmatrix").mkdir(parents=True)
    cache = proj / ".tldr" / "cache" / "semantic"
    cache.mkdir(parents=True)
    mp = cache / "metadata.json"
    mp.write_text(json.dumps({"units": [
        {"qualified_name": "src/app.py::handler", "file": "src/app.py",
         "name": "handler", "unit_type": "function"},
    ]}))

    s = Store(tmp_path / "store")
    s.init()
    with s.with_partition("p"):
        n1 = _ingest_tldr_metadata(s, proj, pre_tracked=dict(s.list_tracked()))
        assert n1 == 1

        # bulk_upsert_entity is the pass's sole entity-write entry point; a
        # gated no-op must not call it.
        calls = {"bulk": 0}
        real = s.bulk_upsert_entity

        def spy(*a, **k):
            calls["bulk"] += 1
            return real(*a, **k)

        monkeypatch.setattr(s, "bulk_upsert_entity", spy)

        n2 = _ingest_tldr_metadata(s, proj, pre_tracked=dict(s.list_tracked()))
        assert n2 == 1            # count preserved for chaining + tally
        assert calls["bulk"] == 0  # gate fired: zero re-writes

        st = mp.stat()
        os.utime(mp, (st.st_atime + 5, st.st_mtime + 5))
        n3 = _ingest_tldr_metadata(s, proj, pre_tracked=dict(s.list_tracked()))
        assert n3 == 1
        assert calls["bulk"] > 0
    s.close()
