# refmatrix — Integration Guide

This document covers every place refmatrix touches something outside itself:
external CLIs it shells out to, hooks it installs into git and Claude Code,
file formats it consumes (tldr cache, GMD, ADR markdown), the daemon socket
protocol, and the file watcher.

## External tool dependencies

| Tool       | Required? | Used for                                              | Source                          |
|------------|-----------|-------------------------------------------------------|---------------------------------|
| `git`      | Optional  | `rmx sync --since <ref>`, git post-* hooks            | `sync.py:82-84`, `hooks.py`     |
| `rg`       | Optional  | `rmx grep` fallback (preferred over grep)             | `cli.py:931-941`                |
| `grep`     | Fallback  | `rmx grep` when rg unavailable                        | `cli.py:931-941`                |
| `llm-tldr` | Optional  | `rmx tldr-warm` → semantic + call-graph extraction    | `cli.py:1401-1427`              |

Python deps (`pyproject.toml`):

| Package      | Why                                              | Required group   |
|--------------|--------------------------------------------------|------------------|
| `pyroaring`  | `BitMap64` storage for linkage fragments         | core             |
| `click`      | CLI framework                                    | core             |
| `rich`       | Terminal tables / progress                       | core             |
| `duckdb`     | Native catalog backend (phase 3)                 | core             |
| `pyarrow`    | DuckDB interop                                   | core             |
| `llm-tldr`   | Subprocess shim for `rmx tldr-warm`              | optional `[tldr]`|
| `watchdog`   | Filesystem observer for `rmx watch` / daemon     | optional `[watch]`|

Install with optional groups: `pip install -e '.[tldr,watch,dev]'`.

## Composing with `llm-tldr`

`llm-tldr` is the per-function extractor; refmatrix is the cross-entity
indexer and query layer. Integration is one-way: refmatrix reads tldr's
on-disk cache. tldr is not aware of refmatrix.

### Cache surface refmatrix consumes

| File                                         | Used as                                | Reader                                  |
|----------------------------------------------|----------------------------------------|-----------------------------------------|
| `.tldr/cache/semantic/metadata.json`         | Richest: per-unit signature, docstring, code preview, CFG/DFG summary, unit_type, language | `ingest.py:_ingest_tldr_metadata` |
| `.tldr/cache/call_graph.json`                | Leaner: `(from_file, from_func) → [callees]`                          | `ingest.py:_ingest_tldr`               |

### Source priority (`ingest.py:40-48`)

```
metadata.json  ↘
                → ingest_path() picks first available
call_graph.json  →
                ↗
filesystem      → fallback (tree walk, file-level only)
```

Force a specific source: `rmx ingest . --source metadata|tldr|tree`.

### Subprocess invocation

| Command          | Invokes                                                |
|------------------|--------------------------------------------------------|
| `rmx tldr-warm`  | `tldr warm <path> [--lang <lang>]` then `ingest_path(..., source="tldr")` |

`tldr-warm` is the recommended onboarding command for an unindexed project:
it warms the cache, then ingests in one shot. After that, the sync layer
keeps things current incrementally.

### How refmatrix extends what tldr provides

| Layer                       | Provided by tldr                          | Added by refmatrix                                  |
|-----------------------------|-------------------------------------------|-----------------------------------------------------|
| Per-function extraction     | ✓ signatures, docstrings, CFG/DFG         | (consumed verbatim into `entities.meta` blob)       |
| Call graph                  | ✓ `(caller, callee)` pairs                | Indexed as `calls` / `called_by` linkage bitmaps    |
| Import analysis             | partial (some langs)                      | Python AST imports (`_ingest_python_semantics`)     |
| Docstring keyword indexing  | ✗                                         | `mentions` linkages from docstring tokens           |
| Markdown semantics          | ✗                                         | H1/H3 PascalCase + fenced class specs → `defines`   |
| ADR-aware extraction        | ✗                                         | ADR class specs, ADR-NNNN xrefs → `defines`, `related_to` |
| Plan/spec/issue extraction  | ✗                                         | `specifies` linkages from `PLAN|ISSUE|SPEC|ROADMAP` files and `plans/`, `specs/`, `issues/`, `roadmap/` dirs |
| Graph Markdown (GMD)        | ✗                                         | Full GMD spec parser: `rel:` typed edges, frontmatter, `{#id}` anchors, `[[wikilinks]]` |
| Pseudocode parsing          | ✗                                         | `.pseudo` file type/func extraction (`is_a`, `defines`) |
| Cross-codebase canon links  | ✗                                         | Per-partition concept → canonical concept           |

## Claude Code integration

### Hook events installed

`rmx install-hooks` writes a JSON block into `.claude/settings.local.json`
(project-local) or `~/.claude/settings.json` (user-global, with `--user`).

