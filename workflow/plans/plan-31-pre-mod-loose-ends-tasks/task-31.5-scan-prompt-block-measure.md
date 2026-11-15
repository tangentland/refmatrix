---
gmd: "0.1"
id: task-31.5-scan-prompt-block-measure
title: "Task 31.5: the per-prompt injection, measured per block — capture the full payload, score discovery calls against it, band each block kind, then cut and tighten"
tags: [task, plan-31, scan-prompt, recall, injection, stm, telemetry, measurement, freeze]
metadata:
  node_type: task
  status: approved
  plan: plan-31-pre-mod-loose-ends
  created: 2026-11-15
  updated: 2026-11-15
  revision: 3
---

# Task 31.5: the per-prompt injection, measured per block {#root}

> Plan: [[plan-31-pre-mod-loose-ends]] ([[plan-31-pre-mod-loose-ends#t5]]; Q27 = b, now in
> [[pop-finished]]).
> Status: **Approved** by ruling L140 in [[plan-of-plans#rulings]] (ch-bsd confirm-lite r2,
> MEH-only GO; L125: plan-31 specs are approved on that GO), revision 3. Written by
> ch-architect on Fable 5.2, 2026-11-15. Revision 2 folded ch-bsd spec review r1 (DIRTY
> 3B/8S/11M) per ruling L133 ([[#rev-r1]]); revision 3 folds r2's five MEHs ([[#rev-r2]]).
> Depends on: 0.84.0 deployed (the block order, the 9,500 B command budget, the grounded-topic
> filter and the unchanged-composite marker; [[bsd-scanorder-r1-ca22b79]], ruling L120 in
> [[plan-review-2026-11-13#lead]]).
> Five sub-steps in one spec: **S0** capture ([[#s0]]), **S0b** discovery-call scoring
> ([[#s0b]]), **S1** per-block bands ([[#s1]]), **S2** cut and tighten ([[#s2]]), **S3**
> ablation, conditional ([[#s3]]).
> Two releases: **release A** carries S0, one composite fix ([[#r2-0]]) and bug-256
> ([[#r0-7]]); **release B** carries S2. The measurement window runs between them. In the
> POP's release plan ([[plan-of-plans#queue-releases]], ruling L135) release A is part of
> **R1** and release B is part of **R8**; the capture's count starts at R1's deploy.
> Queue: S0 is row 5 of [[plan-of-plans#queue]]; S0b to S3 are row 14. Plan-10's dedupe (10.5,
> 10.6, 10.4, 10.2) is post-mod (ruling L128); 10.3 stays pre-mod. Nothing here waits on either.
> Feeds 21.5 phase M and plan-30's 30.6 ([[#handoff]]).
> Decisions: `plan-31 D1`-`D6` are decided in [[plan-of-plans#decisions]] and amended in here
> ([[#decisions]]).
> Sibling specs on another branch (31.1, 31.2, 31.6) are written as code, not links.

rel: part-of -> [[plan-31-pre-mod-loose-ends]]
rel: implements -> [[plan-31-pre-mod-loose-ends#t5]]
rel: depends-on -> [[task-21.1-context-usage-telemetry]]
rel: depends-on -> [[task-25.1-recall-hook-byte-budget]]
rel: depends-on -> [[plan-of-plans#decisions]]
rel: derives-from -> [[task-21.5-tool-used-signal]]
rel: derives-from -> [[measurement-task-21.5-r12-pilot-2026-11-13]]
rel: derives-from -> [[bsd-scanorder-r1-ca22b79]]
rel: related-to -> [[measurement-injection-already-held-2026-11-13]]
rel: related-to -> [[design-note-tool-keyed-context-2026-11-15]]
rel: related-to -> [[plan-10-injection-dedup]]
rel: related-to -> [[task-21.7-behavioural-use]]
rel: related-to -> [[task-25.3-stm-ref-admission-and-helix-repeat]]
rel: related-to -> [[plan-30-materialisation#t6]]
rel: related-to -> [[bug_registry#registry]]
rel: reinforces -> [[feedback_injection_presentation_rules]]
rel: reinforces -> [[feedback_no_raw_prompts_in_public_repo]]
rel: reinforces -> [[feedback_go_no_go_ranges_not_predrop]]
rel: reinforces -> [[feedback_measure_the_path_users_run]]
rel: reinforces -> [[feedback_measure_the_outcome_not_the_wall]]
rel: reinforces -> [[feedback_generated_data_off_watched_tree]]
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
ch-bsd re-ran the script in r1 and reproduced rows A and B exactly. {#sized-method}

| Regime | What delivered | Prompts | Sessions | Scan output cut by `--max-bytes` | Recall previewed by the harness | Discovery calls per prompt (mean / sd / median) |
|---|---|---|---|---|---|---|
| A: to about 2026-11-14 01:00Z | no rmx byte cap; Claude Code previews any hook over 10,000 units | 791 | 11 | 0 (no cap); 50 scan outputs previewed | 582 of 791 (74%) | 3.24 / 5.92 / 1 |
| B: 0.83.0, to the 0.84.0 deploy | scan capped at 4,499 B, content first; recall packed to 4,000 B | 90 | 3 | 46 of 90 (51%) | 5 of 90 | 6.31 / 8.64 / 3 |
| C: 0.84.0 | 8,999 B, named identifiers first, grounded and on-change composite | 19 at the first run; growing | 1 | 4 of 19 | 0 | 6.00 / 8.31 / 4 |
{#sized-table}

What the sizing settles:

- **A week is about 450 prompts in 7 sessions.** `sizing.py --since 2026-11-09T00:00` printed
  455 hook-fired prompts in 7 sessions of 36 to 124 on 2026-11-15. {#sized-week}
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
- **The token stop is not a tail event** (ch-bsd r1, counts over the same transcripts): the
  `# [truncated by --max-tokens]` marker is in 411 of 775 regime-A scan outputs (53%).
  {#sized-token-stop}
- **The hook is already slow.** bug-182 ([[bug_registry#registry]]): `scan-prompt --timeout 5`
  ran p50 3.3 s and p95 13.9 s on 2026-11-08/09; ch-bsd read p50 3.6 s and p95 5.3 to 6.7 s in
  regimes B and C from the transcripts' `durationMs`. Anything the capture adds before the
  command exits lands on that. {#sized-latency}

## What already logs what {#existing}

| Instrument | Holds | Lacks |
|---|---|---|
| `.refmatrix/recall-events.jsonl` (21.1) | per item: `retrieved` and `delivered` events, byte spans, `block_sha` of the payload, `query_id`, session, turn | which block an item was in; why a retrieved item was not delivered; any text; the composite's items (the composite never enters `trace`) |
| `.refmatrix/query.log` | one row per call: kind, the first 200 characters of the prompt, timing, `query_id`. The row is written when the call's `log_query` block ends, **before** the payload is printed | blocks; anything known only after the print |
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
8. **A measured `shrink` from a defaulted one, below about 160 delivered prompts.** At the
   window's minimum sizes no count reads `shrink` ([[#r1-2-reach]]). The report labels which
   one each kind got.
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
| `not_built` | only in capture mode `names` ([[#r0-4-mode]]): a symbol bundle after the one that tripped the stop | no: its name only |
| `suppressed_unchanged` | the composite, not rendered because its member-set signature equals the last delivered one | no: the signature only |
| `suppressed_cadence` | the composite, skipped by `--composite-every` | no |
{#r0-1-states}

Block kinds: `symbol_named` (tier 1: bundles for identifier-shaped tokens the prompt names),
`content` (the content-ranked bundle), `symbol_other` (tier 3: plain words and PPR
expansions), `composite`, and for the recall channels `recall_hit` (one per hit: its hook line,
and its body when one was printed). Trailers and the `[truncated by --max-tokens]` marker are
recorded as kind `marker`. The plan's "symbol context" is split in two because 0.84.0 gave the
two tiers different positions. {#r0-1-kinds}

**The content block is never `not_built`.** The content bundle is built before any section is
rendered. When tier 1 trips the token stop, `scan_prompt` returns before rendering it; the
capture renders it and stores it as `dropped_tokens`, with text, at no build cost, in mode
`full` and in mode `names` alike. {#r0-1-content}

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
- **the capture's own outcome:** `capture_mode` (`full` or `names`, [[#r0-4-mode]]),
  `capture_ms` (the wall time the capture added before the command exits: the extra builds
  plus the append), `capture_built` (bundles built only for the capture; 0 in mode `names`), `pruned` (day files this call removed), and `composite_error` (the exception's
  class and message when the composite build raised, else null; [[#r0-7]]);
- `blocks`: in render order, each with `i`, `kind`, `state`, `bytes`, `sha256`, `names` (the
  item names the block carries), `dedup_rows`, and `text` where [[#r0-1-states]] says so. A
  `recall_hit` block carries `name`, `rank`, `mtype`, `scope`, `hook_bytes`, `body_bytes`,
  `body_sha256` and a state of `delivered` (hook line and body), `delivered_hook_only`, or
  `dropped_bytes` (behind the `+N more` trailer). It stores no body text: a memory body is
  addressable by name.
{#r0-2-fields}

A call that produces nothing still writes a record, with an empty `blocks` list: a prompt the
pipeline had nothing for is part of the denominator. {#r0-2-empty}

**The capture stores payload text, and payload text carries prompt terms.** A block's text is
the text the hook printed or would have printed. The content block's header lists up to eight
of the prompt's own non-stopword terms, the symbol header lists every matched name, and the
bodies quote lines of whatever the store indexes. The prompt as a whole is stored only as a
hash; its terms are stored in clear, locally, in every store the capture is on. That is why the
directory ignores itself ([[#r0-4]]) and why nothing derived from it is committed except counts
([[#r0b-1]]). {#r0-2-text}

**The outcome lives on the record, not on the `query.log` row.** That row is already written
when the capture runs ([[#existing-table]]). Its fields and its `latency_ms`, which bug-182's
analyses read, are untouched. The same holds for the recall emitter. {#r0-2-outcome}

### R0.3: what the capture must not change {#r0-3}

- The payload: byte-identical with the capture on and off.
- `recall-events.jsonl` and the `query.log` row: a bundle built only for the capture does not
  enter `trace`, so `retrieved` counts keep their meaning, and the row is not reopened.
- The composite's "sent" marker: committed only when the composite is delivered, exactly as
  0.84.0 does ([[bsd-scanorder-r1-ca22b79#s3]]).
- The generated hook config: release A changes no hook command, so there is no install window.
- `--format json` and the MCP path write no capture record: they are answers, not hook
  payloads.
{#r0-3-list}

### R0.4: where it lives, its bound, its retention, its switch {#r0-4}

- **Where:** `<store root>/injection-capture/capture-<UTC yyyymmdd>.jsonl`, one file per UTC
  day, in the store the call resolved. Hits from the global store are recorded in the calling
  project's file with `scope: global`.
- **The directory ignores itself.** Before **every** write into the directory (a record, or a
  line of `errors.jsonl`) the writer checks that `injection-capture/.gitignore` exists and
  creates it, containing `*`, when it does not. One `stat` per call. A check made only when the
  directory is created would leave a directory that already exists without the file (a crash
  between the `mkdir` and the write, a hand-made directory) written into unprotected. A
  repository's own ignore rules cannot be relied on: atlftpd ignores nothing under `.refmatrix/`, the default branches of cliquet,
  atldb and prep_prolific lack the line, and `rmx save-state --commit` runs `git add -A`
  (bug-261, bug-214; ch-bsd r1 B1).
- **Bound:** 64 MiB per store across all day files. Estimated cost is 15 kB per prompt,
  30 kB at worst, so the bound holds at least 2,000 prompts.
- **Retention:** 42 days, the longest window 21.5 R12 reads ([[task-21.5-tool-used-signal#r12]]).
- **Enforced at write time:** before appending, the writer removes day files older than 42 days,
  then the oldest earlier day files while the total exceeds the bound, and lists them in the
  record's `pruned`. Two hook processes run in parallel on every prompt, so a file another
  process already removed is not an error.
- **A hard stop within a day.** The current day's file is never pruned. Once the total still
  exceeds the bound with only the current day left, the writer appends no more records that
  day and counts each skipped call in `errors.jsonl` with reason `over_bound`.
- **Failures:** `injection-capture/errors.jsonl` takes one line per failed or skipped append
  (`ts`, `query_id`, `channel`, `reason`, the error's class and message). It holds no payload
  text and stops growing at 1 MiB. When the directory itself cannot be created or written,
  nothing can be recorded in it; the coverage count of [[#r0-6]] is then the signal.
- **Switch:** the capture is on by default in every store (`plan-31 D1`, [[#d1]]). It is off
  when `RMX_INJECTION_CAPTURE=0` is set, when the marker file
  `<store root>/injection-capture.off` exists, or when `REFMATRIX_NO_TELEMETRY` is set. The
  first two turn off the capture and nothing else: the `query.log` row and the recall events
  are still written. When off, the writer creates no directory.
- **Mode: both capture paths ship in release A, behind one setting.** `full` builds every
  bundle the token stop skipped. `names` builds nothing extra: it stores the bundle that
  tripped the stop and the content block, and records later symbol bundles as `not_built`.
  The mode is read, first match wins, from `RMX_INJECTION_CAPTURE` (`full` or `names`), then
  from the one word in `<store root>/injection-capture.mode`, then from the release default
  that [[#r0-5-bands]] chose. An unrecognised word turns the capture off and shows on the
  report line as an invalid mode. Changing the mode is a setting change in one store, not a
  release (ruling L140). {#r0-4-mode}
- **Why per-day files and not rename rotation:** appending to a day file needs no rename, so
  two writers cannot rotate over each other.
{#r0-4-list}

### R0.5: the cost on the hook path, banded before it is measured {#r0-5}

Recording a block that was already rendered costs one append after the payload is printed.
Building the bundles the token stop skipped costs up to four more `build_context` calls before
the command exits, and Claude Code waits for the command. The stop fires on about half of
prompts ([[#sized-token-stop]]), so those builds set the p95, not a tail. ch-bsd's r1 probe on
a read-only copy of the live catalog put one build at p50 34 ms and p95 92 ms, with hub words
(`daemon`, `memory`, `partition`, `session`) at 69 to 92 ms against 25 to 33 ms for
identifiers, so four extra builds cost about 140 ms at the median and about 370 ms on hub
words. The bundles past the stop are tier 3, which is where the hub words are. {#r0-5-why}

**How the cost is measured, before release A** (measurement lane; read-only):

1. **On a copy of the live catalog.** `.refmatrix/catalog.read.duckdb` of this project's store
   is copied into the `.refmatrix/` of a throwaway root under a short `mkdtemp()`, and only the
   copy is opened, `read_only=True`. A store built from `docs/` and `src/` has far fewer edges
   per hub word and would understate the cost. `HOME` is redirected to a scratch directory so
   the dev build cannot reach the live hub; `REFMATRIX_ROOT` is not exported.
2. **In fresh processes, with the hook's arguments, on the dev binary by path.** Each run is
   a new process running `<checkout>/.venv-eval/bin/rmx scan-prompt` with the arguments of the
   generated `scan_cmd`, from the throwaway root, with a prompt envelope on stdin. It is never
   a bare `rmx`: the hook's environment puts `$HOME/bin` first on `PATH`, and with `HOME`
   redirected a bare `rmx` can resolve to the deployed build, which has no capture, so both
   arms would time the same code. The summary records `rmx version -v` from that exact binary.
   If the copy root cannot serve the CLI's read path, each run instead times the same
   `scan_prompt` call in a fresh `.venv-eval` interpreter, and the summary says which was
   used.
3. **On a prompt set that trips the stop.** The committed synthetic set of 40 prompts
   ([[#files]]) is built from repository vocabulary: at least half trip the token stop, and at
   least 10 leave hub words in tier 3.
4. **At least 200 runs per arm,** capture off and capture on in mode `full` (by the switch and
   the mode of [[#r0-4]]) alternating, once quiet and once beside a running suite. The worse
   run is read. When the band sends the default to `names`, the same runs are made in that
   mode.
5. **Counting what the leg produced.** Beside wall p50 and p95 per arm, the summary reports
   `capture_built` per call and milliseconds per built bundle
   ([[feedback_measure_the_outcome_not_the_wall]]).
{#r0-5-method}

The band is read from the p95 of `capture_ms`, and it sets the release default of the mode.
Both modes are built either way ([[#r0-4-mode]]):

| `capture_ms`, p95 | Release default |
|---|---|
| mode `full` at most 250 ms | `full`: every token-cut bundle is built and stored |
| mode `full` over 250 ms | `names`: the bundle that tripped the stop is stored (it was already built), and so is the content block ([[#r0-1-content]]); later symbol bundles are recorded as `not_built` with their names only. Mode `names` is then measured the same way |
| mode `names` over 750 ms | the capture does not ship on; report to the lead with the profile |
{#r0-5-bands}

A `not_built` block has no text and no items. S0b counts a target that matches only a
`not_built` name as `avoidable_unverified`, a separate column. {#r0-5-not-built}

The band is checked again on the live path after release A, over the first 100 captured hook
prompts in this store ([[#ac-0-17]]). The fallback is a setting, never a release:

| Live `capture_ms`, p95 | What happens |
|---|---|
| mode `full` at most 250 ms | the window runs on |
| mode `full` over 250 ms | the lead **first** creates `injection-capture.off` in this store: the capture stops, telemetry stays on, the window is paused. Then the lead writes `names` into `injection-capture.mode`, removes the off marker, and the window restarts from that instant; the next 100 captured prompts are read |
| mode `names` at most 750 ms | the window runs on in mode `names`; S0b's `avoidable_unverified` column carries what `full` would have verified |
| mode `names` over 750 ms | the capture stays off (the off marker is put back) and the lead gets the profile. S0b and S1 do not run on an unmeasured window; the task stops at S0 and reports it |
{#r0-5-live}

### R0.6: a capture that stops is visible {#r0-6}

The scan hook discards stderr (`2>/dev/null || true`), so a message there reaches nobody.

- `rmx telemetry --context` prints one `capture:` line: the switch state (on, or off and by
  which of the three switches), day files, total bytes, newest record, and over the report
  window: captured records against hook calls in `query.log` (the coverage), errors by reason
  from `errors.jsonl`, and the count of records with a `composite_error`.
- A failed append never changes the payload or the exit status.
- The measurement does not start below 95% coverage ([[#ac-1-0]]).
{#r0-6-list}

### R0.7: a failing composite is counted (bug-256) {#r0-7}

`scan._composite_text` wraps the composite build in `except Exception: comp = ""`. A composite
that fails is indistinguishable from one that is absent, and the hook's `2>/dev/null` hides
anything written to stderr. bug-256 ([[bug_registry#registry]]) is scheduled to this task's
release A.

- The handler keeps the payload as it is (no composite) and records the exception's class and
  message: on stderr in one line, for callers that keep stderr, and in `composite_error` on the
  call's capture record.
- `rmx telemetry --context` counts those records on the `capture:` line ([[#r0-6]]).
- With the capture switched off, the count is off too; stderr is then the only trace. The
  report line says the capture is off, so the absence is not read as "no errors".
{#r0-7-list}

The registry row's remedy says "on stderr the hook keeps". The scan hook does not keep stderr
(`hooks.py`: `2>/dev/null || true`), and release A changes no hook command; the row's wording
is the lead's to correct. {#r0-7-registry}

### S0 acceptance criteria {#s0-acceptance}

Tests are in `tests/test_injection_capture.py` unless named. Each runs the real `scan-prompt`
or `memory recall --pack` command on a throwaway store under a short `mkdtemp()` root. "Capture
off" means the capture switch (`RMX_INJECTION_CAPTURE=0`), never `REFMATRIX_NO_TELEMETRY`,
unless the test says so.

- **AC-0.1 (RED at base): one record per call, every block labelled.**
  `test_a_scan_call_writes_one_record_with_every_block`: a prompt naming two identifiers and
  three plain words yields one line whose blocks carry the kinds of [[#r0-1-kinds]] in render
  order, with `capture_ms` and `capture_built` set. At base no file exists. {#ac-0-1}
- **AC-0.2 (RED): the delivered blocks are the payload.**
  `test_delivered_blocks_concatenate_to_the_payload`: the `delivered` and `marker` texts, joined
  in order, equal the printed payload; `payload_sha256` equals the `block_sha` of the call's
  recall events. {#ac-0-2}
- **AC-0.3 (RED): each cut is recorded as itself.** Five tests:
  `test_a_block_the_byte_fit_dropped_is_stored_as_dropped_bytes`,
  `test_bundles_past_the_token_stop_are_built_and_stored_as_dropped_tokens`,
  `test_content_after_a_tier_1_token_stop_is_stored_with_text` ([[#r0-1-content]]),
  `test_an_unchanged_composite_is_recorded_as_suppressed_unchanged`,
  `test_a_cadence_skip_is_recorded_as_suppressed_cadence`. Both capture paths exist, so both
  are tested whatever the release default: the second test runs in mode `full`, and
  `test_names_mode_records_later_bundles_as_not_built` runs the same prompt in mode `names`
  (the tripping bundle and the content block stored with text, later symbol bundles
  `not_built`, `capture_built` 0, `capture_mode` `names` on the record). {#ac-0-3}
- **AC-0.4 (guard, green at base; proven by mutation M0-1): the payload is unchanged.**
  `test_the_capture_never_changes_the_payload`: the same store and prompt give byte-identical
  stdout with the capture on and off, for a prompt that trips the token stop and one that trips
  the byte fit. {#ac-0-4}
- **AC-0.5 (guard, proven by M0-2): no other log changes.**
  `test_capture_only_bundles_emit_no_recall_events`: the call's `retrieved` and `delivered`
  events, and its `query.log` row apart from `ts` and timing fields, are the same with the
  capture on and off. Both arms write events, because the capture switch leaves telemetry on.
  {#ac-0-5}
- **AC-0.6 (guard, proven by M0-3): the composite marker follows delivery.** The existing
  `tests/test_scanorder_r2_l120.py::test_s3_a_composite_the_cap_dropped_is_delivered_when_there_is_room`
  stays green, and `test_a_composite_stored_as_dropped_is_sent_on_the_next_prompt` repeats it
  with the capture on. {#ac-0-6}
- **AC-0.7 (RED): recall is captured per hit.**
  `test_a_packed_recall_writes_one_block_per_hit`: 12 hits under a budget that names 8 and
  bodies 2 give 2 `delivered`, 6 `delivered_hook_only` and 4 `dropped_bytes` blocks, and no
  body text anywhere in the record. {#ac-0-7}
- **AC-0.8 (RED): no prompt field, and prompt terms only where the payload had them.**
  `test_prompt_text_appears_only_inside_block_text`, on two prompts that carry a canary token:
  one that produces blocks and one that produces none. It asserts: the record's keys are
  exactly the schema's; `prompt_sha256` is the prompt's hash; the canary appears in no field
  other than `blocks[*].text`; inside `blocks[*].text` it appears only at offsets where the
  printed payload carried it (a delivered block) or where the uncapped render carried it (a
  dropped block's header); and the second prompt's record has an empty `blocks` list and no
  canary at all. {#ac-0-8}
- **AC-0.9 (RED): the bound and the retention hold.**
  `test_old_and_oversize_day_files_are_pruned_and_listed` (bound and clock injected: the
  50-day file goes first, then the oldest, never the current day; the record's `pruned` names
  what went); `test_a_day_file_over_the_bound_stops_appending` (no new record;
  one `over_bound` line in `errors.jsonl`); `test_a_file_another_process_removed_is_not_an_error`.
  {#ac-0-9}
- **AC-0.10 (RED): a failed capture is countable and harmless.**
  `test_a_failed_append_keeps_the_payload_and_is_counted`: with the day file unwritable, stdout
  and exit status are unchanged, `errors.jsonl` holds one `append_failed` line, and
  `rmx telemetry --context` prints a `capture:` line with one error.
  `test_an_unwritable_capture_dir_shows_as_missing_coverage`: stdout and exit status are
  unchanged and the `capture:` line reads 0 captured of 1 hook call. {#ac-0-10}
- **AC-0.11 (characterization): JSON and MCP write nothing.**
  `test_json_format_writes_no_capture_record`, and
  `test_a_verb_recall_with_pack_writes_no_capture_record`, which calls `verbs.memory_recall`
  with `pack` the way the MCP adapter does and asserts no capture directory appears. {#ac-0-11}
- **AC-0.12 (gate): no hook drift.** `rmx install-hooks --check` is clean on the release A
  tree, and the generated hook block is byte-identical to base (the existing hooks-in-sync
  tests). {#ac-0-12}
- **AC-0.13 (measurement): the cost is inside a band.** The implementation summary holds the
  [[#r0-5-method]] run: the store copy's size, the binary's path and its `rmx version -v`
  output, the command used, runs per arm, wall p50 and
  p95 per arm quiet and loaded, `capture_ms` p50 and p95, `capture_built` per call,
  milliseconds per built bundle, and the release default [[#r0-5-bands]] gave. {#ac-0-13}
- **AC-0.14 (measurement, live, after release A): the capture is the production path.** On the
  deployed build, one real prompt in this project produces a record whose delivered blocks
  match that prompt's `hook_success.stdout` in the transcript (prefix match: the same command
  also prints curator status). Read-only. {#ac-0-14}
- **AC-0.15 (RED): the capture never shows in `git status`.**
  `test_the_capture_dir_ignores_itself`: in a throwaway git repository with no ignore rules at
  all, holding a store, after one `scan-prompt` call, `git status --porcelain -uall` lists
  nothing under `injection-capture/`, and `git add -A` stages nothing from it.
  `test_an_existing_capture_dir_without_gitignore_gets_one`: the directory is made by hand,
  with no `.gitignore`, before the call; after one call the same two checks hold. A third
  case does the same when the call's only write is a line of `errors.jsonl`. {#ac-0-15}
- **AC-0.16 (RED): a failing composite is counted.**
  `test_a_raising_composite_build_is_recorded_and_counted`: with the composite build made to
  raise through a real input (a corrupt ring file; a patch of a dependency only if no real
  input raises, registered in [[test_mock_registry]]), stdout is byte-identical to the same
  call with the composite absent, the capture record's `composite_error` names the exception,
  stderr carries one line, and `rmx telemetry --context` counts one. {#ac-0-16}
- **AC-0.17 (measurement, live, after release A): the band holds on the live path.** Over the
  first 100 captured hook prompts in this store, the p95 of `capture_ms` is read against
  [[#r0-5-live]], and the row that applied, the settings changed and their instants are
  recorded in the measurement doc. On a miss the lead's first act is the off marker. No row of
  that table needs a release. {#ac-0-17}
- **AC-0.18 (RED): the capture switch turns off the capture only, and the mode is a setting.**
  `test_the_capture_switch_leaves_telemetry_on`, parametrised over `RMX_INJECTION_CAPTURE=0`
  and the marker file: no capture directory is created, and the call's `query.log` row and
  recall events are written as usual. `test_no_telemetry_implies_no_capture`.
  `test_the_mode_file_selects_the_path`: with `names` in `injection-capture.mode` the record's
  `capture_mode` is `names`; the environment value outranks the file; an unrecognised word
  writes no record and shows as an invalid mode on the `capture:` line. {#ac-0-18}

## S0b: discovery calls, scored against the injection {#s0b}

The primary score ([[plan-31-pre-mod-loose-ends#t5]] step 0b; the user, 2026-11-15: "one way
for us to score context relevance is if it reduces your usage of grep & other similar
commands"). {#s0b-intro}

### R0b.1: the scorer and its inputs {#r0b-1}

One script, `scripts/score-injection-blocks.py`, standard library only. Inputs are paths given
on the command line, never discovered by a walk: capture day files, transcript files, and an
output directory. It joins a capture record to its transcript `hook_success` record by session,
then by time, then confirms by text (`stdout` starts with the record's delivered text). Every
unjoined record is counted, in both directions. {#r0b-1-body}

It refuses an output directory that git would track, and one that sits under any directory
holding a `.refmatrix/`: an untracked directory under a watch root is still ingested
([[feedback_generated_data_off_watched_tree]]). Working files go to the session scratchpad.
{#r0b-1-out}

### R0b.2: what is a discovery call, and its target {#r0b-2}

Main-loop tool calls only (`isSidechain` false), between one hook-fired prompt and the next.

| Call | Kind | Target |
|---|---|---|
| `Grep`, `Glob` tools; Bash `grep`, `rg`, `find`, `rmx grep`, `rmx context`, `rmx-master`; the refmatrix MCP read tools | **search**: looking for where something is | the searched name or pattern, and separately any path argument |
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
| `self_found` | a **fetch** whose path appeared in the output of an earlier main-loop call in the same turn (a grep listed it, then the agent read it) | nothing: counted, in no rate. The agent found it; the injection did not give it |
| `followed` | a **fetch** whose path is in a delivered block; or a **search** that matches a delivered block only through its path argument (a grep inside a file the injection delivered). Not `prompt_named`, and not touched by the agent earlier in the session before that delivery | a **candidate** credit to the block. It counts only once labelled CAUSED or INFORMED ([[#r0b-5]]) |
| `ignored` | a **search** whose searched name or pattern itself is in a delivered block | **the agent**, never the injection ([[#r0b-4]]) |
| `avoidable` | the target is only in a dropped block (`dropped_bytes`, `dropped_tokens`) | the cut: the cap's cost |
| `avoidable_unverified` | the target matches only a `not_built` name | the cut, unverified |
| `uncovered` | in no block | retrieval: a relevance or coverage gap |
| `unscorable` / `required` / `prompt_named` fetch | counted, in no rate | — |
{#r0b-3-table}

`followed` is not in the plan's three classes. It is added because without it a fetch of a path
the injection delivered would be counted as the agent "searching anyway", which scores the
injection's best case as the agent's failure. It is the same leg that carried all of the
pilot's signal: main-loop `bash_path`, C + I 9 of 26
([[measurement-task-21.5-r12-pilot-2026-11-13#by-leg]]). It adds candidates, not credit.
{#r0b-3-followed}

**Lag.** Every credited or blamed call carries its lag, reported in the pilot's bands: 0, 1-3,
4-6 and 7+. The rates of [[#r1-1]] read lag 0 to 6. Lag 7+ is reported and feeds no rate: the
pilot found 0 CAUSED of 13 there. {#r0b-3-lag}

**A target in blocks of several kinds** is a candidate for every kind that carried it. The
number of such calls is reported, so a kind's rate is never read as exclusive credit.
{#r0b-3-overlap}

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
presentation or the agent's instructions, never retrieval. This task reports it and changes
nothing for it (`plan-31 D4`, [[#d4]]). {#r0b-4-remedy}

### R0b.5: labels {#r0b-5}

- `followed` candidates are labelled with the pilot's rubric (CAUSED / INFORMED / CONSISTENT /
  UNRELATED): all of them up to 150 per block kind. Beyond 150, a uniform draw of 150, seed
  `3151`; the kind's use rate is then computed from the labels weighted by the inverse sampling
  fraction, which is printed.
- 40 `avoidable` and `uncovered` calls are labelled as a check on the extractor ("is the target
  really only in a dropped block, or in none").
- Labellers are agent forks under one rubric. ch-bsd blind-labels at least 60 pairs. The gate
  is on the Wilson 95% lower bound of the agreement, which must be at least 80% (55 of 60
  agreeing reaches it; 25 pairs at 80% agreement would have a lower bound of 61%).
- Pair ids, labels and one-line paraphrases stay in the output directory; the repository gets
  the pair list's sha256 and the counts.
{#r0b-5-body}

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
  [[#r0b-3-table]] and per exclusion of [[#r0b-2-rules]], among them a grep-then-read chain
  (`self_found`), a grep inside a delivered file (`followed`) and a grep for a delivered name
  (`ignored`); each gets exactly its class. At base the script does not exist. {#ac-0b-1}
- **AC-0b.2 (RED): precedence, lag and overlap.**
  `test_delivered_outranks_dropped_and_lag_is_counted` (a target dropped at lag 0 and delivered
  at lag 2 is `ignored` or `followed` with `lag 2`, not `avoidable`);
  `test_lag_7_and_over_feeds_no_rate`;
  `test_a_target_in_two_kinds_is_a_candidate_for_both_and_counted_once_as_overlap`. {#ac-0b-2}
- **AC-0b.3 (RED): the pilot's false credits stay out.**
  `test_plain_words_heredocs_and_shell_variables_are_not_targets` and
  `test_a_read_before_an_edit_is_required_not_ignored`. {#ac-0b-3}
- **AC-0b.4 (RED): unjoined records are counted.**
  `test_unjoined_records_are_counted_in_both_directions`. {#ac-0b-4}
- **AC-0b.5 (RED): no text leaves.** `test_the_report_holds_counts_only`: a canary string
  placed in the fixture's prompt, a command, a block text and a path appears nowhere in the
  report; `test_a_tracked_output_dir_is_refused`;
  `test_an_output_dir_under_a_store_root_is_refused`. {#ac-0b-5}
- **AC-0b.6 (RED): sampled labels are weighted.**
  `test_a_sampled_kind_weights_its_labels`: a fixture kind with 300 candidates and 150 labels
  gives the use rate of the weighted labels, and prints the sampling fraction. {#ac-0b-6}
- **AC-0b.7 (measurement): label agreement.** The blind re-label's agreement on `ignored`
  against not, and on CAUSED + INFORMED against not, is in the measurement doc with its Wilson
  lower bound, on at least 60 pairs each. Under 80% on either lower bound, the affected rates
  are report-only and no band reads them. {#ac-0b-7}

## S1: measure each block kind against bands written first {#s1}

### R1.0: the window, counted in prompts and sessions {#r1-0}

"About a week of normal use" is counted, not timed (`plan-31 D2`, [[#d2]]). The window opens at
release A's deploy in this store, or at the instant the mode was changed if [[#r0-5-live]]
changed it, and closes when all three hold:

1. at least **400** hook-fired main-loop prompts with a joined capture record;
2. in at least **6** sessions of 20 or more such prompts each;
3. every block kind was **delivered** on at least **80** prompts. The band's `insufficient`
   row reads delivered prompts, so the window closes on the same count.

It closes regardless at **800** prompts. A kind still under 80 then is `insufficient`. The
minimums come from [[#sized-week]] and from the bands: with 80 prompts and no use, the Wilson
95% upper bound is 4.6%, the first size at which "under 5%" can be read at all. The composite
is the kind most likely to hold the window open: it was delivered on 3 of the first 22 regime-C
prompts (ch-bsd r1), a rate at which 80 deliveries take about 590 prompts. Capture coverage
must be at least 95% of hook calls in the window, and the join rate at least 95%, or the window
does not count ([[#r0-6]]). {#r1-0-body}

### R1.1: what is measured per block kind {#r1-1}

Kinds: `symbol_named`, `content`, `symbol_other`, `composite`, `recall`. Curator status is
reported from the transcript only (bytes and repetition; it is never cut, and its on-change
print is plan-10's 10.4, post-mod).

| Measure | Definition |
|---|---|
| bytes per prompt | delivered and dropped, median and p90 |
| produced / delivered / dropped | prompts on which the kind was produced, delivered, dropped, by state |
| repetition | share of delivered blocks whose text equals the previous prompt's block of that kind; for the composite also by member-set signature |
| **use rate `u`** | prompts on which a delivered block of the kind has a `followed` call or a reply naming one of its items, at lag 0 to 6, labelled CAUSED or INFORMED (ruling L53 in [[plan-review-2026-11-13#lead]]: bands read CAUSED + INFORMED) ÷ prompts on which the kind was delivered. The use is credited to the item's first delivery in the session segment. Also printed by lag band (0, 1-3, 4-6, 7+) |
| ignored rate | prompts with an `ignored` call (after [[#r0b-4]]) on a delivered block of the kind ÷ prompts delivered |
| **avoidable rate `a`** | prompts on which an `avoidable` call's target was in a dropped block of the kind ÷ prompts on which the kind was dropped |
| overlap | calls whose target was in delivered blocks of more than one kind |
| uncovered | calls in no block, by target kind (path, identifier), not per block |
{#r1-1-table}

Every rate carries its Wilson 95% interval on prompts and its per-session range. {#r1-1-ci}

### R1.2: the bands {#r1-2}

Written here before the window opens ([[feedback_go_no_go_ranges_not_predrop]]). A band is
read from intervals, not point estimates. `U` is the Wilson 95% interval of `u`, `A` that of
`a`, `nd` the prompts on which the kind was delivered and `nx` those on which it was dropped.
The rows are tried top to bottom and cover every case.

| # | Condition | Band | What S2 does |
|---|---|---|---|
| 1 | `nd` under 80 | `insufficient` | nothing; 21.5 phase M reads it again |
| 2 | `U` upper under 5%, and (`nx` under 40, or `A` upper under 5%) | `cut` | the kind's cut action ([[#actions]]) |
| 3 | `U` upper under 5%, `nx` at least 40, and `A` lower at or over 5% | `cut-was-the-cap` | not cut: the useful part was the part being dropped. Its budget share or order changes so that part is delivered |
| 4 | `U` upper under 5%, `nx` at least 40, and `A` crosses 5% | `ambiguous` (on `a`) | the window runs on to 800 prompts; still ambiguous: `shrink` by default ([[#d5]]) |
| 5 | `U` lower at or over 5% and `U` upper at or under 15% | `shrink` (measured) | the kind's shrink action |
| 6 | `U` lower over 15% | `keep` | no change |
| 7 | every other case: `U` crosses 5% or crosses 15% | `ambiguous` (on `u`) | as row 4 |
{#r1-2-table}

**What each size can read.** Wilson 95%, computed before the window:

| `nd` | `cut` needs uses of | `shrink` (measured) needs uses of | `keep` needs uses of at least |
|---|---|---|---|
| 80 | 0 | no count reads it | 19 (23.8%) |
| 120 | 0 to 1 | no count reads it | 26 (21.7%) |
| 160 | 0 to 2 | 14 to 15 | 33 (20.6%) |
| 240 | 0 to 5 | 19 to 25 | 47 (19.6%) |
| 400 | 0 to 11 | 29 to 46 | 74 (18.5%) |
{#r1-2-reach}

So at 80 delivered prompts every use rate from 1.2% to 22.5% is `ambiguous`, and below about
160 a kind with modest use reaches `shrink` only through row 4 or row 7's default. The
measurement doc prints each kind's `nd`, the bands reachable at that size, and whether a
`shrink` is **measured** (row 5) or **default** ([[#d5]]). A default is not evidence that the
kind is used 5% to 15% of the time. {#r1-2-reach-note}

### The actions, per kind {#actions}

The table is confirmed before the numbers (`plan-31 D3`, [[#d3]]). `keep` means no change.

| Kind | `cut` | `shrink` |
|---|---|---|
| `symbol_named` | **no cut**: the author named it. The floor is the shrink | `--named-concept-tokens 300` (new knob: tier 1's per-bundle budget, 600 today) |
| `content` | the generated hook passes `--no-content` (knob exists) | `--content-tokens 300` (exists) |
| `symbol_other` | `--max-other-concepts 0` (new knob) | `--max-other-concepts 2` |
| `composite` | the generated hook passes `--no-composite` (exists); the focus graph, `rmx focus` and the MCP composite verb are unchanged. The user is asked again with the number in hand before release B ([[#d3]]) | `--composite-k 1` (exists) |
| `recall` | **no cut in this task**: its use is the kind the tool legs cannot see ([[#limits-cannot]] item 4). The floor is the shrink | `--k` 12 → 6 on the per-prompt hook (exists) |
{#actions-table}

No action removes the scan-prompt hook or the recall hook. {#actions-floor}

Two actions of the first draft are gone, for different reasons (ch-bsd r2 M4):

- **Turning a named bundle into a pointer line** is new presentation, which
  [[plan-of-plans#post-mod]] sends after the mod. The plan never asked for it.
- **Dropping item kinds with no labelled use from a kept block** (the per-item tighten) is a
  content filter, not presentation. It is dropped because it had no knob and no test, and
  ruling L133 took "tested or dropped" as dropped. It was the only thing behind the plan's
  "over 15% is kept and tightened", so that line of the plan now reads "kept; tightened only
  by the member filter (R2.0) and the shrink knobs" ([[plan-31-pre-mod-loose-ends#t5]];
  recorded for the user in ruling L140).

The composite's shrink no longer drops the external bridges, for which no knob exists.
{#actions-removed}

### S1 acceptance criteria {#s1-acceptance}

- **AC-1.0 (gate): the window is valid.** The measurement doc opens with the window's counts
  against [[#r1-0]]: prompts, sessions, per-kind delivered counts, capture coverage, join rate.
  A window that misses a minimum is extended or reported as invalid; no band is read from it.
  {#ac-1-0}
- **AC-1.1 (RED at base): the rates are computed as defined.**
  `tests/test_score_injection_blocks.py::test_per_kind_rates_on_the_fixture`: on the synthetic
  fixture the script prints each row of [[#r1-1-table]] with hand-computed values, including a
  kind that is `insufficient` and a use at lag 7 that feeds no rate. {#ac-1-1}
- **AC-1.2 (RED): the band table is total and read from intervals.**
  `test_band_assignment_follows_the_intervals`: one fixture kind per row of [[#r1-2-table]]
  (seven), among them a kind whose point estimate is under 5% while `U` crosses it (row 7) and
  a kind with `U` upper under 5% whose `A` crosses 5% on 40 or more drops (row 4).
  `test_every_count_gets_exactly_one_band`: for `nd` in 80, 160 and 400, every pair of use and
  avoidable counts maps to exactly one row. {#ac-1-2}
- **AC-1.3 (measurement): the result.** `workflow/measurements/task-31.5-block-use-<date>.md`
  holds, for this store: the [[#r1-1-table]] rows per kind, the band per kind with
  [[#r1-2-reach-note]]'s three facts, the before/after table of [[#r0b-6]], the `ignored`
  finding per session, and the list of what the run could not separate, copied from
  [[#limits]] with the observed sizes. Counts, rates, hashes and labels only.
  `./scripts/lint-gmd.sh` is clean on it. {#ac-1-3}
- **AC-1.4 (gate): reviewed before it decides anything.** ch-bsd re-runs the scorer on the same
  inputs and reproduces the counts; the bands are read only after that. {#ac-1-4}

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
`cut-was-the-cap` or `shrink`. Every knob reaches the hook through the generator (`hooks.py`);
nothing is hand-edited. An `insufficient` kind is unchanged; a kind still `ambiguous` at 800
prompts takes `shrink` unless the user has asked for S3 ([[#d5]]).

What each action needs, and so what kind of test proves it:

| Action | Knob | The payload test ([[#ac-2-1]]) | The generator test ([[#ac-2-2]]) |
|---|---|---|---|
| `content` cut / shrink | `--no-content` / `--content-tokens`: exist | characterization: green at base | RED |
| `composite` cut / shrink | `--no-composite` / `--composite-k`: exist | characterization | RED |
| `recall` shrink | `--k`: exists | characterization | RED |
| `symbol_other` cut / shrink | `--max-other-concepts N`: **new** | RED, named, with mutation M2-2 | RED |
| `symbol_named` shrink | `--named-concept-tokens N`: **new** | RED, named, with mutation M2-3 | RED |
| `cut-was-the-cap` | the order or budget share of the kind, by the two knobs above or `--max-tokens` | RED when a new knob is needed; else characterization | RED |
{#r2-1-table}

A new knob is built only if its action is selected. {#r2-1-body}

### R2.2: what stays out of S2 {#r2-2}

Item-level dedup across prompts, labels by kind and curator status on change are plan-10's
10.5, 10.6, 10.4 and 10.2, which ruling L128 moved post-mod. Presentation changes beyond block
order are post-mod as well ([[plan-of-plans#post-mod]]). {#r2-2-body}

### S2 acceptance criteria {#s2-acceptance}

- **AC-2.0 (RED at base): the member filter.** `tests/test_stm_composite_members.py`:
  `test_stopwords_and_unknown_plain_words_are_not_printed_as_members` (a topic of
  `scan-prompt`, `store.py`, `the`, `buigger`, `question` prints `scan-prompt, store.py` and
  `question` only when the store holds that concept);
  `test_a_topic_with_no_printable_member_is_not_emitted`;
  `test_the_focus_graph_is_unchanged_by_the_filter` (characterization). {#ac-2-0}
- **AC-2.1 (per selected action, kind of test per [[#r2-1-table]]).**
  `tests/test_scan_block_cuts.py`, named `test_<kind>_<action>`: with the action's knob, the
  real command's payload on a throwaway store has the block absent or within its new budget,
  and the tier-1 block is still first. For an existing knob this is a characterization and the
  summary says so. For a new knob it is RED at base, by name:
  `test_symbol_other_cut_renders_no_tier_3_bundle`, `test_symbol_other_shrink_keeps_two`,
  `test_symbol_named_shrink_halves_the_tier_1_bundle_budget_only` (tier 3 bundles keep 600).
  Only selected actions get a test; the summary lists the unselected ones as not built.
  {#ac-2-1}
- **AC-2.2 (RED): the generator carries the knob.** In the existing hook-generator tests: the
  generated `scan_cmd` (and the per-prompt recall command, if recall shrinks) contains the
  flag. This is the RED test of every action whose knob already exists. {#ac-2-2}
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
(`plan-31 D5`, [[#d5]]). Fixed now, so the protocol cannot be fitted to the result:

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
| M0-4 | every block is recorded as `delivered` | [[#ac-0-3]] (all five) |
| M0-5 | the token stop returns before recording the bundle that tripped it; then: before rendering the content block | [[#ac-0-3]] (`dropped_tokens`; content) |
| M0-6 | the record gains a `prompt` field; then: the canary is copied into a second field | [[#ac-0-8]] |
| M0-7 | the pruner removes the current day's file; then: removes nothing; then: keeps appending over the bound | [[#ac-0-9]] |
| M0-8 | a failed append raises; then: writes no `errors.jsonl` line | [[#ac-0-10]] |
| M0-9 | recall records only the named hits | [[#ac-0-7]] |
| M0-10 | the writer does not create `injection-capture/.gitignore`; then: it creates it only when it creates the directory | [[#ac-0-15]] (the first test; then the existing-directory tests) |
| M0-11 | `_composite_text` goes back to a silent `comp = ""` | [[#ac-0-16]] |
| M0-12 | the capture switch is ignored; then: it also disables the `query.log` row | [[#ac-0-18]] |
| M0-13 | the verb's pack branch writes a capture record | [[#ac-0-11]] |
| M0-14 | mode `names` builds the skipped bundles anyway; then: the mode file is ignored | [[#ac-0-3]] (`test_names_mode_…`); [[#ac-0-18]] (`test_the_mode_file_selects_the_path`) |
| M0b-1 | a fetch of a delivered path is classed `ignored` | [[#ac-0b-1]] |
| M0b-2 | dropped outranks delivered; then: lag 7+ feeds the rate | [[#ac-0b-2]] |
| M0b-3 | plain words become targets (the pilot's `bash_name` leg) | [[#ac-0b-3]] |
| M0b-4 | a `Read` before an `Edit` is scored | [[#ac-0b-3]] |
| M0b-5 | an unjoined record is dropped without a count | [[#ac-0b-4]] |
| M0b-6 | the report prints a target; then: an output dir under a store root is accepted | [[#ac-0b-5]] |
| M0b-7 | a grep-then-read chain is classed `followed` | [[#ac-0b-1]] |
| M0b-8 | a grep inside a delivered file is classed `ignored` | [[#ac-0b-1]] |
| M0b-9 | sampled labels are counted unweighted | [[#ac-0b-6]] |
| M1-1 | the use rate divides by all prompts, not by prompts on which the kind was delivered | [[#ac-1-1]] |
| M1-2 | the band is read from the point estimate | [[#ac-1-2]] |
| M1-3 | row 4 is removed (the case falls through to `cut`) | [[#ac-1-2]] (both tests) |
| M2-1 | the member filter keeps stoplist words; then: keeps unknown plain words | [[#ac-2-0]] |
| M2-2 | `--max-other-concepts` is parsed and ignored by `scan_prompt` | its [[#ac-2-1]] tests |
| M2-3 | `--named-concept-tokens` applies to every tier | its [[#ac-2-1]] test |
| M2-4 | the generator omits a selected knob | [[#ac-2-2]] |
{#mutations-table}

## Caller census {#census}

Counted at `f3a508f` by grep over `src/`, `eval/` and `scripts/`; the task re-counts at its
base.

| Changed | Callers | Note |
|---|---|---|
| `scan.scan_prompt` | 1: `cli.scan_prompt_cmd` | the capture hangs off the same `trace` hand-off; the function returns text as before |
| `scan._composite_text` | 1: `scan._finish` | [[#r0-7]]; the handler's outcome reaches the record through the same hand-off |
| `hook_budget.fit_blocks` | 5 sites: `scan._finish`, `recall_pack.pack`, `cli` focus context, `cli` curator status, `handoff` recall-state | unchanged. Only the first two record a capture; the other three are not per-prompt recall or scan payloads |
| `recall_pack.pack` | 1: `verbs.memory_recall` | serves the CLI hook and MCP; the record is written by the CLI emitter only ([[#r0-3-list]], [[#ac-0-11]]) |
| `composite.build_topic_composite_pending` | 1: `scan._composite_text`; `build_topic_composite`: `verbs` | the member filter is in `_render_gmd`, so both get it |
| `telemetry` writers | `emit_call`, `log_query` | a new writer beside them; `log_query` and its row are not changed; `summarize_context` gains one line |
| `hooks._claude_hook_block` | `install-hooks`, the hook tests | release B only |
| tests that import a changed module | 17 import `scan`, `composite`, `hook_budget` or `recall_pack`; 24 mention `telemetry`; 38 mention scan-prompt | the family for each release's gate is listed by grep in the summary until 29.4 R6 derives it |
{#census-table}

## Files {#files}

| File | Change | Release |
|---|---|---|
| `src/refmatrix/telemetry.py` | the capture writer (self-ignore, switch, mode, pruner, hard stop, `errors.jsonl`) and the `capture:` report line | A |
| `src/refmatrix/scan.py` | blocks carry kind and state; both capture paths (`full` builds the token-cut bundles, `names` does not); `_composite_text` records its failure | A |
| `src/refmatrix/cli.py`, `src/refmatrix/verbs.py` | hand the blocks to the writer after the payload is printed | A |
| `src/refmatrix/composite.py` | the member filter ([[#r2-0]]) | A |
| `tests/test_injection_capture.py`, `tests/test_stm_composite_members.py` | new | A |
| `tests/fixtures/injection_capture/prompts.txt` | new: 40 synthetic prompts for [[#r0-5-method]] | A |
| `scripts/score-injection-blocks.py` | new: the scorer | with S0b |
| `tests/test_score_injection_blocks.py`, `tests/fixtures/injection_score/` | new: synthetic transcript and capture | with S0b |
| `workflow/measurements/task-31.5-block-use-<date>.md` | new: the result | S1 |
| `src/refmatrix/hooks.py`, `src/refmatrix/scan.py`, `src/refmatrix/cli.py` | the selected actions' knobs | B |
| `tests/test_scan_block_cuts.py`, the hook-generator tests | new and extended | B |
| `workflow/implementation_summaries/task-31.5-*.md` | one per release | A, B |
| `workflow/measurements/task-31.5-sizing/sizing.py` | committed with this spec; `--since` added in revision 2 | — |
{#files-table}

Both releases change a hook's output or the store's logs, so each is a major release (`0.N.0`)
gated by the full suite on merged `master` ([[orchestration#release]]). Neither is a release of
its own: release A ships in R1 and release B in R8 of [[plan-of-plans#queue-releases]]. The
fallback of [[#ac-0-17]] is a setting inside R1, not a release
([[plan-of-plans#queue-releases-contingent]], ruling L140). Release A changes no hook command;
`hooks.py` is edited only in release B. {#files-release}

## Risks {#risks}

1. **The capture slows a hook that is already slow** (bug-182). Bounded by [[#r0-5-bands]],
   measured on a copy of the live catalog, checked again live ([[#r0-5-live]]), with an off
   marker the lead sets first, a cheaper mode that is a setting, and a stop.
2. **The window is not "normal use".** It runs while plan-29 and plan-30 are built by an
   orchestrating lead. That is the population ([[#limits-cannot]] items 5 and 6); the result
   is not extended beyond it.
3. **The scorer credits proximity again.** The pilot's matcher did. The defences are the
   direction (from the agent's call, not from the item), the target rules, `prompt_named`,
   prior touch, `self_found`, the lag bound, and labels on every credited class.
4. **A number changes under review.** ch-bsd re-runs the scorer before any band is read
   ([[#ac-1-4]]); the pair list is frozen by hash.
5. **The capture holds prompt terms in every fleet store, and not every fleet repository
   ignores `.refmatrix/`.** atlftpd ignores nothing under it; the default branches of cliquet,
   atldb and prep_prolific lack the line; `rmx save-state --commit` runs `git add -A`
   (bug-261). The directory therefore ignores itself ([[#r0-4]], [[#ac-0-15]]). That protects
   the capture only: the catalogs and STM rings those repositories expose are bug-261's and
   the user's to fix.
6. **Large appends from two parallel hook processes.** One `write()` per record on an
   `O_APPEND` descriptor, as the event log does, but records are up to 30 kB. A torn line is
   counted by the reader (`malformed`), never skipped silently, and counts against the 95%
   coverage gate.
7. **Release B changes hook commands fleet-wide.** The re-install is the lead's, behind
   backups, checked by `rmx install-hooks --check` in each repo ([[#ac-2-3]]).
8. **Two releases and a window of 400 to 800 prompts** put S2 one to two weeks after release
   A. S0b's scorer and its tests are built during the window, so nothing waits on the window
   but the numbers.
9. **Most kinds will not reach a measured `shrink`** at the window's sizes
   ([[#r1-2-reach]]). The likely outcome is a mix of `cut`, `keep` and defaulted `shrink`, and
   the report must say which is which.
10. **Turning the capture off turns off the composite-failure count** ([[#r0-7]]). The report
    line states the switch, so an off capture is not read as a clean one.
{#risks-list}

## Seen while writing this spec {#seen}

- `scan._composite_text`'s silent handler is bug-256 and is now this task's ([[#r0-7]]).
- The plan's "59% of bytes, 100% repeated" premise ([[#sized-composite]]).
- The registry's remedy text for bug-256 names a stderr the hook does not keep
  ([[#r0-7-registry]]).
{#seen-list}

## What this task hands on {#handoff}

- **21.5 phase M:** per-leg label precision for `followed`, the capture itself as its delivered
  set by block, and any kind left `insufficient`.
- **Plan-30's 30.6** ([[plan-30-materialisation#t6]]): the `uncovered` counts by target kind,
  and a local, uncommitted list of the uncovered targets for its evaluation grid.
- **Plan-10's dedupe, post-mod** (ruling L128): repetition per kind ([[#r1-1-table]]) and the
  `ignored` finding for 10.6, read at the post-mod re-evaluation.
- **Plan-24's freshness revision** (row 16 of [[plan-of-plans#queue]]): the bands, the
  `ignored` finding, and [[design-note-tool-keyed-context-2026-11-15]].
{#handoff-list}

## Out of scope {#out-of-scope}

- Item-level dedup, labels by kind, curator status on change: plan-10, post-mod.
- Any presentation change beyond block order, including pointer-line renders and per-item-kind
  filters ([[#actions-removed]]), and tool-keyed rules: post-mod ([[plan-of-plans#post-mod]]).
- Retrieval quality (what `uncovered` needs): plan-30 and 30.6.
- STM admission (bug-166): 25.3.
- Subagent context: no injection reaches a subagent today, and none is added.
- bug-182's latency, beyond not making it worse than [[#r0-5-bands]] allows.
- The `.refmatrix/` ignore lines of fleet repositories (bug-261).
{#out-of-scope-list}

## Decisions {#decisions}

All six are **decided in [[plan-of-plans#decisions]]** and amended in here: D1 to D6 by ruling
L125 (the architect's recommendation; none changes a catalog on disk), D1 with the correction
of ruling L133. The POP row is the record; this section says where each decision lives in the
spec. {#decisions-status}

- **plan-31 D1: the capture is on by default in every store,** local to each store's
  `.refmatrix/`, bounded at 64 MiB and 42 days. As corrected by L133: the capture stores block
  payload text, which echoes up to eight prompt terms per call (the prompt itself only as a
  hash), so the directory writes its own `.gitignore` and a test proves it. Not taken: a
  marker-file opt-in; off by default. Amended into [[#r0-2-text]], [[#r0-4]], [[#ac-0-15]],
  [[#ac-0-18]], [[#risks]] item 5. {#d1}
- **plan-31 D2: "a week" is counted,** as at least 400 prompts in at least 6 sessions of 20 or
  more, at least 80 per block kind, closing at 800. Revision 2 states the per-kind count as
  delivered prompts, the count the bands read (ch-bsd r1 S6). Amended into [[#r1-0]],
  [[#ac-1-0]]. {#d2}
- **plan-31 D3: the band action table is confirmed before the numbers,** and the composite's
  cut (`--no-composite` in the generated hook) is put to the user again with the number in
  hand before release B. Revision 2 narrowed the table to actions with a knob and a test
  ([[#actions-removed]]). Amended into [[#actions]], [[#r2-1]]. {#d3}
- **plan-31 D4: `ignored` is reported only,** per session, and handed to 10.6 and the mod's
  design note; nothing is changed for it here. Amended into [[#r0b-4-remedy]], [[#handoff]].
  {#d4}
- **plan-31 D5: an `insufficient` kind is unchanged; an `ambiguous` kind takes `shrink` by
  default,** and S3 runs only on the user's go. Amended into [[#r1-2-table]] rows 4 and 7,
  [[#r2-1]], [[#s3]]. {#d5}
- **plan-31 D6: the capture stays on after this task,** bounded; 21.5 phase M, plan-10's
  re-measure and 30.6 read it. Amended into [[#r0-4]], [[#handoff]]. {#d6}

## Design choices in this draft {#spec-decisions}

These are how the draft is built, open to ch-bsd's challenge. They are not `plan-31 D<n>`
decisions. {#spec-decisions-note}

- **A separate capture file, joined by `query_id`,** not new fields on the recall-event schema.
  The event schema is per item and is read by 19.2's fold and 21.5; the capture is per call,
  carries text, and is bounded and prunable. One writer, in the module that owns the others.
- **The capture's outcome is on its own record** ([[#r0-2-outcome]]).
- **The classes are assigned from the agent's call, not from the injected item.** The pilot
  showed the other direction measures proximity.
- **`followed` is a candidate class** ([[#r0b-3-followed]]).
- **The before/after table decides nothing** ([[#limits-cannot]] item 2).
- **The member filter ships with the capture,** ahead of the window ([[#r2-0-body]]).
- **Recall and named-symbol bundles are never cut below a shrink here** ([[#actions-table]]).
{#spec-decisions-list}

## Revision 2: the ch-bsd r1 fold (2026-11-15, ruling L133) {#rev-r1}

ch-bsd spec review r1 read `f3a508f..3f6de0b` and returned DIRTY 3B/8S/11M. Ruling L133 in
[[plan-of-plans#rulings]] folds all of it. The report is held with this branch until its merge,
so its finding ids are written as code. This spec's share:

| Finding | Change here |
|---|---|
| `B1`: the capture's text would show in fleet repos' `git status`; D1 was summarised as "sha256 only" | [[#r0-4]]: the directory writes its own `.gitignore`; [[#ac-0-15]], mutation M0-10; [[#r0-2-text]] states plainly that prompt terms are stored; [[#risks]] item 5 rewritten against bug-261; "never added by rmx" removed |
| `B3`: bug-256 routed here with no requirement | [[#r0-7]], [[#ac-0-16]], mutation M0-11; `composite_error` on the record and on the report line; [[#r0-7-registry]] flags the registry wording |
| `S1`: the cost band was measured on a toy store | [[#r0-5-why]], [[#r0-5-method]]: a copy of the live catalog, fresh processes, the hook's command, 200 runs per arm, bundles built counted; `capture_ms` and `capture_built` on the record; [[#ac-0-13]] rewritten; [[#ac-0-17]] live |
| `S2`: the `query.log` row is already written | [[#r0-2-outcome]]: the outcome is on the capture record (`capture_ms`, `capture_built`, `pruned`, `composite_error`); failures go to `errors.jsonl` ([[#r0-4]]); `latency_ms` untouched; [[#ac-0-9]], [[#ac-0-10]] rewritten |
| `S3`: no capture-only switch | [[#r0-4]]: `RMX_INJECTION_CAPTURE=0` and a marker file; [[#ac-0-18]], mutation M0-12; [[#ac-0-4]] and [[#ac-0-5]] use it |
| `S4`: AC-0.8's canary contradicted R0.2 | [[#ac-0-8]] rewritten: two prompts, the canary only where the payload carried it |
| `S5`: five gaps around `followed` and `ignored`; the blind-label gate | [[#r0b-3-table]]: `self_found`; a search scoped by a delivered path is `followed`; `ignored` only for a delivered name or pattern; [[#r0b-3-lag]]; [[#r0b-3-overlap]]; [[#r0b-5-body]]: a seeded draw with weighted labels, 60 blind pairs, the gate on the lower bound; [[#ac-0b-1]], [[#ac-0b-2]], [[#ac-0b-6]], [[#ac-0b-7]]; mutations M0b-7 to M0b-9 |
| `S6`: a hole in the band table; `shrink` out of reach; closure counted produced | [[#r1-2-table]]: seven rows, total, each naming its interval; [[#r1-2-reach]] and its note; [[#r1-0]] condition 3 counts delivered; [[#ac-1-2]], mutation M1-3; [[#limits-cannot]] item 8 |
| `S7`: release B's ACs were RED for knobs that exist; three actions had no knob | [[#r2-1-table]]: per action, knob exists or new, characterization or RED; [[#ac-2-1]], [[#ac-2-2]]; mutations M2-2, M2-3 |
| `M2`: "about 430 a week" not reproducible | `sizing.py --since`; [[#sized-week]] cites its output (455) |
| `M5`: the bound's loose ends | [[#r0-4]]: a hard stop within a day; a file already removed is not an error; [[#ac-0-9]] |
| `M6`: no MCP no-capture test | [[#ac-0-11]], mutation M0-13 |
| `M7`: the scorer accepted a watched output dir | [[#r0b-1-out]], [[#ac-0b-5]] |
| `M9`: plan-10's dedupe said to run after this task | header, [[#r2-2]], [[#handoff]], [[#out-of-scope]]: post-mod by L128 |
| `M10`: two actions were new presentation | removed ([[#actions-removed]]); [[#actions-table]] holds only knob-backed actions |
| `M11`: the content bundle's state on a tier-1 stop | [[#r0-1-content]], a third test in [[#ac-0-3]], mutation M0-5 |
| D1-D6 decided (L125, L133) | [[#decisions]] |
{#rev-r1-table}

## Revision 3: the ch-bsd r2 fold (2026-11-15, ruling L140) {#rev-r2}

ch-bsd confirm-lite r2 read `3f6de0b..661bc73`: MEH-only GO, all 22 r1 findings closed, five
MEHs. Ruling L140 approves the spec once they fold. The report is held with this branch until
its merge, so its finding ids are written as code. This spec's share:

| Finding | Change here |
|---|---|
| `M1`: the AC-0.17 fallback was a release, with no stop row | [[#r0-4-mode]]: release A builds both capture paths behind one setting; `capture_mode` on the record; [[#r0-5-bands]] sets only the release default; [[#r0-5-live]]: the live table, the off marker first, and the stop row for mode `names` over 750 ms; [[#ac-0-3]] tests both paths; [[#ac-0-17]], [[#ac-0-18]] rewritten; mutation M0-14; [[#files-release]] cites the POP instead of a ninth gate |
| `M2`: the cost method did not name the binary | [[#r0-5-method]] step 2: `.venv-eval/bin/rmx` by path, never a bare `rmx`; [[#ac-0-13]] records its `rmx version -v` |
| `M3`: `.gitignore` only before the first append | [[#r0-4]]: checked before every write, created if absent; [[#ac-0-15]] gains the existing-directory and `errors.jsonl`-first cases; mutation M0-10 gains its second step |
| `M4`: the per-item tighten was dropped for the wrong reason | [[#actions-removed]] gives the reason (no knob, no test) and names the plan line that changed |
| `M5` | 31.3's ([[task-31.3-ledger-anchor-guard#rev-r2]]) |
{#rev-r2-table}
