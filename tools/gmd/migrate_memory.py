#!/usr/bin/env python3
"""Bulk-add `gmd:` + `id:` frontmatter keys to Claude memory files.

Idempotent. Only edits files that:
  - have YAML frontmatter (start with `---`)
  - lack a `gmd:` key
  - aren't MEMORY.md (those are index files, separate handling)

For each qualifying file:
  - inserts `gmd: "0.1"` and `id: <filename-stem>` as first two keys after `---`
  - preserves all existing keys, body, and ordering of other keys
  - reports what changed

Usage:
  python3 migrate_memory.py <dir-or-file> [...]
  python3 migrate_memory.py --dry-run <dir>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def needs_migration(path: Path) -> tuple[bool, str]:
    """Return (should_edit, reason). reason is informational on skip."""
    if path.name == "MEMORY.md":
        return False, "index file (MEMORY.md)"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        return False, f"unreadable: {e}"
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return False, "no frontmatter"
    # find closing ---
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return False, "unterminated frontmatter"
    fm = lines[1:end]
    for ln in fm:
        if ln.split(":", 1)[0].strip() == "gmd":
            return False, "already has gmd: key"
    return True, "needs gmd: + id:"


def _derive_id(path: Path) -> str:
    """ID = path relative to the nearest enclosing `memory/` dir, dropping `.md`.

    Examples:
      memory/feedback_foo.md           -> feedback_foo
      memory/project/foo.md            -> project/foo
      memory/reference/sub/bar.md      -> reference/sub/bar

    Falls back to filename stem if no `memory/` ancestor found.
    """
    parts = path.resolve().parts
    if "memory" in parts:
        idx = len(parts) - 1 - parts[::-1].index("memory")
        rel = "/".join(parts[idx + 1:])
        if rel.endswith(".md"):
            rel = rel[:-3]
        if rel:
            return rel
    return path.stem


def migrate(path: Path, dry_run: bool = False) -> bool:
    """Return True if the file was (or would be) modified."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    # find closing ---
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return False

    derived_id = _derive_id(path)
    # Check if id: already present (some files may have it)
    has_id = False
    for ln in lines[1:end]:
        if ln.split(":", 1)[0].strip() == "id":
            has_id = True
            break

    new_keys = ['gmd: "0.1"\n']
    if not has_id:
        new_keys.append(f"id: {derived_id}\n")

    new_lines = lines[:1] + new_keys + lines[1:]

    if not dry_run:
        path.write_text("".join(new_lines), encoding="utf-8")
    return True


def collect(targets: list[Path]) -> list[Path]:
    out: list[Path] = []
    seen: set[Path] = set()
    for t in targets:
        if t.is_file():
            if t not in seen:
                out.append(t)
                seen.add(t)
        elif t.is_dir():
            for p in sorted(t.rglob("*.md")):
                if "memory" in p.parts and p not in seen:
                    out.append(p)
                    seen.add(p)
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("targets", nargs="+", type=Path)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv[1:])

    files = collect(args.targets)
    if not files:
        print("no files matched", file=sys.stderr)
        return 1

    changed: list[Path] = []
    skipped: list[tuple[Path, str]] = []

    for f in files:
        should, reason = needs_migration(f)
        if not should:
            skipped.append((f, reason))
            continue
        if migrate(f, dry_run=args.dry_run):
            changed.append(f)

    verb = "would update" if args.dry_run else "updated"
    print(f"{verb} {len(changed)} file(s); skipped {len(skipped)}")
    for f in changed[:30]:
        print(f"  + {f}")
    if len(changed) > 30:
        print(f"  + ... and {len(changed) - 30} more")
    if skipped:
        print("\nSkipped (sample):")
        for f, why in skipped[:10]:
            print(f"  - {f}: {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
