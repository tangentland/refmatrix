#!/usr/bin/env python3
"""Turn the LongMemEval drop into a corpus rmx can be measured on.

Upstream ships one JSON array of 500 questions; each question carries its OWN
haystack of ~50 chat sessions, and a session is a list of `{role, content}`
turns. Four things have to happen before any run:

  1. **Explode.** The unit a memory system retrieves is a session, so each one
     becomes a file. Across 500 haystacks that is 25,112 slots collapsing to
     19,829 distinct session ids — the haystacks overlap heavily, and writing
     the union once is the only tractable shape. The dedup is lossless *as
     long as one id always means one text*, which held with zero conflicts when
     measured on 2026-09-15; `build` verifies it per id rather than trusting it,
     because a silent overwrite would corrupt one question's haystack with
     another's prose and nothing downstream would see it.

  2. **Reshape as GMD.** This is a finding, not plumbing. rmx's general markdown
     pass extracts only STRUCTURED signals — bold metadata, ADR refs,
     concept-doc linkages, fenced specs. Measured on the MemAware corpus, plain
     prose produced 1309 doc entities, **0 `mentions` rows and 3 concepts**:
     no graph at all, every symbolic surface degraded to the grep backstop.
     `ingest_gmd` is the pass that runs the body term-frequency sweep the
     symbolic index is built from, so frontmatter here is not decoration — it
     is what makes the corpus retrievable. `--as-memory` at ingest time is the
     honest analogy besides: in rmx a past session IS a memory.

  3. **Keep the date.** 133 of 500 questions are temporal-reasoning and another
     78 are knowledge-update. A session stripped of its timestamp makes both
     unanswerable by construction — and the run would still finish and print a
     number, which is the dangerous part.

  4. **Label.** `answer_session_ids` becomes a document-level qrel, and
     `haystack_session_ids` becomes the per-question candidate set that the
     `restricted` scoring mode needs. Both are emitted; `run.py` never
     reconstructs them.

Abstention questions (`_abs`) are SCORED, not dropped. All 30 carry non-empty
`answer_session_ids`, every one present in their own haystack: the gold sessions
hold related-but-insufficient evidence, so retrieval is well defined. Choosing
to abstain is the answer model's job, not the retriever's. They are flagged so
`run.py` can report them as their own slice.

Outputs (all off-tree, all gitignored):
  corpus/<session_id>.md   one session per file, GMD
  qrels.json               question_id -> [gold session id]
  haystacks.json           question_id -> [every session id in its haystack]
  questions.json           question metadata (no transcripts), abstention flag
  subsets/<name>.json      type-stratified question subsets
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from paths import (CORPUS, DATA, HAYSTACKS, HF_REPO, QRELS, QUESTIONS, SPLITS,
                   SUBSETS, UPSTREAM)

# A session id becomes a GMD `id:` and a filename stem, so it has to survive
# both. Upstream ids are already `answer_<hex>_<n>`; this is a guard, not a
# transform, and anything it would have to change is reported.
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]+$")


class CorpusConflict(RuntimeError):
    """One session id, two different transcripts. Dedup would lose one."""


def fetch(split: str = "s") -> Path:
    """Download the split blob from HuggingFace. Idempotent (hf caches)."""
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:  # a gap, named — not worked around
        sys.exit("  ! huggingface_hub is not installed in this interpreter.\n"
                 "    It is the only supported fetch path for this dataset.\n"
                 "    Install it, or place the blob at "
                 f"{UPSTREAM / SPLITS[split]} by hand.")
    UPSTREAM.mkdir(parents=True, exist_ok=True)
    name = SPLITS[split]
    print(f"  ~ fetching {HF_REPO}:{name} -> {UPSTREAM}")
    return Path(hf_hub_download(HF_REPO, name, repo_type="dataset",
                                local_dir=str(UPSTREAM)))


def _turns_to_markdown(session: list[dict]) -> str:
    """One `### <role>` block per turn.

    Roles are kept because half the question types turn on WHO said a thing
    (`single-session-user` vs `single-session-assistant`); a flattened
    transcript erases the distinction the benchmark is testing.
    """
    out: list[str] = []
    for i, turn in enumerate(session, 1):
        role = str(turn.get("role") or "unknown")
        content = (turn.get("content") or "").strip()
        out.append(f"### {role} (turn {i}) {{#turn-{i}}}\n\n{content}")
    return "\n\n".join(out)


def _as_gmd(sid: str, date: str, session: list[dict]) -> str:
    title = f"Session {sid}"
    return (
        '---\n'
        'gmd: "0.1"\n'
        f'id: {sid}\n'
        f'title: "{title}"\n'
        'tags: [longmemeval, session]\n'
        'metadata:\n'
        '  node_type: memory\n'
        '  type: longmemeval/session\n'
        f'  session_id: {sid}\n'
        f'  date: "{date}"\n'
        '---\n\n'
        f'# {title} {{#root}}\n\n'
        f'**Date:** {date}\n\n'
        f'{_turns_to_markdown(session)}\n'
    )


def _digest(session: list[dict]) -> str:
    return hashlib.sha1(json.dumps(session, sort_keys=True).encode()).hexdigest()


def build(questions: list[dict], out: Path) -> dict:
    """Write the union corpus plus every label file. Returns reconciled counts.

    Counts are returned AND printed because every number here is a place a
    silent drop could hide: `feedback_no_silent_failures` applies to a
    benchmark corpus exactly as it applies to a memory path — a skipped session
    that nobody counted becomes a retrieval miss nobody can explain.
    """
    corpus = out / "corpus"
    corpus.mkdir(parents=True, exist_ok=True)
    for stale in corpus.glob("*.md"):
        stale.unlink()

    seen: dict[str, str] = {}          # session id -> content digest
    dates: dict[str, str] = {}
    slots = 0

    for q in questions:
        sids = q.get("haystack_session_ids") or []
        sessions = q.get("haystack_sessions") or []
        hdates = q.get("haystack_dates") or []
        for i, sid in enumerate(sids):
            slots += 1
            if not _SAFE_ID.match(str(sid)):
                raise CorpusConflict(
                    f"session id {sid!r} is not filename/GMD-id safe")
            session = sessions[i] if i < len(sessions) else []
            date = hdates[i] if i < len(hdates) else ""
            digest = _digest(session)
            prior = seen.get(sid)
            if prior is not None:
                if prior != digest:
                    raise CorpusConflict(
                        f"session id {sid!r} carries two different transcripts "
                        f"(first seen {prior[:12]}, now {digest[:12]}); dedup "
                        f"would silently drop one — question {q['question_id']}")
                continue
            seen[sid] = digest
            dates[sid] = date
            (corpus / f"{sid}.md").write_text(_as_gmd(sid, date, session),
                                              encoding="utf8")

    # ── labels ────────────────────────────────────────────────────────────
    qrels: dict[str, list[str]] = {}
    haystacks: dict[str, list[str]] = {}
    meta: list[dict] = []
    unresolved_gold = 0
    without_gold = 0
    abstention = 0

    for q in questions:
        qid = q["question_id"]
        is_abs = str(qid).endswith("_abs")
        abstention += int(is_abs)
        haystacks[qid] = list(q.get("haystack_session_ids") or [])
        gold = []
        for sid in q.get("answer_session_ids") or []:
            if sid in seen:
                gold.append(sid)
            else:
                unresolved_gold += 1
                print(f"  ! {qid}: gold session {sid!r} is not in any haystack "
                      f"— dropped from qrels and counted")
        if gold:
            qrels[qid] = gold
        else:
            without_gold += 1
            print(f"  ! {qid}: no resolvable gold session — excluded from scoring")
        meta.append({
            "question_id": qid,
            "question": q.get("question", ""),
            "question_type": q.get("question_type", "unknown"),
            "question_date": q.get("question_date", ""),
            "answer": q.get("answer", ""),
            "abstention": is_abs,
            "n_haystack": len(haystacks[qid]),
        })

    (out / "qrels.json").write_text(json.dumps(qrels, indent=1), encoding="utf8")
    (out / "haystacks.json").write_text(json.dumps(haystacks, indent=1), encoding="utf8")
    (out / "questions.json").write_text(json.dumps(meta, indent=1), encoding="utf8")

    counts = {
        "questions": len(questions),
        "session_slots": slots,
        "sessions_written": len(seen),
        "sessions_deduped": slots - len(seen),
        "questions_with_gold": len(qrels),
        "questions_without_gold": without_gold,
        "unresolved_gold": unresolved_gold,
        "abstention": abstention,
        "by_type": dict(Counter(m["question_type"] for m in meta)),
    }
    return counts


def stratified_subset(questions: list[dict], *, per_type: int,
                      seed: int) -> list[dict]:
    """Type-balanced sample.

    A `--limit N` that takes the first N in file order silently over-weights
    whichever type leads, and LongMemEval's types are wildly uneven (133
    multi-session vs 30 single-session-preference). Every limited run goes
    through here.
    """
    by_type: dict[str, list[dict]] = defaultdict(list)
    for q in questions:
        by_type[q.get("question_type", "unknown")].append(q)
    rng = random.Random(seed)
    picked: list[dict] = []
    for qtype in sorted(by_type):
        pool = sorted(by_type[qtype], key=lambda q: q["question_id"])
        picked.extend(pool if len(pool) <= per_type
                      else rng.sample(pool, per_type))
    picked.sort(key=lambda q: q["question_id"])
    return picked


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fetch", action="store_true",
                    help="download the split from HuggingFace if absent")
    ap.add_argument("--split", default="s", choices=sorted(SPLITS),
                    help="longmemeval_s (default) / _m / _oracle")
    ap.add_argument("--per-type", type=int, default=20,
                    help="questions per type in the stratified subset")
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()

    DATA.mkdir(parents=True, exist_ok=True)
    blob = UPSTREAM / SPLITS[a.split]
    if a.fetch and not blob.exists():
        blob = fetch(a.split)
    if not blob.exists():
        sys.exit(f"  ! {blob} missing — run with --fetch")

    questions = json.loads(blob.read_text(encoding="utf8"))
    print(f"  ~ {len(questions)} questions from {blob.name}")

    counts = build(questions, DATA)
    for k, v in counts.items():
        print(f"  + {k}: {v}")

    SUBSETS.mkdir(parents=True, exist_ok=True)
    sub = stratified_subset(questions, per_type=a.per_type, seed=a.seed)
    lean = [{k: v for k, v in q.items()
             if k not in ("haystack_sessions", "haystack_session_ids",
                          "haystack_dates")} for q in sub]
    out = SUBSETS / f"stratified-{a.per_type}.json"
    out.write_text(json.dumps(lean, indent=1), encoding="utf8")
    print(f"  + subset {out.name}: {len(lean)} questions "
          f"({a.per_type}/type, seed={a.seed})")
    print(f"\n  next: python3 ingest.py     # build the rmx store over corpus/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
