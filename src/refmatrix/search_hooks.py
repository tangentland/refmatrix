"""Claude Code search hooks — vendored, rendered, and installed by
`rmx install-hooks --search`.

Three user-global scripts under ~/.claude/hooks make every agent search feed
the graph and every reasoning-free dodge structurally impossible:

- grep-rewrite-guard.sh   PreToolUse(Bash): rewrites a leading grep/rg
  (bare, /abs/path, or command/env-launched) to the rmxgrep/rmxrg learning
  wrappers; passes git through untouched in its entirety.
- rmxgrep-rewrite.py      the precise rewriter the guard calls.
- grep-tool-teach.sh      PostToolUse(Grep): the dedicated Grep tool bypasses
  the Bash hook, so this fires a detached, throttled teach ping with the same
  pattern. Capture-only.

Scripts always live at the user-global hooks dir (one stable path, like the
agent bashrc); the settings wiring follows --scope: project merges into
.claude/settings.json, user prints a snippet (we never silently edit
~/.claude/settings.json). Wrapper paths are resolved at install time — PATH
first, then this package's repo bin/ — and baked in absolute, because the
guard's own history shows aliasable names get aliased out from under hooks.
"""
from __future__ import annotations

import json
import os
import shutil
import stat
from pathlib import Path

GUARD_NAME = "grep-rewrite-guard.sh"
REWRITER_NAME = "rmxgrep-rewrite.py"
TEACH_NAME = "grep-tool-teach.sh"

GUARD_TEMPLATE = """\
#!/usr/bin/env bash
# PreToolUse(Bash) guard + search rewriter. (Renamed from rtk-write-guard.sh
# 2026-09-13 — the last rtk-named artifact; content was already rtk-free.)
#
# HISTORY (2026-09-11): rtk was REMOVED. This script was formerly a wrapper that
# interposed on rtk-rewrite.sh (rtk integrity-checked its own hook against
# ~/.claude/hooks/.rtk-hook.sha256, so it could not be edited in place — hence a
# wrapper rather than an edit). rtk is gone and the delegation went with it. The
# NAME and PATH are unchanged on purpose: ~/.claude/settings.json PreToolUse(Bash)
# points here, and the file is the address. What survives is the part that was
# never about rtk — the grep -> rmxgrep rewrite, now this script's whole job.
#
# Behavior:
#   1. git (in its entirety) and state-changing alembic pass through RAW.
#   2. A LEADING grep/rg becomes rmxgrep/rmxrg, so every search teaches the graph.
#   3. Everything else passes through untouched.
#
# Why git is exempt IN ITS ENTIRETY (todd, 2026-07-25): the READ filters were the
# dangerous ones. `rtk git status --short` was observed SILENTLY DROPPING modified
# files, printing only an untracked entry against a tree that actually held two
# modified tracked files. That reads as "clean tree", which is exactly how in-flight
# work gets treated as abandoned and lost. A status/log/diff filter that can omit a
# row is not a compression, it is a correctness hazard: git porcelain is the ground
# truth that commit, merge, and hand-off decisions are made on, and no token saving
# is worth a false reading of it. The exemption is KEPT after rtk's removal so that
# nothing added here later can quietly re-acquire the git surface.
#
# Why grep is REWRITTEN, not merely spared (todd, 2026-07-27 -> 2026-09-06): a
# compressed grep result teaches the graph NOTHING; `rmx grep` is a LEARNING grep —
# it captures the I/O and indexes the intersections it finds, so the project graph
# improves on every search. Originally this could only pass grep through, because
# `rmx grep` was not flag-compatible and an automatic rewrite would have mangled any
# flag-bearing search into a SILENTLY WRONG ANSWER — the same failure class that
# retired `rtk git`. Flag-compat landed (rmx grep bare flags 0.25.7 -> byte-exact
# rmxgrep/rmxrg shell wrappers 0.54.0), so the guard graduated to the real rewrite
# its own header had planned. Worst case of a rewrite is byte-identical grep
# behavior — rmxgrep's plain mode execs the real tool.
#
# Matched where grep HEADS a command segment — start, or after | ; && ( ` . The
# rewriter (rmxgrep-rewrite.py) skips heredocs and quoted contexts.
#
# ABSOLUTE PATHS ARE LOAD-BEARING (2026-09-11). The interactive rc aliases
# `grep` -> rmxgrep under `shopt -s expand_aliases`. When this script inherited
# that alias, its own `grep -qE` match tests became `rmxgrep -qE`, whose exit
# status does not follow grep's match/no-match contract — so the rewrite test
# evaluated FALSE and the hook silently emitted nothing, passing every search
# through unrewritten. A guard that fails OPEN and SILENT is the failure mode
# this file exists to prevent, so the internal tools are called by absolute path
# and can no longer be aliased out from under it.

GREP=/usr/bin/grep
JQ=$(command -v jq 2>/dev/null)
[ -x "$JQ" ] || JQ=/usr/bin/jq

INPUT=$(cat)
CMD=$(printf '%s' "$INPUT" | "$JQ" -r '.tool_input.command // empty' 2>/dev/null)

[ -z "$CMD" ] && exit 0

# GUARD: pass ALL git through untouched, plus state-changing alembic.
if printf '%s' "$CMD" | "$GREP" -qE '\\bgit\\b|\\balembic[[:space:]][^|;&]*[[:space:]](upgrade|downgrade|stamp|revision)\\b'; then
  exit 0
fi

# REWRITE: leading grep/rg -> rmxgrep/rmxrg.
# Sloppy on purpose: fires on any standalone grep/rg token (covers bare,
# path-prefixed, and command/env-launched forms); the python rewriter makes
# the precise call and emits nothing when no true head matches.
if printf '%s' "$CMD" | "$GREP" -qE '(^|[[:space:]]|[|;&({`])([^[:space:]]*/)?(grep|rg)([[:space:]]|$)'; then
  NEWCMD=$(printf '%s' "$INPUT" | /usr/bin/python3 "@REWRITER@" 2>/dev/null)
  if [ -n "$NEWCMD" ] && [ "$NEWCMD" != "$CMD" ]; then
    "$JQ" -cn --arg cmd "$NEWCMD" \\
      '{hookSpecificOutput:{hookEventName:"PreToolUse",updatedInput:{command:$cmd}}}'
  fi
  exit 0
fi

# Everything else: untouched.
exit 0
"""

