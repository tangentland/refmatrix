"""cctree — prompt -> action tree log for Claude Code sessions.

Reads a Claude Code session transcript (JSONL under ~/.claude/projects/<slug>/)
and emits a tree of:

    TURN
      prompt          (raw user text)
      decoration      (hook additionalContext, skill/agent/tool listings)
      actions         (tool_use -> tool_result), nested for subagent sidechains
      response        (assistant text)

Usage:
    cctree.py                          # latest session in cwd's project
    cctree.py --list                   # list sessions for cwd's project
    cctree.py SESSION.jsonl            # explicit file
    cctree.py --session <uuid>         # by session id, searched across projects
    cctree.py --project /path/to/repo  # pick project by working dir
    cctree.py --json                   # structured output instead of tree
    cctree.py --follow                 # tail the live session
    cctree.py --full                   # do not truncate payloads


OWNED BY refmatrix. Moved in from ~/claude_tools/utilities/cctree.py; that
standalone copy is gone and this is the only one. The CLI entry point lives on
as `rmx cctree`, and the hub serves the same renderers over HTTP.

Stdlib only — importing this module must stay free of third-party deps so the
hub can render trees on a host without the [dense] extra installed, and so the
CLI keeps working when the embedder cannot load.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from html import escape as html_escape
from pathlib import Path
from typing import Any, Iterator

PROJECTS = Path.home() / ".claude" / "projects"

# attachment kinds that make up the "decorated" prompt actually sent to the model
DECORATION_KINDS = {
    "hook_additional_context",
    "hook_success",
    "skill_listing",
    "agent_listing_delta",
    "deferred_tools_delta",
    "system_reminder",
    "memory_file",
    "claude_md",
    "selected_lines",
    "file",
    "diagnostics",
}


# --------------------------------------------------------------------------- io


def slug_for(path: Path) -> str:
    """Claude Code encodes a project cwd as its path with / and _ both -> -.

    That is lossy, so it is only a fallback; prefer matching the recorded cwd.
    """
    return str(path.resolve()).replace("/", "-").replace("_", "-")


def project_dir(cwd: Path) -> Path | None:
    """Find the transcript dir for a working directory.

    Matches the cwd recorded inside each session first, since the directory-name
    encoding collapses _ into - and cannot be reversed reliably.
    """
    want = str(cwd.resolve())
    for d in all_projects():
        ss = sessions_in(d)
        if ss and session_cwd(ss[0]) == want:
            return d
    d = PROJECTS / slug_for(cwd)
    return d if d.is_dir() else None


def sessions_in(d: Path) -> list[Path]:
    return sorted(d.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)


def all_projects() -> list[Path]:
    return sorted(d for d in PROJECTS.glob("*") if d.is_dir() and any(d.glob("*.jsonl")))


def session_cwd(path: Path) -> str:
    """Real working directory for a session, read from its first records.

    The directory name is the cwd with / replaced by -, which is ambiguous for
    paths containing dashes, so prefer the recorded value.
    """
    try:
        with path.open(encoding="utf-8", errors="ignore") as fh:
            for i, line in enumerate(fh):
                if i > 40:
                    break
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("cwd"):
                    return rec["cwd"]
    except OSError:
        pass
    return path.parent.name


def find_session(session_id: str) -> Path | None:
    for p in PROJECTS.glob(f"*/{session_id}*.jsonl"):
        return p
    return None


def read_records(path: Path) -> list[dict]:
    out = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # partial trailing write while session is live
    return out


# ------------------------------------------------------------------------ model


@dataclass
class Action:
    tool: str
    tool_id: str
    input: dict
    uuid: str
    ts: str
    result: Any = None
    result_text: str = ""
    is_error: bool = False
    children: list["Action"] = field(default_factory=list)  # subagent actions
    agent_said: list[str] = field(default_factory=list)  # subagent's own text output
    agent_type: str | None = None
    agent_depth: int | None = None


@dataclass
class Turn:
    prompt: str
    ts: str
    uuid: str
    prompt_id: str
    source: str
    index: int = 0
    decorations: list[tuple[str, str]] = field(default_factory=list)  # (label, text)
    # chronological stream of what the model emitted: ("thinking"|"text"|"action", payload)
    stream: list[tuple[str, Any]] = field(default_factory=list)
    duration_ms: int | None = None

    @property
    def actions(self) -> list[Action]:
        return [p for k, p in self.stream if k == "action"]

    @property
    def response(self) -> list[str]:
        return [p for k, p in self.stream if k == "text"]

    @property
    def thinking(self) -> list[str]:
        return [p for k, p in self.stream if k == "thinking"]


def content_blocks(rec: dict) -> list[dict]:
    c = (rec.get("message") or {}).get("content")
    if isinstance(c, list):
        return [b for b in c if isinstance(b, dict)]
    return []


def content_string(rec: dict) -> str | None:
    c = (rec.get("message") or {}).get("content")
    return c if isinstance(c, str) else None


def is_user_prompt(rec: dict, allow_sidechain: bool = False) -> bool:
    """A real turn-opening prompt: string content, not a tool_result carrier.

    In a subagent transcript every record is a sidechain record and the opening
    line is the agent's own prompt, so callers parsing those pass allow_sidechain.
    """
    return (
        rec.get("type") == "user"
        and content_string(rec) is not None
        and rec.get("toolUseResult") is None
        and (allow_sidechain or not rec.get("isSidechain"))
    )


def decoration_text(att: dict) -> str:
    # Hook stdout is the most common thing to get offloaded, and it arrives as
    # a decoration rather than a tool result — so the rehydration has to happen
    # on this path too, not just in flatten_result.
    c = att.get("content")
    if isinstance(c, list):
        return _rehydrate_offload("\n".join(str(x) for x in c))
    if isinstance(c, str):
        return _rehydrate_offload(c)
    for k in ("addedLines", "stdout", "names"):
        v = att.get(k)
        if isinstance(v, list):
            return _rehydrate_offload("\n".join(str(x) for x in v))
        if isinstance(v, str) and v.strip():
            return _rehydrate_offload(v)
    return json.dumps({k: v for k, v in att.items() if k != "type"})[:2000]


def decoration_label(att: dict) -> str:
    kind = att.get("type", "attachment")
    hook = att.get("hookName") or att.get("hookEvent")
    return f"{kind}:{hook}" if hook else kind


# Anchored at the head of the payload on purpose. An offload stub always OPENS
# the text (optionally inside a <persisted-output> wrapper); a plain `search`
# would also fire on output that merely quotes the marker — e.g. a grep of a
# transcript — and rewrite an innocent result.
_OFFLOAD_RE = re.compile(
    r"\A\s*(?:<persisted-output>\s*)?"
    r"Output too large \([^)]*\)\.\s*Full output saved to:\s*(\S+)")


def _rehydrate_offload(text: str) -> str:
    """Swap an offloaded-output stub for the file it points at.

    Large tool/hook output is written to `<session>/tool-results/*.txt` and the
    transcript keeps only a ~2KB preview. Rendering the preview in a browsable
    tree reads as silent truncation — the reader has no way to know the rest
    exists. The full text is right there on disk, so read it.

    Keeps the stub when the file is gone or unreadable, and says which, rather
    than passing the preview off as the whole output.
    """
    m = _OFFLOAD_RE.match(text or "")
    if not m:
        return text
    p = Path(m.group(1))
    try:
        full = p.read_text(errors="replace")
    except OSError as e:
        return f"{text}\n\n[cctree: offloaded output unreadable — {e}]"
    return f"[cctree: rehydrated {len(full)} bytes from {p.name}]\n{full}"


def flatten_result(rec: dict) -> tuple[str, bool]:
    """Render a tool result to text plus an is_error flag, with offloaded
    output rehydrated from disk. One wrapper so every extraction branch below
    gets the treatment and none can be forgotten."""
    text, err = _flatten_result(rec)
    return _rehydrate_offload(text), err


def _flatten_result(rec: dict) -> tuple[str, bool]:
    err = False
    for b in content_blocks(rec):
        if b.get("type") == "tool_result":
            err = bool(b.get("is_error"))
    tur = rec.get("toolUseResult")
    if isinstance(tur, str):
        return tur, err
    if isinstance(tur, dict):
        if tur.get("stdout") or tur.get("stderr"):
            parts = []
            if tur.get("stdout"):
                parts.append(tur["stdout"])
            if tur.get("stderr"):
                parts.append("[stderr] " + tur["stderr"])
                err = err or bool(tur.get("stderr"))
            return "\n".join(parts), err
        for k in ("content", "text", "output", "result", "file"):
            v = tur.get(k)
            if isinstance(v, str):
                return v, err
            if isinstance(v, dict) and isinstance(v.get("content"), str):
                return v["content"], err
            if isinstance(v, list):
                return "\n".join(
                    x.get("text", json.dumps(x)) if isinstance(x, dict) else str(x)
                    for x in v
                ), err
        return json.dumps(tur, default=str), err
    # fall back to the rendered tool_result block
    for b in content_blocks(rec):
        if b.get("type") == "tool_result":
            c = b.get("content")
            if isinstance(c, str):
                return c, err
            if isinstance(c, list):
                return "\n".join(
                    x.get("text", "") if isinstance(x, dict) else str(x) for x in c
                ), err
    return "", err


# ------------------------------------------------------------------------ build


def build_turns(
    records: list[dict],
    allow_sidechain: bool = False,
    index: dict[str, Action] | None = None,
) -> list[Turn]:
    """Parse one transcript into turns.

    index, if given, collects every Action by its tool_use id across all
    transcripts so subagent runs can be grafted onto their spawning call.
    """
    # tool_use id -> Action, so results can find the call they belong to
    actions_by_tool_id: dict[str, Action] = {}
    # assistant record uuid -> Actions it emitted (sourceToolAssistantUUID target)
    actions_by_assistant_uuid: dict[str, list[Action]] = {}

    turns: list[Turn] = []
    cur: Turn | None = None

    for rec in records:
        rtype = rec.get("type")
        side = bool(rec.get("isSidechain")) and not allow_sidechain

        if rtype == "attachment" and cur is not None and not side:
            att = rec.get("attachment") or {}
            if att.get("type") in DECORATION_KINDS:
                text = decoration_text(att)
                if text.strip():  # silent hooks inject nothing; skip the empty entry
                    cur.decorations.append((decoration_label(att), text))
            continue

        if is_user_prompt(rec, allow_sidechain):
            cur = Turn(
                prompt=content_string(rec) or "",
                ts=rec.get("timestamp", ""),
                uuid=rec.get("uuid", ""),
                prompt_id=rec.get("promptId", ""),
                source=rec.get("promptSource") or rec.get("origin") or "user",
                index=len(turns) + 1,
            )
            turns.append(cur)
            continue

        if rtype == "assistant":
            for b in content_blocks(rec):
                bt = b.get("type")
                if bt == "thinking" and cur is not None and not side:
                    # transcripts keep the signature but usually not the plaintext,
                    # so record the step even when the body is empty
                    cur.stream.append(("thinking", b.get("thinking", "")))
                elif bt == "text" and cur is not None and not side:
                    txt = b.get("text", "")
                    if txt.strip():
                        cur.stream.append(("text", txt))
                elif bt == "tool_use":
                    act = Action(
                        tool=b.get("name", "?"),
                        tool_id=b.get("id", ""),
                        input=b.get("input") or {},
                        uuid=rec.get("uuid", ""),
                        ts=rec.get("timestamp", ""),
                    )
                    if side:
                        continue
                    actions_by_tool_id[act.tool_id] = act
                    if index is not None:
                        index[act.tool_id] = act
                    actions_by_assistant_uuid.setdefault(
                        rec.get("uuid", ""), []
                    ).append(act)
                    if cur is not None:
                        cur.stream.append(("action", act))
            continue

        if rtype == "user" and rec.get("toolUseResult") is not None:
            text, err = flatten_result(rec)
            target: Action | None = None
            for b in content_blocks(rec):
                if b.get("type") == "tool_result":
                    target = actions_by_tool_id.get(b.get("tool_use_id") or "")
                    break
            if target is None:
                src = rec.get("sourceToolAssistantUUID")
                cands = actions_by_assistant_uuid.get(src or "", [])
                target = cands[-1] if cands else None
            if target is not None:
                target.result = rec.get("toolUseResult")
                target.result_text = text
                target.is_error = err
            continue

        if rtype == "system" and rec.get("subtype") == "turn_duration" and cur:
            cur.duration_ms = rec.get("durationMs")

    return turns


@dataclass
class AgentRun:
    """A subagent whose actions do not nest under any call in this transcript."""

    meta: dict
    turns: list["Turn"]
    reason: str  # "teammate" (never tool-spawned) or "orphan" (spawning call missing)

    @property
    def label(self) -> str:
        m = self.meta
        name = m.get("name") or m.get("agentType") or "agent"
        atype = m.get("customAgentType") or m.get("agentType") or "?"
        team = f" team={m['teamName']}" if m.get("teamName") else ""
        return f"{name} <{atype}>{team}"


def graft_subagents(
    session_path: Path, index: dict[str, Action]
) -> tuple[int, list[AgentRun]]:
    """Attach subagent runs to the Agent call that spawned them.

    Layout: <session>/subagents/agent-<id>.jsonl paired with a .meta.json whose
    toolUseId names the spawning tool_use. Because that id may live inside another
    subagent's transcript, repeat until nothing new attaches — that resolves
    nesting to arbitrary depth regardless of file order.

    Team agents (taskKind: in_process_teammate) carry no toolUseId because no
    Agent call spawned them; they come back as top-level runs instead.
    """
    sub_dir = session_path.parent / session_path.stem / "subagents"
    if not sub_dir.is_dir():
        return 0, []

    pending: list[tuple[dict, Path]] = []
    standalone: list[AgentRun] = []
    for meta_path in sorted(sub_dir.glob("*.meta.json")):
        jsonl = meta_path.with_suffix("").with_suffix(".jsonl")
        if not jsonl.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not meta.get("toolUseId"):
            # team agent / fork: nothing spawned it via a tool call
            standalone.append(
                AgentRun(
                    meta,
                    build_turns(read_records(jsonl), allow_sidechain=True, index=index),
                    "teammate",
                )
            )
            continue
        pending.append((meta, jsonl))

    attached = 0
    while pending:
        progressed = False
        still: list[tuple[dict, Path]] = []
        for meta, jsonl in pending:
            parent = index.get(meta.get("toolUseId") or "")
            if parent is None:
                still.append((meta, jsonl))
                continue
            turns = build_turns(read_records(jsonl), allow_sidechain=True, index=index)
            for t in turns:
                parent.children.extend(t.actions)
                parent.agent_said.extend(t.response)
            parent.agent_type = meta.get("agentType")
            parent.agent_depth = meta.get("spawnDepth")
            attached += 1
            progressed = True
        pending = still
        if not progressed:
            # spawning call absent from the transcript (typically dropped by compaction)
            for meta, jsonl in pending:
                standalone.append(
                    AgentRun(
                        meta,
                        build_turns(
                            read_records(jsonl), allow_sidechain=True, index=index
                        ),
                        "orphan",
                    )
                )
            break

    return attached, standalone


# ----------------------------------------------------------------------- render

C = {
    "dim": "\033[2m",
    "b": "\033[1m",
    "cyan": "\033[36m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "red": "\033[31m",
    "mag": "\033[35m",
    "off": "\033[0m",
}


def paint(s: str, *keys: str, color: bool = True) -> str:
    if not color:
        return s
    return "".join(C[k] for k in keys) + s + C["off"]


def clip(s: str, n: int) -> str:
    s = (s or "").strip()
    if n <= 0 or len(s) <= n:
        return s
    return s[:n] + f" …(+{len(s) - n} chars)"


def indent_block(s: str, pad: str, limit: int, max_lines: int) -> Iterator[str]:
    s = clip(s, limit)
    lines = s.splitlines() or [""]
    if max_lines > 0 and len(lines) > max_lines:
        head = lines[:max_lines]
        head.append(f"…(+{len(lines) - max_lines} lines)")
        lines = head
    for ln in lines:
        yield pad + ln


def fmt_input(inp: dict, limit: int) -> str:
    if not inp:
        return ""
    for k in ("command", "prompt", "pattern", "query", "file_path", "path"):
        if k in inp and isinstance(inp[k], str):
            extra = [f"{k2}={v}" for k2, v in inp.items() if k2 != k and k2 != "description"]
            tail = "  " + " ".join(extra) if extra else ""
            return clip(inp[k], limit) + clip(tail, 120)
    return clip(json.dumps(inp, default=str), limit)


def render_action(
    act: Action, depth: int, args, color: bool, out: list[str]
) -> None:
    pad = "  " * depth
    if act.is_error:
        status = paint("ERR", "red", color=color)
    elif act.result is not None:
        status = paint("ok", "green", color=color)
    else:
        status = paint("…", "dim", color=color)
    tag = ""
    if act.agent_type:
        tag = paint(f"  <{act.agent_type}>", "mag", color=color)
    out.append(f"{pad}├─ {paint(act.tool, 'cyan', 'b', color=color)}  [{status}]{tag}")
    ip = fmt_input(act.input, args.in_limit)
    if ip:
        out.extend(indent_block(ip, pad + "│    ", args.in_limit, args.in_lines))
    if act.children and not args.no_subagents:
        n = len(act.children)
        out.append(
            f"{pad}│    {paint(f'└─ subagent · {n} action{"" if n == 1 else "s"}', 'mag', color=color)}"
        )
        for kid in act.children:
            render_action(kid, depth + 2, args, color, out)
    for said in act.agent_said:
        if not args.no_subagents:
            out.append(f"{pad}│    {paint('└─ subagent returned:', 'mag', color=color)}")
            out.extend(
                indent_block(said, pad + "│      ", args.out_limit, args.out_lines)
            )
    if act.result_text:
        out.append(f"{pad}│  {paint('→', 'dim', color=color)}")
        out.extend(
            indent_block(act.result_text, pad + "│    ", args.out_limit, args.out_lines)
        )


def render_runs(runs: list[AgentRun], args, color: bool) -> list[str]:
    out: list[str] = []
    for r in runs:
        note = "team agent" if r.reason == "teammate" else "spawning call not in transcript"
        out.append("")
        out.append(
            paint(f"━━ AGENT {r.label} ━━ ({note})", "b", "mag", color=color)
        )
        for t in r.turns:
            out.append(paint("PROMPT", "b", color=color))
            out.extend(indent_block(t.prompt, "  ", args.prompt_limit, 0))
            for kind, payload in t.stream:
                if kind == "action":
                    render_action(payload, 0, args, color, out)
                elif kind == "text":
                    out.append(paint("SAID", "b", "green", color=color))
                    out.extend(indent_block(payload, "  ", args.resp_limit, 0))
    return out


def render(turns: list[Turn], args, color: bool) -> str:
    out: list[str] = []
    for t in turns:
        dur = f"  {t.duration_ms/1000:.1f}s" if t.duration_ms else ""
        out.append("")
        out.append(
            paint(
                f"━━ TURN {t.index} ━━ {t.ts}{dur}  ({t.source})",
                "b",
                "yellow",
                color=color,
            )
        )
        out.append(paint("PROMPT", "b", color=color))
        out.extend(indent_block(t.prompt, "  ", args.prompt_limit, 0))
        if t.decorations and not args.no_decoration:
            out.append(paint("DECORATION", "b", "dim", color=color))
            for label, text in t.decorations:
                out.append(f"  + {paint(label, 'dim', color=color)}")
                out.extend(
                    indent_block(text, "      ", args.deco_limit, args.deco_lines)
                )
        for kind, payload in t.stream:
            if kind == "thinking":
                if not args.thinking:
                    continue
                if not payload.strip():
                    out.append(paint("THINKING  (not persisted)", "dim", color=color))
                    continue
                out.append(paint("THINKING", "b", "dim", color=color))
                out.extend(indent_block(payload, "  ", args.think_limit, args.think_lines))
            elif kind == "text":
                out.append(paint("SAID", "b", "green", color=color))
                out.extend(indent_block(payload, "  ", args.resp_limit, 0))
            elif kind == "action":
                if args.tool and payload.tool != args.tool:
                    continue
                render_action(payload, 0, args, color, out)
    return "\n".join(out)


HTML_CSS = """
:root { color-scheme: dark;
  --bg:#121417; --fg:#e6e6e6; --mut:#9aa0a6; --line:#33383d; --card:#1d2024;
  --tool:#6fb3f2; --ok:#5cc98a; --err:#ff8a80; --agent:#c99bf0; --prompt:#e0b25e;
  /* one background per nesting level; deeper = lighter, so branches separate visually */
  --l0:#15181c; --l1:#1d2229; --l2:#262c34; --l3:#2f363f;
  --l4:#38404b; --l5:#414a56; --l6:#4a5462; --l7:#535e6d; }
* { box-sizing:border-box; }
body { margin:0; padding:1rem 1.2rem 4rem; background:var(--bg); color:var(--fg);
  font:14px/1.5 ui-sans-serif,-apple-system,Segoe UI,Roboto,sans-serif; }
h1 { font-size:1.05rem; margin:0 0 .15rem; }
.sub { color:var(--mut); font-size:.82rem; margin-bottom:.9rem; word-break:break-all; }
.bar { position:sticky; top:0; z-index:5; background:var(--bg); padding:.5rem 0 .35rem;
  border-bottom:1px solid var(--line); margin-bottom:.8rem; }
.row { display:flex; gap:.4rem; flex-wrap:wrap; align-items:center; }
.toggles { display:flex; gap:.75rem; flex-wrap:wrap; padding:.4rem .1rem 0; font-size:.75rem; }
.toggles label { display:inline-flex; align-items:center; gap:.25rem; color:var(--mut);
  cursor:pointer; user-select:none; }
.toggles label:hover { color:var(--fg); }
.toggles input { margin:0; accent-color:var(--tool); }
button { font:inherit; font-size:.82rem; padding:.25rem .6rem; border:1px solid var(--line);
  background:var(--card); color:var(--fg); border-radius:5px; cursor:pointer; }
button:hover { border-color:var(--mut); }
#q { flex:1; min-width:11rem; font:inherit; font-size:.82rem; padding:.25rem .5rem;
  border:1px solid var(--line); border-radius:5px; background:var(--card); color:var(--fg); }
