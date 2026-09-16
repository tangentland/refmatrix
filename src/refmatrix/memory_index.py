"""Generate `MEMORY.md` — the flat memory index — under a hard line cap.

`MEMORY-RULES.md` caps the index at 200 lines because everything past that is
cut when the file is loaded into a session's context. Nothing enforced it:
`handoff._ss_update_index` appends one line per memory and never collapses
anything, so the index grew monotonically and on 2026-09-16 stood at 234 lines /
34 KB — the last 34 entries silently unreachable from the surface whose entire
job is to reach them. The memories were on disk the whole time.

Three rules, in the order they fire:

1. **Keep the hooks.** The one-line descriptions are hand-written and are the
   value of the index; regenerating them from titles would destroy the curation
   this is meant to protect. Existing hooks are parsed out of the current file
   and reused verbatim (truncated, never rewritten). Only a memory with no entry
   yet gets a hook derived from its title.
2. **Collapse what is a pointer rather than content.** Impressions are an
   agent's cross-run ledger, already indexed in `workflow/bullshit/
   IMPRESSIONS.md`; save-states are read by `rmx recall-state`, which always
   wants the newest. Both become a single line that says how many they stand
   for, so nothing is hidden — it is summarised.
3. **Fold the oldest PROJECT notes last, and never feedback.** Feedback is how
   the user corrects behaviour and it outranks a project note when something has
   to give; project notes are recoverable through `rmx memory list` and the
   store, and the fold line says how many were folded.

Run by hand or in a check:

    python3 -m refmatrix.memory_index <memdir> [--check]
"""
from __future__ import annotations

import sys
from pathlib import Path

# Past this width an entry stops being a one-line hook and starts being prose
# that pushes the cap down for everyone else.
MAX_LINE_CHARS = 200

# The cap `MEMORY-RULES.md` names.
MAX_LINES = 200

INDEX_NAME = "MEMORY.md"

# Files in the memory dir that are not memories.
_NOT_A_MEMORY = {INDEX_NAME, "README.md"}


def _frontmatter(text: str) -> dict:
    """Minimal frontmatter read: `title` and `metadata.type` only.

    Deliberately not a YAML parse — the memory dir is GMD with a fixed shape,
    and a dependency here would run on every save-state.
    """
    out: dict = {}
    if not text.startswith("---"):
        return out
    body = text.split("---", 2)
    if len(body) < 3:
        return out
    in_meta = False
    for raw in body[1].splitlines():
        line = raw.rstrip()
        if not line:
            continue
        if line.startswith("metadata:"):
            in_meta = True
            continue
        if in_meta and not line.startswith(" "):
            in_meta = False
        key, _, val = line.strip().partition(":")
        val = val.strip().strip('"').strip("'")
        if in_meta:
            if key.strip() == "type":
                out["type"] = val
            elif key.strip() in ("created", "updated"):
                out.setdefault(key.strip(), val)
        elif key.strip() in ("id", "title"):
            out[key.strip()] = val
    return out


def _first_prose(text: str) -> str:
    """The first non-heading, non-`rel:` body line — the fallback hook."""
    seen_h1 = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("# "):
            seen_h1 = True
            continue
        if not seen_h1 or not line:
            continue
        if line.startswith(("#", "rel:", "---", "```", "|", ">")):
            continue
        return line
    return ""


class Entry:
    __slots__ = ("path", "rel", "title", "mtype", "hook", "mtime", "created")

    def __init__(self, path: Path, memdir: Path, hooks: dict):
        self.path = path
        self.rel = str(path.relative_to(memdir))
        text = path.read_text(errors="replace")
        fm = _frontmatter(text)
        self.title = fm.get("title") or path.stem
        self.mtype = fm.get("type") or path.stem.split("_")[0]
        self.mtime = path.stat().st_mtime
        self.created = fm.get("created") or ""
        # Rule 1: a curated hook wins over anything derived.
        self.hook = hooks.get(self.rel) or _first_prose(text)

    @property
    def kind(self) -> str:
        if self.rel.startswith("impressions/"):
            return "impression"
        if self.path.stem.startswith("savestate_"):
            return "savestate"
        if self.mtype.startswith("feedback"):
            return "feedback"
        if self.mtype.startswith("reference"):
            return "reference"
        return "project"

    def line(self) -> str:
        out = f"- [{self.title}]({self.rel})"
        if self.hook:
            out = f"{out} — {self.hook}"
        if len(out) > MAX_LINE_CHARS:
            out = out[:MAX_LINE_CHARS - 1].rstrip() + "…"
        return out


