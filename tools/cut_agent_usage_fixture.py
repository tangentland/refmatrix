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

Trim (2026-10-19, AC-6 measurement round 14). The first cut kept every row before `--cut`
(query.log 2.1 MB, cli.log 22.6 MB). AC-6 reads only the window, and from cli.log only the
`memory` commands, so the cut keeps rows in [`KEEP_FROM`, `CUT`) — one day before `--since`, so
the report's lower bound still has rows to exclude — and, from cli.log, only rows whose command is
`memory` (every `memory` subcommand and its `phase=start` intent row stays, so `memory get` /
`memory search` remain negative controls for the recall count). A row whose argv begins with a
global option (`-p X memory recall`) has its command path hashed by the redaction and is not a
`memory` row to the report either; it is dropped and counted in the manifest.

Flag tokens are kept verbatim only when they have a flag's SHAPE (`-x`, `-A12`, `--name`,
`--name=<sha>`): the first cut kept four argv tokens that were grep PATTERNS beginning with `-`
(`--(force|check|port)`, `--[a-z-]+`, `-i -l`), which d8f forbids. Redaction is idempotent (a
value already `sha256:<64 hex>` or `<scrubbed>` is kept), so `--from-fixture DIR` re-cuts a
committed fixture without the live logs and yields the same bytes a fresh cut would.

Usage:
    python3 tools/cut_agent_usage_fixture.py [--store <project>/.refmatrix] [--out DIR]
    python3 tools/cut_agent_usage_fixture.py --from-fixture tests/fixtures/agent_usage [--out DIR]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SINCE = "2026-09-23"
UNTIL = "2026-10-07T11:06:35"
CUT = "2026-10-07T11:07:14"
KEEP_FROM = "2026-09-22"          # one day before SINCE: the lower bound keeps rows to exclude
CLI_COMMANDS_KEPT = ("memory",)   # the only cli.log command the AC-6 report reads
_FLAG_SHAPE = re.compile(r"^--?[A-Za-z][A-Za-z0-9-]*$")
_REDACTED = re.compile(r"^(sha256:[0-9a-f]{64}|<scrubbed>)$")

# Fields that carry a filesystem path (scrubbed) or free text (hashed).
PATH_FIELDS = ("cwd", "root", "path", "file", "store", "paths")
TEXT_FIELDS = ("body", "error", "query", "prompt", "text")


def _sha(s: str) -> str:
    """The hex sha256 of `s`; a value that is already `sha256:<hex>` yields its own hex, so a
    re-cut of a redacted fixture keeps every hash (idempotent redaction)."""
    if s.startswith("sha256:") and _REDACTED.match(s):
        return s[len("sha256:"):]
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
        name, eq, val = a.partition("=")
        if a in ("-", "--") or _FLAG_SHAPE.match(name):
            out.append(name + ("=sha256:" + _sha(val) if eq else ""))
        elif _REDACTED.match(a):
            out.append(a)
        else:
            out.append("sha256:" + _sha(a))
    return out


def _redact(row: dict, tops: set, groups: set) -> dict:
    r = dict(row)
    for k in TEXT_FIELDS:
        if isinstance(r.get(k), str) and not _REDACTED.match(r[k]):
            r[k] = "sha256:" + _sha(r[k])
    for k in PATH_FIELDS:
        if k in r and r[k] is not None:
            r[k] = "<scrubbed>"
    if isinstance(r.get("argv"), list):
        r["argv"] = _redact_argv(r["argv"], tops, groups)
    return r


def _cut(src: Path, dst: Path, tops: set, groups: set,
         commands: "tuple[str, ...] | None" = None) -> "tuple[int, int, int]":
    """Copy the redacted rows of `src` in [KEEP_FROM, CUT) to `dst`; with `commands`, only
    rows whose redacted argv starts with one of them. Returns (kept, unparseable,
    dropped_other_command)."""
    kept = unparseable = dropped = 0
    with src.open("r", errors="surrogateescape") as fh, dst.open("w") as out:
        for line in fh:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError:
                unparseable += 1
                continue
            if not isinstance(row, dict):
                continue
            ts = str(row.get("ts", ""))
            if ts >= CUT or ts < KEEP_FROM:
                continue
            red = _redact(row, tops, groups)
            if commands is not None and (red.get("argv") or [None])[0] not in commands:
                dropped += 1
                continue
            out.write(json.dumps(red) + "\n")
            kept += 1
    return kept, unparseable, dropped


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--store", type=Path, default=REPO / ".refmatrix")
    ap.add_argument("--out", type=Path, default=REPO / "tests" / "fixtures" / "agent_usage")
    ap.add_argument("--from-fixture", type=Path, default=None,
                    help="re-cut an already-redacted fixture dir (never the live logs); its "
                         "manifest's `sources` are carried forward as `origin_sources`")
    a = ap.parse_args(argv)
    tops, groups = _command_names()
    src_dir = a.from_fixture or a.store
    origin = None
    if a.from_fixture is not None:
        old = json.loads((a.from_fixture / "manifest.json").read_text())
        origin = old.get("origin_sources") or old.get("sources")
    # Read every source into memory first: --from-fixture may name the --out dir itself.
    blobs = {}
    for name in ("query.log", "cli.log"):
        src = src_dir / name
        if not src.is_file():
            print(f"missing source log: {src}", file=sys.stderr)
            return 2
        blobs[name] = src.read_bytes()
    a.out.mkdir(parents=True, exist_ok=True)
    manifest: dict = {"since": SINCE, "until": UNTIL, "cut": CUT, "keep_from": KEEP_FROM,
                      "cli_commands_kept": list(CLI_COMMANDS_KEPT), "sources": {}}
    if origin is not None:
        manifest["origin_sources"] = origin
    tmp = a.out / ".cut-src"
    tmp.mkdir(exist_ok=True)
    for name in ("query.log", "cli.log"):
        (tmp / name).write_bytes(blobs[name])
        manifest["sources"][name] = {"sha256": hashlib.sha256(blobs[name]).hexdigest()}
        kept, bad, other = _cut(tmp / name, a.out / name, tops, groups,
                                CLI_COMMANDS_KEPT if name == "cli.log" else None)
        (tmp / name).unlink()
        manifest["sources"][name].update(kept=kept, unparseable_skipped=bad)
        if name == "cli.log":
            manifest["sources"][name]["dropped_other_command"] = other
        manifest["sources"][name]["fixture_sha256"] = hashlib.sha256(
            (a.out / name).read_bytes()).hexdigest()
        if bad:
            print(f"{name}: {bad} unparseable line(s) not copied", file=sys.stderr)
    tmp.rmdir()
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
    # memory recall commands in the window, end rows only (phase=start excluded), per R11
    # channel recomputed from the argv flags and the row's `source` (its invocation).
    crows = [json.loads(l) for l in (a.out / "cli.log").read_text().splitlines() if l]
    chan: dict = {}
    for r in crows:
        if r.get("phase") == "start" or not (SINCE <= str(r.get("ts", "")) < UNTIL):
            continue
        av = r.get("argv") or []
        if av[:2] != ["memory", "recall"]:
            continue
        fl = set(av[2:])
        ch = ("session_start" if "--session-start" in fl else
              "prompt_recall" if "--stdin-json" in fl else
              "precompact" if "--recent" in fl and r.get("source") == "hook" else "recall")
        chan[ch] = chan.get(ch, 0) + 1
    manifest["counts"]["memory-recall-by-channel"] = dict(sorted(chan.items()))
    (a.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))
    if manifest["L"] != manifest["window_rows"]:
        print("WARNING: window holds non-legacy rows; AC-6 assumes every row is legacy",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
