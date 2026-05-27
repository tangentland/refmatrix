"""Tests for incremental sync, weighted links, semantic ingest, hooks."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from refmatrix.hooks import install
from refmatrix.ingest import _ingest_python_semantics, ingest_path
from refmatrix.query import QueryEngine
from refmatrix.store import Store
from refmatrix.sync import enqueue, flush_queue, sync_files, sync_since


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / ".refmatrix")
    s.init()
    yield s
    s.close()


# --- weighted ---------------------------------------------------------------


def test_weighted_link_and_top(store):
    parser = store.add_concept("parser")
    a = store.upsert_entity(kind="code", name="a.py")
    b = store.upsert_entity(kind="code", name="b.py")
    c = store.upsert_entity(kind="code", name="c.py")
    store.weighted_link("mentions", parser, a, weight=1.0)
    store.weighted_link("mentions", parser, b, weight=5.0)
    store.weighted_link("mentions", parser, c, weight=3.0)
    rows = store.top_weighted("mentions", parser, k=2)
    assert [eid for eid, _ in rows] == [b, c]
    assert store.get_weight("mentions", parser, b) == 5.0


# --- purge / forward index --------------------------------------------------


def test_purge_entity_clears_all_bitmaps(store):
    parser = store.add_concept("parser")
    tokenizer = store.add_concept("tokenizer")
    foo = store.upsert_entity(kind="code", name="foo.py", path="/x/foo.py")
    store.link("defines", parser, foo)
    store.link("mentions", tokenizer, foo)
    n = store.purge_entity(foo)
    assert n >= 2
    qe = QueryEngine(store)
    assert len(qe.run("defines:parser")) == 0
    assert len(qe.run("mentions:tokenizer")) == 0


def test_purge_path_removes_file_and_function_entities(store):
    foo_file = store.upsert_entity(kind="code", name="foo.py", path="/x/foo.py")
    foo_run = store.upsert_entity(kind="code", name="foo.py::run", path="/x/foo.py")
    other = store.upsert_entity(kind="code", name="bar.py", path="/x/bar.py")
    parser = store.add_concept("parser")
    store.link("defines", parser, foo_file)
    store.link("defines", parser, foo_run)
    store.link("defines", parser, other)
    store.purge_path("/x/foo.py")
    qe = QueryEngine(store)
    remaining = qe.run("defines:parser")
    assert other in remaining
    assert foo_file not in remaining
    assert foo_run not in remaining


# --- sync -------------------------------------------------------------------


def test_sync_files_handles_create_and_delete(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    f = proj / "foo.py"
    f.write_text("x = 1\n")
    s = Store(tmp_path / ".refmatrix")
    s.init()
    report = sync_files(s, [str(f)], project_root=proj)
    assert report["added"] == 1
    rel = "foo.py"
    assert s.get_entity("code", rel) is not None
    f.unlink()
    report = sync_files(s, [str(f)], project_root=proj)
    assert report["purged"] == 1
    assert s.get_entity("code", rel) is None
    s.close()


def test_sync_files_skips_unsupported_ext(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    f = proj / "thing.bin"
    f.write_text("xxx")
    s = Store(tmp_path / ".refmatrix")
    s.init()
    report = sync_files(s, [str(f)], project_root=proj)
    assert report["added"] == 0
    assert report["purged"] == 0
    s.close()


def test_queue_enqueue_and_flush(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    a = proj / "a.py"; a.write_text("# a")
    b = proj / "b.py"; b.write_text("# b")
    s = Store(tmp_path / ".refmatrix")
    s.init()
    enqueue(s.root, [str(a), str(b), str(a)])  # dedup
    report = flush_queue(s, project_root=proj)
    assert report["added"] == 2
    assert not (s.root / "dirty.queue").exists()
    s.close()


def test_sync_since_via_real_git(tmp_path):
    if subprocess.run(["git", "--version"], capture_output=True).returncode != 0:
        pytest.skip("git not available")
    proj = tmp_path / "proj"
    proj.mkdir()
    env = {**os.environ,
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    def run(*args):
        subprocess.run(["git", "-C", str(proj), *args], env=env, check=True,
                       capture_output=True)
    run("init", "-q", "-b", "main")
    (proj / "a.py").write_text("# a")
    run("add", "a.py")
    run("commit", "-q", "-m", "init")
    (proj / "b.py").write_text("# b")
    run("add", "b.py")
    run("commit", "-q", "-m", "add b")
    s = Store(proj / ".refmatrix")
    s.init()
    report = sync_since(s, "HEAD~1", project_root=proj)
    assert report["added"] == 1  # only b.py changed in HEAD~1..HEAD
    s.close()


# --- semantic ---------------------------------------------------------------


def test_python_semantic_ingest(tmp_path, store):
    proj = tmp_path
    f = proj / "mod.py"
    f.write_text(
        'import json\n'
        'from collections import Counter\n'
        '\n'
        'def parse(text):\n'
        '    """Parse the input text into tokens via the tokenizer."""\n'
        '    return Counter(text)\n'
    )
    n = _ingest_python_semantics(store, f, proj)
    assert n > 0
    qe = QueryEngine(store)
    # imports get namespaced under 'import/'
    json_concept = store.get_entity("concept", "import/json")
    coll_concept = store.get_entity("concept", "import/collections")
    assert json_concept is not None and coll_concept is not None
    # the bare 'json' must NOT exist — that's the whole point of namespacing,
    # so user-added json concepts don't collide with auto-imported ones.
    assert store.get_entity("concept", "json") is None
    file_e = store.get_entity("code", "mod.py")
    assert file_e is not None
    imports_json = qe.run("imports:import/json")
    assert file_e.id in imports_json
    # docstring keyword 'tokenizer' becomes a 'keyword/' namespaced concept
    tok = store.get_entity("concept", "keyword/tokenizer")
    assert tok is not None
    assert store.get_entity("concept", "tokenizer") is None
    func_e = store.get_entity("code", "mod.py::parse")
    assert func_e is not None
    mentions_tok = qe.run("mentions:keyword/tokenizer")
    assert func_e.id in mentions_tok
    # evidence was recorded
    ev = store.get_evidence(file_e.id, linkage="imports", concept_id=json_concept.id)
    assert ev and ev[0]["line"] is not None


# --- hooks ------------------------------------------------------------------


def test_install_hooks_dry_run_lists_targets(tmp_path):
    proj = tmp_path / "proj"
    (proj / ".git").mkdir(parents=True)
    rmx = proj / ".refmatrix"
    rmx.mkdir()
    out = install(project_root=proj, refmatrix_root=rmx, apply=False)
    txt = "\n".join(out)
    assert "post-commit" in txt
    assert "post-merge" in txt
    assert "settings.local.json" in txt or "user scope" in txt
    assert "dry-run" in txt
    # no actual files written
    assert not (proj / ".git" / "hooks" / "post-commit").exists()
    assert not (proj / ".claude" / "settings.local.json").exists()


def test_install_hooks_apply_writes_executable_scripts(tmp_path):
    proj = tmp_path / "proj"
    (proj / ".git").mkdir(parents=True)
    rmx = proj / ".refmatrix"
    rmx.mkdir()
    install(project_root=proj, refmatrix_root=rmx, apply=True)
    pc = proj / ".git" / "hooks" / "post-commit"
    assert pc.exists()
    assert os.access(pc, os.X_OK)
    settings = proj / ".claude" / "settings.local.json"
    assert settings.exists()
    data = json.loads(settings.read_text())
    assert "PostToolUse" in data["hooks"]
    assert "Stop" in data["hooks"]


def test_tldr_warm_invokes_binary_and_ingests(tmp_path, monkeypatch):
    """tldr-warm shells out to `tldr warm`, then ingests the resulting cache."""
    import json
    import subprocess
    from click.testing import CliRunner

    from refmatrix.cli import main as cli_main

    proj = tmp_path / "proj"
    proj.mkdir()
    rmx_root = proj / ".refmatrix"
    rmx_root.mkdir()
    Store(rmx_root).init()

    fake_bin = tmp_path / "fake-tldr"
    fake_bin.write_text("# placeholder")
    fake_bin.chmod(0o755)

    invoked: list[list[str]] = []

    def fake_run(cmd, *args, **kwargs):
        invoked.append(cmd)
        # simulate tldr warm: drop a call_graph.json into the project
        cache = proj / ".tldr" / "cache"
        cache.mkdir(parents=True, exist_ok=True)
        (cache / "call_graph.json").write_text(json.dumps({
            "edges": [{"from_file": "a.py", "from_func": "f",
                       "to_file": "b.py", "to_func": "g"}],
            "languages": ["python"],
        }))
        class R:
            returncode = 0
        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setenv("REFMATRIX_ROOT", str(rmx_root))

    runner = CliRunner()
    result = runner.invoke(
        cli_main,
        ["tldr-warm", str(proj), "--tldr-bin", str(fake_bin), "--lang", "python"],
    )
    assert result.exit_code == 0, result.output
    assert invoked, "subprocess.run was never called"
    cmd = invoked[0]
    assert cmd[0] == str(fake_bin)
    assert cmd[1] == "warm"
    assert "--lang" in cmd and "python" in cmd
    # ingest happened: a.py and b.py exist as code entities, plus f and g concepts
    s = Store(rmx_root)
    s._connect()
    assert s.get_entity("code", "a.py") is not None
    assert s.get_entity("concept", "f") is not None
    assert s.get_entity("concept", "g") is not None
    s.close()


def test_tldr_warm_errors_when_binary_missing(tmp_path, monkeypatch):
    import shutil
    from click.testing import CliRunner
    from refmatrix.cli import main as cli_main

    proj = tmp_path / "proj"
    proj.mkdir()
    rmx_root = proj / ".refmatrix"
    rmx_root.mkdir()
    Store(rmx_root).init()

    monkeypatch.setattr(shutil, "which", lambda _: None)
    monkeypatch.delenv("REFMATRIX_TLDR_BIN", raising=False)
    monkeypatch.setenv("REFMATRIX_ROOT", str(rmx_root))

    runner = CliRunner()
    result = runner.invoke(cli_main, ["tldr-warm", str(proj)])
    assert result.exit_code != 0
    assert "tldr" in result.output.lower()


def test_install_hooks_writes_claude_briefing(tmp_path):
    proj = tmp_path / "proj"
    (proj / ".git").mkdir(parents=True)
    rmx = proj / ".refmatrix"
    rmx.mkdir()
    out = install(project_root=proj, refmatrix_root=rmx, apply=True)
    briefing = rmx / "CLAUDE.md"
    assert briefing.exists()
    text = briefing.read_text()
    # core triggers should be present
    assert "rmx context" in text
    assert "rmx neighbors" in text
    assert "rmx sync --flush-queue" in text
    assert "DSL" in text and "PQL" in text
    # the suggestion to import is printed but the project CLAUDE.md is NOT written
    assert not (proj / "CLAUDE.md").exists()
    flat = "\n".join(out)
    assert "@.refmatrix/CLAUDE.md" in flat


def test_install_hooks_briefing_respects_force(tmp_path):
    proj = tmp_path / "proj"
    (proj / ".git").mkdir(parents=True)
    rmx = proj / ".refmatrix"
    rmx.mkdir()
    briefing = rmx / "CLAUDE.md"
    briefing.write_text("# my own notes")
    install(project_root=proj, refmatrix_root=rmx, apply=True)
    assert briefing.read_text() == "# my own notes"
    install(project_root=proj, refmatrix_root=rmx, apply=True, force=True)
    assert "rmx context" in briefing.read_text()


def test_install_hooks_no_briefing_flag(tmp_path):
    proj = tmp_path / "proj"
    (proj / ".git").mkdir(parents=True)
    rmx = proj / ".refmatrix"
    rmx.mkdir()
    install(project_root=proj, refmatrix_root=rmx, apply=True, briefing=False)
    assert not (rmx / "CLAUDE.md").exists()


def test_install_hooks_no_overwrite_without_force(tmp_path):
    proj = tmp_path / "proj"
    (proj / ".git" / "hooks").mkdir(parents=True)
    pc = proj / ".git" / "hooks" / "post-commit"
    pc.write_text("# user's own hook")
    rmx = proj / ".refmatrix"
    rmx.mkdir()
    install(project_root=proj, refmatrix_root=rmx, apply=True)
    assert pc.read_text() == "# user's own hook"
    install(project_root=proj, refmatrix_root=rmx, apply=True, force=True)
    assert "rmx sync" in pc.read_text()


# --- llm-tldr semantic metadata ingester -----------------------------------


def _write_metadata(proj: Path, units: list[dict]) -> None:
    cache = proj / ".tldr" / "cache" / "semantic"
    cache.mkdir(parents=True)
    (cache / "metadata.json").write_text(json.dumps({
        "units": units, "model": "test", "dimension": 0, "count": len(units),
    }))


def test_ingest_metadata_creates_units_concepts_and_kind(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "a.py").write_text("def foo():\n    bar()\n")
    (proj / "b.py").write_text("def bar(): pass\n")
    _write_metadata(proj, [
        {
            "name": "foo",
            "qualified_name": "a.py.foo",
            "file": "a.py",
            "line": 1,
            "language": "python",
            "unit_type": "function",
            "signature": "def foo() -> None",
            "docstring": "",
            "calls": ["bar"],
            "called_by": [],
            "dependencies": "",
        },
        {
            "name": "bar",
            "qualified_name": "b.py.bar",
            "file": "b.py",
            "line": 1,
            "language": "python",
            "unit_type": "function",
            "signature": "def bar() -> None",
            "docstring": "",
            "calls": [],
            "called_by": ["foo"],
            "dependencies": "",
        },
    ])
    s = Store(proj / ".refmatrix")
    s.init()
    n = ingest_path(s, proj)
    assert n == 2

    # qualified-name unit entities
    foo_unit = s.get_entity("code", "a.py.foo")
    bar_unit = s.get_entity("code", "b.py.bar")
    assert foo_unit is not None and foo_unit.tldr == "def foo() -> None"
    assert foo_unit.meta.get("unit_type") == "function"
    assert bar_unit is not None

    # bare-name concepts collide with what user concepts would use
    foo_concept = s.get_entity("concept", "foo")
    bar_concept = s.get_entity("concept", "bar")
    assert foo_concept is not None and bar_concept is not None

    # kind/function categorical concept exists and links to both units
    qe = QueryEngine(s)
    is_a_function = qe.run("is_a:kind/function")
    assert foo_unit.id in is_a_function
    assert bar_unit.id in is_a_function

    # calls linkage: bar concept's `calls` bitmap holds foo (the caller)
    calls_bar = s.load_bitmap("calls", bar_concept.id)
    assert foo_unit.id in calls_bar


def test_ingest_metadata_aggregates_dependencies_per_file(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "x.py").write_text("import os\nimport sys\n")
    _write_metadata(proj, [
        {
            "name": "alpha",
            "qualified_name": "x.py.alpha",
            "file": "x.py",
            "line": 1,
            "language": "python",
            "unit_type": "function",
            "signature": "def alpha()",
            "docstring": "",
            "calls": [],
            "called_by": [],
            "dependencies": "os, sys",
        },
        {
            "name": "beta",
            "qualified_name": "x.py.beta",
            "file": "x.py",
            "line": 5,
            "language": "python",
            "unit_type": "function",
            "signature": "def beta()",
            "docstring": "",
            "calls": [],
            "called_by": [],
            "dependencies": "os, json",  # 'os' duplicated, 'json' new
        },
    ])
    s = Store(proj / ".refmatrix")
    s.init()
    ingest_path(s, proj)

    file_e = s.get_entity("code", "x.py")
    assert file_e is not None

    # Aggregated to file-level: os, sys, json all link the file once
    for mod in ("os", "sys", "json"):
        cid = s.get_entity("concept", f"import/{mod}")
        assert cid is not None, f"missing import/{mod}"
        bm = s.load_bitmap("imports", cid.id)
        assert file_e.id in bm

    # Dedup check: 'os' appears in two units but only once on the file
    os_concept = s.get_entity("concept", "import/os")
    bm = s.load_bitmap("imports", os_concept.id)
    assert len(bm) == 1


def test_ingest_metadata_skips_blocklisted_callees(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "x.py").write_text("class Foo: ...\n")
    _write_metadata(proj, [
        {
            "name": "Foo",
            "qualified_name": "x.py.Foo",
            "file": "x.py",
            "line": 1,
            "language": "python",
            "unit_type": "class",
            "signature": "class Foo",
            "docstring": "",
            "calls": ["__init__", "real_helper"],
            "called_by": [],
            "dependencies": "",
        },
    ])
    s = Store(proj / ".refmatrix")
    s.init()
    ingest_path(s, proj)
    # __init__ should NOT have created a concept
    assert s.get_entity("concept", "__init__") is None
    # real_helper should
    assert s.get_entity("concept", "real_helper") is not None


def test_ingest_auto_prefers_metadata_over_call_graph(tmp_path):
    """When both metadata.json and call_graph.json exist, metadata wins."""
    proj = tmp_path / "proj"
    proj.mkdir()
    # Sentinel call_graph.json with a unique entity name we can detect.
    cache = proj / ".tldr" / "cache"
    cache.mkdir(parents=True)
    (cache / "call_graph.json").write_text(json.dumps({
        "edges": [{
            "from_file": "legacy.py", "from_func": "from_callgraph",
            "to_file": "legacy.py", "to_func": "to_callgraph",
        }],
    }))
    # Metadata with a different sentinel
    _write_metadata(proj, [{
        "name": "from_metadata",
        "qualified_name": "new.py.from_metadata",
        "file": "new.py",
        "line": 1,
        "language": "python",
        "unit_type": "function",
        "signature": "def from_metadata()",
        "docstring": "",
        "calls": [],
        "called_by": [],
        "dependencies": "",
    }])
    s = Store(proj / ".refmatrix")
    s.init()
    ingest_path(s, proj, source="auto")
    assert s.get_entity("code", "new.py.from_metadata") is not None
    # Old call_graph entity must NOT have been created (auto stops at metadata)
    assert s.get_entity("code", "legacy.py::from_callgraph") is None


# --- cooperative shutdown ---------------------------------------------------


def test_sync_files_cooperative_cancel(tmp_path):
    """`sync_files(cancel_check=...)` aborts the per-file loop when the
    check returns True. Files queued before the cancel point still
    ingest; files after are skipped. Transaction commits the partial
    batch cleanly (no rollback)."""
    proj = tmp_path / "proj"
    proj.mkdir()
    files = []
    for i in range(8):
        p = proj / f"f{i}.md"
        p.write_text(f"# title {i}\n\nbody {i}\n")
        files.append(p)

    s = Store(proj / ".refmatrix")
    s.init()

    # Cancel after the 3rd file is processed.
    seen = {"n": 0}

    def cancel_after_three() -> bool:
        seen["n"] += 1
        return seen["n"] > 3

    report = sync_files(
        s, [str(p) for p in files],
        project_root=proj,
        cancel_check=cancel_after_three,
    )
    s.close()

    assert report["cancelled"] is True
    # First 3 files completed before cancel; remaining 5 skipped.
    assert report["added"] == 3
    assert report["touched"] == 3


def test_sync_files_no_cancel_completes_full_batch(tmp_path):
    """Default path (cancel_check=None) processes every file and reports
    cancelled=False."""
    proj = tmp_path / "proj"
    proj.mkdir()
    files = []
    for i in range(4):
        p = proj / f"g{i}.md"
        p.write_text(f"# g {i}\n")
        files.append(p)

    s = Store(proj / ".refmatrix")
    s.init()
    report = sync_files(s, [str(p) for p in files], project_root=proj)
    s.close()
    assert report["cancelled"] is False
    assert report["added"] == 4
