---
gmd: "0.1"
id: task-21.4-surfaces-and-nl-ranking
title: "Task 21.4: measure and fix natural-language context ranking, then rewrite every steering surface to one rule"
tags: [task, context, ranking, docs, agent, eval]
metadata:
  node_type: task
  status: pending
  created: 2026-10-07
  updated: 2026-10-14
---

# Task 21.4: NL ranking, then the surfaces {#root}

> Plan: [plan-21-agent-context-usage](../plan-21-agent-context-usage.md)
> Status: Pending (revision after the 2026-10-14 decision log)
> Wave: 3
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
   - **Source:** real NL queries from this project's `.refmatrix/query.log` (`kind=context` NL rows
     and concept-OR grep rows with their eventual answers), filtered by 21.1's
     `is_test_artifact_row` and with `invocation=internal` rows and the 2026-10-07T11:06:35-11:07:13
     replay window excluded. The global log is not a source (it holds other trees' queries).
   - **Who drafts:** a dedicated agent whose brief forbids reading the ranking code
     (`src/refmatrix/context.py`, `src/refmatrix/reranker.py`, and the rerank ops in `daemon.py`);
     its tool-call list is kept with the set's provenance, and a check fails the set if any Read of
     those paths appears. A question whose gold lies in those files is excluded. The tuner (the
     agent or session doing R3) never edits the set.
   - **Approval:** the user approves the drafted set (redacted form) before it is frozen.
   - **Privacy (d8f):** the RAW set stays local under `eval/production/context_nl/raw/`
     (gitignored). Committed: the sha256 of the raw set's canonical JSON, recorded in
     [[#frozen-hash]], and a REDACTED fixture (absolute paths, hostnames and non-refmatrix tree names
     scrubbed; the question text otherwise kept) with its own sha256. All runs and tests use the
     redacted fixture.
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
   - The regenerated `.refmatrix/CLAUDE.md` ships in the C11 install-hooks window (bsd #m-5).

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
