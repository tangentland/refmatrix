"""bug-067: a learned `query/PATTERN` must be reachable by the query that made it.

`rmx grep` tells the user "future searches hit the index". Measured over this
project's own 121 repeated grep patterns
(`workflow/review-output/grep-reachability-repeated.json`, 2026-10-06), that was
true for 24 of the 76 patterns that fell to the floor and taught something —
and for **0 of 18 multi-word patterns**.

MECHANISM, proven by direct SQL rather than inferred. `store.add_concept` runs
`_concept_variants`, which writes the canonical underscore row PLUS space and
dash ALIAS rows as separate entities, and `_learn_grep_hits` attaches all its
evidence to the canonical id:

    query/roaring bitmap    evidence=0      <- the literal the next grep looks for
    query/roaring-bitmap    evidence=0
    query/roaring_bitmap    evidence=10     <- where the evidence actually went

The read then matched `c.name ILIKE '%<literal>%'` and JOINed
`linkage_evidence`, so a pattern whose literal form is an alias found a concept
with nothing attached and fell through to the tool floor — forever, on every
repeat. `learning_enabled` worked only because its literal IS its canonical
form.

The fix is the read side: `identifier.canonicalize_name` exists for exactly this
boundary ("Used at the query INPUT boundary"), the query/context/neighbors paths
already use `expand_name_variants`, and the grep lookup was never wired to it.
The same SQL existed in THREE copies (the daemon op with `regexp_matches`, the
CLI's direct branch and the CLI's replica branch with `~` — already divergent),
so the predicate is now built once in `Store.grep_evidence` and the copies
delegate. bug-058/059/060 were all one rule implemented per path; this is the
same family and it does not get a fourth copy.
"""
from __future__ import annotations

import shutil

import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod
from refmatrix.daemon import Daemon, _op_grep_indexed, _op_learn_from_grep
from refmatrix.store import Store


