"""`rmx context "<natural language phrase>"` — the three defects a prose corpus
exposed that a code corpus never did.

Measured before these fixes, on 90 questions over 1307 GMD-ingested chat
sessions (eval/memaware): `context` scored 0.007 MRR@20 while `memory recall`
scored 0.180 over the SAME store. It was not a ranking difference — the surface
could not reach the index for this input shape at all.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from refmatrix.context import _grep_backstop, _ref_terms, build_context
from refmatrix.ingest_gmd import ingest_gmd_paths
from refmatrix.store import Store


# ─── _ref_terms: stopwords ────────────────────────────────────────────────

def test_multi_word_ref_drops_function_words():
    terms = [t.lower() for t in _ref_terms(
        "Do you know if my old sneakers are still in that spot?")]
    assert "sneakers" in terms
    for junk in ("do", "you", "if", "my", "are", "in", "that"):
        assert junk not in terms


def test_single_token_ref_is_never_stoplisted():
    """The ref IS the query when there is only one token — `context "the"`
    must still look for `the`, not fall back to an empty term list."""
    assert [t.lower() for t in _ref_terms("the")] == ["the"]


def test_all_stopword_ref_keeps_its_terms():
    """Filtering to nothing would silently turn the query into a no-op."""
    assert _ref_terms("are you the one") != []


def test_identifier_ref_survives_intact():
    assert _ref_terms("fov_wedge_polygon") == ["fov_wedge_polygon"]


# ─── _grep_backstop: word boundaries ──────────────────────────────────────

@pytest.fixture
def tree(tmp_path):
    (tmp_path / "notes.md").write_text(
        "tags: [memaware, session]\nthe user bought sneakers\n", encoding="utf8")
    return tmp_path


def test_substring_match_is_the_default(tree):
    """Identifier refs depend on it: `fov_wedge` must find
    `fov_wedge_polygon`."""
    hits = _grep_backstop(["are"], tree, limit=5)
    assert hits, "substring mode should match 'are' inside 'memaware'"


def test_whole_word_rejects_the_substring(tree):
    """A prose ref carrying a short function word used to crown whichever file
    repeated the commonest fragment — live, `tags: [memaw«are», session]`
    scored 191 and won."""
    assert _grep_backstop(["are"], tree, limit=5, whole_word=True) == []
    assert _grep_backstop(["sneakers"], tree, limit=5, whole_word=True)


# ─── content_rank reaching GMD body text ──────────────────────────────────

# NOTE: the doc id deliberately avoids a `session-` prefix — `_is_session_card`
# treats those as transient activity logs and filters them out of content hits,
# which would mask the behaviour under test here.
GMD_DOC = """---
gmd: "0.1"
id: chat-alpha
title: "Chat alpha"
tags: [testing]
metadata:
  node_type: memory
  type: test/session
---

# Chat alpha {#root}

