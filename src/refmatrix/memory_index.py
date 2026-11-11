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
    python3 -m refmatrix.memory_index --repair-cut-hooks <memdir> [--apply] [--restore k=text]

The second form is bug-195's one-shot repair of hook values bug-193 cut.
"""
from __future__ import annotations

import json
import os
import re
import stat
import sys
import tempfile
import time
from pathlib import Path

from refmatrix import memory_layout

# Past this width an entry stops being a one-line hook and starts being prose
# that pushes the cap down for everyone else.
MAX_LINE_CHARS = 200

# When an entry's link alone is over MAX_LINE_CHARS, its title is shortened --
# but never below this many leading chars, so the entry stays recognisable
# (bug-192, ch-bsd 26.1 #b-1).
TITLE_MIN_CHARS = 40

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

# Files in the memory dir that are not memories. The one definition lives in
# `memory_layout` (ADR-0005 #one-walk, task 26.1); this name stays for callers.
_NOT_A_MEMORY = set(memory_layout.NOT_A_MEMORY)

# The first line of the carried-prose block an ORGANISED dir's index starts
# with (task 26.1 AC-5). Regeneration used to drop every hand-written line that
# was not an entry: viascope 62, cliquedb 29, viascope2 12, cliquet 8 (ch-bsd
# plan-26 r1 #b4). The marker line is how a later render recognises the block
# and re-carries it ONCE instead of nesting it.
CARRY_HEAD = "<!-- carried from the hand-written index; edit freely -->"

# The generated fold line (`_render_entries`). Not an entry, not prose.
_FOLD_RE = re.compile(r"^- (\d+) older project memories folded\b")
_IMPS_RE = re.compile(r"^- \[ch-bsd impressions \((\d+)\)\]\(impressions/\)")
_SAVES_RE = re.compile(r"^- \[Save-states \((\d+)\), newest ")

# When carried prose alone leaves less than this share of the char budget for
# entries, an organised write refuses rather than fold every entry away
# (task 26.1 AC-5).
MIN_ENTRY_SHARE = 0.25

# An organised write refuses when fewer than this share of the old index's
# content lines would remain (task 26.1 AC-6).
MIN_CONTENT_KEPT = 0.5


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


def _kind_of_type(mtype: str) -> str:
    """The render class of a `metadata.type`: feedback and reference keep
    their own sections; every other type renders (and folds) as a project
    note, as it always has."""
    if mtype.startswith("impression"):
        return "impression"
    if mtype.startswith("session/recall-state"):
        return "savestate"
    if mtype.startswith("feedback"):
        return "feedback"
    if mtype.startswith("reference"):
        return "reference"
    return "project"


class Entry:
    __slots__ = ("path", "rel", "id", "title", "mtype", "hook", "mtime", "created")

    def __init__(self, path: Path, memdir: Path, hooks: dict):
        self.path = path
        self.rel = str(path.relative_to(memdir))
        text = path.read_text(errors="replace")
        fm = _frontmatter(text)
        # The store identity (ADR-0005 #identity): the frontmatter `id`, which
        # MEMORY-RULES requires to equal the stem. Never the folder.
        self.id = fm.get("id") or path.stem
        self.title = fm.get("title") or path.stem
        self.mtype = fm.get("type") or path.stem.split("_")[0]
        self.mtime = path.stat().st_mtime
        self.created = fm.get("created") or ""
        # Rule 1: a curated hook wins over anything derived. Looked up by path
        # first (the pre-ADR key), then by id, so a hook survives a move
        # between folders (task 26.1 AC-4).
        self.hook = hooks.get(self.rel) or hooks.get(self.id) or _first_prose(text)

    @property
    def kind(self) -> str:
        """Folder first, then the stem / frontmatter (task 26.1 AC-7). In a
        layout-1 dir the folder IS the type (ADR-0005 #folders); a flat dir has
        no folder to read, so the pre-ADR rules decide."""
        parts = Path(self.rel).parts
        if len(parts) > 1 and parts[0] in memory_layout.FOLDERS:
            return _kind_of_type(memory_layout.FOLDERS[parts[0]])
        if self.path.stem.startswith("savestate_"):
            return "savestate"
        if self.mtype.startswith("feedback"):
            return "feedback"
        if self.mtype.startswith("reference"):
            return "reference"
        return "project"

    def line(self) -> str:
        """The entry's index line: at most MAX_LINE_CHARS, and NEVER cut inside
        its `](rel)` link (bug-192, ch-bsd 26.1 #b-1, 2026-11-09).

        HEAD cut the whole line at 200 chars. With a long title the cut landed
        before `](rel)`: the memory became unreachable from the index (cliquedb's
        live index holds 8 such lines), and an organised render read the cut
        line as prose, carried it, and rendered the entry again -- the carried
        block grew 8 lines per render until the index froze over budget.

        Shortened in a fixed order: the hook first (byte-identical to HEAD's
        cut whenever HEAD's cut fell inside the hook, so short-title indexes
        do not change), then -- only when the link alone is over the cap -- the
        hook is dropped and the title is shortened, keeping at least its first
        TITLE_MIN_CHARS. A link longer than that leaves the line over the cap
        rather than cutting the link: an over-long line still reaches its file."""
        link = f"]({self.rel})"
        out = f"- [{self.title}{link}"
        placed = _with_hook(out, self.hook)
        if placed is not None:
            return placed
        if len(out) <= MAX_LINE_CHARS:
            return out
        keep = max(TITLE_MIN_CHARS, MAX_LINE_CHARS - len(f"- [{link}") - 1)
        return f"- [{self.title[:keep].rstrip()}…{link}"


def _with_hook(link_part: str, hook: str) -> "str | None":
    """`link_part — hook`, the hook cut to the line's room -- THE hook placement,
    shared by `Entry.line` and the bug-199 repair's line rewrite so the two can
    never cut a hook differently. None when there is no hook or under 2 chars
    of room (the caller decides what the hook-less line looks like)."""
    if not hook:
        return None
    room = MAX_LINE_CHARS - len(link_part) - len(" — ")
    if len(hook) <= room:
        return f"{link_part} — {hook}"
    if room >= 2:
        # Same bytes as HEAD's whole-line cut when it fell in the hook.
        return f"{link_part} — {hook[:room - 1].rstrip()}…"
    return None


def _split_entry_line(line: str) -> "tuple[str, str, str] | None":
    """`(link part, rel, hook)` of one linked entry line, or None for any other
    line (a generated save-state pointer or fold line included) -- THE index-line
    split, read by `_index_hook_records` and by the bug-199 repair's rewrite.

    Split at the LINK, not at the first em dash: titles contain " — "
    themselves ("Capture reasoning deliberately — extended-thinking is
    redacted"), so partitioning on the dash stole half the title into the
    hook and the next render shifted it again — a generator that was not
    idempotent on its own output. Caught on the real index, not in a
    fixture, because the fixture titles had no dashes (2026-09-16)."""
    if not line.startswith("- [") or _SAVES_RE.match(line) or _FOLD_RE.match(line):
        return None
    head, sep, rest = line.partition("](")
    if not sep:
        return None
    rel, sep, tail = rest.partition(")")
    if not sep:
        return None
    hook = tail.lstrip()
    if hook.startswith("—"):
        hook = hook[1:]
    return f"{head}]({rel})", rel, hook.strip()


def _is_entry_line(line: str) -> bool:
    return line.startswith("- [") and "](" in line


def _link_refs(lines: list) -> set:
    """The link targets of an index's entry lines -- WHOLE links only. A line
    HEAD cut inside its link (`](feedback/feedback_cut_ins…`, no closing `)`)
    names no file, so it never counts as a memory "whose file is gone": the
    memory exists and the next render links it again (task 26.1 spec
    #fu-dropped; ch-bsd 26.1 r2, bug-193, 2026-11-09)."""
    refs = set()
    for ln in lines:
        if not _is_entry_line(ln):
            continue
        rel, sep, _ = ln.split("](", 1)[1].partition(")")
        if sep and rel and not rel.endswith("…"):
            refs.add(rel)
    return refs


def _parse_index_hooks(idx: Path) -> dict:
    """`{relative path: hook}` exactly as written in an existing index -- the
    `{rel: hook}` projection of `_index_hook_records`, never a second parser
    (ch-bsd 26.1 r3 #m-2, 2026-11-10: `_dead_hooks` and `load_hooks` read the
    index through two copies of one partition + dash-strip, free to drift)."""
    return {rel: hook for rel, (hook, _room) in _index_hook_records(idx).items()}


def _is_path_key(key: str) -> bool:
    """A sidecar / index key that names a FILE (the pre-ADR shape), as opposed
    to a memory id (task 26.1 AC-4) or a generated pointer (`impressions/`)."""
    return key.endswith(".md")


def _id_of_link(memdir: Path, rel: str) -> str:
    """The memory id a path-shaped hook key points at: the linked file's
    frontmatter `id` when it exists, else its stem -- MEMORY-RULES makes the id
    equal the stem, which is what lets a hook whose file has MOVED find the
    memory again (ADR-0005 #hooks)."""
    p = memdir / rel
    if p.is_file():
        try:
            fid = _frontmatter(p.read_text(errors="replace")).get("id")
        except OSError as exc:
            print(f"{INDEX_NAME}: {rel}: unreadable ({exc}); keying its hook by "
                  f"the file stem", file=sys.stderr)
            fid = None
        if fid:
            return fid
    return Path(rel).stem


def _with_id_aliases(memdir: Path, hooks: dict) -> dict:
    """Every path-keyed hook ALSO under the id its link points at. Path keys
    are kept as they are: a dead link's hook stays findable under its path."""
    out = dict(hooks)
    for k, v in hooks.items():
        if _is_path_key(k):
            out.setdefault(_id_of_link(memdir, k), v)
    return out


HOOKS_SIDECAR = ".memory_hooks.json"


class SidecarError(RuntimeError):
    """The hook sidecar exists but cannot be read or is not a JSON object."""


def _load_sidecar(memdir: Path) -> "tuple[bytes, dict] | None":
    """THE sidecar reader: `(raw bytes, parsed object)`, or None when there is
    no sidecar. RAISES `SidecarError` on an unreadable file, unparseable JSON,
    or a non-object. The render path (`_read_sidecar`) degrades on that with a
    named warning; the bug-195 repair refuses on it -- one parse, two policies
    (bug-195 / ch-bsd 26.1 r3 s-2, 2026-11-10)."""
    side = memdir / HOOKS_SIDECAR
    if not side.exists():
        return None
    try:
        raw = side.read_bytes()
        data = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise SidecarError(f"{side}: hook sidecar unreadable "
                           f"({type(exc).__name__}: {exc})") from exc
    if not isinstance(data, dict):
        raise SidecarError(f"{side}: hook sidecar is a JSON {type(data).__name__}, "
                           f"not an object")
    return raw, data


def _dump_sidecar(data: dict) -> str:
    """THE sidecar serialisation -- the bytes `save_hooks` has always written."""
    return json.dumps(data, indent=0, sort_keys=True, ensure_ascii=False)


def _sidecar_mode(side: Path) -> int:
    """The mode the sidecar write must leave: the existing file's permission
    bits, else what `write_text` would have created -- `0o666 & ~umask`. The
    umask has no read-only accessor before Python 3.15, so it is read by
    setting it and restoring it at once (ch-bsd bug-195 r1 m-1, 2026-11-10)."""
    try:
        return stat.S_IMODE(side.stat().st_mode)
    except FileNotFoundError:
        pass
    umask = os.umask(0o022)
    os.umask(umask)
    return 0o666 & ~umask


def _store_sidecar(memdir: Path, data: dict) -> None:
    """Write the sidecar atomically: a temp file in the memdir, then a rename,
    so a crash mid-write never leaves a half sidecar (bug-195 R3, 2026-11-10).
    RAISES on failure, after removing the temp file; callers decide whether
    that is a warning (`save_hooks`) or a refusal (the repair).

    The file keeps its mode (`_sidecar_mode`): `mkstemp` creates 0600 and the
    rename keeps it, so ccb9398 turned every save-state's sidecar owner-only
    where `write_text` had left 0644 (ch-bsd bug-195 r1 m-1, 2026-11-10)."""
    _atomic_write_text(memdir, HOOKS_SIDECAR, _dump_sidecar(data))


def _atomic_write_text(memdir: Path, name: str, text: str) -> None:
    """THE atomic memdir write: temp file beside the target, fsync, rename,
    the target's mode kept (`_sidecar_mode` reads any file's bits). Shared by
    the sidecar and the bug-199 repair's MEMORY.md rewrite (2026-11-10), so
    the index rewrite is no less crash-safe than the sidecar one. RAISES on
    failure, after removing the temp file."""
    target = memdir / name
    mode = _sidecar_mode(target)
    fd, tmp = tempfile.mkstemp(prefix=f"{name}.", suffix=".tmp", dir=memdir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
            fh.flush()
            os.fchmod(fh.fileno(), mode)
            os.fsync(fh.fileno())
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def _read_sidecar(memdir: Path) -> dict:
    hooks: dict = {}
    try:
        loaded = _load_sidecar(memdir)
    except SidecarError as exc:
        print(f"{INDEX_NAME}: {exc}; folded entries may lose their curated hooks",
              file=sys.stderr)
        loaded = None
    if loaded is not None:
        hooks.update({str(k): str(v) for k, v in loaded[1].items()})
    return hooks


def load_hooks(memdir: Path) -> dict:
    """Curated hooks: the index PLUS the sidecar of hooks for folded entries.

    Without the sidecar the generator is not idempotent on its own output
    (bug-050). The index alone only shows entries it still lists, so a
    folded entry loses its curated hook, falls back to derived prose — usually
    LONGER — which grows the render and folds two more. Rendering the live
    index from itself moved the fold 56 -> 58 with no memory added, and
    `--check` read out of sync immediately after a successful write. Every
    save-state would have degraded the index a little further.

    DUAL reader, every dir, marker or not (task 26.1 AC-4, ADR-0005 #marker):
    a sidecar keyed by path (pre-ADR, and what an un-organised write still
    writes) and one keyed by memory id (an organised write) are both read, and
    every path key is also aliased to its id. A reader writes no file.

    Precedence, every dir (task 26.1 spec #fu-hooks; ch-bsd 26.1 r2, bug-193,
    2026-11-09 -- narrows the remedy GREEN's "an empty index hook never erases a
    curated hook"): the index hook replaces the sidecar value, because the
    index is what a human last edited -- EXCEPT where the index could not carry
    the hook (`_index_hook_wins`). A hook deleted from a line that had room
    for it is CLEARED, as at HEAD 61b3bde, so a marker-off dir keeps HEAD's
    hook-clear byte for byte (ADR-0005 #marker).
    """
    memdir = Path(memdir)
    side = _with_id_aliases(memdir, _read_sidecar(memdir))
    hooks = dict(side)
    for rel, (hook, room) in _index_hook_records(memdir / INDEX_NAME).items():
        if not _is_path_key(rel):
            hooks[rel] = hook                  # a generated pointer (`impressions/`)
            continue
        mid, derived = _link_identity(memdir, rel)
        # ONE decision per memory, written under both keys: `Entry` looks the
        # path up first, so a path key the sidecar never had (an organised,
        # id-keyed sidecar) must not let the cut win by the back door.
        # The existing value is the sidecar's, else the memory's DERIVED hook
        # (ch-bsd 26.1 r3 #m-1, 2026-11-10): with `cur` empty a cut of derived
        # prose won and `save_hooks` froze it into the sidecar as if curated --
        # how live refmatrix's sidecar came to hold 37 derived cuts (bug-195).
        cur = side.get(rel) or side.get(mid) or derived
        val = hook if _index_hook_wins(hook, cur, room) else cur
        hooks[rel] = val
        hooks[mid] = val
    return hooks


def _link_identity(memdir: Path, rel: str) -> tuple:
    """`(memory id, derived hook)` of the file an index link names: the id as
    `_id_of_link` gives it, and `_first_prose` of the file ("" when the link's
    file is gone, so a dead link has no derived value to keep)."""
    p = memdir / rel
    if p.is_file():
        try:
            text = p.read_text(errors="replace")
        except OSError as exc:
            print(f"{INDEX_NAME}: {rel}: unreadable ({exc}); keying its hook by "
                  f"the file stem, no derived hook", file=sys.stderr)
            return Path(rel).stem, ""
        return _frontmatter(text).get("id") or Path(rel).stem, _first_prose(text)
    return Path(rel).stem, ""


def _index_hook_records(idx: Path) -> dict:
    """`{rel: (hook, room)}` for every linked entry line of an index -- THE
    index-line parser (`_parse_index_hooks` is its projection; ch-bsd 26.1 r3
    #m-2, 2026-11-10). `room` is the line's NUMERIC hook room, `MAX_LINE_CHARS
    - len(link part) - len(" — ")`, the same arithmetic `Entry.line` cuts with
    (ch-bsd 26.1 r3 #s-1: a yes/no "had room" could not tell a value the line
    carried whole from one it cut).

    Generated pointer lines are no hook source (ch-bsd 26.1 r3 #m-3): the
    save-state pointer (`_SAVES_RE`) links `savestate_X.md`, so its generated
    "session handoffs; ..." text won over savestate_X's curated hook (cliquedb
    lost one that way, pre-existing at 61b3bde); the fold line carries no link
    and is skipped by name all the same. The `impressions/` pointer is kept --
    `load_hooks` stores it under its own non-path key."""
    out: dict = {}
    if not idx.exists():
        return out
    for line in idx.read_text(errors="replace").splitlines():
        split = _split_entry_line(line)
        if split is None:
            continue
        link_part, rel, hook = split
        out[rel] = (hook, MAX_LINE_CHARS - len(link_part) - len(" — "))
    return out


def _index_hook_wins(hook: str, cur: str, room: int) -> bool:
    """Whether an index hook replaces the existing value `cur` -- the sidecar
    value, else the memory's derived hook (task 26.1 spec #fu-hooks; ch-bsd 26.1
    r2, bug-193, 2026-11-09; narrowed by ch-bsd 26.1 r3 #s-1, 2026-11-10). It
    does, except when the index line could not carry `cur`:

    (a) the hook is empty and the link alone left under 2 chars of room --
        `Entry.line` dropped the hook, so the empty read is the renderer's;
    (b) the hook is `prefix…`, the prefix a prefix of `cur`, AND `len(cur) >
        room` -- the renderer's cut (bug-193: taking it wrote the cut over the
        full text, 246 chars became 171 in two renders);
    (c) the hook is a bare `…` AND `len(cur) > room` (HEAD cuts that ended
        `.md)…`).

    On a line that HAD room for `cur`, a `prefix…` or `…` is the user's own
    shortening and replaces, as at HEAD 61b3bde -- r3's probe: c9a035e reverted
    "the curated hook…" to the full sidecar value and said nothing. A hand edit
    that is not a prefix of `cur` always replaces."""
    if not cur or hook == cur:
        return True
    cut = len(cur) > room
    if hook == "…":
        return not cut
    if hook.endswith("…") and cur.startswith(hook[:-1].rstrip()):
        return not cut
    if not hook and room < 2:
        return False
    return True


def save_hooks(memdir: Path, entries: list, *, dead: "dict | None" = None) -> None:
    """Persist every entry's hook, listed or folded, so curation survives a
    fold. Written on the same call that rewrites the index.

    Un-organised dir (no `.memory-layout`): HEAD's path-keyed sidecar, byte for
    byte -- its write is what keeps bug-050's fold idempotent there (r3 s1).
    Organised dir: keyed by memory id, so a move never loses a hook, plus every
    `dead` hook kept under the key it was found under (task 26.1 AC-4)."""
    memdir = Path(memdir)
    if memory_layout.is_organised(memdir):
        data = dict(dead or {})
        data.update({e.id: e.hook for e in entries if e.hook})
    else:
        data = {e.rel: e.hook for e in entries if e.hook}
    try:
        _store_sidecar(memdir, data)
    except Exception as exc:  # noqa: BLE001 — named, never mute
        print(f"{INDEX_NAME}: could not write hook sidecar "
              f"({type(exc).__name__}: {exc}); folded entries will lose their "
              f"curated hooks on the next render", file=sys.stderr)


def _dead_hooks(memdir: Path, entries: list) -> dict:
    """Curated hooks (sidecar or index) that point at NO current memory.

    A path key is alive when it names a current file or the id its link
    points at is a current memory's id (a moved file); an id key is alive when
    a current memory carries that id. Anything else is dead -- and KEPT under
    the key it was found under, never silently discarded (task 26.1 AC-4: a
    file that is gone right now may come back, and the hook is hand-written)."""
    rels = {e.rel for e in entries}
    ids = {e.id for e in entries}
    raw = _read_sidecar(memdir)
    raw.update(_parse_index_hooks(memdir / INDEX_NAME))
    dead: dict = {}
    for k, v in raw.items():
        if not v or k.endswith("/"):          # a generated pointer's hook
            continue
        if _is_path_key(k):
            if k in rels or _id_of_link(memdir, k) in ids:
                continue
        elif k in ids:
            continue
        dead[k] = v
    return dead


def collect(memdir: Path) -> list:
    """Every memory in the dir, through THE walk (`memory_layout.iter_memory_files`).

    Ungated, every dir (task 26.1 AC-3, ADR-0005 #marker r4 s1): the old
    `*.md` + `impressions/*.md` glob saw 4 of viascope's ~146 memories, and
    gating the walk would have kept that wipe. On a dir flat except for
    `impressions/` it yields what the glob did, in the same order."""
    memdir = Path(memdir)
    hooks = load_hooks(memdir)
    return [Entry(p, memdir, hooks) for p in memory_layout.iter_memory_files(memdir)]


def _prose_lines(lines: list) -> list:
    """Hand-written prose of an index (ORGANISED path only): every non-blank
    line that is not entry-shaped, a fold line, or the carried block's own
    header (task 26.1 AC-5). Verbatim, in order.

    Entry-shaped means it starts `- [`, link or no link (AC-5 amended
    2026-11-09, ch-bsd 26.1 #b-1, bug-192): HEAD's 200-char cut left link-less
    `- [Long title…` lines in live indexes (cliquedb: 8), and reading those as
    prose carried them and re-rendered the same entry every pass. They are
    dropped here and the memory is rendered again WITH its link."""
    return [ln for ln in lines
            if ln.strip() and ln.strip() != CARRY_HEAD
            and not ln.startswith("- [") and not _FOLD_RE.match(ln)]


def _carried_block(prose: list) -> str:
    """The block an organised index starts with. Empty when there is no prose,
    so a prose-free organised index carries no empty header."""
    if not prose:
        return ""
    return "\n".join([CARRY_HEAD, *prose]) + "\n\n"


def _index_lines(memdir: Path) -> list:
    idx = memdir / INDEX_NAME
    return idx.read_text(errors="replace").splitlines() if idx.exists() else []


def _render_entries(memdir: Path, entries: list, *, max_lines: int, max_chars: int,
                    organised: bool) -> str:
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
    saves = by.get("savestate", [])
    if saves:
        if organised:
            # ADR-0005 #newest: the ONE ordering (`updated`, then mtime;
            # never `created`), shared with recall-state (task 26.1 AC-1).
            first = memory_layout.sort_savestates([e.path for e in saves])[0]
            newest = next(e for e in saves if e.path == first)
        else:
            # Un-organised: HEAD's ordering, kept byte-for-byte (ADR-0005
            # #marker). By DATE, not by stem: save-state ids are session
            # hashes (`savestate_fd45323ccbb8`), so sorting the names picked
            # an arbitrary one and called it newest. `created` comes from the
            # frontmatter, mtime is the tiebreak.
            newest = sorted(saves, key=lambda e: (e.created, e.mtime))[-1]
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


def _render_organised(memdir: Path, entries: list, prose: list, *, max_lines: int,
                      max_chars: int) -> str:
    """The layout-1 renderer (ADR-0005 #hooks, task 26.1 AC-5): the carried
    prose block first, then the entries under what the block leaves of BOTH
    budgets -- the prose's characters count against `MAX_INDEX_CHARS`."""
    block = _carried_block(prose)
    return block + _render_entries(
        memdir, entries, organised=True,
        max_lines=max(1, max_lines - block.count("\n")),
        max_chars=max_chars - len(block))


def render(memdir: Path, *, max_lines: int = MAX_LINES,
           max_chars: int = MAX_INDEX_CHARS) -> str:
    """The index `write` would produce. An organised dir (`.memory-layout`)
    gets the layout-1 renderer; any other dir gets the pre-ADR render exactly
    (ADR-0005 #marker: a deploy changes no un-organised dir's files)."""
    memdir = Path(memdir)
    entries = collect(memdir)
    if memory_layout.is_organised(memdir):
        return _render_organised(memdir, entries, _prose_lines(_index_lines(memdir)),
                                 max_lines=max_lines, max_chars=max_chars)
    return _render_entries(memdir, entries, organised=False,
                           max_lines=max_lines, max_chars=max_chars)


def _named_count(lines: list, rels: set) -> int:
    """How many memories a rendered index NAMES: inline entry links, plus the
    count each generated pointer and the fold line stand for (task 26.1 AC-6).
    A fold is a summary, not a loss -- counting links only would refuse every
    legitimate fold."""
    n = 0
    for ln in lines:
        for rx in (_FOLD_RE, _IMPS_RE, _SAVES_RE):
            m = rx.match(ln)
            if m:
                n += int(m.group(1))
                break
        else:
            if _is_entry_line(ln) and ln.split("](", 1)[1].split(")", 1)[0] in rels:
                n += 1
    return n


def _refuse(out, reason: str) -> int:
    print(f"{INDEX_NAME}: {reason}; index left untouched", file=out)
    return 0


def _write_organised(memdir: Path, entries: list, *, max_lines: int, max_chars: int,
                     out) -> int:
    """An organised dir's write: carried prose, the two refusals, the id-keyed
    sidecar (task 26.1 AC-4..AC-6, ADR-0005 #hooks). Every refusal leaves the
    index AND the sidecar untouched, says why on `out`, and returns 0."""
    idx = memdir / INDEX_NAME
    before_lines = _index_lines(memdir)
    prose = _prose_lines(before_lines)
    block = _carried_block(prose)
    # AC-5: prose counts against the char budget. When it alone leaves less
    # than a quarter for entries, refuse -- folding every entry away to make
    # room for prose would hide the memories the index exists to reach.
    if prose and (max_chars - len(block)) < MIN_ENTRY_SHARE * max_chars:
        return _refuse(out, (
            f"the carried hand-written prose ({len(prose)} prose lines, {len(block)} "
            f"chars) leaves less than {int(MIN_ENTRY_SHARE * 100)}% of the "
            f"{max_chars}-char budget for entries; move that prose into a memory"))
    text = _render_organised(memdir, entries, prose,
                             max_lines=max_lines, max_chars=max_chars)
    # AC-6 (#m-1): `_render_entries` has already folded every foldable entry
    # it could. Still over the budget means the tail WILL be cut on load
    # (ch-bsd 26.1 #m-1, 2026-11-09: cliquedb's marker-on render 1 was 24,378
    # chars, pushed over by its carried prose, and was written anyway). There is no
    # "any prose lost" check: the render carries every prose line by
    # construction (#s-1 removed it as a guard that could never fire).
    #
    # Amended 2026-11-09 at the 26.1 remedy GREEN: refuse only when the CARRIED
    # PROSE is what blocks the fit -- the same entries rendered without the
    # block, against the whole budget, would fit -- because then the user can
    # move prose into a memory. When even that cannot fit (feedback is never
    # folded), write it and let `_report` say STILL OVER, as a marker-off dir
    # does: an index that stops updating is worse than an over-budget one.
    if len(text) > max_chars and prose:
        bare = _render_entries(memdir, entries, organised=True,
                               max_lines=max_lines, max_chars=max_chars)
        if len(bare) <= max_chars:
            return _refuse(out, (
                f"even with every foldable entry folded the render is {len(text)} "
                f"chars, over the {max_chars}-char budget, and without the carried "
                f"hand-written prose ({len(prose)} prose lines, {len(block)} chars) "
                f"it would fit ({len(bare)} chars) -- move that prose into a memory"))
    after_lines = text.splitlines()
    # AC-6: the shrink guard counts CONTENT -- entries plus prose -- not links.
    before_content = sum(1 for ln in before_lines if _is_entry_line(ln)) + len(prose)
    after_content = _named_count(after_lines, {e.rel for e in entries}) + len(prose)
    if before_content and after_content < MIN_CONTENT_KEPT * before_content:
        return _refuse(out, (
            f"the render would keep {after_content} of {before_content} content lines "
            f"(entries + prose; under {int(MIN_CONTENT_KEPT * 100)}%) -- a partial "
            f"view of {memdir} ({len(entries)} memories visible)"))
    before_refs = _link_refs(before_lines)
    after_refs = _link_refs(after_lines)
    gone = sorted(r for r in before_refs - after_refs if not (memdir / r).exists())
    # Entry-shaped lines with no link are never prose (AC-5) and never carried:
    # each one is COUNTED and NAMED verbatim, so a hand-written `- [ ] todo` is
    # not lost in silence (CLAUDE.md #no-silent-failures; task 26.1 spec
    # #fu-skips; ch-bsd 26.1 r2, 2026-11-09).
    unlinked = [ln for ln in before_lines if ln.startswith("- [") and not _is_entry_line(ln)]
    dead = _dead_hooks(memdir, entries)
    idx.write_text(text)
    save_hooks(memdir, entries, dead=dead)
    _report(out, before_lines, after_lines, text, entries, max_lines, max_chars, gone)
    if prose:
        print(f"{INDEX_NAME}: carried {len(prose)} hand-written prose line(s)", file=out)
    if unlinked:
        shown = unlinked[:20]
        print(f"{INDEX_NAME}: dropped {len(unlinked)} entry-shaped line(s) with no link "
              f"(a line starting '- [' is never carried as prose; a memory among them is "
              f"rendered again with its link): " + " | ".join(shown)
              + (f" … and {len(unlinked) - len(shown)} more" if len(unlinked) > 20 else ""),
              file=out)
    if dead:
        names = sorted(dead)
        print(f"{INDEX_NAME}: kept {len(dead)} curated hook(s) whose link is dead "
              f"under their own key in {HOOKS_SIDECAR}: {', '.join(names[:5])}"
              f"{' …' if len(names) > 5 else ''}", file=out)
    return len(after_lines)


def _report(out, before_lines, after_lines, text, entries, max_lines, max_chars,
            gone) -> None:
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


def write(memdir: Path, *, max_lines: int = MAX_LINES,
          max_chars: int = MAX_INDEX_CHARS, out=None) -> int:
    """Rewrite the index. Returns the number of lines written, and SAYS what it
    did — a silent rewrite of the memory index is the shape this project's
    no-silent-failures rule exists to prevent.

    An organised dir takes `_write_organised` (task 26.1); every other dir
    takes the pre-ADR write below unchanged, including its prose-dropping
    compaction and its path-keyed sidecar (ADR-0005 #marker, r3 s1/m4: a guard
    there would refuse every index write in the fleet's un-organised dirs)."""
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
    if memory_layout.is_organised(memdir):
        return _write_organised(memdir, entries, max_lines=max_lines,
                                max_chars=max_chars, out=out)
    before_lines = idx.read_text(errors="replace").splitlines() if idx.exists() else []
    before_refs = _link_refs(before_lines)
    text = render(memdir, max_lines=max_lines, max_chars=max_chars)
    after_lines = text.splitlines()
    after_refs = _link_refs(after_lines)
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
    _report(out, before_lines, after_lines, text, entries, max_lines, max_chars, gone)
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


# ---- bug-195: the one-shot repair of hook values bug-193 cut ------------------

# The classes a `…`-ended sidecar value falls into, in report order.
REPAIR_CLASSES = ("derived", "bare", "curated-lost", "gone")

# The classes whose key `--apply` drops so the memory's derived hook returns.
_REPAIR_DROPS = frozenset({"derived", "bare"})


class RepairError(RuntimeError):
    """A repair refusal: printed by name, exit non-zero, nothing written."""


def _repair_backup_dir(memdir: Path) -> Path:
    """`<user_home>/backups/memory-hooks/<memdir-slug>-<timestamp>/` (bug-195 R3).
    The slug is the project dir's name for a `.../<project>/memory` dir -- the
    part that tells two projects' backups apart -- else the memdir's own name."""
    from refmatrix import taxonomy

    m = memdir.resolve()
    name = m.parent.name if m.name == "memory" and m.parent.name else m.name
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-") or "memdir"
    stamp = time.strftime("%Y%m%dT%H%M%S") + f"-{time.time_ns() % 1_000_000_000:09d}"
    return taxonomy.user_home() / "backups" / "memory-hooks" / f"{slug}-{stamp}"


def _memory_text(memdir: Path, key: str, path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise RepairError(f"{HOOKS_SIDECAR}: {key}: memory file {path} unreadable "
                          f"({type(exc).__name__}: {exc}); nothing repaired") from exc


def _ids_to_files(memdir: Path) -> dict:
    """`{memory id: path}` over THE walk (`memory_layout.iter_memory_files`), the
    same identity `Entry` uses (frontmatter `id`, else the stem). Every file is
    read: an unreadable one could be the memory an id key names, so it refuses
    rather than calling that key gone."""
    out: dict = {}
    for f in memory_layout.iter_memory_files(memdir):
        rel = str(f.relative_to(memdir))
        fid = _frontmatter(_memory_text(memdir, rel, f)).get("id") or f.stem
        out.setdefault(fid, f)
    return out


def classify_cut_hooks(memdir: Path, data: dict) -> list:
    """`[(key, class)]` for every sidecar value ending in `…`, in key order
    (bug-195 / ch-bsd 26.1 r3 s-2, 2026-11-10). Values not ending in `…` are
    never classified -- they are not cuts.

    - `bare`: the value is exactly `…` (HEAD cuts that ended `.md)…`).
    - `derived`: the memory's file exists and the cut's prefix starts its
      `_first_prose` -- a frozen cut of the derived hook (37 on live refmatrix).
    - `curated-lost`: the file exists and the prefix is not its prose -- the
      full curated text is gone; kept, and named for the user to rewrite.
    - `gone`: the key names no current memory -- never touched.

    Key resolution: a path key (`*.md`, including `impressions/x.md`) against
    the memdir; any other key as a memory id through THE walk (`load_hooks`
    reads id keys in every dir, so they are resolved in every dir). RAISES
    `RepairError` naming the key when a memory file cannot be read."""
    out: list = []
    ids: "dict | None" = None
    for key in sorted(data):
        val = data[key]
        if not isinstance(val, str) or not val.endswith("…"):
            continue
        if _is_path_key(key):
            f = memdir / key
            path = f if f.is_file() else None
        else:
            if ids is None:
                ids = _ids_to_files(memdir)
            path = ids.get(key)
        if val == "…":
            # A bare `…` carries nothing to keep, file or no file -- but a key
            # whose memory is gone is still never touched.
            out.append((key, "bare" if path is not None else "gone"))
            continue
        if path is None:
            out.append((key, "gone"))
            continue
        prefix = val[:-1].rstrip()
        prose = _first_prose(_memory_text(memdir, key, path))
        out.append((key, "derived" if prefix and prose.startswith(prefix)
                    else "curated-lost"))
    return out


def _parse_restores(restores: list) -> dict:
    """`k=text` pairs, split on the FIRST `=` (the text may hold `=`)."""
    out: dict = {}
    for r in restores:
        key, sep, text = r.partition("=")
        if not sep or not key:
            raise RepairError(f"--restore {r!r}: expected <key>=<text>")
        out[key] = text
    return out


def _repaired_index(memdir: Path, new: dict, changed: set) -> "tuple[bytes, str, list] | None":
    """`(old index bytes, new index text, [rel, ...])` with the HOOK part of
    every index line whose memory a repair changed rewritten to the repaired
    value, or None when there is no index (bug-199, 2026-11-10).

    Why: the repair wrote only the sidecar, and the stale `prefix…` left on a
    line WITH room is, to `_index_hook_wins`, the user's own shortening -- so
    the next `write` put 26 of 29 live restores back to their cuts. Only the
    hook part of the affected lines changes (the link part, every other line,
    and the line endings stay byte-identical): a whole-index re-render would
    also re-render hand edits elsewhere away, and `write`'s own guards would
    refuse it on an index that carries prose.

    A line is affected when its link, or the memory id the link points at, is
    a `changed` key. Its new hook is what `Entry` reads from the NEW sidecar
    alone -- path key, then id, then the memory's derived hook -- placed by
    `_with_hook`, the renderer's own cut. RAISES `RepairError` on an index
    that cannot be read as UTF-8: rewriting it with replacement chars would
    corrupt the user's file."""
    idx = memdir / INDEX_NAME
    if not idx.exists():
        return None
    try:
        raw = idx.read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise RepairError(f"{idx}: unreadable ({type(exc).__name__}: {exc}); "
                          f"nothing repaired") from exc
    side = _with_id_aliases(memdir, {str(k): str(v) for k, v in new.items()})
    lines = text.splitlines(keepends=True)
    rewritten: list = []
    for i, full in enumerate(lines):
        body = full.rstrip("\r\n")
        split = _split_entry_line(body)
        if split is None:
            continue
        link_part, rel, _old = split
        if not _is_path_key(rel):
            continue                           # a generated pointer (`impressions/`)
        mid, derived = _link_identity(memdir, rel)
        if rel not in changed and mid not in changed:
            continue
        hook = side.get(rel) or side.get(mid) or derived
        line = _with_hook(link_part, hook) or link_part
        if line != body:
            lines[i] = line + full[len(body):]
            rewritten.append(rel)
    return raw, "".join(lines), rewritten


def repair_cut_hooks(memdir: Path, *, apply: bool = False,
                     restores: "list | None" = None, out=None) -> int:
    """Classify, and with `apply` repair, the hook values bug-193 froze into the
    sidecar (bug-195 / ch-bsd 26.1 r3 s-2, 2026-11-10).

    bug-193 saved `Entry.line`'s `prefix…` cut back into `.memory_hooks.json`
    as if it were curated; the fixed precedence (25af9ca) stops new damage but
    never heals old values -- live refmatrix held 66 `…`-ended values. Dropping
    a `derived` or `bare` key lets the full derived hook return on the next
    render; `curated-lost` and `gone` keys are kept byte-identical. `restores`
    (`k=text`, R5) set explicit values the operator recovered from git -- the
    tool never guesses curated text.

    Dry-run by default: prints, writes nothing. `apply` backs the sidecar up
    under `taxonomy.user_home()` FIRST and refuses if that fails, then writes
    atomically (`_store_sidecar`). A second apply finds nothing and says so.

    The index is repaired with it (bug-199, 2026-11-10): every MEMORY.md line
    of a dropped or restored key gets the repaired hook (`_repaired_index`),
    backed up into the SAME backup dir before anything is written, and written
    atomically after the sidecar -- otherwise the stale cut on the line wins
    the next `write` and undoes the repair. Each rewritten line is printed.
    Every failure is printed by name and returns non-zero; no traceback, no
    partial write (R4). Returns the exit code."""
    out = out if out is not None else sys.stdout
    memdir = Path(memdir)
    try:
        if not memdir.is_dir():
            raise RepairError(f"{memdir}: not a directory")
        wanted = _parse_restores(restores or [])
        try:
            loaded = _load_sidecar(memdir)
        except SidecarError as exc:
            raise RepairError(f"{exc}; nothing repaired") from exc
        if loaded is None:
            if wanted:
                raise RepairError(f"{memdir / HOOKS_SIDECAR}: no hook sidecar; "
                                  f"--restore has nothing to restore into")
            print(f"{HOOKS_SIDECAR}: no hook sidecar in {memdir}; nothing to repair",
                  file=out)
            return 0
        raw, data = loaded
        missing = sorted(k for k in wanted if k not in data)
        if missing:
            raise RepairError(f"--restore: no such key in {memdir / HOOKS_SIDECAR}: "
                              f"{', '.join(missing)}")
        found = classify_cut_hooks(memdir, data)
        new = {k: v for k, v in data.items()
               if k not in {key for key, cls in found if cls in _REPAIR_DROPS}}
        new.update(wanted)
        changed = {k for k in set(data) | set(new) if data.get(k) != new.get(k)}
        index = _repaired_index(memdir, new, changed) if changed else None
    except RepairError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1

    for key, cls in found:
        print(f"  {cls:<12} {key}", file=out)
    counts = {c: sum(1 for _, k in found if k == c) for c in REPAIR_CLASSES}
    print(f"{len(found)} cut value(s) in {memdir / HOOKS_SIDECAR}: "
          + "  ".join(f"{c}: {counts[c]}" for c in REPAIR_CLASSES), file=out)

    for key in wanted:
        print(f"  restore      {key}", file=out)
    if new == data:
        print("nothing to repair", file=out)
        return 0
    dropped = len(data) - len(set(new) & set(data))
    rewritten = index[2] if index is not None else []
    for rel in rewritten:
        print(f"  {'would rewrite' if not apply else 'rewrite'} {INDEX_NAME} line {rel}",
              file=out)
    if not apply:
        print(f"dry-run: would drop {dropped} key(s), restore {len(wanted)} and "
              f"rewrite {len(rewritten)} {INDEX_NAME} line(s); rerun with --apply "
              f"to write", file=out)
        return 0

    bakdir = _repair_backup_dir(memdir)
    backups = [(bakdir / HOOKS_SIDECAR, raw)]
    if rewritten:
        backups.append((bakdir / INDEX_NAME, index[0]))
    try:
        bakdir.mkdir(parents=True, exist_ok=False)
        for bak, content in backups:
            bak.write_bytes(content)
            if bak.read_bytes() != content:
                raise OSError(f"{bak} does not read back as the original")
    except OSError as exc:
        print(f"refused: backup to {bakdir} failed ({type(exc).__name__}: {exc}); "
              f"{memdir / HOOKS_SIDECAR} and {memdir / INDEX_NAME} left untouched",
              file=sys.stderr)
        return 1
    for bak, _content in backups:
        print(f"backup: {bak}", file=out)
    try:
        _store_sidecar(memdir, new)
    except OSError as exc:
        print(f"refused: writing {memdir / HOOKS_SIDECAR} failed "
              f"({type(exc).__name__}: {exc}); the old sidecar and index are "
              f"intact and backed up in {bakdir}", file=sys.stderr)
        return 1
    if rewritten:
        try:
            _atomic_write_text(memdir, INDEX_NAME, index[1])
        except OSError as exc:
            # The sidecar is already repaired; the stale index lines would win
            # the next `write` back (bug-199), so this is a failure, by name.
            print(f"refused: {memdir / HOOKS_SIDECAR} was repaired but writing "
                  f"{memdir / INDEX_NAME} failed ({type(exc).__name__}: {exc}); the "
                  f"old index is intact -- copy {bakdir / HOOKS_SIDECAR} back "
                  f"before the next write, which would let the stale lines win", file=sys.stderr)
            return 1
    print(f"applied: dropped {dropped} key(s), restored {len(wanted)}, rewrote "
          f"{len(rewritten)} {INDEX_NAME} line(s); {len(new)} hook(s) remain", file=out)
    return 0


_USAGE = ("usage: python3 -m refmatrix.memory_index <memdir> [--check]\n"
          "       python3 -m refmatrix.memory_index --repair-cut-hooks <memdir> "
          "[--apply] [--restore <key>=<text> ...]")


def main(argv: "list[str] | None" = None) -> int:
    """The module entry. Every `--` flag is a known one or an error: HEAD
    dropped any `--` arg it did not know and rendered, so a mistyped
    `--repair-cut-hook` would have REWRITTEN the index it meant to inspect
    (bug-195, 2026-11-10)."""
    args = list(sys.argv[1:] if argv is None else argv)
    checking = applying = False
    repair: "str | None" = None
    restores: list = []
    pos: list = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--repair-cut-hooks", "--restore"):
            if i + 1 >= len(args):
                print(f"{a} needs a value\n{_USAGE}", file=sys.stderr)
                return 2
            if a == "--restore":
                restores.append(args[i + 1])
            elif repair is not None:
                print(f"--repair-cut-hooks given twice\n{_USAGE}", file=sys.stderr)
                return 2
            else:
                repair = args[i + 1]
            i += 2
            continue
        if a == "--check":
            checking = True
        elif a == "--apply":
            applying = True
        elif a.startswith("--"):
            print(f"unknown flag {a}\n{_USAGE}", file=sys.stderr)
            return 2
        else:
            pos.append(a)
        i += 1
    if repair is not None:
        if pos or checking:
            print(f"--repair-cut-hooks takes its memdir as its value and no other "
                  f"argument or --check\n{_USAGE}", file=sys.stderr)
            return 2
        return repair_cut_hooks(Path(repair), apply=applying, restores=restores)
    if applying or restores:
        print(f"--apply / --restore belong to --repair-cut-hooks\n{_USAGE}",
              file=sys.stderr)
        return 2
    if len(pos) != 1:
        print(_USAGE, file=sys.stderr)
        return 2
    memdir = Path(pos[0])
    if checking:
        ok = check(memdir)
        print(f"{INDEX_NAME}: {'in sync' if ok else 'STALE — run without --check'}")
        return 0 if ok else 1
    write(memdir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
