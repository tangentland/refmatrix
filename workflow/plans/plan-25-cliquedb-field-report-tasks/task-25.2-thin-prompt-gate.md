---
gmd: "0.1"
id: task-25.2-thin-prompt-gate
title: "Task 25.2: one ack-only gate, beside the shared stoplist, decides whether scan-prompt and the prompt recall inject anything; a prompt made only of acknowledgements injects nothing and is counted, and a single content word still gets its recall (bug-165)"
tags: [task, plan-25, bug-165, scan-prompt, memory-recall, stopwords, gate, verbs, cliquedb]
metadata:
  node_type: task
  status: pending
  plan: plan-25-cliquedb-field-report
  created: 2026-11-08
  updated: 2026-11-09
---

# Task 25.2: ack-only prompt gate {#root}

> Plan: [[plan-25-cliquedb-field-report]]
> Status: Pending (spec drafted 2026-11-08; revision round 1 2026-11-09, [[#rev-round-1]])
> Bug: bug-165 (cliquedb priority 2)
> Depends on: [[task-25.1-recall-hook-byte-budget]] merged (it moves the per-prompt recall into
> the verb, where this gate lives, and owns the hook generator; the after-measurement is taken on
> the packed payload); task 3.7 merged.

rel: part-of -> [[plan-25-cliquedb-field-report]]
rel: depends-on -> [[task-25.1-recall-hook-byte-budget]]
rel: depends-on -> [[task-3.7-verb-it-backlog]]
rel: derives-from -> [[bug_registry#registry]]
rel: derives-from -> [[bsd-plan25-spec-r1-2f4a1df]]
rel: depends-on -> [[feedback_reuse_shared_stoplist]]
rel: related-to -> [[task-24.2a-hook-verbs-explicit-session]]
rel: related-to -> [[task-21.1-context-usage-telemetry]]

## Why {#why}

On "a - next", "yes next" and "i - next", cliquedb's scan-prompt content block carried ~500 tokens
of unrelated save-state «NEXT» hits, and the per-prompt recall returned its LARGEST payload of the
session (29,151 B on "yes next", 2026-11-08). Nothing in either path asks whether the prompt says
anything: scan-prompt's content leg runs whenever `extract_candidates` returns any token
(`scan.py:948`, `if content and cands`), and recall embeds whatever the prompt is. A prompt made
only of acknowledgements has no topic; every hit it gets is noise. {#why-lead}

The first draft gated any prompt with fewer than two content terms. Simulated on the STM rings'
input events ([[bsd-plan25-spec-r1-2f4a1df#s4]], counts only) it gated 8.6% of refmatrix prompts
and 7.6% of cliquedb's, and about half of those were ONE content word: `push`, `deploy`, `build`,
`commit`, `littlebig`, `fold`, `status`, `dispatch`, an issue reference `#44`. Those one-word
commands are exactly where guardrail memories fire (`push` has
`feedback_push_from_dev_not_deploy`, `littlebig` has `feedback_isolate_work_in_littlebig_clones`).
Gating them would remove the recall that justifies the hook. So the gate is narrowed to ACK-ONLY
prompts (orchestrator decision 2026-11-09).

Under the shared stoplist (`terms.STOPWORDS`, re-exported as `scan._PROMPT_STOPWORDS`) "yes", "a",
"i" are stopwords and "next", "ok", "continue", "go" are not. The stoplist is function words only
by design (`scan.py:60-73`): `next`, `go`, `use` can be real concepts. A genuinely different need
goes in a separate, documented set applied IN ADDITION ([[feedback_reuse_shared_stoplist]]).

## Decisions {#decisions}

| # | decision | reason |
|---|---|---|
| g1 | ONE function `terms.prompt_gate(prompt) -> PromptGate(passed, tokens, reason)` | two call sites (scan-prompt, prompt recall) and the mod later must agree |
| g2 | The gate tokenizes on WHITESPACE, not `scan._IDENT_RE` | `#44`, `25.2`, `bug-164` must be tokens it sees; the identifier regex cannot start on `#` or a digit. No second identifier regex is introduced: the gate only asks "is every token an ack" |
| g3 | `terms.ACK_WORDS`: a documented set of acknowledgement / continuation words, applied in addition to `STOPWORDS`, used ONLY by the gate | `next` must stay a matchable concept everywhere else |
| g4 | Gated iff EVERY token (punctuation stripped, lower-cased) is in `STOPWORDS ∪ ACK_WORDS`, or is a list-marker shape (a single letter or digit, a roman numeral up to `x`, optionally followed by `.` / `)` / `-`, or a bare `-` / `—`), or is empty | a single content word, an issue or task number, or any identifier passes |
| g5 | The gate suppresses prompt-DERIVED output only: concept bundles, the content leg, helix, the prompt recall. The STM topic composite (session-derived, own `--composite-every` cadence) is not gated | on "yes next" the session's current topics are the relevant thing; AC-5 measures it |
| g6 | A gated call prints nothing and is counted | a one-line stub costs tokens on every ack; the count lives in telemetry ([[#r4]]) |

## Requirements {#requirements}

1. **R1 The gate.** `terms.prompt_gate(prompt: str) -> PromptGate`, a frozen dataclass
   `(passed: bool, tokens: tuple[str, ...], reason: str)`. Tokens are the whitespace-split prompt
   with leading/trailing `.,;:!?"'()[]` stripped and lower-cased. `passed` is False iff g4 holds.
   `reason` is `"ok"` or `"ack-only: <n> tokens"` (never the tokens themselves: telemetry must not
   carry prompt text, [[feedback_no_raw_prompts_in_public_repo]]). {#r1}
2. **R2 `ACK_WORDS`.** In `terms.py` next to `STOPWORDS`, documented as gate-only. Initial
   membership, each with the motivating prompt shape in a comment: `ok okay k kk next continue cont
   go ahead proceed sure thanks thank ty please pls yep yeah yup yes y nope lgtm approved agree
   agreed done fine good great cool right correct exactly perfect nice option`. A word is added
   only with the prompt that motivated it named (shape only, no raw text). A word that is also a
   plausible command (`push`, `commit`, `deploy`, `build`, `status`) is NEVER added. {#r2}
3. **R3 Call sites.**
   - `scan.scan_prompt(...)` calls `prompt_gate(prompt)` first. Not passed → it returns the
     composite alone (when asked for and its cadence fires) or the empty string; no
     `match_concepts`, no content leg, no helix, no rerank.
   - Prompt recall: `verbs.memory_recall(..., gate_thin_prompt: bool = False)`. 25.1 R5 makes the
     per-prompt argv call the verb, so the CLI's `--stdin-json` passes `True` and the gate runs in
     the verb. Not passed → no retrieval, empty payload, exit 0. An explicit query
     (`rmx memory recall "next"`) is never gated. When 24.2a lands, `trigger="prompt"` implies
     `gate_thin_prompt=True`.
   - No other module re-implements the rule (AC-6). {#r3}
4. **R4 Counted, never silent.** Every gated invocation writes the call's existing telemetry row
   with `gated: "ack-only"`, `gate_tokens: <n>` and `retrieved: 0`: scan-prompt's `query.log` row
   and the recall channel's 21.1 row (`prompt_recall`). The hook-cost report shows a gated count
   per channel. {#r4}
5. **R5 Gate rate and noise, measured.** Before GREEN, re-run the gate over every input event in
   the local STM rings of refmatrix and cliquedb (counts only: gated / total, and a count of gated
   prompts whose tokens include a word outside `STOPWORDS ∪ ACK_WORDS`, which must be 0 by
   construction). Record the rate beside the first draft's 8.6% / 7.6%. After deploy, record bytes
   per UserPromptSubmit event (scan-prompt + recall summed) for ack prompts and real prompts, and
   whether rerank ran. If real prompts still carry save-state «NEXT» content hits with rerank live,
   log a new bug row (not fixed here). {#r5}

## Acceptance criteria {#acceptance}

Run in 23.0's sandbox on 25.1's fixture store, extended with 6 synthetic save-state-shaped memory
rows whose bodies carry a «NEXT» section, so scan-prompt's content leg has the noise cliquedb saw.
Run through the GENERATED UserPromptSubmit commands from `hooks._claude_hook_block(...)` with
`bash -c` and the envelope on stdin. At RED time, verify scan's content leg reaches those rows on
the fixture (the bsd could not trace how cliquedb's save-states reached it); if it does not, the
fixture is changed until AC-1 is RED, and the route is recorded. {#acceptance-lead}

1. **AC-1 scan-prompt on a bare ack.** The generated scan-prompt command on "yes next" prints a
   content block naming at least one fixture save-state at HEAD (RED, bytes recorded); after, 0
   bytes of concept / content / helix output (composite disabled; AC-5 covers it enabled).
2. **AC-2 recall on a bare ack.** The generated per-prompt recall command on "yes next" prints hits
   at HEAD (RED); after, stdout is empty and exit is 0.
3. **AC-3 The table.** Asserted through BOTH generated commands (scan-prompt: prompt-derived
   output present / absent; recall: retrieval ran / did not, read from the R4 row).
   - Gated: `yes next`, `a - next`, `i - next`, `ok`, `please continue`, `next.`, `yes.`, `go
     ahead`, `thanks!`, `1 - next`, `b)`, `—`.
   - Passed (the bsd's measured false-gate set, single content words): `push`, `deploy`, `build`,
     `commit`, `purge`, `reap`, `ugrep`, `littlebig`, `refmatrix`, `hooks`, `fold`, `status`,
     `dispatch`, `bsd`, `spec`, `vocab`, `login`, `#44`; and `do 25.2`, `bug-164?`, `ScanPrompt`,
     `fix rmx_context timeout`, `why is the daemon slow`, `yes, push`.
   - At HEAD every gated row fails (nothing is gated).
4. **AC-4 Counted.** After AC-1..AC-3, `query.log` and the recall rows carry exactly one
   `gated: "ack-only"` row per gated invocation per channel and no prompt text in `reason` (RED:
   the field does not exist at HEAD).
5. **AC-5 Composite survives.** With the composite enabled and a session ring holding two topics,
   "yes next" prints the composite block and nothing else; its bytes are recorded.
6. **AC-6 One gate.** A structural test parses `src/refmatrix/` and fails if any module other than
   `terms.py` defines an ack-word set, or if scan-prompt or the recall verb decides "thin prompt"
   without calling `terms.prompt_gate` (the bypass check [[feedback_converge_repeated_shapes]]
   asks for).
7. **AC-7 Verb parity.** `verbs.memory_recall(query="yes next", gate_thin_prompt=True, pack=True)`
   returns empty text and the gated reason; the parity test lists `gate_thin_prompt` with the CLI's
   `--stdin-json` as its twin.
8. **AC-8 Mutations that must FAIL a test:** gate on "< 2 content terms" (AC-3: `push` gated);
   `ACK_WORDS` not applied (AC-3: `please continue` passes); punctuation not stripped (AC-3:
   `next.` passes); list-marker shape not recognised (AC-3: `a - next` passes); adding `push` to
   `ACK_WORDS` (AC-3); the recall call site skipping the gate (AC-2); the gated branch not writing
   its row (AC-4); gating the composite (AC-5).

## Measurement {#measurement}

Rows appended to `workflow/measurements/plan-25-hook-bytes.md`: bytes per UserPromptSubmit event,
scan-prompt + recall, HEAD vs GREEN, for each AC-3 prompt, three runs each; R5's gate rate on the
local rings (counts only) beside the first draft's; R5's live counts after deploy.

## Files to modify {#files-to-modify}

| file | change |
|---|---|
| `src/refmatrix/terms.py` | `ACK_WORDS`, `PromptGate`, `prompt_gate()` |
| `src/refmatrix/scan.py` | `scan_prompt` gates first; gated telemetry row |
| `src/refmatrix/verbs.py` (`memory_recall`) | `gate_thin_prompt` |
| `src/refmatrix/cli.py` (`_memory_recall_impl`) | `--stdin-json` passes `gate_thin_prompt=True` to the verb; gated row through `_RecallCall` |
| `src/refmatrix/telemetry.py` | `gated` / `gate_tokens` fields; per-channel gated count in the hook-cost report |
| `tests/test_task25_2_prompt_gate.py` (new) | AC-1..AC-8 |
| `tests/test_verb_parity.py` | `gate_thin_prompt` twin |
| `workflow/bug_registry.md` | bug-165 → fixed at merge |

## Test strategy {#test-strategy}

- RED first on AC-1, AC-2, AC-3, AC-4 at HEAD (after 25.1 merges); recorded.
- No mock of the gate, scan-prompt, recall or telemetry; AC-3's table runs through the generated
  commands, because a unit-green gate that one call site skips is the failure this repo has had
  four times.
- Fixture save-state rows are synthetic; no cliquedb prompt or body is committed; R5 reads the
  local rings in-process and writes counts only.

## Open decisions {#open-decisions}

| # | decision | recommendation |
|---|---|---|
| o1 | Empty output vs a one-line stub on a gated prompt | empty; the count lives in telemetry (g6) |
| o2 | Gate the STM composite too | no (g5); revisit if AC-5's bytes on an ack exceed ~1,500 B |
| o3 | Number-like tokens (`25.2`, `#44`, `bug-164`) | pass: they are not ack words (g4) |
| o4 | `ACK_WORDS` membership owner | `terms.py`, one comment per addition; command-like words are never added |
| o5 | `gate_thin_prompt` as an explicit verb param, or wait for 24.2a's `trigger` | explicit param now, implied by `trigger="prompt"` later; 24.2a's d9 gains one line |

## Revision round 1 (2026-11-09) {#rev-round-1}

Answers [[bsd-plan25-spec-r1-2f4a1df]] and the orchestrator's decisions of 2026-11-09.

| finding | change | anchor |
|---|---|---|
| S4 false gates on single-topic commands | gate narrowed to ACK-ONLY prompts (every token a stopword, an ACK_WORD or a list marker); whitespace tokens so `#44` is seen; AC-3 carries the bsd's measured false-gate set as must-pass rows; R5 re-measures the gate rate on the local rings (counts only); `ahead`, `option` added to `ACK_WORDS`; command words barred from it | [[#why]], [[#decisions]] g2/g4, [[#r1]], [[#r2]], [[#r5]], AC-3, AC-8 |
| S1 (25.2 half) the CLI does not call the verb | the gate is reached because 25.1 R5 moves the per-prompt rows into the verb; R3 says so | [[#r3]] |
| q5 / o3 | o3 restated under the ack-only rule | [[#open-decisions]] |
