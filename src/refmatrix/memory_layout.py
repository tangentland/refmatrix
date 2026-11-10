"""The curated memory dir's layout, in ONE place (ADR-0005, task 26.1, 2026-11-09).

WHY THIS MODULE EXISTS. Before it, three readers each kept their own walk of
`~/.claude/projects/<slug>/memory/` and they disagreed:

- `memory_index.collect` globbed `*.md` + `impressions/*.md`, so on a copy of
  viascope's dir (146 memories in `feedback/`, `project/`, `reference/`)
  `memory_index.write` turned a 157-line / 61-link index into 1 line
  (ch-bsd plan-26 r1 #b4);
- `ingest_gmd.collect_gmd_files` `rglob`-ed everything, so a
  `.organise-rollback-1/x.md` aside inside a memdir was ingested as a memory
  (ch-bsd plan-26 r1 #s3);
- `handoff` read save-states at the top level only, and recall-state and the
  index had two different definitions of "newest" (r2 #s3, r3 #m2).

ADR-0005 #one-walk makes `iter_memory_files` the only walk of a memory dir and
`iter_savestates` the only "newest" ordering; ADR-0005 #folders is `FOLDERS`;
ADR-0005 #marker-encoding is `is_organised`. Callers must not keep a private
glob -- that is how the three walks drifted apart (feedback_converge_repeated_shapes).
"""
from __future__ import annotations

import functools
import json
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Iterator

# ADR-0005 #folders, layout version 1: folder -> the `metadata.type` it holds.
# Type folders are singular (one type value each); lifecycle collections are
# plural (a machine-written series). A change here is a new layout version and
# needs an ADR that amends ADR-0005.
FOLDERS: dict = {
    "feedback": "feedback",
    "project": "project",
    "reference": "reference",
    "user": "user",
    "guardrail": "guardrail",
    "impressions": "impression",
    "savestates": "session/recall-state",
}

_FOLDER_OF_TYPE: dict = {mtype: folder for folder, mtype in FOLDERS.items()}

# The layout version this module reads and writes (ADR-0005 #marker).
LAYOUT_VERSION = 1

MARKER_NAME = ".memory-layout"
SAVESTATE_FOLDER = "savestates"
SAVESTATE_PREFIX = "savestate_"

# Files inside a memory dir that are never memories, at any depth. `MEMORY.md`
# is the flat index (not GMD, MEMORY-RULES #index); `README.md` is prose about
# the dir. Dotfiles (the hooks sidecar, the marker) are excluded by name shape.
NOT_A_MEMORY = frozenset({"MEMORY.md", "README.md"})


class MemoryLayoutError(ValueError):
    """A memory dir whose layout cannot be read safely.

    Raised, never defaulted: reading an unreadable `.memory-layout` as "not
    organised" would re-enable the pre-ADR renderer over an organised dir
    (ADR-0005 #marker-encoding, pinned 2026-11-09)."""


def folder_for_type(mtype: str) -> str:
    """The ADR-0005 folder for a `metadata.type`. An unknown type RAISES:
    `organise` (26.5) must report a type it cannot place, never guess a folder
    for it -- a guess is a hand-move with no ADR behind it."""
    try:
        return _FOLDER_OF_TYPE[mtype]
    except KeyError:
        raise MemoryLayoutError(
            f"metadata.type {mtype!r} has no folder in the ADR-0005 layout "
            f"(known: {', '.join(sorted(_FOLDER_OF_TYPE))})") from None


def savestate_dir(memdir) -> Path:
    """Where layout-1 save-states live (`savestates/`, ADR-0005 #folders)."""
    return Path(memdir) / SAVESTATE_FOLDER


def _is_memory_name(name: str) -> bool:
    return name.endswith(".md") and not name.startswith(".") and name not in NOT_A_MEMORY


def iter_memory_files(memdir, *, skipped: "list | None" = None) -> Iterator[Path]:
    """THE walk of a memory dir (ADR-0005 #one-walk): every `.md` file,
    recursively, except `MEMORY.md`, `README.md`, a dotfile, or anything under a
    dot-directory at any depth (a `.organise-rollback-1/` aside is never a
    memory store -- ch-bsd plan-26 r1 #s3).

    Dot-ness is judged on the path RELATIVE to `memdir`, never on its absolute
    parts: every real memdir lives under `~/.claude/`, which is itself a dot-dir.

    Order is deterministic and matches the pre-ADR `memory_index.collect` on a
    dir that is flat except for `impressions/` (top-level files by name, then
    each sub-folder by name), so a flat dir's index renders byte-identically
    (task 26.1 AC-8).

    `skipped`, when given, receives every `.md` path the walk excluded, so a
    caller on a memory path can COUNT and print what it did not take (CLAUDE.md
    #no-silent-failures) instead of the skip being invisible.
    """
    root = Path(memdir)

    def _walk(d: Path) -> Iterator[Path]:
        try:
            with os.scandir(d) as it:
                ents = sorted(it, key=lambda e: e.name)
        except FileNotFoundError:
            return
        dirs = []
        for e in ents:
            if e.is_dir():
                dirs.append(e)
                continue
            if not e.name.endswith(".md") or not e.is_file():
                continue
            if _is_memory_name(e.name):
                yield d / e.name
            elif skipped is not None:
                skipped.append(d / e.name)
        for e in dirs:
            if e.name.startswith("."):
                if skipped is not None:
                    skipped.extend(sorted(p for p in Path(e.path).rglob("*.md")))
                continue
            # A symlinked sub-folder is not followed: the walk stays inside the
            # memdir it was asked about (the same rule as `os.walk` and `rglob`).
            if e.is_symlink():
                continue
            yield from _walk(d / e.name)

    if not root.is_dir():
        return iter(())
    return _walk(root)