REWRITER_TEMPLATE = """\
#!/usr/bin/env python3
\"\"\"Rewrite grep/rg command heads to rmxgrep/rmxrg (PreToolUse Bash helper).

Called by rtk-write-guard.sh with the hook input JSON on stdin. Prints the
REWRITTEN COMMAND STRING (raw, no JSON) when a rewrite applies, else nothing.
The wrapper wraps it into the updatedInput envelope. (Through 2026-09-11 the
wrapper then delegated that command to rtk so a pipeline's non-grep half kept
its compaction; rtk has since been removed, so the envelope is the final word.)

Scope (v2, widened 2026-09-06 — "we can probably make the rewrite less
conservative"): a grep/rg token is a command head when it sits at the start
of the command or line, or after |, ||, &&, ;, &, $(, backtick, (, or {.
Pipes are now IN scope: rmxgrep's plain mode is byte-exact (it execs the
real tool), so a mid-pipeline rewrite cannot change bytes or exit codes —
it only adds the detached teach ping.

Still skipped:
  * commands containing a heredoc (`<<`) — rewriting document bodies could
    corrupt file content being written;
  * matches inside an open quote (single or double quote parity is odd at
    the match position) — `echo "x | grep y"` keeps its string literal.
\"\"\"
import json
import re
import sys

RMXGREP = "@RMXGREP@"
RMXRG = "@RMXRG@"

# The head token may carry an absolute path (`/usr/bin/grep`, `/opt/local/
# bin/rg`) — the classic dodge around a bare-name rewrite. The optional
# prefix must END in `/` so `ugrep` / `/x/ugrep` never match (`[^\\s/]+`
# cannot cross a slash, so a prefix cannot terminate mid-basename).
#
# `command grep` (with optional -p) and `env VAR=val ... grep` are dodges
# too — the launcher word stays in place and only the tool token is
# replaced, so env assignments survive and `command /abs/rmxgrep` remains
# valid. `command -v grep` (a lookup, not a search) deliberately fails the
# pattern: -v is not in the allowed prefix, and without the launcher the
# token has no head boundary.
_HEAD = re.compile(
    r"(^|\\|\\||&&|[|;&(`{]\\s*|\\$\\(\\s*|\\n\\s*)\\s*"
    r"(?:command\\s+(?:-p\\s+)?|env\\s+(?:\\w+=\\S*\\s+)*)?"
    r"((?:/[^\\s/]+)*/)?(grep|rg)(?=\\s|$)",
    re.MULTILINE,
)


def _in_open_quote(s: str) -> bool:
    \"\"\"True when position `len(s)` sits inside an unclosed ' or " span.\"\"\"
    sq = dq = False
    i = 0
    while i < len(s):
        c = s[i]
        if c == "\\\\" and not sq:
            i += 2
            continue
        if c == "'" and not dq:
            sq = not sq
        elif c == '"' and not sq:
            dq = not dq
        i += 1
    return sq or dq


def main() -> None:
    try:
        d = json.load(sys.stdin)
        cmd = d.get("tool_input", {}).get("command") or ""
    except Exception:
        return
    if not cmd or "<<" in cmd:
        return
    hits = []
    for m in _HEAD.finditer(cmd):
        # Replace from the path prefix (if any) so /usr/bin/grep becomes
        # the wrapper wholesale, not /usr/bin/<wrapper>.
        start = m.start(2) if m.group(2) else m.start(3)
        if _in_open_quote(cmd[:start]):
            continue
        end = m.end(3)
        hits.append((start, end, m.group(3)))
    if not hits:
        return
    out = cmd
    for start, end, tok in reversed(hits):
        repl = RMXGREP if tok == "grep" else RMXRG
        out = out[:start] + repl + out[end:]
    sys.stdout.write(out)


if __name__ == "__main__":
    main()
"""

