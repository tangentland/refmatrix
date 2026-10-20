"""Task 3.7 remedy round 1 — the verbs against a REAL spawned daemon (RED where noted).

R-S1 (ch-bsd [[bsd-plan3-task37-impl-41c3568#s-1]], RED): `link` / `unlink` / `canon link`
     resolved names on the read snapshot, which lags the writer (~250 ms debounce), so an
     `add concept` followed at once by `link` failed "no concept named". The verbs now send
     NAMES and the ops resolve them under the writer: read-your-writes, no sleep.
R-RM8 (graduation): one FakeDaemon payload test per family — canon, curation, matrix,
     focus — now also runs end to end on a spawned daemon (short `/tmp` root).
     workflow/test_mock_registry.md records the graduation.
Adapted from the auditor's probe /private/tmp/claude-501/bsd37/t/test_bsd37_raw.py.
"""
from __future__ import annotations

import shutil
import tempfile
import time
from pathlib import Path

import pytest

from refmatrix import daemon as dm
from refmatrix import verbs
from refmatrix.store import Store


@pytest.fixture(scope="module")
def live():
    base = Path(tempfile.mkdtemp(prefix="rmxk-", dir="/tmp"))
    root = base / "proj" / ".refmatrix"
    root.parent.mkdir()
    s = Store(root)
    s.init()
    s.close()
    pid = dm.spawn_daemon_subprocess(root, watch_root=[])
    assert pid and dm.ping(root)
    verbs.matrix(root, action="add_concept", name="warm")       # forces a first snapshot
    deadline = time.monotonic() + 30
    while not (root / "catalog.read.duckdb").exists() and time.monotonic() < deadline:
        time.sleep(0.1)
    assert (root / "catalog.read.duckdb").exists(), "the daemon never wrote a snapshot"
    yield root
    dm.stop_daemon(root)
    shutil.rmtree(base, ignore_errors=True)


@pytest.fixture(autouse=True)
def _no_partition_env(monkeypatch):
    monkeypatch.delenv("RMX_PARTITION", raising=False)


# ---- R-S1: read-your-writes (RED at 6fd9b7c) -------------------------------------------------


@pytest.mark.timeout(120)
def test_add_concept_then_link_at_once(live):
    r1 = verbs.matrix(live, action="add_concept", name="fresh1")
    verbs.matrix(live, action="add_entity", kind="doc", name="freshdoc1")
    assert r1.get("source") == "daemon", r1
    out = verbs.matrix(live, action="link", concept="fresh1", entity="freshdoc1")
    assert out.get("created") is True, out


@pytest.mark.timeout(120)
def test_link_then_unlink_at_once(live):
    verbs.matrix(live, action="add_concept", name="fresh2")
    verbs.matrix(live, action="add_entity", kind="doc", name="freshdoc2")
    verbs.matrix(live, action="link", concept="fresh2", entity="freshdoc2")
    out = verbs.matrix(live, action="unlink", concept="fresh2", entity="freshdoc2")
    assert out.get("unlinked") is True, out


@pytest.mark.timeout(120)
def test_add_concept_then_canon_link_at_once(live):
    """Also R-RM8's canon graduation (the link_canon payload, end to end)."""
    verbs.matrix(live, action="add_concept", name="fresh3")
    out = verbs.canon(live, action="link", concept="fresh3", canon_name="Fresh3")
    assert isinstance(out.get("canon_id"), int), out


# ---- R-RM8: curation + focus graduations ------------------------------------------------------


@pytest.mark.timeout(120)
def test_curate_protect_end_to_end(live):
    verbs.matrix(live, action="add_entity", kind="doc", name="keepme.md")
    out = verbs.curate(live, action="protect", names=["keepme.md"])
    assert out["count"] == 1 and out["names"] == ["keepme.md"], out
    assert out.get("source") == "daemon", out
    prev = verbs.curate(live, action="forget", names=["keepme.md"])
    assert prev["dry_run"] is True and prev["names"] == ["keepme.md"], prev


@pytest.mark.timeout(120)
def test_focus_subjects_end_to_end(live):
    rec = verbs.change_subject(live, "Topic Live", session="sLive")
    assert isinstance(rec.get("id"), int), rec
    deadline = time.monotonic() + 30
    labels: list = []
    while time.monotonic() < deadline:
        labels = [r.get("label") for r in verbs.focus(live, action="subjects")["rows"]]
        if "Topic Live" in labels:
            break
        time.sleep(0.25)
    assert "Topic Live" in labels, labels
