---
gmd: "0.1"
id: task-26.9-impression-patterns
title: "Task 26.9: ch-bsd impressions gain a pattern layer, derived by compile, and the ledger becomes a rolling window"
tags: [task, plan-26, ch-bsd, impressions, compile, subjects, patterns]
metadata:
  node_type: task
  status: pending
  plan: plan-26-memory-organisation
---

# Task 26.9: impression patterns {#root}

> Plan: [[plan-26-memory-organisation]]
> Status: Pending
> Depends on: [[task-26.6-compile-subject-hygiene]] (labels, retirement), [[task-26.1-layout-module-and-index-walk]] (`impressions/` is a type folder)

rel: part-of -> [[plan-26-memory-organisation]]
rel: depends-on -> [[task-26.6-compile-subject-hygiene]]
rel: depends-on -> [[task-26.1-layout-module-and-index-walk]]
rel: derives-from -> [[refmatrix/adr-0002-subject-memory-container]]
rel: reinforces -> [[feedback_decay_never_loses_knowledge]]
rel: reinforces -> [[feedback_prefer_existing_infra]]

## Why {#why}

User, 2026-11-08: "yes add the impression work" — after asking whether the impressions need
another layer. Measured state at `2f4a1df`: {#why-state}

- `workflow/bullshit/IMPRESSIONS.md` is 290 lines / 177 bullets. `ch-bsd.md#update-impressions-md`
  caps it at 50 lines ("summarize the oldest 10 into one consolidated bullet"); the cap has been
  applied only sporadically, so every run reads the whole ledger at step 0b.
- `memory/impressions/` holds 67 durable lessons with 125 `rel:` edges among them
  (amends / reinforces / related-to), and 149 run reports sit under them as evidence.
- Many lessons are repeated sightings of a few families (busy≠absent, partial bound, quoted-line
  sibling, count cannot see order, guard cannot fire, measured on a path users do not run, counter
  read at the wrong instant). Escalation by family is in the agent's procedure
  (`ch-bsd.md` "a finding that matches a pattern … gets escalated") but the families exist only
  implicitly across the ledger.

The missing layer is a small set of PATTERN nodes above the lessons — the same derived-subject
mechanism plan-26 already repairs for memory (ADR-0002 container, `part-of` edges, multi-membership).
Not hand-built folders, not a second clustering path.

## Requirements {#requirements}

1. **R1 Derive.** `rmx memory compile` runs over the `impression` mtype (scoped selection, same
   code path as 26.6 — no second clusterer) and produces candidate pattern subjects with
   `part-of` edges to member impressions. A lesson may belong to several patterns. {#r1}
2. **R2 Curate.** Each accepted pattern becomes a GMD memory `impressions/pattern_bsd_<slug>.md`
   (`metadata.type: impression`, tag `pattern`) carrying: the rule (one paragraph), a check list
   ("when you see X, look at Y"), `rel: part-of` edges FROM its members (or `catalogs` edges to
   them), and a sighting count derived from member count + ledger mentions. The rule text is
   written by ch-bsd in a dedicated run after 26.8 (user decision 2026-11-08, see [[#q1-decided]]), never auto-generated; compile only proposes membership. {#r2}
3. **R3 Ledger window.** `IMPRESSIONS.md` keeps the last ~20 runs' bullets; older bullets are folded
   into the pattern they belong to (pattern doc gains a "sightings" line with date + report link) or,
   if unmatched, into one consolidated bullet — never deleted without a home. A bullet's history is
   reachable from its pattern (decay demotes, never loses — [[feedback_decay_never_loses_knowledge]]). {#r3}
4. **R4 Procedure.** `.claude/agents/ch-bsd.md` (and the shipped template under
   `src/refmatrix/templates/agents/`) step 0b reads pattern docs first, then the ledger window;
   the escalation rule cites a pattern id and bumps its sighting count; the 50-line cap is enforced
   by the fold in R3. {#r4}
5. **R5 Graph.** Patterns ingest through the normal bridge and are reachable by
   `rmx memory recall --type impression` and `rmx context <pattern-id>`; no new store table. {#r5}

## Acceptance criteria {#acceptance}

1. **AC-1** On a throwaway memory dir seeded with ≥12 impression fixtures forming ≥3 families
   (multi-membership in at least one), the compile run proposes ≥3 candidate patterns whose
   membership matches the planted families (precision/recall reported, threshold pre-registered
   in the test before running). RED at HEAD: compile has no mtype-scoped selection. {#ac-1}
2. **AC-2** A pattern doc written per R2 lints with zero errors and is returned by
   `rmx memory recall` for a phrase unique to its rule text (recall, not `memory get` —
   [[feedback_verify_memory_by_recall_not_get]]). {#ac-2}
3. **AC-3** The fold (R3) on a copy of the real `IMPRESSIONS.md` leaves ≤50 lines, and every folded
   bullet's text is findable in exactly one pattern doc or the consolidated bullet (a checker
   enumerates bullets before and after). {#ac-3}
4. **AC-4** The ch-bsd procedure change ships in both the repo agent file and the template, and a
   test asserts step 0b names the pattern location. {#ac-4}
5. **AC-5** Live: after 26.8, the real refmatrix impressions compile; the user (or ch-bsd) accepts
   the curated patterns; the ledger fold runs once; the next ch-bsd run reports which pattern ids
   it escalated against. {#ac-5}

## Files to modify {#files-to-modify}

| File | Change |
|---|---|
| `src/refmatrix/consolidate.py` (compile) | mtype-scoped selection for compile (if 26.6 does not already add it) |
| `src/refmatrix/cli.py`, `src/refmatrix/verbs.py`, `src/refmatrix/mcp.py` | `memory compile --type` option, verb-first, parity |
| `.claude/agents/ch-bsd.md`, `src/refmatrix/templates/agents/ch-bsd.md` | step 0b + escalation + fold procedure |
| `workflow/bullshit/IMPRESSIONS.md` | the one-time fold (R3) |
| `memory/impressions/pattern_bsd_*.md` | curated pattern docs (live dir, after 26.8) |

## Test strategy {#test-strategy}

Throwaway memory dir + throwaway store under a short `mkdtemp()` root; real compile through the
CLI/MCP verb (no mocking compile). The fold checker runs on a copy of the real ledger, never the
live file, until AC-5. Pre-register AC-1's thresholds in the test file before the first run
([[feedback_go_no_go_ranges_not_predrop]]).

## Open questions {#open-questions}

1. **Who writes the rule text for each pattern?** DECIDED (user, 2026-11-08): ch-bsd writes the
   patterns in a dedicated run right after 26.8 lands (AC-5); the user reviews them. {#q1-decided}
2. **Should project memories (not only impressions) get the same pattern layer?** Recommend no for
   now — 26.7's subject-grouped MEMORY.md covers them; revisit after AC-5.
