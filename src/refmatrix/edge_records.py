"""The ONE edge-record format: a link, unlink or evidence row named by both ends.

Two writers used to spell an edge differently. facts.log events named the concept end by NAME only
(`c`) and the entity end by kind and name (`e_kind`, `e`); the parallel-ingest recorder
(`ingest_records.py`) spelled the same edge `src` / `dst`. The missing concept kind is bug-117: a
rebuild looked every concept up as kind `concept`, so every edge whose concept end is a doc anchor,
a memory row or a code symbol (every GMD `rel:` edge) was dropped on replay, with no count.

Fields, for every edge record:

    op        "link" | "unlink" | "evidence"
    linkage   the linkage type name
    c_kind    the concept end's entity kind ("concept", "doc", "code", "memory")
    c         the concept end's name
    e_kind    the entity end's kind
    e         the entity end's name

`link` adds `weight`; `evidence` adds `file`, `line`, `span_end`, `detail`. A facts.log event also
carries `ts` and, when known, `partition`. In an ingest record the end values may still be
symbolic @-refs (`ingest_records` grammar) that resolve at apply time, and a kind is None when the
recorder cannot know it yet; the field NAMES are the same.
"""
from __future__ import annotations

from typing import Iterable

EDGE_OPS = frozenset({"link", "unlink", "evidence"})

# The only legacy rule: what an edge event written BEFORE `c_kind` existed means. A `concept` of
# that name wins (the rule every old rebuild applied); otherwise a name held by exactly ONE entity
# kind in the partition is that entity. Anything else is ambiguous or missing, and the caller
# COUNTS it — a guess would attach a row to the wrong node, which is worse than dropping it.
_LEGACY_PREFERRED_KIND = "concept"


def edge_fields(linkage: str, c_kind: "str | None", c: str, e_kind: "str | None", e: str,
                **extra) -> dict:
    """The edge's fields in canonical order, without `op`. `extra` carries `weight` for a link
    and `file` / `line` / `span_end` / `detail` for evidence."""
    out = {"linkage": linkage, "c_kind": c_kind, "c": c, "e_kind": e_kind, "e": e}
    out.update(extra)
    return out


def edge_event(op: str, linkage: str, c_kind: "str | None", c: str,
               e_kind: "str | None", e: str, **extra) -> dict:
    """A full edge record: `{"op": op, **edge_fields(...)}`."""
    if op not in EDGE_OPS:
        raise ValueError(f"not an edge op: {op!r}")
    return {"op": op, **edge_fields(linkage, c_kind, c, e_kind, e, **extra)}


def resolve_legacy_kind(kinds: Iterable[str]) -> "str | None":
    """The concept end's kind for a legacy event, given every kind an entity of that NAME has in
    the event's partition. None means ambiguous or missing (the caller counts it)."""
    ks = set(kinds)
    if _LEGACY_PREFERRED_KIND in ks:
        return _LEGACY_PREFERRED_KIND
    if len(ks) == 1:
        return next(iter(ks))
    return None
