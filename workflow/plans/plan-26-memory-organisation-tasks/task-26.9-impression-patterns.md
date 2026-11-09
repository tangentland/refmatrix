---
gmd: "0.1"
id: task-26.9-impression-patterns
title: "Task 26.9: ch-bsd impressions gain a pattern layer, derived by the scoped compile, and the ledger becomes a rolling window"
tags: [task, plan-26, ch-bsd, impressions, compile, subjects, patterns]
metadata:
  node_type: task
  status: pending
  plan: plan-26-memory-organisation
  updated: 2026-11-09
---

# Task 26.9: impression patterns {#root}

> Plan: [[plan-26-memory-organisation]]
> Status: Pending
> Depends on:
> - [[task-26.6-compile-subject-hygiene]]: scope-aware compile R-A, the `memory_compile` verb, and the `stale` mark.
> - [[task-26.1-layout-module-and-index-walk]]: `impressions/` is a type folder.
> - Live AC-5 runs after 26.8. AC-5 does NOT gate plan-26's close (ch-bsd r1 #m9).

rel: part-of -> [[plan-26-memory-organisation]]
rel: depends-on -> [[task-26.6-compile-subject-hygiene]]
rel: depends-on -> [[task-26.1-layout-module-and-index-walk]]
rel: derives-from -> [[refmatrix/adr-0002-subject-memory-container]]
rel: reinforces -> [[feedback_decay_never_loses_knowledge]]
rel: reinforces -> [[feedback_prefer_existing_infra]]

## Why {#why}

On 2026-11-08 the user asked whether the impressions need another layer, then said "yes add the
impression work". The state measured at `2f4a1df` follows. {#why-state}

- **The ledger has outgrown its cap.**
  - `workflow/bullshit/IMPRESSIONS.md` holds 295 lines (113 KB).
  - `ch-bsd.md#update-impressions-md` caps it at 50 lines, by folding the oldest 10 bullets into
    one consolidated bullet. That cap has been applied only sporadically.
  - So every run reads the whole ledger at step 0b.
- **The durable layer under it.**
  - `memory/impressions/` holds 67 durable lessons, with 125 `rel:` edges among them.
  - 149 run reports sit under them as evidence.
- **The families exist only implicitly.**
  - Many lessons are repeated sightings of a few families, such as busy≠absent, partial bound,
    and counter read at the wrong instant.
  - The procedure already escalates findings by family.
  - But no pattern node exists to escalate against.

The missing layer is a small set of PATTERN nodes above the lessons. It uses the same
derived-subject mechanism that 26.6 builds (ADR-0002 container, `part-of` edges,
multi-membership), in its own compile scope.

## Requirements {#requirements}

