---
gmd: "0.1"
id: task-U1-use-observations
title: "Task U1: use observations, recorded only: the recall-event log gains the cue, the item's path and a held-out arm, with outcomes classified by a read-only report"
tags: [task, u1, used-signal, telemetry, recall-events, held-out, scan-prompt, prompt-recall]
metadata:
  node_type: task
  status: approved
  created: 2026-11-25
  author: ch-architect (Fable 5.2)
---

# Task U1: use observations, recorded only {#root}

> Status: written 2026-11-25 for queue row U1 (Q83 = a, L250); the lead approves. **Large**
> (the scan-prompt and prompt-recall payloads are hook output, a shared path): RED and GREEN
> in separate hands, mutations, one ch-bsd pass. The writer waits on nothing; the report's
> unit section and its context windows read [[task-I1.b2-marker-and-ledger]]. It edits
> `cli.py` and `verbs.py` thinly, so it merges before queue row 4's sha or after 29.5
> ([[plan-of-plans#queue-quiet]]). Nothing in retrieval reads what it records.

rel: implements -> [[plan-of-plans#queue]]
rel: derives-from -> [[measurement-task-21.5-usage-weight-2026-11-13#verdict]]
rel: derives-from -> [[measurement-task-21.5-r12-pilot-2026-11-13#matcher-changes]]
rel: depends-on -> [[task-21.1-context-usage-telemetry#req-schema]]
rel: depends-on -> [[task-21.5-tool-used-signal#decision-no-build]]
rel: depends-on -> [[task-I1.b2-marker-and-ledger#d7]]
rel: related-to -> [[plan-28-handhold-outcome-experiment]]
rel: reinforces -> [[feedback_no_raw_prompts_in_public_repo]]

## Goal {#goal}

The 2026-11-13 measurement could not fit a usage weight because the evidence was 93 used
units, with 3 in a control that was biased low (trimmed items rank lower). U1 starts the
record that fit needs: for every item an injection surface delivers, what cued it; for a
random share, that it was withheld; and afterwards, read from the session's own events, what
happened. It changes no ranking and writes no weight. {#goal-body}

## What is built {#design}

- **D1 The record is `recall-events.jsonl`, extended.** It is already one append-only event
  per item per call, with session, turn, channel, item id, kind and rank, written by one
  writer, and it has carried an unused `arm` and `policy` since 21.1. A second per-item file
  would write each delivery twice. The I1 units' deliveries stay in the instruction ledger
  ([[task-I1.b2-marker-and-ledger#d7]]), which already holds one row each; the report reads
  both. {#d1}
- **D2 Three additive fields, `v` stays 1** ([[task-21.5-tool-used-signal#d3]]'s rule, and its
  `path` field built as written there): `cue`, at most 16 concept ids of the prompt terms that
  retrieved the item (scan-prompt) or passed the prompt gate (prompt recall); `cue_n`, how
  many there were; `path`. No prompt text, term text or hash of a single term is stored; a
  term with no concept is counted in `cue_n` and dropped. {#d2}
- **D2b The activity mode, as counts** (Q87 = a, L253). Each row also carries `mode`: the
  counts of tool types over the session's last 20 ring events before the call, in fixed
  buckets (`read`, `search` (Grep, Glob, `rmx context`/`grep`, MCP reads), `edit` (Edit,
  Write, MultiEdit, NotebookEdit), `bash`, `test` (a Bash command the test-to-file hook
  classes as a test), `agent` (Agent, SendMessage), `other`) and `mode_n`, the events read.
  Read from the ring tail the hook already opens; no text, no path, no classification at
  hook time: clustering is M4's and the report's. {#d2b}
- **D3 A held-out arm, on the two prompt channels only.** A new stage, `held_out`: the item
  was retrieved, ranked and fitted into the budget, then left out of the payload. Nothing
  takes its place. Delivered and held-out rows of a hook-invoked `scan_prompt` or
  `prompt_recall` call carry `arm` (`delivered`, `held-out`) and `policy`
  (`holdout-v1@<rate>`); every other row keeps `fixed`. {#d3}
- **D4 Who can be held out.** An item with a path or a body the agent could fetch: doc, code,
  subject, and memory. Never: a `feedback` or `guardrail` memory (until I1.h such a memory is
  a rule's only delivery); a term concept (the pilot found no evidence route for one); any
  call an agent made itself (`rmx context`, MCP recall); `session_start`, `precompact`, the
  handoff; any I1 unit (a rule is never withheld). {#d4}
- **D5 The choice is a hash, sticky for the session.** An eligible item is held out when a
  hash of (store salt, session, item key) falls under the rate. So one item is withheld
  every time it is retrieved in that session, no hook reads back what it delivered earlier
  ([[task-21.5-tool-used-signal#d1]]), and a test needs no patched randomness. {#d5}
- **D6 The rate is a setting in one store, off until the user sets it.** One number in
  `<store>/use-holdout.rate`, like the injection capture's mode file; absent means 0. At 0
  the payload is byte-identical to today's and the new fields are still recorded. {#d6}
- **D7 Nothing is withheld that will not be recorded.** With telemetry off, or the event
  file not appendable when the call starts, no item is held out and one stderr line says so.
  A row that still fails to write after an item was withheld is said on stderr with the
  count. {#d7}
- **D8 Outcomes are a report's, never a hook's.** `rmx telemetry --use` reads the events,
  the explicit `used` events 21.1 already writes, and the session's STM ring, and writes
  nothing. Per row it gives one class with an evidence reference: {#d8}

  | Class | Rule |
  |---|---|
  | `already-held` | the same key was delivered earlier in this context (since the last compaction marker), or its file was touched before the delivery |
  | `caused` | an explicit `used` event that references this delivery, and the item's own name was not in the cue |
  | `informed` | a later main-loop Read, Edit or Write of the item's `path`, or an explicit use where the cue named the item |
  | `ignored` | none of these before the session ends |

  The same rules run on held-out rows, where a positive means "touched anyway". The report
  prints, per channel, kind and arm, the counts and the difference in positive rate with its
  interval. It applies the pilot's corrections that the ring allows today: no name leg, no
  term concepts, file tools only. A row it cannot class is counted with its reason. {#d8-rules}
- **D9 Size.** The log has no reap today: 73.6 MB after 36 days, about 1,000 B a row. U1 adds
  held-out rows (at most the rate times the eligible deliveries) and under 150 B a row for
  the new fields. The report prints the file's size and its growth over the last seven days.
  {#d9}

## Acceptance criteria {#acceptance}

Through the generated hook commands for scan-prompt and prompt recall (`/bin/bash -c`, the
envelope on stdin) on a sandbox daemon with seeded items, and through `rmx telemetry --use`.
The event-schema cases extend `tests/test_task21_1_emitters.py`; the arm and the report are a
new feature, one new file, `tests/test_use_observations.py`. {#acceptance-lead}

- **AC-1 Rate 0 changes no payload.** With no rate file, each channel's payload equals the
  base payload byte for byte and no `held_out` row is written; each delivered row carries
  `cue`, `cue_n`, `path` where the item has one, `arm: delivered` and
  `policy: holdout-v1@0`. `test_use_observations.py::test_rate_zero[channel]`. {#ac-1}
- **AC-2 Only what may be withheld is.** At rate 1, on a fixture holding a doc, a code item,
  a `project_` memory, a `feedback_` memory and a term concept: the payload has no span for
  the first three, and each has one `held_out` row with its rank, cue and path and no offset;
  the other two are delivered. `…::test_holdout_eligibility[channel]`. {#ac-2}
- **AC-3 Sticky, and the rate is the rate.** At rate 0.5: two calls of one session withhold
  the same items; over 400 seeded items the withheld share is between 0.4 and 0.6; a second
  session withholds a different set. `…::test_holdout_is_sticky_and_proportional`. {#ac-3}
- **AC-4 Nothing takes the place.** At rate 1 the payload is the base payload minus the
  withheld spans: no item appears that the base call did not deliver.
  `…::test_no_backfill[channel]`. {#ac-4}
- **AC-5 Not recorded, not withheld.** With `REFMATRIX_NO_TELEMETRY` set, and with the event
  file's directory read-only, a rate-1 call delivers everything, prints one stderr line and
  exits as the base call does. `…::test_no_holdout_without_a_record[case]`. {#ac-5}
- **AC-6 A call the agent made is never thinned.** `rmx context <name>` and the MCP recall
  at rate 1 deliver everything and their rows keep `arm: fixed`.
  `…::test_pull_calls_keep_everything[route]`. {#ac-6}
- **AC-7 The cue is ids, capped, and holds no text.** A prompt with 40 gate terms, 5 of them
  unknown to the store: `cue` has at most 16 ids, `cue_n` is 40, and no term of the prompt
  appears anywhere in the event file. `…::test_cue_is_bounded_and_textless[channel]`. {#ac-7}
- **AC-7b The mode is counts only.** A fixture session whose ring tail holds 5 Reads, 3
  Edits, 2 test runs and 1 Agent call: the next delivered and held-out rows carry those
  counts in their buckets and `mode_n` 11; with an empty ring, every bucket is 0 and
  `mode_n` is 0; no path or command text appears in the event file.
  `…::test_mode_is_textless_counts[channel]`. {#ac-7b}
- **AC-8 The schema's readers do not move.** `v` is 1; `row_provenance` classes a `held_out`
  row `attributed`; `rmx telemetry --agent-usage` prints the same counts with and without
  `held_out` rows in the file. `tests/test_task21_1_emitters.py`,
  `tests/test_task21_1_agent_usage_report.py`. {#ac-8}
- **AC-9 Each class, from real session events.** A fixture session written by the real hooks:
  a delivered memory then `rmx memory get` of it → `caused`; a delivered doc then a Read of
  its path two turns later → `informed`; a delivered doc never touched → `ignored`; an item
  delivered twice in one context → the second `already-held`; a held-out doc that is Read
  later → `informed` in the held-out arm. `--json` gives each positive its evidence
  reference. `…::test_report_classes[case]`. {#ac-9}
- **AC-10 The report is honest and read-only.** An unparseable line is counted; a row whose
  session has no ring is `unclassified: no ring`; a term concept is `unclassified: no
  evidence route`; the sizes and mtimes of every file under the store are unchanged by the
  run. `…::test_report_edges[case]`. {#ac-10}
- **AC-11 Units are listed, not judged here.** With an instruction ledger holding `injected`
  and `gated` rows, the report lists them per unit as delivered observations and names the
  context review as their outcome's owner; with no ledger it prints `not measured` and the
  task. `…::test_report_units[case]`. {#ac-11}
- **AC-12 Busy changes nothing.** Beside C2's held writer, a rate-1 call returns inside its
  existing `--timeout`; when the base call would print no payload, nothing is held out and
  no row is written. `…::test_holdout_beside_a_held_writer[channel]`. {#ac-12}
- **AC-13 Measured on the real catalog before it is enabled.** On a copy of the live
  catalog, 100 hook-form calls per channel with and without the new fields: the added p95 is
  at most 20 ms (a band written here; over it the prompt-recall cue is cut to the ids the
  call already holds). The summary states the row size before and after. {#ac-13}
- **AC-14 The size is said.** `rmx telemetry --use` prints the log's bytes and its seven-day
  growth. `…::test_report_prints_size`. {#ac-14}

## Mutations {#mutations}

| # | Mutation | Must fail |
|---|---|---|
| M1 | the selection ignores the rate file (an item is held out at rate 0) | AC-1 |
| M2 | a `feedback` memory is eligible | AC-2 |
| M3 | a term concept is eligible | AC-2 |
| M4 | an item is withheld and its `held_out` row is not written | AC-2 |
| M4b | `mode` counts the whole ring, not its last 20 events (or drops the `test` bucket) | AC-7b |
| M5 | the hash is keyed on the call, not the session | AC-3 |
| M6 | the next-ranked item fills the freed budget | AC-4 |
| M7 | the arm runs with telemetry off | AC-5 |
| M8 | the arm runs on an agent or MCP call | AC-6 |
| M9 | `cue` is not capped | AC-7 |
| M10 | a prompt term is written as text | AC-7 |
| M11 | `v` becomes 2 | AC-8 |
| M12 | a held-out row's later touch is counted in the delivered arm | AC-9 |
| M13 | an earlier delivery in the same context is not seen | AC-9 |
| M14 | an unparseable line is skipped uncounted | AC-10 |
| M15 | the report writes a file | AC-10 |

## Files {#files}

| File | Change |
|---|---|
| a new module beside `telemetry.py` | the policy, the eligibility rule, the hash, the report |
| `src/refmatrix/telemetry.py` | the stage, the three fields, `arm` and `policy` in `call_events` |
| `src/refmatrix/scan.py`, `recall_pack.py`, `cli.py`, `verbs.py` | the two producers leave the chosen items out and pass the cue; the `--use` flag |
| `tests/test_use_observations.py` (new), `test_task21_1_emitters.py`, `test_task21_1_agent_usage_report.py`, `test_docs_generated.py`'s inputs | the ACs |
| [[task-21.1-context-usage-telemetry#req-schema]] | the field table gains the stage and the three fields, in the same commit |

## Risks (self-audit) {#risks}

1. **Real:** AC-13 is the run on a copy of the live catalog; after the deploy the lead runs
   `rmx telemetry --use` on the dev store at rate 0 and pastes it.
2. **Wiring:** every AC fires the generated hook command or the CLI; the selection function
   is called directly only in addition.
3. **Census:** every caller of the event writer (seven by `grep`: three in `cli.py`, four in
   `verbs.py`; only the hook-invoked scan-prompt and recall calls change); the readers of
   `arm`, `policy` and `stage`
   (the agent-usage report, `delivered_in_session`, 19.2's frozen fold); both outputs of the
   report. 31.5's capture records the same calls per block: a rate above 0 changes what it
   captures, so the day the rate is set is a regime mark in its record.
4. **Bound:** the choice is one hash per eligible item; the rows ride the call's one write;
   the cue lookup is one read on the snapshot the call already holds, inside the command's
   existing `--timeout`. The report is bounded by the files it reads and prints what it
   capped.
5. **Busy / down:** AC-12, on a real held writer; with no daemon the producers already print
   nothing, so nothing is held out.
6. **Guard:** D7's two branches and D4's exclusions are each reached by a real state (a
   read-only directory, a fixture memory of each type), never a patched value.
7. **Loud:** D7's stderr lines; the report counts what it could not read or class. A
   withheld item is otherwise invisible to the session by design, which is why the rate is
   the user's.
8. **Handoff:** the outcome of a unit delivery → I1.i's review. Any weight, demotion or
   `useful_for` edge derived from this record → plan-28's report and 21.5 phase B
   ([[task-21.5-tool-used-signal#decision-no-build]]). The fuller matcher (Bash paths, the
   origin of a touch) → 21.5 phase B; the report's classes are re-run when it lands, since
   the events are kept.

## Open decisions {#open}

**Answered:** Q85 = a (10%, dev store only, set after 31.5's 400 prompts), Q86 = a (keep everything; rotation at 1 GiB); L252, 2026-11-25. {#answered}

1. **The held-out rate, and where it runs.** Measured on a copy of the dev store's log, the
   last 14 days: 519 prompts, 13,900 items delivered by the two channels, 3,998 of them
   eligible under D4 (about 2,000 a week, 7.7 a prompt). Used items were about 1% of
   deliveries on 2026-11-13; the weeks below assume 1% to 5% of eligible items are touched.

   | Rate | Withheld per week | Per prompt | Prompts losing an item | Weeks to 100 touched-anyway events |
   |---|---|---|---|---|
   | 5% | 100 | 0.4 | 33% | 20 to 100 |
   | 10% | 200 | 0.8 | 56% | 10 to 50 |
   | 20% | 400 | 1.5 | 82% | 5 to 25 |

   Recommended: 10%, in the dev store only, set after 31.5's capture has its 400 prompts. It
   gives a control in a quarter to a year without thinning most prompts twice. The
   alternatives are 5% (half the cost, twice as long) and 0 (record the cue and path only;
   no control, which is what made the last fit impossible).
2. **Retention.** The log grows about 2 MB a day in the dev store and nothing reaps it; U1's
   evidence is only useful if it is kept. Recommended: keep everything, print the size (D9),
   and decide rotation when it passes 1 GiB. The alternative is a monthly compressed archive
   built now, which changes every reader of a window longer than a month.
