#!/usr/bin/env python3
"""Inventory for the P1 (b) proportionality review (L164, L165, L235).

WHY: the review prices each queued spec's pre-L165 ceremony from counts, not from a
reader's impression. Read-only: it reads the spec files named in files.txt and writes
inventory.tsv and evidence.txt beside itself. It edits no spec.

Usage: python3 inventory.py <repo-root>
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
# A heading that opens history: a revision round, a fold record, a lint transcript.
HISTORY = re.compile(
    r"^(Revision\b|Review findings folded|Inherited from ch-bsd|Open after revision|"
    r"Lines that change under|Approval of the|Round \d|bsd-spec-\S+ r\d+ folded|"
    r"Lead inputs folded|Lint run for|Freshness: what was re-read|Facts re-read|"
    r"The ten rows of|Homes proposed since|What changed\b|Changelog|History\b)",
    re.I,
)
RULINGS = re.compile(r"^(Lead rulings|Decision\b|Decisions\b|Owners from ruling)", re.I)
AC = re.compile(r"\bAC-?\d+[a-z]?(?:\.\d+)?[a-z]?\b")
REQ = re.compile(r"\bR\d+(?:\.\d+)?[a-z]?\b")
ROUND = re.compile(
    r"(?:ch-bsd|\bbsd)\b[^|\n]{0,80}\b(?:round|pass|review|confirm)|confirm-lite|"
    r"spec[- ]review round|architect re-read|re-read before RED|review round",
    re.I,
)
BAND = re.compile(
    r"\b\d+[- ](?:pass(?:es)?|consecutive|clean (?:full[- ])?(?:runs?|suites?)|"
    r"(?:full[- ]suite )?runs?|trials?|iterations?|repeats?|cycles?)\b|"
    r"\b\d+\s?[x×]\s|\btwice in a row\b|\bfull suite\b[^.\n]{0,40}\b(?:twice|each|per|every)\b",
    re.I,
)
MUT_HEAD = re.compile(r"mutation", re.I)
MUT_INLINE = re.compile(r"mutations?\b[^\n]{0,60}(?:FAIL|killed|must|each)", re.I)
MUT_BULLET = re.compile(r"^\s*(?:[-*]|\d+\.)\s+\*\*(?:Mutations?|Must-fail mutations)\b")
MUT_ROW = re.compile(r"^\|\s*`?\*{0,2}M[A-Za-z]?[\d.]+[a-z]?\b")
TABLE_ROW = re.compile(r"^\|(?!\s*[-:]+\s*\|)(?!\s*(?:#|Id|id|mutation|Mutation)\s*\|)")
LIST_ITEM = re.compile(r"^\s*(?:[-*]|\d+\.|\([a-z0-9]+\)|[a-z]\))\s+")
NON_SRC = re.compile(
    r"tests?/|conftest|test_\w+|fixture|scripts/|tools/|\.sh\b|workflow/|docs/|"
    r"lint\.py|the test\b|the guard test|allowlist|eval/",
    re.I,
)
SRC = re.compile(r"src/|refmatrix/\w+\.py|`\w+\.py`|\b(?:store|daemon|cli|verbs|hooks|ingest\w*)\.py")


def sections(lines: list[str]) -> list[str]:
    """Label every line: 'hist', 'rule' (ruling/decision record), 'mut' or 'body'."""
    label = ["body"] * len(lines)
    stack: list[tuple[int, str]] = []
    fence = False
    for i, line in enumerate(lines):
        if line.startswith("```"):
            fence = not fence
        m = None if fence else HEADING.match(line)
        if m:
            level, text = len(m.group(1)), m.group(2)
            while stack and stack[-1][0] >= level:
                stack.pop()
            kind = "body"
            if HISTORY.match(text):
                kind = "hist"
            elif RULINGS.match(text):
                kind = "rule"
            elif MUT_HEAD.search(text):
                kind = "mut"
            stack.append((level, kind))
        kinds = [k for _, k in stack]
        if "hist" in kinds:
            label[i] = "hist"
        elif "rule" in kinds:
            label[i] = "rule"
        elif kinds and kinds[-1] == "mut":
            label[i] = "mut"
    return label


def mutation_rows(lines: list[str], label: list[str]) -> list[str]:
    rows: list[str] = []
    inline_indent = None
    for i, line in enumerate(lines):
        if label[i] == "hist":
            inline_indent = None
            continue
        if MUT_ROW.match(line):
            rows.append(line)
            continue
        if label[i] == "mut":
            if (TABLE_ROW.match(line) and line.count("|") >= 3) or LIST_ITEM.match(line):
                if not HEADING.match(line):
                    rows.append(line)
            continue
        if (MUT_INLINE.search(line) and line.rstrip().endswith(":")) or MUT_BULLET.match(line):
            inline_indent = len(line) - len(line.lstrip())
            continue
        if inline_indent is not None:
            if not line.strip():
                continue
            indent = len(line) - len(line.lstrip())
            if LIST_ITEM.match(line) and indent > inline_indent:
                rows.append(line)
            elif indent <= inline_indent:
                inline_indent = None
    return rows


MUT_WORD = re.compile(r"\bMutations?\b")
MUT_VERB = re.compile(r"FAIL|\bRED\b|\bred\b|fails\b|killed|caught|each\b")
AC_ANCHOR = re.compile(r"\{#ac-[\w.-]+\}")
ACCEPT_HEAD = re.compile(r"accept", re.I)


def inline_mutations(lines: list[str], label: list[str]) -> list[str]:
    """Mutations written into prose ("Mutation: X FAILS", "Mutations, each FAILS: a; b").

    Approximate by design: a plural clause counts one statement per ';'-separated item.
    """
    paras: list[str] = []
    cur: list[str] = []
    for i, line in enumerate(lines):
        if label[i] in ("hist", "mut") or MUT_ROW.match(line) or HEADING.match(line):
            if cur:
                paras.append(" ".join(cur))
                cur = []
            continue
        if not line.strip() or LIST_ITEM.match(line):
            if cur:
                paras.append(" ".join(cur))
            cur = [line.strip()] if line.strip() else []
        else:
            cur.append(line.strip())
    if cur:
        paras.append(" ".join(cur))
    out: list[str] = []
    for para in paras:
        hits = list(MUT_WORD.finditer(para))
        for n, m in enumerate(hits):
            end = hits[n + 1].start() if n + 1 < len(hits) else len(para)
            clause = para[m.start():end].split("{#")[0][:700]
            if clause.rstrip().endswith(":") or not MUT_VERB.search(clause[:260]):
                continue
            if para.startswith(("- **Mutations", "* **Mutations")) and n == 0:
                continue  # counted through its sub-list by mutation_rows()
            if m.group(0) == "Mutations":
                out += [x.strip() for x in clause.split(";") if x.strip()]
            else:
                out.append(clause.strip())
    return out


def accept_items(lines: list[str], label: list[str]) -> int:
    """ACs written as an un-numbered list or table under an Acceptance heading."""
    n, inside, level = 0, False, 0
    for i, line in enumerate(lines):
        m = HEADING.match(line)
        if m:
            if inside and len(m.group(1)) <= level:
                inside = False
            if ACCEPT_HEAD.search(m.group(2)):
                inside, level = True, len(m.group(1))
            continue
        if inside and label[i] != "hist":
            if re.match(r"^(?:[-*]|\d+\.)\s+", line) or (TABLE_ROW.match(line) and line.count("|") >= 3):
                n += 1
    return n


ANCHOR = re.compile(r"\{#([\w.-]+)\}")
DOC_ID = re.compile(r"^id:\s*(\S+)", re.M)
CORPUS: dict[Path, str] = {}


def load_corpus(root: Path) -> None:
    """Every GMD file that could link into a spec: a trim that deletes a linked anchor
    turns that link into a lint error, so the inbound count is part of a trim's price."""
    for top in ("workflow", "docs"):
        for f in (root / top).rglob("*.md"):
            try:
                CORPUS[f.resolve()] = f.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                print(f"UNREADABLE {f}: {exc}", file=sys.stderr)


