---
gmd: "0.1"
id: bsd-plan19-21-spec-rereview-r4-878647c
title: "plan-19 + plan-21 spec re-review r4: the pre-prompt snapshot is taken after the input hook has already swept abandoned calls into the ring and graph, three latest_session callers were never routed, and bug-109 now owns the pointer the specs still plan to build"
severity: BULLSHIT
plan: plan-19-adaptive-memory-budget, plan-21-agent-context-usage
task: spec-rereview-19.0-19.6-21.1-21.4
round: 4
tags: [bsd, audit, spec-review, re-review, stm, session, snapshot, mcp, bug-109, recall-events, plan-19, plan-21]
---

# ch-bsd spec re-review r4 of plans 19 and 21 at `878647c` {#root}

**Commit reviewed:** `878647c` on branch `wave0-spec-reviews` (the round-3 revision is `a820b22`).
**Written:** 2026-10-14T14:08-0700.

HEAD moved once while this review ran: `224495c` adds d9v (19.6's ranges CONFIRMED as written,
`C = 6` included) and d9w (a conftest tree guard shipped on the bug-109 branch). Neither touches a
plan-19 or plan-21 file (`git diff --stat 878647c..224495c`: `plan-review-2026-10-14.md` only).

The bug-109 fix (d9s) was committed DURING this review, on branch `bug-109-mcp-session` in the
clone `/Volumes/littlebig/refmatrix-bug109`: `06ecd0f` (fix) and `54e13c6` (d9w guard), not merged
to `master`. It is read here as the existing code both specs must now extend ([[#s-1]]).

**Scope:**
- plan-19 and tasks 19.0-19.6; plan-21 and tasks 21.1-21.4;
- [[exploration-session-phased-context]];
- the r3 report [[bsd-plan19-21-spec-rereview-r3-6091648]] (every id) and `#nm17-r3-5` of the
  23+17 r3 report;
- [[plan-review-2026-10-14]] `#t9-approvals`, `#t11-approvals` (d9p-d9u, then d9v/d9w),
  `#t10-waves`.

**Method:** read-only. Every code line the revised specs cite was re-read at HEAD and holds:
`store.py:2504`, `cli.py:12110`, `:12322`, `:10272`, `:1060`, `:1893`, `:1923-1927`;
`partitions.py:27`; `stm.py:127`, `:309`; `scan.py:535-537`; `hooks.py:263-345`. Probes, all
read-only: this subagent's own environment; `ps` of every `rmx mcp`; the STM rings and in-flight
sidecars under `.refmatrix/stm/`; the bug-109 clone's log and diff. No `src/`, `tests/`, store,
plan, registry or ledger file was touched, and no `rmx` command was run against a store.

rel: specifies -> [[plan-19-adaptive-memory-budget]]
rel: specifies -> [[plan-21-agent-context-usage]]
rel: derives-from -> [[bsd-plan19-21-spec-rereview-r3-6091648]]
rel: related-to -> [[plan-review-2026-10-14]]
rel: contradicts -> [[feedback_check_the_sibling_condition]]
rel: contradicts -> [[feedback_red_test_must_fail_at_head]]

## Live evidence {#evidence}

- **The input hook mutates the ring and graph BEFORE `Stm.record("input")`.** `focus_hook`
  (`cli.py:1971-1981`) runs `s.inflight_sweep()` first, and only then
  `if prompt and not _is_ambient_prompt(prompt): s.record("input", …)`. `inflight_sweep`
  (`stm.py:331-353`) calls `self.record("tool", …, extra={"abandoned": True})` for every parked
  call older than 90 s. `record` appends to the ring and ingests the refs into `focus.json`
  (`stm.py:246-282`). Two consequences:
  - The sweep runs before the snapshot that both specs place INSIDE `Stm.record(kind="input")`.
  - It runs before the ambient check, so ambient prompts also mutate state.
- **The sweep fires in real sessions.** Read off the ring of session `db80475a` (1,806 events):
  - 30 events are `abandoned`;
  - 17 of its 78 recorded prompts (22%) directly follow a swept run, and 16 of those 17 sweeps
    carried refs into the graph.
  - Right now `db80475a`'s sidecar holds one call parked 1,858 s, and `742dab0d`'s holds one.
- **The session switch, again.** Claude process `CLAUDE_PID=59363` ran `db80475a` until about
  13:35 and runs `742dab0d` now. This subagent's Bash env says `CLAUDE_CODE_SESSION_ID=742dab0d…`.
  Its MCP child `rmx mcp` pid 59378 (ppid 59363) still carries `b38025a7…` and has no `CLAUDE_PID`.
- **Three `latest_session` callers the specs never name** (`src/` read at HEAD):
  - `composite.py:100-103`: `build_topic_composite` sets `session = session or
    latest_session(root)`. scan-prompt calls it without a session (`scan.py:888-894`) inside
    `except Exception: comp = ""`, and the result is the per-prompt STM composite block. It reads
    the LIVE `focus_graph()` (`composite.py:106`).
  - `helix.py:84-96`: `_current_session` (`RMX_SESSION` → `latest_session`) excludes "the
    current session's" touches on the scan-prompt helix path.
  - `promote.py:158-161`: `promote_focus_edges` defaults to `latest_session`, and runs as the
    daemon op `promote_edges` when `rmx focus promote-edges --apply` is given no `--session`
    (`cli.py:1458-1498`). That is a durable LTM edge write.
- **The cluster member set is not stable for an untouched cluster.**
  - Every recorded input multiplies every node's recency by `DECAY = 0.85` (`stm.py:37-38`,
    `:420-424`).
  - `focus_graph(top=30)` cuts to the 30 best-scoring nodes (`stm.py:558-570`).
  - `cluster_focus` runs label propagation in SCORE order (`stm.py:751-785`).
  - So a non-selected cluster gains or loses members without being touched.
- **Event timestamps are local and naive.** Every telemetry writer stamps
  `time.strftime("%Y-%m-%dT%H:%M:%S")` (`telemetry.py:281`, `:329`, `:425`; `stm.py:259`). A live
  `query.log` row reads `"ts": "2026-10-14T14:04:41"`, with no zone.
- **bug-109 as built** (`06ecd0f`, clone only):
  - pointer `stm/by-pid/<pid>.json` = `{session, pid, pid_start, t}`;
  - written by the input hook at the top of the turn, before the sweep and the ambient check,
    for every envelope with a `session_id`;
  - `owner_claude_pid()` = `$CLAUDE_PID`, else the nearest `claude` ancestor within 4 levels;
  - `verbs._LONG_LIVED` is set by `serve_stdio`;
  - resolution order: long-lived = pointer → `RMX_SESSION` → `latest_session` → `default`; per
    call = `RMX_SESSION` → pointer → `latest_session` → `default`;
  - no SessionStart entry, no `SessionResolution`, no stale counter;
  - `tests/test_mcp_session_pointer.py` (10 tests);
  - no `bug_registry.md` row for bug-109 on `master` (`224495c`) or on the branch.

## Prior findings: status {#prior-status}

### r3 findings ([[bsd-plan19-21-spec-rereview-r3-6091648]]) {#prior-r3}

| id | status | evidence |
|---|---|---|
| b-1 MCP session frozen at spawn | **closed** (spec), **reopened in part by d9s** | 21.1 R1 (long-lived, env var dropped), R9 resolver + pid pointer + `pid_start` + two writers, R12 "Whose session", AC-1, AC-1b, AC-4. 19.0 R5 (write verbs raise `SessionUnresolved`, read verbs labelled), R0 hook env, AC-6b, AC-6c. The signatures are identical in both specs. Still open: bug-109 now builds the pointer first and the specs still say they will build it ([[#s-1]]). Three `latest_session` callers were never routed ([[#b-2]]) |
| b-2 sibling phase inputs racy; second-truncated `ts` | **partial** | 21.1 R9 `snapshot_pre_prompt` / `pre_prompt_state` (live-then-snapshot read: the ordering argument is sound), `turn` per channel, the `t0 − 1 s` rule withdrawn, AC-8b's three orderings; 19.0 R7, AC-6d; 19.6 R2, R3, AC-3c. The snapshot is taken AFTER the input hook's sweep has already mutated the ring and graph, and ambient prompts sweep too ([[#b-1]]) |
| b-3 vacuous AC-8 mutations; channel rule; scan-prompt partition | closed | R11 `recall_channel` (pinned by scanning the generated config), R11 "What scan-prompt and context deliver", AC-8 per-leg partition, AC-8c one leg per channel (nudge in 21.3 AC-2 plus its mutation), AC-8d non-ASCII guard on scan-prompt, recall-leg ASCII stated with 19.1 AC-6 owning `--pack` |
| s-1 `kind` map; concept-anchored memory body | closed | R10a `event_kind` table incl. `concept` (kinds verified at `cli.py:10272`, `partitions.py:27`); R11 attached body = its own `kind=memory` item, partition from the row (`find_memory_any_partition` at `store.py:2504` returns it); R12 `context_by_name`; AC-11e, AC-12 |
| s-2 fold arithmetic vs decay; `H` | closed | 19.2 R1 raw integer tables plus `memory_usage_daily`, R5 sum/min/max `merge_fn`, R7 recency at read time from daily counts, AC-6 (three batchings + reordered log), AC-17 (`H` varied, independent computation). The arithmetic replays exactly. The `day` key rests on an undefined `ts` zone: [[#s-2]] |
| s-3 two test bases; `malformed` | closed | 21.1 R5 key path = `root` (`cwd` only without `root`), base-`None` rows never `test_artifact`, class 0 `malformed` under `source="events"`; AC-7 two-base, cwd-fallback, live-tree and event legs; 19.2 R5, AC-16 x/y/z |
| s-4 collapsed line not byte-stable | **partial** | 19.6 R9 (label + id only, label frozen at first collapse, counts on the expanded header, cap `C`), AC-7c regex, AC-7d (re-touch, weight reorder), AC-7g; exploration `#tree-render` matches. The member set it assumes stable is not stable for an untouched cluster, and the composite is versioned as ONE block whose expanded header now moves every turn ([[#s-3]]) |
| m-1 stale names, statuses, edge | closed | 19.1 title, plan-19 `#tasks` `--max-bytes`; plan-21 R8-R12 citations; 19.2 R7 and plan-19 item 1 cite d9k; user-asserted floor = `metadata.type` `user`/`guardrail` (= d9r) with AC-9 and a mutation; plan-21 items 3/4 CLOSED; the plan-19 `#dependencies` 19.1 row states the 21.1 edge. `#t10-waves` itself still lists them as parallel bullets ([[#m-3]]) |
| m-2 unterminated heredoc | closed | 19.0 R1 rule, AC-1d, mutation |
| m-3 multibyte density | closed | 19.1 AC-1 (≥ 4 multibyte chars per line, recorded pre-check), AC-6 (≥ 6 bytes of excess before each span) |
| m-4 structured rung-2 match; R0 facts | closed | 19.0 R2 rung 2 (byte hit = candidate only), AC-4f, R0 (id on disk at PostToolUse; hook env) |
| m-5 marker writer; non-prompt arms; carryover | closed | 19.6 R8a `focus hook --event compact-marker` in its own PreCompact entry (AC-7f with and without the recall), R7 (`session_start`/`precompact` always `fixed`; carryover stated, same-arm lift printed), AC-7b. Small gap: [[#m-3]] |
| m-6 exploration wording | closed | `#shape` row replaced by return/new; `#decisions` closed by d5b |
| m-7 focus-note edges | closed | 21.1 R12 edge cases, AC-11f, two mutations |
| m-8 two previews; cap in bytes | closed | 19.5 R1(a) (char numbers taken as bytes), R2 "before" uses the same measured `cap`/`preview`; 19.1 AC-2 |
| nm17-r3-5 19.4 AC-2 vs `requires_arming=True` | closed | 19.4 AC-2 unarmed day 1 (`dry_run:unarmed`, byte-identical outputs), hand dry run → real run → `rmx hub maintain arm … --run-id`, armed day 2; mutation; matches 17.2 `#r7-unarmed` (an earlier dry-run line, surface-valued `invoked_by`) |

**Totals:** 16 r3 ids: 13 closed, 3 partial (b-1's d9s reconciliation, b-2, s-4), 0 open.

## Findings {#findings}

### BULLSHIT b-1: the pre-prompt snapshot is taken after the input hook has already swept abandoned calls into the ring and the graph {#b-1}

**Where:**
- 21.1 R9 "The pre-prompt state" (the writer and the "This is exact because …" proof), R10
  `stm_events_n`, AC-8b, its mutations;
- 19.0 R7, AC-6d;
- 19.6 R2, R3, AC-3c.

**What:**
- **The proof's premise is false.** The specs put `snapshot_pre_prompt` inside
  `Stm.record(kind="input")`, "BEFORE it appends the event or touches the graph". The proof
  reads "the writer writes `pre.json` before it changes anything". In the production hook it does
  not:
  - `focus_hook` first runs `inflight_sweep()` (`cli.py:1976`);
  - the sweep `record`s one `abandoned` tool event per call parked longer than 90 s, appending to
    the ring AND ingesting its refs into `focus.json` (`stm.py:331-353` → `:246-282`);
  - only then does `record("input")` run (`cli.py:1980-1981`).
  A reader that reads the live state before the hook starts sees the pre-sweep ring and graph.
  One that matches `pre.json` gets the post-sweep state. So `stm_events_n` differs by the number
  of swept calls, and `focus_topics_n`, `overlap` and 19.6's phase can differ by their refs:
  ordering (i) differs from (ii).
- **"Ambient prompts never changed state" is false too.** 21.1 R9 says ambient prompts "write no
  snapshot and their readers read the live state, which they never changed". The sweep runs
  BEFORE the `_is_ambient_prompt` check, so an ambient prompt's input hook mutates the state its
  readers race.
- **It is not rare.** 17 of `db80475a`'s 78 recorded prompts followed a sweep, 16 of them with
  refs ([[#evidence]]). Denied calls, hung calls and a background subagent's long calls park in
  the parent's sidecar.
- **None of the ACs can fail on it.** 21.1 AC-8b, 19.0 AC-6d and 19.6 AC-3c seed no parked call.
  AC-6d even asserts that `pre.json` holds "the ring event count from BEFORE the call", which a
  parked call would break, but the fixture has none.

**Why it's bullshit:** this is r3 [[bsd-plan19-21-spec-rereview-r3-6091648#b-2]]'s fix certified
by fixtures without the mutation that matters. The specs read `Stm.record` and missed the
production caller that writes before it. That is the sibling-condition miss a third time
([[feedback_check_the_sibling_condition]]). r3's impression asked to "list every value computed
from the racing write". The inverse also holds: list every WRITE the racing process makes before
the snapshot.

**Fix:**
- The snapshot is the input hook's first state access, in `focus_hook`, not in `Stm.record`:
  - call `s.snapshot_pre_prompt(prompt)` for every non-empty prompt, ambient included, before
    `inflight_sweep()`;
  - bug-109's pointer write may precede it, because readers never read the pointer as state.
- Or move the sweep after the input record. That reorders the timeline the sweep's docstring
  wants, so the snapshot move is the smaller change.
- State it in 21.1 R9 and 19.0 R7, and fix the ambient sentence.
- Every three-ordering AC (21.1 AC-8b, 19.6 AC-3c), and 19.0 AC-6d, seeds a call parked more than
  90 s whose refs join the active topic, plus an ambient-prompt leg.
- New mutation: the snapshot taken inside `record("input")` after the sweep. AC-8b fails because
  (i) and (ii) disagree on `stm_events_n`.

**Pattern match:** YES. It matches "the test builds the one case where the input is clean" and
r3's sibling impression.

### BULLSHIT b-2: three `latest_session` callers were never routed, one of them the very block 19.6 versions {#b-2}

**Where:**
- 21.1 R9 ("`stm.latest_session` … is NEVER consulted");
- 19.0 R5 ("Every resolver of 'this session' used by STM …" names `scan.py:535-537`,
  `verbs.resolve_session`, `cli._resolve_stm_session` and the focus hook, and "`latest_session` is
  not consulted on any of these paths"), its mutation list and Files;
- 19.6 R2 ("no phase code reads `focus.json` … directly"), R9 and Files.

**What:** `src/` has three more callers ([[#evidence]]), and no spec names them.
- **`composite.py:103`, the scan-prompt STM composite.**
  - `scan.py:888-894` calls `build_topic_composite(s, composite_root, …)` with no session, so it
    renders the NEWEST ring (bug-100's shape) from the LIVE `focus_graph()`, racing the input hook
    ([[#b-1]]).
  - Its failure is swallowed (`except Exception: comp = ""`).
  - This block is `stm-topic-composite`, the one 19.6 R9 turns into the expand/collapse tree, R5
    versions and Table A measures. 19.6's Files put the render in `stm.py`, but the render lives
    in `composite.py`.
  - After both specs ship, scan-prompt's enrichment reads the envelope's ring through
    `pre_prompt_state`, while the composite in the same payload reads another session's live
    graph.
- **`helix.py:96`.** `_current_session` decides whose touches the helix stale gate excludes on
  the scan-prompt path. With two sessions open, it excludes the wrong one.
- **`promote.py:161`.** `rmx focus promote-edges --apply` without `--session` promotes the newest
  ring's co-occurrence into durable `co-occurs` edges. It is a write of the class 19.0 R5 says must
  raise rather than misroute.
- **The mutations miss them.** 19.0's mutation "restore the `latest_session` fallback on the scan
  enrichment path" covers `scan.py:535` only.

**Why it's bullshit:** both specs assert a universal ("NEVER", "every resolver") that the code
contradicts in three places. One of them is the prompt-time block that plan-19's measurement and
versioning are built on. bug-109 fixes the MCP write path but keeps `latest_session` as its last
fallback, so these callers stay misrouted after it merges.

**Fix:**
- 19.0 R5 lists every caller:
  - `composite.build_topic_composite`: session from the resolver; graph from
    `pre_prompt_state(…).graph` on prompt-time calls;
  - `helix._current_session`: the resolver;
  - `promote_focus_edges` / `focus promote-edges`: the resolver, `SessionUnresolved` on `--apply`;
  - the scan-prompt composite's `except Exception` prints and counts instead of returning "".
- An AC-6e enumerates every `latest_session(` call in `src/` (AST scan) and fails on any caller
  outside an explicit allow-list: the labelled read verbs of R5 ([[#m-2]]).
- 19.6 Files add `src/refmatrix/composite.py` (R2, R9), and 19.6 R2's rule covers the composite.
- Mutations: the composite or helix restored to `latest_session` (AC-6e, and AC-6's two-ring
  fixture through scan-prompt); `promote-edges --apply` with no session writing (AC-6c's leg).

**Pattern match:** YES. It is bug-100's shape, and a sibling-condition miss in the same specs for
the third round running.

### SKETCHY s-1: bug-109 now owns the pointer and the MCP resolution, and both specs still plan to build them {#s-1}

**Where:** 21.1 R1, R9 ("built by whichever of 21.1 and 19.0 merges first"), AC-1b ("RED at HEAD
(the server has no per-call resolution)"), Files; 19.0 R5, R0, AC-6b, AC-6c, test strategy
("RED first"), Files; [[plan-review-2026-10-14#t11-approvals]] d9s.

**What:** d9s ships a subset first, and its code exists (`06ecd0f`, [[#evidence]]). The specs
predate d9s (`a820b22`), and they now disagree with it on every point a merge will hit:
- **File format.** bug-109 writes `{session, pid, pid_start, t}`. 21.1 R9 specifies
  `{session_id, pid, pid_start, written_at, hook_source}`. A spec built as written either
  rewrites bug-109's format or reads two.
- **Writers.** bug-109's only writer is the input hook. The specs add a SessionStart entry
  (`rmx focus hook --event session-start`, `startup|resume|clear|compact`) as the primary writer.
  Both spec ACs (21.1 AC-1b, 19.0 AC-6b) drive that entry, so after bug-109 merges they are RED
  only because `--event session-start` is not a click choice. They would be RED for the wrong
  reason ([[feedback_red_test_must_fail_at_head]]).
- **Resolution order.**
  - Per-call: bug-109 has `RMX_SESSION` → pointer → `latest_session` → `default`. The specs have
    envelope → `CLAUDE_CODE_SESSION_ID` → pointer → `RMX_SESSION` → none.
  - Long-lived: bug-109 identifies the process by the `verbs._LONG_LIVED` module flag. The specs
    pass `stm.resolve_session(…, long_lived=True)`.
  - Neither spec says which order wins, or that bug-109's `latest_session` / `default` tail is
    what 19.0 R5 removes.
- **Silent misses.** bug-109's `owner_claude_pid()` returning `None` writes nothing and prints
  nothing, and a stale or unreadable pointer falls through silently. 21.1 R9 wants one stderr line
  and a `pid_pointer_stale` count.
- **Tests twice.** `tests/test_mcp_session_pointer.py` (10 tests) already covers the pointer. The
  specs' ACs re-specify it without naming that file.
- **No registry row.** bug-109 is named by d9s but has no `workflow/bug_registry.md` row, on
  `master` or on its branch. bug-104's row still names `_extract_refs` as the cause, which 19.0
  Why refutes.

**Fix:**
- 21.1 R9 and 19.0 R5 cite bug-109's functions (`stm.write_pid_pointer`, `read_pid_pointer`,
  `owner_claude_pid`, `verbs._LONG_LIVED`) as EXISTING code, and list the deltas each spec owns:
  - the SessionStart writer;
  - `SessionResolution` with `source`;
  - the per-call order (adopt one, and state it once);
  - `latest_session` / `default` removed for writes;
  - the stale and miss counters;
  - `CLAUDE_CODE_SESSION_ID` dropped from the server env.
- Adopt bug-109's key names, or state the read-both migration.
- Re-baseline every "RED at HEAD" claim against post-bug-109 `master`, naming the assertion that
  fails (the SessionStart writer, `SessionUnresolved`, the `context-mcp` row, `used`), not the
  session switch bug-109 already passes.
- Extend `tests/test_mcp_session_pointer.py` rather than add a parallel file.
- Log bug-109 in the registry before merge.

### SKETCHY s-2: 19.2's `day` is "the UTC date of the event's `ts`", and no spec says what zone `ts` is in {#s-2}

**Where:** 19.2 R1 (`day`), R7 (`mid(day)`), AC-6, AC-17; 21.1 R10 (`ts` listed, never defined).

**What:**
- **The arithmetic is exact.** The r3 fix made the fold exact: integers, mins and maxes.
- **The key is not.** Every timestamp writer in the repo emits local naive
  `time.strftime("%Y-%m-%dT%H:%M:%S")` ([[#evidence]]), and 21.1 R10 does not override that for
  events. So turning `ts` into a "UTC date" uses the FOLDING process's zone:
  - a replay on a machine or launchd environment with a different `TZ`, or across a DST change,
    files events under different `day` rows;
  - the DST fall-back hour makes naive `ts` non-monotonic.
- **The ACs cannot see it.** AC-6's "byte-identical under any batching" and AC-17's independent
  computation both run in one zone, so they cannot fail on this. The claim "any order and any
  batch boundary give the same rows, exactly" holds per zone, not per log.

**Fix:**
- 21.1 R10 defines `ts` as UTC ISO-8601 with `Z` (or adds an epoch `t`, as R9 already does for
  input events), written by `emit_recall_events`.
- 19.2 derives `day` and `mid(day)` from it.
- AC-6 adds a replay under `TZ=UTC` and `TZ=America/Los_Angeles` across a DST boundary, with
  identical tables.

### SKETCHY s-3: 19.6 R9's byte-stable collapsed line rests on a member set the clustering does not hold still, inside a block that changes every turn {#s-3}

**Where:** 19.6 R9 ("BYTE-STABLE across turns while its member set is unchanged, so versioned
injection (R5) can send it as unchanged"), R5, R1 / Table A, AC-7d, AC-7g;
[[exploration-session-phased-context]] `#tree-render`.

**What:**
- **Under its own cap `C`, the line holds.** The line is now `▸ topic: <label>  (id <cid>)`, with
  the label frozen and the shown set ordered by first-collapse. AC-7g keeps the other `C − 1` lines
  byte-identical when a cluster is added. That part is sound.
- **The member set is not stable.** The premise "while its member set is unchanged" does not hold
  for an untouched cluster ([[#evidence]]):
  - every input decays every node by 0.85;
  - `focus_graph(top=30)` drops whatever falls below the top 30;
  - label propagation iterates in score order.
  So a collapsed cluster loses or gains members without being touched, mints a new `<cid>`, and
  re-enters as "most recently first-collapsed", pushing a stable line out of the shown `C`.
  AC-7d's fixture holds the member set fixed by construction (re-touch, weight reorder) and never
  runs a decay-only turn.
- **The versioning unit does not match.** R5 versions a BLOCK by content hash, and the composite
  is one block id (`stm-topic-composite`). R9 moved the event count and the `L<a>–L<b>` range onto
  the expanded cluster's header, which changes on every warm or return turn. The composite
  block's hash therefore changes every such turn, and a byte-stable collapsed line inside it buys
  no `unchanged`. That would change only if collapsed lines are their own versioned units, and no
  requirement says they are.
- **"First collapsed" is undefined on a second collapse.** A cluster that is expanded, then
  collapses again, keeps or resets its first-collapse time: the spec does not say which. If it
  keeps it, the cluster that just lost focus, the likeliest `return`, can sit behind
  `+<m> more topics`.

**Fix:**
- R1 measures, on the frozen sets, the per-turn persistence of non-selected clusters' member
  sets, which is the share of collapsed lines byte-identical turn to turn. Table A then decides on
  the real figure.
- R5/R9 state the unit: either each collapsed line is versioned by `<cid>`, or the composite
  splits into an expanded block and a collapsed block with no counts in the latter.
- R9 defines first-collapse on re-collapse.
- AC-7d adds a decay-only turn in which a member drops below the top-30 cut.
- d9v confirmed `C = 6` and the tables. This changes what Table A measures for the composite, not
  any confirmed number.

### MEH m-1: `pre_prompt_state` residuals beyond the sweep {#m-1}

- **`S` measures the wrong interval.** R0 measures entry-to-entry skew between the parallel hooks,
  but the match compares the reader's entry `t0` with the WRITER's `wall`. `wall` is stamped after
  the writer's imports and envelope parse, plus bug-109's pointer read (a `ps` call on a change).
  Fix: log `pre.wall − reader t0` directly in R0.
- **Background subagents append between the reads.** Their PostToolUse events land in the parent
  ring during the window (19.0 R2 keeps them in the ring), so `events_n` varies by ordering for a
  reason unrelated to the input hook. Fix: count parent-origin events only, or state the residual.
- **`focus.json` has no lock.** It is read-modify-written without a lock (`stm.py:405-424`), so a
  concurrent PostToolUse ingest can lose the input hook's update. This predates the specs; state
  it as a known limit.

### MEH m-2: 19.0 R5's read-verb fallback IS a `latest_session` consult {#m-2}

19.0 R5 lets read verbs "read the newest ring and say so". In the same requirement it says
`latest_session` "is not consulted on any of these paths", and 21.1 R9 says it is NEVER consulted.
The labelled read fallback is reasonable. Name it as the ONE allowed `latest_session` use, and make
[[#b-2]]'s AST allow-list exactly those read verbs.

### MEH m-3: small cross-file gaps {#m-3}

- **The marker dispatch has no owner.** 19.6 R8a says 19.0's `session-start` hook also runs the
  compaction marker when `source=compact`. Neither 19.0 R5 / Files nor 19.6 Files lists that
  dispatch change. Name it in 19.6 Files (`cli.py` `focus hook --event session-start`).
- **The wave list still shows the edge as parallel.** `#t10-waves` still lists 21.1 and
  "19.5 R1 → 19.1 → 19.2" as parallel bullets, while plan-19 `#dependencies` now states the
  21.1 → 19.1 edge. The decision log is the order of record, so state the edge there too.
- **Stale status lines.** 19.6's R0 and `#ranges` status lines still read PROPOSED. d9v says they
  flip after this review lands, so no action is due from the pair until then.

## Cross-plan consistency {#cross-plan}

| contract | plan-21 | plan-19 | verdict |
|---|---|---|---|
| `stm.resolve_session` signature | R9: `(root, *, envelope=None, long_lived=False) -> SessionResolution(session, source)` | 19.0 R5: identical | identical; both ignore bug-109's existing functions and order ([[#s-1]]) |
| per-call order | envelope → `CLAUDE_CODE_SESSION_ID` → pointer(`$CLAUDE_PID`) → `RMX_SESSION` → none | identical | identical between specs; differs from bug-109 (`RMX_SESSION` → pointer → newest → default) |
| long-lived order | pointer(`os.getppid()`) → `RMX_SESSION` → none | identical | identical; bug-109 walks to the `claude` ancestor (same pid live: 59378 → 59363) and keeps the newest-ring tail |
| pid pointer file | `{session_id, pid, pid_start, written_at, hook_source}`; SessionStart + input writers | "written by SessionStart, refreshed by the input hook" | specs agree; bug-109 writes `{session, pid, pid_start, t}` from the input hook only ([[#s-1]]) |
| unresolved session | rows/events `session: null`; R12 no `used` | 19.0 R5: writes raise, reads labelled newest | consistent; the read fallback contradicts "NEVER" ([[#m-2]]) |
| `latest_session` callers | "NEVER consulted" | scan enrichment, verbs, CLI, focus hook | **gap**: composite, helix, promote ([[#b-2]]) |
| `pre_prompt_state` | R9 (writer in `Stm.record`) | 19.0 R7 (same), 19.6 R2/R3 | identical between specs; **wrong writer site** ([[#b-1]]) |
| `day` / `ts` | `ts` undefined | 19.2 R1 UTC day | **gap** ([[#s-2]]) |
| `delivered` owner, unit, `kind`, classifier, channel rule | R5, R10, R10a, R11 | 19.1 R8, 19.2 R3/R5, 21.3 AC-2 | consistent |
| asserted floor | — | 19.2 R7 `feedback` / `user` / `guardrail` / protected / `rel:` | matches d9r |

## Open-after-revision items: who decides {#open-items}

### plan-19 {#open-19}

1. ADR floor: settled (d9k).
2. 19.6 tables, thresholds, `N`, `K`, `C`: CONFIRMED by the user (d9v, at `224495c`). The r4
   items do not change any confirmed number. [[#s-3]] changes what Table A measures for the
   composite, and [[#b-1]] changes when the classifier's input is taken. Both are spec work.
3. Everything else in plan-19 `#open-after-revision` is settled or closed.

### plan-21 {#open-21}

All items closed or settled. [[#b-1]], [[#b-2]], [[#s-1]] and [[#s-2]] are spec work.

### Needs the user {#needs-user}

- **Nothing is blocked on a decision.**
- **The user should know that bug-109 is a partial fix.** As built, its write verbs still fall
  back to the newest ring when no pointer resolves, so the misroute it fixes can recur silently
  until 19.0 R5 lands. Also, the scan-prompt STM composite still reads the newest ring ([[#b-2]]).

## Verdict {#verdict}

- **plan-19: NEEDS-REVISION.**
  - Prior: 13/16 r3 ids closed; b-1 (d9s reconciliation), b-2 and s-4 partial.
  - New: [[#b-1]] (19.0 R7, 19.6 R2/AC-3c), [[#b-2]] (19.0 R5, 19.6 Files), [[#s-1]] (19.0 R5),
    [[#s-2]] (19.2), [[#s-3]] (19.6), [[#m-1]], [[#m-2]], [[#m-3]].
- **plan-21: NEEDS-REVISION.**
  - New: [[#b-1]] (21.1 R9/AC-8b), [[#b-2]] (21.1 R9 "NEVER"), [[#s-1]] (21.1 R1/R9/AC-1b),
    [[#s-2]] (21.1 R10 `ts`), [[#m-1]], [[#m-2]].

**8 new findings: 2 BULLSHIT, 3 SKETCHY, 3 MEH.** b-1, b-2, s-1, s-2, m-1 and m-2 span both
plans.

The resolver and snapshot SIGNATURES now agree across the pair. What fails is the specs'
reading of production code around them:
- the hook body that writes before the snapshot;
- three callers that bypass the resolver;
- a bug fix that landed first;
- a timestamp convention the fold silently inherits.

rel: contradicts -> [[feedback_no_silent_failures]]

## Ledger entries (to merge) {#ledger}

### INDEX.md row {#ledger-index}

```
| 878647c (plan-19 + plan-21 spec re-review r4, 19.0-19.6 + 21.1-21.4; written 2026-10-14T14:08-0700; HEAD moved to 224495c (d9v/d9w, decision log only); bug-109 read at 06ecd0f on the littlebig clone, unmerged) | 2026-10-14 | Todd Holley / Opus 5.5 / spec-reviser (Wave 0 revision round 3) | DIRTY | 8 (2B/3S/3M) | [[bsd-plan19-21-spec-rereview-r4-878647c]]. NEEDS-REVISION both. Prior r3: 13/16 closed, 3 partial (b-1 via d9s, b-2, s-4). Pre-prompt snapshot sits inside Stm.record but focus_hook runs inflight_sweep (records + ingests abandoned calls) first, ambient prompts too -- 17/78 db80475a prompts followed a sweep; no AC seeds a parked call. latest_session still called by composite.py:103 (scan-prompt STM composite = 19.6's versioned block), helix.py:96, promote.py:161 while specs say NEVER. bug-109 (06ecd0f) built the pointer first with a different format/order/writer; specs still say first-to-merge builds it, AC-1b/AC-6b RED for the wrong reason; no registry row. 19.2 day = UTC date of a zone-less local ts. 19.6 collapsed line stable only if member set is, which decay + top-30 cut + score-order label propagation do not give; composite versioned as one block whose header now moves. |
```

### last_run.log line {#ledger-last-run}

```
2026-10-14T14:08:00-0700 commit=878647c verdict=DIRTY findings=8 (2B/3S/3M) report=2026-10-14-1408-plan19-21-r4-spec-rereview-snapshot-after-sweep-and-unrouted-latest-session-878647c.md
```

### Impressions {#ledger-impressions}

- 2026-10-14 (p19/21 r4): **"Before it changes anything" must be checked against the CALLER, not
  the method.** The snapshot was put first inside `Stm.record`, while `focus_hook` writes through
  `inflight_sweep` before calling it. To check a "first" claim, read the production entry point
  top to bottom.
- 2026-10-14 (p19/21 r4): **To retire a fallback, list its callers with a scan, not from memory.**
  "latest_session is NEVER consulted" survived four rounds because each round listed the callers
  it already knew. `composite.py`, `helix.py` and `promote.py` were never named. An AST allow-list
  test is the durable form.
- 2026-10-14 (p19/21 r4): **A hotfix that lands mid-review becomes the spec's baseline.** bug-109
  shipped a different pointer format and resolution order hours after the specs said "first to
  merge builds it". Re-read the bug branch before closing a spec item that it overlaps.
