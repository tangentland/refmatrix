"""Shared memory-tag taxonomy.

A controlled, hub-level vocabulary so memories are categorized consistently
across every store. Lives at `~/.refmatrix/taxonomy.json` (override the home
with `RMX_HOME`). `mtype` stays the coarse class; tags are the fine, taxonomy-
validated facet. Validation is SOFT — an off-vocabulary tag warns, never blocks
(reuses the existing JSON `tags` column, so there is no schema migration).
"""
from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
from typing import Any

TAXONOMY_FILE = "taxonomy.json"

# Seeded on first load. Categories map to {description, tags:{tag:{description,
# color}}}. Aligns with the MEMORY-RULES memory types + common engineering
# facets so the vocabulary is useful before anyone curates it.
DEFAULT_TAXONOMY: dict[str, Any] = {
    "version": 1,
    "categories": {
        "behavior": {
            "description": "How Claude should work — cross-project, promote to global.",
            "tags": {
                "tone": {"description": "Communication style preferences.", "color": "#8b5cf6"},
                "git-policy": {"description": "Commit/branch/push conventions.", "color": "#8b5cf6"},
                "tooling": {"description": "Preferred tools and workflows.", "color": "#8b5cf6"},
                "workflow": {"description": "Process / how-to-work rules.", "color": "#8b5cf6"},
            },
        },
        "architecture": {
            "description": "Durable design facts and structure.",
            "tags": {
                "design": {"description": "Design decisions and rationale.", "color": "#0ea5e9"},
                "data-model": {"description": "Schema / storage shape.", "color": "#0ea5e9"},
                "concurrency": {"description": "Locking / threading / async.", "color": "#0ea5e9"},
            },
        },
        "decision": {
            "description": "A choice made, with its reasoning.",
            "tags": {
                "tradeoff": {"description": "Weighed alternatives.", "color": "#f59e0b"},
                "chosen-direction": {"description": "The committed path.", "color": "#f59e0b"},
            },
        },
        "gotcha": {
            "description": "Non-obvious traps, bugs, and their fixes.",
            "tags": {
                "bug": {"description": "A defect and its resolution.", "color": "#ef4444"},
                "env": {"description": "Environment / setup pitfalls.", "color": "#ef4444"},
                "perf": {"description": "Performance pitfalls.", "color": "#ef4444"},
            },
        },
        "reference": {
            "description": "Pointers to external resources.",
            "tags": {
                "url": {"description": "Links / dashboards / tickets.", "color": "#10b981"},
                "command": {"description": "Useful invocations.", "color": "#10b981"},
            },
        },
    },
}


def user_home() -> Path:
    """The user-level refmatrix home (`~/.refmatrix`, override via RMX_HOME)."""
    env = os.environ.get("RMX_HOME")
    return Path(env).expanduser() if env else Path.home() / ".refmatrix"


def taxonomy_path() -> Path:
    return user_home() / TAXONOMY_FILE


class TaxonomyCorrupt(RuntimeError):
    """The taxonomy file exists but is not a vocabulary (unparseable JSON, or no
    `categories`). Writers refuse to replace it; readers degrade with a warning."""


def _empty() -> dict:
    return {"version": 1, "categories": {}}


def _parse(p: Path) -> dict:
    """The vocabulary in `p`. Missing → a copy of the defaults (nothing is written).
    Unparseable / not a vocabulary → `TaxonomyCorrupt` naming the file. Any other
    read error propagates."""
    try:
        raw = p.read_text()
    except FileNotFoundError:
        return json.loads(json.dumps(DEFAULT_TAXONOMY))
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise TaxonomyCorrupt(f"taxonomy file {p} is corrupt ({e}); refusing to overwrite "
                              f"it — repair or move it aside") from e
    if not isinstance(data, dict) or not isinstance(data.get("categories"), dict):
        raise TaxonomyCorrupt(f"taxonomy file {p} is corrupt (no `categories` mapping); "
                              f"refusing to overwrite it — repair or move it aside")
    return data


