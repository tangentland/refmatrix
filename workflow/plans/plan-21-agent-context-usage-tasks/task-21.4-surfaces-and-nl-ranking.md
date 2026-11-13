---
gmd: "0.1"
id: task-21.4-surfaces-and-nl-ranking
title: "Task 21.4: measure and fix natural-language context ranking, then rewrite every steering surface to one rule"
tags: [task, context, ranking, docs, agent, eval]
metadata:
  node_type: task
  status: pending
  created: 2026-10-07
  updated: 2026-11-13
---

# Task 21.4: NL ranking, then the surfaces {#root}

> Plan: [plan-21-agent-context-usage](../plan-21-agent-context-usage.md)
> Status: Pending (revision after the 2026-10-14 decision log)
> Wave: 3 (history; 2026-11-13: queue item 6, after 21.2, [[#rev-2026-11-13]])
> Depends on: 21.1 (the `internal` source, the shared pytest-temp predicate the draw filters
> with), 21.2, 23.0 (sandbox). The docs change LAST, so they never promise what the tool cannot do.

rel: part-of -> [[plan-21-agent-context-usage]]
rel: derives-from -> [[exploration-agent-context-usage]]
rel: derives-from -> [[bsd-plan21-spec-review-3104a81]]
rel: derives-from -> [[plan-review-2026-10-14]]
rel: depends-on -> [[task-21.1-context-usage-telemetry]]
rel: depends-on -> [[task-21.2-precise-identifier-context]]
rel: related-to -> [[plan-13-cross-partition-sweep]]

## Why {#why}

**Natural-language replay.** On deployed 0.76.2, 6 NL questions gave 0 hits, 1 partial and 5
misses: memory and handoff prose crowded out code. All replay rows are `source=context-replica`,
and the CLI replica route builds the bundle with NO `reranker=` argument, at 0.76.2 (`d0273a5`) and
at HEAD (`cli.py:5100`). The replay therefore measured the UNRERANKED replica route. `2cd73b9`
fixed the DAEMON route's no-anchor hand-off, which the replay never exercised (bsd #s-8; the
earlier story that "the hand-off dropped the reranker" was wrong for these rows). Re-running the
same CLI command on the branch stays unreranked; only the daemon / MCP route reflects `2cd73b9`, and
nobody has measured it.

**Steering surfaces disagree:**
- CLAUDE.md frames context as symbol-only.
- The PRIMER promises "plain english … never empty".
- `.refmatrix/CLAUDE.md` routes "where is X used" to `neighbors`.
- The MCP description has no when-to-use.
- Plan-16 R3 points at `rmx_search`, a federated DSL, not a concept search.

{#why-body}

## Requirements {#requirements}

**This set is the ONE ranking-eval harness** (plan review C9). It judges 21.4's own candidates and
ADR-0004's sentence co-location rerank (after bug-075). It does NOT judge plan-13's
session-inclusion question: sessions are out of the gold (d4b), and plan-13 stays dormant with its
pointer at [[plan-21-agent-context-usage#consolidations]]. It lives at
`eval/production/context_nl/` with a stable runner API (`run(questions, route) -> per-question
ranks`) so those callers reuse it rather than building their own.

1. **R1 The question set: drawn, approved, hashed, redacted** (d4b, d4c, d8f; bsd #s-9).
   - **Strata:** code (gold = a `path:line` of a definition) and doc (gold = a GMD `doc-id#anchor`
     section). n = 40: ≥ 20 code, ≥ 15 doc, each reported separately. Sessions and memories are not
     gold.
   - **Source: this project's `.refmatrix/query.log` ONLY** (d9h, the user, 2026-10-14). Real NL
     queries (`kind=context` NL rows and concept-OR grep rows with their eventual answers),
     classified by 21.1's `telemetry.row_provenance(row, reader_root=<this project's store
     root>)`: `test_artifact` and `legacy_fixture` rows are dropped (`legacy_unattributed` rows,
     i.e. every row written before 21.1, are eligible, per 21.1 R5's totals rule), with
     `invocation=internal` rows and the 2026-10-07T11:06:35-11:07:13 replay window excluded. The
     global `~/.refmatrix/query.log` is never read (it holds other trees' queries).
   - **Who drafts:** a dedicated agent whose brief forbids reading the ranking code
     (`src/refmatrix/context.py`, `src/refmatrix/reranker.py`, the rerank ops in `daemon.py`, and,
     since bug-216 R9 made them part of ranking (lead, 2026-11-13), the typed-edge candidate
     expansion and the PageRank edge-set code that bug-216 changed: the `denotes` walk and fold);
     its tool-call list is kept with the set's provenance, and a check fails the set if any Read of
     those paths appears. A question whose gold lies in those files is excluded. The tuner (the
     agent or session doing R3) never edits the set.
   - **Approval (user-gated):** the user approves the drafted set (redacted form) before it is
     frozen. The goal stops here for the user (L45; bsd-spec-t3ab M6).
   - **Privacy (d8f):** the RAW set stays local under `eval/production/context_nl/raw/`
     (gitignored). Committed: the sha256 of the raw set's canonical JSON, recorded in
     [[#frozen-hash]], and a REDACTED fixture (absolute paths, hostnames and non-refmatrix tree names
     scrubbed; the question text otherwise kept) with its own sha256. All runs and tests use the
     redacted fixture.
   - **The question-text exception, stated** (re-review #m-4). d8f and
     [[feedback_no_raw_prompts_in_public_repo]] say prompts are scrubbed. This set keeps question
     TEXT because the questions are the agent's own queries about THIS repo's code and docs (the
     content the public repo already holds), not user prompts, and because a hashed question
     cannot be re-run. The gate is the user's approval of the redacted set (above), which
     reviews every kept question; a question that quotes a user prompt, a person, a host or
     another tree is dropped at approval, not scrubbed.
2. **R2 Measure both routes.** hit@1 / hit@5 for the daemon route (reranked) and the CLI replica
   route (not reranked), against an `rg -n` baseline the agent would have written, per stratum. The
   runner sets `RMX_INVOCATION_SOURCE=internal` (d4f) and runs on a catalog copy taken from the
   replica reader file.
3. **R3 Fix what the measurement shows.** Candidates, each measured on R1 and kept only by AC-3's
   rule:
   - a kind-aware prior (code before memory prose for a query that names no memory);
   - a `--code` scope;
   - the replica route reranking under the same budget as the daemon route (`with_budget`), the
     route that produced the old number (bsd #s-8).
4. **R4 One rule on every surface, written after R3:** "identifier, or what-calls-X →
   `rmx context` (MCP `rmx_context`, `--brief`). Regex in a known file, or log triage → grep."
   - The surfaces: CLAUDE.md's ladder, the PRIMER header (generated by `rmx primer`,
     `cli.py:8939`), `.refmatrix/CLAUDE.md` (generated by `hooks._install_briefing`,
     `hooks.py:1017`), the MCP tool description, plan-16 R3 / task 16.3.
   - The PRIMER keeps "plain english" only if R2/R3 support it.
   - Plan-16's `rmx_search` mention is corrected.
   - The regenerated `.refmatrix/CLAUDE.md` ships in the C11 install-hooks window (bsd #m-5): the
     first user-gated window after R4 lands, 10.4's (queue item 6), else 16.3's (item 10). The
     lead lists it in the plan review's G31 (lead, 2026-11-13).

## The frozen hash {#frozen-hash}

Filled at freeze time, in its own commit, BEFORE any R3 change; never edited after:

| artifact | sha256 |
|---|---|
| raw set (local, gitignored) | _to be recorded at freeze_ |
| redacted fixture (committed) | _to be recorded at freeze_ |

{#frozen-hash-body}

## Acceptance criteria {#acceptance}

1. **Frozen before tuning** (d4c). A test recomputes the redacted fixture's sha256 and asserts it
   equals [[#frozen-hash]]; when the local raw set is present it also checks the raw hash. The
   commit that fills [[#frozen-hash]] precedes the first commit touching `context.py`,
   `reranker.py` or the rerank ops on the task branch (commit order checked). The drafting agent's
   provenance shows no Read of the ranking files.
2. **The R2 table** (both routes × hit@1/@5 × the rg baseline × each stratum) is in the
   implementation summary and `REPORT.md`.
3. **Pre-registered win** (d4b). An R3 change ships only if, on the route it touches, hit@5 over
   the 40 rises by **≥ 3 questions net** (7.5 points) AND **no stratum loses net** on hit@5. Every
   candidate that fails is recorded in `REPORT.md` as a negative with its numbers.
4. **The five surfaces agree, checked on generator output** (bsd #s-10). The test runs the PRIMER
   generator and `_install_briefing` into a tmp dir and greps THEIR output; it reads the MCP
   description from the generated tool schema; it greps the committed `CLAUDE.md` and plan-16 files
   in place. Each contains the rule's anchor sentence. It never reads the gitignored
   `.refmatrix/PRIMER.md` or `.refmatrix/CLAUDE.md`. The PRIMER makes no claim the R2 table
   contradicts.
5. **No live writes.** Every run leaves the live `query.log` / `recall-events.jsonl` line counts
   unchanged and writes only `invocation=internal` rows to the copy.
6. **Mutations that must FAIL a test** (pre-registered):
   - one question edited in the redacted fixture (AC-1);
   - the surface test pointed at `.refmatrix/PRIMER.md` instead of the generator output, with the
     generator's rule sentence removed (AC-4 must still fail);
   - the runner's `internal` source removed (AC-5).

## Files to modify {#files-to-modify}

`eval/production/context_nl/` (redacted set + runner + `REPORT.md`; `raw/` gitignored);
`.gitignore` (the `raw/` entry); `src/refmatrix/context.py` and the replica route in `cli.py` (R3);
`CLAUDE.md`, the PRIMER generator, `hooks._install_briefing`; `src/refmatrix/mcp.py` / `verbs.py`
descriptions; `workflow/plans/plan-16-invisible-grep-shim.md`.

## Test strategy {#test-strategy}

- **Sandbox:** 23.0's sandbox for every test; runner subprocesses get `HOME` = tmp,
  `REFMATRIX_ROOT` = the copy's root and `RMX_HUB_MODELS=0`. The eval runs on the redacted fixture
  (d8f).
- The ranking work is evaluated, not unit-tested; its gate is AC-3's pre-registered margin.
- **RED:** the surface consistency test fails today, because the surfaces disagree; AC-1's hash
  test fails until the freeze commit lands.

## Revision (2026-10-14 decision log) {#rev-2026-10-14}

| finding or decision | answered at |
|---|---|
| bsd #s-8 (wrong causal story; replica never reranked) | [[#why]]; R3 third candidate |
| bsd #s-9 / d4b (code + doc, sessions out, plan-13 dormant, min win + n) | R1 strata; [[#requirements]] preamble; AC-3 |
| d4c (drawn from query.log, agent blind to ranking code, user-approved, hash before tuning) | R1; [[#frozen-hash]]; AC-1 |
| d8f (raw local, hash + redacted fixture committed) | R1 privacy; [[#frozen-hash]]; [[#test-strategy]] |
| decision-log #s-8 (source log, fixture filter) | R1 source (project log; d8d predicate; `internal` and replay window excluded) |
| bsd #s-10 (generator, not runtime) | AC-4 |
| bsd #s-7 / d1a, d1b | [[#test-strategy]]; AC-5 |
| d4f (harness sets `internal`) | R2; AC-5 |
| bsd #m-5 (C11) | R4 last bullet |
| #t4-fixes "replica-route reranker for 21.4" | R3 third candidate |

## Revision round 2 (2026-10-14) {#rev-round-2}

Answers [[bsd-plan19-21-spec-rereview-32dde06]] and [[plan-review-2026-10-14#t9]].

| finding / decision | answered at |
|---|---|
| d9h (question set from this project's `query.log` only) | R1 source |
| re-review #b-2 / d9g (legacy rows, fixture rows) as they reach the draw | R1 source (`row_provenance` classes) |
| re-review #m-4 (question text kept) | R1 "question-text exception" |

## Revision (2026-11-13, the plan review: D-Q3, D-Q5; re-read against bug-216's resolver) {#rev-2026-11-13}

Three requirement changes, no AC change: the Q8 constraint on the doc stratum's gold, which the
spec wave's rule required and Q9 / L60 keeps ([[#q8]]), and the lead's 2026-11-13 rulings on R1's forbidden list and
R4's install window. A third ruling adds a note on the fold re-score (all listed at the end).
{#rev-2026-11-13-lead}

rel: implements -> [[plan-review-2026-11-13#d-q3]]
rel: implements -> [[plan-review-2026-11-13#d-q5]]
rel: related-to -> [[task-bug216-rule-docs-in-graph]]

| item | record |
|---|---|
| D-Q5 | plan-24 D1's hold on 21.2-21.4 is superseded. This task builds now on the current surfaces: the CLI, the MCP tool description, the PRIMER generator, `_install_briefing`. The MCP description stays a surface until plan-24's re-plan after the charter decision |
| D-Q3 | pull-side work proceeds. Queue item 6, after 21.2 |
| doc stratum gold (`doc-id#anchor`) under bug-216 R6 | anchored targets keep concept-first, so the gold's meaning is unchanged |
| ranking under bug-216 R9 | `denotes` is a zero-cost hop in `build_context`'s degree walk, and PageRank folds a concept's typed in-edges onto its `denotes` target, so doc ranks move when bug-216 goes live. R2's table and every R3 candidate run on ONE catalog copy taken after bug-216's live re-derive (queue item 1, user-gated, with R10's pending refs resolved). Otherwise bug-216's movement would be scored as a 21.4 win or loss. The copy is also taken BEFORE G22 rev 2's gate deploys ([[#q8-copy-order]]) |
| bug-216 R11 (CLAUDE.md and `.claude/PROJECT_PROFILE.md` ingested when they carry GMD frontmatter) | CLAUDE.md is one of R4's five surfaces and is now also a ranked doc, so R4's rule sentence enters the corpus. No conflict. AC-4 still reads the committed file |

**Ruled by the lead, 2026-11-13** (each on the recommended option):
- **O-a (folded into R1):** the drafting agent's forbidden list adds bug-216's typed-edge
  candidate expansion and PageRank edge-set code (the `denotes` walk and fold), by d4c's own rule.
- **O-b (a note, no requirement change):** C9 makes this set THE ranking-eval harness, but L29's
  per-type evaluation of bug-216's PageRank fold (plan review G30) runs in the measurement lane
  before this harness exists (item 6). G30 therefore scores with its own pre-registered per-type
  bands. Once this set is frozen ([[#frozen-hash]]), this harness RE-SCORES the fold on both
  routes and records the result in `REPORT.md` beside G30's numbers. The re-score is a
  measurement and gates nothing in 21.4.
- **O-c (folded into R4's last bullet):** the regenerated `.refmatrix/CLAUDE.md` rides the first
  user-gated install window after R4 lands (10.4's, else 16.3's). The lead adds it to G31.

## Q8 / Q9: `workflow/` in the store {#q8}

Q8 is answered (a), and Q9 refined it for `workflow/` (L60, G22 rev 2). `workflow/` stays ingested
in the project partition and is DEMOTED by design: one gate in `pagerank.py` drops operational ids
(`workflow/`-path docs, their anchors and the concepts that `denote` them) from PageRank adjacency,
`concept_df`, the mentions BM25 statistics and co-occurrence. Context and scan then rank those hits
last unless the query names that doc or anchor. So R1's doc stratum still draws gold only from GMD
docs OUTSIDE `workflow/`. A gold section under `workflow/` would measure G22's demotion, not 21.4's
ranking. The restriction is not lifted. Save-states are never gold (R1: memories and sessions are
out). {#q8-b}

**The catalog copy's order** (bsd-spec-t3ab r3 m4). 21.4's ONE catalog copy, which R2's table and
every R3 candidate use, is taken after bug-216's live re-derive (queue item 1) and BEFORE G22 rev
2's gate deploys (item 6 precedes item 9). `REPORT.md` records the deployed sha the copy was taken
at. If G22 has landed by the time the copy is taken, the run records that, and the measurement
re-scores on a pre-G22 copy (built from the last pre-G22 deployed sha in a throwaway store),
rather than attributing G22's rank shift to a 21.4 candidate. {#q8-copy-order}

rel: depends-on -> [[plan-review-2026-11-13#lead]]
