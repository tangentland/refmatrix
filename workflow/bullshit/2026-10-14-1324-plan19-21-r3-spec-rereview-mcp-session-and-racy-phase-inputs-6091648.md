---
gmd: "0.1"
id: bsd-plan19-21-spec-rereview-r3-6091648
title: "plan-19 + plan-21 spec re-review r3: the MCP server's session id is frozen at spawn, the turn race was fixed but its sibling phase inputs were not, and two AC-8 mutations cannot fail"
severity: BULLSHIT
plan: plan-19-adaptive-memory-budget, plan-21-agent-context-usage
task: spec-rereview-19.0-19.6-21.1-21.4
round: 3
tags: [bsd, audit, spec-review, re-review, recall-events, memory, stm, mcp, session, telemetry, plan-19, plan-21]
---

# ch-bsd spec re-review r3 of plans 19 and 21 at `6091648` {#root}

**Commit reviewed:** `6091648` on branch `wave0-spec-reviews`.
**Written:** 2026-10-14T13:24:43-0700.

HEAD moved twice while this review ran: `3021cd6` (d9k, the ADR-0004 amendment APPROVED and folded
into `#rule-floor` / `#rule-no-delete` / `#rule-asserted-floor`; d9l) and `097e7b1` (`#t10-waves`).
Neither touches a plan-19 or plan-21 file (`git diff --stat 6091648..HEAD`). Both are taken into
account where they change a status (plan-19 open item 1, the 19.2 R7 wording).

**Scope:**
- plan-19 and tasks 19.0–19.6;
- plan-21 and tasks 21.1–21.4;
- the r2 report [[bsd-plan19-21-spec-rereview-32dde06]] and its r1 partials;
- [[plan-review-2026-10-14]] `#t9`, `#t9-fixes`, `#t9-approvals`, `#t10-waves`;
- ADR-0004 `#amend-2026-10-14` and `#amend-counter-rules`;
- 23.0 R1/R2/AC-4 and 23.1 R1/R3/R4/R6/R8, which these plans consume.

**Method:** read-only. Every code line the revised specs cite was re-read at HEAD and holds:
`cli.py:1411`, `:1893`, `:1906`, `:1923`, `:1946`, `:5152`, `:6202`, `:11326`;
`verbs.py:519-530`, `:538`, `:679`, `:766`, `:908`, `:1102`; `stm.py:43`, `:53`, `:309`,
`:447-480`, `:840`; `scan.py:535`; `store.py:2618`; `telemetry.py:151`; `hooks.py:263-345`.
Probes, all read-only:
- the environment of this session's MCP server process;
- the parent's in-flight sidecar against the live subagent transcripts, during a running call;
- `cli.log`'s row fields;
- the exploration and plan-13 diffs in `69c5dc4`.

No `src/`, `tests/`, store, plan file or ledger was touched. No `rmx` command was run against a
store, and no suite was run.

