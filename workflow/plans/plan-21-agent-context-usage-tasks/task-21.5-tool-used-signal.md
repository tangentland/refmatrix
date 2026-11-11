---
gmd: "0.1"
id: task-21.5-tool-used-signal
title: "Task 21.5: a tool-level `used` signal: derived at report time by joining each session's delivered events with its STM tool events, never emitted by a hook, reported as a per-channel usefulness rate with its denominator and every exclusion counted"
tags: [task, plan-21, telemetry, recall-events, used, stm, agent-usage]
metadata:
  node_type: task
  status: pending
  plan: plan-21-agent-context-usage
  created: 2026-11-11
  updated: 2026-11-11
---

# Task 21.5: a tool-level `used` signal {#root}

> Plan: [[plan-21-agent-context-usage]]
> Status: Pending (drafted 2026-11-11; needs a spec review before it can be approved)
> Wave: now. The user prioritised it on 2026-11-11, after reading `rmx telemetry --agent-usage`.
> Depends on: 21.1 (completed: the ONE recall-event schema, `emit_recall_events`,
> `delivered_in_session`, R12's three explicit evidences, the `--agent-usage` report), and 23.0
> (completed: the shared test sandbox).
> Touches the interfaces of 19.2 and 19.6 (pending), 24.6 (pending, plan-24 drafting) and 25.1
> (pending). It changes none of their specs. [[#open-decisions]] lists what each of them must
> decide.

rel: part-of -> [[plan-21-agent-context-usage]]
rel: depends-on -> [[task-21.1-context-usage-telemetry]]
rel: depends-on -> [[task-23.0-test-sandbox]]
rel: amends -> [[task-21.1-context-usage-telemetry#req-schema]]
rel: related-to -> [[task-19.2-memory-usage-record]]
rel: related-to -> [[task-19.6-phased-context-and-topic-cache]]
rel: related-to -> [[task-24.6-context-and-observation]]
rel: related-to -> [[task-25.1-recall-hook-byte-budget]]
rel: related-to -> [[task-24.0-hook-cost-baseline]]
rel: derives-from -> [[bsd-plan19-21-spec-rereview-32dde06]]
rel: reinforces -> [[feedback_no_silent_failures]]
rel: reinforces -> [[feedback_go_no_go_ranges_not_predrop]]

## Why {#why}

Since 2026-11-10, the user's run of `rmx telemetry --agent-usage` gave these funnels. scan_prompt:
2,051 retrieved, 1,733 delivered, 9 used. prompt_recall: 1,200 retrieved, 338 delivered, 0 used.

Under 21.1 R12, `used` fires only on an explicit agent or MCP call that names something the
session was delivered: `memory get <name>`, `context <name>`, or a `focus note` that contains the
name. Hook calls never emit (R12's helix rule). In practice, the agent acts on a delivered hit by
Reading, Editing or Grepping the delivered file, or by naming a delivered memory in a later tool
input. None of that is visible today. So "9 of ~2,100" is a floor, not a usefulness rate.

The signal is already on disk. The PostToolUse focus hook records every tool call into the
session's STM ring (`rmx focus hook --event tool`, `cli.py::focus_hook`). The ring keeps the tool's
file paths as `refs` and its verbatim input as `detail` (`cli.py::_tool_event_fields`). Each
delivered event names an item that has a file path in the catalog (`store.Entity.path`).

This task joins those two records and reports an honest rate per channel. The join happens at
report time. It does not emit a new event, and it does not reopen R12's hook rule.
{#why-body}

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
     does 19.2 AC-2, the fold's test of it. A hook that observes the agent's own tool call is
     not the helix confound (a hook re-retrieving what it delivered). But a hook that emits
     `used` would break the one simple rule that keeps the confound out.
   - **Reproducibility.** The ring is append-only and never trimmed (`stm.py`, `Stm.record`).
     The event file is retained until folded (C7). So the derivation can be re-run whenever the
     matcher, the window or the Bash rules change. Events emitted at hook time would freeze
     whatever matcher version was live when they were written, into counters that never decay
     (19.2 R1).
   - **What it costs.** No live consumer can read the signal. None needs to yet. 19.2 must not
     count it before its precision is measured ([[#d4]]). 19.6 scores offline. If a live
     consumer later needs it, a fold step calls the same derivation function ([[#od-3]]). It
     never gets a second matcher.
2. **D2: the STM ring is the source, not the transcript.** {#d2}
   - The ring is refmatrix's own primitive. It is keyed by the same Claude session id as the
     events (R9's resolver), and both the shell hook and 24.6's mod observe write it.
   - The transcript is Claude Code's internal format. It lives outside the store root and holds
     raw prompts (d8f).
   - The ring loses two things: `detail` is truncated at `stm.DETAIL_MAX` (600), and Edit /
     Write bodies are dropped (`_tool_event_fields`). Both are stated and counted
     ([[#r9]] `detail_truncated`). Neither affects a path match.
3. **D3: delivered events carry the item's `path`; the schema goes to `v: 2`.** {#d3}
   - Matching a Read or Edit needs the delivered item's file. The event carries `name` and
     `entity_id` but no path.
   - Resolving the path at report time from the catalog would follow 26.2's moves: a file that
     moved after delivery would no longer match the Read that happened before the move. The
     emitter already holds the entity, so it records the path at emission.
   - Adding a field under the same `v` would make a v1 event's missing `path` ambiguous: was the
     event written before this task, or does the entity have no path? So `v` becomes 2,
     `RECALL_EVENT_FIELDS_V2 = RECALL_EVENT_FIELDS_V1 + ("path",)`, and the V1 tuple stays as it
     is. No consumer of the tuple has shipped (19.2 is pending), so this is the cheap moment.
4. **D4: 19.2 counts none of it until it is measured.** {#d4}
   - Derived `tool` records never enter `recall-events.jsonl`, so 19.2's fold never sees them.
   - 19.2 R1's route for a new evidence kind still holds: a migration adds its own column. That
     route opens only after [[#r12]]'s precision band says so. The column's weight comes from
     the measured precision. It is never the `w_e: 2` default (19.2 R7; 32dde06 item 3 made
     the weight a read-time parameter, which is what lets it differ).
5. **D5: no new verb, command or flag.** {#d5}
   - `telemetry` is a `harness` entry in `verbs.LEGACY_UNPAIRED`, and `--agent-usage` already
     exists. This task adds report lines and no agent-callable capability, so verb parity and
     the generated CLI tree do not change.
   - The window `W` is a committed constant, not a flag ([[#r4]]).

## Requirements {#requirements}

1. **R1: the ring records what the join needs.** Every ring event gains `t`, the sub-second epoch
   that the input event already carries (21.1 R9). `Stm.record` stamps it, so every writer of
   the ring gets it: the shell hook, the sweep's `abandoned` events, and 24.2a / 24.6's observe.
   A `tool` event also gains three fields:
   - `tool`: the envelope's `tool_name`.
   - `cwd`: the envelope's `cwd`, used to resolve relative paths in a Bash command.
   - `t_start`: the parked PreToolUse record's `t`, read from `inflight_end`'s return value.
     When nothing was parked it is null, and the event counts under `order_from_end`.

   No extra file is opened and no extra read is made: the fields ride the existing append.
   {#r1}
2. **R2: `path` on every delivered and retrieved event (v2).**
   - Every emitter writes `path`: `telemetry.norm_path` of the item's `Entity.path`, or null
     when the entity has none (a term concept). The item builders already hold the entity:
     `context._item` / `bundle_items` (anchor, attached memory, group entries); `scan.py` through
     the context bundle; `telemetry.recall_item` (recall hits, through `Store.item_meta` with
     `path` added to `context.ITEM_META_FIELDS`).
   - `emit_recall_events` stamps `v: 2`.
   - R5's `malformed` rule does not change. `_EVENT_REQUIRED` does not gain `path`.
   {#r2}
3. **R3: ONE matcher, `telemetry.tool_use_matches(tool_event, delivered_index) -> list[(key,
   match_on)]`.** A ring `tool` event matches a delivered item under these rules, applied in
   order:

   | tool (ring `tool`) | match_on | rule |
   |---|---|---|
   | Read, Edit, Write, MultiEdit, NotebookEdit | `path` | `norm_path` of any `refs` entry equals the item's `path` |
   | Grep | `path` | its `path` input (from `detail`) equals the item's `path` |
   | Grep | `name` | a whole token of its `pattern` equals the item's `name`. Tokenised by 21.1 R12's `_NOTE_TOKEN_RE` and gated by `_matchable`, so this is the focus-note matcher and not a new one |
   | Glob | `glob` | the item's `path` basename appears literally in the pattern's last component, AND `fnmatch(path, pattern)` (`**/*.py` alone matches nothing) |
   | Bash | `bash_path` | a `refs` path, resolved against the event's `cwd` (or against the store root's parent when `cwd` is null, counted `cwd_fallback`), equals the item's `path` |
   | Bash | `bash_name` | a whole token of `detail` equals the item's `name` (same tokeniser and gate) |
   | Agent / Task | `name` | a whole token of the `prompt` in `detail` equals the item's `name` |
   | any other tool | none | not matched; counted per tool name in `tool_events_unmatched_by_tool` |

   - **Explicit calls are skipped.** This applies to any tool whose name starts with
     `mcp__refmatrix__`, and to a Bash command whose first `rmx` invocation is `context`,
     `memory get` or `focus note`. Those are R12's explicit evidences. Matching them here would
     count one act twice. They are counted (`skipped_explicit_tool_calls`) and never matched.
   - **Other `rmx` commands match as Bash.** That includes `rmx grep`, the shim's target.
   - **Memory items.** A memory's `path` is its source file, so a Read of
     `memory/feedback_x.md` is a `path` match. Its `name` matches under the name rules.
   {#r3}
4. **R4: order and window.** A tool event `T` can credit a delivered event `D` only when all of
   these hold:
   - same session;
   - `T.t_start` (or `T.t`, counted `order_from_end`) is strictly after `D.ts` (UTC, R10). The
     ring's local naive `ts` is used only for legacy lines ([[#r10]]);
   - `lag_turns(D, T) ≤ W`, with `W = telemetry.TOOL_USED_WINDOW_TURNS = 2`. `lag_turns` is the
     number of the session's `input` events (merged across its subject rings by `t`) in
     `(D.ts, T.t_start]`.
   - **Reads before delivery never count.** A match whose `T` precedes `D` sets `prior_touch` on
     that key for every LATER delivery of it in the session. A credited use with `prior_touch`
     is still a use, but the report shows it separately ([[#r8]]).
   - **Matches beyond the window.** A match with `lag_turns > W` credits nothing. It appears in
     the lag histogram as `>W`.
   - **Subject rings.** A session's events are the union of `<session>.jsonl` and every
     `<session>__<subject>.jsonl` (`stm._partition_key`), merged by `t`. Each ring's own turn
     counter is not used.
   - **Residual, counted as `anchor_race`.** A prompt-time delivery whose prompt's own `input`
     line was written AFTER the delivery (the input hook ran slower than scan-prompt). The
     delivery is still credited, but its same-turn calls read `lag_turns = 1` instead of 0.
   {#r4}
5. **R5: attribution and dedupe.** Each delivered event is credited at most once, by the
   earliest qualifying `T`. A `T` credits the deliveries of its key (`name`, `kind`, `scope`) in
   the most recent delivering turn before it. Deliveries of that key in the same turn on
   different channels (scan_prompt and prompt_recall answering one prompt) are each credited.
   Older deliveries of the key stay uncredited, so a key that scan_prompt re-delivers every
   prompt lowers the per-event rate. The report also prints a per-distinct-key rate, so the
   re-delivery effect is visible instead of being guessed at. {#r5}
6. **R6: explicit uses are attributed to the delivering channel.** An R12 `used` event is counted
   under the channel of the delivered event its `ref_query_id` points to (looked up among the
   window's delivered events). It is not counted under its own `channel` field, which is
   `context` for `context_by_name`. A `ref_query_id` with no delivered event in the window is
   counted `explicit_ref_unresolved`. {#r6}
7. **R7: a control.** The same matcher, window and ordering run over `retrieved` events that have
   no `delivered` event for the same `query_id` and key: retrieved and then trimmed, so the
   agent never saw them. Their "touch" rate is the base rate at which the agent reaches a
   relevant file anyway.
   - The report prints `lift = rate_tool − control_rate`.
   - Stated bias: trimmed items rank lower, so the control under-estimates the base rate and the
     lift over-estimates the effect.
   {#r7}
8. **R8: the report.** `agent_usage_report` gains a `used by channel` block. Per delivering
   channel, over the window:
   - `delivered`, `eligible` (= `delivered` minus [[#r9]]'s exclusions);
   - `used_explicit` per R12 evidence; `used_tool`; `used_any` (the union per delivered event);
   - `rate_any = used_any / eligible`, printed with both numbers and a percentage;
   - `used_tool` split by `tool` and by `match_on`, and by `prior_touch` (yes / no);
   - the `lag_turns` histogram (0, 1, 2, `>W`) and `censored`: eligible deliveries with fewer
     than `W` later `input` events in their session. These stay in the denominator, and their
     count is shown;
   - per-distinct-key: `distinct_used / distinct_eligible`;
   - the control and the lift (R7).

   Deliveries come from the store's own file AND the global file, filtered to `root` = this
   store's root through R5's `row_provenance`. A global memory delivered in this project's
   session therefore joins this project's ring, and is reported per `scope`. {#r8}
9. **R9: no silent drops.** One `used-by-channel exclusions` line, every count printed even when 0:
   - `no_session`;
   - `no_ring` (the session has no ring file under this root, for example after `rmx focus
     clear`);
   - `precompact_gated` (d5d);
   - `no_path` (the v2 entity has no path; name rules only);
   - `path_from_catalog` and `path_unresolved` (legacy, [[#r10]]);
   - `order_ambiguous`, `order_from_end`, `anchor_race`, `cwd_fallback`;
   - `ring_unparseable` (ring lines that are not JSON);
   - `skipped_explicit_tool_calls`, `detail_truncated` (tool events whose `detail` reached
     `DETAIL_MAX`);
   - `tool_events_unmatched_by_tool`.

   The identity `delivered = eligible + no_session + no_ring + precompact_gated` is asserted by
   the report itself. A mismatch prints `identity-broken` and the report exits 1. {#r9}
10. **R10: legacy data (the window the user already asked about).**
    - **v1 delivered events.** Their `path` is resolved from the read snapshot by `entity_id`
      (the normal CLI read path, never a `Store()` open on the active slot) and counted
      `path_from_catalog`. An id that is not found is counted `path_unresolved`, and that event
      falls back to the name rules.
    - **Ring lines without `t`.** They are ordered by their local `ts`, converted with
      `time.mktime`. A tie with `D.ts` at one-second resolution is counted `order_ambiguous`
      and credits nothing.
    - **What this gives.** The report gives a number for 2026-11-10 onward on the day it ships.
      That number is marked `legacy-ordered=<n>`, so it is not read as being as exact as v2 data.
    {#r10}
11. **R11: no hook emits.** After this task, a `used` event with an evidence other than R12's
    three appears in no `recall-events.jsonl`. `rmx focus hook` opens no `recall-events.jsonl`
    and makes no `delivered_in_session` call. R12's sentence "a `hook` call never emits `used`"
    stays true without an exception clause. {#r11}
12. **R12: pre-registered precision bands (before any consumer counts it).**
    - **The sample.** After the code merges, a frozen window of ≥ 50 credited `(D, T)` pairs is
      drawn uniformly. It is stratified by `match_on`, with ≥ 10 per stratum where available.
    - **The labelling.** Each pair is labelled "the delivery plausibly caused the tool call"
      yes / no, from the local transcript (d8f: raw text stays local; the labels, the sample's
      hash and the counts are committed). The labeller is [[#od-2]].
    - **The bands.** Recorded here before labelling ([[feedback_go_no_go_ranges_not_predrop]]'s
      rule):

    | precision (pooled) | action |
    |---|---|
    | ≥ 0.80 | 19.2 may add a `used_tool` column (a migration, 19.2 R1), weight `w_tool = round(2 × precision, 1)` |
    | 0.50 to 0.80 | report-only; 19.2 does not count it; strata below 0.50 are dropped from the matcher first (the Bash and name legs are the expected candidates) |
    | < 0.50 | the matcher is revised and re-measured; nothing downstream changes |

    A stratum below 0.50 is shown as such in the report's `match_on` split even in the top band.
    {#r12}

## Acceptance criteria {#acceptance}

Every AC runs inside 23.0's sandbox and ends by asserting that the line counts of the live
`.refmatrix/query.log`, `~/.refmatrix/query.log`, `.refmatrix/recall-events.jsonl`,
`~/.refmatrix/recall-events.jsonl` and the live `.refmatrix/stm/*.jsonl` are unchanged. The ring
and the events are produced by the REAL commands: `rmx focus hook --event tool-pre|tool|input`
fed real-shaped envelopes on stdin, and `rmx scan-prompt` / `rmx memory recall --stdin-json`
against a tmp store. No ring or event line is hand-written, except in AC-9, which is about legacy
lines.

1. **AC-1 (R1): ring fields.** A `tool-pre` then `tool` envelope pair for a Read of `F` (with
   `cwd` set) writes one ring `tool` line carrying `t`, `t_start` (= the parked `t`), `tool:
   "Read"` and `cwd`. A `tool` envelope with no prior `tool-pre` writes `t_start: null`. **RED
   at HEAD:** the line has no `tool`, `cwd`, `t_start` or `t`. {#ac-1}
2. **AC-2 (R2, D3): `path` and `v: 2`.** A real scan-prompt over a tmp store holding code file `F`
   writes delivered events for `F`'s symbols with `v == 2` and `path == norm_path(F)`. A real
   `memory recall --stdin-json` over a tmp memory dir writes a `kind=memory` delivered event
   whose `path` is the memory's source file. A term concept with no path writes `path: null`.
   `RECALL_EVENT_FIELDS_V1` is unchanged and `RECALL_EVENT_FIELDS_V2` adds `path`. **RED at
   HEAD:** no `path` field, `v == 1`. {#ac-2}
3. **AC-3 (R3, R4, R8): the end-to-end use.** Turn 0: scan-prompt delivers symbol `S` of `F`.
   Then a Read of `F`. `--agent-usage` prints, under `scan_prompt`: `used_tool=1`, tool `Read`,
   `match_on=path`, `prior_touch=no`, `lag 0=1`, and `rate_any` with `eligible` as its
   denominator. **RED at HEAD:** there is no `used by channel` block. {#ac-3}
4. **AC-4 (R4): before delivery never counts.** (a) A Read of `F` at turn 0, then a delivery of
   `S` at turn 1, and no later Read: `used_tool=0`. (b) As (a), plus a Read of `F` at turn 1:
   `used_tool=1`, `prior_touch=yes`. (c) A Read of `F` whose `t_start` precedes the delivery's
   `ts` but whose PostToolUse lands after it (a slow Read started before an MCP context call
   returned): not credited. **RED at HEAD:** no block; with an ordering mutation, (c) is
   credited. {#ac-4}
5. **AC-5 (R4): the window.** A Read of `F` three prompts after the delivery credits nothing and
   lands in `lag >2`. At two prompts after, it is credited. `censored` counts a delivery made in
   the session's last prompt. **RED at HEAD:** no block. {#ac-5}
6. **AC-6 (R5): attribution and dedupe.** `S` delivered by scan_prompt at turns 0 and 1, and one
   Read at turn 1: per-event `1/2`, distinct `1/1`. `S` delivered at turn 2 by both scan_prompt
   and prompt_recall, then a Read: both channels credited, and the `any channel` row counts the
   key once. Two Reads after one delivery: credited once. **RED at HEAD:** no block. {#ac-6}
7. **AC-7 (R3): each matcher leg, positive and negative.**
   - Grep with `path=F` is credited. A Grep whose pattern is `used_events|other` is credited for
     the delivered name `used_events`.
   - A Grep for `run` against a delivered name `run` is NOT credited (`_matchable`).
   - Glob `**/telemetry.py` is credited for `src/refmatrix/telemetry.py`; Glob `**/*.py` is not.
   - Bash `sed -n 1,40p src/x.py` with `cwd` = the project dir is credited `bash_path`.
   - Bash `rmx context S` and a tool `mcp__refmatrix__rmx_context` are each counted in
     `skipped_explicit_tool_calls` and credit nothing.
   - An Agent tool whose prompt names a delivered memory is credited `name`.
   - A Read of a memory's source file is credited for that memory.

   **RED at HEAD:** no matcher. {#ac-7}
8. **AC-8 (R6): explicit uses go to the delivering channel.** scan_prompt delivers `S`, then
   `rmx context S` (agent) emits R12's `context_by_name`. The report counts it under
   `scan_prompt used_explicit context_by_name=1`, not under `context`. A `used` event whose
   `ref_query_id` matches no delivered event in the window is counted `explicit_ref_unresolved`.
   **RED at HEAD:** the report lists it as `events context used: 1`. {#ac-8}
9. **AC-9 (R9, R10): every exclusion is counted and the identity holds.**
   - One fixture holds: a delivered event with `session: null`; one whose session has no ring; a
     `precompact` delivery; a v2 term concept with `path: null`; a v1 event whose `entity_id`
     is in the tmp catalog (`path_from_catalog`) and one whose id is not (`path_unresolved`); a
     legacy ring line without `t` tying `D.ts` to the second (`order_ambiguous`); a Bash
     without `cwd` (`cwd_fallback`); a non-JSON ring line; and a `detail` of exactly
     `DETAIL_MAX`.
   - Each count is printed with its exact value. `delivered = eligible + no_session + no_ring +
     precompact_gated` holds.
   - A mutation that drops the `no_ring` term prints `identity-broken` and exits 1.
   - The v1 and legacy lines here are the one place lines are hand-written. They copy the field
     sets a HEAD-era emitter and hook wrote.

   **RED at HEAD:** none of the counts exist. {#ac-9}
10. **AC-10 (R7): the control.** A `retrieved`-only item (trimmed by the payload cap) whose file is
    later Read counts in the control and not in `used_tool`. `lift` is printed as `rate_tool −
    control_rate`. **RED at HEAD:** no control. {#ac-10}
11. **AC-11 (R8): global scope.** A global memory delivered by prompt_recall in a session of this
    store (event in the GLOBAL file, `root` = this store) whose source file is then Read is
    credited and reported under `scope=global`. The same event with a different `root` is not
    read. **RED at HEAD:** the report reads only the project file. {#ac-11}
12. **AC-12 (R1, R4): subject rings merge.** With `rmx focus subject` switched between the
    delivery and the Read, the Read lands in `<session>__<subject>.jsonl` and is still credited
    at `lag 0`. **RED at HEAD:** no block. With a mutation that reads only the bare-session
    ring, it is not credited. {#ac-12}
13. **AC-13 (R11): no hook emits (a guard, proven by mutation).** After AC-3's flow, no
    `recall-events.jsonl` contains a `used` event outside R12's three evidences. Across the
    `rmx focus hook` calls, the event files' size and mtime are unchanged. A mutation that
    emits from `focus_hook` fails this AC. This passes at HEAD by construction; its RED is the
    mutation. {#ac-13}
14. **AC-14 (R4): subagent events.** When ring lines carry `origin` (19.0 R2), a non-parent tool
    event credits nothing, is counted `subagent_tool_events`, and the footer residual is
    removed. Until 19.0 R2 ships, the footer says the rate includes background subagents' tool
    calls. **RED at HEAD:** no footer line about tool events. {#ac-14}
15. **AC-15: run once on real data (the benchmark path IS the production path).** The dev-tree
    report (`.venv-eval`) is run against an APFS clone, made under a `mkdtemp()` root, of this
    project's `.refmatrix/` logs, `stm/*.jsonl`, the global events file and the read snapshot.
    Nothing is written to the live tree.
    - The output and its wall time go into the implementation summary, with the window
      2026-11-10 onward and the legacy counts of R10.
    - The run executes the same `agent_usage_report` function the tests drive, with no bespoke
      path.
    - It is not a pass/fail gate on the number. It IS a gate on the run: exit 0, identity
      holds.
    {#ac-15}

## Mutations {#mutations}

Each mutation must make at least one AC FAIL, not hang. Each restore runs as its own command.
- `>` to `>=` in R4's ordering: AC-4 (c) credits.
- `t_start` replaced by `t`: AC-4 (c) credits.
- The window `W` raised to 3: AC-5 credits the third-prompt Read.
- Credit every older delivery of the key: AC-6 per-event reads `2/2`.
- The explicit skip removed: AC-7 credits `rmx context S`, and AC-8's `scan_prompt` `used_any`
  double-counts.
- Explicit uses attributed by their own `channel`: AC-8.
- `no_ring` dropped from the identity: AC-9 prints `identity-broken`.
- The global file not read: AC-11.
- The bare ring only: AC-12.
- `focus_hook` calls `emit_recall_events`: AC-13.
- `path` written as the raw `Entity.path` (not `norm_path`): AC-2 on a `/tmp`-spelled root.

## Files to modify {#files-to-modify}

| file | change |
|---|---|
| `src/refmatrix/stm.py` | `Stm.record` stamps `t` on every event (R1) |
| `src/refmatrix/cli.py` | `focus_hook` tool branch: `tool`, `cwd`, `t_start` from `inflight_end`'s record (R1); no other change |
| `src/refmatrix/context.py` | `_item` / `bundle_items` carry the entity's path; `ITEM_META_FIELDS` gains `path` (R2) |
| `src/refmatrix/store.py` | `Store.item_meta` selects `e.path` (R2) |
| `src/refmatrix/telemetry.py` | `RECALL_EVENT_FIELDS_V2`, `v: 2` in `emit_recall_events`, `path` in `_item_fields` / `recall_item` (R2); `TOOL_USED_WINDOW_TURNS`; `tool_use_matches` (R3); `derive_tool_used(root, *, global_root, since, until) -> ToolUsed` returning used-shaped records (`stage=used`, `evidence=tool`, `tool`, `match_on`, `ref_query_id`, `lag_turns`, `lag_s`, `prior_touch`) plus the R9 counts, never written to any file (R4-R7, R9, R10); the `used by channel` block and the identity check in `agent_usage_report` (R8, R9) |
| `tests/test_task21_5_tool_used.py` | AC-1 to AC-14 |
| `workflow/implementation_summaries/task-21.5-tool-used-signal.md` | AC-15's run |

There is no `verbs.py` change and no `hooks.py` change (D5, R11). `rmx install-hooks --check`
stays clean because the generated hook commands are unchanged.

## Test strategy {#test-strategy}

- **Sandbox.** Tests use 23.0's fixtures: `$HOME`, the global root, the registry and LaunchAgents
  are redirected before import, and spawned `rmx` children refuse sockets outside the tmp dir.
  Tmp roots are short (macOS `sun_path`).
- **Real producers.** The ring comes from the real `rmx focus hook` command and the events from
  the real scan-prompt / recall / context commands, so the test exercises the hook and emitter
  code that production runs. A unit test of `tool_use_matches` alone is allowed in addition to
  this, never instead of it.
- **RED first.** The test file is run against unfixed HEAD and its failures are read: every AC
  except AC-13 must fail there, for the stated reason.
- **Output.** Runs are captured to `workflow/review-output/pytest-task21-5.log`.
- **Regression.** The full suite runs before merge, because the `v: 2` change touches every
  emitter, and 21.1's schema tests must pass with `V2`.

## Open decisions {#open-decisions}

1. **OD-1: does 24.6 R4's `tool_result` evidence stay?** {#od-1}
   - **The conflict.** [[task-24.6-context-and-observation#r4]] (d6) plans to EMIT `used` from
     the mod's `tool.call` observe, with evidence `tool_result`. It finds delivered names in the
     tool's RESULT text. That conflicts with D1 and R11: it is an observe-time emitter, and it
     would make the R12 hook rule need an exception. It is also a weaker signal. A Grep or Read
     result that merely contains a delivered name credits it, which is re-exposure rather than
     use. And it is a second "tool evidence" beside this task's.
   - **Recommendation.** Amend 24.6 R4. The mod's observe writes R1's ring fields, through the
     same `Stm.record`, and emits no `used`. If result-text evidence is wanted, it becomes a
     second `match_on` leg of R3, derived from a result digest that the observe stores in the
     ring, and measured by R12 before anything counts it.
   - **Owner.** The user, because plan-24 is a decided direction.
2. **OD-2: who labels R12's precision sample?** {#od-2}
   - **Recommendation.** An agent that never reads the matcher code labels it from local
     transcripts (d4c's independence rule), and the user spot-checks 10 pairs.
   - **Alternative.** The user labels all ≥ 50.
3. **OD-3: if a live consumer ever needs the signal, how does it get it?** {#od-3}
   - **Recommendation.** It is NOT materialised now. If 19.2 or 19.6 later needs it live, a
     plan-23 drain tick calls `derive_tool_used` over the newly folded window and writes
     `stage=used, evidence=tool` events through `emit_recall_events`, with the matcher version
     in `policy`. It never uses a hook. This needs its own task after R12's top band.
4. **OD-4: rename 21.1 R12's reserved `file_read` evidence to this task's `tool`?** {#od-4}
   - **Why it needs the user.** 19.6's read-back definition (d9v, user-confirmed;
     [[task-19.6-phased-context-and-topic-cache#ranges]]) already counts "a later tool call whose
     input names it (`file_read`)", computed by its offline transcript scorer. This task
     computes the same clause from the ring. Two implementations of one clause would be two
     ways to do X.
   - **Recommendation.** One decision-log row:
     - `score_readback.py` imports `telemetry.tool_use_matches` for that clause;
     - the evidence is named `tool` everywhere;
     - 21.1 R12's reservation names `tool` (owned here) and `cited_in_answer` (still 19.6's,
       transcript-only).

     The definition's wording does not change; only its source and its owner do. d9v says that
     changing a confirmed item needs a new row, hence the user.
5. **OD-5: the window `W = 2` and the bands in R12.** {#od-5}
   - **Recommendation.** Confirm them as written. They are pre-registered numbers of the same
     class as d4d and d9v, so they are the user's to confirm before AC-15's run is read.
   - **What changing `W` costs.** It is a one-constant change that rewrites no data (D1). The
     lag histogram shows what any other `W` would have given.

Spec-settled here, and not needing the user:
- the `v: 2` bump (D3);
- the control (R7);
- the explicit-call skip (R3);
- attribution by `ref_query_id` (R6);
- no new verb (D5).

## Non-goals {#non-goals}

- `cited_in_answer`: a delivered name in the assistant's reply. It stays 19.6's
  transcript-only evidence.
- Any change to R12's three explicit evidences, their lookup, or their destination.
- Any change to what is delivered. That is 19.1's and 25.1's business; this task is the
  instrument they will be judged by.
- A live counter of any kind ([[#d4]], [[#od-3]]).
