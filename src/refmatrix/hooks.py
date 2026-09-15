"""
Hook installer. Two surfaces:

- git hooks (post-commit, post-merge, post-checkout, post-rewrite) that fire
  `rmx sync --since <ref>` after history-changing operations.
- Claude Code hook config: a JSON block adding PostToolUse enqueue and Stop
  flush. Written to `.claude/settings.json` for project scope, or
  printed for the user to merge into `~/.claude/settings.json`.

Default mode is dry-run. Pass `apply=True` to actually write. Refuses to
overwrite an existing file unless `force=True`.

The git hook scripts are intentionally minimal: they just `cd` to the project
root and shell out to `rmx`. They background the call so commits stay snappy.
"""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path

# Prefix for every Claude-hook command so cli.log tags the invocation form as
# `hook` (telemetry "by form" axis). Exported so it reaches every rmx in a
# compound command.
HOOK_ENV = "export RMX_INVOCATION_SOURCE=hook; "

GIT_HOOK_SCRIPTS: dict[str, str] = {
    "post-commit": r"""#!/usr/bin/env bash
# refmatrix: refresh after each commit
set -e
ROOT="$(git rev-parse --show-toplevel)"
[ -d "$ROOT/.refmatrix" ] || exit 0
( cd "$ROOT" && rmx sync --since HEAD~1 >/dev/null 2>&1 || true ) &
disown
""",
    "post-merge": r"""#!/usr/bin/env bash
# refmatrix: refresh after merge
set -e
ROOT="$(git rev-parse --show-toplevel)"
[ -d "$ROOT/.refmatrix" ] || exit 0
( cd "$ROOT" && rmx sync --since ORIG_HEAD >/dev/null 2>&1 || true ) &
disown
""",
    "post-checkout": r"""#!/usr/bin/env bash
# refmatrix: refresh after checkout (only branch switches, $3==1)
set -e
[ "$3" = "1" ] || exit 0
ROOT="$(git rev-parse --show-toplevel)"
[ -d "$ROOT/.refmatrix" ] || exit 0
( cd "$ROOT" && rmx sync --since "$1..$2" >/dev/null 2>&1 || true ) &
disown
""",
    "post-rewrite": r"""#!/usr/bin/env bash
# refmatrix: refresh after rebase/amend
set -e
ROOT="$(git rev-parse --show-toplevel)"
[ -d "$ROOT/.refmatrix" ] || exit 0
# Read rewritten oid pairs from stdin; sync from the oldest old-oid.
OLD=$(awk '{print $1; exit}')
[ -z "$OLD" ] && exit 0
( cd "$ROOT" && rmx sync --since "$OLD" >/dev/null 2>&1 || true ) &
disown
""",
}


