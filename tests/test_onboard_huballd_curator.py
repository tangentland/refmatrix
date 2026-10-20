"""UI onboarding wizard, hub launchd plist, GMD curator off the queue."""
from __future__ import annotations

import plistlib
import shutil
import tempfile
from pathlib import Path

import pytest

from refmatrix import gmd_curator, launchctl


@pytest.fixture
def home(monkeypatch):
    d = tempfile.mkdtemp(prefix="rh", dir="/tmp")
    monkeypatch.setenv("RMX_HOME", d)
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


# ---- hub launchd plist ----


def test_hub_plist_renders_valid(deployed_rmx):
    """On `deployed_rmx` (task 4.6 M2): it rendered against whatever `rmx` was on PATH, and
    the assertion's `or "hub" in ...` let any binary through."""
    raw = launchctl.render_hub_plist(port=7799, host="127.0.0.1")
    data = plistlib.loads(raw)
    assert data["Label"] == "com.refmatrix.hub"
    assert data["ProgramArguments"][:3] == [str(deployed_rmx), "hub", "start"], \
        data["ProgramArguments"]
    assert "--no-detach" in data["ProgramArguments"]
    assert "7799" in data["ProgramArguments"]
    assert data["RunAtLoad"] is True
    assert data["KeepAlive"] == {"SuccessfulExit": False}


def test_hub_status_shape():
    st = launchctl.hub_status()
    assert st["label"] == "com.refmatrix.hub"
    assert set(st) >= {"label", "plist_path", "installed", "loaded"}


# ---- GMD curator ----


def _gmd_file(path: Path, body: str):
    path.write_text(body)


def _spool(root: Path, *paths: Path) -> Path:
    """One watcher flush in the format the watcher WRITES (task 3.7 #fam-refine-drain,
    r2 B1): `.refmatrix/curator.spool/<time_ns:020d>-<uuid4>.jsonl`, one
    `{ts, path, reason}` JSON object per line. These fixtures used raw paths in a
    `curator.queue` — a format nobody writes — so they passed while the scheduled
    scan found zero files."""
    import json
    import time
    import uuid
    d = root / "curator.spool"
    d.mkdir(exist_ok=True)
    f = d / f"{time.time_ns():020d}-{uuid.uuid4()}.jsonl"
    f.write_text("".join(json.dumps({"ts": time.time(), "path": str(p),
                                     "reason": "fs-change"}) + "\n" for p in paths))
    return f


def test_curator_reads_queue(tmp_path):
    proj = tmp_path / "proj"
    root = proj / ".refmatrix"
    root.mkdir(parents=True)
    a, b = proj / "a.md", proj / "b.md"
    _spool(root, a, b)
    _spool(root, a)
    assert gmd_curator.read_queue(root) == [str(a), str(b)]  # deduped, oldest first


def test_curator_skips_non_gmd(tmp_path, monkeypatch):
    proj = tmp_path / "proj"
    root = proj / ".refmatrix"
    root.mkdir(parents=True)
    plain = proj / "plain.md"
    plain.write_text("# just markdown, no frontmatter")
    _spool(root, plain)
    # lint unavailable → no manufactured failures; non-gmd skipped anyway
    monkeypatch.setenv("RMX_GMD_LINT", str(tmp_path / "nope.py"))
    assert gmd_curator.scan(root) == []


def test_curator_flags_bad_gmd(tmp_path, monkeypatch):
    proj = tmp_path / "proj"
    root = proj / ".refmatrix"
    root.mkdir(parents=True)
    doc = proj / "bad.md"
    doc.write_text('---\ngmd: "0.1"\nid: bad\n---\n# no anchor here\n')
    _spool(root, doc)
    # stub linter that always reports an error
    lint = tmp_path / "lint.py"
    lint.write_text("import sys; print('1 errors'); sys.exit(1)")
    monkeypatch.setenv("RMX_GMD_LINT", str(lint))
    cands = gmd_curator.scan(root)
    assert len(cands) == 1
    assert cands[0]["kind"] == "lint"
    assert cands[0]["origin"] == "gmd-curator"
    assert cands[0]["path"].endswith("bad.md")


def test_curator_scan_and_enqueue_to_refinement(tmp_path, monkeypatch, home):
    proj = tmp_path / "proj"
    root = proj / ".refmatrix"
    root.mkdir(parents=True)
    doc = proj / "bad.md"
    doc.write_text('---\ngmd: "0.1"\nid: bad\n---\n# x\n')
    _spool(root, doc)
    lint = tmp_path / "lint.py"
    lint.write_text("import sys; print('err'); sys.exit(1)")
    monkeypatch.setenv("RMX_GMD_LINT", str(lint))
    res = gmd_curator.scan_and_enqueue(root, drain=True)
    assert res["candidates"] == 1 and res["drained"] is True
    # drained — by token: the spool file it read is gone
    assert not list((root / "curator.spool").glob("*.jsonl"))
    # landed in the shared refinement queue
    from refmatrix.bus import Bus
    pending = Bus().refinement_queue("pending")
    assert any(c.get("origin") == "gmd-curator" for c in pending)


def test_curator_scheduler_op_allowed():
    from refmatrix import scheduler
    assert "curator-scan" in scheduler.ALLOWED_OPS
