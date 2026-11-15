"""`--pack`: recall rows rendered as a pointer-first text payload under a UTF-8 byte budget.

Why (task 25.1 R3/R4/R8/R9, building task 19.1 R3-R8; bug-164, 2026-11-11): the recall hooks
printed `--json`, a list of whole rows with multi-kB bodies, so 12 hits were 15-59 kB and Claude
Code handed the model a 2 kB preview of the first row. A pointer -- one line naming the memory,
its curated hook and the exact command that fetches it -- costs ~200-370 B, so the same budget
carries every hit the recall found, and the bodies follow only while whole ones still fit.

The format (19.1 R3):

    # rmx recall · <channel> · <N> hits · budget <B> B
    - <name> — <title> — <hook>  (rmx memory get <name>[ --scope global])
    ...one hook line per NAMED hit, all of them before any body...
    ## <name>
    <the row's content, whole>
    +<M> more: <command that lists every hit>

`pack` is pure: no I/O, no telemetry, no store. It is called ONCE per recall, by the verb, on the
final row list (after every source is merged and excluded, R4), and it returns the byte spans of
what it named (R9) for the ONE emitter (`cli._RecallCall` / the verb's MCP branch) -- the packer
itself emits nothing, so a hit can never be counted delivered twice.
"""
from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from refmatrix.hook_budget import clip_utf8, fit_blocks, nbytes

# R3(d): the query in a trailer is collapsed to one line and capped.
TRAILER_QUERY_CHARS = 120
# A first-sentence hook longer than this is cut on a word boundary (a hook is a pointer).
FIRST_SENTENCE_CHARS = 200


@dataclass(frozen=True)
class Packed:
    """`text` (the payload), `spans` (one per NAMED hit, in order: the hit's identity plus
    `offset_bytes`/`bytes` of its hook line, newline included, and `body_offset_bytes`/
    `body_bytes` of its body or None), `named` (the named hits' names, in order), `more` (the
    trailer's count = hits given but not named) and `payload_bytes` (UTF-8 length of text)."""
    text: str
    spans: "list[dict]" = field(default_factory=list)
    named: "list[str]" = field(default_factory=list)
    more: int = 0
    payload_bytes: int = 0


def _one_line(text: str) -> str:
    return " ".join(str(text or "").split())


_SENTENCE_END = re.compile(r"(?<=[.!?])\s")


def first_sentence(content: "str | None") -> str:
    """19.1 R3(b)'s fallback hook: the first prose sentence of a row's content -- frontmatter,
    headings, `rel:` lines and blank lines skipped, cut at the first sentence end."""
    text = str(content or "")
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                lines = lines[i + 1:]
                break
    para: "list[str]" = []
    for ln in lines:
        s = ln.strip()
        if not s:
            if para:
                break
            continue
        if s.startswith(("#", "rel:", ">", "```", "|")) and not para:
            continue
        para.append(s)
    prose = " ".join(para)
    m = _SENTENCE_END.search(prose)
    out = prose[:m.start()] if m else prose
    if len(out) > FIRST_SENTENCE_CHARS:
        cut = out[:FIRST_SENTENCE_CHARS].rsplit(" ", 1)[0]
        out = (cut or out[:FIRST_SENTENCE_CHARS]) + " …"
    return out


def _path_key_hook(hooks: "Mapping[str, str]", source_path: str) -> "str | None":
    """The hook keyed by the row's path RELATIVE to the memdir. `pack` is not told the memdir,
    so the relative key is found as the longest path key the row's `source_path` ends with
    (`/<key>`, or equal): `fx_mem_00.md` and `project/fx_mem_00.md` both resolve, and a bare
    id key (no `/`, no `.md`) never matches a path."""
    best = None
    for key, hook in hooks.items():
        if not key or not str(key).endswith(".md"):
            continue
        if source_path == key or source_path.endswith("/" + str(key)):
            if best is None or len(key) > len(best[0]):
                best = (key, hook)
    return best[1] if best else None


def hook_for(row: dict, hooks: "Mapping[str, str]") -> str:
    """R4 (r3 #m2): the curated hook looked up by the row's memory id (its name) first, then by
    its path relative to the memdir (`metadata.source_path`), else the first sentence."""
    name = str(row.get("name") or "")
    h = hooks.get(name) if name else None
    if not h:
        sp = (row.get("metadata") or {}).get("source_path") or row.get("path")
        if sp:
            h = _path_key_hook(hooks, str(sp))
    return _one_line(h) if h else _one_line(first_sentence(row.get("content")))


def _title_of(row: dict) -> "str | None":
    t = (row.get("metadata") or {}).get("title") or row.get("title")
    t = _one_line(t) if t else ""
    return t if t and t != row.get("name") else None


def fetch_of(row: dict) -> str:
    """R6: the scope-correct fetch pointer -- a global row reads the global store."""
    cmd = f"rmx memory get {shlex.quote(str(row.get('name')))}"
    return cmd + (" --scope global" if row.get("scope") == "global" else "")


def hook_line(row: dict, hooks: "Mapping[str, str]") -> str:
    """`- <name> — <title> — <hook>  (<fetch>)` + newline (19.1 R3(b)); one line, always."""
    parts = [str(row.get("name"))]
    title = _title_of(row)
    if title:
        parts.append(title)
    parts.append(hook_for(row, hooks))
    return "- " + " — ".join(parts) + f"  ({fetch_of(row)})\n"


