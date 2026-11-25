---
gmd: "0.1"
id: task-b1-f4-f7
title: "B1 residue: the findings ledger tallies by self-audit question (F4) and IMPRESSIONS.md stays under its 50-line cap (F7)"
tags: [task, ch-bsd, ledger, impressions, self-audit, b1]
metadata:
  node_type: task
  status: drafting
  created: 2026-11-24
  author: ch-architect (Fable 5.2)
---

# Task: B1 residue, F4 and F7 {#root}

> Status: drafted for the spec window (L232); the lead approves. Queue row B1.
> Size: **small** (docs, one script, tests; no `src/`). One isolated agent; the lead reads the
> diff. Waits on nothing. Both findings need a build: neither is a pure doc edit.

rel: implements -> [[refmatrix/ch-bsd-assessment-2026-11-23#f4]]
rel: implements -> [[refmatrix/ch-bsd-assessment-2026-11-23#f7]]
rel: depends-on -> [[plan-of-plans#queue]]
rel: depends-on -> [[bsd-open-findings]]
rel: depends-on -> [[bsd-closed-findings]]
rel: depends-on -> [[bsd-impressions]]
rel: related-to -> [[self-audit#loop]]

## Goal {#goal}

**F4.** `INDEX.md`'s by-author leaderboard cannot tell authors apart (136 rows say
"orchestrator") and was last updated at run 54. It is replaced by a tally of **which
[[self-audit]] question missed each BULLSHIT**, derived from the findings ledger by a script,
never kept by hand. The tally is the input [[self-audit#loop]] needs to pick the next lint.
{#goal-f4}

**F7.** `IMPRESSIONS.md` is 404 lines at `160d4633`: 66 run bullets on 90 lines, and a
283-line pointer list that every run reads and every persisted report re-ingests (the file is
the holder named in bug-185). The pointer list moves to its own file and the window is folded
back under 50 lines, with a guard so it stays there. {#goal-f7}

## What is built {#design}

- **D1 A `question` column** in `OPEN.md` and `CLOSED.md`, after `level`. For a row whose level
  is or was re-rated BULLSHIT: `SA-1` to `SA-8` (several allowed), or `none: <the question or
  lint ch-bsd proposed>`. For GATE and SKETCHY rows: `-`. Backfill of the 35 BULLSHIT-level rows
  at `160d4633` (3 open, 32 closed) is read from each row's report; a report that names no
  question gets `unnamed`, which the tally counts apart. {#d1}
- **D2 `scripts/bsd-tally.py`** reads both ledgers and prints: per question, the BULLSHIT count
  (open, closed upheld, closed overruled); every `none:` proposal; the `unnamed` count; F5's
  upheld / overruled rate. It exits 1, naming the row id, for a BULLSHIT-level row with an empty
  or `-` cell, an unknown token, or a row it cannot parse. {#d2}
- **D3 Who fills it.** ch-bsd already names the question per BULLSHIT (its overlay). The lead
  copies it into the row when persisting the report ([[orchestration#reports]] gains the
  clause). Release step 1b ([[orchestration#release]]) runs the tally; the release commit body
  carries its lines. {#d3}
- **D4 The leaderboard is retired.** `INDEX.md` `#leaderboard` gets one closing line (frozen at
  run 54; superseded by the tally). `.claude/agents/ch-bsd.md`
  `#update-leaderboard-in-index-md` is replaced by three lines naming the column and the
  script. The author column of `INDEX.md` stays as history. {#d4}
- **D5 The pointer list gets its own file.** `workflow/bullshit/IMPRESSION_ANCHORS.md`, id
  `bsd-impression-anchors`, holds `## Former anchors, restored` verbatim, one id per line.
  `IMPRESSIONS.md` keeps the id `bsd-impressions` (31.3's ledger selection reads that id) and
  holds only the run window. {#d5}
- **D6 The fold.** The oldest bullets are folded verbatim, ids unchanged, into one new
  `impression_bsd_ledger_*` memory until `IMPRESSIONS.md` is at most 50 lines (the whole file,
  `wc -l`); each folded id gets one pointer line in the register. The agent returns the
  memory's text; **the lead writes the memory file and runs the bridge** (memory-dir and store
  writes are the lead's). {#d6}
- **D7 Citations follow the id.** Every `[[bsd-impressions#<id>]]` whose id now lives in the
  register is rewritten to `[[bsd-impression-anchors#<id>]]` (58 of the 70 cited ids are in
  the pointer list today; 55 files hold a citation; plus the ids folded here). A missed one is a `dangling-anchor` error
  in `./scripts/lint-gmd.sh`, so the gate proves the rewrite. The same step joins the fold
  procedure. {#d7}
- **D8 One cap rule.** `ch-bsd.local.md`'s size-cap paragraph is rewritten: the cap is the
  file, 50 lines; the fold is D6 plus D7. `ch-bsd.md` `#update-impressions-md` loses
  "summarize the oldest 10 … and delete them" for "fold the oldest verbatim into a ledger
  memory; never delete", so base and overlay stop differing. {#d8}

## Acceptance criteria {#acceptance}

- **AC-1 The tally runs on the committed ledger.** `python3 scripts/bsd-tally.py` exits 0 on
  this repo and prints one line per `SA-n`, the `none:` proposals, `unnamed`, and the upheld /
  overruled counts, whose sum equals the BULLSHIT-level row count. Test:
  `tests/test_bsd_findings_ledger.py::test_tally_on_the_committed_ledger` (new file, named for
  the behaviour; the script is run as a subprocess). {#ac-1}
- **AC-2 An unfilled or broken row fails loudly.** One parametrized test plants, in a copy of
  the two ledgers, a BULLSHIT row with an empty cell, one with `-`, one with `SA-9`, and a row
  with a missing column: each run exits 1 and stderr names the row id.
  `…::test_tally_refuses_a_bad_row[case]`. (Mutation: the script skips an unparseable row.)
  {#ac-2}
- **AC-3 The window is under the cap, and the guard can fail.**
  `tests/test_gmd_body_anchors.py::test_impressions_window_is_under_its_cap` asserts
  `IMPRESSIONS.md` is at most 50 lines; the same check on a planted 51-line text fails. {#ac-3}
- **AC-4 The register is addressable.** In `tests/test_gmd_body_anchors.py`:
  `test_the_two_parsers_agree_on_the_ledger_that_exposed_this` is parametrized over both
  files; `test_cited_impression_anchors_resolve_in_the_graph` reads the register; a new case
  asserts every anchored register line carries exactly one id and no id is in both files (a
  planted packed line fails). {#ac-4}
- **AC-5 No citation dangles and no id is lost.** `./scripts/lint-gmd.sh` exits 0. The
  summary pastes the id-set comparison: `imp-*` ids in `IMPRESSIONS.md` at the base sha equal
  the ids in the window, the register and the new memory's text at the head. {#ac-5}
- **AC-6 The rule texts agree.** `grep -n "Leaderboard\|BS Rate" .claude/agents/ch-bsd.md`
  shows only D4's pointer; `ch-bsd.md`, `ch-bsd.local.md`, [[orchestration#reports]] and
  [[orchestration#release]] each name the column, the script and the 50-line file cap once.
  {#ac-6}

## Files {#files}

| File | Change |
|---|---|
| `scripts/bsd-tally.py` (new) | D2 |
| `workflow/bullshit/OPEN.md`, `CLOSED.md` | D1 column and backfill |
| `workflow/bullshit/IMPRESSION_ANCHORS.md` (new), `IMPRESSIONS.md`, `INDEX.md` | D5, D6, D4 |
| `workflow/bullshit/*.md`, `workflow/**`, `docs/**` that cite a moved id | D7, by one scripted pass |
| `.claude/agents/ch-bsd.md`, `.claude/agents/ch-bsd.local.md`, `workflow/ORCHESTRATION.md` | D3, D4, D8 |
| `tests/test_bsd_findings_ledger.py` (new), `tests/test_gmd_body_anchors.py` | AC-1 to AC-4 |

## Risks (self-audit) {#risks}

1. **Real:** run `scripts/bsd-tally.py` and `./scripts/lint-gmd.sh` on the branch; paste both.
2. **Wiring:** the tests run the script as a subprocess and parse the real files; no helper is
   called directly.
3. **Census:** readers of `IMPRESSIONS.md` by path: `tests/test_gmd_body_anchors.py` (changed
   here), `tests/test_bug179_anchor_parity.py` (reads a historic blob, unaffected),
   `memory_index.py:688` (a pointer string, still true), 31.3's spec (its census of this file
   is recounted at its RED). Writers: ch-bsd and the lead ([[orchestration#reports]]).
4. **Bound:** the script reads two files; no daemon, no store.
5. **Busy / down:** not applicable: nothing here talks to a daemon.
6. **Guard:** AC-2 and AC-3 each plant the failing input.
7. **Loud:** AC-2's exit 1 and stderr line.
8. **Handoff:** the commit-time form of the cap and of the unfilled cell is an I1.e `check`
   unit (the lead adds the clause to the I1.e row); `bsd-pass` (I1.d) carries D3's sentence
   ([[task-I1.d-first-skills#ac-3]]). After the merge the lead checks one moved id on the live
   store: `rmx context "bsd-impression-anchors#imp-two-paths" --no-grep`.

## For the user {#for-the-user}

None. One note for the lead: D6's memory write and the bridge run are the lead's, in the same
sitting as the merge, so the new pointer lines resolve.