TEACH_TEMPLATE = """\
#!/usr/bin/env bash
# PostToolUse(Grep) teach ping — the dedicated Grep tool bypasses the Bash
# PreToolUse rewriter entirely, so those searches taught the graph nothing.
# This closes that channel the same way rmxgrep's plain mode does: a
# detached, throttled `rmx grep` with the same pattern, output discarded.
# Capture-only — never touches the tool's own result or timing.
#
# Same absolute-path discipline as grep-rewrite-guard.sh: internal tools by
# absolute path so shell aliases/functions can't alias them out from under us.

JQ=$(command -v jq 2>/dev/null); [ -x "$JQ" ] || JQ=/usr/bin/jq
RMX="${RMXGREP_RMX:-rmx}"
command -v "$RMX" >/dev/null 2>&1 || exit 0

INPUT=$(cat)
PATTERN=$(printf '%s' "$INPUT" | "$JQ" -r '.tool_input.pattern // empty' 2>/dev/null)
[ -z "$PATTERN" ] && exit 0
DIR=$(printf '%s' "$INPUT" | "$JQ" -r '.tool_input.path // .cwd // empty' 2>/dev/null)
[ -d "$DIR" ] || DIR=$(printf '%s' "$INPUT" | "$JQ" -r '.cwd // empty' 2>/dev/null)
[ -d "$DIR" ] || exit 0

# Only inside an rmx project.
root=""; d="$DIR"
while [ -n "$d" ] && [ "$d" != "/" ]; do
    [ -d "$d/.refmatrix" ] && { root="$d"; break; }
    d="${d%/*}"
done
[ -z "$root" ] && exit 0

# Throttle: one ping per pattern per TTL (default 5 min), same stamp scheme
# as the rmxgrep wrappers.
ttl="${RMXGREP_TEACH_TTL_MIN:-5}"
stampdir="$root/.refmatrix/.rmxgrep-teach"
stamp="$stampdir/$(printf 'tool:%s' "$PATTERN" | cksum | tr ' \\t' '__')"
if [ -z "$(find "$stamp" -mmin "-$ttl" 2>/dev/null)" ]; then
    mkdir -p "$stampdir" 2>/dev/null
    : > "$stamp" 2>/dev/null
    # Grep-tool patterns are rg-dialect regex → -E.
    ( cd "$root" && exec "$RMX" grep -E --limit 3 "$PATTERN" >/dev/null 2>&1 ) &
    disown 2>/dev/null
fi
exit 0
"""


def hooks_dir() -> Path:
    """User-global Claude hooks dir. RMX_CLAUDE_HOOKS_DIR overrides (tests)."""
    return Path(os.environ.get(
        "RMX_CLAUDE_HOOKS_DIR", str(Path.home() / ".claude" / "hooks")))