rel: specifies -> [[plan-19-adaptive-memory-budget]]
rel: specifies -> [[plan-21-agent-context-usage]]
rel: derives-from -> [[bsd-plan19-21-spec-rereview-32dde06]]
rel: related-to -> [[plan-review-2026-10-14]]
rel: related-to -> [[refmatrix/adr-0004-unified-location-space-index#amend-2026-10-14]]
rel: contradicts -> [[feedback_check_the_sibling_condition]]
rel: contradicts -> [[feedback_no_silent_failures]]

## Live evidence {#evidence}

- **The MCP server's session id is frozen at spawn.** The Claude process `CLAUDE_PID=59363`
  (started 2026-10-06 22:27) now runs session `db80475a…`, and the Bash tool's
  `CLAUDE_CODE_SESSION_ID` says so. Its MCP child, `rmx mcp` pid 59378 (started 22:27:57 the same
  night), carries `CLAUDE_CODE_SESSION_ID=b38025a7…`, and has no `RMX_SESSION`.
  `.refmatrix/stm/b38025a7….jsonl` was last written 2026-10-07 10:09. Three older orphan
  `rmx mcp` processes carry other stale ids. So after `/resume` or `/clear` the MCP server's env
  names a dead session for the rest of the process's life. Nothing in `src/` reads
  `CLAUDE_CODE_SESSION_ID` today. `verbs.resolve_session` (`verbs.py:519-530`) uses
  `RMX_SESSION`, then `latest_session`, and it is called by `save_state`, `focus`, `focus_note`,
  `change_subject`, `task` and `recall_state` (`verbs.py:845`, `:886`, `:910`, `:923`, `:979`,
  `:1013`).
- **The tool_use id is on disk while the call runs.** During one of this review's own Bash calls,
  its `toolu_01R7Bet…` id was already parked in the parent's `db80475a….inflight.json`, and it was
  already a `tool_use` block in this subagent's `agent-ad150d615f2d525ad.jsonl`. It was absent
  from the parent transcript. This is positive evidence for 19.0 rung 2 (the block exists before
  PostToolUse).
  - The same probe found in-flight ids TEXTUALLY in two subagent files at once: one file quoted
    them in a `tool_result`. Only a structured `tool_use.id` match is safe.
  - The parked `terse` of that call carried `glob.glob`, `json.load`, `inf.items`,
    `os.path.basen` and `v.get`: bug-104 is still live.
- **The input hook mutates the graph in place.** `Stm.record` (`stm.py:246-282`) appends the event
  and then calls `_ingest_into_graph(rlist, …)` on the same call. A parallel reader of
  `focus.json` therefore sees this prompt's own terms, or does not, by scheduling. The event `ts`
  is `time.strftime("%Y-%m-%dT%H:%M:%S")`, truncated to the SECOND (`stm.py:259`).
- **The JSON renderer is ASCII.** `memory recall --json` prints `_json.dumps(rows, indent=2)`
  with the default `ensure_ascii=True`, so `—` reaches stdout as `—`.
- **scan-prompt does not read the memory partition.** `scan.py` has no memory or partition
  retrieval. Memory text reaches its payload only through `context.py:230-243`, where a bare slug
  "very often" anchors on the CONCEPT node and the memory body is attached by
  `find_memory_any_partition`.
- **`cli.log` timing.** Each row carries `ts` (to the second) and `latency_ms`. That latency is
  measured after process entry (1–6 ms for `focus hook`), so process start-up skew between
  parallel hooks is not recorded anywhere.

## Prior findings: status {#prior-status}

### r2 findings ([[bsd-plan19-21-spec-rereview-32dde06]]) {#prior-r2}

| id | status | evidence |
|---|---|---|
| b-1 schema lacks `partition`/`cwd`/`root`; channel enum; non-memory events | closed | 21.1 R10 has all three, never null, and `RECALL_EVENT_FIELDS_V1`. 19.2 R3 uses the enum verbatim and counts `kind == memory` only; AC-15, AC-16. The scan-prompt/context kind gap is new: [[#s-1]] |
| b-2 AC-6 vs AC-7 | closed | R5 totals rule (Option A). AC-6 prints `legacy_unattributed=<L>`. AC-7 uses five rows (3 counted). The paired mutation fails both |
| b-3 19.0 ±2 s window | closed | rung 2 by `tool_use_id` (verified live, [[#evidence]]); rung 2b from the park time; rung 3 judges completed-search and open-call; AC-4e covers 10 s and 45 s; AC-4 literal reads `ch-bsd` |
| b-4 19.0 wrong mechanism | closed | Why names `cli._tool_event_fields`; R1 `stm.command_refs` on both paths; rebuild re-extracts from `detail`; AC-1b, AC-1c. Residual: [[#m-2]] |
| b-5 `used` underspecified | **partial** | matcher, lookup, global destination, call sites and AC-11a–d are all specified. The common `context` path is excluded ([[#s-1]]), and every MCP-route `used` matches the wrong session ([[#b-1]]) |
| s-1 `delivered` owner | closed | 21.1 R11 is the single emission site; 19.1 R8 returns spans only; 19.2 R3; 19.1 AC-6 (7, not 14) |
| s-2 units, offsets, `seen` | closed | bytes everywhere (21.1 R10, 19.1 R1, 19.5 R1/R2); hook-line and body spans; 19.5 AC-2b |
| s-3 phase-field ACs, `turn` race | **partial** | AC-8 phase clause and AC-8b exist. `turn` is not race-free on second-truncated ts, and the sibling phase inputs are still racy ([[#b-2]]) |
| s-4 19.6 Table C | closed | per-prompt arm; live `fixed` arm; one read-back definition (`score_readback.py`); baseline used as a validity check; thresholds PROPOSED; a concrete re-measure trigger |
| s-5 degenerate score | closed | d9e accepts the defaults; 19.2 R7 records the interaction; `at_floor` printed |
| s-6 stale-subject accretion | closed | 19.4 R5 names 22.1a's `stale-subject` class (verified at `task-22.1a:96`); AC-4b bounds growth |
| s-7 21.3 identifier set | closed | 21.3 R0 draws from the local raw log and commits a count + sha256 |
| m-1 wave slips | closed | 19.1 AC-3 seeds `metadata.stale`; 19.5 R1 runs in Wave 1 (`#t10-waves`) |
| m-2 PreCompact constant | closed | `hooks.PRECOMPACT_STDOUT_DELIVERED` |
| m-3 `first_seen` | closed | 19.2 R1 (min event ts; virtual null) |
| m-4 21.4 question text | closed | 21.4 R1 states the question-text exception |
| m-5 "in the window" | closed | 19.6 R8a. The marker's writer is unnamed: [[#m-5]] |
| m-6 stale wording | **partial** | 21.3 band row annotated. The exploration `#shape` table still has the `shift` row, and `#decisions` still lists the two items d5b closed ([[#m-6]]) |

**Totals:** 18 r2 findings: 15 closed, 3 partial, 0 open.

### r1 partials carried into r2 {#prior-r1}

| id | status | evidence |
|---|---|---|
| 19 r1 b-4 (ADR floor text) | closed | d9k at `3021cd6`: `#rule-floor` now reads `base * (1 + log1p(hits + 2*used))`, at read time over raw counts, and matches 19.2 R7 |
| 19 r1 b-6 (focus-note matcher) | closed | 21.1 R12 matcher + AC-11c (MCP session caveat: [[#b-1]]) |
| 21 r1 b-2 (channel enum, 19.2 side) | closed | 19.2 R3 |
| 21 r1 s-1 (delivered vs seen) | closed | 19.5 R2 |
| 21 r1 s-2 (phase fields, `used`) | **partial** | as r2 s-3 ([[#b-2]]) |
| 21 r1 s-3 (frozen AC) | closed | AC-6 / AC-7 |
| 21 r1 s-8 (exploration causal story) | closed | `69c5dc4` corrected the exploration (34; `-E` struck; the replica-route reranker caveat). plan-21 open item 3 still calls it open ([[#m-1]]) |
| decision-log s-8 (21.4 source and privacy) | closed | d9h; 21.4 R1 |

**Totals:** 8 r1 partials: 7 closed, 1 partial.

## Findings {#findings}

### BULLSHIT b-1: the session source both specs promote is frozen at spawn in the MCP server, the agent's primary route {#b-1}

**Where:**
- 19.0 R5 (the verb resolver: envelope → `CLAUDE_CODE_SESSION_ID` → `RMX_SESSION`, and
  `latest_session` removed);
- 21.1 R9 (the same order for every `query.log` row and event), R12 (`used` lookup by session),
  and AC-1 / AC-4.

**What:** a long-lived `rmx mcp` keeps the `CLAUDE_CODE_SESSION_ID` it was spawned with. On this
machine that is `b38025a7…`, idle since 2026-10-07, while it serves session `db80475a…`
([[#evidence]]). MCP calls have no hook envelope, so under both specs they resolve to the dead id.
The consequences:
- **19.0 R5 is a regression on a memory path.** Today an MCP `rmx_focus_note`, `rmx_save_state`,
  `rmx_task` or `rmx_recall_state` resolves through `RMX_SESSION` → `latest_session`, which picks
  the newest ring and is right whenever one session is active. Under R5 every one of them writes
  to, checkpoints or promotes the DEAD session's ring. If a verb is treated like enrichment ("when
  none of the three is present … skipped"), a write is silently dropped. Either outcome breaks the
  no-silent-failure rule on a memory path.
- **21.1 R9 / R12.**
  - Every MCP `context-mcp` row and every MCP-route event carries the wrong `session`.
  - `delivered_in_session` searches the wrong session's deliveries, so `focus_note`,
    `memory_get_by_name` and `context_by_name` never fire on MCP. That is the route
    `feedback_mcp_first_agent_stm` tells the agent to use.
  - 19.2's `used_*` columns therefore count only the Bash-route uses.
- **The ACs cannot fail.** AC-1 and AC-4 spawn fresh subprocesses with a freshly set
  `CLAUDE_CODE_SESSION_ID`. No AC starts the server under id A and then switches the session to B.

**Why it's bullshit:** both specs make one environment variable the authority for "this session",
and in the process that serves most agent calls that variable is stale. The tests construct the
one case where it is fresh.

**Fix:**
- A session pointer keyed by the Claude process: the SessionStart hook (`startup|resume|clear`,
  `session_id` from its envelope) writes `<store>/stm/by-pid/<CLAUDE_PID>`.
- The MCP server resolves its session per call: that pointer (via `os.getppid()`) → `RMX_SESSION`
  → a skip that is printed. `CLAUDE_CODE_SESSION_ID` is trusted only in processes the harness
  spawns per call (hooks, the Bash tool).
- 19.0 R0's probe also records whether `CLAUDE_PID` and the CURRENT `CLAUDE_CODE_SESSION_ID`
  reach hook processes.
- R5 states, for every write verb, what happens when no session resolves (an error, never a
  dropped write).
- New AC (19.0 and 21.1): start `rmx mcp` with `CLAUDE_CODE_SESSION_ID=A`, then feed a
  SessionStart(`clear`) envelope for B. `rmx_focus_note` lands in B's ring, the `context-mcp` row
  logs B, and a note naming a memory delivered in B emits `used`.

**Pattern match:** YES. This is "the test builds the one case where the input is fresh" (r2's
replay-of-stored-data impression), and it is bug-100's shape again: a session guessed from
ambient state.

### BULLSHIT b-2: the `turn` race was fixed, its sibling phase inputs were not, and the phase classifier reads a graph the parallel input hook has already changed {#b-2}

**Where:** 21.1 R9 (`turn`), R10 (`stm_events_n`, `focus_topics_n`, `overlap`), AC-8, AC-8b;
19.6 R2, R3, AC-3.

**What:**
- **Same race, different fields.** 21.1 R9 correctly says the recall and scan hooks race
  `focus hook --event input`. But `Stm.record` ingests the prompt's refs into `focus.json` in
  the same call that appends the event ([[#evidence]]). So:
  - `stm_events_n` is n or n+1;
  - `focus_topics_n` and `overlap` are computed with or without this prompt's own terms in the
    graph.
  AC-8 asserts `stm_events_n == seeded ring's event count`, but AC-8 runs no parallel input hook,
  so it passes. In production the value flips by scheduling.
- **19.6 R2 has no mechanism.** It says the phase "reads the ring as it stood before the prompt;
  tests do not assume an ordering". There is no mechanism and no AC behind that sentence.
  `focus.json` is maintained in place and cannot be rewound by a `ts` filter. When the input hook
  wins, the prompt's own terms are already members of the active cluster, so the overlap with it
  is inflated and the prompt classifies `warm` by construction. The same applies to `return`
  against the cache. AC-3 uses static fixture rings.
- **`turn` itself is not race-free.** The rule `ts < t0 − 1 s` compares a float `t0` with a ring
  `ts` truncated to the second (`stm.py:259`). Truncation alone uses up to 1 s of the margin. For
  example, an input written at :10.95 reads :10.00, and a recall whose `t0` is :11.20 (start-up
  skew 0.25 s) counts it as an earlier prompt. The 1 s margin is also unmeasured: `cli.log`
  records only post-entry latency. AC-8b writes its event "ts = now" right before the run, so it
  sits inside the margin.

**Why it's bullshit:** the r2 fix closed one condition and left its siblings in the same
expression ([[feedback_check_the_sibling_condition]]). 19.6's whole verdict (Table C's
phased-vs-fixed lift) rests on a phase label that the race biases toward `warm`.

**Fix:**
- The input hook writes, before it ingests, a pre-turn snapshot `focus.pre.json` keyed by
  `sha256(prompt)` (atomic `os.replace`). Every prompt-time reader uses the snapshot when its
  prompt hash matches, and the current graph otherwise. `stm_events_n` is counted the same way
  (events before the snapshot mark).
- `turn` comes from the same mark (the input event stores its own ordinal and prompt hash; a
  reader takes the newest event with its hash, else `count`), not from a wall-clock margin.
- ACs: run AC-8b's before/after pair for ALL phase inputs, and add a 19.6 AC-3c that classifies
  the same prompt with the input event (and graph ingest) written before vs after: same phase,
  same `overlap`.

### BULLSHIT b-3: two AC-8 mutations cannot fail, and AC-8's scan-prompt leg cannot be built as written {#b-3}

**Where:** 21.1 AC-8, the mutation list (AC-12), R11.

**What:**
- **Five of seven emitters are untested.** The mutation "each surface's emitter removed, one at a
  time (AC-8)" claims a catch AC-8 cannot make. AC-8 runs `scan-prompt` and
  `memory recall --stdin-json` only. Nothing reads the events of `session_start`, `precompact`,
  `recall`, `context` or `nudge`:
  - AC-1/AC-2 check `query.log` rows only;
  - AC-10's "a recall" names no channel.
  `session_start` is the largest delivery channel (k = 30 under 19.1 R4), and 19.2 counts it.
- **The chars mutation is invisible on the recall leg.** "Offsets counted in characters (AC-8: …
  hooks contain `—`)" cannot fail there: the JSON renderer escapes non-ASCII ([[#evidence]]), so
  the payload is ASCII and bytes equal characters.
- **The scan-prompt leg has no events of the kind it asserts.** AC-8 seeds 10 memories in
  `intuition` and asserts `partition == "intuition"` on every event. scan-prompt never retrieves
  from `intuition` ([[#evidence]]), so that leg emits either no memory events (vacuous) or
  default-partition events (the AC fails on correct code).
- **No channel derivation rule.** The one recall emission site must pick `session_start`
  (`--session-start`), `prompt_recall` (`--stdin-json`), `precompact` (`--recent` under
  `RMX_INVOCATION_SOURCE=hook`, `hooks.py:340`) or `recall` (an agent's own `--recent` or query).
  No requirement states that rule.

**Why it's bullshit:** pre-registered mutations that cannot fail certify coverage that does not
exist.

**Fix:**
- State the channel rule in R11.
- Add an AC-8c that runs the GENERATED SessionStart and PreCompact argv, plus an agent
  `memory recall <q>`, an MCP `rmx_context` and the nudge, and checks the event set of each.
- Make the chars mutation target 19.1's `--pack` text (a non-ASCII payload), or assert on the raw
  `—` bytes of a `--pack` run.
- Seed scan-prompt's leg with code/doc items in the bound partition and assert THEIR `partition`.
  The memory case moves to [[#s-1]]'s rule.

### SKETCHY s-1: `kind` has no mapping from catalog kinds, and `context_by_name` excludes the common way context delivers a memory {#s-1}

**Where:** 21.1 R10 `kind`, R11, R12 `context_by_name`, AC-11b; 19.2 R3 (scan_prompt / context
memory deliveries count).

**What:**
- **No mapping, and no `concept`.** The event enum is `code`, `doc`, `memory`, `session`,
  `subject`. Catalog kinds are `function`, `class`, `concept`, `doc`, `memory`, … No mapping is
  given, and `concept`, which is what most scan-prompt anchors are, has no value.
- **The common path never counts.** `context.py:230-243` anchors a bare slug on the concept node
  and attaches the memory's body. That is the documented common case. R12 requires the anchor to
  have the delivered event's `kind`, so the agent reading a memory through `rmx context <slug>`
  is never a use.
- **Its delivery has no stated event.** R11 does not say what `delivered` event (name, kind,
  partition) that attached body produces. 19.2 R3 nonetheless counts scan_prompt/context memory
  deliveries.
- AC-11b tests only "anchor resolves to the memory".

**Fix:**
- A catalog→event kind table, with `concept` added or mapped.
- A memory body attached by `find_memory_any_partition` is a `kind=memory` delivered item, with
  `partition` taken from that row. `context_by_name` matches when the call delivered that memory
  body.
- AC-11e: the concept-anchor fallback case.

### SKETCHY s-2: 19.2's fold arithmetic: a plain-sum `merge_fn` cannot carry per-event decay, and "H can change without a rewrite" is false {#s-2}

**Where:** 19.2 R5 (`merge_fn` SUMS), R7 (fold-time decay; "`H` … read at read time, so `H` can
change without a rewrite"), AC-6, AC-17.

**What:**
- **Order and batching matter.** R7 decays every `recency_*` to each event's ts and then adds 1.
  That is per-event and order-dependent. 23.1 R4's `TailLog` coalesces by `key_fn`, and a plain
  SUM drops the per-event ts and the `min(ts)` that `first_seen` needs.
  - Recency then depends on batch boundaries, which depend on the tick budget.
  - Even with a decay-aware merge, the float summation order changes.
  - So AC-6's "identical rows" (and AC-5's "byte-identical") holds only when the replay happens
    to batch identically.
- **H is baked in at fold time.** The stored `recency_*` values already embed the fold-time `H`
  (the decay between events). Changing `H` at read time re-decays only the tail since
  `recency_ts`, so the result mixes two half-lives. AC-17 varies `w_e` and `base`, never `H`.
- **Clock-skewed events.** An event with `ts < recency_ts` (parallel appenders) decays "forward"
  and moves `recency_ts` backward.

**Fix:**
- `merge_fn` is decay-aware: the accumulator carries the per-kind count, recency at a reference
  ts, and `min_ts`/`max_ts`.
- `recency_ts = max`.
- AC-6 replays with two different batch sizes and compares recency within a stated tolerance
  (lifetime columns exact).
- R7 says a change of `H` is a drop-and-replay (the retained log allows it; ADR
  `#rule-two-records` "recomputed"), and an AC proves replay-under-new-`H` equals a fresh fold.

### SKETCHY s-3: `row_provenance` makes a sandbox fold drop its own events when cwd and root sit in different test bases {#s-3}

**Where:** 21.1 R5 class 1 ("`cwd` or `root` … the TEST BASE of EITHER differs"), AC-7; 19.2 R5,
AC-16, mutation "`cwd` ignored"; 23.0 R1/R2.

**What:**
- **Two test bases in one run.** 23.0 puts store roots under `/tmp/rmx-*`. pytest's `tmp_path`
  lives under `/private/var/folders/…/pytest-of-<u>/pytest-<N>`. In-process emission from pytest
  has cwd = the repo, whose test base is None.
  - Any test whose cwd is `tmp_path` or the repo, while its root is in the sandbox, makes the
    sandbox reader classify its own events `test_artifact`.
  - That is the opposite of R5's stated intent ("a sandbox test of 19.2's fold must fold its own
    events").
- **A sandbox reader drops live rows by that name.** A live row (test base None) read by a
  sandbox reader is "different", so it is labelled `test_artifact`.
- **A vacuous mutation.** 19.2 AC-16's extra event has BOTH `cwd` and `root` under pytest temp,
  so the "`cwd` ignored by the classifier" mutation survives on `root`.
- **`malformed` is not a return value.** AC-7's event leg says "classified by the same function:
  c–e are `malformed`", but `row_provenance` returns only four classes. The malformed rule then
  lives in each reader: the per-reader copy R5 forbids.

**Fix:**
- 23.0 sets pytest `--basetemp` inside the sandbox root, or class 1 keys on `root` and uses `cwd`
  only when `root` is absent.
- AC-16 adds an event whose `root` is in the sandbox and whose `cwd` is pytest temp, and states
  its expected class.
- Add `malformed` to `row_provenance` for events (a `source="events"` keyword).

### SKETCHY s-4: 19.6 R9's "byte-stable" collapsed line carries fields that change while its member set does not {#s-4}

**Where:** 19.6 R9, AC-7d; [[exploration-session-phased-context#tree-render]].

**What:**
- **Fields that move without a member change.** The collapsed line is
  `label (n events · L<a>–L<b> · id <cid>)`. `n events` and `L<b>` change whenever a non-selected
  cluster is re-touched without a membership change (a prompt term below the warm threshold, a
  tool ref).
- **A label that moves too.** The label is the head member by focus weight
  (`topic_composites` sorts by `weight`, `stm.py:790-813`), which can reorder while the member set
  is stable.
- **AC-7d holds the wrong thing fixed.** It changes "other clusters' event counts", not this
  cluster's, so the fixture passes.
- **No bound on line count.** "Every other cluster renders as ONE line" has no cap, so the
  composite grows with the session.

**Fix:**
- Define "unchanged" as member set + label frozen at snapshot.
- Drop or quantize `n events` and the range, or accept a new rev when they change and say so in
  Table A's measurement.
- Cap collapsed lines at k, in a stable order.
- AC-7d adds a re-touch of the collapsed cluster.

### MEH m-1: stale names, statuses and section numbers {#m-1}

- **Stale names.** The 19.1 title says "a character budget". plan-19 `#tasks` says
  `--max-chars`. Both are now `--max-bytes`.
- **Stale R-numbers.** plan-21 `#consolidations` cites "21.1 R6–R9" for the schema, and
  `#decisions` cites "d4a … 21.1 R6" and "d8e … 21.1 R7, R8". The schema is R8–R12.
- **Stale ADR wording.** 19.2 R7 and plan-19 open item 1 say the ADR amendment is "pending". It
  was approved at `3021cd6` (d9k).
- **Asserted floor set.** 19.2 R7's asserted floor omits ADR `#rule-asserted-floor`'s
  "user-asserted" class. Map it or say it equals `protected`.
- **Stale open items.** plan-21 open items 3 and 4 say "STILL OPEN … outside this pair's edit
  set". The same commit `69c5dc4` made both edits: the exploration's 34 / `-E` / reranker
  corrections, and plan-13's header and plan-of-plans row.
- **Ordering.** `#t10-waves` lists 21.1 and "19.5 R1 → 19.1 → 19.2" as parallel bullets. 19.1's
  header needs 21.1 R11 first, so state the edge.

### MEH m-2: 19.0 R1 assumes a terminated heredoc {#m-2}

R1 says the 600-char `DETAIL_MAX` cut "can only drop body text". For a parser that needs the
closing `EOF`, an unterminated heredoc (and a `-c '…` with an unbalanced quote) is read as COMMAND
LINE, so the cut ADDS junk. State the rule (an unterminated heredoc or quote runs to the end of
the string) and add an AC-1c case.

### MEH m-3: the chars-vs-bytes mutation fixtures need a stated multibyte density {#m-3}

19.1 AC-1 and AC-6 can let a char-counting packer through when the greedy slack exceeds the
fixture's multibyte excess. Require each fixture line to carry enough `—`/`→` that the excess
exceeds the largest whole-line slack, and record the pre-check that the mutation fails.

### MEH m-4: 19.0 rung 2 must be a structured match; R0 should record two more facts {#m-4}

- **Structured match only.** The spec does say "a `tool_use` block with `id == tool_use_id`".
  The early-stop byte scan in the cost bound must still not match on text: this review's probe
  found in-flight ids quoted inside another subagent's `tool_result` ([[#evidence]]). Add AC-4f:
  an id present only in another transcript's `tool_result` text gives no match.
- **Two more R0 measurements.** R0 should record whether the id is on disk at PostToolUse time
  (this review saw it there during the call), and the hook environment's `CLAUDE_PID` and session
  id ([[#b-1]]).

### MEH m-5: 19.6's compaction marker and arms have unnamed or undefined pieces {#m-5}

- **The marker has no writer.** No hook command in 19.6's Files writes R8a's marker. If 19.5
  R1(c) drops the PreCompact recall, the marker command must survive.
- **No arm for non-prompt channels.** `session_start` and `precompact` deliveries have no prompt,
  so R7's per-prompt `arm` is undefined for them.
- **Carryover is not stated.** Per-prompt arms share one context window (carryover between arms).
  Table C should say so as a known limit.

### MEH m-6: exploration stale wording (r2 m-6, carried) {#m-6}

`#shape`'s table still has the `shift` row (split into `return` / `new` below it), and
`#decisions` still lists placement and turn-as-tiebreaker, which d5b closed.

### MEH m-7: focus_note matcher edge cases {#m-7}

- **Sentence-final names.** The token class includes `.`, so a sentence-final `name.` never
  matches. That under-counts, which is the safe direction, but the spec should state it.
- **One name, two keys.** A name that matches two delivered keys (`memory` and `code`) has no
  stated event count.

### MEH m-8: 19.5 mixes a constant preview with a measured one, and "cap in bytes" is ambiguous for a char harness {#m-8}

- **Two previews.** R2's "before" uses a fixed 2 KB preview, while `seen` uses R1's measured
  `preview`. Use the measured one for both.
- **Which number is the byte cap.** If R1 finds the cap in characters, "the cap in bytes" must be
  the char-cap NUMBER taken as bytes (the conservative reading), not the byte length of the probe
  payload.

## Cross-plan consistency {#cross-plan}

| contract | plan-21 | plan-19 | verdict |
|---|---|---|---|
| session source | 21.1 R9: envelope → `CLAUDE_CODE_SESSION_ID` → `RMX_SESSION` | 19.0 R5: same | consistent with each other; both wrong for MCP ([[#b-1]]) |
| `delivered` owner | R11: one `emit_recall_events` site | 19.1 R8 spans only; 19.2 R3 | consistent |
| unit | R10 bytes | 19.1 R1 `--max-bytes`, `RMX_HOOK_BUDGET_BYTES`; 19.5 bytes | consistent. UTF-8 bytes ≥ chars ≥ UTF-16 units, so a byte budget is safe under any harness unit. 19.3's `MEMORY.md` cap stays in CHARACTERS: a different loader, which is correct per bug-045. Stale names: [[#m-1]] |
| channel enum | R10 closed enum | 19.2 R3 verbatim | consistent; derivation unstated ([[#b-3]]) |
| `kind` | R10 enum, no map | 19.2 counts `memory`; 19.2 R3 counts scan/context memory deliveries | **gap** ([[#s-1]]) |
| classifier | R5 `row_provenance` / `is_test_artifact_row`, owner `telemetry.py` | 19.2 R5; 21.4 R1; 23.0 AC-4 (valid call) | names consistent; sandbox semantics wrong ([[#s-3]]) |
| read-back evidences | R12 reserves `file_read` / `cited_in_answer` for 19.6 | 19.6 `score_readback.py`, never appends | consistent |
| phase inputs / `turn` | R9, R10 | 19.6 R2 | **both racy** ([[#b-2]]) |
| plan-23 names | — | 19.2 R5 `register(…, kind="tail")`, `TailLog`, `bind(partition_name)`, `queue_offsets`; R6 vs 23.1 R8 | consistent (verified in 23.1 R1.2, R4, R6, R8). `merge_fn` vs decay: [[#s-2]] |
| ADR-0004 | — | 19.2 R7 floor `base·(1+log1p(W))`, raw counts, read-time weights | matches the approved `#rule-floor` (d9k). `H` claim: [[#s-2]] |

## Open-after-revision items: who decides {#open-items}

### plan-19 {#open-19}

1. **ADR floor text:** SETTLED by d9k (`3021cd6`). Update the item and 19.2 R7's "pending".
2. **21.1's revision:** moot, closed.
3. **`used` weights:** settled (d9e).
4. **`replica_merge` offsets:** closed (23.1 R8).
5. **19.6 Tables A–D, the thresholds, N, K:** a real **user decision** (d9f), before 19.6 starts.
   Table D and the thresholds are part of it. Fix [[#s-4]] and [[#b-2]] first so the user confirms
   numbers for a well-defined classifier.
6. **19.2 constants:** settled (d9e).

New: the [[#b-1]] fix (a pid-keyed session pointer) is spec-settlable. The user should still be
TOLD that the MCP route's session attribution is broken today, because it changes what "MCP-first"
memory writes do under 19.0 R5.

### plan-21 {#open-21}

1. **Legacy rows, d9g:** settled.
2. **Scorer owner:** settled.
3. **Exploration corrections:** DONE in `69c5dc4`. Close the item.
4. **plan-13 pointer:** DONE in `69c5dc4`. Close the item.
5. **Channel enum:** settled.
6. **21.4 source:** settled (d9h).
7. **MCP tools beyond context and recall:** closed.

No plan-21 item needs the user. All of b-1, b-2, b-3 and s-1 through s-3 are spec work.

## Verdict {#verdict}

- **plan-19: NEEDS-REVISION.**
  - Prior: 15/18 r2 closed (b-5 and s-3 partial on the 19.2/19.6 side, m-6 partial), r1 partials
    closed.
  - New: [[#b-1]] (19.0 R5), [[#b-2]] (19.6 R2), [[#s-2]], [[#s-3]] (19.2 side), [[#s-4]],
    [[#m-1]], [[#m-2]], [[#m-3]], [[#m-4]], [[#m-5]], [[#m-6]], [[#m-8]].
- **plan-21: NEEDS-REVISION.**
  - Prior: the same 15/18 r2 closed; 21 r1 s-2 partial.
  - New: [[#b-1]] (21.1 R9/R12), [[#b-2]] (21.1 R10), [[#b-3]], [[#s-1]], [[#s-3]], [[#m-1]],
    [[#m-7]].

**15 new findings: 3 BULLSHIT, 4 SKETCHY, 8 MEH** (b-1, b-2 and s-3 span both plans).

The r2 seam (producer vs consumer) is closed field by field. What remains is runtime fact the
specs did not read:
- the MCP process's environment;
- the input hook's in-place graph write;
- the renderer's ASCII escaping;
- scan-prompt's partition.

rel: contradicts -> [[refmatrix/adr-0004-unified-location-space-index#rule-two-records]]

## Ledger entries (to merge) {#ledger}

### INDEX.md row {#ledger-index}

```
| 6091648 (plan-19 + plan-21 spec re-review r3, 19.0-19.6 + 21.1-21.4; written 2026-10-14T13:24:43-0700; HEAD moved to 097e7b1 during the run, no plan-19/21 file changed) | 2026-10-14 | Todd Holley / Opus 5.5 / spec-reviser (Wave 0 revision round 2) | DIRTY | 15 (3B/4S/8M) | [[bsd-plan19-21-spec-rereview-r3-6091648]]. NEEDS-REVISION both. Prior r2: 15/18 closed, 3 partial. MCP server's CLAUDE_CODE_SESSION_ID frozen at spawn (pid 59378 holds b38025a7, serves db80475a) yet 19.0 R5 + 21.1 R9 make it the session for every MCP verb/event -> focus_note/save_state into a dead ring, MCP `used` never matches; turn race fixed but stm_events_n/overlap/19.6 phase read a graph the parallel input hook already mutated (and ring ts is second-truncated); AC-8 mutations vacuous (5/7 emitters untested; JSON renderer is ASCII); kind map + context same-slug fallback; merge_fn sum vs per-event decay, H not read-time; row_provenance two test bases; 19.6 collapsed line not byte-stable. |
```

### last_run.log line {#ledger-last-run}

```
2026-10-14T13:24:43-0700 commit=6091648 verdict=DIRTY findings=15 (3B/4S/8M) report=2026-10-14-1324-plan19-21-r3-spec-rereview-mcp-session-and-racy-phase-inputs-6091648.md
```

### Impressions {#ledger-impressions}

- 2026-10-14 (p19/21 r3): **An env var is a snapshot of the process's birth.** Each Bash call
  gets a fresh `CLAUDE_CODE_SESSION_ID`, but the long-lived MCP server keeps the one it was
  spawned with, through every `/resume` and `/clear`. Before a spec names an env var as the
  authority, read it in the LONGEST-lived process that will consult it (`ps eww <pid>`).
- 2026-10-14 (p19/21 r3): **Fixing one racy field invites the reviewer to the others.** 21.1 fixed
  `turn`, and `stm_events_n`, `overlap` and 19.6's phase read the same mutated state. When a race
  is fixed, list every value computed from the racing write.
- 2026-10-14 (p19/21 r3): **Check the renderer before trusting a multibyte mutation.**
  `json.dumps` escapes non-ASCII by default, so a "chars vs bytes" mutation on a JSON payload
  cannot fail.
