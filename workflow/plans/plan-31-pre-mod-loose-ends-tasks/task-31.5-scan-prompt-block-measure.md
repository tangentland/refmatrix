---
gmd: "0.1"
id: task-31.5-scan-prompt-block-measure
title: "Task 31.5: the per-prompt injection, measured per block — capture the full payload, score discovery calls against it, band each block kind, then cut and tighten"
tags: [task, plan-31, scan-prompt, recall, injection, stm, telemetry, measurement, freeze]
metadata:
  node_type: task
  status: drafting
  plan: plan-31-pre-mod-loose-ends
  created: 2026-11-15
  updated: 2026-11-15
---

# Task 31.5: the per-prompt injection, measured per block {#root}

> Plan: [[plan-31-pre-mod-loose-ends]] ([[plan-31-pre-mod-loose-ends#t5]]; Q27 = b, now in
> [[pop-finished]]).
> Status: Drafting. Written by ch-architect on Fable 5.2, 2026-11-15; ch-bsd spec review next
> ([[orchestration#planning]]).
> Depends on: 0.84.0 deployed (the block order, the 9,500 B command budget, the grounded-topic
> filter and the unchanged-composite marker; [[bsd-scanorder-r1-ca22b79]], ruling L120 in
> [[plan-review-2026-11-13#lead]]).
> Five sub-steps in one spec: **S0** capture ([[#s0]]), **S0b** discovery-call scoring
> ([[#s0b]]), **S1** per-block bands ([[#s1]]), **S2** cut and tighten ([[#s2]]), **S3**
> ablation, conditional ([[#s3]]).
> Two releases: **release A** carries S0 and one composite fix ([[#r2-0]]); **release B**
> carries S2. The measurement window runs between them.
> Runs ahead of plan-10's dedup (T3 in [[plan-of-plans#freeze]]). Whether that dedup stays
> pre-mod is open (Q32 in [[plan-of-plans#questions]]); nothing here depends on the answer.
> Feeds 21.5 phase M and plan-30's 30.6 ([[#handoff]]).
> Proposed decisions: `plan-31 D1`-`D6` ([[#decisions]]). None is decided here; each is
> entered in [[plan-of-plans#decisions]] by the lead before it is amended into this spec.
> Sibling specs on another branch (31.1, 31.2, 31.6) are written as code, not links.

rel: part-of -> [[plan-31-pre-mod-loose-ends]]
rel: implements -> [[plan-31-pre-mod-loose-ends#t5]]
rel: depends-on -> [[task-21.1-context-usage-telemetry]]
rel: depends-on -> [[task-25.1-recall-hook-byte-budget]]
rel: derives-from -> [[task-21.5-tool-used-signal]]
rel: derives-from -> [[measurement-task-21.5-r12-pilot-2026-11-13]]
rel: derives-from -> [[bsd-scanorder-r1-ca22b79]]
rel: related-to -> [[measurement-injection-already-held-2026-11-13]]
rel: related-to -> [[design-note-tool-keyed-context-2026-11-15]]
rel: related-to -> [[plan-10-injection-dedup]]
rel: related-to -> [[task-21.7-behavioural-use]]
rel: related-to -> [[task-25.3-stm-ref-admission-and-helix-repeat]]
rel: related-to -> [[plan-30-materialisation#t6]]
rel: reinforces -> [[feedback_injection_presentation_rules]]
rel: reinforces -> [[feedback_no_raw_prompts_in_public_repo]]
rel: reinforces -> [[feedback_go_no_go_ranges_not_predrop]]
rel: reinforces -> [[feedback_measure_the_path_users_run]]
rel: reinforces -> [[feedback_causal_story_before_evidence]]
rel: reinforces -> [[feedback_reuse_shared_stoplist]]
rel: reinforces -> [[feedback_clean_corpus_hides_a_dead_gate]]
rel: recalls -> [[project_1113_used_signal_injection_arc]]

## Why {#why}

Every prompt pays for two injections: `rmx scan-prompt` (up to 9,000 B) and the per-prompt
`rmx memory recall --pack` (up to 4,000 B). The user asked for the scan-prompt injection to be
reduced and tightened, not removed, and for the STM composite to be judged on value
([[plan-31-pre-mod-loose-ends#t5-ask]]). {#why-ask}

Nothing measured so far can support a cut:

- **Past data saw a truncated payload.** The 2026-11-13 pilot
  ([[measurement-task-21.5-r12-pilot-2026-11-13]]) measured what reached the model. What the
  hooks produced and then dropped was never logged. A block that looks unused may be a block
  whose useful part was the part being cut.
- **The pilot did not split by block.** Its 7% CAUSED and 19% CAUSED + INFORMED are over all
  blocks ([[measurement-task-21.5-r12-pilot-2026-11-13#p-w]]).
- **The user's score is a different question.** "Did the agent touch an injected item" starts
  from the injection. "Did the injection save the agent a search" starts from the agent's
  demonstrated need: a discovery call. Nothing counts that today.
{#why-list}

So the order is: capture the whole payload, score discovery calls against it, read bands that
were written first, then cut. {#why-order}

## Sized at `f3a508f` (2026-11-15) {#sized}

Read-only, counts and byte totals only, by `workflow/measurements/task-31.5-sizing/sizing.py`
(committed with this spec; it prints no prompt, command or payload text). Input: the 15 session
transcripts of this project, 2026-10-14 to 2026-11-15, deduplicated by record `uuid` (a resumed
session's file repeats earlier records). The live session was still running, so the last row
grows. The regime instants are approximations read off the transcripts, not log-verified.
{#sized-method}

| Regime | What delivered | Prompts | Sessions | Scan output cut by `--max-bytes` | Recall previewed by the harness | Discovery calls per prompt (mean / sd / median) |
|---|---|---|---|---|---|---|
| A: to about 2026-11-14 01:00Z | no rmx byte cap; Claude Code previews any hook over 10,000 units | 791 | 11 | 0 (no cap); 50 scan outputs previewed | 582 of 791 (74%) | 3.24 / 5.92 / 1 |
| B: 0.83.0, to the 0.84.0 deploy | scan capped at 4,499 B, content first; recall packed to 4,000 B | 90 | 3 | 46 of 90 (51%) | 5 of 90 | 6.31 / 8.64 / 3 |
| C: 0.84.0 | 8,999 B, named identifiers first, grounded and on-change composite | 19 so far | 1 | 4 of 19 | 0 | 6.00 / 8.31 / 4 |
{#sized-table}

What the sizing settles:

- **A week is about 430 prompts in 7 sessions.** The seven days to 2026-11-15 held 433
  hook-fired prompts in 7 sessions of 36 to 119. {#sized-week}
- **Discovery calls per prompt are heavy-tailed and cluster by session.** In regime A, 35% of
  prompts have none, the 90th percentile is 9 and the maximum is 55. Per-session means run from
  1.5 to 9.3 with no injection change between them. The effective sample of any before/after
  comparison is therefore close to the number of sessions, not the number of prompts
  ([[#limits]]). {#sized-noise}
- **The transcript already records delivered against printed.** Each `hook_success` record
  holds `stdout` (what rmx printed) and `content` (what Claude Code delivered: the whole text,
  or a preview of about 2.2 kB). So for past data, "printed but previewed away" is measurable
  from transcripts alone. "Produced by rmx and dropped before printing" is not, in any regime:
  only S0's capture sees it. {#sized-transcript}
- **The cap did what the user saw.** In regime A the symbol sections were 65% of scan bytes and
  content matches 23%. Under regime B's cap, content was 64% and symbols 25%. {#sized-cap}
- **Two numbers in the plan do not describe the corpus.** [[plan-31-pre-mod-loose-ends#t5]]
  quotes the composite at "59% of scan-prompt bytes and 100% repeated". That is one payload from
  one probe on 2026-10-01 (3,690 of 6,265 B, [[bsd-plan8-9-10-r5-e0b7df6]]). Across the
  transcripts, by a header split, the composite is about 11% of scan bytes in regime A (5% to
  14% by session) and is present on 261 of 775 scan outputs, because this store's hook passes
  `--composite-every 3`. Exact-text repetition between consecutive composites is rare; whether
  the member sets repeat (0.84.0's signature) was not sized. S1 measures both
  ([[#r1-1]]). {#sized-composite}
- **The hook is already slow.** bug-182 ([[bug_registry#registry]]): `scan-prompt --timeout 5`
  ran p50 3.3 s and p95 13.9 s on 2026-11-08/09. Anything the capture adds before the payload
  is printed lands on that. {#sized-latency}

## What already logs what {#existing}

| Instrument | Holds | Lacks |
|---|---|---|
| `.refmatrix/recall-events.jsonl` (21.1) | per item: `retrieved` and `delivered` events, byte spans, `block_sha` of the payload, `query_id`, session, turn | which block an item was in; why a retrieved item was not delivered; any text; the composite's items (the composite never enters `trace`) |
| `.refmatrix/query.log` | one row per call: kind, the first 200 characters of the prompt, timing, `query_id` | blocks |
| Claude Code transcript | per hook command: `stdout`, delivered `content`, duration; every later tool call and reply | anything rmx dropped before printing; the rmx version |
{#existing-table}

No log row carries the rmx version, so a regime is identified today only by markers in the
output. The capture record adds it ([[#r0-2]]). {#existing-version}

## What the measurement can and cannot separate {#limits}

Written before any number, so the result cannot be argued into a story afterwards.

**It can separate:**

1. Delivered from dropped, per block and per cut (byte fit, token stop, unchanged composite,
   composite cadence). Exact, from the capture.
2. For each discovery call: its target was in a delivered block, only in a dropped block, or in
   neither. Mechanical and exact for calls with an extractable target; the rest are counted as
   `unscorable`.
3. "The content is useless" from "the useful content was the part being cut": per block kind,
   the use rate of delivered blocks beside the avoidable rate of dropped ones.
4. Repetition: the same block text, or the same composite member sets, on consecutive prompts.
{#limits-can}

**It cannot separate:**

1. **A call that did not happen.** An avoided search leaves no trace. "Discovery calls
   avoided" is therefore never observed. It is bounded from two sides: the outcome trend (item
   2 below) and the counterfactual classes (`avoidable`: a call that delivery could have
   saved). `ignored` shows that delivered content does not reliably prevent a call, so
   `avoidable` is an upper bound on what lifting a cut would save.
2. **Before from after 0.84.0, at the size of effect that is likely.** Three things changed in
   that release (order, the 9,000 B cap, the composite gate); 25.1's recall pack changed a day
   earlier; the task mix changes by session; regime B is 90 prompts in 3 sessions. With
   per-prompt sd of 6 to 9 around means of 3 to 6, and sessions that differ sixfold on their
   own, a week on each side can show a halving of discovery calls per prompt and cannot show a
   20% shift. The before/after table is **descriptive**. No band reads it.
3. **Read from unread.** No instrument sees whether the model attended to a block. `unread`
   means "no trace of it in any later call or reply", nothing more.
4. **Use that names nothing.** A memory's rule followed, a mistake avoided, a decision reused:
   the tool legs cannot see it ([[task-21.7-behavioural-use#why]]). This under-credits the
   recall block most, which is why this task never cuts recall below a shrink
   ([[#actions]]).
5. **Delegated discovery.** No injection reaches a subagent, and this project's main loop is an
   orchestrating lead that dispatches agents (0.13 to 0.47 dispatches per prompt by regime). A
   search an agent ran is not a main-loop discovery call. Dispatches per prompt are reported
   beside every rate, and prompts whose turn dispatches an agent are a stratum.
6. **Other populations.** The result describes an orchestrating lead in this repository. It
   says nothing about a coding agent in another repo. cliquedb is reported only if it reaches
   100 captured prompts in the window.
7. **Required reads.** A `Read` the harness demands before an `Edit` of the same file cannot be
   avoided by any injection. It is excluded, and counted ([[#r0b-2]]).
{#limits-cannot}

## S0: capture the full payload by block {#s0}

### R0.1: what "full, uncapped" means {#r0-1}

The capture records the render the pipeline produces under its **retrieval** parameters
(`max_concepts`, `per_concept_tokens`, `content_tokens`, the composite's own token budget, the
cross-section dedup) with the **delivery cuts** lifted. A block is one unit `fit_blocks` keeps
or drops whole. Each block carries one state:

| State | Meaning | Text stored |
|---|---|---|
| `delivered` | in the payload the command printed | yes |
| `dropped_bytes` | rendered, then dropped by the `--max-bytes` fit | yes |
| `dropped_tokens` | cut by the `--max-tokens` section stop: the bundle that tripped it, and every bundle the stop prevented from being built | yes ([[#r0-5]]) |
| `suppressed_unchanged` | the composite, not rendered because its member-set signature equals the last delivered one | no: the signature only |
| `suppressed_cadence` | the composite, skipped by `--composite-every` | no |
{#r0-1-states}

Block kinds: `symbol_named` (tier 1: bundles for identifier-shaped tokens the prompt names),
`content` (the content-ranked bundle), `symbol_other` (tier 3: plain words and PPR
expansions), `composite`, and for the recall channels `recall_hit` (one per hit: its hook line,
and its body when one was printed). Trailers and the `[truncated by --max-tokens]` marker are
recorded as kind `marker`. The plan's "symbol context" is split in two because 0.84.0 gave the
two tiers different positions. {#r0-1-kinds}

Rows the cross-section dedup removed are counted per block (`dedup_rows`), not stored.
{#r0-1-dedup}

### R0.2: the record {#r0-2}

One JSON line per call, written by ONE function in `telemetry.py` (the module that owns every
other log writer), after the payload is printed:

- `v`, `ts` (UTC, `event_ts`), `rmx_version`, `channel` (`scan_prompt`, `prompt_recall`,
  `session_start`, `precompact`), `invocation`, `session`, `query_id` (the join key to
  `query.log` and `recall-events.jsonl`);
- `prompt_sha256` and `prompt_chars`. **No field holds the prompt**;
- `budget_bytes`, `max_tokens`, `payload_sha256` (equal to the call's `block_sha`),
  `payload_bytes`;
- `blocks`: in render order, each with `i`, `kind`, `state`, `bytes`, `sha256`, `names` (the
  item names the block carries), `dedup_rows`, and `text` where [[#r0-1-states]] says so. A
  `recall_hit` block carries `name`, `rank`, `mtype`, `scope`, `hook_bytes`, `body_bytes`,
  `body_sha256` and a state of `delivered` (hook line and body), `delivered_hook_only`, or
  `dropped_bytes` (behind the `+N more` trailer). It stores no body text: a memory body is
  addressable by name.
{#r0-2-fields}

A call that produces nothing still writes a record, with an empty `blocks` list: a prompt the
pipeline had nothing for is part of the denominator. {#r0-2-empty}

**What the text carries.** A block's text is the payload text. The payload echoes prompt terms
in its headers (`# refmatrix content matches for prompt: …`) and quotes lines of whatever the
store indexes, as the delivered payload always has. The capture is therefore local runtime
state of the same class as `query.log`, never repository content ([[#r0-4]]). {#r0-2-text}

### R0.3: what the capture must not change {#r0-3}

- The payload: byte-identical with the capture on and off.
- `recall-events.jsonl` and the `query.log` row's existing fields: a bundle built only for the
  capture does not enter `trace`, so `retrieved` counts keep their meaning.
- The composite's "sent" marker: committed only when the composite is delivered, exactly as
  0.84.0 does ([[bsd-scanorder-r1-ca22b79#s3]]).
- The generated hook config: release A changes no hook command, so there is no install window.
- `--format json` and the MCP path write no capture record: they are answers, not hook
  payloads.
{#r0-3-list}

### R0.4: where it lives, its bound, its retention {#r0-4}

- **Where:** `<store root>/injection-capture/capture-<UTC yyyymmdd>.jsonl`, one file per UTC
  day, in the store the call resolved. `.refmatrix/` is ignored by this repository's
  `.gitignore`. Hits from the global store are recorded in the calling project's file with
  `scope: global`.
- **Bound:** 64 MiB per store across all day files. Estimated cost is 15 kB per prompt,
  30 kB at worst, so the bound holds at least 2,000 prompts.
- **Retention:** 42 days, the longest window 21.5 R12 reads ([[task-21.5-tool-used-signal#r12]]).
- **Enforced at write time:** before appending, the writer removes day files older than 42 days,
  then the oldest day files while the total exceeds the bound. It never removes the current
  day's file. Each removal is recorded on the call's `query.log` row (`capture_pruned`).
- **Off switch:** `REFMATRIX_NO_TELEMETRY`, the switch every other telemetry writer obeys.
  Whether the capture is on by default in every store is `plan-31 D1`.
- **Why per-day files and not rename rotation:** two hook commands run in parallel on every
  prompt. Appending to a day file needs no rename, so two writers cannot rotate over each
  other.
{#r0-4-list}

### R0.5: the cost on the hook path, banded before it is measured {#r0-5}

Recording a block that was already rendered costs one append after the payload is printed.
Building the bundles the token stop skipped costs up to four more `build_context` calls before
the command exits, and Claude Code waits for the command. That cost is measured before release
A, on a throwaway store built from `docs/` and `src/refmatrix/`, with the committed synthetic
prompt set ([[#files]]), capture on and off alternating, quiet and under a running suite; the
worse run is read:

| Added wall time, p95 | Action |
|---|---|
| at most 250 ms | ship: every token-cut bundle is built and stored |
| 250 to 750 ms | the cheaper path: the bundle that tripped the stop is stored (it was already built); later ones are recorded as `not_built` with their names only. Re-measure; ship when at most 250 ms |
| over 750 ms after the cheaper path | do not ship; report to the lead with the profile |
{#r0-5-bands}

A `not_built` block has no text and no items. S0b counts a target that matches only a
`not_built` name as `avoidable_unverified`, a separate column. {#r0-5-not-built}

### R0.6: a capture that stops is visible {#r0-6}

The scan hook discards stderr (`2>/dev/null || true`), so a message there reaches nobody.

- The call's `query.log` row gains `capture`: the bytes appended, `off`, or the error text. A
  failed append never changes the payload or the exit status.
- `rmx telemetry --context` prints one `capture:` line: day files, total bytes, newest record,
  and over the report window the captured calls against the hook calls in `query.log`, with the
  error count.
- The measurement does not start below 95% coverage ([[#ac-1-0]]).
{#r0-6-list}

### S0 acceptance criteria {#s0-acceptance}

Tests are in `tests/test_injection_capture.py` unless named. Each runs the real `scan-prompt`
or `memory recall --pack` command on a throwaway store under a short `mkdtemp()` root.

- **AC-0.1 (RED at base): one record per call, every block labelled.**
  `test_a_scan_call_writes_one_record_with_every_block`: a prompt naming two identifiers and
  three plain words yields one line whose blocks carry the kinds of [[#r0-1-kinds]] in render
  order. At base no file exists. {#ac-0-1}
- **AC-0.2 (RED): the delivered blocks are the payload.**
  `test_delivered_blocks_concatenate_to_the_payload`: the `delivered` and `marker` texts, joined
  in order, equal the printed payload; `payload_sha256` equals the `block_sha` of the call's
  recall events. {#ac-0-2}
- **AC-0.3 (RED): each cut is recorded as itself.** Four tests, one per state:
  `test_a_block_the_byte_fit_dropped_is_stored_as_dropped_bytes`,
  `test_bundles_past_the_token_stop_are_built_and_stored_as_dropped_tokens`,
  `test_an_unchanged_composite_is_recorded_as_suppressed_unchanged`,
  `test_a_cadence_skip_is_recorded_as_suppressed_cadence`. If [[#r0-5-bands]] selects the
  cheaper path, the second test asserts `not_built` for the bundles after the one that tripped
  the stop. {#ac-0-3}
- **AC-0.4 (guard, green at base; proven by mutation M0-1): the payload is unchanged.**
  `test_the_capture_never_changes_the_payload`: the same store and prompt give byte-identical
  stdout with the capture on and with `REFMATRIX_NO_TELEMETRY=1`, for a prompt that trips the
  token stop and one that trips the byte fit. {#ac-0-4}
- **AC-0.5 (guard, proven by M0-2): no other log changes.**
  `test_capture_only_bundles_emit_no_recall_events`: the call's `retrieved` and `delivered`
  events are the same set with the capture on and off. {#ac-0-5}
- **AC-0.6 (guard, proven by M0-3): the composite marker follows delivery.** The existing
  `tests/test_scanorder_r2_l120.py::test_s3_a_composite_the_cap_dropped_is_delivered_when_there_is_room`
  stays green, and `test_a_composite_stored_as_dropped_is_sent_on_the_next_prompt` repeats it
  with the capture on. {#ac-0-6}
- **AC-0.7 (RED): recall is captured per hit.**
  `test_a_packed_recall_writes_one_block_per_hit`: 12 hits under a budget that names 8 and
  bodies 2 give 2 `delivered`, 6 `delivered_hook_only` and 4 `dropped_bytes` blocks, and no
  body text anywhere in the record. {#ac-0-7}
- **AC-0.8 (RED): no prompt field.** `test_the_record_has_no_prompt_field`: the record's keys
  are exactly the schema's; `prompt_sha256` is the prompt's hash; a canary token in a prompt
  that matches nothing appears nowhere in the record. {#ac-0-8}
- **AC-0.9 (RED): the bound and the retention hold.**
  `test_old_and_oversize_day_files_are_pruned_and_counted`: with day files dated 50 and 10 days
  back and a total over the bound (bound and clock injected), the 50-day file goes first, then
  the oldest, never the current day; the row's `capture_pruned` names what went. {#ac-0-9}
- **AC-0.10 (RED): a failed capture is countable and harmless.**
  `test_an_unwritable_capture_dir_keeps_the_payload_and_marks_the_row`: stdout and exit status
  are unchanged, the row's `capture` holds the error, and `rmx telemetry --context` prints a
  `capture:` line with one error. {#ac-0-10}
- **AC-0.11 (characterization): JSON and MCP write nothing.**
  `test_json_format_writes_no_capture_record`. {#ac-0-11}
- **AC-0.12 (gate): no hook drift.** `rmx install-hooks --check` is clean on the release A
  tree, and the generated hook block is byte-identical to base (the existing hooks-in-sync
  tests). {#ac-0-12}
- **AC-0.13 (measurement): the cost is inside a band.** The [[#r0-5-bands]] table is filled in
  the implementation summary with p50 and p95, quiet and loaded, and the action taken.
  {#ac-0-13}
- **AC-0.14 (measurement, live, after release A): the capture is the production path.** On the
  deployed build, one real prompt in this project produces a record whose delivered blocks
  match that prompt's `hook_success.stdout` in the transcript (prefix match: the same command
  also prints curator status). Read-only. {#ac-0-14}

## S0b: discovery calls, scored against the injection {#s0b}

The primary score ([[plan-31-pre-mod-loose-ends#t5]] step 0b; the user, 2026-11-15: "one way
for us to score context relevance is if it reduces your usage of grep & other similar
commands"). {#s0b-intro}

### R0b.1: the scorer and its inputs {#r0b-1}

One script, `scripts/score-injection-blocks.py`, standard library only. Inputs are paths given
on the command line, never discovered by a walk: capture day files, transcript files, and an
output directory. It joins a capture record to its transcript `hook_success` record by session,
then by time, then confirms by text (`stdout` starts with the record's delivered text). Every
unjoined record is counted, in both directions. It refuses an output directory that git would
track. {#r0b-1-body}

### R0b.2: what is a discovery call, and its target {#r0b-2}

Main-loop tool calls only (`isSidechain` false), between one hook-fired prompt and the next.

| Call | Kind | Target |
|---|---|---|
| `Grep`, `Glob` tools; Bash `grep`, `rg`, `find`, `rmx grep`, `rmx context`, `rmx-master`; the refmatrix MCP read tools | **search**: looking for where something is | the pattern or name, and any path argument |
| `Read` tool; Bash `cat`, `sed -n`, `head`, `tail` on a path | **fetch**: getting content at a known place | the path |
{#r0b-2-kinds}

Target rules, from the pilot's matcher corrections
([[measurement-task-21.5-r12-pilot-2026-11-13#matcher-changes]]):

- A target is a **path** or an **identifier-shaped token** (`scan.is_identifier_shaped`, the one
  shared classifier). Plain words and regex fragments are not targets: the pilot's `bash_name`
  leg was 0 CAUSED of 46 on such tokens. A call with no path and no identifier-shaped token is
  `unscorable`.
- Heredoc and commit-message bodies are not tokenised. A path held in a shell variable is
  unknown.
- Calls are ordered by their own start, not by a ring timestamp.
- **Required reads are excluded:** a `Read` of a file that the same turn then edits or writes.
- **Prompt-named targets are flagged:** a target that appears in the prompt's own text (read
  locally from the transcript) is `prompt_named`. The agent had it from the user.
{#r0b-2-rules}

### R0b.3: the classes {#r0b-3}

Each scorable call gets one class, against the session's injections since the last compaction
boundary. Precedence is top to bottom. `lag` is the number of prompts since the block that
matched (0 is this prompt's own injection).

| Class | Rule | Scored against |
|---|---|---|
| `followed` | a **fetch** whose path is in a delivered block, not `prompt_named`, and not touched by the agent earlier in the session before that delivery | credit to the block: the agent went straight to a place the injection gave it |
| `ignored` | a **search** whose target is in a delivered block | **the agent**, never the injection ([[#r0b-4]]) |
| `avoidable` | the target is only in a dropped block (`dropped_bytes`, `dropped_tokens`) | the cut: the cap's cost |
| `avoidable_unverified` | the target matches only a `not_built` name | the cut, unverified |
| `uncovered` | in no block | retrieval: a relevance or coverage gap |
| `unscorable` / `required` / `prompt_named` fetch | counted, in no rate | — |
{#r0b-3-table}

`followed` is not in the plan's three classes. It is added because without it a fetch of a path
the injection delivered would be counted as the agent "searching anyway", which scores the
injection's best case as the agent's failure. It is the same leg that carried all of the
pilot's signal ([[measurement-task-21.5-r12-pilot-2026-11-13#by-leg]]). {#r0b-3-followed}

### R0b.4: `ignored` is its own finding, with sub-cases {#r0b-4}

The user, 2026-11-15: "you ignoring input should be its own class of finding". Every `ignored`
candidate is labelled from the local transcript (all of them up to 150; beyond that a uniform
draw, seed `3150`, with the sampling fraction printed):

| Label | Meaning | Where it counts |
|---|---|---|
| `re-verified` | the answer the call sought was in the delivered block, and the agent checked it | `ignored`, against the agent |
| `unread` | the answer was there, and nothing shows the block was used | `ignored`, against the agent |
| `stale` | the block showed the fact, and the fact was out of date | moves to `uncovered`: an injection defect |
| `answer-absent` | the block named the target but did not hold what the call sought (a definition shown, call sites wanted) | moves to `uncovered` |
| `unjudgeable` | | counted |
{#r0b-4-labels}

`ignored` is reported per session as a finding count, with its sub-cases. Its remedy is
presentation or the agent's instructions, never retrieval; what this task does with it under
the freeze is `plan-31 D4`. {#r0b-4-remedy}

### R0b.5: labels {#r0b-5}

`followed` candidates are labelled with the pilot's rubric (CAUSED / INFORMED / CONSISTENT /
UNRELATED), all of them up to 150 per block kind. 40 `avoidable` and `uncovered` calls are
labelled as a check on the extractor ("is the target really only in a dropped block, or in
none"). Labellers are agent forks under one rubric; ch-bsd blind-labels at least 25 pairs and
the agreement is printed. Pair ids, labels and one-line paraphrases stay in the output
directory; the repository gets the pair list's sha256 and the counts. {#r0b-5-body}

### R0b.6: the before/after split {#r0b-6}

Regimes are the builds that changed delivery: A, B, C as in [[#sized-table]], and D (release A:
C's delivery plus the capture). Their instants are read from the daemon log's version lines and
cross-checked against the output markers; the capture's `rmx_version` settles D. C and D pool,
because [[#ac-0-4]] proves the capture does not change the payload.

Reported per regime, as counts with per-session rows: discovery calls per prompt (all, search,
fetch), agent dispatches per prompt, and the share of scorable calls whose target was in the
delivered output. For A and B the rest cannot be split into `avoidable` and `uncovered`, except
for the part the harness previewed away (`stdout` minus `content`), which is reported as
`previewed`. The table is descriptive ([[#limits-cannot]] item 2). An on/off alternation is
considered only if this table is the only thing standing between two bands, and then it is
S3's question, not this step's. {#r0b-6-body}

### S0b acceptance criteria {#s0b-acceptance}

Tests are in `tests/test_score_injection_blocks.py`, on a synthetic fixture under
`tests/fixtures/injection_score/` (a hand-written transcript and capture; no real session data).

- **AC-0b.1 (RED at base): every class from one fixture.**
  `test_each_class_is_assigned_by_its_rule`: the fixture holds one call per row of
  [[#r0b-3-table]] and per exclusion of [[#r0b-2-rules]]; each gets exactly its class. At base
  the script does not exist. {#ac-0b-1}
- **AC-0b.2 (RED): precedence and lag.** `test_delivered_outranks_dropped_and_lag_is_counted`:
  a target dropped at lag 0 and delivered at lag 2 is `ignored` or `followed` with `lag 2`, not
  `avoidable`. {#ac-0b-2}
- **AC-0b.3 (RED): the pilot's false credits stay out.**
  `test_plain_words_heredocs_and_shell_variables_are_not_targets` and
  `test_a_read_before_an_edit_is_required_not_ignored`. {#ac-0b-3}
- **AC-0b.4 (RED): unjoined records are counted.**
  `test_unjoined_records_are_counted_in_both_directions`. {#ac-0b-4}
- **AC-0b.5 (RED): no text leaves.** `test_the_report_holds_counts_only`: a canary string
  placed in the fixture's prompt, a command, a block text and a path appears nowhere in the
  report; and `test_a_tracked_output_dir_is_refused`. {#ac-0b-5}
- **AC-0b.6 (measurement): label agreement.** The blind re-label's agreement on
  `ignored` against not, and on CAUSED + INFORMED against not, is in the measurement doc.
  Under 80% on either, the affected rates are report-only and no band reads them. {#ac-0b-6}

## S1: measure each block kind against bands written first {#s1}

### R1.0: the window, counted in prompts and sessions {#r1-0}

"About a week of normal use" is counted, not timed. The window opens at release A's deploy in
this store and closes when all three hold:

1. at least **400** hook-fired main-loop prompts with a joined capture record;
2. in at least **6** sessions of 20 or more such prompts each;
3. every block kind has at least **80** prompts on which it was produced (delivered or
   dropped).

It closes regardless at **800** prompts. A kind still under 80 then is `insufficient`. The
minimums come from [[#sized-week]] and from the bands: with 80 prompts and no use, the Wilson
95% upper bound is 4.6%, the first size at which "under 5%" can be read at all. Capture
coverage must be at least 95% of hook calls in the window, and the join rate at least 95%, or
the window does not count ([[#r0-6]]). These numbers are `plan-31 D2`. {#r1-0-body}

### R1.1: what is measured per block kind {#r1-1}

Kinds: `symbol_named`, `content`, `symbol_other`, `composite`, `recall`. Curator status is
reported from the transcript only (bytes and repetition; it is never cut, and its on-change
print is plan-10's 10.4).

| Measure | Definition |
|---|---|
| bytes per prompt | delivered and dropped, median and p90 |
| produced / delivered / dropped | prompts on which the kind was produced, delivered, dropped, by state |
| repetition | share of delivered blocks whose text equals the previous prompt's block of that kind; for the composite also by member-set signature |
| **use rate `u`** | prompts on which a delivered block of the kind has a `followed` call or a reply naming one of its items, labelled CAUSED or INFORMED (ruling L53 in [[plan-review-2026-11-13#lead]]: bands read CAUSED + INFORMED) ÷ prompts on which the kind was delivered. The use is credited to the item's first delivery in the session segment |
| ignored rate | prompts with an `ignored` call (after [[#r0b-4]]) on a delivered block of the kind ÷ prompts delivered |
| **avoidable rate `a`** | prompts on which an `avoidable` call's target was in a dropped block of the kind ÷ prompts on which the kind was dropped |
| uncovered | calls in no block, by target kind (path, identifier), not per block |
{#r1-1-table}

Every rate carries its Wilson 95% interval on prompts and its per-session range. {#r1-1-ci}

### R1.2: the bands {#r1-2}

Written here before the window opens ([[feedback_go_no_go_ranges_not_predrop]]). A band is
read from the interval, not the point estimate.

| Condition | Band | What S2 does |
|---|---|---|
| the kind was delivered on fewer than 80 prompts | `insufficient` | nothing; 21.5 phase M reads it again |
| `u` upper bound under 5%, and (`a` upper bound under 5% or the kind was dropped on fewer than 40 prompts) | `cut` | the kind's cut action ([[#actions]]) |
| `u` upper bound under 5%, and `a` lower bound at or over 5% | `cut-was-the-cap` | not cut: the useful part was the part being dropped. Its budget share or order changes so that part is delivered |
| `u` interval inside 5% to 15% | `shrink` | the kind's shrink action |
| `u` lower bound over 15% | `keep` | kept, tightened |
| the interval crosses 5% or 15% | `ambiguous` | the window runs on to 800 prompts; still ambiguous: [[#s3]] |
{#r1-2-table}

### The actions, per kind {#actions}

| Kind | `cut` | `shrink` | `keep` (tighten) |
|---|---|---|---|
| `symbol_named` | never removed: the author named it. Each bundle becomes one pointer line (`name → path:line`) | `--per-concept-tokens` 600 → 300 for tier 1 | item kinds with no labelled use in the window stop being rendered |
| `content` | the generated hook passes `--no-content` | `--content-tokens` 600 → 300 | as above |
| `symbol_other` | the generated hook passes a new `--max-other-concepts 0` | `--max-other-concepts 2` | as above |
| `composite` | the generated hook passes `--no-composite`; the focus graph, `rmx focus` and the MCP composite verb are unchanged (`plan-31 D3`: the user confirms with the number) | `--composite-k 1`, and no external `{ltm}` bridges | kept |
| `recall` | **no cut in this task**: its use is the kind the tool legs cannot see ([[#limits-cannot]] item 4). The floor is the shrink | `--k` 12 → 6 on the per-prompt hook | kept |
{#actions-table}

No action removes the scan-prompt hook or the recall hook. {#actions-floor}

### S1 acceptance criteria {#s1-acceptance}

- **AC-1.0 (gate): the window is valid.** The measurement doc opens with the window's counts
  against [[#r1-0]]: prompts, sessions, per-kind produced counts, capture coverage, join rate.
  A window that misses a minimum is extended or reported as invalid; no band is read from it.
  {#ac-1-0}
- **AC-1.1 (RED at base): the rates are computed as defined.**
  `tests/test_score_injection_blocks.py::test_per_kind_rates_on_the_fixture`: on the synthetic
  fixture the script prints each row of [[#r1-1-table]] with hand-computed values, including a
  kind that is `insufficient`. {#ac-1-1}
- **AC-1.2 (RED): a band is read from the interval.**
  `test_band_assignment_follows_the_interval`: five fixture kinds, one per band, and one whose
  point estimate is under 5% while its interval crosses it, which must be `ambiguous`.
  {#ac-1-2}
- **AC-1.3 (measurement): the result.** `workflow/measurements/task-31.5-block-use-<date>.md`
  holds, for this store: the [[#r1-1-table]] rows per kind, the band per kind, the before/after
  table of [[#r0b-6]], the `ignored` finding per session, and the list of what the run could
  not separate, copied from [[#limits]] with the observed sizes. Counts, rates, hashes and
  labels only. `./scripts/lint-gmd.sh` is clean on it. {#ac-1-3}
- **AC-1.4 (gate): reviewed before it decides anything.** ch-bsd re-runs the scorer on the same
  inputs and reproduces the counts; the bands go to the user only after that
  ([[orchestration#planning]] step 6). {#ac-1-4}

## S2: cut and tighten {#s2}

### R2.0: the one cut that needs no measurement (ships in release A) {#r2-0}

[[plan-31-pre-mod-loose-ends#t5]] lists four cuts as "already clear". 0.84.0 shipped three: no
topic without an identifier-shaped member, no repeat of an unchanged composite, most relevant
first under the cap. One remains: **no stopword or typo tokens as STM topic members.** A
grounded topic still prints every non-junk member, so `Members:` lines carry the prompt's own
plain words.

A member is printed only when it is identifier-shaped or a path (`scan.is_identifier_shaped`),
or it is a plain word that is outside the shared stoplist (`scan._PROMPT_STOPWORDS`) **and**
names a concept the store holds. A typo names nothing. A topic with no printed member is not
emitted. The focus graph is unchanged: this is a render filter. Admission of junk into the ring
is 25.3's ([[task-25.3-stm-ref-admission-and-helix-repeat]]); the two do not conflict.

It ships in release A, before the window opens, so that the window measures the composite the
user would keep, not one about to change. {#r2-0-body}

### R2.1: the band actions {#r2-1}

Release B implements the action of [[#actions-table]] for each kind whose band is `cut`,
`cut-was-the-cap` or `shrink`, and nothing for `keep` beyond the tightening named there. Every
knob reaches the hook through the generator (`hooks.py`); nothing is hand-edited. A kind that
is `insufficient` or still `ambiguous` is handled per `plan-31 D5`. {#r2-1-body}

### R2.2: what stays out of S2 {#r2-2}

Item-level dedup across prompts and labels by kind are plan-10's (10.5, 10.6, 10.4, 10.2), which
run after this task. Presentation changes beyond block order are post-mod
([[plan-of-plans#post-mod]]). {#r2-2-body}

### S2 acceptance criteria {#s2-acceptance}

- **AC-2.0 (RED at base): the member filter.** `tests/test_stm_composite_members.py`:
  `test_stopwords_and_unknown_plain_words_are_not_printed_as_members` (a topic of
  `scan-prompt`, `store.py`, `the`, `buigger`, `question` prints `scan-prompt, store.py` and
  `question` only when the store holds that concept);
  `test_a_topic_with_no_printable_member_is_not_emitted`;
  `test_the_focus_graph_is_unchanged_by_the_filter` (characterization). {#ac-2-0}
- **AC-2.1 (RED, one test per selected action).** `tests/test_scan_block_cuts.py`, named
  `test_<kind>_<action>` (for example `test_content_cut_drops_the_content_block`,
  `test_symbol_other_shrink_keeps_two`): with the action's knob, the real command's payload on
  a throwaway store has the block absent or within its new budget, and the tier-1 block is
  still first. Only selected actions get a test; the implementation summary lists the
  unselected ones as not built. {#ac-2-1}
- **AC-2.2 (RED): the generator carries the knob.** In the existing hook-generator tests: the
  generated `scan_cmd` (and the per-prompt recall command, if recall shrinks) contains the
  flag. {#ac-2-2}
- **AC-2.3 (gate): installed equals generated.** `rmx install-hooks --check` is clean after the
  lead's re-install, here and in every fleet repo, each behind a backup. {#ac-2-3}
- **AC-2.4 (guard): the 0.84.0 order holds.** `tests/test_scan_prompt_block_order.py`,
  `tests/test_stm_composite_injection.py` and `tests/test_scanorder_r2_l120.py` stay green;
  an expectation changed on purpose is named in the summary with its reason. {#ac-2-4}
- **AC-2.5 (measurement, live): the cut is visible.** Over the first 100 captured prompts after
  release B, delivered bytes per prompt by kind are below the window's, by the amount the
  actions predict; discovery calls per prompt are reported beside them, descriptively.
  {#ac-2-5}

## S3: ablation, only for an ambiguous band {#s3}

Runs only for a kind still `ambiguous` at 800 prompts, and only on the user's go
(`plan-31 D5`). Fixed now, so the protocol cannot be fitted to the result:

- **Design:** paired. 30 prompts drawn (seed `3153`) from the window's prompts on which the
  kind was delivered; each replayed twice in a fresh agent session on a clone at that prompt's
  commit, once with the full payload and once with the kind removed. Prompts stay local.
- **Outcome:** main-loop discovery calls before the first edit or the first reply, whichever
  comes first; and whether both arms touch the same first file.
- **Reading:** the paired difference in discovery calls, with its sign-test interval. Fewer
  calls with the kind (interval excluding zero): `keep`. No difference: `shrink`. The result
  never yields `cut`: 30 pairs cannot show the absence of an effect.
- **The protocol's remaining detail** (the replay harness, the judge for "same first file") is
  written as an amendment to this spec and reviewed by ch-bsd before any replay runs. 21.7's
  judge ([[task-21.7-behavioural-use#scope]]) is the method it reuses.
- **Without it:** an ambiguous kind takes `shrink`, the reversible middle action.
{#s3-list}

- **AC-3.1 (gate, conditional).** No replay runs before the amendment is approved; the
  measurement doc records either the ablation's result or "not run: `shrink` by default".
  {#ac-3-1}

## Mutations {#mutations}

Committed fix first; one at a time; each must FAIL a test, not hang it
([[orchestration#task]]).

| Id | Mutation | Must fail |
|---|---|---|
| M0-1 | the capture path renders into the delivered `parts` (payload changes) | [[#ac-0-4]] |
| M0-2 | capture-only bundles call `_retrieve` | [[#ac-0-5]] |
| M0-3 | the composite's marker is committed when the composite is stored but not delivered | [[#ac-0-6]] |
| M0-4 | every block is recorded as `delivered` | [[#ac-0-3]] (all four) |
| M0-5 | the token stop returns before recording the bundle that tripped it | [[#ac-0-3]] (`dropped_tokens`) |
| M0-6 | the record gains a `prompt` field | [[#ac-0-8]] |
| M0-7 | the pruner removes the current day's file, or removes nothing | [[#ac-0-9]] |
| M0-8 | a failed append raises, or leaves the row's `capture` unset | [[#ac-0-10]] |
| M0-9 | recall records only the named hits | [[#ac-0-7]] |
| M0b-1 | a fetch of a delivered path is classed `ignored` | [[#ac-0b-1]] |
| M0b-2 | dropped outranks delivered | [[#ac-0b-2]] |
| M0b-3 | plain words become targets (the pilot's `bash_name` leg) | [[#ac-0b-3]] |
| M0b-4 | a `Read` before an `Edit` is scored | [[#ac-0b-3]] |
| M0b-5 | an unjoined record is dropped without a count | [[#ac-0b-4]] |
| M0b-6 | the report prints a target | [[#ac-0b-5]] |
| M1-1 | the use rate divides by all prompts, not by prompts on which the kind was delivered | [[#ac-1-1]] |
| M1-2 | the band is read from the point estimate | [[#ac-1-2]] |
| M2-1 | the member filter keeps stoplist words; then: keeps unknown plain words | [[#ac-2-0]] |
| M2-2 | each selected action's knob is ignored by `scan_prompt` | its [[#ac-2-1]] test |
| M2-3 | the generator omits the knob | [[#ac-2-2]] |
{#mutations-table}

## Caller census {#census}

Counted at `f3a508f` by grep over `src/`, `eval/` and `scripts/`; the task re-counts at its
base.

| Changed | Callers | Note |
|---|---|---|
| `scan.scan_prompt` | 1: `cli.scan_prompt_cmd` | the capture hangs off the same `trace` hand-off; the function returns text as before |
| `hook_budget.fit_blocks` | 5 sites: `scan._finish`, `recall_pack.pack`, `cli` focus context, `cli` curator status, `handoff` recall-state | unchanged. Only the first two record a capture; the other three are not per-prompt recall or scan payloads |
| `recall_pack.pack` | 1: `verbs.memory_recall` | serves the CLI hook and MCP; the record is written by the CLI emitter only ([[#r0-3-list]]) |
| `composite.build_topic_composite_pending` | 1: `scan._composite_text`; `build_topic_composite`: `verbs` | the member filter is in `_render_gmd`, so both get it |
| `telemetry` writers | `emit_call`, `log_query` | a new writer beside them; `summarize_context` gains one line |
| `hooks._claude_hook_block` | `install-hooks`, the hook tests | release B only |
| tests that import a changed module | 17 import `scan`, `composite`, `hook_budget` or `recall_pack`; 24 mention `telemetry`; 38 mention scan-prompt | the family for each release's gate is listed by grep in the summary until 29.4 R6 derives it |
{#census-table}

## Files {#files}

| File | Change | Release |
|---|---|---|
| `src/refmatrix/telemetry.py` | the capture writer, pruner and the `capture:` report line | A |
| `src/refmatrix/scan.py` | blocks carry kind and state; token-cut bundles built for the capture | A |
| `src/refmatrix/cli.py`, `src/refmatrix/verbs.py` | hand the blocks to the writer after the payload is printed; the row's `capture` field | A |
| `src/refmatrix/composite.py` | the member filter ([[#r2-0]]) | A |
| `tests/test_injection_capture.py`, `tests/test_stm_composite_members.py` | new | A |
| `tests/fixtures/injection_capture/prompts.txt` | new: 40 synthetic prompts for [[#r0-5]] | A |
| `scripts/score-injection-blocks.py` | new: the scorer | with S0b |
| `tests/test_score_injection_blocks.py`, `tests/fixtures/injection_score/` | new: synthetic transcript and capture | with S0b |
| `workflow/measurements/task-31.5-block-use-<date>.md` | new: the result | S1 |
| `src/refmatrix/hooks.py`, `src/refmatrix/scan.py`, `src/refmatrix/cli.py` | the selected actions' knobs | B |
| `tests/test_scan_block_cuts.py`, the hook-generator tests | new and extended | B |
| `workflow/implementation_summaries/task-31.5-*.md` | one per release | A, B |
| `workflow/measurements/task-31.5-sizing/sizing.py` | committed with this spec | — |
{#files-table}

Both releases change a hook's output or the store's logs, so each is a minor release gated by
the full suite on merged `master` ([[orchestration#release]]). {#files-release}

## Risks {#risks}

1. **The capture slows a hook that is already slow** (bug-182). Bounded by [[#r0-5-bands]], with
   a cheaper path and a stop.
2. **The window is not "normal use".** It runs while plan-29 and plan-30 are built by an
   orchestrating lead. That is the population ([[#limits-cannot]] items 5 and 6); the result
   is not extended beyond it.
3. **The scorer credits proximity again.** The pilot's matcher did. The defences are the
   direction (from the agent's call, not from the item), the target rules, `prompt_named`,
   prior touch, and labels on every credited class.
4. **A number changes under review.** ch-bsd re-runs the scorer before any band is read
   ([[#ac-1-4]]); the pair list is frozen by hash.
5. **Fleet stores that track `.refmatrix/` files** (cliquet, atldb, prep_prolific; bug-214)
   would show the capture directory as untracked files. It is never added by rmx, and D1's
   option (b) keeps it out of them altogether.
6. **Large appends from two parallel hook processes.** One `write()` per record on an
   `O_APPEND` descriptor, as the event log does, but records are up to 30 kB. A torn line is
   counted by the reader (`malformed`), never skipped silently, and counts against the 95%
   coverage gate.
7. **Release B changes hook commands fleet-wide.** The re-install is the lead's, behind
   backups, checked by `rmx install-hooks --check` in each repo ([[#ac-2-3]]).
8. **Two releases and a window of 400 to 800 prompts** put S2 one to two weeks after release
   A. S0b's scorer and its tests are built during the window, so nothing waits on the window
   but the numbers.
{#risks-list}

## Seen while writing this spec, not this task's to fix {#seen}

Reported to the lead for the registry; no id is allocated here.

- `scan._composite_text` wraps the composite build in `except Exception: comp = ""`. A failing
  composite is indistinguishable from an absent one, and the hook's `2>/dev/null` hides the
  rest. The capture makes the absence countable (no `composite` block and no `suppressed_*`
  state on a prompt whose ring has topics) but does not surface the error.
- The plan's "59% of bytes, 100% repeated" premise ([[#sized-composite]]).
{#seen-list}

## What this task hands on {#handoff}

- **21.5 phase M:** per-leg label precision for `followed`, the capture itself as its delivered
  set by block, and any kind left `insufficient`.
- **Plan-30's 30.6** ([[plan-30-materialisation#t6]]): the `uncovered` counts by target kind,
  and a local, uncommitted list of the uncovered targets for its evaluation grid.
- **Plan-10:** repetition per kind ([[#r1-1-table]]), the input to its dedup re-measure.
- **Plan-24:** the `ignored` finding, beside [[design-note-tool-keyed-context-2026-11-15]].
{#handoff-list}

## Out of scope {#out-of-scope}

- Item-level dedup, labels by kind, curator status on change: plan-10.
- Any presentation change beyond block order, and tool-keyed rules: post-mod
  ([[plan-of-plans#post-mod]]).
- Retrieval quality (what `uncovered` needs): plan-30 and 30.6.
- STM admission (bug-166): 25.3.
- Subagent context: no injection reaches a subagent today, and none is added.
- bug-182's latency, beyond not making it worse than [[#r0-5-bands]] allows.
{#out-of-scope-list}

## Proposed decisions {#decisions}

Each is **proposed**, not decided. The lead enters it in [[plan-of-plans#decisions]] under its id
first; only a decision made there is amended into this spec (the user, 2026-11-15; ruling L125 in
[[plan-of-plans#rulings]]). The recommended option is listed first, and each item names the
anchors that depend on it. Until a decision is amended in, the text at those anchors is the
recommended option written as a draft. {#decisions-proposed}

- **plan-31 D1 (proposed, [[plan-of-plans#decisions]]): in which stores is the capture on?** It
  ships in a release that every fleet store runs.
  - (a) **Recommended.** On by default in every store, local to each store's `.refmatrix/`,
    bounded at 64 MiB and 42 days. Nothing to configure, "normal use" accrues everywhere, and
    cliquedb can be read if it reaches 100 prompts.
  - (b) On only in stores that carry a marker file; the lead creates it for refmatrix and
    cliquedb. Keeps payload text out of the three fleet repos that track `.refmatrix/` files.
  - (c) Off by default; on per store by request.
  - Depends on it: [[#r0-4]] (the off switch and default), [[#risks]] item 5.
  {#d1}
- **plan-31 D2 (proposed, [[plan-of-plans#decisions]]): how is "about a week of normal use"
  counted?**
  - (a) **Recommended.** At least 400 hook-fired prompts in at least 6 sessions of 20 or more,
    at least 80 prompts per block kind, closing at 800 regardless.
  - (b) A smaller window (200 prompts, 4 sessions). It reads no band under 5%: with 40 prompts
    of a kind and no use, the upper bound is 8.8%.
  - (c) A calendar week, whatever it holds.
  - Depends on it: [[#r1-0]], [[#ac-1-0]], the `insufficient` and `ambiguous` rows of
    [[#r1-2-table]].
  {#d2}
- **plan-31 D3 (proposed, [[plan-of-plans#decisions]]): is the band action table confirmed
  before the numbers, and what is the composite's `cut`?**
  - (a) **Recommended.** Confirm [[#actions-table]] now. The composite's `cut` (the generated
    hook stops passing the composite; the focus graph and `rmx focus` stay) is put to the user
    again with the number in hand before release B: the user asked to "consider taking
    action" on it, and [[orchestration#planning]] step 6 re-asks a decision once its number
    exists.
  - (b) Confirm the table now, the composite's cut included, with no second ask.
  - (c) No table in advance; the user reads the numbers and decides each kind.
  - Depends on it: [[#actions]], [[#r2-1]], [[#ac-2-1]].
  {#d3}
- **plan-31 D4 (proposed, [[plan-of-plans#decisions]]): what is done about `ignored` under the
  freeze?**
  - (a) **Recommended.** Report it per session, hand it to plan-10's 10.6 and to the mod's
    design note, change nothing here. Its remedies are presentation and instructions, which
    the freeze sends post-mod except where plan-10 already owns them.
  - (b) Also add one instruction line to the generated primer when the `unread` share is over
    a threshold named with the number.
  - Depends on it: [[#r0b-4-remedy]], [[#handoff]].
  {#d4}
- **plan-31 D5 (proposed, [[plan-of-plans#decisions]]): what happens to a kind that is
  `ambiguous` or `insufficient` when the window closes?**
  - (a) **Recommended.** `insufficient`: unchanged. `ambiguous` at 800 prompts: `shrink`; S3
    runs only on the user's go. S3 spends days of agent replays, and `shrink` is reversible.
  - (b) S3 runs automatically for every ambiguous kind.
  - Depends on it: [[#r2-1]], [[#s3]], [[#ac-3-1]].
  {#d5}
- **plan-31 D6 (proposed, [[plan-of-plans#decisions]]): does the capture stay on after this
  task closes?**
  - (a) **Recommended.** It stays on, bounded as in [[#r0-4]]. 21.5 phase M, plan-10's
    re-measure and 30.6 all read it, and the mod replaces the hook surface it sits on.
  - (b) Off by default from release B.
  - Depends on it: [[#r0-4]], [[#handoff]].
  {#d6}

None of the six changes a catalog on disk. D1 decides whether a new log directory appears under
each store's `.refmatrix/`; whether that falls under ruling L125's store-on-disk exception is
the lead's call. {#decisions-l125}

## Design choices in this draft {#spec-decisions}

These are how the draft is built, open to ch-bsd's challenge. They are not `plan-31 D<n>`
decisions and none is recorded as decided anywhere. {#spec-decisions-note}

- **A separate capture file, joined by `query_id`,** not new fields on the recall-event schema.
  The event schema is per item and is read by 19.2's fold and 21.5; the capture is per call,
  carries text, and is bounded and prunable. One writer, in the module that owns the others.
- **The classes are assigned from the agent's call, not from the injected item.** The pilot
  showed the other direction measures proximity.
- **`followed` is a class** ([[#r0b-3-followed]]).
- **The before/after table decides nothing** ([[#limits-cannot]] item 2).
- **The member filter ships with the capture,** ahead of the window ([[#r2-0-body]]).
- **Recall is never cut below a shrink here** ([[#actions-table]]).
{#spec-decisions-list}
