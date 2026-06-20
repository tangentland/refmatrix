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


def test_hub_plist_renders_valid():
    raw = launchctl.render_hub_plist(port=7799, host="127.0.0.1")
    data = plistlib.loads(raw)
    assert data["Label"] == "com.refmatrix.hub"
    assert data["ProgramArguments"][:3] == [
        launchctl._rmx_path(), "hub", "start"] or "hub" in data["ProgramArguments"]
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


def test_curator_reads_queue(tmp_path):
    root = tmp_path / "proj" / ".refmatrix"
    root.mkdir(parents=True)
    (root / "curator.queue").write_text("a.md\nb.md\na.md\n")
    assert gmd_curator.read_queue(root) == ["a.md", "b.md"]  # deduped


def test_curator_skips_non_gmd(tmp_path, monkeypatch):
    proj = tmp_path / "proj"
    root = proj / ".refmatrix"
    root.mkdir(parents=True)
    plain = proj / "plain.md"
    plain.write_text("# just markdown, no frontmatter")
    (root / "curator.queue").write_text("plain.md\n")
    # lint unavailable → no manufactured failures; non-gmd skipped anyway
    monkeypatch.setenv("RMX_GMD_LINT", str(tmp_path / "nope.py"))
    assert gmd_curator.scan(root) == []


def test_curator_flags_bad_gmd(tmp_path, monkeypatch):
    proj = tmp_path / "proj"
    root = proj / ".refmatrix"
    root.mkdir(parents=True)
    doc = proj / "bad.md"
    doc.write_text('---\ngmd: "0.1"\nid: bad\n---\n# no anchor here\n')
    (root / "curator.queue").write_text("bad.md\n")
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
    (root / "curator.queue").write_text("bad.md\n")
    lint = tmp_path / "lint.py"
    lint.write_text("import sys; print('err'); sys.exit(1)")
    monkeypatch.setenv("RMX_GMD_LINT", str(lint))
    res = gmd_curator.scan_and_enqueue(root, drain=True)
    assert res["candidates"] == 1 and res["drained"] is True
    # drained
    assert not (root / "curator.queue").exists()
    # landed in the shared refinement queue
    from refmatrix.bus import Bus
    pending = Bus().refinement_queue("pending")
    assert any(c.get("origin") == "gmd-curator" for c in pending)


def test_curator_scheduler_op_allowed():
    from refmatrix import scheduler
    assert "curator-scan" in scheduler.ALLOWED_OPS