def _claude_hook_block(refmatrix_root: Path, primer: bool = True,
                       scan_prompt: bool = True,
                       memory_hooks: bool = True, *,
                       composite_every: "int | None" = 3,
                       precompact_checkpoint: bool = True,
                       stop_promote: bool = True,
                       resume_focus: "int | None" = 15,
                       enforce: "bool | None" = None,
                       project_root: "Path | None" = None) -> dict:
    """The ONE generator of a project's rmx hook config (Claude Code
    `.claude/settings.json`).

    Every hook a project runs comes from here — `rmx install-hooks --check`
    diffs the installed file against this render, so a hook that exists only
    in a settings file is a template bug (2026-09-14: four hand-authored hooks
    lived in one project's settings.local.json; a forced reinstall would have
    deleted them, and the only unattended save-state swallowed the memory
    bridge failure the code was built to shout).

    Options (recorded in `.claude/rmx-hooks.json` on apply so --check can
    re-render identically):
      composite_every       scan-prompt `--composite-every N` (None = off)
      precompact_checkpoint PreCompact `rmx save-state --no-promote --no-sync`
      stop_promote          Stop runs `rmx focus summarize --promote`
      resume_focus          SessionStart(resume) `rmx focus context --top N`
      enforce               emit the cat-herder enforcement hooks
                            (enforce-test-to-file, enforce-rmx-grep, adr-gate,
                            p20-0 guardrail compile); None = auto, i.e. each
                            entry only when its script exists under
                            `<project_root>/.claude/hooks` or `.claude/p20-0`.

    Loudness contract: every command on a memory path (memory recall,
    ingest-gmd, save-state, focus summarize) runs in the foreground with no
    `2>/dev/null` and no `|| true`. Plumbing (sync flush, primer, focus
    events, curator status) may stay quiet.

    Uses python -c instead of jq so the hook works on a fresh box without
    extra deps.
    """
    # PostToolUse: read tool_input JSON from stdin, extract file_path(s),
    # enqueue them. Single-line python so it stays one shell command.
    enqueue_py = (
        "import json,sys,subprocess;"
        "d=json.load(sys.stdin);"
        "ti=d.get('tool_input') or {};"
        "paths=set();"
        "fp=ti.get('file_path');"
        "paths.add(fp) if isinstance(fp,str) else None;"
        "[paths.add(e.get('file_path')) for e in (ti.get('edits') or []) "
        "if isinstance(e,dict) and isinstance(e.get('file_path'),str)];"
        "[subprocess.run(['rmx','sync','--enqueue-only','-f',p],check=False) "
        "for p in paths if p]"
    )
    # Run enqueue in a backgrounded subshell so the PostToolUse hook never
    # blocks the agent's next tool call. The queue write is fast (text-file
    # append, no DuckDB lock), but a slow Python startup can still chew
    # 50-100ms per Edit/Write; multiplied by burst hooks it adds up.
    enqueue_cmd = (
        HOOK_ENV
        + f"( python3 -c \"{enqueue_py}\" 2>/dev/null || true ) & disown"
    )
    # PostToolUse focus capture: record the tool + touched paths into the
    # per-project short-term focus graph. Cheap (file append); best-effort.
    focus_tool_cmd = (
        HOOK_ENV + "rmx focus hook --event tool 2>/dev/null || true"
    )
    # PreToolUse focus capture: park the call BEFORE it runs. PostToolUse only
    # fires for calls that complete, so a tool that hangs, is denied, or takes
    # the session down leaves no trace — exactly the moment a post-mortem
    # wants. The parked entry is cleared by the matching PostToolUse; whatever
    # is still parked at the next prompt gets folded into the ring as an
    # `abandoned` event.
    focus_tool_pre_cmd = (
        HOOK_ENV + "rmx focus hook --event tool-pre 2>/dev/null || true"
    )
    # UserPromptSubmit focus capture: record the prompt as an input event
    # (opens a new STM turn + admits prompt symbols).
    focus_input_cmd = (
        HOOK_ENV + "rmx focus hook --event input 2>/dev/null || true"
    )
    # Stop focus capture: record my last assistant message (read from the
    # transcript the Stop envelope points at) so STM holds the full dialogue,
    # not just the user's half — a bare "yes" stays legible against what I
    # had just proposed. Best-effort; never blocks the turn.
    focus_say_cmd = (
        HOOK_ENV + "rmx focus hook --event say 2>/dev/null || true"
    )

    # --async hands the actual sync work to the daemon and returns
    # immediately. With no daemon up, the flag is a silent no-op so the
    # hook stays cheap.
    flush_cmd = (
        HOOK_ENV
        + "( rmx sync --flush-queue --async >/dev/null 2>&1 || true ) & disown"
    )

    # SessionStart: flush + (optionally) regenerate primer in the
    # background, then EMIT (synchronously, foreground) the curator-queue
    # status so any pending curator-relevant changes surface as context
    # for Claude to act on. The status command is sub-second and silent
    # when the queue is empty, so it doesn't slow down session startup.
    bg_parts = [
        "rmx sync --flush-queue --async >/dev/null 2>&1 || true"
    ]
    if primer:
        bg_parts.append(
            "rmx primer --out '"
            + str(refmatrix_root / "PRIMER.md")
            + "' >/dev/null 2>&1 || true"
        )
    sess_cmd = (
        HOOK_ENV
        + "( " + " ; ".join(bg_parts) + " ) & disown ; "
        "rmx curator status --drain 2>/dev/null || true"
    )

    block = {
        "hooks": {
            "PostToolUse": [
                {
                    "matcher": "Edit|Write|MultiEdit|NotebookEdit",
                    "hooks": [{"type": "command", "command": enqueue_cmd}],
                }
            ],
            "Stop": [
                {"hooks": [
                    {"type": "command", "command": flush_cmd},
                    {"type": "command", "command": focus_say_cmd},
                    # STM graduates to durable memory at every turn end
                    # (feedback_save_state_includes_promote). Memory path
                    # → foreground, loud.
                    *([{"type": "command",
                        "command": HOOK_ENV + "rmx focus summarize --promote"}]
                      if stop_promote else []),
                ]}
            ],
            "SubagentStop": [
                {"hooks": [{"type": "command", "command": flush_cmd}]}
            ],
            "SessionStart": [
                {
                    "matcher": "startup|resume",
                    "hooks": [{"type": "command", "command": sess_cmd}],
                }
            ],
        }
    }

    if scan_prompt:
        # UserPromptSubmit: pipe the JSON envelope through `rmx scan-prompt`
        # so Claude sees context for symbols mentioned in the user's prompt.
        # Also surface any pending curator queue so the user's next prompt
        # arrives alongside the curator-dispatch signal (subsecond, silent
        # when empty, drains on read).
        composite = (f" --composite-every {int(composite_every)}"
                     if composite_every else "")
        scan_cmd = (
            HOOK_ENV
            + f"rmx scan-prompt{composite} --max-tokens 2000 2>/dev/null || true ; "
            "rmx curator status --drain 2>/dev/null || true"
        )
        block["hooks"]["UserPromptSubmit"] = [
            {
                "hooks": [
                    {"type": "command", "command": scan_cmd},
                    {"type": "command", "command": focus_input_cmd},
                ],
            }
        ]

    # PostToolUse focus capture on the read/edit/run tools so the focus graph
    # tracks what's being worked on right now (separate matcher so it composes
    # with the enqueue hook above).
    block["hooks"]["PostToolUse"].append({
        "matcher": "Edit|Write|MultiEdit|NotebookEdit|Read|Bash|Grep|Glob",
        "hooks": [{"type": "command", "command": focus_tool_cmd}],
    })
    block["hooks"].setdefault("PreToolUse", []).append({
        "matcher": "Edit|Write|MultiEdit|NotebookEdit|Read|Bash|Grep|Glob",
        "hooks": [{"type": "command", "command": focus_tool_pre_cmd}],
    })

    if memory_hooks:
        # Phase C3: intuition-style memory hooks. Each event gets its
        # OWN matcher block so the file-sync hooks above stay untouched
        # — Claude Code merges multiple matchers per event without
        # squashing either side. Routed explicitly to the `intuition`
        # partition because memories live there by default. No
        # 2>/dev/null and no `|| true` -- memory is critical, broken
        # state must surface; mask the symptom and the data quietly
        # rots.
        # Memory bridge catch-up: ingest the curated-memory dir as
        # kind=memory rows so files written outside `rmx save-state` still
        # reach the store. `--detach` hands the job to the daemon and returns
        # at once (an "ingest already active" or "no daemon" answer prints —
        # memory path, so it is never silenced). Claude Code runs an event's
        # hooks in parallel, so this cannot be ordered before the recall
        # below; save-state's own synchronous bridge is the primary path.
        from refmatrix.handoff import default_memory_dir
        memdir = default_memory_dir(refmatrix_root.parent)
        block["hooks"].setdefault("SessionStart", []).append({
            "matcher": "startup|resume|clear",
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        HOOK_ENV
                        + "rmx memory recall --session-start "
                        "--k 10 --scope both --json"
                    ),
                },
                {
                    "type": "command",
                    "command": (
                        HOOK_ENV
                        + "rmx ingest-gmd --as-memory --detach '"
                        + str(memdir) + "'"
                    ),
                },
            ],
        })
        if resume_focus:
            # The prior session's live STM threads, on resume only.
            block["hooks"]["SessionStart"].append({
                "matcher": "resume",
                "hooks": [{
                    "type": "command",
                    "command": HOOK_ENV
                    + f"rmx focus context --top {int(resume_focus)}",
                }],
            })
        block["hooks"].setdefault("UserPromptSubmit", []).append({
            "hooks": [{
                "type": "command",
                # Claude Code passes the UserPromptSubmit envelope on
                # stdin as JSON ({"prompt": "...", ...}); --stdin-json
                # parses it natively so the hook is one line with no
                # jq/python dependency. Empty prompt = no-op exit 0.
                "command": (
                    HOOK_ENV
                    + "rmx memory recall --stdin-json --k 5 --scope both --json"
                ),
            }],
        })
        block["hooks"]["PreCompact"] = [{
            "hooks": [
                # Inject the FULL STM digest before compaction so the compacted
                # context keeps the session's topics, git milestones, intent
                # arc, and top-N symbols — with L<n> refs into the on-disk full
                # log, so depth is still recoverable post-compact (`focus show`).
                # This is the "compaction keeps the real summary" path.
                {
                    "type": "command",
                    # --promote: the digest must GRADUATE, not just print
                    # (2026-07-06 leak: without it compaction kept the
                    # digest on screen and never wrote it). Loud.
                    "command": HOOK_ENV + "rmx focus summarize --promote",
                },
                {
                    "type": "command",
                    "command": (
                        HOOK_ENV
                        + "rmx memory recall --recent --since 1h "
                        "--k 20 --scope both --json"
                    ),
                },
                # Pre-compact checkpoint: the handoff file for the next
                # instance. --no-promote (the summarize above did it),
                # --no-sync (a 30 s bridge at compaction is the wrong
                # moment; SessionStart catch-up + manual save-state cover
                # the store). Output NOT swallowed — a red "memory bridge
                # FAILED" or lint line must reach the transcript.
                *([{
                    "type": "command",
                    "command": (
                        HOOK_ENV + "rmx save-state --no-promote --no-sync "
                        "-m \"auto: pre-compact checkpoint\""
                    ),
                }] if precompact_checkpoint else []),
            ],
        }]

    # cat-herder enforcement hooks — emitted by THIS generator so the
    # settings file has one author. Auto mode: each entry only when its
    # script is on disk under the project.
    _add_enforce_entries(block, project_root, enforce)
    return block


