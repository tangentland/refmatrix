"""LongMemEval corpus preparation — the reshape that makes prose retrievable.

RED first for task 7.1 (plan-7-longmemeval). Everything here runs on a synthetic
fixture: the real `longmemeval_s` is a 278MB download living off-tree on a
separate volume, and a test that needs it is a test that does not run.

What these assertions protect, in order of how badly each one bit before:

  * The GMD reshape. `eval/memaware/prepare.py` records the measurement: rmx's
    general markdown pass extracts only STRUCTURED signals, so a plain chat
    transcript ingests as 1309 doc entities with 0 `mentions` rows and 3
    concepts. Prose must be emitted as GMD or the whole symbolic half of the
    benchmark measures an empty index.
  * The `date:` field. A third of LongMemEval is temporal-reasoning; a session
    stripped of its timestamp makes those questions unanswerable by
    construction, and the run would still complete and print a number.
  * Lossless dedup. 25,112 haystack slots collapse to 19,829 session ids. That
    is only safe because the same id always carries the same content (measured
    2026-09-15: zero conflicts). The code must verify that invariant rather
    than assume it — a silent overwrite would corrupt one question's haystack
    with another's text and nothing downstream would notice.
  * Counted skips. `feedback_no_silent_failures`: a session that cannot be
    resolved is counted and named, never dropped.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval" / "production" / "longmemeval"))

import prepare  # noqa: E402


def _session(text: str, *, answer: bool = False) -> list[dict]:
    return [
        {"role": "user", "content": text, "has_answer": answer},
        {"role": "assistant", "content": f"Noted: {text}"},
    ]


def _question(qid: str, qtype: str, sids: list[str], gold: list[str],
              sessions: dict[str, list[dict]]) -> dict:
    return {
        "question_id": qid,
        "question_type": qtype,
        "question": f"q for {qid}",
        "answer": "a",
        "question_date": "2023/05/20 (Sat) 10:00",
        "haystack_dates": [f"2023/05/{10 + i:02d} (Wed) 09:0{i}" for i in range(len(sids))],
        "haystack_session_ids": list(sids),
        "haystack_sessions": [sessions[s] for s in sids],
        "answer_session_ids": list(gold),
    }


@pytest.fixture
def raw() -> list[dict]:
    """Three questions over six sessions, two of them shared between haystacks."""
    s = {
        "s1": _session("the fence needed fixing", answer=True),
        "s2": _session("bought a red bicycle"),
        "s3": _session("the GPS stopped working", answer=True),
        "s4": _session("coffee grinder review"),
        "s5": _session("Peter sold me two cows", answer=True),
        "s6": _session("weather was mild"),
    }
    return [
        _question("gpt4_aaa", "single-session-user", ["s1", "s2", "s4"], ["s1"], s),
        _question("gpt4_bbb", "temporal-reasoning", ["s3", "s2", "s6"], ["s3"], s),
        _question("gpt4_ccc_abs", "multi-session", ["s5", "s4", "s6"], ["s5"], s),
    ]


@pytest.fixture
def built(tmp_path: Path, raw: list[dict]) -> tuple[Path, dict]:
    counts = prepare.build(raw, tmp_path)
    return tmp_path, counts


# ── the reshape ────────────────────────────────────────────────────────────

def test_every_haystack_session_is_written_exactly_once(built):
    out, counts = built
    files = sorted(p.stem for p in (out / "corpus").rglob("*.md"))
    assert files == ["s1", "s2", "s3", "s4", "s5", "s6"]
    # 9 haystack slots, 6 distinct sessions — the dedup is the whole point.
    assert counts["session_slots"] == 9
    assert counts["sessions_written"] == 6


def test_sessions_are_emitted_as_gmd_not_bare_prose(built):
    """The measured failure: plain markdown -> 0 mentions rows, 3 concepts."""
    out, _ = built
    text = (out / "corpus" / "s1.md").read_text()
    assert text.startswith("---\n")
    fm = text.split("---", 2)[1]
    assert 'gmd: "0.1"' in fm
    assert "id: s1" in fm
    assert "node_type: memory" in fm
    assert "type: longmemeval/session" in fm
    assert "{#root}" in text


def test_session_body_carries_its_date(built):
    """A third of the benchmark is temporal-reasoning."""
    out, _ = built
    fm = (out / "corpus" / "s1.md").read_text().split("---", 2)[1]
    assert "date:" in fm
    assert "2023/05/10" in fm


def test_session_body_preserves_every_turn_and_its_speaker(built):
    out, _ = built
    text = (out / "corpus" / "s1.md").read_text()
    assert "the fence needed fixing" in text
    assert "Noted: the fence needed fixing" in text
    assert text.lower().count("user") >= 1
    assert text.lower().count("assistant") >= 1


def test_rendered_gmd_passes_the_repo_linter(built):
    out, _ = built
    lint = Path(__file__).resolve().parents[1] / "tools" / "gmd" / "lint.py"
    import subprocess
    p = subprocess.run([sys.executable, str(lint), str(out / "corpus" / "s1.md")],
                       capture_output=True, text=True)
    assert "error" not in p.stdout.lower(), p.stdout


# ── the labels ─────────────────────────────────────────────────────────────

def test_qrels_map_every_question_to_its_gold_sessions(built):
    out, _ = built
    qrels = json.loads((out / "qrels.json").read_text())
    assert qrels["gpt4_aaa"] == ["s1"]
    assert qrels["gpt4_bbb"] == ["s3"]


def test_abstention_questions_keep_their_gold_and_are_flagged(built):
    """Verified on longmemeval_s: all 30 `_abs` questions carry gold sessions,
    all present in their own haystack. Retrieval is well-defined for them;
    abstention is the answer model's decision, not the retriever's."""
    out, counts = built
    qrels = json.loads((out / "qrels.json").read_text())
    assert qrels["gpt4_ccc_abs"] == ["s5"]
    meta = json.loads((out / "questions.json").read_text())
    by_id = {q["question_id"]: q for q in meta}
    assert by_id["gpt4_ccc_abs"]["abstention"] is True
    assert by_id["gpt4_aaa"]["abstention"] is False
    assert counts["abstention"] == 1


def test_haystacks_round_trip_the_full_candidate_set(built):
    """`restricted` scoring is only possible if the per-question haystack survives."""
    out, _ = built
    hs = json.loads((out / "haystacks.json").read_text())
    assert set(hs["gpt4_aaa"]) == {"s1", "s2", "s4"}
    assert set(hs["gpt4_bbb"]) == {"s3", "s2", "s6"}


# ── the loud failures ──────────────────────────────────────────────────────

def test_a_session_id_carrying_two_different_bodies_raises(tmp_path, raw):
    """Dedup is lossless only while one id means one text. If that ever stops
    being true, one question's haystack silently overwrites another's."""
    raw[1]["haystack_sessions"][1] = _session("a completely different session")
    with pytest.raises(prepare.CorpusConflict) as e:
        prepare.build(raw, tmp_path)
    assert "s2" in str(e.value)


def test_an_unresolvable_gold_session_is_counted_and_named(tmp_path, raw, capsys):
    raw[0]["answer_session_ids"] = ["s1", "nonexistent_session"]
    counts = prepare.build(raw, tmp_path)
    assert counts["unresolved_gold"] == 1
    assert "nonexistent_session" in capsys.readouterr().out


def test_a_question_whose_gold_all_vanishes_is_reported_not_silently_kept(tmp_path, raw):
    raw[0]["answer_session_ids"] = ["nonexistent_session"]
    counts = prepare.build(raw, tmp_path)
    qrels = json.loads((tmp_path / "qrels.json").read_text())
    assert "gpt4_aaa" not in qrels
    assert counts["questions_without_gold"] == 1


# ── the subsets ────────────────────────────────────────────────────────────

def test_subset_is_balanced_across_types_not_file_order(tmp_path, raw):
    """`--limit N` semantics take the first N in file order, and file order is
    not type-balanced. A limited run would over-weight whichever type leads."""
    skew = []
    for i in range(12):
        qtype = "multi-session" if i < 9 else "temporal-reasoning"
        skew.append(_question(f"q{i:02d}", qtype, ["s1"], ["s1"],
                              {"s1": _session("x")}))
    picked = prepare.stratified_subset(skew, per_type=2, seed=1)
    from collections import Counter
    assert Counter(q["question_type"] for q in picked) == {
        "multi-session": 2, "temporal-reasoning": 2}


def test_subset_is_deterministic_under_a_seed(raw):
    a = prepare.stratified_subset(raw * 4, per_type=1, seed=7)
    b = prepare.stratified_subset(raw * 4, per_type=1, seed=7)
    assert [q["question_id"] for q in a] == [q["question_id"] for q in b]