User: I need to organize my closet and get rid of some old sneakers that are
taking up space on the shoe rack.
"""


@pytest.fixture
def gmd_store(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "chat-alpha.md").write_text(GMD_DOC, encoding="utf8")
    s = Store(tmp_path / ".refmatrix")
    s.init()
    ingest_gmd_paths(s, [docs / "chat-alpha.md"], as_memory=True,
                     memory_mtype_default="test/session")
    yield s
    s.close()


def test_body_terms_land_on_the_anchored_node_and_score_for_the_memory(gmd_store):
    """Pins the graph shape the fix is built around. A GMD doc yields TWO
    entities and the body term-frequency sweep hangs `mentions` on the node.
    Until bug-300 this test pinned the CONSEQUENCE too: ranking code/doc/memory
    returned [] for a body word, because a memory's own `mentions` are its
    title and tag words. bug-300 R1 (L193 option (a)): when `kinds` includes
    `memory`, the memory's block postings are credited to the memory, so the
    same call now returns the memory -- and never its block node."""
    node = gmd_store.get_entity("concept", "chat-alpha#root")
    assert node is not None
    hits = gmd_store.content_rank(["sneakers"], kinds=["concept"], limit=10)
    assert node.id in [eid for eid, _ in hits]
    mem = gmd_store.get_entity("memory", "chat-alpha")
    assert mem is not None
    got = gmd_store.content_rank(["sneakers"], kinds=["code", "doc", "memory"], limit=10)
    assert [eid for eid, _ in got] == [mem.id], got


# ─── bug-300: a memory's BODY is searchable by content_rank ───────────────
#
# Fixture shape = the LongMemEval shape that made `memory recall --fuse` a no-op (T0.6,
# 2026-11-24): memories TITLED BY AN ID, so their own `mentions` are `session` + id tokens and
# every body word sits on a `<memory-id>#<anchor>` block node (kind=concept). R0 (live and
# LongMemEval copies, workflow/review-output/b300-r0.md): the tie that is total is the block
# NAME prefix (= `meta.doc`); a `part-of` walk is not (GMD `rel: part-of` lines share the
# linkage: 4 live blocks are part-of a FOREIGN memory), and a SQL `LIKE '<id>#%'` treats the
# `_` in ids like `s0042_1` as a wildcard. Both wrong joins have a planted case below.
# Query terms are punctuation-free so bug-301 (content_terms keeps `work?`) cannot interact.

def _gmd(doc_id: str, sections, *, preamble: str = "", rels=(), node_type="memory") -> str:
    """A GMD file titled by its id. `sections` = [(heading, anchor, text)]; `preamble` is body
    text under the H1 (it lands on `<id>#root`); `rels` are `rel:` lines on the root."""
    rel_lines = "".join(f"rel: {r}\n" for r in rels)
    body = "\n\n".join(f"## {t} {{#{a}}}\n\n{txt}" for t, a, txt in sections)
    return (f'---\ngmd: "0.1"\nid: {doc_id}\ntitle: "Session {doc_id}"\ntags: [session]\n'
            f"metadata:\n  node_type: {node_type}\n  type: test/session\n---\n\n"
            f"# Session {doc_id} {{#root}}\n\n{preamble}\n\n{rel_lines}\n{body}\n")


def _headingless(doc_id: str, text: str) -> str:
    """A memory with NO heading: its body lands on the memory entity itself (the synthetic
    `__root__` node IS the memory) -- the 179 live memories without block nodes (R0)."""
    return (f'---\ngmd: "0.1"\nid: {doc_id}\ntitle: "Session {doc_id}"\ntags: [session]\n'
            f"metadata:\n  node_type: memory\n  type: test/session\n---\n\n{text}\n")


# Ingest ORDER matters for one case: `s0061_1` (one `glacier`) gets a LOWER entity id than
# `s0060_1` (two), so a max-per-block join ties them and the id tie-break puts s0061 first.
_MEMORIES = [
    ("s0061_1", _gmd("s0061_1", [
        ("Ice", "ice", "The glacier walk crossed a wide blue field of old snow."),
        ("Rock", "rock", "The moraine walk crossed a wide grey field of old stone.")])),
    ("s0060_1", _gmd("s0060_1", [
        ("Ice", "ice", "The glacier walk crossed a wide blue field of old snow."),
        ("Rock", "rock", "The glacier edge crossed a wide grey field of old stone.")])),
    ("s0042_1", _gmd("s0042_1", [
        ("Garden", "garden", "The tomatoes in the raised bed need staking before the storm."),
        ("Travel", "travel", "My daily commute by train takes forty minutes.")])),
    ("s0043_1", _gmd("s0043_1", [
        ("Kitchen", "kitchen", "The kettle is blue and the toaster burns bread.")])),
    # s0050_1's root block is `part-of` s0051_1 by a GMD rel: line (the live shape R0 found).
    ("s0050_1", _gmd("s0050_1", [("Coast", "coast", "The lighthouse keeper logs every ship.")],
                     rels=["part-of -> [[s0051_1]]"])),
    ("s0051_1", _gmd("s0051_1", [("Hills", "hills", "The shepherd counts sheep at dusk.")])),
    ("s0070_1", _headingless("s0070_1", "A smooth pebble from the river sits on the desk.")),
]
# A DOC (not a memory) whose id matches `s0042_1` under LIKE (`_` = any char): its block holds
# `ferry`, a word no memory has.
_LIKE_TWIN = _gmd("s0042x1", [("Harbour", "harbour", "The ferry leaves the harbour at noon.")],
                  node_type="doc")


@pytest.fixture
def id_titled(tmp_path):
    """A real store, real GMD ingest (`ingest_gmd_paths(as_memory=True)`, the bridge's path),
    no mocks. Yields `(store, ids)` with `ids[name] = entity id` for every memory."""
    import rmx_sandbox
    base = Path(rmx_sandbox.short_root("b300c-"))
    mem_dir, doc_dir = base / "memory", base / "docs"
    mem_dir.mkdir()
    doc_dir.mkdir()
    s = Store(base / ".refmatrix")
    s.init()
    try:
        for name, text in _MEMORIES:            # one call per file: the ingest order is the id order
            (mem_dir / f"{name}.md").write_text(text, encoding="utf8")
        ingest_gmd_paths(s, [mem_dir / f"{n}.md" for n, _ in _MEMORIES], as_memory=True,
                         memory_mtype_default="test/session")
        (doc_dir / "s0042x1.md").write_text(_LIKE_TWIN, encoding="utf8")
        ingest_gmd_paths(s, [doc_dir / "s0042x1.md"])
        ids = {n: s.get_entity("memory", n).id for n, _ in _MEMORIES}
        assert s.get_entity("doc", "s0042x1") is not None
        # An ORPHAN block: the shape R0 found live (3 blocks of
        # `impression_bsd_isolation_drops_the_suite`, memory entity and file gone; logged as
        # its own bug by the lead). Planted directly: a gmd_node concept whose `meta.doc` names
        # a memory that does not exist, carrying the only `zeppelin`.
        orphan = s.upsert_entity(
            kind="concept", name="s0099_1#gone", path=str(mem_dir / "s0099_1.md"),
            tldr="Gone\n\nThe zeppelin hangar", meta={"doc": "s0099_1", "anchor": "gone",
                                                     "level": 2, "gmd_node": True})
        s.link("mentions", s.upsert_entity(kind="concept", name="zeppelin"), orphan, 1.0)
        assert s.get_entity("memory", "s0099_1") is None
        yield s, ids
    finally:
        s.close()
        rmx_sandbox.remove_tree(base)


def _named(s: Store, hits) -> list:
    return [(s.get_entity_by_id(eid).kind, s.get_entity_by_id(eid).name) for eid, _ in hits]


@pytest.mark.parametrize("term,memory", [
    ("commute", "s0042_1"),     # AC-1: a word only in the #travel block
    ("tomatoes", "s0042_1"),    # another block of the same memory
    ("kettle", "s0043_1"),
    ("pebble", "s0070_1"),      # guard: a heading-less memory still scores from its own postings
])
def test_a_body_word_finds_its_id_titled_memory(id_titled, term, memory):
    """bug-300 AC-1: `content_rank([term], kinds=["memory"])` returns the memory whose BODY
    holds the term. RED at base for every block-held term: the leg read only the memory's own
    title/tag `mentions` and returned []."""
    s, _ids = id_titled
    hits = s.content_rank([term], kinds=["memory"], limit=10)
    assert _named(s, hits) == [("memory", memory)], _named(s, hits)


def test_memory_kind_returns_each_memory_once_and_no_block_node(id_titled):
    """bug-300 R1: block postings are CREDITED to their memory; a block node is never a hit of
    its own under `kinds=["memory"]`, and a memory reached through two blocks is one row. (AC-5
    mutation "return block nodes as hits" turns this red.)"""
    s, ids = id_titled
    hits = s.content_rank(["commute", "tomatoes", "kettle"], kinds=["memory"], limit=50)
    named = _named(s, hits)
    assert {k for k, _ in named} == {"memory"}, named
    got = [eid for eid, _ in hits]
    assert len(got) == len(set(got)), named
    assert set(got) == {ids["s0042_1"], ids["s0043_1"]}, named
    # s0042_1 matches two of the three terms (two blocks), s0043_1 one: one document each,
    # so coverage puts s0042_1 first.
    assert got[0] == ids["s0042_1"], named


@pytest.mark.parametrize("term,expect", [
    ("lighthouse", ["s0050_1"]),   # NOT s0051_1, which s0050_1#root is `part-of` by a rel: line
    ("ferry", []),                 # NOT s0042_1: `s0042x1#harbour` is a DOC's block
    ("zeppelin", []),              # an orphan block (its memory is gone) is not a hit
])
def test_block_credit_follows_the_block_name_not_part_of_or_a_like_pattern(
        id_titled, term, expect):
    """R0 + the lead's ruling: a block is credited to the memory named by its NAME prefix
    (`split_part(name, '#', 1)`, which equals `meta.doc` on every block of both stores
    measured), never through `part-of`. A `part-of` walk credits s0050_1's body to s0051_1,
    the memory its GMD `rel: part-of` line names; a `LIKE 's0042_1#%'` join credits the doc
    `s0042x1`'s block to memory `s0042_1`; an orphan block (no memory of that name) maps to
    nothing and is not returned on its own."""
    s, _ids = id_titled
    hits = s.content_rank([term], kinds=["memory"], limit=10)
    assert [n for _, n in _named(s, hits)] == expect, _named(s, hits)


def test_one_memory_is_one_bm25_document_across_its_blocks(id_titled):
    """R1: "the block postings and the memory's own postings are one document for BM25's tf
    and length". s0060_1 says `glacier` in two blocks, s0061_1 in one; the files are the same
    length, so tf decides: s0060_1 first. A max-over-blocks join ties them, and the entity-id
    tie-break then puts s0061_1 (ingested first) on top."""
    s, ids = id_titled
    hits = s.content_rank(["glacier"], kinds=["memory"], limit=10)
    assert [eid for eid, _ in hits] == [ids["s0060_1"], ids["s0061_1"]], _named(s, hits)
    assert hits[0][1] > hits[1][1], hits


# ─── bug-300 R2 / AC-3: a caller over code and docs ranks exactly as before ──
#
# The pin was taken at base (da6af511) and must hold after the fix. The corpus has GMD DOCS
# with `<doc-id>#<anchor>` blocks (the same name shape as a memory's), so a block join that is
# not restricted to memories -- crediting a doc's blocks to the doc -- moves these numbers.

_CODE = '''"""Harbour schedule helpers."""


def ferry_departures(harbour):
    """Return the ferry departures for a harbour, earliest first."""
    return sorted(harbour.schedule)
'''
_DOCS = {
    "harbour-guide": _gmd("harbour-guide", [
        ("Ferries", "ferries", "The ferry schedule lists every departure from the harbour."),
        ("Tides", "tides", "Tide tables decide when the ferry can dock at low water.")],
        node_type="doc"),
    "port-notes": _gmd("port-notes", [
        ("Cargo", "cargo", "Cargo ships share the harbour with the morning ferry."),
        ("Weather", "weather", "Storms cancel the schedule twice a winter.")],
        node_type="doc"),
}
_PIN_QUERY = "ferry schedule harbour departures"
# (kind, name, round(score, 9)) of build_context's content group, taken at base (da6af511).
_PIN_CONTEXT: list = [
    ("concept", "harbour-guide#ferries", 3.080788232),
    ("code", "harbour.py::ferry_departures", 1.751547171),
    ("concept", "port-notes#cargo", 0.631658671),
    ("concept", "plain.md#_h1", 0.619939586),
    ("concept", "port-notes#weather", 0.414953629),
    ("concept", "harbour-guide#tides", 0.204990641),
]
# content_rank under context's own kinds, same base.
_PIN_RANK: list = [
    ("concept", "harbour-guide#ferries", 2.053858822),
    ("code", "harbour.py::ferry_departures", 1.751547171),
    ("concept", "port-notes#cargo", 0.631658671),
    ("concept", "plain.md#_h1", 0.619939586),
    ("concept", "port-notes#weather", 0.414953629),
    ("concept", "harbour-guide#tides", 0.204990641),
]


@pytest.fixture
def code_and_docs():
    import rmx_sandbox
    from refmatrix.ingest import ingest_path
    base = Path(rmx_sandbox.short_root("b300p-"))
    for d in ("src", "plain", "docs"):
        (base / d).mkdir()
    (base / "src" / "harbour.py").write_text(_CODE, encoding="utf8")
    (base / "plain" / "plain.md").write_text(
        "# Plain notes\n\nThe harbour master keeps the ferry log.\n", encoding="utf8")
    for name, text in _DOCS.items():
        (base / "docs" / f"{name}.md").write_text(text, encoding="utf8")
    s = Store(base / ".refmatrix")
    s.init()
    try:
        ingest_path(s, base / "src", semantic=True)   # plain ingest of Python mints no concepts
        ingest_path(s, base / "plain")
        ingest_gmd_paths(s, [base / "docs" / f"{n}.md" for n in _DOCS])
        yield s
    finally:
        s.close()
        rmx_sandbox.remove_tree(base)


def test_context_over_code_and_docs_ranks_exactly_as_at_base(code_and_docs):
    """bug-300 AC-3 (R2): `rmx context` over code and docs ranks byte-for-byte as at base,
    through `build_context` (what the CLI/MCP call) and the `content_rank` call it makes. A
    guard, GREEN at base by construction; it fails if the block join leaks to non-memory
    blocks or the BM25 N / avgdl / doc-length base moves for a store with no memories."""
    s = code_and_docs
    hits = s.content_rank(_ref_terms(_PIN_QUERY), kinds=["code", "doc", "memory", "concept"],
                          limit=30)
    rank = [(k, n, round(sc, 9)) for (k, n), (_e, sc) in zip(_named(s, hits), hits)]
    b = build_context(s, _PIN_QUERY, max_entities=10, grep_backstop=False)
    ctx = [(e.entity.kind, e.entity.name, round(e.weight, 9))
           for e in b.groups.get("content", [])]
    assert rank == _PIN_RANK, f"content_rank moved; base pin {_PIN_RANK!r}, now {rank!r}"
    assert ctx == _PIN_CONTEXT, f"context moved; base pin {_PIN_CONTEXT!r}, now {ctx!r}"


def test_multi_word_phrase_reaches_the_index(gmd_store):
    """The regression itself: every term is indexed, so this must produce
    content hits rather than falling through to the grep floor."""
    bundle = build_context(gmd_store, "sneakers closet organize", max_entities=10)
    assert "content" in bundle.groups, f"expected content hits, got {sorted(bundle.groups)}"
    assert bundle.groups["content"]


def test_bare_concepts_are_not_content_hits(gmd_store):
    """Widening the kinds must not turn query terms into results — only
    anchored `doc#section` concepts are somewhere a reader can be sent."""
    bundle = build_context(gmd_store, "sneakers closet organize", max_entities=10)
    for e in bundle.groups.get("content", []):
        if e.entity.kind == "concept":
            assert "#" in e.entity.name
