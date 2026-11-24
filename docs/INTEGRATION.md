---
gmd: "0.1"
id: refmatrix/INTEGRATION
title: "refmatrix — Integration Guide"
tags: [integration, hooks, gmd, daemon, watcher]
---

# refmatrix — Integration Guide {#root}

rel: related-to -> [[SYSTEM]]
rel: related-to -> [[ARCHITECTURE]]

This document covers every place refmatrix touches something outside itself:
external CLIs it shells out to, hooks it installs into git and Claude Code,
file formats it consumes (tldr cache, GMD, ADR markdown), the daemon socket
protocol, and the file watcher.

## External tool dependencies {#external-tool-dependencies}

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

## Composing with `llm-tldr` {#composing-with-llm-tldr}

`llm-tldr` is the per-function extractor; refmatrix is the cross-entity
indexer and query layer. Integration is one-way: refmatrix reads tldr's
on-disk cache. tldr is not aware of refmatrix.

### Cache surface refmatrix consumes {#cache-surface-refmatrix-consumes}

| File                                         | Used as                                | Reader                                  |
|----------------------------------------------|----------------------------------------|-----------------------------------------|
| `.tldr/cache/semantic/metadata.json`         | Richest: per-unit signature, docstring, code preview, CFG/DFG summary, unit_type, language | `ingest.py:_ingest_tldr_metadata` |
| `.tldr/cache/call_graph.json`                | Leaner: `(from_file, from_func) → [callees]`                          | `ingest.py:_ingest_tldr`               |

### Source priority (`ingest.py:40-48`) {#source-priority-ingest-py-40-48}

```
metadata.json  ↘
                → ingest_path() picks first available
call_graph.json  →
                ↗
filesystem      → fallback (tree walk, file-level only)
```

Force a specific source: `rmx ingest . --source metadata|tldr|tree`.

`--source` picks where CODE structure comes from. Markdown is not a code source: every
markdown file the ignore rules keep goes to the GMD pass (`ingest.py:_ingest_markdown_gmd`,
anchors and `rel:` edges) on every `rmx ingest` / `rmx reingest`, whatever the source and
whether or not a tldr cache answered (bug-241). A failed GMD pass is an `Error:` and a non-zero
exit, not a log line. `rmx ingest` takes a directory; a single file is refused with a pointer to
`rmx sync -f <file>` (bug-240).

### Subprocess invocation {#subprocess-invocation}

| Command          | Invokes                                                |
|------------------|--------------------------------------------------------|
| `rmx tldr-warm`  | `tldr warm <path> [--lang <lang>]` then `ingest_path(..., source="tldr")` |

`tldr-warm` is the recommended onboarding command for an unindexed project:
it warms the cache, then ingests in one shot. After that, the sync layer
keeps things current incrementally.

### How refmatrix extends what tldr provides {#how-refmatrix-extends-what-tldr-provides}

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

## Claude Code integration {#claude-code-integration}

### Hook events installed {#hook-events-installed}

`rmx install-hooks` writes the rmx hook block into the committed `.claude/settings.json`
(project scope; the per-machine `.claude/settings.local.json` keeps only the `env` block) or
prints a snippet for `~/.claude/settings.json` (`--scope user`). The block is GENERATED: the
generator flags are recorded in `.claude/rmx-hooks.json`, and `rmx install-hooks --check`
re-renders and diffs the installed file (exit 1 on drift). A hook that exists only in a settings
file is a template bug — promote it into `hooks.py` or delete it (constitution X).

