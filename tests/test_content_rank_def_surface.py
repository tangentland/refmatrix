"""M1: `content_rank` surfaces the DEFINITION file of a query symbol.

A symbol's own name is a `defines` concept on its file, not a `mentions` term,
so the file that DEFINES the symbol was absent from `content_rank` entirely —
the deeper root of the exact-symbol w=0 miss. content_rank now floors the def
entities into the result set so context's _floor_exact_defs can lift them.
"""
from __future__ import annotations

from refmatrix.store import Store


def _mk(tmp_path):
    s = Store(tmp_path / ".refmatrix")
    s.init()
    return s


def test_def_file_surfaces_with_no_mentions(tmp_path):
    """The audit case: a symbol with a `defines` edge but NO `mentions` edge
    still surfaces its def file."""
    s = _mk(tmp_path)
    deffile = s.upsert_entity("code", "store.py::set_flag_by_selector",
                              path="/store.py", tldr="def set_flag_by_selector")
    concept = s.upsert_entity("concept", "set_flag_by_selector")
    s.bulk_link([("defines", concept, deffile, 1.0)])

    hits = s.content_rank(["set_flag_by_selector"], kinds=["code"])
    ids = [eid for eid, _ in hits]
    assert deffile in ids, "def file absent from content_rank"
    score = dict(hits)[deffile]
    assert score > 0  # content_rank contract: score > 0
    s.close()


def test_real_mention_outranks_bare_def_floor(tmp_path):
    """Def floor must sit BELOW a genuine mention hit (NL behavior preserved)."""
    s = _mk(tmp_path)
    mlid_concept = s.upsert_entity("concept", "widget")
    mentioner = s.upsert_entity("code", "uses.py", path="/uses.py",
                                tldr="uses widget heavily")
    deffile = s.upsert_entity("code", "def.py::widget", path="/def.py",
                              tldr="def widget")
    # mentioner MENTIONS widget (tf=3); deffile DEFINES widget (no mention).
    s.bulk_link([
        ("mentions", mlid_concept, mentioner, 3.0),
        ("defines", mlid_concept, deffile, 1.0),
    ])
    hits = s.content_rank(["widget"], kinds=["code"])
    ids = [eid for eid, _ in hits]
    assert mentioner in ids and deffile in ids
    # real mention ranks first; bare def floor last.
    assert ids[0] == mentioner
    assert dict(hits)[mentioner] > dict(hits)[deffile]
    s.close()


def test_no_defines_no_surface(tmp_path):
    s = _mk(tmp_path)
    # concept exists but nothing defines or mentions it.
    s.upsert_entity("concept", "ghost")
    assert s.content_rank(["ghost"], kinds=["code"]) == []
    s.close()
