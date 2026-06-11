"""Grep backstop — the floor that makes `rmx context` never worse than a plain
grep, plus protected learn-on-miss so the index self-heals and survives prune."""
from __future__ import annotations

import shutil

import pytest

from refmatrix.context import _append_content_hits, _grep_backstop
from refmatrix.store import Store

_HAVE_GREP = bool(shutil.which("rg") or shutil.which("grep"))
pytestmark = pytest.mark.skipif(not _HAVE_GREP, reason="needs rg or grep on PATH")


def test_grep_backstop_finds_unindexed_file(tmp_path):
    (tmp_path / "mod.py").write_text(
        "import os\n\ndef compute_fov_wedge(angle):\n    return angle\n")
    out = _grep_backstop(["compute_fov_wedge"], tmp_path, limit=10)
    assert out, "grep should find the term on disk"
    e = out[0]
    assert e.linkage == "grep"
    assert e.entity.path.endswith("mod.py")
    assert e.line == 3
    assert "compute_fov_wedge" in (e.snippet or "")


def test_grep_backstop_respects_refmatrix_ignore(tmp_path):
    (tmp_path / "mod.py").write_text("def widget(): pass\n")
    vend = tmp_path / "uat-workspace"
    vend.mkdir()
    (vend / "mod.py").write_text("def widget(): pass\n")
    rmx = tmp_path / ".refmatrix"
    rmx.mkdir()
    (rmx / ".refmatrix_ignore").write_text("uat-workspace\n")
    paths = [e.entity.path for e in _grep_backstop(["widget"], tmp_path, limit=10)]
    assert any(p.endswith("/mod.py") and "uat-workspace" not in p for p in paths)
    assert not any("uat-workspace" in p for p in paths)  # ignored copy excluded


def test_grep_backstop_hit_lines_modes(tmp_path):
    (tmp_path / "m.py").write_text(
        "tok = 1\n\ndef tok_fn():\n    return tok\n")  # 'tok' on lines 1,3,4
    # nums: all line numbers on one entry
    e = _grep_backstop(["tok"], tmp_path, limit=10, hit_lines="nums")[0]
    assert e.lines == [1, 3, 4]
    # text: each line with content
    e2 = _grep_backstop(["tok"], tmp_path, limit=10, hit_lines="text")[0]
    assert e2.hit_lines and e2.hit_lines[0][0] == 1


def test_append_content_hits_backstop_fires_only_on_empty_index(tmp_path, monkeypatch):
    (tmp_path / "mod.py").write_text("def zzz_unique_token(): pass\n")
    s = Store(tmp_path / ".refmatrix")
    s.init()
    monkeypatch.setattr(s, "content_rank", lambda *a, **k: [])  # index returns nothing
    built: list = []
    _append_content_hits(s, "zzz_unique_token", built, seen_ids=set(),
                         max_entities=10, expand=0, include_sessions=False,
                         parent_cache={}, grep_backstop=True)
    assert built and built[0].linkage == "grep"
    # off → no backstop, stays empty
    built2: list = []
    _append_content_hits(s, "zzz_unique_token", built2, seen_ids=set(),
                         max_entities=10, expand=0, include_sessions=False,
                         parent_cache={}, grep_backstop=False)
    assert built2 == []
    s.close()


def test_maybe_learn_grep_backstop_brokers_hits_to_daemon(tmp_path):
    """The replica read path is read-only, so the CLI brokers the learn through
    the daemon writer. Verify it extracts every hit line and only fires when the
    backstop is on AND a grep group exists."""
    from refmatrix import cli
    from refmatrix.context import ContextBundle, ContextEntry
    from refmatrix.store import Entity

    calls: list = []

    class FakeDaemon:
        @staticmethod
        def ping(root):
            return True

        @staticmethod
        def call(root, op, args, timeout=None):
            calls.append((op, args))
            return {"ok": True}

    e = ContextEntry(
        entity=Entity(id=0, kind="code", name="m.py", path="/abs/m.py",
                      tldr=None, meta={}),
        linkage="grep")
    e.line, e.lines = 5, [5, 9]
    b = ContextBundle(ref="foo")
    b.groups["grep"] = [e]

    cli._maybe_learn_grep_backstop(tmp_path, FakeDaemon, "foo", b, True)
    assert calls and calls[0][0] == "learn_from_grep"
    hits = calls[0][1]["hits"]
    assert {"file": "/abs/m.py", "line": 5} in hits
    assert {"file": "/abs/m.py", "line": 9} in hits

    calls.clear()
    cli._maybe_learn_grep_backstop(tmp_path, FakeDaemon, "foo", b, False)  # off
    assert not calls
    cli._maybe_learn_grep_backstop(tmp_path, FakeDaemon, "foo",
                                   ContextBundle(ref="foo"), True)  # no grep grp
    assert not calls


def test_learn_grep_hits_marks_concept_and_entities_protected(tmp_path):
    """The whole point: learned-from-grep items are protected so prune_noise
    (which only reaps protected=0) can't undo the learning."""
    from refmatrix.daemon import _learn_grep_hits
    f = tmp_path / "x.py"
    f.write_text("def foo(): pass\n")
    s = Store(tmp_path / ".refmatrix")
    s.init()
    res = _learn_grep_hits(s, "foo", [{"file": str(f), "line": 1}], tmp_path)
    assert res["added"] == 1
    con = s._connect()
    cp = con.execute(
        "SELECT protected FROM entities WHERE name=? AND kind='concept'",
        ["query/foo"]).fetchone()
    assert cp and cp[0] == 1                       # concept protected
    ep = con.execute(
        "SELECT protected FROM entities WHERE kind='code' AND name='x.py'"
    ).fetchone()
    assert ep and ep[0] == 1                       # learned entity protected
    s.close()
