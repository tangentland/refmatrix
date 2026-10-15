---
gmd: "0.1"
id: bsd-plan19-21-spec-rereview-r6-0e77da3
title: "plan-19 + plan-21 spec re-review r6: the specs extend bug-109 as it stood at r1, not as merged, and the Stop hook's per-turn durable promote is still unrouted"
severity: BULLSHIT
plan: plan-19-adaptive-memory-budget, plan-21-agent-context-usage
task: spec-rereview-19.0-19.6-21.1-21.4
round: 6
tags: [bsd, audit, spec-review, re-review, stm, session, bug-109, bug-112, snapshot, plan-19, plan-21]
---

# ch-bsd spec re-review r6 of plans 19 and 21 at `0e77da3` {#root}

**Commit reviewed:** `0e77da3` on `wave0-spec-reviews`. This is the round-5 revision `d454bf9`
plus `734dc5f` (the wave list), plus master's 0.78.0 (bug-109, bug-105) and 0.78.1 (bug-110,
bug-111) merged in. No plan-19 or plan-21 file changed after `d454bf9`.
**Written:** 2026-10-14T23:50-0700.
**Method:** read-only. I read every revised spec and checked each code citation against `src/`
at `0e77da3`. I ran an AST scan of `src/refmatrix/` for calls to `latest_session`,
`resolve_session`, `resolve_session_source`, `session_id`, `_resolve_stm_session` and `_stm`. I
checked the bug-109 history with `git log 320dc82..master`. GMD lint on the 13 spec files:
0 errors. No `src/`, spec, store or registry file was touched.

rel: derives-from -> [[bsd-plan19-21-spec-rereview-r4-878647c]]
rel: specifies -> [[plan-19-adaptive-memory-budget]]
rel: specifies -> [[plan-21-agent-context-usage]]
rel: contradicts -> [[feedback_no_silent_failures]]
rel: contradicts -> [[feedback_check_the_sibling_condition]]

## Round-4 findings: status {#prior-status}

