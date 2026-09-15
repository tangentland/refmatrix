#!/usr/bin/env python3
"""gmd slice — retrieve a relevant subset of a GMD document for a query.

Algorithm:
  1. Parse doc into nodes (heading-bounded sections with anchors).
  2. Score nodes by term overlap with query (TF * IDF, title weighted 3x).
  3. Take top-K as seeds.
  4. Expand: include all ancestors (context) + 1-hop rel:/wikilink neighbors.
  5. Render selected nodes in document order with gap markers.
  6. Report token estimates (chars/4) for full doc vs slice.

Usage:
  gmd slice <file.gmd> "<query>" [--k 5] [--hops 1] [--no-neighbors]
                                 [--budget-tokens 2000] [--show-edges]

Exit codes:
  0 = ok, 1 = no nodes matched, 2 = invocation error.
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ID_RE = re.compile(r"\{#([a-z0-9][a-z0-9._/-]*)([^}]*)\}")
WIKILINK_RE = re.compile(r"\[\[([^\[\]]+)\]\]")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
REL_RE = re.compile(
    r"^rel:\s+([a-z][a-z0-9-]*)\s*->\s*(\S+(?:\s+\S+)*?)(?:\s*\{([^}]*)\})?\s*$"
)
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
CODE_FENCE_RE = re.compile(r"^(```|~~~)")
FRONTMATTER_DELIM = "---"
TOKEN_RE = re.compile(r"[a-z0-9]{2,}")

STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "then", "else", "to", "of",
    "for", "in", "on", "at", "by", "is", "are", "was", "were", "be", "been",
    "do", "does", "did", "what", "where", "when", "why", "how", "this", "that",
    "these", "those", "with", "from", "as", "it", "its", "not", "no",
}


@dataclass
class Node:
    id: str
    line: int
    level: int
    title: str
    parent: str | None = None
    children: list[str] = field(default_factory=list)
    body_lines: list[str] = field(default_factory=list)
    rels: list[tuple[int, str, str]] = field(default_factory=list)
    refs: list[str] = field(default_factory=list)
    attrs: dict[str, str] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return " ".join([self.title, *self.body_lines])

    @property
    def is_synthetic_root(self) -> bool:
        return self.id == "__root__"


def parse_attrs(s: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for tok in re.findall(r'([a-zA-Z_][\w-]*)=("[^"]*"|\S+)', s):
        out[tok[0]] = tok[1].strip('"')
    return out


def parse(path: Path) -> tuple[list[str], list[Node], dict[str, Node], int]:
    """Return (raw_lines, nodes_in_doc_order, by_id, frontmatter_end_line)."""
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()

    # Skip frontmatter for node parsing
    body_start = 0
    if lines and lines[0].strip() == FRONTMATTER_DELIM:
        for i in range(1, len(lines)):
            if lines[i].strip() == FRONTMATTER_DELIM:
                body_start = i + 1
                break

    nodes: list[Node] = []
    by_id: dict[str, Node] = {}

    root = Node(id="__root__", line=body_start, level=0, title="(root)")
    nodes.append(root)
    by_id[root.id] = root

    stack: list[Node] = [root]
    current = root
    in_code = False
    auto_idx = 0

    def push(node: Node) -> None:
        nonlocal current
        while stack and stack[-1].level >= node.level:
            stack.pop()
        parent = stack[-1] if stack else root
        node.parent = parent.id
        parent.children.append(node.id)
        stack.append(node)
        nodes.append(node)
        by_id[node.id] = node
        current = node

    for idx in range(body_start, len(lines)):
        line = lines[idx]
        line_no = idx + 1
        if CODE_FENCE_RE.match(line.strip()):
            in_code = not in_code
            current.body_lines.append(line)
            continue
        if in_code:
            current.body_lines.append(line)
            continue

        scan = INLINE_CODE_RE.sub(lambda m: " " * len(m.group(0)), line)

        hm = HEADING_RE.match(line)
        if hm:
            level = len(hm.group(1))
            heading_rest = hm.group(2)
            id_match = ID_RE.search(heading_rest)
            if id_match:
                node_id = id_match.group(1)
                attrs = parse_attrs(id_match.group(2))
                title = ID_RE.sub("", heading_rest).strip()
            else:
                auto_idx += 1
                node_id = f"_h{auto_idx}"
                attrs = {}
                title = heading_rest.strip()
            if node_id in by_id:
                # duplicate — disambiguate
                node_id = f"{node_id}_{auto_idx}"
                auto_idx += 1
            node = Node(
                id=node_id, line=line_no, level=level,
                title=title, attrs=attrs,
            )
            push(node)
            continue

        # rel: line
        rm = REL_RE.match(line) if line.startswith("rel:") else None
        if rm:
            verb = rm.group(1)
            target = rm.group(2).strip()
            current.rels.append((line_no, verb, target))
            current.body_lines.append(line)
            continue

        # body line
        current.body_lines.append(line)

        # also harvest non-rel wikilink refs for graph expansion
        for wm in WIKILINK_RE.finditer(scan):
            ref = wm.group(1).strip()
            current.refs.append(ref)

    return lines, nodes, by_id, body_start


# ---------------- scoring ----------------

def tokenize(s: str) -> list[str]:
    return [t for t in TOKEN_RE.findall(s.lower()) if t not in STOPWORDS]


def score(nodes: list[Node], query: str) -> dict[str, float]:
    q_terms = tokenize(query)
    if not q_terms:
        return {}
    # df per term
    df: dict[str, int] = {}
    scored = [n for n in nodes if not n.is_synthetic_root]
    N = max(len(scored), 1)
    for n in scored:
        toks = set(tokenize(n.text))
        for t in q_terms:
            if t in toks:
                df[t] = df.get(t, 0) + 1
    idf = {t: math.log(1 + N / (1 + df.get(t, 0))) for t in q_terms}

    out: dict[str, float] = {}
    for n in scored:
        title_toks = tokenize(n.title)
        body_toks = tokenize(" ".join(n.body_lines))
        s = 0.0
        for t in q_terms:
            tf_title = title_toks.count(t)
            tf_body = body_toks.count(t)
            if tf_title or tf_body:
                s += (3 * tf_title + tf_body) * idf[t]
        if s > 0:
            out[n.id] = s
    return out


# ---------------- graph expansion ----------------

def _split_ref(ref: str) -> tuple[str | None, str]:
    ref = ref.strip()
    if ref.startswith("#"):
        return None, ref[1:]
    if "#" in ref:
        doc_id, _, anchor = ref.partition("#")
        return doc_id, anchor
    return ref, ""


def expand(
    seeds: set[str], by_id: dict[str, Node],
    hops: int = 1, include_neighbors: bool = True,
) -> set[str]:
    selected = set(seeds)

    # include ancestors of every seed
    for sid in list(seeds):
        cur = by_id.get(sid)
        while cur and cur.parent:
            selected.add(cur.parent)
            cur = by_id.get(cur.parent)

    if not include_neighbors:
        return selected

    frontier = set(seeds)
    for _ in range(hops):
        next_frontier: set[str] = set()
        for nid in frontier:
            n = by_id.get(nid)
            if not n:
                continue
            for _, _, target in n.rels:
                for wm in WIKILINK_RE.finditer(target):
                    _, anchor = _split_ref(wm.group(1))
                    if anchor and anchor in by_id and anchor not in selected:
                        selected.add(anchor)
                        next_frontier.add(anchor)
            for ref in n.refs:
                _, anchor = _split_ref(ref)
                if anchor and anchor in by_id and anchor not in selected:
                    selected.add(anchor)
                    next_frontier.add(anchor)
        # always pull ancestors of newly-added neighbors
        for nid in list(next_frontier):
            cur = by_id.get(nid)
            while cur and cur.parent:
                selected.add(cur.parent)
                cur = by_id.get(cur.parent)
        frontier = next_frontier
        if not frontier:
            break
    return selected


# ---------------- render ----------------

def render_slice(
    raw_lines: list[str], nodes: list[Node],
    selected: set[str], frontmatter_end: int,
    show_edges: bool = False,
) -> str:
    out: list[str] = []
    # frontmatter passthrough
    if frontmatter_end > 0:
        out.extend(raw_lines[:frontmatter_end])
        out.append("")

    out.append(f"<!-- gmd slice: {len(selected) - 1} nodes selected -->")
    out.append("")

    prev_selected = True
    for n in nodes:
        if n.is_synthetic_root:
            continue
        if n.id in selected:
            if not prev_selected:
                out.append("")
                out.append("...")
                out.append("")
            heading = "#" * n.level + " " + n.title
            if n.id and not n.id.startswith("_h"):
                heading += f" {{#{n.id}}}"
            out.append(heading)
            for ln in n.body_lines:
                out.append(ln)
            if show_edges and n.rels:
                out.append("")
                out.append(f"<!-- edges: {len(n.rels)} -->")
            prev_selected = True
        else:
            prev_selected = False
    return "\n".join(out) + "\n"


def tokens(s: str) -> int:
    return max(1, len(s) // 4)


# ---------------- cli ----------------

def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="gmd slice", description=__doc__)
    ap.add_argument("file", type=Path)
    ap.add_argument("query", type=str)
    ap.add_argument("--k", type=int, default=5, help="top-K seed nodes")
    ap.add_argument("--hops", type=int, default=1, help="graph expansion hops")
    ap.add_argument("--no-neighbors", action="store_true",
                    help="skip neighbor expansion (ancestors only)")
    ap.add_argument("--show-edges", action="store_true")
    ap.add_argument("--budget-tokens", type=int, default=0,
                    help="drop lowest-scored seeds until under budget (0=off)")
    ap.add_argument("--print-scores", action="store_true")
    args = ap.parse_args(argv[1:])

    if not args.file.exists():
        print(f"gmd slice: file not found: {args.file}", file=sys.stderr)
        return 2

    raw_lines, nodes, by_id, fm_end = parse(args.file)
    scores = score(nodes, args.query)

    if not scores:
        print("gmd slice: no nodes matched query terms", file=sys.stderr)
        return 1

    ranked = sorted(scores.items(), key=lambda kv: -kv[1])

    if args.print_scores:
        for nid, sc in ranked[:20]:
            n = by_id[nid]
            print(f"  {sc:6.2f}  {nid:40s}  {n.title[:60]}", file=sys.stderr)

    full_text = "\n".join(raw_lines)
    full_tok = tokens(full_text)

    seeds = {nid for nid, _ in ranked[: args.k]}
    selected = expand(
        seeds, by_id, hops=args.hops,
        include_neighbors=not args.no_neighbors,
    )
    rendered = render_slice(
        raw_lines, nodes, selected, fm_end, show_edges=args.show_edges,
    )

    # budget enforcement: shrink seeds until under budget
    if args.budget_tokens > 0:
        k = args.k
        while tokens(rendered) > args.budget_tokens and k > 1:
            k -= 1
            seeds = {nid for nid, _ in ranked[:k]}
            selected = expand(
                seeds, by_id, hops=args.hops,
                include_neighbors=not args.no_neighbors,
            )
            rendered = render_slice(
                raw_lines, nodes, selected, fm_end, show_edges=args.show_edges,
            )

    slice_tok = tokens(rendered)
    print(rendered)

    pct = 100.0 * slice_tok / full_tok if full_tok else 0.0
    print(
        f"\n--- gmd slice report ---\n"
        f"query: {args.query!r}\n"
        f"seeds: {len(seeds)} top-K, expanded to {len(selected) - 1} nodes\n"
        f"tokens: {slice_tok} slice / {full_tok} full  ({pct:.1f}%)\n"
        f"saved:  ~{full_tok - slice_tok} tokens "
        f"({100.0 - pct:.1f}% reduction)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
