#!/usr/bin/env python3
"""Mine REAL memory-recall queries from a deployed store's query.log.

The recall hook fires `memory recall --stdin-json` (query in stdin, NOT argv),
so cli.log carries no query text. But the SAME UserPromptSubmit prompt is also
logged by `scan-prompt` as a `kind="scan"` query.log row (body = prompt[:200]).
Those scan bodies are the real query traffic the memory system should serve.

This filters that traffic down to substantive natural-language intents (drops
task-notification blobs, slash commands, and short operational acks) and writes
`queries.jsonl` ({qid, text}) — the trusted, usage-grounded query set the LLM
judge will label. NO store access, NO deps beyond stdlib.

Usage:
    python mine_queries.py --root /Users/tholley/github/atollogy/bdep/viascope \
        --limit 80 --out queries.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

# Pure-operational prompts that aren't information-seeking — drop them.
_STOP_EXACT = {
    "save state", "recall state", "continue", "go", "yes", "no", "ok", "okay",
    "that was me", "stop", "stop caveman", "normal mode", "thanks", "thank you",
    "proceed", "do it", "next", "y", "n", "ack",
}
_NOISE_SUBSTR = ("<task-notification", "</", "tool-use-id", "<system-reminder")


def _looks_substantive(text: str) -> bool:
    t = text.strip()
    low = t.lower()
    if not t or low in _STOP_EXACT:
        return False
    if t.startswith("/") or t.startswith("!"):      # slash / bang commands
        return False
    if any(s in low for s in _NOISE_SUBSTR):
        return False
    words = re.findall(r"[A-Za-z0-9_./-]+", t)
    if len(words) < 4 or len(words) > 60:           # too short / a pasted blob
        return False
    # Require at least a couple of alphabetic word-characters (not pure punctuation/ids).
    if sum(c.isalpha() for c in t) < 8:
        return False
    return True


def mine(query_log: Path, limit: int) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    if not query_log.exists():
        raise SystemExit(f"no query.log at {query_log}")
    with query_log.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if row.get("kind") != "scan":
                continue
            body = (row.get("body") or "").strip()
            if not _looks_substantive(body):
                continue
            key = body.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append({"qid": f"q{len(out)+1:03d}", "text": body})
            if len(out) >= limit:
                break
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True,
                    help="Project root holding .refmatrix/ (e.g. the viascope checkout).")
    ap.add_argument("--limit", type=int, default=80)
    ap.add_argument("--out", default="queries.jsonl")
    args = ap.parse_args()

    query_log = Path(args.root) / ".refmatrix" / "query.log"
    rows = mine(query_log, args.limit)
    out_path = Path(args.out)
    out_path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    print(f"mined {len(rows)} substantive queries from {query_log} -> {out_path}")
    for r in rows[:8]:
        print(f"  {r['qid']}: {r['text'][:80]}")


if __name__ == "__main__":
    main()
