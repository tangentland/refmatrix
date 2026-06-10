"""`.refmatrix_ignore` (project-local, in the .refmatrix dir) keeps operational
content (e.g. a workflow/ dir) out of the concept graph, while built-in rules
stay minimal. Covers the matcher, the loader, and both walk gates
(ingest `should_ignore` + watcher `is_relevant`)."""
from __future__ import annotations

from pathlib import Path

from refmatrix.ingest import (
    INGEST_IGNORE_DIRS,
    IgnoreSpec,
    load_ignore_spec,
    should_ignore,
)
from refmatrix.watch import is_relevant


def _write_ignore(root: Path, body: str) -> None:
    d = root / ".refmatrix"
    d.mkdir(parents=True, exist_ok=True)
    (d / ".refmatrix_ignore").write_text(body)


def test_builtin_defaults_minimal_no_workflow():
    # workflow is NOT hardcoded globally — it's a per-repo .refmatrix_ignore.
    assert "workflow" not in INGEST_IGNORE_DIRS
    assert set(INGEST_IGNORE_DIRS) == {"node_modules", "venv"}


def test_ignorespec_pattern_shapes():
    spec = IgnoreSpec([
        "# comment", "", "workflow/", "*.log", "docs/bullshit",
    ])
    # bare name -> any segment
    assert spec.match(Path("workflow/plans/p.md")) is True
    assert spec.match(Path("a/b/workflow/x.md")) is True
    # basename glob
    assert spec.match(Path("ui/run.log")) is True
    # anchored path
    assert spec.match(Path("docs/bullshit/r.md")) is True
    assert spec.match(Path("docs/bullshit")) is True
    # kept
    assert spec.match(Path("docs/design/cameras.md")) is False
    assert spec.match(Path("ui/src/FovWedge.tsx")) is False


def test_empty_or_missing_spec_is_none(tmp_path):
    assert load_ignore_spec(tmp_path) is None
    _write_ignore(tmp_path, "# only comments\n\n")
    assert load_ignore_spec(tmp_path) is None


def test_load_spec_reads_from_dot_refmatrix_dir(tmp_path):
    _write_ignore(tmp_path, "workflow/\n")
    spec = load_ignore_spec(tmp_path)
    assert spec is not None
    assert spec.match(Path("workflow/h.md")) is True


def test_should_ignore_combines_builtin_and_spec(tmp_path):
    _write_ignore(tmp_path, "workflow/\n")
    # spec hit (relative to root)
    assert should_ignore(tmp_path / "workflow" / "p.md", tmp_path) is True
    # built-in dir rule still fires without a spec root
    assert should_ignore(tmp_path / "node_modules" / "x.js") is True
    # durable doc kept
    assert should_ignore(tmp_path / "docs" / "design" / "c.md", tmp_path) is False


def test_watcher_is_relevant_honors_spec(tmp_path):
    _write_ignore(tmp_path, "workflow/\n")
    assert is_relevant(tmp_path / "workflow" / "h.md", tmp_path) is False
    assert is_relevant(tmp_path / "docs" / "c.md", tmp_path) is True
    # without a root, the spec isn't consulted (built-in rules only)
    assert is_relevant(tmp_path / "workflow" / "h.md") is True


def test_spec_cache_refreshes_on_mtime(tmp_path):
    _write_ignore(tmp_path, "workflow/\n")
    assert load_ignore_spec(tmp_path).match(Path("workflow/x")) is True
    # rewrite with a different pattern + bump mtime
    import os
    f = tmp_path / ".refmatrix" / ".refmatrix_ignore"
    f.write_text("scratch/\n")
    os.utime(f, (f.stat().st_atime, f.stat().st_mtime + 10))
    spec = load_ignore_spec(tmp_path)
    assert spec.match(Path("scratch/x")) is True
    assert spec.match(Path("workflow/x")) is False