| r4 id | status | evidence (spec text at `0e77da3`) |
|---|---|---|
| b-1 snapshot after the sweep | **closed** | 21.1 R9: "Writer: the input hook's FIRST state access, not `Stm.record`": 1. pointer write, 2. "`s.snapshot_pre_prompt(prompt)` for EVERY non-empty prompt, ambient included", 3. `s.inflight_sweep()`, 4. `record("input")`. It also says "The round-3 sentence … is WITHDRAWN". AC-8b seeds "one call parked 120 s ago", adds ordering (iv), an ambient leg and a non-vacuous pre-check; there are mutations for "snapshot taken inside `record("input")`, after the sweep" and "skipped for ambient". 19.0 R7 and AC-6d say the same, and so do 19.6 R2 and AC-3c. |
| b-2 three unrouted `latest_session` callers | **closed for the three named**; a second-level sibling is open ([[#b-2]]) | 19.0 R5 caller table has rows for `composite.build_topic_composite` ("`session=` and `graph=pre_prompt_state(…).graph`"), `helix._current_session`, and `promote_focus_edges` ("`session` becomes a REQUIRED argument"). AC-6e: "the list must equal exactly one site, the `read` tail". My AST scan agrees: the only `latest_session` calls are `composite.py:103`, `helix.py:96`, `promote.py:161`, `scan.py:537` and `verbs.py:566`. |
| s-1 bug-109 owns the pointer | **partial; reopened as BULLSHIT** ([[#b-1]]) | The order, the pointer format `{session, pid, pid_start, t}` and "extend, never rebuild" are adopted. But "Existing code this task extends (bug-109, read at `320dc82`)" is bug-109 r1. Three later remedy rounds changed the parts the deltas build on. |
| s-2 `ts` zone | **closed** | 21.1 R10: "**`ts` is UTC** … `YYYY-MM-DDTHH:MM:SS.mmmZ`". R5 class 0 marks any other form `malformed`. AC-7 event (g) covers it. 19.2 R1: "`day` is `ts[:10]` … no zone conversion runs at fold time". AC-6 replays under `TZ=UTC` and `TZ=America/Los_Angeles`, with a DST pre-check. |
| s-3 collapsed line vs unstable members | **closed as asked**; round 5's mechanism has new defects ([[#s-2]]) | R9: "A collapsed line renders a FROZEN SNAPSHOT". "Re-collapse … gets a NEW snapshot". R5 splits the composite into "TWO blocks" (`stm-topic-expanded` / `stm-topic-collapsed`). R1 records member-set persistence. AC-7d has the "DECAY-ONLY turn"; AC-7d2 and AC-7h are added. |
| m-1 `S` interval, subagent appends, lock | **closed** | 21.1 R9: "`S` = max(2 s, 3 × the largest measured `\|wall − t0\|`)". `events_n` counts "`origin` is `parent` or absent". The known limit is stated: "`focus.json` is read-modify-written without a lock". |
| m-2 read tail is a `latest_session` consult | **closed** | 21.1 R9: "`read`: the newest ring … This is the ONE allowed `latest_session` call in `src/`". 19.0 AC-6e enforces it. |
| m-3 small gaps | **closed**; residual edges are [[#m-2]] | 19.6 Files: "the marker dispatch inside `--event session-start` when `source=compact`". `734dc5f` wave list: "21.1 (…) → 19.1". 19.6 status lines read CONFIRMED. |

**Totals:** 8 r4 ids. 6 closed, 1 closed for its named scope with a sibling now open (b-2), and
1 partial and reopened (s-1).

### The two requested checks {#requested-checks}

- **19.6 status lines say CONFIRMED (d9v): yes.**
  - Header (line 20): "The user CONFIRMED [[task-19.6-phased-context-and-topic-cache#ranges]] as written (d9v …)".
  - R0 (line 49): "**R0 Pre-registration, CONFIRMED (d9v).**".
  - `#ranges` heading (line 213) and status (line 215): "**Status: CONFIRMED (d9v).**".
  - R9 cap (line 187): "`C = 6` (CONFIRMED with the other numbers, d9v)".
  - The remaining PROPOSED strings (lines 442, 454, 464) are inside the round-1 to round-3
    revision tables, which are history.
  - plan-19 `#decisions` d9v, item 5 of `#open-after-revision`, and the `#tasks` row all agree.
- **Is the 21.1 → 19.1 dependency a real `rel:` edge in both specs? Only in 19.1.**
  - `task-19.1` line 25 has `rel: depends-on -> [[task-21.1-context-usage-telemetry]]`.
  - `task-21.1` has no `rel:` line naming 19.1. It names 19.1 only in R11's prose.
  - At plan level, `plan-19` has `rel: depends-on -> [[plan-21-agent-context-usage]]`.
  - The decision log states the edge (`734dc5f`).
  - The prose around it is stale: see [[#m-2]].

### bug-112: does any 19/21 spec read the snapshot in process? {#bug112-check}

- **Not affected.** These read files, not the DuckDB snapshot:
  - `pre_prompt_state` reads `<session>.pre.json`;
  - 21.1's `delivered_in_session` reads `recall-events.jsonl`;
  - 19.2's fold reads the events log.
- **Not affected.** 21.2 R7 and 21.4 R2 read "a catalog COPY taken from the replica reader file".
  That file is static and nothing in the process replaces it.
- **Latent, too narrow for a finding.** In 21.1 R12, the `used` emission on `memory get`'s replica
  fall-through can open the snapshot a second time in one short CLI process. That is bug-112's
  shape, but the replacement window is milliseconds.
- **Affected: 19.3 R5 and 19.4 R2-R3.** Inside the daemon, the index render "reads the replica
  directly" right after the daemon's own write. See [[#s-3]].

## Findings {#findings}

### BULLSHIT b-1: both specs extend bug-109 as it was at r1 (`320dc82`), not as merged in 0.78.0; implemented as written, D3/D8 silence recall-state's pointer-error report {#b-1}

**Where:**
- 21.1 R9 "Existing code this task extends" and deltas D3, D5-D8; AC-4, AC-4b; Files.
- 19.0 R0 ("which branch of bug-109's `owner_claude_pid()`") and R5 "Existing code", plus
  "bug-109's deferred items" ("nothing surfaces `_errors.jsonl`").

**What:** `git log 320dc82..master` shows three bug-109 remedy rounds after the sha the specs
read: `0760fb7` (r2), `9fe45fa` (r3) and `8cc9c71` (r4). All are merged (`0c7d0e0`). What
`src/` does at `0e77da3`:

1. **Process lookup.**
   - Merged code: `stm._proc_info` reads the kernel through libproc `proc_pidinfo` and
     `proc_pidpath` (`stm.py:126-165`). `owner_lookup()` returns `(pid, found|none|failed)`
     (`:236-279`). Claude is recognised by executable path (`_is_claude`). `ps` is used only as
     an argv[0] fallback.
   - 21.1 R9 says `read_pid_pointer` compares against "`ps -o lstart=`", and `owner_claude_pid`
     builds its chain from "ONE `ps -A -o pid=,ppid=,comm=` call".
   - 19.0 R0 gives the owner lookup two branches. The merged code has three.
2. **Error reasons and when they are written.**
   - The merged code writes `owner-lookup-failed` (`cli.py:1987`, `verbs.py:562`). The specs'
     list is `no-owner`, `ps-failed`, `write-failed`, `pointer-unresolved`.
   - A miss in a plain terminal records nothing (`verbs.py:558-565`).
   - So 21.1 AC-4 ("`_errors.jsonl` gains one `pointer-unresolved` row") passes or fails
     depending on whether the test process happens to run under a Claude ancestor.
3. **`_errors.jsonl` is already surfaced.**
   - `handoff.session_pointer_anomalies` (`handoff.py:508`) reads it, and `compose_recall_state`
     calls it at `:569`, so `rmx recall-state` reports pointer failures.
   - 19.0 R5 says "nothing surfaces `_errors.jsonl`" and 21.1 D6 says bug-109 "left it unread".
     Both are false at HEAD.
   - D3 and D8 move the pointers and `_errors.jsonl` to `~/.refmatrix/by-pid/`, and "nothing
     writes the old location". No spec lists `handoff.py`.
   - Built as written, recall-state keeps reading `<root>/stm/by-pid/_errors.jsonl`, which never
     gains another row. The one existing report of guessed sessions goes quiet with no error.
     That is a silent failure on a memory path.
4. **The watermark conflicts with the existing size bound.**
   - `record_pointer_error` bounds the file at 256 KiB by rewriting it IN PLACE with the oldest
     half dropped (`stm.py:291`, `:308-310`).
   - D6 adds a byte-offset watermark (`_errors.seen`) and "renames at 1 MB … nothing is
     deleted".
   - After an in-place halving, the stored offset points past or into the middle of the file:
     rows are skipped or surfaced twice. "Nothing is deleted" is false while the halving stays,
     and the halving would trigger before the 1 MB rename ever does.
5. **D7 calls a function that does not exist.** `stm._process_table()` is not in `src/` at HEAD.
   The merged code checks one pid at a time (`_proc_start`).

**Why it's bullshit:**
- This is r4 #s-1's defect one level down. The specs moved from "build it" to "extend it", then
  described a version of "it" three rounds old.
- It is the third sighting of [[bsd-impressions#imp-adopt-by-merge-not-sha]]: plan-23 r4, plan-19/21 r4, and
  now this. That escalates it to BULLSHIT.
- The header's own rule ("the dependency is the merge, not a sha") is broken by the body, which
  cites a sha.
- The merge has landed, so the deferred promise "every line number below is re-read after that
  merge" is now due.

**Fix:**
- Rewrite "Existing code" in 21.1 R9 and 19.0 R5 from `master`:
  - `_proc_info` / `owner_lookup` and their three statuses;
  - the reason `owner-lookup-failed`;
  - `read_pointer_errors` and `handoff.session_pointer_anomalies`;
  - `_ERRORS_MAX_BYTES` and its in-place halving.
- Update 19.0 R0's probe to name `owner_lookup`'s branches.
- D6 extends the recall-state reader rather than adding a second one:
  - `session_pointer_anomalies` reads `stm.pointer_dir()`, and the legacy location for one
    release;
  - add `src/refmatrix/handoff.py` to the Files tables of both specs;
  - remove "nothing surfaces" and "left it unread".
- D6 replaces the in-place halving with rename rotation BEFORE adding any watermark, or keys the
  watermark on `t` instead of a byte offset.
- D7 checks each pointer with `_proc_start(pid)`.
- AC-4 and AC-4b pin the owner: set `CLAUDE_PID` to an ancestor of the child. Add legs:
  - recall-state reports a row written at the new location;
  - the owner lookup fails, giving an `owner-lookup-failed` row.
- New mutation: recall-state left reading `<root>/stm/by-pid/`.

**Pattern match:** YES ([[bsd-impressions#imp-adopt-by-merge-not-sha]], r4 impression "a hotfix that lands
mid-review becomes the spec's baseline").

### BULLSHIT b-2: the Stop and PreCompact hooks' `focus summarize --promote`, a durable write every turn, and four more CLI write commands resolve through `_resolve_stm_session` with no purpose stated {#b-2}

**Where:** the 19.0 R5 caller table, row `cli._resolve_stm_session` ("its `prefer_latest=True`
path calls the resolver with the purpose its caller states"); AC-6c; AC-6e's second check;
mutations.

**What:**
- **Every `prefer_latest=True` caller goes through one helper.** The AST scan finds 13 callers of
  `_stm(prefer_latest=True)` / `_resolve_stm_session(prefer_latest=True)`. All reach
  `verbs.resolve_session` (`cli.py:1072`), which falls back to the newest ring. The table names
  only `focus record`, `focus clear` and `promote-edges`. The rest are writes with no row:
  - `rmx focus summarize --promote` (`cli.py:1297`) writes the `session/digest` memory. The
    generated Stop hook (`hooks.py:202`) and PreCompact hook (`:334`) run it with no
    `--session`, on every turn. It is the most frequent durable STM-to-LTM write in the product.
  - `focus detour` (`:1589`) and `focus return` (`:1614`) write focus marks.
  - `focus clear-subject` (`:1724`) writes subject state.
  - `focus rebuild` without `--dry-run` (`:1556`) rewrites `focus.json`.
- **AC-6e pushes the implementer toward the guess.** It "fails on [a `resolve_session_source`
  call] without a literal `purpose=` keyword". A helper that forwards its caller's purpose cannot
  pass a literal, so the easy way to pass is `purpose="read"` inside `_resolve_stm_session`. That
  sends all 13 callers, including the Stop hook's promote, down the newest-ring read tail.
- **Nothing pins these commands.** AC-6c covers `note`, `record`, `clear` and `promote-edges`
  only, and no mutation touches the others.

**Why it's bullshit:** this is the sibling-caller miss a fourth round running. r4 #b-2's own
fix said "the list comes from a scan of `src/` … for `resolve_session`", and the scan stopped
at the first level. The one helper the scan finds fans out to 13 commands. Five of them write,
and one is a durable LTM write in a generated hook. The spec's rule "no write reaches `default`
or the newest ring" does not hold for them.

**Fix:**
- Give one table row and one purpose to each of the 13 callers:
  - `write`: `summarize --promote`, `detour`, `return`, `clear-subject`, and `rebuild` without
    `--dry-run`;
  - `read`: `tail`, `context`, `show`, `topics`, `export`, `detours`, `subject`, `size`,
    `summarize` without `--promote`, and `recall-state`.
- `_resolve_stm_session(explicit, *, purpose)` takes `purpose` as a required parameter. AC-6e
  allow-lists exactly that one pass-through call site.
- The Stop and PreCompact summarize entries pass the session they already hold, by reading the
  envelope on stdin, as the focus hook does.
- AC-6c leg: with no pointer, `focus summarize --promote` exits 2 and writes no `session/digest`
  memory.
- Mutation: `_resolve_stm_session` with a hard-coded `purpose="read"`.

**Pattern match:** YES ([[bsd-impressions#imp-quoted-line-sibling]]; r4 "to retire a fallback, list its
callers with a scan").

### SKETCHY s-1: the sweep's `abandoned` events bypass 19.0 R2's origin ladder, so a background subagent's long or hung call re-enters the parent's focus {#s-1}

**Where:** 19.0 R2 ("Every PostToolUse event is given an `origin`"; "old events without
`origin` read as `parent`"), R7, AC-4, AC-6d.

**What:**
- **Swept events carry no origin.** `inflight_sweep` (`stm.py:596-617`) records each parked
  PreToolUse call older than 90 s as a `tool` event, with the refs it was parked with, into the
  ring AND the graph. Round 5 made the sweep the most-discussed writer, but R2's ladder runs only
  on PostToolUse. A swept event has no `origin`, so it reads as `parent`.
- **Subagent calls are swept too.** r4's evidence noted that a background subagent's calls park
  in the parent's sidecar. A subagent call that runs longer than 90 s, hangs, or is denied is
  swept into the PARENT's focus at the parent's next prompt. That is bug-103 again, through the
  sweep.
- **Long calls are double-recorded.** A call still RUNNING at the sweep is recorded as
  `abandoned`, and recorded again when its PostToolUse arrives (`inflight_end` finds nothing).
  This predates plan-19 and is not stated anywhere.

**Fix:**
- The park record stores `tool_use_id` and the envelope's `transcript_path`, and the sweep runs
  R2's ladder on it. Rung 2 by id works there, because the subagent transcript holds the
  `tool_use` block from issue time. Otherwise the sweep marks the event `origin: unattributed`.
- State the duplicate-record residual. Alternatively, have PostToolUse mark the swept record as
  completed instead of appending a second event.
- AC-4 leg: a subagent call parked 120 s ago is swept at the parent's next prompt, and none of
  its refs becomes a parent member or label.
- Mutation: the sweep records without an origin.

**Pattern match:** YES (r4 impression "check a 'first' claim against the CALLER"; this is the
same writer, reached from the origin side).

### SKETCHY s-2: 19.6's frozen collapsed snapshot has two writers and two homes, and its "≥ 1 shared member" identity rule collapses new topics into old lines {#s-2}

**Where:** 19.6 R3, R9 ("snapshotted the FIRST time it renders collapsed … stored in the
session's last-emitted state"; "Which live cluster a snapshot stands for"), R1, AC-3c, Files.

**What:**
- **The writer is contradicted.**
  - R3 says the cache file "is updated only by the input hook", and that a cache entry and R9's
    snapshot "are ONE record".
  - R9 creates the snapshot when the cluster first RENDERS collapsed. The render runs in
    scan-prompt (`composite.py`, per R9's own "Where the render lives"), which is a parallel
    reader.
  - So either scan-prompt also writes the cache, which makes R3 false and adds a second unlocked
    writer racing the input hook. Or snapshots live in "the session's last-emitted state", which
    is outside `pre_prompt_state`. That makes the composite's prompt-time read a second live
    read, which R2 forbids.
  - With an evicting prompt, the input hook's own snapshot then lands before or after the
    render depending on scheduling. AC-3c's "composite byte-identical across the four" can fail
    for a reason the spec does not name.
- **The identity rule degenerates on hub refs.**
  - "A non-selected live cluster that shares at least one member with an existing snapshot is
    represented by that snapshot."
  - Hub refs such as `src/refmatrix/cli.py` or `daemon.py` sit in most clusters of this repo. So
    once one snapshot holds a hub ref, every later cluster containing it is hidden behind that
    snapshot's old frozen label, and a new topic never gets its own line.
  - R1's "share of collapsed lines byte-identical" is then high by construction, and Table A's
    verdict on `stm-topic-collapsed` measures the rule, not the clustering. "No new threshold is
    introduced" is true only because the threshold is 1.

**Fix:**
- One writer: the input hook, which already has the prompt and the pre-prompt state.
  - Snapshots live in the topic cache, so `pre.json` carries them.
  - The render reads only `pre_prompt_state(…).topic_cache`.
  - Name the writer in R3, R9 and Files.
- Decide identity by Jaccard against a confirmed threshold (`j_return`), or ignore hub members
  using scan's existing hub rule.
- Add an AC: a new cluster that shares only a hub member with a snapshot gets its own line.
- R1 also records the share of live clusters represented by a snapshot they share exactly one
  member with.
- AC-3c's evicting-`return` fixture asserts the composite bytes.

**Pattern match:** NO (new mechanism from round 5).

### SKETCHY s-3: 19.3 R5 / 19.4 R2-R3, the in-daemon index render reads the replica right after the daemon's own write, which is stale by the snapshot tick and exposed to bug-112 {#s-3}

**Where:**
- 19.3 R5: "inside the daemon (19.4's paths) the render reads the replica directly";
- 19.4 R2 (the bridge regenerates `MEMORY.md`);
- 19.4 R3: "After a successful apply, the compile step regenerates `MEMORY.md` … so subject lines
  are never stale";
- 19.4 AC-1 to AC-3.

**What:**
- **The replica lags the write.** `catalog.read.duckdb` is written by the snapshot tick thread,
  debounced after a write op ("regenerated within ~250ms after each write op", `daemon.py:1782`;
  `_request_snapshot` → tick, `:808-812`). A render inside the compile or bridge op reads the
  catalog as it was BEFORE that op's apply, so R3's "never stale" is false by construction.
- **The spec does not name the reader, which leaves bug-112 open.** If the render is built on
  `search.cached_replica` or a bare `Store(root, read_only=True)`, those are the two openers
  bug-112 names (DuckDB's per-path instance cache). A second in-process opener after the
  snapshot is replaced can then be handed the old, unlinked database (bug_registry bug-112,
  open).
- **Inside the daemon the replica is the wrong source anyway.** The daemon IS the single writer.

**Fix:**
- 19.3 R5: inside the daemon, render from the writer store (`d.store` under `d._store_lock`) in
  the same op as the apply. Alternatively call `_snapshot_catalog(force=True)` and then
  `d._open_read_store(…)`.
- Never use `search.cached_replica` or a bare `Store(read_only=True)` on that path. Cite bug-112.
- 19.4 AC-2 / AC-3: the render in the SAME op as the apply names the new subject, with no sleep
  or retry.
- Mutation: render through `cached_replica` straight after the apply.

**Pattern match:** YES (r2 bug-110 impression "moving a read to a copy makes 'empty' cheap": a
snapshot read standing in for the writer).

### MEH m-1: code citations stale since the merge {#m-1}

- **Line numbers have moved.** 21.1 R9 "The pre-prompt state" ("read at HEAD, `cli.py:1946-1981`;
  sweep `:1976`; except `:1977-1978`; record `:1980-1981`") and 19.0 R7 (`cli.py:1971-1981`)
  predate the merge. At `0e77da3` the input branch is `cli.py:1974-2004`: the pointer write is
  `:1979-1993`, the sweep `:1998-2001`, and the record `:2003-2004`.
- **Wrong owner function.** The resolver calls `owner_lookup()`, not `owner_claude_pid()`
  (`verbs.py:545`).
- **Stale registry status.** The revision tables call bug-109's registry row "open". It is
  `fixed`.
- **Fix:** re-read the citations at `master` along with [[#b-1]].

### MEH m-2: the 21.1 → 19.1 edge is one-sided, and its prose is stale {#m-2}

- **21.1 has no edge to 19.1.** `task-21.1` carries no `rel:` to `task-19.1`.
- **plan-21 omits 19.1 as a consumer.** Its `#dependencies` 21.1 row says "the instrument 19.2,
  19.5 and 19.6 consume" and leaves out 19.1, the one task that must merge after it.
- **plan-19's wording is out of date.** The `#dependencies` 19.1 row (line 139) still says
  `#t10-waves` "lists as parallel bullets". That is false since `734dc5f`.
- **Fix:**
  - add `rel: related-to -> [[task-19.1-pack-recall-under-budget]]` (or a custom `precedes`) to
    21.1;
  - name 19.1 in plan-21's `#dependencies`;
  - delete the stale clause in plan-19.

## Verdict {#verdict}

**7 findings (2 BULLSHIT, 3 SKETCHY, 2 MEH). DIRTY.**

- **plan-19: NEEDS-REVISION.**
  - [[#b-1]] (19.0 R0/R5), [[#b-2]] (19.0 R5, AC-6c/6e), [[#s-1]] (19.0 R2), [[#s-2]] (19.6),
    [[#s-3]] (19.3/19.4), [[#m-1]], [[#m-2]].
- **plan-21: NEEDS-REVISION.**
  - [[#b-1]] (21.1 R9 D3/D6/D7, AC-4/4b), [[#m-1]], [[#m-2]].

The round-4 asks are answered: snapshot order, UTC `ts`, two composite blocks, the AST
allow-list, and d9v. What fails now is the same thing as before, one step out: the specs read
the code they had in mind, not the code on `master`. bug-109 was read at r1. The resolver's
callers were scanned one level deep. The sweep was ordered but never given an origin.

## Ledger entries {#ledger}

Appended to `INDEX.md`, `last_run.log` and `IMPRESSIONS.md` (append only; the file is over its
50-line target, and consolidation is left to a run that may rewrite it).
