#!/usr/bin/env python3
"""Cut + redact the AC-6 frozen fixture for task 21.1 (`rmx telemetry --agent-usage`).

Task 21.1 AC-6 needs a REDACTED copy of this project's `.refmatrix/query.log` and
`.refmatrix/cli.log`, cut around 2026-10-07T11:06:35, committed under
`tests/fixtures/agent_usage/`. Per d8f (feedback_no_raw_prompts_in_public_repo) no raw prompt,
query body or path may reach the public repo: bodies become their sha256, path-valued fields
are scrubbed, and argv keeps only the command path and flag names (every other token, flag
values included, becomes a sha256). Counts are invariant under this redaction.

This script is run BY THE USER (the RED-phase agent was not permitted to read the live logs,
2026-10-16). It only READS the source logs (no store is opened, no lock taken) and writes:

    tests/fixtures/agent_usage/query.log
    tests/fixtures/agent_usage/cli.log
    tests/fixtures/agent_usage/manifest.json   {window, cut, L, counts, source sha256s}

`L` is the number of query.log rows inside the AC-6 window (`--since 2026-09-23`,
`--until 2026-10-07T11:06:35`, until EXCLUSIVE): every such row is legacy (no cwd/root), so
the report prints `legacy_unattributed=<L>`. The file keeps rows up to `--cut` (default
2026-10-07T11:07:14, exclusive), so the 20 replay rows of 11:06:35-11:07:13 are IN the file
and excluded by the report's WINDOW, as AC-6 states.

Usage:
    python3 tools/cut_agent_usage_fixture.py [--store <project>/.refmatrix] [--out DIR]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SINCE = "2026-09-23"
UNTIL = "2026-10-07T11:06:35"
CUT = "2026-10-07T11:07:14"

# Fields that carry a filesystem path (scrubbed) or free text (hashed).
PATH_FIELDS = ("cwd", "root", "path", "file", "store", "paths")
TEXT_FIELDS = ("body", "error", "query", "prompt", "text")


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", "surrogatepass")).hexdigest()


def _command_names() -> "tuple[set[str], set[str]]":
    """(top-level command names, group names) from the click tree, so argv keeps its command
    path and nothing else readable."""
    sys.path.insert(0, str(REPO / "src"))
    import click
    from refmatrix.cli import main
    tops, groups = set(main.commands), set()
    for name, cmd in main.commands.items():
        if isinstance(cmd, click.Group):
            groups.add(name)
            tops |= {f"{name} {sub}" for sub in cmd.commands}
    return tops, groups


def _redact_argv(argv: list, tops: set, groups: set) -> list:
    out: list = []
    i = 0
    if argv and str(argv[0]) in tops:
        out.append(str(argv[0]))
        i = 1
        if str(argv[0]) in groups and len(argv) > 1 and f"{argv[0]} {argv[1]}" in tops:
            out.append(str(argv[1]))
            i = 2
    for a in argv[i:]:
        a = str(a)
        if a.startswith("-"):
            name, eq, val = a.partition("=")
            out.append(name + ("=sha256:" + _sha(val) if eq else ""))
        else:
            out.append("sha256:" + _sha(a))
    return out


def _redact(row: dict, tops: set, groups: set) -> dict:
    r = dict(row)
    for k in TEXT_FIELDS:
        if isinstance(r.get(k), str):
            r[k] = "sha256:" + _sha(r[k])
    for k in PATH_FIELDS:
        if k in r and r[k] is not None:
            r[k] = "<scrubbed>"
    if isinstance(r.get("argv"), list):
        r["argv"] = _redact_argv(r["argv"], tops, groups)
    return r


def _cut(src: Path, dst: Path, tops: set, groups: set) -> "tuple[int, int]":
    kept = unparseable = 0
    with src.open("r", errors="surrogateescape") as fh, dst.open("w") as out:
        for line in fh:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError:
                unparseable += 1
                continue
            if not isinstance(row, dict) or str(row.get("ts", "")) >= CUT:
                continue
            out.write(json.dumps(_redact(row, tops, groups)) + "\n")
            kept += 1
    return kept, unparseable


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--store", type=Path, default=REPO / ".refmatrix")
    ap.add_argument("--out", type=Path, default=REPO / "tests" / "fixtures" / "agent_usage")
    a = ap.parse_args(argv)
    tops, groups = _command_names()
    a.out.mkdir(parents=True, exist_ok=True)
    manifest: dict = {"since": SINCE, "until": UNTIL, "cut": CUT, "sources": {}}
    for name in ("query.log", "cli.log"):
        src = a.store / name
        if not src.is_file():
            print(f"missing source log: {src}", file=sys.stderr)
            return 2
        manifest["sources"][name] = {"sha256": hashlib.sha256(src.read_bytes()).hexdigest()}
        kept, bad = _cut(src, a.out / name, tops, groups)
        manifest["sources"][name].update(kept=kept, unparseable_skipped=bad)
        if bad:
            print(f"{name}: {bad} unparseable line(s) not copied", file=sys.stderr)
    rows = [json.loads(l) for l in (a.out / "query.log").read_text().splitlines() if l]
    win = [r for r in rows if SINCE <= str(r.get("ts", "")) < UNTIL]
    legacy = [r for r in win if "cwd" not in r and "root" not in r]
    manifest["L"] = len(legacy)
    manifest["window_rows"] = len(win)
    manifest["counts"] = {
        "context-replica": sum(1 for r in win if r.get("kind") == "context"
                               and r.get("source") == "context-replica"),
        "grep-replica": sum(1 for r in win if r.get("source") == "grep-replica"),
    }
    (a.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))
    if manifest["L"] != manifest["window_rows"]:
        print("WARNING: window holds non-legacy rows; AC-6 assumes every row is legacy",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
