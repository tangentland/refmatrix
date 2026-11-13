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
  updated: 2026-11-13
  revision: 3
---

# Task 21.5: a tool-level `used` signal {#root}

> Plan: [[plan-21-agent-context-usage]]
> Status: Pending. Rev 2 (2026-11-11) answered ch-bsd spec review r1 (DIRTY 18) and its addendum
> against 24.6 r5 ([[#rev-2]]). Rev 3 (2026-11-13) answers spec review r2 (DIRTY 14, NO-GO on
> b-1: the Bash leg re-opened the clone leg D12 rules out) and re-runs [[#why-data]] under the
> fix ([[#rev-3]]). The user decided OD-4 and OD-5 on 2026-11-13 (OD-5: a decay kernel replaces
> the hard window, [[#d18]]). It needs a spec re-review, and the user's answer on
> [[#ofu-cliquedb]], before approval.
> Wave: now. The user prioritised it on 2026-11-11, after reading `rmx telemetry --agent-usage`.
> Depends on: 21.1 (completed: the ONE recall-event schema, `emit_recall_events`,
> `delivered_in_session`, R12's three explicit evidences, the `--agent-usage` report), and 23.0
> (completed: the shared test sandbox).
> Touches the interfaces of 19.0 R2 and 19.2 (pending), 19.6 (pending), 24.6 (pending; amended
> to r6 with rev 2 and to r7 with rev 3) and 25.1 (pending). [[#open-for-user]] lists what
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
rel: derives-from -> [[bsd-task-21.5-spec-r2-540ab50]]
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

### What the data says (rev 3 re-run) {#why-data}

r1's review found three legs dead on contact with a 40-line join over scratch copies
([[bsd-task-21.5-spec-r1-15e8f64#imp-prototype-the-join]]); r2's found that rev 2's Bash leg
credited clone work through its `cwd` fallback ([[bsd-task-21.5-spec-r2-540ab50#b-1]]). So rev 3's
join was re-run, before this text was written, over fresh read-only APFS clones (`cp -c`, then
`chmod a-w`) of this project's `recall-events.jsonl`, `query.log`, `stm/*.jsonl` and
`catalog.read.duckdb`, plus the global events file and the GLOBAL `catalog.read.duckdb` ([[#r10]]),
under a `mkdtemp()` root, deleted afterwards. Window 2026-11-10T00:00Z to 2026-11-11 ~13:30 local
(rev 2's window). Only counts were printed; no prompt, command or body. Each row gives rev 2's
rules on the same clones (which reproduce r2's re-derivation exactly) and rev 3's rules: the Bash
base directory ([[#d15]]), git lines matched on their command only ([[#r3]]; r2 s-1), legacy Bash
paths from `detail` as well as the capped `refs` (r2 m-4), and global events resolved against the
global snapshot (r2 s-2). The prototype is still legacy-ordered (no `t_start`, no `origin` on any
line), so the numbers show direction, not the shipped result.
{#why-data-method}

| measure | rev 2 rules | rev 3 rules |
|---|---|---|
| prompts on the prompt clock ([[#r4]]) / ring `input` lines | 95 / 82 | same |
| prompts the clock holds with a prompt-recall row but no scan row | 4 | same |
| delivered events (project file + 6 from the global file for this root) / `precompact` gated | 2,440 / 20 | same |
| delivered units ([[#d7]]) over the remaining 2,420 events | 2,144 | same |
| prompt-time deliveries anchored to their own prompt by `query_id` | 2,366 of 2,366 | same |
| eligible events with a path from `Entity.path` / a memory's `source_path` / a grep-floor name | 1,581 / 396 / 45 | 1,581 / 401 / 45 |
| eligible events with no path: term concept / memory without `source_path` / id not in its snapshot (`path_unresolved`) | 158 / 98 / 142 | 158 / 99 / 136 |
| the 6 global-scope deliveries (5 ids): ids found in the project snapshot / in the global snapshot | 0 / not read | 0 / 5 |
| Bash + git ring events (3,451 Bash, 474 git) | 3,925 | same |
| of those: with a simple command based outside the project / on an unknown base / wholly inside | not computed | 2,897 / 146 / 901 |
| Bash refs counted `refs_outside_project` / `bash_base_unknown` / git diffstat refs no longer matched / Bash lines at the 8-ref cap | 0 / 0 / 0 / not counted | 8,022 / 329 / 876 / 458 |
| credited units: scan_prompt / prompt_recall / recall (agent) | 59 / 1 / 4 (64) | 30 / 1 / 4 (35) |
| of those, `prior_touch` (the file was touched before the delivery) | 46 | 17 |
| credited units with no prior touch (the headline numerator, [[#d8]]) | 18 | 18 |
| credited strata: Bash `bash_path` / Bash `bash_name` / Read, Edit, Write `path` | 35 / 29 / 0 | 13 / 22 / 0 |
| headline strata: `bash_path` / `bash_name` | 11 / 7 | 10 / 8 |
| credits whose command names a `/Volumes/littlebig/` path | 38 | 6 |
| units with a later matching call (any lag): first match at lag 0 / 1 / 2 / 3+ | 46 / 9 / 9 / 34 (98) | 27 / 3 / 5 / 21 (56) |
| Read / Edit / Write refs: under this project / under `/Volumes/littlebig/` / elsewhere | 14 / 269 / 65 | same |
| ring tool events: Bash / Read / Write / Edit / Grep, Glob, Agent, `mcp__*` | 3,451 (+474 git) / 134 / 109 / 105 / 0 | same |
| control units ([[#r7]]), keys and files never delivered in the session / touched | 723 / 6 | 723 / 4 |
| control units under R7's per-call rule (never delivered before `T`) / touched | not computed | 1,308 / 4 |

**b-1 alone.** With only the base-directory rule applied (git refs still matched, no `detail`
paths, global events against the project snapshot): 37 credited, 20 prior-touch, 17 headline.
s-1 alone on top of it removes 4 credits (33 / 17 / 16); the `detail` paths add 2 (39 / 20 / 19).
{#why-data-b1-alone}

**Why the headline did not move.** 8 of rev 2's 18 headline units are gone: 7 were clone
commands (5 `bash_path`, 2 `bash_name`) and 1 a git diffstat. 8 others joined: 7 had been
`prior_touch` only because a clone command touched the same relative path before the delivery,
and 1 is a `detail` path past the 8-ref cap. 10 of the 18 are the same units. So the rate is
unchanged by coincidence, and its composition is not.
{#why-data-headline}

Four facts follow. Only the Bash legs produce at present, and nearly three quarters of the
ring's Bash calls (2,897 of 3,925) run at least one simple command outside this tree, so the
base-directory rule ([[#d15]]) is what makes the Bash legs mean "this project". Most
Read/Edit/Write calls in this project's sessions touch paths under `/Volumes/littlebig/`, not
this tree, and cannot match (counted, [[#d12]]). About half the credits are still prior-touch,
which is why the headline excludes them. And the headline rate is small: under `W = 2`, 18 of
2,144 units (0.8%) against a control of 4 of 723 (0.6%) (the kernel's numbers are in
[[#why-data-kernel]]), so on this window the lift is within noise and [[#r12]]'s labelled sample, not this table, decides
whether the signal is worth counting.
{#why-data-reading}

#### The lag, uncapped, and the kernel (the user's OD-5 decision) {#why-data-kernel}

The rows above apply rev 2's `W = 2`. After the user replaced it with a kernel ([[#d18]]), the
join was re-run with no cutoff on the same clones, on the spec window and on the full delivery
range (2026-10-20, the events file's first line, to the copy, 2026-11-13 ~11:00 local). Each
unit's lag is its first qualifying touch's ([[#r5]]); bins 0 / 1 / 2 / 3 / 4 / 5 / 6-10 / 11-20 /
21-50 / 51+. Rev 2's "of 125 first matches ... 63 beyond `W`" counted matching EVENTS; per unit
it was 34 of 98, and 21 of 56 under rev 3's rules.

| measure (rev 3 rules unless stated) | 2026-11-10 window | 2026-10-20 to 2026-11-13 |
|---|---|---|
| eligible units | 2,144 | 8,303 |
| credited units / prior-touch / headline | 56 / 23 / 33 | 258 / 133 / 125 |
| first-match lag, all credits | 27/3/5/3/1/1/7/9/0/0 (56) | 78/28/15/10/10/7/42/39/23/6 (258) |
| first-match lag, headline | 13/2/3/1/0/0/6/8/0/0 (33) | 26/8/2/5/6/3/21/27/22/5 (125) |
| same, rev 2's rules (no base-directory fix) | 12/3/3/4/1/0/5/6/3/0 (37) | 26/15/4/9/7/3/17/25/23/6 (135) |
| headline by lag band 0 / 1-3 / 4-6 / 7+ | 13 / 6 / 2 / 12 | 26 / 15 / 17 / 67 |
| `score_headline`, `k = 3`, `h = 2` (share of units) | 20.7 (0.97%) | 52.5 (0.63%) |
| its parts by band 0 / 1-3 / 4-6 / 7+ | 13.0 / 6.0 / 0.7 / 1.0 | 26.0 / 15.0 / 8.6 / 2.9 |
| sensitivity `k = 4` / `k = 2` | 21.4 / 19.9 | 57.3 / 47.7 |
| binary `used_le2` (rev 2's headline) / `used_lag0` / a step at `k = 3` | 18 / 13 / 19 | 36 / 26 / 41 |
| control units (keys and files never delivered in the session) / touched | 723 / 8 | 2,611 / 28 |
| control kernel score (share) | 6.3 (0.87%) | 10.6 (0.41%) |
| control touched by band 0 / 1-3 / 4-6 / 7+ | 1 / 5 / 0 / 2 | 2 / 6 / 3 / 17 |
| per 1,000 units, headline vs control: lag 0 / 1-3 / 4-6 / 7+ | 6.1 vs 1.4 / 2.8 vs 6.9 / 0.9 vs 0 / 5.6 vs 2.8 | 3.1 vs 0.8 / 1.8 vs 2.3 / 2.0 vs 1.1 / 8.1 vs 6.5 |
| control under R7's per-call rule: units / touched / kernel score | 1,308 / 8 / 6.3 (0.48%) | 5,218 / 36 / 12.8 (0.25%) |

The "rev 2's rules" rows reproduce the lead's own uncapped counts on separate copies (spec window
46/9/9/7/6/0/9/7/5/0 over all 98 credits; headline 37; long window 373 credits, headline 134
against 135 here, the window's end differing by minutes). {#why-data-kernel-check}

**cliquedb, the second corpus (the lead's run, 2026-11-13; not re-run here).** 2026-11-04 to
2026-11-11, 5,874 units: all first matches 39/34/11/9/9/10/20/30/32/21 (215); headline
11/6/3/3/0/1/12/9/15/12 (72); headline without commands that leave the project (the lead's
proxy for [[#d15]]: a `cd`, `pushd` or `git -C` to an absolute directory outside it, or a
`/Volumes/littlebig` path) 11/6/3/3/0/1/11/9/14/10 (68). Kernel about 26 against 20 for `W = 2`;
rate about 0.4%. The proxy removes 4 of 72 there, against 62 of 134 in this project, whose
isolated work runs in clones. AC-15 re-runs cliquedb under the real rule.
{#why-data-cliquedb}

What this says, before any label is read. Lag 6+ is most of the headline credits on the long
windows (75 of 125 here, 60%; 50-65% in the lead's runs), but the kernel gives the 7+ band
little weight (2.9 of 52.5 here). Per unit, lag 0 is four times the
control's rate; lags 1-3, inside the plateau, are not above it on either window here; 7+ is
close to it. So the kernel-matched control does what the user's decision needs it to do: it
shows the tail and the plateau are not yet distinguishable from coincidence. [[#r12]]'s lag
bands, labelled, decide; these counts do not.
{#why-data-kernel-reading}

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
   - **What the column would count (D18).** Kernel-weighted headline credits, `Σ w(U)`, with
     the evidence weight from [[#r12]]'s kernel-weighted precision `p_w`; never a binary
     count, so the column and the band measure the same thing.
5. **D5: no new verb, command or flag.** {#d5}
   - `telemetry` is a `harness` entry in `verbs.LEGACY_UNPAIRED`, and `--agent-usage` already
     exists. This task adds report lines and no agent-callable capability, so verb parity and
     the generated CLI tree do not change.
   - The kernel's `k` and `h` are committed constants, not flags ([[#d18]]). The report function's
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
     visible. The re-run gives 2,420 eligible events in 2,144 units ([[#why-data]]).
8. **D8: the headline excludes prior-touch; both numbers are printed (m-7).** {#d8}
   - A file the agent touched before the delivery and touches again after it is weak evidence
     that the delivery caused the second touch. In rev 3's re-run, 17 of 35 credited units are
     prior-touch (46 of 64 under rev 2's rules, most of them made prior by clone commands).
   - **Lead decision.** The headline counts units used explicitly (R12) or credited by a tool
     call with `prior_touch = no`; `score_incl_prior` (prior-touch credits included) is printed
     on the same line. Neither is hidden. Since the user's OD-5 decision both are
     kernel-weighted scores over `eligible_units` ([[#d18]]), with `used_headline` and
     `used_incl_prior` (unweighted unit counts) printed beside them.
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
      [[#r12]]'s bands. That leg is task 21.6, filed with acceptance criteria as a plan-21 task
      row and a deferral-registry row ([[plan-21-agent-context-usage#tasks]],
      [[deferral_registry#registry]]); its trigger is 24.6 R4 shipping the field (r2 s-5).
11. **D11: the report resolves paths against a logical root (s-4).** {#d11}
    - The ring stores no `root`; pre-task Bash lines store no `cwd`; and R8's global-file filter
      compares each event's recorded `root` with the reader's. Run against a clone (AC-15), the
      reader's root is the clone's `mkdtemp()` dir, so relative refs miss (58 of 58 first
      touches in r1's prototype were Bash) and the global filter returns nothing.
    - **Decision.** `agent_usage_report(root, *, logical_root=None, ...)`: `logical_root` defaults
      to `root`. It is the root the logs were WRITTEN for. The global filter compares
      `norm_path(event.root)` with `norm_path(logical_root)`. A Bash line with no `cwd` STARTS
      at `logical_root`'s parent (the project dir), counted `cwd_fallback`; that is only the
      start: a `cd`, `pushd` or `git -C` in the command moves the base ([[#d15]], r2 b-1). The
      files are read from `root`. Production never passes it; AC-15 passes the live root's path
      as a string and opens nothing under it.
12. **D12: paths outside the project are counted, not matched.** {#d12}
    - In the re-run ([[#why-data]]), of 348 Read/Edit/Write refs, 14 touch this project, 269 a
      path under `/Volumes/littlebig/` (where this project's isolated write work runs, in
      `<project>-<worker>` clones) and 65 somewhere else. A clone's copy of a file is a different
      path from the delivered item's. Which loop issued those calls was not measured (no ring
      line carries `origin` yet).
    - **Decision.** No clone or repo-relative leg, on ANY leg that resolves a path (r2 b-1: the
      rule was first written for Read and came back through Bash's relative refs). Tool-event
      refs outside `logical_root`'s project dir are counted per tool (`refs_outside_project`),
      so the gap is visible. A Bash simple command, or a Grep / Glob call, whose base directory
      is outside the project matches nothing, by path or by name ([[#d15]]). A
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
    - **The parked call keeps its fields (r2 m-3).** Rev 2's park record held only `terse`,
      `refs` and a `detail` cut at 600 (`stm.py:1260`), so a swept call had no `tool`, `origin`,
      `command` or `tool_use_id`, and an abandoned subagent call was credited as
      `origin_unknown`. `Stm.inflight_begin` now stores the builder's `ToolEventFields` ([[#r1]])
      in the park record, and the sweep writes them on the `abandoned` event, `origin` included
      when the park knew it (envelope `agent_id`, or the mod's `origin_known`). These are a
      superset of the park fields 19.0 R2 adds (`tool_use_id`, `tool_name` as `tool`); 19.0 adds
      `transcript_path` and its input digest, and runs its ladder on a swept call whose park has
      no `origin` ([[task-19.0-stm-cluster-hygiene#requirements]]). A park record written before
      this task has none of the fields; its swept event is read as a legacy line ([[#r10]]).
15. **D15: a Bash call's base directory comes from its command, not only the envelope (r2 b-1).**
    {#d15}
    - **The defect.** Rev 2 resolved a relative Bash ref against the envelope `cwd`, else
      `logical_root`'s parent. The envelope `cwd` is the session's working directory, not the
      directory a compound `cd X && …` runs in, and a subagent's cwd resets on every call. So
      `cd /Volumes/littlebig/<clone> && sed -n 1,40p src/refmatrix/telemetry.py` credited the
      PROJECT's `telemetry.py`: the clone leg [[#d12]] rules out, re-opened. Under rev 2's rules
      38 of 64 credits came from commands naming a clone path, 32 of them a `cd` into one.
    - **Decision (the fix r2 prescribes).** `telemetry.bash_segments(command, start) ->
      list[BashSegment]` is the ONE parser. It splits the command into simple commands at
      `&&`, `||`, `;`, `|`, newlines and parentheses (quoted text is not split). The start base
      is the envelope `cwd` (a legacy line: `logical_root`'s parent, counted `cwd_fallback`). A
      simple command `cd D` or `pushd D` sets the base for itself and every later simple
      command (a relative `D` resolves against the current base; a bare `cd` is `$HOME`).
      `git -C D …` sets the base for its own simple command only. A `D` that cannot be resolved
      statically (`$VAR`, a backtick or `$(…)`, `cd -`) and `popd` make the base unknown.
    - **What matches.** A relative ref resolves against its simple command's base; an absolute
      ref is taken as is. A ref that lands inside the project matches under `bash_path`,
      whatever the base (an absolute project path names a project file). A relative ref on a
      base outside the project counts `refs_outside_project`; one on an unknown base counts
      `bash_base_unknown`; neither matches. A name token matches under `bash_name` only in a
      simple command whose base is inside the project. A Bash call with any simple command
      whose base is outside the project or unknown is counted once in
      `bash_names_outside_project` (its tokens there were not matched).
    - **Why the name leg too (lead).** A name in a command run inside a clone is the same act
      as a path there: the clone's copy of the symbol, run mostly by a worker that never saw the
      delivery ([[#d13]]). Matching it would re-open the clone leg by name.
    - **Grep and Glob (lead).** Their `path` input is their base (absent: `cwd`). Outside the
      project they match nothing, counted `refs_outside_project`; the Grep `name` and Glob legs
      apply only inside it.
    - **Not a shell interpreter.** It does not expand variables, aliases or functions, follow
      `source`, or undo a subshell's `cd` at `)`. What it cannot resolve it counts and does not
      match, so its errors can only lower the rate, never credit a clone.
    - **Measured** ([[#why-data]]): 2,897 of 3,925 Bash + git events run a simple command outside
      the project, 146 on an unknown base. Credits fall from 64 to 35; credits from commands that
      name a clone path fall from 38 to 6, each matching in a simple command based in the
      project; the headline stays 18 with 8 units exchanged ([[#why-data-headline]]).
16. **D16: R12's precision is measured on the population a consumer would count (r2 s-3).**
    {#d16}
    - Rev 2 drew "credited (U, T) pairs", so prior-touch credits (17 of 35 in rev 3's re-run, 46
      of 64 under rev 2's rules) would make up much of a sample whose band gates a 19.2 column,
      while [[#d8]]'s headline excludes them.
    - **Decision (lead).** A consumer counts headline credits only: 19.2's `used_tool` column
      ([[#d4]]) and [[#od-3]]'s drain write and count credits with `prior_touch = no`. So
      [[#r12]]'s banded sample is drawn from headline credits. Prior-touch credits get their own
      labelled stratum of up to 20 pairs, reported with its precision and never banded or
      weighted, so the report still says what `score_incl_prior` is made of.
17. **D17: only R12's three explicit MCP tools are skipped; other `mcp__refmatrix__` tools match
    by name (r2 m-5).** {#d17}
    - Rev 2 skipped every `mcp__refmatrix__*` tool while a Bash `rmx grep` matched as Bash: two
      policies for one act.
    - **Decision (lead).** `mcp__refmatrix__rmx_context`, `mcp__refmatrix__rmx_memory_get` and
      `mcp__refmatrix__rmx_focus_note` are R12's explicit evidences: skipped and counted
      (`skipped_explicit_tool_calls`), as their Bash forms are. Every other
      `mcp__refmatrix__*` tool matches under `mcp_name`: a whole token of its string arguments
      equals the item's `name`, by the `bash_name` tokeniser and gate. R1 records those
      arguments as `args`. Live from 24.6 R4 ([[#d6]]). Tools of other MCP servers stay
      unmatched, counted per tool.
18. **D18: credit is weighted by a decay kernel on prompt lag, not cut at a window (the user,
    2026-11-13, OD-5).** {#d18}
    - **The user's decision.** "Why don't we use a sliding score that gradually decays instead
      of using a hard boundary", refined: "i would think 3 or 4 would be better to begin the
      decay". It replaces rev 2's hard window `W = 2`. The shape below was drawn up by the lead
      from those two sentences and pre-registered here before any labelling; [[#rev-3]] lists
      what about it the user should still see.
    - **The kernel.** `telemetry.tool_used_weight(lag, *, k, h) -> float` is the ONE weight
      function: `1.0` for `lag ≤ k`, else `2 ** (-(lag − k) / h)`. Pre-registered:
      `TOOL_USED_PLATEAU_K = 3` (the lead's pick inside the user's "3 or 4") and
      `TOOL_USED_HALF_LIFE_H = 2` prompts. There is no cutoff: a touch at any lag in the same
      session credits, at its weight. The session's end is the only bound.
    - **Raw lag is kept (D1).** Every credit record stores its integer `lag_turns`; the weight
      is computed at report time, so a different `k` or `h` rewrites no data.
    - **A unit's weight** is the maximum of `w(lag)` over its qualifying touches ([[#r5]]).
      An explicit R12 use ([[#r6]]) weighs 1: it names the item, so it is not inferred from
      proximity (lead).
    - **The headline is a weighted score.** `score_headline = Σ w(U) / eligible_units` over
      headline-credited units ([[#d8]]); `score_incl_prior` likewise. Printed beside it, for
      comparability: the binary counts `used_lag0` and `used_le2` (rev 2's `W = 2`), the full
      lag histogram, and a **sensitivity row**, the same score with `k = 4`
      (`TOOL_USED_SENSITIVITY_K`). The sensitivity row is not a second headline.
    - **The control is scored with the same kernel** ([[#r7]]), and `lift` is the difference
      of kernel scores. That is the test of whether far-lag credits are real: a coincidental
      touch long after a delivery is as likely for a trimmed item the agent never saw, so it
      raises the control score as much as the headline.
    - **Checked against measured precision.** [[#r12]] stratifies its sample by lag band
      (0, 1-3, 4-6, 7+; the plateau edge is a band edge), with Wilson bounds per band, and says
      when a band's credit rate is indistinguishable from the control's.
    - **Measured** ([[#why-data-kernel]]): on 2026-10-20 to 2026-11-13, 125 headline credits
      over 8,303 units score 52.5 under the kernel (0.63%) against 36 under `W = 2`; the
      control scores 0.41%. Lag 0 is clearly above the control; lags 1-3 and 7+ are not.

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
   - **Every tool-call line goes through it (r2 s-1, m-3).** Three writers record a tool call,
     and each takes the builder's fields: the `tool` line; the `git` line of the git-milestone
     branch (`cli.py:2161-2180`), which keeps its own `terse` (subcommand + first output line)
     and its diffstat `refs`, and takes every other field from the builder, so it carries
     `t_start`, `tool: "Bash"`, `cwd`, `command`, `tool_use_id` and `origin`; and the sweep's
     `abandoned` line, from the park record ([[#d14]]). The `reason` lines the git branch also
     writes are not tool calls and take no fields.
   - **The park record holds them.** `Stm.inflight_begin` stores the builder's
     `ToolEventFields` (all but `t_start`) beside `t`, `terse`, `refs` and `detail`;
     `inflight_end` returns them and `inflight_sweep` writes them on the `abandoned` event with
     `t_start` = the parked `t` ([[#d14]]).
   - **A tool-call line gains:**
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
       (Agent / Task), and `args` for an `mcp__*` tool (its string arguments as a JSON object,
       [[#d17]]). Each is capped at `stm.INPUT_FIELD_MAX = 2000` characters; a capped field is
       named in `input_truncated` (a list) and counted by the report. Edit / Write bodies are
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
     - every other item: the entity's `Entity.path`, or null (a term concept). A relative
       `Entity.path` (94 entities on the snapshot) is joined to the store root's parent, the
       tree it was indexed from, never resolved against the emitter's cwd (r2 m-6).
   - **The emitters already hold the item.** `context._item` / `bundle_items` (anchor, attached
     memory, group entries); `scan.py` through the context bundle; `telemetry.recall_item`
     (recall hits, through `Store.item_meta`, which gains `e.path` and the memory's
     `metadata->>'source_path'` by a left join, both in `context.ITEM_META_FIELDS`).
   - **The plumbing that filters item keys carries it (r2 m-6).** `context.annotate_items`
     fills `path` and `source_path` alongside `partition` and `mtype` in its ONE catalog query
     (its `fields` tuple, `context.py:1781`), and `telemetry._item_fields`
     (`telemetry.py:1386`) passes `path`, so no emitter drops it on the way to
     `emit_recall_events`.
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
   | Grep | `name` | its base ([[#d15]]: `input_path`, else `cwd`) is inside the project, and a whole token of `pattern` equals the item's `name`; tokenised by 21.1 R12's `_NOTE_TOKEN_RE` and gated by `_matchable`, the focus-note matcher, not a new one |
   | Glob | `glob` | its base is inside the project, the item's `path` basename appears literally in the pattern's last component, AND `fnmatch(path, pattern)` (`**/*.py` alone matches nothing) |
   | Bash (and `kind = git` lines) | `bash_path` | a path in `command` (legacy: `detail`, plus the `refs` of a `tool` line), resolved against its simple command's base ([[#d15]]), lands inside the project and equals the item's `path` |
   | Bash (and `kind = git` lines) | `bash_name` | in a simple command whose base is inside the project, a whole token equals the item's `name` (same tokeniser and gate) |
   | Agent, Task | `name` | a whole token of `prompt` equals the item's `name`. Live from 24.6 R4 ([[#d6]]) |
   | `mcp__refmatrix__*` except R12's three | `mcp_name` | a whole token of `args` equals the item's `name` (same tokeniser and gate). Live from 24.6 R4 ([[#d17]]) |
   | any other tool | none | not matched; counted per tool name in `tool_events_unmatched_by_tool` |

   - **Where the Bash paths come from (r2 m-4).** `tool_touches` extracts paths from the whole
     `command` it is given with `stm._PATH_RE`, with no count cap (the ring's `command` is
     capped at 2,000 characters, named in `input_truncated`). It never reads `refs`: the shell
     hook's `refs` are capped at 8 (`cli.py:2027`; 458 of 3,451 live Bash lines sit at the cap).
     A legacy `tool` line has no `command`: `ring_tool_call` gives `detail` as the command
     (paths with their positions, so each finds its simple command) plus every `refs` entry not
     found in `detail`, resolved against the base at the end of `detail`; a line whose `refs`
     are at the cap is counted `refs_capped`.
   - **Git lines match on their command only (r2 s-1).** A `kind = git` line's `refs` are a
     diffstat of `cwd` (else the project), not the paths the command names: a commit made in a
     clone records the project repo's diffstat. So a git line matches on `command` (legacy:
     `detail`, which the git branch fills with the verbatim invocation) and never on `refs`.
   - **Explicit calls are skipped.** `mcp__refmatrix__rmx_context`,
     `mcp__refmatrix__rmx_memory_get` and `mcp__refmatrix__rmx_focus_note` (live from 24.6 R4),
     and a Bash command whose first `rmx` invocation is `context`, `memory get` or `focus note`.
     Those are R12's explicit evidences; matching them here would count one act twice. They are
     counted (`skipped_explicit_tool_calls`) and never matched.
   - **Other `rmx` commands match as Bash**, including `rmx grep`, the shim's target; other
     `mcp__refmatrix__` tools match under `mcp_name`, so one act has one policy ([[#d17]]).
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
     - `T.t_start` is strictly after the unit's first delivery `ts` (UTC, R10), decided by ONE
       pure function, `telemetry.tool_after_delivery(t_start, d_ts, *, t_start_exact,
       d_ts_exact) -> bool | None`: `True` when strictly after, `False` when at or before,
       `None` (counted `order_ambiguous`) for the legacy tie below. Every ordering in this
       task calls it (r2 m-1: equality is only testable through the function);
     - `lag_turns = idx(T) − idx(U) ≥ 0`, with no upper bound; the credit's weight is
       `tool_used_weight(lag_turns, k=3, h=2)` ([[#d18]]; the user's OD-5 decision replaced rev
       2's `W = 2`);
     - `T`'s `origin` is `parent` or absent ([[#d13]]).
   - **Reads before delivery never count.** A match whose `T` precedes the unit sets
     `prior_touch` on that file (or key) for every LATER unit of it in the session. A credit
     with `prior_touch` is still a credit; the headline excludes it ([[#d8]]).
   - **Every lag is kept.** The lag histogram's bins are 0, 1, 2, 3, 4, 5, 6-10, 11-20, 21-50,
     51+.
   - **Subject rings.** A session's events are the union of `<session>.jsonl` and every
     `<session>__<subject>.jsonl` (`stm._partition_key`), merged by `t`.
   - **Legacy ties.** When either side of a comparison has only second resolution and the two
     fall in the same second, the pair is counted `order_ambiguous` and credits nothing.
5. **R5: attribution and dedupe (per unit).** {#r5}
   - Each unit is credited at most once. Its weight is the maximum of `w(lag_turns)` over its
     qualifying touches; its credit record keeps the touch that gave it (the earliest, since
     a later touch of the same unit never has a smaller lag).
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
   - The same matcher, kernel and ordering run over **control units**: `retrieved` items with no
     `delivered` event for the same `query_id` and key (retrieved, then trimmed, so the agent
     never saw them), whose key AND file were never delivered in the session before `T`.
   - Control units are scored with the same kernel ([[#d18]]): `control_score = Σ w / control
     units`. The report prints `lift = score_headline − control_score` per channel and per
     `kind`, and the control's per-unit credit rate per lag band (0, 1-3, 4-6, 7+) beside the
     headline's, which [[#r12]] uses.
   - Stated bias: trimmed items rank lower, so the control under-estimates the base rate and the
     lift over-estimates the effect.
8. **R8: the report.** `agent_usage_report` gains a `used by channel` block. Per delivering
   channel, over the window: {#r8}
   - `delivered` (events), `eligible` (events) and the exclusions ([[#r9]]); `units` and
     `anchors_in_units` ([[#d7]]);
   - `used_explicit` per R12 evidence; `used_tool`; `used_headline`; `used_incl_prior`;
   - `score_headline` and `score_incl_prior` (kernel-weighted, [[#d18]]), each as `Σ w /
     eligible_units` with a percentage, on one line; beside them the binary `used_lag0` and
     `used_le2`, and the `k = 4` sensitivity row (labelled `sensitivity`, never `headline`);
   - `used_tool` split by `tool`, by `match_on`, by `prior_touch` and by `origin` (`parent` /
     `unknown`);
   - a **leg table**: each R3 leg with its ring event count and producer status (`live`, or
     `not-yet-producing`, [[#d6]]) and its rate (`n/a` when it has no events);
   - the `lag_turns` histogram (0, 1, 2, 3, 4, 5, 6-10, 11-20, 21-50, 51+), and `censored`:
     eligible units with fewer than `k` later prompts in their session, whose plateau the
     session did not reach (kept in the denominator, count shown);
   - per-distinct-file: `distinct_used / distinct_eligible`;
   - the control's kernel score and the lift on kernel scores, and per lag band (0, 1-3, 4-6,
     7+) the headline's and the control's per-unit credit rates ([[#r7]]);
   - the prompt clock line: prompts, prompt-clock rows by kind, prompts without a scan row,
     ring `input` lines, `prompt_unanchored`, `prompt_rows_legacy`;
   - an **`any channel` row** (r2 m-8): credited units collapsed across channels to
     `(session, prompt, file or key)`, over eligible units collapsed the same way, so a file
     that scan_prompt and prompt_recall both delivered for one prompt and one Read used counts
     once there and once under each channel.

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
     `delivered = eligible + no_session + no_ring + precompact_gated`. A mismatch is loud (r2
     m-7): `agent_usage_report` raises `telemetry.UsageIdentityBroken`, which carries the
     report's lines and an `identity-broken delivered=<n> eligible=<n> …` line; `cli.telemetry`
     (`cli.py:7795`, which today only echoes the returned lines) catches it, echoes the lines,
     writes the `identity-broken` line to stderr and exits 1. The return type stays
     `list[str]`, so 21.1's callers and tests are unchanged.
   - **Every other count, printed even when 0**, on one `used-by-channel exclusions` line:
     `no_path`, `memory_no_source_path`, `path_from_catalog`, `path_unresolved`,
     `path_from_name`; `prompt_unanchored`, `prompt_rows_legacy`, `order_ambiguous`,
     `order_from_end`, `cwd_fallback`; `ring_unparseable`, `tool_from_terse`,
     `input_truncated`, `detail_truncated`, `refs_capped`; `skipped_explicit_tool_calls`,
     `tool_events_unmatched_by_tool`, `refs_outside_project`, `bash_base_unknown`,
     `bash_names_outside_project` ([[#d15]]); `origin_unknown`,
     `subagent_tool_events`, `origin_unattributed`; `credited_abandoned`;
     `result_mentions_present`; `explicit_ref_unresolved`.
10. **R10: legacy data (the window the user already asked about).** {#r10}
    - **Events without the `path` key** (written before this task). Their path is resolved from
      the read snapshot by `entity_id` through the same `item_path` rules (memories by
      `memory_content.metadata.source_path`), using the normal CLI read path, never a `Store()`
      open on the active slot. Counted `path_from_catalog`; an id not found is counted
      `path_unresolved` and falls back to the name rules.
    - **A legacy event resolves against the store that minted its id (r2 s-2).** A
      `scope = global` event's `entity_id` belongs to the GLOBAL catalog, so it is resolved
      against the global store's read snapshot (`derive_tool_used`'s `global_root`, default
      `telemetry._global_root_default()`), through the same read path pointed at that root;
      never against the project snapshot, where an id collision would give a confident wrong
      path. A global id not found there is `path_unresolved`. On the re-run the 5 ids of the 6
      global deliveries are all in the global snapshot and none in the project's
      ([[#why-data]]).
    - **Ring lines without `t`** are ordered by their local `ts`, converted with `time.mktime`
      (ties per [[#r4]]).
    - **Ring lines without `tool`** take the tool from `terse`'s first token, counted
      `tool_from_terse` (m-3). `kind = git` lines are Bash calls (the git-milestone branch of
      the tool hook) and are read as `tool = Bash`, with `detail` as the command and their
      diffstat `refs` ignored ([[#r3]]). Post-task git lines carry `tool` and `command` from the
      builder ([[#r1]]).
    - **Query.log rows without `t`** start at `ts − latency_ms` ([[#r4]]).
    - **What this gives.** A number for 2026-11-10 onward on the day it ships, marked
      `legacy-ordered=<n>`, so it is not read as exact.
11. **R11: no hook emits.** After this task, a `used` event with an evidence other than R12's
    three appears in no `recall-events.jsonl`. `rmx focus hook` opens no `recall-events.jsonl`
    and makes no `delivered_in_session` call. R12's sentence "a `hook` call never emits `used`"
    stays true without an exception clause. {#r11}
12. **R12: pre-registered precision bands (s-6), before any consumer counts it.** {#r12}
    - **The population (r2 s-3, [[#d16]]).** The banded sample is drawn from headline credits
      (`prior_touch = no`), the credits a consumer would count. Every count below (the 50, the
      80, the strata) is of headline pairs. Prior-touch credits are a separate, report-only
      stratum: up to 20 pairs drawn uniformly, labelled the same way, their precision printed,
      never banded, dropped or weighted.
    - **The source window.** Credited headline `(U, T)` pairs from the 21 days after the deploy
      sha recorded in the implementation summary. Under 50 pairs at day 21: the window extends
      to day 42. Still under 50: the result is **report-only** (the default; no band is read) and
      R12 re-runs on the next 21-day window.
    - **The draw, stratified by lag band (the user's OD-5 decision, [[#d18]]).** The bands are
      `lag_turns` 0, 1-3, 4-6 and 7+, so the kernel's plateau edge (`k = 3`) is a band edge.
      All headline pairs when there are at most 80; otherwise uniform within each lag band,
      each band taking `min(available, max(20, its proportional share))`, at least 50 in total.
      Each pair's `tool` × `match_on` is recorded for the stratum rule below. The pair list's
      sha256 is committed and frozen.
    - **The labels.** Per pair, from the local transcript (d8f: raw text stays local; labels,
      the hash and the counts are committed): "the delivery plausibly caused the tool call"
      yes / no, and the call's origin (main loop / subagent / unclear). The labeller is
      [[#od-2]].
    - **Which pairs are judged.** Precision is computed over the main-loop pairs, `n_main`. The
      subagent share of all labelled pairs is printed. When it exceeds 10% and neither 19.0 R2
      nor 24.6 R4 is live, no band above report-only applies, because the live rate still
      carries those false credits.
    - **Per lag band.** Each band's precision over its main-loop pairs, with its Wilson 95%
      interval; a band with fewer than 20 is `underpowered`. Beside it, the band's per-unit
      credit rate on the source window and the control's per-unit rate in the same band
      ([[#r7]]): when the control's rate lies inside the Wilson 95% interval of the band's
      rate, the report says `indistinguishable from control` for that band. A band with at
      least 20 main-loop pairs whose precision Wilson upper bound is below 0.50 means the kernel
      over-weights it: `k` and `h` are revised to new pre-registered values and re-measured on
      a fresh draw, and until then the result is report-only.
    - **Pooled bands.** `p_w` = the kernel-weighted precision over the main-loop pairs: each
      pair weighs its kernel weight `w(lag)` times its band's inverse sampling fraction, so
      `p_w` is the precision of what a consumer counting `Σ w(U)` would count ([[#d4]]). Its
      Wilson 95% interval uses the Kish effective sample size of those weights. `n_main` is the
      number of main-loop pairs. Recorded here before labelling
      ([[feedback_go_no_go_ranges_not_predrop]]); the user confirmed the 21 / 42-day window,
      the report-only default under 50, the 20-pair minimum and the 10% subagent ceiling on
      2026-11-13:

    | condition | action |
    |---|---|
    | `n_main < 50` | report-only (the default). No band is read; R12 re-runs |
    | `p_w ≥ 0.80` and Wilson lower bound `≥ 0.65` | 19.2 may add a `used_tool` column (a migration, 19.2 R1) counting `Σ w(U)`, weight `w_tool = round(2 × p_w, 1)` |
    | `0.50 ≤ p_w`, and not the row above | report-only; 19.2 does not count it; the stratum rule below runs |
    | `p_w < 0.50` | the matcher or the kernel is revised and re-measured; nothing downstream changes |

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
hand-written, except these, each because its producer is pre-task or not built by this task
(r2 m-8): AC-2b's pre-task event and AC-9's hand-written rows (legacy shapes copied from a
HEAD-era emitter's and hook's field sets, and edge rows no real producer writes on demand, each
marked in AC-9's table); AC-7's legacy parity lines
(pre-task); AC-14's `origin: "unattributed"` line (19.0 R2's value); AC-16's Agent line, AC-17
(d)'s `prompt_id` rows and AC-18's `result_mentions` line (24.6's producers). Every
hand-written line copies its producer's field set as that producer's spec states it.
{#ac-producers}

1. **AC-1 (R1): ring fields, one builder.** A `tool-pre` then `tool` envelope pair for a Read of
   `F` (with `cwd` and `tool_use_id` set) writes one ring `tool` line carrying `t`, `t_start`
   (= the parked `t`), `tool: "Read"`, `cwd`, `tool_use_id`, `input_path == F`, and no `origin`
   key. The same pair with `agent_id: "a1"` in the envelope writes `origin: "agent:a1"`. A Bash
   whose command is 2,500 characters writes `command` of 2,000 and `input_truncated:
   ["command"]`. A `tool` envelope with no prior `tool-pre` writes `t_start: null`. A call
   parked and then swept writes `abandoned: true` with `t_start` = the parked `t`; the same
   with `agent_id: "a1"` on the `tool-pre` envelope writes the swept line with `origin:
   "agent:a1"`, `tool`, `tool_use_id` and `input_path` (r2 m-3). A Bash `git commit` pair, run
   in a tmp repo, writes a `git` line carrying `t_start`, `tool: "Bash"`, `cwd`, `command` and
   `tool_use_id` beside its diffstat `refs` (r2 s-1).
   **One builder, not one import (r2 m-8).** (a) For each of the three tool-call writers (the
   `tool` line, the `git` line, the swept line), the ring line's builder fields equal
   `stm.tool_event_fields(...)` called on the same envelope, field by field. (b) A pass-through
   spy on `stm.tool_event_fields` (it calls the real function and counts) sees exactly one
   call per `tool-pre` and one per `tool` envelope. (c) An AST scan of `src/refmatrix/` finds
   exactly one function that stores a value under the key `"input_truncated"` (a dict-literal
   key or a subscript store), `stm.tool_event_fields`; an inline copy under another name fails
   it. `cli._tool_event_fields` no longer exists.
   **RED at HEAD:** the line has none of the new fields; the builder is in `cli`; the git line
   has no `tool`. {#ac-1}
2. **AC-2 (R2, D3): `path`, and `v` stays 1.** A real scan-prompt over a tmp store holding code
   file `F` writes delivered events for `F`'s symbols with `v == 1` and `path ==
   norm_path(F)`. A real `memory recall --stdin-json` over a tmp memory dir writes a
   `kind=memory` delivered event whose `path` is the memory file's `source_path`. A memory row
   with no `source_path` and a term concept each write the key with `path: null`. A grep-floor
   item `src/x.py` writes the store root's parent joined with it. A code entity whose
   `Entity.path` is relative writes the store root's parent joined with it, with the test's
   cwd set elsewhere (r2 m-6). The scan-prompt case runs twice, once on a store root spelled
   `/tmp/…` for a dir under `/private/tmp/…`: both write the same `path` (r2 m-8, the
   `norm_path` mutation). `"path" in RECALL_EVENT_FIELDS_V1`. **RED at HEAD:** no `path` key; memories have no
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
   tool `Read`, `match_on=path`, `prior_touch=no`, `lag 0=1`, weight `1.000`, and
   `score_headline` and `score_incl_prior` with `eligible` units as the denominator. **RED at HEAD:** there is no
   `used by channel` block. {#ac-3}
5. **AC-4 (R4, D8): before delivery never counts.** (a) A Read of `F` in prompt 1, then a
   delivery of `S` in prompt 2, and no later Read: `used_tool=0`. (b) As (a), plus a Read of
   `F` in prompt 2: `used_incl_prior=1`, `prior_touch=yes`, `used_headline=0`. (c) A Read of
   `F` whose `t_start` precedes the delivery's `ts` but whose PostToolUse lands after it: not
   credited. (d) Through the pure function (r2 m-1): `tool_after_delivery(x, x, exact, exact)`
   is `False`, `tool_after_delivery(x + 0.001, x, …)` is `True`, and a second-resolution pair in
   the same second is `None`. **RED at HEAD:** no block, no function; with an ordering
   mutation, (c) is credited. {#ac-4}
6. **AC-5 (R4, D9, D18): every prompt counts, and the kernel weighs the lag.** {#ac-5}
   - **(a) The kernel, end to end.** Five delivered files, each Read once, at lag 0, 3, 4, 5
     and 9 (real prompts): every one is credited, with weights `1.000`, `1.000`, `0.707`,
     `0.500` and `0.125`, and `score_headline` is their sum over `eligible_units`. One unit
     touched at lag 1 and again at lag 6 weighs `1.000` (the maximum, [[#r5]]). The
     sensitivity row (`k = 4`) prints the lag-4 credit at `1.000` and the lag-5 credit at
     `0.707`, while the headline keeps `k = 3`. These values kill: `k` 3 → 2 (lag 3 weighs
     0.707), `k` 3 → 4 in the headline (lag 4 weighs 1.000), `h` 2 → 1 or 2 → 3 (lag 5 weighs
     0.250 or 0.630), the kernel replaced by a step at `k` (lags 4, 5 and 9 weigh 0), rev 2's
     hard window (lags 3 to 9 weigh 0), and a unit weighted by its last or summed touches.
   - **(b) The clock counts every prompt.** An AMBIENT prompt (a real `focus hook --event
     input` and scan-prompt hook run on a `<task-notification …>` prompt, which writes no ring
     `input` line) sits between a delivery and a Read four real prompts later: the Read is at
     `lag_turns = 5` in the histogram, weight `0.500`. **Mutation:** the clock counts ring
     `input` lines; the Read lands at lag 4, weight `0.707`.
   - **(c)** `censored` counts a unit delivered in the session's last prompt (fewer than `k`
     later prompts).
   - **(d)** Through the pure function: `tool_used_weight(lag, k=3, h=2)` for lag 0 to 9
     equals the table `1, 1, 1, 1, 0.707, 0.5, 0.354, 0.25, 0.177, 0.125` (to 3 decimals).

   **RED at HEAD:** no block, no kernel.
7. **AC-6 (R5, D7): the unit.** (a) scan-prompt delivers three anchors of `F` in prompt 1, then
   one Read of `F`: `units=1`, `anchors_in_units=3`, `used_tool=1`. (b) `F` delivered by
   scan-prompt in prompts 1 and 2, one Read in prompt 2: per-unit `1/2`, distinct `1/1`. (c)
   `F` delivered in prompt 3 by both scan_prompt and prompt_recall, then a Read: both channels
   credited, and the `any channel` row counts the file once. (d) Two Reads after one delivery:
   credited once. (e) One Bash touching delivered `F` and `G`: two units credited. **RED at
   HEAD:** no block. {#ac-6}
8. **AC-7 (R3, D15): each matcher leg, positive and negative.** {#ac-7}
   - Through the real hook: a Grep with `path=F` is credited; a Grep whose pattern is
     `used_events|other` is credited for the delivered name `used_events`; a Grep for `run`
     against a delivered name `run` is NOT credited (`_matchable`); Glob `**/telemetry.py` is
     credited for `src/refmatrix/telemetry.py` and Glob `**/*.py` is not; Bash `sed -n 1,40p
     src/x.py` with `cwd` = the project dir is credited `bash_path`; Bash `rmx context S` is
     counted in `skipped_explicit_tool_calls` and credits nothing; a Read of a memory's source
     file is credited for that memory.
   - **The base directory (r2 b-1), each with `cwd` = the project dir, `src/x.py` delivered:**
     - `cd <other-dir> && sed -n 1,40p src/x.py` is NOT credited and counts
       `refs_outside_project=1` (the negative case r2 prescribes; `<other-dir>` is a tmp dir
       holding its own `src/x.py`);
     - `pushd <other-dir> && cat src/x.py` and `git -C <other-dir> diff src/x.py`: not
       credited, each counted;
     - `cd <other-dir> && grep -n x_symbol *.py` for a delivered name `x_symbol`: NOT credited
       (`bash_names_outside_project=1`);
     - `cd <other-dir> && cat <project>/src/x.py` (absolute project path): credited
       `bash_path`;
     - `cd <other-dir> && cd <project> && cat src/x.py`: credited (the later `cd` wins);
     - `cd "$D" && cat src/x.py`: not credited, `bash_base_unknown=1`;
     - a Grep with `path=<other-dir>` and pattern `x_symbol`: not credited, counted.
   - **Git lines (r2 s-1).** A `git commit -m "touch x_symbol"` run in a tmp repo OUTSIDE the
     project, whose diffstat names `src/x.py`, credits nothing by path (the diffstat is never
     matched); the same commit run in the project credits `x_symbol` by `bash_name`.
   - **Uncapped paths (r2 m-4).** A Bash command naming ten paths, the delivered one tenth,
     is credited `bash_path` (the shell `refs` would have kept only eight).
   - Unit legs, labelled as such, because their producer is 24.6 R4 ([[#d6]]):
     `tool_touches("Agent", {"prompt": …}, cwd)` matches a delivered memory's name;
     `tool_touches("mcp__refmatrix__rmx_context", …)` is `explicit`;
     `tool_touches("mcp__refmatrix__rmx_grep", {"pattern": "x_symbol"}, cwd)` matches under
     `mcp_name` and is not `explicit` (r2 m-5). The end-to-end test of these is 24.6 r7 AC-3.
   - **Legacy parity (r2 m-8).** `ring_tool_call` on a legacy line (no `tool`, `detail` only)
     gives the same `ToolTouches.match` result as on an R1 line for the same call, for three
     calls: a positive pair (a delivered path and name, both matched), a zero-match pair (no
     delivered path or name), and a command over 600 characters whose delivered path sits past
     character 600 and is its ninth path (so neither the cut `detail` nor the 8 `refs` hold it:
     the legacy line misses it, counted `detail_truncated=1` and `refs_capped=1`; the R1 line
     matches it). Parity is asserted where it holds, and the gap is counted where it does not.

   **RED at HEAD:** no matcher.
9. **AC-8 (R6): explicit uses go to the delivering channel.** scan-prompt delivers `S`, then
   `rmx context S` (agent) emits R12's `context_by_name`. The report counts it under
   `scan_prompt used_explicit context_by_name=1`, not under `context`. A `used` event whose
   `ref_query_id` matches no delivered event in the window is counted `explicit_ref_unresolved`.
   **RED at HEAD:** the report lists it as `events context used: 1`. {#ac-8}
10. **AC-9 (R9, R10): every count has an exact value, and the identity is not tautological (s-7;
    r2 s-2, s-4).** {#ac-9}
    - **One fixture, every count.** The fixture is built from the elements below, real
      producers unless marked (hw = hand-written). Every R9 count is printed and asserted at the
      exact value in the last column, so a count hard-wired to 0, or fed by the wrong element,
      fails. Counts not listed here are asserted 0 in this fixture and are given non-zero exact
      values by the AC named.

    | count | fixture element | value |
    |---|---|---|
    | `no_session` | a delivered event with `session: null` (hw) | 1 |
    | `no_ring` | a delivered event whose session has no ring file (hw) | 1 |
    | `precompact_gated` | a `precompact` delivery (hw) | 1 |
    | `eligible` | every other delivered event of the fixture | their number, counted at admission |
    | `path_from_catalog` | a pre-task event (no `path` key, hw) whose `entity_id` is in the tmp project catalog; and a pre-task `scope = global` event (hw) whose `entity_id` names a memory in the tmp GLOBAL catalog and ALSO a different entity in the tmp project catalog (ids are per store, so the two stores' early ids collide): its path is the global memory's `source_path`, never the project entity's (r2 s-2) | 2 |
    | `path_unresolved` | a pre-task event (hw) whose id is in neither catalog | 1 |
    | `memory_no_source_path` | a real recall delivering a memory row with no `source_path` | 1 |
    | `no_path` | a term concept (`path: null`), the memory above, the unresolved id | 3 |
    | `path_from_name` | a pre-task grep-floor event (hw: no `entity_id`, `name` `src/x.py`, no `path` key) | 1 |
    | `prompt_unanchored` | a `scan_prompt` delivery (hw) whose `query_id` has no query.log row | 1 |
    | `prompt_rows_legacy` | one query.log prompt row without `t` (hw) | 1 |
    | `order_ambiguous` | a legacy Read line without `t` (hw) in the same second as a delivery of its file | 1 |
    | `order_from_end` | a real `tool` envelope with no `tool-pre` before it | 1 |
    | `cwd_fallback`, `refs_capped`, `detail_truncated` | ONE legacy Bash line (hw): no `cwd`, 8 `refs`, `detail` of exactly `DETAIL_MAX` | 1, 1, 1 |
    | `tool_from_terse` | the two legacy lines above (the Read and the Bash) | 2 |
    | `ring_unparseable` | a non-JSON ring line (hw) | 1 |
    | `input_truncated` | a real Bash envelope whose command is 2,500 characters | 1 |
    | `skipped_explicit_tool_calls` | a real Bash `rmx context S` | 1 |
    | `tool_events_unmatched_by_tool` | a real `rmx focus hook --event tool` envelope for `WebFetch` (the hook records what it is fed; the matcher lives in settings) | `WebFetch=1` |
    | `refs_outside_project` | a real Read of a path outside the project | 1 |
    | `bash_base_unknown` | a real Bash `cd "$D" && cat src/x.py` | 1 |
    | `bash_names_outside_project` | a real Bash `cd <other-dir> && echo x_symbol`, `x_symbol` delivered, and the `cd "$D"` call above | 2 |
    | `credited_abandoned` | a real `tool-pre` for a Read of delivered `F`, swept by the next real `input` hook | 1 |
    | `origin_unknown` | the credits of this fixture whose tool line has no `origin` (all of them; the swept Read is one) | the number of credits, asserted equal to `used_tool` |
    | `subagent_tool_events`, `origin_unattributed` | none here | 0 here; exact values in [[#ac-14]] |
    | `result_mentions_present` | none here | 0 here; exact value in [[#ac-18]] |
    | `explicit_ref_unresolved` | none here | 0 here; exact value in [[#ac-8]] |

    - The identity holds. **Mutations, each must make `rmx telemetry --agent-usage` (run through
      the real CLI entry) exit 1 with `identity-broken` on stderr (r2 m-7):** `no_ring` dropped
      from the identity; and, separately, the `no_session` branch made to `continue` without
      counting. The second proves `eligible` is counted at admission, not computed by
      subtraction. A third mutation resolves global legacy events against the project
      snapshot: the collision event's path becomes the project entity's and this AC fails.

    **RED at HEAD:** none of the counts exist.
11. **AC-10 (R7): the control.** A `retrieved`-only item (trimmed by the payload cap) whose file
    is later Read counts in the control and not in `used_tool`. A trimmed item whose file was
    DELIVERED earlier in the session (as another item) is not a control unit. The control is
    kernel-scored (D18): a control unit touched at lag 5 adds `0.500` to `control_score`, and
    `lift` is printed per channel and per kind as the difference of kernel scores, with the
    per-band control rates. **Mutation:** the control scored binary (lag ≤ 3 → 1, else 0)
    prints `0` for that unit. **RED at HEAD:** no control. {#ac-10}
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
    `recall-events.jsonl` contains a `used` event outside R12's three evidences. The flow's
    `rmx focus hook` calls run in-process (click's runner) under a recording audit hook, as
    24.6 AC-3 does with 23.0's: no `open` event names a `recall-events.jsonl`, project or
    global, during any of them (r2 m-2: size and mtime alone miss a READ). Two mutations fail
    this AC: `focus_hook` calls `emit_recall_events`, and `focus_hook` calls
    `delivered_in_session` (the read [[#d1]] and [[#r11]] rule out). This passes at HEAD by
    construction; its RED is the mutations. {#ac-13}
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
    - The window is the full delivery range (from 2026-10-20, the events file's first line),
      so the kernel's tail is measured on a long window ([[#why-data-kernel]]); the
      2026-11-10 window is printed as a second run for comparison with rev 2's numbers.
    - **A second corpus, cliquedb**, run the same way: read-only APFS clones of its store's
      files, `logical_root` = its live root's path as a string, nothing written to or opened
      under that tree (a fleet repo: [[#ofu-cliquedb]]). Its rings and events overlap from
      2026-11-04; it is the only other fleet store whose delivered events overlap its tool
      rings.
    - The output and its wall time go into the implementation summary, with R10's legacy
      counts. The clones are deleted after the run.
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
- `>` to `>=` in `tool_after_delivery`: AC-4 (d) (`(x, x)` returns `True`). AC-4 (c) cannot
  kill it: its `t_start` is strictly before the delivery (r2 m-1).
- `t_start` replaced by `t`: AC-4 (c) credits.
- The kernel's `k` 3 → 2, `k` 3 → 4, `h` 2 → 1 or 3, a step at `k`, rev 2's hard window, and a
  unit weighted by its last or summed touches: AC-5 (a), (d) (D18).
- The control scored binary: AC-10.
- The clock built from ring `input` lines: AC-5 (b) (lag 4, weight 0.707, not lag 5).
- Every older unit of the file credited: AC-6 (b) per-unit reads `2/2`.
- Credit per delivered event instead of per unit: AC-6 (a) reads `used_tool=3`.
- `prior_touch` credits counted in the headline: AC-4 (b).
- The explicit skip removed: AC-7 credits `rmx context S`, and AC-8's `used_headline`
  double-counts.
- Explicit uses attributed by their own `channel`: AC-8.
- `no_ring` dropped from the identity, and the uncounted `no_session` branch: AC-9 (exit 1,
  stderr).
- Any one AC-9 count hard-wired to 0: AC-9's table (r2 s-4).
- Global legacy events resolved against the project snapshot: AC-9's collision row (r2 s-2).
- The Bash base taken from `cwd` only (rev 2's rule): AC-7's `cd <other-dir>`, `pushd` and
  `git -C` cases credit (r2 b-1).
- Name tokens matched in every simple command: AC-7's `cd <other-dir> && grep -n x_symbol`
  case credits.
- A git line matched on its diffstat `refs`: AC-7's out-of-project commit credits (r2 s-1).
- Bash paths read from the 8 `refs`: AC-7's ten-path case misses (r2 m-4).
- Every `mcp__refmatrix__` tool skipped: AC-7's `rmx_grep` unit leg returns `explicit` (r2
  m-5).
- The park record without the builder's fields: AC-1's swept `agent:a1` line has no `origin`
  (r2 m-3).
- An inline copy of the builder in `cli.focus_hook`: AC-1 (a)-(c) (r2 m-8).
- `focus_hook` calls `delivered_in_session`: AC-13's audit hook (r2 m-2).
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
| `src/refmatrix/stm.py` | `Stm.record` stamps `t` on every event; `tool_event_fields` (moved from `cli`) with `tool`, `cwd`, `t_start`, `tool_use_id`, `origin`, `input_path` / `pattern` / `command` / `prompt` / `args`, `INPUT_FIELD_MAX`, `input_truncated`; `inflight_begin` stores the builder's fields in the park record and `inflight_sweep` writes them, with the parked `t` as `t_start` (R1, D13, D14) |
| `src/refmatrix/cli.py` | `focus_hook`'s `tool-pre`, `tool` AND git-milestone branches call `stm.tool_event_fields` with the envelope's `cwd`, `tool_use_id`, `agent_id` (the git line keeps its own `terse` and diffstat `refs`); `_tool_event_fields` removed (R1; r2 s-1). `telemetry` (`cli.py:7795`) catches `telemetry.UsageIdentityBroken`, echoes the lines, writes the `identity-broken` line to stderr and exits 1 (R9; r2 m-7) |
| `src/refmatrix/context.py` | `_item` / `bundle_items` carry `item_path`; `ITEM_META_FIELDS` gains `path` and `source_path`; `annotate_items` fills `path` and `source_path` in its one catalog query (`context.py:1781`) (R2; r2 m-6) |
| `src/refmatrix/store.py` | `Store.item_meta` selects `e.path` and the memory's `metadata->>'source_path'` (R2) |
| `src/refmatrix/hooks.py` | `FOCUS_TOOL_MATCHER` constant, used by the generator; generated output byte-identical (D6) |
| `src/refmatrix/telemetry.py` | `path` appended to `RECALL_EVENT_FIELDS_V1`; `item_path`, with relative `Entity.path` joined to the store root's parent, and `_item_fields` passing `path` (`telemetry.py:1386`) (R2; r2 m-6); `bash_segments` / `BashSegment` (D15); `tool_after_delivery` (R4; r2 m-1); `UsageIdentityBroken` (R9); `log_query` writes `t` (R13); `is_prompt_row`, `prompt_clock`, `PROMPT_PAIR_S` (R4); `tool_used_weight`, `TOOL_USED_PLATEAU_K = 3`, `TOOL_USED_HALF_LIFE_H = 2`, `TOOL_USED_SENSITIVITY_K = 4` (D18); `tool_touches`, `ToolTouches`, `ring_tool_call` (R3); `derive_tool_used(root, *, logical_root, global_root, since, until) -> ToolUsed` returning per-unit credit records (`unit`, `tool`, `match_on`, `ref_query_id`, `lag_turns`, `lag_s`, `prior_touch`, `origin`) plus the R9 counts, never written to any file; global legacy events resolved against `global_root`'s snapshot (R4-R7, R9, R10; r2 s-2); the `used by channel` block, the leg table, the reconciling line and the identity check in `agent_usage_report(..., logical_root=None)` (R8, R9, D11) |
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
4. **OD-4: one implementation of 19.6's tool-input read-back clause — APPROVED by the user,
   2026-11-13.** {#od-4}
   - 19.6's read-back definition (d9v, user-confirmed;
     [[task-19.6-phased-context-and-topic-cache#ranges]]) counted "a later tool call whose input
     names it (`file_read`)", computed by its offline transcript scorer. This task computes the
     same clause from the ring.
   - **The decision (the user approved the recommendation as written).** One decision-log row,
     d21-5a in [[plan-19-adaptive-memory-budget#decisions]]: `score_readback.py` calls
     `telemetry.tool_touches(tool_name, tool_input, cwd)` on each transcript tool call (the
     signature takes Claude Code's own input, so the scorer needs no ring); the evidence is
     named `tool` everywhere; a memory's path is its `memory_content.metadata.source_path`
     (memories have no `Entity.path`); 21.1 R12's reservation names `tool` (owned here) and
     `cited_in_answer` (still 19.6's, transcript-only). The definition's wording does not
     change beyond the evidence's name; its source and owner do. The rename is applied in the
     same change to 19.6's read-back paragraph, 21.1 R12's reservation and 19.2 R1's mention.
   - **The kernel does not reach 19.6.** 19.6's clause is "later in the same session", with no
     window; it calls the matcher, not [[#d18]]'s weight. The kernel scores this task's report
     only.
5. **OD-5: the window and R12's numbers — DECIDED by the user, 2026-11-13.** {#od-5}
   - R12's other numbers are CONFIRMED as written: the 21 / 42-day source window, the
     report-only default under 50 main-loop pairs, the Wilson bounds, the 20-pair stratum
     minimum and the 10% subagent ceiling.
   - `W = 2` is REPLACED by a decay kernel: "why don't we use a sliding score that gradually
     decays instead of using a hard boundary", then "i would think 3 or 4 would be better to
     begin the decay". The lead drew the shape from those sentences ([[#d18]]): a plateau of
     weight 1 to `k = 3`, then a half-life of `h = 2` prompts, no cutoff, raw lag stored, a
     `k = 4` sensitivity row, the control scored by the same kernel, and R12's sample
     stratified by lag band 0 / 1-3 / 4-6 / 7+. What about it the user should still see is
     [[#kernel-for-user]].

**Spec-settled here (lead decisions, made as the user would), not needing the user:** keeping
`v: 1` ([[#d3]]); the Agent / mcp legs ([[#d6]]); the credit unit ([[#d7]]); the headline
([[#d8]]); the prompt definition ([[#d9]]); `result_mentions` ([[#d10]]); the logical root
([[#d11]]); paths outside the project ([[#d12]]); `origin` ([[#d13]]); abandoned calls and
their park fields ([[#d14]]); the Bash base directory and the name leg under it ([[#d15]]);
the precision population ([[#d16]]); the MCP legs ([[#d17]]); the `tool_result` leg's task
row ([[#d10]]); the kernel's shape within the user's OD-5 words ([[#d18]]); the control ([[#r7]]); the explicit-call skip ([[#r3]]); attribution by
`ref_query_id` ([[#r6]]); no new verb ([[#d5]]). {#spec-settled}

## Open for the user {#open-for-user}

OD-4 and OD-5 were decided by the user on 2026-11-13 ([[#od-4]], [[#od-5]]); their entries
stay below as a record. One item still needs the user, and the kernel's shape has points the
user should see before AC-15's output is read.

1. **OD-4: APPROVED (2026-11-13).** The decision-log row is d21-5a. {#ofu-od4}
2. **OD-5: DECIDED (2026-11-13).** The kernel replaces `W = 2` ([[#d18]]); R12's other numbers
   are confirmed. {#ofu-od5}
3. **A second corpus reads a fleet repo's store (AC-15).** cliquedb's `.refmatrix/` files are
   copied read-only (APFS clones, deleted after) so the kernel's tail is checked on a store
   whose work does not run in clones. The project's rules say an agent never touches a fleet
   repo; a read-only copy writes nothing there, and the lead already ran one, but the
   implementer needs the user's yes, or AC-15 runs on this project alone.
   **Recommendation: allow it, read-only, counts only.** {#ofu-cliquedb}
4. **What the user should see about the kernel (not blocking; lead-drawn from the user's
   words).** {#kernel-for-user}
   - **The plateau is not yet above the control.** On 2026-10-20 to 2026-11-13, lags 1-3
     credit 1.8 per 1,000 units against the control's 2.3; only lag 0 is clearly above it
     (3.1 against 0.8). The plateau gives lags 1-3 full weight, 15.0 of the 52.5 score
     ([[#why-data-kernel]]). R12's 1-3 band, labelled, tests it; if it is indistinguishable
     from the control there, R12's band rule revises `k`.
   - **The tail is most credits and little score.** Lag 6+ is 60% of headline credits; the
     kernel gives 7+ only 2.9 of 52.5. Its per-unit rate is close to the control's.
   - **`k = 3` was the lead's pick** within "3 or 4"; `k = 4` is printed beside it (57.3
     against 52.5 on the long window).
   - **R12's pooled precision is now kernel-weighted** (`p_w`, with a Kish effective sample
     size), so 19.2's weight matches what its column would count (`Σ w`). The pooled band
     thresholds (0.80 / 0.65 / 0.50) are unchanged.
   - **"Indistinguishable from control" compares per-unit credit RATES**, the band's against
     the control's, not precision against a rate: the two are different quantities, and only
     rates exist for the control (it has no labels).
   - **An explicit R12 use weighs 1** at any lag: it names the item, so it is not inferred
     from proximity.

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

## Revision 3 (2026-11-13, ch-bsd spec r2) {#rev-3}

rel: derives-from -> [[bsd-task-21.5-spec-r2-540ab50]]
rel: amends -> [[task-24.6-context-and-observation#rev-r7]]

Every r2 finding, with where it is closed, then the user's two decisions of 2026-11-13. Lead
decisions, made as the user would, are marked (lead).

| finding | disposition | where |
|---|---|---|
| b-1 the Bash `cwd` fallback re-opens the clone leg | the base directory comes from the command: `cd` / `pushd` carry forward, `git -C` per simple command, unresolvable bases unknown; a relative ref on a base outside the project counts `refs_outside_project` and never matches; name tokens match only in simple commands based in the project (lead: the name leg too, and Grep / Glob by their `path`); AC-7's negative cases, including r2's `cd <other-dir> && sed -n 1,40p src/x.py`; `#why-data` re-run under the fix: credits 64 → 35, prior-touch 46 → 17, headline 18 → 18 with 8 units exchanged | [[#d15]], [[#d11]], [[#d12]], [[#r3]], [[#ac-7]], [[#why-data]] |
| s-1 git lines get no R1 fields and match on a diffstat | the git branch calls the builder (keeps its `terse` and diffstat `refs`); git lines match on `command` only, never `refs`; legacy git lines on `detail`; AC-1 git case, AC-7 out-of-project commit; 24.6 r7 R4 | [[#r1]], [[#r3]], [[#r10]], [[#ac-1]], [[#ac-7]] |
| s-2 global legacy events resolved against the project snapshot | resolved against the global store's snapshot (`global_root`); re-run: 5 of 5 ids found there, 0 in the project's; AC-9 collision row and mutation | [[#r10]], [[#ac-9]] |
| s-3 prior-touch credits in the precision sample | the banded sample is drawn from headline credits, the population a consumer counts; prior-touch is a report-only stratum of up to 20 pairs (lead) | [[#d16]], [[#r12]] |
| s-4 8 of 23 R9 counts have no fixture | AC-9 is a table: every R9 count with its fixture element and exact value, the rest asserted 0 and valued by the AC named; a hard-wired-0 mutation | [[#ac-9]], [[#mutations]] |
| s-5 the `tool_result` leg defers to a task that does not exist | task 21.6 filed with acceptance criteria as a plan-21 task row and a deferral-registry row (`inert-sentinel`, trigger 24.6 R4) | [[#d10]]; [[plan-21-agent-context-usage#tasks]]; [[deferral_registry#registry]] |
| m-1 AC-4 (c) cannot kill `>` → `>=` | ONE ordering function `tool_after_delivery`; AC-4 (d) tests equality through it; the mutation line now names AC-4 (d) | [[#r4]], [[#ac-4]], [[#mutations]] |
| m-2 AC-13 misses a read in `focus_hook` | recording audit hook over the in-process hook calls: no open of any `recall-events.jsonl`; a `delivered_in_session` mutation | [[#ac-13]] |
| m-3 swept events lack the builder's fields | the park record stores the builder's fields; the sweep writes them, `origin` included; aligned with 19.0 R2's park fields; 24.6 r7 R4 | [[#d14]], [[#r1]], [[#ac-1]] |
| m-4 Bash leg reads `refs`, capped at 8 uncounted | `tool_touches` extracts paths from the whole `command`, no count cap; legacy lines use `detail` plus the `refs`, a capped line counted `refs_capped`; AC-7 ten-path case | [[#r3]], [[#r9]], [[#ac-7]] |
| m-5 every `mcp__refmatrix__*` tool skipped | only R12's three are explicit; the others match under `mcp_name` on `args` (lead); unit leg in AC-7; 24.6 r7 AC-3 | [[#d17]], [[#r1]], [[#r3]], [[#ac-7]] |
| m-6 R2 plumbing unlisted; relative `Entity.path` | `annotate_items` and `_item_fields` named and listed; relative paths joined to the store root's parent; AC-2 case | [[#r2]], [[#ac-2]], [[#files-to-modify]] |
| m-7 "exits 1" has no exit path | `UsageIdentityBroken` raised by the report, caught by `cli.telemetry`, stderr + exit 1; `cli.py` row; AC-9 runs the mutations through the CLI | [[#r9]], [[#files-to-modify]], [[#ac-9]] |
| m-8 AC text gaps | hand-written lines enumerated per AC with the reason; `any channel` row defined in R8; AC-2 `/tmp`-spelled root; AC-7 parity with positive, zero-match and >600-character cases; AC-1 one-builder test by field equality, a pass-through spy and an AST scan | [[#ac-producers]], [[#r8]], [[#ac-2]], [[#ac-7]], [[#ac-1]] |
| imp-ruled-out-leg-returns-via-fallback | D12's exclusion now stated for every leg that resolves a path (Read, Bash, Grep, Glob) | [[#d12]], [[#d15]] |
| imp-printed-count-needs-a-fixture | as s-4 | [[#ac-9]] |
| OD-4 (user, 2026-11-13: approved as recommended) | decision-log row d21-5a in plan-19's log; `file_read` renamed `tool` in 19.6's read-back paragraph, 21.1 R12's reservation and 19.2 R1; 19.6's scorer calls `tool_touches`; the kernel does not reach 19.6 | [[#od-4]]; [[plan-19-adaptive-memory-budget#decisions]] |
| OD-5 (user, 2026-11-13: R12's numbers confirmed; `W = 2` replaced by a sliding, decaying score, decay starting at 3 or 4) | a USER decision with a LEAD-DRAWN shape: `w = 1` to `k = 3`, then `2^(-(lag−k)/h)`, `h = 2`, no cutoff, raw lag stored, unit weight = max over touches, explicit uses weigh 1, kernel-weighted headline with binary `used_lag0` / `used_le2`, the histogram and a `k = 4` sensitivity row beside it; control kernel-scored, lift on kernel scores; R12 drawn by lag band 0 / 1-3 / 4-6 / 7+ with Wilson per band and an `indistinguishable from control` line; pooled precision kernel-weighted. Consumers restated: 19.2's column counts `Σ w` at `w_tool = round(2 × p_w, 1)` (D4); 19.6 untouched (OD-4); AC-3, AC-5, AC-10 and the mutations (`k` 3 → 2 / 4, `h`, a step at `k`, the hard window). `#why-data-kernel` re-run uncapped on two windows; cliquedb from the lead's run | [[#d18]], [[#d4]], [[#d8]], [[#r4]], [[#r5]], [[#r7]], [[#r8]], [[#r12]], [[#ac-5]], [[#ac-10]], [[#ac-15]], [[#mutations]], [[#why-data-kernel]], [[#kernel-for-user]] |

**Re-run.** `#why-data` was re-run on fresh read-only APFS clones, counts only; rev 2's rules on
the same clones reproduce r2's re-derivation exactly (64 / 46 / 18), so every before → after in
the table is a rule change, not a data change. The 21.6 rows were filed in the same change
as this revision. The kernel re-run used fresh read-only clones too, deleted after.
{#rev-3-note}