def more_command(*, mode: str, query: "str | None", k_more: int, since: "str | None",
                 subject: "str | None", scoped_both: bool) -> str:
    """R3(d): the command that lists every hit, mode by mode."""
    scope = " --scope both" if scoped_both else ""
    if mode == "session-start":
        return f"rmx memory recall --session-start --k {int(k_more)}{scope}"
    if mode == "recent":
        win = f" --since {shlex.quote(since)}" if since else ""
        return f"rmx memory recall --recent{win} --k {int(k_more)}{scope}"
    if mode == "subject":
        return (f"rmx memory recall --subject {shlex.quote(str(subject or ''))} "
                f"--k {int(k_more)}{scope}")
    q = _one_line(query)[:TRAILER_QUERY_CHARS]
    return f"rmx memory recall {shlex.quote(q)} --k {int(k_more)}{scope}"


def header_line(*, channel: str, hits: int, max_bytes: int) -> str:
    """19.1 R3(a): one line naming the channel, the hit count and the budget."""
    return f"# rmx recall · {channel} · {hits} hits · budget {max_bytes} B\n"


def _span_base(row: dict) -> dict:
    return {"name": row.get("name"), "entity_id": row.get("id") or row.get("entity_id"),
            "kind": row.get("kind") or "memory", "mtype": row.get("mtype"),
            "scope": row.get("scope") or "project", "partition": row.get("partition")}


def pack(rows: "Sequence[dict]", *, hooks: "Mapping[str, str]", max_bytes: int,
         channel: str, query: "str | None", mode: str, k_more: int,
         since: "str | None" = None, subject: "str | None" = None,
         global_hooks: "Mapping[str, str] | None" = None) -> Packed:
    """Pack `rows` (final, ranked) into at most `max_bytes` UTF-8 bytes.

    1. The header.
    2. One hook line per hit, in rank order, through `hook_budget.fit_blocks`: whole lines, a
       prefix, and the `+M more: <cmd>` trailer when any hit is left unnamed (R8: named + M =
       hits given).
    3. Bodies, in rank order over the NAMED hits, each whole, each only if it still fits in
       front of the trailer (R3(c): never a cut body; a body is not a second named hit) --
       on every channel except `prompt_recall`, which is a pointer list (d3).
    4. Loud overflow (19.1 R5): when the header plus the first hook line does not fit, the
       header plus ONE line naming N -- never empty, never over N.

    `hooks` is `memory_index.load_hooks(memdir)` unchanged (R4). `global_hooks`, when given,
    is the map for `scope == "global"` rows (the verb passes `{}`: no global curated dir is
    registered, and a same-named PROJECT hook would point at another row); None = `hooks`
    serves every row.
    """
    if max_bytes <= 0:
        raise ValueError(f"pack: max_bytes must be positive, got {max_bytes!r}")
    rows = list(rows)
    n = len(rows)
    head = header_line(channel=channel, hits=n, max_bytes=max_bytes)
    cmd = more_command(mode=mode, query=query, k_more=k_more, since=since, subject=subject,
                       scoped_both=any(r.get("scope") == "global" for r in rows))

    def trailer(m: int) -> str:
        # Newline INCLUDED and counted (2026-11-13): every pack ends in one, so the CLI writes
        # the text byte for byte (AC-7) and adds no newline the budget never counted -- a text
        # of exactly N bytes plus click.echo's newline was N+1 bytes on the wire (R8).
        return f"+{m} more: {cmd}\n"

    lines = [hook_line(r, global_hooks if (global_hooks is not None
                                           and r.get("scope") == "global") else hooks)
             for r in rows]
    room = max_bytes - nbytes(head)
    fitted = fit_blocks(lines, room, trailer=trailer) if (lines and room > 0) else None
    if n and (fitted is None or fitted.kept == 0):
        # 19.1 R5: not even one hook line fits beside the header.
        err = (f"+{n} more: {cmd}  (! budget {max_bytes} B fits no hook line; "
               f"raise --max-bytes)\n")
        if nbytes(head) + nbytes(err) > max_bytes:
            err = f"! recall: budget {max_bytes} B fits no hook line ({n} hits)\n"
        if nbytes(head) + nbytes(err) > max_bytes:
            text = clip_utf8(head + err, max_bytes)
        else:
            text = head + err
        return Packed(text=text, spans=[], named=[], more=n, payload_bytes=nbytes(text))
    if not n:
        text = clip_utf8(head, max_bytes)
        return Packed(text=text, spans=[], named=[], more=0, payload_bytes=nbytes(text))

    kept = fitted.kept
    named_rows = rows[:kept]
    dropped = n - kept
    tail = trailer(dropped) if dropped else ""
    tail_bytes = nbytes(tail) if tail else 0

    spans: "list[dict]" = []
    pos = nbytes(head)
    for r, ln in zip(named_rows, lines[:kept]):
        b = nbytes(ln)
        spans.append({**_span_base(r), "offset_bytes": pos, "bytes": b,
                      "body_offset_bytes": None, "body_bytes": None})
        pos += b
    body_text = ""
    # d3 (task 25.1): the per-prompt pack is a POINTER list. A body there would re-inject
    # kBs of the same memory on every prompt, so `prompt_recall` carries hook lines only;
    # bodies are a session_start / precompact (once per session) feature.
    with_bodies = channel != "prompt_recall"
    for i, r in enumerate(named_rows if with_bodies else []):
        content = r.get("content")
        if not content:
            continue
        prefix = f"## {r.get('name')}\n"
        suffix = "" if str(content).endswith("\n") else "\n"
        block = prefix + str(content) + suffix
        if pos + nbytes(block) + tail_bytes > max_bytes:
            continue
        spans[i]["body_offset_bytes"] = pos + nbytes(prefix)
        spans[i]["body_bytes"] = nbytes(str(content))
        body_text += block
        pos += nbytes(block)
    text = head + "".join(lines[:kept]) + body_text + tail
    return Packed(text=text, spans=spans, named=[str(r.get("name")) for r in named_rows],
                  more=dropped, payload_bytes=nbytes(text))
