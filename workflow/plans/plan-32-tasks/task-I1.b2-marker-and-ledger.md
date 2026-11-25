---
gmd: "0.1"
id: task-I1.b2-marker-and-ledger
title: "Task I1.b2: the compaction marker (10.3 with five deltas), the instruction ledger on a shared helper, the loaded writer, and the instructions view"
tags: [task, plan-32, instructions, hooks, stm, compaction, ledger, telemetry]
metadata:
  node_type: task
  status: drafting
  plan: plan-32-instruction-architecture
  created: 2026-11-24
  author: ch-architect (Fable 5.2)
---

# Task I1.b2: marker and ledger {#root}

> Status: drafted for the spec window (L232); the lead approves. Part of queue row I1.b
> ([[task-I1.b-substrate#split]]). **Large** (hook output is a shared path): RED and GREEN in
> separate hands, mutations, one ch-bsd pass. RED bases on `master` after C2 merges. Its
> entries reach a live tree only at install window 1 ([[task-I1.b-substrate#c-flag]]).

rel: implements -> [[refmatrix/adr-0007-instruction-architecture#once]]
rel: implements -> [[refmatrix/adr-0007-instruction-architecture#ledger]]
rel: implements -> [[refmatrix/adr-0007-instruction-architecture#ledger-row]]
rel: implements -> [[refmatrix/adr-0007-instruction-architecture#ledger-writers]]
rel: amends -> [[task-10.3-plan-10-injection-dedup]]
rel: part-of -> [[task-I1.b-substrate]]
rel: depends-on -> [[task-compaction-as-handoff]]

## Goal {#goal}

Give the dispatcher the two things it stands on: a per-context "the window was emptied here"
marker, so an injected rule is delivered again after compaction; and a ledger that records
every delivery, so "was it delivered" is a row and not a belief. {#goal-body}

## The marker: 10.3's contract, except these deltas {#deltas}

[[task-10.3-plan-10-injection-dedup#requirements]] R1 to R4, its decisions f1 to f5 and its
AC-1 to AC-6 hold, with these changes. {#deltas-lead}

- **D1 Two own entries, one command.** `rmx focus hook --event compact-marker` is generated as
  its own PreCompact entry **and** its own SessionStart entry (matcher `compact|clear`). The
  dispatch inside `--event session-start` is not built: 10.3 R4 exits non-zero on a failed
  write, a failing SessionStart command loses its stdout, and that entry's stdout is the
  pointer-error surfacing ([[plan-of-plans#queue-stale]]). The command reads `source` from its
  envelope and writes nothing for any other event. {#d1}
- **D2 Silent on stdout, exit 1 on failure.** C1 made every PreCompact stdout byte a summary
  instruction, so the entry prints nothing there. A failed write is one `Error:` line on
  stderr and exit 1, never 2 (bug-308). {#d2}
- **D3 One marker per context.** A subagent's envelope carries the lead's `session_id` and its
  own `agent_id` (bug-307). Its compaction writes `marker.<agent_id>.json`, never the
  session's; `stm.last_marker(root, session, agent_id=None)` reads the matching file. {#d3}
- **D4 The tests extend `tests/test_hook_wiring.py`**, not the task-named file 10.3 lists
  (`CLAUDE.md` `#test-discipline` rule 1). {#d4}
- **D5 One reader today.** The readers 10.3 names (10.2, 10.4, 10.6, 25.1b, 25.3) are
  unbuilt; the first is the once-ledger of [[task-I1.b3-dispatcher#d5]]. "25.1b ships in the
  same window" no longer applies. {#d5}

## The ledger {#ledger}

- **D6 One helper, two ledgers.** A new module holds append (one JSON line), reap (rows older
  than a keep time) and read (with an unreadable-line count). `handoff._record_event`, the row
  leg of `reap_handoffs` and `handoff_events` call it; the handoff ledger's behaviour does not
  change. {#d6}
- **D7 `<store>/instructions/ledger.jsonl`.** Row keys: `v`, `ts`, `session`, `agent_id`,
  `agent_type`, `event`, `tool`, `unit`, `unit_sha`, `type`, `outcome`, `bytes`, `cause`. No
  prompt, command or path text: a file that is not a unit is `file:<sha256 of its path>`.
  Rows are kept 90 days; the reap runs at most once a day, on an append; the clock has a test
  knob. A project with no store writes no row and that is not an error
  ([[refmatrix/adr-0007-instruction-architecture#consequences]]). {#d7}
- **D8 The `loaded` writer.** A generated `InstructionsLoaded` entry, `rmx rules loaded`
  (hook plumbing, `verbs.INTERNAL_CLI`), appends one `loaded` row per load: the unit id or
  file hash, `type` from `memory_type`, `cause` from `load_reason`, `bytes` from the file,
  `agent_id` when the envelope has one (P3 says whether it does). {#d8}
- **D9 The view.** `rmx telemetry --context` gains `instructions`, in text and JSON: per unit
  and per agent type, the count by outcome, the bytes and the last use, and the unreadable
  lines. A file hash that matches a known instruction file (`CLAUDE.md`, a nested one, a
  rule, the user-level files) is shown by name. {#d9}
- **D10 The recorded option.** This task adds `instructions` to the generator's recorded
  flags ([[task-I1.b-substrate#c-flag]]) and hangs its three entries on the events
  `PreCompact`, `SessionStart` and `InstructionsLoaded`. {#d10}

## Acceptance criteria {#acceptance}

Each event is fired the way Claude Code fires it: every generated command whose matcher
matches, run by `/bin/bash -c` with the envelope on stdin (`tests/task21_1_support.py`), in a
sandbox project with `instructions` enabled. {#acceptance-lead}

- **AC-1 Generated config.** With the option on: PreCompact holds the save entry and exactly
  one marker entry; SessionStart holds exactly one marker entry, matcher `compact|clear`; one
  `InstructionsLoaded` entry; the session-start focus entry is byte-identical to base. With
  the option absent the render equals base. `--check` is clean after `--apply` in both.
  `tests/test_hook_wiring.py`, `tests/test_hooks_reproducible.py`. {#ac-1}
- **AC-2 The events write it.** PreCompact → `last_marker` is `precompact`; SessionStart
  `compact` and `clear` → those; `resume` and `startup` → the file is unchanged. The marker
  entry's stdout is empty in every case. `test_hook_wiring.py::test_marker_by_event[source]`.
  {#ac-2}
- **AC-3 Nothing else moves; failures are told apart.** The ring, `focus.json` and the graph
  turn are byte-identical around AC-2. A marker file holding `{` reads as `unreadable` with
  one stderr line. An unwritable `.emitted` directory → exit 1, one `Error:` line, no
  traceback. `…::test_marker_failures[case]`. {#ac-3}
- **AC-4 A subagent's compaction is its own.** A PreCompact envelope with `agent_id` writes
  `marker.<agent_id>.json` and leaves the session's marker unchanged; `last_marker` with that
  id reads it. `…::test_marker_is_per_context`. {#ac-4}
- **AC-5 A load writes a row.** Firing the `InstructionsLoaded` entry for a rule
  (`path_glob_match`) and for a `CLAUDE.md` reload in a subagent (`compact`, `agent_id`)
  appends two rows with D7's keys; no path text from either envelope is in the ledger file.
  `tests/test_context_cost.py::test_loaded_rows`. {#ac-5}
- **AC-6 One helper.** `tests/test_compaction_handoff.py` passes unchanged. With a `{` line
  planted in each ledger, the `handoff` view and the `instructions` view each report one
  unreadable line; with the clock knob past the keep time, an append reaps old rows from each
  (7 days, 90 days). `tests/test_context_cost.py::test_ledgers_share_one_helper[ledger]`.
  {#ac-6}
- **AC-7 Loud where it should be.** An unwritable ledger directory → `rmx rules loaded` exits
  1 with one line naming the path. No store → exit 0 and no row.
  `…::test_loaded_failures[case]`. {#ac-7}
- **AC-8 The view.** After AC-5: text and `--json` show both rows' units, outcomes, bytes and
  last use; the `CLAUDE.md` hash is shown by name.
  `tests/test_context_cost.py::test_instructions_view[format]`. {#ac-8}
- **AC-9 Mutations that must each fail a test:** the marker chained into the save command
  (AC-1); a marker written on `resume` (AC-2); output on the marker entry's stdout (AC-2);
  exit 2 passed through (AC-3); `agent_id` ignored (AC-4); path text written to a row (AC-5);
  an unreadable line skipped uncounted (AC-6); the reap never run (AC-6). {#ac-9}

## Files {#files}

| File | Change |
|---|---|
| `src/refmatrix/stm.py` | `mark_compaction`, `last_marker`, `Marker`, the `.emitted` directory helper |
| `src/refmatrix/hooks.py` | the three entries; the recorded `instructions` option |
| a new ledger-helper module; `src/refmatrix/handoff.py` | D6; the handoff ledger calls it |
| `src/refmatrix/instructions.py`, `src/refmatrix/telemetry.py` | the row writer; the view |
| `src/refmatrix/cli.py`, `src/refmatrix/verbs.py` | the `compact-marker` choice; `rules loaded`; `INTERNAL_CLI` |
| `tests/test_hook_wiring.py`, `test_hooks_reproducible.py`, `test_context_cost.py`, `test_verb_parity.py` | the ACs |

## Risks (self-audit) {#risks}

1. **Real:** in a sandbox project, run the generated PreCompact, SessionStart and
   `InstructionsLoaded` commands by hand with real envelopes and paste the marker file, the
   ledger rows and `rmx telemetry --context`.
2. **Wiring:** every AC fires the generated command; `mark_compaction` is called directly
   only in addition (10.3's own rule).
3. **Census:** callers of `handoff._record_event` and `handoff_events` (the gate, pulled,
   remind, precompact and the telemetry view); both outputs of the view; the main-session,
   subagent and teammate envelope forms. The save entry's stdout contract (C1) is untouched.
4. **Bound:** each command is one file write or append; no daemon call, no retry. The reap
   is bounded by the ledger's size and runs at most once a day.
5. **Busy / down:** nothing here calls the daemon; RED fires AC-2 and AC-5 with no daemon up
   and once beside a held writer to show neither waits.
6. **Guard:** the `unreadable` branch and the per-agent branch are reached by real files and
   real envelopes (AC-3, AC-4).
7. **Loud:** AC-3 and AC-7 paste exit code and stderr; the permission failure is the case
   outside the JSON error class.
8. **Handoff:** the `spawned` row is I1.g's and the `invoked` row is
   [[task-I1.d-first-skills#second-batch]]'s. The old masked rendering of the option-off path
   gets a deferral row at the merge, closed when H1.f has enabled the last fleet repo.

## For the user {#for-the-user}

None. For the lead: D1 settles the POP's stale point on 10.3 R4 in the spec instead of at
RED; D3 is new since bug-307.
