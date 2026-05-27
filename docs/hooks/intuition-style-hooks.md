# Intuition-style Claude Code hooks (Phase C3)

Copy-pasteable `.claude/settings.local.json` snippets that port
intuition's hook surface onto `rmx memory`. Each section drops into
the matching event in your project's `.claude/settings.local.json`.

These are **templates**, not auto-installed — paste only the hooks
your project wants. All of them shell out to the `rmx` CLI, so the
project must have `rmx` on `$PATH` and an initialized `.refmatrix/`
store somewhere in scope (the memory partition defaults to
`intuition`; override with `RMX_PARTITION` or `-p`).

## TL;DR

| Event | Shell call | Purpose |
|---|---|---|
| `SessionStart` | `rmx -p intuition memory recall --session-start --json` | Inject the top-k recent memories at session boot |
| `UserPromptSubmit` | `rmx memory recall --stdin-json --k 5 --json` | Pull memories matching the user's prompt (reads the hook's stdin JSON envelope natively) |
| `PreCompact` | `rmx -p intuition memory recall --recent --since 1h --json` | Surface this session's recent observations before compaction |
| `Stop` | (out of scope — Phase C4) | Auto-capture session observations as memories |

`--json` makes the output friendlier for piping into your prompt
context; drop it for human-readable Rich tables.

**No silent failures.** These templates intentionally do NOT
`2>/dev/null` or `|| true` — memory is critical and broken state
must surface immediately. The trade-off is that a missing rmx
binary or a down daemon will print errors into the hook output.
That's the correct behavior; fix the cause, not the symptom. If
you're shipping rmx-optional tooling, gate the hook on `command -v
rmx` instead of masking failures.

## SessionStart — inject recent memories

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

## UserPromptSubmit — recall on every prompt

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

## PreCompact — surface this session's observations

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

## Stop — auto-capture (Phase C4, deferred)

ADR-0001 Phase C originally planned a `Stop` hook that runs
`rmx memory add --auto-extract` to capture session observations as
memories. Auto-extraction needs an LLM call to summarize the
transcript, so it's been deferred to **Phase C4 (not yet shipped)**.

For now, capture observations explicitly via:

```bash
rmx memory add <slug> -c "..." --type observation --tags ...
```

Or pair `rmx memory add` with the user-issued `/remember` flow if
your harness has one.

## Cleaning up the intuition wiring

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

## Why rmx ships no MCP server

ADR-0001 is explicit: `rmx` is CLI-only. Hooks shell out to `rmx`
directly, no MCP layer. This keeps the surface small + scriptable +
easy to audit; agents already know how to drive subprocesses.

If you need MCP for a particular agent that can only consume MCP
tools, wrap `rmx` in your own thin shim — it's not in-tree.
