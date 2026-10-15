---
gmd: "0.1"
id: bsd-plan19-21-spec-rereview-r7-331b414
title: "plan-19 + plan-21 spec re-review r7: every round-6 blocker closed; the Jaccard identity still merges small clusters on one hub member, and the user-level error log has no scope"
severity: SKETCHY
plan: plan-19-adaptive-memory-budget, plan-21-agent-context-usage
task: spec-rereview-19.0-19.6-21.1
round: 7
tags: [bsd, audit, spec-review, re-review, stm, session, bug-109, bug-112, snapshot, hooks, plan-19, plan-21]
---

# ch-bsd spec re-review r7 of plans 19 and 21 at `331b414` {#root}

**Commit reviewed:** `331b414` on `wave0-spec-reviews`. The plan-19/21 revision under review is
`9add65b` (7 files: 19.0, 19.3, 19.4, 19.6, 21.1, plan-19, plan-21). `src/` at `331b414` is the
same as at `3d3c798`, the sha the reviser read (`git diff 3d3c798 331b414 -- src/` is empty).
**Written:** 2026-10-15T00:29:17-0700.
**Method:** read-only.
- Every cited line in `src/refmatrix/{stm,cli,verbs,handoff,hooks,daemon,search,hub}.py` was
  checked at HEAD.
- I ran an AST scan of `src/refmatrix/` for calls of `latest_session`, `resolve_session_source`,
  `resolve_session`, `_resolve_stm_session` and `_stm`: 32 calls.
- I ran `rg` for `Stm(` and `session_id()`.
- I clustered COPIES of the 59 live `*.focus.json` files with dev `stm.cluster_focus`, in the
  scratchpad. No store or socket was opened.
- I read `.refmatrix/rmxd.log` around the 00:13 restart.
- Nothing was edited under plans, specs or `src/`.

rel: derives-from -> [[bsd-plan19-21-spec-rereview-r6-0e77da3]]
rel: specifies -> [[plan-19-adaptive-memory-budget]]
rel: specifies -> [[plan-21-agent-context-usage]]
rel: contradicts -> [[feedback_no_silent_failures]]
rel: contradicts -> [[feedback_go_no_go_ranges_not_predrop]]

## Round-6 findings: status {#prior-status}

