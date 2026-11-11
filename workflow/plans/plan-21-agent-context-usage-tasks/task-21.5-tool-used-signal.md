---
gmd: "0.1"
id: task-21.5-tool-used-signal
title: "Task 21.5: a tool-level `used` signal: derived at report time by joining each session's delivered events with its STM tool events on a prompt clock, never emitted by a hook, reported per channel as credited (tool call, file) units over eligible units, with every exclusion counted"
tags: [task, plan-21, telemetry, recall-events, used, stm, agent-usage]
metadata:
  node_type: task
  status: pending
  plan: plan-21-agent-context-usage
  created: 2026-11-11
  updated: 2026-11-11
  revision: 2
---

# Task 21.5: a tool-level `used` signal {#root}

> Plan: [[plan-21-agent-context-usage]]
> Status: Pending. Rev 2 (2026-11-11) answers ch-bsd spec review r1 (DIRTY 18) and its addendum
> against 24.6 r5 ([[#rev-2]]). It needs a spec re-review before it can be approved.
> Wave: now. The user prioritised it on 2026-11-11, after reading `rmx telemetry --agent-usage`.
> Depends on: 21.1 (completed: the ONE recall-event schema, `emit_recall_events`,
> `delivered_in_session`, R12's three explicit evidences, the `--agent-usage` report), and 23.0
> (completed: the shared test sandbox).
> Touches the interfaces of 19.0 R2 and 19.2 (pending), 19.6 (pending), 24.6 (pending; amended
> to r6 in the same change as this revision) and 25.1 (pending). [[#open-for-user]] lists what
> still needs the user.

rel: part-of -> [[plan-21-agent-context-usage]]
rel: depends-on -> [[task-21.1-context-usage-telemetry]]
rel: depends-on -> [[task-23.0-test-sandbox]]
rel: amends -> [[task-21.1-context-usage-telemetry#req-schema]]
rel: related-to -> [[task-19.0-stm-cluster-hygiene#requirements]]
rel: related-to -> [[task-19.2-memory-usage-record]]
rel: related-to -> [[task-19.6-phased-context-and-topic-cache]]
rel: related-to -> [[task-24.6-context-and-observation]]
rel: related-to -> [[task-25.1-recall-hook-byte-budget]]
rel: related-to -> [[task-24.0-hook-cost-baseline]]
rel: derives-from -> [[bsd-plan19-21-spec-rereview-32dde06]]
rel: derives-from -> [[bsd-task-21.5-spec-r1-15e8f64]]
rel: reinforces -> [[feedback_no_silent_failures]]
rel: reinforces -> [[feedback_go_no_go_ranges_not_predrop]]

## Why {#why}

Since 2026-11-10, the user's run of `rmx telemetry --agent-usage` gave these funnels. scan_prompt:
2,051 retrieved, 1,733 delivered, 9 used. prompt_recall: 1,200 retrieved, 338 delivered, 0 used.

Under 21.1 R12, `used` fires only on an explicit agent or MCP call that names something the
session was delivered: `memory get <name>`, `context <name>`, or a `focus note` that contains the
name. Hook calls never emit (R12's helix rule). In practice, the agent acts on a delivered hit by
Reading, Editing or running a command on the delivered file, or by naming a delivered item in a
later tool input. None of that is visible today. So "9 of ~2,100" is a floor, not a usefulness
rate.

The signal is mostly on disk already. The PostToolUse focus hook records every matched tool call
into the session's STM ring (`rmx focus hook --event tool`, `cli.py::focus_hook`). Each delivered
event names an item whose file the catalog knows. This task makes the ring carry what the join
needs, records the item's file on each event, and joins the two at report time. It emits no new
event, and it does not reopen R12's hook rule.
{#why-body}

### What the data says (rev 2 prototype) {#why-data}

r1's review found three legs dead on contact with a 40-line join over scratch copies
([[bsd-task-21.5-spec-r1-15e8f64#imp-prototype-the-join]]). Rev 2's join was re-run the same way
before this text was written: APFS clones of this project's `recall-events.jsonl`, `query.log`,
`stm/*.jsonl` and `catalog.read.duckdb`, plus the global events file, under a `mkdtemp()` root,
deleted afterwards. Window 2026-11-10T00:00Z to the copy (2026-11-11 ~13:30 local). Only counts are
recorded; no prompt, command or body was printed. The prototype is rough (no `t_start`, legacy
ordering only), so these numbers show direction, not the shipped result.
{#why-data-method}

| measure | count |
|---|---|
| prompts on the prompt clock ([[#r4]]) / ring `input` lines | 95 / 82 |
| prompts the clock holds with a prompt-recall row but no scan row | 4 |
| delivered events (project file + 6 from the global file for this root) / `precompact` gated | 2,440 / 20 |
| delivered units ([[#d7]]) over the remaining 2,420 events | 2,144 |
| prompt-time deliveries anchored to their own prompt by `query_id` | 2,366 of 2,366 (no anchor race) |
| delivered items whose path came from `Entity.path` / a memory's `source_path` / a grep-floor name | 1,582 / 396 / 45 |
| delivered items with no path: entity has none / memory has no `source_path` | 293 / 104 |
| credited units: scan_prompt / prompt_recall / recall (agent) | 57 / 1 / 4 |
| of those, `prior_touch` (the file was touched before the delivery) | 44 |
| credited units with no prior touch (the headline numerator, [[#d8]]) | 18 |
| `lag_turns` of the first match: 0 / 1 / 2 / `>W` | 40 / 11 / 11 / 63 |
| credited strata: Bash `bash_path` / Bash `bash_name` / Read, Edit, Write `path` | 35 / 27 / 0 |
| Read / Edit / Write ring events: under this project / under `/Volumes/littlebig/` / elsewhere | 14 / 269 / 65 |
| ring tool events: Bash / Read / Write / Edit / Grep, Glob, Agent, `mcp__*` | 3,475 / 134 / 109 / 105 / 0 |
| control units ([[#r7]]) / touched | 722 / 6 |

Three facts follow. The Bash legs are the whole signal at present. Most Read/Edit/Write calls in
this project's sessions touch paths under `/Volumes/littlebig/`, not this tree, so they cannot
match (counted, [[#d12]]). And most credits are prior-touch, which is why the headline excludes them.
{#why-data-reading}

## Decisions this task carries {#decisions}

1. **D1: derive at report time; never emit at hook time.** {#d1}
   - **Cost.** About 75% of hook rows are `focus hook --event tool/tool-pre` pairs, one pair per
     tool call (`telemetry.py`, the hook-budget comment, ch-bsd r1 #b-7). Emitting at hook time
     would run R12's delivered-set lookup on every PostToolUse. That lookup reads backwards up
     to 4 MB from each of two files. Today the hook does one append and one graph
     read-modify-write. The only way to make the lookup cheap is a per-session cache that the
     hook maintains. That cache would be a second delivered-set source, a "two ways to do X" the
     overlay forbids.
   - **What is NOT the argument.** The event file is appended lock-free (d4a), so emission never
     goes through the daemon's single writer. bug-177's writer contention does not apply. The
     cost is the read.
   - **Correctness.** R12's invariant "no `used` from `invocation=hook`" stays literally true. So
     does 19.2 AC-2, the fold's test of it.
   - **Reproducibility.** The ring is append-only and never trimmed (`stm.py`, `Stm.record`).
     The event file is retained until folded (C7). So the derivation can be re-run whenever the
     matcher, the window or the Bash rules change.
   - **What it costs.** No live consumer can read the signal. None needs to yet ([[#d4]],
     [[#od-3]]).
   - **The mod follows the same rule.** 24.6 r5 (the user's decision on r1's OD-1) and r6:
     the mod's `tool.call` observe writes ring fields and RAW `result_mentions`; it emits no
     `used` and makes no delivered-set read ([[#d10]]).
2. **D2: the STM ring is the source, not the transcript.** {#d2}
   - The ring is refmatrix's own primitive. It is keyed by the same Claude session id as the
     events (R9's resolver), and both the shell hook and 24.6's mod observe write it.
   - The transcript is Claude Code's internal format. It lives outside the store root and holds
     raw prompts (d8f). It is read only by R12's labeller, locally.
   - **What the ring lost, and the fix (m-1, x-1).** Before this task the matcher's inputs lived
     in `detail`, a JSON string cut at `stm.DETAIL_MAX` (600); 16% of live Bash details reach
     the cut. [[#r1]] stores the matcher's inputs as their own fields, each with a larger cap
     and a truncation count. `detail` is unchanged.
3. **D3: delivered events carry the item's `path`; `v` stays 1 (b-1).** {#d3}
   - Matching a Read or Edit needs the delivered item's file. The event carries `name` and
     `entity_id` but no path. Resolving it at report time from the catalog would follow 26.2's
     moves (a file moved after delivery would no longer match the Read made before the move),
     and the emitter already holds the item, so it records the path at emission.
   - **Why no schema bump.** r1 proposed `v: 2`. A version bump is decided by its classifier,
     not by its tuple ([[bsd-task-21.5-spec-r1-15e8f64#imp-version-bump-meets-classifier]]):
     `telemetry.row_provenance` classifies `v != 1` as `malformed` (`telemetry.py:1727`), every
     reader of the events goes through it (21.1 R5, 19.2 AC-16), and two 21.1 tests pin it
     (`tests/test_task21_1_agent_usage_report.py:238` lists `{"v": 2}` as malformed;
     `tests/test_task21_1_emitters.py:204` asserts `v == 1`).
   - **The smaller correct change.** `path` is ADDED to `RECALL_EVENT_FIELDS_V1` and `v` stays 1.
     The bump bought one thing: telling "written before this task" from "the item has no path".
     The key's PRESENCE already tells them apart, durably:
     - `emit_recall_events` writes every field of the tuple, null allowed (21.1 R10;
       `telemetry.py:1320`), so every event written after this task HAS the `path` key;
     - every event written before it LACKS the key;
     - the file is append-only and never rewritten (21.1 R8, 19.2 R5), so absence cannot be
       erased by a later writer.
   - **What does not change.** `row_provenance`, `_EVENT_REQUIRED`, both 21.1 tests and 19.2's
     fold. `path` is not required. A reader reads `"path" in ev` (legacy when absent,
     [[#r10]]) and `ev["path"] is None` (no path, [[#r9]]). A bump would have changed the ONE
     classifier, two pinned tests and 21.1's R5 and R10 to carry no information the key does
     not.
   - **Recorded in 21.1.** 21.1 R10's field table gains a `path` row (null allowed; absent on
     events before 21.5) in the same commit as the code ([[#files-to-modify]]).
4. **D4: 19.2 counts none of it until it is measured.** {#d4}
   - Derived `tool` records never enter `recall-events.jsonl`, so 19.2's fold never sees them.
   - 19.2 R1's route for a new evidence kind still holds: a migration adds its own column. That
     route opens only after [[#r12]]'s precision band says so. The column's weight comes from
     the measured precision, never the `w_e: 2` default (19.2 R7; 32dde06 item 3 made the
     weight a read-time parameter).
5. **D5: no new verb, command or flag.** {#d5}
   - `telemetry` is a `harness` entry in `verbs.LEGACY_UNPAIRED`, and `--agent-usage` already
     exists. This task adds report lines and no agent-callable capability, so verb parity and
     the generated CLI tree do not change.
   - The window `W` is a committed constant, not a flag ([[#r4]]). The report function's
     `logical_root` is a function parameter for AC-15, not a CLI flag ([[#d11]]).
6. **D6: the Agent / Task and `mcp__refmatrix__` legs stay, marked "live from 24.6 R4" (b-3).**
   {#d6}
   - The generated Pre/PostToolUse matcher is `Edit|Write|MultiEdit|NotebookEdit|Read|Bash|Grep|Glob`
     (`hooks.py:292,296`), so the shell hook never records an Agent or MCP call. The live ring
     holds none.
   - **Lead decision (as the user would).** Keep both legs; do not widen the shell matcher.
     24.6's mod observes every tool call, main loop and subagents, with `agentId`, and r6
     widens its `tool.call` row to every tool and tests an Agent call and an
     `mcp__refmatrix__` call reaching the ring ([[task-24.6-context-and-observation#rev-r6]]).
     Widening the shell matcher would add a hook process to every Agent and MCP call for a leg
     the mod gives a producer anyway.
   - **Until 24.6 ships.** The report never prints those legs as zero use. A leg whose tool is
     not in the shell matcher and has no ring events in the window prints
     `not-yet-producing (shell matcher excludes it; live from 24.6 R4)`, with its event count,
     and its rate is `n/a`, never `0`. The matcher list is read from ONE constant,
     `hooks.FOCUS_TOOL_MATCHER`, that the hook generator also uses; the generated output does not
     change.
   - **The legs are tested where they can be.** [[#ac-7]] tests both legs through
     `tool_touches`, labelled as unit legs. The end-to-end producer test is 24.6 r6 AC-3.
     [[#ac-16]] tests the `not-yet-producing` line against the real generated matcher.
7. **D7: the credit unit is one (tool call, file) (s-2).** {#d7}
   - One Read of a bsd report credited 7 delivered anchors of that file in r1's prototype, and
     833 of 927 delivered concepts have a path (mostly GMD anchors of workflow docs). Crediting
     per delivered event counts one act many times.
   - **Lead decision.** A **delivered unit** is `(session, prompt, channel, file)` for items
     with a path, and `(session, prompt, channel, key)` for items without one (`key` = `name`,
     `kind`, `scope`). Every delivered anchor of a file in one prompt on one channel is one unit.
     A tool call `T` that touches file `F` credits at most one unit per channel: the unit of `F`
     from the most recent delivering prompt at or before `T`'s prompt. A Bash touching two
     delivered files credits two units.
   - The report prints `units` and `anchors_in_units` beside each other, so the collapse is
     visible. The prototype gives 2,420 eligible events in 2,144 units.
8. **D8: the headline excludes prior-touch; both numbers are printed (m-7).** {#d8}
   - A file the agent touched before the delivery and touches again after it is weak evidence
     that the delivery caused the second touch. In the prototype, 44 of 62 credited units are
     prior-touch.
   - **Lead decision.** `rate_headline = used_headline / eligible_units`, where `used_headline`
     counts units used explicitly (R12) or credited by a tool call with `prior_touch = no`.
     `rate_incl_prior` (prior-touch credits included) is printed on the same line. Neither is
     hidden.
9. **D9: a prompt is one UserPromptSubmit, ambient included, read from query.log (s-1).** {#d9}
   - r1 counted ring `input` lines. The input hook writes none for ambient prompts (agent
     messages, task notifications; `cli._is_ambient_prompt`), so r1's `W = 2` meant two
     non-ambient prompts plus any number of ambient ones. And the input line is written after
     the parallel scan-prompt may have delivered (r1's `anchor_race`).
   - **What every prompt leaves.** Each UserPromptSubmit runs the scan-prompt hook and the
     prompt-recall hook, ambient or not. Each writes one `query.log` row per call with `session`,
     `query_id` and `invocation = hook`, on success, on empty results and on error. Each
     prompt-time delivered event carries its call's `query_id`.
   - **Decision.** The session's prompts are its **prompt-clock rows** (`kind = scan`, or
     `kind = recall` with neither `session_start` nor `recent` set; `invocation = hook`, or the
     mod's `hook_event = UserPromptSubmit`), grouped into prompts ([[#r4]]). A prompt-time
     delivery belongs to the prompt of its own row, found by `query_id`, so it cannot race its
     prompt. Ambient prompts count, because they are prompts the agent responded to.
   - **Why not write an ambient line to the ring.** It would change 21.1 R9's `events_n` (a raw
     line count every prompt-time event records) and the timeline readers, both outside this
     task. query.log already holds the prompt.
   - **Measured.** 95 prompts on the clock against 82 ring `input` lines; every paired scan and
     prompt-recall row starts within 0.8 s of its partner; 4 prompts have a prompt-recall row
     and no scan row, so the clock uses both kinds.
10. **D10: `result_mentions` is a reserved ring field; the matcher ignores it (x-3, x-4).** {#d10}
    - 24.6 r6's observe records the delivered names it found in the tool's result text RAW, as
      `result_mentions`, pre-filtered only by the mod's `$.state` (`refmatrix.delivered`). It
      does not call `delivered_in_session`: that would be the per-tool-call backward read D1
      rules out, and `$.state` would become the second delivered-set source D1 forbids.
    - This task's report counts ring events that carry the field (`result_mentions_present`)
      and does not match on it. A `match_on: tool_result` leg that checks those names against
      the delivered events at report time joins [[#r3]] only after it is measured against
      [[#r12]]'s bands, in its own task.
11. **D11: the report resolves paths against a logical root (s-4).** {#d11}
    - The ring stores no `root`; pre-task Bash lines store no `cwd`; and R8's global-file filter
      compares each event's recorded `root` with the reader's. Run against a clone (AC-15), the
      reader's root is the clone's `mkdtemp()` dir, so relative refs miss (58 of 58 first
      touches in r1's prototype were Bash) and the global filter returns nothing.
    - **Decision.** `agent_usage_report(root, *, logical_root=None, ...)`: `logical_root` defaults
      to `root`. It is the root the logs were WRITTEN for. The global filter compares
      `norm_path(event.root)` with `norm_path(logical_root)`; a relative Bash ref with no `cwd`
      resolves against `logical_root`'s parent (the project dir), counted `cwd_fallback`. The
      files are read from `root`. Production never passes it; AC-15 passes the live root's path
      as a string and opens nothing under it.
12. **D12: paths outside the project are counted, not matched.** {#d12}
    - In the prototype, of 348 Read/Edit/Write events, 14 touched this project, 269 a path under
      `/Volumes/littlebig/` (where this project's isolated write work runs, in
      `<project>-<worker>` clones) and 65 somewhere else. A clone's copy of a file is a different
      path from the delivered item's. Which loop issued those calls was not measured (no ring
      line carries `origin` yet).
    - **Decision.** No clone or repo-relative leg. Tool-event refs outside `logical_root`'s
      project dir are counted per tool (`refs_outside_project`), so the gap is visible. A
      repo-relative leg would need a "same repository" test and its own precision measurement.
      When `origin` exists ([[#d13]]), the report splits `refs_outside_project` by origin, which
      says whether a clone leg would mostly credit subagents (false by construction) before
      anyone builds one.
13. **D13: subagent tool calls are labelled by `origin`, one field (s-3, x-2).** {#d13}
    - A background subagent's PostToolUse carries the PARENT's `session_id`, so its tool events
      land in the parent's ring. It never saw the parent's delivery, so a credit from it is
      false by construction.
    - **Lead decision.** The ring records `tool_use_id` and ONE origin field, named `origin` as
      19.0 R2 names it ([[task-19.0-stm-cluster-hygiene#requirements]]): `parent`,
      `agent:<agentId>`, or `unattributed`. 24.6's mod writes `agent:<agentId>` from the event's
      `agentId`, else `parent`. The shell hook writes `agent:<agent_id>` only when the envelope
      itself carries `agent_id` (19.0 R2's rung 1, whose presence 19.0 R0 measures), and
      otherwise writes NO `origin` key; 19.0 R2's rungs 2 and 3 fill it when 19.0 ships. This
      task builds no ladder.
    - **The join.** `parent` credits. `agent:*` credits nothing, counted `subagent_tool_events`.
      `unattributed` credits nothing, counted `origin_unattributed`. An absent `origin` credits
      and is counted `origin_unknown`, and the footer says the rate includes subagent tool
      calls whose origin is unknown.
    - **The sample does not wait for 19.0 R2.** [[#r12]]'s labeller records each pair's origin
      from the transcript ([[#od-2]]), so precision is computed over main-loop pairs and the
      subagent share of credits is measured.
14. **D14: an abandoned call credits, counted (m-2).** {#d14}
    - The sweep folds calls parked over 90 s into the ring as `abandoned` events, with `t` at
      sweep time. r1 gave them no `t_start`, so a call started before a delivery could be
      credited after it.
    - **Decision.** The sweep passes the parked record's `t` as `t_start`. An abandoned call
      (hung, denied, killed) still credits: the agent acted on the file, whether or not the
      tool succeeded. Such credits are counted `credited_abandoned`.

## Requirements {#requirements}

1. **R1: the ring records what the join needs, built by ONE builder.** {#r1}
   - **Every ring event** gains `t`, a sub-second epoch, stamped by `Stm.record`. Every writer of
     the ring gets it: the shell hook, the sweep's `abandoned` events, and 24.2a / 24.6's
     observe. (`input` events already carry it; their value is unchanged.)
   - **The ONE builder.** `cli._tool_event_fields` moves to `stm.tool_event_fields(tool_name,
     tool_input, *, cwd, tool_use_id, agent_id, origin_known) -> ToolEventFields`, so the shell
     hook and 24.2a's `rmx_focus_observe` (called by 24.6's mod) call the same code. It returns
     `terse`, `refs` and `detail` exactly as `_tool_event_fields` does today, plus the fields
     below. `cli.focus_hook` calls it; `cli._tool_event_fields` is removed, not kept as a shim.
   - **A `tool` event gains:**
     - `tool`: the envelope's `tool_name`;
     - `cwd`: the envelope's `cwd`;
     - `t_start`: the parked PreToolUse record's `t`, from `inflight_end`'s return value; null
       when nothing was parked (counted `order_from_end`). The sweep's `abandoned` events take
       the parked `t` ([[#d14]]);
     - `tool_use_id`: the envelope's, null when absent;
     - `origin`: per [[#d13]]. The builder writes `agent:<agent_id>` when `agent_id` is given;
       else `parent` when `origin_known` (the mod knows its loop); else no key;
     - the matcher's inputs, from `tool_input`: `input_path` (`file_path`, or Grep's `path`, or
       NotebookEdit's `notebook_path`), `pattern` (Grep / Glob), `command` (Bash), `prompt`
       (Agent / Task). Each is capped at `stm.INPUT_FIELD_MAX = 2000` characters; a capped field
       is named in `input_truncated` (a list) and counted by the report. Edit / Write bodies are
       still dropped;
     - `result_mentions`: written only by 24.6's observe ([[#d10]]); reserved here.
   - **No extra file is opened and no extra read is made.** The fields ride the existing append.
     `stm_events_n` (21.1 R9) is unchanged: no line is added.
2. **R2: `path` on every delivered and retrieved event (additive; `v` stays 1).** {#r2}
   - `path` is appended to `telemetry.RECALL_EVENT_FIELDS_V1` ([[#d3]]). `emit_recall_events`
     still stamps `v: 1`.
   - **ONE function, `telemetry.item_path(kind, entity_path, metadata, name, *, root)`**, gives
     every emitter the path, `norm_path`-ed:
     - `memory` and `subject` items: `memory_content.metadata.source_path` (b-2: memories have
       no `Entity.path`; on the snapshot 153 of 153 delivered memory ids had `path IS NULL`), or
       null when the memory has none;
     - grep-floor items (no `entity_id`, a relative-path `name`; m-6): the store root's parent
       (the project dir the floor searched) joined with the name, when the name contains `/`
       (45 of 45 such names in the window resolve there); legacy events take `logical_root`'s
       parent at report time, counted `path_from_name`;
     - every other item: the entity's `Entity.path`, or null (a term concept).
   - **The emitters already hold the item.** `context._item` / `bundle_items` (anchor, attached
     memory, group entries); `scan.py` through the context bundle; `telemetry.recall_item`
     (recall hits, through `Store.item_meta`, which gains `e.path` and the memory's
     `metadata->>'source_path'` by a left join, both in `context.ITEM_META_FIELDS`).
   - R5's `malformed` rule, `_EVENT_REQUIRED` and `row_provenance` do not change.
3. **R3: ONE matcher, `telemetry.tool_touches(tool_name, tool_input, cwd) -> ToolTouches`, plus
   a ring adapter (m-8, OD-4).** {#r3}
   - `tool_touches` takes a tool call as Claude Code describes it, so 19.6's
     `score_readback.py`, which reads the transcript's full `tool_input`, can call the same
     function ([[#od-4]]). `telemetry.ring_tool_call(ring_event) -> (tool_name, tool_input,
     cwd)` rebuilds the call from a ring event: from R1's fields when present, else from
     `terse` / `refs` / `detail` (legacy, [[#r10]]).
   - `ToolTouches` holds the call's normalised file paths, its name tokens, its glob and an
     `explicit` flag. `ToolTouches.match(path, name) -> match_on | None` applies these rules, in
     order:

   | tool | match_on | rule |
   |---|---|---|
   | Read, Edit, Write, MultiEdit, NotebookEdit | `path` | `norm_path` of `input_path` (or any `refs` entry on legacy lines) equals the item's `path` |
   | Grep | `path` | its `input_path` equals the item's `path` |
   | Grep | `name` | a whole token of `pattern` equals the item's `name`; tokenised by 21.1 R12's `_NOTE_TOKEN_RE` and gated by `_matchable`, the focus-note matcher, not a new one |
   | Glob | `glob` | the item's `path` basename appears literally in the pattern's last component, AND `fnmatch(path, pattern)` (`**/*.py` alone matches nothing) |
   | Bash | `bash_path` | a `refs` path, resolved against `cwd` (else `logical_root`'s parent, counted `cwd_fallback`), equals the item's `path` |
   | Bash | `bash_name` | a whole token of `command` (legacy: `detail`) equals the item's `name` (same tokeniser and gate) |
   | Agent, Task | `name` | a whole token of `prompt` equals the item's `name`. Live from 24.6 R4 ([[#d6]]) |
   | any other tool | none | not matched; counted per tool name in `tool_events_unmatched_by_tool` |

   - **Explicit calls are skipped.** Any tool whose name starts with `mcp__refmatrix__` (live
     from 24.6 R4), and a Bash command whose first `rmx` invocation is `context`, `memory get`
     or `focus note`. Those are R12's explicit evidences; matching them here would count one act
     twice. They are counted (`skipped_explicit_tool_calls`) and never matched.
   - **Other `rmx` commands match as Bash**, including `rmx grep`, the shim's target.
   - **Memory items.** A memory's `path` is its `metadata.source_path` ([[#r2]]), so a Read of
     `memory/feedback_x.md` is a `path` match. Its `name` matches under the name rules.
   - **`result_mentions` is ignored** ([[#d10]]).
4. **R4: the prompt clock, order and window.** {#r4}
   - **Prompt-clock rows.** `telemetry.is_prompt_row(row)` is the ONE predicate: a `query.log`
     row of the session with `kind == "scan"`, or `kind == "recall"` with `session_start` and
     `recent` both unset; and `invocation == "hook"` or `hook_event == "UserPromptSubmit"` (24.6
     d16). A row's start is its `t` (sub-second, [[#r13]]), else `ts − latency_ms` (legacy,
     second resolution, counted `prompt_rows_legacy`).
   - **Grouping.** `telemetry.prompt_clock(rows)` sorts the session's rows by start. When rows
     carry `prompt_id` (24.6 d16), one `prompt_id` is one prompt. Otherwise a row joins the
     current prompt when it starts within `PROMPT_PAIR_S = 5.0` s of the prompt's first row and
     the prompt holds no row of its kind yet; any other row starts a new prompt. A prompt's
     start is its earliest row's start. (Measured: paired rows start within 0.8 s.)
   - **Indexes.** `idx(x)` is the number of the session's prompts whose start is at or before
     time `x`. A prompt-time delivery (channel `scan_prompt` or `prompt_recall`) takes the index
     of the prompt holding its own row (by `query_id`); one with no such row is counted
     `prompt_unanchored` and takes `idx(D.ts)`. Every other delivery takes `idx(D.ts)`.
     A tool event takes `idx(T.t_start)` (or `T.t`, counted `order_from_end`).
   - **Credit conditions.** `T` can credit a unit `U` only when all of these hold:
     - same session (the ring union below);
     - `T.t_start` is strictly after the unit's first delivery `ts` (UTC, R10);
     - `0 ≤ lag_turns = idx(T) − idx(U) ≤ W`, with `W = telemetry.TOOL_USED_WINDOW_TURNS = 2`;
     - `T`'s `origin` is `parent` or absent ([[#d13]]).
   - **Reads before delivery never count.** A match whose `T` precedes the unit sets
     `prior_touch` on that file (or key) for every LATER unit of it in the session. A credit
     with `prior_touch` is still a credit; the headline excludes it ([[#d8]]).
   - **Matches beyond the window** credit nothing and appear in the lag histogram as `>W`.
   - **Subject rings.** A session's events are the union of `<session>.jsonl` and every
     `<session>__<subject>.jsonl` (`stm._partition_key`), merged by `t`.
   - **Legacy ties.** When either side of a comparison has only second resolution and the two
     fall in the same second, the pair is counted `order_ambiguous` and credits nothing.
5. **R5: attribution and dedupe (per unit).** {#r5}
   - Each unit is credited at most once, by the earliest qualifying `T`.
   - A `T` touching file `F` credits, on each channel, the unit of `F` from the most recent
     delivering prompt at or before `idx(T)`. Units of `F` from the same prompt on different
     channels (scan_prompt and prompt_recall answering one prompt) are each credited.
   - Older units of `F` stay uncredited, so a file that scan_prompt re-delivers every prompt
     lowers the per-unit rate. The report also prints a per-distinct-file rate
     (`distinct_used / distinct_eligible`, files or no-path keys), so the re-delivery effect is
     visible.
6. **R6: explicit uses are attributed to the delivering channel.** An R12 `used` event is
   counted under the channel of the delivered event its `ref_query_id` points to (looked up
   among the window's delivered events), and credits that event's unit. It is not counted under
   its own `channel` field, which is `context` for `context_by_name`. A `ref_query_id` with no
   delivered event in the window is counted `explicit_ref_unresolved`. {#r6}
7. **R7: a control (m-4).** {#r7}
   - The same matcher, window and ordering run over **control units**: `retrieved` items with no
     `delivered` event for the same `query_id` and key (retrieved, then trimmed, so the agent
     never saw them), whose key AND file were never delivered in the session before `T`.
   - The report prints `lift = rate_headline − control_rate` per channel and per `kind`.
   - Stated bias: trimmed items rank lower, so the control under-estimates the base rate and the
     lift over-estimates the effect.
8. **R8: the report.** `agent_usage_report` gains a `used by channel` block. Per delivering
   channel, over the window: {#r8}
   - `delivered` (events), `eligible` (events) and the exclusions ([[#r9]]); `units` and
     `anchors_in_units` ([[#d7]]);
   - `used_explicit` per R12 evidence; `used_tool`; `used_headline`; `used_incl_prior`;
   - `rate_headline` and `rate_incl_prior`, each with both numbers and a percentage, on one line;
   - `used_tool` split by `tool`, by `match_on`, by `prior_touch` and by `origin` (`parent` /
     `unknown`);
   - a **leg table**: each R3 leg with its ring event count and producer status (`live`, or
     `not-yet-producing`, [[#d6]]) and its rate (`n/a` when it has no events);
   - the `lag_turns` histogram (0, 1, 2, `>W`) and `censored`: eligible units with fewer than
     `W` later prompts in their session (kept in the denominator, count shown);
   - per-distinct-file: `distinct_used / distinct_eligible`;
   - the control and the lift ([[#r7]]);
   - the prompt clock line: prompts, prompt-clock rows by kind, prompts without a scan row,
     ring `input` lines, `prompt_unanchored`, `prompt_rows_legacy`.

   Deliveries come from the store's own file AND the global file. A global event is read when
   `norm_path(event.root) == norm_path(logical_root)` (m-5; through `row_provenance` first, so
   malformed and test-artifact rows are excluded as everywhere else). A reconciling line prints
   `delivered: project=<n> + global(this root)=<m> = <n+m>`, so the block's count can be
   checked against the existing project-only funnel line.
9. **R9: no silent drops (s-7).** {#r9}
   - **The identity, counted where each event enters.** Each delivered event read in the window
     increments `delivered`, then exactly ONE of `eligible`, `no_session`, `no_ring` (the
     session has no ring file under this root, for example after `rmx focus clear`) or
     `precompact_gated` (d5d), at the branch where it is admitted or turned away. `eligible` is a
     counter at the admission point, never `delivered` minus the others. The report asserts
     `delivered = eligible + no_session + no_ring + precompact_gated`; a mismatch prints
     `identity-broken` and the report exits 1.
   - **Every other count, printed even when 0**, on one `used-by-channel exclusions` line:
     `no_path`, `memory_no_source_path`, `path_from_catalog`, `path_unresolved`,
     `path_from_name`; `prompt_unanchored`, `prompt_rows_legacy`, `order_ambiguous`,
     `order_from_end`, `cwd_fallback`; `ring_unparseable`, `tool_from_terse`,
     `input_truncated`, `detail_truncated`; `skipped_explicit_tool_calls`,
     `tool_events_unmatched_by_tool`, `refs_outside_project`; `origin_unknown`,
     `subagent_tool_events`, `origin_unattributed`; `credited_abandoned`;
     `result_mentions_present`; `explicit_ref_unresolved`.
10. **R10: legacy data (the window the user already asked about).** {#r10}
    - **Events without the `path` key** (written before this task). Their path is resolved from
      the read snapshot by `entity_id` through the same `item_path` rules (memories by
      `memory_content.metadata.source_path`), using the normal CLI read path, never a `Store()`
      open on the active slot. Counted `path_from_catalog`; an id not found is counted
      `path_unresolved` and falls back to the name rules.
    - **Ring lines without `t`** are ordered by their local `ts`, converted with `time.mktime`
      (ties per [[#r4]]).
    - **Ring lines without `tool`** take the tool from `terse`'s first token, counted
      `tool_from_terse` (m-3). `kind = git` lines are Bash calls (the git-milestone branch of
      the tool hook) and are read as `tool = Bash`.
    - **Query.log rows without `t`** start at `ts − latency_ms` ([[#r4]]).
    - **What this gives.** A number for 2026-11-10 onward on the day it ships, marked
      `legacy-ordered=<n>`, so it is not read as exact.
11. **R11: no hook emits.** After this task, a `used` event with an evidence other than R12's
    three appears in no `recall-events.jsonl`. `rmx focus hook` opens no `recall-events.jsonl`
    and makes no `delivered_in_session` call. R12's sentence "a `hook` call never emits `used`"
    stays true without an exception clause. {#r11}
12. **R12: pre-registered precision bands (s-6), before any consumer counts it.** {#r12}
    - **The source window.** Credited `(U, T)` pairs from the 21 days after the deploy sha
      recorded in the implementation summary. Under 50 pairs at day 21: the window extends to
      day 42. Still under 50: the result is **report-only** (the default; no band is read) and
      R12 re-runs on the next 21-day window.
    - **The draw.** All pairs when there are at most 80; otherwise uniform within strata
      (`tool` × `match_on`), each stratum taking `min(available, max(10, its proportional
      share))`, at least 50 in total. The pair list's sha256 is committed and frozen.
    - **The labels.** Per pair, from the local transcript (d8f: raw text stays local; labels,
      the hash and the counts are committed): "the delivery plausibly caused the tool call"
      yes / no, and the call's origin (main loop / subagent / unclear). The labeller is
      [[#od-2]].
    - **Which pairs are judged.** Precision is computed over the main-loop pairs, `n_main`. The
      subagent share of all labelled pairs is printed. When it exceeds 10% and neither 19.0 R2
      nor 24.6 R4 is live, no band above report-only applies, because the live rate still
      carries those false credits.
    - **Pooled bands.** `p` = precision over `n_main`, with its Wilson 95% interval. Recorded
      here before labelling ([[feedback_go_no_go_ranges_not_predrop]]):

    | condition | action |
    |---|---|
    | `n_main < 50` | report-only (the default). No band is read; R12 re-runs |
    | `p ≥ 0.80` and Wilson lower bound `≥ 0.65` | 19.2 may add a `used_tool` column (a migration, 19.2 R1), weight `w_tool = round(2 × p, 1)` |
    | `0.50 ≤ p`, and not the row above | report-only; 19.2 does not count it; the stratum rule below runs |
    | `p < 0.50` | the matcher is revised and re-measured; nothing downstream changes |

    - **Per-stratum minimum.** A stratum is dropped from the matcher only when it has at least
      20 labelled main-loop pairs AND its Wilson 95% upper bound is below 0.50. A stratum with
      fewer than 20 is `underpowered`: reported, not dropped, and given no consumer weight. A
      stratum below 0.50 is shown as such in the report's `match_on` split in every band.
    - **When drops leave too little.** After any drop, the remaining strata are judged again
      only on a fresh draw of at least 50 pairs of their own. Until then the result is
      report-only. The Bash strata are the expected whole signal ([[#why-data]]); if both are
      dropped, the Read / Edit / Write `path` legs must reach 50 pairs alone before any band
      applies.
13. **R13: query.log rows carry a sub-second `t`.** `log_query.__enter__` records `time.time()`
    and the row writes it as `t` (the call's start). Additive: no reader requires it, and the
    second-resolution `ts` stays. It gives [[#r4]]'s prompt clock the resolution the ring's `t`
    has. {#r13}

## Acceptance criteria {#acceptance}

**The AC preamble (s-5).** Every AC runs inside 23.0's sandbox and ends with 21.1's stat-only
live-log guard, not a line count: `live_snapshot(...)` at the start and
`assert_live_logs_unchanged(before)` at the end (`tests/task21_1_support.py:100`, bug-134), over
`live_log_paths()` plus every live `.refmatrix/stm/*.jsonl` of the same stores. The test also
asserts that no ring file named after one of its minted session ids appears under a live `stm/`
directory (a directory listing, never an open). Every minted session id and prompt is registered
with `mark_token`, so 23.0's end-of-run growth check attributes any leak to the test. {#ac-preamble}

The ring and the events are produced by the REAL commands: `rmx focus hook --event
tool-pre|tool|input` fed real-shaped envelopes on stdin, and `rmx scan-prompt` /
`rmx memory recall --stdin-json` against a tmp store. No ring, event or query.log line is
hand-written, except in AC-9 and AC-2b, which are about legacy lines. {#ac-producers}

1. **AC-1 (R1): ring fields, one builder.** A `tool-pre` then `tool` envelope pair for a Read of
   `F` (with `cwd` and `tool_use_id` set) writes one ring `tool` line carrying `t`, `t_start`
   (= the parked `t`), `tool: "Read"`, `cwd`, `tool_use_id`, `input_path == F`, and no `origin`
   key. The same pair with `agent_id: "a1"` in the envelope writes `origin: "agent:a1"`. A Bash
   whose command is 2,500 characters writes `command` of 2,000 and `input_truncated:
   ["command"]`. A `tool` envelope with no prior `tool-pre` writes `t_start: null`. A call
   parked and then swept writes `abandoned: true` with `t_start` = the parked `t`.
   `cli._tool_event_fields` no longer exists, and `stm.tool_event_fields` is the only builder
   (an import check). **RED at HEAD:** the line has none of the new fields; the builder is in
   `cli`. {#ac-1}
2. **AC-2 (R2, D3): `path`, and `v` stays 1.** A real scan-prompt over a tmp store holding code
   file `F` writes delivered events for `F`'s symbols with `v == 1` and `path ==
   norm_path(F)`. A real `memory recall --stdin-json` over a tmp memory dir writes a
   `kind=memory` delivered event whose `path` is the memory file's `source_path`. A memory row
   with no `source_path` and a term concept each write the key with `path: null`. A grep-floor
   item `src/x.py` writes the store root's parent joined with it.
   `"path" in RECALL_EVENT_FIELDS_V1`. **RED at HEAD:** no `path` key; memories have no
   `Entity.path`. {#ac-2}
3. **AC-2b (D3): the classifier and the existing funnel are untouched.** One events file holds a
   hand-written pre-task event (no `path` key, copied from a HEAD-era emitter's field set) and a
   real post-task event. `row_provenance(..., source="events")` gives `attributed` for both;
   the existing `--agent-usage` funnel prints `malformed=0` and folds both; the new block
   counts the first `path_from_catalog` and the second by its own `path`. The 21.1 tests at
   `test_task21_1_agent_usage_report.py:238` and `test_task21_1_emitters.py:204` pass
   unmodified. **Mutation:** the emitter stamps `v: 2`; the funnel prints `malformed=1` and
   this AC fails. {#ac-2b}
4. **AC-3 (R3, R4, R8): the end-to-end use.** Prompt 1: scan-prompt delivers symbol `S` of `F`.
   Then a Read of `F`. `--agent-usage` prints, under `scan_prompt`: `units=1`, `used_tool=1`,
   tool `Read`, `match_on=path`, `prior_touch=no`, `lag 0=1`, and `rate_headline` and
   `rate_incl_prior` with `eligible` units as the denominator. **RED at HEAD:** there is no
   `used by channel` block. {#ac-3}
5. **AC-4 (R4, D8): before delivery never counts.** (a) A Read of `F` in prompt 1, then a
   delivery of `S` in prompt 2, and no later Read: `used_tool=0`. (b) As (a), plus a Read of
   `F` in prompt 2: `used_incl_prior=1`, `prior_touch=yes`, `used_headline=0`. (c) A Read of
   `F` whose `t_start` precedes the delivery's `ts` but whose PostToolUse lands after it: not
   credited. **RED at HEAD:** no block; with an ordering mutation, (c) is credited. {#ac-4}
6. **AC-5 (R4, D9): the window counts every prompt.** (a) A Read of `F` in the third prompt after
   the delivery credits nothing and lands in `lag >2`; in the second prompt after, it is
   credited. (b) An AMBIENT prompt (a real `focus hook --event input` and scan-prompt hook run
   on a `<task-notification …>` prompt, which writes no ring `input` line) sits between the
   delivery and a Read two real prompts later: the Read is at `lag 3` and not credited. (c)
   `censored` counts a unit delivered in the session's last prompt. **RED at HEAD:** no block.
   **Mutation:** the clock counts ring `input` lines; (b) credits at lag 2. {#ac-5}
7. **AC-6 (R5, D7): the unit.** (a) scan-prompt delivers three anchors of `F` in prompt 1, then
   one Read of `F`: `units=1`, `anchors_in_units=3`, `used_tool=1`. (b) `F` delivered by
   scan-prompt in prompts 1 and 2, one Read in prompt 2: per-unit `1/2`, distinct `1/1`. (c)
   `F` delivered in prompt 3 by both scan_prompt and prompt_recall, then a Read: both channels
   credited, and the `any channel` row counts the file once. (d) Two Reads after one delivery:
   credited once. (e) One Bash touching delivered `F` and `G`: two units credited. **RED at
   HEAD:** no block. {#ac-6}
8. **AC-7 (R3): each matcher leg, positive and negative.** {#ac-7}
   - Through the real hook: a Grep with `path=F` is credited; a Grep whose pattern is
     `used_events|other` is credited for the delivered name `used_events`; a Grep for `run`
     against a delivered name `run` is NOT credited (`_matchable`); Glob `**/telemetry.py` is
     credited for `src/refmatrix/telemetry.py` and Glob `**/*.py` is not; Bash `sed -n 1,40p
     src/x.py` with `cwd` = the project dir is credited `bash_path`; Bash `rmx context S` is
     counted in `skipped_explicit_tool_calls` and credits nothing; a Read of a memory's source
     file is credited for that memory.
   - Unit legs, labelled as such, because their producer is 24.6 R4 ([[#d6]]):
     `tool_touches("Agent", {"prompt": …}, cwd)` matches a delivered memory's name;
     `tool_touches("mcp__refmatrix__rmx_context", …)` is `explicit`. The end-to-end test of
     both is 24.6 r6 AC-3.
   - `ring_tool_call` on a legacy line (no `tool`, `detail` only) gives the same matches as on
     an R1 line for the same call.

   **RED at HEAD:** no matcher.
9. **AC-8 (R6): explicit uses go to the delivering channel.** scan-prompt delivers `S`, then
   `rmx context S` (agent) emits R12's `context_by_name`. The report counts it under
   `scan_prompt used_explicit context_by_name=1`, not under `context`. A `used` event whose
   `ref_query_id` matches no delivered event in the window is counted `explicit_ref_unresolved`.
   **RED at HEAD:** the report lists it as `events context used: 1`. {#ac-8}
10. **AC-9 (R9, R10): every exclusion is counted, and the identity is not tautological (s-7).**
    {#ac-9}
    - One fixture holds: a delivered event with `session: null`; one whose session has no ring;
      a `precompact` delivery; a term concept with `path: null`; a pre-task event (no `path`
      key) whose `entity_id` is in the tmp catalog (`path_from_catalog`) and one whose id is not
      (`path_unresolved`); a legacy ring line without `t` tying `D.ts` to the second
      (`order_ambiguous`); a legacy line with no `tool`; a Bash without `cwd`
      (`cwd_fallback`); a non-JSON ring line; a `detail` of exactly `DETAIL_MAX`; a Read of a
      path outside the project.
    - Each count is printed with its exact value, and the identity holds.
    - **Mutations, each must print `identity-broken` and exit 1:** `no_ring` dropped from the
      identity; and, separately, the `no_session` branch made to `continue` without counting.
      The second proves `eligible` is counted at admission, not computed by subtraction.
    - The pre-task and legacy lines here are hand-written; they copy the field sets a HEAD-era
      emitter and hook wrote.

    **RED at HEAD:** none of the counts exist.
11. **AC-10 (R7): the control.** A `retrieved`-only item (trimmed by the payload cap) whose file
    is later Read counts in the control and not in `used_tool`. A trimmed item whose file was
    DELIVERED earlier in the session (as another item) is not a control unit. `lift` is printed
    per channel and per kind. **RED at HEAD:** no control. {#ac-10}
12. **AC-11 (R8): global scope, normalised.** A global memory delivered by prompt_recall in a
    session of this store (event in the GLOBAL file, `root` spelled `/tmp/…` for a store at
    `/private/tmp/…`), whose source file is then Read, is credited and reported under
    `scope=global`. The same event with a different `root` is not read. The reconciling line
    prints `project=<n> + global(this root)=1`. **RED at HEAD:** the report reads only the
    project file. {#ac-11}
13. **AC-12 (R1, R4): subject rings merge.** With `rmx focus subject` switched between the
    delivery and the Read, the Read lands in `<session>__<subject>.jsonl` and is still credited
    at `lag 0`. **RED at HEAD:** no block. With a mutation that reads only the bare-session
    ring, it is not credited. {#ac-12}
14. **AC-13 (R11): no hook emits (a guard, proven by mutation).** After AC-3's flow, no
    `recall-events.jsonl` contains a `used` event outside R12's three evidences. Across the
    `rmx focus hook` calls, the event files' size and mtime are unchanged. A mutation that
    emits from `focus_hook` fails this AC. This passes at HEAD by construction; its RED is the
    mutation. {#ac-13}
15. **AC-14 (R4, D13): origin.** Through the real hook: a tool event with `origin:
    "agent:a1"` (envelope `agent_id`) credits nothing and is counted `subagent_tool_events`; a
    tool event with no `origin` is credited and counted `origin_unknown`, and the footer says
    the rate includes subagent tool calls of unknown origin. A ring line with `origin:
    "unattributed"` (hand-written; 19.0 R2's value, no producer yet) credits nothing, counted
    `origin_unattributed`. **RED at HEAD:** no origin field, no footer line. {#ac-14}
16. **AC-15: run once on real data (the benchmark path IS the production path).** {#ac-15}
    - The dev-tree report (`.venv-eval`) is run against APFS clones, made under a `mkdtemp()`
      root, of this project's `.refmatrix/` `query.log`, `recall-events.jsonl`, `stm/*.jsonl`,
      the global events file and the read snapshot, with `logical_root` = the live root's path
      as a string ([[#d11]]). Nothing is written to, or opened under, the live tree.
    - The output and its wall time go into the implementation summary, with the window
      2026-11-10 onward and R10's legacy counts. The clones are deleted after the run.
    - It runs the same `agent_usage_report` function the tests drive, with no bespoke path.
    - It is not a pass/fail gate on the number. It IS a gate on the run: exit 0, the identity
      holds, and the global reconciling line is non-zero when the global file holds events for
      this root.
17. **AC-16 (D6, R8): legs without a producer are labelled, not zero.** With the real
    generated matcher (`hooks.FOCUS_TOOL_MATCHER`) and a ring holding no Agent and no `mcp__*`
    events, the leg table prints `Agent: 0 events, not-yet-producing (live from 24.6 R4)` and
    rate `n/a`, and the same for `mcp__refmatrix__`. With one hand-written Agent ring line in
    the window, the leg prints `live` with its count. The generated hook config is byte-equal
    before and after the constant's extraction. **RED at HEAD:** no leg table, no constant.
    {#ac-16}
18. **AC-17 (R4, R13, D9): the prompt clock.** (a) Every new query.log row carries `t`. (b) One
    prompt's scan and prompt-recall rows (real hooks on one envelope) group into one prompt.
    (c) A prompt for which only the prompt-recall hook runs (as when Claude Code kills
    scan-prompt at its timeout before it logs) is still one prompt, and the clock line counts
    it under prompts without a scan row. (d) Rows carrying `prompt_id` group by it even 6 s
    apart. (e) A session-start recall row and a `recent` recall row are not prompt rows.
    **RED at HEAD:** no `t`, no clock. {#ac-17}
19. **AC-18 (D10): `result_mentions` is counted, never matched.** A ring tool line carrying
    `result_mentions: ["S"]` (hand-written; 24.6's producer is not built) for a delivered `S`
    with no other touch credits nothing and is counted `result_mentions_present=1`. **RED at
    HEAD:** no count. {#ac-18}

## Mutations {#mutations}

Each mutation must make at least one AC FAIL, not hang. Each restore runs as its own command.
- `>` to `>=` in R4's ordering: AC-4 (c) credits.
- `t_start` replaced by `t`: AC-4 (c) credits.
- The window `W` raised to 3: AC-5 (a) credits the third-prompt Read.
- The clock built from ring `input` lines: AC-5 (b).
- Every older unit of the file credited: AC-6 (b) per-unit reads `2/2`.
- Credit per delivered event instead of per unit: AC-6 (a) reads `used_tool=3`.
- `prior_touch` credits counted in the headline: AC-4 (b).
- The explicit skip removed: AC-7 credits `rmx context S`, and AC-8's `used_headline`
  double-counts.
- Explicit uses attributed by their own `channel`: AC-8.
- `no_ring` dropped from the identity, and the uncounted `no_session` branch: AC-9.
- The control admits units whose file was delivered: AC-10.
- The global filter without `norm_path`: AC-11.
- The bare ring only: AC-12.
- `focus_hook` calls `emit_recall_events`: AC-13.
- `agent:*` origins credited: AC-14.
- A leg with no events printed as rate 0: AC-16.
- Prompt rows not grouped (each row its own prompt): AC-17 (b).
- `result_mentions` matched as a name: AC-18.
- The emitter stamps `v: 2`: AC-2b.
- `path` written as the raw `Entity.path` (not `norm_path`): AC-2 on a `/tmp`-spelled root.

## Files to modify {#files-to-modify}

| file | change |
|---|---|
| `src/refmatrix/stm.py` | `Stm.record` stamps `t` on every event; `tool_event_fields` (moved from `cli`) with `tool`, `cwd`, `t_start`, `tool_use_id`, `origin`, `input_path` / `pattern` / `command` / `prompt`, `INPUT_FIELD_MAX`, `input_truncated`; `inflight_sweep` passes the parked `t` as `t_start` (R1, D13, D14) |
| `src/refmatrix/cli.py` | `focus_hook`'s tool branches call `stm.tool_event_fields` with the envelope's `cwd`, `tool_use_id`, `agent_id`; `_tool_event_fields` removed (R1) |
| `src/refmatrix/context.py` | `_item` / `bundle_items` carry `item_path`; `ITEM_META_FIELDS` gains `path` and `source_path` (R2) |
| `src/refmatrix/store.py` | `Store.item_meta` selects `e.path` and the memory's `metadata->>'source_path'` (R2) |
| `src/refmatrix/hooks.py` | `FOCUS_TOOL_MATCHER` constant, used by the generator; generated output byte-identical (D6) |
| `src/refmatrix/telemetry.py` | `path` appended to `RECALL_EVENT_FIELDS_V1`; `item_path` (R2); `log_query` writes `t` (R13); `is_prompt_row`, `prompt_clock`, `PROMPT_PAIR_S`, `TOOL_USED_WINDOW_TURNS` (R4); `tool_touches`, `ToolTouches`, `ring_tool_call` (R3); `derive_tool_used(root, *, logical_root, global_root, since, until) -> ToolUsed` returning per-unit credit records (`unit`, `tool`, `match_on`, `ref_query_id`, `lag_turns`, `lag_s`, `prior_touch`, `origin`) plus the R9 counts, never written to any file (R4-R7, R9, R10); the `used by channel` block, the leg table, the reconciling line and the identity check in `agent_usage_report(..., logical_root=None)` (R8, R9, D11) |
| `workflow/plans/plan-21-agent-context-usage-tasks/task-21.1-context-usage-telemetry.md` | R10's field table gains a `path` row (null allowed; absent before 21.5); a revision row naming this task (D3) |
| `tests/test_task21_5_tool_used.py` | AC-1 to AC-18 except AC-15 |
| `workflow/implementation_summaries/task-21.5-tool-used-signal.md` | AC-15's run; the deploy sha that opens R12's window |

`verbs.py` does not change (D5). `rmx install-hooks --check` stays clean because the generated
hook commands are byte-identical (AC-16). 24.2a's `rmx_focus_observe` calls `stm.tool_event_fields`
when it is built; this task does not build it.

## Test strategy {#test-strategy}

- **Sandbox.** Tests use 23.0's fixtures: `$HOME`, the global root, the registry and LaunchAgents
  are redirected before import, and spawned `rmx` children refuse sockets outside the tmp dir.
  Tmp roots are short (macOS `sun_path`). The live-log guard is [[#ac-preamble]]'s.
- **Real producers.** The ring comes from the real `rmx focus hook` command, the events and the
  prompt-clock rows from the real scan-prompt / recall / context commands. A unit test of
  `tool_touches` alone is allowed in addition, never instead, except for the two legs whose
  producer is 24.6 (AC-7's labelled unit legs).
- **RED first.** The test file is run against unfixed HEAD and its failures are read: every AC
  except AC-13 must fail there, for the stated reason.
- **Output.** Runs are captured to `workflow/review-output/pytest-task21-5.log`.
- **Regression.** The full suite runs before merge: the builder move touches the focus hook,
  `log_query` touches every query.log writer, and 21.1's schema tests must pass unmodified
  (AC-2b).

## Open decisions {#open-decisions}

1. **OD-1: CLOSED (the user, 2026-11-11).** 24.6 R4's `tool_result` evidence does not emit:
   the mod's observe writes ring fields and no `used` (24.6 r5). r6 makes its `result_mentions`
   raw and leaves the check to this task's report ([[#d10]]). {#od-1}
2. **OD-2: who labels R12's sample — decided as the user would.** {#od-2}
   - An agent that never reads the matcher code labels every pair from local transcripts (d4c's
     independence rule), recording both the cause label and the call's origin (main loop /
     subagent / unclear), and the user spot-checks 10 pairs.
   - The user may instead label all of them; that changes no number pre-registered here.
3. **OD-3: if a live consumer ever needs the signal.** It is NOT materialised now. If 19.2 or
   19.6 later needs it live, a plan-23 drain tick calls `derive_tool_used` over the newly
   folded window and writes `stage=used, evidence=tool` events through `emit_recall_events`,
   with the matcher version in `policy`. It never uses a hook. This needs its own task after
   R12's top band. {#od-3}
4. **OD-4: one implementation of 19.6's tool-input read-back clause — needs the user**
   ([[#open-for-user]]). {#od-4}
   - 19.6's read-back definition (d9v, user-confirmed;
     [[task-19.6-phased-context-and-topic-cache#ranges]]) counts "a later tool call whose input
     names it (`file_read`)", computed by its offline transcript scorer. This task computes the
     same clause from the ring.
   - **Recommendation.** One decision-log row: `score_readback.py` calls
     `telemetry.tool_touches(tool_name, tool_input, cwd)` on each transcript tool call (the
     signature takes Claude Code's own input, so the scorer needs no ring); the evidence is
     named `tool` everywhere; a memory's path is its `memory_content.metadata.source_path`
     (memories have no `Entity.path`); 21.1 R12's reservation names `tool` (owned here) and
     `cited_in_answer` (still 19.6's, transcript-only). The definition's wording does not
     change; its source and owner do.
5. **OD-5: `W = 2` and R12's numbers — needs the user** ([[#open-for-user]]). r1's review
   objected to confirming them before a prompt was defined and a below-minimum default
   existed. Both are now in the spec ([[#d9]], [[#r12]]). {#od-5}

**Spec-settled here (lead decisions, made as the user would), not needing the user:** keeping
`v: 1` ([[#d3]]); the Agent / mcp legs ([[#d6]]); the credit unit ([[#d7]]); the headline
([[#d8]]); the prompt definition ([[#d9]]); `result_mentions` ([[#d10]]); the logical root
([[#d11]]); paths outside the project ([[#d12]]); `origin` ([[#d13]]); abandoned calls
([[#d14]]); the control ([[#r7]]); the explicit-call skip ([[#r3]]); attribution by
`ref_query_id` ([[#r6]]); no new verb ([[#d5]]). {#spec-settled}

## Open for the user {#open-for-user}

1. **OD-4 (d9v changes owner).** Approve the one decision-log row in [[#od-4]]: 19.6's scorer
   calls `tool_touches`, the evidence is named `tool`, and 21.1 R12's reservation is renamed.
   **Recommendation: approve.** Two implementations of one clause would be two ways to do X,
   and the `(tool_name, tool_input, cwd)` signature lets the transcript scorer call it as is.
   d9v says a confirmed item changes only by a new row, hence the user. {#ofu-od4}
2. **OD-5 (pre-registered numbers).** Confirm `W = 2` prompts (ambient included, [[#d9]]) and
   R12 as written: the 21 / 42-day source window, the report-only default under 50 main-loop
   pairs, the Wilson bounds, the 20-pair stratum minimum, and the 10% subagent ceiling.
   **Recommendation: confirm before AC-15's output is read.** Changing `W` is a one-constant
   change that rewrites no data (D1), and the lag histogram shows what any other `W` would
   give; in the prototype, of 125 first matches after a delivery, 40 / 11 / 11 sit at lag
   0 / 1 / 2 and 63 beyond `W`.
   {#ofu-od5}

## Non-goals {#non-goals}

- `cited_in_answer`: a delivered name in the assistant's reply. It stays 19.6's
  transcript-only evidence.
- Any change to R12's three explicit evidences, their lookup, or their destination.
- Any change to what is delivered. That is 19.1's and 25.1's business; this task is the
  instrument they will be judged by.
- Widening the shell hook matcher ([[#d6]]), building 19.0 R2's origin ladder ([[#d13]]), or a
  clone-path leg ([[#d12]]).
- A live counter of any kind ([[#d4]], [[#od-3]]).

## Revision 2 (2026-11-11, ch-bsd spec r1 + its addendum vs 24.6 r5) {#rev-2}

rel: derives-from -> [[bsd-task-21.5-spec-r1-15e8f64]]
rel: amends -> [[task-24.6-context-and-observation#rev-r6]]

Every r1 finding and addendum item, with its disposition. Lead decisions are marked (lead).

| finding | disposition | where |
|---|---|---|
| b-1 `v: 2` is `malformed` | no bump: `path` added to `RECALL_EVENT_FIELDS_V1`, key presence marks legacy; classifier and both 21.1 tests unchanged; AC-2b + a `v: 2` mutation (lead: the smaller correct change) | [[#d3]], [[#r2]], [[#ac-2b]] |
| b-2 memories have no `Entity.path` | `item_path`: memories by `memory_content.metadata.source_path`, null counted `memory_no_source_path`; legacy resolution likewise; AC-2 corrected | [[#r2]], [[#r10]], [[#ac-2]] |
| b-3 Agent / mcp legs unreachable | kept, marked "live from 24.6 R4"; reported `not-yet-producing` with `n/a`, never 0; shell matcher unchanged, read from one constant; unit legs + AC-16; 24.6 r6 AC-3 is the producer test (lead) | [[#d6]], [[#ac-7]], [[#ac-16]] |
| s-1 ambient prompts, anchor race | a prompt is a UserPromptSubmit, from query.log prompt-clock rows grouped per prompt; prompt-time deliveries anchored by `query_id`; `anchor_race` gone by construction; AC-5 (b), AC-17 | [[#d9]], [[#r4]], [[#r13]] |
| s-2 one call credits many anchors | credit unit = (tool call, file); units and anchors both printed; AC-6 (a), (e) (lead) | [[#d7]], [[#r5]] |
| s-3 subagent credits; no `tool_use_id` | `tool_use_id` + one `origin` field per 19.0 R2; `agent:*` and `unattributed` never credit; absent counted + footer; sample labels origin (lead) | [[#d13]], [[#r1]], [[#ac-14]], [[#od-2]] |
| s-4 clone run misses Bash and global | `logical_root` parameter for path resolution and the global filter; AC-15 states it | [[#d11]], [[#ac-15]] |
| s-5 line-count guard | 21.1's stat-only guard + growth ledger + `mark_token`, extended to live rings and new-ring creation | [[#ac-preamble]] |
| s-6 bands lack a below-min default | source window, report-only default under 50, Wilson bounds, 20-pair stratum minimum, re-draw after drops, Bash-only fallback rule | [[#r12]] |
| s-7 tautological identity | `eligible` counted at admission; mutation of an uncounted branch must break the identity | [[#r9]], [[#ac-9]] |
| m-1 matcher inputs only in `detail` | structured `input_path` / `pattern` / `command` / `prompt`, capped at 2,000 with `input_truncated` | [[#r1]], [[#d2]] |
| m-2 abandoned calls have no `t_start` | sweep passes the parked `t`; abandoned calls credit, counted `credited_abandoned` | [[#d14]], [[#ac-1]] |
| m-3 legacy lines have no `tool` | tool from `terse`'s first token, counted; `kind=git` read as Bash | [[#r10]], [[#ac-9]] |
| m-4 control admits delivered keys | control units exclude any key or file delivered in the session before `T`; lift per channel and kind | [[#r7]], [[#ac-10]] |
| m-5 root filter not normalised | `norm_path` on both sides, through `row_provenance` first; reconciling line | [[#r8]], [[#ac-11]] |
| m-6 grep-floor items have no path | `logical_root`'s parent + name, counted `path_from_name` | [[#r2]], [[#ac-2]] |
| m-7 prior-touch in the headline | headline excludes it; `rate_incl_prior` beside it (lead) | [[#d8]], [[#ac-4]] |
| m-8 matcher signature | `tool_touches(tool_name, tool_input, cwd)` + `ring_tool_call` adapter (lead) | [[#r3]], [[#od-4]] |
| x-1 two shapes of the tool input | ONE builder `stm.tool_event_fields` (moved from `cli`); 24.6 r6 R4 names it | [[#r1]]; 24.6 r6 R4 |
| x-2 subagent identity spelled three ways | one ring field `origin`; `agent_id` is only an input parameter; 24.6 r6 writes `origin` and `tool_use_id` | [[#d13]]; 24.6 r6 R3, R12 |
| x-3 observe-time delivered check | 24.6 r6 records RAW `result_mentions` (pre-filtered by `$.state` only); this task checks at report time when a leg exists (lead) | [[#d10]]; 24.6 r6 d6, R4 |
| x-4 `result_mentions` not in 21.5 | reserved ring field, ignored by the matcher, counted `result_mentions_present`; AC-18 (lead) | [[#d10]], [[#r1]], [[#ac-18]] |
| addendum on b-3 | as b-3; 24.6 r6 widens `tool.call` to every tool and AC-3 adds an Agent and an `mcp__refmatrix__` call | [[#d6]]; 24.6 r6 |
| OD-1 | closed by the user (24.6 r5) | [[#od-1]] |
| OD-2 add origin | the labeller records origin; decided (lead) | [[#od-2]] |
| OD-4 wording | signature and memory path stated; still the user's (d9v) | [[#od-4]], [[#ofu-od4]] |
| OD-5 objection | prompt defined and below-min default added; now for the user to confirm | [[#od-5]], [[#ofu-od5]] |
| missing open decisions (b-3, s-2, s-3, m-7) | each recorded as a decision row with its rationale | [[#d6]], [[#d7]], [[#d13]], [[#d8]] |
| imp-prototype-the-join | rev 2's join re-run over scratch copies; counts only | [[#why-data]] |

Also from the prototype (not an r1 finding): 269 of 348 Read/Edit/Write calls touch paths under
`/Volumes/littlebig/` and cannot match; counted `refs_outside_project`, no leg ([[#d12]]). The 21.5 row in
[[plan-21-agent-context-usage]] is updated to match (no `v: 2`; units; headline).
{#rev-2-note}