def _add_enforce_entries(block: dict, project_root: "Path | None",
                         enforce: "bool | None") -> None:
    if enforce is False or (enforce is None and project_root is None):
        return
    hd = (Path(project_root) / ".claude" / "hooks") if project_root else None
    p20 = (Path(project_root) / ".claude" / "p20-0") if project_root else None

    def want(rel: Path | None) -> bool:
        if enforce is True:
            return True                      # forced: emit whether or not the script is on disk yet
        return bool(rel is not None and rel.exists())

    pre = []
    if want(hd / "enforce-test-to-file.sh" if hd else None):
        pre.append({"type": "command", "command":
                    '[ -x "$CLAUDE_PROJECT_DIR/.claude/hooks/enforce-test-to-file.sh" ] '
                    '&& "$CLAUDE_PROJECT_DIR/.claude/hooks/enforce-test-to-file.sh" || true'})
    if want(hd / "enforce-rmx-grep.sh" if hd else None):
        pre.append({"type": "command", "command":
                    '[ -x "$CLAUDE_PROJECT_DIR/.claude/hooks/enforce-rmx-grep.sh" ] '
                    '&& "$CLAUDE_PROJECT_DIR/.claude/hooks/enforce-rmx-grep.sh" || true'})
    if pre:
        block["hooks"].setdefault("PreToolUse", []).append(
            {"matcher": "Bash", "hooks": pre})
    if want(hd / "adr-gate.sh" if hd else None):
        block["hooks"].setdefault("PostToolUse", []).append({
            "matcher": "Edit|Write|MultiEdit|NotebookEdit",
            "hooks": [{"type": "command", "command":
                       '[ -x "$CLAUDE_PROJECT_DIR/.claude/hooks/adr-gate.sh" ] '
                       '&& "$CLAUDE_PROJECT_DIR/.claude/hooks/adr-gate.sh" 2>/dev/null || true'}],
        })
    if want(p20 / "compile_guardrails.py" if p20 else None):
        block["hooks"].setdefault("SessionStart", []).append({
            "matcher": "startup|resume|clear",
            "hooks": [{"type": "command", "command":
                       '[ -d "$CLAUDE_PROJECT_DIR/.claude/p20-0" ] && command -v rmx >/dev/null 2>&1 '
                       '&& python3 "$CLAUDE_PROJECT_DIR/.claude/p20-0/compile_guardrails.py" >/dev/null 2>&1 || true'}],
        })


