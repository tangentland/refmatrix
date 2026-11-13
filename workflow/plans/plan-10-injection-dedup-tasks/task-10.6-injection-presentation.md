---
gmd: "0.1"
id: task-10.6-injection-presentation
title: "Task 10.6: injection presentation — every injected item carries its kind label, generic headers become kind-labelled ones, rank order kept; the STM composite sends `<id> rev N unchanged` when its content has not changed"
tags: [task, plan-10, scan-prompt, memory-recall, pack, composite, presentation]
metadata:
  node_type: task
  status: pending
  plan: plan-10-injection-dedup
  created: 2026-11-13
---

# Task 10.6: injection presentation {#root}

> Plan: [[plan-10-injection-dedup]]
> Status: Pending (drafted 2026-11-13 on presentation rules the user agreed the same day; ch-bsd
> spec review next)
> Depends on: [[task-25.1-recall-hook-byte-budget]] merged (the pack and its hook lines);
> [[task-10.3-plan-10-injection-dedup]] (the `.emitted` directory and the marker, for the composite
> part). Lands before [[task-10.2-plan-10-injection-dedup]], which labels its names line with this
> task's function.

rel: part-of -> [[plan-10-injection-dedup]]
rel: depends-on -> [[task-25.1-recall-hook-byte-budget]]
rel: depends-on -> [[task-10.3-plan-10-injection-dedup]]
rel: implements -> [[exploration-session-phased-context#vi-unchanged]]
rel: realizes -> [[task-19.6-phased-context-and-topic-cache]]
rel: depends-on -> [[feedback_converge_repeated_shapes]]

## Why {#why}

An injected item today says what it is only by its name; a feedback rule and a stray code symbol
look alike, and the headers ("refmatrix content matches for prompt", "=== context for …") say
nothing. Agreed rules (user, 2026-11-13): label every item by kind, label the headers, keep the
most important item first. And the STM composite is re-sent near-identical on every scan-prompt
that carries it: whole-block versioning fits it, although it failed for the per-prompt lists —
10.5's Table A reading (0.00-3.32%) was measured on the two per-prompt ids only
([[plan-10-injection-dedup#context-table-a]]), never on the composite. {#why-lead}

## Decisions {#decisions}

| # | decision | reason |
|---|---|---|
| p1 | ONE label function, `telemetry.kind_label(kind, mtype, path) -> str`, beside `telemetry.event_kind`: memory `feedback*` / `guardrail*` → `rule`; memory `decision*`, or a doc under the store's ADR dir (`ADR_DIR`, `docs/adr/` here) → `decision`; memory `subject` → `subject`; any other memory → `memory`; `doc`, `code`, `concept` as they are. `composite._kind_of_type` calls it | one map, not three (`event_kind`, `_kind_of_type`, a renderer copy) ([[feedback_converge_repeated_shapes]]) |
| p2 | Labels never reorder: 25.1's rank order and scan's render order stand | the agreed rule: the most important item stays first |
| p3 | The kind-labelled header applies to scan-prompt's render only; `rmx context` keeps `=== context for …` | `cli.py:9567` counts `=== context for` to set a row's `cardinality`; the explicit pull is out of scope |
| p4 | The composite's version state is its OWN file, `stm/<session>.emitted/stm-topic-composite.json` (`{schema: 1, rev, content_sha}`), written only by the scan-prompt hook after its print; it does NOT ride 10.2's `scan_prompt.json` | same writer, but a separate file keeps 10.6 independent of 10.2's schema and order, and is where 19.6's block files go ([[task-19.6-phased-context-and-topic-cache#split-plan-10]]); it needs 10.3's directory helper and marker, nothing else of 19.6 |
| p5 | `content_sha` hashes the composite with its `metadata: {turn: N}` line removed | the turn changes every prompt; with it the block would never be unchanged (19.6 R9 keeps turn, count and age out of the collapsed block for the same reason) |
| p6 | The composite is versioned as ONE block now; 19.6 R9 later splits it into `stm-topic-expanded` / `stm-topic-collapsed`, each versioned on its own, and replaces this file | 19.6 owns the composite's shape; this task uses only R5's line and R8a's marker |

## Requirements {#requirements}

1. **R1 Item labels.** 25.1's hook line becomes `- [<label>] <name> — <title> — <hook>  (<fetch>)`;
   scan-prompt's entry line `  [<label>] <name>  [<kind>]…` and anchor line `anchor: [<label>]
   <name>`; the pack and the scan render fit as before (labels count in the budget). {#r1}
2. **R2 Headers.** scan-prompt's content header becomes `# prompt matches: <n> rule · <n> memory ·
   <n> doc · <n> code` (non-zero kinds only, in that order); its per-symbol bundle header `=== <label>
   <name> ===` (`render_text_spans(b, header_style="kind")`); 25.1's pack header adds the kind counts
   after the hit count. {#r2}
3. **R3 The composite.** scan-prompt computes the composite, its `content_sha` (p5) and reads the
   composite state and `stm.last_marker` (10.3). Same sha as the last emitted rev and no marker
   since → it emits the one line `stm-topic-composite rev N unchanged` (N = that rev). Otherwise
   it emits the full composite with `metadata: {turn: T, rev: N+1}` and the line `supersedes earlier
   revs of stm-topic-composite`, and records the new rev after the print. A missing or unreadable
   state file → full (plus one stderr line when unreadable); an unreadable marker → full. {#r3}
4. **R4 Counted.** scan-prompt's row carries `composite: "full" | "unchanged" | null`,
   `composite_rev`, and the labelled item counts; `rmx telemetry --context` shows the composite's
   unchanged share. After deploy, that share is recorded against 19.6 Table A's bands as a check
   (a share under 3% means the line rarely fires; recorded, nothing reverted). {#r4}

## Acceptance criteria {#acceptance}

Through the GENERATED UserPromptSubmit commands in 23.0's sandbox on 25.1's fixture. {#acceptance-lead}

1. **AC-1 Labels.** A fixture with one feedback, one guardrail, one decision memory, one ADR doc,
   one project memory, a doc and a code symbol: each line carries `rule`, `rule`, `decision`,
   `decision`, `memory`, `doc`, `code`; the order equals the unlabelled run's.
2. **AC-2 Headers.** scan-prompt's output has no `refmatrix content matches for prompt` and no
   `=== context for`; `rmx context X` still prints `=== context for` and its row's `cardinality` is
   unchanged.
3. **AC-3 Budget.** At 25.1's budgets (2,000 / 4,000 / 9,000 B) every payload stays within it.
4. **AC-4 Composite unchanged.** Two prompts whose composite differs only in turn: the second
   prints `stm-topic-composite rev 1 unchanged`; a third with a changed member prints rev 2 in full
   with the `supersedes` line; after the generated PreCompact marker entry the next is full.
5. **AC-5 Composite state.** Missing → full; holding `{` → full plus one stderr line, exit 0.
6. **AC-6 One label map.** A structural test: the label literals live only in `telemetry.kind_label`;
   `composite._kind_of_type` calls it.
7. **AC-7 Mutations that must FAIL a test:** labels reorder items (AC-1); `rule` missing for
   `guardrail` (AC-1); `rmx context`'s header changed (AC-2); the turn line kept in the hash (AC-4:
   never unchanged); the marker ignored (AC-4); an unreadable state read as unchanged (AC-5).

## Files to modify {#files}

| file | change |
|---|---|
| `src/refmatrix/telemetry.py` | `kind_label` |
| `src/refmatrix/recall_pack.py` (25.1) | labelled hook lines, header kind counts |
| `src/refmatrix/context.py` (`render_text_spans`) | `header_style="kind"`, labelled entry and anchor lines |
| `src/refmatrix/scan.py` | the content header; the composite's rev / unchanged; row fields |
| `src/refmatrix/composite.py` | `_kind_of_type` → `telemetry.kind_label`; the rev in its header |
| `src/refmatrix/stm.py` | composite state read / write in `.emitted/` (10.3's helper) |
| `tests/test_task10_6_presentation.py` (new) | AC-1..AC-7 |

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation table in the implementation summary.
- Implementation summary at `workflow/implementation_summaries/task-10.6-injection-presentation.md`.
- Committed on branch `task-10.6-injection-presentation`; merged `--no-ff` to `master`.
