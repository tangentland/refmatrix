"""M2 — containment-query demand (hypertree exploration, spike 2026-10-20).

Reads COPIES of each store's `query.log` + `cli.log` (never the live files) and classifies the
last 30 days of real corpus queries. Writes AGGREGATES ONLY: raw query text never leaves this
process (repo rule: no raw prompts in the public repo).

Universe of "real queries" per store, window [2026-09-20, 2026-10-20]:
- `cli.log` `grep` runs that read the corpus: at least one file/dir operand inside the store
  root, or `-r` with the cwd inside the root. Pipe filters (no operand, no -r) and greps over
  files outside the root (scratch logs, ~/.claude) are excluded and counted.
- `cli.log` `context` / `query` / `neighbors` runs (argv shows flags like --hit-lines).
- `query.log` `scan` (UserPromptSubmit prompts) and `recall` (memory recall hook) bodies.
Greps whose every in-root operand is a run artifact (`*.log`/`.out`/`.err`, or under
`workflow/review-output/`) are test/tool-log reads, not corpus queries: excluded and counted.
Hook-sourced cli rows (focus/sync/curator bookkeeping) are not queries and are skipped.

Containment-shaped (the doc's definition, made mechanical):
- C1 grep scoped to a SUBDIR: an operand that is a directory strictly below the root, or -r
  run from a cwd strictly below the root.
- C2 path prefix / "in|under|inside|within X" in a context/query/neighbors arg or a prompt,
  where X is path-like (has '/', a file extension, or names a top-level dir of the store).
- C3 `--hit-lines` (any mode) on a context call: "where in this file".
- C4 grep scoped to ONE file inside the root (no dir operand): the grep form of "--hit-lines on
  one file" (where in this file?), so it belongs to the doc's list. C4m = several named files.
DOC = C1|C2|C3|C4 — the band is read on this. Reported split, because the two halves need
different placements: SUBTREE = C1|C2 (path-prefix: the `fs` representation) and WITHIN-FILE =
C3|C4 (section/def containment: the `gmd` and `code` representations).
Facet-shaped (P2 demand, reported alongside): grep --include/--exclude/-t/--type/-g, DSL
`kind:` `mtype:` `namespace:` `partition:` terms.
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import RESULTS, SPIKE_ROOT, STORES  # noqa: E402

LO, HI = "2026-09-20", "2026-10-21"
VAL_OPTS = {"-e", "-f", "-m", "-A", "-B", "-C", "--limit", "--include", "--exclude",
            "--exclude-dir", "--max-count", "--context", "--after-context",
            "--before-context", "-t", "--type", "-g", "--glob", "--hit-lines", "--max-tokens",
            "--max-entities", "--expand", "--linkages", "-p", "--partition", "--degree"}
FACET_GREP = {"--include", "--exclude", "--exclude-dir", "-t", "--type", "-g", "--glob"}
EXT_RE = re.compile(r"\.(py|md|sql|sh|json|ya?ml|toml|txt|js|ts|html|css|rs|go)\b")
IN_RE = re.compile(r"\b(in|under|inside|within|across|beneath)\s+[`'\"]?([~\w./\-]+)", re.I)
DSL_FACET_RE = re.compile(r"\b(kind|mtype|namespace|partition):", re.I)
DSL_PATH_RE = re.compile(r"\b(path|under|dir|file):", re.I)


def parse_grep(argv):
    flags, pos, explicit_pat = [], [], False
    i = 1
    while i < len(argv):
        x = argv[i]
        if x == "--":
            pos += argv[i + 1:]
            break
        if x.startswith("-") and len(x) > 1:
            name = x.split("=", 1)[0]
            flags.append(name)
            if name in ("-e", "-f"):
                explicit_pat = True
            if name in VAL_OPTS and "=" not in x:
                i += 1
        else:
            pos.append(x)
        i += 1
    operands = pos if explicit_pat else pos[1:]
    recursive = any(f in ("-r", "-R", "--recursive") or
                    (f.startswith("-") and not f.startswith("--") and ("r" in f[1:] or "R" in f[1:]))
                    for f in flags)
    return flags, operands, recursive


def path_like(tok: str, topdirs: set[str]) -> bool:
    t = tok.strip("`'\".,:;()")
    return "/" in t or bool(EXT_RE.search(t)) or t in topdirs


def main() -> None:
    out_all = {}
    for store, (root, _pid) in STORES.items():
        root_r = root.rstrip("/")
        topdirs = {d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d))
                   and not d.startswith(".")}
        cnt = Counter()
        cdir = SPIKE_ROOT / store

        def under_root(p: str, cwd: str) -> "str | None":
            ap = os.path.normpath(os.path.join(cwd or root_r, os.path.expanduser(p)))
            if ap == root_r:
                return "root"
            if ap.startswith(root_r + "/"):
                rel = ap[len(root_r) + 1:]
                if rel.startswith(".refmatrix"):
                    return None
                if os.path.isdir(ap):
                    return "dir"
                if os.path.exists(ap) or EXT_RE.search(rel):
                    return "file"
                return "dir"   # vanished, extension-less: a directory more often than not
            return None

        for line in open(cdir / "cli.log", errors="replace"):
            try:
                r = json.loads(line)
            except ValueError:
                cnt["cli_unparseable"] += 1
                continue
            if not (LO <= r.get("ts", "") < HI):
                continue
            argv = r.get("argv") or []
            if not argv or r.get("source") == "hook":
                continue
            cmd, cwd = argv[0], r.get("cwd") or root_r
            if cmd == "grep":
                flags, ops, rec = parse_grep(argv)
                if "--help" in flags:
                    continue
                kinds = [under_root(o, cwd) for o in ops]
                inside = [k for k in kinds if k]
                # operands that are run artifacts (test/tool logs), not corpus files
                art = [o for o, k in zip(ops, kinds) if k == "file" and (
                    o.endswith((".log", ".out", ".err")) or "review-output" in o)]
                if ops and inside and len(art) == len(inside):
                    cnt["grep_excluded_artifact_log"] += 1
                    continue
                if not ops:
                    if not rec:
                        cnt["grep_excluded_pipe_filter"] += 1
                        continue
                    k = under_root(".", cwd)
                    if k is None:
                        cnt["grep_excluded_outside_root"] += 1
                        continue
                    inside = [k]
                elif not inside:
                    cnt["grep_excluded_outside_root"] += 1
                    continue
                cnt["q_total"] += 1
                cnt["q_grep"] += 1
                c1 = "dir" in inside
                c4 = not c1 and inside.count("file") == 1
                c4m = not c1 and inside.count("file") > 1
                cnt["C4m_grep_multi_file"] += c4m
                facet = any(f in FACET_GREP for f in flags)
                if c1 or c4 or c4m:
                    for o, k in zip(ops, kinds):
                        if k in ("dir", "file"):
                            ap = os.path.normpath(os.path.join(cwd, os.path.expanduser(o)))
                            rel = ap[len(root_r) + 1:]
                            cnt[f"{'C1' if k == 'dir' else 'C4'}_top:{rel.split('/')[0] if '/' in rel else '(root file)' if k == 'file' else rel}"] += 1
                            break
                cnt["C1_grep_subdir"] += c1
                cnt["C4_grep_file"] += c4
                cnt["doc"] += (c1 or c4)
                cnt["subtree"] += c1
                cnt["within_file"] += c4
                cnt["facet"] += facet
                cnt["grep_root_wide"] += (not c1 and not c4 and not c4m)
            elif cmd in ("context", "query", "neighbors"):
                if "--help" in argv:
                    continue
                cnt["q_total"] += 1
                cnt[f"q_{cmd}"] += 1
                args = " ".join(argv[1:])
                c3 = cmd == "context" and any(a.startswith("--hit-lines") for a in argv)
                c2 = bool(DSL_PATH_RE.search(args)) or any(
                    path_like(m.group(2), topdirs) for m in IN_RE.finditer(args)) or any(
                    path_like(a, topdirs) and "/" in a and not a.startswith(("query/", "keyword/",
                                                                             "concept:", "phrase/"))
                    for a in argv[1:] if not a.startswith("-"))
                cnt["C2_path_arg"] += c2
                cnt["C3_hit_lines"] += c3
                cnt["doc"] += (c2 or c3)
                cnt["subtree"] += c2
                cnt["within_file"] += (c3 and not c2)
                cnt["facet"] += bool(DSL_FACET_RE.search(args))
        for line in open(cdir / "query.log", errors="replace"):
            try:
                r = json.loads(line)
            except ValueError:
                cnt["qlog_unparseable"] += 1
                continue
            if not (LO <= r.get("ts", "") < HI) or r.get("kind") not in ("scan", "recall"):
                continue
            body = r.get("body") or ""
            cnt["q_total"] += 1
            cnt[f"q_{r['kind']}"] += 1
            c2 = any(path_like(m.group(2), topdirs) for m in IN_RE.finditer(body))
            cnt["C2_prompt_in_under"] += c2
            cnt["doc"] += c2
            cnt["subtree"] += c2
        n = cnt["q_total"]
        res = dict(cnt)
        res["share_doc"] = cnt["doc"] / n if n else None
        res["share_subtree"] = cnt["subtree"] / n if n else None
        res["share_within_file"] = cnt["within_file"] / n if n else None
        res["sufficient_n"] = n >= 30
        res["share_facet"] = cnt["facet"] / n if n else None
        g = cnt["q_grep"]
        res["grep_share_subdir"] = cnt["C1_grep_subdir"] / g if g else None
        res["grep_share_one_file"] = cnt["C4_grep_file"] / g if g else None
        res["grep_share_multi_file"] = cnt["C4m_grep_multi_file"] / g if g else None
        nsc = cnt["q_scan"] + cnt["q_recall"]
        res["prompt_share_in_under"] = cnt["C2_prompt_in_under"] / nsc if nsc else None
        out_all[store] = res
        print(store, json.dumps(res))
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "m2_all.json").write_text(json.dumps(
        {"window": [LO, HI], "stores": out_all}, indent=2))


if __name__ == "__main__":
    main()
