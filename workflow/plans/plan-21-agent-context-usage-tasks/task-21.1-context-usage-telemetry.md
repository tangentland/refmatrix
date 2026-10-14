---
gmd: "0.1"
id: task-21.1-context-usage-telemetry
title: "Task 21.1: telemetry that can count how the agent uses rmx context, and the ONE recall-event schema"
tags: [task, telemetry, context, mcp, agent, recall-events]
metadata:
  node_type: task
  status: pending
  created: 2026-10-07
  updated: 2026-10-14
---

# Task 21.1: make agent context usage measurable {#root}

> Plan: [plan-21-agent-context-usage](../plan-21-agent-context-usage.md)
> Status: Pending (revision after the 2026-10-14 decision log)
> Wave: 1
> Depends on: 23.0 (the shared test sandbox; [[plan-review-2026-10-14#t8-wave1]]), and bug-109
> MERGED TO `master` (d9s; round-4 #s-1): R9's session resolver and pid pointer EXTEND bug-109's
> code as existing code, never rebuild it. A sha list on the bug-109 branch is not the
> dependency; the merge is. The event emission does NOT depend on plan-23's queue (d4a); only
> 19.2's fold does.

rel: part-of -> [[plan-21-agent-context-usage]]
rel: derives-from -> [[exploration-agent-context-usage]]
rel: derives-from -> [[bsd-plan21-spec-review-3104a81]]
rel: derives-from -> [[plan-review-2026-10-14]]
rel: depends-on -> [[plan-23-bounded-write-harness]]
rel: depends-on -> [[task-23.0-test-sandbox]]
rel: related-to -> [[task-19.2-memory-usage-record]]
rel: related-to -> [[task-19.5-measure-delivery]]
rel: related-to -> [[exploration-session-phased-context]]
rel: depends-on -> [[bug_registry]]

## Why {#why}

The exploration measured 3 CLI `context` calls against 1,119 agent greps (2026-09-23 to
2026-10-07T11:06), and could not count MCP calls at all. Checked at HEAD `b1c4324`:
- `invocation` is `unknown` on every agent grep and context row: an agent's Bash call has no tty
  and no hint (`telemetry.invocation_source`, `telemetry.py:151`).
- `mcp.serve_stdio` (`mcp.py:312`) never sets `RMX_INVOCATION_SOURCE`, although the docstring at
  `telemetry.py:154` says the MCP server does. `mcp` is already a member of `INVOCATION_SOURCES`
  (`telemetry.py:57`).
- No `query.log` row is written by the daemon's `_op_context` (`daemon.py:4687`), by
  `verbs.context` (`verbs.py:538`), or by the CLI's daemon route (`cli.py:5152`). Only the replica
  (`cli.py:5100`) and direct (`cli.py:5231`) routes log.
- `query.log` rows carry no session, no query id and no cwd (`telemetry.log_query.__exit__`), so no
  per-session count (21.3 AC-4, 19.2 R3) can be computed and no event can be joined to its query.
- `grep-stdin` rows (`cli.py:6202`) never set `cardinality`: it is `null` on all 3,521 rows of the
  window. The `-E` replica-path "0 cardinality" defect the exploration named does not reproduce in
  October data (bsd #s-4).

Without these, no change in 21.2–21.4 can be shown to change behaviour, and plan-19's 19.2 / 19.5 /
19.6 have no instrument. {#why-body}

## Requirements {#requirements}

### Invocation source {#req-invocation}

1. **R1 The MCP server sets its source.** `mcp.serve_stdio` sets `RMX_INVOCATION_SOURCE=mcp` in its
   own process environment before it reads the first request, so every verb it serves and every
   child it spawns inherits it. (`mcp` is already in `INVOCATION_SOURCES`; bsd #m-1.)
   - **Existing (bug-109):** `serve_stdio` already sets `verbs._LONG_LIVED = True` before the
     first request, so every verb it serves resolves its session per call through
     `verbs.resolve_session_source` (pointer first, R9). This task does not rebuild that.
   - **Delta (round-3 #b-1; round-4 #s-1):** at startup it also removes `CLAUDE_CODE_SESSION_ID`
     from its own `os.environ`. No resolver reads that variable (R9), but a child the server
     spawns must not inherit a spawn-time id that a non-rmx tool could trust.
2. **R2 An `agent` source with a stated precedence** (d4f; decision-log #m-2). `agent` joins
   `INVOCATION_SOURCES`. `invocation_source()` resolves, in this order:
   1. explicit `RMX_INVOCATION_SOURCE` (hooks: `hook`; MCP: `mcp`; harnesses: `internal`);
   2. `CLAUDECODE` set → `agent`;
   3. stdin is a tty → `interactive`;
   4. otherwise `unknown`.

   Consequences stated, not hidden: a `!`-typed human command inside Claude Code logs `agent`, and
   a bare grep the `grep-rewrite-guard` hook rewrote to `rmx grep` logs `agent` although the agent
   never chose rmx. Adoption reads therefore separate CHOSEN calls from rewritten ones by `source`
   (`grep-replica` with `answered_by`, `context-*`) and by event `channel`, never by `invocation`
   alone. Every eval harness (`eval/production/*`, 21.2's replay, 21.4's runner) sets
   `RMX_INVOCATION_SOURCE=internal` explicitly.

### query.log rows {#req-query-log}

3. **R3 One row per context call, on every route** (bsd #s-5). Each of the four routes writes
   exactly one `query.log` row with `kind=context`, and `source` names the route:
   - MCP `rmx_context` → `verbs.context` → daemon op: `source=context-mcp`;
   - CLI replica route (`cli.py:5100`): `context-replica` (exists);
   - CLI daemon route (`cli.py:5152`): `context-daemon` (missing today);
   - CLI direct route (`cli.py:5231`): `context` (exists).

   The row is written on the CALLER side (the verb or the CLI), never inside a daemon op and never
   under the daemon's writer lock. `memory_recall` reached from the CLI or MCP gets the same
   treatment with `kind=recall`. `ann_search` is NOT covered: it has no verb (`cli.py:10718` calls
   the op directly), and R4 does not report it.
4. **R4 New row fields.** Every `query.log` row (all kinds) gains:
   - `session`: resolved by [[#req-session]] (null when nothing resolves, never guessed);
   - `query_id`: a uuid4 hex minted by the caller once per call and shared with every recall event
     of that call (R7);
   - `cwd` and `root`: the process cwd and the resolved store root, so d8d's predicate (R5) can
     apply to new rows.
5. **R5 One shared row classifier** (d8d, d9g; owner: this task, in `telemetry.py`, per
   [[plan-review-2026-10-14#t9-fixes]]). Signatures, exact:
   - `telemetry.row_provenance(row: dict, *, reader_root: Path | None = None,
     source: Literal["query_log", "events"] = "query_log") -> str`, returning one of
     `attributed`, `test_artifact`, `legacy_fixture`, `legacy_unattributed`, and, for
     `source="events"` only, `malformed`;
   - `telemetry.is_test_artifact_row(row: dict, *, reader_root: Path | None = None,
     source: Literal["query_log", "events"] = "query_log") -> bool`, which is
     `row_provenance(...) == "test_artifact"` and nothing else.

   `reader_root=None` means a LIVE reader (no test base), which is how 23.0 AC-4 calls it,
   `telemetry.is_test_artifact_row(row)`, on rows added to the live logs during a suite run
   ([[task-23.0-test-sandbox]]); the defaults keep that call valid as written. Readers that fold
   or report one store pass that store's root; readers of `recall-events.jsonl` pass
   `source="events"`.

   EVERY reader of `query.log` and `recall-events.jsonl` (R7's report, 19.2's fold, 21.4's question
   draw) calls `row_provenance`; no reader carries its own copy, and no reader decides
   `malformed` itself (round-3 #s-3). The classes, first match wins:
   0. **`malformed`** (`source="events"` only): the event lacks any of `v`, `stage`, `name`,
      `channel`, `cwd`, `root`, `ts`, or its `v` is not 1, or its `channel` is not in R10's enum,
      or its `ts` is not R10's UTC form (`YYYY-MM-DDTHH:MM:SS.mmmZ`; round-4 #s-2).
      Unparseable lines never reach the function: the reader counts them before classifying (R8).
   1. **`test_artifact`** (round-3 #s-3: keyed on `root`). The row's KEY PATH is its `root`, or
      its `cwd` only when it has no `root`. It is `test_artifact` when `test_base(key path)` is not
      `None` and differs from `test_base(reader_root)`. `test_base(p)` is: the path up to and
      including the `pytest-<N>` component that follows a `pytest-of-<user>` component; else, for
      a path under `/tmp` or `/private/tmp` whose first component below it starts with `rmx-`
      (23.0's sandbox root, `tempfile.mkdtemp(prefix="rmx-", dir="/tmp")`), that `rmx-*`
      directory; else `None`.
      - **Why `root`, not `cwd`.** One test run has two test bases: 23.0's store roots under
        `/tmp/rmx-*`, and pytest's `tmp_path` under `/private/var/folders/…/pytest-of-<u>/
        pytest-<N>`, while in-process emission runs with cwd = the repo (base `None`). The root is
        the store the row was written for; the cwd is incidental. Keyed on `root`, a sandbox test
        whose cwd is `tmp_path` or the repo, writing to a sandbox store, folds its own events
        (the intent of `reader_root`), and the live store still drops every test tree's rows.
      - **A row with no test base is never a test artifact.** A live-tree row (base `None`) read
        by a sandbox reader is classified by classes 2-4, not as `test_artifact`: such a row in a
        sandbox log can only come from a broken redirect, which 23.0 R3 refuses and 23.0 AC-4
        detects; this function does not rename it.
   2. **`legacy_fixture`** (d9g): the row has NEITHER `cwd` NOR `root`, `kind == "grep"` and
      `body == "alpha|beta"` exactly (string equality; `alpha`, `alpha|GAMMA`, `alpha.beta` do
      not match). Read-only check at `3357c44` (2026-10-14): `~/.refmatrix/query.log` holds
      exactly 235 such rows (230 `grep-stdin`, 5 `grep-replica`, all `invocation=unknown`,
      2026-10-01T17:08:27 to 2026-10-07T15:12:27); the project `.refmatrix/query.log` holds 0.
   3. **`legacy_unattributed`**: any other row with neither `cwd` nor `root` (every row written
      before this task).
   4. **`attributed`**: everything else.

   **Totals rule (b-2, Option A; #t9-fixes).** `attributed` and `legacy_unattributed` rows ARE
   counted in every total. `test_artifact` and `legacy_fixture` rows are NOT counted. Every
   reader prints all three non-`attributed` counts on their own line, as `excluded_test_rows=<n>
   legacy_fixture_rows=<n> legacy_unattributed=<n>`, so nothing is silently included or dropped.
   A `recall-events.jsonl` event always carries `cwd` and `root` (R10), so an event without them
   is `malformed` by class 0 (classes 2 and 3 never apply to events); event readers print
   `malformed=<n> unparseable=<n>` beside the line above and never fold either.
6. **R6 `grep-stdin` cardinality** (bsd #s-4, retargeted). The stdin filter path (`cli.py:6202`)
   sets `cardinality` to the number of lines it emitted. The `-E` replica-path claim is dropped:
   it does not reproduce at HEAD (live `-E` row 2026-10-14T11:08:31 logged `cardinality: 15`).
7. **R7 `rmx telemetry --agent-usage`** (bsd #m-2, #s-3, #s-5). `telemetry` is a `@main.command`
   (`cli.py:7521`), so this is a FLAG on it, not a subcommand. It reuses `--since` and adds
   `--until` (ISO prefixes); no `--days`. It prints, per `invocation`, the counts and p50/p95
   latency for context (per route), grep (per `source` / `answered_by`), and recall, plus a
   `--by-session` table (calls per `session`). It:
   - reads `query.log` and `cli.log` of ONE store root;
   - counts a `cli.log` command once (excludes `phase=start` intent rows, as `summarize_context`
     already does);
   - applies R5's `row_provenance` with `reader_root` = the store root it reads, counts per R5's
     totals rule, and prints the `excluded_test_rows` / `legacy_fixture_rows` /
     `legacy_unattributed` line;
   - excludes `invocation=internal` rows by default (`--include-internal` to keep them).

   The report covers context, grep and recall only. Other MCP tools are not claimed.

### The ONE recall-event schema (C7) {#req-schema}

8. **R8 The sink** (d4a). Events are appended to `<store root>/recall-events.jsonl`, a NEW
   append-only file, written lock-free like `query.log`: one `write()` of one complete
   newline-terminated JSON line per event, `O_APPEND`, never under the daemon's writer lock. The
   file is never truncated or rotated by any writer; it is the retained replay source for 19.2's
   fold (d2a amendment) and is read by 23.1's non-consuming tail reader, which stops at the last
   complete newline. A hit on a GLOBAL memory is appended to `~/.refmatrix/recall-events.jsonl` with
   `scope=global`, so it is counted in the global store keyed by name (d8e). A failed append is
   never silent: the emitter prints one `rmx: recall-event append failed: <error>` line to stderr
   and the command continues (telemetry never fails the command it describes). Readers count and
   print unparseable lines; they never skip them silently. No other recall log format may be added
   (AC-9).
9. **R9 Session, turn and identity.** Every event and every `query.log` row resolves `session`
   through the ONE resolver below, with `purpose="event"`; turn is logged, never used as a phase
   signal (d5b).
   {#req-session}

   **The ONE session resolver** (round-3 #b-1; round-4 #s-1, #b-2, #m-2; d9s). Live fact, read
   2026-10-14: the long-lived `rmx mcp` process (pid 59378, child of the Claude process
   `CLAUDE_PID=59363`) carries `CLAUDE_CODE_SESSION_ID=b38025a7…` while that Claude process
   serves a later session. An environment variable is a snapshot of its process's birth; after
   `/resume` or `/clear` the MCP server's copy names a dead session for the rest of its life.

   **Existing code this task extends** (bug-109, read at `320dc82` in
   `/Volumes/littlebig/refmatrix-bug109`, branch `bug-109-mcp-session`; it reaches this task only
   through its merge to `master`, and every line number below is re-read after that merge):
   - `stm.write_pid_pointer(root, pid, session) -> bool` writes `stm/by-pid/<pid>.json` =
     `{session, pid, pid_start, t}` by tmp + `replace`; an unchanged pointer costs one read and no
     `ps`; a pid whose start time `ps` cannot report is refused and recorded (`ps-failed`).
   - `stm.read_pid_pointer(root, pid) -> str | None`: the session, or `None` when the file is
     missing, unreadable, or its `pid_start` differs from `_proc_start(pid)` (`ps -o lstart=`).
   - `stm.owner_claude_pid(*, long_lived=False) -> int | None`: long-lived → `os.getppid()`, its
     own environment ignored; per-call → `$CLAUDE_PID` only when that pid is a real ancestor, else
     the nearest ancestor whose command is `claude`, over a chain of at most 16 steps built from
     ONE `ps -A -o pid=,ppid=,comm=` call. (The round-3 "within 4 levels, one `ps` per pid" rule
     is WITHDRAWN in favour of this.)
   - `stm.record_pointer_error(root, reason, **fields)` appends `{t, reason, …}` to
     `stm/by-pid/_errors.jsonl`; reasons `no-owner`, `ps-failed`, `write-failed`,
     `pointer-unresolved`.
   - The input branch of `cli.focus_hook` writes the pointer for every envelope with a
     `session_id`, FIRST, before the in-flight sweep and the ambient check (`cli.py:1973-1992` at
     `320dc82`).
   - `verbs._LONG_LIVED` (set by `mcp.serve_stdio`) and
     `verbs.resolve_session_source(root, session) -> (session, source)`, `source` ∈ `explicit`,
     `pointer`, `env`, `latest`, `default`; order: explicit → (long-lived: pointer → `RMX_SESSION`;
     per-call: `RMX_SESSION` → pointer) → newest ring (recorded `pointer-unresolved` when running
     under Claude) → `default`. Write verbs return `session_source`; `cli.focus_promote_edges`
     resolves its session in the CLI. Tests: `tests/test_mcp_session_pointer.py`.

   **The resolver as this task specifies it** (19.0 R5 cites it; built by whichever of 21.1 and
   19.0 merges first as the deltas below, the other imports it unchanged). The resolution ORDER
   is bug-109's, adopted as written and stated once here; the round-3 order (envelope →
   `CLAUDE_CODE_SESSION_ID` → pointer → `RMX_SESSION`) is WITHDRAWN.
   - **Signature, exact (delta D1):** `verbs.resolve_session_source(root: Path, session: str |
     None = None, *, envelope: dict | None = None, purpose: Literal["write", "read", "event"])
     -> verbs.SessionResolution`, a `NamedTuple(session: str | None, source: str)`. A NamedTuple
     unpacks like bug-109's 2-tuple, so its existing callers keep working; `purpose` is
     REQUIRED (no default), so every caller states what it does with the answer. `source` ∈
     `explicit`, `envelope`, `pointer`, `env`, `latest`, `default`, `none`. The round-3 name
     `stm.resolve_session` is not built.
   - **Order:** `session` (explicit) → `envelope["session_id"]` (source `envelope`; a hook passes
     its stdin envelope) → long-lived: pointer for `owner_claude_pid(long_lived=True)` →
     `RMX_SESSION`; per-call: `RMX_SESSION` → pointer for `owner_claude_pid()` → the TAIL of the
     caller's `purpose`:
     - `read`: the newest ring (source `latest`, output labelled `(newest ring; not resolved)`),
       else `default`. This is the ONE allowed `latest_session` call in `src/` (round-4 #m-2);
       19.0 AC-6e enforces it by an AST scan.
     - `write`: raises `verbs.SessionUnresolved` naming the sources tried (19.0 R5 states the
       CLI and MCP outcome). No write reaches `default` or the newest ring (delta D2: bug-109's
       `latest` / `default` tail is removed for writes).
     - `event`: `SessionResolution(None, "none")`. Telemetry rows and events (this task),
       scan-prompt's enrichment and composite, and the helix gate (19.0 R5) use it.
     In all three, a miss under Claude is recorded `pointer-unresolved`, as today.
   - **`CLAUDE_CODE_SESSION_ID` is read by no resolver path** (bug-109 already reads it nowhere;
     R1 also deletes it from the server's environment).
   - **D3 One pointer location for every store root** (bug-109 r1 #m-4, "the hook and server
     resolve their store root differently"). The hook writes under `cli._root()` (its cwd's
     store); the server reads under `mcp._resolve_root(args)` (its spawn cwd's store, or a named
     `root` / `project`). When the session's cwd moves into another tree, the pointer lands in a
     store the server never reads. A pointer belongs to a Claude PROCESS, not a store, so pointers
     and `_errors.jsonl` move to `<hub.global_store_root()>/by-pid/` (`~/.refmatrix/by-pid/`;
     23.0's sandbox redirects it). `stm.pointer_dir() -> Path` returns it; `write_pid_pointer`,
     `read_pid_pointer` and `pid_pointer_path` drop their `root` argument. Migration, one
     release: `read_pid_pointer` falls back to bug-109's `<root>/stm/by-pid/<pid>.json` when the
     new file is absent, and records `pointer-legacy-location`; nothing writes the old location.
   - **D4 The SessionStart writer** (bug-109 r1 #m-4). A NEW generated SessionStart entry,
     matcher `startup|resume|clear|compact`, command `rmx focus hook --event session-start`
     (stderr NOT discarded: this is a memory path), calls `write_pid_pointer` with the envelope's
     `session_id`, so after `/clear` the pointer names the new session BEFORE the first prompt.
     The pointer gains one field, `hook` (`input`, or `session-start:<source>`); readers ignore
     unknown fields, so bug-109's format `{session, pid, pid_start, t}` is otherwise kept as is
     (the round-3 names `session_id`, `written_at`, `hook_source` are WITHDRAWN).
   - **D5 Silent misses recorded.** `read_pid_pointer` records `pointer-stale` (its `pid_start`
     no longer matches: pid reuse) and `pointer-unreadable` (present but not JSON) instead of
     returning `None` silently. A missing file is not an error by itself; the resolver's
     `pointer-unresolved` row covers it.
   - **D6 `_errors.jsonl` is surfaced** (bug-109 r1 #b-1 left it unread). `rmx focus show`
     prints one line `session pointer: <reason>=<n> … since <ts>` from it. The SessionStart writer
     (D4) prints the same line on STDOUT, where SessionStart output reaches the agent, whenever
     rows were added since the last surfacing (watermark: `by-pid/_errors.seen`, the byte offset
     last surfaced). Once the file exceeds 1 MB the writer renames it to
     `_errors.<YYYYMMDD>.jsonl` after surfacing; nothing is deleted.
   - **D7 `by-pid/` cleanup** (bug-109 r1 #m-4). The SessionStart writer removes pointer files
     whose pid is absent from ONE `stm._process_table()` call or whose `pid_start` differs, and
     prints `pruned=<n>` with the surfacing line. A pointer is only a cache of the process
     relation, so removing a dead process's pointer loses nothing.
   - **D8 `record_pointer_error` generalized.** With D3 it writes `<pointer_dir>/_errors.jsonl`
     and drops its `root` argument (a store-scoped row carries `root=` as a field). 19.0 adds the
     reasons `sweep-failed`, `composite-failed` and `enrichment-unresolved` to the same record, so
     every STM hook failure reaches D6's surfacing; no new error file is added.
   - `stm.latest_session` (`stm.py:127` at HEAD) is never called outside the `read` tail (bsd
     #b-1; bug-100's shape). When nothing resolves, rows and events carry `session: null`.

   **The pre-prompt state, race-free** (re-review #s-3; round-3 #b-2; round-4 #b-1, #m-1). The
   recall and scan hooks run IN PARALLEL with `focus hook --event input` (`hooks.py` registers
   them as separate UserPromptSubmit entries, and Claude Code runs an event's hooks in parallel,
   as the generator's own comment at `hooks.py:263-265` records). The input hook CHANGES the
   state they read, in two places (read at HEAD, `cli.py:1946-1981`; `stm.py:246-282`,
   `:331-353`):
   - `inflight_sweep()` runs first (`cli.py:1976`): every call parked longer than 90 s is
     `record`ed as an `abandoned` tool event, appended to the ring AND ingested into
     `<session>.focus.json`. It runs BEFORE the ambient check, so ambient prompts sweep too. Live:
     17 of session db80475a's 78 recorded prompts directly followed a sweep, 16 with refs.
   - then `Stm.record("input", …)` (`cli.py:1980-1981`) appends the input event and ingests the
     prompt's refs; the ring's `ts` is cut to the second (`stm.py:260`).

   So EVERY value a prompt-time reader computes from the ring or the graph (the event count, the
   turn, the topic list, the overlap, 19.6's phase) depends on scheduling, and no wall-clock
   margin on a second-truncated `ts` can separate this prompt from the last. The round-2 rule
   (`ts < t0 − 1 s`) is WITHDRAWN. Instead, one snapshot, one reader:
   - **Signature, exact:** `stm.pre_prompt_state(root: Path, session: str, prompt: str, *,
     t0: float) -> stm.PrePromptState`, a `NamedTuple(graph: dict, topic_cache: dict, turn: int,
     events_n: int, source: str)`, `source` ∈ `snapshot`, `live`. Same ownership rule as the
     resolver (first of 21.1 / 19.0 to merge builds it; 19.0 R7 restates it).
   - **Writer: the input hook's FIRST state access, not `Stm.record`** (round-4 #b-1). The input
     branch of `cli.focus_hook` runs, in this order:
     1. bug-109's pointer write (existing; no prompt-time reader resolves its session from the
        pointer, since every hook reader has its envelope, so it is not reader state);
     2. `s.snapshot_pre_prompt(prompt)` for EVERY non-empty prompt, ambient included;
     3. `s.inflight_sweep()`; its `except Exception: pass` (`cli.py:1977-1978`) becomes one stderr
        line plus a `sweep-failed` row (D8);
     4. when the prompt is not ambient, `s.record("input", prompt[:300])`.
     `Stm.snapshot_pre_prompt(prompt: str) -> None` writes `<session>.pre.json` = `{prompt_sha,
     wall, turn, events_n, graph, topic_cache}` by tmp + `os.replace`: `prompt_sha` = sha256 of
     the prompt's UTF-8 bytes, `wall` = `time.time()` (sub-second), `turn` = the graph's `turn`
     counter (`stm.py:427` increments it once per recorded input), `events_n` = R9's event count
     below, `graph` = the focus graph, `topic_cache` = 19.6 R3's cache (`{}` until 19.6).
     `Stm.record` no longer calls it. The appended input event gains `prompt_sha` and `t`
     (sub-second epoch).
   - **`events_n`** counts the ring's complete lines whose `origin` is `parent` or absent (19.0
     R2's field; round-4 #m-1). Background subagents' PostToolUse events land in the parent ring
     during the window (19.0 R2 keeps them there), and would otherwise move the count for a reason
     unrelated to the input hook. Until 19.0 R2 ships, no event carries `origin`, every line
     counts, and that residual is stated in `--agent-usage`'s footer.
   - **Reader.** It reads the LIVE state first (focus graph, ring count, topic cache), THEN
     `pre.json`. If `pre.prompt_sha == sha256(prompt)` and `|pre.wall − t0| ≤ S`, it returns the
     snapshot's values (`source=snapshot`); else the live values (`source=live`). This is exact
     because `pre.json` is written before the hook's first change to the ring, the graph or the
     cache (the sweep included): a reader that finds no matching snapshot AFTER reading the live
     state read a state the input hook had not yet touched. `t0` is `time.time()` read once at
     process entry.
   - **Ambient prompts** (round-4 #b-1). The sweep changes state on an ambient prompt too, so an
     ambient prompt writes a snapshot like any other (step 2) and its readers match it; only the
     input event is not recorded. The round-3 sentence "ambient prompts write no snapshot … state
     they never changed" is WITHDRAWN.
   - **`S`, measured on the interval the match compares** (round-4 #m-1). The match compares the
     reader's entry `t0` with the WRITER's `wall`, which is stamped after the writer's imports,
     envelope parse and pointer write. So 19.0 R0 logs, over ≥ 50 real prompts, the writer's
     `wall` and each parallel reader's `t0` (keyed by `prompt_sha`), and `S` = max(2 s, 3 × the
     largest measured `|wall − t0|`), committed as `stm.PRE_PROMPT_SKEW_S` with the measurement
     in its docstring. If R0 finds a per-prompt unique field in the UserPromptSubmit envelope, the
     snapshot is keyed by it instead and `S` is unused. Residual, stated: a prompt textually
     identical to the previous one and submitted within `S` of it reads the previous prompt's
     snapshot (one turn stale).
   - **Known limit, stated** (round-4 #m-1). `focus.json` is read-modify-written without a lock
     (`stm.py:405-424`), so a PostToolUse ingest concurrent with the input hook can lose one of
     the two updates. This predates the task; the snapshot does not fix it and does not claim to.

   **`turn`.** On prompt-time channels (`prompt_recall`, `scan_prompt`): `pre_prompt_state(…).turn`,
   the 0-based ordinal of this prompt among the session's RECORDED prompts (named `recorded_turn`
   in the report). On every other channel and on `used` events (they run while the agent answers,
   after the UserPromptSubmit hooks have finished): the live graph's `turn − 1`, the ordinal of the
   prompt being answered; `session_start` before any prompt logs `−1`. Null when the session has
   no ring or no session resolved. `lag_turns` (R12) is the difference of two such values.
10. **R10 The event fields.** One event per item per stage. The schema is versioned (`v: 1`).

    | field | meaning |
    |---|---|
    | `v`, `ts`, `session`, `turn`, `query_id` | R9; `query_id` equals the `query.log` row of the same call. **`ts` is UTC** (round-4 #s-2): `emit_recall_events` stamps it from ONE `time.time()` per call as ISO-8601 with milliseconds and `Z`, fixed width (`YYYY-MM-DDTHH:MM:SS.mmmZ`), so lexicographic order is time order and no reader depends on its own `TZ` or a DST change. Every other writer in the repo stamps local naive `time.strftime("%Y-%m-%dT%H:%M:%S")` (`telemetry.py:281`, `:329`, `:425`; `stm.py:260`); `query.log` rows keep that legacy form and are joined to events by `query_id`, never by `ts` |
    | `channel` | closed SURFACE enum, the ONE channel enum of C7: `session_start`, `prompt_recall`, `scan_prompt`, `precompact`, `context`, `recall`, `nudge` (bsd #b-2). `invocation` is a separate field with R2's values; `cli`/`mcp` are never channels, and no consumer may list them as channels (19.2 R3 uses this enum verbatim) |
    | `invocation` | R2 |
    | `name`, `entity_id`, `kind` | `name` is the stable key 19.2 counts by (a purge-and-re-add keeps history); `entity_id` is the catalog id at emission (code); `kind` ∈ `code`, `doc`, `concept`, `memory`, `session`, `subject`, mapped from the catalog kind by R10a, never copied raw |
    | `scope` | `project` or `global` (d8e) |
    | `partition` | the partition NAME the item's row was read from (for example `intuition` for project memories), resolved by the emitter from the hit row, never from the store's currently bound partition (bug-098's shape). 19.2 R1 keys on it and 23.1 R1.2 cuts batches on it. Never null on `retrieved` / `delivered` / `used`; an emitter that cannot resolve it writes no event for that item and counts the miss on stderr |
    | `cwd`, `root` | the emitting process's cwd and its resolved store root (the file the event is appended to belongs to `root`'s store, or to the global root for `scope=global`). R5's classifier reads them; they are never null (re-review #b-1) |
    | `rank`, `stage` | 1-based rank in the retrieval; `stage` ∈ `retrieved`, `delivered`, `used` |
    | `offset_bytes`, `bytes`, `payload_bytes` | `delivered` only. ONE unit for the whole schema: UTF-8 BYTES of the payload the command wrote to stdout (re-review #s-2; #t9-fixes). `offset_bytes` / `bytes`: the byte range of the line or object that NAMES the item; `payload_bytes`: the payload's total size. `delivered` means EMITTED. `seen` is NOT a field: 19.5 R2 derives it from these three and 19.5 R1's measured cap and preview size, and 19.5 is its only deriver |
    | `body_offset_bytes`, `body_bytes` | `delivered` only: the byte range of the item's body when the payload carries it separately from the naming line (19.1's pack appends bodies after all hook lines); null when the payload carries no separate body (the JSON renderer's object already contains it, inside `offset_bytes`/`bytes`) |
    | `arm`, `policy` | allocation arm ∈ `fixed`, `phased`, `phased+cache`, and the allocation policy version. Until 19.6 ships, every emitter writes `arm=fixed`, `policy=fixed-v0`; 19.6 chooses and logs the arm per prompt (d5b) |
    | `stm_session`, `stm_source`, `stm_events_n`, `focus_topics_n`, `overlap` | the RAW phase inputs at injection, on prompt-time channels (`session_start`, `prompt_recall`, `scan_prompt`, `precompact`): which ring was read (R9's resolver, never `latest_session`); `stm_source` = `pre_prompt_state`'s `source` (`snapshot` / `live`); R9's `events_n`: the ring's parent-origin event count BEFORE this prompt's input hook (the sweep's `abandoned` events excluded); the number of `stm.topic_composites` topics of the pre-prompt graph; and the prompt-term ∩ composite-member overlap against that same graph. On `prompt_recall` / `scan_prompt` all four come from ONE `stm.pre_prompt_state` call (R9), never from a second read of the live files. `session_start` and `precompact` have no prompt: they read the live state (`stm_source=live`) and log `overlap: null` |
    | `phase`, `restored_cluster_id` | the label the pre-registered rule computed (`cold`, `warm`, `return`, `new`), and on a topic-cache return the restored cluster id. Null until 19.6 writes them |
    | `block_id`, `block_sha`, `rev`, `unchanged` | versioned injection ([[exploration-session-phased-context#vi-evidence]]): the emitted block's stable id (`scan-prompt`, `prompt-recall`, and 19.6 R9's two composite blocks `stm-topic-expanded` / `stm-topic-collapsed`, …) and the sha256 of its body, filled by 21.1's emitters now; `rev` and `unchanged` are null until 19.6's versioned blocks write them. The byte-identical share is recomputable from `block_sha` + `payload_bytes` before 19.6 lands |
    | `evidence`, `ref_query_id`, `lag_turns` | `used` only: what showed the use, which delivered event it points back to, and after how many turns |

    The field list above is exported as `telemetry.RECALL_EVENT_FIELDS_V1` (a tuple of names) and
    every emitter writes every field (null where the table allows null). 19.2's fold imports the
    tuple; a consumer that keys on a field not in it fails its own test (19.2 AC-16).

    **R10a The `kind` map** (round-3 #s-1). Read at HEAD: the catalog's entity `kind` column takes
    `code`, `doc`, `concept` and `memory` (`cli.py:10272` `_DEFAULT_EMBED_KINDS`;
    `partitions.py:27`); `function` / `class` are `is_a` concepts (`kind/function`), not entity
    kinds; session cards and subjects are memory rows told apart by `mtype`. One function,
    `telemetry.event_kind(entity_kind: str, mtype: str | None) -> str | None`, the only place the
    map lives:

    | catalog `kind` | `mtype` | event `kind` |
    |---|---|---|
    | `code` | any | `code` |
    | `doc` | any | `doc` |
    | `concept` | any | `concept` |
    | `memory` | `subject` | `subject` |
    | `memory` | `session` | `session` |
    | `memory` | any other or null | `memory` |
    | anything else | any | `None`: no event for that item; the emitter prints one stderr line per call with the count (`unmapped_kind=<n>`) |

    A scan-prompt or context anchor that is a concept node is a `concept` item; a memory BODY that
    the payload carries for it (R11's attached body) is a separate `memory` item.

11. **R11 Named emitters** (bsd #b-3). Each surface below emits `retrieved` for every item its
    retrieval returned and `delivered` for every item in the payload it wrote:
    - `scan_prompt`: the `rmx scan-prompt` command (`scan.py`), the UserPromptSubmit hook;
    - `prompt_recall`: `rmx memory recall --stdin-json`, the per-prompt recall hook
      (`hooks.py:301-316`);
    - `session_start`: the SessionStart recall;
    - `precompact`: the PreCompact recall. Its `delivered` events are emitted, and consumers do NOT
      count them as delivered until 19.5's probe decides whether PreCompact stdout reaches the
      agent (d5d);
    - `context`: the context verb on all four routes of R3;
    - `recall`: `rmx memory recall` / MCP `rmx_memory_recall` called by the agent;
    - `nudge`: 21.3's hook (it emits `delivered` only).

    **ONE owner of `delivered`: this task** (re-review #s-1; #t9-fixes). The only writer of any
    recall event is `telemetry.emit_recall_events(events, *, root, global_root)` (it splits the
    list by `scope` across the two files of R8). Each surface calls it EXACTLY ONCE per call,
    after its payload is written, with `retrieved` events for every retrieved item and `delivered`
    events for the items the payload names. For the four recall channels (`session_start`,
    `prompt_recall`, `precompact`, `recall`) that single call site is in the `memory recall`
    command / verb; the RENDERER that wrote the payload (today's JSON renderer; later 19.1's
    `--pack`, which REPLACES the JSON renderer on the hook argv) only RETURNS the byte spans of
    R10 (`offset_bytes`, `bytes`, `body_offset_bytes`, `body_bytes`) and never emits. 19.1 is
    therefore a producer of spans that this emission site consumes, not a second emitter; 19.2
    consumes the events. A renderer that emits on its own doubles `delivered` (19.1 AC-6, AC-8
    here).

    **How the recall emission site picks its channel** (round-3 #b-3). One function,
    `telemetry.recall_channel(*, session_start: bool, stdin_json: bool, recent: bool,
    invocation: str) -> str`, first match wins:
    1. `--session-start` → `session_start`;
    2. `--stdin-json` → `prompt_recall`;
    3. `--recent` with `invocation == "hook"` → `precompact` (the only generated hook that runs
       `--recent` is PreCompact's, `hooks.py:340`; a test pins that by scanning the generated
       config, AC-8c);
    4. anything else (an agent's or a human's `rmx memory recall <q>` / `--recent`, the MCP
       `rmx_memory_recall`) → `recall`.

    **What scan-prompt and context deliver** (round-3 #b-3, #s-1). Read at HEAD: `scan.py` has no
    memory or partition retrieval of its own; memory text reaches its payload, and `rmx context`'s,
    only through `context.py:230-243`, where an anchor that resolved to a concept/doc/code node
    gets the same-named memory's body attached via `store.find_memory_any_partition`
    (`store.py:2504`). So:
    - each code / doc / concept item is a `delivered` event with its R10a kind and the partition of
      the row it was read from (the store's project partition for code and docs);
    - an attached memory body is ONE more `delivered` event: `kind` = R10a's map of that memory
      row (`memory`), `name` = the memory's name, `partition` = the memory row's own partition (for
      example `intuition`, or `memory-<project>`), `offset_bytes` / `bytes` = the anchor's naming
      line, `body_offset_bytes` / `body_bytes` = the attached body's span. 19.2 R3 counts these
      as hits. `find_memory_any_partition` returns `get_memory(id)`'s dict, chosen across
      partitions by longest content; this task makes the returned dict carry the chosen row's
      partition NAME (`partition`), so the event never takes the bound partition (bug-098's
      shape).
12. **R12 `used` events, fully specified** (bsd #s-2; re-review #b-5; #t9-fixes). Emitted only by
    an explicit call whose `invocation` is NOT `hook` (a `hook` call never emits `used`, so the
    helix confound cannot recur), and only when the named item is in the session's DELIVERED SET
    (below). `ref_query_id` = that delivered event's `query_id`; `name`, `kind`, `scope`,
    `partition` are copied from it; `lag_turns` = this call's `turn` minus its `turn`.
    - **`memory_get_by_name`**: `rmx memory get <name>` (CLI, `cli.py:11326`, on BOTH its verb path
      and its replica fall-through) and the MCP `rmx_memory` `get` action (`verbs.memory`,
      `verbs.py:1102`), when the lookup was by NAME (not by id) and `<name>` equals a delivered
      `name` with `kind=memory` and the same `scope` (`--scope global` per 19.1 R6 matches only
      `scope=global`). Recall's internal per-hit read (`_call(root, "memory_get", …)`,
      `verbs.py:766`) and the daemon op `_op_memory_get` never emit (19 #b-6).
    - **`context_by_name`**: `verbs.context` (`verbs.py:538`, the MCP route) and the three CLI
      context routes of R3, when the call's `ref`, stripped, equals a delivered `name` exactly
      (case-sensitive) AND this context call DELIVERED an item of that same `name` and the same
      `kind` as the delivered event: either its anchor (by R10a's kind), or, for `kind=memory`,
      the memory body it attached to a concept/doc/code anchor (R11; round-3 #s-1). So the
      documented common case, `rmx context <slug>` landing on the thin concept node with the
      memory's body attached, IS a use of the memory; a code symbol that shares a memory's name
      and gets no memory body attached is not. One context call emits at most one `used` per
      `(name, kind, scope)`.
    - **`focus_note`**: `verbs.focus_note` (`verbs.py:908`; the CLI `rmx focus note`, `cli.py:1411`,
      and the MCP `rmx_focus_note` both call it). The MATCHER, exact: the note text is scanned for
      (a) whole-token occurrences of a delivered `name`, where a token boundary is any character
      outside `[A-Za-z0-9_.-]` or the string edge, case-sensitive; and (b) wikilinks
      `[[<doc>]]` / `[[<doc>#<anchor>]]` whose `<doc>` equals a delivered `name`. Each distinct
      matched name emits ONE `used` event per note, however often it occurs. Only names of
      length ≥ 6 or containing one of `_ . -` are matchable, so a short delivered name (`run`,
      `rank`) cannot fire on prose. Edge cases, stated (round-3 #m-7):
      - **Sentence-final names.** `.` is a token character, so `…applied feedback_alpha_rule.`
        yields the token `feedback_alpha_rule.` and does NOT match. That under-counts, the safe
        direction for a never-decaying counter; the matcher does not strip punctuation.
      - **One name, several delivered keys.** When a matched name is in the delivered set under
        more than one `(kind, scope)` key (for example a `memory` and a `code` item of the same
        name), the note emits one `used` per key, each pointing to its own delivered event; 19.2
        counts only the `kind=memory` one.
    - **Whose session.** The caller's session is R9's resolver's, with `purpose="event"`: on the
      MCP route (`rmx_memory`, `rmx_context`, `rmx_focus_note`) the pid pointer of the MCP
      server's parent, re-read on every call, never the server's spawn-time
      `CLAUDE_CODE_SESSION_ID` (round-3 #b-1). With no resolved session, no `used` is emitted
      (counted, `used_no_session`); the newest ring is never used.
    - **The delivered set (the lookup).** `telemetry.delivered_in_session(session, *, root,
      global_root) -> dict[(name, kind, scope), event]` reads `recall-events.jsonl` of `root` and
      of `global_root` BACKWARDS from the end in 64 KB blocks, keeping `stage=delivered` events
      whose `session` equals the caller's, newest per key, and stops at the start of the file or at
      a hard cap of 4 MB read per file. It runs only on the three explicit calls above, never per
      prompt. Hitting the cap is counted (`used_lookup_cap_hits` in `--agent-usage`): a name
      delivered earlier than the cap reaches is then NOT matched, an under-count, which is the
      safe direction for a never-decaying counter. Events whose `session` is null are never in
      any delivered set. `precompact` deliveries are excluded from the set until 19.5 R1's
      verdict (d5d).
    - **Destination.** A `used` event goes to the file of the delivered event's `scope`: a use of
      a GLOBAL memory is appended to `~/.refmatrix/recall-events.jsonl` with `scope=global`
      (d8e), so 19.2's global fold counts it; a project use to the project file.
    - **Reserved, not emitted here:** `file_read` and `cited_in_answer`. Their only computation is
      19.6's offline transcript scorer (`eval/production/phased_context/`, 19.6 Table C), which
      writes its own report and never appends to `recall-events.jsonl`; so no live counter ever
      depends on them.

## Acceptance criteria {#acceptance}

Every AC runs inside 23.0's sandbox and ends by asserting that the live `.refmatrix/query.log`,
`~/.refmatrix/query.log`, `.refmatrix/recall-events.jsonl` and `~/.refmatrix/recall-events.jsonl`
line counts are unchanged.

1. **MCP route.** An MCP `rmx_context` call through the real stdio server (a subprocess; `HOME` =
   tmp, `REFMATRIX_ROOT` = tmp, `RMX_HUB_MODELS=0`, short root for `sun_path`) produces exactly one
   `query.log` row with `invocation=mcp`, `kind=context`, `source=context-mcp`, a non-null
   `query_id`, and `session` equal to the session of the pid pointer the test wrote for the
   server's parent (the test process) through the GENERATED SessionStart hook command. RED at
   post-bug-109 `master`: the failing assertion is the row count (no `context-mcp` row exists).

   **1b. Session switch under ONE long-lived server** (round-3 #b-1; re-baselined in round 4
   #s-1 against post-bug-109 `master`, which already re-points the server from the INPUT hook).
   The test extends `tests/test_mcp_session_pointer.py` (bug-109's file; no parallel file). It
   starts `rmx mcp` with `CLAUDE_CODE_SESSION_ID=A` in its environment and keeps it running.
   - **Generator (RED at post-109 `master`; failing assertion: the entry is absent).** The
     generated hook config holds a SessionStart entry, matcher `startup|resume|clear|compact`,
     running `rmx focus hook --event session-start` without `2>/dev/null`.
   - **Switch BEFORE any prompt (RED at post-109 `master`; failing assertion: `session == B`).**
     That generated command, fed `{session_id: A, source: startup}` then
     `{session_id: B, source: clear}` with the test process as the Claude owner (the server's
     parent), and NO input-hook run after the clear: an `rmx_context` call logs a `context-mcp`
     row with `session == B`; an `rmx_focus_note` lands in B's ring (A's ring line count
     unchanged); the pointer file's `hook` field reads `session-start:clear`.
   - **`used` after the switch (RED: no `used` events exist).** With a memory
     `feedback_alpha_rule` delivered in B (a `prompt_recall` run through the generated hook with
     B's envelope), an `rmx_focus_note` naming it emits one `used` event with `session == B` and
     `ref_query_id` = that delivery's `query_id`.
   - **Unresolved write (RED at post-109 `master`; failing assertion: A's ring line count
     unchanged).** With the pointer file deleted and no `RMX_SESSION`, the next `rmx_context` row
     carries `session: null`, and `rmx_focus_note` returns a `SessionUnresolved` tool error;
     bug-109 instead writes the note to the newest ring.
   - **Regression guard, GREEN at post-109 `master` and not counted as RED:** the input-hook
     re-point (`focus hook --event input` with B's envelope) still switches the server to B.
2. **CLI routes.** On a tmp store, `rmx context X` forced down each of the replica, daemon and
   direct routes writes exactly one row with the route's `source`. RED at HEAD for
   `context-daemon` (no row).
3. **Precedence.** `invocation_source()` returns, for the env combinations
   {explicit `hook` + `CLAUDECODE`, `CLAUDECODE` alone, tty alone, none}: `hook`, `agent`,
   `interactive`, `unknown`. RED at HEAD on `CLAUDECODE` alone (returns `unknown`).
4. **Session never guessed** (round-4 #s-1: bug-109's names). Two `rmx scan-prompt` runs in ONE
   tmp root, fed envelopes with different `session_id`s, plus a newer STM ring for a third
   session id on disk, log disjoint `session` values equal to their own envelopes' ids. With no
   envelope, no pointer for the owner and no `RMX_SESSION` (and `CLAUDE_CODE_SESSION_ID` set to
   the third id, which no path reads), `session` is null, not the third ring's id, and
   `_errors.jsonl` gains one `pointer-unresolved` row. A pointer whose `pid_start` does not match
   the live process's start time is ignored (`session` null) and recorded as `pointer-stale`.
   RED at post-109 `master`: the failing assertions are `session is None` (bug-109 returns the
   newest ring, source `latest`) and the `pointer-stale` row (bug-109 returns `None` silently).

   **4b. Pointer location, SessionStart surfacing and cleanup** (D3, D6, D7; bug-109 r1 #m-4).
   (i) The input hook run with cwd in tree X writes the pointer under the sandbox's global
   `by-pid/`; an MCP server spawned with cwd in tree Y resolves it. (ii) A pointer present only at
   bug-109's legacy `<root>/stm/by-pid/` resolves once and records `pointer-legacy-location`.
   (iii) With three `_errors.jsonl` rows added since the watermark, the generated SessionStart
   command prints one stdout line naming their reasons and counts, and a second run prints none.
   (iv) A pointer for a pid absent from the process table is removed by the SessionStart run and
   `pruned=1` is printed. RED at post-109 `master` for each leg (no global location, no
   SessionStart entry).
5. **`grep-stdin` cardinality.** `printf 'a\nb\nc\nd\n' | rmx grep -E 'a|b|c'` logs a
   `grep-stdin` row with `cardinality=3`. RED at HEAD (`null`).
6. **The frozen fixture** (bsd #s-3). A REDACTED copy of this project's `query.log` and `cli.log`
   cut at `2026-10-07T11:06:35` (bodies replaced by their sha256 and paths scrubbed, per d8f;
   counts are invariant under redaction) is committed under `tests/fixtures/agent_usage/`.
   `rmx telemetry --agent-usage --since 2026-09-23 --until 2026-10-07T11:06:35` on it prints
   EXACTLY: 3 context calls (`context-replica`), 1,119 `grep-replica` greps, 34 memory recalls
   (not 68: `phase=start` rows excluded). The cut excludes the 20 replay rows of
   2026-10-07T11:06:35-11:07:13 by window. Every row in the fixture is legacy (no `cwd`/`root`
   at HEAD), and per R5's totals rule they ARE counted, so the same run also prints
   `excluded_test_rows=0 legacy_fixture_rows=0 legacy_unattributed=<L>`, where `<L>` is the
   number of fixture rows inside the window, counted by the fixture-cutting script and written
   into this AC when the fixture is committed (before GREEN).
7. **The classifier** (d8d, d9g; re-review #b-2). The report runs on a sandbox store root `R`
   (under 23.0's `/tmp/rmx-*` root) over a `query.log` holding five rows:
   (a) `cwd` = `/private/var/folders/x/pytest-of-u/pytest-7/test_a0`, `root` = that path +
   `/.refmatrix`; (b) `cwd`/`root` inside `R`'s project; (c) a legacy row (no `cwd`/`root`)
   with `kind=grep`, `body="foo"`; (d) a legacy row with `kind=grep`, `body="alpha|beta"`;
   (e) a legacy row with `kind=grep`, `body="alpha"`. `--agent-usage` counts 3 (b, c, e) and
   prints `excluded_test_rows=1 legacy_fixture_rows=1 legacy_unattributed=2`. Unit cases of
   `row_provenance`:
   - a row whose `root` is ANOTHER `/tmp/rmx-*` sandbox is `test_artifact` for a reader at `R`
     and for a reader at a non-temp root; a row from `R`'s own sandbox is `attributed` for a
     reader at `R`;
   - **two test bases** (round-3 #s-3): a row with `root` inside `R`'s sandbox and `cwd` =
     `/private/var/folders/x/pytest-of-u/pytest-7/test_b0` is `attributed` for a reader at `R`;
     the same with `cwd` = the repo is `attributed`; a row with `root` in pytest temp and `cwd`
     inside `R` is `test_artifact` for a reader at `R`;
   - a row with `cwd` in pytest temp and no `root` is `test_artifact` for a reader at `R` (the
     cwd fallback);
   - a live-tree row (`root` = `/Users/x/proj/.refmatrix`) read by a reader at `R` is NOT
     `test_artifact` (`attributed`).

   **Event leg** (round-3 #s-3; round-4 #s-2). The same five rows written as events, with c-e
   stripped of `cwd`/`root`, plus (f) an event whose `channel` is `cli` and (g) b with its `ts` in
   the legacy local naive form (`2026-10-14T14:04:41`, no `Z`), classified by
   `row_provenance(…, source="events")`: c-g are `malformed`, a and b as above; the event reader
   prints `malformed=5 unparseable=<n>` and folds only b. A test asserts that the report, 19.2's
   fold module and 21.4's draw script import `row_provenance` from `telemetry`, define no
   predicate of their own, and contain no check for missing `cwd`/`root` or for the channel enum
   (the `malformed` rule lives only in the function).
8. **Real emitters** (bsd #b-3). On a tmp store whose PROJECT partition holds an indexed code
   and doc corpus (each item's naming line preceded by `—` in its rendered text, see AC-8d) and
   whose partition `intuition` holds 10 indexed memories, plus a seeded STM ring for the
   envelope's session (5 recorded inputs, 2 focus topics), one real `rmx scan-prompt` run and one
   real `rmx memory recall --stdin-json` run, each fed a recorded UserPromptSubmit envelope on
   stdin through the GENERATED hook command line (not a direct function call), run with cwd = the
   tmp project dir, append to `recall-events.jsonl`:
   - per surface, one `retrieved` event per retrieved item and one `delivered` event per emitted
     item, all sharing that call's `query_id` and the envelope's `session_id`;
   - `offset_bytes + bytes ≤ payload_bytes`, `payload_bytes` equal to the BYTES the command wrote
     to stdout, and for every `delivered` event the payload's bytes in
     `[offset_bytes, offset_bytes + bytes)` contain the item's `name`;
   - a recall run whose payload carries 3 of 10 retrieved items logs exactly 10 `retrieved` and 3
     `delivered`;
   - **partition, per leg** (round-3 #b-3): every `memory recall` event carries
     `partition == "intuition"`; every scan-prompt code/doc event carries the PROJECT partition's
     name, and its `kind` is R10a's map of the row (`code`, `doc`, `concept`); scan-prompt's memory
     case is AC-11e's attached body, not this leg;
   - every event carries `cwd` == the tmp project dir, `root` == the tmp store root, and every
     field of `telemetry.RECALL_EVENT_FIELDS_V1` as a key;
   - **phase and versioned-injection fields** (re-review #s-3): on both prompt-time channels,
     `stm_session` == the envelope's session, `stm_events_n` == the seeded ring's event count,
     `focus_topics_n` == 2, `overlap` is a non-null number, `arm == "fixed"`,
     `policy == "fixed-v0"`, `block_id` is the surface's id (`scan-prompt`, `prompt-recall`), and
     `block_sha` == sha256 of the exact stdout bytes of that block.

   **8b. Every phase input is order-independent** (re-review #s-3; round-3 #b-2; round-4 #b-1).
   The seeded ring's prompt terms are chosen so this prompt's own terms CHANGE the graph (they
   join an active topic), AND the seeded in-flight sidecar holds one call parked 120 s ago (more
   than the sweep's 90 s) whose refs also join the active topic, so the sweep changes the ring
   count and the graph before the input record does. The same `memory recall` envelope, and
   separately the same `scan-prompt` envelope, is run four ways against copies of the seeded
   store:
   - (i) the input hook (`focus hook --event input`, the generated command, same envelope) runs to
     completion BEFORE the reader starts;
   - (ii) it runs AFTER the reader finishes;
   - (iii) only its first state step has run: the test calls `Stm.snapshot_pre_prompt(prompt)`,
     runs the reader, then `s.inflight_sweep()` and `s.record("input", prompt)`;
   - (iv) the snapshot AND the sweep have run, the input record has not: the reader runs between
     `inflight_sweep()` and `record("input")`.
   R9's writer is these public steps in this order, so no test-only switch exists in `src/`. All
   four log identical `turn` (5), `stm_events_n` (the seeded count, the swept call EXCLUDED),
   `focus_topics_n` and `overlap`, equal to (ii)'s values, with `stm_source` `snapshot` in (i),
   (iii) and (iv) and `live` in (ii). An earlier prompt with IDENTICAL text whose `pre.json`
   `wall` is `stm.PRE_PROMPT_SKEW_S + 1` s old is not matched (`stm_source` `live`) and is counted
   in `turn`.
   - **Ambient leg.** An ambient prompt (`<task-notification …>`) with the same parked call: (i)
     and (ii) log identical `stm_events_n` and `focus_topics_n`, (i) with `stm_source=snapshot`,
     and the ring gains the swept event but no input event.
   - **Pre-check, recorded before GREEN:** in the seeded copy, running the input hook changes the
     ring count by 2 (one swept, one input) and the graph's member set of the active topic, so the
     fixture is not vacuous.

   **8c. Every channel's emitter, through its real entry point** (round-3 #b-3). On the AC-8
   store, each of these appends its own channel's events, checked per channel for the event set
   (`retrieved` count, `delivered` count, `channel`, `kind`, `partition`, shared `query_id`):
   - `session_start`: the GENERATED SessionStart recall command, with a SessionStart envelope;
   - `precompact`: the GENERATED PreCompact recall command (`--recent`, under
     `RMX_INVOCATION_SOURCE=hook`); a test scans the generated hook config and asserts that this
     is the only generated command combining `memory recall` with `--recent`;
   - `recall`: an agent `rmx memory recall <q>` (`CLAUDECODE=1`) AND an agent `rmx memory recall
     --recent` (channel `recall`, not `precompact`: invocation is `agent`);
   - `context`: an MCP `rmx_context` call through the stdio server (AC-1's harness) and a CLI
     `rmx context` call;
   - `nudge`: not this task's emitter. 21.3 owns the nudge hook (Wave 3) and its AC-2 runs the
     GENERATED PostToolUse hook and asserts one `channel=nudge` `delivered` event, with the
     emitter-removal mutation registered there ([[task-21.3-indexed-symbol-nudge#acceptance]]);
   - `scan_prompt` and `prompt_recall`: AC-8.
   Each channel's leg fails if that channel's emitter call is removed.

   **8d. The multibyte fixture reaches a non-ASCII byte path** (round-3 #b-3, #m-3). Read at
   HEAD: `memory recall --json` prints `json.dumps(rows, indent=2)` with the default
   `ensure_ascii=True` (`cli.py:12110`, `:12322`), so its payload is ASCII and byte offsets equal
   character offsets there: a chars-vs-bytes mutation cannot fail on the recall leg until 19.1's
   `--pack` text replaces it (19.1 AC-1 and AC-6 own that leg). The text payload of `scan-prompt`
   (the hook's format) carries raw UTF-8. AC-8d therefore asserts, on the scan-prompt leg:
   - the payload's stdout bytes contain at least one byte ≥ 0x80 BEFORE the first delivered
     span's `offset_bytes` (a guard that the fixture is not vacuous; it fails if the corpus loses
     its `—`);
   - the multibyte excess before the LAST delivered span (bytes minus characters up to it) is ≥ 6
     (three `—`), larger than any naming line's slack in the fixture, recorded as a pre-check;
   - every delivered span's bytes contain its `name` (AC-8's check), which a character-counted
     offset fails by at least 6 bytes.
9. **One format.** A test enumerates every writer of a `*.jsonl` file under `src/refmatrix/` and
   fails on any new file name that carries recall items other than `recall-events.jsonl`.
10. **Global scope** (d8e). A recall that returns one project and one global memory appends the
    global hit to the GLOBAL root's file with `scope=global` and `name` set, and the project hit to
    the project file.
11. **`used`, one AC per evidence kind** (re-review #b-5). In one session `S`, a `prompt_recall`
    delivers project memory `feedback_alpha_rule` and global memory `reference_beta_ref`:
    - **11a `memory_get_by_name`.** An agent-invocation (`CLAUDECODE=1`) `rmx memory get
      feedback_alpha_rule` emits one `used` event, `evidence=memory_get_by_name`, `ref_query_id`
      = the delivering call's `query_id`, in the PROJECT file. The same command with
      `RMX_INVOCATION_SOURCE=hook` emits none; the recall's internal per-hit read emits none; a
      `memory get <id>` by id emits none; the same name in session `S2` emits none.
    - **11b `context_by_name`.** `rmx context feedback_alpha_rule` (anchor resolves to the memory)
      emits one `used` event. A code symbol named `feedback_alpha_rule` in the tmp store, delivered
      in `S` by `scan_prompt` with `kind=code`, makes `rmx context` on it emit one `used` with
      `kind=code` and NONE with `kind=memory`.
    - **11c `focus_note`.** A note whose text is
      `applied feedback_alpha_rule, then feedback_alpha_rule again; see [[reference_beta_ref#why]]`
      emits exactly two `used` events (one per distinct name), the global one in the GLOBAL file with `scope=global`. A second note
      `"see feedback_alpha_rules and run it"` emits none (a longer token; and `run`, delivered in
      `S` as a code item, is below the matchable length).
    - **11d lookup bound.** With 6 MB of other sessions' events appended after the delivery, the
      lookup reads ≤ 4 MB per file (counted by the reader), emits no `used`, and increments
      `used_lookup_cap_hits`.
    - **11e the concept-anchor case** (round-3 #s-1). The tmp store holds a memory
      `feedback_gamma_rule` in `intuition` AND a concept node of the same name in the project
      partition (as the bridge produces: the title spawns a concept). `rmx context
      feedback_gamma_rule` anchors on the concept and attaches the memory body; its events are one
      `delivered` `kind=concept` (project partition) and one `delivered` `kind=memory`
      (`partition == "intuition"`, body span set). After a `prompt_recall` delivered that memory
      in `S`, the same `rmx context` call by the agent emits exactly one `used`, `kind=memory`,
      `evidence=context_by_name`. With the memory deleted (concept only, no body attached), the
      call emits no `kind=memory` `used`.
    - **11f focus-note edges** (round-3 #m-7). In `S`, with `feedback_alpha_rule` delivered as a
      memory: the note `applied feedback_alpha_rule.` emits none (sentence-final, under-count
      stated); with a code symbol `feedback_alpha_rule` ALSO delivered by `scan_prompt`, the note
      `applied feedback_alpha_rule now` emits two `used` events, one per key (`memory`, `code`).

12. **The `kind` map** (round-3 #s-1). `telemetry.event_kind` returns R10a's value for every row
    of its table, and `None` (with the stderr count) for an unknown kind. After ingesting AC-8's
    tmp corpus, a test enumerates the distinct entity `kind` values and, for memory rows, their
    `mtype` values, and asserts every pair maps to a non-`None` kind, so a new catalog kind fails
    here, not silently.
13. **Mutations that must FAIL a test** (pre-registered):
    - the MCP env set after the first verb call (AC-1);
    - the `query.log` row written inside `_op_context` under the lock (AC-1: a lock-held probe sees
      the write; the caller-side assertion fails);
    - `context-daemon` route row removed (AC-2);
    - `CLAUDECODE` checked before the explicit env (AC-3);
    - `session` falling back to `stm.latest_session` for `purpose="event"` (AC-4);
    - the MCP server resolving its session once at spawn, or from `CLAUDE_CODE_SESSION_ID`
      (AC-1b: the row, the note and the `used` land on A);
    - the pid pointer not rewritten on a `clear` SessionStart (AC-1b's switch-before-prompt leg);
    - a `write` resolution keeping bug-109's newest-ring tail (AC-1b's unresolved-write leg);
    - the pointer's `pid_start` check dropped (AC-4: the stale pointer resolves), or the stale
      pointer returning `None` without its `pointer-stale` row (AC-4);
    - the pointer written under the hook's own store root instead of `stm.pointer_dir()` (AC-4b
      (i));
    - `_errors.jsonl` not surfaced by the SessionStart writer, or surfaced twice (AC-4b (iii));
    - `ts` stamped in local time or without `Z` (AC-7's event g is folded; 19.2 AC-6's two-zone
      replay differs);
    - `grep-stdin` cardinality left unset (AC-5);
    - `phase=start` rows counted (AC-6: 68, not 34);
    - each reader given its own copy of the predicate (AC-7);
    - the legacy rule flipped to EXCLUDE `legacy_unattributed` rows (AC-6 prints 0 / 0 / 0, and
      AC-7 counts 1): the AC-6 / AC-7 pair fails together;
    - the d9g shape loosened to `body` containing `alpha` (AC-7: row e excluded);
    - `reader_root` ignored, so a sandbox reader drops its own rows (AC-7's own-sandbox case);
    - the classifier keyed on `cwd` instead of `root` (AC-7's two-test-base case: a sandbox row
      with a pytest-temp cwd becomes `test_artifact`);
    - a base-`None` row classified `test_artifact` for a sandbox reader (AC-7's live-tree case);
    - the `malformed` rule moved out of `row_provenance` into a reader (AC-7's import/no-check
      assertion), or the channel-enum check dropped from it (AC-7: event f folded);
    - each surface's emitter removed, one at a time: `scan_prompt`, `prompt_recall` (AC-8);
      `session_start`, `precompact`, `recall`, `context` (AC-8c, one leg each); `nudge` is
      registered in 21.3's list (its AC-2);
    - `recall_channel` mapping `--recent` to `precompact` without the `hook` check (AC-8c: the
      agent's `--recent` logs `precompact`);
    - `delivered` logged for every retrieved item (AC-8: 10, not 3);
    - the JSON renderer emitting its own `delivered` events beside the single emission site
      (AC-8: 6, not 3);
    - `partition` dropped from the emitter, or taken from the store's bound partition instead of
      the hit row (AC-8 seeds the recall hits in `intuition` while the CLI's bound partition is
      the default; AC-11e's attached body lives in `intuition` while its concept anchor is in the
      project partition);
    - `cwd` / `root` dropped from events (AC-8; AC-7's event leg);
    - offsets counted in characters (AC-8d, on the scan-prompt leg: ≥ 6 bytes of multibyte excess
      precede the last span, so its name check fails; the recall leg's JSON is ASCII and is NOT
      claimed here, 19.1 AC-1/AC-6 own the `--pack` leg);
    - an emitter writing null phase fields or a `block_sha` of anything but its stdout bytes
      (AC-8);
    - any phase input (`turn`, `stm_events_n`, `focus_topics_n`, `overlap`) read from the live
      files instead of the one `pre_prompt_state` call (AC-8b: run (i) differs from (ii));
    - `pre.json` written AFTER the ring append or the graph ingest (AC-8b: run (iii) differs);
    - the snapshot taken inside `record("input")`, after the sweep (round-4 #b-1; AC-8b: (i) and
      (ii) disagree on `stm_events_n` by the swept call, and (iv) differs);
    - the snapshot skipped for ambient prompts (AC-8b ambient leg: (i) reads the post-sweep
      state);
    - `events_n` counting `origin: agent:<id>` lines once 19.0 R2 ships (19.0 AC-6d's subagent
      leg);
    - the snapshot matched on `prompt_sha` alone without the `wall` window (AC-8b: the older
      identical prompt is matched);
    - global hits written to the project file (AC-10);
    - `used` emitted for `invocation=hook` (AC-11a);
    - `context_by_name` matching without the kind check (AC-11b);
    - `context_by_name` matching the anchor only, not the attached memory body (AC-11e: no `used`);
    - an attached memory body logged with the concept's kind or partition (AC-11e);
    - the `focus_note` matcher stripping trailing punctuation (AC-11f: the sentence-final note
      emits one), or emitting one event per name instead of per key (AC-11f: 1, not 2);
    - an unknown catalog kind copied raw instead of mapped (AC-12);
    - the `focus_note` matcher as a substring match (AC-11c: `feedback_alpha_rules`), or emitting
      per occurrence (AC-11c: 3, not 2);
    - a global `used` written to the project file (AC-11c);
    - an unbounded lookup (AC-11d).

## Files to modify {#files-to-modify}

| file | change |
|---|---|
| `src/refmatrix/mcp.py` | set `RMX_INVOCATION_SOURCE=mcp` in `serve_stdio` before the first request and drop `CLAUDE_CODE_SESSION_ID` from its env (R1). `verbs._LONG_LIVED = True` and the per-call resolution are bug-109's, existing |
| `src/refmatrix/verbs.py` (resolver) | EXTEND bug-109's `resolve_session_source`: `SessionResolution`, `envelope=`, required `purpose=` and its three tails, `SessionUnresolved` (D1, D2); bug-109's `resolve_session` str wrapper is removed, its callers pass `purpose` |
| `src/refmatrix/stm.py` | EXTEND bug-109's pointer code: `pointer_dir()` and the user-level location with the legacy read (D3), the `hook` field (D4), `pointer-stale` / `pointer-unreadable` rows (D5), `record_pointer_error` without `root` (D8), the `_errors.jsonl` surfacing and watermark (D6), the prune (D7). NEW: `snapshot_pre_prompt`, `pre_prompt_state` + `PrePromptState`, `PRE_PROMPT_SKEW_S`; input events gain `prompt_sha` and `t` (R9). Built here or by 19.0, whichever merges first |
| `src/refmatrix/hooks.py`, `cli.py` (`focus hook`, `focus show`) | the generated SessionStart entry `rmx focus hook --event session-start` (matcher `startup\|resume\|clear\|compact`, stderr kept) that writes the pointer, surfaces `_errors.jsonl` and prunes (D4, D6, D7); the input branch reordered: pointer write (existing) → `snapshot_pre_prompt` → sweep (failure recorded) → input record (R9); `focus show` prints the pointer-error line (D6) |
| `tests/test_mcp_session_pointer.py` | EXTENDED, not paralleled (bug-109's file): AC-1b, AC-4, AC-4b |
| `src/refmatrix/store.py` | `find_memory_any_partition` (`:2504`) returns the chosen row's partition name (R11) |
| `src/refmatrix/telemetry.py` | `agent` source + precedence; `session`/`query_id`/`cwd`/`root` on rows; `row_provenance` + `is_test_artifact_row` (R5); the `--agent-usage` report; `RECALL_EVENT_FIELDS_V1`; `emit_recall_events` (the ONE writer, R11); `delivered_in_session` (R12's lookup); `event_kind` (R10a); `recall_channel` (R11); `turn` from `pre_prompt_state` (R9) |
| `src/refmatrix/verbs.py` | caller-side row + events for `context` (`:538`) and `memory_recall` (MCP route); `used` emission in `context`, `memory` `get` action (`:1102`) and `focus_note` (`:908`) |
| `src/refmatrix/cli.py` | `context-daemon` row; `grep-stdin` cardinality; `--agent-usage`/`--until`/`--by-session`; events on the CLI context and recall routes; `used` on `memory get`'s replica fall-through (`:11326`) and the three CLI context routes |
| `src/refmatrix/scan.py` | `scan_prompt` emitter with payload byte spans, `partition`, and raw phase inputs |
| `src/refmatrix/cli.py` (`memory recall`), `hooks.py` | the single recall-channel emission site (`prompt_recall`, `session_start`, `precompact`, `recall`); the JSON renderer returns byte spans; the generated hook lines carry the envelope through |
| `tests/fixtures/agent_usage/` | the redacted frozen `query.log`/`cli.log` cut |

## Test strategy {#test-strategy}

- **Sandbox:** every test runs under 23.0's sandbox ($HOME, global root, registry and LaunchAgents
  redirected before `refmatrix` is imported; spawned `rmx` children refuse sockets outside the tmp
  dir). Subprocess tests additionally pass `HOME`, `REFMATRIX_ROOT` and `RMX_HUB_MODELS=0`
  explicitly, because bug-088's recorder cannot see a child's connects. Each test asserts the live
  log line counts above are unchanged; no test writes the log this task measures (bsd #s-7).
- **RED first** (`feedback_red_test_must_fail_at_head`), against post-bug-109 `master` (round-4
  #s-1), not against the pre-bug-109 tree: AC-1, AC-2 (`context-daemon`), AC-3 (`CLAUDECODE`),
  AC-1b (its four RED legs; its input-hook leg is a GREEN regression guard), AC-4, AC-4b, AC-5,
  AC-7, AC-8, AC-8b, AC-8c, AC-8d, AC-10, AC-11a-f and AC-12 are run before any `src/` change
  and the FAILING ASSERTION is recorded, by name. A test that fails only because a click choice
  (`--event session-start`) or a keyword (`purpose=`) does not exist yet is RED for the wrong
  reason: each such AC first asserts on observable state (the generated config, a row, a ring
  line count) so the recorded failure is that assertion. AC-6 fails at HEAD because
  `--agent-usage` does not parse. No AC is admitted that passes at post-109 `master`.
- **Hook path:** AC-8 runs the command string `hooks.py` GENERATES for UserPromptSubmit, not a
  hand-written one, so a generator change that drops the emitter is caught.

## Revision (2026-10-14 decision log) {#rev-2026-10-14}

| finding or decision | answered at |
|---|---|
| bsd #b-1 (session, query_id, join key) | [[#req-session]] R9; R4; AC-1, AC-4 |
| bsd #b-2 (name key, channel enum) | R10 (`name`, `entity_id`, `channel`); AC-10 |
| bsd #b-3 (no production emitter, no sink) | R8, R11; AC-8, AC-9 |
| bsd #s-1 (delivered vs seen) | R10 (`offset_bytes`, `bytes`, `payload_bytes`); AC-8 |
| bsd #s-2 (phase fields, `used` emitter) | R10 (`arm`, `policy`, raw inputs, `restored_cluster_id`), R12; AC-11 |
| bsd #s-3 (AC-4 cannot fail) | R7; AC-6 |
| bsd #s-4 (`-E` not reproduced) | R6; AC-5 |
| bsd #s-5 (CLI daemon route, `ann_search`, MCP tools) | R3, R7; AC-2 |
| bsd #s-6 / d4f (agent stays unknown) | R2; AC-3 |
| bsd #s-7 / d1a, d1b (tests touch live logs) | [[#test-strategy]]; [[#acceptance]] preamble |
| bsd #m-1 (`mcp` already a source) | R1 |
| bsd #m-2 (`telemetry` is a command) | R7 |
| bsd #m-4 / d4a (dependency and sink) | header; R8 |
| bsd #m-3, #m-5, #m-6, #m-7 | not this task: 21.3 (#m-3, #m-5, #m-6), plan `#decisions` (#m-7) |
| d4a + d2a amendment (retained replay source, tail reader) | R8 |
| d5b (turn logged, never a phase signal; 19.6 owns the arm) | R9, R10 |
| d5d (PreCompact not counted as delivered) | R11 |
| d8d (shared pytest-temp predicate) | R5; AC-7 |
| d8e (`scope`, global hits in global store) | R8, R10; AC-10 |
| d8f (redacted fixture) | AC-6 |
| decision-log #m-2 (`CLAUDECODE` precedence) | R2 |
| exploration #vi-evidence (`block_id`, `rev`, `unchanged`) | R10 |
| #t8-wave1 (21.1 needs only 23.0) | header |

## Revision round 2 (2026-10-14) {#rev-round-2}

Answers [[bsd-plan19-21-spec-rereview-32dde06]] and [[plan-review-2026-10-14#t9]] /
[[plan-review-2026-10-14#t9-fixes]]. Code facts re-read at `3357c44`.

| finding / decision | answered at |
|---|---|
| re-review #b-1 (no `partition`, `cwd`, `root` on events; one channel enum) | R10 (`partition`, `cwd`, `root`; the ONE channel enum, `cli`/`mcp` never channels; `RECALL_EVENT_FIELDS_V1`); AC-8; mutations. The consumer side is 19.2 R3, AC-16 |
| re-review #b-2 (AC-6 vs AC-7) / #t9-fixes "legacy rows counted with a separate printed count" | R5 totals rule (Option A); AC-6 (`legacy_unattributed=<L>` printed); AC-7 (five rows); the paired mutation |
| d9g (the 235 fixture rows by exact shape, own count) | R5 class 2 (`kind=grep`, body exactly `alpha\|beta`, no `cwd`/`root`; 235 verified read-only); AC-7 rows d, e; mutation |
| d8d predicate owned by 21.1 in `telemetry.py` (#t9-fixes) | R5 (exact signatures; `reader_root`; test base incl. 23.0's `/tmp/rmx-*` root) |
| re-review #b-5 (`used` matcher, lookup, global destination, call sites, an AC per evidence) | R12; AC-11a-d; mutations; [[#files-to-modify]] |
| re-review #s-1 / #t9-fixes "one owner for `delivered`" | R11 (owner = this task's single emission site; renderers return spans; 19.1's pack replaces the JSON renderer and emits nothing); AC-8 mutation |
| re-review #s-2 / #t9-fixes "one unit (bytes)" | R10 (bytes; `body_offset_bytes`/`body_bytes`; `seen` derived only by 19.5 R2); AC-8 byte-range check; mutation |
| re-review #s-3 (phase / `block_sha` ACs; `turn` race) | R9 (race-free `turn`); AC-8 phase clause; AC-8b; mutations |
| plan-21 open item 2 (transcript scorer owner) | R12 reserved evidences (19.6's offline scorer; never appended to the live log) |
| cross-plan: 23.0 AC-4 calls `telemetry.is_test_artifact_row(row)` | R5 (`reader_root` optional; `None` = a live reader), so the call 23.0 names is valid as written |

## Revision round 3 (2026-10-14) {#rev-round-3}

Answers [[bsd-plan19-21-spec-rereview-r3-6091648]]. Code facts re-read at `636b210` (read-only):
`hooks.py:209-213`, `:270-290`, `:301-345`; `stm.py:123-140`, `:246-282`, `:405-445`;
`verbs.py:519-530`; `cli.py:1060-1078`, `:1964`, `:12110`, `:12322`; `context.py:225-243`;
`store.py:2504-2524`; `scan.py:970-980`; the live MCP process (`rmx mcp` pid 59378, ppid 59363 =
`CLAUDE_PID`).

rel: derives-from -> [[bsd-plan19-21-spec-rereview-r3-6091648]]

| finding / decision | answered at |
|---|---|
| round-3 #b-1 (the MCP server's `CLAUDE_CODE_SESSION_ID` is frozen at spawn) | R1 (long-lived, per-call resolution, env var dropped); [[#req-session]] R9 (`stm.resolve_session`, the pid pointer, its two writers, pid-reuse check; ownership shared with 19.0 R5); R12 "Whose session"; AC-1 (pointer session), AC-1b (A→B under one server), AC-4 (stale pointer); mutations |
| round-3 #b-2 (sibling phase inputs racy; second-truncated `ts`) | R9 pre-prompt state (`snapshot_pre_prompt` before append/ingest; `pre_prompt_state` reads live then snapshot; `S` measured by 19.0 R0; the `t0 − 1 s` rule withdrawn); R9 `turn` per channel; R10 (`stm_source`; all four inputs from one call); AC-8b (three orderings, all inputs, both prompt-time surfaces); mutations |
| round-3 #b-3 (five emitters untested; ASCII JSON; scan-prompt partition; no channel rule) | R11 `recall_channel`; R11 "What scan-prompt and context deliver"; AC-8 (per-leg partition: project partition for scan-prompt); AC-8c (each channel through its real entry point; nudge in 21.3 AC-2); AC-8d (non-ASCII guard on scan-prompt; recall leg's JSON escaping stated, `--pack` leg is 19.1's); mutations (one per channel) |
| round-3 #s-1 (`kind` map; concept-anchored memory body) | R10 `kind` row; R10a (`event_kind`, the table incl. `concept`); R11 (attached body = a `kind=memory` delivered item with its own partition; `find_memory_any_partition` returns it); R12 `context_by_name`; AC-11e; AC-12; mutations |
| round-3 #s-3 (two test bases; vacuous `cwd` mutation; `malformed` not returned) | R5 (key path = `root`, `cwd` only without `root`; base-`None` rows never `test_artifact`; class 0 `malformed` with `source="events"`); AC-7 (two-test-base, cwd-fallback and live-tree cases; event leg with f); mutations. 19.2 AC-16 carries the fold-side case |
| round-3 #m-7 (focus-note sentence-final names; one name, two keys) | R12 `focus_note` edge cases; AC-11f; mutations |
| round-3 [[bsd-plan19-21-spec-rereview-r3-6091648#cross-plan]] (session source, phase inputs, `kind`, classifier rows) | R9, R10, R10a, R5: the signatures 19.0 R5/R7, 19.2 R5 and 19.6 R2 cite are the ones above |
| cross-plan: 23.0 AC-4's `telemetry.is_test_artifact_row(row)` | R5: the new `source` keyword defaults to `query_log`, so the call stays valid as written |

## Revision round 5 (2026-10-14) {#rev-round-5}

Answers [[bsd-plan19-21-spec-rereview-r4-878647c]] (every id, plus the round-3 ids it marks
partial) and d9s / d9r / d9v of [[plan-review-2026-10-14#t11-approvals]]. Code facts re-read at
write time: HEAD `39dffbb` (`src/` identical to `master` `a434f51`): `cli.py:1946-1981` (the
input branch: sweep at `:1976`, its `except … pass` at `:1977-1978`, ambient check `:1980`),
`stm.py:127`, `:246-282`, `:260`, `:331-353`, `:405-427`, `telemetry.py:281`, `:329`, `:425`,
`mcp.py:49-67`, `cli.py:84-107`, `hub.py:100`; bug-109 at `320dc82` in
`/Volumes/littlebig/refmatrix-bug109` (READ ONLY): `stm.py` pointer functions, `verbs.py:521-566`,
`cli.py:1973-2002`, `mcp.py` `serve_stdio`, its implementation summary and its ch-bsd r1 report.

rel: derives-from -> [[bsd-plan19-21-spec-rereview-r4-878647c]]

| finding / decision | answered at |
|---|---|
| round-4 #b-1 (snapshot taken after the input hook's sweep; ambient prompts sweep too; no AC seeds a parked call) | [[#req-session]] "The pre-prompt state": writer = the input hook's first state access (pointer → snapshot → sweep → record), ambient prompts snapshot, the round-3 ambient sentence withdrawn; AC-8b (a parked call whose refs join the active topic, orderings i-iv, ambient leg, non-vacuous pre-check); mutations (snapshot after the sweep; ambient snapshot skipped). The 19.0 side: [[task-19.0-stm-cluster-hygiene#rev-round-5]] |
| round-4 #b-2 (three `latest_session` callers never routed; "NEVER" false) | [[#req-session]] resolver: `purpose` tails, the `read` tail the ONE allowed call; the per-caller routing and the AST allow-list are 19.0 R5 and AC-6e ([[task-19.0-stm-cluster-hygiene#rev-round-5]]) |
| round-4 #s-1 (bug-109 owns the pointer; specs planned to build it) | header (depends on bug-109 MERGED to `master`); R1 (`_LONG_LIVED` existing; delta = env var drop); [[#req-session]] "Existing code this task extends" (bug-109's names, fields and order, adopted) and deltas D1-D8; AC-1, AC-1b, AC-4 re-baselined on post-109 `master` with the failing assertion named; AC-4b; [[#files-to-modify]] (extend, never rebuild; `tests/test_mcp_session_pointer.py` extended); [[#test-strategy]]. bug-109's registry row exists (`workflow/bug_registry.md`, status open) |
| round-4 #s-2 (`ts` zone undefined) | R10 `ts` row (UTC, ms, `Z`, fixed width; `query.log` keeps its legacy form, joined by `query_id`); R5 class 0 (`ts` form); AC-7 event g; mutation. The fold side: [[task-19.2-memory-usage-record#rev-round-5]] |
| round-4 #m-1 (`S` interval; background subagent appends; `focus.json` lock) | [[#req-session]] `S` measured as writer `wall` − reader `t0`; `events_n` parent-origin only (residual stated until 19.0 R2); the `focus.json` lock stated as a known limit |
| round-4 #m-2 (the read fallback IS a `latest_session` consult) | [[#req-session]] resolver: the `read` tail named as the ONE allowed use; R12 "Whose session" uses `purpose="event"` |
| round-4 #m-3 | not a 21.1 item (19.6 Files; the wave list in the decision log; 19.6 status lines) |
| round-3 #b-1 (partial via d9s) | as round-4 #s-1 above |
| round-3 #b-2 (partial) | as round-4 #b-1 above |
| round-3 #s-4 (partial) | not a 21.1 item; R10 `block_id` now names 19.6 R9's two composite blocks ([[task-19.6-phased-context-and-topic-cache#rev-round-5]]) |
| d9s | header; R1; [[#req-session]] |
| d9r, d9v | not 21.1 items (19.2 R7; 19.6) |