| Hook event                          | Matcher (tools)                          | Command                                  | Purpose                                       |
|-------------------------------------|------------------------------------------|------------------------------------------|-----------------------------------------------|
| `PostToolUse`                       | `Edit\|Write\|MultiEdit\|NotebookEdit`   | `rmx sync --enqueue-only`                | Append touched paths to `dirty.queue`         |
| `Stop`                              | (all)                                    | `rmx sync --flush-queue` (async)         | Drain queue when conversation ends            |
| `SubagentStop`                      | (all)                                    | `rmx sync --flush-queue` (async)         | Drain queue when subagent ends                |
| `SessionStart`                      | `startup\|resume`                        | `rmx sync --flush-queue` + `rmx primer`  | Flush + regenerate `PRIMER.md`                |
| `UserPromptSubmit`                  | (all)                                    | `rmx scan-prompt --max-tokens 2000`      | Inject context bundles for mentioned symbols  |
| `PreCompact`                        | (all)                                    | `rmx save-state --precompact --no-sync --timeout N` | Save state + promote, then print the one-line summary instruction |
| `SessionStart`                      | `compact\|clear`                         | `rmx recall-state --handoff`             | Write the full handoff file, inject a pointer |
| `PreToolUse`                        | (all, MCP included)                      | `rmx handoff gate`                       | Deny other tools until the handoff is Read    |
| `PostToolUse`                       | `Read`                                   | `rmx handoff pulled`                     | A Read of the handoff lifts the gate          |
| `UserPromptSubmit`                  | (all)                                    | `rmx handoff remind`                     | Re-say the pointer until the handoff is Read  |

The full generated list is the README hooks table (`scripts/gen-cli-tree.py`).

### Hook writes enqueue and return {#hook-writes-queue}

The Stop hook's `rmx focus summarize --promote --timeout 8` and the save-state promote never
wait out a busy writer (task-hook-writes-queue, L212, bug-309: 72 of 136 Stop promotes timed out
on a held writer). One probe classifies the daemon:

- **up**: one `memory_add` dial, bounded by what is left of the budget minus 1 s;
- **busy**, or the dial times out: the digest, with the session's active subject, is written to
  `<store>/hook_writes.spool/` as one durable file. The hook prints `queued: <name>` and
  `daemon busy: queued <name> for the next drain; it is applied when the writer frees`, and
  exits 0. `rmx save-state` prints the same note in place of `promoted … (id=…)`. PreCompact
  reports the queued promote as a deferred store commit;
- **absent**: the Stop hook refuses (exit 1, nothing queued); save-state writes in-process as
  before. A spool that cannot take the entry exits 1 naming the path and the OS error.

The daemon drains the spool on its flush tick (`RMX_DAEMON_FLUSH_S`, 30 s) and once at boot.
Entries for one memory coalesce by authoring time, and `Store.add_memory(updated_at=)` skips
a write older than the stored row, so a timed-out dial that lands later and its queued entry
write once. An unreadable entry moves to `hook_writes.spool/bad/`. `rmx daemon status` prints a
`hook_writes:` line when entries are pending or bad; the health surface carries
`hook_writes_pending` and `hook_writes_bad`.

rel: implements -> [[task-hook-writes-queue]]

### Compaction and /clear as a handoff {#compaction-handoff}

Compaction behaves like save-state → `/clear` → recall-state (task-compaction-as-handoff, L195;
the user, 2026-11-14). No hook can suppress the compaction summary or trigger `/clear`, so:

