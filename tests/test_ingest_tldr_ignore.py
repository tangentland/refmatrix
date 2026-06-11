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
