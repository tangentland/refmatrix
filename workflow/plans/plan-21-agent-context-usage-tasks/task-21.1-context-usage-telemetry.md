---
gmd: "0.1"
id: task-21.1-context-usage-telemetry
title: "Task 21.1: telemetry that can count how the agent uses rmx context, and the ONE recall-event schema"
tags: [task, telemetry, context, mcp, agent, recall-events]
metadata:
  node_type: task
  status: pending
  created: 2026-10-07
  updated: 2026-10-15
---

# Task 21.1: make agent context usage measurable {#root}

> Plan: [plan-21-agent-context-usage](../plan-21-agent-context-usage.md)
> Status: Pending (revision after the 2026-10-14 decision log)
> Wave: 1
> Depends on: 23.0 (the shared test sandbox; [[plan-review-2026-10-14#t8-wave1]]), and bug-109
> MERGED TO `master` (d9s; round-4 #s-1): R9's session resolver and pid pointer EXTEND bug-109's
> code as existing code, never rebuild it. A sha list on the bug-109 branch is not the
> dependency; the merge is (it landed: `0c7d0e0`, 0.78.0; R9 is re-read against it in round 6).
> The event emission does NOT depend on plan-23's queue (d4a); only 19.2's fold does.
> Downstream: 19.1 merges AFTER this task (19.1's pack returns byte spans to R11's single
> emission site; [[plan-review-2026-10-14#t10-waves]] orders 21.1 → 19.1).

rel: part-of -> [[plan-21-agent-context-usage]]
rel: derives-from -> [[exploration-agent-context-usage]]
rel: derives-from -> [[bsd-plan21-spec-review-3104a81]]
rel: derives-from -> [[plan-review-2026-10-14]]
rel: depends-on -> [[plan-23-bounded-write-harness]]
rel: depends-on -> [[task-23.0-test-sandbox]]
rel: related-to -> [[task-19.2-memory-usage-record]]
rel: related-to -> [[task-19.5-measure-delivery]]
rel: related-to -> [[task-19.1-pack-recall-under-budget]]
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
- No `query.log` row is written by the daemon's `_op_context` (`daemon.py:4714`), by
  `verbs.context` (`verbs.py:585`), or by the CLI's daemon route (`cli.py:5149`, the
  `daemon_mod.call(root, "context", …)`). Only the replica (`cli.py:5097-5098`,
  `source="context-replica"`) and direct (`cli.py:5228`, `source="context"`) routes log. (Lines
  re-read by symbol at `23ad703`, round-8 #nm-7.)
- `query.log` rows carry no session, no query id and no cwd (`telemetry.log_query.__exit__`), so no
  per-session count (21.3 AC-4, 19.2 R3) can be computed and no event can be joined to its query.
- `grep-stdin` rows (`cli.py:6199`) never set `cardinality`: it is `null` on all 3,521 rows of the
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
   - CLI replica route (`cli.py:5097-5098`): `context-replica` (exists);
   - CLI daemon route (`cli.py:5149`): `context-daemon` (missing today);
   - CLI direct route (`cli.py:5228`): `context` (exists).

   The row is written on the CALLER side (the verb or the CLI), never inside a daemon op and never
   under the daemon's writer lock. `memory_recall` reached from the CLI or MCP gets the same
   treatment with `kind=recall`. `ann_search` is NOT covered: it has no verb
   (`search_dense_cmd`, `cli.py:10763`, calls the op directly), and R4 does not report it.
   **A call that ends without an answer still writes its row** (round-8 #nm-5). The per-prompt
   recall hook (`--timeout 5`) and the SessionStart recall (`--timeout 10`) degrade past their
   budget to "recall skipped", `[]` and exit 0 (`cli.memory_recall`'s `_degrade_or_raise`,
   `cli.py:12012-12025`), and since 0.78.2 the daemon drops the queued read itself
   (`_note_expired_read`, `daemon.py:1362`; bug-116). That skip is a real outcome under load, so
   the recall and context rows carry R4's `outcome` and `budget_s`, and a skipped call writes its
   row with `outcome=skipped_budget` and no recall events.
4. **R4 New row fields.** Every `query.log` row (all kinds) gains:
   - `session`: resolved by [[#req-session]] (null when nothing resolves, never guessed);
   - `query_id`: a uuid4 hex minted by the caller once per call and shared with every recall event
     of that call (R7);
   - `cwd` and `root`: the process cwd and the resolved store root, so d8d's predicate (R5) can
     apply to new rows;
   - on `kind=recall` and `kind=context` rows (round-8 #nm-5): the EXISTING `outcome` field
     (bug-052: every row already carries `ok` / `empty` / `consumer-closed` / `error`, set by
     `telemetry.classify_outcome` in `log_query.__exit__`, `telemetry.py:13`, `:96-118`, `:423`)
     gains one value, and `budget_s` (the call's `--timeout`, or null when it has none) is added.
     `telemetry.CALL_OUTCOMES = ("ok", "empty", "consumer-closed", "error", "skipped_budget")` is
     the ONE vocabulary (round-9 #m9-5: the round-8 three-value tuple left out the four values
     every row already uses). `ok`: an answer was rendered, however many items;
     `skipped_budget`: the call's budget expired before an answer; `error`: any other failure.
     **Classified by exception type, in the one classifier** (round-9 #m9-5): the
     `_degrade_or_raise` path catches `(VerbBusyError, TimeoutError, socket.timeout, OSError)`
     (`cli.py:12241-12244`), so "the degrade path" is not a budget test: a refused or reset
     connection degrades too. `classify_outcome(exc_type, exc_val, *, budgeted: bool = False)`
     gains the keyword: with `budgeted=True`, `VerbBusyError`, `TimeoutError` and
     `socket.timeout` map to `skipped_budget`, and any other `OSError` maps to `error` (the hook
     still degrades, exit 0 and `[]`). The degrade path sets `t.outcome, t.error =
     classify_outcome(type(e), e, budgeted=True)` on its `log_query` handle, and `__exit__` uses
     a set `t.outcome` in place of its own classification. **Two routes reach the degrade path**
     (round-10 #s10-2): (1) `require_daemon(root, retries=0)` (`cli.py:12226`) raising
     `VerbBusyError` when `discovery.daemon_status` finds the ping failed AND the pid file names a
     live process whose argv contains "rmx" or "refmatrix" (`busy`, `discovery.py:189-226`); this
     is the route a budget skip takes, classified `skipped_budget`. (A failed ping with no such
     pid file is `VerbAbsentError`, which raises `ClickException` even in hook mode,
     `cli.py:12230-12234`; it is not a degrade and is unchanged here.) (2) The recall op's own
     `_memory_daemon_call` (`cli.py:12241-12244`), whose transport `OSError`s (a refused connect)
     are classified `error`. **`json.JSONDecodeError` joins that tuple** (round-10 #s10-2): a peer
     that closes mid-answer makes `daemon.call` parse an empty line and raise it
     (`daemon.py:662-668`), a `ValueError` the tuple misses today, so the hook dies with a
     traceback instead of degrading; it is classified `error` (exit 0, `[]`, one row), never
     silently. **The verb (MCP) route cannot be split by type** (round-10 #s10-2): `verbs._call`
     (`verbs.py:216-218`) wraps EVERY transport exception as `VerbBusyError`, so rows written on
     that route are classified with `budgeted=False` (no `skipped_budget` there) unless the verb
     layer gains the same typed split; that change is out of this task's scope and is not
     claimed.
     **Validated where it is written** (round-9 #m9-5): `log_query.__exit__` checks the final
     `outcome` against `telemetry.OUTCOMES_BY_KIND.get(kind, CALL_OUTCOMES)`, where
     `OUTCOMES_BY_KIND: dict[str, tuple[str, ...]]` is DEFINED here (round-10 #m10-4) with no
     entries, so every kind defaults to `CALL_OUTCOMES` and 21.1 names no constant that does not
     exist yet when it merges; 21.3 R3 adds the `"nudge"` entry
     ([[task-21.3-indexed-symbol-nudge#requirements]]); an unknown value is written as `outcome =
     "error"` with `error = "outcome-invalid: <value>"`, never silently kept or dropped, and
     `rmx telemetry --agent-usage` prints `outcome-invalid=<n>` when n > 0. 21.3's nudge row
     uses the same `skipped_budget` value for its deadline (its round-6 `timeout` value is
     renamed, [[task-21.3-indexed-symbol-nudge#rev-round-8]]).
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
6. **R6 `grep-stdin` cardinality** (bsd #s-4, retargeted). The stdin filter path (`cli.py:6199`)
   sets `cardinality` to the number of lines it emitted. The `-E` replica-path claim is dropped:
   it does not reproduce at HEAD (live `-E` row 2026-10-14T11:08:31 logged `cardinality: 15`).
7. **R7 `rmx telemetry --agent-usage`** (bsd #m-2, #s-3, #s-5). `telemetry` is a `@main.command`
   (`cli.py:7518`), so this is a FLAG on it, not a subcommand. It reuses `--since` and adds
   `--until` (ISO prefixes); no `--days`. It prints, per `invocation`, the counts and p50/p95
   latency for context (per route), grep (per `source` / `answered_by`), and recall, plus a
   `--by-session` table (calls per `session`). It:
   - reads `query.log` and `cli.log` of ONE store root;
   - counts a `cli.log` command once (excludes `phase=start` intent rows, as `summarize_context`
     already does);
   - applies R5's `row_provenance` with `reader_root` = the store root it reads, counts per R5's
     totals rule, and prints the `excluded_test_rows` / `legacy_fixture_rows` /
     `legacy_unattributed` line;
   - excludes `invocation=internal` rows by default (`--include-internal` to keep them);
   - prints, per recall channel (R11's `recall_channel` value, recomputed from the row) and for
     context, the count of each `outcome` (round-8 #nm-5), so a skipped prompt is never read as
     "recall ran and delivered 0";
   - prints the daemon's dropped-read count beside it when the store's `stats` op returns it:
     `_op_stats` gains one key, `expired_reads` (the counter `_note_expired_read` already keeps,
     `daemon.py:1362-1368`), so client skips and daemon drops can be reconciled. A store whose
     daemon is down prints `expired_reads: unavailable (daemon down)`, never 0.

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

   **Existing code this task extends** (bug-109 as MERGED: r1 `320dc82` plus the r2-r4 remedies
   `0760fb7`, `9fe45fa`, `8cc9c71`, merged at `0c7d0e0`, released in 0.78.0; round-6 #b-1).
   Every name and line below is read from `src/` at HEAD `3d3c798`, whose `src/` equals `master`
   `c7129e6`:
   - **Process lookup, no subprocess on the common path.** `stm._proc_info(pid) -> (ppid,
     executable path, start) | None` (`stm.py:127-165`): macOS through libproc `proc_pidinfo` and
     `proc_pidpath`, Linux through `/proc`; `start` is the kernel start time. `stm._proc_start(pid)`
     (`:197-202`) is its third field. `stm._is_claude(path)` (`:190-194`) recognises Claude by
     executable path. `stm._ps_comm_chain()` (`:205-229`), ONE `ps -A -o pid=,ppid=,comm=` call,
     is used only as the argv[0] fallback.
   - `stm.owner_lookup() -> (pid | None, status)` (`:236-279`), `status` ∈ `found`, `none`,
     `failed`. It walks the kernel chain (≤ 16 steps). If that chain has fewer than 2 entries it
     falls back to `_ps_comm_chain()`, and returns `failed` when `ps` gives nothing. Otherwise:
     `$CLAUDE_PID` when it is in the chain, else the nearest ancestor that `_is_claude` or whose
     argv[0] is `claude`, else `none`. `stm.owner_claude_pid(*, long_lived)` (`:282-288`) is a
     thin wrapper (long-lived → `os.getppid()`, else `owner_lookup()[0]`); the resolver calls
     `owner_lookup()` directly (`verbs.py:545`).
   - `stm.pid_pointer_path(root, pid)` (`:232`) = `<root>/stm/by-pid/<pid>.json`.
     `stm.write_pid_pointer(root, pid, session) -> bool` (`:346-375`) writes `{session, pid,
     pid_start, t}` by tmp + `replace`; it skips the write when the file already names this session
     AND this `pid_start`; it refuses a pid whose start time cannot be read and records `ps-failed`
     (`:368`); it never creates a store. `stm.read_pid_pointer(root, pid)` (`:378-389`) returns
     `None` SILENTLY on a missing, unreadable or non-object file and on a `pid_start` mismatch.
   - **The error log.** `stm.record_pointer_error(root, reason, **fields) -> bool` (`:294-315`)
     appends `{t, reason, …}` to `<root>/stm/by-pid/_errors.jsonl`, only when the store's STM dir
     exists, never raising. It is bounded by `_ERRORS_MAX_BYTES = 256 * 1024` (`:291`): past that it
     rewrites the file IN PLACE keeping the newer half of its lines (`:308-310`), so rows are
     deleted and byte offsets move. `stm.read_pointer_errors(root, *, since)` (`:318-343`) returns
     rows with `t ≥ since`, and every unparseable line as `{"reason": "unreadable-line"}`.
   - **Reasons written at HEAD:** `no-owner` and `owner-lookup-failed` (input hook,
     `cli.py:1985-1987`), `write-failed` (`cli.py:1991`), `ps-failed` (`stm.py:368`),
     `owner-lookup-failed` and `pointer-unresolved` (resolver, `verbs.py:561-565`). A resolver miss
     in a plain terminal (lookup worked, no owner, no `$CLAUDE_PID`, not long-lived) records
     NOTHING (`verbs.py:558-565`).
   - **The log is already surfaced.** `handoff.session_pointer_anomalies(root, *, window_s=86400)`
     (`handoff.py:508-529`) reads `read_pointer_errors` for the last 24 h and returns one line with
     the count per reason (unreadable lines counted apart); `handoff.compose_recall_state` adds it
     to the anomalies (`handoff.py:569`), so `rmx recall-state` reports pointer failures today.
     Tests: `tests/test_mcp_session_pointer.py` (`test_recall_state_surfaces_pointer_errors`,
     `test_the_anomaly_reads_only_the_window`, among others).
   - The input branch of `cli.focus_hook` (`cli.py:1974-2004`): pointer write `:1979-1993` (for
     every envelope with a `session_id`, FIRST), sweep `:1998-2001`, input record `:2003-2004`.
   - `verbs._LONG_LIVED` (set by `mcp.serve_stdio`) and `verbs.resolve_session_source(root,
     session) -> (session, source)` (`verbs.py:524-569`), `source` ∈ `explicit`, `pointer`, `env`,
     `latest`, `default`; order: explicit → (long-lived: pointer for `os.getppid()` →
     `RMX_SESSION`; per-call: `RMX_SESSION` → pointer for `owner_lookup()`'s pid) → newest ring
     (`latest_session`, `:566`) → `default`. The str wrapper `verbs.resolve_session` (`:572-575`)
     is called by `cli._resolve_stm_session` (`cli.py:1072`), `verbs.focus` (`verbs.py:934`) and
     `verbs.recall_state` (`:1068`); the write verbs `save_state` (`:892`), `focus_note` (`:958`),
     `change_subject` (`:972`) and `task` (`:1029`, every action) call `resolve_session_source`
     and return `session_source`. `cli.focus_promote_edges` resolves its session in the CLI
     (`cli.py:1497`).

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
     its stdin envelope) → long-lived: pointer for `os.getppid()` → `RMX_SESSION`; per-call:
     `RMX_SESSION` → pointer for the pid `owner_lookup()` returns → the TAIL of the caller's
     `purpose`:
     - `read`: the newest ring (source `latest`, output labelled `(newest ring; not resolved)`),
       else `default`. This is the ONE allowed `latest_session` call in `src/` (round-4 #m-2);
       19.0 AC-6e enforces it by an AST scan.
     - `write`: raises `verbs.SessionUnresolved` naming the sources tried (19.0 R5 states the
       CLI and MCP outcome). No write reaches `default` or the newest ring (delta D2: bug-109's
       `latest` / `default` tail is removed for writes).
     - `event`: `SessionResolution(None, "none")`. Telemetry rows and events (this task),
       scan-prompt's enrichment and composite, and the helix gate (19.0 R5) use it.
     In all three, a miss is recorded exactly as bug-109 records it today (`verbs.py:561-565`):
     `owner-lookup-failed` when `owner_lookup()` returned `failed`; `pointer-unresolved` when an
     owner was found, `$CLAUDE_PID` is set, or the process is long-lived; nothing in a plain
     terminal, which has no pointer to miss. "All three" is pinned per purpose (round-7 #s-4):
     AC-4 asserts the row for `event`, `read` and `write`, because for a `write` miss under a
     hook (exit 1, 19.0 R5) the row is the only durable channel; each row carries D8's `root` and
     `owner` scope.
   - **`CLAUDE_CODE_SESSION_ID` is read by no resolver path** (bug-109 already reads it nowhere;
     R1 also deletes it from the server's environment).
   - **D3 One pointer location for every store root** (bug-109 r1 #m-4, "the hook and server
     resolve their store root differently"). The hook writes under `cli._root()` (its cwd's
     store); the server reads under `mcp._resolve_root(args)` (its spawn cwd's store, or a named
     `root` / `project`). When the session's cwd moves into another tree, the pointer lands in a
     store the server never reads. A pointer belongs to a Claude PROCESS, not a store, so pointers
     and `_errors.jsonl` move to `<hub.global_store_root()>/by-pid/` (`~/.refmatrix/by-pid/`,
     `hub.py:100`; 23.0's sandbox redirects it). NEW `stm.pointer_dir() -> Path` returns it, and
     creates only `by-pid/` itself, only when `global_store_root()` already exists (the r2 #s-1
     rule kept: no read creates a store). `write_pid_pointer`, `read_pid_pointer` and
     `pid_pointer_path` drop `root` as the pointer's LOCATION (`write_pid_pointer` and
     `read_pid_pointer` keep a keyword-only `root` that only scopes the error rows they write,
     D8). **Migration, one shot, no legacy read**
     (round-7 #s-3; the round-6 "one release" fallback and its `pointer-legacy-location` reason
     are WITHDRAWN): `read_pid_pointer` reads only `<pointer_dir>/<pid>.json`. bug-109's
     `<root>/stm/by-pid/<pid>.json` files are never read: a pointer is a cache of the process
     relation (D7's own words), and the input hook writes the new-location pointer FIRST on every
     envelope with a `session_id` (`cli.py:1979-1993`), before any MCP call of that turn, so no
     resolution depends on a legacy file. The SessionStart writer's one-shot migration (D6)
     deletes its own root's legacy pointer files, counted. Nothing writes the old location, and
     no `src/` path reads it.
   - **D4 The SessionStart writer** (bug-109 r1 #m-4). A NEW generated SessionStart entry,
     matcher `startup|resume|clear|compact`, command `rmx focus hook --event session-start`
     (stderr NOT discarded: this is a memory path), calls `write_pid_pointer` with the envelope's
     `session_id`, so after `/clear` the pointer names the new session BEFORE the first prompt.
     The pointer gains one field, `hook` (`input`, or `session-start:<source>`); readers ignore
     unknown fields, so bug-109's format `{session, pid, pid_start, t}` is otherwise kept as is
     (the round-3 names `session_id`, `written_at`, `hook_source` are WITHDRAWN).
   - **D5 Silent misses recorded.** `read_pid_pointer` records `pointer-stale` (its `pid_start`
     no longer matches: pid reuse) and `pointer-unreadable` (present but not a JSON object)
     instead of returning `None` silently (`stm.py:383-388` today). A missing file is not an error
     by itself; the resolver's row covers it.
   - **D6 The EXISTING reader follows the log, scoped; one more surface** (round-6 #b-1;
     round-7 #s-2, #s-3, #m-4). bug-109's `handoff.session_pointer_anomalies`
     (`handoff.py:508-529`) already surfaces the log in `rmx recall-state`; D6 extends it, it adds
     no second reader. D3 makes the log ONE user-level file for every project and every Claude
     process, so every reader filters by scope (round-7 #s-2: without it, recall-state in project
     X counted project Y's rows, and the first SessionStart anywhere consumed every session's rows):
     - **Every row is scoped at write time** (D8): `root` (the writer's store root, resolved, as a
       string) and `owner` / `owner_start` (the Claude pid the writer resolved and its
       `_proc_start`, or `null` when it found none, as in `no-owner` and `owner-lookup-failed`).
       The one global row is `errors-truncated` (below), which carries per-scope counts instead.
     - `stm.read_pointer_errors(*, root: Path | None = None, owner: tuple[int, str] | None =
       None, since: float = 0.0) -> list[dict]` reads `<pointer_dir>/_errors.jsonl` only (no
       legacy file: round-7 #s-3, see the migration below). With `root=`, it returns rows whose
       `root` equals it; with `owner=` (`(pid, pid_start)`), rows whose `owner` and `owner_start`
       equal it; with both, rows matching both. A row with no `root` field (a writer defect, or a
       pre-migration row) is returned as `{"reason": "unscoped-row", …}` to every scoped reader,
       counted apart like `unreadable-line`, never attributed silently to the reader's scope.
     - `session_pointer_anomalies(root)` calls `read_pointer_errors(root=root, since=now −
       24 h)` and prints up to three clauses, so its existing "guessed session" text stays true:
       (1) **session-pointer failures** (every reason other than those in (2) and (3)): count per
       reason, then "the session could not be resolved: reads used the labelled newest ring,
       writes were refused, events carry `session: null`"; (2) **STM hook failures**
       (`sweep-failed`, `composite-failed`, `enrichment-unresolved`): count per reason, with no
       session wording; (3) **dropped by truncation**: the sum of `dropped_by_root[root]` over the
       window's `errors-truncated` rows. Unreadable lines and `unscoped-row`s are counted apart, as
       today. Its text names the new path.
     - `rmx focus topics` (`cli.py:1234`, no required argument) prints the same clauses for the
       current root as its last line, also when it prints "no topics yet" (round-7 #m-4 (b): the
       round-6 surface `rmx focus show` takes a required `LINE`, `cli.py:1210`, so it was not a
       status surface).
     - **The SessionStart writer (D4) surfaces TWO sets on STDOUT**, where SessionStart output
       reaches the agent (round-8 #ns-2). Per-owner surfacing alone reaches only the SAME Claude
       process: a `startup` SessionStart, and `claude --resume` / `--continue`, start a NEW
       process whose owner has written no rows yet, so only `clear` / `compact` could surface
       anything, and a session's last rows (its pointer and STM-hook failures, and its final
       Stop's `write` miss, the "durable channel" of 19.0 R5) reached no SessionStart after the
       process exited; `rmx recall-state` is not a hook (the generated SessionStart entries are
       `curator status`, `memory recall --session-start`, `ingest-gmd --detach` and, on resume,
       `focus context`: `hooks.py:209-297`). The two sets:
       **(1) its OWNER's rows**, whenever rows were added since that owner's last surfacing.
       **The watermark is per owner and keyed on `t`, not on a byte offset:**
       `<pointer_dir>/_errors.seen.<pid>` holds `{pid_start, t}`, the largest `t` already
       surfaced for that owner; a file whose `pid_start` differs from the owner's is ignored (pid
       reuse). `P_start` is `stm.proc_identity(P)[1]` (round-10 #m10-2; no identity, no set (1):
       the line reads `own rows skipped: process lookup unavailable`). The writer surfaces
       `read_pointer_errors(owner=(P, P_start), since=<that t>)` minus
       rows with `t` equal to it, so one session's SessionStart never surfaces, or consumes,
       another LIVE session's rows. **(2) its ROOT's ended-session rows, consumed by OWNER**
       (round-9 #s9-2: a per-root `t` watermark over a liveness-filtered set loses rows. Live
       owner A writes at t = 10, ended owner B at t = 20; the next SessionStart prints B's row
       and moves the watermark to 20; when A ends, its row at t = 10 is never selected, the
       normal case with two sessions in this shared tree). A dead owner writes no more rows, so
       "every row of `(pid, pid_start)`" is a closed set and is consumed as one. The per-root
       file `<pointer_dir>/_errors.seen.root.<h>` (`h` = `sha1(str(R)).hexdigest()[:12]`) holds
       `{root, consumed: [[pid, pid_start, t_max], …]}`; a file whose `root` is not R is a hash
       collision, counted (`watermark-collision`) and treated as absent. Set (2) = the rows of
       `read_pointer_errors(root=R, since=now − 24 h)` whose owner is DEAD
       (`stm.owner_alive(owner, owner_start) is False`) and whose `(owner, owner_start)` is not
       in `consumed`, or is in it with `t` above that entry's `t_max` (a row stamped with a dead
       owner later, by an orphaned child of it, is still shown once). They print as ONE line
       `ended_sessions: <reason>=<n> … (see rmx recall-state)`; printing adds or updates each
       owner's entry, `t_max` = the largest `t` printed for it, in the SAME lock hold that
       selected the rows. An entry whose `t_max` is older than the 24 h recall window
       (`handoff.py:508`, `window_s=86400.0`) is pruned in that hold; its rows are then all
       outside the `since` window, so pruning cannot re-surface them. Rows of a live other owner
       are neither printed nor consumed (round-7 #s-2's guarantee kept). A dead owner's row is therefore shown at most twice, once to each
       audience: to its own process (set 1, at a `clear` / `compact` before it exited) and to the
       next session that starts in its root (set 2).
       - **Unowned rows** (round-8 #nm-1). A row whose `owner` is null, OR whose `owner_start` is
         null whatever its `owner`, is UNOWNED: bug-109's `ps-failed` row (`stm.py:368`) is
         written exactly when `_proc_start(pid)` is `None` (`stm.py:359-369`), so its D8 stamp
         `owner_start` is always null and it matches no `(P, P_start)` filter, and its liveness
         cannot be decided. Unowned rows are reported by recall-state and `focus topics` for
         their root, and the SessionStart line adds `unowned_in_root=<n> (see rmx recall-state)`
         for its root's last 24 h without consuming them; they are in neither set.
       - **`stm.owner_alive(pid: int | None, pid_start: str | None = None, *, start_token: str
         | None = None) -> bool | None`**, ONE predicate: `None` when `pid` is null or both
         `pid_start` and `start_token` are null (UNOWNED, nothing else); else
         `_proc_start(pid) == pid_start`, or, given `start_token`,
         `stm.start_token(_proc_start(pid)) == start_token` (`start_token(s)` =
         `sha1(s).hexdigest()[:8]`, `None` for `None`; D6's migration claim names carry it).
         **Lookup availability is a separate function** (round-9 #m9-1: one `None` for "unowned"
         and for "lookup unavailable" left the guard no allowed way to run).
         **Identity is a third, separate function** (round-10 #m10-2):
         `stm.proc_identity(pid: int) -> tuple[int, str] | None` returns `(pid, _proc_start(pid))`,
         or `None` when `_proc_start(pid)` is `None`, WITHOUT judging liveness. It is the ONE
         accessor for a start value: set (1)'s `P_start` and the watermark file's `pid_start`
         check, the migration's claim name (`proc_identity(os.getpid())`), `record_pointer_error`'s
         `owner_start` stamp (D8) and `write_pid_pointer`'s `pid_start` (whose `None` result is
         bug-109's `ps-failed` case, `stm.py:366-369`) all take it from here.
         `stm.liveness_available() -> bool` is `_proc_start(os.getpid()) is not None`, called
         ONCE per SessionStart run by D6 (before set (2) and the claim adoption) and by D7
         (before the prune). Set (2), D7's prune, D6's claim adoption and `read_pid_pointer`
         (`owner_alive(pid, d.get("pid_start")) is True`, replacing its private comparison at
         `stm.py:387`) call `owner_alive`; none calls `_proc_start` to judge liveness itself
         (AC-4b (xii)'s AST check). When `liveness_available()` is `False`, set (2) is not
         computed, nothing is consumed or adopted, and the line reads `ended_sessions skipped:
         process lookup unavailable` (otherwise every live owner would read as dead and another
         session would consume its rows).
       - **Claimed under the lock.** Each watermark (per owner) and the per-root `consumed`
         file are read, their rows selected and the file advanced inside ONE hold of D8's
         `_errors.lock`, and the
         lines are printed after the release, so two SessionStarts in one root at the same time
         (two sessions in this shared tree) print each set-(2) row once between them.
       bug-109's in-place halving (`stm.py:308-310`) moves every byte offset, so an offset
       watermark would skip rows or surface them twice; a `t` watermark is unaffected. Unreadable
       lines carry no `t` and are counted on every surfacing, apart.
     - **The bound is kept, and its deletions are counted per scope.** The 256 KiB halving stays
       (the round-5 1 MB rename and "nothing is deleted" are WITHDRAWN: the halving deletes rows,
       and it fires long before 1 MB). When it halves, `record_pointer_error` first appends one row
       `{reason: "errors-truncated", t, dropped: <n>, oldest_kept_t,
       dropped_by_root: {<root>: n}, unseen_dropped: {"<pid>:<pid_start>": n}}` to the kept half.
       **Counts roll up** (round-9 #m9-3: a later halving drops earlier `errors-truncated` rows,
       and their counts would leave the file): `dropped` = the removed rows OTHER than
       `errors-truncated` rows, plus the sum of the removed `errors-truncated` rows' `dropped`;
       `dropped_by_root` adds the removed rows' maps key by key. `unseen_dropped` is a news
       counter, not an accounting total (round-10 #m10-3): a removed `errors-truncated` row's
       `unseen_dropped[key]` is carried into the new row ONLY when that removed row's `t` is above
       owner `key`'s watermark at halving time (no file: carried), the same test as for ordinary
       rows, so a count the owner was already shown is never reported again. So
       at any time the file's non-truncation row count plus the sum of `dropped` over its
       `errors-truncated` rows equals every row ever appended.
       `unseen_dropped` counts, per owner, the removed rows of that owner with `t` above its
       watermark file at halving time (no file: all of them), so an owner's SessionStart line
       reports exactly how many of ITS unsurfaced rows were lost; `dropped` is the accounting total
       (non-truncation rows removed + rolled-up counts). A reader surfaces the `errors-truncated` row when its own scope has a non-zero count
       in it.
     - **One-shot migration of bug-109's files** (round-7 #s-3, the user's choice; the round-6
       "for one release" legacy read and `legacy_root=` are WITHDRAWN). The SessionStart writer,
       for its own root `R` (`cli._root()` of the hook's cwd), when `R/stm/by-pid/_errors.jsonl`
       exists:
       1. **claims it** (round-8 #nm-2) by `os.rename` to `R/stm/by-pid/_errors.migrating.<own
          pid>.<start_token(own pid_start)>.jsonl` (round-9 #m9-4; own pid_start =
          `proc_identity(os.getpid())[1]`, round-10 #m10-2); a loser of a concurrent
          claim gets `FileNotFoundError`, counts it (`migrate-claim-lost`, printed) and migrates
          nothing. Crash recovery: before claiming, and only when `liveness_available()`, it
          adopts a `_errors.migrating.<pid>.<token>.jsonl` in `R/stm/by-pid/` ONLY when
          `owner_alive(pid, start_token=token) is False` (its claimant is dead), by renaming it
          to its own claim name, so a crash leaves no orphan behind. The round-8 "mtime older
          than 60 s" rule is WITHDRAWN: `os.rename` preserves mtime, and a legacy log last
          appended days ago made a live claim look abandoned at once. A claim whose owner is
          alive, or unknown (`None`), is left alone. A final rename (step 3) that hits
          `FileNotFoundError` (an adopter took the file) is counted as `migrate-claim-lost` and
          prints no `migrated=` count;
       2. appends each parseable legacy row through D8's ONE writer with its ORIGINAL `t`, plus
          `root = R` and `migrated_from = <legacy path>` (legacy rows have no `owner_start`, so
          they are UNOWNED by D6's rule: they surface in recall-state for `R`, never on an
          owner's SessionStart and never as `ended_sessions`), and one `{reason:
          "legacy-unreadable", n}` row scoped to `R` when the legacy file held unparseable lines, whose
          `t` is the legacy file's mtime (read before the claim rename; round-9 #m9-4), so a
          repeated run's `(t, reason)` check matches it;
       3. renames the claim file to `R/stm/by-pid/_errors.migrated.jsonl` ONLY when every append
          returned `True`; otherwise it leaves the claim file, prints `migration incomplete:
          <n> rows not written (global store root absent or unwritable)` on stderr, and the next
          SessionStart retries.
       It is idempotent: a legacy row whose `(t, reason)` already appears in the new log with the
       same `migrated_from` is not appended again (checked inside the writer's lock hold, D8), so a
       run interrupted between the append and the rename repeats nothing. It then deletes `R/stm/by-pid/<pid>.json` legacy pointers (D3) and
       prints `migrated=<rows> legacy_pointers_dropped=<n>` with the surfacing line. No `src/`
       path reads `R/stm/by-pid/` at any time, so there is no legacy read path to remove later.
       Stated limit: a root where no Claude session starts after the deploy keeps its legacy file
       on disk, unmigrated and unread; its rows were reported by recall-state for 24 h only, so
       what is lost is at most one day of that root's report.
   - **D7 `by-pid/` cleanup** (bug-109 r1 #m-4; round-7 #s-2). The SessionStart writer removes
     each pointer file, and each `_errors.seen.<pid>` watermark file, for which
     `stm.owner_alive(pid, <its pid_start>)` is `False` (`_proc_start`, `stm.py:197-202`, one
     kernel lookup per pid; there is no process-table call in `src/`, and the round-5 name
     `stm._process_table()` is WITHDRAWN), and prints `pruned=<n>` with the surfacing line.
     Per-root watermark files `_errors.seen.root.<h>` (round-8 #ns-2) are kept: one small file
     per root that ever had a session, keyed by root, not by a process that dies; one is removed
     only when its `root` path no longer exists (counted in `pruned`). If `stm.liveness_available()`
     is `False` (round-9 #m9-1), nothing is pruned, and the line reads
     `prune skipped: process lookup unavailable` (otherwise every live pointer would be removed).
     A pointer is only a cache of the process relation, and a watermark only of what its process
     was shown, so removing a dead process's files loses nothing.
   - **D8 `record_pointer_error` generalized** (round-7 #s-2). With D3 it writes
     `<pointer_dir>/_errors.jsonl`, named once by `stm.errors_log_path() -> Path` (round-9
     #m9-2): every reader and writer, and `handoff`'s report text, take the path from it. Its
     signature becomes `record_pointer_error(reason: str, *,
     root: Path, owner: int | None, **fields) -> bool`: `root` no longer locates the file, it is
     the row's SCOPE, and is required; `owner` is the Claude pid the caller resolved (`None` when
     it found none), and the writer adds `owner_start` from `stm.proc_identity(owner)` (null when
     it returns `None` or `owner` is `None`; round-10 #m10-2). The existing call
     sites hold both: the input hook its `_root()` and `owner_lookup()` result (`cli.py:1985`,
     `:1991`), the resolver its `root` and `owner` (`verbs.py:562`, `:564`); `write_pid_pointer`'s
     `ps-failed` row (`stm.py:368`) has its `pid` as the owner and takes `root` from its caller
     as a scope keyword (D3 removed `root` only as the pointer's location). 19.0 adds the
     reasons `sweep-failed`, `composite-failed` and `enrichment-unresolved` to the same record,
     scoped the same way, so every STM hook failure reaches D6's surfaces; no new error file is
     added. D9 adds `envelope-unreadable` and `envelope-no-session` (round-8 #nm-4).
     - **ONE locked writer** (round-8 #nm-2; the user's rule: converge repeated shapes into one
       function). D3 makes the log machine-wide: every hook and MCP server of every project
       writes it. bug-109's halving is a read-modify-write with no lock (`read_text` then
       `write_text`, `stm.py:305-307`), so an append from another process between the read and
       the truncate is lost and counted nowhere. So every mutation of an `_errors.*` file goes
       through `stm._errors_locked()`, a context manager holding `fcntl.flock(LOCK_EX)` on
       `<pointer_dir>/_errors.lock`:
       - `stm._append_error_rows(rows: list[dict]) -> bool` is the ONLY function that opens
         `_errors.jsonl` for writing. Under one hold it checks the size, and when it is over
         `_ERRORS_MAX_BYTES` it writes the kept half plus the `errors-truncated` row (D6) to
         `_errors.jsonl.tmp` and `os.replace`s it, then appends `rows` (one `write()` each).
         `record_pointer_error` builds its row and calls it; the migration (D6) calls it with the
         legacy rows and does its idempotence check inside the same hold; nothing else writes
         the file.
       - The watermark files (`_errors.seen.<pid>`, `_errors.seen.root.<h>`) are written by tmp +
         `os.replace` inside a hold (D6 "Claimed under the lock").
       - A failure to take the lock or to write is returned as `False` and, at every call site
         that has a stderr, printed once; the input hook's existing stderr line (`cli.py:1985`
         path) covers its rows.
       - **Bypass check, scoped to WRITES** (round-9 #m9-2: at HEAD `handoff.py:509`, `:522`,
         `:529` and `verbs.py:537` hold `_errors.jsonl` in docstrings and messages, and D6
         requires handoff's text to name the path, so a check on every string constant fails at
         GREEN). An AST test lists every WRITE operation in `src/refmatrix/` (`open(` with a mode
         containing `w`, `a` or `x`; `.write_text(`; `.write_bytes(`; `os.replace(`;
         `os.rename(`; `.unlink(`) whose path expression contains a string constant with
         `_errors`, or a call of `errors_log_path()` or `pointer_dir()`, and requires each to sit
         inside the allow-listed `stm.py` functions (`_errors_locked`, `_append_error_rows`, the
         watermark and `consumed` advance, the migration, D7's prune); docstrings and message
         strings are not write operations and are not listed. A second check requires that no
         module outside `stm.py` joins `"_errors.jsonl"` onto a path (handoff calls
         `errors_log_path()`). **The check can fail:** run on a fixture module holding
         `open(pointer_dir() / "_errors.jsonl", "a")`, it reports that line.
   - **D9 ONE hook-envelope reader** (round-8 #nm-4; the user's rule). Hook stdin envelopes are
     parsed in three places today, each with its own silent fallback: `cli.focus_hook`
     (`cli.py:1963-1966`, `except Exception: return`, then `d.get("session_id") or
     stm_mod.session_id()` at `:1967`), `cli._resolve_query` (`cli.py:8969-9013`, the `--stdin-json`
     path of `memory recall` and `context`) and `scan.read_stdin_prompt` (`scan.py:1036-1054`,
     prompt only, the session dropped). One function replaces the envelope parse in all three
     and in the two new readers (`focus hook --event session-start`, D4; `focus summarize
     --envelope-stdin`, 19.0 R5): `stm.read_hook_envelope(raw: str, *, root: Path, hook: str,
     require_session: bool, prose_ok: bool) -> stm.HookEnvelope`, a `NamedTuple(envelope: dict
     | None, prose: str | None)` with one property, `prompt` (round-9 #s9-4).
     - **Raw text is valid input on two of the callers today** (round-9 #s9-4):
       `scan.read_stdin_prompt` treats `JSONDecodeError` as prose ("We accept either the
       envelope or raw text", `scan.py:1036-1054`), and `_resolve_query` without `--stdin-json`
       treats `{`-prefixed text that fails `json.loads` as prose (`cli.py:9001-9010`). So with
       `prose_ok=True`, unparseable or non-object input returns `HookEnvelope(None,
       raw.strip())` and records NOTHING (a prompt like `fix the {braces` is not an error).
     - With `prose_ok=False`, unparseable or non-object input prints ONE stderr line, records
       `envelope-unreadable` (D8-scoped: `root`, `owner` from `owner_lookup()`) and returns
       `HookEnvelope(None, None)`. With `require_session=True` and a falsy `session_id`
       (missing, `None` or `""`) it prints one stderr line, records `envelope-no-session` and
       returns `HookEnvelope(None, None)`.
     - **Callers:** the STM hooks (`focus hook` every event, session-start, `summarize
       --envelope-stdin`) pass `require_session=True, prose_ok=False`; scan-prompt and
       `_resolve_query` without `--stdin-json` pass `require_session=False, prose_ok=True`;
       `--stdin-json` passes `require_session=False, prose_ok=False` and keeps its
       `ClickException("--stdin-json: invalid JSON on stdin")` after the row is recorded. The
       non-STM callers' session falls through R9's resolver with `envelope=<the dict>`,
       `purpose="event"`, which records its own miss. No caller parses stdin itself: the prose
       fallback lives INSIDE `read_hook_envelope`, so (xii)(c) holds as written (the round-8
       phrase "OUTSIDE the envelope path" is WITHDRAWN; it contradicted (xii)(c)).
     - **ONE prompt-key tuple** (round-9 #s9-4): `stm.HOOK_PROMPT_KEYS = ("prompt",
       "user_prompt", "text", "message")`, scan's four keys. `HookEnvelope.prompt` is `prose`
       when it is set, else the first key of `HOOK_PROMPT_KEYS` whose value in `envelope` is a
       string (stripped), else `""`. **Behaviour change, recorded:** `_resolve_query` today reads
       `prompt` only (`cli.py:9011`), so an envelope carrying only `text` now yields that text
       instead of `""`; and `scan.read_stdin_prompt` today returns the RAW JSON text for an
       object with none of the four keys, which now yields `""`. Claude Code's envelopes carry
       `prompt`, so neither change touches a generated hook's input. No module outside `stm.py`
       names `"user_prompt"` or reads `"prompt"` from a stdin envelope (AC-4b (xii)(c)). Because
     the generated focus entries end `2>/dev/null || true` (`hooks.py:131-147`), the row, not the
     stderr line, is the durable channel there; the suffix itself is not changed by this task
     (bug-118 in `workflow/bug_registry.md` is converging the generator's hook-command wrapper;
     any change to that suffix goes through bug-118's ONE renderer, not a second one here).
     **Bypass check:** an AST test lists every `json.load(sys.stdin)` / `json.loads(<stdin
     read>)` in `cli.py` and `scan.py` and requires none outside `read_hook_envelope`; it also
     requires that no module outside `stm.py` contains the constant `"user_prompt"`, and lists
     every `.get("prompt")` / `["prompt"]` in `cli.py` and `scan.py` as a set equality with a
     list kept in the test (none of them on a stdin envelope), so a new private prompt read
     fails until it is reviewed. **The check can fail:** run on a fixture holding
     `json.loads(sys.stdin.read())`, it reports that line. The grep-guard (`search_hooks.py:309`) and the enqueue one-liner
     (`hooks.py:111`) parse PreToolUse / PostToolUse envelopes for a tool command, not a session,
     and are out of this task's scope (stated in [[#rev-round-8]]).
   - `stm.latest_session` (`stm.py:392` at HEAD) is never called outside the `read` tail (bsd
     #b-1; bug-100's shape). When nothing resolves, rows and events carry `session: null`.

   **The pre-prompt state, race-free** (re-review #s-3; round-3 #b-2; round-4 #b-1, #m-1). The
   recall and scan hooks run IN PARALLEL with `focus hook --event input` (`hooks.py` registers
   them as separate UserPromptSubmit entries, and Claude Code runs an event's hooks in parallel,
   as the generator's own comment at `hooks.py:265-266` records). The input hook CHANGES the
   state they read, in two places (re-read at HEAD `3d3c798` in round 6, unchanged at `23ad703`: `cli.py:1974-2004`;
   `stm.Stm.record` `stm.py:511-544`, `inflight_sweep` `:596-618`):
   - `inflight_sweep()` runs first (`cli.py:1998-2001`): every call parked longer than 90 s is
     `record`ed as an `abandoned` tool event, appended to the ring AND ingested into
     `<session>.focus.json`. It runs BEFORE the ambient check, so ambient prompts sweep too. Live:
     17 of session db80475a's 78 recorded prompts directly followed a sweep, 16 with refs.
   - then `Stm.record("input", …)` (`cli.py:2003-2004`) appends the input event and ingests the
     prompt's refs (`_ingest_into_graph`, `stm.py:705-710`); the ring's `ts` is cut to the second
     (`stm.py:525`).

   So EVERY value a prompt-time reader computes from the ring or the graph (the event count, the
   turn, the topic list, the overlap, 19.6's phase) depends on scheduling, and no wall-clock
   margin on a second-truncated `ts` can separate this prompt from the last. The round-2 rule
   (`ts < t0 − 1 s`) is WITHDRAWN. Instead, one snapshot, one reader:
   - **Signature, exact:** `stm.pre_prompt_state(root: Path, session: str, prompt: str, *,
     t0: float) -> stm.PrePromptState`, a `NamedTuple(graph: dict, topic_cache: dict, turn: int,
     events_n: int, source: str, topic_match: dict[str, str])`, `source` ∈ `snapshot`, `live`;
     `topic_match` is 19.6 R9's completed live-cluster-to-snapshot map, keyed by
     `stm.cluster_cid(members)` and valued by `<cid>` (`{}` until 19.6; round-9 #s9-1; key type
     round-10 #m10-1). 19.6's ONE reader `stm.load_topic_cache` reads `pre.json`'s pre-19.6
     `topic_cache = {}` as the empty cache. Same ownership rule as the
     resolver (first of 21.1 / 19.0 to merge builds it; 19.0 R7 restates it).
   - **Writer: the input hook's FIRST state access, not `Stm.record`** (round-4 #b-1). The input
     branch of `cli.focus_hook` runs, in this order:
     1. bug-109's pointer write (existing; no prompt-time reader resolves its session from the
        pointer, since every hook reader has its envelope, so it is not reader state);
     2. `s.snapshot_pre_prompt(prompt)` for EVERY non-empty prompt, ambient included;
     3. `s.inflight_sweep()`; its `except Exception: pass` (`cli.py:2000-2001`) becomes one stderr
        line plus a `sweep-failed` row (D8); each swept call is given an `origin` by 19.0 R2's
        ladder before it is recorded (19.0 R2 "Swept calls"; round-6 #s-1), so a subagent's
        abandoned call never enters the parent's graph;
     4. when the prompt is not ambient, `s.record("input", prompt[:300])`.
     `Stm.snapshot_pre_prompt(prompt: str) -> None` writes `<session>.pre.json` = `{prompt_sha,
     wall, turn, events_n, graph, topic_cache, topic_match}` by tmp + `os.replace`: `prompt_sha` = sha256 of
     the prompt's UTF-8 bytes, `wall` = `time.time()` (sub-second), `turn` = the graph's `turn`
     counter (`stm.py:692` increments it once per recorded input), `events_n` = R9's event count
     below, `graph` = the focus graph, `topic_cache` = 19.6 R3's cache (`{}` until 19.6), `topic_match` = 19.6 R9's map (`{}` until
     19.6).
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
     (`stm.py:705-710`: `_load_graph`, `_apply_turn`, `_save_graph`), so a PostToolUse ingest concurrent with the input hook can lose one of
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
    `code`, `doc`, `concept` and `memory` (`cli.py:10317` `_DEFAULT_EMBED_KINDS`;
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
    (`store.py:2578`). So:
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
    - **`memory_get_by_name`**: `rmx memory get <name>` (CLI, `cli.memory_get`, `cli.py:11371`, on BOTH its verb path
      and its replica fall-through) and the MCP `rmx_memory` `get` action (`verbs.memory`,
      `verbs.py:1157`), when the lookup was by NAME (not by id) and `<name>` equals a delivered
      `name` with `kind=memory` and the same `scope` (`--scope global` per 19.1 R6 matches only
      `scope=global`). Recall's internal per-hit read (`_call(root, "memory_get", …)`,
      `verbs.py:813`) and the daemon op `_op_memory_get` never emit (19 #b-6).
    - **`context_by_name`**: `verbs.context` (`verbs.py:585`, the MCP route) and the three CLI
      context routes of R3, when the call's `ref`, stripped, equals a delivered `name` exactly
      (case-sensitive) AND this context call DELIVERED an item of that same `name` and the same
      `kind` as the delivered event: either its anchor (by R10a's kind), or, for `kind=memory`,
      the memory body it attached to a concept/doc/code anchor (R11; round-3 #s-1). So the
      documented common case, `rmx context <slug>` landing on the thin concept node with the
      memory's body attached, IS a use of the memory; a code symbol that shares a memory's name
      and gets no memory body attached is not. One context call emits at most one `used` per
      `(name, kind, scope)`.
    - **`focus_note`**: `verbs.focus_note` (`verbs.py:956`; the CLI `rmx focus note`, `cli.py:1411`,
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
   **2b. A skipped call is a row** (round-8 #nm-5). The sandbox daemon socket path
   (`daemon.socket_path(<tmp root>)`, `daemon.py:527`) is held by a test-owned unix listener that
   accepts and never replies (a plain `socket.socket(AF_UNIX)`, not a mock of `src/`). **Busy
   precondition** (round-10 #s10-2): the sandbox root's daemon pid file
   (`daemon.pid_path(<tmp root>)`) names a live helper process the test spawns whose argv
   contains "rmx" (`[sys.executable, "-c", "import time; time.sleep(60)",
   "rmx-sandbox-helper"]`), and the test asserts `discovery.daemon_status(<tmp root>,
   retries=0)["busy"] is True` before the hook runs, so the leg cannot pass through another path
   (with no such pid file the route is `VerbAbsentError`, a `ClickException`). The row's
   `skipped_budget` comes from `require_daemon`'s `VerbBusyError` under `budgeted=True` (R4's
   route 1). The GENERATED per-prompt recall command, fed a UserPromptSubmit envelope, exits 0
   with `[]`, and
   the store's `query.log` gains exactly one `kind=recall` row with `outcome=skipped_budget`,
   `budget_s=5` and the envelope's `session`, and `recall-events.jsonl` gains no event for it; the
   same run against a live sandbox daemon logs `outcome=ok`. `rmx telemetry --agent-usage` over
   both rows prints `prompt_recall: ok=1 skipped_budget=1 error=0`, and run with no daemon and
   no listener prints `expired_reads: unavailable (daemon down)`, never `0`. **Non-budget leg**
   (round-9 #m9-5; round-10 #s10-2: the round-9 accept-and-close listener failed the ping, so
   the run stopped at `require_daemon` as absent and never reached the recall op): the test
   listener answers exactly ONE ping with a valid reply (the line `{"ok": true}`, what
   `daemon.ping` checks, `daemon.py:571-596`), then closes its listening socket and leaves the
   socket file in place, so the recall op's connect raises `ConnectionRefusedError` (an
   `OSError`, R4's route 2). The same command exits 0 with `[]` and logs exactly one
   `kind=recall` row with `outcome=error` (not `skipped_budget`) and no recall event.
   **Mid-answer leg** (round-10 #s10-2): the listener answers the ping, then accepts the recall
   connection and closes it without a reply; `daemon.call` raises `json.JSONDecodeError`; the
   command exits 0 with `[]` (no traceback on stderr) and logs one `kind=recall` row with
   `outcome=error`. **Validation leg:** a `log_query` handle given `t.outcome = "timeout"` writes
   `outcome=error`, `error="outcome-invalid: timeout"`, and `--agent-usage` prints
   `outcome-invalid=1`. RED at HEAD: no `kind=recall` row is written at all (the failing
   assertion is the row count).
3. **Precedence.** `invocation_source()` returns, for the env combinations
   {explicit `hook` + `CLAUDECODE`, `CLAUDECODE` alone, tty alone, none}: `hook`, `agent`,
   `interactive`, `unknown`. RED at HEAD on `CLAUDECODE` alone (returns `unknown`).
4. **Session never guessed** (round-4 #s-1: bug-109's names; round-6 #b-1: owner pinned). Two
   `rmx scan-prompt` runs in ONE tmp root, fed envelopes with different `session_id`s, plus a
   newer STM ring for a third session id on disk, log disjoint `session` values equal to their own
   envelopes' ids. Every child in this AC runs with `CLAUDE_PID` = the test process's pid, a real
   ancestor of the child, so `owner_lookup()` returns `(test pid, "found")` whatever terminal or
   Claude process the suite itself runs under (without it, bug-109 records nothing in a plain
   terminal and the row assertion below would depend on the runner). With no envelope, no pointer
   for that owner and no `RMX_SESSION` (and `CLAUDE_CODE_SESSION_ID` set to the third id, which no
   path reads), `session` is null, not the third ring's id, and `_errors.jsonl` gains exactly one
   `pointer-unresolved` row naming `owner` = the test pid. A pointer whose `pid_start` does not
   match the live process's start time is ignored (`session` null) and recorded as
   `pointer-stale`. **Lookup-failed leg** (in process): with `stm._proc_info` and
   `stm._ps_comm_chain` monkeypatched in the TEST to return `None` (a dependency of the function
   under test, registered in `workflow/test_mock_registry.md`), `verbs.resolve_session_source(root,
   None, purpose="event")` returns `(None, "none")` and adds exactly one `owner-lookup-failed`
   row. RED at post-109 `master`: the failing assertions are `session is None` (bug-109 returns
   the newest ring, source `latest`) and the `pointer-stale` row (bug-109 returns `None`
   silently). The lookup-failed leg is a GREEN regression guard for the row (bug-109 writes
   `owner-lookup-failed` today, `verbs.py:561-562`) and is not counted as RED.
   **Read and write legs** (round-7 #s-4: the row was pinned for `event` only, so a resolver that
   records only for `event` survived). Same `CLAUDE_PID` setup, no pointer for the test pid, no
   `RMX_SESSION`, two rings on disk: (a) `rmx focus note x` (a `write`) exits 2 with ONE stderr
   line naming the sources tried, both rings' line counts are unchanged, and `_errors.jsonl`
   gains exactly one `pointer-unresolved` row with `owner` = the test pid and `root` = the tmp
   root; (b) `rmx focus tail` (a `read`) prints the newest ring labelled `(newest ring; not
   resolved)` and adds exactly one such row. Each row's delta is counted per command, and both
   rows appear in `handoff.compose_recall_state`'s anomalies for that root under the
   session-pointer clause (D6). RED at post-109 `master`, failing assertion: (a)'s newer ring's
   line count (bug-109 writes the note there and exits 0); (b) is a GREEN regression guard for
   the row (bug-109 records it on its `latest` fall-through) and is not counted as RED. Every row
   asserted in this AC carries `root` = the tmp root and `owner_start` = the test process's
   `_proc_start` (D8).

   **4b. Pointer location, surfacing, scope, migration and cleanup** (D3, D6, D7, D8; bug-109 r1
   #m-4; round-6 #b-1; round-7 #s-2, #s-3, #m-4 (a)). Every child runs with `CLAUDE_PID` set as in
   AC-4.
   (i) The input hook run with cwd in tree X writes the pointer under the sandbox's global
   `by-pid/`; an MCP server spawned with cwd in tree Y resolves it.
   (ii) **Legacy pointer dropped, not read** (round-7 #s-3). A pointer present only at bug-109's
   legacy `X/stm/by-pid/<test pid>.json` is NOT read: `resolve_session_source(X, None,
   purpose="event")` returns `(None, "none")` and records `pointer-unresolved`. The first
   SessionStart run in X deletes that file and prints `legacy_pointers_dropped=1`; an input hook
   with an envelope then writes the new-location pointer, and the same call resolves it.
   (iii) With three rows owned by the test pid added since its watermark, the generated
   SessionStart command prints one stdout line naming their reasons and counts, and a second run
   prints none.
   (iii-b) **Halving** (round-7 #m-4 (a): the round-6 text asked for rows the halving had
   deleted). After (iii), N further rows owned by the test pid are written until the file crosses
   `_ERRORS_MAX_BYTES` and halves once. The next SessionStart run prints each SURVIVING owned row
   with `t` above the watermark exactly once, plus the `errors-truncated` row whose `dropped`
   equals the removed row count (the test counts lines before and after; the file held no
   earlier `errors-truncated` row, so nothing rolls up here, D6) and whose
   `unseen_dropped["<test pid>:<start>"]` equals the removed owned rows with `t` above the
   watermark; surfaced rows + `unseen_dropped` = N (the three surfaced rows dropped by the halving
   are in `dropped`, not in `unseen_dropped`).
   (iv) A pointer AND an `_errors.seen.<pid>` file for a pid that no longer exists (a child process
   the test started and reaped) are removed by the SessionStart run and `pruned=2` is printed.
   (iv-b) With `stm._proc_info` monkeypatched in the test to return `None` for every pid, the
   prune (called in process) removes no file and prints `prune skipped: process lookup
   unavailable`.
   (v) **recall-state reads the new location:** a row written through `record_pointer_error`
   (now under the global `by-pid/`) with `root` = X appears in `handoff.compose_recall_state`'s
   anomalies and in `rmx recall-state`'s output for X, and in `rmx focus topics`' last line for X
   (a store with no topics included: the line follows "no topics yet").
   (vi) **One-shot migration** (round-7 #s-3). A legacy `X/stm/by-pid/_errors.jsonl` holding two
   parseable rows (`t` = now − 1 h and now − 2 h) and one unparseable line: the first SessionStart
   run in X appends the two rows to the global log with their ORIGINAL `t`, `root` = X and
   `migrated_from` = the legacy path, plus one `legacy-unreadable` row with `n = 1`, renames the
   file to `X/stm/by-pid/_errors.migrated.jsonl`, and prints `migrated=2`; `rmx recall-state` in
   X then reports both rows. A second run migrates nothing (`migrated=0`, the global log's line
   count unchanged). An interrupted run (the test restores the legacy name after the first run,
   so the rows are present in both files) appends nothing again and renames the file. After the
   migration no read of `X/stm/by-pid/` happens: the test removes read permission on that
   directory and recall-state for X still succeeds with the same counts.
   (vii) **Scope** (round-7 #s-2). Two sandbox roots X and Y, one `pointer-unresolved` row scoped
   to each: `rmx recall-state` in X reports exactly X's row, in Y exactly Y's. Two owners: P1 =
   the test process, P2 = a helper process the test starts that runs the SessionStart hook as its
   own child with `CLAUDE_PID` = P2. One row owned by each. P1's SessionStart run surfaces only
   P1's row and writes only `_errors.seen.<P1>`; P2's run afterwards still surfaces P2's row. One
   `no-owner` row (owner `null`) scoped to X is surfaced by neither run (each prints
   `unowned_in_root=1` for X) and is reported by recall-state in X. A row written with no `root`
   field is counted as `unscoped-row` in both X's and Y's recall-state, never under either's
   pointer clause. **`ps-failed` sub-leg** (round-8 #nm-1): with `stm._proc_info` monkeypatched in
   the test to return `None` for ONE helper pid only (registered in
   `workflow/test_mock_registry.md`), `write_pid_pointer` for that pid writes a `ps-failed` row
   whose `owner` is that pid and `owner_start` null; P1's SessionStart in X does not print it
   under its own reasons, counts it in `unowned_in_root`, and does not consume it (a second run
   counts it again); recall-state in X reports it.
   (viii) **Two clauses** (round-7 #s-2). In X, one `pointer-unresolved` row and one
   `sweep-failed` row: recall-state prints a session-pointer clause counting 1 with the
   "could not be resolved" text, and an STM-hook clause counting `sweep-failed x1` whose text
   contains none of the words `session`, `guessed`, `newest`.
   (ix) **Ended sessions** (round-8 #ns-2; reordered in round 9, #s9-2, so the older row
   belongs to the owner that is still alive). In this order:
   1. a helper process P3 (started by the test, with `CLAUDE_PID` = P3 for its own child)
      writes one `pointer-unresolved` row scoped to X FIRST and stays alive;
   2. a helper P2, the same way, then writes one row scoped to X (a larger `t`), exits and is
      reaped;
   3. P1's generated SessionStart run in X prints `ended_sessions: pointer-unresolved=1`
      exactly once (P2's row) and does not print P3's; the per-root file's `consumed` holds
      exactly `[P2, P2_start, <P2's row t>]`;
   4. a second P1 run prints no `ended_sessions` line;
   5. P3 exits; the next run prints P3's row as `ended_sessions` once, although its `t` is
      BELOW P2's; a further run prints none.
   recall-state in X still reports all rows (consumption is the SessionStart surface's only).
   **Pruning:** a `consumed` entry whose `t_max` the test sets to 25 h ago is gone after the
   next run, and that owner's rows (also 25 h old) are not printed again. With
   `stm._proc_info` monkeypatched to return `None` for every pid (in process, as (iv-b)), the
   run prints `ended_sessions skipped: process lookup unavailable` and the per-root file is
   unchanged.
   (x) **One writer, concurrent** (round-8 #nm-2; round-9 #m9-3). Two processes each append
   2,000 rows through `record_pointer_error` while the file halves at least THREE times (about
   800 KB against 256 KiB, so earlier `errors-truncated` rows are themselves dropped): the
   file's count of rows other than `errors-truncated` plus the sum of `dropped` over the
   `errors-truncated` rows still in the file equals 4,000 exactly (no append lost to a halving,
   no count lost with a dropped truncation row); the same identity holds per root over
   `dropped_by_root`; and every line parses. **News leg** (round-10 #m10-3): after the first
   halving, a SessionStart run for the test owner surfaces the first `errors-truncated` row T1
   (its watermark passes `t1`); after a later halving drops T1, no later row's
   `unseen_dropped["<test pid>:<start>"]` includes T1's count (it equals the owned rows removed
   with `t` above the watermark, recounted by the test), while `dropped` still does.
   (xi) **Migration claimed once** (round-8 #nm-2; round-9 #m9-4). The legacy log's mtime is
   set to one DAY old (`os.utime`) before two SessionStart runs in X are started together (a
   barrier file releases both) over it (two rows): the global log gains exactly two migrated
   rows; exactly one run prints `migrated=2`, the other `migrate-claim-lost=1`, and neither
   adopts the other's live claim. With the global store root absent, a run appends nothing,
   leaves `_errors.migrating.<pid>.<token>.jsonl` in place (no `.migrated`), prints `migration
   incomplete` and exits; after the root is created, the next run adopts that claim (its pid is
   dead: `owner_alive(pid, start_token=token) is False`) and migrates both rows. A claim file
   named with the pid and token of a LIVE helper process is not adopted. A `legacy-unreadable`
   row is migrated once across two runs (its `t` is the legacy file's mtime).
   (xii) **Bypass checks** (round-8 #nm-2, #nm-4; the user's converge rule). AST scans of
   `src/refmatrix/`: (a) every WRITE operation on an `_errors` path (D8's list: write-mode
   `open`, `write_text`, `write_bytes`, `os.replace`, `os.rename`, `unlink`, whose path holds an
   `_errors` constant or derives from `errors_log_path()` / `pointer_dir()`) sits inside D8's
   allow-listed `stm.py` functions; docstrings and messages are not listed (round-9 #m9-2);
   (b) the set of functions that call `_proc_start(` equals {`owner_alive`,
   `liveness_available`, `proc_identity`} (round-10 #m10-2: `write_pid_pointer` and
   `record_pointer_error` take the start value from `proc_identity`; round-9 #m9-1:
   `read_pid_pointer` goes through `owner_alive`), and the set that
   call `_proc_info(` equals {`_proc_start`, `owner_lookup`} (`stm.py:201`, `:249`), so a
   prune, a surfacing path or a pointer read cannot judge liveness on its own; (c) no
   `json.load(sys.stdin)` / `json.loads(` of a stdin read in `cli.py` or `scan.py` outside
   `read_hook_envelope`, and D9's prompt-key check. Each list is a set equality with a list
   kept in the test, and each check is also run on a planted fixture module that it must
   report (a write-mode `open` of `_errors.jsonl`; a `_proc_start(` call in a new function; a
   `json.loads(sys.stdin.read())`), so none of the three can pass vacuously.
   (xiii) **Prose is not an error** (round-9 #s9-4). `printf 'fix the {braces' | rmx
   scan-prompt` (and the same text piped to `rmx memory recall` without `--stdin-json`) adds no
   row to `_errors.jsonl`, and the prompt the command uses equals `fix the {braces`. The same
   text to `rmx memory recall --stdin-json` exits nonzero with the existing `--stdin-json:
   invalid JSON on stdin` message AND adds one `envelope-unreadable` row. An envelope
   `{"text": "abc"}` yields the prompt `abc` on both the scan-prompt and the recall path (one
   `HOOK_PROMPT_KEYS`).
   RED at post-109 `master` for (i)-(v), (vii) and (viii) (no global location, no SessionStart
   entry, no scope fields, one clause); (vi) is RED (no migration: the legacy rows are read in
   place and the file is not renamed); (ii)'s first assertion is RED (bug-109 resolves the
   legacy pointer). (ix)-(xi) are RED (no dead-owner set, no lock, no claim). (xiii)'s
   `{"text": "abc"}` recall leg is RED (`_resolve_query` reads `prompt` only), and so is its
   `--stdin-json` leg's `envelope-unreadable` row (round-10 #m10-5: no row is written today; the
   exit and message already hold); its prose legs are
   GREEN regression guards at `master` (no envelope reader records anything today) and are not
   counted as RED. (xii) is RED on
   all three: (a) the halving's `write_text` in `record_pointer_error` sits outside any
   `_errors_locked` (which does not exist); (b) `owner_alive` does not exist, so the function
   set differs; (c) `cli.focus_hook`, `cli._resolve_query` and `scan.read_stdin_prompt` parse
   their own envelopes.
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
   `ensure_ascii=True` (`cli.py:12155`, `:12367`, both in `cli.memory_recall`), so its payload is ASCII and byte offsets equal
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
    - the watermark kept as a byte offset (AC-4b (iii-b): after the halving, rows are skipped or
      repeated);
    - the halving without its `errors-truncated` row (AC-4b (iii-b));
    - `session_pointer_anomalies` left reading `<root>/stm/by-pid/` (AC-4b (v): the new-location
      row is absent from recall-state);
    - (WITHDRAWN round 7: "the legacy `_errors.jsonl` dropped from the merged read before its
      release ends"; there is no legacy read, round-7 #s-3);
    - the legacy pointer still read as a fallback (AC-4b (ii): it resolves);
    - the migration stamping migrated rows with the migration time instead of their original `t`
      (AC-4b (vi): the rows' `t` differ from the fixture's);
    - the migration appending without the `(t, reason, migrated_from)` check (AC-4b (vi): the
      interrupted run duplicates the rows);
    - the migration leaving the legacy file in place (AC-4b (vi): no `_errors.migrated.jsonl`,
      and the second run reports `migrated=2` again);
    - `read_pointer_errors` ignoring `root=` (AC-4b (vii): X's recall-state counts Y's row);
    - one global watermark file instead of one per owner (AC-4b (vii): P2's row is consumed by
      P1's run);
    - the SessionStart writer surfacing `owner: null` rows as its own (AC-4b (vii): they are
      printed and consumed);
    - an unscoped row attributed to the reader's root (AC-4b (vii): it is counted under X's
      pointer clause);
    - the "could not be resolved" text applied to STM hook failures, or one combined count
      (AC-4b (viii));
    - `unseen_dropped` counting rows at or below the watermark (AC-4b (iii-b): surfaced +
      `unseen_dropped` exceeds N);
    - the prune leaving `_errors.seen.<pid>` files of dead pids (AC-4b (iv): `pruned=1`);
    - `rmx focus topics` printing the pointer line only when topics exist (AC-4b (v): the
      no-topics store);
    - the resolver recording the miss only for `purpose="event"` (or `event` and `read`)
      (AC-4 write leg: no row for `focus note`);
    - the prune removing pointers when `_proc_start` is unavailable for every pid (AC-4b (iv-b):
      the live pointer is removed);
    - the resolver recording nothing when `owner_lookup()` fails (AC-4's lookup-failed leg);
    - (round 8) dead-owner rows never surfaced (AC-4b (ix): no `ended_sessions` line);
    - live other-owner rows surfaced in `ended_sessions` (AC-4b (ix): P3's row prints while P3
      lives);
    - the per-root `consumed` set not advanced, or advanced outside the lock (AC-4b (ix): the
      second run prints the line again);
    - (round 9, #s9-2) the round-8 per-root `t` watermark kept instead of `consumed` owners
      (AC-4b (ix) step 5: P3's row, older than P2's, is never printed);
    - `consumed` entries never pruned, or pruned without the `since` window (AC-4b (ix)
      pruning leg: the file keeps the 25 h entry, or that owner's rows print again);
    - (round 9, #s9-4) `prose_ok` ignored (AC-4b (xiii): the brace prompt adds a row);
    - `_resolve_query` keeping its own `prompt`-only read (AC-4b (xiii): `{"text": "abc"}`
      yields `""` on the recall path);
    - (round 9, #m9-1) `read_pid_pointer` comparing `_proc_start` itself, or a new caller of
      `_proc_info` (AC-4b (xii)(b));
    - `liveness_available` folded back into `owner_alive`'s `None` (AC-4b (iv-b), (ix): the
      unowned rows and the unavailable lookup are no longer told apart; (xii)(b)'s set
      differs);
    - (round 9, #m9-2) handoff building its own `_errors.jsonl` path (AC-4b (xii)(a)'s second
      check);
    - (round 9, #m9-3) a halving that does not roll up the dropped truncation rows' counts
      (AC-4b (x): the identity falls short of 4,000);
    - (round 9, #m9-4) claim adoption by mtime (AC-4b (xi): the one-day-old legacy file makes
      the second run adopt the first's live claim, and `migrated=2` prints twice or the counts
      split); a `legacy-unreadable` row stamped with the run's clock (AC-4b (xi): it migrates
      twice);
    - (round 9, #m9-5) a non-budget `OSError` classified as `skipped_budget` (AC-2b's
      non-budget leg, which since round 10 reaches the recall op's connect);
    - (round 10, #s10-2) `json.JSONDecodeError` left out of the degrade tuple (AC-2b's
      mid-answer leg: a traceback and a nonzero exit); the busy precondition dropped (AC-2b:
      the `busy` assertion fails before the hook runs);
    - (round 10, #m10-2) a new function calling `_proc_start(` for a start value instead of
      `proc_identity` (AC-4b (xii)(b));
    - (round 10, #m10-3) `unseen_dropped` rolled up unconditionally like `dropped` (AC-4b (x)'s
      news leg: T1's count reappears); `log_query` keeping an outcome outside `CALL_OUTCOMES` (AC-2b's
      validation leg);
    - `ended_sessions` computed when the lookup is unavailable (AC-4b (ix): live rows consumed,
      the watermark moves);
    - a row with null `owner_start` matched by its `owner` (AC-4b (vii) `ps-failed` sub-leg: it is
      printed as P1's or consumed);
    - the halving outside the lock, or by `write_text` in place (AC-4b (x): the line-count
      identity fails);
    - the migration without the claim rename (AC-4b (xi): four rows migrated);
    - the legacy file renamed before every append returned `True` (AC-4b (xi): the absent-root
      run renames it and the rows are lost);
    - a second writer of `_errors.jsonl`, a private liveness check, or a private envelope parse
      (AC-4b (xii));
    - a budget skip writing no row, or `outcome=ok` (AC-2b);
    - `expired_reads` printed as 0 when the daemon is down (AC-2b's report run with the daemon
      stopped prints `unavailable`);
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
| `src/refmatrix/stm.py` | EXTEND bug-109's pointer code: `pointer_dir()` and the user-level location, no legacy read (D3); the `hook` field (D4); `pointer-stale` / `pointer-unreadable` rows (D5); `record_pointer_error(reason, *, root, owner, **fields)` writing scoped rows (`root`, `owner`, `owner_start`) and, when it halves, the `errors-truncated` row with `dropped_by_root` / `unseen_dropped` (D8, D6); `read_pointer_errors(*, root=None, owner=None, since)` over the new location only, scope-filtered, `unscoped-row` counted (D6); the per-owner `t`-keyed watermark `_errors.seen.<pid>` (D6); the one-shot migration of a root's legacy log and pointers (D6, D3); the prune of pointers and watermark files through `owner_alive` (D7). Round 8: `owner_alive` (D6); the per-root watermark `_errors.seen.root.<h>` and the `ended_sessions` set (D6, #ns-2); unowned = null `owner` or null `owner_start` (D6, #nm-1); `_errors_locked` + `_append_error_rows`, the ONE locked writer, tmp + `os.replace` halving, the migration's claim-by-rename and append-before-rename order (D8, D6, #nm-2); `read_hook_envelope` (D9, #nm-4). Round 9: set (2) consumed by owner, `{root, consumed: [[pid, pid_start, t_max]]}`, 24 h prune (D6, #s9-2); `HookEnvelope`, `prose_ok`, `HOOK_PROMPT_KEYS` (D9, #s9-4); `liveness_available`, `owner_alive(…, start_token=)`, `start_token`, `proc_identity` (round 10, #m10-2), `read_pid_pointer` through `owner_alive` (D6, D7, #m9-1); `errors_log_path` (D8, #m9-2); truncation-count roll-up (D6, #m9-3); claim name with the start token, adoption only of a dead claimant, `legacy-unreadable` `t` = legacy mtime (D6, #m9-4). NEW: `snapshot_pre_prompt`, `pre_prompt_state` + `PrePromptState`, `PRE_PROMPT_SKEW_S`; input events gain `prompt_sha` and `t` (R9). Built here or by 19.0, whichever merges first |
| `src/refmatrix/hooks.py`, `cli.py` (`focus hook`, `focus topics`) | the generated SessionStart entry `rmx focus hook --event session-start` (matcher `startup\|resume\|clear\|compact`, stderr kept) that writes the pointer, migrates its root's legacy files once, surfaces its owner's rows AND its root's ended-session rows and prunes (D3, D4, D6, D7); every envelope parse through `stm.read_hook_envelope` (D9: `focus hook`, `_resolve_query`, `scan.read_stdin_prompt`); the input branch reordered: pointer write (existing) → `snapshot_pre_prompt` → sweep (failure recorded) → input record (R9); `focus topics` (`cli.py:1234`) prints the scoped clauses as its last line, also with no topics (D6; round-7 #m-4 (b)) |
| `src/refmatrix/handoff.py` (`session_pointer_anomalies`, `:508-529`) | EXTENDED, not paralleled (round-6 #b-1): reads `<pointer_dir>/_errors.jsonl` through `read_pointer_errors(root=root, …)` and names it through `stm.errors_log_path()` (round-9 #m9-2), no legacy read (round-7 #s-3); prints the session-pointer clause, the STM-hook clause and the truncation clause apart (round-7 #s-2); its text names the new path (D6) |
| `tests/test_mcp_session_pointer.py` | EXTENDED, not paralleled (bug-109's file): AC-1b, AC-4, AC-4b |
| `src/refmatrix/store.py` | `find_memory_any_partition` (`:2578`) returns the chosen row's partition name (R11) |
| `src/refmatrix/telemetry.py` | `CALL_OUTCOMES` (the existing four `outcome` values plus `skipped_budget`); `OUTCOMES_BY_KIND` defined empty, `log_query` validating against `OUTCOMES_BY_KIND.get(kind, CALL_OUTCOMES)` (round-10 #m10-4); `classify_outcome(…, budgeted=)` classifying by exception type; `log_query` honouring a set `t.outcome` and rewriting an outcome outside the vocabulary to `error` / `outcome-invalid` (round-9 #m9-5); `budget_s` on recall and context rows, a skipped call still writing its row (R3, R4; #nm-5); `agent` source + precedence; `session`/`query_id`/`cwd`/`root` on rows; `row_provenance` + `is_test_artifact_row` (R5); the `--agent-usage` report; `RECALL_EVENT_FIELDS_V1`; `emit_recall_events` (the ONE writer, R11); `delivered_in_session` (R12's lookup); `event_kind` (R10a); `recall_channel` (R11); `turn` from `pre_prompt_state` (R9) |
| `src/refmatrix/verbs.py` | caller-side row + events for `context` (`:585`) and `memory_recall` (MCP route); `used` emission in `context`, `memory` `get` action (`:1157`) and `focus_note` (`:956`) |
| `src/refmatrix/cli.py` | `context-daemon` row; `grep-stdin` cardinality; `--agent-usage`/`--until`/`--by-session`; events on the CLI context and recall routes; `used` on `memory get`'s replica fall-through (`cli.memory_get`, `:11371`) and the three CLI context routes |
| `src/refmatrix/scan.py` | `scan_prompt` emitter with payload byte spans, `partition`, and raw phase inputs |
| `src/refmatrix/cli.py` (`memory recall`), `hooks.py` | `json.JSONDecodeError` added to the recall op's degrade tuple (`:12241`, round-10 #s10-2); the single recall-channel emission site (`prompt_recall`, `session_start`, `precompact`, `recall`); the JSON renderer returns byte spans; the generated hook lines carry the envelope through |
| `src/refmatrix/daemon.py` (`_op_stats`, `:3816`) | one key, `expired_reads` (bug-116's counter, `_note_expired_read` `:1362-1368`), read by R7 (#nm-5) |
| `tests/fixtures/agent_usage/` | the redacted frozen `query.log`/`cli.log` cut |

## Test strategy {#test-strategy}

- **Sandbox:** every test runs under 23.0's sandbox ($HOME, global root, registry and LaunchAgents
  redirected before `refmatrix` is imported; spawned `rmx` children refuse sockets outside the tmp
  dir). Subprocess tests additionally pass `HOME`, `REFMATRIX_ROOT` and `RMX_HUB_MODELS=0`
  explicitly, because bug-088's recorder cannot see a child's connects. Each test asserts the live
  log line counts above are unchanged; no test writes the log this task measures (bsd #s-7).
- **RED first** (`feedback_red_test_must_fail_at_head`), against post-bug-109 `master` (round-4
  #s-1), not against the pre-bug-109 tree: AC-1, AC-2 (`context-daemon`), AC-3 (`CLAUDECODE`),
  AC-1b (its four RED legs; its input-hook leg is a GREEN regression guard), AC-2b, AC-4, AC-4b, AC-5,
  AC-7, AC-8, AC-8b, AC-8c, AC-8d, AC-10, AC-11a-f and AC-12 are run before any `src/` change
  and the FAILING ASSERTION is recorded, by name. A test that fails only because a click choice
  (`--event session-start`) or a keyword (`purpose=`) does not exist yet is RED for the wrong
  reason: each such AC first asserts on observable state (the generated config, a row, a ring
  line count) so the recorded failure is that assertion. AC-6 fails at HEAD because
  `--agent-usage` does not parse. No AC is admitted that passes at post-109 `master`.
- **Hook path:** AC-8 runs the command string `hooks.py` GENERATES for UserPromptSubmit, not a
  hand-written one, so a generator change that drops the emitter is caught.
- **No daemon from the STM hooks** (round-7 #m-1). The SessionStart writer (D4, D6, D7) is file
  work only, like the input hook's additions (R3, R8 write caller-side). Its leg of the
  "0 daemon connects" check is [[task-19.0-stm-cluster-hygiene#acceptance]] AC-6f, which runs the
  generated `focus hook --event <e>` commands (`session-start`, `input`, `tool-pre`, `tool`) with
  their `2>/dev/null || true` suffix stripped, under a connect logger and with listeners at every
  daemon (project and global store) and hub path (round-8 #nm-3); whichever of 19.0 / 21.1
  merges first builds that test.

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

## Revision round 6 (2026-10-15) {#rev-round-6}

Answers [[bsd-plan19-21-spec-rereview-r6-0e77da3]] (the 21.1 side of #b-1, #s-1, #m-1, #m-2).
No round-6 decision-log row names plan 21 ([[plan-review-2026-10-14#t12-approvals]] holds
d9ao-d9ar, all plans 16/17/22/23). Code facts read at write time at HEAD `3d3c798` (`src/`
identical to `master` `c7129e6`, which carries bug-109 r1-r4, merged at `0c7d0e0`):
`stm.py:127-165`, `:190-202`, `:205-229`, `:232`, `:236-279`, `:282-288`, `:291`, `:294-315`
(halving `:308-310`), `:318-343`, `:346-375` (`ps-failed` `:368`), `:378-389`, `:392`,
`:511-544` (`ts` `:525`), `:596-618`, `:692`, `:705-710`; `cli.py:1072`, `:1497`, `:1974-2004`
(owner reasons `:1985-1987`, `write-failed` `:1991`); `verbs.py:524-575` (owner lookup `:545`,
the plain-terminal branch `:558-565`), `:892`, `:934`, `:958`, `:972`, `:1029`, `:1068`;
`handoff.py:508-529`, `:569`; `hub.py:100`.

rel: derives-from -> [[bsd-plan19-21-spec-rereview-r6-0e77da3]]

| finding / decision | answered at |
|---|---|
| round-6 #b-1 (the spec extended bug-109 as it stood at r1, not as merged) | header (merge landed); [[#req-session]] "Existing code this task extends" rewritten from `master` (`_proc_info` / `owner_lookup` and its three statuses, `owner-lookup-failed`, `read_pointer_errors`, `handoff.session_pointer_anomalies`, `_ERRORS_MAX_BYTES` and its in-place halving); "Order" names `owner_lookup()` and bug-109's exact recording rule; D3 (`pointer_dir()` creates only `by-pid/`); D5; D6 rewritten (extends `session_pointer_anomalies` with a legacy read, `t`-keyed watermark, halving kept and counted; "left it unread", the 1 MB rename and "nothing is deleted" withdrawn); D7 (`_proc_start` per pid; `_process_table` withdrawn; prune skipped when the lookup is unavailable); AC-4 (owner pinned by `CLAUDE_PID`; lookup-failed leg); AC-4b (iii-b), (iv-b), (v), (vi); mutations; [[#files-to-modify]] (`handoff.py` added; `stm.py` row) |
| round-6 #s-1 (the sweep bypasses the origin ladder) | [[#req-session]] "The pre-prompt state" writer step 3 (each swept call gets 19.0 R2's origin). Built and tested in 19.0 ([[task-19.0-stm-cluster-hygiene#rev-round-6]]) |
| round-6 #m-1 (citations stale since the merge) | [[#req-session]] "Existing code" and "The pre-prompt state" (`cli.py:1974-2004`, sweep `:1998-2001`, except `:2000-2001`, record `:2003-2004`; `stm.py:525`, `:692`, `:705-710`; `latest_session` `stm.py:392`); the resolver's owner call named `owner_lookup()`. bug-109's registry row is `fixed` (the round-5 row above said open) |
| round-6 #m-2 (the 21.1 → 19.1 edge one-sided) | `rel: related-to -> [[task-19.1-pack-recall-under-budget]]`; header "Downstream" line |
| round-6 #b-2, #s-2, #s-3 | not 21.1 items (19.0 R5, 19.6, 19.3 / 19.4) |

## Revision round 7 (2026-10-15) {#rev-round-7}

Answers [[bsd-plan19-21-spec-rereview-r7-331b414]] (the 21.1 side of #s-2, #s-3, #s-4, #m-1 and
#m-4 (a), (b)). The user took the recommended one-shot migration for #s-3
([[plan-review-2026-10-14#t12-approvals]], round-7 item 2); #s-2 and #s-4 needed no decision.
Code facts read at write time at HEAD `77ac38f` (its `src/` equals the review's `331b414`):
`stm.py:197-202`, `:291-343` (halving `:308-310`), `:368`; `cli.py:1209-1210` (`focus show`
takes `LINE`), `:1234-1276` (`focus topics`, its "no topics yet" early return), `:1974-2004`
(`record_pointer_error` at `:1985`, `:1991`); `verbs.py:540-569` (rows at `:562`, `:564`);
`handoff.py:508-529`. bug-115/116 ship as 0.78.2 (ping on the dispatcher, heartbeat on cli
completions, expired reads dropped, `daemon.call` sends `deadline_s` and does not re-send after a
send): that bounds what a daemon call from a hook would cost, and the "0 daemon connects" check
still stands, because these hooks should make none.

rel: derives-from -> [[bsd-plan19-21-spec-rereview-r7-331b414]]

| finding / decision | answered at |
|---|---|
| round-7 #s-2 (the user-level log and its watermark are unscoped: recall-state counts other projects' rows; the first SessionStart anywhere consumes every session's rows; "guessed session" text over hook failures) | [[#req-session]] D6 (every row scoped; `read_pointer_errors(*, root, owner, since)`; `unscoped-row` counted apart; three clauses in `session_pointer_anomalies`; per-owner watermark `_errors.seen.<pid>` keyed on `t` and `pid_start`; `owner: null` rows reported by root, never consumed; `errors-truncated` carries `dropped_by_root` and `unseen_dropped`), D7 (watermark files pruned), D8 (`record_pointer_error(reason, *, root, owner)`; `owner_start`; every call site named); AC-4b (vii), (viii); mutations; [[#files-to-modify]] (`stm.py`, `handoff.py`) |
| round-7 #s-3 (two "for one release" legacy reads with no removal task) | D3 (legacy pointers never read; `pointer-legacy-location` withdrawn); D6 "One-shot migration" (original `t`, `root`, `migrated_from`; `legacy-unreadable`; rename to `_errors.migrated.jsonl`; idempotent; legacy pointers deleted; no legacy read path at any time; the unvisited-root limit stated); AC-4b (ii), (vi) rewritten as migration legs; mutations (the round-6 legacy-read mutation withdrawn; five new); [[#files-to-modify]] |
| round-7 #s-4 (21.1 half: the miss row pinned for `event` only) | [[#req-session]] "Order" (all three purposes pinned); AC-4 read and write legs (`CLAUDE_PID` = test pid; one row each with `owner`, `root`; visible in `compose_recall_state`); mutation (records only for `event`). The 19.0 half (AC-6c's hook leg): [[task-19.0-stm-cluster-hygiene#rev-round-7]] |
| round-7 #m-1 (21.1 side: the SessionStart writer's daemon cost) | [[#test-strategy]] (file work only; its "0 daemon connects" leg is 19.0 AC-6f) |
| round-7 #m-4 (a) (AC-4b (iii-b) asked for rows the halving deleted) | AC-4b (iii-b) (surviving rows once; `dropped` = removed lines; `unseen_dropped` = removed owned rows above the watermark; surfaced + `unseen_dropped` = N) |
| round-7 #m-4 (b) (`focus show` takes a required `LINE`) | D6 (`rmx focus topics` prints the clauses, also with no topics); AC-4b (v); [[#files-to-modify]] |
| round-7 #s-1, #m-2, #m-3, #m-4 (c), (d); d9ax, d9ay | not 21.1 items: [[task-19.6-phased-context-and-topic-cache#rev-round-7]], [[task-19.0-stm-cluster-hygiene#rev-round-7]], [[task-19.2-memory-usage-record#rev-round-7]] |

## Revision round 8 (2026-10-15) {#rev-round-8}

Answers [[bsd-plan19-21-spec-rereview-r8-23ad703]] (the 21.1 side of #ns-2, #nm-1, #nm-2, #nm-4,
#nm-5, #nm-7). No user decision was needed: #ns-2's fix restores the round-6 intent inside the
round-7 scope rule. Code facts read at write time at HEAD `23ad703`: `stm.py:197`, `:294-315`
(the unlocked halving `:305-307`), `:346-375` (`ps-failed` `:359-369`), `:378-389`;
`cli.py:1963-1967`, `:1974-2004`, `:5097-5098`, `:5149`, `:5228`, `:6199`, `:7518`,
`:8969-9013`, `:10317`, `:10763`, `:11371`, `:12004-12025`, `:12155`, `:12367`;
`scan.py:1036-1054`; `hooks.py:111`, `:131-147`, `:209-297`, `:265-266`, `:277-278`, `:313`;
`search_hooks.py:309`; `daemon.py:527`, `:629-670`, `:1362-1368`, `:3816`, `:4714`, `:6067`,
`:6108`; `verbs.py:585`, `:813`, `:956`, `:1157`; `store.py:2578`; bug-118's registry row
(open). Older revision tables keep the lines of their own HEAD.

rel: derives-from -> [[bsd-plan19-21-spec-rereview-r8-23ad703]]
rel: related-to -> [[bug_registry]]

| finding / decision | answered at |
|---|---|
| round-8 #ns-2 (per-owner SessionStart surfacing reaches only the same Claude process; an ended session's rows, its last Stop's `write` miss included, surface on no SessionStart) | [[#req-session]] D6 (two sets: the owner's rows, and the root's DEAD-owner rows since a per-root watermark `_errors.seen.root.<sha1(root)[:12]>`, printed as `ended_sessions:`; live other owners untouched; `owner_alive` the one predicate; lookup-unavailable guard; claimed under the lock); D7 (per-root watermark files kept, removed only when the root is gone); AC-4b (ix); mutations (dead-owner rows never surfaced; live other-owner rows surfaced; watermark not advanced or advanced outside the lock; computed with the lookup unavailable); [[#files-to-modify]] |
| round-8 #nm-1 (`ps-failed` rows carry `owner` but a null `owner_start`, so no surface matches them) | D6 "Unowned rows" (null `owner` OR null `owner_start` = unowned, `unowned_in_root`, never consumed, not in `ended_sessions`); AC-4b (vii) `ps-failed` sub-leg; mutation |
| round-8 #nm-2 (machine-wide log; halving, appends and migration unlocked; no append-before-rename order) | D8 "ONE locked writer" (`_errors_locked` flock on `_errors.lock`; `_append_error_rows` the only writer; halving by tmp + `os.replace` under the hold; watermarks advanced under it; AST bypass check); D6 migration (claim by rename to `_errors.migrating.<pid>.jsonl`, loser counted; crash adoption after 60 s; rename to `.migrated` only after every append returned `True`; idempotence check inside the hold); AC-4b (x), (xi), (xii)(a); mutations |
| round-8 #nm-4 (21.1 side: envelope parsing; the user's converge rule) | D9 `stm.read_hook_envelope` (one parser for `focus hook`, `_resolve_query`, `scan.read_stdin_prompt` and the two new readers; `envelope-unreadable` / `envelope-no-session` rows; falsy session; the `2>/dev/null \|\| true` suffix left to bug-118's one renderer); AC-4b (xii)(c). The 19.0 hook leg: [[task-19.0-stm-cluster-hygiene#rev-round-8]] |
| round-8 #nm-5 (a budget skip is invisible in telemetry; the daemon's own drop unreconciled) | R3 (a skipped call writes its row); R4 (`outcome` ∈ `CALL_OUTCOMES` = ok / skipped_budget / error, `budget_s`, on recall and context rows; one vocabulary shared with 21.3); R7 (outcomes per channel; `expired_reads` from `_op_stats`, `unavailable` when the daemon is down); AC-2b; mutations; [[#files-to-modify]] (`telemetry.py`, `daemon.py`). Consumed by [[task-19.5-measure-delivery#rev-round-8]]; 21.3's clause: [[task-21.3-indexed-symbol-nudge#rev-round-8]] |
| round-8 #nm-7 (cites drifted; four already wrong at r7) | one cite-refresh pass, symbol + line read at `23ad703`: [[#why]] (`daemon.py:4714`, `verbs.py:585`, `cli.py:5149`, `:5097-5098`, `:5228`, `:6199`); R3 (`cli.py:10763`, `search_dense_cmd`); R6 (`:6199`); R7 (`:7518`); R9 (`hooks.py:265-266`); R10a (`cli.py:10317`); R11 (`store.py:2578`); R12 (`cli.memory_get` `:11371`, `verbs.py:1157`, `:813`, `:585`, `:956`); AC-8d (`cli.py:12155`, `:12367`); [[#files-to-modify]] |
| user rule: converge repeated shapes; flag other duplicates | D6 `owner_alive`; D8 `_append_error_rows`; D9 `read_hook_envelope`; R4 `CALL_OUTCOMES`; each with an AST or test bypass check (AC-4b (xii), AC-2b). Flagged, NOT converged here (out of scope): the PreToolUse/PostToolUse envelope parses in `search_hooks.py:309` (grep guard, plan 16's) and the enqueue one-liner `hooks.py:111` (a `python3 -c` string, not module code); the generated focus entries' `2>/dev/null \|\| true` suffix (bug-118's renderer) |

## Revision round 9 (2026-10-15) {#rev-round-9}

Answers [[bsd-plan19-21-spec-diffcheck-r9-ebccb20]] for 21.1: #s9-2, #s9-4, #m9-1 to #m9-5, and
the 21.1 side of #s9-1. Edit-level; no decision. Code facts read at HEAD by symbol, then line:
`scan.py:1036-1054`, `cli.py:8995-9013`, `cli.py:12236-12244`, `stm.py:127`, `:201`, `:249`,
`:359`, `:387`, `telemetry.py:13`, `:96-118`, `:423`, `handoff.py:505-530`, `verbs.py:535-537`.

rel: derives-from -> [[bsd-plan19-21-spec-diffcheck-r9-ebccb20]]

| finding | answered at |
|---|---|
| r9 #s9-2 (a per-root `t` watermark over a liveness-filtered set loses an older live owner's rows; AC-4b (ix)'s order hid it) | D6 set (2) consumed by OWNER: `{root, consumed: [[pid, pid_start, t_max]]}`, rows above an entry's `t_max` still shown, entries pruned past the 24 h window with the read bounded by the same window; "Claimed under the lock"; AC-4b (ix) reordered (P3 live writes first; P3's older row printed once after it exits; pruning leg); mutations (the `t`-only watermark) |
| r9 #s9-4 (D9 records prose as `envelope-unreadable`; "fallback outside the envelope path" contradicts (xii)(c); prompt keys diverge) | D9 `read_hook_envelope(…, prose_ok=)` → `HookEnvelope(envelope, prose)` with `.prompt`; the prose fallback moved inside; callers' flags; `--stdin-json` keeps its `ClickException`; `stm.HOOK_PROMPT_KEYS` = scan's four keys, the behaviour change on each path recorded; bypass check extended; AC-4b (xiii) (brace prompt, `--stdin-json`, `{"text": …}`); mutations |
| r9 #m9-1 (`owner_alive`'s `None` conflates unowned and unavailable; `read_pid_pointer`'s private check; `_proc_info` unchecked) | D6 `liveness_available()` (once per run, D6 and D7); `owner_alive(…, start_token=)`; `read_pid_pointer` through `owner_alive`; D7; AC-4b (xii)(b) sets {`owner_alive`, `liveness_available`, `write_pid_pointer`, `record_pointer_error`} and {`_proc_start`, `owner_lookup`} for `_proc_info(`; mutations |
| r9 #m9-2 (the `_errors.` constant check fails at GREEN on docstrings and D6's required text) | D8 `stm.errors_log_path()`; the bypass check scoped to write operations, with a planted-fixture control; handoff takes the path from it ([[#files-to-modify]]); AC-4b (xii)(a); mutation |
| r9 #m9-3 (AC-4b (x)'s identity breaks once a halving drops an earlier truncation row) | D6 roll-up: `dropped`, `dropped_by_root`, `unseen_dropped` add the removed truncation rows' counts; `dropped` counts non-truncation rows, so the identity is "non-truncation rows + Σ `dropped` = rows appended" (no `+ T` term, which no reader could count once truncation rows are dropped); AC-4b (x) at three or more halvings, per-root identity too; (iii-b) wording; mutation |
| r9 #m9-4 (claim adoption by mtime adopts live claims; final-rename `FileNotFoundError` unhandled; `legacy-unreadable` not idempotent; (xi) blind) | D6 step 1 claim name `<pid>.<start_token>`, adoption only when `owner_alive(…) is False`, mtime rule withdrawn; final-rename loss counted `migrate-claim-lost`; `legacy-unreadable` `t` = the legacy file's mtime; AC-4b (xi) with a one-day-old legacy file, a live-claimant leg and the idempotent unreadable row; mutations |
| r9 #m9-5 (`skipped_budget` = "the degrade path" mislabels refused connections; `CALL_OUTCOMES` unguarded) | R4: classification by exception type in `classify_outcome(…, budgeted=True)`; `log_query.__exit__` validates against `CALL_OUTCOMES` (plus 21.3's `NUDGE_OUTCOMES` for `kind=nudge`) and rewrites an unknown value to `error` / `outcome-invalid`; AC-2b non-budget and validation legs; mutations; [[#files-to-modify]] |
| r9 sibling (found while answering #m9-5): `CALL_OUTCOMES` omitted the outcome values every `query.log` row already carries (`empty`, `consumer-closed`; bug-052, `telemetry.py:13`) | R4: the tuple is the existing four plus `skipped_budget`, and the one classifier is the existing `classify_outcome`, extended, not a second one |
| r9 #s9-1 (21.1 side) | R9 `PrePromptState.topic_match` and `pre.json`'s `topic_match` (`{}` until 19.6), the carrier of 19.6 R9's assignment ([[task-19.6-phased-context-and-topic-cache#rev-round-9]]) |
| user rule: converge repeated shapes into one function, each with a bypass check that can fail | `liveness_available`, `errors_log_path`, `HOOK_PROMPT_KEYS`, `read_hook_envelope(prose_ok=)`, `classify_outcome(budgeted=)`; each AST check in (xii) is also run on a planted fixture it must report; `log_query` validates at write time |

## Revision round 10 (2026-10-15) {#rev-round-10}

Answers [[bsd-plan19-21-spec-diffcheck-r10-f6400aa]] for 21.1: #s10-2, #m10-2, #m10-3, the 21.1
side of #m10-4 and #m10-1, and the 21.1 part of #m10-5. Edit-level; no decision. Code facts read
at HEAD: `cli.py:12224-12245` (the two degrade routes), `cli.py:11225-11237`
(`_memory_daemon_call` calls `daemon.call` directly), `verbs.py:194-221` (`require_daemon`,
`_call`), `discovery.py:152-226` (`_read_pid` of `rmxd.pid`, `pid_is_rmx`, `daemon_status`),
`daemon.py:571-596` (`ping`), `:640-671` (`call` re-raises `JSONDecodeError` after its retries).

rel: derives-from -> [[bsd-plan19-21-spec-diffcheck-r10-f6400aa]]

| finding | answered at |
|---|---|
| r10 #s10-2 (neither AC-2b leg reached the code it claimed; both stopped at `require_daemon`, whose result rode an unstated pid file; an accept-and-close peer raises `JSONDecodeError`, outside the degrade tuple) | R4: the two degrade routes named (`require_daemon`'s busy `VerbBusyError` = the budget skip; the recall op's transport `OSError` = `error`); `json.JSONDecodeError` joins the tuple, classified `error`; `verbs._call` wraps every transport error as `VerbBusyError`, so the verb route is classified `budgeted=False`; AC-2b busy precondition (pid file naming a live helper with "rmx" in its argv; `busy is True` asserted first), non-budget leg (one `{"ok": true}` ping, then a refused connect), mid-answer leg; mutations; [[#files-to-modify]] (`cli.py`) |
| r10 #m10-2 (no allowed function could supply set (1)'s `P_start` or the claim's own start) | D6 `stm.proc_identity(pid) -> (pid, start) \| None`, the one start accessor, used by set (1), the migration claim name, D8's `owner_start` and `write_pid_pointer`; AC-4b (xii)(b) set = {`owner_alive`, `liveness_available`, `proc_identity`}; mutation; [[#files-to-modify]] |
| r10 #m10-3 (`unseen_dropped` rolled up counts the owner was already shown; a stale "total line count" sentence) | D6: a removed truncation row's `unseen_dropped[key]` is carried only when its `t` is above that owner's watermark; `dropped` restated as the accounting total; AC-4b (x) news leg; mutation |
| r10 #m10-4 (21.1 side: `log_query` named `NUDGE_OUTCOMES` before 21.3 exists) | R4: `telemetry.OUTCOMES_BY_KIND` defined here, empty; validation against `OUTCOMES_BY_KIND.get(kind, CALL_OUTCOMES)`; 21.3 R3 adds `"nudge"` ([[task-21.3-indexed-symbol-nudge#rev-round-10]]); [[#files-to-modify]] (`telemetry.py`) |
| r10 #m10-1 (21.1 side: `topic_match`'s type) | R9: `PrePromptState.topic_match: dict[str, str]`, keyed by `stm.cluster_cid(members)`; `pre.json`'s `{}` read by 19.6's `load_topic_cache` as the empty cache ([[task-19.6-phased-context-and-topic-cache#rev-round-10]]) |
| r10 #m10-5 (the `--stdin-json` row leg missing from (xiii)'s RED list) | AC-4b RED list: the `--stdin-json` leg's `envelope-unreadable` row is RED |
| user rule: converge repeated shapes into one function, with a bypass check that can fail | `proc_identity` (the one start accessor; (xii)(b)'s planted `_proc_start(` fixture still fails it); `OUTCOMES_BY_KIND` (the one outcome table, validated at write time) |

