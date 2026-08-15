"""`rmx untrack` — drop tracked files that still exist on disk.

`vacuum` only reaps tracked_files whose path is GONE. A subtree ingested by
mistake but still present (an IDE bundle a wide $HOME crawl picked up, a
vendored dependency tree) therefore stays tracked forever and re-reports
`stale` every time upstream touches it. `untrack` is the lever for that case.
"""
from __future__ import annotations

import json
import os

import pytest
from click.testing import CliRunner

from refmatrix.cli import main
from refmatrix.store import Store


def _seed(tmp_path):
    """Store with two tracked trees: one to untrack, one that must survive."""
    s = Store(tmp_path / ".refmatrix", backend="sqlite")
    s.init()
    keep = tmp_path / "src" / "app.py"
    keep.parent.mkdir(parents=True)
    keep.write_text("def app():\n    return 1\n")
    junk_dir = tmp_path / "IDE.app" / "stubs"
    junk_dir.mkdir(parents=True)
    junk_paths = []
    for i in range(3):
        f = junk_dir / f"stub{i}.pyi"
        f.write_text(f"def stub{i}() -> int: ...\n")
        junk_paths.append(str(f))
    for pth in [str(keep), *junk_paths]:
        eid = s.upsert_entity("code", pth, path=pth)
        cid = s.add_concept("shared_term")
        s.link("mentions", cid, eid)
        s.mark_tracked(pth, os.path.getmtime(pth))
    return s, str(keep), junk_paths


def test_untrack_removes_live_paths_vacuum_cannot(tmp_path):
    s, keep, junk = _seed(tmp_path)
    like = str(tmp_path / "IDE.app") + "/%"

    # vacuum is a no-op here: every path still exists.
    before = len(s.stale_files())
    s.vacuum()
    assert s.get_entity("code", junk[0]) is not None, (
        "vacuum reaped a path that still exists on disk"
    )

    r = s.untrack_by_path(like=like)
    assert r["files_untracked"] == 3
    assert r["entities_purged"] == 3
    for pth in junk:
        assert s.get_entity("code", pth) is None
    # The unrelated tree is untouched.
    assert s.get_entity("code", keep) is not None
    assert before >= 0


def test_untrack_dry_run_changes_nothing(tmp_path):
    s, _keep, junk = _seed(tmp_path)
    like = str(tmp_path / "IDE.app") + "/%"
    r = s.untrack_by_path(like=like, dry_run=True)
    assert r["dry_run"] is True
    assert r["files_untracked"] == 3
    assert r["entities_purged"] == 3
    for pth in junk:
        assert s.get_entity("code", pth) is not None


def test_untrack_by_explicit_paths(tmp_path):
    s, keep, junk = _seed(tmp_path)
    r = s.untrack_by_path(paths=[junk[0]])
    assert r["files_untracked"] == 1
    assert s.get_entity("code", junk[0]) is None
    assert s.get_entity("code", junk[1]) is not None
    assert s.get_entity("code", keep) is not None


def test_untrack_without_selector_refuses(tmp_path):
    """An unfiltered untrack would empty the partition."""
    s, _keep, _junk = _seed(tmp_path)
    with pytest.raises(ValueError):
        s.untrack_by_path()


def test_untrack_emits_replayable_event(tmp_path, monkeypatch):
    monkeypatch.setenv("RMX_LOG", "1")
    s, _keep, junk = _seed(tmp_path)
    s.untrack_by_path(paths=[junk[0]])
    events = [
        json.loads(line)
        for line in s.log_path.read_text().splitlines() if line.strip()
    ]
    assert any(e.get("op") == "untrack" and e.get("path") == junk[0]
               for e in events), "untrack must log a replayable event"


def test_cli_untrack_requires_a_selector(tmp_path, monkeypatch):
    _seed(tmp_path)
    monkeypatch.chdir(tmp_path)
    r = CliRunner().invoke(main, ["untrack"])
    assert r.exit_code != 0
    assert "refusing to untrack" in r.output


def test_cli_untrack_dry_run_then_apply(tmp_path, monkeypatch):
    s, keep, junk = _seed(tmp_path)
    s.close()
    monkeypatch.chdir(tmp_path)
    like = str(tmp_path / "IDE.app") + "/%"

    r = CliRunner().invoke(main, ["untrack", "--like", like, "--dry-run"])
    assert r.exit_code == 0, r.output
    assert "would untrack" in r.output
    assert "3 files" in r.output

    r2 = CliRunner().invoke(main, ["untrack", "--like", like, "-y"])
    assert r2.exit_code == 0, r2.output
    assert "untracked" in r2.output

    s2 = Store(tmp_path / ".refmatrix", backend="sqlite")
    assert s2.get_entity("code", junk[0]) is None
    assert s2.get_entity("code", keep) is not None
