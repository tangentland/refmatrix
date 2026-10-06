"""Tests for the daemon-side `grep_indexed` and `learn_from_grep` ops
that back `rmx grep`. Exercised directly against a `Daemon` instance
seeded with an in-memory-ish DuckDB store, so the tests don't need to
spin up a socket server."""
from __future__ import annotations

import pytest

from refmatrix.daemon import Daemon, _op_grep_indexed, _op_learn_from_grep
from refmatrix.store import Store


@pytest.fixture
def daemon(tmp_path, monkeypatch):
    monkeypatch.delenv("RMX_BACKEND", raising=False)
    root = tmp_path / ".refmatrix"
    s = Store(root, backend="duckdb")
    s.init()
    d = Daemon(root)
    d.store = s
    d.corpus = tmp_path          # where _seed writes its REAL files
    yield d
    s.close()


def _seed(s: Store, corpus=None) -> dict:
    """Two concepts, three entities, evidence rows on multiple linkages.

    The files are REAL and the seeded lines REALLY contain the pattern
    (bug-074). This fixture used to point evidence at `/p/foo.py:12`, a path
    that does not exist — and once the read began verifying that a row's line
    holds the pattern, every row was dropped as unreadable. Production cannot
    produce an evidence row for a file that is not there, so the old fixture
    was asserting against a state the system cannot reach; the verification
    exposed it rather than broke it.
    """
    from pathlib import Path as _P

    corpus = _P(corpus) if corpus is not None else None
    parser = s.add_concept("parser", description="parses input")
    tokenizer = s.add_concept("tokenizer", description="splits text")

    def _write(rel: str, lines: dict) -> str:
        """`lines` maps 1-based line number -> text that must appear there."""
        p = (corpus / rel) if corpus else _P(rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        n = max(lines)
        body = [lines.get(i, f"filler {i}") for i in range(1, n + 1)]
        p.write_text("\n".join(body) + "\n")
        return str(p)

    foo_path = _write("src/foo.py", {12: "class parser:", 44: "# parser again"})
    lex_path = _write("src/lex.py", {7: "tokenizer = 1"})
    readme_path = _write("README.md", {3: "the parser docs"})

    foo = s.upsert_entity(kind="code", name="src/foo.py", path=foo_path)
    lex = s.upsert_entity(kind="code", name="src/lex.py", path=lex_path)
    readme = s.upsert_entity(kind="doc", name="README.md", path=readme_path)
    s.link("defines", parser, foo)
    s.link("mentions", parser, readme)
    s.link("defines", tokenizer, lex)
    s.add_evidence("defines", parser, foo, file=foo_path, line=12)
    s.add_evidence("defines", parser, foo, file=foo_path, line=44)
    s.add_evidence("mentions", parser, readme, file=readme_path, line=3)
    s.add_evidence("defines", tokenizer, lex, file=lex_path, line=7)
    return {"parser": parser, "tokenizer": tokenizer,
            "foo": foo, "lex": lex, "readme": readme,
            "foo_path": foo_path, "lex_path": lex_path,
            "readme_path": readme_path}


def test_grep_indexed_substring_finds_evidence(daemon):
    ids = _seed(daemon.store, daemon.corpus)
    out = _op_grep_indexed(daemon, {"pattern": "pars"})
    rows = out["rows"]
    # parser has 3 evidence rows (foo:12, foo:44, README:3); none for tokenizer
    assert len(rows) == 3
    concepts = {r["concept"] for r in rows}
    assert concepts == {"parser"}
    # Rows include path + line + linkage label
    lines = sorted((r["path"], r["line"], r["linkage"]) for r in rows)
    assert (ids["readme_path"], 3, "mentions") in lines
    assert (ids["foo_path"], 12, "defines") in lines
    assert (ids["foo_path"], 44, "defines") in lines


def test_grep_indexed_regex_anchors(daemon):
    _seed(daemon.store, daemon.corpus)
    # `^token` should match tokenizer but not parser
    # `verify=False`: these regexes are anchored against the concept NAME
    # (`^token`, `parser$`), and bug-074's verification applies the pattern to
    # the source LINE — correct for `rmx grep -E '^def '`, a category error for
    # a name anchor. The verified regex path is covered in
    # tests/test_grep_evidence_verified.py.
    rows = daemon.store.grep_evidence("^token", regex=True, verify=False)
    assert {r["concept"] for r in rows} == {"tokenizer"}
    rows = daemon.store.grep_evidence("parser$", regex=True, verify=False)
    assert {r["concept"] for r in rows} == {"parser"}


def test_grep_indexed_linkage_filter(daemon):
    _seed(daemon.store, daemon.corpus)
    out = _op_grep_indexed(daemon, {"pattern": "pars", "linkage": "mentions"})
    assert {r["linkage"] for r in out["rows"]} == {"mentions"}
    assert len(out["rows"]) == 1


def test_grep_indexed_kind_filter(daemon):
    ids = _seed(daemon.store, daemon.corpus)
    # pattern matches both parser concept and its evidence rows; filter to
    # entities with kind=doc -> only the README evidence row remains.
    out = _op_grep_indexed(daemon, {"pattern": "pars", "kind": "doc"})
    assert len(out["rows"]) == 1
    assert out["rows"][0]["path"] == ids["readme_path"]


def test_grep_indexed_limit(daemon):
    _seed(daemon.store, daemon.corpus)
    out = _op_grep_indexed(daemon, {"pattern": "pars", "limit": 2})
    assert len(out["rows"]) == 2


def test_grep_indexed_no_match_returns_empty(daemon):
    _seed(daemon.store, daemon.corpus)
    out = _op_grep_indexed(daemon, {"pattern": "nothing-here"})
    assert out["rows"] == []


def test_learn_from_grep_creates_concept_and_evidence(daemon, tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "src").mkdir()
    f1 = proj / "src" / "alpha.py"
    f2 = proj / "src" / "beta.py"
    # The hit lines must EXIST and contain the pattern: production's hits come
    # from a real grep result, so `foobar` is on those lines by construction
    # (bug-074). This fixture wrote one-line files and claimed hits at lines
    # 10/22/5, a state the floor cannot produce.
    f1.write_text("".join(
        "foobar here\n" if i in (10, 22) else f"filler {i}\n"
        for i in range(1, 23)))
    f2.write_text("".join(
        "foobar here\n" if i == 5 else f"filler {i}\n"
        for i in range(1, 6)))
    hits = [
        {"file": str(f1), "line": 10},
        {"file": str(f1), "line": 22},
        {"file": str(f2), "line": 5},
    ]
    out = _op_learn_from_grep(daemon, {
        "pattern": "foobar",
        "hits": hits,
        "project_root": str(proj),
    })
    # one entity per file = 2 added; concept created with namespaced name
    assert out["added"] == 2
    assert out["concept"] == "query/foobar"
    cid = out["concept_id"]
    assert isinstance(cid, int) and cid > 0

    # Subsequent lookup must surface the promoted concept's evidence.
    # `verify=False`: the probe searches for the CONCEPT NAME `query/foobar`,
    # which is not the text on the line (the line holds `foobar`). Asking
    # "did the learn land?" is a different question from "give me grep-shaped
    # hits", and bug-074's verification answers the second.
    rows = daemon.store.grep_evidence("query/foobar", verify=False)
    assert {r["concept"] for r in rows} == {"query/foobar"}
    # 3 evidence rows total (two on alpha, one on beta)
    assert len(rows) == 3
    pairs = sorted((r["path"], r["line"]) for r in rows)
    assert pairs == sorted([
        (str(f1), 10), (str(f1), 22), (str(f2), 5),
    ])
    # All under the `mentions` linkage by construction.
    assert {r["linkage"] for r in rows} == {"mentions"}


def test_learn_from_grep_noop_on_empty(daemon):
    out = _op_learn_from_grep(daemon, {"pattern": "x", "hits": []})
    assert out == {"added": 0}
    # No concept was created.
    follow = _op_grep_indexed(daemon, {"pattern": "query/x"})
    assert follow["rows"] == []


def test_learn_from_grep_classifies_kind_from_suffix(daemon, tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    code_file = proj / "thing.py"
    doc_file = proj / "NOTES.md"
    code_file.write_text("")
    doc_file.write_text("")
    _op_learn_from_grep(daemon, {
        "pattern": "kindcheck",
        "hits": [
            {"file": str(code_file), "line": 1},
            {"file": str(doc_file), "line": 2},
        ],
        "project_root": str(proj),
    })
    # Inspect entities directly: code suffix -> code, otherwise doc.
    py = daemon.store.get_entity("code", "thing.py")
    md = daemon.store.get_entity("doc", "NOTES.md")
    assert py is not None
    assert md is not None


def test_learn_from_grep_uses_relative_path_for_entity_name(daemon, tmp_path):
    proj = tmp_path / "proj"
    sub = proj / "a" / "b"
    sub.mkdir(parents=True)
    f = sub / "deep.py"
    f.write_text("")
    _op_learn_from_grep(daemon, {
        "pattern": "relcheck",
        "hits": [{"file": str(f), "line": 1}],
        "project_root": str(proj),
    })
    # Entity name should be the posix-relative path, not the absolute one.
    ent = daemon.store.get_entity("code", "a/b/deep.py")
    assert ent is not None
    assert ent.path == str(f)
