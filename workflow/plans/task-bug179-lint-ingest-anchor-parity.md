---
gmd: "0.1"
id: task-bug179-lint-ingest-anchor-parity
title: "Task bug-179: lint and ingester agree on block anchors"
tags: [task, bug-179, gmd, lint, ingest, anchors]
metadata:
  node_type: task
  status: drafting
  created: 2026-11-09
---

# Task bug-179: lint and ingester agree on block anchors {#root}

> Status: Drafting (spec written 2026-11-09 for the pre-plan-24 queue; decisions below are taken as
> the user would and recorded with their rationale).
> Depends on: none. Touches the upstream GMD repo (`~/claude_tools/gmd`) as well as this one.

rel: derives-from -> [[bug_registry]]
rel: derives-from -> [[refmatrix/gmd-spec#block-ids]]
rel: depends-on -> [[refmatrix/gmd-spec#typed-edges]]
rel: motivates -> [[bsd-impressions#former-anchors]]
rel: part-of -> [[plan-of-plans#goal-2026-11-09]]
rel: reinforces -> [[feedback_clean_corpus_hides_a_dead_gate]]

## Why {#why}

`tools/gmd/lint.py` collects every `{#id}` on a line. The store ingester
(`src/refmatrix/ingest_gmd.py`, `parse_gmd`) registers only the first. On 2026-11-09 commit
`efa5f33` compacted `workflow/bullshit/IMPRESSIONS.md` and put 200 former-anchor ids on 12 lines
(7-30 per line) to fit the 50-line cap. Lint, which is the commit gate (CLAUDE.md
`#before-commit`), passed with 0 errors. Meanwhile 188 of the 200 ids resolved to
`(unknown symbol)` in `rmx context`. This spec re-measured both numbers on the `efa5f33` blob: 12
lines and 200 ids by a fence- and inline-code-aware scan, `lint.py` 0 errors, and 188 ids that lint
registers but `parse_gmd` does not. `4c1e2a0` fixed the data (one id per line). The two tools
still disagree. {#why-fact}

This is the second time the two parsers have disagreed on what an anchor is. bug-036
(`tests/test_gmd_body_anchors.py`) found lint treating body anchors as nodes while the ingester
did not, and closed that with a parity test scoped to ONE file. That test would have failed at
`efa5f33`, but nobody runs the full suite on a docs-only commit. The gate that does run on that
commit is lint, so that is where the check has to live. {#why-second}

## Facts at HEAD `9901589` (read, not recalled) {#facts}

- **SPEC §3** (`docs/gmd/SPEC.md:94-119`): an ID MAY appear "at end of heading, paragraph, list
  item, blockquote, code fence info string, or table row". That is one id at the end of a block.
  Nothing in it permits several ids in one block, and neither tool enforces "at end". {#f-spec3}
- **SPEC §5** (`docs/gmd/SPEC.md:131-145`): a `rel:` line is `rel: <verb> -> <target> [{attrs}]`
  and must occupy the whole line. A trailing `{...}` on a `rel:` line is therefore the edge's
  attribute list, not a block id. {#f-spec5}
- **lint**: `ID_RE` (`tools/gmd/lint.py:71`). The anchor loop at `:268-285` runs
  `ID_RE.finditer(strip_inline_code(line))` and registers EVERY match. It runs on every non-fence
  body line, `rel:` lines included, and only afterwards does `:288` handle `rel:`. {#f-lint}
- **ingester**: `_ID_RE` (`src/refmatrix/ingest_gmd.py:150`), with three divergences:
  (a) the heading branch at `:355` runs `_ID_RE.search(rest)` on the RAW heading, without stripping
  inline code, and takes only the first match;
  (b) the `rel:` branch at `:382` `continue`s before any anchor scan, so a `{#id}` on a `rel:` line
  never becomes a node;
  (c) the body branch at `:400` runs `_ID_RE.search(scan)` and takes the first match only. {#f-ingest}
- **Canonical tooling**: `~/claude_tools/gmd/` is its own git repo
  (`git@github.com:tangentland/graph_markdown.git`, head `8a65aa2` "Make the two lint gates
  canonical, and testable"). `tools/gmd/lint.py` here is a vendored copy and is byte-identical to
  it today (`diff` empty). `docs/gmd/SPEC.md` differs from upstream `SPEC.md` only in its `id:`
  line. Upstream owns gate behaviour and carries a stdlib gate test,
  `scripts/test-lint-gates.py`. bug-068 (`f393aee`) recorded a "sync gmd tooling" commit
  overwriting a hardening that existed only downstream. The memory-dir lint the global primer names
  is the upstream `~/claude_tools/gmd/lint.py`. {#f-canonical}
- **Existing multi-anchor lines**: 0. A fence- and inline-code-aware scan of every GMD file in
  `docs/`, `workflow/` and `CLAUDE.md` (483 docs) found none, and so did the same scan over the
  memory dir `~/.claude/projects/-Users-tholley-claude-tools-refmatrix/memory/**` (368 docs),
  `eval/`, `src/refmatrix/templates/`, `.claude/` and `~/claude_tools/gmd/`. {#f-multi-zero}
- **Mid-line single anchors are common and legitimate**: 98 lines in docs/workflow and 16 in
  memory use the bold-lead shape (`- **d-1. Title** {#d-1}. Body…`, the AC lists in task specs, and
  the ADR-0000 bullets). Both parsers register these identically, so they are not a parity problem.
  Enforcing SPEC's "at end" literally would break 114 lines for no graph gain. {#f-midline}
- **Live anchor-set divergence today**: 2 of 483 docs, both caused by a `{#id}` on a `rel:` line.
  Lint registers the id and the ingester does not.
  `workflow/plans/plan-14-grep-learning-measurement.md:50` (`{#not-evidence}`) and
  `workflow/plans/plan-14-grep-learning-measurement-tasks/task-14.4-replay-measurement.md:86`
  (`{#drain-first}`). No wikilink anywhere in docs/, workflow/, CLAUDE.md or the memory dir targets
  either id. Measured with `lint.parse_doc(p).node_ids` vs `{n.id for n in parse_gmd(p).nodes}`,
  excluding `__root__` and auto `_hN` ids. {#f-rel-anchor}

## Requirements {#requirements}

1. **R1 One block anchor per line is a lint ERROR.** If a body line (outside fences, after
   inline-code stripping) carries more than one `{#id}`, lint emits
   `error: [multi-anchor] N block ids on one line (…ids…) — SPEC §3 allows one id per block; the
   store registers only the first`. This applies to headings and to body lines. The first id
   is still registered, as today, so the error does not cascade into dangling-anchor noise. {#r1}
2. **R2 A `{#id}` on a `rel:` line is a lint ERROR and is NOT registered as an anchor.** Per SPEC
   §5 a trailing `{...}` there is the edge's attribute list. Lint emits
   `error: [anchor-on-rel] … a rel: line is not a block; put the id on the paragraph above` and
   leaves the id out of `node_ids`. That matches the ingester. {#r2}
3. **R3 The ingester's heading branch reads anchors from the inline-code-stripped line**
   (`scan`), as its body branch and lint already do. A heading `The X form` whose title holds a
   backtick span quoting `{#x}` and that ends in the real anchor `{#real}` must yield node `real`,
   not `x`. This is the one `src/` change, and it is latent today (0 corpus
   instances), but without it the parity in R5 does not hold. {#r3}
4. **R4 Fix the two data lines.** In the two plan-14 files named in [[#f-rel-anchor]], move the id
   from the `rel:` line to the end of the paragraph directly above it. Both ids keep their names.
   No inbound references exist, so nothing re-points. {#r4}
5. **R5 Parity is a tested invariant over the real corpus.** For every GMD doc under `docs/`,
   `workflow/`, `eval/` and `CLAUDE.md`, lint's registered anchor set equals the ingester's node-id
   set, excluding `__root__` and auto `_hN`. This generalises bug-036's one-file test and does
   not replace it. {#r5}
6. **R6 Upstream first, then re-vendor.** R1 and R2 land in `~/claude_tools/gmd/lint.py`, with
   cases added to `~/claude_tools/gmd/scripts/test-lint-gates.py`. They are committed in that repo
   (the user pushes). `tools/gmd/lint.py` is then re-vendored byte-identical. SPEC §3 gains one
   rule line, "A block carries at most one ID; more than one `{#id}` on a line is an error.", and
   §5 gains "A `rel:` line carries no block ID; `{#…}` there is not an anchor." Both lines go into
   upstream `SPEC.md` and `docs/gmd/SPEC.md`, keeping the only diff the `id:` line. {#r6}

## Acceptance criteria {#acceptance}

1. **AC-1 (RED at HEAD, lint)** A fixture body line `- a {#one} b {#two}` makes `lint.py` exit
   non-zero with `[multi-anchor]`. The same holds for a heading `## T {#h1} {#h2}`. At HEAD both
   exit 0. {#ac-1}
2. **AC-2 (RED at HEAD, lint)** A fixture `rel: related-to -> [[x]] {#on-rel}` makes lint emit
   `[anchor-on-rel]`, and `on-rel` is absent from `parse_doc(...).node_ids`. At HEAD it is
   present. {#ac-2}
3. **AC-3 (RED at HEAD, ingest)** The R3 fixture heading (backtick-quoted `{#x}` in the title,
   real anchor `{#real}` at the end) gives `parse_gmd` a node `real` and no node `x`. At HEAD it
   yields `x`. {#ac-3}
4. **AC-4 (regression, the incident itself)** The `efa5f33` blob of `IMPRESSIONS.md`, committed as
   a fixture under `tests/fixtures/` or regenerated from `git show` inside the test, makes lint
   exit non-zero with exactly 12 `[multi-anchor]` errors. {#ac-4}
5. **AC-5 (parity, real corpus)** R5's test: for every GMD doc in scope, lint anchor set ==
   ingester node-id set. RED at HEAD on exactly the 2 files in [[#f-rel-anchor]]. GREEN after R2+R4.
   It reports the offending path and ids on failure. {#ac-5}
6. **AC-6 (no false positives)** The 114 mid-line single-anchor lines in [[#f-midline]] still lint
   clean. `./scripts/lint-gmd.sh` error count is no higher than at HEAD (12, all pre-existing
   dangling-doc/no-gmd-version) once R4 lands. {#ac-6}
7. **AC-7 (mutations, each must FAIL a test, not hang)** (a) revert R1's `len > 1` check, and
   AC-1/AC-4 fail; (b) re-register rel-line ids in lint, and AC-2/AC-5 fail; (c) revert R3 to `rest`,
   and AC-3 fails; (d) restore one plan-14 data line, and AC-5 fails. Commit the fix before running
   the mutation loop, and restore each mutation in its own command. {#ac-7}
8. **AC-8 (upstream holds it)** `python3 ~/claude_tools/gmd/scripts/test-lint-gates.py` exits 0 with
   the new multi-anchor and anchor-on-rel cases. `diff ~/claude_tools/gmd/lint.py tools/gmd/lint.py`
   is empty. The SPEC diff is only the `id:` line. {#ac-8}
9. **AC-9** The full suite shows no new failures relative to `9901589`, compared by error text.
   `tests/test_gmd_body_anchors.py` stays green unchanged. {#ac-9}

## Files to modify {#files}

Upstream repo `~/claude_tools/gmd/`: `lint.py`, `scripts/test-lint-gates.py`, `SPEC.md`.

This repo: `tools/gmd/lint.py` (re-vendored byte-identical), `docs/gmd/SPEC.md`,
`src/refmatrix/ingest_gmd.py` (heading branch only, R3),
`workflow/plans/plan-14-grep-learning-measurement.md` and
`workflow/plans/plan-14-grep-learning-measurement-tasks/task-14.4-replay-measurement.md` (R4).
New tests: `tests/test_bug179_anchor_parity.py`, plus a fixture if AC-4 vendors the blob.
Also `workflow/bug_registry.md` (the bug-179 row) and the implementation summary
`workflow/implementation_summaries/bug-179-lint-ingest-anchor-parity.md`.

## Decisions {#decisions}

- **d1. Lint errors on more than one anchor per line. The ingester does NOT register them all.**
  The SPEC already says one id per block, and there are zero legitimate multi-anchor lines anywhere
  in the corpus or the memory dir, so the error breaks nothing. It also fires at the gate that
  actually runs on a docs commit. Having the ingester register every id would invent semantics
  SPEC lacks: which text is each id's title, and which id owns the line's `rel:` edges? It would
  also quietly legitimise the packing that caused the incident. {#d1}
- **d2. "At end of block" is NOT enforced.** 114 bold-lead mid-line anchors exist, and both parsers
  agree on them. Enforcing position would be churn with no parity or graph benefit. If wanted,
  SPEC wording can be loosened separately. {#d2}
- **d3. `rel:`-line ids are an error rather than adopted by the ingester.** SPEC §5 already gives
  that `{...}` slot to edge attributes, so lint, not the ingester, is the one out of spec. The two
  live instances move to their paragraph at no cost. {#d3}
- **d4. Upstream first.** `~/claude_tools/gmd` is canonical ([[#f-canonical]]). A fix made only in
  the vendored copy is exactly the shape bug-068 lost to the next sync. The upstream gate test is
  what stops a future sync from reverting it silently. {#d4}
- **d5. The parity test spans the corpus, not one file.** bug-036's one-file parity test was right
  but too narrow, and suite-only. The corpus-wide version catches the next divergence of this
  class (it already found the `rel:`-line case). R1/R2 put the cheap half of it in the commit
  gate. {#d5}
