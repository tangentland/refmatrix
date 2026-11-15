#!/usr/bin/env python3
"""The ONE resolver of the curated memory dir `scripts/lint-gmd.sh` adds to its lint scope.

WHY (bug-155's residual, bug-254; T0.1' R1.4, 2026-11-15). The workflow ledger and the docs cite
memory ids (`[[feedback_…]]`, `[[impression_…]]`) that resolve only when the memory files are in
the scanned set, so the gate scans `<home>/.claude/projects/<slug>/memory`. bug-155's second
cause was that a littlebig clone has a slug of its own and no memory dir there. The fix that
shipped on 2026-11-14 (`44d1a34`) was bash in `lint-gmd.sh` plus a Python copy of the same logic
in the repo-scope test, and both copies:

- tested only that the own-slug dir EXISTS. Claude Code creates an empty `memory/` for any
  session whose cwd is the checkout, so an empty dir was taken, no fallback was tried, and every
  memory-id ref dangled with no line on stderr (1,235 `dangling-doc`, exit 1);
- followed the origin ONE hop. A clone of a clone (8 of the 33 littlebig clones, every review
  clone cut from an author's clone) reached a slug with no memory dir and stopped there (1,235
  `dangling-doc` in the reviewer's own clone).

A third copy of the slug rule in `tests/test_bug179_anchor_parity.py` read the sandbox's decoy
home and never found a memory dir at all (bug-254). This module replaces all of them: the script
calls it under `python3` (never the dev venv, which a no-venv clone lacks: bug-253), and the
tests import it in-process. It is stdlib only.

Rules (task-t0-suite-trust-sweep `#r1-4`):
- a memory dir counts only if it holds at least one `*.md` file ("present" means populated);
- when the own-slug dir is absent or empty, the checkout's `origin` is read and canonicalised
  (a URL with a scheme or an scp-style `host:path` is non-local and stops the walk; a relative
  path is resolved against the checkout it was read from; the path is `resolve()`d and a
  trailing `.git` component or suffix is stripped), then slugged and tried;
- the walk follows local origins hop by hop, and stops at the first populated dir, or, with no
  dir, at a checkout with no origin, a path that is not a checkout, a non-local origin, a cycle
  (a canonical path already visited), or the bound of 5 origins followed;
- whenever the own-slug dir is not the one used, ONE line says so, naming every checkout tried,
  in order, with why it was passed over, and then the dir used or why the walk stopped. Nothing
  here is silent: a git failure other than "no such remote" raises.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

# Origins followed from the checkout being linted before the walk gives up (ruling L122).
BOUND = 5

# `git remote get-url` exits 2 when the named remote does not exist (git-remote(1)).
_GIT_NO_SUCH_REMOTE = 2

# Variables that would point `git -C <path>` at a different repository than <path> (a gate run
# from inside a git hook inherits GIT_DIR); the walk reads each checkout's OWN origin.
_GIT_LOCATING_ENV = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE",
                     "GIT_PREFIX", "GIT_OBJECT_DIRECTORY")

_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")

_NO_DIR_TAIL = "no memory dir; memory-id refs will surface as dangling-doc"


def slug(path) -> str:
    """The `~/.claude/projects/<slug>` name of a checkout path: `/` and `_` become `-`.

    Public so the script-level tests build their decoy homes from it and keep no copy of the
    rule (a third copy is what R1.4 removes; ruling L124)."""
    return str(path).replace("/", "-").replace("_", "-")


def memdir_for(home, checkout) -> Path:
    """`<home>/.claude/projects/<slug(checkout)>/memory`, whether or not it exists."""
    return Path(home) / ".claude" / "projects" / slug(checkout) / "memory"


def _state(d: Path) -> str:
    """`populated` (holds >= 1 `*.md` file), `empty` (a dir with none) or `absent`."""
    if not d.is_dir():
        return "absent"
    if any(p.is_file() for p in d.glob("*.md")):
        return "populated"
    return "empty"


def _git_env() -> dict:
    return {k: v for k, v in os.environ.items() if k not in _GIT_LOCATING_ENV}


def _not_a_checkout(p: Path) -> "str | None":
    """None when `p` is the top of a git checkout; otherwise why not, from git's own words.

    Asked of git (`rev-parse --show-toplevel` must name `p` itself), not read off a `.git`
    entry: a plain dir inside some other repository would otherwise borrow that repository's
    origin, and an empty `.git` marker dir (the gate-root fixtures of the bug-179/216/230 tests
    make one) is no checkout at all. The reason travels into the note, so it is never silent."""
    if not p.is_dir():
        return "does not exist" if not p.exists() else "is not a directory"
    r = subprocess.run(["git", "-C", str(p), "rev-parse", "--show-toplevel"],
                       capture_output=True, text=True, env=_git_env())
    if r.returncode != 0:
        first = (r.stderr.strip().splitlines() or [f"exit {r.returncode}"])[0]
        return f"git: {first}"
    top = Path(r.stdout.strip()).resolve()
    if top != p.resolve():
        return f"it lies inside the checkout {top}"
    return None


def _origin_url(checkout: Path) -> "str | None":
    """The checkout's `origin` URL as git reports it, or None when it has no `origin` remote.
    Any other git failure raises: an unreadable origin is not the same answer as no origin."""
    r = subprocess.run(["git", "-C", str(checkout), "remote", "get-url", "origin"],
                       capture_output=True, text=True, env=_git_env())
    if r.returncode == _GIT_NO_SUCH_REMOTE:
        return None
    if r.returncode != 0:
        raise RuntimeError(f"git remote get-url origin failed in {checkout} "
                           f"(exit {r.returncode}): {r.stderr.strip()}")
    url = r.stdout.strip()
    return url or None


def _is_non_local(url: str) -> bool:
    """A URL with a scheme (`ssh://`, `https://`, `file://`, …) or git's scp-style `host:path`
    (a `:` before the first `/`) names no local checkout path."""
    if _SCHEME.match(url):
        return True
    colon = url.find(":")
    slash = url.find("/")
    return colon > 0 and (slash < 0 or colon < slash)


def canonical_origin(url: str, checkout: Path) -> Path:
    """The canonical checkout path a LOCAL origin URL names: relative to the checkout it was read
    from, `resolve()`d (symlinks, `..`, trailing `/`), with a trailing `.git` component or
    suffix stripped, so every spelling of one origin gives one path and one slug."""
    p = Path(url)
    if not p.is_absolute():
        p = Path(checkout) / p
    p = p.resolve()
    if p.name == ".git":
        p = p.parent
    elif p.name.endswith(".git") and len(p.name) > len(".git"):
        p = p.with_name(p.name[:-len(".git")])
    return p.resolve()


def resolve_memdir(root, home) -> "tuple[Path | None, str]":
    """The memory dir the gate scans for checkout `root` under `home`, and the one-line note to
    print (empty when the own-slug dir is the one used). See the module docstring for the rules.
    Returns `(None, note)` when no dir qualifies; the note then says memory-id refs will surface
    as `dangling-doc`."""
    home = Path(home)
    current = Path(root).resolve()
    visited = {current}
    parts: list = []
    followed = 0
    label = "memory dir for"
    while True:
        d = memdir_for(home, current)
        state = _state(d)
        if state == "populated":
            if not parts:
                return d, ""
            parts.append(f"using {label} {current} ({d})")
            return d, "; ".join(parts)
        parts.append(f"{label} {current} {state} ({d})")
        label = "origin"
        # Every origin was checked before it was followed; only the root is checked here.
        why = _not_a_checkout(current) if followed == 0 else None
        if why is not None:
            parts.append(f"{current} is not a checkout ({why})")
            break
        url = _origin_url(current)
        if url is None:
            parts.append(f"{current} has no origin")
            break
        if _is_non_local(url):
            parts.append(f"origin {url} of {current} is a non-local origin")
            break
        if followed >= BOUND:
            parts.append(f"origin {url} of {current} not followed: stopped at the bound of "
                         f"{BOUND} origins followed")
            break
        nxt = canonical_origin(url, current)
        if nxt in visited:
            parts.append(f"origin {nxt} of {current} was already tried, a cycle")
            break
        why = _not_a_checkout(nxt)
        if why is not None:
            parts.append(f"origin {nxt} of {current} is not a checkout ({why})")
            break
        visited.add(nxt)
        followed += 1
        current = nxt
    parts.append(_NO_DIR_TAIL)
    return None, "; ".join(parts)


def main(argv: list) -> int:
    """`python3 scripts/gmd_memdir.py <root> <home>`: the chosen dir on stdout (nothing when none
    qualifies), the note on stderr as one `lint-gmd:` line. Exit 0 either way; a usage error is
    exit 2 and a git failure raises (non-zero), which `lint-gmd.sh` turns into its own exit 2."""
    if len(argv) != 2:
        sys.stderr.write("usage: gmd_memdir.py <checkout-root> <home>\n")
        return 2
    chosen, note = resolve_memdir(Path(argv[0]), Path(argv[1]))
    if note:
        sys.stderr.write(f"lint-gmd: {note}\n")
    if chosen is not None:
        sys.stdout.write(f"{chosen}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
