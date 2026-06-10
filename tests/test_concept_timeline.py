"""Tests for `rmx concept timeline` — graph resolution + CLI shape.

The graph->files resolution (`_concept_files`) is pure and tested directly.
The CLI happy path is exercised with --no-git and an empty session index
(session collection is best-effort), so the test needs no git repo or daemon.
"""
from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from refmatrix.cli import _concept_files, main
from refmatrix.store import Store


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / ".refmatrix")
    s.init()
    fov = s.add_concept("fov", description="field of view")
    cam = s.add_concept("camera", description="a camera")
    code = s.upsert_entity(kind="code", name="ui/src/FovWedge.tsx",
                           path="/repo/ui/src/FovWedge.tsx", tldr="wedge")
    doc = s.upsert_entity(kind="doc", name="docs/design/cameras.md",
                          path="/repo/docs/design/cameras.md", tldr="design")
    s.link("defines", fov, code)
    s.weighted_link("mentions", fov, doc, weight=2.0)
    # camera is a neighbor concept of the fov code file (defines), reachable
    # only at hops>=1 in this toy graph via a shared file.
    s.link("defines", cam, code)
    yield s, dict(fov=fov, cam=cam, code=code, doc=doc)
    s.close()


def test_concept_files_collects_code_and_doc_paths(store):
    s, ids = store
    files, names = _concept_files(s, [ids["fov"]], hops=0)
    assert "/repo/ui/src/FovWedge.tsx" in files
    assert "/repo/docs/design/cameras.md" in files
    # value is the repo-relative name used as the session --touched key
    assert files["/repo/ui/src/FovWedge.tsx"] == "ui/src/FovWedge.tsx"


def test_concept_files_unknown_concept_is_empty(store):
    s, _ = store
    files, names = _concept_files(s, [], hops=0)
    assert files == {}


def test_timeline_unknown_concept_errors(tmp_path, monkeypatch):
    monkeypatch.setenv("REFMATRIX_ROOT", str(tmp_path / ".refmatrix"))
    s = Store(tmp_path / ".refmatrix")
    s.init()
    s.close()
    res = CliRunner().invoke(
        main, ["concept", "timeline", "no-such-concept", "--no-git"])
    assert res.exit_code != 0
    assert "unknown concept" in res.output.lower()


def test_timeline_json_reports_resolved_files(tmp_path, monkeypatch):
    monkeypatch.setenv("REFMATRIX_ROOT", str(tmp_path / ".refmatrix"))
    s = Store(tmp_path / ".refmatrix")
    s.init()
    fov = s.add_concept("fov", description="field of view")
    code = s.upsert_entity(kind="code", name="ui/src/FovWedge.tsx",
                           path="/repo/ui/src/FovWedge.tsx", tldr="wedge")
    s.link("defines", fov, code)
    s.close()
    res = CliRunner().invoke(
        main, ["concept", "timeline", "fov", "--no-git", "--json"])
    assert res.exit_code == 0, res.output
    data = json.loads(res.output)
    assert data["concept"] == "fov"
    assert data["resolved_files"] == 1
    # No git, no session index -> no events, but the command succeeds.
    assert data["events"] == []


def test_timeline_resolves_variant_spelling(tmp_path, monkeypatch):
    """PascalCase query resolves to the canonical concept (no --strict)."""
    monkeypatch.setenv("REFMATRIX_ROOT", str(tmp_path / ".refmatrix"))
    s = Store(tmp_path / ".refmatrix")
    s.init()
    c = s.add_concept("field_of_view", description="fov")
    code = s.upsert_entity(kind="code", name="ui/src/FovWedge.tsx",
                           path="/repo/ui/src/FovWedge.tsx")
    s.link("defines", c, code)
    s.close()
    res = CliRunner().invoke(
        main, ["concept", "timeline", "FieldOfView", "--no-git", "--json"])
    assert res.exit_code == 0, res.output
    assert json.loads(res.output)["resolved_files"] == 1
