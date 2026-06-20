"""Shared memory-tag taxonomy.

A controlled, hub-level vocabulary so memories are categorized consistently
across every store. Lives at `~/.refmatrix/taxonomy.json` (override the home
with `RMX_HOME`). `mtype` stays the coarse class; tags are the fine, taxonomy-
validated facet. Validation is SOFT — an off-vocabulary tag warns, never blocks
(reuses the existing JSON `tags` column, so there is no schema migration).
"""
from __future__ import annotations

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


def load() -> dict:
    """Load the taxonomy, seeding the default on first use. Best-effort: a
    corrupt file falls back to the default rather than raising."""
    p = taxonomy_path()
    if not p.exists():
        try:
            save(DEFAULT_TAXONOMY)
        except OSError:
            pass
        return json.loads(json.dumps(DEFAULT_TAXONOMY))
    try:
        data = json.loads(p.read_text())
        if not isinstance(data, dict) or "categories" not in data:
            return json.loads(json.dumps(DEFAULT_TAXONOMY))
        return data
    except (json.JSONDecodeError, OSError):
        return json.loads(json.dumps(DEFAULT_TAXONOMY))


def save(data: dict) -> None:
    p = taxonomy_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(p)


def all_tags(data: dict | None = None) -> set[str]:
    data = data or load()
    out: set[str] = set()
    for cat in data.get("categories", {}).values():
        out.update((cat.get("tags") or {}).keys())
    return out


def category_of(tag: str, data: dict | None = None) -> str | None:
    data = data or load()
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
    Persists and returns the updated taxonomy."""
    data = load()
    cats = data.setdefault("categories", {})
    cat = cats.setdefault(category, {"description": "", "tags": {}})
    cat.setdefault("tags", {})[name] = {"description": description, "color": color}
    save(data)
    return data


def remove_tag(name: str) -> bool:
    """Remove a tag from wherever it lives. Returns True if removed."""
    data = load()
    for cat in data.get("categories", {}).values():
        tags = cat.get("tags") or {}
        if name in tags:
            del tags[name]
            save(data)
            return True
    return False
