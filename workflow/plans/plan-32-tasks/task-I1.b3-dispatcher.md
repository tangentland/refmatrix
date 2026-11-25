---
gmd: "0.1"
id: task-I1.b3-dispatcher
title: "Task I1.b3: the dispatcher: one prefiltered entry per event, deny and gate, inject once, the cap channels, counted failures, and C13's hook half"
tags: [task, plan-32, instructions, hooks, dispatcher, deny, gate, once, budget]
metadata:
  node_type: task
  status: drafting
  plan: plan-32-instruction-architecture
  created: 2026-11-24
  author: ch-architect (Fable 5.2)
---

# Task I1.b3: the dispatcher {#root}

> Status: drafted for the spec window (L232); the lead approves. Part of queue row I1.b
> ([[task-I1.b-substrate#split]]). **Large** (hook output is a shared path): RED and GREEN in
> separate hands, mutations, one ch-bsd pass. Waits on b1 and b2, and on the verdicts of P1,
> P2, P4 and P5 ([[task-I1.b0-probes#verdicts]]). Install window 1 follows it.

rel: implements -> [[refmatrix/adr-0007-instruction-architecture#dispatcher]]
rel: implements -> [[refmatrix/adr-0007-instruction-architecture#once]]
rel: implements -> [[refmatrix/adr-0007-instruction-architecture#cap]]
rel: implements -> [[refmatrix/adr-0007-instruction-architecture#dispatcher-failure]]
rel: implements -> [[refmatrix/adr-0007-instruction-architecture#contradictions]]
rel: part-of -> [[task-I1.b-substrate]]
rel: depends-on -> [[task-I1.b1-units-and-check]]
rel: depends-on -> [[task-I1.b2-marker-and-ledger]]

## Goal {#goal}

A tool call that breaks a compiled rule is denied with the rule and the command to run
instead; a call that starts a procedure is stopped once with its checklist; a call that
matches nothing costs one shell test. No failure of the dispatcher ever blocks a session, and
every failure is counted and said. {#goal-body}

## What is built {#design}

- **D1 One entry per event.** `rmx rules fire --event <E>` (hook plumbing,
  `verbs.INTERNAL_CLI`) is generated for each enabled event that a compiled unit binds to,
  with no matcher on the tool events: the prefilter decides. {#d1}
- **D2 The prefilter.** The generated command is bash. It reads the event's pattern from a
  sidecar the compiler writes, with a shell builtin, and tests the raw envelope. On no match
  it exits 0 and has started no process. A missing sidecar goes to Python, which counts it.
  If P4 found a native filter, the entry uses it too. {#d2}
- **D3 The decision.** Python reads the compiled table. `who` comes from the envelope's
  `agent_id` and `agent_type` (bare and namespaced names both match). `where` and `when` are
  judged on the **effective target**, not the envelope's `cwd`: one helper moves it for a
  leading `cd X &&`, `git -C X`, `--root X` and `REFMATRIX_ROOT=X` (ch-bsd counted 360 of
  551 live git events running `cd <clone> && git …` under the dev tree's `cwd`:
  [[bsd-impressions#imp-capture-cwd-is-not-the-repo]]). If bug-318's fix has merged such a
  reader, this is that one. Deny beats ask beats gate beats context. {#d3}
- **D4 The outcomes.** `deny`: JSON at exit 0, the unit's text as the reason. `gate`: the
  same, once per key; the retry passes. `post`: PostToolUse `additionalContext`. `ask` and
  `context` are built only under their probe constants (`ASK_VERIFIED`, `CONTEXT_VERIFIED`),
  each a literal that cites P2's or P1's committed evidence; `context` returns
  `additionalContext` and no `permissionDecision`. **No path returns `allow`.** {#d4}
- **D5 Once.** Key: session, `agent_id` or `main`, unit id, unit sha. One small file per key
  under `stm/<session>.emitted/instructions/`, written through b2's directory helper, so
  parallel hooks never read-modify-write. An entry older than that context's `last_marker`
  suppresses nothing; an unreadable marker counts as now. Unless P5 showed that a subagent's
  compaction fires a hook, a subagent's entry also stops suppressing after
  `ONCE_SUBAGENT_TTL_S` (1,800). A project with no store keeps the entries under the user's
  temp directory. **A gate denies only after its entry is written**; if it cannot be
  written, the call is allowed and the failure counted, so a gate never denies twice. {#d5}
- **D6 The cap.** `hook_budget` gains `instruction_pre` (6,000 B) and `instruction_post`
  (4,000 B), each with its command row, under the import-time check. Matching units are
  packed by priority and labelled by kind; one that does not fit becomes a pointer line (its
  id, file and anchor) and a `dropped_bytes` row. {#d6}
- **D7 Rows.** `denied`, `asked`, `gated`, `injected`, `suppressed_once`, `dropped_bytes`
  and `error`, through b2's writer. {#d7}
- **D8 Failures allow and are counted.** Only a JSON deny at exit 0 blocks. A missing or
  unreadable table, an exception, an older `rmx` (click's exit 2) and the dispatcher's own
  time budget (it stops one second inside the entry's `timeout`) all end at exit 0 with the
  call allowed. One rendering helper in `hooks.py` wraps a command so that a non-zero exit
  appends a row (the hook's name, the exit code, the last stderr line) to
  `<store>/hook_failures.jsonl`. The dispatcher's SessionStart entry prints
  `rmx rules: dispatcher failed N times since <ts> (last: <cause>)` once per count, and its
  shell preamble prints one line when `rmx` is not on PATH. {#d8}
- **D9 C13's hook half** (Q56 = a). Whenever `instructions` is enabled, the four STM capture
  entries (`input`, `tool`, `tool-pre`, `say`) are rendered through D8's helper, with no
  `2>/dev/null` and no `|| true`: exit 0, the failure counted, and the SessionStart entry
  prints `rmx focus hook: N capture failures since <ts> (last: <event>: <cause>)`. {#d9}
- **D10 The cost band.** Before window 1 the generated PreToolUse command is timed with
  b0's harness on non-matching envelopes: a median over 10 ms holds the window
  ([[refmatrix/adr-0007-instruction-architecture#dispatcher-cost]]). {#d10}

## Acceptance criteria {#acceptance}

Each test fires the generated command by `/bin/bash -c` with the envelope on stdin, in a
sandbox project with local units and `instructions` enabled. New feature, one new file,
`tests/test_instruction_dispatch.py`; the hook-config cases extend the existing files.
{#acceptance-lead}

- **AC-1 Deny, by who and where.** A unit bound `who: subagent`, `where: store`: an
  `agent_id` envelope in the store tree → a JSON deny at exit 0 carrying the unit's text and
  a `denied` row. The same from the main session, the same behind `cd <mkdtemp> &&`, and
  `git -C <a no-store dir>` under the store tree's `cwd` → nothing.
  `test_instruction_dispatch.py::test_deny_who_where[case]`. {#ac-1}
- **AC-2 A non-matching call starts no `rmx`.** With a shim `rmx` first on PATH that touches
  a sentinel: a non-matching envelope leaves no sentinel, exits 0 and prints nothing; a
  matching one leaves it. `…::test_prefilter_starts_no_process[case]`. {#ac-2}
- **AC-3 Gate, once per context.** First call → deny with the checklist, `gated`; the same
  call again → nothing, `suppressed_once`; after the generated PreCompact marker entry fires
  → gated again; a subagent's first call in the same session → gated; a changed unit sha →
  gated. `…::test_gate_once[case]`. {#ac-3}
- **AC-4 A gate never traps.** With the once directory read-only the call is allowed and a
  failure row is written; with no store the entry lands in the temp home and the retry
  passes. `…::test_gate_never_denies_twice[case]`. {#ac-4}
- **AC-5 No allow; probe-gated modes follow the committed verdicts.** For every sample
  envelope, firing or not, the output never holds `allow`. Under the committed constants a
  `context` unit is delivered by its mode or its declared fallback, and an `ask` unit as b0
  decided. `…::test_never_allows`, `…::test_probe_gated_modes`. {#ac-5}
- **AC-6 The cap.** Three units matching one call, their texts over 6,000 B together: the
  output is within the channel, the highest priority is whole, the one that does not fit is a
  pointer line, and a `dropped_bytes` row names it. `…::test_overflow_becomes_a_pointer`. {#ac-6}
- **AC-7 Failures allow, are counted, and are said once.** One case each: no compiled table;
  a table holding `{`; an unreadable table; a shim `rmx` that exits 2. The command never
  exits 2, the call is not blocked, and `hook_failures.jsonl` gains a row. The SessionStart
  entry then prints the one line; fired again with no new failure it prints nothing. With no
  `rmx` on PATH the shell line is printed. `…::test_failures_allow_and_are_counted[case]`.
  {#ac-7}
- **AC-8 Capture failures are counted** (C13). With the option on, the four focus entries
  hold no `2>/dev/null` and no `|| true`; one fired with an unwritable `stm/` exits 0, adds a
  row, and the next SessionStart prints the capture line. With the option absent they equal
  base. `tests/test_hook_wiring.py::test_capture_failures_are_counted[event]`;
  `tests/test_hooks_reproducible.py::test_no_memory_path_hook_is_silenced` extended. {#ac-8}
- **AC-9 Bounded.** With a `git` shim that sleeps, a unit with a `when:` state returns inside
  the dispatcher's budget (a test-sized knob), allows and counts; one case runs at the real
  default. `…::test_dispatch_is_bounded[budget]`. {#ac-9}
- **AC-10 The fixtures, through the command.**
  `tests/test_instruction_units.py::test_packaged_unit_fixtures` now sends each envelope
  through the generated command, prefilter included. {#ac-10}
- **AC-11 Mutations that must each fail a test:** a prefilter that under-matches (AC-10);
  `allow` emitted (AC-5); exit 2 passed through (AC-7); the once key without the agent id
  (AC-3); the marker ignored (AC-3); a deny returned before the once entry is written (AC-4);
  an overflow printed whole (AC-6); a failure not counted (AC-7); `|| true` left on a focus
  entry (AC-8); the envelope `cwd` used as the target (AC-1). {#ac-11}
- **AC-12 The band is measured.** `workflow/measurements/instruction-probes.md` gains the
  dispatcher's median, p95 and floor before window 1. {#ac-12}

## Files {#files}

| File | Change |
|---|---|
| `src/refmatrix/instructions.py` | the runtime half of `decide`, the effective-target helper, once, packing |
| `src/refmatrix/hooks.py` | the dispatcher entries; the counted-failure helper; the four focus entries; the SessionStart entry |
| `src/refmatrix/hook_budget.py` | two channels and their command rows |
| `src/refmatrix/cli.py`, `src/refmatrix/verbs.py` | `rules fire`; `INTERNAL_CLI` |
| `tests/test_instruction_dispatch.py` (new), `test_instruction_units.py`, `test_hook_wiring.py`, `test_hooks_reproducible.py`, `test_verb_parity.py` | the ACs |
| `workflow/test_mock_registry.md` | the `rmx` and `git` PATH shims (process boundaries) |

## Risks (self-audit) {#risks}

1. **Real:** in a sandbox project, fire the generated PreToolUse command by hand with a deny
   envelope, a gate envelope twice and a non-matching one; paste the outputs and the ledger.
   At window 1 the lead provokes one real deny in the dev tree.
2. **Wiring:** every AC goes through the generated command; `decide` is called directly only
   in addition.
3. **Census:** the PreToolUse producers (focus `tool-pre`, C1's read gate, the enforce
   scripts, this entry): two may deny one call and each fails open on its own. Envelope
   forms: main, subagent, teammate, an isolated agent with no store; tools Bash, Edit, Write
   and Agent. The four focus entries have one rendering site after D9.
4. **Bound:** the prefilter starts no process; Python reads one file and runs at most one
   `git` per `when:` clause, each under 2 s; the whole run stops inside the entry's
   `timeout`. No daemon call and no retry, so the worst case is that timeout.
5. **Busy / down:** the dispatcher never calls the daemon. AC-1 and AC-3 run with no daemon
   up, and RED adds one run beside C2's held writer.
6. **Guard:** every mode, the reset and both failure branches of D5 are reached by real
   envelopes and real files; the probe constants are never patched.
7. **Loud:** a per-call failure is counted, not shown, by the ADR's rule; the loud points
   are the SessionStart line (AC-7, AC-8) and `rmx telemetry --context`. The exit 2 case is
   the failure outside the caught class.
8. **Handoff:** `instruction_stop` and the Stop entries → I1.e; `agent_start` → I1.g; the
   review-due line → I1.i; the `practices: []` line → H1.c; each joins the SessionStart
   entry built here. `adr-gate.sh` becomes a PostToolUse unit in I1.f (the lead adds the
   clause to that row).

## For the user {#for-the-user}

None now. If D10's median is over 10 ms with no native filter (P4), the choice between the
band and the form goes to the user with the measurement.
