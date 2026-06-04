"""Claude Code session JSONL → GMD session-card pipeline.

Phase A of the session-index plan (ISSUE-session-index.md). This module is the
parse + filter + card-writer half. CLI surface, daemon ops, and partition
routing land in later phases.

The card model:
- One GMD doc per session, hashed by raw JSONL bytes for re-ingest detection.
- User prompts + assistant text only. Tool I/O bodies dropped (tool names +
  file paths kept as symbolic metadata).
- Per-project on-disk location chosen by the caller.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

MAX_PROMPT_LEN = 600
MAX_DECISION_LEN = 1200
TITLE_LEN = 80

_COMMIT_SHA_RE = re.compile(r"\b[0-9a-f]{7,12}\b")
_FILE_TOOLS = {"Edit", "Write", "Read", "NotebookEdit"}


@dataclass
class SessionData:
    session_id: str
    source_path: Path
    project_slug: str
    started: str
    ended: str
    turn_count: int
    user_prompt_count: int
    branch: Optional[str]
    commits: list[str]
    files_touched: list[str]
    models_used: list[str]
    tool_counts: Counter
    ai_title: Optional[str]
    user_prompts: list[str]
    assistant_decisions: list[str]
    content_hash: str


def _resolve_project_slug(cwd: Optional[str], parent_dir_name: str) -> str:
    """Prefer cwd seen in a JSONL turn; fall back to decoding the parent dir."""
    if cwd:
        return cwd.lstrip("/")
    return parent_dir_name.lstrip("-").replace("-", "/")


def _extract_text(content) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for b in content:
        if isinstance(b, dict) and b.get("type") == "text":
            t = b.get("text") or ""
            if t:
                parts.append(t)
    return "\n".join(parts)


def _truncate(s: str, n: int) -> str:
    s = (s or "").strip()
    if len(s) <= n:
        return s
    return s[:n].rstrip() + "…"


def _dedup_consecutive(items: list[str]) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(items):
        j = i
        while j + 1 < len(items) and items[j + 1] == items[i]:
            j += 1
        run = j - i + 1
        out.append(items[i] if run == 1 else f"{items[i]} (×{run})")
        i = j + 1
    return out


def _is_tool_result_turn(content) -> bool:
    if not isinstance(content, list):
        return False
    return any(
        isinstance(b, dict) and b.get("type") == "tool_result" for b in content
    )


def _is_boilerplate_prompt(text: str) -> bool:
    """Drop system-injected user turns that aren't real prompts."""
    if text.startswith("<system-reminder>") and text.endswith("</system-reminder>"):
        return True
    if text.startswith("<command-name>") or text.startswith("<local-command"):
        return True
    return False


def parse_session_jsonl(path: Path) -> SessionData:
    raw_bytes = path.read_bytes()
    content_hash = hashlib.sha256(raw_bytes).hexdigest()

    session_id = path.stem
    started = ""
    ended = ""
    branch: Optional[str] = None
    cwd_seen: Optional[str] = None
    user_prompts: list[str] = []
    assistant_decisions: list[str] = []
    tool_counts: Counter = Counter()
    files_touched: list[str] = []
    commits_seen: set[str] = set()
    models: set[str] = set()
    ai_title: Optional[str] = None
    turn_count = 0
    user_prompt_count = 0

    for ln in raw_bytes.splitlines():
        if not ln.strip():
            continue
        try:
            d = json.loads(ln)
        except json.JSONDecodeError:
            continue

        ttype = d.get("type")
        ts = d.get("timestamp")
        if ts:
            if not started:
                started = ts
            ended = ts
        if not branch and d.get("gitBranch"):
            branch = d["gitBranch"]
        if not cwd_seen and d.get("cwd"):
            cwd_seen = d["cwd"]

        if ttype == "ai-title":
            ai_title = d.get("aiTitle") or ai_title
            continue

        if ttype == "user":
            turn_count += 1
            msg = d.get("message") or {}
            content = msg.get("content")
            if _is_tool_result_turn(content):
                continue
            text = _extract_text(content).strip()
            if not text or _is_boilerplate_prompt(text):
                continue
            user_prompts.append(_truncate(text, MAX_PROMPT_LEN))
            user_prompt_count += 1
            continue

        if ttype == "assistant":
            turn_count += 1
            msg = d.get("message") or {}
            if msg.get("model"):
                models.add(msg["model"])
            content = msg.get("content") or []
            text_parts: list[str] = []
            for b in content:
                if not isinstance(b, dict):
                    continue
                btype = b.get("type")
                if btype == "text":
                    t = (b.get("text") or "").strip()
                    if t:
                        text_parts.append(t)
                elif btype == "tool_use":
                    name = b.get("name") or "?"
                    tool_counts[name] += 1
                    inp = b.get("input") or {}
                    if name in _FILE_TOOLS:
                        fp = inp.get("file_path")
                        if fp and fp not in files_touched:
                            files_touched.append(fp)
            if text_parts:
                joined = "\n".join(text_parts).strip()
                for m in _COMMIT_SHA_RE.findall(joined):
                    commits_seen.add(m)
                assistant_decisions.append(_truncate(joined, MAX_DECISION_LEN))
            continue

    project_slug = _resolve_project_slug(cwd_seen, path.parent.name)
    user_prompts = _dedup_consecutive(user_prompts)
    assistant_decisions = _dedup_consecutive(assistant_decisions)

    return SessionData(
        session_id=session_id,
        source_path=path.resolve(),
        project_slug=project_slug,
        started=started,
        ended=ended,
        turn_count=turn_count,
        user_prompt_count=user_prompt_count,
        branch=branch,
        commits=sorted(commits_seen),
        files_touched=files_touched,
        models_used=sorted(models),
        tool_counts=tool_counts,
        ai_title=ai_title,
        user_prompts=user_prompts,
        assistant_decisions=assistant_decisions,
        content_hash=content_hash,
    )