def install(
    project_root: Path,
    refmatrix_root: Path,
    git: bool = True,
    claude: bool = True,
    briefing: bool = True,
    scope: str = "project",
    apply: bool = False,
    force: bool = False,
    memory_hooks: bool = True,
    agent_env: bool = True,
    search: bool = True,
    primer: bool = True,
    scan_prompt: bool = True,
    composite_every: "int | None" = 3,
    precompact_checkpoint: bool = True,
    stop_promote: bool = True,
    resume_focus: "int | None" = 15,
    enforce: "bool | None" = None,
) -> list[str]:
    """Return a list of human-readable plan lines. Performs writes if apply=True."""
    out: list[str] = []
    project_root = project_root.resolve()
    hook_opts = dict(composite_every=composite_every,
                     precompact_checkpoint=precompact_checkpoint,
                     stop_promote=stop_promote, resume_focus=resume_focus,
                     enforce=enforce)

    if git:
        out.extend(_install_git_hooks(project_root, apply=apply, force=force))
    if claude:
        out.extend(_install_claude_hooks(project_root, refmatrix_root,
                                         scope=scope, apply=apply, force=force,
                                         primer=primer, scan_prompt=scan_prompt,
                                         memory_hooks=memory_hooks, **hook_opts))
    if agent_env:
        out.extend(_install_agent_env(project_root, scope=scope,
                                      apply=apply, force=force))
    if search:
        from refmatrix.search_hooks import install_search_hooks
        out.extend(install_search_hooks(project_root, scope=scope,
                                        apply=apply, force=force))
    if briefing:
        out.extend(_install_briefing(project_root, refmatrix_root,
                                     apply=apply, force=force))
    if apply and scope == "project":
        record_flags(project_root, dict(memory_hooks=memory_hooks, primer=primer,
                                        scan_prompt=scan_prompt, search=search,
                                        **hook_opts))
        out.append(f"[green]write[/] {project_root / '.claude' / 'rmx-hooks.json'} (flags)")
    if not apply:
        out.append("[dim]dry-run — pass --apply to write[/]")
    return out


FLAGS_FILE = Path(".claude") / "rmx-hooks.json"


def record_flags(project_root: Path, flags: dict) -> Path:
    """Persist the generator flags so `--check` re-renders the same block."""
    from refmatrix import __version__
    p = Path(project_root) / FLAGS_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"version": __version__, "flags": flags}, indent=2) + "\n")
    return p


def _managed_entries(hooks: dict) -> "set[tuple[str, str, str]]":
    out = set()
    for event, blocks in (hooks or {}).items():
        for blk in blocks:
            for h in blk.get("hooks", []):
                cmd = h.get("command") or ""
                if _is_rmx_hook(cmd):
                    out.add((event, blk.get("matcher") or "", cmd))
    return out


def _entry_multiset(hooks: dict):
    """(managed Counter of (event, matcher, full-entry-json), unmanaged list).
    Full entry JSON so a `timeout` edit or an extra key is drift; a Counter
    so a duplicated block is drift (bsd-plan2 #s-4)."""
    from collections import Counter
    managed: Counter = Counter()
    unmanaged: list = []
    for event, blocks in (hooks or {}).items():
        for blk in blocks:
            for h in blk.get("hooks", []):
                cmd = h.get("command") or ""
                key = (event, blk.get("matcher") or "",
                       json.dumps(h, sort_keys=True))
                if _is_rmx_hook(cmd):
                    managed[key] += 1
                else:
                    unmanaged.append((event, blk.get("matcher") or "", cmd))
    return managed, unmanaged


def render_managed(project_root: Path, flags: dict) -> dict:
    """The full rmx-managed hook set for a project under `flags`: the Claude
    block plus the search hooks when enabled. This is what `--check` compares
    against and what `--apply` writes."""
    project_root = Path(project_root)
    block = _claude_hook_block(
        project_root / ".refmatrix", primer=flags.get("primer", True),
        scan_prompt=flags.get("scan_prompt", True),
        memory_hooks=flags.get("memory_hooks", True),
        composite_every=flags.get("composite_every", 3),
        precompact_checkpoint=flags.get("precompact_checkpoint", True),
        stop_promote=flags.get("stop_promote", True),
        resume_focus=flags.get("resume_focus", 15),
        enforce=flags.get("enforce"),
        project_root=project_root,
    )
    if flags.get("search", True):
        from refmatrix.search_hooks import search_hook_block
        for event, entries in search_hook_block()["hooks"].items():
            block["hooks"].setdefault(event, []).extend(entries)
    return block


def check(project_root: Path) -> "tuple[bool, str]":
    """Does `.claude/settings.json` carry exactly the rmx-managed hooks this
    version generates under the recorded flags? Returns (ok, diff). The
    diff lists `- event/matcher: cmd` for installed-only and `+ …` for
    generated-only entries."""
    project_root = Path(project_root)
    fp = project_root / FLAGS_FILE
    if not fp.exists():
        return False, (f"no {fp} — run `rmx install-hooks --apply` "
                       "(this records the generator flags --check needs)")
    try:
        flags = json.loads(fp.read_text()).get("flags") or {}
    except json.JSONDecodeError as e:
        return False, f"{fp}: invalid JSON ({e})"
    settings = project_root / ".claude" / "settings.json"
    installed: dict = {}
    if settings.exists():
        try:
            installed = json.loads(settings.read_text()).get("hooks") or {}
        except json.JSONDecodeError as e:
            return False, f"{settings}: invalid JSON ({e})"
    have, foreign = _entry_multiset(installed)
    want, _ = _entry_multiset(render_managed(project_root, flags)["hooks"])
    lines: list = []
    for key in sorted(set(have) | set(want)):
        h, w = have.get(key, 0), want.get(key, 0)
        ev, m, entry = key
        if h > w:
            tag = "duplicate " if w else ""
            lines += [f"- {tag}{ev}/{m}: {entry}"] * (h - w)
        elif w > h:
            lines += [f"+ {ev}/{m}: {entry}"] * (w - h)
    # The three ~/.claude/hooks scripts are the second author of runtime
    # behaviour (the grep rewrite, the Grep-tool teach); an edited one is
    # drift too.
    if flags.get("search", True):
        from refmatrix.search_hooks import hooks_dir, render_scripts
        for name, content in render_scripts().items():
            on_disk = hooks_dir() / name
            if not on_disk.exists() or on_disk.read_text() != content:
                lines.append(f"- script {name} differs from the generator's "
                             f"render (rmx install-hooks --apply --force)")
    ok = not lines
    # Foreign hooks are listed, never failed: they survive --force by design,
    # but the operator should see the second author.
    info = [f"? {ev}/{m}: {c}" for ev, m, c in foreign]
    return ok, "\n".join(lines + info)


