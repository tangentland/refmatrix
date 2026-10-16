---
gmd: "0.1"
id: bsd-plan19-21-spec-rereview-32dde06
title: "plan-19 + plan-21 spec re-review: the ONE event schema still lacks the fields its fold keys and filters on, two 21.1 ACs contradict, and 19.0's subagent match and junk fix cannot pass on the real mechanism"
severity: BULLSHIT
plan: plan-19-adaptive-memory-budget, plan-21-agent-context-usage
task: spec-rereview-19.0-19.6-21.1-21.4
round: 2
tags: [bsd, audit, spec-review, re-review, recall-events, memory, stm, subagents, telemetry, plan-19, plan-21]
---

# ch-bsd spec re-review of plans 19 and 21 at `32dde06` {#root}

**Commit reviewed:** `32dde06` on branch `wave0-spec-reviews`. The tree was clean, and HEAD was
unchanged when this was written.
**Written:** 2026-10-14T12:42:12-0700.
**Scope:**
- plan-19 and tasks 19.0–19.6;
- plan-21 and tasks 21.1–21.4;
- the prior reviews [[bsd-plan19-spec-review-3104a81]] and [[bsd-plan21-spec-review-3104a81]];
- the items in [[bsd-decision-log-review-a192ba2]] that touch these plans;
- [[plan-review-2026-10-14]] (#t8 wins);
- [[exploration-session-phased-context]];
- ADR-0004 `#rule-floor` and `#rule-asserted-floor`;
- 23.1 R4, R6 and R8, which 19.2 consumes.

**Method:** everything was read-only. Every cited line was checked at HEAD; all of them hold
(`daemon.py:4687`, `:5238`, `:5855`, `:6286`; `cli.py:557`, `:5100`, `:5152`, `:5231`, `:6202`,
`:7521`, `:12695`, `:13950`; `stm.py:90`, `:106`, `:127`, `:840`; `verbs.py:528`, `:679`, `:731`,
`:766`; `consolidate.py:585`; `memory_index.py:275`, `:351`; and the 21.2 frozen-set lines).
I also ran these read-only probes:
- the frozen ring (sha256 `517fd359…` matches 19.0 R6; 502 lines);
- the 17 subagent transcripts and meta files of session db80475a;
- the live `.refmatrix/stm/*.inflight.json` keys;
- the field set of the project's `query.log`.

No `src/`, `tests/`, store, plan file or ledger was touched. No `rmx` command was run against a
store, and no suite was run.

rel: specifies -> [[plan-19-adaptive-memory-budget]]
rel: specifies -> [[plan-21-agent-context-usage]]
rel: derives-from -> [[bsd-plan19-spec-review-3104a81]]
rel: derives-from -> [[bsd-plan21-spec-review-3104a81]]
rel: derives-from -> [[bsd-decision-log-review-a192ba2]]
rel: related-to -> [[plan-review-2026-10-14]]
rel: related-to -> [[exploration-session-phased-context]]
rel: contradicts -> [[feedback_decay_never_loses_knowledge]]
rel: contradicts -> [[feedback_red_test_must_fail_at_head]]

## Live evidence {#evidence}

- **Subagent transcripts (d8h fact, verified).**
  - Location: `~/.claude/projects/<slug>/<session>/subagents/` holds 17 `agent-<id>.jsonl` plus
    `agent-<id>.meta.json` pairs. They persist after each agent finishes.
  - Meta keys: `agentType`, `description`, `toolUseId`, `spawnDepth`, `requestShape`,
    `requestNonInteractive`.
  - The decision-log review's meta reads `agentType: "ch-bsd"`,
    `description: "BSD review of decision log"`.
- **Tool duration vs the ±2 s window.** I measured all 699 tool_use→tool_result pairs in those
  transcripts:

  | statistic | value |
  |---|---|
  | p50 gap | 0.81 s |
  | p90 gap | 3.2 s |
  | p99 gap | 11.1 s |
  | max gap | 45.8 s |
  | pairs with gap > 2 s | 285 (41%) |
  | of those, Bash | 279 |

- **The exact join key exists.**
  - `cli._tool_call_key` (`cli.py:1893-1903`) already prefers the envelope's `tool_use_id`.
  - Every key in the live `*.inflight.json` sidecars is `toolu_…`.
  - The key parked in db80475a's sidecar during this run (`toolu_01VnbWdA7Wivs6CzM3TaabhH`, a
    subagent's call) appears verbatim in `subagents/agent-ae4639f357bfae20a.jsonl`.
- **Where the junk refs come from.**
  - For a Bash event, `cli._tool_event_fields` runs `stm._PATH_RE.findall(cmd)` over the WHOLE
    command, heredoc included (`cli.py:1922-1925`). `_PATH_RE` = `[\w./-]+\.[A-Za-z]{1,5}` matches
    `re.searc`, `r.get` and `collections.Count`. The refs are then stored on the event.
  - `_extract_refs` (`stm.py:840`) only runs when `refs is None`.
  - `Stm.rebuild_focus` (`stm.py:447-480`) reuses each event's STORED `refs`, filtered only by
    `is_junk_ref`.
  - The frozen ring has 46 tool events whose stored refs contain `r.get` / `re.searc` /
    `glob.glob` / `json.loads`.
- **`query.log` row fields today:** `answered_by body cardinality error invocation kind latency_ms
  learn outcome source ts`. There is no `session`, `cwd` or `root`: every existing row is
  "legacy".
- **ADR-0004 `#rule-floor`** still reads `floor base * log1p(hits + 2*used)` (`0004…md:251-252`).
- **23.1 R8** already defines the `queue_offsets` merge (the larger `offset_bytes` per
  `(queue, segment)`) and says folded tables carry their own rule (19.2 R6).

## Prior findings: status {#prior-status}

### plan-19 r1 ([[bsd-plan19-spec-review-3104a81]]) {#prior-19}

| id | status | evidence |
|---|---|---|
| b-1 subject noise | closed | 19.1 R2 default `exclude_mtype` adds `subject`; AC-3 with pre-check; mutation |
| b-2 env in argv | closed | 19.1 R1 built-in default; R4 no interpolation; AC-4 RUNS the argv unset; AC-8 no `$` |
| b-3 reachability by fiat | closed | 19.3 R4 executes each printed command (`--k <n>`; `memory list --limit` exists, `cli.py:11554`); AC-2 |
| b-4 zero floor | **partial** | 19.2 R7 `base·(1+log1p)`, virtual rows, AC-9, mutation. ADR-0004 `#rule-floor` text still says `log1p` with no owner (plan-19 open item 1) |
| b-5 coalesce / overflow / name | closed | 19.2 R5 tail reader, SUM `merge_fn`, no overflow, AC-3/4/7/11. The new key gap is [[#b-1]] |
| b-6 recall = use trap | **partial** | the op and internal `memory_get` are excluded (AC-2, mutation). The focus-note matcher is still unspecified, though the 19.2 revision table says "a specified matcher" ([[#b-5]]) |
| b-7 unsandboxed | closed | 23.0 everywhere; isolation ACs in 19.1–19.6 |
| s-1 PreCompact | closed | 19.5 R1(c); 19.2 R3, AC-13; 19.1 R4 |
| s-2 per-event cap | closed | 19.5 R1(b); 19.1 R1 per-event formula |
| s-3 arithmetic | closed | 19.1 R7, AC-2 (both k fixed, named prompt file, 19.5's baseline rule) |
| s-4 global / durability | closed | partition NAME, d8e route, drop-and-replay AC-6, R6 merge, `--scope global` pointer. The event schema lacks `partition` ([[#b-1]]) |
| s-5 asserted 91% | closed | d8b: the fold tier (19.3 R3) is separate from the floor. The floor consequence is [[#s-5]] |
| s-6 dependency cycle | closed | headers: 19.3 → 19.2 only; 19.4 → 19.3 + 17.2; 19.2 lists 23.1 and 21.1 |
| s-7 compile churn | closed | 19.4 R3, R5, R6, AC-4/5/6. New accretion: [[#s-6]] |
| s-8 concurrent writer | closed | 19.3 R8 (lock + `os.replace`), AC-7; 19.4 R2 memdir resolution |
| s-9 wall-clock render | closed | 19.3 R7 snapshot, AC-5 |
| s-10 placement | closed | 19.6 exists; 21.1 R10 carries the phase fields |
| m-1 … m-6 | closed | lines verified (`cli.py:12695`, `memory_index.py:351`); baselines frozen at RED; fallback removed; C11; `shlex.quote`; 19.5 R2 reads events |

**Totals:** 21 closed, 2 partial, 0 open.

### plan-21 r1 ([[bsd-plan21-spec-review-3104a81]]) {#prior-21}

| id | status | evidence |
|---|---|---|
| b-1 no session / join key | closed | 21.1 R4 and R9 (envelope → `CLAUDE_CODE_SESSION_ID` → `RMX_SESSION` → null); AC-4 with a newer third ring |
| b-2 id key, channel enum | **partial** | 21.1 R10 carries `name` and a surface enum. 19.2 R3 still lists `cli \| mcp` as channels; plan-21 open item 5 concedes it ([[#b-1]]) |
| b-3 no emitter / sink | closed | R8 sink; R11 named emitters; AC-8 through the GENERATED hook; AC-9 |
| s-1 delivered vs seen | **partial** | fields exist. 19.1 R8 emits no offsets, 19.5 R2 never derives `seen`, and the units clash ([[#s-2]]) |
| s-2 phase fields, `used` | **partial** | fields exist, but no AC checks them ([[#s-3]]); `used` emitters underspecified ([[#b-5]]) |
| s-3 AC-4 cannot fail | **partial** | frozen fixture, `--since/--until`, exact 3 / 1,119 / 34. It now contradicts AC-7 ([[#b-2]]) |
| s-4 `-E` not reproduced | closed | R6 retargeted to `grep-stdin`. `cli.py:6202-6208` sets no cardinality, so AC-5 is RED at HEAD |
| s-5 daemon route, `ann_search`, MCP tools | closed | R3 (four routes, `context-daemon`); R7 scope narrowed; AC-2 |
| s-6 agent stays unknown | closed | R2 precedence; AC-3 |
| s-7 live logs | closed | sandbox + live line-count assertions in every AC block |
| s-8 causal story | **partial** | plan `#why` and 21.4 `#why` corrected; the exploration is not (plan-21 open item 3) |
| s-9 C9 harness | closed | code + doc strata, n = 40, ≥ 3 net, no stratum loss; blind drafter + user approval |
| s-10 runtime artifacts | closed | 21.4 AC-4 greps generator output |
| s-11 TESTED BY | closed | 21.2 R3 `context.is_test_entity`; AC-5 |
| s-12 unfrozen replay | closed | 21.2 `#frozen-set`, lines verified at HEAD; hit defined; baseline-first AC-1 |
| s-13 latency | closed | 21.3 R0 wall clock, quiet + loaded, band table; 21.2 AC-6 |
| m-1 … m-7 | closed | R1 wording; flag not subcommand; `learn status`; sink is a file (23.0 dependency); C11; three parser inputs + 16.1 in header; d4e |

**Totals:** 18 closed, 5 partial, 0 open.

### Decision-log review items touching 19 / 21 {#prior-dl}

| id | status | evidence |
|---|---|---|
| b-1 (d5a reaps) | closed | d8a → 19.4 R5 marks `stale`; AC-4 row still exists; mutation |
| b-2 (d5c vs ADR) | closed | d8b → 19.2 R7 keeps the ADR definition; 19.3 R3 separate tier; no 22.2 dependency |
| b-6.1 (d4d last band) | closed | 21.3 R0 table, last row |
| b-6.3 (subject expansion) | closed | 19.6 out-of-scope, "not planned" |
| s-1 (d2a retention / merge) | closed | 21.1 R8; 19.2 R5, R6; 23.1 R8 |
| s-3 (tail reader, tick registry) | closed | 23.1 R4, R6; 19.2 R5 |
| s-4 (global route) | closed | 19.2 R4, AC-8 |
| s-8 (21.4 privacy / source) | **partial** | project log named; user confirmation pending (plan-21 open item 6) |
| s-9 (symbol set owner) | closed | 21.3 R6, AC-7 |
| s-10 (19.0 fixture / judged AC / probe / bug-100) | closed as asked | R0, R5, R6, AC-1/2. New defects in the same task: [[#b-3]], [[#b-4]] |
| m-1 (typo folds) | closed | 19.0 R4 (length ≥ 5, identifier-shaped exempt) |
| m-2 (`CLAUDECODE` precedence) | closed | 21.1 R2, AC-3 |
| m-6 (MEH ids) | closed | both revision tables enumerate them |

## Findings {#findings}

### BULLSHIT b-1: the ONE schema still does not carry what its main consumer keys, filters and routes on {#b-1}

**Where:** 21.1 R10 (the field table) vs 19.2 R1, R3 and R5, and 21.1 R5 / AC-7.

**What:**
- **No `partition` field.** 19.2 R1's primary key is `(partition_name, scope, name)`, and R3
  says every counted event "carries … `partition` (by name) … per 21.1's schema". 21.1 R10 has
  no `partition` field. The fold cannot compute its own key, except by guessing the bound
  partition, which is the bug-098 shape R5 forbids.
- **No `cwd` / `root` on events.** 21.1 R4 adds them to `query.log` rows only. R5's predicate
  keys on them, 19.2 R5 applies it to events, and 21.1 AC-7 asserts the same three rows "as
  events" are filtered. With R10 as written:
  - every event is `legacy_unattributed`;
  - d8d's filter on `recall-events.jsonl` can never fire;
  - test events that reach a live file land in a never-decaying counter.
- **Channel enum contradiction.** 19.2 R3 lists `session_start | prompt_recall | precompact |
  recall | cli | mcp`. 21.1 R10 says "`cli`/`mcp` are never channels". This is r1 #b-2's exact
  defect, unfixed on the 19.2 side (plan-21 open item 5).
- **No rule for non-memory events.** 19.2 does not say which channels or kinds count. 21.1
  emits `delivered` for `scan_prompt` and `context` items of kind `code`/`doc`, and scan-prompt
  also surfaces memory rows. As written, the fold either counts code and doc names into
  `memory_usage`, or silently ignores scan-prompt's memory deliveries. Neither is stated or
  tested.

**Why it's bullshit:** the 19.2 revision table says r1 #b-5 and d8d are answered at R5, and the
plan revision table says 21 #b-2 is answered. The fields those answers depend on do not exist in
the producer's schema. No AC in either task can fail on this, because 21.1's ACs never exercise
the fold and 19.2's ACs construct their own events.

**Fix:**
- Add `partition` (name), `cwd` and `root` to 21.1 R10.
- Set 19.2 R3's channel set to 21.1's enum. State the counted set as `kind ∈ {memory}` on
  channels {`session_start`, `prompt_recall`, `precompact` (gated), `recall`, `scan_prompt`?}.
  Deciding `scan_prompt` is a spec call.
- Add a cross-plan AC: events written by 21.1's REAL emitters (AC-8's run) are folded by 19.2,
  and land on `(partition_name, scope, name)`. A pytest-temp-cwd event is skipped and counted.
- Mutations: drop `partition` from the emitter; drop `cwd`.

**Pattern match:** YES. This is r1's "a shared schema is specced by its first consumer", now
inverted: the producer was fixed and the consumer was not re-read.

### BULLSHIT b-2: 21.1 AC-6 and AC-7 cannot both pass {#b-2}

**Where:** 21.1 R5, AC-6, AC-7; plan-21 open item 1.

**What:**
- AC-7 feeds one pytest-temp row, one project row and one legacy row, and expects "counts 1" with
  `legacy_unattributed=1`. So legacy rows are EXCLUDED from the totals.
- AC-6's fixture is a redacted cut of today's `query.log`, and every row in it is legacy: the
  live rows carry no `cwd`/`root` ([[#evidence]]), and the redaction scrubs paths. AC-6 requires
  EXACTLY 3 / 1,119 / 34.

Under AC-7's rule, AC-6 prints 0 / 0 / (34 from `cli.log`, if R5 does not apply there).
R5's prose ("prints them as a separate count instead of silently including or dropping them")
does not say whether legacy rows are in the totals.

**Why it's bullshit:** a correct implementation fails one of the two pre-registered ACs. The
implementer will bend whichever AC is RED last (the cheap-fix shape).

**Fix:** decide in R5:
- **Option A (recommended):** legacy rows ARE counted in the totals, and the report prints how
  many of them could not be screened. AC-7 then expects 2 counted, with `excluded_test_rows=1`
  and `legacy_unattributed=1`.
- **Option B:** add a shape rule (plan-21 open item 1). That one is the user's call.

Add the AC-6 / AC-7 pair to the mutation list: flip the legacy rule and one of them fails.

### BULLSHIT b-3: 19.0 rung 2 matches against the wrong timestamp and ignores the exact key, so long subagent calls fall back into the parent's focus {#b-3}

**Where:** 19.0 R2 rungs 2–3, cost bound, AC-4 / AC-4b / AC-4d; d8h.

**What:**
- **The window misses long calls.** The STM `tool` event is written at PostToolUse, after the
  tool finishes. The subagent transcript's `tool_use` entry is timestamped when the call is
  issued. 41% of this session's 699 subagent tool calls (279 of them Bash) took longer than 2 s
  ([[#evidence]]), so a ±2 s window misses them.
- **Rung 3 then sends them to the parent.** It says: "If no subagent transcript was written within
  the window, the event is the parent's". During a long Bash call the subagent's transcript is
  idle. So the call is attributed to `parent`, and its refs re-enter the parent's focus. That is
  bug-103 again, for exactly the long `python3`/heredoc calls the bug was about.
- **The cost bound excludes the same file.** It opens only files with mtime ≥ ts − W.
- **The exact key is ignored.** The PostToolUse (and PreToolUse) envelope carries `tool_use_id`.
  `cli._tool_call_key` already uses it, the live inflight keys are all `toolu_…`, and this run's
  subagent call id is present verbatim in its `agent-<id>.jsonl`. A by-id lookup needs no window
  and cannot over-attribute.
- **The ACs cannot see it.** AC-4/4b/4d use frozen timestamps and contain no call longer than W.
- **The AC-4 literal is wrong.** AC-4 expects `background: general-purpose: <description>`, but
  the fixture's subagent (the decision-log review) has `agentType: "ch-bsd"`. A correct
  implementation renders `background: ch-bsd: BSD review of decision log` and fails.

**Why it's bullshit:** this is the ladder the user asked for (d8h), and as specified it re-admits
41% of subagent calls to the parent. No AC can fail on that.

**Fix:**
- Rung 2 matches by `tool_use_id`: the envelope id equals a transcript `tool_use.id`, found by a
  bounded tail scan of the files modified since the parent's PreToolUse park time
  (`inflight_begin` records `t`).
- Digest + window become rung 2b, measured from the PreToolUse park time, not the PostToolUse
  time.
- Rung 3's "parent" fallback requires that no subagent of the session is RUNNING. Use meta
  presence plus no `tool_result` for an open `tool_use`, not mtime.
- Add AC-4e: a 10 s subagent Bash call is attributed `agent:<id>`, with a mutation that matches
  on PostToolUse time.
- Fix AC-4's literal to the fixture's `agentType`.

### BULLSHIT b-4: 19.0 R1 names the wrong mechanism, and its replay AC cannot fail on the defect it names {#b-4}

**Where:** 19.0 Why, R1, AC-1, AC-3, the mutation "extract refs from the heredoc body again",
Files.

**What:**
- **Wrong function.** The Why says `_extract_refs` "reads the whole tool `detail`". It does not.
  Bash refs come from `cli._tool_event_fields`, whose `_PATH_RE.findall(cmd)` scans the whole
  command, heredoc included. `_extract_refs` runs only when no refs are passed.
- **The ACs replay stored refs.** Every AC replays the frozen ring through `rmx focus rebuild
  --dry-run`, and `rebuild_focus` replays each event's STORED `refs`; it never re-extracts. The
  fixture therefore carries the junk as data (46 tool events in the raw ring).
- **Consequences:**
  - AC-1 goes green with a rebuild-time drop list (R1's stdlib-head and short-local set) alone,
    with no change to hook-time extraction.
  - The heredoc mutation is in a function the replay never calls, so it cannot fail AC-1 or AC-3.
  - The Files row ("`stm.py` `_extract_refs` command-line-only") points the implementer at the
    function that is not the cause.

**Why it's bullshit:** the AC certifies "script bodies are not focus" without exercising the code
that puts them there. That is a check that is true by construction ([[feedback_red_test_must_fail_at_head]]
holds for AC-3, but only because of the filter).

**Fix:**
- Correct the Why and Files to `cli._tool_event_fields` (`cli.py:1922-1925`).
- Add AC-1b: `rmx focus hook --event tool` fed a recorded heredoc PostToolUse envelope stores no
  body ref. Its mutation is the heredoc mutation.
- State whether `rebuild` re-extracts refs from `detail` (then AC-1 tests R1) or only filters
  (then AC-1 tests the code-noise set, and says so).

### BULLSHIT b-5: the `used` emitters that feed a never-decaying, double-weighted counter are still underspecified, and the 19.2 revision table says otherwise {#b-5}

**Where:** 21.1 R12, AC-11, Files; 19.2 R3, R7, and its revision row for 19 #b-6.

**What:**
- **No matcher.** `focus_note` is "`rmx_focus_note` naming it". There is no matcher (exact
  `name`? `[[name#anchor]]`? substring?) and no AC. Yet the 19.2 revision table claims
  "the focus-note signal is 21.1 R12's `focus_note` evidence, a specified matcher".
- **No lookup.** "Names an item delivered earlier in the same session" needs a lookup over
  `recall-events.jsonl` (and over the GLOBAL file for global memories). Neither its cost nor its
  read path is specified.
- **No route for global `used`.** R8 routes only "a hit on a GLOBAL memory" to the global file.
  A `used` event for a global memory has no stated destination, so 19.2 R4's project fold skips
  it as `scope=global` while the global fold never sees it.
- **Missing call sites.** Files-to-modify does not list the `memory get` CLI / MCP get action,
  the `focus note` path, or the CLI context route as `used` emitters.
- **One evidence tested.** Only `memory_get_by_name` has an AC and a mutation. `context_by_name`
  (a code name equal to a delivered name can collide with a memory name) and `focus_note` have
  neither.

**Why it's bullshit:** r1 #b-6 asked for exactly this ("specify the focus-note matcher … with
its own AC, or drop it"). It is marked answered and is not. Every false positive is a permanent
+2 in `lifetime_used` (R7 weight) and a raised floor, which ADR-0004 #rule-two-records keeps
exact forever.

**Fix:**
- Specify the `focus_note` matcher: exact `name` or `[[name…]]` tokens, same session.
- `context_by_name` counts only when the delivered event's `kind` matches.
- `used` for a global memory goes to the global file.
- Name the lookup: a per-session delivered-name set built from `recall-events.jsonl`, bounded.
- Add one AC and one mutation per evidence kind.
- Correct the 19.2 revision row, or drop `focus_note` until it is specified.

### SKETCHY s-1: who emits `delivered` for recall channels is claimed three ways {#s-1}

The three claims:
- 21.1 R11 has each recall surface emit `retrieved` AND `delivered`.
- 19.1 R8 says "trimmed hits stay `retrieved` only (21.1 already emits those)", and the packer
  emits `delivered`.
- 19.2 R3 says 21.1 emits "`retrieved`, `used`".

21.1's "19.1's pack joins later as an emitter" does not say whether it REPLACES 21.1's
`delivered` emission. 19.2 SUMS, so a double emission doubles `lifetime_hits`. 19.1 AC-6
(7, not 14) would catch an in-process double. The text should still say "replaces", 21.1 AC-8
should state which emitter is live after 19.1, and 19.2 R3 should be corrected.

### SKETCHY s-2: `seen` cannot be derived as specified: units clash, offsets are absent, and 19.5 never derives it {#s-2}

The gaps:
- **Units.** 19.1 R1 budgets in CHARACTERS (the bug-045 lesson). 21.1 R10 derives
  `seen = offset_bytes + bytes ≤ cap` in BYTES, against a cap whose unit 19.5 R1(a) has not yet
  measured. Multibyte payloads (`—`, `→`, which 19.1's own mutation fixture uses) diverge.
- **Offsets.** 19.1 R8's `delivered` events list `name`, `entity_id`, `scope`, `query_id`, with no
  `offset_bytes` / `bytes` / `payload_bytes`, and it does not say whether a hit's span is the hook
  line or the line plus its body.
- **19.5 R2.** It counts `delivered` against `retrieved` and never derives `seen`, although
  plan-21 `#consolidations` says "19.5 compares `delivered` with derived `seen`". Under a
  per-event cap, scan-prompt's tail is emitted but not seen.

**Fix:** carry offsets in the unit 19.5 R1(a) finds (or both units). Have 19.1 R8 emit the three
offset fields, with an AC. Have 19.5 R2 report `seen` per channel.

### SKETCHY s-3: 21.1's phase and versioned-injection fields have no AC, and `turn` is racy {#s-3}

The gaps:
- **No AC on the phase fields.** `stm_session`, `stm_events_n`, `focus_topics_n`, `overlap` and
  `block_id` / `block_sha` are "filled by 21.1's emitters now", but AC-8 asserts none of them.
  An emitter writing nulls passes. r1 #s-2's point was that history must be comparable from day
  one.
- **`turn` is racy.** It is "the count of `input` events in that session's ring at emission". The
  recall and scan hooks run in PARALLEL with `focus hook --event input` (`hooks.py:263-265`), so
  `turn` is n or n+1 depending on scheduling. Ambient prompts are never recorded (`cli.py`
  `focus_hook`), so `turn` is not the prompt ordinal either. `lag_turns` inherits both errors.

**Fix:**
- An AC-8 clause asserting the phase fields are non-null on prompt-time channels, and that
  `block_sha` equals the sha256 of the emitted block.
- Define `turn` as the count of input events strictly before this prompt's own (read before
  writing), or take it from the envelope's prompt id.

### SKETCHY s-4: 19.6 Table C cannot be computed against the baseline it names, and the phase thresholds are not pre-registered {#s-4}

The gaps:
- **Wrong baseline.** Table C scores "read-back citations per 1k delivered chars … against 19.5
  R4's fixed baseline". `baseline-fixed.json` holds delivered counts and sizes only (19.5 R4),
  with no read-back, so the fixed arm's metric does not exist in it.
- **Two definitions of read-back.** "A later tool call or answer cites an injected row" needs the
  transcript scorer (`file_read` / `cited_in_answer`), whose owner is open (plan-21 open item 2).
  "Re-measure after 19.2's `used` read-back exists" means 21.1's `used` events.
- **Confounding.** Arms are assigned per session, so topic and day confound the comparison.
  r1 #s-2 recommended a per-prompt logged arm.
- **No thresholds.** The classifier thresholds (warm overlap, return Jaccard) have no numbers in
  R0 or `#ranges`, so AC-3's fixtures pass for any threshold.
- **Expired anchor.** Table A's "else re-measure after 19.0" points at a hard prerequisite of 19.6
  that will already be done.

**Fix:**
- Run fixed as a live concurrent arm, assigned per prompt, and add read-back to the baseline (or
  drop the baseline from Table C).
- Name one read-back metric, and make 19.6's `eval/production/phased_context/` script the
  transcript scorer. That settles plan-21 open item 2.
- Pre-register the thresholds.
- Replace "after 19.0" with a concrete trigger.

### SKETCHY s-5: the revision's constants make the value score degenerate for ~91% of memories {#s-5}

19.2 R7 keeps ADR-0004's asserted definition, which includes `rel:`-anchored. 298 of 326 files
carry a `rel:` (r1 [[bsd-plan19-spec-review-3104a81#ev-rel]]), so their floor is
`asserted_floor = 1.0`, which equals one fresh delivery. Consequences:
- A memory delivered once (recency ≈ 1.0 decaying) never scores above an untouched anchored one.
- Only memories with ≥ 2 recent deliveries rise above the floor.
- 19.3 R2/R3 order within each tier by that score, so for most of the corpus the "value" order
  reduces to `created`, which is still not use.

The plan lists these constants (open item 6) as "not a user decision". They need the user's
confirmation, with this interaction shown. Alternatives:
- `asserted_floor` below one delivery (e.g. 0.5);
- the floor only for feedback/protected, with `rel:` as a smaller bonus. That needs an ADR
  amendment, which d8b avoided.

### SKETCHY s-6: hash-named subjects plus "mark stale, never remove" accrete protected, embedded rows nightly {#s-6}

19.4 R6 names an unlabeled cluster by a hash of its member set, and "a changed membership is a
different subject; the old one is marked stale". Effects:
- Every nightly compile in which any unlabeled cluster gains or loses one member mints a new
  protected, embedded subject row and strands the old one.
- Stale rows are hidden from recall by post-filter (`verbs.py:479/483`, filter then `[:k]`). They
  still occupy the dense candidate pool and the catalog.
- No plan-22 class is named that would ever review them.

The ADR forbids reaping them in compile (correctly). What is missing is an owner:
- a plan-22 removal class "stale compiled subject, 0 leaves, older than N days" (dry-run → apply);
- or exclusion from the vector index at mark time (no deletion; restorable by re-embedding);
- plus a growth AC.

### SKETCHY s-7: 21.3 R0's identifier set is drawn from a fixture whose bodies are hashed {#s-7}

R0 times the hook over "every identifier-shaped grep pattern in 21.1's redacted fixture". 21.1
AC-6 replaces bodies with their sha256, so the patterns are not recoverable from it. Either:
- draw R0's set from the local raw log, committing only its hash (d8f);
- or keep identifier-shaped bodies in the fixture, which is a privacy call: symbol names are repo
  content, not prompts.

### MEH m-1: wave and ordering slips {#m-1}

- 19.1 AC-3 ("a subject marked `stale` stays out") depends on 19.4 R5's `metadata.stale`
  (Wave 2), while 19.1 is Wave 1. Cite the field name and seed it in the fixture.
- 19.1 depends on 19.5 R1 (the probe), which no wave lists ([[plan-review-2026-10-14#t8-wave1]]).

### MEH m-2: the PreCompact verdict "recorded as a committed constant" is unnamed {#m-2}

19.2 R3 and AC-13 key on it. Name the constant and its module.

### MEH m-3: `first_seen` for a real `memory_usage` row is undefined {#m-3}

A virtual row uses frontmatter `created`, but the first fold could write the first event's `ts`.
Pick one, so AC-6's replay identity does not depend on an accident.

### MEH m-4: 21.4's redaction keeps question text {#m-4}

d8f and [[feedback_no_raw_prompts_in_public_repo]] say "prompts and paths scrubbed". 21.4 R1
keeps the question text, with the user's approval as the gate. That is defensible: these are
agent queries about this repo. State the exception in R1 and in the memory's terms.

### MEH m-5: "in the window" is undefined for a hook {#m-5}

19.6 R5/R6 and [[exploration-session-phased-context#vi-unchanged]] rely on "in the window". A hook
cannot see the window. Define it as "emitted since the last compaction marker this session
recorded", and name how compaction is detected (SessionStart `source=compact`, or the PreCompact
hook).

### MEH m-6: stale wording {#m-6}

- 21.3 R0's band table row 3 still reads "written at SessionStart / on derive", which contradicts
  R6's single writer. Annotate the row.
- The exploration's `#decisions` lists two items that d5b closed.
- The exploration's `#shape` still says `shift`.

## Cross-plan consistency {#cross-plan}

| contract | 21.1 | 19.x | verdict |
|---|---|---|---|
| field names | R10: `name`, `entity_id`, `kind`, `scope`, `session`, `query_id`; no `partition` / `cwd` / `root` | 19.2 R1/R3 need `partition`; R5 needs `cwd` / `root` | **conflict** ([[#b-1]]) |
| channel enum | surfaces only; `cli` / `mcp` never channels | 19.2 R3 includes `cli`, `mcp`; omits `scan_prompt`, `context`, `nudge` | **conflict** ([[#b-1]]) |
| `delivered` owner | R11: each surface; "19.1 joins later" | 19.1 R8: the pack emits; 19.2 R3: 21.1 emits retrieved / used | **ambiguous** ([[#s-1]]) |
| `delivered` payload position | R10 offsets in bytes | 19.1 R8 no offsets; 19.1 R1 chars; 19.5 no `seen` | **conflict** ([[#s-2]]) |
| `used` kinds | `context_by_name`, `memory_get_by_name`, `focus_note`; `file_read` / `cited_in_answer` reserved | 19.2 counts all at weight 2; 19.6 Table C uses transcript cites | **open** ([[#b-5]], [[#s-4]]) |
| `scope` routing | R8: global HITS → global file | 19.2 R4 global fold; `used` for global unrouted | **gap** ([[#b-5]]) |
| `is_test_artifact_row` | R5, owner `telemetry.py` (21.1), one copy; AC-7 import test | 19.2 R5 calls it; 21.4 R1 calls it | owner consistent. **Vacuous on events** ([[#b-1]]); legacy contradiction ([[#b-2]]) |
| `legacy_unattributed` | R5 / AC-7 (excluded from totals, implied) | not used by 19.x | **contradicts AC-6** ([[#b-2]]) |
| `turn` | R9 count of input events, logged only | 19.6 R2 / AC-7 never a signal | consistent; racy ([[#s-3]]) |
| phase / arm enums | `cold\|warm\|return\|new`; `fixed\|phased\|phased+cache` | 19.6 R2, R7 | consistent |
| retention / tail | R8 never rotated; tail stops at newline | 19.2 R5; 23.1 R4 | consistent |
| `replica_merge` | — | 19.2 R6 counters; 23.1 R8 offsets (max) | consistent: settles plan-19 open item 4 |

## Open-after-revision items: who decides {#open-items}

### plan-19 {#open-19}

1. **ADR floor text:** spec-settlable. The nonzero floor was taken in `#t5-fixes`. The revision
   should amend ADR-0004 `#rule-floor` itself (with `rel: amends`) and name 19.2 as the owner. The
   user signs the ADR diff; no new decision is needed.
2. **21.1's uncommitted revision:** moot. 21.1 is committed at `32dde06`, and R5 / R8 / R11 / R12
   are as cited. The contract still mismatches ([[#b-1]]), and that is spec work.
3. **`used` evidence weights:** spec-settlable. Keep exact per-evidence lifetime counts
   (`lifetime_used_by_evidence`), so the weight is a read-time parameter (ADR #rule-two-records);
   default 2 for all. It is the user's only if they want unequal weights now.
4. **The `replica_merge` offset row:** already settled by 23.1 R8. Close it.
5. **19.6 bands, N = 8, K = 8:** **user decision.** These are pre-registered go/no-go numbers, the
   same class as d4d. The revision proposed them; the user must confirm them before R1 runs. Add
   the phase thresholds ([[#s-4]]).
6. **19.2 R7 constants (`base = 0.25`, `asserted_floor = 1.0`, weights 1/2):** **user decision**,
   given [[#s-5]]'s interaction. The plan text "not a user decision" should become "pending user
   confirmation".

### plan-21 {#open-21}

1. **Legacy rows without `cwd`:** the AC-6 / AC-7 consistency is spec-settlable ([[#b-2]], Option
   A). Excluding the 235 global `alpha|beta` rows by SHAPE is a new filter heuristic: **user
   decision**.
2. **Owner of the transcript scorer:** spec-settlable. Make it 19.6's Table C script ([[#s-4]]).
3. **Exploration corrections (s-4, s-8, "68 → 34"):** spec-settlable doc edit; no decision.
4. **plan-13's pointer:** spec-settlable doc edit (plan-13 header and plan-of-plans row).
5. **19.2 R3 channel enum:** spec-settlable. It was taken without a decision in `#t4-fixes`, and it
   is still open ([[#b-1]]).
6. **21.4 source = the project log only:** **user decision** (privacy; decision-log #s-8).
7. **MCP tools beyond context and recall:** settled by the narrowing (r1 #s-5, option 1). Close it,
   unless the user wants more.

## Verdict {#verdict}

- **plan-19: NEEDS-REVISION.**
  - Prior: 21 of 23 closed, 2 partial.
  - New: [[#b-3]], [[#b-4]] and [[#b-5]] (19.2 side), [[#b-1]] (19.2 side), [[#s-1]], [[#s-2]],
    [[#s-4]], [[#s-5]], [[#s-6]], [[#m-1]], [[#m-2]], [[#m-3]], [[#m-5]].
- **plan-21: NEEDS-REVISION.**
  - Prior: 18 of 23 closed, 5 partial.
  - New: [[#b-1]] (schema side), [[#b-2]], [[#b-5]] (emitter side), [[#s-1]], [[#s-2]], [[#s-3]],
    [[#s-7]], [[#m-4]], [[#m-6]].

**18 new findings: 5 BULLSHIT, 7 SKETCHY, 6 MEH** (b-1, b-5, s-1 and s-2 span both plans).

Most r1 blockers did close. What remains is concentrated in two places:
- the 19.2 ↔ 21.1 seam: the producer was revised, and the consumer was not re-read against it;
- the new task 19.0: both of its mechanisms were specified from a story about the code, not from
  the code or the transcripts.

rel: contradicts -> [[refmatrix/adr-0004-unified-location-space-index#rule-two-records]]

## Ledger entries (to merge) {#ledger}

### INDEX.md row {#ledger-index}

```
| 32dde06 (plan-19 + plan-21 spec re-review r2, 19.0-19.6 + 21.1-21.4; written 2026-10-14T12:42:12-0700) | 2026-10-14 | Todd Holley / Opus 5.5 / spec-reviser (Wave 0 revision) | DIRTY | 18 (5B/7S/6M) | [[bsd-plan19-21-spec-rereview-32dde06]]. NEEDS-REVISION both. Prior: p19 21/23 closed, p21 18/23 closed. 21.1 R10 lacks partition/cwd/root that 19.2 keys + d8d filters on; 19.2 R3 still cli/mcp channels; 21.1 AC-6 vs AC-7 legacy-row contradiction; 19.0 rung-2 ±2 s misses 41% of subagent calls (tool_use_id exists, unused) and rung 3 re-admits them to parent; 19.0 R1 blames _extract_refs but junk comes from cli._tool_event_fields and replay reuses stored refs; used-evidence matcher still unspecified. |
```

### last_run.log line {#ledger-last-run}

```
2026-10-14T12:42:12-0700 commit=32dde06 verdict=DIRTY findings=18 (5B/7S/6M) report=2026-10-14-1242-plan19-21-spec-rereview-schema-consumers-and-subagent-window-32dde06.md
```

### Impressions {#ledger-impressions}

- 2026-10-14 (p19/21 r2): **A fixed producer does not fix its consumer.** 21.1's schema closed
  r1's b-1/b-2. 19.2 still keys on `partition` and filters on `cwd`, which the schema never got,
  and it still lists `cli`/`mcp` channels. On a re-review, diff every consumer's field list
  against the producer's table, field by field.
- 2026-10-14 (p19/21 r2): **A replay of stored derived data cannot test the code that derived
  it.** 19.0's AC replays a ring whose `refs` were computed at hook time. A hook-time fix is
  invisible to it, and a rebuild-time filter passes it. Always add one AC through the production
  write path.
- 2026-10-14 (p19/21 r2): **Measure the window before you specify it.** ±2 s looked generous, but
  41% of subagent tool calls run longer, and the exact `tool_use_id` key was already in the code.
  Check for an existing join key before designing a fuzzy one.
