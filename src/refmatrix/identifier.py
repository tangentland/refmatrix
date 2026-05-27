"""
Identifier splitting + name-variant expansion for cross-case retrieval.

`canonicalize_name("JSONParser")` -> `"json_parser"`
`canonicalize_name("some-words")` -> `"some_words"`
`canonicalize_name("parse42Things")` -> `"parse_42_things"`
`canonicalize_name("HTTP_REQUEST")` -> `"http_request"`

`expand_name_variants(name)` returns the surface forms a single logical
identifier may appear as: the input, the canonical underscore-lowercase form,
the dash-joined lowercase form, and the space-joined lowercase form. Used by
the query/context/neighbors paths to widen the net when a caller (typically
an LLM) might pass any of these forms.

Used at the query INPUT boundary, not at ingest. Callers can opt out via
the `--strict` CLI flag, which routes through `Store.resolve_concept_ids(...,
strict=True)` and returns exact-name matches only.
"""
from __future__ import annotations

import re


# Multi-pattern identifier splitter. Order matters — patterns are tried left-
# to-right and the first match wins.
#
# `[A-Z]+(?=[A-Z][a-z])` -- leading acronym before a Word: HTTPServer -> HTTP
# `[A-Z]?[a-z]+`         -- standard word: Server, parser
# `[A-Z]+`               -- trailing acronym: parseHTML -> HTML
# `[0-9]+`               -- digit run: 42, v2
_PART_RE = re.compile(
    r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|[0-9]+"
)


def concept_parts(name: str) -> list[str]:
    """Split a name into lowercase parts on whitespace, _, -, camelCase,
    PascalCase (including acronym-leading like `JSONParser`), and digit
    boundaries (`parse42Things`)."""
    parts: list[str] = []
    for chunk in re.split(r"[\s_\-]+", name.strip()):
        if not chunk:
            continue
        for m in _PART_RE.findall(chunk):
            parts.append(m.lower())
    return parts


def canonicalize_name(name: str) -> str:
    """Return the canonical lowercase underscore form of an identifier.

    Single-part names (no boundary) are returned as `.lower()` of the input.
    Multi-part names are joined with `_`. Empty input returns empty string."""
    parts = concept_parts(name)
    if not parts:
        return name.strip().lower()
    return "_".join(parts)


def expand_name_variants(name: str) -> list[str]:
    """Return the de-duplicated surface forms an identifier may appear as.

    Always includes the original `name`. For multi-part identifiers, also
    includes the canonical underscore-lower form, the dash-joined lower form,
    and the space-joined lower form. Order preserved: original first, then
    canonical, then dash, then space. The caller uses this to widen exact-
    name lookups; pass each variant to the underlying name lookup and union
    the results."""
    stripped = name.strip()
    parts = concept_parts(stripped)
    out: list[str] = [stripped]
    if len(parts) >= 2:
        for variant in ("_".join(parts), "-".join(parts), " ".join(parts)):
            if variant not in out:
                out.append(variant)
    elif len(parts) == 1:
        # Single-part: include lowercase if it differs from original (covers
        # the SCREAMINGCASE -> screamingcase case for single-word acronyms).
        lower = parts[0]
        if lower != stripped:
            out.append(lower)
    return out