def parse_hooks(idx: Path) -> dict:
    """`{relative path: hook}` from an existing index. Hand-written text, so it
    is read back rather than regenerated."""
    hooks: dict = {}
    if not idx.exists():
        return hooks
    for line in idx.read_text(errors="replace").splitlines():
        if not line.startswith("- ["):
            continue
        # Split at the LINK, not at the first em dash: titles contain " — "
        # themselves ("Capture reasoning deliberately — extended-thinking is
        # redacted"), so partitioning on the dash stole half the title into the
        # hook and the next render shifted it again — a generator that was not
        # idempotent on its own output. Caught on the real index, not in a
        # fixture, because the fixture titles had no dashes (2026-09-16).
        head, sep, rest = line.partition("](")
        if not sep:
            continue
        rel, sep, tail = rest.partition(")")
        if not sep:
            continue
        hook = tail.lstrip()
        if hook.startswith("—"):
            hook = hook[1:]
        hooks[rel] = hook.strip()
    return hooks


def collect(memdir: Path) -> list:
    idx = memdir / INDEX_NAME
    hooks = parse_hooks(idx)
    out = []
    for p in sorted(memdir.glob("*.md")) + sorted(memdir.glob("impressions/*.md")):
        if p.name in _NOT_A_MEMORY:
            continue
        out.append(Entry(p, memdir, hooks))
    return out


def render(memdir: Path, *, max_lines: int = MAX_LINES) -> str:
    entries = collect(memdir)
    by = {}
    for e in entries:
        by.setdefault(e.kind, []).append(e)

    lines: list = []
    for kind in ("feedback", "reference", "project"):
        lines.extend(e.line() for e in by.get(kind, []))

    # Rule 2: the pointer classes.
    imps = by.get("impression", [])
    if imps:
        lines.append(
            f"- [ch-bsd impressions ({len(imps)})](impressions/) — cross-run audit "
            f"memories; full ledger in `workflow/bullshit/IMPRESSIONS.md`")
    # By DATE, not by stem: save-state ids are session hashes
    # (`savestate_fd45323ccbb8`), so sorting the names picked an arbitrary one
    # and called it newest. `created` comes from the frontmatter, mtime is the
    # tiebreak.
    saves = sorted(by.get("savestate", []), key=lambda e: (e.created, e.mtime))
    if saves:
        newest = saves[-1]
        lines.append(
            f"- [Save-states ({len(saves)}), newest {newest.path.stem}]"
            f"({newest.rel}) — session handoffs; `rmx recall-state` reads the newest")

    # Rule 3: fold the oldest project notes, never feedback, and say the count.
    if len(lines) > max_lines:
        projects = sorted(by.get("project", []), key=lambda e: e.mtime)
        need = len(lines) - max_lines + 1        # +1 for the fold line itself
        fold = projects[:max(0, need)]
        folded = {e.rel for e in fold}
        lines = [l for l in lines
                 if not any(f"]({rel})" in l for rel in folded)]
        lines.append(
            f"- {len(fold)} older project memories folded — `rmx memory list` or "
            f"`rmx memory search <term>` reaches them; nothing was deleted")
    return "\n".join(lines) + "\n"


def write(memdir: Path, *, max_lines: int = MAX_LINES, out=None) -> int:
    """Rewrite the index. Returns the number of lines written, and SAYS what it
    did — a silent rewrite of the memory index is the shape this project's
    no-silent-failures rule exists to prevent."""
    out = out or sys.stdout
    memdir = Path(memdir)
    idx = memdir / INDEX_NAME
    before = len(idx.read_text(errors="replace").splitlines()) if idx.exists() else 0
    text = render(memdir, max_lines=max_lines)
    after = len(text.splitlines())
    idx.write_text(text)
    print(f"{INDEX_NAME}: {before} -> {after} lines "
          f"(cap {max_lines}; {len(collect(memdir))} memories on disk)", file=out)
    return after


def check(memdir: Path, *, max_lines: int = MAX_LINES) -> bool:
    """True when the index on disk equals what `render` would write."""
    memdir = Path(memdir)
    idx = memdir / INDEX_NAME
    if not idx.exists():
        return False
    return idx.read_text(errors="replace") == render(memdir, max_lines=max_lines)


def main(argv: "list[str] | None" = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    checking = "--check" in args
    args = [a for a in args if not a.startswith("--")]
    if not args:
        print("usage: python3 -m refmatrix.memory_index <memdir> [--check]",
              file=sys.stderr)
        return 2
    memdir = Path(args[0])
    if checking:
        ok = check(memdir)
        print(f"{INDEX_NAME}: {'in sync' if ok else 'STALE — run without --check'}")
        return 0 if ok else 1
    write(memdir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