def _install_git_hooks(project_root: Path, apply: bool, force: bool) -> list[str]:
    out: list[str] = []
    git_dir = project_root / ".git"
    if not git_dir.is_dir():
        out.append(f"[yellow]skip git hooks:[/] no .git in {project_root}")
        return out
    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(exist_ok=True)
    for name, script in GIT_HOOK_SCRIPTS.items():
        target = hooks_dir / name
        if target.exists() and not force:
            out.append(f"[yellow]skip[/] {target} (exists; pass --force to overwrite)")
            continue
        out.append(f"[green]write[/] {target}")
        if apply:
            target.write_text(script)
            target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return out


CLAUDE_BRIEFING = """\
# refmatrix briefing for Claude

This project has a refmatrix index at `.refmatrix/` — a roaring-bitmap-backed
graph of docs, code, and concepts. Hooks keep it fresh on git operations and
on every Edit/Write tool call. **Trust the index.**

## When to reach for `rmx` instead of grep/Read

| Question | Command |
|---|---|
| "what calls X" / "where is X used" | `rmx neighbors X --depth 2` |
| "give me everything about X for an LLM" | `rmx context X` (token-budgeted) |
| "what changed since this branch diverged" | `rmx context --since main` |
| "find docs and code mentioning X" | `rmx query "mentions:X OR defines:X"` |
| "all classes" / "all functions" | `rmx query "is_a:kind/class"` (when ingested via metadata) |
| "every call site of X, including noisy stuff" | `rmx query "calls:X" --full` |
| "explain why an entity matched a query" | `rmx query "<dsl>" --explain` |
| "concepts that co-occur with X" | `rmx co-occur X --type mentions` |
| "rank entities by mention frequency" | `rmx top X --type mentions -k 10` |
| "what does this prompt's symbols touch" | (auto via `UserPromptSubmit` hook) |

`rmx context <symbol>` is the most token-efficient way to understand a symbol's
role — it bundles the symbol's tldr plus immediate neighbors per linkage with
their tldrs, capped by token budget. Prefer it over reading 5 files. For
programmatic use, `rmx context X --format json`.

When a query result surprises you, **always re-run with `--explain`** — it
shows file:line evidence for each (linkage, concept) membership that qualified
the entity. That's the trust mechanism.

## Query syntax

**DSL (infix set algebra):**
```
mentions:parser AND defines:parser
calls:foo OR (mentions:bar AND NOT imports:legacy)
mentions:keyword/data            # namespaced concept (auto-emitted by ingester)
imports:import/json              # python module concept
parser                            # bare term: union across all linkages
```

**PQL (Pilosa-style functions):**
```
Row(defines, parser)
Intersect(Row(calls, foo), Row(mentions, bar))
Union(...)  Difference(A, B)  Xor(...)  TopN(<bm>, n)  Count(<bm>)
```

## Linkage taxonomy

Defaults: `defines`, `called_by`, `calls`, `mentions`, `imports`, `is_a`,
`related-to`. Plus any custom types added with `rmx add-linkage-type`.

`rmx list-linkages` shows what's actually defined in this project.

## Concept namespacing

Auto-generated concepts are namespaced so they don't collide with your own:
- `keyword/<word>` — extracted from docstrings (noisy by design; mostly
  filtered out of the primer and `scan-prompt`)
- `import/<module>` — module dependencies (from metadata.json `dependencies`
  field, or the ast walker as fallback)
- `kind/<unit_type>` — categorical (function/class/method/...) from
  llm-tldr's per-unit metadata. Query with `is_a:kind/class`.
- bare names — symbol concepts (function/class names) and anything you
  added with `rmx add-concept`

To query a namespaced concept: `mentions:keyword/foo`, `imports:import/json`,
`is_a:kind/function`.

## Cleaned vs full graph

`rmx prune-noise` is non-destructive by default — it MARKS concepts as noise
(in `keyword/` namespace, df<2 or df>25%) instead of deleting them. Queries
hide noise concepts so the cleaned graph is what you see normally.

When you need find/grep-style completeness — every match, including
auto-generated noise — pass `--full`:
- `rmx query "mentions:foo" --full`
- `rmx neighbors X --full`
- `rmx co-occur X --full`
- `rmx primer --full`
- `rmx scan-prompt --full`

Pass `rmx prune-noise --drop` to actually delete (irrecoverable).

## Manual additions are protected

`rmx add-entity`, `rmx add-concept`, and `rmx link` mark their entities
`protected` by default — vacuum and prune-noise will never touch them.
This is the durable layer for human-curated knowledge that should outlive
ingester re-runs. Pass `--no-protect` to opt out.

## Freshness contract

Hooks installed by `rmx install-hooks --apply`:
- `PostToolUse` on Edit/Write/MultiEdit/NotebookEdit → enqueues touched paths
- `Stop` / `SubagentStop` → flushes via `rmx sync --flush-queue`
- `SessionStart` (startup|resume) → flushes + regenerates `.refmatrix/PRIMER.md`
- `UserPromptSubmit` → `rmx scan-prompt` injects bundles for symbols you mention
- git `post-commit` / `post-merge` / `post-checkout` / `post-rewrite` → syncs
  paths changed since the relevant ref

Diagnostics:
- `rmx queue` — pending paths waiting to flush
- `rmx stats --stale` — tracked files where on-disk mtime > last_synced
- `cat .refmatrix/sync.log` — append-only log of every sync, with timestamps
  and `+added ~updated -purged` counts

Repair:
- `rmx sync --flush-queue` — force the pending flush
- `rmx vacuum` — drop empty-bitmap concepts and missing-file tracked rows
  (skips protected concepts)
- `rmx prune-noise` — MARK noise concepts (non-destructive); add `--drop`
  to actually delete. Skips protected concepts.
- `rmx ingest . --semantic` — full rebuild
- `rmx tldr-warm . --semantic` — fresh call graph from llm-tldr + rebuild

## What you can trust

- Bitmap membership reflects state as of the last hook flush.
- `tldr` blobs on entities come from llm-tldr's `signature` (when
  metadata.json was ingested), `--semantic` enrichment, or manual
  `rmx add-entity --tldr ...`.
- Symbol concepts come from llm-tldr (preferred:
  `.tldr/cache/semantic/metadata.json` for per-unit data including
  `unit_type`, `signature`, dependencies; fallback:
  `.tldr/cache/call_graph.json` for just the call graph).
- `linkage_evidence` table records file:line for every semantic linkage —
  shown by `rmx query --explain`.

## Quick reference

```
rmx info                            # active .refmatrix root
rmx stats                           # cardinalities per linkage
rmx stats --stale                   # ... plus drift detection
rmx list-entities --kind concept    # all concepts
rmx list-linkages                   # all linkage types
rmx context <symbol> --format json  # LLM-friendly bundle
rmx context --since <git-ref>       # branch-scoped bundle
rmx query "<dsl>" --explain         # results + linkage chains with file:line
rmx query "<dsl>" --ids-only        # raw entity ids for piping
rmx primer --top 50 --max-tokens 1500    # density-ranked symbol map
rmx scan-prompt --text "<prompt>"        # context for symbols in a prompt
```

## Auto-generated context

- `.refmatrix/PRIMER.md` — top reference-dense symbols, regenerated on
  `SessionStart`. Add `@.refmatrix/PRIMER.md` to your project CLAUDE.md
  for cheap orientation. (~2K tokens, 150 symbols, no English noise.)
- `UserPromptSubmit` hook runs `rmx scan-prompt` so any symbol mentioned
  in your prompt gets a `rmx context` bundle injected before the turn.
  Token-shaped names match exactly; bare module names (e.g. `tree_sitter`
  in your prompt) match `import/tree_sitter` via suffix matching.

If you're handed a symbol you've never seen, run `rmx context <name>`
explicitly — the hook only kicks in when the symbol appears verbatim.

## Working memory (STM) — what's being worked on right now

Hooks auto-capture this session into a per-project focus graph + full log:
user prompts (`input`), tool calls (`tool`), my replies (`say`, from the Stop
hook), and git milestones (`git` — commit/push/merge captured WITH their
output + diffstat). Read surfaces default to the **active** Claude session.

```
rmx focus context        # dialogue (intent) + git milestones + ranked graph
                         #   with +1 neighbors, each row L<n>-ref'd to the log
rmx focus topics         # cluster the session into topical threads (timeline)
rmx focus show <n> [-C K] # the full untruncated event(s) at log line n
rmx focus export         # the ENTIRE session log (never trimmed), line-numbered
rmx task push/pop/list   # pushdown stack for interrupted work (snapshots focus)
```

The L<n> refs link every summary row back to raw events — follow the session's
evolution topically, then drill to depth. The log is the full session on disk.

## Capture your reasoning (add-thought-process)

STM auto-captures your prompts, tool calls, replies, and git milestones — but
your extended-thinking blocks are redacted from the transcript, so the WHY
behind your decisions is lost unless you record it. When you make a non-obvious
decision, form a hypothesis, choose between approaches, or hit a gotcha, leave
a terse reasoning note:

```
rmx focus note "chose X over Y because Z; risk is W"
```

It lands as a `reason` event in STM (shown in `focus context` as ✎), so the
reasoning survives compaction and the next instance inherits not just what you
did but why. Cheap, deliberate, high-signal — do it at decision points, not
every turn.

## Durable memory (LTM) + handoff

```
rmx memory recall "<query>"     # semantic recall over curated memories
rmx memory recall --recent      # newest-first, no embedder
rmx memory add <name> -c "..."   # write a memory (--global for cross-project)
rmx context <memory-id>          # a memory's body + its graph neighborhood
rmx save-state [--commit]        # compile STM + git + recent memories into ONE
                                 #   stable-id handoff memory (overwrite, not
                                 #   rebuild). --commit also commits the repo.
```

On a cold start, `rmx memory recall --session-start` (run by the SessionStart
hook) surfaces recent context. `rmx save-state` at the end of a work session
leaves a handoff the next instance reads — and runs the memory bridge
(`ingest-gmd --as-memory` over `~/.claude/projects/<slug>/memory/`) so every
memory file written this session is in the store before that recall. The
SessionStart hook re-runs the bridge in the background as catch-up for files
written outside save-state. Write memory files BEFORE `rmx save-state`, not
after.

## To remove

Delete `.refmatrix/`, the `rmx` lines from `.git/hooks/*`, and the rmx
entries from `.claude/settings.json`.
"""