@pytest.fixture
def daemon(tmp_path, monkeypatch):
    monkeypatch.delenv("RMX_BACKEND", raising=False)
    monkeypatch.delenv("RMX_LEARN", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    root = tmp_path / "proj" / ".refmatrix"
    root.parent.mkdir()
    s = Store(root, backend="duckdb")
    s.init()
    d = Daemon(root)
    d.store = s
    d._log = lambda m: None
    yield d
    s.close()


def _corpus(proj):
    f = proj / "sample.py"
    f.write_text("roaring bitmap lives here\n" * 2 + "bug-008 reference\n"
                 "project.scripts entry\n")
    return f


def _teach(d, pattern: str, f) -> dict:
    return _op_learn_from_grep(d, {
        "pattern": pattern,
        "hits": [{"file": str(f), "line": 1}, {"file": str(f), "line": 2}],
        "project_root": str(f.parent),
    })


def _pairs(rows) -> set:
    return {(r["path"], r["line"]) for r in rows}


# ---- the defect, one case per name shape --------------------------------

@pytest.mark.parametrize("pattern", [
    "roaring bitmap",          # multi-word: 0 of 18 of these ever worked
    "def _open_read_store",    # the most-repeated pattern in the real log
    "bug-008",                 # dash: the alias row is the literal one
    "project.scripts",         # dot
    "scan-prompt",
])
def test_a_learned_pattern_is_reachable_by_its_own_query(daemon, pattern):
    f = _corpus(daemon.root.parent)
    taught = _teach(daemon, pattern, f)
    assert taught["added"] >= 1, taught

    rows = _op_grep_indexed(daemon, {"pattern": pattern})["rows"]

    assert rows, (f"{pattern!r} taught {taught['added']} file(s) as "
                  f"{taught['concept']!r} and the same query cannot find it")
    assert all("query/" in r["concept"] for r in rows), rows


def test_the_literal_form_still_matches_when_it_is_the_canonical_one(daemon):
    """The case that always worked must keep working — this is the control for
    every assertion above."""
    f = _corpus(daemon.root.parent)
    _teach(daemon, "learning_enabled", f)

    rows = _op_grep_indexed(daemon, {"pattern": "learning_enabled"})["rows"]

    assert rows


def test_the_alias_rows_do_not_multiply_the_answer(daemon):
    """A canonical row and two alias rows share a canonical name. If the fix
    matches all three AND they all carried evidence, every hit would be
    returned three times — which is bug-058's "1000 rows covering 100 lines"
    failure wearing a different hat."""
    f = _corpus(daemon.root.parent)
    _teach(daemon, "roaring bitmap", f)

    rows = _op_grep_indexed(daemon, {"pattern": "roaring bitmap"})["rows"]

    assert len(rows) == len(_pairs(rows)), rows


# ---- one predicate, not one per read path -------------------------------

def test_the_op_and_the_store_helper_agree(daemon):
    f = _corpus(daemon.root.parent)
    _teach(daemon, "roaring bitmap", f)

    op_rows = _op_grep_indexed(daemon, {"pattern": "roaring bitmap"})["rows"]
    store_rows = daemon.store.grep_evidence("roaring bitmap")

    assert _pairs(op_rows) == _pairs(store_rows)


@pytest.mark.parametrize("layout", ["replica", "direct"])
def test_both_cli_read_paths_find_the_learned_concept(daemon, monkeypatch, layout):
    """`_grep_run_direct` (replica) and `_grep_run` (daemon/direct) each had
    their OWN copy of this SQL. Both must answer from the index after a teach."""
    proj = daemon.root.parent
    f = _corpus(proj)
    _teach(daemon, "roaring bitmap", f)
    daemon.store.close()
    if layout == "direct":
        legacy = daemon.root / "catalog.duckdb"
        if legacy.exists():
            shutil.move(str(legacy), str(daemon.root / "catalog.A.duckdb"))
        (daemon.root / "active").write_text("A\n")
    monkeypatch.setattr("refmatrix.daemon.ping", lambda *a, **k: False)
    monkeypatch.chdir(proj)

    res = CliRunner().invoke(cli_mod.main, ["grep", "--no-fallback", "--",
                                            "roaring bitmap"])

    assert res.exit_code == 0, f"{layout}: fell through to no-indexed-matches\n{res.output}"
    assert "sample.py" in res.output
    daemon.store = Store(daemon.root, backend="duckdb")


# ---- the filters and the regex mode are unchanged -----------------------

def test_regex_mode_is_not_canonicalized(daemon):
    """A regex is not an identifier. Canonicalizing `^quer` would change what
    the user asked for, so the regex path matches names as given."""
    f = _corpus(daemon.root.parent)
    _teach(daemon, "roaring bitmap", f)

    hit = _op_grep_indexed(daemon, {"pattern": "^query/roaring_bitmap$",
                                    "regex": True})["rows"]
    miss = _op_grep_indexed(daemon, {"pattern": "^nothing_matches_this$",
                                     "regex": True})["rows"]

    assert hit
    assert miss == []


def test_the_linkage_and_kind_filters_still_apply(daemon):
    f = _corpus(daemon.root.parent)
    _teach(daemon, "roaring bitmap", f)

    assert _op_grep_indexed(daemon, {"pattern": "roaring bitmap",
                                     "linkage": "mentions"})["rows"]
    assert _op_grep_indexed(daemon, {"pattern": "roaring bitmap",
                                     "linkage": "defines"})["rows"] == []
    assert _op_grep_indexed(daemon, {"pattern": "roaring bitmap",
                                     "kind": "code"})["rows"]
    assert _op_grep_indexed(daemon, {"pattern": "roaring bitmap",
                                     "kind": "doc"})["rows"] == []


def test_the_limit_still_caps(daemon):
    f = _corpus(daemon.root.parent)
    _teach(daemon, "roaring bitmap", f)

    assert len(_op_grep_indexed(daemon, {"pattern": "roaring bitmap",
                                         "limit": 1})["rows"]) == 1


def test_an_unrelated_pattern_is_not_dragged_in_by_canonicalization(daemon):
    """Canonicalizing widens the net, and a net that is too wide is its own
    wrong answer: `roaring` and `bitmap` are parts of the canonical name, but a
    search for an unrelated word must still miss."""
    f = _corpus(daemon.root.parent)
    _teach(daemon, "roaring bitmap", f)

    assert _op_grep_indexed(daemon, {"pattern": "elephant"})["rows"] == []
    assert _op_grep_indexed(daemon, {"pattern": "bitmap roaring"})["rows"] == []


# ---- bug-070: the canonical predicate is a SPELLING bridge, not a family ----
#
# bug-067's fix matched `canonical_name ILIKE '%<canon>%'`, and on a short
# punctuated pattern that substring joins a whole family: measured on a real
# src+docs store, `rmx grep 'error:'` drew 74 evidence rows from 26 DISTINCT
# concepts — `keyword/errors`, `keyword/eoferror`, `keyword/brokenpipeerror` —
# when the caller asked for `error:`
# (`docs/measurements/grep-canonical-breadth.md`, arm A).
#
# Two narrower predicates were measured and rejected before this one:
#   * plain equality on `canonical_name` lost EVERY multi-word pattern (10 of
#     16 patterns stopped getting an index answer), because concept canonical
#     names are namespace-prefixed: `keyword_roaring_bitmap`, not
#     `roaring_bitmap`;
#   * anchoring on `c.name`'s post-slash tail lost `replica bundle`, whose
#     concept is `keyword/_replica_bundle` — a leading underscore the name tail
#     carries and the canonical form folds away.
# The shipped predicate anchors on the canonical name's TRAILING SEGMENT, which
# costs nothing on the gain side: reachability over the same 132-pattern
# workload is identical on every metric (arm D).


def _concept_names(d, pattern: str) -> set:
    return {r["concept"] for r in _op_grep_indexed(d, {"pattern": pattern})["rows"]}


def test_a_punctuated_pattern_does_not_drag_in_the_whole_family(daemon):
    """THE bug-070 case. `error:` canonicalizes to `error`; as a substring that
    matched every `error`-ish concept name."""
    s = daemon.store
    f = _corpus(daemon.root.parent)
    for name in ("keyword/error", "keyword/errors", "keyword/eoferror",
                 "keyword/brokenpipeerror", "keyword/context_error"):
        cid = s.add_concept(name)
        eid = s.upsert_entity("code", f"{name}-site", path=str(f))
        s.link("mentions", cid, eid)
        s.add_evidence("mentions", cid, eid, file=str(f), line=1)

    got = _concept_names(daemon, "error:")
    assert "keyword/error" in got, got
    for family in ("keyword/errors", "keyword/eoferror",
                   "keyword/brokenpipeerror"):
        assert family not in got, (family, got)


def test_the_spelling_bridge_survives_the_narrowing(daemon):
    """The reach bug-067 bought, and the reason plain equality was rejected:
    the concept is `keyword/roaring_bitmap`, whose canonical name carries the
    `keyword_` namespace prefix."""
    s = daemon.store
    f = _corpus(daemon.root.parent)
    cid = s.add_concept("keyword/roaring_bitmap")
    eid = s.upsert_entity("code", "bitmap-site", path=str(f))
    s.link("mentions", cid, eid)
    s.add_evidence("mentions", cid, eid, file=str(f), line=1)

    assert _concept_names(daemon, "roaring bitmap"), "the bridge is gone"
    assert _concept_names(daemon, "roaring-bitmap"), "the dash spelling is gone"


def test_a_leading_underscore_identifier_is_still_reachable(daemon):
    """`replica bundle` -> `keyword/_replica_bundle`. The name-tail predicate
    lost this one; the canonical form folds the leading underscore away, which
    is why the anchor is on `canonical_name`."""
    s = daemon.store
    f = _corpus(daemon.root.parent)
    cid = s.add_concept("keyword/_replica_bundle")
    eid = s.upsert_entity("code", "rb-site", path=str(f))
    s.link("mentions", cid, eid)
    s.add_evidence("mentions", cid, eid, file=str(f), line=1)

    assert _concept_names(daemon, "replica bundle"), "the leading-underscore \
identifier lost its index answer"


def test_the_underscore_in_the_canonical_form_is_not_a_like_wildcard(daemon):
    """`_` is a single-character wildcard in SQL LIKE, so an unescaped
    `%_build_context` would also match `keyword_buildXcontext`. Escaped."""
    s = daemon.store
    f = _corpus(daemon.root.parent)
    cid = s.add_concept("keyword/buildXcontext")
    eid = s.upsert_entity("code", "x-site", path=str(f))
    s.link("mentions", cid, eid)
    s.add_evidence("mentions", cid, eid, file=str(f), line=1)

    assert "keyword/buildXcontext" not in _concept_names(daemon, "build context")


def test_bug_067s_own_case_still_holds_after_the_narrowing(daemon):
    """The regression guard that matters most: the learned `query/<canon>` row
    is where `_learn_grep_hits` attaches evidence, and narrowing the predicate
    must not put it back out of reach."""
    f = _corpus(daemon.root.parent)
    _teach(daemon, "roaring bitmap", f)
    rows = _op_grep_indexed(daemon, {"pattern": "roaring bitmap"})["rows"]
    assert rows, "bug-067 regressed: the learned concept is unreachable again"
    assert any("query/" in r["concept"] for r in rows), rows


def test_the_name_predicate_breadth_is_deliberately_unchanged(daemon):
    """What this fix does NOT do, pinned so nobody reads it as a wider claim.
    `ERROR` draws the family through `c.name ILIKE '%ERROR%'` — the pre-bug-067
    contract, measured as unchanged at 74 rows / 26 concepts (arms A and D) —
    and narrowing THAT is a separate decision with its own trade."""
    s = daemon.store
    f = _corpus(daemon.root.parent)
    for name in ("keyword/error", "keyword/errors", "keyword/eoferror"):
        cid = s.add_concept(name)
        eid = s.upsert_entity("code", f"{name}-site", path=str(f))
        s.link("mentions", cid, eid)
        s.add_evidence("mentions", cid, eid, file=str(f), line=1)

    got = _concept_names(daemon, "error")
    assert {"keyword/error", "keyword/errors", "keyword/eoferror"} <= got, got
