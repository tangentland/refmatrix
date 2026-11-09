---
gmd: "0.1"
id: task-bug179-lint-ingest-anchor-parity
title: "Task bug-179: lint and ingester agree on block anchors"
tags: [task, bug-179, gmd, lint, ingest, anchors]
metadata:
  node_type: task
  status: drafting
  created: 2026-11-09
  updated: 2026-11-09
---

# Task bug-179: lint and ingester agree on block anchors {#root}

> Status: Drafting. The spec was written 2026-11-09 for the pre-plan-24 queue, with decisions taken
> as the user would and recorded with their rationale. Revision round 1 ([[#rev-round-1]]) folds
> spec review r1. **Approval is pending user consent for the viascope step** ([[#r7]] (b)): it
> edits another repo, so it cannot be decided as the user would.
> Depends on: none. Touches the upstream GMD repo (`~/claude_tools/gmd`) as well as this one, and,
> gated on consent, one line in viascope.

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
  body line, `rel:` lines included, and only afterwards does `:288` handle `rel:`, keyed on
  `line.startswith("rel:")`. {#f-lint}
- **ingester**: `_ID_RE` (`src/refmatrix/ingest_gmd.py:150`), with three divergences:
  (a) the heading branch at `:355` runs `_ID_RE.search(rest)` on the RAW heading, without stripping
  inline code, and takes only the first match; its title is `_ID_RE.sub("", rest)` (`:358`),
  which strips EVERY anchor-shaped token, quoted ones included;
  (b) the `rel:` branch at `:382` `continue`s before any anchor scan, so a `{#id}` on a `rel:` line
  never becomes a node, but only when `_REL_RE` matches: a malformed `rel:`-prefixed line falls
  through to the body branch and registers its id;
  (c) the body branch at `:400` runs `_ID_RE.search(scan)` and takes the first match only. {#f-ingest}
- **Canonical tooling**: `~/claude_tools/gmd/` is its own git repo
  (`git@github.com:tangentland/graph_markdown.git`, head `8a65aa2` "Make the two lint gates
  canonical, and testable"). `tools/gmd/lint.py` here is a vendored copy and is byte-identical to
  it today (`diff` empty). `docs/gmd/SPEC.md` differs from upstream `SPEC.md` only in its `id:`
  line. Upstream owns gate behaviour and carries a stdlib gate test,
  `scripts/test-lint-gates.py`. bug-068 (`f393aee`) recorded a "sync gmd tooling" commit
  overwriting a hardening that existed only downstream. The memory-dir lint the global primer names
  is the upstream `~/claude_tools/gmd/lint.py`. {#f-canonical}
- **Sibling parser upstream**: `slice.py` (upstream, and vendored byte-identical at
  `tools/gmd/slice.py`) uses the same `ID_RE` (`:29`) and the same single-run inline-code regex
  (`:35`). Its heading branch runs `ID_RE.search(heading_rest)` on the raw heading at `:131`, and
  its title is `ID_RE.sub("", heading_rest)` at `:135`. That is divergence (a) again. Nothing in
  refmatrix `src/`, `scripts/` or `.claude/` calls it. {#f-slice}
- **Existing multi-anchor lines**: 0 in refmatrix and in every memory dir, and 7 lines in 3 other
  repos. A fence- and inline-code-aware scan using lint's own regexes found none in the refmatrix
  GMD scopes (`docs workflow CLAUDE.md eval src/refmatrix/templates .claude`, 511 docs), in the
  refmatrix memory dir (368 files), in upstream `~/claude_tools/gmd/` (13 docs), or in any of the
  20 memory dirs under `~/.claude/projects/*/memory/` (981 files). In the sibling repos under
  `~/github/atollogy/bdep/`, atldb, atlftpd, cat-herder, orderly, portal, prep_prolific and thiquet
  are clean. viascope, cliquedb and cliquet are not; the lines are listed in [[#f-consumers]].
  Source: [[bsd-bug179-spec-r1-c5f91e4#p-census]] and [[bsd-bug179-spec-r1-c5f91e4#p-fleet]],
  with each line re-read for this revision. {#f-multi-zero}
- **The 7 consumer lines** (git-tracked; re-read 2026-11-09 at viascope `8fd59c8b3`, cliquedb
  `f6e38b2`, cliquet `f138407`). R1 turns each into a lint error. {#f-consumers}
  1. viascope `workflow/bullshit/IMPRESSIONS.md:14`: a bullet carrying 6 packed ids
     (`e2e-specs-absent-pattern`, `skip-on-empty-data-pattern`, `missing-e2e-spec-files`,
     `gql-argument-name-mismatch`, `gql-parameter-name-mismatch`, `stub-handler-pattern`). This is
     the bug-179 incident shape, and 5 of the 6 are already dead in viascope's store. viascope
     vendors nothing: its `scripts/lint-gmd.sh:12` sets the linter to
     `$HOME/claude_tools/gmd/lint.py`, so it is a LIVE consumer of upstream and goes red the moment
     R6's upstream commit lands. {#f-c-viascope}
  2. cliquedb `docs/architecture/adr/adr-0051-numeric-facet-unit-designation.md:1883`: an
     alias-only line `d-render-b` + `d-render-ruled-b-superseded`. {#f-c-cliquedb-1}
  3. cliquedb `docs/architecture/explorations/first-principles-reconstruction.md:389`: a heading
     alias, `emit` + `instance-store`. {#f-c-cliquedb-2}
  4. cliquedb `workflow/plans/p32-hierarchical-storage/p32.t5-designator-fold-spec.md:66`: a prose
     section citation of the form section-sign + anchor (`designator-dedup`, `materialize-read`),
     which registers bogus ids in this doc today. {#f-c-cliquedb-3}
  5. cliquedb `workflow/plans/p32-hierarchical-storage/p32.t4-materialize-read-spec.md:50`: the
     same citation shape (`materialize-read`, `designator-dedup`). cliquedb vendors
     `tools/gmd/lint.py`; its `scripts/lint-gmd.sh` scope is `CLAUDE.md docs/`, so lines 2-3 are in
     its gate and lines 4-5 are ingested but not gated. {#f-c-cliquedb-4}
  6. cliquet `docs/architecture/OPEN.md:495`: `item-15` + `item-17` on one list item.
     {#f-c-cliquet-1}
  7. cliquet `docs/architecture/OPEN.md:508`: `item-30` + `item-31` on one list item. cliquet
     vendors `tools/gmd/lint.py` and its gate scope includes `docs/`. Each second id has 1 inbound
     link and is already dead in the store. An untracked draft copy,
     `tools/decisions/OPEN.draft.md:494` and `:507`, carries the same two lines. It is not counted
     here because it is not committed. {#f-c-cliquet-2}
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
  excluding `__root__` and auto `_hN` ids. Review r1 re-measured this at `c5f91e4` over 494 docs:
  the same 2, with 0 parse errors in 0.33 s. {#f-rel-anchor}
- **Double-backtick inline code**: lint (`lint.py:84`), the ingester (`ingest_gmd.py:156`) and
  `slice.py:35` all strip inline code with a single-run regex (one backtick, non-backticks, one
  backtick). A span opened and closed by TWO backticks is read as two empty spans, so an
  anchor-shaped token quoted inside it is exposed as a real anchor, and a quoted wikilink as a
  link. Both tools are wrong in the same way, so parity holds. Review r1 compared the naive regex
  with a CommonMark backtick-run matcher over every corpus above and found 0 differences in
  anchors and 0 in wikilinks in any GMD doc fleet-wide ([[bsd-bug179-spec-r1-c5f91e4#p-dbl]]).
  {#f-dbl}
- **Gates**: `scripts/lint-gmd.sh` runs the vendored lint over `CLAUDE.md docs/ workflow/ eval/
  .claude/PROJECT_PROFILE.md` plus the memory dir. Its error set is not fixed (13 at `c5f91e4`,
  some from specs other agents are editing), so it is compared as a set of error texts. `.git/hooks`
  has no pre-commit. The PostToolUse `~/.claude/hooks/lint-memory-gmd.sh` is referenced by no
  settings file, so it never runs ([[#fu-memory-hook]]). {#f-gates}

## Requirements {#requirements}

1. **R1 One block anchor per line is a lint ERROR.** If a body line (outside fences, after
   inline-code stripping) carries more than one `{#id}`, lint emits
   `error: [multi-anchor] N block ids on one line (…ids…) — SPEC §3 allows one id per block; the
   store registers only the first`. This applies to headings and to body lines. **Only the first
   id is registered**, which matches the ingester. The 2nd and later ids are absent from
   `node_ids`, so a link to one of them is a `dangling-local`/`dangling-anchor` error. That is
   true: the store does not have those ids, and hiding it would recreate the incident. {#r1}
2. **R2 A `{#id}` on a `rel:` line is a lint ERROR and is NOT registered as an anchor.** Per SPEC
   §5 a trailing `{...}` there is the edge's attribute list. Lint emits
   `error: [anchor-on-rel] … a rel: line is not a block; put the id on the paragraph above` and
   leaves the id out of `node_ids`. **Both tools use the same trigger:** any line where
   `line.startswith("rel:")`, well-formed or not. Lint already keys `rel:` handling on that
   prefix. The ingester gains a matching guard: on a `rel:`-prefixed line where `_REL_RE` does
   not match, it skips the anchor scan instead of falling through to the body branch
   ([[#f-ingest]] (b)). A malformed `rel:` line is still lint's `malformed-rel` error. {#r2}
3. **R3 The ingester's heading branch reads anchors from the inline-code-stripped line**
   (`scan`), as its body branch and lint already do. A heading `The X form` whose title holds a
   backtick span quoting `{#x}` and that ends in the real anchor `{#real}` must yield node `real`,
   not `x`. **The title removes only the matched anchor span.** The match is taken on `scan`,
   which has the same length as `line`, so the span maps onto `rest` by the heading-prefix offset
   (the `#` run and its whitespace). The title is `rest` with that one span cut out, then
   stripped. It must not be `_ID_RE.sub("", rest)`, which would also delete the quoted `{#x}`
   from the title. The same edit lands in upstream `slice.py` (`:131` search on the raw heading,
   `:135` title) per [[#f-slice]], so no third parser disagrees. R2's guard and R3 are the two
   `src/` changes. Both are latent today (0 corpus instances), but without them the parity in R5
   does not hold. {#r3}
4. **R3b Inline code is matched as CommonMark backtick runs, in every parser.** Replace the
   single-run inline-code regex at `tools/gmd/lint.py:84`, `src/refmatrix/ingest_gmd.py:156`, and
   `slice.py:35` (upstream and vendored) with one CommonMark-style matcher: an opening run of N
   backticks, not adjacent to another backtick, is closed by the next run of exactly N backticks,
   and everything between is code. The reference pattern is in
   [[bsd-bug179-spec-r1-c5f91e4#p-dbl]]. Masking keeps the line length, so every column offset
   (R3's title cut included) stays valid. Blast radius: 0 anchors and 0 wikilinks change in any
   GMD doc in refmatrix, any memory dir, upstream, or the 13 sibling repos ([[#f-dbl]]). {#r3b}
5. **R4 Fix the two data lines.** In the two plan-14 files named in [[#f-rel-anchor]], move the id
   from the `rel:` line to the end of the paragraph directly above it. Both ids keep their names.
   No inbound references exist, so nothing re-points. {#r4}
6. **R5 Parity is a tested invariant over the real corpus, and it runs in the commit gate.** For
   every GMD doc in scope, lint's registered anchor set equals the ingester's node-id set,
   excluding `__root__` and auto `_hN`. The scope is `scripts/lint-gmd.sh`'s own scope: `CLAUDE.md
   docs/ workflow/ eval/ .claude/PROJECT_PROFILE.md` and the memory dir, which is parsed with
   `parse_gmd(..., memory_ids=True)`. The check is a script, `scripts/check-gmd-parity.py`
   ([[#d6]]). `scripts/lint-gmd.sh` stops `exec`-ing lint: it runs lint, then runs the parity
   script over the same scope with `$ROOT/.venv-eval/bin/python`, and exits non-zero if either
   fails. Both are always run, so one failure does not hide the other. If that interpreter is
   missing, the script path exits 2 with a message naming it, as the missing-linter branch already
   does. It is never skipped silently. The script prints each offending path with its lint-only
   and ingester-only ids. `tests/test_bug179_anchor_parity.py` calls the same script function, so
   the suite and the gate cannot drift apart. This generalises bug-036's one-file test and does not
   replace it. {#r5}
7. **R6 Upstream first, then re-vendor from a pinned sha.** R1, R2, R3's `slice.py` edit and R3b
   land in upstream `~/claude_tools/gmd` (`lint.py`, `slice.py`), with cases added to
   `scripts/test-lint-gates.py`. They are committed in that repo (the user pushes). SPEC §3 gains
   one rule line, "A block carries at most one ID; more than one `{#id}` on a line is an error.",
   and §5 gains "A `rel:` line carries no block ID; `{#…}` there is not an anchor." Both lines go
   into upstream `SPEC.md` and `docs/gmd/SPEC.md`, keeping the only diff the `id:` line. The same
   upstream commit adds a `gmd-migration-guide.md` entry and a commit-message note for [[#r7]] (c).
   **Re-vendor** `tools/gmd/lint.py` and `tools/gmd/slice.py` with
   `git -C ~/claude_tools/gmd show <sha>:lint.py` (and `:slice.py`), where `<sha>` is that upstream
   commit and upstream `git status --short` is empty at the time. Record `<sha>` in the refmatrix
   commit message and in the implementation summary. Re-vendoring from a commit needs no push:
   the user's push publishes the change and does not gate this sequence, so the sequence is
   buildable without a workaround. {#r6}
8. **R7 Consumer rollout.** R1 turns the 7 lines in [[#f-consumers]] into errors in 3 other
   repos. The rollout is part of this task, not a follow-up. {#r7}
   - (a) [[#f-multi-zero]] and [[#d1]] carry the honest census: zero in refmatrix and in every
     memory dir, 7 lines in 3 other repos. Done in revision round 1. {#r7-a}
   - (b) **GATED STEP: requires explicit user consent, because it edits another repo.** Split
     viascope `workflow/bullshit/IMPRESSIONS.md:14` into one id per line, in viascope, as its own
     viascope commit, in the same window as R6's upstream commit. The order is the viascope commit
     first, then upstream, so viascope's gate (which runs upstream lint directly) is never red. The
     6 ids keep their names. Ids with inbound links (at least `e2e-specs-absent-pattern`,
     `skip-on-empty-data-pattern` and `stub-handler-pattern`) need nothing re-pointed. If consent
     is withheld, R6's upstream commit does not land, and the task stops at a recorded gap. That
     gap is never worked around by softening R1 to a warning. Not done; not authorised by this
     revision. {#r7-b}
   - (c) **Vendoring repos (cliquedb, cliquet): a migration note, applied at their next
     re-vendor.** Upstream `gmd-migration-guide.md` and the upstream commit message list
     [[#f-c-cliquedb-1]] to [[#f-c-cliquet-2]] with the fix for each shape: one id per line; drop a
     heading alias or move it to its own body line; backtick a section-sign + anchor prose citation
     so it stops registering a bogus id. Their vendored lint does not change until they re-vendor,
     so nothing breaks today. This task does not edit cliquedb or cliquet. {#r7-c}
   - (d) Memory dirs need nothing: all 981 files across the 19 non-empty dirs are clean, so plan-27
     needs no migration note. {#r7-d}

## Acceptance criteria {#acceptance}

1. **AC-1 (RED at HEAD, lint)** A fixture body line `- a {#one} b {#two}` makes `lint.py` exit
   non-zero with `[multi-anchor]`, and `one` is in `parse_doc(...).node_ids` while `two` is not.
   The same holds for a heading `## T {#h1} {#h2}`: `h1` present, `h2` absent. At HEAD both exit 0
   and both ids are registered. {#ac-1}
2. **AC-2 (RED at HEAD, lint)** A fixture `rel: related-to -> [[x]] {#on-rel}` makes lint emit
   `[anchor-on-rel]`, and `on-rel` is absent from `parse_doc(...).node_ids`. At HEAD it is
   present. A malformed `rel:`-prefixed line ending in `{#on-bad}` leaves `on-bad` out of BOTH
   tools' sets (lint also emits `malformed-rel`). At HEAD both tools register it. {#ac-2}
3. **AC-3 (RED at HEAD, ingest)** The R3 fixture heading (backtick-quoted `{#x}` in the title,
   real anchor `{#real}` at the end) gives `parse_gmd` a node `real` and no node `x`, and the
   node's title still contains the quoted backtick span with `{#x}` intact. At HEAD it yields `x`.
   Upstream `slice.py` gives the same id and title for the same fixture. {#ac-3}
4. **AC-3b (RED at HEAD, both tools)** The fixture lives INSIDE `tests/test_bug179_anchor_parity.py`
   as a string literal and is never quoted in prose, because a double-backtick span in a GMD doc
   trips the very bug it tests. It is a list item holding a double-backtick inline-code span that
   quotes anchor `x`, followed by the real anchor `y`. Lint, `parse_gmd`, and `slice.py` each
   register only `y`. At HEAD each registers `x`. {#ac-3b}
5. **AC-4 (regression, the incident itself)** The `efa5f33` blob of `IMPRESSIONS.md`, committed as
   a fixture under `tests/fixtures/` or regenerated from `git show` inside the test, makes lint
   exit non-zero with exactly 12 `[multi-anchor]` errors. {#ac-4}
6. **AC-5 (parity: real corpus plus a synthetic fixture)** R5's script over R5's scope: for every
   GMD doc, lint anchor set == ingester node-id set. RED at HEAD on exactly the 2 files in
   [[#f-rel-anchor]]. **GREEN after R2**; R4 is not needed for AC-5 and instead clears AC-5b. It
   also runs over a synthetic fixture doc held in the test file, with one instance of every shape
   in this spec (multi-anchor body line and heading, `rel:` anchor, malformed `rel:` anchor,
   backtick-quoted heading anchor, double-backtick span). The real corpus is clean, so the
   fixture is what makes a one-sided revert visible ([[feedback_clean_corpus_hides_a_dead_gate]]).
   It reports the offending path and ids on failure. {#ac-5}
7. **AC-5b (corpus clean)** Over the same scope, lint reports zero `[multi-anchor]` and zero
   `[anchor-on-rel]` issues. RED after R1+R2 until R4 lands (the 2 plan-14 lines), and GREEN
   after R4. A parity test proves the two parsers agree. AC-5b proves the corpus is clean.
   {#ac-5b}
8. **AC-6 (no false positives)** The 114 mid-line single-anchor lines in [[#f-midline]] still lint
   clean. The SET of error texts from `./scripts/lint-gmd.sh` after R4 lands is a subset of the
   set at the base commit, compared by text as in AC-9 rather than by count. No new error code
   appears, and the allowed delta is none. {#ac-6}
9. **AC-7 (mutations, each must FAIL a test, not hang)** (a) Revert R1's `len > 1` check: AC-1
   and AC-4 fail. (b) Re-register rel-line ids in lint: AC-2 fails. (c) Revert R3 to `rest`: AC-3
   fails. (c2) Revert R3's title cut to `_ID_RE.sub`: AC-3 fails on the title. (d) Restore one
   plan-14 data line: AC-5b fails. (e) Revert R3b on one side only (lint or ingester): AC-3b and
   AC-5's synthetic fixture fail. (f) Restore `exec` of lint alone in `scripts/lint-gmd.sh`:
   AC-10 fails. Commit the fix before running the mutation loop, and restore each mutation in its
   own command. {#ac-7}
10. **AC-8 (upstream holds it)** `python3 ~/claude_tools/gmd/scripts/test-lint-gates.py` exits 0
    with the new multi-anchor, anchor-on-rel and double-backtick cases. `tools/gmd/lint.py` and
    `tools/gmd/slice.py` equal `git -C ~/claude_tools/gmd show <sha>:lint.py` and `:slice.py`
    byte-for-byte, where `<sha>` is the recorded upstream commit and upstream was clean at
    re-vendor time. `<sha>` appears in the refmatrix commit message and the summary. The SPEC diff
    is only the `id:` line. {#ac-8}
11. **AC-9** The full suite shows no new failures relative to `9901589`, compared by error text.
    `tests/test_gmd_body_anchors.py` stays green unchanged. {#ac-9}
12. **AC-10 (the gate runs parity)** The test builds a throwaway ROOT under a short `mkdtemp()`.
    It holds a copy of `scripts/lint-gmd.sh` and `scripts/check-gmd-parity.py`, a symlinked
    `.venv-eval`, the minimal scope paths, and a vendored `tools/gmd/lint.py` with R2's
    non-registration reverted. A fixture doc there carries an anchor on a `rel:` line. Lint alone
    no longer flags that doc, so only parity can. The real shell script, run from that ROOT, exits
    non-zero and names the doc and the id. Over the unmutated copy it exits 0. The test runs the
    shell script, not the Python function. {#ac-10}
13. **AC-11 (consumer rollout recorded)** [[#f-consumers]] lists all 7 lines. The upstream
    `gmd-migration-guide.md` entry names the cliquedb and cliquet lines. Either the viascope
    commit sha is recorded in the implementation summary (consent given) or the summary records
    the R7 (b) gap and R6's upstream commit did not land (consent withheld). {#ac-11}

## Files to modify {#files}

Upstream repo `~/claude_tools/gmd/`: `lint.py`, `slice.py`, `scripts/test-lint-gates.py`,
`SPEC.md`, `gmd-migration-guide.md`.

This repo: `tools/gmd/lint.py` and `tools/gmd/slice.py` (re-vendored from the pinned sha),
`docs/gmd/SPEC.md`, `src/refmatrix/ingest_gmd.py` (heading branch, R3; `rel:` guard, R2; inline-code
regex, R3b), `scripts/check-gmd-parity.py` (new, R5), `scripts/lint-gmd.sh` (calls it, R5),
`workflow/plans/plan-14-grep-learning-measurement.md` and
`workflow/plans/plan-14-grep-learning-measurement-tasks/task-14.4-replay-measurement.md` (R4).
New tests: `tests/test_bug179_anchor_parity.py`, plus a fixture if AC-4 vendors the blob.
Also `workflow/bug_registry.md` (the bug-179 row) and the implementation summary
`workflow/implementation_summaries/bug-179-lint-ingest-anchor-parity.md`.

Another repo, **gated on explicit user consent** ([[#r7-b]]): viascope
`workflow/bullshit/IMPRESSIONS.md` (line 14 only), in its own viascope commit.

## Decisions {#decisions}

- **d1. Lint errors on more than one anchor per line. The ingester does NOT register them all.**
  The SPEC already says one id per block. There are zero multi-anchor lines in refmatrix and in all
  memory dirs, and 7 lines in 3 other repos ([[#f-consumers]]). R7 handles those: a gated split
  in viascope, which runs upstream lint directly, and a migration note for the two vendoring repos.
  The error fires at the gate that actually runs on a docs commit. Having the ingester register
  every id would invent semantics SPEC lacks: which text is each id's title, and which id owns the
  line's `rel:` edges? It would also quietly legitimise the packing that caused the incident. The
  viascope line is that packing, with 5 of its 6 ids already dead. {#d1}
- **d2. "At end of block" is NOT enforced.** 114 bold-lead mid-line anchors exist, and both parsers
  agree on them. Enforcing position would be churn with no parity or graph benefit. If wanted,
  SPEC wording can be loosened separately. {#d2}
- **d3. `rel:`-line ids are an error rather than adopted by the ingester.** SPEC §5 already gives
  that `{...}` slot to edge attributes, so lint, not the ingester, is the one out of spec. The two
  live instances move to their paragraph at no cost. {#d3}
- **d4. Upstream first.** `~/claude_tools/gmd` is canonical ([[#f-canonical]]). A fix made only in
  the vendored copy is exactly the shape bug-068 lost to the next sync. The upstream gate test is
  what stops a future sync from reverting it silently. {#d4}
- **d5. The parity check spans the corpus, and it runs where docs commits are checked.** bug-036's
  one-file parity test was right but too narrow, and suite-only. The corpus-wide version catches
  the next divergence of this class (it already found the `rel:`-line case). Putting it in
  `scripts/lint-gmd.sh` ([[#r5]]) makes the general invariant, not just R1/R2's two shapes, part
  of the gate that runs on a docs commit. {#d5}
- **d6. The parity script lives at `scripts/check-gmd-parity.py`, not `tools/gmd/parity.py`.** It
  imports `refmatrix.ingest_gmd.parse_gmd`, which pulls in `refmatrix.store`. That makes it
  refmatrix-specific, so it needs the dev venv rather than bare `python3`. `tools/gmd/` is the
  vendored mirror of upstream, re-vendored from a sha ([[#r6]]). A refmatrix-only file there
  would either be flagged as drift or be lost to the next sync, which is the bug-068 shape.
  `scripts/` already holds refmatrix's own `lint-gmd.sh`, which differs from upstream's, and the
  script is its sibling. {#d6}
- **d7. The double-backtick bug is folded in as R3b, not filed separately.** It is the same regex
  in the same three files R1-R3 already edit. R3 makes inline-code stripping load-bearing for
  heading parity. A separate row would mean a second upstream commit and a second re-vendor. Its
  measured blast radius is 0 ([[#f-dbl]]). {#d7}
- **d8. The ingester adopts lint's `rel:` trigger, not the other way round.** A trigger keyed on
  `startswith("rel:")` makes parity unconditional. The alternative, "malformed-rel is already a
  lint error, so it never reaches parity", leans on a separate gate being run, and that is the
  assumption this bug disproved. {#d8}

## Non-goals and follow-ups {#non-goals}

- **Fixing cliquedb or cliquet in this task.** They vendor lint and are unaffected until their
  next re-vendor. They get a migration note ([[#r7-c]]), not an edit. {#ng-vendoring}
- **Enforcing anchor position** ([[#d2]]). {#ng-position}
- **Follow-up, not this task's: the memory-lint hook is unwired.**
  `~/.claude/hooks/lint-memory-gmd.sh` is referenced by no settings file (`~/.claude/*.json`: 0
  hits), so the PostToolUse memory lint that MEMORY-RULES describes never runs. That predates
  bug-179, and the escape analysis must not assume it. The orchestrator logs it as its own
  bug-registry row. This spec does not edit `workflow/bug_registry.md` for it.
  {#fu-memory-hook}
- **Follow-up: upstream `audit.py:257` registers every anchor match.** It has no refmatrix
  caller. If it is kept, the upstream commit either aligns it with R1 or files an upstream row,
  following the same "no third parser that disagrees" rule as [[#f-slice]]. {#fu-audit}

## Revision round 1 (2026-11-09) {#rev-round-1}

Folds the ch-bsd spec review r1 at `c5f91e4` (DIRTY, 0 BULLSHIT, 3 SKETCHY, 7 MEH). Each finding
and where it landed:

- **s1** (R1 upstream turns viascope red; vendoring repos break on re-vendor): [[#r7]] (a-d),
  [[#f-multi-zero]] scoped honestly, [[#f-consumers]] with all 7 lines re-read, [[#d1]]
  corrected, [[#ac-11]]. The viascope edit is a gated step pending consent, not done.
  {#rr1-s1}
- **s2** (AC-7(d) could not fail): [[#ac-5b]] added, [[#ac-5]] reworded to "GREEN after R2", and
  [[#ac-7]] (b) now "AC-2 fails" and (d) now "AC-5b fails". {#rr1-s2}
- **s3** (the general invariant was suite-only): [[#r5]] makes parity a script run by
  `scripts/lint-gmd.sh`, [[#d6]] gives the location, [[#ac-10]] plants a divergence, [[#d5]] is
  reworded, and [[#fu-memory-hook]] records the unwired hook. {#rr1-s3}
- **m1** (first-only registration): [[#r1]], [[#ac-1]]. {#rr1-m1}
- **m2** (heading title derivation): [[#r3]], [[#ac-3]], [[#ac-7]] (c2). {#rr1-m2}
- **m3** (`rel:` trigger parity): [[#r2]], [[#f-ingest]] (b), [[#d8]], [[#ac-2]]. {#rr1-m3}
- **m4** (stale lint baseline count): [[#ac-6]] compares the error-text set; [[#f-gates]].
  {#rr1-m4}
- **m5** (AC-8 had no pinned source): [[#r6]] re-vendors from a sha, [[#ac-8]]. {#rr1-m5}
- **m6** (upstream `slice.py:131`): [[#f-slice]], [[#r3]], [[#r6]], [[#fu-audit]]. {#rr1-m6}
- **m7** (double-backtick inline code): [[#r3b]], [[#f-dbl]], [[#ac-3b]], [[#ac-7]] (e),
  [[#d7]]. {#rr1-m7}

Status stays `drafting`. Every review question is resolved in the spec except one: **approval is
pending user consent for the viascope step** ([[#r7-b]]).

rel: derives-from -> [[bsd-bug179-spec-r1-c5f91e4]]
