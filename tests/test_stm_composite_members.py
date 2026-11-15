"""Task 31.5 R2.0 / AC-2.0 RED: the STM composite prints no stopword or typo as a topic member.

Spec: `workflow/plans/plan-31-pre-mod-loose-ends-tasks/task-31.5-scan-prompt-block-measure.md`,
`#r2-0` and `#ac-2-0` (release A, beside S0: `#files-release`).

Why: 0.84.0 shipped three of the four "already clear" composite cuts. The fourth is left: a
grounded topic still prints every non-junk member, so `Members:` lines carry the prompt's own
plain words (`the`, a typo such as `buigger`). R2.0: a member is printed only when it is
identifier-shaped or a path (`scan.is_identifier_shaped`), or a plain word outside the shared
stoplist (`scan._PROMPT_STOPWORDS`, `feedback_reuse_shared_stoplist`) that names a concept the
store holds. A topic with no printed member is not emitted. It is a RENDER filter: the focus
graph is unchanged (admission into the ring is 25.3's).

Throwaway stores under a short `mkdtemp()` root, in-process `Store`, no daemon, no mocks.
`_render_gmd` is called directly in one test only: the spec puts the filter there (`#census`),
and a topic with no printable member cannot reach it through the public path, because the
0.84.0 grounded-topic gate (`_has_grounded_member`) runs first and every member it accepts is
identifier-shaped, hence printable.
"""
from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path

import pytest

SESSION = "sess-members315"
MEMBERS = ["scan-prompt", "store.py", "the", "buigger", "question"]
_MEMBERS_LINE = re.compile(r"^Members: (.*)$", re.M)


def _ring(root: Path) -> None:
    from refmatrix import stm as stm_mod
    r = stm_mod.Stm(root, SESSION)
    r.record("input", " ".join(MEMBERS), refs=MEMBERS)
    r.record("tool", "again " + " ".join(MEMBERS), refs=MEMBERS)


@pytest.fixture
def make_store():
    """`make_store(holds_question)`: a store with an STM ring whose one topic is MEMBERS;
    the store holds the concept `question` only when asked. `scan-prompt` and `store.py`
    are deliberately NOT concepts: identifier-shaped members print regardless."""
    from refmatrix.store import Store
    made: list = []

    def _make(holds_question: bool):
        base = Path(tempfile.mkdtemp(prefix="mem.", dir="/tmp")).resolve()
        root = base / "proj" / ".refmatrix"
        root.mkdir(parents=True)
        s = Store(root, backend="duckdb")
        s.init()
        eid = s.add_memory(name="mem_question_doc", content="A note about one question.",
                           mtype="feedback")
        if holds_question:
            s.link("mentions", s.add_concept("question"), eid)
        # L178 S3 (bsd-315 r1): the store HOLDS `the`, so the shared stoplist alone keeps it
        # out of `Members:` (mutation M2-1a, dropping the stoplist check, must fail).
        s.link("mentions", s.add_concept("the"), eid)
        s.flush_fragments()
        assert s.resolve_concept_ids("the"), "fixture: the store does not hold `the`"
        made.append((base, s))
        _ring(root)
        return s, root

    yield _make
    for base, s in made:
        s.close()
        shutil.rmtree(base, ignore_errors=True)


def _topic_members(root: Path) -> "list[str]":
    from refmatrix import stm as stm_mod
    topics = stm_mod.topic_composites(stm_mod.Stm(root, SESSION).focus_graph(top=40))
    hit = [t["members"] for t in topics if "scan-prompt" in t["members"]]
    assert hit and set(MEMBERS) <= set(hit[0]), (
        f"fixture: the ring has no topic holding every member: {[t['members'] for t in topics]}")
    return hit[0]


@pytest.mark.parametrize("holds_question", [True, False], ids=["question-held", "not-held"])
def test_stopwords_and_unknown_plain_words_are_not_printed_as_members(make_store,
                                                                      holds_question):
    """AC-2.0 (RED at base; M2-1): a topic of `scan-prompt`, `store.py`, `the`, `buigger`,
    `question` prints `scan-prompt`, `store.py`, and `question` only when the store holds
    that concept. `the` is on the shared stoplist (and the store holds it as a concept, so
    only the stoplist keeps it out); `buigger` names nothing."""
    from refmatrix.composite import build_topic_composite
    s, root = make_store(holds_question)
    _topic_members(root)
    out = build_topic_composite(s, root, expand=False, session=SESSION)
    assert out, "fixture: no composite (the topic holds identifier-shaped members)"
    lines = _MEMBERS_LINE.findall(out)
    assert len(lines) == 1, f"fixture: {len(lines)} Members lines:\n{out}"
    printed = [m.strip() for m in lines[0].split(",")]
    want = {"scan-prompt", "store.py"} | ({"question"} if holds_question else set())
    assert set(printed) == want, (
        f"store holds `question`: {holds_question}; printed members {printed}, expected "
        f"{sorted(want)} (stoplist words and plain words naming no concept are not printed)")


def test_a_topic_with_no_printable_member_is_not_emitted(make_store):
    """AC-2.0 (RED at base): a topic whose members are all stoplist words or plain words
    naming no concept renders no topic block and no `Members:` line. Driven through
    `_render_gmd` (see the module docstring for why the public path cannot reach it)."""
    from refmatrix.composite import _render_gmd
    s, _root = make_store(False)
    topic = {"members": ["the", "buigger", "and", "zorbleplain"], "nodes": []}
    out = _render_gmd(s, [topic], expand=False, per_node_entities=4,
                      expand_nodes_per_topic=3, max_expansions=6, max_tokens=1200, turn=2)
    assert "## Topic" not in out and not _MEMBERS_LINE.search(out), (
        f"a topic with no printable member was emitted:\n{out}")


def test_the_focus_graph_is_unchanged_by_the_filter(make_store):
    """AC-2.0 (characterization, green at base): the filter is a render filter. Building the
    composite leaves the focus graph (its file and its view) exactly as it was; every member,
    stopword and typo included, is still a focus node."""
    from refmatrix import stm as stm_mod
    from refmatrix.composite import build_topic_composite
    s, root = make_store(True)
    gpath = root / "stm" / f"{SESSION}.focus.json"
    before_file = gpath.read_bytes()
    before = stm_mod.Stm(root, SESSION).focus_graph(top=40)
    out = build_topic_composite(s, root, expand=False, session=SESSION)
    assert out, "fixture: no composite"
    assert gpath.read_bytes() == before_file, "building the composite rewrote the focus graph"
    after = stm_mod.Stm(root, SESSION).focus_graph(top=40)
    assert after == before
    assert set(MEMBERS) <= set(_topic_members(root))