| Hook event                          | Matcher (tools)                          | Command                                  | Purpose                                       |
|-------------------------------------|------------------------------------------|------------------------------------------|-----------------------------------------------|
| `PostToolUse`                       | `Edit\|Write\|MultiEdit\|NotebookEdit`   | `rmx sync --enqueue-only`                | Append touched paths to `dirty.queue`         |
| `Stop`                              | (all)                                    | `rmx sync --flush-queue` (async)         | Drain queue when conversation ends            |
| `SubagentStop`                      | (all)                                    | `rmx sync --flush-queue` (async)         | Drain queue when subagent ends                |
| `SessionStart`                      | `startup\|resume`                        | `rmx sync --flush-queue` + `rmx primer`  | Flush + regenerate `PRIMER.md`                |
| `UserPromptSubmit`                  | (all)                                    | `rmx scan-prompt --max-tokens 2000`      | Inject context bundles for mentioned symbols  |

### Briefing doc

`rmx install-hooks` also writes `.refmatrix/CLAUDE.md` — a briefing for
agents working in the project. It's not overwritten by default; suggested
usage is to add `@.refmatrix/CLAUDE.md` to the project's top-level
`CLAUDE.md`.

### `scan-prompt` — agent context injection

When the `UserPromptSubmit` hook fires, `rmx scan-prompt` tokenizes the
prompt, matches symbol-shape tokens against indexed concepts, fuses
top hits via RRF, and emits a token-budgeted context bundle. The bundle
is injected as additional context for the model on that turn.

## Git integration

### Hooks installed (`hooks.py:23-59`)

| Hook              | Command                                            | Trigger                                    |
|-------------------|----------------------------------------------------|--------------------------------------------|
| `post-commit`     | `rmx sync --since HEAD~1`                          | Every commit                               |
| `post-merge`      | `rmx sync --since ORIG_HEAD`                       | After merge                                |
| `post-checkout`   | `rmx sync --since $1..$2` (only when `$3 == 1`)    | Branch switch (not file checkout)          |
| `post-rewrite`    | `rmx sync --since <oldest pre-rewrite OID>`        | After rebase / amend                       |

All hooks run `rmx` in the background so they don't block the git operation.

### `rmx sync --since <ref>`

Calls `git diff --name-only <ref>` to get the changed-file list, then
re-ingests just those paths. Incremental: files whose mtime equals
`tracked_files.mtime` are skipped (`sync.py:129-140`).

## GMD (Graph Markdown) integration

GMD is a spec for markdown documents that carry typed relations and stable
addressability — designed to replace plain markdown in `CLAUDE.md`, `SKILL.md`,
memory files, notes. Spec lives at `../gmd/SPEC.md`.

### What refmatrix's GMD ingestor (`ingest_gmd.py`) accepts

| Input syntax                                  | Becomes                                                       |
|-----------------------------------------------|---------------------------------------------------------------|
| `gmd:` frontmatter                            | doc-level entity (`kind=doc`)                                 |
| `{#id}` block anchor                          | concept entity (with `/` allowed for hierarchy — spec §3)     |
| `rel: <verb> -> <target>`                     | linkage edge (auto-creates verb type if not registered)       |
| `rel: <verb> -> <target> {weight=0.8}`        | weighted linkage                                              |
| Heading hierarchy (CommonMark)                | `part-of` linkages on direct parents                          |
| `[[#section-id]]`                             | intra-doc reference                                           |
| `[[doc-id#section-id]]`                       | cross-doc reference                                           |
| `[[ref]]` outside `rel:` lines                | `mentions` linkage on resolved target                         |
| Frontmatter `imports: [a, b]`                 | `imports` linkage on doc-level entity                         |
| Frontmatter `id:`, `title:`, `tags:`, `alias` | entity attributes                                             |

### Verb policy

- Spec §8 recommends an open vocabulary: `supports`, `contradicts`,
  `derives-from`, `supersedes`, `depends-on`, `instance-of`, `part-of`,
  `mentions`, `defines`, `example-of`.
- Authors MAY use any kebab-case verb. refmatrix auto-creates the linkage
  type on first encounter (`daemon.py:_op_add_linkage_type` /
  `ingest_gmd.py:_ensure_linkage`).
- Pre-registered verbs (with inverses) live in `store.py:DEFAULT_LINKAGES`.

### Recent extensions

- `_ID_RE` now allows `/` in IDs (`ingest_gmd.py:30`), matching spec §3's
  `[a-z0-9][a-z0-9._/-]*` so hierarchical IDs like `project/foo` parse.
- `specifies` + `specified_by` registered in `DEFAULT_LINKAGES` so author
  GMD `rel: specifies -> [[#X]]` and rmx's plan-doc heuristic produce the
  same edge type.

## File watcher integration

### Backend

[watchdog](https://github.com/gorakhargosh/watchdog) (optional dep, install
with `pip install -e '.[watch]'`).