details { border-left:2px solid var(--line); margin:.18rem 0; padding:.1rem .35rem .1rem .55rem;
  border-radius:0 4px 4px 0; }
.l0{background:var(--l0)} .l1{background:var(--l1)} .l2{background:var(--l2)}
.l3{background:var(--l3)} .l4{background:var(--l4)} .l5{background:var(--l5)}
.l6{background:var(--l6)} .l7{background:var(--l7)}
summary { cursor:pointer; padding:.12rem 0; list-style:none; }
summary::-webkit-details-marker { display:none; }
summary::before { content:"\\25B8"; display:inline-block; width:.9em; color:var(--mut); }
details[open]>summary::before { content:"\\25BE"; }
.turn { border-left:3px solid var(--prompt); margin:.9rem 0; }
.turn>summary { font-weight:600; }
.tn { color:var(--prompt); }
.ts { color:var(--mut); font-weight:400; font-size:.8rem; }
.tool { color:var(--tool); font-weight:600; }
.badge { font-size:.72rem; padding:.02rem .3rem; border-radius:3px; border:1px solid var(--line); color:var(--mut); }
.ok { color:var(--ok); border-color:var(--ok); }
.err { color:var(--err); border-color:var(--err); }
.agent { color:var(--agent); border-color:var(--agent); }
.gist { color:var(--mut); font-size:.82rem; }
pre { margin:.25rem 0 .45rem; padding:.45rem .6rem; background:rgba(0,0,0,.32);
  border:1px solid var(--line); border-radius:5px; overflow-x:auto;
  font:12px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace; white-space:pre-wrap;
  word-break:break-word; max-height:26rem; }
