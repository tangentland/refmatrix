"""bug-093: the watch/sync semantic pass writes in BULK, not one row per concept.

py-spy on the deployed daemon (2026-10-07, pid 16409): 599 of 749 busy samples
in single-row `upsert_entity` from `_ingest_python_semantics`, re-syncing
`cli.py` after an edit, under `_store_lock`. The hub watchdog killed the daemon
three times. Full ingest already builds a `RecordingStore` record and applies it
with `bulk_apply_records`; the sync path still called the per-row function.

Real Store, real files. The upsert counter is a pass-through wrapper (the call
still reaches the real method), not a fake.
"""
from __future__ import annotations

from pathlib import Path

from refmatrix import sync as sync_mod
from refmatrix.store import Store

SRC = '''"""Module about daemons, locks and watchers."""


def alpha():
    """Alpha drains the queue, yields the writer lock, and counts failures."""
    return 1


class Beta:
    """Beta compacts datasets nightly; versions shrink and orphans are reaped."""

    def gamma(self):
        """Gamma probes the shared worker with a bounded deadline and budget."""
        return 2
'''


def _graph(s: Store) -> set:
    rows = s._connect().execute(
        "SELECT lt.name, c.name, e.name, el.weight FROM entity_links el "
        "JOIN linkage_types lt ON lt.id = el.linkage_id "
        "JOIN entities c ON c.id = el.concept_id "
        "JOIN entities e ON e.id = el.entity_id").fetchall()
    return {(r[0], r[1], r[2], None if r[3] is None else float(r[3])) for r in rows}


def _resync(tmp_path: Path, monkeypatch=None, counter=None) -> Store:
    proj = tmp_path
    proj.mkdir(parents=True, exist_ok=True)
    f = proj / "mod.py"
    f.write_text(SRC)
    s = Store(proj / ".refmatrix")
    s.init()
    sync_mod.sync_files(s, [str(f)], project_root=proj, semantic=True)
    f.write_text(SRC + "\n# edit\n")          # an edit: the watch re-sync path
    if counter is not None:
        real = Store.upsert_entity

        def counting(self, *a, **k):
            counter.append(k.get("name") or (a[1] if len(a) > 1 else None))
            return real(self, *a, **k)

        monkeypatch.setattr(Store, "upsert_entity", counting)
    sync_mod.sync_files(s, [str(f)], project_root=proj, semantic=True)
    return s


def test_the_resync_semantic_pass_does_not_upsert_one_concept_at_a_time(tmp_path, monkeypatch):
    calls: list = []
    s = _resync(tmp_path, monkeypatch, calls)
    keyword_upserts = [n for n in calls if isinstance(n, str) and n.startswith("keyword/")]
    s.close()
    assert keyword_upserts == [], f"{len(keyword_upserts)} single-row concept upserts"


def test_the_bulk_resync_builds_the_same_graph_as_the_per_row_path(tmp_path):
    from refmatrix.ingest import _ingest_python_semantics

    s = _resync(tmp_path / "a")
    got = _graph(s)
    s.close()

    ref_root = tmp_path / "b"
    ref_root.mkdir()
    f = ref_root / "mod.py"
    f.write_text(SRC + "\n# edit\n")
    r = Store(ref_root / ".refmatrix")
    r.init()
    sync_mod.sync_files(r, [str(f)], project_root=ref_root, semantic=False)
    _ingest_python_semantics(r, f, ref_root)
    want = _graph(r)
    r.close()
    assert got == want, (sorted(got ^ want)[:10])