### Behavior (`watch.py`)

| Concern              | Value                                                                |
|----------------------|----------------------------------------------------------------------|
| Root                 | `project_root` (recursive)                                           |
| Events monitored     | `on_created`, `on_modified`, `on_deleted`, `on_moved`                |
| Relevant extensions  | `CODE_EXTS ∪ DOC_EXTS` (defined in `watch.py:26-40`)                 |
| Ignored directories  | `.git`, `.venv`, `venv`, `node_modules`, `.tldr`, `.refmatrix`, `__pycache__`, `.mypy_cache`, `.pytest_cache`, `.ruff_cache`, `dist`, `build`, `.tox`, `.nox` |
| Debounce             | Configurable window (default 500ms); coalesces bursts into one batch |
| Handler              | Calls `sync_files(paths, semantic=True)` on the coalesced batch      |

### Embedded vs standalone

- **Standalone**: `rmx watch` runs the observer in the foreground (good for
  debugging).
- **Embedded**: `rmx daemon start` runs the same observer on a worker thread
  inside the daemon (`daemon.py:_start_watcher`). This is the production
  path — single process owns the catalog lock AND the watcher.

## Daemon socket protocol

The daemon listens on `.refmatrix/rmxd.sock` (Unix socket). Protocol is
**newline-delimited JSON** — one JSON object per line, request and response.

### Wire format

```json
// request
{"op": "query", "args": {"expr": "defines:parser", "limit": 50}}

// response (success)
{"ok": true, "result": {"rows": [...], "cardinality": 42}}

// response (error)
{"ok": false, "error": "unknown linkage: foobar"}
```

### Client API (`daemon.py:72-99`)

```python
from refmatrix.daemon import ping, call

if ping(project_root):                           # health check
    result = call(project_root, "query", expr="defines:auth")
else:
    # fall back to opening Store directly
    ...
```

### Op inventory

See `ARCHITECTURE.md § Daemon / concurrency layer` for the full 21-op table.

### Concurrency model

The daemon is single-threaded for catalog ops (Store is not thread-safe).
The watcher runs on a worker thread but routes through the same socket to
the main thread so all Store access is serialized. `flush_queue_async`
breaks this rule deliberately: it returns immediately to the client and
processes the queue on a background thread. Acceptable because (a) the
client doesn't need the result and (b) the only writer is still the
daemon's main loop, just shifted in time.

## CLI surface (top-level)

```
rmx
├── init                       create .refmatrix/ in cwd
├── info                       print store metadata
├── daemon start|stop|status   per-store daemon lifecycle
├── partition list|add         multi-codebase shared catalog
├── canon link|siblings        cross-partition canonicalization
├── add entity|concept|linkage-type
├── list entities|linkages|queries
├── link / unlink
├── query                      DSL set algebra
├── neighbors                  walk linkages
├── context                    token-budgeted bundle (--since <ref> also)
├── co-occur                   co-mention analysis
├── grep                       index-backed + rg/grep fallback + learn-on-miss
├── top                        top-N concepts by density
├── save-query / run
├── stats / telemetry
├── ingest                     --source metadata|tldr|tree --semantic
├── tldr-warm                  shell out to llm-tldr, then ingest
├── ingest-gmd                 GMD-specific ingest
├── sync                       --files / --since / --flush-queue / --enqueue-only / --invalidate
├── queue                      list pending dirty.queue
├── watch                      foreground filesystem watcher
├── primer                     density-ranked PRIMER.md
├── scan-prompt                UserPromptSubmit hook target
├── install-hooks              install git + Claude Code hooks
├── compact                    DuckDB EXPORT / IMPORT to reclaim space
├── checkpoint                 DuckDB WAL flush + index rebuild
├── vacuum                     drop zero-linkage concepts + stale tracked_files
├── prune-noise                mark/drop concepts by DF thresholds
├── export / import            JSON dump / restore
├── dump-log / rebuild         rebuild bitmaps from append-only log
└── migrate-to-duckdb          one-shot SQLite → DuckDB native catalog
```

## Onboarding checklist for a new project

```bash
cd my-project
git init                              # if not already
pip install llm-tldr                   # optional but recommended
pip install '<refmatrix-path>[tldr,watch]'

rmx init                              # creates .refmatrix/
rmx daemon start                      # owns the catalog + embeds watcher
rmx tldr-warm . --semantic            # llm-tldr + ingest in one shot
rmx install-hooks                     # git + Claude Code hooks
rmx primer                            # writes .refmatrix/PRIMER.md
rmx query "defines:<your_main_concept>"
```

From this point on, edits trigger incremental sync automatically via either
the file watcher (running in the daemon) or the Claude Code `PostToolUse`
hook. No manual `rmx ingest` needed unless you import data from outside the
project tree.