- **PreCompact** runs `rmx save-state --precompact --timeout N`
  (`hooks.PRECOMPACT_SAVE_TIMEOUT_S`; the entry's Claude Code `timeout` sits above it). The
  session and transcript come from the hook envelope. The save goes in a fixed order: the
  `savestate_*.md` file and MEMORY.md go to disk first, then the store commit (the STM digest
  promote, a daemon write), the lint and the subject filing, within what is left of N. A commit
  that overruns is said on stderr as deferred; the file stays the durable record, and the
  daemon applies the queued write when the writer frees. Only then does stdout carry the
  instruction: at most one summary line naming the task, the handoff is authoritative, do not
  restate files, decisions or plans. It names the save-state and the handoff file. A failed
  save prints its cause on stderr, exits 0 and names the last good save-state. A manual
  `/compact <text>` saves and prints nothing. With `precompact_checkpoint` off the entry is
  `rmx handoff precompact` (no save).
- **SessionStart `compact|clear`** runs `rmx recall-state --handoff --max-bytes N`: the FULL
  report (a full one measured 45,870 B, over the ~10 KB hook cap) goes to
  `.refmatrix/handoffs/<session>.txt` and only a pointer is injected (path, bytes, "read it
  before any other action; it is the authoritative state"). If the file cannot be written, a
  line says so and the budgeted inline report follows.
- **The read gate**:
  - Until that file is Read (from its start), `rmx handoff gate` denies every other tool call
    of the session. The deny is JSON `permissionDecision: deny` at exit 0. The wrapper never
    passes exit 2 through, so a broken or older `rmx` allows the call, loudly.
  - `rmx handoff remind` re-says the pointer on every prompt.
  - `rmx handoff pulled` lifts the gate on the Read.
  - The gate never traps a session. A missing, unreadable or day-old file stands it down in one
    line, and so does a `handoffs/` dir it cannot write.
  - A bash fast path keeps the per-call cost at zero Python starts when nothing is pending.
    `REFMATRIX_ROOT` pins the command to the store the shell tested.
- **Subagents and teammates**: their hook input carries the lead's `session_id` plus
  `agent_id`. The handoff, the gate and the pull are the main thread's. A subagent's call is
  never denied, and its Read lifts nothing. Its compaction writes no handoff and arms nothing,
  and its PreCompact saves nothing and prints nothing, so Claude Code's own summary stands.
- **Reaping**: each handoff write reaps unread gates past their expiry, handoff files older
  than 7 days and their ledger rows (`RMX_HANDOFF_NOW` is the clock knob for tests).
- **The active goal** (R6): save-state reads the newest uncleared `/goal <text>` from the
  transcript into its `{#active-goal}` block; recall-state and the pointer carry
  `active goal: /goal <text>` with the instruction to re-issue it if a bare `/goal` shows none.
- **Telemetry**: `rmx telemetry --context` reports `handoff` (written, pulls with path, bytes and
  seconds to the Read, stand-downs, reaps) from `.refmatrix/handoffs/ledger.jsonl`.

rel: specified-by -> [[task-compaction-as-handoff]]

### Briefing doc {#briefing-doc}

`rmx install-hooks` also writes `.refmatrix/CLAUDE.md` — a briefing for
agents working in the project. It's not overwritten by default; suggested
usage is to add `@.refmatrix/CLAUDE.md` to the project's top-level
`CLAUDE.md`.

### `scan-prompt` — agent context injection {#scan-prompt-agent-context-injection}

When the `UserPromptSubmit` hook fires, `rmx scan-prompt` tokenizes the
prompt, matches symbol-shape tokens against indexed concepts, fuses
top hits via RRF, and emits a token-budgeted context bundle. The bundle
is injected as additional context for the model on that turn.

## Git integration {#git-integration}

### Hooks installed (`hooks.GIT_HOOK_SCRIPTS`) {#hooks-installed}

`rmx install-hooks --apply` writes these into `.git/hooks/` from `hooks.GIT_HOOK_SCRIPTS`
(`--force` replaces an existing hook).

| Hook              | Command                                                         | Trigger                                 |
|-------------------|-----------------------------------------------------------------|-----------------------------------------|
| `post-commit`     | `rmx sync --since HEAD~1` (a root commit: the empty tree)       | Every commit                            |
| `post-merge`      | `rmx sync --since ORIG_HEAD`                                    | After merge                             |
| `post-checkout`   | `rmx sync --since $1..$2` (only when `$3 == 1`, `$1` not null)  | Branch switch (not file checkout)       |
| `post-rewrite`    | `rmx sync --since <oldest pre-rewrite OID>`                     | After rebase / amend                    |

### The store gate {#store-gate}

Each hook syncs only in a checkout that has its own store that a sync may write. The gate is
`hooks._store_gate`. It is built from `store.WRITER_CATALOG_FILES` and `daemon.SOCKET_NAME`,
never retyped:

- **A daemon socket** `.refmatrix/rmxd.sock` passes. Git cannot track a socket, and a live
  daemon takes the write.
- **Otherwise a writer catalog must be present and NOT tracked by git**:
  `catalog.A.duckdb`, `catalog.B.duckdb`, `catalog.duckdb` or `catalog.db`, for which
  `git ls-files` prints nothing. A dir holding only the legacy `catalog.db` passes the gate,
  and the `rmx sync` it runs is refused with one line naming the file (task S1,
  [[ARCHITECTURE#backend-selection-backend-py]]): the hook reports it as a failed sync.
  - A checkout with no catalog exits 0 silently. That covers a worktree or clone that has only
    a tracked `.refmatrix/CLAUDE.md`.
  - A checkout whose catalog git tracks also exits 0 silently, whether it is the main
    checkout, a worktree or a clone. It has no daemon, and a sync would write the committed
    binary (bug-212 r1). To keep such a repo fresh, untrack the catalog
    (`git rm --cached .refmatrix/catalog*` and ignore it) or run its daemon.
  - If `git ls-files` itself fails, the hook prints
    `refmatrix: <hook>: git ls-files failed; not syncing` and does not sync.

`post-checkout` also exits 0 on an initial checkout (`git clone`, `git worktree add`). There
the previous HEAD `$1` is the null sha, and the checkout is not a branch switch.

### Failures are loud, and never fail git {#hook-failures}

Every hook backgrounds and disowns `rmx sync`, so the git operation never waits on it and
never fails because of it.

- The sync's stdout is discarded. Its stderr stays on the terminal that ran git.
- A non-zero exit adds `refmatrix: <hook> rmx sync FAILED (exit N); its error is above`.
- Both lines can print after the shell prompt returns.

### No command opens a tracked catalog read-write in-process {#sync-tracked-catalog}

When no daemon answers, a writer opens the catalog read-write in its own process. Every CLI,
verb and MCP site that opens or replaces a writer catalog (`catalog.A.duckdb`,
`catalog.B.duckdb`, `catalog.duckdb`, `catalog.db`) in-process first calls ONE store-level
check, `store.refuse_tracked_catalog_open` (bug-212 r2-r5, rulings L72, L82 and L95):

- `cli._store_rw()`, through the CLI's one wrapper `cli._refuse_tracked_catalog_open`. It
  serves `rmx sync` (`--files`, `--since`, `--flush-queue`, `-i`), `rmx ingest`,
  `rmx memory add`, `rmx ingest-gmd --as-memory` (the memory bridge), `rmx tldr-warm`, and the
  daemon-down repair commands.
- The same wrapper, called directly by `rmx compact`, which opens the file without a
  `Store`. It checks before it pings or stops the daemon, so a tracked catalog never costs the
  daemon it names as the remedy. (`rmx migrate-to-duckdb`, the second such command, went with
  the SQLite backend in task S1, 2026-11-19.)
- `verbs.local_write` serves every no-daemon verb write (`rmx add concept|entity`,
  `rmx protect`, `rmx noise`, ...). It also serves `rmx init`, `rmx partition drop`,
  `rmx focus change-subject`, the MCP `rmx_memory_add` fallback and the save-state promote,
  which used to open the store themselves.

The daemon is the exception. Its own writer, its A/B slot merge and repair, and the hub's
global store are not checked: a write through the daemon is the remedy the refusal names.
An AST census test keys on the guarded resource, not on one constructor. It fails when
`src/` adds any of these outside the checked sites and a short allowlist with reasons:

- a read-write `Store(`, under any alias;
- a non-`:memory:` `open_duckdb` / `duckdb.connect`;
- a rename or unlink onto a writer-catalog path;
- a copy (`shutil.copy*`, `write_bytes`) whose destination is a writer-catalog path.

`rmx init` and `rmx partition drop` take the in-process route only when the daemon is ABSENT.
A daemon that is alive but not answering is busy, not absent, and they refuse with one
`Error: daemon busy ...` line.

Before the catalog opens, the check asks git (`store.git_tracked_catalogs`) and refuses if a
writer catalog is tracked:

- one `Error: refusing to open <full path of the catalog> read-write in-process: git tracks
  this store's catalog (...)` line that names both remedies (untrack it with
  `git rm --cached`, or start the daemon). MCP replies `isError` with the same text;
- a non-zero exit, with the catalog bytes unchanged.

In `rmx save-state` and MCP `rmx_save_state` the handoff file is written first, and the
refusal arrives through a later step:

- If the STM promote or the memory bridge is refused, or fails for any reason, the verb raises
  one error: `save-state wrote <target> but its promote failed: ...` (or `its memory bridge
  failed: ...`, or both).
- The CLI prints what was written, runs `--commit`, then prints that line on stderr and exits
  1. MCP replies `isError`, and the reply body is the full result (`target`, `promoted`,
  `sync`, ...) with that `error` added.
- A bridge that is only DEFERRED is not a failure. This happens when another ingest job still
  holds the single-active-ingest slot at the end of the wait (`RMX_BRIDGE_WAIT_S`, 120 s).
  - The result carries `sync.deferred = {job, reason}` and no `sync.error`.
  - The CLI prints `warning: memory bridge deferred: ingest job <id> still running ...` on
    stderr and exits 0.
  - MCP replies normally.
  - The next save-state or SessionStart bridges the dir.

A refused `rmx focus change-subject` leaves the session's STM subject as it was. The store
row is written before the STM subject is switched, and the line ends `the session's subject
is unchanged (still '<old>')`.

The check runs two bounded git subprocesses (`rev-parse`, `ls-files`) before every
in-process open, about 25 ms on a small idle repository (measured 2026-11-13) and roughly
30-100 ms on a large or busy one; a write through the daemon pays nothing.

A read can reach the same opener. `_read_store()` serves reads from a reader file, in this
order: `catalog.read.duckdb`, then `read_only.duckdb`, then, when an `active` marker names a
slot, the INACTIVE slot only; without a marker, the legacy `catalog.duckdb`. Only when that
file is missing and no daemon runs does a read fall to `_store_rw()`. On a tracked store it
gets the same refusal. The line is worded as an open, and its tail claims no write. A tracked
store that has a reader file is served read-only and not refused.

A socket file that a crashed daemon left behind passes the hook gate, and this refusal is what
then stops the write. With a live daemon nothing opens in-process, so nothing is refused, and
the daemon writes the catalog itself. A store with no `.git` at or above it, or one whose
catalog git ignores, is still written in-process. When the answer is unknown, the open is
refused too, because unknown counts as tracked. The line then reads `refusing to open <path>
read-write in-process: cannot tell whether git tracks the catalog under <store>: ...`. That
happens when:

- `git ls-files` fails;
- `git rev-parse` fails while a `.git` exists at or above the store (a corrupt `HEAD`);
- either call runs past 10 s (`git <call> timed out after 10s`).

`rmx sync --since <ref>` bounds its `git diff` the same way: past 10 s it fails with
`Error: sync --since <ref> failed: git diff timed out after 10s in <project>`, never a silent
hang in the backgrounded hook.

### A vanished working directory {#vanished-cwd}

A backgrounded hook can outlive `git worktree remove`. Every cwd read (`cli`, `discovery`,
`sync`, `mcp`, `cctree`) goes through `workdir.current_dir()`. When the directory is gone it
raises `workdir.WorkingDirectoryGone`, never a raw `FileNotFoundError`:

- The CLI prints one `Error: the working directory no longer exists (<$PWD>); ...` line and
  exits 1. The conversion happens in `cli._RmxGroup`, for every command.
- The remedy in that line depends on context. With `REFMATRIX_ROOT` set, the command still
  needed the cwd (for example to resolve the partition), so the line says to cd to an existing
  directory.
- `rmx mcp` answers the tool call with `isError` and the same text, and keeps serving.
- `rmx version` still works, and its telemetry row carries `cwd: null` and `cwd_error`.

### `rmx sync --since <ref>` {#rmx-sync-since-ref}

`rmx sync --since` calls `git diff --name-only <ref>` to get the list of changed files, then
re-ingests only those paths. A file whose mtime equals `tracked_files.mtime` is skipped
(`sync._sync_one`).

If git rejects the ref, `sync.GitRefError` is raised and the CLI prints one line:
`Error: sync --since <ref> failed: git diff exited N: <git's message>`. The daemon route and
the daemon-down enqueue route print the same text.

## GMD (Graph Markdown) integration {#gmd-graph-markdown-integration}

GMD is a spec for markdown documents that carry typed relations and stable
addressability — designed to replace plain markdown in `CLAUDE.md`, `SKILL.md`,
memory files, notes. Spec lives at `../gmd/SPEC.md`.

### What refmatrix's GMD ingestor (`ingest_gmd.py`) accepts {#what-refmatrix-s-gmd-ingestor-ingest-gmd-py-accepts}

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

### Verb policy {#verb-policy}

- Spec §8 recommends an open vocabulary: `supports`, `contradicts`,
  `derives-from`, `supersedes`, `depends-on`, `instance-of`, `part-of`,
  `mentions`, `defines`, `example-of`.
- Authors MAY use any kebab-case verb. refmatrix auto-creates the linkage
  type on first encounter (`daemon.py:_op_add_linkage_type` /
  `ingest_gmd.py:_ensure_linkage`).
- Pre-registered verbs (with inverses) live in `store.py:DEFAULT_LINKAGES`.

### Recent extensions {#recent-extensions}

- `_ID_RE` now allows `/` in IDs (`ingest_gmd.py:30`), matching spec §3's
  `[a-z0-9][a-z0-9._/-]*` so hierarchical IDs like `project/foo` parse.
- `specifies` + `specified_by` registered in `DEFAULT_LINKAGES` so author
  GMD `rel: specifies -> [[#X]]` and rmx's plan-doc heuristic produce the
  same edge type.

## File watcher integration {#file-watcher-integration}

### Backend {#backend}

[watchdog](https://github.com/gorakhargosh/watchdog) (optional dep, install
with `pip install -e '.[watch]'`).

### Behavior (`watch.py`) {#behavior-watch-py}

| Concern              | Value                                                                |
|----------------------|----------------------------------------------------------------------|
| Root                 | `project_root` (recursive)                                           |
| Events monitored     | `on_created`, `on_modified`, `on_deleted`, `on_moved`                |
| Relevant extensions  | `CODE_EXTS ∪ DOC_EXTS` (`watch.SUPPORTED_EXTS`)                      |
| Ignored paths        | whatever `ingest.should_ignore(p, root)` excludes — see [[#ignore-rules]] |
| Debounce             | Configurable window (default 500ms); coalesces bursts into one batch |
| Handler              | Calls `sync_files(paths, semantic=True)` on the coalesced batch      |

### Ignore rules (`.refmatrix_ignore`) {#ignore-rules}

Every walker — the `rmx ingest` tree walk, both watchers (`watch.is_relevant`), `sync`
(including its purge of a path that became ignored) and the `rmx ingest-gmd` doc walk — asks
ONE predicate, `ingest.should_ignore(p, root)`; `ingest.ignore_reason` says why. The
per-project file is `<project>/.refmatrix/.refmatrix_ignore`, one line each, `#` comments:

| Line                 | Meaning                                                                    |
|----------------------|----------------------------------------------------------------------------|
| `name`               | a path SEGMENT anywhere (`workflow`, `.claude`)                            |
| `*.glob`             | fnmatch on the file name (`*.log`)                                         |
| `a/b`                | anchored to the project root: that path and everything under it           |
| `!path`              | RE-INCLUDE: anchored to the project root, a glob allowed; files only       |

Precedence, first match wins (bug-216 R1 + R11):

1. `INGEST_IGNORE_DIRS` (`node_modules`, `venv`, `__pycache__`, `dist`, `build`) — always
   ignored; nothing re-includes them. One list: the watcher keeps none of its own (R12).
2. A `!path` line — included, whatever ignore line matches and wherever it sits.
3. An ignore line — ignored.
4. The BUILT-IN include: `CLAUDE.md` at the project root and `.claude/PROJECT_PROFILE.md`, when
   the file carries GMD frontmatter, are included with no ignore file at all (a fresh clone, CI).
5. The built-in hidden-directory rule — any segment starting with `.` is ignored.

So `.claude` + `!.claude/PROJECT_PROFILE.md` ingests the profile and nothing else under
`.claude/`; a `CLAUDE.md` line keeps excluding CLAUDE.md (the fleet's files carry one until it
is removed) and `!CLAUDE.md` beats it. A `!dir` line re-includes NOTHING — list each file — and
is reported once on stderr when the spec loads. `scripts/check-gmd-parity.py`, run by
`scripts/lint-gmd.sh`, fails when a GMD doc in the lint scope is excluded by these rules, naming
the file and the rule (R3).

**Which root a path is judged against.** The spec is read from, and the segment rules (1 and 5)
apply BELOW, the PROJECT root — never the ingest target (bug-216 R2-base + remedy B1):

- `rmx ingest <dir>` and MCP `rmx_ingest`: ALWAYS the project the store belongs to (the parent
  of its `.refmatrix/`). A `<dir>` inside it is judged by that project's spec, segment rules below
  the root: `rmx ingest <proj>/.claude[/projects/x/memory]` stores nothing but a built-in-included
  GMD `.claude/PROJECT_PROFILE.md`. A `<dir>` OUTSIDE it is judged on its absolute path, as
  before bug-216: a memdir under any `.claude/` stores nothing, and no other store's ignore file
  is ever read for it (remedy B1-r2). The store's OWN ignore file still applies to an outside
  file, but by FILE NAME only (an outside path has no project-relative path): a bare-name or
  glob line (`*.log`, `NOTES.md`) matches it, an anchored line (`docs/private`) and a `!path`
  re-include never do (remedy r3 M3). Memories go through `ingest-gmd --as-memory`, never as
  `kind=doc`.
- the watcher and `sync`: the watch root / project root, so a project under `<x>/.hidden/` or
  `<x>/build/` syncs, while a `build/` INSIDE the project stays out.
- `rmx ingest-gmd <dir>`: the spec from the project root (the nearest `.refmatrix/` above
  `<dir>`); the segment rules below `<dir>` itself — a directory handed in explicitly is taken as
  given (`rmx session ingest` indexes cards under `.refmatrix/sessions/` this way). Every path it
  excluded is named in its report, prestage's included.

A deleted file at a built-in-include path stays in scope, so its delete event reaches `sync`,
which purges it.

**Changing the ignore file on a live store.** An edit to `.refmatrix_ignore` is not a file event
the daemon acts on, and docs ingested before the edit are not re-judged. Re-including a doc that
others already cite (R4: the rule docs) is: back up the file, edit it, then run `rmx reingest
--force --no-sessions` through the daemon. The forced pass clears the mtime stamps AND the GMD
content hashes, so every citer is re-processed and its pending `rel:` lines bind; a plain `rmx
ingest .` skips a citer whose GMD content hash still matches. Then measure with
`scripts/check-rel-landing.py` on a copy of the catalog.

rel: specified-by -> [[task-bug216-rule-docs-in-graph#r1]]
rel: specified-by -> [[task-bug216-rule-docs-in-graph#r4]]
rel: specified-by -> [[task-bug216-rule-docs-in-graph#r11]]
rel: specified-by -> [[task-bug216-rule-docs-in-graph#r12]]

### Embedded vs standalone {#embedded-vs-standalone}

- **Standalone**: `rmx watch` runs the observer in the foreground (good for
  debugging).
- **Embedded**: `rmx daemon start` runs the same observer on a worker thread
  inside the daemon (`daemon.py:_start_watcher`). This is the production
  path — single process owns the catalog lock AND the watcher.

## Daemon socket protocol {#daemon-socket-protocol}

The daemon listens on `.refmatrix/rmxd.sock` (Unix socket). Protocol is
**newline-delimited JSON** — one JSON object per line, request and response.

### Wire format {#wire-format}

```json
// request
{"op": "query", "args": {"expr": "defines:parser", "limit": 50}}

// response (success)
{"ok": true, "result": {"rows": [...], "cardinality": 42}}

// response (error)
{"ok": false, "error": "unknown linkage: foobar"}
```

### Client API (`daemon.py:72-99`) {#client-api-daemon-py-72-99}

```python
from refmatrix.daemon import ping, call

if ping(project_root):                           # health check
    result = call(project_root, "query", expr="defines:auth")
else:
    # fall back to opening Store directly
    ...
```

### Op inventory {#op-inventory}

See [[ARCHITECTURE#daemon-concurrency-layer]] for the full op table.

### Concurrency model {#concurrency-model}

The daemon is single-threaded for catalog ops (Store is not thread-safe).
The watcher runs on a worker thread but routes through the same socket to
the main thread so all Store access is serialized. `flush_queue_async`
breaks this rule deliberately: it returns immediately to the client and
processes the queue on a background thread. Acceptable because (a) the
client doesn't need the result and (b) the only writer is still the
daemon's main loop, just shifted in time.

## CLI surface (top-level) {#cli-surface-top-level}

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
├── describe                   every stored fact about ONE entity (row+edges+vectors)
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
└── dump-log / rebuild         rebuild bitmaps from append-only log
```

## Onboarding checklist for a new project {#onboarding-checklist-for-a-new-project}

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
