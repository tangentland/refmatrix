---
gmd: "0.1"
id: intuition-style-hooks
title: "Intuition-style Claude Code hooks (Phase C3)"
tags: [hooks, memory, claude-code, templates]
---

# Intuition-style Claude Code hooks (Phase C3) {#root}

rel: implements -> [[0001-intuition-lance-integration]]

Reference snippets that port intuition's hook surface onto `rmx memory`.
Since 0.67 these are NOT pasted by hand: `rmx install-hooks --apply` generates
the whole block into the committed `.claude/settings.json` (memory hooks on by
default; `--no-memory-hooks` opts out), and `rmx install-hooks --check` proves
the installed file still equals the generator's render. Read this doc to
understand each event; edit `hooks.py:_claude_hook_block` to change one. All of them shell out to the `rmx` CLI, so the
project must have `rmx` on `$PATH` and an initialized `.refmatrix/`
store somewhere in scope (the memory partition defaults to
`intuition`; override with `RMX_PARTITION` or `-p`).

## TL;DR {#tl-dr}

| Event | Shell call | Purpose |
|---|---|---|
| `SessionStart` | `rmx -p intuition memory recall --session-start --json` | Inject the top-k recent memories at session boot |
| `UserPromptSubmit` | `rmx memory recall --stdin-json --k 5 --json` | Pull memories matching the user's prompt (reads the hook's stdin JSON envelope natively) |
| `PreCompact` | `rmx -p intuition memory recall --recent --since 1h --json` | Surface this session's recent observations before compaction |
| `Stop` | `rmx focus summarize --promote --timeout 5` | Graduate the turn's STM digest to durable memory (bounded; a busy daemon skips loudly) |

`--json` makes the output friendlier for piping into your prompt
context; drop it for human-readable Rich tables.

**No silent failures.** These templates intentionally do NOT
`2>/dev/null` or `|| true` — memory is critical and broken state
must surface immediately. The trade-off is that a missing rmx
binary or a down daemon will print errors into the hook output.
That's the correct behavior; fix the cause, not the symptom. If
you're shipping rmx-optional tooling, gate the hook on `command -v
rmx` instead of masking failures.

## SessionStart — inject recent memories {#sessionstart-inject-recent-memories}

Run on session startup and on `/clear`. Pulls the 10 most recent
memories from the last 7 days. The shell output is appended to
Claude's context.

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|resume|clear",
        "hooks": [
          {
            "type": "command",
            "command": "rmx -p intuition memory recall --session-start --k 10 --json",
            "timeout": 10,
            "statusMessage": "Recalling recent memories..."
          }
        ]
      }
    ]
  }
}
```

## UserPromptSubmit — recall on every prompt {#userpromptsubmit-recall-on-every-prompt}

Looks up memories whose content + linked concepts match the user's
prompt. Returns top-5 by hybrid score (dense ANN if `[dense]` is
installed, falls back to symbolic).

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "rmx memory recall --stdin-json --k 5 --json",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

Claude Code passes the UserPromptSubmit envelope on stdin as JSON
(`{"prompt": "...", "session_id": "...", ...}`). `--stdin-json`
parses it natively, so the hook is one line with no `jq` or
`python -c` dependency. An empty prompt (e.g. /clear or /resume
events that fire UserPromptSubmit with no user-typed text) is a
no-op exit 0 — only genuine failures (broken store, daemon
mismatch) surface.

## PreCompact — surface this session's observations {#precompact-surface-this-session-s-observations}

Before context compaction kicks in, dump the last hour of memories
into the surviving context so the compactor can keep the freshest
observations intact.

```json
{
  "hooks": {
    "PreCompact": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "rmx -p intuition memory recall --recent --since 1h --k 20 --json",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

## Stop — STM promote (shipped 0.67.0) {#stop-auto-capture-phase-c4-deferred}

The generator emits three Stop entries: a background `rmx sync --flush-queue --async`, a
`rmx focus hook --event say` capture of the assistant's last message into STM, and
`rmx focus summarize --promote --timeout 5`, which condenses the session's STM (topics,
milestones, intent arc, top symbols) into a `session/digest` memory through the daemon —
upserted by name, so it never grows the store. `--timeout 5` bounds the daemon write: on a busy
daemon the hook fails loud and the next PreCompact / `rmx save-state` promote catches up
(2026-09-14: unbounded, it held a turn for 55 s). The bound is a deadline for the whole
command — the subject filing that follows the promote gets only what is left of the 5 s, so
the worst case is one 0.5 s probe plus `--timeout` — and a daemon that is
alive but not answering is reported as `busy pid=N`, never as "not running". The PreCompact
promote is the catch-up, so its budget is longer but still a bound (`--timeout 30`): past it
rmx fails loud instead of Claude Code's 60 s hook limit ending it silently. There is no LLM-driven "auto-extract" step
and none is planned; observations worth keeping are written explicitly:

```bash
rmx memory add <slug> -c "..." --type observation --tags ...
```

## Cleaning up the intuition wiring {#cleaning-up-the-intuition-wiring}

If you're migrating off `~/claude_tools/intuition`, these steps
finish the cutover after `rmx memory import-sqlite` has migrated the
data:

1. **`.mcp.json`** — remove the `intuition` block from `mcpServers`.
2. **`.claude/settings.local.json`** —
   - drop `mcp__intuition__*` from `permissions.allow`.
   - drop `intuition` from `enabledMcpjsonServers`.
3. **Agent / CLAUDE.md** — rewrite any `mcp__intuition__*` tool
   references to the equivalent `rmx memory ...` invocations:
   - `mcp__intuition__observe`     → `rmx memory add ...`
   - `mcp__intuition__recall`      → `rmx memory recall --prompt ...`
   - `mcp__intuition__concepts`    → `rmx context <concept>` /
                                       `rmx grep-indexed <concept>`
4. **Archive intuition data** — already done as part of
   `rmx memory import-sqlite` (the `.memory.db*` files are moved
   into a sibling `.intuition-migrated/` directory on success).

## Why rmx ships no MCP server {#why-rmx-ships-no-mcp-server}

ADR-0001 is explicit: `rmx` is CLI-only. Hooks shell out to `rmx`
directly, no MCP layer. This keeps the surface small + scriptable +
easy to audit; agents already know how to drive subprocesses.

If you need MCP for a particular agent that can only consume MCP
tools, wrap `rmx` in your own thin shim — it's not in-tree.