| r6 id | status | evidence (spec text at `331b414`) |
|---|---|---|
| b-1 bug-109 read at r1 | **closed** | 21.1 R9 "Existing code this task extends (bug-109 as MERGED: r1 `320dc82` plus the r2-r4 remedies `0760fb7`, `9fe45fa`, `8cc9c71`, merged at `0c7d0e0`…)". It names `_proc_info` (`stm.py:127-165`), `_proc_start` (`:197-202`), `owner_lookup()` "`found`, `none`, `failed`" (`:236-279`), "`_ERRORS_MAX_BYTES = 256 * 1024` (`:291`) … rewrites the file IN PLACE", "**The log is already surfaced.** `handoff.session_pointer_anomalies` … (`handoff.py:508-529`)". D6: "D6 extends it, it adds no second reader … `session_pointer_anomalies(root)` passes `legacy_root=root`"; "**The watermark is keyed on `t`, not on a byte offset**"; the halving is kept and counted. D7: "`_proc_start(pid)` … the round-5 name `stm._process_table()` is WITHDRAWN". AC-4: "Every child in this AC runs with `CLAUDE_PID` = the test process's pid", plus a lookup-failed leg. AC-4b has (iii-b), (iv-b), (v) and (vi). `handoff.py` is in both Files tables. Every line cite above matches HEAD. |
| b-2 the 15 `prefer_latest` callers | **closed** | 19.0 R5: "`purpose` is a REQUIRED keyword of both, with no default". The table has one row per caller. My scan finds the same 15 `prefer_latest=True` sites (`cli.py:1103` … `:13260`) and 19 `_stm` / `_resolve_stm_session` calls, as AC-6e states. AC-6c adds "The other CLI writes" and "The hook entries". The mutation "`_resolve_stm_session` passing a hard-coded `purpose="read"`" is killed by AC-6c, traced: with no pointer, `summarize --promote` reads the newest ring and writes `focus_summary_<newest>`, and the AC asserts that no digest is written. |
| s-1 sweep bypasses the origin ladder | **closed**; three new MEH-level gaps in its mechanism ([[#m-2]], [[#m-3]]) | 19.0 R2 "Swept calls": the park stores `tool_use_id`, `transcript_path`, `tool_name` and the digest, and "the sweep runs THIS ladder on each swept call with `t_pre` = the park's `t`". "A long call is no longer recorded twice": a `swept` list, `late: true`, ring-only. AC-4g has a non-vacuous parent control, and AC-4h checks the weights. Both are traced to `stm.py:574-618` and `cli.py:2013`. |
| s-2 snapshot writers and identity | **writer part closed; identity part partial** ([[#s-1]]) | R3: "**One writer, one home** … written only by the input hook … the ONLY home of R9's collapsed snapshots". `derive_snapshots(graph, cache)` is pure and is called by `snapshot_pre_prompt`, and in memory by the live path. AC-3c asserts the composite BYTES on two fixtures. Identity: "the highest Jaccard … provided it is ≥ `j_return` (0.20…)". The residual is stated, and R1 records the one-member share. |
| s-3 in-daemon render reads the stale replica | **closed** | 19.3 R5: "**Inside the daemon … they come from the WRITER store, in the same op**", "no in-daemon render path calls `search.cached_replica`, `Store(…, read_only=True)` or `d._open_read_store`". 19.4 R2/R3 point at `_run_ingest_gmd_body` (`daemon.py:3450`) and at the `with` block at `:5191`. AC-1/2/3 run under `RMX_SNAPSHOT_DEBOUNCE_MS=60000`. I traced why that kills the mutant: the startup snapshot exists before any test write (`daemon.py:1788-1795`); the ingest body only calls the debounced `_request_snapshot` (`:3506`, `:3528`); and the tick sleeps `debounce_s` before copying (`:2734`). So the replica and the mirror stay older than the write for the whole AC. |
| m-1 stale cites | **closed except one** ([[#m-4]] (c)) | Cites re-read at `3d3c798`. 22 stm/cli/verbs lines checked exactly. One Files-table cite is left: `cli.py:1923-1927`. |
| m-2 21.1 → 19.1 edge | **closed** | 21.1 line 34: `rel: related-to -> [[task-19.1-pack-recall-under-budget]]`. The plan-21 `#dependencies` text says "19.1 must merge AFTER it". The plan-19 19.1 row has its "parallel bullets" clause replaced. |

**Totals:** 7 r6 ids. 5 are closed, 1 is closed with a one-line residual (m-1), and 1 is partial
(s-2).

### Deviation 1: the Stop and PreCompact entries exit 1, not 2 {#deviation-exit-code}

**The deviation is right.**
- **Exit 2 would block the stop.** Claude Code's documented exit-code semantics: on `Stop`, exit 2
  BLOCKS the stop and feeds stderr to the model. The hook would fire again at the next stop.
  Nothing reads `stop_hook_active`, so an unresolved session would keep the turn alive and turn a
  memory-path failure into an instruction to the model.
- **Exit 1 is a non-blocking error.** The model never sees it, and the turn ends.
- **PreCompact.** Exit 2 is not documented as blocking there. Either code is safe, and exit 1
  keeps the two entries alike.
- **Exit 1 is already this entry's convention.** Every existing failure of
  `focus summarize --promote` is a `ClickException`, which exits 1: "daemon busy", "daemon not
  running", "promote not confirmed" (`cli.py:1313-1356`).
- **Stderr is not discarded.** The Stop command has no `2>/dev/null || true` (`hooks.py:202`;
  "Memory path → foreground, loud").

**Visibility is weak on its own.**
- A non-blocking hook error reaches the USER as a hook-error notice; the full stderr appears only
  in the verbose / transcript view.
- The durable channel is the resolver's `pointer-unresolved` row. Under a hook, `CLAUDE_PID` is
  set and the owner is found, so the row is written, and recall-state and the SessionStart
  surfacing report it.
- No AC asserts that row for a `write` purpose, so the deviation's visibility claim is
  unpinned: [[#s-4]].

### Deviation 2: Jaccard ≥ `j_return` in place of a scan hub rule {#deviation-jaccard}

**The reviser's search was right.** `scan.py` has no member-exclusion hub rule. Its hub handling
(`scan.py:259-270`) only damps concept centrality, so my round-6 alternative pointed at
something that does not exist. Jaccard is a sound replacement for the round-5 "≥ 1 shared
member" rule on large clusters.

**It does not close the defect for the clusters this repo actually has: [[#s-1]].**
- The residual it states is the common case. Measured on copies of all 59 live focus graphs
  (`focus_graph(top=30)`, then `cluster_focus`):
  - 238 clusters. 78 have 2 members, 33 have 3, and 111 of 238 (47%) have ≤ 3.
  - In 163 of 493 same-graph cluster pairs (33%), the two sizes sum to ≤ 6. For those pairs, one
    shared member gives Jaccard ≥ 0.20.
  - A 2-member snapshot {hub, a} represents a 2-member live {hub, b} (J = 1/3).
- The residual's own bound is misstated. "Member sets total ≤ 5" is exact only if "total" means
  the union. The condition is |A| + |B| ≤ 6, and AC-7i's own boundary pair, {a,b,c} with
  {a,d,e}, is a 3 + 3 pair.
- R1 records the share, but no band says what happens if it is high.

### bug-109 code claims, verified at HEAD {#code-claims}

All verified:
- `owner_lookup` returns `failed` / `none` / `found`. Its `ps` fallback runs when the kernel
  chain has fewer than 2 entries.
- `_proc_start` is `_proc_info(...)[2]`.
- `handoff.session_pointer_anomalies` is at `:508-529` and is called at `:569`. Its tests
  `test_recall_state_surfaces_pointer_errors` (`tests/test_mcp_session_pointer.py:312`) and
  `test_the_anomaly_reads_only_the_window` (`:418`) exist.
- The `_ERRORS_MAX_BYTES` in-place halving is at `stm.py:308-310`.
- The 15 `prefer_latest=True` callers match.
- `_op_memory_compile_apply` is at `daemon.py:5180`, with its `with d._store_lock,
  d._st().with_partition(...)` at `:5191`; it is registered at `:6251`.
- `_run_ingest_gmd_body` is at `:3450`, run by `_op_ingest_gmd` (`:3566`) and
  `_op_ingest_gmd_start` (`:3585`).
- `RMX_SNAPSHOT_DEBOUNCE_MS`: the tick waits on the event, then `stop.wait(debounce_s)`, then
  `_snapshot_catalog(force=True)`. A value ≤ 0 disables the tick.

### Live note: does hook work reach the daemon's cli pool? {#hook-daemon-cost}

`rmxd.log` shows the restart at 00:13:18: "pool drain disp: timed out after 10s, 3 of 20 workers
still running (in flight: stats, stats, stats)", then `pools cli=4 bg=12 disp=20`.

**What the specs add to the hooks that reach the daemon: nothing.**
- 21.1 R3 writes rows "on the CALLER side … never inside a daemon op and never under the daemon's
  writer lock". R8 appends events the same way.
- 19.0 adds only file work to the input, PostToolUse, SessionStart and Stop hooks: the
  snapshot, the sweep ladder, transcript tails and the pointer and log files.
- The Stop and PreCompact promote is an existing daemon write, bounded by `--timeout 5` / `30`
  with `retries=0` (`cli.py:1321-1328`). `--envelope-stdin` adds no call.
- 19.4 R2's bridge render reads the writer store under `_store_lock` in the bg pool, only after a
  batch that changed memory files.

**What is unbounded or unasserted:** the sweep's total read per prompt, and the claim "zero new
daemon calls", which no AC asserts: [[#m-1]].

## Findings {#findings}

### SKETCHY s-1: 19.6's Jaccard identity still merges a new topic into an old line through one hub member whenever the two clusters are small, and in this repo half of them are {#s-1}

**File:** `task-19.6-phased-context-and-topic-cache.md` R9 "Which live cluster a snapshot stands
for", R1, AC-7i, the mutation list.

**What:**
- **The rule:** "the snapshot with the highest Jaccard … provided it is ≥ `j_return` (0.20)".
- **The residual is the common case, not an edge.** Measured above: 47% of live clusters have
  ≤ 3 members, and in 33% of pairs one shared member reaches 0.20. So r6 #s-2's defect, a hub ref
  (`cli.py`, `daemon.py`) hiding a new topic behind an old frozen line, survives for the clusters
  that dominate the data.
- **The bound is misstated.** "Total ≤ 5" should read |A| + |B| ≤ 6 (union ≤ 5).
- **R1's new figure has no decision attached.** "These are recorded figures; Table A's bands and
  verdicts are unchanged".
- **The threshold is reused without being confirmed for this use.** d9v CONFIRMED `j_return` as
  the PROMPT-TERMS-vs-CACHED-CLUSTER return threshold. Reusing it for MEMBER-SET identity is a
  new use, but the revision table says "no band or threshold changes".
- **One mutation can survive.** The mutation "threshold moved off `j_return` by one step either
  way" survives a move down to anything in (1/6, 0.20), for example 0.18, because AC-7i has no
  pair with J in that interval.

**Why it's sketchy:** the mechanism is right in shape, but its stated residual is the majority
case. An unbanded "measured in R1" is a measurement with no go/no-go attached.

**Fix (needs the user, see [[#user-decisions]]):**
- **(a) Recommended.** Identity requires ≥ 2 shared members AND Jaccard ≥ `j_return`. One
  shared member never establishes identity, and no new number is needed.
  - AC-7i gains a leg: {hub, a} vs {hub, b} gets its own line.
  - The 3 + 3 boundary pair flips to its own line. Keep a represented case at 2 shared members,
    {a,b,c} vs {a,b,d} (J = 0.5).
- **(b) Alternative.** Keep Jaccard only, and pre-register an action band for R1's one-member
  share (for example: > 10% of represented clusters means adopt (a)).
- **Either way:**
  - correct the residual text;
  - add an AC-7i pair at J = 2/11 (for example {a,b,c,d,e,f,g} vs {a,b,h,i,j,k}) so a lowered
    threshold flips it;
  - record the user's acknowledgement of `j_return`'s second use beside d9v.

**Pattern match:** YES ([[feedback_go_no_go_ranges_not_predrop]]; r6 #s-2's "measures the rule,
not the clustering").

### SKETCHY s-2: D3/D6/D8 make `_errors.jsonl` and its watermark user-level, but nothing scopes them: recall-state reports other projects' rows, and the SessionStart surfacing goes to whichever session starts first {#s-2}

**File:** `task-21.1-context-usage-telemetry.md` R9 D3, D6, D8; `task-19.0` R5 deferred items and
Files (`handoff.py` row).

**What:**
- **One file for every project.** D3 moves the log to `<hub.global_store_root()>/by-pid/`. D8
  sends every STM hook failure there from every project: `sweep-failed`, `composite-failed`,
  `enrichment-unresolved`. "A store-scoped row carries `root=` as a field."
- **Nothing filters on it.** D6's `read_pointer_errors` drops its `root` argument and reads the
  whole file. `session_pointer_anomalies(root)` filters nothing. So `rmx recall-state` in project
  X counts project Y's rows.
- **One watermark for every session.** `by-pid/_errors.seen` is a single file, so the first
  SessionStart in ANY project surfaces, and consumes, rows that belong to another session. The
  owning session never sees them on that surface.
- **The existing message becomes false.** recall-state says "STM calls may have used a guessed
  session" (`handoff.py:525-526`). Under D6/D8 the count also includes `errors-truncated`,
  `sweep-failed`, `composite-failed` and `enrichment-unresolved`, which are not guesses.

**Why it's sketchy:** this is a memory-path report. Moving its file to a shared location without
moving its scope turns "surfaced to the right session" into "surfaced to some session". From
the owner's side that is silent. The defect dates from round 5's D3; the round-6 r6 report missed
it, and round 6's D6 rewrite (a single `t` watermark) builds on it.

**Fix:**
- `read_pointer_errors(*, root=None, owner=None, since=…)`: a row carrying `root` counts only for
  that root; a process row (`no-owner`, `pointer-unresolved`, `pointer-stale`…) counts for the
  owner pid it names.
- The watermark is per owner (`_errors.seen.<pid>`, pruned with D7).
- `session_pointer_anomalies` prints pointer failures and STM hook failures as two counts, with
  the "guessed session" text only on the first.
- New AC-4b leg: two sandbox roots, a row for each, and each recall-state reports only its own.
  Two owners: each SessionStart surfaces only its own rows.

**Pattern match:** YES ([[bsd-impressions#imp-log-on-read-is-a-write]] family: a sink's location
decides who it reports to).

### SKETCHY s-3: two new "for one release" legacy reads with no task that removes them {#s-3}

**File:**
- 21.1 R9 D3: "Migration, one release: `read_pid_pointer` falls back to bug-109's
  `<root>/stm/by-pid/<pid>.json`".
- 21.1 R9 D6: "for one release, bug-109's `<root>/stm/by-pid/_errors.jsonl`".
- The 19.0 and 21.1 Files rows.

**What:**
- Both are new deferral text in this diff (rule 9: version hedge).
- Neither names a task or plan that removes the legacy path.
- No task spec under `plan-19-…-tasks/` or `plan-21-…-tasks/` has an acceptance criterion for
  that removal (searched for "legacy" and "one release").
- Built as written, two `legacy_root=` read paths stay in `src/` with no owner.

**Why it's sketchy:** rule 9a, an unanchored deferral. It is SKETCHY rather than BULLSHIT
because it is new in this diff (first occurrence) and it is a spec, not code.

**Fix (no window, cheaper than a removal task):**
- The SessionStart writer (D4) migrates its own root ONCE: it appends the legacy rows to the new
  log with their original `t` and renames the legacy file to `_errors.migrated.jsonl`.
- Legacy pointers are dropped, not read. A pointer is a cache (D7's own words), and the next
  input hook rewrites it.
- After that, no legacy read path exists.
- AC-4b (ii) / (vi) become migration legs.
- Alternative: file a concrete removal task spec with acceptance criteria and point both
  sentences at it.

**Pattern match:** YES (deferral rule 9; first occurrence in plans 19/21).

### SKETCHY s-4: a `write`-purpose miss is never pinned to its row, and that row is the only durable channel the exit-1 Stop path has {#s-4}

**File:** 19.0 R5 table (the Stop/PreCompact row: "the resolver's own row records the miss"),
AC-6c, the mutations; 21.1 R9 "In all three, a miss is recorded exactly as bug-109 records it".

**What:**
- **AC-6c's hook leg** asserts "exit 1 (not 2) and write no digest". It does not assert the
  stderr line or the `pointer-unresolved` row.
- **AC-6c's CLI legs** assert exit 2 "naming the sources tried", with no row.
- **21.1 AC-4** pins the row for `purpose="event"` only.
- **So two mutants survive every AC:**
  - the resolver records only for `event` / `read`;
  - `--envelope-stdin` exits 1 with no stderr and no row.
- **The row's presence also depends on the runner.** AC-6c does not set `CLAUDE_PID`, and in a
  plain terminal bug-109 records nothing. 21.1 AC-4 fixed this for itself in round 6; 19.0 AC-6c
  did not.
- **Why it matters:** per [[#deviation-exit-code]], a non-blocking hook error is a weak channel.
  The row is what makes the exit-1 path not silent.

**Fix:**
- Run AC-6c with `CLAUDE_PID` = the test pid, as 21.1 AC-4 does.
- Assert, for the hook leg and for one CLI write leg: exactly one `pointer-unresolved` row with
  `owner` = the test pid; one stderr line naming the sources; and the row visible in
  `compose_recall_state`.
- Add both mutants to the list.

**Pattern match:** YES ([[bsd-impressions#imp-unknown-is-not-absent]]; r6 b-1's "plain terminal
records nothing").

### MEH m-1: the input hook's new file work has no aggregate bound, and "no new daemon calls from hooks" is true but asserted nowhere {#m-1}

**What:**
- Each swept call's search is capped at 1 MB, and the sidecar holds up to `INFLIGHT_BUDGET` = 64
  calls (`stm.py:45`). So one UserPromptSubmit can read and parse 64 MB synchronously before the
  prompt proceeds.
- "Inside the hook's latency budget" names no budget.
- After the 00:13-00:17 cli-pool stall, the claim that these hooks never touch the daemon is the
  one worth pinning.

**Fix:**
- A per-sweep total cap (for example 4 MB). Calls past it are swept `unattributed`, counted.
- An AC, using 23.0's connect guard, that the `input`, `tool`, `tool-pre` and `session-start`
  hook runs open 0 daemon sockets.

### MEH m-2: the `swept` key list "in the sidecar" breaks both iterators of the sidecar's dict of records {#m-2}

**What:**
- `inflight_sweep` runs `v.get("t")` on every value (`stm.py:604-605`), and `inflight_begin`'s
  eviction runs `d[k].get("t", 0)` (`:579-580`).
- A list stored under a key in the same dict raises `AttributeError`. Every later sweep then
  fails: loudly, as `sweep-failed`, but it stops sweeping.
- AC-4h never runs a second park or sweep after the list exists.

**Fix:**
- Name the layout: `<session>.swept.json`, or a reserved key that both iterators skip.
- AC-4h: park and sweep a second call after the late completion.

### MEH m-3: AC-4/4e/4g fixture timestamps sit below any live `t_lo` {#m-3}

**What:**
- The subagent fixture's `tool_use` entries carry 2026-10-14 timestamps.
- The cost bound reads backward only "to the first entry older than `t_lo`" (`t_lo = t_pre −
  5 s`, park time = now). So the scan stops at the transcript's last line, and the id is never
  found unless it is on that line.
- The easy way to green the test is to widen or drop the bound. That is the cheap fix this ladder
  forbids.

**Fix:** the fixture build script, or the test, rebases entry timestamps and file mtimes onto
the replay clock. State this in R6 and AC-4g.

### MEH m-4: small text defects {#m-4}

- (a) **AC-4b (iii-b) cannot pass as written.** It asks for "exactly the rows newer than the
  watermark (none twice, none skipped)" after a halving that deletes some of those rows. Rewrite:
  the surviving rows with `t` > watermark, each once, plus `errors-truncated` whose `dropped`
  equals the removed line count; surfaced + dropped = rows written since the watermark.
- (b) **`rmx focus show` takes a required `LINE`** (`cli.py:1210`). The origin counts (19.0
  R2) and the pointer-error line (21.1 D6) appear only while viewing one event. Name a surface
  that needs no argument (`focus topics`), or add `focus show --stats`.
- (c) **One stale cite.** The 19.0 Files row says `cli.py:1923-1927`; it is `:1926-1930`
  (HEAD), as 19.0 R1 already says.
- (d) **`Stm.__init__` is an unlisted resolver tail.** `self.session = session or session_id()`
  (`stm.py:447`) sends `RMX_SESSION`, else `default`. The `event` tail returns `None` into
  `Stm(root, session=…)` at `scan.py:540` and `composite.py:106`. AC-6's fixture has no
  `default` ring (the live store has one, `stm/default.jsonl`), so a mutant that passes `None` but
  records its row survives. `hub._op_focus` (`hub.py:565`) uses `or "default"` too (a UI read).
  Fix: seed a `default` ring with distinct terms in AC-6, and make the AST check list `Stm(`
  calls whose session can be `None`.

## Verdict {#verdict}

**8 findings (0 BULLSHIT, 4 SKETCHY, 4 MEH). DIRTY.** This is the first round of plans 19/21
with no BULLSHIT.

- **plan-21: approvable after one small edit pass.**
  - 21.1 D3/D6/D8: [[#s-2]] (scope the log and watermark) and [[#s-3]] (one-shot migration).
  - [[#s-4]]'s 21.1 half: the `write`-purpose row.
  - The MEHs can ride as named fixes: [[#m-4]] (a).
  - No user decision is needed for plan-21.
- **plan-19: approvable after the same 19.0 edits, plus a user decision on 19.6 identity.**
  - [[#s-1]] needs the decision.
  - [[#s-4]] covers AC-6c.
  - [[#m-1]]-[[#m-4]] are small.
- Both deviations are acceptable as revised:
  - exit 1 is correct for Claude Code's Stop semantics, and its visibility needs [[#s-4]];
  - Jaccard is the right shape, but it needs [[#s-1]] (a) or (b).

Neither plan needs another full re-review round. A diff check of the edits against this report
is enough.

### Needs a user decision {#user-decisions}

1. **19.6 snapshot identity ([[#s-1]]):**
   - (a) ≥ 2 shared members AND J ≥ `j_return`. Recommended; no new number.
   - (b) Jaccard only, plus a pre-registered action band on R1's one-member share.
   - (c) Accept the residual as measured: 47% of clusters ≤ 3 members, 33% of pairs exposed.
   - With any option, acknowledge that `j_return` (d9v) is now also the identity threshold.
2. Optional: one-shot migration (recommended) vs a scheduled removal task for the two legacy reads
   ([[#s-3]]).

## Ledger entries {#ledger}

Appended (never rewritten) to `INDEX.md`, `last_run.log` and `IMPRESSIONS.md`.
