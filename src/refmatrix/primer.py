"""
`rmx primer` — emit a density-ranked, symbol-shape-filtered map of the
top-N concepts. Designed to be `@`-included from a project's CLAUDE.md so
any agent has cheap orientation without paying for the whole index.

Output is one line per concept:
    concept_name(total_refs) defines:N called_by:N mentions:N ...

Filtering heuristics:
- "symbol-like" names: contain _ or . or :: or a lowercase-then-uppercase
  transition (camelCase). This is what separates `register_graph_object`
  from `data` or `value`.
- exclude noise namespaces (keyword/, import/) by default.
- token budget — stop when the running estimate hits --max-tokens.
"""
from __future__ import annotations

import re
import time

from refmatrix.store import Store


# Identifier-shaped name detector. We accept either:
# - any namespaced concept (the slash itself is signal that it's structured)
# - or one of: underscore, dot, "::", lower→upper transition (camelCase)
# This treats `import/json` as symbol-like even though the bare token is short.
_SYMBOL_RE = re.compile(r"_|\.|::|[a-z][A-Z]")


def is_symbol_like(name: str) -> bool:
    if "/" in name:
        return True
    return bool(_SYMBOL_RE.search(name))


def concept_density(s: Store, kinds: tuple[str, ...] = ("concept",)) -> list[dict]:
    """Aggregate (concept, total_refs, per-linkage counts) sorted by total desc."""
    placeholders = ",".join("?" * len(kinds))
    rows = s._connect().execute(
        f"""
        SELECT el.concept_id   AS cid,
               c.name           AS name,
               lt.name           AS linkage,
               COUNT(*)          AS n
        FROM entity_links el
        JOIN linkage_types lt ON lt.id = el.linkage_id
        JOIN entities c       ON c.id = el.concept_id
        WHERE c.kind IN ({placeholders})
        GROUP BY el.concept_id, lt.name
        """,
        kinds,
    ).fetchall()

    by_cid: dict[int, dict] = {}
    for r in rows:
        d = by_cid.setdefault(r["cid"], {
            "concept_id": r["cid"], "name": r["name"],
            "by_link": {}, "total": 0,
        })
        d["by_link"][r["linkage"]] = r["n"]
        d["total"] += r["n"]
    out = sorted(by_cid.values(), key=lambda d: (-d["total"], d["name"]))
    return out


def build_primer(
    s: Store,
    *,
    top_n: int = 150,
    symbol_like_only: bool = True,
    exclude_namespaces: tuple[str, ...] = ("keyword",),
    min_refs: int = 2,
    max_tokens: int = 2000,
) -> str:
    rows = concept_density(s)
    excluded = set(exclude_namespaces)

    selected: list[dict] = []
    for r in rows:
        name = r["name"]
        if r["total"] < min_refs:
            break  # rows are sorted desc; once below threshold, all remaining are too
        if "/" in name:
            ns = name.split("/", 1)[0]
            if ns in excluded:
                continue
        if symbol_like_only and not is_symbol_like(name):
            continue
        selected.append(r)
        if len(selected) >= top_n:
            break

    header = [
        "# refmatrix primer — top reference-dense symbols",
        f"# generated {time.strftime('%Y-%m-%d %H:%M')} | "
        f"top_n={top_n} symbol_like={symbol_like_only} "
        f"exclude={','.join(sorted(excluded))} min_refs={min_refs}",
        "#",
        "# Format: NAME(total_refs) linkage:count linkage:count ...",
        "# Use this for orientation only — query the index for specifics:",
        "#   rmx context <name>      # bundle around a symbol",
        "#   rmx neighbors <name>    # graph walk",
        "#   rmx query \"<dsl>\"     # set algebra",
        "",
    ]
    out_lines = list(header)
    used = sum(len(line) // 4 for line in header) + len(header)

    for r in selected:
        link_str = " ".join(f"{ln}:{n}" for ln, n in sorted(r["by_link"].items()))
        line = f"{r['name']}({r['total']}) {link_str}"
        cost = len(line) // 4 + 1
        if used + cost > max_tokens:
            out_lines.append(
                f"# [truncated by --max-tokens={max_tokens}; "
                f"showed {len(out_lines) - len(header)} of {len(selected)} candidates]"
            )
            break
        out_lines.append(line)
        used += cost

    out_lines.append("")
    out_lines.append(f"# {len(selected)} candidates, ~{used} tokens")
    return "\n".join(out_lines)