# ---- ONE "newest" save-state (ADR-0005 #newest) ---------------------------

_DATE_ONLY = re.compile(r"\d{4}-\d{2}-\d{2}")


class _SaveKey:
    __slots__ = ("path", "day", "when", "mtime")

    def __init__(self, path: Path):
        self.path = path
        self.mtime = path.stat().st_mtime
        self.day: "date | None" = None
        self.when: "datetime | None" = None
        raw = _frontmatter_updated(path)
        if not raw:
            return
        try:
            if _DATE_ONLY.fullmatch(raw):
                # Date-only is never read as midnight (r3 m2): old MCP stdio
                # servers keep writing date-only values until respawned.
                self.day = date.fromisoformat(raw)
            else:
                self.when = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                self.day = self.when.date()
        except ValueError as exc:
            # Said, never mute: an unreadable `updated:` falls back to mtime,
            # which is the documented key when `updated` is absent.
            print(f"memory_layout: {path}: unreadable metadata.updated {raw!r} "
                  f"({exc}); ordering it by mtime", file=sys.stderr)
            self.day = self.when = None


def _frontmatter_updated(path: Path) -> str:
    """`metadata.updated` of a memory file, read with the index's own minimal
    frontmatter reader (one parser for the memory dir, not two)."""
    from refmatrix.memory_index import _frontmatter
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"memory_layout: {path}: unreadable ({exc}); ordering it by mtime",
              file=sys.stderr)
        return ""
    return _frontmatter(text).get("updated", "")


def _cmp_newer(a: _SaveKey, b: _SaveKey) -> int:
    """Negative when `a` is NEWER than `b` (so a plain sort is newest-first).

    ADR-0005 #newest: `updated` by calendar date; on the same date, the
    datetimes only when BOTH carry a time of day; otherwise mtime. `created`
    is never a key (r2 s3: a session created earlier but saved later wins).
    """
    def by(x, y) -> int:
        return -1 if x > y else (1 if x < y else 0)

    if a.day is not None and b.day is not None:
        if a.day != b.day:
            return by(a.day, b.day)
        if a.when is not None and b.when is not None \
                and (a.when.tzinfo is None) == (b.when.tzinfo is None):
            c = by(a.when, b.when)
            if c:
                return c
    c = by(a.mtime, b.mtime)
    if c:
        return c
    return by(a.path.name, b.path.name)


def sort_savestates(paths) -> list:
    """Save-state paths ordered newest-first by the ONE ADR-0005 key."""
    keys = [_SaveKey(Path(p)) for p in paths]
    keys.sort(key=functools.cmp_to_key(_cmp_newer))
    return [k.path for k in keys]


def iter_savestates(memdir) -> list:
    """Every save-state, newest-first: `savestates/*.md` plus legacy top-level
    `savestate_*.md` (ADR-0005 #legacy -- a flat dir stays readable forever).
    Nothing else: a `savestate_*` stem in another folder or in a dot-dir is not
    a save-state."""
    root = Path(memdir)
    found = []
    for p in iter_memory_files(root):
        rel = p.relative_to(root).parts
        if (len(rel) == 2 and rel[0] == SAVESTATE_FOLDER) or \
                (len(rel) == 1 and rel[0].startswith(SAVESTATE_PREFIX)):
            found.append(p)
    return sort_savestates(found)


# ---- the marker (ADR-0005 #marker-encoding) -------------------------------

def is_organised(memdir) -> bool:
    """True when `<memdir>/.memory-layout` is a layout-1 marker.

    No file -> False (an un-organised dir keeps the pre-ADR behaviour). A file
    that does not parse as a JSON object with `"layout": 1` RAISES naming the
    file: a silent "not organised" would run the old renderer over an
    organised dir. Extra keys are ignored so a later layout can add fields.
    """
    marker = Path(memdir) / MARKER_NAME
    if not marker.exists():
        return False
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise MemoryLayoutError(
            f"{marker}: the {MARKER_NAME} marker is unreadable "
            f"({type(exc).__name__}: {exc}); fix or move it aside -- it is never "
            f"read as 'not organised'") from exc
    layout = data.get("layout") if isinstance(data, dict) else None
    # `type(...) is int`: JSON `true` is a bool, and `True == 1` in Python.
    if not isinstance(data, dict) or type(layout) is not int or layout != LAYOUT_VERSION:
        raise MemoryLayoutError(
            f"{marker}: the {MARKER_NAME} marker names layout {layout!r}, not "
            f"{LAYOUT_VERSION} (expected a JSON object with \"layout\": "
            f"{LAYOUT_VERSION}); this rmx does not read that layout")
    return True
