"""Summarise a mypy log for task 29.2 -- per-module and per-code error counts.

Usage: python3 mypy_summary.py <mypy.log> [module ...]

Counts lines of the form `<path>:<line>: error: <text>  [<code>]`. With module names (file stems,
e.g. `verbs query store handoff mcp`) the table is split into that STRICT set and the REST, which
is how the gate reads the same log. The "Found N errors" figure mypy printed is checked against
the parsed count; a mismatch exits 1 (an unparsed error line would otherwise go uncounted).
"""
from __future__ import annotations

import collections
import pathlib
import re
import sys

ERR = re.compile(r"^(?P<path>[^:\n]+\.py):(?P<line>\d+): error: .*?(?:\s\s\[(?P<code>[a-z0-9-]+)\])?$")
FOUND = re.compile(r"^Found (\d+) errors? in (\d+) files? \(checked (\d+) source files?\)")


def main(argv: list[str]) -> int:
    text = pathlib.Path(argv[1]).read_text().splitlines()
    strict = set(argv[2:])
    per: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    found = None
    for ln in text:
        m = ERR.match(ln)
        if m:
            per[pathlib.PurePosixPath(m["path"]).stem if strict else m["path"]][m["code"] or "(no code)"] += 1
            continue
        f = FOUND.match(ln)
        if f:
            found = tuple(int(x) for x in f.groups())
    total = sum(sum(c.values()) for c in per.values())
    print(f"parsed errors: {total}; mypy said: {found}")
    if found is None or found[0] != total:
        print("MISMATCH between the parsed count and mypy's own figure", file=sys.stderr)
        return 1

    def table(title: str, mods: list[str]) -> None:
        codes: collections.Counter = collections.Counter()
        for m in mods:
            codes.update(per[m])
        print(f"{title}: {sum(codes.values())} errors in {len(mods)} modules")
        for m in sorted(mods, key=lambda m: -sum(per[m].values())):
            print(f"  {m:28}{sum(per[m].values()):5}")
        print("  by code: " + "  ".join(f"{k}={v}" for k, v in codes.most_common()))

    if strict:
        table("STRICT", [m for m in per if m in strict])
        table("REST", [m for m in per if m not in strict])
    else:
        table("ALL", list(per))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
