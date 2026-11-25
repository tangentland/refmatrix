#!/usr/bin/env python3
"""Tally ch-bsd BULLSHIT findings by the self-audit question that missed them.

Reads workflow/bullshit/OPEN.md and CLOSED.md (the findings ledger) and prints,
per question SA-1..SA-8 (workflow/SELF_AUDIT.md `#questions`): the BULLSHIT-level
rows open, closed-upheld and closed-overruled; every `none:` proposal; the
`unnamed` count; and F5's upheld / overruled rate. Derived, never kept by hand.

Exit 1, naming the row id, for a BULLSHIT-level row whose `question` cell is
empty or `-`, holds an unknown token, or for any row it cannot parse.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LEDGER = REPO / "workflow" / "bullshit"
QUESTIONS = {
    1: "ran it for real", 2: "the test reaches the wiring",
    3: "census of callers and siblings", 4: "the whole path is bounded",
    5: "busy is not absent", 6: "the guard can fire",
    7: "failures are loud", 8: "nothing handed off on paper",
}


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split(" | ")]


def read_rows(path: Path, errors: list[str]) -> list[dict]:
    """Table rows of one ledger as dicts keyed by header cell."""
    rows, header = [], None
    for n, line in enumerate(path.read_text().splitlines(), 1):
        if not line.startswith("|") or line.startswith("|---"):
            continue
        cells = _cells(line)
        if cells[0] == "id":
            header = cells
            continue
        if header is None:
            errors.append(f"{path.name}:{n}: row before any header: {cells[0]}")
            continue
        if "question" not in header:
            errors.append(f"{path.name}: the header has no `question` column")
            return rows
        if len(cells) != len(header):
            errors.append(f"{cells[0]}: {path.name}:{n}: {len(cells)} cells, "
                          f"the header has {len(header)}")
            continue
        row = dict(zip(header, cells))
        row["_src"] = f"{path.name}:{n}"
        rows.append(row)
    return rows


def classify(q: str) -> tuple[str, list[int]] | None:
    """('sa', [n..]) | ('none', []) | ('unnamed', []); None = invalid."""
    if q == "unnamed":
        return "unnamed", []
    if q.startswith("none:") and q[5:].strip():
        return "none", []
    parts = [p.strip() for p in re.split(r",|\+", q)]
    nums = []
    for p in parts:
        m = re.fullmatch(r"SA-(\d+)", p)
        if not m or not 1 <= int(m.group(1)) <= 8:
            return None
        nums.append(int(m.group(1)))
    return "sa", nums


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--open", type=Path, default=LEDGER / "OPEN.md")
    ap.add_argument("--closed", type=Path, default=LEDGER / "CLOSED.md")
    a = ap.parse_args(argv)

    errors: list[str] = []
    rows = [(r, "open") for r in read_rows(a.open, errors)]
    rows += [(r, r.get("outcome", "")) for r in read_rows(a.closed, errors)]

    per_q = {n: {"open": 0, "upheld": 0, "overruled": 0} for n in QUESTIONS}
    nones: list[tuple[str, str]] = []
    unnamed = 0
    total = {"open": 0, "upheld": 0, "overruled": 0}
    for r, state in rows:
        if "BULLSHIT" not in r["level"]:
            continue
        if state not in total:
            errors.append(f"{r['id']}: {r['_src']}: outcome {state!r} is not "
                          "upheld or overruled")
            continue
        q = r["question"]
        c = classify(q) if q not in ("", "-") else None
        if c is None:
            errors.append(f"{r['id']}: {r['_src']}: BULLSHIT-level row has "
                          f"question {q!r}; want SA-1..SA-8, `none: <proposal>` "
                          "or `unnamed`")
            continue
        total[state] += 1
        kind, nums = c
        if kind == "sa":
            for n in nums:
                per_q[n][state] += 1
        elif kind == "none":
            nones.append((r["id"], q[5:].strip()))
        else:
            unnamed += 1
    if errors:
        for e in errors:
            print(f"bsd-tally: {e}", file=sys.stderr)
        return 1

    for n, label in QUESTIONS.items():
        d = per_q[n]
        print(f"SA-{n} {label}: {d['open'] + d['upheld'] + d['overruled']} "
              f"(open {d['open']}, upheld {d['upheld']}, overruled {d['overruled']})")
    print(f"none: {len(nones)}")
    for rid, proposal in nones:
        print(f"  none: {rid}: {proposal}")
    print(f"unnamed: {unnamed}")
    n_all = sum(total.values())
    print(f"BULLSHIT-level rows: {n_all} (open {total['open']}, "
          f"upheld {total['upheld']}, overruled {total['overruled']})")
    closed = total["upheld"] + total["overruled"]
    rate = f"{100 * total['upheld'] / closed:.0f}%" if closed else "n/a"
    print(f"F5 upheld rate: {total['upheld']}/{closed} closed = {rate}; "
          f"overruled {total['overruled']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
