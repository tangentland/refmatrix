#!/usr/bin/env python3
"""Turn the MemAware upstream drop into something rmx can be measured on.

Upstream ships 91 *daily* markdown files, each concatenating ~14 chat sessions,
plus `_mapping.json` (daily file -> the session ids inside it) written with the
author's absolute paths. Three things have to happen before any run:

  1. **Split.** The unit a memory system should retrieve is a session, not a
     day. A 700KB daily file is a terrible BM25 document and a worse graph
     node. Every session already carries a `## Session <id>` header, and the
     mapping accounts for all 1307 of them, so the split is exact and lossless.
  2. **Relocate.** `_mapping.json` points at `/Users/kevin/...`; `run.mjs`
     passes absolute paths straight through to `existsSync`, so the upstream
     mapping silently yields an empty index on any other machine.
  3. **Label.** Each question names its `answer_session_ids`. Once sessions are
     separate files that becomes a document-level qrel — which buys a
     retrieval metric that costs no API calls at all (see retrieval_eval.py).

Outputs (all gitignored):
  corpus/<date>/<session_id>.md   one session per file
  corpus/_mapping.json            local-path mapping for run.mjs
  corpus/_sessions.json           session_id -> {path, date}
  qrels.json                      question_id -> [session doc paths]
  subsets/<name>.json             tier-stratified question subsets
"""

from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

from paths import DATA, UPSTREAM, CORPUS, SUBSETS, QRELS

HERE = Path(__file__).resolve().parent
REPO = "https://github.com/kevin-hs-sohn/memaware.git"

SESSION_RE = re.compile(r"^## Session (\S+)\s*$", re.M)


def clone() -> None:
    if UPSTREAM.exists():
        print(f"  ~ upstream already present: {UPSTREAM}")
        return
    subprocess.run(["git", "clone", "--depth", "1", REPO, str(UPSTREAM)], check=True)


def _as_gmd(sid: str, date: str, body: str) -> str:
    """Wrap one session transcript as a GMD doc.

    Plain-prose markdown is a dead end for rmx: the general markdown pass
    extracts only *structured* signals (bold metadata, ADR refs, concept-doc
    linkages, fenced class specs), so a chat transcript yields a `doc` entity
    and no concepts at all. `ingest_gmd` is the pass that runs a body
    term-frequency sweep into weighted `mentions` edges — the index every
    symbolic read surface (content_rank, context, scan-prompt salience/PPR)
    is built on. Frontmatter is therefore not decoration; it is what makes
    the corpus retrievable at all.

    `--as-memory` at ingest time then registers each session as kind=memory,
    which is the honest analogy: in rmx a past session IS a memory, and this
    puts the corpus on the same surfaces (`memory recall`, dense ANN,
    scan-prompt) that the shipped product uses.
    """
    title = f"Session {sid} ({date})"
    return (
        '---\n'
        'gmd: "0.1"\n'
        f'id: {sid}\n'
        f'title: "{title}"\n'
        'tags: [memaware, session]\n'
        'metadata:\n'
        '  node_type: memory\n'
        '  type: memaware/session\n'
        f'  session_id: {sid}\n'
        f'  date: "{date}"\n'
        '---\n\n'
        f'# {title} {{#root}}\n\n'
        f'{body}\n'
    )