def _yaml_list(items: list[str]) -> str:
    if not items:
        return "[]"
    quoted = ", ".join(f'"{i}"' for i in items)
    return f"[{quoted}]"


def build_card(data: SessionData) -> str:
    title = (
        data.ai_title
        or (data.user_prompts[0] if data.user_prompts else f"session {data.session_id[:8]}")
    )
    title = _truncate(title.replace("\n", " "), TITLE_LEN).replace('"', "'")
    project_tag = data.project_slug.replace("/", "-")
    tool_summary = ", ".join(f"{k}:{v}" for k, v in data.tool_counts.most_common())

    lines: list[str] = [
        "---",
        'gmd: "0.1"',
        f"id: session-{data.session_id[:8]}",
        f'title: "{title}"',
        f"tags: [session, {project_tag}]",
        "metadata:",
        "  node_type: session",
        "  type: session",
        f"  session_id: {data.session_id}",
        f"  project: {data.project_slug}",
        f"  jsonl_path: {data.source_path}",
        f"  started: {data.started}",
        f"  ended: {data.ended}",
        f"  turn_count: {data.turn_count}",
        f"  user_prompt_count: {data.user_prompt_count}",
        f"  branch: {data.branch or 'null'}",
        f"  commits: {_yaml_list(data.commits)}",
        f"  files_touched: {_yaml_list(data.files_touched)}",
        f"  models_used: {_yaml_list(data.models_used)}",
        f"  content_hash: {data.content_hash}",
        "---",
        "",
        f"# {title} {{#root}}",
        "",
        "## User prompts {#prompts}",
        "",
    ]
    for p in data.user_prompts:
        lines.append(f"- {p}")
    lines.append("")
    lines.append("## Assistant decisions {#decisions}")
    lines.append("")
    for d in data.assistant_decisions:
        lines.append(d)
        lines.append("")
    lines.append("## Activity {#activity}")
    lines.append("")
    lines.append(f"- Branch: {data.branch or 'unknown'}")
    if data.commits:
        lines.append(f"- Commits: {', '.join(data.commits)}")
    if data.files_touched:
        lines.append(f"- Files: {', '.join(data.files_touched)}")
    if tool_summary:
        lines.append(f"- Tools: {tool_summary}")
    if data.models_used:
        lines.append(f"- Models: {', '.join(data.models_used)}")
    return "\n".join(lines) + "\n"


def write_card(card_md: str, dest_dir: Path, session_id: str) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / f"{session_id}.md"
    out.write_text(card_md)
    return out


def ingest_session(jsonl_path: Path, dest_dir: Path) -> tuple[Path, SessionData]:
    data = parse_session_jsonl(jsonl_path)
    card = build_card(data)
    out = write_card(card, dest_dir, data.session_id)
    return out, data