def read() -> "tuple[dict, list[str]]":
    """`(vocabulary, warnings)` for READERS — never writes.

    Task 3.7 #fam-taxonomy-corrupt (data loss): `load` silently fell back to the defaults
    on a corrupt file, and the next `add` / `remove` saved those defaults over the user's
    vocabulary; it also wrote the default file on the first read. Now a corrupt or
    unreadable file degrades to an EMPTY vocabulary plus a warning naming it — tag
    validation then checks against nothing, so `memory add` / `retag` are never blocked —
    and a missing file reads as the defaults without creating it."""
    p = taxonomy_path()
    try:
        return _parse(p), []
    except TaxonomyCorrupt as e:
        return _empty(), [str(e)]
    except OSError as e:
        return _empty(), [f"taxonomy file {p} is unreadable ({e}); tags are not validated"]


def load() -> dict:
    """The vocabulary for callers that only need the data (the hub UI). Never writes;
    a corrupt file reads as empty — `read()` carries the warning."""
    return read()[0]


@contextlib.contextmanager
def _locked():
    """Exclusive `fcntl` lock on the SIDECAR `taxonomy.json.lock` (task 3.7 r6 M3).
    Never on `taxonomy.json` itself: `save` replaces that inode by rename, so a lock
    held on it would guard a file nobody reads any more. The sidecar is never deleted."""
    import fcntl
    p = taxonomy_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p.with_name(p.name + ".lock"), "a+") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def save(data: dict) -> None:
    """Atomic replace: write a temp file, fsync it, rename it over `taxonomy.json`.
    Callers hold `_locked()`."""
    p = taxonomy_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    with open(tmp, "w") as fh:
        fh.write(json.dumps(data, indent=2))
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, p)


def tag_warnings(tags: "list[str]") -> "list[str]":
    """The soft note for off-vocabulary tags, shared by the `memory_add` verb, the
    `rmx_memory` retag action and their CLI twins (task 3.7 #fam-taxonomy, r1 M6). A corrupt
    vocabulary yields its own warning instead of flagging every tag."""
    if not tags:
        return []
    data, warns = read()
    if warns:
        return warns
    _, unknown = validate(list(tags), data)
    if not unknown:
        return []
    return [f"off-vocabulary tag(s): {', '.join(unknown)} — add via rmx_taxonomy "
            f"(action add) / `rmx taxonomy add <category> <tag>`"]


def all_tags(data: dict | None = None) -> set[str]:
    data = data if data is not None else load()
    out: set[str] = set()
    for cat in data.get("categories", {}).values():
        out.update((cat.get("tags") or {}).keys())
    return out


def category_of(tag: str, data: dict | None = None) -> str | None:
    data = data if data is not None else load()
    for cat_name, cat in data.get("categories", {}).items():
        if tag in (cat.get("tags") or {}):
            return cat_name
    return None


def validate(tags: list[str], data: dict | None = None) -> tuple[list[str], list[str]]:
    """Split `tags` into (known, unknown) against the vocabulary. Callers warn
    on unknown — they never block."""
    known_vocab = all_tags(data)
    known = [t for t in tags if t in known_vocab]
    unknown = [t for t in tags if t not in known_vocab]
    return known, unknown


def add_tag(
    category: str, name: str, *, description: str = "", color: str = "#64748b",
) -> dict:
    """Add (or update) a tag under a category, creating the category if needed.
    Persists and returns the updated taxonomy. Raises `TaxonomyCorrupt` rather than
    replace a corrupt file (task 3.7 #fam-taxonomy-corrupt)."""
    with _locked():
        data = _parse(taxonomy_path())
        cats = data.setdefault("categories", {})
        cat = cats.setdefault(category, {"description": "", "tags": {}})
        cat.setdefault("tags", {})[name] = {"description": description, "color": color}
        save(data)
    return data


def remove_tag(name: str) -> bool:
    """Remove a tag from wherever it lives. Returns True if removed. Raises
    `TaxonomyCorrupt` rather than replace a corrupt file."""
    with _locked():
        data = _parse(taxonomy_path())
        for cat in data.get("categories", {}).values():
            tags = cat.get("tags") or {}
            if name in tags:
                del tags[name]
                save(data)
                return True
    return False