def inbound(path: Path, lines: list[str], label: list[str]) -> tuple[int, int, list[str]]:
    """(history anchors, of those linked from outside the history, their names)."""
    text = "\n".join(lines)
    m = DOC_ID.search(text)
    doc_id = m.group(1).strip("\"'") if m else path.stem
    hist_anchors = {a for i, l in enumerate(lines) if label[i] == "hist" for a in ANCHOR.findall(l)}
    live_text = "\n".join(l for i, l in enumerate(lines) if label[i] != "hist")
    linked = []
    for a in sorted(hist_anchors):
        hit = f"[[#{a}]]" in live_text
        if not hit:
            needle = re.compile(r"\[\[(?:[\w./-]*/)?" + re.escape(doc_id) + "#" + re.escape(a) + r"\]\]")
            hit = any(needle.search(t) for f, t in CORPUS.items() if f != path.resolve())
        if hit:
            linked.append(a)
    return len(hist_anchors), len(linked), linked


def inventory(path: Path) -> tuple[dict, list[str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    label = sections(lines)
    n_anchor, n_linked, linked = inbound(path, lines, label)
    hist_heads = [
        l for i, l in enumerate(lines)
        if label[i] == "hist" and HEADING.match(l) and HISTORY.match(HEADING.match(l).group(2))
    ]
    live = [l for i, l in enumerate(lines) if label[i] != "hist"]
    hist = [l for i, l in enumerate(lines) if label[i] == "hist"]
    ac_live = {m for l in live for m in AC.findall(l)}
    ac_hist = {m for l in hist for m in AC.findall(l)}
    req_live = {m for l in live for m in REQ.findall(l)}
    req_hist = {m for l in hist for m in REQ.findall(l)}
    rounds = [l for l in live if ROUND.search(l)]
    bands = [l for l in live if BAND.search(l)]
    muts = mutation_rows(lines, label) + inline_mutations(lines, label)
    non_src = [r for r in muts if NON_SRC.search(r) and not SRC.search(r)]
    # ceremony written into an acceptance criterion: a line that names an AC and a round or band
    ac_cer = [l for l in live if AC.search(l) and (ROUND.search(l) or BAND.search(l))]
    row = {
        "lines": len(lines),
        "acs": max(len(ac_live | ac_hist), len(set(AC_ANCHOR.findall("\n".join(lines)))),
                   accept_items(lines, label) if not (ac_live | ac_hist) else 0),
        "acs_only_in_history": len(ac_hist - ac_live),
        "reqs_only_in_history": len(req_hist - req_live),
        "history_sections": len(hist_heads),
        "history_lines": len(hist),
        "ruling_lines": sum(1 for x in label if x == "rule"),
        "round_lines": len(rounds),
        "band_lines": len(bands),
        "mut_rows": len(muts),
        "mut_src": len(muts) - len(non_src),
        "mut_non_src": len(non_src),
        "ac_ceremony_lines": len(ac_cer),
        "history_anchors": n_anchor,
        "history_anchors_linked": n_linked,
    }
    ev = [f"## {path}"]
    ev += [f"H  {h.strip()[:150]}" for h in hist_heads]
    ev += [f"Ah {a}" for a in sorted(ac_hist - ac_live)]
    ev += [f"L  {a}" for a in linked]
    ev += [f"R  {l.strip()[:230]}" for l in rounds]
    ev += [f"B  {l.strip()[:230]}" for l in bands]
    ev += [f"C  {l.strip()[:230]}" for l in ac_cer]
    ev += [f"Mn {l.strip()[:170]}" for l in non_src]
    return row, ev


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    plans = root / "workflow" / "plans"
    names = [n.strip() for n in (HERE / "files.txt").read_text().splitlines() if n.strip()]
    cols = None
    load_corpus(root)
    out, evidence = [], []
    missing = 0
    for name in names:
        p = plans / name
        if not p.is_file():
            missing += 1
            print(f"MISSING {name}", file=sys.stderr)
            continue
        row, ev = inventory(p)
        cols = cols or list(row)
        out.append("\t".join([name] + [str(row[c]) for c in cols]))
        evidence += ev + [""]
    (HERE / "inventory.tsv").write_text("file\t" + "\t".join(cols) + "\n" + "\n".join(out) + "\n")
    (HERE / "evidence.txt").write_text("\n".join(evidence) + "\n")
    weights = root / "tests" / "shard_weights.json"
    if weights.is_file():
        data = json.loads(weights.read_text())
        vals = data.get("weights", data) if isinstance(data, dict) else {}
        nums = [v for v in vals.values() if isinstance(v, (int, float))]
        print(f"shard_weights: {len(nums)} files, {sum(nums):.0f} s summed")
    print(f"files: {len(out)} inventoried, {missing} missing")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
