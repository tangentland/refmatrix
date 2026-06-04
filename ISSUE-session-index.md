# Session Index — design plan

Index past Claude Code sessions for search. Sessions = `~/.claude/projects/<slug>/*.jsonl`.

## Goals

- `rmx session recall "<query>"` → ranked list of past sessions touching the topic.
- `rmx session show <id>` → load the raw JSONL.
- Filter by project, branch, date range, commit, file path.
- Cheap ingest (no LLM, no embeddings). Cheap storage (cards, not turns).
- Cross-partition queries should NOT pollute code/memory results with session noise.

## Non-goals

- Dense embeddings over sessions (low signal, high cost — confirmed in earlier discussion).
- Indexing tool I/O bodies (huge, repetitive, low-information).
- Real-time mid-session indexing. End-of-session is fine.
- Editing or summarizing transcripts with an LLM. Heuristic extraction only.

## Architecture

**Session card model.** Each session JSONL → one GMD card. Cards land in a dedicated partition `sessions-<project>`. Raw JSONL stays on disk; card stores `source_path` pointer.

**No dense pipeline.** Sessions partition is symbolic-only:
- BM25 over card body
- LIKE/regex on extracted concepts (commit shas, file paths, branch names)
- recency-weighted score (`created_at DESC` × bm25)

Reuses existing engine but skips the embedder.

## Schema — session card

GMD doc, one per session. Stored on disk at `~/.refmatrix/sessions/<project>/<session-id>.md`.

```yaml
---
gmd: "0.1"
id: session-<uuid8>
title: "<derived from first user prompt, 80 chars max>"
tags: [session, <project>]
metadata:
  node_type: session
  type: session
  session_id: <full-uuid>
  project: <project-slug>
  source_path: /Users/tholley/.claude/projects/<encoded>/<uuid>.jsonl
  started: <ISO8601>
  ended: <ISO8601>
  turn_count: <int>
  user_prompt_count: <int>
  branch: <git-branch-at-end>
  commits: [<sha>, ...]      # commits authored during session
  files_touched: [<path>, ...] # from Edit/Write tool calls
  models_used: [<model-id>, ...]
---

# <title> {#root}

## User prompts {#prompts}

- <prompt 1, truncated to 300 chars>
- <prompt 2>
...

## Assistant decisions {#decisions}

<assistant final-text turns, joined; filtered to remove pure tool-use turns>

## Activity {#activity}

- Branch: <branch>
- Commits: <sha1>, <sha2>
- Files: <path>, <path>
- Tools: <tool counts, e.g. Edit:14, Bash:8, Read:23>
```

## Filter rules — what enters the card

| JSONL field | Action |
|-------------|--------|
| `type: "user"` text content | KEEP (user prompts) |
| `type: "assistant"` text blocks | KEEP (decisions, explanations) |
| `type: "assistant"` tool_use blocks | EXTRACT name + path/cmd; drop params body |
| `type: "user"` tool_result blocks | DROP body; KEEP error indicator + tool name |
| System messages, system reminders | DROP |
| Hook output, slash-command stdout | DROP |
| Thinking blocks | DROP |

Dedup pass: consecutive identical turns (e.g. retry loops) collapse to one with `×N` marker.

## CLI surface

```
rmx session ingest [PATH] [--project <slug>] [--since <date>] [--force]
    # PATH defaults to ~/.claude/projects; recursive scan
    # --force reingests cards even if hash matches

rmx session recall <query> [--project <slug>] [--branch <name>]
                          [--commit <sha>] [--touched <path>]
                          [--since <date>] [--until <date>]
                          [--k 20] [--json]
    # BM25 + recency. No dense. Returns session cards.

rmx session show <session-id-or-prefix> [--raw|--card|--turns]
    # --card: rendered card markdown
    # --raw:  raw JSONL path (for $EDITOR)
    # --turns: pretty-print turns (filtered, same rules as card)

rmx session list [--project <slug>] [--since <date>] [--limit 50]
    # paginated index; sorted by ended DESC

rmx session stats [--project <slug>]
    # turn counts, model breakdown, commit volume, top topics
```

## Daemon ops (new)

Register in `daemon.py:2506 OPS`:
- `session_ingest` → `_op_session_ingest(args)` — drives the JSONL → card pipeline
- `session_recall` → `_op_session_recall(args)` — BM25 + filters

Reuse existing:
- `query` / `grep_indexed` already cover symbolic search inside the new partition
- `with_partition()` context manager handles partition isolation

CLI_OPS membership: `session_recall` yes (read), `session_ingest` no (background tick OK).

## Auto-ingest — backfill via launchd

No hook integration. Ingest runs as a periodic launchd job — walks `~/.claude/projects/*`, ingests any JSONL whose mtime > last-ingested-mtime (or hash differs). Eventual consistency, decoupled from session lifecycle.

Reuse existing refmatrix launchd supervisor pattern (`project_launchctl_supervisor_shipped`). New plist:

