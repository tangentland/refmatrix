---
gmd: "0.1"
id: task-27.2a-index-prose-to-memories
title: "Task 27.2a: convert hand-written MEMORY.md prose into memory files so the index fits its budget — viascope (94% prose) and any dir over 50%"
tags: [task, plan-27, memory-index, prose, viascope, budget]
metadata:
  node_type: task
  status: pending
  plan: plan-27-memory-fleet-rollout
  created: 2026-11-09
---

# Task 27.2a: index prose → memories {#root}

> Plan: [[plan-27-memory-fleet-rollout]]
> Status: Pending
> Depends on: [[task-27.1-fleet-inventory]] (`prose_chars` per dir). Runs BEFORE
> [[task-27.2-viascope2-fold-and-repoint]]'s apply, because 26.5 AC-3 refuses an apply whose
> index render would refuse. Also before [[task-27.6-per-store-compile-and-landing]].

rel: part-of -> [[plan-27-memory-fleet-rollout]]
rel: depends-on -> [[task-27.1-fleet-inventory]]
rel: depends-on -> [[task-26.1-layout-module-and-index-walk]]
rel: reinforces -> [[feedback_decay_never_loses_knowledge]]
rel: reinforces -> [[feedback_verify_memory_by_recall_not_get]]

## Why {#why}

ch-bsd r2 measured how much of each dir's index budget hand-written `MEMORY.md` prose takes:

| dir | prose chars | share of the 24,000-char budget |
|---|---|---|
| viascope | 22,643 | 94% |
| cliquedb | 4,850 | 20% |
| viascope2 | 848 | 4% |
| cliquet | 512 | 2% |

In viascope, 26.1's carried-prose rule leaves under 25% of the budget for entries, so every
organise apply, save-state and bridge there refuses the index. That refusal is certain, not
conditional. The prose is real knowledge: headers, a session log, an "Active Campaign" block. It
must become memories that recall can reach. It must not be dropped (rule 9a: the deferral is
anchored here).

## Requirements {#requirements}

1. **AC-1: scope.** Every dir whose 27.1 `prose_chars` is over 50% of the budget. Today that is
   viascope only. The others stay carried.
2. **AC-2: convert, with a checker that is a reviewed artifact (r3 s3).**
   - **Unit.** A prose block is a header and its PROSE lines up to the next header. A grouping
     header whose block holds only ENTRY lines (`- [..](..)`, for example
     `### Security & Operational Safety`) has no prose. It stays carried as a header in the index
     and is not converted.
   - **Branches.** Each prose block becomes one of:
     - **(a) a memory.** A `project/` memory file in MEMORY-RULES shape: GMD, lint-clean,
       `originSessionId: plan-27-27.2a`, `created:` today. The block's lines are in its body
       verbatim.
     - **(b) a quote plus an ADR link.** Used when the block restates a viascope ADR or doc. The
       memory quotes the block verbatim in a `> ` blockquote and carries
       `rel: derives-from -> [[<adr-id>]]`. The lines therefore stay checkable in the memory
       itself; the ADR file is not trusted to contain them.
   - **GMD headers.** Every header copied into a memory gets an `{#anchor}`, per the GMD rule.
     viascope's 17 index headers are all un-anchored today.
   - **The checker** is `tools/prose_conversion_check.py`, with its test
     `tests/test_prose_conversion.py`.
     - It enumerates every prose line of the pre-conversion `MEMORY.md`.
     - It passes only if each line is found in some converted memory's body (branch a, or the
       blockquote of branch b) or is still carried in `MEMORY.md`.
     - Comparison uses ONE normalisation: strip a trailing ` {#…}` anchor suffix and a leading
       `> ` quote marker, nothing else. Headers are therefore compared by TEXT, not by anchor.
     - It prints every missing line with its line number.
   - **The checker's RED cases**, in `tests/test_prose_conversion.py` with a committed fixture.
     The fixture is a synthetic prose block in viascope's shape (headers, a dated session log, an
     "Active Campaign" block, a grouping header over entries) plus a converted set. No live
     viascope text goes into the public repo.
     - (a) Drop one line from a converted memory: the checker FAILS and names that line.
     - (b) A header copied with an appended `{#anchor}`: the checker PASSES.
     - (c) A branch-(b) memory missing its blockquote: the checker FAILS.
     - (d) A grouping-only header: not required in any memory, and still carried.
   - The authoring agent is `@ch-doc-writer` or `@gmd-curator`. It writes NEW files into the
     memdir's `project/` folder.
   - The checker runs on the live result BEFORE AC-3's removal. It runs again in 27.6 after the
     index regenerates.
3. **AC-3: the user reviews the converted set before anything is removed from `MEMORY.md`.**
   - The agent presents a table: block → new memory id (or ADR link) → char count.
   - Only after the user approves are the converted blocks removed from the index. They are
     replaced by one pointer line per block: `- [<title>](project/<id>.md) — <hook>`.
   - Unapproved blocks stay carried.
4. **AC-4: budget.** After the conversion, the `rmx memory organise <viascope memdir>` preview
   must report `index: ok`. Carried prose must be at most 25% of the budget (6,000 chars). Below
   the 26.1 refusal line is the hard minimum.
5. **AC-5: reachable.** After 27.2's apply bridges them into viascope's store,
   `rmx memory recall "<phrase unique to a converted block>"` returns its new memory. The check
   uses recall, not `memory get`.
6. **AC-6: git.**
   - viascope's memdir is tracked by the viascope repo. The new files and the `MEMORY.md` edit are
     staged (`git add`).
   - The user commits in the viascope repo.
   - A backup of the pre-conversion `MEMORY.md` lands in `~/.refmatrix/backups/memory-organise/`
     first.

## Files to Create / Modify {#files}

- Create the live viascope memdir `project/*.md` files (converted memories). The user approves
  them, and they are staged in the viascope repo.
- Modify the live viascope `MEMORY.md`: converted blocks are replaced by pointer lines.
- Create `workflow/review-output/27.2a-prose-conversion.log`: the checker output, the block
  table and the user's approval.
- Create `tools/prose_conversion_check.py`: the lossless checker (r3 s3).
- Create `tests/test_prose_conversion.py` and `tests/fixtures/prose_conversion/`: RED cases (a)
  through (d), with a synthetic fixture.

## Test Strategy {#test-strategy}

- This is a live curation, with a checker.
- `tests/test_prose_conversion.py` goes RED first. Case (a) fails at HEAD because the checker
  does not exist yet.
- Then the checker runs on a COPY of viascope's `MEMORY.md` and the converted set, in a
  `mkdtemp()` dir.
- No store writes happen here; 27.2's apply does the bridge.
- The 26.5 preview's `index:` field is the gate.

## Revision round 3 (2026-11-09) {#rev-round-3}

Answers [[bsd-plan26-27-spec-review-r3-696c3cb]].

| finding | change | anchor |
|---|---|---|
| s3 (no checker artifact, no RED, the ADR branch unverifiable, verbatim headers vs GMD anchors) | Named checker script and test with a synthetic fixture; RED (a) planted loss fails and names the line, (b) an anchored header passes under ONE normalisation, (c) a missing quote fails, (d) a grouping header stays carried; the ADR branch quotes the block verbatim; the 17 headers are anchored and compared by text | AC-2, [[#files]], [[#test-strategy]] |