# Agent shell environment. BASH_ENV makes every non-interactive bash the
# Claude Code harness spawns (main agent AND subagents) source this file, so
# rmx helpers and env defaults reach every Bash tool call. The rmx-owned
# content lives between marker lines so re-installs can refresh it without
# touching user-authored additions in the same file.
AGENT_BASHRC_PATH = "~/.claude/agent-bashrc.sh"
_BASHRC_BEGIN = "# >>> rmx agent env >>>"
_BASHRC_END = "# <<< rmx agent env <<<"

AGENT_BASHRC_SECTION = f"""{_BASHRC_BEGIN}
# Managed by `rmx install-hooks` — edits inside these markers are overwritten
# on reinstall. Add personal content OUTSIDE the markers.
# Sourced on EVERY Bash tool call: keep fast.

export RMXGREP_MODE="${{RMXGREP_MODE:-rich}}"

# grep/rg become the learning drop-ins (byte-exact outside a project, index
# + delegation inside) as FUNCTIONS, not aliases. An alias needs
# `shopt -s expand_aliases`, which also rewrites `grep` inside every function
# body bash parses afterwards — 2026-09-14: Claude Code's shell snapshot
# captured a user's `psg` with the rmxgrep path baked in, and its own
# `set -o | grep on` generator got rmx's note → `set -o #`. A function
# resolves at call time only, and the wrappers treat a piped stdin as a
# plain filter.
if [ -x "$HOME/refmatrix/bin/rmxgrep" ]; then grep() {{ "$HOME/refmatrix/bin/rmxgrep" "$@"; }}; fi
if [ -x "$HOME/refmatrix/bin/rmxrg" ]; then rg() {{ "$HOME/refmatrix/bin/rmxrg" "$@"; }}; fi

# Retrieval-first helpers. `rmx context` is THE first lookup (BM25 + graph
# neighbors with a literal-grep floor); see .refmatrix/PRIMER.md.
rmxc()   {{ rmx context "$@"; }}                          # rmxc "<query or symbol>"
rmxcx()  {{ rmx context "$1" --expand "${{2:-5}}"; }}       # rmxcx <name> [N] — ±N source lines/hit
rmxhl()  {{ rmx context "$1" --hit-lines "${{2:-text}}"; }} # rmxhl <name> [nums|text]
rmxn()   {{ rmx neighbors "$@"; }}                        # graph walk from a node
rmxq()   {{ rmx query "$@"; }}                            # set-algebra DSL
rmxg()   {{ rmx grep "$@"; }}                             # index-backed grep (bare grep/rg flags OK)
rmxloc() {{ rmx locate "$@"; }}                           # full paths by filename/symbol
rmxmem() {{ rmx memory recall "$@"; }}                    # memory recall
rmxtop() {{ rmx top "$@"; }}                              # top-K entities by weight
rmxd()   {{ rmx daemon status "$@"; }}                    # daemon health
rmxst()  {{ rmx stats "$@"; }}                            # catalog + bitmap stats
{_BASHRC_END}
"""


