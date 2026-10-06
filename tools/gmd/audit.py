#!/usr/bin/env python3
"""gmd audit — report and repair GMD conformance gaps across a tree.

`gmd lint` answers "is this valid?" — it fails on broken structure and dangling
links. `gmd audit` answers the different question "is this fully GMD yet?", which
is what a conversion or cleanup pass needs: which files are still plain markdown,
which ids are missing their project namespace, which headings have no anchor.

Findings are grouped so a cleanup can be worked category by category rather than
file by file, and the mechanically unambiguous ones can be applied with --fix.

Usage:
  gmd audit <file-or-dir> [...]           # report
  gmd audit <file-or-dir> [...] --fix     # apply the safe repairs
  gmd audit <dir> --category unprefixed-id    # one category only
  gmd audit <dir> --quiet                 # summary table only
  gmd audit <dir> --manual                # only what --fix cannot repair
  gmd audit <dir> --manual --json         # JSONL work queue for an agent

--json emits one object per finding on stdout (the count goes to stderr, so the
stream stays machine-clean). For an unanchored heading it carries a `proposed`
kebab-case slug, the heading `level`, the raw `heading` text, and `collides` when
that slug would duplicate an anchor the doc already has or another proposal in the
same doc. An agent can group by `file`, apply the proposals it accepts in one pass
over each file, and stop only at the collisions:

  {"file":"docs/SYSTEM.md","line":42,"category":"unanchored-heading",
   "fixable":false,"detail":"...","proposed":"memory-layer-integration",
   "level":2,"heading":"Memory-layer integration"}

Proposals are never auto-applied. An anchor is a permanent address and renaming
one is a breaking change (SPEC §3), so the slug is a suggestion to approve, which
turns a naming exercise into a review.

Categories, and whether --fix touches them:

  FIXABLE
    missing-id        no `id:` in frontmatter -> derive from filename stem
    unprefixed-id     id carries no `<project>/` namespace (SPEC §project-namespace)
    bad-id-shape      leading/trailing `/` or `//` (SPEC §3)
    missing-title     no `title:` -> take the first H1's text
    no-root-anchor    no `{#root}` anywhere -> put it on the first H1

  REPORT-ONLY (the repair is a judgment call, not a transform)
    no-gmd            no `gmd:` key; the file is not GMD at all yet
    missing-tags      no `tags:`; which labels apply is editorial
    unanchored-heading   heading with no `{#id}`; a slug is PROPOSED but never
                         applied, since an anchor is a permanent address
    stem-mismatch     id's local part differs from the filename stem; the hint
                      names the canonical direction (align the id to the stem)
                      and when to rename the file instead

Exit status: 0 when no findings (or all findings fixed), 1 when findings remain.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lint  # noqa: E402  — reuse the linter's parser, id rules and namespace logic

# Files that are deliberately not GMD. MEMORY.md is the flat per-project memory
# index (see MEMORY-RULES §index); flagging it as unconverted is noise.
NOT_GMD_BY_DESIGN = {"MEMORY.md", "README.md", "CHANGELOG.md", "LICENSE.md"}

FIXABLE = {
    "missing-id", "unprefixed-id", "bad-id-shape",
    "missing-title", "no-root-anchor",
}
REPORT_ONLY = {"no-gmd", "missing-tags", "unanchored-heading", "stem-mismatch"}

SLUG_STRIP_RE = re.compile(r"[^a-z0-9]+")


def slugify(heading: str) -> str:
    """Propose a kebab-case anchor slug from heading text.

    A PROPOSAL only. An anchor is a permanent address — renaming one is a
    breaking change (SPEC §3) — so these are never auto-applied; they exist so
    reviewing 68 headings is 68 approvals rather than 68 naming exercises.
    """
    s = ANCHOR_RE.sub("", heading)
    s = re.sub(r"`[^`]*`", " ", s)              # inline code
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)  # links -> their text
    s = re.sub(r"[*_~]+", "", s)                 # emphasis
    s = SLUG_STRIP_RE.sub("-", s.lower()).strip("-")
    return s or "section"


H1_RE = re.compile(r"^#\s+(.*?)\s*$")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
ANCHOR_RE = re.compile(r"\{#([a-z0-9][a-z0-9._/-]*)[^}]*\}")


@dataclass
class Finding:
    path: Path
    line: int
    category: str
    detail: str
    fix: str | None = None   # human-readable description of what --fix would do
    # Agent-facing extras, emitted by --json and shown inline in the report.
    proposed: str | None = None    # suggested anchor slug / id, for review
    collides: bool = False         # proposal clashes with an existing or sibling anchor
    level: int | None = None       # heading depth, for unanchored-heading
    heading: str | None = None     # raw heading text
    hint: str | None = None        # which way a manual fix should go

    def as_dict(self, root: Path | None = None) -> dict:
        f = str(self.path)
        if root:
            try:
                f = str(self.path.resolve().relative_to(root))
            except ValueError:
                pass
        d = {"file": f, "line": self.line, "category": self.category,
             "fixable": self.category in FIXABLE, "detail": self.detail}
        for k in ("proposed", "collides", "level", "heading", "hint", "fix"):
            v = getattr(self, k)
            if v not in (None, False):
                d[k] = v
        return d


@dataclass
class FileReport:
    path: Path
    findings: list[Finding] = field(default_factory=list)


def _frontmatter(lines: list[str]) -> tuple[dict, int, int]:
    """(fields, fm_start, fm_end) — fm_end is the index of the closing `---`.
    (-1, -1) when the file has no frontmatter block."""
    if not lines or lines[0].strip() != "---":
        return {}, -1, -1
    for j, l in enumerate(lines[1:], 1):
        if l.strip() == "---":
            fm, _ = lint.parse_frontmatter(lines)
            return fm, 0, j
    return {}, -1, -1


def audit_file(path: Path) -> FileReport:
    rep = FileReport(path=path)
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    fm, _fm_start, fm_end = _frontmatter(lines)
    project = lint.project_name(path)

    # --- is it GMD at all? ---
    if not fm.get("gmd"):
        if path.name in NOT_GMD_BY_DESIGN:
            return rep
        rep.findings.append(Finding(
            path, 1, "no-gmd",
            "no `gmd:` key — file is plain markdown, not part of the graph",
        ))
        # Everything below assumes GMD intent; without it the rest is noise.
        return rep

    # --- id ---
    doc_id = fm.get("id")
    if not doc_id:
        suggested = f"{project}/{path.stem}" if project else path.stem
        rep.findings.append(Finding(
            path, 1, "missing-id", "no `id:` in frontmatter",
            f"add `id: {suggested}`",
        ))
    else:
        shape = lint.id_shape_issue(path, 1, "bad-id-shape", doc_id)
        if shape:
            cleaned = re.sub(r"/{2,}", "/", doc_id).strip("/")
            rep.findings.append(Finding(
                path, 1, "bad-id-shape", shape.msg,
                f"rewrite as `id: {cleaned}`",
            ))
        elif "/" not in doc_id and project:
            rep.findings.append(Finding(
                path, 1, "unprefixed-id",
                f"id `{doc_id}` has no project namespace",
                f"rewrite as `id: {project}/{doc_id}`",
            ))
        local = doc_id.rsplit("/", 1)[-1]
        if local and local != path.stem:
            # MEMORY-RULES §frontmatter and the primer both say the id should
            # equal the filename stem. The stem is the stable filesystem
            # address, so aligning the id to it is the canonical direction;
            # renaming the file is right only when the current id is the
            # address other docs already use.
            # An id must match `[a-z0-9][a-z0-9._/-]*` (SPEC §3), so a stem
            # like `SPEC` or `My Doc` cannot BE an id. Proposing one anyway
            # would hand back an invalid address, so in that case the honest
            # answer is that the mismatch cannot be closed by aligning the id.
            ns = doc_id.rsplit("/", 1)[0] if "/" in doc_id else project
            legal_stem = bool(re.fullmatch(r"[a-z0-9][a-z0-9._-]*", path.stem))
            if legal_stem:
                aligned = f"{ns}/{path.stem}" if ns else path.stem
                hint = (f"canonical: set `id: {aligned}` to match the stem; "
                        f"rename the file to `{local}.md` instead only if "
                        f"`{doc_id}` is the address other docs already reference")
            else:
                aligned = None
                hint = (f"filename stem `{path.stem}` is not a legal id "
                        f"(SPEC §3 requires [a-z0-9][a-z0-9._/-]*), so the id "
                        f"cannot be aligned to it — either rename the file to "
                        f"`{local}.md` or accept the mismatch deliberately")
            rep.findings.append(Finding(
                path, 1, "stem-mismatch",
                f"id local part `{local}` != filename stem `{path.stem}`",
                proposed=aligned, hint=hint,
            ))

    # --- title / tags ---
    first_h1 = next(
        ((i, m.group(1)) for i, l in enumerate(lines)
         if (m := H1_RE.match(l)) and i > fm_end),
        None,
    )
    if not fm.get("title"):
        if first_h1:
            clean = ANCHOR_RE.sub("", first_h1[1]).strip()
            rep.findings.append(Finding(
                path, 1, "missing-title", "no `title:` in frontmatter",
                f'add `title: "{clean}"` (from the first H1)',
            ))
        else:
            rep.findings.append(Finding(
                path, 1, "missing-title",
                "no `title:` and no H1 to derive one from",
            ))
    if not fm.get("tags"):
        rep.findings.append(Finding(path, 1, "missing-tags", "no `tags:`"))

    # --- anchors ---
    in_fence = False
    anchored_ids: set[str] = set()
    unanchored: list[tuple[int, int, str]] = []
    for i, raw in enumerate(lines, 1):
        if i <= fm_end + 1:
            continue
        if lint.CODE_FENCE_RE.match(raw.strip()):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        # Anchors are detected on the inline-code-stripped line so a `{#x}`
        # inside backticks is not mistaken for a real anchor. The heading TEXT,
        # though, is read from the raw line — an agent needs what the file
        # actually says, not a version with its code spans blanked out.
        scan = lint.strip_inline_code(raw)
        anchored_ids.update(m.group(1) for m in ANCHOR_RE.finditer(scan))
        hm = HEADING_RE.match(scan)
        if hm and not ANCHOR_RE.search(scan):
            raw_hm = HEADING_RE.match(raw.rstrip())
            text = raw_hm.group(2) if raw_hm else hm.group(2)
            unanchored.append((i, len(hm.group(1)), text))

    if "root" not in anchored_ids:
        if first_h1:
            rep.findings.append(Finding(
                path, first_h1[0] + 1, "no-root-anchor",
                "no `{#root}` anchor in the document",
                "add `{#root}` to the first H1",
            ))
        else:
            rep.findings.append(Finding(
                path, 1, "no-root-anchor",
                "no `{#root}` anchor and no H1 to attach one to",
            ))
    # Propose a slug per unanchored heading. A proposal collides when it
    # duplicates an anchor the doc already has, or another proposal in the same
    # doc — two different headings can slugify identically. Flagged, not
    # silently de-duplicated: a bad address is worse than an absent one.
    proposed_seen: dict[str, int] = {}
    for line_no, level, htext in unanchored:
        slug = slugify(htext)
        clash = slug in anchored_ids or slug in proposed_seen
        proposed_seen[slug] = proposed_seen.get(slug, 0) + 1
        rep.findings.append(Finding(
            path, line_no, "unanchored-heading",
            f"heading `{htext[:52]}` has no `{{#id}}`",
            proposed=slug, collides=clash, level=level, heading=htext,
            hint=("proposed slug duplicates an existing anchor or another "
                  "proposal in this doc — pick a distinct one"
                  if clash else None),
        ))
    return rep


def apply_fixes(rep: FileReport) -> list[str]:
    """Apply the FIXABLE findings for one file. Returns what was changed."""
    fixable = [f for f in rep.findings if f.category in FIXABLE and f.fix]
    if not fixable:
        return []
    text = rep.path.read_text(encoding="utf-8")
    lines = text.splitlines()
    fm, _s, fm_end = _frontmatter(lines)
    if fm_end < 0:
        return []
    done: list[str] = []

    def set_fm(key: str, value: str) -> None:
        for i in range(1, fm_end):
            if lines[i].startswith(f"{key}:"):
                lines[i] = f"{key}: {value}"
                return
        lines.insert(fm_end, f"{key}: {value}")

    project = lint.project_name(rep.path)
    for f in fixable:
        if f.category in ("missing-id", "unprefixed-id", "bad-id-shape"):
            cur = fm.get("id")
            if f.category == "missing-id":
                new = f"{project}/{rep.path.stem}" if project else rep.path.stem
            elif f.category == "unprefixed-id":
                new = f"{project}/{cur}"
            else:
                new = re.sub(r"/{2,}", "/", str(cur)).strip("/")
            set_fm("id", new)
            done.append(f"id -> {new}")
        elif f.category == "missing-title":
            h1m = next((m for i, l in enumerate(lines)
                        if i > fm_end and (m := H1_RE.match(l))), None)
            if h1m:
                title = ANCHOR_RE.sub("", h1m.group(1)).strip()
                set_fm("title", f'"{title}"')
                done.append(f"title -> {title}")
        elif f.category == "no-root-anchor":
            for i, l in enumerate(lines):
                if i > fm_end and H1_RE.match(l) and not ANCHOR_RE.search(l):
                    lines[i] = l.rstrip() + " {#root}"
                    done.append("added {#root} to the first H1")
                    break
    if done:
        rep.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return done


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        prog="gmd audit", add_help=True,
        description="Report and repair GMD conformance gaps.")
    ap.add_argument("targets", nargs="+", help="files or directories")
    ap.add_argument("--fix", action="store_true",
                    help="apply the mechanically safe repairs")
    ap.add_argument("--category", action="append", default=[],
                    help="restrict to a category (repeatable)")
    ap.add_argument("--quiet", action="store_true",
                    help="summary table only, no per-file detail")
    ap.add_argument("--manual", action="store_true",
                    help=f"only the categories --fix cannot repair "
                         f"({', '.join(sorted(REPORT_ONLY))})")
    ap.add_argument("--json", action="store_true",
                    help="emit one JSON object per finding (JSONL) for an agent "
                         "to consume; suppresses the human report")
    args = ap.parse_args(argv[1:])

    root = lint._repo_root(Path(args.targets[0]))
    ignore = lint.load_config(root).get("ignore") if root else []
    files = lint.collect_files(args.targets, ignore or [])
    if not files:
        print("gmd audit: no files matched", file=sys.stderr)
        return 2

    reports = [audit_file(f) for f in files]
    keep = set(args.category)
    if args.manual:
        keep |= REPORT_ONLY
    if keep:
        for r in reports:
            r.findings = [f for f in r.findings if f.category in keep]

    fixed_counts: dict[str, int] = defaultdict(int)
    if args.fix:
        for r in reports:
            for _ in apply_fixes(r):
                pass
            # Re-audit so the report reflects reality after the write.
            before = {f.category for f in r.findings if f.category in FIXABLE}
            r.findings = audit_file(r.path).findings
            if keep:
                r.findings = [f for f in r.findings if f.category in keep]
            after = {f.category for f in r.findings}
            for c in before - after:
                fixed_counts[c] += 1

    by_cat: dict[str, list[Finding]] = defaultdict(list)
    for r in reports:
        for f in r.findings:
            by_cat[f.category].append(f)

    if args.json:
        out = sys.stdout
        for r in sorted(reports, key=lambda r: str(r.path)):
            for f in sorted(r.findings, key=lambda f: (f.line, f.category)):
                out.write(json.dumps(f.as_dict(root), sort_keys=False) + "\n")
        total = sum(len(r.findings) for r in reports)
        print(f"gmd audit: {len(files)} files, {total} findings", file=sys.stderr)
        return 1 if total else 0

    if not args.quiet:
        for r in sorted(reports, key=lambda r: str(r.path)):
            if not r.findings:
                continue
            print(f"\n{r.path}")
            for f in sorted(r.findings, key=lambda f: (f.line, f.category)):
                tag = "FIX" if f.category in FIXABLE else "   "
                print(f"  {tag} {f.line:>4}: [{f.category}] {f.detail}")
                if f.fix and not args.fix:
                    print(f"            -> {f.fix}")
                elif f.proposed and f.category == "unanchored-heading":
                    flag = "  !! COLLIDES" if f.collides else ""
                    print(f"            -> propose {{#{f.proposed}}}{flag}")
                elif f.hint:
                    print(f"            -> {f.hint}")

    total = sum(len(v) for v in by_cat.values())
    clean = sum(1 for r in reports if not r.findings)
    print(f"\ngmd audit: {len(files)} files, {clean} clean, {total} findings")
    if by_cat:
        width = max(len(c) for c in by_cat)
        for cat in sorted(by_cat, key=lambda c: (-len(by_cat[c]), c)):
            kind = "fixable" if cat in FIXABLE else "manual"
            print(f"  {cat:<{width}}  {len(by_cat[cat]):>4}  ({kind})")
    if fixed_counts:
        print("\n  repaired:")
        for cat, n in sorted(fixed_counts.items()):
            print(f"    {cat}: {n} file(s)")
    remaining_fixable = sum(len(v) for c, v in by_cat.items() if c in FIXABLE)
    if remaining_fixable and not args.fix:
        print(f"\n  {remaining_fixable} finding(s) are fixable: re-run with --fix")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