pre.out { border-left:3px solid var(--ok); }
pre.bad { border-left:3px solid var(--err); }
.lbl { color:var(--mut); font-size:.75rem; text-transform:uppercase; letter-spacing:.05em; }
.said { border-left:3px solid var(--ok); padding-left:.55rem; margin:.3rem 0; }
.hide { display:none; }
"""

# (key, label) per toggleable node type; drives the CSS rules, the checkboxes and
# the class names on the nodes themselves, so the three can never drift apart.
TREE_NODES = [
    ("prompt", "prompt"),
    ("deco", "decoration"),
    ("think", "thinking"),
    ("said", "assistant text"),
    ("action", "tool calls"),
    ("input", "tool input"),
    ("output", "tool output"),
    ("subagent", "subagent branches"),
]

INDEX_NODES = [
    ("tools", "tool chips"),
    ("turns", "turn headlines"),
]


def node_css(nodes: list[tuple[str, str]]) -> str:
    return "".join(f"body.hide-{k} .n-{k}{{display:none}}" for k, _ in nodes)


def node_toolbar(nodes: list[tuple[str, str]], body: str) -> str:
    """Checkboxes for the node types this page actually contains.

    Types with no nodes (e.g. thinking, which transcripts do not persist) would be
    dead controls, so they are dropped rather than shown doing nothing.
    """
    boxes = "".join(
        f'<label><input type="checkbox" data-k="{k}" checked>{esc(lab)}</label>'
        for k, lab in nodes
        if f'"n-{k}' in body or f" n-{k}" in body
    )
    return f'<div class="toggles">{boxes}</div>' if boxes else ""


NODE_JS = """
document.querySelectorAll('.toggles input').forEach(cb => {
  cb.onchange = () => document.body.classList.toggle('hide-' + cb.dataset.k, !cb.checked);
});
"""

HTML_JS = """
function setAll(open) {
  document.querySelectorAll('details').forEach(d => { d.open = open; });
}
document.getElementById('xall').onclick = () => setAll(true);
document.getElementById('call').onclick = () => setAll(false);
const q = document.getElementById('q');
q.oninput = () => {
  const t = q.value.toLowerCase();
  document.querySelectorAll('details.turn').forEach(d => {
    const hit = !t || d.textContent.toLowerCase().includes(t);
    d.classList.toggle('hide', !hit);
    if (t && hit) d.open = true;
  });
};
"""


def esc(s: Any) -> str:
    return html_escape("" if s is None else str(s))


def h_pre(text: str, cls: str = "") -> str:
    return f'<pre class="{cls}">{esc(text)}</pre>' if text.strip() else ""


def lvl(depth: int) -> str:
    """Background class for a nesting depth; cycles past the deepest defined shade."""
    return f"l{depth % 8}"


def h_action(a: Action, depth: int = 1) -> str:
    if a.is_error:
        badge = '<span class="badge err">ERR</span>'
    elif a.result is not None:
        badge = '<span class="badge ok">ok</span>'
    else:
        badge = '<span class="badge">no result</span>'
    atag = f' <span class="badge agent">{esc(a.agent_type)}</span>' if a.agent_type else ""
    gist = esc(clip(fmt_input(a.input, 110), 110).replace("\n", " "))
    parts = [
        f'<details class="n-action {lvl(depth)}">'
        f'<summary><span class="tool">{esc(a.tool)}</span> '
        f'{badge}{atag} <span class="gist">{gist}</span></summary>'
    ]
    if a.input:
        parts.append(
            f'<div class="n-input"><div class="lbl">input</div>'
            f"{h_pre(json.dumps(a.input, indent=2, default=str))}</div>"
        )
    if a.result_text:
        parts.append(
            f'<div class="n-output"><div class="lbl">output</div>'
            f'{h_pre(a.result_text, "bad" if a.is_error else "out")}</div>'
        )
    if a.children:
        n = len(a.children)
        parts.append(
            f'<details open class="n-subagent {lvl(depth + 1)}">'
            f'<summary><span class="badge agent">subagent</span> '
            f'{n} action{"" if n == 1 else "s"}</summary>'
        )
        parts.extend(h_action(k, depth + 2) for k in a.children)
        parts.append("</details>")
    for said in a.agent_said:
        parts.append(
            f'<div class="n-subagent"><div class="lbl">subagent returned</div>'
            f'{h_pre(said, "out")}</div>'
        )
    parts.append("</details>")
    return "".join(parts)


def h_turn(t: Turn, args) -> str:
    n_act = sum(1 for _ in walk_actions(t.actions))
    dur = f" · {t.duration_ms/1000:.1f}s" if t.duration_ms else ""
    head = esc(clip(t.prompt.replace("\n", " "), 90))
    parts = [
        f'<details class="turn l0" open><summary><span class="tn">TURN {t.index}</span> '
        f'<span class="ts">{esc(t.ts)}{dur} · {n_act} action{"" if n_act == 1 else "s"}</span>'
        f'<div class="gist">{head}</div></summary>',
        f'<div class="n-prompt"><div class="lbl">prompt</div>{h_pre(t.prompt)}</div>',
    ]
    if t.decorations and not args.no_decoration:
        parts.append(
            f'<details class="n-deco {lvl(1)}"><summary><span class="lbl">decoration '
            f"({len(t.decorations)})</span></summary>"
        )
        for label, text in t.decorations:
            parts.append(
                f'<details class="{lvl(2)}"><summary>{esc(label)}</summary>'
                f"{h_pre(text)}</details>"
            )
        parts.append("</details>")
    for kind, payload in t.stream:
        if kind == "action":
            parts.append(h_action(payload))
        elif kind == "text":
            parts.append(f'<div class="said n-said">{h_pre(payload)}</div>')
        elif kind == "thinking" and args.thinking and payload.strip():
            parts.append(
                f'<details class="n-think {lvl(1)}">'
                f'<summary><span class="lbl">thinking</span>'
                f"</summary>{h_pre(payload)}</details>"
            )
    parts.append("</details>")
    return "".join(parts)


def render_html(turns: list[Turn], runs: list[AgentRun], path: Path, args) -> str:
    n_act = sum(1 for t in turns for _ in walk_actions(t.actions))
    body = [h_turn(t, args) for t in turns]
    for r in runs:
        note = "team agent" if r.reason == "teammate" else "spawning call not in transcript"
        body.append(
            f'<details class="turn l0"><summary><span class="badge agent">AGENT</span> '
            f'{esc(r.label)} <span class="ts">({note})</span></summary>'
        )
        for t in r.turns:
            body.append(
                f'<div class="n-prompt"><div class="lbl">prompt</div>'
                f"{h_pre(t.prompt)}</div>"
            )
            for kind, payload in t.stream:
                if kind == "action":
                    body.append(h_action(payload))
                elif kind == "text":
                    body.append(f'<div class="said n-said">{h_pre(payload)}</div>')
        body.append("</details>")

    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>cctree {esc(path.stem[:8])}</title>"
        f"<style>{HTML_CSS}{node_css(TREE_NODES)}</style></head><body>"
        f"<h1>{esc(session_cwd(path))}</h1>"
        f"<div class='sub'>session {esc(path.stem)} · {len(turns)} turns · "
        f"{n_act} actions · {len(runs)} standalone agents<br>{esc(path)}</div>"
        "<div class='bar'><div class='row'><button id='xall'>expand all</button>"
        "<button id='call'>collapse all</button>"
        "<input id='q' type='search' placeholder='filter turns…'></div>"
        + node_toolbar(TREE_NODES, "".join(body))
        + "</div>"
        + "".join(body)
        + f"<script>{HTML_JS}{NODE_JS}</script></body></html>"
    )


INDEX_CSS = """
.proj { border-left:3px solid var(--tool); margin:.7rem 0; }
.proj>summary { font-weight:600; font-size:.95rem; }
.sess { border-left:2px solid var(--line); margin:.25rem 0; }
.nums { color:var(--mut); font-weight:400; font-size:.8rem; }
a { color:var(--tool); }
a.open { font-size:.78rem; margin-left:.4rem; white-space:nowrap; }
table { border-collapse:collapse; width:100%; font-size:.82rem; margin:.2rem 0 .4rem; }
td { padding:.12rem .5rem .12rem 0; vertical-align:top; border-bottom:1px solid var(--line); }
td.n { color:var(--mut); white-space:nowrap; width:1%; text-align:right; font-variant-numeric:tabular-nums; }
.toolrow { font-size:.78rem; color:var(--mut); margin:.1rem 0 .35rem; }
.chip { display:inline-block; border:1px solid var(--line); border-radius:3px;
  padding:0 .3rem; margin:0 .25rem .2rem 0; }
