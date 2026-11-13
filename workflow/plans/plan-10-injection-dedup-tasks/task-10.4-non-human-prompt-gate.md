---
gmd: "0.1"
id: task-10.4-non-human-prompt-gate
title: "Task 10.4: one predicate names a non-human prompt (teammate / agent / cross-session / bus / task-notification), and scan-prompt and the per-prompt recall inject nothing on it, counted as skipped_non_human"
tags: [task, plan-10, scan-prompt, memory-recall, gate, stm, hooks, telemetry]
metadata:
  node_type: task
  status: pending
  plan: plan-10-injection-dedup
  created: 2026-11-13
---

# Task 10.4: non-human prompt gate {#root}

> Plan: [[plan-10-injection-dedup]]
> Status: Pending (spec drafted 2026-11-13; ch-bsd spec review next)
> Depends on: [[task-25.1-recall-hook-byte-budget]] merged (the per-prompt recall runs through the
> verb); [[task-25.2-thin-prompt-gate]] merged (it creates `terms.prompt_gate`, the one gate this
> task extends).
> User decision: D2 of 2026-11-13, [[plan-10-injection-dedup#decisions-log]].

rel: part-of -> [[plan-10-injection-dedup]]
rel: depends-on -> [[task-25.1-recall-hook-byte-budget]]
rel: amends -> [[task-25.2-thin-prompt-gate#r1]]
rel: amends -> [[task-25.2-thin-prompt-gate#r3]]
rel: derives-from -> [[measurement-injection-already-held-2026-11-13]]
rel: depends-on -> [[feedback_converge_repeated_shapes]]
rel: depends-on -> [[feedback_no_raw_prompts_in_public_repo]]
rel: related-to -> [[task-21.1-context-usage-telemetry]]

## Why {#why}

The 2026-11-13 measurement put about 64% of prompt-channel deliveries on non-human prompts, held
54.0% / 59.9% there against 27.7% / 40.4% on human prompts
([[measurement-injection-already-held-2026-11-13#breakdowns]]). The user decided (D2) that
scan-prompt and the per-prompt recall inject nothing on teammate, agent, cross-session, bus or
task-notification turns. {#why-lead}

Nothing decides that today. `stm.is_ambient_text` (`stm.py:108`) knows three shapes (`<channel`,
`<task-notification`, `[SYSTEM NOTIFICATION`) and only the focus input hook and `rebuild_focus`
call it; `cli._is_ambient_prompt` (`cli.py:1981`) is a verbatim copy used by the input hook
(`cli.py:2139`). scan-prompt and recall call neither, so they run on every turn, including a
`<task-notification>` that the focus hook already ignores.

## Census (read-only, 2026-11-13, counts and prefixes only) {#census}

Three sources, refmatrix and cliquedb. No prompt, message or reply text was read into any output;
attribute VALUES were not read, only attribute names. Scripts: the session scratchpad `arch10r/`.

**(1) The hook envelope's `prompt`, as the focus input hook recorded it** (STM ring `input`
events; the ring stores `prompt[:300]` for every prompt the ambient filter let through; APFS
clones, read-only):

| opening | attribute names | refmatrix | cliquedb | newest |
|---|---|---|---|---|
| `<agent-message` | `from` | 325 | 163 | 2026-11-13 / 2026-11-11 |
| `<cross-session-message` | `from`, `from-name`, `from-mode` | 10 | 0 | 2026-10-06 |
| `<channel` | `source`, `channel`, `from`, `type`, `id`, `ts` (+`project`) | 238 | 300 | 2026-07-23 |
| `<task-notification` | none | 5 | 523 | 2026-07-23 |
| plain (human) | — | 1,164 | 1,619 | — |

`<channel` and `<task-notification` stop on 2026-07-23 because the ambient filter was added then
(the ring no longer records them); `<agent-message` and `<cross-session-message` were never filtered.
No input event had leading whitespace.

**(2) `query.log` hook rows** (`kind=scan`, and `kind=recall` without `session_start` / `recent`,
`invocation=hook`; the row's `body` is the prompt's first 200 chars), 2026-10-20 onward, the
measurement's window: {#census-querylog}

| store | channel | `<agent-message` | `<task-notification` | other | non-human share |
|---|---|---|---|---|---|
| refmatrix | scan | 110 | 46 | 175 | 47.1% |
| refmatrix | recall | 116 | 47 | 175 | 48.2% |
| cliquedb | scan | 142 | 101 | 150 | 61.8% |
| cliquedb | recall | 147 | 101 | 149 | 62.5% |

So about half of all hook prompts (55% of scan rows pooled) are non-human by an EXACT test on the
envelope text, against the measurement's time-window heuristic (64% of delivered UNITS).

**(3) Transcripts** (`~/.claude/projects/<proj>/*.jsonl` and `*/subagents/*.jsonl`, user-role
entries that are not tool results):

- `<teammate-message teammate_id=` 385 and `<fork-boilerplate>` 25, all in SUBAGENT transcripts.
  No subagent transcript holds a UserPromptSubmit hook attachment, and no ring input or
  `query.log` row has either opening: on today's harness these turns do not reach the hook.
- Peer messages render in the transcript as `Another Claude session sent a message:` (864: 353
  `isMeta` and 497 plain in main transcripts, 14 in subagent ones). The 353 `isMeta` ones (with
  `origin.kind = peer`) join within 10 s to a ring `<agent-message` input in 351 cases: the hook
  sees `<agent-message`, not the prose. Of the 497 plain ones, 487 have no ring input within 10 s
  (no hook evidence either way).
- `<task-notification>` 140 (main). The transcript also carries `origin.kind` (`human`,
  `task-notification`, `peer`, `coordinator`) on newer entries; that field is in the TRANSCRIPT,
  and nothing shows the hook envelope carries it ([[#r0]]).

## Decisions {#decisions}

| # | decision | reason |
|---|---|---|
| n1 | The predicate is a prefix table, `terms.AMBIENT_PREFIXES`, seven `(family, opening)` rows: `channel` `<channel`; `task-notification` `<task-notification`; `system-notification` `[SYSTEM NOTIFICATION`; `agent-message` `<agent-message`; `cross-session-message` `<cross-session-message`; `teammate-message` `<teammate-message`; `fork-boilerplate` `<fork-boilerplate` | the first five are what the envelope carries ([[#census]] (1), (2)); the last two are harness tags seen only in transcripts, kept because transcript readers call the same predicate and a harness that starts hooking subagent turns must not turn them into "human" prompts |
| n2 | NOT in the table: `Another Claude session sent a message:`; `<command-name>`, `<command-message>`, `<bash-input>`, `<bash-stdout>`, `<local-command-*>` | the first is transcript prose a person can paste, and the hook sees `<agent-message` for the same turn; the others are the user's own slash and bash commands (human intent) |
| n3 | A tag opening matches only at a tag boundary: after the name comes whitespace, `>` or the end of the text; leading whitespace is stripped | `<agent-messages-log` is not an agent message; the census found no leading whitespace, but the old predicate stripped it and the rule stays |
| n4 | The definition lives in `terms.py` (`ambient_family(text) -> str \| None`); `stm.is_ambient_text(text)` stays as the name its callers use and returns `ambient_family(text) is not None` | `terms.prompt_gate` (25.2) must call it, and `terms` cannot import `stm` (`stm` imports `scan`, which imports `terms`); one definition, three consumers |
| n5 | 10.4 EXTENDS 25.2's gate rather than adding a second gate: `terms.prompt_gate` checks `ambient_family` FIRST, then 25.2's ack-only rule | two call sites (scan-prompt, recall) must ask ONE function; a second gate called beside the first is the shape this repo has seen skipped at one call site four times ([[feedback_converge_repeated_shapes]]); 25.2's AC-6 structural test already pins "one gate" |
| n6 | 10.4 is its own task, after 25.2 merges; 25.2's spec is NOT re-opened | 25.2 has been through three ch-bsd rounds; this task's delta (a clause, a table, a gate kind, a telemetry value) is reviewable on its own |
| n7 | A non-human prompt gets NOTHING from scan-prompt, the STM composite included | D2 is no injection at all; 25.2 g5 keeps the composite on an ACK because the session's topics are what a human "yes next" needs, which does not hold for a teammate's report |
| n8 | The focus input hook follows the predicate: `<agent-message` and `<cross-session-message` turns are no longer recorded as STM `input` events (no turn increment); tool events after them still are | one predicate, one meaning ("not user intent", the existing docstring); the bus-message case (`<channel`) was decided the same way in 2026-07; the STM turn becomes a human-turn count |
| n9 | `rmx curator status` (the second producer in `scan_cmd`) is NOT gated here | outside D2's named surfaces, and it does not read the envelope (scan-prompt consumes stdin); open question to the user ([[#open-questions]]) |
| n10 | Counted on the call's EXISTING row: `gated: "skipped_non_human"`, `gate_family: <family>`, `retrieved: 0` | 25.2 R4's field with a second value; the family label is a constant from the table, never prompt text |

## Requirements {#requirements}

0. **R0 What the envelope carries.** At RED time, record (key NAMES only) the UserPromptSubmit
   envelope keys on a human prompt and on an `<agent-message` turn, from a scratch Claude Code
   project (19.5 R1's / 25.1 R0's scratch-project rule; never this repo's settings). If the
   envelope carries an origin-like field, stop and report: the user decides whether the predicate
   reads it before the prefix. {#r0}
1. **R1 One predicate.** `terms.AMBIENT_PREFIXES: tuple[tuple[str, str], ...]` (n1) and
   `terms.ambient_family(text: str) -> str | None` (n3). `stm.is_ambient_text` delegates (n4).
   `cli._is_ambient_prompt` is deleted; `cli.py:2139` calls `stm.is_ambient_text`. No other module
   holds an opening from the table. {#r1}
2. **R2 The gate, extended.** `terms.PromptGate` (25.2 R1) gains `kind: str` ∈ `{"ok",
   "ack_only", "non_human"}`. `terms.prompt_gate(prompt)` returns `PromptGate(passed=False,
   tokens=(), reason="skipped_non_human: <family>", kind="non_human")` when `ambient_family`
   names a family, BEFORE the ack-only rule runs; otherwise 25.2's result with `kind` set. {#r2}
3. **R3 Call sites** (25.2 R3's two, unchanged in number). {#r3}
   - `scan.scan_prompt`: on `kind == "non_human"` it returns the empty string: no
     `match_concepts`, no content leg, no rerank, no helix, no composite (n7), and no block rev
     ([[task-10.2-plan-10-injection-dedup]]: the versioned block state is left untouched). On `ack_only` it keeps 25.2's behaviour.
   - Per-prompt recall: the verb's `gate_thin_prompt=True` path (25.2 R3, set by the CLI's
     `--stdin-json`) returns an empty payload with no retrieval and no embedding on `non_human`;
     exit 0. An explicit query (interactive, MCP) is never gated (25.2 R3 unchanged).
   - The focus input hook: no code change beyond R1's call; behaviour per n8.
4. **R4 Counted, never silent.** A gated invocation writes the call's existing row with
   `gated: "skipped_non_human"`, `gate_family`, `retrieved: 0`: scan-prompt's `query.log` row
   and the `prompt_recall` row through 21.1's `_RecallCall`. No `delivered` or `retrieved` event
   is written for it. `rmx telemetry --context` shows gated counts per channel per `gated` value
   and per family. {#r4}
5. **R5 Before / after on the same corpus.** {#r5}
   - **Before (recorded at RED):** [[#census-querylog]]'s table, recomputed by the GREEN
     `terms.ambient_family` over the same `query.log` clones (the numbers must equal the census:
     a difference is a predicate defect or a census defect, and is resolved before GREEN); and the
     measurement's delivered units on prompt channels joined by `query_id` to those rows, split by
     the predicate (this replaces the measurement's time-window human / non-human heuristic with
     the exact test, counts only).
   - **After (deploy, after the fleet has been busy):** over a window holding at least as many hook
     prompts as the before window, per store: gated rows by family; 0 `delivered` events whose
     `query_id` belongs to a gated row; bytes per UserPromptSubmit event (scan-prompt + recall)
     on human vs non-human prompts; the human-only held share beside the measurement's 32.5%.
   - Written to `workflow/measurements/non-human-gate-2026-11.md` (GMD), counts only.

## Acceptance criteria {#acceptance}

Run in 23.0's sandbox on 25.1's fixture store, through the GENERATED UserPromptSubmit commands
(`hooks._claude_hook_block(...)`, `bash -c`, the envelope on stdin), as 25.2's ACs are. Message
bodies are synthetic text built to match fixture concepts (so a missing gate visibly injects), and
attribute values are synthetic. {#acceptance-lead}

1. **AC-1 The predicate table.** `ambient_family` returns the family for each of the seven openings
   with a synthetic attribute set in the census's attribute names (`<agent-message from="x">`,
   `<cross-session-message from="a" from-name="b" from-mode="c">`, `<task-notification>`, …), with
   and without leading whitespace; returns None for `<agent-messages-log x>`, `Another Claude
   session sent a message: …`, `<command-name>/x</command-name>`, `<bash-input>ls</bash-input>`, a
   plain prompt, and a prompt that merely CONTAINS `<agent-message` after its first character.
2. **AC-2 scan-prompt injects nothing.** For an `<agent-message`, a `<cross-session-message` and a
   `<task-notification>` envelope whose body names fixture concepts, the generated scan-prompt
   command prints 0 bytes with the composite enabled and a two-topic session ring. RED at HEAD
   (bundles and the composite print).
3. **AC-3 recall injects nothing.** The same three envelopes through the generated per-prompt
   recall command: empty stdout, exit 0, and the row shows `retrieved: 0` (no embed). RED at HEAD.
4. **AC-4 Counted.** After AC-2/AC-3: exactly one row per gated invocation per channel with
   `gated: "skipped_non_human"` and the right `gate_family`; no `retrieved` / `delivered` events
   carry those calls' `query_id`s; `rmx telemetry --context` reports the counts by family.
5. **AC-5 Human prompts untouched.** 25.2's AC-3 pass list still injects through both commands,
   and its gated list is still gated as `ack_only` (kind checked).
6. **AC-6 The clause order.** An `<agent-message from="x">` whose body is `ok` is gated with
   `kind == "non_human"` and prints nothing, composite included (under ack-first ordering it
   would be `ack_only` and print the composite).
7. **AC-7 Focus follows.** Through the generated focus input command, an `<agent-message` envelope
   records no `input` ring event and leaves the graph `turn` unchanged; a human prompt increments
   it; `rmx focus rebuild --dry-run` on a ring holding `<agent-message` inputs counts them in
   `dropped_ambient`.
8. **AC-8 One predicate.** A structural test parses `src/refmatrix/`: the seven openings appear as
   string literals only in `terms.py`; `cli._is_ambient_prompt` does not exist; `stm.is_ambient_text`
   returns True for every AC-1 positive. 25.2's AC-6 ("one gate") still passes.
9. **AC-9 Mutations that must FAIL a test:** `<agent-message` row removed from the table (AC-1,
   AC-2); tag-boundary check dropped (AC-1: `<agent-messages-log` matches); scan-prompt call site
   skipping the gate (AC-2); recall call site skipping it (AC-3); ack clause evaluated first (AC-6);
   the composite kept on `non_human` (AC-2); the gated row not written (AC-4); `cli._is_ambient_prompt`
   kept with the old three-prefix tuple and still called by the input hook (AC-7, AC-8); the
   predicate matching anywhere in the text instead of at the start (AC-1).

## Files to modify {#files}

| file | change |
|---|---|
| `src/refmatrix/terms.py` | `AMBIENT_PREFIXES`, `ambient_family()`; `PromptGate.kind`; `prompt_gate` checks the family first |
| `src/refmatrix/stm.py` | `is_ambient_text` delegates to `terms.ambient_family` |
| `src/refmatrix/cli.py` | delete `_is_ambient_prompt`; the input hook calls `stm.is_ambient_text`; gated recall row fields through `_RecallCall` |
| `src/refmatrix/scan.py` | `non_human` returns empty (no composite) and writes the gated row |
| `src/refmatrix/verbs.py` (`memory_recall`) | `non_human` on the `gate_thin_prompt` path |
| `src/refmatrix/telemetry.py` | `gate_family` on the rows; per-family gated counts in the hook-cost report |
| `tests/test_task10_4_non_human_gate.py` (new) | AC-1..AC-9 |
| `workflow/measurements/non-human-gate-2026-11.md` (new) | R5 before / after |

No verb parameter is added (25.2's `gate_thin_prompt` carries it), so verb parity is unchanged.

## Test strategy {#test-strategy}

- RED first on AC-1 (new families), AC-2, AC-3, AC-4, AC-6, AC-7 at the 25.2-merged base; a RED
  that passes at HEAD is not a RED ([[feedback_red_test_must_fail_at_head]]).
- No mock of the gate, scan-prompt, recall, STM or telemetry; generated commands only for AC-2..AC-7.
- Fixture envelopes are synthetic; no transcript, ring or `query.log` line is committed. R5's
  scripts read clones in-process and write counts only.

## Open questions {#open-questions}

| # | question | recommendation |
|---|---|---|
| q1 | Does `rmx curator status` (≤ 500 B, every prompt) also go quiet on non-human prompts? | yes, by D2's spirit, but it needs the envelope plumbed into `scan_cmd`'s second command; a follow-up the user should confirm (n9) |
| q2 | Should the live rings be rebuilt so past `<agent-message` inputs leave the focus graphs? | no: `rmx focus rebuild` stays manual; new turns follow n8 from deploy |

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation table in the implementation summary.
- Implementation summary at `workflow/implementation_summaries/task-10.4-non-human-prompt-gate.md`.
- R5's measurement file written (before at RED, after at deploy).
- Committed on branch `task-10.4-non-human-prompt-gate`; merged `--no-ff` to `master`.
