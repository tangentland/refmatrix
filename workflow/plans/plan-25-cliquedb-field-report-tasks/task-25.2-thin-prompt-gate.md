---
gmd: "0.1"
id: task-25.2-thin-prompt-gate
title: "Task 25.2: one thin-prompt gate, beside the shared stoplist, decides whether scan-prompt and the prompt recall inject anything; a bare ack injects nothing and is counted (bug-165)"
tags: [task, plan-25, bug-165, scan-prompt, memory-recall, stopwords, gate, verbs, cliquedb]
metadata:
  node_type: task
  status: pending
  plan: plan-25-cliquedb-field-report
  created: 2026-11-08
  updated: 2026-11-08
---

# Task 25.2: thin-prompt gate {#root}

> Plan: [[plan-25-cliquedb-field-report]]
> Status: Pending (spec drafted 2026-11-08)
> Bug: bug-165 (cliquedb priority 2)
> Depends on: [[task-25.1-recall-hook-byte-budget]] merged (same recall emission path and hook
> generator; the after-measurement is taken on the packed payload); task 3.7 merged.

rel: part-of -> [[plan-25-cliquedb-field-report]]
rel: depends-on -> [[task-25.1-recall-hook-byte-budget]]
rel: depends-on -> [[task-3.7-verb-it-backlog]]
rel: derives-from -> [[bug_registry#registry]]
rel: depends-on -> [[feedback_reuse_shared_stoplist]]
rel: related-to -> [[task-24.2a-hook-verbs-explicit-session]]
rel: related-to -> [[task-21.1-context-usage-telemetry]]

## Why {#why}

On "a - next", "yes next" and "i - next", cliquedb's scan-prompt content block carried ~500 tokens
of unrelated save-state «NEXT» hits (`feedback-mpop-master-schedule`, `savestate_2115785568fc`, …),
and the per-prompt recall returned its LARGEST payload of the session (29,151 B on "yes next",
2026-11-08). Nothing in either path asks whether the prompt says anything: scan-prompt's content
leg runs whenever `extract_candidates` returns any token (`scan.py:948`, `if content and cands`),
and recall embeds whatever the envelope's prompt is. A bare ack has no topic; every hit it gets is
noise by construction, whatever the ranker does. {#why-lead}

Under the shared stoplist (`terms.STOPWORDS`, re-exported as `scan._PROMPT_STOPWORDS`, 86 entries)
"yes", "a", "i" are stopwords and "next", "ok", "continue", "please", "go" are not (read
2026-11-08). The list is deliberately function-words only: content words like `get`, `use`, `next`
can be real concepts (comment at `scan.py:60-73`). So a 2-term rule over the stoplist alone gates
"yes next" but passes "please continue". [[feedback_reuse_shared_stoplist]] says what to do with a
genuinely different need: a separate, documented set applied IN ADDITION to the shared one.

Rerank works again (bug-162, 0.80.2). cliquedb's report predates that, so this task measures the
noise level after the gate with rerank live, rather than assuming the gate is the whole story.

## Decisions {#decisions}

| # | decision | reason |
|---|---|---|
| g1 | ONE function `terms.prompt_gate(prompt) -> PromptGate(passed, terms, reason)` | two call sites (scan-prompt, prompt recall) and a future third (24.2a's `rmx_scan_prompt` and the mod) must agree on what a thin prompt is |
| g2 | The tokenizer moves with it: `scan._IDENT_RE` is hoisted to `terms` and re-exported from `scan` | a gate with its own regex is a second tokenizer; `terms` cannot import `scan` (scan imports terms) |
| g3 | `terms.ACK_WORDS`: a small documented set of acknowledgement / continuation words, applied in addition to `STOPWORDS`, used ONLY by the gate | `next` must stay a matchable concept everywhere else |
| g4 | Pass iff ≥ 2 content terms OR ≥ 1 identifier-shaped token | `rmx_context?`, `ScanPrompt`, `bug-164` and `25.2` are one-token prompts with a topic |
| g5 | The gate suppresses prompt-DERIVED output only: concept bundles, the content leg, helix, the prompt recall. The STM topic composite (session-derived, its own `--composite-every` cadence) is not gated | on "yes next" the session's current topics are the most relevant thing to say, and they are not keyed on the prompt; AC-5 measures it |
| g6 | A gated call prints nothing and is counted | a one-line stub costs tokens on every ack; the count goes to telemetry so the gate is never silent ([[#r4]]) |

## Requirements {#requirements}

1. **R1 The gate.** `terms.prompt_gate(prompt: str) -> PromptGate` where `PromptGate` is a frozen
   dataclass `(passed: bool, terms: tuple[str, ...], reason: str)`. Content terms are the
   candidates of `terms.IDENT_RE` (hoisted, g2) after stripping trailing `.,;:!?` FOR THE GATE ONLY
   (the scanner's own trailing-dot behaviour, `scan._strip_trailing_punct`, is unchanged), lower-
   cased, not in `STOPWORDS ∪ ACK_WORDS`, length ≥ 2. Identifier-shaped: contains an interior `_`,
   `.`, `::`, `/` or `-` followed by an alphanumeric, or internal capitals, or a digit, or matches
   `\d+(\.\d+)+` (a task / version number the identifier regex cannot start on). `passed` iff
   `len(content terms) ≥ 2` or any token is identifier-shaped. `reason` is `"ok"`,
   `"thin-prompt: 1 content term (next)"` or `"thin-prompt: 0 content terms"`. {#r1}
2. **R2 `ACK_WORDS`.** In `terms.py` next to `STOPWORDS`, documented as gate-only. Initial
   membership: `ok okay k next continue cont go proceed sure thanks thank ty please pls yep yeah
   yup nope lgtm approved agree agreed done fine good great cool right correct exactly`. Single
   letters are already excluded by the length rule. A word is added only with the prompt that
   motivated it named in a comment. {#r2}
3. **R3 Call sites.**
   - `scan.scan_prompt(...)` calls `prompt_gate(prompt)` first. Not passed → it returns the
     composite alone (when the caller asked for one and its cadence fires) or the empty string;
     no `match_concepts`, no content leg, no helix, no rerank.
   - Prompt recall: `verbs.memory_recall(..., gate_thin_prompt: bool = False)`; the CLI's
     `--stdin-json` passes `True`. Not passed → no retrieval runs, the payload is empty, exit 0.
     An explicit query (`rmx memory recall "next"`) is never gated. When 24.2a lands,
     `trigger="prompt"` implies `gate_thin_prompt=True` (recorded here so 24.2a's d9 reads it).
   - No other module re-implements the rule ([[#acceptance]] AC-6). {#r3}
4. **R4 Counted, never silent.** Every gated invocation writes the call's existing telemetry row
   with `gated: "thin-prompt"`, `gate_terms: <n>` and `retrieved: 0`: scan-prompt's `query.log`
   row and the recall channel's 21.1 row (`prompt_recall`). `rmx telemetry` (the existing
   hook-cost report) shows a gated count per channel. The prompt text itself is never logged
   beyond what 21.1 already records (its hash). {#r4}
5. **R5 Noise after the gate, measured.** On the fixture and, after deploy, on the cliquedb store
   (read-only, counts and bytes only), record for each ack prompt and each real prompt: bytes per
   UserPromptSubmit event (scan-prompt + recall summed), content-hit count, and whether rerank ran.
   If real (non-ack) prompts still carry save-state «NEXT» content hits with rerank live, that is
   logged as a new bug row, not fixed in this task. {#r5}

## Acceptance criteria {#acceptance}

Run in 23.0's sandbox on 25.1's fixture store (extended with 6 synthetic save-state-shaped memory
rows whose bodies carry a «NEXT» section, typed correctly AND one mis-typed, so the scan-prompt
content leg has the noise cliquedb saw), through the GENERATED UserPromptSubmit commands taken from
`hooks._claude_hook_block(...)`, run with `bash -c` and the envelope on stdin. {#acceptance-lead}

1. **AC-1 scan-prompt on a bare ack.** The generated scan-prompt command on "yes next" prints a
   content block naming at least one fixture save-state at HEAD (RED, bytes recorded); after, it
   prints 0 bytes of concept / content / helix output (with the composite disabled in the fixture
   config; AC-5 covers it enabled).
2. **AC-2 recall on a bare ack.** The generated per-prompt recall command on "yes next" prints
   hits at HEAD (RED); after, stdout is empty and exit is 0.
3. **AC-3 The table.** Gated: `yes next`, `a - next`, `i - next`, `ok`, `please continue`,
   `next.`, `yes.`, `go ahead`, `thanks!`. Passed: `fix rmx_context timeout`, `what does
   memory_recall do`, `do 25.2`, `bug-164?`, `ScanPrompt`, `explain the hub watchdog`,
   `why is the daemon slow`. Asserted through BOTH generated commands (scan-prompt: prompt-derived
   output present / absent; recall: retrieval ran / did not, read from the R4 telemetry row). At
   HEAD every gated row fails.
4. **AC-4 Counted.** After AC-1..AC-3, `query.log` and the recall rows carry exactly one
   `gated: "thin-prompt"` row per gated invocation per channel (RED: the field does not exist at
   HEAD).
5. **AC-5 Composite survives.** With the fixture's composite enabled and a session ring holding
   two topics, "yes next" prints the composite block and nothing else; its bytes are recorded in
   the measurement table.
6. **AC-6 One gate.** A structural test parses `src/refmatrix/` and fails if any module other than
   `terms.py` defines `ACK_WORDS`-like word sets or calls `IDENT_RE` for a gate decision outside
   `prompt_gate`; both call sites reference `terms.prompt_gate` (the bypass check that
   [[feedback_converge_repeated_shapes]] asks for).
7. **AC-7 Verb parity.** `verbs.memory_recall(query="yes next", gate_thin_prompt=True, pack=True)`
   returns empty text and the gated reason; the parity test lists `gate_thin_prompt` with the CLI's
   `--stdin-json` as its twin.
8. **AC-8 Mutations that must FAIL a test:** threshold 2 → 1 (AC-3: `yes next` passes); `ACK_WORDS`
   not applied (AC-3: `please continue` passes); trailing punctuation not stripped for the gate
   (AC-3: `next.` reads as dotted and passes); the recall call site skipping the gate (AC-2);
   the gated branch not writing the telemetry row (AC-4); gating the composite (AC-5).

## Measurement {#measurement}

Rows appended to `workflow/measurements/plan-25-hook-bytes.md` (created by 25.1): bytes per
UserPromptSubmit event, scan-prompt + recall, HEAD vs GREEN, for each AC-3 prompt, three runs each;
plus R5's live counts after deploy.

## Files to modify {#files-to-modify}

| file | change |
|---|---|
| `src/refmatrix/terms.py` | `IDENT_RE` (hoisted), `ACK_WORDS`, `PromptGate`, `prompt_gate()` |
| `src/refmatrix/scan.py` | re-export `_IDENT_RE` from `terms`; `scan_prompt` gates first; gated telemetry row |
| `src/refmatrix/verbs.py` (`memory_recall`) | `gate_thin_prompt` |
| `src/refmatrix/cli.py` (`_memory_recall_impl`) | `--stdin-json` passes `gate_thin_prompt=True`; gated row through `_RecallCall` |
| `src/refmatrix/telemetry.py` | `gated` / `gate_terms` fields; per-channel gated count in the hook-cost report |
| `tests/test_task25_2_prompt_gate.py` (new) | AC-1..AC-8 |
| `tests/test_verb_parity.py` | `gate_thin_prompt` twin |
| `workflow/bug_registry.md` | bug-165 → fixed at merge |

## Test strategy {#test-strategy}

- RED first on AC-1, AC-2, AC-3, AC-4 at HEAD (after 25.1 merges); recorded.
- No mock of the gate, scan-prompt, recall or telemetry; the gate's unit table (AC-3) is ALSO run
  through the generated commands, because a unit-green gate that one call site skips is the
  failure this repo has had four times.
- The fixture's save-state rows are synthetic; no cliquedb prompt or body is committed.

## Open decisions {#open-decisions}

| # | decision | recommendation |
|---|---|---|
| o1 | Empty output vs a one-line stub on a gated prompt | empty; the count lives in telemetry (g6) |
| o2 | Gate the STM composite too | no (g5); revisit if AC-5's bytes on an ack exceed ~1,500 B |
| o3 | Count `25.2`-style numbers as identifier-shaped | yes; "do 25.2" names a task and recall should find it |
| o4 | `ACK_WORDS` membership owner | `terms.py` with a comment per addition; reviewed like the stoplist |
| o5 | `gate_thin_prompt` as an explicit verb param, or wait for 24.2a's `trigger` | explicit param now, implied by `trigger="prompt"` later; 24.2a's d9 table gains one line |
