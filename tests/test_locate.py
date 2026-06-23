"""`rmx locate` — find full filesystem paths by filename and/or keywords.

Two layers under test:
- `federated_locate` merge/rank/filter logic (per-project results faked so the
  test needs no live daemons).
- the CLI's positional term classification (filename-looking token vs keyword)
  and `-n` plumbing, with `federated_locate` stubbed to capture its args.
"""
from __future__ import annotations

from click.testing import CliRunner

import refmatrix.search as search
from refmatrix.cli import main


def _fake_roots(monkeypatch, per_project: dict):
    """Wire discovery/ping/_locate_one_project so federated_locate runs over
    `per_project` = {root_str: {path: hitdict}} without touching daemons."""
    roots = list(per_project)
    monkeypatch.setattr(search.discovery, "discover_roots",
                        lambda: roots)
    monkeypatch.setattr(search.daemon_mod, "ping", lambda r: True)

    def fake_one(root, filename, keywords):
        return per_project.get(root, {})

    monkeypatch.setattr(search, "_locate_one_project", fake_one)


def _hit(path, project, score, why, name_hit=False):
    return {"path": path, "project": project, "root": "/r",
            "score": score, "name_hit": name_hit, "why": set(why)}


def test_keyword_ranking_orders_by_score_desc(monkeypatch):
    _fake_roots(monkeypatch, {
        "A": {
            "/p/low.py": _hit("/p/low.py", "A", 1.0, ["ingest"]),
            "/p/high.py": _hit("/p/high.py", "A", 9.0, ["ingest", "semantic"]),
        },
    })
    res = search.federated_locate(None, ["ingest", "semantic"], limit=10)
    paths = [r["path"] for r in res["results"]]
    assert paths == ["/p/high.py", "/p/low.py"]
    assert res["results"][0]["why"] == ["ingest", "semantic"]


def test_filename_is_a_hard_filter(monkeypatch):
    # Only name_hit rows survive when a filename is given, regardless of score.
    _fake_roots(monkeypatch, {
        "A": {
            "/p/cli.py": _hit("/p/cli.py", "A", 0.0, ["filename=cli.py"],
                              name_hit=True),
            "/p/other.py": _hit("/p/other.py", "A", 99.0, ["kw"],
                                name_hit=False),
        },
    })
    res = search.federated_locate("cli.py", ["kw"], limit=10)
    paths = [r["path"] for r in res["results"]]
    assert paths == ["/p/cli.py"]


def test_filename_plus_keyword_ranks_name_hits_by_relevance(monkeypatch):
    _fake_roots(monkeypatch, {
        "A": {
            "/a/store.py": _hit("/a/store.py", "A", 5.0, ["partition"],
                                name_hit=True),
            "/b/store.py": _hit("/b/store.py", "B", 0.0, [], name_hit=True),
        },
    })
    res = search.federated_locate("store.py", ["partition"], limit=10)
    paths = [r["path"] for r in res["results"]]
    assert paths == ["/a/store.py", "/b/store.py"]  # higher score leads


def test_cross_store_paths_merge_and_sum(monkeypatch):
    # Same path surfaced by two stores -> scores add, single row out.
    _fake_roots(monkeypatch, {
        "A": {"/shared.py": _hit("/shared.py", "A", 2.0, ["x"])},
        "B": {"/shared.py": _hit("/shared.py", "B", 3.0, ["y"])},
    })
    res = search.federated_locate(None, ["x", "y"], limit=10)
    assert len(res["results"]) == 1
    assert res["results"][0]["score"] == 5.0
    assert res["results"][0]["why"] == ["x", "y"]


def test_limit_caps_results(monkeypatch):
    _fake_roots(monkeypatch, {
        "A": {f"/p/f{i}.py": _hit(f"/p/f{i}.py", "A", float(i), ["k"])
              for i in range(20)},
    })
    res = search.federated_locate(None, ["k"], limit=3)
    assert len(res["results"]) == 3
    assert res["results"][0]["path"] == "/p/f19.py"  # highest score first


# ---- CLI term classification ----------------------------------------------


def _capture(monkeypatch):
    seen = {}

    def stub(filename, keywords, *, limit):
        seen["filename"] = filename
        seen["keywords"] = keywords
        seen["limit"] = limit
        return {"results": []}

    monkeypatch.setattr("refmatrix.search.federated_locate", stub)
    return seen


def test_cli_classifies_filename_token(monkeypatch):
    seen = _capture(monkeypatch)
    r = CliRunner().invoke(main, ["locate", "cli.py", "ingest", "-n", "7"])
    assert r.exit_code == 0, r.output
    assert seen["filename"] == "cli.py"
    assert seen["keywords"] == ["ingest"]
    assert seen["limit"] == 7


def test_cli_explicit_file_flag_and_path_basename(monkeypatch):
    seen = _capture(monkeypatch)
    r = CliRunner().invoke(main, ["locate", "-f", "src/pkg/store.py", "concept"])
    assert r.exit_code == 0, r.output
    assert seen["filename"] == "store.py"  # path reduced to basename
    assert seen["keywords"] == ["concept"]


def test_cli_requires_some_input(monkeypatch):
    _capture(monkeypatch)
    r = CliRunner().invoke(main, ["locate"])
    assert r.exit_code != 0
    assert "filename and/or keywords" in r.output
