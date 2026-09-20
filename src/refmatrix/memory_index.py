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

import json
import os
import sys
from pathlib import Path

# Past this width an entry stops being a one-line hook and starts being prose
# that pushes the cap down for everyone else.
MAX_LINE_CHARS = 200

# The cap `MEMORY-RULES.md` names. Advisory: it shapes the index, it does not
# decide whether the index survives the load -- MAX_INDEX_CHARS does.
MAX_LINES = 200

# THE cap that matters. The loader that truncates MEMORY.md counts CHARACTERS
# against a ~24.4 KiB budget; it does not count lines, and it does not count
# bytes. bug-042 capped lines, `--check` reported "in sync", and 38 entries
# stayed unreachable -- the cap was on a dimension nothing enforces (bug-045).
#
# The unit was settled by measuring the live index (197 lines / 31,607 bytes /
# 31,043 chars) against the session banner, which read "MEMORY.md is 30.3KB
# (limit: 24.4KB) ... 38 of 197 lines were cut off, starting at line 160":
#
#   unit=bytes, budget 24.4 KiB -> first line past budget 157, 41 cut
#   unit=chars, budget 24.4 KiB -> first line past budget 160, 38 cut  <-- banner
#   chars/1024 = 30.3 KiB                                              <-- banner
#
# Characters reproduce both banner numbers exactly; bytes reproduce neither.
# The default keeps ~1 KiB of headroom under the observed limit because the
# number belongs to the harness doing the loading, not to rmx -- hence the env
# override, so a changed limit does not need a release.
MAX_INDEX_CHARS = int(os.environ.get("RMX_MEMORY_INDEX_CHARS") or 24000)

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


HOOKS_SIDECAR = ".memory_hooks.json"