1. **R1: Derive candidates.** {#r1}
   - The `memory_compile` verb runs with `scope=pattern`, using 26.6 R-A's single compile path.
     There is no second clusterer.
   - The pattern scope's corpus is mtype `impression`, minus docs tagged `pattern`.
   - The default `memory` scope excludes both: impressions and pattern docs.
   - Candidate subjects are slugged `pattern_<label>` and stamped `compiled_scope: pattern`.
   - A pattern compile never prunes, marks stale, or un-marks a `memory`-scope subject, and the
     reverse also holds (26.6 AC-A). This is ch-bsd r1 B3.
   - A lesson may belong to several patterns.
2. **R2: Curate, with derived counts and user approval.** {#r2}
   - Each accepted pattern becomes a GMD memory `impressions/pattern_bsd_<slug>.md`, with
     `metadata.type: impression` and tag `pattern`. The doc carries:
     - the rule, as one paragraph;
     - a check list ("when you see X, look at Y");
     - `rel: catalogs` edges to its members.
   - The rule text is written by ch-bsd in a dedicated run after 26.8 (user decision 2026-11-08,
     [[#q1-decided]]). It is never auto-generated; the compile only proposes membership.
   - Sighting counts are DERIVED, not kept in prose (ch-bsd r1 #m8, S9). The fold checker (R3)
     counts a pattern's sightings as the run reports under `workflow/bullshit/` that cite either
     the pattern id or a member impression id. The doc carries only the derivation command. A
     generated "sightings" section is rewritten by the checker and never edited by hand.
   - **The user approves each pattern doc before step 0b reads it.** An unapproved doc is tagged
     `pattern-draft`, and step 0b skips it.
3. **R3: Ledger window, lossless.** {#r3}
   - **Three kinds of bullet (r2 s7).** The real ledger at `045ed4e` has 227 bullets:

     | kind | count | how it is recognised |
     |---|---|---|
     | run bullets | 182 dated | carry a date and a plan/round label |
     | pointer bullets | 45 undated | `imp-…` → `[[impression_bsd_…]]`; an index entry, not a run observation |
     | (linked) | 6 | the only run bullets that carry a report link |

   - **A run is a report file.** A run bullet belongs to the report it links. Without a link, it
     is matched by its leading date and plan/round label. A run bullet that matches no report is
     `unassigned`: it stays in the window and is never folded.
   - **The window is defined in RUNS, not characters.** It holds every run bullet of the newest 20
     report files, plus `unassigned` ones. There is no character cap on the window: the measured
     newest-20 holds 33 bullets / 14,450 chars, and those stay whole.
   - **Pointer bullets leave the window.** Each moves to the pattern doc whose members include its
     target (a "pointers" list there). If no pattern claims it, it moves into ONE consolidated
     "legacy pointers" bullet that is a link list (`- legacy pointers: [[impression_bsd_a]],
     [[impression_bsd_b]], …`). A pointer's home is also its memory file, which already exists.
   - **Older run bullets get AT LEAST ONE home** (multi-membership allowed). A home is a pattern
     doc's generated "sightings" section (date, report link, bullet text verbatim), or the
     consolidated "pointer-free" bullet for run bullets no pattern claims.
   - **The character cap applies only to pointer-free consolidated bullets.** Its value is NOT
     guessed. The fold checker first measures, on a COPY of the real ledger, the characters of
     the run bullets that no candidate pattern claims. The cap is then pre-registered in the test
     file before the fold runs: that measurement rounded up to the next 1,000 chars, plus 20%
     headroom. If the measurement exceeds 12,000 chars, the cap is not raised. The checker stops
     and reports that the patterns claim too little (S10).
   - **No deletion without a home.** Decay demotes; it never loses
     ([[feedback_decay_never_loses_knowledge]]).
4. **R4: Procedure, in the overlay, independently reviewed.** {#r4}
   - The ch-bsd procedure change goes into `.claude/agents/ch-bsd.local.md`, which is the project
     overlay. The neutral `.claude/agents/ch-bsd.md` says project specifics belong in the overlay.
     A baseline change, if one is wanted, is a cat-herder change outside this plan. Note that
     `src/refmatrix/templates/agents/` holds only `gmd-curator.md`, so round 0's "shipped
     template" did not exist (S9).
   - The overlay says three things:
     - step 0b reads APPROVED pattern docs first, then the ledger window;
     - the escalation rule cites a pattern id; the count moves only when the checker re-derives it;
     - the 50-line / 12,000-char cap is enforced by the R3 fold.
   - **Conflict of interest (ch-bsd r1 S9):** ch-bsd is the agent whose procedure R4 rewrites. The
     R4 overlay text and the R3 fold checker are therefore assessed by an independent reviewer,
     `@ch-code-reviewer` or `@ch-architect`, NOT by ch-bsd. That review is recorded in this
     task's implementation summary.
5. **R5: Graph.** {#r5}
   - Patterns ingest through the normal bridge.
   - They are reachable by `rmx memory recall --type impression` and `rmx context <pattern-id>`.
   - There is no new store table.
   - Pattern subjects (scope `pattern`) are excluded from project `MEMORY.md` indexes (26.7 AC-A).

## Acceptance criteria {#acceptance}

1. **AC-1: scopes stay separate.** {#ac-1}
   - Setup: a throwaway memory dir and store holding project memories, plus at least 12
     impression fixtures that form at least 3 families, with multi-membership in at least one.
     Run in this order:
     1. the `memory` compile;
     2. the `pattern` compile;
     3. the `memory` compile again.
   - Expected results:
     - The `memory` subjects' leaves and their `stale` flags are byte-identical across step 2.
     - The `pattern` subjects survive step 3.
     - The pattern candidates match the planted families. Precision and recall are reported
       against thresholds pre-registered in the test before the first run.
   - RED at HEAD: a scoped `--apply` (`--exclude-mtype '[!i]*'`) unlinks every project subject's
     leaves.
   - Parity: the `scope` parameter is reachable through the `memory_compile` verb (CLI and MCP),
     not only through the LEGACY `memory compile` command (ch-bsd r1 #m4).
2. **AC-2: pattern docs lint and recall.** {#ac-2}
   - A pattern doc written per R2 lints with zero errors.
   - Once approved, it is returned by `rmx memory recall` for a phrase unique to its rule text.
     The check uses recall, not `memory get` ([[feedback_verify_memory_by_recall_not_get]]).
   - A `pattern-draft` doc is not read by the step 0b reader check.
3. **AC-3: the fold is lossless.** {#ac-3}
   - Run the R3 fold on a COPY of the real `IMPRESSIONS.md`.
   - Expected results:
     - the window holds exactly the run bullets of the newest 20 report files plus the
       `unassigned` ones; the expected count is pre-registered from the measurement (33 run
       bullets at `045ed4e`, re-measured on the copy at RED time);
     - every pointer bullet is in its pattern's pointers list or the "legacy pointers" bullet;
     - every folded bullet's verbatim text is findable in AT LEAST ONE home. A checker enumerates
       bullets before and after and fails listing any bullet with no home;
     - `unassigned` bullets are listed and still in the window;
     - the pointer-free consolidated bullet is within its pre-registered character cap;
     - sighting counts equal the checker's derivation from the report files.
4. **AC-4: the overlay names the pattern location.** {#ac-4}
   - A test asserts that `.claude/agents/ch-bsd.local.md` names the pattern location for step 0b
     and the approval rule.
   - The independent reviewer's assessment of R4 and R3 is linked from the implementation summary.
5. **AC-5: live, after 26.8.** {#ac-5}
   - The real refmatrix impressions compile in scope `pattern`.
   - ch-bsd writes the rule text, and the user approves each doc.
   - The ledger fold runs once.
   - The next ch-bsd run reports which pattern ids it escalated against.
   - AC-5 does not gate plan-26's close.

## Files to modify {#files-to-modify}

| File | Change |
|---|---|
| `src/refmatrix/consolidate.py`, `daemon.py`, `verbs.py` | nothing beyond 26.6's `scope` (R-A); this task adds no clusterer |
| `src/refmatrix/bsd_fold.py` (new) | the R3 fold and its checker; derived sighting counts; run assignment by report |
| `.claude/agents/ch-bsd.local.md` | step 0b, escalation and fold procedure (R4) |
| `workflow/bullshit/IMPRESSIONS.md` | the one-time fold (AC-5) |
| `memory/impressions/pattern_bsd_*.md` | curated pattern docs (live dir, after 26.8) |
| `tests/test_bsd_fold.py`, `tests/test_memory_compile_scope.py` | AC-1, AC-3, AC-4 |

## Test strategy {#test-strategy}

- Use a throwaway memory dir and a throwaway store under a short `mkdtemp()` root, in task 23.0's
  sandbox.
- Run the real compile through the `memory_compile` verb. Compile is never mocked.
- The fold checker runs on a copy of the real ledger, never on the live file, until AC-5.
- Pre-register AC-1's thresholds in the test file before the first run
  ([[feedback_go_no_go_ranges_not_predrop]]).

## Open questions {#open-questions}

1. **Who writes the rule text for each pattern?** DECIDED (user, 2026-11-08): ch-bsd writes the
   patterns in a dedicated run right after 26.8 lands (AC-5), and the user reviews and approves
   them (R2). {#q1-decided}
2. **Should project memories, not only impressions, get the same pattern layer?** No (ch-bsd r1
   verdict: sound). 19.3, built by 26.7, covers project memories.

## Revision round 1 (2026-11-09) {#rev-round-1}

| finding | change | anchor |
|---|---|---|
| B3: two compiles destroy each other; slug collision; impressions already in the default corpus; RED premise false | Scope-aware single path (26.6 R-A); `pattern_` namespace; corpus split; RED AC is "a scoped apply leaves the other scope untouched" | R1, AC-1 |
| S9: template path does not exist; project specifics placed in the neutral file; conflict of interest | Procedure goes in the `ch-bsd.local.md` overlay; independent reviewer, not ch-bsd; user approves each pattern doc | R2, R4, AC-4 |
| S10: "exactly one home" contradicts multi-membership; line cap can be gamed; "last ~20 runs" undefined; pattern docs re-enter the compile | At least one home; line AND character caps; runs defined by report file; `tag: pattern` excluded from both corpora | R1, R3, AC-3 |
| M4: parity (LEGACY compile) | `scope` reached through the `memory_compile` verb | AC-1 |
| M8: sighting count in curated prose | Derived from report files by the checker | R2, AC-3 |
| M9: live step gating plan close | AC-5 does not gate | header, AC-5 |

## Revision round 2 (2026-11-09) {#rev-round-2}

Answers [[bsd-plan26-27-spec-review-r2-8af766a]].

| finding | change | anchor |
|---|---|---|
| s7 (AC-3 cannot pass on the real ledger: pointer bullets and the char cap) | Window defined in runs (newest 20 report files), no char cap on it; pointer bullets moved to their pattern or one "legacy pointers" link-list bullet; char cap only on pointer-free consolidated bullets, pre-measured on a ledger copy and pre-registered (rounded up plus 20%, with a 12,000 ceiling that stops instead of rising) | R3, AC-3 |
