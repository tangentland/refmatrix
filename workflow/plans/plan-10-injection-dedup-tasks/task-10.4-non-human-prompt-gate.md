---
gmd: "0.1"
id: task-10.4-non-human-prompt-gate
title: "Task 10.4: one predicate names a non-human prompt (teammate / agent / cross-session / bus / task-notification); what scan-prompt, the per-prompt recall and curator status inject on it is ONE policy table (Q9 filled, Q10 open), always counted; checked offline before ship and by a per-session live A/B after"
tags: [task, plan-10, scan-prompt, memory-recall, gate, stm, hooks, telemetry]
metadata:
  node_type: task
  status: pending
  plan: plan-10-injection-dedup
  created: 2026-11-13
---

# Task 10.4: non-human prompt gate {#root}

> Plan: [[plan-10-injection-dedup]]
> Status: Pending (spec drafted 2026-11-13; rev 2 the same day: policy table, with/without
> comparison, live A/B, curator status. ch-bsd spec review next). The injection behaviour on
> non-human turns is NOT final: [[#r3]]'s table is filled by Q10 (open).
> Depends on: [[task-25.1-recall-hook-byte-budget]] merged (the per-prompt recall runs through the
> verb); [[task-25.2-thin-prompt-gate]] merged (it creates `terms.prompt_gate`, the one gate this
> task extends).
> User decisions: D2 (direction: no per-prompt injection on non-human turns,
> [[plan-10-injection-dedup#decisions-log]]); curator status silent too (Q9); per-family behaviour
> open (Q10); with/without comparison asked for (user, 2026-11-13). Lead decisions: n8 and R0's
> origin-first rule (2026-11-13).

rel: part-of -> [[plan-10-injection-dedup]]
rel: depends-on -> [[task-25.1-recall-hook-byte-budget]]
rel: amends -> [[task-25.2-thin-prompt-gate#r1]]
rel: amends -> [[task-25.2-thin-prompt-gate#r3]]
rel: derives-from -> [[measurement-injection-already-held-2026-11-13]]
rel: depends-on -> [[feedback_converge_repeated_shapes]]
rel: depends-on -> [[feedback_no_raw_prompts_in_public_repo]]
rel: related-to -> [[task-21.1-context-usage-telemetry]]
rel: related-to -> [[task-21.5-tool-used-signal]]
rel: related-to -> [[exploration-handhold-outcome-experiment#assignment]]
rel: depends-on -> [[measurement-injection-already-held-2026-11-13#gate-comparison]]
rel: depends-on -> [[open-questions]]

## Why {#why}

The 2026-11-13 measurement put about 64% of prompt-channel deliveries on non-human prompts, held
54.0% / 59.9% there against 27.7% / 40.4% on human prompts
([[measurement-injection-already-held-2026-11-13#breakdowns]]). D2 set the direction: no
per-prompt injection on teammate, agent, cross-session, bus or task-notification turns. The
with/without comparison ([[measurement-injection-already-held-2026-11-13#gate-comparison]]) found
the full gate removes 62.3% of prompt-channel units (916,950 → 347,300 B), loses 0 labelled uses,
and loses 10 R12 explicit uses that rode agent-message / task-notification turns with no other
delivery; its pre-registered rule tripped, so the per-family behaviour is the user's (Q10, open).
{#why-lead}

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
| n7 | Under policy `none` a non-human prompt gets NOTHING from scan-prompt, the STM composite included; under `delta`, no composite either | 25.2 g5 keeps the composite on an ACK because the session's topics are what a human ack needs, which does not hold for a teammate's report |
| n8 | The focus input hook follows the predicate: `<agent-message` and `<cross-session-message` turns are no longer recorded as STM `input` events (no turn increment); tool events after them still are; independent of Q10 | lead decision 2026-11-13, same principle as `is_ambient_text` ("not user intent"); the bus-message case (`<channel`) was decided the same way in 2026-07; the STM turn becomes a human-turn count |
| n9 | `rmx curator status` goes silent on non-human turns too (Q9): it becomes its OWN generated UserPromptSubmit entry reading the envelope ([[#r8]]) | Q9 (a). Today it is the second command of `scan_cmd` and cannot see the envelope (scan-prompt consumes stdin); its own entry gets the envelope on its own stdin, needs no shell plumbing, and cannot suppress scan-prompt's output by failing |
| n11 | ONE decision point: `terms.NON_HUMAN_POLICY[family][surface]` ∈ `none` / `delta` / `full`, surfaces `scan_prompt`, `prompt_recall`, `curator_status`; every call site asks `terms.non_human_policy(family, surface, session=…)` and nothing else | Q10 chooses per family (full gate, delta-only, or task-notifications only); Q9 fills the curator column; the mechanism is built and tested for all three values, the shipped values are data filled from the answers |
| n12 | A structured origin field in the envelope, if R0 finds one, is read BEFORE the prefix table | lead decision 2026-11-13: a harness field beats text matching; the prefix table stays the fallback and the transcript readers' rule |
| n13 | The live A/B draws its arm per SESSION from ONE arm table shared with the handhold outcome experiment ([[#r7]]) | the user chose session-level randomisation for a fixed period for that experiment (Q4); two independent draws over the same sessions would confound both |
| n10 | Counted on the call's EXISTING row: `gated: "skipped_non_human"`, `gate_family: <family>`, `retrieved: 0` | 25.2 R4's field with a second value; the family label is a constant from the table, never prompt text |

## Requirements {#requirements}

0. **R0 What the envelope carries.** At RED time, record (key NAMES only) the UserPromptSubmit
   envelope keys on a human prompt and on an `<agent-message` turn, from a scratch Claude Code
   project (19.5 R1's / 25.1 R0's scratch-project rule; never this repo's settings). If the
   envelope carries an origin-like field, `terms.ambient_family` takes an optional `origin`
   argument, read FIRST (n12), mapped to the same family names; the prefix table is the fallback.
   {#r0}
1. **R1 One predicate.** `terms.AMBIENT_PREFIXES: tuple[tuple[str, str], ...]` (n1) and
   `terms.ambient_family(text: str) -> str | None` (n3). `stm.is_ambient_text` delegates (n4).
   `cli._is_ambient_prompt` is deleted; `cli.py:2139` calls `stm.is_ambient_text`. No other module
   holds an opening from the table. {#r1}
2. **R2 The gate, extended.** `terms.PromptGate` (25.2 R1) gains `kind: str` ∈ `{"ok",
   "ack_only", "non_human"}`. `terms.prompt_gate(prompt)` returns `PromptGate(passed=False,
   tokens=(), reason="skipped_non_human: <family>", kind="non_human")` when `ambient_family`
   names a family, BEFORE the ack-only rule runs; otherwise 25.2's result with `kind` set. {#r2}
3. **R3 The decision point and its call sites.** {#r3}
   - `terms.NON_HUMAN_POLICY: Mapping[str, Mapping[str, str]]`, keyed by family then surface
     (`scan_prompt`, `prompt_recall`, `curator_status`); `terms.non_human_policy(family, surface,
     *, session=None) -> str` is its ONLY reader (during the A/B it returns the session's arm's
     value, [[#r7]]). Values: {#policy}
     - `none`: nothing is emitted (scan-prompt: no `match_concepts`, content leg, rerank, helix or
       composite; recall: no retrieval, no embedding, empty payload; curator: no output); exit 0.
     - `delta`: (scan_prompt / prompt_recall only) the block emits only items NOT in its 19.6 block
       state, as an add-only delta (10.2 R2 / R4), never a keyframe, no composite; the added items
       enter the state. The held set is the block state (Q7: no second ledger), so it cuts less
       than the measurement's 57.5% already-held share ([[task-10.5-versioned-block-gate#provisional]]
       measured how little the block state holds); if 10.2 is not built (10.5 d4), `delta` needs
       10.2's R2 state store and R4 delta render built here.
     - `full`: the prompt is injected as a human prompt is today.
   - **Shipped values:** `curator_status` = `none` for every family (Q9). `scan_prompt` and
     `prompt_recall` per family = Q10's answer, written at GREEN with Q10's id in a comment; until
     Q10 is answered this task cannot ship (its RED and the mechanism can be built). Q10's options
     map to: (a) `delta` for every family; (b) `none` for every family; (c) `none` for
     `task-notification` / `system-notification` / `channel`, `full` for the message families.
   - `scan.scan_prompt` and the verb's `gate_thin_prompt=True` path (25.2 R3, set by `--stdin-json`)
     call `prompt_gate` once; on `kind == "non_human"` they ask the policy and act on it. On
     `ack_only` they keep 25.2's behaviour. An explicit query (interactive, MCP) is never gated.
   - The focus input hook: no code change beyond R1's call; behaviour per n8 (independent of the
     policy).
4. **R4 Counted, never silent.** Every non-human invocation writes the call's existing row with
   `gate_family` and `non_human_policy` (`none` / `delta` / `full`); under `none` also `gated:
   "skipped_non_human"` and `retrieved: 0`, and no `retrieved` / `delivered` event. Rows: scan-prompt's
   `query.log` row, the `prompt_recall` row through 21.1's `_RecallCall`, curator status's
   `cli.log` row. `rmx telemetry --context` shows per surface the counts by family and policy. {#r4}
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
6. **R6 Pre-ship offline comparison (the precondition).** The with/without comparison is
   [[measurement-injection-already-held-2026-11-13#gate-comparison]], pre-registered by `dd-10r`
   before its numbers: SAFE if the gate loses at most 1 labelled or R12 explicit use with no
   human-prompt delivery of the same key before it; else the user decides. Result: 0 labelled and
   10 R12 explicit uses lost (2 within minutes) → not SAFE → Q10. The precondition for shipping is
   therefore Q10's answer; the comparison is re-run with the GREEN `terms.ambient_family` and the
   shipped policy table over the same clones before deploy (its numbers must reproduce the
   addendum's for the full gate). {#r6}
7. **R7 Post-ship live A/B, per session.** {#r7}
   - **Arms:** `gate` (the shipped policy table) vs `nogate` (every scan_prompt / prompt_recall
     value `full`; curator's column unchanged, Q9 is not under test). Equal weights, for a fixed
     period written before the run (≥ 14 days and ≥ 40 sessions per arm per store, whichever is
     later), in refmatrix and cliquedb.
   - **One arm table, shared with the handhold experiment** (n13): `arms.SESSION_ARMS` (new, tiny,
     pure module) holds every live session-level experiment's cells and weights, and
     `arms.draw(session_id) -> str` is a pure function of `sha256(session_id + period salt)`
     (recomputable by any process, no state file), called once by the SessionStart focus hook to
     RECORD the arm (one `cli.log` row, `session_arm`) and by `non_human_policy` to apply it. If
     the handhold experiment runs in the same period, the table holds the nested cells: its arm A
     (push on) splits into `A+gate` / `A+nogate`; its B (no push) has no gate factor; its C (bare,
     opt-in) is never drawn. `session_arm` is not 21.1's per-prompt `arm` (19.6 R7), which stays as
     it is.
   - **Outcomes, from telemetry and transcripts, counts only:** injected bytes per HUMAN prompt
     (all per-prompt bytes of the session, non-human turns included, over its human prompts);
     delivered-then-used rate per 100 human prompts (21.5's legs plus R12 explicit `used`); the
     handhold experiment's orientation proxies after session start and `/clear` where its scorer
     exists (recorded, not a band).
   - **Bands, written here before the run:** `gate` cuts bytes per human prompt ≥ 30% and its
     used rate is within −5% of `nogate` (or above) → keep the shipped table; used rate 5-15% below
     → the user decides; > 15% below → the user is asked to move the losing families to `full` or
     `delta`.
   - **The switch is for measurement only:** `arms.py`, its rows and the `session` branch of
     `non_human_policy` are deleted after the period (a row in `workflow/deferral_registry.md`
     with the end date); correctness never depends on them, and outside the period `draw` returns
     the production arm.
8. **R8 Curator status follows (Q9; the 10.4b follow-on).** {#r8}
   - The generator drops `rmx curator status` from `scan_cmd` and emits it as its OWN
     UserPromptSubmit entry, `rmx curator status --stdin-json` (no `|| true`; its own entry cannot
     suppress the others). 25.1's `HOOK_COMMAND_CHANNELS` changes to `scan_cmd` = `scan_prompt`
     and `curator_cmd` = `curator_status` (per-hook cap, R0 outcome (A)); budgets unchanged.
   - `--stdin-json` reads the envelope, calls `terms.prompt_gate`, and on `non_human` asks
     `non_human_policy(family, "curator_status")`; `none` prints nothing and writes the counted
     row (R4). Without `--stdin-json` (interactive) nothing is gated.

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
2. **AC-2 Each policy value, scan-prompt.** With a test policy table, for an `<agent-message`, a
   `<cross-session-message` and a `<task-notification>` envelope whose body names fixture concepts
   (composite enabled, two-topic ring): `none` → 0 bytes; `full` → the same bytes a human prompt
   with that body gets; `delta` → only items outside the block state, no composite, and the state
   grows by them. RED at HEAD for `none` and `delta`.
3. **AC-3 Each policy value, recall.** The same through the generated per-prompt recall command:
   `none` → empty stdout, exit 0, `retrieved: 0` (no embed); `full` and `delta` as in AC-2.
4. **AC-4 Counted.** After AC-2/AC-3: exactly one row per gated invocation per channel with
   `gated: "skipped_non_human"` and the right `gate_family`; no `retrieved` / `delivered` events
   carry those calls' `query_id`s; `rmx telemetry --context` reports the counts by family.
5. **AC-5 Human prompts untouched.** 25.2's AC-3 pass list still injects through both commands,
   and its gated list is still gated as `ack_only` (kind checked).
6. **AC-6 The clause order.** An `<agent-message from="x">` whose body is `ok` is gated with
   `kind == "non_human"` and, under `none`, prints nothing, composite included (under ack-first
   ordering it would be `ack_only` and print the composite).
7. **AC-7 Focus follows.** Through the generated focus input command, an `<agent-message` envelope
   records no `input` ring event and leaves the graph `turn` unchanged; a human prompt increments
   it; `rmx focus rebuild --dry-run` on a ring holding `<agent-message` inputs counts them in
   `dropped_ambient`.
8. **AC-8 One predicate.** A structural test parses `src/refmatrix/`: the seven openings appear as
   string literals only in `terms.py`; `cli._is_ambient_prompt` does not exist; `stm.is_ambient_text`
   returns True for every AC-1 positive. 25.2's AC-6 ("one gate") still passes.
8b. **AC-8b One decision point.** A structural test: `NON_HUMAN_POLICY` is read only inside
   `terms.non_human_policy`; scan-prompt, the recall verb and curator status call it; the shipped
   table's curator column is `none` for every family, and its other two columns equal Q10's
   recorded answer (this leg is written at GREEN, after Q10).
8c. **AC-8c Curator status (R8).** The generated config has `rmx curator status --stdin-json` as
   its own UserPromptSubmit entry and `scan_cmd` no longer contains it; with a 30-path curator queue,
   an `<agent-message` envelope prints nothing and writes one row with `gated:
   "skipped_non_human"`; a human prompt prints the queue within `budget("curator_status")`; `rmx
   install-hooks --check` is clean.
8d. **AC-8d The arm draw (R7).** `arms.draw` is deterministic per session id and salt; over 400
   synthetic session ids the two gate cells get 200 ± 30; the SessionStart focus entry records one
   `session_arm` row; inside the period `non_human_policy` returns `full` for a `nogate` session and
   the table's value for a `gate` one; outside it, the table's value for every session; with the
   handhold rows present the nested cells are drawn and arm C never is.
9. **AC-9 Mutations that must FAIL a test:** `<agent-message` row removed from the table (AC-1,
   AC-2); tag-boundary check dropped (AC-1: `<agent-messages-log` matches); scan-prompt call site
   skipping the gate (AC-2); recall call site skipping it (AC-3); ack clause evaluated first (AC-6);
   the composite kept on `non_human` (AC-2); the gated row not written (AC-4); `cli._is_ambient_prompt`
   kept with the old three-prefix tuple and still called by the input hook (AC-7, AC-8); the
   predicate matching anywhere in the text instead of at the start (AC-1); a call site reading
   `NON_HUMAN_POLICY` directly (AC-8b); `delta` emitting a keyframe or the composite (AC-2);
   curator status left inside `scan_cmd` (AC-8c); curator's skip not counted (AC-8c); `arms.draw`
   using a random source instead of the hash (AC-8d: not deterministic); the `nogate` arm applied
   outside the period (AC-8d).

## Files to modify {#files}

| file | change |
|---|---|
| `src/refmatrix/terms.py` | `AMBIENT_PREFIXES`, `ambient_family()`; `PromptGate.kind`; `prompt_gate` checks the family first |
| `src/refmatrix/stm.py` | `is_ambient_text` delegates to `terms.ambient_family` |
| `src/refmatrix/cli.py` | delete `_is_ambient_prompt`; the input hook calls `stm.is_ambient_text`; gated recall row fields through `_RecallCall` |
| `src/refmatrix/scan.py` | `non_human` returns empty (no composite) and writes the gated row |
| `src/refmatrix/verbs.py` (`memory_recall`) | `non_human` on the `gate_thin_prompt` path |
| `src/refmatrix/telemetry.py` | `gate_family` on the rows; per-family gated counts in the hook-cost report |
| `src/refmatrix/terms.py` (policy) | `NON_HUMAN_POLICY`, `non_human_policy()`; `ambient_family(origin=…)` (R0) |
| `src/refmatrix/arms.py` (new, measurement only; deleted after R7's period) | `SESSION_ARMS`, `draw()` |
| `src/refmatrix/hooks.py` | curator status as its own entry; `HOOK_COMMAND_CHANNELS` (25.1's `hook_budget`) updated |
| `src/refmatrix/cli.py` (`curator status`, `focus hook --event session-start`) | `--stdin-json` + the gate; the `session_arm` row |
| `src/refmatrix/hook_budget.py` (25.1) | `curator_cmd` in `HOOK_COMMAND_CHANNELS` |
| `.claude/settings.json`, `.claude/rmx-hooks.json` | regenerated from Python in the task's clone |
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
| q1 | Curator status silent on non-human prompts? | ANSWERED: yes (Q9); [[#r8]] |
| q3 | Per-family behaviour on non-human turns: delta-only, full gate, or task-notifications only? | OPEN with the user (Q10); [[#policy]] maps each option; nothing ships before the answer |
| q2 | Should the live rings be rebuilt so past `<agent-message` inputs leave the focus graphs? | no: `rmx focus rebuild` stays manual; new turns follow n8 from deploy |

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation table in the implementation summary.
- Implementation summary at `workflow/implementation_summaries/task-10.4-non-human-prompt-gate.md`.
- R5's measurement file written (before at RED, after at deploy).
- Committed on branch `task-10.4-non-human-prompt-gate`; merged `--no-ff` to `master`.
