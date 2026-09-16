"""Scan-prompt over the PROJECT's own store, before vs after a re-derive.

Why this exists: bug-036 meant `parse_gmd` built a node only for a HEADING
anchor, so 483 of the 1,154 anchors in this project's curated memory dir — 42%
— were invisible to the graph. The published benchmarks are unaffected (both
generated corpora carry 0 body anchors, measured), but anything retrieved over
refmatrix's OWN corpus was reading a graph missing two fifths of its memory
anchors. This measures that, and only that.

The one rule that makes the number honest: BOTH runs use the SAME code. Deploy
first, measure, re-derive, measure again. Measuring across the deploy would
confound a code change with a graph change, which is the mistake
`feedback_measure_the_path_users_run` and the retracted 62.9 s latency figure
were both about.

Confounds held down deliberately:
  * RMX_RERANK=0 — the shared cross-encoder is nondeterministic under load and
    bug-025 says it usually times out anyway. Ranking noise would swamp a
    graph delta.
  * --composite-intra-edges 0 — the STM composite is session state that
    changes on every call; it is not part of what a re-derive changes.
  * one fixed prompt set, read from disk, same order both runs.

Usage:
    python3 eval/production/scanprompt_graph_delta.py before  > before.json
    # ... rmx reingest --force ...
    python3 eval/production/scanprompt_graph_delta.py after   > after.json
    python3 eval/production/scanprompt_graph_delta.py compare before.json after.json
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MEMDIR = (Path.home() / ".claude" / "projects"
          / "-Users-tholley-claude-tools-refmatrix" / "memory")

# Real questions of the kind the hook actually sees, spread across the corpus.
# Fixed on disk so a later run cannot quietly use a friendlier set.
PROMPTS = [
    "memory bridge save-state",
    "why did the daemon fast-exit on a DuckDB invalidation",
    "how does the hub decide a daemon is wedged versus busy",
    "what is the rule about measuring the path users run",
    "scan-prompt ranking and the junk token gate",
    "how do writes reach the store without opening it directly",
    "what happened with the rerank timeout on the hook budget",
    "GMD anchors and how rel edges attach",
    "slot rotation drift and the active marker",
    "what did the LongMemEval benchmark actually show",
    "shared model workers and the private fallback",
    "how are stale files different from the dirty queue",
]

_ANCHOR = re.compile(r"\{#([A-Za-z0-9._-]+)\}")
_HEAD = re.compile(r"^#{1,6}\s")
_FENCE = re.compile(r"^\s*```")


def body_anchor_names() -> set[str]:
    """`<doc-id>#<anchor>` for every anchor written on a paragraph or list
    item in the memory dir — precisely the nodes bug-036 hid."""
    out: set[str] = set()
    for f in MEMDIR.rglob("*.md"):
        doc = f.stem
        in_code = False
        for ln in f.read_text(errors="ignore").splitlines():
            if _FENCE.match(ln):
                in_code = not in_code
                continue
            if in_code or _HEAD.match(ln):
                continue
            for m in _ANCHOR.finditer(ln):
                out.add(f"{doc}#{m.group(1)}")
    return out


def run_one(prompt: str) -> dict:
    env = dict(os.environ, RMX_RERANK="0")
    r = subprocess.run(
        ["rmx", "scan-prompt", prompt, "--format", "json",
         "--composite-intra-edges", "0"],
        capture_output=True, text=True, env=env, cwd=str(REPO), timeout=180)
    if r.returncode != 0:
        return {"prompt": prompt, "error": r.stderr.strip()[:400]}
    try:
        bundles = json.loads(r.stdout)
    except json.JSONDecodeError as e:
        return {"prompt": prompt, "error": f"unparseable: {e}"}
    names: list[str] = []
    tokens = neighbors = 0
    for b in bundles:
        tokens += int(b.get("estimated_tokens") or 0)
        neighbors += int(b.get("total_neighbors") or 0)
        a = b.get("anchor") or {}
        if a.get("name"):
            names.append(a["name"])
        for group in (b.get("groups") or {}).values():
            for n in group:
                if n.get("name"):
                    names.append(n["name"])
    return {"prompt": prompt, "bundles": len(bundles), "tokens": tokens,
            "neighbors": neighbors, "names": sorted(set(names)),
            "bytes": len(r.stdout)}


def collect(label: str) -> dict:
    return {"label": label,
            "rows": [run_one(p) for p in PROMPTS]}


def compare(a: dict, b: dict) -> None:
    body = body_anchor_names()
    print(f"body anchors in the memory dir: {len(body)}\n")
    hdr = f"{'prompt':52s} {'bundles':>14s} {'nodes':>13s} {'tokens':>13s}"
    print(hdr)
    print("-" * len(hdr))
    tot_new = tot_body = 0
    errs = []
    for ra, rb in zip(a["rows"], b["rows"]):
        if ra.get("error") or rb.get("error"):
            errs.append((ra["prompt"], ra.get("error") or rb.get("error")))
            continue
        na, nb = set(ra["names"]), set(rb["names"])
        new = nb - na
        newbody = new & body
        tot_new += len(new)
        tot_body += len(newbody)
        print(f"{ra['prompt'][:52]:52s} "
              f"{ra['bundles']:6d}->{rb['bundles']:<7d} "
              f"{len(na):5d}->{len(nb):<7d} "
              f"{ra['tokens']:5d}->{rb['tokens']:<7d}"
              + (f"   +{len(newbody)} body" if newbody else ""))
    print(f"\nnewly returned nodes: {tot_new}")
    print(f"  of which body anchors (what bug-036 hid): {tot_body}")
    if tot_new and not tot_body:
        print("  -> the delta is NOT the body anchors; do not credit the fix")
    for p, e in errs:
        print(f"ERROR {p}: {e}")


if __name__ == "__main__":
    if sys.argv[1:2] == ["compare"]:
        compare(json.loads(Path(sys.argv[2]).read_text()),
                json.loads(Path(sys.argv[3]).read_text()))
    else:
        json.dump(collect(sys.argv[1] if sys.argv[1:] else "run"),
                  sys.stdout, indent=1)