def _install_agent_env(
    project_root: Path,
    scope: str,
    apply: bool,
    force: bool,
) -> list[str]:
    """Write the rmx-managed section of ~/.claude/agent-bashrc.sh and wire
    BASH_ENV (+ RMXGREP_MODE) into the Claude settings env block.

    The bashrc lives at a user-global path regardless of scope — BASH_ENV
    needs one stable path. The env wiring follows scope: project scope merges
    into .claude/settings.local.json; user scope prints a snippet (we never
    silently edit ~/.claude/settings.json).
    """
    out: list[str] = []
    # RMX_AGENT_BASHRC overrides the target path (tests; exotic setups).
    bashrc = Path(os.environ.get("RMX_AGENT_BASHRC",
                                 AGENT_BASHRC_PATH)).expanduser()

    # --- bashrc: create, refresh markers, or append section ---
    if not bashrc.exists():
        out.append(f"[green]write[/] {bashrc}")
        if apply:
            bashrc.parent.mkdir(parents=True, exist_ok=True)
            bashrc.write_text(AGENT_BASHRC_SECTION)
    else:
        text = bashrc.read_text()
        if _BASHRC_BEGIN in text and _BASHRC_END in text:
            if force:
                out.append(f"[green]refresh[/] rmx section in {bashrc}")
                if apply:
                    pre, _, rest = text.partition(_BASHRC_BEGIN)
                    _, _, post = rest.partition(_BASHRC_END)
                    post = post.lstrip("\n")
                    section = AGENT_BASHRC_SECTION.rstrip("\n") + "\n"
                    bashrc.write_text(pre + section + post)
            else:
                out.append(f"[yellow]skip[/] {bashrc} "
                           "(rmx section present; pass --force to refresh)")
        else:
            out.append(f"[green]append[/] rmx section to {bashrc}")
            if apply:
                sep = "" if text.endswith("\n") else "\n"
                bashrc.write_text(text + sep + "\n" + AGENT_BASHRC_SECTION)

    # --- env wiring ---
    env_block = {
        "BASH_ENV": str(bashrc),
        "RMXGREP_MODE": "rich",
    }
    if scope == "user":
        out.append("[bold]Claude Code (user scope)[/] — merge into "
                   "~/.claude/settings.json:")
        out.append(json.dumps({"env": env_block}, indent=2))
        return out

    target = project_root / ".claude" / "settings.local.json"
    existing: dict = {}
    if target.exists():
        try:
            existing = json.loads(target.read_text())
        except json.JSONDecodeError:
            out.append(f"[red]warn[/] {target} is not valid JSON; "
                       "skipping env wiring")
            return out
    env = dict(existing.get("env") or {})
    added = {k: v for k, v in env_block.items()
             if force or k not in env}
    if not added:
        out.append(f"[yellow]skip[/] env block in {target} (keys present)")
        return out
    env.update(added)
    out.append(f"[green]merge[/] env {{{', '.join(sorted(added))}}} "
               f"into {target}")
    if apply:
        target.parent.mkdir(exist_ok=True)
        merged = {**existing, "env": env}
        target.write_text(json.dumps(merged, indent=2))
    return out