def load_hooks(memdir: Path) -> dict:
    """Curated hooks: the index PLUS the sidecar of hooks for folded entries.

    Without the sidecar the generator is not idempotent on its own output
    (bug-050). `parse_hooks` can only see entries the index still lists, so a
    folded entry loses its curated hook, falls back to derived prose — usually
    LONGER — which grows the render and folds two more. Rendering the live
    index from itself moved the fold 56 -> 58 with no memory added, and
    `--check` read out of sync immediately after a successful write. Every
    save-state would have degraded the index a little further.
    """
    hooks: dict = {}
    side = memdir / HOOKS_SIDECAR
    if side.exists():
        try:
            data = json.loads(side.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                hooks.update({str(k): str(v) for k, v in data.items()})
        except Exception as exc:  # noqa: BLE001 — named, never mute
            print(f"{INDEX_NAME}: hook sidecar unreadable ({type(exc).__name__}: "
                  f"{exc}); folded entries may lose their curated hooks",
                  file=sys.stderr)
    # The index wins: it is what a human last edited by hand.
    hooks.update(parse_hooks(memdir / INDEX_NAME))
    return hooks


def save_hooks(memdir: Path, entries: list) -> None:
    """Persist every entry's hook, listed or folded, so curation survives a
    fold. Written on the same call that rewrites the index."""
    side = memdir / HOOKS_SIDECAR
    data = {e.rel: e.hook for e in entries if e.hook}
    try:
        side.write_text(json.dumps(data, indent=0, sort_keys=True,
                                   ensure_ascii=False), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001 — named, never mute
        print(f"{INDEX_NAME}: could not write hook sidecar "
              f"({type(exc).__name__}: {exc}); folded entries will lose their "
              f"curated hooks on the next render", file=sys.stderr)


def collect(memdir: Path) -> list:
    hooks = load_hooks(memdir)
    out = []
    for p in sorted(memdir.glob("*.md")) + sorted(memdir.glob("impressions/*.md")):
        if p.name in _NOT_A_MEMORY:
            continue
        out.append(Entry(p, memdir, hooks))
    return out


def render(memdir: Path, *, max_lines: int = MAX_LINES,
           max_chars: int = MAX_INDEX_CHARS) -> str:
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
    #
    # Two budgets, and the CHARACTER one is the one that decides whether the
    # tail is readable at all (bug-045). Folding is driven by both: take the
    # larger of what the line cap needs and what the char cap needs, then
    # verify the rendered result actually fits instead of assuming the
    # arithmetic did -- the fold line itself has a length, and so does every
    # line that survives.
    projects = sorted(by.get("project", []), key=lambda e: e.mtime)

    def _assemble(fold_n: int) -> str:
        if fold_n <= 0:
            return "\n".join(lines) + "\n"
        fold = projects[:fold_n]
        folded = {e.rel for e in fold}
        kept = [l for l in lines
                if not any(f"]({rel})" in l for rel in folded)]
        kept.append(
            f"- {len(fold)} older project memories folded — `rmx memory list` or "
            f"`rmx memory search <term>` reaches them; nothing was deleted")
        return "\n".join(kept) + "\n"

    need = len(lines) - max_lines + 1 if len(lines) > max_lines else 0
    text = _assemble(need)
    # Grow the fold until the rendered text fits the char budget. Bounded by
    # the number of foldable entries: when they run out the index is as small
    # as folding can make it, and `write()` says so rather than pretending.
    while len(text) > max_chars and need < len(projects):
        # Estimate the shortfall in entries rather than stepping one at a time:
        # a 400-entry index would otherwise re-render 250 times.
        over = len(text) - max_chars
        mean = max(1, (len(text) // max(1, len(lines))))
        need = min(len(projects), need + max(1, over // mean))
        text = _assemble(need)
    return text


def write(memdir: Path, *, max_lines: int = MAX_LINES,
          max_chars: int = MAX_INDEX_CHARS, out=None) -> int:
    """Rewrite the index. Returns the number of lines written, and SAYS what it
    did — a silent rewrite of the memory index is the shape this project's
    no-silent-failures rule exists to prevent."""
    # stderr, NOT stdout: `rmx mcp` speaks JSON-RPC on stdout and save-state
    # calls this with no `out=`, so a report line lands mid-protocol and the
    # client fails to parse the frame around it (bug-045 / ch-bsd #b-2). The
    # failure branch below already used stderr; only the success path leaked.
    # An explicit `out=` still wins -- the CLI passes stdout deliberately.
    out = out if out is not None else sys.stderr
    memdir = Path(memdir)
    idx = memdir / INDEX_NAME
    entries = collect(memdir)
    # NEVER generate from an empty dir. The index is derived FROM the files, so
    # a memdir that reads empty — the wrong path, an unreadable mount, an index
    # written before its files land — would render an empty index and delete
    # every entry. Found by `test_update_index_replaces_not_duplicates`, which
    # exercises exactly that shape (2026-09-16).
    if not entries:
        print(f"{INDEX_NAME}: no memory files found under {memdir}; "
              f"index left untouched", file=out)
        return 0
    before_lines = idx.read_text(errors="replace").splitlines() if idx.exists() else []
    before_refs = {l.split("](", 1)[1].split(")", 1)[0]
                   for l in before_lines if l.startswith("- [") and "](" in l}
    text = render(memdir, max_lines=max_lines, max_chars=max_chars)
    after_lines = text.splitlines()
    after_refs = {l.split("](", 1)[1].split(")", 1)[0]
                  for l in after_lines if l.startswith("- [") and "](" in l}
    # An entry can legitimately disappear: it was collapsed into a pointer, or
    # its file is gone (the forget flow deletes both). Either way the count is
    # PRINTED — a memory index that quietly loses rows is the failure this
    # whole thing exists to fix.
    gone = sorted(r for r in before_refs - after_refs
                  if not (memdir / r).exists())
    idx.write_text(text)
    # Persist EVERY entry's hook, listed or folded, so the next render
    # does not lose the folded ones and fold further (bug-050).
    save_hooks(memdir, entries)
    over = len(text) > max_chars
    print(f"{INDEX_NAME}: {len(before_lines)} -> {len(after_lines)} lines, "
          f"{len(text)} chars (caps {max_lines} lines / {max_chars} chars; "
          f"{len(entries)} memories on disk)", file=out)
    if over:
        # Folding ran out of foldable entries. The index still will not fit,
        # and saying "in sync" here is exactly the silence bug-042 created.
        print(f"{INDEX_NAME}: STILL OVER the {max_chars}-char budget at "
              f"{len(text)} chars — the tail WILL be cut on load; nothing left "
              f"to fold (feedback entries are never folded)", file=out)
    if gone:
        print(f"{INDEX_NAME}: dropped {len(gone)} entr"
              f"{'y' if len(gone) == 1 else 'ies'} whose file is gone: "
              f"{', '.join(gone[:5])}{' …' if len(gone) > 5 else ''}", file=out)
    return len(after_lines)


def check(memdir: Path, *, max_lines: int = MAX_LINES,
          max_chars: int = MAX_INDEX_CHARS) -> bool:
    """True when the index on disk equals what `render` would write."""
    memdir = Path(memdir)
    idx = memdir / INDEX_NAME
    if not idx.exists():
        return False
    return idx.read_text(errors="replace") == render(
        memdir, max_lines=max_lines, max_chars=max_chars)


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