"""


def render_html_index(
    rows: list[SessionStats], links: dict[str, str], title: str
) -> str:
    groups: dict[str, list[SessionStats]] = {}
    for st in rows:
        groups.setdefault(st.cwd, []).append(st)

    body: list[str] = []
    g_turns = g_acts = g_err = g_ag = 0
    for cwd, g in sorted(groups.items(), key=lambda kv: -max(s.mtime for s in kv[1])):
        g = sorted(g, key=lambda s: -s.mtime)
        t = sum(s.turns for s in g)
        a = sum(s.actions for s in g)
        e = sum(s.errors for s in g)
        ag = sum(s.subagents + s.teammates for s in g)
        g_turns += t
        g_acts += a
        g_err += e
        g_ag += ag
        tools: dict[str, int] = {}
        for s in g:
            for k, v in s.tools.items():
                tools[k] = tools.get(k, 0) + v
        chips = "".join(
            f'<span class="chip">{esc(k)} {v}</span>'
            for k, v in sorted(tools.items(), key=lambda kv: -kv[1])[:10]
        )
        body.append(
            f'<details class="proj l0"><summary>{esc(cwd)} '
            f'<span class="nums">· {len(g)} sessions · {t} turns · {a} actions · '
            f"{e} errors · {ag} agents</span></summary>"
            f'<div class="toolrow n-tools">{chips}</div>'
        )
        for s in g:
            link = links.get(s.path.stem)
            open_a = f'<a class="open" href="{esc(link)}">open tree →</a>' if link else ""
            body.append(
                f'<details class="sess l1"><summary>{esc(s.when)} '
                f'<span class="nums">{s.turns} turns · {s.actions} actions · '
                f"{s.errors} err · {s.subagents + s.teammates} agents · "
                f'{esc(s.path.stem[:8])}</span>{open_a}</summary><table class="n-turns">'
            )
            for idx, ts, gist, n in s.gists:
                body.append(
                    f'<tr><td class="n">{idx}</td><td class="n">{esc(ts[:16])}</td>'
                    f'<td class="n">{n}a</td><td>{esc(gist)}</td></tr>'
                )
            if not s.gists:
                body.append('<tr><td colspan="4" class="nums">no turns</td></tr>')
            body.append("</table></details>")
        body.append("</details>")

    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{esc(title)}</title>"
        f"<style>{HTML_CSS}{INDEX_CSS}{node_css(INDEX_NODES)}</style></head><body>"
        f"<h1>{esc(title)}</h1>"
        f"<div class='sub'>{len(groups)} projects · {len(rows)} sessions · {g_turns} turns · "
        f"{g_acts} actions · {g_err} errors · {g_ag} agents</div>"
        "<div class='bar'><div class='row'><button id='xall'>expand all</button>"
        "<button id='call'>collapse all</button>"
        "<input id='q' type='search' placeholder='filter projects…'></div>"
        + node_toolbar(INDEX_NODES, "".join(body))
        + "</div>"
        + "".join(body)
        + f"<script>{HTML_JS.replace('details.turn', 'details.proj')}{NODE_JS}</script>"
        "</body></html>"
    )


def action_json(a: Action) -> dict:
    return {
        "tool": a.tool,
        "tool_id": a.tool_id,
        "ts": a.ts,
        "input": a.input,
        "is_error": a.is_error,
        "result_text": a.result_text,
        "result": a.result,
        "agent_type": a.agent_type,
        "agent_depth": a.agent_depth,
        "agent_said": a.agent_said,
        "children": [action_json(k) for k in a.children],
    }


def to_json(turns: list[Turn], path: Path, runs: list[AgentRun] | None = None) -> str:
    return json.dumps(
        {
            "session": path.stem,
            "path": str(path),
            "standalone_agents": [
                {
                    "label": r.label,
                    "reason": r.reason,
                    "meta": r.meta,
                    "actions": [action_json(a) for t in r.turns for a in t.actions],
                    "said": [x for t in r.turns for x in t.response],
                }
                for r in (runs or [])
            ],
            "turns": [
                {
                    "index": i,
                    "ts": t.ts,
                    "prompt_id": t.prompt_id,
                    "source": t.source,
                    "duration_ms": t.duration_ms,
                    "prompt": t.prompt,
                    "decorations": [{"label": l, "text": x} for l, x in t.decorations],
                    "stream": [
                        {"kind": k, "action": action_json(p)}
                        if k == "action"
                        else {"kind": k, "text": p}
                        for k, p in t.stream
                    ],
                }
                for i, t in enumerate(turns, 1)
            ],
        },
        indent=2,
        default=str,
    )


# ------------------------------------------------------------------------- main


def parse_session(path: Path, expand_subagents: bool = True):
    """Parse one session into (turns, standalone agent runs)."""
    idx: dict[str, Action] = {}
    turns = build_turns(read_records(path), index=idx)
    runs: list[AgentRun] = []
    if expand_subagents:
        _, runs = graft_subagents(path, idx)
    return turns, runs


def count_actions(acts: list[Action], hist: dict[str, int]) -> tuple[int, int]:
    """Return (total actions incl. nested, errors), filling a tool histogram."""
    total = errors = 0
    for a in acts:
        total += 1
        hist[a.tool] = hist.get(a.tool, 0) + 1
        if a.is_error:
            errors += 1
        sub_t, sub_e = count_actions(a.children, hist)
        total += sub_t
        errors += sub_e
    return total, errors


@dataclass
class SessionStats:
    path: Path
    cwd: str
    mtime: float
    turns: int = 0
    actions: int = 0
    errors: int = 0
    subagents: int = 0
    teammates: int = 0
    tools: dict[str, int] = field(default_factory=dict)
    # (turn index, timestamp, prompt gist, action count) — headlines for the index page
    gists: list[tuple[int, str, str, int]] = field(default_factory=list)

    @property
    def when(self) -> str:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(self.mtime))


def stat_session(path: Path) -> SessionStats:
    turns, runs = parse_session(path)
    st = SessionStats(path=path, cwd=session_cwd(path), mtime=path.stat().st_mtime)
    st.turns = len(turns)
    for t in turns:
        st.gists.append(
            (
                t.index,
                t.ts,
                clip(t.prompt.replace("\n", " "), 160),
                sum(1 for _ in walk_actions(t.actions)),
            )
        )
    acts = [a for t in turns for a in t.actions]
    st.actions, st.errors = count_actions(acts, st.tools)
    for r in runs:
        ra = [a for t in r.turns for a in t.actions]
        n, e = count_actions(ra, st.tools)
        st.actions += n
        st.errors += e
        acts.extend(ra)  # teammates can spawn agents too; count those below
        if r.reason == "teammate":
            st.teammates += 1
        else:
            st.subagents += 1

    st.subagents += sum(1 for a in walk_actions(acts) if a.agent_type)
    return st


def walk_actions(acts: list[Action]):
    for a in acts:
        yield a
        yield from walk_actions(a.children)


def render_summary(rows: list[SessionStats], by_project: bool, color: bool, top: int) -> str:
    out: list[str] = []
    groups: dict[str, list[SessionStats]] = {}
    for st in rows:
        groups.setdefault(st.cwd if by_project else "ALL", []).append(st)

    hdr = f"{'when':16} {'turns':>6} {'actions':>8} {'err':>5} {'agents':>7}  session"
    grand = SessionStats(Path("."), "", 0.0)
    for key in sorted(groups, key=lambda k: -max(s.mtime for s in groups[k])):
        g = sorted(groups[key], key=lambda s: -s.mtime)
        t = sum(s.turns for s in g)
        a = sum(s.actions for s in g)
        e = sum(s.errors for s in g)
        ag = sum(s.subagents + s.teammates for s in g)
        grand.turns += t
        grand.actions += a
        grand.errors += e
        grand.subagents += ag
        out.append("")
        out.append(paint(f"▌ {key}", "b", "cyan", color=color))
        out.append(
            paint(
                f"  {len(g)} sessions · {t} turns · {a} actions · {e} errors · {ag} agents",
                "dim",
                color=color,
            )
        )
        if top:
            out.append(paint("  " + hdr, "dim", color=color))
            for s in g[:top]:
                out.append(
                    f"  {s.when:16} {s.turns:>6} {s.actions:>8} {s.errors:>5} "
                    f"{s.subagents + s.teammates:>7}  {s.path.stem[:8]}"
                )
            if len(g) > top:
                out.append(paint(f"  …(+{len(g) - top} more sessions)", "dim", color=color))
    out.append("")
    out.append(
        paint(
            f"TOTAL  {len(rows)} sessions · {grand.turns} turns · {grand.actions} actions "
            f"· {grand.errors} errors · {grand.subagents} agents",
            "b",
            color=color,
        )
    )
    return "\n".join(out)


def summary_json(rows: list[SessionStats]) -> str:
    groups: dict[str, list[SessionStats]] = {}
    for st in rows:
        groups.setdefault(st.cwd, []).append(st)
    return json.dumps(
        {
            "projects": [
                {
                    "cwd": cwd,
                    "sessions": len(g),
                    "turns": sum(s.turns for s in g),
                    "actions": sum(s.actions for s in g),
                    "errors": sum(s.errors for s in g),
                    "subagents": sum(s.subagents for s in g),
                    "teammates": sum(s.teammates for s in g),
                    "tools": dict(
                        sorted(
                            {
                                k: sum(s.tools.get(k, 0) for s in g)
                                for k in {k for s in g for k in s.tools}
                            }.items(),
                            key=lambda kv: -kv[1],
                        )
                    ),
                    "sessions_detail": [
                        {
                            "session": s.path.stem,
                            "when": s.when,
                            "turns": s.turns,
                            "actions": s.actions,
                            "errors": s.errors,
                        }
                        for s in sorted(g, key=lambda s: -s.mtime)
                    ],
                }
                for cwd, g in sorted(
                    groups.items(), key=lambda kv: -max(s.mtime for s in kv[1])
                )
            ]
        },
        indent=2,
    )


def resolve_path(args) -> Path:
    if args.file:
        return Path(args.file).expanduser()
    if args.session:
        p = find_session(args.session)
        if not p:
            sys.exit(f"cctree: no session matching {args.session!r} under {PROJECTS}")
        return p
    base = Path(args.project).expanduser() if args.project else Path.cwd()
    d = project_dir(base)
    if not d:
        sys.exit(f"cctree: no transcripts for {base} (looked for {PROJECTS / slug_for(base)})")
    ss = sessions_in(d)
    if not ss:
        sys.exit(f"cctree: no sessions in {d}")
    return ss[0]


def build_parser() -> argparse.ArgumentParser:
    """The CLI parser, factored out so non-CLI callers (the hub) can get a
    fully-populated options namespace from `render_args()` instead of
    hand-rolling one — a hand-rolled namespace silently goes missing an
    attribute the moment a new flag is added, and the renderer raises.
    """
    ap = argparse.ArgumentParser(description="prompt -> action tree for Claude Code sessions")
    ap.add_argument("file", nargs="?", help="session .jsonl (default: latest for cwd's project)")
    ap.add_argument("--session", help="session id (prefix ok), searched across projects")
    ap.add_argument("--project", help="project working dir to pick the latest session from")
    ap.add_argument("--list", action="store_true", help="list sessions and exit")
    ap.add_argument("--projects", action="store_true", help="list every known project and exit")
    ap.add_argument(
        "--summary",
        action="store_true",
        help="counts per project instead of the tree (pair with --all-projects)",
    )
    ap.add_argument(
        "--all-projects", action="store_true", help="operate across every project"
    )
    ap.add_argument(
        "--all-sessions",
        action="store_true",
        help="every session in the project, not just the latest",
    )
    ap.add_argument("--top", type=int, default=5, help="sessions listed per project in --summary (0 = none)")
    ap.add_argument("--json", action="store_true", help="emit structured JSON")
    ap.add_argument(
        "--html",
        nargs="?",
        const="-",
        metavar="OUT",
        help="write a collapsible self-contained HTML tree (default: alongside cwd)",
    )
    ap.add_argument("--open", action="store_true", help="open the written HTML file")
    ap.add_argument(
        "--html-site",
        metavar="DIR",
        help="rollup: index.html (project -> session -> turn) plus a linked page per session",
    )
    ap.add_argument(
        "--index-only",
        action="store_true",
        help="with --html-site, skip the per-session pages",
    )
    ap.add_argument("--follow", "-f", action="store_true", help="tail a live session")
    ap.add_argument("--full", action="store_true", help="no truncation anywhere")
    ap.add_argument(
        "--no-thinking",
        dest="thinking",
        action="store_false",
        help="hide thinking blocks (shown by default)",
    )
    ap.add_argument("--no-decoration", action="store_true", help="hide hook/skill injections")
    ap.add_argument("--no-subagents", action="store_true", help="do not expand subagent branches")
    ap.add_argument("--turn", type=int, help="render only this turn number")
    ap.add_argument("--tool", help="only show actions for this tool name")
    ap.add_argument("--prompt-limit", type=int, default=0)
    ap.add_argument("--deco-limit", type=int, default=400)
    ap.add_argument("--deco-lines", type=int, default=6)
    ap.add_argument("--in-limit", type=int, default=400)
    ap.add_argument("--in-lines", type=int, default=8)
    ap.add_argument("--out-limit", type=int, default=600)
    ap.add_argument("--out-lines", type=int, default=10)
    ap.add_argument("--resp-limit", type=int, default=0)
    ap.add_argument("--think-limit", type=int, default=800)
    ap.add_argument("--think-lines", type=int, default=12)
    return ap


def render_args(**overrides):
    """Default options with `overrides` applied. Used by the web server."""
    args = build_parser().parse_args([])
    for k, v in overrides.items():
        setattr(args, k, v)
    return args


def main() -> None:
    ap = build_parser()
    args = ap.parse_args()

    if args.full:
        for k in ("prompt_limit", "deco_limit", "in_limit", "out_limit", "resp_limit", "think_limit"):
            setattr(args, k, 0)
        for k in ("deco_lines", "in_lines", "out_lines", "think_lines"):
            setattr(args, k, 0)

    color = (
        sys.stdout.isatty()
        and not args.json
        and not args.html
        and not args.html_site
        and os.environ.get("NO_COLOR") is None
    )

    def scoped_sessions() -> list[Path]:
        if args.all_projects:
            return [p for d in all_projects() for p in sessions_in(d)]
        base = Path(args.project).expanduser() if args.project else Path.cwd()
        d = project_dir(base)
        if not d:
            sys.exit(f"cctree: no transcripts for {base}")
        return sessions_in(d)

    if args.html_site:
        out_dir = Path(args.html_site).expanduser()
        out_dir.mkdir(parents=True, exist_ok=True)
        paths = scoped_sessions()
        rows: list[SessionStats] = []
        links: dict[str, str] = {}
        bytes_out = 0
        for i, p in enumerate(paths, 1):
            rows.append(stat_session(p))
            if args.index_only:
                continue
            turns, runs = parse_session(p, expand_subagents=not args.no_subagents)
            name = f"s-{p.stem}.html"
            doc = render_html(turns, runs, p, args)
            (out_dir / name).write_text(doc, encoding="utf-8")
            links[p.stem] = name
            bytes_out += len(doc)
            print(f"  [{i}/{len(paths)}] {name}  ({len(doc)/1024:.0f}K)", file=sys.stderr)
        title = "Claude Code sessions" if args.all_projects else session_cwd(paths[0])
        idx = render_html_index(rows, links, title)
        (out_dir / "index.html").write_text(idx, encoding="utf-8")
        print(
            f"wrote {out_dir}/index.html  ({len(idx)/1024:.0f}K)  "
            f"{len(rows)} sessions, {len(links)} tree pages, {bytes_out/1048576:.1f}MB total"
        )
        if args.open:
            opener = {"darwin": "open", "win32": "start"}.get(sys.platform, "xdg-open")
            subprocess.run([opener, str(out_dir / "index.html")], check=False)
        return

    if args.html:
        path = resolve_path(args)
        turns, runs = parse_session(path, expand_subagents=not args.no_subagents)
        if args.turn:
            turns = [t for t in turns if t.index == args.turn]
        doc = render_html(turns, runs, path, args)
        out = Path(args.html).expanduser() if args.html != "-" else Path(f"cctree-{path.stem[:8]}.html")
        out.write_text(doc, encoding="utf-8")
        print(f"wrote {out}  ({len(doc)/1024:.0f}K, {len(turns)} turns)")
        if args.open:
            opener = {"darwin": "open", "win32": "start"}.get(sys.platform, "xdg-open")
            subprocess.run([opener, str(out)], check=False)
        return

    if args.projects:
        proj_rows: list[tuple[float, str, int]] = []
        for d in all_projects():
            ss = sessions_in(d)
            proj_rows.append(
                (max(p.stat().st_mtime for p in ss), session_cwd(ss[0]), len(ss))
            )
        for mt, cwd, n in sorted(proj_rows, reverse=True):
            print(f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(mt))}  {n:>3} sessions  {cwd}")
        return

    if args.list:
        dirs = all_projects() if args.all_projects else None
        if dirs is None:
            base = Path(args.project).expanduser() if args.project else Path.cwd()
            d = project_dir(base)
            if not d:
                sys.exit(f"cctree: no transcripts for {base}")
            dirs = [d]
        for d in dirs:
            if args.all_projects:
                print(paint(f"▌ {session_cwd(sessions_in(d)[0])}", "b", "cyan", color=color))
            for p in sessions_in(d):
                mt = time.strftime("%Y-%m-%d %H:%M", time.localtime(p.stat().st_mtime))
                print(f"{mt}  {p.stat().st_size/1024:8.1f}K  {p.stem}")
        return

    if args.summary:
        if args.all_projects:
            paths = [p for d in all_projects() for p in sessions_in(d)]
        else:
            base = Path(args.project).expanduser() if args.project else Path.cwd()
            d = project_dir(base)
            if not d:
                sys.exit(f"cctree: no transcripts for {base}")
            paths = sessions_in(d)
        rows = [stat_session(p) for p in paths]
        print(summary_json(rows) if args.json else render_summary(rows, True, color, args.top))
        return

    if args.all_sessions or args.all_projects:
        if args.all_projects:
            paths = [p for d in all_projects() for p in sessions_in(d)]
        else:
            base = Path(args.project).expanduser() if args.project else Path.cwd()
            d = project_dir(base)
            if not d:
                sys.exit(f"cctree: no transcripts for {base}")
            paths = sessions_in(d)
        for p in sorted(paths, key=lambda p: p.stat().st_mtime):
            turns, runs = parse_session(p, expand_subagents=not args.no_subagents)
            print(paint(f"\n▌ {session_cwd(p)}  ·  session {p.stem}", "b", "cyan", color=color))
            print(render(turns, args, color))
            if runs:
                print("\n".join(render_runs(runs, args, color)))
        return

    path = resolve_path(args)

    def emit(seen: int = 0) -> int:
        records = read_records(path)
        idx: dict[str, Action] = {}
        turns = build_turns(records, index=idx)
        runs: list[AgentRun] = []
        if not args.no_subagents:
            _, runs = graft_subagents(path, idx)
        if args.turn:
            turns = [t for t in turns if t.index == args.turn]
        if args.tool:
            turns = [t for t in turns if any(a.tool == args.tool for a in t.actions)]
        if args.json:
            print(to_json(turns, path, runs))
            return len(records)
        text = render(turns, args, color)
        if not args.turn and not args.tool and runs:
            text += "\n" + "\n".join(render_runs(runs, args, color))
        if seen == 0:
            print(paint(f"session {path.stem}  ({path})", "dim", color=color))
        print(text)
        return len(records)

    if not args.follow:
        emit()
        return

    seen = 0
    try:
        while True:
            n = len(read_records(path))
            if n != seen:
                sys.stdout.write("\033[2J\033[H" if color else "")
                emit(seen)
                seen = n
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