def split_sessions() -> dict:
    """Daily markdown -> one file per session. Returns session_id -> meta."""
    src = UPSTREAM / "data" / "sessions"
    files = sorted(p for p in src.glob("*.md"))
    if not files:
        sys.exit(f"  ! no session files under {src} — run with --clone first")

    sessions: dict[str, dict] = {}
    per_day: dict[str, list[str]] = defaultdict(list)

    for day_file in files:
        date = day_file.stem
        text = day_file.read_text(encoding="utf8")
        marks = list(SESSION_RE.finditer(text))
        if not marks:
            print(f"  ! no session headers in {day_file.name} — skipped")
            continue
        out_dir = CORPUS / date
        out_dir.mkdir(parents=True, exist_ok=True)
        for i, m in enumerate(marks):
            sid = m.group(1)
            end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
            body = text[m.start():end].rstrip()
            # Strip the `## Session <id>` header — it becomes the GMD H1 below,
            # and left in place it would be a second, id-less anchor.
            body = body.split("\n", 1)[1].lstrip("\n") if "\n" in body else ""
            doc = _as_gmd(sid, date, body)
            out = out_dir / f"{sid}.md"
            out.write_text(doc, encoding="utf8")
            if sid in sessions:
                print(f"  ! duplicate session id {sid} ({date})")
            sessions[sid] = {"path": str(out.relative_to(DATA)), "date": date}
            per_day[date].append(sid)

    (CORPUS / "_sessions.json").write_text(json.dumps(sessions, indent=1), encoding="utf8")

    # run.mjs reads _mapping.json as {path: [session_ids]} and indexes each path
    # as ONE document. Pointing it at per-session files gives the BM25 baseline
    # the same granularity rmx gets, so a comparison measures retrieval and not
    # chunk size.
    mapping = {meta["path"]: [sid] for sid, meta in sessions.items()}
    (CORPUS / "_mapping.json").write_text(json.dumps(mapping, indent=1), encoding="utf8")

    # The original day-level mapping, relocated — for reproducing upstream's
    # own numbers rather than our re-chunked variant.
    day_map = {}
    for date, sids in per_day.items():
        p = UPSTREAM / "data" / "sessions" / f"{date}.md"
        day_map[str(p)] = sids
    (CORPUS / "_mapping_daily.json").write_text(json.dumps(day_map, indent=1), encoding="utf8")

    print(f"  + split {len(files)} daily files -> {len(sessions)} session docs")
    return sessions


def build_qrels(sessions: dict) -> dict:
    """question_id -> [relevant session doc paths]. The free-metric ground truth."""
    qs = json.loads((UPSTREAM / "data" / "questions.json").read_text(encoding="utf8"))
    qrels, missing = {}, Counter()
    for q in qs:
        paths = []
        for sid in q.get("answer_session_ids") or []:
            meta = sessions.get(sid)
            if meta is None:
                missing[sid] += 1
                continue
            paths.append(meta["path"])
        if paths:
            qrels[q["question_id"]] = paths
    (QRELS).write_text(json.dumps(qrels, indent=1), encoding="utf8")
    print(f"  + qrels for {len(qrels)}/{len(qs)} questions"
          + (f" ({len(missing)} unresolved session ids)" if missing else ""))
    return qrels


def build_subsets(per_tier: int, seed: int) -> None:
    """Tier-stratified subsets. `run.mjs --limit N` takes the first N in file
    order, and file order is not tier-balanced — a limited run would silently
    over-weight whichever tier leads. Point MEMAWARE_QUESTIONS at a subset."""
    qs = json.loads((UPSTREAM / "data" / "questions.json").read_text(encoding="utf8"))
    by_tier = defaultdict(list)
    for q in qs:
        by_tier[q.get("difficulty", "unknown")].append(q)
    rng = random.Random(seed)
    picked = []
    for tier in ("easy", "medium", "hard"):
        pool = sorted(by_tier[tier], key=lambda q: q["question_id"])
        picked.extend(pool if len(pool) <= per_tier else rng.sample(pool, per_tier))
    picked.sort(key=lambda q: q["question_id"])
    SUBSETS.mkdir(parents=True, exist_ok=True)
    out = SUBSETS / f"stratified-{per_tier}.json"
    out.write_text(json.dumps(picked, indent=1), encoding="utf8")
    print(f"  + subset {out.relative_to(DATA)}: {len(picked)} questions "
          f"({per_tier}/tier, seed={seed})")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--clone", action="store_true", help="git clone upstream if absent")
    ap.add_argument("--per-tier", type=int, default=30,
                    help="questions per tier in the stratified subset (default 30)")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    DATA.mkdir(parents=True, exist_ok=True)
    if args.clone:
        clone()
    sessions = split_sessions()
    build_qrels(sessions)
    build_subsets(args.per_tier, args.seed)
    print(f"\n  next: python3 ingest.py     # build the rmx store over corpus/")


if __name__ == "__main__":
    main()