def wrapper_paths() -> "tuple[str, str]":
    """(rmxgrep, rmxrg) absolute paths: PATH first, else this package's
    repo bin/ (editable installs), else the bare names as a last resort."""
    out = []
    pkg_bin = Path(__file__).resolve().parents[2] / "bin"
    for name in ("rmxgrep", "rmxrg"):
        p = shutil.which(name)
        if not p and (pkg_bin / name).exists():
            p = str(pkg_bin / name)
        out.append(p or name)
    return out[0], out[1]


def render_scripts(wrappers: "tuple[str, str] | list | None" = None) -> "dict[str, str]":
    """name -> rendered content, wrapper + rewriter paths baked in.
    `wrappers` = (rmxgrep, rmxrg) paths to bake; default = this process's
    `wrapper_paths()`. `check()` passes the paths recorded at apply time so
    the comparison does not depend on which venv renders it."""
    rmxgrep, rmxrg = tuple(wrappers) if wrappers else wrapper_paths()
    rewriter = str(hooks_dir() / REWRITER_NAME)
    return {
        GUARD_NAME: GUARD_TEMPLATE.replace("@REWRITER@", rewriter),
        REWRITER_NAME: (REWRITER_TEMPLATE
                        .replace("@RMXGREP@", rmxgrep)
                        .replace("@RMXRG@", rmxrg)),
        TEACH_NAME: TEACH_TEMPLATE,
    }


def search_hook_block() -> dict:
    """Merge-ready settings hooks block wiring the two hook events."""
    d = hooks_dir()
    return {"hooks": {
        "PreToolUse": [{"matcher": "Bash", "hooks": [
            {"type": "command", "command": str(d / GUARD_NAME)}]}],
        "PostToolUse": [{"matcher": "Grep", "hooks": [
            {"type": "command", "command": str(d / TEACH_NAME),
              "timeout": 5000}]}],
    }}


def install_search_hooks(project_root: Path, scope: str,
                         apply: bool, force: bool) -> "list[str]":
    """Write the three scripts (user-global) + wire the settings block."""
    out: "list[str]" = []
    d = hooks_dir()
    for name, content in render_scripts().items():
        target = d / name
        if target.exists():
            if target.read_text() == content:
                out.append(f"[dim]ok[/] {target} (current)")
                continue
            if not force:
                out.append(f"[yellow]skip[/] {target} (differs; --force overwrites)")
                continue
            out.append(f"[green]overwrite[/] {target}")
        else:
            out.append(f"[green]write[/] {target}")
        if apply:
            d.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
            target.chmod(target.stat().st_mode | stat.S_IEXEC
                         | stat.S_IXGRP | stat.S_IXOTH)

    block = search_hook_block()
    if scope == "user":
        out.append("[bold]search hooks (user scope)[/] — merge into ~/.claude/settings.json:")
        out.append(json.dumps(block, indent=2))
        return out

    # Same committed file the rmx block lives in (hooks.py) — one author.
    target = project_root / ".claude" / "settings.json"
    existing: dict = {}
    if target.exists():
        try:
            existing = json.loads(target.read_text())
        except json.JSONDecodeError:
            out.append(f"[red]warn[/] {target} is not valid JSON; skipping search-hook wiring")
            return out
    merged = {**existing}
    merged.setdefault("hooks", {})
    d_str = str(d)
    changed = False
    for event, entries in block["hooks"].items():
        cur = merged["hooks"].setdefault(event, [])
        # Idempotent: one entry per script path; --force refreshes in place.
        if force:
            cur[:] = [e for e in cur if not any(
                (h.get("command") or "").startswith(d_str + "/")
                and (h.get("command") or "").rsplit("/", 1)[-1] in
                (GUARD_NAME, TEACH_NAME)
                for h in e.get("hooks", []))]
        already = any(
            (h.get("command") or "").rsplit("/", 1)[-1] in (GUARD_NAME, TEACH_NAME)
            for e in cur for h in e.get("hooks", []))
        if not already:
            cur.extend(entries)
            changed = True
    if changed or force:
        out.append(f"[green]write[/] {target} (search hooks)")
        if apply:
            target.parent.mkdir(exist_ok=True)
            target.write_text(json.dumps(merged, indent=2))
    else:
        out.append(f"[dim]ok[/] {target} (search hooks present)")
    return out
