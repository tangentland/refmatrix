---
gmd: "0.1"
id: task-10.4-non-human-prompt-gate
title: "Task 10.4: one predicate names a non-human prompt (teammate / agent / cross-session / bus / task-notification); it keeps those turns out of the focus graph, silences curator status on them (Q9), and labels every hook row with the prompt family; no injection gate (Q10)"
tags: [task, plan-10, scan-prompt, memory-recall, curator, stm, hooks, telemetry]
metadata:
  node_type: task
  status: pending
  plan: plan-10-injection-dedup
  created: 2026-11-13
  updated: 2026-11-13
---

# Task 10.4: non-human prompt predicate {#root}

> Plan: [[plan-10-injection-dedup]]
> Status: Pending (drafted 2026-11-13; rev 3 the same day: no injection gate, Q10; ch-bsd spec
> review next). The id keeps "gate" because other docs address it.
> Depends on: [[task-25.1-recall-hook-byte-budget]] merged (curator status's budget and the hook
> command table, R4).
> Decisions: no separate gate, same dedupe as human prompts (Q10); curator silent (Q9); lead:
> agent-message turns are not focus turns, an envelope origin field is read first (2026-11-13).

rel: part-of -> [[plan-10-injection-dedup]]
rel: depends-on -> [[task-25.1-recall-hook-byte-budget]]
rel: derives-from -> [[measurement-injection-already-held-2026-11-13]]
rel: derives-from -> [[measurement-injection-already-held-2026-11-13#gate-comparison]]
rel: derives-from -> [[measurement-injection-already-held-2026-11-13#design-replay-v2]]
rel: depends-on -> [[feedback_converge_repeated_shapes]]
rel: depends-on -> [[feedback_no_raw_prompts_in_public_repo]]
rel: related-to -> [[task-10.2-plan-10-injection-dedup]]
rel: related-to -> [[task-21.1-context-usage-telemetry]]
rel: depends-on -> [[open-questions]]

## Why {#why}

About half of all hook prompts are non-human ([[#census-querylog]]). Removing their per-prompt
injection outright was measured twice and failed both times: the with/without comparison
([[measurement-injection-already-held-2026-11-13#gate-comparison]]) lost 10 R12 explicit uses
that rode agent-message / task-notification turns with no other delivery, and the design replay
found the gate failing in every arm while names-only dedupe on those turns kept every use
([[measurement-injection-already-held-2026-11-13#design-replay-v2]]). So non-human turns get the
same names-only dedupe as human prompts (Q10, built in 10.2), and no injection gate exists.
{#why-lead}

What stays is the predicate and its three non-injection consumers: the focus graph (the lead's
decision: those turns are not user intent), curator status (Q9), and a family label on every
hook row so 10.2's live A/B and the reports can split by it. Today `stm.is_ambient_text`
(`stm.py:108`) knows three shapes and `cli._is_ambient_prompt` (`cli.py:1981`) is a verbatim copy.

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
| n3 | A tag opening matches only at a tag boundary: after the name comes whitespace, `>` or the end of the text; leading whitespace is stripped | `<agent-messages-log` is not an agent message; the old predicate stripped whitespace and the rule stays |
| n4 | The definition lives in `terms.py` (`ambient_family(text, *, origin=None) -> str \| None`); `stm.is_ambient_text(text)` stays as the name its callers use and returns `ambient_family(text) is not None` | curator status, the focus hook, `rebuild_focus`, the hook rows and the measurement scripts share one rule; `terms` is the low-level vocabulary module that `stm` and `scan` already import |
| n5 | NO injection gate: scan-prompt and the per-prompt recall do not consult the predicate to decide what to emit; 25.2's `terms.prompt_gate` is NOT extended | Q10: the gate failed both measurements; non-human turns get 10.2's dedupe like any prompt. 25.2's ack-only rule never fires on a tagged message (its first token is the tag), so no interaction remains |
| n6 | No policy table either (rev 2's `NON_HUMAN_POLICY` is withdrawn) | with Q10 every injection surface behaves the same on every family, and Q9 fixes the only surface that differs; a one-column table would be an indirection shaped like a flag. Curator's rule is one `if` on the predicate |
| n7 | The focus input hook follows the predicate: `<agent-message` and `<cross-session-message` turns are no longer recorded as STM `input` events (no turn increment); tool events after them still are | lead decision 2026-11-13, same principle as `is_ambient_text` ("not user intent"); the bus case (`<channel`) was decided the same way in 2026-07. 10.2 does not use the STM turn for "earlier prompt" (10.2 h2), so the two do not interact |
| n8 | An envelope origin field, if R0 finds one, is read BEFORE the prefix table | lead decision 2026-11-13: a harness field beats text matching; the table stays the fallback and the transcript readers' rule |
| n9 | Curator status becomes its OWN UserPromptSubmit entry reading the envelope, silent on every non-human family (Q9) | today it is the second command of `scan_cmd` and cannot see the envelope (scan-prompt consumes stdin); its own entry gets the envelope on its own stdin, needs no shell plumbing, and cannot suppress scan-prompt's output by failing |
| n10 | Every hook row (scan-prompt's `query.log` row, the `prompt_recall` row, curator status's `cli.log` row) carries `prompt_family` (the family, or `human`); curator's skip also carries `gated: "skipped_non_human"` | 10.2's live A/B splits by it; the skip is counted, never silent; the family label is a constant from the table, never prompt text |

## Requirements {#requirements}

0. **R0 What the envelope carries.** At RED time, record (key NAMES only) the UserPromptSubmit
   envelope keys on a human prompt and on an `<agent-message` turn, from a scratch Claude Code
   project (19.5 R1's / 25.1 R0's rule; never this repo's settings). If the envelope carries an
   origin-like field, `ambient_family` reads it FIRST through its `origin` argument, mapped to the
   same family names (n8). {#r0}
1. **R1 One predicate.** `terms.AMBIENT_PREFIXES: tuple[tuple[str, str], ...]` (n1) and
   `terms.ambient_family` (n3, n4). `stm.is_ambient_text` delegates. `cli._is_ambient_prompt` is
   deleted; `cli.py:2139` calls `stm.is_ambient_text`. No other module holds an opening from the
   table. {#r1}
2. **R2 The focus graph.** No code change beyond R1's call; behaviour per n7. {#r2}
3. **R3 The family label.** The hook `scan-prompt` and `memory recall --stdin-json` compute
   `ambient_family(prompt)` once and write `prompt_family` on their rows (n10); nothing they emit
   depends on it. {#r3}
4. **R4 Curator status (Q9; the 10.4b row).** The generator drops `rmx curator status` from
   `scan_cmd` and emits it as its OWN UserPromptSubmit entry, `rmx curator status --stdin-json`
   (no `|| true`: its own entry cannot suppress the others). 25.1's `hook_budget.HOOK_COMMAND_CHANNELS`
   changes to `scan_cmd` = `scan_prompt` and `curator_cmd` = `curator_status` (per-hook cap, R0
   outcome (A)); budgets unchanged. With `--stdin-json` it reads the envelope; on a non-human family
   it prints nothing and writes its `cli.log` row with `prompt_family` and `gated:
   "skipped_non_human"`. Without `--stdin-json` (interactive) nothing is gated. {#r4}
5. **R5 Before / after.** {#r5}
   - **Before (at RED):** [[#census-querylog]]'s table recomputed by the GREEN `ambient_family`
     over the same `query.log` clones; the numbers must equal the census (a difference is resolved
     before GREEN).
   - **After (deploy, fleet busy):** per store, hook rows by `prompt_family`; curator skips by
     family; the share of ring `input` events that are non-human (expected 0 for the new families).
   - Written to `workflow/measurements/non-human-predicate-2026-11.md` (GMD), counts only.
6. **R6 History.** Rev 2's injection gate, policy table and its with/without A/B are withdrawn
   (Q10); the live A/B is 10.2's (`dedupe` vs `full`, [[task-10.2-plan-10-injection-dedup#r7]]).
   {#r6}

## Acceptance criteria {#acceptance}

Run in 23.0's sandbox on 25.1's fixture store, through the GENERATED UserPromptSubmit commands
(`hooks._claude_hook_block(...)`, `bash -c`, the envelope on stdin). Message bodies and attribute
values are synthetic. {#acceptance-lead}

1. **AC-1 The predicate table.** `ambient_family` returns the family for each of the seven openings
   with a synthetic attribute set in the census's attribute names (`<agent-message from="x">`,
   `<cross-session-message from="a" from-name="b" from-mode="c">`, `<task-notification>`, …), with
   and without leading whitespace; returns None for `<agent-messages-log x>`, `Another Claude
   session sent a message: …`, `<command-name>/x</command-name>`, `<bash-input>ls</bash-input>`, a
   plain prompt, and a prompt that merely CONTAINS `<agent-message` after its first character; with
   an `origin` argument, the origin decides.
2. **AC-2 Injection is unchanged by the predicate.** For an `<agent-message` envelope whose body
   names fixture concepts, the generated scan-prompt and recall commands emit what they emit for a
   plain prompt with the same body (10.2's dedupe aside), and their rows carry `prompt_family:
   "agent-message"`; a human prompt's rows carry `human`.
3. **AC-3 Focus follows.** Through the generated focus input command, an `<agent-message` envelope
   records no `input` ring event and leaves the graph `turn` unchanged; a human prompt increments
   it; `rmx focus rebuild --dry-run` on a ring holding `<agent-message` inputs counts them in
   `dropped_ambient`.
4. **AC-4 Curator status.** The generated config has `rmx curator status --stdin-json` as its own
   UserPromptSubmit entry and `scan_cmd` no longer contains it; with a 30-path curator queue, an
   `<agent-message` envelope prints nothing and writes one row with `gated: "skipped_non_human"`;
   a human prompt prints the queue within `budget("curator_status")`; `rmx install-hooks --check` is
   clean.
5. **AC-5 One predicate.** A structural test parses `src/refmatrix/`: the seven openings appear as
   string literals only in `terms.py`; `cli._is_ambient_prompt` does not exist; `stm.is_ambient_text`
   returns True for every AC-1 positive; scan-prompt and the recall verb call `ambient_family` only
   to label rows (no branch on its result decides output).
6. **AC-6 Mutations that must FAIL a test:** `<agent-message` row removed from the table (AC-1,
   AC-3); tag-boundary check dropped (AC-1); matching anywhere in the text (AC-1); origin ignored
   (AC-1); `cli._is_ambient_prompt` kept with the old three-prefix tuple and still called by the
   input hook (AC-3, AC-5); an injection branch on the family in scan-prompt (AC-2, AC-5); curator
   status left inside `scan_cmd` (AC-4); curator's skip not counted (AC-4); `prompt_family` missing
   from a row (AC-2).

## Files to modify {#files}

| file | change |
|---|---|
| `src/refmatrix/terms.py` | `AMBIENT_PREFIXES`, `ambient_family()` |
| `src/refmatrix/stm.py` | `is_ambient_text` delegates |
| `src/refmatrix/cli.py` | delete `_is_ambient_prompt`; the input hook calls `stm.is_ambient_text`; `curator status --stdin-json`; `prompt_family` on the recall row through `_RecallCall` |
| `src/refmatrix/scan.py` | `prompt_family` on its row |
| `src/refmatrix/hooks.py` | curator status as its own entry |
| `src/refmatrix/hook_budget.py` (25.1) | `curator_cmd` in `HOOK_COMMAND_CHANNELS` |
| `src/refmatrix/telemetry.py` | `prompt_family` in the reports |
| `.claude/settings.json`, `.claude/rmx-hooks.json` | regenerated from Python in the task's clone |
| `tests/test_task10_4_non_human_predicate.py` (new) | AC-1..AC-6 |
| `workflow/measurements/non-human-predicate-2026-11.md` (new) | R5 |

## Test strategy {#test-strategy}

- RED first on AC-1 (new families, origin), AC-2 (the row field), AC-3, AC-4 at the 25.1-merged
  base ([[feedback_red_test_must_fail_at_head]]).
- No mock of the predicate, scan-prompt, recall, curator, STM or telemetry; generated commands only.
- Fixture envelopes are synthetic; no transcript, ring or `query.log` line is committed.

## Open questions {#open-questions}

| # | question | status |
|---|---|---|
| q1 | Curator status silent on non-human prompts? | answered: yes (Q9); [[#r4]] |
| q2 | Rebuild the live rings so past `<agent-message` inputs leave the focus graphs? | no: `rmx focus rebuild` stays manual; new turns follow n7 from deploy |
| q3 | Per-family injection on non-human turns? | answered: no separate gate, same dedupe (Q10) |

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation table in the implementation summary.
- Implementation summary at `workflow/implementation_summaries/task-10.4-non-human-prompt-gate.md`.
- R5's measurement file written (before at RED, after at deploy).
- Committed on branch `task-10.4-non-human-prompt-gate`; merged `--no-ff` to `master`.