```
~/Library/LaunchAgents/com.refmatrix.session-indexer.plist
  ProgramArguments: rmx session ingest ~/.claude/projects --since-last-run
  StartInterval: 600    # every 10 minutes
```

For manual / immediate ingest of one session, CLI accepts `--session <id>` (reads stdin JSON payload format too, future-compatible with hook re-introduction):

```
rmx session ingest --stdin-json     # parses {session_id: "..."} from stdin
rmx session ingest --session <uuid> # explicit id
```

Cold-start backfill: same command without filter walks everything, hash-skips already-indexed sessions.

## File layout

New files:
- `src/refmatrix/session_ingest.py` — JSONL parser + filter + card writer + slug resolver (cwd → dir-decode fallback)
- `src/refmatrix/session_cli.py` — Click group (or embed in cli.py if small)
- `packaging/launchd/com.refmatrix.session-indexer.plist.template` — launchd backfill ticker

Modified:
- `src/refmatrix/cli.py` — register `session_grp`; add `SESSIONS_PARTITION_PREFIX = "sessions-"` near `MEMORY_PARTITION_PREFIX`
- `src/refmatrix/daemon.py` — register two new ops (`session_ingest`, `session_recall`)
- `src/refmatrix/ingest_gmd.py` — `as_session=True` parallel to `as_memory=True`

No schema migrations — cards are GMD docs ingested via existing `ingest_gmd_paths()` with new `as_session=True` flag (parallel to `as_memory=True`).

## Phase plan

**Phase A — card pipeline (no CLI, no daemon):** ✅ SHIPPED (c8ece04)
1. `session_ingest.py`: parse one JSONL → card markdown. Unit test on a fixture session.
2. Filter rules + dedup pass. Snapshot test.
3. Write card to `<root>/sessions/<id>.md`.

**Phase B — ingest into refmatrix:** ✅ SHIPPED (0.3.33)
4. Reused existing `ingest_gmd_paths(as_memory=True)` with `memory_mtype="session"` — no `ingest_gmd.py` changes needed. Cleaner than the originally-planned `as_session=True` flag.
5. `rmx session ingest [PATH]` CLI: default scopes to cwd's matching Claude Code project dir; `--all-projects` for full walk; `--no-index` for card-only preview; `--force` for rebuild; hash-skip for unchanged sessions.

**Phase C — retrieval:** ✅ SHIPPED (0.3.34)
6. `rmx session recall <query>` — BM25 over sessions partition with filters (--project, --branch, --commit, --touched, --since, --until). Recency-sorted when no query.
7. `rmx session show <id>` — three modes (--card / --raw / --turns). Accepts full uuid or 8-char prefix.
8. `rmx session list` + `rmx session stats` — paginated index + aggregate (turn count, top files, branches, models).

Implementation note: list-valued metadata (commits, files_touched, models_used) survives ingest as JSON-string blobs because the `--as-memory` ingest path's frontmatter parser doesn't unwrap nested YAML lists. Added `_session_meta_list()` helper to deserialize at read time. A cleaner long-term fix would be to teach `ingest_gmd.py:583` to JSON-decode list-shaped values, but that's a behaviour change for the existing memory ingest path and out of scope here.

**Phase D — automation:** ✅ SHIPPED (0.3.34)
9. `src/refmatrix/session_launchctl.py` + `rmx session launchctl install/uninstall/status` CLI. Per-store plist with StartInterval (default 600s), no KeepAlive (one-shot ingest tick). Distinct label prefix `com.refmatrix.session-indexer.<slug>-<hash>` so it coexists with the daemon LaunchAgent.
10. Cold-start backfill: `rmx session ingest --all-projects` walks every project under `~/.claude/projects/`; hash-skips unchanged sessions. Available standalone or via the LaunchAgent's `--all-projects` flag.

Ship A+B first (one release). Then C+D (one release combining retrieval + automation).

## Resolved decisions

1. **Project slug** — prefer `cwd` field from first JSONL turn; fall back to dir-name decode (strip leading `-`, `-`→`/`). Both paths in `session_ingest.py:_resolve_project_slug()`.
2. **Auto-ingest** — backfill-only via launchd ticker (every 10 min). No hook integration. Decouples ingest from session lifecycle, no `SessionEnd` dependency.
3. **Card storage** — per-project: `<project>/.refmatrix/sessions/<session-id>.md`. Matches existing partition-per-project model.
4. **Session id source** — stdin JSON payload (`{session_id: "..."}`) for `--stdin-json` mode; `--session <uuid>` explicit. Forward-compatible with future hook re-introduction. No env-var dependency.

## Out of scope (later)

- Cross-session topic clustering ("show me all sessions about the daemon shutdown bug")
- Session → memory promotion (mark a session-card as memory-worthy)
- Replay / restore from a session
- Privacy filtering (redact secrets in card body)
