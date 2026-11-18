"""bug-216 — a project whose ROOT sits below a dot-dir or a dir named like an ignore dir must still
sync; the segment rules apply only BELOW the project root.

Spec: workflow/plans/task-bug216-rule-docs-in-graph.md (#r2-base, #ac-17).

WHY (spec-t56, reading the branch, 2026-11-13). `watch.is_relevant` calls `should_ignore(p, root)`
on ABSOLUTE paths with no `base`, and so does `sync._sync_one`. The hidden-directory rule and the
`INGEST_IGNORE_DIRS` rule read the absolute path's parts, and R12 put `build`, `dist` and
`__pycache__` into that list. A project at `<x>/.hidden/proj` or `<x>/build/proj` therefore syncs
NOTHING through the watcher or sync: every path carries the ancestor segment. Same class as the
session-ingest regression green-216 fixed with `base=` for `ingest-gmd <dir>`.

Each case: a project under `<short mkdtemp>/<ancestor>/proj` with a GMD doc at `docs/d.md` (must
land) and GMD docs at `build/x.md` / `dist/y.md` INSIDE the project (must stay out — the rule
still applies below the root). Routes: the daemon watcher (real handler / debouncer / flush; only
watchdog's Observer is faked, as in test_bug216_rule_docs_e2e), sync, the full `ingest_path` walk,
`ingest-gmd` (op), and `watch.is_relevant` itself (the `rmx watch` filter).
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

from refmatrix.store import Store
from tests.test_bug216_rule_docs_e2e import _ingested, _open, _run
import rmx_sandbox  # task-29.4 #r5: test roots live under the sandbox root (short_root)

ANCESTORS = (".hidden", "build")
ROUTES = ("watcher", "sync", "ingest-path", "op-ingest-gmd")


def _gmd(doc_id: str) -> str:
    return (f'---\ngmd: "0.1"\nid: {doc_id}\ntitle: "Fixture document"\ntags: [t]\n---\n\n'
            f"# Fixture document {{#root}}\n\nBody.\n")


@pytest.fixture(params=ANCESTORS)
def proj(request):
    base = Path(rmx_sandbox.short_root("b216w")).resolve()
    proj = base / request.param / "proj"
    for rel, doc_id in (("docs/d.md", "d"), ("build/x.md", "inner-build-x"),
                        ("dist/y.md", "inner-dist-y")):
        p = proj / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(_gmd(doc_id))
    root = proj / ".refmatrix"
    root.mkdir()
    s = Store(root)
    s.init()
    s.close()
    yield proj
    shutil.rmtree(base)


@pytest.mark.parametrize("route", ROUTES)
def test_ac17_a_project_below_an_ignored_ancestor_still_syncs(route, proj, monkeypatch):
    root = proj / ".refmatrix"
    _run(route, proj, root, monkeypatch)
    s = _open(root)
    try:
        got = _ingested(s, proj)
    finally:
        s.close()
    assert "docs/d.md" in got, (
        f"{route}: nothing synced for a project under `{proj.parent.name}/`: {got}")
    assert not {"build/x.md", "dist/y.md"} & got, f"{route}: an in-project ignore dir leaked: {got}"


def test_ac17_watch_is_relevant_judges_paths_below_the_root(proj):
    from refmatrix.watch import is_relevant
    assert is_relevant(proj / "docs" / "d.md", proj) is True
    assert is_relevant(proj / "build" / "x.md", proj) is False
    assert is_relevant(proj / "dist" / "y.md", proj) is False