def _install_briefing(
    project_root: Path,
    refmatrix_root: Path,
    apply: bool,
    force: bool,
) -> list[str]:
    """Write .refmatrix/CLAUDE.md and print the import suggestion."""
    out: list[str] = []
    target = refmatrix_root / "CLAUDE.md"
    if target.exists() and not force:
        out.append(f"[yellow]skip[/] {target} (exists; pass --force to overwrite)")
    else:
        out.append(f"[green]write[/] {target}")
        if apply:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(CLAUDE_BRIEFING)

    # Suggest (don't write) an import line for the project's main CLAUDE.md.
    try:
        rel = (refmatrix_root / "CLAUDE.md").resolve().relative_to(project_root.resolve())
        rel_path = rel.as_posix()
    except ValueError:
        rel_path = str(refmatrix_root / "CLAUDE.md")
    project_md = project_root / "CLAUDE.md"
    out.append(
        "[dim]Suggestion (not auto-applied):[/] add this line to "
        f"{project_md} so Claude loads the briefing:"
    )
    out.append(f"    @{rel_path}")
    return out


def _install_claude_hooks(
    project_root: Path,
    refmatrix_root: Path,
    scope: str,
    apply: bool,
    force: bool,
    primer: bool = True,
    scan_prompt: bool = True,
    memory_hooks: bool = True,
    **hook_opts,
) -> list[str]:
    out: list[str] = []
    block = _claude_hook_block(
        refmatrix_root, primer=primer, scan_prompt=scan_prompt,
        memory_hooks=memory_hooks, project_root=project_root, **hook_opts,
    )
    if scope == "user":
        # Always print — never silently merge into the user's global config.
        out.append("[bold]Claude Code (user scope)[/] — merge into ~/.claude/settings.json:")
        out.append(json.dumps(block, indent=2))
        return out

    # Project scope writes the COMMITTED settings.json: hooks are project
    # customization every clone runs, not per-machine state (settings.local
    # keeps permissions and the like). Pre-0.67 installs wrote the local
    # file; its rmx entries are stripped below so nothing fires twice.
    target = project_root / ".claude" / "settings.json"
    target.parent.mkdir(exist_ok=True)
    existing: dict = {}
    if target.exists():
        try:
            existing = json.loads(target.read_text())
        except json.JSONDecodeError:
            out.append(f"[red]warn[/] {target} is not valid JSON; aborting claude install")
            return out
        if _managed_entries(existing.get("hooks") or {}) and not force:
            out.append(f"[yellow]skip[/] {target} (already has rmx hooks; pass --force to replace)")
            return out
    legacy = project_root / ".claude" / "settings.local.json"
    if legacy.exists():
        try:
            ldata = json.loads(legacy.read_text())
        except json.JSONDecodeError:
            ldata = None
        if isinstance(ldata, dict) and _managed_entries(ldata.get("hooks") or {}):
            _strip_rmx_hooks(ldata.setdefault("hooks", {}))
            if not ldata["hooks"]:
                del ldata["hooks"]
            out.append(f"[green]strip[/] rmx hooks from legacy {legacy}")
            if apply:
                legacy.write_text(json.dumps(ldata, indent=2))

    merged = {**existing}
    merged.setdefault("hooks", {})
    # --force re-install must OVERWRITE rmx-managed entries, not append them
    # (a blind extend duplicates every hook on each re-run). Strip prior rmx
    # entries first — identified by the RMX_INVOCATION_SOURCE=hook marker that
    # every rmx hook command carries — then add the fresh block. User-authored
    # hooks (without the marker) are preserved, even if they share an event.
    if force:
        _strip_rmx_hooks(merged["hooks"])
    for event, entries in block["hooks"].items():
        merged["hooks"].setdefault(event, [])
        merged["hooks"][event].extend(entries)
    out.append(f"[green]write[/] {target}")
    if apply:
        target.write_text(json.dumps(merged, indent=2))
    return out


RMX_HOOK_MARKER = "RMX_INVOCATION_SOURCE=hook"
# Every current rmx hook carries the marker, but legacy installs predate it
# (e.g. the marker-less `--enqueue-only` PostToolUse hook). Match those
# command signatures too so a `--force` reinstall reaps stale duplicates
# instead of leaving them beside the fresh copy.
_RMX_HOOK_SIGNATURES = (
    RMX_HOOK_MARKER, "--enqueue-only", "rmx focus hook", "rmx memory recall",
    "rmx scan-prompt", "rmx sync --flush-queue", "rmx primer", "rmx curator",
    "grep-rewrite-guard.sh", "grep-tool-teach.sh",
    # rmx-generated memory/STM hooks (also carry the marker) and the
    # cat-herder enforcement hooks this generator now emits.
    "rmx ingest-gmd --as-memory", "rmx save-state", "rmx focus summarize",
    "rmx focus context",
    # EXACT script names — a prefix (`.claude/hooks/enforce-`) classified any
    # user hook named enforce-*.sh as rmx's and `--force` deleted it
    # (bsd-plan2 #b-2, the failure mode this plan exists to end).
    ".claude/hooks/enforce-test-to-file.sh", ".claude/hooks/enforce-rmx-grep.sh",
    ".claude/hooks/adr-gate.sh", "p20-0/compile_guardrails.py",
)


def _is_rmx_hook(cmd: str) -> bool:
    return any(sig in cmd for sig in _RMX_HOOK_SIGNATURES)


def _strip_rmx_hooks(events: dict) -> None:
    """Remove rmx-managed hook entries from a settings `hooks` dict, in place.
    Preserves user hooks; drops blocks left empty and events left with no
    blocks — so a re-install re-adds a clean single copy."""
    for event in list(events.keys()):
        new_blocks = []
        for blk in events.get(event, []):
            kept = [h for h in blk.get("hooks", [])
                    if not _is_rmx_hook(h.get("command") or "")]
            if kept:
                new_blocks.append({**blk, "hooks": kept})
        if new_blocks:
            events[event] = new_blocks
        else:
            del events[event]
