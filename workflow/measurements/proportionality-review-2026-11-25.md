---
gmd: "0.1"
id: proportionality-review-2026-11-25
title: "Proportionality review 2026-11-25: one ruling covers the queue's old ceremony; no trim is proposed; 14 specs are rewritten at entry"
tags: [measurement, p1, proportionality, specs, queue, read-only]
metadata:
  node_type: measurement
  created: 2026-11-25
  author: p1b review agent (Fable 5.2)
  base: 0c798f28
---

# Proportionality review, 2026-11-25 {#root}

POP row P1 (b), per [[agent-brief-p1b-proportionality-review]] (approved, L235). Read-only at
`0c798f28` on branch `p1b`: no plan, spec or POP row was edited. Every cut below is a proposal
for the user. {#purpose}

rel: implements -> [[agent-brief-p1b-proportionality-review#output]]
rel: depends-on -> [[plan-of-plans#queue]]
rel: depends-on -> [[plan-of-plans#rulings]]
rel: depends-on -> [[orchestration#task]]
rel: depends-on -> [[orchestration#planning]]
rel: depends-on -> [[orchestration#proportionate]]
rel: derives-from -> [[admitted-audit-2026-11-24#table]]
rel: derives-from -> [[test-suite-audit-2026-11-15#speed]]

## What was found {#found}

1. **One ruling is enough for the ceremony.** The old review rounds are written into nine
   places in seven files. Everywhere else the round lines are records of rounds already run.
   With the ruling in [[#ruling]], 68 of the 74 files need no edit. {#found-ruling}
2. **No trim is proposed.** History is 4,463 of 35,049 lines (13%). Deleting it saves no round
   and no machine time, and 183 of the 397 anchors inside history sections are linked from live
   text or from another document, so a trim would have to rewrite requirement text, which the
   brief forbids. {#found-trim}
3. **The length is requirements, not ceremony.** The 74 files hold 774 acceptance criteria and
   756 mutation rows, 704 of them on `src/`. None of that is a cut. {#found-length}
4. **Three specs put a full suite inside a criterion or a gate,** 34 runs as written, 26 of
   them in 29.5. That is the only machine time the old load still costs, and it needs the
   user ([[#q1]]). {#found-bands}
5. **Fourteen files are rewritten when their row enters the spec window,** because the audit
   marks them `stale (revise)` or unapproved, not because of ceremony. {#found-rewrite}

## Method {#method}

- **Scope:** every plan file and task spec behind a row of [[plan-of-plans#queue]] that is not
  done and not post-mod: 74 files, listed in `proportionality-review/files.txt`. Rows A1, W1,
  E1, T1, M2, M3 and 18 have no spec file. Plan-24's tasks 24.2 to 24.8 are the mod itself
  and are out; row 16 revises them.
- **Inventory:** `proportionality-review/inventory.py` writes `inventory.tsv` (the counts) and
  `evidence.txt` (every matched line). `render.py` holds the verdicts and prints the table, so
  the table has one row per inventoried file.
- **Prices:** a full suite is 20 minutes at 29.4's sharded-runner target (the figure 29.5 uses)
  and 54 minutes serial (`tests/shard_weights.json`: 3,255 s over 358 files). A mutation is
  about 1 minute: one named test file (mean 9.1 s) plus the apply and the revert. A ch-bsd round
  is one agent run and a fold; it is counted, not timed, because no round has a measured time.
- **Limits of the counts.** Mutation rows are counted from tables, lists and inline "Mutation:"
  clauses, and the `src/` split reads each row's words, so both are approximate. "Rounds
  written" and "full-suite runs written" are the reviewer's reading of the matched lines.
  29.3's four runs assume three module groups; the spec does not fix the number.
- **Status** was taken from the POP and its rulings, never from `metadata.status`.
{#method-list}

## The table {#table}

The row column gives the queue row and its distance from the row in flight (C2).
{#table-lead}

| row | file | lines | ACs | history (sections / lines) | rounds written | full-suite runs written | mutation rows (`src/` / other) | cost if followed | verdict | the cut | reason | at risk |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| C2 (+0) | `task-hook-writes-queue.md` | 101 | 8 | 0 / 0 | 1 (= L165) | 0 | 3 / 0 | rounds as written | **leave** | none | 101 lines, in build; written in the L232 window in the L165 shape; one ch-bsd pass is the rule's own | nothing |
| B1 (+1) | `task-b1-f4-f7.md` | 138 | 6 | 0 / 0 | 0 | 0 | 0 / 0 | nothing beyond L165 | **leave** | none | written in the L232 window in the L165 shape; one ch-bsd pass is the rule's own | nothing |
| I1 (+2) | `plan-32-instruction-architecture.md` | 135 | 1 | 0 / 0 | 0 | 0 | 0 / 0 | nothing beyond L165 | **leave** | none | a plan and its accepted task list (L214, L226); no ceremony in either | nothing |
| I1 (+2) | `retriage-2026-11-24.md` | 209 | 1 | 0 / 0 | 0 | 0 | 2 / 0 | nothing beyond L165 | **leave** | none | a plan and its accepted task list (L214, L226); no ceremony in either | nothing |
| I1 (+2) | `task-I1.a-contradiction-edits.md` | 154 | 8 | 0 / 0 | 1 each large (= L165) | 0 | 0 / 0 | rounds as written | **leave** | none | written in the L232 window in the L165 shape; one ch-bsd pass is the rule's own (L234) | nothing |
| I1 (+2) | `task-I1.b-substrate.md` | 84 | 0 | 0 / 0 | 1 each large (= L165) | 0 | 0 / 0 | rounds as written | **leave** | none | written in the L232 window in the L165 shape; one ch-bsd pass is the rule's own (L234) | nothing |
| I1 (+2) | `task-I1.b0-probes.md` | 120 | 5 | 0 / 0 | 1 each large (= L165) | 0 | 0 / 0 | rounds as written | **leave** | none | written in the L232 window in the L165 shape; one ch-bsd pass is the rule's own (L234) | nothing |
| I1 (+2) | `task-I1.b1-units-and-check.md` | 157 | 8 | 0 / 0 | 1 each large (= L165) | 0 | 6 / 0 | rounds as written | **leave** | none | written in the L232 window in the L165 shape; one ch-bsd pass is the rule's own (L234) | nothing |
| I1 (+2) | `task-I1.b2-marker-and-ledger.md` | 160 | 9 | 0 / 0 | 1 each large (= L165) | 0 | 8 / 0 | rounds as written | **leave** | none | written in the L232 window in the L165 shape; one ch-bsd pass is the rule's own (L234) | nothing |
| I1 (+2) | `task-I1.b3-dispatcher.md` | 182 | 12 | 0 / 0 | 1 each large (= L165) | 0 | 10 / 0 | rounds as written | **leave** | none | written in the L232 window in the L165 shape; one ch-bsd pass is the rule's own (L234) | nothing |
| I1 (+2) | `task-I1.c-first-denies.md` | 152 | 9 | 0 / 0 | 0 | 0 | 0 / 0 | nothing beyond L165 | **leave** | none | drafted in the L165 shape, out of the window (`92ec1050`); Q67-Q69 open | nothing |
| I1 (+2) | `task-I1.d-first-skills.md` | 158 | 9 | 0 / 0 | 0 | 0 | 0 / 0 | nothing beyond L165 | **leave** | none | drafted in the L165 shape, out of the window (`92ec1050`); Q67-Q69 open | nothing |
| I1 (10.3) (+2) | `plan-10-injection-dedup.md` | 353 | 0 | 4 / 50 | 0 | 0 | 0 / 0 | nothing beyond L165 | **covered by rule** | none; the step-4 ruling replaces its process text | only 10.3 is pre-mod; 50 history lines, 1 of 4 history anchors linked | nothing |
| I1 (10.3) (+2) | `task-10.3-plan-10-injection-dedup.md` | 159 | 6 | 1 / 20 | 0 | 0 | 8 / 0 | nothing beyond L165 | **leave** | none | its RED is inside the window: I1.b2 builds it and carries its R4 point as D1, D2 | nothing |
| I1.g (+2) | `task-agent-start-context.md` | 82 | 5 | 0 / 0 | 1 spec round | 0 | 0 / 0 | rounds as written | **rewrite at entry** | at I1.g's entry: one page, and the line 'a ch-bsd spec round precedes approval' goes | `drafting`, 82 lines; L226 pulled it in and L165 gives a spec no ch-bsd round | nothing |
| H1 (+3) | `task-H1.a-reconcile-shipped-files.md` | 132 | 6 | 0 / 0 | 0 (small path) | 0 | 0 / 0 | nothing beyond L165 | **leave** | none | 132 lines, building (L237) | nothing |
| T0.9 (+5) | `task-t0.9-test-isolation.md` | 226 | 13 | 0 / 0 | 0 | 0 | 0 / 0 | nothing beyond L165 | **leave** | none | 226 lines, no history, 'no ch-bsd round' in its own header; (a) is dispatchable (L235). (b) to (d) are revised at their entry (audit: `stale (revise)`) | nothing |
| 4 (+6) | `task-t0-suite-trust-sweep.md` | 1899 | 35 | 9 / 318 | 1 per sub-task, repeated until CLEAN (R0.8) | 2 | 25 / 3 | 2 runs = 40 min sharded (108 serial); 3 non-`src/` mutations = ~3 min; rounds as written | **covered by rule** | none; the ruling replaces R0.8's 'until CLEAN', R7.7's and `#done`'s 'round is CLEAN' | one sub-task (T0.7) is left and the file closes at stage 5; 9 of its 44 history anchors are linked, so a trim would rewrite live text | plans 6, 7, 8 and 15 close on one pass plus a confirm-lite, not on a CLEAN round |
| 4, 6-8 (+6) | `plan-29-code-quality.md` | 194 | 0 | 0 / 0 | 0 | 0 | 0 / 0 | nothing beyond L165 | **leave** | none | 194 lines, no history section | nothing |
| 4, 8 (29.4f) (+6) | `task-29.4-suite-health.md` | 1189 | 19 | 7 / 80 | 1 per sub-task range (R10) | 0 | 19 / 9 | 9 non-`src/` mutations = ~9 min; rounds as written | **covered by rule** | none; R10's round is L165's one pass under the ruling | stage 5 and 29.4f are what is left; 80 history lines | nothing |
| 5, 9, 14 (+7) | `plan-31-pre-mod-loose-ends.md` | 231 | 0 | 0 / 0 | 0 | 0 | 0 / 0 | nothing beyond L165 | **leave** | none | 231 lines, no history, no round, no band | nothing |
| 5 (+7) | `task-31.3-ledger-anchor-guard.md` | 416 | 11 | 2 / 23 | 0 | 0 | 7 / 10 | 10 non-`src/` mutations = ~10 min | **covered by rule** | none; the step-4 ruling replaces its process text | approved on 2026-11-15 (L140); 23 history lines; its product is a gate script outside `src/`, so the ruling as worded would drop its mutation rows: question P1b-Q2 | under the ruling without Q2's clause, a guard nobody proved can fail |
| 5 (+7) | `task-31.4-retire-standing-warnings.md` | 351 | 8 | 2 / 20 | 0 | 0 | 6 / 2 | 2 non-`src/` mutations = ~2 min | **covered by rule** | none; the step-4 ruling replaces its process text | approved L140; 20 history lines; its product is a gate script outside `src/`, so the ruling as worded would drop its mutation rows: question P1b-Q2 | as 31.3 |
| 5 (+7) | `task-31.1-frontmatter-type-refusal.md` | 706 | 11 | 3 / 36 | 0 | 0 | 32 / 1 | 1 non-`src/` mutations = ~1 min | **covered by rule** | none; the step-4 ruling replaces its process text | approved L149; its length is requirements and `src/` mutations, which are never a cut | nothing |
| 5 (+7) | `task-31.6-one-wikilink-resolver.md` | 853 | 15 | 3 / 40 | 0 | 0 | 32 / 0 | nothing beyond L165 | **covered by rule** | none; the step-4 ruling replaces its process text | approved L149; its length is requirements and `src/` mutations, which are never a cut | nothing |
| 6 (+8) | `task-29.1-registry-triage.md` | 552 | 6 | 6 / 87 | 0 | 0 | 0 / 0 | nothing beyond L165 | **covered by rule** | none; the step-4 ruling replaces its process text | docs and a checker; 87 history lines, 2 of 14 history anchors linked | nothing |
| 7 (+9) | `task-29.5-split-giant-modules.md` | 1558 | 21 | 9 / 115 | 0 | 26 | 18 / 0 | 26 runs = 520 min sharded (1404 serial) | **rewrite at entry** | at row 7's entry: one page on the tree as it then is; G5's per-commit full suite goes to the user first (question P1b-Q1) | audit: `stale (revise)` (line counts, `migrate-to-duckdb`, ADR 0006 unwritten); its 115 history lines are the only large history block with no inbound link | a requirement lost in the compression: the entry rewrite is diffed AC by AC |
| 8 (+10) | `task-29.3-converge-shapes.md` | 1176 | 10 | 5 / 86 | 0 | 4 | 37 / 0 | 4 runs = 80 min sharded (216 serial) | **covered by rule** | none by rule; AC-c7's full suite before and after each module group is question P1b-Q1 | 37 `src/` mutations and 10 ACs are the load, and they stay | nothing |
| 8 (+10) | `task-29.2-mypy-gate.md` | 1454 | 30 | 5 / 118 | 2 (R7 and R8 'as their own RED, GREEN, ch-bsd round', then the rest) | 2 | 4 / 0 | 2 runs = 40 min sharded (108 serial); rounds as written | **covered by rule** | none by edit; the ruling makes it one pass over 29.2's whole range; AC-14's before/after suite is question P1b-Q1 | 118 history lines, 6 of 9 history anchors linked | R7's derive-hash change is reviewed with the annotation edits, not ahead of them |
| 8 (+10) | `task-29.6-citation-and-pin-repoint.md` | 394 | 17 | 1 / 12 | 1 confirm-lite per track on re-pointed specs (4 pre-mod tracks) | 0 | 8 / 2 | 2 non-`src/` mutations = ~2 min; rounds as written | **covered by rule** | none by edit; the ruling replaces the per-track confirm-lite with the owner's sign-off the same line already requires; its product is a gate script outside `src/`, so the ruling as worded would drop its mutation rows: question P1b-Q2 | L165: no ch-bsd round on a spec | a location-bound spec change is read by its owner only |
| 9 (+11) | `task-31.2-learned-evidence-agreement.md` | 882 | 16 | 3 / 43 | 0 | 0 | 34 / 0 | nothing beyond L165 | **covered by rule** | none; the step-4 ruling replaces its process text | approved L149; 34 `src/` mutations and 16 ACs are the load | nothing |
| 9 (R4 only) (+11) | `task-22.6-removal-entry-points.md` | 1158 | 28 | 16 / 258 | 0 | 0 | 45 / 2 | 2 non-`src/` mutations = ~2 min | **covered by rule** | none; the step-4 ruling replaces its process text | only R4 is pre-mod and 31.2 builds it; 14 of 16 history anchors are linked | nothing |
| 10 (+12) | `plan-30-materialisation.md` | 388 | 7 | 2 / 40 | 0 | 0 | 0 / 0 | nothing beyond L165 | **covered by rule** | none; the step-4 ruling replaces its process text | written 2026-11-14 with one revision note each (6 to 40 history lines); no round, no band | nothing |
| 10 (+12) | `task-30.0-disk-tier-probe.md` | 285 | 8 | 1 / 6 | 0 | 0 | 0 / 0 | nothing beyond L165 | **covered by rule** | none; the step-4 ruling replaces its process text | written 2026-11-14 with one revision note each (6 to 40 history lines); no round, no band | nothing |
| 10 (+12) | `task-30.5-load-bitmap-row-read.md` | 296 | 8 | 1 / 6 | 0 | 0 | 11 / 1 | 1 non-`src/` mutations = ~1 min | **covered by rule** | none; the step-4 ruling replaces its process text | written 2026-11-14 with one revision note each (6 to 40 history lines); no round, no band | nothing |
| 10 (+12) | `task-30.1-adjacency-mapping-adapter.md` | 253 | 7 | 1 / 6 | 0 | 0 | 10 / 1 | 1 non-`src/` mutations = ~1 min | **covered by rule** | none; the step-4 ruling replaces its process text | written 2026-11-14 with one revision note each (6 to 40 history lines); no round, no band | nothing |
| 10 (+12) | `task-30.2-vectorised-adjacency-build.md` | 405 | 10 | 2 / 14 | 0 | 0 | 18 / 1 | 1 non-`src/` mutations = ~1 min | **covered by rule** | none; the step-4 ruling replaces its process text | written 2026-11-14 with one revision note each (6 to 40 history lines); no round, no band | nothing |
| 10 (+12) | `task-30.3-disk-tier-fate.md` | 247 | 5 | 1 / 6 | 0 | 0 | 10 / 0 | nothing beyond L165 | **covered by rule** | none; the step-4 ruling replaces its process text | written 2026-11-14 with one revision note each (6 to 40 history lines); no round, no band | nothing |
| 10 (+12) | `task-30.4-daemon-adjacency-ppr-op.md` | 839 | 24 | 2 / 26 | 0 | 0 | 32 / 3 | 3 non-`src/` mutations = ~3 min | **covered by rule** | none; the step-4 ruling replaces its process text | written 2026-11-14 with one revision note each (6 to 40 history lines); no round, no band | nothing |
| 10 (G22) (+12) | `task-dq1-operational-content-out-of-graph.md` | 612 | 13 | 5 / 83 | 0 | 0 | 4 / 1 | 1 non-`src/` mutations = ~1 min | **covered by rule** | none; the step-4 ruling replaces its process text | 83 history lines, 5 of 6 history anchors linked; `#queue-stale` points are RED's | nothing |
| 10 (G30, in 30.6) (+12) | `task-bug216-denotes-fold-evaluation.md` | 231 | 7 | 2 / 17 | 1 over the report (`#done`) | 0 | 3 / 0 | rounds as written | **covered by rule** | none by edit; under the ruling the report gets the lead's read, or one pass if question P1b-Q3 says so | a measurement with no `src/` | a wrong reading of the fold bands |
| 11 (+13) | `plan-26-memory-organisation.md` | 592 | 9 | 7 / 112 | 0 | 0 | 0 / 0 | nothing beyond L165 | **covered by rule** | none; the step-4 ruling replaces its process text | 112 / 103 history lines, 6 of 7 and 5 of 8 history anchors linked | nothing |
| 11 (+13) | `task-26.5-memory-organise-verb.md` | 1213 | 14 | 17 / 268 | 0 | 0 | 49 / 4 | 4 non-`src/` mutations = ~4 min | **rewrite at entry** | at row 11's entry: one page from `3a4d430` plus the six `#queue-stale` points; its 17 revision sections (268 lines) go then | audit: `stale (revise)`; P7, P9 and the 26.5 split are open | as 29.5 |
| 11 (+13) | `task-26.7-memory-index-by-subject.md` | 186 | 6 | 4 / 75 | 0 | 0 | 0 / 0 | nothing beyond L165 | **rewrite at entry** | at entry: L226's amendments (ADR 0007 `#memory-index`; AC-8's MEMORY-RULES text, L222) written in, history dropped | audit: `stale (revise)`; held revision `3a4d430` is not on `master` yet (L231 (2)); history anchors are linked from live text | as 29.5 |
| 11 (+13) | `task-26.6-compile-subject-hygiene.md` | 254 | 11 | 3 / 28 | 0 | 0 | 0 / 0 | nothing beyond L165 | **covered by rule** | none; the step-4 ruling replaces its process text | 78 to 261 lines each; no round, no band; `#queue-stale` points are RED's | nothing |
| 11 (+13) | `task-26.8-refmatrix-live-rollout.md` | 306 | 11 | 8 / 114 | 0 | 0 | 0 / 0 | nothing beyond L165 | **rewrite at entry** | at entry: L226's amendments (ADR 0007 `#memory-index`; AC-8's MEMORY-RULES text, L222) written in, history dropped | audit: `stale (revise)`; held revision `3a4d430` is not on `master` yet (L231 (2)); history anchors are linked from live text | as 29.5 |
| 11 (+13) | `task-26.9-impression-patterns.md` | 261 | 5 | 4 / 46 | 0 | 0 | 0 / 0 | nothing beyond L165 | **covered by rule** | none; the step-4 ruling replaces its process text | 78 to 261 lines each; no round, no band; `#queue-stale` points are RED's | nothing |
| 11 (+13) | `plan-27-memory-fleet-rollout.md` | 368 | 9 | 8 / 103 | 0 | 0 | 0 / 0 | nothing beyond L165 | **covered by rule** | none; the step-4 ruling replaces its process text | 112 / 103 history lines, 6 of 7 and 5 of 8 history anchors linked | nothing |
| 11 (+13) | `task-27.0-organise-merge-from.md` | 102 | 9 | 2 / 18 | 0 | 0 | 1 / 0 | nothing beyond L165 | **covered by rule** | none; the step-4 ruling replaces its process text | 78 to 261 lines each; no round, no band; `#queue-stale` points are RED's | nothing |
| 11 (+13) | `task-27.1-fleet-inventory.md` | 181 | 7 | 5 / 52 | 0 | 0 | 0 / 0 | nothing beyond L165 | **covered by rule** | none; the step-4 ruling replaces its process text | 78 to 261 lines each; no round, no band; `#queue-stale` points are RED's | nothing |
| 11 (+13) | `task-27.2a-index-prose-to-memories.md` | 144 | 6 | 2 / 15 | 0 | 0 | 0 / 0 | nothing beyond L165 | **covered by rule** | none; the step-4 ruling replaces its process text | 78 to 261 lines each; no round, no band; `#queue-stale` points are RED's | nothing |
| 11 (+13) | `task-27.2-viascope2-fold-and-repoint.md` | 142 | 8 | 3 / 28 | 0 | 0 | 0 / 0 | nothing beyond L165 | **covered by rule** | none; the step-4 ruling replaces its process text | 78 to 261 lines each; no round, no band; `#queue-stale` points are RED's | nothing |
| 11 (+13) | `task-27.3-thiquet-store-repoint.md` | 90 | 6 | 1 / 8 | 0 | 0 | 0 / 0 | nothing beyond L165 | **covered by rule** | none; the step-4 ruling replaces its process text | 78 to 261 lines each; no round, no band; `#queue-stale` points are RED's | nothing |
| 11 (+13) | `task-27.4-quiet-dir-migrations.md` | 78 | 6 | 1 / 10 | 0 | 0 | 0 / 0 | nothing beyond L165 | **covered by rule** | none; the step-4 ruling replaces its process text | 78 to 261 lines each; no round, no band; `#queue-stale` points are RED's | nothing |
| 11 (+13) | `task-27.5-cliquedb-at-session-boundary.md` | 123 | 5 | 4 / 36 | 0 | 0 | 0 / 0 | nothing beyond L165 | **covered by rule** | none; the step-4 ruling replaces its process text | 78 to 261 lines each; no round, no band; `#queue-stale` points are RED's | nothing |
| 11 (+13) | `task-27.6-per-store-compile-and-landing.md` | 107 | 4 | 4 / 36 | 0 | 0 | 0 / 0 | nothing beyond L165 | **covered by rule** | none; the step-4 ruling replaces its process text | 78 to 261 lines each; no round, no band; `#queue-stale` points are RED's | nothing |
| 12 (+14) | `plan-25-cliquedb-field-report.md` | 482 | 10 | 7 / 133 | 0 pre-mod (25.1b's round is post-mod) | 0 | 0 / 0 | nothing beyond L165 | **covered by rule** | none; the step-4 ruling replaces its process text | 133 history lines, 6 of 8 history anchors linked | nothing |
| 12 (+14) | `task-25.3-stm-ref-admission-and-helix-repeat.md` | 383 | 15 | 4 / 59 | 0 | 0 | 13 / 1 | 1 non-`src/` mutations = ~1 min | **covered by rule** | none; the step-4 ruling replaces its process text | audit: stale at RED only (`stm.pre_prompt_state`) | nothing |
| 12 (+14) | `task-25.2-thin-prompt-gate.md` | 309 | 10 | 5 / 68 | 0 | 0 | 11 / 0 | nothing beyond L165 | **rewrite at entry** | at entry: R0 reports guardrail-memory uses apart from the rest (L226, re-triage `#r12`) | audit: `stale (revise)` | as 29.5 |
| 13 (+15) | `plan-23-bounded-write-harness.md` | 514 | 15 | 13 / 293 | 0 | 0 | 0 / 0 | nothing beyond L165 | **covered by rule** | none; the step-4 ruling replaces its process text | 293 of 514 lines are history, but 12 of 13 history anchors are linked and 9 AC ids and 9 R ids appear only there | nothing |
| 13 (+15) | `task-bug185-bulk-gmd-ingest.md` | 1263 | 16 | 6 / 294 | 0 | 0 | 27 / 2 | 2 non-`src/` mutations = ~2 min | **rewrite at entry** | at row 13's entry: one page with the L136 / L144 / L145 notes and bug-309's measured holder written in; 294 history lines go then | audit: `stale (revise)`; its R9 STOP bands and the 5 + 5 timing runs are measured bands and stay | as 29.5 |
| 13 (+15) | `task-23.2-lock-hold-fixture.md` | 288 | 6 | 5 / 73 | 0 | 0 | 0 / 1 | 1 non-`src/` mutations = ~1 min | **covered by rule** | none; the step-4 ruling replaces its process text | history anchors linked (5 of 5, 7 of 8, 7 of 8); `#queue-stale` points are RED's | nothing |
| 13 (+15) | `task-23.1-queue-and-drain.md` | 2103 | 21 | 13 / 252 | 0 | 0 | 48 / 2 | 2 non-`src/` mutations = ~2 min | **rewrite at entry** | at entry: three one-page specs (23.1b, 23.1a, 23.1c, as decided), L183 / L184 written in, R11 re-based on C2's spool; 252 history lines go then | audit: `stale (revise)`; the largest file on the queue (2,103 lines), and 21 ACs with 53 mutations cannot fit one page unsplit | as 29.5; the split is where a requirement is lost |
| 13 (+15) | `task-23.3-sync-between-file-yield.md` | 517 | 11 | 8 / 104 | 0 | 0 | 18 / 0 | nothing beyond L165 | **covered by rule** | none; the step-4 ruling replaces its process text | history anchors linked (5 of 5, 7 of 8, 7 of 8); `#queue-stale` points are RED's | nothing |
| 13 (+15) | `task-23.5-read-path-and-holder-bounds.md` | 1145 | 10 | 8 / 164 | 0 | 0 | 44 / 2 | 2 non-`src/` mutations = ~2 min | **covered by rule** | none; the step-4 ruling replaces its process text | history anchors linked (5 of 5, 7 of 8, 7 of 8); `#queue-stale` points are RED's | nothing |
| 13 (+15) | `task-bug218-reinforcement-edge-direction.md` | 438 | 14 | 3 / 42 | 0 | 0 | 19 / 1 | 1 non-`src/` mutations = ~1 min | **rewrite at entry** | at entry: the held revision `b2e2451` merged on the lead's read (L231 (2)), then one page | audit: `stale (revise)` | as 29.5 |
| 14 (+16) | `task-31.5-scan-prompt-block-measure.md` | 1148 | 37 | 2 / 41 | 0 | 0 | 29 / 1 | 1 non-`src/` mutations = ~1 min | **rewrite at entry** | at row 14's entry, S2 only: the recall-channel cut after I1.h and the regime marks at each I1 install window (L226). S0b, S1 and the capture size stay as written | audit: `stale (revise)` for S2; the 400-prompt capture and the 200 runs per arm are bands the user set | as 29.5 |
| 14, 15 (+16) | `plan-21-agent-context-usage.md` | 327 | 21 | 12 / 183 | 0 | 0 | 0 / 0 | nothing beyond L165 | **covered by rule** | none; the step-4 ruling replaces its process text | 183 of 327 lines are history with no inbound link, but 15 AC ids appear only there | nothing |
| 14 (+16) | `task-21.2-precise-identifier-context.md` | 183 | 9 | 2 / 35 | 0 | 0 | 6 / 1 | 1 non-`src/` mutations = ~1 min | **covered by rule** | none; the step-4 ruling replaces its process text | 183 lines; its gold files are re-frozen at RED (`#queue-stale`) | nothing |
| 14 (+16) | `task-21.4-surfaces-and-nl-ranking.md` | 246 | 4 | 3 / 56 | 0 | 0 | 2 / 1 | 1 non-`src/` mutations = ~1 min | **rewrite at entry** | at entry: R4 leaves for I1.h (L226); R1 to R3 on one page | audit: `stale (revise)` | as 29.5 |
| 15 (+17) | `task-21.5-tool-used-signal.md` | 1783 | 24 | 5 / 186 | 1 over the measurement, until CLEAN or MEH-only (`#done-m`) | 0 | 45 / 0 | rounds as written | **covered by rule** | none by edit; one pass with no repeat under the ruling (question P1b-Q3) | phase M has no `src/`; phase B (most of the 1,783 lines) is frozen and post-mod | the band reading feeds the charter decision on one review |
| 16, 17 (+18) | `plan-24-mod-transport.md` | 145 | 0 | 0 / 0 | 0 | 0 | 0 / 0 | nothing beyond L165 | **rewrite at entry** | row 16 is the rewrite: the freshness revision, with no ch-bsd round (L226) | audit: `needs-approval`; `drafting`, r7 fold never confirmed | nothing beyond row 16's own |
| 16, 17 (+18) | `task-24.0-hook-cost-baseline.md` | 229 | 7 | 2 / 21 | 0 | 0 | 0 / 0 | nothing beyond L165 | **rewrite at entry** | row 16 is the rewrite: the freshness revision, with no ch-bsd round (L226) | audit: `needs-approval`; `drafting`, r7 fold never confirmed | nothing beyond row 16's own |
| 16, 17 (+18) | `task-24.1-store-runtime-identity.md` | 128 | 6 | 0 / 0 | 0 | 0 | 0 / 0 | nothing beyond L165 | **rewrite at entry** | row 16 is the rewrite: the freshness revision, with no ch-bsd round (L226) | audit: `needs-approval`; `drafting`, r7 fold never confirmed | nothing beyond row 16's own |

{#review-table}

## Totals {#totals}

| verdict | files | lines | history lines | ACs | `src/` mutation rows | other mutation rows | full-suite runs written |
|---|---|---|---|---|---|---|---|
| leave | 17 | 2692 | 20 | 101 | 37 | 0 | 0 |
| trim | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| rewrite at entry | 14 | 9354 | 1346 | 172 | 203 | 11 | 26 |
| covered by rule | 43 | 23003 | 3097 | 501 | 464 | 41 | 8 |
| **all** | 74 | 35049 | 4463 | 774 | 704 | 52 | 34 |

{#totals-table}

- **Lines.** Before: 35,049. After the ruling: 35,049, because the ruling edits nothing. After
  the entry rewrites: the 14 files (9,354 lines) become about 16 one-page specs (23.1 splits in
  three). The eleven task specs written in the L232 window average 140 lines, so the prose
  falls to roughly 2,200 lines; the 172 criteria and 214 mutation rows carry over
  ([[#q5]]). {#totals-lines}
- **Rounds.** Written into the text beyond [[orchestration#task]]: two "repeat until CLEAN"
  loops (T0 R0.8 with 29.4 R10; 21.5 `#done-m`), and about seven named extra rounds (29.2's
  second round, 29.6's confirm-lite on four tracks, G30's report round,
  `task-agent-start-context`'s spec round). After the ruling: none. {#totals-rounds}
- **Full-suite runs.** Written: 34 (680 minutes sharded, 1,836 serial). T0.7's two are the
  task's deliverable and stay. The other 32 are [[#q1]]'s. {#totals-runs}
- **Mutations outside `src/`.** 52 rows by the script, about 52 minutes. About 35 of them
  prove a gate script can fail (31.3, 31.4, 29.6) and are [[#q2]]'s. {#totals-mutations}

## The ruling tested first {#ruling}

Proposed text, for the user: {#ruling-lead}

> For every plan and task spec on the queue written before L165: a ch-bsd spec round, a round
> per sub-task "until CLEAN", a confirm-lite before RED, a proof band, and a mutation on a
> file outside `src/` are replaced by ORCHESTRATION `#task` (one pass on a large change, a
> confirm-lite only for a BULLSHIT, the verify set, mutations on the `src/` change). This holds
> wherever the text sits, a rule, a requirement or a done line included. No spec file is
> edited. Not replaced: a full-suite run that is itself an acceptance criterion, T0.7's R7.4
> and R7.5, and any band the user set.

{#ruling-text}

Sites the ruling replaces, so nobody has to find them again: T0 R0.8, R7.7 and `#done`; 29.4
R10; 29.2's test strategy ("R7 and R8 go first, as their own RED, GREEN, ch-bsd round"); 29.6
(a confirm-lite per track on re-pointed specs); 21.5 `#done-m`; G30's `#done`; the header of
`task-agent-start-context`. {#ruling-sites}

**Result.** Of 74 files, 68 need no edit and nothing else. Six are not settled by the ruling:
{#ruling-result}

| file | why the ruling is not enough | goes to |
|---|---|---|
| `task-29.5-split-giant-modules.md` | gate G5 (R4) runs the full suite before and after each of 25 move commits, about 26 runs | [[#q1]] |
| `task-29.3-converge-shapes.md` | AC-c7: the full suite before and after each module group | [[#q1]] |
| `task-29.2-mypy-gate.md` | AC-14: the full suite before and after | [[#q1]] |
| `task-31.3-ledger-anchor-guard.md` | the task has no `src/`; its 17 mutations prove the guard can fail, and the ruling as worded drops them | [[#q2]] |
| `task-31.4-retire-standing-warnings.md` | as 31.3: 8 mutations on `tools/gmd/lint.py` and the wrapper | [[#q2]] |
| `task-29.6-citation-and-pin-repoint.md` | as 31.3: 10 mutations on the re-point tool | [[#q2]] |

{#ruling-not-covered}

## Questions for the user {#questions}

The lead assigns the Q ids. {#questions-lead}

1. **P1b-Q1: full suites inside criteria.** [[orchestration#task]] says "never a branch full
   suite". **(a, recommended)** 29.5 keeps G5 as written: it moves the two modules nearly every
   test imports, so its verify set is the suite; it runs alone, and the 26 runs are machine
   time (8.7 hours at 20 minutes). Go/no-go: if T0.7's clean run measures the runner above 30
   minutes, G5 drops to the rename commit and each phase boundary (about 4 runs) and a failure
   is found by bisect. 29.3 AC-c7 and 29.2 AC-14 are reworded to "the verify set per group;
   the full suite once, at release R3's gate". **(b)** all three as written (34 runs). **(c)**
   all three on the verify set. At risk under (a): a regression in a file that imports none of
   a group's modules shows at the release gate, not at the group. {#q1}
2. **P1b-Q2: does a gate script count as `src/` for L164's mutation rule?** **(a,
   recommended)** yes: a checker's job is to fail, and CLAUDE.md test rule 5 already asks for a
   planted must-fail case; 31.3, 31.4 and 29.6 keep their rows (about 35 minutes). **(b)** no:
   each keeps one must-fail fixture per check and drops the rest. At risk under (b): a guard
   that passes on a clean corpus and cannot fail. {#q2}
3. **P1b-Q3: a review of a measurement.** L165 has no path for a report with no `src/`. **(a,
   recommended)** 21.5 phase M gets one ch-bsd pass with no repeat (its band reading feeds the
   charter decision and row 16); G30's report gets the lead's read. **(b)** both get one pass.
   **(c)** neither. {#q3}
4. **P1b-Q4: no separate trim pass.** **(a, recommended)** history leaves a spec only when the
   spec is rewritten at entry; the 43 `covered by rule` files keep theirs (3,097 lines). **(b)**
   trim the five files where the script finds no inbound link and no id that lives only in
   history (29.6, 30.1, 30.3, G30, 26.6): 69 lines. **(c)** trim everything and re-point the
   183 links, which changes requirement text. {#q4}
5. **P1b-Q5: what "one page" means for a spec with 20 criteria.** 23.1 has 21 criteria and 53
   mutation rows; 31.5 has 37 criteria. **(a, recommended)** the page is the goal, the files
   and the risks; the criteria and `src/` mutation tables carry over word for word as the
   spec's second part, checked by the script the brief's `#after` names. **(b)** the architect
   may merge or drop criteria, each drop put to the user. {#q5}

## What the audit's table now gets wrong {#audit-drift}

Against [[admitted-audit-2026-11-24#table]], at `0c798f28`: {#audit-drift-lead}

- **bug-318** is `unadmitted` there. It was admitted by L231 (1) and merged (`4ae4ecef`).
- **I1, H1, P1 and B1** read `needs-spec` or "a brief is owed". L234 and L235 approved
  `task-b1-f4-f7`, I1.a, I1.b with b0 to b3, H1.a and this review's brief; H1.a is building
  (L237). I1.c and I1.d are drafted, out of the window.
- **Row 11 and bug-218** are said to wait on a ch-bsd confirm-lite before RED. L231 (2)
  replaced it with the lead's read. Neither held revision (`3a4d430`, `b2e2451`) is reachable
  from `0c798f28` yet.
- **10.3** reads `stale (revise)`. I1.b2's D1 and D2 now carry its R4 exit-code point, so
  its own file needs no edit.
- **Contradictions 1, 5 and 9** are closed: the queue rows are rewritten to L226, Q41 is
  superseded, and row 16 says no ch-bsd round.
- **Row 8 reads `ready` with no stale note.** 29.2 plans two ch-bsd rounds, 29.6 a
  confirm-lite per track, and 29.3 AC-c7 and 29.2 AC-14 a branch full suite. These predate
  L165 as 29.4 R10 does, which the audit does note.
- **Row 15 (21.5) and G30 read `ready`.** Their done lines require a ch-bsd round over the
  report, 21.5's until CLEAN.
- **`task-agent-start-context`** still says a ch-bsd spec round precedes approval; the audit's
  I1 row does not mention it.
{#audit-drift-list}

## Done check {#done-check}

The table has 74 rows and `inventory.tsv` has 74 files. No `trim` is proposed, so no section
is named for deletion. No plan or spec file was edited (`git diff --stat 0c798f28 --
workflow/plans` is empty). {#done-check-body}
